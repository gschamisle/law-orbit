// PDF offsets are Python Unicode code-point offsets, just like citation evidence.
export function pdfPage(document, page) {
  const record = document.pdf_analysis?.pages.find((p) => p.page === Number(page));
  if (!record) throw Error('수집한 PDF에 해당 쪽이 없습니다.');
  return {
    ...record,
    text: Array.from(document.unstructured_text).slice(record.start, record.end).join(''),
  };
}
export function pdfConnections(document, page) {
  const rows = document.pdf_analysis?.internal_connections || [];
  return {
    forward: rows.filter((r) => r.source_page === Number(page)),
    reverse: rows.filter((r) => r.target_page === Number(page)),
  };
}
export function pdfAnchor(document, id) {
  const anchor = document.pdf_analysis?.anchors?.find((a) => a.id === id);
  if (
    !anchor ||
    !Array.from(document.unstructured_text)
      .slice(anchor.start, anchor.end)
      .join('')
      .startsWith(anchor.label)
  )
    throw Error('확인된 PDF 목적지 본문이 없습니다.');
  return anchor;
}
export function renderProcurementPdf(
  container,
  document,
  evidence,
  { text, link, markBody, onPage = () => {} },
) {
  const pdf = document.pdf_analysis;
  if (!pdf) return false;
  const choice = window.document.createElement('select');
  choice.setAttribute('aria-label', 'PDF 본문 쪽');
  for (const p of pdf.pages) {
    const option = text(
      'option',
      `PDF ${p.page}쪽${p.printed_page ? ' (인쇄 ' + p.printed_page + '쪽)' : ''} · ${p.label || '목차·표·서식 등'}${p.analyzed_units ? '' : ' · 연결 미분석'}`,
    );
    option.value = p.page;
    choice.append(option);
  }
  const sourceRows = evidence.filter(
    (r) =>
      r.direction === 'reverse' &&
      r.source_id === document.meta.id &&
      r.source_layer?.startsWith('procurement-pdf-'),
  );
  choice.value = sourceRows[0]?.source_page || pdf.pages.find((p) => p.analyzed_units)?.page || 1;
  const label = text('label', '본문 위치');
  label.append(choice);
  const meta = text('p', '', 'muted small'),
    body = text('div', '', 'reading-text');
  const scope = text('details');
  scope.append(text('summary', 'PDF 분석 범위'), text('p', pdf.limitation, 'muted small'));
  const internal = text('details');
  internal.className = 'pdf-internal';
  const stage = text('div');
  let selected = null;
  stage.append(body);
  container.replaceChildren(scope, label, meta, internal, stage);
  const render = () => {
    const page = pdfPage(document, choice.value);
    stage.replaceChildren(body);
    body.textContent = page.text;
    meta.replaceChildren(
      text(
        'span',
        `PDF ${page.page}쪽 · ${page.analyzed_units ? (pdf.anchors ? '문단·표 셀 인용 분석' : '일반 문단 인용 분석') : '이 쪽은 연결 미분석'} `,
      ),
      link(pdf.pdf_url + '#page=' + page.page, '공식 PDF에서 확인 ↗'),
    );
    const rows = sourceRows
      .filter((r) => r.source_page === page.page)
      .map((r) => ({
        ...r,
        source_start: r.source_start - page.start,
        source_end: r.source_end - page.start,
      }));
    if (rows.length && markBody) markBody(body, page.text, rows, stage);
    const connections = pdfConnections(document, page.page),
      count = connections.forward.length + connections.reverse.length;
    internal.hidden = !count;
    internal.open = !!count;
    internal.replaceChildren(
      text('summary', `지침 내부 연결 ${count}건`),
      text(
        'p',
        '명시된 장·절·항목·별표의 위치 연결입니다. 법령의 조문 인용과 구분합니다.',
        'muted small',
      ),
    );
    for (const [direction, items] of Object.entries(connections))
      for (const row of items) {
        const reverse = direction === 'reverse',
          item = text('div', '', 'pdf-internal-row');
        item.append(
          text(
            'p',
            reverse
              ? `← PDF ${row.source_page}쪽에서 이 쪽을 참조`
              : `→ ${row.target_label} · PDF ${row.target_page}쪽`,
          ),
          text('blockquote', row.raw),
        );
        if (row.review_note) item.append(text('p', row.review_note, 'pdf-review-note'));
        const button = text('button', reverse ? '인용한 쪽 보기' : '대상 쪽 보기', 'quiet');
        button.onclick = () => {
          if (reverse) {
            choice.value = row.source_page;
            selected = { start: row.source_start, end: row.source_end };
          } else {
            const a = pdfAnchor(document, row.target_id);
            choice.value = a.page;
            selected = { start: a.start, end: a.start + Array.from(a.label).length };
          }
          render();
        };
        item.append(button);
        internal.append(item);
      }
    let focusMark = null;
    if (selected && page.start <= selected.start && selected.end <= page.end) {
      const chars = Array.from(page.text),
        a = selected.start - page.start,
        b = selected.end - page.start,
        mark = text('mark', chars.slice(a, b).join(''));
      body.replaceChildren(
        window.document.createTextNode(chars.slice(0, a).join('')),
        mark,
        window.document.createTextNode(chars.slice(b).join('')),
      );
      focusMark = mark;
    }
    onPage(page);
    if (focusMark) focusMark.scrollIntoView({ block: 'center' });
  };
  choice.onchange = () => {
    selected = null;
    render();
  };
  render();
  return true;
}
