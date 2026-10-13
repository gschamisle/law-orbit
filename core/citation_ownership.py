"""Bounded continuation of an explicitly named owner, never semantic matching."""
import re


def scopes(text):
    """Identify nested annotations, leaving quoted law titles opaque."""
    result, stack, quoted = [], [], False
    for offset, char in enumerate(text):
        result.append(tuple(stack))
        if char == '「':
            quoted = True
        elif char == '」':
            quoted = False
        elif not quoted and char in '(（[':
            stack.append(offset)
        elif not quoted and char in ')）]' and stack:
            stack.pop()
    result.append(tuple(stack))
    return result


def without_annotations(gap):
    """Remove complete nested annotations only; a crossed boundary is invalid."""
    depth, result = 0, []
    for char in gap:
        if char in '(（[':
            depth += 1
        elif char in ')）]':
            depth -= 1
            if depth < 0:
                return None
        elif depth == 0:
            result.append(char)
    return None if depth else ''.join(result)


def joined_owner(gap):
    """A post-citation noun phrase joined to the next citation in one sentence.

    A non-adjacent continuation remains reviewable; punctuation, paragraph
    changes, a new quoted owner and explicit self references stop inheritance.
    """
    # A comma after a definition/condition is not an enumeration of citations.
    # Nor may an owner escape a parenthesis (or enter an unclosed one).
    # Parenthetical article titles may sit between enumerated citations. A
    # bracket inside a later noun phrase is not such an article-title suffix.
    if re.search(r'[(（\[]', gap) and not re.match(r'\s*[(（\[]', gap):
        return False
    gap = without_annotations(gap)
    if gap is not None and re.fullmatch(
        r'\s*(?:(?:[,ㆍ·]|및|또는)\s*(?:같은\s*조\s*)?제\s*\d+\s*[항호]'
        r'(?:\s*(?:부터|내지|에서)\s*제\s*\d+\s*[항호]\s*까지)?\s*)+'
        r'(?:[,ㆍ·]|및|또는)\s*', gap
    ):
        gap = ', '
    if gap is None or re.search(
        r'제\s*\d+\s*(?:조|항|호|목)|(?:같은|동)\s*(?:조|항|호|목)'
        r'|(?:말하|포함하|제외하|준용하|적용하|정하|아니하)(?:며|고|되|는|여|지)'
        r'|(?:경우|때)\s*(?:에는|에|는|,)', gap
    ):
        return False
    return bool(len(gap) <= 180
        and not re.search(r'[.。!?;\n「」①-⑳㉑-㉟]|(?<![가-힣])(?:이|본|해당|다른)\s*(?:법|영|규칙|규정)', gap)
        and re.fullmatch(r'\s*(?:(?:에\s*(?:따른|의한)|의)\s+[^「」]+?\s*)?(?:및|또는|와|과|,|ㆍ|·)\s*', gap))
