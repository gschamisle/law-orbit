"""Evidence-only bridge between independently versioned forex and finance data.

Inputs are public viewer snapshots, so the bridge uses exactly the editions a
reader can open. It never modifies a domain corpus or adds thematic guesses.
"""
from collections import defaultdict
from copy import deepcopy
import hashlib
import re

from core.citation_scope import Provision, parse_target
from core.fsc_administrative import adapter, aliases_from, provision_blocks
from core.universe_builder import block_at, QUALIFIER

PAIR = ('forex', 'fsc')
PAIRS = (PAIR, ('procurement', 'public_institutions'))
BRIDGE_KINDS = {PAIR: 'forex-finance-bridge', PAIRS[1]: 'procurement-public-bridge'}
PAIR_LABELS = {PAIR: '외환·금융', PAIRS[1]: '조달계약·공공기관'}


def norm(value):
    return re.sub(r'\s+', '', value or '').replace('ㆍ', '·')


def document(entry, packed):
    if (entry['id'], entry['domain'], entry['effective'], entry['name']) != tuple(
            packed['meta'][k] for k in ('id', 'domain', 'effective', 'name')):
        raise ValueError('Bridge document edition mismatch')
    articles = deepcopy(packed['articles'])
    for a in articles:
        a['blocks'] = provision_blocks(a['text'], a['jo'])
    aliases, evidence = aliases_from('\n'.join(a['text'] for a in articles))
    return dict(name=entry['name'], category=entry['domain'], effective=entry['effective'],
                source_url=entry['url'], articles=articles, aliases=aliases,
                alias_evidence=evidence, short_name=entry['label'])


def make_edge(doc, article, citation):
    c = dict(citation)
    start, end = c.pop('start'), c.pop('end')
    raw = c.pop('raw')
    if article['text'][start:end] != raw:
        raise ValueError('Bridge citation does not match the source text')
    name, ref = c.pop('target_name'), c.pop('target_ref')
    kind = c.pop('kind', 'article')
    block = block_at(article, start)
    identity = (doc['name'], article['jo'], start, end, name, ref, kind)
    return dict(source_law=doc['name'], source_jo=article['jo'], source_title=article['title'],
                source_ref=block['ref'], source_granularity='block', source_start=start, source_end=end,
                source_effective=article.get('effective') or doc['effective'], source_url=doc['source_url'],
                target_law=name, target_ref=ref, target_kind=kind, cite_raw=raw,
                type=c.pop('relation', 'direct'), context=block['text'],
                evidence_id=hashlib.sha256(repr(identity).encode()).hexdigest()[:20], **c)


