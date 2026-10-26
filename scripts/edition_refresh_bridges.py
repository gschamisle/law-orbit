"""Refresh only existing public bridge pairs against the new public editions.

The destination is a new unpacked build tree. Existing bridge references may
still live in the packed immutable base; current document references are read
from the destination first, with hash-verified base fallback. This module never
adds a pair merely because a newer parser profile happens to declare it.
"""
from copy import deepcopy
import json
from pathlib import Path

from core.forex_finance_links import BRIDGE_KINDS, bridge
from scripts.build_forex_finance_site import payloads
from scripts.build_static_galaxies import Writer
from scripts.static_storage import Storage


class _Inputs:
    def __init__(self, base, stage):
        self.base = Storage(base)
        self.stage = Storage(stage, {})

    def read(self, ref):
        # An invalid/corrupt destination asset must not silently fall back.
        try:
            return self.stage.read(ref)
        except FileNotFoundError:
            return self.base.read(ref)

    def snapshot(self, domain):
        catalog = self.read(domain['catalog'])
        if catalog['built_at'] != domain['built_at']:
            raise ValueError('Bridge catalog collection date mismatch')
        result = dict(entries=catalog['laws'], documents={}, details={},
                      built_at=catalog['built_at'])
        for entry in catalog['laws']:
            if entry['id'] in result['documents']:
                raise ValueError('Duplicate bridge document identifier')
            packed = self.read(entry['file'])
            if any(packed['meta'].get(k) != entry.get(k)
                   for k in ('id', 'name', 'domain', 'effective')):
                raise ValueError('Bridge document edition mismatch')
            if entry['domain'] != domain['id']:
                raise ValueError('Bridge catalog domain mismatch')
            details = dict(packed.get('details', {}))
            for part in entry.get('parts', []):
                value = self.read(part)
                if set(value).intersection(details):
                    raise ValueError('Duplicate bridge article detail')
                details.update(value)
            if any(a['jo'] not in details for a in packed['articles']):
                raise ValueError('Missing source article details')
            result['documents'][entry['id']] = packed
            result['details'][entry['id']] = details
        return result


def _pair(value):
    identity = (value.get('domain'), value.get('peer'))
    pair = next((pair for pair in BRIDGE_KINDS if set(pair) == set(identity)), None)
    if (pair is None or identity[0] == identity[1] or value.get('schema') != 1
            or value.get('kind') != BRIDGE_KINDS[pair]):
        raise ValueError('Unrecognized published bridge pair or kind')
    return pair


def _check_payload(value, snapshots):
    """Check embedded reader references as well as the pair's date labels."""
    domain, peer = value['domain'], value['peer']
    if value['editions'] != {d: snapshots[d]['built_at'] for d in (domain, peer)}:
        raise ValueError('Refreshed bridge edition mismatch')
    owners = {e['id']: e for e in snapshots[domain]['entries']}
    neighbors = {e['id']: e for e in snapshots[peer]['entries']}
    embedded = {}
    for entry in value['entries']:
        if entry['id'] in embedded or neighbors.get(entry['id']) != entry:
            raise ValueError('Stale or duplicate bridge reader reference')
        embedded[entry['id']] = entry
    for law_id, sections in value['laws'].items():
        if law_id not in owners:
            raise ValueError('Missing bridge source law')
        numbers = {a['jo'] for a in snapshots[domain]['documents'][law_id]['articles']}
        if not set(sections).issubset(numbers):
            raise ValueError('Missing bridge source article')
        for section in sections.values():
            for row in section['rows']:
                neighbor_id = row['neighbor_id']
                if (neighbor_id not in embedded or row.get('neighbor_domain') != peer
                        or row.get('cross_domain') is not True):
                    raise ValueError('Missing bridge reader endpoint')
                if row['neighbor_kind'] == 'article':
                    article_numbers = {a['jo'] for a in snapshots[peer]['documents'][neighbor_id]['articles']}
                    if row['neighbor_jo'] not in article_numbers:
                        raise ValueError('Missing bridge neighbor article')
                expected = ((law_id, neighbor_id) if row['direction'] == 'forward'
                            else (neighbor_id, law_id))
                if row['direction'] not in ('forward', 'reverse') or expected != (row['source_id'], row['target_id']):
                    raise ValueError('Bridge direction or endpoint mismatch')


