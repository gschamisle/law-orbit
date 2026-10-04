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
TOKEN = re.compile(r'제\s*(\d+)\s*(조|항|호|목)(?:\s*의\s*(\d+))?|(['+MOK+r'])\s*목')
LEVEL = {'조': 0, '항': 1, '호': 2, '목': 3}
RANGE = re.compile(r'~|부터|내지|에서')
TABLE_LOCATOR = re.compile(r'^(.*?)\s+표\s+제\s*(\d+)\s*호$')
ANNEX_REF = re.compile(r'^(별표|별지)(?:제)?(\d+)(?:호의(\d+)|의(\d+)호?|호)?(?:서식)?(?:\((\d+)\))?$')


def table_locator(label):
    match=TABLE_LOCATOR.fullmatch(label or '')
    return dict(base=match[1],table_item=match[2]) if match else None


def article_expectation_scopes(label):
    locator=table_locator(label)
    return authored_scopes(locator['base'] if locator else label)


def annex_key(label):
    # Source text writes 제7호의2서식 while official attachment metadata also
    # writes 제7의2호서식. Normalize only this ordering and whitespace; never
    # discard a branch number or a parenthesized form variant.
    match=ANNEX_REF.fullmatch(re.sub(r'\s+','',label or ''))
    return (match[1],match[2],match[3] or match[4],match[5]) if match else None


def verified_annex_container(row,catalog):
    """One independently checked official PDF holds both VAT form16 subforms.

    Do not generally strip a parenthesized variant to find a physical file.
    Every guard is fixed by the reviewed attachment, not production helpers.
    """
    key=annex_key(row.get('target_ref',''))
    if key not in [('별지','16',None,'1'),('별지','16',None,'2')]:return False
    ref='별지 제16호서식'
    url='https://www.law.go.kr/LSW/flDownload.do?flSeq=162619767'
    if (row.get('target_law')!='부가가치세법 시행규칙'
            or row.get('target_effective')!='20260401'
            or row.get('annex_container_ref')!=ref or row.get('neighbor_jo')!=ref
            or type(row.get('annex_container_page')) is not int
            or row['annex_container_page']!=({'1':1,'2':3}[key[3]])
            or row.get('annex_container_sha256')!='bd850a4cd5318d5eb7e185433868ecfa8a52d1ec512f53d52090c7c9ecf63d72'
            or not isinstance(row.get('annex_urls'),list)
            or not all(isinstance(url,str) for url in row['annex_urls'])):
        return False
    matches=[a for a in catalog if a.get('ref')==ref and a.get('effective')=='20260401'
             and isinstance(a.get('urls'),list) and all(isinstance(u,str) for u in a['urls']) and url in a['urls']]
    return len(matches)==1 and set(row['annex_urls'])==set(matches[0]['urls'])


def table_context_present(row,locator):
    # A table row is not an ordinary article ho. Check its literal qualifier in
    # the original context independently of the production highlight parser.
    base=r'\s*'.join(re.escape(char) for char in re.sub(r'\s+','',locator['base']))
    pattern=base+r'\s*(?:의\s*)?표\s*제\s*'+re.escape(locator['table_item'])+r'\s*호'
    return bool(re.search(pattern,row.get('context','')))


def authored_scopes(label):
    """Decode only the already human-authored expected ref labels, independently."""
    if table_locator(label):
        raise ValueError('Table locator is not an ordinary article item: '+label)
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
    """Read the exported highlight scope without a target-ref fallback."""
    value = row.get('raw_scope')
    if not isinstance(value, dict) or not isinstance(value.get('scopes'), list):
        raise ValueError('Missing exported raw_scope')
    result=[]
    for saved in value['scopes']:
        if not isinstance(saved, (list, tuple)) or len(saved)!=3:
            raise ValueError('Malformed exported scope')
        a,b,axis=saved
        if (not isinstance(a,(list,tuple)) or not isinstance(b,(list,tuple))
                or len(a)!=4 or len(b)!=4 or not all(isinstance(v,str) for v in (*a,*b))
                or not a[0] or not b[0] or axis not in (None,0,1,2,3)
                or (axis is None and a!=b)):
            raise ValueError('Malformed exported scope path')
        # Validate coordinates before comparing; never coerce malformed values.
        for coordinate in (*a,*b):
            if coordinate:ordinal(coordinate)
        result.append((tuple(a),tuple(b),axis))
    return result


