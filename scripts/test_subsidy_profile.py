"""Fail-closed scope and source-first subsidy citation fixtures.

Excerpts were frozen from linked official pages before live app collection.
They test extraction only; live corpus/edition and reverse-link tests are separate.
"""
import json
import os
from pathlib import Path
import unittest

from core.citation_parser import parse_citations
from core.subsidy_profile import (
    PROFILE, NATIONAL, LOCAL, REFUND, STATUTES, RULES, CENTRAL_RULES,
    selected, document_authorities, document_tags, article_tags,
)

# No application edge/result was used to choose these expected destinations.
SOURCE_FIXTURES = (
    dict(
        owner='보조사업 정산보고서 검증지침', jo='1', effective='20241022',
        url='https://www.law.go.kr/LSW/admRulInfoP.do?admRulSeq=2100000248440',
        text='이 지침은 「보조금 관리에 관한 법률」 제27조제2항과 「보조금 관리에 관한 법률 시행령」 제12조의2의 정산보고서 검증에 관한 세부적인 사항을 규정함을 목적으로 한다.',
        expected=((NATIONAL, '27', '', '2'), (NATIONAL+' 시행령', '12', '2', '')),
        annex=(),
    ),
    dict(
        owner='보조사업자 정보공시 세부기준', jo='2', effective='20260304',
        url='https://www.law.go.kr/admRulInfoP.do?admRulSeq=2100000275314',
        text='보조사업자 또는 간접보조사업자는 「보조금 관리에 관한 법률」 제26조의10제1항 및 「보조금 관리에 관한 법률 시행령」 제11조의2에 따라 보조사업 또는 간접보조사업 관련 정보를 공시하여야 한다.',
        expected=((NATIONAL, '26', '10', '1'), (NATIONAL+' 시행령', '11', '2', '')),
        annex=(),
    ),
    dict(
        owner=NATIONAL+' 시행령', jo='14의2', effective='20260102',
        url='https://www.law.go.kr/lsLinkProc.do?chrClsCd=010202&datClsCd=010102&gubun=admRul&joNo=001402000&lsId=49925&mode=10',
        text='법 제33조의2제1항 각 호 외의 부분 본문에 따른 제재부가금(이하 "제재부가금"이라 한다)의 부과기준은 별표 8과 같다.',
        expected=(('법', '33', '2', '1'),), annex=('별표 8',),
    ),
    dict(
        owner=LOCAL+' 시행규칙', jo='3', effective='20231213',
        url='https://law.go.kr/lsLinkCommonInfo.do?chrClsCd=010202&lspttninfSeq=170031',
        text='① 법 제17조제1항 각 호 외의 부분 본문에 따른 실적보고서의 형식, 작성방법 및 항목은 별지 제2호서식에 따른다.\n② 지방보조사업자는 별지 제2호서식의 실적보고서에 다음 각 호의 서류를 첨부하여 지방자치단체의 장에게 제출해야 한다.\n1. 별지 제3호서식의 지방보조사업 정산보고서',
        expected=(('법', '17', '', '1'),), annex=('별지 제2호서식', '별지 제3호서식'),
    ),
    dict(
        owner=REFUND+' 시행령', jo='3', effective='20240927',
        url='https://www.law.go.kr/LSW/lsSideInfoP.do?docCls=jo&joBrNo=00&joNo=0003&lsiSeq=265453&urlMode=lsScJoRltInfoR',
        text='법 제8조제1항에서 “대통령령으로 정하는 이자”란 부정이익 가액에 「국세기본법 시행령」 제43조의3제2항에 따른 이자율을 곱하여 산정한 금액을 말한다.',
        expected=(('법', '8', '', '1'), ('국세기본법 시행령', '43', '3', '2')),
        annex=(),
    ),
)


