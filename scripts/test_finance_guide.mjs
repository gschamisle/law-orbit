import test from 'node:test';
import assert from 'node:assert/strict';
import { FINANCE_GUIDE } from '../web/finance-guide-data.mjs';
import { createFinanceGuide, resolveGuideReference, validateGuideReference } from '../web/finance-guide.mjs';

// Synthetic text deliberately includes an exception: positive wording cannot
// be carried over to a different article, law or silently changed edition.
const law = '검증용 금융규율법';
const ref = {
  law, article: '제12조', title: '등록과 예외',
  quote: '등록하여야 한다. 다만, 다른 법률에 따라 인가를 받은 경우에는 그러하지 아니하다.',
  sourceEffective: '20260102', sourceMst: '277247',
  url: 'https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=277247&efYd=20260102',
};
const entry = { id: 'fsc-example', name: law, domain: 'fsc', effective: '20260102', url: ref.url, file: { url: 'synthetic' } };
const article = { jo: '12', title: ref.title, label: '제12조', text: `제12조(${ref.title})\n① ${ref.quote}` };
const document = { meta: { ...entry }, articles: [article] };
const catalog = { laws: [entry] };

test('exact law and article resolution returns the requested article, never the first law', () => {
  const more = { laws: [{ ...entry, id: 'prefix', name: law + ' 시행령' }, entry] };
  const found = resolveGuideReference(ref, more);
  assert.equal(found.ok, true);
  assert.equal(found.entry.id, entry.id);
  assert.equal(found.jo, '12');
  const result = validateGuideReference(ref, found.entry, document);
  assert.equal(result.ok, true);
  assert.equal(result.article, article);
  assert.equal(result.jo, '12');
});

test('missing and duplicate formal names fail closed instead of guessing an alias', () => {
  assert.equal(resolveGuideReference({ ...ref, law: '금융규율법' }, catalog).ok, false);
  assert.equal(resolveGuideReference(ref, { laws: [] }).ok, false);
  const duplicates = { laws: [entry, { ...entry, id: 'another-edition' }] };
  const ambiguous = resolveGuideReference(ref, duplicates);
  assert.equal(ambiguous.ok, false);
  assert.equal(ambiguous.status, 'ambiguous-law');
});

test('invalid article syntax and absent requested articles cannot substitute a nearby article', () => {
  for (const articleNumber of ['', '12 또는 13', '제0조', '제12조부터 제14조까지', '<script>']) {
    assert.equal(resolveGuideReference({ ...ref, article: articleNumber }, catalog).ok, false, articleNumber);
  }
  const absent = validateGuideReference({ ...ref, article: '제99조' }, entry, document);
  assert.equal(absent.ok, false);
  assert.equal(absent.status, 'missing-article');
  assert.equal(validateGuideReference(ref, entry, null).ok, false);
});

test('inserted article numbers remain distinct from ordinary article numbers', () => {
  const inserted = { ...ref, article: '제12조의2' };
  assert.equal(resolveGuideReference(inserted, catalog).jo, '12의2');
  assert.equal(validateGuideReference(inserted, entry, document).ok, false);
  const body = { ...document, articles: [article, { ...article, jo: '12의2', label: '제12조의2' }] };
  const checked = validateGuideReference(inserted, entry, body);
  assert.equal(checked.ok, true);
  assert.equal(checked.article.jo, '12의2');
});

test('wrong body identity, domain or source edition is never marked verified', () => {
  for (const metadata of [
    { id: 'other-law' }, { name: law + ' 시행령' }, { domain: 'tax' }, { effective: '20270101' },
  ]) {
    const changed = { ...document, meta: { ...document.meta, ...metadata } };
    assert.equal(validateGuideReference(ref, entry, changed).ok, false, JSON.stringify(metadata));
  }
  // Even when catalog and body agree, a newer unreviewed edition is not silently
  // accepted just because the selected sentence happened to stay unchanged.
  const next = { ...entry, effective: '20270101', url: ref.url.replace('20260102', '20270101') };
  assert.equal(validateGuideReference(ref, next, { ...document, meta: next }).ok, false);
  const otherMst = { ...entry, url: ref.url.replace('277247', '999999') };
  assert.equal(validateGuideReference(ref, otherMst, { ...document, meta: otherMst }).ok, false);
});

test('changed legal wording, added negation and wrong titles invalidate the explanation anchor', () => {
  const variants = [
    { ...article, text: article.text.replace('아니하다', '한다') },
    { ...article, text: article.text.replace('등록하여야 한다', '등록하지 아니하여야 한다') },
    { ...article, title: '폐지' },
    { ...article, text: '' },
  ];
  for (const changed of variants)
    assert.equal(validateGuideReference(ref, entry, { ...document, articles: [changed] }).ok, false);
  assert.equal(validateGuideReference({ ...ref, quote: '' }, entry, document).ok, false);
  assert.equal(validateGuideReference({ ...ref, quote: '여기에 없는 근거' }, entry, document).ok, false);
});

