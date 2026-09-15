"""One resolved citation expression -> provision scopes, without changing the legacy parser.

This module matches syntactic scope, not whether an amendment is legally required.
The caller supplies the resolved law. Qualifiers and unresolved context stay reviewable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_TOKEN = re.compile(r"제\s*(\d+)\s*(조|항|호)(?:\s*의\s*(\d+))?|([가-하])\s*목")
_LEVEL = {"조": 0, "항": 1, "호": 2, "목": 3}
_ENUM = re.compile(r"\s*(?:및|또는|와|과|ㆍ|·|,|각\s*호|각\s*목|의|본문|전단|후단)*\s*")
_RANGE = re.compile(r"\s*(?:부터|에서|내지|[~～∼])\s*")
_QUALIFIER = re.compile(r"제외|한정|한하|단서|외의\s*부분|불구|전단|후단|본문|전항|다음\s*항|같은\s*(?:조|항|호)")


@dataclass(frozen=True)
class Provision:
    jo: str
    hang: str = ""
    ho: str = ""
    mok: str = ""

    @property
    def path(self) -> tuple[str, ...]:
        return self.jo, self.hang, self.ho, self.mok

    @property
    def label(self) -> str:
        base, _, sub = self.jo.partition("의")
        ho, _, ho_sub = self.ho.partition("의")
        return (f"제{base}조" + (f"의{sub}" if sub else "")
                + (f"제{self.hang}항" if self.hang else "")
                + (f"제{ho}호" + (f"의{ho_sub}" if ho_sub else "") if ho else "")
                + (f"{self.mok}목" if self.mok else ""))


@dataclass(frozen=True)
class Scope:
    start: Provision
    end: Provision
    axis: int | None = None


@dataclass(frozen=True)
class ParsedScope:
    scopes: tuple[Scope, ...]
    review_reason: str = ""


def _number(value: str) -> tuple[int, int]:
    base, _, sub = value.partition("의")
    return int(base), int(sub or 0)


def parse_target(text: str) -> Provision:
    """Strict input: don't silently turn an invalid target into an entire article."""
    compact = re.sub(r"\s+", "", text)
    match = re.fullmatch(
        r"제(\d+)조(?:의(\d+))?(?:제(\d+)항)?(?:제(\d+)호(?:의(\d+))?)?(?:([가-하])목)?",
        compact,
    )
    if not match:
        raise ValueError("제16조제2항제1호처럼 조문 번호를 입력하세요.")
    jo, sub, hang, ho, ho_sub, mok = match.groups()
    if mok and not ho:
        raise ValueError("목을 지정할 때에는 호도 입력하세요.")
    values = [v for v in (jo, sub, hang, ho, ho_sub) if v]
    if any(int(v) <= 0 for v in values):
        raise ValueError("조문 번호는 1 이상이어야 합니다.")
    norm = lambda v: str(int(v)) if v else ""
    return Provision(norm(jo) + (f"의{norm(sub)}" if sub else ""), norm(hang),
                     norm(ho) + (f"의{norm(ho_sub)}" if ho_sub else ""), mok or "")


