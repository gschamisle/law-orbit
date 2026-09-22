// Delegation candidates, not legal conclusions. Uses the existing citation scopes.
import {target,refine,normalize} from './query.mjs';

export const SUPPORTED_DOMAINS=new Set(['tax','public_institutions']);
export const changeLabels={uncompared:'이전 판본 미대조',added:'위임 문구 추가 후보',changed:'위임 문구 변경',context:'조문 변경 · 위임 문구 동일',moved:'조 번호 이동 후보',removed:'위임 문구 삭제 후보',unchanged:'대조 문구 동일'};
const instruction=/(대통령령|총리령|[가-힣]+부령)(?:\s*(?:으로|에서|이|에))\s*(?:정(?:하는|한|한다|하며|하도록|하여야\s*한다|할\s*수\s*있다)|규정(?:하는|한|한다)|위임(?:한다|하는))/g;
const circled='①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚㉛㉜㉝㉞㉟㊱㊲㊳㊴㊵㊶㊷㊸㊹㊺㊻㊼㊽㊾㊿';
const clean=s=>String(s||'').replace(/<\s*(?:개정|신설|전문개정|타법개정)[^>]*>/g,'').replace(/\[\s*(?:본조신설|전문개정|제목개정)[^\]]*\]/g,'');
const comparable=s=>normalize(clean(s));
const body=s=>clean(s).replace(/^\s*제\s*\d+\s*조(?:\s*의\s*\d+)?\s*\([^\n]*?\)\s*/,'');
export function lawLevel(meta){
 if(meta?.kind==='법률')return 'act';if(meta?.kind==='대통령령')return 'decree';
 if(meta?.kind)return '';
 // Older national-tax exports omit kind; use only unambiguous title suffixes.
 if(meta?.name?.endsWith(' 시행령'))return 'decree';
 return /(?:법|법률)$/.test(meta?.name||'')?'act':'';
}
export function supported(meta){return SUPPORTED_DOMAINS.has(meta?.domain)&&!!lawLevel(meta);}
export function versionLabel(meta){return String(meta?.effective||'시행일 미확인').replace(/^(\d{4})(\d{2})(\d{2})$/,'$1-$2-$3');}

export function extractDelegations(article){
 if(article.deleted)return [];
 const text=String(article.text||''),records=[];
 // Keep the complete paragraph/item as evidence; do not infer a subject from keywords.
 const boundaries=[0];
 const marker=/(?:\n[ \t]*)?(?:[①-⑳㉑-㉟㊱-㊿]|(?:제\d+항|\d+(?:의\d+)?\.(?!\d)|[가-하]\.)(?=\s))/g;
 for(const m of text.matchAll(marker))if(m.index>0&&(circled.includes(m[0].trim())||m[0].startsWith('\n')))boundaries.push(m.index);
 boundaries.push(text.length);
 let hang='',ho='',mok='';
 for(let i=0;i<boundaries.length-1;i++){
  const start=boundaries[i],end=boundaries[i+1],raw=text.slice(start,end),trim=raw.trimStart();
  const c=circled.indexOf(trim[0]);const h=trim.match(/^제(\d+)항\s/),n=trim.match(/^(\d+)(?:의(\d+))?\.\s/),k=trim.match(/^([가-하])\.\s/);
  if(c>=0){hang=String(c+1);ho=mok='';}else if(h){hang=h[1];ho=mok='';}else if(n){ho='제'+n[1]+'호'+(n[2]?'의'+n[2]:'');mok='';}else if(k){mok=k[1];}
  const ref=target(article.label||article.jo).label+(hang?'제'+hang+'항':'')+ho+(mok?mok+'목':'');
  const matches=[...raw.matchAll(instruction)];
  for(const instrument of new Set(matches.map(m=>m[1]))){
   const hits=matches.filter(m=>m[1]===instrument);
   records.push({id:`${article.jo}:${start}:${instrument}`,jo:article.jo,ref,title:article.title||'',instrument,
    quote:raw.trim(),start:start+raw.length-raw.trimStart().length,end:start+raw.trimEnd().length,
    phrases:hits.map(m=>m[0]),article_text:text,article_effective:article.effective||''});
  }
 }
 return records;
}

