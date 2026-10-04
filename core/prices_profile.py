"""Price-policy work area: selected statutory bases, not a whole tariff corpus."""
from core.fsc_collection import norm

PRICE = '물가안정에 관한 법률'
AGRI = '농수산물 유통 및 가격안정에 관한 법률'
CALCULATION = '공공요금 산정기준'
DISPLAY = '(산업통상자원부) 가격표시제 실시요령'
FEES = '물가안정에관한법률 제4조제3항의 규정에 의한 수수료 협의대상 및 방법'
# Official document titles are preserved, including the issuer qualifier above.
# Prices has no declared 물가안정법 시행규칙. Generic family expansion would invent it.
FAMILIES = {
    PRICE: (PRICE, PRICE + ' 시행령'),
    AGRI: tuple(AGRI + suffix for suffix in ('', ' 시행령', ' 시행규칙')),
}
REFERENCES = ('소비자기본법', '관세법', '공공기관의 정보공개에 관한 법률')
STATUTES = tuple(doc for family in FAMILIES.values() for doc in family) + REFERENCES
# FEES is returned only by the official historical (nw=2) API as of 2026-10-04.
# Keep its title for provenance; it is not a current collected rule.
RULES = (CALCULATION, DISPLAY)
KEYWORDS = {
    'consultation': ('공공요금', '수수료', '협의', '산정', '원가', '요금산정', '투자보수'),
    'display': ('가격표시', '판매가격', '단위가격', '권장소비자가격', '표시금지'),
    'supply': ('농수산물', '농산물', '수산물', '수급', '비축', '수입추천', '할당관세'),
    'stabilization': ('최고가격', '긴급수급', '매점매석', '과징금', '가격안정', '물가안정'),
}
_DOCUMENT_SECTORS = {norm(doc): ['stabilization'] for doc in FAMILIES[PRICE]}
_DOCUMENT_SECTORS.update({norm(doc): ['supply'] for doc in FAMILIES[AGRI]})
_DOCUMENT_SECTORS.update({norm(CALCULATION): ['consultation'],
                          norm(DISPLAY): ['display']})


def document_tags(name):
    """Exact owner tags; shared reference laws are not reassigned to price policy."""
    return list(_DOCUMENT_SECTORS.get(norm(name), []))


def article_tags(name, article):
    """Multiple navigation tags cannot create a legal citation or determine duties."""
    result = document_tags(name)
    value = norm(article.get('title', '') + ' ' + article.get('text', ''))
    anchors = {(norm(PRICE), '3'): ['display'], (norm(PRICE), '4'): ['consultation'],
               (norm(AGRI), '15'): ['supply']}
    for sector in anchors.get((norm(name), article.get('jo', '')), []):
        if sector not in result:
            result.append(sector)
    for sector, words in KEYWORDS.items():
        if sector not in result and any(norm(word) in value for word in words):
            result.append(sector)
    return result


_DOCUMENT_OWNERS = {
    **{norm(n): frozenset(('재정경제부',)) for n in FAMILIES[PRICE]+(CALCULATION, '관세법')},
    **{norm(n): frozenset(('농림축산식품부','해양수산부')) for n in FAMILIES[AGRI]},
    norm('소비자기본법'):frozenset(('공정거래위원회',)),
    norm('공공기관의 정보공개에 관한 법률'):frozenset(('행정안전부',)),
}

def document_authorities(name,provider):
    names=STATUTES if provider=='eflaw' else RULES if provider=='admrul' else ()
    if norm(name) not in {norm(n) for n in names}:return frozenset()
    return _DOCUMENT_OWNERS.get(norm(name),frozenset())

def selected(name,authority,provider):
    from core.procurement_collection import authorities
    actual=authorities(authority)
    if provider=='admrul' and norm(name)==norm(DISPLAY):
        return actual in ({'산업통상부'},{'산업통상자원부'})
    expected=document_authorities(name,provider)
    return bool(expected and actual==expected)

CASE_EXPECTATIONS={
    (PRICE,'4'):({'source_law':PRICE+' 시행령','source_jo':'6','target_law':PRICE,'target_jo':'4',
                 'quote_contains':'법 제4조제1항'},),
    (PRICE,'3'):({'source_law':DISPLAY,'source_jo':'1','target_law':PRICE,'target_jo':'3'},
                 {'source_law':DISPLAY,'source_jo':'1','target_law':'소비자기본법','target_jo':'12'}),
    (AGRI,'15'):({'source_law':AGRI,'source_jo':'15','target_law':'관세법','target_jo':'71'},),
}


