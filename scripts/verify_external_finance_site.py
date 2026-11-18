"""Verify preserved sources and exact new cross-field destinations, offline."""
import argparse
import json
from pathlib import Path
from scripts.static_storage import Storage
from scripts.build_edition_refresh_site import load_details


def verify(base, site):
    old=json.loads((base/'manifest.json').read_text(encoding='utf-8'))
    new=json.loads((site/'manifest.json').read_text(encoding='utf-8'))
    before,after=Storage(base,old),Storage(site,new)
    domains={d['id']:d for d in new['domains']}
    original={d['id']:d for d in old['domains']}
    assert set(domains)==set(original)|{'export_finance'}
    assert all(domains[k]==v for k,v in original.items() if k!='forex')
    catalog=after.read(domains['forex']['catalog'])
    entries={e['name']:e for e in catalog['laws']}
    old_forex=before.read(original['forex']['catalog'])
    for e in old_forex['laws']:
        prior,current=before.read(e['file']),after.read(entries[e['name']]['file'])
        assert all(entries[e['name']][k]==e[k] for k in ('id','name','effective','url'))
        for key in ('source_notes','pdf_url','unparsed_provisions'):
            if key in e: assert entries[e['name']].get(key)==e[key], (e['name'],key)
            else: assert entries[e['name']].get(key) in (None,'',[]), (e['name'],key)
        fields=('jo','label','title','text','effective','deleted','reference_notes')
        assert [[a.get(k) for k in fields] for a in prior['articles']]==[[a.get(k) for k in fields] for a in current['articles']]
        assert current.get('annexes',[])==prior.get('annexes',[])
    assert set(entries)-{e['name'] for e in old_forex['laws']}=={'한국투자공사법','한국투자공사법 시행령'}
    export=after.read(domains['export_finance']['catalog'])
    assert len(export['laws'])==8
    assert not any('한국투자공사' in e['name'] for e in export['laws'])
    exim=next(e for e in export['laws'] if e['name']=='한국수출입은행법')
    assert exim['effective']=='20260722' and '285527' in exim['url']
    fixed=[]
    rule=entries['외국환거래규정'];doc=after.read(rule['file'])
    details=load_details(after,rule,doc)
    for jo,target in [('7-8','대외경제협력기금법 시행령'),('7-9','대외경제협력기금법 시행령'),('7-48','자본시장과 금융투자업에 관한 법률 시행령')]:
        rows=details[jo]['rows']+details[jo].get('external',[])+doc.get('broad',[])
        matches=[r for r in rows if r['source_jo']==jo and r['target_law']==target and '시행령' in (r.get('raw') or r.get('cite_raw',''))]
        assert matches,(jo,target)
        fixed.append(dict(law=rule['name'],jo=jo,target=target,evidence=len(matches)))
    pairs={}
    for domain, ref in new['cross_domain'].items():
        value=after.read(ref)
        payloads=[after.read(r) for r in value['bridges']] if value.get('kind')=='domain-bridge-set' else [value]
        for payload in payloads:
            if domain!='export_finance' and not (domain=='forex' and payload['peer']=='tax'):continue
            unique={r['evidence_id']:r for sections in payload['laws'].values() for d in sections.values() for r in d['rows']}
            for rows in payload.get('broad',{}).values(): unique.update({r['evidence_id']:r for r in rows})
            assert unique
            pairs[domain+'/'+payload['peer']]=dict(evidence=len(unique),
                article_references=sum(r.get('target_kind')=='article' for r in unique.values()),
                law_references=sum(r.get('target_kind')=='law' for r in unique.values()))
    assert 'export_finance/forex' in pairs and 'export_finance/tax' in pairs and 'export_finance/fsc' in pairs
    return dict(status='passed',version=new['version'],domains=len(domains),
        existing_domain_catalogs_preserved=len(original)-1,existing_forex_documents_preserved=len(old_forex['laws']),
        new_documents=10,new_articles=sum(e['articles'] for e in export['laws'])+sum(entries[n]['articles'] for n in ('한국투자공사법','한국투자공사법 시행령')),
        corrected_citations=fixed,pairs=pairs,physical_files=sum(p.is_file() for p in site.rglob('*')),
        limitation='명시적 인용과 검토 판본의 근거를 검증합니다. 개별 사업의 지원·투자 적격성을 판정하지 않습니다.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',type=Path,required=True);parser.add_argument('--site',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args();result=verify(args.base,args.site)
    args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
