"""Regression tests for the former-last-paragraph hypothesis and bounded evidence."""
from __future__ import annotations

import unittest

from core.article_structure import compare_articles, parse_article
from core.boundary_review import example_result, review_append
from core.impact_galaxy import build


def article(n=4, reference='제2조'):
    return reference + '(대상)\n' + '\n'.join(f'제{i}항 대상 {i}에 관한 내용이다.' for i in range(1, n + 1))


def graph_for(raw, **override):
    edge = dict(source_law='B법', source_jo='7', source_title='적용 대상', target_law='A법', target_ref='제2조', cite_raw=raw)
    edge.update(override)
    return dict(laws=['A법', 'B법'], built_at='테스트 자료', edges=[edge])


class StructureTests(unittest.TestCase):
    def test_formats_offsets_and_provenance(self):
        snap = parse_article('제2조(제목) ① 내용 하나\r\n② 내용 둘', '제2조', '2026-01-01')
        self.assertEqual([p.number for p in snap.paragraphs], [1, 2])
        for paragraph in snap.paragraphs:
            self.assertIn(paragraph.text, snap.text[paragraph.start:paragraph.end])
        self.assertEqual(snap.version, '2026-01-01')
        self.assertEqual(len(snap.sha256), 64)
        self.assertEqual(parse_article(article(5), '제2조', '안').paragraphs[-1].number, 5)
        self.assertEqual(parse_article(article(2, '제2조의2'), '제2조의2', '안').article, '제2조의2')

    def test_reject_partial_or_wrong_article(self):
        invalid = ['제2조(제목)\n② 내용\n③ 내용', '제3조(제목)\n① 내용', '제2조(제목)\n① 내용\n① 중복',
                   '제2조(제목)\n① 내용\n③ 건너뜀', '제2조제5항을 다음과 같이 신설한다.',
                   '제2조(제목)\n① 내용 ② 내용', '제2조(제목)\n①',
                   '제2조(제목)\n① 내용\n제3조(다음)\n① 내용']
        for text in invalid:
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_article(text, '제2조', '테스트')
        with self.assertRaises(ValueError):
            parse_article(article(), '제2조제1항', '테스트')

    def test_addition_and_complex_changes(self):
        before = parse_article(article(), '제2조', '전')
        appended = compare_articles(before, parse_article(article(6), '제2조', '후'))
        self.assertEqual((appended['kind'], appended['added'], appended['former_last']), ('append', [5, 6], 4))
        self.assertEqual(compare_articles(before, before)['kind'], 'none')
        for after_text in (article(5).replace('대상 2에 관한 내용이다.', '삭제'),
                           article(5).replace('대상 2에 관한 내용이다.', '번호가 이동한 내용이다.'), article(3)):
            with self.subTest(after=after_text):
                self.assertEqual(compare_articles(before, parse_article(after_text, '제2조', '후'))['kind'], 'complex')
        spaced = article(5).replace('대상 2에', '대상\n  2에')
        self.assertEqual(compare_articles(before, parse_article(spaced, '제2조', '후'))['kind'], 'append')


class BoundaryTests(unittest.TestCase):
    def run_case(self, raw, old=4, new=5, **override):
        return review_append('A법', '제2조', article(old), article(new), graph_for(raw, **override))

    def test_ranges_enumeration_and_priorities(self):
        for raw in ('제2조제2항부터 제4항까지', '제2조제2항 내지 제4항', '제2조제2항~제4항',
                    '제2조제2항·제3항 및 제4항', '제2조제2항, 제3항 및 제4항'):
            with self.subTest(raw=raw):
                row = self.run_case(raw)['rows'][0]
                self.assertEqual((row['status'], row['priority'], row['pattern']), ('scope_review', '우선 검토', 'tail'))
                self.assertEqual(row['cited_paragraphs'], [2, 3, 4])
                self.assertEqual(row['excluded_before'], [1])
                self.assertEqual(row['added_paragraphs'], [5])
                self.assertIn('제5항', row['question'])
        all_row = self.run_case('제2조제1항부터 제4항까지')['rows'][0]
        self.assertEqual(all_row['pattern'], 'all')
        row = self.run_case('제2조제2항 및 제4항')['rows'][0]
        self.assertEqual((row['status'], row['priority'], row['pattern']), ('scope_review', '일반 검토', 'enumeration'))

    def test_negative_boundaries(self):
        for raw, old, new in [('제2조제2항부터 제3항까지', 4, 5), ('제2조제4항', 4, 5),
                              ('제2조제2항부터 제4항까지', 5, 6), ('제2조제2항부터 제4항까지', 4, 4)]:
            with self.subTest(raw=raw, old=old, new=new):
                self.assertEqual(self.run_case(raw, old, new)['rows'][0]['status'], 'not_boundary')
        for raw in ('제2조', '제1조부터 제3조까지'):
            self.assertEqual(self.run_case(raw)['rows'][0]['status'], 'covered')

    def test_ambiguous_and_incompatible_evidence(self):
        cases = ['제2조제2항부터 제4항까지(제3항은 제외한다)', '같은 조 제2항부터 제4항까지',
                 '제2조제4항제1호', '제2조제1호', '제2조제2항부터 제6항까지', '제2조제4항부터 제2항까지',
                 '제2조제2항부터 제4항까지에 한정한다']
        for raw in cases:
            with self.subTest(raw=raw):
                self.assertEqual(self.run_case(raw)['rows'][0]['status'], 'review')
        result = self.run_case('제2조제2항부터 제4항까지', source_law='A법', source_jo='2')
        self.assertEqual(result['rows'][0]['status'], 'review')
        self.assertFalse(build(result)['links'])

    def test_complex_amendment_never_emits_simple_boundary_alert(self):
        before, after = article(), article(5).replace('대상 2에 관한 내용이다.', '삭제')
        result = review_append('A법', '제2조', before, after, graph_for('제2조제2항부터 제4항까지'))
        self.assertNotIn('scope_review', result['counts'])
        self.assertEqual(result['change']['kind'], 'complex')
        before = article().replace('대상 2에 관한 내용이다.', '삭제')
        result = review_append('A법', '제2조', before, before + '\n제5항 신규 내용', graph_for('제2조제2항부터 제4항까지'))
        self.assertEqual(result['rows'][0]['status'], 'review')

    def test_bounded_candidates_dedup_and_evidence_graph(self):
        graph = graph_for('제2조제2항부터 제4항까지')
        edge = graph['edges'][0]
        graph['edges'] += [dict(edge), dict(edge, target_law='다른법'), dict(edge, target_ref='제3조', cite_raw='제3조제2항부터 제4항까지'),
                           dict(edge, cite_raw='제2조')]
        result = review_append('A법', '제2조', article(), article(5), graph)
        self.assertEqual(result['candidate_count'], 2)
        self.assertEqual(result['candidate_article_count'], 1)
        galaxy = build(result)
        self.assertEqual(len(galaxy['links']), 2)
        self.assertEqual({l['status']: l['dashed'] for l in galaxy['links']}, {'scope_review': True, 'covered': False})
        self.assertEqual(sum(l['n'] for l in galaxy['links']), sum(len(n['evidence']) for n in galaxy['nodes']))
        self.assertEqual(galaxy, build(result))

    def test_fictional_example_is_labelled_and_expected(self):
        result = example_result()
        self.assertTrue(result['example'])
        self.assertEqual(result['counts'], {'scope_review': 2, 'review': 1, 'covered': 1, 'not_boundary': 1})
        self.assertTrue(build(result)['example'])


if __name__ == '__main__':
    unittest.main()
