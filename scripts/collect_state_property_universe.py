"""Collect national property in a separate folder; retain pinned edition evidence."""
import argparse
from datetime import datetime
import json
import shutil
from pathlib import Path
from zoneinfo import ZoneInfo
from core.fsc_collection import LawTransport, CollectionError, atomic_json
from core.fsc_credentials import law_api_key
from core.state_property_collection import discover_inventory, collect_sources, discover_related, SPECIAL
from core.state_property_special import parse_annex, resolve_rows

ROOT = Path(__file__).resolve().parents[1] / 'output/state_property-universe'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['inventory','core','annex','related','build'], required=True)
    args = parser.parse_args()
    now = datetime.now(ZoneInfo('Asia/Seoul')); stamp = now.strftime('%Y%m%d')
    staging = ROOT / 'staging' / stamp
    ROOT.mkdir(parents=True, exist_ok=True)
    lock = ROOT / 'collect.lock'
    try: handle = lock.open('x')
    except FileExistsError:
        print('다른 수집이 실행 중입니다. 기존 잠금을 보존합니다.'); return 2
    try:
        with handle: handle.write(now.isoformat())
        key = law_api_key()
        if args.stage not in ('annex','build') and not key: raise CollectionError('missing-law-api-key')
        request = LawTransport(key, reuse_connections=True) if key else None
        def log(*items): print(' · '.join(map(str,items)), flush=True)
        if args.stage == 'inventory':
            inventory = discover_inventory(request,stamp,log)
            atomic_json(staging/'inventory.json',inventory)
            log('목록 확인 완료',sum(x['state']=='current-candidate' for x in inventory['records']))
        elif args.stage=='core':
            inventory = json.loads((staging/'inventory.json').read_text(encoding='utf-8'))
            source = collect_sources(request,inventory,staging/'body-cache',log)
            if key in json.dumps(source,ensure_ascii=False): raise CollectionError('credential-found-in-output')
            atomic_json(staging/'core-source.json',source)
            for doc in source['laws']:
                log(doc['name'], '조문',len(doc['articles']), '별표',len(doc['annexes']))
        elif args.stage=='annex':
            source=json.loads((staging/'core-source.json').read_text(encoding='utf-8'))
            register=parse_annex(next(d for d in source['laws'] if d['name']==SPECIAL),source['built_at'])
            atomic_json(staging/'special-cases.json',register)
            from collections import Counter
            log('특례 별표',len(register['rows']),'행',dict(Counter(r['status'] for r in register['rows'])))
        elif args.stage=='related':
            source=json.loads((staging/'core-source.json').read_text(encoding='utf-8'))
            register=json.loads((staging/'special-cases.json').read_text(encoding='utf-8'))
            inventory=discover_related(request,register,staging/'related-inventory-cache',log)
            atomic_json(staging/'related-inventory.json',inventory)
            related=collect_sources(request,inventory,staging/'body-cache',log)
            names={d['name'] for d in source['laws']}
            source['laws'] += [d for d in related['laws'] if d['name'] not in names]
            source['related_laws']=[d['name'] for d in related['laws']]
            source['related_inventory']=inventory
            source['scheduled']+=related['scheduled']
            register=resolve_rows(register,source['laws'])
            source['special_cases']=register
            if key in json.dumps(source,ensure_ascii=False):raise CollectionError('credential-found-in-output')
            atomic_json(staging/'source.json',source)
            log('특례 근거 법령 수집',len(related['laws']),'미수집 법령명',len(inventory['missing']))
        elif args.stage=='build':
            from core.state_property_collection import prepare_source
            from core.state_property_universe import build_graph,validate_bundle,report,BUNDLE
            source=prepare_source(json.loads((staging/'source.json').read_text(encoding='utf-8')))
            graph=build_graph(source);bundle=validate_bundle(dict(source=source,graph=graph))
            if key and key in json.dumps(bundle,ensure_ascii=False):raise CollectionError('credential-found-in-output')
            if BUNDLE.exists():
                history=ROOT/'history'/now.strftime('%Y%m%d-%H%M%S')/'bundle.json'
                history.parent.mkdir(parents=True,exist_ok=False);shutil.copy2(BUNDLE,history)
            atomic_json(BUNDLE,bundle);summary=report(bundle);atomic_json(ROOT/'summary.json',summary)
            print(json.dumps(summary,ensure_ascii=False,indent=2))
        return 0
    except (CollectionError,OSError,ValueError,KeyError,TypeError) as error:
        reason = str(error) if isinstance(error,CollectionError) else type(error).__name__
        print('국유재산 수집 실패 · 기존 자료 유지 · '+reason,flush=True)
        atomic_json(ROOT/'failure.json',dict(at=now.isoformat(),stage=args.stage,reason=reason))
        return 1
    finally: lock.unlink()


if __name__=='__main__':raise SystemExit(main())
