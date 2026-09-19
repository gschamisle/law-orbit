"""Integration checks against the collected official snapshot (no API calls)."""
import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
from core.housing_collection import PLAN
from core.housing_universe import load_bundle, article_for, mark_sector
from core.galaxy_focus import analyze_focus


@unittest.skipUnless(all((Path(__file__).resolve().parents[1]/p).is_file() for p in ['output/housing-universe/bundle.json', 'output/procurement-universe/bundle.json', 'output/fsc-universe/bundle.json', 'output/local-tax-universe/current.json']), "Collected snapshots are not in Git; collect them locally to run real-corpus integration tests")
class HousingUI(unittest.TestCase):
    def test_real_permit_links_and_ordinance_context(self):
        b=load_bundle();g=b['graph']
        r=mark_sector(analyze_focus('주택법','제19조',graph=g),g,'housing')
        targets={e['target_law'] for e in r['rows'] if e['direction']=='forward'}
        self.assertTrue({PLAN,'건축법','농지법','산지관리법','하천법'}<=targets)
        self.assertTrue(any(e['out_of_sector'] and e['target_law']=='농지법' for e in r['rows']))
        self.assertTrue(any(e['direction']=='reverse' for e in r['rows']))
        d,a=article_for(b,'건축법','제11조')
        contexts=[e for e in g['context_evidence'] if e['source_law']==d['name'] and e['source_jo']==a['jo']]
        self.assertTrue(any(e['kind']=='조례 위임·참조 문구' for e in contexts))
        self.assertTrue(all(a['text'][e['source_start']:e['source_end']]==e['raw'] for e in contexts))

    def test_admin_rule_range_and_reverse_are_indexed(self):
        b=load_bundle();g=b['graph']
        edges=[e for e in g['edges'] if e['source_law']=='공공주택 업무처리지침' and e['source_jo']=='2']
        self.assertTrue(any(e['target_law']=='공공주택 특별법' and e['target_ref']=='제32조의4' for e in edges))
        result=analyze_focus('공공주택 특별법','제17조',graph=g)
        self.assertTrue(any(e['source_law']=='공공주택 업무처리지침' and e['direction']=='reverse' for e in result['rows']))
        self.assertNotIn('개발행위허가운영지침',g['laws'])

    def test_five_galaxies_and_sector_states_stay_independent(self):
        app=AppTest.from_file('app.py',default_timeout=60).run()
        self.assertFalse(app.exception,str(app.exception))
        uploader=app.get('file_uploader')[0].proto.id
        self.assertIn('국토건축주택',[t.label for t in app.tabs])
        self.assertEqual(app.radio(key='housing_sector').value,'planning')
        app.text_input(key='lm_library_query').set_value('배당금')
        app.text_input(key='pc_national_library_query').set_value('부정당')
        app.text_input(key='local_tax_central_library_query').set_value('시가표준액')
        app.text_input(key='fsc_focus_ref').set_value('제2조').run()
        app.radio(key='housing_sector').set_value('housing').run()
        app.text_input(key='housing_housing_library_query').set_value('의제')
        app.text_input(key='housing_housing_ref').set_value('제19조')
        app.button(key='housing_housing_run').click().run()
        self.assertEqual(app.session_state['housing_housing_selection'],('주택법','제19조'))
        self.assertTrue(any('인허가 의제' in e.label for e in app.expander))
        app.radio(key='housing_sector').set_value('building').run()
        self.assertEqual(app.selectbox(key='housing_building_law').value,'건축법')
        self.assertEqual(app.text_input(key='housing_building_library_query').value,'')
        app.button(key='housing_building_run').click().run()
        self.assertEqual(app.session_state['housing_building_selection'],('건축법','제11조'))
        app.radio(key='housing_sector').set_value('housing').run()
        self.assertEqual(app.text_input(key='housing_housing_library_query').value,'의제')
        self.assertEqual(app.session_state['housing_housing_selection'],('주택법','제19조'))
        app.radio(key='app_section').set_value('review').run()
        app.radio(key='app_section').set_value('galaxy').run()
        self.assertEqual(app.text_input(key='lm_library_query').value,'배당금')
        self.assertEqual(app.text_input(key='pc_national_library_query').value,'부정당')
        self.assertEqual(app.text_input(key='local_tax_central_library_query').value,'시가표준액')
        self.assertEqual(app.text_input(key='fsc_focus_ref').value,'제2조')
        self.assertEqual(app.get('file_uploader')[0].proto.id,uploader)
        self.assertFalse(app.exception,str(app.exception))

    def test_unindexed_rules_are_readable_but_not_graph_nodes(self):
        app=AppTest.from_string('from ui.housing_map_ui import render\nrender()',default_timeout=60).run()
        self.assertIn('개발행위허가운영지침',app.selectbox(key='housing_planning_raw_name').options)
        self.assertNotIn('개발행위허가운영지침',app.selectbox(key='housing_planning_law').options)
        self.assertTrue(any('장·절·항목' in c.value for c in app.caption))
        self.assertTrue(app.text)
        self.assertFalse(app.exception,str(app.exception))


if __name__=='__main__':unittest.main()
