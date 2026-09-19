"""Procurement profile of the shared sector screen."""
from core.procurement_universe import BUNDLE
from core.procurement_collection import NATIONAL, LOCAL
from ui.sector_map_ui import render as render_sector
PROFILE=dict(domain='procurement',prefix='pc',title='조달·계약',
             default_laws={'national':NATIONAL,'procurement':NATIONAL,'local':LOCAL,'all':NATIONAL},
             default_refs={'national':'제27조','procurement':'제27조','local':'제27조','all':'제27조'},
             outside_note='다른 계약 분야의 수집 조문입니다. 국가계약과 지방계약에 같은 개정이 필요하다는 뜻은 아닙니다.')
def render(law_api_key='',openai_api_key=''):
    render_sector(PROFILE,BUNDLE)
