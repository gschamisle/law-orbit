"""Collect a separate environment corpus and publish validated evidence only."""
import argparse
from datetime import datetime
import json
import shutil
from zoneinfo import ZoneInfo
from core.fsc_collection import LawTransport, CollectionError, atomic_json
from core.fsc_credentials import law_api_key
from core.environment_collection import discover_inventory, collect_sources, prepare_source
from core.environment_universe import BUNDLE, build_graph, report, validate_bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['inventory','collect','build','all'], default='all')
    args=parser.parse_args()
    now=datetime.now(ZoneInfo('Asia/Seoul')); stamp=now.strftime('%Y%m%d')
    root=BUNDLE.parent; staging=root/'staging'/stamp
    root.mkdir(parents=True,exist_ok=True)
    lock=root/'collect.lock'
    try: handle=lock.open('x')
    except FileExistsError:
        print('다른 수집이 실행 중입니다. 잠금을 보존합니다.'); return 2
    try:
        with handle: handle.write(now.isoformat())
        key=law_api_key()
        if args.stage!='build' and not key: raise CollectionError('missing-law-api-key')
        request=LawTransport(key) if key else None
        def log(*items): print(' · '.join(map(str,items)),flush=True)
        if args.stage in ('inventory','all'):
            inventory=discover_inventory(request,stamp,log)
            atomic_json(staging/'inventory.json',inventory)
        else: inventory=json.loads((staging/'inventory.json').read_text(encoding='utf-8'))
        if args.stage in ('collect','all'):
            source=collect_sources(request,inventory,staging/'body-cache',log)
            atomic_json(staging/'source.json',source)
        if args.stage in ('build','all'):
            if args.stage=='build':source=json.loads((staging/'source.json').read_text(encoding='utf-8'))
            source=prepare_source(source); graph=build_graph(source)
            bundle=validate_bundle(dict(source=source,graph=graph))
            if key and key in json.dumps(bundle,ensure_ascii=False):
                raise CollectionError('credential-found-in-output')
            if BUNDLE.exists():
                history=root/'history'/now.strftime('%Y%m%d-%H%M%S')/'bundle.json'
                history.parent.mkdir(parents=True,exist_ok=False);shutil.copy2(BUNDLE,history)
            atomic_json(BUNDLE,bundle)
            summary=report(bundle);atomic_json(root/'summary.json',summary)
            print(json.dumps(summary,ensure_ascii=False,indent=2))
        return 0
    except (CollectionError,OSError,ValueError,KeyError,TypeError) as error:
        reason=str(error) if isinstance(error,CollectionError) else type(error).__name__
        print('환경·화학안전 수집 실패 · 기존 자료 유지 · '+reason,flush=True)
        atomic_json(root/'failure.json',dict(at=now.isoformat(),stage=args.stage,reason=reason))
        return 1
    finally:lock.unlink()


if __name__=='__main__':raise SystemExit(main())
