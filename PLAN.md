# PLAN

현재 목표: **v0.2.0 릴리스 후보(G6 Integration Verification)** — 사용자 결정 D1~D8(2026-11-09)로 구현·검증 완료, 사용자 확정(병합·태그) 대기(브랜치 `g6-dev`, D42, `docs/g6/WORKITEM.md`, TEST_RESULTS §14). 확정 버전은 0.1.5(태그 `v0.1.5`, `main`). 원격 푸시·유료 E2E는 승인되지 않았다.

| 마일스톤 | 내용 | 완료 기준 (테스트) | 상태 |
|---|---|---|---|
| M0 | 환경 조사, SPEC/DECISIONS 확정 | SPEC.md·DECISIONS.md 작성, 환경 사실 기록 | 완료 |
| M1 | WI 모델, 스키마, 상태 머신, 추적성, G1~G3 | 하네스: 스키마·ID·추적·리뷰 해시·STALE(산출물)·T10·T11 | 완료 |
| M2 | G4~G5, Test Runner, 증거, 해시·STALE, 재작업 루프 | 하네스: T05~T09, T12, T13, T17, 3회 실패 BLOCKED, 인코딩 | 완료 (+독립 리뷰 반영 하드닝) |
| M3 | Skills, Subagents, Hooks, 패키징, 설치/제거/버전 | 하네스: guard 훅 판정, 설치·제거·T15·T16, `claude plugin validate`, 실제 훅 동작(헤드리스 haiku ≤4회) | 완료 |
| M4 | 샘플 프로젝트 E2E | 스크립트 E2E(T01~T18 하네스), Windows 실행(T18), 실제 Claude 세션 3회(sonnet, 회당 $4 상한), 새 세션 상태 복원(T14) | 완료 (TEST_RESULTS §3) |
| R0.1.3 | 재작업 결함 F1~F4 수정, 실제 재작업 세션 검증 | 하네스 103/103(WSL), Windows 실패 0, drill-3 실제 세션 1회, audit OK | 완료, 태그 `v0.1.3` |
| R0.1.4 | 결함 검증 상태 표시, guard 읽기 오탐, 실패 TEST 추적·증거 참조 (아래 §v0.1.4), 표시 상태 6종(D37), 실제 세션 1회 | 재현 테스트 RED 확인 후 수정, 기존 하네스 포함 전체 통과, Gate 판정 불변, 새 릴리스, 실제 세션에서 guard 우회 0 | 완료(2026-11-09, TEST_RESULTS §10·§11, DECISIONS D36·D37), 태그 `v0.1.4`, main fast-forward. 푸시는 미승인 |
| R0.1.5 | 업그레이드 시 DevKit 권한 규칙 이동(D38) | 0.1.4 릴리스 대상 RED, GREEN, 전체 회귀, 독립 검토, 실제 릴리스 사본 0.1.4 → 0.1.5 재현 | 완료(2026-11-09, TEST_RESULTS §12·§13, D38·D40), 태그 `v0.1.5`, main fast-forward. 푸시는 미승인 |
| M5 | G6 Integration Verification (아래 §확장) | 하네스 + 새 픽스처(IF 있는 2컴포넌트 `pipeline`, 단일 `single`) | 구현·검증 완료, v0.2.0 후보(브랜치 `g6-dev`, D41·D42, TEST_RESULTS §14). 사용자 확정·E2E 승인 대기 |
| M6 | G7 System Verification, STANDARD WI의 COMPLETED | 하네스 + 새 샘플 | 계획 (사용자 결정 전 착수 금지) |
| M7 | Extension 실제 세션 E2E | 실제 Claude 세션(비용 승인 후) | 계획 |

