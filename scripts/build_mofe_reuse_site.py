"""Reuse collected guidance text and add the procurement/public-institutions pair.

Reads the exact public editions. Never rewrites the source release or raw corpus.
Only manifest-reachable assets are copied into the new output directory.
"""
import argparse
from collections import defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil

from core.ftc_text_citations import collect_text_citations, validate_text_citations, reading_row
from core.citation_scope import parse_target
from scripts.build_forex_finance_site import snapshot, unpack, attach_bridge
from scripts.build_static_galaxies import Writer, tidy, shell
from scripts.validate_static_galaxies import validate

TARGETS = ('treasury', 'procurement')


def guidance_source(snap, domain):
    source = dict(domain=domain, laws=[], administrative_rules=[])
    for entry in snap['entries']:
        packed = snap['documents'][entry['id']]
        indexed = bool(packed['articles'])
        document = dict(uid=entry['id'], name=entry['name'], short_name=entry['label'],
            provider='eflaw' if indexed else 'admrul', category=domain,
            effective=entry['effective'], source_url=entry['url'],
            articles=deepcopy(packed['articles']), raw_body_blocks=[packed.get('unstructured_text', '')])
        if not indexed and packed['meta'].get('text_analysis'):
            raise ValueError('Guidance is already analyzed; choose the original source release')
        # Duplicate official headings cannot be repaired by treating them as paragraphs.
        if 'duplicate' in entry.get('status', ''):
            document['analysis_error'] = '공식 조문번호 중복'
        source['laws' if indexed else 'administrative_rules'].append(document)
    return source


def enhance_domain(base, writer, domain):
    snap = snapshot(base, domain)
    catalog = unpack(base, domain['catalog'])
    source = guidance_source(snap, domain['id'])
    rows, issues = collect_text_citations(source, profile=domain['id'])
    validate_text_citations(source, rows)
    docs = {d['name']: d for d in source['laws'] + source['administrative_rules']}
    ids = {e['name']: e['id'] for e in snap['entries']}
    forward, reverse = defaultdict(list), defaultdict(list)
    for edge in rows:
        forward[edge['source_law']].append(tidy(reading_row(edge, 'forward'), ids, False))
        if edge['target_status'] == 'collected' and edge['target_kind'] == 'article':
            reverse[(edge['target_law'], parse_target(edge['target_ref']).jo)].append(
                tidy(reading_row(edge, 'reverse'), ids, False))
    changed = []
    for entry in catalog['laws']:
        packed = deepcopy(snap['documents'][entry['id']])
        document = docs[entry['name']]
        modified = False
        if document.get('text_analysis'):
            entry['text_analysis'] = document['text_analysis']
            packed['meta']['text_analysis'] = document['text_analysis']
            packed['text_connections'] = forward[entry['name']]
            packed['text_issues'] = [i for i in issues if i['source_law'] == entry['name']]
            modified = True
        for jo, detail in packed.get('details', {}).items():
            additions = reverse[(entry['name'], jo)]
            if additions:
                detail['rows'].extend(additions)
                modified = True
        replacements = {}
        for old in entry['parts']:
            group = unpack(base, old)
            edited = False
            for jo, detail in group.items():
                additions = reverse[(entry['name'], jo)]
                if additions:
                    detail['rows'].extend(additions)
                    edited = True
            if edited:
                replacements[old['url']] = writer.data(group)
                modified = True
        if modified:
            entry['parts'] = [replacements.get(p['url'], p) for p in entry['parts']]
            packed['meta']['parts'] = entry['parts']
            for article in packed['articles']:
                if article.get('detail'):
                    article['detail'] = replacements.get(article['detail']['url'], article['detail'])
            entry['file'] = writer.data(packed)
            changed.append(entry['name'])
    summary = dict(documents=sum(bool(d.get('text_analysis')) for d in docs.values()),
                   citations=len(rows), issues=len(issues))
    catalog['text_summary'] = summary
    catalog['coverage'] = catalog['coverage'].replace('장·절·항목 형식, 첨부파일 본문·별표·부칙은 미분석입니다.', '문단 내부 참조, 미확보 첨부파일 본문·별표·부칙은 미분석입니다.')
    catalog['coverage'] += (' 확보된 문단형 지침·고시의 명시적 인용과 대상 조문의 역인용을 분석합니다. '
                            '내부 문단 간 참조·이미지·표 본문·부칙은 미분석입니다.')
    for entry in catalog.get('workbench', {}).get('unindexed', []):
        if docs[entry['name']].get('text_analysis'):
            entry['status'] = docs[entry['name']]['analysis_error']
    domain['catalog'] = writer.data(catalog)
    return dict(**summary, changed_documents=changed,
        missing_text=[d['name'] for d in docs.values() if not d['articles'] and not d.get('text_analysis')],
        evidence=rows, unresolved=issues)


