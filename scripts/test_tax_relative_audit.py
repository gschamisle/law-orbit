"""Human-audited tax relative references retain scope without inventing targets."""
import unittest
from copy import deepcopy

from core.universe_builder import build_tax_universe
from core.galaxy_focus import analyze_focus
from scripts.build_static_galaxies import EdgeIndex, tidy
from scripts.test_law_universe import article, law


class TaxRelativeAuditTests(unittest.TestCase):
    def test_relative_article_keeps_both_paragraphs_and_original_source_quote(self):
        raw = '「부가가치세법」 제60조제2항 및 같은 조 제3항 및 제4항에 따른 가산세'
        source = dict(built_at='fixture',laws=[law('국세기본법','tax',[article('26의2',[
            ('제26조의2','제26조의2(국세의 부과제척기간)'),('제26조의2제2항제3호다목','다. '+raw)])]),
            law('부가가치세법','tax',[article('60',[('제60조','제60조(가산세)')])])])
        original=deepcopy(source)
        graph = build_tax_universe(source)
        self.assertEqual(source,original)
        relative = [e for e in graph['edges'] if e['cite_raw']=='같은 조 제3항 및 제4항']
        self.assertEqual({e['target_ref'] for e in relative},{'제60조제3항','제60조제4항'})
        self.assertTrue(all(e['target_law']=='부가가치세법' for e in relative))
        self.assertTrue(all(e['resolved_cite_raw']=='제60조제3항 및 제4항' for e in relative))
        text=source['laws'][0]['articles'][0]['text']
        self.assertTrue(all(text[e['source_start']:e['source_end']]==e['cite_raw'] for e in relative))
        index=EdgeIndex(graph,source['laws'])
        row=next(r for r in index.focus('부가가치세법','제60조제4항')['rows'] if r['raw'].startswith('같은 조'))
        exported=tidy(row,{},False)
        self.assertEqual([s[0][1] for s in exported['raw_scope']['scopes']],['3','4'])
        self.assertEqual(exported['raw'],'같은 조 제3항 및 제4항')
        self.assertEqual(exported['status'],'review')
        fifth=index.focus('부가가치세법','제60조제5항')['rows']
        self.assertFalse(any(r['raw'].startswith('같은 조') for r in fifth))

    def test_relative_law_without_number_uses_preceding_anchor_only(self):
        target='특정 금융거래정보의 보고 및 이용 등에 관한 법률'
        text=f'「{target}」 제2조에 따른 금융회사와 같은 법에 따른 가상자산사업자'
        source=dict(built_at='fixture',laws=[law('국세기본법','tax',[article('26의2',[
            ('제26조의2','제26조의2(국세의 부과제척기간)'),('제26조의2제5항제8호','8. '+text)])])])
        graph=build_tax_universe(source)
        rows=[e for e in graph['external_references'] if e['cite_raw']=='같은 법']
        self.assertEqual([(e['target_law'],e['target_kind'],e['target_ref']) for e in rows],[(target,'law','법령·정의 참조')])
        self.assertTrue(rows[0]['context_review'])
        self.assertEqual(rows[0]['target_status'],'not-collected')
        self.assertFalse(any(e['target_kind']=='article' and e['cite_raw']=='같은 법' for e in graph['edges']))

    def test_relative_law_is_not_reassigned_to_later_named_statute(self):
        source=dict(built_at='fixture',laws=[law('국세기본법','tax',[article('47의2',[
            ('제47조의2','제47조의2(무신고가산세)'),
            ('제47조의2제2항제2호','2. 「부가가치세법」 제49조에 따른 신고와 같은 법 또는 「조세특례제한법」에 따른 공제')])])])
        graph=build_tax_universe(source)
        relative=[e for e in graph['external_references'] if e['cite_raw']=='같은 법']
        self.assertEqual([e['target_law'] for e in relative],['부가가치세법'])

    def test_no_anchor_or_different_paragraph_does_not_invent_source_law(self):
        for text in ('같은 법에 따른 기관','「부가가치세법」에 따른 기관\n같은 법에 따른 사업자',
                     '「부가가치세법」에 따른 사업자와 같은 법인'):
            source=dict(built_at='fixture',laws=[law('국세기본법','tax',[article('14',[
                ('제14조','제14조(실질과세)'),('제14조제1항',text)])])])
            graph=build_tax_universe(source)
            self.assertFalse(any(e['cite_raw']=='같은 법' for e in graph['edges']+graph['external_references']))

    def test_relative_law_with_a_number_does_not_also_add_a_law_reference(self):
        source=dict(built_at='fixture',laws=[law('국세기본법','tax',[article('14',[
            ('제14조','제14조(실질과세)'),
            ('제14조제1항','「부가가치세법」 제49조와 같은 법 제60조에 따른 신고')])])])
        graph=build_tax_universe(source)
        rows=graph['edges']+graph['external_references']
        self.assertEqual([(e['target_law'],e['target_ref'],e['target_kind']) for e in rows],
                         [('부가가치세법','제49조','article'),('부가가치세법','제60조','article')])
        self.assertFalse(any(e['cite_raw']=='같은 법' for e in rows))

    def test_relative_law_suffixes_do_not_create_a_parent_law_reference(self):
        # '같은 법 시행령' designates the decree, not another reference to the law.
        # Annex references already have their own parser and must not be doubled.
        for suffix in ('시행령에 따른 기관','시행규칙에서 정하는 사항',
                       '시행령 제3조에 따른 기관','시행규칙 제4조에 따른 서류',
                       '별표 1에 따른 기관','별지 제2호서식'):
            with self.subTest(suffix=suffix):
                source=dict(built_at='fixture',laws=[law('국세기본법','tax',[article('14',[
                    ('제14조','제14조(실질과세)'),
                    ('제14조제1항','「부가가치세법」에 따른 사업자와 같은 법 '+suffix)])])])
                graph=build_tax_universe(source)
                rows=graph['edges']+graph['external_references']
                self.assertFalse(any(e['cite_raw']=='같은 법' for e in rows))
                law_rows=[e for e in rows if e['target_kind']=='law']
                self.assertEqual([e['cite_raw'] for e in law_rows],['「부가가치세법」'])

    def test_relative_article_with_deictic_anchor_keeps_owner_and_source(self):
        text='법 제60조제2항 및 같은 조 제3항 및 제4항에 따른 신고'
        source=dict(built_at='fixture',laws=[
            law('법인세법 시행령','tax',[article('97',[
                ('제97조','제97조(신고)'),('제97조제1항',text)])]),
            law('법인세법','tax',[article('60',[('제60조','제60조(신고)')])])])
        graph=build_tax_universe(source)
        rows=[e for e in graph['edges'] if e['cite_raw'].startswith('같은 조')]
        self.assertEqual({(e['target_law'],e['target_ref']) for e in rows},
                         {('법인세법','제60조제3항'),('법인세법','제60조제4항')})
        original=source['laws'][0]['articles'][0]['text']
        for row in rows:
            self.assertEqual(original[row['source_start']:row['source_end']],row['cite_raw'])
            self.assertEqual(row['resolved_cite_raw'],'제60조제3항 및 제4항')

    def test_unanchored_relative_article_does_not_invent_article_number(self):
        for text in ('같은 조 제3항 및 제4항에 따른 신고',
                     '「부가가치세법」 제60조에 따른 기관. 같은 조 제3항에 따른 신고'):
            with self.subTest(text=text):
                source=dict(built_at='fixture',laws=[law('국세기본법','tax',[article('14',[
                    ('제14조','제14조(실질과세)'),('제14조제1항',text)])])])
                graph=build_tax_universe(source)
                rows=graph['edges']+graph['external_references']
                self.assertFalse(any(e['cite_raw'].startswith('같은 조') for e in rows))


if __name__=='__main__':unittest.main()
