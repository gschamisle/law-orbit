# 이 조문 건드리면 다 죽는 거야

> 개정안을 검토하고, 연결된 법령과 조문을 탐색합니다.

세법에서 시작해 금융법·지방세·조달계약·국토건축주택·환경화학안전까지 확장한 법령 연결 탐색 도구입니다. 분야별로 수집 자료와 화면 상태를 분리하고, 공통 인용 엔진으로 직접 인용·역인용과 원문 근거를 보여 줍니다. 기존 개정안 파일 검토 기능도 유지합니다.

수집 범위 안에서 검토 후보를 찾는 보조 도구이며, 모든 연결의 완전성이나 동시개정 의무를 확정하지 않습니다.

---

## 제1원칙 — 연관 조문 누락 방지

한 조문을 고치면, 그 조문을 **인용·준용·병행**하거나 그 조문과 엮인 **별표**도 함께 개정해야 하는 경우가 많습니다. 이 연결을 사람이 머리로 추적하면 빠뜨리기 쉽고, 빠뜨리면 법령 간 충돌·적용 오류로 이어집니다. **이 도구의 존재 이유는 그 누락을 막는 것입니다.**

그래서 연관 조문 탐지는 **LLM 추측에 의존하지 않습니다.** 인용 파서·인용 그래프·병행 매트릭스 같은 **결정적 레이어**로 후보를 빠짐없이 찾고, 정말 애매한 판단만 사람(또는 Claude 보조 검토)에게 맡깁니다. "애매하면 포함하고 사람이 검토" — 누락(false negative)을 가장 경계합니다.

### 5가지 연관 분류

| 분류 | 의미 | 채우는 방식 |
|------|------|------------|
| **인용** | 이 조문이 끌어쓰는 조문 | 인용 파서 |
| **준용** | "준용한다"로 끌어쓴 조문 | 인용 파서 |
| **역인용** | 이 조문을 인용하는 다른 조문 (개정 영향) | 인용 그래프 |
| **병행개정** | 짝 세법의 대응 조문 (소득세법↔법인세법 등) | 병행 매트릭스 |
| **별표** | 이 조문과 엮인 별표·별지서식 (양방향) | 별표 인덱스 |

---

## 보완 예정 — 제1원칙이 충분히 성숙한 뒤

다음 기능은 **누락 방지가 완벽에 가까워진 후에 보완**할 영역입니다. 지금은 보조·준비 단계입니다.

- **개정 초안 생성** (개정요강 → 신·구조문대비표 초안): 현재 OpenAI 기반 *보조* 기능.
- **HWPX 출력**: **현재 베타에서 비활성화되어 있습니다**(`config.ENABLE_HWPX_OUTPUT`). 탭은 "준비 중"으로 표시되며, 정식 제공은 추후 안내합니다.

> 우선순위가 분명합니다 — **먼저 "절대 안 빠뜨린다"를 완성하고, 그 위에 초안·출력 편의를 얹습니다.**

---

## 핵심 기능 (현재)

- **지방세 은하** — 중앙 지방세 법령에서 선택 지역의 조례·규칙으로 연결을 펼치고, 조문별 전국 역인용 후보·원문 근거·미분석 상태를 확인. 독립 수집 자료를 사용합니다. [수집 범위와 실행 방법](docs/local-tax-universe.md).
- **세법 은하** — 105개 법령(세법령 49개 + 외부 법령 56개)의 직접 인용·역인용을 3D로 탐색. 조문·항·호·목 입력, 범위·나열형 인용 대조, 별표·법령 정의·분류/회계기준 참조, 원문 문맥과 시행일 표시. [수록 범위와 갱신](docs/law-universe.md).
- **연관 조문 4+1분류** — 개정 조문을 직접 입력하면 인용/준용/역인용/병행/별표로 구분해 연관 조문만 구조화 (GPT 없이 결정적 분석).
- **신설 조문 검토** — ① 신설안이 인용하는 조문 ② 재사용 조번호 잔존 인용 충돌 ③ 유사 제도 체크리스트 ④ 관련 별표. 개정안 파일 업로드 시 수기 병행개정과 자동 대조.
- **폭넓은 인용 파싱** — `제X조`, 가지번호(`제3조의2`), 범위(`제2조부터 제8조까지`·구식 `내지`), 항·호·목, 타법(`「소득세법」 제X조`), 지시 인용(`법/영/규칙 제X조`), 별표·별지서식. 범위 인용은 조문 집합으로 펼쳐 중간 조문까지 포착.
- **인용 그래프 / 병행 매트릭스** — 사전 빌드해 런타임 LLM 호출 없이 즉시 역인용·병행 조회.
- **Claude 검토 레이어** — 신설 조문 검토 결과를 누락/판단필요/조치불요로 삼분류 + 종합 의견(보조).

---

## 설치

