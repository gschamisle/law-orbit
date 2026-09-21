"""Collect the three scoped MOFE corpora in observable, resumable phases."""
import argparse,json,shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from core.mofe_profiles import PROFILES
from core.mofe_collection import discover_inventory,collect_sources,prepare_source
from core.mofe_universe import path,build_graph,validate_bundle,assessment,report
from core.fsc_collection import LawTransport,CollectionError,atomic_json,ymd
from core.fsc_credentials import law_api_key

def run(domain,stage,stamp):
    now=datetime.now(ZoneInfo('Asia/Seoul'));root=path(domain).parent
    root.mkdir(parents=True,exist_ok=True);staging=root/'staging'/stamp;lock=root/'collect.lock'
    try:handle=lock.open('x')
    except FileExistsError:print(domain,'다른 실행 잠금 보존',flush=True);return 2
    key=law_api_key()
    def log(*parts):print(domain,' · '.join(map(str,parts)),flush=True)
    def read(name):return json.loads((staging/name).read_text(encoding='utf-8'))
    try:
        with handle:handle.write(now.isoformat())
        if stage in ('inventory','bodies'):
            if not key:raise CollectionError('missing-law-api-key')
            request=LawTransport(key,attempts=3,timeout=30,reuse_connections=True)
        if stage=='inventory':atomic_json(staging/'inventory.json',discover_inventory(request,domain,stamp,log))
        elif stage=='bodies':
            source=collect_sources(request,read('inventory.json'),staging/'body-cache',log)
            if key in json.dumps(source,ensure_ascii=False):raise CollectionError('credential-found-in-output')
            atomic_json(staging/'source.json',source)
        else:
            source=prepare_source(read('source.json'));graph=build_graph(source)
            bundle=validate_bundle(dict(source=source,graph=graph),domain)
            review=assessment(bundle);bundle['assessment']=review
            if key and key in json.dumps(bundle,ensure_ascii=False):raise CollectionError('credential-found-in-output')
            atomic_json(staging/'validated-bundle.json',bundle);atomic_json(root/'assessment.json',review)
            if review['decision']=='hold':raise CollectionError('mofe-usefulness-gate-hold')
            if path(domain).exists():
                backup=root/'history'/now.strftime('%Y%m%d-%H%M%S')/'bundle.json'
                backup.parent.mkdir(parents=True,exist_ok=False);shutil.copy2(path(domain),backup)
            atomic_json(path(domain),bundle);atomic_json(root/'summary.json',report(bundle))
            log('판단',review['decision'],'문서',review['documents'],'조문',review['articles'],'문서간 근거',review['cross_document_evidence'])
        atomic_json(root/'last-run.json',dict(at=now.isoformat(),stage=stage,status='success'));return 0
    except (CollectionError,OSError,ValueError,KeyError,TypeError) as e:
        reason=str(e) if isinstance(e,CollectionError) else type(e).__name__
        log('실패 · 기존 자료 보존',reason)
        atomic_json(root/'failure.json',dict(at=now.isoformat(),stage=stage,reason=reason));return 1
    finally:lock.unlink()

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--domain',choices=['all',*PROFILES],default='all')
    p.add_argument('--stage',choices=['inventory','bodies','build'],required=True);p.add_argument('--date')
    args=p.parse_args();today=datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y%m%d');stamp=ymd(args.date or today)
    if stamp>today:raise ValueError('Future collection date')
    return max(run(d,args.stage,stamp) for d in (PROFILES if args.domain=='all' else [args.domain]))

if __name__=='__main__':raise SystemExit(main())
