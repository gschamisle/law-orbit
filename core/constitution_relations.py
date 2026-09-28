"""Explicit references and an independently validated editorial reading guide."""
import hashlib,re
from core.constitution_profile import CONSTITUTION,GUIDE
from core.fsc_collection import norm

def adapter(law,article,corpus):
    from core.fsc_administrative import adapter as shared
    scoped={**law,'aliases':{**law.get('aliases',{}),'헌법':CONSTITUTION,'대한민국헌법':CONSTITUTION}}
    if law['name']==CONSTITUTION:scoped['aliases']['이헌법']=CONSTITUTION
    rows=shared(scoped,article,corpus)
    for r in rows:
        if norm(r['target_name']) in ('헌법','대한민국헌법'):r['target_name']=CONSTITUTION
    text=article['text']
    # A whole-constitution mention never invents an article number.
    for m in re.finditer(r'(?<![가-힣A-Za-z])(?:대한민국\s*)?헌법(?=\s|[」｣ㆍ·,.()]|에|의|과|을|이|은)',text):
        if law['name']==CONSTITUTION or any(r['start']<=m.start()<r['end'] for r in rows):continue
        rows.append(dict(target_name=CONSTITUTION,target_ref='법령·정의 참조',raw=m[0],
                         start=m.start(),end=m.end(),kind='law',relation='law_reference'))
    return rows

def reading_guide(source):
    docs={d['name']:d for d in source['laws']}
    def endpoint(name,jo):
        d=docs[name];a=next(a for a in d['articles'] if a['jo']==jo)
        return dict(law=name,jo=jo,effective=a.get('effective') or d['effective'],url=d['source_url'],
                    text=a['text'],sha256=hashlib.sha256(a['text'].encode()).hexdigest())
    return [dict(kind='editorial-related-law',is_citation=False,title=title,reason=reason,
                 constitution=endpoint(CONSTITUTION,jo),related=endpoint(law,ref))
            for jo,title,law,ref,reason in GUIDE]

def validate_guide(value,source):
    if value!=reading_guide(source):raise ValueError('헌법 관련 법률 안내의 원문·판본·연결 근거 불일치')
