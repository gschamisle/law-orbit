"""Evidence-backed scope relationships, separate from ordinary citation edges.

Labels describe wording, never decide whether a particular institution is subject
to a law. Indirect paths are limited to one intervening provision and retain both
original citation IDs. No embedding similarity or inferred corporate identities.
"""
import hashlib
import re
from core.fsc_collection import norm
from core.citation_scope import parse_target, classify

PUBLIC = '공공기관의 운영에 관한 법률'
PRIVATE = '공기업의 경영구조개선 및 민영화에 관한 법률'
BORROWERS = (
    '공공기관의 정보공개에 관한 법률', '공공기관의 정보공개에 관한 법률 시행령',
    '부정청탁 및 금품등 수수의 금지에 관한 법률',
    '공공데이터의 제공 및 이용 활성화에 관한 법률',
    '전자정부법', '지능정보화 기본법',
    '공공기록물 관리에 관한 법률', '공공기록물 관리에 관한 법률 시행령',
    '중소기업제품 구매촉진 및 판로지원에 관한 법률',
    '중소기업제품 구매촉진 및 판로지원에 관한 법률 시행령',
)
SCOPE_RULES = ('공공기관의 안전활동 수준평가에 관한 고시', '공공기관의 소프트웨어 관리에 관한 규정')
PRIVATE_LAWS = ('상법', '한국가스공사법', '인천국제공항공사법', '한국공항공사법')
LABELS = {'designated':'지정기관 기준', 'criteria':'지정 요건 차용',
          'subset':'기관 유형 한정', 'reference':'범위 원문 확인',
          'additional':'추가 조건', 'exclusion':'제외·예외 문구', 'other-bases':'다른 적용 근거 함께 확인',
          'law-definition':'조 번호 없는 정의 차용', 'indirect':'정의 조문을 경유', 'priority':'우선적용 문구', 'residual':'보충 적용',
          'named':'대상기업 열거', 'end':'적용배제 조건', 'exception':'준용·특례'}

def role(name, provider):
    names = SCOPE_RULES if provider == 'admrul' else BORROWERS + PRIVATE_LAWS
    if norm(name) not in {norm(n) for n in names}: return ''
    return 'privatization-reference' if norm(name) in {norm(n) for n in PRIVATE_LAWS} else 'scope-reference'

def number(edge):
    try: return parse_target(edge.get('target_ref','')).jo
    except ValueError: return ''

def bridge_matches(first, second):
    """The cited item must contain the actual definition-bearing source item.

    Sharing article 2 is insufficient: telecommunications-network definitions
    and public-body definitions often occupy different items of that article.
    """
    if first['target_law'] != second['source_law']: return False
    try:
        relation, _ = classify(first['target_ref'], parse_target(second['source_ref']))
    except ValueError:
        return False
    return relation in ('exact', 'covering', 'range')

def labels_for(clause, article, reference):
    compact = norm(clause)
    labels = []
    # Subsets require an affirmative subject clause, not a mention elsewhere in the article.
    type_text=compact.replace('지방공기업법','').replace('공기업의경영구조개선및민영화에관한법률','')
    if re.search(r'(공기업|준정부기관|기타공공기관)',type_text) and not all(w in type_text for w in ('공기업','준정부기관','기타공공기관')):
        labels.append('subset')
    elif re.search(r'지정(?:된|받은|받는|한|하는)',compact): labels.append('designated')
    elif '제4조제1항' in norm(reference) and re.search(r'해당하는|요건',compact): labels.append('criteria')
    else: labels.append('reference')
    if re.search(r'중에서|중.*(?:정하는|인정하는|필요|선정)|협의하여',compact): labels.append('additional')
    if re.search(r'제외|아니한다|다만|불구하고|특별한규정|원인행위|회계연도',compact): labels.append('exclusion')
    if '지방공기업법' in article or '공직자윤리법' in article: labels.append('other-bases')
    return labels

