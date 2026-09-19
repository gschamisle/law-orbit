"""Opt-in administrative grammar, evidence identity and sector boundary tests."""
from copy import deepcopy
import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from core.citation_scope import parse_target, parse_scope, classify
from core.fsc_administrative import index_rule, prepare_source
from core.fsc_graph import build_fsc_graph
from core.fsc_universe import validate_bundle, article_for
from core.fsc_sectors import tags_for, sector_graph, mark_sector
from core.galaxy_focus import analyze_focus
from scripts.test_fsc_isolation import fixture

def rule(name,text):
    return dict(name=name,provider='admrul',category='fsc',effective='20260916',fetched_at='20260916',
                managing_authority='금융감독원' if name.endswith('세칙') else '금융위원회',
                kind='세칙' if name.endswith('세칙') else '고시',
                source_url='https://www.law.go.kr/LSW/admRulLsInfoP.do?admRulSeq=123',
                raw_body_blocks=[text],articles=[],annexes=[],body_status='collected-not-indexed')

def sector_fixture():
    source = fixture()['source']
    source['administrative_rules'] = [
        rule('보험업감독규정','제1-1조(목적) 「보험업법」(이하 "법"이라 한다).\n제1-2조(기준) 법 제1조에 따른다.\n제1-3조(준용) 제1-2조를 준용한다.'),
        rule('보험업감독업무시행세칙','제1-1조(목적) 「보험업감독규정」(이하 "감독규정"이라 한다).\n제1-2조(방법) 감독규정 제1-2조부터 제1-3조까지 및 「은행법」 제1조를 적용한다. 미지규정 제7조를 적용한다.'),
        rule('금융소비자 보호에 관한 감독규정','제1조(연계) 「보험업감독규정」 제1-2조를 적용한다.'),
        rule('퇴직연금감독규정','제1조(기준) 「은행법」 제1조를 적용한다.')]
    source=prepare_source(source)
    return validate_bundle(dict(source=source,graph=build_fsc_graph(source)))

