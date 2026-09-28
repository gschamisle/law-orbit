"""Download hash-pinned official PDFs, extract bounded prose and preserve originals."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request
from urllib.parse import urlparse
from core.procurement_pdf import extract_pdf, validate_extraction


def collect(destination, records):
    if destination.exists():raise ValueError('Choose a new directory; existing sources are preserved')
    sources=json.loads(records.read_text(encoding='utf-8'))
    destination.mkdir(parents=True)
    for record in sources:
        url=record['attachments'][0]['첨부파일링크'].replace('http:','https:')
        if urlparse(url).hostname not in ('law.go.kr','www.law.go.kr'):raise ValueError('Unofficial PDF URL')
        request=urllib.request.Request(url,headers={'User-Agent':'LawOrbit-source-verification/1.0'})
        with urllib.request.urlopen(request,timeout=90) as response:
            if urlparse(response.url).hostname not in ('law.go.kr','www.law.go.kr'):raise ValueError('Unofficial PDF redirect')
            raw=response.read(64*1024*1024+1)
        if len(raw)>64*1024*1024 or hashlib.sha256(raw).hexdigest()!=record['file_sha256']:
            raise ValueError('PDF changed or exceeded limit; review the edition before collecting')
        path=destination/(record['document_id']+'.pdf');path.write_bytes(raw)
        result=extract_pdf(path,record);validate_extraction(result)
        path.with_name(path.stem+'-extraction.json').write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
        print(record['name']+': source and text verified',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--destination',type=Path,required=True)
    p.add_argument('--records',type=Path,default=Path('data/procurement-pdf-sources.json'))
    a=p.parse_args();collect(a.destination,a.records)
