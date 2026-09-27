"""Verified transport for legacy shards and byte-preserving small-file packs."""
import base64
from collections import OrderedDict
import gzip
import hashlib
import json
from pathlib import Path
import re

PACK_KIND = 'law-orbit-small-files'
THRESHOLD = 8192


def verify(raw, ref):
    if (not re.fullmatch(r'[0-9a-f]{64}', str(ref.get('sha256', '')))
            or ref.get('url') != 'data/' + ref['sha256'] + '.json.gz'):
        raise ValueError('Unsafe data path')
    if len(raw) != ref['bytes'] or hashlib.sha256(raw).hexdigest() != ref['sha256']:
        raise ValueError('Asset checksum or length mismatch')
    return raw


class Storage:
    def __init__(self, root, manifest=None):
        self.root = Path(root)
        if manifest is None:
            path = self.root / 'manifest.json'
            manifest = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        self.config = manifest.get('data_packs')
        self.loaded = OrderedDict()
        self.physical = {}
        self.members = set()
        self.declared = set()
        if self.config is not None:
            if (self.config.get('schema') != 1 or self.config.get('threshold') != THRESHOLD
                    or self.config.get('prefix_chars') != 2
                    or not isinstance(self.config.get('buckets'), dict)
                    or not all(re.fullmatch(r'[0-9a-f]{2}', k) for k in self.config['buckets'])):
                raise ValueError('Invalid small-file packing configuration')

    def physical_bytes(self, ref):
        # Validate before resolving any path.
        if not re.fullmatch(r'[0-9a-f]{64}', str(ref.get('sha256', ''))) or ref.get('url') != 'data/' + ref['sha256'] + '.json.gz':
            raise ValueError('Unsafe data path')
        raw = verify((self.root / ref['url']).read_bytes(), ref)
        if len(raw) > 25 * 1024 * 1024:
            raise ValueError('Free hosting asset limit exceeded')
        self.physical[ref['url']] = len(raw)
        return raw

    def pack(self, prefix):
        if prefix in self.loaded:
            self.loaded.move_to_end(prefix)
            return self.loaded[prefix]
        ref = self.config['buckets'].get(prefix)
        if not ref:
            raise ValueError('Missing small-file pack')
        value = json.loads(gzip.decompress(self.physical_bytes(ref)))
        if value.get('kind') != PACK_KIND or value.get('schema') != 1 or not isinstance(value.get('entries'), dict) or not value['entries']:
            raise ValueError('Invalid small-file pack')
        for digest, encoded in value['entries'].items():
            if not re.fullmatch(prefix + r'[0-9a-f]{62}', digest):
                raise ValueError('Wrong pack prefix')
            try:
                raw = base64.b64decode(encoded, validate=True)
            except (ValueError, TypeError) as exc:
                raise ValueError('Invalid packed data encoding') from exc
            if len(raw) > THRESHOLD or hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError('Packed member checksum or size mismatch')
            self.declared.add(digest)
        self.loaded[prefix] = value['entries']
        while len(self.loaded) > 256:
            self.loaded.popitem(last=False)
        return value['entries']

    def raw(self, ref):
        if self.config and ref['bytes'] <= THRESHOLD:
            digest = ref['sha256']
            encoded = self.pack(digest[:2]).get(digest)
            if encoded is None:
                raise ValueError('Referenced small-file member missing')
            raw = verify(base64.b64decode(encoded, validate=True), ref)
            self.members.add(digest)
            return raw
        return self.physical_bytes(ref)

    def read(self, ref):
        return json.loads(gzip.decompress(self.raw(ref)))

    def check_inventory(self):
        if self.config:
            for prefix in self.config['buckets']:
                self.pack(prefix)
            if self.declared != self.members:
                raise ValueError('Unexpected or unreferenced packed members')
        actual = {p.relative_to(self.root).as_posix() for p in (self.root / 'data').glob('*.gz')}
        if actual != set(self.physical):
            raise ValueError('Unexpected or unreferenced data files')
