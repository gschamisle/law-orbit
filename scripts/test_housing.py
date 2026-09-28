"""Offline housing scope, evidence and domain separation tests."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from core.fsc_collection import CollectionError
from core.housing_collection import PLAN, BUILDING, selected, tags, prepare_source
from core.housing_universe import build_graph, validate_bundle, load_bundle, sector_graph, mark_sector, present


def bundle():
    laws=[]
    for i,name in enumerate((PLAN,'건축물관리법'),1):
        articles=[dict(jo=str(n),title='시험',text=f'제{n}조(시험) 본문',blocks=[]) for n in (1,2,3,56)]
        if i==1:
            articles[-1]['text']='제56조(허가)\n① 시ㆍ도조례로 정하는 사항은 허가를 받은 것으로 본다.\n② 「건축물관리법」 제2조를 준용한다.'
        else:articles[-1]['text']=f'제56조(검토) 「{PLAN}」 제56조를 준용한다.'
        laws.append(dict(name=name,provider='eflaw',category='housing',uid=f'eflaw:{i}',law_id=str(i),mst=str(i),
                    effective='20260919',kind='법률',managing_authority='국토교통부',
                    short_name='국토계획법' if i==1 else '',articles=articles,annexes=[],
                    source_url=f'https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq={i}'))
    rule=dict(name='공공주택 업무처리지침',provider='admrul',category='housing',uid='admrul:3',
              effective='20260919',kind='훈령',managing_authority='국토교통부',
              source_url='https://www.law.go.kr/LSW/admRulLsInfoP.do?admRulSeq=3',
              raw_body_blocks=[f'제1조(목적) 「{PLAN}」(이하 "법"이라 한다)에 따른다.',
                  '제2조(범위) 「국토계획법」 제1조부터 제3조까지 적용한다.',
                  '제3조(대상) 법 제56조 및 「민법」 제2조에 따른다.'])
    source=prepare_source(dict(domain='housing',built_at='20260919',provider='fixture',laws=laws,
                         administrative_rules=[rule],inventory={'scope':'fixture'}))
    return dict(source=source,graph=build_graph(source))


class HousingTests(unittest.TestCase):
    def test_scope_is_exact(self):
        self.assertTrue(selected(PLAN+' 시행령','국토교통부','eflaw'))
        self.assertTrue(selected('주택공급에 관한 규칙','국토교통부','eflaw'))
        self.assertFalse(selected('조달청 건축공사 계약규정','조달청','admrul'))
        self.assertFalse(selected('서울특별시 건축 조례','서울특별시','ordin'))

    def test_authority_enforced(self):
        self.assertFalse(selected(BUILDING,'다른기관','eflaw'))
        self.assertFalse(selected('공공주택 업무처리지침','산림청','admrul'))

    def test_multi_tags_and_related_scope(self):
        self.assertIn('building',tags(PLAN,'eflaw'))
        self.assertIn('planning',tags(PLAN,'eflaw'))
        self.assertEqual(tags('농지법','eflaw'),['related'])

    def test_wrong_source_domain_rejected(self):
        s=bundle()['source'];s['domain']='tax'
        with self.assertRaises(ValueError):prepare_source(s)

    def test_alias_and_range(self):
        g=bundle()['graph']
        self.assertEqual({e['target_ref'] for e in g['edges'] if e['source_law']=='공공주택 업무처리지침' and e['source_jo']=='2'},
                         {'제1조','제2조','제3조'})

    def test_ordinance_not_guessed_as_collected(self):
        b=bundle();validate_bundle(b)
        rows=b['graph']['context_evidence']
        self.assertEqual({e['kind'] for e in rows},{'조례 위임·참조 문구','인허가 의제 문맥'})
        self.assertTrue(all(e['ordinance_status']=='not-collected' for e in rows))
        self.assertFalse(any('조례' in n for n in b['graph']['laws']))

    def test_permit_deeming_covers_report_done_wording(self):
        from core.housing_universe import context_evidence
        source=bundle()['source']
        source['laws'][0]['articles'][-1]['text']='제56조(의제) 신고를 한 것으로 본다.'
        rows=context_evidence(source)
        self.assertTrue(any(e['kind']=='인허가 의제 문맥' for e in rows))

    def test_context_offsets_cannot_be_fabricated(self):
        b=bundle();b['graph']['context_evidence'][0]['raw']='invented'
        with self.assertRaises(ValueError):validate_bundle(b)

    def test_citation_offsets_cannot_be_fabricated(self):
        b=bundle();b['graph']['edges'][0]['cite_raw']='invented'
        with self.assertRaises(ValueError):validate_bundle(b)

    def test_external_no_reverse_claim(self):
        g=bundle()['graph']
        self.assertNotIn('민법',g['laws'])
        e=next(e for e in g['external_references'] if e['target_law']=='민법')
        self.assertEqual(e['external_reverse'],'not-collected')

    def test_outside_sector_reverse_kept(self):
        from core.galaxy_focus import analyze_focus
        g=bundle()['graph'];self.assertNotIn('건축물관리법',sector_graph(g,'planning')['laws'])
        result=mark_sector(analyze_focus(PLAN,'제56조',graph=g),g,'planning')
        self.assertTrue(any(e['out_of_sector'] and e['direction']=='reverse' for e in result['rows']))

    def test_unstructured_rules_stay_unindexed(self):
        s=bundle()['source'];s['administrative_rules'][0]['raw_body_blocks']=['1-1-1. 목적과 기준을 정한다.']
        s=prepare_source(s)
        self.assertFalse(s['administrative_rules'][0]['articles'])
        self.assertNotIn('공공주택 업무처리지침',build_graph(s)['laws'])

    def test_tax_bundle_rejected(self):
        b=bundle();b['graph']['domain']='tax'
        with self.assertRaises(ValueError):validate_bundle(b)

    def test_missing_no_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):load_bundle(Path(d)/'none.json')

    def test_missing_ui_message(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_string('from unittest.mock import patch\nfrom pathlib import Path\nfrom ui import housing_map_ui as u\nwith patch.object(u,"BUNDLE",Path("output/missing-housing-test.json")):\n u.render()').run()
        self.assertFalse(app.exception)
        self.assertEqual(app.info[0].value,'국토·건축·주택 데이터 미수집')

    def test_palette_stable_across_filters(self):
        from core.law_galaxy import build
        g=bundle()['graph'];data=build(1,10,False,graph=g)
        a=present(data,g,'all');b=present(data,g,'planning')
        self.assertEqual(a['domain'],'housing')
        self.assertEqual([n['color'] for n in a['nodes']],[n['color'] for n in b['nodes']])


if __name__=='__main__':unittest.main()
