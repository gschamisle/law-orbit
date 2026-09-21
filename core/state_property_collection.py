"""Explicit national-property scope; no tax, procurement or housing corpus import."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import re
from pathlib import Path
from core.fsc_collection import CollectionError, norm, ymd
from core.procurement_collection import (authorities, record as common_record,
    discover_query, collect_sources as common_collect_sources, collect_document)

PROPERTY = '국유재산법'
SPECIAL = '국유재산특례제한법'
FAMILIES = (PROPERTY, SPECIAL)
CORE_AUTHORITY = {'재정경제부', '기획재정부'}
RULE_QUERIES = ('국유재산', '국유일반재산', '국유증권', '국유농지', '국유지')
SCOPE = ('two-core-national-property-families; finance-ministry-property-rules; '
         'exact-laws-named-in-special-cases-annex; no-automatic-corpus-merge')


def authority_matches(item, actual):
    expected = authorities(item['managing_authority'])
    if actual and actual.issubset(expected): return True
    # Verified official list uses the legislature, while its body names its secretariat.
    return (item['provider']=='eflaw' and item['name'] in {'국회사무처법','대한민국헌정회 육성법'}
            and expected=={'국회'} and actual=={'국회사무처'})


def collect_sources(request, inventory, cache_dir, progress=None):
    return common_collect_sources(request, inventory, cache_dir, progress,
                                  authority_validator=authority_matches)


def selected(name, authority, provider):
    if not authorities(authority) or not authorities(authority).issubset(CORE_AUTHORITY):
        return False
    if provider == 'eflaw':
        return norm(name) in {norm(f+s) for f in FAMILIES for s in ('', ' 시행령', ' 시행규칙')}
    return provider == 'admrul' and any(word in norm(name) for word in RULE_QUERIES)


def record(row, provider, as_of):
    return common_record(row, provider, as_of, selector=selected, domain='state_property')


def discover_inventory(request, as_of, progress=None):
    layers, current, scheduled = [], {}, {}
    for provider, queries in [('eflaw', FAMILIES), ('admrul', RULE_QUERIES)]:
        for query in queries:
            layer = discover_query(request, provider, query, as_of, record_factory=record)
            for item in layer['records']:
                target = scheduled if item['state'] == 'scheduled' else current
                ident = item['edition_key'] if item['state'] == 'scheduled' else item['uid']
                old = target.get(ident)
                if old and any(old[k] != item[k] for k in ('edition_key', 'name', 'managing_authority')):
                    raise CollectionError('conflicting-current-state-property-editions')
                target[ident] = item
            layers.append(layer)
            if progress: progress(provider, query, layer['received'], len(layer['records']))
    names = {norm(x['name']) for x in current.values()}
    required = (PROPERTY, PROPERTY+' 시행령', PROPERTY+' 시행규칙', SPECIAL, SPECIAL+' 시행령')
    if any(norm(name) not in names for name in required):
        raise CollectionError('required-state-property-core-title-not-found')
    if not any(x['provider']=='admrul' for x in current.values()):
        raise CollectionError('state-property-administrative-rules-not-found')
    return dict(domain='state_property', as_of=ymd(as_of), scope=SCOPE, layers=layers,
                records=sorted([*current.values(), *scheduled.values()], key=lambda x:(x['name'],x['effective'])))


def prepare_source(source):
    from core.fsc_administrative import index_rule
    result = deepcopy(source)
    if result.get('domain') != 'state_property':
        raise ValueError('국유재산 전용 자료가 아닙니다.')
    related = set(result.get('related_laws', []))
    for i, rule in enumerate(result['administrative_rules']):
        try:
            parsed = index_rule(rule)
        except CollectionError:
            parsed = {**rule, 'articles':[], 'body_status':'collected-not-indexed',
                      'analysis_error':'공식 원문의 조문번호 중복 · 연결 분석 보류'}
        if parsed['articles']:
            parsed.pop('analysis_error', None)
        elif parsed.get('analysis_error') in (None, '조문 분석 대기'):
            parsed['analysis_error'] = '목록·항목·첨부 형식 · 조문 연결 미분석'
        result['administrative_rules'][i] = parsed
    for doc in result['laws'] + result['administrative_rules']:
        if doc['category'] != 'state_property' or not (
            selected(doc['name'],doc['managing_authority'],doc['provider'])
            or (doc['provider']=='eflaw' and doc['name'] in related)):
            raise ValueError('선언한 국유재산 수집 범위 밖입니다.')
        doc['sectors'] = (['special'] if doc['name'] in related else
                          ['core', 'special'] if SPECIAL in doc['name'] else ['core'])
        if doc['provider']=='admrul': doc['sectors'].append('administration')
        doc['citation_names'] = list(dict.fromkeys(x for x in [doc['name'],doc.get('short_name')] if x))
        doc['display_name'] = doc.get('short_name') or doc['name']
    return result


def discover_related(request, register, cache_dir, progress=None):
    """Only exact titles printed in the annex; related ministries are intentional."""
    from core.fsc_collection import atomic_json
    cache_dir=Path(cache_dir)
    names=sorted({row['law'] for row in register['rows'] if row['law']})
    def one(name):
        cache=cache_dir/(hashlib.sha256(norm(name).encode()).hexdigest()+'.json')
        if cache.exists():
            old=json.loads(cache.read_text(encoding='utf-8'))
            if old['as_of']==register['as_of'] and old['query']==name and old['records']:return old
        def exact(row,provider,as_of):
            return common_record(row,provider,as_of,domain='state_property',
                selector=lambda n,a,p:p=='eflaw' and norm(n)==norm(name) and bool(authorities(a)))
        layer=discover_query(request,'eflaw',name,register['as_of'],record_factory=exact)
        if not layer['records']:
            # Table wrapping can insert spaces inside words. The exact-title filter
            # still decides inclusion after a compact search, never a fuzzy match.
            layer=discover_query(request,'eflaw',re.sub(r'\s+','',name),register['as_of'],record_factory=exact)
            layer['query']=name
        layer['as_of']=register['as_of']
        current=[r for r in layer['records'] if r['state']=='current-candidate']
        if len(current)>1:raise CollectionError('conflicting-state-property-annex-law-editions')
        atomic_json(cache,layer)
        return layer
    layers=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        for i,layer in enumerate(pool.map(one,names),1):
            layers.append(layer)
            if progress and (i%10==0 or i==len(names)):progress('특례 근거 목록',i,len(names))
    return dict(domain='state_property',as_of=register['as_of'],scope=SCOPE,layers=layers,
                records=[r for layer in layers for r in layer['records']],
                missing=[layer['query'] for layer in layers if not any(r['state']=='current-candidate' for r in layer['records'])])
