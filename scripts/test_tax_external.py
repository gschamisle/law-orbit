"""Tax missing-law evidence survives source parsing and public export."""
from copy import deepcopy
import unittest

from core.universe_builder import build_tax_universe, build_universe
from scripts.build_static_galaxies import EdgeIndex, export_documents
from scripts.test_law_universe import article, law


def fixture():
    return dict(built_at='20260928', laws=[
        law('법인세법', 'tax', [
            article('16', [
                ('제16조', '제16조(배당금 또는 분배금의 의제)'),
                ('제16조제1항제2호가목', '가. 「상법」 제459조제1항에 따른 자본준비금'),
                ('제16조제1항제2호나목', '나. 「자산재평가법」에 따른 재평가적립금(같은 법 제13조제1항제1호에 따른 토지의 재평가차액에 상당하는 금액은 제외한다)'),
            ]),
            article('63', [
                ('제63조', '제63조(중간예납 의무)'),
                ('제63조제1항제1호가목', '가. 「고등교육법」 제3조에 따른 사립학교를 경영하는 학교법인'),
                ('제63조제1항제1호나목', '나. 「국립대학법인 서울대학교 설립ㆍ운영에 관한 법률」에 따른 국립대학법인 서울대학교'),
                ('제63조제1항제1호마목', '마. 「초ㆍ중등교육법」 제3조제3호에 따른 사립학교를 경영하는 학교법인'),
                ('제63조제4항', '④ 제64조제2항을 준용한다.'),
            ]),
            article('64', [('제64조', '제64조(검증) 한국표준산업분류 및 기업회계기준에 따른다.')]),
        ]),
        law('상법', 'external', [
            article('459', [('제459조', '제459조(검증) 「미수집외부법」 제7조를 적용한다.')]),
        ]),
    ])


class MemoryWriter:
    """Exercise the real exporter without writing a release or temp files."""
    def __init__(self):
        self.values = []

    def data(self, value):
        self.values.append(value)
        return {'index': len(self.values) - 1}


