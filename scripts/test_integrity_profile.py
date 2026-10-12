"""Official excerpts selected before collection, plus optional live snapshot checks."""
import json
from pathlib import Path
import unittest
from core.citation_parser import parse_citations
from core.integrity_profile import PROFILE, BASES, CODES, STATUTES, GRAFT, CONFLICT, REFUND, REPORT, ANTICORRUPTION, selected, article_tags

# Official current MSTs checked 2026-10-12: 287511, 281815, 290539.
FIXTURES = (
    ('287511', '17', '법 제8조제3항제2호 본문에서 "대통령령으로 정하는 가액 범위"란 별표 1에 따른 금액을 말한다.',
     {('법', '8', '', '3')}, {'별표 1'}),
    ('281815', '14', '법 제12조제1항 각 호 외의 부분 단서에서 "해당 물품의 생산자가 1명뿐인 경우 등 대통령령으로 정하는 불가피한 사유가 있는 경우"란 「국가를 당사자로 하는 계약에 관한 법률 시행령」 제26조제1항제2호 또는 「지방자치단체를 당사자로 하는 계약에 관한 법률 시행령」 제25조제1항제4호에 해당하는 경우를 말한다.',
     {('법', '12', '', '1'), ('국가를 당사자로 하는 계약에 관한 법률 시행령', '26', '', '1'), ('지방자치단체를 당사자로 하는 계약에 관한 법률 시행령', '25', '', '1')}, set()),
    ('290539', '48', '법 제46조에 따른 시정권고 또는 의견표명은 다음 각 호의 사항을 명시한 서면으로 하여야 한다.',
     {('법', '46', '', '')}, set()),
)


class IntegrityScopeTests(unittest.TestCase):
    def test_exact_owner_and_presidential_codes_not_institutional_rules(self):
        self.assertEqual(len(STATUTES), 12)
        for name in STATUTES:
            self.assertTrue(selected(name, '국민권익위원회', 'eflaw'))
            for owner in ('', '재정경제부', '행정안전부', '국민권익위원회,행정안전부'):
                self.assertFalse(selected(name, owner, 'eflaw'))
            self.assertFalse(selected(name, '국민권익위원회', 'admrul'))
        for name in ('금융위원회 공무원 행동강령', '행정심판법', '국민권익위원회와 그 소속기관 직제', GRAFT+' 시행규칙'):
            self.assertFalse(selected(name, '국민권익위원회', 'eflaw'))

    def test_grievance_is_not_tagged_as_reporting_without_words(self):
        self.assertEqual(article_tags(ANTICORRUPTION, {'title': '시정의 권고', 'text': '고충민원에 관한 내용'}), ['grievance'])
        self.assertEqual(parse_citations('공익 침해가 걱정되므로 신고와 상담을 고려한다.'), [])

    def test_official_source_destinations_and_positions(self):
        for mst, jo, text, expected, annex in FIXTURES:
            with self.subTest(mst=mst, jo=jo):
                cites = parse_citations(text)
                self.assertEqual({(c.law_name,c.jo,c.jo_sub,c.hang) for c in cites if not c.byeolpyo}, expected)
                self.assertEqual({c.byeolpyo for c in cites if c.byeolpyo}, annex)
                for c in cites:self.assertEqual(text[c.span[0]:c.span[1]], c.raw)

    def test_preselected_work_questions_require_evidence(self):
        from core.candidate_evidence import case_proof
        for key, expected in PROFILE['case_expectations'].items():
            self.assertFalse(case_proof({'edges':[]}, expected)['available'], key)
        self.assertEqual(len(PROFILE['case_expectations']), 5)


class IntegrityCollectedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=Path(__file__).resolve().parents[1]/'output/integrity-candidate-20261012/validated-bundle.json'
        if not path.exists():raise unittest.SkipTest('Optional collected integrity snapshot not present')
        from core.mofe_universe import load_bundle, assessment
        cls.bundle=load_bundle('integrity',path)
        cls.assessment=assessment(cls.bundle)
        cls.docs={d['name']:d for d in cls.bundle['source']['laws']}

    def test_all_declared_bodies_and_source_dates(self):
        self.assertEqual(set(self.docs),set(STATUTES))
        self.assertTrue(all(d['articles'] for d in self.docs.values()))
        self.assertTrue(all(d['effective']<='20261012' for d in self.docs.values()))
        for code in CODES:self.assertEqual(self.docs[code]['kind'],'대통령령')
        self.assertEqual(self.assessment['target_article_unavailable'],0)
        self.assertEqual(self.assessment['unindexed'],[])

    def test_all_five_official_chains_reproduced_and_quotes_match(self):
        self.assertEqual(self.assessment['decision'],'limited-release')
        self.assertTrue(all(c['available'] for c in self.assessment['cases']))
        evidence={e['evidence_id']:e for e in self.bundle['graph']['edges']}
        for case in self.assessment['cases']:
            for eid in case['case_proof']['evidence_ids']:
                edge=evidence[eid]
                a=next(a for a in self.docs[edge['source_law']]['articles'] if a['jo']==edge['source_jo'])
                self.assertEqual(a['text'][edge['source_start']:edge['source_end']],edge['cite_raw'])
        # The range/준용 relationship is actually extracted, not an editorial link.
        edges=list(evidence.values())
        self.assertTrue(any(e['source_law']==GRAFT and e['source_jo']=='15' and e['target_law']==REPORT and e['target_ref'].startswith('제11조') for e in edges))

    def test_annexes_remain_official_links_without_inner_text_inference(self):
        annexes=self.docs[GRAFT+' 시행령']['annexes']
        self.assertTrue(annexes)
        self.assertFalse(any(a.get('analysis') for a in annexes))


if __name__=='__main__':unittest.main()
