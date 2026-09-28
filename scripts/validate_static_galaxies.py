"""Verify every referenced static shard, scope, checksum and hosting size limit."""
import argparse,gzip,hashlib,json
from pathlib import Path
from core.domain_navigation import DOMAINS
from core.forex_finance_links import PAIRS, BRIDGE_KINDS
from core.ftc_text_citations import TEXT_DOMAINS
from scripts.static_storage import Storage


def validate(root, *, allow_legacy_menu=False):
    manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    storage=Storage(root,manifest)
    legacy=['tax','procurement','fsc','local_tax','housing','environment']
    ids=[d['id'] for d in manifest['domains']]
    optional=['state_property','forex','public_institutions','customs','treasury','ftc','labor','constitution','medical']
    supported=set(legacy+optional)
    current=[domain for domain in DOMAINS if domain in ids]
    old=[domain for domain in legacy+optional if domain in ids]
    valid_order=ids==current or (allow_legacy_menu and ids==old)
    if not set(legacy).issubset(ids) or set(ids)-supported or len(ids)!=len(set(ids)) or not valid_order:
        raise ValueError('Missing or mixed galaxy menu')
    pending=[];seen=set();total=0;documents=set();articles=0;by_id={};special_rows=[];workbenches=[];bridges=[];text_rows=[];text_bodies={};constitution_bodies={};annex_bodies={};annex_rows=[];pdf_bodies={}
    def references(item):
        if isinstance(item,dict):
            if item.get('source_layer')=='annex-body' and item.get('evidence_id'):annex_rows.append(item)
            if item.get('source_granularity')=='text' and item.get('evidence_id'):text_rows.append(item)
            if {'url','bytes','sha256'}<=item.keys():pending.append(item)
            for k,v in item.items():
                if k!='data_packs':references(v)
        elif isinstance(item,list):
            for v in item:references(v)
    references(manifest)
    while pending:
        ref=pending.pop();name=ref['url']
        if name in seen:continue
        seen.add(name)
        if name!='data/'+ref['sha256']+'.json.gz':raise ValueError('Unsafe data path')
        raw=storage.raw(ref);total+=len(raw)
        if len(raw)!=ref['bytes'] or hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('Asset mismatch')
        if len(raw)>25*1024*1024:raise ValueError('Free hosting asset limit exceeded')
        data=json.loads(gzip.decompress(raw))
        if isinstance(data,dict) and data.get('kind')=='delegation-baseline':
            if data['meta']['domain'] not in ('tax','public_institutions'):raise ValueError('Invalid delegation baseline domain')
            if data.get('schema')!=1 or len({a['jo'] for a in data['articles']})!=len(data['articles']):raise ValueError('Invalid delegation baseline')
            if any(not isinstance(a.get('text'),str) for a in data['articles']):raise ValueError('Missing baseline text')
        elif isinstance(data,dict) and 'meta' in data:
            meta=data['meta'];documents.add(meta['id']);articles+=len(data['articles'])
            by_id[meta['id']]=(meta,{a['jo'] for a in data['articles']})
            if meta['domain']=='constitution':constitution_bodies[meta['id']]={a['jo']:a for a in data['articles']}
            for annex in data.get('annexes',[]):
                from core.annex_analysis import validate_analysis
                if annex.get('analysis'):
                    if annex['status']!='explicit-citations':raise ValueError('Annex coverage mismatch')
                    validate_analysis(annex['analysis']);annex_bodies[(meta['id'],annex['ref'])]=annex['analysis']
                elif annex['status']!='not-analyzed':raise ValueError('Unverified annex body')
            if meta['domain'] in TEXT_DOMAINS and meta.get('text_analysis'):text_bodies[meta['id']]=data['unstructured_text']
            if data.get('pdf_analysis'):
                pdf=data['pdf_analysis'];body=data['unstructured_text']
                if meta['domain']!='procurement' or meta['text_analysis']['status'] not in ('explicit-pdf-prose','explicit-pdf-structured'):raise ValueError('Invalid PDF analysis scope')
                if hashlib.sha256(body.encode()).hexdigest()!=pdf['text_sha256']:raise ValueError('PDF text checksum mismatch')
                if [p['page'] for p in pdf['pages']]!=list(range(1,len(pdf['pages'])+1)):raise ValueError('Missing PDF page')
                if any(not(0<=p['start']<=p['end']<=len(body)) for p in pdf['pages']):raise ValueError('Invalid PDF page bounds')
                anchors={a['id']:a for a in pdf.get('anchors',[])}
                if len(anchors)!=len(pdf.get('anchors',[])):raise ValueError('Duplicate PDF heading identifier')
                for a in anchors.values():
                    page=pdf['pages'][a['page']-1]
                    if not(page['start']<=a['start']<page['end'] and a['start']<a['end']<=len(body) and body[a['start']:].startswith(a['label'])):raise ValueError('Invalid PDF heading source')
                for row in pdf.get('internal_connections',[]):
                    target=anchors[row['target_id']];page=pdf['pages'][row['source_page']-1]
                    if not(page['start']<=row['source_start']<row['source_end']<=page['end']):raise ValueError('Invalid internal PDF source page')
                    if body[row['source_start']:row['source_end']]!=row['raw']:raise ValueError('Invalid internal PDF quote')
                    if target['key']!=row['target_key'] or target['page']!=row['target_page'] or target['label']!=row['target_label']:raise ValueError('Invalid internal PDF target')
                pdf_bodies[meta['id']]=pdf
            if meta['domain'] not in [d['id'] for d in manifest['domains']]:raise ValueError('Invalid document domain')
            for article in data['articles']:
                if 'detail' not in article and article['jo'] not in data.get('details',{}):raise ValueError('Missing article connections')
        if isinstance(data,dict) and data.get('workbench'):
            workbenches.append(data['workbench'])
        if isinstance(data,dict) and data.get('kind') in BRIDGE_KINDS.values():
            bridges.append(data)
        if isinstance(data,dict) and data.get('kind')=='special-annex-register':
            special_rows+=data['rows']
            if hashlib.sha256(data['text'].encode()).hexdigest()!=data['sha256']:raise ValueError('Annex source mismatch')
            if [r['number'] for r in data['rows']]!=list(range(1,len(data['rows'])+1)):raise ValueError('Missing annex row')
            for row in data['rows']:
                if data['text'][row['source_start']:row['source_end']]!=row['raw']:raise ValueError('Annex row evidence mismatch')
        references(data)
    for row in annex_rows:
        a=annex_bodies[(row['source_id'],row['source_jo'])]
        if a['text'][row['source_start']:row['source_end']]!=row['raw'] or a['text_sha256']!=row['source_text_sha256'] or a['file_sha256']!=row['source_file_sha256']:
            raise ValueError('Annex citation source mismatch')
    for row in text_rows:
        meta,numbers=by_id[row['source_id']]
        if meta['domain'] not in TEXT_DOMAINS or meta['name']!=row['source_law'] or numbers or row.get('source_jo'):raise ValueError('Invalid text evidence source')
        if text_bodies[row['source_id']][row['source_start']:row['source_end']]!=row['raw']:raise ValueError('Text evidence mismatch')
        if row.get('source_layer','').startswith('procurement-pdf-'):
            if row['source_layer'] not in ('procurement-pdf-prose','procurement-pdf-annex-prose','procurement-pdf-table-cell'):raise ValueError('Unknown PDF citation layer')
            pdf=pdf_bodies[row['source_id']];page=pdf['pages'][row['source_page']-1]
            if pdf['file_sha256']!=row['source_file_sha256'] or pdf['text_sha256']!=row['source_text_sha256']:raise ValueError('PDF evidence checksum mismatch')
            if not(page['analyzed_units'] and page['start']<=row['source_start']<row['source_end']<=page['end']):raise ValueError('PDF evidence outside analyzed page')
            if row['source_url']!=pdf['pdf_url']+f"#page={page['page']}":raise ValueError('PDF evidence page link mismatch')
            if row['source_layer']=='procurement-pdf-table-cell':
                matches=[c for c in pdf['cells'] if c['page']==row['source_page'] and c['table']==row['source_table'] and c['row']==row['source_row'] and c['column']==row['source_column']]
                if len(matches)!=1 or not(matches[0]['analyzed'] and matches[0]['start']<=row['source_start']<row['source_end']<=matches[0]['end'] and matches[0]['bbox']==row['source_bbox']):raise ValueError('PDF citation crosses cell boundary')
        if row.get('target_id'):
            target_meta,target_numbers=by_id[row['target_id']]
            if target_meta['domain']!=meta['domain'] or target_meta['name']!=row['target_law']:raise ValueError('Text citation domain mismatch')
            if row['target_kind']=='article':
                from core.citation_scope import parse_target
                if parse_target(row['target_ref']).jo not in target_numbers:raise ValueError('Text citation target missing')
        elif row['target_status']!='not-collected':raise ValueError('Missing text citation document')
    for work in workbenches:
        if work['domain'] not in ids or work['decision']!='limited-release':raise ValueError('Unapproved work area')
        if work['domain']=='constitution':
            from core.constitution_profile import CONSTITUTION,GUIDE
            guide=work.get('constitution_guide',[])
            if [(r['constitution']['jo'],r['title'],r['related']['law'],r['related']['jo'],r['reason']) for r in guide]!=list(GUIDE):
                raise ValueError('Constitution reading guide mismatch')
            for row in guide:
                if row['kind']!='editorial-related-law' or row['is_citation'] is not False or row['constitution']['law']!=CONSTITUTION:raise ValueError('Guide confused with citation')
                for side in ('constitution','related'):
                    ep=row[side];meta,numbers=by_id[ep['law_id']]
                    if meta['domain']!='constitution' or meta['name']!=ep['law'] or ep['jo'] not in numbers or ep['url']!=meta['url']:raise ValueError('Guide endpoint mismatch')
                    a=constitution_bodies[ep['law_id']][ep['jo']]
                    if ep['text']!=a['text'] or ep['effective']!=(a.get('effective') or meta['effective']) or ep['sha256']!=hashlib.sha256(a['text'].encode()).hexdigest():raise ValueError('Guide body or edition mismatch')
        for case in work['cases']:
            meta,numbers=by_id[case['law_id']]
            if meta['domain']!=work['domain'] or meta['name']!=case['law'] or case['jo'] not in numbers:raise ValueError('Work case source mismatch')
            if not case['available'] or not case['evidence_ids']:raise ValueError('Work case has no evidence')
    for row in special_rows:
        if row.get('law_id'):
            meta,numbers=by_id[row['law_id']]
            if meta['domain']!='state_property' or meta['name']!=row['law']:raise ValueError('Annex target domain or title mismatch')
            if not set(row.get('article_numbers',[])).issubset(numbers):raise ValueError('Annex target article missing')
        elif row['status']=='matched':raise ValueError('Matched annex target missing')
    cross_domains=set(manifest.get('cross_domain',{}))
    if cross_domains-set(d for pair in PAIRS for d in pair):raise ValueError('Invalid cross-domain scope')
    if any(cross_domains & set(pair) and not set(pair)<=cross_domains for pair in PAIRS):raise ValueError('Incomplete domain pair')
    if len(bridges)!=len(manifest.get('cross_domain',{})):raise ValueError('Missing cross-domain assets')
    for bridge in bridges:
        domain=bridge['domain'];peer=bridge['peer']
        pair=next((p for p in PAIRS if set(p)=={domain,peer}),None)
        if not pair or bridge['schema']!=1 or bridge['kind']!=BRIDGE_KINDS[pair]:raise ValueError('Mixed bridge domains')
        for d,edition in bridge['editions'].items():
            if next(e['built_at'] for e in manifest['domains'] if e['id']==d)!=edition:raise ValueError('Bridge edition mismatch')
        neighbors={e['id']:e for e in bridge['entries']}
        for e in neighbors.values():
            meta,_=by_id[e['id']]
            if meta['domain']!=peer or meta['name']!=e['name'] or meta['effective']!=e['effective']:raise ValueError('Bridge reader edition mismatch')
        for law_id,sections in bridge['laws'].items():
            meta,numbers=by_id[law_id]
            if meta['domain']!=domain or not set(sections).issubset(numbers):raise ValueError('Bridge source missing')
            for value in sections.values():
                for row in value['rows']:
                    neighbor=neighbors[row['neighbor_id']];neighbor_meta,neighbor_numbers=by_id[neighbor['id']]
                    if row['neighbor_domain']!=peer or not row['cross_domain']:raise ValueError('Bridge neighbor mismatch')
                    if row['neighbor_kind']=='article' and row['neighbor_jo'] not in neighbor_numbers:raise ValueError('Bridge article missing')
                    if row['direction']=='forward':source_id,target_id=law_id,neighbor['id']
                    else:source_id,target_id=neighbor['id'],law_id
                    if row['source_id']!=source_id or row['target_id']!=target_id:raise ValueError('Bridge direction mismatch')
    actual=list(root.rglob('*'));files=[p for p in actual if p.is_file()]
    if len(files)>20000:raise ValueError('Cloudflare free file limit exceeded')
    if sum(p.stat().st_size for p in files)>1024**3:raise ValueError('GitHub Pages site limit exceeded')
    storage.check_inventory()
    return dict(status='passed',version=manifest['version'],data_files=len(storage.physical),logical_data_files=len(seen),site_files=len(files),data_bytes=sum(storage.physical.values()),logical_data_bytes=total,site_bytes=sum(p.stat().st_size for p in files),documents=len(documents),articles=articles)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('site',type=Path);a=p.parse_args();print(json.dumps(validate(a.site),indent=2))
