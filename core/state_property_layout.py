"""A disc with two anchors for national property; geometry never changes evidence."""
from copy import deepcopy
import hashlib
import math
from core.law_map import family
from core.state_property_collection import PROPERTY, SPECIAL


def _unit(name, salt=0):
    return int(hashlib.sha256(f'{salt}:{name}'.encode()).hexdigest()[:8],16)/0xffffffff


def layout(data, graph):
    if data.get('mode')!='overview':return data
    result=deepcopy(data)
    catalog={d['name']:d for d in graph['catalog']}
    families=sorted({family(n['id']) for n in data['nodes']
                     if family(n['id']) not in (PROPERTY,SPECIAL)
                     and 'administration' not in catalog.get(n['id'],{}).get('sectors',[])},key=_unit)
    family_positions={}
    for i,name in enumerate(families):
        arm=i%3;t=(i//3+.5)/max(math.ceil(len(families)/3),1)
        angle=arm*math.tau/3+t*2.8+(_unit(name,1)-.5)*.35
        radius=210+260*t
        family_positions[name]=(math.cos(angle)*radius,math.sin(angle)*radius*.76,(_unit(name,2)-.5)*95)
    rules=sorted(n['id'] for n in data['nodes'] if 'administration' in catalog.get(n['id'],{}).get('sectors',[]))
    old={n['id']:(n['x'],n['y'],n['z']) for n in data['nodes']};positions={}
    for n in result['nodes']:
        name=n['id'];fam=family(name);tier=n.get('tier',0)
        if fam in (PROPERTY,SPECIAL):
            base=(-100,-48,-10) if fam==PROPERTY else (115,65,15)
            angle=(math.pi*.85 if fam==PROPERTY else -.2)+tier*1.4
            radius=0 if not tier else 67+tier*19
            x,y,z=base[0]+math.cos(angle)*radius,base[1]+math.sin(angle)*radius,base[2]+tier*12
            n['primary']=name in (PROPERTY,SPECIAL)
        elif name in rules:
            angle=rules.index(name)*math.tau/max(len(rules),1)+.2
            radius=150+(_unit(name)-.5)*42
            x,y,z=math.cos(angle)*radius,math.sin(angle)*radius*.83,(_unit(name,2)-.5)*70
        else:
            x,y,z=family_positions[fam]
            x+=tier*22;y+=tier*17;z+=tier*16
        n.update(x=round(x,2),y=round(y,2),z=round(z,2))
        positions[name]=(n['x'],n['y'],n['z'])
    # Retain exactly the existing article points, remapping offsets into the disc.
    for p in result.get('dust',[]):
        old_center=old[p['law_id']];new_center=positions[p['law_id']]
        for axis,key in enumerate(('x','y','z')):
            p[key]=round(new_center[axis]+(p[key]-old_center[axis])*(.45 if axis==2 else .63),2)
    both_anchors=all(name in positions for name in (PROPERTY,SPECIAL))
    result.update(layout='national-property-disc',camera=dict(rx=-.12,ry=.12),
                  overview_note=('중앙은 두 기본 법령, 주변은 관리 지침과 특례 근거 법률입니다. ' if both_anchors else '선택 분야의 법령·지침입니다. ')
                  +'배치는 탐색을 위한 것으로 법적 위계를 뜻하지 않습니다.')
    return result
