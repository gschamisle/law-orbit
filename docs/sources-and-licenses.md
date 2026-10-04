# 출처와 라이선스 고지

확인일: 2026-10-04. 실제 저장 글꼴·고지 파일과 출처 기록, 공개 후보 `static-tax-audit-20261004-v3`의 글꼴 고지, 국가법령정보센터의 공식 저작권·이용정책을 확인했습니다. 서비스별 상세 약관·제3자 자료 전체의 권리관계를 전수 확인한 문서는 아닙니다.

**프로젝트 코드 라이선스는 선택 중입니다.** 최상위 `LICENSE`가 없으며, 이 고지가 MIT·Apache 등 이용 허락을 새로 부여하지 않습니다. [공개 웹 고지 원본](../web/notices.html)에서도 같은 상태를 안내합니다.

**프로젝트 코드, 법령 데이터, 외부 자료, 글꼴, 이미지는 같은 이용조건으로 묶지 않습니다.** 항목별로 확인된 고지와 미확정 사항을 아래에 구분합니다. 공개자료 경계는 [공개자료 점검](public-materials-audit-20261004.md)을 참고하세요.

## 1. 프로젝트 코드와 문서

| 항목 | 저장소 근거 | 확인 상태 |
|---|---|---|
| Python 코드, 브라우저 코드, 문서 | `core/`, `ui/`, `web/`, `scripts/`, `docs/` | 최상위 프로젝트 `LICENSE` 없음. 코드 라이선스 선택 중; 별도 포괄 이용 허락 미확정 |
| 프로젝트 정보·의존성 선언 | [pyproject.toml](../pyproject.toml), [uv.lock](../uv.lock) | 명칭·버전·의존성 기록은 라이선스 부여를 대신하지 않음 |
| 외부 프로젝트에 대한 영감 표기 | [프로젝트 안내](project-guide.md#영감을-준-프로젝트) | 시각화 아이디어의 출처 표기이며 코드 복제·이용 허락의 증거로 보지 않음 |
| 의견·검토 문서 | [정제된 감사 기록](public-materials-audit-20261004.md) | 공개 적정성 미확정. 법령 원문이나 앱 코드의 라이선스로 간주하지 않음 |

코드 전체에 적용할 라이선스, 저작권 표시 주체, 기여물의 권리 정리는 소유자의 결정이 남아 있습니다. 이 문서는 그 결정을 대신하지 않습니다.

## 2. 법령·행정규칙·조례 및 공식 첨부자료

### 공식 정책에서 확인한 범위

- [저작권법 제7조](https://www.law.go.kr/lsLinkCommonInfo.do?lsJoLnkSeq=1029423769)는 헌법·법률 등 법적 규범과 국가·지방자치단체의 고시 등 일정한 자료를 저작권 보호 대상에서 제외합니다. 확인한 조문 화면의 시행일은 2026-08-11입니다.
- [국가법령정보센터의 법적효력/저작권 안내](https://www.law.go.kr/LSW/lawPetitionForm.do?menuId=13&query=&subMenuId=79)는 제7조 해당 정보 및 법제처가 저작재산권 전부를 보유한 저작물의 자유이용을 안내하고, 제공 법령정보의 영리 목적 활용도 허용한다고 설명합니다. 동시에 비공개 정보·허락 없는 제3자 권리 정보는 제공 대상에서 제외하며, 이용조건과 타인의 권리를 준수하도록 정합니다.
- 같은 안내는 센터의 제공 정보를 참고자료로 구분합니다. 법의 궤도에서도 공식 출처·시행일·판본을 함께 표시하며, 프로젝트가 만든 인용 지도·역인용·가공 결과를 공식 해석이나 기관의 승인으로 표시하지 않습니다.

이 범위를 **공식 사이트의 모든 PDF·사진·로고·첨부 이미지·타인 저작물에 대한 일괄 허락으로 확대하지 않습니다.** 별표·서식이 법령 자체에 해당하는지, 별도 해설·제3자 요소인지 자료별로 구분해야 합니다. 개별 PDF·이미지와 한국은행 등의 별도 자료에 붙은 조건은 각각 확인합니다. API 인증·접근과 자료의 저작권 이용 범위도 구분합니다. [국가법령정보 공동활용](https://open.law.go.kr/LSO/index.html)의 계정별·운영상 상세 이용조건은 이번 고지에서 새로 전수 확인하지 않았습니다.

### 원천별 기록

| 자료 | 확인된 출처·수집 근거 | 표시·가공 방식 | 남은 확인 |
|---|---|---|---|
| 법률·시행령·시행규칙·행정규칙·지방조례 | [국가법령정보센터](https://www.law.go.kr/), [수집 원천 목록](../data/law-galaxy-sources.json), [공식 링크 생성](../core/law_library.py) | 문서명, 시행일, 수집 판본 및 공식 링크와 함께 본문·명시적 인용 제공 | 위 공식 정책을 확인함. API 상세 운영조건과 개별 첨부·제3자 권리는 전수 확인하지 않음 |
| 별표·서식 메타데이터 및 선정 본문 | [국세 별표 원천](../data/tax-annex-sources.json), [별표 연결 범위](annex-reference-links.md), [보건·의료 범위](medical-universe.md) | 번호·제목·공식 첨부파일 링크. 선정 자료만 본문 분석 | 법령 본문·서식·첨부 이미지의 권리를 일괄 동일하게 취급하지 않음 |
| 지방조달 공식 PDF 2종 | [원천·파일 해시](../data/procurement-pdf-sources.json) | 지방자치단체 입찰·계약 집행기준 및 낙찰자 결정기준의 확인한 본문·표 셀·별표 문단을 추출 | PDF 전체와 제3자 도표·서식 등 개별 요소의 이용조건은 별도 확인 필요 |
| 외환 관련 한국은행 세칙·절차 | [한국은행](https://www.bok.or.kr/), [공식 PDF 수집기](../core/forex_bok.py), [수집 안내](forex-universe.md) | 문서명·판본·공식 PDF·원문 해시를 보존하며 조문·인용 추출 | 한국은행 자료별 재사용 조건을 법제처 자료와 동일하다고 추정하지 않음 |
| 공공기관 지정 변경·참고 링크 | [변경 기록](../data/public-institutions/designation-changes.json), [원천 해시](../data/public-institutions/designation-hashes.json), [범위 설명](public-institution-scope.md) | 확인한 공식 변경 내용과 근거 링크 | 지정기관 명부나 모든 정기·수시 변동을 전수 재배포하는 자료가 아님 |
| 고용노동부·중앙노동위원회·헌법재판소 등 참고 사이트 | [노동 프로필](../core/labor_profile.py), [헌법 프로필](../core/constitution_profile.py) | 관련 공식 사이트 링크 | 링크 제공과 사이트 콘텐츠 수집·재배포는 별개 |

기준 공개 묶음의 URL 필드에는 `law.go.kr`, `www.law.go.kr`, `www.bok.or.kr`, `mofe.go.kr`, `alio.go.kr`, `www.alio.go.kr`, `www.moel.go.kr`, `www.nlrc.go.kr`, `www.ccourt.go.kr`가 있었습니다. 링크가 있다는 사실은 그 사이트의 내용을 모두 수집했다는 뜻이 아닙니다.

프로젝트가 만든 그래프·인용 위치·역인용·구조화 결과는 공식 기관의 해석이나 승인 자료로 표시하지 않습니다. 공식 원문 출처와 프로젝트의 분석을 구분하며, 수집 시점과 시행일도 구분합니다. 개별 공공누리 유형이나 포괄적 “자유 이용” 허락은 확인 없이 부여하지 않았습니다.

## 3. 글꼴

| 글꼴·파일 | 출처 기록 | 저장된 이용조건·고지 | 실제 사용 |
|---|---|---|---|
| MaruBuri Regular / SemiBold / Bold, WOFF2 3개 | [atlas-fonts.json](../ui/assets/fonts/atlas-fonts.json)의 네이버 배포 URL·수집일·SHA-256 | [MaruBuri-LICENSE.txt](../ui/assets/fonts/MaruBuri-LICENSE.txt), SIL Open Font License 1.1, NAVER의 저작권·예약 글꼴명 표기 | 공개 웹·지도·독립 HTML·소개문. 검토자료 HTML은 Regular/Bold를 선택적으로 포함 |
| Pretendard SemiBold, WOFF2 1개 | 같은 원천 기록의 공식 저장소 v1.3.9 배포 URL | [Pretendard-LICENSE.txt](../ui/assets/fonts/Pretendard-LICENSE.txt), SIL Open Font License 1.1, Kil Hyung-jin 및 예약 글꼴명 표기 | 버튼·표제·공개 웹·독립 지도 HTML·소개문 |
| NanumMyeongjo Regular / Bold, TTF 2개 | [SOURCE.txt](../ui/assets/fonts/SOURCE.txt)의 Google Fonts 고정 커밋, 원본 파일이라는 기록 | [OFL.txt](../ui/assets/fonts/OFL.txt), SIL Open Font License 1.1, NHN의 저작권·예약 글꼴명 표기 | 저장소 보관 파일. 기준 정적 사이트에는 TTF가 복사되지 않음 |

원천 기록에 있는 WOFF2 4개 파일의 SHA-256은 2026-10-04에 실제 저장 파일과 모두 일치했습니다. MaruBuri의 저장 고지는 Copyright (c) 2010 NAVER Corporation, Pretendard는 Copyright (c) 2021 Kil Hyung-jin, NanumMyeongjo는 Copyright (c) 2010 NHN Corporation으로 시작하며 예약 글꼴명을 명시합니다.

저장된 SIL Open Font License 1.1은 조건에 따라 사용·포함·수정·재배포를 허용합니다. 글꼴 자체의 단독 판매 제한, 글꼴 배포 시 저작권·라이선스 고지 유지, 수정본의 예약 글꼴명 사용 제한 등을 준수해야 합니다. 글꼴을 사용해 만든 문서에 OFL을 강제로 적용하는 조건은 아닙니다. 상세 조건은 위에 연결한 각 고지 전문을 기준으로 확인하세요. 개별 글꼴의 OFL은 앱 코드나 법령 데이터 전체에 대한 이용 허락이 아닙니다.

### 배포별 고지 경로

- 정적 웹: [화면 생성기](../scripts/build_static_galaxies.py)가 `fonts/`에 WOFF2와 고지 텍스트를 복사합니다. 공개 후보 `static-tax-audit-20261004-v3`의 MaruBuri·Pretendard 고지 2개는 저장 원본과 바이트 단위로 같았습니다. [웹 고지](../web/notices.html)는 배포된 두 고지 전문으로 바로 연결합니다.
- 독립 지도 HTML: [render_html](../core/law_galaxy.py)이 두 글꼴의 저작권·OFL 전문을 HTML에 포함합니다.
- 소개문: [소개 HTML](law-orbit-introduction.html)에 글꼴과 읽을 수 있는 OFL 전문이 포함되어 있습니다.
- 검토자료 HTML: 2026-10-04 소스의 [내보내기](../web/app.mjs)와 [HTML 생성](../web/reading.mjs)은 MaruBuri 고지를 읽은 경우에만 글꼴을 포함하며 고지 전문도 함께 넣습니다. 고지를 읽지 못하면 기기의 기본 글꼴을 사용합니다. 이 고지에서 확인한 것은 현재 내보내기 소스의 처리이며, 모든 과거에 내려받은 HTML이 자동으로 바뀌지는 않습니다.

## 4. 이미지·아이콘

| 자산 | 용도·확인된 근거 | 확인 상태 |
|---|---|---|
| `web/law-orbit-social-20260928.jpg` | 공개 사이트 공유용 브랜드 이미지. [웹 메타데이터](../web/index.html)에서 참조 | 화면 캡처로 분류하지 않음. 제작 도구·원본·제작자·별도 재사용 허락 기록은 미확인 |
| `web/icon.svg` | 앱 아이콘. 저장소에 포함된 벡터 도형 | 외부 이미지 링크 없음. 제작 주체와 코드 외 별도 이용 허락은 미확정 |
| `docs/assets/law-orbit-hero-20260928.jpg` | 소개 관련 이미지 자산 | 파일별 제작·편집 경로와 별도 이용 허락은 미확인 |
| `logo.png` | 저장소의 로고 자산 | 기준 정적 사이트에 독립 파일로 포함되지 않음. 제작 출처·별도 허락은 미확인 |
| 소개 HTML의 포함 이미지 | 소개문 자체에는 실제 공개 앱 화면을 캡처했다는 안내가 있음 | 이 설명을 모든 브랜드 이미지의 제작 출처로 확대하지 않음. 개별 포함 이미지와 원본 파일 대응 기록은 미완성 |

이미지 제작 정보가 없다는 이유만으로 제3자 작품이라고 단정하지도, 프로젝트가 모든 권리를 소유한다고 단정하지도 않습니다. 제작자·원본 위치·편집 과정·허락을 확인한 뒤 항목별 기록을 보완해야 합니다.

## 5. 의존성과 개발 도구

정확한 설치 버전은 [uv.lock](../uv.lock), 직접 의존성과 선택 설치 범위는 [pyproject.toml](../pyproject.toml)을 기준으로 확인합니다.

점검한 Python 기본 직접 의존성은 `anthropic`, `lxml`, `olefile`, `openai`, `pypdf`, `pdfplumber`, `python-dotenv`, `python-hwpx`, `pywin32`(Windows), `requests`, `streamlit`입니다. `python-pptx`는 `presentations` 선택 설치 범위에 있습니다.

이 목록은 제3자 라이선스 전문 목록이나 전이 의존성 전체 명세가 아닙니다. 패키지·배포 버전마다 포함된 `LICENSE`·`NOTICE`, 전이 의존성, 네이티브 구성요소의 조건을 별도로 확인해야 합니다. API 클라이언트 패키지의 라이선스와 OpenAI·Anthropic·법제처 등 서비스의 이용조건도 구분합니다.

## 6. 확인이 남은 범위

1. 프로젝트 코드·문서에 적용할 라이선스와 저작권 표시 주체.
2. 브랜드 이미지·로고·소개 이미지의 항목별 제작·재사용 근거.
3. 공식 정책에서 확인한 법령정보 범위를 넘어서는 개별 PDF·이미지·제3자 자료의 조건, API 상세 운영조건과 필요한 고지.
4. 직접·전이 의존성의 버전별 라이선스 전문 및 배포에 필요한 고지의 완전한 목록.
5. Git에 남은 의견 문서의 공개 적정성. 현재 정적 사이트에 없다는 사실과 저장소 공개 가능 여부는 별도 판단입니다.

출처 기록을 보완할 때 인증값이 들어간 API URL, 개인 작성 글의 원문·연락처, 업로드한 개정안은 이 문서에 복사하지 않습니다.
