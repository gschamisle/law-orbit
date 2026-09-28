"""Conservative, opt-in paragraph citations from the two MOIS procurement PDFs.

PDF page/printed-page and chapter/section/item are source locations, not articles.
Tables, annex/form blocks, contents and supplements never enter the citation adapter.
"""
from copy import deepcopy
import hashlib
import re
from urllib.parse import quote

from core.ftc_text_citations import canonical_documents, normalized_quotes, prepare_text_aliases
from core.fsc_administrative import adapter
from core.fsc_collection import norm

LOCAL_LAW = '지방자치단체를 당사자로 하는 계약에 관한 법률'
ALLOWED = {'29508': '지방자치단체 입찰 및 계약 집행기준',
           '36201': '지방자치단체 입찰시 낙찰자 결정기준'}
LIMITATION = ('PDF 일반 문단의 명시적 법령 인용을 분석했습니다. 표·도표·별표·서식·부칙과 '
              '지침 내부 장·절·항목 간 참조는 미분석입니다. 페이지 경계를 넘는 문장과 PDF 추출 오류로 '
              '인용이 누락될 수 있습니다. 금액·점수·산식의 적용을 판정하지 않습니다.')
CHAPTER = re.compile(r'^제\s*\d+\s*장(?:\s*의\s*\d+)?\s+.{2,}')
SECTION = re.compile(r'^제\s*\d+\s*절\s+.{1,}')
ITEM = re.compile(r'^(?:\d+(?:-\d+)*\.|[가나다라마바사아자차카타파하]\.|\d+\)|[가나다라마바사아자차카타파하]\))\s*')
ATTACHMENT = re.compile(r'^(?:[<\[【]\s*별\s*(?:표|지)|■.*\[별|별\s*(?:표|지)\s*\d)')
# A few headings in the two pinned editions use body-size type. Exact titles
# prevent a sentence beginning "제4절 ... 준용한다" from replacing the source section.
BODY_SIZE_SECTIONS = {norm(v) for v in (
    '제11절 지방자치단체 재해복구계약 운영요령', '제10절 부정당업자의 제재와 당사자의 의무',
    '제6절 검사와 대가지급', '제9절 기타', '제1절 목 적', '제5절 보칙',
    '제1절 통 칙', '제2절 대상제품', '제3절 입찰과 계약상대자 결정절차',
    '제4절 그 밖의 사항', '제2절 평가방법')}


