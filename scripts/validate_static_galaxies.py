"""Verify every referenced static shard, scope, checksum and hosting size limit."""
import argparse,gzip,hashlib,json
from pathlib import Path


def validate(root):
    manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    if [d['id'] for d in manifest['domains']]!=['tax','procurement','fsc','local_tax','housing','environment']:
        raise ValueError('Missing or mixed galaxy menu')
    pending=[];seen=set();total=0;documents=set();articles=0
    def references(item):
        if isinstance(item,dict):
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
        if isinstance(data,dict) and 'meta' in data:
            meta=data['meta'];documents.add(meta['id']);articles+=len(data['articles'])
            if meta['domain'] not in [d['id'] for d in manifest['domains']]:raise ValueError('Invalid document domain')
            for article in data['articles']:
                if 'detail' not in article and article['jo'] not in data.get('details',{}):raise ValueError('Missing article connections')
        references(data)
    actual=list(root.rglob('*'));files=[p for p in actual if p.is_file()]
    if len(files)>20000:raise ValueError('Cloudflare free file limit exceeded')
    if sum(p.stat().st_size for p in files)>1024**3:raise ValueError('GitHub Pages site limit exceeded')
    if {p.relative_to(root).as_posix() for p in (root/'data').glob('*.gz')}!=seen:raise ValueError('Unexpected or unreferenced data files')
    return dict(status='passed',version=manifest['version'],data_files=len(seen),site_files=len(files),data_bytes=total,documents=len(documents),articles=articles)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('site',type=Path);a=p.parse_args();print(json.dumps(validate(a.site),indent=2))
