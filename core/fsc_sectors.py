"""Curated document tags; a tag is a navigation aid, not an impact conclusion."""
from __future__ import annotations
from copy import deepcopy
from core.fsc_collection import norm

SECTORS = {'all':'전체 금융', 'insurance':'보험', 'banking':'은행', 'securities':'증권·자산운용',
           'credit':'여신·서민금융', 'digital':'전자금융·가상자산', 'common':'공통'}
# Transparent title rules are deliberately conservative; unmatched material is
# common, never silently assigned to every sector from a passing body mention.
TITLE_RULES = {
    'insurance': ('보험업','보험사기','보험회사','보험계리','보험모집','보험가입'),
    'banking': ('은행법','은행업','인터넷전문은행','한국산업은행','중소기업은행','한국수출입은행','한국주택금융공사','이중상환청구권'),
    'securities': ('자본시장','금융투자','증권','전자등록','사채','자산유동화','기업구조조정투자','우리사주','유동화전문'),
    'credit': ('여신전문','상호저축은행','상호금융','신용협동조합','대부업','서민','개인금융채권','개인채무자보호','신용보증','주택저당채권'),
    'digital': ('전자금융','가상자산','온라인투자연계','혁신금융','핀테크'),
}
MULTI_RULES = {'퇴직연금': ('insurance','banking','securities'),
               '온라인투자연계': ('credit','digital')}

def tags_for(name: str) -> tuple[list[str], list[str]]:
    name = norm(name)
    tags, basis = set(), []
    for sector, tokens in TITLE_RULES.items():
        hits = [t for t in tokens if norm(t) in name]
        if hits:
            tags.add(sector)
            basis += ['명칭 분류: '+t for t in hits]
    # Savings banks have their own credit/mutual sector, not the Banking Act sector.
    if '상호저축은행' in name:
        tags.discard('banking')
    for token, values in MULTI_RULES.items():
        if token in name:
            tags.update(values)
            basis.append('복수 업권 분류: '+token)
    return sorted(tags or {'common'}), basis or ['업권 특정 명칭 없음 · 공통/기관운영 자료']

def tag_source(source: dict) -> dict:
    result = deepcopy(source)
    for doc in result['laws'] + result.get('administrative_rules', []):
        doc['sectors'], doc['sector_basis'] = tags_for(doc['name'])
        doc['sector_tag_version'] = 1
    return result

def sector_graph(graph: dict, sector: str) -> dict:
    if sector not in SECTORS:
        raise ValueError('지원하지 않는 금융 분야입니다.')
    if sector == 'all':
        return graph
    names = {d['name'] for d in graph['catalog'] if sector in d.get('sectors', tags_for(d['name'])[0])}
    return {**graph, 'laws': sorted(names), 'focus_laws': sorted(names),
            'catalog': [d for d in graph['catalog'] if d['name'] in names],
            'edges': [e for e in graph['edges'] if e['source_law'] in names and e['target_law'] in names]}

def mark_sector(result: dict, graph: dict, sector: str) -> dict:
    tagged = {d['name']: d.get('sectors', tags_for(d['name'])[0]) for d in graph['catalog']}
    def mark(row):
        outside = sector != 'all' and sector not in tagged.get(row['neighbor_law'], [])
        return {**row, 'out_of_sector': outside,
                'sector_relation': '분야 밖 관련 조문' if outside else '분야 안 관련 조문',
                'neighbor_sectors': tagged.get(row['neighbor_law'], []),
                'reason': ('분야 밖 관련 조문 · ' if outside else '') + row['reason']}
    return {**result, 'rows': [mark(r) for r in result['rows']],
            'broad_rows': [mark(r) for r in result.get('broad_rows', [])]}

def style_sector(data: dict, sector: str) -> dict:
    data['galaxy_title'] = '금융법 은하' + (' · '+SECTORS[sector] if sector != 'all' else '')
    for node in data['nodes']:
        if any(e.get('out_of_sector') for e in node.get('evidence', [])):
            node['status'] = '분야 밖 관련 조문 · '+node.get('status','')
            node['color'] = '#b4a0ef'
    return data
