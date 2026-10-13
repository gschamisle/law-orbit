# 인용 표현을 구조화해 역인용을 찾는 사례 — 내부 발표용 정리

2026-10-05 현재 저장소의 파서·오프라인 시험과 2026-10-04 국세 원문 주석을 확인해 정리했다. 아래에서 **시험 문구**는 합성 회귀 시험의 입력, **실제 표본**은 수집 원문에서 먼저 고정한 주석을 뜻한다. 실제 표본을 인용할 때도 해당 판본에서 확인한 사례이며 현행 법적 적용의 판단을 뜻하지 않는다.

> 조·항·호·목 번호뿐 아니라 범위, 열거, 생략된 법령명과 상대 지시를 구조화하고, 그 근거를 대상 조문에서 거꾸로 찾아 보여줍니다.

## 문구 파싱과 역인용은 두 단계다

출처 A에 `「B법」 제20조부터 제25조까지`가 있으면 먼저 법령 B, 시작 20조, 끝 25조와 원문 위치를 추출한다. 그 뒤 B법의 제23조를 선택하면 **23조를 포함하는 저장 인용의 출처 A**를 역인용으로 찾는다. 원문에 `제23조`가 직접 적혀 있지 않아도 범위에 포함되는지 대조할 수 있다.

저장 근거의 인용 방향은 **A → B**다. 역인용은 **B를 기준으로 A를 조회하는 방식**이며, B의 본문이 A를 인용했다고 바꾸어 저장하는 것이 아니다. 인용 문구를 알아낸 결과와 해당 조문의 적용·제외·개정 필요성을 판단하는 결과도 구분한다.

구현 근거: [문구 파서](../core/citation_parser.py)의 `parse_citations`·`effective_law_name`, [구조화 연결](../core/universe_builder.py)의 `build_universe`, [범위 대조](../core/citation_scope.py)의 `parse_scope`·`classify`, [역인용 화면](../core/galaxy_focus.py)의 `analyze_focus`, [정적 웹 인덱스](../scripts/build_static_galaxies.py)의 `EdgeIndex`.

## 발표에 사용할 핵심 표현 14개

`구조화 확인`은 아래 문구에서 번호·법령 소속을 확인했다는 뜻이다. `문맥 확인`은 연결이나 범위를 보존해도 사람이 원문을 확인해야 하는 상태다. 표의 E01~E14는 아래 부록의 정확한 시험명과 실제 표본 ID를 가리킨다.