def bridge(snapshots, *, pair=PAIR):
    """Each snapshot has entries, documents, details keyed by public document id."""
    if pair not in PAIRS or set(snapshots) != set(pair):
        raise ValueError('Only an explicitly supported domain pair may participate in this bridge')
    docs, entries, by_name = {}, {}, {}
    for domain, snap in snapshots.items():
        entries[domain] = {e['id']: e for e in snap['entries']}
        by_name[domain] = {}
        for entry in snap['entries']:
            key = norm(entry['name'])
            if key in by_name[domain]:
                raise ValueError('Ambiguous bridge document name')
            by_name[domain][key] = entry
            docs[entry['id']] = document(entry, snap['documents'][entry['id']])
    links, rejected, recovered, annex_count = [], [], [], 0
    suppressed = {d: defaultdict(lambda: defaultdict(set)) for d in pair}
    resolved_issues = {d: defaultdict(lambda: defaultdict(set)) for d in pair}
    seen = set()

    def add(domain, entry, article, edge, origin=None):
        peer = pair[1] if domain == pair[0] else pair[0]
        name = norm(edge.get('target_law', ''))
        # A shared document already available in this domain stays in that domain.
        if name in by_name[domain] or name not in by_name[peer]:
            return False
        target = by_name[peer][name]
        start, end = edge['source_start'], edge['source_end']
        if article['text'][start:end] != edge['cite_raw']:
            raise ValueError('Stored bridge evidence and public source edition differ')
        kind = edge.get('target_kind', 'article')
        target_article = None
        if kind == 'article':
            try:
                jo = parse_target(edge['target_ref'], allow_hyphen=True).jo
            except ValueError:
                return False
            target_article = next((a for a in docs[target['id']]['articles'] if a['jo'] == jo), None)
            if not target_article:
                rejected.append(dict(source=entry['name'], target=target['name'], ref=edge['target_ref'],
                                     reason='대상 조문이 수집 판본에 없음'))
                return False
        elif kind not in ('law', 'annex'):
            return False
        identity = (entry['id'], article['jo'], start, end, target['id'], edge['target_ref'], kind)
        if identity not in seen:
            seen.add(identity)
            e = deepcopy(edge)
            e.update(source_law=entry['name'], target_law=target['name'], source_domain=domain,
                     target_domain=peer, source_url=entry['url'], target_url=target['url'],
                     source_effective=article.get('effective') or entry['effective'],
                     target_effective=(target_article or {}).get('effective') or target['effective'],
                     type='law_reference' if kind == 'law' else edge.get('type', 'direct'),
                     target_status='collected-cross-domain', external_reverse='collected-pair-only',
                     target_analysis='not-indexed' if kind == 'annex' or not target['articles'] else 'indexed',
                     target_provision_status='annex-not-indexed' if kind == 'annex' else
                         'deleted' if (target_article or {}).get('deleted') else 'collected',
                     context_review=bool(edge.get('context_review') or QUALIFIER.search(edge.get('context', ''))
                                         or (target_article or {}).get('deleted')))
            links.append(e)
        if origin:
            suppressed[domain][entry['id']][article['jo']].add(origin['evidence_id'])
        return True

    for domain, snap in snapshots.items():
        peer = pair[1] if domain == pair[0] else pair[0]
        corpus = [docs[e['id']] for e in snap['entries']]
        corpus += [docs[e['id']] for n, e in by_name[peer].items() if n not in by_name[domain]]
        # Match complete official names, never fuzzy names or short generic aliases.
        titles = sorted((e['name'] for n, e in by_name[peer].items() if n not in by_name[domain]), key=len, reverse=True)
        title_pattern = '|'.join(r'\s*'.join(map(re.escape, norm(n))) for n in titles)
        annex_re = re.compile(r'(?<![가-힣A-Za-z])(?:「)?(?P<name>'+title_pattern+
            r')(?:」)?\s*[<〈\[]?\s*별표\s*(?P<no>\d+(?:\s*-\s*\d+)*)(?:\s*의\s*(?P<sub>\d+))?(?:호)?\s*[>〉\]]?') if titles else None
        for entry in snap['entries']:
            doc = docs[entry['id']]
            for article in doc['articles']:
                detail = snap['details'][entry['id']][article['jo']]
                annex_spans = []
                for m in annex_re.finditer(article['text']) if annex_re else []:
                    ref = '별표 '+norm(m['no'])+('의'+m['sub'] if m['sub'] else '')
                    e = make_edge(doc, article, dict(target_name=m['name'], target_ref=ref,
                        start=m.start(), end=m.end(), raw=m[0], kind='annex', relation='annex'))
                    if add(domain, entry, article, e):
                        annex_spans.append((m.start(), m.end())); annex_count += 1
                for e in detail.get('external', []):
                    if any(a <= e['source_start'] < b for a, b in annex_spans):
                        suppressed[domain][entry['id']][article['jo']].add(e['evidence_id'])
                    else:
                        add(domain, entry, article, e, e)
                issues = [i for i in detail.get('issues', []) if '별칭' in i.get('reason', '')]
                if not issues:
                    continue
                # Reuse the administrative parser with the peer title registry.
                # Only previously unresolved exact spans may be added here.
                parsed_article = deepcopy(article); parsed_article['citation_issues'] = []
                for c in adapter(doc, parsed_article, corpus):
                    matches = [i for i in issues if i.get('raw') == c['raw']]
                    if not matches or norm(c['target_name']) not in norm(c['raw']):
                        continue
                    e = make_edge(doc, article, c)
                    if add(domain, entry, article, e):
                        resolved_issues[domain][entry['id']][article['jo']].add(c['raw'])
                        recovered.append(dict(source=entry['name'], jo=article['jo'], raw=c['raw'], target_ref=c['target_ref']))
    # Both domains use the same evidence edges, evaluated by the existing engine.
    graph = dict(domain=pair[0], built_at=' / '.join(snapshots[d]['built_at'] for d in pair),
                 laws=sorted({d['name'] for d in docs.values()}), edges=links, catalog=[],
                 coverage_note=PAIR_LABELS[pair]+' 수집 판본 사이의 명시적 인용만 대조합니다. 별표 본문·의미상 관계는 미분석입니다.')
    return dict(pair=pair, graph=graph, documents=list(docs.values()), entries=entries,
                suppressed=suppressed, resolved_issues=resolved_issues,
                report=dict(edges=len(links), articles=sum(e['target_kind']=='article' for e in links),
                            law_references=sum(e['target_kind']=='law' for e in links), annexes=annex_count,
                            recovered=recovered, rejected=rejected))
