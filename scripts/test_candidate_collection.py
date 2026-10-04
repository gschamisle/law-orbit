"""Candidate collection stages: no network, no active corpus mutation."""
from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import quote, quote_plus

from core.fsc_collection import CollectionError
from core.subsidy_profile import NATIONAL, selected as subsidy_selected
from scripts import collect_candidate_domains as candidate

STAMP='20261004'
KEY='SYNTHETIC-CREDENTIAL /+?never-real'
PROFILE={'title':'보조금·지원사업','required':(NATIONAL,),'required_rules':()}


def record(effective=STAMP, state='current-candidate', serial='100'):
    return dict(name=NATIONAL,provider='eflaw',document_id='1',version_id=serial,
                uid='eflaw:1',edition_key='eflaw:1:'+serial+':'+effective,
                effective=effective,promulgated=STAMP,kind='법률',managing_authority='기획예산처',
                category='subsidy',state=state,source_url='https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq='+serial)


def inventory():
    return dict(domain='subsidy',as_of=STAMP,records=[record()],layers=[])


def source():
    document={**record(),'state':'current-body-verified','fetched_at':STAMP,
              'body_sha256':'b'*64,'body_authorities':['기획예산처'],'articles':[],'annexes':[]}
    return dict(domain='subsidy',built_at=STAMP,inventory=inventory(),
                laws=[document],administrative_rules=[],scheduled=[])