| 번호·대표화한 패턴 | 실제 또는 시험 문구 | 연결을 읽는 방법 | 확인한 구현 범위·제한 | 근거 |
|---|---|---|---|---|
| 01 **정식 법령명 + 조·항·호·목**: `[「법령명」] 제x조[의y]제a항제b호[의c]d목` | **실제 표본** `제127조제1항제6호나목`; **시험 문구** `법인세법 제16조제1항제2호가목`, `제14조제1항제1호의2가목` | 법령명과 상위 번호를 보존해 나목과 가목, 제1호와 제1호의2를 구분한다. | 공통 문구 파서 + 그래프의 가지번호 보완. 국세 연결에서 확인. 단독 `가목`의 부모 조·호는 추측하지 않는다. | E01 |
| 02 **조 범위**: `제x조부터 제y조까지`, `제x조 내지 제y조` | **시험 문구** `제2조부터 제8조까지`, `제2조 내지 제8조`; **실제 표본** `「국세기본법」 제47조의2부터 제47조의4까지` | 끝점만 찾는 것이 아니라 범위 안의 제5조·제5조의2, 가지조문 제47조의3도 대조한다. | 공통 파서·범위 대조. 그래프는 수집된 대상 조문을 기준으로 연결하며 없는 조문을 만들어 넣지 않는다. | E02 |
| 03 **항·호 범위**: `제x조제a항부터 제b항까지`, `제x조제a항제b호부터 제c호까지` | **시험 문구** `제16조제1항부터 제3항까지`, `제16조제2항제1호부터 제3호까지`; **실제 표본** `「고등교육법」 제2조제1호부터 제4호까지` | 선택한 항·호가 원문의 범위 안에 있는지 대조한다. | 공통 범위 대조. 모든 호를 별도 연결선으로 펼쳤다는 뜻은 아니다. 상위 단위가 생략되어 불명확하거나 항→조처럼 단위가 섞이면 문맥 확인. | E03 |
| 04 **열거와 생략 복원**: `「법령명」 제x조, 제y조 및 제z조`; `제x조제a항ㆍ제b항` | **시험 문구** `「부가가치세법」 제9조 및 제10조`; **실제 표본** `「소득세법」 제119조제1호ㆍ제2호, 제4호부터 제8호까지, 제8호의2 및 제10호부터 제12호까지` | 뒤에 생략된 법령명·조·항을 앞의 연결 가능한 번호에서 이어받는다. 범위와 열거가 섞여도 원문을 보존한다. | 공통 문구 파서·그래프 범위 처리. 중간에 실질적 산문이 끼면 법령 소속을 무조건 이어 주지 않는다. | E04 |
| 05 **같은 법**: `「A법」 … 같은 법 제x조` | **시험 문구** `「온실가스 배출권의 할당 및 거래에 관한 법률」 제2조제3호의 배출권과 같은 법 제29조제1항에 따른 외부사업` | `같은 법`을 출처인 조세특례제한법이 아니라 앞서 명시한 온실가스 법률로 읽는다. | 공통 문구 파서에서 선행 법령 소속 확인. 상대 표현·제외 조건이 있으면 그래프에서 문맥 확인 상태가 될 수 있다. 선행 법령이 없는 경우의 정확성은 보장하지 않는다. | E05 |
| 06 **같은 조 + 항 열거**: `제x조제a항 및 같은 조 제b항 및 제c항` | **실제 표본** `「부가가치세법」 제60조제2항 및 같은 조 제3항 및 제4항에 따른 가산세` | 뒤의 제3항과 제4항을 각각 부가가치세법 제60조에 붙여 구조화한다. | 공통 문구 파서 + 국세 그래프에서 두 항 연결 확인. 화면 범위 상태는 **문맥 확인**. 금융·행정규칙 적용기는 같은 조를 미해결 확인사항으로 남기는 경로가 있어 전 분야 지원으로 표현하지 않는다. | E06 |
| 07 **같은 항·동항**: `제x조제a항 … 같은 항 제b호`, `… 동항제b호` | **실제 원문을 고정한 시험** `제155조제7항의 규정에 따른 농어촌주택 중 동항제2호`, `제155조제7항에 따른 농어촌주택 중 같은 항 제2호` | 소득세법 시행령 제155조제7항제2호로 복원한다. 같은 번호가 있는 다른 법률로 붙이지 않는다. | 공통 문구 파서 + 국세 그래프에서 확인. **문맥 확인**이며 같은 문장 안의 분명한 조·항 앵커가 필요하다. 앵커가 없거나 항 범위·경쟁 법령·닫힌 괄호로 모호하면 연결하지 않는다. | E07 |
| 08 **법·영·이 영**: `법 제x조`, `영 제x조`, `이 영 제x조의y` | **시험 문구** `법 제127조제1항제3호`, `영 제184조`, `이 영 제15조의2` | 시행령의 `법`은 모법, 시행규칙의 `영`은 시행령, `이 영`은 해당 법령군의 시행령을 가리킨다. | 공통 지시참조 해석에서 확인. 행정규칙·세칙의 `법`·`규정`은 분야 적용기의 명시 약칭 근거를 확인한다. 토큰만 보고 모든 규정을 모법으로 붙이는 주장이 아니다. | E08 |
| 09 **한글 목 열거**: `제x조제a항제b호나목 및 다목` | **실제 표본** `제20조의3제1항제2호나목 및 다목` | 제20조의3제1항제2호의 나목과 다목을 각각 구조화해 한 목만 남는 잘림을 막는다. | 공통 문구 파서 + 국세 연결 보완에서 확인. 단독 `가목 및 나목`의 조·항·호는 생성하지 않는다. | E09 |
| 10 **목 범위의 보존**: `제x조제a항제b호라목부터 바목까지` | **실제 원문을 고정한 시험** `법 제24조제2항제1호라목부터 바목까지` | 조·항·호와 목 범위의 두 끝점을 보존한다. | **범위 보존 + 문맥 확인**. 목 사이의 순서를 확정해 중간 목 전체를 자동 전개하거나 정확한 포함 판정을 했다고 발표하지 않는다. | E10 |
| 11 **준용 표현**: `제x조를 준용한다`, `제x조의 규정을 준용한다` | **시험 문구** `제30조의2의 규정을 준용한다`, `제20조부터 제25조까지를 준용한다` | 참조 조문을 찾고 가까운 `준용` 표현을 일반 인용과 구분해 태깅한다. | 공통 파서 `is_junyo`, 연결 생성의 `junyo` 관계. 뒤 문장의 준용이 앞 문장 인용에 섞이지 않는 시험 포함. 치환 문구나 준용의 법적 효과를 해석한 결과는 아니다. | E11 |
| 12 **별표·별지서식 번호**: `별표 n`, `별지 제n호서식`, `별지 제n호의m서식` | **시험 문구** `별표 2 제4호가목 및 나목`; **실제 표본** `「개별소비세법 시행규칙」 별지 제6호서식(부표를 포함한다), 별지 제7호서식, 별지 제7호의2서식 또는 별지 제7호의3서식` | 조문에서 별표·서식의 소유 법령과 번호로 연결한다. 국세의 가지서식 열거는 법령 소속을 유지한다. | 공통 번호 참조 + 국세 서식 보완. 일반 별표 파서는 일부 가지서식을 확인사항으로 남기며 국세의 추가 지원과 다르다. `별표 2 제4호가목` 예시는 **별표 2까지** 연결한 시험이다. 별표 안 제4호·칸의 해석 지원으로 말하지 않는다. | E12 |
| 13 **정의된 약칭·공식 짧은 이름**: `「정식명」(이하 “약칭”이라 한다) … 약칭 제x조` | **시험 문구** `「국가회계기준에 관한 규칙」(이하 “규칙”이라 한다) 제3조제2항`, `규칙 제3조부터 제5조까지`, `「공정거래법」 제9조` | 본문에 선언된 약칭 또는 수집 메타데이터의 공식 짧은 이름을 정식 법령명과 연결한다. | 금융·행정규칙 공통 적용기와 명시적으로 허용한 분야에서 확인. 알 수 없는 약칭을 유사한 법령명으로 추측하지 않는다. 화면에 보여 주는 줄임말과 원문의 인용 약칭은 다른 기능이다. | E13 |
| 14 **조문 번호 없는 지침 문단**: `Ⅰ. … / 1. … 「법령명」 제x조` | **시험 문구** `Ⅰ. 첫 구분` 아래 `1. 「공공기관의 정보공개에 관한 법률」 제3조에 따른다.` | 출처를 `Ⅰ. 첫 구분 / 1.`로 기록하고 실제 법률 조문으로 연결한다. 법률에서 역인용하면 지침의 그 문단을 읽는다. | 공정거래·국고·조달·물가·보조금의 허용 프로필에서 분석. 가상의 제1조를 만들지 않는다. `전항`, `가항`, `이 지침 3.` 같은 지침 내부 문단 간 참조는 미분석이다. | E14 |

