"""Foreign-exchange source validation and citation isolation, without live API calls."""
import unittest
from copy import deepcopy
from core import forex_collection as c, forex_bok as bok
from core.fsc_collection import CollectionError
from core.fsc_administrative import adapter
from core.citation_scope import parse_target

def rule(name=c.REGULATION,body=None):
    return dict(name=name,provider='admrul',category='forex',effective='20260101',raw_body_blocks=[body or '제1-1조(목적) 「외국환거래법」(이하 "법"이라 한다)과 동법시행령(이하 "영"이라 한다)에 따른다.\n제7-1조(대상) 영 제3조 및 제7-2조를 따른다.\n제7-2조(절차) 지급 절차를 정한다.'])

class ForexTests(unittest.TestCase):
    def test_scope_and_authority(self):
        self.assertTrue(c.selected(c.LAW,'재정경제부','eflaw'))
        self.assertTrue(c.selected(c.REGULATION,'기획재정부','admrul'))
        self.assertFalse(c.selected('은행법','금융위원회','eflaw'))
        self.assertFalse(c.selected(c.REGULATION,'금융위원회','admrul'))
        self.assertFalse(c.selected(c.LAW+' 특례','재정경제부','eflaw'))
    def test_other_domain_rejected(self):
        with self.assertRaises(ValueError):c.prepare_source({'domain':'tax'})
    def test_hyphen_and_branch_distinct(self):
        self.assertNotEqual(parse_target('제7-1조',allow_hyphen=True),parse_target('제7조의1',allow_hyphen=True))
        with self.assertRaises(ValueError):parse_target('제7-1조',allow_hyphen=False)
    def test_alias_wrapping_and_derivative(self):
        doc=c.index_forex_rule(rule())
        self.assertEqual(doc['aliases']['영'],c.LAW+' 시행령')
        wrapped=c.index_forex_rule(rule(body='제1조(목적) 「외국환거래업무 취급세칙」(이하 “세칙”이\n라 한다) 제2-2조를 따른다.'))
        self.assertEqual(wrapped['aliases']['세칙'],'외국환거래업무 취급세칙')
        refs=adapter(wrapped,wrapped['articles'][0],[wrapped])
        self.assertTrue(any(e['target_name']=='외국환거래업무 취급세칙' and e['target_ref']=='제2-2조' for e in refs))
    def test_raw_evidence_offsets(self):
        doc=c.index_forex_rule(rule());article=doc['articles'][1]
        for e in adapter(doc,article,[doc]):self.assertEqual(article['text'][e['start']:e['end']],e['raw'])
    def test_explicit_derivative_not_own_article(self):
        doc=c.index_forex_rule(rule(body='제1조(목적) 「자본시장과 금융투자업에 관한 법률」 시행령 제10조를 따른다.'))
        refs=adapter(doc,doc['articles'][0],[doc])
        self.assertTrue(any(e['target_name']=='자본시장과 금융투자업에 관한 법률 시행령' for e in refs))
    def test_ambiguous_number_not_merged_or_guessed(self):
        doc=c.index_forex_rule(rule(body='제32조(보고) 보고한다.\n제32조2(제재) 제8조에 따른다.\n제33조(공지) 알린다.'))
        self.assertEqual([a['jo'] for a in doc['articles']],['32','33'])
        self.assertNotIn('제8조',doc['articles'][0]['text'])
        self.assertIn('제8조',doc['unparsed_provisions'][0]['raw'])
    def test_multiple_tags_do_not_omit_articles(self):
        self.assertIn('payment',c.tags('', '송금 신고'))
        self.assertIn('reporting',c.tags('', '송금 신고'))
    def test_official_url_only(self):
        for url in ['https://other.example/test.pdf','http://www.bok.or.kr/a','https://www.bok.or.kr@other.example/a']:
            with self.assertRaises(CollectionError):bok.official_url(url)
    def pdf(self,header='2026. 1. 1.',supplement='2026. 1. 1.',effect='2026년 1월 2일'):
        item=dict(name=bok.TITLES[0],document_id='123',version_id='456',promulgated='20260101')
        text=bok.TITLES[0]+'\n개정 '+header+'\n제1장 총칙\n제1조(목적) 업무.\n부 칙 <'+supplement+'>\n이 세칙은 '+effect+'부터 시행한다.'
        return item,[text]
    def test_pdf_dates_separate(self):
        item,pages=self.pdf();doc=bok.parse_pdf(item,pages,'hash','20260921')
        self.assertEqual(doc['promulgated'],'20260101');self.assertEqual(doc['effective'],'20260102')
    def test_pdf_rejects_version_mismatch(self):
        item,pages=self.pdf(header='2025. 1. 1.')
        with self.assertRaises(CollectionError):bok.parse_pdf(item,pages,'hash','20260921')
    def test_pdf_requires_current_supplement(self):
        for kwargs in [dict(supplement='2025. 1. 1.'),dict(effect='2027년 1월 1일')]:
            item,pages=self.pdf(**kwargs)
            with self.assertRaises(CollectionError):bok.parse_pdf(item,pages,'hash','20260921')
    def test_pdf_title_not_substituted(self):
        item,pages=self.pdf();item['name']='다른 세칙'
        with self.assertRaises(CollectionError):bok.parse_pdf(item,pages,'hash','20260921')
    def test_known_header_discrepancy_does_not_allow_other_hash(self):
        item,pages=self.pdf(header='2023. 1. 29.',supplement='2023. 12. 29.')
        item.update(document_id='100466',version_id='106486',promulgated='20231229')
        with self.assertRaises(CollectionError):bok.parse_pdf(item,pages,'different','20260921')
    def test_listing_id_and_title(self):
        raw=('<li><a href="/portal/singl/law/view.do?lawseq=123&amp;hseq=456">'+bok.TITLES[0]+'</a><span class="fs_date">20260101</span><a href="/portal/singl/law/fileDown.do?lawseq=123&amp;seq=456">PDF</a></li>').encode()
        self.assertEqual(bok.parse_listing(raw,bok.TITLES[0])['version_id'],'456')
        with self.assertRaises(CollectionError):bok.parse_listing(raw.replace(b'&amp;seq=456',b'&amp;seq=789'),bok.TITLES[0])


class CollectedForexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from core.forex_universe import BUNDLE,load_bundle
        if not BUNDLE.exists():raise unittest.SkipTest('Requires local collected forex corpus')
        cls.bundle=load_bundle();cls.graph=cls.bundle['graph'];cls.docs=cls.bundle['source']['laws']+cls.bundle['source']['administrative_rules']
    def test_sources_and_evidence_are_isolated(self):
        self.assertEqual(len(self.docs),14)
        self.assertTrue(all(d['category']=='forex' for d in self.docs))
        self.assertEqual({d['name'] for d in self.docs if d['provider']=='bok'},set(bok.TITLES))
        from core.forex_universe import validate_bundle
        validate_bundle(self.bundle)
        wrong=deepcopy(self.bundle);wrong['source']['domain']='tax'
        with self.assertRaises(ValueError):validate_bundle(wrong)
    def test_real_bok_links_and_reverse(self):
        from core.galaxy_focus import analyze_focus
        edges=self.graph['edges']
        e=next(e for e in edges if e['source_law']=='외국환거래업무 취급절차' and e['source_jo']=='3' and e['target_law']=='외국환거래업무 취급세칙')
        self.assertEqual(e['target_ref'],'제2-3조제4항')
        reverse=analyze_focus(e['target_law'],'제2-3조',self.graph)
        self.assertTrue(any(r['direction']=='reverse' and r['source_law']==e['source_law'] and r['source_jo']=='3' for r in reverse['rows']))
    def test_browser_and_engine_parity(self):
        from scripts.test_static_galaxies import browser,key
        from scripts.build_static_galaxies import EdgeIndex,tidy
        from core.galaxy_focus import analyze_focus
        cases=[];expected=[];index=EdgeIndex(self.graph,self.docs)
        for law,ref in [(c.REGULATION,'제7-1조'),(c.REGULATION,'제2-9조의2'),('외국환거래업무 취급세칙','제2-3조제4항'),('외국환거래업무 취급절차','제3조')]:
            result=analyze_focus(law,ref,self.graph)
            self.assertEqual(result['rows'],index.focus(law,ref)['rows'])
            jo=parse_target(ref,allow_hyphen=True).jo
            from core.citation_scope import Provision
            full=index.focus(law,Provision(jo).label)
            cases.append(dict(rows=[tidy(r,{},True) for r in full['rows']],reference=ref,hyphen=True))
            expected.append(sorted([key(r) for r in result['rows']],key=str))
        self.assertEqual([sorted(a,key=str) for a in browser(cases)],expected)
    def test_work_tags_keep_outside_connections(self):
        from core.forex_universe import mark_sector
        from core.galaxy_focus import analyze_focus
        all_rows=analyze_focus(c.REGULATION,'제2-9조의2',self.graph)
        filtered=mark_sector(all_rows,self.graph,'payment')
        self.assertEqual(len(all_rows['rows']),len(filtered['rows']))
        self.assertTrue(any(r['out_of_sector'] for r in filtered['rows']))
    def test_layout_only_uses_collected_articles(self):
        from scripts.build_static_galaxies import overview,metadata,ident
        catalog=[metadata(d,'forex','') for d in self.docs]
        data=overview(self.graph,'forex',{d['name']:ident('forex','',d['name']) for d in self.docs},catalog)
        self.assertEqual(len(data['nodes']),14)
        self.assertEqual(len(data['dust']),sum(len(d['articles']) for d in self.docs))
        self.assertEqual(len(data['links']),len(data['all_links']))
    def test_pdf_layout_and_ambiguous_article(self):
        doc=next(d for d in self.docs if d['name']=='외환정보집중기관 운영절차')
        self.assertEqual(len(doc['articles']),12)
        self.assertTrue(doc['source_notes'])
        self.assertNotIn('제3조',doc['articles'][0]['text'])
        doc=next(d for d in self.docs if d['name']=='외환정보집중기관 운영세칙')
        self.assertEqual(len(doc['unparsed_provisions']),1)
        self.assertNotIn('제32조2',next(a['text'] for a in doc['articles'] if a['jo']=='32'))

if __name__=='__main__':unittest.main()
