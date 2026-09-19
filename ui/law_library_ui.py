"""Shared collected-law reader; the caller supplies its own domain's document."""
from __future__ import annotations
import streamlit as st
from core.galaxy_focus import _target
from core.law_library import article_label, matching_articles, provision_choices, official_url, collected_text


def render(document: dict | None, *, prefix: str, default_reference: str = '', remember=None) -> str | None:
    key = lambda name: prefix + name
    remember = remember or (lambda name, default: default)
    with st.expander('수집 본문에서 조문 찾기'):
        if not document:
            st.info('이 법령의 수집 본문이 없습니다.')
            return None
        changed = st.session_state.get(key('library_document'), document['name']) != document['name']
        if changed:
            st.session_state[key('library_query')] = ''
            for name in ('library_article', 'library_scope'):
                st.session_state.pop(key(name), None)
        st.session_state[key('library_document')] = document['name']
        restore = lambda name, default: default if changed else remember(name, default)
        effective = document.get('effective', '')
        date = f'{effective[:4]}.{effective[4:6]}.{effective[6:8]}' if len(effective) == 8 else effective
        st.caption(f"{document['name']} · 시행 {date or '확인 필요'} · 수집 조문 {len(document.get('articles', []))}개")
        url = official_url(document)
        if url:
            st.link_button('수집 판본의 공식 원문', url)
        query = st.text_input('조문 내용 검색', value=restore('library_query', ''), key=key('library_query'),
                              placeholder='조문 번호, 제목 또는 본문 단어', help='입력 후 Enter를 누르면 선택 법령 안에서 찾습니다.')
        articles = matching_articles(document, query)
        if not articles:
            st.info('일치하는 수집 조문이 없습니다. 검색어를 바꿔 보세요.' if query else '조문 단위로 수집된 본문이 없습니다.')
            return None
        by_jo = {str(a['jo']): a for a in articles}
        choices = list(by_jo)
        try:
            initial = _target(default_reference, allow_hyphen=True).jo
        except ValueError:
            initial = choices[0]
        desired = st.session_state.get(key('library_article'), restore('library_article', initial))
        if desired not in choices:
            st.session_state.pop(key('library_article'), None)
            desired = initial if initial in choices else choices[0]
        # Explicitly send the new value when a law/search changes the options.
        # Removing only the server key can leave the browser showing an old label.
        if st.session_state.get(key('library_article')) != desired:
            st.session_state[key('library_article')] = desired
        jo = st.selectbox('수집 조문 목록', choices, index=None, key=key('library_article'),
                          format_func=lambda n: article_label(by_jo[n]))
        article = by_jo[jo]
        st.caption(f'검색 결과 {len(articles)}개 · {article_label(article)}')
        with st.container(height=300):
            st.text(article.get('text', ''))
        scopes = provision_choices(article)
        scope = st.session_state.get(key('library_scope'), restore('library_scope', scopes[0]))
        if scope not in scopes:
            st.session_state.pop(key('library_scope'), None)
            scope = scopes[0]
        if st.session_state.get(key('library_scope')) != scope:
            st.session_state[key('library_scope')] = scope
        reference = st.selectbox('연결을 볼 범위', scopes, index=None, key=key('library_scope'),
                                 format_func=lambda ref: ref + (' 전체' if ref == scopes[0] else ''))
        chosen = st.button('이 조문 연결 탐색', key=key('library_use'), type='primary')
        st.download_button('수집 본문 내려받기', collected_text(document).encode('utf-8-sig'),
                            file_name=document['name'] + '-수집본문.txt', mime='text/plain', key=key('library_download'))
        return reference if chosen else None
