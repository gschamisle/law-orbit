"""Declared procurement corpus, collected directly from official pinned editions."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from core.fsc_collection import (CollectionError, field, norm, ymd, require_id,
                                 xml_root, body_params, atomic_json)

NATIONAL = '국가를 당사자로 하는 계약에 관한 법률'
LOCAL = '지방자치단체를 당사자로 하는 계약에 관한 법률'
FAMILIES = (NATIONAL, LOCAL, '조달사업에 관한 법률', '전자조달의 이용 및 촉진에 관한 법률',
            '중소기업제품 구매촉진 및 판로지원에 관한 법률')
STATUTE_QUERIES = FAMILIES + ('공기업ㆍ준정부기관 계약사무규칙',)
RULE_QUERIES = ('계약예규', '국가계약', '지방자치단체 입찰', '조달청',
                '일반용역계약특수조건', '물품구매(제조)계약 특수조건',
                '국가종합전자조달시스템', '다수공급자계약', '기타공공기관 계약사무 운영규정')
AUTHORITIES = {'재정경제부', '기획재정부', '기획예산처', '조달청', '행정안전부', '중소벤처기업부'}
ROOTS = {'eflaw': 'LawSearch', 'admrul': 'AdmRulSearch'}


def authorities(value):
    return {v.strip() for v in re.split(r'[,，/;ㆍ·\n]', value) if v.strip()}


def selected(name, authority, provider):
    n, a = norm(name), authorities(authority)
    if not a or not a.issubset(AUTHORITIES):
        return False
    if provider == 'eflaw':
        return (any(n == norm(f+s) for f in FAMILIES for s in ('', ' 시행령', ' 시행규칙'))
                or (norm(NATIONAL) in n and n.endswith(('특례규정', '특례규칙')))
                or n == norm('공기업ㆍ준정부기관 계약사무규칙'))
    if a & {'재정경제부', '기획재정부', '기획예산처'}:
        return bool(n.startswith('(계약예규)') or '국가계약' in n or norm(NATIONAL) in n
                    or n == norm('기타공공기관 계약사무 운영규정'))
    if '행정안전부' in a:
        return n in {norm('지방자치단체 입찰 및 계약 집행기준'), norm('지방자치단체 입찰시 낙찰자 결정기준'),
                     norm('국제입찰에 의하는 지방자치단체의 공사 및 물품·용역의 범위에 관한 고시')}
    return '조달청' in a and bool(re.search('계약|입찰|낙찰|적격심사|가격|물품구매|전자조달|다수공급자|종합쇼핑몰|혁신제품|우수조달', n))


def record(row, provider, as_of, *, selector=selected, domain="procurement"):
    law = provider == 'eflaw'
    name = field(row, '법령명한글' if law else '행정규칙명')
    authority = field(row, '소관부처명')
    if not selector(name, authority, provider):
        return None
    ident = require_id(field(row, '법령ID' if law else '행정규칙ID'))
    serial = require_id(field(row, '법령일련번호' if law else '행정규칙일련번호'))
    effective = ymd(field(row, '시행일자'))
    published = ymd(field(row, '공포일자' if law else '발령일자'))
    kind = field(row, '법령구분명' if law else '행정규칙종류')
    if not kind or published > as_of:
        raise CollectionError('invalid-procurement-list-metadata')
    return dict(name=name, provider=provider, document_id=ident, version_id=serial,
                uid=f'{provider}:{ident}', edition_key=f'{provider}:{ident}:{serial}:{effective}',
                effective=effective, promulgated=published, kind=kind, managing_authority=authority,
                short_name=field(row, '법령약칭명') if law else '', category=domain,
                state='scheduled' if effective > as_of else 'current-candidate',
                source_url=(f'https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq={serial}&efYd={effective}' if law else
                            f'https://www.law.go.kr/LSW/admRulLsInfoP.do?admRulSeq={serial}'))


def discover_query(request, provider, query, as_of, *, record_factory=record):
    as_of = ymd(as_of)
    expected, received, records, hashes = None, 0, [], []
    for page in range(1, 101):
        raw = request('lawSearch.do', dict(target=provider, query=query, search=1,
                      nw=3 if provider == 'eflaw' else 1, display=100, page=page, sort='lasc'))
        root = xml_root(raw)
        if root.tag != ROOTS[provider]:
            raise CollectionError('unexpected-procurement-list-envelope')
        try:
            total, actual_page = int(field(root, 'totalCnt')), int(field(root, 'page'))
        except ValueError:
            raise CollectionError('missing-procurement-pagination') from None
        if actual_page != page or total < 0 or (expected is not None and total != expected):
            raise CollectionError('unstable-procurement-pagination')
        expected = total
        rows = root.findall('law' if provider == 'eflaw' else 'admrul')
        if len(rows) != min(100, total-received):
            raise CollectionError('short-procurement-page')
        received += len(rows)
        hashes.append(hashlib.sha256(raw).hexdigest())
        for row in rows:
            item = record_factory(row, provider, as_of)
            if item: records.append(item)
        if received == total:
            return dict(provider=provider, query=query, expected=total, received=received,
                        pages=page, list_status='complete', page_sha256=hashes, records=records)
    raise CollectionError('procurement-page-limit')


def discover_inventory(request, as_of, progress=None):
    layers, unique = [], {}
    # Keep list and rule phases sequential and explicitly observable.
    for provider, queries in [('eflaw', STATUTE_QUERIES), ('admrul', RULE_QUERIES)]:
        for query in queries:
            layer = discover_query(request, provider, query, as_of)
            for r in layer['records']:
                old = unique.get(r['uid'])
                if old and any(old[k] != r[k] for k in ('edition_key', 'name', 'managing_authority')):
                    raise CollectionError('conflicting-current-procurement-editions')
                unique[r['uid']] = r
            layers.append(layer)
            if progress: progress(provider, query, layer['received'], len(layer['records']))
    for family in FAMILIES:
        if not any(norm(r['name']) == norm(family) for r in unique.values()):
            raise CollectionError('required-procurement-family-not-found')
    if not any(r['kind'] == '계약예규' for r in unique.values()):
        raise CollectionError('contract-rules-not-found')
    return dict(as_of=ymd(as_of), layers=layers, records=sorted(unique.values(), key=lambda r:r['name']),
                scope='declared-families-and-title-authority-filters; not-all-public-contract-rules')


def safe_xml(raw):
    return re.sub(rb'([?&](?:amp;)?[Oo][Cc]=)[^&\s\"<>]+', rb'\1[redacted]', raw)


def collect_document(request, item, as_of, *, authority_validator=None):
    if item['state'] != 'current-candidate' or item['effective'] > ymd(as_of):
        raise CollectionError('procurement-not-effective')
    raw = safe_xml(request('lawService.do', body_params(item)))
    root = xml_root(raw)
    law = item['provider'] == 'eflaw'
    name = field(root, './/법령명_한글' if law else './/행정규칙명')
    ident = field(root, './/법령ID' if law else './/행정규칙ID')
    actual = {a for tag in ('.//소관부처명', './/소관부처') for node in root.findall(tag)
              for a in authorities(node.text or '')}
    if norm(name) != norm(item['name']) or ident != item['document_id']:
        raise CollectionError('procurement-body-identity-mismatch')
    if ymd(field(root, './/시행일자')) != item['effective'] or (not law and field(root, './/행정규칙일련번호') != item['version_id']):
        raise CollectionError('procurement-body-edition-mismatch')
    if not actual or not (authority_validator(item,actual) if authority_validator else actual.issubset(authorities(item['managing_authority']))):
        raise CollectionError('procurement-body-authority-mismatch')
    common = {**item, 'body_sha256':hashlib.sha256(raw).hexdigest(), 'fetched_at':as_of,
              'state':'current-body-verified'}
    if authority_validator: common['body_authorities'] = sorted(actual)
    if law:
        from scripts.collect_law_universe import parse_body
        parsed = parse_body(root, dict(name=item['name'], law_id=ident, mst=item['version_id'],
                            effective=item['effective'], category=item.get('category','procurement'), family=item['name']))
        if not parsed['articles']: raise CollectionError('procurement-statute-body-empty')
        return {**parsed, **common, 'body_status':'indexed-statute-text'}
    blocks = [node.text or '' for node in root.findall('.//조문내용')]
    attachments = [{child.tag:''.join(child.itertext()).strip() for child in node}
                   for node in root.findall('.//첨부파일')]
    return {**common, 'raw_body_blocks':blocks, 'attachments':attachments, 'articles':[], 'annexes':[],
            'body_status':'collected-not-indexed',
            'analysis_error':('조문 분석 대기' if any(b.strip() for b in blocks) else 'API 본문 미제공 · 공식 첨부파일 확인 필요')}


def collect_sources(request, inventory, cache_dir, progress=None, *, authority_validator=None):
    cache_dir = Path(cache_dir)
    jobs = [r for r in inventory['records'] if r['state'] == 'current-candidate']
    def fetch(r):
        path = cache_dir / (hashlib.sha256(r['edition_key'].encode()).hexdigest()+'.json')
        if path.exists():
            saved = json.loads(path.read_text(encoding='utf-8'))
            data = saved['body']
            digest = hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            if saved['sha256'] != digest: raise CollectionError('procurement-cache-integrity')
            if all(data.get(k)==r[k] for k in ('edition_key','name','managing_authority')) and data['fetched_at']==inventory['as_of']:
                return data
        data = collect_document(request, r, inventory['as_of'], authority_validator=authority_validator)
        digest = hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        atomic_json(path, dict(sha256=digest, body=data))
        return data
    documents = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        for doc in pool.map(fetch, jobs):
            documents.append(doc)
            if progress: progress(len(documents), len(jobs), doc['name'], doc['body_status'])
    return dict(schema_version=1, domain=inventory.get('domain','procurement'), built_at=inventory['as_of'],
                provider='법제처 공식 API · 수집 판본 고정', inventory=inventory,
                laws=[d for d in documents if d['provider']=='eflaw'],
                administrative_rules=[d for d in documents if d['provider']=='admrul'],
                scheduled=[r for r in inventory['records'] if r['state']=='scheduled'])


def prepare_source(source):
    from core.fsc_administrative import index_rule
    result = deepcopy(source)
    for i, rule in enumerate(result['administrative_rules']):
        try: parsed = index_rule(rule)
        except CollectionError:
            parsed = {**rule, 'articles':[], 'body_status':'collected-not-indexed',
                      'analysis_error':'공식 원문의 조문번호 중복 · 연결 분석 보류'}
        if parsed['articles']:
            parsed.pop('analysis_error', None)
        else:
            parsed.setdefault('analysis_error', '장·절·항목 또는 첨부 형식 · 조문 연결 미분석')
            if parsed['analysis_error'] == '조문 분석 대기':
                parsed['analysis_error'] = '장·절·항목 형식 · 조문 연결 미분석'
        result['administrative_rules'][i] = parsed
    for doc in result['laws'] + result['administrative_rules']:
        a = authorities(doc['managing_authority'])
        doc['sectors'] = ['local'] if '행정안전부' in a else ['procurement'] if a == {'조달청'} else ['national']
        if doc['provider']=='eflaw' and any(norm(f) in norm(doc['name']) for f in FAMILIES[2:]):
            doc['sectors'] = ['national', 'procurement', 'local']
        bare = re.sub(r'^\s*\(계약예규\)\s*', '', doc['name'])
        doc['citation_names'] = list(dict.fromkeys(n for n in [doc['name'], doc.get('short_name'), bare] if n))
        doc['display_name'] = doc.get('short_name') or bare
    return result
