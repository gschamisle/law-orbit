"""Regression checks for canonical reverse IDs and expanded forward endpoints."""
from copy import deepcopy
import unittest

from scripts.verify_edition_refresh_release import (
    citation_endpoint, iter_bridge_rows, missing_reverse_evidence,
)


def citation_pair():
    raw_scope = dict(scopes=[
        [['7-14의2','','',''], ['7-14의2','','',''], None],
        [['7-18','1','4',''], ['7-18','1','4',''], None],
        [['7-18','1','5',''], ['7-18','1','5',''], None],
    ], review_reason='')
    reverse = dict(evidence_id='canonical-self-reference', direction='reverse',
        source_id='forex-rule', source_jo='7-14의2', source_start=990, source_end=1018,
        source_effective='20261102', target_id='forex-rule', target_kind='article',
        target_ref='제7-18조', target_ref_recorded='제7-14조의2',
        cite_raw='제7-14조의2, 제7-18조제1항제4호 및 제5호', raw_scope=raw_scope,
        source_scope=dict(scopes=[[
            ['7-14의2','4','',''], ['7-14의2','4','',''], None]], review_reason=''))
    forward = {**deepcopy(reverse), 'evidence_id':'expanded-4', 'direction':'forward',
               'target_ref':'제7-18조제1항제4호', 'target_ref_recorded':'제7-18조제1항제4호'}
    return forward, reverse


class EditionVerifierTests(unittest.TestCase):
    def test_canonical_self_reference_id_can_match_expanded_actual_endpoint(self):
        forward, reverse = citation_pair()
        self.assertEqual(citation_endpoint(forward), citation_endpoint(reverse))
        self.assertEqual(missing_reverse_evidence([forward], [reverse]), [])

    def test_different_destination_edition_quote_or_coordinates_cannot_match(self):
        mutations = dict(target_ref='제7-19조제1항제4호', target_id='different-law',
                         source_effective='20261001', source_id='different-source',
                         source_jo='7-15', source_start=991, source_end=1019,
                         cite_raw='제7-18조를 준용한다.')
        for key, value in mutations.items():
            forward, reverse = citation_pair()
            forward[key] = value
            with self.subTest(key=key):
                self.assertEqual(missing_reverse_evidence([forward], [reverse]), [reverse])

    def test_complete_raw_scope_and_source_scope_must_match(self):
        for field in ('raw_scope', 'source_scope'):
            forward, reverse = citation_pair()
            forward[field]['scopes'][0][0][1] = '9'
            with self.subTest(field=field):
                self.assertEqual(missing_reverse_evidence([forward], [reverse]), [reverse])
        forward, reverse = citation_pair()
        forward['raw_scope']['scopes'].pop()
        self.assertEqual(missing_reverse_evidence([forward], [reverse]), [reverse])

    def test_missing_scope_cannot_gain_endpoint_exception(self):
        for field in ('raw_scope', 'source_scope'):
            forward, reverse = citation_pair()
            forward.pop(field); reverse.pop(field)
            with self.subTest(field=field):
                self.assertEqual(missing_reverse_evidence([forward], [reverse]), [reverse])

    def test_direct_id_matching_still_works_without_range_metadata(self):
        forward = dict(evidence_id='same')
        reverse = dict(evidence_id='same')
        self.assertEqual(missing_reverse_evidence([forward], [reverse]), [])
        self.assertEqual(missing_reverse_evidence([], [reverse]), [reverse])

    def test_unknown_or_missing_ids_never_match_each_other(self):
        self.assertEqual(missing_reverse_evidence([{}], [{}]), [{}])

    def test_article_and_broad_bridge_rows_are_both_visited_once(self):
        class Storage:
            values = dict(root={'bridges':[{'url':'pair'}, {'url':'pair'}]},
                          pair={'laws':{'law1':{'1':{'rows':[{'evidence_id':'article'}]}}},
                                'broad':{'law1':[{'evidence_id':'law-wide'}]}})
            def read(self, ref):
                return self.values[ref['url']]
        result = list(iter_bridge_rows(Storage(), {'url':'root'}, set()))
        self.assertEqual([(row['evidence_id'], location) for row, location in result],
                         [('article','bridge/law1/1'), ('law-wide','bridge/law1/broad')])


if __name__ == '__main__':
    unittest.main()
