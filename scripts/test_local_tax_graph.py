from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.local_tax_collection import parse_ordinance, save
from core.local_tax_graph import build_graph, prepare_document, validate_bundle, publish, load_manifest, load_bundle, national_reverse
from core.fsc_administrative import provision_blocks
from core.galaxy_focus import analyze_focus, visible_rows
from scripts.test_local_tax_collection import BODY, RECORD


def statute():
    articles=[]
    for jo in ('1','4','5','6'):
        text=f'제{jo}조(기준) ① 과세 기준을 정한다.\n② 제1항에 따른다.'
        articles.append(dict(jo=jo,title='기준',text=text,effective='20260101',blocks=provision_blocks(text,jo)))
    return dict(name='지방세법',law_id='100',mst='200',effective='20260101',provider='eflaw',category='local_tax',
                managing_authority='행정안전부',kind='법률',family='지방세법',source_url='https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=200',
                body_status='indexed-statute-text',articles=articles,annexes=[])


def ordinance(text=None):
    doc=parse_ordinance(BODY,RECORD,'20260917')
    if text is not None:
        doc['articles'][1].update(text=text,blocks=provision_blocks(text,'2의1'))
    return prepare_document(doc)


def bundle(ordin=None):
    docs=[prepare_document(statute()),ordin or ordinance()]
    return dict(source=dict(built_at='20260917',laws=docs),graph=build_graph(docs,'20260917'))


def published(directory):
    folder=Path(directory);stage=folder/'staging/20260917'
    save(stage/'central.json',[statute()])
    doc=ordinance();save(folder/'body-cache/1-2.json',dict(body=doc))
    row=dict(status='indexed',name=doc['name'],managing_authority='가람시',law_id='1',mst='2',path='1-2.json')
    save(stage/'collection.json',dict(as_of='20260917',inventory_total=2,candidates_total=1,eligible=1,indexed=1,failed=[],skipped=[],body_status=[row]))
    save(stage/'inventory.json',dict(records=[RECORD,{**RECORD,'name':'누리시 조례','managing_authority':'누리시','law_id':'3'}]))
    publish(folder,'20260917')
    return load_manifest(folder)


