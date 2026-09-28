"""Do not confuse constitutional principles with literal citation evidence."""
import unittest
from copy import deepcopy
from pathlib import Path
from core.constitution_profile import CONSTITUTION,selected
from core.constitution_relations import adapter
from core.constitution_collection import collect
from core.fsc_collection import CollectionError

class ConstitutionTests(unittest.TestCase):
    def parse(self,text):
        law=dict(name='국회법',provider='eflaw',category='constitution',citation_policy='mofe-explicit',articles=[])
        article=dict(jo='98',text=text)
        constitution=dict(name=CONSTITUTION,citation_names=[CONSTITUTION,'헌법'],articles=[{'jo':str(i)} for i in range(1,131)])
        return adapter(law,article,[law,constitution])

    def test_numbered_reference_resolves_canonical_constitution(self):
        for text in ['헌법 제53조제6항에 따라 공포한다.','「헌법」 제53조제6항에 따라 공포한다.','「대한민국헌법」 제53조제6항에 따라 공포한다.']:
            rows=self.parse(text)
            self.assertEqual(len(rows),1)
            self.assertEqual((rows[0]['target_name'],rows[0]['target_ref']),(CONSTITUTION,'제53조제6항'))
            self.assertEqual(text[rows[0]['start']:rows[0]['end']],rows[0]['raw'])

    def test_whole_reference_does_not_invent_an_article(self):
        rows=self.parse('헌법에 따라 근로조건을 정한다.')
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['kind'],'law')
        self.assertEqual(rows[0]['target_ref'],'법령·정의 참조')

    def test_constitutional_court_name_is_not_constitution_reference(self):
        self.assertFalse(any(r['target_name']==CONSTITUTION for r in self.parse('헌법재판소법 제1조에 따른다.')))

    def test_exact_scope_and_no_ministry_exception(self):
        self.assertTrue(selected(CONSTITUTION,'','eflaw'))
        self.assertFalse(selected('국회법','','eflaw'))
        self.assertTrue(selected('국회법','국회','eflaw'))
        self.assertFalse(selected('국회법','재정경제부','eflaw'))
        self.assertFalse(selected('법률안','','eflaw'))
        with self.assertRaises(CollectionError):
            collect(lambda *a:None,dict(name=CONSTITUTION,provider='eflaw',document_id='999',kind='헌법'), '20260928')

@unittest.skipUnless(Path('output/constitution-universe/bundle.json').is_file(),'Requires constitutional snapshot')
class CollectedConstitutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from core.constitution_universe import load_bundle
        cls.bundle=load_bundle()

    def test_actual_reverse_citation_and_body(self):
        from core.galaxy_focus import analyze_focus
        rows=analyze_focus(CONSTITUTION,'53',self.bundle['graph'])['rows']
        self.assertTrue(any(r['direction']=='reverse' and r['source_law']=='국회법' and r['source_jo']=='98'
                            and r['cite_raw']=='헌법 제53조제6항' for r in rows))
        self.assertEqual(len(next(d['articles'] for d in self.bundle['source']['laws'] if d['name']==CONSTITUTION)),130)

    def test_reading_guide_is_not_graph_evidence(self):
        from core.constitution_relations import validate_guide
        b=self.bundle;guide=b['graph']['constitution_guide'];validate_guide(guide,b['source'])
        self.assertTrue(all(r['is_citation'] is False for r in guide))
        self.assertFalse(any(e.get('type')=='editorial-related-law' for e in b['graph']['edges']))
        self.assertFalse(any(e['source_law']=='근로기준법' and e['source_jo']=='1' and e['target_ref']=='제32조' for e in b['graph']['edges']))
        changed=deepcopy(guide);changed[0]['constitution']['text']='변조'
        with self.assertRaises(ValueError):validate_guide(changed,b['source'])

    def test_local_menu_and_missing_data(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_string("from ui.mofe_map_ui import render\nrender('constitution')",default_timeout=60).run()
        self.assertFalse(app.exception,str(app.exception))
        self.assertTrue(any('관련 법률 안내' in e.label for e in app.expander))
        missing=AppTest.from_string("from ui.sector_map_ui import render\nrender(dict(domain='constitution',prefix='missing_constitution',title='헌법'), 'output/does-not-exist/bundle.json')").run()
        self.assertTrue(any('헌법 데이터 미수집' in i.value for i in missing.info))
        self.assertEqual(len(missing.selectbox),0)

if __name__=='__main__':unittest.main()
