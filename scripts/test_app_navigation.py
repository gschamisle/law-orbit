"""Navigation must preserve the existing analysis and upload widgets."""
import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest


class NavigationTests(unittest.TestCase):
    def test_primary_menu_order_domains_and_simplified_controls(self):
        app=AppTest.from_file('app.py',default_timeout=60).run()
        self.assertFalse(app.exception,str(app.exception))
        self.assertEqual(app.radio(key='app_section').options[:2],['법령 탐색','개정안 검토 (국세)'])
        self.assertEqual(app.radio(key='app_section').value,'galaxy')
        self.assertEqual([t.label for t in app.tabs],['국세','조달계약','관세·통관','외환','국유재산','공공기관','국고·회계','금융','지방세','국토건축주택','환경화학안전'])
        self.assertNotIn('법령 관계도 (평면)', app.radio(key='lm_view').options)
        self.assertFalse(any((s.key or '') in ('lm_g_min','lm_g_arts','fsc_minimum','fsc_points') for s in app.slider))
        self.assertTrue(any('현재 국세 개정안만 지원합니다.' in c.value for c in app.caption))
        self.assertGreaterEqual(len(app.get('popover')),3 if (Path(__file__).resolve().parents[1]/'output/fsc-universe/bundle.json').is_file() else 2)

    @unittest.skipUnless((Path(__file__).resolve().parents[1]/"output/fsc-universe/bundle.json").is_file(), "Requires locally collected FSC snapshot")
    def test_sidebar_switch_preserves_galaxy_choices_and_uploader_identity(self):
        app=AppTest.from_file('app.py',default_timeout=60).run()
        upload_id=app.get('file_uploader')[0].proto.id
        app.text_input(key='lm_library_query').set_value('배당금').run()
        app.text_input(key='lm_focus_ref').set_value('제16조제2항')
        app.button(key='lm_focus_run').click().run()
        app.radio(key='fsc_sector').set_value('insurance').run()
        app.selectbox(key='fsc_insurance_focus_law').set_value('보험업감독규정').run()
        app.text_input(key='fsc_insurance_focus_ref').set_value('7-1')
        app.button(key='fsc_insurance_focus_run').click().run()
        app.radio(key='app_section').set_value('review').run()
        self.assertFalse(app.exception,str(app.exception))
        self.assertEqual(app.get('file_uploader')[0].proto.id, upload_id)
        app.radio(key='app_section').set_value('galaxy').run()
        self.assertEqual(app.text_input(key='lm_library_query').value,'배당금')
        self.assertEqual(app.session_state['lm_focus_selection'],('법인세법','제16조제2항'))
        self.assertEqual(app.session_state['fsc_insurance_focus_selection'],('보험업감독규정','제7-1조'))
        self.assertEqual(app.radio(key='fsc_sector').value,'insurance')
        self.assertEqual(app.get('file_uploader')[0].proto.id, upload_id)
        self.assertFalse(app.exception,str(app.exception))


if __name__=='__main__': unittest.main()
