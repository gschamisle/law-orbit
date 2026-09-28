"""A curated starting corpus, not a claim to cover all constitutional relations."""
from core.fsc_collection import norm

CONSTITUTION='대한민국헌법'
AUTHORITIES={
    CONSTITUTION:(), '국회법':('국회',), '정부조직법':('행정안전부',),
    '법원조직법':('대법원',), '헌법재판소법':('헌법재판소',),
    '지방자치법':('행정안전부',), '공직선거법':('중앙선거관리위원회',),
    '국민투표법':('중앙선거관리위원회',), '국세기본법':('재정경제부',),
    '근로기준법':('고용노동부',), '노동조합 및 노동관계조정법':('고용노동부',),
    '교육기본법':('교육부',), '사회보장기본법':('보건복지부',),
    '환경정책기본법':('기후에너지환경부',),
    '독점규제 및 공정거래에 관한 법률':('공정거래위원회',),
}

PROFILE=dict(title='헌법',authorities=(),statutes=tuple(AUTHORITIES),required=tuple(AUTHORITIES),
    law_queries=tuple(AUTHORITIES),rule_queries=(),rules=(),required_rules=(),
    sectors={'all':'헌법과 선정 법률'},keywords={},default=CONSTITUTION,
    purpose='헌법의 조문을 읽고, 실제로 이를 인용하는 법률과 헌법의 원칙을 구체화하는 관련 법률을 구분해 살펴봅니다.',
    limitations=[
        '헌법과 선정한 기본 법률의 시작 목록입니다. 헌법 관련 법령 전체나 모든 역인용을 수집한 것은 아닙니다.',
        '지도와 인용 목록은 명시적 인용 근거를 표시합니다. 관련 법률 안내는 편집한 길잡이이며 인용선·인용 건수에 포함하지 않습니다.',
        '헌법의 추상적 원칙이나 법률로 정한다는 위임만으로 특정 법률과의 인용 관계를 자동 생성하지 않습니다.',
        '헌법재판소 결정례·판례와 학설은 미수집입니다. 위헌 여부·헌법상 의무 이행을 판단하는 도구가 아닙니다.'],
    companion_sources=[{'title':'대한민국헌법 공식 원문','url':'https://www.law.go.kr/법령/대한민국헌법'},
                       {'title':'헌법재판소','url':'https://www.ccourt.go.kr/'}],
    cases=((CONSTITUTION,'53','법률의 공포 절차는 어떤 법에 이어지나?','국회법의 헌법 제53조 인용 원문을 확인합니다.'),
           (CONSTITUTION,'72','중요정책 국민투표의 절차는?','국민투표법이 인용하는 헌법 제72조와 집행 절차를 읽습니다.'),
           (CONSTITUTION,'130','헌법개정 국민투표는 어떻게 이어지나?','국민투표법의 헌법 제130조제1항 인용 원문을 확인합니다.')))

def selected(name,authority,provider):
    from core.procurement_collection import authorities
    canonical=next((n for n in AUTHORITIES if norm(n)==norm(name)),None)
    if provider!='eflaw' or canonical is None:return False
    actual=authorities(authority)
    return not actual if canonical==CONSTITUTION else bool(actual) and actual.issubset(AUTHORITIES[canonical])

# Editorial navigation. Both endpoint bodies are pinned and validated at build time.
# These mappings are deliberately never inserted into the citation graph.
GUIDE=(
 ('31','교육받을 권리','교육기본법','1','교육의 권리·의무와 교육제도의 기본 사항을 정하는 법률을 함께 읽습니다.'),
 ('32','근로의 권리·근로조건','근로기준법','1','헌법에 따라 근로조건의 기준을 정한다는 목적 조항입니다. 이 법의 제1조가 헌법 제32조를 번호로 인용한 것은 아닙니다.'),
 ('33','노동3권','노동조합 및 노동관계조정법','1','단결권·단체교섭권·단체행동권을 구체화하는 법률입니다. 헌법 조문 번호의 직접 인용과 구별합니다.'),
 ('34','사회보장','사회보장기본법','1','사회보장에 관한 권리와 국가 등의 책임을 다루는 기본 법률입니다.'),
 ('35','환경권','환경정책기본법','1','환경 보전의 권리·의무와 국가 등의 책무를 다루는 기본 법률입니다.'),
 ('59','조세법률주의','국세기본법','1','국세에 관한 기본 사항과 납세의무 이행의 공통 규율을 살펴보는 출발점입니다. 개별 세목 전체를 대응시킨 목록은 아닙니다.'),
 ('96','행정각부의 조직','정부조직법','1','행정기관의 설치·조직·직무범위를 정하는 일반법의 목적 조항을 함께 읽습니다.'),
 ('102','법원의 조직','법원조직법','1','각급 법원의 조직을 정하는 법률입니다. 관련성 안내와 조문 번호 인용을 구별합니다.'),
 ('111','헌법재판','헌법재판소법','1','헌법재판소의 조직·운영과 심판절차를 구체화하는 법률입니다.'),
 ('118','지방자치의 조직','지방자치법','1','지방자치단체의 종류·조직·운영 등에 관한 기본 사항을 정하는 법률입니다.'),
 ('119','경제질서','독점규제 및 공정거래에 관한 법률','1','시장지배적 지위 남용·경제력 집중·부당한 공동행위 등 경쟁질서를 다루는 법률의 예입니다. 헌법 제119조의 모든 내용을 대표하지 않습니다.'),
)
