"""Add verified MOIS PDF evidence to an immutable public snapshot; repack small files."""
import argparse
from collections import defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil

from core.procurement_pdf import analyze_pdf, validate_extraction, LIMITATION
from core.ftc_text_citations import reading_row
from core.citation_scope import parse_target
from scripts.build_forex_finance_site import snapshot, unpack
from scripts.build_static_galaxies import Writer, tidy, shell
from scripts.compact_static_galaxies import convert
from scripts.validate_static_galaxies import validate
from scripts.static_storage import Storage


def materialize_reachable(base, destination, value):
    """Materialize only reachable, hash-verified members for the temporary repack."""
    import gzip
    storage=Storage(base);seen=set()
    def walk(item):
        if isinstance(item,dict):
            if {'url','bytes','sha256'}<=item.keys():
                if item['url'] in seen:return
                seen.add(item['url']);path=destination/item['url']
                raw=path.read_bytes() if path.exists() else storage.raw(item)
                if len(raw)!=item['bytes'] or hashlib.sha256(raw).hexdigest()!=item['sha256']:raise ValueError('Repack asset mismatch')
                if not path.exists():path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
                walk(json.loads(gzip.decompress(raw)))
            else:
                for key,child in item.items():
                    if key!='data_packs':walk(child)
        elif isinstance(item,list):
            for child in item:walk(child)
    walk(value)


