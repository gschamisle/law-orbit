"""Byte-preserving incremental candidate builds, isolated from corpus acceptance."""
import argparse
from contextlib import ExitStack
from copy import deepcopy
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.domain_navigation import DOMAINS
from scripts import build_candidate_site as site
from scripts.build_static_galaxies import Writer
from scripts.compact_static_galaxies import convert
from scripts.static_storage import Storage


class CandidateSiteTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        plain = self.root / 'plain'
        plain.mkdir()
        writer = Writer(plain)
        self.original = dict(schema=1, title='검증 사이트', version='previous', domains=[],
                             site_notes=['기존 공개 범위'])
        for domain, title in DOMAINS.items():
            if domain in site.CANDIDATES:
                continue
            nested = writer.data(dict(domain=domain, evidence='기존 원문과 인용'))
            catalog = writer.data(dict(laws=[], nested=nested))
            self.original['domains'].append(dict(id=domain, title=title, laws=0,
                                                 catalog=catalog, built_at='20261004'))
        self.original['cross_domain'] = dict(tax=writer.data(dict(evidence='기존 분야 간 연결')))
        (plain / 'manifest.json').write_text(json.dumps(self.original, ensure_ascii=False), encoding='utf-8')
        (plain / 'index.html').write_text('old shell', encoding='utf-8')
        self.base = self.root / 'packed'
        convert(plain, self.base, validate_site=False)
        self.original = site.read(self.base / 'manifest.json')
        self.paths = {}
        for domain in site.CANDIDATES:
            path = self.root / (domain + '.json')
            path.write_text(json.dumps(self.fixture_bundle(domain), ensure_ascii=False), encoding='utf-8')
            self.paths[domain] = path

    @staticmethod
    def fixture_bundle(domain):
        name = domain + ' 검증법'
        doc = dict(name=name, uid='fixture:' + domain, provider='eflaw', category=domain,
                   kind='법률', effective='20261004', managing_authority='검증기관',
                   source_url='https://www.law.go.kr/법령/검증법', sectors=['topic'], annexes=[],
                   articles=[dict(jo='1', title='검증', text='제1조(검증) 공개 원문.',
                                  blocks=[], effective='20261004', sectors=['topic'])])
        return dict(source=dict(domain=domain, laws=[doc], administrative_rules=[]),
                    graph=dict(domain=domain, built_at='20261004', edges=[],
                               external_references=[], citation_issues=[], coverage_note='검증 범위'))

    @staticmethod
    def metrics(folder):
        files = [path for path in folder.rglob('*') if path.is_file()]
        return dict(site_files=len(files), site_bytes=sum(path.stat().st_size for path in files), passed=True)

    def patches(self, stack, decision='limited-release'):
        # Corpus acceptance, full-domain semantics and visual layout have their
        # own tests. This suite exercises actual export, storage and packing.
        gate = stack.enter_context(patch.object(site, 'assessment', return_value={'decision': decision}))
        stack.enter_context(patch.object(site, 'load_bundle', side_effect=lambda domain, path: site.read(path)))
        validator = stack.enter_context(patch.object(site, 'validate', side_effect=self.metrics))
        stack.enter_context(patch.object(site, 'overview', return_value={'galaxy_title': '검증'}))
        graph = stack.enter_context(patch.object(site, 'overview_graph', side_effect=lambda bundle: bundle['graph']))
        stack.enter_context(patch.object(site, 'workbench', return_value={'cases': [{'title': '새 업무 질문'}]}))
        stack.enter_context(patch.object(site, 'report', return_value={'documents': 1}))
        profiles = {domain: dict(title=domain, sectors={'all': '전체 연결', 'topic': '검증'},
                    default_laws={'all': domain + ' 검증법'}, default_refs={'all': '제1조'},
                    sector_aliases={'old': 'topic'}) for domain in site.CANDIDATES}
        stack.enter_context(patch.object(site, 'WORK_PROFILES', profiles))
        stack.enter_context(patch.dict(DOMAINS, {domain: domain for domain in site.CANDIDATES}))
        def updated_shell(folder):
            (folder / 'index.html').write_text('reviewed shell', encoding='utf-8')
        stack.enter_context(patch.object(site, 'shell', side_effect=updated_shell))
        return gate, validator, graph

    def test_cli_requires_supported_explicit_pairs(self):
        self.assertEqual(site.bundle_argument('privacy=C:/bundle=a.json'),
                         ('privacy', Path('C:/bundle=a.json')))
        for value in ('tax=path', 'privacy=', 'privacy', '=path'):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                site.bundle_argument(value)
        for values in ([], [('tax', self.paths['privacy'])],
                       [('privacy', self.paths['privacy']), ('privacy', self.paths['privacy'])]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                site.normalized_bundles(values)

    def test_no_overwrite_or_nested_inputs(self):
        values = [('privacy', self.paths['privacy'])]
        for dest in (self.base, self.base / 'inside', self.root, self.paths['privacy']):
            with self.subTest(dest=dest), self.assertRaises(ValueError):
                site.output_paths(self.base, values, dest)
        for suffix in ('', '-unpacked', '-report.json'):
            dest = self.root / ('occupied' + str(len(suffix)))
            protected = dest.with_name(dest.name + suffix)
            protected.write_bytes(b'preserve existing preview')
            with self.assertRaisesRegex(ValueError, 'previous outputs'):
                site.output_paths(self.base, values, dest)
            self.assertEqual(protected.read_bytes(), b'preserve existing preview')

    def test_hold_rejected_before_output_creation(self):
        dest = self.root / 'hold'
        with ExitStack() as stack:
            self.patches(stack, decision='hold')
            with self.assertRaisesRegex(ValueError, 'release gate'):
                site.build(self.base, dest, [('privacy', self.paths['privacy'])])
        self.assertFalse(dest.exists())
        self.assertFalse(dest.with_name(dest.name + '-unpacked').exists())

    def test_all_candidates_preserve_old_logical_bytes_and_use_current_shell(self):
        before = {p.relative_to(self.base): p.read_bytes() for p in self.base.rglob('*') if p.is_file()}
        bundles_before = {key: path.read_bytes() for key, path in self.paths.items()}
        dest = self.root / 'preview'
        with ExitStack() as stack:
            _, validator, overview_graph = self.patches(stack)
            result = site.build(self.base, dest, list(self.paths.items()))
            self.assertEqual([call.args[0] for call in validator.call_args_list], [self.base, dest])
            self.assertEqual(overview_graph.call_count, 3)
        final = site.read(dest / 'manifest.json')
        self.assertEqual(len(final['domains']), len(self.original['domains']) + 3)
        self.assertEqual(final['cross_domain'], self.original['cross_domain'])
        self.assertEqual(result['added_domains'], list(site.CANDIDATES))
        self.assertEqual(result['original_logical_assets_unchanged'], len(self.original['domains']) * 2 + 1)
        self.assertTrue(result['source_bundles_unchanged'])
        self.assertEqual((dest / 'index.html').read_text(), 'reviewed shell')
        self.assertTrue(dest.with_name(dest.name + '-report.json').is_file())
        self.assertTrue(final['data_packs']['buckets'])
        storage = Storage(dest, final)
        for domain in site.CANDIDATES:
            entry = next(d for d in final['domains'] if d['id'] == domain)
            catalog = storage.read(entry['catalog'])
            self.assertEqual(catalog['default_laws'], {'all': domain + ' 검증법'})
            self.assertEqual(catalog['default_refs'], {'all': '제1조'})
            self.assertEqual(catalog['sector_aliases'], {'old': 'topic'})
            self.assertEqual(catalog['text_summary'], {'documents': 0, 'citations': 0, 'issues': 0})
            document = storage.read(catalog['laws'][0]['file'])
            self.assertEqual(document['articles'][0]['text'], '제1조(검증) 공개 원문.')
        self.assertEqual(before, {p.relative_to(self.base): p.read_bytes() for p in self.base.rglob('*') if p.is_file()})
        self.assertEqual(bundles_before, {key: path.read_bytes() for key, path in self.paths.items()})

    def test_existing_domain_rejected_before_output_creation(self):
        final = deepcopy(self.original)
        final['domains'].append(dict(id='privacy', title='privacy', laws=0, catalog=final['domains'][0]['catalog']))
        (self.base / 'manifest.json').write_text(json.dumps(final), encoding='utf-8')
        dest = self.root / 'rejected-existing'
        with self.assertRaisesRegex(ValueError, 'already present'):
            site.build(self.base, dest, [('privacy', self.paths['privacy'])])
        self.assertFalse(dest.exists())

    def test_metadata_cross_links_order_and_corrupt_legacy_assets_fail(self):
        dest = self.root / 'single-preview'
        with ExitStack() as stack:
            self.patches(stack)
            site.build(self.base, dest, [('privacy', self.paths['privacy'])])
            final = site.read(dest / 'manifest.json')
            for change in ('metadata', 'cross', 'order', 'extra-meta', 'duplicate'):
                changed = deepcopy(final)
                if change == 'metadata':
                    changed['domains'][0]['title'] = 'changed'
                elif change == 'cross':
                    changed['cross_domain'] = {}
                elif change == 'order':
                    changed['domains'].reverse()
                elif change == 'extra-meta':
                    changed['site_notes'] = ['changed']
                else:
                    changed['domains'].append(deepcopy(changed['domains'][0]))
                with self.subTest(change=change), self.assertRaises(ValueError):
                    site.check_preserved(self.base, dest, self.original, changed)
            pack = next(iter(final['data_packs']['buckets'].values()))
            (dest / pack['url']).write_bytes(gzip.compress(b'{}'))
            with self.assertRaises(ValueError):
                site.check_preserved(self.base, dest, self.original, final)


if __name__ == '__main__':
    unittest.main()
