"""National property profile: explicit citations and a separate official annex register."""
from pathlib import Path
from core import procurement_universe as shared
from core.procurement_universe import documents,sector_graph,mark_sector,article_for,external_evidence
from core.state_property_collection import PROPERTY,SPECIAL
from core.state_property_special import validate_register

BUNDLE=Path(__file__).resolve().parents[1]/'output/state_property-universe/bundle.json'
SECTORS={'core':'국유재산 기본체계','special':'특례 근거 법률','administration':'관리·처분 지침','all':'전체 연결'}
COVERAGE=('국유재산법·국유재산특례제한법과 하위법령, 재정경제부·기획재정부 소관의 제목 기반 선정 행정규칙, '
          '특례제한법 별표에 명시된 근거 법률을 수집했습니다. 근거 법률은 별표 등재 조문과 국유재산 기본 법령을 '
          '명시적으로 인용하는 조문을 중심으로 연결을 분석합니다. 모든 국유재산 관련 법령·지침의 전수 목록은 아닙니다. '
          '별표 등재 관계는 특례 목록에서 별도로 제공하며 직접 인용선에 섞지 않습니다. '
          '별표상 기한·유형은 적용 판단이 아니며 항·호 요건, 부칙·경과조치, 다른 별표·첨부파일 본문은 별도 확인이 필요합니다.')

def build_graph(source):
    graph=shared.build_graph(source,domain='state_property',coverage_note=COVERAGE)
    related=set(source['related_laws'])
    core={d['name'] for d in documents(source)}-related
    selected={}
    for row in source['special_cases']['rows']:
        selected.setdefault(row['law'],set()).update(row.get('article_numbers',[]))
    # Full bodies are readable, but unrelated networks of the annex laws are not
    # imported into this domain. Reverse references to core laws remain included.
    for edge in graph['edges']:
        if edge['source_law'] in related and edge['target_law'] in core:
            selected.setdefault(edge['source_law'],set()).add(edge['source_jo'])
    def included(e):
        return e['source_law'] in core or e['source_jo'] in selected.get(e['source_law'],set())
    for key in ('edges','external_references','citation_issues','context_evidence'):
        if key in graph:graph[key]=[e for e in graph[key] if included(e)]
    for doc in documents(source):
        if doc['name'] in related:doc['analyzed_articles']=sorted(selected.get(doc['name'],set()))
    graph['coverage'].update(special_annex='separate-verified-register',related_laws='listed-articles-and-direct-core-references')
    return graph

def validate_bundle(bundle):
    shared.validate_bundle(bundle,domain='state_property')
    validate_register(bundle['source']['special_cases'],bundle['source'])
    byname={d['name']:d for d in documents(bundle['source'])}
    for e in bundle['graph']['edges']+bundle['graph']['external_references']:
        doc=byname[e['source_law']]
        if 'analyzed_articles' in doc and e['source_jo'] not in doc['analyzed_articles']:
            raise ValueError('특례 근거 법률의 분석 범위를 벗어난 인용입니다.')
    return bundle

def load_bundle(path=BUNDLE):
    import json
    return validate_bundle(json.loads(Path(path).read_text(encoding='utf-8')))

def present(data,graph,sector):
    from core.state_property_layout import layout
    return layout(shared.present(data,graph,sector,domain='state_property',title='국유재산',sectors=SECTORS),graph)

def report(bundle):
    from collections import Counter
    result=shared.report(bundle,domain='state_property',sectors=SECTORS);result.pop('contract_rules',None)
    rows=bundle['source']['special_cases']['rows']
    result.update(special_cases=len(rows),special_status=dict(Counter(r['status'] for r in rows)),
                  deadline_status=dict(Counter(r['deadline_status'] for r in rows)),
                  analyzed_articles=sum(len(d.get('analyzed_articles',d.get('articles',[]))) for d in documents(bundle['source'])))
    return result
