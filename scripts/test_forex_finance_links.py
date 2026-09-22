"""Cross-domain evidence, scope boundaries, edition safety and corpus isolation."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from core.forex_finance_links import bridge, make_edge, document
from core.citation_scope import Provision
from scripts.build_static_galaxies import ident, tidy, EdgeIndex, Writer
from scripts.build_forex_finance_site import payloads, attach_bridge, unpack


def fixture():
    snapshots={d:dict(entries=[],documents={},details={},built_at='20260921') for d in ('forex','fsc')}
    def add(domain,name,items):
        entry=dict(id=ident(domain,'',name),name=name,label=name,domain=domain,effective='20260901',
                   url='https://www.law.go.kr/',articles=len(items),sectors=['securities'],parts=[],file={})
        articles=[dict(jo=jo,label=Provision(jo).label,title='예시',text=text,effective='20260901') for jo,text in items]
        snap=snapshots[domain];snap['entries'].append(entry)
        snap['documents'][entry['id']]=dict(meta=entry.copy(),articles=articles)
        snap['details'][entry['id']]={a['jo']:dict(rows=[],external=[],issues=[]) for a in articles}
        return entry
    fx=add('forex','외환규정',[('7-36','제7-36조(예시) ① 금융투자업규정 제5-1조제6호에 따른다.'),
        ('8','제8조(범위) ① 「금융투자업규정」 제2조부터 제4조까지에 따른다.'),
        ('9','제9조(기준) ① 「은행업감독업무시행세칙」 <별표 4-1>에 따른다.'),
        ('10','제10조(정의) ① 「금융투자업규정」에 따른다.')])
    fin=add('fsc','금융투자업규정',[(jo,f'제{jo}조(예시) ① 내용') for jo in ('2','3','3의2','4','5-1')])
    add('fsc','은행업감독업무시행세칙',[('1','제1조(기준) ① 내용')])
    d=document(fx,snapshots['forex']['documents'][fx['id']])
    for a in d['articles']:
        detail=snapshots['forex']['details'][fx['id']][a['jo']]
        if a['jo']=='7-36':
            detail['issues']=[dict(raw='금융투자업규정 제5-1조제6호',reason='인용 법령·규정의 별칭 또는 상대 참조 미해결')]
        elif a['jo']=='8':
            raw='「금융투자업규정」 제2조부터 제4조까지';start=a['text'].index(raw)
            e=make_edge(d,a,dict(target_name=fin['name'],target_ref='제2조',raw=raw,start=start,end=start+len(raw)))
            detail['external']=[tidy(e,{},True)]
        elif a['jo']=='10':
            raw='「금융투자업규정」';start=a['text'].index(raw)
            e=make_edge(d,a,dict(target_name=fin['name'],target_ref='법령·정의 참조',raw=raw,start=start,end=start+len(raw),kind='law'))
            detail['external']=[tidy(e,{},True)]
    return snapshots,fx,fin


class BridgeTests(unittest.TestCase):
    def test_static_build_hook_keeps_original_domain_files_and_adds_reverse_links(self):
        s,fx,fin=fixture()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);writer=Writer(root);manifest=dict(domains=[])
            for domain,snap in s.items():
                for entry in snap['entries']:
                    packed=deepcopy(snap['documents'][entry['id']])
                    packed['details']=snap['details'][entry['id']]
                    entry['file']=writer.data(packed)
                catalog=writer.data(dict(laws=snap['entries'],built_at=snap['built_at']))
                manifest['domains'].append(dict(id=domain,catalog=catalog,built_at=snap['built_at']))
            original=deepcopy(manifest['domains'])
            files={p:p.read_bytes() for p in (root/'data').iterdir()}
            report=attach_bridge(root,manifest,writer)
            self.assertEqual(manifest['domains'],original)
            self.assertTrue(all(p.read_bytes()==raw for p,raw in files.items()))
            self.assertEqual(len(list((root/'data').iterdir())),len(files)+2)
            self.assertGreater(report['added_bytes'],0)
            reverse=unpack(root,manifest['cross_domain']['fsc'])['laws'][fin['id']]['5-1']['rows']
            self.assertEqual(reverse[0]['source_id'],fx['id'])
            self.assertEqual(reverse[0]['direction'],'reverse')
            with self.assertRaisesRegex(ValueError,'already has a bridge'):attach_bridge(root,manifest,writer)

    def test_recovers_exact_unquoted_title_without_mutation(self):
        s,fx,fin=fixture();original=deepcopy(s);result=bridge(s)
        self.assertEqual(s,original)
        hit=next(e for e in result['graph']['edges'] if e['source_jo']=='7-36')
        self.assertEqual((hit['target_law'],hit['target_ref']),(fin['name'],'제5-1조제6호'))
        self.assertEqual(hit['target_effective'],'20260901')
        p=payloads(result,s)
        self.assertTrue(p['forex']['laws'][fx['id']]['7-36']['rows'])
        self.assertTrue(p['fsc']['laws'][fin['id']]['5-1']['rows'])

    def test_range_includes_branch_and_whole_law_is_only_optional_reverse(self):
        s,fx,fin=fixture();r=bridge(s);idx=EdgeIndex(r['graph'],r['documents'])
        rows=idx.focus(fin['name'],'제3조의2')['rows']
        self.assertEqual([e['source_jo'] for e in rows],['8'])
        self.assertEqual([e['source_jo'] for e in idx.focus(fin['name'],'제3조의2',broad=True)['broad_rows']],['10'])
        self.assertFalse(idx.focus(fin['name'],'제5-1조제5호')['rows'])
        self.assertTrue(idx.focus(fin['name'],'제5-1조제6호')['rows'])

    def test_annex_is_a_reference_not_analyzed_text(self):
        s,fx,_=fixture();r=bridge(s)
        annex=next(e for e in r['graph']['edges'] if e['target_kind']=='annex')
        self.assertEqual(annex['target_ref'],'별표 4-1')
        self.assertEqual(annex['target_analysis'],'not-indexed')
        self.assertTrue(payloads(r,s)['forex']['laws'][fx['id']]['9']['rows'][0]['annex_unanalyzed'])

    def test_mismatched_edition_fails_closed(self):
        s,fx,_=fixture();s['forex']['documents'][fx['id']]['meta']['effective']='20250101'
        with self.assertRaisesRegex(ValueError,'edition mismatch'):bridge(s)

    def test_missing_target_not_replaced_and_unrelated_domains_rejected(self):
        s,fx,fin=fixture();s['fsc']['documents'][fin['id']]['articles'].pop()
        r=bridge(s)
        self.assertFalse(any(e['source_jo']=='7-36' for e in r['graph']['edges']))
        self.assertTrue(r['report']['rejected'])
        with self.assertRaises(ValueError):bridge({'tax':s['forex'],'fsc':s['fsc']})

    def test_tampered_evidence_fails_closed(self):
        s,fx,_=fixture();s['forex']['details'][fx['id']]['8']['external'][0]['cite_raw']='변조'
        with self.assertRaisesRegex(ValueError,'source edition differ'):bridge(s)

    def test_unknown_and_ambiguous_names_stay_unresolved(self):
        s,fx,fin=fixture();s['fsc']['entries'][0]['name']='다른규정';s['fsc']['documents'][fin['id']]['meta']['name']='다른규정'
        r=bridge(s);self.assertFalse(r['report']['recovered'])
        s,_,fin=fixture();s['fsc']['entries'].append(deepcopy(fin))
        with self.assertRaisesRegex(ValueError,'Ambiguous'):bridge(s)


if __name__=='__main__':unittest.main()
