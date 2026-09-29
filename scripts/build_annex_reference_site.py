"""Add explicit annex references and official links to an immutable public site."""
import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from core.annex_metadata import annex_index, annotate_annex, public_annex_metadata
from core.law_universe import norm
from core.law_library import official_url
from core.universe_builder import build_universe
from scripts.build_static_galaxies import EdgeIndex, Writer, shell, tidy, safe_url
from scripts.build_procurement_pdf_site import materialize_reachable
from scripts.compact_static_galaxies import convert
from scripts.static_storage import Storage
from scripts.validate_static_galaxies import validate


def projection(document, effective):
    return [(str(a['jo']), a.get('title', ''), a.get('text', ''),
             a.get('effective') or effective, bool(a.get('deleted')))
            for a in document['articles']]


def row_key(row):
    return (row.get('direction', 'forward'), row.get('source_law'), str(row.get('source_jo')),
            row.get('source_start'), row.get('source_end'), row.get('target_law'),
            row.get('target_ref'), row.get('target_kind'))


def is_annex_row(row):
    return row.get('neighbor_kind') == 'annex' or (row.get('target_kind') == 'annex' and row.get('direction') != 'reverse')


def add_rows(existing, additions):
    result = list(existing)
    seen = {row_key(r) for r in existing}
    added = 0
    for row in additions:
        if row_key(row) not in seen:
            assert row.get('target_kind') == 'annex'
            result.append(row); seen.add(row_key(row)); added += 1
    return result, added


def delta_graph(domain, source_docs, built_at):
    from core.annex_references import annex_references
    selected = set()
    docs = deepcopy(source_docs)
    for d in docs:
        eligible = not d.get('_annex_metadata_only') and (d.get('citation_policy') == 'mofe-explicit' or d.get('provider') == 'admrul'
                    or (d.get('provider') == 'bok' and domain == 'forex'))
        if eligible:
            selected.add(d['name'])
        for a in d['articles']:
            a['citation_issues'] = []
    def adapter(law, article, corpus):
        if 'analyzed_articles' in law and article['jo'] not in law['analyzed_articles']:
            return []
        return annex_references(law, article, corpus)
    g = build_universe(dict(laws=docs, built_at=built_at), focus_categories=(domain,),
                       preserve_external=True, article_adapter=adapter, source_names=selected)
    g['domain'] = domain
    g['edges'] = [e for e in g['edges'] if e['target_kind'] == 'annex']
    g['external_references'] = [e for e in g['external_references'] if e['target_kind'] == 'annex']
    issues = defaultdict(list)
    for d in docs:
        for a in d['articles']:
            for issue in a.get('citation_issues', []):
                issues[(d['name'], str(a['jo']))].append({k:issue[k] for k in ('raw','reason','kind','status') if k in issue})
    return g, issues


def update_catalog(domain, catalog, storage, writer, source_docs, stats, *, parse_new=True):
    """Replace references only when needed, retaining all unrelated payload fields."""
    catalog = deepcopy(catalog)
    entries = catalog['laws']
    bodies = {e['name']: storage.read(e['file']) for e in entries}
    source = {d['name']: d for d in source_docs}
    matched = []
    for e in entries:
        old = bodies[e['name']]
        d = source.get(e['name'])
        if d is not None:
            if (str(d.get('effective', '')) != str(e.get('effective', ''))
                    or safe_url(official_url(d)) != e.get('url','')
                    or projection(d, d.get('effective')) != projection(old, e.get('effective'))):
                raise ValueError('Source and published article edition differ: '+domain+' '+e['name'])
            matched.append(d)
        elif parse_new:
            stats['source_metadata_unavailable'].append(e['name'])
    # Current public analyses take precedence over source bundles. Only metadata
    # is added; no new body analyses or annex-internal references are generated.
    metadata_docs = []
    for e in entries:
        old = bodies[e['name']]
        if 'annexes' in old:
            annexes = deepcopy(old['annexes'])
        else:
            annexes = [public_annex_metadata(a) for a in source.get(e['name'], {}).get('annexes', [])]
        metadata_docs.append(dict(name=e['name'], annexes=annexes))
    index = annex_index(metadata_docs)
    ids = {e['name']: e['id'] for e in entries}
    urls = {e['name']: e['url'] for e in entries}
    graph_docs=list(matched)
    for e in entries:
        if e['name'] not in source:
            graph_docs.append(dict(name=e['name'],category=domain,provider='public-only',
                effective=e.get('effective',''),articles=deepcopy(bodies[e['name']]['articles']),
                annexes=[],_annex_metadata_only=True))
    g, issues = delta_graph(domain, graph_docs, catalog.get('built_at','')) if parse_new else ({'edges':[],'external_references':[],'laws':[]}, {})
    for edge in g['edges']+g['external_references']:
        if edge['source_law'] in urls:edge['source_url']=urls[edge['source_law']]
        if edge['target_law'] in urls:edge['target_url']=urls[edge['target_law']]
    edge_index = EdgeIndex(g, graph_docs)
    additions, outside = defaultdict(list), defaultdict(list)
    for edge in g['edges']:
        key=(edge['source_law'],str(edge['source_jo']))
        additions[key] = None
    for key in additions:
        additions[key] = [tidy(annotate_annex(r,index),ids,edge_index.hyphen)
                          for r in edge_index.focus(*key)['rows']]
    for edge in g['external_references']:
        outside[(edge['source_law'],str(edge['source_jo']))].append(tidy(annotate_annex(edge,index),ids,edge_index.hyphen))
    metadata_by_name = {d['name']:d['annexes'] for d in metadata_docs}
    for e in entries:
        name=e['name']; old=bodies[name]; body=deepcopy(old)
        if metadata_by_name[name] and 'annexes' not in body:
            body['annexes']=metadata_by_name[name]
            stats['metadata_annexes_added']+=len(body['annexes'])
        def detail_update(value, jo):
            result=deepcopy(value)
            for field, extra in (('rows',additions.get((name,str(jo)),[])),('external',outside.get((name,str(jo)),[]))):
                if field not in result and not extra:continue
                old_rows=value.get(field,[])
                rows=[annotate_annex(r,index) if is_annex_row(r) else r for r in old_rows]
                for before,after in zip(old_rows,rows):
                    if before!=after:stats['rows_with_metadata_updated']+=1
                    if before.get('annex_urls'):
                        if not set(before['annex_urls'])<=set(after.get('annex_urls',[])):
                            raise ValueError('Existing annex URL lost')
                rows,count=add_rows(rows,extra)
                stats['new_external_references' if field=='external' else 'new_collected_references']+=count
                result[field]=rows
                # Old evidence is an unchanged prefix except for link metadata.
                for before,after in zip(old_rows,rows):
                    ignored={'annex_urls','annex_analyzed'} if is_annex_row(before) else set()
                    assert {k:v for k,v in before.items() if k not in ignored} == {k:v for k,v in after.items() if k not in ignored}
            for issue in issues.get((name,str(jo)),[]):
                if issue not in result.setdefault('issues',[]):
                    result['issues'].append(issue);stats['new_review_issues']+=1
            return result
        new_parts={}
        for ref in e.get('parts',[]):
            before=storage.read(ref)
            after={jo:detail_update(value,jo) for jo,value in before.items()}
            new_parts[ref['url']]=writer.data(after) if before!=after else ref
        if 'details' in body:
            body['details']={jo:detail_update(value,jo) for jo,value in body['details'].items()}
        for a in body['articles']:
            if a.get('detail'):a['detail']=new_parts.get(a['detail']['url'],a['detail'])
        e['parts']=[new_parts[ref['url']] for ref in e.get('parts',[])]
        body['meta']['parts']=e['parts']
        # Text/PDF analyses, selected annex analyses, and every article's text
        # and metadata remain byte-for-byte equivalent as JSON values.
        assert [{k:v for k,v in a.items() if k!='detail'} for a in body['articles']] == [{k:v for k,v in a.items() if k!='detail'} for a in old['articles']]
        if 'annexes' in old:assert body['annexes']==old['annexes']
        for field in ('unstructured_text','pdf_analysis','text_connections','text_issues','broad'):
            assert body.get(field)==old.get(field)
        if body!=old:
            e['file']=writer.data(body);stats['documents_updated']+=1
    return catalog


