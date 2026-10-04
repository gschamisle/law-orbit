"""Human-audited tax relative references retain scope without inventing targets."""
import unittest
from copy import deepcopy

from core.citation_parser import parse_citations, effective_law_name
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




class SameParagraphAuditTests(unittest.TestCase):
    @staticmethod
    def relative(text):
        return next(c for c in parse_citations(text) if c.raw.startswith(('같은 항', '동항')))

    @staticmethod
    def graph(text, source_name='소득세법 시행령', jo='156의2'):
        label='제'+jo.replace('의','조의')+('' if '의' in jo else '조')
        source=dict(built_at='fixture',laws=[
            law(source_name,'tax',[article(jo,[(label,label+'(회귀표본)'),
                (label+'제11항',text)])])])
        for name in ['소득세법', '소득세법 시행령', '소득세법 시행규칙', '다른법']:
            if name != source_name:
                source['laws'].append(law(name,'tax',[article('155',[('제155조','제155조(표본)')])]))
        source['laws'][0]['articles'].append(article('155',[('제155조','제155조(표본)')]))
        return source,build_tax_universe(source)

    def test_two_manually_verified_housing_references(self):
        samples=[('156의2','제155조제7항의 규정에 따른 농어촌주택 중 동항제2호','동항제2호'),
                 ('156의3','제155조제7항에 따른 농어촌주택 중 같은 항 제2호','같은 항 제2호')]
        for jo,text,raw in samples:
            with self.subTest(jo=jo):
                cite=self.relative(text)
                self.assertEqual((cite.jo,cite.hang,cite.ho),('155','7','2'))
                self.assertEqual(text[slice(*cite.span)],raw)
                source,graph=self.graph(text,jo=jo)
                rows=[e for e in graph['edges'] if e['cite_raw']==raw]
                self.assertEqual([(e['target_law'],e['target_ref']) for e in rows],
                    [('소득세법 시행령','제155조제7항제2호')])
                body=source['laws'][0]['articles'][0]['text']
                self.assertEqual(body[rows[0]['source_start']:rows[0]['source_end']],raw)

    def test_deictic_and_named_owners_are_inherited(self):
        for prefix,wanted in [('법','소득세법'),('영','소득세법 시행령'),
                              ('이 규칙','소득세법 시행규칙'),('「다른법」','다른법')]:
            with self.subTest(prefix=prefix):
                text=prefix+' 제155조제7항에 따른 같은 항 제2호'
                cite=self.relative(text)
                self.assertEqual(effective_law_name(cite,'소득세법 시행규칙'),wanted)
                _,graph=self.graph(text,source_name='소득세법 시행규칙')
                self.assertEqual([(r['target_law'],r['target_ref']) for r in graph['edges'] if r['cite_raw']=='같은 항 제2호'],
                                 [(wanted,'제155조제7항제2호')])

    def test_nearest_explicit_paragraph_replaces_older_anchor(self):
        cite=self.relative('제155조제7항과 제160조제3항에 따른 같은 항 제2호')
        self.assertEqual((cite.jo,cite.hang,cite.ho),('160','3','2'))

    def test_missing_or_ambiguous_anchor_never_falls_back_to_source(self):
        texts=['같은 항 제2호에 따른 주택', '동항제2호에 따른 주택',
               '제155조에 따른 같은 항 제2호',
               '제155조제7항과 제160조에 따른 같은 항 제2호',
               '제155조제7항과 제8항에 따른 같은 항 제2호',
               '제155조제7항부터 제9항까지에 따른 같은 항 제2호',
               '같은 법 제155조제7항에 따른 같은 항 제2호',
               '제155조제7항과 「다른법」에 따른 같은 항 제2호']
        texts += ['제155조제7항에 따른다'+mark+' 같은 항 제2호' for mark in ['.', '?', '!', ';', '\n']]
        for text in texts:
            with self.subTest(text=text):
                cite=self.relative(text)
                self.assertEqual(cite.jo,'')
                _,graph=self.graph(text)
                self.assertFalse(any(e['cite_raw'].startswith(('같은 항','동항')) for e in graph['edges']+graph['external_references']))

    def test_closed_parenthetical_anchor_is_not_inherited_outside(self):
        for text in [
                '제155조제7항(제160조제3항에 따른 경우를 포함한다)에 따른 같은 항 제2호',
                '[제155조제7항(제160조제3항에 따른 경우를 포함한다)에 따른 같은 항 제2호]',
                '제155조제7항[제160조제3항에 따른 경우를 포함한다]에 따른 동항제2호']:
            with self.subTest(text=text):
                self.assertEqual(self.relative(text).jo,'')
                _,graph=self.graph(text)
                self.assertFalse(any(e['cite_raw'].startswith(('같은 항','동항')) for e in graph['edges']))
        inside='제155조제7항(제160조제3항에 따른 같은 항 제2호의 경우)'
        self.assertEqual((self.relative(inside).jo,self.relative(inside).hang),('160','3'))

    def test_closed_aside_law_name_does_not_replace_outer_paragraph(self):
        # VAT rule54(4): the telecom law only qualifies the business sites in an
        # already closed aside; the outer formula still belongs to decree81(3).
        text=('영 제81조제3항의 계산식에 따른 전 사업장의 총공급가액은 해당 과세기간의 모든 사업장'
              '(「전기통신사업법」에 따른 전기통신사업자의 경우에는 공통매입세액과 관련된 해당 과세기간의 모든 사업장)'
              '의 과세사업에 대한 공급가액과 면세사업등에 대한 수입금액의 합계액으로 하고, 같은 항의 계산식')
        cite=self.relative(text)
        self.assertEqual((cite.jo,cite.hang,cite.ho,cite.raw),('81','3','','같은 항'))
        self.assertEqual(effective_law_name(cite,'부가가치세법 시행규칙'),'부가가치세법 시행령')
        self.assertEqual(text[slice(*cite.span)],cite.raw)
        for changed in ['영 제81조제3항과 「전기통신사업법」에 따른 같은 항의 계산식',
                        '영 제81조제3항(「전기통신사업법」에 따른 같은 항의 계산식)']:
            with self.subTest(text=changed):
                self.assertEqual(self.relative(changed).jo,'')

    def test_standalone_mok_does_not_invent_a_parent_item(self):
        for tail in ['가목','제3목']:
            text='제155조제7항제1호에 따른 같은 항 '+tail
            cite=self.relative(text)
            self.assertEqual((cite.jo,cite.ho),('',''))
            self.assertEqual(text[slice(*cite.span)],'같은 항 '+tail)
            _,graph=self.graph(text)
            self.assertFalse(any(e['cite_raw'].startswith('같은 항') for e in graph['edges']))
        cite=self.relative('제155조제7항에 따른 같은 항 제2호가목')
        self.assertEqual((cite.jo,cite.hang,cite.ho,cite.mok),('155','7','2','가'))

    def test_item_range_is_preserved_for_scope_resolution(self):
        text='제155조제7항에 따른 같은 항 제1호부터 제3호까지'
        cite=self.relative(text)
        self.assertEqual((cite.jo,cite.hang,cite.ho),('155','7','1'))
        self.assertEqual(cite.raw,'같은 항 제1호')
        # The builder extends this exact source prefix through the range. Its
        # resolved_cite_raw must preserve the range for reverse detail matching.
        source,graph=self.graph(text)
        rows=[e for e in graph['edges'] if e['cite_raw'].startswith('같은 항')]
        self.assertEqual([(e['target_law'],e['target_ref'],e['cite_raw']) for e in rows],
                         [('소득세법 시행령','제155조제7항제1호','같은 항 제1호부터 제3호까지')])

    def test_word_suffix_is_not_a_relative_paragraph(self):
        self.assertFalse(any(c.raw.startswith('동항') for c in parse_citations('제155조제7항 동항목의 번호')))


    def test_bare_same_paragraph_formula_keeps_the_decree_owner(self):
        text='영 제81조제3항에 따른 금액은 같은 항의 계산식에 따른다'
        cite=self.relative(text)
        self.assertEqual((cite.jo,cite.hang,cite.ho,cite.raw),('81','3','','같은 항'))
        self.assertEqual(effective_law_name(cite,'소득세법 시행규칙'),'소득세법 시행령')
        for changed in ['영 제81조제3항에 따른다. 같은 항의 계산식',
                        '영 제81조제3항 및 법 제9조에 따른 같은 항의 계산식']:
            self.assertEqual(self.relative(changed).jo,'')


