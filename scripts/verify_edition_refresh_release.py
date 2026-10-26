"""Audit a reviewed edition overlay against its immutable public inputs.

This verifier checks source text and stored citation evidence, not the legal
interpretation of a provision. Historical snapshots are checked separately
and are never mistaken for current citation rows.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from core.fsc_administrative import body_text, index_rule
from core.galaxy_focus import _target
from scripts.static_storage import Storage


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def inventory(root):
    storage = Storage(root)
    manifest = json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    entries, catalogs = {}, {}
    for domain in manifest['domains']:
        name = domain['id']
        catalog = storage.read(domain['catalog'])
        catalogs[(name, '')] = catalog
        for entry in catalog['laws']:
            key = (name, '', entry['id'])
            if key in entries:
                raise ValueError('Duplicate public document identity')
            entries[key] = entry
        for region in catalog.get('regions', []):
            if not region.get('catalog'):
                continue
            local = storage.read(region['catalog'])
            catalogs[(name, region['id'])] = local
            for entry in local['laws']:
                key = (name, region['id'], entry['id'])
                if key in entries:
                    raise ValueError('Duplicate regional document identity')
                entries[key] = entry
    return storage, manifest, entries, catalogs


def details(storage, entry, document):
    result = dict(document.get('details', {}))
    for part in entry.get('parts', []):
        value = storage.read(part)
        if set(value).intersection(result):
            raise ValueError('Duplicate article-detail shard key')
        result.update(value)
    return result


def articles(document):
    return [{k: v for k, v in a.items() if k != 'detail'} for a in document['articles']]


def body_projection(document):
    return [{k: a.get(k, '' if k != 'deleted' else False)
             for k in ('jo', 'title', 'text', 'effective', 'deleted')}
            for a in document.get('articles', [])]


def immutable_content(document):
    # Links may need new target metadata; their original attachment content,
    # extraction result, provenance, and analysis findings must not change.
    result = {k: v for k, v in document.items()
              if k not in ('meta', 'details', 'broad', 'text_connections', 'annexes', 'articles')}
    result['articles'] = articles(document)
    result['annexes'] = [{k: v for k, v in item.items() if k != 'connections'}
                         for item in document.get('annexes', [])]
    return result


def iter_rows(document, article_details):
    for section in article_details.values():
        for field in ('rows', 'external'):
            yield from section.get(field, [])
    yield from document.get('broad', [])
    yield from document.get('text_connections', [])
    for annex in document.get('annexes', []):
        yield from annex.get('connections', [])


def evidence_projection(rows):
    fields = ('evidence_id', 'source_id', 'source_jo', 'source_ref', 'source_start',
              'source_end', 'source_effective', 'source_layer', 'raw', 'cite_raw',
              'context', 'source_text_sha256', 'source_file_sha256')
    return sorted((json.dumps({k: r[k] for k in fields if k in r},
                              sort_keys=True, ensure_ascii=False) for r in rows))


def verify(base, site, sources_path, report_path, *, output=None):
    base, site = Path(base).resolve(), Path(site).resolve()
    sources_path, report_path = Path(sources_path), Path(report_path)
    plan_raw = sources_path.read_bytes()
    plan = json.loads(plan_raw)
    build_report = json.loads(report_path.read_text(encoding='utf-8'))
    base_raw, site_raw = (base/'manifest.json').read_bytes(), (site/'manifest.json').read_bytes()
    old_storage, old_manifest, old_entries, old_catalogs = inventory(base)
    new_storage, new_manifest, new_entries, new_catalogs = inventory(site)
    errors = []
    checks = Counter()

    def require(ok, message, key=None):
        if not ok:
            errors.append(dict(message=message, document=list(key) if key else None))
        return bool(ok)

    require(old_manifest['version'] == plan['base_data_version'] == build_report['base_version'],
            'Fixed base data version mismatch')
    require(build_report['base_manifest_sha256'] == sha(base_raw), 'Base manifest checksum mismatch')
    require(not plan.get('base_manifest_sha256') or plan['base_manifest_sha256'] == sha(base_raw),
            'Approved base manifest checksum mismatch')
    require(build_report['source_sha256'] == sha(plan_raw), 'Approved source checksum mismatch')
    require(build_report['data_version'] == new_manifest['version'], 'Published data version mismatch')
    require(set(old_entries) == set(new_entries), 'Document/domain/region identity scope changed')
    require(set(old_catalogs) == set(new_catalogs), 'Regional catalog scope changed')

    selected, changed_sources, fresh_by_key = {}, {}, {}
    for row in plan['rows']:
        finding, fresh = row['finding'], deepcopy(row['fresh_document'])
        require(row.get('validation', {}).get('status') == 'verified', 'Unverified source in approved plan')
        if finding['provider'] == 'admrul':
            fresh = index_rule(fresh)
        fresh_by_key[finding['key']] = fresh
        matches = [key for key, entry in old_entries.items()
                   if key[0] in finding['domains'] and entry['name'] == finding['name']
                   and entry['effective'] == finding['effective'] and entry['url'] == finding['url']]
        require(Counter(k[0] for k in matches) == Counter(finding['domains']),
                'Approved source must match exactly one occurrence per specified domain')
        for key in matches:
            require(key not in selected, 'Duplicate approved replacement', key)
            selected[key] = row
            if row['change_kind'] == 'edition':
                changed_sources[key[2]] = dict(key=key, fresh=fresh,
                    article_by_number={str(a['jo']): a for a in fresh.get('articles', [])},
                    annex_by_reference={a['ref']: a for a in fresh.get('annexes', [])})
    applied = {(r['domain'], r['region'], r['id']): r for r in build_report['applied']}
    require(len(applied) == len(build_report['applied']) and set(applied) == set(selected),
            'Actual replacement occurrences differ from approved plan')

    changed_forward = defaultdict(set)
    changed_reverse = defaultdict(set)
    renamed = {key[2]: row['fresh_document']['name'] for key, row in selected.items()
               if row['fresh_document']['name'] != old_entries[key]['name']}
    entry_by_id = {key[2]: (key, entry) for key, entry in new_entries.items()}
    article_numbers = {}
    regional_forward, national_reverse = [], set()
    bad_row_examples = Counter()

    def regional_endpoint(row):
        # Range expansion can use one canonical evidence ID for several
        # reverse articles while the forward list has an ID per endpoint.
        # Require the same quote coordinates AND actual destination instead.
        try:
            article_number = _target(row.get('target_ref', ''), allow_hyphen=True).jo
        except ValueError:
            article_number = row.get('target_ref')
        return (row.get('source_id'), str(row.get('source_jo')), row.get('source_start'),
                row.get('source_end'), row.get('cite_raw') or row.get('raw'),
                row.get('target_id'), article_number)

    def verify_row(row, location):
        for side in ('source', 'target', 'neighbor'):
            law_id = row.get(side+'_id')
            if law_id in renamed:
                require(row.get(side+'_law') == renamed[law_id],
                        'Stale renamed '+side+' metadata ['+str(location)+']')
                checks['renamed_row_metadata'] += 1
        source_id = row.get('source_id', '')
        change = changed_sources.get(source_id)
        if not change:
            return
        checks['changed_source_row_occurrences'] += 1
        source = change['fresh']
        article = change['article_by_number'].get(str(row.get('source_jo', '')))
        annex_title = None
        if article is None and row.get('source_granularity') == 'annex' and row.get('source_layer') != 'annex-body':
            annex_title = change['annex_by_reference'].get(row.get('source_jo'))
            if annex_title:
                article = dict(text=annex_title['title'], effective=annex_title['effective'])
                checks['changed_annex_title_row_occurrences'] += 1
        label = row.get('evidence_id') or row.get('raw') or row.get('cite_raw') or ''
        key = change['key']
        def row_require(ok, message):
            if not ok:
                bad_row_examples[message] += 1
                if bad_row_examples[message] <= 12:
                    require(False, message+' ['+str(location)+'] evidence='+str(label), key)
            return bool(ok)
        row_require(row.get('source_law') == source['name'], 'Stale changed-source law name')
        row_require(article is not None, 'Changed-source citation references missing article or stale annex analysis')
        if article is None:
            return
        text = article['text']
        row_require(row.get('source_effective') == (article.get('effective') or source['effective']),
                    'Stale changed-source effective date')
        raw = row.get('cite_raw') or row.get('raw', '')
        start, end = row.get('source_start'), row.get('source_end')
        valid_bounds = (isinstance(start, int) and isinstance(end, int)
                        and 0 <= start < end <= len(text))
        row_require(valid_bounds, 'Changed-source evidence bounds invalid')
        if valid_bounds:
            row_require(text[start:end] == raw, 'Changed-source citation does not match fresh body slice')
        if row.get('context'):
            row_require(row['context'] in text, 'Changed-source context absent from fresh body')
        # Annex metadata titles have their own title -> article reverse rows;
        # their content was not analyzed and does not have a forward reader.
        if annex_title:
            return
        if row.get('direction') == 'forward':
            changed_forward[source_id].add(row.get('evidence_id'))
            target_key = entry_by_id.get(row.get('target_id', ''), (None, None))[0]
            if (key[0] == 'local_tax' and key[1] and target_key
                    and target_key[0] == 'local_tax' and not target_key[1]
                    and row.get('target_kind') == 'article'):
                regional_forward.append(row)
        elif row.get('direction') == 'reverse':
            changed_reverse[source_id].add(row.get('evidence_id'))
            if row.get('national') and row.get('region') == key[1]:
                national_reverse.add(regional_endpoint(row))

    for key in sorted(set(old_entries).intersection(new_entries)):
        old_entry, new_entry = old_entries[key], new_entries[key]
        old_doc, new_doc = old_storage.read(old_entry['file']), new_storage.read(new_entry['file'])
        article_numbers[key[2]] = {str(a['jo']) for a in new_doc['articles']}
        checks['documents'] += 1
        row = selected.get(key)
        require(new_doc['meta']['id'] == new_entry['id'] and new_doc['meta']['name'] == new_entry['name'],
                'Reader metadata differs from catalog', key)
        if row:
            fresh = fresh_by_key[row['finding']['key']]
            require(new_entry['name'] == fresh['name'], 'Approved canonical name not published', key)
            if row['change_kind'] == 'edition':
                require(new_entry['effective'] == fresh['effective'], 'Approved edition date not published', key)
                require(new_entry['url'] == fresh['source_url'], 'Approved official edition URL not published', key)
                expected = dict(articles=[{**a, 'effective': a.get('effective') or fresh['effective']}
                                          for a in fresh.get('articles', [])])
                require(body_projection(new_doc) == body_projection(expected), 'Published body differs from fresh source', key)
                if not new_doc['articles']:
                    require(new_doc.get('unstructured_text', '') == body_text(fresh.get('raw_body_blocks', [])),
                            'Published unstructured text differs from fresh source', key)
                annex_fields = ('ref', 'title', 'effective', 'urls')
                require([{k: a.get(k) for k in annex_fields} for a in new_doc.get('annexes', [])]
                        == [{k: a.get(k) for k in annex_fields} for a in fresh.get('annexes', [])],
                        'Published annex links or metadata differ from fresh source', key)
                checks['updated_annex_metadata'] += len(new_doc.get('annexes', []))
                for annex in new_doc.get('annexes', []):
                    require(not annex.get('analysis') and annex.get('status') == 'not-analyzed',
                            'Old annex analysis incorrectly carried into new edition', key)
                checks['edition_occurrences'] += 1
            else:
                require(new_entry['effective'] == old_entry['effective'] and new_entry['url'] == old_entry['url'],
                        'Title-only update changed edition identity', key)
                require(immutable_content(new_doc) == immutable_content(old_doc),
                        'Title-only update changed body or attachment content', key)
                checks['title_occurrences'] += 1
        else:
            require(new_entry['name'] == old_entry['name'] and new_entry['effective'] == old_entry['effective']
                    and new_entry['url'] == old_entry['url'], 'Unapproved edition/name/URL change', key)
            require(immutable_content(new_doc) == immutable_content(old_doc),
                    'Unchanged document body/annex/PDF/extra content changed', key)
            checks['unchanged_documents'] += 1
        if not row or row['change_kind'] != 'edition':
            checks['preserved_annexes'] += len(old_doc.get('annexes', []))
            checks['preserved_annex_analyses'] += sum(bool(a.get('analysis')) for a in old_doc.get('annexes', []))
            checks['preserved_pdf_analyses'] += bool(old_doc.get('pdf_analysis'))
            old_attachment_rows = [r for a in old_doc.get('annexes', []) for r in a.get('connections', [])]
            new_attachment_rows = [r for a in new_doc.get('annexes', []) for r in a.get('connections', [])]
            require(evidence_projection(old_attachment_rows) == evidence_projection(new_attachment_rows),
                    'Unchanged annex source evidence changed', key)
        new_details = details(new_storage, new_entry, new_doc)
        if row and row['change_kind'] == 'edition':
            old_details = details(old_storage, old_entry, old_doc)
            for jo in set(old_details).intersection(new_details):
                expected = [r for r in old_details[jo].get('rows', [])
                            if r.get('direction') == 'reverse' and r.get('source_id') not in changed_sources]
                actual = [r for r in new_details[jo].get('rows', []) if r.get('direction') == 'reverse']
                actual_evidence = Counter(evidence_projection(actual))
                expected_evidence = Counter(evidence_projection(expected))
                missing = expected_evidence-actual_evidence
                require(not missing, 'Unchanged-source incoming evidence lost on retained article '+jo
                        +' ('+str(sum(missing.values()))+' rows)', key)
                checks['expected_incoming_evidence'] += len(expected)
                checks['retained_incoming_evidence'] += len(expected)-sum(missing.values())
                checks['missing_incoming_evidence'] += sum(missing.values())
        for stored_row in iter_rows(new_doc, new_details):
            verify_row(stored_row, '/'.join(key))
        if checks['documents'] % 1000 == 0:
            print('Audited documents:', checks['documents'], flush=True)

    # Version-bound bridges contain a second reader payload. Inspect current
    # bridge rows as well; historical baseline JSON is intentionally excluded.
    seen_bridge_refs = set()
    def bridge_rows(ref):
        if ref['url'] in seen_bridge_refs:
            return
        seen_bridge_refs.add(ref['url'])
        value = new_storage.read(ref)
        for child in value.get('bridges', []):
            bridge_rows(child)
        for source, sections in value.get('laws', {}).items():
            for jo, section in sections.items():
                for row in section.get('rows', []):
                    verify_row(row, 'bridge/'+source+'/'+jo)
    for ref in new_manifest.get('cross_domain', {}).values():
        bridge_rows(ref)
    for source_id, evidence_ids in changed_reverse.items():
        require(not (evidence_ids - changed_forward[source_id]),
                'Reverse citation from changed source has no current forward evidence', changed_sources[source_id]['key'])
    for row in regional_forward:
        if row.get('neighbor_jo') in article_numbers.get(row.get('target_id'), set()):
            require(regional_endpoint(row) in national_reverse,
                    'Regional citation missing from central national reverse index', changed_sources[row['source_id']]['key'])
            checks['regional_national_counterparts'] += 1

    for catalog_key, old_catalog in old_catalogs.items():
        prior = old_catalog.get('delegation_review', {}).get('baselines', {})
        current = new_catalogs[catalog_key].get('delegation_review', {}).get('baselines', {})
        for doc_id, old in prior.items():
            key = (*catalog_key, doc_id)
            if key in selected and selected[key]['change_kind'] == 'edition':
                checks['changed_document_baselines'] += 1
                continue
            if require(doc_id in current, 'Unchanged historical comparison removed', key):
                require(old_storage.raw(old['file']) == new_storage.raw(current[doc_id]['file']),
                        'Unchanged historical comparison bytes changed', key)
                checks['preserved_historical_baselines'] += 1
    require((base/'manifest.json').read_bytes() == base_raw and sources_path.read_bytes() == plan_raw,
            'Immutable input changed during verification')
    result = dict(ok=not errors, base_version=old_manifest['version'], data_version=new_manifest['version'],
        base_manifest_sha256=sha(base_raw), sources_sha256=sha(plan_raw), approved_sources=len(plan['rows']),
        approved_occurrences=len(selected), checks=dict(checks), row_errors=dict(bad_row_examples), errors=errors,
        scope='Public document identities, edition bodies, unchanged attachments and histories, current changed-source evidence')
    if output:
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ('base-site', 'site', 'sources'):
        parser.add_argument('--'+argument, type=Path, required=True)
    parser.add_argument('--build-report', type=Path,
                        help='Original build report; defaults to <site>-report.json')
    parser.add_argument('--report', '--output', dest='output', type=Path, required=True,
                        help='Write the independent release verification result here')
    args = parser.parse_args()
    build_report = args.build_report or args.site.with_name(args.site.name+'-report.json')
    result = verify(args.base_site, args.site, args.sources, build_report, output=args.output)
    print(json.dumps({k: v for k, v in result.items() if k != 'errors'}, ensure_ascii=False, indent=2))
    for error in result['errors'][:20]:
        print(json.dumps(error, ensure_ascii=False))
    raise SystemExit(0 if result['ok'] else 1)
