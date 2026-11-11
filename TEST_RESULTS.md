# TEST_RESULTS

마지막 갱신: 2026-11-09(8차, §14 v0.2.0 후보: G6 Integration Verification). 후보 **0.2.0** (core `sha256:f835ec91…`, `releases/vmodel-0.2.0.json`, 브랜치 `g6-dev`, 사용자 확정 전, 실제 Claude 세션 없음) — §14. 2026-11-09(7차, §13 v0.1.5 확정 검증). 확정 버전: VModel DevKit **0.1.5** (core `sha256:37071459…`, `releases/vmodel-0.1.5.json`, 태그 `v0.1.5`) — §12의 하네스(WSL·Windows)·RED/GREEN·독립 검토 3회와 §13의 확정 검증(릴리스 해시, 업그레이드 공백 프로브, 원장·리뷰 호환 프로브, 깨끗한 worktree 전체 회귀)으로 검증, 실제 Claude 세션 없음. 이전 확정 버전 **0.1.4** (core `sha256:5dd1d010…`, `releases/vmodel-0.1.4.json`) — 하네스(WSL·Windows), 첫 0.1.4 빌드 대상 RED, 독립 검토 2회, **실제 Claude Code 세션 1회**(sonnet, $0.15, §11)로 검증. §10은 첫 0.1.4 빌드(core `b1fee43f…`) 기준 기록으로 보존한다. 이전 버전 **0.1.3** (core `sha256:0208c798…`, `releases/vmodel-0.1.3.json`) — 하네스와 **실제 Claude 재작업 세션 1회**(§9, drill-3)로 검증. 기준 버전 **0.1.2** (core `sha256:a0555e32…`, 태그 `v0.1.2` → 커밋 `bbd6a3d`)는 §3의 E2E-3과 §8의 실전 재작업 드릴에서 실제 세션으로 검증. 0.1.0·0.1.1은 E2E-1·2에서 쓴 이전 릴리스.

"실측"은 이 PC에서 실제로 실행한 결과, "미검증"은 실행하지 않은 것입니다. 추정은 따로 표시합니다.

## 1. 부트스트랩 하네스 (Validator 자체 검증, unittest)

명령: `cd tests && python3 -m unittest discover -s . -p "test_*.py"`

| 환경 | 결과 | 비고 |
|---|---|---|
| WSL2 Ubuntu 24.04, Python 3.12.3, pytest 9.0.3, ruff — **0.1.4 최종** (`e0358a5`, 깨끗한 worktree) | **186/186 통과** (실측, 644초, skip 0, `test-results/wsl-harness-0.1.4-final.log`) | 기존 162 + 표시 상태 24(§11) |
| Windows 11, Python 3.13.14 venv, cp949 — **0.1.4 최종** (`e0358a5`) | **186 실행, 실패 0, 오류 0, skip 6** (실측, 1560초, `test-results/windows-t18-harness-0.1.4-final.log`) | skip 6건은 Windows **미검증**(§11.3), WSL에서는 통과 |
| WSL2 Ubuntu 24.04, Python 3.12.3, pytest 9.0.3, ruff — **0.1.4 첫 빌드** (`8ac43c8`, 작업 트리 clean worktree) | **162/162 통과** (실측, 504초, skip 0, `test-results/wsl-harness-0.1.4.log`) | 기존 103(기대값 무수정) + 신규 59. 0.1.3 릴리스는 `dist/`가 없는 worktree라 git 태그 `v0.1.3`에서 해시 대조로 복원(`helpers.old_release`) |
| Windows 11, Python 3.13.14 venv, 로캘 cp949, `%TEMP%\vmodel 한글 테스트\devkit-0.1.4`(`git archive 8ac43c8` + 불변 `dist/vmodel-0.1.3` 복사) — **0.1.4** | **162 실행, 실패 0, 오류 0, skip 5** (실측, 1174초, `test-results/windows-t18-harness-0.1.4.log`) | skip 4건은 이전과 같음(ruff 미설치 1, pty 2, 심볼릭 링크 권한 1) + `OldEvidenceAccept`(재고정에 pty 필요) 1. 0.1.3 대비 차등·판정 불변식 테스트는 복사한 `dist/vmodel-0.1.3`으로 Windows에서도 실행·통과 |
| WSL2 Ubuntu 24.04, Python 3.12.3, pytest 9.0.3, ruff — **0.1.3, drill-3 실제 세션 후 재실행** | **103/103 통과** (실측, 196초, skip 0) | 코드 변경 없음(작업 트리 clean, Core `0208c798…`, `dist/vmodel-0.1.3` 43개 파일 해시가 `releases/vmodel-0.1.3.json`과 일치). 신규 실패 없음 |
| WSL2 Ubuntu 24.04, Python 3.12.3, pytest 9.0.3, ruff — **0.1.3** | **103/103 통과** (실측, 227초) | 기존 94 + 신규 9(`test_rework_flow.py`). 신규 중 6개는 0.1.2 코드에서, 1개(`verified_by` 기준 Gate)는 중간 수정본에서 먼저 실패(RED) 확인 후 수정. 나머지 2개는 Validator 불변식 특성 테스트 |
| WSL2 Ubuntu 24.04, Python 3.12.3, pytest 9.0.3, ruff — 0.1.2 기준 | **94/94 통과** (실측, 159초, 태그 전) | 샌드박스 경로에 한글+공백 포함 |
| Windows 11, Python 3.13.14 venv(아래 행과 같은 것), 로캘 cp949, `devkit-0.1.3-rerun`(`git archive HEAD`) — **0.1.3, drill-3 후 재실행** | **103 실행, 실패 0, skip 4** (실측, 477초, `test-results/windows-t18-harness-0.1.3-rerun.log`) | skip 4건 동일 |
| Windows 11, Python 3.13.14(Store) venv + pytest 9.2.0, 로캘 cp949, 경로 `%TEMP%\vmodel 한글 테스트\devkit-0.1.3` — **0.1.3** | **103 실행, 실패 0, skip 4** (실측, `test-results/windows-t18-harness-0.1.3.log`) | skip 4건은 아래와 동일 |
| Windows 11, 같은 venv — 0.1.2 | **94 실행, 실패 0, skip 4** (실측) | skip: ruff 미설치 1, pty(POSIX 전용) 2, 심볼릭 링크 권한 1 |
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
- Gate 차단: 실제 세션에서 G1 REVIEW_REQUIRED 차단 1회 관찰(리뷰 없음 → 다음 세션이 리뷰 후 통과). E2E-1~3에서는 FAILED → DEFECT → 재검증 루프가 생기지 않았습니다. 이 루프는 이후 §8 실전 재작업 드릴에서 관찰했습니다.
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
- ~~실제 Claude 세션에서의 FAILED → DEFECT → 수정 → 재검증 루프~~ → §8에서 부분 검증. 남은 것: (a) G4 리뷰가 실제로 결함을 놓쳐 G5가 실패하는 **주입 없는** 실제 경로(드릴에서는 실제 verifier가 결함을 잡아서 G4 승인 1건을 주입했음), (b) 완전 실제 G4 FAILED(drill-1) 상태에서의 실제 재작업 세션
- ~~0.1.3의 스킬·verifier 변경(D28~D30)이 실제 세션 행동을 바꾸는지~~ → §9에서 실제 세션 1회로 확인(`fixed` 시점, 5/5 링크, verifier 원인 대조). 남은 것: (c) 실제 세션에서 링크가 빠졌을 때 에이전트가 경고를 보고 보완하는지(이번에는 누락이 없어 경고 경로가 실행되지 않음, Validator 쪽은 프로브 P-F2로만 확인), (d) 표본 1회 — 반복 실행의 일관성
- 대화형 세션에서 auto 모드가 아닌 기본 권한으로 재작업 루프를 도는 것
- 사람이 승인 창에 응답하는 대화형 세션에서의 사용성(헤드리스만 측정)
- 마켓플레이스 `--scope project` 설치 상태로 실제 세션 실행(설치/제거 CLI 동작만 격리 디렉터리에서 확인, 세션은 `--plugin-dir`로 실행)

## 7. 확장 단계로 남긴 것 (구현하지 않음)
G6 통합 검증, G7 시스템 검증, LITE/STRICT 프로필 실행, 다중 언어, 커버리지 기준, CI 기반 독립 재검증, 사용자 결정의 암호학적 결속, 서명 릴리스 배포, WorkMind 적용.

## 8. 실전 재작업 드릴: 실패 → 결함 → 수정 → 재검증 (2026-11-08, 릴리스 0.1.2)

기준 버전: 커밋 `bbd6a3d`, 태그 `v0.1.2`(태그 객체 `f1ea8f7`, 로컬만, 푸시 안 함). 드릴은 불변 사본 `dist/vmodel-0.1.2`(core `sha256:a0555e32…`)로 실행했습니다. 실행 전후로 릴리스 트리 다이제스트가 같았습니다(`release_tree_unchanged: true`).

### 8.1 환경과 명령
- WSL2 Ubuntu 24.04, Python 3.12.3, pytest 9.0.3, ruff, Claude Code 2.1.319(claude.ai 구독 로그인). 샌드박스는 세션 스크래치 디렉터리의 `drill-1/한글 드릴 프로젝트`, `drill-2/한글 드릴 프로젝트`(한글+공백 경로, git 저장소, 샘플 `samples/scorestats`). STANDARD 프로필, G1~G5, ruff, 서명 키와 앵커는 드릴 전용 `VMODEL_HOME`.
- 공통 옵션: `--plugin-dir dist/vmodel-0.1.2 --setting-sources project,local --no-session-persistence --permission-mode auto --permission-prompts none --max-budget-usd 4`, `--dangerously-skip-permissions`는 쓰지 않음.
```bash
python3 scripts/e2e/rework_drill.py setup --work <drill-1>          # 샌드박스 + 시딩 계획 봉인 (sha256:1b7c05fa…)
python3 scripts/e2e/rework_drill.py probe --work <drill-1>          # haiku: 에이전트 pytest 차단 규칙 확인
python3 scripts/e2e/rework_drill.py run --work <drill-1> --phase s1 --prompt-file p-s1.txt   # +--disallowedTools Bash(*pytest*)
python3 scripts/e2e/rework_drill.py fork --source <drill-1> --work <drill-2>                 # G5 경로 포크 (D27)
python3 scripts/e2e/drill_safety.py --work <drill-2> --tag after-g5-fail                    # 안전장치 프로브 (모델 호출 없음)
python3 scripts/e2e/rework_drill.py run --work <drill-2> --phase s2 --prompt-file p-s2.txt
```
- 사용자 승인: ① haiku 프로브 ② S1 sonnet ③ S2 sonnet, 3회만. 실제 비용은 $0.0025 + $0.70 + $0.33 = **약 $1.04**.

### 8.2 시딩 계획(실행 전 봉인, `test-results/drill/s1-drill-1/drill-plan.json`)
- 기능: 점수 목록의 nearest-rank 백분위수(`r = ceil(p/100·N)`, p는 1~100 정수, 빈 목록·범위 밖 p는 ValueError).
- 결함(P4): 0-기반 인덱스를 `ceil(p·N/100)−1` 대신 `min(int(p·N/100), N−1)`로 계산. p·N/100이 N보다 작은 정수일 때만 드러남(예: [15,20,35,40,50], p=40 → 20이 아니라 35).
- 기대: G5 FAILED(G5.EXECUTION·RESULTS·TEST_MAPPING), 원인 P4, 수정 범위는 해당 모듈뿐, 테스트·명세 변경 없음. 대안 경로: verifier가 읽기만으로 찾으면 G4 리뷰 reject.

### 8.3 ① 권한 프로브 (실제 세션, haiku, $0.0025)
`--disallowedTools "Bash(*pytest*)"` 상태에서 `ls`는 허용됐고, `python3 -m pytest --version`, `cd . && PYTHONPATH=src python3 -m pytest -q`, `python3 -I -c "import pytest"`는 모두 거부됐습니다(`deny-probe.json`).

### 8.4 ② S1 — 요구사항~구현, 결함 시딩 (실제 세션, sonnet, $0.70, 34턴, 273초)
- 자동 진행: WI-001 → REQ 3개(AC 9개) → ARCH 1개 → DESIGN 1개 → test-designer가 TEST 16개(단위 12, 시스템 4) → 구현 → G4.
- 원장: R00002 G1 리뷰 approve → R00003 **G1 PASSED** → R00005 **G2 PASSED** → R00007 **G3 PASSED** → R00008 G4 리뷰 **reject** → R00009 **G4 FAILED**(기계 체크 8개 통과, G4.REVIEW만 실패). G5는 실행되지 않음.
- verifier는 결함을 모르는 상태(서브에이전트 프롬프트는 스킬 표준 그대로, 트랜스크립트로 확인)였고 pytest도 막혀 있었는데, 코드를 손으로 추적해 `percentile.py:20`의 내림 인덱스를 major로 지적했습니다. 실패할 테스트도 TEST-010/011/012로 정확히 지목했습니다. 에이전트 pytest 시도 1건은 거부, guard 거부 0건.
- 판정: 시딩 결함은 **G4 리뷰에서 검출**됐습니다. 계획한 G5 경로는 이 세션에서 나오지 않았습니다.

### 8.5 G5 경로 포크 — 놓친 리뷰 주입 (Validator 직접 실행, 모델 호출 없음)
S1의 실제 산출물·코드·테스트와 실제 G1~G3 리뷰 파일(바이트 동일)을 drill-2로 옮겨 G1~G3을 다시 통과시켰습니다(R00003/05/07). **G4 승인 리뷰 1건만 하네스가 작성**했고(R00008, summary에 `[DRILL FAULT INJECTION …]` 명시), R00009 G4 PASSED 뒤 Validator가 테스트를 직접 실행했습니다.
- **R00010 G5 FAILED**: 명령 `/usr/bin/python3 -m pytest -q -p no:cacheprovider --junitxml=…`, **종료 코드 1**, 18개 중 **5개 실패**(TEST-001 `[40-20]` 35≠20, TEST-002 3.5≠2.5, TEST-010 35≠20, TEST-011 30≠29, TEST-012 9≠5). G5.EXECUTION·G5.RESULTS·G5.TEST_MAPPING 실패, failure_signature 기록.
- 증거: `.vmodel/evidence/WI-001/G5/20261108T114053060340Z-unit-1576a1/`(record.json 서명, stdout.bin `sha256:78bafdbb…`, junit.xml `sha256:9e425f3e…`, git HEAD·dirty, manifest `sha256:b87df78d…`). 사본: `test-results/drill/s2-drill-2/evidence-G5/`.
- 실패 5건이 봉인 계획의 "드러나는 조건"과 모두 일치(N=4·p=50 포함). WI는 IN_PROGRESS, next_action은 rework.

### 8.6 안전장치 프로브 (실제 G5 FAILED 상태, `drill_safety.py`, 11/11 통과, 전부 원상 복구)
각 프로브 뒤 프로젝트 트리 다이제스트와 원장 길이가 이전과 같음을 확인했습니다(`safety-after-g5-fail.json`).

| 항목 | 프로브 | 결과 |
|---|---|---|
| 1 실패 상태에서 PASS 불가 | DEFECT 없이 `gate G5` 재실행 | BLOCKED, 기록 안 됨, "rework record missing" |
| 2 AI가 쓴 JSON은 증거 아님 | 위조 evidence record.json + junit(전부 통과) | `verify-evidence` REJECTED, `audit` FAILED(원장 미참조), G5 그대로 FAILED |
| 2 | WI 폴더에 `g5-result.json {"status":"PASSED"}` | 무시됨, G5 FAILED |
| 3 실행 없이 PASS 불가 | 원장에 G5 PASSED 줄 추가 / FAILED→PASSED 변조 / 마지막 줄 삭제 | 3건 모두 원장 INVALID, Gate BLOCKED |
| 4 코드 변경 → 재평가 | `src/` 파일 변경 | G4 PASSED → STALE, 변경 파일 명시 |
| 5 테스트·설정 변경 → 재평가 | 테스트 파일 / pyproject.toml / `.vmodel/config.json` 변경 | 각각 G4 STALE |
| 6 Validator 보호 | guard에 증거 Write, 원장 Edit, 원장 리디렉션, 릴리스 Core Edit, 메인 세션의 리뷰 Write·review-submit | 모두 deny, 일반 소스 Write는 allow |

### 8.7 ③ S2 — 재작업 (실제 세션, sonnet, $0.33, 128초, 시딩 정보 없음)
프롬프트: `/vmodel:rework WI-001` + "G5가 실패했다, 원인 분석·결함 기록·원인 단계 수정·재검증, 테스트 삭제·완화 금지".
- 결함: **DEFECT-001**, gate G5, found_in_records `R00010`, root_cause_phase **P4**, root_cause "index=int(p*N/100)(내림), 설계는 ceil", fix_scope `src/scorestats/percentile.py`. 봉인 계획과 원인·단계·범위가 일치합니다. **빈틈**: `related`에 실패 TEST 5개 중 3개(001/002/010)만 연결, `failed_checks`는 G5.RESULTS만 기록.
- 수정: 2줄(`rank = -(-p * count // 100)`, `return ordered[rank - 1]`). 테스트 파일·tests.json·요구사항·설계는 S1과 바이트 동일.
- 재검증: R00011 G4 REVIEW_REQUIRED(defects.json·코드 변경으로 이전 리뷰 무효) → 실제 verifier 재리뷰(R00012 approve, pytest 18 passed) → R00013 G4 PASSED → **R00014 G5 PASSED**(exit 0, 18/18, NO_WEAKENING "no test change since R00010").
- **실제 세션에서 드러난 결함 F1**: 통과 뒤 오케스트레이터가 defects.json `status`를 `fixed`로 바꿨고(0.1.2 rework 스킬 지시 그대로, verifier의 info finding도 이를 권유), 그 결과 G4/G5가 STALE → R00015·R00016 REVIEW_REQUIRED → verifier 재리뷰 R00017 → R00018 G4 PASSED → R00019 G5 PASSED. 최종 상태는 **PARTIALLY_VERIFIED**였지만 리뷰 1회와 Gate 재실행이 추가로 들었습니다.
- 두 번째 verifier가 finding status에 스키마 밖 값 `closed`를 써서 `review-submit`이 거부했습니다. 이어서 `sed -i`로 고치려 했고 **guard가 차단**("verifier may only run read-only commands"), Write 도구로 다시 써서 제출했습니다.
- 메인 세션이 단일 명령 규칙을 어긴 묶음 명령·`cd`·python heredoc을 썼고, auto 모드에서 허용됐습니다(D31). 원장 파일을 `tail`로 직접 읽어 실패 내용을 확인했습니다(→ D30).

### 8.8 독립 Audit (드릴 종료 후, 릴리스 0.1.2 Validator, `audit-final.txt`)
- `vmodel audit` OK(원장 19건, 증거 9건). 증거 9건 모두 `verify-evidence` OK.
- `vmodel verify WI-001`(저장 결과를 쓰지 않고 G1~G5 재평가, G5는 pytest 재실행) → R00020~R00024 전부 PASSED, 18/18, 재실행 후 audit OK(원장 24건, 증거 11건).
- 모든 Gate 기록의 Validator core hash가 `sha256:a0555e32…` 하나뿐(재작업 중 Validator 변경 없음). G5 이력: R00010 FAILED(5/18 실패) → R00014·R00019·R00024 PASSED, 모두 NO_WEAKENING 통과.
- `vmodel trace` 끊어진 링크 없음. 단, 설계 단위가 하나라 모든 단위 테스트가 REQ 3개 모두로 추적됨(D31).
- report: `DEFECT-001 [fixed — verified by R00019]`(0.1.2는 마지막 PASS를 표시). 0.1.3의 `defect_trace`를 같은 원장에 적용하면 `verified_by: R00014`(수정 후 첫 PASS), `unlinked_failing_tests: TEST-011, TEST-012`(`defect-trace-0.1.3.json`).

