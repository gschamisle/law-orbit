// Optional evidence overlay. Catalogs, selections and original shards stay separate.
export const bridgePeers={forex:'fsc',fsc:'forex',procurement:'public_institutions',public_institutions:'procurement'};
export const bridgeNames={forex:'외환',fsc:'금융',procurement:'조달계약',public_institutions:'공공기관'};
export function bridgeEditions(bridge){return Object.entries(bridge.editions).map(([id,date])=>`${bridgeNames[id]} ${date}`).join(', ');}
export function validateBridge(value,domain,manifest,catalog){
 const peer=bridgePeers[domain],kind=['forex','fsc'].includes(domain)?'forex-finance-bridge':'procurement-public-bridge';
 if(!peer||value.kind!==kind||value.schema!==1||value.domain!==domain||value.peer!==peer)throw Error('분야 간 연결 자료의 범위가 맞지 않습니다.');
 const other=manifest.domains.find(d=>d.id===peer);
 if(value.editions[domain]!==catalog.built_at||value.editions[peer]!==other?.built_at)throw Error('분야 간 연결 자료와 본문의 수집 판본이 다릅니다.');
 if(value.entries.some(e=>e.domain!==peer)||new Set(value.entries.map(e=>e.id)).size!==value.entries.length)throw Error('연결 대상의 분야 정보가 올바르지 않습니다.');
 const own=new Set(catalog.laws.map(e=>e.id)),foreign=new Set(value.entries.map(e=>e.id));
 for(const [id,articles] of Object.entries(value.laws)){
  if(!own.has(id))throw Error('연결 출처를 찾을 수 없습니다.');
  for(const detail of Object.values(articles))for(const row of detail.rows){
   if(!foreign.has(row.neighbor_id)||row.neighbor_domain!==peer||!row.cross_domain)throw Error('분야 간 연결 대상이 올바르지 않습니다.');
   if(row.direction==='forward'?(row.source_id!==id||row.target_id!==row.neighbor_id):(row.target_id!==id||row.source_id!==row.neighbor_id))throw Error('인용 방향 정보가 올바르지 않습니다.');
  }
 }
 for(const [id,rows] of Object.entries(value.broad))if(!own.has(id)||rows.some(r=>!foreign.has(r.neighbor_id)||!r.broad||r.direction!=='reverse'))throw Error('법령 전체 참조 정보가 올바르지 않습니다.');
 return value;
}
export function combineConnections(detail,broad,bridge,id,jo,enabled=true){
 if(!enabled||!bridge)return {...detail,rows:[...detail.rows],broad:[...broad]};
 const extra=bridge.laws[id]?.[jo],hidden=new Set(extra?.suppressed||[]),resolved=new Set(extra?.resolved_issues||[]);
 return {...detail,rows:[...detail.rows,...(extra?.rows||[])],broad:[...broad,...(bridge.broad[id]||[])],
  external:detail.external.filter(e=>!hidden.has(e.evidence_id)),issues:detail.issues.filter(i=>!resolved.has(i.raw))};
}
export function bridgeLookup(lookup,bridge){return new Map([...lookup,...(bridge?.entries||[]).map(e=>[e.id,e])]);}
export function bridgeLabel(row){
 if(!row.cross_domain)return '';
 if(row.neighbor_domain!=='fsc')return '분야 밖 관련 조문 · '+(bridgeNames[row.neighbor_domain]||'확인 필요');
 const sectors={banking:'은행',securities:'증권·자산운용',insurance:'보험',credit:'여신·서민금융',digital:'전자금융',common:'공통'};
 const tags=(row.neighbor_sectors||[]).map(s=>sectors[s]).filter(Boolean);
 return '분야 밖 관련 조문 · 금융'+(tags.length?' / '+tags.join('·'):'');
}
