"""Bidirectional, one-hop provision spotlight over the stored citation evidence."""
from __future__ import annotations

from collections import Counter, defaultdict
import json
import math
import re

from core import law_abbrev
from core.citation_scope import Provision, classify, parse_target
from core.impact_explorer import GRAPH, analyze
from core.law_universe import load_graph
from core.impact_galaxy import LABELS

DIRECTIONS = {"both": "인용 + 역인용", "forward": "인용하는 조문", "reverse": "인용받는 경로"}
COLORS = {"forward": "#66e5ed", "reverse": "#ffc77a", "review": "#e8a1cc"}
KINDS = {"article": "조문 인용", "law": "법령·정의·산식", "annex": "별표·서식", "standard": "분류·회계기준"}


def _norm(name: str) -> str:
    return "".join(str(name).split()).replace("ㆍ", "·")


def _target(reference: str, *, allow_hyphen=False) -> Provision:
    compact = "".join(reference.split())
    match = re.fullmatch(r"(\d+(?:-\d+)*)(?:의(\d+))?" if allow_hyphen else r"(\d+)(?:의(\d+))?", compact)
    if match:
        compact = f"제{match[1]}조" + (f"의{match[2]}" if match[2] else "")
    return parse_target(compact, allow_hyphen=allow_hyphen)


