"""Foreign-exchange profile; explicit citations across all identifiable main articles."""
from pathlib import Path
from core import procurement_universe as shared
from core.procurement_universe import documents,sector_graph,mark_sector,article_for,external_evidence
from core.forex_collection import SECTORS

BUNDLE=Path(__file__).resolve().parents[1]/'output/forex-universe/bundle.json'
COVERAGE=('외국환거래법·시행령, 선정한 외환 관련 행정규칙 8종과 한국은행 세칙·절차 4종의 수집 본문을 분석합니다. '
          '한국은행 자료는 공식 법규정보 목록과 PDF의 개정일·부칙 시행일을 대조합니다. '
          '업무 태그는 조문 제목·본문 키워드에 따른 탐색 보조 분류이며 법적 적용범위의 판정이 아닙니다. '
          '수집 본칙 중 조문번호를 식별할 수 있는 전체 조문의 명시적 인용을 분석하며, 별표·서식 본문·부칙의 인용과 상대 참조 일부는 미분석입니다. '
          '미수집 외부 법령의 본문·역인용은 점검하지 않았고 인용선은 동시개정 의무를 뜻하지 않습니다.')

def build_graph(source):
    graph=shared.build_graph(source,domain='forex',coverage_note=COVERAGE)
    graph['allow_hyphen']=True
    graph['article_catalog']={d['name']:[{k:a.get(k,[]) for k in ('jo','title','sectors')} for a in d['articles']] for d in documents(source)}
    graph['unparsed_provisions']=[dict(law=d['name'],**a) for d in documents(source) for a in d.get('unparsed_provisions',[])]
    graph['coverage'].update(source_provisions='all-identifiable-main-articles',bok_source='official-listed-consolidated-PDF')
    return graph

def validate_bundle(bundle):
    shared.validate_bundle(bundle,domain='forex')
    if not bundle['graph'].get('allow_hyphen'):raise ValueError('외환 조문번호 설정 누락')
    for d in documents(bundle['source']):
        if not d.get('articles'):raise ValueError('외환 수집 문서의 조문 분석 누락')
        if d.get('analyzed_articles') is not None:raise ValueError('외환 본칙 분석 범위를 제한할 수 없습니다.')
    return bundle

def load_bundle(path=BUNDLE):
    import json
    return validate_bundle(json.loads(Path(path).read_text(encoding='utf-8')))

def present(data,graph,sector):
    from core.forex_layout import layout
    result=layout(shared.present(data,graph,sector,domain='forex',title='외환',sectors=SECTORS),graph)
    if sector!='all' and result.get('mode')=='overview':result['dust']=[a for a in result['dust'] if sector in a['sectors']]
    return result

def mark_sector(result,graph,sector):
    from copy import deepcopy
    result=deepcopy(result)
    tags={(name,a['jo']):a['sectors'] for name,articles in graph['article_catalog'].items() for a in articles}
    docs={d['name']:d['sectors'] for d in graph['catalog']}
    for row in result['rows']+result.get('broad_rows',[]):
        tag=tags.get((row['neighbor_law'],row['neighbor_jo']),[]) if row['neighbor_kind']=='article' else docs.get(row['neighbor_law'],[])
        outside=sector!='all' and sector not in tag
        row.update(out_of_sector=outside,sector_relation='분야 밖 관련 조문' if outside else '선택 분야')
    return result


def report(bundle):
    result=shared.report(bundle,domain='forex',sectors=SECTORS);result.pop('contract_rules',None)
    result['bok_rules']=sum(d['provider']=='bok' for d in documents(bundle['source']))
    result['api_administrative_rules']=sum(d['provider']=='admrul' for d in documents(bundle['source']))
    result['unparsed_provisions']=len(bundle['graph'].get('unparsed_provisions',[]))
    return result
