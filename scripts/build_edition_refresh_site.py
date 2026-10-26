"""Refresh reviewed public editions without reparsing unrelated evidence.

Stable reader IDs survive official title changes. Original quoted text is never
rewritten. Only changed sources are parsed; unchanged bodies and attachments are
copied, while reverse citations and version-bound bridges are regenerated.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from core.citation_scope import Provision
from core.fsc_administrative import adapter, index_rule, provision_blocks
from core.galaxy_focus import _target
from core.universe_builder import build_universe
from scripts.build_static_galaxies import Writer, EdgeIndex, tidy, shell, WORK_DOMAINS
from scripts.static_storage import Storage
from scripts.build_procurement_pdf_site import materialize_reachable
from scripts.compact_static_galaxies import convert


def load_details(storage, entry, document):
    result=deepcopy(document.get('details',{}))
    for ref in entry.get('parts',[]): result.update(storage.read(ref))
    return result


def provider(entry):
    url=entry.get('url','').lower()
    return 'ordin' if 'ordin' in url or '자치법규' in url else 'admrul' if 'admrul' in url or '행정규칙' in url else 'eflaw'


def source_document(entry, document, domain, nodes):
    articles=[{k:deepcopy(v) for k,v in a.items() if k!='detail'} for a in document['articles']]
    for a in articles:
        a['blocks']=provision_blocks(a['text'],a['jo'])
    category=domain
    if domain=='tax': category=nodes.get(entry['name'],{}).get('category','external')
    d=dict(name=entry['name'],short_name=entry.get('label',''),effective=entry['effective'],
           source_url=entry['url'],category=category,family=entry['name'],provider=provider(entry),
           managing_authority=entry.get('authority',''),kind=entry.get('kind',''),articles=articles,
           sectors=entry.get('sectors',[]),annexes=deepcopy(document.get('annexes',[])))
    if document.get('unstructured_text'): d['raw_body_blocks']=[document['unstructured_text']]
    return d


def prepare_fresh(fresh, old_source, domain):
    d=deepcopy(fresh)
    d.update(category=old_source['category'],family=old_source.get('family',fresh['name']))
    d.setdefault('provider',old_source['provider'])
    d.setdefault('source_url',old_source['source_url'])
    if d['provider']=='admrul': d=index_rule(d)
    d.setdefault('articles',[]);d.setdefault('annexes',[])
    d['sectors']=deepcopy(old_source.get('sectors',[]))
    if domain in WORK_DOMAINS:
        from core.mofe_collection import prepare_source
        src=prepare_source(dict(domain=domain,laws=[d] if d['provider']!='admrul' else [],
                                administrative_rules=[d] if d['provider']=='admrul' else []))
        d=(src['laws']+src['administrative_rules'])[0]
    elif domain=='local_tax':
        from core.local_tax_graph import prepare_document
        d=prepare_document(d)
    for a in d['articles']:
        a.setdefault('title','');a.setdefault('blocks',provision_blocks(a['text'],a['jo']))
    # Analyses are tied to attachment bytes and cannot be carried to a new edition.
    for a in d['annexes']:
        a.pop('body_analysis',None);a.pop('analysis',None);a.pop('connections',None)
    return d


def edge_from_row(row):
    edge=deepcopy(row)
    edge['target_ref']=row.get('target_ref_recorded') or row.get('target_ref','')
    edge['cite_raw']=row.get('cite_raw') or row.get('raw','')
    edge['context_review']=row.get('status')=='review' and row.get('target_kind','article')=='article'
    edge.setdefault('type','direct')
    return edge


def edge_key(row):
    return (row.get('source_law'),str(row.get('source_jo')),row.get('source_start'),row.get('source_end'),
            row.get('target_law'),row.get('target_ref_recorded') or row.get('target_ref'),row.get('cite_raw',row.get('raw','')))


def mapped_row(row, renames, changed_targets, ids):
    result=deepcopy(row)
    for key in ('source_law','target_law','neighbor_law'):
        if result.get(key) in renames: result[key]=renames[result[key]]
    target=changed_targets.get(result.get('target_law'))
    if target:
        result['target_effective']=target['effective'];result['target_url']=target['source_url']
        if result.get('target_kind')=='article':
            try: jo=_target(result.get('target_ref_recorded') or result['target_ref'],allow_hyphen=True).jo
            except ValueError: jo=''
            if jo and jo not in {a['jo'] for a in target['articles']}:
                result['target_provision_status']='not-found-in-collected-edition'
                result['target_reference_note']='인용된 조문 번호를 갱신한 수집 판본에서 찾지 못했습니다. 삭제·이동 여부를 공식 원문에서 확인하세요.'
    for side in ('source','target','neighbor'):
        name=result.get(side+'_law')
        if name in ids: result[side+'_id']=ids[name]
    return result


def store_document(writer, entry, document, details):
    entry=deepcopy(entry);doc=deepcopy(document)
    doc['details']={};parts=[]
    for a in doc['articles']: a.pop('detail',None)
    if len(doc['articles'])<=24:
        doc['details']={a['jo']:details[a['jo']] for a in doc['articles']}
    else:
        size=96 if entry.get('domain')=='ftc' else 24
        for start in range(0,len(doc['articles']),size):
            group=doc['articles'][start:start+size]
            ref=writer.data({a['jo']:details[a['jo']] for a in group});parts.append(ref)
            for a in group:a['detail']=ref
    entry['parts']=parts;entry['articles']=len(doc['articles']);entry['analyzed']=bool(doc['articles'])
    doc['meta']={k:deepcopy(v) for k,v in entry.items() if k!='file'}
    entry['file']=writer.data(doc)
    return entry


def overview_overlay(old, graph, changed, renames, entries, as_of):
    """Retain reviewed layout and untouched source counts; replace outgoing links."""
    value=deepcopy(old);byname={e['name']:e for e in entries};changed_new={renames.get(n,n) for n in changed}
    pair=Counter((e['source_law'],e['target_law']) for e in graph['edges']
                 if e['source_law']!=e['target_law'])
    value['all_links']=[{**l,'a':renames.get(l['a'],l['a']),'b':renames.get(l['b'],l['b'])}
                        for l in value.get('all_links',[]) if l['a'] not in changed]
    value['all_links'] += [dict(a=a,b=b,n=n) for (a,b),n in sorted(pair.items()) if a in changed_new and a in byname and b in byname]
    counts=Counter(e['source_law'] for e in graph['edges'])
    for node in value['nodes']:
        oldname=node['id'];name=renames.get(oldname,oldname);node['id']=name
        if node.get('full_name')==oldname:node['full_name']=name
        if name in byname:
            e=byname[name];node.update(web_law=e['id'],label=e['label'])
            if oldname in changed:
                node['count']=counts[name]
                node['title']=e.get('authority','')+' · 시행 '+e['effective']
    nodes={n['id']:n for n in value['nodes']}
    # Do not erase original map style, color or sector-specific positioning.
    value['links']=[deepcopy(l) for l in value['all_links'] if l['n']>=8 and
                    nodes.get(l['a'],{}).get('family')!=nodes.get(l['b'],{}).get('family')]
    if old.get('links')==old.get('all_links'):value['links']=deepcopy(value['all_links'])
    known={d['name']:{a['jo'] for a in d.get('articles',[])} for d in graph.get('source_documents',[])}
    dust=[]
    for point in value.get('dust',[]):
        oldname=point['law_id'];name=renames.get(oldname,oldname)
        if oldname in changed:
            try: jo=_target(point['jo'],allow_hyphen=True).jo
            except ValueError: jo=str(point['jo'])
            if jo not in known.get(name,set()):continue
        point['law_id']=name
        if name in byname:point['law']=byname[name]['label']
        dust.append(point)
    value['dust']=dust;value['built_at']=as_of
    return value



def apply_reviewed_corrections(graph, corpus, corrections):
    from scripts.build_citation_context_site import edge_id, corrected_edge
    documents={d['name']:d for d in corpus}
    entries={d['name']:dict(name=d['name'],effective=d['effective'],url=d['source_url']) for d in corpus}
    for item in corrections:
        if item['domain']!=graph['domain']:continue
        document=documents[item['law']]
        article=next(a for a in document['articles'] if a['jo']==item['jo'])
        if document['effective']!=item['effective'] or hashlib.sha256(article['text'].encode()).hexdigest()!=item['source_sha256']:
            raise ValueError('Reviewed citation correction source changed')
        prior=item['before']
        if article['text'][prior['start']:prior['end']]!=prior['raw']:raise ValueError('Reviewed citation quote changed')
        oldid=edge_id(item['law'],item['jo'],prior)
        candidates=graph['edges']+graph['external_references']
        old=next((e for e in candidates if e['evidence_id']==oldid),None)
        if old is None:
            if not all(any(e['evidence_id']==edge_id(item['law'],item['jo'],c) for e in candidates) for c in item['after']):
                raise ValueError('Reviewed citation correction no longer matches parser evidence')
            continue
        for key in ('edges','external_references'):graph[key]=[e for e in graph[key] if e['evidence_id']!=oldid]
        existing={e['evidence_id'] for e in graph['edges']+graph['external_references']}
        for citation in item['after']:
            if (citation['start'],citation['end'],citation['raw'])!=(prior['start'],prior['end'],prior['raw']):
                raise ValueError('Correction cannot alter quoted source text')
            edge=corrected_edge(old,citation,entries)
            if edge['evidence_id'] not in existing:
                graph['edges' if edge['target_law'] in documents else 'external_references'].append(edge)
                existing.add(edge['evidence_id'])


def refresh_catalog(storage, catalog, domain, replacements, writer, as_of, context_entries=(), context_documents=None, reviewed_corrections=()):
    entries=deepcopy(catalog['laws']);documents={e['id']:storage.read(e['file']) for e in entries}
    details={e['id']:load_details(storage,e,documents[e['id']]) for e in entries}
    all_entries=entries+list(context_entries);all_docs={**(context_documents or {}),**documents}
    old_overview=storage.read(catalog['overview']);nodes={n['id']:n for n in old_overview['nodes']}
    sources={e['id']:source_document(e,all_docs[e['id']],domain,nodes) for e in all_entries}
    selected={};renames={};edition_old=set();report=[]
    for row in replacements:
        if row.get('validation',{}).get('status')!='verified':raise ValueError('Unverified replacement')
        finding=row['finding']
        matches=[e for e in entries if e['name']==finding['name'] and e['effective']==finding['effective'] and e['url']==finding['url']]
        if len(matches)!=1:raise ValueError('Replacement does not match exactly one public edition: '+finding['name'])
        e=matches[0];fresh=row['fresh_document'];kind=row['change_kind']
        if fresh['effective']>as_of.replace('-','') or fresh['effective']=='99991231':raise ValueError('Unconfirmed or future edition')
        selected[e['id']]=row
        if fresh['name']!=e['name']:renames[e['name']]=fresh['name']
        if kind=='edition':
            edition_old.add(e['name']);sources[e['id']]=prepare_fresh(fresh,sources[e['id']],domain)
        else:
            sources[e['id']]['name']=fresh['name']
        report.append(dict(id=e['id'],name=fresh['name'],old_name=e['name'],kind=kind,
                           previous=e['effective'],effective=fresh['effective']))
    ids={s['name']:i for i,s in sources.items()};edition_new={renames.get(n,n) for n in edition_old}
    changed_targets={sources[i]['name']:sources[i] for i in selected}
    corpus=list(sources.values())
    selected_adapter=adapter
    if domain=='local_tax':
        from core.local_tax_graph import ordinance_adapter
        selected_adapter=ordinance_adapter
    elif domain=='constitution':
        from core.constitution_relations import adapter as selected_adapter
    if domain=='local_tax':
        from core.local_tax_graph import prepare_document
        corpus=[prepare_document(d) for d in corpus]
    graph=build_universe(dict(laws=corpus,built_at=as_of),focus_categories=('tax' if domain=='tax' else domain,),
                         preserve_external=True,article_adapter=selected_adapter,source_names=edition_new,
                         tax_reference_context=domain=='tax')
    graph.update(domain=domain,source_documents=corpus)
    apply_reviewed_corrections(graph,corpus,[r for r in reviewed_corrections if r['law'] in edition_new])
    # Respect the existing selective scope for property special-case legislation.
    if domain=='state_property':
        limited={sources[i]['name']:{jo for jo,d in details[i].items() if not d.get('analysis_error')}
                 for i in selected if any(d.get('analysis_error') for d in details[i].values())}
        core={e['name'] for e in entries if 'core' in e.get('sectors',[])}
        for edge in graph['edges']:
            if edge['source_law'] in limited and edge['target_law'] in core:limited[edge['source_law']].add(edge['source_jo'])
        for key in ('edges','external_references','context_evidence'):
            graph[key]=[e for e in graph.get(key,[]) if e['source_law'] not in limited or e['source_jo'] in limited[e['source_law']]]
    for edge in graph['edges']+graph['external_references']:
        d=next(d for d in corpus if d['name']==edge['source_law'])
        edge['source_url']=d['source_url']
        target=next((d for d in corpus if d['name']==edge['target_law']),None)
        if target:edge['target_url']=target['source_url']
    # Old incoming references remain evidence of the unchanged source. Re-index
    # them over new target articles, including branch articles inside ranges.
    incoming={}
    for e in all_entries:
        old=all_docs[e['id']]
        det=details.get(e['id']) or load_details(storage,e,old)
        for row in [r for d in det.values() for r in d.get('rows',[])]+old.get('text_connections',[]):
            if row.get('source_law') not in edition_old and row.get('target_law') in edition_old:
                r=mapped_row(row,renames,changed_targets,ids)
                incoming.setdefault(edge_key(r),edge_from_row(r))
    # Metadata-only title corrections retain quoted source text and prior statuses.
    fresh_index=EdgeIndex(graph,corpus)
    incoming_graph={**graph,'edges':list(incoming.values())};incoming_index=EdgeIndex(incoming_graph,corpus)
    external=defaultdict(list);issues=defaultdict(list)
    for r in graph['external_references']:external[(r['source_law'],str(r['source_jo']))].append(tidy(r,ids,fresh_index.hyphen))
    for d in corpus:
        if d['name'] not in edition_new:continue
        for a in d['articles']:
            issues[(d['name'],a['jo'])].extend({k:x[k] for k in ('raw','reason','kind','status') if k in x} for x in a.get('citation_issues',[]))
    for x in graph.get('context_evidence',[]):
        issues[(x['source_law'],str(x['source_jo']))].append({k:x[k] for k in ('raw','reason','kind','status') if k in x})
    context_reverse={};result=[]
    for e in all_entries:
        ident=e['id'];old=all_docs[ident];src=sources[ident];is_context=ident not in documents
        if is_context:
            central={}
            for a in old['articles']:
                rows=[tidy(r,ids,fresh_index.hyphen) for r in fresh_index.focus(src['name'],a['label'])['rows'] if r['direction']=='reverse']
                if rows:central[a['jo']]=rows
            if central:context_reverse[ident]=central
            continue
        doc=deepcopy(old);new_e=deepcopy(e);new_details={}
        replacement=selected.get(ident)
        changed=bool(replacement and replacement['change_kind']=='edition')
        if replacement:
            new_e.update(name=src['name'],effective=src['effective'],url=src['source_url'])
            if src['name']!=e['name']:
                new_e['label']=src.get('display_name') or src['name']
                new_e['former_names']=list(dict.fromkeys(e.get('former_names',[])+[e['name']]))
            new_e['edition_checked_at']=as_of
        if changed:
            new_e.update(status=src.get('body_status',''),sectors=src.get('sectors',e.get('sectors',[])))
            doc['articles']=[{k:deepcopy(a[k]) for k in ('jo','title','text','effective','deleted','reference_notes','sectors') if k in a} for a in src['articles']]
            for a in doc['articles']:
                a['label']=Provision(a['jo']).label;a.setdefault('deleted',False);a.setdefault('effective',src['effective'])
            if 'article_sectors' in new_e:new_e['article_sectors']={a['jo']:a.get('sectors',[]) for a in src['articles']}
            from core.fsc_administrative import body_text
            doc['unstructured_text']=body_text(src.get('raw_body_blocks',[])) if not src['articles'] else ''
            doc['annexes']=[dict(ref=a['ref'],title=a.get('title',''),effective=a.get('effective',''),urls=a.get('urls',[]),status='not-analyzed',connections=[],issues=[]) for a in src.get('annexes',[])]
            for key in ('pdf_analysis','text_analysis','text_connections','text_issues','internal_links'):
                doc.pop(key,None);new_e.pop(key,None)
        for a in doc['articles']:
            jo=a['jo'];prior=details[ident].get(jo,{})
            parsed=fresh_index.focus(src['name'],a['label'])
            newrows=[tidy(r,ids,fresh_index.hyphen) for r in parsed['rows']]
            if changed:
                inc=incoming_index.focus(src['name'],a['label'])
                # Keep already reviewed incoming evidence at surviving numbers,
                # including PDF/table/text locators that are not legal articles.
                # The numbered index only supplements newly introduced targets.
                prior_incoming=[mapped_row(r,renames,changed_targets,ids) for r in prior.get('rows',[])
                                if r.get('direction')=='reverse' and r.get('source_law') not in edition_old]
                seen_incoming={edge_key(r) for r in prior_incoming}
                newrows += prior_incoming
                newrows += [tidy(r,ids,fresh_index.hyphen) for r in inc['rows']
                            if r['direction']=='reverse' and edge_key(r) not in seen_incoming]
                detail=dict(rows=newrows,same_article_count=parsed['same_article_count'],unplaced=parsed['unplaced'],
                            external=external[(src['name'],jo)],issues=issues[(src['name'],jo)])
                if domain=='state_property' and src['name'] in limited and jo not in limited[src['name']]:
                    detail['analysis_error']=next(d['analysis_error'] for d in details[ident].values() if d.get('analysis_error'))
            else:
                detail=deepcopy(prior)
                detail['rows']=[mapped_row(r,renames,changed_targets,ids) for r in prior.get('rows',[]) if r.get('source_law') not in edition_old]+newrows
                detail['external']=[mapped_row(r,renames,changed_targets,ids) for r in prior.get('external',[])]
            new_details[jo]=detail
        parsed_broad=fresh_index.focus(src['name'],doc['articles'][0]['label'],broad=True)['broad_rows'] if doc['articles'] else []
        doc['broad']=[mapped_row(r,renames,changed_targets,ids) for r in old.get('broad',[]) if r.get('source_law') not in edition_old]+[tidy(r,ids,fresh_index.hyphen) for r in parsed_broad]
        if not changed:
            for key in ('text_connections',):
                if key in doc:doc[key]=[mapped_row(r,renames,changed_targets,ids) for r in doc[key] if r.get('source_law') not in edition_old]
            for annex in doc.get('annexes',[]):
                if 'connections' in annex:annex['connections']=[mapped_row(r,renames,changed_targets,ids) for r in annex['connections'] if r.get('source_law') not in edition_old]
        result.append(store_document(writer,new_e,doc,new_details))
    value=deepcopy(catalog);value['laws']=result
    value['overview']=writer.data(overview_overlay(old_overview,graph,edition_old,renames,result+list(context_entries),as_of))
    value['edition_updates']=dict(checked_at=as_of,documents=report,
        note='표시된 법령의 판본·명칭을 개별 갱신했습니다. 다른 법령과 별표 본문은 기존 수집 자료를 유지합니다.')
    value['built_at']=as_of
    return value,report,context_reverse


def matches(entry,row):
    f=row['finding'];return entry['name']==f['name'] and entry['url']==f['url'] and entry['effective']==f['effective']


def validate_approved_sources(plan):
    """Bind each collected body to its recorded hash and pinned identity.

    The enclosing plan hash records the build input; it cannot establish that
    a body still matches the earlier collection verification on its own.
    """
    from core.edition_watch import valid_day
    checked = 0
    for row in plan['rows']:
        fresh = row['fresh_document']; validation = row.get('validation', {})
        if validation.get('status') != 'verified':
            raise ValueError('Unverified replacement')
        actual_hash = hashlib.sha256(json.dumps(fresh, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        if validation.get('fresh_document_sha256') != actual_hash:
            raise ValueError('Collected fresh document checksum mismatch')
        actual = [fresh.get('provider', 'eflaw'),
                  str(fresh.get('document_id') or fresh.get('law_id') or ''),
                  str(fresh.get('version_id') or fresh.get('mst') or ''),
                  str(fresh.get('effective', ''))]
        finding = row['finding']; recorded = row.get('identity', {})
        expected = [recorded.get('provider'), str(recorded.get('stable_id', '')),
                    str(recorded.get('new_serial', '')), str(recorded.get('new_effective', ''))]
        current = finding.get('current', {})
        pinned = [current.get('provider'), str(current.get('stable_id', '')),
                  str(current.get('serial', '')), str(current.get('effective', ''))]
        if (not all(actual) or actual != validation.get('expected_identity') or actual != expected
                or actual != pinned or actual[:2] != [finding.get('provider'), str(finding.get('stable_id', ''))]
                or not valid_day(actual[3])):
            raise ValueError('Collected fresh document identity mismatch')
        checked += 1
    return checked


def build(base,sources_path,destination,validate_site=True):
    base=Path(base).resolve();destination=Path(destination).resolve();sources_path=Path(sources_path)
    stage=destination.with_name(destination.name+'-unpacked')
    if destination.exists() or stage.exists():raise ValueError('Use a new destination')
    raw=(base/'manifest.json').read_bytes();original=json.loads(raw);plan_raw=sources_path.read_bytes();plan=json.loads(plan_raw)
    if plan['base_data_version']!=original['version']:raise ValueError('Wrong base data version')
    if plan.get('base_manifest_sha256') and plan['base_manifest_sha256']!=hashlib.sha256(raw).hexdigest():raise ValueError('Wrong base manifest hash')
    validate_approved_sources(plan)
    as_of=plan['as_of'];as_of=as_of[:4]+'-'+as_of[4:6]+'-'+as_of[6:] if '-' not in as_of else as_of
    manifest=deepcopy(original);manifest.pop('data_packs',None);storage=Storage(base)
    stage.mkdir(parents=True);shell(stage);writer=Writer(stage);changed_domains=set();applied=[]
    for domain in manifest['domains']:
        name=domain['id'];catalog=storage.read(domain['catalog']);rows=[r for r in plan['rows'] if name in r['finding']['domains']]
        if not rows:continue
        central_docs={e['id']:storage.read(e['file']) for e in catalog['laws']} if name=='local_tax' else {}
        direct=[r for r in rows if any(matches(e,r) for e in catalog['laws'])]
        if direct:
            catalog,report,_=refresh_catalog(storage,catalog,name,direct,writer,as_of,reviewed_corrections=plan.get('reviewed_citation_corrections',[]))
            applied.extend({**r,'domain':name,'region':''} for r in report)
        if name=='local_tax':
            if direct:raise ValueError('Central local-tax edition refresh needs a full jurisdiction review')
            national={};removed_ids=set();regional_reports=[];regional_names={};regional_ids={}
            for region in catalog['regions']:
                if not region.get('catalog'):continue
                local=storage.read(region['catalog']);found=[r for r in rows if any(matches(e,r) for e in local['laws'])]
                if not found:continue
                local,report,reverse=refresh_catalog(storage,local,name,found,writer,as_of,
                                                     context_entries=catalog['laws'],context_documents=central_docs)
                removed_ids.update(r['id'] for r in report if r['kind']=='edition')
                regional_reports.extend(report)
                regional_names.update({r['old_name']:r['name'] for r in report if r['old_name']!=r['name']})
                regional_ids.update({r['name']:r['id'] for r in report})
                for ident,details in reverse.items():
                    for jo,items in details.items():national.setdefault((ident,jo),[]).extend({**r,'national':True,'region':region['id']} for r in items)
                region['catalog']=writer.data(local)
                applied.extend({**r,'domain':name,'region':region['id']} for r in report)
            # Nationwide incoming index lives in central document shards.
            central=[]
            for e in catalog['laws']:
                doc=central_docs[e['id']];details=load_details(storage,e,doc)
                for jo,detail in details.items():
                    detail['rows']=[mapped_row(r,regional_names,{},regional_ids) for r in detail.get('rows',[]) if not (r.get('national') and r.get('source_id') in removed_ids)]+national.get((e['id'],jo),[])
                central.append(store_document(writer,e,doc,details))
            catalog['laws']=central;catalog['built_at']=as_of
            catalog['edition_updates']=dict(checked_at=as_of,documents=regional_reports,note='표시된 지역별 판본·명칭만 갱신했습니다. 전국의 모든 조례를 최신 판본으로 교체한 것은 아닙니다.')
        domain['catalog']=writer.data(catalog);domain['built_at']=as_of;changed_domains.add(name)
        print('Refreshed',name,flush=True)
    # Surface unresolved official-source conflicts without replacing their bodies.
    notices=plan.get('public_notices',{})
    for domain in manifest['domains']:
        if domain['id'] not in notices:continue
        ref=domain['catalog'];cat=Storage(stage).read(ref) if (stage/ref['url']).exists() else storage.read(ref)
        cat['coverage']=cat.get('coverage','')+notices[domain['id']]
        domain['catalog']=writer.data(cat)
    expected={(r['finding']['key'],d) for r in plan['rows'] for d in r['finding']['domains']}
    if len(applied)!=len(expected):raise ValueError('Not every approved replacement was applied exactly once')
    # Only sources already present in the public version are considered.
    (stage/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    materialize_reachable(base,stage,manifest)
    from scripts.edition_refresh_bridges import rebuild_bridges
    bridge_report=rebuild_bridges(base,stage,manifest,changed_domains,writer)
    # A changed tax edition retains the previous public body as its comparison.
    from scripts.delegation_baseline import attach_catalog,eligible
    for d in manifest['domains']:
        if d['id'] not in changed_domains or d['id'] not in ('tax','public_institutions'):continue
        cat=Storage(stage).read(d['catalog']);old=storage.read(next(x['catalog'] for x in original['domains'] if x['id']==d['id']))
        oldids=set(old.get('delegation_review',{}).get('baselines',{}))
        skip=[e['id'] for e in cat['laws'] if eligible(e) and e['id'] not in oldids and not any(r['id']==e['id'] for r in applied)]
        attach_catalog(writer,d['id'],cat,previous_site=base,skip_ids=skip);d['catalog']=writer.data(cat)
    manifest['edition_refresh']=dict(checked_at=as_of,scope='reviewed-new-weekly-findings-only',documents=len(plan['rows']),
        note='이번 주 새로 확인하고 검증한 판본·명칭만 반영했습니다. 이전 미반영 목록·예정판본·출처 간 불일치 사항은 남아 있습니다.')
    manifest.pop('version',None);manifest['version']=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()[:20]
    (stage/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    reachable=materialize_reachable(base,stage,manifest)
    for p in (stage/'data').glob('*.json.gz'):
        if p.relative_to(stage).as_posix() not in reachable:
            resolved=p.resolve()
            if not resolved.is_relative_to((stage/'data').resolve()):raise ValueError('Unsafe provisional path')
            resolved.unlink()
    convert(stage,destination,validate_site=False)
    verification={}
    if validate_site:
        from scripts.validate_static_galaxies import validate
        verification=validate(destination)
    if (base/'manifest.json').read_bytes()!=raw or sources_path.read_bytes()!=plan_raw:raise ValueError('Input mutated')
    report=dict(base_version=original['version'],data_version=manifest['version'],base_manifest_sha256=hashlib.sha256(raw).hexdigest(),
                source_sha256=hashlib.sha256(plan_raw).hexdigest(),applied=applied,bridges=bridge_report,verification=verification,
                excluded=plan.get('excluded',[]),unchanged_domains=[d['id'] for d in original['domains'] if d['id'] not in changed_domains])
    destination.with_name(destination.name+'-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('base-site','sources','destination'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();print(json.dumps(build(a.base_site,a.sources,a.destination),ensure_ascii=False,indent=2))
