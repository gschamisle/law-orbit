"""Page-bounded PDF cells and explicit, uniquely resolved document locations.

Cells never borrow a law name or a number from adjacent cells. Locations describe
the PDF's real structure, and are not fabricated statutory article numbers.
"""
from collections import defaultdict
import re

from core.fsc_collection import norm
from core.ftc_text_citations import normalized_quotes
from core.procurement_pdf import (ALLOWED, CHAPTER, SECTION, ITEM, BODY_SIZE_SECTIONS,
                                 digest)

LIMITATION = ('일반 문단·별표 문단·표의 개별 셀에서 명시한 인용과 목적지가 확인된 내부 참조를 분석했습니다. '
    '표의 열·행을 합쳐 적용조건을 추론하거나 점수·금액·산식을 판정하지 않습니다. '
    '부칙·서식, 여러 쪽·셀에 걸친 인용, 모호한 상대 참조는 미분석 또는 확인 필요로 남깁니다.')
CH = re.compile(r'제\s*(\d+)\s*장(?:\s*의\s*(\d+))?')
SEC = re.compile(r'제\s*(\d+)\s*절')
ANN = re.compile(r'별\s*표\s*(\d+(?:\s*[-의]\s*\d+)?)')
MARKER = re.compile(r'제\s*\d+\s*장(?:\s*의\s*\d+)?|제\s*\d+\s*절|[<\[【]\s*별\s*표\s*\d+(?:\s*[-의]\s*\d+)?\s*[>\]】]')


def chapter_id(text):
    m=CH.search(text)
    return m[1]+('의'+m[2] if m[2] else '') if m else ''


def location_key(chapter='',annex='',section='',item=''):
    return '|'.join((chapter,annex,section,item))


