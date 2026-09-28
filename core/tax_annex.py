"""Pinned national-tax annexes: HWP cells/paragraphs, never tax calculations.

This deliberately supports only the reviewed top-level HWP 5 table layout.
The shared annex reader remains fail-closed for other, unreviewed HWP tables.
"""
from copy import deepcopy
from collections import Counter
import json
from pathlib import Path
import re
import struct
from urllib.parse import parse_qs, urlparse
import zlib

from core.annex_analysis import (compact, digest, reference_spacing,
                                 validate_analysis, collect_annex_citations)
from core.hwp_reader import _para_text, read_hwp_text

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / 'output/tax-annexes-20260929'
SPECS = ROOT / 'data/tax-annex-sources.json'
LIMITATION = ('선정한 국세 별표 3개의 셀·문단과 명시적 인용을 제공합니다. '
              '다른 셀의 법령명이나 조건을 합치지 않습니다. 표 내부 참조와 '
              '내용연수·감가상각비·세액공제·적용 여부는 판정하지 않습니다.')


def official_download(url):
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if (parsed.scheme != 'https' or parsed.netloc != 'www.law.go.kr' or
            parsed.path != '/LSW/flDownload.do' or set(query) != {'flSeq'} or
            len(query['flSeq']) != 1 or not query['flSeq'][0].isdigit()):
        raise ValueError('별표의 공개 공식 다운로드 URL만 허용합니다.')
    return url


def records(data):
    """HWP record bounds and nesting levels; reject truncated records."""
    pos = 0
    while pos < len(data):
        begin = pos
        if pos + 4 > len(data):
            raise ValueError('잘린 HWP 레코드 헤더')
        header, = struct.unpack_from('<I', data, pos)
        pos += 4
        size = header >> 20
        if size == 4095:
            if pos + 4 > len(data):
                raise ValueError('잘린 HWP 확장 길이')
            size, = struct.unpack_from('<I', data, pos)
            pos += 4
        if pos + size > len(data):
            raise ValueError('잘린 HWP 레코드 본문')
        yield header & 1023, (header >> 10) & 1023, data[pos:pos+size], begin
        pos += size


def table_units(data, section='BodyText/Section0'):
    """Read reviewed top-level table cells and preserve each source paragraph.

    HWP table/list/cell layout: Hancom 5.0 revision 1.2, tables 65, 77, 80.
    These editions include the two-byte reserved list-header word (8 bytes
    total before cell properties); accept only the observed 47-byte records.
    Reject nested tables, unsupported controls, missing or overlapping cells.
    """
    units, cells = [], []
    table = cell = None
    paragraph_count = 0
    def close_cell():
        if cell is not None and paragraph_count != cell['paragraph_count']:
            raise ValueError('HWP 셀의 문단 개수 불일치')
    for index, (tag, level, payload, offset) in enumerate(records(data)):
        if tag == 71 and payload[:4] == b' lbt':
            if level != 1 or table is not None:
                raise ValueError('검증하지 않은 중첩·복수 표')
        elif tag == 71 and level > 1:
            raise ValueError('셀 내부의 지원하지 않는 컨트롤')
        if tag == 77:
            if level != 2 or table is not None or len(payload) < 18:
                raise ValueError('검증하지 않은 HWP 표 구조')
            rows, columns = struct.unpack_from('<HH', payload, 4)
            if not rows or not columns or rows * columns > 10000:
                raise ValueError('HWP 표 크기 오류')
            table = dict(rows=rows, columns=columns, section=section, record=index)
        elif tag == 72:
            close_cell()
            if table is None or level != 2 or len(payload) != 47:
                raise ValueError('검증하지 않은 HWP 셀 목록')
            count, reserved = struct.unpack_from('<HH', payload)
            column, row, col_span, row_span = struct.unpack_from('<HHHH', payload, 8)
            if reserved or not count or not col_span or not row_span:
                raise ValueError('HWP 셀 헤더 오류')
            if row+row_span > table['rows'] or column+col_span > table['columns']:
                raise ValueError('HWP 셀이 표 경계를 벗어납니다.')
            cell = dict(row=row, column=column, row_span=row_span, column_span=col_span,
                        paragraph_count=count, record=index, record_offset=offset)
            cells.append(cell)
            paragraph_count = 0
        elif tag == 66 and level == 2:
            if cell is None:
                raise ValueError('귀속할 셀이 없는 문단')
            paragraph_count += 1
        elif tag == 67:
            raw = _para_text(payload).strip()
            if not raw:
                continue
            if cell is None or level != 3:
                raise ValueError('검증된 셀 밖의 HWP 본문')
            if not paragraph_count:
                raise ValueError('HWP 문단 헤더 없음')
            units.append(dict(kind='paragraph' if cell['column_span'] == table['columns'] else 'cell',
                raw_text=raw, source_section=section, source_record=index,
                source_record_offset=offset, cell_record=cell['record'],
                cell_address=dict(rowAddr=cell['row'], colAddr=cell['column']),
                cell_span=dict(rowSpan=cell['row_span'], colSpan=cell['column_span']),
                source_paragraph=paragraph_count,
                locator=f"HWP 표 · {cell['row']+1}행 {cell['column']+1}열 · 문단 {paragraph_count}"))
    close_cell()
    if table is None or not units:
        raise ValueError('검증할 HWP 표 본문 없음')
    occupied = set()
    for cell in cells:
        for row in range(cell['row'], cell['row']+cell['row_span']):
            for column in range(cell['column'], cell['column']+cell['column_span']):
                if (row, column) in occupied:
                    raise ValueError('HWP 셀 영역 중복')
                occupied.add((row, column))
    if len(occupied) != table['rows'] * table['columns']:
        raise ValueError('HWP 표에 귀속되지 않은 셀 영역')
    return units, {**table, 'cells': cells}


