"""국세 은하 — 수집 본문과 조문 연결 탐색.

발표 후 공개된 정보만 다루므로 LLM도 API 키도 필요 없다. 인용 그래프만 읽는다.
"""
from __future__ import annotations

import json
import streamlit as st
import streamlit.components.v1 as components

from core import law_abbrev
from core.law_universe import SOURCES
from ui.law_library_ui import render as render_library


@st.cache_data(show_spinner=False, max_entries=8)
def _tax_document(path: str, stamp: tuple[int, int], law: str) -> dict | None:
    from pathlib import Path
    source = json.loads(Path(path).read_text(encoding='utf-8'))
    return next((d for d in source['laws'] if d['name'] == law), None)


@st.cache_data(show_spinner=False)
def _connected_galaxy_data(min_edge: int, max_articles: int, stamp: int, external: bool = True) -> dict:
    from core.law_galaxy import build

    from ui.impact_explorer_ui import _snapshot
    return build(min_edge=min_edge, max_articles_per_law=max_articles, include_external=external, graph=_snapshot(stamp))


@st.cache_data(show_spinner=False)
def _focus(law: str, reference: str, stamp: int) -> dict:
    from core.galaxy_focus import analyze_focus
    from ui.impact_explorer_ui import _snapshot
    return analyze_focus(law, reference, graph=_snapshot(stamp))


def _render_galaxy() -> None:
    from core.galaxy_focus import DIRECTIONS, KINDS, build, visible_rows
    from core.law_universe import graph_path
    from core.law_galaxy import render_html, render_page
    from ui.impact_explorer_ui import _snapshot

    stamp = graph_path().stat().st_mtime_ns
    graph = _snapshot(stamp)
    tax_laws = set(graph.get('tax_laws',graph.get('laws',[])))
    laws = sorted(graph.get("laws", []), key=lambda n:(n not in tax_laws,n))
    law_entry, reference_entry = st.columns([1, 1], vertical_alignment='bottom')
    with law_entry:
        law = st.selectbox("법령 선택", laws, key="lm_focus_law",
                           index=laws.index("법인세법") if "법인세법" in laws else 0)
    document = None
    if 'source' in graph:
        document = next((d for d in graph['source']['laws'] if d['name'] == law), None)
    elif SOURCES.is_file():
        stat = SOURCES.stat()
        document = _tax_document(str(SOURCES), (stat.st_mtime_ns, stat.st_size), law)
    picked = render_library(document, prefix='lm_', default_reference=st.session_state.get('lm_focus_ref', '제16조'))
    if picked:
        st.session_state['lm_focus_ref'] = picked
    previous = st.session_state.get('lm_focus_selection')
    if previous and previous[0] != law:
        st.session_state.pop('lm_focus_selection', None)
        st.session_state.pop('lm_focus_error', None)
    with reference_entry:
        with st.form("lm_focus_form", border=False):
            entry, action = st.columns([4, 1.5], vertical_alignment='bottom')
            reference = entry.text_input("조문 번호", "제16조", key="lm_focus_ref",
                                        help="수집 본문에서 고르거나 제16조제2항제1호처럼 직접 입력하세요.")
            with action:
                submitted = st.form_submit_button("연결 탐색", key="lm_focus_run", type='primary', width='stretch')
    if submitted or picked:
        st.session_state.pop("lm_focus_selection", None)
        st.session_state.pop("lm_focus_error", None)
        try:
            result = _focus(law, reference, stamp)
            st.session_state["lm_focus_selection"] = (result["law"], result["reference"])
        except ValueError as exc:
            st.session_state["lm_focus_error"] = str(exc)
    if st.session_state.get("lm_focus_selection"):
        if st.button("전체 은하로 돌아가기", key="lm_focus_clear"):
            st.session_state.pop("lm_focus_selection", None)
    if st.session_state.get("lm_focus_error"):
        st.error(st.session_state["lm_focus_error"])

    selection = st.session_state.get("lm_focus_selection")
    result = _focus(*selection, stamp) if selection else None
    direction, review, broad = "both", True, False
    kinds = list(KINDS)
    if result:
        st.markdown(f"#### {result['law']} {result['reference']}의 연결")
        direction = st.radio("연결 방향", list(DIRECTIONS), format_func=DIRECTIONS.get,
                             horizontal=True, key="lm_focus_direction")
        if result["narrow"]:
            st.info("역인용의 범위와 나가는 인용의 출처 항·호·목을 대조합니다. 상위 단위의 공통 문구와 한정·제외 조건은 점선으로 표시합니다.")
    with st.expander("연결 설정"):
        external = st.checkbox("외부 법령 연결 포함", True, key='lm_external',
                               help='국세 법령과 직접 연결된 상법·자본시장법 등 외부 법령을 함께 봅니다.')
        if result:
            review = st.checkbox("문맥·출처 확인 후보 포함", True, key="lm_focus_review")
            if result.get('broad_rows'):
                broad = st.checkbox("법령 전체를 참조하는 역인용 후보 포함", False, key='lm_broad')
            kinds = st.multiselect('연결 종류', list(KINDS), default=list(KINDS), format_func=KINDS.get, key='lm_kinds')
        st.caption('전체 지도는 주요 연결을 표시합니다. 법령·조문을 선택하면 드문 연결까지 펼쳐집니다.')
    min_edge, max_arts = 8, 220
    data = _connected_galaxy_data(min_edge, max_arts, stamp, external)
    if result:
        filters = dict(external=external,kinds=kinds,include_broad=broad)
        data = build(result, data, direction, review, **filters)
        rows = visible_rows(result, direction, review, **filters)
        c1, c2, c3 = st.columns(3)
        c1.metric("연결된 대상", data["neighbor_count"])
        c2.metric("인용 문구", sum(r["direction"] == "forward" for r in rows))
        c3.metric("역인용 문구", sum(r["direction"] == "reverse" for r in rows))
        if not rows:
            st.info("현재 조건에 맞는 저장 인용이 없습니다. 연결이 없거나 조문이 존재하지 않는다는 뜻은 아닙니다.")
    components.html(render_html(data, height=740), height=760, scrolling=False)
    st.download_button("은하 내려받기",
                       render_page(data).encode("utf-8"), "국세 은하-조문연결.html" if result else "국세 은하.html",
                       "text/html", key="lm_g_dl")
    if result:
        st.caption("민트: 선택 조문 → 인용 대상 · 금색: 인용 출처 → 선택 조문 · 분홍 점선: 문맥·출처 확인. "
                   "점을 선택하면 원문 문맥과 시행일을 봅니다. 조문·법령 전체·별표·기준은 각각 구분합니다.")
        st.caption(f"{result['built_at']} 생성 자료 · {len(result['laws'])}개 법령 · "
                   "직접 연결만 표시하며, 연결 유무가 연계개정 필요성을 확정하지는 않습니다.")
        with st.expander(f"강조된 연결의 인용 근거 {len(rows)}개"):
            table = [{"방향": r["direction_label"], "인용 출처": r["source_law"] + " " + r["source_ref"],
                      "대상": r["target_law"] + " " + r["target_ref"], "저장 참조 번호": r["target_ref_recorded"],
                      "인용 문구": r["raw"], "구분": r["precision"], "확인 내용": r["reason"],
                      '원문 문맥':r.get('context',''), '출처 시행일':r.get('source_effective',''),
                      '원문 링크':r.get('source_url','')} for r in rows]
            st.dataframe(table, hide_index=True, width="stretch")
            st.download_button("인용 근거 내려받기", json.dumps({**result, "rows": rows,
                               "direction": direction, "include_review": review, 'filters':filters}, ensure_ascii=False, indent=2).encode("utf-8"),
                               "조문연결근거.json", "application/json", key="lm_focus_evidence")
        with st.expander("조회 범위와 표시에서 제외된 항목"):
            st.write(result["coverage_note"])
            st.write(f"항·호 범위 불일치 {result['disjoint_count']}개 · 같은 조 내부 참조 {result['same_article_count']}개. "
                     "같은 조 내부 참조는 지도에서 제외합니다.")
            if result["unplaced"]:
                st.write("참조 번호를 해석하지 못한 나가는 인용은 아래에 남겼습니다.")
                st.dataframe(result["unplaced"], hide_index=True)
    else:
        st.caption("한 손가락·드래그로 회전 · 두 손가락·휠로 확대 · 점을 선택해 연결 확인")


