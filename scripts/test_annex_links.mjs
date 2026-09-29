import test from 'node:test';
import assert from 'node:assert/strict';
import {annexReference,annexSources,appendAnnexSources} from '../web/annex-links.mjs';
import {renderAnnex} from '../web/annex.mjs';
import {safeLink} from '../web/query.mjs';

const owner='https://www.law.go.kr/법령/검증법시행규칙';
const source='https://www.law.go.kr/법령/다른법';
const files=['https://www.law.go.kr/LSW/flDownload.do?flSeq=123','https://www.law.go.kr/LSW/flDownload.do?flSeq=456'];
const forward={direction:'forward',neighbor_kind:'annex',neighbor_id:'rule',neighbor_law:'검증법 시행규칙',neighbor_jo:'별표 1',source_url:source,target_url:owner,annex_urls:files,annex_analyzed:false};
const documentFixture={meta:{id:'rule',name:'검증법 시행규칙',url:owner},articles:[],annexes:[{ref:'별표 1',urls:files,analysis:{text:'검증 본문'}}]};

test('forward annex links open supplied originals without claiming a readable body',()=>{
 const result=annexReference(forward);
 assert.deepEqual(result.originals,files);
 assert.equal(result.ownerUrl,safeLink(owner));
 assert.equal(result.status,'not-analyzed');
 assert.equal(result.analyzed,false);
 assert.equal(result.ref,'별표 1');
});

test('reverse annex title evidence uses the source owner and keeps its provenance',()=>{
 const row={...forward,direction:'reverse',target_kind:'article',source_jo:'별표 1',source_url:owner,target_url:source,annex_urls:[],source_granularity:'annex'};
 const result=annexReference(row);
 assert.equal(result.ownerUrl,safeLink(owner));
 assert.notEqual(result.ownerUrl,safeLink(source));
 assert.equal(result.titleReference,true);
 assert.equal(annexReference({...row,source_layer:'annex-body'}).titleReference,false);
});

test('uncollected annexes retain safe attachment links with no invented body access',()=>{
 const result=annexReference({target_kind:'annex',target_law:'외부법',target_ref:'별표 9',target_url:owner,annex_urls:files},{external:true});
 assert.equal(result.law,'외부법');
 assert.equal(result.ref,'별표 9');
 assert.deepEqual(result.originals,files);
 assert.equal(result.analyzed,false);
 assert.equal(result.id,undefined);
 assert.equal(annexReference({target_kind:'article',annex_urls:files},{external:true}),null);
 assert.equal(annexReference({...forward,neighbor_kind:'article',target_kind:'annex'}),null);
});

test('verified flags retain annex body reading without treating title evidence as analysis',()=>{
 assert.equal(annexReference({...forward,annex_analyzed:true}).analyzed,true);
 assert.equal(annexReference({...forward,annex_analyzed:undefined,source_granularity:'annex'}).analyzed,false);
 assert.equal(annexReference({...forward,annex_analyzed:true},{currentDoc:{...documentFixture,annexes:[]}}).analyzed,false);
 assert.equal(annexReference({...forward,annex_analyzed:true},{currentDoc:{meta:documentFixture.meta}}).analyzed,false);
});

test('legacy rows use only the exact loaded owner and annex as evidence of a body',()=>{
 const legacy={...forward,annex_analyzed:undefined,annex_urls:undefined};
 const result=annexReference(legacy,{currentDoc:documentFixture});
 assert.equal(result.analyzed,true);
 assert.deepEqual(result.originals,files);
 assert.equal(annexReference({...legacy,neighbor_id:'other'},{currentDoc:documentFixture}).analyzed,false);
 assert.equal(annexReference({...legacy,neighbor_law:'다른 법'},{currentDoc:documentFixture}).analyzed,false);
 assert.equal(annexReference({...legacy,neighbor_jo:'별표 2'},{currentDoc:documentFixture}).analyzed,false);
 assert.equal(annexReference(forward,{currentDoc:documentFixture}).analyzed,false);
});

test('unsafe and duplicate addresses are removed without guessing formats',()=>{
 assert.deepEqual(annexSources([...files,files[0],'javascript:alert(1)','data:text/plain,x','https://name:password@www.law.go.kr/file'],owner).originals,files);
 assert.deepEqual(annexSources(files[0],'javascript:bad'),{originals:[],ownerUrl:''});
 const value=annexSources(['https://www.law.go.kr/example.pdf','https://www.law.go.kr/example.hwp'],owner);
 const container=new Element('div');appendAnnexSources(container,value,{text,link});
 assert.deepEqual(container.children.map(c=>c.textContent),['별표 원본 1 ↗','별표 원본 2 ↗']);
 assert.ok(container.children.every(c=>!c.download&&c.target==='_blank'&&c.rel==='noopener noreferrer'));
});