def covered(scope, allowed):
    """A range may equal a union of manually enumerated adjacent targets."""
    if any(contains(candidate,scope) for candidate in allowed):
        return True
    a,b,axis=scope
    if axis is None:
        return False
    start,end=ordinal(a[axis]),ordinal(b[axis])
    if len(start)!=1 or len(end)!=1:
        return False  # Do not invent adjacency between branched provision numbers.
    intervals=[]
    for x,y,other_axis in allowed:
        if other_axis not in (None,axis):continue
        if x[:axis]!=a[:axis] or y[:axis]!=a[:axis]:continue
        if x[axis+1:]!=a[axis+1:] or y[axis+1:]!=b[axis+1:]:continue
        left,right=ordinal(x[axis]),ordinal(y[axis])
        if len(left)==len(right)==1:intervals.append((left[0],right[0]))
    cursor=start[0]
    for left,right in sorted(intervals):
        if right<cursor:continue
        if left>cursor:return False
        cursor=max(cursor,right+1)
        if cursor>end[0]:return True
    return False


def point(path):
    return (tuple(path),tuple(path),None)


def reference_scopes(value):
    try:return authored_scopes(value)
    except (TypeError,ValueError):return []


def annotation_span(body,annotation):
    start=annotation.get('start')
    if start is None:start=body.find(annotation['quote'])
    end=annotation.get('end',start+len(annotation['quote']))
    return start,end


def expected_for_row(body,row,annotations):
    """Use the narrowest authored quote containing this occurrence.

    A broad context quote can contain a separately annotated law name. For a
    combined app span crossing several atomic quotes, use their authored union.
    No expectations are inferred from the production raw_scope or row target.
    """
    start,end=row['source_start'],row['source_end']
    candidates=[]
    for annotation in annotations:
        a,b=annotation_span(body,annotation)
        if a>=0 and body[a:b]==annotation['quote'] and a<end and b>start:
            candidates.append((a,b,annotation))
    enclosing=[v for v in candidates if v[0]<=start and end<=v[1]]
    if enclosing:
        candidates=[v for v in enclosing if not any(
            v[0]<=w[0] and w[1]<=v[1] and (v[0],v[1])!=(w[0],w[1]) for w in enclosing)]
    return [target for _,_,annotation in candidates for target in annotation['expected']]


def outgoing_rows(detail):
    return [('rows',r) for r in detail.get('rows',[]) if r.get('direction')=='forward'] + [
        ('external',r) for r in detail.get('external',[])]


