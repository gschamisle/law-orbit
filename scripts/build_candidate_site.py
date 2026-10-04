"""Add accepted candidate fields to a verified snapshot without rebuilding old data.

Example: python -m scripts.build_candidate_site --base output/previous-site
    --dest output/candidate-preview --bundle privacy=output/privacy-universe/bundle.json
    --bundle prices=output/prices-universe/bundle.json

Input folders, bundle files and previous previews are never overwritten. The
unpacked staging tree is not a deployable artifact; only the final validated,
repacked destination may be reviewed for publication.
"""
import argparse
from collections.abc import Mapping
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from core.domain_navigation import ordered_domains
from core.ftc_universe import overview_graph
from core.mofe_profiles import WORK_PROFILES
from core.mofe_universe import assessment, load_bundle, report
from scripts.build_static_galaxies import Writer, export_documents, overview, read, shell, workbench
from scripts.build_procurement_pdf_site import materialize_reachable
from scripts.compact_static_galaxies import convert
from scripts.static_storage import Storage
from scripts.validate_static_galaxies import validate

CANDIDATES = ('privacy', 'prices', 'subsidy')


def bundle_argument(value):
    """Split only the first '='; a Windows path may itself contain that character."""
    if '=' not in value:
        raise argparse.ArgumentTypeError('Use --bundle domain=path')
    domain, name = value.split('=', 1)
    if domain not in CANDIDATES or not name.strip():
        raise argparse.ArgumentTypeError('Only privacy, prices or subsidy bundle paths are supported')
    return domain, Path(name)


def normalized_bundles(values):
    items = list(values.items()) if isinstance(values, Mapping) else list(values)
    if not items:
        raise ValueError('At least one candidate bundle is required')
    if any(domain not in CANDIDATES for domain, _ in items):
        raise ValueError('Unsupported candidate domain')
    domains = [domain for domain, _ in items]
    if len(set(domains)) != len(domains):
        raise ValueError('Duplicate candidate domain')
    return [(domain, Path(path).resolve()) for domain, path in items]


def output_paths(base, bundles, destination):
    base, destination = Path(base).resolve(), Path(destination).resolve()
    staging = destination.with_name(destination.name + '-unpacked')
    report_path = destination.with_name(destination.name + '-report.json')
    if any(path.exists() for path in (destination, staging, report_path)):
        raise ValueError('Choose new outputs; previous outputs are preserved')
    protected = [base, *(path for _, path in bundles)]
    for output in (destination, staging, report_path):
        if any(output == path or output.is_relative_to(path) or path.is_relative_to(output)
               for path in protected):
            raise ValueError('Choose independent outputs outside every input')
    return base, destination, staging, report_path


def check_preserved(base, destination, original, final):
    """Verify the old catalog identity, cross-field metadata and every nested shard."""
    old_domains = original['domains']
    new_domains = final['domains']
    by_id = {domain['id']: domain for domain in new_domains}
    if len(by_id) != len(new_domains):
        raise ValueError('Duplicate output domain')
    if ordered_domains(new_domains) != new_domains:
        raise ValueError('Output domain order changed')
    if any(by_id.get(domain['id']) != domain for domain in old_domains):
        raise ValueError('Existing domain metadata changed')
    if original.get('cross_domain') != final.get('cross_domain'):
        raise ValueError('Cross-domain metadata changed')
    # Preserve other manifest-level public data too, rather than checking only
    # the currently known fields. Version and transport packs may change.
    for key, value in original.items():
        if key not in ('domains', 'version', 'data_packs') and final.get(key) != value:
            raise ValueError('Existing manifest metadata changed: ' + key)
    before, after = Storage(base, original), Storage(destination, final)
    seen = set()
    pending = [original]
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            if {'url', 'bytes', 'sha256'} <= value.keys():
                if value['url'] in seen:
                    continue
                seen.add(value['url'])
                raw = before.raw(value)
                if raw != after.raw(value):
                    raise ValueError('Existing logical corpus changed')
                pending.append(before.read(value))
            else:
                pending.extend(child for key, child in value.items() if key != 'data_packs')
        elif isinstance(value, list):
            pending.extend(value)
    return len(seen)


