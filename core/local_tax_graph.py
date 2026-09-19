"""Independent local-tax graphs, jurisdiction shards and nationwide reverse index."""
from __future__ import annotations
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import re
from urllib.parse import quote

from core.citation_scope import Provision, parse_scope, scope_relation
from core.fsc_administrative import adapter as common_adapter, aliases_from
from core.fsc_collection import CollectionError, norm
from core.local_tax_collection import OUTPUT, BASES, read, save
from core.universe_builder import build_universe, ANNEX

NOTE = ('수집한 지방세 법령과 선택 지역의 조례·규칙에서 찾은 직접 인용·역인용입니다. '
        '전국 목록 대조와 지방세 본문 검색 후보 분석을 구분합니다. 검색 밖 자료·지자체 공보는 미대조이며 '
        '부칙·별표 본문과 문구 유사성에 따른 영향은 미분석입니다. 인용 관계가 곧 연계개정 의무를 뜻하지는 않습니다.')


def region_id(authority: str) -> str:
    return sha256(authority.encode()).hexdigest()[:16]


def ordinance_adapter(law: dict, article: dict, corpus: list[dict]) -> list[dict]:
    """Reuse provision/range parsing, with conservative ordinance alias handling."""
    article['citation_issues'] = []
    # Definitions introduced in an article do not become global bindings unless
    # they occur in the first (purpose/definitions) provisions.
    aliases, _ = aliases_from(article['text'])
    definitions = {**law.get('aliases',{}),**aliases}
    text = article['text']
    known = {norm(d.get('official_name',d['name'])):d['name'] for d in corpus}
    # Explicitly named laws outside this region still stay external evidence.
    # Short aliases only resolve when the document defines them.
    candidates = common_adapter({**law,'aliases':definitions},article,corpus)
    citations=[]
    for edge in candidates:
        # "같은 조례" cannot inherit the last named national statute.
        if re.match(r'같은\s*조례',edge['raw']) and not edge['target_name'].endswith('조례'):
            article['citation_issues'].append(dict(raw=edge['raw'],start=edge['start'],end=edge['end'],reason='같은 조례의 선행 조례 미확인'))
            continue
        key=norm(edge['target_name'])
        if key in known: edge['target_name']=known[key]
        citations.append(edge)
    # The common administrative adapter keeps article references. Add annex
    # references separately; never imply that the annex contents were analyzed.
    for match in ANNEX.finditer(text):
        before=text[:match.start()]
        explicit=re.search(r'「([^」]+)」\s*$',before)
        alias=re.search(r'(같은\s*(?:법|영|규칙|조례)|법|영|규칙|조례|이\s*조례|이\s*규칙)\s*$',before)
        owner=law['name'];start=match.start()
        if explicit: owner,start=explicit[1],explicit.start()
        elif alias:
            token=norm(alias[1]);start=alias.start()
            if token in ('이조례','이규칙'): owner=law['name']
            elif token.startswith('같은'):
                anchors=list(re.finditer(r'「([^」]+)」',text[:alias.start()]))
                owner=anchors[-1][1] if anchors else ''
                if owner and token in ('같은영','같은규칙'):
                    owner=re.sub(r'\s*시행(?:령|규칙)$','',owner)+(' 시행령' if token=='같은영' else ' 시행규칙')
                if token=='같은조례' and owner and not owner.endswith('조례'):owner=''
            else: owner=definitions.get(token,'')
        if not owner:
            article['citation_issues'].append(dict(raw=text[start:match.end()],start=start,end=match.end(),reason='별표·서식 소속 법령 미해결'))
            continue
        no=str(int(match[2]))+('의'+str(int(match[3])) if match[3] else '')
        label='별표 '+no if match[1]=='별표' else '별지 제'+no+'호서식'
        citations.append(dict(target_name=known.get(norm(owner),owner),target_ref=label,raw=text[start:match.end()],start=start,end=match.end(),
                              kind='annex',relation='annex_reference',context_review=True,target_analysis='annex-body-not-indexed'))
    return citations


def prepare_document(document: dict) -> dict:
    doc=deepcopy(document)
    if doc.get('provider')=='ordin':
        # The opening purpose/definitions usually defines 법/영/조례. Local
        # redefinitions remain scoped to their own articles in the adapter.
        opening='\n'.join(a['text'] for a in doc['articles'] if a['jo'] in ('1','2'))
        doc['aliases'],doc['alias_evidence']=aliases_from(opening)
        label=doc['name']
        authority=doc.get('managing_authority','')
        for prefix in (authority,authority.split()[-1] if authority else ''):
            if prefix and label.startswith(prefix): label=label[len(prefix):].strip();break
        # UI-only abbreviations must never become legal citation aliases.
        doc['display_name']=label
    else:
        doc['display_name']=doc['name'].replace('지방세특례제한법','지특법')
    return doc


