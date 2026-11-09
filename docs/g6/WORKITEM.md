# v0.2.0 작업 항목: G6 Integration Verification 구현 (V-Model 절차 기록)

작성 2026-11-09. 근거: 사용자 지시(2026-11-09, "VModel DevKit v0.2.0 — G6 Integration Verification 개발", 결정 D1~D8 승인), 확정 설계 `docs/g6/G6-DESIGN.md`(REQ-G6-01~26, D41).
브랜치 `g6-dev`(기준 태그 `v0.1.5` = `78517d5`, 설계 커밋 `fe38239`). main 병합·`v0.2.0` 태그·원격 푸시·유료 헤드리스 실행은 하지 않는다.

## 0. 절차

v0.1.4·v0.1.5와 같다. 절차는 G1~G5를 따르고 판정은 독립 하네스와 독립 검토가 한다(SPEC §5.8, DevKit 코어를 DevKit Gate로 승인하지 않는다).

| 단계 | 이 작업에서 하는 일 | 산출물 |
|---|---|---|
| 요구사항 | 설계 REQ-G6-01~26에 결정 D1~D8 반영, 새 요구사항 REQ-G6-27~34 | §2 |
| 아키텍처·영향 | 변경 파일과 G1~G5 영향 범위 | §3 |
| 상세 설계 | 설계 §4에서 바뀐 부분만 | §4 |
| 테스트 명세 | T01~T20을 하네스 테스트로, 클래스 접미사로 기대 결과 고정 | §5 |
| RED | 불변 릴리스 `dist/vmodel-0.1.5` 대상 `scripts/red_green.py --mode red --marker RED-TARGET` | `test-results/v0.2.0/red-*.log` |
| 구현 → GREEN | 최소 변경, 모듈별 GREEN | 커밋, `test-results/v0.2.0/green-*.log` |
| 독립 검토 | 별도 컨텍스트 읽기 전용 검토자(직접 만든 detached worktree). 지적은 직접 재현한 것만 RED 테스트 후 수정 | §7 |
| 회귀 | 깨끗한 worktree WSL 전체, Windows cp949, 릴리스 빌드, 0.1.5 → 0.2.0 업그레이드 재현, plugin validate | TEST_RESULTS §14 |

## 1. 사용자 결정 D1~D8의 반영 (설계 §9 대응)

| 결정 | 설계 §9 | 반영 |
|---|---|---|
| D1 Core 변경과 최신성 | 1번 | 설계 §1.1 그대로. G6 추가는 G1~G5 manifest를 늘리지 않고, Core 교체 STALE 규칙은 유지. 기존 기록·증거는 다시 쓰지 않는다 |
| D2 N/A 조건 | 2번 | G2·G3 리뷰 둘 다(설계 기본값). REQ-G6-15 그대로. 내부 PASSED + `applicability: not_applicable`, 표시 N/A |
| D3 unit/integration 명령 분리 | 3번 | 설계 기본값(경로가 없어도 기본 argv를 써 둠)을 **바꾼다**: 실제로 있는 통합 테스트 경로만 등록(REQ-G6-27), 기존 프로젝트는 사용자 전용 명령으로 이전(REQ-G6-28). 0개 테스트 성공 종료는 PASS 아님(이미 RESULTS) |
| D4 G4 manifest | 4번 | `.claude/settings.json`을 코드 manifest에 그대로 둔다. 변경 없음(REQ-G6-26 그대로) |
| D5 정적 도달 + 실제 통합 증거 | 5번 | 설계 §4.6의 "하위 프로세스·동적 import는 도달 아님"을 **바꾼다**: 경로 A(정적 호출 경로)와 경로 B(subprocess·IPC·API·동적 import + G4 리뷰 선언·테스트 소스 해시 + G6 실행 계측)로 나눈다(REQ-G6-29~33). 도달은 "호출"이어야 하며 import·참조만으로는 인정하지 않는다 |
| D6 버전 | 6번 | 0.2.0. 0.1.5 태그·릴리스 사본 불변 |
| D7 범위 삭제된 G6 결함 | 7번 | 설계 기본값(CLOSED 아님 + 주석)을 **바꾼다**: 표시 상태 OUT_OF_SCOPE를 더한다(REQ-G6-34). 과거 기록·결함 이력 보존, CR·DEFECT 연결 |
| D8 실전 E2E | 8번 | 계획만(시나리오 A·B, Sonnet 2회, 회당 $2, 합계 $4). 이번에는 실행하지 않고 별도 승인 요청 |

