"""Bounded central land/building/housing corpus; never loads another galaxy."""
from copy import deepcopy
from core.fsc_collection import CollectionError, norm, ymd
from core.procurement_collection import (authorities, record as common_record,
    discover_query, collect_sources, collect_document, safe_xml)

PLAN = '국토의 계획 및 이용에 관한 법률'
BUILDING = '건축법'
HOUSING = '주택법'
# Tags describe the chosen review scope, not exclusive ministerial jurisdiction.
FAMILY_TAGS = {
    PLAN: ['planning','building','housing'],
    BUILDING: ['building','housing'],
    HOUSING: ['housing','building'],
    '도시개발법': ['planning','housing'],
    '도시 및 주거환경정비법': ['housing','planning'],
    '공공주택 특별법': ['housing','planning'],
    '건축물관리법': ['building'],
    '공동주택관리법': ['housing'],
    '빈집 및 소규모주택 정비에 관한 특례법': ['housing','building'],
    '민간임대주택에 관한 특별법': ['housing'],
    '개발제한구역의 지정 및 관리에 관한 특별조치법': ['planning','building'],
    '토지이용규제 기본법': ['planning'],
    # Collected independently so actual permit links can be followed.
    '농지법': ['related'], '산지관리법': ['related'], '도로법': ['related'],
    '하천법': ['related'], '수도법': ['related'], '하수도법': ['related'],
}
SPECIAL_TAGS = {
    '주택건설기준 등에 관한 규정': ['housing','building'],
    '주택건설기준 등에 관한 규칙': ['housing','building'],
    '주택공급에 관한 규칙': ['housing'],
    '건축물의 피난ㆍ방화구조 등의 기준에 관한 규칙': ['building','housing'],
    '건축물의 설비기준 등에 관한 규칙': ['building'],
    '건축물의 구조기준 등에 관한 규칙': ['building'],
    '도시ㆍ군계획시설의 결정ㆍ구조 및 설치기준에 관한 규칙': ['planning'],
}
RULE_TAGS = {
    '도시ㆍ군기본계획수립지침': ['planning'],
    '도시ㆍ군관리계획수립지침': ['planning','building'],
    '광역도시계획수립지침': ['planning'],
    '지구단위계획수립지침': ['planning','building','housing'],
    '개발행위허가운영지침': ['planning','building'],
    '도시개발업무지침': ['planning','housing'],
    '공공주택 업무처리지침': ['housing','planning'],
    '도시ㆍ주거환경정비기본계획 수립 지침': ['housing','planning'],
    '건축물의 에너지절약설계기준': ['building','housing'],
    '주택건설공사 감리자지정기준': ['housing','building'],
    '공동주택 분양가격의 산정 등에 관한 시행지침': ['housing'],
    '소규모주택정비사업의 시공자 및 정비사업전문관리업자 선정기준': ['housing'],
}
STATUTE_QUERIES = tuple(FAMILY_TAGS) + tuple(SPECIAL_TAGS)
# Short stable query fragments handle punctuation variation; selection is exact.
RULE_QUERIES = ('기본계획수립지침','관리계획수립지침','광역도시계획','지구단위계획',
    '개발행위허가','도시개발업무','공공주택 업무처리','주거환경정비기본계획',
    '에너지절약설계기준','감리자지정기준','분양가격의 산정','소규모주택정비사업의 시공자')
AUTHORITIES = {'국토교통부','농림축산식품부','산림청','환경부','기후에너지환경부'}
SCOPE = 'declared-18-central-families-7-special-rules-12-administrative-titles; ordinances-not-collected'


def tags(name, provider):
    n = norm(name)
    if provider == 'admrul':
        return next((v[:] for k,v in RULE_TAGS.items() if norm(k)==n), [])
    for family, value in FAMILY_TAGS.items():
        if any(n == norm(family+suffix) for suffix in ('',' 시행령',' 시행규칙')):
            return value[:]
    return next((v[:] for k,v in SPECIAL_TAGS.items() if norm(k)==n), [])


def selected(name, authority, provider):
    a = authorities(authority)
    return bool(a and a.issubset(AUTHORITIES) and tags(name,provider)
                and (provider != 'admrul' or a == {'국토교통부'}))


def record(row, provider, as_of):
    return common_record(row,provider,as_of,selector=selected,domain='housing')


def discover_inventory(request, as_of, progress=None):
    layers, unique = [], {}
    for provider, queries in [('eflaw',STATUTE_QUERIES),('admrul',RULE_QUERIES)]:
        for query in queries:
            layer=discover_query(request,provider,query,as_of,record_factory=record)
            for r in layer['records']:
                old=unique.get(r['uid'])
                if old and any(old[k]!=r[k] for k in ('edition_key','name','managing_authority')):
                    raise CollectionError('conflicting-current-housing-editions')
                unique[r['uid']]=r
            layers.append(layer)
            if progress:progress(provider,query,layer['received'],len(layer['records']))
    found={norm(r['name']) for r in unique.values()}
    missing=[n for n in (*FAMILY_TAGS,*SPECIAL_TAGS,*RULE_TAGS) if norm(n) not in found]
    if missing:
        # Names are public, contain no credential, and make omissions actionable.
        raise CollectionError('required-housing-titles-not-found: '+' / '.join(missing))
    return dict(domain='housing',as_of=ymd(as_of),layers=layers,
                records=sorted(unique.values(),key=lambda r:r['name']),scope=SCOPE)


def prepare_source(source):
    from core.fsc_administrative import index_rule
    result=deepcopy(source)
    if result.get('domain')!='housing':raise ValueError('국토·건축·주택 전용 자료가 아닙니다.')
    for i,rule in enumerate(result['administrative_rules']):
        try:parsed=index_rule(rule)
        except CollectionError:
            parsed={**rule,'articles':[],'body_status':'collected-not-indexed',
                    'analysis_error':'공식 조문번호 중복 · 연결 분석 보류'}
        if parsed['articles']:parsed.pop('analysis_error',None)
        elif parsed.get('analysis_error') in (None,'조문 분석 대기'):
            parsed['analysis_error']='장·절·항목 형식 · 조문 연결 미분석'
        result['administrative_rules'][i]=parsed
    for d in result['laws']+result['administrative_rules']:
        d['sectors']=tags(d['name'],d['provider'])
        if not d['sectors'] or not selected(d['name'],d['managing_authority'],d['provider']):
            raise ValueError('선언한 수집 범위 밖 자료입니다.')
        d['citation_names']=list(dict.fromkeys(n for n in [d['name'],d.get('short_name')] if n))
        d['display_name']=d.get('short_name') or d['name']
    return result
