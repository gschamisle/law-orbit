"""Renderer data integrity and integration through Streamlit's app test harness."""
from __future__ import annotations

import unittest

from core.impact_explorer import analyze
from core.impact_galaxy import build
from core.law_galaxy import build as overview, render_page


class GalaxyTests(unittest.TestCase):
    def test_evidence_graph(self):
        result = analyze('법인세법', '제16조제2항제1호')
        galaxy = build(result)
        self.assertTrue(galaxy['links'])
        ids = {n['id'] for n in galaxy['nodes']}
        self.assertTrue(all(l['a'] in ids and l['b'] in ids for l in galaxy['links']))
        count = sum(len(n['evidence']) for n in galaxy['nodes'])
        expected = sum(r['status'] != 'disjoint' and not r['same_article'] for r in result['rows'])
        self.assertEqual(count, expected)
        self.assertEqual(build(result), galaxy)

    def test_render_and_all_links(self):
        data = overview()
        self.assertGreater(len(data['all_links']), len(data['links']))
        self.assertTrue(any('시행령' in l['a'] and l['a'].startswith(l['b']) for l in data['all_links']))
        data['nodes'][0]['title'] = '</script><img src=x onerror=alert(1)>'
        html = render_page(data)
        self.assertNotIn('</script><img', html)
        self.assertIn('\\u003c/script', html)
        self.assertNotIn('__DATA__', html)
        self.assertNotIn('src="https://', html)

    def test_new_view_and_upload_flow(self):
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_file('app.py', default_timeout=30).run()
        self.assertFalse(app.exception, str(app.exception))
        labels = ' '.join(t.label for t in app.tabs)
        self.assertEqual(app.radio(key='app_section').options[:2], ['법령은하', '개정안 검토'])
        self.assertIn('세법', labels)
        self.assertNotIn('입법예고 의견', labels)
        self.assertFalse(any((t.key or '').startswith('op_') for t in app.text_input))
        self.assertTrue(app.get('file_uploader'))

        view = next(r for r in app.radio if r.key == 'lm_view')
        view.set_value('조문 영향 탐색').run()
        self.assertFalse(app.exception, str(app.exception))
        self.assertEqual(len(app.metric), 5)
        self.assertTrue(app.get('file_uploader'))

    def test_boundary_example_real_form_and_stale_result(self):
        from streamlit.testing.v1 import AppTest
        from scripts.test_boundary_review import article
        app = AppTest.from_file('app.py', default_timeout=30).run()
        next(r for r in app.radio if r.key == 'lm_view').set_value('조문 영향 탐색').run()
        app.radio(key='impact_mode').set_value('신설 항 범위 재검토').run()
        app.button(key='boundary_demo').click().run()
        self.assertFalse(app.exception, str(app.exception))
        self.assertEqual([str(m.value) for m in app.metric], ['2', '1', '1', '1'])
        self.assertTrue(app.session_state['boundary_result']['example'])
        app.text_input(key='boundary_reference').set_value('제16조')
        app.text_area(key='boundary_before').set_value(article(4, '제16조'))
        app.text_area(key='boundary_after').set_value(article(5, '제16조'))
        app.button(key='boundary_run').click().run()
        self.assertFalse(app.exception, str(app.exception))
        self.assertFalse(app.session_state['boundary_result']['example'])
        self.assertEqual(app.session_state['boundary_result']['change']['added'], [5])
        app.text_area(key='boundary_before').set_value('')
        app.button(key='boundary_run').click().run()
        self.assertFalse(app.exception, str(app.exception))
        self.assertTrue(app.error)
        self.assertEqual(len(app.metric), 0)
        self.assertTrue(app.get('file_uploader'))



if __name__ == '__main__':
    unittest.main()
