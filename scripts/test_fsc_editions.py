"""No-network regressions for the 2026-11-09 future-edition displacement."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from core.fsc_collection import CollectionError, collect_body, collect_sources, list_record
from core.fsc_editions import effective_records, resolve_inventory
from core.galaxy_updates import current_signature, inventory_signature
from scripts.test_fsc_collection import row, page, admin_body
from scripts.verify_fsc_snapshot import verify_inventory_editions

AS_OF = '20261109'


def edition(serial='2100000287734', effective='20261113', published='20261103',
            identity='36044', name='증권의 발행 및 공시 등에 관한 규정',
            amendment='일부개정', target='admrul', authority='금융위원회'):
    result = row(target, identity, serial, effective, authority)
    result.find('발령일자' if target == 'admrul' else '공포일자').text = published
    result.find('행정규칙명' if target == 'admrul' else '법령명한글').text = name
    ET.SubElement(result, '제개정구분명').text = amendment
    return result


def previous(**changes):
    return edition(**dict(serial='2100000283270', effective='20260728',
                          published='20260728', **changes))


def inventory(*rows, as_of=AS_OF, target='admrul'):
    records = [list_record(r, target, as_of) for r in rows]
    return dict(as_of=as_of, layers={target: dict(provider=target, list_status='complete',
                expected=len(records), received=len(records), records=records)})


def response(rows, target='admrul'):
    def request(endpoint, params):
        assert endpoint == 'lawSearch.do'
        start = (params['page'] - 1) * params['display']
        return page(rows[start:start + params['display']], total=len(rows),
                    number=params['page'], target=target)
    return request


class EffectiveEditionTests(unittest.TestCase):
    def resolve(self, rows=None, scheduled=None, **options):
        return resolve_inventory(response([previous()] if rows is None else rows),
                                 inventory(edition() if scheduled is None else scheduled), **options)

    def test_real_displaced_edition_signature_and_body_are_current(self):
        result = self.resolve()
        listed = result['layers']['admrul']['records'][0]
        selected = list(effective_records(result['layers']['admrul'], as_of=AS_OF))[0]
        self.assertEqual(listed['version_id'], '2100000287734')
        self.assertEqual(selected['version_id'], '2100000283270')
        self.assertEqual(result['layers']['admrul']['received'], 1)
        self.assertEqual(listed['edition_resolution']['history']['received'], 1)
        self.assertEqual(len(listed['edition_resolution']['history']['page_sha256'][0]), 64)
        calls = []
        def request(endpoint, params):
            calls.append((endpoint, params))
            return ET.tostring(admin_body(selected), encoding='utf-8')
        collected = collect_body(request, selected, as_of=AS_OF)
        self.assertEqual(calls, [('lawService.do', {'target':'admrul', 'ID':'2100000283270'})])
        self.assertEqual(inventory_signature('fsc', result),
                         current_signature({'laws': [], 'administrative_rules':[collected]}))
        self.assertEqual(collected['state'], 'current-body-verified')

    def test_postdate_uses_announced_edition_without_history_request(self):
        result = resolve_inventory(lambda *_: self.fail('history not needed'),
                                   inventory(edition(), as_of='20261113'))
        self.assertEqual(inventory_signature('fsc', result),
                         [('admrul:36044', 'admrul:36044:2100000287734:20261113')])

    def test_renamed_same_id_uses_its_historical_title(self):
        result = self.resolve([previous(name='이전 제목')], edition(name='개정 제목'))
        selected = result['layers']['admrul']['records'][0]['effective_record']
        self.assertEqual(selected['name'], '이전 제목')
        self.assertEqual(selected['uid'], 'admrul:36044')
        self.assertEqual(selected['source_url'].split('=')[-1], '2100000283270')

    def test_issuer_history_is_title_independent_and_shared_across_documents(self):
        calls = []
        history = [previous(), previous(identity='36045')]
        def request(endpoint, params):
            calls.append(params)
            return response(history)(endpoint, params)
        result = resolve_inventory(request, inventory(edition(), edition(identity='36045')))
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['org'], '1160100')
        self.assertEqual(calls[0]['nw'], 2)
        self.assertNotIn('query', calls[0])
        self.assertEqual(len(inventory_signature('fsc', result)), 2)

    def test_unrelated_identity_cannot_supply_a_predecessor(self):
        with self.assertRaisesRegex(CollectionError, 'history-unavailable'):
            self.resolve([previous(identity='999')])

    def test_absent_history_for_amendment_fails_closed(self):
        with self.assertRaisesRegex(CollectionError, 'history-unavailable'):
            self.resolve([])

    def test_verified_future_new_enactment_remains_scheduled_only(self):
        result = self.resolve([], edition(amendment='제정'))
        self.assertEqual(inventory_signature('fsc', result), [])
        listed = result['layers']['admrul']['records'][0]
        self.assertEqual(listed['edition_resolution']['status'], 'new-enactment-not-yet-effective')
        self.assertNotIn('effective_record', listed)

    def test_historical_future_enactment_supports_later_future_amendment(self):
        result = self.resolve([edition(serial='123', effective='20261111', amendment='제정')])
        self.assertEqual(inventory_signature('fsc', result), [])

    def test_future_non_enactment_does_not_prove_absent_current(self):
        with self.assertRaisesRegex(CollectionError, 'history-unavailable'):
            self.resolve([edition(serial='123', effective='20261111')])

    def test_later_effective_then_later_published_ordering(self):
        older = edition(serial='1', effective='20260727', published='20260801')
        same_date_older_publication = edition(serial='2', effective='20260728', published='20260727')
        result = self.resolve([older, same_date_older_publication, previous()])
        self.assertEqual(result['layers']['admrul']['records'][0]['effective_record']['version_id'], '2100000283270')

    def test_tied_dates_are_ambiguous_not_resolved_by_arbitrary_serial(self):
        with self.assertRaisesRegex(CollectionError, 'duplicate-history'):
            self.resolve([previous(), previous(identity='36044', name='다른 명칭')])

    def test_distinct_serial_same_dates_fails_ambiguous(self):
        other = previous(); other.find('행정규칙일련번호').text = '999'
        with self.assertRaisesRegex(CollectionError, 'ambiguous'):
            self.resolve([previous(), other])

    def test_repealed_latest_history_not_resurrected(self):
        with self.assertRaisesRegex(CollectionError, 'repealed'):
            self.resolve([previous(amendment='폐지')])

    def test_pagination_provenance_and_failure_modes(self):
        result = self.resolve([previous(), previous(identity='999')], display=1)
        history = result['layers']['admrul']['records'][0]['edition_resolution']['history']
        self.assertEqual((history['pages'], history['expected'], len(history['page_sha256'])), (2, 2, 2))
        with self.assertRaisesRegex(CollectionError, 'page-limit'):
            self.resolve([previous(), previous(identity='999')], display=1, max_pages=1)
        for raw, error in ((page([], total=1, target='admrul'), 'short-or-oversized'),
                           (b'<error/>', 'unexpected-history'),
                           (page([previous()], total=1, number=2, target='admrul'), 'pagination')):
            with self.subTest(error=error), self.assertRaisesRegex(CollectionError, error):
                resolve_inventory(lambda *_: raw, inventory(edition()))

    def test_wrong_authority_and_future_publication_fail(self):
        for old in (previous(authority='법무부'), edition(effective='20261101', published='20261110')):
            with self.subTest(), self.assertRaises(CollectionError):
                self.resolve([old])

    def test_eflaw_uses_documented_history_flag_and_stable_id(self):
        calls = []
        def request(endpoint, params):
            calls.append(params)
            return response([previous(target='eflaw')], 'eflaw')(endpoint, params)
        result = resolve_inventory(request, inventory(edition(target='eflaw'), target='eflaw'))
        self.assertEqual((calls[0]['nw'], calls[0]['LID']), (1, '36044'))
        self.assertEqual(inventory_signature('fsc', result)[0][0], 'eflaw:36044')

    def test_malformed_resolved_record_cannot_bypass_collection_checks(self):
        for field, value in (('uid', 'admrul:999'), ('effective', '20261113'),
                             ('document_id', '999'), ('version_id', '999')):
            result = self.resolve()
            result['layers']['admrul']['records'][0]['effective_record'][field] = value
            with self.subTest(field=field), self.assertRaises(CollectionError):
                inventory_signature('fsc', result)

    def test_collector_and_snapshot_audit_keep_scheduled_and_current_same_uid(self):
        result = self.resolve()
        statute = list_record(row(), 'eflaw', AS_OF)
        result['layers']['eflaw'] = dict(provider='eflaw', list_status='complete',
                                       received=1, expected=1, records=[statute])
        def collector(request, record, **kwargs):
            return {**record, 'body_status':'indexed-statute-text', 'fetched_at':AS_OF}
        with patch('core.fsc_collection.collect_body', side_effect=collector) as fetch:
            source = collect_sources(lambda *_: self.fail('resolved history reused'), result)
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(len(source['scheduled']), 1)
        self.assertEqual(source['administrative_rules'][0]['version_id'], '2100000283270')
        verify_inventory_editions(source)
        source['administrative_rules'].clear()
        with self.assertRaises(AssertionError):
            verify_inventory_editions(source)

    def test_future_body_is_never_requested_and_old_body_failure_is_not_reused(self):
        result = self.resolve()
        selected = result['layers']['admrul']['records'][0]['effective_record']
        with self.assertRaises(CollectionError):
            collect_body(lambda *_: b'<error/>', selected, as_of=AS_OF)
        with self.assertRaisesRegex(CollectionError, 'not-effective'):
            collect_body(lambda *_: self.fail('future body requested'),
                         result['layers']['admrul']['records'][0], as_of=AS_OF)


if __name__ == '__main__':
    unittest.main()
