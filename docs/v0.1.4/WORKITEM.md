# v0.1.4 작업 항목 (V-Model 절차 기록)

작성 2026-11-08. 근거: PLAN.md §v0.1.4, DECISIONS D32~D35, 사용자 지시(정책 A·B·C, 2026-11-08).
브랜치 `v0.1.4-dev`(기준 `main` = `e6fc892`, 태그 `v0.1.3` = `0df13b7`).

## 0. 이 작업에 V-Model을 적용하는 방식

사용자 지시는 "이번 작업 자체에도 G1~G5 워크플로우를 적용하라"이다. SPEC §5.8(순환 검증 금지)은 "DevKit 개발 자체를 DevKit Validator로 승인하지 않는다"고 정한다. 두 요구를 함께 지키기 위해 **절차는 G1~G5를 따르되, 판정은 독립 하네스가 한다.**

| DevKit 단계 | 이 작업에서 하는 일 | 산출물 |
|---|---|---|
| G1 Requirements | 항목별 요구사항(REQ)·수용 기준(AC) | 이 문서 §1~§3의 REQ/AC |
| G2 Architecture | 변경 영향 분석(바뀌는 모듈·바뀌지 않는 계약) | §4 |
| G3 Design & Test Planning | 상세 설계, 구현 전 테스트 명세(TEST ↔ 하네스 메서드) | §5, §6 |
| G4 Implementation | 최소 수정, ruff 정적 분석, Verification Agent 독립 검토(별도 컨텍스트, 읽기 전용) | 커밋, §8 |
| G5 Unit Verification | 0.1.3 릴리스 대상 RED → 수정본 GREEN → 전체 회귀 | `test-results/v0.1.4/*.log`, §7 |
| (확인) | Validator·Audit 확인: drill-3 실제 원장 복사본에서 status·audit·verify-evidence | §7 |

RED는 "작성자가 고치기 전에 실패했다"가 아니라 **불변 릴리스 `v0.1.3` 코어를 대상으로 실패한다**로 확인한다. `tests/helpers.py`의 `VMODEL_TEST_PLUGIN`으로 대상 플러그인을 바꾸고, `scripts/red_green.py`가 클래스 이름 규칙으로 기대 결과를 기계적으로 대조한다.

- `...Red` 클래스: 0.1.3에서 모든 메서드가 FAIL(assertion)해야 하고 0.1.4에서 통과해야 한다.
- `...Char` / `...Invariant` 클래스: 0.1.3과 0.1.4 모두에서 통과해야 한다(현재 동작 고정, 불변식).
- `...Accept` 클래스: 0.1.4에서만 의미가 있는 인수 테스트(교차 버전 등). RED 대조에서 빠진다.

## 1. F1 — 결함 검증 상태의 정확성 (D32 권장안 C)

배경: `verified_by`는 "인용된 실패 이후 그 Gate의 첫 PASS"라는 과거 사실이다. 0.1.3은 이후 입력이 바뀌어 Gate가 STALE이 돼도 `[open; verified by R00013]`을 표시했다(drill-3 P-F1).

- REQ-F1-1 status JSON의 DEFECT마다 `closure_state`(OPEN, FIX_APPLIED, VERIFIED, CLOSED), `closure_gate`, `closure_gate_status`를 둔다. defects.json 스키마와 enum(`open`/`fixed`)은 바꾸지 않는다.
  - AC-F1-1a 검증 전 주장 `open` → OPEN, 주장 `fixed` → FIX_APPLIED.
  - AC-F1-1b 수정 후 그 Gate PASS, 현재도 PASSED → CLOSED, `closure_gate_status` PASSED.
- REQ-F1-2 `verified_by`가 있어도 그 Gate가 지금 PASSED가 아니면 VERIFIED로 표시하고, 현재 Gate 상태와 재검증 필요를 함께 보인다. 과거 `verified_by`를 현재도 유효한 것처럼 표시하지 않는다.
  - AC-F1-2a CLOSED 뒤 소스 1바이트 변경 → G4·G5 STALE → VERIFIED, `closure_gate_status` STALE, 텍스트 줄이 `DEFECT-001 VERIFIED`로 시작하고 `G5 is now STALE`·`re-verify`를 포함한다(P-F1 재현).
  - AC-F1-2b 상위 산출물(tests.json) 변경 → CLOSED가 아니다.
