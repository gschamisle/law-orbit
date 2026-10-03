"""Reparse tax citations while preserving the published texts and history.

The reviewed rebuild input restores seven older local editions to the exact
public snapshot. It is not a new legal-data collection or a history refresh.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from core.annex_analysis import validate_analysis
from core.universe_builder import build_tax_universe
from scripts.build_static_galaxies import Writer, export_documents, overview, shell
from scripts.build_tax_review_site import check_current_texts
from scripts.build_procurement_pdf_site import materialize_reachable
from scripts.compact_static_galaxies import convert
from scripts.static_storage import Storage
from scripts.validate_static_galaxies import validate


def build(base, source_path, destination):
    base, destination = base.resolve(), destination.resolve()
    stage = destination.with_name(destination.name + '-unpacked')
    if destination.exists() or stage.exists():
        raise ValueError('Choose a new destination; previous sites are preserved')
    source_raw = source_path.read_bytes()
    source = json.loads(source_raw)
    manifest_raw = (base / 'manifest.json').read_bytes()
    original = json.loads(manifest_raw)
    storage = Storage(base)
    manifest = deepcopy(original)
    manifest.pop('data_packs', None)
    domain = next(d for d in manifest['domains'] if d['id'] == 'tax')
    catalog = storage.read(domain['catalog'])
    old_catalog = deepcopy(catalog)
    old_entries = {e['name']: e for e in catalog['laws']}
    check_current_texts(base, catalog, source)
    print('Verified all current tax editions and bodies', flush=True)

    # Keep the collection date; this run verifies citations in that snapshot.
    source['built_at'] = catalog['built_at']
    count = 0
    for law in source['laws']:
        public = source['public_annexes'][law['name']]
        annexes = {a['ref']: a for a in law.get('annexes', [])}
        if set(annexes) != {a['ref'] for a in public}:
            raise ValueError('Annex scope changed: ' + law['name'])
        for item in public:
            target = annexes[item['ref']]
            for key in ('ref', 'title', 'effective', 'urls'):
                target[key] = deepcopy(item[key])
            if item.get('analysis'):
                validate_analysis(item['analysis'])
                law.setdefault('source_url', old_entries[law['name']]['url'])
                target['body_analysis'] = deepcopy(item['analysis'])
                count += 1
    if count != 3:
        raise ValueError('Expected three preserved annex analyses')
    graph = build_tax_universe(source, annex_bodies=True)
    graph['coverage_note'] = catalog['coverage']
    public_annex_rows = {r['evidence_id']: r for items in source['public_annexes'].values()
                         for a in items for r in a.get('connections', [])}
    restored_annex_rows = set()
    for row in graph['edges'] + graph['external_references']:
        if row.get('source_layer') != 'annex-body':
            continue
        prior = public_annex_rows[row['evidence_id']]
        # Restoring a source edition can also populate a formerly blank target
        # URL. Preserve this metadata as part of the unchanged annex evidence.
        old_url, new_url = prior.get('target_url', ''), row.get('target_url', '')
        if old_url != new_url:
            target = old_entries.get(row['target_law'])
            if old_url or not target or new_url != target['url']:
                raise ValueError('Unexpected annex target URL change')
            row['target_url'] = old_url
        restored_annex_rows.add(row['evidence_id'])
    if restored_annex_rows != set(public_annex_rows):
        raise ValueError('Annex citation scope changed')
    print('Reparsed source citations and preserved three annex analyses', flush=True)

    stage.mkdir(parents=True)
    shell(stage)
    writer = Writer(stage)
    entries, ids = export_documents(writer, 'tax', '', source['laws'], graph)
    annex_count = 0
    for entry in entries:
        old_entry = old_entries[entry['name']]
        old_document = storage.read(old_entry['file'])
        new_document = Storage(stage).read(entry['file'])
        # Rebuilding citations cannot change annex content, verified evidence,
        # links, collection metadata, or unrelated document fields.
        if new_document.get('annexes') != old_document.get('annexes'):
            raise ValueError('Annex evidence changed: ' + entry['name'])
        annex_count += len(old_document.get('annexes', []))
        preserved = deepcopy(old_document)
        preserved.update(articles=new_document['articles'], details=new_document['details'],
                         broad=new_document['broad'])
        preserved['meta']['parts'] = entry['parts']
        current_entry = deepcopy(old_entry)
        current_entry.update(parts=entry['parts'], file=writer.data(preserved))
        entry.clear()
        entry.update(current_entry)
    check_current_texts(stage, dict(laws=entries), source)
    catalog.update(laws=entries, overview=writer.data(overview(graph, 'tax', ids, entries)))
    if catalog.get('delegation_review') != old_catalog.get('delegation_review'):
        raise ValueError('Historical comparison references changed')
    domain['catalog'] = writer.data(catalog)
    manifest.pop('version', None)
    manifest['version'] = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()[:20]
    (stage / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False,
                                                   separators=(',', ':')), encoding='utf-8')
    for old, new in zip(original['domains'], manifest['domains']):
        if old['id'] != 'tax' and old != new:
            raise ValueError('Unrelated domain changed')
    if original.get('cross_domain') != manifest.get('cross_domain'):
        raise ValueError('Cross-domain evidence changed')
    reachable = materialize_reachable(base, stage, manifest)
    # Export writes provisional metadata before preservation overlays. Remove
    # only files created by this writer that the final manifest does not reach.
    # Published snapshots and unrelated files are never candidates for deletion.
    for url in set(writer.assets) - reachable:
        path = (stage / url).resolve()
        if not path.is_relative_to((stage / 'data').resolve()):
            raise ValueError('Unsafe provisional asset path')
        path.unlink()
    convert(stage, destination, validate_site=False)
    print('Packed data; validating every domain and historical asset', flush=True)
    verification = validate(destination)
    packed = Storage(destination)
    packed_catalog = packed.read(domain['catalog'])
    check_current_texts(destination, packed_catalog, source)
    baselines = old_catalog.get('delegation_review', {}).get('baselines', {})
    for prior in baselines.values():
        if storage.raw(prior['file']) != packed.raw(prior['file']):
            raise ValueError('Historical baseline bytes changed')
    if source_path.read_bytes() != source_raw or (base / 'manifest.json').read_bytes() != manifest_raw:
        raise ValueError('Immutable input changed during build')
    report = dict(audited_at=datetime.now(timezone.utc).isoformat(), verification=verification,
                  base_manifest_sha256=hashlib.sha256(manifest_raw).hexdigest(),
                  source_sha256=hashlib.sha256(source_raw).hexdigest(),
                  data_version=manifest['version'], current_documents=len(entries),
                  current_articles=sum(len(d['articles']) for d in source['laws']),
                  collected_edges=len(graph['edges']), external_references=len(graph['external_references']),
                  citation_issues=len(graph.get('citation_issues', [])),
                  preserved_annexes=annex_count, preserved_annex_analyses=count,
                  preserved_annex_citations=len(restored_annex_rows),
                  preserved_historical_baselines=len(baselines),
                  untouched_domains=[d['id'] for d in original['domains'] if d['id'] != 'tax'],
                  source_unchanged=True, current_bodies_unchanged=True,
                  history_unchanged=True, cross_domain_unchanged=True)
    destination.with_name(destination.name + '-report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('base-site', 'source', 'destination'):
        p.add_argument('--' + name, type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(build(args.base_site, args.source, args.destination), ensure_ascii=False, indent=2))
