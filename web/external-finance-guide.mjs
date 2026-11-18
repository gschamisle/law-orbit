import { EXTERNAL_FINANCE_GUIDES } from './external-finance-guide-data.mjs';
import { resolveGuideReference, validateGuideReference } from './finance-guide.mjs';
import { safeLink } from './query.mjs';

// Each card is an editorial reading path. It never creates citation edges.
export function createExternalFinanceGuide({ host, load, read, explore, kind }) {
  const guide = EXTERNAL_FINANCE_GUIDES[kind];
  if (!guide) throw new Error('Unknown external finance guide');
  const dom = host.ownerDocument;
  let catalog = null;
  let generation = 0;
  let selection = 0;
  let selectedId = guide.nodes[0].id;
  const pending = new Map();
  const buttons = new Map();
  let detail, diagram, announcement;
  const el = (tag, text = '', className = '') => {
    const element = dom.createElement(tag);
    element.textContent = text;
    if (className) element.className = className;
    return element;
  };
  const button = (text, action, className = '') => {
    const element = el('button', text, className);
    element.type = 'button';
    element.addEventListener('click', action);
    return element;
  };
  function sourceLink(reference) {
    const href = safeLink(reference.url);
    if (!href) return el('span', '공식 출처 확인 필요', 'muted small');
    const link = el('a', '검토 판본 원문 ↗');
    link.href = href;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    return link;
  }
  function loadDocument(entry) {
    const key = JSON.stringify(entry.file);
    if (!pending.has(key)) {
      const request = Promise.resolve().then(() => load(entry.file));
      pending.set(key, request);
      request.catch(() => { if (pending.get(key) === request) pending.delete(key); });
    }
    return pending.get(key);
  }
  async function renderReference(reference, box, token, cycle) {
    box.append(el('h4', `${reference.law} ${reference.article}`),
      el('p', reference.title, 'finance-reference-title'), el('p', reference.why));
    const status = el('p', '수집 판본과 근거 문구를 대조하고 있습니다.', 'finance-reference-status');
    const quote = el('details', '', 'finance-quote');
    quote.append(el('summary', '검토에 사용한 근거 문구'), el('blockquote', reference.quote),
      el('p', `검토 판본 시행일 ${reference.sourceEffective}`, 'muted small'));
    const actions = el('div', '', 'finance-reference-actions');
    actions.append(sourceLink(reference));
    box.append(status, quote, actions);
    const found = resolveGuideReference(reference, catalog);
    if (!found.ok) {
      status.textContent = found.message;
      status.classList.add('needs-review');
      return;
    }
    try {
      const document = await loadDocument(found.entry);
      if (token !== selection || cycle !== generation) return;
      const checked = validateGuideReference(reference, found.entry, document);
      status.textContent = checked.message;
      if (!checked.ok) { status.classList.add('needs-review'); return; }
      actions.prepend(
        button('조문 읽기', () => read(found.entry.id, checked.jo), 'finance-read'),
        button('인용 지도에서 보기', () => explore(found.entry.id, checked.jo), 'quiet'),
      );
    } catch {
      if (token !== selection || cycle !== generation) return;
      status.textContent = '본문을 불러오지 못했습니다. 공식 원문을 열거나 다시 시도해 주세요.';
      status.classList.add('needs-review');
      actions.prepend(button('다시 대조', () => {
        box.replaceChildren();
        void renderReference(reference, box, token, cycle);
      }, 'quiet'));
    }
  }
  function select(id, explicit = false) {
    if (!catalog) return;
    const node = guide.nodes.find((item) => item.id === id);
    if (!node) return;
    selectedId = id;
    const token = ++selection;
    const cycle = generation;
    for (const [key, value] of buttons) value.setAttribute('aria-pressed', String(key === id));
    announcement.textContent = `${node.title}의 확인 사항과 근거 조문을 표시합니다.`;
    detail.replaceChildren();
    const summary = el('div', '', 'finance-detail-summary');
    const back = button('다른 항목 보기 ↑', () => {
      buttons.get(selectedId)?.focus({ preventScroll: true });
      diagram.scrollIntoView({ block: 'start', behavior: 'instant' });
    }, 'finance-back quiet');
    summary.append(back, el('span', '살펴볼 기준', 'eyebrow'), el('h3', node.question), el('p', node.summary));
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
    if (explicit && dom.defaultView?.matchMedia?.('(max-width: 1000px)').matches) {
      detail.focus({ preventScroll: true });
      detail.scrollIntoView({ block: 'start', behavior: 'instant' });
    }
  }
  function update(nextCatalog) {
    reset();
    catalog = nextCatalog;
    host.hidden = false;
    host.classList.add('finance-guide', 'external-finance-guide');
    const intro = el('header', '', 'finance-guide-intro');
    intro.append(el('span', guide.eyebrow, 'eyebrow'), el('h2', guide.title), el('p', guide.scope, 'muted'),
      el('p', `길잡이 검토 ${guide.reviewedOn}`, 'finance-guide-review'));
    const note = el('p', guide.diagramNote, 'finance-diagram-note');
    diagram = el('div', '', guide.layout === 'flow' ? 'external-guide-flow' : 'external-guide-topics');
    diagram.setAttribute('aria-label', guide.layout === 'flow' ? '위탁·운용에서 확인할 순서' : '지원 목적에 따른 업무별 출발점');
    guide.nodes.forEach((node, index) => {
      const item = el('div', '', 'external-guide-item');
      const b = button('', () => select(node.id, true), 'finance-node');
      b.setAttribute('aria-pressed', String(node.id === selectedId));
      b.setAttribute('aria-controls', `${guide.id}-detail`);
      b.append(el('span', guide.layout === 'flow' ? String(index + 1).padStart(2, '0') : node.tag, 'finance-node-number'),
        el('strong', node.title), el('span', node.question, 'finance-node-question'));
      buttons.set(node.id, b);
      item.append(b);
      if (guide.layout === 'flow' && index < guide.nodes.length - 1) {
        const arrow = el('span', '→', 'external-guide-arrow');
        arrow.setAttribute('aria-hidden', 'true');
        item.append(arrow);
      }
      diagram.append(item);
    });
    announcement = el('p', '', 'finance-selection-status');
    announcement.setAttribute('role', 'status');
    announcement.setAttribute('aria-live', 'polite');
    detail = el('section', '', 'finance-detail');
    detail.id = `${guide.id}-detail`;
    detail.tabIndex = -1;
    detail.setAttribute('aria-label', '선택한 업무의 확인 사항과 근거');
    host.append(intro, note, diagram, announcement, detail);
    select(selectedId);
  }
  function reset() {
    generation++;
    selection++;
    catalog = null;
    pending.clear();
    buttons.clear();
    host.replaceChildren();
  }
  function hide() { reset(); host.hidden = true; }
  return { update, show: update, hide, reset };
}
