"""Task evidence must demonstrate the frozen source/target, never link volume.

These counterexamples use citation-shaped rows deliberately. The gate consumes
an already source-validated graph; source offsets are exercised independently.
"""
from copy import deepcopy
import unittest

from core.candidate_evidence import case_proof
from core.mofe_universe import validate_bundle
from scripts.test_mofe_domains import fixture


EXPECTED = dict(source_law='신용정보의 이용 및 보호에 관한 법률', source_jo='15',
                target_law='개인정보 보호법', target_jo='15',
                quote_contains='「개인정보 보호법」 제15조제1항제2호부터 제7호까지')


def citation(**changes):
    row=dict(source_law=EXPECTED['source_law'], source_jo='15',
                target_law=EXPECTED['target_law'], target_ref='제15조제1항제2호',
                target_kind='article', type='direct', context_review=False,
                context=EXPECTED['quote_contains'] + '의 어느 하나에 해당하는 경우',
                cite_raw=EXPECTED['quote_contains'], evidence_id='credit-privacy-15')
    row.update(changes)
    return row


def graph(*edges, text=()):
    return dict(edges=list(edges), text_citations=list(text))


class CandidateEvidenceCounterexamples(unittest.TestCase):
    def test_many_irrelevant_links_cannot_make_the_task_available(self):
        rows=[]
        for number in range(1, 1001):
            row=citation()
            row.update(source_law='다른법', source_jo=str(number),
                       evidence_id='unrelated-' + str(number))
            rows.append(row)
        result=case_proof(graph(*rows), [EXPECTED])
        self.assertFalse(result['available'])
        self.assertEqual(result['verified_relations'], 0)
        self.assertEqual(result['evidence_ids'], [])

    def test_exact_source_and_destination_are_required(self):
        for change in (
            dict(source_law=EXPECTED['target_law']),
            dict(target_law=EXPECTED['source_law']),
            dict(source_jo='16'), dict(target_ref='제16조'),
            dict(source_jo='15의2'), dict(target_ref='제15조의2'),
        ):
            with self.subTest(change=change):
                row=citation(); row.update(change)
                self.assertFalse(case_proof(graph(row), [EXPECTED])['available'])

    def test_review_candidates_are_not_confirmed_task_evidence(self):
        for change in (
            dict(context_review=True), dict(type='context'),
            dict(type='context-review'),
        ):
            with self.subTest(change=change):
                row=citation(); row.update(change)
                self.assertFalse(case_proof(graph(row), [EXPECTED])['available'])

    def test_whole_law_reference_does_not_invent_the_expected_article(self):
        row=citation()
        row.update(target_kind='law', target_ref='법령·정의 참조')
        self.assertFalse(case_proof(graph(row), [EXPECTED])['available'])

    def test_quote_from_another_edge_does_not_complete_the_expected_edge(self):
        expected_endpoint=citation()
        expected_endpoint['cite_raw']='「개인정보 보호법」 제3조제1항 및 제2항'
        expected_endpoint['context']=expected_endpoint['cite_raw']
        expected_quote=citation(); expected_quote['source_jo']='2'
        self.assertFalse(case_proof(graph(expected_endpoint, expected_quote),
                                    [EXPECTED])['available'])

    def test_forged_context_cannot_replace_the_source_verified_citation_span(self):
        row=citation()
        row['cite_raw']='「개인정보 보호법」 제15조제1항제1호'
        # Correct-looking context is deliberately retained, while the actual
        # source span points at a different legal basis than the frozen case.
        self.assertFalse(case_proof(graph(row), [EXPECTED])['available'])

    def test_invalid_or_isolated_reference_does_not_silently_become_article_15(self):
        for reference in ('제15조 등', '제1항제2호', '제15조부터 제17조까지', '제0조'):
            with self.subTest(reference=reference):
                row=citation(); row['target_ref']=reference
                self.assertFalse(case_proof(graph(row), [EXPECTED])['available'])

    def test_all_independently_frozen_relations_are_required(self):
        second={**EXPECTED, 'target_jo':'3', 'quote_contains':'제3조제1항 및 제2항'}
        result=case_proof(graph(citation()), [EXPECTED, second])
        self.assertFalse(result['available'])
        self.assertEqual(result['expected_relations'], 2)
        self.assertEqual(result['verified_relations'], 1)

    def test_empty_expectations_are_not_a_release_claim(self):
        self.assertFalse(case_proof(graph(citation()), [])['available'])

    def test_article_qualification_and_spacing_do_not_hide_real_evidence(self):
        row=citation()
        row.update(target_law='개인정보보호법', target_ref='제15조 제1항 제2호',
                   cite_raw='「개인정보 보호법」\n제15조 제1항 제2호부터 제7호까지',
                   context='「개인정보 보호법」\n제15조 제1항 제2호부터 제7호까지')
        result=case_proof(graph(row), [EXPECTED])
        self.assertTrue(result['available'])
        self.assertEqual(result['evidence_ids'], ['credit-privacy-15'])

    def test_explicit_text_citation_uses_the_same_endpoint_gate(self):
        row=citation(); row['raw']=row.pop('cite_raw')
        self.assertTrue(case_proof(graph(text=[row]), [EXPECTED])['available'])
        row=citation(); row['context_review']=True
        self.assertFalse(case_proof(graph(text=[row]), [EXPECTED])['available'])

    def test_duplicate_evidence_is_not_a_second_verified_relation(self):
        result=case_proof(graph(citation(), deepcopy(citation())), [EXPECTED])
        self.assertEqual(result['verified_relations'], 1)
        self.assertEqual(result['evidence_ids'], ['credit-privacy-15'])

    def test_missing_collected_target_article_cannot_pass_a_plausible_edge(self):
        known={(EXPECTED['source_law'], '15'), (EXPECTED['target_law'], '3')}
        result=case_proof(graph(citation()), [EXPECTED], known_articles=known)
        self.assertFalse(result['available'])
        self.assertEqual(result['evidence_ids'], [])

    def test_missing_collected_source_article_cannot_pass_a_plausible_edge(self):
        known={(EXPECTED['source_law'], '1'), (EXPECTED['target_law'], '15')}
        self.assertFalse(case_proof(graph(citation()), [EXPECTED],
                                    known_articles=known)['available'])

    def test_known_document_with_a_branch_article_does_not_imply_base_article(self):
        known={(EXPECTED['source_law'], '15'), (EXPECTED['target_law'], '15의2')}
        self.assertFalse(case_proof(graph(citation()), [EXPECTED],
                                    known_articles=known)['available'])

    def test_empty_collected_catalog_is_distinct_from_omitting_the_prerequisite(self):
        self.assertFalse(case_proof(graph(citation()), [EXPECTED],
                                    known_articles=set())['available'])
        self.assertTrue(case_proof(graph(citation()), [EXPECTED])['available'])

    def test_real_collected_endpoints_survive_title_spacing_normalization(self):
        known={(EXPECTED['source_law'], '15'), ('개인정보보호법', '15')}
        self.assertTrue(case_proof(graph(citation()), [EXPECTED],
                                   known_articles=known)['available'])


class CandidateSourcePrerequisites(unittest.TestCase):
    def test_source_quote_and_offset_must_validate_before_assessment(self):
        valid=fixture()
        validate_bundle(valid, 'public_institutions')
        for change in (dict(cite_raw='꾸며낸 근거'), dict(source_start=999999)):
            with self.subTest(change=change):
                candidate=deepcopy(valid)
                candidate['graph']['edges'][0].update(change)
                with self.assertRaisesRegex(ValueError, '원문'):
                    validate_bundle(candidate, 'public_institutions')


if __name__ == '__main__':
    unittest.main()
