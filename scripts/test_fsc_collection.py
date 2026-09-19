"""Credential-free tests of FSC collection contracts; XML responses are synthetic."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
from core.fsc_collection import (
    CollectionError, LawTransport, atomic_json, body_params, check_body,
    collect_body, collect_sources, discover, list_record, xml_root, ymd,
)
from core.fsc_graph import bootstrap_sources, build_fsc_graph, merge_external

AS_OF = '20260916'


def row(target='eflaw', identity='001', serial='123', effective='20260101', authority='금융위원회'):
    tags = (dict(법령명한글='검증법', 법령ID=identity, 법령일련번호=serial,
                 법령구분명='법률', 공포일자='20251201') if target == 'eflaw' else
            dict(행정규칙명='검증감독규정', 행정규칙ID=identity, 행정규칙일련번호=serial,
                 행정규칙종류='고시', 발령일자='20251201'))
    tags.update(시행일자=effective, 소관부처명=authority)
    element = ET.Element('law' if target == 'eflaw' else 'admrul')
    for key, value in tags.items():
        ET.SubElement(element, key).text = value
    return element


def page(rows, total=None, number=1, target='eflaw'):
    root = ET.Element('LawSearch' if target == 'eflaw' else 'AdmRulSearch')
    ET.SubElement(root, 'totalCnt').text = str(len(rows) if total is None else total)
    ET.SubElement(root, 'page').text = str(number)
    root.extend(rows)
    return ET.tostring(root, encoding='utf-8')


def admin_body(record):
    root = ET.Element('행정규칙')
    for key, value in {
        '행정규칙명': record['name'], '행정규칙ID': record['document_id'],
        '행정규칙일련번호': record['version_id'], '시행일자': record['effective'],
        '소관부처명': '금융위원회', '조문내용': '제1-2조(검증) 법 제2조를 준용한다.',
    }.items():
        ET.SubElement(root, key).text = value
    return root


class DiscoveryTests(unittest.TestCase):
    def test_provider_specific_current_flags_and_org(self):
        calls = []
        for target, flag in (('eflaw', 3), ('admrul', 1)):
            def request(endpoint, params):
                calls.append((endpoint, params))
                return page([row(target)], target=target)
            result = discover(request, target, as_of=AS_OF)
            self.assertEqual(calls[-1][1]['nw'], flag)
            self.assertEqual(calls[-1][1]['org'], '1160100')
            self.assertNotIn('OC', calls[-1][1])
            self.assertEqual(result['received'], result['expected'])
            self.assertEqual(result['records'][0]['document_id'], '001')

    def test_all_pages_not_a_seed_list(self):
        def request(_, params):
            i = params['page']
            return page([row(identity=str(i), serial=str(100 + i))], total=3, number=i)
        result = discover(request, 'eflaw', as_of=AS_OF, display=1)
        self.assertEqual(result['pages'], 3)
        self.assertEqual(len(result['records']), 3)

    def test_short_page_is_not_no_more_laws(self):
        with self.assertRaisesRegex(CollectionError, 'short-or-oversized-page'):
            discover(lambda *_: page([], total=3), 'eflaw', as_of=AS_OF)

    def test_page_limit_is_an_error(self):
        with self.assertRaisesRegex(CollectionError, 'page-limit'):
            discover(lambda *_: page([row()], total=2), 'eflaw', as_of=AS_OF, display=1, max_pages=1)

    def test_repeated_page_number_is_rejected(self):
        with self.assertRaisesRegex(CollectionError, 'invalid-list-pagination'):
            discover(lambda *_: page([row()], total=2), 'eflaw', as_of=AS_OF, display=1)

    def test_count_change_is_rejected(self):
        def request(_, p):
            return page([row(identity=str(p['page']))], total=p['page'] + 1, number=p['page'])
        with self.assertRaisesRegex(CollectionError, 'inventory-changed'):
            discover(request, 'eflaw', as_of=AS_OF, display=1)

    def test_duplicate_document_is_rejected(self):
        with self.assertRaisesRegex(CollectionError, 'duplicate-or-repeated'):
            discover(lambda *_: page([row(), row(serial='999')]), 'eflaw', as_of=AS_OF)

    def test_wrong_authority_is_not_relabelled_fsc(self):
        with self.assertRaisesRegex(CollectionError, 'wrong-authority'):
            discover(lambda *_: page([row(authority='금융감독원')]), 'eflaw', as_of=AS_OF)

    def test_affiliated_fiu_rules_keep_their_actual_authority(self):
        record = list_record(row('admrul', authority='금융정보분석원'), 'admrul', AS_OF)
        self.assertEqual(record['managing_authority'], '금융정보분석원')
        with self.assertRaises(CollectionError):
            list_record(row(authority='금융정보분석원'), 'eflaw', AS_OF)

    def test_error_envelope_is_not_empty_success(self):
        with self.assertRaisesRegex(CollectionError, 'unexpected-list-envelope'):
            discover(lambda *_: b'<error>denied</error>', 'eflaw', as_of=AS_OF)

    def test_missing_official_id_is_an_error(self):
        with self.assertRaisesRegex(CollectionError, 'missing-official'):
            list_record(row(identity=''), 'eflaw', AS_OF)

    def test_scheduled_rule_is_retained_separately(self):
        record = list_record(row('admrul', effective='20271001'), 'admrul', AS_OF)
        self.assertEqual(record['state'], 'scheduled')
        with self.assertRaisesRegex(CollectionError, 'not-effective'):
            collect_body(lambda *_: self.fail('must not fetch'), record, as_of=AS_OF)

    def test_invalid_date_and_xml_are_rejected(self):
        for value in ('20260230', '', '20261301'):
            with self.assertRaises(CollectionError):
                ymd(value)
        for value in (b'<broken>', b'<!DOCTYPE x [<!ENTITY a "x">]><x/>', '<x/>'.encode('utf-16')):
            with self.assertRaises(CollectionError):
                xml_root(value)

    def test_empty_inventory_cannot_be_a_full_corpus(self):
        with self.assertRaisesRegex(CollectionError, 'empty-statute'):
            collect_sources(lambda *_: b'', dict(as_of=AS_OF, layers={}))


class BodyAndStorageTests(unittest.TestCase):
    def test_pin_statute_mst_and_effective_date(self):
        record = list_record(row(), 'eflaw', AS_OF)
        self.assertEqual(body_params(record), dict(target='eflaw', MST='123', efYd='20260101'))

    def test_administrative_id_is_serial_not_stable_id(self):
        record = list_record(row('admrul', identity='36056', serial='2100000276094'), 'admrul', AS_OF)
        self.assertEqual(body_params(record), dict(target='admrul', ID='2100000276094'))

    def test_rule_bodies_are_not_silently_sent_to_statute_parser(self):
        record = list_record(row('admrul'), 'admrul', AS_OF)
        body = admin_body(record)
        body.find('조문내용').text += ' https://example.invalid/?OC=PRIVATE_KEY&x=1'
        result = collect_body(lambda *_: ET.tostring(body, encoding='utf-8'), record, as_of=AS_OF)
        self.assertEqual(result['articles'], [])
        self.assertEqual(result['body_status'], 'collected-not-indexed')
        self.assertIn('제1-2조', result['raw_body_blocks'][0])
        self.assertNotIn('PRIVATE_KEY', result['raw_body_blocks'][0])
        self.assertEqual(result['coverage']['relative_aliases'], 'unresolved')

    def test_mismatched_edition_or_identity_is_rejected(self):
        record = list_record(row('admrul'), 'admrul', AS_OF)
        for tag, wrong in (('시행일자', '20250101'), ('행정규칙ID', '999'),
                           ('행정규칙일련번호', '999'), ('소관부처명', '금융감독원')):
            root = admin_body(record)
            root.find(tag).text = wrong
            with self.subTest(tag=tag), self.assertRaises(CollectionError):
                check_body(root, record)

    def test_joint_authority_body_must_belong_to_listed_issuers(self):
        record = list_record(row('admrul', authority='산업통상부,금융위원회'), 'admrul', AS_OF)
        body = admin_body(record)
        body.find('소관부처명').text = '산업통상부'
        check_body(body, record)
        body.find('소관부처명').text = '법무부'
        with self.assertRaisesRegex(CollectionError, 'authority-mismatch'):
            check_body(body, record)

    def test_atomic_serialization_failure_preserves_previous_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bundle.json'
            atomic_json(path, {'complete': True})
            before = path.read_bytes()
            with self.assertRaises(TypeError):
                atomic_json(path, {'not_json': object()})
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(path.parent.glob('*.tmp')), [])

    def test_transport_does_not_leak_credentials_in_errors(self):
        import requests
        with patch('requests.get', side_effect=requests.RequestException('url?OC=PRIVATE_KEY')):
            with self.assertRaises(CollectionError) as result:
                LawTransport('PRIVATE_KEY', attempts=1)('lawSearch.do', {'target': 'eflaw'})
        self.assertNotIn('PRIVATE_KEY', str(result.exception))
        with self.assertRaises(CollectionError):
            LawTransport('')

    def test_transport_disallows_redirect_and_auth_override(self):
        with patch('requests.get', return_value=SimpleNamespace(status_code=302)) as request:
            with self.assertRaises(CollectionError):
                LawTransport('test-key', attempts=1)('lawSearch.do', {'target': 'eflaw'})
            self.assertFalse(request.call_args.kwargs['allow_redirects'])
        with self.assertRaises(CollectionError):
            LawTransport('test-key')('lawSearch.do', {'OC': 'override'})


class ScopeIsolationTests(unittest.TestCase):
    def corpus(self):
        return dict(built_at='2026-09-16', laws=[
            dict(name='은행법', family='은행법', category='external', law_id='1', mst='2', effective='20260101', articles=[], annexes=[]),
            dict(name='소득세법', family='소득세법', category='tax', law_id='3', mst='4', effective='20260101', articles=[], annexes=[]),
        ])

    def test_bootstrap_preserves_input_and_explains_partial_coverage(self):
        source, seeds = self.corpus(), (SimpleNamespace(name='은행법'), SimpleNamespace(name='보험업법'))
        before = deepcopy(source)
        result = bootstrap_sources(source, seeds)
        self.assertEqual(source, before)
        self.assertEqual(result['laws'][0]['category'], 'fsc')
        self.assertEqual(result['laws'][1]['category'], 'tax')
        self.assertEqual(result['coverage']['unmatched_seed_names'], ['보험업법'])

    def test_external_date_conflict_is_not_silently_mixed(self):
        primary, external = self.corpus(), self.corpus()
        external['built_at'] = '2026-09-15'
        with self.assertRaisesRegex(CollectionError, 'snapshot-date'):
            merge_external(primary, external)

    def test_external_edition_conflict_is_rejected(self):
        primary, external = self.corpus(), self.corpus()
        external['laws'][0]['mst'] = '99'
        with self.assertRaisesRegex(CollectionError, 'edition-or-identity'):
            merge_external(primary, external)

    def test_equal_editions_merge_without_mutation(self):
        primary, external = self.corpus(), self.corpus()
        before = deepcopy(primary)
        self.assertEqual(len(merge_external(primary, external)['laws']), 2)
        self.assertEqual(primary, before)

    def test_nonstatute_is_blocked_before_engine_import(self):
        source = self.corpus()
        source['laws'][0].update(category='fsc', provider='admrul')
        with self.assertRaisesRegex(CollectionError, 'nonstatute'):
            build_fsc_graph(source)


if __name__ == '__main__':
    unittest.main()
