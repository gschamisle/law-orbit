import test from 'node:test';
import assert from 'node:assert/strict';
import {loadReading,scopeHighlights,quoteHighlights,connectionHighlights,evidenceKey,collectReview,reviewHTML,reviewCSV} from '../web/reading.mjs';
const entry={id:'tax-a',name:'법인세법',domain:'tax',region:'',file:'body'};
const doc={meta:entry,articles:[{jo:'32',text:'기준 조문'},{jo:'60',text:'읽을 조문'}]};
const context={catalog:{laws:[entry]},lookup:new Map([[entry.id,entry]]),currentDoc:doc,read:async()=>{throw Error('unexpected network request');}};
test('same-law reading reuses the body and preserves the anchor document',async()=>{
 const before=JSON.stringify(context.catalog),original=JSON.stringify(doc);
 const result=await loadReading({id:entry.id,jo:'60'},context);
 assert.equal(result.article.text,'읽을 조문');assert.equal(JSON.stringify(doc),original);assert.equal(JSON.stringify(context.catalog),before);
 assert.equal(context.currentDoc,doc);
});
test('reading another law fetches its body only, without citation detail expansion',async()=>{
 const other={id:'other',name:'다른 법령',domain:'tax',file:'other-body'};const requests=[];
 const result=await loadReading({id:'other',jo:'1'},{...context,lookup:new Map([['other',other]]),read:async ref=>{requests.push(ref);return {meta:other,articles:[{jo:'1',text:'다른 본문'}]};}});
 assert.equal(result.article.text,'다른 본문');assert.deepEqual(requests,['other-body']);assert.equal(context.currentDoc,doc);
});
test('a missing provision never substitutes the first article',async()=>{
 const result=await loadReading({id:entry.id,jo:'999'},context);assert.equal(result.article,undefined);assert.equal(result.requestedJo,'999');
});
test('a law-level reference asks the reader to select an article',async()=>{
 const result=await loadReading({id:entry.id},context);assert.equal(result.article,null);assert.equal(result.document.articles.length,2);
});
test('a regional citation reads the requested jurisdiction without switching the active catalog',async()=>{
 const regionEntry={id:'region-a-law',name:'같은 이름의 조례',region:'region-a',domain:'local_tax',file:'region-body'};
 const catalog={laws:[],regions:[{id:'region-a',catalog:'catalog-a'},{id:'region-b',catalog:'catalog-b'}]},lookup=new Map(),requests=[];
 const result=await loadReading({id:regionEntry.id,jo:'7',region:'region-a'},{catalog,lookup,currentDoc:doc,read:async ref=>{
 requests.push(ref);if(ref==='catalog-a')return {laws:[regionEntry]};if(ref==='region-body')return {meta:regionEntry,articles:[{jo:'7',text:'해당 지역의 본문'}]};throw Error('wrong jurisdiction');
 }});
 assert.equal(result.article.text,'해당 지역의 본문');assert.equal(lookup.size,0);assert.equal(catalog.laws.length,0);assert.deepEqual(requests,['catalog-a','region-body']);
});
test('uncollected and mismatched bodies fail explicitly',async()=>{
 await assert.rejects(loadReading({id:'missing'},context),/수집 범위/);
 await assert.rejects(loadReading({id:entry.id,jo:'60'},{...context,currentDoc:null,read:async()=>({meta:{id:'wrong',domain:'tax'},articles:[]})}),/일치하지/);
});

