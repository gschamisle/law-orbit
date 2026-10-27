// Validate the curated guide against a locally prepared, content-addressed site.
// No network, collection, inference, or publication is performed by this command.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { gunzipSync } from 'node:zlib';
import { createHash } from 'node:crypto';
import { FINANCE_GUIDE } from '../web/finance-guide-data.mjs';
import { resolveGuideReference, validateGuideReference } from '../web/finance-guide.mjs';

function siteReader(site, manifest) {
  const packs = new Map();
  const checked = new Map();
  const read = (ref) => {
    assert.match(ref?.sha256 || '', /^[a-f0-9]{64}$/, 'Invalid content digest');
    assert.equal(ref.url, `data/${ref.sha256}.json.gz`, 'Unsafe content path');
    assert.ok(Number.isSafeInteger(ref.bytes) && ref.bytes > 0 && ref.bytes <= 25 * 1024 * 1024);
    let raw;
    if (manifest.data_packs && ref.bytes <= manifest.data_packs.threshold) {
      const bucket = manifest.data_packs.buckets[ref.sha256.slice(0, 2)];
      assert.ok(bucket, 'Missing small-file bucket');
      if (!packs.has(bucket.sha256)) {
        assert.match(bucket.sha256 || '', /^[a-f0-9]{64}$/);
        assert.equal(bucket.url, `data/${bucket.sha256}.json.gz`, 'Unsafe bucket path');
        const compressed = fs.readFileSync(path.join(site, bucket.url));
        checkBytes(compressed, bucket);
        const pack = JSON.parse(gunzipSync(compressed));
        assert.equal(pack.kind, 'law-orbit-small-files');
        assert.equal(pack.schema, 1);
        packs.set(bucket.sha256, pack.entries);
      }
      const encoded = packs.get(bucket.sha256)[ref.sha256];
      assert.equal(typeof encoded, 'string', 'Missing packed member');
      raw = Buffer.from(encoded, 'base64');
    } else raw = fs.readFileSync(path.join(site, ref.url));
    checkBytes(raw, ref);
    checked.set(ref.sha256, ref.bytes);
    return JSON.parse(gunzipSync(raw));
  };
  return { read, checked };
}

function checkBytes(raw, ref) {
  assert.match(ref?.sha256 || '', /^[a-f0-9]{64}$/);
  assert.equal(ref.url, `data/${ref.sha256}.json.gz`);
  assert.equal(raw.length, ref.bytes, 'Content length mismatch');
  assert.equal(createHash('sha256').update(raw).digest('hex'), ref.sha256, 'Content checksum mismatch');
}

export function verifyFinanceGuide(site) {
  site = path.resolve(site);
  const manifest = JSON.parse(fs.readFileSync(path.join(site, 'manifest.json'), 'utf8'));
  const finance = manifest.domains.find((d) => d.id === 'fsc');
  assert.ok(finance, 'Finance collection is missing');
  const { read, checked } = siteReader(site, manifest);
  const catalog = read(finance.catalog);
  const documents = new Map();
  const evidence = [];
  for (const node of FINANCE_GUIDE.flowNodes) {
    assert.ok(node.references.length > 0, `${node.id}: no source references`);
    for (const ref of node.references) {
      const resolved = resolveGuideReference(ref, catalog);
      assert.equal(resolved.ok, true, `${node.id}: ${ref.law} ${ref.article}: ${resolved.status}`);
      if (!documents.has(resolved.entry.id)) documents.set(resolved.entry.id, read(resolved.entry.file));
      const document = documents.get(resolved.entry.id);
      const result = validateGuideReference(ref, resolved.entry, document);
      assert.equal(result.ok, true, `${node.id}: ${ref.law} ${ref.article}: ${result.status}`);
      assert.equal(ref.sourceEffective, document.meta.effective, 'The curated source edition has changed');
      assert.match(ref.sourceMst || '', /^\d+$/, 'The reviewed official edition must be recorded');
      const source = new URL(ref.url);
      assert.equal(source.protocol, 'https:');
      assert.ok(['www.law.go.kr', 'law.go.kr'].includes(source.hostname), 'Unexpected official source host');
      assert.equal(source.searchParams.get('lsiSeq'), ref.sourceMst, 'Official link points to a different edition');
      assert.equal(source.searchParams.get('efYd'), ref.sourceEffective);
      evidence.push({ node: node.id, law: ref.law, article: ref.article, title: ref.title,
        sourceEffective: ref.sourceEffective, sourceMst: ref.sourceMst, collectedEffective: document.meta.effective,
        documentId: resolved.entry.id, documentSha256: resolved.entry.file.sha256,
        quote: ref.quote, status: result.status });
    }
  }
  assert.ok(evidence.length > 0);
  return { status: 'passed', guide: FINANCE_GUIDE.id, reviewedOn: FINANCE_GUIDE.reviewedOn,
    siteVersion: manifest.version, financeBuiltAt: catalog.built_at,
    nodes: FINANCE_GUIDE.flowNodes.length, references: evidence.length, documents: documents.size,
    checkedAssets: checked.size, sourceEvidence: evidence,
    limitation: 'Checks exact source identity, edition, title and quote anchors. This does not determine applicability or prove complete legal coverage.' };
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  const args = process.argv.slice(2);
  let site, report;
  while (args.length) {
    const name = args.shift();
    if (name === '--site') site = args.shift();
    else if (name === '--report') report = args.shift();
    else throw Error(`Unknown option: ${name}`);
  }
  if (!site) throw Error('Usage: node scripts/verify_finance_guide.mjs --site SITE [--report OUTPUT.json]');
  const result = verifyFinanceGuide(site);
  if (report) {
    fs.mkdirSync(path.dirname(path.resolve(report)), { recursive: true });
    fs.writeFileSync(report, JSON.stringify(result, null, 2) + '\n', 'utf8');
  }
  console.log(`Finance guide: ${result.nodes} stages, ${result.references} source anchors, ${result.documents} documents verified (${result.siteVersion}).`);
}
