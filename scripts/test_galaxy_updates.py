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


def fsc_fixture():
    fixture = tax_fixture()
    for doc in fixture['source']['laws']:
        doc.update(category='fsc', provider='eflaw', document_id=doc['law_id'],
                   uid='eflaw:' + doc['law_id'], body_status='indexed-statute-text',
                   edition_key=f"eflaw:{doc['law_id']}:{doc['mst']}:{doc['effective']}")
    fixture['source']['administrative_rules'] = [dict(
        name='운영지침', category='fsc', provider='admrul', document_id='3', uid='admrul:3',
        effective='20260101', edition_key='admrul:3:30:20260101', body_status='indexed-administrative-text',
        articles=[dict(jo='1', text='「나법」 제1조', title='목적')], annexes=[])]
    fixture['graph'].update(domain='fsc', laws=['가법', '나법', '운영지침'],
                            focus_laws=['가법', '나법', '운영지침'], external_references=[])
    fixture['graph'].pop('tax_laws')
    return fixture


def renamed_fixture(fixture):
    result = deepcopy(fixture)
    titles = {'가법': '개정가법', '운영지침': '운영규정'}
    for doc in updates.source_documents(result['source']):
        doc['name'] = titles.get(doc['name'], doc['name'])
    for key in ('laws', 'tax_laws', 'focus_laws'):
        if key in result['graph']:
            result['graph'][key] = [titles.get(name, name) for name in result['graph'][key]]
    for edge in result['graph']['edges']:
        for key in ('source_law', 'target_law'):
            edge[key] = titles.get(edge[key], edge[key])
    result['source']['built_at'] = result['graph']['built_at'] = '2026-09-17'
    return result


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

    def test_same_document_rename_publishes_with_backup_and_new_graph_names(self):
        for domain, make in (('tax', tax_fixture), ('fsc', fsc_fixture)):
            with self.subTest(domain=domain), tempfile.TemporaryDirectory() as folder:
                old = make(); new = renamed_fixture(old)
                dest = Path(folder) / 'bundle.json'
                dest.write_text(json.dumps(old), encoding='utf-8')
                saved = dest.read_bytes()
                updates.publish(domain, new, old, dest, '20260917', 'rename')
                self.assertEqual((dest.parent / 'history/rename/bundle.json').read_bytes(), saved)
                active = updates.read_json(dest)
                graph = active['graph'] if domain == 'fsc' else active
                self.assertIn('개정가법', graph['laws'])
                self.assertNotIn('가법', graph['laws'])
                self.assertEqual(graph['edges'][0]['source_law'], '개정가법')
                self.assertEqual(old['source']['laws'][0]['name'], '가법')
                renames = updates.renamed_documents(domain, new['source'], old['source'])
                self.assertEqual(len(renames), 2 if domain == 'fsc' else 1)
                self.assertEqual(next(r for r in renames if r['uid'] == 'eflaw:1')['name'], '개정가법')

    def test_name_match_cannot_hide_replaced_document_id(self):
        for domain, make in (('tax', tax_fixture), ('fsc', fsc_fixture)):
            old = make(); new = deepcopy(old)
            new['source']['laws'][0]['law_id'] = '4'
            if domain == 'fsc':
                new['source']['laws'][0].update(document_id='4', uid='eflaw:4')
            with self.subTest(domain=domain):
                with self.assertRaisesRegex(CollectionError, 'document-scope-shrank'):
                    updates.validate_candidate(domain, new, old, '20260917')

    def test_invalid_or_duplicate_identity_rejected_in_previous_and_candidate(self):
        for side in ('previous', 'candidate'):
            for mutation in ('empty', 'duplicate', 'provider', 'document-id', 'uid-format', 'law-id', 'duplicate-name'):
                old = fsc_fixture(); new = deepcopy(old)
                value = old if side == 'previous' else new
                first, second = value['source']['laws']
                if mutation == 'empty': first['uid'] = ''
                if mutation == 'duplicate':
                    second.update(uid=first['uid'], document_id=first['document_id'], law_id=first['law_id'])
                if mutation == 'provider': first['provider'] = 'unknown'
                if mutation == 'document-id': first['document_id'] = ''
                if mutation == 'uid-format': first['uid'] = 'admrul:1'
                if mutation == 'law-id': first['law_id'] = '9'
                if mutation == 'duplicate-name': second['name'] = first['name']
                with self.subTest(side=side, mutation=mutation):
                    with self.assertRaises(CollectionError):
                        updates.validate_candidate('fsc', new, old, '20260917')

    def test_renamed_document_failure_preserves_active_and_creates_no_backup(self):
        for domain, make in (('tax', tax_fixture), ('fsc', fsc_fixture)):
            for mutation in ('missing', 'regressed', 'future', 'empty-body', 'evidence'):
                with self.subTest(domain=domain, mutation=mutation), tempfile.TemporaryDirectory() as folder:
                    old = make(); new = renamed_fixture(old)
                    first = new['source']['laws'][0]
                    if mutation == 'missing': new['source']['laws'].pop(0)
                    if mutation == 'regressed': first['effective'] = '20250101'
                    if mutation == 'future': first['effective'] = '20270101'
                    if mutation == 'empty-body': first['articles'] = []
                    if mutation == 'evidence': new['graph']['edges'][0]['cite_raw'] = '위조 문구'
                    dest = Path(folder) / 'bundle.json'; dest.write_bytes(b'preserve-active')
                    with self.assertRaises(CollectionError):
                        updates.publish(domain, new, old, dest, '20260917', 'rejected')
                    self.assertEqual(dest.read_bytes(), b'preserve-active')
                    self.assertFalse((dest.parent / 'history').exists())

    def test_tax_inventory_accepts_renamed_titles_with_same_law_id(self):
        old = tax_fixture()['source']; rows = deepcopy(old['laws'])
        rows[0]['name'] = '개정가법'
        with patch('scripts.collect_law_universe.discover', return_value=rows):
            result = updates.tax_inventory(old, 'test-key', '20260917')
        self.assertEqual({r['law_id'] for r in result['records']}, {'1', '2'})
        self.assertIn('개정가법', {r['name'] for r in result['records']})

    def test_tax_inventory_rejects_same_name_with_missing_old_id(self):
        old = tax_fixture()['source']; rows = deepcopy(old['laws'])
        rows[0]['law_id'] = '4'
        with patch('scripts.collect_law_universe.discover', return_value=rows):
            with self.assertRaisesRegex(CollectionError, 'tax-scope-shrank'):
                updates.tax_inventory(old, 'test-key', '20260917')

    def test_update_report_records_confirmed_title_changes(self):
        old = {'tax': tax_fixture(), 'fsc': fsc_fixture()}
        new = {domain: renamed_fixture(fixture) for domain, fixture in old.items()}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.multiple(updates, STATE_DIR=root/'state', TAX_BUNDLE=root/'tax/bundle.json',
                                FSC_BUNDLE=root/'fsc/bundle.json'), \
                 patch.object(updates, 'law_api_key', return_value='test-key'), \
                 patch.object(updates, 'current_bundle', side_effect=lambda domain: old[domain]), \
                 patch.object(updates, 'tax_inventory', return_value={}), \
                 patch.object(updates, 'fsc_inventory', return_value={}), \
                 patch.object(updates, 'inventory_signature', return_value=['changed']), \
                 patch.object(updates, 'collect_candidate', side_effect=lambda domain,*args: new[domain]):
                result = updates.run(mode='full')
            self.assertEqual(result['status'], 'ok')
            self.assertEqual(len(result['domains']['fsc']['renamed_documents']), 2)
            self.assertEqual(len(result['domains']['tax']['renamed_documents']), 1)
            self.assertFalse((root/'state/update.lock').exists())
            self.assertEqual(updates.read_json(root/'state/latest.json'), result)

if __name__=='__main__':unittest.main()
