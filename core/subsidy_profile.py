"""Limited central/local subsidy scope; exact names and current authorities.

Navigation topics never establish a legal relation or determine grant eligibility.
There is no generated 시행규칙 for the central Subsidy Act or Public Funds Act.
"""
from core.fsc_collection import norm

NATIONAL = '보조금 관리에 관한 법률'
LOCAL = '지방자치단체 보조금 관리에 관한 법률'
REFUND = '공공재정 부정청구 금지 및 부정이익 환수 등에 관한 법률'

FAMILIES = {
    NATIONAL: (NATIONAL, NATIONAL+' 시행령'),
    LOCAL: (LOCAL, LOCAL+' 시행령', LOCAL+' 시행규칙'),
    REFUND: (REFUND, REFUND+' 시행령'),
}
STATUTES = tuple(name for family in FAMILIES.values() for name in family)
CENTRAL_RULES = (
    '국고보조금 통합관리지침',
    '보조사업 실적보고서 및 정산보고서 작성지침',
    '보조사업 정산보고서 검증지침',
    '보조사업자 회계감사 세부기준',
    '보조사업자 정보공시 세부기준',
)
LOCAL_RULE = '지방보조금 관리기준'
REFUND_RULE = '공공재정지급금의 범위에 관한 규정'
RULES = CENTRAL_RULES+(LOCAL_RULE, REFUND_RULE)

# Old promulgation names/numbers do not replace current managing authority.
# Each document has one explicit authority, not a union-wide allow list.
DOCUMENT_AUTHORITIES = {
    norm(name): frozenset((authority,))
    for names, authority in (
        (FAMILIES[NATIONAL]+CENTRAL_RULES, '기획예산처'),
        (FAMILIES[LOCAL]+(LOCAL_RULE,), '행정안전부'),
        (FAMILIES[REFUND]+(REFUND_RULE,), '국민권익위원회'),
    )
    for name in names
}
_DOCUMENT_TOPICS = {
    norm(name): topic
    for names, topic in (
        (FAMILIES[NATIONAL]+CENTRAL_RULES, 'national'),
        (FAMILIES[LOCAL]+(LOCAL_RULE,), 'local'),
        (FAMILIES[REFUND]+(REFUND_RULE,), 'control'),
    )
    for name in names
}
KEYWORDS = {
    'settlement': ('실적보고', '정산', '검증', '회계감사', '감사보고', '정보공시'),
    'control': ('부정청구', '부정수급', '환수', '제재부가금', '반환', '수행배제',
                '수행 배제', '교부결정의 취소', '중요재산', '처분제한', '처분 제한'),
}


def document_authorities(name, provider):
    """Return the exact declared authority set, or empty for an unknown owner."""
    names = STATUTES if provider == 'eflaw' else RULES if provider == 'admrul' else ()
    if norm(name) not in {norm(value) for value in names}:
        return frozenset()
    return DOCUMENT_AUTHORITIES.get(norm(name), frozenset())


def selected(name, authority, provider):
    from core.procurement_collection import authorities
    expected = document_authorities(name, provider)
    actual = authorities(authority)
    return bool(expected and actual and actual == expected)


def document_tags(name):
    topic = _DOCUMENT_TOPICS.get(norm(name))
    return [topic] if topic else []


def article_tags(name, article):
    result = document_tags(name)
    value = norm(article.get('title', '')+' '+article.get('text', ''))
    for topic, words in KEYWORDS.items():
        if topic not in result and any(norm(word) in value for word in words):
            result.append(topic)
    return result


CASE_EXPECTATIONS={
    (NATIONAL,'27'):({'source_law':NATIONAL+' 시행령','source_jo':'12의2','target_law':NATIONAL,'target_jo':'27','quote_contains':'법 제27조제2항'},),
    (NATIONAL,'33의2'):({'source_law':NATIONAL+' 시행령','source_jo':'14의2','target_law':NATIONAL,'target_jo':'33의2','quote_contains':'법 제33조의2제1항'},),
    (LOCAL,'17'):({'source_law':LOCAL+' 시행규칙','source_jo':'3','target_law':LOCAL,'target_jo':'17','quote_contains':'법 제17조제1항'},),
    (NATIONAL,'26의10'):({'source_law':NATIONAL+' 시행령','source_jo':'11의2','target_law':NATIONAL,'target_jo':'26의10','quote_contains':'법 제26조의10제1항'},),
    (REFUND,'8'):({'source_law':REFUND+' 시행령','source_jo':'3','target_law':REFUND,'target_jo':'8','quote_contains':'법 제8조제1항'},),
}


