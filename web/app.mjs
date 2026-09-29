import {renderProcurementPdf} from './procurement-pdf.mjs';
import {installFeedback} from './feedback.mjs';
import {mountPublicScope} from './public-scope.mjs';
import {renderAnnex} from './annex.mjs';
import {annexReference,appendAnnexSources} from './annex-links.mjs';
import {mountPageviews} from './pageviews.mjs';
import {createDelegationReview} from './delegation-ui.mjs';
import {loadReading,scopeHighlights,connectionHighlights,evidenceKey,collectReview,reviewHTML,reviewCSV,provisionOptions} from './reading.mjs';
import {validateBridge,combineConnections,bridgeLookup,bridgeLabel,bridgePeers,bridgeNames,bridgeEditions} from './cross-domain.mjs';
import {selectCases,deadlineLabels,statusLabels,dateLabel} from './special.mjs';
import {data,cached,saveAll,clearSaved,configureStorage} from './store.mjs';
import {target,refine,matchingArticles,safeLink,focusMap,normalize,resolveSector} from './query.mjs';
const $=id=>document.getElementById(id),stateKey='law-galaxy-state:'+new URL('.',location.href).pathname;
mountPageviews($('pageviews'));
let manifest,catalog,regional,lookup=new Map(),domain='',state={},doc=null,detail=null,wanted=null,overview=null,epoch=0,currentRows=[],limit=40,saveController=null;
let reading=null,readingEpoch=0;
let selectedEvidence=new Set(),exportRows=[],exportUnresolved=[],exportEpoch=0,exportUrls=[];
let cross=null,crossError='';
function relatedLookup(){return bridgeLookup(lookup,cross);}
const delegation=createDelegationReview({button:$('followup-open'),dialog:$('followup'),getContext:()=>({doc,catalog,lookup,wanted}),load:data,read:(id,jo)=>openReading(id,jo)});
let special=null,specialScope={},specialLimit=30;
let saved={};try{saved=JSON.parse(localStorage.getItem(stateKey)||'{}');}catch{}
function persist(){if(!domain)return;try{saved[domain]=state;localStorage.setItem(stateKey,JSON.stringify(saved));localStorage.setItem(stateKey+':active',domain);}catch{}}
function note(message,error=false){$('notice').hidden=!message;$('notice').textContent=message;$('notice').className=error?'error':'';}
function error(err){note(err?.message||'자료를 불러오지 못했습니다.',true);}
function busy(value){for(const id of ['sector','region','law','article','reference','save-law','overview','body-query'])$(id).disabled=value;$('reference-form').querySelector('button').disabled=value;for(const id of ['direction','review','broad'])$(id).disabled=value||!doc?.articles.length;if(!value&&doc&&!doc.articles.length){for(const id of ['article','reference','body-query'])$(id).disabled=true;$('reference-form').querySelector('button').disabled=true;}}
function cancelSave(){saveController?.abort();saveController=null;$('save-law').textContent='이 법령 오프라인 저장';}
function text(tag,value,cls=''){const e=document.createElement(tag);e.textContent=value;if(cls)e.className=cls;return e;}
function link(url,label){const href=safeLink(url);if(!href)return text('span','공식 출처 확인 필요','muted');const e=text('a',label);e.href=href;e.target='_blank';e.rel='noopener noreferrer';return e;}
function option(value,label){const e=text('option',label);e.value=value;return e;}
function displayLaw(d){return d.domain==='labor'||d.name.length<=22?d.name:d.label;}
function connection(){const e=$('connection');e.textContent=navigator.onLine?'필요한 자료만 내려받아 열람':'오프라인 · 저장한 자료로 탐색';}
function allLaws(){return [...catalog.laws,...(regional?.laws||[])];}
function usesArticleTags(){return domain==='forex'||!!catalog?.workbench;}
function readableUnstructured(document){
 const raw=document.unstructured_text||'';
 if(!['public_institutions','customs','treasury','ftc','procurement','labor'].includes(document.meta?.domain))return raw;
 const hasImages=/<\/?img\b[^>]*>/i.test(raw);
 const plain=raw.replace(/<\/?img\b[^>]*>/gi,'').replace(/\n[ \t]*\n(?:[ \t]*\n)+/g,'\n\n').trim();
 return (hasImages?'[이미지·도표는 공식 원문에서 확인하세요.]\n\n':'')+plain;
}