class OmittedJeParagraphAuditTests(unittest.TestCase):
    def test_official_corporate_rule49_literal_keeps_paragraph(self):
        # Same-edition official XML: MST287787 / 20260701, jo49 hang3.
        text='이 경우 자산은 영 제95조1항 각호의 자산에 한한다.'
        cite=next(c for c in parse_citations(text) if c.jo=='95')
        self.assertEqual((cite.hang,cite.ho),('1',''))
        self.assertEqual(effective_law_name(cite,'법인세법 시행규칙'),'법인세법 시행령')
        self.assertEqual(cite.raw,'영 제95조1항')
        self.assertEqual(text[slice(*cite.span)],cite.raw)

    def test_only_missing_je_immediately_after_article_is_allowed(self):
        for prefix in ['', '법 ', '같은 법 ', '「법인세법」 ', '법인세법 ']:
            with self.subTest(prefix=prefix):
                old=parse_citations(prefix+'제95조제1항')[0]
                new=parse_citations(prefix+'제95조1항')[0]
                self.assertEqual((old.jo,old.hang),(new.jo,new.hang))
                self.assertEqual((old.law_name,old.relative),(new.law_name,new.relative))
        for text in ['제95조의21항','제95조 1항','제95조 중 1항']:
            with self.subTest(text=text):
                self.assertFalse(any(c.hang=='1' for c in parse_citations(text)))
        self.assertFalse(parse_citations('1항의 대상'))


