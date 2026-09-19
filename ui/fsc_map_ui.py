"""Independent financial galaxies with isolated sector searches and full evidence."""
from __future__ import annotations
import json
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
from core.fsc_universe import BUNDLE, article_for, external_evidence, load_bundle, present
from core.fsc_sectors import SECTORS, sector_graph, mark_sector, style_sector, tags_for
from ui.law_library_ui import render as render_library

@st.cache_data(show_spinner=False)
def _fsc_snapshot(path: str, stamp: tuple[int,int]) -> dict:
    return load_bundle(Path(path))

@st.cache_data(show_spinner=False)
def _fsc_overview(path: str, stamp: tuple[int,int], minimum: int, points: int, sector='all') -> dict:
    from core.law_galaxy import build
    return present(build(minimum,points,include_external=False,graph=sector_graph(_fsc_snapshot(path,stamp)['graph'],sector)))

@st.cache_data(show_spinner=False)
def _fsc_focus(path: str, stamp: tuple[int,int], law: str, reference: str, sector='all') -> dict:
    from core.galaxy_focus import analyze_focus
    bundle=_fsc_snapshot(path,stamp)
    article_for(bundle,law,reference)
    # Analyze the whole financial corpus, so incoming cross-sector evidence survives.
    return mark_sector(analyze_focus(law,reference,graph=bundle['graph']),bundle['graph'],sector)

def _date(value: str) -> str:
    return f'{value[:4]}.{value[4:6]}.{value[6:8]}' if len(value)==8 else value

def _tag_label(doc: dict) -> str:
    return ' · '.join(SECTORS[s] for s in doc.get('sectors',tags_for(doc['name'])[0]))

def _rules(bundle: dict, sector: str, key) -> None:
    from core.fsc_administrative import body_text
    rules=[r for r in bundle['source'].get('administrative_rules',[]) if sector=='all' or sector in r.get('sectors',tags_for(r['name'])[0])]
    indexed=sum(r.get('body_status')=='indexed-administrative-text' for r in rules)
    with st.expander(f'감독규정·시행세칙 원문 · {indexed}/{len(rules)}건 조문 분석'):
        if rules:
            by_name={r['name']:r for r in rules}
            choices=sorted(by_name)
            previous=st.session_state.get('fsc_sector_saved_widgets',{}).get(sector,{}).get(key('rule_name'))
            rule=by_name[st.selectbox('감독규정·행정규칙 찾기',choices,index=choices.index(previous) if previous in choices else 0,key=key('rule_name'))]
            status=f"{len(rule['articles'])}개 조문 · 직접 인용·역인용 분석 포함" if rule.get('body_status')=='indexed-administrative-text' else rule.get('analysis_error','본문 수집 · 조문 구조 미분석')
            st.caption(f"{rule['managing_authority']} · {rule['kind']} · 시행 {_date(rule['effective'])} · {status}")
            st.caption('분야 태그: '+_tag_label(rule))
            st.link_button('행정규칙 공식 원문',rule['source_url'])
            with st.container(height=320): st.text(body_text(rule['raw_body_blocks']))
        else: st.info('이 분야의 감독규정·시행세칙 데이터 미수집')
    scheduled=bundle['source'].get('scheduled',[])
    if scheduled and sector=='all':
        with st.expander(f'시행예정 자료 · {len(scheduled)}건'):
            st.dataframe([{'자료':r['name'],'시행예정일':_date(r['effective']),'상태':'본문 미수집 · 연결 미분석'} for r in scheduled],hide_index=True)

