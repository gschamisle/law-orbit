"""Isolated procurement corpus using shared citation and galaxy engines."""
from __future__ import annotations
from copy import deepcopy
import json
import hashlib
from pathlib import Path
from urllib.parse import quote
from core.fsc_collection import norm
from core.fsc_universe import article_for, external_evidence

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'output/procurement-universe/bundle.json'
SECTORS = {'national':'국가계약 · 재경부', 'procurement':'조달청 집행기준', 'local':'지방계약', 'all':'전체 연결'}


def documents(source):
    return source['laws'] + source.get('administrative_rules', [])


def build_graph(source, *, domain="procurement", coverage_note=None):
    from core.universe_builder import build_universe
    from core.fsc_administrative import adapter
    indexed = [d for d in documents(source) if d.get('articles')]
    if not indexed or any(d.get('category') != domain for d in indexed):
        raise ValueError(f'{domain} 전용 데이터가 아닙니다.')
    graph = build_universe({**source, 'laws':indexed}, focus_categories=(domain,),
                           preserve_external=True, article_adapter=adapter)
    graph.update(domain=domain, tax_laws=[], coverage_note=coverage_note or (
        '국가계약 법령·재경부 계약예규와 선정한 조달청·지방계약 자료의 명시적 인용망입니다. '
        '전체 공공기관 계약규정·조례를 수집한 것은 아닙니다. 미수집 대상은 본문·역인용 미점검입니다. '
        '장·절·항목 형식, 첨부파일 본문·별표·부칙은 미분석입니다. 인용 관계는 동시개정 의무를 뜻하지 않습니다.'))
    by_name = {d['name']:d for d in documents(source)}
    unindexed = {norm(n):d for n,d in by_name.items() if not d.get('articles')}
    for edge in graph['edges'] + graph['external_references']:
        edge['source_url'] = by_name[edge['source_law']]['source_url']
        dest = by_name.get(edge['target_law']) or unindexed.get(norm(edge['target_law']))
        if dest:
            edge['target_url'] = dest['source_url']
            if not dest.get('articles'): edge['target_status'] = 'collected-not-indexed'
        elif edge['target_law'].endswith(('규정','세칙','기준','지침','조건','요령','유의서','고시')):
            edge['target_url'] = 'https://www.law.go.kr/행정규칙/'+quote(edge['target_law'],safe='')
    graph['citation_issues'] = [dict(source_law=d['name'], source_jo=a['jo'], source_url=d['source_url'], **issue)
                               for d in indexed for a in d['articles'] for issue in a.get('citation_issues',[])]
    graph['coverage'] = dict(scope=source['inventory']['scope'], supplement='not-indexed', annex_body='not-indexed',
                             chapters_sections='not-indexed', external_reverse='not-collected', semantic_similarity='not-analyzed')
    return graph


def validate_bundle(bundle, *, domain="procurement"):
    source, graph = bundle['source'], bundle['graph']
    docs = documents(source)
    indexed = [d for d in docs if d.get('articles')]
    names = {d['name'] for d in indexed}
    if (source.get('domain') != domain or graph.get('domain') != domain or not names
        or len({d['uid'] for d in docs}) != len(docs) or len({norm(d['name']) for d in docs}) != len(docs)
        or set(graph['laws']) != names or set(graph['focus_laws']) != names
        or graph['built_at'] != source['built_at']
        or any(d.get('category') != domain or d['effective'] > source['built_at'] for d in docs)):
        raise ValueError(f'{domain} 수집 범위와 그래프가 일치하지 않습니다.')
    for d in indexed:
        if len({a['jo'] for a in d['articles']}) != len(d['articles']):
            raise ValueError('조문 번호가 중복되었습니다.')
    articles = {(d['name'],a['jo']):a for d in indexed for a in d['articles']}
    articles.update({(d['name'],a['ref']):{'text':a['title']} for d in indexed for a in d.get('annexes',[])})
    for e in graph['edges'] + graph.get('external_references',[]):
        article = articles.get((e['source_law'],e['source_jo']))
        if not article or article['text'][e['source_start']:e['source_end']] != e['cite_raw']:
            raise ValueError('인용 근거가 수집 원문과 일치하지 않습니다.')
    if any(e['source_law'] not in names or e['target_law'] not in names for e in graph['edges']):
        raise ValueError('기본 지도에 미수집 대상이 포함되었습니다.')
    if any(e['source_law'] not in names or e['target_law'] in names for e in graph.get('external_references',[])):
        raise ValueError('외부 인용 상태가 잘못되었습니다.')
    return bundle


