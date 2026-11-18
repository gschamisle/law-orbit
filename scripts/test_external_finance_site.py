"""Frozen-source restoration invariants for the export finance / KIC preview."""
from copy import deepcopy
import unittest

from core.fsc_administrative import adapter
from core.forex_collection import KIC
from core.forex_universe import build_graph
from scripts.build_edition_refresh_site import prepare_fresh
from scripts.build_external_finance_site import restore_forex


class MemoryStorage:
    def __init__(self, values):
        self.values=values

    def read(self, ref):
        return deepcopy(self.values[ref])


def article(jo, text):
    return dict(jo=jo, title='검증', label='제'+jo+'조', text=text, deleted=False,
                effective='20261102', sectors=['capital'],
                reference_notes=['[시행일: 2026. 11. 2.]'])


def fixture():
    specifications=[
        ('외국환거래법', 'law', 'https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=123', '재정경제부', '법률',
         [article('1','제1조(목적) 외국환거래를 정한다.')]),
        ('외국환거래법 시행령', 'decree', 'https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=124', '재정경제부', '대통령령',
         [article('1','제1조(대상) 법 제1조에 따른다.')]),
        ('외국환거래규정', 'regulation', 'https://www.law.go.kr/admRulLsInfoP.do?admRulSeq=125', '재정경제부', '고시',
         [article('1-1','제1-1조(목적) 「외국환거래법」(이하 "법"이라 한다)과 동법시행령(이하 "영"이라 한다)에 따른다.'),
          article('7-8','제7-8조(대상) ④ 다음을 따른다.\n2. 「대외경제협력기금법」시행령에 따른 지원.'),
          article('7-9','제7-9조(절차) 영 제1조를 따른다.')]),
        ('외국환거래업무 취급세칙', 'bok', 'https://www.bok.or.kr/portal/singl/law/view.do?lawseq=123&hseq=456', '한국은행', '한국은행 세칙',
         [article('1-1','제1-1조(목적) 「외국환거래규정」(이하 “규정”이\n라 한다)에 따른다.'),
          article('2-1','제2-1조(대상) 규정 제7-8조에 따른다.')]),
    ]
    entries=[];values={}
    for name,ident,url,authority,kind,articles in specifications:
        entry=dict(id=ident,domain='forex',name=name,label='화면용 '+ident,effective='20261102',
                   url=url,authority=authority,kind=kind,sectors=['capital'],file=ident,
                   source_notes=['공식 원문 주의사항'],pdf_url='https://www.bok.or.kr/portal/singl/law/fileDown.do?lawseq=123&seq=456' if ident=='bok' else '',
                   unparsed_provisions=[dict(raw='제32조2(미확인) 원문.',reason='번호 확인 필요')] if ident=='bok' else [])
        entries.append(entry)
        values[ident]=dict(meta=deepcopy(entry),articles=articles,annexes=[
            dict(ref='별표 1',title='검증 별표',effective='20261102',
                 urls=['https://www.law.go.kr/LSW/flDownload.do?flSeq=123'],status='not-analyzed',connections=[],issues=[])])
    kic=dict(domain='export_finance',built_at='20261118',laws=[
        dict(name=name,provider='eflaw',category='export_finance',state='current-body-verified',effective='20260102',
             source_url='https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq='+serial,
             uid='eflaw:'+serial,articles=[article('1','제1조(목적) 위탁 운용을 정한다.')],annexes=[])
        for name,serial in [(KIC,'900'),(KIC+' 시행령','901')]],scheduled=[
        dict(name=KIC,effective='20270101',state='scheduled')])
    return MemoryStorage(values),dict(laws=entries,built_at='20261109'),kic


