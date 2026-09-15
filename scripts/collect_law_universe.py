"""Collect current effective-date XML; no credentials in persisted data or errors."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
import hashlib
import html
import json
from pathlib import Path
import os
import re
import sys
import time
import unicodedata
import xml.etree.ElementTree as ET
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.law_universe import NEW_TAX, EXTERNAL, COURT_RULES, norm


def request_xml(endpoint, key, params):
    for attempt in range(3):
        try:
            response = requests.get('https://www.law.go.kr/DRF/' + endpoint,
                                    params={'OC':key, 'type':'XML', **params}, timeout=40)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            return root, response.content
        except (requests.RequestException, ET.ParseError):
            if attempt == 2:
                raise RuntimeError('공식 API 응답 실패: ' + params.get('query', params.get('ID',''))) from None
            time.sleep(attempt + 1)


def discover(base, category, key):
    result = []
    for page in range(1, 8):
        root, _ = request_xml('lawSearch.do', key, {'target':'eflaw','query':base,'nw':3,'display':100,'page':page})
        laws = root.findall('law')
        allowed = {norm(base + suffix) for suffix in ('',' 시행령',' 시행규칙')}
        for row in laws:
            name = row.findtext('법령명한글','')
            if norm(name) in allowed:
                result.append({'name':name, 'law_id':row.findtext('법령ID',''),
                               'mst':row.findtext('법령일련번호',''), 'effective':row.findtext('시행일자',''),
                               'category':category, 'family':base})
        if len(laws) < 100:
            break
    if not any(norm(r['name']) == norm(base) for r in result):
        raise RuntimeError('정확한 현행 법령명 검색 실패: ' + base)
    return result


def clean(text):
    return html.unescape(re.sub(r'<[^>]+>', '', text or '')).strip()


def number(text):
    text = (text or '').strip()
    m = re.search(r'(\d+)(?:의(\d+))?', text)
    if m:
        return str(int(m[1])) + ('의'+str(int(m[2])) if m[2] else '')
    for c in text:
        try:
            return str(int(unicodedata.numeric(c)))
        except (TypeError,ValueError):
            pass
    return ''


def ref(jo, hang='', ho='', mok=''):
    a, _, b = jo.partition('의')
    h, _, hb = ho.partition('의')
    return (f'제{a}조' + ('의'+b if b else '') + (f'제{hang}항' if hang else '')
            + (f'제{h}호' + ('의'+hb if hb else '') if ho else '') + (mok+'목' if mok else ''))


def parse_body(root, metadata):
    name = root.findtext('기본정보/법령명_한글','')
    if norm(name) != norm(metadata['name']):
        raise RuntimeError('법령 본문 이름 불일치: ' + metadata['name'])
    articles = []
    for unit in root.findall('.//조문단위'):
        if unit.findtext('조문여부') != '조문':
            continue
        jo = number(unit.findtext('조문번호'))
        branch = number(unit.findtext('조문가지번호'))
        if branch and branch != '0':
            jo += '의' + branch
        blocks, parts, offset = [], [], 0
        def add(text, label):
            nonlocal offset
            value = clean(text)
            if not value:
                return
            if parts:
                offset += 1
            blocks.append({'start':offset, 'end':offset+len(value), 'ref':label, 'text':value})
            parts.append(value)
            offset += len(value)
        add(unit.findtext('조문내용'), ref(jo))
        for hang in unit.findall('항'):
            hn = number(hang.findtext('항번호'))
            add(hang.findtext('항내용'), ref(jo, hn))
            for ho in hang.findall('호'):
                hon = number(ho.findtext('호번호'))
                add(ho.findtext('호내용'), ref(jo, hn, hon))
                for mok in ho.findall('목'):
                    mn = re.search(r'[가-하]',mok.findtext('목번호',''))
                    add(mok.findtext('목내용'), ref(jo, hn, hon, mn[0] if mn else ''))
        articles.append({'jo':jo, 'title':unit.findtext('조문제목',''), 'text':'\n'.join(parts),
                         'effective':unit.findtext('조문시행일자',''), 'blocks':blocks})
    annexes = []
    for a in root.findall('.//별표단위'):
        no = number(a.findtext('별표번호'))
        sub = number(a.findtext('별표가지번호'))
        kind = a.findtext('별표구분','별표')
        no += ('의'+sub if sub and sub != '0' else '')
        links = []
        for tag in ('별표서식파일링크','별표서식PDF파일링크'):
            link = a.findtext(tag,'').strip()
            if link.startswith('/'):
                link = 'https://www.law.go.kr' + link
            if link.startswith('https://www.law.go.kr/') or link.startswith('http://www.law.go.kr/'):
                links.append(link.replace('http://','https://',1))
        annexes.append({'ref': ('별지 제'+no+'호서식') if kind in ('서식','별지') else kind+' '+no,
                        'title':clean(a.findtext('별표제목')), 'text':clean(a.findtext('별표내용')),
                        'effective':a.findtext('별표시행일자',''), 'urls':links})
    return {**metadata, 'name':name, 'effective':root.findtext('기본정보/시행일자',''),
            'promulgated':root.findtext('기본정보/공포일자',''), 'articles':articles, 'annexes':annexes,
            'fetched_at':date.today().isoformat()}


def collect(metadata, key, cache, refresh):
    path = cache / (metadata['law_id'] + '.json')
    if path.exists() and not refresh:
        old = json.loads(path.read_text(encoding='utf-8'))
        if old.get('fetched_at') == date.today().isoformat() and old.get('mst') == metadata['mst'] and old.get('effective') == metadata['effective']:
            return old
    # ID resolves the current effective edition, avoiding promulgation compilations.
    root, raw = request_xml('lawService.do', key, {'target':'eflaw','ID':metadata['law_id']})
    data = parse_body(root, metadata)
    if not data['articles']:
        raise RuntimeError('조문이 없는 응답: ' + metadata['name'])
    if data['effective'] > date.today().strftime('%Y%m%d'):
        raise RuntimeError('시행예정본 수집 방지: ' + metadata['name'])
    data['xml_sha256'] = hashlib.sha256(raw).hexdigest()
    (cache / (metadata['law_id'] + '.xml')).write_bytes(raw)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--refresh',action='store_true')
    args = parser.parse_args()
    key = os.environ.get('LAW_API_KEY') or os.environ.get('LAW_OC')
    if not key:
        raise SystemExit('LAW_API_KEY 또는 LAW_OC 환경변수가 필요합니다.')
    old = json.loads((ROOT/'data/law-snapshot-manifest.json').read_text(encoding='utf-8'))
    tax = {r['name'] for r in old['laws'] if not r['name'].endswith(('시행령','시행규칙'))} | set(NEW_TAX)
    jobs = [(b,'tax') for b in sorted(tax)] + [(b,'external') for b in EXTERNAL + COURT_RULES]
    metadata, failures = [], []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(discover,b,c,key):b for b,c in jobs}
        for future in as_completed(futures):
            try:
                metadata.extend(future.result())
            except RuntimeError as exc:
                failures.append(str(exc))
    if failures:
        print('\n'.join(failures), flush=True)
        return 1
    metadata = list({r['law_id']:r for r in metadata}.values())
    cache = ROOT/'data/law-galaxy-snapshots'
    cache.mkdir(parents=True,exist_ok=True)
    sources = []
    print(f'수집 대상 {len(metadata)}개 법령', flush=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(collect,m,key,cache,args.refresh):m['name'] for m in metadata}
        for future in as_completed(futures):
            try:
                data = future.result()
                sources.append(data)
                print(f"[{len(sources)}/{len(metadata)}] {data['name']} · {len(data['articles'])}개 조문",flush=True)
            except RuntimeError as exc:
                failures.append(str(exc))
    if failures:
        print('\n'.join(failures),flush=True)
        return 1
    payload = {'built_at':date.today().isoformat(), 'provider':'법제처 시행일 기준 Open API (eflaw)',
               'laws':sorted(sources,key=lambda x:x['name'])}
    path = ROOT/'data/law-galaxy-sources.json'
    staging = path.with_suffix('.json.tmp')
    staging.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
    staging.replace(path)
    print(f'원문 수집 완료: {len(sources)}개 법령', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
