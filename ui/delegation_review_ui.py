"""Private local draft input; never included in the static public website."""
import json
from pathlib import Path
import streamlit as st
from core.delegation_review import compare
from core.law_universe import load_graph, SOURCES
from core.citation_scope import Provision
from core.galaxy_focus import analyze_focus

ROOT = Path(__file__).resolve().parents[1]
LABELS = {'added':'위임 문구 추가 후보','changed':'위임 문구 변경','removed':'위임 문구 삭제 후보',
          'moved':'조 번호 이동 후보','context':'조문 변경 · 기존 인용 재검토','unchanged':'대조 문구 동일'}


def load_domain(domain):
    if domain == 'tax':
        graph = load_graph()
        source = graph.get('source') or json.loads(SOURCES.read_text(encoding='utf-8'))
    else:
        from core.public_institutions_universe import load_bundle, BUNDLE
        path = ROOT / 'output/public-scope/privatization/bundle.json'
        bundle = load_bundle(path if path.is_file() else BUNDLE)
        graph, source = bundle['graph'], bundle['source']
    docs = source.get('laws', []) + source.get('administrative_rules', [])
    return graph, [d for d in docs if d.get('kind') in ('법률','대통령령') or
                  (not d.get('kind') and d['name'].endswith(('법','법률',' 시행령')))], {d['name']:d.get('kind','') for d in docs}


def render(*_):
    st.caption('국세·공공기관 / 로컬 개정안 비교 · 입력 본문은 외부 AI·API로 보내거나 파일에 저장하지 않습니다.')
    domain = st.radio('검토 분야', ['tax','public_institutions'], format_func=lambda d:'국세' if d=='tax' else '공공기관', horizontal=True, key='delegation_domain')
    try:
        graph, documents, kinds = load_domain(domain)
    except (OSError, ValueError, KeyError):
        st.info('이 분야의 수집 자료를 불러오지 못했습니다. 다른 분야 자료로 대체하지 않습니다.'); return
    if not documents:
        st.info('비교할 법률·시행령의 수집 본문이 없습니다.'); return
    prefix='delegation_'+domain
    by_name={d['name']:d for d in documents}
    default='법인세법' if domain=='tax' else '공공기관의 운영에 관한 법률'
    names=list(by_name)
    law=st.selectbox('법률·시행령',names,index=names.index(default) if default in names else 0,key=prefix+'_law')
    document=by_name[law]; articles=document.get('articles',[])
    if not articles:
        st.info('조문 단위 본문이 없습니다.');return
    # Namespace by law as well as domain; draft inputs never follow a menu change.
    from scripts.build_static_galaxies import ident
    prefix+='_'+ident(domain,'',law)
    chosen=st.selectbox('수집 조문 불러오기',articles,format_func=lambda a:Provision(str(a['jo'])).label+' · '+a.get('title',''),key=prefix+'_article')
    if st.button('수집 본문을 개정 전·후 칸에 넣기',key=prefix+'_load',width='content'):
        st.session_state[prefix+'_before']=chosen['text'];st.session_state[prefix+'_after']=chosen['text']
        st.session_state.pop(prefix+'_result',None)
    with st.form(prefix+'_form',border=False):
        st.caption('조문 한 개의 전체 본문을 비교합니다. 제○조(제목)부터 마지막 항까지 넣어 주세요. 조 번호가 바뀌면 전후 번호를 그대로 입력합니다.')
        left,right=st.columns(2)
        with left:
            absent=st.checkbox('신설 조문 · 개정 전 본문 없음',key=prefix+'_new')
            before_date=st.text_input('개정 전 시행일 (선택)',placeholder='2026-01-01',key=prefix+'_before_date')
            before=st.text_area('개정 전 전체 조문',height=240,key=prefix+'_before')
        with right:
            removed=st.checkbox('삭제 조문 · 개정 후 본문 없음',key=prefix+'_deleted')
            after_date=st.text_input('개정 후 시행일 (선택)',placeholder='2027-01-01',key=prefix+'_after_date')
            after=st.text_area('개정 후 전체 조문',height=240,key=prefix+'_after')
        complete=st.checkbox('발췌문이 아닌 조문 전체이며, 신설·삭제 여부를 확인했습니다.',key=prefix+'_complete')
        submit=st.form_submit_button('후속 개정 후보 확인',type='primary',width='content')
    if submit:
        st.session_state.pop(prefix+'_result',None)
        if not complete:
            st.warning('조문 전체와 신설·삭제 여부를 먼저 확인해 주세요.');return
        try:
            result=compare(before,after,meta={'id':ident(domain,'',law),'name':law,'kind':document.get('kind',''),'domain':domain},
                new_article=absent,deleted_article=removed,before_date=before_date,after_date=after_date)
            st.session_state[prefix+'_result']=result
        except (ValueError, OSError, TimeoutError) as exc:
            st.error(str(exc));return
    result=st.session_state.get(prefix+'_result')
    if not result:return
    st.caption('마지막 실행 결과입니다. 입력을 수정했다면 다시 실행하세요. 입력 판본과 저장 인용 판본은 다를 수 있습니다.')
    st.caption('신규 위임·문구 변화·조 번호 이동은 검토 후보입니다. 의미상 변경의 전수 분석이나 위임 이행 판정은 아닙니다.')
    if not result['rows']:st.info('명시적 위임·조문 변경 후보가 탐지되지 않았습니다. 후속 개정이 불필요하다는 판정은 아닙니다.')
    for row in result['rows']:
        label=LABELS.get(row['change'],row['change'])
        if row.get('kind')=='citation-change':label='변경·삭제 조문 · 기존 인용 재검토'
        with st.expander(label+' · '+row['ref'],expanded=row['change']!='unchanged'):
            st.write(row['quote'])
            if row.get('before'):st.caption('개정 전: '+row['before']['quote'])
            refs=list(dict.fromkeys([row['ref']]+([row['before']['ref']] if row.get('before') else [])))
            for ref in refs:
                st.markdown('**수집 판본의 '+ref+' 인용 근거**')
                try:
                    rows=analyze_focus(law,ref,graph=graph)['rows']
                    def is_rule(r):
                        kind=kinds.get(r['source_law'],'')
                        return kind=='총리령' or kind.endswith('부령') or r['source_law'].endswith(' 시행규칙')
                    rows=[r for r in rows if r['direction']=='reverse' and (is_rule(r) or kinds.get(r['source_law'])=='대통령령' or r['source_law'].endswith(' 시행령'))]
                    if document.get('kind')=='대통령령' or document['name'].endswith(' 시행령'):rows=[r for r in rows if is_rule(r)]
                except ValueError:
                    st.caption('해당 조문 번호의 저장 인용을 대조하지 못했습니다.');continue
                if not rows:st.caption('현재 수집 범위에서 대응 인용 미확인 · 기존 규정 충족·미수집·개정 대기 여부를 확인하세요.')
                for r in rows:
                    st.write(r['source_law']+' '+r['source_ref'])
                    st.caption('인용 출처 시행 '+r.get('source_effective','미확인')+' · '+r.get('raw',''))
                    if r.get('source_url'):st.link_button('인용 당시 원문',r['source_url'])
