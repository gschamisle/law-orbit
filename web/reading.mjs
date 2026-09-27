import {classify,safeLink} from './query.mjs';
// Read a related provision without replacing the active galaxy/catalog.
export async function loadReading({id,jo='',region=''}, {catalog,lookup,currentDoc,read}) {
 let entry=lookup.get(id);
 if(!entry&&region){
  const place=catalog.regions?.find(r=>r.id===region);
  if(place?.catalog){const local=await read(place.catalog);entry=local.laws.find(d=>d.id===id&&d.region===region);}
 }
 if(!entry)throw Error('이 연결 대상의 본문은 현재 수집 범위에 없습니다. 인용 근거의 공식 원문 링크를 확인해 주세요.');
 const document=currentDoc?.meta.id===id?currentDoc:await read(entry.file);
 if(document.meta.id!==entry.id||document.meta.domain!==entry.domain)throw Error('본문 자료의 법령 정보가 일치하지 않습니다.');
 if(entry.effective&&document.meta.effective!==entry.effective)throw Error('연결 자료와 본문의 시행 판본이 다릅니다. 새 판본을 확인해 주세요.');
 return {entry,document,article:jo?document.articles.find(a=>a.jo===jo):null,requestedJo:jo};
}

// Offsets from the Python collector count Unicode code points, not UTF-16 units.
function utf16(text,index){return Array.from(text).slice(0,index).join('').length;}
function occurrences(text,needle){const found=[];if(!needle)return found;let i=0;while((i=text.indexOf(needle,i))>=0){found.push([i,i+needle.length]);i+=needle.length;}return found;}
function outline(body,jo){
 const points=[],path=[jo,'','',''];
 const pattern=/^[ \t]*(?:([①-⑳㉑-㉟㊱-㊿])|제(\d+)항(?=[\s(])|(\d+(?:의\d+)?)\.(?=\s)|([가-하])\.(?=\s))/gm;
 for(const m of body.matchAll(pattern)){
  const code=m[1]?.codePointAt(0),n=code?(code<=0x2473?code-0x2460+1:code<=0x325f?code-0x3251+21:code-0x32b1+36):0;
  const level=m[1]||m[2]?1:m[3]?2:3;
  path[level]=String(n||m[2]||m[3]||m[4]);for(let i=level+1;i<4;i++)path[i]='';
  points.push({start:m.index,end:body.length,level,path:[...path]});
 }
 for(let i=0;i<points.length;i++){const next=points.slice(i+1).find(p=>p.level<=points[i].level);if(next)points[i].end=next.start;}
 return points;
}
function mergeRanges(ranges){const out=[];for(const r of ranges.sort((a,b)=>a[0]-b[0])){const last=out.at(-1);if(last&&r[0]<=last[1])last[1]=Math.max(last[1],r[1]);else out.push([...r]);}return out;}
export function scopeHighlights(body,jo,parsed){
 if(!parsed?.scopes?.length||parsed.review_reason)return {ranges:[],message:'인용 범위를 확정하지 못해 본문 전체를 표시합니다.'};
 const ranges=[],points=outline(body,jo);let missing=0,whole=false;
 for(const s of parsed.scopes){
  const depth=Math.max(...s[0].map((v,i)=>v?i:0),...s[1].map((v,i)=>v?i:0));
  if(depth===0){whole=true;continue;}
  if(s[0][0]!==jo||s[1][0]!==jo){missing++;continue;}
  const matches=points.filter(p=>p.level===depth&&['exact','range'].includes(classify({scopes:[s]},{path:p.path})));
  // Repeated numbers without their parent paragraph are not a unique location.
  const parents=new Set(matches.map(p=>p.path.slice(0,depth).join('|')));
  const ambiguous=parents.size>1&&s[0].slice(1,depth).some(v=>!v);
  if(!matches.length||ambiguous){missing++;continue;}
  if(s[2]!=null){const axis=s[2];if(!matches.some(p=>p.path[axis]===s[0][axis])||!matches.some(p=>p.path[axis]===s[1][axis])){missing++;continue;}}
  ranges.push(...matches.map(p=>[p.start,p.end]));
 }
 return {ranges:mergeRanges(ranges),message:missing?'일부 인용 범위의 위치를 확인하지 못했습니다. 확인된 위치만 강조합니다.':whole?(ranges.length?'조 전체 인용과 세부 범위 인용이 함께 있습니다. 세부 인용 위치를 강조했습니다.':'조 전체를 인용합니다. 항·호를 특정하지 않습니다.'):'인용 대상 항·호·목을 강조했습니다.'};
}
export function quoteHighlights(body,row){
 const raw=row.raw||row.cite_raw||'',hits=occurrences(body,raw);
 if(Number.isInteger(row.source_start)&&Number.isInteger(row.source_end)&&row.source_start>=0&&row.source_end>=row.source_start){
  const a=utf16(body,row.source_start),b=utf16(body,row.source_end);
  if(raw&&body.slice(a,b)===raw)return {ranges:[[a,b]],message:'이 조문에서 실제로 인용한 문구입니다.'};
 }
 if(hits.length===1)return {ranges:hits,message:'이 조문에서 실제로 인용한 문구입니다.'};
 if(hits.length>1){
  const contexts=occurrences(body,row.context||'');
  let narrowed=contexts.length===1?hits.filter(([a,b])=>a>=contexts[0][0]&&b<=contexts[0][1]):[];
  if(narrowed.length!==1&&row.source_jo){const scopes=scopeHighlights(body,row.source_jo,row.source_scope).ranges;narrowed=hits.filter(([a,b])=>scopes.some(([x,y])=>a>=x&&b<=y));}
  if(narrowed.length===1)return {ranges:narrowed,message:'주변 문맥과 대조한 인용 문구입니다.'};
 }
 return {ranges:[],message:hits.length?'같은 인용 문구가 여러 곳에 있어 위치를 특정하지 않았습니다.':'저장된 인용 문구의 위치를 본문에서 확인하지 못했습니다.'};
}
export function connectionHighlights(body,jo,rows=[]){
 const results=rows.map(row=>row.direction==='reverse'?quoteHighlights(body,row):jo?scopeHighlights(body,jo,row.raw_scope):{ranges:[],message:'법령 전체 참조입니다. 특정 조문·문단을 강조하지 않습니다.'});
 return {ranges:mergeRanges(results.flatMap(r=>r.ranges)),message:[...new Set(results.map(r=>r.message))].join(' ')};
}
export function evidenceKey(r){return JSON.stringify([r.evidence_id||r.raw||r.cite_raw,r.direction,r.source_id||r.source_law,r.source_ref,r.target_id||r.target_law,r.target_ref_recorded||r.target_ref,r.neighbor_jo,r.region,r.external]);}
export function plainBody(document){
 const raw=document.unstructured_text||'',hasImages=/<\/?img\b[^>]*>/i.test(raw);
 return (hasImages?'[이미지·도표는 공식 원문에서 확인하세요.]\n\n':'')+raw.replace(/<\/?img\b[^>]*>/gi,'').replace(/\n[ \t]*\n(?:[ \t]*\n)+/g,'\n\n').trim();
}
const LIMITATION='수집 판본의 명시적 인용에 근거한 검토자료입니다. 연결이 개정 의무를 뜻하지 않으며, 연결이 없다고 영향이 없다고 판단할 수 없습니다. 미수집·미분석 자료, 별표·이미지와 최신 판본은 공식 원문을 확인하세요.';
export async function collectReview({anchor,rows,unresolved=[],context,cancelled=()=>false,progress=()=>{}}){
 const cache=new Map(),loadedContext={...context,read:ref=>{const key=JSON.stringify(ref);if(!cache.has(key))cache.set(key,context.read(ref));return cache.get(key);}},items=[];
 for(const row of rows){
  if(cancelled())throw Error('검토자료 준비가 취소되었습니다.');
  let body='',bodyStatus='',effective='',url='';
  if(row.export_uncollected||!row.neighbor_id)bodyStatus='미수집 또는 조문 연결 미분석 · 본문을 포함하지 않았습니다.';
  else if(row.neighbor_kind==='annex')bodyStatus='별표 본문 미분석 · 공식 원문을 확인하세요.';
  else try{
   const result=await loadReading({id:row.neighbor_id,jo:row.neighbor_kind==='article'?row.neighbor_jo:'',region:row.region||''},loadedContext);
   effective=result.article?.effective||result.entry.effective||'';url=result.entry.url||'';
   if(result.article){body=result.article.text;bodyStatus=result.article.deleted?'수집 판본의 삭제 조문':'수집 조문 전체';}
   else if(row.neighbor_kind==='article')bodyStatus='수집 판본에 해당 조문 본문이 없습니다.';
   else if(!result.document.articles.length){body=plainBody(result.document);bodyStatus=body?'수집 문서 본문 · 문단 내부 참조·이미지·표는 미분석':'본문 미확보';}
   else bodyStatus='법령 전체 참조 · 특정 조문 본문을 포함하지 않았습니다.';
  }catch(err){bodyStatus='본문 불러오기 실패: '+(err.message||'자료 확인 필요');}
  items.push({row:{...row},body,bodyStatus,effective,url});progress(items.length,rows.length);
 }
 if(cancelled())throw Error('검토자료 준비가 취소되었습니다.');
 return {anchor,items,unresolved,limitation:LIMITATION};
}
function escape(value){return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function official(url,label){const href=safeLink(url);return href?`<a href="${escape(href)}" target="_blank" rel="noopener noreferrer">${escape(label)}</a>`:'';}
function date(value){value=String(value??'');return /^\d{8}$/.test(value)?`${value.slice(0,4)}-${value.slice(4,6)}-${value.slice(6)}`:(value||'확인 필요');}
export function reviewHTML(packet,fonts={}){
 const a=packet.anchor;
 const fontCSS=Object.entries(fonts).filter(([weight,b64])=>['400','700'].includes(weight)&&/^[A-Za-z0-9+/=]+$/.test(b64)).map(([weight,b64])=>`@font-face{font-family:MaruBuri;font-weight:${weight};src:url(data:font/woff2;base64,${b64}) format('woff2')}`).join('');
 const items=packet.items.map(({row:r,body,bodyStatus,effective,url},i)=>`<article><p class="tag">${i+1}. ${r.direction==='reverse'?'역인용':'직접 인용'}${r.cross_domain?' · 분야 밖 관련 조문':''}</p><h2>${escape(r.neighbor_law||r.target_law)} ${escape(r.neighbor_ref||r.target_ref||'')}</h2><p>${escape(r.source_law)} ${escape(r.source_ref||r.source_jo)} → ${escape(r.target_law)} ${escape(r.target_ref_recorded||r.target_ref)}</p><blockquote>${escape(r.raw||r.cite_raw)}</blockquote><p class="meta">${escape(r.precision||r.status)} · ${escape(r.reason)}<br>출처 시행 ${escape(date(r.source_effective))} · 대상 시행 ${escape(date(r.target_effective))}<br>${official(r.source_url,'출처 원문')} ${official(r.target_url,'대상 원문')}</p>${r.context?`<details><summary>인용 주변 원문</summary><pre>${escape(r.context)}</pre></details>`:''}<p class="meta">${escape(bodyStatus)}${effective?' · 시행 '+escape(date(effective)):''} ${official(url,'본문 공식 원문')}</p>${body?`<pre>${escape(body)}</pre>`:''}</article>`).join('');
 const unresolved=packet.unresolved.map(r=>`<li><strong>${escape(r.source_law||'')} ${escape(r.source_ref||'')} → ${escape(r.target_law||'')} ${escape(r.target_ref||'')}</strong><p>${escape(r.raw||r.cite_raw||r.reference||'')} — ${escape(r.reason||r.status||r.kind||'해석 확인')}</p>${official(r.source_url,'출처 원문')} ${official(r.target_url,'대상 원문')}</li>`).join('');
 return `<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; font-src data:; base-uri 'none'; form-action 'none'"><title>${escape(a.name)} ${escape(a.reference)} — 검토자료</title><style>${fontCSS}*{box-sizing:border-box}body{margin:0;background:#092c29;color:#f4eedf;font:400 16px/1.9 MaruBuri,serif}main{max-width:900px;margin:auto;padding:40px 24px}header{border-bottom:2px solid #dfc485;padding-bottom:24px}h1{font-size:30px;line-height:1.5}h2{font-size:22px;color:#edcf8a}h3{font-size:19px}h1,h2,h3,strong{font-weight:700}.tag{color:#9addca;font-size:13px}.meta{font-size:13px;color:#b6ccc2}a{color:#a4e0ce;margin-right:14px}article,section{padding:24px 0;border-bottom:1px solid #44645b}pre{font:inherit;white-space:pre-wrap;overflow-wrap:anywhere}blockquote{margin:18px 0;padding:10px 18px;border-left:3px solid #e4c47c;background:#ffffff07}summary{cursor:pointer}li{padding:8px 0}@media print{body{background:white;color:#182d28}main{padding:0}h2,a,.tag,.meta{color:#244d43}article{break-before:auto}h2,h3{break-after:avoid}pre{orphans:3;widows:3}details{display:none}@page{margin:18mm}}@media(max-width:600px){main{padding:24px 18px}h1{font-size:24px}h2{font-size:19px}}</style><main><header><p class="tag">법의 궤도 · 검토자료</p><h1>${escape(a.name)} ${escape(a.reference)}</h1><p>${escape(a.domainTitle)} · 선택한 인용 근거 ${packet.items.length}건</p><p class="meta">수집 ${escape(date(a.builtAt))} · 시행 ${escape(date(a.effective))}<br>자료 버전 ${escape(a.version)} · 작성 ${escape(a.createdAt)}<br>탐색 조건: ${escape(a.filters)}${a.editions?'<br>분야별 수집: '+escape(a.editions):''}</p><p class="meta">${escape(packet.limitation)}</p></header><section><h2>검토 기준 본문</h2><p class="meta">${escape(a.bodyStatus)} ${official(a.url,'공식 원문')}</p><pre>${escape(a.body)}</pre></section>${items}<section><h2>미수집·미해석 확인 목록 ${packet.unresolved.length}건</h2><p class="meta">선택 여부와 관계없이 현재 검토 범위에 확인된 미수집·미해석 사항을 함께 담았습니다. 0건이어도 누락이 없다는 뜻은 아닙니다.</p>${unresolved?`<ul>${unresolved}</ul>`:'<p>현재 자료에 기록된 확인 항목이 없습니다.</p>'}</section></main></html>`;
}
function csvCell(value){let s=String(value??'');if(/^[\t\r\n]|^\s*[=+\-@]/.test(s))s="'"+s;return '"'+s.replace(/"/g,'""')+'"';}
export function reviewCSV(packet){
 const a=packet.anchor,header=['구분','분야','검토 기준 법령','검토 기준 조문','자료 버전','기준 수집일','분야별 수집일','작성일','탐색 조건','방향','출처 법령','출처 조문·문단','대상 법령','인용 대상 범위','인용 문구','인용 주변 원문','판단 상태','확인사항','출처 시행일','대상 시행일','본문 상태','출처 URL','대상 URL'];
 const base=[a.domainTitle,a.name,a.reference,a.version,a.builtAt,a.editions,a.createdAt,a.filters];
 const line=(r,kind,bodyStatus)=>[kind,...base,r.direction==='reverse'?'역인용':'직접 인용',r.source_law,r.source_ref||r.source_jo,r.target_law,r.target_ref_recorded||r.target_ref,r.raw||r.cite_raw,r.context,r.precision||r.status,r.reason,r.source_effective,r.target_effective,bodyStatus,safeLink(r.source_url),safeLink(r.target_url)];
 const rows=[header,...packet.items.map(i=>line(i.row,'선택 근거',i.bodyStatus)),...packet.unresolved.map(r=>line(r,'미확인 참고','미수집·미해석 확인')),['이용 한계',packet.limitation]];
 return '\ufeff'+rows.map(row=>row.map(csvCell).join(',')).join('\r\n')+'\r\n';
}
