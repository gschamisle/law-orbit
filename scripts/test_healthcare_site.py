"""Portable checks for an additive medical-only public snapshot replacement."""
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.domain_navigation import DOMAINS
from scripts import build_healthcare_site as site
from scripts.build_static_galaxies import Writer, export_documents
from scripts.compact_static_galaxies import convert
from scripts.static_storage import Storage


def analysis(value):
    text = value + '\n'
    return dict(schema=1, status='explicit-citations-ready', text=text,
                text_sha256=hashlib.sha256(text.encode()).hexdigest(), file_sha256='fixture',
                units=[dict(id='u1', locator='문단 1', kind='paragraph', raw_text=value,
                            text=value, start=0, end=len(value))])


def fixture_document(number):
    document = dict(name=f'검증법 {number}', uid=str(number), category='medical', provider='eflaw',
                    kind='법률', effective='20260928', managing_authority='보건복지부',
                    source_url='https://www.law.go.kr/법령/검증법', sectors=['opening'],
                    articles=[dict(jo='1', title='검증', text=f'제1조(검증) 원문 {number}',
                                   effective='20260928', deleted=False, sectors=['opening'])], annexes=[])
    if number < 4:
        document['annexes'] = [dict(ref='별표 1', title=f'검증표 {number}', effective='20260928',
                                   urls=['https://www.law.go.kr/LSW/flDownload.do?flSeq=1'],
                                   body_analysis=analysis(f'별표 본문 {number}'))]
    return document


class HealthcareSiteTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.plain = self.root / 'plain'
        self.plain.mkdir()
        self.source = dict(domain='medical', laws=[fixture_document(i) for i in range(7)],
                           administrative_rules=[fixture_document(7)])
        self.graph = dict(domain='medical', built_at='2026-09-29', edges=[],
                          external_references=[], citation_issues=[], coverage_note='검증 범위')
        writer = Writer(self.plain)
        entries, _ = export_documents(writer, 'medical', '', site.documents(self.source), self.graph)
        self.catalog = dict(laws=entries, overview=writer.data(dict(galaxy_title='의료')),
                            sectors={'all': '전체 연결'}, built_at='2026-09-28')
        self.original = dict(schema=1, title='검증 사이트', version='original', domains=[])
        for domain, title in DOMAINS.items():
            catalog = self.catalog if domain == 'medical' else dict(
                nested=writer.data(dict(domain=domain, evidence='기존 공개 근거')))
            self.original['domains'].append(dict(id=domain, title=title,
                catalog=writer.data(catalog), laws=8 if domain == 'medical' else 0, built_at='2026-09-28'))
        self.original['cross_domain'] = {'tax': writer.data(dict(evidence='기존 분야간 근거'))}
        self.save_manifest(self.plain, self.original)
        (self.plain / 'introduction.html').write_text('old introduction', encoding='utf-8')
        self.base = self.root / 'packed'
        convert(self.plain, self.base, validate_site=False)
        self.original = json.loads((self.base / 'manifest.json').read_bytes())
        self.bundle = self.root / 'expanded.json'
        self.save_bundle(self.source)

    def save_manifest(self, folder, manifest):
        (folder / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')

    def save_bundle(self, source):
        self.bundle.write_text(json.dumps(dict(source=source, graph=self.graph), ensure_ascii=False), encoding='utf-8')

    def build_patches(self, stack, decision='limited-release'):
        # These tests isolate incremental publication from corpus acceptance and
        # the full fifteen-domain validator, each covered by their own suites.
        gate = stack.enter_context(patch.object(site, 'assessment', return_value={'decision': decision}))
        stack.enter_context(patch.object(site, 'validate_bundle', side_effect=lambda bundle, domain: bundle))
        validator = stack.enter_context(patch.object(site, 'validate', return_value={'passed': True}))
        stack.enter_context(patch.object(site, 'overview', return_value={'galaxy_title': '의료'}))
        stack.enter_context(patch.object(site, 'workbench', return_value={'cases': [{'title': '새 실무 질문'}]}))
        stack.enter_context(patch.object(site, 'report', return_value={'documents': 9}))
        stack.enter_context(patch.object(site, 'WORK_PROFILES', {'medical': {
            'sectors': {'all': '전체 연결', 'health': '보건'}, 'sector_aliases': {'opening': 'health'}}}))
        def current_shell(folder):
            (folder / 'introduction.html').write_text('reviewed introduction', encoding='utf-8')
        stack.enter_context(patch.object(site, 'shell', side_effect=current_shell))
        return gate, validator

    def test_additions_and_sector_retagging_preserve_original_editions(self):
        expanded = deepcopy(self.source)
        expanded['laws'].append(fixture_document(8))
        expanded['laws'][0]['articles'][0]['sectors'] = ['health']
        self.assertEqual(site.check_current_documents(self.base, self.catalog, expanded)['documents'], 8)

    def test_missing_or_duplicate_original_documents_fail(self):
        for change in ('missing', 'duplicate'):
            with self.subTest(change=change):
                changed = deepcopy(self.source)
                if change == 'missing':
                    changed['administrative_rules'] = []
                else:
                    changed['laws'].append(deepcopy(changed['laws'][0]))
                with self.assertRaisesRegex(ValueError, 'missing|Duplicate'):
                    site.check_current_documents(self.base, self.catalog, changed)

    def test_body_title_effective_deleted_or_article_membership_changes_fail(self):
        for field, value in (('text', '바뀐 본문'), ('title', '바뀐 표제'),
                             ('effective', '20260929'), ('deleted', True), ('jo', '2')):
            with self.subTest(field=field):
                changed = deepcopy(self.source)
                changed['laws'][0]['articles'][0][field] = value
                with self.assertRaisesRegex(ValueError, 'edition changed'):
                    site.check_current_documents(self.base, self.catalog, changed)
        changed = deepcopy(self.source)
        changed['laws'][0]['effective'] = '20260929'
        with self.assertRaisesRegex(ValueError, 'edition changed'):
            site.check_current_documents(self.base, self.catalog, changed)
        changed['laws'][0] = deepcopy(self.source['laws'][0])
        changed['laws'][0]['articles'] = []
        with self.assertRaisesRegex(ValueError, 'edition changed'):
            site.check_current_documents(self.base, self.catalog, changed)

    def test_missing_changed_or_reassigned_annex_evidence_fails(self):
        for change in ('missing', 'analysis', 'url', 'effective'):
            with self.subTest(change=change):
                changed = deepcopy(self.source)
                annex = changed['laws'][0]['annexes'][0]
                if change == 'missing':
                    changed['laws'][0]['annexes'] = []
                elif change == 'analysis':
                    annex['body_analysis']['units'][0]['locator'] = '다른 칸'
                elif change == 'url':
                    annex['urls'] = ['https://www.law.go.kr/LSW/flDownload.do?flSeq=2']
                else:
                    annex['effective'] = '20260929'
                with self.assertRaisesRegex(ValueError, 'annex (identity|analysis) changed'):
                    site.check_current_documents(self.base, self.catalog, changed)

    def test_outputs_cannot_overwrite_or_nest_in_inputs(self):
        for path in (self.base, self.base / 'new', self.root):
            with self.subTest(path=path), self.assertRaises(ValueError):
                site.output_paths(self.base, self.bundle, path)
        for suffix in ('', '-unpacked', '-report.json'):
            destination = self.root / ('occupied' + str(len(suffix)))
            protected = destination.with_name(destination.name + suffix)
            protected.write_bytes(b'keep')
            with self.assertRaisesRegex(ValueError, 'previous outputs'):
                site.output_paths(self.base, self.bundle, destination)
            self.assertEqual(protected.read_bytes(), b'keep')

    def test_hold_or_changed_source_fails_before_any_output_is_created(self):
        destination = self.root / 'rejected'
        with ExitStack() as stack:
            gate, _ = self.build_patches(stack, decision='hold')
            with self.assertRaisesRegex(ValueError, 'release gate'):
                site.build(self.base, self.bundle, destination)
            gate.return_value = {'decision': 'limited-release'}
            changed = deepcopy(self.source)
            changed['laws'][0]['articles'][0]['text'] = '바뀐 본문'
            self.save_bundle(changed)
            with self.assertRaisesRegex(ValueError, 'edition changed'):
                site.build(self.base, self.bundle, destination)
        self.assertFalse(destination.exists())
        self.assertFalse(destination.with_name(destination.name + '-unpacked').exists())

    def test_medical_only_replacement_preserves_packed_assets_and_current_intro(self):
        expanded = deepcopy(self.source)
        expanded['laws'].append(fixture_document(8))
        self.save_bundle(expanded)
        before = {p.relative_to(self.base): p.read_bytes() for p in self.base.rglob('*') if p.is_file()}
        bundle_raw = self.bundle.read_bytes()
        destination = self.root / 'expanded-site'
        with ExitStack() as stack:
            _, validator = self.build_patches(stack)
            result = site.build(self.base, self.bundle, destination)
            self.assertEqual([call.args[0] for call in validator.call_args_list], [self.base, destination])
        final = json.loads((destination / 'manifest.json').read_bytes())
        domain = next(d for d in final['domains'] if d['id'] == 'medical')
        catalog = Storage(destination, final).read(domain['catalog'])
        self.assertEqual((domain['title'], domain['laws']), ('보건의료', 9))
        self.assertEqual(catalog['sector_aliases'], {'opening': 'health'})
        self.assertEqual(Storage(destination, final).read(catalog['overview'])['galaxy_title'], '보건의료')
        self.assertEqual(len(result['untouched_domains']), 14)
        self.assertEqual(result['preserved_medical']['documents'], 8)
        self.assertEqual(len(result['preserved_medical']['annexes']), 4)
        self.assertEqual(result['added_documents'], 1)
        self.assertEqual(final['cross_domain'], self.original['cross_domain'])
        self.assertEqual((destination / 'introduction.html').read_text(), 'reviewed introduction')
        self.assertEqual(before, {p.relative_to(self.base): p.read_bytes() for p in self.base.rglob('*') if p.is_file()})
        self.assertEqual(bundle_raw, self.bundle.read_bytes())
        self.assertTrue(destination.with_name(destination.name + '-report.json').is_file())
        # Packing consumes only reachable members, so the replaced catalog is absent.
        storage = Storage(destination, final)
        old_medical = next(d for d in self.original['domains'] if d['id'] == 'medical')
        with self.assertRaises((ValueError, FileNotFoundError)):
            storage.raw(old_medical['catalog'])
        for change in ('other-domain', 'cross-domain', 'order'):
            changed = deepcopy(final)
            if change == 'other-domain':
                next(d for d in changed['domains'] if d['id'] != 'medical')['title'] = '변경'
            elif change == 'cross-domain':
                changed['cross_domain'] = {}
            else:
                changed['domains'].reverse()
            with self.subTest(change=change), self.assertRaises(ValueError):
                site.check_unchanged_domains(self.base, destination, self.original, changed)


if __name__ == '__main__':
    unittest.main()
