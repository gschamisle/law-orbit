"""Annex evidence and conservative opt-in boundaries; no network required."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from core.annex_analysis import box_cells,extract_annex,digest,collect_annex_citations,validate_analysis
from core.universe_builder import build_universe
from core.galaxy_focus import analyze_focus


def analysis(texts):
    text='';units=[]
    for i,value in enumerate(texts):
        units.append(dict(id=f'u{i}',locator=f'표 {i+1}행',kind='cell',raw_text=value,text=value,start=len(text),end=len(text)+len(value)))
        text+=value+'\n'
    return dict(schema=1,status='explicit-citations-ready',text=text,units=units,text_sha256=digest(text.encode()),file_sha256='fixture')


def fixture():
    target=dict(name='의료법',category='medical',provider='eflaw',effective='20260612',source_url='https://www.law.go.kr/법령/의료법',articles=[dict(jo='43',title='진료과목',text='제43조(진료과목) 본문')],annexes=[])
    rule=dict(name='의료법 시행규칙',category='medical',provider='eflaw',effective='20260612',source_url='https://www.law.go.kr/법령/의료법시행규칙',articles=[],annexes=[dict(ref='별표 5',title='의료인 정원',effective='20260612',urls=[],body_analysis=analysis(['법 제43조제1항에 따른다.','법 제43조제2항에 따른다.']))])
    return dict(laws=[target,rule],built_at='20260928')


class AnnexTests(unittest.TestCase):
    def test_cells_do_not_interleave(self):
        rows=box_cells('┌─┬─┐\n│의사│법 제43│\n│    │조제1항│\n└─┴─┘')
        self.assertEqual(rows,[['의사','법 제43 조제1항']])

    def test_ambiguous_table_fails(self):
        with self.assertRaises(ValueError):box_cells('┌─┬─┐\n│a│b│\n│c│\n└─┴─┘')

    def test_default_unchanged_and_opt_in_reverse_keeps_distinct_cells(self):
        src=fixture();original=deepcopy(src)
        old=build_universe(src,focus_categories=('medical',),preserve_external=True)
        self.assertFalse(old['edges']);self.assertNotIn('annex_analysis',old)
        graph=build_universe(src,focus_categories=('medical',),preserve_external=True,annex_bodies=True)
        self.assertEqual(len(graph['edges']),2)
        rows=analyze_focus('의료법','43',graph)['rows']
        self.assertEqual(len(rows),2);self.assertTrue(all(r['neighbor_kind']=='annex' for r in rows))
        self.assertEqual(src,original)
        body=src['laws'][1]['annexes'][0]['body_analysis']['text']
        for e in graph['edges']:self.assertEqual(body[e['source_start']:e['source_end']],e['cite_raw'])

    def test_no_alias_leak_between_cells_and_unresolved_internal_item(self):
        src=fixture();src['laws'][1]['annexes'][0]['body_analysis']=analysis(['「외부법」 제2조를 준용한다.','같은 법 제3조 및 제2호가목에 따른다.'])
        result=collect_annex_citations(src['laws'],('medical',))
        self.assertEqual(len(result['external_references']),1)
        self.assertEqual(result['external_references'][0]['target_status'],'not-collected')
        self.assertTrue(any('별칭' in i['reason'] for i in result['issues']))
        self.assertTrue(any('별표 내부' in i['reason'] for i in result['issues']))

    def test_missing_target_is_not_success(self):
        src=fixture();src['laws'][1]['annexes'][0]['body_analysis']=analysis(['법 제999조에 따른다.'])
        result=collect_annex_citations(src['laws'],('medical',))
        self.assertFalse(result['edges']);self.assertTrue(result['issues'])

    def test_tampered_evidence_is_rejected(self):
        a=analysis(['법 제43조']);a['text']='변조'
        with self.assertRaises(ValueError):validate_analysis(a)

    def test_unassigned_text_and_duplicate_units_rejected(self):
        a=analysis(['법 제43조','법 제43조']);a['units'][1]['id']=a['units'][0]['id']
        with self.assertRaises(ValueError):validate_analysis(a)
        a=analysis(['법 제43조']);a['units']=[]
        with self.assertRaises(ValueError):validate_analysis(a)

    def test_unknown_multicell_hwp_not_flattened(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'table.hwp';p.write_bytes(bytes.fromhex('d0cf11e0a1b11ae1'))
            with patch('core.annex_analysis.read_hwp_text',return_value='법 제43조'),patch('core.annex_analysis.hwp_table_shapes',return_value=[(2,3)]):
                self.assertEqual(extract_annex(p)['status'],'not-analyzed')

    def test_source_filter_keeps_destination_catalog(self):
        src=fixture();g=build_universe(src,focus_categories=('medical',),annex_bodies=True,preserve_external=True,source_names={'의료법 시행규칙'})
        self.assertEqual(len(g['edges']),2);self.assertFalse(g['external_references'])

    def test_hwpx_signature_and_linebreak_tail(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'download.hwp'
            with zipfile.ZipFile(p,'w') as z:
                z.writestr('Contents/section0.xml','<section><p><run><t>첫 줄<lineBreak/>법 제43조</t></run></p></section>')
            a=extract_annex(p)
            self.assertEqual(a['format'],'hwpx');self.assertIn('첫 줄\n법 제43조',a['text'])
            validate_analysis(a)

    def test_unsupported_file_is_explicitly_unanalyzed(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'scan.pdf';p.write_bytes(b'%PDF fake')
            a=extract_annex(p);self.assertEqual(a['status'],'not-analyzed');self.assertTrue(a['issues'])


if __name__=='__main__':unittest.main()