def load_bundle(path=BUNDLE, *, domain="procurement"):
    return validate_bundle(json.loads(Path(path).read_text(encoding='utf-8')), domain=domain)


def sector_graph(graph, sector):
    if sector == 'all': return graph
    names = {d['name'] for d in graph['catalog'] if sector in d['sectors']}
    return {**graph, 'laws':sorted(names), 'focus_laws':sorted(names),
            'catalog':[d for d in graph['catalog'] if d['name'] in names],
            'edges':[e for e in graph['edges'] if e['source_law'] in names and e['target_law'] in names]}


def mark_sector(result, graph, sector):
    result = deepcopy(result)
    members = set(sector_graph(graph, sector)['laws'])
    for r in result['rows'] + result.get('broad_rows',[]):
        outside = r['source_law'] not in members or r['target_law'] not in members
        r.update(out_of_sector=outside, sector_relation='분야 밖 관련 조문' if outside else '선택 분야')
    return result


def present(data, graph, sector, *, domain="procurement", title="조달·계약 은하", sectors=SECTORS):
    from core.law_map import family
    data = deepcopy(data)
    data.update(domain=domain, galaxy_title=title + (' · '+sectors[sector] if sector!='all' else ''))
    catalog = {d['name']:d for d in graph['catalog']}
    palette = ('#80b4ff','#68dfc4','#bea2ff','#f0b77e','#ef96bb','#83d0ed',
               '#cedc80','#ffa58e','#91a1ff','#e1a6e8','#7de0e2','#f1ce84',
               '#a6d5a0','#acbfff','#e8a195','#8ed7ba')
    def color(name):
        identity = norm(family(name))
        return palette[int(hashlib.sha256(identity.encode()).hexdigest()[:8],16) % len(palette)]
    for n in data['nodes']:
        d = catalog.get(n['id'])
        if d:
            n.update(label=d['display_name'], full_name=d['name'], category=domain,
                     title=d['managing_authority']+' · '+d['kind']+' · 시행 '+d['effective'], color=color(d['name']))
        else:
            d = catalog.get(n.get('family'))
            if d: n.update(label=d['display_name'], full_name=d['name'])
            if any(e.get('out_of_sector') for e in n.get('evidence',[])):
                n['status'] = '분야 밖 관련 조문 · '+n.get('status','')
            # Article colors continue to mean forward/reverse/context, not sector.
    for point in data.get('dust',[]):
        if point.get('law_id') in catalog:
            point['c'] = color(point['law_id'])
            point['law'] = catalog[point['law_id']]['display_name']
    return data


def report(bundle, *, domain="procurement", sectors=SECTORS):
    source, graph = bundle['source'], bundle['graph']
    docs = documents(source)
    return dict(domain=domain, built_at=graph['built_at'], documents=len(docs),
                statutes=len(source['laws']), administrative_rules=len(source['administrative_rules']),
                indexed_documents=len(graph['laws']), articles=sum(len(d.get('articles',[])) for d in docs),
                edges=len(graph['edges']), external_references=len(graph['external_references']),
                unresolved=len(graph['citation_issues']),
                contract_rules=sum(d['kind']=='계약예규' for d in docs),
                not_indexed=[{'name':d['name'],'reason':d.get('analysis_error','연결 미분석')} for d in docs if not d.get('articles')],
                sectors={s:len(sector_graph(graph,s)['laws']) for s in sectors}, coverage=graph['coverage'])
