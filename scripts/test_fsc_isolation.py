"""Offline regressions for independent data, evidence, UI state and safe reuse."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.fsc_collection import atomic_json, collect_sources, CollectionError
from core.fsc_graph import build_fsc_graph
from core.fsc_universe import validate_bundle, load_bundle, article_for, external_evidence, present
from core.galaxy_focus import analyze_focus, build as focus, visible_rows
from core.law_galaxy import build as overview, render_html
from scripts.test_fsc_graph import source


def fixture():
    src = source()
    src['laws'] = [l for l in src['laws'] if l['category'] == 'fsc']
    for i, law in enumerate(src['laws']):
        law.update(provider='eflaw', body_status='indexed-statute-text', managing_authority='금융위원회',
                   kind='법률', fetched_at='20260916', source_url=f'https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq={i+1}')
    src['administrative_rules'] = []
    return dict(source=src, graph=build_fsc_graph(src))


class IsolationTests(unittest.TestCase):
    def test_fsc_graph_never_reads_tax_graph(self):
        data = fixture()
        with patch('core.law_galaxy.load_graph', side_effect=AssertionError('tax fallback')):
            mapped = overview(graph=data['graph'], include_external=False)
            result = analyze_focus('은행법', '제1조', data['graph'])
            spotlight = focus(result, mapped, external=False)
        self.assertEqual({n['id'] for n in mapped['nodes']}, {'은행법','보험업법'})
        self.assertTrue(visible_rows(result, 'forward', external=False))
        self.assertTrue(visible_rows(result, 'reverse', external=False))
        self.assertFalse(any(n.get('family') == '미수록법' for n in spotlight['nodes']))
        self.assertTrue(all(n['category'] == 'fsc' for n in mapped['nodes']))

    def test_uncollected_external_references_have_evidence_not_map_nodes(self):
        data = fixture()
        graph = data['graph']
        refs = external_evidence(graph, '은행법', '제1조제1항')
        self.assertTrue(refs)
        self.assertEqual({e['target_law'] for e in refs}, {'미수록법'})
        self.assertTrue(all(e['target_status']=='not-collected' and e['target_analysis']=='not-indexed' for e in refs))
        self.assertTrue(all(e['target_url'].startswith('https://www.law.go.kr/') for e in refs))
        self.assertFalse(external_evidence(graph, '은행법', '제1조제2항'))
        texts = {(l['name'], a['jo']):a['text'] for l in data['source']['laws'] for a in l['articles']}
        for edge in graph['edges'] + graph['external_references']:
            if edge['source_granularity'] == 'annex':
                continue
            self.assertEqual(texts[edge['source_law'],edge['source_jo']][edge['source_start']:edge['source_end']], edge['cite_raw'])

    def test_missing_and_mixed_data_are_rejected(self):
        data = fixture()
        validate_bundle(data)
        mixed = deepcopy(data)
        mixed['source']['laws'][0]['category'] = 'tax'
        with self.assertRaises(ValueError):
            validate_bundle(mixed)
        mixed = deepcopy(data)
        mixed['graph']['edges'][0]['target_law'] = '소득세법'
        with self.assertRaises(ValueError):
            validate_bundle(mixed)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):
                load_bundle(Path(directory) / 'missing.json')
        with self.assertRaises(ValueError):
            article_for(data, '은행법', '999')

    def test_domain_title_and_font_are_shared(self):
        html = render_html(present(overview(graph=fixture()['graph'])))
        self.assertIn('"galaxy_title": "금융"', html)
        self.assertIn("font-family:'MaruBuri'", html)
        self.assertIn("font-family:'Pretendard'", html)
        self.assertIn('data:font/woff2;base64,', html)
        self.assertIn('"domain": "fsc"', html)

    def test_cache_resume_checks_integrity_and_does_not_request_again(self):
        record = dict(name='은행법', provider='eflaw', edition_key='eflaw:1:2:20260101',
                      managing_authority='금융위원회', state='current-candidate')
        inventory = dict(as_of='20260916', layers={'eflaw':dict(list_status='complete', received=1, expected=1, records=[record])})
        body = {**record, 'fetched_at':'20260916', 'body_status':'indexed-statute-text'}
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)/'bodies'
            with patch('core.fsc_collection.collect_body', return_value=body) as collector:
                first = collect_sources(None, inventory, cache_dir=cache)
                second = collect_sources(None, inventory, cache_dir=cache)
                self.assertEqual(collector.call_count, 1)
                self.assertEqual(first, second)
            file = next(cache.glob('*.json'))
            saved = json.loads(file.read_text(encoding='utf-8'))
            saved['body']['name'] = '변조법'
            atomic_json(file, saved)
            with self.assertRaises(CollectionError):
                collect_sources(None, inventory, cache_dir=cache)


class UiTests(unittest.TestCase):
    def test_missing_fsc_data_does_not_load_tax_fallback(self):
        from streamlit.testing.v1 import AppTest
        from ui import fsc_map_ui
        with tempfile.TemporaryDirectory() as directory, patch.object(fsc_map_ui, 'BUNDLE', Path(directory)/'missing.json'):
            with patch('ui.fsc_map_ui._fsc_snapshot', side_effect=AssertionError('must not load')):
                app = AppTest.from_string('from ui.fsc_map_ui import render\nrender()').run()
            self.assertFalse(app.exception, str(app.exception))
            self.assertIn('금융위 데이터 미수집', [i.value for i in app.info])
            self.assertFalse(app.selectbox)

    def test_two_galaxies_preserve_separate_search_selection_and_filters(self):
        from streamlit.testing.v1 import AppTest
        from ui import fsc_map_ui
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory)/'bundle.json'
            atomic_json(bundle, fixture())
            with patch.object(fsc_map_ui, 'BUNDLE', bundle):
                app = AppTest.from_file('app.py', default_timeout=45).run()
                self.assertFalse(app.exception, str(app.exception))
                self.assertTrue(any(t.label == '금융' for t in app.tabs))
                self.assertTrue(app.get('file_uploader'))
                app.text_input(key='lm_focus_ref').set_value('16')
                app.button(key='lm_focus_run').click().run()
                app.radio(key='lm_focus_direction').set_value('reverse').run()
                app.selectbox(key='fsc_focus_law').set_value('은행법')
                app.text_input(key='fsc_focus_ref').set_value('1')
                app.button(key='fsc_focus_run').click().run()
                self.assertFalse(app.exception, str(app.exception))
                self.assertEqual(app.session_state['lm_focus_selection'], ('법인세법','제16조'))
                self.assertEqual(app.session_state['fsc_focus_selection'], ('은행법','제1조'))
                app.radio(key='fsc_direction').set_value('forward').run()
                self.assertEqual(app.radio(key='lm_focus_direction').value, 'reverse')
                self.assertEqual(app.text_input(key='lm_focus_ref').value, '16')
                app.button(key='fsc_focus_clear').click().run()
                self.assertNotIn('fsc_focus_selection', app.session_state)
                self.assertEqual(app.session_state['lm_focus_selection'], ('법인세법','제16조'))
                app.text_input(key='fsc_focus_ref').set_value('999')
                app.button(key='fsc_focus_run').click().run()
                self.assertTrue(app.error)
                self.assertNotIn('fsc_focus_selection', app.session_state)
                self.assertFalse(app.exception, str(app.exception))


if __name__ == '__main__':
    unittest.main()
