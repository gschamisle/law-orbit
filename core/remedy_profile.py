"""First-stage administrative remedies: selected procedures, not all tribunals."""
from core.fsc_collection import norm

APPEAL = '행정심판법'
LITIGATION = '행정소송법'
TAX = '국세기본법'
CUSTOMS = '관세법'
LOCAL = '지방세기본법'
LABOR = '근로기준법'
COMMISSION = '노동위원회법'
HEALTH = '국민건강보험법'
MEDICAL_AID = '의료급여법'
BASIC = '행정기본법'
INFORMATION = '공공기관의 정보공개에 관한 법률'
COMPETITION = '독점규제 및 공정거래에 관한 법률'
GREENBELT = '개발제한구역의 지정 및 관리에 관한 특별조치법'
REGIONAL = '지역 개발 및 지원에 관한 법률'
JEJU = '제주특별자치도 설치 및 국제자유도시 조성을 위한 특별법'
OWNERS = {
    APPEAL: '국민권익위원회', APPEAL+' 시행령': '국민권익위원회',
    APPEAL+' 시행규칙': '국민권익위원회', LITIGATION: '법무부',
    TAX: '재정경제부', CUSTOMS: '재정경제부', LOCAL: '행정안전부',
    LABOR: '고용노동부', COMMISSION: '고용노동부',
    HEALTH: '보건복지부', MEDICAL_AID: '보건복지부',
    BASIC: '법제처', BASIC+' 시행령': '법제처', INFORMATION: '행정안전부',
    COMPETITION: '공정거래위원회', GREENBELT: '국토교통부', REGIONAL: '국토교통부',
    JEJU: '국토교통부,행정안전부',
}
STATUTES = tuple(OWNERS)
PEERS = ('tax', 'customs', 'local_tax', 'labor', 'medical', 'privacy', 'public_institutions', 'ftc', 'housing', 'state_property')
SECTORS = {'all': '전체 연결', 'general': '이의신청·심판·소송', 'tax': '국세 불복',
           'customs': '관세 불복', 'local_tax': '지방세 불복',
           'labor': '노동위원회 구제', 'medical': '건강보험·의료급여',
           'information': '정보공개 불복', 'competition': '공정거래 불복', 'jurisdiction': '개발·지역 관할 특례'}
DOC_TAGS = {APPEAL: 'general', APPEAL+' 시행령': 'general', APPEAL+' 시행규칙': 'general',
            LITIGATION: 'general', TAX: 'tax', CUSTOMS: 'customs', LOCAL: 'local_tax',
            LABOR: 'labor', COMMISSION: 'labor', HEALTH: 'medical', MEDICAL_AID: 'medical',
            BASIC: 'general', BASIC+' 시행령': 'general', INFORMATION: 'information',
            COMPETITION: 'competition', GREENBELT: 'jurisdiction', REGIONAL: 'jurisdiction', JEJU: 'jurisdiction'}
KEYWORDS = {'general': ('행정심판', '행정소송'), 'tax': ('심사청구', '심판청구'),
            'customs': ('관세심사',), 'local_tax': ('지방세심의',),
            'labor': ('구제명령', '재심판정'), 'medical': ('건강보험분쟁조정',)}


def selected(name, authority, provider):
    from core.procurement_collection import authorities
    expected = next((owner for law, owner in OWNERS.items() if norm(law) == norm(name)), None)
    return provider == 'eflaw' and expected is not None and authorities(authority) == authorities(expected)


def document_tags(name):
    return [tag for law, tag in DOC_TAGS.items() if norm(law) == norm(name)]


def article_tags(name, article):
    # Full statutes remain readable; keywords do not invent citation edges.
    return document_tags(name)


