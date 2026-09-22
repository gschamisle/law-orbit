"""Verify every referenced static shard, scope, checksum and hosting size limit."""
import argparse,gzip,hashlib,json
from pathlib import Path
from core.domain_navigation import DOMAINS


def validate(root, *, allow_legacy_menu=False):
    manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    legacy=['tax','procurement','fsc','local_tax','housing','environment']
    ids=[d['id'] for d in manifest['domains']]
    optional=['state_property','forex','public_institutions','customs','treasury','ftc']
    supported=set(legacy+optional)
    current=[domain for domain in DOMAINS if domain in ids]
    old=[domain for domain in legacy+optional if domain in ids]
    valid_order=ids==current or (allow_legacy_menu and ids==old)
    if not set(legacy).issubset(ids) or set(ids)-supported or len(ids)!=len(set(ids)) or not valid_order:
        raise ValueError('Missing or mixed galaxy menu')
    pending=[];seen=set();total=0;documents=set();articles=0;by_id={};special_rows=[];workbenches=[];bridges=[];text_rows=[];text_bodies={}
    def references(item):
        if isinstance(item,dict):
            if item.get('source_granularity')=='text' and item.get('evidence_id'):text_rows.append(item)
            if {'url','bytes','sha256'}<=item.keys():pending.append(item)
            for v in item.values():references(v)
        elif isinstance(item,list):
            for v in item:references(v)
    references(manifest)
    while pending:
        ref=pending.pop();name=ref['url']
        if name in seen:continue
        seen.add(name)
        if name!='data/'+ref['sha256']+'.json.gz':raise ValueError('Unsafe data path')
        path=root/name;raw=path.read_bytes();total+=len(raw)
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
            if meta['domain']=='ftc' and meta.get('text_analysis'):text_bodies[meta['id']]=data['unstructured_text']
            if meta['domain'] not in [d['id'] for d in manifest['domains']]:raise ValueError('Invalid document domain')
            for article in data['articles']:
                if 'detail' not in article and article['jo'] not in data.get('details',{}):raise ValueError('Missing article connections')
        if isinstance(data,dict) and data.get('workbench'):
            workbenches.append(data['workbench'])
        if isinstance(data,dict) and data.get('kind')=='forex-finance-bridge':
            bridges.append(data)
        if isinstance(data,dict) and data.get('kind')=='special-annex-register':
            special_rows+=data['rows']
            if hashlib.sha256(data['text'].encode()).hexdigest()!=data['sha256']:raise ValueError('Annex source mismatch')
            if [r['number'] for r in data['rows']]!=list(range(1,len(data['rows'])+1)):raise ValueError('Missing annex row')
            for row in data['rows']:
                if data['text'][row['source_start']:row['source_end']]!=row['raw']:raise ValueError('Annex row evidence mismatch')
        references(data)
    for row in text_rows:
        meta,numbers=by_id[row['source_id']]
        if meta['domain']!='ftc' or meta['name']!=row['source_law'] or numbers or row.get('source_jo'):raise ValueError('Invalid text evidence source')
        if text_bodies[row['source_id']][row['source_start']:row['source_end']]!=row['raw']:raise ValueError('Text evidence mismatch')
        if row.get('target_id'):
            target_meta,target_numbers=by_id[row['target_id']]
            if target_meta['domain']!='ftc' or target_meta['name']!=row['target_law']:raise ValueError('Text citation domain mismatch')
            if row['target_kind']=='article':
                from core.citation_scope import parse_target
                if parse_target(row['target_ref']).jo not in target_numbers:raise ValueError('Text citation target missing')
        elif row['target_status']!='not-collected':raise ValueError('Missing text citation document')
    for work in workbenches:
        if work['domain'] not in ids or work['decision']!='limited-release':raise ValueError('Unapproved work area')
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
    if set(manifest.get('cross_domain',{})) not in (set(),{'forex','fsc'}):raise ValueError('Invalid cross-domain scope')
    if len(bridges)!=len(manifest.get('cross_domain',{})):raise ValueError('Missing cross-domain assets')
    for bridge in bridges:
        domain=bridge['domain'];peer=bridge['peer']
        if {domain,peer}!={'forex','fsc'} or bridge['schema']!=1:raise ValueError('Mixed bridge domains')
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
    if {p.relative_to(root).as_posix() for p in (root/'data').glob('*.gz')}!=seen:raise ValueError('Unexpected or unreferenced data files')
    return dict(status='passed',version=manifest['version'],data_files=len(seen),site_files=len(files),data_bytes=total,documents=len(documents),articles=articles)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('site',type=Path);a=p.parse_args();print(json.dumps(validate(a.site),indent=2))