def render(law_api_key: str='', openai_api_key: str='') -> None:
    if not BUNDLE.is_file():
        st.info('금융위 데이터 미수집');return
    stat=BUNDLE.stat();path,stamp=str(BUNDLE),(stat.st_mtime_ns,stat.st_size)
    try: bundle=_fsc_snapshot(path,stamp)
    except (OSError,ValueError,KeyError,TypeError):
        st.error('금융위 데이터 검증 실패 · 수집 범위와 본문·그래프를 확인해 주세요.');return
    graph=bundle['graph']
    heading,info=st.columns([5,1],vertical_alignment='center')
    with heading:
        sector=st.radio('업권',list(SECTORS),format_func=SECTORS.get,horizontal=True,key='fsc_sector',label_visibility='collapsed')
    with info:
        with st.popover('자료 안내',width='stretch'): _source_info(bundle)
    prefix='fsc_' if sector=='all' else f'fsc_{sector}_'
    key=lambda name:prefix+name
    # Streamlit removes hidden widget keys; persist each sector's values separately.
    saved=st.session_state.setdefault('fsc_sector_saved_widgets',{})
    remember=lambda name,default:saved.get(sector,{}).get(key(name),default)
    view=sector_graph(graph,sector);laws=sorted(view['laws'])
    if not laws:
        st.info('이 분야의 금융위 데이터 미수집');return
    from core.fsc_labels import labels
    display_names=labels(graph['catalog'])
    indexed=graph.get('administrative_rules_indexed',0)
    defaults={'all':'은행법','insurance':'보험업법','banking':'은행법','securities':'자본시장과 금융투자업에 관한 법률'}
    default=remember('focus_law',defaults.get(sector,laws[0]))
    law_entry,reference_entry=st.columns([1,1],vertical_alignment='bottom')
    with law_entry:
        law=st.selectbox('법령·규정 선택',laws,index=laws.index(default) if default in laws else 0,key=key('focus_law'),format_func=display_names.get)
    document=next((d for d in bundle['source']['laws']+bundle['source'].get('administrative_rules',[]) if d['name']==law),None)
    picked=render_library(document,prefix=prefix,default_reference=st.session_state.get(key('focus_ref'),remember('focus_ref','제2조')),remember=remember)
    if picked: st.session_state[key('focus_ref')]=picked
    previous=st.session_state.get(key('focus_selection'))
    if previous and previous[0]!=law:
        st.session_state.pop(key('focus_selection'),None);st.session_state.pop(key('focus_error'),None)
    with reference_entry:
        with st.form(key('focus_form'),border=False):
            entry,action=st.columns([4,1.5],vertical_alignment='bottom')
            reference=entry.text_input('조문 번호',remember('focus_ref','제2조'),key=key('focus_ref'),help='수집 본문에서 고르거나 제2-9조의2제1항처럼 직접 입력하세요.')
            with action:
                submitted=st.form_submit_button('연결 탐색',key=key('focus_run'),type='primary',width='stretch')
    if submitted or picked:
        st.session_state.pop(key('focus_selection'),None);st.session_state.pop(key('focus_error'),None)
        try:
            result=_fsc_focus(path,stamp,law,reference,sector)
            st.session_state[key('focus_selection')]=(result['law'],result['reference'])
        except ValueError as error: st.session_state[key('focus_error')]=str(error)
    if st.session_state.get(key('focus_selection')) and st.button('전체 은하로 돌아가기',key=key('focus_clear')):
        st.session_state.pop(key('focus_selection'),None)
    if st.session_state.get(key('focus_error')): st.error(st.session_state[key('focus_error')])
    selection=st.session_state.get(key('focus_selection'));result=None
    if selection:
        try: result=_fsc_focus(path,stamp,*selection,sector)
        except ValueError as error: st.warning(str(error))
    from core.galaxy_focus import DIRECTIONS,KINDS,build,visible_rows
    from core.law_galaxy import render_html,render_page
    direction,review,broad,kinds='both',True,False,list(KINDS)
    if result:
        st.markdown(f"#### {display_names.get(result['law'],result['law'])} {result['reference']}")
        direction=st.radio('연결 방향',list(DIRECTIONS),index=list(DIRECTIONS).index(remember('direction','both')),format_func=DIRECTIONS.get,horizontal=True,key=key('direction'))
    if result:
        with st.expander('연결 설정'):
            review=st.checkbox('문맥·출처 확인 후보 포함',remember('review',True),key=key('review'))
            broad=st.checkbox('법령 전체를 참조하는 역인용 후보 포함',remember('broad',False),key=key('broad'))
            kinds=st.multiselect('연결 종류',list(KINDS),default=remember('kinds',list(KINDS)),format_func=KINDS.get,key=key('kinds'))
    minimum,points=8,160
    data=_fsc_overview(path,stamp,minimum,points,sector);rows=[]
    if result:
        filters=dict(external=False,kinds=kinds,include_broad=broad)
        rows=visible_rows(result,direction,review,**filters)
        data=present(build(result,_fsc_overview(path,stamp,minimum,points,'all'),direction,review,**filters))
        if sector!='all':
            members=set(view['laws'])
            data['nodes']=[n for n in data['nodes'] if not n.get('context_only') or n['id'] in members]
            data['dust']=[d for d in data['dust'] if d.get('law_id') in members]
        outside=sum(r.get('out_of_sector',False) for r in rows)
        st.caption(f"연결 대상 {data['neighbor_count']}개 · 인용 {sum(r['direction']=='forward' for r in rows)}건 · 역인용 {sum(r['direction']=='reverse' for r in rows)}건 · 분야 밖 관련 조문 근거 {outside}건")
        if not rows: st.info('현재 조건에 맞는 저장 인용이 없습니다. 관련 영향이 없다는 뜻은 아닙니다.')
    data=style_sector(data,sector)
    components.html(render_html(data,height=740),height=760,scrolling=False)
    st.download_button('은하 내려받기',render_page(data).encode('utf-8'),f'금융 은하-{SECTORS[sector]}.html','text/html',key=key('html'))
    if result:
        document,article=article_for(bundle,*selection)
        st.caption(f"{document['name']} · 시행 {_date(document['effective'])} · {document['managing_authority']} · 분야 {_tag_label(document)}")
        st.link_button('선택 법령의 수집 판본 · 공식 원문',document['source_url'])
        with st.expander(f"선택 조문 원문 · {result['reference']} · {article['title']}"): st.text(article['text'])
        def table(items):
            st.dataframe([{'분야':r.get('sector_relation',''),'방향':r['direction_label'],
                           '인용 출처':r['source_law']+' '+r['source_ref'],'인용 대상':r['target_law']+' '+r['target_ref'],
                           '인용 문구':r['raw'],'원문 문맥':r.get('context',''),'확인 내용':r['reason'],
                           '대상 조문 확인':{'missing-from-collected-body':'수집 판본에서 찾지 못함','deleted':'삭제 조문'}.get(r.get('target_provision_status'),'인용 근거 확인'),
                           '출처 시행일':_date(r.get('source_effective','')),'원문 링크':r.get('source_url','')} for r in items],hide_index=True,width='stretch')
        with st.expander(f'법령·감독규정·시행세칙 사이의 인용 근거 · {len(rows)}건'): table(rows)
        if sector!='all':
            outside=[r for r in rows if r.get('out_of_sector')]
            with st.expander(f'분야 밖 관련 조문 · 공통·다른 업권 · {len(outside)}건',expanded=bool(outside)):
                st.caption('금융 은하 안에서 수집·분석한 다른 분야의 조문입니다. 분야 태그는 개정 의무를 뜻하지 않습니다.')
                table(outside)
        issues=[e for e in graph.get('citation_issues',[]) if e['source_law']==selection[0] and e['source_jo']==article['jo']]
        if issues:
            with st.expander(f'이 조문의 연결 해석 보류 · {len(issues)}건'):
                st.caption('미해결 별칭·상대 참조입니다. 대상 조문으로 확정하지 않았습니다.')
                st.dataframe([{'원문':e['raw'],'상태':e['reason']} for e in issues],hide_index=True,width='stretch')
        external=external_evidence(graph,*selection)
        with st.expander(f'선택 조문이 인용하는 지도 밖·미분석 대상 · {len(external)}건'):
            st.caption('미수집 대상과 본문만 수집한 미분석 자료를 구분합니다. 대상 조문 연결·역인용은 점검하지 않았으며 지도에 펼치지 않습니다.')
            st.dataframe([{'대상':e['target_law']+' '+e['target_ref'],'인용 원문':e['cite_raw'],'원문 문맥':e['context'],
                           '상태':'본문 수집 · 조문 연결 미분석' if e.get('target_status')=='collected-not-indexed' else '미수집 · 본문/역인용 미점검','공식 링크':e['target_url'],'인용 출처 링크':e['source_url']} for e in external],hide_index=True,width='stretch')
        st.download_button('금융 인용 근거 내려받기',json.dumps(dict(domain='fsc',sector=sector,selection=selection,rows=rows,
                           external_references=external,unresolved=issues,coverage=graph['coverage']),ensure_ascii=False,indent=2).encode('utf-8'),
                           '금융 은하-인용근거.json','application/json',key=key('evidence'))
    _rules(bundle,sector,key)
    widget_names=('focus_law','focus_ref','direction','review','broad','kinds','rule_name','library_query','library_article','library_scope')
    saved[sector]={key(n):st.session_state[key(n)] for n in widget_names if key(n) in st.session_state}


