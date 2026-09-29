"""Offline publication-scope, credential and immutable-stage collection tests."""
from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import quote, quote_plus

from scripts import collect_healthcare_expansion as collector

STAMP = '20260929'
SECRET = 'fixture+credential with/slash'


def inventory_fixture():
    profile = collector.WORK_PROFILES['medical']
    records = []
    for provider, names in (('eflaw', profile['required']), ('admrul', profile['required_rules'])):
        for name in names:
            number = len(records) + 1
            records.append(dict(name=name, provider=provider, managing_authority='보건복지부',
                                category='medical', state='current-candidate', effective=STAMP,
                                uid=f'{provider}:{number}', edition_key=f'{provider}:{number}:1:{STAMP}'))
    return dict(domain='medical', as_of=STAMP, records=records, scope='test')


def document_fixture(item):
    return {**item, 'state': 'current-body-verified', 'fetched_at': STAMP,
            'body_status': 'indexed-statute-text', 'articles': [], 'annexes': []}


def source_fixture(inventory):
    docs = [document_fixture(item) for item in inventory['records']]
    return dict(domain='medical', built_at=STAMP, inventory=inventory,
                laws=[d for d in docs if d['provider']=='eflaw'],
                administrative_rules=[d for d in docs if d['provider']=='admrul'])


class HealthcareCollectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.destination = self.root / 'staged'
        self.inventory = inventory_fixture()
        self.source = source_fixture(self.inventory)
        self.stdout = io.StringIO()
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(redirect_stdout(self.stdout))
        self.key = stack.enter_context(patch.object(collector, 'law_api_key', return_value=SECRET))
        self.transport = stack.enter_context(patch.object(collector, 'LawTransport'))

    def save(self, name, value):
        self.destination.mkdir(exist_ok=True)
        (self.destination / name).write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')

    def read(self, name):
        return json.loads((self.destination / name).read_bytes())

    def build_patches(self, stack, decision='limited-release'):
        stack.enter_context(patch.object(collector, 'prepare_source', side_effect=deepcopy))
        stack.enter_context(patch.object(collector, 'attach', side_effect=lambda source: source))
        stack.enter_context(patch.object(collector, 'build_graph', return_value={'domain': 'medical'}))
        stack.enter_context(patch.object(collector, 'validate_bundle', side_effect=lambda bundle, domain: bundle))
        stack.enter_context(patch.object(collector, 'assessment', return_value=dict(
            decision=decision, documents=len(self.inventory['records']), articles=0)))
        stack.enter_context(patch.object(collector, 'report', return_value={'approved': True}))

    def test_invalid_stage_or_date_has_no_files_or_credential_access(self):
        for stage, stamp in (('unknown', STAMP), ('build', 'bad'), ('inventory', '99990101')):
            with self.subTest(stage=stage, stamp=stamp), self.assertRaises((ValueError, collector.CollectionError)):
                collector.run(stage, self.destination, stamp)
        self.assertFalse(self.destination.exists())
        self.key.assert_not_called()
        self.transport.assert_not_called()

    def test_existing_lock_and_outputs_are_preserved(self):
        self.save('source.json', {'keep': True})
        lock = self.destination / 'collect.lock'
        lock.write_text('another owner', encoding='utf-8')
        self.assertEqual(collector.run('inventory', self.destination, STAMP), 2)
        self.assertEqual(lock.read_text(), 'another owner')
        self.assertEqual(self.read('source.json'), {'keep': True})
        self.assertFalse((self.destination / 'last-run.json').exists())
        self.key.assert_not_called()

    def test_wrong_inventory_rejected_before_transport_or_body_collection(self):
        for problem in ('domain', 'date', 'scope', 'missing', 'duplicate', 'future'):
            wrong = deepcopy(self.inventory)
            if problem == 'domain': wrong['domain'] = 'tax'
            elif problem == 'date': wrong['as_of'] = '20260928'
            elif problem == 'scope': wrong['records'][0]['name'] = '약사법'
            elif problem == 'missing': wrong['records'].pop()
            elif problem == 'duplicate': wrong['records'].append(deepcopy(wrong['records'][0]))
            else: wrong['records'][0]['effective'] = '20990101'
            self.save('inventory.json', wrong)
            with self.subTest(problem=problem), patch.object(collector, 'collect_sources') as collect:
                self.assertEqual(collector.run('bodies', self.destination, STAMP), 1)
                collect.assert_not_called()
        self.transport.assert_not_called()
        self.assertFalse((self.destination / 'source.json').exists())
        self.assertFalse((self.destination / 'collect.lock').exists())

    def test_identical_retry_is_safe_and_conflict_does_not_overwrite(self):
        with patch.object(collector, 'discover_inventory', return_value=self.inventory):
            self.assertEqual(collector.run('inventory', self.destination, STAMP), 0)
            before = (self.destination / 'inventory.json').read_bytes()
            self.assertEqual(collector.run('inventory', self.destination, STAMP), 0)
            self.assertEqual((self.destination / 'inventory.json').read_bytes(), before)
        changed = {**self.inventory, 'scope': 'changed declaration'}
        with patch.object(collector, 'discover_inventory', return_value=changed):
            self.assertEqual(collector.run('inventory', self.destination, STAMP), 1)
        self.assertEqual((self.destination / 'inventory.json').read_bytes(), before)
        self.assertEqual(self.read('last-run.json')['status'], 'failure')
        self.assertEqual(self.read('failure.json')['reason'], 'ValueError')

    def test_body_cache_is_guarded_before_a_credential_can_be_written(self):
        self.save('inventory.json', self.inventory)
        def unsafe_document(request, item, stamp, **kwargs):
            return {**document_fixture(item), 'source_url': 'https://www.law.go.kr/?OC=' + quote(SECRET, safe='')}
        # Use the real shared collector so this covers its cache-write boundary.
        with patch.object(collector, 'collect', side_effect=unsafe_document):
            self.assertEqual(collector.run('bodies', self.destination, STAMP), 1)
        self.assertFalse((self.destination / 'source.json').exists())
        self.assertFalse(list((self.destination / 'body-cache').glob('*.json')))
        self.assertEqual(self.read('failure.json')['reason'], 'credential-found-in-output')
        self.assert_no_secret()

    def test_nested_credentials_are_rejected_before_json_escaping(self):
        secret = 'fixture"quoted\\credential'
        self.key.return_value = secret
        value = deepcopy(self.inventory)
        value['unexpected'] = {'nested': [secret]}
        with patch.object(collector, 'discover_inventory', return_value=value):
            self.assertEqual(collector.run('inventory', self.destination, STAMP), 1)
        self.assertFalse((self.destination / 'inventory.json').exists())
        self.assertEqual(self.read('failure.json')['reason'], 'credential-found-in-output')
        self.assertNotIn(secret, self.stdout.getvalue())

    def test_bodies_stage_collects_fixed_scope_and_safe_cache(self):
        self.save('inventory.json', self.inventory)
        with patch.object(collector, 'collect', side_effect=lambda request, item, stamp, **kwargs: document_fixture(item)):
            self.assertEqual(collector.run('bodies', self.destination, STAMP), 0)
        result = self.read('source.json')
        self.assertEqual(len(result['laws']) + len(result['administrative_rules']), len(self.inventory['records']))
        self.assertEqual(len(list((self.destination / 'body-cache').glob('*.json'))), len(self.inventory['records']))
        self.assertEqual(self.read('last-run.json')['stage'], 'bodies')
        self.assert_no_secret()

    def test_offline_build_success_marks_latest_status_and_keeps_failure_history(self):
        self.key.return_value = ''
        self.save('source.json', self.source)
        self.save('failure.json', {'stage': 'inventory', 'reason': 'previous failure'})
        previous_failure = (self.destination / 'failure.json').read_bytes()
        source_before = (self.destination / 'source.json').read_bytes()
        with ExitStack() as stack:
            self.build_patches(stack)
            self.assertEqual(collector.run('build', self.destination, STAMP), 0)
        latest = self.read('last-run.json')
        self.assertEqual((latest['status'], latest['stage'], latest['as_of']), ('success', 'build', STAMP))
        self.assertEqual(set(latest['outputs']), {'validated-bundle.json', 'summary.json'})
        for name, expected in latest['outputs'].items():
            self.assertEqual(hashlib.sha256((self.destination / name).read_bytes()).hexdigest(), expected)
        self.assertEqual((self.destination / 'failure.json').read_bytes(), previous_failure)
        self.assertEqual((self.destination / 'source.json').read_bytes(), source_before)
        self.transport.assert_not_called()

    def test_build_hold_or_output_conflict_publishes_no_partial_bundle(self):
        self.save('source.json', self.source)
        with ExitStack() as stack:
            self.build_patches(stack, decision='hold')
            self.assertEqual(collector.run('build', self.destination, STAMP), 1)
        self.assertFalse((self.destination / 'validated-bundle.json').exists())
        self.save('summary.json', {'older': 'immutable'})
        with ExitStack() as stack:
            self.build_patches(stack)
            self.assertEqual(collector.run('build', self.destination, STAMP), 1)
        self.assertFalse((self.destination / 'validated-bundle.json').exists())
        self.assertEqual(self.read('summary.json'), {'older': 'immutable'})

    def test_source_scope_must_match_inventory_before_preparation(self):
        for problem in ('domain', 'date', 'missing', 'category'):
            source = deepcopy(self.source)
            if problem == 'domain': source['domain'] = 'tax'
            elif problem == 'date': source['built_at'] = '20260928'
            elif problem == 'missing': source['laws'].pop()
            else: source['laws'][0]['category'] = 'tax'
            self.save('source.json', source)
            with self.subTest(problem=problem), patch.object(collector, 'prepare_source') as prepare:
                self.assertEqual(collector.run('build', self.destination, STAMP), 1)
                prepare.assert_not_called()

    def test_progress_and_error_text_are_redacted_and_replacement_lock_survives(self):
        def failure(request, domain, stamp, progress):
            progress('unsafe progress', SECRET, quote(SECRET, safe=''))
            raise collector.CollectionError('request:' + quote_plus(SECRET, safe=''))
        with patch.object(collector, 'discover_inventory', side_effect=failure):
            self.assertEqual(collector.run('inventory', self.destination, STAMP), 1)
        self.assert_no_secret()
        self.assertIn('[redacted]', self.stdout.getvalue())
        def replaced_lock(request, domain, stamp, progress):
            (self.destination / 'collect.lock').write_text('replacement owner', encoding='utf-8')
            return self.inventory
        with patch.object(collector, 'discover_inventory', side_effect=replaced_lock):
            self.assertEqual(collector.run('inventory', self.destination, STAMP), 0)
        self.assertEqual((self.destination / 'collect.lock').read_text(), 'replacement owner')

    def assert_no_secret(self):
        content = self.stdout.getvalue() + ''.join(p.read_text(encoding='utf-8') for p in self.destination.rglob('*.json'))
        for value in (SECRET, quote(SECRET, safe=''), quote_plus(SECRET, safe='')):
            self.assertNotIn(value, content)


if __name__ == '__main__':
    unittest.main()
