"""FTC-specific scope, source numbering and edition protection."""
from copy import deepcopy
import unittest
from core.ftc_collection import FAIR,selected,tags,prepare_source,discover_inventory
from core.fsc_collection import CollectionError
from core.ftc_text_citations import collect_text_citations,validate_text_citations,ftc_adapter,reading_row

def text_source():
    statute=dict(uid='law:1',name=FAIR,short_name='공정거래법',provider='eflaw',category='ftc',managing_authority='공정거래위원회',
                 effective='20260901',source_url='https://www.law.go.kr/법령/독점규제및공정거래에관한법률',
                 articles=[dict(jo=str(i),title='기준',text=f'제{i}조(기준) 본문') for i in (9,10,11)])
    rule=dict(uid='rule:1',name='기업결합 심사기준',provider='admrul',category='ftc',managing_authority='공정거래위원회',
              effective='20260901',source_url='https://www.law.go.kr/행정규칙/기업결합심사기준',
              raw_body_blocks=['Ⅰ. 목적\n「'+FAIR+'」(이하 ‘법’이라 한다) 제9조제1항에 따른다.\nⅡ. 기준\n법 제9조부터 제11조까지 적용한다.\n법 제999조를 확인한다.\n부칙\n법 제10조에 따른다.'],articles=[])
    return prepare_source(dict(domain='ftc',laws=[statute],administrative_rules=[rule]))

class FtcTests(unittest.TestCase):
    def test_scope_is_official_and_multi_tagged(self):
        self.assertEqual(tags(FAIR,'eflaw'),['competition','groups'])
        self.assertTrue(selected('제조물 책임법','법무부,공정거래위원회','eflaw'))
        self.assertFalse(selected(FAIR,'금융위원회','eflaw'))
        self.assertFalse(selected('공정거래위원회 인사관리규정','공정거래위원회','admrul'))
        self.assertTrue(selected('부당한 지원행위의 심사지침','공정거래위원회','admrul'))
        self.assertTrue(selected('동일인 판단 기준 및 확인 절차에 관한 지침','공정거래위원회','admrul'))
        self.assertFalse(selected('소비자정책자문단 설치·운영에 관한 규정','공정거래위원회','admrul'))

    def test_real_paragraph_locations_aliases_ranges_and_unknown_targets(self):
        source=text_source();rows,issues=collect_text_citations(source)
        validate_text_citations(source,rows)
        self.assertEqual(len(rows),4)
        self.assertEqual({r['target_ref'] for r in rows},{'제9조제1항','제9조','제10조','제11조'})
        self.assertEqual({r['source_ref'] for r in rows},{'Ⅰ. 목적','Ⅱ. 기준'})
        self.assertTrue(all(r['source_jo']=='' for r in rows))
        self.assertIn('‘법’',rows[0]['raw'])
        self.assertTrue(any('999' in i['raw'] and '대상 조문 없음' in i['reason'] for i in issues))
        damaged=deepcopy(rows);damaged[0]['source_end']-=1
        with self.assertRaisesRegex(ValueError,'offset'):validate_text_citations(source,damaged)
        reverse=reading_row(rows[0],'reverse')
        self.assertEqual(reverse['neighbor_kind'],'text');self.assertEqual(reverse['neighbor_jo'],'')

    def test_official_short_title_is_resolved_without_changing_display(self):
        source=text_source();law=source['laws'][0]
        article={'text':'제1조(목적) 「공정거래법」 제9조를 적용한다.'}
        result=ftc_adapter(law,article,source['laws'])
        self.assertEqual(result[0]['target_name'],FAIR)
        self.assertEqual(result[0]['raw'],'「공정거래법」 제9조')

    def test_text_export_keeps_numbered_graph_separate_and_reader_identifiers(self):
        import gzip,json,tempfile
        from pathlib import Path
        from scripts.build_static_galaxies import export_documents,Writer
        source=text_source();rows,issues=collect_text_citations(source)
        docs=source['laws']+source['administrative_rules']
        graph=dict(domain='ftc',laws=[FAIR],focus_laws=[FAIR],catalog=[],edges=[],built_at='20260901',text_citations=rows,text_citation_issues=issues)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);entries,ids=export_documents(Writer(root),'ftc','',docs,graph)
            values=[json.loads(gzip.decompress((root/e['file']['url']).read_bytes())) for e in entries]
            law,rule=values
            self.assertEqual(len(law['details']['9']['rows']),2)
            self.assertEqual(rule['articles'],[])
            self.assertEqual(len(rule['text_connections']),4)
            self.assertTrue(all(r['neighbor_id']==ids[FAIR] for r in rule['text_connections']))
            self.assertTrue(all(r['neighbor_id']==ids[rule['meta']['name']] for r in law['details']['9']['rows']))

    def test_paragraph_document_does_not_get_fabricated_article_numbers(self):
        rule=dict(name='기업결합 심사기준',provider='admrul',category='ftc',managing_authority='공정거래위원회',
                  effective='20260901',raw_body_blocks=['Ⅰ. 목적\n이 기준은 법 제9조에 따른다.\nⅡ. 심사\n1. 시장'],articles=[])
        source=dict(domain='ftc',laws=[],administrative_rules=[rule]);original=deepcopy(source)
        prepared=prepare_source(source)['administrative_rules'][0]
        self.assertEqual(prepared['articles'],[]);self.assertIn('문단',prepared['analysis_error'])
        self.assertEqual(source,original)

    def test_article_rules_index_and_display_official_names(self):
        rule=dict(name='공정거래위원회 조사절차에 관한 규칙',short_name='조사규칙',provider='admrul',category='ftc',
                  managing_authority='공정거래위원회',effective='20260901',raw_body_blocks=['제1조(목적) 이 규칙은 「'+FAIR+'」(이하 "법"이라 한다) 제81조에 따른다.\n제2조(기준) 법 제82조에 따른다.'],articles=[])
        d=prepare_source(dict(domain='ftc',laws=[],administrative_rules=[rule]))['administrative_rules'][0]
        self.assertEqual([a['jo'] for a in d['articles']],['1','2']);self.assertEqual(d['display_name'],rule['name'])
        self.assertEqual(d['aliases']['법'],FAIR)

    def test_foreign_corpus_is_rejected(self):
        with self.assertRaises(ValueError):prepare_source(dict(domain='tax',laws=[],administrative_rules=[]))

    def test_api_pagination_failure_is_not_success(self):
        def request(endpoint,params):
            self.assertEqual(params['org'],'1130000')
            return b'<LawSearch><totalCnt>2</totalCnt><page>1</page></LawSearch>'
        with self.assertRaisesRegex(CollectionError,'short-procurement-page'):discover_inventory(request,'20260922')

if __name__=='__main__':unittest.main()