## 2. 요구사항

REQ-G6-01~26은 설계 문서 §2가 정본이다. 아래는 바뀐 것과 새로 더한 것이다.

### 2.1 바뀐 요구사항
- **REQ-G6-11'** G4.INTEGRATION_WIRING(기계, integration 명세가 있을 때만 기록)은 integration 테스트 함수마다 연결 경로를 분류한다.
  - 경로 A(정적): 함수(같은 파일 도우미·요청한 fixture를 깊이 3까지 포함)의 **호출식**이 소스 모듈을 가리키고, 그 모듈들의 import 폐포에 IF provider 모듈과(ARCH consumer가 있으면) consumer 모듈이 들어 있음. 모듈 이름을 import하거나 참조만 하는 것은 호출이 아니다.
  - 경로 B(실행 경로): 정적 호출 경로는 없지만 함수에 subprocess·IPC(multiprocessing, socket)·API(http.client, urllib, requests, httpx, xmlrpc)·동적 import(importlib, `__import__`, runpy) 호출이 있음.
  - placeholder: 함수(도우미·fixture 포함)에 호출식이 하나도 없음 → fail.
  - IF마다: 경로 A 테스트가 하나라도 있으면 pass. 없고 경로 B 테스트가 있으면 G4 리뷰의 선언(REQ-G6-30)이 있을 때 pass, 없으면 pending(verifier). 둘 다 없으면 fail.
  - provider 모듈 patch는 warn(설계 그대로).
- **REQ-G6-19'** `required` G6의 IF 커버리지는 경로 A(이번 실행에서 passed + Validator가 다시 계산한 정적 호출 경로) 또는 경로 B(REQ-G6-32)로만 성립한다.
- **REQ-G6-22'** G6 manifest = 코드 manifest + `reviews/G2.json` + `reviews/G3.json` + `reviews/G4.json`(경로 B 선언의 근거).
- **REQ-G6-24'** N/A 평가는 결함 검증이 아니다. G6 실패를 인용한 결함은 G6이 N/A여도 CLOSED가 아니고 표시 상태 OUT_OF_SCOPE(REQ-G6-34)다.

### 2.2 새 요구사항
- **REQ-G6-27 (D3, init)** 새 `vmodel init`(및 `install`)은 `integration_test`를 **실제로 있고 테스트 함수가 하나 이상 있는 경로**에만 등록한다: `--integration-tests PATH`를 주었거나, 주지 않았는데 `tests/integration/`이 그 조건을 만족할 때. 등록하면 기본 unit argv에 `--ignore=PATH`를 더해 두 명령이 같은 범위를 갖지 않게 한다. 경로·테스트 파일을 만들지 않는다.
  - AC-27a `tests/integration/`이 없으면 `integration_test`를 쓰지 않고 안내만 출력한다.
  - AC-27b `--integration-tests`가 없는 경로, 테스트 함수가 없는 경로, 프로젝트 밖 경로, 설정된 tests 경로 밖, 또는 unit 실행 범위 전체(예: `tests`, `.`)이면 init을 거부하고 아무것도 만들지 않는다.
  - AC-27c 등록된 config는 스키마를 통과하고, unit argv와 integration argv의 테스트 경로가 겹치지 않는다.
