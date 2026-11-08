# TEST_RESULTS

마지막 갱신: 2026-11-08. 검증 대상: VModel DevKit 0.1.2 (core `sha256:a0555e32…`, `releases/vmodel-0.1.2.json`). 0.1.0·0.1.1은 E2E-1·2에서 쓴 이전 릴리스.

"실측"은 이 PC에서 실제로 실행한 결과, "미검증"은 실행하지 않은 것입니다. 추정은 따로 표시합니다.

## 1. 부트스트랩 하네스 (Validator 자체 검증, unittest)

명령: `cd tests && python3 -m unittest discover -s . -p "test_*.py"`

| 환경 | 결과 | 비고 |
|---|---|---|
| WSL2 Ubuntu 24.04, Python 3.12.3, pytest 9.0.3, ruff | **94/94 통과** (실측) | 샌드박스 경로에 한글+공백 포함 |
| Windows 11, Python 3.13.14(Store) venv + pytest 9.2.0, 로캘 cp949, 경로 `%TEMP%\vmodel 한글 테스트\…` | **94 실행, 실패 0, skip 4** (실측) | skip: ruff 미설치 1, pty(POSIX 전용) 2, 심볼릭 링크 권한 1 |
| Python 3.11 | **미검증** | 이 PC에 3.11 없음. 3.12+ 전용 문법은 쓰지 않았으나 실행 확인 안 함 |

로그: Windows `%TEMP%\vmodel 한글 테스트\t18-harness.log` (세션 임시 파일, 영구 보관 아님).

### 시나리오별 근거 (하네스 테스트 이름)

| ID | 결과 | 근거 |
|---|---|---|
| T01 요청→REQ/AC | 기계 검증 통과 | `HappyPath.test_T01_T05_full_flow_partially_verified`(픽스처), `MechanicalChecks.test_missing_acceptance_criteria` 등. 실제 Claude 산출물은 §3 |
| T02 아키텍처 | 통과 | 전체 흐름 + `test_T11_broken_traceability_g2` |
| T03 상세 설계·테스트 명세 | 통과 | `test_T11_broken_traceability_g3`, `test_g3_requires_abnormal_and_system_tests` |
| T04 설계 기반 구현 | 통과 | `test_T04_design_conformance`, `test_g4_syntax_error_and_missing_test_code` |
| T05 실제 테스트 실행·증거 | 통과 | `test_T05_evidence_contents`(명령·실행파일·런타임·시각·종료코드·원본 바이트 해시·Git HEAD/dirty·파일 해시·Validator 해시·서명), `audit` OK |
| T06 실패 시 G5 차단 | 통과 | `test_T06_failing_test_blocks_g5` |
| T07 실행 없는 PASS 보고 거부 | 통과 | `test_T07_pass_report_without_execution_is_rejected`(가짜 증거·결과 JSON·리뷰), `test_unsubmitted_review_file_is_not_accepted` |
| T08 소스 변경 → STALE | 통과 | `test_T08_source_change_makes_pass_stale` (이전 G4 PASS로 G5 평가 불가 확인) |
| T09 테스트 변경 → 무효화 | 통과 | `test_T09_test_change_invalidates_and_needs_justification`, `test_deleted_test_is_detected`, `test_M2_test_data_change_makes_stale` |
| T10 필수 산출물 누락 | 통과 | `test_T10_missing_required_artifact_blocks_gate`, `test_T10_missing_architecture_and_prereq` |
| T11 잘못된 추적 | 통과 | `test_T11_broken_traceability_g2/g3`, `vmodel trace` 종료코드 1 |
| T12 Core 무결성 위반 | 통과 | `test_T12_validator_core_modification_blocks`, `test_release_manifest_detects_modified_file`, `test_upgrade_requires_user_repin_and_stales_previous_passes` |
| T13 실패→결함→수정→재검증 | 통과 | `test_T13_fail_defect_fix_reverify_pass`(결함 기록 없으면 재평가 거부), `test_three_identical_failures_block`, `test_streak_not_reset_by_review_required`, `test_user_unblock_with_tty` |
| T14 세션 재시작 후 복원 | 통과(하네스) | `test_T14_state_restored_in_new_process`, `test_session_start_restores_context`. 실제 새 세션은 §3 |
| T15 다른 프로젝트 적용 | 통과 | `test_T15_apply_to_a_different_project`(flat 레이아웃, 별도 키·원장) |
| T16 기존 설정 보존·충돌 | 통과 | `test_T16_existing_settings_preserved_and_conflicts_reported`, `test_claude_md_import_is_optional_and_reversible`, `test_invalid_existing_settings_not_touched` |
| T17 가짜 PASS 주입 | 통과 | `test_T17_injected/modified/truncated…`, `test_missing_signing_key_blocks`, `test_tampered_evidence_detected_by_audit`, `test_C1_reinit_after_wipe_refused_and_rollback_detected` |
| T18 한글 경로·Windows | 통과(실측) | 모든 샌드박스가 한글+공백 경로. Windows 하네스 위 표. CP949 산출물·비 UTF-8 테스트 출력·stdout None·cp949 콘솔 테스트 |

