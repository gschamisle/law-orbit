import json
import tempfile
import unittest
from pathlib import Path
from scripts.build_static_galaxies import Writer
from scripts.delegation_baseline import attach_catalog, read_ref
from core.delegation_review import compare


class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def site(self, name, text='제1조(위임) 대통령령으로 정한다.', effective='20260101', previous=None):
        root=self.root/name;root.mkdir();writer=Writer(root)
        meta=dict(id='act',name='시험법',domain='tax',kind='법률',effective=effective,url='https://www.law.go.kr')
        article=dict(jo='1',label='제1조',title='위임',text=text,deleted=False,effective=effective)
        document=dict(meta=meta,articles=[article],details={'1':dict(rows=[])},broad=[])
        entry={**meta,'parts':[],'file':writer.data(document)}
        catalog=dict(laws=[entry],built_at='2026-09-21')
        attach_catalog(writer,'tax',catalog,previous)
        manifest=dict(domains=[dict(id='tax',catalog=writer.data(catalog))])
        (root/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
        return root,catalog

    def test_first_collection_is_not_claimed_as_amendment(self):
        root,c=self.site('first');record=c['delegation_review']['baselines']['act']
        self.assertEqual(record['mode'],'initial')
        self.assertEqual(read_ref(root,record['file'])['articles'][0]['jo'],'1')

    def test_new_collection_retains_previous_body_and_evidence(self):
        first,_=self.site('first')
        second,c=self.site('second','제1조(위임) 정원은 대통령령으로 정한다.','20270101',first)
        record=c['delegation_review']['baselines']['act'];old=read_ref(second,record['file'])
        self.assertEqual(record['mode'],'previous-version')
        self.assertEqual(old['meta']['effective'],'20260101')
        self.assertNotIn('정원',old['articles'][0]['text'])
        self.assertIn('1',old['details'])

    def test_weekly_no_change_does_not_erase_last_different_version(self):
        first,_=self.site('first')
        second,_=self.site('second','제1조(위임) 정원은 대통령령으로 정한다.','20270101',first)
        third,c=self.site('third','제1조(위임) 정원은 대통령령으로 정한다.','20270101',second)
        record=c['delegation_review']['baselines']['act']
        self.assertEqual(record['mode'],'previous-version')
        self.assertEqual(read_ref(third,record['file'])['meta']['effective'],'20260101')

    def test_other_domains_are_not_modified(self):
        catalog={'laws':[]};attach_catalog(Writer(self.root),'fsc',catalog)
        self.assertEqual(catalog,{'laws':[]})

    def test_corrupt_baseline_fails_closed(self):
        root,c=self.site('first');ref=c['delegation_review']['baselines']['act']['file']
        (root/ref['url']).write_bytes(b'broken')
        with self.assertRaisesRegex(ValueError,'checksum'):read_ref(root,ref)

    def test_local_bridge_runs_same_engine_and_rejects_bad_input(self):
        meta=dict(id='act',name='시험법',kind='법률',domain='tax')
        result=compare('','제2조(신설) 정원은 대통령령으로 정한다.',meta=meta,new_article=True)
        self.assertEqual(result['rows'][0]['change'],'added')
        with self.assertRaises(ValueError):compare('','발췌문',meta=meta,new_article=True)


if __name__=='__main__':unittest.main()
