const compact=s=>String(s||'').replace(/\s/g,'');
export function selectScope(records,{anchor='',label='',query='',indirect=true}={}){
 return records.filter(r=>(!anchor||r.target_jo===anchor)&&(!label||r.labels.includes(label))&&(indirect||r.kind!=='indirect')&&compact(r.source_law+' '+r.context).includes(compact(query)));
}
export function changeCandidates(records,event){
 const unique=new Map();
 for(const r of records.filter(r=>r.kind==='scope'))unique.set(r.source_law+'|'+r.source_ref,r);
 return [...unique.values()].sort((a,b)=>(event.kind==='changed'?Number(!a.labels.includes('subset'))-Number(!b.labels.includes('subset')):Number(!['4','6'].includes(a.target_jo))-Number(!['4','6'].includes(b.target_jo)))||a.source_law.localeCompare(b.source_law,'ko'));
}
export function mountPublicScope(host,register,actions){
 if(!register)return;
 const el=(tag,value='',cls='')=>{const e=document.createElement(tag);e.textContent=value;if(cls)e.className=cls;return e;};
 const button=(label,run)=>{const b=el('button',label,'quiet');b.type='button';b.onclick=run;return b;};
 const option=(value,label)=>{const o=el('option',label);o.value=value;return o;};
 const read=(law,jo)=>actions.read(law,jo);
 const section=el('details','','public-scope');section.append(el('summary','정의·적용범위 검토'));
 const nav=el('div','','scope-tabs');nav.setAttribute('role','tablist');nav.setAttribute('aria-label','공공기관 검토 종류');
 const body=el('section');body.id='public-scope-panel';body.setAttribute('role','tabpanel');section.append(nav,body);host.append(section);
 function badges(parent,labels){const line=el('div','','scope-badges');for(const key of labels)line.append(el('span',register.labels[key]||key,'badge'));parent.append(line);}
 function card(r){
  const c=el('article','','scope-card');const h=el('header');h.append(el('h3',r.source_law+' '+r.source_ref),button('본문 보기',()=>read(r.source_law,r.source_jo)));c.append(h);badges(c,r.labels);
  const path=el('div','','scope-path');
  const steps=[...r.path.map(s=>({law:s.law,jo:s.jo,ref:s.source_ref})),{law:r.target_law,jo:r.target_jo,ref:r.target_ref}];
  steps.forEach((s,i)=>{if(i)path.append(el('span',' → '));path.append(button(`${s.law} ${s.ref||`제${s.jo}조`}`,()=>read(s.law,s.jo)));});c.append(path);
  c.append(el('blockquote',r.context));
  if(r.kind==='indirect')c.append(el('p','정의 조문을 경유한 검토 경로입니다. 직접 인용 건수와 구분합니다.','muted small'));
  const more=el('details');more.append(el('summary','인용 문구·시행일'),el('p',r.raw),el('p','출처 조문 시행 '+r.effective,'muted small'),actions.link(r.source_url,'공식 원문 ↗'));c.append(more);
  return c;
 }
 function scope(){
  body.replaceChildren(el('p',register.coverage,'muted small'));
  const fields=el('div','','scope-fields');const anchor=el('select'),label=el('select'),query=el('input');query.type='search';query.placeholder='법령명·근거 문구 검색';
  anchor.append(option('','공운법 기준 전체'),...['2','4','5','6'].map(j=>option(j,`공운법 제${j}조`)));
  label.append(option('','관계 전체'),...['subset','designated','criteria','additional','exclusion','other-bases','law-definition','indirect'].map(k=>option(k,register.labels[k])));
  for(const [name,input] of [['기준 조문',anchor],['관계 유형',label],['근거 검색',query]]){const l=el('label',name);input.setAttribute('aria-label',name);l.append(input);fields.append(l);}
  const list=el('div'),status=el('p','','muted small');status.setAttribute('role','status');body.append(fields,status,list);
  const go=button('선택 기준의 연결 지도 보기',()=>actions.explore(register.anchors[0].law,anchor.value||'4',true));fields.append(go);
  function render(){const rows=selectScope(register.records,{anchor:anchor.value,label:label.value,query:query.value});status.textContent=`직접 근거 ${rows.filter(r=>r.kind==='scope').length}건 · 정의 경유 경로 ${rows.filter(r=>r.kind==='indirect').length}건`;
   if(rows.some(r=>r.target_kind==='law'))status.textContent+=' · 조 번호 없는 법령 참조 포함';
   list.replaceChildren(...rows.map(card));if(!rows.length)list.append(el('p','조건에 맞는 수집 근거가 없습니다. 적용 대상이 없다는 뜻은 아닙니다.','empty'));}
  anchor.onchange=label.onchange=query.oninput=render;render();
 }
 function privatization(){
  body.replaceChildren(el('p','대상기업 열거와 적용배제 조건을 함께 읽습니다. 과거 기관명을 현재 기관에 자동 대응하거나 법률 간 우열을 판정하지 않습니다.','muted small'));
  for(const guide of register.privatization){const c=el('article','','scope-card'),head=el('header');
   head.append(el('h3',`제${guide.jo}조 · ${guide.title}`),button('본문 보기',()=>read(guide.law,guide.jo)));c.append(head);badges(c,guide.labels);
   const text=el('details');text.append(el('summary','조문 전체·조건 확인'),el('div',guide.text,'scope-original'));c.append(text);
   const refs=el('div','','scope-path');const seen=new Set();for(const r of guide.related){const id=r.law+'|'+r.jo;if(seen.has(id))continue;seen.add(id);
    if(r.collected)refs.append(button(r.law+(r.jo?' 제'+r.jo+'조':''),()=>read(r.law,r.jo)));
    else refs.append(actions.link(r.url,r.law+' · 미수집'));
   }c.append(refs,button('이 조문의 연결 지도',()=>actions.explore(guide.law,guide.jo,false)));body.append(c);
  }
 }
 function designations(){
  const d=register.designations;body.replaceChildren();
  if(!d){body.append(el('p','지정 변경 자료 미수집','muted'));return;}
  body.append(el('p',d.coverage,'muted small'));
  const fields=el('div','','scope-fields'),year=el('select'),query=el('input');query.type='search';query.placeholder='기관명 검색';
  year.append(option('','연도 전체'),...[...new Set(d.events.map(e=>e.year))].sort().reverse().map(y=>option(y,y+'년 발표')));
  for(const [name,input] of [['발표 연도',year],['기관 찾기',query]]){const l=el('label',name);input.setAttribute('aria-label',name);l.append(input);fields.append(l);}const list=el('div');body.append(fields,list);
  function render(){list.replaceChildren();
   const events=d.events.filter(e=>(!year.value||String(e.year)===year.value)&&compact(e.name).includes(compact(query.value))).sort((a,b)=>b.year-a.year||a.kind.localeCompare(b.kind));
   if(!events.length)list.append(el('p','해당 이름의 변경 발표가 이 자료에 없습니다. 현재 지정 여부를 판단할 수 없습니다.','muted'));
   for(const e of events){const s=d.sources.find(s=>s.id===e.source_id),c=el('article','','scope-card');c.append(el('h3',e.name),el('p',`${e.before||'신규 지정'} → ${e.after}`,'scope-transition'),el('p',`${e.year}년 · 발표 ${s.announced} · ${e.authority} · 실제 적용일 별도 확인`,'muted small'));
    c.append(actions.link(s.pdf_url+`#page=${s.page}`,`공식 발표 ${s.page}쪽 ↗`));
    const evidence=el('details');evidence.append(el('summary','변경 근거 표'),el('pre',s.page_text,'scope-original'));c.append(evidence);
    const related=el('details');related.append(el('summary','다시 확인할 규정'),el('p',e.review_basis,'muted small'));
    related.addEventListener('toggle',()=>{if(related.open&&!related.dataset.loaded){related.dataset.loaded='yes';
      for(const r of changeCandidates(register.records,e)){const line=el('div','','scope-change-ref');line.append(button(r.source_law+' '+r.source_ref,()=>read(r.source_law,r.source_jo)),el('small',r.labels.map(k=>register.labels[k]).join(' · ')));related.append(line);}
    }});c.append(related);list.append(c);
   }
  }year.onchange=query.oninput=render;render();
 }
 const tabs=[['정의·적용범위',scope],['민영화·특례',privatization],['지정 변경',designations]];
 tabs.forEach(([title,render],i)=>{const b=button(title,()=>{for(const t of nav.children)t.setAttribute('aria-selected',String(t===b));render();});b.setAttribute('role','tab');b.setAttribute('aria-controls',body.id);b.setAttribute('aria-selected',String(i===0));nav.append(b);});
 let loaded=false;section.addEventListener('toggle',()=>{if(section.open&&!loaded){loaded=true;scope();}});
}
