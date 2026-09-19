"""Offline audit of the actual independently collected financial snapshot."""
from __future__ import annotations
import json
from core.fsc_collection import atomic_json
from core.fsc_universe import BUNDLE, load_bundle
from core.fsc_sectors import SECTORS, sector_graph, mark_sector
from core.fsc_bylaws import BYLAWS
from core.galaxy_focus import analyze_focus

def verify() -> dict:
    bundle=load_bundle();source,graph=bundle['source'],bundle['graph']
    rules=source['administrative_rules'];docs=source['laws']+rules
    assert len({d['uid'] for d in docs})==len(docs)
    assert all(d.get('body_sha256') and d.get('document_id') and d.get('version_id') for d in docs)
    assert all(d.get('sectors') and set(d['sectors']) <= set(SECTORS)-{'all'} for d in docs)
    layers=source['inventory']['layers']
    assert len(source['laws'])+sum(r['provider']=='eflaw' for r in source['scheduled'])==layers['eflaw']['received']
    assert len(rules)+sum(r['provider']=='admrul' for r in source['scheduled'])==sum(l['received'] for l in layers.values() if l['provider']=='admrul')
    fss=[d for d in rules if d['managing_authority']=='금융감독원']
    assert {d['name'] for d in fss}==set(BYLAWS)
    assert all(d['body_status']=='indexed-administrative-text' and d['articles'] for d in fss)
    texts={(d['name'],a['jo']):a['text'] for d in docs for a in d['articles']}
    checked=0
    for e in graph['edges']+graph['external_references']:
        if e['source_granularity']=='annex':continue
        assert texts[e['source_law'],e['source_jo']][e['source_start']:e['source_end']]==e['cite_raw']
        checked+=1
    for issue in graph['citation_issues']:
        assert texts[issue['source_law'],issue['source_jo']][issue['start']:issue['end']]==issue['raw']
    examples=[]
    for bylaw,regulation in (('보험업감독업무시행세칙','보험업감독규정'),('은행업감독업무시행세칙','은행업감독규정'),('금융투자업규정시행세칙','금융투자업규정')):
        edge=next(e for e in graph['edges'] if e['source_law']==bylaw and e['target_law']==regulation and e['target_kind']=='article' and e.get('target_provision_status')=='collected')
        result=analyze_focus(regulation,edge['target_ref'],graph)
        assert any(r['direction']=='reverse' and r['source_law']==bylaw for r in result['rows'])
        result=analyze_focus(bylaw,edge['source_jo'],graph)
        assert any(r['direction']=='forward' and r['target_law']==regulation for r in result['rows'])
        examples.append(dict(source=bylaw,source_ref=edge['source_ref'],target=regulation,target_ref=edge['target_ref']))
    example=mark_sector(analyze_focus('보험업감독규정','4-10',graph),graph,'insurance')
    assert any(r['out_of_sector'] and r['target_law']=='은행법' for r in example['rows'])
    result=dict(built_at=graph['built_at'],statutes=len(source['laws']),administrative_bodies=len(rules),
                fss_bylaws=len(fss),indexed_administrative_rules=graph['administrative_rules_indexed'],
                administrative_articles=graph['administrative_articles'],internal_evidence=len(graph['edges']),
                outside_map_evidence=len(graph['external_references']),verified_citation_spans=checked,
                verified_review_spans=len(graph['citation_issues']),sector_documents={s:len(sector_graph(graph,s)['laws']) for s in SECTORS},
                unindexed=[dict(name=d['name'],reason=d.get('analysis_error',d.get('coverage',{}).get('provisions'))) for d in rules if not d['articles']],
                bidirectional_examples=examples,cross_sector_example='보험업감독규정 제4-10조 → 은행법 제2조',
                scope='금융위 법령·행정규칙 + 명시한 금감원 시행세칙 28건',status='passed')
    atomic_json(BUNDLE.parent/'sector-verification.json',result)
    return result

if __name__=='__main__':
    print(json.dumps(verify(),ensure_ascii=False,indent=2))
