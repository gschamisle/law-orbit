"""Independent land/building/housing screen using shared library and rendering."""
from core.housing_universe import BUNDLE
from core.housing_collection import PLAN, BUILDING, HOUSING
from ui.sector_map_ui import render as render_sector
PROFILE=dict(domain='housing',prefix='housing',title='국토건축주택',
             default_laws={'planning':PLAN,'building':BUILDING,'housing':HOUSING,'all':HOUSING},
             default_refs={'planning':'제56조','building':'제11조','housing':'제19조','all':'제19조'},
             outside_note='선택 분야 밖의 수집 조문입니다. 농지·산지 등 관련 인허가와 다른 분야의 조건도 원문에서 함께 확인하세요.')
def render(law_api_key='',openai_api_key=''):
    render_sector(PROFILE,BUNDLE)
