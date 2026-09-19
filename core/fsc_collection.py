"""FSC discovery and pinned-edition collection; no guessed IDs or counts.

Administrative-rule bodies are retained but NOT fed into the statute parser.
Their numbering, source hierarchy and law aliases require their own adapter.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import tempfile
import time
import xml.etree.ElementTree as ET

FSC_ORG = "1160100"
FSC_AUTHORITY = "금융위원회"
ORG_SOURCE = "https://opinion.lawmaking.go.kr/rest/ogLmPp"
LIST_GUIDES = {
    "eflaw": "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsEfYdListGuide",
    "admrul": "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=admrulListGuide",
}
CURRENT_NW = {"eflaw": 3, "admrul": 1}  # DIFFERENT semantics in the two APIs
ROW_TAG = {"eflaw": "law", "admrul": "admrul"}
ROOT_TAG = {"eflaw": "LawSearch", "admrul": "AdmRulSearch"}


class CollectionError(RuntimeError):
    """Stable safe error code: never include request URLs or credentials."""


def norm(value: str) -> str:
    return "".join(str(value).split()).replace("ㆍ", "").replace("·", "")


def ymd(value: str) -> str:
    value = str(value).strip().replace("-", "")
    if not re.fullmatch(r"\d{8}", value):
        raise CollectionError("invalid-date")
    try:
        datetime.strptime(value, "%Y%m%d")
    except ValueError:
        raise CollectionError("invalid-date") from None
    return value


def xml_root(raw: bytes) -> ET.Element:
    # Reject UTF-16/32 and DTDs rather than permitting hidden entity declarations.
    if b"\x00" in raw or b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise CollectionError("unsafe-xml")
    try:
        return ET.fromstring(raw)
    except ET.ParseError:
        raise CollectionError("invalid-xml") from None


def field(root: ET.Element, *names: str) -> str:
    for name in names:
        value = root.findtext(name)
        if value is not None and value.strip():
            return value.strip()
    return ""


def require_id(value: str) -> str:
    if not value or not value.isdigit():
        raise CollectionError("missing-official-identifier")
    return value


# Financial Intelligence Unit is an FSC subordinate authority, not FSS.
# https://www.kofiu.go.kr/kor/policy/amls01.do
FSC_AFFILIATES = {"금융정보분석원"}


def authority_matches(value: str, *, include_affiliates: bool = False) -> bool:
    allowed = {FSC_AUTHORITY} | (FSC_AFFILIATES if include_affiliates else set())
    return bool(allowed.intersection(p.strip() for p in re.split(r"[,，/;ㆍ·\n]", value)))


class LawTransport:
    def __init__(self, key: str, *, attempts: int = 3, timeout: int = 40, reuse_connections: bool = False):
        if not key.strip():
            raise CollectionError("missing-law-api-key")
        if attempts < 1 or timeout < 1:
            raise CollectionError("invalid-transport-options")
        self._key, self.attempts, self.timeout = key, attempts, timeout
        self._reuse_connections = reuse_connections
        if reuse_connections:
            import threading
            self._sessions = threading.local()

    def __call__(self, endpoint: str, params: dict) -> bytes:
        if endpoint not in ("lawSearch.do", "lawService.do") or "OC" in params:
            raise CollectionError("invalid-endpoint-or-auth-override")
        import requests
        client = requests
        if self._reuse_connections:
            if not hasattr(self._sessions, 'client'):
                self._sessions.client = requests.Session()
            client = self._sessions.client
        for attempt in range(self.attempts):
            try:
                response = client.get(
                    "https://www.law.go.kr/DRF/" + endpoint,
                    params={**params, "type": "XML", "OC": self._key},
                    timeout=self.timeout, allow_redirects=False,
                )
                if response.status_code == 200:
                    return response.content
            except requests.RequestException:
                pass
            if attempt + 1 < self.attempts:
                time.sleep(attempt + 1)
        raise CollectionError("official-api-request-failed") from None


Request = Callable[[str, dict], bytes]


def list_record(row: ET.Element, target: str, as_of: str, *, fss=False) -> dict:
    as_of = ymd(as_of)
    if target == "eflaw":
        name = field(row, "법령명한글")
        stable = require_id(field(row, "법령ID"))
        serial = require_id(field(row, "법령일련번호"))
        kind, published = field(row, "법령구분명"), field(row, "공포일자")
    elif target == "admrul":
        name = field(row, "행정규칙명")
        stable = require_id(field(row, "행정규칙ID"))
        serial = require_id(field(row, "행정규칙일련번호"))
        kind, published = field(row, "행정규칙종류"), field(row, "발령일자")
    else:
        raise CollectionError("unknown-list-provider")
    authority = field(row, "소관부처명")
    authority_ok = (target == "admrul" and authority == "금융감독원" and norm(name).endswith("시행세칙")) if fss else authority_matches(authority, include_affiliates=target == "admrul")
    if not name or not kind or not authority_ok:
        raise CollectionError("missing-name-kind-or-wrong-authority")
    effective, published = ymd(field(row, "시행일자")), ymd(published)
    if published > as_of:
        raise CollectionError("future-publication-in-current-list")
    return dict(
        name=name, short_name=field(row, "법령약칭명") if target == "eflaw" else "", provider=target, document_id=stable, version_id=serial,
        uid=f"{target}:{stable}", edition_key=f"{target}:{stable}:{serial}:{effective}",
        effective=effective, promulgated=published, kind=kind,
        managing_authority=authority, requested_org="" if fss else FSC_ORG,
        collection_scope="fss-sector-bylaws" if fss else "fsc-authority",
        state="scheduled" if effective > as_of else "current-candidate",
        body_status="not-collected", category="fsc",
        source_url=(
            f"https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq={serial}&efYd={effective}"
            if target == "eflaw" else
            f"https://www.law.go.kr/LSW/admRulLsInfoP.do?admRulSeq={serial}"
        ),
    )


def discover(request: Request, target: str, *, as_of: str,
             display: int = 100, max_pages: int = 1000) -> dict:
    """Enumerate every page or fail; never return a prefix as the whole list."""
    if target not in CURRENT_NW or not 1 <= display <= 100 or max_pages < 1:
        raise CollectionError("invalid-discovery-options")
    as_of = ymd(as_of)
    records, page_hashes, seen = [], [], set()
    expected = None
    for page in range(1, max_pages + 1):
        raw = request("lawSearch.do", dict(target=target, org=FSC_ORG,
                      nw=CURRENT_NW[target], display=display, page=page, sort="lasc"))
        root = xml_root(raw)
        if root.tag != ROOT_TAG[target]:
            raise CollectionError("unexpected-list-envelope")
        try:
            count, returned_page = int(field(root, "totalCnt")), int(field(root, "page"))
        except ValueError:
            raise CollectionError("missing-list-pagination") from None
        if count < 0 or returned_page != page:
            raise CollectionError("invalid-list-pagination")
        if expected is not None and expected != count:
            raise CollectionError("inventory-changed-during-pagination")
        expected = count
        page_hashes.append(hashlib.sha256(raw).hexdigest())
        rows = root.findall(ROW_TAG[target])
        if len(rows) != min(display, max(0, count - len(records))):
            raise CollectionError("short-or-oversized-page")
        for row in rows:
            record = list_record(row, target, as_of)
            if record["uid"] in seen:
                raise CollectionError("duplicate-or-repeated-current-document")
            seen.add(record["uid"])
            records.append(record)
        if len(records) == count:
            return dict(provider=target, requested_org=FSC_ORG, as_of=as_of,
                        list_status="complete", expected=count, received=len(records),
                        pages=page, page_sha256=page_hashes, records=records,
                        list_guide=LIST_GUIDES[target])
        if page >= math.ceil(count / display):
            raise CollectionError("list-count-mismatch")
    raise CollectionError("page-limit-before-completion")


def body_params(record: dict) -> dict:
    if record["provider"] == "eflaw":
        return dict(target="eflaw", MST=record["version_id"], efYd=record["effective"])
    if record["provider"] == "admrul":
        # admrul ID means serial, whereas LID is the stable document ID.
        return dict(target="admrul", ID=record["version_id"])
    raise CollectionError("unknown-body-provider")


def check_body(root: ET.Element, record: dict) -> None:
    law = record["provider"] == "eflaw"
    name = field(root, ".//법령명_한글" if law else ".//행정규칙명")
    stable = field(root, ".//법령ID" if law else ".//행정규칙ID")
    if norm(name) != norm(record["name"]) or stable != record["document_id"]:
        raise CollectionError("body-identity-mismatch")
    if ymd(field(root, ".//시행일자")) != record["effective"]:
        raise CollectionError("body-edition-mismatch")
    # Jointly managed documents list all issuers in search, but the service body
    # can expose only the lead issuer. It must be an issuer from that pinned list.
    listed = {p.strip() for p in re.split(r"[,，/;ㆍ·\n]", record['managing_authority']) if p.strip()}
    actual = {p.strip() for tag in ('.//소관부처명', './/소관부처') for node in root.findall(tag)
              for p in re.split(r"[,，/;ㆍ·\n]", node.text or '') if p.strip()}
    fss = (not law and record.get('collection_scope') == 'fss-sector-bylaws'
           and record['managing_authority'] == '금융감독원' and norm(record['name']).endswith('시행세칙'))
    if (not (fss or authority_matches(record['managing_authority'], include_affiliates=not law))
            or not actual or not actual.issubset(listed)):
        raise CollectionError("body-authority-mismatch")
    if not law and field(root, ".//행정규칙일련번호") != record["version_id"]:
        raise CollectionError("body-edition-mismatch")


def collect_body(request: Request, record: dict, *, as_of: str) -> dict:
    if record["state"] != "current-candidate" or record["effective"] > ymd(as_of):
        raise CollectionError("not-effective-on-collection-date")
    raw = request("lawService.do", body_params(record))
    root = xml_root(raw)
    check_body(root, record)
    common = {**record, "body_sha256": hashlib.sha256(raw).hexdigest(),
              "fetched_at": as_of, "state": "current-body-verified"}
    if record["provider"] == "admrul":
        bodies = [re.sub(r"([?&](?:amp;)?[Oo][Cc]=)[^&\s\"<>]+", r"\1[redacted]", n.text or "")
                  for n in root.findall(".//조문내용")]
        if not any(text.strip() for text in bodies):
            raise CollectionError("administrative-body-unavailable")
        return {**common, "raw_body_blocks": bodies, "articles": [], "annexes": [],
                "body_status": "collected-not-indexed",
                "coverage": {"provisions": "adapter-pending", "supplement": "not-indexed",
                             "annex_body": "not-indexed", "relative_aliases": "unresolved"}}
    from scripts.collect_law_universe import parse_body
    parsed = parse_body(root, dict(name=record["name"], law_id=record["document_id"],
                        mst=record["version_id"], effective=record["effective"],
                        category="fsc", family=record["name"]))
    if not parsed["articles"]:
        raise CollectionError("statute-body-unavailable")
    return {**parsed, **common, "body_status": "indexed-statute-text",
            "coverage": {"provisions": "parsed", "supplement": "not-indexed",
                         "annex_body": "not-indexed"}}


def collect_inventory(request: Request, *, as_of: str, include_rules: bool = True) -> dict:
    targets = ("eflaw", "admrul") if include_rules else ("eflaw",)
    layers = {target: discover(request, target, as_of=as_of) for target in targets}
    return dict(schema_version=1, as_of=ymd(as_of), org=FSC_ORG,
                managing_authority=FSC_AUTHORITY, org_source=ORG_SOURCE,
                layers=layers, worldwide_coverage="not-claimed",
                fss_rules="not-collected-separate-authority")


def collect_sources(request: Request, inventory: dict, *, cache_dir: Path | None = None,
                    progress: Callable | None = None, workers: int = 1) -> dict:
    """Keep validated editions resumable; publish a source only if all bodies pass."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    if not 1 <= workers <= 4:
        raise CollectionError("invalid-worker-count")
    statutes, rules, scheduled, jobs = [], [], [], []
    for target, layer in inventory["layers"].items():
        if layer["list_status"] != "complete":
            raise CollectionError("incomplete-inventory")
        if layer.get("received") != len(layer["records"]) or layer.get("expected") != len(layer["records"]):
            raise CollectionError("inventory-record-count-mismatch")
        for record in layer["records"]:
            if record['provider'] != layer.get('provider', target):
                raise CollectionError("inventory-provider-mismatch")
            if record["state"] == "scheduled":
                scheduled.append(record)
            else:
                jobs.append(record)
    def body(record):
        cache = None
        if cache_dir:
            token = hashlib.sha256(record['edition_key'].encode()).hexdigest()
            cache = Path(cache_dir) / (token + '.json')
            if cache.exists():
                saved = json.loads(cache.read_text(encoding='utf-8'))
                data = saved['body']
                digest = hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
                if digest != saved['sha256']:
                    raise CollectionError('body-cache-integrity-mismatch')
                if (data['edition_key'] == record['edition_key'] and data['fetched_at'] == inventory['as_of']
                        and data['name'] == record['name'] and data['managing_authority'] == record['managing_authority']):
                    return {**data, **{k:record[k] for k in ('source_url', 'short_name') if k in record}}
        data = collect_body(request, record, as_of=inventory['as_of'])
        if cache:
            digest = hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            atomic_json(cache, {'sha256': digest, 'body': data})
        return data
    failures = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(body, record): record for record in jobs}
        for done, future in enumerate(as_completed(futures), 1):
            record = futures[future]
            try:
                result = future.result()
                (statutes if record['provider'] == 'eflaw' else rules).append(result)
                if progress:
                    progress(done, len(jobs), record, result['body_status'])
            except CollectionError as error:
                failures.append({'name': record['name'], 'provider': record['provider'], 'code': str(error)})
                if progress:
                    progress(done, len(jobs), record, 'failed:' + str(error))
    if failures:
        if cache_dir:
            atomic_json(Path(cache_dir).parent / 'collection-failures.json', {'failures': failures})
        raise CollectionError('body-collection-incomplete:' + str(len(failures)))
    if not statutes:
        raise CollectionError("empty-statute-corpus")
    return dict(schema_version=1, built_at=inventory["as_of"],
                provider="법제처 공식 API: eflaw/admrul; pinned editions", laws=sorted(statutes, key=lambda l:l['name']),
                administrative_rules=sorted(rules, key=lambda l:l['name']), scheduled=scheduled, inventory=inventory,
                coverage={"fsc_statute_list": "complete", "fsc_statute_bodies": "collected",
                          "fsc_rules": "collected-not-indexed" if rules else "not-collected",
                          "fss_rules": "not-collected", "external_reverse": "not-collected",
                          "supplement": "not-indexed", "annex_body": "not-indexed"})


def atomic_json(path: Path, data: dict) -> None:
    """A failed write must not replace the last complete data."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(data, ensure_ascii=False, indent=2)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
            tmp = Path(stream.name)
            stream.write(encoded)
        tmp.replace(path)
    finally:
        if tmp and tmp.exists():
            tmp.unlink()
