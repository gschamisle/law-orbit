"""Surface explicit article-movement notes without rewriting cited numbers."""
import re
from core.citation_scope import Provision

MOVE = re.compile(r'\[\s*제\s*(\d+)\s*조(?:\s*의\s*(\d+))?\s*에서\s*이동')
DATE = re.compile(r'<\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.\s*>')


def movement_review(document, target, source_effective):
    """Dated later movements and undated movements require edition review.

    An old number can now exist with a different subject. The original target
    stays intact and all candidates are reported, including ambiguous moves.
    """
    if not document:
        return {}
    stamp = re.sub(r'[^0-9]', '', source_effective or '')
    candidates = []
    for article in document.get('articles', []):
        for note in article.get('reference_notes', []):
            match = MOVE.search(note)
            if not match:
                continue
            base, branch = match.groups()
            old = str(int(base)) + ('의' + str(int(branch)) if branch else '')
            dated = DATE.search(note, match.end())
            date = ''.join(f'{int(n):0{width}}' for n,width in zip(dated.groups(),(4,2,2))) if dated else ''
            if old == target.jo and article['jo'] != old and (not date or not stamp or stamp < date):
                candidates.append(dict(ref=Provision(article['jo']).label,
                                       title=article.get('title', ''), date=date, raw=note))
    if not candidates:
        return {}
    labels = ', '.join(c['ref'] for c in candidates)
    return dict(target_provision_status='renumbered-reference-review', context_review=True,
                target_movement_candidates=candidates,
                target_reference_note=f'조문 이동·판본 확인 필요 · 원문은 {target.label} 인용. 수집 판본에 {labels}로 이동한 이력이 있습니다. 원문 번호를 자동 변경하지 않았습니다.')
