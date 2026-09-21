"""Fail-closed scope and cross-document evidence checks for MOFE profiles."""
import unittest
from copy import deepcopy
from core.mofe_profiles import selected,PROFILES,PUBLIC
from core.mofe_collection import prepare_source,discover_inventory
from core.mofe_universe import build_graph,validate_bundle,load_bundle,mark_sector
from core.fsc_collection import CollectionError

def fixture():
    d=dict(name=PUBLIC,provider='eflaw',uid='eflaw:1',category='public_institutions',kind='법률',
           effective='20260102',managing_authority='재정경제부',short_name='공공기관운영법',annexes=[],
           source_url='https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=1',
           articles=[dict(jo=str(n),title='회계',text=f'제{n}조(회계) 회계를 정한다.',blocks=[]) for n in [38,39,40]])
    r=dict(name='공기업·준정부기관 회계기준',provider='admrul',uid='admrul:2',category='public_institutions',
           kind='고시',effective='20260102',managing_authority='재정경제부',
           source_url='https://www.law.go.kr/LSW/admRulLsInfoP.do?admRulSeq=2',raw_body_blocks=[
           f'제1조(목적) 「{PUBLIC}」(이하 "법"이라 한다)에 따른다.\n'
           '제2조(회계) 법 제38조부터 제40조까지 적용한다.\n'
           '제3조(관리) 이 기준 제2조 및 「국가재정법」 제43조의2에 따른다.'])
    source=prepare_source(dict(domain='public_institutions',built_at='20260921',laws=[d],administrative_rules=[r],inventory={'scope':'fixture'}))
    return dict(source=source,graph=build_graph(source))

class ScopeTests(unittest.TestCase):
    def test_budget_ministry_is_excluded(self):
        for domain,p in PROFILES.items():
            self.assertFalse(selected(domain,p['required'][0],'기획예산처','eflaw'))
            self.assertFalse(selected(domain,p['required'][0],'재정경제부,기획예산처','eflaw'))
        self.assertFalse(selected('treasury','국고보조금 통합관리지침','기획예산처','admrul'))
    def test_public_scope_is_not_all_public_agencies(self):
        self.assertTrue(selected('public_institutions',PUBLIC,'재정경제부','eflaw'))
        for name in ['한국토지주택공사법','2020년 공공기관 지정 고시','공공기관의 조직과 정원에 관한 지침']:
            self.assertFalse(selected('public_institutions',name,'재정경제부','admrul'))
    def test_customs_personnel_excluded(self):
        self.assertTrue(selected('customs','수입통관 사무처리에 관한 고시','관세청','admrul'))
        self.assertFalse(selected('customs','관세청 공무원 행동강령','관세청','admrul'))
        self.assertFalse(selected('customs','관세법','금융위원회','eflaw'))
    def test_treasury_does_not_claim_budget_or_local_accounting(self):
        self.assertFalse(selected('treasury','국가재정법','재정경제부','eflaw'))
        self.assertFalse(selected('treasury','국고금 회계처리지침','행정안전부','admrul'))
        self.assertTrue(selected('treasury','국고금 회계처리지침','재정경제부','admrul'))
    def test_short_inventory_fails(self):
        with self.assertRaises(CollectionError):discover_inventory(lambda *a:b'<LawSearch><totalCnt>1</totalCnt><page>1</page></LawSearch>','customs','20260921')
    def test_required_documents_not_silently_omitted(self):
        def empty(endpoint,params):
            tag='LawSearch' if params['target']=='eflaw' else 'AdmRulSearch'
            return f'<{tag}><totalCnt>0</totalCnt><page>1</page></{tag}>'.encode()
        with self.assertRaisesRegex(CollectionError,'required-documents-missing'):discover_inventory(empty,'treasury','20260921')
    def test_missing_bundle_never_substitutes(self):
        with self.assertRaises(FileNotFoundError):load_bundle('customs','does-not-exist.json')
    def test_domain_mix_rejected(self):
        bundle=fixture()
        with self.assertRaises(ValueError):validate_bundle(bundle,'customs')
    def test_range_and_reverse_are_preserved(self):
        b=fixture();g=b['graph'];validate_bundle(b,'public_institutions')
        refs={e['target_ref'] for e in g['edges'] if e['source_law']!=PUBLIC and e['source_jo']=='2'}
        self.assertEqual(refs,{'제38조','제39조','제40조'})
        from core.galaxy_focus import analyze_focus
        result=analyze_focus(PUBLIC,'제39조',g)
        self.assertTrue(any(r['direction']=='reverse' and r['source_jo']=='2' for r in result['rows']))
    def test_external_budget_law_remains_uncollected(self):
        b=fixture();self.assertNotIn('국가재정법',b['graph']['laws'])
        self.assertTrue(any(e['target_law']=='국가재정법' and e['target_status']=='not-collected' for e in b['graph']['external_references']))
    def test_evidence_cannot_be_fabricated(self):
        b=fixture();b['graph']['edges'][0]['cite_raw']='꾸며낸 근거'
        with self.assertRaises(ValueError):validate_bundle(b,'public_institutions')
    def test_outside_sector_does_not_drop_links(self):
        from core.galaxy_focus import analyze_focus
        b=fixture();result=analyze_focus(PUBLIC,'제39조',b['graph'])
        marked=mark_sector(result,b['graph'],'contracts')
        self.assertEqual(len(result['rows']),len(marked['rows']))
        self.assertTrue(all(r['out_of_sector'] for r in marked['rows']))
    def test_unstructured_rule_is_not_indexed(self):
        b=fixture();s=b['source'];s['administrative_rules'][0]['raw_body_blocks']=['Ⅰ. 회계 처리\n1. 기준을 따른다.']
        s=prepare_source(s);self.assertEqual(s['administrative_rules'][0]['articles'],[])
        self.assertIn('미분석',s['administrative_rules'][0]['analysis_error'])


