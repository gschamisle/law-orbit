"""Collect only the reviewed 2026-10-26 delta into an isolated staging output."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from core.fsc_credentials import law_api_key
from core.fsc_collection import LawTransport, CollectionError, field, norm, xml_root, atomic_json
from core.procurement_collection import record as central_record, collect_document, authorities, safe_xml
from core.local_tax_collection import ordinance_record, collect_ordinance
from core.fsc_administrative import index_rule

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent
AS_OF = '20261026'
OUT = ROOT / 'output/edition-refresh-20261026'
DELTA = BASE / 'FscLawGalaxy-Stage2/output/law-updates/all-edition-delta-20261026.json'

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

def identity(doc):
    return (doc.get('provider', 'eflaw'), str(doc.get('document_id') or doc.get('law_id') or ''),
            str(doc.get('version_id') or doc.get('mst') or ''), str(doc.get('effective', '')))

def metadata(request, finding):
    expected = finding['current']
    provider = expected['provider']
    raw_pages, matches = [], []
    for page in range(1, 11):
        raw = request('lawSearch.do', dict(target=provider, query=expected['name'], search=1,
                     nw=3 if provider == 'eflaw' else 1, display=100, page=page, sort='lasc'))
        root = xml_root(raw)
        envelope = {'eflaw':'LawSearch', 'admrul':'AdmRulSearch', 'ordin':'OrdinSearch'}[provider]
        if root.tag != envelope or field(root, 'page') != str(page):
            raise CollectionError('delta-list-envelope-or-page-invalid')
        total = int(field(root, 'totalCnt'))
        raw_pages.append(sha256(safe_xml(raw)).hexdigest())
        for row in root.findall('admrul' if provider == 'admrul' else 'law'):
            sid = field(row, {'eflaw':'법령ID','admrul':'행정규칙ID','ordin':'자치법규ID'}[provider])
            if sid != expected['stable_id']:
                continue
            item = (ordinance_record(row, AS_OF) if provider == 'ordin' else
                    central_record(row, provider, AS_OF, selector=lambda *args: True,
                                   domain=finding['domains'][0]))
            if identity(item) == (provider, expected['stable_id'], expected['serial'], expected['effective']):
                matches.append(item)
        if page * 100 >= total:
            break
    else:
        raise CollectionError('delta-list-page-limit')
    unique = {json.dumps(x, ensure_ascii=False, sort_keys=True):x for x in matches}
    if len(unique) != 1:
        raise CollectionError('delta-expected-current-edition-not-unique')
    item = next(iter(unique.values()))
    if item['state'] != 'current-candidate' or norm(item['name']) != norm(expected['name']):
        raise CollectionError('delta-current-state-or-name-mismatch')
    return item, raw_pages

def reuse_index():
    result = {}
    for domain in ('tax', 'fsc'):
        path = BASE / f'FscLawGalaxy-Stage2/output/{domain}-universe/bundle.json'
        data = read(path)['source']
        for group in ('laws','administrative_rules'):
            for doc in data.get(group, []):
                if re.sub(r'\D', '', str(doc.get('fetched_at',''))) != AS_OF:
                    continue
                result[identity(doc)] = (doc, path)
    return result

def collect_one(finding, reused):
    request = LawTransport(law_api_key(), attempts=2, timeout=40, reuse_connections=True)
    expected = finding['current']
    item, hashes = metadata(request, finding)
    key = identity(item)
    cached = reused.get(key)
    validation = dict(status='verified', expected_identity=list(key), independent_list_sha256=hashes,
        managing_authority=item['managing_authority'], source_url=item['source_url'],
        current_on=AS_OF, authority_checked=True, stable_id_checked=True, edition_date_checked=True,
        version_id_checked=True, annex_body_complete=False)
    if cached:
        doc, path = cached
        if doc.get('state') != 'current-body-verified' or not doc.get('body_sha256'):
            raise CollectionError('delta-reuse-body-not-verified')
        if norm(doc['name']) != norm(item['name']) or not authorities(doc.get('managing_authority','')).issubset(authorities(item['managing_authority'])):
            raise CollectionError('delta-reuse-title-or-authority-mismatch')
        fresh = deepcopy(doc)
        validation.update(collection='reused-verified-weekly-body', reused_from=str(path),
                          reused_document_sha256=digest(doc))
    elif item['provider'] == 'ordin':
        fresh = collect_ordinance(request, item, OUT / 'ordinance-cache', AS_OF)
        validation.update(collection='fresh-pinned-api-body',
            raw_xml_sha256=sha256((OUT / 'ordinance-cache' / (item['law_id']+'-'+item['mst']+'.xml')).read_bytes()).hexdigest())
    else:
        fresh = collect_document(request, item, AS_OF)
        if item['provider'] == 'admrul':
            if fresh.get('raw_body_blocks'):
                fresh = index_rule(fresh)
        validation.update(collection='fresh-pinned-api-body', raw_xml_sha256=fresh.get('body_sha256'))
    fresh.setdefault('provider', item['provider'])
    if identity(fresh) != key:
        raise CollectionError('delta-final-identity-mismatch')
    if not fresh.get('articles') and not (fresh.get('raw_body_blocks') or fresh.get('attachments')):
        raise CollectionError('delta-empty-body')
    if item['provider'] == 'eflaw':
        fresh.setdefault('law_id', item['document_id'])
        fresh.setdefault('mst', item['version_id'])
        fresh.setdefault('document_id', item['document_id'])
        fresh.setdefault('version_id', item['version_id'])
    validation.update(article_count=len(fresh.get('articles', [])),
        body_status=fresh.get('body_status'), body_indexed=bool(fresh.get('articles')),
        fresh_document_sha256=digest(fresh))
    if finding.get('edition_changed'):
        change_kind = 'edition'
    elif norm(finding['name']) == norm(expected['name']):
        change_kind = 'punctuation-only'
    else:
        change_kind = 'title-metadata'
    if change_kind != 'edition':
        validation['published_old_body_comparison'] = 'not-performed; retain published body for title-only updates'
    return dict(finding=finding, identity=dict(provider=key[0],stable_id=key[1],
            old_serial=finding['serial'],old_effective=finding['effective'],new_serial=key[2],new_effective=key[3],
            domains=finding['domains']), change_kind=change_kind, fresh_document=fresh, validation=validation)

MANUAL = [
 dict(name='선불식 할부거래에서의 소비자보호 지침', provider='admrul', stable_id='39435',
      decision='hold-replacement-source-effective-date-conflict', preserve_serial='2100000235042',
      preserve_effective='20240109', candidate_serial='2100000287152',
      official_api=dict(promulgated='20261023',number='502',effective='20261029',current_flag='N'),
      issuing_authority_press_release=dict(published='20261023',stated_effective='20261023'),
      evidence=['https://www.law.go.kr/admRulInfoP.do?admRulSeq=2100000287152',
      'https://m.korea.kr/briefing/pressReleaseView.do?newsId=156786238&pWiseMinistry=ministryNews&repCode=C00001&repCodeType=%EC%A0%95%EB%B6%80%EB%B6%80%EC%B2%98',
      'https://www.korea.kr/common/download.do?fileId=198575852&tblKey=GMN'],
      explanation='법제처 API는 시행 10/29·현행N, 공정위 보도자료 및 HWPX 원문은 10/23 시행. 새 API 부칙은 2024 제451호까지만 제공. 실제 시행일을 임의 확정하지 않고 기존 수집본을 보존한다.'),
 dict(name='대전광역시 동구 효행가정 지원 조례',provider='ordin',stable_id='2051815',serial='764640',
      decision='retain-existing-edition-supported-by-supplement',raw_effective='99991231',
      preserved_effective='20091130',promulgated='20091130',number='839',
      supplement='이 조례는 공포한 날부터 시행한다.',
      evidence=['https://www.law.go.kr/ordinInfoP.do?ordinSeq=764640'],
      explanation='동일 판본 부칙과 공포일에 근거하여 2009-11-30을 유지. 99991231은 메타데이터 이상으로 기록하며 다른 판본에 일반화하지 않는다.'),
 dict(name='용인시 소하천 점용료 등 징수 조례',provider='ordin',stable_id='2145925',serial='1961523',
      decision='correct-stale-title-not-a-new-2026-edition',effective='20240802',number='2536',
      evidence=['https://www.jachilaw.com/yongin2/law_history.asp?lawid=1-20-04-002&mode=history_view',
      'https://www.jachilaw.com/DATA/YongIn/PDF/1-16-06-002-20240802.PDF'],
      explanation='용인시 자체 법규 연혁에 2024-08-02 제2536호 제명개정 명시. 구명칭은 별칭으로 보존한다.'),
 dict(name='부산광역시 서구 오수ㆍ분뇨 및 가축분뇨의 관리에 관한 조례',provider='ordin',stable_id='2064271',serial='1608089',
      decision='separate-title-history-annotation',effective='20210701',number='1338',
      evidence=['https://www.law.go.kr/LSW/ordinInfoP.do?ordinSeq=1608089'],
      explanation='동일 2021 판본이다. 제명개정 2013.10.1은 이력 주석으로 분리하고 새 판본 변경으로 집계하지 않는다.')
]

def main():
    if (OUT/'sources.json').exists():
        raise FileExistsError('Existing sources.json may contain reviewed corrections; choose a new collection output instead of overwriting it')
    delta = read(DELTA)
    selected = [x for x in delta['new_findings'] if x['status']=='changed']
    reused = reuse_index()
    rows, failed = [], []
    OUT.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        pending = {pool.submit(collect_one, f, reused):f for f in selected}
        for future in as_completed(pending):
            finding = pending[future]
            try:
                row = future.result()
                rows.append(row)
                print('VERIFIED', finding['name'], row['validation']['article_count'], flush=True)
            except Exception as exc:
                code = str(exc) if isinstance(exc, CollectionError) and re.fullmatch('[a-z0-9-]+',str(exc)) else type(exc).__name__
                failed.append(dict(finding=finding,error=code))
                print('EXCLUDED', finding['name'], code, flush=True)
    rows.sort(key=lambda x:x['finding']['key'])
    excluded = [dict(finding=f,reason='not-a-confirmed-current-replacement') for f in delta['new_findings'] if f['status']!='changed'] + failed
    result = dict(schema_version=1,as_of=AS_OF,generated_at=datetime.now(timezone.utc).isoformat(),
            base_data_version=delta['data_version'],delta_path=str(DELTA),delta_sha256=sha256(DELTA.read_bytes()).hexdigest(),
            rows=rows,excluded=excluded)
    report = dict(schema_version=1,as_of=AS_OF,selected=len(selected),verified=len(rows),failed=len(failed),
        edition_changes=sum(r['change_kind']=='edition' for r in rows),
        title_metadata=sum(r['change_kind']=='title-metadata' for r in rows),
        punctuation_only=sum(r['change_kind']=='punctuation-only' for r in rows),
        reused_weekly=sum(r['validation']['collection']=='reused-verified-weekly-body' for r in rows),
        manual_clarifications=MANUAL,failures=failed,excluded_findings=excluded,
        body_not_indexed=[dict(name=r['fresh_document']['name'],provider=r['identity']['provider'],
          stable_id=r['identity']['stable_id'],body_status=r['fresh_document'].get('body_status'),
          scope='edition-and-raw-body-verified; article-level-analysis-not-complete')
          for r in rows if not r['fresh_document'].get('articles')],
        limitations=['범위는 이번 주 delta의 새 changed 목록이다. 기존 미반영 전체 목록 갱신을 뜻하지 않는다.',
        '별표·첨부파일 자체 변경 및 미수집 법령의 신규 제정은 점검 범위 밖이다.',
        '제목만 다른 12건은 기존 공개 본문을 유지할 수 있다. 과거 본문과의 전문 동일성은 주장하지 않는다.',
        '행정규칙 본문 구조화 및 조례 부칙·별표 추출 범위는 기존 수집기 한계를 유지한다.'])
    atomic_json(OUT/'sources.json',result)
    atomic_json(OUT/'report.json',report)
    print(json.dumps({k:v for k,v in report.items() if k in ('selected','verified','failed','edition_changes','title_metadata','punctuation_only','reused_weekly')},ensure_ascii=False),flush=True)
    return 1 if failed else 0

if __name__=='__main__':
    raise SystemExit(main())
