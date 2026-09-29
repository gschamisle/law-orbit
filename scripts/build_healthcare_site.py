"""Expand only medical in a new public snapshot; preserve all other evidence."""
import argparse
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path

from core.mofe_profiles import WORK_PROFILES
from core.mofe_universe import assessment, documents, report, validate_bundle
from scripts.build_static_galaxies import Writer, export_documents, overview, shell, workbench
from scripts.build_procurement_pdf_site import materialize_reachable
from scripts.compact_static_galaxies import convert
from scripts.static_storage import Storage
from scripts.validate_static_galaxies import validate

DOMAIN = 'medical'
TITLE = '보건·의료'


def article_projection(document, effective):
    return [(str(a['jo']), a.get('title', ''), a.get('text', ''),
             a.get('effective', effective), bool(a.get('deleted')))
            for a in document['articles']]


def check_current_documents(base, catalog, source):
    """Allow additions and retagging, never replace the eight published editions."""
    storage = Storage(base)
    docs = documents(source)
    by_name = {d['name']: d for d in docs}
    entries = {e['name']: e for e in catalog['laws']}
    if len(by_name) != len(docs) or len(entries) != len(catalog['laws']):
        raise ValueError('Duplicate medical document name')
    if len(entries) != 8 or not entries.keys() <= by_name.keys():
        raise ValueError('Original eight medical documents are missing')
    analyses = []
    article_count = 0
    for name, entry in entries.items():
        current, law = storage.read(entry['file']), by_name[name]
        if (law['effective'] != entry['effective'] or
                article_projection(law, law['effective']) != article_projection(current, entry['effective'])):
            raise ValueError('Current public edition changed: ' + name)
        article_count += len(current['articles'])
        annexes = {a['ref']: a for a in law.get('annexes', [])}
        if len(annexes) != len(law.get('annexes', [])):
            raise ValueError('Duplicate medical annex reference: ' + name)
        for old in current.get('annexes', []):
            new = annexes.get(old['ref'])
            if new is None or any(old.get(k) != new.get(k) for k in ('ref', 'title', 'effective', 'urls')):
                raise ValueError('Published annex identity changed: ' + name + ' ' + old['ref'])
            if old.get('analysis'):
                if old['analysis'] != new.get('body_analysis'):
                    raise ValueError('Published annex analysis changed: ' + name + ' ' + old['ref'])
                analyses.append(dict(law=name, ref=old['ref'],
                                     text_sha256=old['analysis']['text_sha256'],
                                     file_sha256=old['analysis']['file_sha256']))
    if len(analyses) != 4:
        raise ValueError('Expected four published medical annex analyses')
    return dict(documents=len(entries), articles=article_count, annexes=analyses)


def check_exported_documents(base, old_catalog, destination, new_catalog):
    """Recheck the public export, independently of the source-to-export pipeline."""
    storage = Storage(destination)
    docs = []
    for entry in new_catalog['laws']:
        public = storage.read(entry['file'])
        docs.append(dict(name=entry['name'], effective=entry['effective'], articles=public['articles'],
                         annexes=[{**a, 'body_analysis': a.get('analysis')}
                                  for a in public.get('annexes', [])]))
    return check_current_documents(base, old_catalog, dict(laws=docs))


def check_unchanged_domains(base, destination, original, final):
    """Verify unchanged metadata and every reachable logical asset byte."""
    if [d['id'] for d in original['domains']] != [d['id'] for d in final['domains']]:
        raise ValueError('Domain membership or order changed')
    untouched = [d for d in original['domains'] if d['id'] != DOMAIN]
    if untouched != [d for d in final['domains'] if d['id'] != DOMAIN]:
        raise ValueError('Unrelated domain metadata changed')
    exclude = {'domains', 'version', 'data_packs'}
    if {k:v for k,v in original.items() if k not in exclude} != {k:v for k,v in final.items() if k not in exclude}:
        raise ValueError('Cross-domain or shared metadata changed')
    before, after = Storage(base, original), Storage(destination, final)
    pending = [{**{k:v for k,v in original.items() if k not in exclude}, 'domains': untouched}]
    seen = set()
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            if {'url', 'bytes', 'sha256'} <= item.keys():
                if item['url'] in seen:
                    continue
                seen.add(item['url'])
                raw = before.raw(item)
                if raw != after.raw(item):
                    raise ValueError('Unrelated logical asset changed: ' + item['url'])
                pending.append(json.loads(gzip.decompress(raw)))
            else:
                pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    return dict(untouched_domains=[d['id'] for d in untouched],
                unchanged_logical_assets=len(seen), cross_domain_unchanged=True)


