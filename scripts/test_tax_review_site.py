"""Publication boundaries for historical texts and the immutable tax corpus."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.build_static_galaxies import Writer
from scripts.build_tax_review_site import check_current_texts
from scripts.delegation_baseline import attach_official_history, body_digest


class TaxPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.writer = Writer(self.root)
        self.catalog = dict(laws=[], delegation_review=dict(baselines={}))
        self.source = dict(laws=[])
        self.manifest = dict(schema=1, kind='tax-delegation-history', public_manifest_sha256='expected', laws=[])
        for i, name in enumerate(('법인세법', '소득세법', '조세특례제한법')):
            meta = dict(id=str(i), domain='tax', name=name, effective='20260701')
            article = dict(jo='1', title='위임', text='제1조(위임) 대통령령으로 정한다.')
            entry = dict(meta, parts=[], file=self.writer.data(dict(meta=meta, articles=[article])))
            self.catalog['laws'].append(entry)
            self.source['laws'].append(dict(meta, articles=[article]))
            baseline = dict(schema=1, kind='delegation-baseline', meta=dict(meta, effective='20260101'),
                            built_at='2026-09-29', articles=[dict(article, text='제1조(위임) 법률로 정한다.')],
                            details={}, evidence_availability=dict(reverse_citations='not-collected'))
            self.save_baseline(i, baseline)
        self.save_manifest()

    def save_baseline(self, i, baseline):
        raw = json.dumps(baseline, ensure_ascii=False).encode()
        ref = dict(path=f'old-{i}.json', bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        (self.root / ref['path']).write_bytes(raw)
        record = dict(id=str(i), name=baseline['meta']['name'],
                      current=dict(effective='20260701', text_sha256=body_digest(self.source['laws'][i]['articles'])),
                      previous=dict(effective=baseline['meta']['effective'], text_sha256=body_digest(baseline['articles'])), baseline=ref)
        if i < len(self.manifest['laws']):self.manifest['laws'][i] = record
        else:self.manifest['laws'].append(record)

    def save_manifest(self):
        (self.root / 'manifest.json').write_text(json.dumps(self.manifest), encoding='utf-8')

    def test_all_three_previous_bodies_are_attached_with_unavailable_old_citations(self):
        report = attach_official_history(self.writer, self.catalog, self.root, 'expected')
        self.assertEqual(len(report), 3)
        self.assertTrue(all(r['reverse_citations'] == 'not-collected' for r in report))
        self.assertTrue(all(r['mode'] == 'previous-version' for r in self.catalog['delegation_review']['baselines'].values()))

    def test_foreign_snapshot_and_future_baseline_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'different public snapshot'):
            attach_official_history(self.writer, self.catalog, self.root, 'wrong')
        baseline = json.loads((self.root / 'old-0.json').read_bytes())
        baseline['meta']['effective'] = '20270101'
        self.save_baseline(0, baseline);self.save_manifest()
        with self.assertRaisesRegex(ValueError, 'temporal order'):
            attach_official_history(self.writer, self.catalog, self.root, 'expected')

    def test_made_up_historical_reverse_data_is_rejected(self):
        baseline = json.loads((self.root / 'old-0.json').read_bytes())
        baseline['details'] = {'1': {'rows': []}}
        self.save_baseline(0, baseline);self.save_manifest()
        with self.assertRaisesRegex(ValueError, 'uncollected'):
            attach_official_history(self.writer, self.catalog, self.root, 'expected')

    def test_corrupt_history_or_changed_current_text_is_rejected(self):
        (self.root / 'old-0.json').write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            attach_official_history(self.writer, self.catalog, self.root, 'expected')
        check_current_texts(self.root, self.catalog, self.source)
        modified = deepcopy(self.source)
        modified['laws'][0]['articles'][0]['text'] += ' 변경'
        with self.assertRaisesRegex(ValueError, 'edition changed'):
            check_current_texts(self.root, self.catalog, modified)

    def test_an_omitted_current_law_fails_instead_of_silently_shrinking_scope(self):
        with self.assertRaisesRegex(ValueError, 'scope changed'):
            check_current_texts(self.root, self.catalog, dict(laws=self.source['laws'][:-1]))

    def test_per_article_edition_or_deleted_state_cannot_change_silently(self):
        for field, value in (('effective', '20270101'), ('deleted', True)):
            changed = deepcopy(self.source)
            changed['laws'][0]['articles'][0][field] = value
            with self.assertRaisesRegex(ValueError, 'edition changed'):
                check_current_texts(self.root, self.catalog, changed)


if __name__ == '__main__':
    unittest.main()
