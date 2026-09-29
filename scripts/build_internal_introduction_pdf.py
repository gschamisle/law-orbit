"""Refresh the internal announcement PDF, retaining its artwork and typefaces.

Optional authoring dependencies: reportlab, pypdf, fonttools[woff], qrcode.
The source PDF and final PDF remain outside Git under output/pdf.
"""
import argparse
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from fontTools.ttLib import TTFont as SourceFont
from pypdf import PdfReader
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.cu2quPen import Cu2QuPen
import qrcode

ROOT=Path(__file__).resolve().parents[1]
W,H=A4;M=48;CW=W-2*M
BG='#092d30';INK='#f4eedc';MINT='#a3d7c6';MUTED='#aac5ba';GOLD='#e6c983';LINE='#345955'
APP='https://gschamisle.github.io/law-orbit/'
DEVELOPER_CREDIT='개발 · 재정경제부 이금석'
FIELDS=[
 ('국세','국세 법령, 인용 관계, 위임사항·후속 개정 후보'),
 ('조달·계약','국가·지방계약, 계약예규·조달청 집행기준'),
 ('관세·통관','관세·FTA·환급, 통관·원산지·보세 고시'),
 ('외환','지급·송금·자본거래·보고, 한국은행 세칙, 금융 연결'),
 ('국유재산','관리 법령·지침, 특례의 근거·유형·기한'),
 ('공공기관','정의 차용·민영화 특례·지정 변경, 후속 개정 후보'),
 ('국고·회계','국고 집행·국가회계·채권·국채, 문단형 지침 근거'),
 ('금융','금융위 법령, 업권별 감독규정·시행세칙'),
 ('공정거래','경쟁·기업집단·하도급·소비자, 심사지침 인용'),
 ('고용·노동','근로기준·기간제·파견·임금·휴가·권리구제'),
 ('의료','개설·시설·인력·진료지원, 선정 별표 본문 인용'),
 ('지방세','중앙 지방세 법령, 선택 지역의 조례·규칙'),
 ('국토·건축·주택','도시계획·건축·주택·정비, 인허가 관련 근거'),
 ('환경·화학·안전','환경관리·화학물질·화학사고·안전 관련 근거'),
]

def pdf_font(source, target):
    font=SourceFont(source);font.flavor=None
    if 'CFF ' in font:
        glyph_set=font.getGlyphSet();glyphs={}
        for name in font.getGlyphOrder():
            pen=TTGlyphPen(glyph_set)
            glyph_set[name].draw(Cu2QuPen(pen,max_err=1.0,reverse_direction=True))
            glyphs[name]=pen.glyph()
        fb=FontBuilder(font['head'].unitsPerEm,isTTF=True)
        fb.setupGlyphOrder(font.getGlyphOrder());fb.setupCharacterMap(font.getBestCmap())
        fb.setupGlyf(glyphs);fb.setupHorizontalMetrics(font['hmtx'].metrics)
        fb.setupHorizontalHeader(ascent=font['hhea'].ascent,descent=font['hhea'].descent)
        names={k:font['name'].getDebugName(v) or 'Document Serif' for k,v in {'familyName':1,'styleName':2,'uniqueFontIdentifier':3,'fullName':4,'psName':6,'version':5}.items()}
        fb.setupNameTable(names)
        os2=font['OS/2']
        fb.setupOS2(sTypoAscender=os2.sTypoAscender,sTypoDescender=os2.sTypoDescender,usWinAscent=os2.usWinAscent,usWinDescent=os2.usWinDescent,usWeightClass=os2.usWeightClass)
        fb.setupPost();fb.setupMaxp();font=fb.font
    font.save(target)