- **REQ-G6-28 (마이그레이션)** 기존 프로젝트에는 사용자 전용 명령 `vmodel configure-tests --integration PATH [--timeout S]`(TTY 확인, guard가 에이전트 실행을 막음)를 둔다. REQ-G6-27과 같은 경로 검증을 하고, 바뀔 config를 보여 준 뒤 'yes'에만 쓰며, 서명 원장에 `config` 기록(이전·새 config 해시)을 남긴다. unit argv가 pytest 형식이 아니면 거부하고 수동 편집을 안내한다. `integration_test`가 없는 0.1.x config는 그대로 유효하다(REQ-G6-01·06).
- **REQ-G6-29 (D5, import-only·빈 테스트)** 정적 도달은 호출식으로만 성립한다. `assert True`, `pass`, docstring만 있는 함수, import 후 모듈·심볼을 참조만 하는 함수는 IF를 덮지 못한다(G4 fail, G6 IF_COVERAGE fail).
- **REQ-G6-30 (경로 B 선언)** G4 리뷰 `interfaces[]` 항목에 `runtime_paths: [{"test": "TEST-xxx", "kind": "subprocess"|"ipc"|"api"|"dynamic_import", "test_file_sha256": "sha256:…", "entry", "note"}]`를 둔다. G4는 선언이 (a) 그 IF를 `verifies`에 가진 integration TEST, (b) Validator가 그 함수에서 찾은 실행 경로 종류, (c) 그 함수가 있는 테스트 파일의 현재 sha256과 맞을 때만 인정한다. 안 맞으면 pending(재리뷰). `vmodel wiring WI`가 verifier에게 함수 위치·분류·해시를 보여 준다(읽기 전용).
- **REQ-G6-31 (실행 계측)** G6은 통합 명령을 Validator Core의 계측 모듈(`tracer/sitecustomize.py`)을 `PYTHONPATH`로 주입해 실행한다. 실행 중 생긴 모든 Python 프로세스(하위 프로세스 포함)가 감시 대상 파일(IF provider·consumer 설계 단위 모듈, integration 테스트 파일)의 함수 실행을 그때의 pytest 테스트 ID(`PYTEST_CURRENT_TEST`)와 함께 기록한다. 계측 파일은 실행 폴더 `trace/`에 남고 서명된 record.json에 해시와 요약이 들어간다. 계측 실패는 테스트를 깨지 않는다.
- **REQ-G6-32 (경로 B 판정)** 경로 B로 IF가 덮이려면 모두 필요하다: 선언이 현재 G4 PASS가 인정한 리뷰(`G4.REVIEW` `review_sha256` = 지금 `reviews/G4.json`)에 있음, 선언 해시 = 지금 테스트 파일 해시, Validator가 다시 찾은 실행 경로 종류와 일치, 그 테스트가 이번 실행에서 passed, 계측이 그 테스트 동안 provider 모듈 함수 실행과(ARCH consumer가 있으면) consumer 모듈 함수 실행을 기록. 선언은 있지만 실행 증거가 부족하면 G6은 BLOCKED(`integration_evidence_insufficient`, 중립 차단)이고 PASS하지 않는다. AI 리뷰 문장만으로 IF를 덮지 않는다.
- **REQ-G6-33 (경로 A 교차 확인)** 경로 A로 덮인 IF라도, 계측이 그 테스트 함수 실행을 기록했는데 provider 함수 실행이 없으면 IF_COVERAGE는 warn("정적으로는 닿지만 실행되지 않음: 목 대체 의심")이다. 판정은 바꾸지 않는다(데이터 타입 IF 등 오탐 가능).
- **REQ-G6-34 (D7, OUT_OF_SCOPE)** 결함 표시 상태에 OUT_OF_SCOPE를 더한다(D37의 6종 + 1). 조건: 결함의 종료 Gate(인용한 실패 중 가장 하위)가 G6이고, G6이 지금 PASSED + `applicability: not_applicable`(현재 manifest, STALE 아님). 표시에는 제거된 IF·TEST ID와 그것을 `removed_ids`에 둔 CR·DEFECT ID와 사유, 과거 FAILED 기록을 함께 보인다. CLOSED로 치지 않고 `verified_by`는 비운다. 결함 저장 형식은 그대로다(스키마 enum에 G6·P6·IF만 추가).

## 3. 아키텍처·영향 분석

