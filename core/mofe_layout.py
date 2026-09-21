"""Display only evidenced document links, including statute/decree/rule links."""
from copy import deepcopy

def layout(data,graph):
    result=deepcopy(data)
    result['work_domain_label']={'public_institutions':'PUBLIC INSTITUTIONS','customs':'CUSTOMS / CLEARANCE','treasury':'TREASURY / ACCOUNTING'}[graph['domain']]
    if data.get('mode')!='overview':return result
    catalog={d['name']:d for d in graph['catalog']}
    connected={name for e in result['all_links'] for name in (e['a'],e['b'])}
    result['nodes']=[n for n in result['nodes'] if n['id'] in connected]
    for n in result['nodes']:
        d=catalog[n['id']]
        n.update(category=graph['domain'],label=d['display_name'],full_name=d['name'],
                 title=d['managing_authority']+' · '+d['kind']+' · 시행 '+d['effective'])
    result['dust']=[a for a in result['dust'] if a['law_id'] in connected]
    tags={(name,a['jo']):a['sectors'] for name,aa in graph['article_catalog'].items() for a in aa}
    from core.citation_scope import parse_target
    for a in result['dust']:
        try:a['sectors']=tags.get((a['law_id'],parse_target(a['jo']).jo),[])
        except ValueError:a['sectors']=[]
    result.update(links=deepcopy(result['all_links']),
        overview_note='문서 사이에 수집된 인용 근거가 있는 법령·규정을 표시합니다. 같은 법의 시행령·시행규칙 연결도 포함합니다. 작은 점은 인용 근거가 있는 조문 일부이며, 전체 수집 본문은 법령 목록에서 읽을 수 있습니다. 배치는 법적 위계를 뜻하지 않습니다.')
    return result
