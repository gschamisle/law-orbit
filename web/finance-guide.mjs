import { FINANCE_GUIDE } from './finance-guide-data.mjs';
import { safeLink, target } from './query.mjs';

// These are editorial starting points, never an inference that a law applies.
const compact = (value) => String(value || '').replace(/\s+/gu, '');
const fail = (status, message) => ({ ok: false, status, message });
function editionId(value) {
  try {
    const url = new URL(value);
    if (!['law.go.kr', 'www.law.go.kr'].includes(url.hostname) || url.protocol !== 'https:') return '';
    return url.searchParams.get('lsiSeq') || '';
  } catch {
    return '';
  }
}

export function resolveGuideReference(reference, catalog) {
  let jo;
  try {
    jo = target(reference.article).jo;
  } catch {
    return fail('invalid-reference', '근거 조문 표기를 확인해야 합니다.');
  }
  const matches = (catalog?.laws || []).filter((law) => law.name === reference.law);
  if (!matches.length) return fail('missing-law', '이 법령은 현재 수집 목록에서 찾지 못했습니다.');
  if (matches.length !== 1)
    return fail('ambiguous-law', '같은 이름의 자료가 여럿이어서 판본 확인이 필요합니다.');
  if (!matches[0].file) return fail('missing-document', '수집 본문 파일이 없습니다.');
  return { ok: true, status: 'resolved', message: '', entry: matches[0], jo };
}

export function validateGuideReference(reference, entry, document) {
  if (!document?.meta || !Array.isArray(document.articles))
    return fail('missing-document', '수집 본문 형식을 확인할 수 없습니다.');
  if (
    document.meta.id !== entry.id ||
    document.meta.name !== entry.name ||
    reference.law !== entry.name ||
    (entry.domain && document.meta.domain !== entry.domain)
  )
    return fail('metadata-mismatch', '목록과 본문의 법령 정보가 일치하지 않습니다.');
  if (
    (entry.effective && document.meta.effective !== entry.effective) ||
    (reference.sourceEffective &&
      (entry.effective !== reference.sourceEffective || document.meta.effective !== reference.sourceEffective)) ||
    (reference.sourceMst &&
      (editionId(entry.url) !== reference.sourceMst || editionId(document.meta.url) !== reference.sourceMst))
  )
    return fail('edition-mismatch', '길잡이의 검토 판본과 수집 판본이 다릅니다. 설명을 적용하기 전에 변경 내용을 확인해야 합니다.');
  let jo;
  try {
    jo = target(reference.article).jo;
  } catch {
    return fail('invalid-reference', '근거 조문 표기를 확인해야 합니다.');
  }
  const articles = document.articles.filter((article) => article.jo === jo);
  if (articles.length !== 1) return fail('missing-article', '수집 본문에서 이 조문을 확정하지 못했습니다.');
  const article = articles[0];
  if (!reference.title || compact(article.title) !== compact(reference.title))
    return fail('title-mismatch', '검토 당시 조문 제목과 수집 본문이 달라 다시 확인해야 합니다.');
  if (!compact(reference.quote) || !compact(article.text).includes(compact(reference.quote)))
    return fail('quote-mismatch', '검토에 사용한 문구를 수집 본문에서 확인하지 못했습니다.');
  return { ok: true, status: 'verified', message: '검토 판본·제목·근거 문구 대조', entry, article, jo };
}

function dateLabel(value) {
  const raw = String(value || '');
  return /^\d{8}$/.test(raw) ? `${raw.slice(0, 4)}.${raw.slice(4, 6)}.${raw.slice(6)}` : raw;
}

