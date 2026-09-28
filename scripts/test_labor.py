"""Labor scope, source fidelity and independent state/data boundaries."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from core.fsc_collection import CollectionError
from core.labor_profile import FIXED,EQUALITY,PROFILE
from core.mofe_profiles import selected,PROFILES
from core.mofe_collection import prepare_source,discover_inventory
from core.mofe_universe import build_graph,validate_bundle,mark_sector
from core.labor_universe import load_bundle,BUNDLE
from core.galaxy_focus import analyze_focus

def fixture():
    def doc(name,uid,articles):
        return dict(name=name,uid=uid,provider='eflaw',category='labor',kind='법률',effective='20260101',
                    managing_authority='고용노동부',source_url='https://www.law.go.kr/법령/'+name,annexes=[],
                    articles=[dict(jo=jo,title='기간제근로자',text=text,blocks=[]) for jo,text in articles])
    laws=[doc(FIXED,'eflaw:1',[('4','제4조(기간제근로자의 사용) 기간제근로자를 사용한다.'),
                                ('9','제9조(시정신청) 「노동위원회법」 제2조에 따른다.')]),
          doc(FIXED+' 시행령','eflaw:2',[('3','제3조(예외) 법 제4조제1항에 따른다.')])]
    src=dict(domain='labor',built_at='20260928',laws=laws,administrative_rules=[],inventory={'scope':'fixture'})
    source=prepare_source(src)
    return dict(source=source,graph=build_graph(source))

class LaborTests(unittest.TestCase):
    def test_scope_requires_both_declared_name_and_authority(self):
        self.assertTrue(selected('labor',FIXED,'고용노동부','eflaw'))
        self.assertTrue(selected('labor','노동위원회규칙','중앙노동위원회','admrul'))
        for name,authority in [('근로기준법','재정경제부'),('산업안전보건법','고용노동부'),('고용노동부 공무원 행동강령','고용노동부')]:
            self.assertFalse(selected('labor',name,authority,'eflaw'))
        self.assertNotIn('labor',PROFILES)  # Legacy MOFE bulk collection scope stays unchanged.
        self.assertTrue(selected('labor',EQUALITY,'고용노동부,성평등가족부','eflaw'))
        self.assertFalse(selected('labor','근로기준법','성평등가족부','eflaw'))

    def test_missing_required_laws_fail(self):
        def empty(endpoint,params):
            tag='LawSearch' if params['target']=='eflaw' else 'AdmRulSearch'
            return f'<{tag}><totalCnt>0</totalCnt><page>1</page></{tag}>'.encode()
        with self.assertRaisesRegex(CollectionError,'required-documents-missing'):
            discover_inventory(empty,'labor','20260928')

    def test_reverse_citation_and_outside_topic_preserved(self):
        b=fixture();validate_bundle(b,'labor')
        rows=analyze_focus(FIXED,'4',b['graph'])
        self.assertTrue(any(r['direction']=='reverse' and r['source_law']==FIXED+' 시행령' for r in rows['rows']))
        marked=mark_sector(rows,b['graph'],'collective')
        self.assertEqual(len(rows['rows']),len(marked['rows']))
        self.assertTrue(all(r['out_of_sector'] for r in marked['rows']))

    def test_external_body_not_claimed(self):
        b=fixture();self.assertNotIn('노동위원회법',b['graph']['laws'])
        self.assertTrue(any(e['target_law']=='노동위원회법' and e['target_status']=='not-collected' for e in b['graph']['external_references']))

    def test_mixed_domain_and_modified_evidence_rejected(self):
        b=fixture()
        with self.assertRaises(ValueError):validate_bundle(b,'tax')
        b['graph']['edges'][0]['cite_raw']='변조'
        with self.assertRaises(ValueError):validate_bundle(b,'labor')

    def test_missing_labor_file_no_tax_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):load_bundle(Path(tmp)/'absent.json')

    def test_preparation_does_not_mutate_and_topics_are_multiple(self):
        b=fixture();source=b['source'];before=deepcopy(source)
        ready=prepare_source(source);self.assertEqual(source,before)
        article=next(a for a in ready['laws'][0]['articles'] if a['jo']=='9')
        self.assertTrue({'fixed','equality','remedy'}.issubset(article['sectors']))

@unittest.skipUnless(BUNDLE.is_file(),'Requires locally collected labor snapshot')
class CollectedLaborTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle=load_bundle()

    def test_period_exception_has_decree_evidence(self):
        rows=analyze_focus(FIXED,'4',self.bundle['graph'])['rows']
        self.assertTrue(any(r['direction']=='reverse' and r['source_law']==FIXED+' 시행령'
                            and r['source_ref']=='제3조제1항' and r['cite_raw']=='법 제4조제1항제5호'
                            and r['status']!='review' for r in rows))

    def test_rule_alias_and_range_resolve_to_the_right_law(self):
        rows=analyze_focus(FIXED,'9',self.bundle['graph'])['rows']
        self.assertTrue(any(r['source_law']=='노동위원회규칙' and r['source_ref']=='제100조'
                            and r['cite_raw']=='기간제법 제9조제1항' and r['status']!='review' for r in rows))
        self.assertTrue(any(r['source_law']=='노동위원회규칙' and r['source_ref']=='제17조제1호'
                            and r['status']=='range' for r in rows))

    def test_all_documents_match_declared_scope_and_cases_have_evidence(self):
        b=self.bundle
        docs=b['source']['laws']+b['source']['administrative_rules']
        self.assertTrue(all(selected('labor',d['name'],d['managing_authority'],d['provider']) for d in docs))
        self.assertTrue(all(d['articles'] for d in docs))
        self.assertTrue(all(c['available'] and c['evidence_ids'] for c in b['assessment']['cases']))
        self.assertEqual(b['graph']['coverage']['annex_body'],'not-indexed')

if __name__=='__main__':unittest.main()
