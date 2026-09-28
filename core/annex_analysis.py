"""Opt-in annex text evidence. Table cells never borrow a neighbouring owner.

Supported: API box tables verified against HWP text, HWP paragraphs, and HWPX
paragraphs/cells. Unverified layouts fail closed; images are not OCR'd. Offsets
refer to the stored analysis text, whose units retain extracted source text.
"""
from copy import deepcopy
import hashlib
from pathlib import Path
import re
import struct
import zipfile
import zlib
from xml.etree import ElementTree as ET

from core.fsc_administrative import adapter, aliases_from
from core.fsc_collection import norm
from core.hwp_reader import read_hwp_text, _hwp_records


def digest(data):
    return hashlib.sha256(data).hexdigest()


def compact(text):
    return re.sub(r'\s+', '', text)


def reference_spacing(text):
    # Only repair a split legal number (e.g. 제4 3조), never all word spaces.
    return re.sub(r'제\s*((?:\d\s*)+)(조|항|호)',
                  lambda m: '제'+compact(m[1])+m[2], text)


def box_cells(text):
    """Read horizontal bands of an API box table, retaining original fragments."""
    rows, band = [], []
    for line in text.splitlines():
        value = line.strip()
        if value.startswith(('┌', '├', '└')):
            if band:
                widths = {len(parts) for parts in band}
                if len(widths) != 1:
                    raise ValueError('한 행 안의 열 경계가 달라 표 구조를 확인할 수 없습니다.')
                rows.append([' '.join(parts[c].strip() for parts in band if parts[c].strip())
                             for c in range(len(band[0]))])
                band = []
        elif value.startswith('│') and value.endswith('│'):
            band.append(value[1:-1].split('│'))
    if band or not rows:
        raise ValueError('닫히지 않았거나 지원하지 않는 표입니다.')
    return rows


def hwp_table_shapes(path):
    """HWP 5.0 TABLE: uint32 flags followed by uint16 row/column counts.

    Hancom file format 5.0 revision 1.2, table object record (HWPTAG_TABLE).
    This is a guard against flattening unknown multi-cell tables, not a parser.
    """
    import olefile
    shapes=[]
    with olefile.OleFileIO(str(path)) as document:
        compressed=bool(document.openstream('FileHeader').read()[36]&1)
        for entry in document.listdir():
            if entry[0]!='BodyText': continue
            data=document.openstream(entry).read()
            for tag,payload in _hwp_records(zlib.decompress(data,-15) if compressed else data):
                if tag==77: shapes.append(struct.unpack_from('<HH',payload,4))
    return shapes


def hwpx_units(path):
    """Keep paragraph breaks, nested text tails, cell address and merged spans."""
    units = []
    local = lambda e: e.tag.rsplit('}', 1)[-1]
    def contents(e):
        if local(e) in ('lineBreak', 'br'): return '\n'+(e.tail or '')
        return (e.text or '')+''.join(contents(c) for c in e)+(e.tail or '')
    def visit(e, location, inside_cell=False):
        tag = local(e)
        if tag == 'tc':
            if any(local(c)=='tbl' for c in e.iter()):
                raise ValueError('중첩 표는 칸의 경계를 확정할 수 없어 분석하지 않습니다.')
            address = next((a.attrib for a in e.iter() if local(a)=='cellAddr'), {})
            span = next((a.attrib for a in e.iter() if local(a)=='cellSpan'), {})
            paras = [p for p in e.iter() if local(p)=='p']
            text = '\n'.join(''.join(contents(t) for t in p if local(t)=='run').strip() for p in paras)
            units.append(dict(locator=f'{location} · 행 {int(address.get("rowAddr",0))+1} 열 {int(address.get("colAddr",0))+1}',
                              raw_text=text, kind='cell', cell_address=address, cell_span=span))
            return
        if tag == 'p' and not any(local(c)=='tbl' for c in e.iter()):
            text = ''.join(contents(t) for t in e if local(t)=='run').strip()
            if text: units.append(dict(locator=location, raw_text=text, kind='paragraph'))
            return
        for c in e: visit(c, location, inside_cell)
    with zipfile.ZipFile(path) as archive:
        names = sorted(n for n in archive.namelist() if re.fullmatch(r'Contents/section\d+\.xml', n))
        if not names: raise ValueError('HWPX 본문 섹션이 없습니다.')
        for name in names: visit(ET.fromstring(archive.read(name)), name)
    return units


