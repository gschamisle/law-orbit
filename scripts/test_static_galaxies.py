"""Shared-engine parity, offline package boundaries and browser scope evaluation."""
from __future__ import annotations
import gzip,json,os,random,shutil,subprocess,tempfile,unittest
from collections import defaultdict
from pathlib import Path
from scripts.build_static_galaxies import EdgeIndex,Writer,tidy,ident,export_documents
from core.galaxy_focus import analyze_focus,visible_rows
from core.citation_scope import Provision

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(os.environ.get('STATIC_SOURCE_ROOT',str(ROOT)))
NODE=shutil.which('node') or (r'C:\Program Files\nodejs\node.exe' if os.name=='nt' else 'node')


def edge(law,jo,dest,ref,raw,**kw):
    return dict(source_law=law,source_jo=jo,source_title='fixture',source_ref=f'제{jo}조제2항',source_granularity='block',source_start=kw.pop('source_start',0),source_end=len(raw),target_law=dest,target_ref=ref,cite_raw=raw,type='direct',target_kind='article',**kw)


def fixtures():
    docs=[dict(name='A법',articles=[dict(jo=jo,title='조문',text='공개 본문') for jo in ('2','3','3의2','4')]),dict(name='B법',articles=[dict(jo='5',title='인용',text='공개 본문')])]
    edges=[edge('B법','5','A법','제2조','제2조부터 제4조까지'),edge('B법','5','A법','제3조','제3조제1항부터 제3항까지',source_start=20),edge('B법','5','A법','제3조','제3조제1항',source_start=40,context_review=True),edge('B법','5','A법','제4조','제2조',source_start=70)]
    g=dict(laws=['A법','B법'],focus_laws=['A법','B법'],catalog=[],edges=edges,built_at='20260919')
    return docs,g


def key(row):return [row['direction'],row['source_law'],row.get('source_start'),row.get('raw'),row.get('target_ref_recorded'),row['status']]


def browser(cases):
    code="""import {readFileSync} from 'node:fs';import {target,refine} from './web/query.mjs';const cases=JSON.parse(readFileSync(0,'utf8'));console.log(JSON.stringify(cases.map(c=>refine(c.rows,target(c.reference,c.hyphen),{broad:true}).map(r=>[r.direction,r.source_law,r.source_start??null,r.raw,r.target_ref_recorded??null,r.status]))));"""
    result=subprocess.run([NODE,'--input-type=module','-e',code],input=json.dumps(cases,ensure_ascii=False),text=True,encoding='utf-8',capture_output=True,cwd=ROOT,timeout=120)
    if result.returncode:raise AssertionError(result.stderr)
    return json.loads(result.stdout)


