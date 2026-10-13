"""Apply source-bound ownership corrections without replacing any legal text.

The plan is tied to the previous release, whole article hashes, and exact old
evidence. Forward/reverse rows and overview counts change together. Other rows,
annexes, historical editions, selected notes and collection dates are preserved.
"""
import argparse
from collections import defaultdict
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from core.citation_scope import Provision
from core.law_map import family
from core.universe_builder import QUALIFIER, public_url
from scripts.build_static_galaxies import ROOT, Writer, EdgeIndex, tidy, shell
from scripts.build_procurement_pdf_site import materialize_reachable
from scripts.compact_static_galaxies import convert
from scripts.static_storage import Storage
from scripts.validate_static_galaxies import validate


def edge_id(law, jo, citation):
    ident = (law, jo, citation['start'], citation['end'], citation['target_name'], citation['target_ref'], 'article')
    return sha256(repr(ident).encode('utf-8')).hexdigest()[:20]


def corrected_edge(old, citation, entries):
    target = entries.get(citation['target_name'])
    edge = {k: deepcopy(v) for k, v in old.items()
            if k.startswith('source_') and k not in ('source_id', 'source_scope')}
    edge.update(context=old['context'], cite_raw=citation['raw'], target_law=citation['target_name'],
        target_ref=citation['target_ref'], target_kind='article', type=citation['relation'],
        target_effective=target['effective'] if target else '',
        target_url=target['url'] if target else public_url(citation['target_name'], citation['target_ref']),
        context_review=bool(citation.get('context_review') or QUALIFIER.search(old['context'])),
        target_provision_status=citation['target_provision_status'], via_range=citation.get('via_range', False))
    edge['evidence_id'] = edge_id(edge['source_law'], str(edge['source_jo']), citation)
    if not target:
        edge.update(target_status='not-collected', target_analysis='not-indexed', external_reverse='not-collected')
    for key in ('target_reference_note', 'target_movement_candidates'):
        if key in citation: edge[key] = deepcopy(citation[key])
    return edge


def adjust_overview(value, removed, added):
    value = deepcopy(value)
    nodes = {n['id']: n for n in value['nodes']}
    pairs = {(r['a'], r['b']): r['n'] for r in value['all_links']}
    for sign, edges in ((-1, removed), (1, added)):
        for edge in edges:
            a, b = edge['source_law'], edge['target_law']
            if a not in nodes or b not in nodes: continue
            nodes[a]['count'] += sign
            if nodes[a]['count'] < 0: raise ValueError('Negative overview count')
            if a != b:
                pairs[(a, b)] = pairs.get((a, b), 0) + sign
                if pairs[(a, b)] < 0: raise ValueError('Negative overview link count')
    value['all_links'] = [dict(a=a, b=b, n=n) for (a, b), n in sorted(pairs.items()) if n]
    value['links'] = [r for r in sorted(value['all_links'], key=lambda r: -r['n'])
                      if r['n'] >= 8 and family(r['a']) != family(r['b'])]
    # Dust is a sampled layout, not an article-count ledger. Keep its positions.
    return value