test('layout-only whitespace can vary while punctuation and exception text stay intact', () => {
  const wrapped = { ...article, text: article.text.replaceAll(' ', '\n  '), title: '등록과\n예외' };
  const sourceBefore = JSON.stringify(document);
  assert.equal(validateGuideReference(ref, entry, { ...document, articles: [wrapped] }).ok, true);
  assert.equal(JSON.stringify(document), sourceBefore);
  assert.equal(validateGuideReference(ref, entry, { ...document, articles: [{ ...article, text: article.text.replace('다만,', '다만') }] }).ok, false);
});

test('each guide step has explicit question, source and reviewed edition; no invented destinations', () => {
  const ids = FINANCE_GUIDE.flowNodes.map((n) => n.id);
  assert.equal(new Set(ids).size, ids.length);
  assert.ok(ids.length >= 5);
  assert.match(FINANCE_GUIDE.reviewedOn, /^\d{4}-\d{2}-\d{2}$/);
  for (const node of FINANCE_GUIDE.flowNodes) {
    assert.ok(node.title && node.question && node.summary);
    assert.ok(node.references.length > 0);
    for (const source of node.references) {
      assert.ok(source.law && source.article && source.title && source.why && source.quote);
      assert.match(source.sourceEffective, /^\d{8}$/);
      assert.match(source.sourceMst, /^\d+$/);
      const url = new URL(source.url);
      assert.equal(url.protocol, 'https:');
      assert.ok(['law.go.kr', 'www.law.go.kr'].includes(url.hostname));
      assert.equal(url.searchParams.get('lsiSeq'), source.sourceMst, 'The official link must open the reviewed edition');
      assert.equal(url.searchParams.get('efYd'), source.sourceEffective);
    }
  }
  for (const edge of FINANCE_GUIDE.flowEdges) {
    assert.ok(ids.includes(edge.from) && ids.includes(edge.to));
    assert.notEqual(edge.from, edge.to);
    assert.ok(edge.label, 'A guide connector must explain its review relationship');
  }
  const mapped = new Set();
  for (const group of FINANCE_GUIDE.systemGroups) {
    assert.ok(group.title && group.summary && group.nodeIds.length);
    for (const id of group.nodeIds) {
      assert.ok(ids.includes(id));
      mapped.add(id);
    }
  }
  assert.deepEqual([...mapped].sort(), [...ids].sort());
});

test('supervision is an optional parallel review branch rather than a prerequisite of selling', () => {
  const edges = FINANCE_GUIDE.flowEdges;
  assert.ok(edges.some((e) => e.to === 'oversight'));
  assert.equal(edges.some((e) => e.from === 'oversight' && ['entry', 'selling', 'contract'].includes(e.to)), false);
  const queue = ['scope'], visited = new Set();
  while (queue.length) {
    const id = queue.shift();
    if (visited.has(id) || id === 'oversight') continue;
    visited.add(id);
    queue.push(...edges.filter((e) => e.from === id).map((e) => e.to));
  }
  for (const id of ['entry', 'selling', 'contract', 'remedy']) assert.ok(visited.has(id));
});

// Small DOM adapter exercises request/callback boundaries without installing a
// browser dependency. Actual layout and focus appearance are browser checks.
class Element {
  constructor(tag, ownerDocument) {
    this.tagName = tag.toUpperCase();
    this.ownerDocument = ownerDocument;
    this.children = [];
    this.attributes = new Map();
    this.listeners = new Map();
    this.className = '';
    this.value = '';
    this.classList = { add: (...names) => { this.className = [...new Set([...this.className.split(' '), ...names])].join(' ').trim(); } };
  }
  set textContent(value) { this.value = String(value); this.children = []; }
  get textContent() { return this.value + this.children.map((n) => n.textContent).join(''); }
  append(...nodes) { this.children.push(...nodes); }
  prepend(...nodes) { this.children.unshift(...nodes); }
  replaceChildren(...nodes) { this.value = ''; this.children = nodes; }
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  getAttribute(name) { return this.attributes.get(name); }
  addEventListener(type, handler) { this.listeners.set(type, [...(this.listeners.get(type) || []), handler]); }
  click() { for (const handler of this.listeners.get('click') || []) handler({ currentTarget: this }); }
  querySelector(selector) { return walk(this).find((n) => selector.startsWith('.') ? n.className.split(' ').includes(selector.slice(1)) : n.tagName === selector.toUpperCase()) || null; }
}
function walk(root) { return root.children.flatMap((n) => [n, ...walk(n)]); }
function hostFixture() {
  const dom = { createElement: (tag) => new Element(tag, dom) };
  return dom.createElement('section');
}
function fixtureSources() {
  const documents = new Map();
  for (const stage of FINANCE_GUIDE.flowNodes) for (const r of stage.references) {
    if (!documents.has(r.law)) {
      const meta = { id: 'fixture-' + documents.size, name: r.law, domain: 'fsc', effective: r.sourceEffective, url: r.url, file: { url: r.law } };
      documents.set(r.law, { meta, articles: [] });
    }
    const doc = documents.get(r.law);
    const jo = /^제(\d+)조(?:의(\d+))?$/.exec(r.article);
    const number = jo[1] + (jo[2] ? '의' + jo[2] : '');
    if (!doc.articles.some((a) => a.jo === number)) doc.articles.push({ jo: number, title: r.title, text: r.quote });
  }
  return { documents, catalog: { laws: [...documents.values()].map((d) => d.meta) } };
}
const settle = () => new Promise((resolve) => setImmediate(resolve));
const buttons = (host, label) => walk(host).filter((n) => n.tagName === 'BUTTON' && n.textContent === label);

