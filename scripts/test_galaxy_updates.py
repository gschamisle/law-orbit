"""Safety and scheduling regressions; no network or real credentials."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from core import galaxy_updates as updates
from core.fsc_collection import CollectionError


def tax_fixture():
    text='「나법」 제1조'
    docs=[dict(name=n,category='tax',family=n,law_id=str(i),mst=str(i+10),effective='20260101',
               articles=[dict(jo='1',text=text,title='인용')],annexes=[])
          for i,n in enumerate(['가법','나법'],1)]
    source=dict(built_at='2026-09-16',laws=docs)
    graph=dict(built_at=source['built_at'],laws=['가법','나법'],tax_laws=['가법','나법'],
               edges=[dict(source_law='가법',source_jo='1',source_start=0,source_end=len(text),
                           cite_raw=text,target_law='나법')])
    return dict(source=source,graph=graph)


class UpdateTests(unittest.TestCase):
    def test_weekly_monday_and_missed_week_catchup(self):
        self.assertTrue(updates.full_refresh_due(date(2026,9,21),'2026-09-16'))
        self.assertFalse(updates.full_refresh_due(date(2026,9,21),'2026-09-21'))
        self.assertFalse(updates.full_refresh_due(date(2026,9,17),'2026-09-16'))
        self.assertTrue(updates.full_refresh_due(date(2026,9,22),'2026-09-14'))

    def test_future_fsc_editions_do_not_count_as_current(self):
        inventory={'layers':{'eflaw':{'records':[
            {'uid':'eflaw:1','edition_key':'old','state':'current-candidate'},
            {'uid':'eflaw:2','edition_key':'future','state':'scheduled'}]}}}
        self.assertEqual(updates.inventory_signature('fsc',inventory),[('eflaw:1','old')])
        inventory['layers']['eflaw']['records'][1]['state']='current-candidate'
        self.assertEqual(len(updates.inventory_signature('fsc',inventory)),2)

    def test_valid_publish_is_atomic_and_preserves_backup(self):
        old=tax_fixture();new=deepcopy(old)
        new['source']['built_at']=new['graph']['built_at']='2026-09-17'
        with tempfile.TemporaryDirectory() as folder:
            dest=Path(folder)/'bundle.json'
            dest.write_text(json.dumps({**old['graph'],'source':old['source']}),encoding='utf-8')
            previous_bytes=dest.read_bytes()
            updates.publish('tax',new,old,dest,'20260917','test')
            self.assertEqual((dest.parent/'history/test/bundle.json').read_bytes(),previous_bytes)
            live=updates.read_json(dest)
            self.assertEqual(live['built_at'],live['source']['built_at'])
            self.assertEqual(live['built_at'],'2026-09-17')

    def test_failed_validation_never_replaces_previous_data(self):
        old=tax_fixture()
        for mutation in ('missing','future','regressed','evidence','empty'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as folder:
                dest=Path(folder)/'bundle.json';dest.write_text('old',encoding='utf-8')
                new=deepcopy(old)
                if mutation=='missing':new['source']['laws'].pop()
                if mutation=='future':new['source']['laws'][0]['effective']='20270101'
                if mutation=='regressed':new['source']['laws'][0]['effective']='20250101'
                if mutation=='evidence':new['graph']['edges'][0]['cite_raw']='다른 문구'
                if mutation=='empty':new['graph']['edges']=[]
                with self.assertRaises(CollectionError): updates.publish('tax',new,old,dest,'20260917','test')
                self.assertEqual(dest.read_text(),'old')

    def test_replace_failure_preserves_active_file(self):
        old=tax_fixture()
        with tempfile.TemporaryDirectory() as folder:
            dest=Path(folder)/'bundle.json';dest.write_text('old',encoding='utf-8')
            with patch('pathlib.Path.replace',side_effect=OSError('simulated write failure')):
                with self.assertRaises(OSError): updates.publish('tax',old,old,dest,'20260917','test')
            self.assertEqual(dest.read_text(),'old')

    def test_existing_lock_prevents_overlapping_runs(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(updates,'STATE_DIR',Path(folder)):
            (Path(folder)/'update.lock').touch()
            with patch.object(updates,'law_api_key',side_effect=AssertionError('must not start')):
                self.assertEqual(updates.run()['status'],'busy')

    def test_check_only_does_not_collect_publish_or_advance_update_state(self):
        old=tax_fixture()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with patch.multiple(updates,STATE_DIR=root/'state',TAX_BUNDLE=root/'tax/bundle.json',FSC_BUNDLE=root/'fsc/bundle.json'), \
                 patch.object(updates,'law_api_key',return_value='test-key'), \
                 patch.object(updates,'current_bundle',return_value=old), \
                 patch.object(updates,'tax_inventory',return_value={}),patch.object(updates,'fsc_inventory',return_value={}), \
                 patch.object(updates,'inventory_signature',return_value=['changed']), \
                 patch.object(updates,'collect_candidate',side_effect=AssertionError('must not collect')):
                result=updates.run(check_only=True)
            self.assertEqual(result['status'],'ok')
            self.assertTrue(all(d['status']=='update-available' for d in result['domains'].values()))
            self.assertFalse((root/'state/state.json').exists())
            self.assertFalse((root/'tax/bundle.json').exists())
            self.assertFalse((root/'fsc/bundle.json').exists())

    def test_live_tax_bundle_is_preferred_without_touching_legacy(self):
        from core import law_universe
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'live.json'
            with patch.object(law_universe,'LIVE_BUNDLE',path):
                self.assertNotEqual(law_universe.graph_path(),path)
                old=tax_fixture();updates.atomic_json(path,{**old['graph'],'source':old['source']})
                self.assertEqual(law_universe.graph_path(),path)
                self.assertEqual(law_universe.load_graph()['source'],old['source'])

if __name__=='__main__':unittest.main()
