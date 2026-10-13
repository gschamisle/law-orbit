// Editorial explanations are distinct from parsed edges and never count as citations.
export function matchingRemedyNotes(guide, law, article) {
  if (guide?.kind !== 'editorial-remedy-guide' || guide.schema !== 1 || guide.is_citation !== false || !article?.text)
    return [];
  // A note checked on a later snapshot may be reused only for identical wording.
  // No keyword-only fallback: a changed exception or qualifier must hide the note.
  return guide.entries.filter(r => r.law === law && r.jo === article.jo && r.quote &&
    (r.full_article ? article.text === r.quote : article.text.includes(r.quote)));
}

export function mountRemedyNotes(container, guide, law, article, { text, link, explore }) {
  const rows = matchingRemedyNotes(guide, law, article);
  if (!rows.length) return;
  const section = document.createElement('section');
  section.className = 'remedy-notes';
  section.append(text('h4', '행정구제 · 연결 읽기 안내'));
  for (const row of rows) {
    const item = document.createElement('details');
    item.append(text('summary', `${row.scope} · ${row.labels.join(' · ')}`));
    item.append(text('p', row.summary, 'small'));
    item.append(text('blockquote', row.quote, 'small muted'));
    item.append(link(row.url, '확인한 판본의 공식 원문 ↗'));
    section.append(item);
  }
  section.append(text('p', '확인한 원문의 절차 안내입니다. 인용선은 법적 적용관계나 청구 가능 여부를 판정하지 않습니다.', 'small muted'));
  if (explore) {
    const b = text('button', '행정구제에서 함께 보기', 'quiet');
    b.type = 'button';
    b.onclick = () => explore(rows[0].law_id, rows[0].scope);
    section.append(b);
  }
  container.append(section);
}