export function createFinanceGuide({ host, load, read, explore }) {
  const dom = host.ownerDocument;
  const guide = FINANCE_GUIDE;
  let catalog = null;
  let generation = 0;
  let selection = 0;
  let selectedId = guide.flowNodes[0]?.id;
  let mode = 'flow';
  let diagram, detail, announcement, modeButtons;
  const pending = new Map();
  const nodeButtons = [];

  function el(tag, content = '', className = '') {
    const element = dom.createElement(tag);
    element.textContent = content;
    if (className) element.className = className;
    return element;
  }

  function button(label, action, className = '') {
    const element = el('button', label, className);
    element.type = 'button';
    element.addEventListener('click', action);
    return element;
  }

  function sourceLink(reference) {
    const href = safeLink(reference.url);
    if (!href) return el('span', '공식 출처 확인 필요', 'muted small');
    const a = el('a', '검토 판본 원문 ↗');
    a.href = href;
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    return a;
  }

  function nodeButton(node, index = null) {
    const b = button('', () => {
      selectNode(node.id);
      // Only an explicit step selection moves a narrow screen to its result.
      // Initial rendering, scrolling, and switching views never move the page.
      if (dom.defaultView?.matchMedia?.('(max-width: 1000px)').matches) {
        detail.focus({ preventScroll: true });
        detail.scrollIntoView({ block: 'start', behavior: 'instant' });
      }
    }, 'finance-node');
    b.setAttribute('aria-pressed', String(node.id === selectedId));
    b.setAttribute('aria-controls', 'finance-guide-detail');
    if (index !== null) b.append(el('span', String(index + 1).padStart(2, '0'), 'finance-node-number'));
    b.append(el('strong', node.title), el('span', node.question, 'finance-node-question'));
    nodeButtons.push({ id: node.id, element: b });
    return b;
  }

  function renderDiagram() {
    diagram.replaceChildren();
    nodeButtons.length = 0;
    if (mode === 'flow') {
      const path = el('div', '', 'finance-flow-path');
      path.setAttribute('aria-label', '상품과 업무를 정한 뒤 확인할 순서');
      const main = guide.flowNodes.filter((node) => node.id !== 'oversight');
      main.forEach((node, index) => {
        const part = el('div', '', 'finance-flow-part');
        const step = el('div', '', 'finance-flow-step');
        step.append(nodeButton(node, index));
        part.append(step);
        if (index < main.length - 1) {
          const edge = guide.flowEdges.find((item) => item.from === node.id && item.to === main[index + 1].id);
          if (edge) {
            const arrow = el('div', '', 'finance-flow-arrow');
            arrow.setAttribute('role', 'img');
            arrow.setAttribute('aria-label', edge.label);
            arrow.title = edge.label;
            arrow.append(el('span', '→'));
            step.append(el('span', edge.label, 'finance-flow-label'));
            part.append(arrow);
          }
        } else {
          const spacer = el('span', '', 'finance-flow-label');
          spacer.setAttribute('aria-hidden', 'true');
          step.append(spacer);
        }
        path.append(part);
      });
      diagram.append(path);
      const oversight = guide.flowNodes.find((node) => node.id === 'oversight');
      if (oversight) {
        const rail = el('div', '', 'finance-parallel');
        const edge = guide.flowEdges.find((item) => item.to === oversight.id);
        const caption = el('div', '', 'finance-parallel-caption');
        caption.append(el('span', '↳', 'finance-parallel-arrow'), el('p', edge?.label || '영업 전반에서 함께 확인'));
        rail.append(caption, nodeButton(oversight));
        diagram.append(rail);
      }
    } else {
      const grid = el('div', '', 'finance-system-grid');
      for (const group of guide.systemGroups) {
        const section = el('section', '', 'finance-system-group');
        section.append(el('h3', group.title), el('p', group.summary, 'muted'));
        for (const id of group.nodeIds) {
          const node = guide.flowNodes.find((item) => item.id === id);
          if (node) section.append(nodeButton(node));
        }
        grid.append(section);
      }
      diagram.append(grid);
    }
  }

  function loadDocument(entry) {
    const key = typeof entry.file === 'string' ? entry.file : JSON.stringify(entry.file);
    if (!pending.has(key)) {
      const request = Promise.resolve().then(() => load(entry.file));
      pending.set(key, request);
      request.catch(() => {
        if (pending.get(key) === request) pending.delete(key);
      });
    }
    return pending.get(key);
  }

  async function renderReference(reference, box, token, cycle) {
    const heading = el('h4', `${reference.law} ${reference.article}`);
    box.append(heading, el('p', reference.title, 'finance-reference-title'), el('p', reference.why));
    const status = el('p', '수집 본문과 근거를 대조하고 있습니다.', 'finance-reference-status');
    box.append(status);
    const quotation = el('details', '', 'finance-quote');
    quotation.append(el('summary', '검토에 사용한 근거 문구'), el('blockquote', reference.quote));
    if (reference.sourceEffective)
      quotation.append(el('p', `검토 판본 시행일 ${dateLabel(reference.sourceEffective)}`, 'muted small'));
    box.append(quotation);
    const actions = el('div', '', 'finance-reference-actions');
    actions.append(sourceLink(reference));
    box.append(actions);
    const resolved = resolveGuideReference(reference, catalog);
    if (!resolved.ok) {
      status.textContent = resolved.message;
      status.classList.add('needs-review');
      return;
    }
    try {
      const document = await loadDocument(resolved.entry);
      if (token !== selection || cycle !== generation) return;
      const checked = validateGuideReference(reference, resolved.entry, document);
      status.textContent = checked.message;
      if (!checked.ok) {
        status.classList.add('needs-review');
        return;
      }
      const dates = [`수집 본문 시행일 ${dateLabel(resolved.entry.effective) || '미기재'}`];
      const collected = resolved.entry.collected_at || resolved.entry.collected;
      if (collected) dates.push(`수집 ${dateLabel(collected)}`);
      else if (catalog.built_at) dates.push(`자료 구성 ${dateLabel(catalog.built_at)}`);
      status.append(el('span', dates.join(' · '), 'finance-reference-date'));
      actions.prepend(
        button('조문 읽기', () => read(resolved.entry.id, checked.jo), 'finance-read'),
        button('인용 지도에서 보기', () => explore(resolved.entry.id, checked.jo), 'quiet'),
      );
    } catch {
      if (token !== selection || cycle !== generation) return;
      status.textContent = '본문을 불러오지 못했습니다. 연결을 확인하거나 공식 원문에서 읽어 주세요.';
      status.classList.add('needs-review');
      const retry = button('다시 대조', () => {
        box.replaceChildren();
        void renderReference(reference, box, token, cycle);
      }, 'quiet');
      actions.prepend(retry);
    }
  }

  function selectNode(id) {
    const node = guide.flowNodes.find((item) => item.id === id);
    if (!node || !catalog) return;
    selectedId = id;
    const token = ++selection;
    const cycle = generation;
    for (const item of nodeButtons) item.element.setAttribute('aria-pressed', String(item.id === id));
    announcement.textContent = `${node.title}의 확인 사항과 근거 조문을 표시합니다.`;
    detail.replaceChildren();
    const summary = el('div', '', 'finance-detail-summary');
    const back = button('다른 단계 보기 ↑', () => {
      const selected = nodeButtons.find((item) => item.id === selectedId)?.element;
      selected?.focus({ preventScroll: true });
      diagram.scrollIntoView({ block: 'start', behavior: 'instant' });
    }, 'finance-back quiet');
    summary.append(back);
    summary.append(el('span', '이 단계에서 살펴볼 것', 'eyebrow'), el('h3', node.question), el('p', node.summary));
    const roles = el('div', '', 'finance-roles');
    roles.setAttribute('aria-label', '관련 역할');
    for (const role of node.roles) roles.append(el('span', role));
    summary.append(roles);
    const checks = el('ul', '', 'finance-checks');
    for (const check of node.checks) checks.append(el('li', check));
    summary.append(checks);
    const references = el('div', '', 'finance-references');
    references.append(el('h3', '근거 조문'));
    detail.append(summary, references);
    for (const reference of node.references) {
      const box = el('article', '', 'finance-reference');
      references.append(box);
      void renderReference(reference, box, token, cycle);
    }
  }

  function setMode(value) {
    mode = value;
    for (const [key, b] of Object.entries(modeButtons)) b.setAttribute('aria-pressed', String(key === mode));
    renderDiagram();
    const note = host.querySelector('.finance-diagram-note');
    note.textContent = mode === 'flow'
      ? '화살표는 확인할 순서입니다. 법적 인용 관계나 모든 업무의 필수 절차를 뜻하지 않습니다.'
      : '역할별로 편집한 체계도입니다. 칸의 위치는 법률의 우열이나 적용 순위를 뜻하지 않습니다.';
  }

  function update(nextCatalog) {
    reset();
    catalog = nextCatalog;
    host.classList.add('finance-guide');
    const intro = el('header', '', 'finance-guide-intro');
    intro.append(el('span', 'FINANCE / WORK & RULES', 'eyebrow'), el('h2', guide.title), el('p', guide.scope, 'muted'));
    const review = el('p', `길잡이 검토 ${dateLabel(guide.reviewedOn)} · 금융상품 판매·소비자보호부터 제공합니다.`, 'finance-guide-review');
    intro.append(review);
    const switcher = el('div', '', 'finance-view-switch');
    switcher.setAttribute('aria-label', '길잡이 보기 방식');
    modeButtons = {
      flow: button('업무 흐름', () => setMode('flow')),
      system: button('규율 체계', () => setMode('system')),
    };
    for (const b of Object.values(modeButtons)) switcher.append(b);
    diagram = el('div', '', 'finance-diagram');
    const diagramNote = el('p', '', 'finance-diagram-note');
    announcement = el('p', '', 'finance-selection-status');
    announcement.setAttribute('role', 'status');
    announcement.setAttribute('aria-live', 'polite');
    detail = el('section', '', 'finance-detail');
    detail.id = 'finance-guide-detail';
    detail.tabIndex = -1;
    detail.setAttribute('aria-label', '선택한 업무의 확인 사항과 근거');
    host.append(intro, switcher, diagramNote, diagram, announcement, detail);
    setMode(mode);
    selectNode(selectedId);
  }

  function reset() {
    generation++;
    selection++;
    catalog = null;
    pending.clear();
    nodeButtons.length = 0;
    host.replaceChildren();
  }

  return { update, reset };
}
