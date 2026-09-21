"""Compact foreign-exchange constellation. Geometry never adds citation evidence."""
from copy import deepcopy
import math
from core.forex_collection import LAW, REGULATION
COLORS={'common':'#a8baff','payment':'#68dfc4','capital':'#c09cff','market':'#f3be78','reporting':'#ef96bb'}
def layout(data,graph):
    if data.get('mode')!='overview':return data
    result=deepcopy(data);catalog={d['name']:d for d in graph['catalog']}
    anchors={LAW:(-130,-85,-15),LAW+' 시행령':(-130,85,15),REGULATION:(60,0,0),
             '외국환거래업무 취급세칙':(220,-130,35),'외국환거래업무 취급절차':(245,135,-20)}
    others=sorted(n['id'] for n in result['nodes'] if n['id'] not in anchors)
    result['dust']=[]
    for n in result['nodes']:
        name=n['id'];doc=catalog[name]
        if name in anchors:x,y,z=anchors[name]
        else:
            i=others.index(name);theta=i*math.tau/max(len(others),1)+.15
            x,y,z=math.cos(theta)*450,math.sin(theta)*350,math.sin(theta*2)*65
        n.update(x=x,y=y,z=z,primary=name in (LAW,REGULATION),category='forex',label=doc['display_name'],
                 full_name=name,title=doc['managing_authority']+' · '+doc['kind']+' · 시행 '+doc['effective'])
        articles=graph.get('article_catalog',{}).get(name,[])
        for i,a in enumerate(articles):
            theta=i*math.pi*(3-math.sqrt(5));radius=22+55*math.sqrt((i+.5)/max(len(articles),1))
            tags=a.get('sectors') or ['common']
            result['dust'].append(dict(x=x+math.cos(theta)*radius,y=y+math.sin(theta)*radius*.8,
                z=z+math.sin(i*1.71)*30,c=COLORS[tags[0]],law=doc['display_name'],law_id=name,
                jo='제'+a['jo'].replace('의','조의')+('' if '의' in a['jo'] else '조'),sectors=tags))
    result.update(links=deepcopy(result['all_links']),layout='forex-disc',camera=dict(rx=-.12,ry=.12),
                  overview_note='큰 별은 법령·규정, 작은 점은 수집한 조문입니다. 작은 점의 색은 업무 태그이며 복수 태그 중 첫 분류를 표시합니다. 배치는 법적 위계를 뜻하지 않습니다.')
    return result
