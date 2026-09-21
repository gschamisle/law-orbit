"""Shared profiles plus evidence-based acceptance reports for three MOFE work areas."""
from pathlib import Path
from collections import Counter
from core import procurement_universe as shared
from core.procurement_universe import documents,sector_graph,article_for,external_evidence
from core.mofe_profiles import PROFILES,selected

ROOT=Path(__file__).resolve().parents[1]

def path(domain):return ROOT/f'output/{domain}-universe/bundle.json'

def coverage(domain):
    return (PROFILES[domain]['purpose']+' '+' '.join(PROFILES[domain]['limitations'])+
            ' 업무 태그는 조문 제목·본문 키워드에 따른 탐색 보조이며 법적 적용범위 판정이 아닙니다. '
            '수집 본칙의 명시적 인용을 분석합니다. 따옴표 속 조문 등 대상이 불명확한 인용은 확인 목록으로 남깁니다. 별표·서식 본문과 부칙은 미분석이며, '
            '외부 법령의 본문·역인용은 점검하지 않았습니다. 인용선은 동시개정 의무가 아닙니다.')

def build_graph(source):
    domain=source['domain'];graph=shared.build_graph(source,domain=domain,coverage_note=coverage(domain))
    graph['article_catalog']={d['name']:[dict(jo=a['jo'],title=a['title'],sectors=a['sectors']) for a in d['articles']] for d in documents(source)}
    return graph

def validate_bundle(bundle,domain):
    shared.validate_bundle(bundle,domain=domain)
    for d in documents(bundle['source']):
        if not selected(domain,d['name'],d['managing_authority'],d['provider']):raise ValueError('소관·업무 범위 외 자료')
        if 'analyzed_articles' in d:raise ValueError('선택한 본칙의 임의 분석 생략')
    return bundle

def load_bundle(domain,file=None):
    import json
    return validate_bundle(json.loads(Path(file or path(domain)).read_text(encoding='utf-8')),domain)

def mark_sector(result,graph,sector):
    from copy import deepcopy
    result=deepcopy(result)
    tags={(n,a['jo']):a['sectors'] for n,aa in graph['article_catalog'].items() for a in aa}
    doc_tags={d['name']:d['sectors'] for d in graph['catalog']}
    for r in result['rows']+result.get('broad_rows',[]):
        value=tags.get((r['neighbor_law'],r['neighbor_jo']),[]) if r['neighbor_kind']=='article' else doc_tags.get(r['neighbor_law'],[])
        outside=sector!='all' and sector not in value
        r.update(out_of_sector=outside,sector_relation='분야 밖 관련 조문' if outside else '선택 분야')
    return result

def present(data,graph,sector):
    domain=graph['domain'];p=PROFILES[domain]
    from core.mofe_layout import layout
    return layout(shared.present(data,graph,sector,domain=domain,title=p['title'],sectors=p['sectors']),graph)

def assessment(bundle):
    from core.galaxy_focus import analyze_focus
    from core.citation_scope import parse_target
    domain=bundle['graph']['domain'];p=PROFILES[domain];g=bundle['graph'];docs=documents(bundle['source'])
    pairs=set();incident=Counter();cross=[];missing=[]
    indexed={(d['name'],a['jo']) for d in docs for a in d['articles']}
    for e in g['edges']:
        if e['target_kind']!='article':continue
        try:jo=parse_target(e['target_ref']).jo
        except ValueError:continue
        if (e['target_law'],jo) not in indexed:missing.append(e['evidence_id']);continue
        if (e['source_law'],e['source_jo'])==(e['target_law'],jo):continue
        pair=(e['source_law'],e['source_jo'],e['target_law'],jo);pairs.add(pair)
        incident[e['source_law']]+=1;incident[e['target_law']]+=1
        if e['source_law']!=e['target_law']:cross.append(e)
    cases=[]
    for law,jo,title,description in p['cases']:
        from core.fsc_collection import norm
        law=next((d['name'] for d in docs if norm(d['name'])==norm(law)),law)
        article_for(bundle,law,'제'+jo+'조')
        result=analyze_focus(law,'제'+jo+'조',g)
        useful=[r for r in result['rows'] if r['neighbor_kind']=='article' and r['neighbor_law']!=law and (r['neighbor_law'],r['neighbor_jo']) in indexed]
        cases.append(dict(law=law,jo=jo,title=title,description=description,
            connected_articles=len({(r['neighbor_law'],r['neighbor_jo']) for r in useful}),
            evidence_ids=list(dict.fromkeys(r['evidence_id'] for r in useful)),
            forward=sum(r['direction']=='forward' for r in useful),reverse=sum(r['direction']=='reverse' for r in useful),
            available=bool(useful)))
    # This is a release gate for a demonstrable task, not a numerical usefulness rating.
    eligible=sum(c['available'] for c in cases)>=2 and len({(e['source_law'],e['target_law']) for e in cross})>=2
    unindexed=[dict(name=d['name'],status=d.get('analysis_error','미분석'),url=d['source_url']) for d in docs if not d['articles']]
    return dict(domain=domain,title=p['title'],purpose=p['purpose'],decision='limited-release' if eligible else 'hold',
        decision_basis='2개 이상의 실무 질문에서 서로 다른 문서의 수집 조문과 인용 원문을 확인할 수 있어야 공개합니다. 사용성·개정 필요성의 정량 점수는 아닙니다.',
        cases=cases,documents=len(docs),indexed_documents=sum(bool(d['articles']) for d in docs),
        articles=sum(len(d['articles']) for d in docs),unique_article_connections=len(pairs),
        cross_document_evidence=len(cross),cross_document_pairs=len({(e['source_law'],e['target_law']) for e in cross}),
        external_evidence=len(g['external_references']),unresolved=len(g['citation_issues']),
        target_article_unavailable=len(missing),unindexed=unindexed,
        isolated_documents=[d['name'] for d in docs if d['articles'] and not incident[d['name']]],
        limitations=p['limitations'],companion_sources=p['companion_sources'],
        unavailable_selected_rules=bundle['source']['inventory'].get('unavailable_selected_rules',[]))

def report(bundle):
    p=PROFILES[bundle['graph']['domain']]
    return {**shared.report(bundle,domain=bundle['graph']['domain'],sectors=p['sectors']),'assessment':assessment(bundle)}
