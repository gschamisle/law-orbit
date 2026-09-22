"""Collect FTC inventory, pinned bodies and validated graph in resumable stages."""
import argparse,json,shutil
from datetime import datetime
from zoneinfo import ZoneInfo
from core.ftc_collection import discover_inventory,collect_sources,prepare_source
from core.ftc_universe import BUNDLE,build_graph,validate_bundle,report
from core.fsc_collection import LawTransport,CollectionError,atomic_json,ymd
from core.fsc_credentials import law_api_key

def run(stage,stamp):
    now=datetime.now(ZoneInfo('Asia/Seoul'));root=BUNDLE.parent;root.mkdir(parents=True,exist_ok=True)
    staging=root/'staging'/stamp;lock=root/'collect.lock'
    try:handle=lock.open('x')
    except FileExistsError:print('공정거래 수집 잠금 보존 · 다른 실행 확인 필요',flush=True);return 2
    key=law_api_key()
    def log(*items):print(' · '.join(map(str,items)),flush=True)
    def read(name):return json.loads((staging/name).read_text(encoding='utf-8'))
    try:
        with handle:handle.write(now.isoformat())
        if stage in ('inventory','bodies'):
            if not key:raise CollectionError('missing-law-api-key')
            request=LawTransport(key,attempts=3,timeout=30,reuse_connections=True)
        if stage=='inventory':atomic_json(staging/'inventory.json',discover_inventory(request,stamp,log))
        elif stage=='bodies':
            source=collect_sources(request,read('inventory.json'),staging/'body-cache',log)
            if key in json.dumps(source,ensure_ascii=False):raise CollectionError('credential-found-in-output')
            atomic_json(staging/'source.json',source)
        else:
            source=prepare_source(read('source.json'));graph=build_graph(source)
            bundle=validate_bundle(dict(source=source,graph=graph))
            if key and key in json.dumps(bundle,ensure_ascii=False):raise CollectionError('credential-found-in-output')
            atomic_json(staging/'validated-bundle.json',bundle)
            if BUNDLE.exists():
                backup=root/'history'/now.strftime('%Y%m%d-%H%M%S')/'bundle.json'
                backup.parent.mkdir(parents=True,exist_ok=False);shutil.copy2(BUNDLE,backup)
            atomic_json(BUNDLE,bundle);summary=report(bundle);atomic_json(root/'summary.json',summary)
            log('수집',summary['documents'],'문서','분석',summary['articles'],'조문','인용',summary['edges'],'건')
        atomic_json(root/'last-run.json',dict(at=now.isoformat(),stage=stage,status='success'));return 0
    except (CollectionError,OSError,ValueError,KeyError,TypeError) as error:
        reason=str(error) if isinstance(error,CollectionError) else type(error).__name__
        log('공정거래 수집 실패 · 기존 자료 보존',reason)
        atomic_json(root/'failure.json',dict(at=now.isoformat(),stage=stage,reason=reason));return 1
    finally:lock.unlink()

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stage',choices=['inventory','bodies','build'],required=True);p.add_argument('--date')
    args=p.parse_args();today=datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y%m%d');stamp=ymd(args.date or today)
    if stamp>today:raise ValueError('Future collection date')
    return run(args.stage,stamp)

if __name__=='__main__':raise SystemExit(main())
