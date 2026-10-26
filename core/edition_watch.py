"""Read-only edition checks for the documents actually published in a snapshot.

No body replacement, graph rebuild, commit or deployment is performed here.
Provider outages and unresolvable identities never mean 'unchanged'.
"""
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from core.fsc_collection import CollectionError, field, xml_root
from core.local_tax_collection import inventory as ordinance_inventory
from scripts.static_storage import Storage

ROOTS = {'eflaw': 'LawSearch', 'admrul': 'AdmRulSearch'}
IDENTITY_TAGS = {'eflaw': ('기본정보', '법령ID', '법령일련번호'),
                 'admrul': ('행정규칙기본정보', '행정규칙ID', '행정규칙일련번호'),
                 'ordin': ('자치법규기본정보', '자치법규ID', '자치법규일련번호')}
UNKNOWN_EFFECTIVE_DATES = {'99991231'}


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(path)


def valid_day(value):
    try:
        return (isinstance(value, str) and len(value) == 8 and value.isdigit()
                and value not in UNKNOWN_EFFECTIVE_DATES
                and date.fromisoformat(f'{value[:4]}-{value[4:6]}-{value[6:]}') is not None)
    except (ValueError, TypeError):
        return False


def record(row, provider, as_of):
    prefix = '법령' if provider == 'eflaw' else '행정규칙'
    stable, serial = field(row, prefix + 'ID'), field(row, prefix + '일련번호')
    name = field(row, '법령명한글' if provider == 'eflaw' else '행정규칙명')
    if not stable.isdigit() or not serial.isdigit() or not name:
        raise CollectionError('edition-list-missing-identity')
    effective = field(row, '시행일자')
    state = ('date-unverified' if not valid_day(effective) else
             'scheduled' if effective > as_of else 'current')
    if '폐지' in field(row, '제개정구분명'):
        state = 'repealed'
    return dict(provider=provider, stable_id=stable, serial=serial, name=name,
                effective=effective, state=state)


def inventory(request, provider, as_of, folder, workers=3, progress=lambda x: None):
    if provider == 'ordin':
        result = ordinance_inventory(request, folder, as_of, workers=workers,
                                      progress=lambda message, **_: progress(message))
        return [dict(provider=provider, stable_id=r['law_id'], serial=r['mst'],
                     name=r['name'], effective=r['effective'],
                     state=('date-unverified' if not valid_day(r['effective']) and r['state'] != 'repealed'
                            else 'current' if r['state'] == 'current-candidate' else r['state']))
                for r in result['records']]
    params = dict(target=provider, nw=3 if provider == 'eflaw' else 1,
                  query='*', search=1, display=100, sort='lasc')

    def page(number):
        root = xml_root(request('lawSearch.do', {**params, 'page': number}))
        if (root.tag != ROOTS[provider] or field(root, 'resultCode') != '00'
                or field(root, 'page') != str(number) or not field(root, 'totalCnt').isdigit()):
            raise CollectionError('edition-list-response-invalid')
        total = int(field(root, 'totalCnt'))
        rows = [record(r, provider, as_of) for r in root.findall('law' if provider == 'eflaw' else 'admrul')]
        if len(rows) != max(0, min(100, total - (number - 1) * 100)):
            raise CollectionError('edition-list-short-page')
        return total, rows

    total, first = page(1)
    rows = list(first)
    pages = max(1, math.ceil(total / 100))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for number, (count, values) in enumerate(pool.map(page, range(2, pages + 1)), 2):
            if count != total:
                raise CollectionError('edition-list-changing-count')
            rows.extend(values)
            if number % 50 == 0 or number == pages:
                progress(f'{provider}: {number}/{pages} pages')
    if page(1) != (total, first):
        raise CollectionError('edition-list-changed-during-check')
    # Conflicting current editions remain ambiguous at comparison time.
    # Repeated identical serials on different pages can hide omissions: fail.
    if len({r['serial'] for r in rows}) != total:
        raise CollectionError('edition-list-duplicate-serial')
    return rows