def build_graph(documents: list[dict], as_of: str, *, source_names=None) -> dict:
    # Same-title records must be reviewed rather than merged into one node.
    names=[norm(d['name']) for d in documents]
    if len(names)!=len(set(names)):
        raise CollectionError('local-tax-duplicate-document-name')
    graph=build_universe(dict(laws=documents,built_at=as_of,provider='법제처 Open API'),
                         focus_categories=('local_tax',),preserve_external=True,
                         article_adapter=ordinance_adapter,source_names=source_names)
    by_name={d['name']:d for d in documents}
    graph.update(domain='local_tax',coverage_note=NOTE)
    issues=[]
    for document in documents:
        for article in document['articles']:
            issues.extend(dict(source_law=document['name'],source_jo=article['jo'],source_url=document['source_url'],**i) for i in article.get('citation_issues',[]))
    for edge in graph['edges']+graph['external_references']:
        source=by_name[edge['source_law']]
        edge.update(source_url=source['source_url'],source_authority=source['managing_authority'],source_provider=source['provider'])
        target=by_name.get(edge['target_law'])
        if target:
            edge['target_url']=target['source_url']
        elif '조례' in edge['target_law'] or edge['target_law'].endswith('규칙') and not edge['target_law'].endswith('시행규칙'):
            edge['target_url']='https://www.law.go.kr/자치법규/'+quote(edge['target_law'],safe='')
    graph['citation_issues']=issues
    return graph


def validate_bundle(bundle: dict) -> dict:
    source,graph=bundle['source'],bundle['graph']
    documents=source['laws'];names={d['name'] for d in documents}
    if graph.get('domain')!='local_tax' or not names or len(names)!=len(documents) or set(graph['laws'])!=names:
        raise ValueError('지방세 전용 데이터의 수록 범위가 일치하지 않습니다.')
    if source['built_at']!=graph['built_at'] or any(d.get('category')!='local_tax' or d.get('provider') not in ('eflaw','ordin') for d in documents):
        raise ValueError('지방세 본문과 그래프의 기준이 일치하지 않습니다.')
    if any(d.get('body_status') not in ('indexed-statute-text','indexed-ordinance-text') or not d.get('articles') for d in documents):
        raise ValueError('분석되지 않은 자료가 지도에 포함되어 있습니다.')
    articles={(d['name'],a['jo']):a for d in documents for a in d['articles']}
    for edge in graph['edges']+graph.get('external_references',[]):
        if edge['source_law'] not in names:
            raise ValueError('수집 범위 밖 인용 출처입니다.')
        if edge.get('source_granularity')!='annex':
            article=articles.get((edge['source_law'],edge['source_jo']))
            if not article or article['text'][edge['source_start']:edge['source_end']]!=edge['cite_raw']:
                raise ValueError('인용 근거가 수집한 원문과 일치하지 않습니다.')
    if any(e['target_law'] not in names for e in graph['edges']):
        raise ValueError('미수집 법령을 지도에 연결할 수 없습니다.')
    if any(e['target_law'] in names or e.get('target_status')!='not-collected' for e in graph.get('external_references',[])):
        raise ValueError('외부 인용 상태가 잘못되었습니다.')
    return bundle


def merge_region(base: dict, shard: dict) -> dict:
    if base['graph']['built_at']!=shard['built_at']:
        raise ValueError('지역 자료의 기준일이 중앙 자료와 다릅니다.')
    source=dict(built_at=shard['built_at'],laws=base['source']['laws']+shard['documents'])
    graph={**base['graph']}
    for key in ('laws','focus_laws','catalog','edges','external_references','citation_issues'):
        graph[key]=base['graph'].get(key,[])+shard['graph'].get(key,[])
    graph['relation_counts']=dict(Counter(e['target_kind'] for e in graph['edges']))
    return validate_bundle(dict(source=source,graph=graph))


