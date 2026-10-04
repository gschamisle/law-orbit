"""Exact source repairs preserve editions, offsets and unrelated texts."""
from copy import deepcopy
import unittest
import xml.etree.ElementTree as ET

from core.tax_source_repairs import apply_repairs, digest
from core.universe_builder import build_tax_universe
from scripts.collect_law_universe import parse_body
from scripts.test_law_universe import article,law


class SourceRepairTests(unittest.TestCase):
    def fixture(self):
        source=dict(laws=[dict(name='검증법',mst='123',effective='20261001',articles=[dict(jo='1',title='계산',effective='20261001',text='제1조\nA - B\n제2항',blocks=[dict(start=0,end=3,text='제1조',ref='제1조'),dict(start=4,end=9,text='A - B',ref='제1조제1항'),dict(start=10,end=13,text='제2항',ref='제1조제2항')])])])
        plan=dict(schema=1,body_edits=[dict(law='검증법',jo='1',mst='123',effective='20261001',start=6,end=8,before='- ',after='×',before_sha256=digest('제1조\nA - B\n제2항'),after_sha256=digest('제1조\nA ×B\n제2항'),official_url='https://www.law.go.kr/')])
        return source,plan

    def test_verified_body_edit_keeps_input_and_adjusts_following_offsets(self):
        source,plan=self.fixture();prior=deepcopy(source)
        fixed,changes=apply_repairs(source,plan)
        self.assertEqual(source,prior)
        a=fixed['laws'][0]['articles'][0]
        self.assertEqual(a['text'],'제1조\nA ×B\n제2항')
        self.assertEqual([(b['start'],b['end'],b['text']) for b in a['blocks']],[(0,3,'제1조'),(4,8,'A ×B'),(9,12,'제2항')])
        self.assertEqual(fixed['laws'][0]['mst'],'123')
        self.assertEqual(len(changes),1)

    def test_wrong_edition_and_hash_are_rejected(self):
        for key,value in [('mst','124'),('effective','20261002'),('before_sha256','0'*64),('after_sha256','0'*64),('before','+ ')]:
            with self.subTest(key=key):
                source,plan=self.fixture();plan['body_edits'][0][key]=value
                with self.assertRaises(ValueError):apply_repairs(source,plan)

    def test_cross_block_repair_is_rejected(self):
        source,plan=self.fixture();edit=plan['body_edits'][0]
        edit.update(start=2,end=6,before=source['laws'][0]['articles'][0]['text'][2:6],after='')
        edit['after_sha256']=digest('제1- B\n제2항')
        with self.assertRaises(ValueError):apply_repairs(source,plan)

    def test_official_remarks_stay_outside_operative_text_and_graph(self):
        root=ET.fromstring('<법령><기본정보><법령명_한글>검증법</법령명_한글><시행일자>20261001</시행일자></기본정보><조문><조문단위><조문여부>조문</조문여부><조문번호>1</조문번호><조문내용>제1조(검증)</조문내용><조문참고자료>[시행일: 2027.1.1] 제1조(제20조제27호에 관한 부분)</조문참고자료></조문단위></조문></법령>')
        parsed=parse_body(root,dict(name='검증법',category='tax'))
        a=parsed['articles'][0]
        self.assertEqual(a['text'],'제1조(검증)')
        self.assertIn('2027.1.1',a['reference_notes'][0])
        graph=build_tax_universe(dict(built_at='fixture',laws=[parsed]))
        self.assertEqual(graph['edges'],[])

    def test_partial_commencement_note_travels_with_real_citation(self):
        a=article('14',[('제14조','제14조(과세)'),('제14조제3항','제21조제1항제27호에 따른 소득')])
        a['reference_notes']=['[시행일: 2027.1.1] 제14조제3항(제21조제1항제27호에 관한 부분)']
        source=dict(built_at='fixture',laws=[law('소득세법','tax',[a,article('21',[('제21조','제21조(기타소득)')])])])
        rows=build_tax_universe(source)['edges']
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['source_reference_notes'],a['reference_notes'])
        self.assertEqual(rows[0]['cite_raw'],'제21조제1항제27호')


class SourceContextIntegrationTests(unittest.TestCase):
    def test_definition_range_keeps_exception_review_and_source_quote(self):
        text='① 이 조부터 제3조까지 적용하되 다음의 경우는 제외한다.'
        src=dict(built_at='fixture',laws=[law('검증법','tax',[
            article('1',[('제1조제1항',text)]),
            article('2',[('제2조','제2조(중간)')]),article('3',[('제3조','제3조(끝)')])])])
        rows=build_tax_universe(src)['edges']
        self.assertEqual({r['target_ref'] for r in rows},{'제1조','제2조','제3조'})
        self.assertTrue(all(r['context_review'] for r in rows))
        self.assertTrue(all(r['cite_raw']=='이 조부터 제3조까지' for r in rows))

    def test_official_omitted_paragraph_marker_preserves_actual_source_span(self):
        text='① 영 제95조1항 각호의 자산에 한한다.'
        src=dict(built_at='fixture',laws=[law('법인세법 시행규칙','tax',[article('49',[('제49조제1항',text)])]),
            law('법인세법 시행령','tax',[article('95',[('제95조','제95조(검증)')])])])
        rows=build_tax_universe(src)['edges']
        self.assertEqual(len(rows),1)
        r=rows[0]
        self.assertEqual(r['target_ref'],'제95조제1항')
        self.assertEqual(r['cite_raw'],'영 제95조1항')
        self.assertEqual(text[r['source_start']:r['source_end']],r['cite_raw'])
        self.assertEqual(r['resolved_cite_raw'],'영 제95조제1항')

    def test_renamed_law_identity_never_remaps_historical_article_numbers(self):
        old='주식회사의 외부감사에 관한 법률';current='주식회사 등의 외부감사에 관한 법률'
        text='① 「'+old+'」에 따른 감사. 「'+old+'」 제2조에 따른 대상.'
        src=dict(built_at='fixture',laws=[law('국세기본법','tax',[article('81의6',[('제81조의6제1항',text)])]),
            law(current,'external',[article('2',[('제2조','제2조(정의)')])])])
        graph=build_tax_universe(src)
        identity=next(r for r in graph['edges'] if r['target_kind']=='law')
        self.assertEqual(identity['target_law'],current)
        self.assertEqual(identity['target_name_original'],old)
        self.assertIn(old,identity['cite_raw'])
        numbered=next(r for r in graph['external_references'] if r['target_kind']=='article')
        self.assertEqual(numbered['target_law'],old)
        self.assertNotIn('target_name_original',numbered)


if __name__=='__main__':unittest.main()
