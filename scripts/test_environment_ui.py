"""Offline integration with the separately collected environment snapshot."""
import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
from core.environment_universe import load_bundle,mark_sector
from core.environment_collection import SAFETY,CHEMICAL
from core.galaxy_focus import analyze_focus


@unittest.skipUnless(all((Path(__file__).resolve().parents[1]/p).is_file() for p in ['output/environment-universe/bundle.json', 'output/housing-universe/bundle.json', 'output/procurement-universe/bundle.json', 'output/fsc-universe/bundle.json', 'output/local-tax-universe/current.json']), "Collected snapshots are not in Git; collect them locally to run real-corpus integration tests")
class EnvironmentUI(unittest.TestCase):
    def test_real_rule_reverse_and_cross_sector(self):
        b=load_bundle();g=b['graph']
        r=mark_sector(analyze_focus(SAFETY,'제23조',graph=g),g,'chemical')
        self.assertTrue(any(e['direction']=='reverse' and e['source_law']=='화학사고예방관리계획서 작성 등에 관한 규정' for e in r['rows']))
        self.assertTrue(any(e['out_of_sector'] and e['source_law']=='산업안전보건법 시행령' for e in r['rows']))
        rule=analyze_focus('화학사고예방관리계획서 작성 등에 관한 규정','제17조',graph=g)
        self.assertTrue(any(e['target_law'].startswith('공정안전보고서') for e in rule['rows']))

    def test_future_edition_never_replaces_current_body(self):
        b=load_bundle();s=b['source'];self.assertTrue(s['scheduled'])
        future=next(r for r in s['scheduled'] if r['document_id']=='62419')
        d=next(d for d in s['administrative_rules'] if d['document_id']=='62419')
        self.assertGreater(future['effective'],s['built_at'])
        self.assertLessEqual(d['effective'],s['built_at'])
        self.assertNotEqual(d['version_id'],future['version_id'])
        self.assertEqual(len({r['uid'] for r in s['laws']+s['administrative_rules']}),len(s['laws'])+len(s['administrative_rules']))

    def test_six_galaxies_and_sector_state_isolation(self):
        app=AppTest.from_file('app.py',default_timeout=60).run()
        self.assertFalse(app.exception,str(app.exception))
        self.assertIn('환경화학안전',[t.label for t in app.tabs])
        upload_id=app.get('file_uploader')[0].proto.id
        app.text_input(key='lm_library_query').set_value('배당금')
        app.text_input(key='fsc_focus_ref').set_value('제2조')
        app.text_input(key='local_tax_central_library_query').set_value('시가표준액')
        app.text_input(key='pc_national_library_query').set_value('부정당')
        app.text_input(key='housing_planning_library_query').set_value('허가').run()
        app.radio(key='env_sector').set_value('chemical').run()
        self.assertEqual(app.selectbox(key='env_chemical_law').value,CHEMICAL)
        app.selectbox(key='env_chemical_law').set_value(SAFETY).run()
        app.text_input(key='env_chemical_library_query').set_value('예방관리계획서')
        app.text_input(key='env_chemical_ref').set_value('제23조')
        app.button(key='env_chemical_run').click().run()
        self.assertEqual(app.session_state['env_chemical_selection'],(SAFETY,'제23조'))
        self.assertTrue(any('분야 밖 관련 조문' in e.label for e in app.expander))
        app.radio(key='env_sector').set_value('accident').run()
        self.assertEqual(app.text_input(key='env_accident_library_query').value,'')
        app.radio(key='env_sector').set_value('chemical').run()
        self.assertEqual(app.text_input(key='env_chemical_library_query').value,'예방관리계획서')
        self.assertEqual(app.session_state['env_chemical_selection'],(SAFETY,'제23조'))
        app.radio(key='app_section').set_value('review').run()
        app.radio(key='app_section').set_value('galaxy').run()
        for key,value in [('lm_library_query','배당금'),('fsc_focus_ref','제2조'),('local_tax_central_library_query','시가표준액'),('pc_national_library_query','부정당'),('housing_planning_library_query','허가')]:
            self.assertEqual(app.text_input(key=key).value,value)
        self.assertEqual(app.get('file_uploader')[0].proto.id,upload_id)
        self.assertFalse(app.exception,str(app.exception))

    def test_unindexed_and_future_notices(self):
        app=AppTest.from_string('from ui.environment_map_ui import render\nrender()',default_timeout=60).run()
        app.radio(key='env_sector').set_value('chemical').run()
        self.assertIn('화학물질의 시험방법에 관한 규정',app.selectbox(key='env_chemical_raw_name').options)
        self.assertNotIn('화학물질의 시험방법에 관한 규정',app.selectbox(key='env_chemical_law').options)
        self.assertTrue(any('API 본문 미제공' in c.value for c in app.caption))
        self.assertTrue(any('시행예정' in e.label for e in app.expander))
        self.assertFalse(app.exception,str(app.exception))


if __name__=='__main__':unittest.main()