- REQ-F1-3 주장 `open`인데 원장상 검증됨 → 불일치 주석(`claim_note`).
- REQ-F1-4 report.md가 status와 같은 종료 상태를 낸다.
- REQ-F1-5 표시 전용. Gate 판정·원장 기록·manifest 계산은 바꾸지 않는다. 0.1.x defects.json·원장을 그대로 읽는다.

## 2. F2 — Guard 오탐 수정 (D34)

배경: `WRITE_VERBS`의 `>`·`N>` 패턴이 `/dev/null`로 가는 리디렉션도 쓰기로 봐서, verifier는 `.vmodel`과 무관한 `cat src/x.py 2>/dev/null`도 거부됐다. 착수 중 bash 실측으로 **반대 방향의 빈틈**도 확인했다. 0.1.3 guard는 `echo x &> .vmodel/state/ledger.jsonl`, `echo x >& .vmodel/...`, `echo x 1>&파일`을 쓰기로 보지 않는다(bash는 실제로 파일을 만든다). `&>/dev/null`을 허용하면서 이 빈틈을 두면 보호 수준이 약해지므로 같은 항목에서 막는다.

- REQ-F2-1 대상이 정확히 `/dev/null`인 리디렉션(`>`, `>>`, `N>`, `N>>`, `&>`, `&>>`, `>&`, 연산자 뒤 공백·탭 허용)은 쓰기 판정에서 뺀다. `/dev/null` 바로 뒤는 공백, 문자열 끝, `;`, `&`, `|`, `)`만 허용한다.
  - AC-F2-1a 메인 세션 `cat .vmodel/work-items/WI-001/defects.json 2>/dev/null`, `ls .vmodel/work-items >/dev/null 2>&1 && echo ok` 허용.
  - AC-F2-1b verifier `cat src/textstats/wordfreq.py 2>/dev/null` 허용.
  - AC-F2-1c `2> /dev/null`, `&>/dev/null`, `&>> /dev/null`, `>>/dev/null`, `1>/dev/null`, `>& /dev/null` 허용.
- REQ-F2-2 파일로 가는 `&>`, `&>>`, `>&word`, `N>&word`(word가 숫자나 `-`가 아님)를 쓰기로 판정한다. fd 복제(`2>&1`, `>&2`, `2>&-`)는 쓰기가 아니다.
  - AC-F2-2a `echo x &> .vmodel/state/ledger.jsonl`, `echo x >& .vmodel/state/ledger.jsonl`, `echo x >&.vmodel/evidence/...`, `echo x 1>&.vmodel/state/head.json` 거부.
  - AC-F2-2b verifier `cat src/... &> notes.txt`, `cat src/... >& notes.txt` 거부. verifier `2>&1 | head`, `>&2`, `2>&-`, `1>&2` 허용.
- REQ-F2-3 그 밖의 차단 규칙(보호 경로, verifier 읽기 전용, 저장소 전체 삭제, VModel 홈, Core 경로, 사용자 전용 명령, review-submit)은 그대로이며 `/dev/null` 리디렉션을 붙여도 계속 차단된다.
  - AC-F2-3a 두 번째 리디렉션(`>/dev/null > .vmodel/x`), 복합 명령(`; `, `&&`, `|` 뒤의 쓰기), `tee`, `cp`, `rm`, `sed -i`, `python -c`, heredoc 쓰기는 `/dev/null`이 붙어도 거부.
- REQ-F2-4 해석이 불확실하면 기존처럼 쓰기로 본다. `/dev/null` 뒤에 따옴표·백틱·`$`·`#`·`/` 등이 붙어 다른 경로가 되는 경우(bash 실측: `/dev/nullx`, `/dev/nully`, `/dev/null#c`), 따옴표로 감싼 `"/dev/null"`, `>|`.
- REQ-F2-5 Windows `NUL`, PowerShell `$null`은 이번 범위 밖이다(기존 차단 유지). Bash 도구에서 `$null`은 변수라 다른 경로가 될 수 있고, `NUL`은 Linux에서 일반 파일이다.

