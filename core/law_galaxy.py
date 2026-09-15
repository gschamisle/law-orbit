"""법령 은하 — 32개 법령을 중심 노드로 둔 3D 관계도 (자체 완결 HTML).

법령군을 3D 공간에 흩고, 각 법령을 그 군의 궤도에, 조문을 다시 법령 주위에 둔다.
법령군 간 인용만 호(arc)로 잇는다 — 시행령→모법은 위임 구조상 당연해서 그리면
나머지를 덮는다.

**외부 라이브러리를 쓰지 않는다.** 캔버스에 회전·원근 투영을 직접 계산한다.
CDN을 물면 폐쇄망·오프라인·Artifacts(CSP)에서 통째로 깨지는데, 이 도구가 놓일
자리가 대개 그런 곳이다. 좌표는 파이썬이 결정적으로 계산해 JSON으로 심는다 —
브라우저에서 난수를 돌리면 열 때마다 그림이 달라진다.
"""
from __future__ import annotations

import json
from functools import lru_cache
import math
from collections import Counter, defaultdict
from pathlib import Path

from core import law_abbrev
from core.law_map import family
from core.law_universe import load_graph, norm as normalize

ROOT = Path(__file__).resolve().parents[1]
_GRAPH = ROOT / "data" / "law-citation-graph.json"

_FAMILY_COLOR: dict[str, str] = {
    "소득세법": "#5b8cff", "법인세법": "#3ddc84", "부가가치세법": "#ffb03a",
    "상속세 및 증여세법": "#c084fc", "조세특례제한법": "#ff6b8a",
    "국제조세조정에 관한 법률": "#2dd4bf", "관세법": "#fbbf24",
    "국세기본법": "#94a3b8", "국세징수법": "#cbd5e1",
    "농어촌특별세법": "#f472b6", "종합부동산세법": "#60a5fa",
    "증권거래세법": "#a78bfa", "개별소비세법": "#fb923c", "교육세법": "#fcd34d",
    "주세법": "#fb7185", "교통ㆍ에너지ㆍ환경세법": "#34d399", "인지세법": "#93c5fd",
}
_TIER = {"": 0, "시행령": 1, "시행규칙": 2}      # 모법 → 령 → 칙 순으로 바깥 궤도


def _tier(law_name: str) -> int:
    for suffix, idx in (("시행규칙", 2), ("시행령", 1)):
        if law_name.endswith(suffix):
            return idx
    return 0