class SubsidyScopeTests(unittest.TestCase):
    def test_exact_real_families_do_not_invent_implementing_rules(self):
        self.assertEqual(len(STATUTES), 7)
        self.assertEqual(len(RULES), 7)
        self.assertEqual(len(set(STATUTES+RULES)), 14)
        self.assertEqual(set(PROFILE['required']), set(STATUTES))
        self.assertEqual(set(PROFILE['required_rules']), set(RULES))
        for base in (NATIONAL, REFUND):
            self.assertNotIn(base+' 시행규칙', STATUTES)
            self.assertFalse(selected(base+' 시행규칙', '기획예산처', 'eflaw'))

    def test_authority_is_checked_per_document_not_as_one_combined_union(self):
        for name in STATUTES+RULES:
            provider='eflaw' if name in STATUTES else 'admrul'
            expected=document_authorities(name, provider)
            self.assertEqual(len(expected), 1, name)
            owner=next(iter(expected))
            self.assertTrue(selected(name, owner, provider), name)
            for wrong in ('재정경제부', '기획재정부', '기획예산처', '행정안전부', '국민권익위원회'):
                if wrong!=owner:
                    self.assertFalse(selected(name, wrong, provider), (name, wrong))
            self.assertFalse(selected(name, owner+',재정경제부', provider), name)
            self.assertFalse(selected(name, '', provider), name)

    def test_provider_and_unapproved_department_programs_are_excluded(self):
        self.assertFalse(selected(NATIONAL, '기획예산처', 'admrul'))
        self.assertFalse(selected(CENTRAL_RULES[0], '기획예산처', 'eflaw'))
        for name, authority, provider in (
            ('기획예산처 공무원 행동강령', '기획예산처', 'admrul'),
            ('고용노동분야 국고보조사업 관리규정', '고용노동부', 'admrul'),
            ('지방보조금통합관리망의 관리 및 운영에 관한 규칙', '행정안전부', 'eflaw'),
            ('국가재정법', '기획예산처', 'eflaw'),
            ('서울특별시 지방보조금 관리 조례', '서울특별시', 'ordin'),
        ):
            self.assertFalse(selected(name, authority, provider), name)

    def test_navigation_keeps_owner_and_cross_topics_without_creating_relations(self):
        self.assertEqual(document_tags(NATIONAL), ['national'])
        self.assertEqual(document_tags(LOCAL+' 시행규칙'), ['local'])
        self.assertEqual(document_tags(REFUND), ['control'])
        self.assertEqual(document_tags('국세기본법'), [])
        self.assertEqual(set(article_tags(LOCAL, dict(title='정산과 반환', text='검증보고서와 정보공시'))),
                         {'local', 'settlement', 'control'})
        self.assertEqual(article_tags(NATIONAL, dict(title='목적', text='목적을 정한다.')), ['national'])

    def test_questions_include_three_different_real_source_chains(self):
        cases={(case[0],case[1]) for case in PROFILE['cases']}
        self.assertTrue({(NATIONAL, '27'), (NATIONAL, '33의2'), (LOCAL, '17')}.issubset(cases))
        self.assertEqual(PROFILE['default_refs']['all'], '제27조')
        self.assertEqual(PROFILE['sectors']['all'], '전체 연결')


class SubsidyFrozenSourceTests(unittest.TestCase):
    def test_numbered_quotes_have_exact_destinations_and_verifiable_spans(self):
        for fixture in SOURCE_FIXTURES:
            with self.subTest(owner=fixture['owner'], jo=fixture['jo']):
                cites=parse_citations(fixture['text'])
                actual={(c.law_name,c.jo,c.jo_sub,c.hang) for c in cites if not c.byeolpyo}
                self.assertEqual(actual, set(fixture['expected']))
                self.assertEqual({c.byeolpyo for c in cites if c.byeolpyo}, set(fixture['annex']))
                for cite in cites:
                    self.assertEqual(fixture['text'][cite.span[0]:cite.span[1]], cite.raw)

    def test_source_numbers_are_not_treated_as_grant_eligibility_or_sum(self):
        self.assertEqual(parse_citations('지원금 1천만원, 회계연도 2026년, 보조율 50%'), [])
        self.assertEqual(parse_citations('중앙 보조금과 지방 보조금은 정산을 한다.'), [])


