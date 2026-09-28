"""Pin the four verified annex samples to their independently collected editions."""
import hashlib,json
from pathlib import Path
from xml.etree import ElementTree as ET
from core.annex_analysis import extract_annex,validate_analysis
from core.procurement_collection import safe_xml,collect_document,body_params
from core.medical_profile import ACTS
ROOT=Path(__file__).resolve().parents[1]
SAMPLES=ROOT/'output/medical-annex-feasibility-20260928'

def xml_digest(raw):
    def tree(e):return (e.tag,sorted(e.attrib.items()),(e.text or '').strip(),(e.tail or '').strip(),[tree(c) for c in e])
    return hashlib.sha256(json.dumps(tree(ET.fromstring(raw)),ensure_ascii=False).encode()).hexdigest()

def collect(request,item,as_of,**options):
    result=collect_document(request,item,as_of,**options)
    if item['name'] in ('의료법 시행규칙',ACTS):
        raw=safe_xml(request('lawService.do',body_params(item)))
        if hashlib.sha256(raw).hexdigest()!=result['body_sha256']:raise ValueError('별표 재조회 원문 불일치')
        result['annex_xml_structure_sha256']=xml_digest(raw)
    return result

def attach(source,folder=SAMPLES):
    specs=json.loads((folder/'samples.json').read_text(encoding='utf-8'))
    docs={d['name']:d for d in source['laws']+source['administrative_rules']}
    for spec in specs:
        medical=spec['id'].startswith('medical-')
        owner=docs['의료법 시행규칙' if medical else ACTS]
        raw=safe_xml((folder/spec['source_xml']).read_bytes())
        # A different edition must be collected and reviewed again, never grafted.
        if xml_digest(raw)!=owner.get('annex_xml_structure_sha256'):
            raise ValueError('검증한 별표 표본과 새로 수집한 본문 판본이 다릅니다.')
        ref='별표 '+spec['id'].split('-')[1] if medical else '별표'
        if not medical:
            node=ET.fromstring(raw).find('.//별표단위')
            if node is None or node.findtext('별표제목')!=spec['title']:raise ValueError('고시 별표 표제 불일치')
            urls=['https://www.law.go.kr'+node.findtext(t) for t in ('별표서식파일링크','별표서식PDF파일링크')]
            owner['annexes']=[dict(ref=ref,title=spec['title'],text=node.findtext('별표내용',''),effective=owner['effective'],urls=urls)]
        annex=next(a for a in owner['annexes'] if a['ref']==ref)
        if annex['title']!=spec['title'] or set(annex['urls'])!=set(spec['files'].values()):raise ValueError('별표 원본 파일 식별자 불일치')
        analysis=extract_annex(folder/(spec['id']+('.hwp' if medical else '.hwpx')),
                               (folder/(spec['id']+'-api.txt')).read_text(encoding='utf-8'))
        validate_analysis(analysis)
        annex['body_analysis']=analysis
    return source

def validate(source,graph):
    docs=source['laws']+source['administrative_rules']
    analyzed={(d['name'],a['ref']):a['body_analysis'] for d in docs for a in d.get('annexes',[]) if a.get('body_analysis')}
    if len(analyzed)!=4:raise ValueError('선정 별표 4개 원문 검증 필요')
    for a in analyzed.values():validate_analysis(a)
    for e in graph['edges']+graph['external_references']:
        if e.get('source_layer')!='annex-body':continue
        a=analyzed[(e['source_law'],e['source_jo'])]
        if e['source_text_sha256']!=a['text_sha256'] or e['source_file_sha256']!=a['file_sha256']:
            raise ValueError('별표 인용 판본 불일치')
        if a['text'][e['source_start']:e['source_end']]!=e['cite_raw']:raise ValueError('별표 인용 위치 불일치')
