"""Reviewed procedural notes; never manufacture citation or applicability edges."""
import hashlib
from core.remedy_profile import APPEAL, LITIGATION, TAX, CUSTOMS, LOCAL, LABOR, COMMISSION, HEALTH, MEDICAL_AID
from core.remedy_profile import BASIC, INFORMATION, COMPETITION, GREENBELT, REGIONAL, JEJU
from core.fsc_collection import norm
from core.citation_scope import parse_target

# A paragraph is shown only when its full, checked wording exists in the reader.
# Each explanation is deliberately narrower than a law-wide applicability claim.
SPECS = (
    (BASIC, '36', '', '제36조', ('이의신청과 심판·소송', '적용 제외 확인'), '제3항은 이의신청과 관계없이 행정심판·행정소송을 제기할 수 있다고 정합니다. 제6항의 다른 법률과의 관계 및 제8항의 적용 제외를 함께 읽습니다. 이의신청이라는 명칭만으로 특별행정심판이나 필수 선행 절차로 분류하지 않습니다.', ('관계없이', '⑧', '공무원 인사', '과태료')),
    (INFORMATION, '18', '', '제18조', ('정보공개 이의신청',), '공공기관에 하는 이의신청입니다. 제19조의 행정심판과 구별하며, 이의신청을 거치지 않아도 행정심판을 청구할 수 있다는 제19조제2항을 함께 확인합니다.', ('이의신청', '행정심판 또는 행정소송')),
    (INFORMATION, '19', '', '제19조', ('이의신청 선행 불필요', '법령 전체 참조'), '제2항은 이의신청 없이 행정심판을 청구할 수 있다고 명시합니다. 제1항의 행정심판법 참조는 특정 조문번호를 지목하지 않아 법령 전체 참조로 표시합니다.', ('제18조', '거치지 아니하고', '행정심판법')),
    (INFORMATION, '20', '', '제20조', ('정보공개 소송', '법령 전체 참조'), '정보공개 관련 불복 소송과 법원의 심리 규정을 함께 읽습니다. 행정소송법의 특정 조문번호를 새로 만들어 연결하지 않습니다.', ('행정소송법', '재판장')),
    (COMPETITION, '96', '', '제96조', ('공정거래 이의신청',), '공정거래위원회에 대한 이의신청과 재결 규정입니다. 제99조의 소 제기 및 제100조의 전속관할과 구별해 읽으며, 이 조문만으로 일반 행정심판법의 적용 여부를 판정하지 않습니다.', ('이의신청을 할 수 있다', '재결')),
    (COMPETITION, '99', '', '제99조', ('소 제기',), '처분 통지와 이의신청 재결서 송달을 규정한 소 제기 조문입니다. 개별 사건의 기산점이나 기간 충족 여부는 자동 계산하지 않습니다.', ('처분의 통지를 받은 날 또는', '불변기간')),
    (COMPETITION, '100', '', '제100조', ('전속관할',), '제99조의 불복 소송은 서울고등법원을 전속관할로 정합니다. 원문에 있는 제99조 인용을 연결합니다.', ('제99조', '서울고등법원')),
    (GREENBELT, '27', '', '제27조', ('관할 특례', '대상 처분 한정'), '매수 여부·매수가격 또는 부담금 부과·징수에 관한 제1항의 이의신청에 한정된 특례입니다. 제2항은 행정심판법 제6조에도 불구하고 중앙토지수용위원회가 심리·의결하여 재결한다고 정합니다.', ('매수가격', '부담금', '제6조에도 불구하고', '중앙토지수용위원회')),
    (REGIONAL, '78', '', '제78조', ('관할 특례', '지정권자별 조건'), '단서는 행정기관이 아닌 시행자가 한 처분을 대상으로 합니다. 다른 법률의 특별 규정 유무와 지정권자가 국토교통부장관인지 시·도지사인지에 따른 조건을 함께 확인합니다.', ('행정기관이 아닌', '다른 법률에 특별한 규정', '지정권자')),
    (JEJU, '350', '', '제350조', ('관할 특례', '보훈사무 한정'), '제341조부터 제349조까지의 보훈사무에 관한 제주 소속 행정청의 처분·부작위에 한정된 특례입니다. 제주특별법의 모든 처분에 같은 관할이 적용된다는 뜻은 아닙니다.', ('제341조부터 제349조까지', '보훈사무', '제6조제3항에도 불구하고')),
    (APPEAL, '4', '②', '제4조제2항', ('특별절차와 일반법',), '특별행정심판·절차 특례에서 규정하지 않은 사항에 관한 일반 규정입니다. 개별법의 적용 제외·준용 조항도 함께 확인합니다.', ('특별행정심판', '규정하지 아니한 사항')),
    (LITIGATION, '18', '①', '제18조제1항', ('행정심판과 소송',), '취소소송과 행정심판의 일반 관계를 정합니다. 다른 법률에서 재결을 먼저 거치도록 정한 경우의 단서가 있습니다.', ('거치지 아니하고', '다른 법률')),
    (TAX, '56', '①', '제56조제1항', ('적용 제외', '일부 준용'), '제55조의 처분은 행정심판법 적용을 제외하면서 심사·심판청구에 일부 조문을 준용합니다. 두 문장을 함께 읽어야 합니다.', ('적용하지 아니한다', '준용하며')),
    (TAX, '56', '②', '제56조제2항', ('소송 전 절차·예외',), '심사·심판청구와 그 결정을 거치는 규정 및 재조사 결정 후 처분에 관한 단서를 함께 확인합니다.', ('거치지 아니하면', '다만')),
    (CUSTOMS, '120', '①', '제120조제1항', ('적용 제외', '일부 준용'), '제119조의 처분에 대한 적용 제외와 심사·심판청구의 일부 준용을 함께 정합니다.', ('적용하지 아니한다', '준용하며')),
    (CUSTOMS, '120', '②', '제120조제2항', ('소송 전 절차·예외',), '심사·심판청구와 결정의 선행 규정에 단서가 있습니다. 모든 관세 사건에 동일한 경로를 적용한다는 뜻은 아닙니다.', ('거치지 아니하면', '다만')),
    (LOCAL, '98', '①', '제98조제1항', ('적용 제외', '일부 준용'), '이의신청 대상 처분에 관한 적용 제외와 이의신청 절차의 일부 준용입니다. 심판청구는 제2항과 구별합니다.', ('적용하지 아니한다', '준용하며')),
    (LOCAL, '98', '②', '제98조제2항', ('국세 절차 준용',), '심판청구 대상 처분에는 국세기본법 제56조제1항을 준용합니다. 지방세의 이의신청과 심판청구를 한 절차로 합치지 않습니다.', ('국세기본법', '제56조제1항')),
    (LOCAL, '98', '③', '제98조제3항', ('소송 전 절차·예외',), '심판청구와 결정의 선행 규정 및 재조사 결정 후 처분에 관한 예외를 함께 확인합니다.', ('심판청구와', '다만')),
    (LABOR, '31', '①', '제31조제1항', ('노동위원회 재심',), '지방노동위원회의 구제명령·기각결정에 대한 중앙노동위원회 재심 규정입니다. 일반 행정심판 청구를 뜻하지 않습니다.', ('중앙노동위원회', '재심')),
    (LABOR, '31', '②', '제31조제2항', ('재심판정 후 소송',), '중앙노동위원회 재심판정에 대한 소송 규정입니다. 기산점과 기간은 해당 원문으로 확인합니다.', ('재심판정', '행정소송법')),
    (COMMISSION, '15의3', '', '제15조의3', ('일부 준용',), '선정대표자·지위 승계·대리인 선임에 행정심판법 일부를 준용합니다. 노동위원회 사건 전체가 일반 행정심판 절차라는 뜻은 아닙니다.', ('행정심판법', '제18조를 준용')),
    (HEALTH, '88', '①', '제88조제1항', ('건강보험 심판청구',), '이의신청 결정에 대한 건강보험분쟁조정위원회 심판청구와 제기기간·방법의 준용 근거입니다.', ('건강보험분쟁조정위원회', '제87조제3항')),
    (MEDICAL_AID, '30의2', '①', '제30조의2제1항', ('의료급여 심판청구',), '제30조제2항의 급여비용심사기관 이의신청 결정에 관한 규정입니다. 모든 의료급여 처분이 이 조항의 대상이라는 뜻은 아닙니다.', ('제30조제2항', '국민건강보험법', '제89조')),
)


