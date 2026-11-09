"""Resolve list entries displaced by announced editions without using old bundles.

History flags differ by provider (see fsc_collection.LIST_GUIDES). The admrul
list API has no documented stable-ID filter: enumerate the complete issuer
scope, not a title query which can silently omit a predecessor after a rename.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib

from core.fsc_collection import (
    CollectionError, FSC_ORG, LIST_GUIDES, ROOT_TAG, ROW_TAG,
    field, list_record, require_id, xml_root, ymd,
)


def _history(request, target, scope, *, display, max_pages):
    rows, hashes, seen, expected = [], [], set(), None
    for page in range(1, max_pages + 1):
        params = dict(target=target, nw=1 if target == 'eflaw' else 2,
                      display=display, page=page, sort='lasc', **scope)
        raw = request('lawSearch.do', params)
        root = xml_root(raw)
        if root.tag != ROOT_TAG[target]:
            raise CollectionError('unexpected-history-envelope')
        try:
            count, returned = int(field(root, 'totalCnt')), int(field(root, 'page'))
        except ValueError:
            raise CollectionError('missing-history-pagination') from None
        if count < 0 or returned != page or (expected is not None and expected != count):
            raise CollectionError('history-pagination-changed')
        expected = count
        batch = root.findall(ROW_TAG[target])
        if len(batch) != min(display, max(0, count - len(rows))):
            raise CollectionError('short-or-oversized-history-page')
        for row in batch:
            prefix = '법령' if target == 'eflaw' else '행정규칙'
            key = (require_id(field(row, prefix + 'ID')),
                   require_id(field(row, prefix + '일련번호')), field(row, '시행일자'))
            if key in seen:
                raise CollectionError('duplicate-history-edition')
            seen.add(key)
        rows.extend(batch)
        hashes.append(hashlib.sha256(raw).hexdigest())
        if len(rows) == count:
            return rows, dict(list_status='complete', expected=count, received=len(rows),
                              pages=page, page_sha256=hashes, request_scope={k: v for k, v in params.items()
                                                                       if k != 'page'},
                              list_guide=LIST_GUIDES[target])
    raise CollectionError('history-page-limit-before-completion')


def resolve_inventory(request, inventory, *, display=100, max_pages=1000):
    """Keep original list counts/rows; attach a verified effective predecessor.

    No predecessor is allowed only when a complete history supports a future
    new enactment. Other missing histories, repeal or tied editions fail closed.
    """
    if not 1 <= display <= 100 or max_pages < 1:
        raise CollectionError('invalid-history-options')
    as_of = ymd(inventory['as_of'])
    result, history_cache = deepcopy(inventory), {}
    for layer in result['layers'].values():
        if layer.get('list_status') != 'complete' or any(
                layer.get(key) != len(layer['records']) for key in ('expected', 'received')):
            raise CollectionError('incomplete-inventory')
        for record in layer['records']:
            if record['state'] != 'scheduled':
                continue
            if record['effective'] <= as_of:
                raise CollectionError('scheduled-state-date-mismatch')
            if record.get('edition_resolution', {}).get('as_of') == as_of:
                continue
            target = record['provider']
            fss = record.get('collection_scope') == 'fss-sector-bylaws'
            scope = ({'LID': record['document_id']} if target == 'eflaw' else
                     {} if fss else {'org': FSC_ORG})
            cache_key = (target, tuple(sorted(scope.items())))
            if cache_key not in history_cache:
                history_cache[cache_key] = _history(request, target, scope,
                                                    display=display, max_pages=max_pages)
            rows, provenance = history_cache[cache_key]
            id_tag = '법령ID' if target == 'eflaw' else '행정규칙ID'
            matches = [list_record(row, target, as_of, fss=fss) for row in rows
                       if field(row, id_tag) == record['document_id']]
            eligible = [r for r in matches if r['effective'] <= as_of]
            resolution = dict(as_of=as_of, scheduled_edition_key=record['edition_key'],
                              history=provenance,
                              matched_editions=[{k: r[k] for k in ('uid', 'edition_key', 'name',
                                                'effective', 'promulgated', 'amendment_type')}
                                                for r in matches])
            if eligible:
                latest = max((r['effective'], r['promulgated']) for r in eligible)
                selected = [r for r in eligible if (r['effective'], r['promulgated']) == latest]
                if len(selected) != 1:
                    raise CollectionError('ambiguous-effective-history-edition')
                current = selected[0]
                if '폐지' in current['amendment_type']:
                    raise CollectionError('effective-history-is-repealed')
                if current['amendment_type'] not in ('제정', '일부개정', '전부개정', '일괄개정', '타법개정'):
                    raise CollectionError('unknown-effective-history-amendment-type')
                resolution.update(status='effective-predecessor-verified',
                                  selected_edition_key=current['edition_key'])
                current['edition_resolution'] = resolution
                record['effective_record'] = current
            elif any(r.get('amendment_type') == '제정' for r in matches + [record]):
                resolution.update(status='new-enactment-not-yet-effective', selected_edition_key=None)
                record.pop('effective_record', None)
            else:
                raise CollectionError('effective-history-unavailable')
            record['edition_resolution'] = resolution
    # Validate the same resolved view that signatures and body collection use.
    for layer in result['layers'].values():
        list(effective_records(layer, as_of=as_of))
    return result


def effective_records(layer, *, as_of):
    """One pinned effective record per list UID, shared by signatures/collection."""
    as_of = ymd(as_of)
    seen = set()
    for listed in layer['records']:
        record = listed
        if listed['state'] == 'scheduled':
            resolution = listed.get('edition_resolution', {})
            if (resolution.get('as_of') != as_of
                    or resolution.get('scheduled_edition_key') != listed['edition_key']
                    or listed['effective'] <= as_of
                    or resolution.get('history', {}).get('list_status') != 'complete'):
                raise CollectionError('unresolved-scheduled-edition')
            if resolution.get('status') == 'new-enactment-not-yet-effective':
                if listed.get('effective_record') is not None:
                    raise CollectionError('invalid-scheduled-resolution')
                continue
            record = listed.get('effective_record') or {}
            if (resolution.get('status') != 'effective-predecessor-verified'
                    or record.get('uid') != listed['uid']
                    or record.get('edition_key') != resolution.get('selected_edition_key')
                    or record.get('provider') != listed.get('provider')):
                raise CollectionError('invalid-scheduled-resolution')
        if (record.get('state') != 'current-candidate'
                or ymd(record.get('effective', '')) > as_of
                or ymd(record.get('promulgated', '')) > as_of):
            raise CollectionError('not-effective-on-collection-date')
        if (record.get('provider') not in ('eflaw', 'admrul')
                or record.get('uid') != f"{record['provider']}:{require_id(record.get('document_id', ''))}"
                or record.get('edition_key') != f"{record['uid']}:{require_id(record.get('version_id', ''))}:{record['effective']}"):
            raise CollectionError('invalid-effective-identity')
        if record['uid'] in seen:
            raise CollectionError('duplicate-effective-document')
        seen.add(record['uid'])
        yield record
