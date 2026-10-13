# 전 분야 주간 판본 점검

공개 사이트에 실린 자료가 법제처의 현행 목록과 같은 판본인지 매주 월요일 오전 9시(한국시간)에 확인한다. 이름이 바뀌어도 법제처의 고유 식별번호로 비교한다. 새 판본을 찾았다는 사실과 공개 자료에 반영했다는 사실을 구분한다.

## 범위

- 공개 메뉴의 법령·행정규칙 전체. 현재 20개 분야이며 새 분야는 공개 목록에 포함되면 자동으로 점검 대상이 된다.
- 지방세 중앙 법령뿐 아니라 공개된 지역별 조례·규칙 목록.
- 분야 간 중복은 같은 제공처·판본·시행일을 기준으로 제거하고, 영향을 받는 분야는 모두 기록.
- 국세·금융의 기존 주간 수집·분석 갱신은 유지. 다른 분야는 이번 작업에서 **판본 확인만** 추가했다.

한국은행의 별도 제공 자료 4개는 법제처 판본 식별자가 없으므로 `manual-source-check`로 남긴다. 별표·첨부파일의 내용 자체 변경, 미수집 법령의 신규 제정, 지자체 공보와의 대조는 이 점검이 보장하지 않는다.

## 실행

`LawGalaxy-StateProperty` 폴더에서:

```powershell
..\FscLawGalaxy-Stage2\.venv\Scripts\python.exe -m scripts.check_all_editions
```

기본 실행은 GitHub main의 공개 자료 메타데이터와 실제 공개 사이트 버전이 일치하는지 먼저 확인한다. 고정 배포 자료는 체크섬을 검증해 내려받아 재사용한다. 개발 중인 로컬 판본을 공개 판본으로 오인하지 않는다.

이미 보유한 같은 공개 자료로 점검할 때는 `--site output/<공개자료폴더>`를 지정할 수 있다. 이때도 `static-web-release.json`의 자료 버전과 일치해야 한다.

API 인증은 기존 환경변수·로컬 설정을 재사용하며 요청 URL·인증값을 보고서에 저장하지 않는다. 결과는 `output/all-edition-checks/latest.json`, 실행별 기록은 `runs/`, 초기 실행 실패는 `last-failure.json`에 저장한다. `check.lock`이 있으면 다른 실행을 중단하거나 잠금을 지우지 않고 종료한다.

## 결과 읽기

| 상태 | 의미 |
|---|---|
| unchanged | 고유번호·판본번호·시행일·명칭이 일치 |
| changed | 새 판본 또는 명칭 변경. `edition_changed`와 `renamed`로 구분 |
| repealed / scheduled | 목록상 폐지 또는 시행 예정. 현행 일치로 처리하지 않음 |
| missing-current / ambiguous-current | 현행 목록에 없거나 복수 판본이어서 추가 확인 필요 |
| identity-unverified / provider-failed | 구판 식별 또는 제공처 목록 확인 실패. 변화 없음으로 처리하지 않음 |
| manual-source-check | 법제처 외 별도 출처 자료로 수동 확인 필요 |

공식 목록은 모든 페이지의 수·식별번호와 첫 페이지 재조회를 확인한다. 부분 조회 성공을 전체 성공으로 보고하지 않는다. 구판이 현행 목록에 없으면 구판 원문 메타데이터로 고유번호를 확인하며, 제목 유사도만으로 이름 변경을 확정하지 않는다.

`notification_needed`는 미반영 목록의 변화 여부를 나타낸다. 같은 변경 후보·같은 접근 장애를 반복 알리지 않는다. 공개 자료를 자동 덮어쓰거나 커밋·푸시·배포하지 않으며, 검토 후 별도 반영한다. 공공 GitLab의 읽기 전용 비교와 미반영 변경 알림도 기존 주간 예약에서 유지한다.

공식 규격: [법령 목록 API](https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsEfYdListGuide), [자치법규 목록 API](https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=ordinListGuide).
