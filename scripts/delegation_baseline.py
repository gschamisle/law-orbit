"""Public-only, immutable comparison baselines for two pilot domains."""
import gzip
import hashlib
import json
from pathlib import Path
from scripts.static_storage import Storage

DOMAINS = ('tax', 'public_institutions')


def read_ref(root, ref):
    return Storage(root).read(ref)


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


def body_digest(articles):
    projection = [{k: a.get(k, '') for k in ('jo', 'title', 'text', 'effective')} for a in articles]
    return hashlib.sha256(json.dumps(projection, ensure_ascii=False, separators=(',', ':'), sort_keys=True).encode()).hexdigest()


def attach_official_history(writer, catalog, folder, public_manifest_sha256):
    """Attach verified historical texts without inventing old reverse evidence."""
    folder = Path(folder).resolve()
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    if (manifest.get('schema') != 1 or manifest.get('kind') != 'tax-delegation-history'
            or manifest.get('public_manifest_sha256') != public_manifest_sha256):
        raise ValueError('Historical texts belong to a different public snapshot')
    expected = {'법인세법', '소득세법', '조세특례제한법'}
    records = manifest['laws']
    if len(records) != 3 or {r['name'] for r in records} != expected:
        raise ValueError('Expected three verified tax histories')
    laws = {entry['id']: entry for entry in catalog['laws']}
    report = []
    for record in records:
        entry = laws[record['id']]
        if entry['name'] != record['name'] or entry['effective'] != record['current']['effective']:
            raise ValueError('Historical comparison current edition mismatch')
        ref = record['baseline']
        path = (folder / ref['path']).resolve()
        if not path.is_relative_to(folder):
            raise ValueError('Unsafe history file path')
        raw = path.read_bytes()
        if len(raw) != ref['bytes'] or hashlib.sha256(raw).hexdigest() != ref['sha256']:
            raise ValueError('Historical text checksum mismatch')
        baseline = json.loads(raw)
        if (baseline.get('schema') != 1 or baseline.get('kind') != 'delegation-baseline'
                or baseline['meta']['id'] != entry['id'] or baseline['meta']['name'] != entry['name']
                or baseline['meta']['domain'] != 'tax'
                or baseline['meta']['effective'] != record['previous']['effective']
                or not baseline['meta']['effective'] < entry['effective']):
            raise ValueError('Historical text identity or temporal order mismatch')
        if (baseline.get('details') != {} or
                baseline.get('evidence_availability', {}).get('reverse_citations') != 'not-collected'):
            raise ValueError('Historical lower-law evidence must remain explicitly uncollected')
        if not baseline.get('articles') or len({a['jo'] for a in baseline['articles']}) != len(baseline['articles']):
            raise ValueError('Missing or duplicate historical articles')
        if (body_digest(baseline['articles']) != record['previous']['text_sha256'] or
                body_digest(read_ref(writer.dest, entry['file'])['articles']) != record['current']['text_sha256']):
            raise ValueError('Historical comparison body digest mismatch')
        catalog['delegation_review']['baselines'][entry['id']] = dict(
            file=writer.data(baseline), mode='previous-version',
            effective=baseline['meta']['effective'], built_at=baseline['built_at'])
        report.append(dict(name=entry['name'], previous=baseline['meta']['effective'],
                           current=entry['effective'], reverse_citations='not-collected'))
    return report


def attach_catalog(writer, domain, catalog, previous_site=None, *, skip_ids=()):
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
        if not eligible(entry) or entry['id'] in skip_ids:
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
