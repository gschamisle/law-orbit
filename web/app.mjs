import {loadReading} from './reading.mjs';
import {validateBridge,combineConnections,bridgeLookup,bridgeLabel} from './cross-domain.mjs';
import {selectCases,deadlineLabels,statusLabels,dateLabel} from './special.mjs';
import {data,cached,saveAll,clearSaved} from './store.mjs';
import {target,refine,matchingArticles,safeLink,focusMap,normalize} from './query.mjs';
const $=id=>document.getElementById(id),stateKey='law-galaxy-state:'+new URL('.',location.href).pathname;
let manifest,catalog,regional,lookup=new Map(),domain='',state={},doc=null,detail=null,wanted=null,overview=null,epoch=0,currentRows=[],limit=40,saveController=null;
let reading=null,readingEpoch=0;
let cross=null,crossError='';
function relatedLookup(){return bridgeLookup(lookup,cross);}
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
function displayLaw(d){return d.name.length<=22?d.name:d.label;}
function connection(){const e=$('connection');e.textContent=navigator.onLine?'필요한 자료만 내려받아 열람':'오프라인 · 저장한 자료로 탐색';}
function allLaws(){return [...catalog.laws,...(regional?.laws||[])];}
function usesArticleTags(){return domain==='forex'||!!catalog?.workbench;}
function readableUnstructured(document){
 const raw=document.unstructured_text||'';
 if(!['public_institutions','customs','treasury','ftc'].includes(document.meta?.domain))return raw;
 const hasImages=/<\/?img\b[^>]*>/i.test(raw);
 const plain=raw.replace(/<\/?img\b[^>]*>/gi,'').replace(/\n[ \t]*\n(?:[ \t]*\n)+/g,'\n\n').trim();
 return (hasImages?'[이미지·도표는 공식 원문에서 확인하세요.]\n\n':'')+plain;
}