def build_scope(source, graph):
    docs = {d['name']:d for d in source['laws'] + source.get('administrative_rules',[])}
    articles = {(n,a['jo']):a for n,d in docs.items() for a in d['articles']}
    edges = graph['edges']
    records = []
    def anchor(e):
        if e['target_law']!=PUBLIC:return False
        if e['target_kind']=='article':return number(e) in ('2','4','5','6')
        # An unnumbered definition stays law-level; never assign article 4 to it.
        return e['target_kind']=='law' and bool(re.search(r'정의',articles[(e['source_law'],e['source_jo'])].get('title','')))
    def record(e, kind, labels, path=None):
        a = articles[(e['source_law'],e['source_jo'])]
        context = e.get('context','').strip() or a['text']
        identity = '|'.join([kind, e['evidence_id'], *(x['evidence_id'] for x in path or [])])
        return dict(id=hashlib.sha256(identity.encode()).hexdigest()[:20], kind=kind,
            source_law=e['source_law'], source_jo=e['source_jo'], source_ref=e['source_ref'],
            target_law=e['target_law'], target_jo=number(e), target_ref=e.get('target_ref',''), target_kind=e['target_kind'],
            raw=e['cite_raw'], context=context, source_start=e['source_start'],source_end=e['source_end'],
            source_url=e['source_url'], effective=e['source_effective'], labels=labels,
            evidence_ids=[e['evidence_id'],*(x['evidence_id'] for x in path or [])],
            path=[dict(law=x['source_law'],jo=x['source_jo'],target_law=x['target_law'],target_jo=number(x),source_ref=x['source_ref'],target_ref=x['target_ref'],raw=x['cite_raw']) for x in [e,*(path or [])]],
            review_required=True)
    for e in edges:
        if e['source_law'] == PUBLIC or not anchor(e): continue
        a=articles[(e['source_law'],e['source_jo'])]
        # All direct scope anchors retained, including conditions outside a definitions article.
        r=record(e,'scope',labels_for(e.get('context',''),a['text'],e.get('cite_raw','')))
        if e['target_kind']=='law':r['labels'].append('law-definition')
        records.append(r)
        if number(e)=='2':
            hops=[x for x in edges if x['source_law']==PUBLIC and x['source_jo']=='2' and x['target_law']==PUBLIC and number(x) in ('4','5','6')]
            for h in hops:
                if not bridge_matches(e,h):continue
                indirect=record(e,'indirect',r['labels']+['indirect'],[h])
                indirect.update(target_jo=number(h),target_ref=h['target_ref'])
                records.append(indirect)
    # A different law's definition can itself borrow an anchor (e.g. electronic
    # government -> public data). Only a definitions/scope article may bridge it.
    for h in edges:
        if not anchor(h) or h['source_law']==PUBLIC:continue
        a=articles[(h['source_law'],h['source_jo'])]
        if not re.search(r'정의|적용.*범위|기관의 범위',a.get('title','')):continue
        for e in edges:
            if e['target_law']!=h['source_law'] or number(e)!=h['source_jo'] or e['source_law'] in (PUBLIC,h['source_law']):continue
            if e.get('target_kind')!='article' or not bridge_matches(e,h):continue
            r=record(e,'indirect',labels_for(h.get('context',''),a['text'],h.get('cite_raw',''))+['indirect'],[h])
            r.update(target_law=PUBLIC,target_jo=number(h),target_ref=h['target_ref'],target_kind=h['target_kind'])
            if h['target_kind']=='law':r['labels'].append('law-definition')
            records.append(r)
    # Special-law context is a separate reading guide, not a synthetic legal citation.
    guides=[]
    for jo,types,title in [('2',['named'],'대상기업과 설립 근거'),('3',['priority','residual'],'우선적용·보충 적용'),
                           ('15',['exception'],'감사 특례'),('17',['exception'],'소수주주권 준용'),
                           ('20',['exception'],'주식 매각·재정 특례'),('21',['end'],'적용배제 조건')]:
        a=articles.get((PRIVATE,jo))
        if not a: continue
        guides.append(dict(law=PRIVATE,jo=jo,title=title,
            labels=types,text=a['text'],source_url=docs[PRIVATE]['source_url'],effective=docs[PRIVATE]['effective'],
            related=[dict(law=e['target_law'],jo=number(e),raw=e['cite_raw'],evidence_id=e['evidence_id'],
                          collected=e in edges,url=e.get('target_url',''))
                     for e in edges+graph.get('external_references',[]) if e['source_law']==PRIVATE and e['source_jo']==jo]))
    value=dict(schema=1,kind='public-institution-scope',built_at=source['built_at'],labels=LABELS,
        anchors=[dict(law=PUBLIC,jo=j) for j in ('2','4','5','6')],records=records,privatization=guides,
        coverage='선정한 외부 법령·규정의 명시적 인용을 대조했습니다. 표시는 문구 분류이며 기관별 적용 여부 판정이 아닙니다. 정의 경유는 한 단계만 추적합니다.')
    validate_scope(value,source,graph)
    return value

def validate_scope(value,source,graph):
    docs={d['name']:d for d in source['laws']+source.get('administrative_rules',[])}
    aa={(n,a['jo']):a for n,d in docs.items() for a in d['articles']}
    ee={e['evidence_id']:e for e in graph['edges']}
    for r in value['records']:
        a=aa[(r['source_law'],r['source_jo'])]
        if a['text'][r['source_start']:r['source_end']]!=r['raw']:raise ValueError('scope-evidence-text-mismatch')
        if r['target_law'] not in docs or (r['target_kind']=='article' and (r['target_law'],r['target_jo']) not in aa):raise ValueError('scope-target-missing')
        if not all(e in ee for e in r['evidence_ids']):raise ValueError('scope-evidence-missing')
        if len(r['path']) != len(r['evidence_ids']) or len(r['path']) != (2 if r['kind']=='indirect' else 1):
            raise ValueError('scope-path-length')
        for step,eid in zip(r['path'],r['evidence_ids']):
            edge=ee[eid]
            expected=dict(law=edge['source_law'],jo=edge['source_jo'],target_law=edge['target_law'],
                target_jo=number(edge),source_ref=edge['source_ref'],target_ref=edge['target_ref'],raw=edge['cite_raw'])
            if step != expected:raise ValueError('scope-path-evidence-mismatch')
        first_edge,last_edge=ee[r['evidence_ids'][0]],ee[r['evidence_ids'][-1]]
        for field in ('source_law','source_jo','source_ref','source_start','source_end','source_url'):
            if r[field]!=first_edge[field]:raise ValueError('scope-source-mismatch')
        if r['raw']!=first_edge['cite_raw'] or r['context']!=(first_edge.get('context','').strip() or a['text']):
            raise ValueError('scope-source-context-mismatch')
        if (r['target_law'],r['target_jo'],r['target_ref'],r['target_kind'])!=(last_edge['target_law'],number(last_edge),last_edge['target_ref'],last_edge['target_kind']):
            raise ValueError('scope-final-target-mismatch')
        if r['kind']=='indirect':
            if not bridge_matches(first_edge,last_edge):raise ValueError('scope-path-item-disjoint')
            first,last=r['path']
            if (first['target_law'],first['target_jo'])!=(last['law'],last['jo']):raise ValueError('scope-path-disconnected')
    return value
