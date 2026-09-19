"""Declared central environment/chemical-safety scope, with exact official titles."""
from copy import deepcopy
from core.fsc_collection import CollectionError, norm, ymd
from core.procurement_collection import (authorities, record as common_record,
    discover_query, collect_sources as common_collect_sources, collect_document, safe_xml)

ENVIRONMENT='환경오염시설의 통합관리에 관한 법률'
CHEMICAL='화학물질의 등록 및 평가 등에 관한 법률'
SAFETY='화학물질관리법'
FAMILY_TAGS={
    '환경정책기본법':['environment'],
    '환경영향평가법':['environment'],
    ENVIRONMENT:['environment','chemical'],
    '대기환경보전법':['environment'],
    '물환경보전법':['environment','accident'],
    '폐기물관리법':['environment','chemical'],
    '토양환경보전법':['environment','accident'],
    '환경보건법':['environment','chemical'],
    '잔류성오염물질 관리법':['environment','chemical'],
    CHEMICAL:['chemical'],
    SAFETY:['chemical','accident'],
    '생활화학제품 및 살생물제의 안전관리에 관한 법률':['chemical','accident'],
    '환경오염피해 배상책임 및 구제에 관한 법률':['environment','accident'],
    '산업안전보건법':['accident'],
    '위험물안전관리법':['accident'],
    '고압가스 안전관리법':['accident'],
}
SPECIAL_TAGS={'산업안전보건기준에 관한 규칙':['accident']}
RULE_TAGS={
    '화학물질의 분류 및 표시 등에 관한 규정':['chemical','accident'],
    '등록신청자료의 작성방법 및 유해성심사 방법 등에 관한 규정':['chemical'],
    '화학물질 위해성평가의 구체적 방법 등에 관한 규정':['chemical'],
    '화학물질의 시험방법에 관한 규정':['chemical'],
    '화학물질의 분류·표시 및 물질안전보건자료에 관한 기준':['chemical','accident'],
    '등록신청자료의 위해성 작성방법에 관한 규정':['chemical'],
    '화학사고예방관리계획서 이행 등에 관한 규정':['accident'],
    '안전확인대상생활화학제품 승인 등에 관한 규정':['chemical'],
    '안전확인대상생활화학제품 시험·검사 기준 및 방법 등에 관한 규정':['chemical'],
    '살생물물질과 살생물제품의 승인기준':['chemical'],
    '반도체·디스플레이 제조업종 유해화학물질 취급시설 설치 및 관리에 관한 고시':['chemical','accident'],
    '인체급성유해성물질, 인체만성유해성물질 및 생태유해성물질의 지정고시':['chemical','accident'],
    '제한물질ㆍ금지물질의 지정':['chemical','accident'],
    '사고대비물질의 지정':['chemical','accident'],
    '유해화학물질 소량 취급시설에 관한 고시':['chemical','accident'],
    '화학사고예방관리계획서 작성 등에 관한 규정':['accident','chemical'],
    '화학사고예방관리계획서 검토 등에 관한 규정':['accident'],
    '화학물질의 배출량조사 및 산정계수에 관한 규정':['environment','chemical'],
    '화학물질 통계조사에 관한 규정':['chemical'],
    '안전확인대상생활화학제품 지정 및 안전ㆍ표시기준':['chemical','accident'],
    '살생물물질과 살생물제품 승인신청자료의 작성범위 및 작성방법 등에 관한 규정':['chemical'],
    '공정안전보고서의 제출ㆍ심사ㆍ확인 및 이행상태평가 등에 관한 규정':['accident'],
    '위험물안전관리에 관한 세부기준':['accident'],
    '환경영향평가서등 작성 등에 관한 규정':['environment'],
}
DISPLAY_NAMES={
    '화학사고예방관리계획서 작성 등에 관한 규정':'화학사고예방계획 작성규정',
    '화학사고예방관리계획서 검토 등에 관한 규정':'화학사고예방계획 검토규정',
    '화학사고예방관리계획서 이행 등에 관한 규정':'화학사고예방계획 이행규정',
    '공정안전보고서의 제출ㆍ심사ㆍ확인 및 이행상태평가 등에 관한 규정':'공정안전보고서규정',
    '등록신청자료의 작성방법 및 유해성심사 방법 등에 관한 규정':'화학물질 등록자료·유해성심사규정',
    '등록신청자료의 위해성 작성방법에 관한 규정':'화학물질 위해성자료 작성규정',
    '인체급성유해성물질, 인체만성유해성물질 및 생태유해성물질의 지정고시':'인체·생태 유해성물질 지정고시',
    '화학물질의 분류·표시 및 물질안전보건자료에 관한 기준':'화학물질 분류·표시·MSDS 기준',
    '살생물물질과 살생물제품 승인신청자료의 작성범위 및 작성방법 등에 관한 규정':'살생물물질·제품 승인자료 규정',
    '반도체·디스플레이 제조업종 유해화학물질 취급시설 설치 및 관리에 관한 고시':'반도체·디스플레이 화학시설 기준',
}
AUTHORITIES={'환경부','기후에너지환경부','화학물질안전원','국립환경과학원',
             '고용노동부','소방청','산업통상자원부','산업통상부'}
