"""The explorer and the 3D view share exactly the same evidence rows."""
from __future__ import annotations

import math

from core import law_abbrev

COLORS = {"exact": "#66efce", "range": "#ffc77a", "covering": "#88b8ff", "contained": "#c6a3ff", "review": "#e8a1cc"}
LABELS = {"exact": "직접 인용", "range": "범위 포함", "covering": "상위 조문 인용", "contained": "하위 조문 인용", "review": "문맥 확인", "disjoint": "항·호 불일치"}


def build(result: dict) -> dict:
    boundary = result.get("mode") == "boundary"
    if boundary:
        from core.boundary_review import COLORS as colors, LABELS as labels, paragraph_labels
    else:
        colors, labels = COLORS, LABELS
    center = result["law"] + " " + result["reference"]
    groups: dict[tuple, list[dict]] = {}
    for row in result["rows"]:
        if row["status"] in ("disjoint", "not_boundary") or row["same_article"]:
            continue
        groups.setdefault((row["source_law"], row["source_jo"]), []).append(row)
    nodes = [dict(id=center, label=law_abbrev.law(result["law"]), subtitle=result["reference"],
                  family=result["law"], color="#e4f7ff", count=len(groups), x=0, y=0, z=0,
                  title=("신설 " + paragraph_labels(result["change"]["added"]) if boundary else "선택한 개정 대상"),
                  evidence=[], is_target=True)]
    links = []
    for i, ((law, jo), evidence) in enumerate(sorted(groups.items())):
        n = len(groups)
        theta = i * math.pi * (3 - math.sqrt(5))
        y = 1 - 2 * (i + .5) / max(n, 1)
        r = math.sqrt(max(0, 1 - y * y))
        ident = law + "|" + str(jo)
        status = evidence[0]["status"]
        nodes.append(dict(id=ident, label=law_abbrev.law(law), subtitle=law_abbrev.jo_key(jo),
                          family=law, color=colors[status], count=len(evidence),
                          x=round(math.cos(theta)*r*340, 2), y=round(y*280, 2), z=round(math.sin(theta)*r*300, 2),
                          title=evidence[0]["source_title"], status=labels[status], evidence=evidence))
        for link_status in dict.fromkeys(e["status"] for e in evidence):
            links.append(dict(a=ident, b=center, n=sum(e["status"] == link_status for e in evidence),
                              color=colors[link_status], status=link_status,
                              dashed=boundary and link_status != "covered"))
    return dict(nodes=nodes, dust=[], links=links, all_links=links,
                families=list(colors), mode="boundary" if boundary else "impact", built_at=result["built_at"],
                focus=center, target=center, title="한 조문의 변화, 연결된 법령의 궤도",
                example=result.get("example", False),
                change_summary=("신설 " + paragraph_labels(result["change"]["added"])) if boundary else "",
                evidence_count=sum(len(v) for v in groups.values()),
                stats=f"{len(groups)}개 연결 조문 · 저장 인용 기준")
