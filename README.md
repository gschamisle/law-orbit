# 법의 궤도

한 조문에서 시작하는 법령 연결 지도입니다. 법령·조문을 고르면 직접 인용과 역인용, 본문과 공식 출처를 함께 읽습니다.
헌법과 14개 업무 분야를 제공하는 **실험적 베타**이며, 분야별 수집·분석 범위가 다릅니다.
**[공개 사이트 열기](https://gschamisle.github.io/law-orbit/)** · [모바일 소개문](https://gschamisle.github.io/law-orbit/introduction.html)

![법의 궤도 브랜드 이미지](web/law-orbit-social-20260928.jpg)

## 시작하기

1. 분야에서 법령과 조문·항·호·목을 선택합니다. 본문 검색으로 목록을 좁힐 수 있습니다.
2. 인용 근거를 눌러 연결된 본문·시행일·공식 출처를 확인합니다. **이 조문을 중심으로 탐색**을 누르면 기준을 바꿉니다.
3. 필요한 근거를 선택해 HTML·CSV 검토자료로 내려받거나, **이 법령 오프라인 저장**으로 해당 자료를 보관합니다.

모바일은 기본적으로 페이지 스크롤을 허용합니다. 지도를 움직일 때 **지도 조작**, 마칠 때 **조작 종료**를 누릅니다. 상단에는 **전체 보기 · 전체 화면 · 지도 조작**을 표시하며, 기기의 동작 줄이기 설정을 존중합니다.

## 수록 분야

**[헌법](docs/constitution-universe.md)**은 최상단의 별도 메뉴입니다.

| 업무 분야 | 상세 범위 |
|---|---|
| 국세 | [법령·인용 탐색](docs/law-universe.md) |
| 조달·계약 | [법령·예규·지침](docs/procurement-universe.md) |
| 관세·통관 | [관세·FTA·통관 근거](docs/mofe-universes.md) |
| 외환 | [법령·한국은행 세칙·절차](docs/forex-universe.md) |
| 국유재산 | [관리 근거·특례](docs/state-property-universe.md) |
| 공공기관 | [정의·적용범위·지정 변경](docs/public-institution-scope.md) |
| 국고·회계 | [집행·회계의 근거](docs/mofe-universes.md) |
| 금융 | [업권별 법령·감독규정](docs/fsc-expansion/sectors.md) |
| 공정거래 | [경쟁·거래·소비자 관련 규정](docs/ftc-universe.md) |
| 고용·노동 | [선정 노동 법령·규정](docs/labor-universe.md) |
| 보건·의료 | [의료기관·지역보건·건강보험·의료급여](docs/medical-universe.md) |
| 지방세 | [중앙 법령·지역 조례·규칙](docs/local-tax-universe.md) |
| 국토·건축·주택 | [도시계획·건축·주택 관련 법령](docs/housing-universe.md) |
| 환경·화학·안전 | [환경·화학·안전 관련 법령](docs/environment-universe.md) |

## 범위와 한계

기능 시험이나 자료 무결성 검사를 통과한 것이 법령 전체의 인용 정확도·누락률을 검증했다는 뜻은 아닙니다. 연결이 있어도 개정 의무를 확정하지 않고, 연결이 없어도 영향이 없다고 판단하지 않습니다.

별표·서식은 번호와 공식 원본을 연결하며, 본문 분석은 확인한 일부 자료에 한정합니다. 부칙·미수집 자료·의미만 비슷한 관계는 지원 범위를 확인하세요. **개정안 파일 검토는 국세의 로컬 앱에서만 지원하며 공개 웹에는 업로드하지 않습니다.**

## 로컬 실행

Python 3.13 이상과 [uv](https://github.com/astral-sh/uv)를 사용합니다. 공개 웹은 설치 없이 열람할 수 있습니다.

```bash
uv sync
uv run streamlit run app.py --server.port 8503
```

로컬 후속 개정 비교에는 Node.js 22 이상이 필요합니다. 수집 자료가 없는 분야에는 미수집 안내가 표시됩니다. 인증·수집·갱신·검증 방법은 [상세 프로젝트 안내](docs/project-guide.md)에 있습니다.

## 더 알아보기

- [공개 웹 사용법](docs/static-galaxies.md) · [날짜별 업데이트 기록](docs/release-history.md)
- [아키텍처](docs/architecture.md) · [파서 지원 범위](docs/citation-parsing.md) · [후속 개정 점검](docs/delegation-review.md)
- [출처·코드·글꼴·이미지 라이선스 확인 상태](docs/sources-and-licenses.md) · [공개자료 점검](docs/public-materials-audit-20261004.md)
- [웹 보안·오프라인 유지](docs/web-security.md) · [2026-10-04 보강 검증](docs/hardening-verification-20261004.md)
- [국세 30조의 공식 원문·인용 연결 표본 검증](docs/qa/tax-citation-audit-20261004.md)
- [추가 24조·역인용·실제 본문 클릭 검증과 보완](docs/qa/tax-validation-phase2-20261004.md)
- [공개 화면의 출처·이용조건](https://gschamisle.github.io/law-orbit/notices.html)

프로젝트 코드 전체의 라이선스는 아직 명시되지 않았습니다. MaruBuri·Pretendard 등 포함 글꼴의 고지와 법령·이미지의 출처는 위 인벤토리에서 구분해 확인할 수 있습니다.

법령 관계를 입체적으로 표현하는 시각화는 [제도 은하](https://chris.gomdori.app/korea100)에서 영감을 받았습니다.