STATUTE_QUERIES=tuple(FAMILY_TAGS)+tuple(SPECIAL_TAGS)
RULE_QUERIES=('화학물질의 분류','등록신청자료','화학물질의 위해성평가','화학물질의 시험방법',
              '인체급성유해성물질','제한물질','사고대비물질','화학사고예방관리계획서',
              '화학물질 배출량조사','화학물질 통계조사','안전확인대상생활화학제품',
              '살생물물질과 살생물제품','공정안전보고서','위험물안전관리','환경영향평가서',
              '유해화학물질')
SCOPE='16-central-families; industrial-safety-standards; declared-administrative-titles-and-NICS-facility-standards; not-all-environment-rules'


def facility_rule(name):
    n=norm(name)
    return n.startswith('유해화학물질') and '시설' in n and ('설치및관리에관한고시' in n or '설치및관리에관한세부기준' in n)


def tags(name,provider):
    n=norm(name)
    if provider=='admrul':
        if facility_rule(name):return ['chemical','accident']
        return next((v[:] for k,v in RULE_TAGS.items() if norm(k)==n),[])
    if provider!='eflaw':return []
    for family,value in FAMILY_TAGS.items():
        if any(n==norm(family+suffix) for suffix in ('',' 시행령',' 시행규칙')):return value[:]
    return next((v[:] for k,v in SPECIAL_TAGS.items() if norm(k)==n),[])


def selected(name,authority,provider):
    a=authorities(authority)
    if not a or not a.issubset(AUTHORITIES) or not tags(name,provider):return False
    if provider=='admrul' and facility_rule(name):return a=={'화학물질안전원'}
    return True


def record(row,provider,as_of):
    return common_record(row,provider,as_of,selector=selected,domain='environment')


def discover_inventory(request,as_of,progress=None):
    layers,unique,scheduled=[],{},{}
    for provider,queries in [('eflaw',STATUTE_QUERIES),('admrul',RULE_QUERIES)]:
        for query in queries:
            layer=discover_query(request,provider,query,as_of,record_factory=record)
            for r in layer['records']:
                # The official current-rules endpoint can return both an effective
                # edition and already-promulgated future editions for the same ID.
                # Keep future metadata separate; only one effective edition may win.
                target=scheduled if r['state']=='scheduled' else unique
                identity=r['edition_key'] if r['state']=='scheduled' else r['uid']
                old=target.get(identity)
                if old and any(old[k]!=r[k] for k in ('edition_key','name','managing_authority')):
                    raise CollectionError('conflicting-current-environment-editions')
                target[identity]=r
            layers.append(layer)
            if progress:progress(provider,query,layer['received'],len(layer['records']))
    found={norm(r['name']) for r in unique.values()}
    missing=[n for n in (*FAMILY_TAGS,*SPECIAL_TAGS,*RULE_TAGS) if norm(n) not in found]
    if missing:raise CollectionError('required-environment-titles-not-found: '+' / '.join(missing))
    if not any(facility_rule(r['name']) for r in unique.values()):raise CollectionError('chemical-facility-rules-not-found')
    return dict(domain='environment',as_of=ymd(as_of),layers=layers,
                records=sorted([*unique.values(),*scheduled.values()],key=lambda r:(r['name'],r['effective'])),scope=SCOPE)


def prepare_source(source):
    from core.fsc_administrative import index_rule
    result=deepcopy(source)
    if result.get('domain')!='environment':raise ValueError('환경·화학안전 전용 자료가 아닙니다.')
    for i,rule in enumerate(result['administrative_rules']):
        try:parsed=index_rule(rule)
        except CollectionError:
            parsed={**rule,'articles':[],'body_status':'collected-not-indexed',
                    'analysis_error':'공식 조문번호 중복 · 연결 분석 보류'}
        if parsed['articles']:parsed.pop('analysis_error',None)
        elif parsed.get('analysis_error') in (None,'조문 분석 대기'):
            parsed['analysis_error']='장·절·항목 또는 지정 목록 형식 · 조문 연결 미분석'
        result['administrative_rules'][i]=parsed
    for d in result['laws']+result['administrative_rules']:
        d['sectors']=tags(d['name'],d['provider'])
        if not selected(d['name'],d['managing_authority'],d['provider']):raise ValueError('선언한 환경·화학안전 수집 범위 밖입니다.')
        d['citation_names']=list(dict.fromkeys(n for n in [d['name'],d.get('short_name')] if n))
        d['display_name']=d.get('short_name') or next((v for k,v in DISPLAY_NAMES.items() if norm(k)==norm(d['name'])),d['name'])
        d['display_name_kind']='official-short-name' if d.get('short_name') else 'ui-short-label' if d['display_name']!=d['name'] else 'official-name'
    return result


def authority_matches(item, actual):
    expected=authorities(item['managing_authority'])
    if actual and actual.issubset(expected):return True
    # These three pinned official bodies list both the ministry and its committee,
    # whereas their list entries report the ministry alone. No other mismatch is waived.
    family='환경오염피해 배상책임 및 구제에 관한 법률'
    return (item['provider']=='eflaw' and norm(item['name']) in {norm(family+s) for s in ('',' 시행령',' 시행규칙')}
            and expected=={'기후에너지환경부'}
            and actual=={'기후에너지환경부','중앙환경분쟁조정피해구제위원회'})


def collect_sources(request,inventory,cache_dir,progress=None):
    return common_collect_sources(request,inventory,cache_dir,progress,authority_validator=authority_matches)