class CandidateCollectionTests(unittest.TestCase):
    def setUp(self):
        output=candidate.ROOT/'output';output.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=output,prefix='candidate-stage-tests-')
        self.root=Path(self.temp.name)
        self.patches=[patch.object(candidate,'ROOT',self.root),
                      patch.dict(candidate.WORK_PROFILES,{'subsidy':PROFILE}),
                      patch.object(candidate,'selected',lambda domain,*args:domain=='subsidy' and subsidy_selected(*args)),
                      patch.object(candidate,'law_api_key',return_value=KEY),
                      patch.object(candidate,'LawTransport',return_value=lambda *args:None)]
        for item in self.patches:item.start()
        self.dest=self.root/'output'/('subsidy-candidate-'+STAMP)

    def tearDown(self):
        for item in reversed(self.patches):item.stop()
        self.temp.cleanup()

    def run_stage(self, stage):
        stream=io.StringIO()
        with redirect_stdout(stream):status=candidate.run('subsidy',stage,self.dest,STAMP)
        return status,stream.getvalue()

    def write(self,name,value):
        target=self.dest/name;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')

    def receipts(self):return [json.loads(path.read_text(encoding='utf-8')) for path in (self.dest/'runs').glob('*.json')]

    def test_scope_date_and_future_state_are_checked(self):
        candidate.check_inventory(inventory(),'subsidy',STAMP)
        valid=inventory();valid['records'].append(record('20261005','scheduled','101'))
        candidate.check_inventory(valid,'subsidy',STAMP)
        for field,value in [('domain','privacy'),('as_of','20261003')]:
            changed=inventory();changed[field]=value
            with self.assertRaises(CollectionError):candidate.check_inventory(changed,'subsidy',STAMP)
        for field,value in [('managing_authority','행정안전부'),('state','scheduled'),('category','privacy')]:
            changed=inventory();changed['records'][0][field]=value
            with self.assertRaises(CollectionError):candidate.check_inventory(changed,'subsidy',STAMP)
        duplicate=inventory();duplicate['records']*=2
        with self.assertRaises(CollectionError):candidate.check_inventory(duplicate,'subsidy',STAMP)

    def test_source_identity_and_body_authority_cannot_change_after_inventory(self):
        candidate.check_source(source(),'subsidy',STAMP)
        for field,value in [('version_id','999'),('body_authorities',['행정안전부']),
                            ('state','current-candidate'),('fetched_at','20261003')]:
            changed=source();changed['laws'][0][field]=value
            with self.assertRaises(CollectionError):candidate.check_source(changed,'subsidy',STAMP)
        changed=source();changed['scheduled']=[record('20261005','scheduled','101')]
        with self.assertRaises(CollectionError):candidate.check_source(changed,'subsidy',STAMP)

    def test_destination_cannot_select_an_active_corpus_or_outside_workspace(self):
        for path in (self.root/'output'/'subsidy-universe', self.root/'outside',
                     self.root/'output'/'privacy-candidate-20261004'):
            with self.assertRaises(ValueError):candidate.destination_path('subsidy',path,STAMP)

    def test_missing_key_fails_before_inventory_network(self):
        with patch.object(candidate,'law_api_key',return_value=''),patch.object(candidate,'discover_inventory') as discover:
            status,printed=self.run_stage('inventory')
        self.assertEqual(status,1);discover.assert_not_called()
        self.assertFalse((self.dest/'inventory.json').exists())
        self.assertEqual(self.receipts()[0]['reason'],'missing-law-api-key')

    def test_conflicting_lock_is_preserved_without_reading_credentials(self):
        self.dest.mkdir(parents=True);lock=self.dest/'collect.lock';lock.write_text('other-owner',encoding='utf-8')
        with patch.object(candidate,'law_api_key') as key:status,_=self.run_stage('inventory')
        self.assertEqual(status,2);key.assert_not_called()
        self.assertEqual(lock.read_text(encoding='utf-8'),'other-owner')
        self.assertEqual(list(self.dest.iterdir()),[lock])

    def test_replacement_lock_is_not_removed(self):
        def discover(*args):
            (self.dest/'collect.lock').write_text('replacement-owner',encoding='utf-8')
            return inventory()
        with patch.object(candidate,'discover_inventory',side_effect=discover):status,_=self.run_stage('inventory')
        self.assertEqual(status,0)
        self.assertEqual((self.dest/'collect.lock').read_text(encoding='utf-8'),'replacement-owner')

    def test_existing_inventory_is_not_overwritten(self):
        self.write('inventory.json',{'retained':'original'})
        original=(self.dest/'inventory.json').read_bytes()
        with patch.object(candidate,'discover_inventory',return_value=inventory()):status,_=self.run_stage('inventory')
        self.assertEqual(status,1);self.assertEqual((self.dest/'inventory.json').read_bytes(),original)
        self.assertEqual(self.receipts()[0]['reason'],'ValueError')

    def test_plain_and_url_encoded_credentials_are_never_written_or_logged(self):
        forms=(KEY,quote(KEY,safe=''),quote_plus(KEY,safe=''))
        for secret in forms:
            with self.subTest(secret_kind='encoded' if secret!=KEY else 'plain'):
                stream=io.StringIO()
                with self.assertRaises(CollectionError):candidate.guard({'metadata':[{'request':secret}]},KEY)
                def discover(request,domain,stamp,log):
                    log('URL',secret);raise CollectionError('failure-'+secret)
                with patch.object(candidate,'discover_inventory',side_effect=discover):status,printed=self.run_stage('inventory')
                self.assertEqual(status,1)
                stored=''.join(path.read_text(encoding='utf-8') for path in self.dest.rglob('*.json'))
                for forbidden in forms:self.assertNotIn(forbidden,printed+stored)
        with self.assertRaises(CollectionError):candidate.guard({'OC':'unknown-other-key'},KEY)

    def test_cached_body_with_changed_identity_is_rejected_and_preserved(self):
        self.write('inventory.json',inventory())
        doc=source()['laws'][0];doc['version_id']='999'
        digest=hashlib.sha256(json.dumps(doc,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        name='body-cache/'+hashlib.sha256(doc['edition_key'].encode()).hexdigest()+'.json'
        self.write(name,{'body':doc,'sha256':digest});original=(self.dest/name).read_bytes()
        with patch.object(candidate,'collect_sources') as collect:status,_=self.run_stage('bodies')
        self.assertEqual(status,1);collect.assert_not_called()
        self.assertEqual((self.dest/name).read_bytes(),original)

    def test_credential_in_collected_body_is_rejected_before_shared_cache_write(self):
        self.write('inventory.json',inventory())
        doc=source()['laws'][0];doc['attachments']=[{'url':'https://test.invalid/?OC='+quote(KEY,safe='')}]
        with patch.object(candidate,'collect_document',return_value=doc):status,_=self.run_stage('bodies')
        self.assertEqual(status,1)
        self.assertFalse((self.dest/'source.json').exists())
        self.assertEqual(list((self.dest/'body-cache').glob('*.json')),[])
        self.assertEqual(self.receipts()[0]['reason'],'credential-found-in-output')

    def test_hold_decision_cannot_emit_a_releasable_bundle(self):
        self.write('source.json',source())
        with patch.object(candidate,'prepare_source',side_effect=lambda value:value),\
             patch.object(candidate,'build_graph',return_value={}),\
             patch.object(candidate,'validate_bundle',side_effect=lambda value,domain:value),\
             patch.object(candidate,'assessment',return_value={'decision':'hold'}):
            status,_=self.run_stage('build')
        self.assertEqual(status,1)
        self.assertFalse((self.dest/'validated-bundle.json').exists())
        self.assertEqual(self.receipts()[0]['reason'],'candidate-usefulness-gate-hold')

    def test_build_preflights_all_outputs_before_writing_any_new_file(self):
        self.write('source.json',source());self.write('summary.json',{'retained':'original'})
        original=(self.dest/'summary.json').read_bytes()
        with patch.object(candidate,'prepare_source',side_effect=lambda value:value),\
             patch.object(candidate,'build_graph',return_value={}),\
             patch.object(candidate,'validate_bundle',side_effect=lambda value,domain:value),\
             patch.object(candidate,'assessment',return_value={'decision':'limited-release'}),\
             patch.object(candidate,'report',return_value={'different':'new'}):
            status,_=self.run_stage('build')
        self.assertEqual(status,1)
        self.assertFalse((self.dest/'validated-bundle.json').exists())
        self.assertEqual((self.dest/'summary.json').read_bytes(),original)


if __name__=='__main__':unittest.main()