# Exact contexts checked against official bodies on 2026-10-13. The review flag
# stays visible: these prove a citation exists, not that the target rule applies.
REVIEWED_CONTEXTS = {
    INFORMATION: '① 청구인이 정보공개와 관련한 공공기관의 결정에 대하여 불복이 있거나 정보공개 청구 후 20일이 경과하도록 정보공개 결정이 없는 때에는 「행정심판법」에서 정하는 바에 따라 행정심판을 청구할 수 있다. 이 경우 국가기관 및 지방자치단체 외의 공공기관의 결정에 대한 감독행정기관은 관계 중앙행정기관의 장 또는 지방자치단체의 장으로 한다.',
    GREENBELT: '② 제1항에 따른 이의신청에 대하여는 「행정심판법」 제6조에도 불구하고 중앙토지수용위원회가 심리ㆍ의결하여 재결한다.',
    JEJU: '제350조(보훈사무의 행정심판에 관한 특례) 「행정심판법」 제6조제3항에도 불구하고 제341조부터 제349조까지의 보훈사무에 관한 제주자치도 소속 행정청의 처분 또는 부작위에 대한 행정심판의 청구는 같은 법 제6조제2항에 따른 중앙행정심판위원회에서 심리ㆍ재결한다.',
}
CASE_EXPECTATIONS = {
    (BASIC, '36'): (dict(source_law=BASIC, source_jo='36', target_law=APPEAL, target_jo='3', quote_contains='제3조'),),
    (INFORMATION, '19'): (dict(source_law=INFORMATION, source_jo='19', target_law=APPEAL, target_kind='law', quote_contains='행정심판법', reviewed_context=REVIEWED_CONTEXTS[INFORMATION]),),
    (COMPETITION, '100'): (dict(source_law=COMPETITION, source_jo='100', target_law=COMPETITION, target_jo='99', quote_contains='제99조'),),
    (GREENBELT, '27'): (dict(source_law=GREENBELT, source_jo='27', target_law=APPEAL, target_jo='6', quote_contains='제6조', reviewed_context=REVIEWED_CONTEXTS[GREENBELT]),),
    (REGIONAL, '78'): (dict(source_law=REGIONAL, source_jo='78', target_law=APPEAL, target_kind='law', quote_contains='행정심판법'),),
    (JEJU, '350'): (dict(source_law=JEJU, source_jo='350', target_law=APPEAL, target_jo='6', quote_contains='제6조제3항', reviewed_context=REVIEWED_CONTEXTS[JEJU]),),
    (TAX, '56'): (dict(source_law=TAX, source_jo='56', target_law=APPEAL, target_jo='15', quote_contains='제15조'),),
    (CUSTOMS, '120'): (dict(source_law=CUSTOMS, source_jo='120', target_law=APPEAL, target_jo='15', quote_contains='제15조'),),
    (LOCAL, '98'): (dict(source_law=LOCAL, source_jo='98', target_law=TAX, target_jo='56', quote_contains='제56조제1항'),),
    (LABOR, '31'): (dict(source_law=LABOR, source_jo='31', target_law=LITIGATION, target_kind='law', quote_contains='행정소송법'),),
    (COMMISSION, '15의3'): (dict(source_law=COMMISSION, source_jo='15의3', target_law=APPEAL, target_jo='18', quote_contains='제18조'),),
    (MEDICAL_AID, '30의2'): (dict(source_law=MEDICAL_AID, source_jo='30의2', target_law=HEALTH, target_jo='89', quote_contains='제89조'),),
}