PROFILE = dict(
    title='물가·공공요금',
    authorities=('재정경제부', '농림축산식품부', '해양수산부', '산업통상부', '산업통상자원부',
                 '공정거래위원회', '행정안전부'),
    statutes=STATUTES, required=STATUTES,
    law_queries=(PRICE, AGRI, *REFERENCES),
    rule_queries=(CALCULATION, '가격표시제 실시요령'),
    rules=RULES, required_rules=RULES,
    sectors={'all': '전체 연결', 'consultation': '공공요금·수수료', 'display': '가격표시',
             'supply': '농수산물·수급', 'stabilization': '가격안정·집행'},
    keywords=KEYWORDS,
    default=PRICE,
    default_laws={'all': PRICE, 'consultation': PRICE, 'display': PRICE,
                  'supply': AGRI, 'stabilization': PRICE},
    default_refs={'all': '제4조', 'consultation': '제4조', 'display': '제3조',
                  'supply': '제15조', 'stabilization': '제2조'},
    purpose='공공요금·수수료 협의, 가격표시와 농수산물 수급의 명시적 인용 근거를 함께 읽습니다.',
    limitations=[
        '물가안정법과 선정한 가격표시·공공요금·수수료 기준, 농수산물 수급 법률군입니다. 물가 관련 모든 법령과 전기·가스·교통·상하수도 요금 규정을 수집한 것은 아닙니다.',
        '물가안정법 제4조의 다른 법률이라는 표현만으로 전체 요금 법령을 연결하지 않습니다. 법령명이 확인되는 명시적 인용만 분석합니다.',
        '공공요금 산정기준의 로마숫자·숫자 문단은 조문과 구분해 표시합니다. 가항·전항·다른 문단 참조의 적용 범위, 원가 산식·요금 적정성은 자동 판정하지 않습니다.',
        '별표·서식은 관련 조문과 공식 원본 링크를 표시하되 이 분야의 표 본문은 미분석입니다. 가격표시 품목·단위와 수수료 목록은 공식 원본을 확인하세요.',
        '관세법·소비자기본법·정보공개법은 명시적 연결을 읽기 위한 공통 참조 법률입니다. 통관·소비자보호·정보공개 전반의 별도 수집 범위를 의미하지 않습니다.',
        '개별 요금 조정·수수료 협의 대상 여부, 매점매석 위법성, 공급량·가격 전망은 자동 판단하지 않습니다. 연도별 긴급 고시·기관 내부 자료와 실제 원가 자료는 미수집입니다.',
        '2007년 수수료 협의대상 및 방법 고시는 API에서 연혁 자료로만 확인되어 현행 지도에서 제외했습니다. 공식 연혁 링크는 참고용이며 현재 협의 대상·절차라고 단정하지 않습니다.',
    ],
    companion_sources=[
        {'title': '국가법령정보센터 · 물가안정에 관한 법률',
         'url': 'https://www.law.go.kr/법령/물가안정에관한법률'},
        {'title': '공공요금 산정기준 · 공식 원문',
         'url': 'https://www.law.go.kr/admRulInfoP.do?admRulSeq=2100000272762'},
        {'title': '2007년 수수료 협의대상 및 방법 · API 연혁 자료 / 현행 지도 제외',
         'url': 'https://www.law.go.kr/LSW/admRulLsInfoP.do?admRulSeq=2000000055890'},
    ],
    case_expectations=CASE_EXPECTATIONS,
    cases=(
        (PRICE, '4', '공공요금 협의와 요금 산정원칙은 어떻게 연결되나?',
         '물가안정법 제4조를 인용하는 시행령 제6조의 총괄원가·산정기간·개별 산정기준을 함께 읽습니다. 요금 적정성과 개별 협의 대상 여부는 판정하지 않습니다.'),
        (PRICE, '3', '가격표시의 법률 근거와 세부 요령은 어떻게 연결되나?',
         '가격표시제 실시요령의 명시적 인용에서 물가안정법·시행령과 소비자기본법을 함께 읽습니다.'),
        (AGRI, '15', '농산물 수입물량 조절과 할당관세 근거는 어디서 이어지나?',
         '농수산물유통안정법 제15조제5항에서 관세법 제71조와 심의 근거를 확인합니다. 품목별 관세율·수입 가능 여부는 판정하지 않습니다.'),
    ),
)
