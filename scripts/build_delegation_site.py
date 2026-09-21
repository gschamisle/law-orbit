"""Refresh the browser shell and add comparison baselines without recollecting laws."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
from scripts.build_static_galaxies import Writer, read, shell
from scripts.delegation_baseline import DOMAINS, attach_catalog, read_ref
from scripts.validate_static_galaxies import validate


def build(base, destination, previous=None):
    base, destination = Path(base), Path(destination)
    if destination.exists():
        raise ValueError('Use a new destination; existing builds are preserved')
    validate(base)
    if previous:
        validate(Path(previous))
    original = read(base / 'manifest.json')
    manifest = read(base / 'manifest.json')
    destination.mkdir(parents=True)
    shell(destination)
    writer = Writer(destination)
    # Copy verified current shards first. They are never edited in place.
    shutil.copytree(base / 'data', destination / 'data')
    for domain in manifest['domains']:
        if domain['id'] not in DOMAINS:
            continue
        catalog = read_ref(base, domain['catalog'])
        attach_catalog(writer, domain['id'], catalog, previous)
        domain['catalog'] = writer.data(catalog)
    manifest.pop('version', None)
    manifest['version'] = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()[:20]
    (destination / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    pending = []
    seen = set()
    def refs(value):
        if isinstance(value, dict):
            if {'url', 'sha256', 'bytes'} <= value.keys():
                pending.append(value)
            for v in value.values():
                refs(v)
        elif isinstance(value, list):
            for v in value:
                refs(v)
    refs(manifest)
    while pending:
        ref = pending.pop()
        if ref['url'] in seen:
            continue
        seen.add(ref['url'])
        refs(read_ref(destination, ref))
    # Only unused copied catalogs in this newly created destination can be removed.
    for path in (destination / 'data').glob('*.json.gz'):
        if path.relative_to(destination).as_posix() not in seen:
            path.unlink()
    for old, new in zip(original['domains'], manifest['domains']):
        if old['id'] not in DOMAINS and old != new:
            raise ValueError('Other domain changed')
        if old['id'] in DOMAINS:
            old_catalog, new_catalog = read_ref(base, old['catalog']), read_ref(destination, new['catalog'])
            old_catalog.pop('delegation_review', None); new_catalog.pop('delegation_review', None)
            if old_catalog != new_catalog:
                raise ValueError('Existing public law data changed')
    result = validate(destination)
    result['law_data_unchanged'] = True
    result['baseline_domains'] = list(DOMAINS)
    (destination.parent / (destination.name + '-report.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-site', type=Path, required=True)
    p.add_argument('--destination', type=Path, required=True)
    p.add_argument('--previous-site', type=Path)
    a = p.parse_args()
    print(json.dumps(build(a.base_site, a.destination, a.previous_site), ensure_ascii=False, indent=2))
