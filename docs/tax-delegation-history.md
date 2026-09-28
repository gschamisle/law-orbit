# 국세 3법의 실제 직전 시행판 비교

## 2026-09-29 수집 결과

`scripts/collect_tax_delegation_history.py`는 법인세법·소득세법·조세특례제한법의 **현재 공개본 직전 시행판**을 공식 API에서 수집한다. 현재 공개 사이트 본문은 변경하지 않는다.

| 법률 | 직전 시행판 / MST | 현재 공개판 / MST | 실제 엔진의 변경 조문 |
|---|---|---|---|
| 법인세법 | 2026-01-02 / 276111 | 2026-07-01 / 280349 | 제90조 |
| 소득세법 | 2026-04-21 / 285523 | 2026-07-01 / 280405 | 제57조의2, 제129조 |
| 조세특례제한법 | 2026-07-01 / 280409 | 2026-09-18 / 284389 | 제7조, 제118조 |

산출물: `output/tax-delegation-history-20260929/manifest.json`과 `baselines/`, `current/`, `sources/`. 실제 공개 엔진의 결과와 원문 사례는 같은 폴더의 `review-report.json`에 저장했다.

## 판본 선택과 검증

1. 공개 카탈로그의 고정 `lsiSeq`와 `efYd`를 읽는다. 해당 MST·시행일로 공식 현재 본문을 받아 공개 조문 전체의 번호·제목·본문·조문시행일이 동일한지 확인한다.
2. 공식 본문의 법령ID로 시행일 목록을 `nw=1,3`, 현재 공개 시행일 이하, 시행일 내림차순으로 **끝까지** 읽는다. 전체 건수·페이지 순서·동일 법령ID·현행/연혁 표시·날짜 범위를 검증한다.
3. 현재 판본이 목록에 정확히 한 번 존재해야 한다. 현재보다 이른 시행일 중 가장 늦은 판본을 선택한다. 동일 시행일에서는 공포일·공포번호 순서를 확인하고 식별이 모호하면 실패한다.
4. 선택한 과거판은 `MST`와 `efYd`를 둘 다 지정한다. 과거 요청에 `ID`를 쓰지 않는다. 응답 법령ID·법령명·공포일·공포번호·시행일을 목록과 대조하고, 조문 누락·중복을 거부한다.
5. 선택하는 현재·직전판은 공포일이 시행일 이후이면 수동 확인을 요구한다. 먼 과거의 소급 시행 사례나 이전 법률명은 동일 법령ID의 이력으로 보존하되 실제 비교판의 동일 명칭·날짜 검증을 생략하지 않는다.

**MST 크기와 공포일만으로 전후를 판정하지 않는다.** 실제 소득세법의 직전 시행판은 MST 285523·공포 2026-04-21이고, 공개판은 MST 280405·공포 2025-12-23이다. 시행일은 각각 2026-04-21과 2026-07-01로 공식 시행일 목록 순서를 따른다.

근거 문서: [시행일 목록 API](https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsEfYdListGuide), [시행일 본문 API](https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsEfYdInfoGuide).

## 공개 기준 자료 계약

- manifest: `schema:1`, `kind:tax-delegation-history`, `public_manifest_sha256`, `laws`.
- 각 law: `id`, `name`, `current`, `previous`, `baseline:{path,sha256,bytes}`, `current_snapshot`, `history_pages`.
- baseline: 기존 `schema:1`, `kind:delegation-baseline`, `meta`, `articles`, `details` 형식이며 수집·검증 근거를 `provenance`에 추가한다.
- `current.text_sha256` 및 `previous.text_sha256`는 조문 순서를 유지한 `{jo,title,text,effective}` 배열을 `ensure_ascii=False`, `separators=(',', ':')`, `sort_keys=True`로 직렬화한 UTF-8 SHA256이다. 재사용 함수는 `article_sha256`이다.
- `baseline.meta.id/name/domain`은 공개 법령과 동일하다. 시행일과 공식 링크는 과거판의 값이다.
- **과거 하위법령 전체와 역인용 그래프는 수집하지 않았다.** `details:{}`이고 `evidence_availability.reverse_citations:'not-collected'`이다. 현재 그래프를 종전 판본 근거처럼 복사하지 않는다. 공개 화면은 과거 대응 인용 미확인 안내와 과거 법령 공식 링크를 표시해야 한다.
- 모든 파일은 처음 한 번만 생성한다. 이미 존재하는 목적지는 거부하며, 세 법의 검증이 모두 끝난 뒤 새 폴더에 저장한다.

## 인증값과 원문 해시

공식 이력 목록의 상세링크는 요청한 OC 값을 응답에 포함할 수 있다. 수집기는 해당 값의 원문·URL 인코딩·HTML 표현을 `[REDACTED]`로 치환하고 인증값이 남아 있으면 저장하지 않는다. 인증이 붙은 요청 URL은 저장·로그 출력하지 않는다.

`sources/*.xml`은 필요한 경우 인증값만 치환한 XML이다. `sha256`와 `bytes`는 **실제 저장 파일** 기준이다. 원래 공식 응답은 저장하지 않고 `response_sha256`만 보존한다. `credential_values_redacted`가 둘의 차이를 명시한다. 법령 조문 본문은 변형하지 않는다.

## 실제 변경 사례와 한계

- 법인세법 제90조: 명시적 위임 문구가 없어도, 국세기본법 제47조의4 인용 범위가 `제1항제1호…및 제3호`에서 `제1항제1호의2ㆍ제3호ㆍ제4호`로 바뀌어 기존 인용 재검토 대상으로 나온다.
- 소득세법 제129조제8항제2호: 간접투자외국법인세액을 세후기준가격을 고려하여 대통령령으로 계산하는 문구가 추가 후보로 나온다. 종전 제8항의 범위 `제5항부터 제7항까지`는 현재 제11항의 `제5항부터 제10항까지`와 달라, 기존 엔진은 삭제·추가 후보로 표시한다. 동일 문구 이동으로 확정하지 않는다.
- 조특법 제7조: 업종 목록의 재생에너지·수소발전사업 및 후속 목 번호가 바뀐다. 위임 문구 자체가 같아도 조문 맥락 변경으로 재검토한다.

기존 `reviewDocument`의 결과는 법인세법 1개 항목(context 1), 소득세법 13개 항목(context 10·added 2·removed 1), 조특법 8개 항목(context 8)이다. 중복된 위임 문구가 있으므로 **항목 수는 변경 조문 수나 개정 의무 수가 아니다.** 이 작업은 실제 본칙 판본 비교를 가동하며 의미상 위임 이행, 부칙·별표, 과거 역인용까지 판정하지 않는다.

## 실행과 검사

```powershell
python -B -X utf8 -m scripts.collect_tax_delegation_history --site output/static-procurement-structured-v2-20260928 --destination output/tax-delegation-history-20260929
python -B -X utf8 -m scripts.test_tax_delegation_history
node --test scripts/test_tax_delegation_history.mjs
```

수집기는 기존 `LAW_API_KEY` 또는 `LAW_OC` 환경변수를 사용한다. 환경변수가 없으면 기존 config의 인증값을 사용하되 값을 출력하지 않는다. 새 수집 시에는 새로운 목적지를 지정한다.

검증 결과: Python 9개, 실제 JS 엔진 회귀 5개 통과. 공개 현재 본문 동일성, 원문/기준 파일 해시, 잘못된 법령·판본·미래 시행일·불완전 기준 거부, 인증값 치환, 실제 추가 위임 및 위임 없는 조문 변경을 확인했다.