## 발표에서 먼저 보여줄 8개 장면

1. **범위 안의 숨은 조문** — `제2조부터 제8조까지`에도 제5조와 제5조의2가 들어간다. 숫자 5를 직접 찾는 방식의 한계를 보여주기 좋다(E02, 시험 문구).
2. **구식 표현도 같은 범위** — `제2조 내지 제8조`를 같은 범위로 읽는다(E02, 시험 문구).
3. **가지조문까지 이어지는 범위** — `「국세기본법」 제47조의2부터 제47조의4까지`에서 제47조의3을 대조한다(E02, 실제 부가가치세법 시행령 제114조 표본).
4. **법령명은 한 번만 써도** — `「부가가치세법」 제9조 및 제10조`의 제10조를 출처 법률이 아닌 부가가치세법으로 붙인다(E04, 시험 문구).
5. **‘같은 조’ 뒤 두 항을 모두** — `같은 조 제3항 및 제4항`을 앞의 부가가치세법 제60조에 붙이고 원문 표현도 보존한다(E06, 실제 국세기본법 제26조의2 표본; 문맥 확인).
6. **‘동항’도 출처와 대상을 유지** — `제155조제7항 … 동항제2호`를 시행령 제155조제7항제2호로 읽는다(E07, 실제 원문을 고정한 회귀 시험; 문맥 확인).
7. **한글 목이 생략된 열거** — `제20조의3제1항제2호나목 및 다목`에서 나목과 다목을 모두 기록한다(E09, 실제 소득세법 제21조 표본).
8. **별지 가지번호와 법령 소속** — 외부 시행규칙의 `별지 제7호의2서식 또는 별지 제7호의3서식`을 각각 구분한다(E12, 실제 국세기본법 시행규칙 제12조 표본; 국세 보완).