## 3. F3 — 실패 TEST 증거 정확성 (D35 P1, 정책 A·B·C)

- REQ-F3-1 유효한 실패 증거 = 같은 WI의 서명된 gate 기록 중 FAILED, 또는 BLOCKED(`three_consecutive_identical_failures`). 재작업 전제 조건(needs_defect)과 같은 정의. 그 밖의 인용(원장에 없음, 다른 WI, gate 기록 아님, PASSED, REVIEW_REQUIRED, 환경 BLOCKED)은 `ERROR [invalid_citation]`이고 `failing_tests`·`verified_by` 계산에서 뺀다.
  - AC-F3-1a PASSED 기록만 인용 → 무효 인용 오류, 실패 TEST 없음, `verified_by` 없음.
  - AC-F3-1b [실패 기록, 나중 PASSED 기록] 혼합 → `verified_by`는 실패 기록 Gate의 첫 PASS(0.1.3은 엉뚱한 G4 PASS를 표시).
  - AC-F3-1c REVIEW_REQUIRED, 환경 BLOCKED(misconfigured) 인용 → 무효 인용.
  - AC-F3-1d 없는 ID, 다른 WI, 리뷰 기록 → 무효 인용(`unknown_records`도 호환을 위해 유지).
  - AC-F3-1e(특성) 3회 동일 실패 BLOCKED 기록은 유효하고 TEST별 결과를 가진다.
- REQ-F3-2 TEST별 결과(정책 B): 테스트를 실행한 Gate(G5) 기록에서 `executed_tests`가 없거나 비면 대상 TEST 전부, G5.TEST_MAPPING이 `not executed`로 적은 TEST는 그 ID만 UNKNOWN. G1~G4 기록은 N/A(경고 없음). 판정은 서명된 기록만 쓴다.
  - AC-F3-2a JUnit 없이 실패한 G5(종료 코드 1, 결과 파일 없음) → 모든 unit TEST UNKNOWN, 텍스트에 `UNKNOWN`, `failing tests (ledger): -`가 아님.
  - AC-F3-2b 일부만 실행된 G5 실패(`-x`로 첫 실패에서 중단) → 실패 TEST와 UNKNOWN TEST를 따로 표시.
  - AC-F3-2c G4 리뷰 reject 인용 → N/A, UNKNOWN 경고 없음.
- REQ-F3-3 추적성 경고: 미연결 실패 TEST `WARNING [unlinked_failing_test]`, UNKNOWN `WARNING [unknown_test_result]`. Gate는 막지 않는다(D33·D35 대안 1).
- REQ-F3-4 무결성 오류(정책 A) `ERROR [evidence_integrity]`: 원장 무결성 실패(서명·체인·head·앵커) → 인용을 확인할 수 없음(무효 인용으로 바꿔 적지 않는다). 인용된 유효 실패 기록 또는 `verified_by` 기록의 증거 파일이 원장 해시·서명과 다르거나 없음 → 그 결함의 `verified_by`를 인정하지 않는다(`verification_withheld`). 원장은 고치지 않는다.
  - AC-F3-4a 인용된 실패 기록의 `stdout.bin` 변조 → 결함에 무결성 오류(무효 인용과 다른 분류), audit FAILED 유지.
  - AC-F3-4b 검증 PASS 기록의 증거 변조 → CLOSED가 아니고 `verified_by` 없음, 무결성 오류.
  - AC-F3-4c 원장 위조 → 결함에 무결성 오류 1건, 무효 인용 오류 없음, 모든 Gate BLOCKED 유지.
- REQ-F3-5 같은 분류 이름을 status JSON(`errors`·`warnings`, WI `defect_checks`)·status 텍스트·lint·report가 쓴다. lint 종료 코드는 오류나 경고가 하나라도 있으면 1(정책 C). lint 출력의 모든 문제 줄에 `ERROR`/`WARNING`을 붙인다.
  - AC-F3-5a report에 `## Defect trace check` 절이 항상 있고, 항목이 없으면 `None`.
  - AC-F3-5b 경고가 있는 PARTIALLY_VERIFIED에서도 누락 TEST가 report에 나열된다. status WI 줄에 오류·경고 개수.
