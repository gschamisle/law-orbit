"""Edition overlays preserve immutable public evidence and rebuild both directions.

All document bodies in this file are synthetic test fixtures, not legal text.
"""
from collections import defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.universe_builder import build_universe
from scripts.build_static_galaxies import Writer, export_documents, ident
from scripts.delegation_baseline import public_snapshot
from scripts.static_storage import Storage


ROOT = Path(__file__).resolve().parents[1]
SOURCE = '국세기본법'
OLD_TARGET = '민법'
NEW_TARGET = '민사집행법'
INCOMING = '국세징수법'
LOCAL = '합성시 시세 기본 조례'
CENTRAL = '지방세기본법'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def document(name, serial, text, *, category='tax', effective='20260101', jo='1'):
    label = f'제{jo}조'
    return dict(name=name, mst=str(serial), law_id=str(serial), category=category, provider='eflaw',
                effective=effective, kind='법률', articles=[dict(jo=jo, title='합성 검증',
                text=f'{label}(합성 검증) {text}', effective=effective)])


def graph_for(documents, domain='tax'):
    return build_universe(dict(laws=documents, built_at='20261020'),
                          focus_categories=(domain,), preserve_external=True)


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def catalog_at(root, domain='tax', region=''):
    storage = Storage(root)
    manifest = json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    item = next(d for d in manifest['domains'] if d['id'] == domain)
    catalog = storage.read(item['catalog'])
    if region:
        catalog = storage.read(next(r for r in catalog['regions'] if r['id'] == region)['catalog'])
    return catalog


def public_document(root, name, domain='tax', region=''):
    entry = next(d for d in catalog_at(root, domain, region)['laws'] if d['name'] == name)
    storage = Storage(root)
    body = storage.read(entry['file'])
    details = deepcopy(body.get('details', {}))
    for ref in entry.get('parts', []):
        details.update(storage.read(ref))
    return entry, body, details


