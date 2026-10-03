import { safeLink } from './query.mjs';

export function annexSources(urls, ownerUrl = '') {
  const originals = [...new Set((Array.isArray(urls) ? urls : []).map(safeLink).filter(Boolean))];
  return { originals, ownerUrl: safeLink(ownerUrl) };
}

// URLs and analysis flags describe the connected annex (the source on reverse rows).
export function annexReference(row, { currentDoc = null, external = false } = {}) {
  const reverse = !external && row.direction === 'reverse';
  if ((external ? row.target_kind : row.neighbor_kind || row.target_kind) !== 'annex') return null;
  const law = external
    ? row.target_law
    : row.neighbor_law || (reverse ? row.source_law : row.target_law);
  const ref = external
    ? row.target_ref
    : row.neighbor_jo || row.neighbor_ref || (reverse ? row.source_jo : row.target_ref);
  const id = external
    ? row.target_id
    : row.neighbor_id || (reverse ? row.source_id : row.target_id);
  const sameOwner =
    !!currentDoc?.meta &&
    (id ? currentDoc.meta.id === id : !!law && currentDoc.meta.name === law) &&
    (!law || currentDoc.meta.name === law);
  const local = sameOwner ? (currentDoc.annexes || []).find((a) => a.ref === ref) : null;
  const status =
    row.annex_analyzed === false
      ? 'not-analyzed'
      : local
        ? local.analysis
          ? 'verified'
          : 'not-analyzed'
        : sameOwner
          ? 'not-analyzed'
          : row.annex_analyzed === true
            ? 'verified'
            : row.annex_unanalyzed
              ? 'not-analyzed'
              : 'unknown';
  const ownerUrl =
    (reverse ? row.source_url : row.target_url) || (sameOwner ? currentDoc.meta.url : '');
  const sources = annexSources(
    [...(Array.isArray(row.annex_urls) ? row.annex_urls : []), ...(local?.urls || [])],
    ownerUrl,
  );
  return {
    law,
    ref,
    id,
    ...sources,
    status,
    analyzed: status === 'verified',
    titleReference: row.source_granularity === 'annex' && row.source_layer !== 'annex-body',
  };
}

export function appendAnnexSources(container, sources, { text, link }) {
  if (sources.originals.length) {
    for (const [i, url] of sources.originals.entries())
      container.append(link(url, `별표 원본 ${i + 1} ↗`));
  } else {
    container.append(text('span', '첨부파일 주소 미확보', 'muted small'));
    if (sources.ownerUrl) container.append(link(sources.ownerUrl, '별표 소유 법령 원문 ↗'));
    else
      container.append(text('span', '별표 소유 법령의 공식 출처를 확인해 주세요.', 'muted small'));
  }
}
