"""Before/after paragraph review alongside the existing citation explorer."""
from __future__ import annotations

import json

import streamlit as st
import streamlit.components.v1 as components

from core import law_abbrev
from core.boundary_review import LABELS, example_result, paragraph_labels, review_append
from core.impact_galaxy import build
from core.law_galaxy import render_html, render_page


def _result_view(result: dict) -> None:
    change = result["change"]
    st.markdown(f"#### {result['law']} {result['reference']} · 신설 항 검토")
    if result.get("example"):
        st.info("가상 A법·B법으로 보는 작동 예시입니다. 실제 법령 분석 결과가 아닙니다.")
    st.caption(f"인용 자료: {result['built_at']} · 구조 자료: {change['before']['version']} → {change['after']['version']}")
    st.write(f"종전 {paragraph_labels(change['before_numbers'])} → 개정 후 {paragraph_labels(change['after_numbers'])}")
    if change["kind"] == "complex":
        st.warning("복합 변경입니다. 단순 신설에 따른 인용 범위 경고를 보류하고, 연결된 인용을 구조·문맥 확인 대상으로 표시합니다.")
        for issue in change["issues"]:
            st.caption(issue)
    elif change["kind"] == "none":
        st.info("입력된 조문에서 신설 항이 확인되지 않았습니다.")
    else:
        st.write(f"**신설: {paragraph_labels(change['added'])}** · 종전 마지막 항: 제{change['former_last']}항")
    st.caption(f"이 조문을 인용하는 {result['candidate_article_count']}개 조문의 {result['candidate_count']}개 문구만 대조했습니다. 우선순위는 인용 형태를 기준으로 하며, 내용상 유사도나 개정 필요성의 점수가 아닙니다.")
    columns = st.columns(4)
    for col, status in zip(columns, LABELS):
        col.metric(LABELS[status], result["counts"].get(status, 0))
    if change["kind"] == "append" and not result["counts"].get("scope_review"):
        st.info("저장 자료에서 끝 경계 재검토 후보를 찾지 못했습니다. 다른 유형의 인용이나 자료 밖 법령의 영향 여부는 별도 확인 대상입니다.")
    galaxy = build(result)
    components.html(render_html(galaxy, 740), height=760, scrolling=False)
    st.caption("주황 점선: 인용 범위 재검토 · 분홍 점선: 구조·문맥 확인 · 파란 실선: 문언상 신설 항 포함. 점선은 신설 항에 대한 직접 인용을 뜻하지 않습니다. 같은 조 내부 인용은 아래 목록에서 확인할 수 있습니다.")
    selected = st.multiselect("신설 항 검토 근거", list(LABELS),
                              default=["scope_review", "review", "covered"], format_func=LABELS.get,
                              key="boundary_filters")
    for row in result["rows"]:
        if row["status"] not in selected:
            continue
        title = f"{LABELS[row['status']]} · {row['source_law']} {law_abbrev.jo_key(str(row['source_jo']))}"
        with st.expander(title, expanded=row["status"] == "scope_review"):
            if row["priority"]:
                st.caption(row["priority"] + " · 인용 구조 기준")
            st.code(row["raw"], language=None, wrap_lines=True)
            st.write(row["reason"])
            if row["question"]:
                st.warning(row["question"])
            if row["cited_paragraphs"]:
                st.caption("인용 문구에서 읽은 종전 항 번호: " + paragraph_labels(row["cited_paragraphs"]) + " · 한정·제외가 있는 경우 실제 적용 범위와 다를 수 있습니다.")
            st.caption("출처: 조 단위 · 신설 항 내용과 인용 법령의 목적·단서를 함께 확인하세요.")
    with st.expander("비교에 사용한 조문 전체와 버전"):
        left, right = st.columns(2)
        for col, key in ((left, "before"), (right, "after")):
            col.caption(change[key]["version"])
            col.code(change[key]["text"], language=None, wrap_lines=True)
    st.caption(result["coverage_note"])
    a, b = st.columns(2)
    a.download_button("검토 결과 내려받기", render_page(galaxy).encode("utf-8"), "신설항-인용범위검토.html", "text/html", key="boundary_html")
    b.download_button("비교 원문과 근거 저장", json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8"), "신설항검토근거.json", "application/json", key="boundary_json")


def render(graph: dict) -> None:
    st.caption("개정 전후의 한 조문 전체를 비교합니다. 종전 마지막 항을 포함하던 범위·열거 인용을 찾아 신설 항도 포함할 취지인지 묻습니다.")
    if st.button("A법 제5항 신설 예시 보기", key="boundary_demo"):
        st.session_state["boundary_result"] = example_result()
    with st.form("boundary_form", border=False):
        laws = sorted(graph.get("laws", []))
        left, right = st.columns([3, 2])
        law = left.selectbox("비교할 법령", laws, index=laws.index("법인세법") if "법인세법" in laws else 0, key="boundary_law")
        reference = right.text_input("비교할 조", "제16조", key="boundary_reference")
        a, b = st.columns(2)
        before_version = a.text_input("개정 전 버전·시행일", "개정 전", key="boundary_before_version")
        after_version = b.text_input("개정 후 버전·법령안", "개정 후(안)", key="boundary_after_version")
        before = a.text_area("개정 전 조문 전체", height=220, key="boundary_before", placeholder="제16조(제목)\n① 첫 번째 항 내용\n② 두 번째 항 내용")
        after = b.text_area("개정 후 조문 전체", height=220, key="boundary_after", placeholder="제16조(제목)\n① 첫 번째 항 내용\n② 두 번째 항 내용\n③ 신설 항 내용")
        st.caption("조문 표제부터 마지막 항까지 넣어 주세요. 각 항은 새 줄에서 ①·② 또는 '제1항 내용'으로 시작합니다. 발췌문이나 개정 지시문만으로는 종전 마지막 항을 확인할 수 없습니다.")
        submitted = st.form_submit_button("신설 항 인용 범위 검토", type="primary", key="boundary_run")
    if submitted:
        # Invalid new input must not leave an unrelated previous result on screen.
        st.session_state.pop("boundary_result", None)
        try:
            st.session_state["boundary_result"] = review_append(law, reference, before, after, graph, before_version, after_version)
        except ValueError as exc:
            st.error(str(exc))
            return
    if result := st.session_state.get("boundary_result"):
        _result_view(result)
    else:
        st.info("개정 전·후 조문을 넣거나 가상 예시로 작동 방식을 확인하세요.")
