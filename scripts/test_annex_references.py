"""Numbered annex references only: owner boundaries and unchanged article edges."""
import json
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from core.annex_references import annex_references as references
from core.fsc_administrative import adapter, provision_blocks
from core.mofe_citations import prepare_aliases
from core.universe_builder import build_universe

ROOT = Path(__file__).resolve().parents[1]


def document(name, text, *, jo='1', provider='eflaw', category='medical', strict=True, annexes=()):
    article = dict(jo=jo, title='검증', text=text, effective='20260929', blocks=provision_blocks(text, jo))
    law = dict(name=name, provider=provider, category=category, effective='20260929',
               articles=[article], annexes=[dict(ref=ref, title='검증표', effective='20260929',
                   urls=['https://www.law.go.kr/LSW/flDownload.do?flSeq=123']) for ref in annexes])
    if strict:
        prepare_aliases(law)
    return law


class AnnexReferences(unittest.TestCase):
    def extract(self, law, *others):
        article = law['articles'][0]
        rows = references(law, article, [law, *others])
        for row in rows:
            self.assertEqual(article['text'][row['start']:row['end']], row['raw'])
        return [(r['target_name'], r['target_ref']) for r in rows]

    def test_requested_local_references_without_annex_body(self):
        for name, jo, text, provider in (
            ('국민건강보험 요양급여의 기준에 관한 규칙', '15', '제15조(규제의 재검토) 별표 2 제4호가목 및 나목에 따른 기준을 검토한다.', 'eflaw'),
            ('근로기준법 시행령', '7', '제7조(적용범위) 적용하는 법 규정은 별표 1과 같다.', 'eflaw'),
            ('은행업감독업무시행세칙', '4', '제4조(서류) 제출서류는 별표 1과 같다.', 'admrul'),
        ):
            with self.subTest(name=name):
                law = document(name, text, jo=jo, provider=provider, annexes=('별표 1', '별표 2'))
                expected = '별표 2' if jo == '15' else '별표 1'
                self.assertEqual(self.extract(law), [(name, expected)])
                graph = build_universe(dict(laws=[law], built_at='20260929', provider='fixture'),
                    focus_categories=('medical',), article_adapter=adapter, preserve_external=True)
                edge = next(e for e in graph['edges'] if e['target_kind'] == 'annex')
                self.assertEqual(edge['annex_urls'], law['annexes'][0]['urls'])
                self.assertFalse(any(a.get('body_analysis') for a in law['annexes']))

    def test_named_owner_does_not_leak_to_bare_local_reference(self):
        law = document('은행업감독업무시행세칙', '제6조(서류) 규정 제9조제1항에 따른 첨부서류는 별표 2와 같다.', provider='admrul')
        law['aliases'] = {'규정': '은행업감독규정'}
        self.assertEqual(self.extract(law), [(law['name'], '별표 2')])
        law = document('국토의 계획 및 이용에 관한 법률 시행령', '제4조(기준) 「건축법 시행령」 별표 1에 따른 건축물은 별표 1로 정한다.')
        self.assertEqual(self.extract(law), [('건축법 시행령', '별표 1'), (law['name'], '별표 1')])

    def test_family_aliases_and_explicit_document_alias(self):
        law = document('근로기준법 시행령', '제7조(검증) 법 별표 1, 영 별표 2 및 규칙 별지 제3호서식에 따른다.')
        self.assertEqual(self.extract(law), [('근로기준법', '별표 1'), ('근로기준법 시행령', '별표 2'), ('근로기준법 시행규칙', '별지 제3호서식')])
        law = document('특별급여 규칙', '제2조(검증) 건강보험규칙의 별표 6에 따른다.')
        law['aliases'] = {'건강보험규칙': '국민건강보험법 시행규칙'}
        self.assertEqual(self.extract(law), [('국민건강보험법 시행규칙', '별표 6')])

    def test_named_declaration_derivative_and_enumeration(self):
        law = document('검증법', '제2조(검증) 「건축법」 시행령 별표 1 및 별표 2를 적용한다.\n「교육법」(이하 "법"이라 한다) 별지 제4호서식을 쓴다.')
        self.assertEqual(self.extract(law), [('건축법 시행령', '별표 1'), ('건축법 시행령', '별표 2'), ('교육법', '별지 제4호서식')])
        law = document('검증법', '제2조(검증) 「건축법」의 별표 1 및 별표 2에 따른다.')
        self.assertEqual(self.extract(law), [('건축법', '별표 1'), ('건축법', '별표 2')])

    def test_self_names_and_bok_are_local(self):
        law = document('외국환거래업무취급절차', '제2조(검증) 이 절차 별표 1 및 본 절차 별지 제2호서식과 같다.', provider='bok', category='forex', strict=False)
        self.assertEqual(self.extract(law), [(law['name'], '별표 1'), (law['name'], '별지 제2호서식')])

    def test_same_law_requires_one_explicit_owner_in_same_paragraph(self):
        law = document('검증법', '제2조(검증) 「건축법」 제3조 및 같은 법 별표 1에 따른다.')
        self.assertEqual(self.extract(law), [('건축법', '별표 1')])
        for text in ('제2조(검증) 같은 법 별표 1에 따른다.',
                     '제2조(검증) 「건축법」 제3조에 따른다.\n② 같은 법 별표 1에 따른다.',
                     '제2조(검증) 「건축법」과 「다른법」을 적용하고 같은 법 별표 1에 따른다.'):
            with self.subTest(text=text):
                law = document('검증법', text)
                self.assertEqual(self.extract(law), [])
                self.assertEqual(len(law['articles'][0]['citation_issues']), 1)
        law = document('검증법', '제2조(검증) ① 「건축법」을 적용한다. ② 같은 법 별표 1에 따른다.')
        law['articles'][0].pop('blocks')
        self.assertEqual(self.extract(law), [])

    def test_unknown_and_conflicting_aliases_are_issues_not_guessed(self):
        for text in ('제2조(검증) 알수없는규정 별표 1에 따른다.', '제2조(검증) 영 별표 1에 따른다.',
                     '제2조(검증) 「규정」 별표 1에 따른다.', '제2조(검증) 「동법」 별표 1에 따른다.'):
            law = document('특별급여 규칙', text)
            self.assertEqual(self.extract(law), [])
        law = document('검증법', '제2조(검증) 「첫째법」(이하 "규정"이라 한다), 「둘째법」(이하 "규정"이라 한다). 규정 별표 1에 따른다.')
        self.assertEqual(self.extract(law), [])
        self.assertTrue(law['articles'][0]['citation_issues'])

    def test_quotes_and_synthetic_annex_units_are_not_analyzed(self):
        law = document('검증법', '제2조(검증) "별표 1"을 "별표 2"로 본다.')
        self.assertEqual(self.extract(law), [])
        self.assertEqual(len(law['articles'][0]['citation_issues']), 2)
        law['articles'][0]['jo'] = ''  # Existing annex-body collector uses synthetic empty-jo units.
        before = deepcopy(law)
        self.assertEqual(self.extract(law), [])
        self.assertEqual(law, before)

    def test_partial_numbers_and_ambiguous_article_enumeration_are_issues(self):
        for text in ('별지 제1호의2서식', '별표 1-2', '규정 제9조 및 별표 1', '규정 제9조의 별표 1',
                     '규정 별표 1부터 별표 3까지', '별표 1부터 3까지', '해당 규칙의 별표 1', '다른 법령의 별표 1'):
            with self.subTest(text=text):
                law = document('검증법', '제2조(검증) ' + text + '을 적용한다.')
                law['aliases'] = {'규정': '다른규정'}
                self.assertEqual(self.extract(law), [])
                self.assertEqual(len(law['articles'][0]['citation_issues']), 1)
        law = document('관세법 시행령', '제98조(검증) 「세계무역기구협정 등에 의한 양허관세규정」 별표 1부터 별표 4까지를 따른다.')
        self.assertEqual(self.extract(law), [])
        self.assertEqual(len(law['articles'][0]['citation_issues']), 1)

    def test_ordinance_exclusion_and_unchanged_non_annex_outputs(self):
        law = document('검증조례', '제2조(검증) 별표 1에 따른다.', provider='ordin')
        self.assertEqual(self.extract(law), [])
        law = document('근로기준법 시행령', '제7조(검증) 「근로기준법」 제11조에 따라 범위는 별표 1과 같다.')
        with patch('core.annex_references.annex_references', return_value=[]):
            old = adapter(deepcopy(law), deepcopy(law['articles'][0]), [law])
        new = adapter(deepcopy(law), deepcopy(law['articles'][0]), [law])
        self.assertEqual([r for r in new if r.get('kind') != 'annex'], old)
        self.assertEqual(len([r for r in new if r.get('kind') == 'annex']), 1)

    def test_issues_are_idempotent(self):
        law = document('검증법', '제2조(검증) 같은 법 별표 1에 따른다.')
        self.extract(law)
        before = deepcopy(law['articles'][0]['citation_issues'])
        self.extract(law)
        self.assertEqual(law['articles'][0]['citation_issues'], before)


