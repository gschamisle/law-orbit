"""Environment profile over the common citation and galaxy engines."""
from pathlib import Path
from core import procurement_universe as shared
from core.procurement_universe import documents,sector_graph,mark_sector,article_for,external_evidence

BUNDLE=Path(__file__).resolve().parents[1]/'output/environment-universe/bundle.json'
SECTORS={'environment':'환경관리','chemical':'화학물질','accident':'화학사고·안전','all':'전체 연결'}
COVERAGE=('선정한 환경·화학안전 중앙 법령과 핵심 행정규칙의 명시적 인용망입니다. '
          '화학물질관리·등록평가·생활화학제품과 산업안전·위험물·고압가스의 연결을 함께 살펴봅니다. '
          '모든 환경 고시·조례·기술기준을 수집한 것은 아닙니다. 별표·첨부파일 본문, 부칙, '
          'CAS 번호별 물질 목록·농도·수량 기준은 분석하지 않았습니다. '
          '인용 관계가 곧 동일한 규제 적용이나 동시개정 의무를 뜻하지는 않습니다.')

def build_graph(source):
    graph=shared.build_graph(source,domain='environment',coverage_note=COVERAGE)
    graph['coverage'].update(substance_identity='not-analyzed',thresholds='not-analyzed',ordinances='not-collected')
    return graph

def validate_bundle(bundle):return shared.validate_bundle(bundle,domain='environment')

def load_bundle(path=BUNDLE):return shared.load_bundle(path,domain='environment')

def present(data,graph,sector):
    return shared.present(data,graph,sector,domain='environment',title='환경화학안전',sectors=SECTORS)

def report(bundle):
    result=shared.report(bundle,domain='environment',sectors=SECTORS)
    result.pop('contract_rules',None)
    return result
