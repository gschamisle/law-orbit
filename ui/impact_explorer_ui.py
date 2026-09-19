"""Additive exploration screen; the uploaded-bill review workflow is untouched."""
from __future__ import annotations

import json

import streamlit as st
import streamlit.components.v1 as components

from core.impact_explorer import analyze
from core.law_universe import graph_path, load_graph
from core.impact_galaxy import LABELS, build
from core.law_galaxy import render_html, render_page


@st.cache_data(show_spinner=False)
def _snapshot(stamp: int) -> dict:
    return load_graph()


def render() -> None:
    graph = _snapshot(graph_path().stat().st_mtime_ns)
    mode = st.radio("탐색 방식", ["기존 인용 탐색", "신설 항 범위 재검토"], horizontal=True, key="impact_mode")
    if mode == "신설 항 범위 재검토":
        from ui.boundary_review_ui import render as render_boundary
        render_boundary(graph)
        return
    st.caption("개정하려는 조문을 선택하면 직접 인용·상위 조문 인용·범위 포함을 근거와 함께 구분합니다.")
    laws = sorted(graph.get("laws", []))
    with st.form("impact_target", border=False):
        left, right, button = st.columns([3, 3, 1], vertical_alignment="bottom")
        law = left.selectbox("법령", laws, index=laws.index("법인세법") if "법인세법" in laws else 0)
        reference = right.text_input("개정 대상", "제16조제2항제1호")
        submitted = button.form_submit_button("영향 탐색", type="primary", width="stretch")
    if submitted or "impact_selection" not in st.session_state:
        try:
            st.session_state["impact_selection"] = analyze(law, reference, graph)
        except ValueError as exc:
            st.error(str(exc))
            return
    result = st.session_state["impact_selection"]
    st.markdown(f"#### {result['law']} {result['reference']}")
    st.caption(f"그래프 생성일 {result['built_at']} · 수록 법령 {len(result['laws'])}개 · 현재 시행 중인 조문의 존재 여부는 별도 확인이 필요합니다.")
    cols = st.columns(5)
    for col, status in zip(cols, ("exact", "range", "covering", "contained", "review")):
        col.metric(LABELS[status] + " 문구", result["counts"].get(status, 0))
    galaxy = build(result)
    components.html(render_html(galaxy, 740), height=760, scrolling=False)
    st.caption("화살표는 인용하는 조문 → 인용받는 조문 방향입니다. 문맥 확인 항목도 지도에 포함합니다. 같은 조 내부의 항목은 아래 근거 목록에서 확인하세요.")
    st.info("이 결과는 함께 개정할지 검토할 후보입니다. 인용이 있다는 사실만으로 개정 필요성을 확정하지 않습니다. 저장 데이터에 인용 주변의 단서·제외 문구나 출처 항·호가 없으면 여기서 복원할 수 없습니다.")
    selected = st.multiselect("근거 목록", list(LABELS), default=[k for k in LABELS if k != "disjoint"], format_func=LABELS.get)
    rows = [r for r in result["rows"] if r["status"] in selected]
    st.caption(f"표시 {len(rows)}개 문구 · 항·호 불일치 {result['counts'].get('disjoint', 0)}개 문구는 필터에서 확인할 수 있습니다.")
    for row in rows:
        base, _, sub = str(row["source_jo"]).partition("의")
        source_label = f"제{base}조" + (f"의{sub}" if sub else "") if base.isdigit() else str(row["source_jo"])
        with st.expander(f"{LABELS[row['status']]} · {row['source_law']} {source_label} · {row['source_title']}"):
            st.code(row["raw"], language=None)
            st.write(row["reason"])
            st.caption("출처 위치: 조 단위 · 인용 주변 문맥과 현행본은 후속 검증 대상")
    a, b = st.columns(2)
    a.download_button("영향 은하 저장", render_page(galaxy).encode("utf-8"), "조문영향은하.html", "text/html")
    b.download_button("근거 목록 저장", json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8"), "조문영향근거.json", "application/json")