## 환경 사실 (M0 조사, 2026-11-08)
- 개발 OS: WSL2 Ubuntu 24.04 (Linux 6.6), Python 3.12.3, pytest 9.0.3, ruff 사용 가능
- Windows 측: Python 3.13.14 (Microsoft Store), PowerShell 5.1, Git for Windows(Git Bash), 콘솔 코드페이지 949(ko-KR)
- Claude Code 2.1.319, claude.ai 구독 로그인. `--plugin-dir`(디렉터리/zip), `claude plugin validate|install|uninstall|update|marketplace` 지원
- 훅: 기본 fail-open, `onFailure: "block"`(2.1.295+)로 fail-closed 가능 — 실제 동작은 M3에서 직접 확인
- Python 3.11 실물은 이 PC에 없음 → 3.12/3.13에서만 실측, 3.11 호환은 코드 규칙으로만 보장(미검증 표기)

## 헤드리스 실행 예산 (사용자 승인 2026-11-08)
- 훅 동작 확인: haiku 최대 4회, 회당 `--max-budget-usd 0.5`
- 샘플 E2E: sonnet 3회, 회당 `--max-budget-usd 4`
- 전부 임시 샌드박스에서만, `--setting-sources project,local`로 사용자 전역 설정 격리

## 현재 작업
v0.1.5 확정(2026-11-09): 재고정(`lock --accept-current`)이 설치 기록의 DevKit 규칙만 새 릴리스 경로로 옮긴다(D38). 확정 검증은 TEST_RESULTS §13(D40). 확정 중 새로 확인한 사실: 업그레이드가 `.claude/settings.json`을 바꾸므로 G4 리뷰를 다시 받아야 한다(문서 정정). 실제 Claude 헤드리스 실행은 하지 않았다(비용 0).

다음: G6. 사용자가 정한 정책(명시적 integration_test 필수·대체 실행 없음, G4 준비 검토/G6 실행 증거 분리, 조건부 N/A, 기존 WI 표시 조건)을 브랜치 `g6-dev`의 `docs/g6/G6-DESIGN.md`로 구체화했다. 구현은 그 문서 §9 결정 뒤 별도 세션.

이전: 0.1.4 확정(2026-11-09). 남은 미검증은 TEST_RESULTS §6, §9.13, §11.7, §12.7, §13.7.

## 헤드리스 실행 예산 (실전 재작업 드릴, 사용자 승인 2026-11-08)
- 승인 3회만: haiku 권한 프로브 1회($0.3 상한) + sonnet S1·S2 각 1회($4 상한). 사용: $0.0025 + $0.70 + $0.33. 추가 실행은 다시 승인.

## 헤드리스 실행 예산 (0.1.3 실제 재작업 검증, 사용자 승인 2026-11-08)
- 승인: sonnet 최대 1회, `--max-budget-usd 1`, `--dangerously-skip-permissions` 금지, 임시 샌드박스만. 사용: 1회 $0.26(S3). 추가 실행은 다시 승인.

## 헤드리스 실행 예산 (0.1.4 실제 세션 검증, 사용자 승인 2026-11-09)
- 승인: sonnet 1회, `--max-budget-usd 1`, `--dangerously-skip-permissions` 금지, 독립 샌드박스, 실제 업무 프로젝트 수정 금지. 사용: 1회 $0.15(`scripts/e2e/live_session.py`, TEST_RESULTS §11.4). 추가 실행은 다시 승인.

## v0.1.4 계획 (범위 확정 2026-11-08, 구현 완료 2026-11-09)

구현 결과와 계획 대비 달라진 점은 DECISIONS D36, 검증 결과는 TEST_RESULTS §10, 요구사항·테스트 명세는 `docs/v0.1.4/WORKITEM.md`에 있다. 계획과 달라진 점: guard는 `/dev/null`만이 아니라 fd 복제·단순 입력 리디렉션도 정규화하고, 0.1.3이 놓친 `&>`·`>&파일` 쓰기를 새로 잡는다(독립 검토 결과). 결함 종료 Gate는 인용된 실패 중 가장 하위 Gate다. 원장 무결성 실패 시 종료 상태는 UNKNOWN이다. 테스트는 계획한 `test_rework_flow.py`·`test_hooks.py` 대신 새 파일 4개(`test_guard_redirects.py`, `test_defect_evidence.py`, `test_defect_closure.py`, `test_version_compat.py`)에 두었다(기존 파일 무수정).