def output_paths(base, bundle, destination):
    base, bundle, destination = Path(base).resolve(), Path(bundle).resolve(), Path(destination).resolve()
    stage = destination.with_name(destination.name + '-unpacked')
    result = destination.with_name(destination.name + '-report.json')
    if any(p.exists() for p in (destination, stage, result)):
        raise ValueError('Choose a new destination; previous outputs are preserved')
    for output in (destination, stage):
        if output.is_relative_to(base) or base.is_relative_to(output) or bundle.is_relative_to(output):
            raise ValueError('Choose an independent destination outside the immutable inputs')
    return base, bundle, destination, stage, result


def build(base, bundle, destination):
    base, bundle_path, destination, stage, result_path = output_paths(base, bundle, destination)
    manifest_raw = (base / 'manifest.json').read_bytes()
    bundle_raw = bundle_path.read_bytes()
    original = json.loads(manifest_raw)
    ids = [d['id'] for d in original['domains']]
    if len(ids) != 15 or len(set(ids)) != 15 or ids.count(DOMAIN) != 1:
        raise ValueError('Expected the published fifteen-domain base snapshot')
    baseline = validate(base)
    source_bundle = validate_bundle(json.loads(bundle_raw), DOMAIN)
    acceptance = assessment(source_bundle)
    if acceptance['decision'] != 'limited-release':
        raise ValueError('Healthcare workbench evidence did not pass the release gate')
    source, graph = source_bundle['source'], source_bundle['graph']
    old_domain = next(d for d in original['domains'] if d['id'] == DOMAIN)
    old_catalog = Storage(base, original).read(old_domain['catalog'])
    preserved = check_current_documents(base, old_catalog, source)
    print('Verified the original eight medical editions and four annex analyses', flush=True)

    stage.mkdir(parents=True)
    # Uses the current reviewed web shell and introduction; no source-site files are edited.
    shell(stage)
    writer = Writer(stage)
    entries, law_ids = export_documents(writer, DOMAIN, '', documents(source), graph)
    profile = WORK_PROFILES[DOMAIN]
    map_data = overview(graph, DOMAIN, law_ids, entries)
    map_data['galaxy_title'] = TITLE
    catalog = deepcopy(old_catalog)
    collection = report(source_bundle)
    catalog.update(laws=entries, overview=writer.data(map_data), coverage=graph['coverage_note'],
                   built_at=graph['built_at'], sectors=deepcopy(profile['sectors']),
                   workbench=workbench(source_bundle, law_ids), collection_summary=collection)
    catalog.pop('sector_aliases', None)
    if profile.get('sector_aliases'):
        catalog['sector_aliases'] = deepcopy(profile['sector_aliases'])
    manifest = deepcopy(original)
    manifest.pop('data_packs', None)
    domain = next(d for d in manifest['domains'] if d['id'] == DOMAIN)
    domain.update(title=TITLE, laws=len(entries), catalog=writer.data(catalog), built_at=graph['built_at'])
    manifest.pop('version', None)
    manifest['version'] = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()[:20]
    (stage / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    materialize_reachable(base, stage, manifest)
    convert(stage, destination, validate_site=False)
    print('Packed the healthcare expansion; validating all fifteen domains', flush=True)
    verification = validate(destination)
    final = json.loads((destination / 'manifest.json').read_bytes())
    unchanged = check_unchanged_domains(base, destination, original, final)
    check_exported_documents(base, old_catalog, destination, catalog)
    if (base / 'manifest.json').read_bytes() != manifest_raw or bundle_path.read_bytes() != bundle_raw:
        raise ValueError('Immutable source changed during build')
    result = dict(verification=verification, baseline_verification=baseline,
                  base_manifest_sha256=hashlib.sha256(manifest_raw).hexdigest(),
                  healthcare_source_sha256=hashlib.sha256(bundle_raw).hexdigest(),
                  preserved_medical=preserved, **unchanged, collection=collection,
                  current_documents=len(entries), current_articles=sum(len(d['articles']) for d in documents(source)),
                  added_documents=len(entries)-preserved['documents'], source_unchanged=True)
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('base-site', 'bundle', 'destination'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.base_site, args.bundle, args.destination), ensure_ascii=False, indent=2))
