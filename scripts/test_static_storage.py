"""Storage round trips preserve exact original bytes and fail closed."""
import base64
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.compact_static_galaxies import convert
from scripts.static_storage import Storage, THRESHOLD


def write(root, value):
    raw = gzip.compress(json.dumps(value, ensure_ascii=False).encode(), mtime=0)
    digest = hashlib.sha256(raw).hexdigest()
    ref = dict(url=f'data/{digest}.json.gz', sha256=digest, bytes=len(raw))
    (root / ref['url']).write_bytes(raw)
    return ref


class StorageTests(unittest.TestCase):
    def setUp(self):
        output = Path(__file__).resolve().parents[1] / 'output'
        output.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=output)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'original'
        (self.source / 'data').mkdir(parents=True)
        self.leaf = write(self.source, {'text': '법인세법 제60조 본문', 'version': 'fixture'})
        self.parent = write(self.source, {'next': self.leaf, 'meta': {'domain': 'tax'}})
        # Incompressible-enough, deterministic content remains a standalone asset.
        large = ''.join(hashlib.sha256(str(i).encode()).hexdigest() for i in range(500))
        self.large = write(self.source, {'text': large})
        self.assertGreater(self.large['bytes'], THRESHOLD)
        self.manifest = dict(schema=1, version='unchanged-law-edition', domains=[dict(catalog=self.parent)], extra=self.large)
        (self.source / 'manifest.json').write_text(json.dumps(self.manifest), encoding='utf-8')
        (self.source / 'index.html').write_text('viewer', encoding='utf-8')
        self.packed = self.root / 'packed'

    def compact(self):
        return convert(self.source, self.packed, validate_site=False)

    def test_exact_roundtrip_preserves_original_manifest_and_bytes(self):
        original = {p.relative_to(self.source): p.read_bytes() for p in self.source.rglob('*') if p.is_file()}
        result = self.compact()
        self.assertEqual(result['packed_members'], 2)
        self.assertFalse((self.packed / self.leaf['url']).exists())
        self.assertTrue((self.packed / self.large['url']).exists())
        storage = Storage(self.packed)
        for ref in (self.leaf, self.parent, self.large):
            self.assertEqual(storage.raw(ref), original[Path(ref['url'])])
        storage.check_inventory()
        restored = self.root / 'restored'
        convert(self.packed, restored, unpack=True, validate_site=False)
        self.assertEqual(json.loads((restored / 'manifest.json').read_text()), self.manifest)
        for path, raw in original.items():
            self.assertEqual((self.source / path).read_bytes(), raw)
            if path.name != 'manifest.json':
                self.assertEqual((restored / path).read_bytes(), raw)

    def test_existing_and_nested_destinations_are_never_overwritten(self):
        self.compact()
        for dest in (self.source, self.packed, self.source / 'nested'):
            with self.assertRaises(ValueError):
                convert(self.source, dest, validate_site=False)

    def test_deterministic_packs(self):
        self.compact()
        second = self.root / 'same'
        convert(self.source, second, validate_site=False)
        self.assertEqual((self.packed / 'manifest.json').read_bytes(), (second / 'manifest.json').read_bytes())

    def test_corrupt_pack_and_missing_member_fail(self):
        self.compact()
        manifest = json.loads((self.packed / 'manifest.json').read_text())
        ref = manifest['data_packs']['buckets'][self.leaf['sha256'][:2]]
        raw = (self.packed / ref['url']).read_bytes()
        (self.packed / ref['url']).write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
        with self.assertRaisesRegex(ValueError, 'checksum'):
            Storage(self.packed).read(self.leaf)
        (self.packed / ref['url']).write_bytes(raw)
        bad = {**self.leaf, 'sha256': self.leaf['sha256'][:2] + '0' * 62}
        bad['url'] = f"data/{bad['sha256']}.json.gz"
        with self.assertRaisesRegex(ValueError, 'missing'):
            Storage(self.packed).read(bad)

    def test_orphaned_members_and_wrong_lengths_fail(self):
        self.compact()
        storage = Storage(self.packed)
        storage.read(self.large)
        with self.assertRaisesRegex(ValueError, 'unreferenced'):
            storage.check_inventory()
        with self.assertRaisesRegex(ValueError, 'length'):
            Storage(self.packed).read({**self.leaf, 'bytes': self.leaf['bytes'] + 1})

    def test_modified_member_rejected_even_with_valid_outer_pack(self):
        self.compact()
        manifest = json.loads((self.packed / 'manifest.json').read_text())
        prefix = self.leaf['sha256'][:2]
        old = manifest['data_packs']['buckets'][prefix]
        value = json.loads(gzip.decompress((self.packed / old['url']).read_bytes()))
        value['entries'][self.leaf['sha256']] = base64.b64encode(b'wrong body').decode()
        manifest['data_packs']['buckets'][prefix] = write(self.packed, value)
        with self.assertRaisesRegex(ValueError, 'member checksum'):
            Storage(self.packed, manifest).read(self.leaf)

    def test_legacy_reader_and_unsafe_path(self):
        self.assertIn('본문', Storage(self.source).read(self.leaf)['text'])
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            Storage(self.source).read({**self.leaf, 'url': '../outside'})


if __name__ == '__main__':
    unittest.main()
