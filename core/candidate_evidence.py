"""Source-first task acceptance for new domains, independent of link counts.

Expected endpoints must be frozen from official wording before collection.
They are tests of real parser output, never inserted or reconstructed edges.
"""
from core.fsc_collection import norm
from core.citation_scope import parse_target


def case_proof(graph, expected, *, known_articles=None):
    known=None if known_articles is None else {(norm(law),str(jo)) for law,jo in known_articles}
    matches=[]
    for requirement in expected:
        found=[]
        for edge in graph['edges']+graph.get('text_citations',[]):
            if edge.get('target_kind')!='article' or edge.get('context_review'):continue
            if edge.get('type') in ('context','context-review'):continue
            if any(norm(edge.get(k,''))!=norm(requirement[k]) for k in ('source_law','target_law')):continue
            if str(edge.get('source_jo',''))!=str(requirement.get('source_jo','')):continue
            try:target=parse_target(edge.get('target_ref','')).jo
            except ValueError:continue
            if target!=requirement['target_jo']:continue
            if known is not None:
                if (norm(edge['target_law']),target) not in known:continue
                if edge.get('source_jo') and (norm(edge['source_law']),str(edge['source_jo'])) not in known:continue
            if requirement.get('quote_contains') and norm(requirement['quote_contains']) not in norm(edge.get('cite_raw') or edge.get('raw','')):continue
            found.append(edge['evidence_id'])
        matches.append(found)
    return dict(available=bool(expected) and all(matches),
                expected_relations=len(expected),verified_relations=sum(bool(m) for m in matches),
                evidence_ids=list(dict.fromkeys(e for m in matches for e in m)))