def build(base, destination, plan_file):
    base, destination = Path(base).resolve(), Path(destination).resolve()
    stage = destination.with_name(destination.name + '-unpacked')
    if any(p.exists() for p in (destination, stage)):
        raise ValueError('Choose a new output; existing snapshots are preserved')
    if not all(p.is_relative_to(ROOT/'output') for p in (base, destination, stage)):
        raise ValueError('Use independent project output folders')
    original_raw = (base/'manifest.json').read_bytes()
    original = json.loads(original_raw)
    plan = json.loads(Path(plan_file).read_text(encoding='utf-8'))
    if plan['base_version'] != original['version']:
        raise ValueError('Correction plan belongs to a different release')
    storage = Storage(base, original)
    stage.mkdir(parents=True); shell(stage); writer = Writer(stage)
    replacements, retired_ids, added_ids, summary = {}, set(), set(), {}
    updated_entries, entry_sources = {}, {}
    changes = defaultdict(list)
    for item in plan['changes']: changes[item['domain']].append(item)
    for domain in original['domains']:
        name = domain['id']
        if name not in changes: continue
        catalog = storage.read(domain['catalog'])
        entries = {e['name']: e for e in catalog['laws']}
        docs, details = {}, {}
        for e in catalog['laws']:
            doc = storage.read(e['file']); docs[e['name']] = doc
            detail = deepcopy(doc.get('details', {}))
            for part in e['parts']: detail.update(storage.read(part))
            details[e['name']] = detail
        removed, added = {}, {}
        for item in changes[name]:
            law, jo, prior = item['law'], item['jo'], item['before']
            article = next(a for a in docs[law]['articles'] if a['jo'] == jo)
            if (entries[law]['effective'] != item['effective']
                    or sha256(article['text'].encode()).hexdigest() != item['source_sha256']
                    or article['text'][prior['start']:prior['end']] != prior['raw']):
                raise ValueError('Correction source changed')
            old_id = edge_id(law, jo, prior)
            old_rows = details[law][jo]['rows'] + details[law][jo].get('external', [])
            old = next((r for r in old_rows if r['evidence_id'] == old_id), None)
            if not old: raise ValueError('Old citation evidence absent')
            removed[old_id] = old
            for citation in item['after']:
                if citation['start'] != prior['start'] or citation['end'] != prior['end']:
                    raise ValueError('Ownership correction cannot move a source span')
                edge = corrected_edge(old, citation, entries)
                added[edge['evidence_id']] = edge
        # The same multi-target span may be represented by several plan rows.
        original_ids = {r['evidence_id'] for dt in details.values() for v in dt.values()
                        for r in v.get('rows', []) + v.get('external', [])}
        added = {k: v for k, v in added.items() if k not in original_ids or k in removed}
        shared = set(removed) & set(added)
        for key in shared: removed.pop(key); added.pop(key)
        retired_ids.update(removed); added_ids.update(added)
        graph = dict(domain=name, laws=list(entries), focus_laws=list(entries), built_at=catalog['built_at'],
                     edges=[r for r in added.values() if r['target_law'] in entries])
        source_docs = [dict(name=n, articles=d['articles']) for n, d in docs.items()]
        index = EdgeIndex(graph, source_docs)
        ids = {n: e['id'] for n, e in entries.items()}
        ext = defaultdict(list)
        for r in added.values():
            if r['target_law'] not in entries: ext[(r['source_law'], r['source_jo'])].append(tidy(r, ids, index.hyphen))
        changed_docs = 0
        for law, e in entries.items():
            doc = docs[law]; updated = deepcopy(doc); updated_details = details[law]
            any_change = False
            for article in doc['articles']:
                jo = article['jo']; old_detail = updated_details[jo]; detail = deepcopy(old_detail)
                for key in ('rows', 'external'):
                    detail[key] = [r for r in detail.get(key, []) if r['evidence_id'] not in removed]
                fresh = index.focus(law, Provision(jo).label)
                detail['rows'] += [tidy(r, ids, index.hyphen) for r in fresh['rows']]
                detail['external'] += ext[(law, jo)]
                detail['same_article_count'] += fresh['same_article_count']
                detail['unplaced'] += fresh['unplaced']
                if detail != old_detail: any_change = True; updated_details[jo] = detail
            if not any_change: continue
            changed_docs += 1
            if e['parts']:
                for part in e['parts']:
                    old_chunk = storage.read(part)
                    new_chunk = {jo: updated_details[jo] for jo in old_chunk}
                    if old_chunk != new_chunk:
                        replacements[part['url']] = writer.data(new_chunk)
                updated['meta']['parts'] = [replacements.get(p['url'], p) for p in e['parts']]
                for a in updated['articles']:
                    if a.get('detail'): a['detail'] = replacements.get(a['detail']['url'], a['detail'])
            else:
                updated['details'] = updated_details
            replacements[e['file']['url']] = writer.data(updated)
            updated_entries[e['id']] = dict(e, file=replacements[e['file']['url']], parts=updated['meta']['parts'])
            entry_sources[e['id']] = doc
        replacements[catalog['overview']['url']] = writer.data(adjust_overview(storage.read(catalog['overview']), removed.values(), added.values()))
        summary[name] = dict(corrected_old_evidence=len(removed), replacement_evidence=len(added), documents=changed_docs)
        print(name, summary[name], flush=True)

    # Update references wherever the same entries occur, including bridge
    # metadata. A stale bridge citation itself must be reviewed, never hidden.
    memo = {}
    def rewrite(value, location='manifest'):
        if isinstance(value, list): return [rewrite(v, location+'[]') for v in value]
        if not isinstance(value, dict): return value
        if value.get('id') in updated_entries and 'file' in value and 'parts' in value:
            current = updated_entries[value['id']]
            old_doc = storage.read(value['file'])
            main_doc = entry_sources[value['id']]
            plain_articles = lambda d: [{k: v for k, v in a.items() if k != 'detail'} for a in d['articles']]
            if value['effective'] != current['effective'] or plain_articles(old_doc) != plain_articles(main_doc):
                raise ValueError('Bridge metadata refers to a different source edition')
            for key in set(old_doc) - {'meta', 'articles', 'details'}:
                if old_doc[key] != main_doc[key]:
                    raise ValueError('Bridge document has different non-citation content')
            return {**value, 'file': current['file'], 'parts': current['parts']}
        if {'url', 'bytes', 'sha256'} <= value.keys():
            url = value['url']
            if url in replacements: return replacements[url]
            if url in memo: return memo[url]
            obj = storage.read(value); updated = rewrite(obj, location+'@'+url)
            memo[url] = writer.data(updated) if updated != obj else value
            return memo[url]
        if value.get('evidence_id') in retired_ids:
            raise ValueError('Retired citation retained at '+location+': ' + repr({k: value.get(k) for k in
                ('evidence_id', 'source_law', 'source_jo', 'source_id', 'source_effective', 'target_law', 'target_ref', 'direction')}))
        return {k: rewrite(v, location+'.'+k) for k, v in value.items() if k != 'data_packs'}
    manifest = rewrite(original)
    manifest.pop('version', None)
    manifest['version'] = sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()[:20]
    (stage/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    reachable = materialize_reachable(base, stage, manifest)
    for url in set(writer.assets) - reachable:
        path = (stage/url).resolve()
        if path.parent != stage/'data': raise ValueError('Unsafe provisional asset')
        path.unlink()
    convert(stage, destination, validate_site=False)
    verified = validate(destination)
    after = Storage(destination)
    # Text, editions, annexes and all entry metadata except derived file refs
    # must remain exactly equal, across corrected and untouched domains.
    count = 0
    for old_domain, new_domain in zip(original['domains'], manifest['domains']):
        old_cat, new_cat = storage.read(old_domain['catalog']), after.read(new_domain['catalog'])
        for old, new in zip(old_cat['laws'], new_cat['laws']):
            before, now = storage.read(old['file']), after.read(new['file'])
            strip = lambda d: {k: v for k, v in d.items() if k not in ('file', 'parts', 'detail')}
            if strip(old) != strip(new): raise ValueError('Published entry changed')
            if [strip(a) for a in before['articles']] != [strip(a) for a in now['articles']]:
                raise ValueError('Published article text changed')
            for key in set(before) - {'meta', 'articles', 'details'}:
                if before[key] != now[key]: raise ValueError('Non-citation content changed')
            count += len(before['articles'])
    if (base/'manifest.json').read_bytes() != original_raw: raise ValueError('Input changed')
    result = dict(verification=verified, domains=summary, preserved_central_articles=count,
                  removed_ids=sorted(retired_ids), added_ids=sorted(added_ids), source_unchanged=True)
    destination.with_name(destination.name+'-report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base', type=Path, required=True); p.add_argument('--dest', type=Path, required=True)
    p.add_argument('--plan', type=Path, required=True); a = p.parse_args()
    print(json.dumps(build(a.base, a.dest, a.plan)['verification'], ensure_ascii=False, indent=2))
