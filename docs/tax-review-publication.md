# 국세 보완판 생성과 보존 조건

공개 자료를 보존한 채 국세의 미수집 인용, 선정 별표 본문, 실제 직전 시행판 비교를 순서대로 추가한다. 현재 국세 105개 법령의 14,324개 조문 본문·시행일·삭제 상태, 기존 연결 32,587건은 바꾸지 않는다. 다른 14개 분야의 법령·인용 자료와 분야 간 연결 자료는 보존한다. 이 중 조달·계약, 국토·건축·주택, 환경·화학·안전은 메뉴와 지도 제목의 구분점만 통일한다.

## 실행 순서

```powershell
python -B -m scripts.collect_tax_annexes --collect
python -B -m scripts.collect_tax_delegation_history --site output/static-procurement-structured-v2-20260928 --destination output/tax-delegation-history-20260929
python -B -m scripts.build_tax_review_site --base-site output/static-procurement-structured-v2-20260928 --tax-bundle ../FscLawGalaxy-Stage2/output/tax-universe/bundle.json --annexes output/tax-annexes-20260929 --history output/tax-delegation-history-20260929 --destination output/static-tax-review-final-20260929
```

이미 생성된 결과는 덮어쓰지 않는다. 새로 수집할 때는 새 목적지를 지정한다. 별표 원본·분석 해시는 검토한 세 파일에 고정되어 있으며, 판본이 바뀌면 재수집·재검토 후 갱신해야 한다. 이전 판본 비교도 현재 공개 자료의 해시와 결합되어 있어 다른 판본에 재사용할 수 없다.

일반 국세 수집·빌드는 미수집 인용 보존을 계속 사용한다. 별표 본문은 `core.tax_annex.attach`로 검증된 자료를 원본의 사본에 결합한 뒤 `build_tax_universe(..., annex_bodies=True)`로 생성한다. 확인하지 않은 새 별표 판본을 과거 분석 결과로 대체하지 않는다. 위 전용 빌드가 현재 공개판에 세 보완을 함께 반영하는 경로다.

## 검증과 한계

- 별표는 칸·문단의 원문 위치를 보존하며, 0건 인용과 미분석을 구분한다. 내부 항목 참조·세액 계산·적용 판단은 하지 않는다.
- 본칙의 새 미수집 인용은 5,589건이며, 대상이 불명확한 문구 42건은 별도의 확인 항목이다. 이 수는 새로 수집한 법령 수나 확정된 영향 조문 수가 아니다.
- 법인세법·소득세법·조특법의 공식 직전 시행판을 대조한다. 과거 역인용은 현재 연결에서 만들어내지 않는다.
- 공개 파일을 다시 묶은 후 전체 분야를 검증한다. 원천 bundle과 기존 공개판은 그대로 둔다.
- 로컬 개정안 검토, 의미만 유사한 조문, 표의 계산 조건, 미수집 대상 법령 본문은 이번 작업 범위가 아니다.

빌드 결과·파일 수·용량·보존 검증은 목적지 옆의 `-report.json`에 저장한다. 코드의 회귀 검사와 실제 수집 자료를 이용한 검사는 구분해 실행한다.