## 2. 독립 리뷰 결과와 반영 (2026-11-08)

별도 컨텍스트의 리뷰 에이전트가 Validator Core를 적대적으로 검토(코드 읽기만, 실험 없음). 지적 사항을 **먼저 회귀 테스트로 재현(17개 전부 실패 확인)한 뒤** 수정해 통과시켰습니다(`tests/test_hardening.py`).

| 지적 | 재현 | 조치 |
|---|---|---|
| `.vmodel` 삭제 후 재init으로 이력 초기화, 원장 롤백 | 재현됨 | 외부 앵커, 재init 거부, purge TTY, guard 차단 (D24) |
| Bash heredoc으로 리뷰 위조 | 재현됨 | `review-submit`(verifier만) + 원장 등록 해시 대조 (D19) |
| 루트 `pytest.py`·`__pycache__` 속 `.py`·심볼릭 링크·데이터 파일 사각지대 | 재현됨 | 전체 트리 manifest + G4.UNEXPECTED_CODE (D20) |
| 에이전트 환경변수(PYTEST_ADDOPTS 등) 누수 | 재현됨 | 정리된 환경·pycache prefix·플러그인 자동로드 끔 (D21) |
| conftest로 종료코드/junit 조작 | 재현됨 | G4.TEST_INTEGRITY (D22, 휴리스틱) |
| 한 테스트가 여러 TEST ID 충족, 주석도 인정 | 재현됨 | AST 함수명·JUnit name에 ID 하나 (D23) |
| LITE/미지 프로필이 COMPLETED | 재현됨 | STANDARD만 생성, 미지 프로필 BLOCKED |
| 3회 규칙이 중간 기록으로 리셋 | 재현됨 | REVIEW_REQUIRED·환경 BLOCKED는 건너뜀 |
| 비정상 JSON 형태로 크래시, 내부 오류가 FAILED(1)로 보임 | 재현됨 | 방어적 접근 + 내부 오류는 exit 2 |
| 상위 Gate 실패가 하위 PASS에 반영 안 됨 | 재현됨 | 상위가 PASSED가 아니면 하위 STALE |
| 사용자 결정 자기 증명, pty·스크립트로 우회 | 인정 | 문서화된 한계 (D25) |

## 3. 실제 Claude Code 실행 (헤드리스, 사용자 승인 범위 내)

승인: haiku 훅 확인 최대 4회(회당 $0.5), sonnet E2E 3회(회당 $4). 모든 실행은 임시 샌드박스, `--setting-sources project,local`(사용자 전역 설정 격리), `--no-session-persistence`.

### 3.1 훅 동작 (haiku)
| 실행 | 확인 내용 | 결과 | 비용 |
|---|---|---|---|
| H1 실패 모드 | 훅 크래시/타임아웃/exit 2/인터프리터 없음/깨진 JSON, `onFailure` 유무 | block 모드: 크래시·타임아웃·exit2·인터프리터 없음 **차단**, 깨진 JSON(exit 0)은 **통과**. 기본 모드: 크래시·타임아웃 **통과**(fail-open) | $0.006 |
| H2 guard | 보호 파일 쓰기, 증거 폴더 Bash 쓰기, 메인의 리뷰 작성, verifier의 리뷰/소스 쓰기, Core 변조, SessionStart 주입, 스킬·에이전트 등록 | 전부 설계대로. `agent_type`이 `vmodel:verifier`로 전달됨 확인 | $0.009 |
| H3 자동 트리거 음성 | "코드 설명해줘" | `vmodel:start` 미호출, WI 미생성 (정상) | $0.003 |