class CollectedAnnexReferences(unittest.TestCase):
    def test_public_snapshot_examples_when_present(self):
        from scripts.static_storage import Storage
        folder = ROOT / 'output/static-healthcare-label-20260929'
        if not (folder / 'manifest.json').is_file():
            self.skipTest('Requires immutable public snapshot')
        manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
        storage = Storage(folder, manifest)
        for domain, name, jo, ref, owner in (
            ('medical', '국민건강보험 요양급여의 기준에 관한 규칙', '15', '별표 2', None),
            ('labor', '근로기준법 시행령', '7', '별표 1', None),
            ('fsc', '은행업감독업무시행세칙', '4', '별표 1', None),
            ('procurement', '조달청 협상에 의한 계약 제안서평가 세부기준', '2', '별표 1', '조달청 평가위원 통합관리 규정'),
        ):
            with self.subTest(name=name):
                catalog = storage.read(next(d['catalog'] for d in manifest['domains'] if d['id'] == domain))
                entry = next(d for d in catalog['laws'] if d['name'] == name)
                saved = storage.read(entry['file'])
                articles = list(saved['articles'])
                for part in entry.get('parts', []):
                    articles.extend(storage.read(part).get('articles', []))
                article = next(a for a in articles if a['jo'] == jo)
                law = document(name, article['text'], jo=jo, provider='admrul' if domain in ('fsc', 'procurement') else 'eflaw')
                rows = references(law, law['articles'][0], [law])
                self.assertIn((owner or name, ref), [(r['target_name'], r['target_ref']) for r in rows])


if __name__ == '__main__':
    unittest.main()