def _source_info(bundle: dict) -> None:
    graph=bundle['graph']
    st.caption(f"수집 기준 {_date(graph['built_at'])} · 법령 {len(bundle['source']['laws'])}건 · 감독규정·시행세칙 {graph.get('administrative_rules_indexed',0)}건 분석")
    st.caption('공식 약칭을 우선 표시합니다. 업권은 복수 태그로 분류하며, 다른 업권·공통규정과의 연결은 분야 밖 관련 조문으로 안내합니다.')
    with st.expander('금융 은하 수집 범위와 분석 상태'):
        st.write(graph['coverage_note'])
        st.caption('업권 태그는 명칭에 따른 분류이며 복수 지정할 수 있습니다. 공통에는 업권 공통규정과 기관운영 자료가 포함됩니다. 별표 파일 본문·부칙은 미분석입니다.')
        st.dataframe([{'법령·규정':d['name'],'분야':_tag_label(d),'분류 근거':' / '.join(d.get('sector_basis',[])),
                       '소관':d['managing_authority'],'종류':d['kind'],'시행일':_date(d['effective']),
                       '분석 조문':len(d.get('articles',[])),'공식 원문':d['source_url']} for d in bundle['source']['laws']+bundle['source'].get('administrative_rules',[])],hide_index=True,width='stretch')
