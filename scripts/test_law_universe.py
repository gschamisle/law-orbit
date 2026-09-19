"""Expanded law coverage, evidence ownership, hierarchy and scope regressions."""
from copy import deepcopy
import json
import unittest
from core.law_galaxy import build as overview
from core.universe_builder import build_universe
from core.law_universe import SOURCES, load_graph
from core.galaxy_focus import analyze_focus, visible_rows, build


def law(name, category, articles, annexes=None):
    return dict(name=name, category=category, effective='20260101', family=name,
                articles=articles, annexes=annexes or [])


def article(jo, parts):
    offset, blocks = 0, []
    for ref,text in parts:
        blocks.append(dict(ref=ref,text=text,start=offset,end=offset+len(text)))
        offset += len(text)+1
    return dict(jo=jo,title='검증',text='\n'.join(t for _,t in parts),blocks=blocks)


def fixture():
    a = article('2', [
        ('제2조','제2조(검증)'),
        ('제2조제1항','① 「상법」 제7조제2항을 적용한다.'),
        ('제2조제2항','② 「민법」에 따른 채권(같은 법 제3조에 따른 경우는 제외한다)을 말한다.'),
        ('제2조제3항','③ 「상법」 별표 1에 따른다. 「민법」에 따른 채권은 별표 2로 정한다.'),
        ('제2조제4항','④ 「상법」 제7조부터 제9조까지 및 제11조제1호의2가목을 준용한다.'),
        ('제2조제5항','⑤ 한국표준산업분류에 따른다.'),
    ])
    corpus = [law('세법','tax',[a]),
              law('상법','external',[article(j,[(f'제{j}조','「민법」 제3조 및 「세법」 제2조를 준용한다.')]) for j in ('7','7의2','8','9','11')],
                  [dict(ref='별표 1',title='규모 기준',urls=['https://www.law.go.kr/example'])]),
              law('민법','external',[article('3',[('제3조','제3조(검증)')])])]
    return dict(built_at='fixture',laws=corpus)


class UniverseTests(unittest.TestCase):
    def test_exact_evidence_scope_and_relative_law(self):
        source=fixture()
        graph=build_universe(source)
        own=[e for e in graph['edges'] if e['source_law']=='세법']
        relative=next(e for e in own if e['cite_raw'].startswith('같은 법'))
        self.assertEqual(relative['target_law'],'민법')
        self.assertTrue(relative['context_review'])
        self.assertEqual(relative['source_ref'],'제2조제2항')
        a=source['laws'][0]['articles'][0]
        for e in own:
            self.assertEqual(a['text'][e['source_start']:e['source_end']],e['cite_raw'])
        self.assertFalse(any(e['source_law']=='상법' and e['target_law']=='민법' for e in graph['edges']))
        self.assertTrue(any(e['source_law']=='상법' and e['target_law']=='세법' for e in graph['edges']))

    def test_annexes_ranges_item_branches_and_standards(self):
        graph=build_universe(fixture())
        own=[e for e in graph['edges'] if e['source_law']=='세법']
        annexes=[e for e in own if e['target_kind']=='annex']
        self.assertEqual({(e['target_law'],e['target_ref']) for e in annexes},{('상법','별표 1'),('세법','별표 2')})
        self.assertTrue(next(e for e in annexes if e['target_law']=='상법')['annex_urls'])
        ranged=[e for e in own if e.get('via_range')]
        self.assertTrue({'제7조','제7조의2','제8조','제9조'} <= {e['target_ref'] for e in ranged})
        self.assertTrue(any(e['target_ref']=='제11조제1호의2가목' for e in own))
        self.assertEqual(len([e for e in own if e['target_kind']=='standard']),1)

    def test_whole_law_reverse_is_optional(self):
        graph=build_universe(fixture())
        result=analyze_focus('민법','제3조',graph)
        self.assertTrue(result['broad_rows'])
        self.assertFalse(any(r.get('broad') for r in visible_rows(result)))
        self.assertTrue(any(r.get('broad') for r in visible_rows(result,include_broad=True)))
        self.assertFalse(visible_rows(result,external=False))
        self.assertTrue(all(r['kind']=='law' for r in visible_rows(result,kinds=['law'],include_broad=True)))

    def test_source_paragraph_filter_and_nonarticle_nodes(self):
        graph=build_universe(fixture())
        result=analyze_focus('세법','제2조제1항',graph)
        forward=visible_rows(result,'forward')
        self.assertEqual({r['target_ref'] for r in forward},{'제7조제2항'})
        self.assertEqual(forward[0]['status'],'exact')
        all_result=analyze_focus('세법','제2조',graph)
        data=build(all_result,dict(nodes=[],dust=[]))
        ids={n['id'] for n in data['nodes']}
        self.assertTrue(any(n.get('kind')=='annex' for n in data['nodes']))
        self.assertTrue(any(n.get('kind')=='standard' for n in data['nodes']))
        self.assertTrue(all(e['a'] in ids and e['b'] in ids for e in data['links']))

    def test_real_expanded_connections(self):
        g=load_graph()
        self.assertEqual(len(g['laws']),105)
        self.assertEqual(len(g['tax_laws']),49)
        self.assertTrue(all(l['effective'] <= g['built_at'].replace('-','')[:8] for l in g['catalog']))
        examples=[('법인세법','16','상법','제459조제1항'),
                  ('조세특례제한법 시행령','2','중소기업기본법 시행령','별표 1'),
                  ('법인세법 시행령','19의2','민법','법령·정의 참조'),
                  ('법인세법 시행령','19의2','민사집행법','제102조'),
                  ('부가가치세법','29','교육세법','과세표준 산식 참조')]
        for a,jo,b,ref in examples:
            with self.subTest(source=a,jo=jo,target=b):
                self.assertTrue(any(e['source_law']==a and e['source_jo']==jo and e['target_law']==b and e['target_ref']==ref for e in g['edges']))
        self.assertFalse(any(e['source_law']=='법인세법' and e['source_jo']=='16' and e['target_law']=='상법' and e['target_ref'].startswith('제13조') for e in g['edges']))
        r=analyze_focus('법인세법','제16조제1항제2호가목',g)
        self.assertTrue(any(e['target_law']=='상법' for e in visible_rows(r,'forward',False)))
        self.assertFalse(any(e['source_ref']=='제16조제1항제6호' for e in visible_rows(r,'forward')))
        # A later enumerated item must inherit the article and paragraph of the first.
        r=analyze_focus('법인세법','제16조제2항제2호',g)
        self.assertTrue(any(e['source_law']=='법인세법 시행규칙' and e['source_jo']=='7' for e in visible_rows(r,'reverse')))

    def test_all_persisted_evidence_spans_and_scope(self):
        g=load_graph()
        src=g.get('source') or json.loads(SOURCES.read_text(encoding='utf-8'))
        self.assertEqual(src['built_at'],g['built_at'])
        texts={(l['name'],a['jo']):a['text'] for l in src['laws'] for a in l['articles']}
        taxes=set(g['tax_laws'])
        for e in g['edges']:
            self.assertTrue(e['source_law'] in taxes or e['target_law'] in taxes)
            if e['source_granularity']=='annex':
                continue
            text=texts[e['source_law'],e['source_jo']]
            self.assertEqual(text[e['source_start']:e['source_end']],e['cite_raw'])