def copy_references(base, destination, value):
    """Copy only checked, reachable assets; no cleanup/deletion in the source tree."""
    seen = set()
    def walk(item):
        if isinstance(item, dict):
            if {'url', 'bytes', 'sha256'} <= item.keys():
                if item['url'] in seen:
                    return
                seen.add(item['url'])
                present = destination / item['url']
                owner = destination if present.exists() else base
                data = unpack(owner, item)  # Checks hash, byte size and path before copy.
                if owner == base:
                    present.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(base / item['url'], present)
                walk(data)
            else:
                for v in item.values():
                    walk(v)
        elif isinstance(item, list):
            for v in item:
                walk(v)
    walk(value)


def build(base, destination):
    base, destination = base.resolve(), destination.resolve()
    if destination.exists():
        raise ValueError('Choose a new destination; existing previews are preserved')
    before = validate(base)
    manifest = json.loads((base / 'manifest.json').read_text(encoding='utf-8'))
    original = deepcopy(manifest)
    if set(manifest.get('cross_domain', {})) & {'procurement', 'public_institutions'}:
        raise ValueError('This pair is already present; choose the original source release')
    shutil.copytree(base, destination, ignore=lambda folder, names: ['data'] if Path(folder) == base else [])
    shell(destination)
    # Retain the independently maintained introduction exactly.
    shutil.copy2(base / 'introduction.html', destination / 'introduction.html')
    writer = Writer(destination)
    report = dict(before=before, guidance={})
    for domain in manifest['domains']:
        if domain['id'] in TARGETS:
            report['guidance'][domain['id']] = enhance_domain(base, writer, domain)
            print(domain['id'] + ': guidance citations verified', flush=True)
    copy_references(base, destination, manifest)
    report['bridge'] = attach_bridge(destination, manifest, writer,
                                      pair=('procurement', 'public_institutions'))
    # Domain catalogs for tax and all other unaffected areas are bit-for-bit references.
    for old, new in zip(original['domains'], manifest['domains']):
        if old['id'] not in TARGETS and old != new:
            raise ValueError('An unrelated domain changed')
    if any(manifest['cross_domain'][d] != r for d, r in original.get('cross_domain', {}).items()):
        raise ValueError('An existing cross-domain pair changed')
    manifest.pop('version', None)
    manifest['version'] = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()[:20]
    (destination / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    report['verification'] = validate(destination)
    report['unchanged_domains'] = [d['id'] for d in original['domains'] if d['id'] not in TARGETS]
    report['source_release_unchanged'] = validate(base) == before
    (destination.parent / (destination.name + '-report.json')).write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return {**report, 'guidance': {d: {k: v for k, v in r.items() if k not in ('evidence', 'unresolved')}
                                 for d, r in report['guidance'].items()}}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-site', type=Path, required=True)
    p.add_argument('--destination', type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(build(args.base_site, args.destination), ensure_ascii=False, indent=2))
