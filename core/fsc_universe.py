"""Independent FSC data access; absence or invalid scope never falls back to tax."""
from __future__ import annotations
import json
from pathlib import Path
from core.citation_scope import classify
from core.galaxy_focus import _target

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'output/fsc-universe/bundle.json'


def validate_bundle(bundle: dict) -> dict:
    source, graph = bundle['source'], bundle['graph']
    laws = source['laws']
    rules = [r for r in source.get('administrative_rules',[]) if r.get('body_status') == 'indexed-administrative-text']
    documents = laws + rules
    names = {law['name'] for law in documents}
    if any(r.get('provider') != 'admrul' or r.get('category') != 'fsc' or not r.get('articles') for r in rules):
        raise ValueError('행정규칙의 조문 분석 상태가 올바르지 않습니다.')
    if (not names or len(names) != len(documents) or graph.get('domain') != 'fsc'
            or set(graph['laws']) != names or set(graph['focus_laws']) != names
            or any(law['category'] != 'fsc' or law.get('provider') != 'eflaw'
                   or law.get('body_status') != 'indexed-statute-text' for law in laws)):
        raise ValueError('금융위 전용 수집 범위와 일치하지 않는 데이터입니다.')
    if graph['built_at'] != source['built_at']:
        raise ValueError('금융위 본문과 그래프의 수집 기준일이 다릅니다.')
    if any(e['source_law'] not in names or e['target_law'] not in names for e in graph['edges']):
        raise ValueError('금융위 기본 지도에 수집 범위 밖 법령이 포함되어 있습니다.')
    if any(e['source_law'] not in names or e['target_law'] in names
           or e.get('target_status') not in ('not-collected','collected-not-indexed')
           or (e.get('target_status') == 'collected-not-indexed' and e['target_law'] not in {r['name'] for r in source.get('administrative_rules',[]) if not r.get('articles')})
           for e in graph.get('external_references', [])):
        raise ValueError('외부 인용의 미수집 상태를 확인할 수 없습니다.')
    return bundle


def load_bundle(path: Path = BUNDLE) -> dict:
    return validate_bundle(json.loads(Path(path).read_text(encoding='utf-8')))


def article_for(bundle: dict, law: str, reference: str) -> tuple[dict, dict]:
    target = _target(reference, allow_hyphen=True)
    document = next((l for l in bundle['source']['laws'] + bundle['source'].get('administrative_rules',[]) if l['name'] == law), None)
    article = next((a for a in document['articles'] if a['jo'] == target.jo), None) if document else None
    if article is None:
        raise ValueError('수집된 본문에서 해당 조문을 찾지 못했습니다. 법령명과 조문 번호를 확인하세요.')
    return document, article


def external_evidence(graph: dict, law: str, reference: str) -> list[dict]:
    target = _target(reference, allow_hyphen=True)
    return [e for e in graph.get('external_references', [])
            if e['source_law'] == law and e['source_jo'] == target.jo
            and classify(e['source_ref'], target, allow_hyphen=True)[0] != 'disjoint']


def present(data: dict) -> dict:
    return {**data, 'domain': 'fsc', 'galaxy_title': '금융법 은하'}