PROFILE = dict(
    title='보조금·지원사업',
    authorities=('기획예산처', '행정안전부', '국민권익위원회'),
    statutes=STATUTES, required=STATUTES,
    law_queries=(NATIONAL, LOCAL, REFUND),
    rules=RULES, required_rules=RULES,
    rule_queries=RULES,
    sectors={'all': '전체 연결', 'national': '국고보조금', 'local': '지방보조금',
             'settlement': '정산·검증·공시', 'control': '환수·제재·재산관리'},
    keywords=KEYWORDS,
    default=NATIONAL,
    default_laws={'all': NATIONAL, 'national': NATIONAL, 'local': LOCAL,
                  'settlement': NATIONAL, 'control': REFUND},
    default_refs={'all': '제27조', 'national': '제27조', 'local': '제17조',
                  'settlement': '제27조', 'control': '제8조'},
    purpose='국고·지방 보조금의 교부·정산·공시와 환수·제재의 법률·하위규정 인용을 함께 읽습니다.',
    limitations=[
        '기획예산처·행정안전부·국민권익위원회의 선정 공통 법령·규정입니다. 재정경제부 단독 소관이 아니며 모든 지원사업을 수집한 것은 아닙니다.',
        '개별 부처 사업지침·모집공고·교부조건·사업협약과 지역별 지방보조금 조례는 미수집입니다. 특정 사업의 지원대상·지원금액·지출 가능 여부는 판단하지 않습니다.',
        '법률·시행령·시행규칙·조문 형식 지침의 명시적 인용만 연결합니다. 법령과 지침의 규정이 비슷하다는 이유로 자동 연결하지 않습니다.',
        '별표·서식은 번호와 공식 원본을 연결합니다. 비목표·부과율표·보고서 칸 내부의 문구와 계산식은 미분석이며, 정산·검증·감사를 수행하는 기능은 아닙니다.',
        '공공재정환수법과 다른 법률의 적용관계 및 제재 중복 여부는 원문을 확인해야 합니다. 환수·제재부가금의 부과 필요성이나 부정수급 여부를 자동 판정하지 않습니다.',
    ],
    companion_sources=[
        {'title': '국가법령정보센터 · 국고보조금 통합관리지침',
         'url': 'https://www.law.go.kr/행정규칙/국고보조금통합관리지침'},
        {'title': '국가법령정보센터 · 지방보조금 관리기준',
         'url': 'https://www.law.go.kr/행정규칙/지방보조금관리기준'},
    ],
    case_expectations=CASE_EXPECTATIONS,
    cases=(
        (NATIONAL, '27', '국고보조사업 정산·검증은 어떤 근거에서 내려오나?',
         '법률과 시행령 제12조의2, 실적·정산 작성지침과 검증지침의 명시적 인용을 함께 읽습니다.'),
        (NATIONAL, '33의2', '부정수급 제재부가금의 기준은 어느 규정·별표에 있나?',
         '시행령 제14조의2와 별표 8의 공식 원본을 확인합니다. 부과 사유와 부과액은 자동 판정하지 않습니다.'),
        (LOCAL, '17', '지방보조사업 실적보고·정산 서식은 어디서 확인하나?',
         '시행규칙 제3조와 별지 제2·3호서식, 관리기준의 실제 인용을 확인합니다.'),
        (NATIONAL, '26의10', '보조사업 정보공시의 법률·시행령·세부기준은?',
         '시행령 제11조의2와 정보공시 세부기준의 근거를 함께 읽습니다.'),
        (REFUND, '8', '공공재정 부정이익 환수금액의 근거는?',
         '환수 조문과 시행령 제3조의 산정 근거를 읽습니다. 미수집 외부 인용은 구분해 표시합니다.'),
    ),
)
