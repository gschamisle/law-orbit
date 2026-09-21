"""Collect BOK's official consolidated PDFs, not an undocumented body API.

The latest revision is discovered by exact title. Its date is cross-checked in
the PDF; the commencement date is read from its final supplementary provision.
Unexpected formats fail closed so a stale PDF cannot silently replace live data.
"""
import hashlib
import io
import re
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlparse, parse_qs
from lxml import html
from core.fsc_collection import CollectionError, norm, ymd, atomic_json

BASE='https://www.bok.or.kr'
SEARCH=BASE+'/portal/singl/law/listSearch.do?menuNo=200200'
TITLES=('외국환거래업무 취급세칙','외국환거래업무 취급절차',
        '외환정보집중기관 운영세칙','외환정보집중기관 운영절차')

def official_url(url):
    url=urljoin(BASE,url);p=urlparse(url)
    if p.scheme!='https' or p.netloc!='www.bok.or.kr' or p.username:raise CollectionError('untrusted-bok-link')
    return url

def fetch(url):
    import requests
    try:
        response=requests.get(official_url(url),timeout=60)
        response.raise_for_status();official_url(response.url)
        if len(response.content)>40*1024*1024:raise CollectionError('bok-file-too-large')
        return response.content
    except requests.RequestException:raise CollectionError('bok-network-failure') from None

def parse_listing(raw, title):
    tree=html.fromstring(raw.decode('utf-8'));matches=[]
    for a in tree.xpath('//a[contains(@href,"/singl/law/view.do")]'):
        if norm(a.text_content())!=norm(title):continue
        li=a.xpath('ancestor::li[1]')
        if not li:continue
        dates=li[0].xpath('.//span[contains(@class,"fs_date")]/text()')
        files=li[0].xpath('.//a[contains(@href,"/law/fileDown.do")]/@href')
        if len(dates)!=1 or len(files)!=1:raise CollectionError('bok-list-schema-changed')
        source=official_url(a.get('href'));pdf=official_url(files[0]);query=parse_qs(urlparse(source).query)
        ident=query.get('lawseq',[''])[0];version=query.get('hseq',[''])[0]
        if not ident.isdigit() or not version.isdigit():raise CollectionError('bok-edition-id-missing')
        pq=parse_qs(urlparse(pdf).query)
        if pq.get('lawseq')!=[ident] or pq.get('seq')!=[version]:raise CollectionError('bok-PDF-edition-mismatch')
        matches.append(dict(name=title,provider='bok',document_id=ident,version_id=version,
                            source_url=source,pdf_url=pdf,promulgated=ymd(dates[0].strip()),
                            listing_sha256=hashlib.sha256(raw).hexdigest()))
    if len(matches)!=1:raise CollectionError('bok-exact-title-not-found:'+title)
    return matches[0]

def discover(as_of, folder, request=fetch):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);records=[]
    for title in TITLES:
        url=SEARCH+'&'+urlencode({'search_text':title})
        raw=request(url);item=parse_listing(raw,title);item['listing_url']=url
        if item['promulgated']>as_of:raise CollectionError('bok-latest-edition-not-yet-current')
        (folder/(item['document_id']+'-listing.html')).write_bytes(raw);records.append(item)
    return dict(as_of=as_of,provider='한국은행 공식 법규정보',records=records)

def extract_pdf(raw):
    import pdfplumber
    if not raw.startswith(b'%PDF'):raise CollectionError('bok-not-PDF')
    try:
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            pages=[]
            for page in pdf.pages:
                # The BOK information procedure is printed as two A4 pages on a spread.
                # Other landscape pages may be annex tables; never split by size alone.
                if (len(pdf.pages)>0 and pdf.pages[0].width>pdf.pages[0].height
                        and '외환정보집중기관운영절차' in norm(pdf.pages[0].extract_text() or '')):
                    halves=[(0,0,page.width/2,page.height),(page.width/2,0,page.width,page.height)]
                    pages.append('\n'.join(page.crop(box).extract_text() or '' for box in halves))
                else:pages.append(page.extract_text() or '')
    except Exception:raise CollectionError('bok-PDF-extraction-failed') from None
    if not pages or any(not p.strip() for p in pages):raise CollectionError('bok-PDF-has-unreadable-page')
    return pages

