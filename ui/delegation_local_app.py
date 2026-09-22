"""Optional standalone entry point for the local draft-review screen."""
import streamlit as st
from ui.styles import inject_global_css
from ui.delegation_review_ui import render

st.set_page_config(page_title='법의 궤도 · 로컬 후속 개정 점검', page_icon='✦', layout='wide')
inject_global_css()
st.title('후속 개정 점검')
st.caption('법의 궤도 · 내부 개정안의 위임사항과 하위법령 인용을 함께 검토합니다.')
render()
