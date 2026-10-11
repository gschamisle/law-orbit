"""Scheduled, isolated corpus refreshes with validation and atomic publication."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
import json
import os
from pathlib import Path
import shutil
from zoneinfo import ZoneInfo

from core.fsc_collection import (CollectionError, LawTransport, atomic_json, collect_sources,
                                 discover, FSC_ORG, FSC_AUTHORITY, ORG_SOURCE)
from core.fsc_credentials import law_api_key
from core.law_universe import ROOT, GRAPH, SOURCES

STATE_DIR = ROOT / 'output/law-updates'
TAX_BUNDLE = ROOT / 'output/tax-universe/bundle.json'
FSC_BUNDLE = ROOT / 'output/fsc-universe/bundle.json'


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def current_bundle(domain: str) -> dict:
    if domain == 'tax':
        if TAX_BUNDLE.exists():
            data = read_json(TAX_BUNDLE)
            return {'source': data['source'], 'graph': {k:v for k,v in data.items() if k != 'source'}}
        return {'source': read_json(SOURCES), 'graph': read_json(GRAPH)}
    from core.fsc_universe import load_bundle
    return load_bundle(FSC_BUNDLE)


def source_documents(source: dict) -> list[dict]:
    return source['laws'] + source.get('administrative_rules', [])


def document_identity(domain: str, doc: dict) -> str:
    """Use the provider's stable document ID, never its title or edition serial."""
    if domain == 'fsc':
        provider, document_id = doc.get('provider'), doc.get('document_id')
        if (provider not in ('eflaw', 'admrul') or not isinstance(document_id, str)
                or not document_id.isdigit() or doc.get('uid') != f'{provider}:{document_id}'
                or (provider == 'eflaw' and str(doc.get('law_id', '')) != document_id)):
            raise CollectionError('invalid-document-identity')
        return doc['uid']
    law_id = doc.get('law_id')
    if isinstance(law_id, bool) or not isinstance(law_id, (str, int)) or not str(law_id).isdigit():
        raise CollectionError('invalid-document-identity')
    uid = f'eflaw:{law_id}'
    if ((doc.get('provider') is not None and doc['provider'] != 'eflaw')
            or (doc.get('document_id') is not None and str(doc['document_id']) != str(law_id))
            or (doc.get('uid') is not None and doc['uid'] != uid)):
        raise CollectionError('invalid-document-identity')
    return uid


def document_index(domain: str, source: dict) -> dict[str, dict]:
    documents, names = {}, set()
    for doc in source_documents(source):
        identity = document_identity(domain, doc)
        if identity in documents or not doc.get('name') or doc['name'] in names:
            raise CollectionError('duplicate-document-identity-or-name')
        documents[identity] = doc
        names.add(doc['name'])
    return documents


def renamed_documents(domain: str, source: dict, previous: dict) -> list[dict]:
    old, new = document_index(domain, previous), document_index(domain, source)
    return [{'uid': uid, 'previous_name': old[uid]['name'], 'name': new[uid]['name']}
            for uid in sorted(old.keys() & new.keys()) if old[uid]['name'] != new[uid]['name']]


def current_signature(source: dict) -> list[tuple]:
    result = []
    for law in source_documents(source):
        if law.get('provider') in ('eflaw', 'admrul'):
            result.append((law['uid'], law['edition_key']))
        else:
            result.append((str(law['law_id']), str(law['mst']), law['effective']))
    return sorted(result)


def inventory_signature(domain: str, inventory: dict) -> list[tuple]:
    if domain == 'tax':
        return sorted((str(r['law_id']), str(r['mst']), r['effective']) for r in inventory['records'])
    return sorted((r['uid'], r['edition_key']) for layer in inventory['layers'].values()
                  for r in layer['records'] if r['state'] != 'scheduled')


def full_refresh_due(today: date, last_full: str) -> bool:
    last = date.fromisoformat(last_full)
    return last < today and (today.weekday() == 0 or (today - last).days >= 7)