사용자가 정한 우선순위: 1. STALE Gate에 대한 결함 검증 상태 표시 개선, 2. Guard의 읽기 명령 오탐 수정, 3. 실패 TEST 추적 및 증거 참조 정확성 개선.

공통 원칙
- 항목마다 v0.1.3 코드에서 실패하는 재현 테스트를 먼저 쓰고, 실패(RED)를 확인한 뒤 고친다. 현재 동작을 고정하는 특성 테스트는 RED가 아니라 처음부터 통과해야 하며, 그렇게 따로 표시한다.
- 기존 Gate Validator의 신뢰성을 유지한다. 세 항목 모두 Gate 판정(PASSED/FAILED/BLOCKED/STALE), 원장 기록 내용, manifest 해시 계산을 바꾸지 않는다. 항목마다 이를 확인하는 불변식 테스트를 둔다. 기존 하네스 103개는 고치지 않고 그대로 통과해야 한다.
- 세 항목 모두 Core(`validator/`, `hooks/`, `bin/`)를 바꾸므로 버전을 0.1.4로 올리고 새 릴리스를 만든다. 0.1.0~0.1.3 릴리스 사본과 기록은 건드리지 않는다.
- 설치된 프로젝트는 `vmodel lock --accept-current`(TTY)로 다시 고정해야 하고, 그때 기존 PASS가 한 번 STALE이 된다(SPEC §11 업그레이드 절차와 같다).
- 실제 Claude 세션 검증은 선택이며 비용 승인을 받은 뒤에만 한다.
- 구현 순서 메모: 1과 3은 같은 함수(`gates.py defect_trace()`)를 고친다. 1의 CLOSED/VERIFIED는 `verified_by`에 기대고, `verified_by`의 기준 기록은 3의 "유효한 실패 기록만 인정"을 따라야 맞다. 그래서 3의 유효 인용 필터를 1과 같은 변경에서 함께 넣거나 먼저 넣는다. 우선순위는 위 순서를 유지한다.

### 1. STALE Gate에 대한 결함 검증 상태 표시 개선 (D32 권장안 C)
- 문제: `verified_by`는 "인용된 실패 이후 그 Gate의 첫 PASS"라는 과거 사실이다. 이후 입력이 바뀌어 Gate가 STALE이 돼도 status와 report는 계속 `verified by R00013`을 보여 준다. drill-3 프로브 P-F1에서 G4·G5가 STALE인데 `[open; verified by R00013]`가 표시됐다(`test-results/drill/s3-drill-3/probe-f1-f2.json`).
- 원인 위치: `gates.py defect_trace()`는 원장만 보고 현재 Gate 상태를 보지 않는다. `status.py render_defect()`와 report 생성부는 그 값을 그대로 쓴다.
- 변경안: defects.json의 스키마와 enum(`open`/`fixed`)은 그대로 둔다. Validator가 표시용 종료 상태를 파생한다.
  - OPEN: `verified_by` 없음, 주장 `open`
  - FIX_APPLIED: `verified_by` 없음, 주장 `fixed`
  - VERIFIED: `verified_by` 있음, 하지만 그 Gate가 지금 PASSED가 아님(STALE·FAILED 등). "재확인 필요"와 현재 Gate 상태를 함께 표시
  - CLOSED: `verified_by` 있음, 그 Gate가 현재 해시로 PASSED(상위 Gate가 PASSED가 아니면 `gate_state`가 이미 STALE을 내므로 상위도 포함됨)
  - 주장과 파생이 어긋나면 주석을 단다(예: 주장 `open`인데 CLOSED).
  - status JSON에 `closure_state`, `closure_gate_status`를 추가하고 텍스트·report 표시를 바꾼다. Gate 판정과 manifest에는 쓰지 않는 표시 전용이다.
