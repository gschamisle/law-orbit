"""Declared foreign-exchange scope, isolated from the financial-sector corpus."""
from copy import deepcopy
import re
from core.fsc_collection import CollectionError, norm, ymd
from core.procurement_collection import authorities, record as common_record, discover_query, collect_sources

LAW = '외국환거래법'
REGULATION = '외국환거래규정'
RULES = {
    REGULATION: {'재정경제부','기획재정부'},
    '외국 금융기관의 외국환업무에 관한 지침': {'재정경제부','기획재정부'},
    '외국환업무전문인력교육에관한규정': {'재정경제부','기획재정부'},
    '외환정보집중기관의 운영에 관한 규정': {'재정경제부','기획재정부'},
    '외국환감독업무시행세칙': {'금융감독원'},
    '외국환거래당사자에 대한 제재규정': {'금융위원회'},
    '외국환거래의 검사 및 제재에 관한 훈령': {'관세청'},
    '환전영업자 관리에 관한 고시': {'관세청'},
}
QUERIES = ('외국환','외환정보집중기관','환전영업자')
SCOPE = 'foreign-exchange-law-and-decree; eight-exact-title-rules; four-BOK-official-rule-PDFs; all-collected-main-provisions'
SECTORS = {'all':'전체 연결','common':'기본체계','payment':'지급·송금','capital':'자본거래',
           'market':'외국환업무·시장','reporting':'보고·검사'}
KEYWORDS = {'payment':('지급','송금','상계','환전','수령','영수'),
            'capital':('자본거래','예금','차입','대출','보증','담보','증권','부동산','투자','채권','파생'),
            'market':('외국환업무','외국환은행','외국금융기관','포지션','외환건전성','외환시장','중개','선도은행'),
            'reporting':('보고','신고','정보집중','검사','제재','자료제출','사후관리','모니터링')}

def selected(name, authority, provider):
    allowed = ({'재정경제부','기획재정부'} if provider=='eflaw' and norm(name) in {norm(LAW),norm(LAW+' 시행령')}
               else next((v for k,v in RULES.items() if norm(k)==norm(name)),set()) if provider=='admrul' else set())
    actual=authorities(authority)
    return bool(actual and actual.issubset(allowed))

def record(row, provider, as_of):
    return common_record(row,provider,as_of,selector=selected,domain='forex')

def discover_inventory(request, as_of, progress=None):
    layers=[];current={};scheduled={}
    for provider,queries in [('eflaw',(LAW,)),('admrul',QUERIES)]:
        for query in queries:
            layer=discover_query(request,provider,query,as_of,record_factory=record)
            for item in layer['records']:
                target=scheduled if item['state']=='scheduled' else current
                ident=item['edition_key'] if item['state']=='scheduled' else item['uid']
                if ident in target and target[ident]!=item:raise CollectionError('conflicting-forex-editions')
                target[ident]=item
            layers.append(layer)
            if progress:progress(provider,query,layer['received'],len(layer['records']))
    required={norm(n) for n in (LAW,LAW+' 시행령',*RULES)}
    if required!={norm(d['name']) for d in current.values()}:raise CollectionError('forex-required-title-not-found')
    return dict(domain='forex',as_of=ymd(as_of),scope=SCOPE,layers=layers,
                records=sorted([*current.values(),*scheduled.values()],key=lambda d:(d['name'],d['effective'])))

def tags(name, text):
    # Navigation tags only: never used to omit source articles from analysis.
    value=norm(text)
    result=[tag for tag,words in KEYWORDS.items() if any(w in value for w in words)]
    return result or ['common']

