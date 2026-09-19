"""Collect an independent FSC corpus from the official API; never read tax data."""
from __future__ import annotations
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo
import json
from pathlib import Path
import sys
from core.fsc_collection import (CollectionError, LawTransport, atomic_json, discover,
                                 collect_sources, FSC_ORG, FSC_AUTHORITY, ORG_SOURCE)
from core.fsc_credentials import law_api_key
from core.fsc_graph import build_fsc_graph, graph_report
from core.fsc_universe import validate_bundle

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'output/fsc-universe'


def run(args: argparse.Namespace) -> int:
    output = args.output.resolve()
    if not output.is_relative_to(OUTPUT.resolve()):
        raise CollectionError('output-must-stay-in-fsc-universe')
    today = datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y%m%d')
    if args.build_only:
        source = json.loads((output / 'source-checkpoint.json').read_text(encoding='utf-8'))
    else:
        request = LawTransport(law_api_key())
        if args.reuse_inventory:
            inventory = json.loads((output / 'inventory.json').read_text(encoding='utf-8'))
            if inventory['as_of'] != today or inventory['org'] != FSC_ORG:
                raise CollectionError('inventory-date-or-authority-mismatch')
            targets = {'eflaw'} if args.statutes_only else {'eflaw', 'admrul'}
            if set(inventory['layers']) - {'fss_admrul'} != targets:
                raise CollectionError('inventory-layer-mismatch')
        else:
            layers = {}
            for target in (('eflaw',) if args.statutes_only else ('eflaw', 'admrul')):
                layers[target] = discover(request, target, as_of=today)
                print(f"목록 확인 · {target} · {layers[target]['received']}건", flush=True)
            inventory = dict(schema_version=1, as_of=today, org=FSC_ORG,
                             managing_authority=FSC_AUTHORITY, org_source=ORG_SOURCE, layers=layers)
            atomic_json(output / 'inventory.json', inventory)
        if args.with_sector_rules:
            from core.fsc_bylaws import discover_bylaws
            inventory['layers']['fss_admrul'] = discover_bylaws(request, as_of=today)
            print(f"시행세칙 목록 확인 · {inventory['layers']['fss_admrul']['received']}건", flush=True)
            atomic_json(output / 'inventory.json', inventory)
        if args.inventory_only:
            return 0
        def progress(done, total, record, status):
            if done % 20 == 0 or done == total or status.startswith('failed'):
                print(f"본문 {done}/{total} · {record['name']} · {status}", flush=True)
        source = collect_sources(request, inventory, cache_dir=output / 'body-cache', workers=3, progress=progress)
        atomic_json(output / 'source-checkpoint.json', source)
    from core.fsc_administrative import prepare_source
    source = prepare_source(source)
    if 'fss_admrul' in source.get('inventory',{}).get('layers',{}):
        source['coverage']['fss_rules'] = 'selected-bylaws-article-indexed'
    required = [r for r in source.get('administrative_rules',[]) if r.get('collection_scope') == 'fss-sector-bylaws' or r['name'] in ('보험업감독규정','은행업감독규정','금융투자업규정')]
    if any(r.get('body_status') != 'indexed-administrative-text' for r in required):
        raise CollectionError('required-sector-rule-not-indexed')
    graph = build_fsc_graph(source)
    bundle = validate_bundle(dict(source=source, graph=graph, report=graph_report(graph)))
    atomic_json(output / 'bundle.json', bundle)
    report = {k:v for k,v in bundle['report'].items() if k != 'focus_law_names'}
    report['statute_articles'] = sum(len(l['articles']) for l in source['laws'])
    report['scheduled_not_collected'] = len(source.get('scheduled', []))
    atomic_json(output / 'report.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--inventory-only', action='store_true', help='statute list, then administrative-rule list; no bodies')
    modes.add_argument('--build-only', action='store_true', help='rebuild from the FSC source checkpoint; no network')
    parser.add_argument('--reuse-inventory', action='store_true', help='reuse today\'s verified official inventory')
    parser.add_argument('--statutes-only', action='store_true', help='explicitly omit administrative rules')
    parser.add_argument('--with-sector-rules', action='store_true', help='collect the declared FSS sector bylaw scope')
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args(argv)
    if args.statutes_only and args.with_sector_rules:
        parser.error('--statutes-only and --with-sector-rules are mutually exclusive')
    if args.build_only and (args.reuse_inventory or args.statutes_only or args.with_sector_rules):
        parser.error('--build-only uses the source checkpoint without changing its scope')
    try:
        return run(args)
    except CollectionError as error:
        code = str(error)
        if code == 'missing-law-api-key':
            print(f"로컬 설정: {ROOT / '.env'} · LAW_API_KEY=", file=sys.stderr)
    except (OSError, ValueError, KeyError, TypeError):
        code = 'local-input-or-schema-error'
    print('FSC 작업 중단: ' + code + ' · 기존 완료 번들은 유지됩니다.', file=sys.stderr)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
