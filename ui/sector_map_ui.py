"""Profile-based galaxy screen with explicit domain/path/state isolation."""
import json
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
from core import procurement_universe, housing_universe, environment_universe, state_property_universe, forex_universe
from core import public_institutions_universe, customs_universe, treasury_universe
from core.procurement_universe import documents, sector_graph, mark_sector, article_for, external_evidence
APIS={'procurement':procurement_universe,'housing':housing_universe,'environment':environment_universe,'state_property':state_property_universe,'forex':forex_universe}
APIS.update(public_institutions=public_institutions_universe,customs=customs_universe,treasury=treasury_universe)
from ui.law_library_ui import render as render_library


@st.cache_data(show_spinner=False)
def snapshot(path, stamp, domain):
    return APIS[domain].load_bundle(Path(path))


@st.cache_data(show_spinner=False)
def overview(path, stamp, sector, domain, palette_version='families-v4-domain-labels'):
    from core.law_galaxy import build
    graph=snapshot(path,stamp,domain)['graph']
    return APIS[domain].present(build(2,160,include_external=False,graph=sector_graph(graph,sector)),graph,sector)


@st.cache_data(show_spinner=False)
def focus(path, stamp, law, reference, sector, domain):
    from core.galaxy_focus import analyze_focus
    bundle=snapshot(path,stamp,domain)
    article_for(bundle,law,reference)
    return APIS[domain].mark_sector(analyze_focus(law,reference,graph=bundle['graph']),bundle['graph'],sector)


def date(value):
    return f'{value[:4]}.{value[4:6]}.{value[6:]}' if len(value)==8 else value


def evidence_table(rows):
    st.dataframe([{'분야':r.get('sector_relation',''), '방향':r['direction_label'],
                   '인용 출처':r['source_law']+' '+r['source_ref'],
                   '인용 대상':r['target_law']+' '+r['target_ref'],
                   '인용 문구':r['raw'], '원문 문맥':r.get('context',''), '확인 내용':r['reason'],
                   '출처 시행일':date(r.get('source_effective','')), '공식 원문':r.get('source_url','')}
                  for r in rows],hide_index=True,width='stretch')


