"""Display order shared by local navigation and static releases.

Order reflects expected task frequency and current usefulness, not a usage metric
or a claim that every included document belongs to the same ministry.
"""

DOMAINS = {
    'constitution': '헌법',
    'tax': '국세',
    'procurement': '조달·계약',
    'customs': '관세·통관',
    'forex': '외환',
    'state_property': '국유재산',
    'public_institutions': '공공기관',
    'treasury': '국고·회계',
    'fsc': '금융',
    'ftc': '공정거래',
    'labor': '고용·노동',
    'medical': '보건의료',
    'local_tax': '지방세',
    'housing': '국토·건축·주택',
    'environment': '환경·화학·안전',
}


def ordered_domains(entries):
    """Reorder metadata without changing entries or silently discarding domains."""
    by_id = {entry['id']: entry for entry in entries}
    if len(by_id) != len(entries) or set(by_id) - DOMAINS.keys():
        raise ValueError('Duplicate or unknown galaxy menu')
    return [by_id[domain] for domain in DOMAINS if domain in by_id]
