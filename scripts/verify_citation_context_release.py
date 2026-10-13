"""Check frozen source ownership cases and both directions in a public build."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from core.citation_scope import parse_target
from scripts.static_storage import Storage
from scripts.build_citation_context_site import edge_id


def verify(site, plan_path):
    site = Path(site); storage = Storage(site)
    manifest = json.loads((site/'manifest.json').read_text(encoding='utf-8'))
    plan = json.loads(Path(plan_path).read_text(encoding='utf-8'))
    snapshots = {}
    for domain in {r['domain'] for r in plan['changes']}:
        cat = storage.read(next(d for d in manifest['domains'] if d['id'] == domain)['catalog'])
        entries, docs, details = {}, {}, {}
        for e in cat['laws']:
            entries[e['name']] = e
            doc = storage.read(e['file']); docs[e['name']] = doc
            rows = dict(doc['details'])
            for part in e['parts']: rows.update(storage.read(part))
            details[e['name']] = rows
        snapshots[domain] = entries, docs, details
    checked, reverse = set(), set()
    for item in plan['changes']:
        entries, docs, details = snapshots[item['domain']]
        law, jo, prior = item['law'], item['jo'], item['before']
        article = next(a for a in docs[law]['articles'] if a['jo'] == jo)
        if (entries[law]['effective'] != item['effective']
                or sha256(article['text'].encode()).hexdigest() != item['source_sha256']):
            raise ValueError('Frozen source edition changed')
        detail = details[law][jo]
        rows = detail['rows'] + detail.get('external', [])
        old_id = edge_id(law, jo, prior)
        if any(r['evidence_id'] == old_id for r in rows):
            raise ValueError('Old owner still displayed')
        for citation in item['after']:
            ident = edge_id(law, jo, citation)
            if ident in checked: continue
            checked.add(ident)
            matches = [r for r in rows if r['evidence_id'] == ident]
            if not matches: raise ValueError('Corrected citation missing')
            for row in matches:
                if article['text'][row['source_start']:row['source_end']] != citation['raw']:
                    raise ValueError('Source quote or offset changed')
                if row['target_law'] != citation['target_name']:
                    raise ValueError('Incorrect citation owner')
            target = citation['target_name']
            if target in entries:
                target_jo = parse_target(citation['target_ref'], allow_hyphen=True).jo
                reverse_rows = details[target][target_jo]['rows']
                # The reader merges one source phrase naming several targets
                # into one reverse row. Verify the phrase and actual target
                # page, not which sibling record supplied the merged row ID.
                if not any(r['direction'] == 'reverse' and r['source_law'] == law
                           and str(r['source_jo']) == jo and r['target_law'] == target
                           and r['source_start'] == citation['start']
                           and r['source_end'] == citation['end']
                           and r['raw'] == citation['raw'] for r in reverse_rows):
                    raise ValueError('Corrected reverse citation missing: '+repr((item['domain'],law,jo,target,target_jo,ident)))
                reverse.add(ident)
    return dict(status='passed', version=manifest['version'], corrected_evidence=len(checked),
                reverse_evidence=len(reverse), fields=len(snapshots))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--site', type=Path, required=True)
    p.add_argument('--plan', type=Path, default=Path('docs/qa/citation-context-corrections-20261013.json'))
    p.add_argument('--report', type=Path, required=True); a = p.parse_args()
    result = verify(a.site, a.plan)
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
