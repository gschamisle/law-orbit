"""Bounded privacy/public-data scope, verified against official current titles.

Navigation tags are not legal relations. Every selected document must pass its
own issuer policy; the union of the three authorities is never a selector.
"""
from __future__ import annotations

from core.fsc_collection import norm
from core.procurement_collection import authorities

PRIVACY = '개인정보 보호법'
PUBLIC_DATA = '공공데이터의 제공 및 이용 활성화에 관한 법률'
DISCLOSURE = '공공기관의 정보공개에 관한 법률'
AI_ADMIN = '인공지능 및 데이터 기반 행정 활성화에 관한 법률'
CREDIT = '신용정보의 이용 및 보호에 관한 법률'
SAFETY = '개인정보의 안전성 확보조치 기준'
METHODS = '개인정보 처리 방법에 관한 고시'
STANDARD = '표준 개인정보 보호지침'
VERIFIED_AS_OF = '20261004'

# The former 개인정보 보호법 시행규칙 was abolished on 2021-01-15.
# AI_ADMIN does have a current 시행규칙; do not infer either from convention.
FAMILIES = {
    PRIVACY: (PRIVACY, PRIVACY + ' 시행령'),
    PUBLIC_DATA: tuple(PUBLIC_DATA + s for s in ('', ' 시행령', ' 시행규칙')),
    DISCLOSURE: tuple(DISCLOSURE + s for s in ('', ' 시행령', ' 시행규칙')),
    AI_ADMIN: tuple(AI_ADMIN + s for s in ('', ' 시행령', ' 시행규칙')),
    CREDIT: tuple(CREDIT + s for s in ('', ' 시행령', ' 시행규칙')),
}
STATUTES = tuple(doc for docs in FAMILIES.values() for doc in docs)
RULES = (SAFETY, METHODS, STANDARD)
_OWNERS = {
    PRIVACY: '개인정보보호위원회',
    PUBLIC_DATA: '행정안전부',
    DISCLOSURE: '행정안전부',
    AI_ADMIN: '행정안전부',
    CREDIT: '금융위원회',
}
_DOCUMENT_OWNERS = {
    ('eflaw', norm(doc)): owner
    for base, owner in _OWNERS.items() for doc in FAMILIES[base]
}
_DOCUMENT_OWNERS.update({('admrul', norm(doc)): '개인정보보호위원회' for doc in RULES})


def authority_policy(name, provider):
    """Return required/allowed issuers for exactly one declared document.

    No joint ownership has been assumed. A newly observed joint issuer must be
    verified and explicitly added to this document's policy before collection.
    """
    owner = _DOCUMENT_OWNERS.get((provider, norm(name)))
    if owner is None:
        return None
    return {'required': frozenset((owner,)), 'allowed': frozenset((owner,))}


def selected(name, authority, provider):
    policy = authority_policy(name, provider)
    if policy is None or not isinstance(authority, str):
        return False
    actual = authorities(authority)
    return bool(actual and policy['required'].issubset(actual)
                and actual.issubset(policy['allowed']))


KEYWORDS = {
    'processing': ('개인정보', '수집', '동의', '처리', '제공', '가명', '민감정보', '고유식별'),
    'safety': ('안전성', '안전조치', '접근권한', '암호화', '접속기록', '유출', '영향평가'),
    'public_data': ('공공데이터', '정보공개', '비공개', '제공대상', '제공거부', '저작권'),
    'administration': ('인공지능', '데이터기반행정', '데이터 기반 행정', '데이터의 제공',
                       '공동활용', '분석', '메타데이터'),
    'credit': ('신용정보', '본인신용정보관리', '신용정보주체', '금융거래'),
}
_BASE_SECTORS = {PRIVACY: 'processing', PUBLIC_DATA: 'public_data',
                 DISCLOSURE: 'public_data', AI_ADMIN: 'administration', CREDIT: 'credit'}
_DOCUMENT_SECTORS = {norm(doc): sector for base, sector in _BASE_SECTORS.items()
                     for doc in FAMILIES[base]}
_DOCUMENT_SECTORS.update({norm(SAFETY): 'safety', norm(METHODS): 'processing',
                          norm(STANDARD): 'processing'})


def document_tags(name):
    sector = _DOCUMENT_SECTORS.get(norm(name))
    return [sector] if sector else []


def article_tags(name, article):
    """Keep document axis and add matching topic tags without making edges."""
    result = document_tags(name)
    value = norm(article.get('title', '') + ' ' + article.get('text', ''))
    for sector, words in KEYWORDS.items():
        if sector not in result and any(norm(word) in value for word in words):
            result.append(sector)
    return result


# Official quoted interactions for the collection acceptance check. These are
# not inserted graph edges: the real collected body/parser must demonstrate them.
CASE_PROOFS = (
    {'source_law': CREDIT, 'source_jo': '15', 'target_law': PRIVACY,
     'target_ref': '제15조제1항제2호', 'target_kind': 'article',
     'quote_contains': '「개인정보 보호법」 제15조제1항제2호부터 제7호까지',
     'url': 'https://www.law.go.kr/LSW/lsSideInfoP.do?docCls=jo&joBrNo=00&joNo=0015&lsiSeq=283841&urlMode=lsScJoRltInfoR'},
    {'source_law': PUBLIC_DATA, 'source_jo': '17', 'target_law': DISCLOSURE,
     'target_ref': '제9조', 'target_kind': 'article',
     'quote_contains': '「공공기관의 정보공개에 관한 법률」 제9조',
     'url': 'https://law.go.kr/LSW/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1020989561'},
    {'source_law': AI_ADMIN, 'source_jo': '5', 'target_law': PUBLIC_DATA,
     'target_ref': '제5조', 'target_kind': 'article',
     'quote_contains': '「공공데이터의 제공 및 이용 활성화에 관한 법률」 제5조',
     'url': 'https://www.law.go.kr/lsInfoP.do?lsiSeq=283735'},
)
CASE_EXPECTATIONS = {
    (PRIVACY, '15'): ({**CASE_PROOFS[0], 'target_jo': '15'},),
    (PUBLIC_DATA, '17'): ({**CASE_PROOFS[1], 'target_jo': '9'},),
    (AI_ADMIN, '5'): ({**CASE_PROOFS[2], 'target_jo': '5'},),
}

