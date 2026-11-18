import assert from 'node:assert/strict';
import {combineConnections,bridgeLookup,validateBridge,bridgeLabel,bridgeEditions,loadBridgeGroup} from '../web/cross-domain.mjs';
import {loadReading} from '../web/reading.mjs';
import {target,refine,focusMap} from '../web/query.mjs';
const row={cross_domain:true,neighbor_domain:'fsc',neighbor_id:'fi',neighbor_law:'금융규정',neighbor_kind:'article',neighbor_jo:'2',neighbor_ref:'제2조',direction:'forward',source_id:'fx',target_id:'fi',source_ref:'제1조제2항',source_granularity:'block',source_scope:{scopes:[[['1','2','',''],['1','2','',''],-1]]},kind:'article',neighbor_sectors:['banking'],status:'exact'};
const entry={id:'fi',name:'금융규정',domain:'fsc',effective:'20260901',file:{url:'finance-body'}};
const b={kind:'forex-finance-bridge',schema:1,domain:'forex',peer:'fsc',editions:{forex:'20260921',fsc:'20260917'},entries:[entry],laws:{fx:{'1':{rows:[row],suppressed:['old'],resolved_issues:['recovered']}}},broad:{}};
const manifest={domains:[{id:'forex',built_at:'20260921'},{id:'fsc',built_at:'20260917'}]},catalog={built_at:'20260921',laws:[{id:'fx'}]};
assert.equal(validateBridge(b,'forex',manifest,catalog),b);
assert.throws(()=>validateBridge(b,'tax',manifest,catalog));
assert.throws(()=>validateBridge({...b,editions:{forex:'20250101'}},'forex',manifest,catalog));
assert.throws(()=>validateBridge({...b,entries:[{...entry,domain:'tax'}]},'forex',manifest,catalog));
const detail={rows:[],external:[{evidence_id:'old'},{evidence_id:'uncollected'}],issues:[{raw:'recovered'},{raw:'unresolved'}]};
const original=JSON.stringify(detail),combined=combineConnections(detail,[],b,'fx','1');
assert.equal(combined.rows.length,1);assert.equal(combined.external.length,1);assert.equal(combined.issues.length,1);assert.equal(JSON.stringify(detail),original);
assert.equal(combineConnections(detail,[],b,'fx','1',false).external.length,2);
assert.equal(combineConnections(detail,[],null,'fx','1').rows.length,0);
assert.equal(refine(combined.rows,target('제1조제1항')).length,0);
assert.equal(refine(combined.rows,target('제1조제2항')).length,1);
const ownLookup=new Map([['fx',{id:'fx',domain:'forex'}]]),lookup=bridgeLookup(ownLookup,b);
assert.equal(ownLookup.size,1);assert.equal(lookup.size,2);
assert.match(bridgeLabel(row),/금융 \/ 은행/);
const currentDoc={meta:{id:'fx',domain:'forex'},articles:[]},state={law:'fx',reference:'제1조'};
const stateBefore=JSON.stringify(state);
const loaded=await loadReading({id:'fi',jo:'2'},{catalog,lookup,currentDoc,read:async ref=>{
 assert.equal(ref.url,'finance-body');return {meta:entry,articles:[{jo:'2',text:'실제 수집 본문'}]};
}});
assert.equal(loaded.article.text,'실제 수집 본문');assert.equal(currentDoc.meta.id,'fx');assert.equal(JSON.stringify(state),stateBefore);
await assert.rejects(loadReading({id:'unknown',jo:'2'},{catalog,lookup,currentDoc,read:async()=>{throw Error('must not fetch');}}));
await assert.rejects(loadReading({id:'fi',jo:'2'},{catalog,lookup,currentDoc,read:async()=>({meta:{id:'fi',domain:'tax'},articles:[]})}));
const missing=await loadReading({id:'fi',jo:'99'},{catalog,lookup,currentDoc,read:async()=>({meta:entry,articles:[{jo:'2'}]})});
assert.equal(missing.article,undefined);assert.equal(missing.requestedJo,'99');
const map=focusMap([row],{id:'fx',name:'외환규정',label:'외환규정'},target('제1조'),{nodes:[],links:[]},lookup);
assert.equal(map.nodes[0].web_law,'fx');assert.equal(map.nodes[1].web_law,'fi');assert.match(map.nodes[1].status,/분야 밖/);
const annex=focusMap([{...row,annex_unanalyzed:true,neighbor_kind:'annex',neighbor_jo:'별표 4-1'}],{id:'fx',name:'외환규정'},target('제1조'),{},lookup);
assert.equal(annex.nodes[1].web_law,'');
console.log('Cross-domain browser logic checks passed');

