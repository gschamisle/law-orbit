"""Local-tax atlas: central statutes first, municipal ordinances on demand."""
from __future__ import annotations
from collections import Counter, defaultdict
import json
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components

from core.local_tax_collection import OUTPUT
from core.local_tax_graph import load_manifest, load_bundle, national_reverse
from core.galaxy_focus import _target, analyze_focus, visible_rows, build as focus_map, DIRECTIONS, KINDS
from core.law_galaxy import build as overview, render_html, render_page
from ui.law_library_ui import render as library


@st.cache_data(show_spinner=False)
def _snapshot(folder: str, version: str, region: str, manifest: dict) -> dict:
    return load_bundle(Path(folder),manifest,region)


@st.cache_data(show_spinner=False)
def _national(folder: str, version: str, law: str, reference: str, manifest: dict) -> list[dict]:
    return national_reverse(Path(folder),manifest,law,reference)


def _date(value):
    return f'{value[:4]}.{value[4:6]}.{value[6:8]}' if len(value)==8 else value


def _display(bundle):
    proposed={d['name']:d.get('display_name',d['name']) for d in bundle['source']['laws']}
    counts=Counter(proposed.values())
    return {name:label if counts[label]==1 else name for name,label in proposed.items()}


def _map(bundle: dict) -> dict:
    graph=bundle['graph'];documents={d['name']:d for d in bundle['source']['laws']}
    # Keep disconnected candidates in the library, but not as unexplained stars.
    connected={name for name,doc in documents.items() if doc['provider']=='eflaw'}
    while True:
        before=len(connected)
        for edge in graph['edges']:
            if edge['source_law'] in connected or edge['target_law'] in connected:
                connected.update((edge['source_law'],edge['target_law']))
        if len(connected)==before:break
    view={**graph,'laws':[n for n in graph['laws'] if n in connected],
          'edges':[e for e in graph['edges'] if e['source_law'] in connected and e['target_law'] in connected]}
    data=overview(1,120,include_external=False,graph=view)
    labels=_display(bundle)
    colors={'지방세기본법':'#8bbef5','지방세징수법':'#b7a3e6','지방세법':'#68dbc2','지방세특례제한법':'#efb975'}
    for node in data['nodes']:
        doc=documents[node['id']]
        node.update(label=labels[node['id']],full_name=node['id'],category='local_tax',
                    color=colors.get(doc.get('family'),'#d5c78d'),
                    title=doc['managing_authority']+' · '+doc['kind']+' · 시행 '+_date(doc['effective']))
    nodes={n['id']:n for n in data['nodes']}
    for point in data['dust']:
        point.update(law=labels[point['law_id']],c=nodes[point['law_id']]['color'])
    return data


def _present(data):
    return {**data,'domain':'local_tax','galaxy_title':'지방세 은하'}


def _open_region(region: dict, law: str, reference: str):
    st.session_state['local_tax_province']=region['province']
    st.session_state['local_tax_region']=region['id']
    prefix='local_tax_'+region['id']+'_'
    st.session_state[prefix+'focus_law']=law
    st.session_state[prefix+'focus_ref']=reference
    st.session_state[prefix+'selection']=(law,reference)


