"""Local labor navigation and missing-corpus behavior."""
import unittest
from streamlit.testing.v1 import AppTest
from core.labor_universe import BUNDLE
from core.labor_profile import FIXED

class LaborUI(unittest.TestCase):
    def test_missing_corpus_does_not_load_another_domain(self):
        app=AppTest.from_string("from ui.sector_map_ui import render\nrender(dict(domain='labor',prefix='missing_labor',title='고용·노동'), 'output/does-not-exist/bundle.json')").run()
        self.assertFalse(app.exception,str(app.exception))
        self.assertTrue(any('고용·노동 데이터 미수집' in i.value for i in app.info))
        self.assertEqual(len(app.selectbox),0)

    @unittest.skipUnless(BUNDLE.is_file(),'Requires locally collected labor snapshot')
    def test_case_and_topic_navigation(self):
        app=AppTest.from_string("from ui.mofe_map_ui import render\nrender('labor')",default_timeout=60).run()
        self.assertFalse(app.exception,str(app.exception))
        app.button(key='mofe_labor_case_'+FIXED+'_4').click().run()
        self.assertEqual(app.session_state['mofe_labor_all_selection'],(FIXED,'제4조'))
        app.radio(key='mofe_labor_sector').set_value('remedy').run()
        app.button(key='mofe_labor_case_근로기준법_60').click().run()
        self.assertEqual(app.radio(key='mofe_labor_sector').value,'all')
        self.assertEqual(app.session_state['mofe_labor_all_selection'],('근로기준법','제60조'))
        self.assertFalse(app.exception,str(app.exception))

if __name__=='__main__':unittest.main()