- REQ-F3-6 rework·start 스킬의 최종 보고에 "결함 추적 점검의 ERROR·WARNING을 빠짐없이 옮긴다".
- REQ-F3-7 Gate 판정, 원장 기록 형식·개수, manifest 계산은 0.1.3과 같다. 무효 인용만 있는 DEFECT는 지금처럼 재평가 전제 조건을 통과하지 못한다.

## 3-1. 버전·증거 관리 (지시 §5)

- REQ-V-1 0.1.3이 서명한 원장·증거를 0.1.4가 그대로 검증한다(audit OK, verify-evidence OK). 기존 기록의 `validator.version`·`core_hash`는 0.1.3 값 그대로이며, 어떤 명령도 기존 원장 줄이나 증거 파일을 다시 쓰지 않는다.
- REQ-V-2 재고정(`lock --accept-current`, 사용자 TTY) 뒤 이전 PASS는 STALE("validator core changed")이고, 재검증한 새 기록은 0.1.4 버전·해시를 갖는다. 이전 PASS를 새 해시로 다시 인정하는 경로는 만들지 않는다.
- REQ-V-3 0.1.0~0.1.3 릴리스 사본·기록과 `v0.1.3` 태그는 바꾸지 않는다.

## 4. 변경 영향 분석

바뀌는 것
- `validator/vmodel_validator/gates.py`: `defect_trace()`(인용 분류, TEST별 결과, 무결성, verified_by 기준) — Gate 평가 함수, `preconditions()`, `compute_manifest()`, `run_gate()`, 원장 기록 형식은 **바꾸지 않는다**.
- `runner.py`: 증거 기록 검사 `check_evidence()`(cli의 `_check_evidence`를 옮김, 동작 동일). audit·verify-evidence·결함 점검이 같은 함수를 쓴다.
- `status.py`: 종료 상태 파생, 결함 줄·WI 줄 표시, report의 결함 절과 새 점검 절.
- `cli.py`: lint 출력 분류, audit·verify-evidence는 옮긴 함수 호출.
- `hook.py`: 쓰기 판정 전 `/dev/null` 리디렉션 제거, `&>`·`>&word` 쓰기 판정 추가.
- `skills/rework`, `skills/start`: 최종 보고 문구. `__init__.py`·`plugin.json` 버전 0.1.4.

영향받는 소비자
- SessionStart 훅(`render_status` 출력을 주입) — 결함 줄 형식이 바뀐다. 텍스트 파싱하는 코드는 없다.
- status JSON의 기존 키(`verified_by`, `failing_tests`, `unlinked_failing_tests`, `unknown_records`, `failing_tests_by_record`)는 유지한다. `failing_tests_by_record`·`failing_tests`는 유효 인용만 담는다(F3).
- Core 해시가 바뀐다 → 설치 프로젝트는 재고정 필요, 기존 PASS는 한 번 STALE(SPEC §11 업그레이드 절차 그대로).
- 기존 하네스 103개는 고치지 않는다. 기존 테스트가 고정한 문자열(`DEFECT-001 [fixed — verified by R…]`, `does not link failing test(s) of R…`, `failing tests in R… (from the signed ledger): …`)을 유지한다.

## 5. 상세 설계

F1
- `closure_view(dt, gate_statuses)`: `verified_by`가 없으면 주장 `fixed` → FIX_APPLIED, 그 밖 → OPEN. 있으면 `closure_gate`(유효 인용 중 마지막 실패 기록의 서명된 gate) 현재 상태가 PASSED → CLOSED, 아니면 VERIFIED. 주장 `open` + VERIFIED/CLOSED → `claim_note`.
- `project_status()`가 Gate 상태를 계산한 뒤 붙인다. report는 `project_status()`의 결함 목록을 그대로 쓴다(재계산하지 않음).
- 텍스트: `DEFECT-001 CLOSED [claimed fixed; verified by R00013, G5 PASSED] …`, `DEFECT-001 VERIFIED [claimed fixed; verified by R00013 but G5 is now STALE: re-verify] …`.

