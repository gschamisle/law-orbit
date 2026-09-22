"""Meaningful boundaries for guidance reuse and the independent contract pair."""
from copy import deepcopy
import unittest
import json

from core.ftc_text_citations import collect_text_citations, validate_text_citations
from core.forex_finance_links import bridge
from scripts.test_forex_finance_links import fixture
from scripts.build_forex_finance_site import payloads


def guidance(domain, body):
    law = dict(uid='law', name='국가회계기준에 관한 규칙', provider='eflaw',
               category=domain, effective='20260901', source_url='https://www.law.go.kr/',
               articles=[dict(jo=n, text='제'+n+'조(기준) 내용') for n in ('3','4','4의2','5')])
    rule = dict(uid='rule', name='회계처리지침', provider='admrul', category=domain,
                effective='20260901', source_url='https://www.law.go.kr/',
                articles=[], raw_body_blocks=[body])
    return dict(domain=domain, laws=[law], administrative_rules=[rule])


class GuidanceReuseTests(unittest.TestCase):
    def test_numeric_heading_alias_range_and_real_offsets(self):
        source=guidance('treasury', '1. (목적) 「국가회계기준에 관한 규칙」(이하 “규칙”이라 한다) 제3조제2항에 따른다.\n'
                        '2. (범위) 규칙 제3조부터 제5조까지 따른다.\n부칙\n규칙 제3조를 준용한다.')
        rows, issues=collect_text_citations(source, profile='treasury')
        validate_text_citations(source, rows)
        self.assertEqual(len(rows),5)
        self.assertIn('제4조의2',{r['target_ref'] for r in rows})
        self.assertTrue(all(r['source_jo']=='' and r['source_ref'].startswith(('1.','2.')) for r in rows))
        self.assertEqual(source['administrative_rules'][0]['articles'],[])
        self.assertEqual(issues,[])
        broken=deepcopy(rows);broken[0]['source_end']-=1
        with self.assertRaises(ValueError):validate_text_citations(source,broken)

    def test_relative_owner_cannot_leak_across_numbered_items(self):
        source=guidance('treasury','1. 기준\n「국가회계기준에 관한 규칙」 제3조에 따른다.\n2. 다른 기준\n같은 규칙 제4조에 따른다.')
        rows, issues=collect_text_citations(source, profile='treasury')
        self.assertEqual([r['target_ref'] for r in rows],['제3조'])
        self.assertTrue(any('미해결' in i['reason'] for i in issues))

    def test_missing_body_missing_target_and_internal_items_not_success(self):
        source=guidance('procurement','□ 근거규정\n「국가회계기준에 관한 규칙」 제999조에 따른다.\n2. 이 지침 3.에 따른다.')
        source['administrative_rules'].append({**deepcopy(source['administrative_rules'][0]),'uid':'empty','name':'첨부 예규','raw_body_blocks':[]})
        rows, issues=collect_text_citations(source, profile='procurement')
        self.assertEqual(rows,[])
        self.assertTrue(any('대상 조문 없음' in i['reason'] for i in issues))
        self.assertNotIn('text_analysis',source['administrative_rules'][1])
        self.assertEqual(source['administrative_rules'][0]['text_analysis']['internal_paragraph_references'],'not-analyzed')

    def test_profile_scope_is_explicit(self):
        with self.assertRaises(ValueError):collect_text_citations(guidance('tax','1. 본문'),profile='tax')
        with self.assertRaises(ValueError):collect_text_citations(guidance('treasury','1. 본문'),profile='procurement')


class ContractPairTests(unittest.TestCase):
    def contract_fixture(self):
        old,fx,fin=fixture()
        # This pair uses ordinary article numbering, unlike forex's 5-1 format.
        old=json.loads(json.dumps(old,ensure_ascii=False).replace('7-36','7').replace('5-1','6'))
        fx=old['forex']['entries'][0];fin=old['fsc']['entries'][0]
        mapping={'forex':'procurement','fsc':'public_institutions'}
        snapshots={mapping[k]:v for k,v in old.items()}
        for domain,snap in snapshots.items():
            for entry in snap['entries']:
                entry['domain']=domain
                snap['documents'][entry['id']]['meta']['domain']=domain
        return snapshots,fx,fin

    def test_same_engine_keeps_bidirectional_scope_and_inputs(self):
        source,contract,institution=self.contract_fixture();before=deepcopy(source)
        result=bridge(source,pair=('procurement','public_institutions'))
        self.assertEqual(source,before)
        exported=payloads(result,source)
        self.assertEqual(exported['procurement']['kind'],'procurement-public-bridge')
        self.assertEqual(exported['procurement']['peer'],'public_institutions')
        # Article ranges still include branch articles. Read destinations remain in the peer.
        reverse=exported['public_institutions']['laws'][institution['id']]['3의2']['rows']
        self.assertEqual(reverse[0]['neighbor_id'],contract['id'])
        self.assertEqual(reverse[0]['neighbor_domain'],'procurement')
        self.assertEqual(reverse[0]['direction'],'reverse')

    def test_no_arbitrary_pair_or_edition_fallback(self):
        source,contract,_=self.contract_fixture()
        with self.assertRaises(ValueError):bridge(source)
        source['procurement']['documents'][contract['id']]['meta']['effective']='19990101'
        with self.assertRaisesRegex(ValueError,'edition mismatch'):
            bridge(source,pair=('procurement','public_institutions'))


if __name__=='__main__':unittest.main()
