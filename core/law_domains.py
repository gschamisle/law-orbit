"""Domain registry for extending the law galaxy beyond tax law.

The current tax-law universe remains the default and is intentionally not
rewired here.  New domains start from explicitly verified seeds and collection
layers so that a regulator's notices or supervisory rules are never inferred
from a statute name alone.
"""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_DOMAIN = "tax"
FSC_VERIFIED_AS_OF = "2026-09-16"
FSC_STATUTE_LIST_URL = "https://www.fsc.go.kr/po040101"
FSC_RULES_BOARD_URL = "https://www.fsc.go.kr/po040200"
LAW_OPEN_API_URL = "https://open.law.go.kr"
FSS_HOME_URL = "https://www.fss.or.kr"


@dataclass(frozen=True)
class LawSeed:
    """A law name that has been verified in an official source.

    IDs and effective-edition identifiers are deliberately blank until the
    collector resolves them against the official effective-date API.  A seed
    therefore proves only that the named principal statute belongs in the
    domain inventory, not that any guessed subordinate rule is related to it.
    """

    name: str
    group: str
    priority: int
    source_url: str
    source_page: int
    verified_as_of: str = FSC_VERIFIED_AS_OF
    law_id: str = ""
    mst: str = ""
    effective: str = ""
    status: str = "verified-name-only"


@dataclass(frozen=True)
class CollectionLayer:
    key: str
    label: str
    authority: str
    source_url: str
    discovery_policy: str
    coverage: str
    relationship_policy: str = "official-evidence-only"


@dataclass(frozen=True)
class DomainSpec:
    key: str
    label: str
    focus_category: str
    principal_laws: tuple[LawSeed, ...]
    collection_layers: tuple[CollectionLayer, ...]
    notes: str = ""


def _fsc(name: str, group: str, priority: int, page: int) -> LawSeed:
    return LawSeed(
        name=name,
        group=group,
        priority=priority,
        source_url=f"{FSC_STATUTE_LIST_URL}?curPage={page}",
        source_page=page,
    )


# Initial verified seed set, not the full FSC inventory.  Every name below was
# observed on the FSC's current-law list on 2026-09-16.  The complete 117-item
# inventory must be regenerated from official sources before production use.
FSC_LAW_SEEDS: tuple[LawSeed, ...] = (
    _fsc("개인금융채권의 관리 및 개인금융채무자의 보호에 관한 법률", "consumer-debt", 2, 1),
    _fsc("가상자산 이용자 보호 등에 관한 법률", "digital-finance", 2, 1),
    _fsc("금융복합기업집단의 감독에 관한 법률", "common-supervision", 2, 1),
    _fsc("중소기업은행법", "policy-finance", 3, 3),
    _fsc("주식회사 등의 외부감사에 관한 법률", "capital-accounting", 2, 3),
    _fsc("전기통신금융사기 피해 방지 및 피해금 환급에 관한 특별법", "consumer-protection", 3, 4),
    _fsc("자산유동화에 관한 법률", "capital-market", 2, 4),
    _fsc("자본시장과 금융투자업에 관한 법률", "capital-market", 1, 4),
    _fsc("인터넷전문은행 설립 및 운영에 관한 특례법", "banking", 2, 4),
    _fsc("은행법", "banking", 2, 5),
    _fsc("유사수신행위의 규제에 관한 법률", "consumer-protection", 3, 5),
    _fsc("온라인투자연계금융업 및 이용자 보호에 관한 법률", "digital-finance", 2, 5),
    _fsc("예금자보호법", "common-supervision", 2, 5),
    _fsc("여신전문금융업법", "credit-finance", 2, 6),
    _fsc("신용협동조합법", "mutual-finance", 3, 6),
    _fsc("신용정보의 이용 및 보호에 관한 법률", "data-credit", 1, 6),
    _fsc("신용보증기금법", "policy-finance", 3, 6),
    _fsc("서민의 금융생활 지원에 관한 법률", "inclusive-finance", 3, 7),
    _fsc("상호저축은행법", "banking", 2, 7),
    _fsc("보험업법", "insurance", 2, 7),
    _fsc("보험사기방지 특별법", "insurance", 3, 7),
    _fsc("기업구조조정 촉진법", "restructuring", 3, 9),
    _fsc("금융회사의 지배구조에 관한 법률", "common-supervision", 1, 9),
    _fsc("금융혁신지원 특별법", "digital-finance", 2, 9),
    _fsc("금융지주회사법", "common-supervision", 2, 10),
    _fsc("금융위원회의 설치 등에 관한 법률", "institutional", 3, 10),
    _fsc("금융실명거래 및 비밀보장에 관한 법률", "common-supervision", 1, 11),
    _fsc("금융소비자 보호에 관한 법률", "consumer-protection", 1, 11),
)