F2
- `DEVNULL_REDIRECT = (?:&>>?|>&|[0-9]*>>?)[ \t]*/dev/null(?=$|[\s;&|)])`, 일치 부분을 공백 하나로 바꾼 뒤 `WRITE_VERBS` 판정. 다른 판정(홈·Core 표지, 사용자 전용, 저장소 삭제)은 원문으로 한다.
- `WRITE_VERBS`에 `&>`와 `>&(?![ \t]*(?:[0-9]+|-)(?=$|[\s;&|)<>]))` 추가.

F3
- 인용 분류 `_classify_citation(entry|None, wi)` → valid, reason. 유효 기록마다 `test_results` = `recorded`/`partial`/`unknown`(G5) 또는 `not_applicable`(G1~G4), `failing_tests`, `unknown_tests`(TEST_MAPPING `TEST-x: not executed`).
- `defect_trace(entries, wi, defects, evidence_check=None, ledger_error=None)`: `evidence_check(path, sha)`가 문제 목록을 돌려주면 `evidence_integrity` 오류. 원장 오류면 인용 확인 없이 무결성 오류 1건.
- 분류 이름(JSON 값 = 텍스트 라벨): 오류 `evidence_integrity`, `invalid_citation` / 경고 `unlinked_failing_test`, `unknown_test_result`. 텍스트는 `ERROR [<분류>] …`, `WARNING [<분류>] …`.
- lint: 기존 문제(스키마·추적 끊김·원장)는 `ERROR`, 결함 점검은 위 분류. 요약 `N problem(s): E error(s), W warning(s) (not a gate decision)`, 종료 코드 정책 불변.

## 6. 테스트 명세 (구현 전 작성, 하네스 메서드와 1:1)