def analyze_focus(law: str, reference: str, graph: dict | None = None) -> dict:
    graph = graph if graph is not None else load_graph()
    from functools import partial
    from core import citation_scope as scopes
    option = dict(allow_hyphen=graph.get("domain") in ("fsc", "forex"))
    target_input = partial(_target, **option)
    parse_target = partial(scopes.parse_target, **option)
    classify = partial(scopes.classify, **option)
    canonical = {_norm(name): name for name in graph.get("laws", [])}
    if _norm(law) not in canonical:
        raise ValueError("저장된 그래프에 수록된 법령을 선택하세요.")
    law = canonical[_norm(law)]
    target = target_input(reference)
    narrow = any(target.path[1:])
    reverse = analyze(law, target.label, graph)
    tax_laws = {_norm(n) for n in graph.get('focus_laws', graph.get('tax_laws', graph.get('laws', [])))}
    is_external = lambda a, b: _norm(a) not in tax_laws or _norm(b) not in tax_laws
    rows = []
    for row in reverse["rows"]:
        if row["same_article"] or row["status"] == "disjoint":
            continue
        try:
            source = target_input(str(row["source_jo"]))
            neighbor_jo, neighbor_ref, kind = source.jo, source.label, 'article'
        except ValueError:
            if row.get('source_granularity') != 'annex':
                continue
            neighbor_jo = neighbor_ref = row['source_jo']
            kind = 'annex'
        source_law = canonical.get(_norm(row["source_law"]), row["source_law"])
        rows.append({**row, "source_law": source_law, "source_ref": row.get('source_ref', neighbor_ref),
                     "target_law": law, "target_ref": target.label,
                     "neighbor_law": source_law, "neighbor_jo": neighbor_jo, 'neighbor_ref':neighbor_ref,
                     'neighbor_kind':kind, 'kind':kind, 'external':is_external(source_law,law),
                     "neighbor_title": row["source_title"], "direction": "reverse",
                     "direction_label": "역인용 · 이 조문을 인용",
                     "precision": LABELS[row["status"]]})

    seen = set()
    broad_rows = []
    for edge in graph.get('edges', []):
        if edge.get('target_kind') != 'law' or _norm(edge.get('target_law','')) != _norm(law):
            continue
        if _norm(edge.get('source_law','')) == _norm(law):
            continue
        try:
            source = target_input(str(edge['source_jo']))
        except ValueError:
            continue
        broad_rows.append({**edge, 'raw':edge['cite_raw'], 'source_ref':edge.get('source_ref',source.label),
                           'target_ref_recorded':edge['target_ref'], 'status':'review',
                           'reason':'법령 전체의 정의·제도를 참조합니다. 선택한 조문까지 적용되는지는 확정하지 않았습니다.',
                           'same_article':False, 'neighbor_law':edge['source_law'], 'neighbor_jo':source.jo,
                           'neighbor_ref':source.label, 'neighbor_kind':'article', 'kind':'law',
                           'neighbor_title':edge.get('source_title',''), 'direction':'reverse',
                           'direction_label':'역인용 후보 · 법령 전체 참조', 'precision':KINDS['law'],
                           'external':is_external(edge['source_law'],law), 'broad':True})
    unplaced = []
    same_article_count = sum(row["same_article"] for row in reverse["rows"])
    for edge in graph.get("edges", []):
        if _norm(edge.get("source_law", "")) != _norm(law):
            continue
        try:
            source = target_input(str(edge.get("source_jo", "")))
        except ValueError:
            continue
        if source.jo != target.jo:
            continue
        target_law = canonical.get(_norm(edge.get("target_law", "")), edge.get("target_law", ""))
        raw = str(edge.get("cite_raw", ""))
        source_ref = edge.get('source_ref', source.label)
        source_status = classify(source_ref, target)[0] if narrow else 'exact'
        if source_status == 'disjoint':
            continue
        identity = (target_law, edge.get("target_ref"), edge.get('source_start'), raw)
        if identity in seen:
            continue
        seen.add(identity)
        kind = edge.get('target_kind', 'article')
        try:
            dest = parse_target(str(edge.get("target_ref", ""))) if kind == 'article' else None
        except ValueError:
            unplaced.append({"target_law": target_law, "raw": raw,
                             "target_ref_recorded": edge.get("target_ref", ""),
                             "reason": "저장된 참조 번호를 해석하지 못해 지도 위치를 정하지 못했습니다."})
            continue
        if dest and _norm(target_law) == _norm(law) and dest.jo == target.jo:
            continue
        status, reason = classify(raw, dest) if dest else ('review', {
            'law':'법령 전체 참조입니다.', 'annex':'별표·서식 참조입니다. 표·서식 본문과 적용 조건을 원문에서 확인하세요.',
            'standard':'분류·회계기준 참조입니다. 기준 전문의 개정 영향은 별도 검토가 필요합니다.'}.get(kind,''))
        if kind == 'law':
            reason = '법령의 정의·제도 또는 산식을 참조합니다. 특정 조문 번호로 연결을 확정하지 않았습니다.'
        reason = reason.replace("개정 대상", "저장된 참조 대상")
        if status == "disjoint":
            status, reason = "review", "저장된 참조 대상과 인용 문구가 일치하는지 확인해야 합니다."
        if edge.get('context_review'):
            status = 'review'
            reason += ' 인용 주변의 한정·제외·대체 또는 상대 참조를 확인하세요.'
        if narrow and (edge.get('source_granularity') != 'block' or source_status in ('covering','review')):
            status = "review"
            reason = (f"{Provision(target.jo).label}에서 인용한 문구입니다. 출처가 조 단위 또는 상위 단위로 저장되어 "
                      f"{target.label} 안의 인용인지는 원문 확인이 필요합니다. " + reason)
        rows.append({**edge, "source_law": law, "source_jo": target.jo,
                     "source_ref": source_ref, "source_title": edge.get("source_title", ""),
                     "target_law": target_law, "target_ref": dest.label if dest else edge['target_ref'],
                     "target_ref_recorded": edge.get("target_ref", ""),
                     "raw": raw, "status": status, "reason": reason,
                     "source_granularity": edge.get('source_granularity','article'), "same_article": False,
                     "relation_type": edge.get("type", "direct"),
                     "neighbor_law": target_law, "neighbor_jo": dest.jo if dest else edge['target_ref'],
                     'neighbor_ref':Provision(dest.jo).label if dest else edge['target_ref'],
                     'neighbor_kind':kind, 'kind':kind, 'external':is_external(law,target_law),
                     "neighbor_title": edge.get('target_title',''),
                     "direction": "forward", "direction_label": "인용 · 이 조문이 참조",
                     "precision": KINDS[kind] if kind != 'article' else LABELS[status]})
    rows.sort(key=lambda r: (r["direction"], r["status"] == "review", r["neighbor_law"], r["neighbor_jo"], r["raw"]))
    return {"law": law, "reference": target.label, "narrow": narrow, "rows": rows, 'broad_rows':broad_rows,
            "built_at": graph.get("built_at", ""), "laws": graph.get("laws", []),
            "same_article_count": same_article_count, "unplaced": unplaced,
            "disjoint_count": reverse["counts"].get("disjoint", 0),
            "coverage_note": graph.get('coverage_note', '저장된 인용 그래프에서 직접 이어지는 경로입니다. 수록 범위 밖 법령과 문맥은 추가 확인이 필요합니다.')}


