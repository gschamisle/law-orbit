"""Ownership boundaries and old-number safety, with independent mutation cases."""
from copy import deepcopy
import unittest
from xml.etree import ElementTree as ET

from core.fsc_administrative import adapter
from core.annex_metadata import administrative_annexes
from core.citation_scope import parse_target
from core.citation_history import movement_review


class HealthcareCitationTests(unittest.TestCase):
    def citations(self, body, corpus=None):
        law=dict(name='공공보건의료에 관한 법률 시행규칙',provider='eflaw',category='medical',
                 citation_policy='mofe-explicit',effective='20220218',aliases={})
        article=dict(jo='2의2',text='제2조의2(범위) '+body)
        rows=adapter(law,article,corpus or [])
        for row in rows:
            self.assertEqual(article['text'][row['start']:row['end']],row['raw'])
        return rows,article

    def test_elided_second_owner_retained_with_original_span_and_review(self):
        rows,article=self.citations('「감염병의 예방 및 관리에 관한 법률」 제8조의2에 따른 감염병전문병원 및 제36조에 따른 감염병관리기관')
        second=next(r for r in rows if r['target_ref']=='제36조')
        self.assertEqual(second['target_name'],'감염병의 예방 및 관리에 관한 법률')
        self.assertEqual(second['raw'],'제36조')
        self.assertTrue(second['context_review'])
        self.assertFalse(article['citation_issues'])

    def test_owner_inheritance_stops_at_sentence_paragraph_and_self_reference(self):
        for gap in ('에 따른 기관. ', '에 따른 기관\n및 ', '에 따른 기관 및 이 법 ', '에 따른 기관 및 본 법 '):
            rows,_=self.citations('「감염병의 예방 및 관리에 관한 법률」 제8조의2'+gap+'제36조에 따른다.')
            self.assertFalse(any(r['target_name']=='감염병의 예방 및 관리에 관한 법률' and r['target_ref']=='제36조' for r in rows))

    def test_new_quoted_owner_takes_precedence(self):
        rows,_=self.citations('「감염병의 예방 및 관리에 관한 법률」 제8조의2에 따른 기관 및 「의료법」 제36조에 따른 기관')
        self.assertEqual(next(r for r in rows if r['target_ref']=='제36조')['target_name'],'의료법')

    def test_same_act_rule_resolves_nearest_act_without_document_default(self):
        rows,_=self.citations('「응급의료에 관한 법률」 제31조의4 및 동법 시행규칙 제18조의3제5항')
        self.assertTrue(any(r['target_name']=='응급의료에 관한 법률 시행규칙' and r['target_ref']=='제18조의3제5항' for r in rows))

    def test_unanchored_same_act_is_reported_not_guessed(self):
        rows,article=self.citations('동법 시행규칙 제18조의3제5항에 따른다.')
        self.assertFalse(rows)
        self.assertTrue(article['citation_issues'])
        rows,article=self.citations('제8조에 따른 기관. 동법 시행규칙 제18조의3제5항에 따른다.')
        self.assertFalse(any(r['target_ref']=='제18조의3제5항' for r in rows))
        self.assertTrue(article['citation_issues'])

    def document(self, dated=False):
        note='[제18조의3에서 이동, 종전 제18조의4는 제18조의5로 이동'+(' <2026. 6. 5.>' if dated else '')+']'
        return dict(name='응급의료에 관한 법률 시행규칙',category='medical',effective='20260814',
                    articles=[dict(jo='18의3',title='응급의료기관의 재지정 절차',text='현행 재지정 본문'),
                              dict(jo='18의4',title='응급환자의 중증도 분류',text='현행 분류 본문',reference_notes=[note])])

    def test_reused_number_is_review_without_silent_redirect(self):
        rule=dict(name='한국 응급환자 중증도 분류기준',provider='admrul',category='medical',citation_policy='mofe-explicit',effective='20240101')
        article=dict(jo='1',text='제1조(목적) 「응급의료에 관한 법률 시행규칙」 제18조의3에 따른다.')
        rows=adapter(rule,article,[self.document()])
        row=next(r for r in rows if r.get('target_ref')=='제18조의3')
        self.assertEqual(row['target_provision_status'],'renumbered-reference-review')
        self.assertTrue(row['context_review'])
        self.assertEqual(row['target_movement_candidates'][0]['ref'],'제18조의4')
        self.assertIn('자동 변경하지 않았습니다',row['target_reference_note'])
        self.assertNotIn('제18조의4',row['raw'])

    def test_known_newer_source_not_falsely_marked_but_undated_history_is_reviewed(self):
        wanted=parse_target('제18조의3')
        self.assertFalse(movement_review(self.document(True),wanted,'20260814'))
        self.assertTrue(movement_review(self.document(True),wanted,'20240101'))
        self.assertTrue(movement_review(self.document(),wanted,'20260814'))

    def test_multiple_moves_remain_candidates_and_do_not_match_unrelated_number(self):
        document=self.document()
        another=deepcopy(document['articles'][1]);another['jo']='20'
        document['articles'].append(another)
        result=movement_review(document,parse_target('제18조의3'),'20240101')
        self.assertEqual({r['ref'] for r in result['target_movement_candidates']},{'제18조의4','제20조'})
        self.assertFalse(movement_review(document,parse_target('제19조'),'20240101'))

    def test_administrative_annex_identity_links_and_body_are_separate(self):
        xml=ET.fromstring('<r><별표단위><별표구분>별표</별표구분><별표번호>000001</별표번호><별표가지번호>0</별표가지번호><별표제목>분류기준</별표제목><별표내용>본문 해석 금지</별표내용><별표서식PDF파일링크>/LSW/flDownload.do?flSeq=1</별표서식PDF파일링크><별표서식파일링크>https://example.com/unsafe</별표서식파일링크></별표단위></r>')
        annex=administrative_annexes(xml,'20240101')[0]
        self.assertEqual(annex['ref'],'별표 1')
        self.assertEqual(annex['urls'],['https://www.law.go.kr/LSW/flDownload.do?flSeq=1'])
        self.assertNotIn('text',annex)
        self.assertNotIn('body_analysis',annex)
        rule=dict(name='고시',effective='20240101',raw_body_blocks=['제1조(목적) 별표 1을 따른다.'],annexes=[annex])
        from core.fsc_administrative import index_rule
        self.assertEqual(index_rule(rule)['annexes'],[annex])
        keyed=ET.fromstring('<r><별표단위><별표번호>1</별표번호><별표서식파일링크>https://www.law.go.kr/LSW/flDownload.do?flSeq=1&amp;OC=fixture</별표서식파일링크></별표단위></r>')
        self.assertFalse(administrative_annexes(keyed,'20240101')[0]['urls'])


if __name__=='__main__':unittest.main()