def extract_tax_annex(path, spec):
    import olefile
    path = Path(path)
    raw = path.read_bytes()
    expected = spec['files']['hwp']
    if digest(raw) != expected['sha256'] or len(raw) != expected['bytes']:
        raise ValueError('검증된 국세 별표 HWP 판본 해시 불일치')
    if not raw.startswith(bytes.fromhex('d0cf11e0a1b11ae1')):
        raise ValueError('HWP 파일 시그니처 불일치')
    with olefile.OleFileIO(str(path)) as doc:
        header = doc.openstream('FileHeader').read()
        if header[:17] != b'HWP Document File' or header[32:36] != bytes.fromhex('01000105'):
            raise ValueError('검증하지 않은 HWP 버전')
        flags, = struct.unpack_from('<I', header, 36)
        if flags & 6:
            raise ValueError('암호화·배포용 HWP는 지원하지 않습니다.')
        sections = [e for e in doc.listdir() if e[0] == 'BodyText']
        if sections != [['BodyText', 'Section0']]:
            raise ValueError('검증하지 않은 HWP 다중 섹션')
        data = doc.openstream(sections[0]).read()
        if flags & 1:
            data = zlib.decompress(data, -15)
        units, table = table_units(data)
    original = read_hwp_text(path)
    if compact(''.join(u['raw_text'] for u in units)) != compact(original):
        raise ValueError('셀·문단 추출과 전체 HWP 원문 불일치')
    text = ''
    notes = False
    path_labels = ['', '', '', '']
    for i, unit in enumerate(units):
        value = reference_spacing(unit['raw_text']).strip()
        if compact(value) != compact(unit['raw_text']):
            raise ValueError('공백 이외의 HWP 원문 변경')
        if value == '비고':
            notes = True
            path_labels = ['', '', '', '']
        marker = re.match(r'^(\d+\.|[가-하]\.\s|\d+\)|[가-하]\))\s*', value)
        if marker and unit['kind'] == 'paragraph':
            label = marker[1].strip()
            level = (0 if label[0].isdigit() else 1) + (2 if label.endswith(')') else 0)
            path_labels[level] = label
            path_labels[level+1:] = [''] * (3-level)
        item = ('비고 / ' if notes else '') + ' / '.join(p for p in path_labels if p)
        if item and unit['kind'] == 'paragraph':
            unit['locator'] = item + ' · ' + unit['locator']
        # Title-related parent provisions belong to existing title-link evidence.
        unit['header'] = value.startswith('■') or compact(value) == compact(spec['title'])
        unit.update(id=f'u{i+1}', text=value, start=len(text), end=len(text)+len(value))
        text += value + '\n'
    result = dict(schema=1, kind='tax-annex-hwp-cells', format='hwp',
        status='explicit-citations-ready', file_sha256=digest(raw), text_sha256=digest(text.encode()),
        text=text, units=units, table_structure=table, full_hwp_text_verified=True,
        internal_references='not-resolved', numeric_rules='not-evaluated', issues=[],
        limitation=LIMITATION, reading_note=LIMITATION, extraction='pinned-hwp-table-cell-paragraph-v1')
    validate_analysis(result)
    return result


