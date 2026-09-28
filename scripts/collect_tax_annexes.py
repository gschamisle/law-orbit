"""Reproduce the three pinned tax annex analyses; never replace existing output.

Network is opt-in (--collect) and uses the public attachment URLs only.
The dated source bundle remains read-only. No API credentials are needed.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
from urllib.request import Request, urlopen

from core.annex_analysis import digest, validate_analysis
from core.tax_annex import (ROOT, SPECS, DEFAULT_OUTPUT, official_download,
                            validate_source, extract_tax_annex, analyze)


def immutable_write(path, raw):
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError('기존 결과와 다릅니다. 별도 새 출력 폴더를 사용하세요: ' + path.name)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def collect(source_bundle, output, *, network=False, specs_path=SPECS):
    specs = json.loads(Path(specs_path).read_text(encoding='utf-8'))
    if len(specs['annexes']) != 3 or len({a['id'] for a in specs['annexes']}) != 3:
        raise ValueError('검증 대상 국세 별표 3개가 필요합니다.')
    raw = Path(source_bundle).read_bytes()
    if digest(raw) != specs['source_bundle_sha256']:
        raise ValueError('검증 대상 국세 2026-09-28 자료 묶음의 해시 불일치')
    original = json.loads(raw)['source']
    validate_source(original, specs)
    source = deepcopy(original)
    documents = {d['name']:d for d in source['laws']}
    analyses = {}
    for spec in specs['annexes']:
        for format, file in spec['files'].items():
            url = official_download(file['url'])
            path = output / file['name']
            if not path.exists():
                if not network:
                    raise ValueError('공식 원본 파일 없음: --collect 옵션으로 먼저 수집하세요.')
                request = Request(url, headers={'User-Agent':'LawGalaxy public annex verifier'})
                with urlopen(request, timeout=60) as response:
                    payload = response.read()
                if len(payload) != file['bytes'] or digest(payload) != file['sha256']:
                    raise ValueError('공식 서버 파일의 검증 판본 해시 불일치')
                immutable_write(path, payload)
            payload = path.read_bytes()
            if len(payload) != file['bytes'] or digest(payload) != file['sha256']:
                raise ValueError('보존 원본의 해시 불일치')
            signature = b'%PDF-' if format == 'pdf' else bytes.fromhex('d0cf11e0a1b11ae1')
            if not payload.startswith(signature):
                raise ValueError('공식 원본 파일 시그니처 불일치')
        owner = documents[spec['law']]
        owner.setdefault('source_url', spec['source_url'])
        annex = next(a for a in owner['annexes'] if a['ref'] == spec['ref'])
        immutable_write(output/(spec['id']+'-api-source.txt'), annex['text'].encode())
        analysis = extract_tax_annex(output/spec['files']['hwp']['name'], spec)
        analyses[spec['id']] = analysis
        annex['body_analysis'] = analysis
    citations = analyze(source)
    selected = []
    for spec in specs['annexes']:
        analysis = analyses[spec['id']]
        coverage = next(c for c in citations['coverage'] if c['law'] == spec['law'] and c['ref'] == spec['ref'])
        analysis.update(citation_status=coverage['citation_status'], citation_count=coverage['references'])
        validate_analysis(analysis)
        payload = json_bytes(analysis)
        if spec.get('analysis_sha256') and digest(payload) != spec['analysis_sha256']:
            raise ValueError('검증된 별표 분석 결과 해시 불일치')
        immutable_write(output/(spec['id']+'-analysis.json'), payload)
        immutable_write(output/(spec['id']+'-body.txt'), analysis['text'].encode())
        selected.append(dict(id=spec['id'], law=spec['law'], ref=spec['ref'],
            units=len(analysis['units']), cells=len(analysis['table_structure']['cells']),
            characters=len(analysis['text']), text_sha256=analysis['text_sha256'],
            analysis_sha256=digest(payload), citation_status=coverage['citation_status'],
            citations=coverage['references']))
    for row in citations['edges']+citations['external_references']:
        owner = documents[row['source_law']]
        analysis = next(a['body_analysis'] for a in owner['annexes'] if a['ref'] == row['source_jo'])
        if analysis['text'][row['source_start']:row['source_end']] != row['cite_raw']:
            raise ValueError('인용 근거 원문 위치 불일치')
    if original != json.loads(raw)['source']:
        raise ValueError('입력 자료가 변경되었습니다.')
    report = dict(schema=1, selected_annexes=3, selected=selected,
        source_bundle_sha256=specs['source_bundle_sha256'],
        collected_citations=len(citations['edges']), external_citations=len(citations['external_references']),
        citation_issues=len(citations['issues']),
        all_original_hashes_verified=True, all_hwp_text_verified=True,
        all_citation_offsets_verified=True, source_unchanged=True,
        calculations='not-evaluated', applicability='not-evaluated',
        internal_annex_references='not-resolved')
    immutable_write(output/'citations.json', json_bytes(citations))
    immutable_write(output/'verification.json', json_bytes(report))
    immutable_write(output/'source-manifest.json', json_bytes(specs))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-bundle', type=Path,
        default=ROOT.parent/'FscLawGalaxy-Stage2/output/tax-universe/bundle.json')
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--collect', action='store_true')
    args = parser.parse_args()
    print(json.dumps(collect(args.source_bundle, args.output, network=args.collect), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
