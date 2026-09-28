"""Run manually selected official-PDF cases; never call this an accuracy estimate."""
import argparse
from collections import Counter
import json
from pathlib import Path
from core.procurement_pdf import analyze_pdf,validate_extraction
from core.procurement_pdf_structure import internal_links
from scripts.static_storage import Storage


def verify(extracted,site):
    storage=Storage(site)
    manifest=json.loads((site/'manifest.json').read_text(encoding='utf-8'))
    catalog=storage.read(next(d['catalog'] for d in manifest['domains'] if d['id']=='procurement'))
    corpus=[]
    for entry in catalog['laws']:
        doc=storage.read(entry['file'])
        corpus.append(dict(name=entry['name'],short_name=entry['label'],articles=doc['articles'],
            provider='eflaw' if entry['articles'] else 'admrul',uid=entry['id'],effective=entry['effective'],
            source_url=entry['url'],category='procurement'))
    spec=json.loads(Path('data/procurement-pdf-review-cases.json').read_text(encoding='utf-8'))
    sources={r['document_id']:r for r in json.loads(Path('data/procurement-pdf-sources.json').read_text(encoding='utf-8'))}
    analyzed={};results=[]
    for id in sources:
        d=json.loads((extracted/(id+'-extraction.json')).read_text(encoding='utf-8'));validate_extraction(d)
        if d['file_sha256']!=sources[id]['file_sha256']:raise ValueError('Review cases belong to a different PDF edition')
        rows,issues=analyze_pdf(d,corpus);links,unresolved=internal_links(d)
        analyzed[id]=dict(evidence=rows,issues=issues,internal=links,internal_issues=unresolved)
    for case in spec['cases']:
        doc=analyzed[case['document']]
        if case['kind']=='law':matches=[e for e in doc['evidence'] if e['source_page']==case['page'] and e['target_law']==case['law'] and e['target_ref']==case['reference']]
        else:matches=[e for e in doc['internal'] if e['source_page']==case['page'] and e['target_key']==case['target_key']]
        passed=not matches if case.get('expected')=='unresolved' else bool(matches)
        results.append(dict(id=case['id'],topic=case['topic'],passed=passed,matches=len(matches)))
    if not all(r['passed'] for r in results):raise ValueError('Source review failed: '+str([r for r in results if not r['passed']]))
    return dict(scope=spec['scope'],cases=results,analyzed=analyzed)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--extracted',type=Path,required=True)
    p.add_argument('--site',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    report=verify(a.extracted,a.site);a.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=len(report['cases']),documents={id:dict(citations=len(r['evidence']),internal=len(r['internal']),layers=dict(Counter(e['source_layer'] for e in r['evidence']))) for id,r in report['analyzed'].items()}),ensure_ascii=False))
