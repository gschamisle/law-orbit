"""Independent foreign-exchange profile of the shared screen."""
from core.forex_universe import BUNDLE
from core.forex_collection import LAW, REGULATION
from ui.sector_map_ui import render as render_sector
PROFILE=dict(domain='forex',prefix='fx',title='외환',
             default_laws={'all':REGULATION,'common':LAW,'payment':REGULATION,'capital':REGULATION,'market':REGULATION,'reporting':REGULATION},
             default_refs={'all':'제7-1조','common':'제3조','payment':'제4-1조','capital':'제7-1조','market':'제2-1조','reporting':'제10-1조'},
             outside_note='선택 업무 밖의 관련 조문입니다. 지급·송금·자본거래·보고 의무의 요건을 원문에서 확인하세요.')
def render(law_api_key='',openai_api_key=''):
    render_sector(PROFILE,BUNDLE)