### 3.2 샘플 프로젝트 E2E (sonnet, `--plugin-dir dist/vmodel-<ver>`, 샌드박스 `한글 샘플 프로젝트`)

| 실행 | 버전 | 요청 방식 / 권한 모드 | 결과 | 비용·턴·시간 |
|---|---|---|---|---|
| E2E-1 | 0.1.0 | 자연어 "단어 빈도 기능을 개발해줘" / acceptEdits | **자동 트리거 성공**(`vmodel:start`). WI 생성 후 멈춤: 스킬이 프로젝트 밖 플러그인 파일(ARTIFACTS.md)을 Read → 비대화형이라 자동 거부. 에이전트는 우회하지 않고 보고 → **0.1.1에서 `vmodel guide`로 수정** | $0.10, 9턴, 21초 |
| E2E-2 | 0.1.1 | 명시 `/vmodel:start 문장 통계…` / acceptEdits | 명령 실행 성공. requirements.json 작성, lint 통과, G1 기계 체크 7/7 pass → **G1 REVIEW_REQUIRED**에서 멈춤: verifier가 `VM=…; …` 같은 묶음 명령을 써서 권한 매칭 실패 후 리뷰를 쓰지 않고 반환 → **0.1.2에서 "명령 하나씩" 규칙 + CLI allow 규칙 추가** | $0.26, 16턴, 74초 |
| (사용자 작업) | 0.1.1→0.1.2 | 문서화된 업그레이드 절차 | 재고정 전 전 Gate BLOCKED, TTY 재고정 후 이력 유지 | — |
| E2E-3 | 0.1.2 | **새 세션**, 자연어 "지난번 작업 이어서 끝까지" / auto | **자동 트리거 성공**, WI-001을 G1 REVIEW_REQUIRED부터 이어받음(T14 실측). verifier 4회·test-designer 1회 서브에이전트, 리뷰 4건 원장 제출, **G1~G5 PASSED → PARTIALLY_VERIFIED**. guard 거부 0건 | $0.64, 39턴, 3.7분 |

E2E-3 산출물(사본: `test-results/e2e/e2e3-artifacts/`): REQ 4개(functional 3 + constraint 1, AC 10개, 충돌 분석 1건, 가정 5건), ARCH 1개(인터페이스 없음, 트레이드오프 2건), DESIGN 1개(예외 1, 경계조건 8), TEST 6개(unit normal/abnormal/boundary×2, system 2), 리뷰 G1~G4 모두 approve(major 0). 구현 `src/textstats/sentences.py`, 테스트 4개 함수.

**독립 재검증(제가 별도로 실행)**: `vmodel verify WI-001`(릴리스 0.1.2)로 G1~G5를 처음부터 재평가 → 전부 PASSED, ruff·pytest를 Validator가 다시 실행(5 passed), `vmodel audit` OK(원장 17건, 증거 4건), `vmodel trace` 끊어진 링크 없음. 보고서: `test-results/e2e/e2e3-WI-001-report.md`.

### 3.3 측정 요약
- 명령 실행 성공률: 명시 명령 1/1 (워크플로우 시작). 자연어 개발 요청의 자동 트리거 2/2(E2E-1, E2E-3), 비개발 요청 오트리거 0/1(H3). 표본이 작아 "비율"로 일반화할 수 없음.
- 필요한 산출물 생성률: 끝까지 간 세션(E2E-3)에서 6/6(requirements, architecture, design, tests, 코드, 테스트 코드) + 리뷰 4/4.
- Gate 차단: 실제 세션에서 G1 REVIEW_REQUIRED 차단 1회 관찰(리뷰 없음 → 다음 세션이 리뷰 후 통과). **실제 세션에서 FAILED → DEFECT → 재검증 루프는 발생하지 않아 미관찰**(하네스 T13으로만 검증).
- 사용량: sonnet 3회 합계 $1.00, haiku 3회 합계 $0.018, 총 약 $1.02 (승인 상한 약 $14 이내). haiku 승인 4회 중 1회 미사용.
- 실제 세션 원본 기록: `test-results/e2e/measure-*.json`, `hook-probe-*.json`, 전체 트랜스크립트 `test-results/raw/`(git 제외).