class Element{
 constructor(tag,value=''){this.tag=tag;this.textContent=value;this.children=[];}
 append(...children){this.children.push(...children);}
 prepend(...children){this.children.unshift(...children);}
 scrollIntoView(){}
}
const text=(tag,value='',cls='')=>Object.assign(new Element(tag,value),{className:cls});
const link=(url,label)=>Object.assign(text('a',label),{href:safeLink(url),target:'_blank',rel:'noopener noreferrer'});
const flatten=element=>[element,...element.children.flatMap(flatten)];
const contents=element=>flatten(element).map(e=>e.textContent).join(' ');
function inDocument(callback){
 const original=globalThis.document;
 globalThis.document={createElement:tag=>text(tag),createTextNode:value=>text('#text',value)};
 try{return callback();}finally{if(original===undefined)delete globalThis.document;else globalThis.document=original;}
}

test('missing addresses show an explicit notice and the owning law, not the other citation endpoint',()=>{
 const container=text('div');
 appendAnnexSources(container,annexReference({...forward,direction:'reverse',source_url:owner,target_url:source,annex_urls:[]}),{text,link});
 assert.match(contents(container),/첨부파일 주소 미확보/);
 const links=flatten(container).filter(e=>e.tag==='a');
 assert.deepEqual(links.map(e=>e.href),[safeLink(owner)]);
 assert.match(links[0].textContent,/별표 소유 법령/);
 const unknown=text('div');appendAnnexSources(unknown,annexSources([]),{text,link});
 assert.match(contents(unknown),/공식 출처를 확인/);
 assert.equal(flatten(unknown).filter(e=>e.tag==='a').length,0);
});

test('unanalysed annex reader exposes originals and never fabricates body or read actions',()=>inDocument(()=>{
 const body=text('div'),reads=[];
 renderAnnex(body,{ref:'별표 2',title:'시설',urls:files},[],{text,link,read:(...args)=>reads.push(args),ownerUrl:owner});
 assert.deepEqual(flatten(body).filter(e=>e.tag==='a').map(e=>e.href),files);
 assert.match(contents(body),/본문은 미분석/);
 assert.equal(flatten(body).filter(e=>e.tag==='button').length,0);
 assert.deepEqual(reads,[]);
 const missing=text('div');renderAnnex(missing,{ref:'별표 3',title:'미확보',urls:[]},[],{text,link,read:()=>{},ownerUrl:owner});
 assert.match(contents(missing),/첨부파일 주소 미확보/);
 assert.equal(flatten(missing).find(e=>e.tag==='a').href,safeLink(owner));
}));

test('verified annex body and its article links survive alongside external annex originals',()=>inDocument(()=>{
 const raw='법 제43조제1항',value=raw+'을 따른다.',annex={ref:'별표 5',title:'인력 기준',urls:files,
  analysis:{text:value+'\n',units:[{locator:'1행 1열',start:0,text:value}]},
  connections:[{target_law:'의료법',target_ref:'제43조제1항',neighbor_kind:'article',neighbor_id:'law',neighbor_jo:'43',context:raw},
   {target_law:'외부법',target_ref:'별표 7',target_kind:'annex',neighbor_kind:'annex',external:true,annex_urls:files,target_url:source,context:'외부 별표'}]};
 const body=text('div'),reads=[];
 renderAnnex(body,annex,[{source_layer:'annex-body',source_jo:'별표 5',direction:'reverse',raw,source_start:0,source_end:raw.length}],{text,link,read:(...args)=>reads.push(args),ownerUrl:owner});
 assert.match(contents(body),/별표 원본 1/);
 assert.equal(flatten(body).filter(e=>e.tag==='mark')[0].textContent,raw);
 assert.match(contents(body),/인용 조문 본문 보기/);
 assert.equal(flatten(body).filter(e=>e.tag==='a'&&e.href===files[0]).length,2);
 assert.deepEqual(reads,[]);
 flatten(body).find(e=>e.tag==='button'&&e.textContent==='인용 조문 본문 보기').onclick();
 assert.deepEqual(reads[0].slice(0,3),['law','43','']);
}));
