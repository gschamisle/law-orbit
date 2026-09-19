"""Map labels use official API abbreviations; full names remain identifiers."""
from __future__ import annotations

# These seven long regulation names have no API abbreviation. These are display
# labels only, never official titles, identifiers, aliases for parsing or URLs.
DISPLAY_LABELS = {
    '금융실명거래및비밀보장에관한법률부칙제7조의규정에의한소득세등의계산방법에관한규칙': '실명법부칙 소득세 계산규칙',
    '금융위원회 소관 비영리법인의 설립 및 감독에 관한 규칙': '금융위 비영리법인규칙',
    '금융위원회와 그 소속기관 직제': '금융위 직제',
    '금융위원회와 그 소속기관 직제 시행규칙': '금융위 직제 시행규칙',
    '대부업정책협의회 등의 구성 및 운영에 관한 규정': '대부업정책협의회규정',
    '중소기업은행법제54조제6항시행에관한규정': '기업은행법54조 시행규정',
    '중소기업은행법제54조제6항시행에관한규정 시행세칙': '기업은행법54조 시행세칙',
}


def labels(catalog: list[dict]) -> dict[str, str]:
    result = {law['name']: law.get('short_name', '').strip() or DISPLAY_LABELS.get(law['name'], law['name'])
              for law in catalog}
    # A provider abbreviation collision must not make distinct documents look identical.
    counts = {label: sum(value == label for value in result.values()) for label in set(result.values())}
    return {name: label if counts[label] == 1 else name for name,label in result.items()}
