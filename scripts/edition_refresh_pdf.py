"""Bind freshly extracted procurement PDFs to a reviewed edition replacement.

The API body and its checksum remain untouched. PDF evidence has independent
byte/text provenance and may only supplement its exact official edition.
"""
from collections import defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

from core.citation_scope import parse_target
from core.ftc_text_citations import reading_row
from core.procurement_pdf import analyze_pdf, validate_extraction
from scripts.build_static_galaxies import tidy


def load_pdf(row):
    spec = row.get('pdf_extraction')
    if not spec:
        return None
    fresh = row['fresh_document']
    if (row['change_kind'] != 'edition' or row['finding']['domains'] != ['procurement']
            or fresh.get('provider') != 'admrul' or fresh.get('articles')):
        raise ValueError('PDF refresh outside approved procurement scope')
    raw = Path(spec['path']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != spec['sha256']:
        raise ValueError('PDF extraction checksum mismatch')
    result = json.loads(raw)
    validate_extraction(result)
    record = result['record']
    for key in ('name', 'document_id', 'effective', 'source_url'):
        if record.get(key) != fresh.get(key):
            raise ValueError('PDF and fresh document identity mismatch: ' + key)
    if record.get('version_id') != fresh.get('version_id'):
        raise ValueError('PDF and fresh document edition mismatch')
    url = result['pdf_url']
    # Only a link present in the newly verified API response can be analyzed.
    def links(value):
        if isinstance(value, str):
            yield value.replace('http:', 'https:')
        elif isinstance(value, list):
            for item in value:
                yield from links(item)
        elif isinstance(value, dict):
            for item in value.values():
                yield from links(item)
    if urlparse(url).hostname not in ('law.go.kr', 'www.law.go.kr') or url not in set(links(fresh)):
        raise ValueError('PDF URL absent from verified official attachment metadata')
    pdf_raw = Path(spec['pdf_path']).read_bytes()
    if not pdf_raw.startswith(b'%PDF-') or hashlib.sha256(pdf_raw).hexdigest() != result['file_sha256']:
        raise ValueError('Official PDF checksum mismatch')
    return result


def refresh_pdf_evidence(replacements, corpus, ids):
    """Return the same evidence contract as paragraph refresh, plus PDF metadata."""
    documents, forward, reverse, edges, issues = {}, {}, defaultdict(list), [], []
    known = {d['name'] for d in corpus}
    for replacement in replacements:
        result = load_pdf(replacement)
        if result is None:
            continue
        name = result['record']['name']
        rows, problems = analyze_pdf(result, corpus)
        if not rows:
            raise ValueError('Refreshed PDF contains no verified citations')
        internal = []
        if result.get('schema') == 2:
            from core.procurement_pdf_structure import internal_links
            internal, internal_issues = internal_links(result)
            problems += internal_issues
        # Old page-number review notes are not transferable across editions.
        summary = dict(status='explicit-pdf-structured' if result.get('schema') == 2 else 'explicit-pdf-prose',
            references=len(rows), issues=len(problems), pages=len(result['pages']),
            prose_pages=len({u['page'] for u in result['units'] if u.get('layer', 'prose') == 'prose'}),
            analyzed_pages=sum(p['analyzed_units'] > 0 for p in result['pages']),
            table_regions=sum(p['tables'] for p in result['pages']),
            table_citations=sum(r['source_layer'] == 'procurement-pdf-table-cell' for r in rows),
            annex_citations=sum(r['source_layer'] == 'procurement-pdf-annex-prose' for r in rows),
            internal_links=len(internal), internal_paragraph_references='explicit-unique-headings' if internal else 'not-analyzed')
        forward[name] = [tidy(reading_row(r, 'forward'), ids, False) for r in rows]
        for edge in rows:
            if edge['target_status'] == 'collected' and edge['target_kind'] == 'article':
                reverse[(edge['target_law'], parse_target(edge['target_ref']).jo)].append(
                    tidy(reading_row(edge, 'reverse'), ids, False))
        provenance = {k: deepcopy(result[k]) for k in
                      ('file_sha256', 'text_sha256', 'pdf_url', 'pages', 'limitation', 'extraction')}
        for key in ('anchors', 'cells'):
            if key in result:
                provenance[key] = deepcopy(result[key])
        provenance['internal_connections'] = internal
        for page in provenance['pages']:
            unit = next((u for u in result['units'] if u['page'] == page['page']), None)
            page['label'] = unit['locator'] if unit else ''
        documents[name] = dict(text_analysis=summary, analysis_error='', text_connections=forward[name],
            text_issues=problems, unstructured_text=result['text'], pdf_analysis=provenance,
            pdf_url=result['pdf_url'], source_notes=[result['limitation']])
        edges.extend(rows)
        issues.extend(problems)
    return dict(documents=documents, forward=forward, reverse=dict(reverse),
                overview_edges=[dict(e, type='direct') for e in edges if e['target_law'] in known],
                text_citations=edges, text_issues=issues)