def digest(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def extract_pdf(path, record):
    import pdfplumber
    if ALLOWED.get(record['document_id']) != record['name']:
        raise ValueError('Unapproved PDF source')
    raw = path.read_bytes()
    if not raw.startswith(b'%PDF-'):
        raise ValueError('Not a PDF')
    pages, units, parts = [], [], []
    offset = 0
    chapter = section = item = ''
    item_path = ['', '', '', '']
    attachment = supplement = False
    with pdfplumber.open(path) as pdf:
        for number, original in enumerate(pdf.pages, 1):
            page = original.dedupe_chars(tolerance=2, extra_attrs=())
            text = page.extract_text(x_tolerance=2) or ''
            printed = re.search(r'(?m)^-\s*(\d+)\s*-$', text)
            printed = printed[1] if printed else ''
            tables = page.find_tables()
            boxes = [t.bbox for t in tables]
            # Reject the whole line if it intersects a table. A column must never be
            # joined to unrelated prose on the same baseline to fabricate a citation.
            lines = page.extract_text_lines(x_tolerance=2, return_chars=True)
            clean = []
            for line in lines:
                if re.fullmatch(r'-\s*\d+\s*-', line['text'].strip()):
                    continue
                if any(line['top'] < y1 and line['bottom'] > y0 and line['x0'] < x1 and line['x1'] > x0
                       for x0, y0, x1, y1 in boxes):
                    clean.append(('[표·도표 영역: 공식 PDF 확인 · 연결 미분석]', 0))
                else:
                    clean.append((line['text'].strip(), min((c['size'] for c in line['chars'] if c['text'].strip()), default=0)))
            clean = [v for i, v in enumerate(clean) if i == 0 or v != clean[i-1]]
            is_contents = number <= 2 or '순서' in norm(text[:160])
            status = 'contents' if is_contents else 'prose'
            prefix = f'\n\n[PDF {number}쪽' + (f' · 인쇄 {printed}쪽' if printed else '') + ']\n'
            parts.append(prefix); offset += len(prefix)
            start = offset
            pending, begin, location = [], offset, ''

            def flush():
                nonlocal pending, begin
                body = '\n'.join(pending)
                if body.strip():
                    units.append(dict(start=begin, end=begin+len(body), page=number,
                        printed_page=printed, chapter=chapter, section=section, item=item,
                        locator=location, text=body))
                pending = []

            for line, font_size in clean:
                # Typography separates headings from a wrapped sentence citing a
                # different chapter. Both approved PDFs use 20pt/15pt headings.
                is_chapter = bool(CHAPTER.match(line) and font_size >= 18)
                is_section = bool(SECTION.match(line) and (font_size >= 14.8 or norm(line) in BODY_SIZE_SECTIONS))
                boundary = bool(is_chapter or is_section or ITEM.match(line))
                if boundary or line.startswith('[표·도표'):
                    flush()
                if is_chapter:
                    chapter = line; section = item = ''; item_path = ['', '', '', '']; attachment = False
                elif is_section:
                    section = line; item = ''; item_path = ['', '', '', '']
                elif ITEM.match(line):
                    # Retain the actual numbered item, not its entire paragraph.
                    label = ITEM.match(line)[0].strip()
                    level = (0 if re.match(r'^\d+\.', label) else 1 if re.match(r'^[가나다라마바사아자차카타파하]\.', label) else 2 if re.match(r'^\d+\)', label) else 3)
                    item_path[level] = label
                    for n in range(level+1, 4): item_path[n] = ''
                    item = ' / '.join(v for v in item_path if v)
                if not is_contents and re.match(r'^부\s*칙(?:\s|$|\()', line):
                    flush(); supplement = True
                if not is_contents and ATTACHMENT.match(line):
                    flush(); attachment = True
                eligible = not (is_contents or attachment or supplement or line.startswith('[표·도표'))
                if eligible:
                    if not pending:
                        begin = offset
                        location = ' / '.join(v for v in (chapter, section, item) if v)
                    pending.append(line)
                parts.append(line+'\n'); offset += len(line)+1
            flush()
            if supplement: status = 'supplement'
            elif attachment: status = 'annex-or-form'
            page_units = [u for u in units if u['page'] == number]
            pages.append(dict(page=number, printed_page=printed, start=start, end=offset,
                              tables=len(boxes), status=status, analyzed_units=len(page_units)))
            if number % 100 == 0:
                print(f"{record['document_id']}: PDF {number}/{len(pdf.pages)}", flush=True)
    text = ''.join(parts)
    # Parts include a terminal newline; unit offsets exclude it.
    if any(text[u['start']:u['end']] != u['text'] for u in units):
        raise ValueError('PDF source offset mismatch')
    source_url = record['attachments'][0]['첨부파일링크'].replace('http:', 'https:')
    return dict(schema=1, kind='procurement-pdf-prose', text=text, units=units, pages=pages,
        file_sha256=digest(raw), text_sha256=digest(text), bytes=len(raw), pdf_url=source_url,
        record=deepcopy(record), limitation=LIMITATION,
        extraction=dict(engine='pdfplumber', version=pdfplumber.__version__,
                        char_dedupe_tolerance=2, excluded='tables,contents,annexes,forms,supplements',
                        page_boundary_references='not-joined'))


def validate_extraction(result):
    if result.get('kind') != 'procurement-pdf-prose' or digest(result['text']) != result['text_sha256']:
        raise ValueError('PDF text integrity mismatch')
    if ALLOWED.get(result['record']['document_id']) != result['record']['name']:
        raise ValueError('Unapproved PDF source')
    if not result['units']:
        raise ValueError('PDF has no verified prose units')
    for unit in result['units']:
        page = result['pages'][unit['page']-1]
        if not (page['start'] <= unit['start'] < unit['end'] <= page['end']):
            raise ValueError('PDF page bounds mismatch')
        if result['text'][unit['start']:unit['end']] != unit['text']:
            raise ValueError('PDF unit integrity mismatch')


def analyze_pdf(result, corpus):
    validate_extraction(result)
    record = result['record']; names = canonical_documents(corpus)
    rows, issues = [], []
    chapter_docs = {}
    # A verified collective definition supplies the local-contract triplet. Do not
    # infer a law from the ministry, PDF title, or nearby legal subject matter.
    compact = norm(result['text'])
    declaration = re.search(re.escape(norm(LOCAL_LAW))+r'[․·ㆍ]시행령[․·ㆍ]시행규칙」\(각각["“]법["”],["“]시행령["”],["“]시행규칙["”]이라한다\)', compact)
    collective = {'법':LOCAL_LAW,'시행령':LOCAL_LAW+' 시행령','시행규칙':LOCAL_LAW+' 시행규칙'} if declaration else {}
    for unit in result['units']:
        chapter_docs.setdefault(unit['chapter'], []).append(unit['text'])
    for chapter, texts in chapter_docs.items():
        doc = dict(record, raw_body_blocks=['\n'.join(texts)], articles=[])
        prepare_text_aliases(doc)
        doc['aliases'] = {**collective, **doc['aliases']}
        doc['citation_policy'] = 'mofe-explicit'
        chapter_docs[chapter] = doc
    for unit in result['units']:
        part = dict(text=normalized_quotes(unit['text']), jo='')
        parsing = deepcopy(chapter_docs[unit['chapter']])
        for citation in adapter(parsing, part, corpus):
            canonical = {norm(k):v for k,v in parsing.get('aliases',{}).items()}.get(norm(citation['target_name']),citation['target_name'])
            target = names.get(norm(canonical))
            kind = citation.get('kind', 'article')
            owner = target['name'] if target else canonical
            if kind=='law' and re.search(r'법률\s*[․·ㆍ]\s*시행령',owner):
                a,b=unit['start']+citation['start'],unit['start']+citation['end']
                issues.append(dict(source_law=record['name'],source_ref=unit['locator']+f" · PDF {unit['page']}쪽",source_start=a,source_end=b,raw=result['text'][a:b],reason='법률·시행령·시행규칙을 함께 정의한 문구 · 개별 법령 인용과 구분'))
                continue
            if kind == 'law' and not target and not owner.endswith(('법','법률','시행령','시행규칙','규칙','고시','지침','기준','규정','요령')):
                continue
            a, b = unit['start']+citation['start'], unit['start']+citation['end']
            locator = unit['locator'] + f" · PDF {unit['page']}쪽" + (f" (인쇄 {unit['printed_page']}쪽)" if unit['printed_page'] else '')
            raw = result['text'][a:b]
            rows.append(dict(evidence_id=digest(repr((record['uid'],result['file_sha256'],a,b,owner,citation['target_ref'])))[:20],
                source_law=record['name'], source_jo='', source_ref=locator, source_granularity='text',
                source_layer='procurement-pdf-prose', source_page=unit['page'], source_file_sha256=result['file_sha256'],
                source_text_sha256=result['text_sha256'], source_start=a, source_end=b,
                source_effective=record['effective'], source_url=result['pdf_url']+f"#page={unit['page']}",
                target_law=owner, target_ref=citation['target_ref'], target_kind=kind,
                target_url=target['source_url'] if target else 'https://www.law.go.kr/법령/'+quote(owner,safe=''),
                target_effective=target['effective'] if target else '',
                target_status=('collected' if target.get('articles') else 'collected-not-indexed') if target else 'not-collected',
                target_provision_status=citation.get('target_provision_status',''), raw=raw, cite_raw=raw,
                context=unit['text'], context_review=citation.get('context_review',False),
                reason='PDF 일반 문단의 명시적 인용입니다. 장·절·항목은 조문 번호로 변환하지 않았습니다.'))
        for issue in part.get('citation_issues', []):
            a, b = unit['start']+issue['start'], unit['start']+issue['end']
            issues.append(dict(source_law=record['name'], source_ref=unit['locator']+f" · PDF {unit['page']}쪽",
                source_start=a, source_end=b, raw=result['text'][a:b], reason=issue['reason']))
    return rows, issues
