"""Real collected API snapshots, kept optional for offline fixture-only CI."""
import json,unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
from core.public_institution_scope import PUBLIC,PRIVATE

BUNDLE=Path('output/public-scope/privatization/bundle.json')

@unittest.skipUnless(BUNDLE.is_file(),'Requires the separately collected public-scope snapshot')
class CollectedScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle=json.loads(BUNDLE.read_text(encoding='utf-8'))
        cls.scope=cls.bundle['graph']['public_scope']

    def test_info_disclosure_uses_institution_definition_not_network_definition(self):
        rows=[r for r in self.scope['records'] if r['kind']=='indirect' and r['source_law']=='공공기관의 정보공개에 관한 법률']
        self.assertEqual({r['target_jo'] for r in rows},{'4','5','6'})
        self.assertTrue(all(r['source_ref']=='제2조제3호다목' for r in rows))
        self.assertTrue(all(r['path'][1]['law']==PUBLIC for r in rows))

    def test_public_data_chain_stays_unnumbered(self):
        rows=[r for r in self.scope['records'] if r['kind']=='indirect' and r['source_law']=='공공데이터의 제공 및 이용 활성화에 관한 법률']
        self.assertEqual(len(rows),1)
        r=rows[0]
        self.assertEqual(r['source_ref'],'제2조제1호')
        self.assertEqual(r['path'][1]['source_ref'],'제2조제16호가목')
        self.assertEqual(r['path'][1]['law'],'지능정보화 기본법')
        self.assertEqual(r['target_jo'],'')
        self.assertEqual(r['target_kind'],'law')
        self.assertIn('law-definition',r['labels'])

    def test_conditions_and_subsets_are_distinct(self):
        records=self.scope['records']
        software=next(r for r in records if '소프트웨어' in r['source_law'] and r['source_ref']=='제2조제3호마목')
        self.assertIn('criteria',software['labels']);self.assertIn('exclusion',software['labels'])
        self.assertIn('제5호',software['raw']);self.assertNotIn('제6호',software['raw'])
        safety=next(r for r in records if '안전활동' in r['source_law'])
        self.assertIn('additional',safety['labels']);self.assertNotIn('subset',safety['labels'])
        subset=next(r for r in records if '개발선정품' in r['source_law'])
        self.assertIn('subset',subset['labels'])

    def test_privatization_conditions_and_original_sources_survive(self):
        docs={d['name']:d for d in self.bundle['source']['laws']}
        for guide in self.scope['privatization']:
            original=next(a for a in docs[PRIVATE]['articles'] if a['jo']==guide['jo'])
            self.assertEqual(guide['text'],original['text'])
        end=next(g for g in self.scope['privatization'] if g['jo']=='21')
        self.assertIn('그 후 최초로 소집되는 주주총회일',end['text'])
        self.assertIn('100분의 51 이상',end['text'])
        self.assertTrue(all(n in docs for n in ['상법','한국가스공사법','인천국제공항공사법','한국공항공사법']))

    def test_local_viewer_all_guides_and_filter_states(self):
        source="""import json
from pathlib import Path
from ui.public_scope_ui import render
b=json.loads(Path('output/public-scope/privatization/bundle.json').read_text(encoding='utf-8'))
render(b['graph']['public_scope'],{d['name']:d for d in b['source']['laws']+b['source']['administrative_rules']},prefix='p')
"""
        app=AppTest.from_string(source,default_timeout=30).run()
        self.assertFalse(app.exception,str(app.exception))
        for index in range(len(self.scope['privatization'])):
            app.selectbox(key='p_private_guide').set_value(index).run()
            self.assertFalse(app.exception,str(app.exception))
        app.selectbox(key='p_scope_anchor').set_value('4').run()
        app.selectbox(key='p_scope_label').set_value('indirect').run()
        self.assertFalse(app.exception,str(app.exception))
        app.selectbox(key='p_designation').set_value(19).run()
        self.assertEqual(app.selectbox(key='p_scope_anchor').value,'4')
        self.assertEqual(app.selectbox(key='p_scope_label').value,'indirect')
        self.assertFalse(app.exception,str(app.exception))

if __name__=='__main__':unittest.main()
