"""Price scope and faithful explicit-citation fixtures; no network or API keys."""
from copy import deepcopy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from core.prices_profile import AGRI, PRICE, CALCULATION, DISPLAY, FEES, PROFILE, CASE_EXPECTATIONS, article_tags, document_tags
from core.mofe_profiles import WORK_PROFILES, selected
from core.fsc_administrative import adapter
from core.mofe_citations import prepare_aliases


def provision_document(name, provider, text, jo='1'):
    document = dict(name=name, uid='fixture:' + name, provider=provider, articles=[
        dict(jo=jo, title='', text=text, blocks=[])], aliases={})
    prepare_aliases(document)
    return document


class PricesProfileTests(unittest.TestCase):
    def test_scope_is_declared_and_nonexistent_rule_not_invented(self):
        self.assertNotIn(PRICE + ' 시행규칙', PROFILE['statutes'])
        self.assertEqual(len(PROFILE['cases']), 3)
        self.assertEqual(PROFILE['sectors']['all'], '전체 연결')
        self.assertEqual(PROFILE['default_refs']['consultation'], '제4조')
        self.assertIn(DISPLAY, PROFILE['required_rules'])
        self.assertNotIn(FEES, PROFILE['rules'])
        self.assertNotIn(FEES, PROFILE['required_rules'])
        self.assertTrue(any('연혁' in item['title'] for item in PROFILE['companion_sources']))
        self.assertNotIn('가격표시제 실시요령', PROFILE['rules'])

    def test_exact_scope_and_authority_reject_nearby_tariffs(self):
        with patch.dict(WORK_PROFILES, {'prices': PROFILE}):
            self.assertTrue(selected('prices', PRICE, '재정경제부', 'eflaw'))
            self.assertTrue(selected('prices', AGRI, '농림축산식품부,해양수산부', 'eflaw'))
            self.assertTrue(selected('prices', DISPLAY, '산업통상부', 'admrul'))
            self.assertFalse(selected('prices', PRICE, '금융위원회', 'eflaw'))
            self.assertFalse(selected('prices', FEES, '재정경제부', 'admrul'))
            self.assertFalse(selected('prices', '전기사업법', '산업통상부', 'eflaw'))
            self.assertFalse(selected('prices', '의약품 가격표시제 실시요령', '보건복지부', 'admrul'))

    def test_navigation_keeps_shared_law_unassigned_and_multiple_tags(self):
        self.assertEqual(document_tags('관세법'), [])
        self.assertEqual(document_tags('소비자기본법'), [])
        self.assertEqual(document_tags(CALCULATION), ['consultation'])
        self.assertEqual(document_tags(DISPLAY), ['display'])
        item = dict(jo='4', title='공공요금 및 수수료의 결정', text='가격표시와 원가를 검토한다.')
        before = deepcopy(item)
        self.assertTrue({'consultation', 'display'}.issubset(article_tags(PRICE, item)))
        self.assertEqual(item, before)

    def test_three_source_first_questions_keep_actual_owners_and_spans(self):
        # Short source fixtures, not a claim that all source articles were verified.
        # The sources and edition IDs are recorded in docs/prices-universe.md.
        cases = (
            (PRICE + ' 시행령', 'eflaw', '법 제4조제1항에 따른 공공요금은',
             PRICE, '제4조제1항'),
            (DISPLAY, 'admrul', '「물가안정에 관한 법률」 제3조 및 「소비자기본법」 제12조',
             '소비자기본법', '제12조'),
            (AGRI, 'eflaw', '「관세법」 제71조에 따른 할당관세를 적용하려는 경우',
             '관세법', '제71조'),
        )
        for name, provider, text, owner, target in cases:
            with self.subTest(name=name):
                source = provision_document(name, provider, text)
                rows = adapter(source, source['articles'][0], [])
                match = [r for r in rows if r['target_name'] == owner and r['target_ref'] == target]
                self.assertEqual(len(match), 1)
                for row in rows:
                    self.assertEqual(text[row['start']:row['end']], row['raw'])

    def test_public_fee_case_requires_current_substantive_decree(self):
        expected = CASE_EXPECTATIONS[(PRICE, '4')]
        self.assertEqual(len(expected), 1)
        self.assertEqual(expected[0]['source_law'], PRICE + ' 시행령')
        self.assertEqual(expected[0]['source_jo'], '6')
        self.assertEqual(expected[0]['target_law'], PRICE)
        self.assertEqual(expected[0]['target_jo'], '4')
        self.assertEqual(expected[0]['quote_contains'], '법 제4조제1항')

    def test_generic_other_laws_does_not_expand_every_tariff(self):
        source = provision_document(PRICE, 'eflaw', '주무부장관은 다른 법률에서 정하는 바에 따라 요금을 정한다.', '4')
        self.assertEqual(adapter(source, source['articles'][0], []), [])