def parse_scope(raw: str) -> ParsedScope:
    """Parse direct, enumerated, and same-level ranges in a single-law expression.

    No invented context: an isolated paragraph or a cross-level range needs review.
    Ranges stay intervals, including article/item branches, rather than guessed lists.
    """
    tokens = list(_TOKEN.finditer(raw))
    if not tokens:
        return ParsedScope((), "조문 번호를 해석하지 못했습니다.")
    review = "한정·제외 또는 상대 참조는 원문 확인이 필요합니다." if _QUALIFIER.search(raw) else ""
    scopes: list[Scope] = []
    path = ["", "", "", ""]
    previous_level = -1
    previous_end = 0
    pending_range: tuple[Provision, int] | None = None
    for i, token in enumerate(tokens):
        unit = "목" if token.group(4) else token.group(2)
        level = _LEVEL[unit]
        value = token.group(4) or str(int(token.group(1)))
        if token.group(3):
            if unit == "항":
                return ParsedScope(tuple(scopes), "지원하지 않는 항 가지번호입니다.")
            value += "의" + str(int(token.group(3)))
        gap = raw[previous_end:token.start()]
        # '까지' terminates the previous range and may precede another enumeration.
        if pending_range and gap.strip().startswith("까지"):
            gap = re.sub(r"^\s*까지", "", gap)
        if i and _RANGE.fullmatch(gap):
            if level != previous_level:
                return ParsedScope(tuple(scopes), "서로 다른 단위에 걸친 범위는 추가 확인이 필요합니다.")
            pending_range = (Provision(*path), level)
        elif i and not (level > previous_level and gap.strip() in ("", "의")):
            scopes.append(Scope(Provision(*path), Provision(*path)))
            if not _ENUM.fullmatch(gap):
                review = "인용 사이 문맥을 추가로 해석해야 합니다."
        if level == 0:
            path = [value, "", "", ""]
        else:
            if not path[0]:
                return ParsedScope(tuple(scopes), "조번호가 생략되어 문맥 확인이 필요합니다.")
            path[level] = value
            for lower in range(level + 1, 4):
                path[lower] = ""
        if pending_range:
            start, axis = pending_range
            end = Provision(*path)
            if axis != level or start.path[:axis] != end.path[:axis]:
                return ParsedScope(tuple(scopes), "범위의 상위 조문이 일치하지 않습니다.")
            if axis == 3:
                review = "목 범위의 순서 확인이 필요합니다."
            elif _number(start.path[axis]) > _number(end.path[axis]):
                return ParsedScope(tuple(scopes), "역순 범위는 확정할 수 없습니다.")
            scopes.append(Scope(start, end, axis))
            # A range endpoint is not a separate direct citation.
        previous_level, previous_end = level, token.end()
        if pending_range:
            # Consume '까지' via previous_end so subsequent tokens retain their context.
            tail = re.match(r"\s*까지", raw[previous_end:])
            if tail:
                previous_end += tail.end()
            pending_range = None
            previous_level = -1
    if previous_level != -1:
        scopes.append(Scope(Provision(*path), Provision(*path)))
    if re.search(r"(?:부터|에서|내지|[~～∼])", raw[previous_end:]):
        review = "범위의 끝을 확인하지 못했습니다."
    return ParsedScope(tuple(dict.fromkeys(scopes)), review)


def scope_relation(scope: Scope, target: Provision) -> str | None:
    """exact / covering / contained / range, or None when provably disjoint."""
    for level, (a, b, wanted) in enumerate(zip(scope.start.path, scope.end.path, target.path)):
        if not wanted:
            if not any(target.path[level:]):
                return "contained" if any(scope.start.path[level:]) else "exact"
            if not a:
                continue
            return "review"
        if not a:
            if any(scope.start.path[level + 1:]):
                return "review"
            return "covering"
        if scope.axis == level:
            if level == 3:
                return None  # unsupported: caller preserves review status
            if not (_number(a) <= _number(wanted) <= _number(b)):
                return None
            return "range"
        if a != wanted:
            return None
    return "exact"


def classify(raw: str, target: Provision) -> tuple[str, str]:
    parsed = parse_scope(raw)
    if parsed.review_reason:
        return "review", parsed.review_reason
    matches = [scope_relation(s, target) for s in parsed.scopes]
    if "review" in matches:
        return "review", "항·호의 상위 계층이 생략되어 원문 구조 확인이 필요합니다."
    for relation in ("exact", "range", "covering", "contained"):
        if relation in matches:
            return relation, {
                "exact": "개정 대상과 같은 조문 단위를 인용합니다.",
                "range": "인용 범위에 개정 대상이 포함됩니다.",
                "covering": "개정 대상을 포함하는 상위 조문을 인용합니다.",
                "contained": "개정 대상 안의 하위 조문을 인용합니다.",
            }[relation]
    return "disjoint", "지정한 항·호와 겹치지 않는 인용입니다."
