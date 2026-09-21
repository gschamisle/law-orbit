"""Collect foreign exchange in isolated, resumable phases; publish only validated bundles."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import shutil
from zoneinfo import ZoneInfo
from core.fsc_collection import LawTransport,CollectionError,atomic_json
from core.fsc_credentials import law_api_key
from core.forex_collection import discover_inventory,collect_sources,prepare_source
from core import forex_bok

ROOT=Path(__file__).resolve().parents[1]/'output/forex-universe'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage',choices=['inventory','bodies','build'],required=True)
    p.add_argument('--date',help='Resume an existing collection date (YYYYMMDD)')
    args=p.parse_args();now=datetime.now(ZoneInfo('Asia/Seoul'));stamp=args.date or now.strftime('%Y%m%d')
    from core.fsc_collection import ymd
    stamp=ymd(stamp)
    if stamp>now.strftime('%Y%m%d'):raise ValueError('Future collection date')
    staging=ROOT/'staging'/stamp;ROOT.mkdir(parents=True,exist_ok=True);lock=ROOT/'collect.lock'
    try:handle=lock.open('x')
    except FileExistsError:print('다른 수집이 실행 중입니다. 기존 잠금을 보존합니다.');return 2
    key=law_api_key()
    def log(*items):print(' · '.join(map(str,items)),flush=True)
    def read(name):return json.loads((staging/name).read_text(encoding='utf-8'))
    try:
        with handle:handle.write(now.isoformat())
        request=LawTransport(key,reuse_connections=True) if key else None
        if args.stage=='inventory':
            if not request:raise CollectionError('missing-law-api-key')
            atomic_json(staging/'inventory.json',discover_inventory(request,stamp,log))
            atomic_json(staging/'bok-inventory.json',forex_bok.discover(stamp,staging/'bok'))
            log('법제처·한국은행 목록 확인 완료')
        elif args.stage=='bodies':
            if not request:raise CollectionError('missing-law-api-key')
            source=collect_sources(request,read('inventory.json'),staging/'body-cache',log)
            source['bok_inventory']=read('bok-inventory.json')
            source['administrative_rules']+=forex_bok.collect(source['bok_inventory'],staging/'bok',progress=log)
            source['provider']='법제처 공식 API · 한국은행 공식 법규정보 PDF · 수집 판본 고정'
            if key in json.dumps(source,ensure_ascii=False):raise CollectionError('credential-found-in-output')
            atomic_json(staging/'source.json',source);log('전체 본문 수집 완료')
        else:
            from core.forex_universe import build_graph,validate_bundle,report,BUNDLE
            source=prepare_source(read('source.json'));graph=build_graph(source)
            bundle=validate_bundle(dict(source=source,graph=graph))
            if key and key in json.dumps(bundle,ensure_ascii=False):raise CollectionError('credential-found-in-output')
            atomic_json(staging/'validated-bundle.json',bundle)
            if BUNDLE.exists():
                history=ROOT/'history'/now.strftime('%Y%m%d-%H%M%S')/'bundle.json'
                history.parent.mkdir(parents=True,exist_ok=False);shutil.copy2(BUNDLE,history)
            atomic_json(BUNDLE,bundle);summary=report(bundle);atomic_json(ROOT/'summary.json',summary)
            log(json.dumps(summary,ensure_ascii=False,indent=2))
        atomic_json(ROOT/'last-run.json',dict(at=now.isoformat(),stage=args.stage,status='success'))
        return 0
    except (CollectionError,OSError,ValueError,KeyError,TypeError) as error:
        reason=str(error) if isinstance(error,CollectionError) else type(error).__name__
        log('외환 수집 실패 · 기존 자료 유지',reason)
        atomic_json(ROOT/'failure.json',dict(at=now.isoformat(),stage=args.stage,reason=reason));return 1
    finally:lock.unlink()

if __name__=='__main__':raise SystemExit(main())
