"""Offline contracts for annex identities and one source-verified PDF container."""
from copy import deepcopy
import unittest

from core.annex_metadata import annex_key, annex_index, annotate_annex

OWNER = '부가가치세법 시행규칙'
PDF = 'https://www.law.go.kr/LSW/flDownload.do?flSeq=162619767'
HWP = 'https://www.law.go.kr/LSW/flDownload.do?flSeq=162619765'
DIGEST = 'bd850a4cd5318d5eb7e185433868ecfa8a52d1ec512f53d52090c7c9ecf63d72'


def container():
    return dict(ref='별지 제16호서식', title='신용카드매출전표등 수령명세서(갑, 을)',
                effective='20260401', urls=[HWP, PDF])


def index_for(*annexes, owner=OWNER):
    return annex_index([dict(name=owner, annexes=list(annexes))])


def row_for(ref, *, owner=OWNER, reverse=False):
    return dict(direction='reverse' if reverse else 'forward',
                source_law=owner, source_jo='62', source_effective='20260401', target_effective='20260401', target_law='다른 인용 대상 법' if reverse else owner,
                target_ref='제1조' if reverse else ref, target_kind='article' if reverse else 'annex',
                neighbor_law=owner, neighbor_kind='annex', neighbor_jo=ref, neighbor_ref=ref,
                cite_raw=ref, source_start=10, source_end=10+len(ref))


