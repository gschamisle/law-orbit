from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from core.annex_metadata import annex_index, annotate_annex
from core.universe_builder import build_universe
from scripts.build_annex_reference_site import update_catalog
from scripts.build_static_galaxies import Writer, export_documents
from scripts.static_storage import Storage


def fixture():
    return dict(name='시험법 시행령',provider='eflaw',category='labor',effective='20260929',
                citation_policy='mofe-explicit',source_url='https://www.law.go.kr/법령/시험법시행령',
                articles=[dict(jo='7',title='적용범위',text='제7조(적용범위) 적용 사항은 별표 1과 같다.')],
                annexes=[dict(ref='별표 1',title='적용 사항(제7조 관련)',effective='20260929',
                             urls=['https://www.law.go.kr/LSW/flDownload.do?flSeq=1'])])


def stats():
    return dict(source_metadata_unavailable=[],metadata_annexes_added=0,rows_with_metadata_updated=0,
                new_collected_references=0,new_external_references=0,new_review_issues=0,documents_updated=0)


class AnnexReferenceSiteTests(unittest.TestCase):
    def test_reverse_uses_annex_owner_and_keeps_article_rows_untouched(self):
        index=annex_index([fixture()])
        row=dict(direction='reverse',neighbor_kind='annex',neighbor_law='시험법 시행령',neighbor_jo='별표 1',
                 source_law='시험법 시행령',target_law='다른법',target_kind='article')
        result=annotate_annex(row,index)
        self.assertEqual(result['annex_urls'],fixture()['annexes'][0]['urls'])
        self.assertFalse(result['annex_analyzed'])
        article=dict(neighbor_kind='article',direction='forward',target_kind='article')
        self.assertIs(annotate_annex(article,index),article)

    def test_incremental_update_preserves_evidence_and_does_not_analyze_annex_body(self):
        doc=fixture();source=deepcopy(doc)
        graph=build_universe(dict(laws=[doc],built_at='20260929'),focus_categories=('labor',),article_adapter=lambda *args:[])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);writer=Writer(root)
            entries,_=export_documents(writer,'labor','',[doc],graph)
            storage=Storage(root)
            body=storage.read(entries[0]['file']);body.pop('annexes')
            old_rows=deepcopy(body['details']['7']['rows'])
            body['pdf_analysis_sentinel']={'preserved':'yes'}
            entries[0]['file']=writer.data(body)
            old=deepcopy(body)
            catalog=dict(laws=entries,built_at='20260929')
            result_stats=stats()
            updated=update_catalog('labor',catalog,storage,writer,[doc],result_stats)
            new=storage.read(updated['laws'][0]['file'])
            self.assertEqual(new['articles'],old['articles'])
            self.assertEqual(new['pdf_analysis_sentinel'],old['pdf_analysis_sentinel'])
            self.assertEqual(new['annexes'][0]['status'],'not-analyzed')
            self.assertNotIn('analysis',new['annexes'][0])
            rows=new['details']['7']['rows']
            for before,after in zip(old_rows,rows):
                self.assertEqual(before,{k:v for k,v in after.items() if k in before})
            added=rows[len(old_rows):]
            self.assertEqual([(r['direction'],r['target_ref']) for r in added],[('forward','별표 1')])
            self.assertEqual(added[0]['annex_urls'],doc['annexes'][0]['urls'])
            self.assertFalse(added[0]['annex_analyzed'])
            repeat=stats()
            again=update_catalog('labor',updated,storage,writer,[doc],repeat)
            self.assertEqual(again,updated)
            self.assertEqual(repeat['new_collected_references'],0)
            self.assertEqual(doc,source)

    def test_mismatched_source_edition_fails_before_reuse(self):
        doc=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);writer=Writer(root)
            graph=build_universe(dict(laws=[doc],built_at='20260929'),focus_categories=('labor',),article_adapter=lambda *args:[])
            entries,_=export_documents(writer,'labor','',[doc],graph)
            bad=deepcopy(doc);bad['articles'][0]['text']+=' 다른 판본'
            with self.assertRaisesRegex(ValueError,'edition differ'):
                update_catalog('labor',dict(laws=entries),Storage(root),writer,[bad],stats())
            bad=deepcopy(doc);bad['source_url']='https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=999'
            with self.assertRaisesRegex(ValueError,'edition differ'):
                update_catalog('labor',dict(laws=entries),Storage(root),writer,[bad],stats())

    def test_edition_url_can_be_derived_from_collected_statute_id(self):
        doc=fixture();doc.pop('source_url');doc['mst']='12345'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);writer=Writer(root)
            graph=build_universe(dict(laws=[doc],built_at='20260929'),focus_categories=('labor',),article_adapter=lambda *args:[])
            entries,_=export_documents(writer,'labor','',[doc],graph)
            updated=update_catalog('labor',dict(laws=entries),Storage(root),writer,[doc],stats())
            self.assertIn('lsiSeq=12345',updated['laws'][0]['url'])


if __name__=='__main__':unittest.main()