class PricesParagraphTests(unittest.TestCase):
    def test_repeated_numeric_items_keep_roman_parents_and_do_not_become_articles(self):
        from core.ftc_text_citations import collect_text_citations, validate_text_citations, main_text
        owner = '공공기관의 정보공개에 관한 법률'
        text = ('Ⅰ. 첫 구분\n1. 「' + owner + '」 제3조에 따른다.\n'
                'Ⅱ. 다음 구분\n1. 「' + owner + '」 제4조에 따른다.')
        rule = dict(name=CALCULATION, uid='fixture:calculation', provider='admrul',
                    articles=[], raw_body_blocks=[text], effective='20260102',
                    source_url='https://www.law.go.kr/admRulInfoP.do?admRulSeq=2100000272762')
        target = dict(name=owner, provider='eflaw', articles=[dict(jo='3'), dict(jo='4')],
                      effective='20231117', source_url='https://www.law.go.kr/법령/공공기관의정보공개에관한법률')
        source = dict(domain='prices', laws=[target], administrative_rules=[rule])
        rows, issues = collect_text_citations(source, profile='prices')
        validate_text_citations(source, rows)
        self.assertEqual(issues, [])
        self.assertEqual([(e['source_ref'], e['target_ref']) for e in rows],
                         [('Ⅰ. 첫 구분 / 1.', '제3조'), ('Ⅱ. 다음 구분 / 1.', '제4조')])
        self.assertEqual(rule['articles'], [])
        for edge in rows:
            self.assertEqual(edge['source_jo'], '')
            self.assertEqual(edge['source_granularity'], 'text')
            self.assertEqual(main_text(rule)[edge['source_start']:edge['source_end']], edge['raw'])


class PricesBareTitleTests(unittest.TestCase):
    def test_unique_full_title_with_legal_cue_has_exact_law_level_span(self):
        from core.prices_citations import bare_law_references
        owner = '공공기관의 정보공개에 관한 법률'
        text = '6. 소관부처장관은 ' + owner + '에서 정하는 범위 내에서 공개할 수 있다.'
        rows = bare_law_references(dict(text=text, jo=''), [dict(name=owner, provider='eflaw')])
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row['target_name'], owner)
        self.assertEqual(row['kind'], 'law')
        self.assertEqual(row['target_ref'], '법령·정의 참조')
        self.assertEqual(row['raw'], owner)
        self.assertEqual(text[row['start']:row['end']], owner)

    def test_no_alias_generic_name_embedded_title_or_quoted_text_guess(self):
        from core.prices_citations import bare_law_references
        owner = '공공기관의 정보공개에 관한 법률'
        texts = (
            '신' + owner + '에서 정하는 범위에 따른다.',
            owner + ' 시행령에 따라 공개한다.',
            '“' + owner + '에서 정하는 범위”라는 문구를 검토한다.',
            '「' + owner + '」에서 정하는 범위에 따른다.',
            '정보공개법에서 정하는 범위에 따른다.',
            '다른 법률에서 정하는 범위에 따른다.',
            owner + ' 관련 교육을 한다.',
        )
        for text in texts:
            with self.subTest(text=text):
                self.assertEqual(bare_law_references(dict(text=text, jo=''), [dict(name=owner, provider='eflaw')]), [])

    def test_existing_same_span_is_not_duplicated(self):
        from core.prices_citations import bare_law_references
        owner = '공공기관의 정보공개에 관한 법률'
        text = '6. ' + owner + '에서 정하는 범위에 따른다.'
        start = text.index(owner)
        existing = [dict(start=start, end=start + len(owner), raw=owner, kind='law',
                         target_name=owner, target_ref='법령·정의 참조')]
        self.assertEqual(bare_law_references(dict(text=text, jo=''), [dict(name=owner, provider='eflaw')], existing=existing), [])


