"""Pinned tax annex completeness, source integrity and owner-boundary tests."""
from copy import deepcopy
import json
from pathlib import Path
import struct
import tempfile
import unittest

from core.annex_analysis import digest, validate_analysis
from core.tax_annex import (ROOT, SPECS, DEFAULT_OUTPUT, official_download, records,
                            table_units, attach, analyze, merge_graph)
from scripts.collect_tax_annexes import collect, immutable_write


def record(tag, level, payload):
    return struct.pack('<I', tag | level << 10 | len(payload) << 20) + payload


def fixture_table(addresses=((0,0,1,1),(1,0,1,1))):
    payload = bytearray(18)
    struct.pack_into('<HH', payload, 4, 1, 2)
    data = record(77, 2, payload)
    for i, address in enumerate(addresses):
        cell = bytearray(47)
        struct.pack_into('<H', cell, 0, 1)
        struct.pack_into('<HHHH', cell, 8, *address)
        data += record(72,2,cell) + record(66,2,b'')
        data += record(67,3,(('「외부법」' if i == 0 else '제2조')+'\r').encode('utf-16le'))
    return data


def fixture_analysis(texts, kind='cell'):
    text = ''; units = []
    for i, value in enumerate(texts):
        units.append(dict(id=f'u{i}', locator=f'셀 {i+1}', kind=kind,
            raw_text=value, text=value, start=len(text), end=len(text)+len(value)))
        text += value+'\n'
    return dict(schema=1, status='explicit-citations-ready', text=text,
        text_sha256=digest(text.encode()), file_sha256='fixture', units=units)


def citation_fixture(kind='cell'):
    law = dict(name='가상법 시행규칙', effective='20260928', category='tax', provider='eflaw',
        articles=[dict(jo='2', text='제2조(검증) 본문', title='검증')],
        annexes=[dict(ref='별표 1', title='검증용', urls=[],
                     body_analysis=fixture_analysis(['「외부법」','제2조','같은 법 제3조'],kind))])
    return dict(laws=[law])


class TaxAnnexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = ROOT.parent/'FscLawGalaxy-Stage2/output/tax-universe/bundle.json'
        cls.source = json.loads(cls.bundle.read_text(encoding='utf-8'))['source']
        cls.enriched = attach(cls.source)
        cls.specs = json.loads(SPECS.read_text(encoding='utf-8'))

    def test_records_reject_truncation(self):
        for raw in (b'\x00', struct.pack('<I',67 | 15 << 20)+b'a'):
            with self.assertRaises(ValueError): list(records(raw))

    def test_cell_coordinates_and_paragraphs_are_preserved(self):
        units, table = table_units(fixture_table())
        self.assertEqual(table['columns'],2)
        self.assertEqual(units[1]['cell_address'],dict(rowAddr=0,colAddr=1))
        self.assertEqual(units[1]['raw_text'],'제2조')
        self.assertNotIn('외부법',units[1]['raw_text'])

    def test_overlap_missing_and_unsupported_cells_fail(self):
        for addresses in (((0,0,1,1),(0,0,1,1)),((0,0,1,1),),((0,0,3,1),)):
            with self.assertRaises(ValueError): table_units(fixture_table(addresses))
        with self.assertRaises(ValueError): table_units(fixture_table()+record(77,2,bytes(18)))

    def test_bare_article_and_relative_owner_never_cross_unit(self):
        for kind in ('cell','paragraph'):
            result = analyze(citation_fixture(kind))
            self.assertFalse(result['edges'])
            self.assertEqual(len(result['external_references']),1)
            self.assertTrue(any('명시된 인용 법령 없음' in i['reason'] for i in result['issues']))
            self.assertTrue(any('별칭' in i['reason'] for i in result['issues']))

    def test_url_guard_rejects_keyed_and_unofficial_sources(self):
        for url in ('https://www.law.go.kr/LSW/flDownload.do?flSeq=1&OC=secret',
                    'https://example.com/LSW/flDownload.do?flSeq=1',
                    'https://name:password@www.law.go.kr/LSW/flDownload.do?flSeq=1'):
            with self.assertRaises(ValueError): official_download(url)

    def test_attach_is_nonmutating_and_three_selected_only(self):
        before = deepcopy(self.source)
        enriched = attach(self.source)
        self.assertEqual(self.source,before)
        found = [a for d in enriched['laws'] for a in d['annexes'] if a.get('body_analysis')]
        self.assertEqual(len(found),3)
        self.assertEqual(sum(len(a['body_analysis']['units']) for a in found),237)
        for annex in found: validate_analysis(annex['body_analysis'])

    def test_wrong_edition_or_api_text_is_rejected(self):
        for key in ('effective','mst','xml_sha256'):
            changed = deepcopy(self.source)
            next(d for d in changed['laws'] if d['name']=='법인세법 시행규칙')[key] = 'changed'
            with self.assertRaises(ValueError): attach(changed)
        changed = deepcopy(self.source)
        doc = next(d for d in changed['laws'] if d['name']=='법인세법 시행규칙')
        next(a for a in doc['annexes'] if a['ref']=='별표 5')['text'] += '변경'
        with self.assertRaises(ValueError): attach(changed)

    def test_missing_or_tampered_analysis_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            for spec in self.specs['annexes']:
                for file in spec['files'].values():
                    (folder/file['name']).write_bytes((DEFAULT_OUTPUT/file['name']).read_bytes())
                name = spec['id']+'-analysis.json'
                (folder/name).write_bytes((DEFAULT_OUTPUT/name).read_bytes())
            path = folder/'corporate-rule-5-analysis.json'
            path.write_bytes(path.read_bytes()+b' ')
            with self.assertRaises(ValueError): attach(self.source,folder)
            path.unlink()
            with self.assertRaises(FileNotFoundError): attach(self.source,folder)

    def test_notes_and_zero_citation_status_are_not_lost(self):
        doc = next(d for d in self.enriched['laws'] if d['name']=='법인세법 시행규칙')
        five = next(a['body_analysis'] for a in doc['annexes'] if a['ref']=='별표 5')
        six = next(a['body_analysis'] for a in doc['annexes'] if a['ref']=='별표 6')
        self.assertIn('무역거래기반 조성에 관한 법률',five['text'])
        self.assertIn('사용비율이 큰 업종',six['text'])
        self.assertEqual(six['citation_status'],'zero-explicit-citations')
        self.assertEqual(six['citation_count'],0)

    def test_real_citation_offsets_counts_and_self_reference(self):
        result = analyze(self.enriched)
        self.assertEqual((len(result['edges']),len(result['external_references'])),(7,27))
        self.assertEqual(len(result['issues']),25)
        rows = result['edges']+result['external_references']
        self.assertEqual(len({r['evidence_id'] for r in rows}),34)
        for row in rows:
            doc = next(d for d in self.enriched['laws'] if d['name']==row['source_law'])
            a = next(a['body_analysis'] for a in doc['annexes'] if a['ref']==row['source_jo'])
            self.assertEqual(a['text'][row['source_start']:row['source_end']],row['cite_raw'])
            unit = next(u for u in a['units'] if u['id']==row['source_unit'])
            self.assertTrue(unit['start'] <= row['source_start'] < row['source_end'] <= unit['end'])
        own = [r for r in rows if r['cite_raw']=='제25조의3제3항제2호가목']
        self.assertEqual(len(own),1)
        self.assertEqual(own[0]['target_law'],'조세특례제한법 시행령')

    def test_graph_merge_preserves_non_annex_and_is_idempotent(self):
        ordinary = dict(target_kind='article',source_law='fixture',source_jo='1')
        graph = dict(edges=[ordinary],external_references=[],relation_counts={'article':1})
        before = deepcopy(graph)
        merged = merge_graph(graph,self.enriched)
        self.assertEqual(graph,before)
        self.assertEqual(merged['edges'][0],ordinary)
        self.assertEqual(merge_graph(merged,self.enriched),merged)

    def test_collection_reproduces_and_never_overwrites(self):
        report = collect(self.bundle,DEFAULT_OUTPUT)
        self.assertEqual(report['selected_annexes'],3)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'result.json'
            immutable_write(path,b'original')
            with self.assertRaises(ValueError): immutable_write(path,b'changed')
            self.assertEqual(path.read_bytes(),b'original')


if __name__ == '__main__':
    unittest.main()