class TaxExternalTests(unittest.TestCase):
    def test_opt_in_preserves_existing_edges_catalog_and_source(self):
        source = fixture()
        original = deepcopy(source)
        old = build_universe(source)
        graph = build_tax_universe(source)
        self.assertEqual(source, original)
        self.assertNotIn('external_references', old)
        for key in ('edges', 'catalog', 'laws', 'tax_laws', 'relation_counts'):
            self.assertEqual(graph[key], old[key], key)
        self.assertEqual(sum(e['target_kind'] == 'standard' for e in graph['edges']), 2)
        self.assertFalse(any(e['target_kind'] == 'standard' for e in graph['external_references']))

    def test_real_reference_patterns_keep_owner_scope_and_original_span(self):
        source = fixture()
        graph = build_tax_universe(source)
        rows = graph['external_references']
        expected = {
            ('16', '제16조제1항제2호나목', '자산재평가법', '제13조제1항제1호', '같은 법 제13조제1항제1호'),
            ('63', '제63조제1항제1호가목', '고등교육법', '제3조', '「고등교육법」 제3조'),
            ('63', '제63조제1항제1호마목', '초ㆍ중등교육법', '제3조제3호', '「초ㆍ중등교육법」 제3조제3호'),
        }
        actual = {(e['source_jo'], e['source_ref'], e['target_law'], e['target_ref'], e['cite_raw']) for e in rows}
        self.assertTrue(expected <= actual)
        texts = {a['jo']: a['text'] for a in source['laws'][0]['articles']}
        for row in rows:
            self.assertEqual(row['source_law'], '법인세법')
            self.assertEqual(texts[row['source_jo']][row['source_start']:row['source_end']], row['cite_raw'])
            self.assertEqual(row['target_status'], 'not-collected')
            self.assertEqual(row['target_effective'], '')
            self.assertEqual(row['external_reverse'], 'not-collected')
            self.assertTrue(row['evidence_id'])
        self.assertFalse(any(e['target_law'] == '상법' and e['target_ref'].startswith('제13조') for e in graph['edges']))

    def test_law_only_and_missing_ranges_do_not_invent_article_targets(self):
        source = fixture()
        source['laws'][0]['articles'].append(article('65', [
            ('제65조', '제65조(검증) 「미수집범위법」 제2조부터 제5조까지를 준용한다.'),
        ]))
        graph = build_tax_universe(source)
        named = [e for e in graph['external_references'] if e['target_law'].startswith('국립대학법인')]
        self.assertEqual([(e['target_kind'], e['target_ref']) for e in named], [('law', '법령·정의 참조')])
        ranged = [e for e in graph['external_references'] if e['target_law'] == '미수집범위법']
        self.assertEqual(len(ranged), 1)
        self.assertEqual(ranged[0]['cite_raw'], '「미수집범위법」 제2조부터 제5조까지')
        self.assertTrue(ranged[0]['via_range'])
        self.assertFalse(any(e['target_law'] == '미수집범위법' for e in graph['edges']))

    def test_public_export_keeps_external_rows_without_reverse_links(self):
        source = fixture()
        graph = build_tax_universe(source)
        writer = MemoryWriter()
        entries, ids = export_documents(writer, 'tax', '', source['laws'], graph)
        self.assertNotIn('고등교육법', ids)
        entry = next(e for e in entries if e['name'] == '법인세법')
        document = writer.values[entry['file']['index']]
        external = document['details']['63']['external']
        row = next(e for e in external if e['target_law'] == '고등교육법')
        self.assertEqual(row['source_ref'], '제63조제1항제1호가목')
        self.assertEqual(row['target_ref'], '제3조')
        self.assertEqual(row['target_status'], 'not-collected')
        self.assertEqual(row['target_id'], '')
        self.assertEqual(row['source_scope']['scopes'][0][0], ('63', '1', '1', '가'))
        self.assertFalse(any(e['target_law'] == '고등교육법' for e in document['details']['63']['rows']))
        index = EdgeIndex(graph, source['laws'])
        self.assertNotIn(('고등교육법', '3'), index.reverse)

    def test_table_contaminated_or_nested_names_are_review_issues_without_urls(self):
        source = fixture()
        source['laws'][0]['articles'].append(article('66', [
            ('제66조', '제66조(검증)'),
            ('제66조제1항', '① 「전자무 │다른 표 열의 제33조│\n│역 촉진에 관한 법률」 제12조제1항에 따른다.'),
            ('제66조제2항', '② 「잘린 법령명 「방문판매 등에 관한 법률」 제13조에 따른다.'),
        ]))
        graph = build_tax_universe(source)
        issues = [e for e in graph['citation_issues'] if e['source_jo'] == '66']
        self.assertEqual(len(issues), 2)
        self.assertEqual({e['source_ref'] for e in issues}, {'제66조제1항', '제66조제2항'})
        self.assertFalse(any(e['source_jo'] == '66' for e in graph['external_references']))
        body = source['laws'][0]['articles'][-1]['text']
        for issue in issues:
            self.assertEqual(body[issue['source_start']:issue['source_end']], issue['raw'])
            self.assertEqual(issue['kind'], 'unresolved-law-name')
            self.assertNotIn('target_url', issue)
            self.assertNotIn('target_law', issue)
        writer = MemoryWriter()
        entries, _ = export_documents(writer, 'tax', '', source['laws'], graph)
        entry = next(e for e in entries if e['name'] == '법인세법')
        detail = writer.values[entry['file']['index']]['details']['66']
        self.assertEqual(len(detail['issues']), 2)
        self.assertEqual(detail['external'], [])

    def test_name_whitespace_and_real_regulation_titles_are_not_rewritten(self):
        source = fixture()
        source['laws'][0]['articles'].append(article('67', [
            ('제67조', '제67조(검증) 「장애인복지법 」 제2조 및 「국가공무원 복무규정」에 따른다. 「5ㆍ18민주화운동 관련자 보상 등에 관한 법률」 제2조를 준용한다.'),
        ]))
        graph = build_tax_universe(source)
        rows = [e for e in graph['external_references'] if e['source_jo'] == '67']
        self.assertEqual({e['target_law'].strip() for e in rows}, {'장애인복지법', '국가공무원 복무규정', '5ㆍ18민주화운동 관련자 보상 등에 관한 법률'})
        self.assertFalse(any(e['source_jo'] == '67' for e in graph.get('citation_issues', [])))

    def test_unresolved_relative_names_and_clause_fragments_are_not_law_links(self):
        source = fixture()
        source['laws'][0]['articles'].append(article('68', [
            ('제68조', '제68조(검증)'),
            ('제68조제1항', '① 법 제89조ㆍ법 제90조ㆍ법 제95조 및 법 제98조에 따른다.'),
            ('제68조제2항', '② 「상법」 제352조의 규정에 의한 주주명부 또는 동법 제566조의 규정에 의한 사원명부'),
        ]))
        graph = build_tax_universe(source)
        issues = [e for e in graph['citation_issues'] if e['source_jo'] == '68']
        self.assertEqual({e['source_ref'] for e in issues}, {'제68조제1항', '제68조제2항'})
        self.assertTrue(all(e['kind'] == 'unresolved-law-name' for e in issues))
        self.assertFalse(any(e['source_jo'] == '68' for e in graph['external_references']))
        self.assertEqual(graph['edges'], build_universe(source)['edges'])


if __name__ == '__main__':
    unittest.main()
