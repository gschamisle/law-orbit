"""Replace only the public-institution shards, preserving the other ten domains."""
import argparse,hashlib,json,shutil,gzip
from pathlib import Path
from scripts.build_static_galaxies import Writer,read,shell,export_documents,overview,workbench
from scripts.validate_static_galaxies import validate
from core.mofe_universe import validate_bundle
from core.mofe_profiles import PROFILES

def build(base,destination,bundle_file):
    if destination.exists():raise ValueError('Use a new destination; existing builds are preserved')
    validate(base);original=read(base/'manifest.json');manifest=read(base/'manifest.json')
    bundle=validate_bundle(read(bundle_file),'public_institutions')
    destination.mkdir(parents=True);shell(destination);writer=Writer(destination)
    source,graph=bundle['source'],bundle['graph']
    docs=source['laws']+source['administrative_rules']
    entries,ids=export_documents(writer,'public_institutions','',docs,graph)
    catalog=dict(laws=entries,overview=writer.data(overview(graph,'public_institutions',ids,entries)),
       coverage=graph['coverage_note'],built_at=graph['built_at'],sectors=PROFILES['public_institutions']['sectors'],workbench=workbench(bundle,ids))
    from scripts.delegation_baseline import attach_catalog
    attach_catalog(writer,'public_institutions',catalog,base)
    for d in manifest['domains']:
        if d['id']=='public_institutions':d.update(laws=len(entries),catalog=writer.data(catalog),built_at=graph['built_at'])
    before={d['id']:d for d in original['domains'] if d['id']!='public_institutions'}
    after={d['id']:d for d in manifest['domains'] if d['id']!='public_institutions'}
    if before!=after:raise ValueError('Other domain metadata changed')
    manifest.pop('version',None);manifest['version']=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()[:20]
    (destination/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    pending=[];seen=set();copied=0
    def refs(v):
        if isinstance(v,dict):
            if {'url','sha256','bytes'}<=v.keys():pending.append(v)
            else:
                for item in v.values():refs(item)
        elif isinstance(v,list):
            for item in v:refs(item)
    refs(manifest)
    while pending:
        ref=pending.pop();name=ref['url']
        if name in seen:continue
        seen.add(name)
        if name!='data/'+ref['sha256']+'.json.gz':raise ValueError('Unsafe shard path')
        dest=destination/name
        if not dest.exists():dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(base/name,dest);copied+=1
        raw=dest.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('Shard mismatch')
        refs(json.loads(gzip.decompress(raw)))
    result=validate(destination);result.update(other_domains_unchanged=list(before),original_shards_copied=copied)
    (destination.parent/(destination.name+'-report.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base-site',type=Path,required=True);p.add_argument('--destination',type=Path,required=True)
    p.add_argument('--bundle',type=Path,default=Path('output/public-scope/privatization/bundle.json'));a=p.parse_args()
    print(json.dumps(build(a.base_site.resolve(),a.destination.resolve(),a.bundle),ensure_ascii=False,indent=2))
