"""Deployment safety checks with small fixtures; no network or credentials needed."""
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from scripts.galaxy_snapshot import BUNDLES, MANIFEST, allowed, bootstrap, complete, digest, restore
from scripts.run_public_server import command


def fixture_archive(folder, change=None):
    version = "20260919-010101"
    prefix = "local-tax-universe/versions/" + version + "/"
    files = {name: b'{}' for name in BUNDLES}
    files["local-tax-universe/current.json"] = json.dumps(dict(domain="local_tax", version=version)).encode()
    files[prefix + "manifest.json"] = json.dumps(dict(domain="local_tax", version=version, regions=[], reverse_targets=[])).encode()
    files[prefix + "central.json"] = b'{}'
    if change:
        change(files)
    manifest = dict(schema=1, files={name:dict(bytes=len(blob), sha256=sha256(blob).hexdigest()) for name,blob in files.items()})
    path = folder / "test.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        for name, blob in {MANIFEST:json.dumps(manifest).encode(), **files}.items():
            member = tarfile.TarInfo(name); member.size = len(blob)
            archive.addfile(member, io.BytesIO(blob))
    return path


class SnapshotTests(unittest.TestCase):
    def test_restore_and_restart_preserve_newer_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); archive=fixture_archive(root); output=root/'output'
            restore(archive,output,digest(archive))
            self.assertTrue(complete(output))
            (output/BUNDLES[0]).write_text('{"newer": true}')
            bootstrap(output,'','')
            self.assertEqual(json.loads((output/BUNDLES[0]).read_text()),dict(newer=True))

    def test_checksum_rejection_does_not_write_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); archive=fixture_archive(root); output=root/'output'
            with self.assertRaisesRegex(ValueError,'checksum'):
                restore(archive,output,'0'*64)
            self.assertFalse(output.exists())

    def test_traversal_and_unrelated_files_are_rejected(self):
        for name in ('../outside.json','data/uploads/bill.json','.env','tax-universe/report.json',
                     'local-tax-universe/versions/20260919-010101/../secret.json'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); archive=fixture_archive(root,lambda files:files.update({name:b'{}'}))
                with self.assertRaisesRegex(ValueError,'Unexpected archive member'):
                    restore(archive,root/'output',digest(archive))
                self.assertFalse((root/'outside.json').exists())

    def test_missing_active_corpus_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); archive=fixture_archive(root,lambda files:files.pop(BUNDLES[0]))
            with self.assertRaisesRegex(ValueError,'Missing or unsafe'):
                restore(archive,root/'output',digest(archive))
            self.assertFalse((root/'output'/BUNDLES[1]).exists())

    def test_partial_corpus_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); archive=fixture_archive(root); output=root/'output'
            old=output/BUNDLES[0]; old.parent.mkdir(parents=True); old.write_text('keep')
            with self.assertRaisesRegex(ValueError,'Partial existing corpus'):
                restore(archive,output,digest(archive))
            self.assertEqual(old.read_text(),'keep')

    def test_only_public_release_downloads_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            for url in ('http://github.com/gschamisle/tax-amendment-assistant/releases/download/a/b',
                        'https://example.com/data.tar.gz',
                        'https://secret@github.com/gschamisle/tax-amendment-assistant/releases/download/a/b',
                        'https://github.com/gschamisle/tax-amendment-assistant/releases/download/a/b?token=secret'):
                with self.assertRaisesRegex(ValueError,'public GitHub release'):
                    bootstrap(Path(tmp),url,'0'*64)

    def test_archive_links_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); original=fixture_archive(root); linked=root/'linked.tar.gz'
            with tarfile.open(original,'r:gz') as source, tarfile.open(linked,'w:gz') as dest:
                for member in source.getmembers():
                    if member.name==BUNDLES[0]:
                        member.type=tarfile.SYMTYPE; member.linkname='/etc/passwd'; member.size=0
                        dest.addfile(member)
                    else:dest.addfile(member,source.extractfile(member))
            with self.assertRaisesRegex(ValueError,'Unexpected archive member'):
                restore(linked,root/'output',digest(linked))

    def test_internal_file_hash_is_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); original=fixture_archive(root); changed=root/'changed.tar.gz'
            with tarfile.open(original,'r:gz') as source, tarfile.open(changed,'w:gz') as dest:
                for member in source.getmembers():
                    blob=source.extractfile(member).read()
                    if member.name==BUNDLES[0]:blob=b'[]'
                    dest.addfile(member,io.BytesIO(blob))
            with self.assertRaisesRegex(ValueError,'file checksum'):
                restore(changed,root/'output',digest(changed))

    def test_bound_port_and_static_serving(self):
        argv=command('10000')
        self.assertIn('--server.port=10000',argv)
        self.assertIn('--server.address=0.0.0.0',argv)
        self.assertIn('--server.enableStaticServing=false',argv)
        for port in ('0','65536','bad','10000; echo nope'):
            with self.assertRaises(ValueError):command(port)


class PublicScreenTests(unittest.TestCase):
    def test_public_mode_does_not_mount_uploads_even_with_optional_flags(self):
        from streamlit.testing.v1 import AppTest
        with patch('config.PUBLIC_GALAXY_ONLY',True), patch('config.ENABLE_WIP_TABS',True), \
             patch('config.ENABLE_DRAFT_TAB',True), patch('config.ENABLE_HWPX_OUTPUT',True):
            app=AppTest.from_file('app.py',default_timeout=90).run()
        self.assertFalse(app.exception,str(app.exception))
        self.assertEqual(app.radio(key='app_section').options,['법령은하'])
        self.assertEqual(len(app.get('file_uploader')),0)
        self.assertEqual([t.label for t in app.tabs],['국세','조달계약','금융','지방세','국토건축주택','환경화학안전'])
        self.assertFalse(any(b.key=='check_freshness' for b in app.button))


if __name__=='__main__':unittest.main()