| TEST | 수용 기준 | 하네스 |
|---|---|---|
| T-F1-01 | AC-F1-1a | `test_defect_closure.DefectClosureRed.test_open_and_fix_applied_before_verification` |
| T-F1-02 | AC-F1-1b | `…DefectClosureRed.test_closed_after_the_gate_passes` |
| T-F1-03 | AC-F1-2a | `…DefectClosureRed.test_source_change_after_closure_shows_verified_not_closed` |
| T-F1-04 | AC-F1-2b | `…DefectClosureRed.test_upstream_artifact_change_keeps_it_from_closed` |
| T-F1-05 | REQ-F1-3 | `…DefectClosureRed.test_claim_open_but_verified_is_annotated` |
| T-F1-06 | REQ-F1-4 | `…DefectClosureRed.test_report_shows_the_same_closure_state_as_status` |
| T-F1-07 | REQ-F1-5 | `…DefectClosureInvariant.test_display_commands_do_not_touch_ledger_or_manifests` |
| T-F2-01 | AC-F2-1a,c | `test_guard_redirects.GuardDevNullRed.test_main_session_reads_with_output_discarded` |
| T-F2-02 | AC-F2-1b | `…GuardDevNullRed.test_verifier_reads_with_output_discarded` |
| T-F2-03 | AC-F2-2a | `…GuardFileRedirectRed.test_ampersand_redirects_into_protected_paths_denied` |
| T-F2-04 | AC-F2-2b | `…GuardFileRedirectRed.test_verifier_ampersand_redirects_to_files_denied` |
| T-F2-05 | AC-F2-3a, REQ-F2-4 | `…GuardWritesChar.test_writes_into_protected_paths_stay_denied` |
| T-F2-06 | REQ-F2-3 | `…GuardWritesChar.test_verifier_writes_stay_denied` |
| T-F2-07 | REQ-F2-3 | `…GuardWritesChar.test_other_rules_ignore_devnull_suffix` |
| T-F2-08 | AC-F2-2b | `…GuardWritesChar.test_fd_duplication_is_not_a_write` |
| T-F3-01 | REQ-F3-3, F3-5 | `test_defect_evidence.DefectEvidenceRed.test_unlinked_failing_tests_are_trace_warnings_everywhere` |
| T-F3-02 | AC-F3-1a | `…DefectEvidenceRed.test_passed_record_alone_is_an_invalid_citation` |
| T-F3-03 | AC-F3-1b | `…DefectEvidenceRed.test_mixed_citation_closes_on_the_failure_gate` |
| T-F3-04 | AC-F3-1c | `…DefectEvidenceRed.test_review_required_record_is_an_invalid_citation` |
| T-F3-05 | AC-F3-1c | `…DefectEvidenceRed.test_environment_blocked_record_is_an_invalid_citation` |
| T-F3-06 | AC-F3-1d | `…DefectEvidenceRed.test_missing_foreign_and_non_gate_records_share_the_category` |
| T-F3-07 | AC-F3-2a | `…DefectTestResultsRed.test_g5_failure_without_junit_is_unknown_not_dash` |
| T-F3-08 | AC-F3-2b | `…DefectTestResultsRed.test_partially_executed_g5_separates_failing_and_unknown` |
| T-F3-09 | AC-F3-2c | `…DefectTestResultsRed.test_g4_review_reject_is_not_applicable` |
| T-F3-10 | AC-F3-4a | `…DefectIntegrityRed.test_tampered_failure_evidence_is_an_integrity_error` |
| T-F3-11 | AC-F3-4b | `…DefectIntegrityRed.test_tampered_verification_evidence_withholds_closure` |
| T-F3-12 | AC-F3-4c | `…DefectIntegrityRed.test_forged_ledger_is_one_integrity_error_not_invalid_citations` |
| T-F3-13 | AC-F3-5a,b | `…DefectEvidenceRed.test_report_always_has_the_defect_trace_check_section` |
| T-F3-14 | REQ-F3-6 | `…SkillReportingRed.test_final_report_steps_carry_errors_and_warnings` |
| T-F3-15 | AC-F3-1e | `…DefectEvidenceChar.test_three_strike_blocked_record_is_valid_failure_evidence` |
| T-F3-16 | REQ-F3-7 | `…DefectEvidenceChar.test_invalid_citations_alone_do_not_satisfy_the_rework_precondition` |
| T-V-01 | REQ-F1-5, F3-7 | `test_version_compat.GateDecisionInvariant.test_same_history_gives_the_same_gate_decisions` |
| T-V-02 | REQ-F3-7 | `…GateDecisionInvariant.test_manifest_hashes_are_computed_identically` |
| T-V-03 | REQ-V-1, V-2 | `…OldEvidenceAccept.test_013_ledger_and_evidence_verify_under_014` |

## 6-1. 검토 후 추가한 테스트 (§8의 지적을 재현한 것)

| TEST | 근거 | 하네스 |
|---|---|---|
| T-F2-09 | 검토 F2-1 (동사·플래그 사이 리디렉션) | `test_guard_redirects.GuardFileRedirectRed.test_redirection_between_verb_and_flag_denied`, `GuardWritesChar.test_devnull_between_verb_and_flag_stays_denied` |
| T-F2-10 | 검토 F2-4, REQ-F2-5 | `…GuardWritesChar.test_non_bash_tools_keep_the_old_rule` |
| T-F2-11 | 검토 F2-1·2, REQ-F2-3·4 | `…GuardDifferentialAccept.test_no_write_detection_is_lost_except_pure_devnull_redirections` (0.1.3 대비 차등) |
| T-F3-17 | 검토 F3-2 / F1-1 | `test_defect_evidence.DefectEvidenceReviewRed.test_multi_gate_citation_is_not_verified_by_an_upstream_pass`, `test_defect_closure.DefectClosureReviewRed.test_multi_gate_failure_is_not_closed_by_the_upstream_pass` |
| T-F3-18 | 검토 F3-1 | `…DefectEvidenceReviewRed.test_malformed_evidence_record_is_an_integrity_error_not_a_crash` |
| T-F3-19 | 검토 F3-3 | `…test_duplicate_citations_count_once`, `…test_three_strike_chain_counts_a_missing_link_once` |
| T-F3-20 | 검토 F3-4 | `…test_defect_without_citations_is_an_invalid_citation` |
| T-F3-21 | 검토 F3-8 | `…test_forged_or_truncated_ledger_is_reported_in_lint_and_report`, `…test_withheld_verification_is_named_in_status_and_report`, `…test_counts_agree_across_status_lint_and_report`, `DefectTestResultsRed.test_unknown_results_are_named_in_lint_and_report`, `DefectEvidenceReviewChar.test_clean_defect_lint_exits_zero` |
| T-F1-08 | 검토 F1-2·3·4·6 | `test_defect_closure.DefectClosureReviewRed.*` (재실행 후 현재 기록, PASS 뒤 실패, 원장 실패 UNKNOWN, report의 claim note, SessionStart 출력), `DefectClosureBlockedRed.test_blocked_gate_does_not_say_re_verify` |