def build(min_edge: int = 8, max_articles_per_law: int = 220, include_external: bool = True) -> dict:
    """법령·조문 좌표와 법령군 간 인용 엣지.

    조문은 법령당 상한을 둔다. 조특령(450조)까지 전부 찍으면 점이 뭉쳐 은하가
    아니라 얼룩이 된다 — 연결이 많은 조문부터 남긴다.
    """
    graph = load_graph()
    edges = graph['edges']
    catalog = {l['name']:l for l in graph.get('catalog',[])}
    tax_laws = set(graph.get('tax_laws',graph.get('laws',[])))

    # 인용 원문의 표기 흔들림('소득세법 ', '소득세법시행령')이 별도 노드가 되지
    # 않도록 추적 목록의 정식 명칭으로 맞춘다. 목록에 없는 법령(지방세법 등)은
    # 조문 데이터가 없어 점을 찍을 수 없으므로 노드로 만들지 않는다.
    canonical = {
        normalize(name): name for name in graph.get('laws',[])
        if include_external or name in tax_laws
    }

    def norm(name: str) -> str:
        return canonical.get(normalize(name), "")

    laws: Counter[str] = Counter({name:0 for name in canonical.values()})
    degree: dict[str, Counter[str]] = defaultdict(Counter)
    pair: Counter[tuple[str, str]] = Counter()
    for e in edges:
        a, b = norm(e.get("source_law", "")), norm(e.get("target_law", ""))
        if not a or not b:
            continue
        laws[a] += 1
        laws[b] += 0
        degree[a][str(e.get("source_jo", ""))] += 1
        if a != b:
            pair[(a, b)] += 1

    names = sorted(laws)
    fams = sorted({family(n) for n in names})
    fam_index = {f: i for i, f in enumerate(fams)}

    # 법령군을 구(球) 위에 균등 배치 — 황금각이라 개수가 바뀌어도 고르게 퍼진다
    nodes: list[dict] = []
    positions: dict[str, tuple[float, float, float]] = {}
    for name in names:
        fam = family(name)
        outer = name not in tax_laws
        ring = sorted({family(l) for l in names if (l not in tax_laws) == outer})
        i = ring.index(fam)
        n = len(ring)
        y = 1 - 2 * (i + 0.5) / n
        rad = math.sqrt(max(0.0, 1 - y * y))
        theta = math.pi * (3 - math.sqrt(5)) * i
        fx, fy, fz = math.cos(theta) * rad, y, math.sin(theta) * rad
        # 같은 군의 모법·령·칙은 중심에서 밖으로 계단 배치
        t = _tier(name)
        scale = (445 if outer else 255) + t * (32 if outer else 35)
        jitter = 0.10 * t
        x = fx * scale + math.cos(theta + jitter) * 26 * t
        yy = fy * scale + jitter * 34
        z = fz * scale + math.sin(theta + jitter) * 26 * t
        positions[name] = (x, yy, z)
        nodes.append({
            "id": name,
            "label": law_abbrev.law(name),
            "family": fam,
            "category": 'external' if outer else 'tax',
            "title": ('외부 법령 · 세법과의 연결' if outer else '세법령') + ' · 시행일 ' + catalog.get(name,{}).get('effective','확인 필요'),
            "color": _FAMILY_COLOR.get(fam, "#8fa3bf"),
            "tier": t,
            "count": laws[name],
            "x": round(x, 1), "y": round(yy, 1), "z": round(z, 1),
        })

    # 조문 — 소속 법령 주위 구면에 결정적으로 배치
    dust: list[dict] = []
    for name in names:
        top = [jo for jo, _n in degree[name].most_common(max_articles_per_law)]
        cx, cy, cz = positions[name]
        color = _FAMILY_COLOR.get(family(name), "#8fa3bf")
        for k, jo in enumerate(sorted(top, key=lambda s: (len(s), s))):
            y = 1 - 2 * (k + 0.5) / max(len(top), 1)
            rad = math.sqrt(max(0.0, 1 - y * y))
            th = math.pi * (3 - math.sqrt(5)) * k
            r = 46 + (k % 7) * 5
            dust.append({
                "x": round(cx + math.cos(th) * rad * r, 1),
                "y": round(cy + y * r, 1),
                "z": round(cz + math.sin(th) * rad * r, 1),
                "c": color,
                "law": law_abbrev.law(name),
                "law_id": name,
                "jo": law_abbrev.jo_key(jo),
            })

    links = [
        {"a": a, "b": b, "n": n}
        for (a, b), n in sorted(pair.items(), key=lambda kv: -kv[1])
        if n >= min_edge and family(a) != family(b)
    ]
    return {
        "nodes": nodes, "dust": dust, "links": links, "families": fams,
        "all_links": [{"a": a, "b": b, "n": n} for (a, b), n in sorted(pair.items())],
        "built_at": graph.get('built_at',''),
        "mode": "overview",
    }


@lru_cache(maxsize=1)
def _font_styles() -> str:
    """Bundle the original fonts and license so standalone exports stay offline."""
    import base64
    from html import escape

    font_dir = ROOT / "ui/assets/fonts"
    faces = []
    for name, weight in (("Regular", 400), ("Bold", 700)):
        encoded = base64.b64encode((font_dir / f"NanumMyeongjo-{name}.ttf").read_bytes()).decode("ascii")
        faces.append(f"@font-face{{font-family:'Nanum Myeongjo';font-style:normal;font-weight:{weight};"
                     f"font-display:swap;src:url(data:font/ttf;base64,{encoded}) format('truetype');}}")
    license_text = escape((font_dir / "OFL.txt").read_text(encoding="utf-8"))
    return "<pre hidden id='galaxy-font-license'>" + license_text + "</pre><style>" + "".join(faces) + "</style>"


def render_html(data: dict, height: int = 720) -> str:
    """Offline canvas renderer; JSON is escaped for an HTML script context."""
    template = (ROOT / "ui/assets/law_galaxy.html").read_text(encoding="utf-8")
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return _font_styles() + template.replace("__H__", str(max(620, int(height)))).replace("__DATA__", payload)


def render_page(data: dict, height: int = 800) -> str:
    return (
        "<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>세법 은하 · 조문 영향 탐색</title>"
        "<style>body{margin:0;background:#040914;padding:16px}</style></head><body>"
        + render_html(data, height) + "</body></html>"
    )