def row_findings(site,law,jo,body,row,origin,expected):
    """Validate both declared evidence and the fields used by public clicks."""
    findings=[]
    def fail(code,**details):findings.append(dict(code=code,**details))
    def equal(field,wanted):
        if row.get(field)!=wanted:fail('field-mismatch',field=field,expected=wanted,actual=row.get(field))
    equal('source_law',law);equal('source_jo',jo)
    equal('source_id',site.entries[law]['id'])
    start,end=row.get('source_start'),row.get('source_end')
    span_valid=(type(start) is int and type(end) is int and 0<=start<end<=len(body))
    if not span_valid:fail('source-span-invalid',start=start,end=end,body_length=len(body))
    original=body[start:end] if span_valid else None
    for field in ('cite_raw','raw'):
        if span_valid and field in row and row[field]!=original:fail('source-quote-mismatch',field=field)
    if not row.get('cite_raw') and not row.get('raw'):fail('source-quote-missing')
    source_refs=reference_scopes(row.get('source_ref',''))
    if not source_refs or any(s[0][0]!=jo or s[1][0]!=jo for s in source_refs):
        fail('source-reference-mismatch')
    name=row.get('target_law');kind=row.get('target_kind',row.get('kind'))
    targets=[t for t in (expected or []) if t['law']==name and (t.get('kind') or ('article' if t.get('ref') else 'law'))==kind]
    if expected is not None and not targets:fail('unexpected-target-owner-or-kind',target_law=name,target_kind=kind)
    entry=site.entries.get(name)
    target_id=entry['id'] if entry else ''
    equal('target_id',target_id)
    if origin=='rows':
        equal('neighbor_id',target_id);equal('neighbor_law',name)
        equal('neighbor_kind',kind);equal('kind',kind)
        if not row.get('target_ref_recorded'):fail('recorded-reference-missing')
        if entry:
            document=site.document(name)
            if document.get('meta',{}).get('id')!=entry['id'] or document.get('meta',{}).get('name')!=name:
                fail('click-document-identity-mismatch')
    else:
        # The outside panel has no collected-body button or fabricated reverse.
        if row.get('neighbor_id'):fail('unexpected-external-click-id',actual=row['neighbor_id'])
        for field,wanted in (('neighbor_law',name),('neighbor_kind',kind)):
            if row.get(field) and row[field]!=wanted:fail('field-mismatch',field=field,expected=wanted,actual=row[field])
    try:
        scopes=actual_scopes(row)
    except (ValueError,TypeError,KeyError) as exc:
        scopes=[];fail('invalid-raw-scope',reason=str(exc))
    refs=reference_scopes(row.get('target_ref','')) if kind=='article' else []
    if kind=='article':
        allowed=[s for t in targets for s in article_expectation_scopes(t['ref'])]
        if not scopes:fail('numbered-raw-scope-missing')
        for scope in scopes:
            if targets and not covered(scope,allowed):fail('raw-scope-exceeds-manual',scope=scope)
        if len(refs)!=1 or refs[0][2] is not None:
            fail('invalid-target-reference',actual=row.get('target_ref'))
        for ref in refs:
            if targets and not covered(ref,allowed):fail('target-reference-outside-manual',reference=ref)
            if scopes and not covered(ref,scopes):fail('target-reference-outside-raw-scope',reference=ref)
        recorded=row.get('target_ref_recorded')
        if recorded is not None and reference_scopes(recorded)!=refs:
            # This verifier audits outgoing rows only. Reverse displayed refs
            # intentionally differ from their recorded range representative.
            fail('recorded-reference-mismatch',actual=recorded,target_ref=row.get('target_ref'))
        if origin=='rows' and refs:
            target_jo=refs[0][0][0]
            equal('neighbor_jo',target_jo)
            if reference_scopes(row.get('neighbor_ref','')) != [point((target_jo,'','',''))]:
                fail('neighbor-reference-mismatch',actual=row.get('neighbor_ref'))
            if entry:
                document=site.document(name)
                if not any(str(a['jo'])==target_jo for a in document.get('articles',[])):
                    fail('click-article-unavailable',target_jo=target_jo)
    else:
        if kind=='annex':
            key=annex_key(row.get('target_ref',''))
            catalog=site.document(name).get('annexes',[]) if entry and origin=='rows' else []
            container_verified=verified_annex_container(row,catalog)
            if any(k in row for k in ('annex_container_ref','annex_container_page','annex_container_sha256')) and not container_verified:
                fail('unverified-annex-container')
            if not key:fail('invalid-annex-reference',actual=row.get('target_ref'))
            if targets and key not in [annex_key(t.get('ref','')) for t in targets]:
                fail('annex-reference-outside-manual',actual=row.get('target_ref'))
            if entry and origin=='rows' and key:
                if not container_verified and not any(annex_key(a.get('ref',''))==key for a in catalog):
                    fail('click-annex-unavailable',target_ref=row.get('target_ref'))
                # The frontend looks up the physical neighbor ref literally.
                # Canonical manual equality must not hide a broken body lookup.
                elif not any(a.get('ref')==row.get('neighbor_jo') for a in catalog):
                    fail('click-annex-catalog-reference-mismatch',neighbor_jo=row.get('neighbor_jo'))
        if scopes:fail('unexpected-numbered-scope',target_kind=kind)
        if reference_scopes(row.get('target_ref','')):fail('unexpected-numbered-target',target_kind=kind)
        if origin=='rows':
            if kind=='annex':
                if not container_verified and annex_key(row.get('neighbor_jo',''))!=annex_key(row.get('target_ref','')):
                    fail('annex-neighbor-reference-mismatch',neighbor_jo=row.get('neighbor_jo'),target_ref=row.get('target_ref'))
            else:
                equal('neighbor_jo',row.get('target_ref'))
            equal('neighbor_ref',row.get('target_ref'))
            equal('target_ref_recorded',row.get('target_ref'))
    return findings