| 파일 | 변경 | G1~G5 영향 |
|---|---|---|
| `data/schemas/*`(생성기 `scripts/gen_schemas.py`) | config `integration_test`, review `integration_applicability`·`interfaces`, defects `gate`+G6·`root_cause_phase`+P6·`removed_ids`+IF, CR `removed_ids`+IF | 선택 키·enum 추가만. 0.1.x 산출물은 그대로 유효 |
| `data/gates.json` | G6 구현, G4 체크 2개, G5.SCOPE, 설명 | IF·integration 명세 없는 WI의 G4, `integration_test` 없는 G5는 판정 불변 |
| `gates.py` | G4 확장, G5.SCOPE·NO_WEAKENING(설정 시만), `g6_applicability`, `eval_g6`, 결함 추적(N/A 제외, Gate별 TEST_MAPPING), 중립 차단 2개 | eval_g5 실행부는 **고치지 않는다**(설계 §4.5의 `_execute_suite` 분리를 하지 않음: G5 무변경 우선, G6은 같은 runner 함수를 따로 호출) |
| `wiring.py`(새) | 모듈 색인, 함수 단위 호출 분석, 실행 경로 분류, placeholder, patch | G4에서 IF·integration 명세가 있을 때만 호출 |
| `tracer/sitecustomize.py`(새, Core) | 실행 계측 | G6 실행에서만 주입 |
| `status.py` | N/A·미평가 표시, `gate_summary`, `scope_warnings`, `g6_applicability_preview`, next_action, MVP_NOTE, trace IF 행, report, OUT_OF_SCOPE | 표시만 |
| `cli.py` | `render_gate` 적용성, `configure-tests`, `wiring`, init `--integration-tests`, lock 안내 | — |
| `setup_project.py` | init 등록 규칙, `configure_tests` | 새 init의 config만 |
| `hook.py` | USER_ONLY에 `configure-tests` | guard 규칙 1개 추가 |
| skills·agents·`VMODEL.md`·README | G6 단계, 리뷰 기록 의무, 통합 테스트 작성 규칙, 문구 | — |
| `__init__.py`, `plugin.json` | 0.2.0 | Core 해시 변경 → 업그레이드 시 기존 규칙대로 전부 STALE(D1) |

원장 형식·서명·앵커·manifest 계산 함수·Core 무결성 규칙은 바꾸지 않는다. 원장 기록 종류 `config`가 새로 생긴다(기존 Validator는 모르는 종류를 무시한다: Gate 질의가 `type`으로 거른다).

## 4. 상세 설계 (설계 §4와 다른 부분)

### 4.1 정적 호출 분석 (`wiring.py`)
1. 모듈 색인: 설정된 source 파일마다 `__init__.py`가 없는 가장 깊은 상위 디렉터리를 패키지 루트로 보고 점 표기 이름을 만든다.
2. 소스 모듈 import 그래프(상대 import 포함, 색인 밖 무시) → 폐포.
3. 테스트 함수의 호출식(`ast.Call`)만 시작점이다. 호출 대상 이름을 테스트 파일의 import 표로 해석한다(`from m import f` → `f(...)`, `import a.b as x` → `x.f(...)`, `a.b.f(...)`의 가장 긴 소스 모듈 접두사). 같은 파일 도우미 함수 호출과 매개변수로 요청한 fixture(같은 파일 또는 tests 경로의 `conftest.py`)의 본문을 깊이 3까지 따라간다.
4. 실행 경로 종류: 같은 import 표로 해석한 호출 이름이 `subprocess.*`·`os.system`·`os.popen`·`os.spawn*`·`asyncio.create_subprocess_*` → subprocess, `multiprocessing.*`·`concurrent.futures.ProcessPoolExecutor`·`socket.*` → ipc, `http.client.*`·`urllib.request.*`·`requests.*`·`httpx.*`·`xmlrpc.client.*` → api, `importlib.import_module`·`__import__`·`runpy.*` → dynamic_import.
5. placeholder: 따라간 범위 전체에 호출식이 없음.
6. patch: `patch("…")`·`patch.object(X, …)`·`monkeypatch.setattr(…)`의 대상이 provider 모듈을 가리킴.

### 4.2 실행 계측 (`tracer/sitecustomize.py`)
- Validator가 실행 폴더에 `trace-spec.json`(감시 파일 절대경로 → 라벨, 출력 폴더)을 쓰고 `PYTHONPATH=<core>/tracer`, `VMODEL_TRACE_SPEC=<spec>`를 정리된 환경 뒤에 더한다(에이전트 환경의 `PYTHON*`·`VMODEL_*`는 이미 제거).
- Python 3.12+는 `sys.monitoring` PY_START(감시 밖 코드는 DISABLE), 그 밖은 `sys.setprofile`+`threading.setprofile`. 함수 코드만 센다(`<module>` 제외: import만으로 실행으로 치지 않음).
- 기록: 프로세스마다 `trace/<pid>-<rand>.jsonl`, 첫 줄 머리(pid, ppid, `sys.orig_argv`, 방식), 이후 새 (테스트 ID, 라벨, 함수) 조합마다 한 줄. 프로젝트에 이미 `sitecustomize`가 있으면 이어서 불러온다.
- 한계: 같은 프로세스 신뢰 경계(SPEC §5.7). 테스트 코드는 계측 파일을 위조할 수 있다(JUnit과 같은 한계). G4.TEST_INTEGRITY가 테스트·지원 코드의 `VMODEL_TRACE` 문자열을 잡는다. `-I`/`-E`/`-S`로 시작한 하위 Python은 계측되지 않는다(→ 경로 B 증거 부족 BLOCKED). 세션 범위 fixture가 띄운 하위 프로세스는 처음 테스트에 귀속된다(→ 보수적 BLOCKED). pytest가 아닌 러너는 테스트 ID가 없어 경로 B를 증명할 수 없다.

