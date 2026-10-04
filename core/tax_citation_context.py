"""Narrow tax reference context helpers; preserve every original evidence span.

These helpers do not parse annex contents. A broken table citation is restored
only for one manually reviewed full-body hash, edition and exact source span.
"""
from __future__ import annotations

import hashlib
import re

_H = r"[ \t]*"
ANNEX_TOKEN = re.compile(
    r"(?<![가-힣A-Za-z0-9])(?P<kind>별표|별지)" + _H + r"(?:제" + _H + r")?"
    r"(?P<number>\d+)(?:" + _H + r"의" + _H + r"(?P<before>\d+))?"
    r"(?:" + _H + r"호(?:" + _H + r"의" + _H + r"(?P<after>\d+))?)?"
    r"(?:" + _H + r"서식)?"
    r"(?:" + _H + r"[\(（]" + _H + r"(?P<suffix>\d+)" + _H + r"[\)）])?"
)
_QUOTED = re.compile(r"「([^」\n]+)」")
_ADJACENT_NAME = re.compile(r"「([^」\n]+)」[ \t]*(시행령|시행규칙)?[ \t]*(?:의[ \t]*)?$")
_RELATIVE = re.compile(
    r"(?<![가-힣A-Za-z])((?:같은|이|본)[ \t]*(?:법|영|규칙)|법|영|규칙)[ \t]*(?:의[ \t]*)?$"
)
_UNCERTAIN = re.compile(r"(?:해당|다른|상기|그|관련|위|동)[ \t]*(?:법|영|규칙|법령)[ \t]*(?:의[ \t]*)?$")
_LAW_END = re.compile(r"(?:법|법률|시행령|시행규칙|규칙|규정|고시|예규)$")
# Only this source-understood parenthesis may intervene in an annex enumeration.
# Arbitrary parentheses could contain a different law, condition or whole sentence.
_LIST_GAP = re.compile(r"[ \t]*(?:\([ \t]*부표를[ \t]*포함한다[ \t]*\)[ \t]*)?(?:,|및|또는|와|과|ㆍ|·)[ \t]*")
_HERE_RANGE = re.compile(r"(?<![가-힣A-Za-z])이[ \t]*조[ \t]*부터[ \t]*제[ \t]*(\d+)[ \t]*조(?:[ \t]*의[ \t]*(\d+))?[ \t]*까지")

# Source-first frozen independent annotation in the public QA sample set.
_REVIEWED_TABLE = {
    "law": "법인세법 시행규칙", "jo": "49", "effective": "20260701",
    "sha256": "c2972b8278b4f85ef12f633d31241b6aa653f66a4630a90619630024a166d5d2",
    "start": 414, "end": 578,
    "raw": "「국세기본법」 제47       공제 및 감면세액          상실된 자산의 가액  │\n│      산출세액          조의2부터                                         ───────────│\n│                        제47조의5까지",
    "target_name": "국세기본법", "resolved_raw": "제47조의2부터 제47조의5까지",
}


def _segment_start(text, position):
    """Do not inherit an owner across a sentence, newline or inline paragraph."""
    boundary = max((text.rfind(mark, 0, position) for mark in ("\n", ".", "。", ";", "!", "?")), default=-1)
    for match in re.finditer(r"[①-⑳㉑-㉟]", text[:position]):
        boundary = max(boundary, match.start())
    return boundary + 1


def _inside_quote(text, position):
    return any(m.start() <= position < m.end() for m in re.finditer(
        r'「[^」]*」|“[^”\n]*”|"[^"\n]*"', text))


def _family(owner, token):
    token = re.sub(r"\s+", "", token)
    base = re.sub(r"[ \t]+시행(?:령|규칙)$", "", owner)
    if token in ("법", "이법", "본법"):
        return base if base.endswith(("법", "법률")) else ""
    if token in ("영", "이영", "본영"):
        return base + " 시행령" if base.endswith(("법", "법률")) else ""
    if token in ("규칙", "이규칙", "본규칙"):
        if owner.endswith("규칙") and not owner.endswith(" 시행규칙"):
            return owner
        return base + " 시행규칙" if base.endswith(("법", "법률")) else ""
    return ""