### 8.9 사실의 출처 구분
| 구분 | 내용 |
|---|---|
| Validator가 직접 확인 | G1~G5 판정·원장 기록 전부, G5 pytest 실행과 종료 코드·JUnit·stdout 해시, STALE 판정, audit/verify-evidence/verify 결과 |
| 별도 하네스·스크립트에서 확인 | 시딩 계획 봉인과 해시, 포크의 G4 승인 주입(D27), 안전장치 프로브 11건, 0.1.3 회귀 테스트(§8.10), 0.1.3 `defect_trace`를 실제 원장에 적용한 결과 |
| 실제 Claude Code 세션에서 확인 | 플러그인 스킬·서브에이전트·훅 로드, 요구사항~구현 산출물 작성, 블라인드 시딩 결함의 G4 리뷰 검출(S1), G5 FAILED 상태에서 DEFECT 기록·원인 P4 판정·최소 수정·verifier 재리뷰·G5 PASSED(S2), 실제 guard 차단 1건(verifier의 `sed -i`), 에이전트 pytest 차단 1건(S1) |
| 외부 CI·별도 권한 환경에서만 가능 | 같은 OS 사용자로 도는 에이전트가 키를 읽고 원장·앵커를 위조하는 것을 막는 일, 신뢰 사본으로 `vmodel audit`/`verify`를 별도 사용자로 실행, 사용자 결정의 암호학적 결속 (SPEC §5.7, D25) |

### 8.10 발견 결함과 0.1.3 조치 (회귀 테스트 먼저, `tests/test_rework_flow.py`)
| ID | 발견 | 재현(RED) | 조치 |
|---|---|---|---|
| F1 | 통과 후 `fixed` 표기 → G4/G5 STALE (S2 실측) | 하네스 특성 테스트 + 스킬 문구 테스트 2건 실패 | 스킬·verifier·VMODEL.md·ARTIFACTS.md: `fixed`는 수정과 함께 재리뷰 전에, 통과 후 defects.json 수정 금지 (D28) |
| F2 | DEFECT가 실패 TEST 5개 중 3개만 연결, 아무도 못 잡음 | `status`/`lint`/`report` 테스트 오류 3건 (+ 기준 Gate 테스트 1건) | 원장에서 `failing_tests`·`unlinked_failing_tests`·`verified_by` 파생(종료 기준 Gate는 에이전트가 쓴 `gate`가 아니라 서명된 실패 기록의 Gate), status/lint/report 표시, 차단 아님 (D29) |
| F3 | status가 실패 체크를 안 보여줘 원장 파일을 직접 읽음 | 위 테스트에 포함 | FAILED/BLOCKED Gate에 `failed_checks`·`failing_tests` (D30) |
| F4 | verifier가 원인을 실패 증거와 대조하지 않음(TEST-011을 잘못 해석) | verifier 문구 테스트 실패 | G4 체크리스트: 원인이 모든 실패를 설명하는지 status의 실패 정보로 확인, 통과 후 수정 요구 금지 |

0.1.3은 하네스로만 검증했습니다. **0.1.3 스킬·verifier 변경을 실제 Claude 세션으로 확인하지는 않았습니다**(승인된 실행 3회를 모두 사용).

## 9. 0.1.3 실제 재작업 세션 검증: drill-3 (2026-11-08, 릴리스 0.1.3)

목적: 0.1.3에서 고친 F1~F4가 실제 Claude Code 세션의 "실패 → 결함 분석 → 수정 → 재검증 → Gate PASS" 흐름을 실제로 바꾸는지 확인한다. 조건은 S2(§8.7)와 똑같이 맞췄다. 시작 상태, 프롬프트, 권한 모드, 허용 도구가 같고 릴리스만 0.1.2에서 0.1.3으로 바꿨다. 그래서 두 결과를 나란히 비교할 수 있다.

### 9.1 환경·명령·실행 횟수·비용
- WSL2 Ubuntu 24.04, Python 3.12.3, pytest 9.0.3, ruff, Claude Code 2.1.319(claude.ai 구독 로그인). 모델은 `claude-sonnet-5-5`(세션 init 기록). 샌드박스는 세션 스크래치의 `drill-3/한글 드릴 프로젝트`(한글+공백 경로, git 저장소)이고, 서명 키·앵커는 드릴 전용 `VMODEL_HOME`을 썼다.
- 릴리스 `dist/vmodel-0.1.3`(core `sha256:0208c798…`). 43개 파일 해시가 `releases/vmodel-0.1.3.json`과 일치했고, 릴리스 트리 다이제스트가 세션 전후로 같았다(`2964dacc…`, `release_tree_unchanged: true`).
- 세션 옵션: `--plugin-dir dist/vmodel-0.1.3 --setting-sources project,local --no-session-persistence --permission-mode auto --permission-prompts none --max-budget-usd 1 --model sonnet`, 허용 도구는 S2와 같다. `--dangerously-skip-permissions`는 쓰지 않았다.
```bash
python3 scripts/e2e/rework_drill.py fork --source <drill-1> --work <drill-3> --release "$PWD/dist/vmodel-0.1.3"   # 모델 호출 없음
python3 scripts/e2e/drill_safety.py --work <drill-3> --tag after-g5-fail --release "$PWD/dist/vmodel-0.1.3"     # 모델 호출 없음
python3 scripts/e2e/rework_drill.py run --work <drill-3> --phase s3 --prompt-file p-s3.txt \
        --release "$PWD/dist/vmodel-0.1.3" --model sonnet --budget 1 --permission-mode auto                      # 실제 세션 1회
```
  `--release`는 절대 경로여야 한다. 첫 fork 시도는 상대 경로라서 설치 단계에서 실패했다(모델 호출 없음, 반쯤 만든 폴더는 지우고 다시 실행).
- **실행 횟수: sonnet 헤드리스 1회**(승인 1회 중 1회 사용). 추가 실행은 없었다.
- **비용: $0.2606**(CLI의 `total_cost_usd`, list 가격 기준 추정치, 상한 $1의 26%). 토큰은 출력 7,241 / 캐시 읽기 405,646 / 캐시 생성 44,451 / 입력 34이고, 벽시계는 77초다. 구독 로그인이라 실제 청구액이 아닌 추정치다.
- **예산 상한 강제 여부(조사 결과)**: `--max-budget-usd`는 `-p`(print) 모드에서만 동작한다. CLI 2.1.319 바이너리에는 "print budget halt: this run's spend reached --max-budget-usd; stopping background agents"와 `error_max_budget_usd` 결과 유형이 있다. 상한에 닿으면 실행을 멈추고 백그라운드 에이전트도 멈춘다는 뜻이다. 한계도 세 가지 있다. 첫째, CLI 문서 문자열 스스로 "An estimate, not a billing statement"라고 적는다. 둘째, 지출이 생긴 뒤에 검사하므로 진행 중이던 요청만큼은 넘을 수 있다. 셋째, 이번 실행은 상한에 닿지 않아서 멈추는 동작 자체는 실측하지 못했다.

### 9.2 Synthetic Fixture 명시 (자연 발생 실패가 아님)
G5 FAILED 상태는 **합성 픽스처**이고, 아래 두 가지가 인위적이다.
1. **결함은 블라인드 시딩이다**(D26). S1에서 오케스트레이터가 봉인된 계획(`drill-plan.json`, `sha256:1b7c05fa…`)대로 P4 결함을 넣었다.
2. **G4 승인 리뷰 1건(R00008)은 하네스가 작성했다**(D27). 실제 S1에서는 verifier가 이 코드를 reject했다. 주입한 리뷰의 summary에 `[DRILL FAULT INJECTION - written by the rework-drill harness, not by an AI reviewer]`가 적혀 있고, 그 해시가 원장에 묶여 있다.

그 밖에는 모두 실제다. 요구사항~코드·테스트와 G1~G3 리뷰(R00002/04/06)는 S1의 실제 산출물로, 커밋된 사본 `test-results/drill/s1-drill-1/`과 바이트 단위로 같다. R00009 이후 기록은 모두 Validator 또는 실제 세션이 만들었다. drill-3은 포크가 새로 만든 샌드박스·원장이고, 기존 서명 원장(drill-1·drill-2)은 수정하지 않았다. drill-1 프로젝트 트리 다이제스트는 포크 전후 `731af922…`로 같았다. 포크가 다시 봉인한 계획 파일(`sha256:867b4b89…`)은 원본 계획에 시각과 `fork` 절만 더한 것이다.

### 9.3 최초 실패 상태 (Validator 직접 실행)
- **R00010 G5 FAILED**: Validator가 실행한 명령은 `/usr/bin/python3 -m pytest -q -p no:cacheprovider --junitxml=…`이고, **종료 코드 1**, 18개 중 **5개 실패**였다(TEST-001 `[40-20]` 35≠20, TEST-002 3.5≠2.5, TEST-010 35≠20, TEST-011 30≠29, TEST-012 9≠5). 실패 체크는 G5.EXECUTION·G5.RESULTS·G5.TEST_MAPPING이고 failure_signature는 `sha256:da8cba83…`다.
- 증거는 `.vmodel/evidence/WI-001/G5/20261108T125458427119Z-unit-0c2e40/`에 있다. stdout은 `sha256:78bafdbb…`로 **drill-2의 R00010과 바이트 단위로 같아** 결정적으로 재현됐다. junit.xml은 `sha256:f5ee7f7c…`, git HEAD는 `5cd748a2`(dirty)다. 사본: `test-results/drill/s3-drill-3/evidence-G5/`.
- `vmodel status`(0.1.3)는 G5 아래에 실패 체크 3개, 실패 케이스 5개, `failing tests: TEST-001, TEST-002, TEST-010, TEST-011, TEST-012`를 출력했다(F3).
- **실패 상태의 PASS 차단(안전장치 프로브 11/11, 0.1.3, 모두 원상 복구)**: DEFECT 없이 G5를 다시 실행하면 기록 없이 BLOCKED가 된다. 위조 증거 JSON·결과 JSON은 무시되거나 거부되고, 원장 위조·변조·꼬리 삭제는 INVALID로 잡힌다. 소스·테스트·빌드 설정·Validator 설정을 바꾸면 G4가 STALE이 되고, guard는 보호 경로 쓰기와 메인 세션의 리뷰 작성·제출을 거부한다(`safety-after-g5-fail.json`). 결과는 §8.6과 같다.

### 9.4 S3 실제 세션 진행 (트랜스크립트 도구 호출 24건, `timeline-s3.json`)
프롬프트는 S2와 바이트 단위로 같다. `/vmodel:rework WI-001`에 "G5 실패, 원인 분석·결함 기록·원인 단계 수정·재검증, 테스트 삭제·완화 금지"를 붙였다.

| # | 주체 | 동작 | 결과 |
|---|---|---|---|
| 1 | 메인 | `vmodel status WI-001` | 실패 체크·케이스·TEST ID 5개 확인 |
| 2~5 | 메인 | 코드·테스트·설계·`guide artifacts` 읽기 | #3 guard 거부 1건(오탐, §9.10) |
| 6 | 메인 | Write `defects.json` | DEFECT-001, `status: fixed`, 실패 TEST 5개 연결 |
| 7 | 메인 | Edit `src/scorestats/percentile.py` | 2줄 수정 |
| 8 | 메인 | `vmodel lint WI-001` | lint OK(미연결 경고 없음) |
| 9 | 메인 | `vmodel status WI-001` | G4 STALE(defects.json·소스 변경), `DEFECT-001 [fixed; not verified yet]` |
| 10 | 메인 | vmodel:verifier 실행(백그라운드) | 재리뷰 요청 |
| 11~20 | verifier | `hash`, `status --json`, 코드·테스트·defects·설계·명세 읽기, G4.json 작성, `review-submit` | **R00011 G4 approve** |
| 22 | 메인 | `vmodel gate WI-001 G4` | **R00012 G4 PASSED** |
| 23 | 메인 | `vmodel gate WI-001 G5` | **R00013 G5 PASSED** |
| 24 | 메인 | `vmodel status` | `DEFECT-001 [fixed; verified by R00013]` |