function markBody(element,body,plan,container,auto){
 element.replaceChildren();let end=0;const marks=[];
 for(const [a,b] of plan.ranges){element.append(document.createTextNode(body.slice(end,a)));const mark=text('mark',body.slice(a,b),'citation-hit');element.append(mark);marks.push(mark);end=b;}element.append(document.createTextNode(body.slice(end)));
 if(!plan.message&&!marks.length)return;
 const controls=text('div','','citation-controls');controls.append(text('span',plan.message,'muted small'));
 let index=0;const jump=()=>{marks[index]?.scrollIntoView({block:'center',behavior:'instant'});counter.textContent=`강조 위치 ${index+1} / ${marks.length}`;};
 const counter=text('button',`강조 위치 1 / ${marks.length}`,'quiet');counter.type='button';counter.onclick=jump;
 if(marks.length){controls.append(counter);if(marks.length>1){const next=text('button','다음 위치','quiet');next.onclick=()=>{index=(index+1)%marks.length;jump();};controls.append(next);}}
 container.insertBefore(controls,element);
 if(auto&&marks.length){const token=readingEpoch;requestAnimationFrame(()=>{if(token===readingEpoch&&element.isConnected&&$('reading').open)jump();});}
}
function updateExportControls(){
 $('export-count').textContent=`선택한 근거 ${selectedEvidence.size}건`;$('export-clear').disabled=!selectedEvidence.size;$('export-open').disabled=!selectedEvidence.size;$('export-all').disabled=!currentRows.length;
}
function resetReview(){
 exportEpoch++;selectedEvidence.clear();exportRows=[];exportUnresolved=[];if($('review-export').open)$('review-export').close();for(const id of ['export-html','export-csv'])$(id).disabled=false;updateExportControls();$('export-all').disabled=true;
}
function setExportRows(rows,issues){
 exportRows=rows;exportUnresolved=[...rows.filter(r=>r.export_uncollected).map(r=>({...r,reason:(r.reason||'')+' · 미수집 또는 조문 연결 미분석'})),...issues.map(r=>typeof r==='string'?{raw:r,reason:'해석 확인'}:r)];
 const keys=new Set(rows.map(evidenceKey));selectedEvidence=new Set([...selectedEvidence].filter(k=>keys.has(k)));updateExportControls();
}
$('export-all').onclick=()=>{for(const r of currentRows)selectedEvidence.add(evidenceKey(r));renderEvidence();updateExportControls();};
$('export-clear').onclick=()=>{selectedEvidence.clear();document.querySelectorAll('.evidence-actions input').forEach(x=>{x.checked=false;});updateExportControls();};
$('export-open').onclick=()=>{if(!doc||!selectedEvidence.size)return;$('export-summary').textContent=`${doc.meta.name} ${wanted?.label||'문서 본문'} · 선택한 근거 ${selectedEvidence.size}건`;$('export-status').textContent='';for(const id of ['export-html','export-csv'])$(id).disabled=false;$('review-export').showModal();};
$('review-export').addEventListener('close',()=>{exportEpoch++;const old=exportUrls;exportUrls=[];setTimeout(()=>old.forEach(url=>URL.revokeObjectURL(url)),60000);});
async function exportFonts(){
 const fonts={};for(const [weight,name] of [['400','Regular'],['700','Bold']]){try{const response=await fetch(`fonts/MaruBuri-${name}.woff2`);if(!response.ok)continue;const bytes=new Uint8Array(await response.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));fonts[weight]=btoa(binary);}catch{}}
 return fonts;
}
async function downloadReview(format){
 if(!doc||!selectedEvidence.size)return;const token=++exportEpoch;
 for(const id of ['export-html','export-csv'])$(id).disabled=true;
 const article=doc.articles.find(a=>a.jo===wanted?.jo),anchor={name:doc.meta.name,reference:wanted?.label||'문서 본문',body:article?.text||readableUnstructured(doc),bodyStatus:article?(article.deleted?'수집 판본의 삭제 조문':'수집 조문 전체'):'수집 문서 본문 · 이미지·표는 공식 원문 확인',effective:article?.effective||doc.meta.effective,url:doc.meta.url,domainTitle:$('heading').textContent,builtAt:catalog.built_at,version:manifest.version,createdAt:new Date().toISOString(),filters:`${catalog.sectors[state.sector]||'전체'} / ${state.direction==='reverse'?'역인용':state.direction==='forward'?'직접 인용':'인용 + 역인용'} / 문맥 확인 ${state.review?'포함':'제외'} / 법령 전체 참조 ${state.broad?'포함':'제외'} / 분야 밖 연결 ${state.cross?'포함':'제외'}`,editions:cross&&state.cross?bridgeEditions(cross):''};
 const rows=structuredClone(exportRows.filter(r=>selectedEvidence.has(evidenceKey(r)))),unresolved=structuredClone(exportUnresolved),context={catalog,lookup:new Map(relatedLookup()),currentDoc:doc,read:data};
 $('export-status').textContent='선택한 본문과 인용 근거를 준비하고 있습니다.';
 try{
  const packet=await collectReview({anchor,rows,unresolved,context,cancelled:()=>token!==exportEpoch,progress:(n,total)=>{if(token===exportEpoch)$('export-status').textContent=`검토자료 준비 중 · ${n} / ${total}`;}});
  const fonts=format==='html'?await exportFonts():{};if(token!==exportEpoch)return;
  const content=format==='html'?reviewHTML(packet,fonts):reviewCSV(packet),url=URL.createObjectURL(new Blob([content],{type:format==='html'?'text/html;charset=utf-8':'text/csv;charset=utf-8'}));
  const download=document.createElement('a');download.href=url;download.download=`법의궤도-검토자료-${anchor.name}-${anchor.reference}`.replace(/[\\/:*?"<>|]/g,'-')+'.'+format;exportUrls.push(url);download.textContent='완성된 '+format.toUpperCase()+' 내려받기';download.className='export-file';
  const missing=packet.items.filter(i=>!i.body).length;$('export-status').textContent=`선택한 근거 ${packet.items.length}건의 자료를 만들었습니다.${missing?' 본문 미포함 '+missing+'건은 사유와 공식 출처를 기록했습니다.':''}${format==='html'&&Object.keys(fonts).length<2?' 일부 글꼴을 불러오지 못해 기기의 기본 글꼴로 표시될 수 있습니다.':''}`;$('export-status').append(text('span',' 자동 다운로드가 시작되지 않으면 아래 링크를 눌러 주세요.'),download);download.click();
 }catch(err){if(token===exportEpoch)$('export-status').textContent=err.message||'자료를 준비하지 못했습니다.';}
 finally{if(token===exportEpoch)for(const id of ['export-html','export-csv'])$(id).disabled=false;}
}
$('export-html').onclick=()=>downloadReview('html');$('export-csv').onclick=()=>downloadReview('csv');

function renderWorkbench(){
 const box=$('workbench'),work=catalog.workbench;box.hidden=!work;box.replaceChildren();if(!work)return;
 const head=document.createElement('div');head.className='workbench-head';
 head.append(text('h2',domain==='constitution'?'헌법에서 시작하기':'업무 질문으로 시작'),text('span',`조문 분석 ${work.indexed_documents} / 수집 ${work.documents}개 문서`,'muted small'));box.append(head,text('p',work.purpose,'muted small'));
 const cases=document.createElement('div');cases.className='work-cases';
 for(const c of work.cases){const b=text('button',c.title,'work-case');b.type='button';b.append(text('small',`${c.law} 제${c.jo}조 · 다른 문서의 연결 조문 ${c.connected_articles}개`));b.title=c.description;b.onclick=()=>navigate(domain,{sector:'all',law:c.law_id,reference:`제${c.jo}조`,query:''});cases.append(b);}box.append(cases);
 const scope=text('button',`지원 범위·빠진 자료 확인${work.unindexed.length?' · '+work.unindexed.length+'개 문서의 분석 범위 확인':''} ↗`,'work-scope quiet');scope.onclick=()=>$('coverage-open').click();box.append(scope);
 if(work.constitution_guide){
  const guide=document.createElement('details');guide.className='constitutional-guide';guide.append(text('summary','기본권·국가기관·경제질서의 관련 법률 안내'));
  guide.append(text('p','편집한 길잡이입니다. 직접 인용과 구별하며 인용선·인용 건수에 포함하지 않습니다.','muted small'));
  const choices=document.createElement('div');choices.className='guide-choices';
  for(const r of work.constitution_guide){const b=text('button',r.title,'quiet');b.append(text('small',`헌법 제${r.constitution.jo}조`));b.onclick=()=>follow(r.constitution.law_id,r.constitution.jo,'');choices.append(b);}guide.append(choices);box.append(guide);
 }
 if(work.public_scope)mountPublicScope(box,work.public_scope,{
  link,
  read:(law,jo)=>{const entry=[...lookup.values()].find(d=>d.name===law);if(entry)openReading(entry.id,jo);else note('이 법령의 본문은 미수집입니다.');},
  explore:(law,jo,scopeOnly)=>{const entry=[...lookup.values()].find(d=>d.name===law);if(entry){state.relation=scopeOnly?'scope':'all';$('relation').value=state.relation;if(entry.id===doc?.meta.id&&jo===wanted?.jo)renderConnections();else follow(entry.id,jo,'');}}
 });
}
function allowedLaws(){return allLaws().filter(d=>state.sector==='all'||(d.sectors||[]).includes(state.sector));}
function renderLaws(){
 const filtered=allowedLaws();
 $('law').replaceChildren(option('','법령을 선택하세요'),...filtered.map(d=>option(d.id,displayLaw(d)+(d.analyzed?'':d.text_analysis?' · 문단 인용':' · 조문 미분석'))));
 if(filtered.some(d=>d.id===state.law))$('law').value=state.law;
 return filtered;
}
function renderArticles(){
 const candidates=(doc?.articles||[]).filter(a=>!usesArticleTags()||state.sector==='all'||(a.sectors||[]).includes(state.sector));
 const matches=matchingArticles(candidates,$('body-query').value);$('article').replaceChildren(...matches.map(a=>option(a.jo,a.label+(a.title?' · '+a.title:''))));
 if(wanted&&matches.some(a=>a.jo===wanted.jo))$('article').value=wanted.jo;
 else if(matches.length)$('article').selectedIndex=-1;
 if(!matches.length)$('article').append(option('','검색 결과 없음'));
}
function domainButtons(){
 const nav=$('domains');nav.replaceChildren();
 const button=d=>{const b=text('button',d.title);b.type='button';b.setAttribute('aria-current',d.id===domain?'page':'false');b.onclick=()=>navigate(d.id);return b;};
 const foundation=manifest.domains.find(d=>d.id==='constitution');
 if(foundation){const top=document.createElement('div');top.className='nav-foundation';const b=button(foundation);b.append(text('small','원칙과 제도의 출발점'));top.append(b);nav.append(top,text('p','분야별 법령','nav-section-label'));}
 const fields=document.createElement('div');fields.className='nav-fields';fields.append(...manifest.domains.filter(d=>d.id!=='constitution').map(button));nav.append(fields);
}
async function navigate(id,overrides={}){
 resetReview();delegation.reset();
 $('workbench').hidden=true;$('workbench').replaceChildren();
 closeReading();cancelSave();persist();domain=id;state={sector:'all',region:'',law:'',query:'',reference:'',direction:'both',review:true,broad:false,cross:true,relation:'all',...saved[id],...overrides};const token=++epoch;busy(true);note('');doc=detail=wanted=null;regional=null;cross=null;crossError='';
 $('cross-label').hidden=!manifest.cross_domain?.[id];$('cross-text').textContent=(bridgeNames[bridgePeers[id]]||'관련 분야')+' 연결 포함';$('cross').checked=state.cross;$('cross').disabled=true;
 $('article-content').replaceChildren(text('p','법령 자료를 불러오고 있습니다.','muted'));$('evidence').replaceChildren();$('outside').replaceChildren();$('evidence-count').textContent='';domainButtons();
 try{
  const entry=manifest.domains.find(d=>d.id===id);if(!entry)throw Error('지원하지 않는 분야입니다.');
  const loaded=await data(entry.catalog);if(token!==epoch)return;
  // Display a shared scope label without changing the collected catalog or its coverage.
  catalog={...loaded,sectors:{...loaded.sectors,all:'전체 연결'}};
  if(manifest.cross_domain?.[id]){
   try{const linked=await data(manifest.cross_domain[id]);if(token!==epoch)return;cross=validateBridge(linked,id,manifest,catalog);$('cross').disabled=false;}
   catch(err){if(token!==epoch)return;crossError='분야 간 연결 자료를 불러오지 못했습니다. '+err.message;}
  }
  renderWorkbench();$('relation-label').hidden=!catalog.workbench?.public_scope;$('relation').value=state.relation||'all';
  if(state.region){const r=catalog.regions?.find(r=>r.id===state.region);if(r?.catalog)regional=await data(r.catalog);else state.region='';}
  if(token!==epoch)return;lookup=new Map(allLaws().map(d=>[d.id,d]));
  $('heading').textContent=entry.title;document.title='법의 궤도 — '+entry.title;
  document.querySelector('.page-head .eyebrow').textContent=id==='constitution'?'CONSTITUTION / FOUNDATIONS':'EXPLORE THE CONNECTIONS';
  document.querySelector('.page-head p').textContent=id==='constitution'?'헌법에서 출발해, 원칙을 구체화하는 법률을 읽습니다.':'조문을 불러오면, 함께 살펴볼 법이 보입니다.';
  special=null;specialScope={};if($('special').open)$('special').close();
  $('special-open').hidden=!catalog.special_cases;
  $('sector').replaceChildren(...Object.entries(catalog.sectors).map(([v,t])=>option(v,t)));state.sector=resolveSector(catalog,state.sector);$('sector').value=state.sector;
  $('sector-label').hidden=Object.keys(catalog.sectors).length<2;
  $('overview').textContent=state.sector==='all'?'전체 지도 보기':'분야 지도 보기';
  $('region-label').hidden=id!=='local_tax';$('region').replaceChildren(option('','중앙 법령·전국 역인용'),...(catalog.regions||[]).map(r=>option(r.id,r.authority+(r.catalog?'':' · 분석 자료 없음'))));$('region').value=state.region;
  $('body-query').value=state.query||'';$('direction').value=state.direction;$('review').checked=state.review;$('broad').checked=state.broad;
  const choices=renderLaws();overview=await data((regional||catalog).overview);if(token!==epoch)return;
 const defaults={tax:'법인세법',fsc:'은행법',ftc:'독점규제 및 공정거래에 관한 법률',local_tax:'지방세법',procurement:'국가를 당사자로 하는 계약에 관한 법률',housing:'국토의 계획 및 이용에 관한 법률',environment:'화학물질관리법',state_property:'국유재산법',forex:'외국환거래규정',public_institutions:'공공기관의 운영에 관한 법률',customs:'관세법',treasury:'국고금 관리법',labor:'근로기준법',constitution:'대한민국헌법',medical:'의료법'};
  const medicalDefault={public:['지역보건법','제11조'],insurance:['국민건강보험법','제42조']}[state.sector]||['의료법','제43조'];
  const preferred=id==='medical'?medicalDefault[0]:defaults[id];
  const chosen=lookup.get(state.law)||choices.find(d=>d.name===preferred)||choices[0];
  const previousQuery=state.query;if(chosen){await openLaw(chosen.id,state.reference||(id==='ftc'&&chosen.name===defaults.ftc?'제45조':id==='labor'&&chosen.name===defaults.labor?'제11조':id==='constitution'&&chosen.name===defaults.constitution?'제53조':id==='medical'&&chosen.name===medicalDefault[0]?medicalDefault[1]:''),token);if(token===epoch){state.query=previousQuery;$('body-query').value=previousQuery;renderArticles();}}else{showMap(overview);$('article-content').replaceChildren(text('p','선택 분야의 수집 조문이 없습니다.','muted'));}
  persist();
 }catch(err){if(token===epoch){error(err);$('map-host').replaceChildren(text('p','이 분야의 자료를 불러오지 못했습니다. 다른 분야의 자료로 대체하지 않습니다.','empty'));}}
 finally{if(token===epoch)busy(false);}
}
async function openLaw(id,reference='',token=++epoch){
 resetReview();delegation.reset();
 const entry=lookup.get(id);if(!entry){error(Error('이 범위에 수집되지 않은 법령입니다.'));return;}
 closeReading();cancelSave();busy(true);note('');$('article-content').replaceChildren(text('p','조문 자료를 불러오고 있습니다.','muted'));$('evidence').replaceChildren();$('outside').replaceChildren();detail=wanted=null;
 try{
  const loaded=await data(entry.file);if(token!==epoch)return;doc=loaded;state.law=id;state.query='';$('body-query').value='';
  if(!$('law').querySelector(`option[value="${id}"]`))$('law').prepend(option(id,entry.label+' · 분야 밖 관련 법령'));$('law').value=id;
  $('law-title').textContent=entry.name;$('law-meta').replaceChildren(text('span',`시행 ${entry.effective||'확인 필요'} · ${entry.authority||entry.kind||'수집 자료'} `),link(entry.url,'공식 원문 ↗'));
  if(doc.annexes?.length){const annexes=document.createElement('details');annexes.className='annex-picker';annexes.append(text('summary',`별표·서식 ${doc.annexes.length}개 · 본문 분석 ${doc.annexes.filter(a=>a.analysis).length}개`));const choice=document.createElement('select');choice.setAttribute('aria-label','읽을 별표·서식');choice.append(option('','별표·서식을 선택하세요'),...doc.annexes.map(a=>option(a.ref,a.ref+' · '+a.title+(a.analysis?'':' · 본문 미분석'))));choice.onchange=()=>{if(choice.value)openReading(id,choice.value);};annexes.append(choice);$('law-meta').append(annexes);}
  for(const control of [document.querySelector('.body-search'),$('article').parentElement,$('reference-form')])if(control)control.hidden=!doc.articles.length;
  renderArticles();$('download-state').textContent='조문과 연결 근거는 필요한 부분만 불러옵니다.';
  if(!doc.pdf_analysis)for(const message of entry.source_notes||[])$('law-meta').append(text('p',message,'muted small'));
  if(entry.pdf_url)$('law-meta').append(link(entry.pdf_url,'수집 판본 PDF ↗'));
  if(entry.unparsed_provisions?.length){const details=document.createElement('details');details.append(text('summary','조문번호 확인이 필요한 미분석 원문'));for(const item of entry.unparsed_provisions)details.append(text('p',item.reason),text('div',item.raw,'article-body'));$('law-meta').append(details);}
  let a=(usesArticleTags()&&state.sector!=='all'?doc.articles.find(a=>(a.sectors||[]).includes(state.sector)):null)||doc.articles[0];try{const t=target(reference,['fsc','forex'].includes(domain));a=doc.articles.find(a=>a.jo===t.jo)||a;}catch{}
  if(a)await openArticle(reference&&doc.articles.some(a=>{try{return a.jo===target(reference,['fsc','forex'].includes(domain)).jo;}catch{return false;}})?reference:a.label,token);
  else{
   detail=wanted=null;state.reference='';$('reference').replaceChildren();
   $('article-content').replaceChildren(text('p',doc.meta.text_analysis?'문단의 명시적 인용 분석 · 지침 내부 문단 간 참조는 미분석':'본문 수집 · 조문 연결 미분석','status-badge'),text('div',readableUnstructured(doc)||'조문 단위로 분석된 본문이 없습니다. 공식 원문을 확인해 주세요.','article-body'));
   currentRows=doc.text_connections?.filter(r=>!r.external)||[];limit=40;setExportRows((doc.text_connections||[]).map(r=>({...r,export_uncollected:!!r.external})),doc.text_issues||[]);renderEvidence();
   $('evidence-count').textContent=doc.text_connections?`${currentRows.length}건`:'';
   $('connection-note').textContent=doc.text_connections?'지침 본문에 명시된 인용입니다. 근거 조문의 본문을 읽거나 그 조문의 연결을 탐색할 수 있습니다.':'';
   $('outside').replaceChildren();
   if(doc.text_connections){
    const notes=document.createElement('details');notes.className='outside-note';const external=doc.text_connections.filter(r=>r.external),issues=doc.text_issues||[];
    notes.append(text('summary',`미수집 인용·해석 확인 ${external.length+issues.length}건`));notes.append(...external.map(r=>evidenceCard(r,true)),...issues.map(i=>text('p',i.raw+' — '+i.reason)));$('outside').append(notes);
   }
   if(doc.pdf_analysis)renderProcurementPdf($('article-content'),doc,[],{text,link,onPage:page=>{
    resetReview();const rows=doc.text_connections.filter(r=>r.source_page===page.page),issues=doc.text_issues.filter(r=>r.source_start>=page.start&&r.source_start<page.end);
    currentRows=rows.filter(r=>!r.external);limit=40;setExportRows(rows.map(r=>({...r,export_uncollected:!!r.external})),issues);renderEvidence();
    $('evidence-count').textContent=`${currentRows.length}건`;$('connection-note').textContent=`PDF ${page.page}쪽의 명시적 인용입니다. 다른 쪽은 본문 위치에서 선택하세요.`;
    const external=rows.filter(r=>r.external);$('outside').replaceChildren();if(external.length||issues.length){const notes=document.createElement('details');notes.className='outside-note';notes.append(text('summary',`이 쪽의 미수집 인용·해석 확인 ${external.length+issues.length}건`),...external.map(r=>evidenceCard(r,true)),...issues.map(i=>text('p',i.raw+' — '+i.reason)));$('outside').append(notes);}
   }});
   showMap(sectorMap());
  }
  delegation.update();persist();
 }catch(err){if(token===epoch)error(err);}finally{if(token===epoch)busy(false);}
}
async function openArticle(reference,token=++epoch){
 if(!doc)return;resetReview();closeReading();busy(true);note('');
 try{
  const parsed=target(reference,['fsc','forex'].includes(domain)),a=doc.articles.find(a=>a.jo===parsed.jo);if(!a)throw Error('수집한 본문에 해당 조문이 없습니다. 다른 조문으로 대체하지 않았습니다.');
  const group=doc.details?.[a.jo]?doc.details:await data(a.detail);if(token!==epoch)return;if(!group[a.jo])throw Error('조문 연결 자료를 찾지 못했습니다.');
  wanted=parsed;detail=group[a.jo];state.reference=wanted.label;$('reference').replaceChildren(...provisionOptions(a,wanted.label).map(p=>option(p.value,p.label)));$('reference').value=wanted.label;$('article').value=a.jo;limit=40;
  const box=$('article-content');box.replaceChildren(text('h3',a.label+(a.title?' · '+a.title:''),'article-title'));
  if(a.deleted)box.append(text('p','수집 판본에서 삭제된 조문','status-badge'));
  const meta=document.createElement('div');meta.className='article-meta';meta.append(text('span','시행 '+(a.effective||doc.meta.effective||'확인 필요'),'muted small'));
  const copy=text('button','본문 복사');copy.onclick=async()=>{try{await navigator.clipboard.writeText(doc.meta.name+' '+a.label+'\n'+a.text);copy.textContent='복사됨';}catch{note('본문을 선택해 복사해 주세요.');}};meta.append(copy);box.append(meta);const mainBody=text('div',a.text,'article-body');box.append(mainBody);if(wanted.narrow){const plan=scopeHighlights(a.text,a.jo,{scopes:[[wanted.path,wanted.path,null]]});markBody(mainBody,a.text,plan,box,false);}
  if(wanted.narrow)box.append(text('p',`본문은 ${a.label} 전체이며 연결은 ${wanted.label} 범위로 대조합니다.`,'muted small'));
  if(domain==='constitution'&&doc.meta.name==='대한민국헌법'){
   const related=(catalog.workbench?.constitution_guide||[]).filter(r=>r.constitution.jo===a.jo);
   if(related.length){const section=document.createElement('section');section.className='constitutional-reading';section.append(text('h3','관련 법률 안내'),text('p','해설성 연결 · 직접 인용 건수에 포함하지 않습니다.','muted small'));
    for(const r of related){section.append(text('h4',r.related.law+' 제'+r.related.jo+'조'),text('p',r.reason,'muted small'));const b=text('button','관련 법률 본문 보기');b.onclick=()=>openReading(r.related.law_id,r.related.jo);section.append(b);}box.append(section);}
  }
  if(domain==='state_property'){
   const button=text('button',doc.meta.name==='국유재산특례제한법'?'별표의 특례 근거 목록 ↗':'이 조문의 특례 등재 확인 ↗','special-inline quiet');
   button.onclick=()=>openSpecial(doc.meta.name==='국유재산특례제한법'?{}:{law:doc.meta.name,jo:a.jo});box.append(button);
  }
  renderConnections();persist();
 }catch(err){if(token===epoch)error(err);}finally{if(token===epoch)busy(false);}
}
function showMap(value){
 const frame=document.createElement('iframe');frame.title=(value.galaxy_title||'법령').replace(/\s*은하/g,'')+' · 3D 법령 지도';frame.src='renderer.html';frame.allow='fullscreen';frame.onload=()=>frame.contentWindow.postMessage({type:'galaxy-data',data:value},location.origin);$('map-host').replaceChildren(frame);
}
function sectorMap(){if(state.sector==='all')return overview;const names=new Set(allowedLaws().map(d=>d.name));return {...overview,...(domain==='state_property'?{overview_note:'선택 분야의 법령·지침입니다. 배치는 탐색을 위한 것으로 법적 위계를 뜻하지 않습니다.'}:{}),galaxy_title:$('heading').textContent+' ('+catalog.sectors[state.sector]+')',nodes:overview.nodes.filter(n=>names.has(n.id)),dust:overview.dust.filter(n=>names.has(n.law_id)&&(!usesArticleTags()||(n.sectors||[]).includes(state.sector))),links:overview.links.filter(l=>names.has(l.a)&&names.has(l.b)),all_links:overview.all_links.filter(l=>names.has(l.a)&&names.has(l.b))};}
function outsideSector(row){const d=lookup.get(row.neighbor_id);if(usesArticleTags()&&state.sector!=='all'&&row.neighbor_kind==='article')return !(d?.article_sectors?.[row.neighbor_jo]||[]).includes(state.sector);return state.sector!=='all'&&(!d||(d.sectors||[]).indexOf(state.sector)<0);}
function evidenceCard(row,external=false){
 const annex=annexReference(row,{currentDoc:doc,external});
 const card=document.createElement('article');card.className='evidence-card';const header=document.createElement('header'),title=document.createElement('div');
 title.append(text('span',external?'지도 밖 인용':row.direction==='reverse'?'← 역인용':'직접 인용 →','flow '+(row.direction==='reverse'?'reverse':'')));
 title.append(text('h3',external?(row.target_law+' '+(row.target_ref||'')):(row.neighbor_law+' '+(row.neighbor_ref||row.neighbor_jo||''))));
 if(row.source_granularity==='annex'&&row.source_layer!=='annex-body')title.append(text('small','별표 제목의 관련 조문','muted'));
 if(row.cross_domain)title.append(text('span',bridgeLabel(row),'badge'));else if(row.national)title.append(text('span','전국 수집 조례 · '+(row.source_law||''),'badge'));else if(outsideSector(row))title.append(text('span','분야 밖 관련 조문','badge'));
 if(row.scope_labels?.length)title.append(text('small',row.scope_labels.map(k=>catalog.workbench.public_scope.labels[k]).join(' · '),'scope-labels'));
 header.append(title);
 if(annex){const originals=text('div','','annex-sources');appendAnnexSources(originals,annex,{text,link});header.append(originals);if(!external&&annex.id&&annex.analyzed){const button=text('button','검증된 별표 본문 보기');button.onclick=()=>openReading(annex.id,annex.ref,row.region||relatedLookup().get(annex.id)?.region||'',[row]);header.append(button);}}
 else if(!external&&row.neighbor_id){const button=text('button','본문 보기');button.onclick=()=>openReading(row.neighbor_id,row.neighbor_kind==='article'?row.neighbor_jo:'',row.region||relatedLookup().get(row.neighbor_id)?.region||'',[row]);header.append(button);}
 const actions=document.createElement('div');actions.className='evidence-actions';
 const pick=text('label','','check');const check=document.createElement('input');check.type='checkbox';check.checked=selectedEvidence.has(evidenceKey(row));check.setAttribute('aria-label',`검토자료에 담기: ${row.neighbor_law||row.target_law} ${row.neighbor_ref||row.target_ref||''} · ${row.source_law||''} ${row.source_ref||''}`);check.onchange=()=>{if(check.checked)selectedEvidence.add(evidenceKey(row));else selectedEvidence.delete(evidenceKey(row));updateExportControls();};pick.append(check,document.createTextNode('검토자료에 담기'));actions.append(pick);
 const sourceId=row.source_id||(row.source_law===doc?.meta.name?doc.meta.id:'');
 if(row.direction==='forward'&&sourceId&&(relatedLookup().has(sourceId)||sourceId===doc?.meta.id)){const quote=text('button','인용 위치','quiet');quote.onclick=()=>openReading(sourceId,row.source_jo||'',relatedLookup().get(sourceId)?.region||'',[{...row,direction:'reverse'}]);actions.append(quote);}
 card.append(header,actions,text('blockquote',row.raw||row.cite_raw||''));
 if(row.source_law)card.append(text('p',`${row.source_law} ${row.source_ref||row.source_jo||''} → ${row.target_law||''} ${row.target_ref||''}`));
 card.append(text('p',external?(row.target_status==='collected-not-indexed'?'본문 수집 · 조문 연결 미분석':'미수집 · 본문과 역인용 미점검'):(row.precision||'')+' · '+(row.reason||'')));
 if(row.target_provision_status==='missing-from-collected-body')card.append(text('p','대상 법령은 수집했지만 해당 조문은 수집 판본에 없습니다.'));
 if(row.target_provision_status==='deleted')card.append(text('p','대상은 수집 판본의 삭제 조문입니다.'));
 if(row.cross_domain)card.append(text('p',`출처 시행 ${row.source_effective||'확인 필요'} · 대상 시행 ${row.target_effective||'확인 필요'}`,'muted small'));
 if(annex&&!annex.analyzed)card.append(text('p',annex.status==='not-analyzed'?'별표 본문·표 내부 인용은 미분석입니다. 공식 원본에서 내용을 확인하세요.':'별표 본문 분석 여부는 이 연결 자료에서 확인되지 않습니다. 공식 원본을 확인하세요.','muted small'));
 if(row.context){const context=document.createElement('details');context.append(text('summary','인용 주변 원문'),text('p',row.context));card.append(context);}
 const sources=document.createElement('div');sources.className='sources';if(row.source_url)sources.append(link(row.source_url,annex&&row.direction==='reverse'||row.source_granularity==='annex'?'출처 별표 소유 법령 원문 ↗':'출처 원문 ↗'));if(row.target_url)sources.append(link(row.target_url,annex&&row.direction!=='reverse'||row.target_kind==='annex'?'대상 별표 소유 법령 원문 ↗':'대상 원문 ↗'));card.append(sources);
 return card;
}
function renderEvidence(){
 $('evidence').replaceChildren(...currentRows.slice(0,limit).map(r=>evidenceCard(r)));
 if(!currentRows.length)$('evidence').append(text('p','현재 범위·조건에 맞는 저장 인용이 없습니다. 영향이 없다는 판정은 아닙니다.','empty'));
 if(currentRows.length>limit){const button=text('button',`근거 더 보기 (${limit} / ${currentRows.length})`);button.id='more-evidence';button.onclick=()=>{limit+=40;renderEvidence();};$('evidence').append(button);}
}
function renderConnections(){
 if(!detail||!wanted)return;
 state.direction=$('direction').value;state.review=$('review').checked;state.broad=$('broad').checked;
 state.cross=$('cross').checked;const connected=combineConnections(detail,doc.broad,cross,doc.meta.id,wanted.jo,state.cross);
 currentRows=refine([...connected.rows,...connected.broad],wanted,state);
 if(domain==='public_institutions'&&catalog.workbench?.public_scope){
  const records=catalog.workbench.public_scope.records;
  for(const row of currentRows){const matches=records.filter(r=>r.kind==='scope'&&r.evidence_ids.includes(row.evidence_id));row.scope_labels=[...new Set(matches.flatMap(r=>r.labels))];}
  if(state.relation==='scope'){const ids=new Set(records.flatMap(r=>r.evidence_ids));currentRows=currentRows.filter(r=>ids.has(r.evidence_id));}
 }
 $('evidence-count').textContent=`${currentRows.length.toLocaleString()}건`;
 $('connection-note').textContent=detail.analysis_error||`${catalog.built_at} 수집 자료 · 인용 문구의 범위를 대조한 결과입니다. 지도는 최대 180개 연결 대상을 표시하며 근거 목록은 모두 열람할 수 있습니다.`;
 if(cross&&state.cross)$('connection-note').textContent+=` 분야 밖 연결 ${currentRows.filter(r=>r.cross_domain).length}건 · ${bridgeEditions(cross)} 수집 판본.`;
 if(crossError)$('connection-note').textContent+=' '+crossError;
 const map=focusMap(currentRows,doc.meta,wanted,sectorMap(),relatedLookup());showMap(map);
 const external=connected.external.filter(e=>!wanted.narrow||!e.source_scope||refine([{...e,direction:'forward',kind:e.target_kind||'article'}],wanted,{review:true}).length);
 $('outside').replaceChildren();
 if(external.length||connected.issues.length){const section=document.createElement('details');section.className='outside-note';section.append(text('summary',`미수집 인용·해석 확인 ${external.length+connected.issues.length}건`),text('p','미수집 법령 본문과 역인용·별표 본문을 점검한 것으로 해석하지 마세요.','muted small'));
 section.append(...external.map(e=>evidenceCard(e,true)));for(const i of connected.issues)section.append(text('p',(i.raw||'')+' — '+(i.reason||i.kind||i.status||'문맥 확인')));$('outside').append(section);}
 setExportRows([...currentRows.map(r=>({...r,export_uncollected:false})),...external.map(r=>({...r,export_uncollected:true}))],[...connected.issues,...(detail.unplaced||[])]);renderEvidence();
 if(detail.unplaced?.length)$('outside').append(text('p',`참조 번호를 해석하지 못해 지도 위치를 정하지 못한 근거 ${detail.unplaced.length}건`,'muted small'));
 persist();
}
async function follow(id,jo,region){
 if(id===doc?.meta.id&&jo===wanted?.jo)return;
 const reference=jo?`제${jo.replace('의','조의')}${jo.includes('의')?'':'조'}`:'';
 const entry=relatedLookup().get(id);if(entry&&entry.domain!==domain){await navigate(entry.domain,{sector:'all',law:id,reference,query:''});return;}
 if(domain==='local_tax'&&region&&region!==state.region){await navigate(domain,{region,law:id,reference,query:''});return;}
 await openLaw(id,reference);
}
function closeReading(){
 readingEpoch++;reading=null;if($('reading').open)$('reading').close();
}
function readingLabel(jo){return /^(별표|별지|서식)/.test(jo)?jo:jo?`제${jo.replace('의','조의')}${jo.includes('의')?'':'조'}`:'';}
function renderReadingArticle(jo){
 if(!reading)return;const {entry,document}=reading;const a=document.articles.find(a=>a.jo===jo),annex=(document.annexes||[]).find(a=>a.ref===jo);
 reading.article=a;reading.requestedJo=jo;reading.copyText=a?entry.name+' '+a.label+'\n'+a.text:(!document.articles.length?readableUnstructured(document):'');
 $('reading-title').textContent=entry.name+(jo?' '+readingLabel(jo):'');
 $('reading-meta').replaceChildren(text('span','시행 '+(a?.effective||entry.effective||'확인 필요')+' '),link(entry.url,'공식 원문 ↗'));
 const body=$('reading-body');body.replaceChildren();$('reading-copy').textContent='본문 복사';$('reading-copy').disabled=!reading.copyText;$('reading-explore').disabled=!a;
 if(annex){
  reading.copyText=annex.analysis?entry.name+' '+annex.ref+'\n'+annex.analysis.text:'';$('reading-copy').disabled=!reading.copyText;$('reading-explore').disabled=true;
  $('reading-status').textContent=annex.analysis?'별표 본문 · 명시적 인용 분석':'별표 본문 미분석';
  $('reading-meta').replaceChildren(text('span','시행 '+(annex.effective||entry.effective||'확인 필요')+' '),link(entry.url,'공식 원문 ↗'));
  renderAnnex(body,annex,reading.evidence,{text,link,read:openReading,ownerUrl:entry.url,currentDoc:document});
 }else if(a){
  $('reading-status').textContent=a.deleted?'수집 판본에서 삭제된 조문입니다.':'';
  body.append(text('h3',a.title));const content=text('div',a.text,'reading-text');body.append(content);markBody(content,a.text,connectionHighlights(a.text,jo,reading.evidence.filter(r=>r.direction==='reverse'?r.source_jo===jo:r.neighbor_kind==='article'&&r.neighbor_jo===jo)),body,true);
 }else if(/^(별표|별지|서식)/.test(jo)){
  reading.copyText='';$('reading-copy').disabled=true;$('reading-explore').disabled=true;
  const row=reading.evidence.find(r=>r.neighbor_id===entry.id&&r.neighbor_jo===jo);
  const original=annexReference(row||{neighbor_kind:'annex',neighbor_id:entry.id,neighbor_law:entry.name,neighbor_jo:jo,target_url:entry.url},{currentDoc:document});
  $('reading-status').textContent='별표 본문 미확보 · 공식 원본을 확인하세요.';
  renderAnnex(body,{ref:jo,title:jo,urls:original?.originals||[]},[],{text,link,read:openReading,ownerUrl:entry.url});
 }else if(jo){
  $('reading-status').textContent='수집한 판본에 해당 조문 본문이 없습니다. 공식 원문을 확인해 주세요.';
 }else if(document.articles.length){
  $('reading-status').textContent='수집된 법령 본문에서 읽을 조문을 선택해 주세요.';
 }else{
  $('reading-status').textContent=document.meta.text_analysis?'문단 인용 분석 · 지침 내부 문단 간 참조는 미분석':'본문 수집 · 조문 연결 미분석';
  if(document.pdf_analysis){
   $('reading-status').textContent=document.pdf_analysis.anchors?'PDF 문단·표 인용 · 내부 위치 연결':'PDF 문단 인용 · 표·서식·부칙은 연결 미분석';
   renderProcurementPdf(body,document,reading.evidence,{text,link,markBody:(element,raw,rows,stage)=>markBody(element,raw,connectionHighlights(raw,'',rows),stage,true),onPage:page=>{reading.copyText=entry.name+` · PDF ${page.page}쪽\n`+page.text;}});
  }else{
  const raw=readableUnstructured(document),content=text('div',raw||'수집된 본문이 없습니다. 공식 원문을 확인해 주세요.','reading-text');body.append(content);if(raw)markBody(content,raw,connectionHighlights(raw,'',reading.evidence),body,true);
  }
 }
 $('reading-scroll').scrollTop=0;
}
async function openReading(id,jo='',region='',evidence=null){
 const token=++readingEpoch,anchor=epoch,context={catalog,lookup:relatedLookup(),currentDoc:doc,read:data};reading=null;
 $('reading-title').textContent='연결 조문 본문';$('reading-context').textContent='검토 기준 · '+(doc?.meta.name||$('heading').textContent)+' '+(wanted?.label||'');
 $('reading-status').textContent='본문을 불러오고 있습니다.';$('reading-meta').replaceChildren();$('reading-body').replaceChildren();$('reading-picker').hidden=true;
 $('reading-copy').disabled=true;$('reading-explore').disabled=true;
 if(document.fullscreenElement){try{await document.exitFullscreen();}catch{}}
 if(token!==readingEpoch||anchor!==epoch)return;
 if(!$('reading').open)$('reading').showModal();
 try{
  const result=await loadReading({id,jo,region},context);if(token!==readingEpoch||anchor!==epoch)return;
  reading={...result,evidence:evidence||currentRows.filter(r=>r.neighbor_id===id&&(['article','annex'].includes(r.neighbor_kind)?r.neighbor_jo:'')===jo)};$('reading-picker').hidden=!!jo||!result.document.articles.length;
  $('reading-article').replaceChildren(option('','읽을 조문을 선택하세요'),...result.document.articles.map(a=>option(a.jo,a.label+(a.title?' · '+a.title:''))));
  renderReadingArticle(jo);
 }catch(err){if(token===readingEpoch&&anchor===epoch)$('reading-status').textContent=err.message||'본문을 불러오지 못했습니다. 인터넷 연결 또는 저장 자료를 확인해 주세요.';}
}
$('relation').onchange=()=>{state.relation=$('relation').value;renderConnections();};
$('reading').addEventListener('close',()=>{if(!$('reading').open){readingEpoch++;reading=null;}});
$('reading-article').onchange=()=>renderReadingArticle($('reading-article').value);
$('cross').onchange=()=>{limit=40;renderConnections();};
$('reading-copy').onclick=async()=>{
 const selected=reading;if(!selected?.copyText)return;
 try{await navigator.clipboard.writeText(selected.copyText);if(reading===selected)$('reading-copy').textContent='복사됨';}
 catch{if(reading===selected)$('reading-status').textContent='본문을 선택해 복사해 주세요.';}
};
$('reading-explore').onclick=()=>{
 if(!reading?.article)return;const {entry,article}=reading;closeReading();if($('special').open)$('special').close();follow(entry.id,article.jo,entry.region||'');
};
$('law').onchange=()=>{if($('law').value)openLaw($('law').value);};
$('sector').onchange=()=>navigate(domain,{sector:$('sector').value,law:'',reference:'',query:''});
$('region').onchange=()=>{const region=catalog.regions?.find(r=>r.id===$('region').value);if(region&&!region.catalog){note('이 지역은 분석된 조례·규칙 데이터가 없습니다. 관련 법령이 없다는 뜻은 아닙니다.');$('region').value=state.region;return;}navigate(domain,{region:$('region').value,law:'',reference:'',query:''});};
$('body-query').oninput=()=>{state.query=$('body-query').value;renderArticles();persist();};
$('article').onchange=()=>{const a=doc.articles.find(a=>a.jo===$('article').value);if(a)openArticle(a.label);};
$('reference-form').onsubmit=e=>{e.preventDefault();openArticle($('reference').value);};
for(const id of ['direction','review','broad'])$(id).onchange=()=>{limit=40;renderConnections();};
$('overview').onclick=()=>showMap(sectorMap());
$('special-open').onclick=()=>openSpecial();
async function openSpecial(scope={}){
 if(domain!=='state_property'||!catalog.special_cases)return;
 const token=epoch;specialScope=scope;specialLimit=30;
 $('special-query').value='';$('special-type').value='';$('special-deadline').value='';$('special-status').value='';
 $('special-list').replaceChildren(text('p','공식 별표를 불러오고 있습니다.','muted'));
 $('special-count').textContent='';$('special-source').replaceChildren();$('special-reset').hidden=!scope.law;
 if(!$('special').open)$('special').showModal();
 try{
  const loaded=special||await data(catalog.special_cases);if(token!==epoch||domain!=='state_property')return;
  special=loaded;$('special-note').textContent=special.note;
  $('special-source').replaceChildren(text('span',`별표 시행 ${dateLabel(special.source_effective)} · 수집 ${dateLabel(special.as_of)} `),link(special.source_url,'법률 원문 ↗'),...special.annex_urls.map((u,i)=>link(u,`별표 원본 ${i+1} ↗`)));
  renderSpecial();
 }catch(err){if(token===epoch)$('special-list').replaceChildren(text('p','특례 목록을 불러오지 못했습니다. 인터넷 연결 또는 저장 자료를 확인해 주세요.','empty'));}
}
function renderSpecial(){
 if(!special)return;
 const rows=selectCases(special.rows,{...specialScope,query:$('special-query').value,type:$('special-type').value,deadline:$('special-deadline').value,status:$('special-status').value});
 $('special-count').textContent=`${rows.length} / ${special.rows.length}개 항목`+(specialScope.law?` · ${specialScope.law} ${readingLabel(specialScope.jo)}`:'');
 const list=$('special-list');list.replaceChildren();
 for(const row of rows.slice(0,specialLimit)){
  const card=document.createElement('article');card.className='special-card';
  card.append(text('span',`별표 ${row.number} · ${statusLabels[row.status]||'확인 필요'}`,'eyebrow'),text('h3',row.legal_text));
  const labels=text('div','', 'special-tags');for(const t of row.types)labels.append(text('span',special.types[t],'special-tag'));
  labels.append(text('span',`${deadlineLabels[row.deadline_status]} · ${dateLabel(row.deadline)}`,'special-tag '+(row.deadline_status==='elapsed'?'elapsed':'')));card.append(labels);
  card.append(text('p',row.type_text,'muted small'),text('p',row.reason,'muted small'));
  const actions=text('div','','special-actions');
  if(row.law_id)for(const jo of row.article_numbers||[]){const b=text('button',readingLabel(jo)+' 본문');b.onclick=async()=>{await openReading(row.law_id,jo);if(reading?.entry.id===row.law_id)$('reading-context').textContent=`국유재산특례제한법 별표 ${row.number} · ${row.legal_text}`;};actions.append(b);}
  if(row.law_url)actions.append(link(row.law_url,'근거 법률 원문 ↗'));
  const evidence=document.createElement('details');evidence.append(text('summary','별표 원문 근거'),text('pre',row.raw));card.append(actions,evidence);list.append(card);
 }
 if(!rows.length)list.append(text('p','현재 조건에 맞는 별표 항목이 없습니다. 다른 법률상 특례나 적용 가능성이 없다는 판정은 아닙니다.','empty'));
 if(rows.length>specialLimit){const b=text('button',`특례 더 보기 (${specialLimit}/${rows.length})`);b.onclick=()=>{specialLimit+=30;renderSpecial();};list.append(b);}
}
for(const id of ['special-query','special-type','special-deadline','special-status'])$(id).addEventListener(id==='special-query'?'input':'change',()=>{specialLimit=30;renderSpecial();});
$('special-reset').onclick=()=>{specialScope={};$('special-reset').hidden=true;renderSpecial();};
window.addEventListener('message',e=>{const frame=$('map-host').querySelector('iframe');if(e.origin!==location.origin||e.source!==frame?.contentWindow||e.data?.type!=='galaxy-select')return;if(e.data.mode==='spotlight'||e.data.jo)openReading(e.data.law,e.data.jo,e.data.region||'');else follow(e.data.law,e.data.jo,e.data.region||'');});
$('save-law').onclick=async()=>{
 if(!doc)return;if(saveController){saveController.abort();return;}saveController=new AbortController();const controller=saveController;const id=doc.meta.id,entry=lookup.get(id),refs=[manifest.domains.find(d=>d.id===domain).catalog,(regional||catalog).overview,entry.file,...entry.parts];
 if(state.region)refs.push(catalog.regions.find(r=>r.id===state.region).catalog);
 if(cross&&manifest.cross_domain?.[domain])refs.push(manifest.cross_domain[domain]);
 if(catalog.special_cases)refs.push(catalog.special_cases);
 if(catalog.delegation_review?.baselines?.[id])refs.push(catalog.delegation_review.baselines[id].file);
 const unique=[...new Map(refs.map(r=>[r.url,r])).values()];$('save-law').textContent='저장 멈추기';
 try{await saveAll(unique,(i,n)=>{if(controller===saveController)$('download-state').textContent=`${displayLaw(entry)} 자료 저장 중 · ${i}/${n}`;},controller.signal);if(controller!==saveController)return;
  const verified=await Promise.all(unique.map(cached));
  const registration=await navigator.serviceWorker?.getRegistration();if(controller!==saveController)return;if(!registration?.active){$('download-state').textContent='자료는 저장했지만 오프라인 화면 준비가 끝나지 않았습니다. 연결된 상태에서 한 번 새로고침해 주세요.';return;}$('download-state').textContent=verified.every(Boolean)?`${displayLaw(entry)} 본문·인용 근거 저장 완료. 연결 대상의 본문은 해당 법령을 열 때 받습니다.`:'일부 자료를 저장하지 못했습니다. 저장 공간·인터넷 연결을 확인해 주세요.';
 }catch(err){if(controller===saveController)error(err);}finally{if(controller===saveController){saveController=null;$('save-law').textContent='이 법령 오프라인 저장';}}
};
installFeedback(()=>({domain:$('heading').textContent,law:doc?.meta.name,reference:wanted?.label||($('article-content').querySelector('[aria-label="PDF 본문 쪽"]')?'PDF '+$('article-content').querySelector('[aria-label="PDF 본문 쪽"]').value+'쪽':''),effective:doc?.meta.effective,version:manifest?.version,builtAt:catalog?.built_at,relatedLaw:reading?.entry.name,relatedReference:reading?.article?.label||reading?.requestedJo||($('reading-body').querySelector('[aria-label="PDF 본문 쪽"]')?'PDF '+$('reading-body').querySelector('[aria-label="PDF 본문 쪽"]').value+'쪽':'')}));
$('about-open').onclick=()=>$('about').showModal();
$('coverage-open').onclick=()=>{
 const content=$('coverage-copy');content.replaceChildren(text('p',`${$('heading').textContent} · 수집 기준 ${catalog?.built_at||''}`),text('p',catalog?.workbench&&domain!=='medical'?'수집한 본칙의 명시적 인용을 분석합니다. 별표·서식 본문·부칙은 미분석이며, 미수집 외부 법령의 본문·역인용은 점검하지 않았습니다. 불명확한 인용은 확인 목록에 보존합니다.':catalog?.coverage||''),text('p','항·호·목 범위를 포함한 저장 인용을 대조합니다. 새 항 신설의 취지 추론·의미상 유사성·신설 조문 검토는 이 무료 열람 버전에 포함하지 않습니다.'),text('p','이 웹사이트는 공개 법령 본문과 분석 결과만 제공합니다. 법제처 API 인증값이나 개정안 업로드 기능은 포함하지 않습니다.'));
 if(['tax','public_institutions'].includes(domain))content.append(text('p','후속 개정 점검은 수집 법률·시행령의 위임 문구와 이전 판본의 변경을 대조합니다. 과거 판본 미확보 시 신규 여부는 미대조이며, 위임 이행·개정 누락을 자동 확정하지 않습니다. 내부 개정안 비교는 로컬 앱에서 제공합니다.'));
 const work=catalog?.workbench;
 const summary=catalog?.collection_summary;
 if(catalog?.pdf_summary){for(const pdf of catalog.pdf_summary)content.append(text('p',`${pdf.name}: PDF ${pdf.pages}쪽 · 법령 인용 ${pdf.references}건${pdf.status==='explicit-pdf-structured'?` (표 셀 ${pdf.table_citations}건, 별표 문단 ${pdf.annex_citations}건 포함) · 내부 위치 연결 ${pdf.internal_links}건. 표의 적용조건·산식과 서식·부칙은 미분석입니다.`:`. 표·서식·부칙은 연결 미분석입니다.`}`));}
 if(catalog?.text_summary){const t=catalog.text_summary;content.append(text('p',`문단 인용 분석 ${t.documents}개 문서 · 명시적 인용 근거 ${t.citations}건 · 해석 확인 ${t.issues}건. 내부 문단 간 참조·이미지·표 본문은 미분석입니다.`));}
 if(summary){
  content.append(text('p',`법령 ${summary.statutes}건 · 행정규칙 ${summary.administrative_rules}건 · 조문 분석 ${summary.indexed_documents}개 문서 / ${summary.articles}개 조문`),text('p',`문단 인용 분석 ${summary.text_analyzed_documents}개 문서 · 명시적 인용 ${summary.text_citations}건 · 시행예정 ${summary.scheduled}건은 현재 지도에서 제외했습니다.`),text('p',`해석 확인 목록: 조문 ${summary.unresolved}건 · 지침 문단 ${summary.text_unresolved}건. 인용 대상이나 범위를 확정하지 못한 사례는 근거 목록에서 구분합니다.`));
 }
 if(work){content.append(text('h3','이 분야에서 확인할 수 있는 것'),text('p',work.purpose));for(const message of work.limitations)content.append(text('p',message));content.append(text('p','업무 태그는 제목·본문 키워드에 따른 탐색 보조 분류입니다. 법적 적용 범위의 판정이 아닙니다. 지도에 쓰는 짧은 이름은 표시용 약칭이며, 공식 명칭은 본문 상단에서 확인합니다.'));
  for(const source of work.companion_sources){const p=document.createElement('p');p.append(link(source.url,source.title+' ↗'));content.append(p);}
  if(work.unindexed.length){const details=document.createElement('details');details.append(text('summary',`문단형·미분석 자료 ${work.unindexed.length}건`));for(const item of work.unindexed){const p=document.createElement('p');p.append(link(item.url,item.name+' ↗'),text('span',' · '+item.status));details.append(p);}content.append(details);}
  if(work.unavailable_selected_rules.length)content.append(text('p','선정했으나 이번 수집 목록에서 확인하지 못한 자료: '+work.unavailable_selected_rules.join(', ')));
 }
 $('coverage').showModal();
};
for(const button of document.querySelectorAll('.dialog-close'))button.onclick=()=>button.closest('dialog').close();
$('saved-manager').onclick=async()=>{const usage=await navigator.storage?.estimate?.();$('storage-size').textContent=usage?`이 사이트의 브라우저 저장 사용량: 약 ${((usage.usage||0)/1048576).toFixed(1)} MB`:'저장 용량을 확인할 수 없습니다.';$('storage').showModal();};
$('clear-saved').onclick=async()=>{try{await clearSaved();$('storage-size').textContent='저장한 법령 자료를 비웠습니다.';}catch(err){error(err);}};
$('check-update').onclick=async()=>{try{const registration=await navigator.serviceWorker?.getRegistration();await registration?.update();}catch{}location.reload();};
window.addEventListener('online',connection);window.addEventListener('offline',connection);
async function start(){
 connection();try{
  let response;try{response=await fetch('manifest.json',{cache:'no-cache'});if(!response.ok)throw Error();try{const c=await caches.open('law-galaxy-manifest-v1');await c.put(new URL('manifest.json',location.href),response.clone());}catch{}}
  catch{response=await caches.match(new URL('manifest.json',location.href));if(!response)throw Error('처음 사용할 때에는 인터넷 연결이 필요합니다.');}
  manifest=await response.json();if(manifest.schema!==1)throw Error('자료 형식이 맞지 않습니다. 새 판본을 확인해 주세요.');
  configureStorage(manifest.data_packs);
  if('serviceWorker'in navigator)navigator.serviceWorker.register('./sw.js').catch(()=>{});
  let active=manifest.domains.some(d=>d.id==='constitution')?'constitution':'tax';try{active=localStorage.getItem(stateKey+':active')||active;}catch{}
  await navigate(manifest.domains.some(d=>d.id===active)?active:manifest.domains.some(d=>d.id==='constitution')?'constitution':'tax');
 }catch(err){error(err);}
}
start();
