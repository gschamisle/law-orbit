"""Independent manual-fixture comparison. Reads a saved site; no network or production citation parser."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.static_storage import Storage

MOK = '가나다라마바사아자차카타파하거너더러머버서어저처커터퍼허'
TOKEN = re.compile(r'제\s*(\d+)\s*(조|항|호)(?:\s*의\s*(\d+))?|(['+MOK+r'])\s*목')
LEVEL = {'조': 0, '항': 1, '호': 2}
RANGE = re.compile(r'~|부터|내지|에서')

def authored_scopes(label):
    """Decode only the already human-authored expected ref labels, independently."""
    found = list(TOKEN.finditer(label or ''))
    if not found:
        raise ValueError('Expected numbered reference has no number: '+str(label))
    cur = ['', '', '', '']; prev_level = -1; prev_end = 0; pending = None; scopes = []
    def emit():
        if cur[0]:
            scopes.append((pending[0] if pending else tuple(cur), tuple(cur), pending[1] if pending else None))
    for token in found:
        level = 3 if token.group(4) else LEVEL[token.group(2)]
        val = token.group(4) or token.group(1) + ('의'+token.group(3) if token.group(3) else '')
        if level <= prev_level:
            gap = label[prev_end:token.start()]
            if RANGE.search(gap):
                if pending:
                    raise ValueError('Nested manual range: '+label)
                pending = (tuple(cur), level)
            else:
                emit(); pending = None
        cur[level] = val
        for n in range(level+1, 4):
            cur[n] = ''
        prev_level = level; prev_end = token.end()
    emit()
    return scopes

def ordinal(value):
    if value in MOK and len(value)==1:
        return (MOK.index(value),)
    return tuple(int(v) for v in value.split('의') if v) if value else ()

def contains(outer, inner):
    a,b,level = outer; x,y,inner_level = inner
    if level is None:
        return inner_level is None and tuple(a)==tuple(x)
    if inner_level is not None and inner_level != level:
        return False
    if tuple(a[:level]) != tuple(x[:level]) or tuple(a[:level]) != tuple(y[:level]):
        return False
    if not x[level] or not y[level]:
        return False
    # Lower-level detail must not be silently broadened or discarded.
    if tuple(a[level+1:]) != tuple(x[level+1:]) or tuple(b[level+1:]) != tuple(y[level+1:]):
        return False
    return ordinal(a[level]) <= ordinal(x[level]) <= ordinal(y[level]) <= ordinal(b[level])

def actual_scopes(row):
    saved = (row.get('raw_scope') or {}).get('scopes') or []
    if saved:
        return [(tuple(a), tuple(b), level) for a,b,level in saved]
    ref = row.get('target_ref_recorded') or row.get('target_ref') or ''
    try:
        return authored_scopes(ref)
    except ValueError:
        return []

def assert_decoder():
    assert authored_scopes('제127조제1항제6호나목') == [(('127','1','6','나'),('127','1','6','나'),None)]
    assert authored_scopes('제20조의3제1항제2호나목 및 다목') == [
        (('20의3','1','2','나'),('20의3','1','2','나'),None),
        (('20의3','1','2','다'),('20의3','1','2','다'),None)]
    assert authored_scopes('제24조~제26조') == [(('24','','',''),('26','','',''),0)]
    assert authored_scopes('제21조제1항제1호~제8호')[0][2] == 2
    assert authored_scopes('제13조제1항 각 호 외의 부분 단서') == [(('13','1','',''),('13','1','',''),None)]
    assert not contains((('127','1','6',''),('127','1','6',''),None),
                        (('127','1','6','나'),('127','1','6','나'),None))

class Site:
    def __init__(self, site):
        self.path = site
        self.storage = Storage(site)
        self.manifest = json.loads((site/'manifest.json').read_text(encoding='utf-8'))
        cat = self.storage.read(next(d['catalog'] for d in self.manifest['domains'] if d['id']=='tax'))
        self.entries = {d['name']:d for d in cat['laws']}
        self.docs = {}
        self.details = {}
    def article(self, law, jo):
        if law not in self.docs:
            self.docs[law] = self.storage.read(self.entries[law]['file'])
        return next(a for a in self.docs[law]['articles'] if a['jo']==jo)
    def detail(self, law, jo):
        key=(law,jo)
        if key not in self.details:
            article=self.article(law,jo)
            self.details[key] = self.storage.read(article['detail'])[jo]
        return self.details[key]

def compact(row):
    return {k:row.get(k) for k in ('target_law','target_ref','target_kind','status','target_status',
        'source_start','source_end','cite_raw','raw_scope') if k in row}

def compare(site, law, jo, annotation, *, fixture=False):
    body = site.article(law,jo)['text']
    quote = annotation['quote']
    start = annotation.get('start')
    end = annotation.get('end')
    if start is None:
        start = body.find(quote); end = start+len(quote)
    identity = annotation.get('id',law+'|'+jo+'|'+str(start))
    if start < 0 or body[start:end] != quote:
        return dict(id=identity,law=law,jo=jo,outcome='source-span-mismatch',quote=quote,expected_start=start)
    detail = site.detail(law,jo)
    outgoing = [r for r in detail.get('rows',[]) if r.get('direction')=='forward']+detail.get('external',[])
    related = [r for r in outgoing if isinstance(r.get('source_start'),int) and isinstance(r.get('source_end'),int)
               and r['source_start']<end and r['source_end']>start]
    missing=[]
    for target in annotation['expected']:
        kind=target.get('kind') or ('article' if target.get('ref') else 'law')
        owned=[r for r in related if r.get('target_law')==target['law'] and r.get('target_kind',r.get('kind'))==kind]
        if kind in ('law','standard'):
            if not owned:missing.append(dict(target=target,reason='target-or-occurrence-absent'))
            continue
        expected=authored_scopes(target['ref'])
        actual=[s for r in owned for s in actual_scopes(r)]
        absent=[scope for scope in expected if not any(contains(s,scope) for s in actual)]
        if absent:missing.append(dict(target=target,missing_scopes=absent))
    before=annotation.get('before_observation',[]) + ([annotation['kind']] if fixture else [])
    if missing and 'unresolved-table-law' in before:
        issues=detail.get('issues',[])
        issue=next((i for i in issues if quote==i.get('raw') or quote in i.get('raw','')),None)
        if issue:
            return dict(id=identity,law=law,jo=jo,outcome='retained-unresolved-table-candidate',quote=quote,missing=missing,issue={k:issue.get(k) for k in ('kind','reason','raw')})
    outcome='missing-or-truncated-target' if missing else 'matched'
    if not missing and 'matched-source-target-candidate' in before:
        outcome='matched-source-target-existence-candidate'
    return dict(id=identity,law=law,jo=jo,outcome=outcome,quote=quote,missing=missing,
                app_rows=[compact(r) for r in related] if missing else [],
                note='review/not-collected alone is not a failure')

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--site',type=Path,required=True)
    ap.add_argument('--golden',type=Path,default=ROOT/'docs/qa/tax-citation-samples-20261004.json')
    ap.add_argument('--report',type=Path,required=True)
    args=ap.parse_args()
    assert_decoder()
    report_path=args.report.resolve()
    if not report_path.is_relative_to((ROOT/'output').resolve()):
        raise SystemExit('Report must remain under this project output/')
    golden=json.loads(args.golden.read_text(encoding='utf-8')); site=Site(args.site)
    results=[];fixtures=[];negative=[];edition_checks=[]
    editions={e['law']+'|'+e['effective']:e for e in golden['editions']}
    checked_editions=set()
    def check_edition(law, jo, edition_key):
        key=(law,jo,edition_key)
        if key in checked_editions:
            return
        checked_editions.add(key)
        expected=editions[edition_key]
        actual=str(site.article(law,jo).get('effective',''))
        edition_checks.append(dict(law=law,jo=jo,expected_effective=expected['effective'],
            actual_effective=actual,edition_key=edition_key,
            outcome='edition-matched' if law==expected['law'] and actual==expected['effective'] else 'source-edition-mismatch'))
    for article in golden['articles']:
        check_edition(article['law'],article['jo'],article['edition'])
        for annotation in article['annotations']:
            results.append(compare(site,article['law'],article['jo'],annotation))
        for context in article.get('context_annotations',[]):
            if context['expectation_kind']=='unspecified_delegation':
                detail=site.detail(article['law'],article['jo'])
                forward=[r for r in detail.get('rows',[]) if r.get('direction')=='forward']+detail.get('external',[])
                negative.append(dict(law=article['law'],jo=article['jo'],outcome='negative-control-passed' if not forward else 'unexpected-concrete-target',forward_rows=len(forward)))
    for fixture in golden['regression_fixtures']:
        check_edition(fixture['law'],fixture['jo'],fixture['edition'])
        fixtures.append(compare(site,fixture['law'],fixture['jo'],fixture,fixture=True))
    from collections import Counter
    failures=[r for r in results+fixtures if r['outcome'] in ('source-span-mismatch','missing-or-truncated-target')]
    failure_count=len(failures)+sum(n['outcome']!='negative-control-passed' for n in negative)+sum(e['outcome']!='edition-matched' for e in edition_checks)
    payload=dict(site=str(args.site),site_version=site.manifest.get('version'),golden_sha256=hashlib.sha256(args.golden.read_bytes()).hexdigest(),
       method='Human-authored expected refs decoded by a small independent tokenizer; production citation parser/scope utilities are not used. Check source article effective dates against frozen editions, then match owner+kind, original-span overlap and raw_scope. Existing review and not-collected status are allowed.',
       source_articles=len(golden['articles']),edition_checks=edition_checks,edition_outcomes=dict(Counter(e['outcome'] for e in edition_checks)),main_annotations=len(results),main_outcomes=dict(Counter(r['outcome'] for r in results)),
       regression_fixtures=len(fixtures),fixture_outcomes=dict(Counter(r['outcome'] for r in fixtures)),negative_controls=negative,
       failure_count=failure_count,results=results,fixtures=fixtures,
       limits='Checks frozen independent expectations only. Not legal validity, target edition validity, complete reverse recall, or an overall accuracy percentage. Source target-existence candidate and retained table-name candidate remain separate.')
    report_path.parent.mkdir(parents=True,exist_ok=True)
    report_path.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:payload[k] for k in ('source_articles','edition_outcomes','main_annotations','main_outcomes','regression_fixtures','fixture_outcomes','negative_controls','failure_count')},ensure_ascii=False))
    return 1 if failure_count else 0

if __name__=='__main__':
    raise SystemExit(main())
