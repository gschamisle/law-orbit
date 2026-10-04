"""Stage selected new fields without replacing any active collection.

Each stage is independently resumable. Inventory/body/bundle outputs are immutable;
separate run receipts record outcomes. A conflicting lock is never removed.
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
from urllib.parse import quote, quote_plus
from uuid import uuid4
from zoneinfo import ZoneInfo

from core.fsc_collection import CollectionError, LawTransport, atomic_json, norm, require_id, ymd
from core.fsc_credentials import law_api_key
from core.mofe_collection import discover_inventory, collect_sources, prepare_source
from core.mofe_profiles import WORK_PROFILES, selected
from core.mofe_universe import assessment, build_graph, report, validate_bundle
from core.procurement_collection import authorities, collect_document

ROOT = Path(__file__).resolve().parents[1]
DOMAINS = ('privacy', 'prices', 'subsidy')
STAGES = ('inventory', 'bodies', 'build')
IDENTITY_FIELDS = ('name', 'provider', 'document_id', 'version_id', 'uid', 'edition_key',
                   'effective', 'promulgated', 'kind', 'managing_authority', 'category')


def destination_path(domain, destination, stamp):
    path=Path(destination).resolve()
    output=(ROOT/'output').resolve()
    if (not path.is_relative_to(output)
            or not path.name.startswith(domain+'-candidate-'+stamp)
            or path==output):
        raise ValueError('Candidate destination must be a new domain/date folder inside output')
    return path


def check_inventory(inventory, domain, stamp):
    if inventory['domain']!=domain or inventory['as_of']!=stamp:
        raise CollectionError('candidate-inventory-domain-or-date-mismatch')
    current=[]; identities=set()
    for item in inventory['records']:
        if (item.get('category')!=domain or item['state'] not in ('current-candidate', 'scheduled')
                or not selected(domain,item['name'],item['managing_authority'],item['provider'])):
            raise CollectionError('candidate-inventory-outside-declared-scope')
        effective=ymd(item['effective'])
        if (effective<=stamp)!=(item['state']=='current-candidate'):
            raise CollectionError('candidate-inventory-edition-state-mismatch')
        if not all(item.get(field) for field in IDENTITY_FIELDS):
            raise CollectionError('candidate-inventory-identity-incomplete')
        ident=require_id(item['document_id']);serial=require_id(item['version_id'])
        if (ymd(item['promulgated'])>stamp or item['uid']!=f"{item['provider']}:{ident}"
                or item['edition_key']!=f"{item['provider']}:{ident}:{serial}:{effective}"):
            raise CollectionError('candidate-inventory-identity-inconsistent')
        if item['edition_key'] in identities:
            raise CollectionError('candidate-inventory-duplicate-edition')
        identities.add(item['edition_key'])
        if item['state']=='current-candidate':current.append(norm(item['name']))
    profile=WORK_PROFILES[domain]
    required={norm(name) for name in (*profile['required'],*profile['required_rules'])}
    if len(current)!=len(set(current)) or not required<=set(current):
        raise CollectionError('candidate-inventory-required-documents-missing-or-duplicated')


def check_source(source, domain, stamp):
    if source['domain']!=domain or source['built_at']!=stamp:
        raise CollectionError('candidate-source-domain-or-date-mismatch')
    inventory=source['inventory'];check_inventory(inventory,domain,stamp)
    expected={item['edition_key']:item for item in inventory['records'] if item['state']=='current-candidate'}
    docs=source['laws']+source['administrative_rules']
    actual=[doc['edition_key'] for doc in docs]
    if len(actual)!=len(set(actual)) or set(actual)!=set(expected):
        raise CollectionError('candidate-source-inventory-scope-mismatch')
    for doc in docs:
        item=expected[doc['edition_key']]
        if any(doc.get(field)!=item[field] for field in IDENTITY_FIELDS):
            raise CollectionError('candidate-source-inventory-identity-mismatch')
        if (doc['state']!='current-body-verified' or doc['fetched_at']!=stamp
                or not doc.get('body_sha256')
                or set(doc.get('body_authorities',[]))!=authorities(item['managing_authority'])
                or not selected(domain,doc['name'],doc['managing_authority'],doc['provider'])):
            raise CollectionError('candidate-source-unverified-body')
    scheduled=[item for item in inventory['records'] if item['state']=='scheduled']
    if source.get('scheduled',[])!=scheduled:
        raise CollectionError('candidate-scheduled-editions-mismatch')


def redact(value, key):
    value=str(value)
    if key:
        for secret in sorted({key,quote(key,safe=''),quote_plus(key,safe='')},key=len,reverse=True):
            value=value.replace(secret,'[redacted]')
    return value


def guard(value, key):
    """Reject credentials before any output/cache write, including nested keys."""
    pending=[value]
    while pending:
        item=pending.pop()
        if isinstance(item,dict):
            if any(str(k).lower() in ('oc','law_oc','law_api_key','authorization') for k in item):
                raise CollectionError('credential-field-found-in-output')
            pending.extend(item.keys());pending.extend(item.values())
        elif isinstance(item,(list,tuple)):pending.extend(item)
        elif isinstance(item,str) and redact(item,key)!=item:
            raise CollectionError('credential-found-in-output')


def save_once(path, value):
    if path.exists():
        if json.loads(path.read_text(encoding='utf-8'))!=value:
            raise ValueError('Existing candidate result differs; choose a new destination')
        return
    atomic_json(path,value)


def check_cache(cache_dir, inventory, key):
    """An old/mismatched cached body must never be silently replaced or reused."""
    records={hashlib.sha256(item['edition_key'].encode()).hexdigest():item
             for item in inventory['records'] if item['state']=='current-candidate'}
    for path in Path(cache_dir).glob('*.json'):
        item=records.get(path.stem)
        if item is None:raise CollectionError('candidate-cache-outside-inventory')
        saved=json.loads(path.read_text(encoding='utf-8'));guard(saved,key)
        doc=saved['body']
        digest=hashlib.sha256(json.dumps(doc,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        if saved['sha256']!=digest:raise CollectionError('candidate-cache-integrity-mismatch')
        # Full required-document coverage is checked on the whole inventory above.
        if (any(doc.get(field)!=item[field] for field in IDENTITY_FIELDS)
                or doc.get('fetched_at')!=inventory['as_of']
                or doc.get('state')!='current-body-verified'
                or set(doc.get('body_authorities',[]))!=authorities(item['managing_authority'])):
            raise CollectionError('candidate-cache-identity-mismatch')


def run(domain, stage, destination, stamp):
    if domain not in DOMAINS or domain not in WORK_PROFILES or stage not in STAGES:
        raise ValueError('Unsupported candidate domain or stage')
    stamp=ymd(stamp)
    if stamp>datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y%m%d'):
        raise ValueError('Future collection date')
    destination=destination_path(domain,destination,stamp)
    destination.mkdir(parents=True,exist_ok=True)
    lock=destination/'collect.lock'
    try:handle=lock.open('x')
    except FileExistsError:
        print('다른 실행의 수집 잠금을 보존합니다.',flush=True);return 2
    token=uuid4().hex;key=None
    started=datetime.now(ZoneInfo('Asia/Seoul')).isoformat()
    receipt=destination/'runs'/(datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y%m%d-%H%M%S')+'-'+stage+'-'+token+'.json')
    try:
        with handle:handle.write(token)
        key=law_api_key()
        def log(*parts):
            print(WORK_PROFILES[domain]['title']+' · '+' · '.join(redact(part,key) for part in parts),flush=True)
        def read(name):
            value=json.loads((destination/name).read_text(encoding='utf-8'));guard(value,key);return value
        def request():
            if not key:raise CollectionError('missing-law-api-key')
            return LawTransport(key,attempts=3,timeout=30,reuse_connections=True)
        if stage=='inventory':
            inventory=discover_inventory(request(),domain,stamp,log)
            guard(inventory,key);check_inventory(inventory,domain,stamp)
            outputs={'inventory.json':inventory}
        elif stage=='bodies':
            inventory=read('inventory.json');check_inventory(inventory,domain,stamp)
            cache=destination/'body-cache';check_cache(cache,inventory,key)
            def authority_check(item, actual):
                return (actual==authorities(item['managing_authority'])
                        and selected(domain,item['name'],','.join(sorted(actual)),item['provider']))
            def checked_collect(*args,**kwargs):
                doc=collect_document(*args,**kwargs);guard(doc,key);return doc
            source=collect_sources(request(),inventory,cache,log,
                                   authority_validator=authority_check,document_collector=checked_collect)
            guard(source,key);check_source(source,domain,stamp)
            outputs={'source.json':source}
        else:
            source=read('source.json');check_source(source,domain,stamp)
            prepared=prepare_source(source)
            bundle=validate_bundle(dict(source=prepared,graph=build_graph(prepared)),domain)
            bundle['assessment']=assessment(bundle)
            if bundle['assessment']['decision']!='limited-release':
                raise CollectionError('candidate-usefulness-gate-hold')
            outputs={'validated-bundle.json':bundle,'summary.json':report(bundle)}
        # Check all output conflicts and credentials before writing any stage result.
        for name,value in outputs.items():
            guard(value,key)
            path=destination/name
            if path.exists() and read(name)!=value:
                raise ValueError('Existing candidate result differs; choose a new destination')
        for name,value in outputs.items():save_once(destination/name,value)
        atomic_json(receipt,dict(domain=domain,stage=stage,status='success',as_of=stamp,
            started_at=started,completed_at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
            outputs={name:hashlib.sha256((destination/name).read_bytes()).hexdigest() for name in outputs}))
        log('완료',stage)
        return 0
    except (CollectionError,OSError,ValueError,KeyError,TypeError) as error:
        reason=redact(str(error),key) if isinstance(error,CollectionError) else type(error).__name__
        failure=dict(domain=domain,stage=stage,status='failure',as_of=stamp,started_at=started,
                     completed_at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),reason=reason)
        atomic_json(receipt,failure)
        print('수집 중단 · 기존 자료 보존 · '+reason,flush=True)
        return 1
    finally:
        if lock.exists() and lock.read_text(encoding='utf-8')==token:lock.unlink()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--domain',choices=DOMAINS,required=True)
    parser.add_argument('--stage',choices=STAGES,required=True)
    parser.add_argument('--dest',type=Path)
    parser.add_argument('--as-of')
    args=parser.parse_args()
    stamp=ymd(args.as_of or datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y%m%d'))
    dest=args.dest or ROOT/'output'/(args.domain+'-candidate-'+stamp)
    return run(args.domain,args.stage,dest,stamp)


if __name__=='__main__':raise SystemExit(main())
