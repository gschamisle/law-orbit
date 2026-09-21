"""Pinned official data; independent domain scopes; rejected candidates remain auditable."""
from copy import deepcopy
from core.fsc_collection import CollectionError,norm,ymd
from core.procurement_collection import record,discover_query,collect_sources
from core.fsc_administrative import index_rule
from core.mofe_profiles import PROFILES,selected,tags

LABELS={
 '공기업·준정부기관 계약사무규칙':'공기업·준정부 계약규칙',
 '공기업·준정부기관 회계사무규칙':'공기업·준정부 회계규칙',
 '공기업·준정부기관 사업 예비타당성조사 운용지침':'공기업 사업예타 지침',
 '공기업·준정부기관 총사업비관리지침':'공기업 총사업비 지침',
 '공기업·준정부기관 회계기준':'공기업·준정부 회계기준',
 '공공기관의 개발선정품 지정 및 운영에 관한 기준':'개발선정품 기준',
 '기타공공기관 계약사무 운영규정':'기타공공기관 계약규정',
 '자유무역협정의 이행을 위한 관세법의 특례에 관한 법률 사무처리에 관한 고시':'FTA관세 사무처리 고시',
 '수출용 원재료에 대한 관세 등 환급사무처리에 관한 고시':'관세환급 고시',
 '수출용 원재료에 대한 관세 등 환급사무에 관한 훈령':'관세환급 훈령',
 '수출용 원재료에 대한 관세 등의 일괄납부 및 정산에 관한 고시':'관세 일괄납부·정산 고시',
 '관세법 제226조에 따른 세관장확인물품 및 확인방법 지정고시':'세관장확인 고시',
 '관세법 제246조의3에 따른 안전성 검사 업무처리에 관한 고시':'수입물품 안전성검사 고시',
 '국가관세종합정보시스템의 이용 및 운영 등에 관한 고시':'관세정보시스템 고시',
 '국가채권 체납 등의 자료 제공 및 신고 포상금 지급에 관한 규정':'국가채권 자료·포상금 규정',
 '국고채권의 발행 및 국고채전문딜러 운영에 관한 규정':'국고채 발행·딜러 규정',
 '국고채전문딜러에 대한 금융지원에 관한 기준':'국고채딜러 금융지원 기준',
}

def discover_inventory(request,domain,as_of,progress=None):
    p=PROFILES[domain];layers=[];unique={};excluded={}
    for provider,queries in [('eflaw',p['law_queries']),('admrul',p['rule_queries'])]:
        for query in queries:
            def factory(row,provider,stamp):
                item=record(row,provider,stamp,selector=lambda *args:True,domain=domain)
                if not selected(domain,item['name'],item['managing_authority'],provider):
                    excluded[item['edition_key']]={**item,'exclusion':'소관 또는 선언한 업무 범위 밖'};return None
                return item
            layer=discover_query(request,provider,query,as_of,record_factory=factory)
            for item in layer['records']:
                identity=item['edition_key'] if item['state']=='scheduled' else item['uid']
                if identity in unique and unique[identity]!=item:raise CollectionError('mofe-conflicting-current-editions')
                unique[identity]=item
            layers.append(layer)
            if progress:progress(provider,query,layer['received'],len(layer['records']))
    actual={norm(d['name']) for d in unique.values() if d['state']=='current-candidate'}
    missing=[n for n in (*p['required'],*p['required_rules']) if norm(n) not in actual]
    if missing:raise CollectionError('mofe-required-documents-missing:'+','.join(missing))
    return dict(domain=domain,as_of=ymd(as_of),scope='declared-current-MOFE-work-area; exact-statutes-and-selected-rules; not-complete-ministry-corpus',
                layers=layers,records=sorted(unique.values(),key=lambda d:(d['name'],d['effective'])),
                excluded=sorted(excluded.values(),key=lambda d:d['name']),
                unavailable_selected_rules=[n for n in p['rules'] if norm(n) not in actual])

def prepare_source(source):
    domain=source['domain'];p=PROFILES[domain];result=deepcopy(source)
    for i,rule in enumerate(result['administrative_rules']):
        try:parsed=index_rule(rule)
        except CollectionError as e:
            if not str(e).startswith('administrative-duplicate-article:'):raise
            parsed={**rule,'articles':[],'body_status':'collected-not-indexed','analysis_error':'조문번호 중복 · 원문 확인 필요'}
        if parsed['articles']:parsed.pop('analysis_error',None)
        else:parsed['analysis_error']='문단·표·첨부 형식 · 조문 연결 미분석'
        result['administrative_rules'][i]=parsed
    for d in result['laws']+result['administrative_rules']:
        if d['category']!=domain or not selected(domain,d['name'],d['managing_authority'],d['provider']):
            raise ValueError('재경부 분야 수집 범위 불일치')
        display=next((v for k,v in LABELS.items() if norm(k)==norm(d['name'])),None)
        d['display_name']=display or d.get('short_name') or d['name'].replace(' 사무처리에 관한 고시',' 고시').replace(' 운영에 관한 고시',' 운영 고시')
        # Display abbreviations are not legal citation aliases.
        d['citation_names']=list(dict.fromkeys([n for n in (d['name'],d.get('short_name')) if n]))
        d['sectors']=tags(domain,d['name'],'')
        for a in d['articles']:
            a['sectors']=tags(domain,'',a.get('title','')+' '+a['text'])
            d['sectors']=list(dict.fromkeys(d['sectors']+a['sectors']))
        from core.mofe_citations import prepare_aliases
        prepare_aliases(d)
        # Self references and explicit title aliases, without borrowing another domain's parser policy.
        d.setdefault('aliases',{}).update({n:d['name'] for n in ('이고시','이훈령','이예규','이기준','이지침','본지침')})
    return result
