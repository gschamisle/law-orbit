import { evidenceKey } from './reading.mjs';

// Use all stored law edges, not the subset drawn in the field overview.
// Self-citations belong to article exploration and are not neighboring laws.
export function lawNeighbors(overview, name) {
  const nodes = new Map((overview.nodes || []).map((n) => [n.id, n]));
  const result = new Map();
  for (const edge of overview.all_links || overview.links || []) {
    if (edge.a === edge.b || (edge.a !== name && edge.b !== name)) continue;
    const id = edge.a === name ? edge.b : edge.a;
    if (!nodes.has(id)) continue;
    if (!result.has(id)) result.set(id, { node: nodes.get(id), forward: false, reverse: false });
    result.get(id)[edge.a === name ? 'forward' : 'reverse'] = true;
  }
  return [...result.values()].sort((a, b) =>
    (a.node.full_name || a.node.id).localeCompare(b.node.full_name || b.node.id, 'ko'),
  );
}

export function lawOverview(overview, entry) {
  const peers = lawNeighbors(overview, entry.name);
  const original = (overview.nodes || []).find((n) => n.id === entry.name) || {};
  const nodes = [{
    ...original, id: entry.name, label: entry.label || entry.name, full_name: entry.name,
    web_law: entry.id, web_jo: '', x: 0, y: 0, z: 0,
    color: '#e4f7ff', count: peers.length, is_target: true,
  }];
  peers.forEach(({ node, forward, reverse }, i) => {
    const angle = i * Math.PI * (3 - Math.sqrt(5));
    const radius = 320 + 190 * Math.sqrt((i + 1) / peers.length);
    nodes.push({ ...node, web_jo: '',
      x: Math.cos(angle) * radius, y: Math.sin(angle) * radius * .8,
      z: Math.sin(angle * 1.5) * 90,
      color: forward && reverse ? '#b5a1ff' : forward ? '#66e5ed' : '#ffc77a',
    });
  });
  const names = new Set(nodes.map((n) => n.id));
  const links = (overview.all_links || overview.links || []).filter((e) =>
    e.a !== e.b && (e.a === entry.name || e.b === entry.name) && names.has(e.a) && names.has(e.b),
  ).map((e) => ({ ...e, color: e.a === entry.name ? '#66e5ed' : '#ffc77a' }));
  return { ...overview, mode: 'law-overview', nodes, dust: [], links, all_links: links,
    galaxy_title: entry.name, overview_subtitle: '법령 전체의 연결 · 법령을 눌러 연결 조문 확인',
    overview_note: '가운데가 선택한 법령입니다. 연결 법령을 누르면 두 법령 사이의 인용 근거를 확인할 수 있습니다.',
  };
}

// Detail chunks are fetched only when a user opens a law pair. A failed or
// incomplete chunk must not be silently reported as having no citations.
export async function loadLawPair(document, otherName, read) {
  const refs = new Map();
  for (const a of document.articles || []) {
    if (document.details?.[a.jo]) continue;
    if (!a.detail) throw Error('일부 조문의 연결 자료가 없습니다. 조문별 탐색이나 공식 원문에서 확인해 주세요.');
    refs.set(JSON.stringify(a.detail), a.detail);
  }
  const loaded = await Promise.all([...refs.values()].map(read));
  const details = Object.assign({}, document.details, ...loaded);
  for (const a of document.articles || [])
    if (!details[a.jo]) throw Error('일부 조문 연결 자료를 불러오지 못했습니다. 다시 시도해 주세요.');
  const rows = [...(document.broad || []), ...(document.text_connections || []),
    ...Object.values(details).flatMap((d) => d.rows || [])];
  const ownName = document.meta.name;
  const unique = new Map();
  for (const row of rows) {
    if (!((row.source_law === ownName && row.target_law === otherName) ||
      (row.source_law === otherName && row.target_law === ownName))) continue;
    unique.set(evidenceKey(row), row);
  }
  return [...unique.values()];
}
