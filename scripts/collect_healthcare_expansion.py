"""Stage the approved healthcare expansion without replacing the active corpus."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
from urllib.parse import quote, quote_plus
from uuid import uuid4
from zoneinfo import ZoneInfo

from core.fsc_collection import CollectionError, LawTransport, atomic_json, norm, ymd
from core.fsc_credentials import law_api_key
from core.medical_annexes import attach, collect
from core.mofe_collection import collect_sources, discover_inventory, prepare_source
from core.mofe_universe import assessment, build_graph, report, validate_bundle
from core.mofe_profiles import WORK_PROFILES, selected


STAGES = ('inventory', 'bodies', 'build')


def check_inventory(inventory, stamp):
    """A staged inventory cannot broaden the approved medical collection."""
    if inventory['domain'] != 'medical' or inventory['as_of'] != stamp:
        raise CollectionError('healthcare-inventory-domain-or-date-mismatch')
    current = []
    for item in inventory['records']:
        if (item.get('category') != 'medical' or item['state'] not in ('current-candidate', 'scheduled')
                or not selected('medical', item['name'], item['managing_authority'], item['provider'])):
            raise CollectionError('healthcare-inventory-outside-declared-scope')
        effective = ymd(item['effective'])
        if (effective <= stamp) != (item['state'] == 'current-candidate'):
            raise CollectionError('healthcare-inventory-edition-state-mismatch')
        if item['state'] == 'current-candidate':
            current.append(norm(item['name']))
    profile = WORK_PROFILES['medical']
    required = {norm(name) for name in (*profile['required'], *profile['required_rules'])}
    if len(current) != len(set(current)) or not required <= set(current):
        raise CollectionError('healthcare-inventory-required-documents-missing-or-duplicated')


def check_source(source, stamp):
    if source['domain'] != 'medical' or source['built_at'] != stamp:
        raise CollectionError('healthcare-source-domain-or-date-mismatch')
    check_inventory(source['inventory'], stamp)
    docs = source['laws'] + source['administrative_rules']
    actual = [norm(doc['name']) for doc in docs]
    expected = {norm(item['name']) for item in source['inventory']['records']
                if item['state'] == 'current-candidate'}
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise CollectionError('healthcare-source-inventory-scope-mismatch')
    for doc in docs:
        if (doc.get('category') != 'medical'
                or not selected('medical', doc['name'], doc['managing_authority'], doc['provider'])):
            raise CollectionError('healthcare-source-outside-declared-scope')


def save_once(path, value):
    if path.exists():
        if json.loads(path.read_text(encoding='utf-8')) != value:
            raise ValueError('Existing staged result differs; choose a new destination')
        return
    atomic_json(path, value)


def run(stage, destination, stamp):
    if stage not in STAGES:
        raise ValueError('Unsupported healthcare collection stage')
    stamp = ymd(stamp)
    if stamp > datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y%m%d'):
        raise ValueError('Future collection date')
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    lock = destination / 'collect.lock'
    try:
        handle = lock.open('x')
    except FileExistsError:
        print('다른 실행의 수집 잠금을 보존합니다.', flush=True)
        return 2
    key = None
    lock_token = uuid4().hex
    started = datetime.now(ZoneInfo('Asia/Seoul')).isoformat()
    try:
        with handle:
            handle.write(lock_token)
        key = law_api_key()
        def redacted(value):
            text = str(value)
            if key:
                for secret in sorted({key, quote(key, safe=''), quote_plus(key, safe='')}, key=len, reverse=True):
                    text = text.replace(secret, '[redacted]')
            return text
        def log(*parts):
            print('보건의료 · ' + ' · '.join(redacted(part) for part in parts), flush=True)
        def read(name):
            return json.loads((destination / name).read_text(encoding='utf-8'))
        def guard(value):
            pending = [value]
            while pending:
                item = pending.pop()
                if isinstance(item, dict):
                    pending.extend(item.keys())
                    pending.extend(item.values())
                elif isinstance(item, (list, tuple)):
                    pending.extend(item)
                elif isinstance(item, str) and redacted(item) != item:
                    raise CollectionError('credential-found-in-output')
        def save_outputs(outputs):
            # Preflight every immutable output before writing any of this stage.
            for name, value in outputs.items():
                guard(value)
                path = destination / name
                if path.exists() and read(name) != value:
                    raise ValueError('Existing staged result differs; choose a new destination')
            for name, value in outputs.items():
                save_once(destination / name, value)
        def transport():
            if not key:
                raise CollectionError('missing-law-api-key')
            return LawTransport(key, attempts=3, timeout=30, reuse_connections=True)
        if stage == 'inventory':
            inventory = discover_inventory(transport(), 'medical', stamp, log)
            check_inventory(inventory, stamp)
            outputs = {'inventory.json': inventory}
        elif stage == 'bodies':
            inventory = read('inventory.json')
            guard(inventory)
            check_inventory(inventory, stamp)
            def checked_collector(*args, **kwargs):
                document = collect(*args, **kwargs)
                guard(document)  # The shared collector writes its cache next.
                return document
            source = collect_sources(transport(), inventory, destination / 'body-cache',
                                     log, document_collector=checked_collector)
            check_source(source, stamp)
            outputs = {'source.json': source}
        else:
            source = read('source.json')
            guard(source)
            check_source(source, stamp)
            source = prepare_source(source)
            # The existing four annexes remain pinned to their reviewed owners.
            source = attach(source)
            bundle = validate_bundle(dict(source=source, graph=build_graph(source)), 'medical')
            bundle['assessment'] = assessment(bundle)
            if bundle['assessment']['decision'] != 'limited-release':
                raise CollectionError('healthcare-usefulness-gate-hold')
            outputs = {'validated-bundle.json': bundle, 'summary.json': report(bundle)}
        save_outputs(outputs)
        completed = datetime.now(ZoneInfo('Asia/Seoul')).isoformat()
        # failure.json is retained as historical evidence; this is the latest outcome.
        atomic_json(destination / 'last-run.json', dict(stage=stage, status='success',
            started_at=started, completed_at=completed, as_of=stamp,
            outputs={name: hashlib.sha256((destination / name).read_bytes()).hexdigest() for name in outputs}))
        if stage == 'build':
            log('검증 완료', '문서', bundle['assessment']['documents'],
                '조문', bundle['assessment']['articles'])
        return 0
    except (CollectionError, OSError, ValueError, KeyError, TypeError) as error:
        reason = str(error) if isinstance(error, CollectionError) else type(error).__name__
        if key:
            for secret in sorted({key, quote(key, safe=''), quote_plus(key, safe='')}, key=len, reverse=True):
                reason = reason.replace(secret, '[redacted]')
        failure = dict(stage=stage, status='failure', started_at=started,
                       completed_at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(), as_of=stamp, reason=reason)
        atomic_json(destination / 'failure.json', failure)
        atomic_json(destination / 'last-run.json', failure)
        print('보건의료 수집 중단 · 기존 자료 보존 · ' + reason, flush=True)
        return 1
    finally:
        # Never remove a replacement lock created by another execution.
        if lock.exists() and lock.read_text(encoding='utf-8') == lock_token:
            lock.unlink()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=STAGES, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--date')
    args = parser.parse_args()
    today = datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y%m%d')
    stamp = ymd(args.date or today)
    if stamp > today:
        raise ValueError('Future collection date')
    raise SystemExit(run(args.stage, args.destination, stamp))
