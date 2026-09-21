"""Housing profile over the shared citation engine, with exact context evidence."""
import re
from pathlib import Path
from core import procurement_universe as shared
from core.procurement_universe import documents, sector_graph, mark_sector, article_for, external_evidence

BUNDLE=Path(__file__).resolve().parents[1]/'output/housing-universe/bundle.json'
SECTORS={'planning':'도시계획','building':'건축','housing':'주택·정비','all':'전체 연결'}
COVERAGE=('선정한 국토·건축·주택 중앙 법령과 핵심 행정규칙의 명시적 인용망입니다. '
          '농지·산지·도로·하천·수도·하수도 법령은 관련 인허가 검토용으로 별도 수집했습니다. '
          '모든 국토부 고시·기준이나 조례를 수집한 것은 아닙니다. '
          '장·절·항목 형식, 첨부파일·별표 본문·부칙은 조문 연결 미분석입니다. '
          '인용·의제·위임 문구는 검토 단서이며 자동으로 동시개정 의무를 뜻하지 않습니다.')


def context_evidence(source):
    rows=[]
    for d in documents(source):
        for a in d.get('articles',[]):
            if a.get('deleted'):continue
            # Preserve full paragraph offsets, never resolve an unnamed ordinance.
            for m in re.finditer(r'[^\n]+',a['text']):
                text=m[0]
                kinds=[]
                if re.search(r'조례(?:로|에서)\s*(?:정|규정)|조례에\s*(?:따|위임)',text):
                    kinds.append('조례 위임·참조 문구')
                if re.search(r'의제|(?:받은|한|얻은)\s*것으로\s*본다',text) and re.search(r'허가|인가|승인|신고|협의|면허|결정|등록',a['text']):
                    kinds.append('인허가 의제 문맥')
                for kind in kinds:
                    rows.append(dict(kind=kind,source_law=d['name'],source_jo=a['jo'],
                        source_start=m.start(),source_end=m.end(),raw=text,
                        source_effective=d['effective'],source_url=d['source_url'],
                        status='문맥 검토 필요',ordinance_status='not-collected'))
    return rows


def build_graph(source):
    g=shared.build_graph(source,domain='housing',coverage_note=COVERAGE)
    g['context_evidence']=context_evidence(source)
    g['coverage']['ordinances']='not-collected; explicit-delegation-text-only'
    g['coverage']['permit_deeming']='explicit-context-candidates; not-automatic-amendment-obligations'
    return g


def validate_bundle(bundle):
    shared.validate_bundle(bundle,domain='housing')
    if bundle['graph'].get('context_evidence')!=context_evidence(bundle['source']):
        raise ValueError('의제·조례 위임 근거가 수집 원문과 일치하지 않습니다.')
    return bundle


def load_bundle(path=BUNDLE):
    import json
    return validate_bundle(json.loads(Path(path).read_text(encoding='utf-8')))


def present(data,graph,sector):
    return shared.present(data,graph,sector,domain='housing',title='국토건축주택',sectors=SECTORS)


def report(bundle):
    result=shared.report(bundle,domain='housing',sectors=SECTORS)
    result.pop('contract_rules',None)
    result['context_evidence']={kind:sum(e['kind']==kind for e in bundle['graph']['context_evidence'])
                                for kind in ('조례 위임·참조 문구','인허가 의제 문맥')}
    return result