class SubsidyCollectedSourceTests(unittest.TestCase):
    """Optional offline recheck of staged live data against preselected sources."""

    @classmethod
    def setUpClass(cls):
        from core.mofe_collection import prepare_source
        from core.mofe_universe import build_graph, validate_bundle
        from core.procurement_universe import documents
        candidate=Path(__file__).resolve().parents[1]/'output/subsidy-candidate-20261004/source.json'
        cls.source_path=Path(os.environ.get('SUBSIDY_SOURCE', str(candidate)))
        if not cls.source_path.is_file():
            raise unittest.SkipTest('No staged subsidy source; frozen official-source checks still run')
        cls.source=prepare_source(json.loads(cls.source_path.read_text(encoding='utf-8')))
        cls.graph=build_graph(cls.source)
        cls.bundle=validate_bundle(dict(source=cls.source, graph=cls.graph), 'subsidy')
        cls.docs={d['name']:d for d in documents(cls.source)}

    def test_all_fourteen_declared_sources_have_verified_current_bodies(self):
        self.assertEqual(set(self.docs), set(STATUTES+RULES))
        for document in self.docs.values():
            self.assertTrue(selected(document['name'], document['managing_authority'], document['provider']))
            self.assertEqual(document['state'], 'current-body-verified')
            self.assertLessEqual(document['effective'], self.source['built_at'])
            self.assertTrue(document['articles'], document['name'])

    def test_five_preselected_source_chains_have_exact_spans_reverse_rows_and_bodies(self):
        from core.citation_scope import parse_target, Provision
        from core.galaxy_focus import analyze_focus
        from core.mofe_universe import article_for
        # Destination and quote expectations come from the frozen official sources,
        # not from graph results. Parent-law resolution is checked independently.
        expected=(
            ('보조사업 정산보고서 검증지침','1',NATIONAL,'제27조제2항','「보조금 관리에 관한 법률」 제27조제2항'),
            (NATIONAL+' 시행령','14의2',NATIONAL,'제33조의2제1항','법 제33조의2제1항'),
            (LOCAL+' 시행규칙','3',LOCAL,'제17조제1항','법 제17조제1항'),
            ('보조사업자 정보공시 세부기준','2',NATIONAL,'제26조의10제1항','「보조금 관리에 관한 법률」 제26조의10제1항'),
            (REFUND+' 시행령','3',REFUND,'제8조제1항','법 제8조제1항'),
        )
        for owner,jo,target,reference,raw in expected:
            with self.subTest(owner=owner,jo=jo):
                article=next(a for a in self.docs[owner]['articles'] if a['jo']==jo)
                self.assertIn(raw, article['text'])
                matches=[e for e in self.graph['edges'] if
                         (e['source_law'],e['source_jo'],e['target_law'],e['target_ref'],e['cite_raw'])
                         ==(owner,jo,target,reference,raw)]
                self.assertTrue(matches, (owner,jo,target,reference))
                target_jo=parse_target(reference).jo
                rows=analyze_focus(target,Provision(target_jo).label,self.graph)['rows']
                for edge in matches:
                    self.assertEqual(article['text'][edge['source_start']:edge['source_end']],raw)
                    self.assertTrue(any(r['evidence_id']==edge['evidence_id']
                                        and r['direction']=='reverse' and r['neighbor_law']==owner
                                        and r['neighbor_jo']==jo for r in rows))
                _,body=article_for(self.bundle,owner,Provision(jo).label)
                self.assertEqual(body['text'],article['text'])
                _,target_body=article_for(self.bundle,target,reference)
                self.assertEqual(target_body['jo'],target_jo)
                self.assertTrue(target_body['text'])

    def test_annex_numbers_have_real_metadata_and_official_original_urls(self):
        expected=((NATIONAL+' 시행령','14의2','별표 8'),
                  (LOCAL+' 시행규칙','3','별지 제2호서식'),
                  (LOCAL+' 시행규칙','3','별지 제3호서식'))
        for owner,jo,reference in expected:
            with self.subTest(owner=owner,reference=reference):
                edges=[e for e in self.graph['edges'] if e['source_law']==owner
                       and e['source_jo']==jo and e['target_law']==owner
                       and e['target_kind']=='annex' and e['target_ref']==reference]
                self.assertTrue(edges)
                annex=next(a for a in self.docs[owner]['annexes'] if a['ref']==reference)
                self.assertTrue(annex['title'])
                self.assertTrue(annex['urls'])
                self.assertTrue(all(url.startswith(('https://www.law.go.kr/','https://law.go.kr/',
                                                   'http://www.law.go.kr/','http://law.go.kr/'))
                                    for url in annex['urls']))

    def test_tax_interest_rate_reference_remains_explicitly_uncollected(self):
        owner=REFUND+' 시행령';target='국세기본법 시행령';reference='제43조의3제2항'
        self.assertNotIn(target,self.docs)
        rows=[e for e in self.graph['external_references'] if e['source_law']==owner
              and e['source_jo']=='3' and e['target_law']==target and e['target_ref']==reference]
        self.assertTrue(rows)
        self.assertTrue(all(e['target_status']=='not-collected' for e in rows))
        self.assertFalse(any(e['target_law']==target for e in self.graph['edges']))


if __name__=='__main__':
    unittest.main()
