"""Citation direction, precision, and main-galaxy integration regressions."""
from __future__ import annotations

import unittest

from core.galaxy_focus import analyze_focus, build, visible_rows


def edge(a, jo, b, ref, raw=None):
    return dict(source_law=a, source_jo=jo, source_title='테스트 조문',
                target_law=b, target_ref=ref, cite_raw=raw or ref, type='direct')


def fixture():
    return dict(laws=['A법', 'B법', 'C법'], built_at='fixture', edges=[
        edge('A법', '2', 'B법', '제7조'),
        edge('A법', '2', 'B법', '제7조'),  # same evidence twice
        edge('A법', '2', 'A법', '제2조'),  # legacy header/self edge
        edge('B법', '7', 'A법', '제2조제2항'),  # reciprocal
        edge('C법', '9', 'A법', '제2조제2항', '제2조제2항부터 제4항까지'),
        edge('C법', '10', 'A법', '제2조제1항'),  # disjoint for paragraph 2
        edge('C법', '11', 'A법', '제2조', '제2조(제1항은 제외한다)'),
        edge('A법', '2의2', 'B법', '제8조'),
        edge('A법', '2', 'B법', '제17조', '제19조'),  # inconsistent stored target
        edge('A법', '2', 'B법', '별표1', '별표 1'),  # not silently lost
    ])


class FocusTests(unittest.TestCase):
    def test_both_directions_and_evidence(self):
        result = analyze_focus('A법', '2', fixture())
        self.assertEqual(result['reference'], '제2조')
        forward = visible_rows(result, 'forward')
        self.assertEqual(len(forward), 2)
        self.assertEqual(sum(r['target_ref'] == '제7조' for r in forward), 1)
        self.assertTrue(any(r['direction'] == 'reverse' for r in result['rows']))
        self.assertFalse(any(r['neighbor_law'] == 'A법' and r['neighbor_jo'] == '2' for r in result['rows']))
        self.assertEqual(len(result['unplaced']), 1)
        self.assertEqual(result['same_article_count'], 1)
        self.assertEqual(analyze_focus('A 법', '제2조', fixture()), result)

    def test_paragraph_range_and_source_precision(self):
        result = analyze_focus('A법', '제2조제3항', fixture())
        rows = visible_rows(result, include_review=False)
        self.assertFalse(any(r['direction'] == 'forward' for r in rows))
        self.assertEqual({r['neighbor_jo'] for r in rows}, {'9'})
        self.assertEqual(rows[0]['status'], 'range')
        self.assertTrue(all(r['status'] == 'review' for r in visible_rows(result, 'forward')))
        self.assertEqual(result['disjoint_count'], 2)
        self.assertTrue(any('출처가 조 단위' in r['reason'] for r in result['rows']))

    def test_branch_invalid_empty_and_no_mutation(self):
        self.assertEqual([r['target_ref'] for r in analyze_focus('A법', '2의2', fixture())['rows']], ['제8조'])
        self.assertEqual(analyze_focus('A법', '제999조', fixture())['rows'], [])
        for ref in ('', '0', '제2조제0항', '2-4', '제2조부터 제4조까지'):
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                analyze_focus('A법', ref, fixture())
        with self.assertRaises(ValueError):
            analyze_focus('다른법', '2', fixture())
        graph = fixture()
        analyze_focus('A법', '2', graph)
        self.assertEqual(graph, fixture())

    def test_graph_directions_background_and_filters(self):
        result = analyze_focus('A법', '2', fixture())
        context = {'nodes': [dict(id='context-law', color='#ffffff', x=0, y=0, z=0)], 'links': [], 'dust': []}
        data = build(result, context)
        self.assertEqual(data, build(result, context))
        self.assertNotIn('context_only', context['nodes'][0])
        self.assertTrue(data['nodes'][0]['context_only'])
        ids = {n['id'] for n in data['nodes']}
        for link in data['links']:
            self.assertIn(link['a'], ids)
            self.assertIn(link['b'], ids)
            self.assertEqual(link['a'] if link['direction'] == 'forward' else link['b'], data['focus'])
            self.assertNotEqual(link['a'], link['b'])
        self.assertEqual(sum(l['n'] for l in data['links']), len(result['rows']))
        neighbor = next(n for n in data['nodes'] if n['id'] == 'article:B법|7')
        self.assertEqual(len(neighbor['evidence']), 2)
        for direction in ('forward', 'reverse'):
            filtered = build(result, context, direction, include_review=False)
            self.assertTrue(all(l['direction'] == direction and not l['dashed'] for l in filtered['links']))
            self.assertEqual(sum(l['n'] for l in filtered['links']), len(visible_rows(result, direction, False)))
        with self.assertRaises(ValueError):
            visible_rows(result, 'invalid')

    def test_real_corporate_16(self):
        result = analyze_focus('법인세법', '16')
        self.assertTrue({'44', '46', '459'} <= {r['neighbor_jo'] for r in visible_rows(result, 'forward')})
        self.assertTrue(visible_rows(result, 'reverse'))
        from core.law_galaxy import build as overview
        # Overview's line threshold must never suppress a provision-level connection.
        data = build(result, overview(min_edge=60, max_articles_per_law=40))
        self.assertEqual(sum(l['n'] for l in data['links']), len(result['rows']))

    def test_main_galaxy_form_clear_and_invalid(self):
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_file('app.py', default_timeout=30).run()
        self.assertFalse(app.exception, str(app.exception))
        self.assertTrue(app.get('file_uploader'))
        self.assertNotIn('입법예고', ' '.join(t.label for t in app.tabs))
        self.assertEqual(len(app.metric), 0)
        app.text_input(key='lm_focus_ref').set_value('16')
        app.button(key='lm_focus_run').click().run()
        self.assertFalse(app.exception, str(app.exception))
        self.assertEqual(app.session_state['lm_focus_selection'], ('법인세법', '제16조'))
        self.assertEqual(len(app.metric), 3)
        app.radio(key='lm_focus_direction').set_value('forward').run()
        expected = build(analyze_focus('법인세법','16'), dict(nodes=[],dust=[]), 'forward')
        self.assertEqual([str(m.value) for m in app.metric], [str(expected['neighbor_count']), str(expected['evidence_count']), '0'])
        app.text_input(key='lm_focus_ref').set_value('제16조제2항제1호')
        app.button(key='lm_focus_run').click().run()
        app.checkbox(key='lm_focus_review').uncheck().run()
        self.assertEqual([str(m.value) for m in app.metric], ['0', '0', '0'])
        app.button(key='lm_focus_clear').click().run()
        self.assertEqual(len(app.metric), 0)
        app.text_input(key='lm_focus_ref').set_value('16')
        app.button(key='lm_focus_run').click().run()
        app.text_input(key='lm_focus_ref').set_value('잘못된 번호')
        app.button(key='lm_focus_run').click().run()
        self.assertTrue(app.error)
        self.assertEqual(len(app.metric), 0)
        self.assertNotIn('lm_focus_selection', app.session_state)
        self.assertTrue(app.get('file_uploader'))
        self.assertFalse(app.exception, str(app.exception))


if __name__ == '__main__':
    unittest.main()
