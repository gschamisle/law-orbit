"""Build an offline-capable public viewer, using the existing citation engine.

Only normalized public-law fields are exported. No API calls, credentials,
user uploads or live Streamlit application are included in the site.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path
import shutil
from urllib.parse import urlparse

from core.citation_scope import Provision, parse_scope, scope_relation, _number
from core.galaxy_focus import analyze_focus, _target, _norm
from core.law_library import official_url
from core.law_abbrev import law as short_law
from core.law_galaxy import build as build_map
from core.domain_navigation import DOMAINS

ROOT=Path(__file__).resolve().parents[1]
WORK_DOMAINS=('public_institutions','customs','treasury')
PALETTE=['#80b4ff','#68dfc4','#bea2ff','#f0b77e','#ef96bb','#83d0ed','#cedc80','#ffa58e','#91a1ff']
LIMIT=24*1024*1024
FIELDS=('source_law','source_jo','source_title','source_ref','source_granularity','source_effective','source_url','target_law','target_ref','target_ref_recorded','target_url','target_effective','target_kind','target_status','target_provision_status','context','raw','cite_raw','reason','status','precision','direction','direction_label','neighbor_law','neighbor_jo','neighbor_ref','neighbor_kind','neighbor_title','kind','external','broad','source_start','source_end','evidence_id','annex_urls')


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def ident(domain,region,name):return hashlib.sha256((domain+'|'+region+'|'+name).encode()).hexdigest()[:20]
def safe_url(value):
    parsed=urlparse(str(value))
    if parsed.scheme not in ('http','https') or parsed.username or parsed.password:return ''
    if any(k in parsed.query.lower() for k in ('oc=','api_key=','token=')):return ''
    return str(value)

@lru_cache(maxsize=100000)
def parsed(raw,hyphen):return parse_scope(raw,allow_hyphen=hyphen)
def scopes(raw,hyphen):
    p=parsed(raw,hyphen)
    return dict(scopes=[[s.start.path,s.end.path,s.axis] for s in p.scopes],review_reason=p.review_reason)


class Writer:
    def __init__(self,dest):self.dest=dest;self.assets={}
    def data(self,value):
        raw=json.dumps(value,ensure_ascii=False,separators=(',',':')).encode()
        content=gzip.compress(raw,compresslevel=6,mtime=0)
        if len(content)>LIMIT:raise ValueError('Static asset exceeds 24 MiB; split the data further')
        checksum=hashlib.sha256(content).hexdigest();name='data/'+checksum+'.json.gz'
        path=self.dest/name;path.parent.mkdir(parents=True,exist_ok=True)
        if not path.exists():path.write_bytes(content)
        self.assets[name]=len(content)
        return dict(url=name,bytes=len(content),sha256=checksum)


class EdgeIndex:
    """Candidate narrowing only; final decisions remain analyze_focus decisions.

    Raw article ranges are indexed over collected articles, including branches
    omitted by older recorded target_ref values. Original edge order is retained.
    """
    def __init__(self,graph,documents):
        self.graph=graph;self.hyphen=graph.get('domain') in ('fsc','forex')
        self.forward=defaultdict(set);self.reverse=defaultdict(set);self.broad=defaultdict(set)
        known=defaultdict(set)
        for d in documents:
            for a in d.get('articles',[]):known[_norm(d['name'])].add(str(a['jo']))
        for i,e in enumerate(graph['edges']):
            self.forward[(_norm(e['source_law']),str(e['source_jo']))].add(i)
            target=_norm(e.get('target_law',''))
            if e.get('target_kind','article')=='law':self.broad[target].add(i);continue
            if e.get('target_kind','article')!='article':continue
            candidates=set()
            try:candidates.add(_target(e.get('target_ref',''),allow_hyphen=self.hyphen).jo)
            except ValueError:pass
            for scope in parsed(e.get('cite_raw',''),self.hyphen).scopes:
                if scope.axis==0:
                    candidates.update(jo for jo in known[target] if scope_relation(scope,Provision(jo),allow_hyphen=self.hyphen))
                elif scope.start.jo:candidates.add(scope.start.jo)
            for jo in candidates:self.reverse[(target,jo)].add(i)
    def focus(self,law,reference,*,broad=False):
        target=_target(reference,allow_hyphen=self.hyphen)
        indices=self.forward[(_norm(law),target.jo)]|self.reverse[(_norm(law),target.jo)]
        if broad:indices=indices|self.broad[_norm(law)]
        graph={**self.graph,'edges':[self.graph['edges'][i] for i in sorted(indices)]}
        return analyze_focus(law,reference,graph)


def tidy(row,ids,hyphen):
    out={k:row[k] for k in FIELDS if k in row}
    for key in ('source_url','target_url'):
        if key in out:out[key]=safe_url(out[key])
    if 'annex_urls' in out:out['annex_urls']=[safe_url(u) for u in out['annex_urls'] if safe_url(u)]
    out['source_id']=ids.get(row.get('source_law',''),'')
    out['target_id']=ids.get(row.get('target_law',''),'')
    out['neighbor_id']=ids.get(row.get('neighbor_law',''),'')
    out['raw_scope']=scopes(row.get('raw',row.get('cite_raw','')),hyphen)
    out['source_scope']=scopes(row.get('source_ref',''),hyphen)
    if row.get('direction')=='reverse':
        scope=parsed(row.get('raw',''),hyphen)
        try:recorded=_target(row.get('target_ref_recorded',''),allow_hyphen=hyphen)
        except ValueError:recorded=None
        out['record_review']=not scope.scopes or bool(recorded and not any(scope_relation(s,Provision(recorded.jo),allow_hyphen=hyphen) for s in scope.scopes))
    return out


def metadata(d,domain,region):
    return dict(id=ident(domain,region,d['name']),name=d['name'],label=d.get('display_name') or d.get('short_name') or short_law(d['name']),
        effective=d.get('effective',''),url=safe_url(official_url(d)),authority=d.get('managing_authority',''),
        kind=d.get('kind',''),sectors=d.get('sectors',[]),region=region,articles=len(d.get('articles',[])),
        analyzed=bool(d.get('articles')),status=d.get('body_status',''),domain=domain)


def overview(graph,domain,ids,catalog):
    data=build_map(graph=graph,include_external=domain=='tax',min_edge=8,max_articles_per_law=100)
    byname={d['name']:d for d in catalog}
    for node in data['nodes']:
        doc=byname.get(node['id'],{})
        if domain!='tax':node['color']=PALETTE[int(hashlib.sha256(node['family'].encode()).hexdigest()[:8],16)%len(PALETTE)]
        node.update(label=doc.get('label',node['label']),full_name=node['id'],web_law=ids.get(node['id'],''),web_jo='')
    colors={n['id']:n['color'] for n in data['nodes']}
    if domain=='ftc':
        data['dust']=[d for d in data['dust'] if d.get('jo') and d['jo']!='제조']
        for node in data['nodes']:
            d=byname.get(node['id'],{})
            node.update(category='ftc',title=d.get('authority','공정거래위원회')+' · 시행 '+d.get('effective',''))
    for point in data['dust']:point['c']=colors.get(point['law_id'],point['c'])
    data.update(domain=domain,galaxy_title=DOMAINS[domain])
    if domain in ('state_property','forex'):
        from importlib import import_module
        data=import_module('core.'+domain+'_layout').layout(data,graph)
    if domain in WORK_DOMAINS:
        from core.mofe_layout import layout
        data=layout(data,graph)
    return data


def export_documents(writer,domain,region,docs,graph,*,write_names=None,central_ids=None,national=None):
    ids={d['name']:ident(domain,region,d['name']) for d in docs}
    ids.update(central_ids or {})
    index=EdgeIndex(graph,docs);result=[]
    external=defaultdict(list);issues=defaultdict(list)
    text_forward=defaultdict(list);text_reverse=defaultdict(list)
    if domain=='ftc':
        from core.ftc_text_citations import reading_row
        for edge in graph.get('text_citations',[]):
            text_forward[edge['source_law']].append(tidy(reading_row(edge,'forward'),ids,False))
            if edge['target_status']=='collected' and edge['target_kind']=='article':
                jo=_target(edge['target_ref']).jo
                text_reverse[(edge['target_law'],jo)].append(tidy(reading_row(edge,'reverse'),ids,False))
    for e in graph.get('external_references',[]):external[(e['source_law'],str(e['source_jo']))].append(e)
    for e in graph.get('citation_issues',[])+graph.get('context_evidence',[]):issues[(e['source_law'],str(e['source_jo']))].append(e)
    if national is not None:
        region_names=set(write_names or [])
        for (norm_law,jo),indexes in index.reverse.items():
            law=next((n for n in (central_ids or {}) if _norm(n)==norm_law),None)
            if not law or not any(graph['edges'][i]['source_law'] in region_names for i in indexes):continue
            for row in index.focus(law,Provision(jo).label)['rows']:
                if row['direction']=='reverse' and row['source_law'] in region_names:
                    national[(law,jo)].append({**tidy(row,ids,index.hyphen),'national':True,'region':region})
    for d in docs:
        if write_names is not None and d['name'] not in write_names:continue
        entry=metadata(d,domain,region);entry['id']=ids[d['name']]
        if domain=='ftc' and d.get('text_analysis'):entry['text_analysis']=d['text_analysis']
        if domain=='forex':
            entry.update(source_notes=d.get('source_notes',[]),unparsed_provisions=d.get('unparsed_provisions',[]),
                         pdf_url=safe_url(d.get('pdf_url','')),article_sectors={a['jo']:a.get('sectors',[]) for a in d['articles']})
        if domain in WORK_DOMAINS:entry['article_sectors']={a['jo']:a.get('sectors',[]) for a in d['articles']}
        articles=[];parts=[];bucket={};bucket_articles=[];broad=[];inline={};small=len(d.get('articles',[]))<=24
        def flush():
            if not bucket:return
            if small:inline.update(bucket)
            else:
                ref=writer.data(bucket);parts.append(ref)
                for article in bucket_articles:article['detail']=ref
            bucket.clear();bucket_articles.clear()
        for a in d.get('articles',[]):
            jo=str(a['jo']);label=Provision(jo).label
            article=dict(jo=jo,label=label,title=a.get('title',''),text=a.get('text',''),deleted=bool(a.get('deleted')),effective=a.get('effective',d.get('effective','')))
            if domain=='forex' or domain in WORK_DOMAINS:article['sectors']=a.get('sectors',[])
            try:
                analyzed=index.focus(d['name'],label,broad=not articles)
                if not articles:broad=[tidy(r,ids,index.hyphen) for r in analyzed.get('broad_rows',[])]
                detail=dict(rows=[tidy(r,ids,index.hyphen) for r in analyzed['rows']],same_article_count=analyzed['same_article_count'],unplaced=analyzed['unplaced'])
            except ValueError:
                detail=dict(rows=[],analysis_error='이 조문 번호 형식의 연결은 미분석입니다.')
            detail['rows']+=text_reverse[(d['name'],jo)]
            detail['external']=[tidy(e,ids,index.hyphen) for e in external[(d['name'],jo)]]
            if 'analyzed_articles' in d and jo not in d['analyzed_articles']:
                detail['analysis_error']='이 조문은 국유재산 특례의 선택 분석 범위 밖입니다. 본문은 열람할 수 있으며, 표시된 역인용은 수집·분석한 출처 범위입니다.'
            detail['issues']=[{k:e[k] for k in ('raw','reason','kind','status') if k in e} for e in issues[(d['name'],jo)]]
            if national is not None and not region:detail['rows']+=national.get((d['name'],jo),[])
            bucket[jo]=detail;bucket_articles.append(article);articles.append(article)
            if len(bucket)>=24:flush()
        flush()
        # Do not claim an unstructured administrative text was analyzed.
        body=''
        if not articles and d.get('raw_body_blocks'):
            from core.fsc_administrative import body_text
            body=body_text(d['raw_body_blocks'])
        entry['parts']=parts
        extra={}
        if domain=='ftc' and d.get('text_analysis'):
            extra=dict(text_connections=text_forward[d['name']],text_issues=[i for i in graph.get('text_citation_issues',[]) if i['source_law']==d['name']])
        entry['file']=writer.data(dict(meta=entry,articles=articles,details=inline,broad=broad,unstructured_text=body,**extra))
        result.append(entry)
    return result,ids


def shell(dest):
    for p in (ROOT/'web').iterdir():
        if p.is_file():shutil.copy2(p,dest/p.name)
    shutil.copy2(ROOT/'docs/law-orbit-introduction.html',dest/'introduction.html')
    fonts=dest/'fonts';fonts.mkdir(exist_ok=True)
    for p in (ROOT/'ui/assets/fonts').iterdir():
        if p.suffix in ('.woff2','.txt'):shutil.copy2(p,fonts/p.name)
    html=(ROOT/'ui/assets/law_galaxy.html').read_text(encoding='utf-8').replace('__H__','730')
    html=html.replace('__SOUND__',(ROOT/'ui/assets/law_galaxy_sound.js').read_text(encoding='utf-8')).replace('__GESTURES__',(ROOT/'ui/assets/law_galaxy_gestures.js').read_text(encoding='utf-8'))
    html=html.replace("(()=>{'use strict';", "window.addEventListener('message',function init(event){if(event.source!==parent||event.origin!==location.origin||event.data?.type!=='galaxy-data')return;window.removeEventListener('message',init);const WEB_DATA=event.data.data;(()=>{'use strict';",1)
    html=html.replace('__DATA__','WEB_DATA')
    html=html.replace("function select(n){selected", "function select(n){if(n?.web_law)parent.postMessage({type:'galaxy-select',law:n.web_law,jo:n.web_jo||'',region:n.web_region||'',mode:D.mode},location.origin);selected",1)
    html=html.replace('})();\n</script>', '})();});\n</script>')
    prefix="<!doctype html><html lang='ko'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>법의 궤도 — 연결 지도</title><link rel='stylesheet' href='fonts.css'><style>body{margin:0;background:#051e22}#galaxy-wrap{border:0!important;border-radius:0!important;height:100vh!important;min-height:0!important}</style>"
    (dest/'renderer.html').write_text(prefix+html+'</html>',encoding='utf-8')


def build(source,dest):
    if dest.exists():raise ValueError('Choose a new empty destination; existing builds are preserved')
    dest.mkdir(parents=True);writer=Writer(dest);shell(dest)
    manifest=dict(schema=1,title='법의 궤도',domains=[])
    for domain,title in DOMAINS.items():
        if domain=='local_tax':
            from core.local_tax_graph import load_manifest,validate_bundle,merge_region
            folder,local=load_manifest(source/'output/local-tax-universe');base=validate_bundle(read(folder/'central.json'))
            central=base['source']['laws'];central_ids={d['name']:ident(domain,'',d['name']) for d in central}
            region_entries=[];national=defaultdict(list)
            for i,region in enumerate(local['regions']):
                item={k:region[k] for k in ('id','authority','province','inventory','indexed')}
                if region.get('file'):
                    shard=read(folder/region['file']);bundle=merge_region(base,shard)
                    names={d['name'] for d in shard['documents']}
                    entries,ids=export_documents(writer,domain,region['id'],bundle['source']['laws'],bundle['graph'],write_names=names,central_ids=central_ids,national=national)
                    item['catalog']=writer.data(dict(laws=entries,overview=writer.data(overview(bundle['graph'],domain,ids,entries))))
                region_entries.append(item)
                if (i+1)%20==0:print(f'local_tax: {i+1}/{len(local["regions"])} regions',flush=True)
            entries,ids=export_documents(writer,domain,'',central,base['graph'],national=national)
            catalog=dict(laws=entries,regions=region_entries,overview=writer.data(overview(base['graph'],domain,ids,entries)),coverage=local['coverage_note'],built_at=base['graph']['built_at'],sectors={'all':'중앙 법령·전국 역인용'})
            count=len(entries)+sum(r['indexed'] for r in region_entries)
        else:
            path=source/f'output/{domain}-universe/bundle.json'
            bundle=read(path)
            if domain=='tax':
                graph=bundle;src=bundle['source'];sectors={'all':'전체 국세'}
            else:
                if domain=='fsc':
                    from core.fsc_universe import validate_bundle
                    from core.fsc_sectors import SECTORS as sectors
                else:
                    import importlib
                    module=importlib.import_module('core.'+domain+'_universe');validate_bundle=module.validate_bundle;sectors=module.SECTORS
                validate_bundle(bundle);graph=bundle['graph'];src=bundle['source']
            docs=src['laws']+src.get('administrative_rules',[])
            # Keep the same no-unconnected-external-law overview as the tax app.
            entries,ids=export_documents(writer,domain,'',docs,graph)
            map_graph=graph
            if domain=='ftc':
                from core.ftc_universe import overview_graph
                map_graph=overview_graph(bundle)
            catalog=dict(laws=entries,overview=writer.data(overview(map_graph,domain,ids,entries)),coverage=graph.get('coverage_note','수집한 명시적 인용 범위입니다.'),built_at=graph['built_at'],sectors={'all':'전체 연결',**sectors})
            if domain=='state_property':catalog['special_cases']=writer.data(export_special_cases(src['special_cases'],ids))
            if domain in WORK_DOMAINS:catalog['workbench']=workbench(bundle,ids)
            count=len(entries)
        manifest['domains'].append(dict(id=domain,title=title,laws=count,catalog=writer.data(catalog),built_at=catalog['built_at']))
        print(domain+': exported '+str(count)+' documents',flush=True)
    from scripts.build_forex_finance_site import attach_bridge
    bridge_report=attach_bridge(dest,manifest,writer)
    manifest['version']=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()[:20]
    (dest/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    report=dict(version=manifest['version'],data_files=len(writer.assets),data_bytes=sum(writer.assets.values()),largest_asset=max(writer.assets.values()),domains=manifest['domains'],cross_domain=bridge_report)
    (dest.parent/(dest.name+'-report.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='domains'},indent=2),flush=True)
    return manifest


def workbench(bundle,ids):
    from core.mofe_universe import assessment
    result=assessment(bundle)
    if result['decision']=='hold':raise ValueError('업무 질문의 인용 근거 검증을 통과하지 못한 분야입니다.')
    result['cases']=[{**c,'law_id':ids[c['law']]} for c in result['cases'] if c['available']]
    return result


def export_special_cases(register,ids):
    from copy import deepcopy
    value=deepcopy(register)
    value['source_url']=safe_url(value['source_url'])
    value['annex_urls']=[safe_url(u) for u in value['annex_urls'] if safe_url(u)]
    for row in value['rows']:
        row['law_id']=ids.get(row['law'],'')
        for key in ('source_url','law_url'):
            if key in row:row[key]=safe_url(row[key])
        row['annex_urls']=[safe_url(u) for u in row['annex_urls'] if safe_url(u)]
    return value


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source-root',type=Path,required=True);p.add_argument('--destination',type=Path,required=True)
    a=p.parse_args();build(a.source_root.resolve(),a.destination.resolve())