export function snapshot(doc,builtAt=''){
 if(!supported(doc.meta))throw Error('위임사항 점검은 국세·공공기관의 수집 법률·시행령에서 지원합니다.');
 return {schema:1,meta:{id:doc.meta.id,name:doc.meta.name,domain:doc.meta.domain,kind:doc.meta.kind,effective:doc.meta.effective,url:doc.meta.url},built_at:builtAt,
  articles:doc.articles.map(a=>({jo:a.jo,label:a.label,title:a.title,text:a.text,deleted:!!a.deleted,effective:a.effective||''}))};
}
export function validateSnapshot(value,meta){
 if(value?.schema!==1||value.meta?.id!==meta.id||value.meta?.domain!==meta.domain||value.meta?.name!==meta.name||!Array.isArray(value.articles))throw Error('같은 분야·법률의 비교 기준 자료가 아닙니다.');
 const ids=new Set();for(const a of value.articles){if(typeof a.text!=='string'||target(a.label||a.jo).jo!==a.jo||ids.has(a.jo))throw Error('비교 기준의 조문 자료가 올바르지 않습니다.');ids.add(a.jo);}
 return value;
}

export function compareDocuments(before,after){
 if(before)validateSnapshot(before,after.meta);
 const beforeDate=String(before?.meta.effective||'').replaceAll('-',''),afterDate=String(after.meta.effective||'').replaceAll('-','');
 if(/^\d{8}$/.test(beforeDate)&&/^\d{8}$/.test(afterDate)&&beforeDate>afterDate)throw Error('비교 기준의 시행일이 현재 수집본보다 뒤입니다. 판본 순서를 확인해 주세요.');
 const old=before?.articles.flatMap(extractDelegations)||[],next=after.articles.flatMap(extractDelegations),used=new Set();
 const oldByJo=new Map((before?.articles||[]).map(a=>[a.jo,a]));
 const result=next.map(row=>{
  if(!before)return {...row,change:'uncompared'};
  let index=old.findIndex((r,i)=>!used.has(i)&&r.jo===row.jo&&r.instrument===row.instrument&&comparable(body(r.quote))===comparable(body(row.quote)));
  let change='unchanged';
  if(index<0){index=old.findIndex((r,i)=>!used.has(i)&&r.instrument===row.instrument&&comparable(body(r.quote))===comparable(body(row.quote)));if(index>=0)change=old[index].jo!==row.jo?'moved':'changed';}
  if(index<0){index=old.findIndex((r,i)=>!used.has(i)&&r.ref===row.ref&&r.instrument===row.instrument);if(index>=0)change='changed';}
  if(index<0)return {...row,change:'added',previous_article:oldByJo.get(row.jo)||null};
  const prior=old[index];used.add(index);
  if(change==='unchanged'&&comparable(row.article_text)!==comparable(prior.article_text))change='context';
  return {...row,change,before:prior};
 });
 if(before)for(let i=0;i<old.length;i++)if(!used.has(i))result.push({...old[i],change:'removed',before:old[i]});
 return result;
}

// Also review changed parent provisions without an explicit delegation phrase.
export function reviewDocument(before,after){
 const rows=compareDocuments(before,after);if(!before)return rows;
 const represented=new Set(rows.filter(r=>r.change!=='removed').map(r=>r.jo));
 const old=new Map(before.articles.map(a=>[a.jo,a]));
 for(const a of after.articles){
  if(represented.has(a.jo))continue;const prior=old.get(a.jo);
  if(prior&&comparable(prior.text)===comparable(a.text)&&prior.deleted===a.deleted)continue;
  rows.push({id:`citation:${a.jo}`,jo:a.jo,ref:a.label,title:a.title,quote:a.text,article_text:a.text,
   instrument:lawLevel(after.meta)==='act'?'하위법령':'시행규칙',change:prior?'context':'added',kind:'citation-change',
   before:prior?{...prior,ref:prior.label,quote:prior.text}:null});
 }
 for(const a of before.articles)if(!after.articles.some(v=>v.jo===a.jo)&&!rows.some(r=>r.jo===a.jo&&r.change==='removed'))
  rows.push({id:`deleted:${a.jo}`,jo:a.jo,ref:a.label,title:a.title,quote:a.text,article_text:a.text,instrument:lawLevel(after.meta)==='act'?'하위법령':'시행규칙',change:'removed',kind:'citation-change',before:{...a,ref:a.label,quote:a.text}});
 return rows;
}

