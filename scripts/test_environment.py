"""Environment scope, traceable citation evidence, and data separation."""
from pathlib import Path
import tempfile
import unittest
from core.environment_collection import selected,tags,prepare_source,SAFETY,CHEMICAL,record
from core.environment_universe import build_graph,validate_bundle,load_bundle,sector_graph,mark_sector,present
from core.fsc_collection import CollectionError,xml_root
from core.procurement_collection import discover_query


def bundle():
    laws=[]
    for i,name in enumerate((SAFETY,'산업안전보건법'),1):
        articles=[dict(jo=str(n),title='시험',text=f'제{n}조(시험) 본문',blocks=[]) for n in (1,2,3,23)]
        if i==2:articles[-1]['text']=f'제23조(계획) 「{SAFETY}」 제23조를 준용한다.'
        laws.append(dict(name=name,provider='eflaw',category='environment',uid=f'eflaw:{i}',law_id=str(i),mst=str(i),
            effective='20260919',kind='법률',managing_authority='기후에너지환경부' if i==1 else '고용노동부',
            short_name='화관법' if i==1 else '',articles=articles,annexes=[],
            source_url=f'https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq={i}'))
    rule=dict(name='화학사고예방관리계획서 작성 등에 관한 규정',provider='admrul',category='environment',uid='admrul:3',
        effective='20260919',kind='고시',managing_authority='화학물질안전원',
        source_url='https://www.law.go.kr/LSW/admRulLsInfoP.do?admRulSeq=3',
        raw_body_blocks=[f'제1조(목적) 「{SAFETY}」(이하 "법"이라 한다)에 따른다.',
                        '제2조(범위) 「화관법」 제1조부터 제3조까지 적용한다.',
                        '제3조(대상) 법 제23조 및 「민법」 제2조에 따른다.'])
    s=prepare_source(dict(domain='environment',built_at='20260919',provider='fixture',laws=laws,
                         administrative_rules=[rule],inventory={'scope':'fixture'}))
    return dict(source=s,graph=build_graph(s))


