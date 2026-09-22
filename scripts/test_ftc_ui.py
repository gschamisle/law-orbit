"""FTC missing data and real reader/state isolation checks, without API access."""
import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
from core.ftc_universe import BUNDLE

class FtcUI(unittest.TestCase):
    def test_missing_data_is_not_substituted(self):
        code='''from ui.sector_map_ui import render
from ui.ftc_map_ui import PROFILE
from pathlib import Path
render(PROFILE,Path("output/nonexistent-ftc-fixture/bundle.json"))'''
        app=AppTest.from_string(code).run()
        self.assertFalse(app.exception,str(app.exception));self.assertEqual(app.info[0].value,'공정거래 데이터 미수집')
        self.assertEqual(len(app.selectbox),0)

    @unittest.skipUnless(BUNDLE.exists(),'Requires collected FTC corpus')
    def test_sectors_keep_selections_and_paragraph_evidence(self):
        app=AppTest.from_string('from ui.ftc_map_ui import render\nrender()',default_timeout=60).run()
        self.assertFalse(app.exception,str(app.exception))
        app.text_input(key='ftc_all_ref').set_value('제45조')
        app.button(key='ftc_all_run').click().run()
        selection=app.session_state['ftc_all_selection']
        self.assertTrue(any('이 조문을 인용한 지침 문단' in e.label for e in app.expander))
        app.radio(key='ftc_sector').set_value('consumer').run()
        app.text_input(key='ftc_consumer_library_query').set_value('청약').run()
        app.radio(key='ftc_sector').set_value('all').run()
        self.assertEqual(app.session_state['ftc_all_selection'],selection)
        self.assertEqual(app.text_input(key='ftc_all_ref').value,'제45조')
        app.selectbox(key='ftc_all_raw_name').set_value('기업결합 심사기준').run()
        self.assertTrue(any('Ⅰ. 목 적' in t.value for t in app.text))
        self.assertFalse(app.exception,str(app.exception))

if __name__=='__main__':unittest.main()
