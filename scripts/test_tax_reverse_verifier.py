"""Reverse audits detect missing source occurrences and wrong body targets."""
from copy import deepcopy
import hashlib
import unittest

from scripts.verify_tax_reverse_sources import audit


class ReverseSite:
    def __init__(self):
        self.entries={'출처법':dict(id='source'),'대상법':dict(id='target')}
        self.text='제1조(검증)\n「대상법」 제10조제2항\n다른 법 제10조'
        start=self.text.index('「대상법」');end=self.text.index('\n',start)
        self.row=dict(direction='reverse',source_law='출처법',source_jo='1',source_id='source',
            source_start=start,source_end=end,cite_raw=self.text[start:end],raw=self.text[start:end],
            target_law='대상법',target_id='target',target_ref='제10조',target_ref_recorded='제10조제2항',
            neighbor_law='출처법',neighbor_jo='1',neighbor_id='source',
            raw_scope=dict(scopes=[[['10','2','',''],['10','2','',''],None]]))
        self.rows=[self.row]
        common=dict(source_law='출처법',source_jo='1',source_effective='20261004',source_article_sha256=hashlib.sha256(self.text.encode()).hexdigest())
        positive=common|dict(candidate_index=0,paragraph_start=start,paragraph_end=end,text=self.text[start:end],expected=[dict(start=start,end=end,quote=self.text[start:end],target_refs=['제10조제2항'])])
        negative=common|dict(candidate_index=1,paragraph_start=end+1,paragraph_end=len(self.text),text=self.text[end+1:],reason='other law')
        self.golden=dict(protocol='synthetic source-first fixture',targets=[dict(law='대상법',jo='10',annotations=[positive],excluded=[negative])])
    def article(self,law,jo):return dict(text=self.text,effective='20261004')
    def detail(self,law,jo):return dict(rows=self.rows)


class ReverseVerifierTests(unittest.TestCase):
    def test_valid_reverse_and_negative_control(self):
        site=ReverseSite();prior=deepcopy(site.__dict__)
        self.assertEqual(audit(site,site.golden)['failure_count'],0)
        self.assertEqual(site.__dict__,prior)

    def test_missing_relative_occurrence_is_not_hidden_by_other_article_row(self):
        site=ReverseSite();site.rows=[]
        report=audit(site,site.golden)
        self.assertEqual(report['outcomes'],{'missing-reverse-occurrence':1})

    def test_correct_scope_does_not_hide_wrong_source_click_id_or_article(self):
        for key,value in [('neighbor_id','target'),('neighbor_jo','99'),('source_id','target')]:
            site=ReverseSite();site.row[key]=value
            self.assertIn('wrong-source-click-destination',audit(site,site.golden)['results'][0]['issues'])

    def test_wrong_owner_negative_and_duplicate_rows_fail(self):
        site=ReverseSite();other=deepcopy(site.row)
        negative=site.golden['targets'][0]['excluded'][0]
        other.update(source_start=negative['paragraph_start'],source_end=negative['paragraph_end'])
        site.rows.append(other)
        self.assertEqual(audit(site,site.golden)['negative_outcomes'],{'wrong-owner-reverse-row':1})
        site.rows=[site.row,deepcopy(site.row)]
        self.assertEqual(len(audit(site,site.golden)['duplicate_rows']),1)

    def test_representative_reference_must_belong_to_full_scope(self):
        site=ReverseSite();site.row['target_ref_recorded']='제99조'
        self.assertTrue(audit(site,site.golden)['results'][0]['missing_recorded_refs'])


if __name__=='__main__':unittest.main()