class EnvironmentTests(unittest.TestCase):
    def test_exact_scope_and_authority(self):
        self.assertTrue(selected(CHEMICAL+' 시행령','기후에너지환경부','eflaw'))
        self.assertTrue(selected('산업안전보건기준에 관한 규칙','고용노동부','eflaw'))
        self.assertFalse(selected('서울특별시 화학물질 관리 조례','서울특별시','ordin'))
        self.assertFalse(selected(SAFETY,'다른기관','eflaw'))

    def test_facility_rule_scope(self):
        name='유해화학물질 제조·사용시설 설치 및 관리에 관한 고시'
        self.assertTrue(selected(name,'화학물질안전원','admrul'))
        self.assertFalse(selected(name,'고용노동부','admrul'))
        self.assertFalse(selected('화학물질안전원 공무직 관리 규정','화학물질안전원','admrul'))

    def test_multi_tags(self):self.assertEqual(tags(SAFETY,'eflaw'),['chemical','accident'])

    def test_official_record_retains_domain(self):
        xml=f'<law><법령명한글>{SAFETY}</법령명한글><소관부처명>기후에너지환경부</소관부처명><법령ID>1</법령ID><법령일련번호>2</법령일련번호><시행일자>20260901</시행일자><공포일자>20250101</공포일자><법령구분명>법률</법령구분명></law>'
        self.assertEqual(record(xml_root(xml.encode()),'eflaw','20260919')['category'],'environment')

    def test_partial_inventory_fails(self):
        with self.assertRaises(CollectionError):
            discover_query(lambda *a:b'<LawSearch><totalCnt>2</totalCnt><page>1</page><law/></LawSearch>',
                           'eflaw',SAFETY,'20260919',record_factory=record)

    def test_effective_and_future_editions_are_separated(self):
        from unittest.mock import patch
        from core import environment_collection as c
        current=dict(uid='admrul:1',edition_key='admrul:1:2:20260101',name=SAFETY,
                     managing_authority='화학물질안전원',state='current-candidate',effective='20260101')
        future={**current,'edition_key':'admrul:1:3:20261217','state':'scheduled','effective':'20261217'}
        layer=dict(records=[future,current],received=2)
        with patch.multiple(c,STATUTE_QUERIES=(),RULE_QUERIES=('test',),FAMILY_TAGS={SAFETY:[]},SPECIAL_TAGS={},RULE_TAGS={}), patch.object(c,'discover_query',return_value=layer), patch.object(c,'facility_rule',return_value=True):
            inventory=c.discover_inventory(None,'20260919')
        self.assertEqual(len(inventory['records']),2)
        self.assertEqual([r['edition_key'] for r in inventory['records'] if r['state']=='current-candidate'],[current['edition_key']])

    def test_conflicting_effective_editions_still_fail(self):
        from unittest.mock import patch
        from core import environment_collection as c
        current=dict(uid='admrul:1',edition_key='a',name=SAFETY,managing_authority='화학물질안전원',state='current-candidate')
        layer=dict(records=[current,{**current,'edition_key':'b'}],received=2)
        with patch.multiple(c,STATUTE_QUERIES=(),RULE_QUERIES=('test',)), patch.object(c,'discover_query',return_value=layer):
            with self.assertRaises(CollectionError):c.discover_inventory(None,'20260919')

    def test_joint_body_authority_is_narrowly_verified(self):
        from core.environment_collection import authority_matches
        item=dict(provider='eflaw',name='환경오염피해 배상책임 및 구제에 관한 법률',managing_authority='기후에너지환경부')
        joint={'기후에너지환경부','중앙환경분쟁조정피해구제위원회'}
        self.assertTrue(authority_matches(item,joint))
        self.assertFalse(authority_matches({**item,'name':SAFETY},joint))
        self.assertFalse(authority_matches(item,{'기후에너지환경부','다른기관'}))
        self.assertFalse(authority_matches(item,{'중앙환경분쟁조정피해구제위원회'}))

    def test_alias_and_range(self):
        refs={e['target_ref'] for e in bundle()['graph']['edges'] if e['source_law'].startswith('화학사고예방') and e['source_jo']=='2'}
        self.assertEqual(refs,{'제1조','제2조','제3조'})

    def test_reverse_cross_sector(self):
        from core.galaxy_focus import analyze_focus
        g=bundle()['graph'];self.assertNotIn('산업안전보건법',sector_graph(g,'chemical')['laws'])
        r=mark_sector(analyze_focus(SAFETY,'제23조',graph=g),g,'chemical')
        self.assertTrue(any(e['direction']=='reverse' and e['out_of_sector'] for e in r['rows']))

    def test_evidence_not_fabricated(self):
        b=bundle();validate_bundle(b);b['graph']['edges'][0]['cite_raw']='fake'
        with self.assertRaises(ValueError):validate_bundle(b)

    def test_domain_mismatch(self):
        b=bundle();b['source']['domain']='tax'
        with self.assertRaises(ValueError):validate_bundle(b)
        with self.assertRaises(ValueError):prepare_source(b['source'])

    def test_external_no_reverse_claim(self):
        g=bundle()['graph'];self.assertNotIn('민법',g['laws'])
        e=next(e for e in g['external_references'] if e['target_law']=='민법')
        self.assertEqual(e['external_reverse'],'not-collected')

    def test_unstructured_raw_not_graph(self):
        s=bundle()['source'];s['administrative_rules'][0]['raw_body_blocks']=['1. CAS 목록은 별표로 정한다.']
        s=prepare_source(s);self.assertFalse(s['administrative_rules'][0]['articles'])
        self.assertNotIn(s['administrative_rules'][0]['name'],build_graph(s)['laws'])

    def test_substance_and_thresholds_not_claimed(self):
        c=bundle()['graph']['coverage']
        self.assertEqual(c['substance_identity'],'not-analyzed')
        self.assertEqual(c['thresholds'],'not-analyzed')

    def test_missing_no_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):load_bundle(Path(d)/'none.json')

    def test_missing_ui_explicit(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_string('from unittest.mock import patch\nfrom pathlib import Path\nfrom ui import environment_map_ui as u\nwith patch.object(u,"BUNDLE",Path("output/missing-environment-test.json")):\n u.render()').run()
        self.assertFalse(app.exception)
        self.assertEqual(app.info[0].value,'환경·화학안전 데이터 미수집')

    def test_palette_stable(self):
        from core.law_galaxy import build
        g=bundle()['graph'];data=build(1,10,False,graph=g)
        a=present(data,g,'all');b=present(data,g,'chemical')
        self.assertEqual(a['domain'],'environment')
        self.assertEqual([n['color'] for n in a['nodes']],[n['color'] for n in b['nodes']])


if __name__=='__main__':unittest.main()
