"""Ownership boundaries: enumerations versus prose and parenthetical clauses."""
import unittest

from core.citation_ownership import joined_owner
from core.fsc_administrative import adapter


class CitationOwnershipTests(unittest.TestCase):
    def test_noun_enumerations_and_balanced_labels_survive(self):
        for gap in (' 및 ', ', ', '에 따른 허가 및 ', '(허가) 또는 ',
                    '에 의한 허가와 신고 및 '):
            with self.subTest(gap=gap):
                self.assertTrue(joined_owner(gap))

    def test_clauses_and_bracket_boundaries_do_not_inherit(self):
        for gap in ('에 따른 법인을 말하며, ', '에 따른 자를 포함하고, ',
                    '에 따른 경우에는, ', '에 따른 외국법인) 및 ',
                    '에 따른 법인(이하 회사 및 ',
                    '에 따른 내국법인 및 같은 조 제3호에 따른 외국법인을 말하며, ',
                    '에 따른 허가. 및 ', ' 및\n', '에 따른 허가; 또는 '):
            with self.subTest(gap=gap):
                self.assertFalse(joined_owner(gap))

    def rows(self, text):
        law = dict(name='지방세기본법', citation_policy='mofe-explicit', aliases={})
        article = dict(jo='93의2', text=text)
        return adapter(law, article, []), article

    def test_local_tax_93_2_keeps_153_in_local_tax(self):
        text = ('제93조의2(선정 대리인) 법인(「법인세법」 제2조제1호에 따른 내국법인 및 '
                '같은 조 제3호에 따른 외국법인을 말하며, 제153조에 따라 준용되는 '
                '「국세기본법」 제13조에 따라 법인으로 보는 단체를 포함한다)인 경우: '
                '「법인세법」 제43조의 기업회계기준')
        rows, article = self.rows(text)
        hit = next(r for r in rows if r.get('target_ref') == '제153조')
        self.assertEqual(hit['target_name'], '지방세기본법')
        self.assertEqual(text[hit['start']:hit['end']], hit['raw'])
        self.assertEqual(hit['raw'], '제153조')
        self.assertTrue(any(r['target_name'] == '법인세법' and r['target_ref'] == '제43조' for r in rows))
        # Unresolved relative articles remain visible for review, not silently guessed.
        self.assertTrue(any('상대 조문' in r['reason'] for r in article['citation_issues']))

    def test_omitted_owner_enumeration_and_parenthetical_return(self):
        rows, _ = self.rows('제1조(예시) 「다른법」 제2조에 따른 허가 및 제3조에 따른 신고')
        hit = next(r for r in rows if r['target_ref'] == '제3조')
        self.assertEqual(hit['target_name'], '다른법')
        self.assertTrue(hit['context_review'])
        rows, _ = self.rows('제1조(예시) 법인(「다른법」 제2조에 따른 법인) 및 제3조에 따른 기관')
        self.assertEqual(next(r for r in rows if r['target_ref'] == '제3조')['target_name'], '지방세기본법')

    def test_outer_enumeration_resumes_after_nested_foreign_law(self):
        text = ('제1조(예시) 「독립유공자예우에 관한 법률」 제15조제3항('
                '「국가유공자 등 예우 및 지원에 관한 법률」의 준용규정 중 같은 법 제26조제1항에 따른 권한에 한정한다), '
                '제16조제4항 및 제17조에 따른 권한')
        rows, _ = self.rows(text)
        self.assertEqual(next(r for r in rows if r['target_ref'] == '제26조제1항')['target_name'], '국가유공자 등 예우 및 지원에 관한 법률')
        for ref in ('제16조제4항', '제17조'):
            self.assertEqual(next(r for r in rows if r['target_ref'] == ref)['target_name'], '독립유공자예우에 관한 법률')

    def test_local_definition_does_not_destroy_outer_same_law_anchor(self):
        text = ('제43조(예시) 「해외자원개발 사업법」 제2조제5호에 따른 해외자원개발사업자'
                '(이하 이 항 및 제44조제7항에서 "사업자"라 한다)가 같은 법 제3조제1호에 따른 방법')
        rows, _ = self.rows(text)
        self.assertEqual(next(r for r in rows if r['target_ref'] == '제44조제7항')['target_name'], '지방세기본법')
        self.assertEqual(next(r for r in rows if r['target_ref'] == '제3조제1호')['target_name'], '해외자원개발 사업법')

    def test_same_law_prefers_nearby_law_only_anchor_even_inside_bracket(self):
        rows, _ = self.rows('제1조(예시) 「상법」 제5조에 따른 자 및 「특정법」에 따른 사업자(같은 법 제7조에 따라 신고된 자)')
        self.assertEqual(next(r for r in rows if r['target_ref'] == '제7조')['target_name'], '특정법')
        rows, _ = self.rows('제1조(예시) 「다른법」 제2조의 기업집단(「특정법 시행령」 제4조에 따른 범위를 말한다)에 속하였으나 같은 법 시행령 제5조에 따라 제외된 회사')
        self.assertEqual(next(r for r in rows if r['target_ref'] == '제5조')['target_name'], '특정법 시행령')

    def test_relative_paragraph_list_keeps_outer_owner(self):
        rows, _ = self.rows('제1조(예시) 「대기환경보전법」 제82조제1항(같은 법 제16조에 따른 검사에 한정한다)ㆍ제2항, 제85조에 따른 권한')
        self.assertEqual(next(r for r in rows if r['target_ref'] == '제85조')['target_name'], '대기환경보전법')
        rows, _ = self.rows('제1조(예시) 「지원법」 제4조제1항부터 제3항까지, 같은 조 제5항부터 제7항까지, 제4조의2 및 제6조')
        self.assertEqual(next(r for r in rows if r['target_ref'] == '제4조의2')['target_name'], '지원법')

    def test_noun_qualifier_is_not_an_article_title(self):
        rows, _ = self.rows('제1조(예시) 「건축법」 제2조제2항제2호의 공동주택(아파트는 제외한다. 이하 같다)과 제251조제1항에 따른 시설')
        self.assertEqual(next(r for r in rows if r['target_ref'] == '제251조제1항')['target_name'], '지방세기본법')


if __name__ == '__main__':
    unittest.main()
