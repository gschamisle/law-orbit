"""Explicit before/after article snapshots; never infer the former end from citations."""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass

from core.citation_scope import parse_target

_CIRCLES = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚㉛㉜㉝㉞㉟㊱㊲㊳㊴㊵㊶㊷㊸㊹㊺㊻㊼㊽㊾㊿"
_MARKER = re.compile(rf"(?m)^[ \t]*(?:([{_CIRCLES}])|제\s*(\d+)\s*항(?=\s|$))[ \t]*")
_HEADER = re.compile(r"^제\s*\d+\s*조(?:\s*의\s*\d+)?(?:\s*[（(][^）)\n]*[）)])?")
_ARTICLE_LINE = re.compile(r"(?m)^\s*제\s*\d+\s*조(?:\s*의\s*\d+)?\s*[（(]")


@dataclass(frozen=True)
class Paragraph:
    number: int
    text: str
    start: int
    end: int


@dataclass(frozen=True)
class ArticleSnapshot:
    article: str
    version: str
    text: str
    sha256: str
    paragraphs: tuple[Paragraph, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def parse_article(text: str, reference: str, version: str) -> ArticleSnapshot:
    """Accept one complete article with a heading and explicit, ordered paragraph labels.

    Circled numbers or line-initial '제1항 ...' are accepted. Item numbers and
    amendment instructions are not treated as paragraph structure. Offsets refer
    to the normalized text stored in this snapshot (Unicode code points).
    """
    target = parse_target(reference)
    if target.hang or target.ho or target.mok:
        raise ValueError("비교 대상은 제2조처럼 조 단위로 입력하세요.")
    text = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff").strip()
    if not text or len(text) > 100_000:
        raise ValueError("개정 전·후 조문 전체를 각각 입력하세요. 한 조문은 10만 자 이내로 입력할 수 있습니다.")
    header = _HEADER.match(text)
    if not header:
        raise ValueError("각 원문은 '제2조(제목)'처럼 조문 표제로 시작해야 합니다.")
    header_ref = re.match(r"제\s*\d+\s*조(?:\s*의\s*\d+)?", header.group()).group()
    if parse_target(header_ref).jo != target.jo:
        raise ValueError(f"원문 표제와 비교 대상 {target.label}의 번호가 다릅니다.")
    if _ARTICLE_LINE.search(text[header.end():]):
        raise ValueError("여러 조문이 들어 있습니다. 비교할 한 조문 전체만 입력하세요.")
    body = text[header.end():]
    # A first paragraph may immediately follow the article heading on the same line.
    leading = len(body) - len(body.lstrip())
    body = body.lstrip()
    offset = header.end() + leading
    markers = list(_MARKER.finditer(body))
    if not markers or markers[0].start() != 0:
        raise ValueError("각 항을 새 줄의 ①·② 또는 '제1항 내용' 형식으로 표시하세요. 개정 지시문만으로는 전체 구조를 확인할 수 없습니다.")
    numbers = [(_CIRCLES.index(m.group(1)) + 1) if m.group(1) else int(m.group(2)) for m in markers]
    if numbers != list(range(1, len(numbers) + 1)):
        raise ValueError("항 번호가 제1항부터 순서대로 이어져야 합니다. 누락·중복·발췌 여부를 확인하세요. 삭제된 항도 번호와 '삭제'를 남겨 주세요.")
    paragraphs = []
    for i, marker in enumerate(markers):
        end = markers[i + 1].start() if i + 1 < len(markers) else len(body)
        content = body[marker.end():end].strip()
        if not content or re.search(rf"[{_CIRCLES}]", content):
            raise ValueError("항 내용이 비었거나 한 줄에 여러 항이 있습니다. 각 항을 새 줄에 입력하세요.")
        paragraphs.append(Paragraph(numbers[i], content, offset + marker.start(), offset + end))
    return ArticleSnapshot(target.label, version.strip() or "버전 미지정", text,
                           hashlib.sha256(text.encode("utf-8")).hexdigest(), tuple(paragraphs))


def compare_articles(before: ArticleSnapshot, after: ArticleSnapshot) -> dict:
    if before.article != after.article:
        raise ValueError("같은 조문의 개정 전·후 원문이 필요합니다.")
    old = {p.number: p.text for p in before.paragraphs}
    new = {p.number: p.text for p in after.paragraphs}
    added, removed = sorted(new.keys() - old.keys()), sorted(old.keys() - new.keys())
    normalize = lambda text: re.sub(r"\s+", "", text)
    modified = sorted(n for n in old.keys() & new.keys() if normalize(old[n]) != normalize(new[n]))
    deleted = sorted(n for n, text in {**old, **new}.items() if re.match(r"^삭제(?:\s|[.。<〈(（]|$)", text))
    # Include formerly deleted slots even if this amendment reuses their numbers.
    deleted = sorted(set(deleted) | {n for n, text in old.items() if re.match(r"^삭제(?:\s|[.。<〈(（]|$)", text)})
    issues = []
    if removed:
        issues.append("항 번호가 사라졌습니다. 삭제·번호 이동 여부를 확인해야 합니다.")
    if modified:
        issues.append("기존 항의 내용도 바뀌었습니다. 번호 이동·대체·내용 개정을 함께 확인해야 합니다.")
    if deleted:
        issues.append("삭제로 표시된 항이 있습니다. 종전 적용 대상의 범위를 원문에서 확인해야 합니다.")
    kind = "append" if added and not issues else "complex" if added or removed or modified else "none"
    return {"article": before.article, "kind": kind, "before": before.to_dict(), "after": after.to_dict(),
            "before_numbers": sorted(old), "after_numbers": sorted(new), "added": added,
            "removed": removed, "modified": modified, "deleted_slots": deleted, "issues": issues,
            "former_last": max(old), "source": "입력된 조문 전체 기준"}