def index_forex_rule(document):
    from core.fsc_administrative import index_rule, body_text, BOUNDARY, provision_blocks
    result=index_rule(document)
    text=body_text(document['raw_body_blocks']);cut=BOUNDARY.search(text)
    main=text[:cut.start()] if cut else text
    # PDF line wrapping may split "이라 한다". Keep evidence offsets in the source.
    definition=re.compile(r'「([^」]+)」\s*\(이하\s*["“]([^"”]+)["”]\s*이?\s*라\s*한\s*다\)')
    definitions=[]
    for match in definition.finditer(main):
        definitions.append(dict(alias=norm(match[2]),target_law=match[1],raw=match[0],start=match.start(),end=match.end()))
    for match in re.finditer(r'동\s*법\s*(시행령|시행규칙)\s*\(이하\s*["“]([^"”]+)["”]\s*이?\s*라\s*한다\)',main):
        prior=[e for e in definitions if e['end']<=match.start()]
        if prior and match.start()-prior[-1]['end']<40:
            base=re.sub(r'\s*시행(?:령|규칙)$','',prior[-1]['target_law'])
            definitions.append(dict(alias=norm(match[2]),target_law=base+' '+match[1],raw=main[prior[-1]['start']:match.end()],start=prior[-1]['start'],end=match.end()))
    names={}
    for e in definitions:names.setdefault(e['alias'],set()).add(norm(e['target_law']))
    for e in definitions:
        if len(names[e['alias']])==1:result['aliases'][e['alias']]=e['target_law']
        else:result['aliases'].pop(e['alias'],None)
    result['alias_evidence']+=definitions
    # A printed "제32조2" cannot silently be treated as 제32조 or 제32조의2.
    result['unparsed_provisions']=[]
    for article in result['articles']:
        bad=re.search(r'(?m)^\s*제\s*\d+\s*조\s*\d+\s*\(',article['text'])
        if bad:
            raw=article['text'][bad.start():].strip()
            result['unparsed_provisions'].append(dict(raw=raw,reason='공식 원문의 조문번호 형식 확인 필요 · 조문 연결 미분석'))
            article['text']=article['text'][:bad.start()].rstrip()
            article['blocks']=provision_blocks(article['text'],article['jo'])
    if result['unparsed_provisions']:
        result['body_status']='partially-indexed-administrative-text'
        result.setdefault('source_notes',[]).append('원문에 제32조2로 표기된 부분은 번호를 추정하지 않고 미분석 원문으로 별도 보존합니다.')
    return result


def prepare_source(source):
    from core.fsc_administrative import index_rule
    from core.forex_bok import TITLES
    result=deepcopy(source)
    if result.get('domain')!='forex':raise ValueError('외환 전용 자료가 아닙니다.')
    for i,d in enumerate(result['administrative_rules']):
        if d['provider']=='bok':
            if d['name'] not in TITLES or d['managing_authority']!='한국은행':raise ValueError('한국은행 수집 범위 불일치')
        elif not selected(d['name'],d['managing_authority'],d['provider']):raise ValueError('외환 규정 수집 범위 불일치')
        parsed=index_forex_rule(d)
        if not parsed['articles']:raise CollectionError('forex-rule-body-not-indexed:'+d['name'])
        parsed.pop('analysis_error',None)
        result['administrative_rules'][i]=parsed
    for d in result['laws']+result['administrative_rules']:
        if d['category']!='forex':raise ValueError('외환 분야에 다른 분야 자료가 섞였습니다.')
        if d['provider']=='eflaw' and not selected(d['name'],d['managing_authority'],d['provider']):raise ValueError('외환 법령 수집 범위 불일치')
        d['sectors']=[]
        for a in d['articles']:
            a['sectors']=tags(d['name'],a['title']+' '+a['text'])
            d['sectors']=list(dict.fromkeys(d['sectors']+a['sectors']))
        d['citation_names']=list(dict.fromkeys([d['name'],d.get('short_name') or d['name']]))
        d['display_name']={LAW:'외환법',LAW+' 시행령':'외환법 시행령',REGULATION:'외환규정',
            '외국 금융기관의 외국환업무에 관한 지침':'외국금융기관 지침','외국환감독업무시행세칙':'외환감독세칙',
            '외국환거래당사자에 대한 제재규정':'외환 제재규정','외국환거래의 검사 및 제재에 관한 훈령':'외환검사·제재 훈령',
            '외국환업무전문인력교육에관한규정':'외환전문인력 교육규정','외환정보집중기관의 운영에 관한 규정':'외환정보 운영규정',
            '환전영업자 관리에 관한 고시':'환전영업자 고시','외국환거래업무 취급세칙':'한은 외환취급세칙',
            '외국환거래업무 취급절차':'한은 외환취급절차','외환정보집중기관 운영세칙':'한은 외환정보세칙',
            '외환정보집중기관 운영절차':'한은 외환정보절차'}.get(d['name'],d['name'])
    return result
