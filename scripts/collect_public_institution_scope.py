"""Collect selected cross-ministry scope sources, without changing other domains."""
import argparse,json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from core.fsc_collection import LawTransport,CollectionError,atomic_json,norm
from core.fsc_credentials import law_api_key
from core.procurement_collection import record,discover_query,collect_sources
from core.public_institution_scope import BORROWERS,SCOPE_RULES,PRIVATE_LAWS
from core.mofe_collection import prepare_source
from core.mofe_universe import build_graph,validate_bundle,assessment

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-bundle',type=Path,required=True)
    p.add_argument('--stage',choices=('inventory','bodies','build'),required=True)
    p.add_argument('--phase',choices=('scope','privatization'),default='scope')
    p.add_argument('--output',type=Path,default=Path('output/public-scope'))
    a=p.parse_args();root=a.output;root.mkdir(parents=True,exist_ok=True)
    now=datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y%m%d')
    key=law_api_key();target=root/a.phase
    lock=root/'collect.lock'
    try: handle=lock.open('x')
    except FileExistsError: print('다른 실행의 잠금을 보존합니다.');return 2
    def read(file):return json.loads(file.read_text(encoding='utf-8'))
    def save(file,value):
        if key and key in json.dumps(value,ensure_ascii=False):raise CollectionError('credential-in-output')
        atomic_json(file,value)
    try:
        with handle:handle.write(now)
        if a.stage in ('inventory','bodies'):request=LawTransport(key,timeout=30,reuse_connections=True)
        if a.stage=='inventory':
            sets=[('eflaw',BORROWERS),('admrul',SCOPE_RULES)] if a.phase=='scope' else [('eflaw',PRIVATE_LAWS)]
            records={};layers=[]
            for provider,names in sets:
                for name in names:
                    def factory(row,provider,stamp):
                        return record(row,provider,stamp,selector=lambda n,authority,pr:norm(n)==norm(name),domain='public_institutions')
                    layer=discover_query(request,provider,name,now,record_factory=factory)
                    current=[r for r in layer['records'] if r['state']=='current-candidate']
                    if len(current)!=1:raise CollectionError('scope-exact-current-count:'+name+':'+str(len(current)))
                    for r in layer['records']:
                        prior=records.get(r['edition_key'])
                        if prior and prior!=r:raise CollectionError('scope-conflicting-edition')
                        records[r['edition_key']]=r
                    layers.append(layer);print(provider,name,'현행 1건',flush=True)
            save(target/'inventory.json',dict(domain='public_institutions',as_of=now,scope='selected-cross-ministry-scope-references',records=list(records.values()),layers=layers))
        elif a.stage=='bodies':
            inv=read(target/'inventory.json')
            save(target/'source.json',collect_sources(request,inv,target/'body-cache',lambda *parts:print(*parts,flush=True)))
        else:
            base=read(a.base_bundle);addition=read(target/'source.json');source=base['source']
            source['built_at']=addition['built_at']
            for field in ('laws','administrative_rules'):
                merged={d['uid']:d for d in source.get(field,[])}
                merged.update({d['uid']:d for d in addition[field]});source[field]=list(merged.values())
            source['inventory'].setdefault('scope_extensions',{})[a.phase]=addition['inventory']
            scheduled={r['edition_key']:r for r in source.get('scheduled',[])}
            scheduled.update({r['edition_key']:r for r in addition.get('scheduled',[])})
            source['scheduled']=list(scheduled.values())
            source=prepare_source(source);graph=build_graph(source)
            bundle=validate_bundle(dict(source=source,graph=graph),'public_institutions')
            bundle['assessment']=assessment(bundle)
            if bundle['assessment']['decision']=='hold':raise CollectionError('scope-usefulness-gate')
            save(target/'bundle.json',bundle)
            save(target/'report.json',dict(assessment=bundle['assessment'],scope_records=len(graph['public_scope']['records']),
                 direct_scope=sum(r['kind']=='scope' for r in graph['public_scope']['records']),
                 indirect=sum(r['kind']=='indirect' for r in graph['public_scope']['records'])))
            print('분석·검증 완료',len(source['laws'])+len(source['administrative_rules']),'문서',flush=True)
        return 0
    except (CollectionError,ValueError,KeyError,TypeError,OSError) as e:
        reason=str(e) if isinstance(e,CollectionError) else type(e).__name__
        save(target/'failure.json',dict(stage=a.stage,reason=reason));print('기존 자료 보존 · 실패',reason,flush=True);return 1
    finally:lock.unlink()

if __name__=='__main__':raise SystemExit(main())
