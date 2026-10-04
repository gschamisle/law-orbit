"""Source-first reverse recall, ownership, and body-click audit.

The frozen fixture is manually authored before app comparison. This tool reads
exported records; it never runs the production citation parser or network API.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from scripts.verify_tax_citation_samples import Site, actual_scopes, authored_scopes, covered, reference_scopes, compact

ROOT = Path(__file__).resolve().parents[1]


def audit(site, golden):
    results=[]; negatives=[]; provenance=[]; duplicate=[]
    for target in golden['targets']:
        law,jo=target['law'],target['jo']
        rows=[r for r in site.detail(law,jo).get('rows',[]) if r.get('direction')=='reverse']
        seen=set()
        for row in rows:
            key=(row.get('source_law'),row.get('source_jo'),row.get('source_start'),row.get('source_end'),row.get('target_ref'))
            if key in seen:duplicate.append(dict(law=law,jo=jo,row=compact(row)))
            seen.add(key)
        for source in target['annotations']+target['excluded']:
            body=site.article(source['source_law'],source['source_jo'])
            text=body['text']
            okay=(hashlib.sha256(text.encode()).hexdigest()==source['source_article_sha256']
                  and str(body.get('effective',''))==source['source_effective']
                  and text[source['paragraph_start']:source['paragraph_end']]==source['text'])
            provenance.append(dict(target_law=law,target_jo=jo,source_law=source['source_law'],source_jo=source['source_jo'],
                candidate_index=source['candidate_index'],outcome='source-matched' if okay else 'source-mismatch'))
            source_rows=[r for r in rows if r.get('source_law')==source['source_law'] and r.get('source_jo')==source['source_jo']
                         and isinstance(r.get('source_start'),int) and isinstance(r.get('source_end'),int)]
            if 'reason' in source:
                bad=[r for r in source_rows if r['source_start']<source['paragraph_end'] and r['source_end']>source['paragraph_start']]
                negatives.append(dict(target_law=law,target_jo=jo,source_law=source['source_law'],source_jo=source['source_jo'],
                    candidate_index=source['candidate_index'],reason=source['reason'],outcome='excluded-correctly' if not bad else 'wrong-owner-reverse-row',rows=[compact(r) for r in bad]))
                continue
            for annotation in source['expected']:
                found=[r for r in source_rows if r['source_start']<annotation['end'] and r['source_end']>annotation['start']]
                expected=[scope for ref in annotation['target_refs'] for scope in authored_scopes(ref)]
                scopes=[];refs=[];issues=[]
                for row in found:
                    if row.get('target_law')!=law:issues.append('wrong-target-law')
                    try:scopes.extend(actual_scopes(row))
                    except (ValueError,TypeError,KeyError):issues.append('malformed-scope')
                    # Reverse display groups at article level; the exact
                    # originally cited suffix is retained separately.
                    refs.extend(reference_scopes(row.get('target_ref_recorded',row.get('target_ref',''))))
                    entry=site.entries[source['source_law']]
                    if any(row.get(k)!=v for k,v in dict(neighbor_law=source['source_law'],neighbor_jo=source['source_jo'],
                       neighbor_id=entry['id'],source_id=entry['id']).items()):issues.append('wrong-source-click-destination')
                    if row.get('target_id')!=site.entries[law]['id']:issues.append('wrong-target-id')
                    if text[row['source_start']:row['source_end']]!=row.get('cite_raw',row.get('raw')):issues.append('wrong-source-span')
                missing_scope=[s for s in expected if not covered(s,scopes)]
                # Article ranges have a reverse record for the target's article;
                # lower ranges may retain their starting record and full scope.
                # The UI intentionally folds one source phrase citing several
                # destinations into one reverse row. Its representative
                # recorded ref can be a different member of that same list;
                # the full source scope must retain every expected member.
                # The reverse body button opens the SOURCE article (checked
                # above), so it does not click this representative target.
                missing_ref=[s for s in refs if not covered(s,scopes)]
                outcome=('matched' if found and not missing_scope and not missing_ref and not issues else
                         'missing-reverse-occurrence' if not found else 'inconsistent-reverse-record')
                results.append(dict(target_law=law,target_jo=jo,source_law=source['source_law'],source_jo=source['source_jo'],
                    candidate_index=source['candidate_index'],**annotation,outcome=outcome,missing_scopes=missing_scope,
                    missing_recorded_refs=missing_ref,issues=issues,rows=[compact(r) for r in found] if outcome!='matched' else []))
    failures=sum(r['outcome']!='matched' for r in results)+sum(r['outcome']!='excluded-correctly' for r in negatives)+sum(r['outcome']!='source-matched' for r in provenance)+len(duplicate)
    return dict(targets=len(golden['targets']),source_candidate_paragraphs=len(provenance),expected_occurrences=len(results),
        outcomes=dict(Counter(r['outcome'] for r in results)),negative_outcomes=dict(Counter(r['outcome'] for r in negatives)),
        provenance_outcomes=dict(Counter(r['outcome'] for r in provenance)),duplicate_rows=duplicate,failure_count=failures,
        results=results,negative_controls=negatives,source_checks=provenance,
        limits=golden['protocol']+' This reports recall within the frozen source discovery scope, not all statutory/semantic reverse relationships.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site',type=Path,required=True)
    parser.add_argument('--golden',type=Path,default=ROOT/'docs/qa/tax-reverse-source-samples-20261004.json')
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    report=args.report.resolve()
    if not report.is_relative_to((ROOT/'output').resolve()):raise SystemExit('Report must stay in project output/')
    raw=args.golden.read_bytes();golden=json.loads(raw)
    if golden['status']!='frozen-before-app-comparison':raise SystemExit('Only frozen source-first expectations accepted')
    site=Site(args.site)
    payload=audit(site,golden)|dict(golden_sha256=hashlib.sha256(raw).hexdigest(),site_version=site.manifest.get('version'))
    report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:payload[k] for k in ('targets','source_candidate_paragraphs','expected_occurrences','outcomes','negative_outcomes','provenance_outcomes','failure_count')},ensure_ascii=False))
    return 1 if payload['failure_count'] else 0


if __name__=='__main__':raise SystemExit(main())