def _source_info(manifest):
    st.caption(f"수집 기준 {_date(manifest['as_of'])}")
    st.caption(f"전국 자치법규 목록 {manifest['inventory_total']:,}건 대조 · 지방세 본문 검색 후보 {manifest['candidates_total']:,}건")
    st.caption(f"중앙 법령 {manifest['central_documents']}건 · 조례·규칙 {manifest['indexed']:,}건 조문 분석")
    st.caption(f"별칭·상대 참조·대상 조문 확인 후보 {sum(r.get('issues',0) for r in manifest['regions']):,}건은 각 조문의 확인 목록에 남겼습니다.")
    st.caption(manifest['coverage_note'])
    st.caption('법제처 제공 목록의 건수·고유번호를 대조했습니다. 전국 관련 조례의 완전성이나 지자체 공보와의 일치는 검증하지 않았습니다.')
    if manifest.get('provider_duplicates'):
        st.caption(f"API의 동일 자료 중복 반환 {sum(d['rows']-1 for d in manifest['provider_duplicates'])}건은 개별 명칭 조회에서도 재현됨을 확인하고 한 문서로 집계했습니다.")
    st.caption('별표 본문은 API 제공 제한이 있고 미분석입니다. 부칙은 저장만 했으며 연결 분석에 포함하지 않았습니다.')
    if manifest.get('edition_differences'):
        st.caption(f"본문 검색의 과거 판본 {len(manifest['edition_differences'])}건은 별도 현행 목록의 판본으로 대조했습니다. 제목 검색으로 {len(manifest.get('title_additions',[]))}건을 보완했습니다.")
    if manifest.get('unresolved_candidates'):
        st.warning(f"본문 검색에 있으나 현행 목록에서 확인하지 못한 자료 {len(manifest['unresolved_candidates'])}건 · 연결 분석 보류")
        st.dataframe([{'자료':r['name'],'상태':'현행 여부 미확인','검색 판본':r['mst']} for r in manifest['unresolved_candidates']],hide_index=True)
    st.link_button('법제처 자치법규 제공 범위','https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=ordinInfoGuide')
    if manifest.get('failed') or manifest.get('review'):
        st.warning(f"원문 확인·분석 보류 {len(manifest.get('failed',[]))+len(manifest.get('review',[]))}건")
        reasons={'ordin-no-structured-articles':'조문 본문 없음','ordin-duplicate-article':'같은 조문 번호가 중복됨',
                 'ordin-amendment-instructions-in-body':'개정 지시문과 본문이 혼재함','ordin-empty-article':'빈 조문 내용',
                 'ordin-article-number-body-mismatch':'조문 번호와 본문 표기가 다름','ordin-body-edition-mismatch':'목록과 본문의 판본이 다름',
                 'official-api-request-failed':'공식 원문 조회 실패'}
        st.dataframe([{'자료':r['name'],'지역':r.get('managing_authority',r.get('authority','')),
                       '확인 내용':reasons.get(r.get('reason'),'원문 구조 확인 필요'),
                       '공식 원문':'https://www.law.go.kr/LSW/ordinInfoP.do?ordinSeq='+r['mst'] if r.get('mst') else ''}
                      for r in manifest.get('failed',[])+manifest.get('review',[])],hide_index=True)
    st.download_button('수집·분석 범위 내려받기',json.dumps(manifest,ensure_ascii=False,indent=2).encode('utf-8'),
                       '지방세-수집범위.json','application/json',key='local_tax_coverage_download')


