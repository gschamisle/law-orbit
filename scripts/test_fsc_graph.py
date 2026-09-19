"""Integration tests for the real existing engine; run in a complete checkout."""
from copy import deepcopy
import unittest
import xml.etree.ElementTree as ET
from core.fsc_collection import collect_body, list_record
from core.fsc_graph import build_fsc_graph
from core.universe_builder import build_universe
from scripts.test_fsc_collection import row, AS_OF


def article(jo, parts):
    offset, blocks = 0, []
    for ref, text in parts:
        blocks.append(dict(ref=ref, text=text, start=offset, end=offset + len(text)))
        offset += len(text) + 1
    return dict(jo=jo, title='합성 검증자료', text='\n'.join(t for _, t in parts), blocks=blocks)


def law(name, category, articles, annexes=None):
    return dict(name=name, category=category, effective='20260101', family=name,
                articles=articles, annexes=annexes or [])


def source():
    return dict(built_at='20260916', coverage={'mode': 'synthetic-test'}, laws=[
        law('은행법', 'fsc', [article('1', [
            ('제1조', '제1조(검증)'),
            ('제1조제1항', '① 「보험업법」 제2조를 준용한다. 「미수록법」 제3조도 확인한다.'),
            ('제1조제2항', '② 「보험업법」에 따른 보험회사 및 별표 1을 말한다.'),
        ])], [dict(ref='별표 1', title='제1조 관련', effective='20260101', urls=[])]),
        law('보험업법', 'fsc', [article('2', [('제2조', '제2조(검증) 「은행법」 제1조를 적용한다.')])]),
        law('소득세법', 'tax', [article('3', [('제3조', '제3조(검증) 「은행법」 제1조를 적용한다.')])]),
        law('민법', 'external', [article('4', [('제4조', '제4조(검증) 「보험업법」 제2조 및 「상법」 제5조를 적용한다.')])]),
        law('상법', 'external', [article('5', [('제5조', '제5조(검증)')])]),
    ])


class FscGraphTests(unittest.TestCase):
    def test_tax_default_is_unchanged_and_input_is_not_mutated(self):
        src = source()
        original = deepcopy(src)
        before = build_universe(src)
        build_fsc_graph(src)
        self.assertEqual(before, build_universe(src, focus_categories=('tax',)))
        self.assertEqual(src, original)
        self.assertNotIn('focus_laws', before)

    def test_financial_to_financial_and_external_reverse_are_retained(self):
        graph = build_fsc_graph(source())
        pairs = {(e['source_law'], e['target_law']) for e in graph['edges']}
        self.assertIn(('은행법', '보험업법'), pairs)
        self.assertIn(('보험업법', '은행법'), pairs)
        self.assertIn(('소득세법', '은행법'), pairs)
        self.assertIn(('민법', '보험업법'), pairs)
        self.assertNotIn(('민법', '상법'), pairs)
        self.assertEqual(set(graph['focus_laws']), {'은행법', '보험업법'})
        self.assertEqual(graph['tax_laws'], ['소득세법'])

    def test_law_level_annexes_and_out_of_scope_are_not_dropped(self):
        graph = build_fsc_graph(source())
        self.assertTrue(any(e['target_kind'] == 'law' for e in graph['edges']))
        self.assertTrue(any(e['target_kind'] == 'annex' for e in graph['edges']))
        self.assertTrue(any(e['type'] == 'byeolpyo' for e in graph['edges']))
        self.assertTrue(any(e['law'] == '미수록법' for e in graph['outside_scope']))

    def test_every_saved_span_still_matches_the_source_text(self):
        src = source()
        graph = build_fsc_graph(src)
        texts = {(l['name'], a['jo']): a['text'] for l in src['laws'] for a in l['articles']}
        for edge in graph['edges']:
            if edge['source_granularity'] == 'annex':
                continue
            self.assertEqual(texts[edge['source_law'], edge['source_jo']]
                             [edge['source_start']:edge['source_end']], edge['cite_raw'])

    def test_invalid_focus_options_fail(self):
        for categories in ((), 'fsc', (None,), iter(['fsc'])):
            with self.subTest(categories=categories), self.assertRaises(ValueError):
                build_universe(source(), focus_categories=categories)

    def test_official_statute_adapter_reuses_existing_hierarchy_parser(self):
        record = list_record(row(), 'eflaw', AS_OF)
        root = ET.fromstring('''<법령><기본정보><법령명_한글>검증법</법령명_한글>
          <법령ID>001</법령ID><시행일자>20260101</시행일자>
          <공포일자>20251201</공포일자><소관부처>금융위원회</소관부처></기본정보>
          <조문><조문단위><조문여부>조문</조문여부><조문번호>1</조문번호>
          <조문제목>검증</조문제목><조문내용>제1조(검증)</조문내용>
          <항><항번호>①</항번호><항내용>① 「은행법」 제2조를 준용한다.</항내용></항>
          </조문단위></조문></법령>''')
        result = collect_body(lambda *_: ET.tostring(root, encoding='utf-8'), record, as_of=AS_OF)
        self.assertEqual(result['law_id'], '001')
        self.assertEqual(result['mst'], '123')
        self.assertEqual(result['body_status'], 'indexed-statute-text')
        self.assertEqual(result['articles'][0]['blocks'][1]['ref'], '제1조제1항')


if __name__ == '__main__':
    unittest.main()