def destination_key(row):
    ref=reference_scopes(row.get('target_ref','')) or row.get('target_ref','')
    return (row.get('source_start'),row.get('source_end'),row.get('target_law'),
            row.get('target_kind'),json.dumps(ref,ensure_ascii=False))


def structural_check(site,law,jo):
    """Check every outgoing row in the sampled article, including unannotated spans.

    This is a transport/provenance check, not a manual semantic expectation for
    citations absent from the frozen golden. Malformed/unplaced spans cannot be
    hidden by a correct row at an annotated occurrence.
    """
    body=site.article(law,jo)['text'];outgoing=outgoing_rows(site.detail(law,jo))
    errors=[];seen={}
    for index,(origin,row) in enumerate(outgoing):
        findings=row_findings(site,law,jo,body,row,origin,None)
        key=destination_key(row)
        if key in seen:findings.append(dict(code='duplicate-source-target-occurrence',first_row=seen[key]))
        else:seen[key]=index
        if findings:errors.append(dict(row_index=index,origin=origin,findings=findings,row=compact(row)))
    return dict(law=law,jo=jo,outcome='structural-mismatch' if errors else 'structure-matched',
                outgoing_rows=len(outgoing),row_errors=errors)


def click_covered(scope,rows,name,site,*,source_law=None,source_jo=None,detail=None):
    """Check usable destination records as well as the shared highlight scope."""
    a,b,axis=scope
    if axis==0 and name in site.entries:
        numbers=[str(x['jo']) for x in site.document(name).get('articles',[])
                 if contains(scope,point((str(x['jo']),'','','')))]
        # The reader omits a separate button for the currently open source
        # article. This exception applies only to that exact same-law member,
        # with its body available, a positive self-reference count, and the full
        # manual article range still explicitly present in an outgoing scope.
        self_visible=False
        count=(detail or {}).get('same_article_count')
        if (name==source_law and source_jo in numbers and type(count) is int and count>0):
            try:
                body=site.article(source_law,source_jo).get('text','')
                self_visible=bool(body) and any(scope in actual_scopes(row) for row in rows)
            except (StopIteration,KeyError,ValueError,TypeError):
                self_visible=False
        return bool(numbers) and all(
            (self_visible and number==source_jo) or any(
                point((number,'','','')) in reference_scopes(r.get('target_ref','')) for r in rows)
            for number in numbers)
    for row in rows:
        refs=reference_scopes(row.get('target_ref',''))
        if covered(scope,refs):return True
        try:saved=actual_scopes(row)
        except (ValueError,TypeError,KeyError):continue
        for candidate in saved:
            # One range row may legitimately represent several paragraphs,
            # items or mok. Article ranges need each collected clickable jo.
            if candidate[2] is None or (candidate[2]==0 and name in site.entries):continue
            if contains(candidate,scope) and any(contains(candidate,ref) for ref in refs):return True
    return False


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
    def document(self, law):
        if law not in self.docs:
            self.docs[law] = self.storage.read(self.entries[law]['file'])
        return self.docs[law]
    def article(self, law, jo):
        return next(a for a in self.document(law)['articles'] if a['jo']==jo)
    def detail(self, law, jo):
        key=(law,jo)
        if key not in self.details:
            article=self.article(law,jo)
            self.details[key] = (self.storage.read(article['detail'])[jo] if article.get('detail')
                                 else self.document(law)['details'][jo])
        return self.details[key]

def compact(row):
    return {k:row.get(k) for k in ('source_law','source_jo','source_id','source_ref',
        'target_law','target_id','target_ref','target_ref_recorded','target_kind',
        'neighbor_law','neighbor_id','neighbor_jo','neighbor_ref','neighbor_kind',
        'target_effective','annex_urls','annex_container_ref','annex_container_page','annex_container_sha256',
        'status','target_status','source_start','source_end','raw','cite_raw','context','raw_scope','evidence_id') if k in row}