class ExternalFinanceSiteTests(unittest.TestCase):
    def test_original_bodies_dates_notes_attachments_and_input_objects_survive(self):
        storage,catalog,kic=fixture()
        before=deepcopy((storage.values,catalog,kic))
        result=restore_forex(storage,catalog,kic)
        docs={d['name']:d for d in result['laws']+result['administrative_rules']}
        for entry in catalog['laws']:
            original=storage.values[entry['file']]
            restored=docs[entry['name']]
            for key in ('name','effective'):
                self.assertEqual(restored[key],entry[key])
            self.assertEqual(restored['source_url'],entry['url'])
            self.assertEqual(restored['annexes'],original['annexes'])
            for key in ('source_notes','pdf_url','unparsed_provisions'):
                self.assertEqual(restored[key],entry[key])
            for old,new in zip(original['articles'],restored['articles'],strict=True):
                for key in ('jo','title','text','deleted','effective','reference_notes'):
                    self.assertEqual(new[key],old[key])
            self.assertEqual(restored['display_name'],entry['label'])
            self.assertEqual(restored['citation_names'],[entry['name']])
            self.assertEqual(restored['short_name'],entry['name'])
            self.assertNotIn('citation_policy',restored)
        self.assertEqual((storage.values,catalog,kic),before)

    def test_bok_provenance_aliases_and_hyphen_citations_are_preserved(self):
        storage,catalog,kic=fixture();result=restore_forex(storage,catalog,kic)
        docs={d['name']:d for d in result['laws']+result['administrative_rules']}
        bok=docs['외국환거래업무 취급세칙']
        self.assertEqual(bok['provider'],'bok')
        self.assertIn(bok,result['administrative_rules'])
        self.assertEqual(bok['aliases']['규정'],'외국환거래규정')
        rule=docs['외국환거래규정']
        self.assertEqual(rule['aliases']['영'],'외국환거래법 시행령')
        graph=build_graph(result)
        self.assertTrue(any(e['source_law']==bok['name'] and e['source_jo']=='2-1'
                            and e['target_law']==rule['name'] and e['target_ref']=='제7-8조'
                            for e in graph['edges']))
        self.assertTrue(any(e['source_law']==rule['name'] and e['source_jo']=='7-9'
                            and e['target_law']=='외국환거래법 시행령' and e['target_ref']=='제1조'
                            for e in graph['edges']))
        # Statutory deictic owners retain the established general-parser route.
        self.assertTrue(any(e['source_law']=='외국환거래법 시행령' and e['target_law']=='외국환거래법'
                            and e['target_ref']=='제1조' for e in graph['edges']))
        broad=next(e for e in graph['external_references'] if e['source_jo']=='7-8')
        self.assertEqual((broad['target_law'],broad['target_kind'],broad['cite_raw']),
                         ('대외경제협력기금법 시행령','law','「대외경제협력기금법」시행령'))

    def test_display_labels_do_not_become_legal_aliases(self):
        storage,catalog,kic=fixture();result=restore_forex(storage,catalog,kic)
        docs=result['laws']+result['administrative_rules']
        rule=next(d for d in docs if d['name']=='외국환거래규정')
        probe=article('9','제9조(검증) 화면용law 제1조를 읽는다.')
        refs=adapter(rule,probe,docs)
        self.assertFalse(any(r['target_name']=='외국환거래법' for r in refs))

    def test_unknown_or_misidentified_bok_provenance_is_rejected(self):
        for updates in ({'url':'https://www.bok.or.kr.evil.example/forged'},
                        {'authority':'다른 기관'}, {'name':'새로운 미확인 세칙'}):
            with self.subTest(updates=updates):
                storage,catalog,kic=fixture();catalog['laws'][-1].update(updates)
                with self.assertRaisesRegex(ValueError,'BOK source identity'):
                    restore_forex(storage,catalog,kic)

    def test_kic_addition_needs_two_verified_current_bodies(self):
        for update in ('future','unverified','missing','duplicate'):
            with self.subTest(update=update):
                storage,catalog,kic=fixture()
                if update=='future':kic['laws'][0]['effective']='20270101'
                elif update=='unverified':kic['laws'][0]['state']='scheduled'
                elif update=='duplicate':kic['laws'].append(deepcopy(kic['laws'][0]))
                else:kic['laws'].pop()
                with self.assertRaises(ValueError):restore_forex(storage,catalog,kic)
        storage,catalog,kic=fixture();result=restore_forex(storage,catalog,kic)
        additions=[d for d in result['laws'] if d['name'].startswith(KIC)]
        self.assertEqual(len(additions),2)
        self.assertTrue(all(d['category']=='forex' and d['sectors']==['entrusted'] for d in additions))
        self.assertTrue(all(a['sectors']==['entrusted'] for d in additions for a in d['articles']))

    def test_kic_edition_refresh_keeps_new_articles_in_entrusted_sector(self):
        storage, catalog, kic = fixture()
        restored = restore_forex(storage, catalog, kic)['laws']
        for fresh in kic['laws']:
            with self.subTest(name=fresh['name']):
                previous = next(d for d in restored if d['name'] == fresh['name'])
                updated = deepcopy(fresh)
                amended = article('2', '제2조(운용) 투자·대출·보증을 검토한다.')
                amended.pop('sectors')
                updated['articles'] = [amended]
                result = prepare_fresh(updated, previous, 'forex')
                self.assertEqual(result['sectors'], ['entrusted'])
                self.assertEqual(result['articles'][0]['sectors'], ['entrusted'])


if __name__=='__main__':unittest.main()
