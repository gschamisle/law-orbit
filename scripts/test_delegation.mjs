import test from 'node:test';
import assert from 'node:assert/strict';
import {extractDelegations,compareDocuments,reviewDocument,compareInputs,parseArticleInput,supported,snapshot,counterpartCandidates} from '../web/delegation.mjs';
const meta={id:'tax-a',name:'시험법',kind:'법률',domain:'tax',effective:'20260101'};
const article=(jo,text)=>({jo,label:`제${jo.replace('의','조의')}${jo.includes('의')?'':'조'}`,title:'위임',text,deleted:false});
const doc=articles=>({schema:1,meta,articles});
const line='제2조(위임) 조직과 운영에 필요한 사항은 대통령령으로 정한다.';

test('scope covers two domains, acts and decrees; excludes ministerial/admin rules',()=>{
 assert.ok(supported(meta));assert.ok(supported({...meta,kind:'',name:'법인세법'}));assert.ok(supported({...meta,kind:'',name:'법인세법 시행령'}));
 assert.ok(supported({...meta,kind:'대통령령',domain:'public_institutions'}));
 for(const kind of ['훈령','재정경제부령','대통령훈령'])assert.equal(supported({...meta,kind}),false);
 assert.equal(supported({...meta,domain:'fsc'}),false);
});
test('extracts explicit and qualifying delegation phrases with exact source spans',()=>{
 for(const phrase of ['대통령령으로 정한다','대통령령으로 정하는','대통령령이 정하는','대통령령에서 정한','재정경제부령으로 정할 수 있다','총리령으로 정하여야 한다']){
  const a=article('2',`제2조(위임) ${phrase} 사항.`),[r]=extractDelegations(a);
  assert.ok(r,phrase);assert.equal(a.text.slice(r.start,r.end),r.quote);
 }
});
test('negative delegation, deleted provisions and date references do not create candidates',()=>{
 for(const text of ['대통령령으로 정하지 아니한다.','대통령령으로 정할 수 없다.','대통령령 제12345호로 개정되었다.'])assert.deepEqual(extractDelegations(article('2',text)),[]);
 assert.deepEqual(extractDelegations({...article('2',line),deleted:true}),[]);
});
test('keeps paragraph/item identity and more than one instrument',()=>{
 const a=article('2','제2조(위임)\n① 대상은 대통령령으로 정한다.\n② 절차는 다음과 같다.\n1. 서식은 재정경제부령으로 정한다.\n2. 다른 사항\n③ 대통령령으로 정하는 범위에서 재정경제부령으로 정한다.');
 const rows=extractDelegations(a);assert.deepEqual(rows.map(r=>r.ref),['제2조제1항','제2조제2항제1호','제2조제3항','제2조제3항']);
 assert.equal(new Set(rows.map(r=>r.id)).size,4);
});
test('without a baseline, existing delegation is not mislabeled new',()=>{
 assert.equal(compareDocuments(null,doc([article('2',line)]))[0].change,'uncompared');
});
test('new, changed and removed delegation stay distinct',()=>{
 const before=doc([article('2',line)]);
 assert.equal(compareDocuments(doc([]),before)[0].change,'added');
 assert.equal(compareDocuments(before,doc([article('2',line.replace('조직과 운영','조직과 정원'))]))[0].change,'changed');
 assert.equal(compareDocuments(before,doc([]))[0].change,'removed');
});
test('an unchanged delegation still flags changes in another paragraph',()=>{
 const a=article('2',line+'\n② 장관이 결정한다.');
 const b=article('2',line+'\n② 위원회가 결정한다.');
 assert.equal(compareDocuments(doc([a]),doc([b]))[0].change,'context');
});
test('amendment annotations and whitespace alone do not imply substantive change',()=>{
 assert.equal(compareDocuments(doc([article('2',line)]),doc([article('2',line+' <개정 2026. 9. 21.>')]))[0].change,'unchanged');
});
test('moved article is a candidate, preserving the old article number',()=>{
 const result=compareDocuments(doc([article('2',line)]),doc([article('8',line.replace('제2조','제8조'))]));
 assert.equal(result[0].change,'moved');assert.equal(result[0].before.jo,'2');
});
test('same number with different content is changed, not an automatically valid old link',()=>{
 const result=compareDocuments(doc([article('2',line)]),doc([article('2','제2조(위임) 평가 기준은 대통령령으로 정한다.')]));
 assert.equal(result[0].change,'changed');assert.ok(result[0].before.quote.includes('조직'));
});
test('changed provisions without a delegation phrase enter citation recheck',()=>{
 const result=reviewDocument(doc([article('3','제3조(결정) 장관이 결정한다.')]),doc([article('3','제3조(결정) 위원회가 결정한다.')]));
 assert.equal(result[0].kind,'citation-change');assert.equal(result[0].change,'context');
});
test('deleted non-delegating article remains a recheck candidate',()=>{
 const result=reviewDocument(doc([article('3','제3조(결정) 장관이 결정한다.')]),doc([]));
 assert.equal(result[0].change,'removed');assert.equal(result[0].kind,'citation-change');
});
test('cross-domain and wrong-law comparisons are rejected',()=>{
 assert.throws(()=>compareDocuments({...doc([]),meta:{...meta,domain:'public_institutions'}},doc([])));
 assert.throws(()=>compareDocuments({...doc([]),meta:{...meta,name:'다른법'}},doc([])));
});
test('snapshots contain public source fields only',()=>{
 const s=snapshot({...doc([article('2',line)]),secret:'private',meta:{...meta,api_key:'secret'}});
 assert.equal(s.meta.api_key,undefined);assert.equal(s.secret,undefined);
});
const edge=(jo,kind='대통령령')=>({direction:'reverse',source_id:kind,source_law:kind==='대통령령'?'시험법 시행령':'시험법 시행규칙',source_ref:'제5조',source_jo:'5',kind:'article',raw_scope:{scopes:[[[jo,'1','',''],[jo,'1','',''],null]]},source_effective:'20250101',target_effective:'20260101'});
const lookup=new Map([['대통령령',{kind:'대통령령'}],['부령',{kind:'재정경제부령'}]]);
test('counterpart candidates honor paragraph scope and target instrument',()=>{
 const r={jo:'2',ref:'제2조제1항',instrument:'대통령령'};
 const result=counterpartCandidates(r,{'2':{rows:[edge('2'),edge('2','부령'),edge('3')]}},lookup);
 assert.equal(result.rows.length,1);assert.equal(result.status,'references');assert.equal(result.rows[0].version_check,true);
 assert.equal(counterpartCandidates({...r,ref:'제2조제2항'},{'2':{rows:[edge('2')]}},lookup).rows.length,0);
});
test('missing data and no stored citation are not success or confirmed omission',()=>{
 const r={jo:'2',ref:'제2조',instrument:'대통령령'};
 assert.equal(counterpartCandidates(r,{},lookup).status,'unavailable');
 assert.equal(counterpartCandidates(r,{'2':{rows:[]}},lookup).status,'unconfirmed');
 assert.equal(counterpartCandidates(r,{'2':{rows:[],analysis_error:'미분석'}},lookup).status,'unavailable');
});
test('draft comparison requires complete single-article form or explicit new article',()=>{
 assert.throws(()=>parseArticleInput('대통령령으로 정한다.'));
 assert.throws(()=>parseArticleInput(line+'\n제3조(다른 조) 내용'));
 assert.throws(()=>compareInputs('',line,{meta}));
 assert.equal(compareInputs('',line,{meta,newArticle:true}).rows[0].change,'added');
 assert.equal(compareInputs(line,'',{meta,deletedArticle:true}).rows[0].change,'removed');
 assert.throws(()=>compareInputs(line,line,{meta,beforeDate:'2027-01-01',afterDate:'2026-01-01'}));
});
test('paragraphs above twenty and branched items retain their actual references',()=>{
 const rows=extractDelegations(article('2','제2조(위임)\n㉑ 세부 사항\n1의2. 대통령령으로 정한다.'));
 assert.equal(rows[0].ref,'제2조제21항제1호의2');
});
test('future baseline and invalid dates fail instead of inverting amendment direction',()=>{
 assert.throws(()=>compareDocuments({...doc([]),meta:{...meta,effective:'20270101'}},doc([])));
 assert.throws(()=>compareInputs(line,line,{meta,afterDate:'2027-02-30'}));
});
