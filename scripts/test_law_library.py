"""Stored-body browsing and handoff regressions, without API requests."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.law_library import article_label, matching_articles, provision_choices, official_url


class LibraryTests(unittest.TestCase):
    def test_search_keeps_original_numbering_and_text(self):
        document = dict(name='검증법', articles=[
            dict(jo='2', title='목적', text='제2조(목적) 본문.'),
            dict(jo='2의2', title='배당', text='제2조의2(배당) 이익을 분배한다.'),
            dict(jo='2-9의2', title='감독', text='제2-9조의2(감독) 감독기준을 정한다.'),
        ])
        original = deepcopy(document)
        self.assertEqual([a['jo'] for a in matching_articles(document,'분배')],['2의2'])
        self.assertEqual([a['jo'] for a in matching_articles(document,'배당 이익')],['2의2'])
        self.assertEqual([a['jo'] for a in matching_articles(document,'제2-9조의2')],['2-9의2'])
        self.assertFalse(matching_articles(document,'없는 검색어'))
        self.assertEqual(document, original)

    def test_scopes_are_actual_blocks_and_official_edition_is_preserved(self):
        article = dict(jo='2-9의2',title='감독',blocks=[
            dict(ref='제2-9조의2제1항'),dict(ref='제2-9조의2제1항제2호'),
            dict(ref='제2-9조의2제1항'),dict(ref='제3조제1항'),dict(ref='잘못된 번호')])
        self.assertEqual(provision_choices(article),['제2-9조의2','제2-9조의2제1항','제2-9조의2제1항제2호'])
        self.assertEqual(article_label(article),'제2-9조의2 · 감독')
        self.assertEqual(official_url(dict(mst='123',effective='20260101')),
                         'https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=123&efYd=20260101')
        self.assertEqual(official_url(dict(source_url='https://www.law.go.kr/example')),'https://www.law.go.kr/example')
        self.assertEqual(official_url({}),'')

    def test_missing_body_never_offers_substitute(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_string("from ui.law_library_ui import render\nrender(None,prefix='empty_')").run()
        self.assertFalse(app.exception,str(app.exception))
        self.assertEqual([i.value for i in app.info],['이 법령의 수집 본문이 없습니다.'])
        self.assertFalse(app.selectbox)

    def test_tax_reader_search_scope_and_direct_handoff(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_string('from ui.law_map_ui import render\nrender()',default_timeout=45).run()
        self.assertFalse(app.exception,str(app.exception))
        app.text_input(key='lm_library_query').set_value('배당금').run()
        app.selectbox(key='lm_library_article').set_value('16').run()
        self.assertTrue(any('배당금 또는 분배금의 의제' in t.value for t in app.text))
        app.selectbox(key='lm_library_scope').set_value('제16조제2항제1호').run()
        app.button(key='lm_library_use').click().run()
        self.assertFalse(app.exception,str(app.exception))
        self.assertEqual(app.text_input(key='lm_focus_ref').value,'제16조제2항제1호')
        self.assertEqual(app.session_state['lm_focus_selection'],('법인세법','제16조제2항제1호'))
        app.text_input(key='lm_library_query').set_value('절대없는검색어987654').run()
        self.assertFalse(any(s.key=='lm_library_article' for s in app.selectbox))
        self.assertTrue(any('일치하는 수집 조문이 없습니다' in i.value for i in app.info))
        app.selectbox(key='lm_focus_law').set_value('민법').run()
        self.assertFalse(app.exception,str(app.exception))
        self.assertEqual(app.text_input(key='lm_library_query').value,'')
        self.assertNotIn('lm_focus_selection',app.session_state)

    def test_financial_rules_handoff_and_separate_sector_reader_state(self):
        from streamlit.testing.v1 import AppTest
        from scripts.test_fsc_sectors import sector_fixture
        from ui import fsc_map_ui
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'bundle.json'
            p.write_text(json.dumps(sector_fixture(),ensure_ascii=False),encoding='utf-8')
            with patch.object(fsc_map_ui,'BUNDLE',p):
                app=AppTest.from_file('app.py',default_timeout=45).run()
                app.text_input(key='lm_library_query').set_value('배당금').run()
                app.radio(key='fsc_sector').set_value('insurance').run()
                app.selectbox(key='fsc_insurance_focus_law').set_value('보험업감독규정').run()
                app.text_input(key='fsc_insurance_library_query').set_value('제1-2조').run()
                app.selectbox(key='fsc_insurance_library_article').set_value('1-2').run()
                app.button(key='fsc_insurance_library_use').click().run()
                self.assertFalse(app.exception,str(app.exception))
                self.assertEqual(app.session_state['fsc_insurance_focus_selection'],('보험업감독규정','제1-2조'))
                self.assertEqual(app.text_input(key='fsc_insurance_focus_ref').value,'제1-2조')
                app.radio(key='fsc_sector').set_value('banking').run()
                self.assertEqual(app.text_input(key='fsc_banking_library_query').value,'')
                app.radio(key='fsc_sector').set_value('insurance').run()
                self.assertFalse(app.exception,str(app.exception))
                self.assertEqual(app.text_input(key='fsc_insurance_library_query').value,'제1-2조')
                self.assertEqual(app.selectbox(key='fsc_insurance_library_article').value,'1-2')
                self.assertEqual(app.text_input(key='lm_library_query').value,'배당금')
                app.selectbox(key='fsc_insurance_focus_law').set_value('보험업감독업무시행세칙').run()
                self.assertEqual(app.text_input(key='fsc_insurance_library_query').value,'')
                app.selectbox(key='fsc_insurance_library_article').set_value('1-2').run()
                app.button(key='fsc_insurance_library_use').click().run()
                self.assertFalse(app.exception,str(app.exception))
                self.assertEqual(app.session_state['fsc_insurance_focus_selection'],('보험업감독업무시행세칙','제1-2조'))


if __name__=='__main__': unittest.main()
