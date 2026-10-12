"""Check selected ACRC public-reader chains against official source expectations."""
import argparse
import json
from pathlib import Path
from core.integrity_profile import GRAFT, REPORT, CONFLICT, ANTICORRUPTION, REFUND
from scripts.static_storage import Storage
from scripts.build_forex_finance_site import snapshot

# Official excerpts/MSTs frozen before collection; not chosen from output counts.
EXPECTED = (
    ('integrity', CONFLICT+' 시행령', '14', 'procurement', '국가를 당사자로 하는 계약에 관한 법률 시행령', '26', '제26조제1항제2호'),
    ('integrity', CONFLICT+' 시행령', '14', 'procurement', '지방자치단체를 당사자로 하는 계약에 관한 법률 시행령', '25', '제25조제1항제4호'),
    ('integrity', CONFLICT, '2', 'public_institutions', '공공기관의 운영에 관한 법률', '4', '제4조'),
    ('public_institutions', GRAFT, '15', 'integrity', REPORT, '2', '제2조제6호'),
    ('subsidy', REFUND, '23', 'integrity', ANTICORRUPTION, '69', '제69조'),
)


def verify(site):
    site=Path(site); manifest=json.loads((site/'manifest.json').read_text(encoding='utf-8'))
    storage=Storage(site,manifest)
    domains={d for e in EXPECTED for d in (e[0],e[3])}
    snaps={d:snapshot(site,next(e for e in manifest['domains'] if e['id']==d)) for d in domains}
    overlays={}
    for domain in domains:
        value=storage.read(manifest['cross_domain'][domain])
        overlays[domain]=[storage.read(ref) for ref in value['bridges']] if value['kind']=='domain-bridge-set' else [value]
    results=[]
    for source_domain,source_law,source_jo,target_domain,target_law,target_jo,quote in EXPECTED:
        source=next(e for e in snaps[source_domain]['entries'] if e['name']==source_law)
        target=next(e for e in snaps[target_domain]['entries'] if e['name']==target_law)
        part=next(v for v in overlays[source_domain] if v['peer']==target_domain)
        rows=part['laws'][source['id']][source_jo]['rows']
        matches=[r for r in rows if r['direction']=='forward' and r['neighbor_id']==target['id'] and r['neighbor_jo']==target_jo and quote in r['raw']]
        if not matches:raise ValueError('Missing preselected official-source bridge: '+source_law+' '+source_jo)
        article=next(a for a in snaps[source_domain]['documents'][source['id']]['articles'] if a['jo']==source_jo)
        if not any(a['jo']==target_jo and a['text'] for a in snaps[target_domain]['documents'][target['id']]['articles']):
            raise ValueError('Connected body is unavailable')
        back=next(v for v in overlays[target_domain] if v['peer']==source_domain)
        reverse=back['laws'].get(target['id'],{}).get(target_jo,{}).get('rows',[])
        local_source=next((e for e in snaps[target_domain]['entries'] if e['name']==source_law and e['effective']==source['effective']),None)
        local_reverse=snaps[target_domain]['details'][target['id']][target_jo]['rows'] if local_source else []
        for row in matches:
            if article['text'][row['source_start']:row['source_end']]!=row['raw']:
                raise ValueError('Quote offset changed')
            cross_match=any(r['evidence_id']==row['evidence_id'] and r['direction']=='reverse' and r['neighbor_id']==source['id'] for r in reverse)
            local_match=bool(local_source and any(r['direction']=='reverse' and r['neighbor_id']==local_source['id'] and r['neighbor_jo']==source_jo and r['raw']==row['raw'] for r in local_reverse))
            if not cross_match and not local_match:raise ValueError('Matching reverse evidence is unavailable')
        results.append(dict(source=source_law,source_jo=source_jo,target=target_law,target_jo=target_jo,
                            source_domain=source_domain,target_domain=target_domain,evidence_ids=[r['evidence_id'] for r in matches]))
    return dict(status='passed',version=manifest['version'],cases=results)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--site',type=Path,required=True);p.add_argument('--report',type=Path,required=True)
    a=p.parse_args();result=verify(a.site);a.report.parent.mkdir(parents=True,exist_ok=True)
    a.report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Official-source cross-domain cases passed: '+str(len(result['cases'])))
