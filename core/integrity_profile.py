"""Selected ACRC laws. Topics aid navigation and never decide applicability."""
from core.fsc_collection import norm

ANTICORRUPTION = '부패방지 및 국민권익위원회의 설치와 운영에 관한 법률'
REPORT = '공익신고자 보호법'
GRAFT = '부정청탁 및 금품등 수수의 금지에 관한 법률'
CONFLICT = '공직자의 이해충돌 방지법'
REFUND = '공공재정 부정청구 금지 및 부정이익 환수 등에 관한 법률'
BASES = (ANTICORRUPTION, REPORT, GRAFT, CONFLICT, REFUND)
CODES = ('공무원 행동강령', '지방의회의원 행동강령')
STATUTES = tuple(name + suffix for name in BASES for suffix in ('', ' 시행령')) + CODES
RULES = ()
KEYWORDS = {
    'report': ('신고', '보호조치', '불이익조치', '보상', '포상', '구조금'),
    'conduct': ('부정청탁', '금품', '외부강의', '행동강령'),
    'conflict': ('이해충돌', '사적이해관계', '수의계약', '회피'),
    'refund': ('부정청구', '부정이익', '환수', '제재부가금'),
    'grievance': ('고충민원', '시정권고', '시정의 권고', '의견표명', '의견의 표명'),
}


def document_authorities(name, provider):
    return frozenset(('국민권익위원회',)) if provider == 'eflaw' and norm(name) in {norm(n) for n in STATUTES} else frozenset()


def selected(name, authority, provider):
    from core.procurement_collection import authorities
    expected = document_authorities(name, provider)
    return bool(expected and authorities(authority) == expected)


def document_tags(name):
    n = norm(name)
    for base, topic in ((REPORT, 'report'), (GRAFT, 'conduct'), (CONFLICT, 'conflict'), (REFUND, 'refund')):
        if n in {norm(base), norm(base + ' 시행령')}:
            return [topic]
    if n in {norm(c) for c in CODES}:
        return ['conduct']
    return ['report', 'grievance'] if n in {norm(ANTICORRUPTION), norm(ANTICORRUPTION + ' 시행령')} else []


def article_tags(name, article):
    value = norm(article.get('title', '') + ' ' + article.get('text', ''))
    # The comprehensive ACRC Act is tagged at article level so grievance and
    # reporting tabs do not both acquire its entire text.
    result = [] if norm(name).startswith(norm(ANTICORRUPTION)) else document_tags(name)
    for topic, words in KEYWORDS.items():
        if topic not in result and any(norm(word) in value for word in words):
            result.append(topic)
    return result


# Expected official-source chains were checked before collecting this corpus.
CASE_EXPECTATIONS = {
    (GRAFT, '15'): (dict(source_law=GRAFT, source_jo='15', target_law=REPORT, target_jo='2', quote_contains='제2조제6호'),),
    (GRAFT, '8'): (dict(source_law=GRAFT + ' 시행령', source_jo='17', target_law=GRAFT, target_jo='8', quote_contains='법 제8조제3항제2호'),),
    (CONFLICT, '12'): (dict(source_law=CONFLICT + ' 시행령', source_jo='14', target_law=CONFLICT, target_jo='12', quote_contains='법 제12조제1항'),),
    (REFUND, '23'): (dict(source_law=REFUND, source_jo='23', target_law=ANTICORRUPTION, target_jo='69', quote_contains='제69조'),),
    (ANTICORRUPTION, '46'): (dict(source_law=ANTICORRUPTION + ' 시행령', source_jo='48', target_law=ANTICORRUPTION, target_jo='46', quote_contains='법 제46조'),),
}

PROFILE = dict(
    title='청렴·권익', authorities=('국민권익위원회',),
    statutes=STATUTES, required=STATUTES, law_queries=BASES + CODES,
    rules=RULES, required_rules=RULES, rule_queries=RULES,
    sectors={'all': '전체 연결', 'conduct': '청탁·금품·행동강령', 'conflict': '이해충돌·계약',
             'report': '신고·보호·보상', 'refund': '공공재정 환수', 'grievance': '고충민원'},
    keywords=KEYWORDS, default=GRAFT,
    default_laws={'all': GRAFT, 'conduct': GRAFT, 'conflict': CONFLICT, 'report': GRAFT,
                  'refund': REFUND, 'grievance': ANTICORRUPTION},
    default_refs={'all': '제15조', 'conduct': '제8조', 'conflict': '제12조', 'report': '제15조',
                  'refund': '제23조', 'grievance': '제46조'},
    purpose='청탁금지·이해충돌·행동강령, 신고자 보호·보상, 공공재정 환수와 고충민원의 법적 근거를 함께 읽습니다.',
    limitations=[
        '권익위 소관의 선정 법률 5개와 시행령 5개, 대통령령인 공무원·지방의회의원 행동강령 2개를 수집합니다. 권익위 전체 소관 법령을 망라한 것은 아닙니다.',
        '행정심판법 계열, 각 헌법기관의 시행규칙, 기관별 행동강령·내부 지침·질의회신·판례·실제 신고사건은 이번 범위에서 제외합니다.',
        '공익신고자 보호법 별표와 금품 가액표 등은 번호와 공식 원본만 연결합니다. 별표 내부 대상 법률을 모두 수집하거나 공익신고 해당 여부·허용 금액을 자동 판정하지 않습니다.',
        '신고 유형별 적용요건, 보호·보상 가능성, 수의계약 제한의 예외, 환수·제재 여부는 원문 확인이 필요합니다. 준용·치환 문구와 문맥 확인 후보를 법적 판단으로 바꾸지 않습니다.',
    ],
    companion_sources=[{'title': '국민권익위원회 · 소관 법령', 'url': 'https://www.acrc.go.kr/menu.es?mid=a10503010000'}],
    case_expectations=CASE_EXPECTATIONS,
    cases=(
        (GRAFT, '15', '청탁금지 신고자의 보호 근거는 어느 법률로 이어지나?', '공익신고자 보호법의 불이익조치 정의와 준용 조항, 부패방지권익위법의 보상 근거를 함께 읽습니다.'),
        (GRAFT, '8', '금품 수수 예외의 가액 기준은 어디에 있나?', '시행령 제17조와 별표 1 공식 원본으로 이어집니다. 허용 여부와 금액을 자동 판정하지 않습니다.'),
        (CONFLICT, '12', '이해충돌에 따른 수의계약 제한과 예외의 근거는?', '시행령 제14조가 인용하는 국가·지방계약 시행령의 근거를 확인합니다. 계약 가능 여부의 자동 판정은 아닙니다.'),
        (REFUND, '23', '공공재정 신고 포상·보상의 심의 근거는?', '부패방지권익위법 제69조의 보상심의위원회와 공익신고자 보호법의 인용을 함께 읽습니다.'),
        (ANTICORRUPTION, '46', '고충민원 시정권고는 어떤 절차로 이어지나?', '시행령 제48조의 권고·의견표명 방법을 확인합니다. 민원 접수나 처분 판단을 대신하지 않습니다.'),
    ),
)