def extract_annex(path, api_text=''):
    """Return explicit coverage and a reproducible unit/offset ledger."""
    path = Path(path); raw = path.read_bytes()
    result = dict(schema=1, file_sha256=digest(raw), format='unknown', status='not-analyzed',
                  text='', units=[], issues=[], internal_references='not-resolved', numeric_rules='not-evaluated')
    try:
        if raw.startswith(b'PK\x03\x04'):
            result['format']='hwpx'; units=hwpx_units(path)
        elif raw.startswith(bytes.fromhex('d0cf11e0a1b11ae1')):
            result['format']='hwp'; original=read_hwp_text(path)
            if '┌' in api_text and '│' in api_text:
                rows=box_cells(api_text)
                # This check is for extraction fidelity, not legal equivalence.
                table=''.join(''.join(row) for row in rows)
                if not compact(table) or compact(table) not in compact(original):
                    raise ValueError('표의 칸별 내용과 HWP 원문이 일치하지 않습니다.')
                result['table_verified_against_hwp']=True
                result['table_rows']=rows
                units=[]; headers=rows[0]
                for r,row in enumerate(rows):
                    merged=len(row)!=len(headers)
                    for c,value in enumerate(row):
                        if not value.strip(): continue
                        label=f'표 {r+1}행 {c+1}열'
                        if r and c and not merged: label+=' · '+row[0]+' / '+headers[c]
                        units.append(dict(locator=label,raw_text=value,kind='cell',row=r,column=c,
                                          header=r==0 or c==0,merged_columns_unknown=merged))
                if any(u['merged_columns_unknown'] for u in units):
                    result['issues'].append('병합 행의 기관별 열 귀속은 미확정입니다. 해당 행은 개별 기관으로 배분하지 않습니다.')
            else:
                shapes=hwp_table_shapes(path)
                if any(shape!=(1,1) for shape in shapes):
                    raise ValueError('여러 칸으로 구성된 HWP 표는 칸별 API 원문 대조가 필요합니다.')
                result['single_cell_layout_only']=bool(shapes)
                units=[dict(locator=f'문단 {i+1}',raw_text=t.strip(),kind='paragraph')
                       for i,t in enumerate(original.splitlines()) if t.strip()]
        else:
            raise ValueError('지원하지 않는 파일 형식입니다. 이미지·PDF 표는 자동 분석하지 않습니다.')
        if not units: raise ValueError('추출된 본문이 없습니다.')
        text=''; numbered=''; letter=''; notes=False
        for i,u in enumerate(units):
            value=reference_spacing(u['raw_text']).strip()
            if compact(value)!=compact(u['raw_text']): raise ValueError('공백 이외의 원문이 변경되었습니다.')
            if u['kind']=='paragraph':
                if re.match(r'^비\s*고(?:\s|$|:)',value): notes=True;numbered=letter=''
                match=re.match(r'^(\d+)\.\s',value)
                sub=re.match(r'^([가-하])\.\s',value)
                if match: numbered=match[1]+'.';letter=''
                if sub: letter=sub[1]+'.'
                u['locator']=('비고 ' if notes else '')+(numbered+letter or u['locator'])
            u.update(id=f'u{i+1}',text=value,start=len(text),end=len(text)+len(value))
            text+=value+'\n'
        result.update(status='explicit-citations-ready',text=text,units=units,text_sha256=digest(text.encode()))
    except (ValueError, KeyError, IndexError, OSError, struct.error, zlib.error, ET.ParseError, zipfile.BadZipFile) as error:
        result['issues'].append(str(error))
    return result


def validate_analysis(analysis):
    if analysis.get('schema')!=1 or analysis.get('status')!='explicit-citations-ready':
        raise ValueError('별표 본문 분석 준비가 완료되지 않았습니다.')
    text=analysis['text']
    if digest(text.encode())!=analysis['text_sha256']: raise ValueError('별표 본문 해시 불일치')
    last=0;seen=set()
    for unit in analysis['units']:
        if unit['start']!=last or unit['end']<last or text[unit['start']:unit['end']]!=unit['text']:
            raise ValueError('별표 항목의 원문 위치 불일치')
        if unit['id'] in seen: raise ValueError('별표 항목 식별자 중복')
        seen.add(unit['id'])
        if compact(unit['text'])!=compact(unit['raw_text']): raise ValueError('별표 원문 내용 불일치')
        if text[unit['end']:unit['end']+1]!='\n': raise ValueError('별표 항목 구분 불일치')
        last=unit['end']+1
    if not seen or last!=len(text): raise ValueError('별표 본문에 귀속되지 않은 내용이 있습니다.')