def _source_info(graph: dict) -> None:
    tax_laws = set(graph.get('tax_laws', graph.get('laws', [])))
    laws = graph.get('laws', [])
    st.caption(f"수집 기준 {graph['built_at']} · 국세 법령 {len(tax_laws)}개 · 외부 법령 {len(laws)-len(tax_laws)}개")
    st.caption('국세 법령과 인용·역인용이 확인된 외부 법령만 기본 지도에 표시합니다. 숨긴 법령의 수집 본문은 보관합니다.')
    st.caption('법령 약칭은 세제개편안 상세본의 표기를 따릅니다. 표시 거리는 법적 영향의 크기를 뜻하지 않습니다.')
    if graph.get('catalog'):
        with st.expander(f"수록 범위 · 국세 법령 {len(tax_laws)}개 + 외부 법령 {len(laws)-len(tax_laws)}개"):
            st.write(graph.get('coverage_note',''))
            st.caption(f"수집일 {graph['built_at']} · 국가법령정보센터 시행일 기준 본문. 매일 새 시행 여부 확인 · 월요일 전체 갱신(노트북과 Codex 실행 중).")
            st.dataframe([{'법령':l['name'], '구분':'국세 법령' if l['category']=='tax' else '외부 법령',
                           '시행일':l['effective'], '공포일':l.get('promulgated','')} for l in graph['catalog']],
                         hide_index=True, width='stretch')
            if graph.get('outside_scope'):
                st.caption('아직 수록하지 않은 법령의 언급입니다. 아래 법령과의 연결은 현재 지도에 포함되지 않습니다.')
                st.dataframe([{'미수록 법령':r['law'],'언급 수':r['mentions'],'예시':r['example']}
                              for r in graph['outside_scope'][:20]], hide_index=True, width='stretch')


def render(law_api_key: str = "", openai_api_key: str = "") -> None:
    from core.law_universe import graph_path
    from ui.impact_explorer_ui import _snapshot
    views = ['법령 은하 (3D)', '조문 영향 탐색']
    if st.session_state.get('lm_view') not in views:
        st.session_state['lm_view'] = views[0]
    heading, info = st.columns([5, 1], vertical_alignment='center')
    with heading:
        view = st.radio('탐색 방식', views, horizontal=True, key='lm_view', label_visibility='collapsed',
                        format_func=lambda v: {'법령 은하 (3D)':'3D 은하', '조문 영향 탐색':'조문 영향 탐색'}[v])
    with info:
        with st.popover('자료 안내', width='stretch'):
            _source_info(_snapshot(graph_path().stat().st_mtime_ns))
    if view == '조문 영향 탐색':
        from ui.impact_explorer_ui import render as render_impact
        render_impact()
    else:
        _render_galaxy()