표현을 화면에 보여줄 때 **시험 문구 / 실제 표본 / 문맥 확인** 표시를 붙인다. 위 여덟 장면은 구문 처리와 근거 보존을 보여주는 예시이며, 법적 판단이나 분야 전체 정확도 점수로 설명하지 않는다.

## 부록 A — 표현별 검증 파일·시험명·표본 ID

시험명은 파일 안에서 그대로 검색할 수 있도록 완전한 이름으로 적었다. 실제 JSON 주석은 수정 전 발견 상태도 함께 보존한다. 해결 여부는 JSON의 옛 `note`만 보지 말고 [후속 국세 검증 기록](qa/tax-validation-phase2-20261004.md)과 아래 회귀 시험을 함께 본다.

| 근거 | 검증 파일과 시험명 | 실제 표본·확인한 내용 |
|---|---|---|
| E01 | [test_tax_citation_audit.py](../scripts/test_tax_citation_audit.py): `TaxCitationAuditTests.test_income_70_paragraph_2_keeps_na_mok`, `test_explicit_named_relative_and_deictic_patterns_keep_the_same_fields`, `test_branch_item_with_mok_remains_supported_by_existing_tail` | [국세 30조 주석](qa/tax-citation-samples-20261004.json): 소득세법70 `277f9bea93e15137`. 목 번호와 원문 위치, 다른 목의 불일치를 확인. |
| E02 | [test_citation_parser.py](../scripts/test_citation_parser.py): `test_naeji_range_parsing`, `test_article_range_covers`, `test_range_expansion_back_citations`, `test_citation_matches_range_subarticle`, `test_range_inherits_cross_law_name` | [추가 24조 주석](qa/tax-blind-samples-20261004.json): 부가가치세법 시행령114 `b-58e6489235ffd004`. [범위 시험](../scripts/test_citation_scope.py)의 `ScopeTests.test_branch_intervals_and_mok`도 범위 내 가지조문 확인. |
| E03 | [test_citation_scope.py](../scripts/test_citation_scope.py): `ScopeTests.test_scope_cases` | [국세 30조 주석](qa/tax-citation-samples-20261004.json): 소득세법12 `c8e61fd83a83e0b2`. 항·호의 범위 안/밖, 혼합 단위·역순·미완성 범위의 문맥 확인을 검사. |
| E04 | [test_citation_parser.py](../scripts/test_citation_parser.py): `test_enumerated_cross_law_name`, `test_enumeration_chain_survives_fillers`; [test_citation_scope.py](../scripts/test_citation_scope.py): `ScopeTests.test_scope_cases` | [국세 30조 주석](qa/tax-citation-samples-20261004.json): 국세기본법45의2 `9cb6348887f6096b`. 조문 소속 전파와 항·호의 생략 계층·열거·범위를 구분. |
| E05 | [test_relative_law_resolution.py](../scripts/test_relative_law_resolution.py): `test_same_law_resolves_to_antecedent`, `test_same_law_in_parenthetical`, `test_same_law_across_lines_and_table` | 조세특례제한법에서 발견한 타법 소속 오탐을 고정한 시험. `같은 법`의 소속과 줄바꿈이 있는 시험 문구를 확인. |
| E06 | [test_tax_relative_audit.py](../scripts/test_tax_relative_audit.py): `TaxRelativeAuditTests.test_relative_article_keeps_both_paragraphs_and_original_source_quote`, `test_relative_article_with_deictic_anchor_keeps_owner_and_source`, `test_unanchored_relative_article_does_not_invent_article_number` | [국세 30조 주석](qa/tax-citation-samples-20261004.json): 국세기본법26의2 `ec2043d0e6350fb8`. 제3항·제4항 각각 연결, 원문 보존, 제5항은 제외. 시험은 화면 상태 `review`도 확인. |
| E07 | [test_tax_relative_audit.py](../scripts/test_tax_relative_audit.py): `SameParagraphAuditTests.test_two_manually_verified_housing_references`, `test_missing_or_ambiguous_anchor_never_falls_back_to_source`, `test_closed_parenthetical_anchor_is_not_inherited_outside` | [원문부터 작성한 역인용 주석](qa/tax-reverse-source-samples-20261004.json): 대상 소득세법 시행령155, 출처156의2·156의3, `동항제2호`·`같은 항 제2호`. 해당 JSON은 별도 문자열 ID 대신 대상·출처·원문 발생 위치로 구분. |
| E08 | [test_citation_parser.py](../scripts/test_citation_parser.py): `test_deictic_parsing`, `test_deictic_resolution`, `test_citation_matches_cross_law`, `test_find_back_citations_deictic` | 시행령의 `법 제127조`를 시행령 자체127조의 역인용으로 오인하지 않는 음성대조 포함. |
| E09 | [test_tax_citation_audit.py](../scripts/test_tax_citation_audit.py): `TaxCitationAuditTests.test_income_21_item_21_keeps_enumerated_mok`, `test_named_law_chain_continues_after_enumerated_mok`, `test_numeric_mok_and_intra_references_keep_legacy_behavior` | [국세 30조 주석](qa/tax-citation-samples-20261004.json): 소득세법21 `a992c73fdf48e022`. 나목·다목 각각 확인하고 단독 목의 부모 추측은 배제. |
| E10 | [test_tax_citation_audit.py](../scripts/test_tax_citation_audit.py): `TaxCitationAuditTests.test_corporate_decree_24_keeps_ra_to_ba_range` | 법인세법 시행령24의 원문 회귀 문구. 구조화 범위의 축·시작 라목·끝 바목과 `목 범위` 확인 사유를 동시에 검사. |
| E11 | [test_junyo_tagging.py](../scripts/test_junyo_tagging.py): `test_junyo_with_regulation_phrase`, `test_range_junyo`, `test_junyo_does_not_leak_across_sentence`, `test_nearest_citation_scoping` | 파서의 `is_junyo` 태깅을 확인. [연결 생성](../core/universe_builder.py)과 [행정규칙 적용기](../core/fsc_administrative.py)는 `junyo` 관계를 저장하는 경로가 있음. |
| E12 | [test_annex_references.py](../scripts/test_annex_references.py): `AnnexReferences.test_requested_local_references_without_annex_body`, `test_same_law_requires_one_explicit_owner_in_same_paragraph`; [test_tax_citation_context.py](../scripts/test_tax_citation_context.py): `TaxAnnexContextTests.test_audited_named_forms_keep_owner_through_parenthesis_and_enumeration`, `test_branch_position_variants_and_subforms_are_distinct` | [추가 24조 주석](qa/tax-blind-samples-20261004.json): 국세기본법 시행규칙12 `b-7754d2d33841f334`. 별표 번호와 별지 번호를 확인. 별표 내부 본문 분석 시험은 아님. |
| E13 | [test_mofe_reuse.py](../scripts/test_mofe_reuse.py): `GuidanceReuseTests.test_numeric_heading_alias_range_and_real_offsets`, `test_relative_owner_cannot_leak_across_numbered_items`; [test_ftc.py](../scripts/test_ftc.py): `FtcTests.test_official_short_title_is_resolved_without_changing_display` | `규칙` 약칭 선언의 실제 위치·명시 범위·원문 span을 확인. 공식 짧은 이름과 정식명 연결을 별도 확인. |
| E14 | [test_prices_profile.py](../scripts/test_prices_profile.py): `PricesParagraphTests.test_repeated_numeric_items_keep_roman_parents_and_do_not_become_articles`; [test_ftc.py](../scripts/test_ftc.py): `FtcTests.test_real_paragraph_locations_aliases_ranges_and_unknown_targets`; [test_mofe_reuse.py](../scripts/test_mofe_reuse.py): `GuidanceReuseTests.test_missing_body_missing_target_and_internal_items_not_success` | 반복되는 숫자1을 상위 로마숫자로 구분. 출처 `source_jo`는 빈 값이고 실제 문단 위치를 보존. 역인용 읽기 행의 대상이 문단이라는 시험 포함. |