class TaxOverviewTests(unittest.TestCase):
    def graph(self):
        return dict(
            laws=['세법', '연결없는세법', '직접인용법', '역인용법', '고립규칙',
                  '외부끼리법', '다른외부법', '자기참조규칙'],
            tax_laws=['세법', '연결없는세법'],
            edges=[
                dict(source_law='세법 ', target_law='직접인용법', source_jo='1'),
                dict(source_law='역인용법', target_law=' 세법', source_jo='2'),
                dict(source_law='외부끼리법', target_law='다른외부법', source_jo='3'),
                dict(source_law='자기참조규칙', target_law='자기참조규칙', source_jo='4'),
            ],
        )

    def test_tax_connections_survive_display_threshold_in_both_directions(self):
        graph = self.graph()
        original = deepcopy(graph)
        for threshold in (1, 8, 60):
            with self.subTest(threshold=threshold):
                data = overview(graph=graph, min_edge=threshold)
                ids = {node['id'] for node in data['nodes']}
                self.assertEqual(ids, {'세법', '연결없는세법', '직접인용법', '역인용법'})
                self.assertEqual({(e['a'], e['b']) for e in data['all_links']},
                                 {('세법', '직접인용법'), ('역인용법', '세법')})
                self.assertTrue(all(dot['law_id'] in ids for dot in data['dust']))
                if threshold > 1:
                    self.assertFalse(data['links'])
        self.assertEqual(graph, original)

    def test_tax_only_switch_keeps_all_tax_laws(self):
        data = overview(graph=self.graph(), include_external=False)
        self.assertEqual({n['id'] for n in data['nodes']}, {'세법', '연결없는세법'})
        self.assertFalse(data['all_links'])

    def test_fsc_scope_keeps_disconnected_documents(self):
        graph = self.graph()
        graph.update(domain='fsc', focus_laws=list(graph['laws']))
        del graph['tax_laws']
        for external in (True, False):
            with self.subTest(external=external):
                data = overview(graph=graph, include_external=external)
                self.assertEqual({n['id'] for n in data['nodes']}, set(graph['laws']))


if __name__=='__main__':
    unittest.main()