def published_documents(site):
    site = Path(site)
    manifest = json.loads((site / 'manifest.json').read_text(encoding='utf-8'))
    storage = Storage(site, manifest)
    documents = {}
    domain_counts = Counter()
    for domain in manifest['domains']:
        catalog = storage.read(domain['catalog'])
        regions = catalog.get('regions', [])
        if any(r.get('indexed', 0) and not r.get('catalog') for r in regions):
            raise ValueError('An indexed regional catalog is missing')
        catalogs = [catalog] + [storage.read(r['catalog']) for r in regions if r.get('catalog')]
        for cat in catalogs:
            for entry in cat['laws']:
                domain_counts[domain['id']] += 1
                url = urlparse(entry.get('url', ''))
                query = parse_qs(url.query)
                provider, serial = '', ''
                if url.hostname in ('www.law.go.kr', 'law.go.kr'):
                    for name, param in (('eflaw', 'lsiSeq'), ('admrul', 'admRulSeq'), ('ordin', 'ordinSeq')):
                        if query.get(param, [''])[0].isdigit():
                            provider, serial = name, query[param][0]
                            break
                # A document can appear in several fields or in distinct editions.
                key = f'{provider}:{serial}:{entry.get("effective", "")}' if provider else entry.get('url') or entry['id']
                item = documents.setdefault(key, dict(key=key, provider=provider, serial=serial,
                    name=entry['name'], effective=entry.get('effective', ''), url=entry.get('url', ''), domains=[]))
                if item['name'] != entry['name']:
                    item['identity_conflict'] = True
                if domain['id'] not in item['domains']:
                    item['domains'].append(domain['id'])
    if set(domain_counts) != {d['id'] for d in manifest['domains']}:
        raise ValueError('A published field has no checkable catalog')
    return manifest['version'], list(documents.values()), dict(domain_counts)


def historical_identity(request, item):
    """Resolve the pinned *old* edition; never equate two laws by title alone."""
    provider, serial = item['provider'], item['serial']
    params = dict(target=provider)
    if provider == 'eflaw':
        params.update(MST=serial, efYd=item['effective'])
    elif provider == 'ordin':
        params['MST'] = serial
    else:
        params['ID'] = serial
    root = xml_root(request('lawService.do', params))
    container, id_tag, serial_tag = IDENTITY_TAGS[provider]
    info = root.find('.//' + container)
    if info is None:
        raise CollectionError('edition-old-identity-missing')
    stable = field(info, id_tag)
    actual_serial = field(info, serial_tag) or field(root, serial_tag)
    # eflaw does not echo MST. Its 법령키 begins with the *stable* law ID,
    # not the serial. Bind its returned title/date to the requested old edition.
    if provider == 'eflaw':
        matches = (root.tag == '법령' and root.attrib.get('법령키', '').startswith(stable)
                   and field(info, '법령명_한글') == item['name']
                   and field(info, '시행일자') == item['effective'])
    else:
        matches = actual_serial == serial
    if not stable.isdigit() or not matches:
        raise CollectionError('edition-old-identity-not-verified')
    return stable


def compare(item, current, stable_id):
    # Recheck dates here as callers may reuse inventories made by an older
    # checker. Do not silently turn an unknown-date marker into a future law.
    normalized = [dict(r, state='date-unverified')
                  if not valid_day(r.get('effective')) and r['state'] != 'repealed' else r
                  for r in current if r['stable_id'] == stable_id]
    candidates = {json.dumps(r, sort_keys=True): r for r in normalized}
    if not candidates:
        return dict(status='missing-current', stable_id=stable_id)
    ordered = [candidates[key] for key in sorted(candidates)]
    active = [r for r in ordered if r['state'] == 'current']
    scheduled = [r for r in ordered if r['state'] == 'scheduled']
    conflicts = [r for r in ordered if r['state'] not in ('current', 'scheduled')]
    if len(active) == 1 and not conflicts:
        latest = active[0]
    elif len(ordered) == 1:
        latest = ordered[0]
    else:
        return dict(status='ambiguous-current', stable_id=stable_id, candidates=ordered)
    result = dict(stable_id=stable_id, current=latest)
    if latest['state'] == 'current' and scheduled:
        # Future editions are evidence about planned changes, not competing
        # current texts. Preserve every one for review and repeat detection.
        result['scheduled_editions'] = scheduled
    if latest['state'] != 'current':
        return dict(result, status=latest['state'])
    if not valid_day(item['effective']):
        return dict(result, status='baseline-date-unverified')
    if latest['effective'] < item['effective']:
        return dict(result, status='baseline-ahead-of-current')
    edition_changed = latest['serial'] != item['serial'] or latest['effective'] != item['effective']
    renamed = latest['name'] != item['name']
    return dict(result, status='changed' if edition_changed or renamed else 'unchanged',
                edition_changed=edition_changed, renamed=renamed)