### 3.4 실제 실행에서 드러난 결함과 조치
1. 0.1.0: 플러그인 파일을 Read하도록 한 스킬 → 프로젝트 밖이라 권한 거부 → `vmodel guide <topic>`(0.1.1).
2. 0.1.1: 에이전트의 묶음 명령이 권한 규칙과 매칭되지 않음, verifier가 거부 한 번에 포기 → 단일 명령 규칙·포기 금지 지시, 설치 시 validator CLI allow 규칙(0.1.2).
3. 관찰된 한계: 설계 단위가 하나면 모든 단위 테스트가 모든 REQ를 덮는 것으로 추적된다(추적 정밀도는 설계 분해 수준에 의존). E2E-3 리뷰어가 "REQ-004(표준 라이브러리 제약)를 확인하는 테스트 없음"을 minor로 지적한 것도 같은 맥락.

## 4. 플러그인 패키징
- `claude plugin validate --strict plugins/vmodel`: 통과 (실측). 디렉터리 제출용 경고(icon 없음)는 해당 없음.
- 공식 CLI 설치/제거: 격리된 `CLAUDE_CONFIG_DIR`에서 `marketplace add --scope project` → `install --scope project` → `plugin list`(0.1.0, project, enabled) → `uninstall` → `marketplace remove` 실측. 레지스트리는 격리 디렉터리에만 기록, 실제 `~/.claude` 변경 0건. 제거 후 settings에 빈 `{}` 키가 남음(관찰).
- 릴리스 불변성: 같은 버전 재생성 거부, 파일 읽기 전용, `RELEASE_MANIFEST.json`으로 파일별 대조 (하네스).
- 업그레이드 0.1.1 → 0.1.2: 재고정 전 무결성 FAILED(전 Gate BLOCKED), TTY 재고정 후 원장 이력 유지 (실측).

## 5. Windows 실행 경로 (실측)
- `bin/vmodel`(Git Bash sh 런처), `bin\vmodel.cmd`(cmd, PowerShell) 모두 동작. 한글+공백 경로.
- Git Bash에서 `hook guard`(deny JSON), `hook session-start`(컨텍스트 출력) 동작. 파이프 출력 UTF-8.
- PowerShell 5.1이 파이프 출력을 cp949로 해석해 한글이 깨져 보임: 설계상 파이프는 UTF-8(Claude Code가 UTF-8로 읽음). PowerShell 사용자는 `VMODEL_OUTPUT_ENCODING=cp949`로 바꿀 수 있음.
- **미검증**: Windows에서 Claude Code 세션 자체(훅·스킬 실행), Windows 절대경로 deny 규칙 형식(`//c/...`).

## 6. 미검증 항목 (MVP 범위 안)
- Python 3.11 실물 실행 (3.12·3.13만 실측)
- Windows에서 Claude Code 세션 자체로 훅·스킬을 돌리는 것 (Windows는 Validator·런처·훅 진입점까지만 실측)
- Windows 절대경로용 deny 규칙 형식(`Edit(//c/...)`)이 실제로 매칭되는지
- 실제 Claude 세션에서의 FAILED → DEFECT → 수정 → 재검증 루프(하네스로만 검증)
- 사람이 승인 창에 응답하는 대화형 세션에서의 사용성(헤드리스만 측정)
- 마켓플레이스 `--scope project` 설치 상태로 실제 세션 실행(설치/제거 CLI 동작만 격리 디렉터리에서 확인, 세션은 `--plugin-dir`로 실행)

## 7. 확장 단계로 남긴 것 (구현하지 않음)
G6 통합 검증, G7 시스템 검증, LITE/STRICT 프로필 실행, 다중 언어, 커버리지 기준, CI 기반 독립 재검증, 사용자 결정의 암호학적 결속, 서명 릴리스 배포, WorkMind 적용.
