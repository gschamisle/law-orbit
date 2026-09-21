# 법의 궤도

[소개문 HTML 내려받기](https://github.com/gschamisle/law-orbit/raw/refs/heads/codex/state-property/docs/law-orbit-introduction.html) — 모바일용 · 약 2.3 MB · 글꼴·이미지 포함

**베타 안내:** 국세를 포함한 모든 분야는 실험적 베타 단계입니다. 기능·인용 사례·자료 무결성 검사를 통과한 것과 실제 법령 전체의 정확도·누락률을 검증한 것은 다릅니다. 아래 공개 여부는 배포 상태이며, 분야별 정확도 등급이 아닙니다.

**[공개 웹 열기](https://gschamisle.github.io/law-orbit/) · [최신 개발 소스 — 11개 분야](https://github.com/gschamisle/law-orbit/tree/codex/state-property)**

이 README는 공개판과 최신 개발판의 기능·범위를 함께 안내합니다. 추가 5개 분야와 최신 화면 문구는 `codex/state-property` 브랜치에 있습니다. 기본 브랜치의 실행 코드는 기존 버전을 유지합니다.

> 한 조문에서 시작하는 법령 연결 지도.

[공유용 앱 소개문](https://github.com/gschamisle/law-orbit/blob/codex/state-property/docs/app-introduction.md) · [공개 범위와 개발 현황](https://github.com/gschamisle/law-orbit/blob/codex/state-property/docs/mofe-universes.md)

**국세 · 조달계약 · 관세·통관 · 외환 · 국유재산 · 공공기관 · 국고·회계 · 금융 · 지방세 · 국토건축주택 · 환경화학안전**의 법령과 조문을 3D 법령 지도로 탐색하는 도구입니다. 조문 번호를 입력하거나 수집 본문에서 조문을 고르면, 직접 인용·역인용 경로와 원문 근거를 확인할 수 있습니다.

최신 개발판의 **국유재산·외환·공공기관·관세통관·국고회계**는 별도 미리보기 단계입니다. 기존 공개 사이트에 아직 배포하지 않았습니다. [국유재산 수집·특례](https://github.com/gschamisle/law-orbit/blob/codex/state-property/docs/state-property-universe.md) · [외환 수집·분석](https://github.com/gschamisle/law-orbit/blob/codex/state-property/docs/forex-universe.md) · [재경부 3개 업무 분야의 효용·한계](https://github.com/gschamisle/law-orbit/blob/codex/state-property/docs/mofe-universes.md).

분야마다 **자료·검색·선택 상태를 독립적으로 관리**하고 공통 인용 분석·시각화 엔진을 사용합니다. **개정안 파일 자동 검토는 현재 국세만 지원**합니다.

## 무료 공개 열람 버전

**[법의 궤도 열기](https://gschamisle.github.io/law-orbit/)**

서버 없이 브라우저에서 조문 본문·직접 인용·역인용을 확인하는 [무료 웹 버전 안내](https://github.com/gschamisle/law-orbit/blob/codex/state-property/docs/static-galaxies.md)를 제공합니다. 법령을 선택할 때 필요한 압축 자료만 받고, **이 법령 오프라인 저장**으로 해당 법령 본문과 연결 근거를 기기에 보관할 수 있습니다. 연결 조문을 클릭하면 검토 기준과 지도를 유지한 채 본문 읽기 창이 열립니다. 별도의 **이 조문을 중심으로 탐색** 버튼으로 탐색 기준을 바꿀 수 있습니다. 아래의 국세 개정안 업로드 검토는 기존 로컬 앱에서만 이용합니다.

## 화면 구성

### 1. 법령 탐색

국세를 시작으로 재정경제부 업무와 관련된 분야를 먼저 배치하고, 금융·지방세·국토건축주택·환경화학안전으로 이어집니다. 조달계약·관세통관처럼 법령과 집행규정을 자주 함께 읽는 분야를 앞에 두었습니다. 활용도를 예상한 탐색 순서이며, 실제 이용 통계에 따른 순위나 각 분야 모든 문서의 단독 소관을 뜻하지 않습니다. 새 세 분야는 인용 근거를 확인한 업무 질문으로 시작하며, 종합적인 경영평가·관세 판단·결산 검증 도구를 표방하지 않습니다.

| 순서 | 분야 | 탐색 범위 | 상세 안내 |
|---|---|---|---|
| 1 | **국세** | 국세 법령과 직접 연결된 외부 법령, 조문 영향 탐색, 신설 항 인용 범위 검토 | [수록 범위](https://github.com/gschamisle/law-orbit/blob/codex/state-property/docs/law-universe.md) · [영향 탐색](https://github.com/gschamisle/law-orbit/blob/codex/state-property/docs/impact-explorer.md) |
| 2 | **조달계약** | 국가계약·계약예규, 조달청 집행기준, 지방계약 | [수집·분석 안내](https://github.com/gschamisle/law-orbit/blob/codex/state-property/docs/procurement-universe.md) |
| 3 | **관세·통관** | 관세·FTA·환급 법령과 선정 관세청 통관·원산지·보세 고시 | [판단·수집 범위](https://github.com/gschamisle/law-orbit/blob/codex/state-property/docs/mofe-universes.md) |
| 4 | **외환** | 외환법·시행령·관련 행정규칙·한국은행 세칙/절차, 지급·송금·자본거래·보고·검사 | [수집·분석 안내](https://github.com/gschamisle/law-orbit/blob/codex/state-property/docs/forex-universe.md) |
| 5 | **국유재산** | 기본 법령·관리 지침의 인용망, 특례제한법 별표의 근거·유형·존속기한 | [수집·특례 안내](https://github.com/gschamisle/law-orbit/blob/codex/state-property/docs/state-property-universe.md) |
| 6 | **공공기관** | 운영법과 계약·회계·사업관리 규정의 근거 확인; 현행 평가편람·기관 내규 미분석 | [판단·수집 범위](https://github.com/gschamisle/law-orbit/blob/codex/state-property/docs/mofe-universes.md) |
| 7 | **국고·회계** | 국고 집행·국가회계·국가채권·국채의 근거 확인; 문단형 지침 조문 미분석 | [판단·수집 범위](https://github.com/gschamisle/law-orbit/blob/codex/state-property/docs/mofe-universes.md) |
| 8 | **금융** | 금융위 법령, 보험·은행·증권 등 업권별 감독규정과 시행세칙 | [업권별 탐색](https://github.com/gschamisle/law-orbit/blob/codex/state-property/docs/fsc-expansion/sectors.md) · [구현·수집 범위](https://github.com/gschamisle/law-orbit/blob/codex/state-property/docs/fsc-expansion/implementation.md) |
| 9 | **지방세** | 중앙 지방세 법령, 선택 지역의 조례·규칙, 전국 역인용 후보 | [수집 범위와 한계](https://github.com/gschamisle/law-orbit/blob/codex/state-property/docs/local-tax-universe.md) |
| 10 | **국토건축주택** | 도시계획·건축·주택·정비 관련 법령과 핵심 행정규칙, 인허가 의제·조례 위임 문구 | [수집·분석 안내](https://github.com/gschamisle/law-orbit/blob/codex/state-property/docs/housing-universe.md) |
| 11 | **환경화학안전** | 환경관리·화학물질·화학사고·안전 관련 법령과 핵심 행정규칙 | [수집·분석 안내](https://github.com/gschamisle/law-orbit/blob/codex/state-property/docs/environment-universe.md) |

### 2. 개정안 검토 (국세)

국세 개정안 파일을 여러 개 올리고 두 가지를 대조합니다.

- **번호 이동에 따른 인용 정비:** 항·호·목 번호가 바뀔 때 기존 번호를 인용하던 조문의 정비 후보를 찾습니다.
- **병행개정 대응 조문:** 등록된 대응 관계를 바탕으로 함께 검토할 조문을 찾습니다.

이 메뉴는 국세용 인용 그래프와 병행개정 대응표를 사용합니다. 금융 등 다른 분야의 자료를 수집해도 **해당 분야의 개정안 자동 검토까지 지원하는 것은 아닙니다.** PDF·HWP·HWPX·Markdown·텍스트 파일을 받으며, 문서 형식별 추출 가능 여부에 따라 읽기 결과가 달라질 수 있습니다.

## 법령 탐색에서 할 수 있는 일

- **특정 조문에 집중:** 법령·규정을 선택하고 조문 번호를 입력하면 해당 조문의 인용·역인용 연결을 강조합니다. 수집 본문에서 조문을 찾아 불러올 수도 있습니다.
- **인용 근거 확인:** 범위·나열형 인용을 해석하고, 원문 문맥·시행일·공식 출처를 함께 보여 줍니다. 문맥 확인이 필요한 후보는 구분합니다.
- **분야 밖 연결 확인:** 업권·세부 분야는 복수 태그로 관리합니다. 수집한 다른 분야로 이어지는 조문은 ‘분야 밖 관련 조문’으로 표시합니다.
- **미수집·미분석 구분:** 자료가 없는 분야는 미수집으로 안내합니다. 외부 법령 인용이나 본문 분석이 안 된 자료는 그 상태와 공식 링크를 남깁니다.
- **오프라인 탐색·공유:** 수집된 법령과 연결을 열람하고 독립 HTML로 내려받을 수 있습니다. 드래그·한 손가락 회전, 휠·두 손가락 확대·축소, 전체 화면과 선택형 효과음을 지원합니다.

인용 탐색은 파서와 저장된 그래프를 사용하며 런타임 LLM 호출이 필요하지 않습니다. 분야 사이의 전체 자료를 자동으로 합치지 않습니다.

## 해석할 때 알아둘 점

이 도구는 **수집 범위 안의 검토 후보와 근거**를 보여 줍니다. 연결이 있다고 반드시 함께 개정해야 하는 것은 아니며, 연결이 없다고 영향이 없다고 확정할 수도 없습니다.

- 전국 조례를 비롯한 모든 관련 자료의 완전 수집을 보장하지 않습니다. 분야별 문서에서 수집 범위·미분석 항목을 확인하세요.
- 별표·첨부파일·부칙, 의미만 비슷하고 명시적 인용이 없는 관계 등은 분야별 지원 수준이 다릅니다.
- 화면의 거리·색상·연결 건수는 법적 영향의 크기나 개정 의무의 수를 뜻하지 않습니다.
- 개정안 검토용 자료와 법령 탐색용 자료는 별도입니다. 수집 자료 갱신이 국세 개정안 검토의 모든 자료 갱신을 의미하지 않습니다.

## 설치와 실행

Python 3.13 이상과 [uv](https://github.com/astral-sh/uv)를 사용합니다.

최신 11개 분야의 개발판을 실행하려면 다음과 같이 작업 브랜치를 받습니다.

```bash
git clone --branch codex/state-property https://github.com/gschamisle/law-orbit.git
cd law-orbit
uv sync
uv run streamlit run app.py --server.port 8503
```

Windows에서는 프로젝트 폴더의 `./start.ps1`로 실행할 수도 있습니다. 실행 후 `http://127.0.0.1:8503/`에서 엽니다.

### 인증 설정

자료 수집·현행본 확인에는 법제처 Open API 인증값이 필요합니다. 기존 환경변수 또는 프로젝트 루트의 `.env`에 `LAW_API_KEY`를 설정하세요. 분야별 수집기는 `LAW_OC`도 지원합니다. 인증값을 코드나 Git에 넣지 않습니다.

```env
LAW_API_KEY=법제처_인증값
```

이미 수집된 자료의 법령 탐색에는 API 호출이 필요하지 않습니다. `OPENAI_API_KEY`·`ANTHROPIC_API_KEY`는 선택적 보조 기능·일부 자료 구축에 사용하며, 기본 법령 탐색과 국세 개정안 대조에는 필요하지 않습니다. 설정 항목은 [.env.example](.env.example)을 참고하세요.

## 자료 수집과 갱신

확장 수집 자료는 로컬 전용이며 Git에 포함하지 않습니다. 저장소를 새로 받으면 분야별 수집이 필요하고, 준비되지 않은 분야에는 **데이터 미수집** 안내가 표시됩니다.

| 분야 | 전용 자료 위치 | 수집 안내 |
|---|---|---|
| 국세 | `output/tax-universe/` (별도 갱신판 우선, 기존 `data/` 수록판도 사용) | [수록·갱신 안내](https://github.com/gschamisle/law-orbit/blob/codex/state-property/docs/law-universe.md) |
| 조달계약 | `output/procurement-universe/` | [실행 방법](https://github.com/gschamisle/law-orbit/blob/codex/state-property/docs/procurement-universe.md) |
| 금융 | `output/fsc-universe/` | [수집·검증 안내](https://github.com/gschamisle/law-orbit/blob/codex/state-property/docs/fsc-expansion/implementation.md) |
| 지방세 | `output/local-tax-universe/` | [실행 방법](https://github.com/gschamisle/law-orbit/blob/codex/state-property/docs/local-tax-universe.md) |
| 국토건축주택 | `output/housing-universe/` | [실행 방법](https://github.com/gschamisle/law-orbit/blob/codex/state-property/docs/housing-universe.md) |
| 환경화학안전 | `output/environment-universe/` | [실행 방법](https://github.com/gschamisle/law-orbit/blob/codex/state-property/docs/environment-universe.md) |
| 국유재산 | `output/state_property-universe/` | [실행 방법](https://github.com/gschamisle/law-orbit/blob/codex/state-property/docs/state-property-universe.md) |
| 외환 | `output/forex-universe/` | [실행 방법](https://github.com/gschamisle/law-orbit/blob/codex/state-property/docs/forex-universe.md) |

현재 개발 노트북에는 **국세·금융의 주 1회 갱신**이 예약되어 있습니다. 이 예약은 저장소를 복제한다고 자동 설치되지 않습니다. 국유재산을 포함한 나머지 분야는 수동 수집·갱신하며, 실행 방법은 위 문서를 참고하세요. [자동 갱신의 실행 조건과 검증](https://github.com/gschamisle/law-orbit/blob/codex/state-property/docs/fsc-expansion/automatic-updates.md).

```bash
# 국세·금융의 수동 갱신 (기존 로컬 인증 설정 사용)
uv run python -m scripts.update_law_galaxies --mode auto
```

## 검증

```bash
uv run python -m scripts.run_offline_tests
```

파서·인용 분석·데이터 분리·화면 상태 등을 오프라인으로 검사합니다. 실제 수집 판본에 의존하는 통합 테스트는 로컬 자료가 없으면 이유를 표시하고 건너뛰며, 고정 입력 테스트와 미수집 안내 테스트는 계속 실행합니다. 자료가 있는데 검증에 실패한 경우에는 건너뛰지 않습니다.

GitHub Actions의 [오프라인 테스트](https://github.com/gschamisle/law-orbit/blob/codex/state-property/.github/workflows/offline-tests.yml)에서도 같은 스위트를 실행합니다.

## 기존 기능과 브랜치

- **`main`**: 현재 공개된 여섯 분야의 법령 탐색 + 국세 개정안 검토 화면.
- **[`archive/legacy-main-2026-09-19`](https://github.com/gschamisle/law-orbit/tree/archive/legacy-main-2026-09-19)**: 기존 초안 작성·인용 확인·출력 중심 버전의 보존본. 필요한 기능을 다시 가져올 수 있습니다.

## 내부자료 보호

인증값, 업로드한 개정안, 로컬 수집·분석 결과는 Git에 올리지 않습니다. 업로드 파일은 Git에서 제외한 `data/uploads/`에 보관합니다. 기존 수집 자료와 원문을 유지한 채 검증된 갱신 결과를 분야별로 반영합니다.

## 개발 문서

- [아키텍처와 구현 이력](https://github.com/gschamisle/law-orbit/blob/codex/state-property/docs/architecture.md)
- [인용 파싱의 지원 패턴·한계](https://github.com/gschamisle/law-orbit/blob/codex/state-property/docs/citation-parsing.md)
- [국세 병행법령 탐지](https://github.com/gschamisle/law-orbit/blob/codex/state-property/docs/parallel-law-detection.md)
- [수동 검증 시나리오](https://github.com/gschamisle/law-orbit/blob/codex/state-property/docs/manual-test-scenarios.md)

## 영감을 준 프로젝트

법령 관계를 입체적으로 표현하는 시각화는 [제도 은하](https://chris.gomdori.app/korea100)에서 영감을 받았습니다. 멋진 발상을 나누어준 제작자에게 감사드립니다.