def validate_source(source, specs):
    if len(specs.get('annexes', [])) != 3 or len({s['id'] for s in specs['annexes']}) != 3:
        raise ValueError('검증 대상 국세 별표 3개가 필요합니다.')
    documents = {d['name']:d for d in source['laws']}
    for spec in specs['annexes']:
        owner = documents.get(spec['law'])
        if owner is None or any(owner.get(k) != spec['edition'][k] for k in spec['edition']):
            raise ValueError('국세 별표 소유 법령의 수집 판본 불일치')
        annex = next((a for a in owner['annexes'] if a['ref'] == spec['ref']), None)
        if (not annex or annex['title'] != spec['title'] or annex['effective'] != owner['effective'] or
                digest(annex['text'].encode()) != spec['api_text_sha256'] or
                set(annex['urls']) != {f['url'] for f in spec['files'].values()}):
            raise ValueError('국세 별표 메타데이터 또는 API 본문 불일치')
        for file in spec['files'].values():
            official_download(file['url'])
    return documents


def attach(source, folder=DEFAULT_OUTPUT, specs_path=SPECS):
    """Attach only reviewed editions; no source mutation or network access."""
    specs = json.loads(Path(specs_path).read_text(encoding='utf-8'))
    validate_source(source, specs)
    result = deepcopy(source)
    documents = {d['name']:d for d in result['laws']}
    for spec in specs['annexes']:
        for format, file in spec['files'].items():
            raw = (Path(folder) / file['name']).read_bytes()
            if digest(raw) != file['sha256'] or len(raw) != file['bytes']:
                raise ValueError('보존한 국세 별표 원본의 해시 불일치')
        analysis_raw = (Path(folder)/(spec['id']+'-analysis.json')).read_bytes()
        if digest(analysis_raw) != spec['analysis_sha256']:
            raise ValueError('검증된 국세 별표 분석 파일의 해시 불일치')
        analysis = json.loads(analysis_raw)
        validate_analysis(analysis)
        if analysis['file_sha256'] != spec['files']['hwp']['sha256']:
            raise ValueError('국세 별표 분석과 원본 파일 불일치')
        owner = documents[spec['law']]
        owner.setdefault('source_url', spec['source_url'])
        annex = next(a for a in owner['annexes'] if a['ref'] == spec['ref'])
        annex['body_analysis'] = analysis
    return result


def analyze(source, specs_path=SPECS):
    """Shared citation adapter, with explicit zero-citation coverage per annex."""
    result = collect_annex_citations(source['laws'], ('tax',))
    analyses = {(d['name'],a['ref']):a['body_analysis'] for d in source['laws']
                for a in d.get('annexes',[]) if a.get('body_analysis')}
    specs = json.loads(Path(specs_path).read_text(encoding='utf-8'))
    verified_self = {(spec['law'], spec['ref'], review['unit_text_sha256'], review['cite_raw'], review['target_ref'])
        for spec in specs['annexes'] for review in spec.get('verified_self_references', [])}
    # A bare article number must not silently become this annex's owner. Only
    # the one self-reference reviewed against the pinned paragraph is allowed.
    for group in ('edges', 'external_references'):
        accepted = []
        for row in result[group]:
            analysis = analyses[(row['source_law'], row['source_jo'])]
            unit = next(u for u in analysis['units'] if u['id'] == row['source_unit'])
            approved_self = (row['source_law'], row['source_jo'], digest(unit['text'].encode()),
                             row['cite_raw'], row['target_ref']) in verified_self
            if re.match(r'^제\s*\d+\s*조', row['cite_raw']) and not (approved_self and row['target_law'] == row['source_law']):
                result['issues'].append(dict(source_law=row['source_law'], source_jo=row['source_jo'],
                    source_ref=row['source_ref'], source_start=row['source_start'], source_end=row['source_end'],
                    raw=row['cite_raw'], reason='같은 셀·문단에 명시된 인용 법령 없음 · 인접 셀·문단의 법령명과 결합하지 않았습니다.'))
            else:
                accepted.append(row)
        result[group] = accepted
    counts = Counter((e['source_law'], e['source_jo']) for e in result['edges']+result['external_references'])
    for coverage in result['coverage']:
        if (coverage['law'], coverage['ref']) not in analyses:
            continue
        coverage['references'] = counts[(coverage['law'], coverage['ref'])]
        coverage['citation_status'] = 'citations-found' if coverage['references'] else 'zero-explicit-citations'
    return result


def merge_graph(graph, source):
    """Add selected annex evidence after the ordinary tax graph was built."""
    result = deepcopy(graph)
    annex = analyze(source)
    for group in ('edges', 'external_references'):
        result[group] = [e for e in result.get(group, []) if e.get('source_layer') != 'annex-body'] + annex[group]
    result['annex_analysis'] = {k:annex[k] for k in ('coverage', 'issues')}
    result['relation_counts'] = dict(Counter(e['target_kind'] for e in result['edges']))
    return result
