"""National-property scope, pagination and isolation before calling the live API."""
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from core import state_property_collection as c
from core.fsc_collection import CollectionError, xml_root
from core.state_property_special import parse_annex,resolve_rows,validate_register


def annex_document(text=None):
    return dict(name=c.SPECIAL,edition_key='eflaw:1:2:20260901',version_id='2',effective='20260901',
                source_url='https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=2',annexes=[
                dict(ref='별표 0',title='국유재산특례(제4조 관련)',urls=[],text=text or
                     '근거 법률 특례유형 존속기한\n│1│「시험법」 제2조 및│사용료등의 감│2026. 12. 31.│\n││제3조│면 및 양여││\n│2│법률 제123호 역사법 부칙 제2조│장기사용허가등│2024. 12. 31.│\n')])


class StatePropertyCollectionTests(unittest.TestCase):
    def test_exact_core_scope(self):
        self.assertTrue(c.selected('국유재산법 시행령','재정경제부','eflaw'))
        self.assertTrue(c.selected('국유재산특례제한법','기획재정부','eflaw'))
        self.assertFalse(c.selected('공유재산 및 물품 관리법','행정안전부','eflaw'))
        self.assertFalse(c.selected('국유재산법','다른기관','eflaw'))
        self.assertFalse(c.selected('국유재산법을 위한 임의 법률','재정경제부','eflaw'))

    def test_rules_require_scope_and_issuer(self):
        self.assertTrue(c.selected('국유증권 관리·처분 기준','재정경제부','admrul'))
        self.assertFalse(c.selected('지방자치단체 국유재산 관리 규칙','서울특별시','admrul'))
        self.assertFalse(c.selected('계약예규','재정경제부','admrul'))

    def test_own_domain(self):
        raw='<law><법령명한글>국유재산법</법령명한글><소관부처명>재정경제부</소관부처명><법령ID>1</법령ID><법령일련번호>2</법령일련번호><시행일자>20260820</시행일자><공포일자>20260219</공포일자><법령구분명>법률</법령구분명></law>'
        self.assertEqual(c.record(xml_root(raw.encode()),'eflaw','20260920')['category'],'state_property')

    def test_short_page_fails(self):
        with self.assertRaises(CollectionError):
            c.discover_query(lambda *a:b'<LawSearch><totalCnt>2</totalCnt><page>1</page><law/></LawSearch>',
                             'eflaw',c.PROPERTY,'20260920',record_factory=c.record)

    def test_conflicting_effective_editions_fail(self):
        row=dict(uid='1',edition_key='1:1',name=c.PROPERTY,managing_authority='재정경제부',state='current-candidate')
        with patch.object(c,'discover_query',return_value={'records':[row,{**row,'edition_key':'1:2'}]}):
            with self.assertRaises(CollectionError): c.discover_inventory(None,'20260920')

    def test_wrong_domain_never_falls_back(self):
        with self.assertRaises(ValueError): c.prepare_source({'domain':'tax'})

    def test_annex_multiline_rows_and_provenance(self):
        doc=annex_document();register=parse_annex(doc,'20260920');row=register['rows'][0]
        self.assertEqual(row['types'],['fee','transfer'])
        self.assertEqual(row['references'],['제2조','제3조'])
        self.assertEqual(row['deadline'],'20261231')
        self.assertEqual(register['text'][row['source_start']:row['source_end']],row['raw'])

    def test_annex_historical_supplement_not_current_article(self):
        row=parse_annex(annex_document(),'20260920')['rows'][1]
        self.assertEqual(row['status'],'historical-supplement')
        self.assertEqual(row['references'],[])
        self.assertEqual(row['deadline_status'],'elapsed')

    def test_annex_row_loss_or_ambiguous_date_fails(self):
        doc=annex_document()
        for a,b in [('│2│','│3│'),('2026. 12. 31.','2026 또는 2027'),('│면 및 양여││','│면 및 양여│')]:
            with self.subTest(value=b),self.assertRaises(CollectionError):
                parse_annex(annex_document(doc['annexes'][0]['text'].replace(a,b)),'20260920')

    def test_missing_reference_not_substituted(self):
        register=parse_annex(annex_document(),'20260920')
        docs=[dict(name='시험법',source_url='https://www.law.go.kr/',effective='20260901',articles=[{'jo':'2'}])]
        result=resolve_rows(register,docs)['rows'][0]
        self.assertEqual(result['status'],'article-unavailable')
        self.assertEqual(result['article_numbers'],['2'])

    def test_wrapped_supplement_and_qualified_reference(self):
        source=annex_document()['annexes'][0]['text'].replace('부칙','부 칙').replace('제3조│','제3조 (시설에 한정한다)│')
        register=parse_annex(annex_document(source),'20260920')
        self.assertEqual(register['rows'][1]['status'],'historical-supplement')
        self.assertEqual(register['rows'][0]['references'],['제2조','제3조'])
        self.assertEqual(register['rows'][0]['condition'],'(시설에한정한다)')

    def test_issuer_exception_is_narrow(self):
        item=dict(provider='eflaw',name='국회사무처법',managing_authority='국회')
        self.assertTrue(c.authority_matches(item,{'국회사무처'}))
        self.assertFalse(c.authority_matches({**item,'name':'무관한 법률'},{'국회사무처'}))
        self.assertFalse(c.authority_matches(item,{'다른 기관'}))

    def test_range_endpoint_is_required(self):
        text=annex_document()['annexes'][0]['text'].replace('제2조 및','제2조부터').replace('제3조│','제5조까지│')
        register=parse_annex(annex_document(text),'20260920')
        docs=[dict(name='시험법',source_url='https://www.law.go.kr/',effective='20260901',articles=[{'jo':'2'},{'jo':'3'}])]
        self.assertEqual(resolve_rows(register,docs)['rows'][0]['status'],'article-unavailable')

    def test_register_rejects_false_matched_status(self):
        doc=annex_document();source=dict(built_at='20260920',laws=[doc])
        reg=resolve_rows(parse_annex(doc,'20260920'),[doc]);validate_register(reg,source)
        reg['rows'][0]['status']='matched'
        with self.assertRaises(ValueError):validate_register(reg,source)

    def test_graph_retains_core_reverse_but_not_unrelated_network(self):
        from core.state_property_universe import build_graph
        source=dict(laws=[dict(name=c.PROPERTY),dict(name='시험법')],administrative_rules=[],related_laws=['시험법'],
                    special_cases={'rows':[dict(law='시험법',article_numbers=['2'])]})
        edges=[dict(source_law='시험법',source_jo='2',target_law='그밖의법'),
               dict(source_law='시험법',source_jo='3',target_law=c.PROPERTY),
               dict(source_law='시험법',source_jo='4',target_law='그밖의법')]
        with patch('core.state_property_universe.shared.build_graph',return_value=dict(edges=edges,external_references=[],coverage={})):
            graph=build_graph(source)
        self.assertEqual([e['source_jo'] for e in graph['edges']],['2','3'])
        self.assertEqual(source['laws'][1]['analyzed_articles'],['2','3'])

    def test_browser_filters_are_independent_and_keep_expired_evidence(self):
        import subprocess,json,shutil
        node=shutil.which('node') or r'C:\Program Files\nodejs\node.exe'
        code="""import {selectCases,dateLabel} from './web/special.mjs';
        const rows=[{number:1,law:'시험법',article_numbers:['2'],types:['fee','transfer'],deadline_status:'elapsed',status:'matched',legal_text:'시험법 제2조',deadline:'20241231'},
        {number:2,law:'다른법',article_numbers:['2'],types:['fee'],deadline_status:'within_date',status:'not-collected',legal_text:'다른법 제2조',deadline:'20261231'}];
        console.log(JSON.stringify([selectCases(rows,{type:'transfer'}).map(r=>r.number),selectCases(rows,{law:'시험법',jo:'3'}),selectCases(rows,{deadline:'elapsed'}).map(r=>r.number),selectCases(rows,{query:'다른 법'}).map(r=>r.number),dateLabel('20261231')]));"""
        result=subprocess.run([node,'--input-type=module','-e',code],capture_output=True,text=True,encoding='utf-8',check=True)
        self.assertEqual(json.loads(result.stdout),[[1],[],[1],[2],'2026.12.31'])

    def test_missing_data_never_substitutes_another_galaxy(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_string("from ui.sector_map_ui import render\nfrom ui.state_property_map_ui import PROFILE\nrender(PROFILE,'output/nonexistent-state-property-test.json')").run()
        self.assertFalse(app.exception)
        self.assertEqual(app.info[0].value,'국유재산 데이터 미수집')
        self.assertFalse(app.selectbox)


@unittest.skipUnless((Path(__file__).resolve().parents[1]/'output/state_property-universe/bundle.json').exists(),'Requires collected national-property source')
class CollectedPropertyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from core.state_property_universe import load_bundle
        cls.bundle=load_bundle()

    def test_real_annex_target_and_original_evidence(self):
        register=self.bundle['source']['special_cases']
        row=next(r for r in register['rows'] if r['law']=='공공주택 특별법' and r.get('reference_text')=='제18조')
        self.assertEqual(row['status'],'matched');self.assertEqual(row['article_numbers'],['18'])
        self.assertIn('18',next(d for d in self.bundle['source']['laws'] if d['name']=='공공주택 특별법')['analyzed_articles'])
        self.assertEqual(register['text'][row['source_start']:row['source_end']],row['raw'])

    def test_real_direct_and_reverse_evidence_and_isolated_ids(self):
        from core.galaxy_focus import analyze_focus
        from scripts.build_static_galaxies import ident
        edges=self.bundle['graph']['edges']
        edge=next(e for e in edges if e['source_law']=='공공주택 특별법' and e['source_jo']=='18' and e['target_law']==c.PROPERTY)
        self.assertTrue(analyze_focus(edge['source_law'],'제18조',self.bundle['graph'])['rows'])
        reverse=analyze_focus(c.PROPERTY,edge['target_ref'],self.bundle['graph'])['rows']
        self.assertTrue(any(r['source_law']=='공공주택 특별법' and r['direction']=='reverse' for r in reverse))
        self.assertNotEqual(ident('state_property','',c.PROPERTY),ident('housing','',c.PROPERTY))

    def test_actual_profile_switch_preserves_own_state(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_string('from ui.state_property_map_ui import render\nrender()',default_timeout=60).run()
        self.assertFalse(app.exception,str(app.exception))
        app.text_input(key='property_core_library_query').set_value('재산').run()
        app.radio(key='property_sector').set_value('special').run()
        self.assertEqual(app.text_input(key='property_special_library_query').value,'')
        app.radio(key='property_sector').set_value('core').run()
        self.assertEqual(app.text_input(key='property_core_library_query').value,'재산')
        self.assertFalse(app.exception,str(app.exception))


if __name__=='__main__':unittest.main()
