"""Offline mutation tests for the independently authored tax sample verifier."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import json
import tempfile
from pathlib import Path

from scripts.verify_tax_citation_samples import Site, compare, structural_check, negative_control, authored_scopes, annex_key, main, ROOT


class MockSite:
    def __init__(self, quote):
        self.entries={name:{'name':name,'id':ident} for name,ident in
                      [('출발법','source-id'),('대상법','target-id'),('다른법','other-id')]}
        self.docs={name:{'meta':deepcopy(entry),'articles':[
            {'jo':jo,'text':'제'+jo+'조(저장된 대상)', 'effective':'20261004'}
            for jo in ('10','20','21','21의2','22','99')]} for name,entry in self.entries.items()}
        self.body='제1조(출발 조문)\n'+quote
        self.docs['출발법']['articles']=[{'jo':'1','text':self.body,'effective':'20261004'}]
        self.saved={'rows':[],'external':[],'issues':[]}
    def document(self,law):return self.docs[law]
    def article(self,law,jo):return next(a for a in self.document(law)['articles'] if a['jo']==jo)
    def detail(self,law,jo):return self.saved


def scope(path,end=None,axis=None):return [path,end or path,axis]


def row(site, quote, ref='제10조제1항제2호나목', jo='10', scopes=None, law='대상법', kind='article'):
    start=site.body.index(quote)
    return dict(source_law='출발법',source_jo='1',source_ref='제1조',source_id='source-id',
        source_start=start,source_end=start+len(quote),raw=quote,cite_raw=quote,
        target_law=law,target_id=site.entries.get(law,{}).get('id',''),target_kind=kind,
        target_ref=ref,target_ref_recorded=ref,direction='forward',status='review',
        neighbor_law=law,neighbor_id=site.entries.get(law,{}).get('id',''),
        neighbor_kind=kind,neighbor_jo=jo,neighbor_ref='제'+jo.replace('의','조의')+('' if '의' in jo else '조'),
        kind=kind,raw_scope={'scopes':scopes if scopes is not None else [scope(['10','1','2','나'])]},
        evidence_id='evidence')


def annotation(quote, expected=None):
    return dict(quote=quote,expected=expected or [dict(law='대상법',ref='제10조제1항제2호나목',kind='article')])


def codes(result):return {finding['code'] for error in result.get('row_errors',[]) for finding in error['findings']}


class TaxAuditVerifierTests(unittest.TestCase):
    def fixture(self):
        quote='「대상법」 제10조제1항제2호나목'
        site=MockSite(quote);site.saved['rows']=[row(site,quote)]
        return site,annotation(quote)

    def check(self,site,note,**kw):return compare(site,'출발법','1',note,**kw)

    def test_valid_record_and_review_status_pass_without_mutating_the_site(self):
        site,note=self.fixture();before=deepcopy(site.__dict__)
        self.assertEqual(self.check(site,note)['outcome'],'matched')
        self.assertEqual(site.__dict__,before)

    def test_correct_raw_scope_does_not_hide_wrong_declared_or_recorded_target(self):
        for field in ('target_ref','target_ref_recorded'):
            with self.subTest(field=field):
                site,note=self.fixture();site.saved['rows'][0][field]='제99조'
                result=self.check(site,note)
                self.assertEqual(result['outcome'],'unexpected-or-inconsistent-app-row')
                self.assertIn('recorded-reference-mismatch',codes(result))

    def test_actual_click_and_source_fields_are_checked_independently(self):
        for field,value in [('target_id','other-id'),('neighbor_id','other-id'),
                            ('neighbor_law','다른법'),('neighbor_jo','99'),
                            ('neighbor_ref','제99조'),('neighbor_kind','law'),
                            ('source_id','other-id'),('source_law','다른법'),('source_jo','99')]:
            with self.subTest(field=field):
                site,note=self.fixture();site.saved['rows'][0][field]=value
                self.assertEqual(self.check(site,note)['outcome'],'unexpected-or-inconsistent-app-row')

    def test_additional_wrong_owner_is_not_hidden_by_a_correct_row(self):
        site,note=self.fixture();extra=deepcopy(site.saved['rows'][0])
        extra.update(target_law='다른법',target_id='other-id',neighbor_law='다른법',neighbor_id='other-id')
        site.saved['rows'].append(extra)
        self.assertIn('unexpected-target-owner-or-kind',codes(self.check(site,note)))

    def test_a_correct_catalog_id_cannot_hide_the_wrong_body_file(self):
        site,note=self.fixture();site.docs['대상법']['meta']['name']='다른법'
        self.assertIn('click-document-identity-mismatch',codes(self.check(site,note)))
        site,note=self.fixture();site.docs['대상법']['articles']=[]
        self.assertIn('click-article-unavailable',codes(self.check(site,note)))

    def test_broader_and_additional_scopes_are_rejected(self):
        for changed in [[scope(['10','1','2',''])],
                        [scope(['10','1','2','나']),scope(['10','1','2','다'])]]:
            with self.subTest(scopes=changed):
                site,note=self.fixture();site.saved['rows'][0]['raw_scope']['scopes']=changed
                self.assertIn('raw-scope-exceeds-manual',codes(self.check(site,note)))

    def test_raw_scope_is_required_and_bad_paths_are_reported_instead_of_crashing(self):
        for changed in (None,{'scopes':[]},{'scopes':[[['10'],['10'],None]]}):
            with self.subTest(value=changed):
                site,note=self.fixture();site.saved['rows'][0]['raw_scope']=changed
                self.assertEqual(self.check(site,note)['outcome'],'unexpected-or-inconsistent-app-row')

    def test_duplicate_destination_is_found_even_with_a_different_evidence_id(self):
        site,note=self.fixture();duplicate=deepcopy(site.saved['rows'][0]);duplicate['evidence_id']='new-id'
        site.saved['rows'].append(duplicate)
        self.assertIn('duplicate-source-target-occurrence',codes(self.check(site,note)))

    def test_repeated_source_occurrences_are_not_duplicates(self):
        quote='「대상법」 제10조제1항제2호나목'
        site=MockSite(quote+' 또는 '+quote);first=row(site,quote);second=deepcopy(first)
        second['source_start']=site.body.rindex(quote);second['source_end']=len(site.body)
        site.saved['rows']=[first,second]
        note=annotation(quote+' 또는 '+quote)
        self.assertEqual(self.check(site,note)['outcome'],'matched')

    def test_article_range_expansion_including_branch_articles_is_not_duplicate(self):
        quote='「대상법」 제20조부터 제22조까지';site=MockSite(quote)
        saved=[scope(['20','','',''],['22','','',''],0)]
        site.saved['rows']=[row(site,quote,ref,jo,saved) for ref,jo in
                           [('제20조','20'),('제21조','21'),('제21조의2','21의2'),('제22조','22')]]
        note=annotation(quote,[dict(law='대상법',ref='제20조~제22조',kind='article')])
        self.assertEqual(self.check(site,note)['outcome'],'matched')
        site.saved['rows']=[r for r in site.saved['rows'] if r['neighbor_jo']!='21']
        result=self.check(site,note)
        self.assertEqual(result['outcome'],'missing-or-truncated-target')
        self.assertTrue(result['missing'][0]['missing_destination_records'])
        self.assertFalse(result['missing'][0]['missing_scopes'])

    def test_current_source_in_a_range_uses_open_body_but_other_clicks_are_required(self):
        quote='이 조부터 제3조까지';site=MockSite(quote)
        site.docs['출발법']['articles'] += [{'jo':jo,'text':'제'+jo+'조(표본)','effective':'20261004'} for jo in ('2','3')]
        full=scope(['1','','',''],['3','','',''],0)
        site.saved['rows']=[row(site,quote,'제'+jo+'조',jo,[full],law='출발법') for jo in ('2','3')]
        site.saved['same_article_count']=1
        note=annotation(quote,[dict(law='출발법',ref='제1조~제3조',kind='article')])
        self.assertEqual(self.check(site,note)['outcome'],'matched')
        second=site.saved['rows'].pop(0)
        self.assertEqual(self.check(site,note)['outcome'],'missing-or-truncated-target')
        site.saved['rows'].insert(0,second)
        for count in (0,None,True):
            with self.subTest(same_article_count=count):
                site.saved['same_article_count']=count
                self.assertEqual(self.check(site,note)['outcome'],'missing-or-truncated-target')
        site.saved['same_article_count']=1
        for saved in site.saved['rows']:
            saved['raw_scope']['scopes']=[scope(['2','','',''],['3','','',''],0)]
        self.assertEqual(self.check(site,note)['outcome'],'missing-or-truncated-target')

    def test_one_compound_quote_needs_each_destination_record(self):
        quote='「대상법」 제10조제1항제2호나목 및 다목';site=MockSite(quote)
        saved=[scope(['10','1','2','나']),scope(['10','1','2','다'])]
        site.saved['rows']=[row(site,quote,ref,scopes=saved) for ref in
                           ['제10조제1항제2호나목','제10조제1항제2호다목']]
        note=annotation(quote,[dict(law='대상법',ref='제10조제1항제2호나목 및 다목',kind='article')])
        self.assertEqual(self.check(site,note)['outcome'],'matched')
        site.saved['rows'].pop()
        self.assertEqual(self.check(site,note)['outcome'],'missing-or-truncated-target')

    def test_item_range_one_row_can_cover_manually_enumerated_expected_items(self):
        quote='「대상법」 제10조제1항제1호부터 제3호까지';site=MockSite(quote)
        site.saved['rows']=[row(site,quote,'제10조제1항제1호',scopes=[scope(['10','1','1',''],['10','1','3',''],2)])]
        note=annotation(quote,[dict(law='대상법',ref=ref,kind='article') for ref in
                              ['제10조제1항제1호','제10조제1항제2호','제10조제1항제3호']])
        self.assertEqual(self.check(site,note)['outcome'],'matched')

    def test_external_article_and_law_have_no_fabricated_local_click(self):
        for kind,quote,ref,saved in [('article','「미수집법」 제10조','제10조',[scope(['10','','',''])]),
                                   ('law','「미수집법」','법령·정의 참조',[])]:
            with self.subTest(kind=kind):
                site=MockSite(quote);outside=row(site,quote,ref,law='미수집법',kind=kind,scopes=saved)
                for field in ('direction','raw','neighbor_law','neighbor_jo','neighbor_ref','neighbor_kind','kind','target_ref_recorded'):
                    outside.pop(field,None)
                outside['target_status']='not-collected';site.saved['external']=[outside]
                note=annotation(quote,[dict(law='미수집법',kind=kind,ref=ref if kind=='article' else None)])
                self.assertEqual(self.check(site,note)['outcome'],'matched')
                outside['neighbor_id']='target-id'
                self.assertIn('unexpected-external-click-id',codes(self.check(site,note)))

    def test_nested_quote_uses_its_own_manual_owner_not_the_outer_relative_anchor(self):
        quote='같은 법 또는 「다른법」';site=MockSite(quote)
        def law_row(raw,name):
            result=row(site,raw,'법령·정의 참조','법령·정의 참조',[],law=name,kind='law')
            result['neighbor_ref']='법령·정의 참조'
            return result
        site.saved['rows']=[law_row('같은 법','대상법'),law_row('「다른법」','다른법')]
        outer=annotation(quote,[dict(law='대상법',ref=None,kind='law')])
        inner=annotation('「다른법」',[dict(law='다른법',ref=None,kind='law')])
        self.assertEqual(self.check(site,outer,annotations=[outer,inner])['outcome'],'matched')
        site.saved['rows'].append(law_row('「다른법」','대상법'))
        self.assertIn('unexpected-target-owner-or-kind',codes(self.check(site,outer,annotations=[outer,inner])))

    def test_source_quote_or_offset_mutation_cannot_pass(self):
        for field,value in [('raw','다른 원문'),('cite_raw','다른 원문'),('source_end',999)]:
            with self.subTest(field=field):
                site,note=self.fixture();site.saved['rows'][0][field]=value
                wanted='source-span-invalid' if field=='source_end' else 'source-quote-mismatch'
                self.assertIn(wanted,codes(self.check(site,note)))

    def test_partial_regression_context_is_reported_not_claimed_fully_verified(self):
        quote='「다른법」 제99조에 따라 「대상법」 제10조제1항제2호나목을 적용한다.'
        site=MockSite(quote)
        site.saved['rows']=[row(site,'「다른법」 제99조','제99조','99',[scope(['99','','',''])],law='다른법'),
                            row(site,'「대상법」 제10조제1항제2호나목')]
        note=annotation(quote);note['kind']='scope-loss'
        result=self.check(site,note,fixture=True)
        self.assertEqual(result['outcome'],'matched-with-unassessed-context')
        self.assertEqual(len(result['unassessed_context_rows']),1)
        self.assertFalse(result['row_errors'])
        # Wider context is not a blanket exception: its actual click still must
        # agree with the source quote and saved scope.
        site.saved['rows'][0]['neighbor_jo']='20'
        self.assertEqual(self.check(site,note,fixture=True)['outcome'],'unexpected-or-inconsistent-app-row')
        site.saved['rows'][0]['neighbor_jo']='99'
        site.saved['rows'][1].update(target_law='다른법',target_id='other-id',neighbor_law='다른법',neighbor_id='other-id')
        self.assertIn('unexpected-target-owner-or-kind',codes(self.check(site,note,fixture=True)))

    def test_additional_missing_reversed_and_out_of_body_spans_fail_full_article_check(self):
        for start,end in [(None,20),(20,10),(100000,100020),(-1,20)]:
            with self.subTest(start=start,end=end):
                site,note=self.fixture();extra=deepcopy(site.saved['rows'][0])
                extra.update(source_start=start,source_end=end,evidence_id='bad-span-extra')
                site.saved['rows'].append(extra)
                result=structural_check(site,'출발법','1')
                self.assertEqual(result['outcome'],'structural-mismatch')
                self.assertIn('source-span-invalid',codes(result))
                self.assertEqual(len(result['row_errors']),1)

    def test_unannotated_source_quote_still_checks_source_identity_and_click_fields(self):
        site,note=self.fixture();extra_quote='「대상법」 제99조'
        site.body+=' '+extra_quote;site.docs['출발법']['articles'][0]['text']=site.body
        extra=row(site,extra_quote,'제99조','99',[scope(['99','','',''])])
        site.saved['rows'].append(extra)
        self.assertEqual(self.check(site,note)['outcome'],'matched')
        self.assertEqual(structural_check(site,'출발법','1')['outcome'],'structure-matched')
        for field,value in [('source_id','other-id'),('neighbor_id','other-id'),('raw','잘못된 원문')]:
            with self.subTest(field=field):
                original=extra[field];extra[field]=value
                self.assertEqual(structural_check(site,'출발법','1')['outcome'],'structural-mismatch')
                extra[field]=original

    def test_law_and_standard_rows_do_not_need_a_numbered_body_target(self):
        for name,kind,ref in [('대상법','law','법령·정의 참조'),('기업회계기준','standard','기준 참조')]:
            with self.subTest(kind=kind):
                site=MockSite(name);saved=row(site,name,ref,ref,[],law=name,kind=kind)
                saved['neighbor_ref']=ref;site.saved['rows']=[saved]
                note=annotation(name,[dict(law=name,kind=kind,ref=None)])
                self.assertEqual(self.check(site,note)['outcome'],'matched')
                self.assertEqual(structural_check(site,'출발법','1')['outcome'],'structure-matched')

    def annex_fixture(self,ref='별지 제7호의2서식',law='대상법'):
        site=MockSite(ref)
        if law in site.docs:site.docs[law]['annexes']=[{'ref':ref,'title':'공식 서식'}]
        saved=row(site,ref,ref,ref,[],law=law,kind='annex');saved['neighbor_ref']=ref
        site.saved['rows']=[saved]
        return site,annotation(ref,[dict(law=law,ref=ref,kind='annex')])

    def test_annex_missing_wrong_branch_or_form_variant_cannot_pass_empty_scopes(self):
        for ref,wrong in [('별지 제7호의2서식','별지 제7호서식'),
                          ('별지 제16호서식(2)','별지 제16호서식(1)'),('별표 2','별표 1')]:
            with self.subTest(ref=ref):
                site,note=self.annex_fixture(ref)
                self.assertEqual(self.check(site,note)['outcome'],'matched')
                original=deepcopy(site.saved['rows'][0]);site.saved['rows']=[]
                self.assertEqual(self.check(site,note)['outcome'],'missing-or-truncated-target')
                original.update(target_ref=wrong,target_ref_recorded=wrong,neighbor_jo=wrong,neighbor_ref=wrong)
                site.docs['대상법']['annexes'].append({'ref':wrong})
                site.saved['rows']=[original]
                self.assertIn('annex-reference-outside-manual',codes(self.check(site,note)))

    def test_annex_branch_metadata_order_is_equivalent_but_clicks_still_must_agree(self):
        for source,catalog in [('별지 제7호의2서식','별지 제7의2호서식'),
                               ('별지 제33호의2서식','별지 제33의2호서식'),
                               ('별지 제54호의2서식','별지 제54의2호서식')]:
            with self.subTest(source=source):
                self.assertEqual(annex_key(source),annex_key(catalog))
                site,note=self.annex_fixture(source)
                site.docs['대상법']['annexes']=[{'ref':catalog}]
                saved=site.saved['rows'][0]
                saved.update(target_ref=catalog,target_ref_recorded=catalog,neighbor_jo=catalog,neighbor_ref=catalog)
                self.assertEqual(self.check(site,note)['outcome'],'matched')
                self.assertEqual(structural_check(site,'출발법','1')['outcome'],'structure-matched')
                saved.update(target_ref=source,target_ref_recorded=source,neighbor_jo=catalog,neighbor_ref=source)
                self.assertEqual(self.check(site,note)['outcome'],'matched')
                self.assertEqual(structural_check(site,'출발법','1')['outcome'],'structure-matched')
                saved['neighbor_jo']=source
                self.assertIn('click-annex-catalog-reference-mismatch',codes(self.check(site,note)))
                saved.update(target_ref=catalog,target_ref_recorded=catalog,neighbor_jo=catalog,neighbor_ref=catalog)
                saved['neighbor_jo']='별지 제7호서식'
                self.assertIn('annex-neighbor-reference-mismatch',codes(self.check(site,note)))
                saved['neighbor_jo']=catalog
                site.docs['대상법']['annexes']=[{'ref':'별지 제7의3호서식'}]
                self.assertIn('click-annex-unavailable',codes(self.check(site,note)))
        self.assertNotEqual(annex_key('별지 제7의2호서식'),annex_key('별지 제7호서식'))
        self.assertIsNone(annex_key('별지 제7호의2호서식'))
        self.assertIsNone(annex_key('별지 제7의2호서식부터 별지 제7의3호서식'))

    def test_annex_collected_destination_requires_exact_catalog_entry(self):
        site,note=self.annex_fixture();site.docs['대상법']['annexes']=[]
        self.assertIn('click-annex-unavailable',codes(self.check(site,note)))
        self.assertIn('click-annex-unavailable',codes(structural_check(site,'출발법','1')))

    def combined_form_fixture(self,variant='1'):
        owner='부가가치세법 시행규칙';ref='별지 제16호서식('+variant+')'
        container='별지 제16호서식';url='https://www.law.go.kr/LSW/flDownload.do?flSeq=162619767'
        site=MockSite(ref);site.entries[owner]={'id':'vat-id','name':owner}
        site.docs[owner]={'meta':deepcopy(site.entries[owner]),'articles':[],
                          'annexes':[dict(ref=container,effective='20260401',urls=[url])]}
        saved=row(site,ref,ref,container,[],law=owner,kind='annex')
        saved.update(neighbor_ref=ref,target_effective='20260401',annex_urls=[url],
            annex_container_ref=container,annex_container_page=1 if variant=='1' else 3,
            annex_container_sha256='bd850a4cd5318d5eb7e185433868ecfa8a52d1ec512f53d52090c7c9ecf63d72')
        site.saved['rows']=[saved]
        return site,annotation(ref,[dict(law=owner,ref=ref,kind='annex')])

    def test_verified_combined_pdf_keeps_logical_subform_and_physical_click_distinct(self):
        for variant in ('1','2'):
            site,note=self.combined_form_fixture(variant)
            self.assertEqual(self.check(site,note)['outcome'],'matched')
            self.assertEqual(structural_check(site,'출발법','1')['outcome'],'structure-matched')
        site,note=self.combined_form_fixture()
        saved=site.saved['rows'][0]
        for field in ('annex_container_ref','annex_container_page','annex_container_sha256'):
            saved.pop(field)
        self.assertIn('click-annex-unavailable',codes(self.check(site,note)))
        self.assertIn('annex-neighbor-reference-mismatch',codes(self.check(site,note)))

    def test_container_exception_rejects_changed_identity_proof_or_catalog(self):
        changes=[('target_law','다른법'),('target_effective','20260402'),
                 ('annex_container_ref','별지 제17호서식'),('annex_container_page',3),
                 ('annex_container_page',True),('annex_container_sha256','0'*64),
                 ('annex_urls',[]),('annex_urls',['https://www.law.go.kr/LSW/flDownload.do?flSeq=999']),
                 ('target_ref','별지 제17호서식(1)'),('neighbor_jo','별지 제17호서식')]
        for field,value in changes:
            with self.subTest(field=field,value=value):
                site,note=self.combined_form_fixture();site.saved['rows'][0][field]=value
                self.assertIn('unverified-annex-container',codes(self.check(site,note)))
        for field,value in [('effective','20260402'),('ref','별지 제17호서식'),('urls',[])]:
            with self.subTest(catalog_field=field):
                site,note=self.combined_form_fixture()
                site.docs['부가가치세법 시행규칙']['annexes'][0][field]=value
                self.assertIn('unverified-annex-container',codes(self.check(site,note)))

    def test_uncollected_annex_is_checked_without_inventing_a_catalog_entry(self):
        site,note=self.annex_fixture(law='미수집법');saved=site.saved['rows'].pop()
        for field in ('direction','neighbor_law','neighbor_id','neighbor_jo','neighbor_ref','neighbor_kind','kind','target_ref_recorded'):
            saved.pop(field,None)
        site.saved['external']=[saved]
        self.assertEqual(self.check(site,note)['outcome'],'matched')
        saved['target_ref']='별지 제7호서식'
        self.assertIn('annex-reference-outside-manual',codes(self.check(site,note)))

    def test_table_item_is_not_decoded_as_an_ordinary_ho(self):
        with self.assertRaises(ValueError):authored_scopes('제10조제1항 표 제2호')
        quote='대상법 제10조제1항의 표 제2호';site=MockSite(quote)
        base=row(site,'제10조제1항','제10조제1항','10',[scope(['10','1','',''])])
        base['context']=quote;site.saved['rows']=[base]
        note=annotation(quote,[dict(law='대상법',ref='제10조제1항 표 제2호',kind='article')])
        result=self.check(site,note)
        self.assertEqual(result['outcome'],'matched-table-base-only')
        self.assertTrue(result['table_locators'][0]['context_preserved'])
        base['context']='제10조제1항만 남은 문맥'
        self.assertEqual(self.check(site,note)['outcome'],'missing-or-truncated-target')
        base['context']=quote
        base.update(target_ref='제10조제1항제2호',target_ref_recorded='제10조제1항제2호',
                    raw_scope={'scopes':[scope(['10','1','2',''])]})
        self.assertIn('raw-scope-exceeds-manual',codes(self.check(site,note)))

    def test_matching_current_body_does_not_verify_required_historical_target(self):
        site,note=self.fixture()
        note['target_edition_constraint']={'relation':'before_amendment','law_number':'123','law':'대상법'}
        result=self.check(site,note)
        self.assertEqual(result['outcome'],'target-edition-unverified')
        self.assertEqual(result['target_edition_check']['constraint'],note['target_edition_constraint'])
        site.saved['rows'][0]['neighbor_jo']='99'
        self.assertEqual(self.check(site,note)['outcome'],'unexpected-or-inconsistent-app-row')

    def test_delegation_negative_control_uses_only_its_frozen_occurrence(self):
        quote='대통령령으로 정하는 사항';site=MockSite(quote+' 및 대상법 제10조')
        site.saved['rows']=[row(site,'대상법 제10조','제10조','10',[scope(['10','','',''])])]
        context=dict(quote=quote,start=site.body.index(quote),end=site.body.index(quote)+len(quote))
        self.assertEqual(negative_control(site,'출발법','1',context)['outcome'],'negative-control-passed')
        site.saved['rows'].append(row(site,quote,'제10조','10',[scope(['10','','',''])]))
        self.assertEqual(negative_control(site,'출발법','1',context)['outcome'],'unexpected-concrete-target')
        context['start']=0
        self.assertEqual(negative_control(site,'출발법','1',context)['outcome'],'source-span-mismatch')

    def test_cli_accepts_a_frozen_golden_without_regression_fixtures(self):
        site,note=self.fixture();site.manifest={'version':'mock'}
        golden={'editions':[dict(law='출발법',effective='20261004')],
                'articles':[dict(law='출발법',jo='1',edition='출발법|20261004',annotations=[note])]}
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'golden.json';source.write_text(json.dumps(golden),encoding='utf-8')
            args=['verify','--site',folder,'--golden',str(source),'--report',str(ROOT/'output/mock-verifier-report.json')]
            with patch('scripts.verify_tax_citation_samples.Site',return_value=site),patch('sys.argv',args), \
                    patch('pathlib.Path.write_text'),patch('pathlib.Path.mkdir'),patch('builtins.print'):
                self.assertEqual(main(),0)

    def test_site_reads_inline_details_without_a_shard_reference(self):
        site=Site.__new__(Site);site.details={}
        site.docs={'출발법':{'articles':[{'jo':'1','text':'본문'}],'details':{'1':{'rows':[]}}}}
        self.assertEqual(site.detail('출발법','1'),{'rows':[]})


if __name__=='__main__':unittest.main()
