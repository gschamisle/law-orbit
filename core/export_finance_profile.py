"""Declared institutional sources for export finance and KIC companion reading.

KIC is collected with the four founding laws, but displayed inside foreign exchange.
The export_finance bundle contains only EXIM, trade insurance and EDCF families.
"""
from core.fsc_collection import norm
from core.procurement_collection import authorities

EXIM = '한국수출입은행법'
KIC = '한국투자공사법'
INSURANCE = '무역보험법'
EDCF = '대외경제협력기금법'
EXPORT_FAMILIES = (EXIM, INSURANCE, EDCF)
COLLECTION_FAMILIES = (*EXPORT_FAMILIES, KIC)
SUFFIXES = ('', ' 시행령', ' 시행규칙')
STATUTES = tuple(base + suffix for base in COLLECTION_FAMILIES for suffix in SUFFIXES)
REQUIRED_EXPORT = tuple(base + suffix for base in EXPORT_FAMILIES for suffix in
                        (('', ' 시행령') if base == EXIM else SUFFIXES))
REQUIRED_ALL = (*REQUIRED_EXPORT, KIC, KIC + ' 시행령')

PROFILE = dict(
    title='수출·해외사업 금융',
    statutes=STATUTES,
    required=REQUIRED_EXPORT,
    law_queries=COLLECTION_FAMILIES,
    rule_queries=(), rules=(), required_rules=(),
    authorities=('재정경제부', '산업통상부'),
    sectors={'all': '전체 연결', 'export': '수출입 금융·보증', 'overseas': '해외사업·투자',
             'insurance': '무역보험·기금', 'development': '대외경제협력기금'},
    keywords={
        'export': ('수출', '수입', '대출', '보증', '자금', '신용'),
        'overseas': ('해외', '투자', '출자', '자원', '사업'),
        'insurance': ('보험', '보험료', '재보험', '보험금'),
        'development': ('개발도상', '대외경제협력기금', '기금관리', '수탁기관'),
    },
    default=EXIM,
    purpose='수출입 금융·보증, 해외사업 투자, 무역보험과 대외경제협력기금의 근거 조문을 업무별로 읽습니다.',
    limitations=[
        '한국수출입은행법·무역보험법·대외경제협력기금법과 실재 하위법령의 본칙을 수집했습니다. 모든 정책금융 법령·기관 내규를 수집한 것은 아닙니다.',
        '대출·보증과 보험, 개발협력기금은 서로 다른 제도입니다. 같은 기관이 취급하더라도 동일한 지원대상·심사절차로 보지 않습니다.',
        '상품별 지원요건·심사기준·보험약관·협정과 실제 거래조건은 미수집입니다. 금융지원 가능 여부를 자동 판정하지 않습니다.',
        '한국투자공사법과 시행령은 외환 분야의 위탁·운용 길잡이에서 별도로 읽습니다.',
    ],
    companion_sources=[
        {'title': '한국수출입은행 공식 안내', 'url': 'https://www.koreaexim.go.kr/'},
        {'title': '한국무역보험공사 공식 안내', 'url': 'https://www.ksure.or.kr/'},
        {'title': '대외경제협력기금 공식 안내', 'url': 'https://www.edcfkorea.go.kr/'},
    ],
    cases=(
        (EXIM, '18', '수출입·해외사업 금융의 업무 범위는?', '법률의 업무 범위와 시행령의 세부 규정을 함께 확인합니다.'),
        (INSURANCE, '31', '무역보험기금은 어떻게 조성하는가?', '기금 재원의 법률과 시행령상 추가 재원을 함께 확인합니다.'),
        (EDCF, '9', '기금 관리를 수출입은행에 맡기는 근거는?', '기금법의 관리·운용 근거와 시행령의 위탁 조문을 확인합니다.'),
    ),
)


def family(name):
    key = norm(name)
    return next((base for base in COLLECTION_FAMILIES
                 if key in {norm(base + suffix) for suffix in SUFFIXES}), '')


def selected(name, authority, provider):
    base = family(name)
    expected = {'산업통상부'} if base == INSURANCE else {'재정경제부'}
    return provider == 'eflaw' and bool(base) and authorities(authority) == expected


def document_tags(name):
    return {EXIM: ['export', 'overseas'], INSURANCE: ['insurance'],
            EDCF: ['development'], KIC: []}.get(family(name), [])


def article_tags(name, article):
    base = family(name)
    if base != EXIM:
        return document_tags(name)
    value = norm(article.get('title', '') + ' ' + article.get('text', ''))
    tags = [tag for tag in ('export', 'overseas')
            if any(norm(word) in value for word in PROFILE['keywords'][tag])]
    return tags or ['export', 'overseas']