def parse_pdf(item, pages, raw_hash, as_of):
    text='\n'.join(pages).replace('｢','「').replace('｣','」')
    # Keep original extracted pages; normalize only quotation glyphs for the shared parser.
    if norm(item['name']) not in norm(pages[0]):raise CollectionError('bok-PDF-title-mismatch')
    before=re.split(r'제\s*1\s*(?:장|조)',text,maxsplit=1)[0]
    dates=re.findall(r'개정\s*(\d{4})\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})',before)
    revision=max((''.join((y,m.zfill(2),d.zfill(2))) for y,m,d in dates),default='')
    source_notes=[]
    if revision!=item['promulgated']:
        # Verified against the rendered PDF, its final supplement and BOK's release:
        # https://www.bok.or.kr/portal/bbs/P0002014/view.do?menuNo=200402&nttId=10081715
        # Only this exact immutable file has the January/December header discrepancy.
        known=(item['document_id']=='100466' and item['version_id']=='106486'
               and item['promulgated']=='20231229' and revision=='20230129'
               and raw_hash=='5a571f88414a4cc5d1a6c14f757a6f2f5b2b5611a50966465d12d465ae31a4c1')
        if not known:raise CollectionError('bok-list-PDF-revision-mismatch')
        source_notes.append('공식 PDF 첫 쪽의 개정 이력은 2023.1.29.로 표기되어 있습니다. '
                            '법규정보 목록·공식 개정 게시물·마지막 부칙의 2023.12.29.를 대조했습니다. 원문 표기를 보존합니다.')
    revision=item['promulgated']
    supplements=list(re.finditer(r'(?m)^\s*부\s*칙\s*[<〈(]?\s*(\d{4})\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})',text))
    latest=[m for m in supplements if ''.join((m[1],m[2].zfill(2),m[3].zfill(2)))==revision]
    if len(latest)!=1:raise CollectionError('bok-latest-supplement-missing')
    tail=text[latest[0].end():];tail=re.split(r'(?m)^\s*(?:[<\[〈]\s*별|부\s*칙)',tail,maxsplit=1)[0]
    dates=re.findall(r'이\s*(?:세칙|절차)\s*(?:은|는)\s*(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일\s*부터\s*시행한다',tail)
    if len(set(dates))!=1:raise CollectionError('bok-commencement-date-unresolved')
    y,m,d=dates[0];effective=ymd(y+m.zfill(2)+d.zfill(2))
    if effective>as_of:raise CollectionError('bok-PDF-not-yet-effective')
    ident=item['document_id'];version=item['version_id']
    return {**item,'uid':'bok:'+ident,'edition_key':f'bok:{ident}:{version}:{effective}',
            'category':'forex','managing_authority':'한국은행','kind':'세칙' if item['name'].endswith('세칙') else '절차',
            'effective':effective,'state':'current-body-verified','fetched_at':as_of,
            'body_sha256':raw_hash,'text_sha256':hashlib.sha256(text.encode()).hexdigest(),
            'source_notes':source_notes,'raw_body_blocks':[text],'pdf_pages':len(pages),'extraction':'pdfplumber; two-up BOK procedure read left then right; quotation glyph normalization',
            'effective_basis':tail.strip(),'articles':[],'annexes':[],
            'body_status':'collected-not-indexed'}

def collect(inventory, folder, request=fetch, progress=None):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);result=[]
    for item in inventory['records']:
        path=folder/(item['document_id']+'-'+item['version_id']+'.pdf')
        raw=path.read_bytes() if path.exists() else request(item['pdf_url'])
        path.write_bytes(raw) # Staging only: retain downloaded evidence even when validation fails.
        pages=extract_pdf(raw);doc=parse_pdf(item,pages,hashlib.sha256(raw).hexdigest(),inventory['as_of'])
        path.write_bytes(raw);atomic_json(path.with_suffix('.pages.json'),pages)
        result.append(doc)
        if progress:progress(doc['name'],'시행',doc['effective'],'PDF',len(pages),'쪽')
    return result
