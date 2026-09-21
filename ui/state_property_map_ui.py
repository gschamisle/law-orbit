"""Separate national-property menu over the existing galaxy screen."""
import streamlit as st
from core.state_property_universe import BUNDLE,load_bundle
from core.state_property_collection import PROPERTY,SPECIAL
from core.state_property_special import TYPES
from ui.sector_map_ui import render as render_sector

PROFILE=dict(domain='state_property',prefix='property',title='국유재산',
    default_laws={'all':PROPERTY,'core':PROPERTY,'special':SPECIAL,'administration':'국유재산 용도폐지에 관한 지침'},
    default_refs={'all':'제3조','core':'제3조','special':'제4조','administration':'제1조'},
    outside_note='선택 분야 밖의 수집 조문입니다. 특례의 적용요건·기한·부칙은 각각의 원문에서 확인하세요.')

def render(law_api_key='',openai_api_key=''):
    render_sector(PROFILE,BUNDLE)
    if not BUNDLE.is_file():return
    try:register=load_bundle()['source']['special_cases']
    except (ValueError,KeyError,OSError):return
    with st.expander('국유재산 특례 목록 · 근거·유형·존속기한'):
        st.caption(register['note'])
        query=st.text_input('특례 근거 검색',key='property_special_query')
        kind=st.selectbox('특례 유형',['all',*TYPES],format_func=lambda x:TYPES.get(x,'전체'),key='property_special_type')
        rows=[r for r in register['rows'] if (not query or query.replace(' ','') in r['legal_text'].replace(' ','')) and (kind=='all' or kind in r['types'])]
        st.dataframe([{'연번':r['number'],'근거':r['legal_text'],'유형':r['type_text'],'별표상 기한':r['deadline_text'],
                       '대조 상태':r['reason'],'공식 원문':r.get('law_url',r['source_url'])} for r in rows],hide_index=True)
        for i,url in enumerate(register['annex_urls'],1):st.link_button(f'공식 별표 원본 {i}',url)
