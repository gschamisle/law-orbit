"""Quoted legal titles whose decree/rule suffix sits outside the title marks.

Offsets always refer to the original source. Only an adjacent, complete suffix
extends a base Act title; conjunctions and explanatory prose never do.
"""
import re


# Keep the title as capture 1 for the existing citation patterns. The lookahead
# requires paired marks, so a mismatched 「...』 is not an explicit title.
QUOTED_PATTERN = r'(?:(?=「[^「」『』]+」)|(?=『[^「」『』]+』))[「『]([^「」『』]+)[」』]'
QUOTED_RE = re.compile(QUOTED_PATTERN)
# Tax ingestion retains nested opening marks in the raw evidence so it can
# show an unresolved title. The matching closing mark still has to be present.
REVIEW_QUOTED_PATTERN = r'(?:(?=「[^」』]+」)|(?=『[^」』]+』))[「『]([^」』]+)[」』]'
REVIEW_QUOTED_RE = re.compile(REVIEW_QUOTED_PATTERN)
DERIVATIVE_PATTERN = (r'\s*(?:시행규칙|시행령)'
                      r'(?=$|\s|[^\w]|제\s*\d|별표|별지|'
                      r'(?:으로|에|의|을|과|와|은|는|이|도|만|상)(?![가-힣]))')
DERIVATIVE_RE = re.compile(DERIVATIVE_PATTERN)


def quoted_owner(text, match):
    """Return the exact owner and exclusive source end of a quoted-title match."""
    name, end = match[1], match.end()
    if name.rstrip().endswith(('법', '법률')):
        suffix = DERIVATIVE_RE.match(text, end)
        if suffix:
            name = name.rstrip() + ' ' + suffix[0].strip()
            end = suffix.end()
    return name, end