PROFILE = dict(
    title='행정구제', authorities=tuple(sorted({v for owner in OWNERS.values() for v in owner.split(',')})),
    statutes=STATUTES, required=STATUTES,
    law_queries=(APPEAL, LITIGATION, TAX, CUSTOMS, LOCAL, LABOR, COMMISSION, HEALTH, MEDICAL_AID,
                 BASIC, INFORMATION, COMPETITION, GREENBELT, REGIONAL, JEJU),
    rules=(), required_rules=(), rule_queries=(), sectors=SECTORS, keywords=KEYWORDS,
    default=APPEAL,
    default_laws={'all': APPEAL, 'general': BASIC, 'tax': TAX, 'customs': CUSTOMS,
                  'local_tax': LOCAL, 'labor': COMMISSION, 'medical': MEDICAL_AID,
                  'information': INFORMATION, 'competition': COMPETITION, 'jurisdiction': GREENBELT},
    default_refs={'all': '제4조', 'general': '제36조', 'tax': '제56조', 'customs': '제120조',
                  'local_tax': '제98조', 'labor': '제15조의3', 'medical': '제30조의2',
                  'information': '제19조', 'competition': '제100조', 'jurisdiction': '제27조'},
    purpose='이의신청·행정심판·행정소송의 관계와 분야별 불복 근거, 개발·지역의 관할 특례를 함께 읽습니다.',
    entry_guide=dict(first=True, title='어떤 불복절차를 확인하나요?',
        subtitle='헌법 제107조제3항의 행정심판 원칙에서 출발해, 업무별 불복 근거와 절차 특례를 읽습니다.',
        note='준용·적용 제외·별도 절차를 구분한 원문 안내입니다. 개인 사건의 관할·청구기한·승소 가능성을 판정하지 않습니다.'),
    limitations=[
        '선정한 18개 법령의 본칙을 수록합니다. 일반 불복절차와 기존 분야의 정보공개·공정거래·개발·지역 특례를 포함하며, 특별행정심판기관 전체나 모든 불복절차의 목록은 아닙니다.',
        '국세·관세·지방세의 본칙, 근로기준법·노동위원회법, 국민건강보험법·의료급여법을 수집합니다. 각 개별법의 하위 규정은 기존 분야에서 확보한 범위의 인용을 연결합니다.',
        '특허·소청·산재·고용보험·장기요양 등의 확대 수집, 판례·재결례, 실제 사건·청구서 작성은 이번 범위에서 제외합니다.',
        '절차 안내는 확인한 조항의 원문에 붙인 편집 설명입니다. 적용 제외와 일부 준용이 같은 항에 함께 있을 수 있으며, 인용선 자체가 법적 적용관계를 판정하지 않습니다.',
        '이의신청이라는 명칭만으로 특별행정심판이나 소송 전 필수 절차로 분류하지 않습니다. 헌법의 출발점 안내는 편집 설명이며 자동 인용선이 아닙니다.',
        '기존 분야와 수집일·시행 판본이 다를 수 있습니다. 각 본문의 시행일을 표시하며, 현재 사건의 기한·전치요건·관할·경과규정은 공식 원문을 확인해야 합니다.',
    ],
    companion_sources=[{'title': '헌법 제107조 · 행정심판의 출발점', 'url': 'https://www.law.go.kr/법령/대한민국헌법/제107조'},
                       {'title': '온라인행정심판 · 일반·특별행정심판 안내', 'url': 'https://simpan.go.kr/eas/aa/ac/100/admjdgmTrgt.do?cmnMenuCd=E03020100'}],
    case_expectations=CASE_EXPECTATIONS,
    cases=(
        (BASIC, '36', '이의신청을 하면 행정심판을 따로 못 하나?', '이의신청과 별개로 심판·소송을 제기할 수 있는 규정과 적용 제외를 함께 확인합니다.'),
        (INFORMATION, '19', '정보공개 이의신청을 꼭 먼저 거쳐야 하나?', '이의신청 없이 행정심판을 청구할 수 있다는 원문과 행정심판법 참조를 읽습니다.'),
        (COMPETITION, '100', '공정거래 처분의 불복 소송은 어디로 이어지나?', '소 제기 규정과 서울고등법원 전속관할을 확인하고 제96조의 이의신청과 구별합니다.'),
        (GREENBELT, '27', '개발제한구역 처분은 누가 심판하나?', '행정심판법 제6조와 다른 중앙토지수용위원회 관할 특례를 읽습니다.'),
        (REGIONAL, '78', '지역개발 사업의 심판 관할은 어떻게 달라지나?', '사업시행자와 지정권자에 따라 달라지는 조문상의 조건을 함께 읽습니다.'),
        (JEJU, '350', '제주 보훈사무는 어느 행정심판위원회가 맡나?', '제341조부터 제349조까지의 보훈사무에 한정된 행정심판법 관할 특례입니다.'),
        (TAX, '56', '국세 불복에는 행정심판법이 어떻게 적용되나?', '적용 제외와 일부 조문 준용, 행정소송 전 심사·심판청구 규정을 함께 확인합니다.'),
        (CUSTOMS, '120', '관세 불복과 일반 행정심판의 관계는?', '관세법의 적용 제외·준용 문구와 행정소송법 특례를 확인합니다.'),
        (LOCAL, '98', '지방세 불복은 국세 절차와 어디서 연결되나?', '이의신청과 심판청구를 구분하고 국세기본법 제56조제1항 준용을 읽습니다.'),
        (COMMISSION, '15의3', '노동위원회도 행정심판법을 준용하나?', '선정대표자·지위 승계·대리인 선임에 한정된 준용을 확인합니다.'),
        (LABOR, '31', '부당해고 구제명령에 불복하면 어떤 절차인가?', '노동위원회 재심과 행정소송의 근거입니다. 일반 행정심판 청구로 바꾸어 안내하지 않습니다.'),
        (MEDICAL_AID, '30의2', '의료급여의 심판청구는 건강보험과 어떻게 연결되나?', '급여비용심사기관의 이의신청 결정에 관한 규정과 건강보험분쟁조정위원회 근거를 읽습니다.'),
    ),
)
