"""FTC-owned current editions; substantive rules selected by declared title groups."""
from copy import deepcopy
import re
from core.fsc_collection import CollectionError, norm, ymd
from core.procurement_collection import authorities, record, discover_query, collect_sources
from core.fsc_administrative import index_rule
from core.mofe_citations import prepare_aliases

DOMAIN='ftc'
ORG='1130000'
ORG_SOURCE='https://theme.archives.go.kr/next/organ/organBasicInfo.do?code=OG0000928'
FAIR='독점규제 및 공정거래에 관한 법률'
FAMILIES={
    FAIR:['competition','groups'],
    '하도급거래 공정화에 관한 법률':['subcontract'],
    '가맹사업거래의 공정화에 관한 법률':['distribution'],
    '대규모유통업에서의 거래 공정화에 관한 법률':['distribution'],
    '대리점거래의 공정화에 관한 법률':['distribution'],
    '약관의 규제에 관한 법률':['consumer'],
    '표시ㆍ광고의 공정화에 관한 법률':['consumer'],
    '방문판매 등에 관한 법률':['consumer'],
    '전자상거래 등에서의 소비자보호에 관한 법률':['consumer'],
    '할부거래에 관한 법률':['consumer'],
    '소비자기본법':['consumer'],
    '소비자생활협동조합법':['consumer'],
    '제조물 책임법':['consumer'],
}
SECTORS={'all':'전체 연결','competition':'경쟁·기업결합','groups':'기업집단',
         'subcontract':'하도급','distribution':'가맹·유통·대리점','consumer':'소비자·약관','procedure':'조사·사건절차'}
RULE_PATTERNS={
    'competition':r'기업결합|시장지배|공동행위|불공정거래|재판매가격|사업자단체|온라인플랫폼|지식재산권|거래상지위',
    'groups':r'기업집단|지주회사|상호출자|부당(?:한)?지원|특수관계인|사익편취|내부거래|공익법인',
    'subcontract':r'하도급|부당특약|기술자료|기술유용',
    'distribution':r'가맹|대리점|대규모유통|유통업',
    'consumer':r'소비자|약관|표시광고|방문판매|전자상거래|통신판매|할부거래|선불식|다단계',
}
PROCEDURE_RULES=(
    '공정거래위원회 회의 운영 및 사건절차 등에 관한 규칙',
    '공정거래위원회 조사절차에 관한 규칙',
    '동의의결제도 운영 및 절차 등에 관한 규칙',
    '과징금부과 세부기준 등에 관한 고시',
    '과징금 납부기한 연기 및 분할납부 기준에 관한 고시',
    '공정거래위원회 소관 법률에 따른 행정처분 및 과태료의 가중처분에 관한 세부 지침',
    '독점규제 및 공정거래에 관한 법률 등의 위반행위의 고발에 관한 공정거래위원회의 지침',
    '경제분석 의견서 등의 제출에 관한 규정',
    '공정거래위원회의 시정조치 운영지침',
    '공정거래위원회로부터 시정명령을 받은 사실의 공표에 관한 운영지침',
    '공정거래위원회 의결 등의 공개에 관한 지침',
    '공정거래위원회본부와 지방공정거래사무소간 사건처리지침',
    '독점규제 및 공정거래에 관한 법률 등의 위반여부 사전심사청구에 관한 운영지침',
    '디지털 증거의 수집·분석 및 관리 등에 관한 규칙',
    '자료의 열람·복사 업무지침',
    '현장조사 수집·제출자료에 대한 이의제기 업무지침',
    '재신고사건 처리지침',
)
ADDITIONAL_RULES={
    '동일인 판단 기준 및 확인 절차에 관한 지침':['groups'],
    '독립경영 인정제도 운영지침':['groups'],
    '합병 관련 순환출자 금지 규정 해석지침':['groups','competition'],
    '공정거래 자율준수제도(CP) 운영·평가에 관한 규정':['competition','procedure'],
    '법령 등의 경쟁제한사항 심사지침':['competition'],
    '소상공인 단체 행위에 대한 심사지침':['competition'],
    '부당한 위탁취소, 수령거부 및 반품행위에 대한 심사지침':['subcontract'],
    '선급금 등 지연지급 시의 지연이율 고시':['subcontract'],
    '용역위탁 중 역무의 범위 고시':['subcontract'],
    '용역위탁 중 지식·정보성과물의 범위 고시':['subcontract'],
    '제조위탁의 대상이 되는 물품의 범위 고시':['subcontract'],
    '구입강제품목 거래조건 변경 협의에 대한 고시':['distribution'],
    '상품판매대금 등 지연지급 시의 지연이율 고시':['distribution'],
    '대·중소기업간 공정거래협약 이행평가 등에 관한 기준(유통분야)':['distribution'],
    '계속거래 등의 해지·해제에 따른 위약금 및 대금의 환급에 관한 산정기준':['consumer'],
    '인터넷 광고에 관한 심사지침':['consumer'],
    '정정광고에 관한 운영지침':['consumer'],
    '임시중지명령에 관한 운영지침':['consumer','procedure'],
}
# Administrative operations with matching topical words are not substantive scope.
EXCLUDED_RULES=(
    '1372소비자상담센터 상담원 보호에 관한 업무 운영지침',
    '소비자상담센터 운영규정','소비자정책위원회 위원 추천관련 고시',
    '소비자정책자문단 설치·운영에 관한 규정','지역소비자정책 전문가협의체 설치 및 운영에 관한 규정',
    '약관심사 자문위원의 위촉 및 운영에 관한 규정','표시·광고심사자문위원회의 설치 및 운영에 관한 규정',
    '소비자생활협동조합 표준정관례',
)
REQUIRED_RULES=('불공정거래행위 심사지침','기업결합 심사기준',PROCEDURE_RULES[0])
SCOPE='FTC current 13 declared statute families and substantive title-group rules; no internal administration or rulings'


