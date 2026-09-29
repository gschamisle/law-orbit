"""Metadata for the connected annex; never infer or extract annex contents."""
from core.law_universe import norm


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
    annex = index.get(norm(owner), {}).get(norm(ref))
    result = dict(row)
    if annex is not None:
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