### 4.3 G6 체크 (설계 §4.3에 더함)
- G6.IF_COVERAGE: IF마다 경로 A 또는 경로 B. 선언된 경로 B의 실행 증거 부족 → blocked(`integration_evidence_insufficient`). 그 밖의 미충족 → fail. 경로 A 교차 확인 경고(REQ-G6-33).
- record 추가 키: `runtime_trace`(활성 여부, 프로세스 수, 테스트별 실행 라벨 요약, 오류), `interfaces[].tests[TEST].path`(`static`/`runtime`/`none`), `interfaces[].covered_by`.
- G6 증거 record.json은 G5 증거 키 전부 + `command_source`, `config_sha256`, `integration_test_sha256`, `runtime_trace`.

### 4.4 결함 표시 (OUT_OF_SCOPE)
`closure_view` 판정 순서: UNKNOWN(원장) → **OUT_OF_SCOPE** → VERIFICATION_FAILED → UNKNOWN(증거) → CLOSED/REVERIFY_REQUIRED → FIX_APPLIED/OPEN. `defect_trace`는 N/A 기록을 `verified_by`·`verification_history`·`last_verification`에서 뺀다. OUT_OF_SCOPE 데이터: `scope_removal: {"g6_record": R…, "removed_ids": {ID: [CR/DEFECT…]}, "reasons": {CR/DEFECT: 사유}}`.

## 5. 테스트 명세 (구현 전 고정)

클래스 접미사: `Red`(0.1.5에서 목표 assertion 실패, 메시지에 `RED-TARGET`), `Char`·`Invariant`(둘 다 통과), `Accept`(새 코어에서만). 픽스처: `tests/fixtures/pipeline`(2컴포넌트, IF-001 provider ARCH-001 parser → consumer ARCH-002 report, IF-002 provider ARCH-002 → EXTERNAL, `tests/unit`·`tests/integration`), `tests/fixtures/single`(1컴포넌트, IF 0, integration 명세 0, 외부 끝점 2개). 하네스는 사용자 역할로 config를 직접 쓴다(분리 명령).

