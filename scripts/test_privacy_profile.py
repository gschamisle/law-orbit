"""Offline scope/issuer boundaries for the declared privacy/data collection."""
import unittest
from copy import deepcopy

from core.privacy_profile import (
    AI_ADMIN, CASE_EXPECTATIONS, CASE_PROOFS, CREDIT, DISCLOSURE, FAMILIES, METHODS, PRIVACY,
    PROFILE, PUBLIC_DATA, RULES, SAFETY, STANDARD, STATUTES,
    article_tags, authority_policy, document_tags, selected,
)


class PrivacyProfileTests(unittest.TestCase):
    def test_actual_families_are_exact_and_all_required(self):
        self.assertEqual(len(STATUTES), 14)
        self.assertEqual(len(set(STATUTES)), 14)
        self.assertEqual(set(PROFILE['required']), set(STATUTES))
        self.assertEqual(set(PROFILE['required_rules']), set(RULES))
        self.assertNotIn(PRIVACY + ' 시행규칙', STATUTES)
        self.assertIn(AI_ADMIN + ' 시행규칙', STATUTES)
        self.assertNotIn('데이터기반행정 활성화에 관한 법률', STATUTES)
        self.assertEqual(set(RULES), {SAFETY, METHODS, STANDARD})

    def test_each_document_rejects_the_union_of_issuers(self):
        issuers = {PRIVACY: '개인정보보호위원회', PUBLIC_DATA: '행정안전부',
                   DISCLOSURE: '행정안전부', AI_ADMIN: '행정안전부', CREDIT: '금융위원회'}
        for base, documents in FAMILIES.items():
            for name in documents:
                with self.subTest(name=name):
                    issuer = issuers[base]
                    self.assertTrue(selected(name, issuer, 'eflaw'))
                    for wrong in set(issuers.values()) - {issuer}:
                        self.assertFalse(selected(name, wrong, 'eflaw'))
                        self.assertFalse(selected(name, issuer + ',' + wrong, 'eflaw'))
                    policy = authority_policy(name, 'eflaw')
                    self.assertEqual(policy['required'], frozenset((issuer,)))
                    self.assertEqual(policy['allowed'], frozenset((issuer,)))
        for name in RULES:
            self.assertTrue(selected(name, '개인정보보호위원회', 'admrul'))
            self.assertFalse(selected(name, '행정안전부', 'admrul'))
            self.assertFalse(selected(name, '개인정보보호위원회,금융위원회', 'admrul'))

    def test_provider_and_unknown_document_are_fail_closed(self):
        for authority in ('', None, '개인정보보호위원회,행정안전부'):
            self.assertFalse(selected(PRIVACY, authority, 'eflaw'))
        for name, authority, provider in (
            (PRIVACY, '개인정보보호위원회', 'admrul'),
            (SAFETY, '개인정보보호위원회', 'eflaw'),
            (PRIVACY, '개인정보보호위원회', 'unknown'),
            ('개인정보 보호위원회 직제', '개인정보보호위원회', 'eflaw'),
            ('개인정보보호위원회 공무원 행동강령', '개인정보보호위원회', 'admrul'),
            ('전자정부법', '행정안전부', 'eflaw'),
            ('인공지능 발전과 신뢰 기반 조성 등에 관한 기본법', '과학기술정보통신부', 'eflaw'),
            (PRIVACY + ' 시행규칙', '개인정보보호위원회', 'eflaw'),
        ):
            with self.subTest(name=name, provider=provider):
                self.assertFalse(selected(name, authority, provider))
                self.assertIsNone(authority_policy(name, provider))

    def test_whitespace_is_normalized_but_titles_are_not_guessed(self):
        self.assertTrue(selected('개인정보보호법', '개인정보보호위원회', 'eflaw'))
        self.assertTrue(selected('개인정보처리방법에관한고시', '개인정보보호위원회', 'admrul'))
        self.assertFalse(selected('개인정보 처리 방법 해설서', '개인정보보호위원회', 'admrul'))

    def test_owner_and_cross_topic_tags_are_navigation_only_and_immutable(self):
        article = dict(title='다른 법률과의 관계', text='데이터에 개인정보가 포함된 경우 「개인정보 보호법」에 따른다.')
        original = deepcopy(article)
        self.assertEqual(set(article_tags(AI_ADMIN, article)), {'administration', 'processing'})
        self.assertEqual(article, original)
        self.assertEqual(document_tags(SAFETY), ['safety'])
        self.assertEqual(document_tags('전자정부법'), [])
        self.assertEqual(document_tags(DISCLOSURE + ' 시행규칙'), ['public_data'])
        self.assertNotIn('edges', PROFILE)

    def test_cases_have_independent_official_endpoint_proofs(self):
        self.assertEqual(len(PROFILE['cases']), 3)
        self.assertEqual(len(CASE_PROOFS), 3)
        cases = {(c[0], c[1]) for c in PROFILE['cases']}
        for proof in CASE_PROOFS:
            self.assertIn(proof['source_law'], STATUTES)
            self.assertIn(proof['target_law'], STATUTES)
            self.assertEqual(proof['target_kind'], 'article')
            self.assertTrue(proof['url'].startswith('https://'))
            self.assertIn('law.go.kr/', proof['url'])
            self.assertTrue((proof['source_law'], proof['source_jo']) in cases
                            or (proof['target_law'], proof['target_ref'].split('조')[0][1:]) in cases)
        self.assertEqual(PROFILE['sectors']['all'], '전체 연결')
        self.assertEqual(PROFILE['default_refs']['all'], '제17조')
        self.assertTrue(all(c[0] in STATUTES for c in PROFILE['cases']))
        self.assertEqual(set(CASE_EXPECTATIONS), cases)
        self.assertEqual(PROFILE['case_expectations'], CASE_EXPECTATIONS)
        for expectations in CASE_EXPECTATIONS.values():
            self.assertTrue(expectations)
            for proof in expectations:
                self.assertEqual(proof['target_ref'].split('조')[0][1:], proof['target_jo'])


if __name__ == '__main__':
    unittest.main()
