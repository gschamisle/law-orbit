"""Small configuration adapter; state and source files remain independent."""
from core.mofe_profiles import PROFILES
from core.mofe_universe import path
from ui.sector_map_ui import render as render_sector

def render(domain):
    p=PROFILES[domain]
    render_sector(dict(domain=domain,prefix='mofe_'+domain,title=p['title'],
        default_laws={s:p['default'] for s in p['sectors']},default_refs={'all':'제1조'},
        outside_note='선택 업무 밖의 수집 조문입니다. 인용 원문과 적용 조건을 함께 확인하세요.'),path(domain))
