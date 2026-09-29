"""Numbered annex references for the administrative adapter, without body parsing.

Only adjacent owners, explicit aliases and unqualified references to this
document are resolved. Relative owners never cross a source paragraph.
"""
from __future__ import annotations

import re
from collections import defaultdict

from core.fsc_collection import norm

ANNEX = re.compile(r'(?<![가-힣A-Za-z])(별표|별지)\s*(?:제\s*)?(\d+)(?:\s*의\s*(\d+))?\s*(?:호\s*서식|호|서식)?')
QUOTED = re.compile(r'「([^」]+)」')
DECL = r'(?:\s*\(이하\s*["“][^"”]+["”]\s*(?:이?라\s*(?:한다|함))?\s*\))?'
LAW_END = re.compile(r'(?:법|법률|시행령|규칙|규정|세칙|조례|훈령|고시|예규|지침|요령|기준|조건|절차)$')
SAME = re.compile(r'같은\s*(법\s*시행령|법\s*시행규칙|법|시행령|시행규칙|영|규칙|규정|세칙|조례)\s*(?:의\s*)?$')
OWN = re.compile(r'(?<![가-힣])(?:이|본)\s*(?:법|영|규칙|규정|세칙|조례|훈령|고시|예규|지침|요령|기준|조건|절차)\s*(?:의\s*)?$')
JOIN = re.compile(r'\s*(?:및|또는|와|과|ㆍ|·|,)\s*$')
RANGE = re.compile(ANNEX.pattern + r'\s*(?:부터|내지|에서|[~～∼－-])\s*(?:(?:별표|별지)\s*)?(?:제\s*)?\d+(?:\s*의\s*\d+)?\s*(?:호\s*서식|호|서식)?(?:\s*까지)?')
UNCERTAIN = re.compile(r'(?<![가-힣])(?:(?:해당|다른|그|상기|위|동|관련|상위)\s*(?:법령|법|시행령|시행규칙|영|규칙|규정|세칙|조례)\s*(?:의\s*)?|(?:같은|해당|그|상기|위)\s*)$')
RELATIVE_NAMES = {'법', '영', '시행령', '규칙', '시행규칙', '규정', '세칙', '조례',
                  '같은법', '동법', '해당법', '관련법', '상위법', '이법', '본법'}


def _derived(owner, token):
    token = norm(token)
    if token in ('법', '규정', '세칙', '조례'):
        return owner
    suffix = ' 시행령' if token in ('영', '시행령', '법시행령') else ' 시행규칙'
    if token == '규칙' and owner.endswith('규칙'):
        return owner
    base = re.sub(r'\s*시행(?:령|규칙)$', '', owner)
    return base + suffix if base.endswith(('법', '법률')) else ''