- 회귀 테스트(`tests/test_rework_flow.py`)
  - RED: 결함 수정 후 G5 PASS, 이어서 소스 1바이트 변경 → G4·G5 STALE → VERIFIED(CLOSED 아님), 텍스트에 현재 Gate 상태 표시 (P-F1 재현)
  - RED: 상위만 바뀜(tests.json 변경으로 G3 STALE) → G5도 CLOSED가 아님
  - RED: 결함 수정 후 G5 PASS → CLOSED, 주장 `open` + 검증됨 → 불일치 주석, 검증 전 주장 `open` → OPEN / `fixed` → FIX_APPLIED (0.1.3에는 `closure_state`가 없어서 실패)
  - RED: report.md가 status와 같은 종료 상태를 낸다
  - 불변식: 같은 시나리오에서 Gate 상태 순서, 원장 기록, manifest 해시가 0.1.3과 같다

### 2. Guard의 읽기 명령 오탐 수정 (D34)
- 문제: `hook.py`의 `WRITE_VERBS` 중 `(?<![0-9&])>(?!&)`와 `[0-9]>(?!&)`가 `/dev/null`로 가는 리디렉션도 쓰기로 본다.
- 2026-11-08 릴리스 확정 중 0.1.3 릴리스 코드의 `guard()`를 drill-3 프로젝트에서 직접 호출해 다시 확인한 범위(D34 기록보다 넓다)
  - 메인 세션: `cat .vmodel/work-items/WI-001/defects.json 2>/dev/null` 거부, `ls .vmodel/work-items >/dev/null 2>&1 && echo ok` 거부. 같은 명령에서 리디렉션만 빼면 허용
  - verifier: `.vmodel`과 상관없는 `cat src/scorestats/percentile.py 2>/dev/null`도 거부. verifier는 경로와 무관하게 쓰기 판정만으로 막기 때문이다
  - 실제 쓰기(`echo x > .vmodel/state/ledger.jsonl`, `echo x 2> .vmodel/evidence/a.txt`)는 정상 거부
- 변경안: 쓰기 판정 전에 대상이 정확히 `/dev/null`인 리디렉션(`>`, `>>`, `N>`, `N>>`, `&>`, 연산자 뒤 공백 허용)만 지운다. `/dev/null` 바로 뒤에는 공백, 문자열 끝, `;&|)`만 허용해서 `/dev/nullx`, `/dev/null/../x` 같은 변형은 계속 쓰기로 본다. Windows `NUL`과 PowerShell `$null`을 같이 다룰지는 구현 전에 정한다(다루면 같은 형식으로 테스트 추가).
- 회귀 테스트(`tests/test_hooks.py`)
  - RED(허용으로 바뀌어야 함): 위 거부 3건, `2> /dev/null`(공백), `&>/dev/null`, `>>/dev/null`
  - 특성(거부가 유지돼야 함, 0.1.3에서도 통과): `> .vmodel/state/ledger.jsonl`, `2> .vmodel/evidence/x`, `>/dev/null > .vmodel/x`(두 번째 리디렉션), `cat a >/dev/null; echo y > .vmodel/x`, `echo y >/dev/nullx .vmodel/x`, `tee .vmodel/x >/dev/null`, verifier의 `sed -i`·`rm`·소스 파일로의 `>`
  - 기존 guard 테스트 전부 그대로 통과

### 3. 실패 TEST 추적 및 증거 참조 정확성 개선 (정책 P1, D35)
현재 동작(0.1.3): DEFECT가 인용한 기록에서 실패 TEST를 꺼내 `related`와 비교한다. 빠진 것은 status·report에 "NOT linked"로 나오고 lint는 종료 코드 1을 낸다. Gate는 막지 않는다. 원장에 없는 ID, 다른 WI의 기록, gate 기록이 아닌 것(예: 리뷰 기록) 인용은 `unknown_records`로 잡혀 status에 표시되고 lint가 문제로 보고한다. 그러나 같은 WI의 실패하지 않은 gate 기록(예: PASSED) 인용은 정상 인용으로 받아들인다.