PROFILE = dict(
    title='개인정보·공공데이터',
    authorities=('개인정보보호위원회', '행정안전부', '금융위원회'),
    statutes=STATUTES, required=STATUTES,
    law_queries=(PRIVACY, PUBLIC_DATA, DISCLOSURE, AI_ADMIN, CREDIT),
    rule_queries=RULES, rules=RULES, required_rules=RULES,
    sectors={'all': '전체 연결', 'processing': '수집·이용·제공', 'safety': '보호·안전조치',
             'public_data': '공공데이터·정보공개', 'administration': '공공 AI·데이터 행정',
             'credit': '개인신용정보'},
    keywords=KEYWORDS, default=PUBLIC_DATA,
    default_laws={'all': PUBLIC_DATA, 'processing': PRIVACY, 'safety': PRIVACY,
                  'public_data': PUBLIC_DATA, 'administration': AI_ADMIN, 'credit': CREDIT},
    default_refs={'all': '제17조', 'processing': '제15조', 'safety': '제29조',
                  'public_data': '제17조', 'administration': '제5조', 'credit': '제15조'},
    purpose='공공데이터 제공·정보공개·공공 AI 활용의 근거를 따라가며, 개인정보·신용정보 규정의 직접 인용과 역인용을 함께 확인합니다.',
    entry_guide=dict(
        title='제공·공개·활용의 근거 찾기',
        subtitle='공공데이터 업무에서 함께 살펴볼 법의 근거를 찾습니다.',
        note='업무 질문을 고르면 출발 조문과 그 조문이 인용하거나 인용받는 근거를 함께 엽니다.',
        first=True,
    ),
    limitations=[
        '개인정보·공공데이터·정보공개·AI 데이터 행정과 신용정보의 선정 법령, 개인정보보호위원회 고시 3개의 범위입니다. 개인정보·디지털 분야 전체를 수집한 것은 아닙니다.',
        '개인정보 보호법 시행규칙은 2021년 폐지되어 현행 범위에 포함하지 않습니다. 해설서·가이드라인·기관별 개인정보 처리방침·내부규정은 법령과 구분하며 이번 조문 분석에 포함하지 않습니다.',
        '법률 전체를 참조하거나 다른 법률의 특별 규정을 요구하는 문구에 임의의 조문을 추가하지 않습니다. 수집 범위 밖 법령은 원문 인용과 공식 링크로 확인합니다.',
        '정보공개·개인정보 제공의 적법성, 동의 필요 여부, 가명처리의 충분성, 보안기준 충족 여부와 AI 영향평가 대상 여부를 자동 판정하지 않습니다.',
        '별표·서식은 관련 조문과 공식 원문 연결을 제공하되 표 안의 요건·문구는 이번 범위에서 분석하지 않습니다. 부칙·부분 시행일·시행예정 조문은 공식 판본과 참고자료를 함께 확인해야 합니다.',
        '인공지능 및 데이터 기반 행정 활성화에 관한 법률의 영향평가 관련 일부 조문과 시행령 제26조부터 제29조는 2027년 2월 28일 시행 예정입니다. 이를 현재 시행 중인 의무로 안내하지 않습니다.',
    ],
    companion_sources=[
        {'title': '보-편 · 개인정보 보호법 편히 읽기',
         'url': 'https://privacy-law-reader.vercel.app/', 'kind': 'reader',
         'description': '법률·시행령·고시를 함께 읽는 외부 참고 도구입니다.'},
        {'title': '개인정보보호위원회 · 공식 법령·지침 자료', 'url': 'https://www.pipc.go.kr/'},
        {'title': '공공데이터포털 · 공식 데이터 제공 절차', 'url': 'https://www.data.go.kr/'},
        {'title': '정보공개포털 · 공식 청구 절차', 'url': 'https://www.open.go.kr/'},
    ],
    case_expectations=CASE_EXPECTATIONS,
    cases=(
        (PUBLIC_DATA, '17', '공공데이터 제공에서 비공개 근거는 어느 법으로 이어지나?',
         '공공데이터법 제17조가 인용하는 정보공개법 제9조를 확인합니다. 공개 가능한지는 자동 판정하지 않습니다.'),
        (AI_ADMIN, '5', '공공 AI·데이터 행정의 심의 체계는 어느 법에 근거하나?',
         '공공데이터전략위원회를 규정한 공공데이터법 제5조로 이어집니다. AI 활용의 허용 여부는 판정하지 않습니다.'),
        (PRIVACY, '15', '개인정보 수집 근거를 개인신용정보는 어떻게 인용하나?',
         '개인정보 보호법 제15조에서 이 조문을 인용하는 신용정보법 제15조를 역인용으로 찾습니다. 동의 면제 여부는 판정하지 않습니다.'),
    ),
)
