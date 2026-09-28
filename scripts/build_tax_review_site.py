"""Rebuild only national-tax evidence on an immutable, packed public snapshot."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from core.universe_builder import build_tax_universe
from core.domain_navigation import DOMAINS
from scripts.build_static_galaxies import Writer, export_documents, overview, shell
from scripts.build_procurement_pdf_site import materialize_reachable
from scripts.compact_static_galaxies import convert
from scripts.delegation_baseline import attach_catalog, attach_official_history
from scripts.static_storage import Storage
from scripts.validate_static_galaxies import validate

LABEL_DOMAINS = ('procurement', 'housing', 'environment')


def refresh_display_names(writer, base, manifest):
    """Rename three presentation labels, preserving their law/evidence assets."""
    storage = Storage(base)
    for domain in manifest['domains']:
        if domain['id'] not in LABEL_DOMAINS:
            continue
        old_title, new_title = domain['title'], DOMAINS[domain['id']]
        catalog = storage.read(domain['catalog'])
        original = deepcopy(catalog)
        map_data = storage.read(catalog['overview'])
        map_data['galaxy_title'] = map_data.get('galaxy_title', old_title).replace(old_title, new_title)
        catalog['overview'] = writer.data(map_data)
        if {k:v for k,v in catalog.items() if k != 'overview'} != {k:v for k,v in original.items() if k != 'overview'}:
            raise ValueError('Display rename changed law data')
        domain.update(title=new_title, catalog=writer.data(catalog))


def check_current_texts(base, catalog, source):
    """This enrichment must not silently replace any current public-law text."""
    storage = Storage(base)
    documents = {d['name']: d for d in source['laws']}
    if len(documents) != len(source['laws']) or set(documents) != {e['name'] for e in catalog['laws']}:
        raise ValueError('Tax collection scope changed')
    for entry in catalog['laws']:
        current = storage.read(entry['file'])
        law = documents[entry['name']]
        def projection(article, effective):
            return (article['jo'], article.get('title', ''), article.get('text', ''),
                    article.get('effective', effective), bool(article.get('deleted')))
        if law['effective'] != entry['effective'] or [
            projection(a, law['effective']) for a in law['articles']
        ] != [projection(a, entry['effective']) for a in current['articles']]:
            raise ValueError('Current public edition changed: ' + entry['name'])


def build(base, tax_bundle, annexes, history, destination):
    base, destination = base.resolve(), destination.resolve()
    stage = destination.with_name(destination.name + '-unpacked')
    if destination.exists() or stage.exists():
        raise ValueError('Choose a new destination; previous sites are preserved')
    manifest_raw = (base / 'manifest.json').read_bytes()
    manifest_hash = hashlib.sha256(manifest_raw).hexdigest()
    manifest = json.loads(manifest_raw)
    manifest.pop('data_packs', None)
    original = deepcopy(manifest)
    domain = next(d for d in manifest['domains'] if d['id'] == 'tax')
    catalog = Storage(base).read(domain['catalog'])
    bundle_raw = tax_bundle.read_bytes()
    bundle = json.loads(bundle_raw)
    source = bundle['source']
    check_current_texts(base, catalog, source)
    print('Verified current tax texts and scope against public snapshot', flush=True)

    from core.tax_annex import attach
    enriched = attach(source, folder=annexes)
    graph = build_tax_universe(enriched, annex_bodies=True)
    graph['coverage_note'] += (' 법인세법 시행규칙 별표 5·6과 조세특례제한법 시행령 별표 6은'
                              ' 본문과 명시적 인용을 분석했습니다. 표 내부 참조·계산·적용 여부는 미판정입니다.')
    # Body analysis adds its own layer; all existing source-article/title edges
    # and the current legal texts must remain untouched.
    if [e for e in graph['edges'] if e.get('source_layer') != 'annex-body'] != bundle['edges']:
        raise ValueError('Existing tax edges changed')
    check_current_texts(base, catalog, enriched)

    stage.mkdir(parents=True)
    shell(stage)
    writer = Writer(stage)
    entries, ids = export_documents(writer, 'tax', '', enriched['laws'], graph)
    catalog.update(laws=entries, built_at=graph['built_at'], coverage=graph['coverage_note'],
                   sectors={'all': '전체 연결'}, overview=writer.data(overview(graph, 'tax', ids, entries)))
    coverage = graph['annex_analysis']['coverage']
    selected = [item for item in coverage if item['status'] == 'explicit-citations']
    if len(selected) != 3:
        raise ValueError('Expected exactly three analyzed tax annexes')
    catalog['annex_summary'] = selected
    historical_ids = {entry['id'] for entry in entries if entry['name'] in ('법인세법', '소득세법', '조세특례제한법')}
    attach_catalog(writer, 'tax', catalog, base, skip_ids=historical_ids)
    historical = attach_official_history(writer, catalog, history, manifest_hash)
    domain.update(catalog=writer.data(catalog), built_at=catalog['built_at'])
    refresh_display_names(writer, base, manifest)
    manifest.pop('version', None)
    manifest['version'] = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()[:20]
    (stage / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    for old, new in zip(original['domains'], manifest['domains']):
        if old['id'] not in ('tax', *LABEL_DOMAINS) and old != new:
            raise ValueError('Unrelated domain changed')
    if original.get('cross_domain') != manifest.get('cross_domain'):
        raise ValueError('Cross-domain evidence changed')
    print('Exported tax evidence and three display names; other law data and cross-domain references preserved', flush=True)
    materialize_reachable(base, stage, manifest)
    convert(stage, destination, validate_site=False)
    print('Packed public data; validating all domains', flush=True)
    verification = validate(destination)
    if tax_bundle.read_bytes() != bundle_raw or (base / 'manifest.json').read_bytes() != manifest_raw:
        raise ValueError('Immutable source changed during build')
    report = dict(verification=verification, base_manifest_sha256=manifest_hash,
                  tax_source_sha256=hashlib.sha256(bundle_raw).hexdigest(),
                  preserved_article_edges=len(bundle['edges']), external_references=len(graph['external_references']),
                  citation_issues=len(graph.get('citation_issues', [])), annexes=selected,
                  annex_body_edges=sum(e.get('source_layer') == 'annex-body' for e in graph['edges']),
                  histories=historical, current_documents=len(entries),
                  current_articles=sum(len(d['articles']) for d in source['laws']),
                  untouched_domains=[d['id'] for d in original['domains'] if d['id'] not in ('tax', *LABEL_DOMAINS)],
                  display_only_domains=list(LABEL_DOMAINS),
                  source_unchanged=True)
    destination.with_name(destination.name + '-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('base-site', 'tax-bundle', 'annexes', 'history', 'destination'):
        p.add_argument('--' + name, type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(build(args.base_site, args.tax_bundle, args.annexes, args.history, args.destination), ensure_ascii=False, indent=2))