def annex_references(law, article, corpus):
    """Return adapter-shaped annex edges; append only unresolved annex issues."""
    if law.get('provider') == 'ordin' or not article.get('jo'):
        # Ordinances have their own extractor; empty-jo units are annex bodies.
        return []
    from core.fsc_administrative import aliases_from, provision_blocks

    text = article['text']
    if not ANNEX.search(text):
        return []
    candidates = defaultdict(set)
    for document in corpus:
        for label in (document['name'], document.get('short_name'), *document.get('citation_names', [])):
            if label:
                candidates[norm(label)].add(document['name'])
    names = {label: next(iter(values)) for label, values in candidates.items() if len(values) == 1}
    local, local_evidence = aliases_from(text)
    evidence = law.get('alias_evidence', []) + local_evidence
    conflicts = {norm(e['alias']) for e in evidence
                 if len({norm(v['target_law']) for v in evidence if norm(v['alias']) == norm(e['alias'])}) > 1}
    aliases = {norm(k): names.get(norm(v), v) for k, v in {**law.get('aliases', {}), **local}.items()}
    # Ordinary statutory families are structural; special rules need declarations.
    if law.get('provider') == 'eflaw' and law['name'].endswith((' 시행령', ' 시행규칙')):
        base = re.sub(r' 시행(?:령|규칙)$', '', law['name'])
        for token, owner in (('법', base), ('영', base + ' 시행령'), ('규칙', base + ' 시행규칙')):
            aliases.setdefault(token, owner)
    for label in conflicts:
        aliases.pop(label, None)
    lookup = {**names, **aliases}
    for label in conflicts:
        lookup.pop(label, None)
    alternatives = sorted(lookup, key=len, reverse=True)
    prefix = re.compile(r'(?<![가-힣A-Za-z])(' + '|'.join(r'\s*'.join(map(re.escape, a)) for a in alternatives) + ')' + DECL + r'\s*(?:의\s*)?$') if alternatives else None
    adjacent_quote = re.compile(r'「([^」]+)」' + DECL + r'\s*(시행령|시행규칙)?\s*(?:의\s*)?$')
    quotes = list(QUOTED.finditer(text))
    ranges = list(RANGE.finditer(text))
    blocks = article.get('blocks') or provision_blocks(text, article['jo'])
    outputs = []
    previous = None

    def quoted_owner(name):
        label = norm(name)
        if label in conflicts or '「' in name or UNCERTAIN.fullmatch(name):
            return ''
        return lookup.get(label, name if LAW_END.search(name) and label not in RELATIVE_NAMES else '')

    def issue(start, end, reason):
        entry = dict(raw=text[start:end], start=start, end=end, reason=reason)
        issues = article.setdefault('citation_issues', [])
        if entry not in issues:
            issues.append(entry)

    for match in ANNEX.finditer(text):
        start, end = match.span()
        # Whitespace between an annex number and its following clause is not part of the number.
        while end > start and text[end - 1].isspace():
            end -= 1
        range_match = next((r for r in ranges if r.start() <= start < r.end()), None)
        if range_match:
            issue(range_match.start(), range_match.end(), '별표·서식 번호의 범위 인용 · 대상 번호와 소속 원문 확인 필요')
            previous = None
            continue
        suffix = re.match(r'\s*(?:[-－]\s*\d+|의\s*\d+)(?:\s*호?\s*서식)?', text[end:])
        if suffix:
            issue(start, end + suffix.end(), '별표·서식 번호의 가지번호 형식 · 원문 확인 필요')
            previous = None
            continue
        if any(q.start() <= start < q.end() for q in quotes) or any(q.start() < start < q.end() for q in re.finditer(r'["“][^"”\n]*["”]', text)):
            issue(start, end, '따옴표 속 별표·서식 번호 · 대상 문서 확인 필요')
            previous = None
            continue
        block_start = text.rfind('\n', 0, start) + 1
        for block in blocks:
            if block['start'] <= start < block['end']:
                block_start = max(block_start, block['start'])
                break
        before = text[block_start:start]
        quote = adjacent_quote.search(before)
        same = SAME.search(before)
        own = OWN.search(before)
        named = prefix.search(before) if prefix else None
        owner, review = '', False
        uncertain = UNCERTAIN.search(before)
        if uncertain:
            start = block_start + uncertain.start()
        elif quote:
            owner = quoted_owner(quote[1])
            if quote[2] and owner:
                owner = _derived(owner, quote[2])
            start = block_start + quote.start()
        elif same:
            # Require one explicit owner within this paragraph, never a prior paragraph.
            anchors = {quoted_owner(q[1]) for q in QUOTED.finditer(before[:same.start()])
                       if LAW_END.search(q[1]) or norm(q[1]) in lookup}
            if previous and previous['block'] == block_start and previous['explicit']:
                anchors.add(previous['owner'])
            for label, target in lookup.items():
                pattern = r'(?<![가-힣A-Za-z])' + r'\s*'.join(map(re.escape, label)) + r'\s+제\s*\d+\s*조'
                if re.search(pattern, before[:same.start()]):
                    anchors.add(target)
            owner = _derived(next(iter(anchors)), same[1]) if len(anchors) == 1 else ''
            start, review = block_start + same.start(), True
        elif own:
            owner, start = law['name'], block_start + own.start()
        elif named:
            owner, start = lookup[norm(named[1])], block_start + named.start()
        elif previous and previous['block'] == block_start and JOIN.fullmatch(text[previous['end']:start]):
            owner = previous['owner']
        elif re.search(r'제\s*\d+\s*조(?:\s*의\s*\d+)?(?:\s*제\s*\d+\s*[항호])*(?:\s*[가-하]\s*목)?\s*(?:(?:및|또는|와|과|,)\s*|의\s*)$', before):
            # "규정 제9조 및 별표 1" does not establish whether the annex is
            # owned by the named regulation or by this document.
            owner = ''
        else:
            unknown = re.search(r'([가-힣A-Za-z]+(?:법|법률|령|규칙|규정|세칙|조례|고시|예규|지침|요령|기준|조건|절차)|법|영|규칙|규정|세칙)\s*(?:의\s*)?$', before)
            if unknown:
                start = block_start + unknown.start()
            else:
                owner = law['name']
        if not owner:
            issue(start, end, '별표·서식의 대상 법령·규정 또는 상대 참조 미해결')
            previous = None
            continue
        owner = names.get(norm(owner), owner)
        number = str(int(match[2])) + ('의' + str(int(match[3])) if match[3] else '')
        ref = '별표 ' + number if match[1] == '별표' else '별지 제' + number + '호서식'
        outputs.append(dict(target_name=owner, target_ref=ref, raw=text[start:end], start=start, end=end,
                            kind='annex', relation='annex_reference', context_review=review))
        previous = dict(owner=owner, end=end, block=block_start,
                        explicit=bool(quote or same or own or named))
    return outputs
