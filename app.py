"""이 조문 건드리면 다 죽는 거야 — 법령 연결 탐색과 개정안 검토."""
import streamlit as st
from config import LAW_API_KEY, OPENAI_API_KEY, ENABLE_HWPX_OUTPUT, ENABLE_DRAFT_TAB, ENABLE_WIP_TABS
from ui import (fsc_map_ui, law_map_ui, local_tax_map_ui, procurement_map_ui, housing_map_ui, environment_map_ui, amendment_review_ui, article_relations_ui,
                new_article_ui, stage1_draft, stage2_crossref, stage3_output)
from ui.styles import inject_global_css

APP_TITLE = '이 조문 건드리면 다 죽는 거야'
st.set_page_config(page_title=APP_TITLE, page_icon='✦', layout='wide', initial_sidebar_state='expanded')
inject_global_css()

pages = [('galaxy', '법령은하', None), ('review', '개정안 검토', amendment_review_ui)]
if ENABLE_WIP_TABS:
    pages += [('relations', '조문 연관 조회', article_relations_ui), ('new_article', '신설 조문 검토', new_article_ui)]
if ENABLE_DRAFT_TAB:
    pages += [('draft', '조문안 작성', stage1_draft), ('crossref', '초안 인용 확인', stage2_crossref)]
if ENABLE_HWPX_OUTPUT:
    pages.append(('output', 'HWPX 출력', stage3_output))
labels = {key: label for key, label, _ in pages}

with st.sidebar:
    st.markdown('''<div class="atlas-brand">
      <div class="atlas-orbit" aria-hidden="true"><i></i><b>✦</b></div>
      <div class="atlas-kicker">A LAW RELATION ATLAS</div>
      <div class="atlas-brand-name">이 조문 건드리면<br><em>다 죽는 거야</em></div>
      <p>작은 개정의 커다란 파장.</p>
    </div>''', unsafe_allow_html=True)
    page = st.radio('작업 메뉴', list(labels), format_func=labels.get, key='app_section', label_visibility='collapsed')
    st.markdown('<div class="atlas-sidebar-note">조문을 따라가면<br>다음에 살펴볼 법이 보입니다.</div>', unsafe_allow_html=True)
    with st.popover('자료 관리', width='stretch'):
        with st.container(key='atlas_data_tools'):
            st.markdown('<p class="atlas-data-copy">수집된 본문과 연결 지도는 오프라인에서도 볼 수 있습니다.<br>현행본 대조는 세법 추적 목록을 법제처와 비교합니다. 이 버튼은 저장 자료를 변경하지 않습니다.</p>', unsafe_allow_html=True)
            check = st.button('세법 현행본 대조', disabled=not bool(LAW_API_KEY), key='check_freshness', width='content')
            if not LAW_API_KEY:
                st.info('현행본 대조에는 법제처 API 연결 설정이 필요합니다.')
            if check:
                with st.spinner('현행본 확인 중…'):
                    try:
                        from core.law_freshness import compare_with_manifest, load_manifest
                        changes = compare_with_manifest(LAW_API_KEY) if load_manifest().get('laws') else []
                        st.session_state['law_freshness_changes'] = changes
                        st.session_state['law_freshness_done'] = True
                        st.session_state.pop('law_freshness_error', None)
                    except Exception:
                        st.session_state['law_freshness_error'] = True
            if st.session_state.get('law_freshness_error'):
                st.warning('현행본을 확인하지 못했습니다. API 연결 설정을 확인해 주세요.')
            elif st.session_state.get('law_freshness_done'):
                changes = st.session_state.get('law_freshness_changes', [])
                if changes:
                    st.warning('수집 판본과 다른 법령: ' + ', '.join(c['name'] for c in changes))
                else:
                    st.success('비교한 세법 추적 목록이 현행본과 일치합니다.')
    st.markdown('<div class="atlas-sidebar-footer"><span>●</span> 수집 자료로 탐색 중</div>', unsafe_allow_html=True)

# Keep page widgets mounted, like native tabs, so switching the sidebar does not
# discard uploaded files, unsubmitted forms, or either galaxy's independent state.
hidden = '\n'.join(f'.st-key-page_{key} {{ display: none !important; }}' for key in labels if key != page)
st.markdown('<style>' + hidden + '</style>', unsafe_allow_html=True)

with st.container(key='page_galaxy'):
    st.markdown('''<header class="atlas-hero"><div class="atlas-kicker">01 / EXPLORE THE CONNECTIONS</div>
      <h1>하나의 조문,<br class="atlas-mobile-break"><em> 이어지는 법령.</em></h1>
      <p>개정하기 전에, 이 조문이 연결한 세계부터 살펴보세요.</p>
    </header>''', unsafe_allow_html=True)
    tax, finance, local_tax, procurement, housing, environment = st.tabs(['세법', '금융법', '지방세', '조달·계약', '국토·건축·주택', '환경·화학안전'])
    with tax: law_map_ui.render(LAW_API_KEY, OPENAI_API_KEY)
    with finance: fsc_map_ui.render(LAW_API_KEY, OPENAI_API_KEY)
    with local_tax: local_tax_map_ui.render(LAW_API_KEY, OPENAI_API_KEY)
    with procurement: procurement_map_ui.render(LAW_API_KEY, OPENAI_API_KEY)
    with housing: housing_map_ui.render(LAW_API_KEY, OPENAI_API_KEY)
    with environment: environment_map_ui.render(LAW_API_KEY, OPENAI_API_KEY)

for key, label, module in pages[1:]:
    with st.container(key='page_' + key):
        if key == 'review':
            st.markdown('''<header class="atlas-hero"><div class="atlas-kicker">02 / REVIEW THE AMENDMENT</div>
              <h1>바꾸는 조문,<br class="atlas-mobile-break"><em> 놓치는 연결 없이.</em></h1>
              <p>개정안을 불러오고, 함께 살펴볼 인용과 대응 조문을 확인하세요.</p>
            </header>''', unsafe_allow_html=True)
        else:
            st.markdown(f'<header class="atlas-hero"><h1>{label}</h1></header>', unsafe_allow_html=True)
        module.render(LAW_API_KEY, OPENAI_API_KEY)
