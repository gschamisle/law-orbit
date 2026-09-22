"""Append the FTC corpus; preserve every previous domain and bridge data shard."""
import argparse,hashlib,json,shutil
from pathlib import Path
from scripts.build_static_galaxies import Writer,read,shell,export_documents,overview
from scripts.validate_static_galaxies import validate
from core.ftc_universe import load_bundle,overview_graph,SECTORS,report
from core.domain_navigation import ordered_domains

def build(base,destination):
    if destination.exists():raise ValueError('기존 빌드를 보존하도록 새 출력 폴더를 선택하세요.')
    validate(base);original=read(base/'manifest.json');manifest=read(base/'manifest.json')
    if any(d['id']=='ftc' for d in manifest['domains']):raise ValueError('이미 공정거래 자료가 포함된 빌드입니다.')
    bundle=load_bundle();source,graph=bundle['source'],bundle['graph']
    shutil.copytree(base,destination);shell(destination);writer=Writer(destination)
    entries,ids=export_documents(writer,'ftc','',source['laws']+source['administrative_rules'],graph)
    catalog=dict(laws=entries,overview=writer.data(overview(overview_graph(bundle),'ftc',ids,entries)),
        coverage=graph['coverage_note'],built_at=graph['built_at'],sectors=SECTORS,collection_summary=report(bundle))
    manifest['domains'].append(dict(id='ftc',title='공정거래',laws=len(entries),catalog=writer.data(catalog),built_at=graph['built_at']))
    manifest['domains']=ordered_domains(manifest['domains']);manifest.pop('version',None)
    manifest['version']=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()[:20]
    (destination/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    previous={d['id']:d for d in manifest['domains']}
    if any(previous[d['id']]!=d for d in original['domains']) or manifest.get('cross_domain')!=original.get('cross_domain'):raise ValueError('Existing domain metadata changed')
    unchanged=0
    for p in (base/'data').glob('*.gz'):
        if p.read_bytes()!=(destination/'data'/p.name).read_bytes():raise ValueError('Existing corpus changed')
        unchanged+=1
    result=validate(destination);result.update(original_data_files_unchanged=unchanged,ftc=report(bundle))
    (destination.parent/(destination.name+'-report.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--base-site',type=Path,required=True);p.add_argument('--destination',type=Path,required=True)
    a=p.parse_args();r=build(a.base_site.resolve(),a.destination.resolve());print(json.dumps({k:v for k,v in r.items() if k!='ftc'},indent=2))
