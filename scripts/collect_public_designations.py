"""Fetch and recheck the two visually reviewed official announcement tables.

New years or changed PDF hashes require a new reviewed source profile. Failure
preserves the previous register. The announcement date is not a legal effect date.
"""
import argparse,hashlib,json,urllib.request
from pathlib import Path
from core.fsc_collection import atomic_json,norm
from core.public_designations import validate

PROFILES=(
 dict(year=2025,date='20250121',page=2,new=4,total_before=327,total_after=331,
      url='https://www.alio.go.kr/download/download.json?fileNo=2925562',
      pdf_url='https://www.alio.go.kr/download/download.json?fileNo=2925562',
      changed={'대한석탄공사':('공기업','기타공공기관'),'한국수목원정원관리원':('기타공공기관','준정부기관'),'한국재정정보원':('기타공공기관','준정부기관')}),
 dict(year=2026,date='20260129',page=4,new=11,total_before=331,total_after=342,
      url='https://mofe.go.kr/nw/nes/detailNesDtaView.do?menuNo=4010100&searchBbsId1=MOSFBBS_000000000028&searchNttId1=MOSF_000000000076666',
      pdf_url='https://mofe.go.kr/com/cmm/fms/FileDown.do?atchFileId=ATCH_000000000030916&fileSn=2',
      changed={'한국방송광고진흥공사':('공기업','기타공공기관'),'한국법무보호복지공단':('기타공공기관','준정부기관')}),
)

def build(folder,known_hashes):
    import pdfplumber
    from pypdf import PdfReader
    sources=[];events=[]
    for spec in PROFILES:
        year=spec['year'];file=folder/f'{year}-designation.pdf';raw=file.read_bytes();digest=hashlib.sha256(raw).hexdigest()
        if digest!=known_hashes[str(year)]:raise ValueError('Reviewed official PDF changed; review before importing')
        page=PdfReader(file).pages[spec['page']-1].extract_text(extraction_mode='layout')
        with pdfplumber.open(file) as pdf:
            tables=pdf.pages[spec['page']-1].extract_tables()
        table=next(t for t in tables if t[0][2]=='기관명')
        names=[row[2] for row in table[1:]]
        if len(names)!=spec['new']+len(spec['changed']) or len(set(names))!=len(names):raise ValueError('Designation rows differ')
        if set(names[spec['new']:])!=set(spec['changed']):raise ValueError('Changed institution identities differ')
        source_id=str(year)
        sources.append(dict(id=source_id,year=year,announced=spec['date'],page=spec['page'],url=spec['url'],pdf_url=spec['pdf_url'],
            pdf_sha256=digest,page_text=page,text_sha256=hashlib.sha256(page.encode()).hexdigest(),
            new_count=spec['new'],changed_count=len(spec['changed']),total_before=spec['total_before'],total_after=spec['total_after'],
            basis='공식 연간 지정 발표 · 표와 본문 대조',full_register=False))
        for index,row in enumerate(table[1:]):
            name=row[2];before,after=spec['changed'].get(name,(None,'기타공공기관'))
            start=page.index(name);begin=page.rfind('\n',0,start)+1;end=page.find('\n',start)
            if end<0:end=len(page)
            events.append(dict(id=f'{year}-{index+1}',year=year,kind='changed' if before else 'new',name=name,authority=row[1],
                before=before,after=after,effective=None,source_id=source_id,start=begin,end=end,raw=page[begin:end],
                review_basis='발표 당시 변경 내역입니다. 관련 규정은 현재 수집 판본으로 검토합니다. 실제 적용일·경과규정은 별도 확인하세요.'))
    return validate(dict(schema=1,kind='designation-announcement-changes',sources=sources,events=events,
        coverage='2025·2026년 정기 지정 발표의 변경 내역 20건입니다. 기관 전체 명부나 연중 변경의 전수 수집 자료가 아닙니다. 발표일을 지정 효력 발생일로 사용하지 않습니다.'))

def main():
    p=argparse.ArgumentParser();p.add_argument('--download',action='store_true');p.add_argument('--folder',type=Path,default=Path('output/designations'))
    p.add_argument('--output',type=Path,default=Path('data/public-institutions/designation-changes.json'));a=p.parse_args()
    hashes=json.loads((Path(__file__).resolve().parents[1]/'data/public-institutions/designation-hashes.json').read_text())
    a.folder.mkdir(parents=True,exist_ok=True)
    if a.download:
        for spec in PROFILES:
            raw=urllib.request.urlopen(spec['pdf_url'],timeout=30).read()
            if hashlib.sha256(raw).hexdigest()!=hashes[str(spec['year'])]:raise ValueError('Official PDF differs from reviewed edition')
            (a.folder/f"{spec['year']}-designation.pdf").write_bytes(raw)
    value=build(a.folder,hashes);atomic_json(a.output,value);print('Verified designation changes:',len(value['events']))

if __name__=='__main__':main()