def publish(output: Path=OUTPUT, as_of: str='') -> dict:
    stage=output/'staging'/as_of
    collected=read(stage/'collection.json')
    central=[prepare_document(d) for d in read(stage/'central.json')]
    base=dict(source=dict(built_at=as_of,laws=central),graph=build_graph(central,as_of))
    validate_bundle(base)
    version=as_of+'-'+datetime.now().strftime('%H%M%S')
    destination=output/'versions'/version
    destination.mkdir(parents=True,exist_ok=False)
    save(destination/'central.json',base)
    groups=defaultdict(list)
    for row in collected['body_status']:
        if row['status']=='indexed': groups[row['managing_authority']].append(row)
    central_names={d['name'] for d in central}
    reverse=defaultdict(list);regions=[];review=[]
    inventory=read(stage/'inventory.json')
    counts=Counter(r['managing_authority'] for r in inventory['records'] if r['kind'] in ('조례','규칙'))
    for number,(authority,rows) in enumerate(sorted(groups.items()),1):
        ordinances=[prepare_document(read(output/'body-cache'/r['path'])['body']) for r in rows]
        # A genuine title collision stays out of analysis and in the review ledger.
        duplicate={name for name,count in Counter(norm(d['name']) for d in ordinances).items() if count>1}
        review.extend(dict(name=d['name'],authority=authority,reason='동일 명칭의 자치법규 ID 중복 · 연결 보류') for d in ordinances if norm(d['name']) in duplicate)
        ordinances=[d for d in ordinances if norm(d['name']) not in duplicate]
        if not ordinances: continue
        local_names={d['name'] for d in ordinances}
        graph=build_graph(central+ordinances,as_of,source_names=local_names)
        graph['catalog']=[d for d in graph['catalog'] if d['name'] in local_names]
        graph['laws']=graph['focus_laws']=sorted(local_names)
        shard=dict(built_at=as_of,authority=authority,documents=ordinances,graph=graph)
        merge_region(base,shard)
        ident=region_id(authority)
        save(destination/'regions'/(ident+'.json'),shard)
        incoming=[e for e in graph['edges'] if e['target_law'] in central_names and e['target_kind']=='article']
        for edge in incoming:
            target=re.match(r'제(\d+)조(?:의(\d+))?',edge['target_ref'])
            if target:
                key=edge['target_law']+'|'+target[1]+('의'+target[2] if target[2] else '')
                reverse[key].append({**edge,'region_id':ident})
        regions.append(dict(id=ident,authority=authority,province=authority.split()[0],inventory=counts[authority],indexed=len(ordinances),
                            articles=sum(len(d['articles']) for d in ordinances),central_citations=len(incoming),
                            issues=len(graph['citation_issues']),file='regions/'+ident+'.json'))
        if number%20==0 or number==len(groups):print(f'지역 지도 {number}/{len(groups)} 생성',flush=True)
    # One reverse-index file per central article avoids a nationwide mega-graph.
    targets=[]
    for key,edges in reverse.items():
        file='reverse/'+sha256(key.encode()).hexdigest()[:20]+'.json'
        save(destination/file,edges)
        targets.append(dict(target=key,file=file,evidence=len(edges),regions=len({e['region_id'] for e in edges})))
    for authority,count in sorted(counts.items()):
        if authority not in groups:
            regions.append(dict(id=region_id(authority),authority=authority,province=authority.split()[0],inventory=count,indexed=0,
                                articles=0,central_citations=0,issues=0,file=None))
    manifest={k:v for k,v in collected.items() if k not in ('body_status','skipped')}
    manifest.update(domain='local_tax',version=version,central_documents=len(central),regions=sorted(regions,key=lambda r:r['authority']),
                    indexed=sum(r['indexed'] for r in regions),reverse_targets=targets,review=review,coverage_note=NOTE,
                    skipped_count=len(collected['skipped']),central_file='central.json')
    save(destination/'manifest.json',manifest)
    # Only this small pointer changes after every shard and evidence is validated.
    save(output/'current.json',dict(domain='local_tax',version=version,as_of=as_of))
    return manifest


def load_manifest(output: Path=OUTPUT) -> tuple[Path,dict]:
    current=read(output/'current.json')
    if current.get('domain')!='local_tax' or not re.fullmatch(r'\d{8}-\d{6}',current.get('version','')):
        raise ValueError('지방세 자료 경로가 올바르지 않습니다.')
    folder=output/'versions'/current['version']
    manifest=read(folder/'manifest.json')
    if manifest.get('domain')!='local_tax' or manifest.get('version')!=current['version']:
        raise ValueError('지방세 자료 버전이 일치하지 않습니다.')
    return folder,manifest


def load_bundle(folder: Path, manifest: dict, region: str='') -> dict:
    base=validate_bundle(read(folder/'central.json'))
    if not region: return base
    chosen=next((r for r in manifest['regions'] if r['id']==region),None)
    if not chosen or not chosen.get('file'):raise ValueError('선택 지역의 조례·규칙 데이터 미수집')
    return merge_region(base,read(folder/chosen['file']))


def national_reverse(folder: Path, manifest: dict, law: str, reference: str) -> list[dict]:
    from core.galaxy_focus import _target
    from core.citation_scope import classify
    target=_target(reference)
    chosen=next((r for r in manifest['reverse_targets'] if r['target']==law+'|'+target.jo),None)
    if not chosen:return []
    return [e for e in read(folder/chosen['file']) if classify(e['cite_raw'],target)[0]!='disjoint']
