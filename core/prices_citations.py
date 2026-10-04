"""Known full-title references in price guidance; no article or scope inference."""
import re
from core.fsc_collection import norm

CUE=re.compile(r'\s*(?:에서\s*정하는|에\s*따라|에\s*따른|에\s*의하여|에\s*의한)(?![가-힣A-Za-z])')


def bare_law_references(article,corpus,existing=()):
    text=article['text'];matches=[]
    # Only the official full name of one actual collected statute is eligible.
    grouped={}
    for doc in corpus:
        if doc.get('provider')=='eflaw':grouped.setdefault(norm(doc['name']),[]).append(doc['name'])
    titles=[v[0] for v in grouped.values() if len(set(v))==1]
    occupied=[(r['start'],r['end']) for r in existing]
    quoted=[(q.start(),q.end()) for q in re.finditer(r'[「“\"][^」”\"\n]*[」”\"]',text)]
    for title in sorted(titles,key=len,reverse=True):
        pattern=re.compile(r'(?<![가-힣A-Za-z0-9「“\"])'+r'\s*'.join(map(re.escape,norm(title))))
        for m in pattern.finditer(text):
            if not CUE.match(text,m.end()):continue
            if any(a<m.end() and m.start()<b for a,b in occupied+quoted):continue
            matches.append(dict(start=m.start(),end=m.end(),raw=m[0],target_name=title,
                                target_ref='법령·정의 참조',kind='law',context_review=False))
            occupied.append((m.start(),m.end()))
    return sorted(matches,key=lambda r:r['start'])
