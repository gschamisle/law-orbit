import test from 'node:test';
import assert from 'node:assert/strict';
import {selectScope,changeCandidates} from '../web/public-scope.mjs';
const rows=[{source_law:'정보공개법',source_ref:'제2조',context:'제2조에 따른 공공기관',target_jo:'4',kind:'indirect',labels:['indirect']},
 {source_law:'계약사무규칙',source_ref:'제2조',context:'공기업 및 준정부기관',target_jo:'5',kind:'scope',labels:['subset']},
 {source_law:'안전평가',source_ref:'제2조',context:'추가 선정',target_jo:'4',kind:'scope',labels:['additional']},
 {source_law:'안전평가',source_ref:'제2조',context:'추가 선정',target_jo:'6',kind:'scope',labels:['additional']}];
test('direct citations and indirect definition paths remain distinct',()=>{assert.equal(selectScope(rows,{indirect:false}).length,3);assert.equal(selectScope(rows,{label:'indirect'}).length,1);});
test('anchor and text filters intersect without mutating input',()=>{assert.deepEqual(selectScope(rows,{anchor:'4',query:'추가'}),[rows[2]]);assert.equal(rows.length,4);});
test('type changes prioritize restricted types and deduplicate provisions',()=>{const r=changeCandidates(rows,{kind:'changed'});assert.equal(r.length,2);assert.equal(r[0].source_law,'계약사무규칙');assert.ok(r.every(v=>v.kind==='scope'));});
