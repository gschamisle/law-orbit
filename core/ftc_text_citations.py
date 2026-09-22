"""Explicit citations in unnumbered FTC guidance, with real source offsets.

Reuse the provision adapter without pretending a Roman section is a legal article.
Text evidence is separate from the numbered graph and never becomes a fake jo.
"""
from copy import deepcopy
import hashlib,re
from urllib.parse import quote
from core.fsc_administrative import adapter,body_text,BOUNDARY
from core.fsc_collection import norm
from core.mofe_citations import prepare_aliases
from core.citation_scope import parse_target

SECTION=re.compile(r'(?m)^[ \t]*([ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫ]+|[IVX]+)\.[ \t]*([^\n]+)')

def main_text(document):
    text=body_text(document.get('raw_body_blocks',[]));cut=BOUNDARY.search(text)
    return text[:cut.start()] if cut else text

def normalized_quotes(text):
    # Length preserving: all evidence offsets continue to refer to the original.
    return text.translate(str.maketrans({'‘':'“','’':'”',"'":'"'}))

def canonical_documents(corpus):
    names={norm(d['name']):d for d in corpus};aliases={}
    for d in corpus:
        for label in [d.get('short_name','')]+d.get('citation_names',[]):
            if label:aliases.setdefault(norm(label),{})[d['name']]=d
    for label,matches in aliases.items():
        if len(matches)==1:names.setdefault(label,next(iter(matches.values())))
    return names

def ftc_adapter(document,article,corpus):
    original=article['text'];part={**article,'text':normalized_quotes(original),'citation_issues':[]}
    rows=adapter(document,part,corpus)
    names={k:d['name'] for k,d in canonical_documents(corpus).items()}
    for row in rows:
        row['raw']=original[row['start']:row['end']]
        row['target_name']=names.get(norm(row['target_name']),row['target_name'])
    article['citation_issues']=[{**i,'raw':original[i['start']:i['end']]} for i in part['citation_issues']]
    return rows

def prepare_text_aliases(document):
    text=main_text(document) if document['provider']=='admrul' else '\n'.join(a['text'] for a in document['articles'])
    scan=normalized_quotes(text);temporary={**document,'articles':[{'text':scan}]}
    prepare_aliases(temporary)
    document['aliases']=temporary['aliases'];document['alias_evidence']=temporary['alias_evidence']
    # Derivative aliases are accepted only with an explicit declaration in this text.
    law=document['aliases'].get('법')
    if law:
        for m in re.finditer(r'(?:같은\s*)?법\s*(시행령|시행규칙)\s*\(이하\s*["“]([^"”]+)["”]\s*(?:이?라\s*한다|라\s*함)\)',scan):
            target=law+' '+m[1];alias=norm(m[2])
            document['aliases'][alias]=target
            document['alias_evidence'].append(dict(alias=alias,target_law=target,raw=text[m.start():m.end()],start=m.start(),end=m.end()))

def collect_text_citations(source):
    docs=source['laws']+source['administrative_rules'];by_name=canonical_documents(docs)
    rows=[];issues=[]
    for d in docs:
        if d['provider']!='admrul' or d.get('articles'):continue
        if d.get('analysis_error','').startswith('공식 조문번호 중복'):continue
        text=main_text(d);scan=normalized_quotes(text)
        headings=list(SECTION.finditer(text))
        # Section boundaries keep relative references from borrowing another section's owner.
        starts=sorted(set([0]+[h.start() for h in headings]+[len(text)]))
        for start,end in zip(starts,starts[1:]):
            raw=text[start:end];part={'text':scan[start:end],'jo':''}
            locator=next((h[0].strip() for h in reversed(headings) if h.start()<=start),'본문')
            for c in adapter(deepcopy(d),part,docs):
                dest=by_name.get(norm(c['target_name']));kind=c.get('kind','article')
                if kind=='law' and not dest and not c['target_name'].endswith(('법','법률','시행령','시행규칙','규칙','고시','지침','기준','규정','요령')):continue
                a,b=start+c['start'],start+c['end'];owner=dest['name'] if dest else c['target_name']
                line_start=text.rfind('\n',0,a)+1;line_end=text.find('\n',b)
                if line_end<0:line_end=len(text)
                context=text[line_start:line_end]
                ident=hashlib.sha256(repr((d['uid'],a,b,owner,c['target_ref'])).encode()).hexdigest()[:20]
                rows.append(dict(evidence_id=ident,source_law=d['name'],source_jo='',source_ref=locator,
                    source_granularity='text',source_start=a,source_end=b,source_effective=d['effective'],source_url=d['source_url'],
                    target_law=owner,target_ref=c['target_ref'],target_kind=kind,
                    target_url=dest['source_url'] if dest else 'https://www.law.go.kr/법령/'+quote(owner,safe=''),
                    target_effective=dest['effective'] if dest else '',
                    target_status=('collected' if dest.get('articles') else 'collected-not-indexed') if dest else 'not-collected',
                    target_provision_status=c.get('target_provision_status',''),
                    raw=text[a:b],cite_raw=text[a:b],context=context,context_review=c.get('context_review',False),
                    reason='문단형 지침의 명시적 인용입니다. 문단 번호를 조문 번호로 변환하지 않았습니다.'))
            for i in part.get('citation_issues',[]):
                a,b=start+i['start'],start+i['end']
                issues.append(dict(source_law=d['name'],source_ref=locator,raw=text[a:b],reason=i['reason'],source_start=a,source_end=b))
        d['text_analysis']=dict(status='explicit-citations',references=sum(r['source_law']==d['name'] for r in rows),
                                issues=sum(i['source_law']==d['name'] for i in issues),internal_paragraph_references='not-analyzed')
        d['analysis_error']='문단 인용 분석 · 지침 내부 문단 간 참조는 미분석'
    return rows,issues

def validate_text_citations(source,rows):
    docs={d['name']:d for d in source['laws']+source['administrative_rules']}
    ids=set()
    for r in rows:
        d=docs[r['source_law']];text=main_text(d)
        if d['provider']!='admrul' or d['articles'] or r['source_jo'] or r['source_granularity']!='text':raise ValueError('Invalid text evidence source')
        if text[r['source_start']:r['source_end']]!=r['raw'] or r['evidence_id'] in ids:raise ValueError('Text evidence offset or identity mismatch')
        ids.add(r['evidence_id']);dest=docs.get(r['target_law'])
        if r['target_status']!='not-collected' and not dest:raise ValueError('Missing text citation target')
        if dest and r['target_kind']=='article' and parse_target(r['target_ref']).jo not in {a['jo'] for a in dest['articles']}:raise ValueError('Missing text citation article')

def reading_row(edge,direction):
    reverse=direction=='reverse';row=dict(edge)
    row.update(direction=direction,direction_label='역인용' if reverse else '인용',kind=edge['target_kind'],
        status='review' if edge.get('context_review') or edge['target_kind']=='law' else 'exact',
        precision='문단 인용 · 문맥 확인' if edge.get('context_review') else '문단 인용',
        neighbor_law=edge['source_law'] if reverse else edge['target_law'],
        neighbor_jo='' if reverse or edge['target_kind']!='article' else parse_target(edge['target_ref']).jo,
        neighbor_ref=edge['source_ref'] if reverse else edge['target_ref'],neighbor_kind='text' if reverse else edge['target_kind'],
        broad=edge['target_kind']=='law',external=edge['target_status']=='not-collected')
    return row