class ExplicitOwnerTests(unittest.TestCase):
    def adapter(self,body,name=PUBLIC,aliases=None,corpus=None):
        from core.fsc_administrative import adapter
        d=dict(name=name,category='public_institutions',provider='eflaw',citation_policy='mofe-explicit',aliases=aliases or {})
        a=dict(jo='1',text='제1조(목적) '+body)
        return adapter(d,a,corpus or []),a
    def test_same_law_decree_does_not_use_document_default(self):
        refs,_=self.adapter('「조세특례제한법」 제91조의23 및 같은 법 시행령 제93조의9에 따른다.',aliases={'법':'국채법'})
        self.assertTrue(any(e['target_name']=='조세특례제한법 시행령' and e['target_ref']=='제93조의9' for e in refs))
        self.assertFalse(any(e['target_name']=='국채법 시행령' for e in refs))
    def test_titled_range_retains_external_owner(self):
        refs,_=self.adapter('「형법」 제129조(수뢰)부터 제132조(알선수뢰)까지 적용한다.')
        self.assertTrue(any(e['target_name']=='형법' and e['via_range'] for e in refs))
        self.assertFalse(any(e['target_name']==PUBLIC for e in refs))
    def test_quoted_provision_not_guessed_as_own(self):
        refs,a=self.adapter('「국세기본법」 제21조 중 "제47조의4에 따른 가산세"로 본다.')
        self.assertFalse(any(e['target_name']==PUBLIC for e in refs))
        self.assertTrue(any('따옴표' in i['reason'] for i in a['citation_issues']))
    def test_number_in_document_title_is_not_an_article_citation(self):
        refs,_=self.adapter('「관세법 제226조에 따른 세관장확인물품 및 확인방법 지정고시」 제7조를 따른다.')
        self.assertEqual([r['target_ref'] for r in refs],['제7조'])
    def test_missing_article_is_review_not_phantom_node(self):
        refs,a=self.adapter('제999조에 따른다.',corpus=[dict(name=PUBLIC,articles=[dict(jo='1')])])
        self.assertEqual(refs,[])
        self.assertTrue(any('대상 조문 없음' in i['reason'] for i in a['citation_issues']))

class CollectedEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from core.mofe_universe import path
        if not all(path(d).is_file() for d in PROFILES):raise unittest.SkipTest('Requires three local MOFE snapshots')
        cls.bundles={d:load_bundle(d) for d in PROFILES}
    def test_every_case_has_reversible_cross_document_evidence(self):
        from core.galaxy_focus import analyze_focus
        from core.citation_scope import Provision
        for domain,b in self.bundles.items():
            for case in b['assessment']['cases']:
                self.assertTrue(case['available'],(domain,case['title']))
                edges={e['evidence_id']:e for e in b['graph']['edges']}
                for identity in case['evidence_ids']:
                    e=edges[identity];self.assertNotEqual(e['source_law'],e['target_law'])
                    forward=analyze_focus(e['source_law'],Provision(e['source_jo']).label,b['graph'])
                    self.assertTrue(any(r['evidence_id']==identity and r['direction']=='forward' for r in forward['rows']))
    def test_raw_offsets_ownership_and_no_missing_targets(self):
        from core.citation_scope import parse_target
        from core.mofe_universe import documents
        for domain,b in self.bundles.items():
            validate_bundle(b,domain)
            docs=documents(b['source']);indexed={(d['name'],a['jo']) for d in docs for a in d['articles']}
            for e in b['graph']['edges']:
                if e['target_kind']=='article':self.assertIn((e['target_law'],parse_target(e['target_ref']).jo),indexed)
            self.assertTrue(all(a.get('sectors') for d in docs for a in d['articles']))
            self.assertEqual(len(docs),b['assessment']['documents'])
    def test_real_aliases_not_assigned_to_the_rule_itself(self):
        g=self.bundles['public_institutions']['graph']
        for rule in ['공기업ㆍ준정부기관 계약사무규칙','공기업·준정부기관 총사업비관리지침']:
            self.assertTrue(any(e['source_law']==rule and e['target_law']==PUBLIC for e in g['edges']))
        g=self.bundles['treasury']['graph']
        self.assertTrue(any(e['source_law']=='개인투자용국채규정' and e['target_law']=='조세특례제한법 시행령' for e in g['external_references']))
    def test_unindexed_readable_without_invented_articles(self):
        from core.mofe_universe import documents
        for b in self.bundles.values():
            for d in documents(b['source']):
                if d['articles']:continue
                self.assertTrue(d.get('raw_body_blocks'))
                self.assertIn('미분석',d['analysis_error'])
                self.assertNotIn(d['name'],b['graph']['laws'])
class BrowserParityTests(unittest.TestCase):
    def test_new_domains_match_shared_engine_in_browser(self):
        from core.mofe_universe import path,documents
        from core.citation_scope import Provision
        from scripts.test_static_galaxies import browser,key
        from scripts.build_static_galaxies import EdgeIndex,tidy
        from core.galaxy_focus import analyze_focus
        if not all(path(d).is_file() for d in PROFILES):self.skipTest('Requires local snapshots')
        cases=[];expected=[]
        for domain in PROFILES:
            b=load_bundle(domain);g=b['graph'];index=EdgeIndex(g,documents(b['source']))
            for c in b['assessment']['cases']:
                for suffix in ('','제1항','제2항제1호'):
                    ref=Provision(c['jo']).label+suffix
                    full=analyze_focus(c['law'],ref,g)
                    self.assertEqual(index.focus(c['law'],ref)['rows'],full['rows'])
                    base=index.focus(c['law'],Provision(c['jo']).label)
                    cases.append(dict(rows=[tidy(r,{},False) for r in base['rows']],reference=ref,hyphen=False))
                    expected.append(sorted([key(r) for r in full['rows']],key=str))
        for case,actual,want in zip(cases,browser(cases),expected):self.assertEqual(sorted(actual,key=str),want,case['reference'])

if __name__=='__main__':unittest.main()
