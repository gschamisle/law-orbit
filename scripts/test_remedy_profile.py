"""Procedural boundaries, exclusion/준용 coexistence and source-bound notes."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from core.remedy_profile import PROFILE, STATUTES, OWNERS, APPEAL, TAX, CUSTOMS, LOCAL, LABOR, COMMISSION, HEALTH, MEDICAL_AID, LITIGATION, selected
from core.remedy_relations import reading_guide, validate_guide, procedural_edge, procedural_article
from core.remedy_profile import BASIC, INFORMATION, COMPETITION, GREENBELT, REGIONAL, JEJU
from core.candidate_evidence import case_proof


class RemedyTests(unittest.TestCase):
    def test_selected_unanalyzed_property_procedure_recovers_exact_law_reference(self):
        from core.forex_finance_links import bridge
        from scripts.build_static_galaxies import ident
        snaps={d:dict(entries=[],documents={},details={},built_at='20261013') for d in ('remedy','state_property')}
        for domain,name,items in (
            ('remedy',APPEAL,[('3','제3조(대상) 행정심판의 대상')]),
            ('state_property',REGIONAL,[('78','제78조(행정심판) 「행정심판법」에 따라 행정심판을 제기할 수 있다.'),
                                       ('77','제77조(범위 밖) 「행정심판법」을 참조한다.')]),
        ):
            entry=dict(id=ident(domain,'',name),name=name,label=name,domain=domain,effective='20261013',url='https://www.law.go.kr/',articles=len(items))
            articles=[dict(jo=jo,title='예시',text=body) for jo,body in items]
            snaps[domain]['entries'].append(entry)
            snaps[domain]['documents'][entry['id']]=dict(meta=entry.copy(),articles=articles)
            snaps[domain]['details'][entry['id']]={jo:dict(rows=[],external=[],issues=[],analysis_error='선택 분석 범위 밖') for jo,_ in items}
        before=deepcopy(snaps)
        result=bridge(snaps,pair=('remedy','state_property'))
        self.assertEqual(snaps,before)
        self.assertEqual(len(result['graph']['edges']),1)
        edge=result['graph']['edges'][0]
        self.assertEqual((edge['source_jo'],edge['target_law'],edge['target_kind']),('78',APPEAL,'law'))
        self.assertEqual(edge['cite_raw'],'「행정심판법」')
        self.assertEqual(edge['target_ref'],'법령·정의 참조')

    def test_replaced_bridge_group_retires_only_its_wrapper(self):
        import tempfile
        from scripts.build_static_galaxies import Writer, ROOT
        from scripts.build_integrity_links_site import retire_replaced_groups
        (ROOT / 'output').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT/'output') as folder:
            root=Path(folder);writer=Writer(root)
            one=writer.data(dict(kind='old-bridge',body='preserve'))
            two=writer.data(dict(kind='new-bridge',body='new'))
            before=writer.data(dict(kind='domain-bridge-set',bridges=[one]))
            after=writer.data(dict(kind='domain-bridge-set',bridges=[one,two]))
            original={'cross_domain':{'peer':before}}
            current={'cross_domain':{'peer':after}}
            raw=(root/one['url']).read_bytes()
            self.assertEqual(retire_replaced_groups(root,original,current),[before['url']])
            self.assertFalse((root/before['url']).exists())
            self.assertEqual((root/one['url']).read_bytes(),raw)
            self.assertTrue((root/after['url']).exists())
            before=writer.data(dict(kind='domain-bridge-set',bridges=[one]))
            with self.assertRaises(ValueError):
                retire_replaced_groups(root,original,{'cross_domain':{'peer':two}})
            self.assertTrue((root/one['url']).exists())

    def test_declared_scope_is_not_all_tribunals(self):
        self.assertEqual(len(STATUTES), 18)
        for law, owner in OWNERS.items():
            self.assertTrue(selected(law, owner, 'eflaw'))
            self.assertFalse(selected(law, owner, 'admrul'))
            self.assertFalse(selected(law, owner+',기획예산처', 'eflaw'))
        for law in ('특허법', '국가공무원법', '산업재해보상보험법', '고용보험법', '노인장기요양보험법'):
            self.assertFalse(selected(law, '국민권익위원회', 'eflaw'))

    def test_procedural_overlay_does_not_pull_in_tax_investigation_or_tariffs(self):
        for law, jo in ((TAX,'56'),(CUSTOMS,'120'),(LOCAL,'98'),(COMMISSION,'15의3'),(LABOR,'31'),(HEALTH,'88'),(MEDICAL_AID,'30의2')):
            self.assertTrue(procedural_article(law, jo))
        for law, jo in ((TAX,'81의15'),(CUSTOMS,'56'),(LABOR,'88'),(LOCAL,'116'),(HEALTH,'66')):
            self.assertFalse(procedural_article(law, jo))
        self.assertFalse(procedural_edge(dict(source_law=LABOR,source_jo='2',target_law=TAX,target_ref='제2조',target_kind='article')))
        self.assertTrue(procedural_edge(dict(source_law='국세기본법 시행령',source_jo='46',target_law=TAX,target_ref='제56조제1항',target_kind='article')))

    def test_law_reference_proof_never_invents_article(self):
        req=dict(source_law=LABOR,source_jo='31',target_law=LITIGATION,target_kind='law',quote_contains='행정소송법')
        edge={**req,'cite_raw':'「행정소송법」','evidence_id':'law-only'}
        graph={'edges':[edge]}
        known={(LABOR,'31'),(LITIGATION,'18')}
        self.assertTrue(case_proof(graph,[req],known_articles=known)['available'])
        self.assertFalse(case_proof(graph,[{**req,'target_kind':'article','target_jo':'18'}],known_articles=known)['available'])
        self.assertFalse(case_proof(graph,[req],known_articles={(LABOR,'31')})['available'])

    def test_expansion_does_not_treat_whole_laws_as_appeal_procedures(self):
        for law, jo in ((BASIC,'36'),(INFORMATION,'19'),(COMPETITION,'100'),(GREENBELT,'27'),(REGIONAL,'78'),(JEJU,'350')):
            self.assertTrue(procedural_article(law, jo))
            self.assertFalse(procedural_article(law, '2'))
        self.assertFalse(procedural_article('폐기물관리법', '48의4'))
        self.assertFalse(procedural_article(COMPETITION, '98'))
        self.assertFalse(procedural_edge(dict(source_law=JEJU, source_jo='200', target_law=TAX, target_kind='article', target_ref='제2조')))

    def test_reviewed_exception_requires_exact_context_without_clearing_flag(self):
        req=dict(source_law=GREENBELT, source_jo='27', target_law=APPEAL, target_jo='6')
        context='② 제1항에 따른 이의신청에 대하여는 「행정심판법」 제6조에도 불구하고 중앙토지수용위원회가 심리ㆍ의결하여 재결한다.'
        edge={**req,'target_kind':'article','target_ref':'제6조','type':'direct',
              'context_review':True,'target_provision_status':'collected','context':context,'evidence_id':'exception'}
        graph={'edges':[edge]}
        self.assertFalse(case_proof(graph,[req])['available'])
        checked={**req,'reviewed_context':context}
        self.assertTrue(case_proof(graph,[checked])['available'])
        self.assertTrue(edge['context_review'])
        edge['context']=context.replace('제1항','제2항')
        self.assertFalse(case_proof(graph,[checked])['available'])
        edge['context']=context;edge['target_provision_status']='historical-edition-not-verified'
        self.assertFalse(case_proof(graph,[checked])['available'])


ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'output/remedy-candidate-20261013/source.json'


@unittest.skipUnless(SOURCE.is_file(), 'Optional collected remedy snapshot is absent')
class CollectedRemedyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from core.mofe_collection import prepare_source
        from core.mofe_universe import build_graph, validate_bundle, assessment
        cls.source=prepare_source(json.loads(SOURCE.read_text(encoding='utf8')))
        cls.bundle=validate_bundle(dict(source=cls.source,graph=build_graph(cls.source)),'remedy')
        cls.assessment=assessment(cls.bundle)
        cls.guide=reading_guide(cls.source['laws'])

    def test_all_work_questions_have_real_evidence(self):
        self.assertEqual(self.assessment['decision'],'limited-release')
        self.assertEqual(len(self.assessment['cases']),12)
        self.assertTrue(all(c['case_proof']['available'] for c in self.assessment['cases']))
        self.assertEqual(self.assessment['target_article_unavailable'],0)
        self.assertEqual(self.assessment['unindexed'],[])
        self.assertEqual({d['name'] for d in self.source['laws']},set(STATUTES))

    def test_notes_quote_checked_paragraphs_not_inferred_routes(self):
        validate_guide(self.guide,self.source['laws'])
        tax=next(r for r in self.guide['entries'] if r['law']==TAX and r['scope']=='제56조제1항')
        self.assertEqual(tax['labels'],['적용 제외','일부 준용'])
        self.assertIn('적용하지 아니한다',tax['quote'])
        self.assertIn('준용하며',tax['quote'])
        self.assertFalse(self.guide['is_citation'])
        changed=deepcopy(self.guide);changed['entries'][0]['summary']='일반 행정심판이면 모두 적용'
        with self.assertRaises(ValueError):validate_guide(changed,self.source['laws'])
        source=deepcopy(self.source['laws'])
        law=next(d for d in source if d['name']==TAX)
        a=next(a for a in law['articles'] if a['jo']=='56')
        a['text']=a['text'].replace('적용하지 아니한다','적용한다')
        with self.assertRaises(ValueError):reading_guide(source)

    def test_full_exception_list_and_jurisdiction_conditions_are_bound(self):
        basic=next(r for r in self.guide['entries'] if r['law']==BASIC)
        self.assertIn('⑧', basic['quote'])
        self.assertIn('6. 과태료', basic['quote'])
        green=next(r for r in self.guide['entries'] if r['law']==GREENBELT)
        self.assertIn('매수가격', green['quote'])
        self.assertIn('부담금', green['quote'])
        source=deepcopy(self.source['laws'])
        article=next(a for d in source if d['name']==BASIC for a in d['articles'] if a['jo']=='36')
        article['text']=article['text'].replace('6. 과태료 부과 및 징수에 관한 사항', '')
        with self.assertRaises(ValueError): validate_guide(self.guide,source)


if __name__=='__main__':unittest.main()