// Same independent-reader behavior for procurement/public institutions.
const contractRow={...row,neighbor_domain:'public_institutions',neighbor_sectors:[]};
const contractEntry={...entry,domain:'public_institutions'};
const contract={...b,kind:'procurement-public-bridge',domain:'procurement',peer:'public_institutions',editions:{procurement:'20260919',public_institutions:'20260921'},entries:[contractEntry],laws:{fx:{'1':{rows:[contractRow],suppressed:[],resolved_issues:[]}}}};
const contractManifest={domains:[{id:'procurement',built_at:'20260919'},{id:'public_institutions',built_at:'20260921'}]};
assert.equal(validateBridge(contract,'procurement',contractManifest,{...catalog,built_at:'20260919'}),contract);
assert.match(bridgeLabel(contractRow),/공공기관/);
assert.match(bridgeEditions(contract),/조달·계약 20260919, 공공기관 20260921/);
assert.throws(()=>validateBridge({...contract,kind:'forex-finance-bridge'},'procurement',contractManifest,{...catalog,built_at:'20260919'}));
assert.equal(combineConnections(detail,[],contract,'fx','1',false).rows.length,0);
const isolated=await loadReading({id:'fi',jo:'2'},{catalog,lookup:bridgeLookup(ownLookup,contract),currentDoc,read:async()=>({meta:contractEntry,articles:[{jo:'2',text:'공공기관 수집 본문'}]})});
assert.equal(isolated.article.text,'공공기관 수집 본문');
assert.equal(currentDoc.meta.id,'fx');assert.equal(JSON.stringify(state),stateBefore);

// Multiple peers coexist without replacing an existing procurement/public overlay.
const integEntry={...entry,id:'ig',domain:'integrity',name:'청탁금지법'};
const integRow={...contractRow,neighbor_id:'ig',target_id:'ig',neighbor_domain:'integrity'};
const integ={...contract,kind:'integrity-procurement-bridge',peer:'integrity',editions:{procurement:'20260919',integrity:'20261012'},entries:[integEntry],laws:{fx:{'1':{rows:[integRow],suppressed:['external-report'],resolved_issues:[]}}}};
const multiManifest={domains:[...contractManifest.domains,{id:'integrity',built_at:'20261012'}]};
const multiCatalog={...catalog,built_at:'20260919'};
const group={kind:'domain-bridge-set',schema:1,domain:'procurement',bridges:['old','new']};
const read=async ref=>ref==='old'?contract:integ;
const merged=await loadBridgeGroup(group,'procurement',multiManifest,multiCatalog,read);
assert.equal(merged.laws.fx['1'].rows.length,2);
assert.deepEqual(merged.bridgeRefs,['old','new']);
assert.deepEqual(new Set(merged.peers),new Set(['public_institutions','integrity']));
assert.equal(bridgeLookup(ownLookup,merged).size,3);
assert.match(bridgeLabel(integRow),/청렴·권익/);
assert.equal(combineConnections(detail,[],merged,'fx','1',false).rows.length,0);
assert.equal(merged.laws.fx['1'].rows[0],contractRow);
await assert.rejects(loadBridgeGroup({...group,domain:'tax'},'procurement',multiManifest,multiCatalog,read));
await assert.rejects(loadBridgeGroup({...group,bridges:['new','new']},'procurement',multiManifest,multiCatalog,read));
await assert.rejects(loadBridgeGroup(group,'procurement',multiManifest,multiCatalog,async ref=>ref==='old'?contract:{...integ,editions:{procurement:'20260919',integrity:'20250101'}}));
assert.equal(await loadBridgeGroup(contract,'procurement',multiManifest,multiCatalog,read),contract);

