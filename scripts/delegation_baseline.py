"""Public-only, immutable comparison baselines for two pilot domains."""
import gzip
import hashlib
import json
from pathlib import Path

DOMAINS = ('tax', 'public_institutions')


def read_ref(root, ref):
    if ref['url'] != 'data/' + ref['sha256'] + '.json.gz':
        raise ValueError('Unsafe baseline shard path')
    raw = (Path(root) / ref['url']).read_bytes()
    if len(raw) != ref['bytes'] or hashlib.sha256(raw).hexdigest() != ref['sha256']:
        raise ValueError('Baseline checksum mismatch')
    return json.loads(gzip.decompress(raw))


def eligible(entry):
    kind, name = entry.get('kind', ''), entry['name']
    return kind in ('법률', '대통령령') or (not kind and name.endswith(('법', '법률', ' 시행령')))


def public_snapshot(root, entry, built_at):
    doc = read_ref(root, entry['file'])
    if doc['meta']['id'] != entry['id'] or doc['meta']['name'] != entry['name']:
        raise ValueError('Baseline document identity mismatch')
    fields = ('jo', 'label', 'title', 'text', 'deleted', 'effective')
    meta_fields = ('id', 'name', 'domain', 'kind', 'effective', 'url')
    details = dict(doc.get('details', {}))
    for ref in entry.get('parts', []):
        details.update(read_ref(root, ref))
    # Retain old explicit evidence for deleted/renumbered parent provisions.
    evidence = {jo: dict(rows=[r for r in d.get('rows', []) if r.get('direction') == 'reverse'],
                        analysis_error=d.get('analysis_error', ''), issues=d.get('issues', []))
                for jo, d in details.items()}
    return dict(schema=1, kind='delegation-baseline', meta={k: doc['meta'].get(k, '') for k in meta_fields}, built_at=built_at,
                articles=[{k: a.get(k, False if k == 'deleted' else '') for k in fields} for a in doc['articles']],
                details=evidence)


def signature(snapshot):
    return (snapshot['meta']['effective'], [(a['jo'], a['text'], a.get('deleted', False)) for a in snapshot['articles']])


def attach_catalog(writer, domain, catalog, previous_site=None):
    if domain not in DOMAINS:
        return
    prior_catalog = None
    if previous_site:
        previous_site = Path(previous_site)
        manifest = json.loads((previous_site / 'manifest.json').read_text(encoding='utf-8'))
        entry = next((d for d in manifest['domains'] if d['id'] == domain), None)
        if entry:
            prior_catalog = read_ref(previous_site, entry['catalog'])
    prior_laws = {d['id']: d for d in (prior_catalog or {}).get('laws', [])}
    prior_baselines = (prior_catalog or {}).get('delegation_review', {}).get('baselines', {})
    baselines = {}
    for entry in catalog['laws']:
        if not eligible(entry):
            continue
        current = public_snapshot(writer.dest, entry, catalog['built_at'])
        previous = prior_laws.get(entry['id'])
        if previous:
            baseline = public_snapshot(previous_site, previous, prior_catalog['built_at'])
            prior = prior_baselines.get(entry['id'])
            if signature(current) == signature(baseline) and prior:
                baseline = read_ref(previous_site, prior['file'])
                mode = prior['mode']
            elif signature(current) != signature(baseline):
                mode = 'previous-version'
            else:
                mode = 'initial'
        else:
            baseline, mode = current, 'initial'
        baselines[entry['id']] = dict(file=writer.data(baseline), mode=mode,
                                     effective=baseline['meta']['effective'], built_at=baseline['built_at'])
    catalog['delegation_review'] = dict(schema=1, baselines=baselines,
        note='공개 수집 판본의 본칙·명시적 위임과 저장 인용을 점검합니다. 위임 이행·개정 누락을 확정하지 않습니다.')
