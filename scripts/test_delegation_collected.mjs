import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import zlib from 'node:zlib';
import {extractDelegations,reviewDocument,snapshot,counterpartCandidates,supported} from '../web/delegation.mjs';
const base=process.env.LAW_ORBIT_TEST_SITE||'output/static-delegation-preview';
const read=ref=>JSON.parse(zlib.gunzipSync(fs.readFileSync(base+'/'+ref.url)));
const manifest=JSON.parse(fs.readFileSync(base+'/manifest.json'));
for(const [id,name] of [['tax','법인세법'],['tax','법인세법 시행령'],['public_institutions','공공기관의 운영에 관한 법률'],['public_institutions','공공기관의 운영에 관한 법률 시행령']]){
 test('collected source and counterpart evidence: '+name,()=>{
  const catalog=read(manifest.domains.find(d=>d.id===id).catalog),entry=catalog.laws.find(d=>d.name===name),doc=read(entry.file);
  assert.ok(supported(doc.meta));const records=doc.articles.flatMap(extractDelegations);assert.ok(records.length>0);
  const groups={...doc.details};for(const part of entry.parts)Object.assign(groups,read(part));
  const lookup=new Map(catalog.laws.map(d=>[d.id,d]));let related=0;
  for(const r of records){assert.equal(doc.articles.find(a=>a.jo===r.jo).text.slice(r.start,r.end),r.quote);const c=counterpartCandidates(r,groups,lookup);related+=c.rows.length;}
  assert.ok(related>0,'At least one real lower-regulation reference is available');
  const baseline=read(catalog.delegation_review.baselines[entry.id].file);
  assert.ok(reviewDocument(baseline,snapshot(doc)).every(r=>r.change==='unchanged'));
 });
}
test('public shell has no private draft input or local bridge',()=>{
 const html=fs.readFileSync(base+'/index.html','utf8');assert.match(html,/followup-open/);assert.doesNotMatch(html,/<textarea|delegation_review_bridge|beforeText|afterText/);
 assert.equal(fs.existsSync(base+'/delegation_review_bridge.mjs'),false);
});
