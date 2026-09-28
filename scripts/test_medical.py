import json,unittest,tempfile
from pathlib import Path
from copy import deepcopy
from core.mofe_profiles import selected,PROFILES
from core.medical_annexes import attach,xml_digest
from core.medical_universe import BUNDLE,load_bundle,validate_bundle

class MedicalPolicy(unittest.TestCase):
    def test_scope_and_shared_authorities(self):
        self.assertTrue(selected('medical','의료법','보건복지부,질병관리청','eflaw'))
        self.assertFalse(selected('medical','간호법','질병관리청','eflaw'))
        self.assertFalse(selected('medical','약사법','보건복지부','eflaw'))
        self.assertNotIn('medical',PROFILES)
    def test_xml_whitespace_is_not_an_edition_but_text_changes_are(self):
        self.assertEqual(xml_digest(b'<r><a id="1">text</a></r>'),xml_digest(b'<r>\n  <a id="1">text</a>\n</r>'))
        self.assertNotEqual(xml_digest(b'<r><a>text</a></r>'),xml_digest(b'<r><a>changed</a></r>'))
    def test_missing_data_does_not_substitute_tax(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_string("from ui.sector_map_ui import render\nrender(dict(domain='medical',prefix='missing_medical',title='의료'),'output/does-not-exist/bundle.json')").run()
        self.assertFalse(app.exception,str(app.exception))
        self.assertTrue(any('의료 데이터 미수집' in i.value for i in app.info))

@unittest.skipUnless(BUNDLE.is_file(),'Requires collected medical corpus')
class MedicalCollected(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.b=load_bundle()
    def test_scoped_complete_docs_and_real_reverse_annex_evidence(self):
        from core.galaxy_focus import analyze_focus
        docs=self.b['source']['laws']+self.b['source']['administrative_rules']
        self.assertEqual(len(docs),8);self.assertTrue(all(d['articles'] for d in docs))
        self.assertEqual(sum(bool(a.get('body_analysis')) for d in docs for a in d.get('annexes',[])),4)
        rows=analyze_focus('의료법','43',self.b['graph'])['rows']
        staff=[r for r in rows if r.get('source_layer')=='annex-body' and r['source_jo']=='별표 5']
        self.assertEqual(len(staff),9);self.assertTrue(all(r['neighbor_kind']=='annex' for r in staff))
        self.assertEqual(self.b['assessment']['decision'],'limited-release')
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
    def test_local_annex_reader(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_string("from ui.mofe_map_ui import render\nrender('medical')",default_timeout=60).run()
        app.selectbox(key='mofe_medical_all_law').set_value('의료법 시행규칙').run()
        app.selectbox(key='mofe_medical_all_annex_의료법 시행규칙').set_value('별표 5').run()
        self.assertFalse(app.exception,str(app.exception))
        self.assertTrue(any('칸·문단 순서' in c.value for c in app.caption))

if __name__=='__main__':unittest.main()