세션은 원장·증거 파일을 직접 읽지 않았고(0건), 에이전트가 pytest를 실행하지 않았고(0건), 테스트 파일도 수정하지 않았다(0건). Implementation 역할은 D11에 따라 메인 세션(오케스트레이터)이 맡았고, 코드 수정(#7)도 메인 세션이 했다. 슬래시 명령으로 확장된 스킬 본문은 stream-json에 남지 않는다. 그래서 0.1.3 rework 스킬이 적용됐다는 판단은 행동 차이에 근거한다. S3는 VM 호출을 모두 단독 명령으로 했고, defects.json을 Write 도구로 썼고, 0.1.3에서 추가된 lint 단계를 실행했다. S2는 `VM=…;` 묶음 명령과 python heredoc을 썼고 lint를 실행하지 않았다.

### 9.5 DEFECT와 Root Cause
- DEFECT-001: gate G5, `found_in_records: [R00010]`, `failed_checks: [G5.EXECUTION, G5.RESULTS, G5.TEST_MAPPING]`, `root_cause_phase: P4`, `fix_scope: [src/scorestats/percentile.py]`, `related: [REQ-001~003, DESIGN-001, TEST-001, TEST-002, TEST-010, TEST-011, TEST-012]`, `status: fixed`.
- 원인(세션 기록): "DESIGN-001(순위 r = ceil(p·N/100), 인덱스 r−1)과 달리 `index = min(int(p*count/100), count-1)`. int()는 내림이고 1을 빼지 않아 한 칸 뒤 값을 고른다. 설계와 테스트 명세는 올바르다."
- **봉인 계획과 대조**: 원인 단계(P4), 결함 내용, 수정 범위(해당 모듈만), 테스트 변경 없음이 모두 일치한다.
- **실패 증거와 독립 대조**(`root_cause_check.py`, 모델 호출 없음): 테스트 파일의 정상 입력 호출 13건을 시딩 코드, 수정 코드, 봉인 계획의 기준식(`sorted[ceil(p·N/100)−1]`)으로 계산했다. 시딩 코드가 틀린 경우는 정확히 5건이고 JUnit 실패 5건과 같다. 5건 모두 p·N/100이 N보다 작은 정수였다(계획의 발현 조건). 수정 코드가 틀린 경우는 0건이다(`root-cause-check.txt`). 원인 설명의 "부동소수점 나눗셈도 사용한다"는 사실이지만 실패 원인은 아니다(D34).

### 9.6 코드 수정
```diff
-    index = min(int(p * count / 100), count - 1)
-    return ordered[index]
+    # nearest-rank: 순위 r = ceil(p*N/100)을 정수 연산으로 구하고 0-기반 인덱스는 r-1
+    rank = -(-p * count // 100)
+    return ordered[rank - 1]
```
S2 수정과 로직이 같고 주석 위치만 다르다. 테스트 파일, requirements·architecture·design·tests·workitem은 S1과 바이트 단위로 같다(테스트 완화·삭제 없음).

### 9.7 G4/G5 재검증 (서명 원장)
- R00011 G4 리뷰 approve(major 0, minor 0, info 1: 검증 순서와 원소 타입, 설계 범위 밖) → R00012 **G4 PASSED**(manifest `49b4ad51…`, ruff는 Validator가 직접 실행, 증거 기록) → R00013 **G5 PASSED**(종료 코드 0, 18/18, 단위 명세 12개 통과, NO_WEAKENING "no test change since R00010", stdout `sha256:bd4a0bf2…`, junit `sha256:f8325547…`).
- WI-001 **PARTIALLY_VERIFIED**. G6·G7은 미구현 Extension이므로 V-Model 전체 완료가 아니다.

**0.1.2(S2)와 비교** — 같은 시작 상태, 같은 프롬프트:

| 항목 | S2 (0.1.2, §8.7) | S3 (0.1.3) |
|---|---|---|
| 재작업 구간 원장 기록 | R00011~R00019, 9건 | R00011~R00013, **3건** |
| REVIEW_REQUIRED 기록 | 3건(R00011·15·16) | **0건** |
| verifier 재리뷰 | 2회 | **1회** |
| G4·G5 PASS 기록 | 각 2회(통과 후 `fixed` 편집 → STALE → 재실행) | **각 1회** |
| 통과 후 defects.json 수정 | 1회 | **0회** |
| DEFECT의 실패 TEST 연결 | 3/5 | **5/5** |
| DEFECT의 `failed_checks` | 1/3 | **3/3** |
| 에이전트의 원장 파일 직접 읽기 | 있음(`tail ledger.jsonl`) | **없음** |
| verifier의 원인↔실패 대조 기록 | 없음 | **있음**(체크리스트 항목) |
| review-submit 거부 | 1회(스키마 밖 값 `closed`) | 0회 |
| guard 거부 | 1회(verifier `sed -i`, 정상 차단) | 1회(읽기 명령 오탐, §9.10) |
| 비용·벽시계 | $0.33, 128초 | $0.26, 77초 |

표본은 각 1회다. 이 차이가 0.1.3 변경 때문이라는 해석은 행동 일치(§9.4)에 근거한 것이고, 통계적으로 증명한 것은 아니다.

### 9.8 Evidence Ledger와 독립 Audit (세션 종료 후, 0.1.3 Validator, `audit-final.txt`)
- `vmodel audit` OK(원장 13건, 증거 4건). 증거 4건(G4 lint 2, G5 unit 2) 모두 `verify-evidence` OK, `vmodel lint WI-001` OK.
- `vmodel verify WI-001`(저장 결과를 쓰지 않고 G1~G5 처음부터 재평가) → R00014~R00018 모두 PASSED. ruff와 pytest를 Validator가 다시 실행해 18/18 통과했고 NO_WEAKENING도 통과했다. 이후 audit OK(원장 18건, 증거 6건).
- 모든 Gate 기록의 Validator core hash는 `sha256:0208c798…` 하나뿐이다(재작업 중 Validator 변경 없음).
- `vmodel trace` 끊어진 링크 없음. report에는 `DEFECT-001 [fixed — verified by R00013]`와 "failing tests in R00010 (from the signed ledger): TEST-001, TEST-002, TEST-010, TEST-011, TEST-012"가 나오고 미연결 줄은 없다. 설계 단위가 하나라 모든 단위 테스트가 REQ 3개로 추적되는 한계는 그대로다(D31).
- 최종 Gate 상태(status: G1~G5 PASSED, PARTIALLY_VERIFIED)와 audit·verify 결과가 일치한다.

### 9.9 F1~F4 실전 검증 결과

| ID | 실제 세션(S3)에서 확인 | Validator 단독 프로브(모델 호출 없음, 원상 복구) | 판정 |
|---|---|---|---|
| F1 결함 상태·Gate 최신성 | `fixed`를 수정과 같은 단계(#6, 리뷰 전)에서 기록했고 통과 후 defects.json 편집은 0회였다. status는 수정 시점 `[fixed; not verified yet]`과 검증 시점 `[fixed; verified by R00013]`을 구분했다. 불필요한 STALE·REVIEW_REQUIRED는 0회 | P-F1: 통과 후 status를 `open`으로 바꾸면 G4·G5가 STALE이 되지만 `verified_by`는 R00013으로 유지된다(설계대로, D28) | **통과** |
| F2 실패 테스트 추적 | 세션이 실패 TEST 5/5를 연결했다. lint·status·report가 원장에서 같은 5개를 조회했고 미연결은 0 | P-F2: TEST-011·012를 빼면 status·report가 "NOT linked: TEST-011, TEST-012"를 표시하고 lint는 종료 코드 1. 단, G5 통과 후 보완하면 G4·G5 STALE | **부분 통과**: 조회와 완전 연결은 실측. 누락 → 경고 → 보완 경로는 실제 세션에서 발생하지 않음(프로브로 Validator 동작만 확인) |
| F3 status 명령 | 에이전트가 `status`만으로 실패 Gate, 실패 체크 3개, 실패 케이스 5개, 실패 TEST ID 5개를 얻었다. 원장·증거 파일 직접 읽기 0회 | — | **통과** |
| F4 Verification Agent | verifier가 메인 세션 프롬프트에 없던 `status --json`을 스스로 호출했다. 체크리스트에 "root cause explains every failing case"를 실제 실패값(35≠20, 3.5≠2.5, 30≠29, 9≠5)과 `unlinked_failing_tests` 비어 있음으로 기록했다. 수정 범위 준수를 확인했고, 통과 후 defects.json 편집 요구는 없었다. 결과적으로 결함 상태(fixed, verified by R00013)와 테스트 결과(18/18)가 일치 | 원인↔실패 대조를 독립 계산(`root_cause_check.py`)한 결과 일치 | **통과**: verifier의 대조는 AI 리뷰이고 기계 검증이 아님. verifier는 pytest 없이 손으로 평가했고, 기계 확인은 G5 실행이 함 |

### 9.10 이번 검증에서 발견한 추가 문제 (고치지 않음, D34)
1. guard 오탐: `cat ../../defects.json 2>/dev/null`처럼 `.vmodel`을 읽는 명령을 쓰기로 판정해 거부했다(`WRITE_VERBS`의 `[0-9]>`가 원인, 재현 확인). 막는 쪽으로 틀린 오탐이고, 에이전트는 명령을 나눠 다시 읽었다.
2. verifier의 `reviewed_at`이 실제 시각이 아니다(drill-3 13:10:00Z, 원장 12:56:31Z / S2 `00:00:00Z`). 판정에는 원장 시각만 쓴다.
3. verifier가 백그라운드로 돌면 헤드리스 result 이벤트가 2개 생긴다. 측정 스크립트가 마지막 것만 써서 턴·시간을 적게 기록했다(비용은 누적값이라 정확).
4. 샌드박스의 `.claude/settings.json` allow 규칙이 "workspace not trusted"로 무시됐다(S2와 같음). 헤드리스 드릴은 `--allowedTools`로만 허용한다.

모두 실전 검증을 막지 않았다. 이번에 **필수 코드 수정은 없었다**. 따라서 재현 테스트 추가·Core 수정·새 릴리스도 하지 않았다.

### 9.11 회귀 테스트 (실제 세션 후 재실행)
| 환경 | 결과 | 비고 |
|---|---|---|
| WSL2 Ubuntu 24.04, Python 3.12.3, pytest 9.0.3, ruff | **103/103 통과**, skip 0 (실측, 196초, `test-results/wsl-harness-0.1.3-rerun.log`) | 소스 트리 `plugins/vmodel` 기준(`dist/vmodel-0.1.3`과 바이트 동일) |
| Windows 11, Python 3.13.14 venv, 로캘 cp949, `%TEMP%\vmodel 한글 테스트\devkit-0.1.3-rerun`(`git archive HEAD`로 새로 풀어 실행) | **103 실행, 실패 0, 오류 0, skip 4** (실측, 477초, `test-results/windows-t18-harness-0.1.3-rerun.log`) | skip 4건은 이전과 같다. ruff 미설치 1, pty가 POSIX 전용 2, 심볼릭 링크 권한 1. 이 4건은 Windows에서 **미검증**이고 WSL에서는 통과 |

- 신규 실패는 없다. Validator Core는 바뀌지 않았다(작업 트리 clean, core `0208c798…`, 릴리스 43개 파일 해시 일치, 릴리스 트리 다이제스트가 세션 전후 동일). `claude plugin validate --strict plugins/vmodel`은 통과했다.
- 기존 검증 기능에도 영향이 없다. 0.1.3 Validator로 안전장치 프로브 11/11과 audit·verify-evidence·verify가 실제 drill-3 원장에서 통과했다(§9.3, §9.8).
- 이번에는 코드를 바꾸지 않아서 재현 테스트를 추가하지 않았다.

### 9.12 실제 검증과 시뮬레이션 검증 구분
| 구분 | 내용 |
|---|---|
| 실제 Claude Code 세션(S3, sonnet 1회) | 실패 상태 조회(status), DEFECT 작성(5/5 연결, P4), 코드 수정, lint·status 재확인, verifier 재리뷰(원인↔실패 대조), G4·G5 재평가 호출, 최종 보고 |
| Validator 직접 실행(실제 실행, 모델 아님) | R00010 G5 FAILED와 pytest 실행, R00012·R00013 판정, 증거·서명·해시, audit·verify-evidence·verify(pytest 재실행)·trace·report |
| 합성(Synthetic Fixture) | 시딩 결함(S1, 봉인 계획), G4 승인 리뷰 1건 주입(R00008) |
| 시뮬레이션·프로브(모델 호출 없음, 원상 복구) | 안전장치 프로브 11건, P-F1·P-F2, 원인 독립 계산, 하네스 103개 |

### 9.13 미검증 항목
- 실제 세션에서 DEFECT 링크가 빠졌을 때 경고를 보고 보완하는 행동(이번에는 누락이 생기지 않음).
- 반복 표본: S3는 1회뿐이다. 0.1.2와의 차이가 우연이 아니라는 통계적 근거는 없다.
- 주입 없는 G5 FAILED(G4 리뷰가 실제로 결함을 놓치는 경우)와, 완전 실제 G4 FAILED(drill-1) 상태에서 시작하는 재작업 세션.
- `--max-budget-usd` 상한에 실제로 닿았을 때 멈추는 동작(이번에는 $0.26으로 상한 미도달).
- 대화형 세션, auto가 아닌 기본 권한 모드, Windows에서의 Claude Code 세션, 신뢰된 작업 공간에서 설치 allow 규칙이 적용되는지, Python 3.11(§6).

### 9.14 v0.1.3 릴리스 준비 판단
**태그를 붙일 준비는 됐다고 판단한다. 다만 태그·병합·푸시는 하지 않았고, 결정은 사용자에게 남긴다.**
- 근거: 실제 세션 1회에서 F1·F3·F4가 의도대로 동작했고, F2는 조회와 완전 연결까지 실측했다. 독립 audit·verify가 통과했고, 회귀는 WSL 103/103, Windows 103 실행·실패 0·skip 4다(§9.11). Validator Core·릴리스 사본은 변경되지 않았다. 이번에 발견한 4건은 모두 안전 측 오탐이거나 측정·표시 문제라서 릴리스를 막을 결함이 아니다.
- 단서: 표본이 1회이고, G5 실패는 합성 픽스처이며, auto 권한 모드의 헤드리스 세션에서만 확인했다. `v0.1.3` 태그는 코드가 같으므로 이 검증 결과 문서 커밋에 붙이는 것을 권한다.


## 10. v0.1.4 검증 (2026-11-09, 릴리스 0.1.4, 실제 Claude 세션 없음)

범위: F1 결함 종료 상태, F2 guard 오탐·리디렉션 우회, F3 실패 TEST 증거 정확성(DECISIONS D36, `docs/v0.1.4/WORKITEM.md`). 모델 호출이 드는 헤드리스 실행은 하지 않았다(비용 0). 독립 검토는 이 세션의 서브에이전트(Verification Agent, 별도 컨텍스트, 저장소 읽기 전용)로 했다.

### 10.1 기준선과 커밋
- 시작: `main` = `e6fc892`, 태그 `v0.1.3` = `0df13b7`, 원격 미푸시. 착수 전 0.1.3 코드 하네스 103/103 통과(189초, `test-results/v0.1.4/baseline-0.1.3-harness.log`).
- 브랜치 `v0.1.4-dev`: `68f64e7` F2 → `14f46b5` F3 → `2d4f5c6` F1 → `817b9aa` 검토 반영 → `4c13447`·`89ead99` 재검토 반영 → `8ac43c8` 버전·릴리스·문서 → (이 문서 커밋). 항목마다 독립 커밋이다.

### 10.2 RED → GREEN (`scripts/red_green.py`, 클래스 접미사로 기대 결과 고정)
RED 대상은 "고치기 전의 작업 트리"가 아니라 불변 릴리스 `dist/vmodel-0.1.3`(core `0208c798…`, `releases/vmodel-0.1.3.json`과 43개 파일 일치)이다. 최종 로그는 깨끗한 `8ac43c8` worktree에서 다시 만들었다(`worktree_dirty: false`).

| 모듈 | 0.1.3 대상 RED | 0.1.4 GREEN |
|---|---|---|
| `test_guard_redirects` (F2) | 11/11 기대 충족: Red 5 FAIL, Char 6 통과 | 12/12 (차등 인수 1 포함) |
| `test_defect_closure` (F1) | 15/15: Red 14 FAIL, Invariant 1 통과 | 15/15 |
| `test_defect_evidence` (F3) | 29/29: Red 25 FAIL, Char 4 통과 | 29/29 |
| `test_version_compat` | 2/2: Invariant 2 통과(0.1.3 대 0.1.3) | 3/3 (Accept 1 포함) |
| 합계 | 57 기대 충족, 위반 0 | 59/59, 위반 0, skip 0 (291초) |

로그: `test-results/v0.1.4/red-*.log`, `green-all.log`. Red는 모두 assertion 실패(FAIL)이며 ERROR로 끝난 것은 없다. 검토 지적으로 추가한 테스트 중 4개는 0.1.3뿐 아니라 직전 수정본(`68f64e7` 전 작업 트리, `817b9aa`, `4c13447`)에서도 실패를 확인한 뒤 고쳤다(WORKITEM §8).

### 10.3 회귀
- WSL 전체 하네스 162/162(§1). 기존 103개는 기대값을 바꾸지 않았다. 기존 테스트가 고정한 문구(`DEFECT-001 [fixed — verified by R…]`, `does not link failing test(s) of R…`, `failing tests in R… (from the signed ledger): …`, verifier 지침 정규식)는 유지했다.
- 커밋별: `68f64e7` 115/115(208초), `817b9aa` 157/157(440초), `8ac43c8` 162/162. 모두 깨끗한 worktree.
- Windows cp949: §1.
- `claude plugin validate --strict plugins/vmodel` 통과(README 마켓플레이스 설치 줄 권고 경고 1건은 이전과 같음). ruff: 지적 1건(cli.py의 미사용 import `open_context`)은 0.1.3부터 있던 것이고 손대지 않았다.

### 10.4 불변식 (Gate 판정·원장·manifest)
- 0.1.3 릴리스와 0.1.4에 같은 재작업 이력(무효 인용·미연결 포함 결함, 수정, PASS, 표시 명령, REVIEW_REQUIRED, 전제 조건 BLOCKED)을 돌려 원장 투영(기록 종류, Gate, 상태, blocked_reason, 실패 서명, 체크별 상태, TEST별 결과)이 같음(`GateDecisionInvariant`).
- 같은 프로젝트에서 두 코어의 `vmodel hash WI G1~G5`(파일별 해시와 manifest 해시)가 같음.
- status·status --json·lint·report·trace·impact·SessionStart 훅은 원장·head·manifest·Gate 상태를 바꾸지 않음(`DefectClosureInvariant`).
- 무효 인용만 있는 결함은 0.1.3처럼 재평가 전제 조건에서 BLOCKED(기록 없음)(`DefectEvidenceChar`).

### 10.5 독립 검토 요약 (상세 WORKITEM §8, D36)
- F2: 주요 1(첫 수정본이 `sed >/dev/null 2>&1 -i …`류 쓰기를 통과시킴, bash로 원장 변조 확인) 외 3건 → 수정. 재검토 퍼저 2,483건에서 0.1.3 대비 손실 0. 0.1.3부터 있던 `x2>&파일` 빈틈 추가 수정. 알려진 오탐 2종은 D36.
- F3: 주요 2(깨진 증거로 status·lint·report 종료 코드 2, G4 재PASS가 G5 실패 결함을 종료) 외 → 수정. 재검토에서 수정이 만든 회귀 1건(오래된 결과가 최근 UNKNOWN을 가림)과 표현 문제 1건 → 수정, 재재검토 통과.
- F1: 주요 1(위와 같은 원인의 잘못된 CLOSED) 외 3건 → 수정, 재검토 통과. 반영하지 않은 1건: VERIFIED 이름 변경 제안(사용자 결정 사항).

### 10.6 Validator·Audit 확인: drill-3 실제 원장 (0.1.3 서명, 복사본)
명령: `python3 -I test-results/v0.1.4/drill3_check.py <drill-3> <work> dist/vmodel-0.1.3 dist/vmodel-0.1.4 <out>`. 결과: `test-results/v0.1.4/drill3-check-0.1.4.json`. 원본 샌드박스(이전 세션 스크래치, 서명 키 포함)는 읽기만 했고 다이제스트가 전후 같다. 앵커도 복사본 경로 이름으로 복사해 롤백 검사를 켠 상태로 확인했다. 모델 호출 없음(G5 재검증은 Validator가 pytest를 직접 실행).
- 0.1.3 기준선: PARTIALLY_VERIFIED, audit OK, 원장 18건, 증거 기록 6건.
- 0.1.4로 바꾸면 재고정 전 모든 Gate BLOCKED(무결성). 사용자 TTY 재고정(pty) → 원장에 lock 기록 1건.
- 재고정 뒤 audit OK, 0.1.3 증거 6건 `verify-evidence` 모두 OK. G1~G5 STALE("validator core changed"), DEFECT-001 `VERIFIED [claimed fixed; verified by R00013 but G5 is now STALE: re-verify]`, lint OK.
- 0.1.4로 G1~G5 재검증 → 모두 PASSED, `CLOSED [claimed fixed; verified by R00013, G5 PASSED (R00024)]`.
- P-F1 재확인(통과 뒤 status를 open으로 수정): G4·G5 STALE, `VERIFIED [claimed open; … G5 is now STALE: re-verify]` + `note: defects.json says open, …`. 0.1.3은 같은 상황에서 `[open; verified by R00013]`이었다(`test-results/drill/s3-drill-3/probe-f1-f2.json`).
- P-F2 재확인(TEST-011·012 링크 제거): `WARNING [unlinked_failing_test] … TEST-011, TEST-012`, lint 종료 코드 1, 경고 1건.
- 복원 후 CLOSED, 최종 audit OK(원장 24건, 증거 8건). 이전 18줄은 바이트 그대로이고, 기존 gate 기록은 모두 `0.1.3`/`0208c798…`, 새 기록은 `0.1.4`.

### 10.7 릴리스
- `python3 scripts/release.py` → `dist/vmodel-0.1.4/`(43개 파일, core `sha256:b1fee43f…`), `releases/vmodel-0.1.4.json`. 검토 반영으로 공개 전 한 번 `--force` 재빌드했다(첫 빌드 core `d53ca7c0…`는 버림, 기록 파일은 최종본만 커밋).
- 0.1.0~0.1.3 릴리스 사본 43개 파일씩 각 기록과 해시 일치, `releases/vmodel-0.1.0~0.1.3.json` git 변경 없음, 태그 `v0.1.2`·`v0.1.3` 그대로.

### 10.8 미검증·한계
- 0.1.4로 실제 Claude 세션(헤드리스·대화형)을 돌리지 않았다. guard 변경이 실제 세션의 auto 권한 분류기와 함께 어떻게 동작하는지는 미검증이다(하네스는 훅을 CLI로 직접 호출). 비용 승인 후 선택 사항.
- guard 알려진 오탐 2종과 두 버전 공통 미탐 목록(D36). guard는 최선 노력 보호다.
- Windows `NUL`·PowerShell `$null` 리디렉션 허용은 범위 밖(차단 유지).
- 0.1.4로 재고정한 프로젝트를 0.1.3으로 열면 무결성 BLOCKED다(코드상 동작, 실측은 업그레이드 방향만).
- Python 3.11 미검증(§6과 같음).


## 11. v0.1.4 최종 검증 (2026-11-09 2차: 결함 표시 상태 6종, 실제 Claude 세션, 릴리스 확정)

범위(사용자 지시): 결함 표시 상태 개선(DECISIONS D37), 0.1.4로 실제 Claude Code 세션 1회(sonnet, $1 상한), 최종 회귀, 릴리스 확정. G6/G7은 하지 않았다. §10의 기존 결과와 로그는 그대로 두고, 이번 결과는 새 파일에 남겼다.

### 11.1 커밋과 릴리스 빌드
- `48403ad`(§10) → `73d158e` 표시 상태 6종 → `c4e4da5` 독립 검토 지적 4건 → `e0358a5` 재검토 지적(Gate별 판단, `closure_action` 표기) → 문서·세션 스크립트 커밋.
- 0.1.4는 공개 전이라 같은 버전으로 다시 빌드했다(`release.py --force`). core는 `b1fee43f…`(첫 빌드, §10) → `144428fb…`(`73d158e`) → `f837a465…`(`c4e4da5`) → **`5dd1d010…`(`e0358a5`, 최종)**. 중간 빌드는 공개하지 않았고 `releases/vmodel-0.1.4.json`에는 최종본만 남는다.

### 11.2 RED → GREEN (`scripts/red_green.py`, 깨끗한 `e0358a5` worktree)
| 대상 | 결과 | 로그 |
|---|---|---|
| `test_defect_display_states` vs **첫 0.1.4 빌드**(core `b1fee43f…`, 해시 대조 후 보존한 사본) | 24/24 기대 충족: Red 18 FAIL(전부 assertion, ERROR 0), Char·Invariant 6 통과 | `v0.1.4/red-display-states-final.log` |
| 검토 지적 테스트 vs 수정 직전 빌드 | `73d158e` 빌드에서 6건, `c4e4da5` 빌드에서 1건(Gate별 판단) assertion 실패 확인 | 이 절 |
| `test_defect_closure`(기대값 변경 후) vs 0.1.3 | 15/15 기대 충족(Red 14 FAIL, Invariant 1) | `v0.1.4/red-F1-closure-recheck-final.log` |
| 0.1.4 모듈 GREEN(`guard_redirects`·`defect_closure`·`defect_evidence`·`version_compat`·`defect_display_states`) | **83/83**, 위반 0 | `v0.1.4/green-all-final.log` |

첫 빌드용 0.1.4 테스트 중 상태 이름 변경으로 기대값을 바꾼 것은 `test_defect_closure` 7개 메서드와 `test_version_compat` 1곳이다(D37). 기존 하네스 103개는 고치지 않았다. 중간 커밋 기준 로그(`*-73d158e*`, `*-c4e4da5*`)는 보존했다.

### 11.3 회귀
| 환경 | 커밋 | 결과 |
|---|---|---|
| WSL2 Ubuntu 24.04, Python 3.12.3, pytest, ruff (깨끗한 worktree) | `e0358a5` 최종 | **186/186 통과**, skip 0, 644초 (`wsl-harness-0.1.4-final.log`) |
| 같은 환경 | `c4e4da5` 중간 | 185/185 (`wsl-harness-0.1.4-c4e4da5.log`) |
| 같은 환경 | `73d158e` 중간 | 176/176 (`wsl-harness-0.1.4-73d158e.log`) |
| Windows 11, Python 3.13.14 venv, cp949, `%TEMP%\vmodel 한글 테스트\devkit-0.1.4-<커밋>`(`git archive` + 불변 `dist/vmodel-0.1.3`) | `e0358a5` 최종 | **186 실행, 실패 0, 오류 0, skip 6** (실측, 1560초, `windows-t18-harness-0.1.4-final.log`) |
| 같은 환경 | `c4e4da5` 중간 | 185 실행, 실패 0, skip 6 (`windows-t18-harness-0.1.4-c4e4da5.log`) |
| 같은 환경 | `73d158e` 중간 | 176 실행, 실패 0, skip 5 (`windows-t18-harness-0.1.4-73d158e.log`) |

Windows skip은 이전 5건(ruff 미설치 1, pty 2, 심볼릭 링크 권한 1, 재고정 pty 1)에 새 `test_three_strike_then_user_unblock_says_rework`(사용자 unblock에 pty 필요) 1건을 더한 것이다. 이 6건은 Windows에서 **미검증**이고 WSL에서는 통과했다.

### 11.4 실제 Claude Code 세션 (sonnet 1회, 승인 상한 $1)
- 설정: `scripts/e2e/live_session.py`. `--model sonnet`(실제 `claude-sonnet-5-5`), `--permission-mode auto`, `--permission-prompts none`, `--max-budget-usd 1`, `--plugin-dir dist/vmodel-0.1.4`(최종 릴리스 사본, 세션 init에 `vmodel 0.1.4`), `--setting-sources project,local`, `--no-session-persistence`. `--dangerously-skip-permissions`는 쓰지 않았다. Validator CLI만 `--allowedTools`로 허용했다(설치가 쓰는 allow 규칙과 같다. 헤드리스에서는 신뢰되지 않은 작업 공간이라 프로젝트 allow 규칙이 무시된다). 나머지는 guard 훅과 auto 모드가 판단했다. 비용을 한 번으로 묶으려고 서브에이전트 도구(Task, Workflow)는 막았다.
- 샌드박스: drill-3 프로젝트(0.1.3 실제 세션 산출물과 서명 원장, R00008은 D27의 주입 G4 승인)와 VMODEL_HOME을 세션 스크래치로 복사했다(원본은 읽기만 했고 다이제스트가 같다). SPEC §11 업그레이드 절차대로 플러그인 경로를 바꾸고, 사용자 TTY 재고정은 스크립트가 pty로 대신했다. 재고정 뒤 G1~G5 STALE, `DEFECT-001 REVERIFY_REQUIRED [claimed fixed; previously passed in R00013 (last PASS R00018), G5 is now STALE: re-verify]`, audit OK(19건).
- 사전 확인(모델 호출 없음): 프로브 17개 각각에 대해 릴리스 guard를 직접 호출해 기대 판정과 17/17 일치를 확인했다(`expect.json`).
- 결과: `subtype success`, **비용 $0.1506**, 30턴, 62초. 세션 1회만 실행했다.

| 구분 | 프로브 | guard 로그 | 최종 결과 |
|---|---|---|---|
| A 정상 명령 | A1 Read defects.json, A2 `cat … 2>/dev/null`, A3 `ls … >/dev/null 2>&1 && echo ok`, A4 `head … 2>/dev/null`, A5 `python3 -m pytest -q -p no:cacheprovider 2>&1 \| tail -n 3`, A6 Read head.json | 6/6 allow | 6/6 실행(pytest 18 passed). A2·A3은 0.1.3이 오탐으로 막던 명령. auto 분류기도 모두 허용 |
| B 보호 (Bash) | B3 `>>` 원장, B4 `&>` 증거, B5 `/dev/null`; 실제 쓰기, B6 `&& sed -i`, B7 `sed >/dev/null 2>&1 -i`, B8 `tee -a … </dev/null >/dev/null`, B9 `cp` → state, B10 `bash -c '… >>'` | 8/8 deny | 8/8 차단(`[vmodel guard] … would modify .vmodel/ through the shell`) |
| B 보호 (파일 도구) | B1 Edit head.json, B2 Write evidence/probe.txt | 기록 없음 | 2/2 차단. Claude Code 권한 설정이 guard보다 먼저 막았다("File is in a directory that is denied by your permission settings", 설치가 쓴 `Edit(/.vmodel/state/**)`·`Edit(/.vmodel/evidence/**)` deny 규칙). |
| K 알려진 오탐 | K1 `grep -c '&>' .vmodel/VMODEL.md` | deny | 차단(D36에 기록된 오탐, 읽기 명령) |

- 판정: **guard 우회 0건, 예상 밖 오탐 0건, 미실행 0건.** 세션 뒤 원장 앞 19줄은 바이트 그대로이고, 추가 기록은 Validator가 서명한 gate 기록 5건뿐이다(R00020~R00024). `.vmodel/state`에는 head.json·ledger.jsonl만 있고 프로브 파일은 생기지 않았다. 릴리스 트리 다이제스트도 세션 전후 같다.
- 정상 차단과 오탐 구분: B3~B10은 실제 쓰기(정상 차단), K1은 읽기인데 막힌 알려진 오탐, A2·A3은 0.1.3의 오탐이 0.1.4에서 허용으로 바뀐 것이다. B1·B2는 guard가 아니라 권한 deny 규칙(D06의 두 번째 보호층)이 막았다. 따라서 **guard의 Edit/Write 차단은 이번 실제 세션에서 확인되지 않았다**(오프라인 guard 호출과 하네스로만 확인). 대신 새 사실을 확인했다: 헤드리스의 신뢰되지 않은 작업 공간에서도 프로젝트 deny 규칙은 적용된다(allow 규칙만 무시된다).
- 워크플로우: `/vmodel:status` 스킬(Skill 도구) → status에서 REVERIFY_REQUIRED. `vmodel gate WI-001 G1`~`G5` → 모두 PASSED(R00020~R00024, G5는 Validator가 pytest를 직접 실행해 18/18). status → PARTIALLY_VERIFIED, `DEFECT-001 CLOSED [claimed fixed; verified by R00013, G5 PASSED (R00024)]`. audit OK(24건, 증거 8건). G5 증거 `verify-evidence` OK, lint OK.
- 상태와 증거의 일치: 세션 밖에서 Validator로 독립 확인했다(`inspect.json`). status(G1~G5 PASSED, R00024)와 원장의 마지막 G5 기록(R00024 PASSED, executed_tests 12개 모두 passed, core `5dd1d010…`), 그 증거의 verify-evidence OK, audit OK가 모두 맞다. 세션 모델의 최종 보고도 같은 결론이다.
- 관찰: 모델은 "한 단계에 한 호출" 지시와 달리 A·B 단계를 병렬 묶음으로 보냈다(스스로 보고함). 호출마다 입력은 지정한 그대로였다(명령 문자열 완전 일치로 매칭). 병렬 여부는 guard 판정에 영향이 없다.
- 산출물: `test-results/v0.1.4/live-session/`(setup·expect·prompt·summary·inspect·guard-log·transcript).

### 11.5 Validator·Ledger 무결성과 호환
- Gate 판정·manifest: 0.1.3 릴리스와 같은 재작업 이력에서 원장 투영과 Gate별 manifest가 같다(`GateDecisionInvariant`, GREEN에 포함). 표시 명령은 원장·head·manifest·Gate 상태를 바꾸지 않는다(`DisplayStateInvariant`, `DefectClosureInvariant`).
- 기존 서명 원장: 0.1.3이 서명한 drill-3 원장(18건, 증거 6건)이 최종 0.1.4에서 재고정 뒤 audit OK이고, 실제 세션 뒤에도 audit OK(24건)다. 기존 기록의 `validator.version`·`core_hash`는 0.1.3 값 그대로다. 하네스 `OldEvidenceAccept`도 통과했다(WSL).
- 원장 무결성 위반 시 표시: 서명이 깨진 원장 → UNKNOWN(CLOSED·VERIFICATION_FAILED 상태 모두에서 시작해 확인).
- JSON 호환: 0.1.3·첫 0.1.4 키는 모두 남는다. 추가 키는 `verification_history`, `last_verification`, `closure_action`이다. `closure_state` 값 VERIFIED는 없어졌다(0.1.4 미공개).

### 11.6 버전·릴리스 정합성
- `VERSION`, `plugin.json`, `RELEASE_MANIFEST.json`, `releases/vmodel-0.1.4.json`, 마켓플레이스 항목이 모두 0.1.4다. core `sha256:5dd1d010…`이 manifest와 기록에서 같고, 릴리스 사본 자가 점검은 integrity OK다.
- 43개 파일 해시가 소스 `plugins/vmodel`, `dist/vmodel-0.1.4`, 기록에서 모두 일치한다. 0.1.0~0.1.3 사본은 각 기록과 43개 파일씩 일치하고 기록 파일은 git 변경이 없다. 태그 `v0.1.2`→`bbd6a3d`, `v0.1.3`→`0df13b7`은 그대로다.
- `claude plugin validate --strict`: `plugins/vmodel`과 `dist/vmodel-0.1.4` 모두 통과했다(README 마켓플레이스 설치 줄 권고 1건은 이전과 같음).

### 11.7 미검증·남은 위험
- guard의 Edit/Write 차단은 실제 세션에서 guard까지 가지 않았다(권한 deny 규칙이 먼저 막음). 신뢰된 작업 공간에서 allow 규칙이 적용되는지는 여전히 미검증이다.
- 실제 세션은 auto 권한 모드 헤드리스 1회뿐이다. 대화형, 기본 권한 모드, Windows의 Claude Code 세션은 미검증이다.
- 의도적으로 실제 세션에서 다시 시험하지 않은 것: 문자열 난독화(`.vmodel`을 변수로 조립 등), heredoc·python 하위 프로세스 쓰기. guard는 문자열 기반 최선 노력 보호이고 서명·앵커·audit이 최종 탐지 장치다(D25, D36의 두 버전 공통 미탐). 이 한계는 이번 릴리스에서 바뀌지 않았다.
- 표시 상태의 알려진 한계(D37): 교차 Gate 증상을 함께 인용하면 수정 시도 없이도 VERIFICATION_FAILED로 보인다. Gate 단위 판단이라 다른 결함 소유의 실패도 반영된다. 둘 다 완료로 보이지 않는 쪽이다. `verification_history`에는 보류된 PASS가 표시 없이 들어 있다.
- 업그레이드 시 프로젝트 `.claude/settings.json`의 allow·deny 규칙은 이전 릴리스 경로(예: `dist/vmodel-0.1.3`)를 가리킨 채 남는다. Core 보호는 guard의 Core 경로 검사가 맡지만, 설정 갱신 절차는 SPEC §11에 없다(관찰, 이번 범위 밖).
- Python 3.11 미검증(§6).


## 12. v0.1.5 후보: 업그레이드 시 권한 규칙 이동 (2026-11-09, 브랜치 `v0.1.5-dev`, 실제 Claude 세션 없음)

범위(사용자 지시): 업그레이드 뒤 프로젝트 `.claude/settings.json`의 allow·deny 규칙이 이전 릴리스 절대경로를 가리키는 문제의 재현과 수정(DECISIONS D38, `docs/v0.1.5/WORKITEM.md`). 모델 호출이 드는 헤드리스 실행은 하지 않았다(비용 0). main 병합·태그·원격 푸시는 하지 않았다. G6은 설계 결정안만(D39).

### 12.1 재현 (모델 호출 없음, 실제 릴리스 사본)
`python3 -I test-results/v0.1.5/upgrade_repro.py <old> <new> <out>`. 한글·공백 경로의 임시 프로젝트, 임시 VMODEL_HOME, 사용자 settings(사용자 allow 2개 중 하나는 이전 릴리스 경로 언급, deny 1개, env) 위에 설치. 사용자 TTY는 pty로 대신했다.
- 0.1.3 → 0.1.4(수정 전 코드, `repro-0.1.3-to-0.1.4.json`): SPEC §11 절차(새 릴리스로 재고정) 뒤 lock은 0.1.4인데 settings.json은 바이트 그대로였다. deny `Edit(//…/dist/vmodel-0.1.3/**)`와 0.1.3 CLI allow 2개가 남고 0.1.4 경로 규칙은 0개, 설치 기록 `plugin_root`도 0.1.3. 새 Core는 guard만 막았다(guard 직접 호출 deny). README 절차(옛 uninstall → 새 install) 사이에는 DevKit deny 규칙이 0개였다. 새 릴리스로 install하면 "run 'vmodel uninstall' first"로 그 절차를 안내했다.
- 0.1.4 → 0.1.5(수정본 릴리스 사본, `repro-0.1.4-to-0.1.5.json`): 재고정 출력 `re-pinned core 37071459bd44 (validator 0.1.5)`, `4 DevKit rule(s) added, 3 removed; your own rules unchanged`, 백업 경로. 이전 릴리스 deny·CLI allow 0개, 새 릴리스 Core deny 1개·CLI allow 2개, 0.1.4 경로를 언급하는 사용자 규칙은 남음, 설치 기록 `plugin_root` 0.1.5, 새 Core에 대한 guard deny, status 무결성 OK, 이어서 uninstall하면 원래 사용자 settings와 같다. 새 릴리스로 install하면 재고정을 안내하고 settings는 그대로다. (README의 옛 uninstall → install 절차 자체의 공백은 그대로라 문서에서 그 절차를 뺐다.)

### 12.2 RED → GREEN (`scripts/red_green.py`, 깨끗한 `aae9a99` worktree, 로그 `test-results/v0.1.5/`)
| 모듈 | RED 대상 | RED 결과 | GREEN |
|---|---|---|---|
| `test_upgrade_settings` (요구사항 U1~U9) | 불변 릴리스 `dist/vmodel-0.1.4`(core `5dd1d010…`) | 15/15 기대 충족: Red 10 FAIL(전부 assertion), Char·Invariant 5 통과 (`red-upgrade-settings-final.log`) | 통과 |
| `test_upgrade_review` (1차 검토 지적) | 첫 수정본 `0e691d0` 사본(`git archive`, 검토 worktree와 diff 동일) | 12/12: Red 10 FAIL, Char 2 통과 (`red-review-0e691d0-final.log`) | 통과 |
| `test_upgrade_review2` (재검토 지적) | `c57f7c5` 사본 | 5/5: Red 2 FAIL, Char 3 통과 (`red-review2-c57f7c5-final.log`) | 통과 |
| `test_upgrade_review3` (세 번째 확인 지적) | `be372f4` 사본 | 3/3: Red 2 FAIL, Char 1 통과 (`red-review3-be372f4-final.log`) | 통과 |
| 위 4개 모듈, 대상 = 빌드한 릴리스 사본 `dist/vmodel-0.1.5`(core `37071459…`) | — | — | 39/39 (`green-upgrade-release-0.1.5.log`) |
| 0.1.4 모듈 5개 + 위 4개, 대상 = 소스 | — | — | 122/122, 위반 0, skip 0, 537초 (`green-all-final.log`) |

Accept 클래스(프로세스 내 API 직접 호출, 0.1.4 → 0.1.5 교차 버전 uninstall, 두 번째 업그레이드 무변경, 업그레이드 뒤 G1~G5 재검증·audit)는 RED 대조에서 빠지고 GREEN에서만 확인했다. 수정 전 빌드마다 RED를 먼저 확인한 로그(작업 중 생성)도 같은 폴더에 남겼다(`red-upgrade-settings.log`, `red-review-0e691d0.log`, `red-review2-c57f7c5.log`, `red-review3-be372f4.log`).

### 12.3 회귀
| 환경 | 커밋 | 결과 |
|---|---|---|
| WSL2 Ubuntu 24.04, Python 3.12.3, pytest, ruff (깨끗한 worktree) | `aae9a99` 최종 | **225/225 통과**, skip 0, 747초 (`wsl-harness-0.1.5-final.log`) |
| 같은 환경 | `be372f4` 중간 | 222/222, skip 0, 727초 (`wsl-harness-0.1.5-be372f4.log`) |
| 같은 환경 | `c57f7c5` 중간 | 217/217, skip 0, 674초 (`wsl-harness-0.1.5-c57f7c5.log`) |
| 같은 환경 | `0e691d0` 첫 수정본 | 205/205, skip 0, 671초 (`wsl-harness-0.1.5-0e691d0.log`) |
| Windows 11, Python 3.13.14 venv, cp949, `%TEMP%\vmodel 한글 테스트\devkit-0.1.5-aae9a99`(`git archive` + 불변 `dist/vmodel-0.1.3`·`0.1.4`) | `aae9a99` 최종 | **225 실행, 실패 0, 오류 0, skip 40** (실측, 1641초, `windows-t18-harness-0.1.5-final.log`) |

Windows skip 40 = 이전과 같은 6건(ruff 미설치 1, pty 4, 심볼릭 링크 권한 1) + pty가 필요한 신규 34건(`test_upgrade_settings` 17, `test_upgrade_review` 10, `test_upgrade_review2` 4, `test_upgrade_review3` 3). 이 34건은 Windows에서 **미검증**이고 WSL에서는 통과했다. Windows에서 실제로 돈 신규 5건(`UpgradeSettingsInProcessAccept`, `UpgradeSettingsInvariant`, `UpgradeReviewInProcessRed`·`Char`, `UpgradeReview2InProcessRed`)은 `//c/...` 규칙으로 통과했다.

기존 0.1.4 하네스 186개는 기대값을 바꾸지 않았다. 신규는 `test_upgrade_settings` 19, `test_upgrade_review` 12, `test_upgrade_review2` 5, `test_upgrade_review3` 3. pty가 필요한 클래스는 Windows에서 skip이고, Windows에서는 프로세스 내 API 테스트(`UpgradeSettingsInProcessAccept`, `UpgradeReviewInProcessRed/Char`, `UpgradeReview2InProcessRed`)와 guard 불변식이 드라이브 경로(`//c/...`)로 돈다.

### 12.4 보호 정책 유지
- `hook.py`는 0.1.4 릴리스와 바이트 동일하다(`UpgradeSettingsInvariant`가 확인). `gates.py`·`ledger.py`·`runner.py`·`status.py`·`integrity.py`·`data/`(gates.json, 스키마)·`hooks/`·`bin/`도 `991af67` 대비 변경 없음(`git diff`). 변경은 `setup_project.py`·`cli.py`·버전 두 곳뿐이다.
- 업그레이드 뒤에도 guard가 에이전트의 `lock --accept-current`·`install`·`uninstall`(`--purge` 포함)을 막고, 실행 중 Core·hooks·설치 기록·lock·원장 쓰기를 막는다(불변식 테스트).
- deny 규칙은 줄지 않았다. 생성 deny 규칙에 업그레이드 백업 폴더 `Edit(/.vmodel/install/**)`가 추가됐다(검토 지적 8). 업그레이드는 deny를 먼저 추가하고 이전 것을 나중에 지우며, 사용자가 지운 DevKit deny 규칙도 다시 넣는다.
- 하위 명령 옵션 축약을 막아 `lock --accept`처럼 guard의 사용자 전용 문자열(`accept-current`)을 피하는 호출이 argparse 오류가 된다(`allow_abbrev=False`, 기존부터 있던 빈틈, TTY 확인이 마지막 방어선이었다).
- Gate 판정·원장 기록 형식·manifest 계산은 그대로다(`test_version_compat` GREEN, `GateDecisionInvariant` 포함). 재고정은 원장 기록 → lock 순서로 바뀌었지만 기록 내용은 같고, `type: lock` 기록을 읽는 판정 코드는 없다(재검토 확인).

### 12.5 릴리스·증거 보존
- `dist/vmodel-0.1.0`~`0.1.4` 사본은 각 기록과 43개 파일씩 일치, `releases/vmodel-0.1.0~0.1.4.json` git 변경 없음. 태그 `v0.1.2`→`bbd6a3d`, `v0.1.3`→`0df13b7`, `v0.1.4`→`991af67` 그대로, `main`=`991af67` 그대로. 서명된 이전 원장·증거를 다시 쓰는 경로는 추가하지 않았다(업그레이드 뒤 audit OK, 기존 원장 앞부분 바이트 유지: `test_gates_still_pass_after_upgrade`).
- 0.1.5 후보: `python3 scripts/release.py` → `dist/vmodel-0.1.5/`(43개 파일, core `sha256:37071459bd44…`), `releases/vmodel-0.1.5.json`, 마켓플레이스 항목 0.1.5(`dist/`는 git 제외). 태그는 만들지 않았다. 공개 전이므로 확정 전에 바뀌면 `--force`로 다시 빌드한다.
- `claude plugin validate --strict`: `plugins/vmodel`, `dist/vmodel-0.1.5` 통과.

### 12.6 독립 검토
별도 컨텍스트의 검토자(읽기 전용, 자기 임시 폴더에서 실험)를 세 번 돌렸다. 1차(`0e691d0`) 지적 12건 + 의심 3건, 재검토(`c57f7c5`) 부 1건 + nit 3건, 세 번째(`be372f4`) 부 1건 + nit 1건. 재현한 것은 모두 그 빌드에서 실패하는 테스트로 먼저 고정한 뒤 고쳤다. 반영하지 않은 것 2건(같은 문자열 중 첫 번째 제거, 이전 CLI로 재고정할 때의 deny 공백)은 근거와 함께 D38·WORKITEM §7에 남겼다. 이 세션에서 직접 찾은 것도 둘이다: 1단계 쓰기 순서(소유권을 settings보다 먼저), 보류 결정이 다음 재고정에서 사라지는 문제(`declined_allow`).

### 12.7 미검증·남은 위험
- 실제 Claude Code 세션에서 업그레이드한 프로젝트를 쓰는 것은 확인하지 않았다(비용 승인 필요). 특히 새 CLI allow 규칙이 신뢰된 작업 공간에서 실제로 권한 확인을 없애는지는 §11.7과 같이 미검증이다.
- 마켓플레이스로 등록해 Claude Code가 플러그인을 다른 경로(캐시 등)에서 실행하면 규칙이 가리켜야 할 경로가 달라질 수 있다. 미검증(§6과 같은 항목).
- Windows의 업그레이드 경로 중 pty가 필요한 것(TTY 확인, Ctrl-C, 계획 대조)은 Windows에서 돌리지 않았다. 설정 재작성·복원 로직은 프로세스 내 테스트로 Windows 경로에서 확인했다. Claude Code가 settings.json을 연 채로 있을 때 Windows `os.replace` 동작은 미실측이다(검토자는 libuv가 FILE_SHARE_DELETE로 연다고 판단했다. 실패해도 재고정 전이면 복원된다).
- 0.1.4 이하로 내리는 다운그레이드는 자동화하지 못했다(수동 절차, uninstall과 install 사이 규칙 공백). 0.1.5 업그레이드 뒤 이전 CLI로 재고정하면 그 동안 deny 규칙이 고정된 릴리스를 가리키지 않는다(D38 한계).
- 원장 기록 뒤 실패(앵커 쓰기 실패 등)는 되돌리지 않고 이전+새 규칙으로 남긴다. 이때 원장에는 효력이 없는 lock 기록이 남을 수 있다(사실대로 안내, 재실행으로 마무리). SIGKILL 같은 강제 종료 시점별 상태는 코드 검토와 상태 구성 테스트로만 확인했다.
- 롤백 중 두 번째 Ctrl-C 무시는 결정적 테스트가 없다(코드 검토).
- 심볼릭 링크인 settings.json은 원자적 교체로 일반 파일이 된다(install부터 있던 동작).
- Python 3.11 미검증(§6).


## 13. v0.1.5 확정 검증 (2026-11-09, 사용자 조건부 승인, 실제 Claude 세션 없음)

사용자 승인 조건: 필수 검증(버전 일치, 릴리스·manifest 해시, 업그레이드 권한 공백, 사용자 규칙 보존, 서명 원장·Gate 판정 호환, 현재 소스 전체 회귀)이 통과하면 `main`에 `--ff-only` 병합하고 최종 검증 커밋에 annotated 태그 `v0.1.5`. 기존 태그·릴리스 기록 수정 금지, 원격 푸시 금지, 유료 헤드리스 세션 없음. 아래는 모두 이 PC에서 실제로 실행한 결과다.

### 13.1 출발 상태
- 브랜치 `v0.1.5-dev` = `8f0eaae`(문서), 마지막 코드 커밋 `aae9a99`, `main` = 태그 `v0.1.4` = `991af67`, `main`은 `8f0eaae`의 조상(fast-forward 가능). 예상과 같다.
- `aae9a99`와 `8f0eaae`의 트리 해시가 `plugins`(`b6afbdf`), `tests`(`7777682`), `scripts`(`984cc85`) 모두 같다. 그 사이 변경은 문서·검증 기록·`releases/vmodel-0.1.5.json`뿐이다.

### 13.2 버전·릴리스 해시 (`test-results/v0.1.5/release_check.py`, 결과 `release-check-pre-merge.json`)
Validator 코드를 쓰지 않고 hashlib로 다시 계산했다(파일별 sha256, Core 해시 = validator·hooks·bin 파일 표의 정규 JSON sha256). 각 릴리스 사본의 자가 점검(`bin/vmodel version`)도 함께 비교했다.
- `dist/vmodel-0.1.0`~`0.1.5`: 사본 43개 파일이 각 `releases/vmodel-<ver>.json`과 일치, 사본의 `RELEASE_MANIFEST.json` = 기록, 다시 계산한 Core 해시 = 기록 = 자가 점검 값, 자가 점검 `integrity_ok: true`. 0.1.5 core `sha256:37071459bd445eb9…`.
- 소스 `plugins/vmodel` 43개 파일 = 0.1.5 기록.
- 버전 문자열: `VERSION`, 소스·사본 `plugin.json`, 릴리스 기록, 마켓플레이스 항목(`./vmodel-0.1.5`) 모두 0.1.5.
- `releases/vmodel-0.1.0~0.1.4.json`은 태그 `v0.1.4` 이후 변경 없음. 태그 `v0.1.2`→`bbd6a3d`, `v0.1.3`→`0df13b7`, `v0.1.4`→`991af67` 그대로. `v0.1.4` 대비 바뀐 플러그인 파일은 `plugin.json`, `__init__.py`, `cli.py`, `setup_project.py` 4개다.

### 13.3 업그레이드 권한 공백·사용자 규칙 (`upgrade_gap_probe.py`, 결과 `upgrade-gap-probe-0.1.4-to-0.1.5.json`)
실제 릴리스 사본 `dist/vmodel-0.1.4`로 설치한 프로젝트(한글·공백 경로, 임시 VMODEL_HOME, 사용자 allow 2개(하나는 0.1.4 경로 언급)·deny 1개·env)에 0.1.5의 업그레이드 트랜잭션을 별도 프로세스로 실행하고, 파일 쓰기와 원장 기록 직후마다 디스크 상태를 확인했다. I1 지금 lock이 가리키는 릴리스의 Core deny 규칙이 settings에 있음, I2 0.1.4가 쓴 `.vmodel`·VMODEL_HOME 보호 deny 규칙이 모두 있음, I3 사용자 allow·deny가 순서대로 모두 있음.
- 정상 경로: 쓰기 지점 6개(설치 기록 → settings 추가 → 원장 lock 기록 → lock 파일 → settings 제거 → 설치 기록 확정) 모두에서 I1~I3 성립. 끝 상태: 0.1.4 Core deny 없음, 0.1.5 Core deny 있음, 사용자 규칙 유지. 강제 종료(SIGKILL)는 두 쓰기 사이에서만 일어나므로 이 6개 상태가 남을 수 있는 상태 전부다.
- 지점마다 쓰기 직후 KeyboardInterrupt(새 샌드박스 6개): 원장 기록 전 3개 지점은 바이트 복원, 그 뒤 3개 지점은 상위 집합 또는 완료 상태로 남고, 6개 모두 I1~I3 성립. 같은 명령을 다시 실행하면 6개 모두 새 규칙만 남고 사용자 규칙 유지.
- 관찰(nit, 고치지 않음): settings 제거 쓰기 직후에 중단되면 안내 문구가 ".claude/settings.json keeps the old and the new rules"라고 하지만 실제로는 이전 규칙이 이미 지워진 상태다. 보호는 유지된다(새 규칙 있음, 재실행으로 마무리). 릴리스를 바꾸지 않으므로 다음 버전 후보로 기록한다.

### 13.4 서명 원장·Gate 판정 호환
- 릴리스 사본 대상 GREEN(`scripts/red_green.py --mode green --plugin dist/vmodel-0.1.5`, 로그 `green-release-confirm-0.1.5.log`): `test_upgrade_settings`, `test_upgrade_review`, `test_upgrade_review2`, `test_upgrade_review3`, `test_version_compat` **42/42 기대 충족, 위반 0**, 91.8초. 여기에 `GateDecisionInvariant`(0.1.3과 같은 이력에서 원장 투영·manifest 동일), `OldEvidenceAccept`(0.1.3이 서명한 원장·증거가 새 코어에서 검증), `test_gates_still_pass_after_upgrade`, `test_user_settings_survive_upgrade_and_uninstall`, `test_upgrade_from_014_release_then_014_uninstall`이 포함된다. 로그의 `worktree_dirty: true`는 이번에 추가한 `test-results/v0.1.5/` 프로브 파일(추적 전) 때문이며 플러그인·테스트 파일은 커밋 상태 그대로다.
- 리뷰 유지 확인(`upgrade_review_cost_probe.py`, 결과 `upgrade-review-cost-0.1.4-to-0.1.5.json`): 0.1.4 릴리스로 설치해 G1~G5 PASS한 프로젝트를 0.1.5로 재고정(pty)한 뒤 새 리뷰 없이 재평가했다. 0.1.4가 쓴 원장 10건이 바이트 그대로 앞부분에 남고 audit OK. G1~G3은 PASSED(리뷰 대상 해시가 그대로), **G4는 REVIEW_REQUIRED**(리뷰 대상 해시 불일치). 원인: 업그레이드가 `.claude/settings.json`의 DevKit 규칙을 옮기고, 이 파일은 G4/G5 코드 manifest에 들어 있다(`project.py` 제외 목록에 `.claude` 없음). 같은 프로브로 0.1.3 → 0.1.4를 돌리면 settings가 바뀌지 않아 G1~G5가 리뷰 없이 모두 PASSED였다. 즉 **0.1.5부터 업그레이드마다 WI당 G4 verifier 리뷰가 한 번 더 든다.** D38의 "추가 비용은 없다"는 재실행 비용에만 맞고 리뷰 비용에는 틀렸다(D40에서 정정, SPEC §11·README 업그레이드 절에 반영). Gate 판정 규칙·원장 형식은 바뀌지 않았고 보호 공백도 아니므로 확정을 막는 실패로 보지 않았다. 해결 여부는 G6 설계의 사용자 결정 항목으로 넘겼다(`docs/g6/G6-DESIGN.md` §9 4번).

### 13.5 전체 회귀
| 환경 | 커밋 | 결과 |
|---|---|---|
| WSL2 Ubuntu 24.04, Python 3.12.3, pytest, ruff (깨끗한 detached worktree, dirty 0) | `8f0eaae` | **225/225 통과**, skip 0, 718초 (`wsl-harness-0.1.5-release-8f0eaae.log`) |
| Windows 11, Python 3.13.14 venv, cp949 | `aae9a99` (§12.3) | 225 실행, 실패 0, skip 40. 이번에 다시 돌리지 않았다. `8f0eaae`·확정 커밋과 `plugins`·`tests`·`scripts` 트리가 같으므로 그 결과가 같은 코드에 대한 것이다 |

### 13.6 병합·태그
이 기록을 담은 커밋을 최종 검증 커밋으로 하고, 그 뒤에 `git merge --ff-only`로 `main`을 옮기고 그 커밋에 annotated 태그 `v0.1.5`를 만든다. 최종 SHA와 병합 후 재확인 결과는 HANDOFF와 다음 기록(`test-results/v0.1.5/release-check-post-tag.json`)에 남긴다. 원격 푸시는 하지 않는다.

### 13.7 미검증·남은 위험 (확정 후에도 그대로)
- 실제 Claude Code 세션에서 업그레이드한 프로젝트를 쓰는 것(새 CLI allow 규칙이 신뢰된 작업 공간에서 권한 확인을 없애는지 포함)은 확인하지 않았다(유료 세션 없음).
- Windows의 pty 경로(업그레이드 TTY 확인·Ctrl-C·계획 대조 등 34건 + 기존 6건)는 Windows에서 돌리지 않았다. Windows에서 Claude Code가 settings.json을 연 채로 있을 때의 원자적 교체는 미실측.
- 마켓플레이스 캐시 경로에서 실행될 때 규칙이 가리킬 경로, 다운그레이드 자동화 없음(수동 절차의 규칙 공백), Python 3.11은 §12.7과 같이 미검증이다.
- 업그레이드마다 G4 재리뷰 비용(§13.4), 제거 직후 중단 시 안내 문구 부정확(§13.3)은 알려진 한계로 남는다.

## 14. v0.2.0 후보: G6 Integration Verification (2026-11-09, 브랜치 `g6-dev`, 실제 Claude 세션 없음)

사용자 지시("VModel DevKit v0.2.0 — G6 Integration Verification 개발", 결정 D1~D8 승인)에 따라 G6을 구현해 v0.2.0 후보를 만들었다. main 병합·`v0.2.0` 태그·원격 푸시·유료 헤드리스 실행은 하지 않았다. 절차·요구사항·검토 처리표는 `docs/g6/WORKITEM.md`, 결정은 D42·D43, 로그는 `test-results/v0.2.0/`. 아래는 모두 이 PC에서 실제로 실행한 결과다(하네스는 Claude 없이 사용자·verifier 역할을 대신한다: 그 부분은 시뮬레이션이다).

### 14.1 출발 상태
- Git: `main` = 태그 `v0.1.5` = `78517d5`, `g6-dev` = `fe38239`(설계 문서). 예상과 같았다.
- 기준 하네스(`fe38239`, WSL): **225/225**, 690초.
- 테스트 도우미 변경(G4 리뷰에 `interfaces`, 스냅샷 등)을 0.1.5 릴리스 사본에 돌린 결과 225 중 223 통과, 오류 2는 `copy_plugin`이 읽기 전용 릴리스 파일을 복사해 쓰기 실패한 테스트 환경 문제(`existing225-helpers-c6bc3ce-on-0.1.5.log`). `copy_plugin`이 사본을 쓰기 가능하게 바꾸도록 고쳤다.

### 14.2 RED → GREEN (`scripts/red_green.py`, 0.2.0에서 `--marker RED-TARGET` 추가: 목표 assertion이 아닌 실패는 위반)
| 대상 | 커밋(깨끗한 worktree) | 결과 | 로그 |
|---|---|---|---|
| G6 하네스 10개 모듈 → 불변 `dist/vmodel-0.1.5` | `c6bc3ce`, `aab3422` | 75 중 70, 72: 테스트 도우미 결함(`re.sub` 역슬래시, C2 비교 방식, test_changes 정당화 누락)이 드러나 테스트를 고침 | `red-c6bc3ce.log`, `red-aab3422.log` |
| 같은 모듈 → `dist/vmodel-0.1.5` | `3239eba`, `08469ae`, `14b34af` | **76/76**, 위반 0 (실패 사유도 확인: G6 미구현 BLOCKED, G4가 placeholder·import-only 통과, G5가 통합 테스트 수용, init 옵션 없음) | `red-3239eba.log`, `red-14b34af-on-0.1.5.log` |
| 검토 1회차 테스트 → 검토 빌드 `3239eba` | `5e64974` | **19/19**(Red 18 + D43 특성 1) | `red-review-5e64974-on-3239eba.log` |
| 검토 2회차 테스트 → `c216910` | `14b34af` | **19/19** | `red-review2-14b34af-on-c216910.log` |
| 검토 3회차 테스트 → `08469ae` | `14b34af` | **13/13** | `red-review3-14b34af-on-08469ae.log` |
| GREEN(전 G6·검토 모듈, 소스) | `14b34af` | **135/135** | `green-14b34af.log` |
| GREEN(같은 모듈 + 업그레이드·호환 모듈, 릴리스 사본 `dist/vmodel-0.2.0`) | 작업 트리(코드는 `14b34af`와 같음) | **177/177** | `green-release-0.2.0.log` |

### 14.3 사용자 테스트 T01~T20 대응 (모두 자동화, 하네스)
T01 `test_g6_gate` T01, T02 T02, T03 `test_g6_config` T03, T04 gate T04·T04b, T05 `test_g6_scope` T05 2건, T06 `test_g6_wiring` T06 2건 + 검토 F1·placeholder, T07 wiring T07·gate T07·T07b, T08 wiring T08 + 검토 F2, T09 wiring T09 5건(선언 없음·subprocess·API·해시 불일치·provider 미실행) + 검토 N2(fork)·R2(fixture 서버), T10 `test_g6_applicability` T10, T11 T11 3건, T12 `test_g6_rework` T12(OUT_OF_SCOPE), T13 T13, T14 `test_g6_compat` T14 2건, T15 T15, T16 T16(pty), T17 C1/C2/T17, T18 gate T18 5건 + 검토 N4, T19 `test_g6_encoding` 2건(Windows에서 실제 실행), T20 config InitRed 6건·MigrationRed 4건(pty)·compat T20(0.1.5 릴리스 → 0.2.0 재고정·`configure-tests`·G6, pty). 실행 증거 표본: `g6-demo-release-0.2.0.txt`(릴리스 사본, 모델 호출 없음).

### 14.4 독립 검토 3회 (별도 컨텍스트, 작업 트리 읽기 전용, 사본에서 재현)
| 회차 | 대상 | 지적 | 처리 |
|---|---|---|---|
| 1 | `3239eba` | 12(주요 7) | 직접 재현 후 수정 `c216910` (WORKITEM §7.1) |
| 2 | `c216910` | 1회차 중 닫힘 6·부분 5, 새 11(주요 10) + 0.1.x 내부 오류 2 | 재현 후 수정 `08469ae` (§7.2) |
| 3 | `08469ae` | 2회차 중 닫힘 9·부분 5, 새 14(주요 7) | 테스트별 실행 귀속의 한계를 인정하고 판정 규칙을 정리(D43), 재현 후 수정 `14b34af` (§7.3) |
3회차 수정 자체는 독립 재검토를 받지 않았다(§14.9).

### 14.5 전체 회귀
| 환경 | 코드 | 결과 |
|---|---|---|
| WSL2 Ubuntu 24.04, Python 3.12.3, pytest 9.0.3 (깨끗한 detached worktree) | `14b34af` | **360/360 통과**, skip 0, 1051초 (`wsl-harness-14b34af.log`) |
| 같음 | `08469ae`, `c216910` | 346/346, 327/327 |
| Windows 11, Python 3.13.14 venv, cp949, 한글·공백 경로 | `5e64974`(코드 = `14b34af`) | **360 실행, 실패 0**, skip 48, G6 모듈 122개 실제 실행·통과 (`windows-harness-5e64974.log`) |
| 같음 | `54eac4c`(코드 = `08469ae`), `c216910`, `3239eba` | 346 실행·실패 0·skip 48 / 327 실행·실패 1(아래)·skip 46 / 308 실행·실패 0·skip 46 |
- Windows `c216910`의 실패 1과 WSL 부하 중 1회 실패는 같은 원인이었다: `test_g6_scope` D4가 G5.EXECUTION의 pytest 출력 꼬리(소요 시간 포함)를 비교했다. 테스트 결함이며 고쳤다(`54eac4c`). 제품 결함 아님.
- Windows skip은 pty가 필요한 사용자 전용 경로(재고정, `configure-tests`, unblock 등), 권한이 필요한 심볼릭 링크, ruff 없음이다.

### 14.6 실제 Integration Test 실행 증거 (릴리스 사본, `g6-demo-release-0.2.0.txt`)
- 경로 A: `{python} -m pytest -q -p no:cacheprovider tests/integration --junitxml=…`를 Validator가 직접 실행, 종료 0, 3 passed, G6.SCOPE에 unit ID 없음, IF 2/2. 서명된 증거에 `kind: integration_test`, `command_source: integration_test`, `junit.xml`, `stdout/stderr.bin`, `trace-spec.json`, `trace/<pid>-….jsonl`(해시). `verify-evidence`·`audit` OK.
- 경로 B: TEST-012가 `python -m pipeline.report`를 하위 프로세스로 실행. 선언 없으면 G4 REVIEW_REQUIRED, verifier 선언(테스트 파일 해시) 후 G4 PASSED, G6 PASSED(IF-002 `runtime`, 자식 프로세스의 계측 파일에서 provider 실행 확인).
- 실패 → 재작업: consumer가 parser의 ValueError를 삼키게 심으면 unit은 통과하고 G6 FAILED(TEST-011). DEFECT 없이 재평가는 기록 없이 BLOCKED, DEFECT(G6, P4) → 수정 → G6 PASSED, 결함 CLOSED.

### 14.7 N/A·OUT_OF_SCOPE·G5/G6 분리·호환
- N/A: 단일 컴포넌트에서 G2·G3 리뷰 확인 전에는 BLOCKED `applicability_unconfirmed`, 확인 후 `G6 N/A`(기록은 PASSED + `not_applicable`, 실행 체크 skip, 증거 없음). 출력·status·report에 "integration tests passed"·"G1-G5 verified" 없음. IF를 `removed_ids` 없이 지우면 N/A 불가(T11).
- OUT_OF_SCOPE: G6 실패 결함 뒤 CR로 IF·통합 TEST를 지우고 G2·G3가 확인하면 결함은 CLOSED가 아니라 OUT_OF_SCOPE, `verified_by` 없음, CR 연결, FAILED 기록 보존(T12).
- G5/G6: `integration_test` 설정 시 unit 명령이 integration 테스트를 실행하면 G5.SCOPE FAILED, G6 명령이 unit 테스트를 실행하면 G6.SCOPE FAILED, integration ID가 G5에서 빠지는 것은 약화 아님, unit ID가 빠지면 지금처럼 약화. 설정이 없는 기존 프로젝트의 G5 기록은 0.1.5와 같음(D4 불변식), 섞인 실행은 경고만.
- 호환: IF 없는 WI의 G1~G5 판정 투영과 manifest가 0.1.5와 같음(C1/C2), 0.1.5가 서명한 원장·증거가 새 코어에서 검증됨(T17), 0.1.5 → 0.2.0 재고정 후 이전 기록 바이트 유지·G1~G5 STALE(Core 교체, D1)·G6 평가 전(T20, 릴리스 사본끼리도 통과). 0.1.x에서 상속한 원장 판독·JSON 판독의 내부 오류 2건(P1·R10)은 오류 보고로 바꿨다.

### 14.8 릴리스 후보
- `python3 scripts/release.py` → `dist/vmodel-0.2.0/`(45개 파일, tracer·wiring 포함), `releases/vmodel-0.2.0.json`, core `sha256:f835ec913b6a885f1f1eb297981142878f1c81c49e649231ef69ce26ff09eb5f`.
- `test-results/v0.2.0/release_check.py`(Validator 코드 없이 hashlib로 재계산): 0.1.0~0.2.0 사본·기록·자가 점검 일치, 소스 = 0.2.0 기록, 버전 문자열 일치, 0.1.x 기록 불변, 태그 `v0.1.2`~`v0.1.5` 불변, `v0.2.0` 태그 없음, `main` = `78517d5` (`release-check-14b34af.json`).
- `claude plugin validate --strict`: 소스·릴리스 모두 통과(README 마켓플레이스 설치 줄 권고만).

### 14.9 미검증·남은 위험
- **3회차 수정(`14b34af`)은 독립 재검토를 받지 않았다.** 정적 분석은 Python 근사라 의도적으로 꾸민 테스트(동적 setattr, exec 등)를 모두 잡지 못하고, 검토마다 새 형태가 나왔다.
- D43의 대가: 목만 쓴 경로 A 테스트는 그 IF의 provider가 실행 어딘가에서 돌면 경고와 함께 통과한다(목 판단은 G4 patch 경고와 G4 리뷰).
- 계측 한계(D43): forkserver(Python 3.14부터 Linux 기본)와 이전 테스트가 만든 fork 풀의 귀속, 세션·모듈 범위 서버의 경로 B BLOCKED, 데이터 전용 IF BLOCKED, 같은 프로세스 위조(F5), pytest가 아닌 러너(경로 B 증명 불가).
- 실제 Claude 세션에서의 G6(verifier의 `interfaces`·`runtime_paths`·`integration_applicability` 작성, 사용자 `configure-tests` 흐름)은 실행하지 않았다(D8 E2E 계획 WORKITEM §8, 승인 필요).
- Windows의 pty 경로, Python 3.11, macOS는 미검증. 업그레이드마다 G4 재리뷰 비용(D40)은 그대로(D4 결정).

## 15. v0.2.0 최종 독립 검증과 실제 E2E (2026-11-09~10, 브랜치 `g6-dev`)

사용자 지시("VModel DevKit v0.2.0 — 최종 독립 검증 및 E2E")에 따른 결과다. main 병합·`v0.2.0` 태그·원격 푸시는 하지 않았다. 결정은 D44, 처리표는 `docs/g6/WORKITEM.md` §7.4~7.11, 로그는 `test-results/v0.2.0/`. 하네스는 Claude 없이 사용자·verifier 역할을 대신한다(그 부분은 시뮬레이션). 실제 Claude 세션은 §15.5의 2회뿐이다.

### 15.1 출발 상태 확인
`g6-dev` = `c83df4b`, 마지막 코드 커밋 `14b34af`(그 뒤 플러그인 트리 변경 없음 확인), `main` = 태그 `v0.1.5` = `78517d5`, 릴리스 후보 core `f835ec91…`. HANDOFF·TEST_RESULTS §14의 보고와 같았다.

### 15.2 사용자 Case A~F (`tests/test_g6_evidence.py`, RED 대상 `14b34af`)
14b34af(D43 규칙)에서 재현된 것: **Case B**(IF-001 테스트 둘 다 목, parser는 TEST-012(IF-002)에서만 실행) → G6 PASSED(경고), **Case C**(TEST-010만 목) → `covered_by`에 목 테스트 TEST-010 포함, **Case D**(테스트가 provider를 직접 부르고 consumer 안의 호출은 목) → 경고도 없이 PASSED. 즉 Suite-level 증거가 Test-level 검증으로 표시됐다. RED 10/10(목표 assertion), 이후 계측기 단위 테스트 포함 21/21.
최종 빌드의 판정(모두 하네스에서 실제 실행):
| Case | 시나리오 | 결과 |
|---|---|---|
| A 정상 연결 | consumer가 실제 provider 호출 | PASSED, IF 2/2 Test-level Verified |
| B Mock만 | IF-001 테스트 전부 목 | BLOCKED `integration_evidence_insufficient`, 두 테스트 Suite-level Evidence Only, `covered_by` 비어 있음 |
| C 다른 테스트의 실행 | TEST-010 목, TEST-011 실제 | PASSED, `covered_by` = TEST-011만, TEST-010은 "Suite-level Evidence Only, not counted" |
| D 연결 근거 없음 | provider·consumer가 같은 테스트에서 따로 실행 | BLOCKED, "not called from the consumer"(Insufficient). provider만 부르는 테스트는 G4가 FAILED |
| E subprocess/API/풀 | 선언된 subprocess, 함수 fixture의 HTTP 서버 스레드, 공유 스레드 풀 consumer, 함수 fixture 서버 프로세스 | 모두 PASSED, Test-level |
| F 증거 불충분 | `-I` 자식(계측 불가), provider가 어디서도 안 돎, 계측 없음 | BLOCKED, IF별 Insufficient Evidence와 사유를 gate·status·trace·report에 표시 |
Suite-level 증거만 있는 IF는 PASS가 되지 않는다(D44). 판정 근거는 호출 스택의 consumer→provider 연결(진입 함수·앵커), 스레드·풀 작업의 시작·제출 관계, 자식 프로세스는 Validator 소유 pytest 플러그인이 기록한 그 테스트의 call 구간이다.

### 15.3 독립 검토 4~11회차 (별도 컨텍스트 검토자, 읽기 전용 worktree, 지적은 검토 빌드 대상 RED 후 수정)
| 회차 | 대상 | 지적(HIGH/MED/LOW) | 처리 |
|---|---|---|---|
| 4 | `c83df4b`(=`14b34af`) | 4/6/4 | H1~H4·M1~M6·L1·L2 수정, L3·L4 문서화 (`test_g6_review4`, RED 12/12) |
| 5 | `464d01b` | 3/4/0 | N1·N1b·N2·N3·N7·N8 수정, N4·N5 문서화 (`test_g6_review5`, RED 10/10) |
| 6 | `e8a5a7e` | 1/4/0 | M1·M2·M4·M5/6 수정, M7 보수 판단 (`test_g6_review6`, RED 5/5) |
| 7 | `ce59c33` | 0/3/2 | R1·R3·R4(판단)·R5 수정, R2 문서화 (`test_g6_review7`) |
| 8 | `953d502` | 0/1/1 | P1 수정, P2 문서화 (`test_g6_review8`) |
| 9 | `31ccb0d` | 0/1(거짓 PASS)/0 | Q1 수정 (`test_g6_review9`) |
| 10 | `3a08592` | 0/0/0 | 새 문제 없음 |
| 11 | `5275b5d`(E2E 결함 수정) | 0/0/0 | 새 문제 없음(두 파일 IF 판정 불변) |
내가 회귀 실행 중 발견해 고친 것: `prov_runs` KeyError 내부 오류(`e8a5a7e` 직전 작업 트리). E2E가 찾은 결함 2건은 §15.5.

### 15.4 전체 회귀 (깨끗한 detached worktree)
| 환경 | 커밋 | 결과 |
|---|---|---|
| WSL2 Ubuntu 24.04, Python 3.12.3, pytest 9.0.3 | `464d01b` | 394/394 |
| 같음 | `e8a5a7e` | 409/409 |
| 같음 | `ce59c33` | 414/414 |
| 같음 | `589c779`(E2E에 쓴 빌드) | 422 통과, skip 1(xdist 환경 변수 없을 때) |
| Windows 11, Python 3.13.14 venv, cp949, 한글·공백 경로 | `e8a5a7e` | 409 실행, 실패 0, skip 49 |
최종 커밋 결과는 §15.8.

### 15.5 실제 Claude Code E2E (승인: sonnet 최대 2회, 회당 $2, 합계 $4)
공통: `scripts/e2e/e2e_run.py`, `--model sonnet`(실제 `claude-sonnet-5-5`), `--max-budget-usd 2`, `--permission-mode auto --permission-prompts none`, `--setting-sources project,local`, `--no-session-persistence`, `--plugin-dir dist/vmodel-0.2.0`(빌드 `589c779`, core `2d3dd0ab…`), 임시 샌드박스(스크래치의 `e2e-a`·`e2e-b/한글 샘플 프로젝트`, 전용 `VMODEL_HOME`). `--dangerously-skip-permissions` 쓰지 않음. 실제 업무 프로젝트·기존 릴리스·서명 원장은 건드리지 않았다. 세션 뒤 판정은 모델 호출 없이 `scripts/e2e/e2e_verify.py`(릴리스 Validator의 status·audit·verify-evidence·trace·report). 산출물 `test-results/v0.2.0/e2e/`.
**실행 횟수 2회, 비용 합계 약 $2.08**(A $1.48, B $0.60; CLI `total_cost_usd`, 추정치). 두 세션 모두 끝에 release core `2d3dd0aba096` 무결성 OK.

E2E-A (`samples/scorepipe`, 기존 provider `parser.py` 수정 금지, 소비 측 요약 보고·CLI 추가, 72턴, 8.3분)
- 합성 시딩: provider가 문서대로 점수를 문자열로 반환하고, 요청은 정수 계산·가짜 파서 주입 단위 테스트를 요구(`SEEDING.md`). **에이전트는 함정에 걸리지 않았다**(provider 문서를 읽고 `int()` 변환). 그래서 시딩한 결함으로 G6 FAILED가 나는 단계는 **관찰되지 않았다.**
- 실제 흐름: 요구사항(REQ 6) → 아키텍처(ARCH-001 summary, ARCH-002 CLI, IF-001 summarize) → 설계·테스트 명세(unit 15, integration 2, system 4) → 구현 → G1~G5 PASSED → **G6 BLOCKED `integration_evidence_insufficient`**(R00011) → 에이전트가 원인을 P2(두 컴포넌트가 한 모듈 `report.py`)로 보고 `summarize`를 `summary.py`로 옮김(아키텍처 변경) → G2~G5 재평가 → **G6 PASSED**(R00019, IF-001 Test-level Verified, TEST-016·017) → audit OK(원장 19건, 증거 6건 모두 OK) → WI PARTIALLY_VERIFIED.
- 그 BLOCKED는 **DevKit 결함**이었다(나중에 직접 재현): 6회차 M1 수정(진입 함수 기록)이 같은 파일 안 `main → summarize`를 `main`으로 기록해 "summarize never ran"으로 잘못 판단했다(`e8a5a7e`는 통과). `test_g6_e2e_findings`로 고정(RED 대상 `589c779`) 후 수정(§15.8). 에이전트의 모듈 분리는 그 자체로 합리적이었지만 계기는 Validator 오판이었다.
- BLOCKED는 중립 판정이라 결함 기록 대상이 아니다: 에이전트가 BLOCKED 기록을 인용한 DEFECT를 쓰려다 Validator가 인용 오류로 거부했고, `defects.json`은 비어 있다. 따라서 **G6 FAILED → DEFECT → 수정 → CLOSED 경로는 실제 세션에서 검증되지 않았다**(하네스 F1·T12와 §14.6 시연으로만 확인).
- guard 거부 1건: 셸 heredoc으로 `.vmodel/work-items/.../architecture.json`을 고쳐 쓰려던 명령. 올바른 차단(우회 없음, 에이전트는 Edit/Write로 진행).
- 관찰: 에이전트는 기존 파서를 컴포넌트·IF로 모델링하지 않았다. 그래서 G6이 판정한 IF는 summary↔CLI 하나이고, summary↔기존 파서 연결은 통합 테스트가 실제로 실행하지만 IF로 판정되지는 않았다(verifier가 G2에서 승인). DevKit이 기존 코드 의존을 IF로 강제하지 않는 한계다.

E2E-B (`samples/textstats`, 단일 함수 기능, 37턴, 3.4분)
- REQ 3 → ARCH-001 하나, IF 0 → 설계·unit 7·system 2, integration 0 → G1~G5 PASSED → G6 PASSED + `applicability: not_applicable`(R00011), 실행 체크 전부 skip, 증거 없음 → WI PARTIALLY_VERIFIED, `gate_summary`의 `na: [G6]`.
- verifier가 G2·G3(그리고 G4) 리뷰에 `integration_applicability`(not_required, 사유, endpoints_reviewed)를 기록했다. G6 N/A 근거는 G2(R00005)·G3(R00007) 리뷰.
- 세션 최종 보고: "G6 통합 검증 N/A … 통합 테스트는 실행하지 않았으므로 '통합 테스트 통과'가 아닙니다." 보고서 파일에도 "통합 테스트 통과" 없음. audit OK(원장 11건, 증거 2건 OK), guard 거부 0.
- 발견한 표시 결함(LOW): 보고서 Gate별 체크 절 제목이 `### G6 — PASSED (R00011)`(REQ-G6-17 위반). 고정·수정(§15.8).

### 15.6 G1~G6과 원장·증거
- G1~G5 판정·manifest 불변: `test_g6_compat`(C1/C2), 0.1.5 서명 원장·증거의 새 코어 검증(T17), 0.1.5 → 0.2.0 재고정(T20) 모두 최종 회귀에 포함되어 통과.
- G6 증거: 서명된 record.json에 `runtime_trace`(프로세스 수, spawned 프로세스, 테스트 경계 수, 비교 시계 `perf_counter_ns`, 연결 수, 오류), 실행 직후 스냅샷한 `trace/*.jsonl` 해시. 남은 자식 프로세스가 서명 뒤 증거를 바꾸지 못함(4회차 M5).
- E2E 두 샌드박스: audit OK, 모든 증거 verify-evidence OK, trace 끊어진 링크 없음.

### 15.7 미검증·남은 위험
- 실제 세션에서 G6 FAILED → DEFECT → 수정 → CLOSED 경로(시딩 함정이 발동하지 않음). 추가 실행은 승인 범위 밖이라 하지 않았다.
- E2E 이후 수정(같은 모듈 provider/consumer, 보고서 제목)은 하네스로만 확인했다(E2E는 `589c779`에서 실행).
- 문서화한 보수적 BLOCKED(정상 코드가 막힐 수 있음): 데이터 전달형 테스트, `asyncio.gather` 작업·provider 제너레이터 전달(N4/N5), setup에서 한 번 실행한 함수를 call에서 다시 쓰는 자식 서버(R2), provider 모듈의 호출 가능한 클래스 데코레이터(P2), 세션·모듈 범위 서버, pytest가 아닌 러너, provider 모듈에 정의된 시계·설정 도우미를 patch한 테스트(Q1 판단의 대가).
- (D45로 확정됨) 사용자 확인이 필요했던 보수 판단 2가지: (1) 테스트 함수가 provider(인터페이스 심볼 또는 provider 모듈에 정의된 함수)를 patch하면 그 테스트는 Test-level로 세지 않는다(6회차 M7, 7회차 R4, 9회차 Q1). (2) autouse·요청하지 않은 fixture가 만든 연결은 세지 않고, 요청한 fixture의 연결은 센다.
- 같은 프로세스 신뢰 경계(SPEC §5.7): 계측 줄·경계·시각은 테스트 코드가 의도적으로 위조할 수 있다.
- Windows Python 3.12 이하의 거친 벽시계는 `perf_counter_ns` 비교로 대응했고 시뮬레이션만 했다(실제 3.12 Windows는 미검증). macOS 미검증. 4회차 L3(setprofile 경로의 기록 유실)·L4(손자 프로세스가 파이프를 잡을 때 시간 초과 보고)는 고치지 않았다.
- 검토는 8회 반복했고 회차마다 새 형태가 나왔다(7회차부터 HIGH 0, 9회차 Q1이 마지막 거짓 PASS). 정적 분석·계측 기반 판정의 본질적 한계로, 앞으로도 새 우회·오판이 나올 수 있다.

### 15.8 최종 후보 회귀와 릴리스 점검 (코드 `5275b5d`, 릴리스 기록 `83b3b9a`)
| 항목 | 결과 |
|---|---|
| WSL 전체 하네스(깨끗한 worktree `83b3b9a`) | **424 통과**, skip 1(xdist 시험: `VMODEL_R7_XDIST_PYTHON` 없을 때), 1258초 (`wsl-harness-83b3b9a.log`) |
| Windows 11, Python 3.13.14, cp949, 한글·공백 경로(`83b3b9a`) | **424 실행, 실패 0**, skip 50(pty 필요한 사용자 전용 경로 45, 심볼릭 링크 권한 2, ruff 없음 1, xdist 1, 기타 pty 1) (`windows-harness-83b3b9a.log`) |
| Windows cp949 전체(`589c779`, E2E 빌드) | 422 실행, 실패 0, skip 50 (`windows-harness-589c779.log`) |
| 릴리스 재빌드 | `release.py --force` → `dist/vmodel-0.2.0` 46개 파일, core `sha256:9cc0997a886cd36b5f116a9f0889017a347c5accf234488db6e391a0d1927b9d` |
| 릴리스 점검(`release_check.py`, Validator 코드 없이 해시 재계산) | OK: 소스 = 0.2.0 기록, 0.1.0~0.1.5 사본·기록 일치·불변, 태그 `v0.1.2`~`v0.1.5` 불변, `v0.2.0` 태그 없음, `main` = `78517d5` (`release-check-83b3b9a.json`) |
| `claude plugin validate --strict` | 소스·릴리스 모두 통과(README 마켓플레이스 설치 줄 권고만) |
| 0.1.5 서명 원장·증거 호환, G1~G5 판정·manifest 불변, 0.1.5 → 0.2.0 재고정 | 하네스 T17·C1·C2·T20(pty)·D4 포함, 위 회귀에서 통과 |
| 새 시험 모듈 | `test_g6_evidence`(23), `test_g6_review4`(15), `test_g6_review5`(12), `test_g6_review6`(5), `test_g6_review7`(5), `test_g6_review8`(2), `test_g6_review9`(1), `test_g6_e2e_findings`(2) |
| RED 로그 | `red-evidence-on-14b34af.log`, `red-evidence2-on-14b34af.log`, `red-review4-on-14b34af.log`, `red-review5-on-464d01b.log`, `red-review6-on-e8a5a7e.log`, `red-review7-on-ce59c33.log`, `red-review8-on-953d502.log`, `red-review9-on-31ccb0d.log`, `red-e2e-findings-on-589c779.log` (모두 위반 0) |

### 15.9 판정: RELEASE CONDITIONAL
근거(통과한 것): CRITICAL·HIGH 미해결 0(7~11회차 HIGH 0, 마지막 거짓 PASS인 9회차 Q1은 10회차에서 닫힘), 사용자 Case A~F가 하네스에서 기대대로 판정, Suite-level 증거만으로는 PASS가 나지 않음, 최종 후보 WSL 424 통과·Windows 424 실행 실패 0(skip 50), 릴리스 해시·태그·0.1.x 기록 불변, 실제 E2E-B(N/A)는 기대 전부 충족, 실제 E2E-A는 Provider/Consumer 개발 → G6 BLOCKED → 수정 → G6 Test-level PASS·audit OK까지 진행.
조건(확정 전에 사용자 판단이 필요한 것):
1. 실제 세션에서 G6 FAILED → DEFECT → 수정 → CLOSED 경로는 관찰되지 않았다(시딩 함정 미발동). 하네스와 §14.6 시연으로만 확인됐다. 그대로 받아들일지, 하네스 개입(봉인된 결함 주입, D26/D27 방식)을 쓰는 2세션 드릴을 추가 승인할지.
2. E2E 이후의 수정 2건(같은 모듈 provider/consumer, 보고서 제목)은 하네스·11회차 검토로만 확인했다(실제 세션은 `589c779`).
3. 보수 판단 2가지의 확인: 테스트 함수가 provider(인터페이스 심볼 또는 provider 모듈에 정의된 함수)를 patch하면 Test-level로 세지 않음, autouse·요청하지 않은 fixture의 연결은 세지 않음.
4. 문서화한 거짓 BLOCKED 한계(§15.7)를 받아들일지.

## 16. 보수 정책 A·B 확정과 G6 FAILED 실전 드릴 (2026-11-10, 브랜치 `g6-dev`)

사용자 지시("VModel DevKit v0.2.0 — G6 최종 실패·재작업 실전 드릴")에 따른 결과다. main 병합·`v0.2.0` 태그·원격 푸시·G7 개발은 하지 않았다. 결정은 D45, 처리표는 `docs/g6/WORKITEM.md` §7.13, 로그는 `test-results/v0.2.0/`.

### 16.1 출발 상태 확인
`g6-dev` = `d9cae51`(문서), 마지막 코드 `5275b5d`, `main` = 태그 `v0.1.5` = `78517d5`, `v0.2.0` 태그 없음, 릴리스 후보 core `9cc0997a…`가 소스와 일치(`release_check` OK). HANDOFF·§15의 보고와 같았다. 작업 트리의 `.claude/`(예약 기능 잠금 파일)는 커밋하지 않았다.

### 16.2 정책 A·B 확정과 코드 점검
사용자가 승인한 정책 A(provider patch)·B(autouse fixture)를 D45로 기록하고 D44의 옛 문장(autouse fixture 연결을 셈)을 정정했다. "현재 구현이 이미 충족하면 코드 변경 없음"을 확인하려고 재현해 보니 **충족하지 않았다**: D44는 두 규칙을 정적 경로(경로 A)에만 적용했고, G4에서 선언한 런타임 경로(경로 B)는 call 구간의 provider 실행만 봤다. `5275b5d`에서 provider를 patch한 api·subprocess 테스트, autouse fixture의 스레드·자식 프로세스가 혼자 provider를 돌린 테스트가 Test-level Verified로 PASSED였다(`tests/test_g6_policy.py`, RED 5/5).

### 16.3 수정과 독립 검토 12~15회차 (같은 검토자, 별도 컨텍스트, 읽기 전용 detached worktree, 지적은 검토 빌드 대상 RED 후 수정)
| 회차 | 대상 | 결과 | 처리 |
|---|---|---|---|
| (내 재현) | `5275b5d` | 경로 B 거짓 PASS 5 | `test_g6_policy` RED 5/5·대조군 3/3 → `092a0fe`(경로 B patch 규칙, 스레드·`Popen` 자식 출처 앵커) |
| 12 | `092a0fe` | 거짓 PASS 4(H1~H4, 기존 공백), 내 수정이 만든 거짓 BLOCKED 5모양(M1~M3), LOW 4 | `test_g6_review12` RED 9/9·대조군 3/3 → `c451a13`(autouse·usefixtures patch 탐지, consumer 실행 앵커, multiprocessing·os.system·posix_spawn·fork 출처). H3·H4 문서화 |
| 13 | `c451a13` | 12회차 수정이 만든 회귀 3(SF1 같은 모듈, C5 스캔 상한, `os.system` 교착), 정적 탐지가 닿지 않는 fixture 경로 A1~A5, 보수 판단 A6 | `test_g6_review13` RED 4/4 → `9497d14`. A1~A6 사용자 판단 대상(D45 8항) |
| 14 | `9497d14` | 13회차 수정이 만든 거짓 PASS 1(SF2), C5 미완 2, LOW 1 | `test_g6_review14` RED 4/4 → `fa815b3` |
| 15 | `fa815b3` | 14회차 지적 해결 확인, 새 거짓 PASS·회귀·충돌 없음. 공유 스레드 풀 작업자의 예산 소진(거짓 BLOCKED, "확실하지 않음" 표시) 1 | 문서화(D45), 검토 종료 |
회차마다 이전 수정이 만든 반대쪽 오판이 나왔다(D43·D44와 같은 양상). 그래서 15회차 뒤에는 보수 방향의 남은 1건을 고치지 않고 범위를 묶었다. RED 로그: `red-policy-on-5275b5d.log`, `red-review12-on-092a0fe.log`, `red-review13-on-c451a13.log`, `red-review14-on-9497d14.log`(모두 위반 0).

### 16.4 회귀와 릴리스 (최종 후보 코드 `fa815b3`)
| 항목 | 결과 |
|---|---|
| WSL 전체 하네스(깨끗한 worktree) | `7c7b446` 432 통과, `c451a13` 444 통과, **`fa815b3` 453 통과**(각 skip 1: xdist 시험 환경 변수 없음) (`wsl-harness-*.log`) |
| Windows 11, Python 3.13.14 venv, cp949, 한글·공백 경로(`fa815b3`) | **453 실행, 실패 0**, skip 55 = §15.8의 50(pty 필요한 사용자 전용 경로 등) + 이번 POSIX 전용 새 시험 5(fork 2, fifo·fork 2, forkserver 1). multiprocessing spawn 풀·`os.system`·usefixtures 서버·patch·autouse 시험은 Windows에서 실행·통과 (`windows-harness-fa815b3.log`) |
| 릴리스 재빌드 | `release.py --force` → `dist/vmodel-0.2.0` 46개 파일, core `sha256:ce81befa63914478d8e54252d3cf05ad9104ced40c4e4eab398be7295e80a134` (`0664a39`) |
| 릴리스 점검(`release_check.py`) | OK: 소스 = 0.2.0 기록, 0.1.0~0.1.5 사본·기록 불변, 태그 `v0.1.2`~`v0.1.5` 불변, `v0.2.0` 태그 없음, `main` = `78517d5` (`release-check-fa815b3.json`) |
| `claude plugin validate --strict` | 소스·릴리스 모두 통과 |

### 16.5 드릴 S1 1차 시도: guard 거짓 거부 발견 (유료 세션 1/3)
- 실행: `scripts/e2e/g6_drill.py run --phase s1`(sonnet, `--max-budget-usd 2`, `--permission-mode auto`, `--setting-sources project,local`, `--no-session-persistence`, 릴리스 core `ce81befa`, 임시 샌드박스·전용 `VMODEL_HOME`). `--dangerously-skip-permissions` 쓰지 않음. **비용 $0.107, 5턴, 18.5초.**
- 결과: 에이전트가 요청문을 그대로 넣은 `vmodel new-wi --request "… 'ORDER <order_id>' …"`를 guard가 "Validator Core 수정"으로 거부했고, 에이전트는 규칙대로 우회하지 않고 멈췄다(작업 항목 0, Gate 0, 원장 1건, audit OK, 릴리스 트리 불변). 산출물 `test-results/v0.2.0/drill/*-attempt1*`.
- 원인(직접 재현): 0.1.3·0.1.5·0.2.0 공통의 guard 결함. 따옴표 안 `<`·`>`를 리다이렉션으로 읽어 Validator 호출로 인정하지 않았다(D46). 하네스는 늘 단순 문자열로 호출해 놓쳤다.
- 사용자 결정: 세션 1회 추가 승인(총 3회, 회당 $2). guard 결함은 드릴과 별개로 고쳤다(§16.6).

### 16.6 guard 수정과 독립 검토 16~21회차 (D46)
| 회차 | 대상 | 결과 | 처리 |
|---|---|---|---|
| (S1 재현) | `fa815b3` | 따옴표 안 `<`·`>` 거짓 거부 | `test_guard_quoted` RED 1/1 → `11bb551`(따옴표 안 가리기) |
| 16 | `11bb551` | 새 우회 2(`$'…'`, PowerShell 큰따옴표), 기존 우회 2(줄바꿈, 백슬래시-줄바꿈 `$(`) | `test_guard_quoted2` RED 3/3 → `7526ce3` |
| 17 | `7526ce3` | 기존 우회 2(꼬리 뒤 줄바꿈, PowerShell `(…)`), 거짓 거부 2 | `test_guard_quoted3` RED 2/2 → `88971ac` |
| 18 | `88971ac` | 주석 안 `'`로 줄 숨김(11bb551부터), PowerShell 거짓 거부 | `test_guard_quoted4` RED 2/2 → `690e757` |
| 19 | `690e757` | PowerShell 타이포그래피 따옴표, `.cmd` 재해석(bash·PowerShell) | `test_guard_quoted5` RED 1/1 → **방식 변경** `6f332f1`(허용 목록 문법) + ReDoS 수정(내가 발견) |
| 20 | `6f332f1` | 문법 경로는 단일 호출로만 실행됨 확인, PowerShell의 PATHEXT `vmodel.cmd` 선택 1 | `test_guard_quoted6` RED 1/1 → `18bbcb8` |
| 21 | `18bbcb8` | 해결 확인, fa815b3 대비 회귀·충돌 없음 | 검토 종료. 기존 공백(PowerShell `del,`)은 문서화 |
`test_upgrade_settings`의 guard 불변 Invariant는 D46 블록과 `_is_validator_call`·호출부만 되돌려 나머지를 0.1.4와 바이트 비교하도록 갱신했다(다른 규칙 변이를 잡는지 확인). 남은 제약: PowerShell 도구에서는 따옴표 안 `& | < > ^ %`가 있는 Validator 호출이 여전히 거부될 수 있다(bash에서는 허용).

### 16.7 드릴 S1(유료 2/3)·시딩·S2(유료 3/3): G4에서 정당하게 검출 → G6 FAILED 경로는 미관찰
공통: `scripts/e2e/g6_drill.py`, sonnet(`claude-sonnet-5-5`), 회당 `--max-budget-usd 2`, `--permission-mode auto --permission-prompts none`, `--setting-sources project,local`, `--no-session-persistence`, `--plugin-dir dist/vmodel-0.2.0`(코드 `20d2139`, core `88edfac2…`), 임시 샌드박스 `g6drill3/work/한글 드릴 프로젝트`·전용 `VMODEL_HOME`. 봉인 계획·시드·프롬프트·트랜스크립트는 작업 폴더 밖 `work-sealed/`. `--dangerously-skip-permissions` 쓰지 않음. 실제 업무 프로젝트·기존 서명 원장·릴리스 불변(세션 전후 릴리스 트리 해시 같음). 산출물 `test-results/v0.2.0/drill/`.
- **S1**($0.640, 35턴, 3.4분): 요청(가격 계산 provider `pricing.price_order` + 영수증 consumer `receipt.render_receipt`, consumer 단위 테스트는 가짜 pricer 주입)대로 P1~P4. G1 R00003·G2 R00005·G3 R00007 PASSED(실제 `vmodel:verifier` 리뷰 R00002/4/6 approve, `vmodel:test-designer`가 TEST-001~014 작성), 코드·단위 13·통합 2 작성 후 지시대로 G4 전에 멈춤. guard 거부 0(1차 시도의 `<order_id>` 요청문이 통과), 작업 폴더 밖 접근 0, 원장 7건 audit OK.
- **시딩**(봉인 `seed.json` sha256 `a9215206…`, 확인 기록 `seed-check.json` sha256 `9bad3873…`): S1의 소비 측 단위 테스트가 provider 호출 인자를 확인(`calls == [raw]`)해 인자 모양 불일치는 단위에서 잡히므로, 필드 의미 불일치를 골랐다. `receipt.py` 한 글자: `DISCOUNT {result['discount']}` → `DISCOUNT {-result['discount']}`(consumer가 IF-001의 `discount`를 부호 있는 조정값으로 오해; provider 계약은 양수 할인액, `total == subtotal - discount`). 사본에서 확인: 시딩 전 단위·통합 모두 통과, 시딩 후 단위 13 통과(가짜 pricer는 모두 할인 0, `-0`은 `0`), 통합 TEST-013 실패(`DISCOUNT -5001` ≠ `5001`, 실제 연결), TEST-014 통과. 명세·테스트·리뷰는 건드리지 않았고 주석·위장 없음. S1이 커밋하지 않아 시드는 S1 구현과 구분되지 않는다.
- **S2**($0.401, 21턴, 1.9분, 에이전트·서브에이전트 pytest 차단, 프롬프트는 "WI-001을 이어서 끝까지"뿐): G4 verifier가 **코드와 REQ-004를 읽고 시드를 찾았다**(R00008 reject, F-1 major "`render_receipt`가 할인을 음수로 출력, REQ-004 AC-004-2·DESIGN-002와 다름, TEST-013이 실제 `price_order`로 실패할 것", 테스트는 실행하지 않음) → G4 FAILED R00009(`G4.REVIEW`) → 에이전트가 스스로 DEFECT-001(gate G4, `found_in_records` R00009, root_cause_phase P4, fix_scope `receipt.py`, related REQ-004·DESIGN-002·TEST-013, `status: fixed`를 수정과 같은 단계에) → `-` 한 글자 제거(테스트·명세 변경 없음) → G4 재리뷰 R00010 approve → G4 PASSED R00011 → G5 PASSED R00012(단위 13) → **G6 PASSED R00013**(통합 TEST-013·014 실행·통과, IF-001 Test-level Verified, 실행 계측 연결 4·경계 12·오류 0) → DEFECT-001 **CLOSED**(verified by R00011) → WI PARTIALLY_VERIFIED, audit OK(원장 13건, 증거 4건 verify OK), defect trace 오류·경고 0, guard 거부 0, 작업 폴더 밖·봉인 폴더·저장소 접근 0.
- **판정**: 사용자 지시("G4에서 정당하게 결함을 발견하면 숨기지 말고 기록, 이 경우 G6 FAILED 전체 경로를 확인하지 못한 것으로 보고")에 따라 **G6 FAILED → DEFECT → CLOSED 경로는 실제 세션에서 관찰되지 않았다.** 실제로 확인된 것은 G1~G3 PASSED → G4 FAILED(리뷰) → DEFECT → 근본 원인 → 최소 수정 → G4·G5 재검증 → G6 실제 통합 실행 PASSED(Test-level) → DEFECT CLOSED → audit OK다. BLOCKED·FAILED를 바꾸거나 서명 증거·테스트 기대값을 고친 일은 없다.
- **실제 실행 비용**: 1차 S1 $0.107 + S1 $0.640 + S2 $0.401 = **$1.148**(CLI `total_cost_usd`, 추정치). 승인: 2회 + 추가 1회(사용자), 회당 상한 $2.

### 16.8 최종 품질 점검 (최종 후보 코드 `20d2139`, 릴리스 기록 `8874005`)
| 항목 | 결과 |
|---|---|
| 기존 G6 거짓 PASS 방지 테스트 | `test_g6_evidence`·`test_g6_review4~9`·`test_g6_e2e_findings` 등 기존 모듈 모두 최종 회귀에서 통과 |
| Mock·Fixture 보수 정책(D45) | `test_g6_policy`(8)·`test_g6_review12`(12)·`test_g6_review13`(4)·`test_g6_review14`(4) 통과, 대조군(요청한 fixture 서버·자식, fork·spawn 풀, asyncio 자식, 손자 프로세스, 무관한 autouse fixture) Test-level 유지 |
| guard(D46) | `test_guard_quoted`~`quoted7`, `test_guard_redirects`, `test_hooks` 통과(WSL·Windows), 0.1.4 이후 guard 불변 Invariant는 D46 블록만 되돌려 비교 |
| 기존 Gate 판정 호환 | `test_g6_compat`(C1/C2: G1~G5 판정·manifest 불변), T17(0.1.5 원장·증거의 새 코어 검증), T20(0.1.5 → 0.2.0 재고정) 통과 |
| Ledger·Evidence 무결성 | 드릴 샌드박스 audit OK(원장 13건), verify-evidence 4/4 OK(릴리스 Validator), 하네스 무결성 시험 통과 |
| 전체 회귀 WSL2 Ubuntu 24.04, Python 3.12.3(깨끗한 worktree `20d2139`) | **474 통과**, skip 1(xdist 시험 환경 변수 없음), 1415초 (`wsl-harness-20d2139.log`) |
| 전체 회귀 Windows 11, Python 3.13.14 venv, cp949, 한글·공백 경로(`20d2139`) | **474 실행, 실패 0**, skip 55(pty 필요한 사용자 전용 경로 45, 심볼릭 링크 권한 2, ruff 없음 1, xdist 1, POSIX 전용 fork·fifo·forkserver 5, 기타 1) (`windows-harness-20d2139.log`). 직전 `18bbcb8`에서는 guard 허용 시험 8개 실패(Windows 경로) → D46 수정 |
| 릴리스 사본과 소스 | `release_check.py` OK: 소스 = 0.2.0 기록 = dist 재계산 core `sha256:88edfac2dd33982db9a14a9e6ff854f16e678055ebefb4ce868c0c40ea134932`, 0.1.0~0.1.5 사본·기록 불변, 태그 `v0.1.2`~`v0.1.5` 불변, `v0.2.0` 태그 없음, `main` = `78517d5` (`release-check-final-20d2139.json`). `claude plugin validate --strict` 소스·릴리스 통과. **드릴 S1·S2가 쓴 릴리스 core와 최종 후보가 같다**(봉인 계획의 `release_core`) |

### 16.9 판정: RELEASE CONDITIONAL (유지)
지시 §5 기준("실제 G6 FAILED → DEFECT → 수정 → CLOSED 경로가 성공하고 모든 필수 검증이 통과하면 READY, 실패하거나 일부만 확인하면 CONDITIONAL")에 따라 **CONDITIONAL**이다. 필수 검증(§16.8)은 모두 통과했지만, 실제 세션의 G6 FAILED 경로는 G4가 시드를 정당하게 검출해 관찰되지 않았다(D47).
조건(사용자 판단):
1. 실제 G6 FAILED → DEFECT → CLOSED 경로: D47의 선택지(G4가 읽어서는 못 보는 유형으로 재드릴 / 명시 표시한 G4 승인 주입 / 하네스 검증으로 수용). 추가 유료 세션 승인 필요.
2. 보수 정책의 남은 공백(D45 8항): 정적 patch 탐지가 닿지 않는 fixture 경로 A1~A5(거짓 PASS 가능), 조건부 autouse patch의 보수적 BLOCKED(A6), 요청 주체(H3)·자식 명령 문자열 patch(H4), 공유 스레드 풀 작업자의 예산 소진(거짓 BLOCKED, "확실하지 않음" 표시).
3. guard의 남은 제약·공백(D46): PowerShell 도구에서 따옴표 안 `& | < > ^ %`가 있는 Validator 호출은 거부될 수 있음, PowerShell `del,` 형태 쓰기 미탐지(0.1.x부터).
4. §15.7의 이전 항목(데이터 전달형 테스트 등 문서화한 보수적 BLOCKED, 같은 프로세스 신뢰 경계, macOS 미검증).

## 17. 최종 위험 판단과 릴리스 확정 (2026-11-11, 사용자 지시 "최종 위험 판단 및 릴리스 확정")

추가 유료 세션 없이 알려진 위험을 분류하고 릴리스 여부를 정했다. 결정은 D48, 로그는 `test-results/v0.2.0/`.

### 17.1 출발 상태 확인
`g6-dev` = `e4aaaf5`, 마지막 제품 코드 `20d2139`(이후 플러그인 트리 변경 없음), 릴리스 core `88edfac2…` = 소스 = 기록(`release_check` OK), `main` = 태그 `v0.1.5` = `78517d5`, `v0.2.0` 태그 없음, WSL 474 통과(skip 1), Windows 474 실행 실패 0(skip 55). §16과 같았다.

### 17.2 G6 FAILED 실전 경로 (기록만, 추가 드릴 없음)
실제 세션(§16.7)에서 G4가 코드 결함을 찾았고, 에이전트가 DEFECT-001을 만들고 고쳤으며, G4 재검증과 G5·G6 실행이 통과했고, DEFECT-001은 CLOSED였다. **G6 FAILED → DEFECT → CLOSED 경로는 실제 세션에서 관찰되지 않았다.** 이 경로는 독립 하네스(F1·T12, §14.6 시연, `test_g6_*`의 FAILED 판정 시험)에서만 검증됐다. G4의 조기 검출은 검증 실패로 취급하지 않는다.

### 17.3 D45 위험 분류와 최소 보호 (D48)
| 분류 | 경로 | 처리 |
|---|---|---|
| B 거짓 PASS(재현됨, 현재 후보 `20d2139`) | A1 import한 autouse patch fixture, A2 기반 클래스 autouse patch, A3 `pytest_plugins`, A4 루트 conftest autouse patch, A5 `MonkeyPatch.context()`, H4 자식 명령 문자열 patch, H3 autouse 스레드가 요청한 서버로 요청(스레드·프로세스) | `tests/test_g6_residual.py` RED 8/8 → D48 R1(실행 시점 patch 관찰)·R2(출처 불확실하면 메인 스레드 증거만) → 모두 BLOCKED |
| B 거짓 PASS(분류 중 내가 재현, `86dbf98`) | provider 모듈 수준 인스턴스(provider 정의 클래스)의 메서드를 인스턴스에서 바꾼 patch(autouse fixture·시험 함수 모두) | `tests/test_g6_residual3.py` RED 2/2 → R1 확장(`c399b1a`) → BLOCKED |
| B 거짓 PASS(검토 26회차 재현, `291d18b`) | provider 모듈 객체를 테스트 정의 가짜나 `MagicMock`으로 통째로 바꾼 autouse patch | `tests/test_g6_residual5.py` RED 2/2 → R1을 provider 모듈 전역 전체로 확장(`8849672`; 설정 상수는 경고 유지), 가져온 이름은 같은 컴포넌트(상대·절대 import)만(`f3c1cbb`·`f49bc5c`) → BLOCKED |
| A 증거 부족 BLOCKED(수용) | 조건부 autouse patch(A6), 공유 스레드 풀 예산 소진, autouse fixture가 스레드·프로세스를 띄운 테스트의 스레드·프로세스 경유 연결(R2, 검토 23 R2b·c·d·f), provider 이름을 provider 밖 함수로 정상 재대입(strict 이름), asyncio 작업·제너레이터 전달(N4/N5), 데이터 전달형 테스트, 세션·모듈 범위 서버, pytest가 아닌 러너, 출처 토큰이 닿지 않는 프로세스(Windows `os.spawn*` 등) | 알려진 기능 제약. 사유 메시지에 원인 표시 |
| 결정에 따른 경고(정책상 G4 리뷰 몫) | provider 모듈의 설정 상수 patch와, provider 컴포넌트 밖(다른 컴포넌트·외부 라이브러리)에서 가져온 이름을 스텁·가짜로 바꾼 patch(D44 2항, 8회차 P1, Case F: 의존 대상 스텁), 장식·재대입된(weak) 이름을 라이브러리 함수로 바꾼 patch(R1이 보지 않음; 테스트 트리 밖 지원 코드는 G4가 막음), 모듈 수준이 아닌 객체(컨테이너 안·지역 객체)의 인스턴스 patch | G4 patch 경고 + 리뷰. 재현된 거짓 PASS 아님 |
| 신뢰 경계(주장하지 않음) | 테스트 코드가 계측 줄·토큰을 의도적으로 위조, 의도적 구성(테스트가 시작한 스레드를 autouse 코드가 재사용, signal 처리기) | SPEC §5.7·D25 |
최소 보호의 회귀 확인: 독립 검토 23회차(`733d708`)가 R1 거짓 BLOCKED 2, guard 읽기 명령 거짓 거부, tracer 속도 저하를 찾음 → `tests/test_g6_residual2.py` RED 3/3 → `86dbf98` 수정(스레드 100개×호출 1000회 19.1초 → 1.1초, D48 이전 0.9초). 24회차(`86dbf98`) 확인: 해결, 완화가 A1~A5·H3·H4·`del,`을 다시 열지 않음, 충돌 없음.

### 17.4 guard(D46) 위험 분류
| 분류 | 경로 | 처리 |
|---|---|---|
| 보호 대상 실제 쓰기 허용(릴리스 차단) | PowerShell `vmodel status 'x|del,.vmodel/state/ledger.jsonl'`(vmodel.cmd → cmd.exe가 `del,`를 `del`로 실행), Git Bash의 `vmodel.cmd` 호출도 같음(0.1.x부터, 검토 21회차가 Windows에서 실제 삭제 확인) | `tests/test_guard_cmd_builtin.py` RED 1/1 → 수정(cmd 내장 쓰기 명령 뒤 `, ; = /`도 쓰기). **해결** |
| 정상 명령 차단(알려진 제약) | PowerShell 도구의 따옴표 안 `& | < > ^ %` Validator 호출, 허용 목록 문법 밖 Validator 호출(따옴표 밖 줄바꿈·주석·`$'`), 쓰기 동사 단어가 따옴표 없이 들어간 `.vmodel` 대상 명령 | 기록 |
| 주장하지 않음 | 모든 셸 문법·임의 코드 실행(프로젝트에 쓴 스크립트 실행 등)의 통제, 이미 있는 변수를 쓰는 `${x@P}`·산술 간접 참조 | 서명 원장·외부 앵커·Core 해시가 audit에서 변조를 드러냄(D24·D25) |

### 17.5 최소 보호의 검토 (같은 검토자, 별도 컨텍스트, 읽기 전용 worktree, 지적은 검토 빌드 대상 RED 후 수정)
| 회차 | 대상 | 결과 | 처리 |
|---|---|---|---|
| 23 | `733d708`(D48) | 새 거짓 PASS 없음. 회귀: R1 거짓 BLOCKED 2, guard 읽기 명령 거짓 거부, 스레드 많은 테스트 20배 느려짐, R2 거짓 BLOCKED | `test_g6_residual2` RED 3/3 → `86dbf98`. R2는 분류 A |
| 24 | `86dbf98` | 해결, 다시 열린 것 없음 | — |
| (분류 중 내가 재현) | `86dbf98` | provider 인스턴스 메서드 patch 거짓 PASS | `test_g6_residual3` RED 2/2 → `c399b1a` |
| 25 | `c399b1a` | 인스턴스 확인의 거짓 BLOCKED 2, 예외로 추적이 꺼짐, 약간 느려짐 | `test_g6_residual4` RED 2/2 → `291d18b` |
| 26 | `291d18b` | 해결. 이전부터 있던 통째 교체 거짓 PASS 재현 | `test_g6_residual5` RED 2/2 → `8849672` |
| 27 | `8849672` | 해결, 정상 provider 오판 없음, 충돌·속도 저하 없음. 분류 A 2(테스트 경로 모듈을 import하는 provider, 200회 뒤의 patch) | 새 형태 탐색 종료 |
| (Windows 회귀) | `8849672` | 기존 Case F 시험 실패: 다른 컴포넌트에서 가져온 `report.parse` 스텁을 patch로 봄(D44 2항·P1과 충돌) | `f3c1cbb`: 컴포넌트 밖에서 가져온 이름 제외 |
| 28 | `f3c1cbb`(이 변경만) | 다시 열린 거짓 PASS 없음. 절대 import(`("dotted", …)`)를 풀지 않아 같은 컴포넌트에서 가져온 이름도 제외됨 | `test_g6_provider_defs` RED 1/1(실제 색인) → `f49bc5c` |
| 28 확인 | `f49bc5c`(이 변경만) | 같은 컴포넌트의 상대·절대 import 다시 검사, Case F 유지, 다른 변경 없음 | 마지막 코드 변경 |
RED 로그: `red-residual-on-20d2139.log`, `red-guard-cmd-on-20d2139.log`, `red-residual2-on-733d708.log`, `red-residual3-on-86dbf98.log`, `red-residual4-on-c399b1a.log`, `red-residual5-on-291d18b.log`, `red-provider-defs-on-f3c1cbb.log`(모두 위반 0). 계측 비용(같은 기계, 회귀가 함께 돌던 같은 시점의 상대 비교): 짧은 스레드 100개×호출 1,000회는 `20d2139` 0.90초, `733d708` 19.07초, `86dbf98` 1.10초(따로 잰 값), 최종 `8849672` 1.65초(같은 시점 `86dbf98` 1.87초). 전역 3,000개 provider의 20만 회 호출/요청 스레드 100개는 `8849672` 2.02초/2.48초, 같은 시점 `86dbf98` 1.81초/2.37초, `291d18b` 2.01초/2.45초.

### 17.6 최종 회귀와 릴리스 점검 (최종 코드 `f49bc5c`)
| 항목 | 결과 |
|---|---|
| 전체 회귀 WSL2 Ubuntu 24.04, Python 3.12.3(깨끗한 detached worktree `f49bc5c` + `dist/vmodel-0.1.*`) | **503 통과**, skip 1(xdist 시험 환경 변수 `VMODEL_R7_XDIST_PYTHON` 없음), 1909초 (`wsl-harness-f49bc5c.log`) |
| 전체 회귀 Windows 11, Python 3.13.14 venv, cp949, 한글·공백 경로(`f49bc5c`) | **503 실행, 실패 0**, skip 55(pty가 필요한 사용자 전용 경로 44, POSIX 전용 fork·fifo·forkserver 6, 심볼릭 링크 권한 2, ruff 없음 1, xdist 1, POSIX 권한 1), 4027초 (`windows-harness-f49bc5c.log`) |
| 중간 커밋의 Windows 회귀(참고) | `86dbf98`·`c399b1a`·`291d18b` 실패 1(14회차 C5_reused: D48 R2와 충돌한 옛 기대값 → `e581b36`에서 불변 시험으로 이동, 스레드별 예산은 `test_g6_budget`이 tracer 수준에서 확인), `8849672` 실패 2(같은 것 + Case F → `f3c1cbb`), `e581b36` 501 실행 실패 1(Case F만; 옮긴 C5 불변 시험은 통과). `f3c1cbb`는 WSL 502 통과(skip 1)·Windows 502 실행 실패 0(skip 55)이었고, 최종 `f49bc5c`는 그 뒤 28회차 수정(절대 import 해석)만 더했다. 그 밖의 중간 커밋 WSL 전체 회귀는 다음 수정이 나와 중단했다 |
| 릴리스 사본과 소스 | `release.py --force` 후 `release_check.py` OK(`release-check-f49bc5c.json`): 소스 = 0.2.0 기록 = dist 재계산 core `sha256:2a95adb35aa82abc1ab6380350fd2f3b03ce3d645255d0263f4e48e234228a47`(46 파일), 0.1.0~0.1.5 사본·기록 불변, 태그 `v0.1.2`~`v0.1.5` 불변, `claude plugin validate --strict` 소스·릴리스 통과 |
| 기존 서명 원장·증거 호환 | 하네스 T17(0.1.5 원장·증거를 새 코어로 검증)·T20(0.1.5 → 0.2.0 재고정)·`test_g6_compat`(G1~G5 판정·manifest 불변) 통과. 드릴 S1·S2 원장(후보 core `88edfac2`가 서명, 13건)의 복사본: 재고정 전 audit는 "running core hash differs"로 실패하고 G1~G6 BLOCKED(설계대로, SPEC §11), 증거 4/4 OK → 사용자 재고정(pty) 뒤 audit OK(14건), G1~G6 STALE, DEFECT-001 REVERIFY_REQUIRED, 기존 기록은 다시 쓰지 않음, 원본 다이제스트 불변(`compat-drill-ledger-f49bc5c.txt`) |

### 17.7 판정
지시 §5 기준:
1. CRITICAL·HIGH 결함 없음: 이번에 찾은 재현 가능한 거짓 PASS(분류 B)와 guard 실제 쓰기 우회는 모두 RED 후 고쳤고, 최종 확인(28회차)에서 남은 지적 없음.
2. 재현 가능한 미해결 G6 거짓 PASS 없음: §17.3의 분류 B는 모두 BLOCKED. 남은 것은 분류 A(보수적 BLOCKED, 기능 제약), 정책상 경고(G4 리뷰 몫), 신뢰 경계(주장하지 않음).
3. 재현 가능한 보호 파일 쓰기 우회 없음: `del,` 계열 수정. 남은 guard 항목은 정상 명령 차단(제약)과 주장하지 않는 범위(임의 코드 실행, D24·D25).
4. 전체 회귀를 통과한 최종 코드 `f49bc5c` = 릴리스 사본(core `2a95adb3…`).
5. 기존 서명 원장·증거 호환: §17.6.
6. 미검증 항목 문서화: §17.8.
→ **RELEASE READY.** 단, 릴리스 기록에 "실제 세션의 G6 FAILED → DEFECT → CLOSED 경로는 미관찰(독립 하네스로만 검증)" 한계를 남긴다(§17.2, D47).
확정 절차: 이 기록 커밋을 `main`에 `--ff-only`로 병합하고 이 커밋에 annotated 태그 `v0.2.0`을 단다(원격 푸시 없음). 태그 뒤 확인(`release_check.py --released`: annotated 태그 = `main`, `v0.1.5`가 조상, 태그 시점 플러그인 트리 = 0.2.0 기록·core)은 태그가 이 커밋을 가리키므로 이 문서에 담지 않고 최종 보고에 남긴다.

### 17.8 미검증 항목
- 실제 Claude 세션의 G6 FAILED → DEFECT → 수정 → CLOSED 경로(D47). 하네스(F1·T12, §14.6 시연, `test_g6_*`의 FAILED 판정)로만 검증.
- D48 수정(`733d708`~`f49bc5c`)은 실제 Claude 세션으로 다시 돌리지 않았다(추가 유료 세션 금지). 드릴 S1·S2는 후보 core `88edfac2`로 실행됐고, 최종 core는 하네스와 드릴 원장 복사본 audit로만 확인했다.
- 분류 A의 보수적 BLOCKED(§17.3): 정상 코드가 막힐 수 있다. 사유 메시지가 원인과 해결(fixture를 autouse 대신 요청 등)을 알려 준다.
- 정책상 경고(§17.3): 설정 상수, 다른 컴포넌트·외부 라이브러리에서 가져온 이름의 스텁, weak 이름을 라이브러리 함수로 바꾼 patch, 모듈 수준이 아닌 객체의 인스턴스 patch는 R1이 막지 않는다(G4 리뷰 몫). provider가 같은 단계에서 200회 넘게 시작된 뒤에 건 patch도 보지 못한다.
- 신뢰 경계: 같은 프로세스의 테스트 코드는 계측 줄·토큰을 위조할 수 있다(SPEC §5.7). guard는 모든 셸 문법과 임의 코드 실행을 통제하지 않는다(D24·D25).
- macOS 미검증, Windows Python 3.12 이하의 실제 실행 미검증(§15.7).
- 정적 분석·실행 시점 관찰 기반 판정의 본질적 한계: 검토는 28회 반복했고 회차마다 새 형태가 나왔다. 앞으로도 새 우회·오판이 나올 수 있다.

### 17.9 G7 착수 여부
v0.2.0 확정으로 G7(System Verification, PLAN M6, 제안 0.3.0)의 선행 조건(G6 구현·릴리스)은 갖춰졌다. 착수는 사용자 결정(PLAN M6 "사용자 결정 전 착수 금지")이며, 이번 작업에서는 G7을 구현하지 않았다.
