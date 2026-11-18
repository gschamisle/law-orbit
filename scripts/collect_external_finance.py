"""Collect four named legal families into a new, immutable local staging area.

Current bodies and future-edition metadata are intentionally separate. KIC bodies
are provided as a companion source for forex, never as an export-finance product.
"""
import argparse
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from core.export_finance_profile import (
    COLLECTION_FAMILIES, EXPORT_FAMILIES, KIC, REQUIRED_ALL, family, selected,
)
from core.fsc_collection import CollectionError, LawTransport, atomic_json, norm, ymd
from core.fsc_credentials import law_api_key
from core.procurement_collection import (
    authorities, collect_document, collect_sources, discover_query, record,
)
from scripts.collect_candidate_domains import (
    check_cache, check_inventory, check_source, guard, redact, save_once,
)

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = 'export_finance'


def discover(request, stamp, progress=None):
    current, scheduled, layers = {}, {}, []
    def factory(row, provider, as_of):
        return record(row, provider, as_of, selector=selected, domain=DOMAIN)
    for query in COLLECTION_FAMILIES:
        for mode in ('current', 'scheduled'):
            def scoped_request(endpoint, params):
                return request(endpoint, {**params, 'nw': 3 if mode == 'current' else 2})
            layer = discover_query(scoped_request, 'eflaw', query, stamp, record_factory=factory)
            layer['edition_scope'] = mode
            layers.append(layer)
            for item in layer['records']:
                if (mode == 'scheduled') != (item['state'] == 'scheduled'):
                    raise CollectionError('external-finance-list-state-mismatch')
                target = scheduled if mode == 'scheduled' else current
                identity = item['edition_key'] if mode == 'scheduled' else item['uid']
                if identity in target and target[identity] != item:
                    raise CollectionError('external-finance-conflicting-editions')
                target[identity] = item
            if progress:
                progress(query, mode, layer['received'], len(layer['records']))
    actual = {norm(item['name']) for item in current.values()}
    if {norm(n) for n in REQUIRED_ALL} != actual:
        raise CollectionError('external-finance-required-family-or-subordinate-missing')
    inventory = dict(domain=DOMAIN, as_of=stamp,
        scope='four-exact-founding-law-families; current-bodies; scheduled-metadata-only',
        records=sorted([*current.values(), *scheduled.values()], key=lambda d: (d['name'], d['effective'])),
        layers=layers, excluded=[], unavailable_selected_rules=[])
    check_inventory(inventory, DOMAIN, stamp)
    return inventory


def subset(source, families):
    result = deepcopy(source)
    result['laws'] = [doc for doc in result['laws'] if family(doc['name']) in families]
    result['scheduled'] = [doc for doc in result['scheduled'] if family(doc['name']) in families]
    result['inventory']['records'] = [doc for doc in result['inventory']['records']
                                    if family(doc['name']) in families]
    result['inventory']['scope'] += '; selected-families=' + ','.join(families)
    return result


def run(stage, destination, stamp):
    destination = Path(destination).resolve()
    if stage not in ('inventory', 'bodies', 'build'):
        raise ValueError('Unsupported collection stage')
    if (not destination.is_relative_to((ROOT / 'output').resolve())
            or not destination.name.startswith('external-finance-' + stamp)):
        raise ValueError('Use a new folder inside this worktree output')
    destination.mkdir(parents=True, exist_ok=True)
    lock = destination / 'collect.lock'
    try:
        handle = lock.open('x', encoding='utf-8')
    except FileExistsError:
        print('다른 실행 잠금을 보존합니다.', flush=True)
        return 2
    token, key = uuid4().hex, ''
    started = datetime.now(ZoneInfo('Asia/Seoul')).isoformat()
    receipt = destination / 'runs' / (datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + stage + '-' + token + '.json')
    try:
        with handle:
            handle.write(token)
        key = law_api_key()
        def log(*parts):
            print(' · '.join(redact(part, key) for part in parts), flush=True)
        def read(name):
            value = json.loads((destination / name).read_text(encoding='utf-8'))
            guard(value, key)
            return value
        if stage == 'inventory':
            outputs = {'inventory.json': discover(LawTransport(key, attempts=3, timeout=30, reuse_connections=True), stamp, log)}
        elif stage == 'bodies':
            inventory = read('inventory.json')
            check_inventory(inventory, DOMAIN, stamp)
            check_cache(destination / 'body-cache', inventory, key)
            def authority_check(item, actual):
                return actual == authorities(item['managing_authority']) and selected(item['name'], ','.join(sorted(actual)), item['provider'])
            def checked_collect(*args, **kwargs):
                doc = collect_document(*args, **kwargs)
                guard(doc, key)
                return doc
            source = collect_sources(LawTransport(key, attempts=3, timeout=30, reuse_connections=True),
                inventory, destination / 'body-cache', log,
                authority_validator=authority_check, document_collector=checked_collect)
            check_source(source, DOMAIN, stamp)
            outputs = {'source.json': source, 'kic-source.json': subset(source, (KIC,))}
        else:
            from core.mofe_collection import prepare_source
            from core.mofe_universe import assessment, build_graph, report, validate_bundle
            source = read('source.json')
            check_source(source, DOMAIN, stamp)
            prepared = prepare_source(subset(source, EXPORT_FAMILIES))
            check_source(prepared, DOMAIN, stamp)
            bundle = validate_bundle(dict(source=prepared, graph=build_graph(prepared)), DOMAIN)
            bundle['assessment'] = assessment(bundle)
            if bundle['assessment']['decision'] != 'limited-release':
                raise CollectionError('external-finance-usefulness-gate-hold')
            outputs = {'validated-bundle.json': bundle, 'summary.json': report(bundle)}
        for name, value in outputs.items():
            guard(value, key)
            if (destination / name).exists() and read(name) != value:
                raise ValueError('Existing result differs; choose a new destination')
        for name, value in outputs.items():
            save_once(destination / name, value)
        atomic_json(receipt, dict(status='success', stage=stage, as_of=stamp, started_at=started,
            completed_at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
            outputs={name: hashlib.sha256((destination / name).read_bytes()).hexdigest() for name in outputs}))
        log(stage, '완료')
        return 0
    except (CollectionError, OSError, ValueError, KeyError, TypeError) as error:
        reason = redact(str(error), key) if isinstance(error, CollectionError) else type(error).__name__
        atomic_json(receipt, dict(status='failure', stage=stage, as_of=stamp, started_at=started, reason=reason))
        print('수집 중단 · 기존 자료 보존 · ' + reason, flush=True)
        return 1
    finally:
        if lock.exists() and lock.read_text(encoding='utf-8') == token:
            lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=('inventory', 'bodies', 'build'), required=True)
    parser.add_argument('--dest', type=Path)
    parser.add_argument('--as-of')
    args = parser.parse_args()
    today = datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y%m%d')
    stamp = ymd(args.as_of or today)
    if stamp > today:
        raise ValueError('Future collection date')
    return run(args.stage, args.dest or ROOT / 'output' / ('external-finance-' + stamp), stamp)


if __name__ == '__main__':
    raise SystemExit(main())