class StaticTests(unittest.TestCase):
    def test_range_includes_branch_articles_and_matches_shared_engine(self):
        docs,g=fixtures();idx=EdgeIndex(g,docs)
        for ref in ('제2조','제3조','제3조의2','제4조','제3조제2항','제3조제4항'):
            self.assertEqual(idx.focus('A법',ref)['rows'],analyze_focus('A법',ref,g)['rows'])
        self.assertTrue(idx.focus('A법','제3조의2')['rows'])

    def test_browser_scope_matches_python_context_ranges_and_forward_sources(self):
        docs,g=fixtures();cases=[];expected=[]
        for law,refs in [('A법',['제3조','제3조제2항','제3조제4항','제4조제1항']),('B법',['제5조','제5조제1항','제5조제2항'])]:
            for ref in refs:
                jo=ref.split('조')[0]+'조'
                base=analyze_focus(law,jo,g)
                cases.append(dict(rows=[tidy(r,{},False) for r in base['rows']],reference=ref,hyphen=False))
                expected.append(sorted([key(r) for r in analyze_focus(law,ref,g)['rows']],key=str))
        actual=browser(cases)
        for case,a,b in zip(cases,actual,expected):self.assertEqual(sorted(a,key=str),b,case['reference'])

    def test_small_documents_inline_their_details_and_have_stable_ids(self):
        docs,g=fixtures()
        with tempfile.TemporaryDirectory() as tmp:
            writer=Writer(Path(tmp));catalog,ids=export_documents(writer,'tax','',docs,g)
            packed=json.loads(gzip.decompress((Path(tmp)/catalog[0]['file']['url']).read_bytes()))
            self.assertEqual(len(packed['details']),4)
            self.assertFalse(catalog[0]['parts'])
            self.assertNotIn('detail',packed['articles'][0])
            self.assertEqual(ids['A법'],ident('tax','','A법'))
            self.assertNotEqual(ident('local_tax','region1','조례'),ident('local_tax','region2','조례'))

    def test_regional_reverse_links_keep_jurisdiction_ids(self):
        docs,g=fixtures();national=defaultdict(list)
        central_ids={'A법':ident('local_tax','','A법')}
        with tempfile.TemporaryDirectory() as tmp:
            writer=Writer(Path(tmp))
            for region in ('region1','region2'):
                export_documents(writer,'local_tax',region,docs,g,write_names={'B법'},central_ids=central_ids,national=national)
            rows=national[('A법','3')]
            self.assertEqual({r['neighbor_id'] for r in rows},{ident('local_tax',r,'B법') for r in ('region1','region2')})
            self.assertTrue(all(r['national'] and r['target_id']==central_ids['A법'] for r in rows))
            self.assertEqual({r['region'] for r in rows},{'region1','region2'})

    def test_download_exports_only_public_law_fields(self):
        docs,g=fixtures();docs[0]['api_key']='must-not-export';docs[0]['raw_api_response']='private';docs[0]['source_url']='https://law.go.kr/?OC=private'
        with tempfile.TemporaryDirectory() as tmp:
            writer=Writer(Path(tmp));catalog,_=export_documents(writer,'tax','',docs,g)
            raw=gzip.decompress((Path(tmp)/catalog[0]['file']['url']).read_bytes()).decode()
            self.assertNotIn('must-not-export',raw);self.assertNotIn('raw_api_response',raw);self.assertNotIn('OC=private',raw)

    @unittest.skipUnless((SOURCE/'output/tax-universe/bundle.json').exists(),'Requires collected source corpus')
    def test_real_corpora_match_shared_engine_and_browser(self):
        cases=[];expected=[]
        for domain in ('tax','fsc','procurement','housing','environment'):
            b=json.loads((SOURCE/f'output/{domain}-universe/bundle.json').read_text(encoding='utf-8'));g=b.get('graph',b);source=b['source'];docs=source['laws']+source.get('administrative_rules',[]);index=EdgeIndex(g,docs)
            choices=[(d['name'],str(a['jo'])) for d in docs for a in d.get('articles',[]) if str(a['jo']).replace('의','').replace('-','').isdigit()]
            sample=random.Random(19).sample(choices,min(12,len(choices)))
            sample += [('법인세법','16')] if domain=='tax' else [('보험업감독규정','7-1')] if domain=='fsc' else []
            for law,jo in sample:
                for suffix in ('','제1항','제2항제1호'):
                    ref=Provision(jo).label+suffix
                    try:full=analyze_focus(law,ref,g);part=index.focus(law,ref)
                    except ValueError:continue
                    self.assertEqual(part['rows'],full['rows'],(domain,law,ref))
                    base=index.focus(law,Provision(jo).label)
                    cases.append(dict(rows=[tidy(r,{},domain=='fsc') for r in base['rows']],reference=ref,hyphen=domain=='fsc'))
                    expected.append(sorted([key(r) for r in full['rows']],key=str))
        for case,actual,want in zip(cases,browser(cases),expected):self.assertEqual(sorted(actual,key=str),want,case['reference'])


if __name__=='__main__':unittest.main()