## 부록 B — 별도로 설명할 한정 지원과 문맥 후보

| 대표화한 패턴·예시 | 현재 연결 해석 | 검증 근거 | 발표할 때의 제한 |
|---|---|---|---|
| **현재 조부터 범위**: `이 조부터 제y조까지` — 실제 `이 조부터 제83조까지` | 국세의 출처 조문이 부가가치세법 시행령81임을 사용해 제81조~제83조로 구조화한다. | [test_tax_citation_context.py](../scripts/test_tax_citation_context.py): `TaxArticleContextTests.test_source_article_range_keeps_original_and_resolved_scope`, `test_article_branch_range_and_unsafe_shapes`; [추가 주석](qa/tax-blind-samples-20261004.json) `b-d5418b7a58d0fed2` | 국세 참조 보완 경로에서 확인. 번호 없는 모든 `이 조`·`이 항` 표현의 일반 지원으로 확대하지 않는다. |
| **각 호·부분·예외**: `제16조제2항 각 호`, `제16조제2항 각 호 외의 부분`, `제16조제2항제1호를 제외한다` | `각 호`는 상위 범위와 대조할 수 있다. `외의 부분`·제외·단서·본문·전단·후단·한정은 번호를 보존해도 문맥 확인으로 분류한다. | [test_citation_scope.py](../scripts/test_citation_scope.py): `ScopeTests.test_scope_cases` | 제외된 대상이 실제 적용되는지, 전단·후단의 문장 의미까지 자동 판정했다고 말하지 않는다. |
| **법령 전체 참조**: `「A법」에 따른 …`, `같은 법에 따른 …` | 특정 조문 번호가 없으면 법령·정의 참조로 저장한다. 선택 조문까지 관계가 있다고 확정하지 않고 법령 전체의 역인용 후보로 구분한다. | [test_law_universe.py](../scripts/test_law_universe.py): `UniverseTests.test_whole_law_reverse_is_optional`; [test_tax_relative_audit.py](../scripts/test_tax_relative_audit.py): `TaxRelativeAuditTests.test_relative_law_without_number_uses_preceding_anchor_only` | 법령 참조와 조문 인용을 구분. 법령 전체 후보는 기본 조문 역인용과 별도이며 넓은 범위를 보여주는 선택이 필요하다. |
| **번호 없는 모법 지시**: 실제 `법에 의한 신고`, `법 또는 다른 법률` | 국세 시행령·시행규칙에서 모법의 법령 전체 참조를 보존한다. | [test_tax_citation_context.py](../scripts/test_tax_citation_context.py): `TaxLawLevelContextTests.test_two_source_first_audited_constructions`, `test_other_unnumbered_law_words_are_outside_this_helper`; [추가 주석](qa/tax-blind-samples-20261004.json) `b-fd283e424a5fbf85`, `b-21d61f7af7c65866` | 이 두 형태의 한정 지원. `다른 법률`이 어느 법인지 추측하지 않는다. 번호 있는 역인용이 아닌 문맥 후보다. |
| **낫표 없는 정식명 전체 참조**: `공공기관의 정보공개에 관한 법률에서 정하는 범위` | 물가 문단에서 수집된 정식명과 규범 표현이 함께 있는 경우 법령 단위 근거로 기록한다. | [test_prices_profile.py](../scripts/test_prices_profile.py): `PricesBareTitleTests.test_unique_full_title_with_legal_cue_has_exact_law_level_span`, `test_no_alias_generic_name_embedded_title_or_quoted_text_guess` | 물가용 보완. `정보공개법`, `다른 법률`, 교육 목적 언급 등까지 일반화하지 않는다. |
| **항 앞 ‘제’의 비표준 생략**: 실제 `영 제95조1항` | 원문은 바꾸지 않고 별도 구조화 범위에서 제95조제1항으로 읽는다. | [test_tax_relative_audit.py](../scripts/test_tax_relative_audit.py): `OmittedJeParagraphAuditTests.test_official_corporate_rule49_literal_keeps_paragraph`, `test_only_missing_je_immediately_after_article_is_allowed` | 법인세법 시행규칙49③의 동일 공식 판본 재확인 사례. `제95조 1항`, `제95조의21항`, 단독 `1항`의 지원을 뜻하지 않는다. |
| **옛 판본 한정**: `「법인세법」(법률 제9898호 … 개정되기 전의 것을 말한다) 제44조 및 제46조` | 소속 법령·각 조문과 과거 판본 한정 문구를 보존한다. | [test_tax_relative_audit.py](../scripts/test_tax_relative_audit.py): `HistoricalAndTableQualifierAuditTests.test_historical_owner_and_editions_survive_bracketed_enumeration`, `test_historical_editions_do_not_escape_the_quoted_exception` | 옛 판본의 조문 본문을 대조했다는 뜻은 아니다. `historical-edition-not-verified`와 문맥 확인 상태를 유지한다. |
| **표 안 줄바꿈·절단 인용**: 법인세법 시행규칙49의 국세기본법47조의2~47조의5 | 선정한 전문·시행일·정확한 원문 구간이 맞는 경우에만 연결을 복원한다. | [test_tax_citation_context.py](../scripts/test_tax_citation_context.py): `TaxArticleContextTests.test_reviewed_table_positive_has_exact_source_and_full_skip_span`, `test_table_override_rejects_changed_body_even_outside_citation`, `test_table_override_rejects_wrong_law_article_or_edition` | **선정 사례 보완**. 일반적인 표 모든 행·열·산식·칸 위치 해석으로 소개하지 않는다. |
| **하이픈 조 번호**: `제7-1조` | 외환·금융의 허용 번호 체계에서 제7조의1과 구분한다. | [test_forex.py](../scripts/test_forex.py): `ForexTests.test_hyphen_and_branch_distinct` | 해당 분야 번호 체계에 한정. 국세의 조 번호나 임의 `제32조2`로 확대하지 않는다. |