def tax_annex_references(law, article, *, issues=None):
    """Return add-compatible annex rows with exact branch/subform labels.

    An optional issues list receives ambiguous/unsupported source occurrences;
    law/article inputs are never mutated. Bare numbers designate the source
    document. Only a syntactically adjacent explicit owner or a pure enumeration
    carries another document's ownership.
    """
    text = article["text"]
    own = law["name"]
    result = []
    previous = None
    range_end = -1

    def issue(start, end, reason):
        if issues is not None:
            issues.append(dict(start=start, end=end, raw=text[start:end], reason=reason))

    for match in ANNEX_TOKEN.finditer(text):
        start, end = match.span()
        if start < range_end:
            continue
        # Never silently reinterpret a supported prefix of an unsupported label.
        extension = re.match(r"[ \t]*(?:[-－][ \t]*\d+|의[ \t]*\d+)", text[end:])
        if extension or (match["before"] and match["after"]):
            issue(start, end + (extension.end() if extension else 0),
                  "별표·서식의 중복 또는 미지원 가지번호 · 원문 확인 필요")
            previous = None
            continue
        tail = re.match(r"[ \t]*(?:부터|내지|에서|[~～∼])[ \t]*(?:(?:별표|별지)[ \t]*)?(?:제[ \t]*)?\d+(?:[ \t]*의[ \t]*\d+)?(?:[ \t]*호(?:[ \t]*의[ \t]*\d+)?)?(?:[ \t]*서식)?(?:[ \t]*까지)?", text[end:])
        if tail:
            range_end = end + tail.end()
            issue(start, range_end, "별표·서식 범위 인용 · 개별 번호로 임의 축약하지 않음")
            previous = None
            continue
        if _inside_quote(text, start):
            issue(start, end, "따옴표 속 별표·서식 표현 · 대상 문서 확인 필요")
            previous = None
            continue

        segment = _segment_start(text, start)
        before = text[segment:start]
        named = _ADJACENT_NAME.search(before)
        relative = _RELATIVE.search(before)
        owner = ""
        explicit = False
        if _UNCERTAIN.search(before):
            issue(start, end, "별표·서식 소속을 특정하지 않은 상대 법령 표현")
            previous = None
            continue
        if named:
            owner = named[1] if _LAW_END.search(named[1]) else ""
            if owner and named[2]:
                owner = _family(owner, "영" if named[2] == "시행령" else "규칙")
            explicit = True
        elif relative:
            token = re.sub(r"\s+", "", relative[1])
            if token.startswith("같은"):
                anchors = {q[1] for q in _QUOTED.finditer(before[:relative.start()]) if _LAW_END.search(q[1])}
                if previous and previous["segment"] == segment and previous["explicit"]:
                    anchors.add(previous["owner"])
                if len(anchors) == 1:
                    anchor = next(iter(anchors))
                    owner = anchor if token == "같은법" else _family(anchor, token[2:])
            else:
                owner = _family(own, token)
            explicit = True
        elif (previous and previous["segment"] == segment
              and previous["kind"] == match["kind"]
              and _LIST_GAP.fullmatch(text[previous["end"]:start])):
            owner, explicit = previous["owner"], previous["explicit"]
        elif (previous and previous["segment"] == segment
              and previous["owner"] != own
              and re.search(r"(?:,|및|또는|와|과|ㆍ|·)[ \t]*$", text[previous["end"]:start])):
            # A mixed annex/form list or an unverified intervening modifier
            # proves neither the old external owner nor this document's owner.
            owner = ""
        else:
            # A numbered article followed by "및 별표" is not proof of annex ownership.
            ambiguous = re.search(r"(?:제[ \t]*\d+[ \t]*조(?:[ \t]*의[ \t]*\d+)?(?:[ \t]*제[ \t]*\d+[ \t]*[항호])*)[ \t]*(?:및|또는|와|과|,|의)[ \t]*$", before)
            unknown = re.search(r"[가-힣A-Za-z]+(?:법|법률|령|규칙|규정|고시|예규)[ \t]*(?:의[ \t]*)?$", before)
            owner = "" if ambiguous or unknown else own
        if not owner:
            issue(start, end, "별표·서식의 대상 법령 미해결")
            previous = None
            continue

        number = str(int(match["number"]))
        branch = match["before"] or match["after"]
        branch_label = "의" + str(int(branch)) if branch else ""
        label = ("별표 " + number + branch_label if match["kind"] == "별표"
                 else "별지 제" + number + "호" + branch_label + "서식")
        if match["suffix"]:
            label += "(" + str(int(match["suffix"])) + ")"
        result.append(dict(target_name=owner, target_ref=label, raw=text[start:end],
                           start=start, end=end, kind="annex", relation="annex_reference"))
        previous = dict(owner=owner, end=end, segment=segment,
                        kind=match["kind"], explicit=explicit)
    return result


