// Exact official-body anchors and optional packed-site verification. No network.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { exit } from 'node:process';
import path from 'node:path';
import { gunzipSync } from 'node:zlib';
import { createHash } from 'node:crypto';
import { EXTERNAL_FINANCE_GUIDES } from '../web/external-finance-guide-data.mjs';
import { resolveGuideReference, validateGuideReference } from '../web/finance-guide.mjs';

const args = process.argv.slice(2), options = {};
while (args.length) {
  const key = args.shift();
  if (key === '--if-present') {
    options.ifPresent = true;
    continue;
  }
  if (!['--source', '--site', '--report'].includes(key) || !args.length) throw Error('Unknown or incomplete option');
  options[key.slice(2)] = args.shift();
}
assert.ok(Boolean(options.source) !== Boolean(options.site), 'Use --source SOURCE.json or --site SITE');
assert.ok(!options.ifPresent || options.site, '--if-present requires --site');
let manifest, source, read;
if (options.source) source = JSON.parse(fs.readFileSync(options.source, 'utf8'));
else {
  const site = path.resolve(options.site);
  manifest = JSON.parse(fs.readFileSync(path.join(site, 'manifest.json'), 'utf8'));
  if (options.ifPresent && !manifest.domains.some((d) => d.id === 'export_finance')) {
    console.log('External finance guides: skipped for a snapshot without export finance.');
    exit(0);
  }
  const cache = new Map();
  const rawFile = (ref) => {
    assert.match(ref.sha256 || '', /^[a-f0-9]{64}$/);
    assert.equal(ref.url, `data/${ref.sha256}.json.gz`);
    const raw = fs.readFileSync(path.join(site, ref.url));
    check(raw, ref); return raw;
  };
  const check = (raw, ref) => {
    assert.equal(raw.length, ref.bytes);
    assert.equal(createHash('sha256').update(raw).digest('hex'), ref.sha256);
  };
  read = (ref) => {
    assert.match(ref.sha256 || '', /^[a-f0-9]{64}$/);
    assert.equal(ref.url, `data/${ref.sha256}.json.gz`);
    let raw;
    if (manifest.data_packs && ref.bytes <= manifest.data_packs.threshold) {
      const bucket = manifest.data_packs.buckets[ref.sha256.slice(0, 2)];
      assert.ok(bucket, 'Missing pack bucket');
      if (!cache.has(bucket.sha256)) {
        const pack = JSON.parse(gunzipSync(rawFile(bucket)));
        assert.equal(pack.kind, 'law-orbit-small-files'); assert.equal(pack.schema, 1);
        cache.set(bucket.sha256, pack.entries);
      }
      const value = cache.get(bucket.sha256)[ref.sha256];
      assert.equal(typeof value, 'string'); raw = Buffer.from(value, 'base64'); check(raw, ref);
    } else raw = rawFile(ref);
    return JSON.parse(gunzipSync(raw));
  };
}
const evidence = [];
for (const [kind, guide] of Object.entries(EXTERNAL_FINANCE_GUIDES)) {
  const domain = kind === 'kic' ? 'forex' : 'export_finance';
  let catalog, load;
  if (source) {
    const docs = source.laws.map((doc) => ({ meta: {
      id: doc.uid, name: doc.name, effective: doc.effective, url: doc.source_url, domain, file: { url: doc.uid },
    }, articles: doc.articles }));
    catalog = { laws: docs.map((doc) => doc.meta) };
    load = (entry) => docs.find((doc) => doc.meta.id === entry.id);
  } else {
    const area = manifest.domains.find((d) => d.id === domain);
    assert.ok(area, `Missing ${domain} collection`);
    catalog = read(area.catalog); load = (entry) => read(entry.file);
  }
  for (const node of guide.nodes) for (const ref of node.references) {
    const label = `${kind}/${node.id}: ${ref.law} ${ref.article}`;
    const found = resolveGuideReference(ref, catalog);
    assert.equal(found.ok, true, `${label}: ${found.status}`);
    const document = load(found.entry);
    const result = validateGuideReference(ref, found.entry, document);
    assert.equal(result.ok, true, `${label}: ${result.status}`);
    evidence.push({ kind, node: node.id, law: ref.law, article: ref.article, sourceMst: ref.sourceMst,
      sourceEffective: ref.sourceEffective, title: ref.title, quote: ref.quote, status: result.status });
  }
}
const result = { status: 'passed', reviewedOn: '2026-11-18', source: options.site ? 'built-site' : 'official-collected-bodies',
  siteVersion: manifest?.version || null, references: evidence.length, evidence,
  limitation: 'Exact identity, edition, title and quote verification; not an applicability judgment or completeness guarantee.' };
if (options.report) {
  fs.mkdirSync(path.dirname(path.resolve(options.report)), { recursive: true });
  fs.writeFileSync(options.report, JSON.stringify(result, null, 2) + '\n', 'utf8');
}
console.log(`External finance guides: ${evidence.length} official-body anchors verified.`);
