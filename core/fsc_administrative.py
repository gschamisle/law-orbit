"""Administrative provision adapter, opt-in to the common evidence builder.

No substitute statute IDs: 1-2 and 1의2 remain distinct. Alias resolution uses
definitions in the collected body; unresolved owners stay in a review ledger.
"""
from __future__ import annotations
from copy import deepcopy
from html import unescape
import re
from core.citation_scope import Provision, parse_scope, scope_relation, parse_target
from core.fsc_collection import norm, CollectionError

NUMBER = r'\d+(?:\s*-\s*\d+)*'
JO = rf'제\s*({NUMBER})\s*조(?:\s*의\s*(\d+)(?!\d|일|년|월|명|개|원|배|%))?'
HEAD = re.compile(rf'(?m)^[ \t]*{JO}[ \t]*(?:\(([^\n]*?)\)|(?=<?\s*삭\s*제))')
ATOM = rf'(?:제\s*{NUMBER}\s*조(?:\s*의\s*\d+)?|제\s*\d+\s*(?:항|호)(?:\s*의\s*\d+)?|[가-하]\s*목)'
START = re.compile(JO)
SUB = r'(?:\s*제\s*\d+\s*(?:항|호)(?:\s*의\s*\d+)?)*(?:\s*[가-하]\s*목)?'
TAIL = re.compile(rf'\s*(?:부터|에서|내지|[~～∼]|및|또는|와|과|ㆍ|·|,)\s*{ATOM}{SUB}(?:\s*까지)?')
QUOTED = re.compile(r'「([^」]+)」')
DECL = re.compile(r'\s*\(이하\s*["“]([^"”]+)["”]\s*(?:이?라\s*한다|라\s*함)\)')
SAME_DERIVATIVE = re.compile(r'같은\s*법\s*(시행령|시행규칙)')
BOUNDARY = re.compile(r'(?m)^[ \t]*(?:부\s*칙|\[\s*별표\s*\d|\[\s*별지\s*제?\d)')

def body_text(blocks: list[str]) -> str:
    text = '\n'.join(blocks).replace('\r\n','\n').replace('\r','\n')
    if re.search(r'<(?:p|br|div|span|table)\b', text, re.I):
        text = re.sub(r'</?(?:p|br|div|tr|li)\b[^>]*>', '\n', text, flags=re.I)
        text = re.sub(r'</?(?:span|table|td|tbody|b|strong|a|font)\b[^>]*>', '', text, flags=re.I)
        text = unescape(text)
    return text.strip()

def aliases_from(text: str) -> tuple[dict, list]:
    definitions = []
    quotes = list(QUOTED.finditer(text))
    for m in quotes:
        declaration = DECL.match(text, m.end())
        if declaration:
            definitions.append((declaration[1], m[1], m.start(), declaration.end()))
    for m in SAME_DERIVATIVE.finditer(text):
        declaration = DECL.match(text, m.end())
        prior = [q for q in quotes if q.end() <= m.start()]
        if declaration and prior and m.start()-prior[-1].end() < 160:
            base = re.sub(r'\s*시행(?:령|규칙)$','',prior[-1][1])
            definitions.append((declaration[1],base+' '+m[1],prior[-1].start(),declaration.end()))
    aliases, evidence, conflicts = {}, [], set()
    for alias, name, start, end in definitions:
        alias = norm(alias)
        if alias in aliases and norm(aliases[alias]) != norm(name):
            conflicts.add(alias)
        aliases[alias] = name
        evidence.append(dict(alias=alias, target_law=name, raw=text[start:end], start=start, end=end))
    for alias in conflicts:
        aliases.pop(alias, None)
    return aliases, evidence

def provision_blocks(text: str, jo: str) -> list[dict]:
    # Paragraph marks and line-anchored items only; a citation inside a sentence
    # must never be mistaken for a new source paragraph.
    marks = list(re.finditer(r'(?m)([①-⑳㉑-㉟])|^[ \t　]*(\d+(?:의\d+)?)\.\s+|^[ \t　]*([가-하])\.\s+', text))
    parts, last, hang, ho = [], 0, '', ''
    current = Provision(jo).label
    for m in marks:
        if m.start() > last:
            parts.append(dict(start=last,end=m.start(),text=text[last:m.start()],ref=current))
        if m[1]:
            char = ord(m[1]); hang = str(char-ord('①')+1 if char<=ord('⑳') else char-ord('㉑')+21)
            ho = ''; current = Provision(jo,hang).label
        elif m[2]:
            ho = m[2]; current = Provision(jo,hang,ho).label
        elif ho:
            current = Provision(jo,hang,ho,m[3]).label
        last = m.start()
    if last < len(text):
        parts.append(dict(start=last,end=len(text),text=text[last:],ref=current))
    return parts