D35에 따라 바꿀 것(Gate 판정은 바꾸지 않는다)
- 미연결 실패 TEST: 지금처럼 경고. 분류를 "추적성 경고"로 붙인다.
- UNKNOWN: 인용한 실패 기록에서 TEST별 실제 결과를 확인할 수 없으면 UNKNOWN으로 표시한다. 판정은 서명 기록만 쓴다. 테스트를 실행한 Gate(현재 G5) 기록에서 `executed_tests`가 없거나 비었거나, TEST_MAPPING이 "not executed"로 적은 TEST ID가 대상이다. 지금은 이 경우 DEFECT 줄이 `failing tests (ledger): -`가 되어 "실패 TEST 없음"과 구분되지 않는다. 테스트를 실행하지 않는 Gate(G1~G4) 실패 기록은 UNKNOWN이 아니라 "해당 없음"이다.
- 무효 인용: 실패 증거로 인정하는 기록은 재작업 전제 조건(`gates.py`의 needs_defect)과 같은 정의, 즉 같은 WI의 서명된 gate 기록 중 FAILED이거나 3회 동일 실패로 BLOCKED인 것뿐이다. 그 밖의 인용(원장에 없는 ID, 다른 WI, gate 기록이 아님, PASSED·REVIEW_REQUIRED·환경 BLOCKED)은 무효 인용 오류로 표시하고, `failing_tests`와 `verified_by` 기준 기록 계산에서 뺀다. 지금 코드는 인용 중 가장 나중 기록을 종료 기준으로 써서, PASSED 기록을 함께 인용하면 그 뒤의 엉뚱한 PASS가 `verified_by`가 된다.
- 분류: "증거 오류"(무결성 오류, 무효 인용)와 "추적성 경고"(미연결, UNKNOWN)를 나눈다. 무결성 오류는 원장 서명·체인·head·앵커 불일치(지금처럼 모든 Gate BLOCKED)와 인용된 실패 기록의 증거 파일이 원장 해시와 다른 경우(지금은 audit만 잡음, 결함 줄에도 표시)다. status JSON·텍스트, lint, report가 같은 분류 이름을 쓴다. lint 종료 코드는 지금처럼 어느 쪽이든 있으면 1이고, 출력에 분류를 붙인다.
- 최종 보고: `vmodel report` 보고서에 결함 추적 점검 절을 항상 넣고 항목이 없으면 "없음"을 적는다. status의 WI 요약 줄에 오류·경고 개수를 붙인다(WI 상태 값은 그대로). rework·start 스킬의 마지막 보고 단계에 "status·report의 증거 오류와 추적성 경고를 빠짐없이 옮긴다"를 넣는다.

회귀 테스트(`tests/test_rework_flow.py`, 일부 `tests/test_integrity.py`)
- 특성: 미연결 경고 경로(기존 `test_defect_links_are_derived_from_the_ledger_and_gaps_are_flagged`, `test_unlinked_failing_tests_do_not_block_the_rework` 유지)
- RED: 미연결 항목이 "추적성 경고" 분류로 status JSON·lint·report에 나온다
- RED: JUnit 없이 실패한 G5(예: 테스트 명령이 결과 파일 없이 종료 코드 1) 인용 → 모든 대상 TEST가 UNKNOWN, `-`가 아님
- RED: 일부 TEST만 실행된 G5 실패(다른 테스트 파일 수집 오류) → 실패 TEST와 UNKNOWN TEST를 따로 표시
- 특성: G4 실패(리뷰 reject) 인용 → "해당 없음", UNKNOWN 경고가 나오지 않음
- RED: PASSED 기록만 인용 → 무효 인용 오류, 실패 TEST 없음, `verified_by` 없음
- RED: [실패 기록, PASSED 기록] 혼합 인용 → `verified_by`가 실패 기록 이후 첫 PASS
- RED: REVIEW_REQUIRED 기록, 환경 BLOCKED 기록 인용 → 무효 인용 오류. 없는 ID·다른 WI·gate 기록이 아닌 것은 지금도 `unknown_records`로 잡히므로 분류 이름만 RED
- 특성: 3회 동일 실패 BLOCKED 기록은 세 번째 FAILED 평가 자체를 BLOCKED로 바꿔 쓴 것이라(`gates.py`, `blocked_reason` 설정부) TEST별 결과를 가지고 있다. 인용하면 유효한 실패 증거이고 UNKNOWN이 아니다
- RED: 인용된 실패 기록의 증거 파일(`stdout.bin`) 변조 → 결함 줄에 무결성 오류(무효 인용·추적성 경고와 다른 분류), audit FAILED 유지
- RED: report에 결함 추적 점검 절이 항상 있음(없으면 "없음"), 경고가 있는 PARTIALLY_VERIFIED에서도 누락 TEST가 나열됨, status WI 줄에 개수
- RED: 스킬 문구(rework·start의 최종 보고에 오류·경고 전달), 기존 `SkillWording` 테스트와 같은 방식
- 불변식: 위 모든 시나리오에서 Gate 판정, 원장 기록 수, manifest 해시가 0.1.3과 같다. 무효 인용만 있는 DEFECT로는 지금처럼 재평가 전제 조건을 통과하지 못한다

