"""Selective paragraph refresh preserves original text and reader endpoints."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from core.ftc_text_citations import collect_text_citations, main_text
from scripts.edition_refresh_text import refresh_text_evidence, merge_rows, summarize_text_entries
from scripts.test_ftc import text_source, FAIR


class EditionTextTests(unittest.TestCase):
    def setup_source(self):
        source = text_source()
        rule = source['administrative_rules'][0]
        other = deepcopy(rule)
        other.update(name='기업결합 신고요령', uid='rule:2')
        other['raw_body_blocks'] = ['Ⅰ. 목적\n「' + FAIR + '」 제10조를 적용한다.']
        source['administrative_rules'].append(other)
        docs = source['laws'] + source['administrative_rules']
        return source, docs, {d['name']: 'reader-' + str(i) for i, d in enumerate(docs)}

    def test_selective_parser_never_reads_unchanged_source(self):
        source, docs, ids = self.setup_source()
        source['administrative_rules'][1].pop('uid')
        rows, _ = collect_text_citations(source, source_names={'기업결합 심사기준'})
        self.assertEqual(len(rows), 4)
        self.assertEqual({r['source_law'] for r in rows}, {'기업결합 심사기준'})

    def test_changed_paragraph_sources_have_real_offsets_and_reverse_rows(self):
        source, docs, ids = self.setup_source()
        original = deepcopy(docs)
        result = refresh_text_evidence(docs, {'기업결합 심사기준'}, 'ftc', ids)
        self.assertEqual(docs, original)
        self.assertEqual(set(result['documents']), {'기업결합 심사기준'})
        self.assertEqual(len(result['text_citations']), 4)
        self.assertEqual(len(result['reverse'][(FAIR, '9')]), 2)
        self.assertEqual(set(result['reverse']), {(FAIR, '9'), (FAIR, '10'), (FAIR, '11')})
        text = main_text(docs[1])
        for row in result['text_citations']:
            self.assertEqual(text[row['source_start']:row['source_end']], row['raw'])
            self.assertEqual(row['source_jo'], '')
        for row in result['reverse'][(FAIR, '9')]:
            self.assertEqual(row['neighbor_kind'], 'text')
            self.assertEqual(row['neighbor_jo'], '')
            self.assertEqual(row['neighbor_id'], ids['기업결합 심사기준'])
        self.assertEqual(len(result['overview_edges']), 4)
        self.assertTrue(any('999' in i['raw'] for i in result['documents']['기업결합 심사기준']['text_issues']))

    def test_source_uid_required_only_for_changed_paragraph(self):
        _, docs, ids = self.setup_source()
        docs[2].pop('uid')
        refresh_text_evidence(docs, {'기업결합 심사기준'}, 'ftc', ids)
        docs[1].pop('uid')
        with self.assertRaisesRegex(ValueError, 'stable'):
            refresh_text_evidence(docs, {'기업결합 심사기준'}, 'ftc', ids)

    def test_numbered_or_duplicate_number_source_is_not_paragraph_analyzed(self):
        _, docs, ids = self.setup_source()
        self.assertEqual(refresh_text_evidence(docs, {FAIR}, 'ftc', ids)['documents'], {})
        docs[1]['analysis_error'] = '공식 조문번호 중복 · 원문 확인 필요'
        self.assertEqual(refresh_text_evidence(docs, {docs[1]['name']}, 'ftc', ids)['documents'], {})

    def test_merge_retains_untouched_row_and_distinct_expanded_targets(self):
        _, docs, ids = self.setup_source()
        fresh = refresh_text_evidence(docs, {'기업결합 심사기준'}, 'ftc', ids)
        rows = fresh['forward']['기업결합 심사기준']
        original = dict(evidence_id='old', source_law='other', raw='공백  원문', source_start=17,
                        source_end=23, direction='reverse', target_law=FAIR, target_ref='제9조')
        before = deepcopy(original)
        result = merge_rows([original], rows + rows)
        self.assertEqual(original, before)
        self.assertIs(result[0], original)
        self.assertEqual(len(result), 5)
        bad = deepcopy(rows[0]); bad['raw'] += '변조'
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            merge_rows(rows, [bad])

    def test_summary_counts_preserved_and_refreshed_documents(self):
        entries = [dict(id='old', text_analysis={'status':'explicit-citations'}),
                   dict(id='new', text_analysis={'status':'explicit-citations'})]
        documents = {'old':dict(text_connections=[{},{}], text_issues=[{}]),
                     'new':dict(text_connections=[{}], text_issues=[])}
        self.assertEqual(summarize_text_entries(entries, documents), dict(documents=2,citations=3,issues=1))

    def test_catalog_refresh_replaces_text_edges_and_preserves_untouched_evidence(self):
        from core.ftc_collection import prepare_source
        from scripts.build_edition_refresh_site import refresh_catalog
        from scripts.build_static_galaxies import Writer, export_documents
        from scripts.static_storage import Storage
        law_name = '할부거래에 관한 법률'
        guide_name = '선불식 할부거래에서의 소비자보호 지침'
        preserved_name = '기업결합 심사기준'
        statute = dict(uid='eflaw:100', name=law_name, provider='eflaw', category='ftc',
                       managing_authority='공정거래위원회', effective='20260101', kind='법률',
                       source_url='https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=100',
                       articles=[dict(jo=str(i), title='합성 검증', text=f'제{i}조(합성 검증) 기준을 정한다.')
                                 for i in (1, 2, 3)])
        def guide(name, stable, target):
            return dict(uid=f'admrul:{stable}', document_id=str(stable), version_id=str(stable),
                        name=name, provider='admrul', category='ftc', kind='고시',
                        managing_authority='공정거래위원회', effective='20260101',
                        source_url=f'https://www.law.go.kr/LSW/admRulLsInfoP.do?admRulSeq={stable}',
                        raw_body_blocks=[f'Ⅰ. 합성 검증\n「{law_name}」(이하 ‘법’이라 한다) {target}를 적용한다.'],
                        articles=[])
        source = prepare_source(dict(domain='ftc', built_at='20260101', laws=[statute], administrative_rules=[
            guide(guide_name, 200, '제1조'), guide(preserved_name, 300, '제3조')]))
        rows, issues = collect_text_citations(source)
        graph = dict(domain='ftc', built_at='20260101', laws=[law_name], focus_laws=[law_name],
                     catalog=[], edges=[], text_citations=rows, text_citation_issues=issues)
        docs = source['laws'] + source['administrative_rules']
        output = Path(__file__).resolve().parents[1] / 'output'
        output.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=output) as tmp:
            base, stage = Path(tmp) / 'base', Path(tmp) / 'stage'
            base.mkdir(); stage.mkdir()
            writer = Writer(base)
            entries, ids = export_documents(writer, 'ftc', '', docs, graph)
            old_chart = dict(nodes=[dict(id=d['name'], full_name=d['name'], label=d['name'],
                                        category='ftc', family=d['name'], count=1) for d in docs],
                             all_links=[dict(a=n, b=law_name, n=1) for n in (guide_name,preserved_name)],
                             links=[dict(a=n, b=law_name, n=1) for n in (guide_name,preserved_name)], dust=[])
            catalog = dict(laws=entries, built_at='20260101', overview=writer.data(old_chart),
                           text_summary=dict(documents=2, citations=2, issues=0))
            old_storage = Storage(base)
            old_guide = next(e for e in entries if e['name'] == guide_name)
            old_preserved = old_storage.read(next(e for e in entries if e['name'] == preserved_name)['file'])
            old_law = old_storage.read(next(e for e in entries if e['name'] == law_name)['file'])
            prior_reverse = next(r for r in old_law['details']['3']['rows'] if r['source_law']==preserved_name)
            before = {p.relative_to(base).as_posix():p.read_bytes() for p in base.rglob('*') if p.is_file()}
            fresh = guide(guide_name, 200, '제2조 및 제3조')
            fresh.update(effective='20261102',version_id='201',source_url='https://www.law.go.kr/LSW/admRulLsInfoP.do?admRulSeq=201')
            replacement = dict(finding=dict(name=guide_name, effective=old_guide['effective'],url=old_guide['url']),
                               fresh_document=fresh, change_kind='edition',validation=dict(status='verified'))
            updated, _, _ = refresh_catalog(old_storage,catalog,'ftc',[replacement],Writer(stage),'2026-11-02')
            storage = Storage(stage)
            published = {e['name']:storage.read(e['file']) for e in updated['laws']}
            law, changed, preserved = [published[n] for n in (law_name,guide_name,preserved_name)]
            self.assertEqual(changed['articles'], [])
            self.assertEqual(len(changed['text_connections']), 2)
            self.assertEqual({r['target_ref'] for r in changed['text_connections']}, {'제2조','제3조'})
            self.assertEqual(law['details']['1']['rows'], [])
            self.assertEqual(len(law['details']['2']['rows']), 1)
            self.assertEqual(len(law['details']['3']['rows']), 2)
            self.assertEqual(next(r for r in law['details']['3']['rows'] if r['source_law']==preserved_name),prior_reverse)
            self.assertEqual(preserved['unstructured_text'],old_preserved['unstructured_text'])
            self.assertEqual(preserved['text_connections'],old_preserved['text_connections'])
            self.assertEqual(preserved['text_issues'],old_preserved['text_issues'])
            for row in changed['text_connections']:
                self.assertEqual(changed['unstructured_text'][row['source_start']:row['source_end']],row['raw'])
                self.assertEqual(row['source_id'],ids[guide_name])
                self.assertEqual(row['target_id'],ids[law_name])
            chart=storage.read(updated['overview'])
            self.assertEqual(next(n['count'] for n in chart['nodes'] if n['id']==guide_name),2)
            self.assertEqual(next(n['count'] for n in chart['nodes'] if n['id']==preserved_name),1)
            self.assertEqual(next(e['n'] for e in chart['all_links'] if e['a']==guide_name),2)
            self.assertEqual(updated['text_summary'],dict(documents=2,citations=3,issues=0))
            self.assertEqual({p.relative_to(base).as_posix():p.read_bytes() for p in base.rglob('*') if p.is_file()},before)


if __name__ == '__main__':
    unittest.main()