def extract_structured_pdf(path, record):
    import pdfplumber
    if ALLOWED.get(record['document_id'])!=record['name']:raise ValueError('Unapproved PDF source')
    raw=path.read_bytes()
    if not raw.startswith(b'%PDF-'):raise ValueError('Not a PDF')
    parts=[];units=[];pages=[];anchors=[];cells=[];offset=0
    chapter=annex=section='';chapter_title=section_title='';items=['','','','']
    excluded=False
    def anchor(kind,key,label,start,page):
        anchors.append(dict(kind=kind,key=key,label=label,start=start,page=page))
    with pdfplumber.open(path) as pdf:
        for number,original in enumerate(pdf.pages,1):
            page=original.dedupe_chars(tolerance=2,extra_attrs=())
            plain=page.extract_text(x_tolerance=2) or ''
            printed=re.search(r'(?m)^-\s*(\d+)\s*-$',plain)
            printed=printed[1] if printed else ''
            contents=number<=2 or '순서' in norm(plain[:160])
            tables=page.find_tables();events=[]
            for line in page.extract_text_lines(x_tolerance=2,return_chars=True):
                body=line['text'].strip()
                if not body or re.fullmatch(r'-\s*\d+\s*-',body):continue
                if any(line['top']<t.bbox[3] and line['bottom']>t.bbox[1] and line['x0']<t.bbox[2] and line['x1']>t.bbox[0] for t in tables):continue
                size=min((c['size'] for c in line['chars'] if c['text'].strip()),default=0)
                events.append(dict(top=line['top'],x=line['x0'],text=body,size=size,kind='line'))
            for ti,table in enumerate(tables,1):
                seen=set()
                for ri,row in enumerate(table.rows,1):
                    for ci,box in enumerate(row.cells,1):
                        if box is None or box in seen:continue
                        seen.add(box)
                        # Fully contained characters only: never absorb the adjacent cell.
                        cell=page.within_bbox(box);body=cell.extract_text(x_tolerance=2) or ''
                        if not body.strip():continue
                        events.append(dict(top=box[1],x=box[0],text=body.strip(),size=0,kind='cell',
                            table=ti,row=ri,column=ci,bbox=[round(v,3) for v in box]))
            events.sort(key=lambda e:(e['top'],e['x']))
            prefix=f'\n\n[PDF {number}쪽'+(f' · 인쇄 {printed}쪽' if printed else '')+']\n'
            parts.append(prefix);offset+=len(prefix);page_start=offset
            pending=[];begin=offset;context=None
            def flush():
                nonlocal pending
                body='\n'.join(pending)
                if body.strip():units.append(dict(start=begin,end=begin+len(body),text=body,page=number,
                    printed_page=printed,**context))
                pending=[]
            for e in events:
                body=e['text'];is_line=e['kind']=='line'
                is_ch=not contents and is_line and CHAPTER.match(body) and e['size']>=18
                # Official annex captions give the chapter even for repeated numbers.
                annex_header=not contents and is_line and body.startswith('■') and ANN.search(body)
                bare_annex=not contents and is_line and e['top']<140 and re.fullmatch(r'[<\[【]\s*별\s*표\s*\d+(?:\s*[-의]\s*\d+)?\s*[>\]】]',body)
                is_ann=annex_header or bare_annex
                is_sec=not contents and is_line and SECTION.match(body) and (e['size']>=14.8 or norm(body) in BODY_SIZE_SECTIONS)
                item_match=ITEM.match(body) if is_line and not contents else None
                boundary=bool(is_ch or is_ann or is_sec or item_match or not is_line or body.startswith('■') or re.match(r'^부\s*칙(?:\s|$|\()',body))
                if boundary:flush()
                if is_ch:
                    chapter=chapter_id(body);chapter_title=body;annex=section=section_title='';items=['','','',''];excluded=False
                    anchor('chapter',location_key(chapter),body,offset,number)
                elif is_ann:
                    if annex_header and chapter_id(body):chapter=chapter_id(body)
                    annex='별표'+norm(ANN.search(body)[1]);section=section_title='';items=['','','',''];excluded=False
                    anchor('annex',location_key(chapter,annex),body,offset,number)
                elif is_sec:
                    section=SEC.match(body)[1];section_title=body;items=['','','','']
                    if not excluded:anchor('section',location_key(chapter,annex,section),body,offset,number)
                elif item_match:
                    label=item_match[0].strip();level=0 if re.match(r'^\d+(?:-\d+)*\.',label) else 1 if '.' in label else 2 if label[0].isdigit() else 3
                    items[level]=label
                    for n in range(level+1,4):items[n]=''
                    if level==0 and not excluded:anchor('item',location_key(chapter,annex,section,label[:-1]),body,offset,number)
                if not contents and is_line and (re.match(r'^부\s*칙(?:\s|$|\()',body) or (body.startswith('■') and not is_ann) or re.match(r'^[<\[【]\s*별\s*지',body)):
                    excluded=True
                eligible=bool(chapter and not contents and not excluded)
                context=dict(chapter=chapter_title,section=section_title,item=' / '.join(v for v in items if v),
                    chapter_id=chapter,annex=annex,section_id=section,
                    locator=' / '.join(v for v in (chapter_title,annex,section_title,*items) if v),
                    layer='table-cell' if not is_line else 'annex-prose' if annex else 'prose',heading=bool(is_ch or is_sec or is_ann))
                if not is_line:
                    context['locator']+=f' / 표 {e["table"]} · {e["row"]}행 {e["column"]}열'
                    marker=f'[표 {e["table"]} · {e["row"]}행 {e["column"]}열 · 셀 단위 원문]\n'
                    parts.append(marker);offset+=len(marker)
                    cell_record=dict(page=number,start=offset,end=offset+len(body),table=e['table'],row=e['row'],column=e['column'],bbox=e['bbox'],analyzed=eligible)
                    cells.append(cell_record)
                    if eligible:units.append(dict(start=offset,end=offset+len(body),text=body,page=number,printed_page=printed,**context,cell=cell_record))
                elif eligible:
                    if not pending:begin=offset
                    pending.append(body)
                parts.append(body+'\n');offset+=len(body)+1
                if not is_line:pending=[]
            flush()
            page_units=[u for u in units if u['page']==number]
            pages.append(dict(page=number,printed_page=printed,start=page_start,end=offset,tables=len(tables),
                status='contents' if contents else 'excluded' if excluded else 'prose',analyzed_units=len(page_units),
                table_cells=sum(u['layer']=='table-cell' for u in page_units)))
            if number%100==0:print(f'{record["document_id"]}: structured PDF {number}/{len(pdf.pages)}',flush=True)
    text=''.join(parts)
    for u in units:
        if text[u['start']:u['end']]!=u['text']:raise ValueError('Structured PDF source offset mismatch')
    # A real heading is the endpoint; its body runs until the next sibling/ancestor.
    rank={'chapter':0,'annex':1,'section':2,'item':3}
    for i,a in enumerate(anchors):
        a['id']=digest(record['uid']+'|'+a['key']+'|'+str(a['start']))[:20]
        a['end']=next((b['start'] for b in anchors[i+1:] if rank[b['kind']]<=rank[a['kind']]),len(text))
    return dict(schema=2,kind='procurement-pdf-prose',text=text,units=units,pages=pages,anchors=anchors,cells=cells,
        file_sha256=digest(raw),text_sha256=digest(text),bytes=len(raw),record=record,
        pdf_url=record['attachments'][0]['첨부파일링크'].replace('http:','https:'),limitation=LIMITATION,
        extraction=dict(engine='pdfplumber',version=pdfplumber.__version__,char_dedupe_tolerance=2,
            tables='separate fully-contained cells',excluded='contents,forms,supplements',page_boundary_references='not-joined'))