class GraphTests(unittest.TestCase):
    def test_defined_alias_and_self_ordinance_are_distinct(self):
        data=bundle();validate_bundle(data)
        edges=[e for e in data['graph']['edges'] if e['source_law']==RECORD['name'] and e['target_kind']=='article']
        self.assertIn(('지방세법','제4조'),[(e['target_law'],e['target_ref']) for e in edges])
        self.assertIn((RECORD['name'],'제1조'),[(e['target_law'],e['target_ref']) for e in edges])
        self.assertTrue(visible_rows(analyze_focus('지방세법','제4조',data['graph']),'reverse'))

    def test_article_ranges_expand_and_item_scope_survives(self):
        doc=ordinance('제2조의1(기준) 법 제4조부터 제6조까지 및 제1조제2항을 준용한다.')
        data=bundle(doc);validate_bundle(data)
        targets={e['target_ref'] for e in data['graph']['edges'] if e['source_law']==doc['name'] and e['target_kind']=='article'}
        self.assertEqual(targets,{'제4조','제5조','제6조','제1조제2항'})

    def test_undefined_alias_is_not_assigned_to_own_ordinance(self):
        doc=ordinance('제2조의1(기준) 영 제4조 및 같은 조례 제5조에 따른다.')
        data=bundle(doc)
        edges=[e for e in data['graph']['edges'] if e['source_law']==doc['name'] and e['target_kind']=='article']
        self.assertFalse(edges)
        self.assertGreaterEqual(len(data['graph']['citation_issues']),2)

    def test_outside_jurisdiction_is_preserved_as_uncollected(self):
        doc=ordinance('제2조의1(기준) 「다른시 시세 조례」 제4조에 따른다. 이 조례 별표 1을 참조한다.')
        data=bundle(doc)
        refs=data['graph']['external_references']
        self.assertEqual(refs[0]['target_law'],'다른시 시세 조례')
        self.assertEqual(refs[0]['target_status'],'not-collected')
        self.assertIn('/자치법규/',refs[0]['target_url'])
        annex=next(e for e in data['graph']['edges'] if e['target_kind']=='annex')
        self.assertEqual(annex['target_analysis'],'annex-body-not-indexed')

    def test_same_ordinance_cannot_inherit_a_national_law(self):
        doc=ordinance('제2조의1(기준) 「지방세법」 제4조와 같은 조례 제5조를 검토한다.')
        data=bundle(doc)
        targets=[e['target_ref'] for e in data['graph']['edges'] if e['source_law']==doc['name'] and e['target_kind']=='article']
        self.assertEqual(targets,['제4조'])
        self.assertTrue(data['graph']['citation_issues'])

    def test_display_abbreviation_does_not_become_a_legal_alias(self):
        doc=ordinance('제2조의1(기준) 지특법 제4조에 따른다.')
        data=bundle(doc)
        self.assertFalse([e for e in data['graph']['edges'] if e['source_law']==doc['name'] and e['target_kind']=='article'])
        self.assertTrue(data['graph']['citation_issues'])

    def test_evidence_and_domain_validation_are_enforced(self):
        data=bundle();validate_bundle(data)
        bad=deepcopy(data);bad['graph']['edges'][0]['cite_raw']='조작'
        with self.assertRaises(ValueError):validate_bundle(bad)
        bad=deepcopy(data);bad['source']['laws'][0]['category']='tax'
        with self.assertRaises(ValueError):validate_bundle(bad)

    def test_shard_publication_reverse_lookup_and_no_tax_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            folder,manifest=published(temp)
            with patch('core.law_galaxy.load_graph',side_effect=AssertionError('tax fallback')):
                base=load_bundle(folder,manifest)
                self.assertEqual(base['graph']['laws'],['지방세법'])
                region=next(r for r in manifest['regions'] if r['authority']=='가람시')
                data=load_bundle(folder,manifest,region['id'])
                self.assertEqual(len(data['source']['laws']),2)
                from ui.local_tax_map_ui import _map
                self.assertEqual(len(_map(data)['nodes']),2)
            self.assertTrue(national_reverse(folder,manifest,'지방세법','제4조'))
            self.assertFalse(national_reverse(folder,manifest,'지방세법','제5조'))
            absent=next(r for r in manifest['regions'] if r['authority']=='누리시')
            with self.assertRaises(ValueError):load_bundle(folder,manifest,absent['id'])

    def test_missing_local_data_never_loads_another_galaxy(self):
        from streamlit.testing.v1 import AppTest
        from ui import local_tax_map_ui
        with tempfile.TemporaryDirectory() as temp, patch.object(local_tax_map_ui,'OUTPUT',Path(temp)):
            with patch.object(local_tax_map_ui,'_snapshot',side_effect=AssertionError('fallback')):
                app=AppTest.from_string('from ui.local_tax_map_ui import render\nrender()').run()
                self.assertFalse(app.exception,str(app.exception))
                self.assertIn('지방세 데이터 미수집',app.info[0].value)

    def test_ui_follows_national_reverse_to_region_and_preserves_state(self):
        from streamlit.testing.v1 import AppTest
        from ui import local_tax_map_ui
        with tempfile.TemporaryDirectory() as temp:
            folder,manifest=published(temp)
            with patch.object(local_tax_map_ui,'OUTPUT',Path(temp)):
                app=AppTest.from_string('from ui.local_tax_map_ui import render\nrender()',default_timeout=30).run()
                app.text_input(key='local_tax_central_focus_ref').set_value('제4조')
                app.button(key='local_tax_central_focus_run').click().run()
                self.assertFalse(app.exception,str(app.exception))
                app.button(key='local_tax_central_open_region').click().run()
                self.assertFalse(app.exception,str(app.exception))
                self.assertEqual(app.selectbox(key='local_tax_province').value,'가람시')
                region=next(r for r in manifest['regions'] if r['authority']=='가람시')
                prefix='local_tax_'+region['id']+'_'
                self.assertEqual(app.session_state[prefix+'selection'],('지방세법','제4조'))
                app.radio(key=prefix+'direction').set_value('reverse').run()
                app.selectbox(key='local_tax_province').set_value('중앙 법령만').run()
                self.assertEqual(app.session_state['local_tax_central_selection'],('지방세법','제4조'))
                self.assertEqual(app.radio(key='local_tax_central_direction').value,'both')


if __name__=='__main__':unittest.main()
