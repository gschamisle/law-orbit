import test from 'node:test';
import assert from 'node:assert/strict';
import {loadReading} from '../web/reading.mjs';
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