def compare(site, law, jo, annotation, *, fixture=False, annotations=None):
    body=site.article(law,jo)['text'];quote=annotation['quote']
    start,end=annotation_span(body,annotation)
    identity=annotation.get('id',law+'|'+jo+'|'+str(start))
    if start<0 or body[start:end]!=quote:
        return dict(id=identity,law=law,jo=jo,outcome='source-span-mismatch',quote=quote,expected_start=start)
    detail=site.detail(law,jo)
    related=[(origin,r) for origin,r in outgoing_rows(detail)
             if isinstance(r.get('source_start'),int) and isinstance(r.get('source_end'),int)
             and r['source_start']<end and r['source_end']>start]
    authored=annotations or [annotation]
    errors=[];seen={};unassessed=[]
    for index,(origin,row) in enumerate(related):
        permitted=expected_for_row(body,row,authored)
        if fixture:
            # Regression quotes can be whole paragraphs with only one manually
            # audited target. Distinct literal article numbers elsewhere in that
            # context are not a complete negative oracle. Determine this boundary
            # from the unchanged source substring, never from actual target IDs
            # or production raw_scope; still check the row's transport consistency.
            literal=reference_scopes(body[row['source_start']:row['source_end']])
            numbered=[scope for t in permitted if t.get('kind')=='article' for scope in article_expectation_scopes(t['ref'])]
            known_articles=[((a[0],'','',''),(b[0],'','',''),0 if axis==0 else None) for a,b,axis in numbered]
            if literal and numbered and not any(
                    covered(point((source[0][0],'','','')),known_articles) for source in literal):
                unassessed.append(dict(row_index=index,origin=origin,
                    reason='Regression fixture quotes wider context; this separately numbered source citation has no manual target expectation.',row=compact(row)))
                permitted=None
        findings=row_findings(site,law,jo,body,row,origin,permitted)
        # Different destinations from one range/list are intentional. Duplicate
        # evidence for the same source occurrence and destination is not.
        key=destination_key(row)
        if key in seen:findings.append(dict(code='duplicate-source-target-occurrence',first_row=seen[key]))
        else:seen[key]=index
        if findings:errors.append(dict(row_index=index,origin=origin,findings=findings,row=compact(row)))
    missing=[];table_checks=[]
    for target in annotation['expected']:
        kind=target.get('kind') or ('article' if target.get('ref') else 'law')
        owned=[r for _,r in related if r.get('target_law')==target['law'] and r.get('target_kind',r.get('kind'))==kind]
        if kind in ('law','standard'):
            if not owned:missing.append(dict(target=target,reason='target-or-occurrence-absent'))
            continue
        if kind=='annex':
            key=annex_key(target.get('ref',''))
            if not key:raise ValueError('Malformed manual annex reference: '+str(target))
            if not any(annex_key(r.get('target_ref',''))==key for r in owned):
                missing.append(dict(target=target,reason='annex-reference-or-occurrence-absent'))
            continue
        expected=article_expectation_scopes(target['ref']);actual=[]
        for row in owned:
            try:actual.extend(actual_scopes(row))
            except (ValueError,TypeError,KeyError):pass
        absent=[scope for scope in expected if not covered(scope,actual)]
        absent_click=[scope for scope in expected if not click_covered(scope,owned,target['law'],site,source_law=law,source_jo=jo,detail=detail)]
        if absent or absent_click:
            missing.append(dict(target=target,missing_scopes=absent,missing_destination_records=absent_click))
        locator=table_locator(target.get('ref',''))
        if locator:
            matching=[r for r in owned if any(covered(ref,expected) for ref in reference_scopes(r.get('target_ref','')))]
            context_ok=any(table_context_present(r,locator) for r in matching)
            table_checks.append(dict(target=target,base_scopes=expected,context_preserved=context_ok,
                coverage='article-and-paragraph-only; table-row highlight/click unsupported'))
            if matching and not context_ok:
                missing.append(dict(target=target,reason='table-qualifier-context-not-preserved'))
    before=annotation.get('before_observation',[]) + ([annotation['kind']] if fixture else [])
    if missing and not errors and 'unresolved-table-law' in before:
        issue=next((i for i in detail.get('issues',[]) if quote==i.get('raw') or quote in i.get('raw','')),None)
        if issue:
            return dict(id=identity,law=law,jo=jo,outcome='retained-unresolved-table-candidate',quote=quote,
                        missing=missing,row_errors=[],issue={k:issue.get(k) for k in ('kind','reason','raw')})
    outcome=('unexpected-or-inconsistent-app-row' if errors else 'missing-or-truncated-target' if missing
             else 'matched-with-unassessed-context' if unassessed else 'matched')
    if not missing and not errors and 'matched-source-target-candidate' in before:
        outcome='matched-source-target-existence-candidate'
    if not missing and not errors and table_checks:
        outcome='matched-table-base-only'
    edition_constraint=annotation.get('target_edition_constraint')
    edition_check=(dict(constraint=edition_constraint,outcome='historical-target-edition-unverified',
        reason='Current catalog/body records cannot establish the explicitly required pre-amendment text.') if edition_constraint else None)
    if not missing and not errors and edition_check:
        outcome='target-edition-unverified'
    return dict(id=identity,law=law,jo=jo,outcome=outcome,quote=quote,missing=missing,row_errors=errors,unassessed_context_rows=unassessed,
                table_locators=table_checks,target_edition_check=edition_check,
                app_rows=[compact(r) for _,r in related] if missing or errors else [],
                note='review/not-collected alone is not a failure; outgoing records and click destinations are checked separately from highlight scopes')


