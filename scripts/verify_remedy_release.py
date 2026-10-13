"""Check selected procedural citations and source-bound notes in a built viewer."""
import argparse
import json
from pathlib import Path

from core.remedy_profile import STATUTES, CASE_EXPECTATIONS, APPEAL, LITIGATION, TAX, CUSTOMS, LOCAL, COMMISSION, HEALTH
from core.remedy_profile import INFORMATION, GREENBELT, REGIONAL, JEJU, COMPETITION, PEERS
from core.remedy_relations import validate_guide, procedural_edge
from core.candidate_evidence import case_proof
from scripts.static_storage import Storage
from scripts.build_forex_finance_site import snapshot

# Expected relationships were selected from the official text before collection.
# A law-wide citation has no invented target article number.
EXPECTED = (
    ('tax', TAX, '56', APPEAL, '15', '제15조'),
    ('customs', CUSTOMS, '120', APPEAL, '15', '제15조'),
    ('local_tax', LOCAL, '98', APPEAL, '15', '제15조'),
    ('labor', COMMISSION, '15의3', APPEAL, '18', '제18조'),
    ('medical', HEALTH, '90', LITIGATION, '', '행정소송법'),
    ('privacy', INFORMATION, '19', APPEAL, '', '행정심판법'),
    ('public_institutions', INFORMATION, '20', LITIGATION, '', '행정소송법'),
    ('housing', GREENBELT, '27', APPEAL, '6', '제6조'),
    ('state_property', REGIONAL, '78', APPEAL, '', '행정심판법'),
    ('state_property', JEJU, '350', APPEAL, '6', '제6조제3항'),
)


def verify(site):
    site = Path(site)
    manifest = json.loads((site / 'manifest.json').read_text(encoding='utf-8'))
    storage = Storage(site, manifest)
    ids = {'remedy', *PEERS}
    snaps = {d: snapshot(site, next(e for e in manifest['domains'] if e['id'] == d)) for d in ids}
    remedy = snaps['remedy']
    if {e['name'] for e in remedy['entries']} != set(STATUTES):
        raise ValueError('Unexpected remedy scope')
    docs = [dict(name=e['name'], effective=e['effective'], source_url=e['url'],
                 articles=remedy['documents'][e['id']]['articles']) for e in remedy['entries']]
    validate_guide(manifest['remedy_guide'], docs)
    overlays = {}
    for domain in ids:
        value = storage.read(manifest['cross_domain'][domain])
        overlays[domain] = [storage.read(ref) for ref in value['bridges']] if value['kind'] == 'domain-bridge-set' else [value]
    cases = []
    for domain, law, jo, target_law, target_jo, quote in EXPECTED:
        source = next(e for e in snaps[domain]['entries'] if e['name'] == law)
        target = next(e for e in remedy['entries'] if e['name'] == target_law)
        part = next(v for v in overlays[domain] if v['peer'] == 'remedy')
        rows = part['laws'].get(source['id'], {}).get(jo, {}).get('rows', [])
        matches = [r for r in rows if r['direction'] == 'forward' and r['neighbor_id'] == target['id']
                   and (r.get('neighbor_jo') == target_jo if target_jo else r['target_kind'] == 'law')
                   and quote in r['raw']]
        if not matches:
            raise ValueError('Missing selected procedure: ' + law + ' ' + jo)
        article = next(a for a in snaps[domain]['documents'][source['id']]['articles'] if a['jo'] == jo)
        target_articles = remedy['documents'][target['id']]['articles']
        if not any(a['text'] and (not target_jo or a['jo'] == target_jo) for a in target_articles):
            raise ValueError('Target body is unavailable')
        for row in matches:
            if article['text'][row['source_start']:row['source_end']] != row['raw']:
                raise ValueError('Source quote or offsets changed')
            if not target_jo and row['target_kind'] != 'law':
                raise ValueError('Law-wide reference became an invented article')
        cases.append(dict(domain=domain, source=law, source_jo=jo, source_effective=source['effective'],
                          target=target_law, target_jo=target_jo or None, target_effective=target['effective'],
                          evidence_ids=[r['evidence_id'] for r in matches]))
    # All added rows must touch the declared procedure scope, not merely a shared law.
    added_ids = set()
    for domain, parts in overlays.items():
        for part in parts:
            if not part['kind'].startswith('remedy-'):
                continue
            rows = [r for law in part['laws'].values() for detail in law.values() for r in detail['rows']]
            rows += [r for group in part['broad'].values() for r in group]
            for row in rows:
                if not procedural_edge(row):
                    raise ValueError('Non-procedural overlay: ' + row['evidence_id'])
                added_ids.add(row['evidence_id'])
    # Recheck all entry questions from the actual public rows.
    known = {(e['name'], a['jo']) for e in remedy['entries'] for a in remedy['documents'][e['id']]['articles']}
    proofs = []
    for (law, jo), expected in CASE_EXPECTATIONS.items():
        entry = next(e for e in remedy['entries'] if e['name'] == law)
        rows = remedy['details'][entry['id']][jo]['rows']
        edges = [{**r, 'cite_raw': r['raw']} for r in rows if r['direction'] == 'forward']
        proof = case_proof({'edges': edges}, expected, known_articles=known)
        if not proof['available']:
            raise ValueError('Unproven entry question: ' + law + ' ' + jo)
        proofs.append(dict(law=law, jo=jo, proof=proof))
    # Existing FTC wording must open the checked procedural note, even where
    # its references already resolve inside FTC and need no duplicate edge.
    ftc = snaps['ftc']
    entry = next(e for e in ftc['entries'] if e['name'] == COMPETITION)
    for jo in ('96', '99', '100'):
        article = next(a for a in ftc['documents'][entry['id']]['articles'] if a['jo'] == jo)
        note = next(n for n in manifest['remedy_guide']['entries'] if n['law'] == COMPETITION and n['jo'] == jo)
        if note['quote'] not in article['text']:
            raise ValueError('Existing FTC text cannot reuse the checked note')
    return dict(status='passed', version=manifest['version'], documents=len(docs),
                checked_notes=len(manifest['remedy_guide']['entries']),
                cross_domain_evidence=len(added_ids), cases=cases, entry_questions=proofs)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--site', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    args = p.parse_args()
    result = verify(args.site)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Procedural source cases passed: ' + str(len(result['cases'])))