def build(source,dest):
    temp=dest.parent/'assets';temp.mkdir(parents=True,exist_ok=True)
    for weight in ['Regular','SemiBold','Bold']:
        t=temp/f'MaruBuri-{weight}.ttf'
        pdf_font(ROOT/f'ui/assets/fonts/MaruBuri-{weight}.woff2',t)
        pdfmetrics.registerFont(TTFont('Maru'+weight,str(t)))
    t=temp/'Pretendard.ttf';pdf_font(ROOT/'ui/assets/fonts/Pretendard-SemiBold.woff2',t)
    pdfmetrics.registerFont(TTFont('Pretendard',str(t)))
    pdfmetrics.registerFontFamily('MaruRegular',normal='MaruRegular',bold='MaruBold')
    original=PdfReader(source)
    assets={}
    for i in [0,3,4]:
        p=temp/f'original-art-{i+1}.png';original.pages[i].images[0].image.save(p);assets[i]=p
    qr=qrcode.make(APP);qr.save(temp/'app-qr.png')
    c=canvas.Canvas(str(dest),pagesize=A4,pageCompression=1)
    c.setTitle('법의 궤도 - 내부 공지용 소개');c.setAuthor(DEVELOPER_CREDIT);c.setSubject('헌법과 14개 업무 분야의 법령 연결 탐색 · 2026-09-28')
    def p(text,y,size=11,color=INK,bold=False,x=M,width=CW,leading=None):
        style=ParagraphStyle('body',fontName='MaruBold' if bold else 'MaruRegular',fontSize=size,leading=leading or size*1.72,textColor=HexColor(color),wordWrap='CJK')
        para=Paragraph(text,style);_,h=para.wrap(width,H)
        if y+h>H-65:raise ValueError('Page content overflows: '+text[:60])
        para.drawOn(c,x,H-y-h);return y+h
    def small(text,y,x=M,color=MINT):
        c.setFillColor(HexColor(color));c.setFont('Pretendard',9);c.drawString(x,H-y,text)
    def line(y):
        c.setStrokeColor(HexColor(LINE));c.setLineWidth(.7);c.line(M,H-y,W-M,H-y)
    def page(k,title,eyebrow,sub=''):
        c.setFillColor(HexColor(BG));c.rect(0,0,W,H,fill=1,stroke=0)
        small(eyebrow,51);p(title,73,23,bold=True)
        if sub:p(sub,115,10.3,MUTED)
        c.bookmarkPage('p'+str(k));c.addOutlineEntry(title,'p'+str(k),0,False)
        line(H-50);small('법의 궤도  |  내부 공지용 소개',H-28,color=MUTED)
        c.setFont('Pretendard',9);c.drawRightString(W-M,28,'목차' if k==0 else f'{k:02d}')
    def image(path,top,width=CW,x=M):
        im=ImageReader(str(path));iw,ih=im.getSize();height=width*ih/iw
        c.drawImage(im,x,H-top-height,width,height);return top+height
    def url(text,target,y,x=M):
        p(f'<link href="{escape(target)}" color="{GOLD}"><u>{escape(text)}</u></link>',y,9.5,x=x,width=W-M-x)
    # Cover: preserve the original illustrated background, replace all typeset text.
    c.drawImage(str(assets[0]),0,0,W,H)
    small('PUBLIC AX  /  법령 탐색 도구',58)
    p('법의 궤도',140,43,bold=True)
    p('한 조문을 고치기 전에,<br/>함께 볼 법령을 찾습니다.',218,23,bold=True)
    p('조문 본문과 인용 근거를 함께 읽는<br/>헌법과 14개 업무 분야의 법령 연결 지도',325,12,MINT)
    line(688)
    p('헌법 · 국세 · 조달·계약 · 관세·통관 · 외환 · 국유재산 · 공공기관 · 국고·회계<br/>금융 · 공정거래 · 고용·노동 · 의료 · 지방세 · 국토·건축·주택 · 환경·화학·안전',705,8.2,MUTED,leading=16)
    small('개인이 만든 무료 공개 베타',H-60,color=MUTED);small('2026. 09. 28.',H-60,x=W-M-68)
    c.showPage()
    # Contents.
    page(0,'목차','CONTENTS','한눈에 이해하고, 실제 업무의 조문으로 시작해 보세요.')
    toc=[('한눈에 보는 법의 궤도','취지 · 주요 기능 · 이용 대상 · 앱 접속 QR'),('한 조문에서 연결 찾기','법령·조문·항호목을 목록에서 선택'),('연결된 본문과 근거 보관','기준 조문 유지 · 인용 위치 · HTML·CSV 내려받기'),('헌법과 14개 업무 분야','분야별 수록 내용과 활용 범위'),('새로 넓힌 탐색 범위','헌법 길잡이 · 고용·노동 · 의료 별표'),('후속 개정의 검토 후보','국세·공공기관의 위임사항과 판본 비교'),('이용 조건과 의견 보내기','공개·로컬 기능 · 분석 한계 · 피드백')]
    for i,(t,d) in enumerate(toc,1):
        y=173+(i-1)*74;small(f'{i:02d}',y+15);p(t,y,14,bold=True,x=M+38,width=CW-75);p(d,y+28,9.3,MUTED,x=M+38,width=CW-75)
        c.linkRect('', 'p'+str(i),(M,H-y-59,W-M,H-y+4),relative=0,thickness=0)
        line(y+61)
    p('표지·목차를 제외한 본문은 7쪽입니다. 목차와 주소를 누르면 해당 위치로 이동합니다.',718,9,MUTED)
    c.showPage()
    # Summary with QR.
    page(1,'함께 읽을 조문을 찾는 도구','01 / AT A GLANCE')
    p('법령 개정과 업무 파악의 첫 단계에서<br/><b>관련 조문을 찾고, 그 연결 근거를 읽습니다.</b>',145,16)
    small('헌법 + 14개 업무 분야  /  무료 열람  /  설치·회원가입 없이',224)
    line(246)
    for y,t,d in [(267,'찾기','수집한 법령·조문·항호목을 목록에서 고르고, 직접 인용과 역인용을 확인합니다.'),(312,'읽기','연결 조문과 선정 별표의 본문을 열고, 인용 위치·시행일·공식 출처를 봅니다.'),(357,'보관','선택한 인용 근거와 본문을 HTML로, 근거표를 CSV로 내려받아 검토에 씁니다.'),(402,'점검','국세·공공기관에서는 위임 문구와 하위법령 인용을 대조해 후속 검토 후보를 봅니다.')]:
        p(t,y,11,GOLD,True,width=42);p(d,y,10.2,x=M+56,width=CW-56)
    line(456);p('이런 분께 권합니다',474,12,bold=True)
    p('법령·규정 개정 담당자, 업무 체계를 익히는 수습·신규·전입 직원,<br/>계약·통관·재산·회계·인허가 담당자와 법무·부처 협의 담당자',501,10.5,MUTED)
    c.drawImage(str(temp/'app-qr.png'),M,H-706,120,120)
    p('앱 바로 열기',590,17,bold=True,x=M+143,width=CW-143)
    p('휴대전화 카메라로 QR코드를 스캔하거나<br/>아래 주소를 누르세요.',628,10.5,MUTED,x=M+143,width=CW-143)
    url('gschamisle.github.io/law-orbit/',APP,681,x=M+143)
    p('외부 인터넷 접속이 가능한 기기에서 이용합니다.<br/>전체 분야가 베타이며, 공식 원문 확인과 함께 활용해 주세요.',727,8.8,MUTED)
    c.showPage()
    # Original screenshots retained as dated illustrations; instructions updated.
    page(2,'한 조문에서 연결을 찾습니다','02 / START WITH ONE PROVISION','예시: 국세 → 법인세법 → 제32조(해약환급금준비금의 손금산입)')
    p('분야와 법령을 고른 뒤 수집 조문 목록에서 제32조를 선택합니다.<br/>필요하면 항·호·목으로 범위를 좁혀 연결을 탐색합니다.',153,11)
    end=image(assets[3],221)
    p('기존 안내문의 실제 앱 화면 · 2026. 09. 21. 캡처. 현재는 조문 번호도 목록에서 선택합니다.',end+9,8.3,MUTED)
    p('① 목록에서 선택',end+51,12,GOLD,True);p('법령·조문 번호 직접 입력칸을 목록 선택으로 바꿨습니다. 조 번호를 모를 때는 ‘본문에서 찾기’로 조문 목록을 좁힐 수 있습니다.',end+78,10.5)
    p('② 인용 방향과 근거 확인',end+135,12,GOLD,True);p('화살표는 인용 방향, 점선은 문맥·출처 확인 후보를 나타냅니다. 연결 개수는 개정 의무의 수가 아니므로 지도 아래 인용 근거도 함께 읽습니다.',end+161,10.5)
    c.showPage()
    page(3,'연결된 조문의 본문을 읽습니다','03 / READ & KEEP THE EVIDENCE','기준 조문을 유지하면서 연결된 조문을 읽고, 필요한 근거만 모읍니다.')
    end=image(assets[4],157,width=430,x=(W-430)/2)
    p('기존 안내문의 연결 본문 읽기 화면 · 2026. 09. 21. 캡처',end+8,8.3,MUTED)
    p('본문을 읽어도, 검토의 출발점은 그대로',end+43,12,GOLD,True)
    p('연결된 조문을 누르면 본문 읽기 창이 열립니다. 창을 닫으면 기존 지도로 돌아갑니다. 기준을 바꾸고 싶을 때만 ‘이 조문을 중심으로 탐색’을 선택합니다.',end+70,10.4)
    p('인용 위치 강조와 검토자료 내려받기',end+132,12,GOLD,True)
    p('인용한 문구와 항·호·목 위치를 강조합니다. 원하는 근거를 ‘검토자료에 담기’로 선택하면 본문 포함 HTML 또는 CSV 근거표로 내려받습니다. 수집일·시행일·출처·미확인 사항도 함께 기록합니다.',end+159,10.4)
    c.showPage()
    page(4,'헌법과 14개 업무 분야','04 / COVERAGE','분야별 수집·분석 범위는 다릅니다. 각 화면의 ‘자료 안내’를 함께 확인하세요.')
    p('헌법 - 원칙과 제도의 출발점',157,12,GOLD,True)
    p('최상단의 별도 메뉴. 실제 헌법 인용과 편집한 관련 법률 안내를 구분합니다.',185,10.3,MUTED)
    line(216)
    for i,(name,desc) in enumerate(FIELDS,1):
        y=229+(i-1)*33;small(f'{i:02d}',y+12,color=MINT);p(name,y,10.3,bold=True,x=M+29,width=107);p(desc,y,9.1,MUTED,x=M+140,width=CW-140,leading=14)
        line(y+28)
    p('재정경제부 업무와 관련된 분야를 먼저 배치했습니다. 타 기관 소관도 포함되며, 메뉴 순서는 법적 중요도나 단독 소관을 의미하지 않습니다.',714,9,MUTED)
    c.showPage()
    page(5,'새로 넓힌 탐색 범위','05 / FROM PRINCIPLES TO PRACTICE','자료의 양보다, 실제 업무에서 근거를 찾는 데 도움이 되는지를 먼저 봅니다.')
    sections=[(157,'헌법 | 실제 인용과 길잡이를 구분','헌법 130개 조문과 선정 법률 14개를 수집했습니다. 헌법 제53조를 인용하는 국회법 등 실제 근거는 인용선으로, 기본권·국가기관·경제질서를 구체화하는 관련 법률 11개는 별도 안내로 보여줍니다.','모든 법률의 헌법적 근거·위헌성이나 판례를 분석하지 않습니다.'),(339,'고용·노동 | 근로기준법·기간제법에서 출발','10개 법률군과 선정 규정 4건, 1,494개 조문을 수집했습니다. 근로기준법 제11조·제60조, 기간제법 제4조·제9조 등에서 적용범위·연차휴가·사용기간·차별시정의 근거를 함께 읽습니다.','개인별 권리·의무나 분쟁의 결론을 자동 판단하지 않습니다.'),(521,'의료 | 조문에서 별표 본문까지','의료기관 개설·시설·인력·진료지원의 8개 문서·492개 조문과 별표 4개를 분석했습니다. 의료법 제43조를 인용하는 정원표의 9곳처럼, 칸·문단 단위 인용 근거와 원문을 함께 확인합니다.','다른 별표는 미분석으로 표시합니다. 인력·면적 산식, 내부 참조와 의료행위의 적법성은 미판정입니다.')]
    for y,t,body,limit in sections:
        p(t,y,14,GOLD,True);p(body,y+36,11);p(limit,y+125,9.5,MUTED);line(y+163)
    c.showPage()
    page(6,'후속 개정의 검토 후보를 찾습니다','06 / FOLLOW-UP REVIEW','국세·공공기관에 먼저 적용했습니다. 모든 분야의 후속 개정 필요성을 판정하지 않습니다.')
    p('연결선이 없어도, 위임 문구부터',155,16,GOLD,True)
    p('“대통령령으로 정한다”는 문구가 있어도 시행령이 아직 해당 조문을 인용하지 않으면 기존 인용 지도에는 연결선이 나타나지 않을 수 있습니다. 이를 보완하려고 위임 문구 자체와 대응 인용을 함께 보여줍니다.',199,11.5)
    line(291)
    blocks=[(310,'현재 수집본에서 확인','명시적 위임 문구, 이를 인용하는 시행령·시행규칙, 대응 근거가 확인되지 않은 항목을 살펴봅니다. 비교할 이전 판본이 없으면 ‘이전 판본 미대조’로 표시합니다.'),(424,'이전 판본을 보존한 뒤 비교','새 판본을 수집·분석하여 게시하면 위임의 추가·변경·삭제와 조문 내용 변경 후보를 대조합니다. 앱을 열 때마다 실시간으로 법령을 수집하는 방식은 아닙니다.'),(538,'인용 유무와 개정 의무는 다릅니다','인용이 있어도 새 위임 내용을 충분히 반영했는지 따져야 합니다. 인용이 없다고 개정 누락으로 단정하지 않습니다. 직제·정원 적정성이나 부처 협의 필요성도 자동 판단하지 않습니다.')]
    for y,t,body in blocks:p(t,y,13,bold=True);p(body,y+33,11,MUTED)
    p('공공기관은 정의 차용·확인된 경유 관계·민영화 특례와 검토한 정기 지정 변경도 함께 제공합니다. 전체 기관 명부·수시 변동·기관별 내규를 포괄하지는 않습니다.',690,9.5,MINT)
    c.showPage()
    page(7,'판단의 출발점으로 활용해 주세요','07 / USE & FEEDBACK')
    p('연결이 있다고 반드시 함께 고쳐야 하는 것은 아니며,<br/>연결이 없다고 영향이 없다는 뜻도 아닙니다.',144,14,GOLD,True)
    points=[('전체 분야가 공개 베타','국세도 예외가 아닙니다. 테스트 통과가 법령 전체의 정확도·누락률 검증을 뜻하지 않습니다.'),('미수집·미분석과 표의 한계','별표·첨부·부칙의 지원 수준은 다릅니다. 문구 유사성·입법 취지만으로 이어지는 관계를 모두 찾지 못합니다.'),('공식 원문과 최신 판본 확인','인용 해석에 오류가 있을 수 있습니다. 법령별 수집일·시행일을 확인하고 실제 업무에는 공식 원문을 대조하세요.')]
    for i,(t,d) in enumerate(points):
        y=228+i*80;p(t,y,12,bold=True);p(d,y+29,10.3,MUTED)
    line(472);p('공개 웹 / 내 컴퓨터의 로컬 기능',491,12,GOLD,True)
    p('공개 웹: 본문·인용·역인용·별표 열람, 검토자료 내려받기, 국세·공공기관 위임사항 점검<br/>로컬 전용: 국세·공공기관의 한 조문 전후 비교, 국세 개정안 파일 업로드 검토',521,10.3)
    p('비공개 개정안은 공개 페이지에 입력·업로드하지 않습니다. 공개 앱은 저장 자료와 규칙 기반 분석으로 동작하며, 누적 조회는 고유 방문자 수가 아닌 참고 지표입니다.',579,9.8,MUTED)
    p('이런 의견이 도움이 됩니다',640,12,bold=True)
    p('분야 · 법령명 · 조문 번호 · 이상한 부분의 화면을 함께 알려 주세요.<br/>빠진 인용, 잘못 연결된 조문, 원문 불일치와 실제로 유용했던 사례를 기다립니다.',668,10.2,MUTED)
    url('앱 | gschamisle.github.io/law-orbit/',APP,723)
    url('웹 소개 | gschamisle.github.io/law-orbit/introduction.html',APP+'introduction.html',744)
    c.setFillColor(HexColor(MUTED));c.setFont('Pretendard',8.5)
    c.drawRightString(W-M,64,DEVELOPER_CREDIT)
    c.showPage();c.save()
    return dest

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source',type=Path,default=ROOT/'output/pdf/source/법의궤도_내부공지용_소개.pdf')
    ap.add_argument('--output',type=Path,default=ROOT/'output/pdf/법의궤도_내부공지용_소개_20260928.pdf')
    a=ap.parse_args();a.output.parent.mkdir(parents=True,exist_ok=True);print(build(a.source,a.output))