def negative_control(site,law,jo,annotation):
    """Unspecified delegation is negative only at its frozen source occurrence."""
    body=site.article(law,jo)['text'];start,end=annotation_span(body,annotation)
    if start<0 or body[start:end]!=annotation['quote']:
        return dict(law=law,jo=jo,outcome='source-span-mismatch',quote=annotation['quote'])
    related=[r for _,r in outgoing_rows(site.detail(law,jo))
             if type(r.get('source_start')) is int and type(r.get('source_end')) is int
             and r['source_start']<end and start<r['source_end']]
    return dict(id=annotation.get('id'),law=law,jo=jo,quote=annotation['quote'],start=start,end=end,
        outcome='unexpected-concrete-target' if related else 'negative-control-passed',
        forward_rows=len(related),app_rows=[compact(r) for r in related])


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
    results=[];fixtures=[];negative=[];edition_checks=[];structural_checks=[];checked_structure=set()
    editions={e['law']+'|'+e['effective']:e for e in golden['editions']}
    checked_editions=set()
    def check_edition(law, jo, edition_key):
        key=(law,jo,edition_key)
        if key in checked_editions:
            return
        checked_editions.add(key)
        if (law,jo) not in checked_structure:
            checked_structure.add((law,jo))
            structural_checks.append(structural_check(site,law,jo))
        expected=editions[edition_key]
        actual=str(site.article(law,jo).get('effective',''))
        edition_checks.append(dict(law=law,jo=jo,expected_effective=expected['effective'],
            actual_effective=actual,edition_key=edition_key,
            outcome='edition-matched' if law==expected['law'] and actual==expected['effective'] else 'source-edition-mismatch'))
    for article in golden['articles']:
        check_edition(article['law'],article['jo'],article['edition'])
        for annotation in article['annotations']:
            results.append(compare(site,article['law'],article['jo'],annotation,annotations=article['annotations']))
        for context in article.get('context_annotations',[]):
            if context['expectation_kind']=='unspecified_delegation':
                negative.append(negative_control(site,article['law'],article['jo'],context))
    for fixture in golden.get('regression_fixtures',[]):
        check_edition(fixture['law'],fixture['jo'],fixture['edition'])
        siblings=next((a['annotations'] for a in golden['articles'] if a['law']==fixture['law'] and a['jo']==fixture['jo']),[])
        fixtures.append(compare(site,fixture['law'],fixture['jo'],fixture,fixture=True,annotations=siblings+[fixture]))
    from collections import Counter
    failures=[r for r in results+fixtures if r['outcome'] in ('source-span-mismatch','missing-or-truncated-target','unexpected-or-inconsistent-app-row')]
    failure_count=(len(failures)+sum(n['outcome']!='negative-control-passed' for n in negative)
                   +sum(e['outcome']!='edition-matched' for e in edition_checks)
                   +sum(s['outcome']!='structure-matched' for s in structural_checks))
    payload=dict(site=str(args.site),site_version=site.manifest.get('version'),golden_sha256=hashlib.sha256(args.golden.read_bytes()).hexdigest(),
       method='Manually annotated expected refs decoded by a small independent tokenizer; production citation parser/scope utilities are not used. Check source article effective dates against frozen editions, then validate owner+kind, source identity/quote/span, all actual target references, recorded forward references, catalog IDs, body-click neighbor fields, raw_scope bounds, destination recall and duplicate occurrences. For an article range containing the currently open same-law source, a separate self-click is waived only with its body available, a positive same_article_count and that exact full range present in raw_scope; other members still require actual destination records. Adjacent manual target unions and one-to-many range/list rows are allowed; the narrowest overlapping authored quote owns its occurrence. Existing review and not-collected status are allowed. Regression-fixture context citations with distinct source article numbers are separately marked semantically unassessed while their IDs and internal click/scope consistency are still checked.',
       source_articles=len(golden['articles']),structural_checks=structural_checks,
       structural_outcomes=dict(Counter(s['outcome'] for s in structural_checks)),
       structural_issue_counts=dict(Counter(f['code'] for s in structural_checks for e in s['row_errors'] for f in e['findings'])),
       edition_checks=edition_checks,edition_outcomes=dict(Counter(e['outcome'] for e in edition_checks)),main_annotations=len(results),main_outcomes=dict(Counter(r['outcome'] for r in results)),
       table_locator_targets=sum(len(r.get('table_locators',[])) for r in results),
       table_base_only_annotations=sum(r['outcome']=='matched-table-base-only' for r in results),
       historical_target_edition_checks=[dict(id=r['id'],**r['target_edition_check']) for r in results if r.get('target_edition_check')],
       regression_fixtures=len(fixtures),fixture_outcomes=dict(Counter(r['outcome'] for r in fixtures)),negative_controls=negative,
       failure_count=failure_count,strict_row_issue_counts=dict(Counter(f['code'] for r in results+fixtures for e in r.get('row_errors',[]) for f in e['findings'])),
       unassessed_fixture_context_rows=sum(len(r.get('unassessed_context_rows',[])) for r in fixtures),
       results=results,fixtures=fixtures,
       limits='Checks frozen independent expectations only. Annex refs are checked separately, including branch and form variant numbers, with collected catalog existence. Only the independently checked VAT rule form16 PDF may use a physical base-form container, guarded by owner, edition, exact URL set, page and SHA256. Table locators check only the base provision and original table-number context, explicitly reporting unsupported table-row highlight/click. Explicit historical target editions remain unverified even when the current same-number body is present. Unspecified-delegation negative controls apply only to their frozen quote spans. Not legal validity, target edition validity, complete reverse recall, or an overall accuracy percentage. Source target-existence candidate and retained table-name candidate remain separate. All outgoing rows in sampled and fixture source articles receive structural checks, including missing/invalid spans. Semantic scope expectations apply only to outgoing rows overlapping authored quote spans. Source_ref identity is checked at article level; within-article paragraph/item ownership requires the separate traceability audit. The current-source article range exception verifies stored body availability and reader self-count metadata, not a live browser state; a missing other-article click still fails. Findings may repeat across overlapping annotations, regression fixtures and structural checks; failure_count counts failed check records, not unique defects or an accuracy rate.')
    report_path.parent.mkdir(parents=True,exist_ok=True)
    report_path.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:payload[k] for k in ('source_articles','structural_outcomes','structural_issue_counts','edition_outcomes','main_annotations','main_outcomes','regression_fixtures','fixture_outcomes','negative_controls','failure_count')},ensure_ascii=False))
    return 1 if failure_count else 0

if __name__=='__main__':
    raise SystemExit(main())
