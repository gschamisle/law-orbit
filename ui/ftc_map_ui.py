"""Independent FTC menu using the shared law reader and graph screen."""
from core.ftc_universe import BUNDLE
from core.ftc_collection import FAIR
from ui.sector_map_ui import render as render_sector
PROFILE=dict(domain='ftc',prefix='ftc',title='공정거래',
    default_laws={'all':FAIR,'competition':FAIR,'groups':FAIR,'subcontract':'하도급거래 공정화에 관한 법률',
        'distribution':'가맹사업거래의 공정화에 관한 법률','consumer':'전자상거래 등에서의 소비자보호에 관한 법률',
        'procedure':'공정거래위원회 회의 운영 및 사건절차 등에 관한 규칙'},
    default_refs={'all':'제45조','competition':'제9조','groups':'제47조','subcontract':'제3조','distribution':'제7조','consumer':'제17조','procedure':'제1조'},
    outside_note='선택 분야 밖의 공정위 수집 자료입니다. 적용 요건과 예외는 각 법령·지침의 원문에서 확인하세요.')

def render(law_api_key='',openai_api_key=''):
    render_sector(PROFILE,BUNDLE)