def rebuild_bridges(base: Path, stage: Path, manifest: dict,
                    changed_domains: set[str], writer: Writer) -> dict:
    """Replace affected pair payloads, preserving all other public bridge bytes.

    Catalog changes also count as affected, including reverse-index-only
    changes. The caller owns manifest versioning, final reachability pruning,
    packing and publication. Only ``cross_domain`` and, when necessary, the
    already-present ``remedy_guide`` are replaced here.
    """
    base, stage = Path(base).resolve(), Path(stage).resolve()
    if base == stage or base.is_relative_to(stage) or stage.is_relative_to(base):
        raise ValueError('Bridge refresh requires an independent destination')
    if Path(writer.dest).resolve() != stage or manifest.get('data_packs'):
        raise ValueError('Bridge refresh requires its own unpacked writer')
    base_raw = (base / 'manifest.json').read_bytes()
    original = json.loads(base_raw)
    if manifest.get('cross_domain', {}) != original.get('cross_domain', {}):
        raise ValueError('Bridge refresh input must retain original pair references')
    domains = {d['id']: d for d in manifest['domains']}
    old_domains = {d['id']: d for d in original['domains']}
    if set(domains) != set(old_domains) or not set(changed_domains).issubset(domains):
        raise ValueError('Bridge refresh cannot add or remove domain scope')
    inferred = {d for d in domains if domains[d]['catalog'] != old_domains[d]['catalog']
                or domains[d]['built_at'] != old_domains[d]['built_at']}
    affected = set(changed_domains) | inferred
    inputs = _Inputs(base, stage)
    old_storage = Storage(base, original)
    containers, members, identities, pairs = {}, {}, {}, {}
    for domain, ref in original.get('cross_domain', {}).items():
        value = old_storage.read(ref)
        grouped = value.get('kind') == 'domain-bridge-set'
        if grouped and (value.get('schema') != 1 or value.get('domain') != domain
                        or not value.get('bridges')):
            raise ValueError('Invalid published bridge grouping')
        containers[domain] = (ref, value, grouped)
        members[domain] = list(value['bridges']) if grouped else [ref]
        for index, child in enumerate(members[domain]):
            payload = old_storage.read(child)
            pair = _pair(payload)
            identity = (domain, payload['peer'])
            if payload['domain'] != domain or identity in identities:
                raise ValueError('Duplicate or misdirected published bridge')
            if not set(pair).issubset(domains):
                raise ValueError('Published bridge references a missing domain')
            identities[identity] = (index, child)
            pairs[pair] = True
    if any((peer, domain) not in identities for domain, peer in identities):
        raise ValueError('Incomplete published bridge pair')
    snapshots = {}
    def current(domain):
        if domain not in snapshots:
            snapshots[domain] = inputs.snapshot(domains[domain])
        return snapshots[domain]
    reports, preserved = [], []
    for pair in pairs:
        if not affected.intersection(pair):
            preserved.append(list(pair))
            continue
        print('Refreshing published bridge: ' + ' / '.join(pair), flush=True)
        selected = {d: current(d) for d in pair}
        result = bridge(selected, pair=pair)
        rebuilt = payloads(result, selected)
        for domain in pair:
            peer = next(d for d in pair if d != domain)
            value = rebuilt[domain]
            if _pair(value) != pair:
                raise ValueError('Refreshed bridge kind changed')
            _check_payload(value, selected)
            index, _ = identities[(domain, peer)]
            members[domain][index] = writer.data(value)
        reports.append(dict(pair=list(pair), editions={d: selected[d]['built_at'] for d in pair},
                            report=result['report']))
    cross_domain = {}
    for domain, (ref, value, grouped) in containers.items():
        prior_members = value['bridges'] if grouped else [ref]
        if members[domain] == prior_members:
            cross_domain[domain] = ref
        elif grouped:
            wrapper = deepcopy(value)
            wrapper['bridges'] = members[domain]
            cross_domain[domain] = writer.data(wrapper)
        else:
            cross_domain[domain] = members[domain][0]
    # Check preservation by actual compressed bytes, not only reference equality.
    for pair in preserved:
        for domain in pair:
            peer = next(d for d in pair if d != domain)
            index, ref = identities[(domain, peer)]
            if members[domain][index] != ref:
                raise ValueError('Untouched bridge changed')
            old_storage.raw(ref)
    guide = None
    if 'remedy' in affected and original.get('remedy_guide'):
        from core.remedy_relations import reading_guide
        snap = current('remedy')
        docs = [dict(name=e['name'], effective=e['effective'], source_url=e['url'],
                     articles=snap['documents'][e['id']]['articles']) for e in snap['entries']]
        guide = reading_guide(docs)
        ids = {e['name']: e['id'] for e in snap['entries']}
        for row in guide['entries']:
            row['law_id'] = ids[row['law']]
    if (base / 'manifest.json').read_bytes() != base_raw:
        raise ValueError('Immutable bridge source changed during refresh')
    manifest['cross_domain'] = cross_domain
    if guide is not None:
        manifest['remedy_guide'] = guide
    return dict(refreshed_pairs=reports, preserved_pairs=preserved,
                inferred_changed_domains=sorted(inferred - set(changed_domains)),
                original_pair_count=len(pairs), pair_scope_unchanged=True,
                remedy_guide_refreshed=guide is not None,
                original_manifest_unchanged=True)
