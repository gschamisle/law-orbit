import {data,cached,saveAll,clearSaved} from './store.mjs';
import {target,refine,matchingArticles,safeLink,focusMap,normalize} from './query.mjs';
const $=id=>document.getElementById(id),stateKey='law-galaxy-state:'+new URL('.',location.href).pathname;
let manifest,catalog,regional,lookup=new Map(),domain='',state={},doc=null,detail=null,wanted=null,overview=null,epoch=0,currentRows=[],limit=40,saveController=null;
let saved={};try{saved=JSON.parse(localStorage.getItem(stateKey)||'{}');}catch{}
function persist(){if(!domain)return;try{saved[domain]=state;localStorage.setItem(stateKey,JSON.stringify(saved));localStorage.setItem(stateKey+':active',domain);}catch{}}
function note(message,error=false){$('notice').hidden=!message;$('notice').textContent=message;$('notice').className=error?'error':'';}
function error(err){note(err?.message||'자료를 불러오지 못했습니다.',true);}
function busy(value){for(const id of ['sector','region','law','article','reference','save-law','overview','body-query'])$(id).disabled=value;$('reference-form').querySelector('button').disabled=value;}
function cancelSave(){saveController?.abort();saveController=null;$('save-law').textContent='이 법령 오프라인 저장';}
function text(tag,value,cls=''){const e=document.createElement(tag);e.textContent=value;if(cls)e.className=cls;return e;}
function link(url,label){const href=safeLink(url);if(!href)return text('span','공식 출처 확인 필요','muted');const e=text('a',label);e.href=href;e.target='_blank';e.rel='noopener noreferrer';return e;}
function option(value,label){const e=text('option',label);e.value=value;return e;}
function displayLaw(d){return d.name.length<=22?d.name:d.label;}
function connection(){const e=$('connection');e.textContent=navigator.onLine?'필요한 자료만 내려받아 열람':'오프라인 · 저장한 자료로 탐색';}
function allLaws(){return [...catalog.laws,...(regional?.laws||[])];}
function allowedLaws(){return allLaws().filter(d=>state.sector==='all'||(d.sectors||[]).includes(state.sector));}
function renderLaws(){
 const filtered=allowedLaws().filter(d=>normalize(d.name+' '+d.label).includes(normalize($('law-query').value)));
 $('law').replaceChildren(option('','법령을 선택하세요'),...filtered.map(d=>option(d.id,displayLaw(d)+(d.analyzed?'':' · 조문 미분석'))));
 if(filtered.some(d=>d.id===state.law))$('law').value=state.law;
 return filtered;
}
function renderArticles(){
 const matches=matchingArticles(doc?.articles||[],$('body-query').value);$('article').replaceChildren(...matches.map(a=>option(a.jo,a.label+' · '+a.title)));
 if(wanted&&matches.some(a=>a.jo===wanted.jo))$('article').value=wanted.jo;
 else if(matches.length)$('article').selectedIndex=-1;
 if(!matches.length)$('article').append(option('','검색 결과 없음'));
}
function domainButtons(){
 $('domains').replaceChildren(...manifest.domains.map(d=>{const b=text('button',d.title);b.type='button';b.setAttribute('aria-current',d.id===domain?'page':'false');b.onclick=()=>navigate(d.id);return b;}));
}
async function navigate(id,overrides={}){
 cancelSave();persist();domain=id;state={sector:'all',region:'',law:'',query:'',reference:'',direction:'both',review:true,broad:false,...saved[id],...overrides};const token=++epoch;busy(true);note('');doc=detail=wanted=null;regional=null;
 $('article-content').replaceChildren(text('p','법령 자료를 불러오고 있습니다.','muted'));$('evidence').replaceChildren();$('outside').replaceChildren();$('evidence-count').textContent='';domainButtons();
 try{
  const entry=manifest.domains.find(d=>d.id===id);if(!entry)throw Error('지원하지 않는 분야입니다.');
  const loaded=await data(entry.catalog);if(token!==epoch)return;catalog=loaded;
  if(state.region){const r=catalog.regions?.find(r=>r.id===state.region);if(r?.catalog)regional=await data(r.catalog);else state.region='';}
  if(token!==epoch)return;lookup=new Map(allLaws().map(d=>[d.id,d]));
  $('heading').textContent=entry.title+' 은하';document.title=entry.title+' 은하 · 이 조문 건드리면 다 죽는 거야';
  $('sector').replaceChildren(...Object.entries(catalog.sectors).map(([v,t])=>option(v,t)));if(!catalog.sectors[state.sector])state.sector='all';$('sector').value=state.sector;
  $('region-label').hidden=id!=='local_tax';$('region').replaceChildren(option('','중앙 법령·전국 역인용'),...(catalog.regions||[]).map(r=>option(r.id,r.authority+(r.catalog?'':' · 분석 자료 없음'))));$('region').value=state.region;
  $('law-query').value='';$('body-query').value=state.query||'';$('direction').value=state.direction;$('review').checked=state.review;$('broad').checked=state.broad;
  const choices=renderLaws();overview=await data((regional||catalog).overview);if(token!==epoch)return;
  const defaults={tax:'법인세법',fsc:'은행법',local_tax:'지방세법',procurement:'국가를 당사자로 하는 계약에 관한 법률',housing:'국토의 계획 및 이용에 관한 법률',environment:'화학물질관리법'};
  const chosen=lookup.get(state.law)||choices.find(d=>d.name===defaults[id])||choices[0];
  const previousQuery=state.query;if(chosen){await openLaw(chosen.id,state.reference,token);if(token===epoch){state.query=previousQuery;$('body-query').value=previousQuery;renderArticles();}}else{showMap(overview);$('article-content').replaceChildren(text('p','선택 분야의 수집 조문이 없습니다.','muted'));}
  persist();
 }catch(err){if(token===epoch){error(err);$('map-host').replaceChildren(text('p','이 분야의 자료를 불러오지 못했습니다. 다른 은하로 대체하지 않습니다.','empty'));}}
 finally{if(token===epoch)busy(false);}
}
async function openLaw(id,reference='',token=++epoch){
 const entry=lookup.get(id);if(!entry){error(Error('이 범위에 수집되지 않은 법령입니다.'));return;}
 cancelSave();busy(true);note('');$('article-content').replaceChildren(text('p','조문 자료를 불러오고 있습니다.','muted'));$('evidence').replaceChildren();$('outside').replaceChildren();detail=wanted=null;
 try{
  const loaded=await data(entry.file);if(token!==epoch)return;doc=loaded;state.law=id;state.query='';$('body-query').value='';
  if(!$('law').querySelector(`option[value="${id}"]`))$('law').prepend(option(id,entry.label+' · 분야 밖 관련 법령'));$('law').value=id;
  $('law-title').textContent=entry.name;$('law-meta').replaceChildren(text('span',`시행 ${entry.effective||'확인 필요'} · ${entry.authority||entry.kind||'수집 자료'} `),link(entry.url,'공식 원문 ↗'));
  renderArticles();$('download-state').textContent='조문과 연결 근거는 필요한 부분만 불러옵니다.';
  let a=doc.articles[0];try{const t=target(reference,domain==='fsc');a=doc.articles.find(a=>a.jo===t.jo)||a;}catch{}
  if(a)await openArticle(reference&&doc.articles.some(a=>{try{return a.jo===target(reference,domain==='fsc').jo;}catch{return false;}})?reference:a.label,token);
  else{
   detail=wanted=null;$('article-content').replaceChildren(text('p','본문 수집 · 조문 연결 미분석','status-badge'),text('div',doc.unstructured_text||'조문 단위로 분석된 본문이 없습니다. 공식 원문을 확인해 주세요.','article-body'));
   $('evidence').replaceChildren();$('outside').replaceChildren();showMap(overview);
  }
  persist();
 }catch(err){if(token===epoch)error(err);}finally{if(token===epoch)busy(false);}
}
async function openArticle(reference,token=++epoch){
 if(!doc)return;busy(true);note('');
 try{
  const parsed=target(reference,domain==='fsc'),a=doc.articles.find(a=>a.jo===parsed.jo);if(!a)throw Error('수집한 본문에 해당 조문이 없습니다. 다른 조문으로 대체하지 않았습니다.');
  const group=doc.details?.[a.jo]?doc.details:await data(a.detail);if(token!==epoch)return;if(!group[a.jo])throw Error('조문 연결 자료를 찾지 못했습니다.');
  wanted=parsed;detail=group[a.jo];state.reference=wanted.label;$('reference').value=wanted.label;$('article').value=a.jo;limit=40;
  const box=$('article-content');box.replaceChildren(text('h3',a.label+' · '+a.title,'article-title'));
  if(a.deleted)box.append(text('p','수집 판본에서 삭제된 조문','status-badge'));
  const meta=document.createElement('div');meta.className='article-meta';meta.append(text('span','시행 '+(a.effective||doc.meta.effective||'확인 필요'),'muted small'));
  const copy=text('button','본문 복사');copy.onclick=async()=>{try{await navigator.clipboard.writeText(doc.meta.name+' '+a.label+'\n'+a.text);copy.textContent='복사됨';}catch{note('본문을 선택해 복사해 주세요.');}};meta.append(copy);box.append(meta,text('div',a.text,'article-body'));
  if(wanted.narrow)box.append(text('p',`본문은 ${a.label} 전체이며 연결은 ${wanted.label} 범위로 대조합니다.`,'muted small'));
  renderConnections();persist();
 }catch(err){if(token===epoch)error(err);}finally{if(token===epoch)busy(false);}
}
function showMap(value){
 const frame=document.createElement('iframe');frame.title=(value.galaxy_title||'법령 은하')+' · 3D 연결 지도';frame.src='renderer.html';frame.allow='fullscreen';frame.onload=()=>frame.contentWindow.postMessage({type:'galaxy-data',data:value},location.origin);$('map-host').replaceChildren(frame);
}
function sectorMap(){if(state.sector==='all')return overview;const names=new Set(allowedLaws().map(d=>d.name));return {...overview,galaxy_title:$('heading').textContent+' ('+catalog.sectors[state.sector]+')',nodes:overview.nodes.filter(n=>names.has(n.id)),dust:overview.dust.filter(n=>names.has(n.law_id)),links:overview.links.filter(l=>names.has(l.a)&&names.has(l.b)),all_links:overview.all_links.filter(l=>names.has(l.a)&&names.has(l.b))};}
function outsideSector(row){const d=lookup.get(row.neighbor_id);return state.sector!=='all'&&(!d||(d.sectors||[]).indexOf(state.sector)<0);}
function evidenceCard(row,external=false){
 const card=document.createElement('article');card.className='evidence-card';const header=document.createElement('header'),title=document.createElement('div');
 title.append(text('span',external?'지도 밖 인용':row.direction==='reverse'?'← 역인용':'직접 인용 →','flow '+(row.direction==='reverse'?'reverse':'')));
 title.append(text('h3',external?(row.target_law+' '+(row.target_ref||'')):(row.neighbor_law+' '+(row.neighbor_ref||row.neighbor_jo||''))));
 if(row.national)title.append(text('span','전국 수집 조례 · '+(row.source_law||''),'badge'));else if(outsideSector(row))title.append(text('span','분야 밖 관련 조문','badge'));
 header.append(title);
 if(!external&&row.neighbor_id){const button=text('button','조문 불러오기');button.onclick=()=>follow(row.neighbor_id,row.neighbor_kind==='article'?row.neighbor_jo:'',row.region||lookup.get(row.neighbor_id)?.region||'');header.append(button);}
 card.append(header,text('blockquote',row.raw||row.cite_raw||''));
 if(row.source_law)card.append(text('p',`${row.source_law} ${row.source_ref||row.source_jo||''} → ${row.target_law||''} ${row.target_ref||''}`));
 card.append(text('p',external?(row.target_status==='collected-not-indexed'?'본문 수집 · 조문 연결 미분석':'미수집 · 본문과 역인용 미점검'):(row.precision||'')+' · '+(row.reason||'')));
 if(row.target_provision_status==='missing-from-collected-body')card.append(text('p','대상 법령은 수집했지만 해당 조문은 수집 판본에 없습니다.'));
 if(row.target_provision_status==='deleted')card.append(text('p','대상은 수집 판본의 삭제 조문입니다.'));
 if(row.context){const context=document.createElement('details');context.append(text('summary','인용 주변 원문'),text('p',row.context));card.append(context);}
 const sources=document.createElement('div');sources.className='sources';if(row.source_url)sources.append(link(row.source_url,'출처 원문 ↗'));if(row.target_url)sources.append(link(row.target_url,'대상 원문 ↗'));card.append(sources);
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
 currentRows=refine([...detail.rows,...doc.broad],wanted,state);$('evidence-count').textContent=`${currentRows.length.toLocaleString()}건`;
 $('connection-note').textContent=detail.analysis_error||`${catalog.built_at} 수집 자료 · 인용 문구의 범위를 대조한 결과입니다. 지도는 최대 180개 연결 대상을 표시하며 근거 목록은 모두 열람할 수 있습니다.`;
 const map=focusMap(currentRows,doc.meta,wanted,sectorMap(),lookup);showMap(map);renderEvidence();
 const external=detail.external.filter(e=>!wanted.narrow||!e.source_scope||refine([{...e,direction:'forward',kind:e.target_kind||'article'}],wanted,{review:true}).length);
 $('outside').replaceChildren();
 if(external.length||detail.issues.length){const section=document.createElement('details');section.className='outside-note';section.append(text('summary',`미수집 인용·해석 확인 ${external.length+detail.issues.length}건`),text('p','미수집 법령 본문과 역인용·별표 본문을 점검한 것으로 해석하지 마세요.','muted small'));
 section.append(...external.map(e=>evidenceCard(e,true)));for(const i of detail.issues)section.append(text('p',(i.raw||'')+' — '+(i.reason||i.kind||i.status||'문맥 확인')));$('outside').append(section);}
 if(detail.unplaced?.length)$('outside').append(text('p',`참조 번호를 해석하지 못해 지도 위치를 정하지 못한 근거 ${detail.unplaced.length}건`,'muted small'));
 persist();
}
async function follow(id,jo,region){
 if(id===doc?.meta.id&&jo===wanted?.jo)return;
 const reference=jo?`제${jo.replace('의','조의')}${jo.includes('의')?'':'조'}`:'';
 if(domain==='local_tax'&&region&&region!==state.region){await navigate(domain,{region,law:id,reference,query:''});return;}
 await openLaw(id,reference);
}
$('law-query').oninput=renderLaws;
$('law').onchange=()=>{if($('law').value)openLaw($('law').value);};
$('sector').onchange=()=>navigate(domain,{sector:$('sector').value,law:'',reference:'',query:''});
$('region').onchange=()=>{const region=catalog.regions?.find(r=>r.id===$('region').value);if(region&&!region.catalog){note('이 지역은 분석된 조례·규칙 데이터가 없습니다. 관련 법령이 없다는 뜻은 아닙니다.');$('region').value=state.region;return;}navigate(domain,{region:$('region').value,law:'',reference:'',query:''});};
$('body-query').oninput=()=>{state.query=$('body-query').value;renderArticles();persist();};
$('article').onchange=()=>{const a=doc.articles.find(a=>a.jo===$('article').value);if(a)openArticle(a.label);};
$('reference-form').onsubmit=e=>{e.preventDefault();openArticle($('reference').value);};
for(const id of ['direction','review','broad'])$(id).onchange=()=>{limit=40;renderConnections();};
$('overview').onclick=()=>showMap(sectorMap());
window.addEventListener('message',e=>{const frame=$('map-host').querySelector('iframe');if(e.origin!==location.origin||e.source!==frame?.contentWindow||e.data?.type!=='galaxy-select')return;follow(e.data.law,e.data.jo,e.data.region||'');});
$('save-law').onclick=async()=>{
 if(!doc)return;if(saveController){saveController.abort();return;}saveController=new AbortController();const controller=saveController;const id=doc.meta.id,entry=lookup.get(id),refs=[manifest.domains.find(d=>d.id===domain).catalog,(regional||catalog).overview,entry.file,...entry.parts];
 if(state.region)refs.push(catalog.regions.find(r=>r.id===state.region).catalog);
 const unique=[...new Map(refs.map(r=>[r.url,r])).values()];$('save-law').textContent='저장 멈추기';
 try{await saveAll(unique,(i,n)=>{if(controller===saveController)$('download-state').textContent=`${displayLaw(entry)} 자료 저장 중 · ${i}/${n}`;},controller.signal);if(controller!==saveController)return;
  const verified=await Promise.all(unique.map(cached));
  const registration=await navigator.serviceWorker?.getRegistration();if(controller!==saveController)return;if(!registration?.active){$('download-state').textContent='자료는 저장했지만 오프라인 화면 준비가 끝나지 않았습니다. 연결된 상태에서 한 번 새로고침해 주세요.';return;}$('download-state').textContent=verified.every(Boolean)?`${displayLaw(entry)} 본문·인용 근거 저장 완료. 연결 대상의 본문은 해당 법령을 열 때 받습니다.`:'일부 자료를 저장하지 못했습니다. 저장 공간·인터넷 연결을 확인해 주세요.';
 }catch(err){if(controller===saveController)error(err);}finally{if(controller===saveController){saveController=null;$('save-law').textContent='이 법령 오프라인 저장';}}
};
$('coverage-open').onclick=()=>{
 const content=$('coverage-copy');content.replaceChildren(text('p',`${$('heading').textContent} · 수집 기준 ${catalog?.built_at||''}`),text('p',catalog?.coverage||''),text('p','항·호·목 범위를 포함한 저장 인용을 대조합니다. 새 항 신설의 취지 추론·의미상 유사성·신설 조문 검토는 이 무료 열람 버전에 포함하지 않습니다.'),text('p','이 웹사이트는 공개 법령 본문과 분석 결과만 제공합니다. 법제처 API 인증값이나 개정안 업로드 기능은 포함하지 않습니다.'));
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
  if('serviceWorker'in navigator)navigator.serviceWorker.register('./sw.js').catch(()=>{});
  let active='tax';try{active=localStorage.getItem(stateKey+':active')||'tax';}catch{}
  await navigate(manifest.domains.some(d=>d.id===active)?active:'tax');
 }catch(err){error(err);}
}
start();
