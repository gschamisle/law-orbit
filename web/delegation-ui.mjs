import {supported,snapshot,reviewDocument,counterpartCandidates,changeLabels,versionLabel} from './delegation.mjs';
import {safeLink,normalize} from './query.mjs';

const text=(tag,value,cls='')=>{const n=document.createElement(tag);n.textContent=value;n.className=cls;return n;};
const option=(value,label)=>{const n=text('option',label);n.value=value;return n;};
const link=(url,label)=>{const a=text('a',label),href=safeLink(url);if(!href)return text('span','공식 출처 미확인');a.href=href;a.target='_blank';a.rel='noopener noreferrer';return a;};

export function createDelegationReview({button,dialog,getContext,load,read}){
 let generation=0,context=null,rows=[],baseline=null,filter='all',query='',limit=30;
 const title=dialog.querySelector('h2'),content=dialog.querySelector('.delegation-content');
 button.onclick=open;
 dialog.addEventListener('close',()=>{generation++;});
 function reset(){generation++;button.hidden=true;button.textContent='후속 개정 점검 · 위임사항 ↗';if(dialog.open)dialog.close();context=null;rows=[];baseline=null;content.replaceChildren();}
 async function update(){
  const ctx=getContext();button.hidden=!supported(ctx?.doc?.meta);if(button.hidden)return;
  const ref=ctx.catalog.delegation_review?.baselines?.[ctx.doc.meta.id];if(ref?.mode!=='previous-version')return;
  const token=generation;
  try{const old=await load(ref.file);if(token!==generation)return;const changes=reviewDocument(old,snapshot(ctx.doc)).filter(r=>r.change!=='unchanged');const count=new Set(changes.map(r=>r.jo)).size;if(count)button.textContent=`후속 개정 점검 · 변경 조문 ${count}개 ↗`;}
  catch{if(token===generation)button.textContent='후속 개정 점검 · 비교 자료 확인 필요 ↗';}
 }
 async function open(){
  const ctx=getContext();if(!supported(ctx?.doc?.meta))return;
  context=ctx;const token=++generation;limit=30;filter='all';query='';
  title.textContent='후속 개정 점검 · '+ctx.doc.meta.name;
  content.replaceChildren(text('p','위임 문구와 저장 인용을 대조하고 있습니다.','muted small'));
  if(!dialog.open)dialog.showModal();
  const reference=ctx.catalog.delegation_review?.baselines?.[ctx.doc.meta.id];
  let baselineError='';baseline=null;
  try{if(reference)baseline=await load(reference.file);}catch{baselineError='이전 판본 자료를 불러오지 못했습니다. 신규·변경 여부는 미대조로 표시합니다.';}
  if(token!==generation)return;
  try{
   const compare=reference?.mode==='previous-version'?baseline:null;
   rows=reviewDocument(compare,snapshot(ctx.doc,ctx.catalog.built_at));
   const groups={...(ctx.doc.details||{})},failures=new Set();
   const needed=new Map();
   for(const row of rows){const a=ctx.doc.articles.find(a=>a.jo===row.jo);if(a?.detail)needed.set(a.detail.url,a.detail);}
   for(const ref of needed.values()){
    try{Object.assign(groups,await load(ref));}catch{failures.add(ref.url);}
    if(token!==generation)return;
   }
   for(const row of rows){
    row.counterpart=counterpartCandidates(row,row.change==='removed'?(baseline?.details||{}):groups,ctx.lookup);
    row.counterpart_basis=row.change==='removed'?'previous':'current';
    if(row.before&&baseline?.details&&!['removed','unchanged'].includes(row.change))row.previous_counterpart=counterpartCandidates({...row,jo:row.before.jo,ref:row.before.ref},baseline.details,ctx.lookup);
   }
   if(compare)filter='changed';
   const head=text('div','','delegation-intro');
   head.append(text('p','법률 → 시행령·시행규칙 / 시행령 → 시행규칙','eyebrow'),text('p',`현재 수집본 시행 ${versionLabel(ctx.doc.meta)} · 수집 ${ctx.catalog.built_at}`,'muted small'));
   head.append(text('p',compare?`비교 기준: 시행 ${versionLabel(baseline.meta)} · 수집 ${baseline.built_at}. 같은 조 번호도 내용이 바뀌면 기존 인용을 재검토합니다.`:baselineError||'이전 판본 미대조 · 현재 수집본을 첫 비교 기준으로 보관했습니다. 지금 보이는 위임을 신규 위임으로 단정하지 않습니다.','muted small'));
   head.append(text('p','연결이 없어도 후속 개정이 필요할 수 있고, 연결이 있어도 위임사항이 충족됐다는 뜻은 아닙니다. 본칙의 명시적 문구와 수집 인용 범위만 점검합니다.','muted small'));
   if(failures.size)head.append(text('p',`인용 자료 ${failures.size}묶음 읽기 실패 · 해당 항목은 미확인으로 표시합니다. 다시 열어 재시도하세요.`,'error small'));
   if(!reference)head.append(text('p','배포 자료에 비교 기준이 없습니다. 이전 사이트를 지정해 자료를 다시 빌드해야 판본 비교를 할 수 있습니다.','muted small'));
   const controls=text('div','','delegation-filters'),statusLabel=text('label','보기'),select=document.createElement('select');
   select.setAttribute('aria-label','후속 개정 점검 필터');
   select.append(option('all','모든 위임·변경 항목'),option('changed','신규·변경·삭제 후보'),option('unconfirmed','대응 인용 미확인'),option('current','선택 조문'));
   select.value=filter;statusLabel.append(select);
   const searchLabel=text('label','조문·내용 검색'),search=document.createElement('input');search.type='search';search.placeholder='예: 조직, 평가, 제8조';search.setAttribute('aria-label','위임사항 검색');searchLabel.append(search);
   controls.append(statusLabel,searchLabel);
   const count=text('p','','muted small');count.setAttribute('role','status');const list=text('div','','delegation-list');
   content.replaceChildren(head,controls,count,list);
   select.onchange=()=>{filter=select.value;limit=30;render();};search.oninput=()=>{query=search.value;limit=30;render();};
   function render(){
    let visible=rows.filter(r=>(filter!=='changed'||!['uncompared','unchanged'].includes(r.change))&&(filter!=='unconfirmed'||r.counterpart.status!=='references')&&(filter!=='current'||r.jo===ctx.wanted?.jo)&&normalize(r.ref+' '+r.title+' '+r.quote).includes(normalize(query)));
    count.textContent=`${visible.length}개 검토 항목 · 개정 의무의 수가 아닙니다.`;
    list.replaceChildren(...visible.slice(0,limit).map(card));
    if(!visible.length)list.append(text('p',filter==='changed'&&!compare?'이전 판본이 없어 신규·변경 여부를 대조하지 않았습니다. 모든 위임 항목을 확인해 주세요.':'현재 조건에서 탐지된 항목이 없습니다. 의미상 영향·별표·서식·부칙까지 검토한 결과는 아닙니다.','empty'));
    if(visible.length>limit){const more=text('button',`더 보기 (${limit}/${visible.length})`,'quiet');more.onclick=()=>{limit+=30;render();};list.append(more);}
   }
   render();
  }catch(err){if(token===generation)content.replaceChildren(text('p','비교 자료를 검증하지 못했습니다. '+err.message,'error'));}
 }
 function evidence(items,label){
  const section=document.createElement('details');section.className='delegation-evidence';section.append(text('summary',label));
  for(const row of items){
   const block=text('div','','delegation-link');block.append(text('strong',`${row.source_law} ${row.source_ref}`),text('p',`시행 ${versionLabel({effective:row.source_effective})} → 근거 시행 ${versionLabel({effective:row.target_effective})}`,'muted small'),text('blockquote',row.context||row.raw||row.cite_raw||''));
   const actions=text('div','','sources');actions.append(link(row.source_url,'인용 당시 판본 원문 ↗'));
   const id=row.source_id||row.neighbor_id;
   if(context.lookup.has(id)){const b=text('button','현재 수집 본문','quiet');b.onclick=()=>read(id,row.source_jo||row.neighbor_jo);actions.append(b);}
   block.append(actions);section.append(block);
  }
  return section;
 }
 function card(row){
  const item=text('article','','delegation-card'),head=text('div','','delegation-card-head');
  const label=row.kind==='citation-change'?(row.change==='removed'?'삭제 조문 · 기존 인용 재검토':'변경 조문 · 기존 인용 재검토'):changeLabels[row.change];
  head.append(text('span',label,'delegation-badge '+(!['unchanged','uncompared'].includes(row.change)?'changed':'')),text('span',row.instrument,'muted small'));
  item.append(head,text('h3',`${row.ref} · ${row.title}`),text('blockquote',row.quote));
  if(row.before&&row.change!=='unchanged'){
   const old=document.createElement('details');old.append(text('summary','개정 전 근거 · '+row.before.ref),text('blockquote',row.before.quote));item.append(old);
  }
  if(row.kind==='citation-change')item.append(text('p','명시적 위임 문구가 없어도 기존 하위법령 인용을 함께 확인합니다.','muted small'));
  const c=row.counterpart;
  item.append(text('p',c.status==='references'?`같은 조문 범위를 인용하는 하위법령 근거 ${c.rows.length}건 · 이 위임에 대응하는지는 원문 확인 필요`:c.status==='unavailable'?'인용 자료 미확인 · 미분석 또는 읽기 실패':'현재 수집 범위에서 대응 인용을 찾지 못했습니다. 기존 규정 충족·미수집·개정 대기 여부를 확인하세요.','delegation-status'));
  if(c.rows.length)item.append(evidence(c.rows,row.counterpart_basis==='previous'?'종전 조문을 가리킨 이전 판본 인용':'현재 수집 판본의 인용 근거'));
  if(row.previous_counterpart?.rows.length)item.append(evidence(row.previous_counterpart.rows,'개정 전 인용 근거도 함께 확인'));
  if(c.issues.length)item.append(text('p',`인용 해석 확인 사항 ${c.issues.length}건 · 조문 연결 목록에서도 확인하세요.`,'muted small'));
  if(c.rows.some(r=>r.version_check)||row.previous_counterpart?.rows.length)item.append(text('p','판본 확인: 시행일이 다른 것만으로 개정 누락은 아닙니다. 종전 인용을 바뀐 내용에 그대로 적용하지 마세요.','muted small'));
  item.append(link(row.change==='removed'?baseline?.meta.url:context.doc.meta.url,'위임·변경 근거 원문 ↗'));
  return item;
 }
 return {reset,update};
}
