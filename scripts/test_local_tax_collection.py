import tempfile
from pathlib import Path
import unittest
from core.local_tax_collection import ordinance_record, parse_page, parse_ordinance, collect_ordinance, inventory, safe_xml, read, save
from core.fsc_collection import CollectionError, xml_root

RECORD=dict(name='가람시 시세 조례',official_name='가람시 시세 조례',law_id='1',mst='2',effective='20260101',
            managing_authority='가람시',kind='조례',provider='ordin',category='local_tax',state='current-candidate',
            source_url='https://www.law.go.kr/LSW/ordinInfoP.do?ordinSeq=2')
BODY='''<LawService><자치법규기본정보><자치법규ID>1</자치법규ID><자치법규일련번호>2</자치법규일련번호><자치법규명>가람시 시세 조례</자치법규명><지자체기관명>가람시</지자체기관명><시행일자>20260101</시행일자><자치법규종류>C0001</자치법규종류></자치법규기본정보><조문><조><조문번호>000100</조문번호><조문여부>Y</조문여부><조제목>목적</조제목><조내용>제1조(목적) 「지방세법」(이하 "법"이라 한다)에 따른다.</조내용></조><조><조문번호>000201</조문번호><조문여부>Y</조문여부><조제목>기준</조제목><조내용>제2조의1(기준) ① 법 제4조에 따른다.
② 이 조례 제1조를 준용한다.</조내용></조></조문><부칙><부칙내용>이 조례는 공포한 날부터 시행한다.</부칙내용></부칙></LawService>'''.encode()

def page(records,page=1,total=None):
    rows=''.join('<law>'+''.join(f'<{tag}>{r[key]}</{tag}>' for key,tag in [('name','자치법규명'),('law_id','자치법규ID'),('mst','자치법규일련번호'),('effective','시행일자'),('managing_authority','지자체기관명'),('kind','자치법규종류')])+'</law>' for r in records)
    return f'<OrdinSearch><resultCode>00</resultCode><totalCnt>{len(records) if total is None else total}</totalCnt><page>{page}</page>{rows}</OrdinSearch>'.encode()


class CollectionTests(unittest.TestCase):
    def test_actual_api_shape_and_article_branch(self):
        doc=parse_ordinance(BODY,RECORD,'20260917')
        self.assertEqual([a['jo'] for a in doc['articles']],['1','2의1'])
        self.assertEqual(doc['aliases']['법'],'지방세법')
        self.assertTrue(doc['supplements'])
        self.assertEqual(doc['coverage']['supplement'],'stored-not-indexed')
        self.assertEqual(doc['articles'][1]['blocks'][-1]['ref'],'제2조의1제2항')

    def test_edition_authority_and_date_cannot_be_guessed(self):
        for mutation in [dict(mst='3'),dict(effective='20270101'),dict(managing_authority='누리시')]:
            with self.assertRaises(CollectionError): parse_ordinance(BODY,{**RECORD,**mutation},'20260917')
        with self.assertRaises(CollectionError):
            parse_ordinance(BODY.replace(b'000201',b'000200'),RECORD,'20260917')

    def test_cache_resumes_and_rejects_tampering(self):
        calls=[]
        def request(*args): calls.append(args);return BODY
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            collect_ordinance(request,RECORD,root,'20260917')
            collect_ordinance(request,RECORD,root,'20260917')
            self.assertEqual(len(calls),1)
            path=root/'1-2.json';data=read(path);data['body']['name']='변조';save(path,data)
            with self.assertRaises(CollectionError):collect_ordinance(request,RECORD,root,'20260917')

    def test_listing_reconciles_unique_ids_not_just_row_count(self):
        with tempfile.TemporaryDirectory() as temp:
            result=inventory(lambda *a:page([RECORD]),Path(temp),'20260917',progress=lambda *a,**kw:None)
            self.assertEqual(result['received'],1)
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(CollectionError):
                inventory(lambda endpoint,params:page([RECORD] if params['query']!='*' else [RECORD,RECORD]),Path(temp),'20260917',progress=lambda *a,**kw:None)

    def test_reproduced_provider_duplicate_is_explained_in_ledger(self):
        with tempfile.TemporaryDirectory() as temp:
            result=inventory(lambda *a:page([RECORD,RECORD]),Path(temp),'20260917',progress=lambda *a,**kw:None)
            self.assertEqual(result['received'],1)
            self.assertEqual(result['received_rows'],2)
            self.assertEqual(result['provider_duplicates'][0]['rows'],2)

    def test_changed_list_fails_and_auth_echo_is_removed(self):
        calls=[]
        def request(*args):
            calls.append(1)
            return page([RECORD],total=1 if len(calls)==1 else 2)
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(CollectionError):inventory(request,Path(temp),'20260917',progress=lambda *a,**kw:None)
        raw=b'<link>/DRF/lawService.do?OC=private-value&amp;MST=2</link>'
        self.assertNotIn(b'private-value',safe_xml(raw))
        self.assertIn(b'MST=2',safe_xml(raw))

    def test_future_and_undated_records_stay_in_ledger(self):
        _,rows=parse_page(page([{**RECORD,'effective':'20270101'},{**RECORD,'law_id':'3','effective':''}]),1,'20260917')
        self.assertEqual([r['state'] for r in rows],['scheduled','date-unverified'])

    def test_search_old_editions_use_verified_current_inventory(self):
        rows=[{**RECORD,'mst':'10'},RECORD,{**RECORD,'law_id':'999'}]
        with tempfile.TemporaryDirectory() as temp:
            result=inventory(lambda *a:page(rows),Path(temp),'20260917',query='지방세',search=2,
                             canonical={'1':RECORD},progress=lambda *a,**kw:None)
            self.assertEqual(result['records'],[RECORD])
            self.assertEqual(result['edition_differences'][0]['hit_mst'],'10')
            self.assertEqual(result['unresolved'][0]['law_id'],'999')
            self.assertEqual(result['received_rows'],3)


if __name__=='__main__': unittest.main()
