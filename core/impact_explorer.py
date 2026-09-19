"""Read-only precise explorer over the existing, versioned citation snapshot."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from core.citation_scope import Provision, classify, parse_scope, parse_target, scope_relation
from core.law_universe import graph_path, load_graph

GRAPH = graph_path()


def analyze(law: str, reference: str, graph: dict | None = None) -> dict:
    from functools import partial
    from core import citation_scope as scopes
    graph = graph if graph is not None else load_graph()
    option = dict(allow_hyphen=graph.get("domain") == "fsc")
    parse_target = partial(scopes.parse_target, **option)
    parse_scope = partial(scopes.parse_scope, **option)
    scope_relation = partial(scopes.scope_relation, **option)
    classify = partial(scopes.classify, **option)
    target = parse_target(reference)
    norm = lambda name: "".join(str(name).split()).replace("ㆍ", "·")
    rows: list[dict] = []
    seen: set[tuple] = set()
    for edge in graph.get("edges", []):
        if edge.get("target_kind", "article") != "article":
            continue
        if norm(edge.get("target_law", "")) != norm(law):
            continue
        raw = str(edge.get("cite_raw", ""))
        parsed = parse_scope(raw)
        # Scan raw article ranges too: the legacy graph omits intermediate branch articles.
        candidate = any(scope_relation(s, Provision(target.jo)) for s in parsed.scopes)
        try:
            recorded = parse_target(str(edge.get("target_ref", "")))
            candidate = candidate or recorded.jo == target.jo
        except ValueError:
            recorded = None
        if not candidate:
            continue
        status, reason = classify(raw, target)
        if not parsed.scopes or (recorded and not any(
            scope_relation(s, Provision(recorded.jo)) for s in parsed.scopes
        )):
            status, reason = "review", "저장된 참조 대상과 인용 문구의 문맥을 확인해야 합니다."
        same_article = norm(edge.get("source_law", "")) == norm(law) and str(edge.get("source_jo")) == target.jo
        if same_article:
            status, reason = "review", "같은 조 안의 참조입니다. 표제에서 추출된 항목인지 원문 확인이 필요합니다."
        if edge.get("context_review") and status != "disjoint":
            status, reason = "review", "인용 주변에 한정·제외·대체 또는 상대 참조가 있습니다. 적용 범위는 원문 문맥을 확인하세요."
        identity = (edge.get("source_law"), edge.get("source_jo"), edge.get("source_start"), raw)
        if identity in seen:
            continue
        seen.add(identity)
        rows.append({
            **edge,
            "source_law": edge.get("source_law", ""),
            "source_jo": edge.get("source_jo", ""),
            "source_title": edge.get("source_title", ""),
            "raw": raw, "status": status, "reason": reason,
            "target_ref_recorded": edge.get("target_ref", ""),
            "relation_type": edge.get("type", "direct"),
            "source_granularity": edge.get("source_granularity", "article"), "same_article": same_article,
        })
    priority = {k: i for i, k in enumerate(("exact", "range", "covering", "contained", "review", "disjoint"))}
    rows.sort(key=lambda row: (priority[row["status"]], row["source_law"], row["source_jo"], row["raw"]))
    return {
        "law": law, "reference": target.label, "rows": rows,
        "counts": dict(Counter(row["status"] for row in rows)),
        "built_at": graph.get("built_at", ""), "laws": graph.get("laws", []),
        "edge_count": len(graph.get("edges", [])),
        "coverage_note": "저장된 그래프의 인용 문구를 대조한 결과입니다. 전체 법령·최신 현행본·문맥상 제외 조건의 완전성은 보장하지 않습니다.",
    }