def visible_rows(result: dict, direction: str = "both", include_review: bool = True, *, external=True, kinds=None, include_broad=False) -> list[dict]:
    if direction not in DIRECTIONS:
        raise ValueError("지원하지 않는 인용 방향입니다.")
    candidates = result['rows'] + (result.get('broad_rows',[]) if include_broad else [])
    return [r for r in candidates if (direction == "both" or r["direction"] == direction)
            and (external or not r.get('external')) and (kinds is None or r.get('kind','article') in kinds)
            and (include_review or r["status"] != "review")]


def build(result: dict, overview: dict, direction: str = "both", include_review: bool = True, **filters) -> dict:
    rows = visible_rows(result, direction, include_review, **filters)
    groups = defaultdict(list)
    for row in rows:
        groups[(row["neighbor_law"], row.get('neighbor_kind','article'), row["neighbor_jo"])].append(row)
    display_names = {n["id"]: n["label"] for n in overview.get("nodes", []) if n.get("full_name")}
    center = "focus:" + result["law"] + "|" + result["reference"]
    nodes = [{**n, "context_only": True} for n in overview.get("nodes", [])]
    nodes.append(dict(id=center, label=display_names.get(result["law"], law_abbrev.law(result["law"])), subtitle=result["reference"],
                      full_name=result["law"] if display_names else "",
                      family=result["law"], color="#e4f7ff", count=len(groups), x=0, y=0, z=0,
                      title="선택한 개정 대상 · 직접 연결", is_target=True, evidence=[]))
    links = []
    for i, ((law, kind, jo), evidence) in enumerate(sorted(groups.items())):
        theta = i * math.pi * (3 - math.sqrt(5))
        radius = 450 * math.sqrt(.40 + .60 * (i + .5) / max(len(groups), 1))
        ident = kind + ":" + law + "|" + str(jo)
        directions = {e["direction"] for e in evidence}
        color = "#b5a1ff" if len(directions) > 1 else COLORS[evidence[0]["direction"]]
        if all(e["status"] == "review" for e in evidence):
            color = COLORS["review"]
        nodes.append(dict(id=ident, label=display_names.get(law, law_abbrev.law(law)), subtitle=evidence[0]['neighbor_ref'], kind=kind,
                          full_name=law if display_names else "",
                          family=law, color=color, count=len(evidence),
                          x=round(math.cos(theta)*radius, 2), y=round(math.sin(theta)*radius*.85, 2), z=round(math.sin(theta*1.5)*100, 2),
                          title=next((e["neighbor_title"] for e in evidence if e["neighbor_title"]), "연결된 조문"),
                          status=" · ".join("인용" if d == "forward" else "역인용" for d in sorted(directions)),
                          evidence=evidence))
        for (flow, review), count in sorted(Counter((e["direction"], e["status"] == "review") for e in evidence).items()):
            links.append(dict(a=center if flow == "forward" else ident,
                              b=ident if flow == "forward" else center, n=count,
                              direction=flow, color=COLORS["review" if review else flow],
                              dashed=review, status="review" if review else "citation",
                              bend=(1 if flow == "forward" else -1) * (1.7 if review else 1)))
    return dict(nodes=nodes, dust=overview.get("dust", []), links=links, all_links=links,
                mode="spotlight", built_at=result["built_at"], focus=center,
                target=result["law"] + " " + result["reference"],
                direction=DIRECTIONS[direction], evidence_count=len(rows),
                article_count=len(groups) + 1, neighbor_count=len(groups),
                stats=f"{len(groups)}개 연결 대상 · {len(rows)}개 인용 근거")
