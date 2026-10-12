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


def attach_integrity_links(root, manifest, writer=None):
    original = deepcopy(manifest['domains'])
    writer = writer or Writer(root)
    storage = Storage(root, manifest)
    scope = {d for pair in INTEGRITY_PAIRS for d in pair}
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
        if any(storage.read(ref).get('peer') == 'integrity' for ref in values) or domain == 'integrity' and values:
            raise ValueError('Integrity connections already exist; choose an earlier base')
    reports = {}
    for pair in INTEGRITY_PAIRS:
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
    return reports


def build(base, destination):
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
    reports = attach_integrity_links(staging, manifest)
    manifest.pop('version', None)
    manifest['version'] = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()[:20]
    (staging / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    convert(staging, destination, validate_site=False)
    verified = validate(destination)
    final = json.loads((destination / 'manifest.json').read_text(encoding='utf-8'))
    # The approved change adds overlay metadata, never rewrites old law shards.
    comparison = deepcopy(final)
    comparison['cross_domain'] = deepcopy(original.get('cross_domain', {}))
    preserved = check_preserved(base, destination, original, comparison)
    if (base / 'manifest.json').read_bytes() != original_bytes:
        raise ValueError('Input site was changed')
    result = dict(verification=verified, bridges=reports, original_logical_assets_unchanged=preserved,
                  original_domains_unchanged=True, source_site_unchanged=True)
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base', type=Path, required=True)
    p.add_argument('--dest', type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(build(a.base, a.dest), ensure_ascii=False, indent=2))
