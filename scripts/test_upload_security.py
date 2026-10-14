"""Exercise hostile names through storage and shell-free document conversion."""
import json
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from core import document_text as dt
from core.upload_storage import save_upload


class UploadSecurityTests(unittest.TestCase):
    def upload(self, name='bill.pdf', data=b'%PDF-1.4'):
        return SimpleNamespace(name=name, getbuffer=lambda: data)

    def test_generated_names_preserve_data_and_separate_same_named_documents(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first = save_upload(self.upload('이름&명령%.pdf'), root)
            self.assertRegex(first.name, r'^[a-f0-9]{64}\.pdf$')
            self.assertEqual(first.read_bytes(), b'%PDF-1.4')
            self.assertEqual(first, save_upload(self.upload('other.pdf'), root))
            second = save_upload(self.upload('이름&명령%.pdf', b'other content'), root)
            self.assertNotEqual(first, second)
            self.assertEqual(first.read_bytes(), b'%PDF-1.4')

    def test_paths_stream_names_invalid_types_and_sizes_fail_before_writing(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ('../a.txt', '..\\a.txt', 'C:\\a.txt', '/a.txt', 'x.txt:stream', 'x\x00.pdf', 'x.exe'):
                with self.subTest(name=name), self.assertRaises(dt.ExtractError):
                    save_upload(self.upload(name), root)
            with patch('core.upload_storage.MAX_UPLOAD_BYTES', 3):
                for data in (b'', b'1234'):
                    with self.assertRaises(dt.ExtractError): save_upload(self.upload(data=data), root)
            self.assertEqual(list(root.iterdir()), [])

    def test_existing_content_is_verified_not_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); dest = save_upload(self.upload(), root)
            dest.write_bytes(b'corrupted')
            with self.assertRaises(dt.ExtractError): save_upload(self.upload(), root)
            self.assertEqual(dest.read_bytes(), b'corrupted')

    def test_real_subprocess_keeps_metacharacters_in_a_single_argument(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            pdf = root / 'sample&echo.AUDIT_MARKER&100%.pdf'; pdf.write_bytes(b'%PDF')
            stub = root / 'converter.py'
            stub.write_text('import sys,json\nfrom pathlib import Path\nPath(sys.argv[sys.argv.index("-o")+1]).write_text(json.dumps(sys.argv[1]),encoding="utf-8")\n')
            with patch.object(dt, '_converter_command', return_value=[sys.executable, str(stub)]):
                result = dt.pdf_to_markdown(pdf)
            self.assertEqual(json.loads(result.read_text()), str(pdf.resolve()))

    def test_timeout_and_failed_partial_conversion_preserve_existing_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            pdf = Path(folder)/'input.pdf'; pdf.write_bytes(b'%PDF')
            cache = pdf.with_suffix('.pdf.kordoc.md'); cache.write_text('prior result')
            command = [sys.executable, 'converter.py']
            with patch.object(dt, '_converter_command', return_value=command):
                with patch.object(dt.subprocess, 'run', side_effect=subprocess.TimeoutExpired(command, 180)) as run:
                    with self.assertRaises(dt.ExtractError): dt.pdf_to_markdown(pdf, force=True)
                    self.assertIs(run.call_args.kwargs['shell'], False)
                    self.assertEqual(run.call_args.kwargs['timeout'], 180)
                def failed(args, **kwargs):
                    Path(args[args.index('-o')+1]).write_text('partial output')
                    return SimpleNamespace(returncode=1)
                with patch.object(dt.subprocess, 'run', side_effect=failed):
                    with self.assertRaises(dt.ExtractError): dt.pdf_to_markdown(pdf, force=True)
            self.assertEqual(cache.read_text(), 'prior result')
            self.assertEqual(list(pdf.parent.glob('.pdf-convert-*')), [])

    def test_converter_requires_exact_installed_version_and_real_node(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); (root/'dist').mkdir(); (root/'dist/cli.js').write_text('')
            (root/'package.json').write_text(json.dumps({'version':'4.19.0'}))
            with patch.object(dt, '_KORDOC_DIR', root), patch.object(dt.shutil, 'which', return_value=sys.executable):
                self.assertEqual(len(dt._converter_command()), 2)
                (root/'package.json').write_text(json.dumps({'version':'9.0.0'}))
                self.assertIsNone(dt._converter_command())
            with patch.object(dt.shutil, 'which', return_value='node.cmd'):
                self.assertIsNone(dt._converter_command())

    def test_both_upload_interfaces_use_generated_paths(self):
        from ui import amendment_review_ui as ar, new_article_ui as na
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); upload=self.upload('friendly.pdf')
            text='법률 일부를 다음과 같이 개정한다. '+('본문 '*100)
            with patch.object(ar, '_UPLOAD_DIR', root), patch.object(na, '_UPLOAD_DIR', root), patch.object(dt, 'extract', return_value=text) as extract:
                result=ar._read_upload(upload)
                with patch.object(na, 'find_amendment_body', return_value=('법률',text)):
                    newer=na._ingest_upload(upload)
                self.assertEqual(result[1], 'friendly.pdf')
                self.assertEqual(newer['file'], 'friendly.pdf')
                for call in extract.call_args_list:
                    self.assertEqual(call.args[0].parent, root)
                    self.assertRegex(call.args[0].name, r'^[a-f0-9]{64}\.pdf$')

    def test_private_files_are_not_in_the_git_index(self):
        root=Path(__file__).resolve().parents[1]
        files=subprocess.check_output(['git','ls-files','-z'],cwd=root).decode('utf-8').split('\0')
        forbidden=[name for name in files if name and (
            name.startswith(('output/','data/uploads/','data/opinions/'))
            or name.endswith(('.hwpx','.hwp','.pem','.key'))
            or Path(name).name=='.env')]
        self.assertEqual(forbidden, [])


if __name__=='__main__': unittest.main()
