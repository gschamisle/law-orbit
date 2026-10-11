"""Bounded continuation of an explicitly named owner, never semantic matching."""
import re


def joined_owner(gap):
    """A post-citation noun phrase joined to the next citation in one sentence.

    A non-adjacent continuation remains reviewable; punctuation, paragraph
    changes, a new quoted owner and explicit self references stop inheritance.
    """
    return bool(len(gap) <= 180
        and not re.search(r'[.。!?;\n「」①-⑳㉑-㉟]|(?<![가-힣])(?:이|본|해당|다른)\s*(?:법|영|규칙|규정)', gap)
        and re.fullmatch(r'\s*(?:(?:에\s*(?:따른|의한)|의)\s+[^「」]+?\s*)?(?:및|또는|와|과|,|ㆍ|·)\s*', gap))
