import test from 'node:test';
import assert from 'node:assert/strict';
import { EXTERNAL_FINANCE_GUIDES } from '../web/external-finance-guide-data.mjs';
import { createExternalFinanceGuide } from '../web/external-finance-guide.mjs';

// Adapter tests async callback boundaries. Real official source anchors are
// checked separately against collected documents by verify_external_finance_guide.
class Element {
  constructor(tag, ownerDocument) {
    this.tagName = tag.toUpperCase(); this.ownerDocument = ownerDocument;
    this.children = []; this.attributes = new Map(); this.listeners = new Map();
    this.className = ''; this.value = '';
    this.classList = { add: (...names) => { this.className += ' ' + names.join(' '); } };
  }
  set textContent(value) { this.value = String(value); this.children = []; }
  get textContent() { return this.value + this.children.map((n) => n.textContent).join(''); }
  append(...nodes) { this.children.push(...nodes); }
  prepend(...nodes) { this.children.unshift(...nodes); }
  replaceChildren(...nodes) { this.value = ''; this.children = nodes; }
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  getAttribute(name) { return this.attributes.get(name); }
  addEventListener(type, handler) { this.listeners.set(type, [...(this.listeners.get(type) || []), handler]); }
  click() { for (const handler of this.listeners.get('click') || []) handler(); }
}
const walk = (host) => host.children.flatMap((n) => [n, ...walk(n)]);
const buttons = (host, label) => walk(host).filter((n) => n.tagName === 'BUTTON' && n.textContent === label);
const settle = () => new Promise((resolve) => setImmediate(resolve));
function fixture(kind) {
  const dom = { createElement: (tag) => new Element(tag, dom) };
  const documents = new Map();
  for (const node of EXTERNAL_FINANCE_GUIDES[kind].nodes) for (const r of node.references) {
    if (!documents.has(r.law)) documents.set(r.law, {
      meta: { id: 'fixture-' + documents.size, name: r.law, domain: kind === 'kic' ? 'forex' : 'export_finance', effective: r.sourceEffective, url: r.url, file: { url: r.law } }, articles: [],
    });
    const doc = documents.get(r.law);
    const match = /^제(\d+)조(?:의(\d+))?$/.exec(r.article);
    const jo = match[1] + (match[2] ? '의' + match[2] : '');
    const article = doc.articles.find((a) => a.jo === jo);
    if (article) article.text += '\n' + r.quote;
    else doc.articles.push({ jo, title: r.title, text: r.quote });
  }
  return { host: dom.createElement('section'), documents, catalog: { laws: [...documents.values()].map((d) => d.meta) } };
}

test('export topics do not misclassify KIC as trade credit or imply a mandatory chain', () => {
  const guide = EXTERNAL_FINANCE_GUIDES.export;
  assert.equal(guide.layout, 'topics');
  assert.deepEqual(guide.nodes.map((n) => n.id), ['credit', 'investment', 'insurance', 'edcf']);
  assert.equal(guide.nodes.some((n) => n.references.some((r) => r.law.includes('한국투자공사'))), false);
  const kic = EXTERNAL_FINANCE_GUIDES.kic;
  assert.equal(kic.layout, 'flow');
  assert.match(kic.diagramNote, /필수 절차/);
  assert.match(kic.nodes.map((n) => n.summary).join(' '), /예외|특례/);
});

test('every reference carries a formal source edition and an exact textual anchor', () => {
  for (const guide of Object.values(EXTERNAL_FINANCE_GUIDES)) {
    assert.equal(new Set(guide.nodes.map((n) => n.id)).size, guide.nodes.length);
    for (const node of guide.nodes) {
      assert.ok(node.checks.length && node.references.length);
      for (const r of node.references) {
        assert.match(r.article, /^제\d+조(?:의\d+)?$/);
        assert.ok(r.title && r.quote && r.why);
        assert.match(r.sourceEffective, /^\d{8}$/);
        assert.ok(r.sourceEffective <= '20261118');
        assert.match(r.sourceMst, /^\d+$/);
        const url = new URL(r.url);
        assert.equal(url.hostname, 'www.law.go.kr');
        assert.equal(url.searchParams.get('lsiSeq'), r.sourceMst);
        assert.equal(url.searchParams.get('efYd'), r.sourceEffective);
      }
    }
  }
});

test('explicit actions open the verified source article; cards never navigate on initial load', async () => {
  for (const kind of ['export', 'kic']) {
    const { host, documents, catalog } = fixture(kind);
    const reads = [], explores = [], loads = [];
    const controller = createExternalFinanceGuide({ host, kind,
      load: async (file) => { loads.push(file.url); return documents.get(file.url); },
      read: (...args) => reads.push(args), explore: (...args) => explores.push(args),
    });
    controller.update(catalog);
    await settle();
    assert.equal(reads.length, 0); assert.equal(explores.length, 0);
    assert.ok(loads.length > 0 && loads.length <= 2);
    assert.ok(buttons(host, '조문 읽기').length > 0);
    buttons(host, '조문 읽기')[0].click();
    buttons(host, '인용 지도에서 보기')[0].click();
    assert.deepEqual(reads[0], explores[0]);
    assert.equal(reads.length, 1);
    const nextNode = EXTERNAL_FINANCE_GUIDES[kind].nodes[1];
    const next = walk(host).find((n) => n.tagName === 'BUTTON' && n.textContent.includes(nextNode.title));
    next.click(); await settle();
    assert.equal(next.getAttribute('aria-pressed'), 'true');
  }
});

test('new unreviewed editions retain official links but cannot open a misleading explanation as verified', async () => {
  const { host, documents, catalog } = fixture('kic');
  for (const doc of documents.values()) doc.meta = { ...doc.meta, effective: '20990101' };
  const controller = createExternalFinanceGuide({ host, kind: 'kic', load: async (file) => documents.get(file.url), read() {}, explore() {} });
  controller.update(catalog); await settle();
  assert.equal(buttons(host, '조문 읽기').length, 0);
  assert.match(host.textContent, /判本|판본/);
  assert.ok(walk(host).some((n) => n.tagName === 'A' && n.href.startsWith('https://www.law.go.kr/')));
});

test('reset invalidates late loads and failed requests can be retried', async () => {
  const { host, documents, catalog } = fixture('export');
  let release;
  const pending = new Promise((resolve) => { release = resolve; });
  const controller = createExternalFinanceGuide({ host, kind: 'export', load: () => pending, read() {}, explore() {} });
  controller.update(catalog); await settle(); controller.reset();
  release(documents.values().next().value); await settle();
  assert.equal(host.children.length, 0);
  let failed = true;
  const retry = createExternalFinanceGuide({ host, kind: 'export', load: async (file) => {
    if (failed) throw Error('offline'); return documents.get(file.url);
  }, read() {}, explore() {} });
  retry.update(catalog); await settle();
  assert.ok(buttons(host, '다시 대조').length > 0);
  failed = false; buttons(host, '다시 대조')[0].click(); await settle();
  assert.ok(buttons(host, '조문 읽기').length > 0);
});