def tax_inventory(source: dict, key: str, today: str) -> dict:
    from scripts.collect_law_universe import discover as tax_discover
    jobs = sorted({(law['family'], law['category']) for law in source['laws']})
    with ThreadPoolExecutor(max_workers=3) as pool:
        batches = list(pool.map(lambda job: tax_discover(*job, key), jobs))
    by_id = {}
    for rows in batches:
        for row in rows:
            if not row.get('law_id') or not row.get('mst') or len(row.get('effective', '')) != 8:
                raise CollectionError('tax-invalid-edition')
            if row['effective'] > today:
                continue
            previous = by_id.get(row['law_id'])
            if previous and (previous['effective'], int(previous['mst'])) > (row['effective'], int(row['mst'])):
                continue
            by_id[row['law_id']] = row
    records = sorted(by_id.values(), key=lambda r:r['name'])
    previous_ids = set(document_index('tax', source))
    discovered_ids = {document_identity('tax', record) for record in records}
    if not records or previous_ids - discovered_ids:
        raise CollectionError('tax-scope-shrank-review-required')
    return {'as_of':today, 'records':records}


def fsc_inventory(request: LawTransport, today: str) -> dict:
    from core.fsc_bylaws import discover_bylaws
    layers = {target:discover(request, target, as_of=today) for target in ('eflaw', 'admrul')}
    layers['fss_admrul'] = discover_bylaws(request, as_of=today)
    return dict(schema_version=1, as_of=today, org=FSC_ORG,
                managing_authority=FSC_AUTHORITY, org_source=ORG_SOURCE, layers=layers)


def collect_candidate(domain: str, inventory: dict, key: str, staging: Path) -> dict:
    staging.mkdir(parents=True, exist_ok=True)
    if domain == 'tax':
        from scripts.collect_law_universe import collect
        from core.universe_builder import build_tax_universe
        cache = staging / 'body-cache'
        cache.mkdir(exist_ok=True)
        with ThreadPoolExecutor(max_workers=3) as pool:
            laws = list(pool.map(lambda r:collect(r, key, cache, True), inventory['records']))
        records = {r['law_id']:r for r in inventory['records']}
        if any(l['effective'] != records[l['law_id']]['effective'] for l in laws):
            raise CollectionError('tax-edition-changed-during-collection')
        source = {'built_at':date.fromisoformat(inventory['as_of']).isoformat(),
                  'provider':'법제처 시행일 기준 Open API (eflaw)', 'laws':sorted(laws,key=lambda l:l['name'])}
        atomic_json(staging / 'source-checkpoint.json', source)
        return {'source':source, 'graph':build_tax_universe(source)}
    from core.fsc_administrative import prepare_source
    from core.fsc_graph import build_fsc_graph, graph_report
    source = collect_sources(LawTransport(key), inventory, cache_dir=staging/'body-cache', workers=3)
    source = prepare_source(source)
    source['coverage']['fss_rules'] = 'selected-bylaws-article-indexed'
    required = [r for r in source.get('administrative_rules',[]) if r.get('collection_scope') == 'fss-sector-bylaws'
                or r['name'] in ('보험업감독규정','은행업감독규정','금융투자업규정')]
    if any(r.get('body_status') != 'indexed-administrative-text' for r in required):
        raise CollectionError('required-sector-rule-not-indexed')
    atomic_json(staging / 'source-checkpoint.json', source)
    graph = build_fsc_graph(source)
    return {'source':source, 'graph':graph, 'report':graph_report(graph)}


def validate_candidate(domain: str, candidate: dict, previous: dict, today: str) -> None:
    source, graph = candidate['source'], candidate['graph']
    old_docs = document_index(domain, previous['source'])
    indexed_docs = document_index(domain, source)
    if old_docs.keys() - indexed_docs.keys():
        raise CollectionError('document-scope-shrank-review-required')
    docs = {doc['name']: doc for doc in indexed_docs.values()}
    if graph['built_at'] != source['built_at'] or not graph.get('edges'):
        raise CollectionError('graph-date-or-empty-edges')
    if domain == 'fsc':
        from core.fsc_universe import validate_bundle
        validate_bundle(candidate)
    else:
        if (set(graph['laws']) != set(docs) or any(d['category'] not in ('tax','external') for d in docs.values())
                or set(graph['tax_laws']) != {d['name'] for d in docs.values() if d['category']=='tax'}):
            raise CollectionError('tax-source-graph-scope-mismatch')
    for identity, doc in indexed_docs.items():
        effective = doc['effective'].replace('-', '')
        prior = old_docs.get(identity)
        if effective > today or (prior is not None and effective < prior['effective'].replace('-', '')):
            raise CollectionError('future-or-regressed-edition')
        if prior is not None and prior.get('articles') and not doc.get('articles'):
            raise CollectionError('previously-indexed-document-lost-articles')
    texts = {(d['name'],a['jo']):a['text'] for d in docs.values() for a in d.get('articles',[])}
    for edge in graph['edges'] + graph.get('external_references',[]):
        if edge.get('source_granularity') == 'annex':
            continue
        text = texts.get((edge['source_law'],edge['source_jo']))
        if text is None or text[edge['source_start']:edge['source_end']] != edge['cite_raw']:
            raise CollectionError('citation-evidence-mismatch')