def index_rule(rule: dict) -> dict:
    result = deepcopy(rule)
    text = body_text(rule.get('raw_body_blocks', []))
    cut = BOUNDARY.search(text)
    main = text[:cut.start()] if cut else text
    headings = list(HEAD.finditer(main))
    articles, seen = [], set()
    for i, h in enumerate(headings):
        jo = '-'.join(str(int(x.strip())) for x in h[1].split('-')) + ('의'+str(int(h[2])) if h[2] else '')
        if jo in seen:
            raise CollectionError('administrative-duplicate-article:'+rule['name'])
        seen.add(jo)
        end = headings[i+1].start() if i+1 < len(headings) else len(main)
        raw = main[h.start():end].strip()
        # Chapter headings belong to the document structure, not the preceding article.
        section = re.search(r'(?m)^\s*제\s*\d+\s*(?:편|장|절|관)\s',raw)
        if section: raw = raw[:section.start()].rstrip()
        articles.append(dict(jo=jo,title=(h[3] or '삭제').strip(),text=raw,deleted=not bool(h[3]),
                             effective=rule['effective'],blocks=provision_blocks(raw,jo),
                             body_start=h.start(), heading_raw=h[0].strip()))
    aliases, evidence = aliases_from(main)
    result.update(articles=articles, annexes=[], aliases=aliases, alias_evidence=evidence,
                  body_status='indexed-administrative-text' if articles else 'collected-not-indexed',
                  coverage=dict(provisions='parsed' if articles else 'no-supported-article-headings',
                                supplement='not-indexed',annex_body='not-indexed',
                                relative_aliases='explicit-definitions-only'))
    return result

def prepare_source(source: dict) -> dict:
    from core.fsc_sectors import tag_source
    result = tag_source(source)
    rules=[]
    for r in result.get('administrative_rules', []):
        try: rules.append(index_rule(r))
        except CollectionError as error:
            if not str(error).startswith('administrative-duplicate-article:'): raise
            # A genuine duplicate number in the official source is not repairable
            # by guessing. Exclude the document from indexed coverage explicitly.
            rules.append({**r,'articles':[],'body_status':'collected-not-indexed',
                          'analysis_error':'공식 원문의 조문번호 중복 · 원문 확인 필요',
                          'coverage':dict(provisions='blocked-duplicate-number',supplement='not-indexed',annex_body='not-indexed')})
    result['administrative_rules'] = rules
    return result

