"""Declared health-care phase 1; navigation tags never create legal relations."""
from core.fsc_collection import norm

BASES=('의료법','간호법')
PUBLIC_BASES=('보건의료기본법','지역보건법','공공보건의료에 관한 법률','국민건강증진법')
INSURANCE_BASES=('국민건강보험법','의료급여법')
SUPPORT='간호사의 진료지원업무 수행에 관한 규칙'
ACTS='간호사의 진료지원업무 수행행위 목록 고시'
BENEFITS='국민건강보험 요양급여의 기준에 관한 규칙'

# Exact current titles only. 보건의료기본법 has no 시행규칙; discovery must
# verify every declared document instead of guessing a three-document family.
FAMILIES={name:tuple(name+s for s in ('',' 시행령',' 시행규칙'))
          for name in BASES+PUBLIC_BASES+INSURANCE_BASES if name!='보건의료기본법'}
FAMILIES['보건의료기본법']=('보건의료기본법','보건의료기본법 시행령')
STATUTES=tuple(doc for name in BASES+PUBLIC_BASES+INSURANCE_BASES for doc in FAMILIES[name])+(SUPPORT,BENEFITS)
LEGACY_STATUTES=tuple(doc for name in BASES for doc in FAMILIES[name])+(SUPPORT,)
SECTOR_ALIASES={'opening':'institutions','staff':'institutions','support':'institutions'}
KEYWORDS={
    'institutions':('의료기관','의료인','의료법','간호법','간호사','진료지원','의료법인','진료과목','병상'),
    'public':('보건의료기본법','지역보건','공공보건의료','국민건강증진','건강증진','보건소','보건지소',
              '보건진료소','건강생활지원센터','보건의료발전계획'),
    'insurance':('국민건강보험','건강보험심사평가원','의료급여','요양급여','보험급여','급여비용',
                 '보험료','본인부담','요양기관'),
}
_DOCUMENT_SECTORS={norm(doc):sector for bases,sector in
                   ((BASES,'institutions'),(PUBLIC_BASES,'public'),(INSURANCE_BASES,'insurance'))
                   for name in bases for doc in FAMILIES[name]}
_DOCUMENT_SECTORS.update({norm(SUPPORT):'institutions',norm(ACTS):'institutions',norm(BENEFITS):'insurance'})


def document_tags(name):
    """Owner-family navigation; exact names avoid classifying out-of-scope laws."""
    sector=_DOCUMENT_SECTORS.get(norm(name))
    return [sector] if sector else []


def article_tags(name,article):
    """Keep the owner axis and add every matching cross-topic navigation tag.

    An institution mentioned by insurance rules stays visible in both views.
    Only the shared citation parser creates explicit legal connections.
    """
    value=norm(article.get('title','')+' '+article.get('text',''))
    result=document_tags(name)
    for sector,words in KEYWORDS.items():
        if sector not in result and any(norm(word) in value for word in words):result.append(sector)
    return result


PROFILE=dict(title='보건·의료',authorities=('보건복지부',),
    statutes=STATUTES,required=STATUTES,
    law_queries=BASES+PUBLIC_BASES+INSURANCE_BASES+(SUPPORT,BENEFITS),
    rule_queries=(ACTS,),rules=(ACTS,),required_rules=(ACTS,),
    sectors={'all':'전체 연결','institutions':'의료기관·인력','public':'지역·공공보건','insurance':'건강보험·의료급여'},
    sector_aliases=SECTOR_ALIASES,keywords=KEYWORDS,
    default='의료법',
    default_laws={'all':'의료법','institutions':'의료법','public':'지역보건법','insurance':'국민건강보험법'},
    default_refs={'all':'제43조','institutions':'제43조','public':'제11조','insurance':'제42조'},
    purpose='의료기관·인력, 지역·공공보건, 건강보험·의료급여의 법령과 명시적 인용을 함께 읽습니다. 의료기관 시설·정원과 진료지원의 검증된 별표도 유지합니다.',
    limitations=[
        '의료법·간호법과 지역·공공보건·건강보험·의료급여의 선정 법령 범위입니다. 보건의료 전체 법령을 수집한 것은 아닙니다. 감염병·응급의료·약사·의료기기 법령군은 이번 확장에 포함하지 않습니다.',
        '국민건강보험 요양급여 기준 규칙은 포함하지만 수가표·급여 고시 전체, 심사지침·개별 급여 사례는 수집하지 않습니다. 급여 인정 여부·수가·본인부담액을 자동 판정하지 않습니다.',
        '본문을 검증한 별표 4개만 칸·문단 단위의 명시적 인용을 분석합니다. 나머지 별표·서식은 공식 링크와 미분석 상태로 남깁니다.',
        '별표의 같은 항목·다른 칸 참조, 병합 칸의 기관별 귀속, 면적·정원 산식은 자동 판정하지 않습니다. 칸·문단 읽기는 원본 표 배치를 대체하지 않습니다.',
        '업무 분류는 법령 소속과 본문 핵심어를 함께 사용하는 탐색 보조입니다. 복수 분류가 법적 적용범위나 개정 의무를 뜻하지 않습니다.',
        '인허가 가능 여부, 시설·인력 기준 충족 여부, 의료행위 적법성이나 개인별 임상 판단을 자동 판정하지 않습니다.'],
    companion_sources=[{'title':'국가법령정보센터 · 의료법','url':'https://www.law.go.kr/법령/의료법'},
                       {'title':'국가법령정보센터 · 국민건강보험법','url':'https://www.law.go.kr/법령/국민건강보험법'}],
    cases=(('의료법','33','의료기관 개설의 근거와 후속 규정은?','개설 조문과 수집한 시행령·시행규칙의 인용 근거를 읽습니다.'),
           ('의료법','36','시설·인력 기준은 어느 별표에 있나?','준수사항과 시행규칙을 따라 시설·규격·정원 별표를 읽습니다.'),
           ('의료법','43','진료과목과 의료인 정원표는 어떻게 이어지나?','제43조를 인용하는 의료인 정원표의 실제 칸과 인용 문구를 확인합니다.'),
           ('지역보건법','11','보건소의 업무는 어떤 보건의료 근거에 연결되나?','보건소 기능·업무의 조문에서 보건의료기본법·건강증진 관련 명시적 인용을 확인합니다.'),
           ('공공보건의료에 관한 법률 시행규칙','2','공공보건의료 협약은 의료기관 개설 근거와 어떻게 연결되나?','수집 원문의 의료법 제33조 인용과 공공보건의료 법률 근거를 함께 읽습니다.'),
           ('국민건강보험법','42','요양기관과 의료기관·보건소는 어디서 연결되나?','의료법·지역보건법 등 요양기관 조문의 명시적 인용을 확인합니다. 미수집 약사법 등은 외부 근거로 남깁니다.'),
           ('의료급여법','9','의료급여기관은 어떤 기관·하위법령에 연결되나?','의료급여기관 조문에서 의료기관·보건기관과 수집 하위법령의 명시적 인용을 확인합니다. 개별 급여 인정 여부는 판정하지 않습니다.')))
