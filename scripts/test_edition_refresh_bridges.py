"""Offline tests for edition-bound bridge replacement and preservation."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from core.citation_scope import Provision
from core.forex_finance_links import bridge
from scripts.build_forex_finance_site import payloads
from scripts.build_static_galaxies import Writer, ident
from scripts.edition_refresh_bridges import rebuild_bridges
from scripts.static_storage import Storage
from scripts.test_forex_finance_links import fixture


def save_manifest(root, manifest):
    (root / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')


def write_domain(writer, domain, snap):
    snap = deepcopy(snap)
    for entry in snap['entries']:
        packed = deepcopy(snap['documents'][entry['id']])
        packed['details'] = snap['details'][entry['id']]
        packed['meta'] = deepcopy(entry)
        entry['file'] = writer.data(packed)
        snap['documents'][entry['id']] = packed
    ref = writer.data(dict(laws=snap['entries'], built_at=snap['built_at']))
    return dict(id=domain, catalog=ref, built_at=snap['built_at']), snap


def write_site(root, snaps, pairs):
    writer = Writer(root)
    manifest = dict(domains=[], cross_domain={})
    saved = {}
    for domain, snap in snaps.items():
        meta, saved[domain] = write_domain(writer, domain, snap)
        manifest['domains'].append(meta)
    refs = {}
    for pair in pairs:
        selected = {d: saved[d] for d in pair}
        values = payloads(bridge(selected, pair=pair), selected)
        for domain in pair:
            refs.setdefault(domain, []).append(writer.data(values[domain]))
    for domain, values in refs.items():
        manifest['cross_domain'][domain] = (values[0] if len(values) == 1 else writer.data(
            dict(kind='domain-bridge-set', schema=1, domain=domain,
                 bridges=values, preserved_note='published wrapper metadata')))
    save_manifest(root, manifest)
    return manifest, saved


def one_document(domain, name, text):
    entry = dict(id=ident(domain, '', name), name=name, label=name, domain=domain,
                 effective='20260901', url='https://www.law.go.kr/', articles=1,
                 sectors=[], parts=[], file={})
    article = dict(jo='1', label=Provision('1').label, title='예시', text=text,
                   effective=entry['effective'])
    return dict(entries=[entry], documents={entry['id']: dict(meta=deepcopy(entry), articles=[article])},
                details={entry['id']: {'1': dict(rows=[], external=[], issues=[])}}, built_at='20260921')


class EditionRefreshBridgeTests(unittest.TestCase):
    def test_new_text_rebuilds_forward_reverse_and_reader_dates_with_base_fallback(self):
        snaps, fx, fin = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            base, stage = Path(tmp) / 'base', Path(tmp) / 'stage'
            base.mkdir(); stage.mkdir()
            original, saved = write_site(base, snaps, [('forex', 'fsc')])
            original_bytes = {p: p.read_bytes() for p in base.rglob('*') if p.is_file()}
            current = deepcopy(saved['forex'])
            current['built_at'] = '20261026'
            for entry in current['entries']:
                entry['effective'] = '20261026'
                for article in current['documents'][entry['id']]['articles']:
                    article['effective'] = '20261026'
                    if article['jo'] == '7-36':
                        article['text'] = article['text'].replace('제5-1조제6호', '제2조제6호')
                        for issue in current['details'][entry['id']]['7-36']['issues']:
                            issue['raw'] = issue['raw'].replace('제5-1조제6호', '제2조제6호')
            writer = Writer(stage)
            changed, _ = write_domain(writer, 'forex', current)
            manifest = deepcopy(original)
            manifest['domains'][0] = changed
            report = rebuild_bridges(base, stage, manifest, {'forex'}, writer)
            storage = Storage(stage, {})
            forward = storage.read(manifest['cross_domain']['forex'])
            reverse = storage.read(manifest['cross_domain']['fsc'])
            rows = forward['laws'][fx['id']]['7-36']['rows']
            self.assertEqual({r['neighbor_jo'] for r in rows}, {'2'})
            reverse_rows = reverse['laws'][fin['id']]['2']['rows']
            self.assertTrue(any(r['neighbor_jo'] == '7-36' for r in reverse_rows))
            self.assertFalse(any(r['neighbor_jo'] == '7-36'
                                 for r in reverse['laws'][fin['id']].get('5-1', {}).get('rows', [])))
            self.assertEqual(reverse['editions']['forex'], '20261026')
            self.assertEqual(reverse['entries'][0]['effective'], '20261026')
            self.assertEqual(len(report['refreshed_pairs']), 1)
            self.assertTrue(all(p.read_bytes() == raw for p, raw in original_bytes.items()))

    def test_changed_catalog_is_inferred_even_when_changed_set_omits_domain(self):
        snaps, _, _ = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            base, stage = Path(tmp) / 'base', Path(tmp) / 'stage'
            base.mkdir(); stage.mkdir()
            original, saved = write_site(base, snaps, [('forex', 'fsc')])
            current = deepcopy(saved['fsc']); current['built_at'] = '20261026'
            writer = Writer(stage)
            changed, _ = write_domain(writer, 'fsc', current)
            manifest = deepcopy(original); manifest['domains'][1] = changed
            report = rebuild_bridges(base, stage, manifest, set(), writer)
            self.assertEqual(report['inferred_changed_domains'], ['fsc'])
            self.assertEqual(len(report['refreshed_pairs']), 1)

    def test_no_changes_preserves_all_references_without_writing_data(self):
        snaps, _, _ = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            base, stage = Path(tmp) / 'base', Path(tmp) / 'stage'
            base.mkdir(); stage.mkdir()
            original, _ = write_site(base, snaps, [('forex', 'fsc')])
            manifest = deepcopy(original); writer = Writer(stage)
            report = rebuild_bridges(base, stage, manifest, set(), writer)
            self.assertEqual(manifest, original)
            self.assertEqual(writer.assets, {})
            self.assertEqual(report['preserved_pairs'], [['forex', 'fsc']])

    def test_packed_base_supplies_original_pair_and_unchanged_reader_data(self):
        from scripts.compact_static_galaxies import convert
        snaps, _, _ = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            unpacked, base, stage = (Path(tmp) / name for name in ('unpacked', 'base', 'stage'))
            unpacked.mkdir(); stage.mkdir()
            original, _ = write_site(unpacked, snaps, [('forex', 'fsc')])
            convert(unpacked, base, validate_site=False)
            manifest = deepcopy(original)
            report = rebuild_bridges(base, stage, manifest, {'forex'}, Writer(stage))
            self.assertEqual(report['original_pair_count'], 1)
            self.assertEqual(len(report['refreshed_pairs']), 1)
            values = [Storage(stage, {}).read(ref) for ref in manifest['cross_domain'].values()]
            self.assertEqual({value['peer'] for value in values}, {'forex', 'fsc'})

    def test_group_replaces_only_affected_pairs_and_preserves_wrapper_metadata(self):
        snaps = {
            'procurement': one_document('procurement', '국가계약법', '제1조(예시) 「공공기관법」 제1조에 따른다.'),
            'public_institutions': one_document('public_institutions', '공공기관법', '제1조(예시) 내용'),
            'integrity': one_document('integrity', '청렴법', '제1조(예시) 「국가계약법」 제1조에 따른다.'),
            'subsidy': one_document('subsidy', '보조금법', '제1조(예시) 내용'),
        }
        pairs = [('procurement', 'public_institutions'), ('integrity', 'procurement'), ('integrity', 'subsidy')]
        with tempfile.TemporaryDirectory() as tmp:
            base, stage = Path(tmp) / 'base', Path(tmp) / 'stage'
            base.mkdir(); stage.mkdir()
            original, saved = write_site(base, snaps, pairs)
            old_storage = Storage(base)
            prior_group = old_storage.read(original['cross_domain']['integrity'])
            current = deepcopy(saved['procurement']); current['built_at'] = '20261026'
            writer = Writer(stage)
            changed, _ = write_domain(writer, 'procurement', current)
            manifest = deepcopy(original); manifest['domains'][0] = changed
            report = rebuild_bridges(base, stage, manifest, {'procurement'}, writer)
            group = Storage(stage, {}).read(manifest['cross_domain']['integrity'])
            self.assertEqual(group['preserved_note'], prior_group['preserved_note'])
            self.assertNotEqual(group['bridges'][0], prior_group['bridges'][0])
            self.assertEqual(group['bridges'][1], prior_group['bridges'][1])
            self.assertEqual(manifest['cross_domain']['subsidy'], original['cross_domain']['subsidy'])
            self.assertEqual(report['preserved_pairs'], [['integrity', 'subsidy']])
            self.assertEqual(len(report['refreshed_pairs']), 2)

    def test_corrupt_stage_asset_never_falls_back_to_good_base(self):
        snaps, _, _ = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            base, stage = Path(tmp) / 'base', Path(tmp) / 'stage'
            base.mkdir(); stage.mkdir()
            original, _ = write_site(base, snaps, [('forex', 'fsc')])
            ref = original['domains'][0]['catalog']
            path = stage / ref['url']; path.parent.mkdir(); path.write_bytes(b'bad')
            manifest = deepcopy(original)
            with self.assertRaisesRegex(ValueError, 'checksum'):
                rebuild_bridges(base, stage, manifest, {'forex'}, Writer(stage))
            self.assertEqual(manifest, original)

    def test_one_sided_pair_and_wrong_kind_fail_without_manifest_mutation(self):
        snaps, _, _ = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            base, stage = Path(tmp) / 'base', Path(tmp) / 'stage'
            base.mkdir(); stage.mkdir()
            original, _ = write_site(base, snaps, [('forex', 'fsc')])
            one_side = deepcopy(original); del one_side['cross_domain']['fsc']
            save_manifest(base, one_side)
            manifest = deepcopy(one_side)
            with self.assertRaisesRegex(ValueError, 'Incomplete'):
                rebuild_bridges(base, stage, manifest, {'forex'}, Writer(stage))
            self.assertEqual(manifest, one_side)
            broken = Storage(base).read(original['cross_domain']['forex'])
            broken['kind'] = 'unpublished-new-kind'
            original['cross_domain']['forex'] = Writer(base).data(broken)
            save_manifest(base, original); manifest = deepcopy(original)
            with self.assertRaisesRegex(ValueError, 'Unrecognized'):
                rebuild_bridges(base, stage, manifest, {'forex'}, Writer(stage))
            self.assertEqual(manifest, original)


if __name__ == '__main__':
    unittest.main()