export function counterpartCandidates(record,details,lookup){
 const source=details?.[record.jo];
 if(!source)return {status:'unavailable',rows:[],issues:[],analysis_error:'이 판본의 인용 자료를 불러오지 못했습니다.'};
 const candidates=refine(source.rows||[],target(record.ref),{direction:'reverse',review:true});
 const rows=candidates.filter(r=>{
  const entry=lookup.get(r.source_id||r.neighbor_id),name=r.source_law||'',kind=entry?.kind||'';
  const decree=kind==='대통령령'||name.endsWith(' 시행령'),rule=kind==='총리령'||kind.endsWith('부령')||name.endsWith(' 시행규칙');
  return record.instrument==='대통령령'?decree:record.instrument==='하위법령'?decree||rule:rule;
 }).map(r=>({...r,version_check:!!r.source_effective&&!!r.target_effective&&r.source_effective!==r.target_effective}));
 const issues=[...(source.issues||[]),...(source.unplaced||[])];
 return {status:source.analysis_error?'unavailable':rows.length?'references':'unconfirmed',rows,issues,analysis_error:source.analysis_error||''};
}

export function parseArticleInput(text,{absent=false}={}){
 if(absent)return null;
 if(text.length>200000)throw Error('조문 한 개의 전체 본문을 입력해 주세요.');
 const heading=text.trim().match(/^제\s*(\d+)\s*조(?:\s*의\s*(\d+))?\s*\(([^\n]+?)\)/);
 if(!heading||!text.trim().slice(heading[0].length).trim())throw Error('제10조(제목)부터 시작하는 조문 전체 본문이 필요합니다. 개정 지시문·발췌문만으로는 비교하지 않습니다.');
 if((text.match(/^\s*제\s*\d+\s*조(?:\s*의\s*\d+)?\s*\(/gm)||[]).length!==1)throw Error('한 번에 조문 한 개씩 비교해 주세요.');
 if(/다음과\s*같이\s*(?:신설|개정)한다|중\s*[“"].*?[”"]\s*(?:을|를)\s*[“"]/.test(text))throw Error('개정 지시문 대신 개정 후 조문 전체를 입력해 주세요.');
 const jo=String(Number(heading[1]))+(heading[2]?'의'+Number(heading[2]):'');
 target(jo);
 return {jo,label:target(jo).label,title:heading[3],text:text.trim(),deleted:false,effective:''};
}

export function compareInputs(beforeText,afterText,{meta,newArticle=false,deletedArticle=false,beforeDate='',afterDate=''}={}){
 if(newArticle&&deletedArticle)throw Error('신설과 삭제를 동시에 선택할 수 없습니다.');
 for(const d of [beforeDate,afterDate])if(d&&(!/^\d{4}-\d{2}-\d{2}$/.test(d)||!Number.isFinite(Date.parse(d))||new Date(d).toISOString().slice(0,10)!==d))throw Error('실제 날짜를 연-월-일 형식으로 입력해 주세요.');
 if(beforeDate&&afterDate&&beforeDate>afterDate)throw Error('개정 후 시행일이 개정 전 시행일보다 빠릅니다.');
 const before=parseArticleInput(beforeText,{absent:newArticle}),after=parseArticleInput(afterText,{absent:deletedArticle});
 const previous={schema:1,meta,articles:before?[before]:[]};
 const current={schema:1,meta,articles:after?[after]:[]};
 return {rows:reviewDocument(previous,current),before,after,beforeDate,afterDate,scope:'user-provided-single-article'};
}
