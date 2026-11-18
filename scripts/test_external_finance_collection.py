"""Offline safeguards for current/scheduled bodies and KIC/export separation."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from xml.etree.ElementTree import Element, SubElement, tostring

from core.export_finance_profile import (
    EXIM, KIC, INSURANCE, EDCF, EXPORT_FAMILIES, REQUIRED_ALL,
    document_tags, family, selected,
)
from core.fsc_collection import CollectionError
from scripts.collect_external_finance import ROOT, discover, run, subset

STAMP = '20261118'


def response(params, *, omit=None, wrong_future=False):
    query = params['query']
    scheduled = params['nw'] == 2
    names = ([EXIM] if query == EXIM else []) if scheduled else [
        name for name in REQUIRED_ALL if family(name) == query and name != omit]
    root = Element('LawSearch')
    SubElement(root, 'totalCnt').text = str(len(names))
    SubElement(root, 'page').text = '1'
    for name in names:
        node = SubElement(root, 'law')
        ident = str(100 + REQUIRED_ALL.index(name))
        values = {
            '법령명한글': name, '법령ID': ident,
            '법령일련번호': ident + ('99' if scheduled else '88'),
            '시행일자': '20261130' if scheduled and not wrong_future else '20260102',
            '공포일자': '20251001',
            '소관부처명': '산업통상부' if family(name) == INSURANCE else '재정경제부',
            '법령구분명': '대통령령' if name.endswith('시행령') else '부령' if name.endswith('시행규칙') else '법률',
        }
        for key, value in values.items():
            SubElement(node, key).text = value
    return tostring(root, encoding='utf-8')


class ExternalFinanceCollectionTests(unittest.TestCase):
    def test_each_family_queries_current_and_scheduled_separately(self):
        calls = []
        def request(endpoint, params):
            calls.append((endpoint, params.copy()))
            return response(params)
        inventory = discover(request, STAMP)
        current = [r for r in inventory['records'] if r['state'] == 'current-candidate']
        future = [r for r in inventory['records'] if r['state'] == 'scheduled']
        self.assertEqual(len(current), 10)
        self.assertEqual(len(future), 1)
        self.assertEqual(future[0]['effective'], '20261130')
        self.assertEqual(next(r for r in current if r['name'] == EXIM)['effective'], '20260102')
        self.assertEqual(len(calls), 8)
        self.assertEqual({p['nw'] for _, p in calls}, {2, 3})

    def test_missing_subordinate_or_wrong_future_state_fails(self):
        with self.assertRaises(CollectionError):
            discover(lambda endpoint, params: response(params, omit=EDCF + ' 시행규칙'), STAMP)
        with self.assertRaises(CollectionError):
            discover(lambda endpoint, params: response(params, wrong_future=True), STAMP)

    def test_kic_is_not_promoted_to_export_support(self):
        inventory = discover(lambda endpoint, params: response(params), STAMP)
        source = dict(laws=deepcopy(inventory['records']), scheduled=deepcopy(inventory['records']),
                      inventory=deepcopy(inventory), administrative_rules=[], domain='export_finance')
        export = subset(source, EXPORT_FAMILIES)
        kic = subset(source, (KIC,))
        self.assertTrue(all(family(d['name']) != KIC for d in export['laws']))
        self.assertEqual({d['name'] for d in kic['laws']}, {KIC, KIC + ' 시행령'})
        self.assertEqual(document_tags(KIC), [])
        self.assertEqual(len(source['inventory']['records']), 11)

    def test_scope_rejects_unrelated_laws_and_wrong_authorities(self):
        self.assertTrue(selected(INSURANCE, '산업통상부', 'eflaw'))
        self.assertFalse(selected(INSURANCE, '재정경제부', 'eflaw'))
        self.assertFalse(selected(EXIM, '산업통상부', 'eflaw'))
        self.assertFalse(selected('한국수출입은행법 관련 지침', '재정경제부', 'eflaw'))
        self.assertFalse(selected(KIC, '재정경제부', 'admrul'))

    def test_destination_cannot_touch_active_corpus_or_outside_output(self):
        for destination in (ROOT / 'output' / 'export_finance-universe', ROOT / 'web', ROOT / 'output'):
            with self.assertRaises(ValueError):
                run('inventory', destination, STAMP)


if __name__ == '__main__':
    unittest.main()