def build(base, extracted, destination):
    base, destination = base.resolve(), destination.resolve()
    stage = destination.with_name(destination.name+'-unpacked')
    if destination.exists() or stage.exists():
        raise ValueError('Use a new destination; existing previews are preserved')
    before = validate(base)
    stage.mkdir(parents=True)
    shell(stage)
    manifest = json.loads((base/'manifest.json').read_text(encoding='utf-8'))
    manifest.pop('data_packs',None)
    original = deepcopy(manifest)
    domain = next(d for d in manifest['domains'] if d['id'] == 'procurement')
    snap = snapshot(base, domain); catalog = unpack(base, domain['catalog'])
    corpus = [dict(name=e['name'], short_name=e['label'], articles=snap['documents'][e['id']]['articles'],
        provider='eflaw' if e['articles'] else 'admrul', uid=e['id'], effective=e['effective'],
        source_url=e['url'], category='procurement') for e in snap['entries']]
    ids = {e['name']: e['id'] for e in snap['entries']}
    analyses, forward, reverse, results = {}, defaultdict(list), defaultdict(list), []
    all_rows, all_issues = [], []
    for path in sorted(extracted.glob('*-extraction.json')):
        result = json.loads(path.read_text(encoding='utf-8')); validate_extraction(result)
        record = result['record']; entry = next(e for e in catalog['laws'] if e['name'] == record['name'])
        if entry['effective'] != record['effective'] or entry['url'] != record['source_url']:
            raise ValueError('PDF and public document editions differ')
        if entry.get('pdf_analysis') or entry.get('text_analysis'):
            raise ValueError('PDF already analyzed; do not duplicate evidence')
        pdf_path = path.with_name(record['document_id']+'.pdf')
        if hashlib.sha256(pdf_path.read_bytes()).hexdigest() != result['file_sha256']:
            raise ValueError('Official PDF checksum mismatch')
        rows, issues = analyze_pdf(result, corpus)
        if not rows:
            raise ValueError('No PDF citations; inspect extraction or parser')
        all_rows.extend(rows); all_issues.extend(issues)
        for edge in rows:
            f = tidy(reading_row(edge, 'forward'), ids, False)
            forward[entry['name']].append(f)
            if edge['target_status'] == 'collected' and edge['target_kind'] == 'article':
                reverse[(edge['target_law'], parse_target(edge['target_ref']).jo)].append(tidy(reading_row(edge,'reverse'),ids,False))
        summary = dict(status='explicit-pdf-prose', references=len(rows), issues=len(issues),
            pages=len(result['pages']), prose_pages=sum(p['analyzed_units']>0 for p in result['pages']),
            table_regions=sum(p['tables'] for p in result['pages']), internal_paragraph_references='not-analyzed')
        analyses[entry['name']] = dict(result=result, summary=summary, issues=issues)
        results.append(dict(name=entry['name'], **summary))
    if len(results) != 2:
        raise ValueError('Expected the two approved local-procurement PDFs')
    writer = Writer(stage); changed=[]
    for entry in catalog['laws']:
        packed = deepcopy(snap['documents'][entry['id']]); modified=False
        if entry['name'] in analyses:
            analysis = analyses[entry['name']]; result=analysis['result']
            summary = analysis['summary']
            entry.update(text_analysis=summary, pdf_url=result['pdf_url'], status='pdf-prose-citations',
                         source_notes=[LIMITATION])
            packed['meta'].update({k:v for k,v in entry.items() if k!='file'})
            packed['unstructured_text']=result['text']
            packed['text_connections']=forward[entry['name']]; packed['text_issues']=analysis['issues']
            # Compact provenance per page; all offsets remain in the collected text.
            packed['pdf_analysis']={k:result[k] for k in ('file_sha256','text_sha256','pdf_url','pages','limitation','extraction')}
            for page in packed['pdf_analysis']['pages']:
                unit=next((u for u in result['units'] if u['page']==page['page']),None)
                page['label']=unit['locator'] if unit else ''
            modified=True
        for jo, detail in packed['details'].items():
            if reverse[(entry['name'],jo)]:
                detail['rows'].extend(reverse[(entry['name'],jo)]);modified=True
        replacements={}
        for old in entry['parts']:
            group=unpack(base,old); edited=False
            for jo, detail in group.items():
                if reverse[(entry['name'],jo)]:
                    detail['rows'].extend(reverse[(entry['name'],jo)]);edited=True
            if edited:
                replacements[old['url']]=writer.data(group);modified=True
        if modified:
            entry['parts']=[replacements.get(p['url'],p) for p in entry['parts']]
            packed['meta']['parts']=entry['parts']
            for article in packed['articles']:
                if article.get('detail'): article['detail']=replacements.get(article['detail']['url'],article['detail'])
            entry['file']=writer.data(packed);changed.append(entry['name'])
    previous=catalog.get('text_summary',dict(documents=0,citations=0,issues=0))
    catalog['text_summary']=dict(documents=previous['documents']+2,citations=previous['citations']+len(all_rows),issues=previous['issues']+len(all_issues))
    catalog['pdf_summary']=results;catalog['coverage']+=' '+LIMITATION
    domain['catalog']=writer.data(catalog)
    manifest.pop('version',None)
    manifest['version']=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()[:20]
    (stage/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    # Unrelated catalogs and cross-domain evidence remain byte-identical.
    for old,new in zip(original['domains'],manifest['domains']):
        if old['id']!='procurement' and old!=new:raise ValueError('Unrelated domain changed')
    if original.get('cross_domain')!=manifest.get('cross_domain'):raise ValueError('Cross-domain evidence changed')
    materialize_reachable(base,stage,manifest)
    # The temporary unpacked tree is deliberately larger than the public file
    # budget. Every member is verified while packing; validate the final site.
    convert(stage,destination,validate_site=False)
    verification=validate(destination)
    report=dict(before=before,verification=verification,documents=results,changed_documents=changed,
        evidence=all_rows,issues=all_issues,untouched_domains=[d['id'] for d in original['domains'] if d['id']!='procurement'],
        source_unchanged=validate(base)==before)
    destination.with_name(destination.name+'-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return {k:v for k,v in report.items() if k not in ('evidence','issues')}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-site',type=Path,required=True);p.add_argument('--extracted',type=Path,required=True)
    p.add_argument('--destination',type=Path,required=True);args=p.parse_args()
    print(json.dumps(build(args.base_site,args.extracted,args.destination),ensure_ascii=False,indent=2))