def build(base, destination, bundles):
    bundles = normalized_bundles(bundles)
    base, destination, staging, report_path = output_paths(base, bundles, destination)
    original_manifest_bytes = (base / 'manifest.json').read_bytes()
    original = read(base / 'manifest.json')
    if any(domain in {d['id'] for d in original['domains']} for domain, _ in bundles):
        raise ValueError('An added candidate is already present in the base site')
    baseline = validate(base)
    accepted = []
    # Complete every source/profile/acceptance check before creating any folder.
    for domain, path in bundles:
        bundle_bytes = path.read_bytes()
        bundle = load_bundle(domain, path)
        fresh = assessment(bundle)
        if fresh.get('decision') != 'limited-release':
            raise ValueError('Candidate release gate failed: ' + domain)
        if domain not in WORK_PROFILES:
            raise ValueError('Candidate profile has not been integrated: ' + domain)
        accepted.append((domain, path, bundle, hashlib.sha256(bundle_bytes).hexdigest(), fresh))
    staging.mkdir(parents=True)
    shell(staging)
    manifest = deepcopy(original)
    manifest.pop('data_packs', None)
    writer = Writer(staging)
    summaries = {}
    for domain, _, bundle, source_sha256, fresh in accepted:
        profile = WORK_PROFILES[domain]
        docs = bundle['source']['laws'] + bundle['source']['administrative_rules']
        graph = bundle['graph']
        entries, ids = export_documents(writer, domain, '', docs, graph)
        map_graph = overview_graph(bundle)
        catalog = dict(
            laws=entries, overview=writer.data(overview(map_graph, domain, ids, entries)),
            coverage=graph['coverage_note'], built_at=graph['built_at'], sectors=profile['sectors'],
            workbench=workbench(bundle, ids), collection_summary=report(bundle),
            text_summary=dict(documents=sum(bool(d.get('text_analysis')) for d in docs),
                              citations=len(graph.get('text_citations', [])),
                              issues=len(graph.get('text_citation_issues', []))),
        )
        for key in ('sector_aliases', 'default_laws', 'default_refs'):
            if profile.get(key):
                catalog[key] = deepcopy(profile[key])
        manifest['domains'].append(dict(id=domain, title=profile['title'], laws=len(entries),
                                       catalog=writer.data(catalog), built_at=graph['built_at']))
        summaries[domain] = dict(bundle_sha256=source_sha256, assessment=fresh,
                                 collection=report(bundle), documents=len(entries))
    manifest['domains'] = ordered_domains(manifest['domains'])
    manifest.pop('version', None)
    manifest['version'] = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()[:20]
    (staging / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, separators=(',', ':')),
                                         encoding='utf-8')
    # New content-addressed assets already exist in staging; the helper copies
    # only the old still-reachable members, checking every length and checksum.
    materialize_reachable(base, staging, manifest)
    convert(staging, destination, validate_site=False)
    verified = validate(destination)  # Final content and hosting guards are mandatory.
    final = read(destination / 'manifest.json')
    preserved = check_preserved(base, destination, original, final)
    if (base / 'manifest.json').read_bytes() != original_manifest_bytes:
        raise ValueError('Source manifest changed during the build')
    if any(hashlib.sha256(path.read_bytes()).hexdigest() != digest
           for _, path, _, digest, _ in accepted):
        raise ValueError('Source bundle changed during the build')
    result = dict(
        before=baseline, verification=verified, version=final['version'],
        added_domains=[domain for domain, _ in bundles],
        original_domains_unchanged=True, original_logical_assets_unchanged=preserved,
        original_cross_domain_unchanged=True, source_manifest_unchanged=True,
        source_bundles_unchanged=True,
        added_site_files=verified['site_files'] - baseline['site_files'],
        added_site_bytes=verified['site_bytes'] - baseline['site_bytes'],
        candidates=summaries,
    )
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--dest', type=Path, required=True)
    parser.add_argument('--bundle', type=bundle_argument, action='append', required=True)
    args = parser.parse_args()
    result = build(args.base, args.dest, args.bundle)
    print(json.dumps({key: value for key, value in result.items() if key != 'candidates'},
                     ensure_ascii=False, indent=2))
