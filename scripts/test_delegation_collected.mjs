import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import zlib from 'node:zlib';
import {createHash} from 'node:crypto';
import {extractDelegations,reviewDocument,snapshot,counterpartCandidates,supported} from '../web/delegation.mjs';
const base=process.env.LAW_ORBIT_TEST_SITE||'output/static-delegation-preview';
const manifest=JSON.parse(fs.readFileSync(base+'/manifest.json'));
const packs=new Map();
const read=ref=>{
 let raw;
 if(fs.existsSync(base+'/'+ref.url))raw=fs.readFileSync(base+'/'+ref.url);
 else{
  const packed=manifest.data_packs?.buckets[ref.sha256.slice(0,2)];assert.ok(packed,'Missing packed asset');
  if(!packs.has(packed.url))packs.set(packed.url,read(packed));
  raw=Buffer.from(packs.get(packed.url).entries[ref.sha256],'base64');
 }
 assert.equal(raw.length,ref.bytes);assert.equal(createHash('sha256').update(raw).digest('hex'),ref.sha256);
 return JSON.parse(zlib.gunzipSync(raw));
};
const historicalCases=new Map([
 ['법인세법',['20260102','20260701',['90']]],
 ['소득세법',['20260421','20260701',['57의2','129']]],
 ['조세특례제한법',['20260701','20260918',['7','118']]],
]);
for(const [id,name] of [['tax','법인세법'],['tax','소득세법'],['tax','조세특례제한법'],['tax','법인세법 시행령'],['public_institutions','공공기관의 운영에 관한 법률'],['public_institutions','공공기관의 운영에 관한 법률 시행령']]){
 test('collected source and counterpart evidence: '+name,()=>{
  const catalog=read(manifest.domains.find(d=>d.id===id).catalog),entry=catalog.laws.find(d=>d.name===name),doc=read(entry.file);
  assert.ok(supported(doc.meta));const records=doc.articles.flatMap(extractDelegations);assert.ok(records.length>0);
  const groups={...doc.details};for(const part of entry.parts)Object.assign(groups,read(part));
  const lookup=new Map(catalog.laws.map(d=>[d.id,d]));let related=0;
  for(const r of records){assert.equal(doc.articles.find(a=>a.jo===r.jo).text.slice(r.start,r.end),r.quote);const c=counterpartCandidates(r,groups,lookup);related+=c.rows.length;}
  assert.ok(related>0,'At least one real lower-regulation reference is available');
  const saved=catalog.delegation_review.baselines[entry.id],baseline=read(saved.file);
  const comparison=reviewDocument(baseline,snapshot(doc));
  if(saved.mode==='initial')assert.ok(comparison.every(r=>r.change==='unchanged'));
  else{
   assert.equal(saved.mode,'previous-version');assert.ok(baseline.meta.effective<entry.effective);
   assert.ok(comparison.every(r=>r.change!=='uncompared'));
   // This reviewed historical pair has a real change; do not silently turn it
   // back into a current/current comparison when packaging the public site.
   const known=historicalCases.get(name);
   if(known&&baseline.meta.effective===known[0]&&entry.effective===known[1]){
    assert.deepEqual([...new Set(comparison.filter(r=>r.change!=='unchanged').map(r=>r.jo))],known[2]);
    assert.equal(baseline.evidence_availability.reverse_citations,'not-collected');assert.deepEqual(baseline.details,{});
   }
  }
 });
}
test('public shell has no private draft input or local bridge',()=>{
 const html=fs.readFileSync(base+'/index.html','utf8');assert.match(html,/followup-open/);assert.doesNotMatch(html,/delegation_review_bridge|beforeText|afterText|type=["']file["']/);
 // Public error reporting has one deliberately bounded text field. It is not
 // a private draft upload/comparison form.
 const fields=[...html.matchAll(/<textarea\b[^>]*>/g)].map(m=>m[0]);
 assert.equal(fields.length,1);assert.match(fields[0],/id="feedback-description"/);assert.match(fields[0],/maxlength="1200"/);
 assert.equal(fs.existsSync(base+'/delegation_review_bridge.mjs'),false);
});