## 7. 결과
(최종 수치는 TEST_RESULTS §10)

## 8. 독립 검토 (Verification Agent, 별도 컨텍스트, 저장소 읽기 전용)

검토자에게는 결론이 아니라 요구사항(이 문서)·diff·실행 방법만 넘겼다. 지적은 직접 재현해 사실인 것만 RED 테스트로 고정한 뒤 고쳤다(재현 못 한 것, 사용자 결정 사항은 고치지 않음).

F2 (커밋 `68f64e7` 전 작업 트리)
- 주요, 사실 확인: `sed >/dev/null 2>&1 -i … .vmodel/state/ledger.jsonl`류를 0.1.3은 막았는데 첫 수정본은 통과시켰다. bash에서 실제로 원장이 바뀌었다(abc→Xbc). → 비쓰기 리디렉션을 모두 정규화한 뒤 판정.
- 부, 사실 확인: `sh -c 'ls 2>&1'` 같은 새 오탐, `/dev/null\r`, PowerShell에서 `/dev/null`이 `C:\dev\null` → 각각 수정.
- 재검토: 퍼저 2,483건에서 0.1.3 대비 손실 0, 새 오탐 1종(`>&2` 바로 뒤 따옴표)은 bash에서 `>&2"y"`가 파일을 만들어 불확실 → 차단 유지(알려진 오탐). 0.1.3부터 있던 `x2>&파일` 빈틈을 추가로 찾아 수정(bash로 파일 생성 확인).

F3 (커밋 `14f46b5`)
- 주요, 사실 확인: 형식이 깨진 증거 record.json으로 status·lint·report가 종료 코드 2(TypeError). → 수정.
- 주요, 사실 확인: G5 실패와 G4 실패를 함께 인용하면 G4 재PASS가 `verified_by`(0.1.3부터 있던 기준 선택). → 가장 하위 실패 Gate 기준.
- 부: 3회 사슬 중복 경고, 인용 없는 결함, 원장 오류 시 `unknown_records` 의미 변화, 반복 해싱. → 수정. 테스트 공백 → §6-1.
- 지적 중 "로그가 dirty 작업 트리에서 생성" → 최종 RED/GREEN 로그는 커밋된 상태에서 다시 만든다(TEST_RESULTS §10).
- 재검토(`817b9aa`): 지적 1~4 해결. 새 회귀 1건(결과 있는 오래된 실행이 최근 실행의 UNKNOWN을 가림, 사실 확인) → `4c13447`. 재재검토: 해결, 경고 `records`에 대체된 실행이 남는 표현 문제 → `test_unknown_warning_names_only_the_runs_that_still_decide`(4c13447에서 실패 확인) 후 수정.
- F1 재검토(`817b9aa`): 지적 1~4 해결, 회귀 없음.

F1 (커밋 `2d4f5c6`)
- 주요, 사실 확인: 위 F3 주요 2와 같은 원인으로 G5가 FAILED인데 CLOSED 표시. → 같은 수정.
- 부: 재실행 뒤 옛 PASS만 표시, 원장 위조 시 "아직 검증 안 됨" 단정, BLOCKED인데 re-verify 안내. → 수정(현재 기록 표시, UNKNOWN, 차단 해소 안내).
- 반영 안 함: VERIFIED 이름 변경 제안(사용자가 정한 상태 이름. 사용자 결정 사항으로 보고).