## 2026-10-13 추가: 괄호·정의 문장과 조문 열거 구분

- **정의 문장 뒤 소속 전파 중단**: 지방세기본법 제93조의2의 `…외국법인을 말하며, 제153조에 따라…`에서 제153조는 앞의 법인세법을 따라가지 않고 지방세기본법 소속으로 연결한다.
- **괄호 밖의 열거 복원**: `「A법」 제3조(「B법」 제4조에 따른 …) 및 제5조`처럼 원래 열거가 이어지면 제5조의 소속은 A법으로 유지한다. 이 문구는 구조를 설명하기 위한 시험 예시다.
- **‘같은 법’과 단순 열거 구분**: 명시적인 상대 지시는 선행 법령명과 대조하되 문맥 확인 상태를 유지한다. 괄호를 넘는 모든 참조를 무조건 삭제하거나 확정하지 않는다.

엄격 인용 분석 경로의 보완이며, 모든 자연어 문맥 해석을 보장하지 않는다. [실제 공개 자료 교정과 검증 기록](qa/citation-context-weekly-20261013.md), [회귀 시험](../scripts/test_citation_ownership.py)을 함께 참고한다.

## 부록 C — 지원했다고 말하지 않을 표현

| 표현·상황 | 현재 제한과 확인 근거 |
|---|---|
| `가목 및 나목`만 있고 조·항·호가 없음 | 부모 번호를 생성하지 않는다. E09의 `test_numeric_mok_and_intra_references_keep_legacy_behavior`에서 단독 한글 목 입력의 파싱 결과가 빈 목록임을 확인. |
| `제3항`, `제2호`만 있고 조 번호가 없음 | 공통 파서는 부분 토큰을 잡지만 그것만으로 다른 조문의 확정 연결을 만들지 못한다. E09의 같은 시험에서 빈 조 번호, E03에서 독립 항의 `review` 분류 확인. |
| 선행 번호 없는 `같은 조 제3항`, `같은 항 제2호`, `동항제2호` | 국세 연결 시험에서 조·항을 추측하지 않는다. E06 `test_unanchored_relative_article_does_not_invent_article_number`, E07 `test_missing_or_ambiguous_anchor_never_falls_back_to_source`. |
| 선행 법령 없는 `같은 법 제29조` | 공통 파서에는 출처 법령으로 폴백하는 기존 동작이 있다. [test_relative_law_resolution.py](../scripts/test_relative_law_resolution.py)의 `test_same_law_falls_back_when_no_antecedent`가 이를 명시한다. 모든 상대 지시가 항상 정확히 해결된다고 발표하지 않는다. |
| `전항`, `전조`, `다음 항`, `같은 호`만으로 대상을 추론 | 숫자 인용의 독립 연결 지원으로 목록에 올리지 않는다. 공통 파서의 현재 패턴에는 전항·전조·다음 항·같은 호 전용 해석이 없다. 일부 범위 분석에서는 확인 신호만 남는다. E14처럼 지침 내부 문단 참조도 미분석이다. |
| `별표 1부터 별표 4까지`, `별표 1-2`, 알 수 없는 소유 법령 | 확정 번호 연결로 만들지 않고 확인사항으로 남기는 시험. [test_annex_references.py](../scripts/test_annex_references.py)의 `AnnexReferences.test_partial_numbers_and_ambiguous_article_enumeration_are_issues`, [test_tax_citation_context.py](../scripts/test_tax_citation_context.py)의 `TaxAnnexContextTests.test_unsupported_suffix_range_or_quotation_never_becomes_partial_number`. |
| 별표 내부 제4호·가목, 서식의 칸·산식·금액 | 이 문서는 조문→별표·서식 번호→공식 원본 연결을 설명한다. 일부 별표 본문 분석 기능과 구분하며, 번호 연결 사례로 표 내부 내용·적용조건·금액 계산의 일반 지원을 주장하지 않는다. E12의 시험은 `body_analysis`가 없음을 확인한다. |
| 미수집 대상·판본 부재·의미만 비슷한 법률 | 원문 인용의 추출과 본문을 읽을 수 있는지는 다르다. 미수집 상태를 보존하며 다른 번호로 대체하지 않는다. E13·E14의 대상 부재 시험과 [추가 검증의 미검증 범위](qa/tax-validation-phase2-20261004.md)를 확인. |

## 이번 문서 작성에서 확인한 시험 범위

2026-10-05 오프라인에서 표현과 반례를 확인했다. `unittest` 106개와 공통 인용 파서·상대 법령명 해석·준용 태깅의 함수 시험 27개, **총 133개 시험이 모두 통과**했다. 문서에 연결한 53개 로컬 구현·검증 파일 링크의 존재도 확인했다. 시험 기록은 `output/citation-expression-verification/report.json`과 같은 폴더의 `unittest.log`에 있다.

이 133개는 발표 목록과 연결된 선택 시험이며 저장소 전체 회귀 시험이나 전체 수집 자료의 재감사 수가 아니다. 실제 원문 사례의 검증 결과는 [2026-10-04 추가 검증 기록](qa/tax-validation-phase2-20261004.md)을 근거로 삼았으며, 이번 문서 작성에서 그 전체 사이트 검사를 다시 실행한 것은 아니다. 인용 해석의 완전성·누락률·법적 정답을 보증하지 않는다.
