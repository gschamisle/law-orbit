// The Python build emits parsed scopes; this module evaluates those scopes.
// Law resolution and citation parsing remain in the shared Python engine.
export const labels={exact:'직접 인용',range:'범위 포함',covering:'상위 조문 인용',contained:'하위 조문 인용',review:'문맥 확인'};
export function normalize(value){return String(value||'').replace(/\s/g,'').toLocaleLowerCase();}
export function target(input,hyphen=false){
 let text=normalize(input);if(/^\d+(?:-\d+)*(?:의\d+)?$/.test(text))text=text.replace(/^(\d+(?:-\d+)*)(?:의(\d+))?$/,(_,a,b)=>`제${a}조${b?'의'+b:''}`);
 const match=text.match(/^제(\d+(?:-\d+)*)조(?:의(\d+))?(?:제(\d+)항)?(?:제(\d+)호(?:의(\d+))?)?(?:([가-하])목)?$/);
 if(!match||(!hyphen&&match[1].includes('-'))||(match[6]&&!match[4]))throw Error('제16조 또는 제16조제2항제1호처럼 입력해 주세요.');
 const num=v=>v?v.split('-').map(n=>{if(Number(n)<1)throw Error('조문 번호는 1 이상이어야 합니다.');return String(Number(n));}).join('-'):'';
 const jo=num(match[1])+(match[2]?'의'+num(match[2]):''),hang=num(match[3]),ho=num(match[4])+(match[5]?'의'+num(match[5]):''),mok=match[6]||'';
 return {jo,path:[jo,hang,ho,mok],label:`제${jo.replace('의','조의')}${jo.includes('의')?'':'조'}${hang?'제'+hang+'항':''}${ho?'제'+ho.replace('의','호의')+(ho.includes('의')?'':'호'):''}${mok?mok+'목':''}`,narrow:!!(hang||ho||mok)};
}
function number(v){let [base,sub='0']=v.split('의');return [base.split('-').map(Number),Number(sub)];}
function compare(a,b){a=number(a);b=number(b);for(let i=0;i<Math.max(a[0].length,b[0].length);i++){if(i>=a[0].length)return -1;if(i>=b[0].length)return 1;if(a[0][i]!==b[0][i])return a[0][i]-b[0][i];}return a[1]-b[1];}
function relation([start,end,axis],wanted){
 for(let i=0;i<4;i++){
  const a=start[i],b=end[i],w=wanted[i];
  if(!w){if(!wanted.slice(i).some(Boolean))return start.slice(i).some(Boolean)?'contained':'exact';if(!a)continue;return 'review';}
  if(!a)return start.slice(i+1).some(Boolean)?'review':'covering';
  if(axis===i){if(i===3)return null;if(compare(a,w)>0||compare(w,b)>0)return null;return 'range';}
  if(a!==w)return null;
 }return 'exact';
}
export function classify(parsed,wanted){
 if(parsed?.review_reason)return 'review';
 const matches=(parsed?.scopes||[]).map(s=>relation(s,wanted.path));
 return ['review','exact','range','covering','contained'].find(s=>matches.includes(s))||'disjoint';
}
export function refine(rows,wanted,{direction='both',review=true,kinds=['article','law','annex','standard'],broad=false}={}){
 return rows.flatMap(original=>{
  const row={...original};if(row.broad&&!broad)return [];
  if(row.direction==='reverse'&&!row.broad){
   const status=classify(row.raw_scope,wanted);
   if(status==='disjoint'&&!row.record_review)return [];
   if(row.status!=='review'){row.status=status;row.precision=labels[status];}
   row.target_ref=wanted.label;
  }else if(row.direction==='forward'&&wanted.narrow){
   const status=classify(row.source_scope,wanted);if(status==='disjoint')return [];
   if(row.source_granularity!=='block'||['covering','review'].includes(status)){
    row.status='review';row.precision=labels.review;
    row.reason='출처가 조 단위 또는 상위 단위로 저장되어 선택한 항·호·목 안의 인용인지는 원문 확인이 필요합니다. '+(row.reason||'');
   }
  }
  if((direction!=='both'&&row.direction!==direction)||(!review&&row.status==='review')||!kinds.includes(row.kind||'article'))return [];
  return [row];
 });
}
export function matchingArticles(articles,query){const words=query.split(/\s+/).filter(Boolean).map(normalize);return articles.filter(a=>words.every(t=>normalize(a.label+' '+a.title+' '+a.text).includes(t)));}
export function safeLink(value){try{const u=new URL(value);return ['https:','http:'].includes(u.protocol)&&!u.username&&!u.password?u.href:'';}catch{return '';}}
export function focusMap(rows,entry,wanted,overview,lookup){
 const grouped=new Map();
 for(const r of rows){const key=(r.neighbor_id||r.neighbor_law)+'|'+r.neighbor_kind+'|'+r.neighbor_jo;if(!grouped.has(key))grouped.set(key,[]);grouped.get(key).push(r);}
 const center='selected',nodes=[],links=[];nodes.push({id:center,label:entry.label,subtitle:wanted.label,family:entry.name,color:'#e4f7ff',count:grouped.size,x:0,y:0,z:0,title:entry.name,is_target:true,evidence:[],web_law:entry.id,web_jo:wanted.jo,web_region:entry.region});
 let i=0;for(const [id,evidence] of [...grouped].slice(0,180)){
  const r=evidence[0],d=lookup.get(r.neighbor_id),angle=i*Math.PI*(3-Math.sqrt(5)),radius=450*Math.sqrt(.40+.60*(i+.5)/Math.max(grouped.size,1));i++;
  const dirs=new Set(evidence.map(e=>e.direction));const color=evidence.every(e=>e.status==='review')?'#e8a1cc':dirs.size>1?'#b5a1ff':r.direction==='forward'?'#66e5ed':'#ffc77a';
  nodes.push({id,label:d?.label||r.neighbor_law,full_name:r.neighbor_law,subtitle:r.neighbor_ref||r.neighbor_jo,family:r.neighbor_law,color,count:evidence.length,x:Math.cos(angle)*radius,y:Math.sin(angle)*radius*.85,z:Math.sin(angle*1.5)*100,title:r.neighbor_title||'연결된 조문',evidence,status:(r.cross_domain?'분야 밖 관련 조문 · ':'')+(dirs.size>1?'인용 · 역인용':r.direction==='forward'?'직접 인용':'역인용'),web_law:r.annex_unanalyzed&&r.neighbor_kind==='annex'?'':r.neighbor_id,web_jo:r.neighbor_kind==='article'?r.neighbor_jo:'',web_region:r.region||d?.region||''});
  for(const direction of dirs){const rev=evidence.filter(e=>e.direction===direction).every(e=>e.status==='review');links.push({a:direction==='forward'?center:id,b:direction==='forward'?id:center,n:evidence.filter(e=>e.direction===direction).length,direction,color:rev?'#e8a1cc':direction==='forward'?'#66e5ed':'#ffc77a',dashed:rev});}
 }
 return {...overview,nodes,dust:[],links,all_links:links,mode:'spotlight',target:entry.name+' '+wanted.label,focus:center,direction:'인용 + 역인용',evidence_count:rows.length,article_count:grouped.size+1,neighbor_count:grouped.size};
}
