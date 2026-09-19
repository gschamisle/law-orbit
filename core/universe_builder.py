"""Build evidence edges without expanding uncited external law-to-law networks."""
from __future__ import annotations
from collections import Counter
from datetime import date
import hashlib
import json
import re
from urllib.parse import quote

from core.citation_parser import parse_citations, effective_law_name, resolve_deictic_law
from core.citation_scope import Provision, parse_scope, scope_relation
from core.law_universe import GRAPH, SOURCES, norm

BRACKET = re.compile(r'「([^」]+)」')
ANNEX = re.compile(r'(별표|별지)\s*(?:제\s*)?(\d+)(?:\s*의\s*(\d+))?\s*(?:호\s*서식|호|서식)?')
STANDARDS = ('한국표준산업분류', '한국채택국제회계기준', '기업회계기준')
ENUM_TAIL = re.compile(r'\s*(?:부터|에서|내지|[~～∼]|및|또는|와|과|ㆍ|·|,)\s*'
                       r'(?:제\s*\d+\s*(?:조|항|호)(?:\s*의\s*\d+)?|[가-하]\s*목)'
                       r'(?:\s*제\s*\d+\s*(?:항|호)(?:\s*의\s*\d+)?)*(?:\s*[가-하]\s*목)?(?:\s*까지)?')
QUALIFIER = re.compile(r'제외|한정|한하|단서|외의\s*부분|불구|으로\s*본다|로\s*본다|으로\s*한다|로\s*한다|같은\s*(?:법|영|조|항|호)')


def public_url(name, reference=''):
    return 'https://www.law.go.kr/법령/' + quote(name, safe='') + ('/'+quote(reference,safe='') if reference else '')


def block_at(article, start):
    return next((b for b in article.get('blocks',[]) if b['start'] <= start < b['end']),
                {'ref': '제'+article['jo'].replace('의','조의')+('' if '의' in article['jo'] else '조'), 'text':article['text']})


def resolved_name(cite, text, citations, own_law):
    """A nearer quoted law without an article overrides an older numbered anchor."""
    name = effective_law_name(cite, own_law)
    same = re.match(r'같은\s*(법|영|령|규칙)', text[cite.span[0]:cite.span[1]])
    if same:
        anchors = [(m.start(), m[1]) for m in BRACKET.finditer(text, 0, cite.span[0])]
        anchors += [(c.span[0],c.law_name) for c in citations if c.span[0] < cite.span[0] and c.law_name and not c.relative]
        if not anchors:
            return ''
        name = max(anchors, key=lambda a:a[0])[1]
        if same[1] in ('영','령','규칙'):
            name = resolve_deictic_law('규칙' if same[1]=='규칙' else '영',name)
    return name


