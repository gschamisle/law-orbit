"""Append approved MOFE work areas while retaining all prior static corpus shards."""
import argparse,hashlib,json,shutil
from pathlib import Path
from scripts.build_static_galaxies import Writer,read,shell,export_documents,overview,workbench
from scripts.validate_static_galaxies import validate
from core.mofe_profiles import PROFILES
from core.mofe_universe import load_bundle
from core.domain_navigation import ordered_domains

def build(base,destination):
    if destination.exists():raise ValueError('기존 빌드를 보존하도록 새 출력 폴더를 선택하세요.')
    validate(base,allow_legacy_menu=True);original=read(base/'manifest.json');manifest=read(base/'manifest.json')
    if any(d['id'] in PROFILES for d in manifest['domains']):raise ValueError('이미 재경부 확장이 포함된 빌드입니다.')
    bundles={d:load_bundle(d) for d in PROFILES}
    shutil.copytree(base,destination);shell(destination);writer=Writer(destination)
    for domain,p in PROFILES.items():
        b=bundles[domain];source,graph=b['source'],b['graph']
        docs=source['laws']+source['administrative_rules']
        entries,ids=export_documents(writer,domain,'',docs,graph)
        catalog=dict(laws=entries,overview=writer.data(overview(graph,domain,ids,entries)),
            coverage=graph['coverage_note'],built_at=graph['built_at'],sectors=p['sectors'],workbench=workbench(b,ids))
        manifest['domains'].append(dict(id=domain,title=p['title'],laws=len(entries),catalog=writer.data(catalog),built_at=graph['built_at']))
        print(domain,': exported',len(entries),'documents',flush=True)
    manifest['domains']=ordered_domains(manifest['domains'])
    manifest.pop('version',None)
    manifest['version']=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()[:20]
    (destination/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    by_id={d['id']:d for d in manifest['domains']}
    if any(by_id.get(d['id'])!=d for d in original['domains']):raise ValueError('Original domain metadata changed')
    result=validate(destination);result['original_domains_unchanged']=True
    (destination.parent/(destination.name+'-report.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--base-site',type=Path,required=True);p.add_argument('--destination',type=Path,required=True)
    a=p.parse_args();print(json.dumps(build(a.base_site.resolve(),a.destination.resolve()),indent=2))