const scoped=(a,b=a,axis=null)=>({scopes:[[a,b,axis]],review_reason:''});
const provision='제60조(신고)\n① 첫 항\n1. 첫째 호\n2. 첫 항 둘째 호\n② 둘째 항\n1. 다른 호\n2. 신고 서류\n가. 세부 가목\n나. 세부 나목\n3. 마지막 호\n③ 마지막 항';
test('target highlighting identifies the correct paragraph, item and subitem without matching repeated numbers',()=>{
 const r=scopeHighlights(provision,'60',scoped(['60','2','2','가']));
 assert.equal(r.ranges.length,1);assert.equal(provision.slice(...r.ranges[0]).trim(),'가. 세부 가목');
 const ho=scopeHighlights(provision,'60',scoped(['60','2','2','']));assert.match(provision.slice(...ho.ranges[0]),/^2\. 신고 서류/);assert.doesNotMatch(provision.slice(...ho.ranges[0]),/마지막 호/);
});
test('range and enumerated targets preserve the selected article and range endpoints',()=>{
 const r=scopeHighlights(provision,'60',scoped(['60','1','',''],['60','2','',''],1));assert.equal(r.ranges.length,1);assert.doesNotMatch(provision.slice(...r.ranges[0]),/③/);
 const e=scopeHighlights(provision,'60',{scopes:[[['60','1','1',''],['60','1','1',''],null],[['60','2','3',''],['60','2','3',''],null]]});assert.equal(e.ranges.length,2);
 assert.equal(scopeHighlights(provision,'59',scoped(['60','2','',''])).ranges.length,0);
});
test('unresolved or absent targets never highlight a guessed paragraph',()=>{
 for(const p of [scoped(['60','9','','']),scoped(['60','','2','']),{scopes:scoped(['60','2','','']).scopes,review_reason:'ambiguous'},scoped(['60','2','',''],['60','4','',''],1)])assert.equal(scopeHighlights(provision,'60',p).ranges.length,0);
 assert.equal(scopeHighlights('제1조(목적) 한 문단뿐이다.','1',scoped(['1','1','',''])).ranges.length,0);
 assert.match(scopeHighlights(provision,'60',scoped(['60','','',''])).message,/조 전체/);
});
test('circled paragraphs beyond ten and inserted item numbers are supported',()=>{
 const body='제1조(제목)\n⑪ 열한째\n1의2. 삽입 호\n㉑ 스물한째\n㊱ 서른여섯째';
 assert.match(body.slice(...scopeHighlights(body,'1',scoped(['1','11','1의2',''])).ranges[0]),/삽입 호/);
 assert.equal(scopeHighlights(body,'1',scoped(['1','36','',''])).ranges.length,1);
});
test('source quotes validate Python code point offsets and disambiguate repeated text',()=>{
 const body='★🌠 제1조\n① 제2조에 따른다.\n② 제2조에 따른다.';const raw='제2조',start=Array.from(body.slice(0,body.lastIndexOf(raw))).length;
 const r=quoteHighlights(body,{raw,source_start:start,source_end:start+3});assert.equal(r.ranges[0][0],body.lastIndexOf(raw));
 const context=quoteHighlights(body,{raw,context:'② 제2조에 따른다.'});assert.equal(context.ranges[0][0],body.lastIndexOf(raw));
 assert.equal(quoteHighlights(body,{raw}).ranges.length,0);
 assert.equal(quoteHighlights(body,{raw:'없는 문구',source_start:0,source_end:3}).ranges.length,0);
});
test('source paragraph scope narrows a repeated quote and text guidance remains literal',()=>{
 const body='제1조(목적)\n① 제2조를 준용한다.\n② 제2조를 준용한다.';
 const r=quoteHighlights(body,{raw:'제2조',source_jo:'1',source_scope:scoped(['1','2','',''])});assert.equal(r.ranges[0][0],body.lastIndexOf('제2조'));
 const guidance='[이미지는 공식 원문 확인]\n1. (목적) 「A법」 제2조를 따른다.';
 assert.equal(connectionHighlights(guidance,'',[{direction:'reverse',raw:'「A법」 제2조',source_start:200,source_end:210}]).ranges.length,1);
});
const row={evidence_id:'e1',direction:'forward',source_id:'tax-a',source_law:'법인세법',source_ref:'제32조',target_id:'tax-a',target_law:'법인세법',target_ref:'제60조',neighbor_id:'tax-a',neighbor_law:'법인세법',neighbor_ref:'제60조',neighbor_kind:'article',neighbor_jo:'60',raw:'제60조',source_effective:'20260701',target_effective:'20260701',source_url:'https://www.law.go.kr/a',target_url:'https://www.law.go.kr/b'};
const anchor={name:'법인세법',reference:'제32조',body:'기준 조문',effective:'20260701',builtAt:'20260918',version:'fixture-v1',createdAt:'2026-09-28',domainTitle:'국세',filters:'인용 + 역인용',editions:'국세 20260918',url:'https://www.law.go.kr/a'};
test('review selection exports only selected bodies, retaining unresolved notes and the anchor',async()=>{
 const packet=await collectReview({anchor,rows:[row],unresolved:[{raw:'어떤 법',reason:'미수집'}],context});
 assert.equal(packet.items.length,1);assert.equal(packet.items[0].body,'읽을 조문');assert.equal(packet.anchor.body,'기준 조문');assert.equal(packet.unresolved.length,1);assert.equal(context.currentDoc,doc);
 assert.notEqual(evidenceKey(row),evidenceKey({...row,direction:'reverse'}));
});
test('an external flag on a collected graph edge does not suppress its collected body',async()=>{
 const packet=await collectReview({anchor,rows:[{...row,external:true}],context});assert.equal(packet.items[0].body,'읽을 조문');
});
test('export explicitly distinguishes uncollected, missing, broad and failed bodies',async()=>{
 const p=await collectReview({anchor,rows:[{...row,export_uncollected:true},{...row,neighbor_jo:'999'},{...row,neighbor_kind:'law'},{...row,neighbor_id:'missing'}],context});
 assert.ok(p.items.every(i=>!i.body));assert.match(p.items[0].bodyStatus,/미수집/);assert.match(p.items[1].bodyStatus,/해당 조문/);assert.match(p.items[2].bodyStatus,/법령 전체/);assert.match(p.items[3].bodyStatus,/실패/);
});
test('version mismatch remains a visible export failure and cancellation returns no packet',async()=>{
 const bad={...entry,effective:'20260101'};const changed={...doc,meta:{...bad,effective:'20250101'}};
 const p=await collectReview({anchor,rows:[row],context:{...context,lookup:new Map([[bad.id,bad]]),currentDoc:changed}});assert.match(p.items[0].bodyStatus,/판본/);assert.equal(p.items[0].body,'');
 await assert.rejects(collectReview({anchor,rows:[row],context,cancelled:()=>true}),/취소/);
});
test('HTML preserves literal law text, safe sources and provenance without executing source markup',async()=>{
 const packet=await collectReview({anchor:{...anchor,body:'<script>alert(1)</script>'},rows:[{...row,raw:'<img src=x onerror=alert(1)>',source_url:'javascript:alert(1)',target_effective:'<svg/onload=1>'}],unresolved:[{raw:'<b>원문</b>',reason:'확인'}],context});
 const html=reviewHTML(packet,{'400':'YWJj','700':'YWJj'});
 assert.ok(html.includes('&lt;script&gt;'));assert.ok(!html.includes('<script>'));assert.ok(!html.includes('<img'));assert.ok(!html.includes('<svg'));assert.ok(!html.includes('href="javascript:'));assert.ok(html.includes('fixture-v1'));assert.ok(html.includes('data:font/woff2;base64,YWJj'));assert.ok(html.includes('미수집·미해석 확인 목록 1건'));assert.ok(html.includes('읽을 조문'));
});
test('CSV escapes formulas, multiline quotes and has a UTF-8 BOM for spreadsheet readers',async()=>{
 const p=await collectReview({anchor,rows:[{...row,raw:'=HYPERLINK("x")',context:'두 줄\n"원문"'}],context});const csv=reviewCSV(p);
 assert.ok(csv.startsWith('\ufeff'));assert.ok(csv.includes("\"'=HYPERLINK(\"\"x\"\")\""));assert.ok(csv.includes('"두 줄\n""원문"""'));assert.ok(csv.includes('fixture-v1'));
});
