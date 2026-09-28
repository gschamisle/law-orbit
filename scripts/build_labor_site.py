"""Append labor, constitution or medical; retain old catalogs and logical data bytes.

Packed input is expanded in a new staging folder, then the completed site is
repacked before final hosting validation. The source site is never overwritten.
"""
import argparse,hashlib,json
from pathlib import Path
from scripts.build_static_galaxies import Writer,read,shell,export_documents,overview,workbench
from scripts.compact_static_galaxies import convert
from scripts.validate_static_galaxies import validate
from scripts.static_storage import Storage
from core.mofe_universe import report
from core.domain_navigation import ordered_domains

def build(base,destination,domain='labor'):
    if domain not in ('labor','constitution','medical'):raise ValueError('Unsupported incremental domain')
    from importlib import import_module
    from core.mofe_profiles import WORK_PROFILES
    profile=WORK_PROFILES[domain]
    api=import_module('core.'+domain+'_universe')
    base,destination=Path(base).resolve(),Path(destination).resolve()
    staging=destination.with_name(destination.name+'-staging')
    if destination.exists() or staging.exists() or destination.is_relative_to(base) or base.is_relative_to(destination):
        raise ValueError('기존 자료를 보존하도록 별도의 새 출력 폴더를 선택하세요.')
    baseline=validate(base);original=read(base/'manifest.json')
    if any(d['id']==domain for d in original['domains']):raise ValueError('이미 해당 분야가 포함된 빌드입니다.')
    bundle=api.load_bundle()
    if bundle['assessment']['decision']!='limited-release':raise ValueError('실무 질문 근거 확인 필요')
    # Base checks passed above. Expanded intermediate files can exceed the
    # hosting file-count budget; only the final packed site is deployable.
    convert(base,staging,unpack=True,validate_site=False)
    manifest=read(staging/'manifest.json');shell(staging);writer=Writer(staging)
    docs=bundle['source']['laws']+bundle['source']['administrative_rules'];graph=bundle['graph']
    entries,ids=export_documents(writer,domain,'',docs,graph)
    catalog=dict(laws=entries,overview=writer.data(overview(graph,domain,ids,entries)),
                 coverage=graph['coverage_note'],built_at=graph['built_at'],sectors=profile['sectors'],
                 workbench=workbench(bundle,ids),collection_summary=report(bundle))
    manifest['domains'].append(dict(id=domain,title=profile['title'],laws=len(entries),catalog=writer.data(catalog),built_at=graph['built_at']))
    manifest['domains']=ordered_domains(manifest['domains']);manifest.pop('version',None)
    manifest['version']=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()[:20]
    (staging/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    convert(staging,destination,validate_site=False)
    result=validate(destination)  # No hosting or content validation is waived.
    final=read(destination/'manifest.json');by_id={d['id']:d for d in final['domains']}
    if any(by_id[d['id']]!=d for d in original['domains']) or final.get('cross_domain')!=original.get('cross_domain'):
        raise ValueError('Existing domain metadata changed')
    before,after=Storage(base,original),Storage(destination,final);seen=set();pending=[original]
    while pending:
        value=pending.pop()
        if isinstance(value,dict):
            if {'url','bytes','sha256'}<=value.keys():
                if value['url'] in seen:continue
                seen.add(value['url']);raw=before.raw(value)
                if raw!=after.raw(value):raise ValueError('Existing logical corpus changed')
                pending.append(before.read(value))
            else:pending.extend(v for k,v in value.items() if k!='data_packs')
        elif isinstance(value,list):pending.extend(value)
    result.update(original_domains_unchanged=True,original_logical_assets_unchanged=len(seen),
                  added_site_files=result['site_files']-baseline['site_files'],
                  added_site_bytes=result['site_bytes']-baseline['site_bytes'],added_domain=domain,collection=report(bundle))
    (destination.parent/(destination.name+'-report.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-site',type=Path,required=True);p.add_argument('--destination',type=Path,required=True)
    p.add_argument('--domain',choices=('labor','constitution','medical'),default='labor')
    a=p.parse_args();result=build(a.base_site,a.destination,a.domain)
    print(json.dumps({k:v for k,v in result.items() if k!='collection'},ensure_ascii=False,indent=2))
