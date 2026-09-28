import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {reviewDocument,counterpartCandidates} from '../web/delegation.mjs';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const bundle=path.join(root,'output/tax-delegation-history-20260929');
const read=relative=>JSON.parse(fs.readFileSync(path.join(bundle,relative),'utf8'));
const manifest=read('manifest.json');
const expected=new Map([
 ['법인세법',{articles:['90'],counts:{context:1}}],
 ['소득세법',{articles:['57의2','129'],counts:{context:10,added:2,removed:1}}],
 ['조세특례제한법',{articles:['7','118'],counts:{context:8}}],
]);

for(const law of manifest.laws){
 test('actual prior effective edition: '+law.name,()=>{
  const before=read(law.baseline.path),after=read(law.current_snapshot.path);
  const changed=reviewDocument(before,after).filter(row=>row.change!=='unchanged');
  const counts={};for(const row of changed)counts[row.change]=(counts[row.change]||0)+1;
  assert.deepEqual(counts,expected.get(law.name).counts);
  assert.deepEqual([...new Set(changed.map(row=>row.jo))],expected.get(law.name).articles);
  assert.equal(before.evidence_availability.reverse_citations,'not-collected');
  for(const row of changed)assert.equal(counterpartCandidates(row,before.details,new Map()).status,'unavailable');
 });
}

test('real income-tax formula delegation added at Article 129(8)(2)',()=>{
 const law=manifest.laws.find(law=>law.name==='소득세법');
 const rows=reviewDocument(read(law.baseline.path),read(law.current_snapshot.path));
 const formula=rows.find(row=>row.ref==='제129조제8항제2호');
 assert.equal(formula.change,'added');
 assert.match(formula.quote,/간접투자외국법인세액을 세후기준가격을 고려하여 대통령령으로 정하는/);
 const expanded=rows.find(row=>row.ref==='제129조제11항');
 assert.equal(expanded.change,'added');
 assert.match(expanded.quote,/제5항부터 제10항까지/);
 const prior=rows.find(row=>row.ref==='제129조제8항'&&row.change==='removed');
 assert.match(prior.quote,/제5항부터 제7항까지/);
});

test('changed article without delegation and unchanged delegation within changed context remain reviewable',()=>{
 const corporate=manifest.laws.find(law=>law.name==='법인세법');
 const corpRows=reviewDocument(read(corporate.baseline.path),read(corporate.current_snapshot.path));
 const a90=corpRows.find(row=>row.jo==='90');
 assert.equal(a90.kind,'citation-change');
 assert.match(a90.quote,/제1호의2ㆍ제3호ㆍ제4호/);
 assert.match(a90.before.quote,/납부기한의 다음 날/);
 const special=manifest.laws.find(law=>law.name==='조세특례제한법');
 const rows=reviewDocument(read(special.baseline.path),read(special.current_snapshot.path));
 const a7=rows.find(row=>row.jo==='7'&&row.change==='context');
 assert.match(a7.article_text,/수소발전사업/);
 assert.doesNotMatch(a7.before.article_text,/수소발전사업/);
 assert.equal(a7.quote,a7.before.quote);
});
