"""세법 관계도 탭 — 법령 은하(3D)와 조문 관계도(2D).

발표 후 공개된 정보만 다루므로 LLM도 API 키도 필요 없다. 인용 그래프만 읽는다.
"""
from __future__ import annotations

import json
import streamlit as st
import streamlit.components.v1 as components

from core import law_abbrev


@st.cache_data(show_spinner=False)
def _galaxy_data(min_edge: int, max_articles: int, stamp: int, external: bool = True) -> dict:
    from core.law_galaxy import build

    return build(min_edge=min_edge, max_articles_per_law=max_articles, include_external=external)


@st.cache_data(show_spinner=False)
def _focus(law: str, reference: str, stamp: int) -> dict:
    from core.galaxy_focus import analyze_focus
    return analyze_focus(law, reference)


def _render_galaxy() -> None:
    from core.galaxy_focus import DIRECTIONS, KINDS, build, visible_rows
    from core.impact_explorer import GRAPH
    from core.law_galaxy import render_html, render_page
    from ui.impact_explorer_ui import _snapshot

    stamp = GRAPH.stat().st_mtime_ns
    graph = _snapshot(stamp)
    tax_laws = set(graph.get('tax_laws',graph.get('laws',[])))
    laws = sorted(graph.get("laws", []), key=lambda n:(n not in tax_laws,n))
    external = st.checkbox("외부 법령 연결 함께 보기", True, key='lm_external',
                           help='상법·자본시장법·민법·중소기업·회생·주택·금융 관련 법령과 세법 사이의 연결을 표시합니다.')
    with st.form("lm_focus_form"):
        a, b = st.columns([3, 4])
        law = a.selectbox("개정할 법령", laws, key="lm_focus_law",
                          index=laws.index("법인세법") if "법인세법" in laws else 0)
        reference = b.text_input("조문 번호", "제16조", key="lm_focus_ref",
                                 help="16, 16의2 또는 제16조제2항제1호처럼 입력하세요.")
        submitted = st.form_submit_button("조문 연결 보기", key="lm_focus_run")
    if submitted:
        st.session_state.pop("lm_focus_selection", None)
        st.session_state.pop("lm_focus_error", None)
        try:
            result = _focus(law, reference, stamp)
            st.session_state["lm_focus_selection"] = (result["law"], result["reference"])
        except ValueError as exc:
            st.session_state["lm_focus_error"] = str(exc)
    if st.session_state.get("lm_focus_selection"):
        if st.button("조문 선택 해제 · 전체 은하로", key="lm_focus_clear"):
            st.session_state.pop("lm_focus_selection", None)
    if st.session_state.get("lm_focus_error"):
        st.error(st.session_state["lm_focus_error"])

    selection = st.session_state.get("lm_focus_selection")
    result = _focus(*selection, stamp) if selection else None
    direction, review, broad = "both", True, False
    kinds = list(KINDS)
    if result:
        st.markdown(f"#### {result['law']} {result['reference']}의 연결")
        direction = st.radio("강조할 방향", list(DIRECTIONS), format_func=DIRECTIONS.get,
                             horizontal=True, key="lm_focus_direction")
        review = st.checkbox("문맥·출처 확인이 필요한 연결도 점선으로 보기", True, key="lm_focus_review")
        if result.get('broad_rows'):
            broad = st.checkbox(f"이 법령 전체를 참조하는 역인용 후보 {len(result['broad_rows'])}개도 보기", False,
                                key='lm_broad', help='특정 조문과의 연결을 확정하지 않은 넓은 후보입니다.')
        if result["narrow"]:
            st.info("역인용의 범위와 나가는 인용의 출처 항·호·목을 대조합니다. 상위 단위의 공통 문구와 한정·제외 조건은 점선으로 표시합니다.")
    with st.expander("은하 표시 설정"):
        if result:
            kinds = st.multiselect('연결 종류', list(KINDS), default=list(KINDS), format_func=KINDS.get, key='lm_kinds')
        c1, c2 = st.columns(2)
        min_edge = c1.slider("표시할 최소 인용 건수", 2, 60, 8, key="lm_g_min",
                             help="전체 은하에 적용합니다. 조문 연결 보기에서는 한 건의 인용도 표시합니다.")
        max_arts = c2.slider("법령당 조문 점 수", 40, 450, 220, step=10, key="lm_g_arts")
    data = _galaxy_data(min_edge, max_arts, stamp, external)
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
    st.download_button("은하 HTML 내려받기 (파일 하나, 오프라인 동작)",
                       render_page(data).encode("utf-8"), "조문연결은하.html" if result else "법령은하.html",
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
        st.caption("드래그로 회전, 휠로 확대, 법령을 클릭하면 그 법령의 인용만 남습니다. "
                   "안쪽은 세법령, 바깥쪽은 외부 법령입니다. 위에서 조문을 입력하면 인용과 역인용 경로만 부각됩니다.")
    if graph.get('catalog'):
        with st.expander(f"수록 범위 · 세법령 {len(tax_laws)}개 + 외부 법령 {len(laws)-len(tax_laws)}개"):
            st.write(graph.get('coverage_note',''))
            st.caption(f"수집일 {graph['built_at']} · 국가법령정보센터 시행일 기준 본문. 자동 갱신 일정은 설정하지 않았습니다.")
            st.dataframe([{'법령':l['name'], '구분':'세법령' if l['category']=='tax' else '외부 법령',
                           '시행일':l['effective'], '공포일':l.get('promulgated','')} for l in graph['catalog']],
                         hide_index=True, width='stretch')
            if graph.get('outside_scope'):
                st.caption('아직 수록하지 않은 법령의 언급입니다. 아래 법령과의 연결은 현재 지도에 포함되지 않습니다.')
                st.dataframe([{'미수록 법령':r['law'],'언급 수':r['mentions'],'예시':r['example']}
                              for r in graph['outside_scope'][:20]], hide_index=True, width='stretch')


@st.cache_data(show_spinner=False)
def _flat_map(min_edge: int, cross_only: bool, stamp: int) -> tuple[str, list]:
    from core.law_map import build, render_svg, top_pairs

    data = build(min_edge=min_edge, cross_family_only=cross_only)
    return render_svg(data), top_pairs(data, 15)


def render(law_api_key: str = "", openai_api_key: str = "") -> None:
    st.markdown('<div class="mofe-section-header">세법 관계도</div>', unsafe_allow_html=True)
    st.caption(
        "세법령의 인용 관계를 은하에서 탐색합니다. 법령 전체를 둘러보거나, "
        "개정할 조문을 입력해 연결된 경로를 따라가세요."
    )

    view = st.radio(
        "보기", ["법령 은하 (3D)", "조문 영향 탐색", "법령 관계도 (평면)"],
        horizontal=True, key="lm_view", label_visibility="collapsed",
    )

    if view == "조문 영향 탐색":
        from ui.impact_explorer_ui import render as render_impact
        render_impact()
    elif view.startswith("법령 은하"):
        _render_galaxy()
    else:
        c1, c2 = st.columns([1, 2])
        min_edge = c1.slider("표시할 최소 인용 건수", 2, 80, 8, key="lm_f_min")
        cross = c2.checkbox(
            "법령군 간 인용만 (시행령→모법 제외)", value=True, key="lm_f_cross",
            help="끄면 조특령→조특법(2,728건) 같은 당연한 관계가 화면을 덮습니다",
        )
        from core.impact_explorer import GRAPH
        svg, pairs = _flat_map(min_edge, cross, GRAPH.stat().st_mtime_ns)
        st.markdown(svg, unsafe_allow_html=True)
        st.download_button("관계도 SVG 내려받기", data=svg.encode("utf-8"),
                           file_name="법령관계도.svg", mime="image/svg+xml", key="lm_f_dl")
        with st.expander(f"인용이 많은 법령쌍 {len(pairs)}건"):
            for a, b, n in pairs:
                st.markdown(f"- **{a} → {b}** · {n:,}건")

    st.divider()
    # 조문 단위 관계도(조문 연관 조회)는 지금 숨겨 둔 탭이라 여기서 안내하지 않는다 —
    # 없는 탭으로 보내는 문구가 되기 때문. ENABLE_WIP_TABS를 켜면 다시 살릴 것.
    st.caption(
        "법령 약칭은 재정경제부 세제개편안 상세본의 공식 약어를 따릅니다 "
        f"(예: {law_abbrev.law('소득세법 시행령')} {law_abbrev.article('제73조의2')})."
    )