class Sectors(unittest.TestCase):
    def test_tax_grammar_unchanged_and_hyphen_branches_distinct(self):
        with self.assertRaises(ValueError): parse_target('제1-2조')
        self.assertNotEqual(parse_target('제1-2조',allow_hyphen=True),parse_target('제1조의2'))
        p=parse_target('제2-9조의2제3항',allow_hyphen=True)
        self.assertEqual(p.label,'제2-9조의2제3항')
        self.assertEqual(classify('제2-9조부터 제2-10조까지',p,allow_hyphen=True)[0],'range')
        self.assertEqual(classify('제2-9조부터 제2-10조까지',parse_target('제2-11조',allow_hyphen=True),allow_hyphen=True)[0],'disjoint')

    def test_body_structure_does_not_split_inline_citations(self):
        d=index_rule(rule('보험업감독규정','제1장 총칙\n제1-1조(목적) 제2-3조(기준)를 적용한다.\n제1-2조의2(기준) ① 법 제1조에 따른다.\n ② 법 제2조에 따른다.\n부칙\n제1조(시행일) 공포한 날'))
        self.assertEqual([a['jo'] for a in d['articles']],['1-1','1-2의2'])
        self.assertTrue(any(b['ref']=='제1-2조의2제2항' for b in d['articles'][1]['blocks']))
        for a in d['articles']:
            for b in a['blocks']: self.assertEqual(a['text'][b['start']:b['end']],b['text'])

    def test_deleted_headings_and_duration_are_not_branch_numbers(self):
        s=fixture()['source']
        s['administrative_rules']=[rule('공통규정','제27조(기간) 제28조의 10일을 단축한다.\n제28조 삭 제 <2005. 1. 1.>\n제29조(기준) 본문.')]
        source=prepare_source(s);graph=build_fsc_graph(source)
        self.assertEqual([a['jo'] for a in source['administrative_rules'][0]['articles']],['27','28','29'])
        e=next(e for e in graph['edges'] if e['source_law']=='공통규정')
        self.assertEqual(e['target_ref'],'제28조')
        self.assertEqual(e['target_provision_status'],'deleted')

    def test_explicit_alias_and_rule_to_rule_reverse_evidence(self):
        bundle=sector_fixture();graph=bundle['graph']
        bylaw=[e for e in graph['edges'] if e['source_law']=='보험업감독업무시행세칙' and e['source_jo']=='1-2']
        self.assertTrue(any(e['target_law']=='보험업감독규정' and e['target_ref']=='제1-3조' for e in bylaw))
        self.assertFalse(any(e['target_ref']=='제7조' for e in bylaw))
        self.assertTrue(any('미지규정' in e['raw'] for e in graph['citation_issues']))
        result=analyze_focus('보험업감독규정','1-2',graph)
        self.assertTrue(any(r['direction']=='reverse' and r['source_law']=='보험업감독업무시행세칙' for r in result['rows']))
        self.assertTrue(any(r['direction']=='forward' and r['target_law']=='보험업법' for r in result['rows']))
        texts={(d['name'],a['jo']):a['text'] for d in bundle['source']['laws']+bundle['source']['administrative_rules'] for a in d['articles']}
        for e in graph['edges']+graph['external_references']:
            if e['source_granularity']!='annex': self.assertEqual(texts[e['source_law'],e['source_jo']][e['source_start']:e['source_end']],e['cite_raw'])

    def test_multiple_tags_and_common_cross_sector_connections_survive(self):
        self.assertEqual(set(tags_for('퇴직연금감독규정시행세칙')[0]),{'insurance','banking','securities'})
        bundle=sector_fixture();graph=bundle['graph']
        insurance=sector_graph(graph,'insurance')
        self.assertIn('보험업감독규정',insurance['laws'])
        self.assertNotIn('은행법',insurance['laws'])
        result=mark_sector(analyze_focus('보험업감독규정','1-2',graph),graph,'insurance')
        self.assertTrue(any(r['out_of_sector'] and r['neighbor_law']=='금융소비자 보호에 관한 감독규정' for r in result['rows']))
        self.assertTrue(any(not r['out_of_sector'] and r['neighbor_law']=='보험업감독업무시행세칙' for r in result['rows']))
        self.assertEqual(article_for(bundle,'보험업감독업무시행세칙','1-2')[1]['jo'],'1-2')

    def test_derivative_alias_uses_explicit_parent(self):
        d=index_rule(rule('은행업감독규정','제1조(목적) 「은행법」(이하 "법"이라 한다) 및 같은 법 시행령(이하 "영"이라 한다).\n제2조(내용) 영 제1조의2에 따른다.'))
        self.assertEqual(d['aliases']['영'],'은행법 시행령')

    def test_parenthetical_alias_before_article_keeps_explicit_owner(self):
        s=fixture()['source']
        s['administrative_rules']=[rule('공통규정','제1조(목적) 「은행법」 (이하 "법"이라 한다) 제1조에 따른다.\n제2조(연계) 법 시행령 제1조에 따른다.')]
        source=prepare_source(s);g=build_fsc_graph(source)
        self.assertTrue(any(e['source_law']=='공통규정' and e['target_law']=='은행법' and e['target_kind']=='article' for e in g['edges']))
        self.assertFalse(any(e['source_law']=='공통규정' and e['target_law']=='공통규정' for e in g['edges']))
        self.assertTrue(any(e['target_law']=='은행법 시행령' for e in g['external_references']))

    def test_duplicate_official_numbers_are_blocked_not_renumbered(self):
        s=fixture()['source']
        s['administrative_rules']=[rule('공통규정','제4조(업무대행) 본문.\n제4조(안건상정) 다른 본문.')]
        prepared=prepare_source(s);r=prepared['administrative_rules'][0]
        self.assertEqual(r['body_status'],'collected-not-indexed')
        self.assertFalse(r['articles'])
        self.assertEqual(r['coverage']['provisions'],'blocked-duplicate-number')
        self.assertNotIn('공통규정',build_fsc_graph(prepared)['laws'])

    def test_sector_ui_restores_own_search_and_filters(self):
        from streamlit.testing.v1 import AppTest
        from ui import fsc_map_ui
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'bundle.json';p.write_text(json.dumps(sector_fixture(),ensure_ascii=False),encoding='utf-8')
            with patch.object(fsc_map_ui,'BUNDLE',p):
                app=AppTest.from_string('from ui.fsc_map_ui import render\nrender()',default_timeout=45).run()
                app.radio(key='fsc_sector').set_value('insurance').run()
                self.assertNotIn('은행법',app.selectbox(key='fsc_insurance_focus_law').options)
                app.selectbox(key='fsc_insurance_focus_law').set_value('보험업감독규정')
                app.text_input(key='fsc_insurance_focus_ref').set_value('1-2')
                app.button(key='fsc_insurance_focus_run').click().run()
                self.assertFalse(app.exception,str(app.exception))
                self.assertTrue(any('분야 밖 관련 조문' in e.label for e in app.expander))
                app.radio(key='fsc_insurance_direction').set_value('reverse').run()
                app.radio(key='fsc_sector').set_value('banking').run()
                self.assertNotIn('fsc_banking_focus_selection',app.session_state)
                self.assertEqual(app.text_input(key='fsc_banking_focus_ref').value,'제2조')
                app.text_input(key='fsc_banking_focus_ref').set_value('1')
                app.button(key='fsc_banking_focus_run').click().run()
                app.radio(key='fsc_sector').set_value('insurance').run()
                self.assertFalse(app.exception,str(app.exception))
                self.assertEqual(app.session_state['fsc_insurance_focus_selection'],('보험업감독규정','제1-2조'))
                self.assertEqual(app.text_input(key='fsc_insurance_focus_ref').value,'1-2')
                self.assertEqual(app.radio(key='fsc_insurance_direction').value,'reverse')
                self.assertEqual(app.session_state['fsc_banking_focus_selection'],('은행법','제1조'))

    def test_bylaw_discovery_rejects_partial_and_wrong_issuer(self):
        from core.fsc_bylaws import discover_bylaws
        from core.fsc_collection import CollectionError
        header='<AdmRulSearch><totalCnt>1</totalCnt><page>1</page>'
        wrong=header+'<admrul><행정규칙ID>123</행정규칙ID><행정규칙명>보험업감독업무시행세칙</행정규칙명><소관부처명>다른기관</소관부처명></admrul></AdmRulSearch>'
        with self.assertRaises(CollectionError): discover_bylaws(lambda *a:wrong.encode(),as_of='20260916')
        short=header+'</AdmRulSearch>'
        with self.assertRaises(CollectionError): discover_bylaws(lambda *a:short.encode(),as_of='20260916')

if __name__=='__main__': unittest.main()
