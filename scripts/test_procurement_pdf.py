import json
from copy import deepcopy
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from core.procurement_pdf import extract_pdf, analyze_pdf, validate_extraction, digest, LOCAL_LAW, ALLOWED


def fixture(text):
    record=dict(document_id='29508',name=ALLOWED['29508'],uid='admrul:29508',provider='admrul',effective='20260701',category='procurement',source_url='https://www.law.go.kr/')
    return dict(kind='procurement-pdf-prose',text=text,text_sha256=digest(text),file_sha256='f'*64,
        record=record,pdf_url='https://www.law.go.kr/flDownload.do?flSeq=1',
        pages=[dict(page=1,start=0,end=len(text),analyzed_units=1)],
        units=[dict(start=0,end=len(text),text=text,page=1,printed_page='2',chapter='제1장 일반기준',section='제1절 총칙',item='1. / 가.',locator='제1장 / 제1절 / 1. / 가.')])


class ProcurementPdfTests(unittest.TestCase):
    def test_explicit_alias_and_page_provenance(self):
        body='「'+LOCAL_LAW+' ․ 시행령 ․ 시행규칙」(각각 "법", "시행령", "시행규칙"이라 한다)\n시행령 제33조에 따른다.'
        result=fixture(body);target=dict(name=LOCAL_LAW+' 시행령',articles=[dict(jo='33')],effective='20260101',source_url='https://www.law.go.kr/')
        rows,issues=analyze_pdf(result,[target]);self.assertEqual(len(rows),1)
        row=rows[0];self.assertEqual(row['target_law'],target['name']);self.assertEqual(row['source_jo'],'')
        self.assertEqual(row['source_url'],result['pdf_url']+'#page=1')
        self.assertEqual(body[row['source_start']:row['source_end']],row['raw'])
        self.assertTrue(issues) # Collective definition is not an invented law name.

    def test_alias_not_inferred_from_title_and_missing_article_not_faked(self):
        target=dict(name=LOCAL_LAW+' 시행령',articles=[dict(jo='33')],effective='',source_url='https://www.law.go.kr/')
        rows,issues=analyze_pdf(fixture('시행령 제33조에 따른다.'),[target])
        self.assertFalse(rows);self.assertTrue(issues)
        rows,issues=analyze_pdf(fixture('「'+target['name']+'」 제999조에 따른다.'),[target])
        self.assertFalse(rows);self.assertTrue(any('대상 조문 없음' in i['reason'] for i in issues))

    def test_checksum_page_bounds_and_empty_analysis_are_blocked(self):
        result=fixture('본문');validate_extraction(result)
        for edit in (lambda r:r.update(text='오염'),lambda r:r['units'][0].update(end=99),lambda r:r.update(units=[])):
            broken=deepcopy(result);edit(broken)
            with self.assertRaises(ValueError):validate_extraction(broken)

    def test_contents_supplement_table_and_chapter_reference_boundaries(self):
        class Page:
            def __init__(self,lines,table=False):self.lines=lines;self.table=table
            def dedupe_chars(self,**kw):return self
            def extract_text(self,**kw):return '\n'.join(t for t,_ in self.lines)
            def find_tables(self):return [SimpleNamespace(bbox=(0,60,100,80))] if self.table else []
            def extract_text_lines(self,**kw):return [dict(text=t,top=i*20,bottom=i*20+15,x0=0,x1=100,chars=[dict(text=t,size=size)]) for i,(t,size) in enumerate(self.lines)]
        class Pdf:
            pages=[Page([('표지',20)]),Page([('목차',20),('부 칙 ··· 90',14)]),
                Page([('제1장 일반기준',20),('제1절 총칙',15),('1. 본문',14),('「표안법」 제2조',14),('제9장 다른 장을 참고한다.',14),('「본문법」 제3조',14)],True),
                Page([('제9절 기타',14),('2. 확인',14),('등) 참조한다.',14),('제4절 다른 절을 준용한다.',14),('「확인법」 제8조',14)]),
                Page([('[별표 1]',14),('「서식법」 제4조',14)]),Page([('부칙',20),('「부칙법」 제5조',14)])]
            def __enter__(self):return self
            def __exit__(self,*args):pass
        module=SimpleNamespace(open=lambda _:Pdf(),__version__='fixture')
        with tempfile.TemporaryDirectory() as folder,patch.dict('sys.modules',{'pdfplumber':module}):
            p=Path(folder)/'test.pdf';p.write_bytes(b'%PDF-test')
            record={**fixture('x')['record'],'attachments':[{'첨부파일링크':'https://www.law.go.kr/flDownload.do?flSeq=1'}]}
            result=extract_pdf(p,record);validate_extraction(result)
        joined='\n'.join(u['text'] for u in result['units'])
        self.assertIn('본문법',joined);self.assertNotIn('표안법',joined);self.assertNotIn('서식법',joined);self.assertNotIn('부칙법',joined)
        self.assertEqual({u['chapter'] for u in result['units']},{'제1장 일반기준'})
        check=next(u for u in result['units'] if '확인법' in u['text'])
        self.assertEqual(check['section'],'제9절 기타');self.assertEqual(check['item'],'2.')


if __name__=='__main__':unittest.main()
