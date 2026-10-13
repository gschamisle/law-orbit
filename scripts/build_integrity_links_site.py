"""Attach selected ACRC peer evidence while preserving every existing catalog."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from core.forex_finance_links import INTEGRITY_PAIRS, bridge
from scripts.build_forex_finance_site import snapshot, payloads
from scripts.build_static_galaxies import ROOT, Writer, shell
from scripts.compact_static_galaxies import convert
from scripts.static_storage import Storage
from scripts.validate_static_galaxies import validate
from scripts.build_candidate_site import check_preserved


def preserved_bridge_manifest(root, manifest):
    """Compare original bridge payloads, not replaced grouping containers."""
    result = deepcopy(manifest)
    storage = Storage(root, manifest)
    result['cross_domain'] = {}
    for domain, ref in manifest.get('cross_domain', {}).items():
        value = storage.read(ref)
        result['cross_domain'][domain] = value['bridges'] if value.get('kind') == 'domain-bridge-set' else [ref]
    return result


def retire_replaced_groups(staging, original, current):
    """Remove only obsolete group indexes in this new unpacked build tree."""
    staging = Path(staging).resolve()
    if not staging.is_relative_to((ROOT / 'output').resolve()) or current.get('data_packs'):
        raise ValueError('Use a new unpacked project output tree')
    storage = Storage(staging, {})
    used = set()
    for ref in current.get('cross_domain', {}).values():
        used.add(ref['url'])
        value = storage.read(ref)
        if value.get('kind') == 'domain-bridge-set':
            used.update(r['url'] for r in value['bridges'])
    retired = []
    for ref in original.get('cross_domain', {}).values():
        if ref['url'] in used:
            continue
        value = storage.read(ref)  # verifies the hash and safe content-addressed path
        if value.get('kind') != 'domain-bridge-set':
            raise ValueError('An original bridge payload would be removed')
        if not all(r['url'] in used for r in value['bridges']):
            raise ValueError('An original group member would be lost')
        target = (staging / ref['url']).resolve()
        if target.parent != staging / 'data':
            raise ValueError('Unsafe group container path')
        target.unlink()
        retired.append(ref['url'])
    return retired


def attach_integrity_links(root, manifest, writer=None):
    return attach_selected_links(root, manifest, INTEGRITY_PAIRS, 'integrity', writer)


def attach_selected_links(root, manifest, pairs, hub, writer=None):
    original = deepcopy(manifest['domains'])
    writer = writer or Writer(root)
    storage = Storage(root, manifest)
    scope = {d for pair in pairs for d in pair}
    snapshots = {d: snapshot(root, next(e for e in manifest['domains'] if e['id'] == d)) for d in scope}
    existing = manifest.get('cross_domain', {})
    refs = {}
    for domain in scope:
        if domain not in existing:
            refs[domain] = []
            continue
        value = storage.read(existing[domain])
        refs[domain] = list(value['bridges']) if value.get('kind') == 'domain-bridge-set' else [existing[domain]]
    for domain, values in refs.items():
        if any(storage.read(ref).get('peer') == hub for ref in values) or domain == hub and values:
            raise ValueError(hub + ' connections already exist; choose an earlier base')
    reports = {}
    for pair in pairs:
        print('Checking official citation evidence: ' + ' / '.join(pair), flush=True)
        selected = {d: snapshots[d] for d in pair}
        result = bridge(selected, pair=pair)
        linked = payloads(result, selected)
        for domain in pair:
            refs[domain].append(writer.data(linked[domain]))
        reports[pair[1]] = result['report']
    manifest.setdefault('cross_domain', {})
    for domain, values in refs.items():
        manifest['cross_domain'][domain] = values[0] if len(values) == 1 else writer.data(
            dict(kind='domain-bridge-set', schema=1, domain=domain, bridges=values))
    if manifest['domains'] != original:
        raise ValueError('Existing catalog changed')
    if hub == 'remedy':
        from core.remedy_relations import reading_guide
        snap = snapshots[hub]
        docs = [dict(name=e['name'], effective=e['effective'], source_url=e['url'],
                     articles=snap['documents'][e['id']]['articles']) for e in snap['entries']]
        guide = reading_guide(docs)
        ids = {e['name']: e['id'] for e in snap['entries']}
        for row in guide['entries']:
            row['law_id'] = ids[row['law']]
        manifest['remedy_guide'] = guide
    return reports


def build(base, destination, *, hub='integrity'):
    base, destination = Path(base).resolve(), Path(destination).resolve()
    allowed = (ROOT / 'output').resolve()
    staging = destination.with_name(destination.name + '-unpacked')
    report_path = destination.with_name(destination.name + '-report.json')
    if not all(p.is_relative_to(allowed) for p in (base, destination, staging, report_path)):
        raise ValueError('Use project output directories')
    if any(p.exists() for p in (destination, staging, report_path)):
        raise ValueError('Preserve existing outputs; select a new destination')
    validate(base)
    original_bytes = (base / 'manifest.json').read_bytes()
    original = json.loads(original_bytes)
    convert(base, staging, unpack=True, validate_site=False)
    shell(staging)
    manifest = json.loads((staging / 'manifest.json').read_text(encoding='utf-8'))
    if hub == 'integrity':
        reports = attach_integrity_links(staging, manifest)
    elif hub == 'remedy':
        from core.forex_finance_links import REMEDY_PAIRS
        reports = attach_selected_links(staging, manifest, REMEDY_PAIRS, hub)
    else:
        raise ValueError('Unknown selected bridge hub')
    manifest.pop('version', None)
    manifest['version'] = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()[:20]
    (staging / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    retired = retire_replaced_groups(staging, original, manifest)
    convert(staging, destination, validate_site=False)
    verified = validate(destination)
    final = json.loads((destination / 'manifest.json').read_text(encoding='utf-8'))
    # The approved change adds overlay metadata, never rewrites old law shards.
    comparison = deepcopy(final)
    preserved_original = preserved_bridge_manifest(base, original)
    comparison['cross_domain'] = deepcopy(preserved_original['cross_domain'])
    preserved = check_preserved(base, destination, preserved_original, comparison)
    if (base / 'manifest.json').read_bytes() != original_bytes:
        raise ValueError('Input site was changed')
    result = dict(verification=verified, bridges=reports, original_logical_assets_unchanged=preserved,
                  original_domains_unchanged=True, source_site_unchanged=True,
                  replaced_group_containers=retired)
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base', type=Path, required=True)
    p.add_argument('--dest', type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(build(a.base, a.dest), ensure_ascii=False, indent=2))