// Added work areas must be supported in both directions, with exact kind and edition guards.
for (const [hub, peer] of [...['forex','fsc','tax','public_institutions','customs','treasury'].map(peer => ['export_finance',peer]), ['forex','tax']]) {
  for (const [own,other] of [[hub,peer],[peer,hub]]) {
    const value={...b,kind:`${hub}-${peer}-bridge`,domain:own,peer:other,
      editions:{[own]:'20260921',[other]:'20260917'},entries:[{...entry,domain:other}],
      laws:{fx:{'1':{rows:[{...row,neighbor_domain:other}],suppressed:[],resolved_issues:[]}}}};
    const m={domains:[{id:own,built_at:'20260921'},{id:other,built_at:'20260917'}]};
    assert.equal(validateBridge(value,own,m,catalog),value);
    assert.throws(()=>validateBridge({...value,kind:'forex-finance-bridge'},own,m,catalog));
    assert.throws(()=>validateBridge({...value,editions:{[own]:'20250101',[other]:'20260917'}},own,m,catalog));
  }
}

// Multiple fields can collect the same official edition of a cited law.
const sharedCitation = {
  ...row, evidence_id: 'same-official-citation', source_jo: '1', source_start: 10, source_end: 30,
  source_url: 'https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=1', source_effective: '20260921',
  target_url: 'https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=2', target_effective: '20260917',
  target_ref: '제2조', target_ref_recorded: '제2조',
};
const broadCitation = {
  ...sharedCitation, evidence_id: 'same-whole-law-citation', direction: 'reverse', broad: true,
  source_id: 'fi', target_id: 'fx', source_jo: '2', source_ref: '제2조',
  source_url: sharedCitation.target_url, source_effective: sharedCitation.target_effective,
  target_url: sharedCitation.source_url, target_effective: sharedCitation.source_effective,
};
const exportFinance = {
  ...b, kind: 'export_finance-fsc-bridge', domain: 'export_finance', peer: 'fsc',
  editions: { export_finance: '20260921', fsc: '20260917' },
  laws: { fx: { '1': { rows: [sharedCitation], suppressed: ['old-fsc'], resolved_issues: [] } } },
  broad: { fx: [broadCitation] },
};
const sharedTax = { ...sharedCitation, target_id: 'tax-law', neighbor_id: 'tax-law', neighbor_domain: 'tax' };
const taxBroad = { ...broadCitation, source_id: 'tax-law', neighbor_id: 'tax-law', neighbor_domain: 'tax' };
const differentCitations = [
  { ...sharedTax, target_effective: '20260901', target_url: 'https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=3' },
  { ...sharedTax, source_start: 40, source_end: 60 },
  { ...sharedTax, neighbor_jo: '3', neighbor_ref: '제3조', target_ref: '제3조' },
  { ...sharedTax, raw_scope: { scopes: [[['2', '1', '', ''], ['2', '1', '', ''], null]] } },
  { ...sharedTax, direction: 'reverse', source_id: 'tax-law', target_id: 'fx' },
];
const exportTax = {
  ...exportFinance, kind: 'export_finance-tax-bridge', peer: 'tax',
  editions: { export_finance: '20260921', tax: '20260918' },
  entries: [{ ...entry, id: 'tax-law', domain: 'tax' }],
  laws: { fx: { '1': { rows: [sharedTax, ...differentCitations], suppressed: ['old-tax'], resolved_issues: [] } } },
  broad: { fx: [taxBroad, { ...taxBroad, source_effective: '20260901' }] },
};
const exportManifest = { domains: [
  { id: 'export_finance', built_at: '20260921' },
  { id: 'fsc', built_at: '20260917' },
  { id: 'tax', built_at: '20260918' },
] };
const exportGroup = await loadBridgeGroup(
  { kind: 'domain-bridge-set', schema: 1, domain: 'export_finance', bridges: ['fsc', 'tax'] },
  'export_finance', exportManifest, catalog, async (ref) => ref === 'fsc' ? exportFinance : exportTax,
);
assert.deepEqual(exportGroup.laws.fx['1'].rows, [sharedCitation, ...differentCitations]);
assert.deepEqual(exportGroup.laws.fx['1'].suppressed, ['old-fsc', 'old-tax']);
assert.deepEqual(exportGroup.broad.fx, [broadCitation, { ...taxBroad, source_effective: '20260901' }]);
assert.deepEqual(exportGroup.entries.map((item) => item.id), ['fi', 'tax-law']);
