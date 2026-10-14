import test from 'node:test';
import assert from 'node:assert/strict';
import { lawNeighbors, lawOverview, loadLawPair } from '../web/law-overview.mjs';

const overview = {
  nodes: ['국세기본법', '민법', '국세징수법', '소득세법'].map((id) => ({ id, web_law: id + '-id' })),
  links: [{ a: '국세기본법', b: '민법', n: 3 }],
  all_links: [
    { a: '국세기본법', b: '민법', n: 3 },
    { a: '국세징수법', b: '국세기본법', n: 2 },
    { a: '민법', b: '국세기본법', n: 1 },
    { a: '국세기본법', b: '국세기본법', n: 40 },
    { a: '민법', b: '소득세법', n: 4 },
    { a: '국세기본법', b: '미수집법', n: 1 },
  ],
};
test('law overview includes rare reverse edges, excludes self and unrelated edges, and keeps directions', () => {
  const peers = lawNeighbors(overview, '국세기본법');
  assert.equal(peers.length, 2);
  assert.deepEqual(peers.find((p) => p.node.id === '민법'), { node: overview.nodes[1], forward: true, reverse: true });
  assert.equal(peers.find((p) => p.node.id === '국세징수법').reverse, true);
  const original = JSON.stringify(overview);
  const map = lawOverview(overview, { name: '국세기본법', id: 'anchor' });
  assert.equal(map.nodes.length, 3);
  assert.equal(map.links.length, 3);
  assert.deepEqual([map.nodes[0].x, map.nodes[0].y, map.nodes[0].z], [0, 0, 0]);
  assert.equal(map.mode, 'law-overview');
  assert.ok(map.nodes.every((n) => n.web_jo === ''));
  assert.equal(JSON.stringify(overview), original);
  assert.equal(lawOverview(overview, { name: '연결없는법', id: 'empty' }).nodes.length, 1);
});

const direct = { evidence_id: 'range', direction: 'forward', source_law: '국세기본법', source_ref: '제25조의2', target_law: '민법', target_ref: '제413조', neighbor_jo: '413', status: 'range' };
const broad = { evidence_id: 'broad', direction: 'reverse', source_law: '민법', source_ref: '제1조', target_law: '국세기본법', target_ref: '법령·정의 참조', neighbor_jo: '1', status: 'review' };
test('law pair reads every unique chunk, preserves range members and broad citations, deduplicates repeated rows', async () => {
  const document = { meta: { name: '국세기본법' }, articles: [{ jo: '25의2', detail: { url: 'a', key: 'one' } }, { jo: '28', detail: { url: 'a', key: 'one' } }, { jo: '29', detail: { url: 'a', key: 'two' } }], broad: [broad] };
  const reads = [];
  const rows = await loadLawPair(document, '민법', async (ref) => {
    reads.push(ref);
    return ref.key === 'one' ? { '25의2': { rows: [direct, { ...direct, target_ref: '제414조', neighbor_jo: '414' }] }, '28': { rows: [direct] } } : { '29': { rows: [{ ...direct, target_law: '다른법' }] } };
  });
  assert.equal(reads.length, 2);
  assert.equal(rows.length, 3);
  assert.ok(rows.some((r) => r.status === 'review'));
  assert.ok(rows.some((r) => r.target_ref === '제414조'));
});
test('inline details need no download and unavailable details never masquerade as an empty result', async () => {
  const document = { meta: { name: '국세기본법' }, articles: [{ jo: '25의2' }], details: { '25의2': { rows: [direct] } } };
  assert.equal((await loadLawPair(document, '민법', () => { throw Error('unexpected read'); })).length, 1);
  assert.equal((await loadLawPair(document, '관계없는법', () => {})).length, 0);
  await assert.rejects(loadLawPair({ ...document, details: {} }, '민법', () => {}), /자료가 없습니다/);
  const chunked = { ...document, details: {}, articles: [{ jo: '25의2', detail: { url: 'part' } }] };
  await assert.rejects(loadLawPair(chunked, '민법', async () => { throw Error('offline'); }), /offline/);
  await assert.rejects(loadLawPair(chunked, '민법', async () => ({})), /불러오지 못했습니다/);
});
