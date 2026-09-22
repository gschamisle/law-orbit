"""FTC profile over the shared citation engine, isolated from all existing corpora."""
from pathlib import Path
from core import procurement_universe as shared
from core.procurement_universe import documents,sector_graph,mark_sector,article_for,external_evidence
from core.ftc_collection import SECTORS,selected,FAIR

BUNDLE=Path(__file__).resolve().parents[1]/'output/ftc-universe/bundle.json'
COVERAGE=('공정거래위원회 소관 13개 법률군과 제목 범위로 선정한 집행규정·고시·심사지침입니다. '
          '경쟁·기업집단·하도급·가맹·유통·소비자·사건절차의 명시적 인용을 확인합니다. '
          '조문형 규정의 직접 인용·역인용과 문단형 지침이 법 조문을 명시적으로 인용한 근거를 분석합니다. '
          '지침 내부 문단 간 참조와 조문번호 중복 자료는 미분석입니다. '
          '별표·서식 본문, 부칙, 심결례·판례·표준계약서 및 의미상 관련성은 미분석입니다. '
          '다른 부처 법령은 인용 사실과 공식 링크를 남기며 본문·역인용 미점검입니다. '
          '인용 연결이 위법성·시장획정·과징금·연계개정 의무를 판정하지 않습니다.')

def build_graph(source):
    from core.ftc_text_citations import collect_text_citations,ftc_adapter
    rows,issues=collect_text_citations(source)
    graph=shared.build_graph(source,domain='ftc',coverage_note=COVERAGE,article_adapter=ftc_adapter)
    graph.update(text_citations=rows,text_citation_issues=issues)
    graph['coverage']['guidance_text']='explicit-citations; internal paragraph references not analyzed'
    return graph

def validate_bundle(bundle):
    shared.validate_bundle(bundle,domain='ftc')
    for d in documents(bundle['source']):
        if not selected(d['name'],d['managing_authority'],d['provider']):raise ValueError('공정거래 범위 외 자료')
    from core.ftc_text_citations import validate_text_citations
    validate_text_citations(bundle['source'],bundle['graph'].get('text_citations',[]))
    return bundle

def load_bundle(path=BUNDLE):
    import json
    return validate_bundle(json.loads(Path(path).read_text(encoding='utf-8')))

def present(data,graph,sector):return shared.present(data,graph,sector,domain='ftc',title='공정거래',sectors=SECTORS)

def report(bundle):
    result=shared.report(bundle,domain='ftc',sectors=SECTORS);result.pop('contract_rules',None)
    result['scheduled']=len(bundle['source'].get('scheduled',[]))
    result['excluded']=len(bundle['source']['inventory'].get('excluded',[]))
    result['text_analyzed_documents']=sum(bool(d.get('text_analysis')) for d in documents(bundle['source']))
    result['text_citations']=len(bundle['graph'].get('text_citations',[]))
    result['text_unresolved']=len(bundle['graph'].get('text_citation_issues',[]))
    return result

def overview_graph(bundle):
    """Document nodes may include text guidance; no fake article dust is created."""
    graph=bundle['graph'];docs=documents(bundle['source']);known={d['name'] for d in docs}
    edges=graph['edges']+[dict(r,type='direct') for r in graph.get('text_citations',[]) if r['target_law'] in known]
    connected={e[k] for e in edges for k in ('source_law','target_law')}
    catalog=[{k:v for k,v in d.items() if k not in ('articles','raw_body_blocks','annexes')} for d in docs if d['name'] in connected]
    names=[d['name'] for d in catalog]
    return {**graph,'laws':names,'focus_laws':names,'catalog':catalog,'edges':edges}
