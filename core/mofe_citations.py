"""Opt-in explicit owners; unresolved quotations are a ledger, never guessed links."""
import re
from core.fsc_administrative import aliases_from,QUOTED
from core.fsc_collection import norm

DECLARATION=r'\s*\(이하\s*["“]([^"”]+)["”](?:\s*이?\s*라\s*(?:한다|함))?\s*\)'

def prepare_aliases(document):
    document['citation_policy']='mofe-explicit'
    bodies=[a['text'] for a in document['articles']]
    text='\n'.join(bodies)
    aliases,evidence=aliases_from(text)
    # Also accept the explicit compact form 「법률명」(이하 "약칭").
    for q in QUOTED.finditer(text):
        m=re.match(DECLARATION,text[q.end():])
        if m:
            alias=norm(m[1]);target=q[1]
            if alias not in aliases:aliases[alias]=target
            evidence.append(dict(alias=alias,target_law=target,raw=text[q.start():q.end()+m.end()],start=q.start(),end=q.end()+m.end()))
    conflicts={e['alias'] for e in evidence if len({norm(v['target_law']) for v in evidence if v['alias']==e['alias']})>1}
    for alias in conflicts:aliases.pop(alias,None)
    name=document['name']
    if document['provider']=='eflaw' and name.endswith((' 시행령',' 시행규칙')):
        base=re.sub(r' 시행(?:령|규칙)$','',name)
        aliases.setdefault('법',base);aliases.setdefault('영',base+' 시행령');aliases.setdefault('규칙',base+' 시행규칙')
    document['aliases']=aliases;document['alias_evidence']=evidence

def embedded_quote(text,start):
    return any(m.start()<start<m.end() for m in re.finditer(r'["“][^"”\n]*["”]',text))
