import json,os,unittest,tempfile
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
from core.mofe_profiles import selected,PROFILES
from core.medical_annexes import attach,xml_digest
from core.medical_universe import BUNDLE,load_bundle,validate_bundle
from core.medical_profile import (
    PROFILE,BASES,PUBLIC_BASES,INSURANCE_BASES,STATUTES,LEGACY_STATUTES,
    SUPPORT,ACTS,BENEFITS,document_tags,article_tags,
)
TEST_BUNDLE=Path(os.environ.get('LAW_ORBIT_MEDICAL_TEST_BUNDLE',str(BUNDLE)))

class MedicalPolicy(unittest.TestCase):
    def test_scope_and_shared_authorities(self):
        self.assertTrue(selected('medical','의료법','보건복지부,질병관리청','eflaw'))
        self.assertTrue(selected('medical','보건의료기본법','보건복지부,질병관리청','eflaw'))
        self.assertTrue(selected('medical','보건의료기본법 시행령','보건복지부,질병관리청','eflaw'))
        self.assertTrue(selected('medical','지역보건법','보건복지부,질병관리청','eflaw'))
        self.assertTrue(selected('medical','국민건강증진법 시행령','보건복지부,질병관리청','eflaw'))
        self.assertFalse(selected('medical','보건의료기본법','질병관리청','eflaw'))
        self.assertFalse(selected('medical','지역보건법','질병관리청','eflaw'))
        self.assertFalse(selected('medical','의료법','보건복지부,식품의약품안전처','eflaw'))
        self.assertFalse(selected('medical','간호법','질병관리청','eflaw'))
        self.assertFalse(selected('medical','국민건강보험법','보건복지부,질병관리청','eflaw'))
        self.assertFalse(selected('medical','약사법','보건복지부','eflaw'))
        self.assertNotIn('medical',PROFILES)
    def test_exact_phase_one_scope_preserves_original_documents(self):
        self.assertEqual(len(STATUTES),25)
        self.assertEqual(len(set(STATUTES)),25)
        self.assertEqual(set(PROFILE['required']),set(STATUTES))
        self.assertEqual(set(PROFILE['rules']),{ACTS})
        self.assertEqual(set(PROFILE['required_rules']),{ACTS})
        self.assertEqual(len(LEGACY_STATUTES),7)
        self.assertTrue(set(LEGACY_STATUTES).issubset(STATUTES))
        self.assertIn(SUPPORT,STATUTES)
        self.assertIn(BENEFITS,STATUTES)
        self.assertTrue(set(PUBLIC_BASES+INSURANCE_BASES).issubset(STATUTES))
        self.assertNotIn('보건의료기본법 시행규칙',STATUTES)
        for name in STATUTES:
            self.assertTrue(selected('medical',name,'보건복지부','eflaw'),name)
    def test_unapproved_families_and_fee_notices_remain_outside_scope(self):
        for base in ('감염병의 예방 및 관리에 관한 법률','응급의료에 관한 법률','약사법','의료기기법'):
            for suffix in ('',' 시행령',' 시행규칙'):
                self.assertFalse(selected('medical',base+suffix,'보건복지부','eflaw'))
        for name in ('건강보험 행위 급여·비급여 목록표 및 급여 상대가치점수','요양급여의 적용기준 및 방법에 관한 세부사항'):
            self.assertFalse(selected('medical',name,'보건복지부','admrul'))
        self.assertFalse(selected('medical','보건의료기본법 시행규칙','보건복지부','eflaw'))
    def test_every_declared_document_is_required_without_network(self):
        from core.mofe_collection import discover_inventory
        from core.fsc_collection import CollectionError
        names=(*STATUTES,ACTS)
        for missing in names:
            records=[dict(name=n,state='current-candidate',uid=str(i),edition_key=str(i))
                     for i,n in enumerate(names) if n!=missing]
            def fake_query(*args,**kwargs):return dict(records=records,received=len(records))
            with self.subTest(missing=missing),patch('core.mofe_collection.discover_query',fake_query):
                with self.assertRaises(CollectionError) as raised:
                    discover_inventory(lambda *args:self.fail('Network request attempted'),'medical','20260929')
                self.assertIn('required-documents-missing:'+missing,str(raised.exception))
    def test_three_axes_keep_legacy_links_and_multiple_topics(self):
        self.assertEqual(list(PROFILE['sectors']),['all','institutions','public','insurance'])
        self.assertEqual(PROFILE['sector_aliases'],dict(opening='institutions',staff='institutions',support='institutions'))
        self.assertEqual(PROFILE['default_laws']['public'],'지역보건법')
        self.assertEqual(PROFILE['default_refs']['insurance'],'제42조')
        self.assertEqual(document_tags(BENEFITS),['insurance'])
        self.assertEqual(document_tags('공공보건의료에 관한 법률 시행규칙'),['public'])
        self.assertEqual(document_tags('약사법'),[])
        self.assertEqual(article_tags('국민건강보험법',dict(title='정의',text='용어의 뜻은 다음과 같다.')),['insurance'])
        insurance=article_tags('국민건강보험법',dict(title='요양기관',text='「의료법」에 따라 개설된 의료기관과 「지역보건법」에 따른 보건소'))
        self.assertEqual(set(insurance),{'institutions','public','insurance'})
        public=article_tags('공공보건의료에 관한 법률 시행규칙',dict(title='협약',text='「의료법」 제33조제4항에 따른다.'))
        self.assertEqual(set(public),{'institutions','public'})
    def test_source_preparation_keeps_owner_tags_and_cross_topic_tags(self):
        from core.mofe_collection import prepare_source
        source=dict(domain='medical',laws=[dict(name='국민건강보험법',provider='eflaw',category='medical',
                    managing_authority='보건복지부',articles=[
                    dict(jo='1',title='목적',text='용어의 뜻은 다음과 같다.'),
                    dict(jo='42',title='요양기관',text='「의료법」에 따라 개설된 의료기관과 「지역보건법」에 따른 보건소')])],administrative_rules=[])
        prepared=prepare_source(source)['laws'][0]
        self.assertEqual(prepared['articles'][0]['sectors'],['insurance'])
        self.assertEqual(set(prepared['articles'][1]['sectors']),{'institutions','public','insurance'})
        self.assertNotIn('sectors',source['laws'][0]['articles'][0])
    def test_xml_whitespace_is_not_an_edition_but_text_changes_are(self):
        self.assertEqual(xml_digest(b'<r><a id="1">text</a></r>'),xml_digest(b'<r>\n  <a id="1">text</a>\n</r>'))
        self.assertNotEqual(xml_digest(b'<r><a>text</a></r>'),xml_digest(b'<r><a>changed</a></r>'))
    def test_missing_data_does_not_substitute_tax(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_string("from ui.sector_map_ui import render\nrender(dict(domain='medical',prefix='missing_medical',title='의료'),'output/does-not-exist/bundle.json')").run()
        self.assertFalse(app.exception,str(app.exception))
        self.assertTrue(any('의료 데이터 미수집' in i.value for i in app.info))

@unittest.skipUnless(TEST_BUNDLE.is_file(),'Requires collected medical corpus')
class MedicalCollected(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.b=load_bundle(TEST_BUNDLE)
    def test_scoped_complete_docs_and_real_reverse_annex_evidence(self):
        from core.galaxy_focus import analyze_focus
        docs=self.b['source']['laws']+self.b['source']['administrative_rules']
        self.assertEqual({d['name'] for d in docs},set(STATUTES)|{ACTS})
        self.assertEqual(len(docs),26);self.assertTrue(all(d['articles'] for d in docs))
        self.assertEqual(sum(bool(a.get('body_analysis')) for d in docs for a in d.get('annexes',[])),4)
        rows=analyze_focus('의료법','43',self.b['graph'])['rows']
        staff=[r for r in rows if r.get('source_layer')=='annex-body' and r['source_jo']=='별표 5']
        self.assertEqual(len(staff),9);self.assertTrue(all(r['neighbor_kind']=='annex' for r in staff))
        self.assertEqual(self.b['assessment']['decision'],'limited-release')
    def test_real_public_and_insurance_connections_have_collected_endpoints(self):
        edges=self.b['graph']['edges']
        for source,jo,target,ref,kind in (
                ('지역보건법','11','보건의료기본법','제3조제4호','article'),
                ('지역보건법','7','국민건강증진법','제4조','article'),
                ('공공보건의료에 관한 법률 시행규칙','2','의료법','제33조제4항','article'),
                ('국민건강보험법','42','의료법','제3조의4','article'),
                ('국민건강보험법','42','지역보건법','법령·정의 참조','law'),
                ('의료급여법','9','의료법','제33조제3항','article'),
                ('의료급여법','9','의료법','제33조제4항','article')):
            with self.subTest(source=source,jo=jo,target=target,ref=ref):
                self.assertTrue(any(e['source_law']==source and e['source_jo']==jo and e['target_law']==target
                                    and e['target_ref']==ref and e['target_kind']==kind for e in edges))
        self.assertTrue(any(e['source_law']=='국민건강보험법' and e['source_jo']=='42'
                            and e['target_law']=='약사법' and e['target_status']=='not-collected'
                            for e in self.b['graph']['external_references']))
    def test_all_healthcare_questions_have_real_collected_connections(self):
        from core.mofe_universe import assessment
        cases=assessment(self.b)['cases']
        self.assertEqual(len(cases),7)
        self.assertEqual({(c['law'],c['jo']) for c in cases},{(c[0],c[1]) for c in PROFILE['cases']})
        self.assertTrue(all(c['available'] and c['connected_articles'] and c['evidence_ids'] for c in cases))
    def test_unnumbered_annex_is_linked_from_its_own_rule(self):
        from core.medical_profile import ACTS
        self.assertTrue(any(e['source_law']==ACTS and e['source_jo']=='2' and e['target_ref']=='별표' and e['target_kind']=='annex' for e in self.b['graph']['edges']))
    def test_changed_annex_body_and_evidence_are_rejected(self):
        changed=deepcopy(self.b)
        a=next(a for d in changed['source']['laws'] for a in d.get('annexes',[]) if a.get('body_analysis'))
        a['body_analysis']['text']+='변조'
        with self.assertRaises(ValueError):validate_bundle(changed)
        changed=deepcopy(self.b);e=next(e for e in changed['graph']['edges'] if e.get('source_layer')=='annex-body');e['source_file_sha256']='changed'
        with self.assertRaises(ValueError):validate_bundle(changed)
    def test_sample_cannot_attach_to_a_changed_api_document(self):
        source=deepcopy(self.b['source']);d=next(d for d in source['laws'] if d['name']=='의료법 시행규칙');d['annex_xml_structure_sha256']='changed'
        with self.assertRaisesRegex(ValueError,'판본'):attach(source)
    def test_export_preserves_annex_body_offsets_and_mixed_coverage(self):
        from scripts.build_static_galaxies import Writer,export_documents
        import gzip
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);entries,_=export_documents(Writer(root),'medical','',self.b['source']['laws']+self.b['source']['administrative_rules'],self.b['graph'])
            entry=next(d for d in entries if d['name']=='의료법 시행규칙')
            doc=json.loads(gzip.decompress((root/entry['file']['url']).read_bytes()))
            annex=next(a for a in doc['annexes'] if a['ref']=='별표 5')
            self.assertEqual(annex['status'],'explicit-citations')
            self.assertTrue(any(a['status']=='not-analyzed' for a in doc['annexes']))
            for r in annex['connections']:
                self.assertEqual(annex['analysis']['text'][r['source_start']:r['source_end']],r['raw'])
            self.assertTrue(any(r['neighbor_jo']=='43' for r in annex['connections']))
    def local_app(self,legacy=None):
        from streamlit.testing.v1 import AppTest
        # Every rerun uses the explicit test snapshot; the active bundle is untouched.
        code=("from pathlib import Path\nfrom unittest.mock import patch\n"
              "from ui.mofe_map_ui import render\n"
              f"with patch('ui.mofe_map_ui.path',return_value=Path({str(TEST_BUNDLE.resolve())!r})):\n"
              "    render('medical')\n")
        app=AppTest.from_string(code,default_timeout=60)
        if legacy:app.session_state['mofe_medical_sector']=legacy
        return app.run()
    def test_local_three_sector_defaults_and_shared_reference_navigation(self):
        app=self.local_app()
        self.assertFalse(app.exception,str(app.exception))
        for sector in ('institutions','public','insurance'):
            with self.subTest(sector=sector):
                app.radio(key='mofe_medical_sector').set_value(sector).run()
                self.assertFalse(app.exception,str(app.exception))
                self.assertEqual(app.selectbox(key=f'mofe_medical_{sector}_law').value,PROFILE['default_laws'][sector])
                self.assertEqual(app.text_input(key=f'mofe_medical_{sector}_ref').value,PROFILE['default_refs'][sector])
                app.button(key=f'mofe_medical_{sector}_run').click().run()
                self.assertFalse(app.exception,str(app.exception))
                self.assertFalse(app.error,str(app.error))
                self.assertTrue(any('역인용' in c.value for c in app.caption))
    def test_local_legacy_sector_state_resolves_to_institutions(self):
        for alias in PROFILE['sector_aliases']:
            with self.subTest(alias=alias):
                app=self.local_app(alias)
                self.assertFalse(app.exception,str(app.exception))
                self.assertEqual(app.radio(key='mofe_medical_sector').value,'institutions')
                self.assertEqual(app.selectbox(key='mofe_medical_institutions_law').value,'의료법')
    def test_local_annex_reader(self):
        app=self.local_app()
        self.assertFalse(app.exception,str(app.exception))
        app.selectbox(key='mofe_medical_all_law').set_value('의료법 시행규칙').run()
        app.selectbox(key='mofe_medical_all_annex_의료법 시행규칙').set_value('별표 5').run()
        self.assertFalse(app.exception,str(app.exception))
        self.assertTrue(any('칸·문단 순서' in c.value for c in app.caption))

if __name__=='__main__':unittest.main()
