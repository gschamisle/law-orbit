"""Bounded reverse-citation review for paragraphs appended beyond a former endpoint.

No semantic inference and no automatic amendment verdict. Original scope and the
structural reason for asking about new paragraphs are both retained as evidence.
"""
from __future__ import annotations

from collections import Counter

from core.article_structure import compare_articles, parse_article
from core.citation_scope import Provision, parse_scope, scope_relation
from core.impact_explorer import analyze

LABELS = {"scope_review": "인용 범위 재검토", "covered": "문언상 신설 항 포함",
          "review": "구조·문맥 확인", "not_boundary": "끝 경계 후보 아님"}
COLORS = {"scope_review": "#ffc77a", "covered": "#88b8ff", "review": "#e8a1cc"}


def paragraph_labels(numbers: list[int]) -> str:
    return "·".join(f"제{n}항" for n in numbers) or "없음"


def _evaluate(row: dict, change: dict) -> dict:
    old, added = change["before_numbers"], change["added"]
    target_jo = change["article"].removeprefix("제").replace("조", "")
    parsed = parse_scope(row["raw"])
    relevant = [s for s in parsed.scopes if scope_relation(s, Provision(target_jo))]
    cited: set[int] = set()
    whole = False
    partial = False
    nonexistent = False
    for scope in relevant:
        if not scope.start.hang or scope.axis == 0:
            if scope.start.ho or scope.start.mok:
                partial = True
            else:
                whole = True
            continue
        if scope.start.ho or scope.end.ho or scope.start.mok or scope.end.mok or scope.axis not in (None, 1):
            partial = True
            continue
        lo, hi = int(scope.start.hang), int(scope.end.hang)
        cited.update(n for n in old if lo <= n <= hi)
        if lo < old[0] or hi > old[-1]:
            nonexistent = True
    evidence = dict(row, citation_status=row["status"], cited_paragraphs=sorted(cited),
                    added_paragraphs=added, excluded_before=sorted(set(old) - cited),
                    priority="", pattern="", question="", change_summary=(
                        f"종전 {paragraph_labels(old)} → 신설 {paragraph_labels(added)}"))

    def finish(status: str, reason: str, **extra) -> dict:
        return dict(evidence, status=status, reason=reason, **extra)

    if change["kind"] == "none":
        return finish("not_boundary", "입력된 개정 전후에서 신설 항이 확인되지 않았습니다.")
    if change["kind"] == "complex":
        return finish("review", "삭제·번호 이동 또는 기존 항 내용 변경이 함께 있어, 단순한 끝 항 신설로 판정하지 않았습니다.")
    if row["status"] == "review" or parsed.review_reason or not relevant:
        return finish("review", row["reason"] if row["status"] == "review" else parsed.review_reason or "인용 대상을 원문에서 확인해야 합니다.")
    if nonexistent:
        return finish("review", "인용 범위가 입력한 종전 항 구조를 벗어납니다. 원문 버전과 인용 자료의 시점이 맞는지 확인하세요.")
    if whole and not partial:
        return finish("covered", "조 전체를 인용하여 문언상 신설 항도 포함합니다. 실제 적용 취지는 별도 확인 대상입니다.")
    if partial:
        return finish("review", "호·목 또는 생략된 계층을 포함합니다. 항 전체를 인용한 것으로 확대하지 않았습니다.")
    if len(cited) < 2 or change["former_last"] not in cited:
        return finish("not_boundary", "종전 마지막 항을 포함하는 둘 이상의 항에 대한 범위·열거 인용에 해당하지 않습니다.")
    excluded = sorted(set(old) - cited)
    contiguous_tail = sorted(cited) == list(range(min(cited), old[-1] + 1))
    if not excluded:
        pattern, priority, reason = "all", "우선 검토", "개정 전의 모든 항을 번호로 지정해 인용했습니다."
    elif contiguous_tail:
        pattern, priority, reason = "tail", "우선 검토", f"개정 전 {paragraph_labels(excluded)}을 제외한 모든 항을 인용했습니다."
    else:
        pattern, priority, reason = "enumeration", "일반 검토", "종전 마지막 항을 포함한 일부 항을 열거했습니다. 모든 나머지 항을 포괄하는 형태는 아닙니다."
    question = f"기존 인용 취지에 {paragraph_labels(added)}도 포함되는지 확인하세요."
    # Priority is structural, not a score estimating legislative intent.
    evidence.update(pattern=pattern, priority=priority, question=question)
    return finish("scope_review", reason + " 신설 항은 현재 인용 범위에 포함되지 않습니다.")


def review_append(law: str, reference: str, before_text: str, after_text: str,
                  graph: dict | None = None, before_version: str = "개정 전", after_version: str = "개정 후(안)") -> dict:
    before = parse_article(before_text, reference, before_version)
    after = parse_article(after_text, reference, after_version)
    change = compare_articles(before, after)
    result = analyze(law, reference, graph)
    rows = [_evaluate(row, change) for row in result["rows"]]
    order = {"scope_review": 0, "review": 1, "covered": 2, "not_boundary": 3}
    rows.sort(key=lambda row: (order[row["status"]], row["priority"] != "우선 검토", row["source_law"], row["source_jo"], row["raw"]))
    return dict(result, mode="boundary", rows=rows, change=change,
                counts=dict(Counter(row["status"] for row in rows)),
                candidate_count=len(rows), candidate_article_count=len({(r["source_law"], r["source_jo"]) for r in rows}),
                schema_version=1, example=False,
                coverage_note="입력한 조문의 개정 전후와 저장된 역인용 문구만 대조합니다. 전체 법령의 완전한 탐지나 입법 취지 판정이 아닙니다. 조문 원문과 인용 자료의 버전 일치 여부는 확인이 필요합니다.")


def example_result() -> dict:
    """Explicit fictional fixture, never inserted into the real citation snapshot."""
    before = "제2조(적용 대상)\n① 기본 원칙을 정한다.\n② 첫 번째 적용 대상을 정한다.\n③ 두 번째 적용 대상을 정한다.\n④ 세 번째 적용 대상을 정한다."
    after = before + "\n⑤ 새로운 적용 대상을 추가한다."
    references = [("B법", "7", "제2조제2항부터 제4항까지"),
                  ("C법", "3", "제2조제2항·제3항 및 제4항"),
                  ("D법", "8", "제2조제2항부터 제3항까지"),
                  ("E법", "9", "제2조"),
                  ("F법", "6", "제2조제2항부터 제4항까지(제3항은 제외한다)")]
    graph = {"built_at": "가상 예시", "laws": ["A법", "B법", "C법", "D법", "E법", "F법"],
             "edges": [dict(source_law=law, source_jo=jo, source_title="인용 예시", target_law="A법",
                            target_ref="제2조", cite_raw=raw) for law, jo, raw in references]}
    result = review_append("A법", "제2조", before, after, graph, "가상 A법 — 개정 전", "가상 A법 — 제5항 신설안")
    result["example"] = True
    return result