def adapter(law: dict, article: dict, corpus: list[dict]) -> list[dict]:
    text = article['text']
    aliases = {norm(k):v for k,v in law.get('aliases',{}).items()}
    # Explicit article-local definitions take precedence, without leaking to other articles.
    local, _ = aliases_from(text)
    aliases.update(local)
    if aliases.get('법'):
        aliases.setdefault('법시행령',aliases['법']+' 시행령')
        aliases.setdefault('법시행규칙',aliases['법']+' 시행규칙')
    aliases.update({'이세칙':law['name'],'본세칙':law['name']} if law['name'].endswith('세칙')
                   else {'이규정':law['name'],'본규정':law['name'],'이규칙':law['name']})
    if law.get('provider') == 'ordin':
        aliases.update({'이조례':law['name'],'본조례':law['name']} if law.get('kind') == '조례'
                       else {'이규칙':law['name'],'본규칙':law['name']})
    names = {norm(d['name']):d for d in corpus}
    declared = {}
    for d in corpus:
        for label in d.get('citation_names', []):
            declared.setdefault(norm(label), []).append(d)
    for label, candidates in declared.items():
        if len({d['name'] for d in candidates}) == 1:
            names.setdefault(label, candidates[0])
            aliases.setdefault(label, candidates[0]['name'])
    if law.get('category') in ('procurement','housing','environment'):
        aliases.update({n:law['name'] for n in ('이예규','본예규','이기준','이조건','본조건','이요령','이지침','본지침')})
    for d in corpus:
        aliases.setdefault(norm(d['name']),d['name'])
        if d.get('short_name'): aliases.setdefault(norm(d['short_name']),d['name'])
    # Prefix names are matched only at a word boundary; 감독규정 must not match 규정.
    alternatives = sorted(aliases,key=len,reverse=True)
    prefix = re.compile(r'(?<![가-힣A-Za-z])('+'|'.join(r'\s*'.join(map(re.escape,a)) for a in alternatives)+r')\s*$')
    outputs, occupied, previous_owner, previous_end = [], [], '', 0
    issues = article.setdefault('citation_issues', [])
    for match in START.finditer(text):
        if any(a<=match.start()<b for a,b in occupied): continue
        # A heading identifies the source and is never an outgoing citation.
        if not text[:match.start()].strip(): continue
        end = match.end()
        child = re.match(SUB,text[end:]); end += child.end()
        while tail := TAIL.match(text,end): end = tail.end()
        before = text[:match.start()]
        quote = re.search(r'「([^」]+)」(?:\s*\(이하\s*["“][^"”]+["”]\s*이?라\s*(?:한다|함)\))?\s*$',before)
        named = prefix.search(before)
        same = re.search(r'같은\s*(법|영|시행령|규칙|시행규칙|규정|세칙|조례)\s*$',before)
        review = False
        if quote:
            owner, start = quote[1], quote.start()
        elif same:
            owner, start, review = previous_owner, same.start(), True
            if same[1] in ('영','시행령','규칙','시행규칙') and owner:
                owner = re.sub(r'\s*시행(?:령|규칙)$','',owner) + (' 시행령' if same[1] in ('영','시행령') else ' 시행규칙')
        elif named:
            owner, start = aliases[norm(named[1])], named.start()
        elif previous_owner and re.fullmatch(r'\s*(?:및|,|ㆍ|·)\s*동조\s*준용규정\s*[,ㆍ·]\s*',text[previous_end:match.start()]):
            owner, start, review = previous_owner,match.start(),True
        else:
            unknown = re.search(r'([가-힣]+(?:법|규정|세칙|규칙|조례)|법|영|규정|세칙|규칙|시행령|조례)\s*$',before)
            if unknown:
                owner, start = '', unknown.start()
            else:
                owner, start = law['name'],match.start()
        if law.get('category') in ('procurement','housing','environment') and owner:
            owner = aliases.get(norm(owner), owner)
            if norm(owner) in names: owner = names[norm(owner)]['name']
        raw = text[start:end]
        occupied.append((start,end))
        if not owner:
            issues.append(dict(raw=raw,start=start,end=end,reason='인용 법령·규정의 별칭 또는 상대 참조 미해결'))
            continue
        if quote or named or same: previous_owner = owner
        previous_end = end
        parsed = parse_scope(text[match.start():end], allow_hyphen=True)
        dest = names.get(norm(owner))
        ranges = [s for s in parsed.scopes if s.axis == 0]
        refs = [s.start.label for s in parsed.scopes if s.start.jo and s.axis != 0]
        if ranges:
            if dest:
                refs += [Provision(a['jo']).label for a in dest['articles']
                         if any(scope_relation(s,Provision(a['jo']),allow_hyphen=True) for s in ranges)]
            else: refs += [s.start.label for s in ranges]
        for ref in dict.fromkeys(refs):
            try: target = parse_target(ref, allow_hyphen=True)
            except ValueError:
                issues.append(dict(raw=raw,start=start,end=end,reason='인용 대상의 항·호 계층 생략 · 조문 위치 확인 필요'))
                continue
            target_article = next((a for a in dest['articles'] if a['jo']==target.jo),None) if dest else None
            missing = bool(dest and not target_article)
            deleted = bool(target_article and target_article.get('deleted'))
            outputs.append(dict(target_name=owner,target_ref=ref,raw=raw,start=start,end=end,
                                relation='junyo' if re.match(r'\s*(?:을|를)?\s*준용',text[end:]) else 'direct',
                                via_range=bool(ranges),target_provision_status='missing-from-collected-body' if missing else 'deleted' if deleted else 'collected' if dest else 'not-collected',
                                context_review=bool(missing or deleted or review or parsed.review_reason or
                                      re.search(r'제외|한정|단서|불구',text[max(0,start-30):end+30])),
                                alias_basis=[e for e in law.get('alias_evidence',[]) if norm(e['alias']) in norm(raw)]))
            if missing:
                issues.append(dict(raw=raw,start=start,end=end,reason=f'수집 판본에 대상 조문 없음 · {owner} {ref} 원문 확인 필요'))
    # Keep document-level quoted references separate from definite article links.
    for q in QUOTED.finditer(text):
        if any(a<=q.start()<b for a,b in occupied): continue
        outputs.append(dict(target_name=(names.get(norm(q[1]),{}).get('name',q[1]) if law.get('category') in ('procurement','housing','environment') else q[1]),target_ref='법령·정의 참조',raw=q[0],start=q.start(),end=q.end(),
                            kind='law',relation='law_reference'))
    # Relative wording is reported explicitly, rather than guessed across sentences.
    for m in re.finditer(r'같은\s*(?:조|항|호)(?:\s*제\s*\d+\s*(?:항|호))?',text):
        issues.append(dict(raw=m[0],start=m.start(),end=m.end(),reason='상대 조문 참조 · 문맥 검토 필요'))
    return outputs