def fixture_site(root):
    """A -> B and D -> A; one local source -> central article 1."""
    root.mkdir(parents=True)
    writer = Writer(root)
    docs = [document(SOURCE, 101, f'「{OLD_TARGET}」 제1조를 따른다.'),
            document(OLD_TARGET, 102, '기존 연결 대상에 관한 합성 본문.'),
            document(NEW_TARGET, 103, '새 연결 대상에 관한 합성 본문.'),
            document(INCOMING, 104, f'「{SOURCE}」 제1조를 따른다.')]
    entries, _ = export_documents(writer, 'tax', '', docs, graph_for(docs))
    preserved = next(e for e in entries if e['name'] == OLD_TARGET)
    body = Storage(root).read(preserved['file'])
    # Previously published, verified content is deliberately not reconstructible
    # from the article parser: an overlay must retain these exact public fields.
    body['annexes'] = [dict(ref='별표 1', title='합성 별표', effective='20260101',
                           urls=['https://www.law.go.kr/test-annex.pdf'],
                           status='explicit-citations', analysis=dict(marker='old-analysis'),
                           connections=[], issues=[])]
    body['pdf_analysis'] = dict(marker='old-pdf-pages-and-anchors')
    body['unstructured_text'] = '보존할 합성 PDF 원문'
    preserved['file'] = writer.data(body)
    historic = public_snapshot(root, preserved, '20250101')
    historic['meta']['effective'] = '20250101'
    historic['articles'][0].update(effective='20250101', text='보존할 과거 판본의 합성 본문')
    history = writer.data(historic)
    chart = writer.data(dict(nodes=[dict(id=e['name'], full_name=e['name'],
                            web_law=e['id'], category='tax') for e in entries], links=[], dust=[]))
    catalog = dict(laws=entries, built_at='20261020', sectors={'all':'전체 연결'}, overview=chart,
                   coverage='합성 회귀검증 범위', delegation_review=dict(
                       baselines={preserved['id']: dict(file=history, mode='official-previous-version',
                           effective='20250101', built_at='20250101')}))

    central = [document(CENTRAL, 201, '중앙 첫째 조문.', category='local_tax')]
    central[0]['articles'].append(dict(jo='2', title='둘째 조문',
                                     text='제2조(둘째 조문) 중앙 둘째 조문.', effective='20260101'))
    local = document(LOCAL, 202, f'「{CENTRAL}」 제1조를 따른다.', category='local_tax')
    local.update(kind='조례', provider='ordin', source_url='https://www.law.go.kr/LSW/ordinInfoP.do?ordinSeq=202')
    national = defaultdict(list)
    central_ids = {CENTRAL: ident('local_tax', '', CENTRAL)}
    regional, _ = export_documents(writer, 'local_tax', 'region1', central+[local],
        graph_for(central+[local], 'local_tax'), write_names={LOCAL},
        central_ids=central_ids, national=national)
    central_entries, _ = export_documents(writer, 'local_tax', '', central,
        graph_for(central, 'local_tax'), national=national)
    local_chart = writer.data(dict(nodes=[dict(id=CENTRAL, category='local_tax')], links=[], dust=[]))
    local_catalog = dict(laws=central_entries, built_at='20261020', overview=local_chart,
        sectors={'all':'중앙 법령·전국 역인용'}, coverage='합성 지역 범위',
        regions=[dict(id='region1', authority='합성시', province='합성도', inventory=1,
                      indexed=1, catalog=writer.data(dict(laws=regional,
                          built_at='20261020', sectors={'all':'전체 연결'}, coverage='합성 조례',
                          overview=local_chart)))])
    manifest = dict(schema=1, title='합성 판본 회귀검증', version='fixed-public-version',
        domains=[dict(id='tax', title='국세', laws=len(entries), catalog=writer.data(catalog), built_at='20261020'),
                 dict(id='local_tax', title='지방세', laws=2, catalog=writer.data(local_catalog), built_at='20261020')])
    (root/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
    (root/'index.html').write_text('Synthetic static fixture', encoding='utf-8')
    return dict(documents=docs, local=local, central=central, history=history)


class EditionRefreshTests(unittest.TestCase):
    def setUp(self):
        output = ROOT/'output'
        output.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=output)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.base = self.root/'base'
        self.fixture = fixture_site(self.base)
        self.base_bytes = snapshot(self.base)
        self.original_catalog = catalog_at(self.base)
        self.stage = self.root/'stage'
        self.stage.mkdir()
        self.writer = Writer(self.stage)

    def change(self, name=SOURCE, *, text=None, fresh_name=None,
               kind='edition', domain='tax', region=''):
        entry, body, _ = public_document(self.base, name, domain, region)
        old = self.fixture['local'] if region else next(d for d in self.fixture['documents'] if d['name'] == name)
        fresh = deepcopy(old)
        if kind == 'edition':
            fresh.update(mst=str(int(old['mst'])+1000), effective='20261026')
            fresh['source_url'] = ('https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq='
                                   +fresh['mst']+'&efYd='+fresh['effective'])
            for article in fresh['articles']:
                article['effective'] = fresh['effective']
            if region:
                fresh['source_url'] = 'https://www.law.go.kr/LSW/ordinInfoP.do?ordinSeq='+fresh['mst']
        if fresh_name:
            fresh['name'] = fresh_name
        if text is not None:
            fresh['articles'][0]['text'] = '제1조(합성 검증) '+text
        provider = 'ordin' if region else 'eflaw'
        expected = [provider, old['law_id'], fresh['mst'], fresh['effective']]
        return dict(finding=dict(provider=provider, key=entry['id'], domains=[domain],
                    serial=old['mst'], stable_id=old['law_id'], name=entry['name'],
                    url=entry['url'], effective=entry['effective'], current=dict(
                        provider=provider, stable_id=old['law_id'], serial=fresh['mst'], effective=fresh['effective'])),
                    identity=dict(provider=provider, stable_id=old['law_id'],
                        new_serial=fresh['mst'], new_effective=fresh['effective']),
                    change_kind=kind, fresh_document=fresh,
                    validation=dict(status='verified', expected_identity=expected,
                        fresh_document_sha256=digest(json.dumps(fresh, ensure_ascii=False, sort_keys=True).encode())))

    def refresh(self, replacements, *, domain='tax', region='', **kwargs):
        from scripts.build_edition_refresh_site import refresh_catalog
        catalog = catalog_at(self.base, domain, region)
        result = refresh_catalog(Storage(self.base), catalog, domain, replacements,
                                 self.writer, '20261026', **kwargs)
        self.assertEqual(snapshot(self.base), self.base_bytes)
        return result

    def resulting_document(self, catalog, name):
        entry = next(e for e in catalog['laws'] if e['name'] == name)
        # Unchanged content-addressed assets may still refer into the base.
        def read(ref):
            source = self.stage if (self.stage/ref['url']).exists() else self.base
            return Storage(source).read(ref)
        body = read(entry['file'])
        details = deepcopy(body.get('details', {}))
        for ref in entry.get('parts', []):
            details.update(read(ref))
        return entry, body, details

    def rows(self, catalog, name, direction, jo='1'):
        return [r for r in self.resulting_document(catalog, name)[2][jo]['rows']
                if r['direction'] == direction]

    def test_changed_source_removes_old_edges_and_adds_new_edges_in_both_directions(self):
        change = self.change(text=f'「{NEW_TARGET}」 제1조를 따른다.')
        catalog, _, _ = self.refresh([change])
        outgoing = self.rows(catalog, SOURCE, 'forward')
        self.assertEqual({r['target_law'] for r in outgoing}, {NEW_TARGET})
        self.assertFalse([r for r in self.rows(catalog, OLD_TARGET, 'reverse') if r['source_law'] == SOURCE])
        incoming = [r for r in self.rows(catalog, NEW_TARGET, 'reverse') if r['source_law'] == SOURCE]
        self.assertEqual(len(incoming), 1)
        self.assertEqual(incoming[0]['evidence_id'], outgoing[0]['evidence_id'])
        self.assertEqual(incoming[0]['source_effective'], '20261026')

    def test_changed_target_keeps_unchanged_incoming_quote_and_updates_edition_metadata(self):
        before = [r for r in public_document(self.base, INCOMING)[2]['1']['rows'] if r['direction'] == 'forward'][0]
        catalog, _, _ = self.refresh([self.change(text='변경된 합성 본문.')])
        forward = self.rows(catalog, INCOMING, 'forward')[0]
        reverse = [r for r in self.rows(catalog, SOURCE, 'reverse') if r['source_law'] == INCOMING]
        self.assertEqual(len(reverse), 1)
        self.assertEqual(forward['target_effective'], '20261026')
        self.assertIn('lsiSeq=1101', forward['target_url'])
        self.assertEqual(forward['evidence_id'], before['evidence_id'])
        self.assertEqual(forward['raw'], before['raw'])
        self.assertEqual(reverse[0]['evidence_id'], before['evidence_id'])
        self.assertEqual(public_document(self.base, INCOMING)[1]['articles'],
                         self.resulting_document(catalog, INCOMING)[1]['articles'])

    def test_changed_target_preserves_unstructured_pdf_incoming_without_source_article_number(self):
        writer = Writer(self.base)
        catalog = catalog_at(self.base)
        source_entry = next(e for e in catalog['laws'] if e['name'] == INCOMING)
        target_entry = next(e for e in catalog['laws'] if e['name'] == SOURCE)
        source_body = Storage(self.base).read(source_entry['file'])
        target_body = Storage(self.base).read(target_entry['file'])
        forward = deepcopy(next(r for r in source_body['details']['1']['rows'] if r['direction'] == 'forward'))
        quote = f'「{SOURCE}」 제1조'
        forward.update(evidence_id='synthetic-pdf-to-article', source_jo='', source_ref='본문 제2장',
            source_title='합성 PDF 인용', source_granularity='text', source_layer='procurement-pdf-prose',
            source_page=2, source_start=0, source_end=len(quote), raw=quote, cite_raw=quote, context=quote)
        source_body['text_connections'] = [forward]
        reverse = deepcopy(forward)
        reverse.update(direction='reverse', neighbor_law=INCOMING, neighbor_id=source_entry['id'],
            neighbor_jo='', neighbor_ref='본문 제2장', neighbor_kind='text', neighbor_title='합성 PDF 인용')
        target_body['details']['1']['rows'].append(reverse)
        source_entry['file'] = writer.data(source_body)
        target_entry['file'] = writer.data(target_body)
        manifest = json.loads((self.base/'manifest.json').read_text(encoding='utf-8'))
        next(d for d in manifest['domains'] if d['id'] == 'tax')['catalog'] = writer.data(catalog)
        (self.base/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
        self.base_bytes = snapshot(self.base)
        result, _, _ = self.refresh([self.change(text='변경된 합성 본문.')])
        retained = [r for r in self.rows(result, SOURCE, 'reverse')
                    if r.get('evidence_id') == reverse['evidence_id']]
        self.assertEqual(len(retained), 1)
        for field in ('source_jo', 'source_ref', 'source_layer', 'source_page', 'source_start',
                      'source_end', 'raw', 'cite_raw', 'evidence_id', 'neighbor_kind'):
            self.assertEqual(retained[0][field], reverse[field], field)
        self.assertEqual(retained[0]['target_effective'], '20261026')

    def test_renaming_keeps_bookmark_id_and_original_evidence_but_updates_canonical_names(self):
        original_entry, _, _ = public_document(self.base, SOURCE)
        old_quote = self.rows(self.original_catalog, INCOMING, 'forward')[0]['raw']
        new_name = '조세기본법'
        catalog, _, _ = self.refresh([self.change(fresh_name=new_name)])
        entry, body, _ = self.resulting_document(catalog, new_name)
        self.assertEqual(entry['id'], original_entry['id'])
        self.assertEqual(body['meta']['id'], original_entry['id'])
        self.assertEqual(body['meta']['name'], new_name)
        self.assertIn(SOURCE, entry.get('former_names', body['meta'].get('former_names', [])))
        incoming = self.rows(catalog, INCOMING, 'forward')[0]
        self.assertEqual(incoming['target_id'], original_entry['id'])
        self.assertEqual(incoming['target_law'], new_name)
        self.assertEqual(incoming['neighbor_law'], new_name)
        self.assertEqual(incoming['raw'], old_quote)
        self.assertEqual({r['source_law'] for r in self.rows(catalog, new_name, 'forward')}, {new_name})

    def test_removed_target_article_keeps_incoming_evidence_with_missing_article_status(self):
        change = self.change(text='새 판본에서 번호가 달라진 합성 본문.')
        article = change['fresh_document']['articles'][0]
        article.update(jo='2', text=article['text'].replace('제1조', '제2조', 1))
        before = self.rows(self.original_catalog, INCOMING, 'forward')[0]
        catalog, _, _ = self.refresh([change])
        row = self.rows(catalog, INCOMING, 'forward')[0]
        self.assertEqual(row['evidence_id'], before['evidence_id'])
        self.assertEqual(row['raw'], before['raw'])
        self.assertEqual(row['target_provision_status'], 'not-found-in-collected-edition')
        self.assertEqual(row['target_effective'], '20261026')

    def test_title_only_update_preserves_body_and_annex_evidence(self):
        old_entry, old_body, old_details = public_document(self.base, OLD_TARGET)
        catalog, _, _ = self.refresh([self.change(OLD_TARGET, fresh_name='민사기본법', kind='title-metadata')])
        entry, body, _ = self.resulting_document(catalog, '민사기본법')
        self.assertEqual(entry['id'], old_entry['id'])
        self.assertEqual(entry['effective'], old_entry['effective'])
        for key in ('articles', 'annexes', 'pdf_analysis', 'unstructured_text'):
            self.assertEqual(body[key], old_body[key], key)

    def test_unmodified_body_annex_pdf_and_history_survive_changed_neighbor(self):
        _, old_body, _ = public_document(self.base, OLD_TARGET)
        catalog, _, _ = self.refresh([self.change(text=f'「{NEW_TARGET}」 제1조를 따른다.')])
        _, body, _ = self.resulting_document(catalog, OLD_TARGET)
        for key in ('articles', 'annexes', 'pdf_analysis', 'unstructured_text'):
            self.assertEqual(body[key], old_body[key], key)
        self.assertEqual(catalog['delegation_review'], self.original_catalog['delegation_review'])
        ref = self.fixture['history']
        self.assertEqual(Storage(self.base).raw(ref), self.base_bytes[ref['url']])

    def test_local_change_returns_only_new_central_reverse_rows_with_regional_ids(self):
        central_catalog = catalog_at(self.base, 'local_tax')
        central_entries = central_catalog['laws']
        central_docs = {entry['id']: Storage(self.base).read(entry['file']) for entry in central_entries}
        catalog, _, national = self.refresh([self.change(LOCAL,
            text=f'「{CENTRAL}」 제2조를 따른다.', domain='local_tax', region='region1')],
            domain='local_tax', region='region1',
            context_entries=central_entries, context_documents=central_docs)
        central_id = central_entries[0]['id']
        outgoing = self.rows(catalog, LOCAL, 'forward')
        self.assertEqual(len(outgoing), 1)
        self.assertEqual(outgoing[0]['target_id'], central_id)
        self.assertEqual(outgoing[0]['target_ref'], '제2조')
        self.assertFalse(national.get(central_id, {}).get('1'))
        incoming = national[central_id]['2']
        self.assertEqual(len(incoming), 1)
        self.assertEqual(incoming[0]['source_id'], ident('local_tax', 'region1', LOCAL))
        self.assertEqual(incoming[0]['evidence_id'], outgoing[0]['evidence_id'])

    def test_mismatched_fixed_base_version_and_hash_fail_without_modifying_input(self):
        from scripts.build_edition_refresh_site import build
        for version, sha in (('wrong-version', digest(self.base_bytes['manifest.json'])),
                             ('fixed-public-version', '0'*64)):
            with self.subTest(version=version, sha=sha):
                source = self.root/'sources.json'
                source.write_text(json.dumps(dict(base_data_version=version,
                    base_manifest_sha256=sha, rows=[self.change()])), encoding='utf-8')
                source_bytes = source.read_bytes()
                with self.assertRaisesRegex(ValueError, '(?i)base|snapshot|manifest|version|hash'):
                    build(self.base, source, self.root/'rejected-site', validate_site=False)
                self.assertEqual(source.read_bytes(), source_bytes)
                self.assertEqual(snapshot(self.base), self.base_bytes)

    def test_unverified_and_future_replacements_are_not_published_as_current(self):
        for state, effective in (('pending', '20261026'), ('verified', '20261029'),
                                 ('verified', '99991231')):
            with self.subTest(state=state, effective=effective):
                change = self.change()
                change['validation']['status'] = state
                change['fresh_document']['effective'] = effective
                with self.assertRaisesRegex(ValueError, '(?i)unverified|unconfirmed|future'):
                    self.refresh([change])

    def test_production_build_rejects_body_changed_after_collection_verification(self):
        from scripts.build_edition_refresh_site import build
        change = self.change()
        change['fresh_document']['articles'][0]['text'] += ' 검증 후 추가된 문구'
        sources = self.root/'tampered-sources.json'
        sources.write_text(json.dumps(dict(base_data_version='fixed-public-version',
            base_manifest_sha256=digest(self.base_bytes['manifest.json']), as_of='20261026',
            rows=[change]), ensure_ascii=False), encoding='utf-8')
        before = sources.read_bytes()
        destination = self.root/'tampered-build'
        with self.assertRaisesRegex(ValueError, 'fresh document checksum mismatch'):
            build(self.base, sources, destination, validate_site=False)
        self.assertFalse(destination.exists())
        self.assertFalse(destination.with_name(destination.name+'-unpacked').exists())
        self.assertEqual(sources.read_bytes(), before)
        self.assertEqual(snapshot(self.base), self.base_bytes)

    def test_collected_identity_is_checked_even_when_document_hash_was_recomputed(self):
        from scripts.build_edition_refresh_site import validate_approved_sources
        change = self.change()
        change['fresh_document']['mst'] = '999999'
        change['validation']['fresh_document_sha256'] = digest(json.dumps(
            change['fresh_document'], ensure_ascii=False, sort_keys=True).encode())
        with self.assertRaisesRegex(ValueError, 'fresh document identity mismatch'):
            validate_approved_sources(dict(rows=[change]))

    def test_collector_rerun_preserves_reviewed_sources_before_any_api_or_delta_read(self):
        from scripts import collect_edition_refresh_sources as collector
        output = self.root/'collected'
        output.mkdir()
        source = output/'sources.json'
        source.write_text(json.dumps(dict(reviewed_citation_corrections=[dict(approved=True)],
            public_notices={'tax':'검토한 안내'}, base_manifest_sha256='fixed-base'), ensure_ascii=False), encoding='utf-8')
        before = source.read_bytes()
        with patch.object(collector, 'OUT', output), patch.object(collector, 'read', side_effect=AssertionError('Must stop before reading delta')):
            with self.assertRaisesRegex(FileExistsError, 'reviewed corrections'):
                collector.main()
        self.assertEqual(source.read_bytes(), before)

    def reviewed_ownership_fixture(self):
        change = self.change(text='계약 품질은 물품구매계약 품질관리 특수조건에 따르며 제17조의 기준을 따른다.')
        text = change['fresh_document']['articles'][0]['text']
        start = text.index('제17조')
        before = dict(target_name=SOURCE, target_ref='제17조', raw='제17조',
            start=start, end=start+len('제17조'), relation='direct', via_range=False,
            target_provision_status='collected', context_review=False, alias_basis=[])
        after = {**before, 'target_name':'물품구매계약 품질관리 특수조건',
                 'target_provision_status':'not-collected', 'context_review':True}
        review = dict(domain='tax', law=SOURCE, jo='1', effective='20261026',
                      source_sha256=digest(text.encode()), before=before, after=[after], context=text)
        return change, review

    def test_current_article_hash_bound_review_corrects_ownership_without_changing_quote(self):
        change, review = self.reviewed_ownership_fixture()
        before_catalog, _, _ = self.refresh([change])
        incorrect = [r for r in self.rows(before_catalog, SOURCE, 'forward') if r['raw'] == '제17조']
        self.assertEqual([r['target_law'] for r in incorrect], [SOURCE])
        catalog, _, _ = self.refresh([change], reviewed_corrections=[review])
        entry, body, detail = self.resulting_document(catalog, SOURCE)
        self.assertFalse([r for r in detail['1']['rows']
                          if r['raw'] == '제17조' and r['target_law'] == SOURCE])
        corrected = [r for r in detail['1']['external'] if r['cite_raw'] == '제17조']
        self.assertEqual(len(corrected), 1)
        self.assertEqual(corrected[0]['target_law'], review['after'][0]['target_name'])
        self.assertEqual(corrected[0]['target_provision_status'], 'not-collected')
        self.assertEqual(body['articles'][0]['text'], change['fresh_document']['articles'][0]['text'])
        self.assertEqual(body['articles'][0]['text'][corrected[0]['source_start']:corrected[0]['source_end']], '제17조')
        self.assertEqual(corrected[0]['source_effective'], entry['effective'])

    def test_review_from_other_article_hash_or_edition_is_rejected(self):
        for field, bad in (('source_sha256', '0'*64), ('effective', '20260101')):
            with self.subTest(field=field):
                change, review = self.reviewed_ownership_fixture()
                review[field] = bad
                with self.assertRaisesRegex(ValueError, '(?i)correction source changed|hash|edition'):
                    self.refresh([change], reviewed_corrections=[review])

    def test_packed_build_updates_national_reverse_and_preserves_fixed_sources_and_history(self):
        from scripts.build_edition_refresh_site import build
        rows = [self.change(text=f'「{NEW_TARGET}」 제1조를 따른다.'),
                self.change(LOCAL, text=f'「{CENTRAL}」 제2조를 따른다.',
                            domain='local_tax', region='region1')]
        sources = self.root/'approved-sources.json'
        sources.write_text(json.dumps(dict(base_data_version='fixed-public-version',
            base_manifest_sha256=digest(self.base_bytes['manifest.json']), as_of='20261026',
            rows=rows), ensure_ascii=False), encoding='utf-8')
        source_bytes = sources.read_bytes()
        destination = self.root/'published'
        report = build(self.base, sources, destination, validate_site=False)
        self.assertEqual(report['source_sha256'], digest(source_bytes))
        self.assertEqual(report['base_manifest_sha256'], digest(self.base_bytes['manifest.json']))
        self.assertEqual(sources.read_bytes(), source_bytes)
        self.assertEqual(snapshot(self.base), self.base_bytes)
        central = public_document(destination, CENTRAL, 'local_tax')[2]
        self.assertFalse([r for r in central['1']['rows'] if r.get('source_law') == LOCAL])
        new_rows = [r for r in central['2']['rows'] if r.get('source_law') == LOCAL]
        self.assertEqual(len(new_rows), 1)
        self.assertTrue(new_rows[0]['national'])
        self.assertEqual(new_rows[0]['region'], 'region1')
        self.assertEqual(new_rows[0]['source_effective'], '20261026')
        old_entry, old_body, _ = public_document(self.base, OLD_TARGET)
        new_body = public_document(destination, OLD_TARGET)[1]
        for key in ('articles', 'annexes', 'pdf_analysis', 'unstructured_text'):
            self.assertEqual(new_body[key], old_body[key], key)
        baseline = catalog_at(destination)['delegation_review']['baselines'][old_entry['id']]
        self.assertEqual(baseline['file'], self.fixture['history'])
        self.assertEqual(Storage(destination).raw(baseline['file']), Storage(self.base).raw(baseline['file']))
        self.assertTrue(json.loads((destination/'manifest.json').read_text())['data_packs'])

    def test_regional_title_only_change_updates_central_national_reverse_names(self):
        from scripts.build_edition_refresh_site import build
        new_name = '합성시 시세기본 조례'
        change = self.change(LOCAL, fresh_name=new_name, kind='title-metadata',
                             domain='local_tax', region='region1')
        sources = self.root/'title-sources.json'
        sources.write_text(json.dumps(dict(base_data_version='fixed-public-version',
            base_manifest_sha256=digest(self.base_bytes['manifest.json']), as_of='20261026',
            rows=[change]), ensure_ascii=False), encoding='utf-8')
        destination = self.root/'renamed-region'
        build(self.base, sources, destination, validate_site=False)
        old_row = public_document(self.base, CENTRAL, 'local_tax')[2]['1']['rows'][0]
        new_rows = public_document(destination, CENTRAL, 'local_tax')[2]['1']['rows']
        row = next(r for r in new_rows if r['source_id'] == old_row['source_id'])
        self.assertEqual(row['source_law'], new_name)
        self.assertEqual(row['neighbor_law'], new_name)
        self.assertEqual(row['raw'], old_row['raw'])
        self.assertEqual(row['evidence_id'], old_row['evidence_id'])


if __name__ == '__main__':
    unittest.main()