class PricesCollectedSourceTests(unittest.TestCase):
    """Optional local source audit; fixtures still run without collected files."""

    @classmethod
    def setUpClass(cls):
        from core.mofe_collection import prepare_source
        from core.mofe_universe import build_graph, validate_bundle
        from core.procurement_universe import documents
        root = Path(__file__).resolve().parents[1]
        candidate = root / 'output/prices-candidate-20261004-v2/source.json'
        if not candidate.is_file():
            candidate = root / 'output/prices-candidate-20261004/source.json'
        source_path = Path(os.environ.get('PRICES_SOURCE', str(candidate)))
        if not source_path.is_file():
            raise unittest.SkipTest('No staged prices source; frozen official-source checks still run')
        cls.source = prepare_source(json.loads(source_path.read_text(encoding='utf-8')))
        cls.graph = build_graph(cls.source)
        cls.bundle = validate_bundle(dict(source=cls.source, graph=cls.graph), 'prices')
        cls.docs = {d['name']: d for d in documents(cls.source)}

    def test_all_ten_declared_sources_are_current_and_historical_fee_is_excluded(self):
        self.assertEqual(set(self.docs), set(PROFILE['statutes'] + PROFILE['rules']))
        self.assertNotIn(FEES, self.docs)
        for document in self.docs.values():
            self.assertTrue(selected('prices', document['name'], document['managing_authority'], document['provider']))
            self.assertEqual(document['state'], 'current-body-verified')
            self.assertLessEqual(document['effective'], self.source['built_at'])
        self.assertEqual(self.docs[CALCULATION]['articles'], [])
        self.assertEqual(self.docs[DISPLAY]['articles'][0]['jo'], '1')

    def test_all_three_preselected_cases_keep_exact_owners_source_spans_and_reverse_rows(self):
        from core.citation_scope import parse_target, Provision
        from core.galaxy_focus import analyze_focus
        from core.mofe_universe import article_for
        # Frozen official wording determines these four relationships; graph counts do not.
        expected = (
            (PRICE + ' 시행령', '6', PRICE, '제4조제1항', '법 제4조제1항'),
            (DISPLAY, '1', PRICE, '제3조', '「물가안정에 관한 법률」 제3조'),
            (DISPLAY, '1', '소비자기본법', '제12조', '「소비자기본법」 제12조'),
            (AGRI, '15', '관세법', '제71조', '「관세법」 제71조'),
        )
        for owner, jo, target, reference, raw in expected:
            with self.subTest(owner=owner, jo=jo, target=target):
                article = next(a for a in self.docs[owner]['articles'] if a['jo'] == jo)
                self.assertIn(raw, article['text'])
                matches = [e for e in self.graph['edges'] if
                           (e['source_law'], e['source_jo'], e['target_law'], e['target_ref'], e['cite_raw'])
                           == (owner, jo, target, reference, raw)]
                self.assertTrue(matches, (owner, jo, target, reference))
                target_jo = parse_target(reference).jo
                rows = analyze_focus(target, Provision(target_jo).label, self.graph)['rows']
                for edge in matches:
                    self.assertFalse(edge.get('context_review'))
                    self.assertEqual(article['text'][edge['source_start']:edge['source_end']], raw)
                    self.assertTrue(any(r['evidence_id'] == edge['evidence_id']
                                        and r['direction'] == 'reverse' and r['neighbor_law'] == owner
                                        and r['neighbor_jo'] == jo for r in rows))
                _, body = article_for(self.bundle, owner, Provision(jo).label)
                self.assertEqual(body['text'], article['text'])
                _, target_body = article_for(self.bundle, target, reference)
                self.assertEqual(target_body['jo'], target_jo)
                self.assertTrue(target_body['text'])

    def test_actual_unquoted_disclosure_reference_is_kept_as_law_level_text_evidence(self):
        from core.ftc_text_citations import main_text, validate_text_citations
        owner = '공공기관의 정보공개에 관한 법률'
        document = self.docs[CALCULATION]
        text = main_text(document)
        self.assertIn(owner + '에서 정하는 범위 내에서 요금산정보고서를 공개할 수 있다.', text)
        rows = [e for e in self.graph.get('text_citations', []) if
                e['source_law'] == CALCULATION and e['target_law'] == owner]
        self.assertEqual(len(rows), 1)
        edge = rows[0]
        self.assertEqual(edge['source_ref'], 'Ⅶ. 요금검증 / 6.')
        self.assertEqual(edge['source_jo'], '')
        self.assertEqual(edge['source_granularity'], 'text')
        self.assertEqual(edge['target_kind'], 'law')
        self.assertEqual(edge['target_ref'], '법령·정의 참조')
        self.assertEqual(edge['target_status'], 'collected')
        self.assertEqual(edge['raw'], owner)
        self.assertEqual(text[edge['source_start']:edge['source_end']], owner)
        validate_text_citations(self.source, self.graph['text_citations'])
        self.assertEqual(document['articles'], [])


if __name__ == '__main__':
    unittest.main()