FSC_COLLECTION_LAYERS: tuple[CollectionLayer, ...] = (
    CollectionLayer(
        key="statutes",
        label="법률·대통령령·총리령",
        authority="금융위원회 / 국가법령정보센터",
        source_url=FSC_STATUTE_LIST_URL,
        discovery_policy=(
            "FSC current-law inventory -> resolve exact official law name and effective edition "
            "through law.go.kr eflaw; persist law ID, MST, effective date and source hash"
        ),
        coverage="seeded-partial",
    ),
    CollectionLayer(
        key="fsc-administrative-rules",
        label="금융위 규정·고시·훈령",
        authority="금융위원회",
        source_url=FSC_RULES_BOARD_URL,
        discovery_policy=(
            "Use the official administrative-rule corpus (admrul) and FSC publication evidence; "
            "separate normative texts from amendment notices, registrations and case-specific notices"
        ),
        coverage="not-collected",
    ),
    CollectionLayer(
        key="fss-rules",
        label="금융감독원 시행세칙·검사업무 규정 등",
        authority="금융감독원",
        source_url=FSS_HOME_URL,
        discovery_policy=(
            "Collect only from an identified FSS official source and retain the issuer; do not "
            "treat FSS rules as FSC-issued administrative rules"
        ),
        coverage="not-collected",
    ),
    CollectionLayer(
        key="external-reverse-citations",
        label="타 부처 법령의 금융법 역인용",
        authority="관계 부처 / 국가법령정보센터",
        source_url=LAW_OPEN_API_URL,
        discovery_policy=(
            "Scan the declared external corpus for citations into resolved FSC law IDs; retain "
            "collection failures and out-of-scope status instead of reporting no impact"
        ),
        coverage="not-collected",
    ),
)

FSC_DOMAIN = DomainSpec(
    key="fsc",
    label="금융위원회 법령",
    focus_category="fsc",
    principal_laws=FSC_LAW_SEEDS,
    collection_layers=FSC_COLLECTION_LAYERS,
    notes=(
        "Initial implementation is a verified seed registry only. It intentionally does not "
        "synthesize 시행령/시행규칙/감독규정 names or IDs."
    ),
)

TAX_DOMAIN = DomainSpec(
    key="tax",
    label="세법",
    focus_category="tax",
    principal_laws=(),
    collection_layers=(),
    notes="Existing tax-law manifest and law_universe constants remain authoritative.",
)


def get_domain(key: str | None = None) -> DomainSpec:
    """Return a domain; omitting the key preserves the current tax default."""
    wanted = (key or DEFAULT_DOMAIN).strip().lower()
    if wanted == "tax":
        return TAX_DOMAIN
    if wanted == "fsc":
        return FSC_DOMAIN
    raise KeyError(f"unknown law domain: {key}")


def legacy_tax_scope() -> dict[str, tuple[str, ...]]:
    """Expose the exact pre-registry tax collector scope for regression checks.

    Importing lazily avoids making the existing tax universe depend on this new
    registry and keeps the first FSC draft isolated.
    """
    from core.law_universe import COURT_RULES, EXTERNAL, NEW_TAX

    return {
        "new_tax": tuple(NEW_TAX),
        "external": tuple(EXTERNAL),
        "court_rules": tuple(COURT_RULES),
    }