def publish(domain: str, candidate: dict, previous: dict, destination: Path, today: str, run_id: str) -> None:
    validate_candidate(domain, candidate, previous, today)
    destination.parent.mkdir(parents=True, exist_ok=True)
    history = destination.parent/'history'/run_id/'bundle.json'
    if history.exists():
        raise CollectionError('backup-already-exists')
    history.parent.mkdir(parents=True)
    if destination.exists():
        shutil.copy2(destination, history)
    else:
        atomic_json(history, {**previous['graph'],'source':previous['source']})
    # Tax source and graph now share one atomic file; legacy data stays untouched.
    value = {**candidate['graph'],'source':candidate['source']} if domain == 'tax' else candidate
    atomic_json(destination, value)


def run(*, mode: str = 'auto', check_only: bool = False) -> dict:
    now = datetime.now(ZoneInfo('Asia/Seoul'))
    today, ymd = now.date(), now.strftime('%Y%m%d')
    run_id = now.strftime('%Y%m%d-%H%M%S-%f')
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    lock = STATE_DIR/'update.lock'
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return {'status':'busy', 'message':'다른 갱신이 실행 중이거나 이전 작업의 잠금을 확인해야 합니다.'}
    os.close(fd)
    report = {'run_id':run_id, 'checked_at':now.isoformat(), 'check_only':check_only, 'domains':{}}
    state_path = STATE_DIR/'state.json'
    try:
        key = law_api_key()
        if not key:
            raise CollectionError('missing-law-api-key')
        state = read_json(state_path) if state_path.exists() else {'domains':{}}
        for domain, destination in (('tax',TAX_BUNDLE), ('fsc',FSC_BUNDLE)):
            try:
                previous = current_bundle(domain)
                prior_state = state['domains'].get(domain,{})
                baseline = date.fromisoformat(previous['source']['built_at']).isoformat()
                weekly = mode == 'full' or (mode == 'auto' and full_refresh_due(today, prior_state.get('last_full',baseline)))
                inventory = tax_inventory(previous['source'],key,ymd) if domain == 'tax' else fsc_inventory(LawTransport(key),ymd)
                staging = destination.parent/'staging'/run_id
                atomic_json(staging/'inventory.json',inventory)
                changed = inventory_signature(domain,inventory) != current_signature(previous['source'])
                due = weekly or changed
                result = {'status':'update-available' if due else 'unchanged', 'editions_changed':changed,
                          'weekly_refresh':weekly, 'documents':len(source_documents(previous['source']))}
                if due and not check_only:
                    candidate = collect_candidate(domain,inventory,key,staging)
                    renames = renamed_documents(domain, candidate['source'], previous['source'])
                    publish(domain,candidate,previous,destination,ymd,run_id)
                    result.update(status='updated',documents=len(source_documents(candidate['source'])),
                                  indexed_documents=len(candidate['graph']['laws']),edges=len(candidate['graph']['edges']))
                    if renames:
                        result['renamed_documents'] = renames
                    prior_state['last_update'] = today.isoformat()
                    if weekly: prior_state['last_full'] = today.isoformat()
                if not check_only:
                    prior_state['last_checked'] = today.isoformat()
                    state['domains'][domain] = prior_state
                    atomic_json(state_path,state)
                report['domains'][domain] = result
            except (CollectionError, OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
                # Error details can contain URLs with credentials. Keep only approved codes.
                code = str(error) if isinstance(error,CollectionError) else type(error).__name__
                report['domains'][domain] = {'status':'failed', 'code':code, 'previous_data_retained':True}
        report['status'] = 'failed' if any(d['status']=='failed' for d in report['domains'].values()) else 'ok'
        atomic_json(STATE_DIR/'runs'/f'{run_id}.json',report)
        atomic_json(STATE_DIR/'latest.json',report)
        return report
    finally:
        lock.unlink(missing_ok=True)