### 4. v0.1.4 완료 기준
- 위 RED 테스트를 0.1.3 코드에서 먼저 실패시키고, 수정 후 기존 103개를 포함한 WSL 하네스 전체 통과, Windows(cp949) 실패 0(skip은 기존 4건만)
- `claude plugin validate --strict` 통과, `scripts/release.py`로 `dist/vmodel-0.1.4`와 `releases/vmodel-0.1.4.json` 생성, 이전 릴리스 사본·기록 불변 확인
- P-F1 재확인(모델 호출 없음): drill-3 샌드박스(이전 세션 임시 폴더, 서명 키 포함)가 남아 있으면 그 복사본에서 P-F1을 다시 돌려 VERIFIED 표시를 확인한다. 없어졌으면 하네스의 같은 시나리오 테스트로 대신한다. 커밋된 사본 `test-results/drill/s3-drill-3/`은 서명 키가 없어 서명 검증을 거치는 status에 쓸 수 없다.
- SPEC §7(재작업 루프)과 표시 설명, DECISIONS(D35 구현 결과), TEST_RESULTS에 결과 기록

### 0.1.4 범위 밖 (기록만)
- 측정 스크립트가 다중 result 이벤트를 집계하지 못함(`scripts/e2e`, 플러그인이 아니라 버전과 무관. 다음 실제 세션 전에 고치면 된다)
- verifier가 쓰는 `reviewed_at`이 실제 시각이 아님(판정에 쓰지 않음)
- 신뢰된 작업 공간에서 설치 allow 규칙이 적용되는지(검증 항목)

## 확장 마일스톤 계획: G6 Integration / G7 System Verification (계획만, 미착수)

착수 조건: v0.1.4 릴리스 뒤 사용자가 Extension 착수를 결정할 때. LITE/STRICT 프로필, CI 독립 재검증, 사용자 결정의 암호학적 결속, WorkMind 적용은 이 계획에 넣지 않는다.

이미 있는 것
- `gates.json`에 G6(G6.EXECUTION, G6.IF_COVERAGE)과 G7(G7.EXECUTION, G7.AC_COVERAGE)이 `implemented: false`로 정의돼 있다. manifest는 G4/G5와 같은 코드 manifest다.
- `tests.json` 스키마가 `level: unit|integration|system`, `verifies`, `acceptance_criteria`를 지원하고, G3.INTEGRATION_SYSTEM_TESTS가 이미 IF별 통합 명세와 AC별 시스템 명세를 요구한다. 즉 테스트 계획은 G3에서 이미 만들어진다.
- 실행·증거·NO_WEAKENING·재작업 전제 조건·3회 실패 BLOCKED는 G5 구현을 재사용할 수 있다.

없는 것
- config의 통합·시스템 테스트 명령(지금은 `unit_test`만 있다)
- 실행·매핑·커버리지 체크
- G4에서 통합·시스템 테스트 코드 확인(G4.TEST_CODE와 TEST_INTEGRITY는 unit만 본다)
- 스킬·verifier 지침·SessionStart 문구("MVP scope: only G1-G5")·하네스
- IF가 있는 실제 산출물. 지금까지 실제 세션이 textstats·scorestats 샘플로 만든 아키텍처는 모두 컴포넌트 1개, IF 0개였다(E2E-3, drill S1). 이대로면 G6은 공허하게 통과한다.

