# Render 공개 배포

공개 사이트는 여섯 은하 탐색만 제공합니다. `PUBLIC_GALAXY_ONLY=1`은 개정안 검토·업로드 및 선택형 작성 기능을 실제로 생성하지 않습니다. 로컬 기본값은 `0`이며 기존 검토 기능은 유지됩니다.

## 초기 구성

| 항목 | 값 |
|---|---|
| 종류 / 실행 환경 | Web Service / Python 3.13 (`.python-version`) |
| 저장소 / 브랜치 | `gschamisle/tax-amendment-assistant` / `codex/render-deployment` |
| 지역 | Singapore |
| 서버 | `1c-2g` — 1 CPU, 2GB RAM, 월 $25 |
| 영구 디스크 | 10GB, 월 $2.50 |
| 디스크 경로 | `/opt/render/project/src/output` |
| Build Command | `uv sync --frozen && uv cache prune --ci` |
| Start Command | `uv run --frozen python -m scripts.run_public_server` |
| Health Check | `/_stcore/health` |
| Auto-Deploy | Off — 초기 검증 뒤 수동 배포 |

2026-09-19 Render 생성 화면 기준 기본 합계 월 $27.50. 세금·추가 트래픽 등은 별도이며 소수 이용자용 초기 사양입니다. 실제 서버 메모리와 동시 접속을 확인한 뒤 증설 여부를 판단합니다. 영구 디스크를 연결하면 재배포 중 짧은 중단이 발생하고 여러 인스턴스로 확장할 수 없습니다.

배포 준비 코드는 `codex/render-deployment` 브랜치에서 관리하며 기존 `main`은 그대로 유지합니다. `render.yaml`로 같은 구성을 만들 수 있습니다. 이 파일을 추가하는 것만으로 유료 서비스가 생성되지는 않습니다. 서비스 생성은 비용 승인 후 진행합니다.

## 공개 법령 자료 이전

Git에 없는 수집 자료는 인증값과 업로드 문서를 제외한 별도 묶음으로 이전합니다.

```powershell
.\.venv\Scripts\python.exe -m scripts.galaxy_snapshot --archive output/render-deploy/public-laws-20260919.tar.gz
```

다섯 분야의 현재 `bundle.json`과 지방세 `current.json`이 가리키는 실제 분석 파일만 포함합니다. 이전 버전·수집 로그·업로드·인증 설정은 포함하지 않습니다. JSON 파싱, 인증값 검사 및 파일별 SHA256 검사를 수행합니다.

검증한 묶음을 **이 저장소의 GitHub Release 공개 자산**으로 올리고 다음 환경변수를 입력합니다. 법령 자료 자체가 공개된다는 점을 확인한 뒤 올립니다.

- `GALAXY_SNAPSHOT_URL`: 해당 Release의 `https://github.com/gschamisle/tax-amendment-assistant/releases/download/...` 주소
- `GALAXY_SNAPSHOT_SHA256`: 도구가 출력한 전체 묶음의 SHA256
- `PUBLIC_GALAXY_ONLY`: `1`

API 키, `.env`, LLM 키는 이 열람 서버에 필요하지 않습니다. 인증값을 넣지 않습니다. 최초 기동 시 자료를 다운로드하고 경로·용량·파일 목록·체크섬을 확인한 뒤 여섯 자료 폴더를 설치합니다. 하나라도 빠지면 공개 앱을 기동하지 않습니다. 기존 자료가 있으면 최초 묶음으로 되돌리지 않습니다. 불완전한 기존 자료나 잠금 충돌은 보존하고 관리자 확인을 요구합니다.

## 자료 갱신과 운영

첫 배포는 검증된 시점의 자료를 제공하는 열람 서버입니다. **노트북의 Codex 자동 갱신 예약은 Render로 이전되지 않습니다.** 서버 자동 갱신은 아직 구성하지 않습니다. Render Cron Job은 이 웹 서비스의 영구 디스크를 공유할 수 없으므로 기존 갱신 명령을 별도 Cron에 등록하는 것으로 해결되지 않습니다.

후속 갱신은 수집·검증한 새 자료를 서버에 별도로 반영해야 합니다. 단순 재배포나 최초 묶음 환경변수 변경은 이미 설치된 자료를 덮어쓰지 않습니다. 자동 갱신을 옮길 때에는 같은 서버 내 예약 작업 또는 별도 공유 저장소를 설계하고 수집 작업의 메모리·복구 조건을 검증해야 합니다.

공개 서버는 파일 업로드, API 인증값 및 런타임 LLM 호출 없이 시작합니다. PDF 추출용 Node/kordoc과 Windows HWP 도구를 설치하지 않습니다. 향후 비공개 검토 서비스를 따로 열 때 인증·사용자별 파일 격리·문서 추출 런타임을 추가해야 합니다.

## 검증

```bash
uv run python -m scripts.test_public_deployment
uv run python -m scripts.test_app_navigation
```

로컬 테스트와 별도로 실제 Render 배포에서는 Linux 의존성 설치, 여섯 은하 탐색·HTML 다운로드, 메모리 사용량, 헬스 체크 및 재기동 후 자료 보존을 확인합니다. 실제 배포 전에는 이 항목들이 통과했다고 간주하지 않습니다.