Python 3.13+ 및 [uv](https://github.com/astral-sh/uv).

```bash
uv sync
```

## 환경 변수

프로젝트 루트에 `.env` (`.env.example` 참조):

```env
LAW_API_KEY=...            # 법제처 Open API 인증키 (필수)
OPENAI_API_KEY=sk-...      # 개정 초안 생성용 (보조 기능)
ANTHROPIC_API_KEY=...      # Claude 검토 레이어 · 병행 매트릭스 빌드용
# ENABLE_HWPX_OUTPUT=1     # HWPX 출력 활성화(기본 비활성화)
```

법제처 키 발급: [open.law.go.kr](https://open.law.go.kr) 회원가입 후 인증키 신청.

## 실행

```bash
uv run streamlit run app.py
```

첫 메뉴 **법령은하**에 세법 / 금융법 / 지방세 / 조달·계약 / 국토·건축·주택 / 환경·화학안전 탭이 있고, 두 번째 메뉴는 **개정안 검토**입니다.

Windows에서는 `./start.ps1`로 실행하면 `http://127.0.0.1:8503`에서 열립니다.
세법 관계도에서 3D 은하, 조문 영향 탐색, 신설 항 범위 재검토를 이용할 수 있습니다.
자세한 내용은 [조문 영향 탐색](docs/impact-explorer.md)을 참고하세요.

---

## 검증 (오프라인 테스트)

API 키 없이 파서·인용그래프·병행매트릭스·별표 등 핵심 로직을 검증합니다.

```bash
uv run python -m scripts.run_offline_tests
```

실제 수집 판본을 쓰는 통합 테스트는 로컬 전용 번들이 없으면 사유를 표시하고 건너뜁니다. 고정 입력·파서·데이터 분리·미수집 안내 테스트는 계속 실행합니다. 로컬 수집 후에는 실제 판본 테스트도 함께 실행됩니다.

`push`/`pull_request` 시 GitHub Actions([offline-tests.yml](.github/workflows/offline-tests.yml))에서 동일 스위트를 실행합니다.

---

## 아키텍처 (요지)

```
TaxLawAmend/
├── app.py                      # Streamlit 진입점, 탭 구성·기능 플래그
├── config.py                   # API URL, 병행법령 매핑, 기능 플래그
├── core/
│   ├── citation_parser.py      # 인용·준용·범위·별표 파싱 (결정적 핵심)
│   ├── citation_graph.py       # 역인용 그래프 (사전 빌드 JSON 조회)
│   ├── parallel_matrix.py      # 병행 매트릭스 조회 (런타임 LLM 0회)
│   ├── article_relations.py    # 직접입력 → 연관 조문 4+1분류
│   ├── new_article_scanner.py  # 신설 조문 검토 (잔존 인용·프록시·별표)
│   ├── byeolpyo.py             # 별표 ↔ 조문 양방향 연관
│   ├── law_network.py          # 법령군 스코프·역인용 스캔
│   ├── llm_review.py           # Claude 검토 레이어 (삼분류)
│   ├── amendment_agent.py      # 개정 초안 생성 (보조)
│   ├── hwpx_writer.py          # HWPX 생성 (준비 중)
│   └── law_api.py              # 법제처 Open API 클라이언트
└── ui/                         # 단계별 Streamlit UI
```

자세한 내용은 [docs/architecture.md](docs/architecture.md).

---

## 데이터 갱신 (법령 개정 시)

은하의 확장 자료는 `python -m scripts.collect_law_universe`로 수집하고
`python -m core.universe_builder`로 다시 만든다. 수집할 때만 `LAW_API_KEY`가 필요하다.
아래 명령은 기존 개정안 업로드 검토의 인용 그래프·병행 매트릭스를 갱신한다.

```bash
# 현행본 갱신 확인
uv run python scripts/check_law_freshness.py --update-manifest

# 인용 그래프 재빌드 (역인용·별표 — API 비용 없음)
uv run python scripts/build_law_citation_graph.py --all

# 병행 매트릭스 (0~2단계 무료 → 3단계 Claude Batches 약 $3)
uv run python scripts/build_parallel_matrix.py
uv run python scripts/build_parallel_candidates.py
uv run python scripts/adjudicate_parallel_pairs.py --submit
uv run python scripts/adjudicate_parallel_pairs.py --fetch
uv run python scripts/build_parallel_matrix.py
uv run python scripts/build_special_tax_links.py
```

---

## 내부자료 보호

심사·발표 전 개정안 등 내부 문서는 저장소·외부 서비스에 올리지 않습니다. 업로드 파일은 `data/uploads/`(gitignore)에만 저장되고, 골든 기대값 등 민감 자료도 저장소 밖으로 외부화되어 있습니다.

---

## 문서

| 파일 | 내용 |
|------|------|
| [docs/architecture.md](docs/architecture.md) | 전체 아키텍처·모듈 설계·구현 이력 |
| [docs/citation-parsing.md](docs/citation-parsing.md) | 인용 파싱 지원 패턴·한계·확장 |
| [docs/parallel-law-detection.md](docs/parallel-law-detection.md) | 병행법령 탐지 로직·한계·확장 |
| [docs/manual-test-scenarios.md](docs/manual-test-scenarios.md) | 수동 테스트 시나리오·알려진 한계 |

## 조달·계약 은하

**법령은하 → 조달·계약**에서 국가계약·재경부 계약예규를 중심으로 조달청 집행기준과 지방계약을 구분해 탐색합니다. 자료·검색 상태는 기존 은하와 분리하며 공통 인용 분석·시각화 엔진을 재사용합니다. [수집 범위·실행·검증 안내](docs/procurement-universe.md).


## 국토·건축·주택 은하

법령은하의 별도 탭에서 도시계획·건축·주택 및 정비 분야를 탐색합니다. 법령 61건과 행정규칙 12건을 독립 수집하고, 인허가 의제·조례 위임 원문 근거를 함께 보여 줍니다. 수집 범위·실행·미분석 자료·검증은 [국토·건축·주택 은하 안내](docs/housing-universe.md)를 참고하세요.


## 환경·화학안전 은하

환경관리 / 화학물질 / 화학사고·안전 분야에서 중앙 법령 49건과 행정규칙 29건을 별도 수집해 조문 단위 인용·역인용을 탐색합니다. 시행예정판은 현행판과 분리합니다. [수집 범위·실행·검증](docs/environment-universe.md)을 참고하세요.