function renderWorkbench(){
 const box=$('workbench'),work=catalog.workbench;box.hidden=!work;box.replaceChildren();if(!work)return;
 const head=document.createElement('div');head.className='workbench-head';
 head.append(text('h2','업무 질문으로 시작'),text('span',`조문 분석 ${work.indexed_documents} / 수집 ${work.documents}개 문서`,'muted small'));box.append(head,text('p',work.purpose,'muted small'));
 const cases=document.createElement('div');cases.className='work-cases';
 for(const c of work.cases){const b=text('button',c.title,'work-case');b.type='button';b.append(text('small',`${c.law} 제${c.jo}조 · 다른 문서의 연결 조문 ${c.connected_articles}개`));b.title=c.description;b.onclick=()=>navigate(domain,{sector:'all',law:c.law_id,reference:`제${c.jo}조`,query:''});cases.append(b);}box.append(cases);
 const scope=text('button',`지원 범위·빠진 자료 확인${work.unindexed.length?' · '+work.unindexed.length+'개 문서는 조문 미분석':''} ↗`,'work-scope quiet');scope.onclick=()=>$('coverage-open').click();box.append(scope);
}
function allowedLaws(){return allLaws().filter(d=>state.sector==='all'||(d.sectors||[]).includes(state.sector));}
function renderLaws(){
 const filtered=allowedLaws().filter(d=>normalize(d.name+' '+d.label).includes(normalize($('law-query').value)));
 $('law').replaceChildren(option('','법령을 선택하세요'),...filtered.map(d=>option(d.id,displayLaw(d)+(d.analyzed?'':d.text_analysis?' · 문단 인용':' · 조문 미분석'))));
 if(filtered.some(d=>d.id===state.law))$('law').value=state.law;
 return filtered;
}
function renderArticles(){
 const candidates=(doc?.articles||[]).filter(a=>!usesArticleTags()||state.sector==='all'||(a.sectors||[]).includes(state.sector));
 const matches=matchingArticles(candidates,$('body-query').value);$('article').replaceChildren(...matches.map(a=>option(a.jo,a.label+' · '+a.title)));
 if(wanted&&matches.some(a=>a.jo===wanted.jo))$('article').value=wanted.jo;
 else if(matches.length)$('article').selectedIndex=-1;
 if(!matches.length)$('article').append(option('','검색 결과 없음'));
}
function domainButtons(){
 $('domains').replaceChildren(...manifest.domains.map(d=>{const b=text('button',d.title);b.type='button';b.setAttribute('aria-current',d.id===domain?'page':'false');b.onclick=()=>navigate(d.id);return b;}));
}
async function navigate(id,overrides={}){
 $('workbench').hidden=true;$('workbench').replaceChildren();
 closeReading();cancelSave();persist();domain=id;state={sector:'all',region:'',law:'',query:'',reference:'',direction:'both',review:true,broad:false,cross:true,...saved[id],...overrides};const token=++epoch;busy(true);note('');doc=detail=wanted=null;regional=null;cross=null;crossError='';
 $('cross-label').hidden=!manifest.cross_domain?.[id];$('cross-text').textContent=id==='forex'?'금융 연결 포함':'외환 연결 포함';$('cross').checked=state.cross;$('cross').disabled=true;
 $('article-content').replaceChildren(text('p','법령 자료를 불러오고 있습니다.','muted'));$('evidence').replaceChildren();$('outside').replaceChildren();$('evidence-count').textContent='';domainButtons();
 try{
  const entry=manifest.domains.find(d=>d.id===id);if(!entry)throw Error('지원하지 않는 분야입니다.');
  const loaded=await data(entry.catalog);if(token!==epoch)return;catalog=loaded;
  if(manifest.cross_domain?.[id]){
   try{const linked=await data(manifest.cross_domain[id]);if(token!==epoch)return;cross=validateBridge(linked,id,manifest,catalog);$('cross').disabled=false;}
   catch(err){if(token!==epoch)return;crossError='분야 간 연결 자료를 불러오지 못했습니다. '+err.message;}
  }
  renderWorkbench();
  if(state.region){const r=catalog.regions?.find(r=>r.id===state.region);if(r?.catalog)regional=await data(r.catalog);else state.region='';}
  if(token!==epoch)return;lookup=new Map(allLaws().map(d=>[d.id,d]));
  $('heading').textContent=entry.title;document.title='법의 궤도 — '+entry.title;
  special=null;specialScope={};if($('special').open)$('special').close();
  $('special-open').hidden=!catalog.special_cases;
  $('sector').replaceChildren(...Object.entries(catalog.sectors).map(([v,t])=>option(v,t)));if(!catalog.sectors[state.sector])state.sector='all';$('sector').value=state.sector;
  $('region-label').hidden=id!=='local_tax';$('region').replaceChildren(option('','중앙 법령·전국 역인용'),...(catalog.regions||[]).map(r=>option(r.id,r.authority+(r.catalog?'':' · 분석 자료 없음'))));$('region').value=state.region;
  $('law-query').value='';$('body-query').value=state.query||'';$('direction').value=state.direction;$('review').checked=state.review;$('broad').checked=state.broad;
  const choices=renderLaws();overview=await data((regional||catalog).overview);if(token!==epoch)return;
  const defaults={tax:'법인세법',fsc:'은행법',ftc:'독점규제 및 공정거래에 관한 법률',local_tax:'지방세법',procurement:'국가를 당사자로 하는 계약에 관한 법률',housing:'국토의 계획 및 이용에 관한 법률',environment:'화학물질관리법',state_property:'국유재산법',forex:'외국환거래규정',public_institutions:'공공기관의 운영에 관한 법률',customs:'관세법',treasury:'국고금 관리법'};
  const chosen=lookup.get(state.law)||choices.find(d=>d.name===defaults[id])||choices[0];
  const previousQuery=state.query;if(chosen){await openLaw(chosen.id,state.reference||(id==='ftc'&&chosen.name===defaults.ftc?'제45조':''),token);if(token===epoch){state.query=previousQuery;$('body-query').value=previousQuery;renderArticles();}}else{showMap(overview);$('article-content').replaceChildren(text('p','선택 분야의 수집 조문이 없습니다.','muted'));}
  persist();
 }catch(err){if(token===epoch){error(err);$('map-host').replaceChildren(text('p','이 분야의 자료를 불러오지 못했습니다. 다른 분야의 자료로 대체하지 않습니다.','empty'));}}
 finally{if(token===epoch)busy(false);}
}
async function openLaw(id,reference='',token=++epoch){
 const entry=lookup.get(id);if(!entry){error(Error('이 범위에 수집되지 않은 법령입니다.'));return;}
 closeReading();cancelSave();busy(true);note('');$('article-content').replaceChildren(text('p','조문 자료를 불러오고 있습니다.','muted'));$('evidence').replaceChildren();$('outside').replaceChildren();detail=wanted=null;
 try{
  const loaded=await data(entry.file);if(token!==epoch)return;doc=loaded;state.law=id;state.query='';$('body-query').value='';
  if(!$('law').querySelector(`option[value="${id}"]`))$('law').prepend(option(id,entry.label+' · 분야 밖 관련 법령'));$('law').value=id;
  $('law-title').textContent=entry.name;$('law-meta').replaceChildren(text('span',`시행 ${entry.effective||'확인 필요'} · ${entry.authority||entry.kind||'수집 자료'} `),link(entry.url,'공식 원문 ↗'));
  renderArticles();$('download-state').textContent='조문과 연결 근거는 필요한 부분만 불러옵니다.';
  for(const message of entry.source_notes||[])$('law-meta').append(text('p',message,'muted small'));
  if(entry.pdf_url)$('law-meta').append(link(entry.pdf_url,'수집 판본 PDF ↗'));
  if(entry.unparsed_provisions?.length){const details=document.createElement('details');details.append(text('summary','조문번호 확인이 필요한 미분석 원문'));for(const item of entry.unparsed_provisions)details.append(text('p',item.reason),text('div',item.raw,'article-body'));$('law-meta').append(details);}
  let a=(usesArticleTags()&&state.sector!=='all'?doc.articles.find(a=>(a.sectors||[]).includes(state.sector)):null)||doc.articles[0];try{const t=target(reference,['fsc','forex'].includes(domain));a=doc.articles.find(a=>a.jo===t.jo)||a;}catch{}
  if(a)await openArticle(reference&&doc.articles.some(a=>{try{return a.jo===target(reference,['fsc','forex'].includes(domain)).jo;}catch{return false;}})?reference:a.label,token);
  else{
   detail=wanted=null;state.reference='';$('reference').value='';
   $('article-content').replaceChildren(text('p',doc.meta.text_analysis?'문단의 명시적 인용 분석 · 지침 내부 문단 간 참조는 미분석':'본문 수집 · 조문 연결 미분석','status-badge'),text('div',readableUnstructured(doc)||'조문 단위로 분석된 본문이 없습니다. 공식 원문을 확인해 주세요.','article-body'));
   currentRows=doc.text_connections?.filter(r=>!r.external)||[];limit=40;renderEvidence();
   $('evidence-count').textContent=doc.text_connections?`${currentRows.length}건`:'';
   $('connection-note').textContent=doc.text_connections?'지침 본문에 명시된 인용입니다. 근거 조문의 본문을 읽거나 그 조문의 연결을 탐색할 수 있습니다.':'';
   $('outside').replaceChildren();
   if(doc.text_connections){
    const notes=document.createElement('details');notes.className='outside-note';const external=doc.text_connections.filter(r=>r.external),issues=doc.text_issues||[];
    notes.append(text('summary',`미수집 인용·해석 확인 ${external.length+issues.length}건`));notes.append(...external.map(r=>evidenceCard(r,true)),...issues.map(i=>text('p',i.raw+' — '+i.reason)));$('outside').append(notes);
   }
   showMap(sectorMap());
  }
  persist();
 }catch(err){if(token===epoch)error(err);}finally{if(token===epoch)busy(false);}
}
async function openArticle(reference,token=++epoch){
 if(!doc)return;closeReading();busy(true);note('');
 try{
  const parsed=target(reference,['fsc','forex'].includes(domain)),a=doc.articles.find(a=>a.jo===parsed.jo);if(!a)throw Error('수집한 본문에 해당 조문이 없습니다. 다른 조문으로 대체하지 않았습니다.');
  const group=doc.details?.[a.jo]?doc.details:await data(a.detail);if(token!==epoch)return;if(!group[a.jo])throw Error('조문 연결 자료를 찾지 못했습니다.');
  wanted=parsed;detail=group[a.jo];state.reference=wanted.label;$('reference').value=wanted.label;$('article').value=a.jo;limit=40;
  const box=$('article-content');box.replaceChildren(text('h3',a.label+' · '+a.title,'article-title'));
  if(a.deleted)box.append(text('p','수집 판본에서 삭제된 조문','status-badge'));
  const meta=document.createElement('div');meta.className='article-meta';meta.append(text('span','시행 '+(a.effective||doc.meta.effective||'확인 필요'),'muted small'));
  const copy=text('button','본문 복사');copy.onclick=async()=>{try{await navigator.clipboard.writeText(doc.meta.name+' '+a.label+'\n'+a.text);copy.textContent='복사됨';}catch{note('본문을 선택해 복사해 주세요.');}};meta.append(copy);box.append(meta,text('div',a.text,'article-body'));
  if(wanted.narrow)box.append(text('p',`본문은 ${a.label} 전체이며 연결은 ${wanted.label} 범위로 대조합니다.`,'muted small'));
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
 const card=document.createElement('article');card.className='evidence-card';const header=document.createElement('header'),title=document.createElement('div');
 title.append(text('span',external?'지도 밖 인용':row.direction==='reverse'?'← 역인용':'직접 인용 →','flow '+(row.direction==='reverse'?'reverse':'')));
 title.append(text('h3',external?(row.target_law+' '+(row.target_ref||'')):(row.neighbor_law+' '+(row.neighbor_ref||row.neighbor_jo||''))));
 if(row.cross_domain)title.append(text('span',bridgeLabel(row),'badge'));else if(row.national)title.append(text('span','전국 수집 조례 · '+(row.source_law||''),'badge'));else if(outsideSector(row))title.append(text('span','분야 밖 관련 조문','badge'));
 header.append(title);
 if(!external&&row.neighbor_id){if(row.neighbor_kind==='annex'&&row.annex_unanalyzed)header.append(link(row.target_url,'별표 공식 원문 ↗'));else{const button=text('button','본문 보기');button.onclick=()=>openReading(row.neighbor_id,row.neighbor_kind==='article'?row.neighbor_jo:'',row.region||relatedLookup().get(row.neighbor_id)?.region||'');header.append(button);}}
 card.append(header,text('blockquote',row.raw||row.cite_raw||''));
 if(row.source_law)card.append(text('p',`${row.source_law} ${row.source_ref||row.source_jo||''} → ${row.target_law||''} ${row.target_ref||''}`));
 card.append(text('p',external?(row.target_status==='collected-not-indexed'?'본문 수집 · 조문 연결 미분석':'미수집 · 본문과 역인용 미점검'):(row.precision||'')+' · '+(row.reason||'')));
 if(row.target_provision_status==='missing-from-collected-body')card.append(text('p','대상 법령은 수집했지만 해당 조문은 수집 판본에 없습니다.'));
 if(row.target_provision_status==='deleted')card.append(text('p','대상은 수집 판본의 삭제 조문입니다.'));
 if(row.cross_domain)card.append(text('p',`출처 시행 ${row.source_effective||'확인 필요'} · 대상 시행 ${row.target_effective||'확인 필요'}`,'muted small'));
 if(row.annex_unanalyzed)card.append(text('p','별표 인용 위치를 확인했습니다. 별표 본문·표 내부 인용은 미분석입니다.','muted small'));
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
 state.cross=$('cross').checked;const connected=combineConnections(detail,doc.broad,cross,doc.meta.id,wanted.jo,state.cross);
 currentRows=refine([...connected.rows,...connected.broad],wanted,state);$('evidence-count').textContent=`${currentRows.length.toLocaleString()}건`;
 $('connection-note').textContent=detail.analysis_error||`${catalog.built_at} 수집 자료 · 인용 문구의 범위를 대조한 결과입니다. 지도는 최대 180개 연결 대상을 표시하며 근거 목록은 모두 열람할 수 있습니다.`;
 if(cross&&state.cross)$('connection-note').textContent+=` 분야 밖 연결 ${currentRows.filter(r=>r.cross_domain).length}건 · 외환 ${cross.editions.forex}, 금융 ${cross.editions.fsc} 수집 판본.`;
 if(crossError)$('connection-note').textContent+=' '+crossError;
 const map=focusMap(currentRows,doc.meta,wanted,sectorMap(),relatedLookup());showMap(map);renderEvidence();
 const external=connected.external.filter(e=>!wanted.narrow||!e.source_scope||refine([{...e,direction:'forward',kind:e.target_kind||'article'}],wanted,{review:true}).length);
 $('outside').replaceChildren();
 if(external.length||connected.issues.length){const section=document.createElement('details');section.className='outside-note';section.append(text('summary',`미수집 인용·해석 확인 ${external.length+connected.issues.length}건`),text('p','미수집 법령 본문과 역인용·별표 본문을 점검한 것으로 해석하지 마세요.','muted small'));
 section.append(...external.map(e=>evidenceCard(e,true)));for(const i of connected.issues)section.append(text('p',(i.raw||'')+' — '+(i.reason||i.kind||i.status||'문맥 확인')));$('outside').append(section);}
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
function readingLabel(jo){return jo?`제${jo.replace('의','조의')}${jo.includes('의')?'':'조'}`:'';}
function renderReadingArticle(jo){
 if(!reading)return;const {entry,document}=reading;const a=document.articles.find(a=>a.jo===jo);
 reading.article=a;reading.requestedJo=jo;reading.copyText=a?entry.name+' '+a.label+'\n'+a.text:(!document.articles.length?readableUnstructured(document):'');
 $('reading-title').textContent=entry.name+(jo?' '+readingLabel(jo):'');
 $('reading-meta').replaceChildren(text('span','시행 '+(a?.effective||entry.effective||'확인 필요')+' '),link(entry.url,'공식 원문 ↗'));
 const body=$('reading-body');body.replaceChildren();$('reading-copy').textContent='본문 복사';$('reading-copy').disabled=!reading.copyText;$('reading-explore').disabled=!a;
 if(a){
  $('reading-status').textContent=a.deleted?'수집 판본에서 삭제된 조문입니다.':'';
  body.append(text('h3',a.title),text('div',a.text,'reading-text'));
 }else if(jo){
  $('reading-status').textContent='수집한 판본에 해당 조문 본문이 없습니다. 공식 원문을 확인해 주세요.';
 }else if(document.articles.length){
  $('reading-status').textContent='수집된 법령 본문에서 읽을 조문을 선택해 주세요.';
 }else{
  $('reading-status').textContent=document.meta.text_analysis?'문단 인용 분석 · 지침 내부 문단 간 참조는 미분석':'본문 수집 · 조문 연결 미분석';
  body.append(text('div',readableUnstructured(document)||'수집된 본문이 없습니다. 공식 원문을 확인해 주세요.','reading-text'));
 }
 $('reading-scroll').scrollTop=0;
}
async function openReading(id,jo='',region=''){
 const token=++readingEpoch,anchor=epoch,context={catalog,lookup:relatedLookup(),currentDoc:doc,read:data};reading=null;
 $('reading-title').textContent='연결 조문 본문';$('reading-context').textContent='검토 기준 · '+(doc?.meta.name||$('heading').textContent)+' '+(wanted?.label||'');
 $('reading-status').textContent='본문을 불러오고 있습니다.';$('reading-meta').replaceChildren();$('reading-body').replaceChildren();$('reading-picker').hidden=true;
 $('reading-copy').disabled=true;$('reading-explore').disabled=true;
 if(document.fullscreenElement){try{await document.exitFullscreen();}catch{}}
 if(token!==readingEpoch||anchor!==epoch)return;
 if(!$('reading').open)$('reading').showModal();
 try{
  const result=await loadReading({id,jo,region},context);if(token!==readingEpoch||anchor!==epoch)return;
  reading=result;$('reading-picker').hidden=!!jo||!result.document.articles.length;
  $('reading-article').replaceChildren(option('','읽을 조문을 선택하세요'),...result.document.articles.map(a=>option(a.jo,a.label+' · '+a.title)));
  renderReadingArticle(jo);
 }catch(err){if(token===readingEpoch&&anchor===epoch)$('reading-status').textContent=err.message||'본문을 불러오지 못했습니다. 인터넷 연결 또는 저장 자료를 확인해 주세요.';}
}
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
$('law-query').oninput=renderLaws;
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
 const unique=[...new Map(refs.map(r=>[r.url,r])).values()];$('save-law').textContent='저장 멈추기';
 try{await saveAll(unique,(i,n)=>{if(controller===saveController)$('download-state').textContent=`${displayLaw(entry)} 자료 저장 중 · ${i}/${n}`;},controller.signal);if(controller!==saveController)return;
  const verified=await Promise.all(unique.map(cached));
  const registration=await navigator.serviceWorker?.getRegistration();if(controller!==saveController)return;if(!registration?.active){$('download-state').textContent='자료는 저장했지만 오프라인 화면 준비가 끝나지 않았습니다. 연결된 상태에서 한 번 새로고침해 주세요.';return;}$('download-state').textContent=verified.every(Boolean)?`${displayLaw(entry)} 본문·인용 근거 저장 완료. 연결 대상의 본문은 해당 법령을 열 때 받습니다.`:'일부 자료를 저장하지 못했습니다. 저장 공간·인터넷 연결을 확인해 주세요.';
 }catch(err){if(controller===saveController)error(err);}finally{if(controller===saveController){saveController=null;$('save-law').textContent='이 법령 오프라인 저장';}}
};
$('about-open').onclick=()=>$('about').showModal();
$('coverage-open').onclick=()=>{
 const content=$('coverage-copy');content.replaceChildren(text('p',`${$('heading').textContent} · 수집 기준 ${catalog?.built_at||''}`),text('p',catalog?.workbench?'수집한 본칙의 명시적 인용을 분석합니다. 별표·서식 본문·부칙은 미분석이며, 외부 법령의 본문·역인용은 점검하지 않았습니다. 불명확한 인용은 확인 목록에 보존합니다.':catalog?.coverage||''),text('p','항·호·목 범위를 포함한 저장 인용을 대조합니다. 새 항 신설의 취지 추론·의미상 유사성·신설 조문 검토는 이 무료 열람 버전에 포함하지 않습니다.'),text('p','이 웹사이트는 공개 법령 본문과 분석 결과만 제공합니다. 법제처 API 인증값이나 개정안 업로드 기능은 포함하지 않습니다.'));
 const work=catalog?.workbench;
 const summary=catalog?.collection_summary;
 if(summary){
  content.append(text('p',`법령 ${summary.statutes}건 · 행정규칙 ${summary.administrative_rules}건 · 조문 분석 ${summary.indexed_documents}개 문서 / ${summary.articles}개 조문`),text('p',`문단 인용 분석 ${summary.text_analyzed_documents}개 문서 · 명시적 인용 ${summary.text_citations}건 · 시행예정 ${summary.scheduled}건은 현재 지도에서 제외했습니다.`),text('p',`해석 확인 목록: 조문 ${summary.unresolved}건 · 지침 문단 ${summary.text_unresolved}건. 인용 대상이나 범위를 확정하지 못한 사례는 근거 목록에서 구분합니다.`));
 }
 if(work){content.append(text('h3','이 분야에서 확인할 수 있는 것'),text('p',work.purpose));for(const message of work.limitations)content.append(text('p',message));content.append(text('p','업무 태그는 제목·본문 키워드에 따른 탐색 보조 분류입니다. 법적 적용 범위의 판정이 아닙니다. 지도에 쓰는 짧은 이름은 표시용 약칭이며, 공식 명칭은 본문 상단에서 확인합니다.'));
  for(const source of work.companion_sources){const p=document.createElement('p');p.append(link(source.url,source.title+' ↗'));content.append(p);}
  if(work.unindexed.length){const details=document.createElement('details');details.append(text('summary',`조문 연결 미분석 자료 ${work.unindexed.length}건`));for(const item of work.unindexed){const p=document.createElement('p');p.append(link(item.url,item.name+' ↗'),text('span',' · '+item.status));details.append(p);}content.append(details);}
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
  if('serviceWorker'in navigator)navigator.serviceWorker.register('./sw.js').catch(()=>{});
  let active='tax';try{active=localStorage.getItem(stateKey+':active')||'tax';}catch{}
  await navigate(manifest.domains.some(d=>d.id===active)?active:'tax');
 }catch(err){error(err);}
}
start();