### M5. G6 Integration Verification (0.2.0 후보, 2026-11-09 구현)
2026-11-10 최종 독립 검증(사용자 지시 "최종 독립 검증 및 E2E"): Case A~F 테스트로 D43의 Suite-level 귀속 문제를 재현하고 D44(테스트 수준 증거만 셈)로 고쳤다. 독립 검토 4~11회차, 실제 E2E 2회(sonnet, 합계 약 $2.08), 결과 TEST_RESULTS §15. 확정(병합·태그)과 푸시는 사용자 결정 대기.
2026-11-09 두 번째 결정(D1~D8)으로 남은 §9 항목이 모두 정해져 구현했다(D42). 진행·검토 기록은 `docs/g6/WORKITEM.md` §6·§7, 결과는 TEST_RESULTS §14. 다음: 사용자 확정(병합·태그 여부), 실전 E2E 2회 승인(계획 WORKITEM §8: sonnet 2회, 회당 $2, 합계 $4).

2026-11-09 사용자가 정책 네 가지를 정했다(D41). 확정 설계·요구사항·테스트 명세·구현 절차는 `docs/g6/G6-DESIGN.md`가 정본이다(이전 결정안 D39·`G6-DESIGN-PROPOSAL.md`는 대안 비교 기록).

착수 조건: 설계 §9의 남은 결정(§1.1 해석 확인, N/A 리뷰 확인 범위, 새 init 기본값, 업그레이드 G4 재리뷰 비용 처리, 연결 정적 확인 강도, 버전 번호). 결정 전 구현 금지.

구현 절차(설계 §7): 브랜치 `g6-dev` → `docs/g6/WORKITEM.md` → 테스트 코드 먼저(새 모듈 8개, 픽스처 `pipeline`·`single`) → RED(불변 `dist/vmodel-0.1.5` 대상, Red는 assertion 실패) → 구현(스키마 → gates.json → G5 실행부 분리(G5 불변식 먼저) → G5.SCOPE → G4 → 적용 판단 → eval_g6 → 결함 추적 → 표시 → 지침 → init → 버전) → GREEN(기존 225개 무수정 통과) → 독립 검토(읽기 전용, detached worktree, 지적은 RED 고정 후 수정) → 회귀(WSL·Windows cp949, 릴리스 빌드, 0.1.5 → 새 버전 업그레이드 재현) → E2E(비용 승인 후) → 사용자 확정.

완료 기준(테스트): 설계 §6의 Red 전부가 0.1.5에서 실패하고 새 코어에서 통과, Invariant(0.1.5 대비 G1~G5 투영·manifest 동일)와 Char 통과, 기존 하네스 225개 무수정 통과, Windows 실패 0, 0.1.5 서명 원장·증거가 새 코어에서 audit·verify-evidence 통과.

### M6. G7 System Verification (제안 버전 0.3.0)
먼저 결정할 것
1. 시스템 테스트 실행 방식과 `system_test` 명령. 라이브러리 샘플이면 CLI나 공개 API를 종단으로 호출하는 테스트.
2. `gates.json`의 G7 reviewer는 "vmodel:verifier + user acceptance"다. 사용자 결정 기록은 자기 증명(D25)이므로, STANDARD는 기계 판정만 하고 사용자 승인은 STRICT와 사용자 결정 결속(Extension)에서 함께 다루는 안을 권장한다.

체크(초안): G7.PREREQ(G6 PASSED), G7.EXECUTION, G7.RESULTS, G7.TEST_MAPPING, G7.AC_COVERAGE(활성 functional REQ의 모든 AC가 통과한 시스템 테스트로 검증), G7.NO_WEAKENING, G7.INPUTS_UNCHANGED.

완료 상태: G1~G7이 모두 현재 해시로 PASSED면 STANDARD WI가 처음으로 COMPLETED에 도달한다. SPEC §4.2·§10, status와 report 문구, SessionStart 주입 문구를 바꾸고, 하네스의 "MVP에서 COMPLETED 도달 불가" 테스트는 의도된 변경으로 갱신한다.