def internal_links(result):
    """Only explicit document-scoped references with a unique real heading match."""
    index=defaultdict(list)
    for a in result['anchors']:index[a['key']].append(a)
    headings=[(a['start'],result['text'].find('\n',a['start'])) for a in result['anchors']]
    rows=[];issues=[]
    for unit in result['units']:
        if unit.get('heading'):continue
        body=normalized_quotes(unit['text']).translate(str.maketrans({'｢':'「','｣':'」'}));markers=list(MARKER.finditer(body));i=0
        # Do not lose an external owner across "시행령 제6장 및 제9장", or
        # interpret "일반조건 제7절" as this chapter's section 7.
        owner_uncertain=bool(re.search(r'(?:법|법률|시행령|시행규칙|특례규정|일반조건|특수조건)\s*제\s*\d+\s*[장절]',body))
        other_alias='낙찰자결정기준' if result['record']['document_id']=='29508' else '계약집행기준'
        owner_uncertain=owner_uncertain or bool(re.search(re.escape(other_alias)+r'\s*[」”"]?\s*제\s*\d+\s*[장절]',norm(body)))
        owner_uncertain=owner_uncertain or any(norm(m[1])!=norm(result['record']['name']) for m in re.finditer(r'「([^」]+)」\s*(?=제\s*\d+\s*[장절]|[<\[【]\s*별\s*표)',body))
        while i<len(markers):
            first=markers[i];i+=1;start=first.start();end=first.end()
            if any(a<=unit['start']+start<=b for a,b in headings):continue
            ch=unit['chapter_id'];ann=unit['annex'];sec=unit['section_id'];item=''
            def apply(marker):
                nonlocal ch,ann,sec
                if CH.fullmatch(marker):ch=chapter_id(marker);ann=sec='';return 'chapter'
                if SEC.fullmatch(marker):sec=SEC.fullmatch(marker)[1];return 'section'
                ann='별표'+norm(ANN.search(marker)[1]);sec='';return 'annex'
            kind=apply(first[0]);key=location_key(ch,ann,sec)
            # A preceding named external law owns its chapter/annex. Do not turn
            # it into a same-document reference (e.g. 시행령 [별표 8]).
            before=body[max(0,start-130):start]
            owner=re.search(r'[「｢]([^」｣]+)[」｣]\s*$',before)
            if (owner and norm(owner[1])!=norm(result['record']['name'])) or re.search(r'(?:시행령|시행규칙|같은\s*법)\s*$',before):continue
            while i<len(markers):
                following=markers[i];gap=norm(body[end:following.start()]).strip('「」“”"\'<>[]')
                titles=[norm(re.sub(r'^제\s*\d+\s*(?:장(?:\s*의\s*\d+)?|절)\s*','',a['label'])) for a in index.get(key,[])]
                allowed=not gap or gap in titles
                candidate_kind='chapter' if CH.fullmatch(following[0]) else 'section' if SEC.fullmatch(following[0]) else 'annex'
                if not allowed or candidate_kind=='chapter' or (kind=='section' and candidate_kind!='annex') or (kind=='annex' and candidate_kind!='section'):break
                kind=apply(following[0]);key=location_key(ch,ann,sec);end=following.end();i+=1
            # Explicit numbered item following a section: 제9절 “11”, 제5절 3.
            if kind=='section':
                item_match=re.match(r'\s*(?:[“"「](\d+(?:-\d+)*)[”"」]|(\d+(?:-\d+)*)\.(?=\s|$))',body[end:])
                if item_match:item=item_match[1] or item_match[2];end+=item_match.end();key=location_key(ch,ann,sec,item)
            # Don't degrade an unsupported deeper reference to a broad ancestor.
            rest=body[end:end+18]
            unsupported=bool(re.match(r'\s*(?:부터|내지|[-~～]|[“"「]\d|[“"「][가나다라마바사아자차카타파하](?=[”"」.\-)]))',rest) or re.search(r'(?:부터|내지|[-~～])\s*$',before))
            candidates=index.get(key,[])
            a,b=unit['start']+start,unit['start']+end;raw=result['text'][a:b]
            mismatch=False
            if kind=='chapter' and len(candidates)==1:
                description=re.match(r'\s*[「“"]?([가-힣·․\s]+?(?:기준|요령|조건))',body[end:end+65])
                if description and not description[1].startswith(('에','의','을','를','및','또는')):
                    title=norm(CH.sub('',candidates[0]['label'],count=1));quoted=norm(description[1])
                    mismatch=not(title.startswith(quoted) or quoted.startswith(title))
            if unsupported or owner_uncertain or mismatch or len(candidates)!=1:
                issues.append(dict(source_law=result['record']['name'],source_ref=unit['locator']+f' · PDF {unit["page"]}쪽',
                    source_start=a,source_end=b,raw=raw,reason='내부 참조: 인용한 번호와 제목의 대조 필요' if mismatch else '내부 참조: 다른 법령·기준의 범위 확인 필요' if owner_uncertain else '내부 참조: 범위·세부항목 해석 필요' if unsupported else '내부 참조: 목적지 미확인 또는 중복'))
                continue
            target=candidates[0]
            if target['start']==a:continue # A heading does not cite itself.
            if target['start']<=a<target['end'] and target['kind']=='item':continue
            rows.append(dict(id=digest(result['record']['uid']+str(a)+str(b)+target['id'])[:20],
                source_page=unit['page'],source_start=a,source_end=b,source_ref=unit['locator'],raw=raw,
                context=body,target_id=target['id'],target_key=key,target_page=target['page'],target_label=target['label']))
    return rows,issues