def reading_guide(documents):
    docs = {d['name']: d for d in documents}
    entries = []
    for law, jo, prefix, scope, labels, summary, required in SPECS:
        doc = docs[law]
        article = next(a for a in doc['articles'] if a['jo'] == jo)
        quote = next((line.strip() for line in article['text'].splitlines() if line.startswith(prefix)), '') if prefix else article['text']
        if not quote or any(norm(term) not in norm(quote) for term in required):
            raise ValueError('Reviewed procedural wording changed: ' + law + ' ' + scope)
        entries.append(dict(law=law, jo=jo, scope=scope, labels=list(labels), summary=summary,
            full_article=not bool(prefix),
            quote=quote, quote_sha256=hashlib.sha256(quote.encode()).hexdigest(),
            article_sha256=hashlib.sha256(article['text'].encode()).hexdigest(),
            effective=article.get('effective') or doc['effective'], url=doc['source_url']))
    return dict(kind='editorial-remedy-guide', schema=1, is_citation=False, entries=entries)


def validate_guide(value, documents):
    # law_id is a transport identifier, bound separately by the site validator.
    clean = {**value, 'entries': [{k: v for k, v in r.items() if k != 'law_id'} for r in value['entries']]}
    if clean != reading_guide(documents):
        raise ValueError('Procedural reading guide and verified source differ')


def procedural_article(law, jo):
    if law in (APPEAL, APPEAL+' 시행령', APPEAL+' 시행규칙', LITIGATION):
        return True
    if law == COMMISSION:
        return jo in ('15의3', '26', '27')
    if law == MEDICAL_AID:
        return jo in ('30', '30의2')
    selected = {BASIC: ('36',), BASIC+' 시행령': ('11',), INFORMATION: ('18', '19', '20'),
                COMPETITION: ('96', '97', '99', '100'), GREENBELT: ('27',),
                REGIONAL: ('78',), JEJU: ('350', '416')}
    if law in selected:
        return jo in selected[law]
    ranges = {TAX: (55, 81), CUSTOMS: (119, 132), LOCAL: (89, 100), LABOR: (28, 33), HEALTH: (87, 90)}
    if law not in ranges:
        return False
    # Do not include tax investigation Chapter 7-2 (81-2 onward).
    if law == TAX and jo.startswith('81의'):
        return False
    try: number = int(jo.split('의')[0])
    except (ValueError, AttributeError): return False
    lo, hi = ranges[law]
    return lo <= number <= hi


def procedural_edge(edge):
    if procedural_article(edge.get('source_law', ''), edge.get('source_jo', '')):
        return True
    if edge.get('target_kind') == 'article':
        try: jo = parse_target(edge['target_ref'], allow_hyphen=True).jo
        except (ValueError, KeyError): return False
        return procedural_article(edge.get('target_law', ''), jo)
    return edge.get('target_law') in (APPEAL, LITIGATION)