class AnnexCatalogTests(unittest.TestCase):
    def test_branch_printing_variants_share_identity(self):
        variants=['별지 제13호의2서식','별지 제13의2호서식','별지 제013호의02서식','별지 제13호의2 서식']
        self.assertEqual({annex_key(ref) for ref in variants},{('별지','13','2','')})
        self.assertEqual(annex_key('별표 제5호'),annex_key('별표 5'))

    def test_numbered_subforms_keep_distinct_identity(self):
        refs=['별지 제16호서식','별지 제16호서식(1)','별지 제16호서식(2)','별지 제16호의1서식','별표 16']
        self.assertEqual(len({annex_key(ref) for ref in refs}),len(refs))
        self.assertEqual(annex_key(refs[1]),('별지','16','','1'))
        self.assertEqual(annex_key('별지 제1의2호의3서식')[0],'literal')

    def test_unique_canonical_match_changes_click_ref_only(self):
        annex=dict(ref='별지 제13의2호서식',urls=[PDF],analysis={'status':'verified'})
        row=row_for('별지 제13호의2서식'); original=deepcopy(row); index=index_for(annex); saved=deepcopy(index)
        result=annotate_annex(row,index)
        self.assertEqual(result['neighbor_jo'],annex['ref'])
        for key in ['target_ref','neighbor_ref','cite_raw','source_start','source_end']:
            self.assertEqual(result[key],original[key])
        self.assertTrue(result['annex_analyzed'])
        self.assertEqual(row,original); self.assertEqual(index,saved)

    def test_ambiguous_canonical_matches_do_not_choose_a_file(self):
        index=index_for(dict(ref='별지 제13호의2서식',urls=['first']),
                        dict(ref='별지 제13의2호서식',urls=['second']))
        row=row_for('별지 제013의02호서식'); result=annotate_annex(row,index)
        self.assertEqual(result['neighbor_jo'],row['neighbor_jo'])
        self.assertEqual(result['annex_urls'],[])
        self.assertFalse(result['annex_analyzed'])

    def test_verified_single_pdf_contains_two_printed_subforms(self):
        # Official PDF flSeq162619767 was visually checked as one 3-page file:
        # page1=form16(1)/갑, page2=back/instructions, page3=form16(2)/을.
        for number,page in [('1',1),('2',3)]:
            with self.subTest(number=number):
                row=row_for('별지 제16호서식('+number+')'); result=annotate_annex(row,index_for(container()))
                self.assertEqual(result['annex_container_ref'],'별지 제16호서식')
                self.assertEqual(result['annex_container_page'],page)
                self.assertEqual(result['annex_container_sha256'],DIGEST)
                self.assertEqual(result['neighbor_jo'],'별지 제16호서식')
                self.assertEqual(result['target_ref'],row['target_ref'])
                self.assertEqual(result['neighbor_ref'],row['neighbor_ref'])
                self.assertEqual(result['cite_raw'],row['cite_raw'])
                self.assertEqual(result['annex_urls'],[HWP,PDF])
                self.assertFalse(result['annex_analyzed'])

    def test_every_container_guard_is_required(self):
        good=container()
        changes=[('effective','20260402'),('title','신용카드매출전표등 수령명세서'),
                 ('urls',[HWP]),('urls',[PDF+'&other=1']),('urls',[PDF.replace('https:','http:')]),
                 ('ref','별지 제17호서식')]
        for key,value in changes:
            with self.subTest(key=key,value=value):
                bad={**good,key:value}; result=annotate_annex(row_for('별지 제16호서식(1)'),index_for(bad))
                self.assertNotIn('annex_container_ref',result)
                self.assertEqual(result['neighbor_jo'],'별지 제16호서식(1)')
                self.assertEqual(result['annex_urls'],[])
        result=annotate_annex(row_for('별지 제16호서식(1)',owner='다른 시행규칙'),index_for(good,owner='다른 시행규칙'))
        self.assertNotIn('annex_container_ref',result)
        self.assertEqual(result['annex_urls'],[])

    def test_container_uses_effective_date_of_the_annex_owner_direction(self):
        for reverse in [False,True]:
            selected='source_effective' if reverse else 'target_effective'
            other='target_effective' if reverse else 'source_effective'
            for day in ['', '20260402']:
                row=row_for('별지 제16호서식(1)',reverse=reverse)
                if day:row[selected]=day
                else:row.pop(selected)
                with self.subTest(reverse=reverse,day=day):
                    result=annotate_annex(row,index_for(container()))
                    self.assertNotIn('annex_container_ref',result)
                    self.assertEqual(result['annex_urls'],[])
            row=row_for('별지 제16호서식(1)',reverse=reverse);row[other]='20250101'
            self.assertEqual(annotate_annex(row,index_for(container()))['annex_container_page'],1)

    def test_no_inferred_arbitrary_subform_or_branch_container(self):
        for ref in ['별지 제16호서식(3)','별지 제16호서식(01)','별지 제16호의1서식','별지 제17호서식(1)','별표 16(1)']:
            with self.subTest(ref=ref):
                result=annotate_annex(row_for(ref),index_for(container()))
                self.assertNotIn('annex_container_ref',result)
                self.assertEqual(result['neighbor_jo'],ref)
                self.assertEqual(result['annex_urls'],[])

    def test_explicit_subform_catalog_entry_precedes_container_fallback(self):
        explicit=dict(ref='별지 제16호서식(2)',urls=['explicit'],body_analysis={'status':'verified'})
        result=annotate_annex(row_for(explicit['ref']),index_for(container(),explicit))
        self.assertNotIn('annex_container_ref',result)
        self.assertEqual(result['neighbor_jo'],explicit['ref'])
        self.assertEqual(result['annex_urls'],['explicit'])
        self.assertTrue(result['annex_analyzed'])

    def test_reverse_annex_neighbor_owns_the_container(self):
        row=row_for('별지 제16호서식(2)',reverse=True); result=annotate_annex(row,index_for(container()))
        self.assertEqual(result['annex_container_page'],3)
        self.assertEqual(result['neighbor_jo'],'별지 제16호서식')
        self.assertEqual(result['target_law'],'다른 인용 대상 법')
        self.assertEqual(result['target_ref'],'제1조')
        self.assertEqual(result['neighbor_ref'],'별지 제16호서식(2)')

    def test_reverse_article_neighbor_is_not_annotated_as_target_annex(self):
        row=dict(direction='reverse',target_kind='annex',target_law=OWNER,target_ref='별지 제16호서식(2)',
                 neighbor_kind='article',neighbor_law='다른법',neighbor_jo='62')
        self.assertEqual(annotate_annex(row,index_for(container())),row)

    def test_forward_without_neighbor_fields_uses_target(self):
        row=dict(direction='forward',target_kind='annex',target_law=OWNER,target_ref='별지 제16호서식(1)',target_effective='20260401')
        result=annotate_annex(row,index_for(container()))
        self.assertEqual(result['annex_container_page'],1)
        self.assertNotIn('neighbor_jo',result)
        self.assertEqual(result['target_ref'],row['target_ref'])

    def test_annotation_is_idempotent_and_deduplicates_links(self):
        row=row_for('별지 제16호서식(1)');row['annex_urls']=[PDF]
        original=deepcopy(row); index=index_for(container()); saved=deepcopy(index)
        once=annotate_annex(row,index); twice=annotate_annex(once,index)
        self.assertEqual(once,twice)
        self.assertEqual(once['annex_urls'],[PDF,HWP])
        self.assertEqual(row,original);self.assertEqual(index,saved)


if __name__ == '__main__':
    unittest.main()
