"""Real collected-corpus screen checks; no network calls."""
import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
from core.procurement_collection import NATIONAL


@unittest.skipUnless(all((Path(__file__).resolve().parents[1]/p).is_file() for p in ['output/procurement-universe/bundle.json', 'output/fsc-universe/bundle.json', 'output/local-tax-universe/current.json']), "Collected snapshots are not in Git; collect them locally to run real-corpus integration tests")
class ProcurementUI(unittest.TestCase):
    def test_real_citation_search_sector_and_other_domains_are_isolated(self):
        app=AppTest.from_file('app.py',default_timeout=60).run()
        self.assertFalse(app.exception,str(app.exception))
        uploader=app.get('file_uploader')[0].proto.id
        self.assertEqual(app.radio(key='pc_sector').value,'national')
        app.text_input(key='lm_library_query').set_value('배당금').run()
        app.text_input(key='local_tax_central_library_query').set_value('시가표준액').run()
        app.text_input(key='fsc_focus_ref').set_value('제2조').run()
        app.text_input(key='pc_national_library_query').set_value('부정당').run()
        app.text_input(key='pc_national_ref').set_value('제27조')
        app.button(key='pc_national_run').click().run()
        self.assertEqual(app.session_state['pc_national_selection'],(NATIONAL,'제27조'))
        self.assertTrue(any('역인용 110건' in c.value for c in app.caption))
        app.radio(key='pc_sector').set_value('procurement').run()
        app.text_input(key='pc_procurement_library_query').set_value('계약').run()
        app.radio(key='pc_sector').set_value('national').run()
        self.assertEqual(app.text_input(key='pc_national_library_query').value,'부정당')
        self.assertEqual(app.session_state['pc_national_selection'],(NATIONAL,'제27조'))
        self.assertEqual(app.text_input(key='lm_library_query').value,'배당금')
        self.assertEqual(app.text_input(key='local_tax_central_library_query').value,'시가표준액')
        self.assertEqual(app.text_input(key='fsc_focus_ref').value,'제2조')
        app.radio(key='app_section').set_value('review').run()
        self.assertEqual(app.get('file_uploader')[0].proto.id,uploader)
        app.radio(key='app_section').set_value('galaxy').run()
        self.assertEqual(app.session_state['pc_national_selection'],(NATIONAL,'제27조'))
        self.assertFalse(app.exception,str(app.exception))

    def test_rule_source_library_and_local_unindexed_notice(self):
        app=AppTest.from_file('app.py',default_timeout=60).run()
        rule='(계약예규)정부 입찰ㆍ계약 집행기준'
        app.selectbox(key='pc_national_law').set_value(rule).run()
        app.text_input(key='pc_national_ref').set_value('제94조')
        app.button(key='pc_national_run').click().run()
        self.assertEqual(app.session_state['pc_national_selection'],(rule,'제94조'))
        self.assertTrue(any('역인용 4건' in c.value for c in app.caption))
        self.assertTrue(any('보험료' in t.value for t in app.text))
        app.radio(key='pc_sector').set_value('local').run()
        target='지방자치단체 입찰 및 계약 집행기준'
        app.selectbox(key='pc_local_raw_name').set_value(target).run()
        self.assertTrue(any('API 본문 미제공' in c.value for c in app.caption))
        self.assertNotIn(target,app.selectbox(key='pc_local_law').options)
        self.assertFalse(app.exception,str(app.exception))


if __name__=='__main__':unittest.main()