def tags(name,provider):
    n=norm(name)
    if provider=='eflaw':
        return next((v[:] for k,v in FAMILIES.items() if any(n==norm(k+s) for s in ('',' 시행령',' 시행규칙'))),[])
    if provider!='admrul':return []
    if n in {norm(v) for v in EXCLUDED_RULES}:return []
    result=[k for k,p in RULE_PATTERNS.items() if re.search(p,n)]
    result+=next((v for k,v in ADDITIONAL_RULES.items() if norm(k)==n),[])
    if n in {norm(v) for v in PROCEDURE_RULES}:result.append('procedure')
    return list(dict.fromkeys(result))


def selected(name,authority,provider):
    actual=authorities(authority)
    # Jointly administered product liability is retained; FTC ownership is mandatory.
    return '공정거래위원회' in actual and bool(tags(name,provider))


def discover_inventory(request,as_of,progress=None):
    as_of=ymd(as_of);layers=[];unique={};excluded=[]
    def scoped_request(endpoint,params):return request(endpoint,{**params,'org':ORG})
    def factory(row,provider,stamp):
        item=record(row,provider,stamp,selector=lambda *args:True,domain=DOMAIN)
        if '공정거래위원회' not in authorities(item['managing_authority']):
            raise CollectionError('ftc-list-authority-mismatch')
        if not selected(item['name'],item['managing_authority'],provider):
            excluded.append({**item,'exclusion':'선정한 실체법·집행기준 범위 밖'});return None
        return item
    for provider in ('eflaw','admrul'):
        layer=discover_query(scoped_request,provider,'',as_of,record_factory=factory)
        for item in layer['records']:
            identity=item['edition_key'] if item['state']=='scheduled' else item['uid']
            if identity in unique and unique[identity]!=item:raise CollectionError('ftc-conflicting-current-editions')
            unique[identity]=item
        layers.append(layer)
        if progress:progress(provider,'목록',layer['received'],'선정',len(layer['records']))
    found={norm(d['name']) for d in unique.values() if d['state']=='current-candidate'}
    missing=[n for n in (*FAMILIES,*REQUIRED_RULES) if norm(n) not in found]
    if missing:raise CollectionError('ftc-required-documents-missing:'+','.join(missing))
    return dict(domain=DOMAIN,as_of=as_of,scope=SCOPE,org=ORG,org_source=ORG_SOURCE,
                layers=layers,records=sorted(unique.values(),key=lambda d:(d['name'],d['effective'])),excluded=excluded)


def prepare_source(source):
    if source.get('domain')!=DOMAIN:raise ValueError('공정거래 전용 수집 자료가 아닙니다.')
    result=deepcopy(source)
    for i,rule in enumerate(result['administrative_rules']):
        try:parsed=index_rule(rule)
        except CollectionError as error:
            if not str(error).startswith('administrative-duplicate-article:'):raise
            parsed={**rule,'articles':[],'body_status':'collected-not-indexed','analysis_error':'공식 조문번호 중복 · 원문 확인 필요'}
        if parsed['articles']:parsed.pop('analysis_error',None)
        elif parsed.get('analysis_error') in (None,'조문 분석 대기'):
            parsed['analysis_error']='문단·표 형식 · 조문 번호 미부여 · 본문 인용은 별도 확인'
        result['administrative_rules'][i]=parsed
    for d in result['laws']+result['administrative_rules']:
        if d['category']!=DOMAIN or not selected(d['name'],d['managing_authority'],d['provider']):
            raise ValueError('공정거래 소관·수집 범위 불일치')
        d['sectors']=tags(d['name'],d['provider'])
        # Keep official titles in selectors; short names remain available for matching.
        d['display_name']=d['name']
        d['citation_names']=list(dict.fromkeys(n for n in (d['name'],d.get('short_name')) if n))
        prepare_aliases(d)
        from core.ftc_text_citations import prepare_text_aliases
        prepare_text_aliases(d)
        d['aliases'].update({n:d['name'] for n in ('이고시','이규정','이훈령','이예규','이기준','이지침','본지침')})
    return result
