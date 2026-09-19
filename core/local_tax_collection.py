"""Resumable local-tax and ordinance collection with an explicit coverage ledger.

The nationwide inventory is NOT a claim that every ordinance was analyzed.
Only API full-text/title search candidates are collected; unsearched semantic
dependencies and municipal gazette reconciliation remain explicit gaps.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from hashlib import sha256
import json
import math
from pathlib import Path
import re

from core.fsc_collection import CollectionError, LawTransport, field, norm, xml_root, ymd
from core.fsc_administrative import aliases_from, body_text, provision_blocks
from core.citation_scope import Provision

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'output/local-tax-universe'
BASES = ('지방세기본법', '지방세징수법', '지방세법', '지방세특례제한법')
KINDS = {'C0001': '조례', 'C0002': '규칙', 'C0003': '훈령', 'C0004': '예규', 'C0006': '기타', 'C0010': '고시', 'C0011': '의회규칙'}
GUIDE = 'https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=ordinInfoGuide'
PARSER_VERSION = 2


def save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    temp.replace(path)


def read(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def safe_xml(raw: bytes) -> bytes:
    # The provider echoes OC in list links. Never save or print it.
    return re.sub(rb'(?i)(OC=)[^&<\s"\']*', rb'\1REDACTED', raw)


def ordinance_record(row, as_of: str) -> dict:
    ids = [field(row, '자치법규ID'), field(row, '자치법규일련번호')]
    if not all(v.isdigit() for v in ids):
        raise CollectionError('ordin-missing-identifier')
    name, authority = field(row, '자치법규명'), field(row, '지자체기관명')
    if not name or not authority:
        raise CollectionError('ordin-missing-name-or-authority')
    effective = field(row, '시행일자')
    valid_date = bool(re.fullmatch(r'\d{8}', effective))
    if valid_date:
        try: ymd(effective)
        except CollectionError: valid_date = False
    status = 'current-candidate' if valid_date and effective <= as_of else 'scheduled' if valid_date else 'date-unverified'
    if field(row, '제개정구분명') in ('폐지', '일괄폐지', '타법폐지'):
        status = 'repealed'
    return dict(name=name, official_name=name, law_id=ids[0], mst=ids[1], effective=effective,
                promulgated=field(row, '공포일자'), managing_authority=authority,
                kind=field(row, '자치법규종류'), provider='ordin', category='local_tax',
                state=status, source_url='https://www.law.go.kr/LSW/ordinInfoP.do?ordinSeq='+ids[1])


def parse_page(raw: bytes, page: int, as_of: str) -> tuple[int, list[dict]]:
    root = xml_root(raw)
    if root.tag != 'OrdinSearch' or field(root, 'resultCode') != '00':
        raise CollectionError('ordin-list-response-invalid')
    if field(root, 'page') != str(page) or not field(root, 'totalCnt').isdigit():
        raise CollectionError('ordin-list-page-or-count-invalid')
    rows = [ordinance_record(r, as_of) for r in root.findall('law')]
    return int(field(root, 'totalCnt')), rows


def inventory(request, folder: Path, as_of: str, *, query='*', search=1, workers=3, progress=print, canonical=None) -> dict:
    """Reconcile all pages/unique IDs; changed counts never become success."""
    base = dict(target='ordin', nw=1, display=100, query=query, search=search, sort='lasc')
    first_raw = request('lawSearch.do', {**base, 'page':1})
    total, first = parse_page(first_raw, 1, as_of)
    folder.mkdir(parents=True, exist_ok=True)
    fingerprint = sha256(json.dumps([as_of, base, total], sort_keys=True).encode()).hexdigest()
    def one(page):
        path = folder / f'{page:05}.json'
        cached = read(path) if path.exists() else None
        if page == 1:
            count, rows = total, first
        elif cached and cached.get('fingerprint') == fingerprint:
            count, rows = cached['total'], cached['records']
        else:
            count, rows = parse_page(request('lawSearch.do', {**base, 'page':page}), page, as_of)
        expected = max(0, min(100, total-(page-1)*100))
        if count != total or len(rows) != expected:
            raise CollectionError('ordin-list-changed-or-incomplete')
        save(path, dict(fingerprint=fingerprint, total=count, records=rows))
        return rows
    pages = max(1, math.ceil(total/100))
    records = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for done, rows in enumerate(pool.map(one, range(1, pages+1)), 1):
            records.extend(rows)
            if done % 50 == 0 or done == pages:
                progress(f'목록 {query}: {done}/{pages}쪽 · {len(records)}/{total}건', flush=True)
    unique = {r['law_id']:r for r in records}
    if search==2:
        if canonical is None:raise CollectionError('ordin-search-needs-independent-current-inventory')
        # The actual full-text index can return old editions despite nw=1.
        # Preserve all hits and resolve each ID against the independent current
        # inventory, never pick the biggest serial number or infer by title.
        resolved=[canonical[ident] for ident in unique if ident in canonical]
        unresolved=[r for ident,r in unique.items() if ident not in canonical]
        differences=[dict(law_id=r['law_id'],name=r['name'],hit_mst=r['mst'],current_mst=canonical[r['law_id']]['mst'])
                     for r in records if r['law_id'] in canonical and r['mst']!=canonical[r['law_id']]['mst']]
        check_total,check_first=parse_page(request('lawSearch.do',{**base,'page':1}),1,as_of)
        if check_total!=total or check_first!=first:raise CollectionError('ordin-search-changed-during-collection')
        return dict(as_of=as_of,query=query,search=search,expected=total,received=len(unique),received_rows=len(records),
                    list_status='search-pages-reconciled-current-inventory-verified',records=resolved,hits=records,
                    unresolved=unresolved,edition_differences=differences,duplicate_hit_rows=len(records)-len(unique))
    duplicates=[]
    multiplicity=Counter(r['law_id'] for r in records)
    for ident,count in multiplicity.items():
        if count==1:continue
        record=unique[ident]
        if any(r!=record for r in records if r['law_id']==ident):
            raise CollectionError('ordin-list-conflicting-editions')
        # Real API repeats one Daejeon ordinance even in an independent name
        # lookup. Accept only independently reproduced identical source rows;
        # pagination overlap or conflicting editions still fail validation.
        probe_total,probe=parse_page(request('lawSearch.do',{**base,'query':record['name'],'search':1,'page':1}),1,as_of)
        matches=[r for r in probe if r['law_id']==ident]
        if probe_total>100 or len(matches)!=count or any(r!=record for r in matches):
            raise CollectionError('ordin-list-duplicate-or-missing-id')
        duplicates.append(dict(law_id=ident,mst=record['mst'],name=record['name'],rows=count,
                               basis='reproduced-identical-rows-in-independent-name-query'))
    if len(unique)+sum(d['rows']-1 for d in duplicates)!=total:
        raise CollectionError('ordin-list-count-not-reconciled')
    check_total, check_first = parse_page(request('lawSearch.do', {**base, 'page':1}), 1, as_of)
    if check_total != total or [(r['law_id'],r['mst']) for r in check_first] != [(r['law_id'],r['mst']) for r in first]:
        raise CollectionError('ordin-list-changed-during-collection')
    return dict(as_of=as_of, query=query, search=search, expected=total, received=len(unique),received_rows=len(records),provider_duplicates=duplicates,
                list_status='api-count-and-id-reconciled', gazette_status='not-reconciled',
                snapshot_status='paginated-api-not-transactional', records=list(unique.values()))


def parse_ordinance(raw: bytes, record: dict, as_of: str) -> dict:
    root = xml_root(raw)
    info = root.find('자치법규기본정보')
    if root.tag != 'LawService' or info is None:
        raise CollectionError('ordin-body-response-invalid')
    for key, tag in [('law_id','자치법규ID'),('mst','자치법규일련번호'),('effective','시행일자'),
                     ('name','자치법규명'),('managing_authority','지자체기관명')]:
        if norm(field(info, tag)) != norm(record[key]):
            raise CollectionError('ordin-body-edition-mismatch')
    if record['state'] != 'current-candidate' or record['effective'] > as_of:
        raise CollectionError('ordin-body-not-current')
    articles, seen = [], set()
    for unit in root.findall('./조문/조'):
        if field(unit, '조문여부') != 'Y':
            continue
        text = body_text([field(unit, '조내용')])
        code = field(unit, '조문번호')
        if not re.fullmatch(r'\d{6}', code):
            raise CollectionError('ordin-article-number-invalid')
        jo = str(int(code[:4])) + ('의'+str(int(code[4:])) if int(code[4:]) else '')
        heading = re.match(r'제\s*(\d+)\s*조(?:\s*의\s*(\d+))?', text)
        if heading:
            actual = str(int(heading[1])) + ('의'+str(int(heading[2])) if heading[2] else '')
            if actual != jo:
                raise CollectionError('ordin-article-number-body-mismatch')
        if jo in seen:
            raise CollectionError('ordin-duplicate-article')
        if not text:
            raise CollectionError('ordin-empty-article')
        if re.match(r'^제\s*\d+\s*조(?:\s*의\s*\d+)?\s*(?:제\s*\d+\s*항\s*중|중\s|[을를]\s*다음과\s*같이|의\s*제목)',text):
            raise CollectionError('ordin-amendment-instructions-in-body')
        seen.add(jo)
        articles.append(dict(jo=jo, title=field(unit,'조제목'), text=text, effective=record['effective'],
                             deleted=bool(re.match(r'^(?:제\s*\d+\s*조(?:의\d+)?\s*)?삭제',text)),
                             blocks=provision_blocks(text, jo)))
    if not articles:
        raise CollectionError('ordin-no-structured-articles')
    text = '\n'.join(a['text'] for a in articles)
    aliases, evidence = aliases_from(text)
    return {**record, 'articles':articles, 'annexes':[], 'family':record['name'],
            'kind':KINDS.get(field(info,'자치법규종류'),record['kind']),
            'aliases':aliases, 'alias_evidence':evidence, 'fetched_at':as_of,
            'body_status':'indexed-ordinance-text',
            'supplements':[body_text([x.text or '']) for x in root.findall('./부칙/부칙내용')],
            'annex_metadata':[dict(number=field(x,'별표번호'),title=field(x,'별표제목')) for x in root.findall('.//별표')],
            'coverage':dict(provisions='indexed', supplement='stored-not-indexed', annex_body='not-indexed-provider-limited')}


def collect_ordinance(request, record: dict, folder: Path, as_of: str) -> dict:
    stem = record['law_id']+'-'+record['mst']
    path = folder / (stem+'.json')
    if path.exists():
        saved = read(path)
        data = saved['body']
        digest = sha256(json.dumps(data,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        if digest != saved.get('sha256') or any(data.get(k) != record[k] for k in ('law_id','mst','effective','name','managing_authority')):
            raise CollectionError('ordin-cache-integrity-failed')
        if saved.get('parser_version') == PARSER_VERSION:
            return data
        raw_path=folder/(stem+'.xml')
        if raw_path.is_file():
            data=parse_ordinance(raw_path.read_bytes(),record,as_of)
            digest=sha256(json.dumps(data,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
            save(path,dict(sha256=digest,parser_version=PARSER_VERSION,body=data))
            return data
    raw = safe_xml(request('lawService.do', dict(target='ordin', MST=record['mst'])))
    # Preserve supplied bodies even if their structure cannot be analyzed.
    folder.mkdir(parents=True, exist_ok=True)
    (folder / (stem+'.xml')).write_bytes(raw)
    data = parse_ordinance(raw, record, as_of)
    digest = sha256(json.dumps(data,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    save(path, dict(sha256=digest, parser_version=PARSER_VERSION, body=data))
    return data


def collect_central(request, as_of: str, folder: Path) -> list[dict]:
    from scripts.collect_law_universe import parse_body
    records = {}
    for base in BASES:
        root = xml_root(request('lawSearch.do',dict(target='eflaw',nw=3,query=base,display=100,page=1)))
        if root.tag != 'LawSearch':
            raise CollectionError('local-statute-list-invalid')
        wanted = {norm(base+suffix) for suffix in ('',' 시행령',' 시행규칙')}
        for row in root.findall('law'):
            name, effective = field(row,'법령명한글'), field(row,'시행일자')
            if norm(name) not in wanted or ymd(effective)>as_of: continue
            record = dict(name=name, official_name=name, law_id=field(row,'법령ID'), mst=field(row,'법령일련번호'),
                          effective=effective, family=base, category='local_tax', provider='eflaw',
                          managing_authority='행정안전부', kind=field(row,'법령구분명'),
                          source_url='https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq='+field(row,'법령일련번호')+'&efYd='+effective)
            if name not in records or (record['effective'],int(record['mst']))>(records[name]['effective'],int(records[name]['mst'])):
                records[name]=record
    if len(records) != 12:
        raise CollectionError('local-statute-family-incomplete')
    result = []
    for record in records.values():
        raw = safe_xml(request('lawService.do',dict(target='eflaw',ID=record['law_id'])))
        root = xml_root(raw)
        body = parse_body(root, record)
        if body['effective'] != record['effective'] or not body['articles']:
            raise CollectionError('local-statute-edition-mismatch')
        body.update(body_status='indexed-statute-text')
        folder.mkdir(parents=True,exist_ok=True)
        (folder/(record['law_id']+'.xml')).write_bytes(raw)
        save(folder/(record['law_id']+'.json'),body)
        result.append(body)
    return result


def collect_all(request, output: Path = OUTPUT, *, as_of=None, workers=3, progress=print) -> dict:
    """Checkpoint in a dated staging directory; publish only a validated build."""
    as_of = as_of or date.today().strftime('%Y%m%d')
    stage = output/'staging'/as_of
    stage.mkdir(parents=True,exist_ok=True)
    central = collect_central(request,as_of,stage/'central')
    save(stage/'central.json',central)
    progress('중앙 지방세 법령 12건 수집 완료',flush=True)
    complete = inventory(request,stage/'inventory-pages',as_of,workers=workers,progress=progress)
    save(stage/'inventory.json',complete)
    # Full text reaches ordinances whose titles do not mention local taxes.
    all_ids = {r['law_id']:r for r in complete['records']}
    candidates = inventory(request,stage/'candidate-pages',as_of,query='지방세',search=2,workers=workers,progress=progress,canonical=all_ids)
    save(stage/'candidates.json',candidates)
    if any(r['law_id'] not in all_ids or r['mst'] != all_ids[r['law_id']]['mst'] for r in candidates['records']):
        raise CollectionError('ordin-inventory-candidate-edition-mismatch')
    selected={r['law_id']:r for r in candidates['records']}
    title_additions=[]
    for record in complete['records']:
        if re.search(r'지방세|(?:시|도|군|구)세(?:\s|$)|납세자|세무조사',record['name']) and record['law_id'] not in selected:
            selected[record['law_id']]=record;title_additions.append(record)
    eligible = [r for r in selected.values() if r['state']=='current-candidate' and r['kind'] in ('조례','규칙')]
    results, failures = [], []
    def one(record):
        try:
            body = collect_ordinance(request,record,output/'body-cache',as_of)
            return dict(law_id=record['law_id'],mst=record['mst'],name=record['name'],managing_authority=record['managing_authority'],
                        status='indexed',articles=len(body['articles']),path=record['law_id']+'-'+record['mst']+'.json')
        except CollectionError as error:
            return dict(law_id=record['law_id'],mst=record['mst'],name=record['name'],managing_authority=record['managing_authority'],
                        status='failed',reason=str(error))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one,r) for r in eligible]
        for done, future in enumerate(as_completed(futures),1):
            item = future.result()
            results.append(item)
            if item['status']=='failed': failures.append(item)
            if done%100==0 or done==len(eligible):
                save(stage/'progress.json',dict(done=done,total=len(eligible),failed=len(failures),updated_at=datetime.now().isoformat()))
                save(stage/'body-status.json',results)
                progress(f'조례·규칙 본문 {done}/{len(eligible)} · 확인 필요 {len(failures)}',flush=True)
    eligible_ids={r['law_id'] for r in eligible}
    report = dict(as_of=as_of, inventory_total=complete['received'], inventory_rows=complete['received_rows'],provider_duplicates=complete['provider_duplicates'],candidates_total=candidates['received'],
                  candidate_rows=candidates['received_rows'],candidate_duplicate_rows=candidates['duplicate_hit_rows'],
                  title_additions=title_additions,edition_differences=candidates['edition_differences'],unresolved_candidates=candidates['unresolved'],
                  eligible=len(eligible), indexed=sum(r['status']=='indexed' for r in results), failed=failures,
                  skipped=[r for r in selected.values() if r['law_id'] not in eligible_ids],
                  search=dict(query='지방세',scope='API 본문 검색 + 전체 목록의 세목·납세자·세무조사 제목 보완',status='candidate-search-not-exhaustive-relevance'),
                  inventory_status=complete['list_status'], gazette_status='not-reconciled',
                  annex_status='not-indexed-provider-limited', supplement_status='stored-not-indexed',
                  body_status=results)
    save(stage/'collection.json',report)
    return report