def render(law_api_key: str='', openai_api_key: str=''):
    if not (OUTPUT/'current.json').is_file():
        st.info('지방세 데이터 미수집 · 검증된 수집 자료가 준비되면 이곳에 표시됩니다.')
        return
    try: folder,manifest=load_manifest(OUTPUT)
    except (OSError,ValueError,KeyError,TypeError):
        st.error('지방세 자료를 확인하지 못했습니다. 수집 기준과 파일 상태를 확인해 주세요.');return
    provinces=sorted({r['province'] for r in manifest['regions']})
    place,subplace,info=st.columns([2,2,1],vertical_alignment='bottom')
    with place:
        province=st.selectbox('지역 범위',['중앙 법령만']+provinces,key='local_tax_province')
    region=''
    if province!='중앙 법령만':
        regions=[r for r in manifest['regions'] if r['province']==province]
        lookup={r['id']:r for r in regions}
        if st.session_state.get('local_tax_region') not in lookup:st.session_state.pop('local_tax_region',None)
        with subplace:
            region=st.selectbox('지자체',list(lookup),format_func=lambda i:lookup[i]['authority'],key='local_tax_region')
        if not lookup[region].get('file'):
            with info:
                with st.popover('자료 안내'): _source_info(manifest)
            st.info('이 지역은 지방세 검색 후보 중 분석된 조례·규칙이 없습니다. 관련 조례가 없다는 뜻은 아닙니다.');return
        st.caption(f"{lookup[region]['authority']} · 전체 조례·규칙 목록 {lookup[region]['inventory']:,}건 중 지방세 검색 후보 {lookup[region]['indexed']:,}건 분석")
    else:
        st.caption('중앙 법령을 먼저 살펴보고, 조문을 검색해 이를 인용하는 지역의 조례를 펼쳐보세요.')
    with info:
        with st.popover('자료 안내'): _source_info(manifest)
    try: bundle=_snapshot(str(folder),manifest['version'],region,manifest)
    except (OSError,ValueError,KeyError,TypeError):
        st.error('선택 지역의 지방세 자료 검증 실패 · 다른 은하의 자료로 대체하지 않습니다.');return
    prefix='local_tax_'+(region or 'central')+'_';key=lambda n:prefix+n
    saved=st.session_state.setdefault('local_tax_saved_widgets',{})
    remember=lambda n,d:saved.get(region,{}).get(n,d)
    documents={d['name']:d for d in bundle['source']['laws']};labels=_display(bundle)
    laws=sorted(documents,key=lambda n:(documents[n]['provider']=='ordin',n))
    desired=remember('focus_law','지방세법')
    law=st.selectbox('법령·조례 선택',laws,index=laws.index(desired) if desired in laws else 0,format_func=labels.get,key=key('focus_law'))
    picked=library(documents[law],prefix=prefix,default_reference=st.session_state.get(key('focus_ref'),remember('focus_ref','제4조')),remember=remember)
    if picked:st.session_state[key('focus_ref')]=picked
    old=st.session_state.get(key('selection'))
    if old and old[0]!=law:st.session_state.pop(key('selection'),None)
    with st.form(key('focus_form'),border=False):
        entry,action=st.columns([4,1],vertical_alignment='bottom')
        if key('focus_ref') not in st.session_state:st.session_state[key('focus_ref')]=remember('focus_ref','제4조')
        reference=entry.text_input('조문 번호',key=key('focus_ref'),placeholder='예: 제4조 또는 제103조의19')
        with action: submitted=st.form_submit_button('연결 탐색',type='primary',key=key('focus_run'))
    if submitted or picked:
        st.session_state.pop(key('selection'),None)
        try:
            target=_target(reference)
            if not any(a['jo']==target.jo for a in documents[law]['articles']):raise ValueError('수집한 본문에 해당 조문이 없습니다.')
            st.session_state[key('selection')]=(law,target.label)
            st.session_state.pop(key('error'),None)
        except ValueError as error:st.session_state[key('error')]=str(error)
    if st.session_state.get(key('error')):st.error(st.session_state[key('error')])
    selection=st.session_state.get(key('selection'))
    if selection and (selection[0] not in documents or not any(a['jo']==_target(selection[1]).jo for a in documents[selection[0]]['articles'])):
        st.session_state.pop(key('selection'),None);selection=None
        st.info('자료가 갱신되어 이전 선택 조문을 찾지 못했습니다. 수집 본문에서 다시 선택해 주세요.')
    if selection and st.button('전체 은하로 돌아가기',key=key('clear')):
        st.session_state.pop(key('selection'),None);selection=None
    graph=bundle['graph'];data=_map(bundle);rows=[];result=None
    if selection:
        result=analyze_focus(*selection,graph=graph)
        st.markdown(f'#### {labels[selection[0]]} {selection[1]}')
        direction=st.radio('연결 방향',list(DIRECTIONS),index=list(DIRECTIONS).index(remember('direction','both')),format_func=DIRECTIONS.get,horizontal=True,key=key('direction'))
        rows=visible_rows(result,direction,True,external=False)
        data=focus_map(result,data,direction,True,external=False)
        st.caption(f"선택 범위의 직접 연결 근거 {len(rows):,}건 · 역인용은 수집·분석한 자료 범위입니다.")
    components.html(render_html(_present(data),height=720),height=740,scrolling=False)
    st.download_button('은하 내려받기',render_page(_present(data)).encode('utf-8'),'지방세 은하.html','text/html',key=key('html'))
    if selection:
        document=documents[selection[0]];article=next(a for a in document['articles'] if a['jo']==_target(selection[1]).jo)
        national=[]
        if document['provider']=='eflaw':
            national=_national(str(folder),manifest['version'],*selection,manifest)
            counts=defaultdict(set)
            for edge in national:counts[edge['region_id']].add((edge['source_law'],edge['source_jo']))
            st.markdown('#### 이 조문을 인용하는 지역')
            st.caption(f"전국 수집 후보 중 {len(counts)}개 지역 · 서로 다른 조례·규칙 조문 {sum(len(v) for v in counts.values()):,}개. 법령 전체 참조와 문구 유사성은 이 수에 포함하지 않습니다.")
            if counts:
                choices={r['id']:r for r in manifest['regions'] if r['id'] in counts}
                ordered=sorted(choices,key=lambda i:(-len(counts[i]),choices[i]['authority']))
                chosen=st.selectbox('연결된 지역 펼치기',ordered,format_func=lambda i:f"{choices[i]['authority']} · {len(counts[i])}개 조문",key=key('related_region'))
                st.button('이 지역 펼치기',key=key('open_region'),on_click=_open_region,args=(choices[chosen],*selection))
                with st.expander('전국 조례 인용 근거'):
                    st.dataframe([{'지역':e['source_authority'],'조례·규칙':e['source_law'],'출처 조문':e['source_ref'],
                                   '인용 문구':e['cite_raw'],'시행일':_date(e['source_effective']),'공식 원문':e['source_url']} for e in national],hide_index=True,width='stretch',
                                 column_config={'공식 원문':st.column_config.LinkColumn('공식 원문',display_text='원문 보기')})
            else:st.info('수집·분석된 후보 안에서 이 조문을 직접 인용하는 조례를 찾지 못했습니다. 영향 없음의 판정은 아닙니다.')
        with st.expander('선택 조문 원문 · '+article['title']):
            st.caption(document['name']+' · 시행 '+_date(document['effective']))
            st.link_button('수집 판본의 공식 원문',document['source_url'])
            st.text(article['text'])
        with st.expander(f'직접 인용·역인용 근거 · {len(rows)}건'):
            st.dataframe([{'방향':r['direction_label'],'출처':r['source_law']+' '+r['source_ref'],
                           '대상':r['target_law']+' '+r['target_ref'],'인용 문구':r['raw'],'문맥':r.get('context',''),
                           '대상 조문 상태':{'missing-from-collected-body':'수집 판본에 조문 없음','deleted':'삭제 조문'}.get(r.get('target_provision_status'),'인용 근거 확인'),
                           '확인 내용':r['reason'],'원문':r.get('source_url','')} for r in rows],hide_index=True,width='stretch',
                         column_config={'원문':st.column_config.LinkColumn('원문',display_text='원문 보기')})
        external=[e for e in graph['external_references'] if e['source_law']==selection[0] and e['source_jo']==article['jo']]
        issues=[e for e in graph['citation_issues'] if e['source_law']==selection[0] and e['source_jo']==article['jo']]
        with st.expander(f'지도 밖 인용·해석 확인 · {len(external)+len(issues)}건'):
            st.caption('미수집 대상의 본문·역인용과 별표 본문은 점검하지 않았습니다. 같은 이름의 다른 지역 조례로 대체하지 않습니다.')
            if external:st.dataframe([{'대상':e['target_law']+' '+e['target_ref'],'인용 문구':e['cite_raw'],'상태':'미수집 · 본문/역인용 미점검','공식 링크':e['target_url']} for e in external],hide_index=True)
            if issues:st.dataframe([{'원문':i['raw'],'확인 내용':i['reason']} for i in issues],hide_index=True)
        st.download_button('지방세 인용 근거 내려받기',json.dumps(dict(selection=selection,region=region,rows=rows,national_reverse=national,
                           external_references=external,issues=issues,coverage=manifest['coverage_note']),ensure_ascii=False,indent=2).encode('utf-8'),
                           '지방세-인용근거.json','application/json',key=key('evidence'))
    widget_names=('focus_law','focus_ref','direction','library_query','library_article','library_scope')
    saved[region]={n:st.session_state[key(n)] for n in widget_names if key(n) in st.session_state}