def render(profile, bundle_path):
    domain=profile['domain'];BUNDLE=Path(bundle_path);SECTORS=APIS[domain].SECTORS
    present=APIS[domain].present;report=APIS[domain].report
    state_prefix=profile['prefix']

    if not BUNDLE.is_file():
        st.info(profile['title']+' 데이터 미수집'); return
    stat=BUNDLE.stat();path,stamp=str(BUNDLE),(stat.st_mtime_ns,stat.st_size)
    try:bundle=snapshot(path,stamp,domain)
    except (OSError,ValueError,KeyError,TypeError):
        st.error(profile['title']+' 데이터 검증 실패 · 수집 자료를 확인해 주세요.');return
    graph=bundle['graph'];docs=documents(bundle['source']);by_name={d['name']:d for d in docs}
    work=bundle.get('assessment')
    if work:
        st.caption(work['purpose'])
        with st.expander('업무 질문으로 시작'):
            st.caption('수집 조문 간 인용 근거를 확인한 질문입니다. 개정 필요성의 자동 판정은 아닙니다.')
            for case in work['cases']:
                if not case['available']:continue
                if st.button(case['title'],key=state_prefix+'_case_'+case['jo'],width='content'):
                    remembered=st.session_state.setdefault(state_prefix+'_saved_widgets',{})
                    remembered.setdefault('all',{}).update(law=case['law'],ref='제'+case['jo']+'조')
                    st.session_state[state_prefix+'_all_law']=case['law']
                    st.session_state[state_prefix+'_all_ref']='제'+case['jo']+'조'
                    st.session_state[state_prefix+'_all_selection']=(case['law'],'제'+case['jo']+'조')
                    st.session_state[state_prefix+'_sector']='all'
            for limitation in work['limitations']:st.caption(limitation)
    title,info=st.columns([5,1],vertical_alignment='center')
    with title:
        sector=st.radio('탐색 분야',list(SECTORS),format_func=SECTORS.get,horizontal=True,key=state_prefix+'_sector',label_visibility='collapsed')
    with info:
        with st.popover('자료 안내',width='stretch'):
            summary=report(bundle)
            if domain=='forex':
                st.caption(f"수집 {date(graph['built_at'])} · 법령 {summary['statutes']}건 · 행정규칙 {summary['api_administrative_rules']}건 · 한국은행 세칙·절차 {summary['bok_rules']}건")
            else:
                st.caption(f"수집 {date(graph['built_at'])} · 법령 {summary['statutes']}건 · 행정규칙 {summary['administrative_rules']}건 · 조문 분석 {summary['indexed_documents']}건")
            st.write(graph['coverage_note'])
            if work:
                for item in work['companion_sources']:st.link_button(item['title'],item['url'])
            for document in docs:
                for note in document.get('source_notes',[]):st.caption(document['name']+' · '+note)
            st.caption('분야는 복수 태그입니다. 다른 분야와 연결되는 근거는 전체 수집 범위에서 찾습니다. 자동 갱신 예약은 아직 연결하지 않았습니다.')
            with st.expander('수집 목록과 분석 상태'):
                st.dataframe([{'자료':d['name'],'소관':d['managing_authority'],'시행일':date(d['effective']),
                               '분석 조문':len(d.get('articles',[])), '상태':'조문 분석' if d.get('articles') else d.get('analysis_error','미분석'),
                               '공식 원문':d['source_url']} for d in docs],hide_index=True)
            scheduled=bundle['source'].get('scheduled',[])
            if scheduled:
                with st.expander(f'시행예정 · 본문 미반영 · {len(scheduled)}건'):
                    st.caption('공포되었으나 아직 시행하지 않은 판본입니다. 현재 지도에는 반영하지 않았습니다.')
                    st.dataframe([{'자료':d['name'],'시행예정일':date(d['effective']),'공식 원문':d['source_url']} for d in scheduled],hide_index=True)
    prefix=f'{state_prefix}_{sector}_';key=lambda n:prefix+n
    saved=st.session_state.setdefault(state_prefix+'_saved_widgets',{})
    remember=lambda n,default:saved.get(sector,{}).get(n,default)
    view=sector_graph(graph,sector);laws=sorted(view['laws'])
    if not laws:st.info('이 분야의 조문 분석 자료가 없습니다.');return
    default=remember('law',profile['default_laws'].get(sector,profile['default_laws']['all']))
    left,right=st.columns([1,1],vertical_alignment='bottom')
    with left:
        law=st.selectbox('법령·규정 선택',laws,index=laws.index(default) if default in laws else 0,
                         format_func=lambda n:by_name[n]['display_name'],key=key('law'))
    picked=render_library(by_name[law],prefix=prefix,default_reference=remember('ref',profile['default_refs'].get(sector,'제1조')),remember=remember)
    if picked:st.session_state[key('ref')]=picked
    previous=st.session_state.get(key('selection'))
    if previous and previous[0]!=law:st.session_state.pop(key('selection'),None)
    with right:
        with st.form(key('form'),border=False):
            field,action=st.columns([4,1.5],vertical_alignment='bottom')
            reference=field.text_input('조문 번호',remember('ref',profile['default_refs'].get(sector,'제1조')),key=key('ref'))
            with action:submitted=st.form_submit_button('연결 탐색',key=key('run'),type='primary',width='stretch')
    if picked or submitted:
        st.session_state.pop(key('selection'),None);st.session_state.pop(key('error'),None)
        try:
            result=focus(path,stamp,law,reference,sector,domain)
            st.session_state[key('selection')]=(result['law'],result['reference'])
        except ValueError as error:st.session_state[key('error')]=str(error)
    if st.session_state.get(key('error')):st.error(st.session_state[key('error')])
    selection=st.session_state.get(key('selection'))
    if selection and st.button('전체 보기',key=key('clear')):
        st.session_state.pop(key('selection'),None);selection=None
    from core.galaxy_focus import DIRECTIONS,KINDS,build,visible_rows
    from core.law_galaxy import render_html,render_page
    result=None;rows=[];data=overview(path,stamp,sector,domain)
    if selection:
        try:result=focus(path,stamp,*selection,sector,domain)
        except ValueError as error:st.warning(str(error))
    if result:
        st.markdown(f"#### {by_name[law]['display_name']} {result['reference']}")
        direction=st.radio('연결 방향',list(DIRECTIONS),index=list(DIRECTIONS).index(remember('direction','both')),
                           format_func=DIRECTIONS.get,horizontal=True,key=key('direction'))
        with st.expander('연결 설정'):
            review=st.checkbox('문맥·출처 확인 후보 포함',remember('review',True),key=key('review'))
            broad=st.checkbox('법령 전체를 참조하는 역인용 후보 포함',remember('broad',False),key=key('broad'))
            kinds=st.multiselect('연결 종류',list(KINDS),default=remember('kinds',list(KINDS)),format_func=KINDS.get,key=key('kinds'))
        filters=dict(external=False,kinds=kinds,include_broad=broad)
        rows=visible_rows(result,direction,review,**filters)
        data=present(build(result,overview(path,stamp,'all',domain),direction,review,**filters),graph,sector)
        members=set(view['laws'])
        data['nodes']=[n for n in data['nodes'] if not n.get('context_only') or n['id'] in members]
        data['dust']=[d for d in data['dust'] if d.get('law_id') in members]
        st.caption(f"인용 {sum(r['direction']=='forward' for r in rows)}건 · 역인용 {sum(r['direction']=='reverse' for r in rows)}건 · 분야 밖 관련 근거 {sum(r.get('out_of_sector',False) for r in rows)}건")
        if not rows:st.info('조건에 맞는 저장 인용이 없습니다. 관련 영향이 없다는 뜻은 아닙니다.')
    components.html(render_html(data,height=740),height=760,scrolling=False)
    st.download_button('3D 화면 내려받기',render_page(data).encode('utf-8'),profile['title']+'-법령연결.html','text/html',key=key('html'))
    if result:
        document,article=article_for(bundle,*selection)
        st.caption(f"{document['name']} · 시행 {date(document['effective'])} · {document['managing_authority']}")
        st.link_button('수집 판본의 공식 원문',document['source_url'])
        with st.expander('선택 조문 원문'):st.text(article['text'])
        contexts=[e for e in graph.get('context_evidence',[]) if e['source_law']==law and e['source_jo']==article['jo']]
        if contexts:
            with st.expander(f'인허가 의제 · 조례 위임 문구 · {len(contexts)}건'):
                st.caption('원문의 검토 단서입니다. 조례 본문·역인용은 미수집이며, 의제 범위와 적용 조건은 각 조문에서 확인하세요.')
                st.dataframe([{'구분':e['kind'],'원문 근거':e['raw'],'시행일':date(e['source_effective']),
                               '공식 원문':e['source_url']} for e in contexts],hide_index=True,width='stretch')

        with st.expander(f'인용·역인용 근거 · {len(rows)}건'):evidence_table(rows)
        outside=[r for r in rows if r.get('out_of_sector')]
        if outside:
            with st.expander(f'분야 밖 관련 조문 · {len(outside)}건'):
                st.caption(profile['outside_note'])
                evidence_table(outside)
        external=external_evidence(graph,*selection)
        with st.expander(f'지도 밖·미분석 인용 대상 · {len(external)}건'):
            st.caption('이 대상의 조문과 역인용은 점검하지 않았습니다.')
            st.dataframe([{'대상':e['target_law']+' '+e['target_ref'],'인용 원문':e['cite_raw'],
                           '상태':'자료 확인 · 조문 연결 미분석' if e['target_status']=='collected-not-indexed' else '미수집',
                           '공식 링크':e['target_url']} for e in external],hide_index=True,width='stretch')
        issues=[e for e in graph['citation_issues'] if e['source_law']==law and e['source_jo']==article['jo']]
        if issues:
            with st.expander(f'연결 해석 보류 · {len(issues)}건'):
                st.dataframe([{'원문':e['raw'],'확인 내용':e['reason']} for e in issues],hide_index=True)
        st.download_button('인용 근거 내려받기',json.dumps(dict(domain=domain,sector=sector,selection=selection,
                           rows=rows,external_references=external,unresolved=issues,context_evidence=contexts,coverage=graph['coverage']),ensure_ascii=False,indent=2).encode('utf-8'),
                           domain+'-인용근거.json','application/json',key=key('evidence'))
    unindexed=[d for d in docs if not d.get('articles') and (sector=='all' or sector in d['sectors'])]
    if unindexed:
        with st.expander(f'조문 연결 미분석 자료 · {len(unindexed)}건'):
            name=st.selectbox('원문 확인 자료',[d['name'] for d in unindexed],key=key('raw_name'))
            d=by_name[name]
            st.caption(d.get('analysis_error','조문 형식 확인 필요'))
            st.link_button('공식 원문·첨부파일 확인',d['source_url'])
            from core.fsc_administrative import body_text
            text=body_text(d.get('raw_body_blocks',[]))
            if work:
                import re
                if re.search(r'</?img\b[^>]*>',text,re.I):
                    text='[이미지·도표는 공식 원문에서 확인하세요.]\n\n'+re.sub(r'</?img\b[^>]*>','',text,flags=re.I).strip()
            if text:
                with st.container(height=300):st.text(text)
    widgets=('law','ref','direction','review','broad','kinds','library_query','library_article','library_scope')
    saved[sector]={n:st.session_state[key(n)] for n in widgets if key(n) in st.session_state}