def tax_article_overrides(law, article):
    """Return source-preserving article ranges plus their legacy skip spans.

    Callers must suppress legacy numbered and law-level records overlapping each
    skip span, parse resolved_raw, and retain raw/start/end as the source evidence.
    """
    text = article["text"]
    own = law["name"]
    jo = str(article.get("jo", ""))
    result = []
    if re.fullmatch(r"\d+(?:의\d+)?", jo):
        current = tuple(int(x) for x in jo.split("의"))
        current_label = "제" + jo.replace("의", "조의") + ("" if "의" in jo else "조")
        for match in _HERE_RANGE.finditer(text):
            if _inside_quote(text, match.start()):
                continue
            endpoint = (int(match[1]),) + ((int(match[2]),) if match[2] else ())
            if endpoint < current:
                continue
            end_label = "제" + str(int(match[1])) + "조" + ("의" + str(int(match[2])) if match[2] else "")
            result.append(dict(target_name=own, raw=match[0], start=match.start(), end=match.end(),
                resolved_raw=current_label + "부터 " + end_label + "까지",
                skip_spans=[match.span()], verification="explicit-current-article-range"))

    reviewed = _REVIEWED_TABLE
    if (own == reviewed["law"] and jo == reviewed["jo"]
            and (article.get("effective") or law.get("effective")) == reviewed["effective"]
            and hashlib.sha256(text.encode("utf-8")).hexdigest() == reviewed["sha256"]
            and text[reviewed["start"]:reviewed["end"]] == reviewed["raw"]):
        result.append(dict(target_name=reviewed["target_name"], raw=reviewed["raw"],
            start=reviewed["start"], end=reviewed["end"],
            resolved_raw=reviewed["resolved_raw"],
            skip_spans=[(reviewed["start"], reviewed["end"])],
            verification="manually-reviewed-full-body-hash-and-span",
            verified_source_sha256=reviewed["sha256"]))
    return result


_LAW_LEVEL_PHRASE = re.compile(
    r"(?<![가-힣A-Za-z0-9_一-龯])(?:"
    r"법에[ \t]+의한[ \t]+신고(?=$|[\s.,;:!?。)\]]|(?:를|는|의|에|도|로|만|와|가)(?=$|[\s.,;:!?。)\]]))|"
    r"법[ \t]+또는[ \t]+다른[ \t]+법률(?=$|[\s.,;:!?。)\]]|(?:을|은|의|에|도|로|만|과|이)(?=$|[\s.,;:!?。)\]]))"
    r")"
)
_LAW_ALIAS_DECLARATION = re.compile(
    r'(?:이하[ \t]*)?["“‘「\']법["”’」\'][ \t]*(?:이?라[ \t]*(?:한다|함)|이?란|을[ \t]*말한다)'
)
_LAW_LEVEL_MODIFIER = re.compile(
    r"(?<![가-힣A-Za-z])(?:같은|다른|해당|관련|관계|상기|위|그|동|이|본)[ \t]*$"
)


def _law_level_in_quote(text, position):
    # Fail closed for an unclosed quotation too; this helper resolves only two
    # ordinary legal phrases, never examples, replacement text or law titles.
    before = text[:position]
    for opening, closing in (("「", "」"), ("『", "』"), ("“", "”"), ("‘", "’")):
        if before.rfind(opening) > before.rfind(closing):
            return True
    return before.count('"') % 2 == 1 or before.count("'") % 2 == 1


def _law_alias_is_ambiguous(law, article, parent):
    for holder in (law, article):
        aliases = holder.get("aliases") or {}
        if isinstance(aliases, dict) and "법" in aliases and aliases["법"] != parent:
            return True
    own_declaration = re.compile(
        r"(?:「[ \t]*" + re.escape(parent) + r"[ \t]*」|(?<![가-힣A-Za-z])"
        + re.escape(parent) + r")[ \t]*[\(（][ \t]*$"
    )
    # Explicit declarations elsewhere in the document can override the family
    # shorthand. Examine them only after finding one of the two constructions.
    bodies = [article["text"]] + [a.get("text", "") for a in law.get("articles", [])]
    for body in bodies:
        for match in _LAW_ALIAS_DECLARATION.finditer(body):
            # Only 'Parent Act (hereinafter "법")' proves the default meaning.
            if not match[0].startswith("이하") or not own_declaration.search(body[:match.start()]):
                return True
    return False


def tax_law_level_references(law, article):
    """Resolve only two audited unnumbered parent-act constructions.

    '법에 의한 신고' and '법 또는 다른 법률' retain their complete original
    quote. The unnamed other law never gains a guessed target. A statute,
    unrelated special rule or shadowing definition has no family fallback.
    """
    text = article["text"]
    family = re.fullmatch(r"(.+(?:법|법률))[ \t]+시행(?:령|규칙)", law["name"])
    if not family:
        return []
    matches = list(_LAW_LEVEL_PHRASE.finditer(text))
    if not matches:
        return []
    parent = family[1]
    if _law_alias_is_ambiguous(law, article, parent):
        return []
    result = []
    for match in matches:
        if _law_level_in_quote(text, match.start()):
            continue
        before = text[_segment_start(text, match.start()):match.start()]
        if _LAW_LEVEL_MODIFIER.search(before):
            continue
        # A different explicitly named law in this same sentence makes this
        # narrow, otherwise-unqualified construction unsuitable for fallback.
        if any(q[1] != parent for q in _QUOTED.finditer(before)):
            continue
        result.append(dict(target_name=parent, target_ref="법령·정의 참조",
            raw=match[0], start=match.start(), end=match.end(),
            kind="law", relation="law_reference", context_review=True))
    return result