def load_sources(domain, primary, legacy):
    if domain == 'local_tax':
        from core.local_tax_graph import load_manifest
        folder,_=load_manifest(legacy/'output/local-tax-universe')
        path=folder/'central.json'
    else:
        path=primary/f'output/{domain}-universe/bundle.json'
        if not path.is_file():path=legacy/f'output/{domain}-universe/bundle.json'
    raw=path.read_bytes();bundle=json.loads(raw);source=bundle['source']
    docs=source['laws']+source.get('administrative_rules',[])
    return docs,dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest())


def build(base, destination, primary, legacy):
    base,destination,primary,legacy=map(lambda p:Path(p).resolve(),(base,destination,primary,legacy))
    stage=destination.with_name(destination.name+'-unpacked')
    if destination.exists() or stage.exists():raise ValueError('Use a new independent destination')
    if destination.is_relative_to(base) or base.is_relative_to(destination):raise ValueError('Immutable base overlaps destination')
    original_bytes=(base/'manifest.json').read_bytes();original=json.loads(original_bytes)
    manifest=deepcopy(original);manifest.pop('data_packs',None)
    storage=Storage(base,original);stage.mkdir(parents=True);shell(stage);writer=Writer(stage)
    results={};inputs=[]
    for domain in manifest['domains']:
        did=domain['id'];source,provenance=load_sources(did,primary,legacy);inputs.append(provenance)
        catalog=storage.read(domain['catalog'])
        if did=='public_institutions':
            names={d['name'] for d in source}
            wanted={e['name'] for e in catalog['laws']}-names
            for other in ('state_property','procurement','tax'):
                candidates,origin=load_sources(other,primary,legacy);inputs.append(origin)
                for d in candidates:
                    if d['name'] in wanted:
                        copy=deepcopy(d);copy['_annex_metadata_only']=True
                        source.append(copy);wanted.remove(d['name'])
        stats=dict(source_metadata_unavailable=[],metadata_annexes_added=0,rows_with_metadata_updated=0,
                   new_collected_references=0,new_external_references=0,new_review_issues=0,documents_updated=0)
        updated=update_catalog(did,catalog,storage,writer,source,stats,parse_new=did!='local_tax')
        if updated!=catalog:domain['catalog']=writer.data(updated)
        results[did]=stats
        print(did+': '+json.dumps(stats,ensure_ascii=False),flush=True)
    # Overview, regional ordinance catalogs, cross-domain data, PDF evidence,
    # historical comparisons and special registers retain their original refs.
    manifest.pop('version',None)
    manifest['version']=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()[:20]
    (stage/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    materialize_reachable(base,stage,manifest)
    convert(stage,destination,validate_site=False)
    verified=validate(destination)
    assert (base/'manifest.json').read_bytes()==original_bytes
    for item in inputs:assert hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()==item['sha256']
    report=dict(verification=verified,domains=results,source_inputs=inputs,annex_body_analysis_expanded=False,
                source_and_public_articles_unchanged=True,base_manifest_sha256=hashlib.sha256(original_bytes).hexdigest())
    destination.with_name(destination.name+'-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('base-site','destination','primary-source','legacy-source'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();build(a.base_site,a.destination,a.primary_source,a.legacy_source)
