import {quoteHighlights} from './reading.mjs';
import {annexReference,annexSources,appendAnnexSources} from './annex-links.mjs';
export function renderAnnex(body,annex,rows,{text,link,read,ownerUrl='',currentDoc=null}){
 body.append(text('h3',annex.title));
 const sources=text('p','','annex-sources');
 appendAnnexSources(sources,annexSources(annex.urls,ownerUrl),{text,link});
 body.append(sources);
 const a=annex.analysis;if(!a){body.append(text('p','이 별표 본문은 미분석입니다. 공식 원본에서 내용을 확인하세요.','muted'));return;}
 body.append(text('p',a.reading_note||'원문을 칸·문단 순서로 읽습니다. 병합 칸의 기관별 귀속·표 내부 참조·정원과 면적 산식은 미판정입니다. 적용 조건과 표 배치는 공식 원본을 함께 확인하세요.','muted small'));
 if(a.citation_status==='zero-explicit-citations')body.append(text('p','별표 본문 분석 완료 · 명시적 법령 인용 0건. 표의 내용과 적용 조건은 공식 원본을 함께 확인하세요.','muted small'));
 for(const issue of a.issues||[])body.append(text('p',issue,'muted small'));
 if(annex.issues?.length){const issues=document.createElement('details');issues.append(text('summary',`별표 인용 해석 확인 ${annex.issues.length}건`));for(const issue of annex.issues)issues.append(text('p',`${issue.source_ref||''} · ${issue.raw} — ${issue.reason}`,'muted small'));body.append(issues);}
 const quotes=rows.filter(r=>r.source_layer==='annex-body'&&r.source_jo===annex.ref&&r.direction==='reverse');
 const ranges=quotes.flatMap(r=>quoteHighlights(a.text,r).ranges),marks=[];
 for(const unit of a.units){
  const section=text('section','','annex-unit');section.append(text('small',/^Contents\//.test(unit.locator)?'별표 본문':unit.locator,'muted'));
  const line=text('p','','annex-text'),base=Array.from(a.text).slice(0,unit.start).join('').length;
  let end=0;
  const local=ranges.map(([x,y])=>[Math.max(x-base,0),Math.min(y-base,unit.text.length)]).filter(([x,y])=>y>x).sort((a,b)=>a[0]-b[0]);
  for(const [x,y] of local){if(x<end)continue;line.append(document.createTextNode(unit.text.slice(end,x)));const mark=text('mark',unit.text.slice(x,y),'citation-hit');line.append(mark);marks.push(mark);end=y;}
  line.append(document.createTextNode(unit.text.slice(end)));section.append(line);body.append(section);
 }
 if(marks.length){let i=0;const b=text('button',`인용 위치 ${1} / ${marks.length}`,'quiet');b.onclick=()=>{marks[i].scrollIntoView({block:'center',behavior:'instant'});b.textContent=`인용 위치 ${i+1} / ${marks.length}`;i=(i+1)%marks.length;};body.prepend(b);}
 const connections=annex.connections||[];
 if(connections.length){const box=document.createElement('details');box.append(text('summary',`이 별표가 인용하는 법령 · 근거 ${connections.length}건`));
  for(const r of connections){const p=text('div','','annex-citation');p.append(text('strong',r.target_law+' '+r.target_ref),text('p',r.context,'muted small'));
   const relatedAnnex=annexReference(r,{currentDoc,external:!!r.external});
   if(relatedAnnex){appendAnnexSources(p,relatedAnnex,{text,link});if(!r.external&&relatedAnnex.id&&relatedAnnex.analyzed){const b=text('button','검증된 별표 본문 보기');b.onclick=()=>read(relatedAnnex.id,relatedAnnex.ref,'',[r]);p.append(b);}}
   else if(r.neighbor_id&&r.neighbor_kind==='article'){const b=text('button','인용 조문 본문 보기');b.onclick=()=>read(r.neighbor_id,r.neighbor_jo,'',[r]);p.append(b);}else p.append(text('p','미수집 또는 조문 미확정 · 본문·역인용 미점검','muted small'),link(r.target_url,'공식 원문 ↗'));
   box.append(p);
  }body.append(box);
 }
}
