"""Independent environment/chemical-safety profile of the shared screen."""
from core.environment_universe import BUNDLE
from core.environment_collection import ENVIRONMENT,CHEMICAL,SAFETY
from ui.sector_map_ui import render as render_sector
PROFILE=dict(domain='environment',prefix='env',title='환경·화학안전',
             default_laws={'environment':ENVIRONMENT,'chemical':CHEMICAL,'accident':SAFETY,'all':SAFETY},
             default_refs={'environment':'제6조','chemical':'제10조','accident':'제23조','all':'제23조'},
             outside_note='선택 분야 밖의 수집 조문입니다. 화학물질·환경·산업안전·위험물 법령마다 적용 대상과 요건을 원문에서 확인하세요.')
def render(law_api_key='',openai_api_key=''):
    render_sector(PROFILE,BUNDLE)
