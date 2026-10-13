"""Edition checks must not confuse failures, names, dates, or omitted regions."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.edition_watch import compare, historical_identity, inventory, published_documents, check
from core.fsc_collection import CollectionError
from scripts.build_static_galaxies import Writer
from scripts.check_all_editions import lock, run


class EditionWatchTests(unittest.TestCase):
    def item(self):
        return dict(provider='eflaw', serial='123', name='옛 법률', effective='20260101', domains=['tax'])

    def current(self, **changes):
        return dict(dict(provider='eflaw', stable_id='000001', serial='123', name='옛 법률',
                         effective='20260101', state='current'), **changes)

    def test_stable_identity_handles_renamed_same_day_edition(self):
        result = compare(self.item(), [self.current(serial='456', name='새 법률')], '000001')
        self.assertEqual(result['status'], 'changed')
        self.assertTrue(result['renamed'])
        self.assertTrue(result['edition_changed'])
        self.assertEqual(compare(self.item(), [self.current()], '000001')['status'], 'unchanged')

    def test_missing_future_ambiguous_and_invalid_dates_are_not_unchanged(self):
        for rows, status in (([], 'missing-current'),
            ([self.current(), self.current(serial='222')], 'ambiguous-current'),
            ([self.current(state='scheduled')], 'scheduled'),
            ([self.current(state='repealed')], 'repealed'),
            ([self.current(effective='20250101')], 'baseline-ahead-of-current')):
            self.assertEqual(compare(self.item(), rows, '000001')['status'], status)
        item = self.item(); item['effective'] = 'unknown'
        self.assertEqual(compare(item, [self.current()], '000001')['status'], 'baseline-date-unverified')

    def test_old_mst_uses_bound_title_and_date_not_key_as_serial(self):
        raw = '<법령 법령키="0000012025100121000"><기본정보><법령ID>000001</법령ID><법령명_한글>옛 법률</법령명_한글><시행일자>20260101</시행일자></기본정보></법령>'.encode()
        calls = []
        def request(endpoint, params):
            calls.append(params); return raw
        self.assertEqual(historical_identity(request, self.item()), '000001')
        self.assertEqual(calls[0]['MST'], '123')
        changed = self.item(); changed['effective'] = '20260201'
        with self.assertRaises(CollectionError): historical_identity(request, changed)

    def test_short_api_page_fails_closed(self):
        raw = b'<LawSearch><resultCode>00</resultCode><page>1</page><totalCnt>1</totalCnt></LawSearch>'
        with self.assertRaises(CollectionError):
            inventory(lambda *_: raw, 'eflaw', '20261013', Path('.'))

    def site(self, root):
        writer = Writer(root)
        law = dict(id='national', name='옛 법률', effective='20260101',
                   url='https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=123')
        local = dict(id='local', name='지역 조례', effective='20260101',
                     url='https://www.law.go.kr/LSW/ordinInfoP.do?ordinSeq=99')
        regional = writer.data(dict(laws=[local]))
        a = writer.data(dict(laws=[law], regions=[dict(catalog=regional)]))
        b = writer.data(dict(laws=[law]))
        manifest = dict(version='sample', domains=[dict(id='local_tax', catalog=a), dict(id='tax', catalog=b)])
        (root/'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')

    def test_all_fields_and_regions_deduplicate_only_identical_editions(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); self.site(root)
            _, items, counts = published_documents(root)
            self.assertEqual(counts, dict(local_tax=2, tax=1))
            self.assertEqual(len(items), 2)
            self.assertEqual(items[0]['domains'], ['local_tax', 'tax'])

    def test_outage_and_unknown_identity_are_reported_and_repeat_is_quiet(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); self.site(root)
            before = (root/'manifest.json').read_bytes()
            def inventories(request, provider, *args):
                if provider == 'ordin': raise RuntimeError('URL WITH PRIVATE KEY')
                return [self.current()] if provider == 'eflaw' else []
            with patch('core.edition_watch.inventory', inventories):
                one = check(root, lambda *_: b'', root/'reports', as_of='20261013', progress=lambda _: None)
                two = check(root, lambda *_: b'', root/'reports', as_of='20261013', progress=lambda _: None)
            self.assertEqual(one['counts'], {'unchanged': 1, 'provider-failed': 1})
            self.assertTrue(one['notification_needed']); self.assertFalse(two['notification_needed'])
            self.assertNotIn('PRIVATE', json.dumps(one))
            self.assertEqual(before, (root/'manifest.json').read_bytes())

    def test_existing_lock_is_not_removed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); path = root/'check.lock'; path.write_text('other-run')
            with self.assertRaises(FileExistsError):
                with lock(root): pass
            self.assertEqual(path.read_text(), 'other-run')

    def test_initial_failure_is_sanitized_quiet_on_repeat_and_alerts_after_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch('scripts.check_all_editions.urlopen', side_effect=OSError('PRIVATE KEY URL')):
                first = run(output=root)
                repeated = run(output=root)
                self.assertTrue(first['notification_needed'])
                self.assertFalse(repeated['notification_needed'])
                self.assertNotIn('PRIVATE', json.dumps(repeated))
                (root/'latest.json').write_text(json.dumps({'checked_at': '9999-01-01'}))
                self.assertTrue(run(output=root)['notification_needed'])
            self.assertFalse((root/'check.lock').exists())


if __name__ == '__main__': unittest.main()
