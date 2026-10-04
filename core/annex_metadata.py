"""Metadata for the connected annex; never infer or extract annex contents."""
import re
from core.law_universe import norm


def annex_key(ref):
    """Equivalent printed branch placement; preserve numbered subforms."""
    compact = re.sub(r'\s+', '', ref)
    match = re.fullmatch(r'(별표|별지)(?:제)?(\d+)(?:의(\d+))?(?:호(?:의(\d+))?)?(?:서식)?(?:[(](\d+)[)])?', compact)
    if not match or (match[3] and match[4]):
        return ('literal', compact)
    return (match[1], str(int(match[2])), str(int(match[3] or match[4])) if match[3] or match[4] else '', match[5] or '')


def annex_index(documents):
    return {norm(d['name']): {norm(a['ref']): a for a in d.get('annexes', [])}
            for d in documents}


def annotate_annex(row, index):
    """Use the neighbor's annex on reverse rows, not the cited article's law."""
    if row.get('neighbor_kind') == 'annex':
        owner = row.get('neighbor_law', '')
        ref = row.get('neighbor_jo') or row.get('neighbor_ref', '')
    elif row.get('target_kind') == 'annex' and row.get('direction') != 'reverse':
        owner, ref = row.get('target_law', ''), row.get('target_ref', '')
    else:
        return row
    catalog = index.get(norm(owner), {})
    annex = catalog.get(norm(ref))
    if annex is None:
        matches = [a for a in catalog.values() if annex_key(a['ref']) == annex_key(ref)]
        if len(matches) == 1:
            annex = matches[0]
    result = dict(row)
    if annex is None and owner == '부가가치세법 시행규칙':
        key = annex_key(ref)
        # Official PDF flSeq162619767 visibly contains (1) on p1 and (2) on p3.
        # Pin this verified physical container, never infer arbitrary subforms.
        candidate = catalog.get(norm('별지 제16호서식'))
        if (key in (('별지', '16', '', '1'), ('별지', '16', '', '2'))
                and candidate and candidate.get('effective') == '20260401'
                and row.get('source_effective' if row.get('direction') == 'reverse' else 'target_effective') == '20260401'
                and candidate.get('title') == '신용카드매출전표등 수령명세서(갑, 을)'
                and 'https://www.law.go.kr/LSW/flDownload.do?flSeq=162619767' in candidate.get('urls', [])):
            annex = candidate
            result.update(annex_container_ref=annex['ref'], annex_container_page=1 if key[3]=='1' else 3,
                annex_container_sha256='bd850a4cd5318d5eb7e185433868ecfa8a52d1ec512f53d52090c7c9ecf63d72')
    if annex is not None:
        if row.get('neighbor_kind') == 'annex':
            # The frontend opens a physical catalog entry by exact ref, while
            # target_ref and neighbor_ref retain the printed citation identity.
            result['neighbor_jo'] = annex['ref']
        result['annex_urls'] = list(dict.fromkeys((row.get('annex_urls') or [])+(annex.get('urls') or [])))
        result['annex_analyzed'] = bool(annex.get('analysis') or annex.get('body_analysis'))
    else:
        result['annex_urls'] = list(dict.fromkeys(row.get('annex_urls') or []))
        result['annex_analyzed'] = False
    return result


def public_annex_metadata(annex):
    """Only identity and official links. Existing verified analyses stay separate."""
    return {**{k: annex.get(k) for k in ('ref', 'title', 'effective', 'urls')},
            'status': 'not-analyzed', 'connections': [], 'issues': []}