def collect_annex_citations(corpus,focus_categories,source_names=None):
    """Reuse the shared citation adapter, separately for each cell/paragraph."""
    edges=[];external=[];issues=[];coverage=[]
    by_name={norm(d['name']):d for d in corpus}
    for law in corpus:
        if law.get('category') not in focus_categories: continue
        if source_names is not None and law['name'] not in source_names: continue
        main='\n'.join(a['text'] for a in law.get('articles',[]))
        main=main.translate(str.maketrans({'‘':'“','’':'”',"'":'"'}))
        declared,evidence=aliases_from(main)
        parsing={**deepcopy(law),'citation_policy':'mofe-explicit',
                 'aliases':{**law.get('aliases',{}),**declared},'alias_evidence':evidence}
        if law.get('provider','eflaw')=='eflaw' and law['name'].endswith((' 시행령',' 시행규칙')):
            base=re.sub(r' 시행(?:령|규칙)$','',law['name'])
            parsing['aliases'].setdefault('법',base)
            parsing['aliases'].setdefault('영',base+' 시행령')
        for annex in law.get('annexes',[]):
            analysis=annex.get('body_analysis')
            item=dict(law=law['name'],ref=annex['ref'],status='not-analyzed',references=0)
            coverage.append(item)
            if not analysis or analysis.get('status')!='explicit-citations-ready': continue
            validate_analysis(analysis)
            item.update(status='explicit-citations',units=len(analysis['units']),
                        internal_references='not-resolved',numeric_rules='not-evaluated')
            for unit in analysis['units']:
                if unit.get('header'): continue
                if unit['text'].startswith(('■','[별표')) or norm(unit['text'])==norm(annex['title']): continue
                prefix='별표 항목\n'; part=dict(jo='',text=prefix+unit['text'],citation_issues=[])
                for citation in adapter(parsing,part,corpus):
                    a=citation['start']-len(prefix);b=citation['end']-len(prefix)
                    if a<0: continue
                    owner=citation['target_name'];dest=by_name.get(norm(owner))
                    if dest: owner=dest['name']
                    start=unit['start']+a;end=unit['start']+b
                    quote=analysis['text'][start:end]
                    if quote!=citation['raw']: raise ValueError('별표 인용 근거 위치 불일치')
                    ident=(law['name'],annex['ref'],analysis['text_sha256'],start,end,owner,citation['target_ref'])
                    row=dict(source_law=law['name'],source_jo=annex['ref'],source_ref=annex['ref']+' · '+unit['locator'],
                             source_title=annex['title'],source_granularity='annex',source_layer='annex-body',
                             source_start=start,source_end=end,source_unit=unit['id'],
                             source_effective=law['effective'],source_url=law.get('source_url',''),
                             source_text_sha256=analysis['text_sha256'],source_file_sha256=analysis['file_sha256'],
                             target_law=owner,target_ref=citation['target_ref'],target_kind=citation.get('kind','article'),
                             target_url=dest.get('source_url','') if dest else '',target_effective=dest['effective'] if dest else '',
                             target_status='collected' if dest else 'not-collected',
                             target_provision_status=citation.get('target_provision_status',''),
                             context=unit['text'],cite_raw=quote,type='annex_body_reference',
                             context_review=bool(citation.get('context_review') or unit.get('merged_columns_unknown')),
                             annex_urls=annex.get('urls',[]),evidence_id=digest(repr(ident).encode())[:20])
                    if not dest:
                        from urllib.parse import quote as urlquote
                        row.update(target_url='https://www.law.go.kr/법령/'+urlquote(owner,safe=''),
                                   target_analysis='not-indexed',external_reverse='not-collected')
                    (edges if dest else external).append(row);item['references']+=1
                for issue in part['citation_issues']:
                    a=issue['start']-len(prefix);b=issue['end']-len(prefix)
                    if a>=0: issues.append(dict(source_law=law['name'],source_jo=annex['ref'],source_ref=unit['locator'],
                                              raw=unit['text'][a:b],reason=issue['reason'],source_start=unit['start']+a))
                for match in re.finditer(r'(?:제\s*\d+\s*호(?:[가-하]목)?|[가-힣]+과\s*같\s*음|같은\s*(?:표|항목))',unit['text']):
                    if any(e['source_law']==law['name'] and e['source_jo']==annex['ref'] and
                           e['source_start']<=unit['start']+match.start()<e['source_end'] for e in edges+external): continue
                    issues.append(dict(source_law=law['name'],source_jo=annex['ref'],source_ref=unit['locator'],
                                       raw=match[0],reason='별표 내부 항목·다른 칸 참조는 미해결입니다.',source_start=unit['start']+match.start()))
    return dict(edges=edges,external_references=external,issues=issues,coverage=coverage)
