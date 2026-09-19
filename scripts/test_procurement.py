"""Offline scope, evidence, isolation and procurement UI tests."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from core.fsc_collection import CollectionError, xml_root
from core.procurement_collection import (selected, record, discover_query, collect_document, safe_xml,
                                         prepare_source, NATIONAL, LOCAL)
from core.procurement_universe import build_graph, validate_bundle, sector_graph, mark_sector, load_bundle
from core.fsc_administrative import provision_blocks


def fixture():
    law=dict(name=NATIONAL,provider='eflaw',category='procurement',uid='eflaw:1',law_id='1',mst='11',
             effective='20260918',kind='법률',managing_authority='재정경제부',short_name='국가계약법',
             source_url='https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=11',body_status='indexed-statute-text',annexes=[],
             articles=[dict(jo=str(n),title='계약',text=f'제{n}조(계약) 계약을 체결한다.',blocks=[]) for n in [1,2,3,27]])
    rule=dict(name='(계약예규)정부 입찰ㆍ계약 집행기준',provider='admrul',category='procurement',uid='admrul:2',
              effective='20260918',kind='계약예규',managing_authority='재정경제부',
              source_url='https://www.law.go.kr/LSW/admRulLsInfoP.do?admRulSeq=22',
              raw_body_blocks=[f'제1조(목적) 「{NATIONAL}」(이하 "법"이라 한다)에 따른다.',
                               '제2조(절차) 법 제27조에 따른다.', '제3조(범위) 「국가계약법」 제1조부터 제3조까지 적용한다.'])
    other=dict(name='조달청 물품구매적격심사 세부기준',provider='admrul',category='procurement',uid='admrul:3',
               effective='20260918',kind='지침',managing_authority='조달청',
               source_url='https://www.law.go.kr/LSW/admRulLsInfoP.do?admRulSeq=33',
               raw_body_blocks=['제1조(심사) 「정부 입찰ㆍ계약 집행기준」 제2조를 적용한다.',
                                '제2조(다른 법) 「민법」 제2조에 따른다.'])
    return prepare_source(dict(domain='procurement',built_at='20260918',provider='fixture',laws=[law],
                               administrative_rules=[rule,other],inventory={'scope':'fixture'}))


def bundle():
    source=fixture()
    return dict(source=source,graph=build_graph(source))


class ProcurementTests(unittest.TestCase):
    def test_scope_exact_family_not_employment(self):
        self.assertTrue(selected(NATIONAL,'재정경제부,조달청','eflaw'))
        self.assertFalse(selected('국방부 무기계약근로자 등 운영예규','국방부','admrul'))
        self.assertFalse(selected('조달청 공무직근로자 관리규정','조달청','admrul'))

    def test_wrong_authority_rejected(self):
        self.assertFalse(selected('(계약예규) 공동계약운용요령','다른기관','admrul'))

    def test_pagination_fails_closed(self):
        raw=b'<LawSearch><totalCnt>2</totalCnt><page>1</page><law/></LawSearch>'
        with self.assertRaisesRegex(CollectionError,'short-procurement-page'):
            discover_query(lambda *args:raw,'eflaw',NATIONAL,'20260918')

    def test_wrong_envelope(self):
        with self.assertRaises(CollectionError):
            discover_query(lambda *args:b'<Error/>','eflaw',NATIONAL,'20260918')

    def test_credential_scrubbing(self):
        self.assertNotIn(b'private',safe_xml(b'<a>?OC=private&amp;ID=22</a>'))

    def test_body_identity_mismatch_rejected(self):
        item=dict(provider='admrul',state='current-candidate',effective='20260918',version_id='22',
                  document_id='2',name='기준',managing_authority='재정경제부')
        with self.assertRaisesRegex(CollectionError,'identity-mismatch'):
            collect_document(lambda *args:b'<AdmRulService/>',item,'20260918')

    def test_future_body_rejected(self):
        with self.assertRaisesRegex(CollectionError,'not-effective'):
            collect_document(None,dict(state='scheduled'),'20260918')

    def test_real_quote_alias_and_range(self):
        graph=bundle()['graph']
        refs=[e['target_ref'] for e in graph['edges'] if e['source_jo']=='3']
        self.assertEqual(set(refs),{'제1조','제2조','제3조'})
        self.assertTrue(any(e['target_law'].startswith('(계약예규)') and e['target_ref']=='제2조' for e in graph['edges']))

    def test_pinned_links_and_external_not_nodes(self):
        graph=bundle()['graph']
        self.assertNotIn('민법',graph['laws'])
        self.assertTrue(any(e['target_law']=='민법' and e['target_status']=='not-collected' for e in graph['external_references']))
        self.assertTrue(all('admRulSeq=' in e['source_url'] for e in graph['edges']))

    def test_evidence_offsets_and_validation(self):
        data=bundle();validate_bundle(data)
        data['graph']['edges'][0]['cite_raw']='fabricated'
        with self.assertRaises(ValueError):validate_bundle(data)

    def test_annex_title_evidence_is_validated(self):
        source=fixture()
        source['laws'][0]['annexes']=[dict(ref='별표 1',title='기준(제27조 관련)',effective='20260918')]
        graph=build_graph(source)
        validate_bundle(dict(source=source,graph=graph))
        self.assertTrue(any(e['source_granularity']=='annex' for e in graph['edges']))

    def test_wrong_domain_rejected(self):
        data=bundle();data['graph']['domain']='tax'
        with self.assertRaises(ValueError):validate_bundle(data)

    def test_missing_file_never_falls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):load_bundle(Path(directory)/'missing.json')

    def test_sector_filter_keeps_cross_sector_reverse(self):
        from core.galaxy_focus import analyze_focus
        graph=bundle()['graph'];rule='(계약예규)정부 입찰ㆍ계약 집행기준'
        view=sector_graph(graph,'national')
        self.assertNotIn('조달청 물품구매적격심사 세부기준',view['laws'])
        result=mark_sector(analyze_focus(rule,'제2조',graph),graph,'national')
        self.assertTrue(any(r['direction']=='reverse' and r['out_of_sector'] for r in result['rows']))

    def test_attachment_only_stays_unindexed(self):
        source=fixture()
        rule=deepcopy(source['administrative_rules'][0]);rule.update(uid='admrul:4',name='지방자치단체 입찰 및 계약 집행기준',
            managing_authority='행정안전부',raw_body_blocks=[],analysis_error='API 본문 미제공',articles=[])
        source['administrative_rules'].append(rule)
        result=prepare_source(source)
        self.assertFalse(result['administrative_rules'][-1]['articles'])
        self.assertNotIn(rule['name'],build_graph(result)['laws'])

    def test_duplicate_headings_not_silently_indexed(self):
        source=fixture();source['administrative_rules'][0]['raw_body_blocks']=['제1조(가) 본문\n제1조(나) 본문']
        parsed=prepare_source(source)['administrative_rules'][0]
        self.assertEqual(parsed['body_status'],'collected-not-indexed')

    def test_missing_ui_is_explicit(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_string('from unittest.mock import patch\nfrom pathlib import Path\nfrom ui import procurement_map_ui as u\nwith patch.object(u,"BUNDLE",Path("output/nonexistent-procurement-test.json")):\n u.render()').run()
        self.assertFalse(app.exception)
        self.assertEqual(app.info[0].value,'조달계약 데이터 미수집')


if __name__=='__main__':unittest.main()
