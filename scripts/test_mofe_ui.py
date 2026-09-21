"""Exercise independent state and practical cases against the collected snapshots."""
import unittest
from streamlit.testing.v1 import AppTest
from core.mofe_profiles import PROFILES
from core.mofe_universe import path

@unittest.skipUnless(all(path(d).is_file() for d in PROFILES),'Requires local MOFE snapshots')
class MofeUI(unittest.TestCase):
    def test_cases_and_domains_keep_independent_state(self):
        source='from ui.mofe_map_ui import render\nfor domain in '+repr(list(PROFILES))+':\n    render(domain)'
        app=AppTest.from_string(source,default_timeout=90).run()
        self.assertFalse(app.exception,str(app.exception))
        app.button(key='mofe_customs_case_226').click().run()
        self.assertEqual(app.session_state['mofe_customs_all_selection'],('관세법','제226조'))
        app.button(key='mofe_treasury_case_26').click().run()
        self.assertEqual(app.session_state['mofe_treasury_all_selection'],('국고금 관리법','제26조'))
        self.assertEqual(app.session_state['mofe_customs_all_selection'],('관세법','제226조'))
        app.radio(key='mofe_public_institutions_sector').set_value('contracts').run()
        app.text_input(key='mofe_public_institutions_contracts_library_query').set_value('계약').run()
        app.button(key='mofe_public_institutions_case_39').click().run()
        self.assertEqual(app.radio(key='mofe_public_institutions_sector').value,'all')
        app.radio(key='mofe_public_institutions_sector').set_value('contracts').run()
        self.assertEqual(app.text_input(key='mofe_public_institutions_contracts_library_query').value,'계약')
        self.assertEqual(app.session_state['mofe_customs_all_selection'],('관세법','제226조'))
        self.assertFalse(app.exception,str(app.exception))

    def test_missing_corpus_notice_without_other_domain_fallback(self):
        app=AppTest.from_string("from ui.sector_map_ui import render\nrender(dict(domain='customs',prefix='missing_customs',title='관세·통관'), 'output/does-not-exist/bundle.json')").run()
        self.assertFalse(app.exception,str(app.exception))
        self.assertTrue(any('관세·통관 데이터 미수집' in i.value for i in app.info))
        self.assertEqual(len(app.selectbox),0)

if __name__=='__main__':unittest.main()
