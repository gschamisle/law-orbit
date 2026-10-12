// Optional evidence overlay. Catalogs, selections and original shards stay separate.
export const bridgePeers = {
  forex: 'fsc',
  fsc: 'forex',
  procurement: 'public_institutions',
  public_institutions: 'procurement',
};
export const bridgeNames = {
  forex: '외환',
  fsc: '금융',
  procurement: '조달·계약',
  public_institutions: '공공기관',
  integrity: '청렴·권익',
  subsidy: '보조금·지원사업',
};
export function bridgeEditions(bridge) {
  return Object.entries(bridge.editions)
    .map(([id, date]) => `${bridgeNames[id]} ${date}`)
    .join(', ');
}
export function validateBridge(value, domain, manifest, catalog) {
  const peer = value.peer;
  const integrityPeer = domain === 'integrity' ? peer : peer === 'integrity' ? domain : '';
  const kind = ['procurement', 'public_institutions', 'subsidy'].includes(integrityPeer)
    ? `integrity-${integrityPeer}-bridge`
    : peer === bridgePeers[domain]
      ? (['forex', 'fsc'].includes(domain) ? 'forex-finance-bridge' : 'procurement-public-bridge')
      : null;
  if (
    !peer || !kind ||
    value.kind !== kind ||
    value.schema !== 1 ||
    value.domain !== domain ||
    value.peer !== peer
  )
    throw Error('분야 간 연결 자료의 범위가 맞지 않습니다.');
  const other = manifest.domains.find((d) => d.id === peer);
  if (value.editions[domain] !== catalog.built_at || value.editions[peer] !== other?.built_at)
    throw Error('분야 간 연결 자료와 본문의 수집 판본이 다릅니다.');
  if (
    value.entries.some((e) => e.domain !== peer) ||
    new Set(value.entries.map((e) => e.id)).size !== value.entries.length
  )
    throw Error('연결 대상의 분야 정보가 올바르지 않습니다.');
  const own = new Set(catalog.laws.map((e) => e.id)),
    foreign = new Set(value.entries.map((e) => e.id));
  for (const [id, articles] of Object.entries(value.laws)) {
    if (!own.has(id)) throw Error('연결 출처를 찾을 수 없습니다.');
    for (const detail of Object.values(articles))
      for (const row of detail.rows) {
        if (!foreign.has(row.neighbor_id) || row.neighbor_domain !== peer || !row.cross_domain)
          throw Error('분야 간 연결 대상이 올바르지 않습니다.');
        if (
          row.direction === 'forward'
            ? row.source_id !== id || row.target_id !== row.neighbor_id
            : row.target_id !== id || row.source_id !== row.neighbor_id
        )
          throw Error('인용 방향 정보가 올바르지 않습니다.');
      }
  }
  for (const [id, rows] of Object.entries(value.broad))
    if (
      !own.has(id) ||
      rows.some((r) => !foreign.has(r.neighbor_id) || !r.broad || r.direction !== 'reverse')
    )
      throw Error('법령 전체 참조 정보가 올바르지 않습니다.');
  return value;
}
export function combineConnections(detail, broad, bridge, id, jo, enabled = true) {
  if (!enabled || !bridge) return { ...detail, rows: [...detail.rows], broad: [...broad] };
  const extra = bridge.laws[id]?.[jo],
    hidden = new Set(extra?.suppressed || []),
    resolved = new Set(extra?.resolved_issues || []);
  return {
    ...detail,
    rows: [...detail.rows, ...(extra?.rows || [])],
    broad: [...broad, ...(bridge.broad[id] || [])],
    external: detail.external.filter((e) => !hidden.has(e.evidence_id)),
    issues: detail.issues.filter((i) => !resolved.has(i.raw)),
  };
}
export function bridgeLookup(lookup, bridge) {
  return new Map([...lookup, ...(bridge?.entries || []).map((e) => [e.id, e])]);
}
export function bridgeLabel(row) {
  if (!row.cross_domain) return '';
  if (row.neighbor_domain !== 'fsc')
    return '분야 밖 관련 조문 · ' + (bridgeNames[row.neighbor_domain] || '확인 필요');
  const sectors = {
    banking: '은행',
    securities: '증권·자산운용',
    insurance: '보험',
    credit: '여신·서민금융',
    digital: '전자금융',
    common: '공통',
  };
  const tags = (row.neighbor_sectors || []).map((s) => sectors[s]).filter(Boolean);
  return '분야 밖 관련 조문 · 금융' + (tags.length ? ' / ' + tags.join('·') : '');
}

// Each pair retains its own source and target editions. The aggregate is only
// a reading overlay; original catalogs and their selections are not modified.
export async function loadBridgeGroup(value, domain, manifest, catalog, read) {
  if (value.kind !== 'domain-bridge-set') return validateBridge(value, domain, manifest, catalog);
  if (value.schema !== 1 || value.domain !== domain || !Array.isArray(value.bridges) || !value.bridges.length)
    throw Error('분야 간 연결 묶음의 범위가 맞지 않습니다.');
  const parts = await Promise.all(value.bridges.map(async ref => validateBridge(await read(ref), domain, manifest, catalog)));
  if (new Set(parts.map(p => p.peer)).size !== parts.length) throw Error('분야 간 연결이 중복되었습니다.');
  const out = { domain, bridgeRefs: [...value.bridges], peers: parts.map(p => p.peer), editions: {}, entries: [], laws: {}, broad: {}, coverage: parts.map(p => p.coverage || '').join(' ') };
  const entries = new Map();
  for (const part of parts) {
    for (const [id, edition] of Object.entries(part.editions)) {
      if (out.editions[id] && out.editions[id] !== edition) throw Error('연결 묶음의 판본이 서로 다릅니다.');
      out.editions[id] = edition;
    }
    for (const entry of part.entries) {
      if (entries.has(entry.id) && JSON.stringify(entries.get(entry.id)) !== JSON.stringify(entry))
        throw Error('연결된 본문의 판본이 중복됩니다.');
      entries.set(entry.id, entry);
    }
    for (const [id, articles] of Object.entries(part.laws)) {
      out.laws[id] ||= {};
      for (const [jo, detail] of Object.entries(articles)) {
        const target = out.laws[id][jo] ||= { rows: [], suppressed: [], resolved_issues: [] };
        target.rows.push(...detail.rows);
        for (const key of ['suppressed', 'resolved_issues']) target[key] = [...new Set([...target[key], ...(detail[key] || [])])];
      }
    }
    for (const [id, rows] of Object.entries(part.broad)) (out.broad[id] ||= []).push(...rows);
  }
  out.entries = [...entries.values()];
  return out;
}