class HistoricalAndTableQualifierAuditTests(unittest.TestCase):
    def test_historical_owner_and_editions_survive_bracketed_enumeration(self):
        samples=[('법인세법','법률 제9898호 법인세법 일부개정법률','제44조 및 제46조',['44','46']),
                 ('법인세법 시행령','대통령령 제22184호 법인세법 시행령 일부개정령',
                  '제80조, 제82조, 제83조 및 제83조의2',['80','82','83','83의2'])]
        for owner,bill,refs,wanted in samples:
            qualifier='('+bill+'로 개정되기 전의 것을 말한다)'
            text='양도차익[「'+owner+'」'+qualifier+' '+refs+'에 따른 차익을 포함한다]'
            with self.subTest(owner=owner):
                citations=[c for c in parse_citations(text) if c.jo]
                self.assertEqual([c.jo+('의'+c.jo_sub if c.jo_sub else '') for c in citations],wanted)
                self.assertTrue(all(c.law_name==owner and c.edition_qualifier==qualifier for c in citations))
                for cite in citations:self.assertEqual(text[slice(*cite.span)],cite.raw)
                self.assertIn(qualifier,citations[0].raw)

    def test_historical_editions_do_not_escape_the_quoted_exception(self):
        historical='「법인세법」(법률 제9898호 법인세법 일부개정법률로 개정되기 전의 것을 말한다) 제44조'
        for text in ['['+historical+'] 및 제46조',historical+'에 따른 세액과 제46조']:
            with self.subTest(text=text):
                last=next(c for c in parse_citations(text) if c.jo=='46')
                self.assertEqual(last.edition_qualifier,'')
                self.assertEqual(last.law_name,'')
        arbitrary='「법인세법」(다른 조건에 해당하는 경우를 말한다) 제44조'
        self.assertFalse(any(c.edition_qualifier for c in parse_citations(arbitrary)))

    def test_table_item_qualifier_carries_only_the_decree_owner(self):
        text='영 제90조제3항의 표 제9호 및 제91조제2항의 표 제12호'
        citations=[c for c in parse_citations(text) if c.jo]
        self.assertEqual([(c.jo,c.hang,c.ho) for c in citations],[('90','3',''),('91','2','')])
        self.assertEqual([effective_law_name(c,'부가가치세법 시행규칙') for c in citations],
                         ['부가가치세법 시행령','부가가치세법 시행령'])
        self.assertEqual(citations[1].raw,'제91조제2항')
        for gap in ['의 표 제9호에 따른 사업과 ', '의 표 제9호. 및 ', '의 다른 표 제9호 및 ']:
            changed='영 제90조제3항'+gap+'제91조제2항'
            last=next(c for c in parse_citations(changed) if c.jo=='91')
            self.assertEqual(last.law_name,'',gap)


class WrappedFormulaLawAuditTests(unittest.TestCase):
    @staticmethod
    def formula(raw='「사회적기업  │\n│육성법」 제2조제1호'):
        return '제24조(기부금)\n┌────────┐\n│비율 '+raw+'에 따른 비율│\n└────────┘'

    def test_verified_single_box_wrap_preserves_source_and_exact_item(self):
        text=self.formula(); cite=next(c for c in parse_citations(text) if c.raw.startswith('「사회적기업'))
        self.assertEqual((cite.law_name,cite.jo,cite.hang,cite.ho),('사회적기업 육성법','2','','1'))
        self.assertEqual(cite.raw,'「사회적기업  │\n│육성법」 제2조제1호')
        self.assertEqual(text[slice(*cite.span)],cite.raw)
        source=dict(built_at='fixture',laws=[law('법인세법','tax',[article('24',[('제24조',text)])])])
        graph=build_tax_universe(source)
        rows=[r for r in graph['external_references'] if r['target_law']=='사회적기업 육성법']
        self.assertEqual([(r['target_ref'],r['cite_raw'],r['target_status']) for r in rows],
                         [('제2조제1호',cite.raw,'not-collected')])
        self.assertFalse(any('사회적기업' in i.get('raw','') for i in graph.get('citation_issues',[])))

    def test_ambiguous_cell_boundaries_remain_issues(self):
        normal=self.formula()
        texts=[normal.replace('│비율','│다른 셀│비율'),
               normal.replace('기업  │\n│육성','기업  ││\n│육성'),
               normal.replace('기업  │\n│육성','기업  │\n│육성 │\n│지원'),
               normal.replace('┌────────┐\n',''),
               normal.replace('기업  │\n│육성','기업 「다른법」 │\n│육성')]
        for text in texts:
            with self.subTest(text=text):
                source=dict(built_at='fixture',laws=[law('법인세법','tax',[article('24',[('제24조',text)])])])
                graph=build_tax_universe(source)
                self.assertFalse(any(r['target_law']=='사회적기업 육성법' for r in graph['edges']+graph['external_references']))
                self.assertTrue(graph.get('citation_issues'))


if __name__=='__main__':unittest.main()
