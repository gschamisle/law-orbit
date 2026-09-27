"""Pack small verified public files into bounded hash buckets; preserve source."""
import argparse
import base64
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import shutil

from scripts.static_storage import PACK_KIND, THRESHOLD, Storage


def convert(source, destination, *, unpack=False, validate_site=True):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists() or destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError('Choose a new independent destination; existing files are preserved')
    from scripts.validate_static_galaxies import validate
    if validate_site:
        validate(source)
    manifest = json.loads((source / 'manifest.json').read_text(encoding='utf-8'))
    storage = Storage(source, manifest)
    destination.mkdir(parents=True)
    (destination / 'data').mkdir()
    # Only public web assets are copied, from an already verified site.
    for path in source.iterdir():
        if path.name in ('data', 'manifest.json'):
            continue
        if path.is_dir():
            shutil.copytree(path, destination / path.name)
        else:
            shutil.copy2(path, destination / path.name)
    buckets = defaultdict(dict)
    logical = set()
    pending = []

    def refs(value):
        if isinstance(value, dict):
            if {'url', 'bytes', 'sha256'} <= value.keys():
                pending.append(value)
            for key, item in value.items():
                if key != 'data_packs':
                    refs(item)
        elif isinstance(value, list):
            for item in value:
                refs(item)

    refs(manifest)
    while pending:
        ref = pending.pop()
        if ref['url'] in logical:
            continue
        raw = storage.raw(ref)
        logical.add(ref['url'])
        refs(json.loads(gzip.decompress(raw)))
        if not unpack and len(raw) <= THRESHOLD:
            buckets[ref['sha256'][:2]][ref['sha256']] = base64.b64encode(raw).decode('ascii')
        else:
            (destination / ref['url']).write_bytes(raw)
    storage.check_inventory()
    manifest.pop('data_packs', None)
    if not unpack:
        pack_refs = {}
        for prefix, entries in sorted(buckets.items()):
            payload = dict(kind=PACK_KIND, schema=1, entries=dict(sorted(entries.items())))
            raw = gzip.compress(json.dumps(payload, separators=(',', ':')).encode(), compresslevel=6, mtime=0)
            if len(raw) > 1024 * 1024:
                raise ValueError('Small-file pack exceeds 1 MiB; revise bucket granularity')
            digest = hashlib.sha256(raw).hexdigest()
            url = 'data/' + digest + '.json.gz'
            (destination / url).write_bytes(raw)
            pack_refs[prefix] = dict(url=url, bytes=len(raw), sha256=digest)
        manifest['data_packs'] = dict(schema=1, threshold=THRESHOLD, prefix_chars=2, buckets=pack_refs)
    # Data version, domain catalogs, logical hashes and editions are unchanged.
    (destination / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    result = validate(destination) if validate_site else {}
    result.update(logical_files=len(logical), packed_members=sum(map(len, buckets.values())), packs=len(buckets))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--unpack', action='store_true', help='Materialize original shards for incremental rebuilds')
    args = parser.parse_args()
    print(json.dumps(convert(args.source, args.destination, unpack=args.unpack), indent=2))
