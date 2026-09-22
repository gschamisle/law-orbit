"""Add a version-bound forex/finance bridge without replacing any domain shard."""
import argparse
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import shutil

from core.forex_finance_links import PAIR, BRIDGE_KINDS, bridge
from core.citation_scope import Provision
from scripts.build_static_galaxies import Writer, EdgeIndex, tidy, shell, ROOT
from scripts.validate_static_galaxies import validate


def unpack(root, ref):
    if ref['url'] != 'data/'+ref['sha256']+'.json.gz':
        raise ValueError('Invalid static reference')
    raw = (root/ref['url']).read_bytes()
    if len(raw) != ref['bytes'] or hashlib.sha256(raw).hexdigest() != ref['sha256']:
        raise ValueError('Static edition checksum mismatch')
    return json.loads(gzip.decompress(raw))


def snapshot(root, domain):
    catalog = unpack(root, domain['catalog'])
    snap = dict(entries=catalog['laws'], documents={}, details={}, built_at=catalog['built_at'])
    for e in catalog['laws']:
        packed = unpack(root, e['file']); snap['documents'][e['id']] = packed
        details = dict(packed.get('details', {}))
        for part in e['parts']:
            details.update(unpack(root, part))
        if any(a['jo'] not in details for a in packed['articles']):
            raise ValueError('Missing source article details')
        snap['details'][e['id']] = details
    return snap


def payloads(result, snapshots):
    pair = result.get('pair', PAIR)
    graph = result['graph']; index = EdgeIndex(graph, result['documents'])
    edge_domains = {e['evidence_id']:(e['source_domain'],e['target_domain']) for e in graph['edges']}
    owners = {d: {e['name']: e for e in snapshots[d]['entries']} for d in pair}
    payload = {}
    for domain in pair:
        peer = next(d for d in pair if d != domain)
        ids = {name: e['id'] for name, e in owners[peer].items()}
        ids.update({name: e['id'] for name, e in owners[domain].items()})
        peer_entries = {}; laws = {}; broad = {}
        def belongs(r):
            source,target = edge_domains[r['evidence_id']]
            return (source if r['direction']=='forward' else target)==domain
        def row(r):
            value = tidy(r, ids, True)
            e = owners[peer][r['neighbor_law']]
            peer_entries[e['id']] = e
            value.update(cross_domain=True, neighbor_domain=peer, neighbor_sectors=e.get('sectors', []),
                         annex_unanalyzed=r.get('target_kind') == 'annex')
            return value
        for name, entry in owners[domain].items():
            law_details = {}
            for article in snapshots[domain]['documents'][entry['id']]['articles']:
                jo = article['jo']
                focus = index.focus(name, Provision(jo).label)
                rows = [row(r) for r in focus['rows'] if r['neighbor_law'] in owners[peer]
                        and r['neighbor_law'] not in owners[domain] and belongs(r)]
                suppressed = sorted(result['suppressed'][domain][entry['id']][jo])
                issues = sorted(result['resolved_issues'][domain][entry['id']][jo])
                if rows or suppressed or issues:
                    law_details[jo] = dict(rows=rows, suppressed=suppressed, resolved_issues=issues)
            if entry['articles']:
                first = snapshots[domain]['documents'][entry['id']]['articles'][0]['label']
                broad[entry['id']] = [row(r) for r in index.focus(name, first, broad=True)['broad_rows']
                    if r['neighbor_law'] in owners[peer] and r['neighbor_law'] not in owners[domain] and belongs(r)]
            if law_details:
                laws[entry['id']] = law_details
        payload[domain] = dict(kind=BRIDGE_KINDS[pair], schema=1, domain=domain, peer=peer,
            editions={d:snapshots[d]['built_at'] for d in pair}, entries=list(peer_entries.values()),
            laws=laws, broad={k:v for k,v in broad.items() if v}, coverage=graph['coverage_note'])
    return payload


def attach_bridge(root, manifest, writer=None, *, pair=PAIR):
    """Attach evidence for the exact editions in a newly generated static site."""
    if set(manifest.get('cross_domain', {})) & set(pair):
        raise ValueError('This build already has a bridge for this pair; use its original base')
    original_domains = json.loads(json.dumps(manifest['domains']))
    snapshots = {d:snapshot(root, next(e for e in manifest['domains'] if e['id']==d)) for d in pair}
    print('Source editions verified; building cross-domain evidence', flush=True)
    result = bridge(snapshots, pair=pair)
    payload = payloads(result, snapshots)
    writer = writer or Writer(root)
    manifest.setdefault('cross_domain', {}).update({d:writer.data(payload[d]) for d in pair})
    if manifest['domains'] != original_domains:
        raise ValueError('Existing domain metadata changed')
    return dict(result['report'], original_domains_unchanged=True,
                added_bytes=sum(manifest['cross_domain'][d]['bytes'] for d in pair),
                editions={d:snapshots[d]['built_at'] for d in pair})


def build(base, destination):
    base, destination = base.resolve(), destination.resolve()
    if destination.exists():
        raise ValueError('Choose a new destination; existing previews are preserved')
    validate(base)
    manifest = json.loads((base/'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('cross_domain'):
        raise ValueError('This build already has a bridge; use its original base')
    shutil.copytree(base, destination)
    shell(destination)
    # This feature does not revise the separately maintained introduction.
    shutil.copy2(base/'introduction.html', destination/'introduction.html')
    report = attach_bridge(destination, manifest)
    manifest.pop('version', None)
    manifest['version'] = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()[:20]
    (destination/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    report['verification'] = validate(destination)
    (destination.parent/(destination.name+'-report.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-site', type=Path, required=True)
    p.add_argument('--destination', type=Path, required=True)
    a=p.parse_args()
    print(json.dumps(build(a.base_site, a.destination), ensure_ascii=False, indent=2))