test('selected-step loading is lazy and reading/exploring are separate deliberate actions', async () => {
  const host = hostFixture(), sources = fixtureSources(), loads = [], reads = [], explores = [];
  const guide = createFinanceGuide({ host,
    load: async (file) => { loads.push(file.url); return sources.documents.get(file.url); },
    read: (...args) => reads.push(args), explore: (...args) => explores.push(args),
  });
  guide.update(sources.catalog);
  await settle();
  assert.equal(loads.length, 1, 'Initial same-law references share one body request');
  assert.equal(reads.length, 0);
  assert.equal(explores.length, 0);
  buttons(host, '조문 읽기')[0].click();
  assert.deepEqual(reads, [['fixture-0', '2']]);
  assert.equal(explores.length, 0);
  buttons(host, '인용 지도에서 보기')[0].click();
  assert.deepEqual(explores, [['fixture-0', '2']]);
  const entryButton = walk(host).find((n) => n.tagName === 'BUTTON' && n.textContent.includes('인가·등록 확인'));
  entryButton.click();
  await settle();
  assert.equal(loads.length, 2, 'Decree is fetched only when its stage is selected');
  assert.equal(entryButton.getAttribute('aria-pressed'), 'true');
  assert.ok(walk(host).includes(entryButton), 'Selecting a stage must preserve its focused button');
  buttons(host, '규율 체계')[0].click();
  await settle();
  assert.equal(loads.length, 2, 'Switching diagram styles reuses the selection and loaded source');
});

test('failed loads can be retried and a mismatch never exposes active local read actions', async () => {
  const host = hostFixture(), sources = fixtureSources();
  let calls = 0, fail = true;
  const guide = createFinanceGuide({ host, load: async (file) => {
    calls++;
    if (fail) throw Error('offline');
    return sources.documents.get(file.url);
  }, read: () => assert.fail('unexpected read'), explore: () => assert.fail('unexpected explore') });
  guide.update(sources.catalog);
  await settle();
  assert.equal(calls, 1);
  assert.equal(buttons(host, '조문 읽기').length, 0);
  assert.ok(buttons(host, '다시 대조').length > 0);
  fail = false;
  buttons(host, '다시 대조')[0].click();
  await settle();
  assert.equal(calls, 2);
  assert.equal(buttons(host, '조문 읽기').length, 1);
  const doc = sources.documents.values().next().value;
  doc.meta = { ...doc.meta, effective: '20990101' };
  guide.update(sources.catalog);
  await settle();
  assert.equal(buttons(host, '조문 읽기').length, 0);
  assert.equal(buttons(host, '인용 지도에서 보기').length, 0);
  assert.match(host.textContent, /판본/);
  const originalSource = FINANCE_GUIDE.flowNodes[0].references[0].url;
  assert.ok(walk(host).some((n) => n.tagName === 'A' && n.href === originalSource && n.textContent.includes('원문')));
});

test('late requests cannot populate a removed step or restore a reset guide', async () => {
  const host = hostFixture(), sources = fixtureSources();
  let release;
  const pending = new Promise((resolve) => { release = resolve; });
  const guide = createFinanceGuide({ host, load: () => pending, read: () => {}, explore: () => {} });
  guide.update(sources.catalog);
  await settle();
  const oldReferences = walk(host).filter((n) => n.className === 'finance-reference');
  const next = walk(host).find((n) => n.tagName === 'BUTTON' && n.textContent.includes('권리·분쟁 해결'));
  next.click();
  release(sources.documents.values().next().value);
  await settle();
  for (const old of oldReferences) assert.equal(buttons(old, '조문 읽기').length, 0, 'Old selection received a late action');
  assert.equal(buttons(host, '조문 읽기').length, 3);
  let resolveAgain;
  const stillPending = new Promise((resolve) => { resolveAgain = resolve; });
  const resetHost = hostFixture();
  const resetting = createFinanceGuide({ host: resetHost, load: () => stillPending, read: () => {}, explore: () => {} });
  resetting.update(sources.catalog);
  await settle();
  resetting.reset();
  resolveAgain(sources.documents.values().next().value);
  await settle();
  assert.equal(resetHost.children.length, 0);
  assert.equal(resetHost.textContent, '');
});