def build_universe(source, *, focus_categories=("tax",), preserve_external=False, article_adapter=None, source_names=None):
    """Preserve the tax default; other domains are explicit opt-ins."""
    if (not isinstance(focus_categories, (tuple, list)) or not focus_categories
            or any(not isinstance(c, str) or not c for c in focus_categories)):
        raise ValueError("focus_categories must be a nonempty list or tuple of category names")
    focus_categories = tuple(dict.fromkeys(focus_categories))
    corpus = source['laws']
    catalog = {norm(l['name']):l for l in corpus}
    metadata = [{k:v for k,v in l.items() if k not in ('articles','annexes','raw_body_blocks')} for l in corpus]
    edges, seen, outside = [], set(), Counter()
    external_references = []
    samples = {}
    def add(law, article, target_name, target_ref, raw, start, end, kind='article', relation='direct', **extra):
        dest = catalog.get(norm(target_name))
        if kind != 'standard' and not dest:
            if target_name and target_name != law['name'] and law['category'] in focus_categories:
                outside[target_name] += 1
                samples.setdefault(target_name, law['name']+' '+block_at(article,start)['ref']+' · '+raw)
            if not preserve_external or not target_name:
                return
        target_name = dest['name'] if dest else target_name
        if law['category'] not in focus_categories and (not dest or dest['category'] not in focus_categories):
            return
        # Ignore the article's own heading, retaining genuine intra-article text separately.
        if start == 0 and target_name == law['name'] and kind == 'article' and extra.get('source_granularity') != 'annex':
            return
        block = block_at(article,start)
        context = block['text']
        ident = (law['name'],article['jo'],start,end,target_name,target_ref,kind)
        if ident in seen:
            return
        seen.add(ident)
        edge = {'source_law':law['name'], 'source_jo':article['jo'], 'source_title':article['title'],
                'source_ref':block['ref'], 'source_granularity':'block',
                'source_start':start, 'source_end':end, 'source_effective':article.get('effective') or law['effective'],
                'target_law':target_name, 'target_ref':target_ref, 'target_kind':kind,
                'cite_raw':raw, 'type':relation, 'context_review':bool(QUALIFIER.search(context)),
                'context':context,
                'source_url':public_url(law['name'],Provision(article['jo']).label) if not article['jo'].startswith('별') else public_url(law['name']),
                'target_url':public_url(target_name,target_ref if kind == 'article' else '') if kind != 'standard' else '',
                'target_effective':dest['effective'] if dest else '', **extra}
        if kind == 'annex' and dest:
            matched = next((a for a in dest.get('annexes',[]) if norm(a['ref']) == norm(target_ref)),None)
            edge['target_title'] = matched['title'] if matched else ''
            edge['annex_urls'] = matched.get('urls',[]) if matched else []
        edge['evidence_id'] = hashlib.sha256(repr(ident).encode('utf-8')).hexdigest()[:20]
        if preserve_external and not dest:
            edge.update(target_status='not-collected', target_analysis='not-indexed', external_reverse='not-collected')
            external_references.append(edge)
        else:
            edges.append(edge)

    for law in corpus:
        if source_names is not None and law['name'] not in source_names:
            continue
        for article in law['articles']:
            text = article['text']
            if article_adapter is not None and law.get('provider') in ('admrul', 'ordin'):
                for citation in article_adapter(law, article, corpus):
                    add(law, article, **citation)
                continue
            citations = parse_citations(text)
            expanded_spans = []
            for cite in citations:
                if not cite.jo:
                    continue
                if any(a <= cite.span[0] and cite.span[1] <= b for a,b in expanded_spans):
                    continue
                target_name = resolved_name(cite,text,citations,law['name'])
                # Scope parser retains ranges and item branches; enumerate only real target articles.
                start, end = cite.span
                # Legacy tokens stop at '제1호'; keep item branches and their mok.
                tail = re.match(r'\s*의\s*\d+(?:\s*[가-하]\s*목)?',text[end:]) if cite.ho else None
                if tail:
                    end += tail.end()
                while tail := ENUM_TAIL.match(text,end):
                    end = tail.end()
                if end > cite.span[1]:
                    expanded_spans.append((start,end))
                raw = text[start:end]
                dest = catalog.get(norm(target_name))
                parsed = parse_scope(raw)
                article_ranges = [s for s in parsed.scopes if s.axis == 0]
                if article_ranges and dest:
                    refs = [Provision(a['jo']).label for a in dest['articles']
                            if any(scope_relation(s, Provision(a['jo'])) for s in article_ranges)]
                    refs += [s.start.label for s in parsed.scopes if s.axis != 0 and s.start.jo]
                else:
                    refs = [s.start.label for s in parsed.scopes if s.start.jo] or [
                        Provision(cite.jo + ('의'+cite.jo_sub if cite.jo_sub else ''), cite.hang, cite.ho, cite.mok).label]
                for reference in refs:
                    add(law,article,target_name,reference,raw,start,end,
                        relation='junyo' if cite.is_junyo or re.match(r'\s*(?:을|를)?\s*준용',text[end:]) else 'direct', via_range=bool(article_ranges))
            brackets = list(BRACKET.finditer(text))
            for m in brackets:
                name = m[1]
                if norm(name) not in catalog and not preserve_external:
                    if law['category'] in focus_categories and name.endswith(('법','법률','시행령','시행규칙','규칙')):
                        outside[name] += 1
                        samples.setdefault(name, law['name']+' '+block_at(article,m.start())['ref']+' · '+m[0])
                    continue
                tail = text[m.end():m.end()+100]
                if re.match(r'\s*제\s*\d+\s*조', tail) or re.match(r'\s*(?:별표|별지)',tail):
                    continue
                if any(c.span[0] <= m.start() < c.span[1] for c in citations if c.jo):
                    continue
                # Law-level wording does not prove a link to any particular article.
                raw = m[0]
                add(law,article,name,'법령·정의 참조',raw,m.start(),m.end(),kind='law',relation='law_reference')
            for m in ANNEX.finditer(text):
                start = max(text.rfind('\n',0,m.start()),text.rfind('。',0,m.start()))+1
                before = text[start:m.start()]
                matches = list(BRACKET.finditer(before))
                # A remote law mention in the same paragraph is not an annex owner.
                direct = matches[-1] if matches and not before[matches[-1].end():].strip() else None
                name = direct[1] if direct else law['name']
                prefix = re.search(r'(같은\s*법|같은\s*영|같은\s*규칙|법|영|규칙)\s*$',before)
                if prefix:
                    token = ''.join(prefix[1].split())
                    if token.startswith('같은'):
                        prior = [b for b in brackets if b.end() <= m.start()]
                        if not prior:
                            continue  # An unresolved 'same law' must not be assigned to this law.
                        name = prior[-1][1]
                        if token in ('같은영','같은규칙'):
                            name = resolve_deictic_law('영' if token == '같은영' else '규칙',name)
                    else:
                        name = resolve_deictic_law(token,law['name'])
                no = str(int(m[2])) + ('의'+str(int(m[3])) if m[3] else '')
                label = '별표 '+no if m[1]=='별표' else '별지 제'+no+'호서식'
                add(law,article,name,label,m[0],m.start(),m.end(),kind='annex',relation='annex_reference')
            if law['category'] in focus_categories:
                for standard in STANDARDS:
                    for m in re.finditer(re.escape(standard),text):
                        add(law,article,standard,'기준 참조',m[0],m.start(),m.end(),kind='standard',relation='standard_reference')
                # A named tax in the statutory import VAT base is a calculation dependency.
                # Restrict this explicit mapping to the verified provision, not arbitrary tax words.
                if law['name'] == '부가가치세법' and article['jo'] == '29':
                    tax_names = {'관세':'관세법', '개별소비세':'개별소비세법', '주세':'주세법',
                                 '교육세':'교육세법', '농어촌특별세':'농어촌특별세법',
                                 '교통ㆍ에너지ㆍ환경세':'교통ㆍ에너지ㆍ환경세법'}
                    for b in article.get('blocks',[]):
                        if b['ref'] != '제29조제2항':
                            continue
                        for tax, target_law in tax_names.items():
                            for m in re.finditer(re.escape(tax), b['text']):
                                add(law,article,target_law,'과세표준 산식 참조',m[0],b['start']+m.start(),b['start']+m.end(),
                                    kind='law',relation='calculation_reference')
        # The annex's own title identifies its related article; do not read image/table cells as parsed text.
        if law['category'] in focus_categories:
            for annex in law.get('annexes',[]):
                synthetic = {'jo':annex['ref'],'title':annex['title'],'text':annex['title'], 'effective':annex['effective']}
                for cite in parse_citations(annex['title']):
                    if cite.jo:
                        name = effective_law_name(cite,law['name'])
                        add(law,synthetic,name,f'제{cite.jo}조'+('의'+cite.jo_sub if cite.jo_sub else ''),
                            cite.raw,*cite.span,relation='byeolpyo',source_ref=annex['ref'],source_granularity='annex')
    edges.sort(key=lambda e:(e['source_law'],e['source_jo'],e['source_start'],e['target_law'],e['target_ref']))
    result = {'schema_version':2,'built_at':source['built_at'],'provider':source.get('provider',''),
            'laws':sorted(l['name'] for l in corpus), 'catalog':metadata, 'edges':edges,
            'tax_laws':sorted(l['name'] for l in corpus if l['category']=='tax'),
            'relation_counts':dict(Counter(e['target_kind'] for e in edges)),
            'outside_scope':[{'law':n,'mentions':c,'example':samples.get(n,'')} for n,c in outside.most_common()],
            'coverage_note':'수집한 세법령 내부 및 세법령↔선정 외부 법령의 연결입니다. 법령·정의 참조는 특정 조문 연결을 확정하지 않습니다. 별표 파일 본문·부칙·고시 및 회계기준 전문은 전수 해석하지 않았습니다.'}
    if preserve_external:
        result['external_references'] = sorted(external_references, key=lambda e:(e['source_law'], e['source_jo'], e['source_start']))
    if focus_categories != ("tax",):
        result["focus_categories"] = list(focus_categories)
        result["focus_laws"] = sorted(l["name"] for l in corpus if l["category"] in focus_categories)
        result["coverage_note"] = "수록한 선택 도메인 내부와 수록 외부 법령의 직접 연결입니다. 미수록 법령·부칙·별표 파일 본문·행정규칙은 별도 점검이 필요합니다."
    return result


def main():
    data = build_universe(json.loads(SOURCES.read_text(encoding='utf-8')))
    temp = GRAPH.with_suffix('.json.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    temp.replace(GRAPH)
    print(json.dumps({'laws':len(data['laws']),'tax_laws':len(data['tax_laws']),'edges':len(data['edges']),
                      'relations':data['relation_counts']},ensure_ascii=False))


if __name__ == '__main__':
    main()
