"""Opt-in FSC graph; existing tax data and UI defaults remain unchanged."""
from __future__ import annotations
from copy import deepcopy
from core.fsc_collection import CollectionError, norm, ymd


def bootstrap_sources(existing: dict, seeds: tuple) -> dict:
    """Reuse repository source editions, NOT a new official FSC collection."""
    wanted = {norm(s.name) for s in seeds}
    result, matched = deepcopy(existing), set()
    for law in result['laws']:
        family, name = norm(law.get('family', law['name'])), norm(law['name'])
        if family in wanted or name in wanted:
            matched.update({family, name} & wanted)
            law.update(origin_category=law['category'], category='fsc',
                       scope_basis='existing-corpus-family-match-to-seed')
    if not any(law['category'] == 'fsc' for law in result['laws']):
        raise CollectionError('no-fsc-document-in-existing-corpus')
    result['coverage'] = dict(
        mode='bootstrap-existing-editions-not-fresh-collection',
        fsc_statute_list='partial-seed-match', fsc_statute_bodies='borrowed',
        fsc_rules='not-collected', fss_rules='not-collected',
        external_reverse='existing-tax-corpus-only', supplement='not-indexed',
        annex_body='not-indexed',
        unmatched_seed_names=[s.name for s in seeds if norm(s.name) not in matched])
    return result


def merge_external(primary: dict, external: dict) -> dict:
    if ymd(primary['built_at']) != ymd(external['built_at']):
        raise CollectionError('external-snapshot-date-mismatch')
    result = deepcopy(primary)
    rows = result['laws']
    by_name = {norm(l['name']): l for l in rows}
    by_id = {l['law_id']: l for l in rows}
    for candidate in external['laws']:
        row = deepcopy(candidate)
        old = by_name.get(norm(row['name'])) or by_id.get(row['law_id'])
        if old:
            if norm(old['name']) != norm(row['name']) or any(
                str(old.get(k, '')) != str(row.get(k, ''))
                for k in ('law_id', 'mst', 'effective')):
                raise CollectionError('external-edition-or-identity-conflict')
            old['origin_category'] = row['category']
            continue
        rows.append(row)
        by_name[norm(row['name'])], by_id[row['law_id']] = row, row
    result.setdefault('coverage', {})['external_reverse'] = 'declared-equal-date-external-corpus-only'
    return result


def build_fsc_graph(source: dict) -> dict:
    if any(l.get('provider', 'eflaw') != 'eflaw' for l in source['laws']):
        raise CollectionError('nonstatute-fed-to-statute-builder')
    if not any(l['category'] == 'fsc' for l in source['laws']):
        raise CollectionError('no-fsc-focus-documents')
    from core.universe_builder import build_universe
    from core.fsc_administrative import adapter
    rules = [r for r in source.get('administrative_rules',[]) if r.get('body_status') == 'indexed-administrative-text']
    documents = source['laws'] + rules
    graph = build_universe({**source, 'laws':documents}, focus_categories=('fsc',), preserve_external=True, article_adapter=adapter)
    graph['domain'] = 'fsc'
    # Evidence opens the edition collected, even after the current law changes.
    editions = {law['name']: law.get('source_url', '') for law in source['laws'] + source.get('administrative_rules',[])}
    unindexed = {norm(r['name']):r for r in source.get('administrative_rules',[]) if r.get('body_status') != 'indexed-administrative-text'}
    for edge in graph.get('external_references',[]):
        if norm(edge['target_law']) in unindexed:
            target=unindexed[norm(edge['target_law'])]
            edge.update(target_law=target['name'],target_status='collected-not-indexed',target_analysis='not-indexed',target_url=target['source_url'])
        elif edge['target_law'].endswith(('규정','세칙','기준','지침')):
            from urllib.parse import quote
            edge['target_url']='https://www.law.go.kr/행정규칙/'+quote(edge['target_law'],safe='')
    for edge in graph['edges'] + graph.get('external_references', []):
        if editions.get(edge['source_law']):
            edge['source_url'] = editions[edge['source_law']]
        if editions.get(edge['target_law']):
            edge['target_url'] = editions[edge['target_law']]
    graph['coverage'] = deepcopy(source.get('coverage', {}))
    graph['administrative_rule_bodies_not_indexed'] = len(source.get('administrative_rules', []))-len(rules)
    graph['administrative_rules_indexed'] = len(rules)
    graph['administrative_articles'] = sum(len(r['articles']) for r in rules)
    graph['citation_issues'] = [dict(source_law=r['name'],source_jo=a['jo'],source_url=r['source_url'],**issue) for r in rules for a in r['articles'] for issue in a.get('citation_issues',[])]
    graph['coverage'].update(fsc_rules='article-indexed-with-explicit-review-gaps', fss_rules=source.get('coverage',{}).get('fss_rules','not-collected'))
    graph['tax_laws'] = sorted(l['name'] for l in source['laws']
                              if l.get('origin_category', l['category']) == 'tax')
    graph['coverage_note'] = (
        '수집한 금융위 법령·감독규정과 금감원 시행세칙의 조문 인용망입니다. 외부 미수집 법령은 인용 근거만 보존하며 본문·역인용은 미점검입니다. '
        '범위 밖·조회 실패는 영향 없음이 아닙니다. 해석하지 못한 별칭·상대 참조는 확인 목록에 남깁니다. '
        '부칙·별표 파일 본문과 조문 형식이 없는 자료는 미분석입니다. 금감원 내부 규정 전체를 수집한 것은 아닙니다. '
        '인용 관계는 동시개정 의무의 자동 확정이 아닙니다.')
    return graph


def graph_report(graph: dict) -> dict:
    return dict(built_at=graph['built_at'], focus_laws=len(graph['focus_laws']),
                focus_law_names=graph['focus_laws'], corpus_laws=len(graph['laws']),
                evidence_edges=len(graph['edges']), external_references=len(graph.get('external_references', [])), relation_counts=graph['relation_counts'],
                coverage=graph['coverage'], note=graph['coverage_note'],
                administrative_rule_bodies_not_indexed=graph['administrative_rule_bodies_not_indexed'],
                administrative_rules_indexed=graph.get('administrative_rules_indexed',0),
                administrative_articles=graph.get('administrative_articles',0),
                unresolved_citations=len(graph.get('citation_issues',[])))