하네스: G1~G7 → COMPLETED, AC 미검증 → FAILED, G6 STALE → G7 STALE 전파, 재작업 루프, Windows cp949.

### M7. Extension 실제 세션 E2E
2026-11-10: G6 부분 실행(E2E-A: G6 BLOCKED → 아키텍처 수정 → PASSED, E2E-B: G6 N/A). G6 FAILED → DEFECT → CLOSED는 실제 세션에서 아직 관찰되지 않음(시딩 함정 미발동).
새 샘플로 `/vmodel:start`부터 G7 COMPLETED까지 1회, G6 실패에서 시작하는 재작업 1회. 실제 Claude 실행이라 횟수와 상한을 정해 사용자 승인을 받은 뒤에만 한다.

## 버전 이력
- 0.2.0 후보 (브랜치 `g6-dev`, 확정 전): G6 Integration Verification(D41·D42·D43·D44). 최종 독립 검증 TEST_RESULTS §15. 기록·태그는 사용자 확정 때 정한다(릴리스 사본 `dist/vmodel-0.2.0`과 `releases/vmodel-0.2.0.json`은 후보로 만들어 두었고, 같은 버전으로 다시 빌드하려면 `release.py --force`).
- 0.1.5 (releases/vmodel-0.1.5.json, core `sha256:37071459…`, 태그 `v0.1.5`, 2026-11-09 확정): 업그레이드 시 DevKit 권한 규칙 이동(D38). Gate 판정·원장 형식·manifest·guard 불변. **현재 기준 버전.** 검증: WSL 225/225, Windows cp949 225 실행·실패 0·skip 40, 확정 검증 TEST_RESULTS §13(D40). 알려진 비용: 업그레이드마다 G4 재리뷰.
- 0.1.0 (releases/vmodel-0.1.0.json): 최초 고정 릴리스. E2E-1에서 사용.
- 0.1.1 (releases/vmodel-0.1.1.json): 스킬/에이전트가 프로젝트 밖 플러그인 파일을 Read하지 않도록 `vmodel guide <topic>` 추가. E2E-2에서 사용.
- 0.1.2 (releases/vmodel-0.1.2.json, 태그 `v0.1.2` → `bbd6a3d`): 단일 명령 규칙(스킬·에이전트), verifier 포기 금지, 설치 시 validator CLI allow 규칙. E2E-3에서 G1~G5 완주, 실전 재작업 드릴(TEST_RESULTS §8)의 기준 버전.
- 0.1.4 (releases/vmodel-0.1.4.json, core `sha256:5dd1d010…`, 태그 `v0.1.4`, 2026-11-09 확정): guard `/dev/null` 오탐 수정과 리디렉션 우회 차단(F2), 실패 TEST 증거 정확성(F3, D35 P1), 결함 표시 상태 OPEN·FIX_APPLIED·REVERIFY_REQUIRED·VERIFICATION_FAILED·CLOSED·UNKNOWN(F1, D32 (C)·D37). Gate 판정·원장 형식·manifest 불변. 검증: WSL 186/186, Windows cp949 186 실행·실패 0·skip 6, 실제 세션 1회(guard 우회 0, audit OK). 공개 전 재빌드 이력은 §11.1.
- 0.1.3 (releases/vmodel-0.1.3.json, 태그 `v0.1.3`(태그 객체 `ef72f9a`) → `0df13b7`, 2026-11-08 확정): 드릴에서 찾은 F1~F4 수정 — 결함 `fixed`는 수정과 함께, 원장 파생 결함 추적(`failing_tests`/`unlinked_failing_tests`/`verified_by`), status에 실패 체크 표시, verifier 원인 대조 체크리스트(D28~D30). 실제 재작업 세션 1회(drill-3, TEST_RESULTS §9)에서 F1·F3·F4 통과, F2 부분 통과(누락 경고 경로는 프로브만). 확정 시 재검증: 하네스 103/103(WSL, 196초), 릴리스 사본·기록·소스 43개 파일 해시 일치, core `0208c798…`, drill-3 원장 audit OK(18건, 증거 6건). `main`은 fast-forward로 `0df13b7`(로컬, 푸시 안 함).
