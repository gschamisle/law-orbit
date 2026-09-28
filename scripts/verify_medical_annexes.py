"""Reproducible opt-in medical annex pilot; never writes an active domain bundle.

Uses the four previously collected official samples and two independently
collected target laws. --collect-targets is the only network-enabled step.
"""
import argparse
from collections import Counter
from copy import deepcopy
from functools import partial
import json
from pathlib import Path
from xml.etree import ElementTree as ET

from core.annex_analysis import extract_annex,validate_analysis
from core.fsc_administrative import index_rule
from core.fsc_collection import LawTransport,atomic_json,CollectionError
from core.fsc_credentials import law_api_key
from core.procurement_collection import discover_query,record,collect_document
from core.universe_builder import build_universe
from core.galaxy_focus import analyze_focus
from scripts.collect_law_universe import parse_body

ROOT=Path(__file__).resolve().parents[1]
SAMPLES=ROOT/'output/medical-annex-feasibility-20260928'
OUTPUT=ROOT/'output/medical-annex-analysis-20260928'
TARGETS=('의료법','간호사의 진료지원업무 수행에 관한 규칙')


def collect_target(name,folder,as_of='20260928',domain='medical'):
    selector=lambda n,a,p:n==name and p=='eflaw'
    request=LawTransport(law_api_key(),attempts=2,timeout=35)
    records=discover_query(request,'eflaw',name,as_of,record_factory=partial(record,selector=selector,domain=domain))
    candidates=[r for r in records['records'] if r['state']=='current-candidate'] if isinstance(records,dict) else []
    if not candidates: raise CollectionError('required-current-law-not-found')
    chosen=max(candidates,key=lambda r:(r['effective'],r['promulgated'],r['version_id']))
    document=collect_document(request,chosen,as_of);document['category']=domain
    atomic_json(folder/(name+'.json'),document)
    return document


def run():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--collect-targets',action='store_true')
    args=parser.parse_args();OUTPUT.mkdir(parents=True,exist_ok=True)
    documents=[]
    for name in TARGETS:
        cache=OUTPUT/(name+'.json')
        if cache.exists(): documents.append(json.loads(cache.read_text(encoding='utf-8')))
        elif args.collect_targets:
            documents.append(collect_target(name,OUTPUT));print('대상 법령 확보:',name,flush=True)
        else: raise ValueError('대상 판본 자료 없음: --collect-targets로 먼저 수집하세요.')
    root=ET.parse(SAMPLES/'medical.xml').getroot()
    medical=parse_body(root,dict(name='의료법 시행규칙',law_id='007863',mst='286963',category='medical',family='의료법',provider='eflaw',source_url='https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=286963&efYd=20260612'))
    nr=ET.parse(SAMPLES/'nursing.xml').getroot()
    nursing=index_rule(dict(name='간호사의 진료지원업무 수행행위 목록 고시',provider='admrul',category='medical',effective='20260811',source_url='https://www.law.go.kr/LSW/admRulLsInfoP.do?admRulSeq=2100000282180',raw_body_blocks=[n.text or '' for n in nr.findall('조문내용')]))
    nursing['annexes']=[dict(ref='별표',title='진료지원업무에 포함되는 행위 (제2조 관련)',effective='20260811',urls=[])]
    samples=json.loads((SAMPLES/'samples.json').read_text(encoding='utf-8'))
    for spec in samples:
        name=spec['id'];owner=medical if name.startswith('medical') else nursing
        ref='별표 '+name.split('-')[1] if owner is medical else '별표'
        annex=next(a for a in owner['annexes'] if a['ref']==ref)
        ext='hwp' if owner is medical else 'hwpx'
        analysis=extract_annex(SAMPLES/(name+'.'+ext),(SAMPLES/(name+'-api.txt')).read_text(encoding='utf-8'))
        validate_analysis(analysis);annex.update(body_analysis=analysis,urls=list(spec['files'].values()))
        atomic_json(OUTPUT/(name+'-analysis.json'),analysis)
    documents += [medical,nursing]
    source=dict(laws=documents,built_at='20260928',provider='official-sample-pilot',domain='medical')
    before=deepcopy(source)
    graph=build_universe(source,focus_categories=('medical',),preserve_external=True,annex_bodies=True)
    assert source==before,'Build mutated the source'
    body_edges=[e for e in graph['edges'] if e.get('source_layer')=='annex-body']
    external=[e for e in graph['external_references'] if e.get('source_layer')=='annex-body']
    staff=[e for e in body_edges if e['source_law']=='의료법 시행규칙' and e['source_jo']=='별표 5' and e['target_law']=='의료법']
    assert len(staff)==9,(len(staff),'정원표 인용 9곳이 모두 보존되어야 합니다.')
    assert Counter(e['target_ref'] for e in staff)=={'제43조제1항':3,'제43조제2항':3,'제43조제3항':3}
    reverse=analyze_focus('의료법','43',graph)
    assert sum(r.get('source_layer')=='annex-body' and r['source_jo']=='별표 5' for r in reverse['rows'])==9
    assert len({e['evidence_id'] for e in body_edges+external})==len(body_edges+external)
    for edge in body_edges+external:
        doc=next(d for d in documents if d['name']==edge['source_law'])
        annex=next(a for a in doc['annexes'] if a['ref']==edge['source_jo'])
        assert annex['body_analysis']['text'][edge['source_start']:edge['source_end']]==edge['cite_raw']
    report=dict(samples=4,units=sum(len(a['body_analysis']['units']) for d in documents for a in d.get('annexes',[]) if a.get('body_analysis')),
                collected_target_evidence=len(body_edges),external_target_evidence=len(external),staff_citations=len(staff),staff_reverse_citations=9,
                coverage=graph['annex_analysis']['coverage'],issues=graph['annex_analysis']['issues'],
                not_run=['의료 분야 전수 수집','이미지 OCR','산식·정원 적합성 판단','별표 내부 참조 완전 해석','공개 배포'])
    atomic_json(OUTPUT/'source.json',source);atomic_json(OUTPUT/'graph.json',graph);atomic_json(OUTPUT/'verification.json',report)
    print(json.dumps({k:v for k,v in report.items() if k not in ('coverage','issues')},ensure_ascii=False,indent=2))


if __name__=='__main__': run()