def check(site, request, output, *, as_of=None, workers=3, progress=print):
    """Caller holds the lock. Only this check's own reports/caches are written."""
    as_of = as_of or datetime.now().strftime('%Y%m%d')
    if not valid_day(as_of):
        raise ValueError('Invalid check date')
    output = Path(output)
    version, items, domain_counts = published_documents(site)
    providers, failures = {}, {}
    for provider in ('eflaw', 'admrul', 'ordin'):
        try:
            providers[provider] = inventory(request, provider, as_of,
                output / 'inventory-cache' / as_of / provider, workers, progress)
            save(output / 'inventory-cache' / as_of / (provider + '.json'), providers[provider])
        except Exception:
            # Transport/library exceptions may include URLs with credentials.
            failures[provider] = 'official-inventory-unverified'
    identity_file = output / 'identities.json'
    identities = json.loads(identity_file.read_text(encoding='utf-8')) if identity_file.exists() else {}
    by_serial = {p: {r['serial']: r for r in rows} for p, rows in providers.items()}
    by_id = {p: defaultdict(list) for p in providers}
    for p, rows in providers.items():
        for row in rows:
            by_id[p][row['stable_id']].append(row)

    def one(item):
        p, serial = item['provider'], item['serial']
        if item.get('identity_conflict'):
            return dict(item, status='baseline-identity-conflict'), None
        if not p:
            return dict(item, status='manual-source-check', reason='법제처 판본 식별자가 없는 별도 기관 자료'), None
        if p in failures:
            return dict(item, status='provider-failed'), None
        key = f'{p}:{serial}'
        stable = by_serial[p].get(serial, {}).get('stable_id') or identities.get(key)
        try:
            if not stable:
                stable = historical_identity(request, item)
            return dict(item, **compare(item, by_id[p].get(stable, []), stable)), (key, stable)
        except Exception:
            return dict(item, status='identity-unverified'), None

    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for number, (result, identity) in enumerate(pool.map(one, items), 1):
            results.append(result)
            if identity:
                identities[identity[0]] = identity[1]
            if number % 500 == 0:
                progress(f'Edition checks: {number}/{len(items)}')
    counts = Counter(r['status'] for r in results)
    domains = {d: dict(catalog_entries=n, statuses=dict(Counter(r['status'] for r in results if d in r['domains'])))
               for d, n in domain_counts.items()}
    actionable = [r for r in results if r['status'] != 'unchanged' or r.get('scheduled_editions')]
    fingerprint = sha256(json.dumps(actionable, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    previous_path = output / 'latest.json'
    previous = json.loads(previous_path.read_text(encoding='utf-8')) if previous_path.exists() else {}
    report = dict(schema=1, checked_at=datetime.now(timezone.utc).isoformat(), as_of=as_of,
        data_version=version, domains=domains, unique_published_editions=len(items),
        counts=dict(counts), provider_failures=failures, actionable=actionable,
        fingerprint=fingerprint, notification_needed=bool(actionable and fingerprint != previous.get('fingerprint')),
        coverage_note='공개 수집 목록의 판본 점검. 별표·첨부파일 자체 변경 및 미수집 법령의 신규 제정은 별도 확인. 본문·연결·배포 자료는 변경하지 않음.')
    save(identity_file, identities)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    save(output / 'runs' / (stamp + '.json'), report)
    save(previous_path, report)
    return report