| 사용자 T | 테스트 (모듈 / 클래스) | PASS 기준 |
|---|---|---|
| T01 실제 Provider/Consumer PASS | `test_g6_gate` GateRed.test_T01 | pipeline G6 PASSED, 증거 kind `integration_test`, record에 명령·종료 코드 0·IF별 `static` 도달·통과 TEST, verify-evidence OK |
| T02 실패 → FAILED | GateRed.test_T02 | provider 결함 → G6 FAILED, `failed_cases`, 실패 서명 |
| T03 integration_test 누락 → BLOCKED | `test_g6_config` ConfigRed.test_T03 | BLOCKED `misconfigured`, 실행 증거 없음, next_action 사용자 조치 |
| T04 unit 재사용 우회 차단 | GateRed.test_T04 | integration argv = unit argv → G6 FAILED(SCOPE, TEST_MAPPING) |
| T05 통합 테스트로 G5 부당 통과 금지 | `test_g6_scope` ScopeRed.test_T05 | 분리 config에서 unit 명령이 통합 테스트 실행 → G5 FAILED(G5.SCOPE). unit 명세 함수 없이 통합 테스트만 있으면 G4·G5 통과 못 함 |
| T06 빈·placeholder 테스트 | `test_g6_wiring` WiringRed.test_T06 | `assert True`·`pass` 통합 함수 → G4 FAILED(INTEGRATION_WIRING placeholder) |
| T07 IF↔테스트 매핑 누락 | WiringRed.test_T07, GateRed.test_T07 | IF-002 함수 없음 → G4 FAILED(TEST_CODE). 통합 명령이 IF-002 테스트를 실행하지 않음 → G6 FAILED(TEST_MAPPING not executed, IF_COVERAGE) |
| T08 import-only | WiringRed.test_T08 | provider import + 참조만 → G4 FAILED(INTEGRATION_WIRING) |
| T09 subprocess/API 통합 | WiringRed.test_T09_* | 선언 없음 → G4 REVIEW_REQUIRED, 선언(해시 일치) → G4 PASSED → G6 PASSED(`runtime`), 해시 불일치 → REVIEW_REQUIRED, 하위 프로세스가 provider를 안 부르면 G6 BLOCKED `integration_evidence_insufficient` |
| T10 정당한 N/A | `test_g6_applicability` NaRed.test_T10 | single + G2·G3 확인 → PASSED·N/A, 증거 없음, 출력에 N/A, "integration tests passed" 없음 |
| T11 IF 삭제 N/A 우회 차단 | NaRed.test_T11_* | `removed_ids` 없이 IF 삭제 → BLOCKED `applicability_unconfirmed`. 정당화 있어도 G2·G3 확인 없으면 BLOCKED |
| T12 N/A가 결함 CLOSED 안 함 | `test_g6_rework` ReworkRed.test_T12 | G6 실패 결함 → 범위 삭제(CR) → N/A → OUT_OF_SCOPE, `verified_by` 없음, CR 연결, FAILED 기록 보존 |
| T13 실패 → 수정 → 재검증 | ReworkRed.test_T13 | FAILED → DEFECT 없으면 BLOCKED → DEFECT(G6, P4) → 수정 → PASSED, CLOSED |
| T14 IF 변경 시 STALE | `test_g6_compat` CompatRed.test_T14 | architecture IF 변경 → G2~G6 STALE, 리뷰 G2 교체 → G6만 STALE, 테스트 파일 변경 → G4~G6 STALE |
| T15 G1~G5 증거 보존 | CompatRed.test_T15 | G6 평가 전후 G1~G5 기록 바이트·상태 동일, G6 미평가는 IN_PROGRESS+`not_evaluated` |
| T16 Core 변경 → 기존 규칙 | CompatAccept.test_T16 | Core 해시 변경(재고정) 후 G1~G6 PASS 전부 STALE, 이전 기록 유지 |
| T17 0.1.5 원장·manifest 호환 | CompatInvariant/Accept | 0.1.5가 서명한 원장·증거가 audit·verify-evidence 통과, G1~G5 manifest 해시 동일, 같은 이력의 G1~G5 투영 동일(IF 없는 WI) |
| T18 Runner 증거 없이 PASS 불가 | GateRed.test_T18_* | 0 tests, junit 없음, 가짜 증거·결과 파일 주입, 시간 초과, 시작 실패 → PASS 아님 |
| T19 Windows 경로·인코딩 | `test_g6_encoding` EncodingRed | 한글·공백 경로, CP949 바이트 출력, 계측 경로 → G6 PASSED, 증거 검증 OK (Windows 회귀에서 실제 실행) |
| T20 업그레이드·마이그레이션 | `test_g6_config` MigrationRed/Accept | init 등록 규칙(REQ-27), `configure-tests`(pty), 0.1.5 config 유효, 0.1.5 설치 프로젝트 → 0.2.0 재고정 → 마이그레이션 → G6 |
| (보조) 계측 단위 | `test_g6_tracer` TracerAccept | 하위 프로세스 기록·테스트 ID 귀속, setprofile 경로, 계측 오류가 테스트를 깨지 않음 |
| (보조) 상태 표시 | `test_g6_status` StatusRed | `gate_summary`, 미평가·N/A·required 문구, trace IF 행, next_action 3종, mvp_note |

기존 225개 중 의도적으로 바꾸는 기대값(설계 §6.1, 첫 단계에서 grep으로 재생성): `test_gates.py` 32~35·43행, `test_rework_flow.py` 47·65행, `test_defect_evidence.py` 126·130행, `test_defect_closure.py` 219행, `test_version_compat.py` 투영(G4 새 체크 2개 제외), `helpers.Sandbox.review()`(IF가 있으면 G4 리뷰에 `interfaces`). 각 변경 위치에 0.1.5 기대값과 근거 REQ를 주석으로 남긴다.

## 6. 진행 기록
(구현 중 갱신)

## 7. 독립 검토
(검토 후 갱신)
