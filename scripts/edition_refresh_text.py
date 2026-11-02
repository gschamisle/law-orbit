"""Selectively rebuild paragraph evidence without creating numbered articles.

This helper returns only evidence from replaced documents. The refresh caller
keeps all other published evidence byte-for-byte (apart from target metadata),
removes prior evidence from replaced sources, then adds these fresh rows.
"""
from collections import defaultdict
from copy import deepcopy

from core.citation_scope import parse_target
from core.ftc_text_citations import (
    TEXT_DOMAINS, collect_text_citations, main_text, prepare_text_aliases,
    reading_row, validate_text_citations,
)
from scripts.build_static_galaxies import tidy


def merge_rows(existing, added):
    """Preserve original rows/ordering and deduplicate identical fresh evidence.

    One span may legitimately cite multiple targets (including expanded ranges),
    so target identity and direction are part of the key. Conflicting versions
    of the same fresh evidence are rejected rather than silently chosen.
    """
    result = list(existing)
    def key(row):
        return (row.get('evidence_id'), row.get('source_law'), row.get('source_jo'),
                row.get('source_start'), row.get('source_end'), row.get('target_law'),
                row.get('target_ref_recorded') or row.get('target_ref'),
                row.get('target_kind'), row.get('direction'))
    seen = {key(row): row for row in existing}
    for row in added:
        ident = key(row)
        if ident in seen:
            if seen[ident] != row:
                raise ValueError('Conflicting refreshed text evidence')
            continue
        seen[ident] = row
        result.append(row)
    return result


def refresh_text_evidence(corpus, changed_names, domain, ids):
    """Return fresh text rows/metadata for changed sources; never mutate inputs.

    ``ids`` are existing public reader IDs, not newly computed title hashes.
    ``overview_edges`` belong only in a copy passed to overview_overlay, never
    in the numbered EdgeIndex. An unchanged unstructured source need not have a
    UID because it is a target-only corpus member in this selective pass.
    """
    empty = dict(documents={}, forward={}, reverse={}, overview_edges=[],
                 text_citations=[], text_issues=[])
    if domain not in TEXT_DOMAINS:
        return empty
    selected = set(changed_names)
    docs = deepcopy(corpus)
    if len({d['name'] for d in docs}) != len(docs):
        raise ValueError('Duplicate text refresh document name')
    by_name = {d['name']: d for d in docs}
    if not selected.issubset(by_name):
        raise ValueError('Missing changed text refresh source')
    candidates = set()
    for name in selected:
        d = by_name[name]
        if d.get('provider') != 'admrul' or d.get('articles'):
            continue
        if ('조문번호 중복' in d.get('analysis_error', '')
                or d.get('coverage', {}).get('provisions') == 'blocked-duplicate-number'):
            continue
        if not main_text(d).strip():
            continue
        if not d.get('uid') or not ids.get(name):
            raise ValueError('Missing stable text source or reader identity')
        if domain == 'ftc':
            from core.ftc_collection import prepare_source
            d = prepare_source(dict(domain='ftc', laws=[], administrative_rules=[d]))['administrative_rules'][0]
        else:
            prepare_text_aliases(d)
        by_name[name] = d
        candidates.add(name)
    if not candidates:
        return empty
    # Only selected sources are scanned; all documents remain available for
    # resolving official names, aliases and real article numbers.
    docs = [by_name[d['name']] for d in docs]
    source = dict(domain=domain,
                  laws=[d for d in docs if d.get('provider') != 'admrul'],
                  administrative_rules=[d for d in docs if d.get('provider') == 'admrul'])
    edges, issues = collect_text_citations(source, profile=domain, source_names=candidates)
    validate_text_citations(source, edges)
    forward, reverse = defaultdict(list), defaultdict(list)
    for edge in edges:
        forward[edge['source_law']].append(tidy(reading_row(edge, 'forward'), ids, False))
        if edge['target_status'] == 'collected' and edge['target_kind'] == 'article':
            jo = parse_target(edge['target_ref']).jo
            reverse[(edge['target_law'], jo)].append(tidy(reading_row(edge, 'reverse'), ids, False))
    documents = {}
    for name in candidates:
        d = by_name[name]
        documents[name] = dict(text_analysis=deepcopy(d['text_analysis']),
                               analysis_error=d['analysis_error'],
                               text_connections=merge_rows([], forward[name]),
                               text_issues=[deepcopy(i) for i in issues if i['source_law'] == name])
    known = set(by_name)
    return dict(documents=documents, forward=dict(forward),
                reverse={k: merge_rows([], v) for k, v in reverse.items()},
                overview_edges=[dict(e, type='direct') for e in edges if e['target_law'] in known],
                text_citations=edges, text_issues=issues)


def summarize_text_entries(entries, documents):
    """Recount from the final published documents, including preserved sources."""
    return dict(documents=sum(bool(e.get('text_analysis')) for e in entries),
                citations=sum(len(documents[e['id']].get('text_connections', [])) for e in entries),
                issues=sum(len(documents[e['id']].get('text_issues', [])) for e in entries))
