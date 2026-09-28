"""Collect verified prior effective editions without modifying a public site.

Only official eflaw XML is requested. Request URLs and authentication values are
never persisted. Output is immutable and fails closed on incomplete/ambiguous
history, unexpected identity, or a current body different from the public body.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime
import hashlib
import html
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import parse_qs, quote, quote_plus, urlsplit
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.collect_law_universe import parse_body, ref, request_xml
from scripts.static_storage import Storage

NAMES = ("법인세법", "소득세법", "조세특례제한법")
GUIDES = {
    "list": "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsEfYdListGuide",
    "body": "https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsEfYdInfoGuide",
}
REVERSE_NOTICE = "과거 하위법령 전체와 역인용 그래프를 수집하지 않았습니다. 과거 대응 인용은 미확인입니다."


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def valid_date(value):
    if not re.fullmatch(r"\d{8}", str(value)):
        raise ValueError("Missing or invalid edition date")
    datetime.strptime(value, "%Y%m%d")
    return value


def identity(root, mst):
    info = root.find("기본정보")
    if info is None:
        raise ValueError("Official response has no statute identity")
    result = {"law_id": info.findtext("법령ID", ""), "name": info.findtext("법령명_한글", ""),
              "mst": str(mst), "effective": valid_date(info.findtext("시행일자", "")),
              "promulgated": valid_date(info.findtext("공포일자", "")),
              "promulgation_number": info.findtext("공포번호", ""),
              "kind": info.findtext("법종구분", "")}
    if not result["law_id"].isdigit() or not result["mst"].isdigit() or not result["promulgation_number"].isdigit():
        raise ValueError("Missing official edition identifier")
    if result["kind"] != "법률" or result["promulgated"] > result["effective"]:
        raise ValueError("Invalid statute kind or promulgation/effective chronology")
    result["url"] = f"https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq={mst}&efYd={result['effective']}"
    return result


def history_rows(root):
    if root.tag != "LawSearch" or root.findtext("resultCode") != "00":
        raise ValueError("Official history search did not succeed")
    result = []
    for row in root.findall("law"):
        result.append({"law_id": row.findtext("법령ID", ""), "name": row.findtext("법령명한글", ""),
                       "mst": row.findtext("법령일련번호", ""), "effective": valid_date(row.findtext("시행일자", "")),
                       "promulgated": valid_date(row.findtext("공포일자", "")),
                       "promulgation_number": row.findtext("공포번호", ""),
                       "status": row.findtext("현행연혁코드", "")})
    return result


def check_identity(actual, expected):
    for field in ("law_id", "name", "mst", "effective", "promulgated", "promulgation_number"):
        if actual.get(field) != expected.get(field):
            raise ValueError("Official history/body identity mismatch: " + field)


def select_previous(rows, current, as_of):
    """Effective chronology controls; a prior edition may have a newer MST.

    Multiple laws can commence on the same day. Choose the last promulgated
    statute/number for that effective day, rejecting an ambiguous identity.
    Every history row must match the official law ID, not a fuzzy title.
    """
    valid_date(as_of)
    if current["effective"] > as_of:
        raise ValueError("The public edition has not commenced")
    exact, older = [], []
    for row in rows:
        # A law ID may have a remote historical former title (e.g. 조세감면규제법).
        # The actual compared edition must still have the exact current title.
        if row["law_id"] != current["law_id"]:
            raise ValueError("History contains a different statute")
        if row["status"] not in ("현행", "연혁"):
            raise ValueError("Unverified history status")
        if row["effective"] > current["effective"] or row["promulgated"] > as_of:
            raise ValueError("History response exceeds the requested effective range")
        if row["mst"] == current["mst"] and row["effective"] == current["effective"]:
            check_identity(row, current)
            exact.append(row)
        if row["effective"] < current["effective"]:
            older.append(row)
    if len(exact) != 1 or not older:
        raise ValueError("Current anchor or prior official edition missing/duplicated")
    rank = lambda row: (row["effective"], row["promulgated"], int(row["promulgation_number"]))
    highest = max(map(rank, older))
    selected = [row for row in older if rank(row) == highest]
    if len(selected) != 1:
        raise ValueError("Ambiguous prior effective edition")
    if selected[0]["name"] != current["name"]:
        raise ValueError("Selected previous edition has a different title; manual verification required")
    if selected[0]["promulgated"] > selected[0]["effective"]:
        raise ValueError("Selected prior edition has retroactive commencement; manual verification required")
    return selected[0]


def body_articles(root, metadata):
    parsed = parse_body(root, metadata)
    result = []
    seen = set()
    for article in parsed["articles"]:
        if not article["jo"] or article["jo"] in seen or not article["text"].strip():
            raise ValueError("Missing/duplicated/empty article in official body")
        seen.add(article["jo"])
        result.append({"jo": article["jo"], "label": ref(article["jo"]), "title": article["title"],
                       "text": article["text"], "deleted": article["title"].strip() == "삭제",
                       "effective": article["effective"]})
    if not result:
        raise ValueError("Official response contains no articles")
    return result


def assert_public_body(official, public):
    fields = ("jo", "title", "text", "effective")
    projection = lambda articles: [{k: a.get(k, "") for k in fields} for a in articles]
    if projection(official) != projection(public):
        raise ValueError("Official current articles differ from the public site; public bodies were preserved")


def article_sha256(articles):
    """Canonical ordered jo/title/text/effective projection, UTF-8 JSON."""
    value = [{k: a.get(k, "") for k in ("jo", "title", "text", "effective")} for a in articles]
    return digest(json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def artifact(path, raw):
    return {"path": path, "bytes": len(raw), "sha256": digest(raw)}


def public_xml(raw, key):
    """History detail links echo OC; keep only a redacted XML and raw digest."""
    response_digest = digest(raw)
    for value in {key, quote(key, safe=""), quote_plus(key), html.escape(key)}:
        if value:
            raw = raw.replace(value.encode("utf-8"), b"[REDACTED]")
    return raw, {"response_sha256": response_digest, "credential_values_redacted": digest(raw) != response_digest}


def collect_one(entry, public_doc, key, as_of, request=request_xml):
    query = parse_qs(urlsplit(entry["url"]).query)
    mst = query.get("lsiSeq", [""])[0]
    effective = valid_date(entry["effective"])
    if not mst.isdigit() or query.get("efYd") != [effective]:
        raise ValueError("Public edition is not pinned by MST and effective date")
    params = {"target": "eflaw", "MST": mst, "efYd": effective}
    current_root, current_raw = request("lawService.do", key, params)
    current_raw, current_transport = public_xml(current_raw, key)
    current = identity(current_root, mst)
    if current["name"] != entry["name"] or current["effective"] != effective:
        raise ValueError("Current official response does not match the public edition")
    current_articles = body_articles(current_root, current)
    assert_public_body(current_articles, public_doc["articles"])
    current["text_sha256"] = article_sha256(current_articles)
    files = {f"sources/{entry['id']}-current.xml": current_raw}
    current["xml"] = {**artifact(next(iter(files)), current_raw), **current_transport}
    rows, list_refs, total = [], [], None
    for page in range(1, 21):
        params = {"target": "eflaw", "LID": current["law_id"], "nw": "1,3", "sort": "efdes",
                  "efYd": "19480101~" + effective, "display": 100, "page": page}
        root, raw = request("lawSearch.do", key, params)
        raw, transport = public_xml(raw, key)
        page_rows = history_rows(root)
        page_total = int(root.findtext("totalCnt", "-1"))
        if total is None:
            total = page_total
        if page_total != total or int(root.findtext("page", "0")) != page:
            raise ValueError("History pagination changed during collection")
        path = f"sources/{entry['id']}-history-{page}.xml"
        files[path] = raw
        list_refs.append({**artifact(path, raw), **transport})
        rows.extend(page_rows)
        if len(rows) == total:
            break
        if len(page_rows) != 100 or len(rows) > total:
            raise ValueError("Incomplete history pagination")
    else:
        raise ValueError("History exceeds the bounded complete-search limit")
    previous_row = select_previous(rows, current, as_of)
    old_root, old_raw = request("lawService.do", key, {"target": "eflaw", "MST": previous_row["mst"],
                                                    "efYd": previous_row["effective"]})
    old_raw, previous_transport = public_xml(old_raw, key)
    previous = identity(old_root, previous_row["mst"])
    check_identity(previous, previous_row)
    previous_articles = body_articles(old_root, previous)
    previous["text_sha256"] = article_sha256(previous_articles)
    old_path = f"sources/{entry['id']}-previous.xml"
    files[old_path] = old_raw
    previous["xml"] = {**artifact(old_path, old_raw), **previous_transport}
    old_by_jo = {a["jo"]: a for a in previous_articles}
    new_by_jo = {a["jo"]: a for a in current_articles}
    changed = [jo for jo in new_by_jo if jo not in old_by_jo or new_by_jo[jo]["text"] != old_by_jo[jo]["text"]]
    removed = [jo for jo in old_by_jo if jo not in new_by_jo]
    provenance = {"provider": "국가법령정보센터 시행일 기준 Open API", "collected_at": as_of,
                  "selection": "immediately-prior-effective-edition", "guides": GUIDES,
                  "previous": previous, "current": current, "history_pages": list_refs,
                  "history_count": len(rows), "public_document_sha256": digest(encode(public_doc)),
                  "order_basis": "effective date, then promulgation date/number; MST size is not chronology"}
    meta = {"id": entry["id"], "name": entry["name"], "domain": "tax", "kind": "법률",
            "effective": previous["effective"], "url": previous["url"]}
    baseline = {"schema": 1, "kind": "delegation-baseline", "meta": meta,
                "built_at": f"{as_of[:4]}-{as_of[4:6]}-{as_of[6:]}", "articles": previous_articles,
                "details": {}, "evidence_availability": {"reverse_citations": "not-collected", "note": REVERSE_NOTICE},
                "provenance": provenance}
    baseline_path = f"baselines/{entry['id']}.json"
    files[baseline_path] = encode(baseline)
    current_path = f"current/{entry['id']}.json"
    files[current_path] = encode({"schema": 1, "meta": {**meta, "effective": effective, "url": current["url"]},
                                 "articles": current_articles})
    row = {"id": entry["id"], "name": entry["name"], "current": current, "previous": previous,
           "baseline": artifact(baseline_path, files[baseline_path]), "current_snapshot": artifact(current_path, files[current_path]),
           "history_pages": list_refs, "history_count": len(rows), "changed_article_ids": changed,
           "removed_article_ids": removed, "reverse_citations": "not-collected"}
    # Reject even an unexpected server echo of authentication before any writes.
    if key and any(key.encode("utf-8") in raw for raw in files.values()):
        raise ValueError("Server response contains an authentication value; output refused")
    return row, files


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args(argv)
    source, destination = args.site.resolve(), args.destination.resolve()
    if source != ROOT and ROOT not in source.parents or ROOT not in destination.parents:
        raise ValueError("Source and destination must stay inside this repository")
    if destination.exists():
        raise ValueError("Immutable output requires a new destination")
    key = os.environ.get("LAW_API_KEY") or os.environ.get("LAW_OC")
    if not key:
        from config import LAW_API_KEY
        key = LAW_API_KEY
    if not key:
        raise ValueError("LAW_API_KEY or LAW_OC is required")
    manifest_raw = (source / "manifest.json").read_bytes()
    manifest = json.loads(manifest_raw)
    storage = Storage(source, manifest)
    tax = next(d for d in manifest["domains"] if d["id"] == "tax")
    catalog = storage.read(tax["catalog"])
    as_of = date.today().strftime("%Y%m%d")
    result, files = [], {}
    for name in NAMES:
        entries = [e for e in catalog["laws"] if e["name"] == name]
        if len(entries) != 1:
            raise ValueError("Public tax identity is missing or duplicated: " + name)
        entry = entries[0]
        doc = storage.read(entry["file"])
        if doc["meta"]["id"] != entry["id"] or doc["meta"]["name"] != name:
            raise ValueError("Public document/catalog identity mismatch")
        row, collected = collect_one(entry, doc, key, as_of)
        result.append(row)
        files.update(collected)
        print(name + ": verified " + row["previous"]["effective"] + " -> " + row["current"]["effective"], flush=True)
    output = {"schema": 1, "kind": "tax-delegation-history", "built_at": date.today().isoformat(),
              "public_manifest_sha256": digest(manifest_raw), "public_site": source.relative_to(ROOT).as_posix(),
              "laws": result, "scope": "three statute bodies; historical reverse citations not collected"}
    files["manifest.json"] = encode(output)
    # All three laws must pass before publishing any output.
    destination.mkdir(parents=True, exist_ok=False)
    for relative, raw in files.items():
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(raw)
    print("Verified immutable history bundle: " + destination.name)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, ET.ParseError) as exc:
        # request_xml replaces network exceptions before they reach this point.
        raise SystemExit(str(exc)) from None
