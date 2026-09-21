"""Traceable rows from the official special-cases annex, not inferred citation edges."""
from datetime import datetime
import hashlib
import re
from core.citation_scope import parse_scope
from core.fsc_collection import CollectionError, norm, ymd
from core.state_property_collection import SPECIAL

TYPES = {'fee':'사용료등 감면', 'long_term':'장기 사용허가·대부', 'transfer':'양여'}


def parse_annex(document, as_of):
    as_of = ymd(as_of)
    annexes = [a for a in document['annexes'] if '국유재산특례' in a['title'] and '제4조' in a['title']]
    if document['name'] != SPECIAL or len(annexes) != 1:
        raise CollectionError('special-annex-identity-mismatch')
    annex = annexes[0]; text = annex['text']
    if not all(word in text for word in ('근거 법률', '특례유형', '존속기한')):
        raise CollectionError('special-annex-header-mismatch')
    rows=[]; current=None; offset=0
    for line in text.splitlines(keepends=True):
        if '│' in line:
            cells=line.rstrip('\r\n').split('│')[1:-1]
            if len(cells)!=4: raise CollectionError('special-annex-column-count')
            cells=[x.strip() for x in cells]
            if cells[0].isdigit():
                if current: rows.append(current)
                current=dict(number=int(cells[0]), columns=[[],[],[]], source_start=offset,source_end=offset+len(line))
            elif cells[0] and norm(cells[0]) not in ('연','번','연번'):
                raise CollectionError('special-annex-unknown-row-number')
            if current and (cells[0].isdigit() or not cells[0]):
                for column,value in zip(current['columns'],cells[1:]):
                    if value:column.append(value)
                current['source_end']=offset+len(line)
        offset+=len(line)
    if current:rows.append(current)
    if not rows or [r['number'] for r in rows]!=list(range(1,rows[-1]['number']+1)):
        raise CollectionError('special-annex-row-sequence')
    for row in rows:
        legal,type_text,deadline_text=[' '.join(c) for c in row.pop('columns')]
        row.update(legal_text=legal,type_text=type_text,deadline_text=deadline_text,
                   raw=text[row['source_start']:row['source_end']],
                   law='',references=[],status='needs-review',reason='근거 법률·조문 형식 확인 필요',
                   source_law=SPECIAL,source_ref=f"별표 연번 {row['number']}",
                   source_url=document['source_url'],annex_urls=annex['urls'],
                   source_effective=document['effective'])
        row['id']='property-special-'+hashlib.sha256((document['edition_key']+'|'+str(row['number'])).encode()).hexdigest()[:16]
        compact=norm(type_text)
        row['types']=[key for key,phrase in [('fee','사용료등의감면'),('long_term','장기사용허가등'),('transfer','양여')] if phrase in compact]
        if not row['types']:raise CollectionError('special-annex-unrecognized-type')
        date_match=re.fullmatch(r'\s*(\d{4})\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})\s*\.?\s*',deadline_text)
        if date_match:
            try: deadline=datetime(*map(int,date_match.groups())).strftime('%Y%m%d')
            except ValueError: raise CollectionError('special-annex-invalid-deadline') from None
            row.update(deadline=deadline,deadline_status='elapsed' if deadline<as_of else 'within_date')
        elif not deadline_text or deadline_text in ('-', '―', '—'):
            row.update(deadline='',deadline_status='not_stated')
        else:raise CollectionError('special-annex-unrecognized-deadline')
        # Historical supplementary provisions must never resolve to a present main article.
        if '부칙' in norm(legal):
            row.update(status='historical-supplement',reason='특정 개정법 부칙 · 해당 역사 판본 별도 확인 필요')
            continue
        match=re.fullmatch(r'\s*「([^」]+)」\s*(.+)',legal)
        if match:
            row['law']=match[1]
            reference=re.sub(r'\s+','',match[2])
            if '(' in reference:
                reference, condition = reference.split('(',1)
                row['condition']='('+condition
            scopes=parse_scope(reference)
            row['reference_text']=reference
            if scopes.scopes and not scopes.review_reason:
                row['references']=list(dict.fromkeys(s.start.label for s in scopes.scopes))
                row['ranges']=[dict(start=s.start.label,end=s.end.label,axis=s.axis) for s in scopes.scopes]
                row.update(status='pending-collection',reason='근거 법령 판본과 조문 대조 대기')
    return dict(schema=1,kind='special-annex-register',as_of=as_of,source_law=SPECIAL,
                source_effective=document['effective'],source_version=document['version_id'],
                source_url=document['source_url'],annex_ref=annex['ref'],annex_title=annex['title'],
                annex_urls=annex['urls'],text=text,sha256=hashlib.sha256(text.encode()).hexdigest(),
                rows=rows,types=TYPES,
                note='공식 별표의 등재 관계입니다. 직접 인용 관계·특례 적용 판정과 구분합니다. '
                     '기한 표시는 수집 기준일과 별표상 날짜의 비교이며, 개별 적용요건·부칙·경과조치를 대신 판단하지 않습니다.')


def resolve_rows(register, documents):
    from core.citation_scope import Provision,scope_relation
    byname={norm(d['name']):d for d in documents}
    for row in register['rows']:
        if row['status']!='pending-collection':continue
        doc=byname.get(norm(row['law']))
        if not doc:
            row.update(status='not-collected',reason='별표의 근거 법률과 일치하는 현행 본문 미수집')
            continue
        row.update(law=doc['name'],law_url=doc['source_url'],law_effective=doc['effective'])
        parsed=parse_scope(row['reference_text'])
        articles=[a for a in doc['articles'] if any(scope_relation(s,Provision(a['jo'])) for s in parsed.scopes)]
        # Every recorded start article must exist, including separately enumerated articles.
        expected={endpoint.jo for s in parsed.scopes for endpoint in (s.start,s.end)}
        present={a['jo'] for a in articles}
        if not expected.issubset(present):
            row.update(status='article-unavailable',reason='수집 현행본에서 별표의 근거 조문 일부를 찾지 못함')
        else:
            row.update(status='matched',reason='별표 근거 법률명·조 번호 대조 완료 · 항·호 적용요건은 원문 확인')
        row['article_numbers']=sorted(present)
    return register


def validate_register(register, source):
    doc=next(d for d in source['laws'] if d['name']==SPECIAL)
    fresh=resolve_rows(parse_annex(doc,source['built_at']),source['laws'])
    if register['sha256']!=fresh['sha256'] or register['source_version']!=doc['version_id']:
        raise ValueError('특례 별표 판본이 수집 법령과 다릅니다.')
    if len(register['rows'])!=len(fresh['rows']):raise ValueError('특례 별표 행 누락')
    for row,original in zip(register['rows'],fresh['rows']):
        for key in ('id','number','raw','legal_text','type_text','types','deadline','deadline_status','source_start','source_end',
                    'status','law','references','reference_text','article_numbers','condition','law_url','law_effective'):
            if row.get(key)!=original.get(key):raise ValueError('특례 별표의 원문 근거가 일치하지 않습니다.')
    return register
