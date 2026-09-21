"""Extend a verified seven-domain static release without rebuilding its original data."""
import argparse,hashlib,json,shutil
from pathlib import Path
from scripts.build_static_galaxies import Writer,read,shell,export_documents,overview
from scripts.validate_static_galaxies import validate
from core.forex_universe import BUNDLE,load_bundle,SECTORS
from core.domain_navigation import ordered_domains

def build(base,destination,bundle_path=BUNDLE):
    if destination.exists():raise ValueError('Choose a new empty destination; existing builds are preserved')
    validate(base,allow_legacy_menu=True);manifest=read(base/'manifest.json')
    if any(d['id']=='forex' for d in manifest['domains']):raise ValueError('Base already contains foreign exchange')
    bundle=load_bundle(bundle_path);source,graph=bundle['source'],bundle['graph']
    shutil.copytree(base,destination);shell(destination);writer=Writer(destination)
    entries,ids=export_documents(writer,'forex','',source['laws']+source['administrative_rules'],graph)
    catalog=dict(laws=entries,overview=writer.data(overview(graph,'forex',ids,entries)),
                 coverage=graph['coverage_note'],built_at=graph['built_at'],sectors={'all':'전체 연결',**SECTORS})
    manifest['domains'].append(dict(id='forex',title='외환',laws=len(entries),catalog=writer.data(catalog),built_at=graph['built_at']))
    manifest['domains']=ordered_domains(manifest['domains'])
    manifest.pop('version',None)
    manifest['version']=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()[:20]
    (destination/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    report=validate(destination)
    by_id={d['id']:d for d in manifest['domains']}
    if any(by_id.get(d['id'])!=d for d in read(base/'manifest.json')['domains']):raise ValueError('Original domains changed')
    report['original_domains_unchanged']=True
    (destination.parent/(destination.name+'-report.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--base-site',type=Path,required=True)
    p.add_argument('--destination',type=Path,required=True);p.add_argument('--bundle',type=Path,default=BUNDLE)
    a=p.parse_args();print(json.dumps(build(a.base_site.resolve(),a.destination.resolve(),a.bundle),indent=2))
