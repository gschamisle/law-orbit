"""Local viewer for the same public-scope evidence used by the static app."""
import streamlit as st
from core.public_designations import load,review_candidates

def render(scope,docs,*,prefix):
    def read(law,jo):
        d=docs.get(law)
        if not d:st.caption('본문 미수집');return
        a=next((a for a in d['articles'] if a['jo']==jo),None)
        if a:
            st.markdown(f'##### {law} 제{jo}조')
            st.caption('시행 '+d['effective'])
            st.write(a['text'])
        st.markdown('[공식 원문 ↗]('+d['source_url']+')')
    with st.expander('정의·적용범위 검토'):
        first,second,third=st.tabs(['정의·적용범위','민영화·특례','지정 변경'])
        with first:
            st.caption(scope['coverage'])
            col1,col2=st.columns(2)
            anchor=col1.selectbox('공운법 기준 조문',['전체','2','4','5','6'],key=prefix+'_scope_anchor')
            label=col2.selectbox('관계 유형',['전체',*scope['labels']],format_func=lambda k:scope['labels'].get(k,k),key=prefix+'_scope_label')
            rows=[r for r in scope['records'] if (anchor=='전체' or r['target_jo']==anchor) and (label=='전체' or label in r['labels'])]
            if rows:
                index=st.selectbox('인용 출처',range(len(rows)),format_func=lambda i:rows[i]['source_law']+' '+rows[i]['source_ref']+' → '+rows[i]['target_ref']+(' · 정의 경유' if rows[i]['kind']=='indirect' else ''),key=prefix+'_scope_record')
                r=rows[index];st.caption(' · '.join(scope['labels'][k] for k in r['labels']));st.write(r['context'])
                for step in r['path']:
                    st.caption(f"{step['law']} {step['source_ref']} → {step['target_law']} {step['target_ref']} · {step['raw']}")
                read(r['source_law'],r['source_jo'])
            else:st.caption('조건에 맞는 수집 근거가 없습니다. 영향 없음의 판정은 아닙니다.')
        with second:
            st.caption('적용대상과 적용배제를 함께 확인하세요. 법률 우선순위나 기관별 적용 여부를 자동 판정하지 않습니다.')
            guides=scope['privatization']
            if guides:
                i=st.selectbox('민영화법 검토 조문',range(len(guides)),format_func=lambda i:'제'+guides[i]['jo']+'조 · '+guides[i]['title'],key=prefix+'_private_guide')
                g=guides[i];read(g['law'],g['jo'])
                unique={(r['law'],r['jo']):r for r in g['related']}
                for r in unique.values():
                    with st.expander(r['law']+' '+r['jo']):
                        if r['collected']:read(r['law'],r['jo'])
                        else:st.caption('미수집 · 본문과 역인용 미점검');st.link_button('출처',r['url'])
        with third:
            register=load();st.caption(register['coverage'])
            events=sorted(register['events'],key=lambda e:(-e['year'],e['kind']))
            i=st.selectbox('지정 변경 발표',range(len(events)),format_func=lambda i:f"{events[i]['year']} · {events[i]['name']}",key=prefix+'_designation')
            e=events[i];st.write(f"{e['before'] or '신규 지정'} → {e['after']}");st.caption(e['review_basis'])
            s=next(s for s in register['sources'] if s['id']==e['source_id'])
            st.link_button('공식 발표 원문',s['pdf_url']+'#page='+str(s['page']))
            st.dataframe([{'조문':r['source_law']+' '+r['source_ref'],'확인사항':' · '.join(scope['labels'][k] for k in r['labels']),'근거':r['context']} for r in review_candidates(scope,e)],hide_index=True)
