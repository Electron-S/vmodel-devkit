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
- **REQ-G6-32 (경로 B 판정)** 경로 B로 IF가 덮이려면 모두 필요하다: 선언이 현재 G4 PASS가 인정한 리뷰(`G4.REVIEW` `review_sha256` = 지금 `reviews/G4.json`)에 있음, 선언 해시 = 지금 테스트 파일 해시, Validator가 다시 찾은 실행 경로 종류와 일치, 그 테스트 함수가 이번 실행에서 실제로 돌았고 passed, 계측이 그 테스트의 **호출 단계**에서 provider 모듈 함수 실행과(ARCH consumer가 있으면) consumer 모듈 함수 실행을 기록, 선언 종류가 subprocess·ipc면 provider 실행이 테스트 함수와 **다른 프로세스**에서 일어남(검토 F6). 선언은 있지만 실행 증거가 부족하면 G6은 BLOCKED(`integration_evidence_insufficient`, 중립 차단)이고 PASS하지 않는다. AI 리뷰 문장만으로 IF를 덮지 않는다.
- **REQ-G6-33 (실행 확인, 검토 3회차로 확정, D43)** G6은 계측이 실행을 본 분석 대상 함수만 IF 근거로 쓴다. 경로 A는 그 함수의 실행과 **실행 전체에서** provider(와 ARCH consumer) 함수가 한 번이라도 실행됨을 요구한다(아무 데서도 안 돌았으면 BLOCKED `integration_evidence_insufficient`). 테스트별 provider 귀속은 경고만 낸다. 경로 B 근거 없는 선언은 IF가 덮이면 경고, 아니면 BLOCKED. 계측이 아예 없으면 BLOCKED(JUnit만으로 인정하지 않음), 잘렸으면 "실행되지 않음" 판단은 BLOCKED. 데이터 전용 IF(dataclass·Enum)는 BLOCKED(한계).
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
| 단계 | 커밋 | 결과 |
|---|---|---|
| 테스트 먼저 | `c6bc3ce` | 작업 항목, 픽스처 2개, G6 하네스 10개 모듈, `red_green.py --marker` |
| RED 1차 | `c6bc3ce` | 75개 중 70 기대 충족, 위반 5: 도우미 `replace_function`이 `re.sub`로 역슬래시를 해석해 주입 소스가 문법 오류(같은 이유로 "엉뚱한 이유의 RED"가 섞일 수 있어 전부 다시 돌림), C2가 서로 다른 샌드박스의 manifest를 비교(workitem.json 생성 시각이 달라 항상 다름) |
| 테스트 보정 1 | `aab3422` | 함수 교체를 함수형 치환으로, C2는 같은 프로젝트를 두 코어로 해시 |
| RED 2차 | `aab3422` | 75개 중 72, 위반 3: G5 PASS 뒤 통합 테스트 파일을 바꾸는 시나리오가 기존 규칙 G5.NO_WEAKENING(test_changes 정당화)에 먼저 걸림 |
| 테스트 보정 2 | `5430a1e` | `justify_test_change` 도우미(CR `test_changes`) |
| 기존 225개 + 새 helpers, 0.1.5 대상 | `c6bc3ce` | 223 통과, 오류 2: `copy_plugin`이 읽기 전용 릴리스 사본을 복사해 쓰기 실패(테스트 환경 문제, helpers 변경과 무관) → `copy_plugin`이 사본을 쓰기 가능하게 바꿈 |
| 구현 | `3239eba` | 스키마 → gates.json → wiring → tracer → gates(G4·G5·G6·결함) → status → cli·setup·hook → 지침 → 0.2.0 |
| 구현 중 발견 | `3239eba` | (1) 계측이 class 본문을 함수 실행으로 셈 → CO_OPTIMIZED 함수만. (2) API 경로 테스트가 정적으로 분류됨: 분석이 테스트 안 중첩 class의 메서드 본문까지 걸어 들어감 → 중첩 def·class·lambda는 테스트가 이름으로 부를 때만 따라감. 같은 원인으로 "호출되지 않는 중첩 def에 provider 호출을 숨긴 placeholder"가 통과하던 우회를 막고 RED 테스트 추가(`test_T06_unused_nested_call_does_not_hide_a_placeholder`). (3) N/A next_action이 "G1-G5 verified"로 시작 → "G1-G5 PASSED, G6 N/A"(REQ-G6-17). (4) 기존 불변식 `hook.py`가 0.1.4와 바이트 동일 → configure-tests USER_ONLY 추가만 허용하도록 조정 |
| RED 최종 | `3239eba`(깨끗한 worktree) | 76/76 기대 충족(위반 0, 표지 강제), 실패 사유 확인: G6 미구현 BLOCKED, G4가 placeholder·import-only 통과, G5가 통합 테스트 수용, init·configure-tests 옵션 없음 |
| GREEN | `3239eba`(깨끗한 worktree) | 83/83(Accept 7 포함) |
| 전체 하네스 1차 | 작업 트리(`3239eba` 직전) | 308개 중 307, 실패 1 = 위 (4) |
| 검토 1회차 | `3239eba` → `9fd0075`(테스트) → `c216910`(수정) | §7.1. RED 19/19(대상 3239eba), 전체 327/327, Windows 308 실행·실패 0 |
| 검토 2회차 | `c216910` → `903a2b3`(테스트) → `08469ae`(수정) | §7.2. RED 19/19(대상 c216910), 전체 346/346 |
| D4 간헐 실패 | `54eac4c` | Windows `c216910`·WSL 부하 중 각 1회: D4가 pytest 출력의 소요 시간을 비교. 테스트 수정 |
| 검토 3회차 | `08469ae` → `359680e`(테스트) → `14b34af`(수정, D43) | §7.3. RED 13/13(대상 08469ae), F2·N1 기대값은 D43으로 경고 있는 PASSED(F2는 특성 테스트로 `5e64974`) |
| 최종 | `14b34af`(코드), `5e64974`(테스트) | WSL 360/360, GREEN 135/135, 릴리스 사본 177/177, RED 76/76(0.1.5)·19/19·19/19·13/13, 릴리스 점검 OK, Windows 360 실행·실패 0·skip 48 |

## 7. 독립 검토
### 7.1 1회차 (`3239eba`, 별도 컨텍스트, 작업 트리 읽기 전용, 사본에서 재현)
지적 12건(주요 7, 부 4, nit 1). 사용자 전역 규칙에 따라 검토자 말을 그대로 받지 않고, 지적마다 `tests/test_g6_review.py`의 테스트로 **직접 재현**한 뒤(RED 대상 = 검토한 빌드 `git archive 3239eba plugins/vmodel`) 고쳤다. RED 19개 모두 목표 assertion으로 실패(`red-review-c216910-on-3239eba.log`), 수정본 GREEN.

| 지적 | 판정 | 처리 (`c216910`) |
|---|---|---|
| F1 주요: 실행되지 않은 함수로 IF 인정(수집되지 않는 파일, `__test__ = False` + smoke 함수) | 재현 | G4는 TEST ID를 가진 함수 하나하나가 경로 A·B여야 함. G6은 계측이 실행을 본 분석 대상 함수만 인정(계측이 아예 없을 때만 JUnit classname/name 대조) |
| F2 주요: 참조·가림 이름을 호출로 인정(`report.__name__.endswith`, 중첩 def·매개변수 기본값이 import를 가림) | 재현 | 정적 분석 재작성: 함수 지역 범위 우선, 호출은 소스 모듈의 최상위 def/class(또는 그 클래스 메서드)로 풀릴 때만. 경로 A도 계측이 있으면 호출 단계에서 provider가 돌아야 인정(못 돌면 경고 + 불인정; 모든 테스트가 그러면 FAILED) |
| F3 주요: 리뷰 `interfaces[].id`가 리스트면 G4 내부 오류 | 재현 | 문자열 id만 사용 → REVIEW_REQUIRED |
| F4 주요: trace 폴더·junit 경로에 디렉터리를 심으면 G6(그리고 같은 runner를 쓰는 G5) 내부 오류 | 재현(G5 경로는 0.1.x부터 있던 문제를 같이 발견) | trace는 정규·비심볼릭 파일만 읽고 해시(크기 상한), 증거의 비정규 파일은 해시하지 않고 `not_regular_file`로 기록. 결과는 기록된 FAILED/PASSED |
| F5 부: 테스트 코드가 계측 줄을 위조해 경로 B 증명 | 재현(검토자) | 코드 수정 없음. 같은 프로세스 신뢰 경계(SPEC §5.7)의 한계로 문서화하고, G4.TEST_INTEGRITY의 `VMODEL_TRACE` 문자열 검사는 "우발적 언급만 잡는다"고 정정 |
| F6 부: 경로 B 증거가 선언한 경로와 무관(autouse fixture가 provider 실행) | 재현 | 계측이 pytest 단계를 기록, 증거는 호출 단계만, subprocess·ipc는 테스트 함수와 다른 프로세스에서 provider 실행 필요 |
| F7 주요(오판): 클래스 테스트의 self 도우미, unittest setUp 별칭, 인자 lambda, star import가 "none" | 재현 | self 메서드·setUp/setup_method(별칭 포함)·인자 lambda·star import·모듈 수준 인스턴스 추적 |
| F8 주요(오판): `__init__.py` 없는 패키지, `src.` 접두 import | 재현 | 모듈을 파일 경로로 식별, 경로의 고유한 점 접미사 전부로 해석(겹치면 일반 import 이름 소유자만) |
| F9 부(오판): 의존성 주입(provider를 consumer 호출 인자로 넘김) | 재현 | 소스 호출의 인자로 넘긴 소스 def/class를 도달로 인정(경로 A). 사용자 지시의 "DI"는 정적 경로로, 동적 import는 경로 B 종류로 둔다 |
| F10 부: `verifies`가 리스트가 아니면 trace·wiring 내부 오류 | 재현 | 방어적 목록 처리 |
| F11 부: `tests/integration/..`, `tests/.`를 경로로 받음 | 재현 | 정규화 후 검사 |
| F12 nit: N/A인데 머리줄이 "G6 PASSED" | 재현 | 머리줄 "G6 N/A", N/A 평가가 실패하면 "recorded as PASSED" 문구를 쓰지 않음 |

검토자가 맞다고 확인한 것: 설정 속임수(unit argv 재사용, 전체 tests, 0 tests, junit 없음, skip, `-k` 제외)는 실패, 시작 실패는 `tool_unavailable`, `integration_test` 없음·잘못됨은 실행 없이 `misconfigured`, 에이전트 PYTHONPATH·PYTEST_ADDOPTS 제거, 리뷰 교체는 G6 STALE·인정된 리뷰만 사용, N/A 조건 전부와 우회 없음, N/A의 결함 검증 제외·OUT_OF_SCOPE, 중립 차단의 3회 규칙 제외, IF 없는 WI·`integration_test` 없는 G5의 0.1.5 경로 유지.

### 7.2 2회차 (`c216910`)
1회차 수정의 재검토. 1회차 12건 중 닫힘 6(F1·F3·F9·F10·F11·F12), 부분 5(F2·F4·F6·F7·F8), 문서화 1(F5). 새 지적 11건(주요 10)과 0.1.x부터 있던 내부 오류 2건. 전부 `tests/test_g6_review2.py`로 직접 재현했다(RED 대상 = `git archive c216910 plugins/vmodel`). 처음 RED에서 2건(N1, N5c)은 내 테스트 잘못으로 재현되지 않아(목 테스트가 스레드 주기보다 짧음, 함수 제거 순서 때문에 새 클래스가 지워짐) 테스트를 고쳐 다시 재현했다. 수정 `08469ae`.

| 지적 | 처리 |
|---|---|
| N1 주요: conftest의 백그라운드 스레드가 provider를 돌리면 목 테스트가 근거가 됨 | 계측이 다른 스레드를 그 스레드를 시작한 테스트·단계에 귀속(`threading.Thread.start` 감쌈). import 때 시작한 스레드는 어느 테스트에도 속하지 않음 |
| N2 주요: fork 자식이 부모 trace 파일에 씀 → "다른 프로세스" 판정 오류, forkserver는 다른 테스트에 귀속 | `os.register_at_fork`로 자식이 자기 파일을 엶. forkserver는 서버를 시작한 테스트의 환경을 물려받아 귀속이 틀릴 수 있다(한계, 문서화) |
| N3 주요: 깊게 중첩된 trace 줄로 내부 오류 | 줄 길이 상한, RecursionError·MemoryError 포함 무시하고 오류로 기록 |
| N4 주요: trace를 지우면 JUnit만으로 인정 | 계측이 아예 없으면 BLOCKED, JUnit 대체 인정 제거 |
| N5 주요: 호출되지 않는 참조(모듈 수준 def가 import를 가림, 지역 재대입, setUp 지역 별칭, 호출되지 않는 lambda, 비consumer 호출로 주입) | 모듈 수준 바인딩은 문장 순서, 지역에서 import와 대입이 겹치면 지역 값, setUp 별칭은 setUp 범위, lambda·callable은 pytest.raises/warns·assertRaises 등 호출자에 넘긴 것만, 주입은 consumer 호출에만 |
| N6 주요: 프로젝트 파일이 `json`·`http` 이름을 점유 | 점유 이름을 프로젝트 루트 기준 경로, 최상위 소스 루트(예 `src/`) 기준 경로, 두 부분 이상인 일반 패키지 이름(테스트는 pytest 이름)으로 제한 |
| N7 주요: 심볼릭 링크 junit이 해시되지 않음(1회차 F4 수정의 회귀) | 링크를 거친 정규 파일은 0.1.x처럼 내용으로 해시, 디렉터리·FIFO만 기록 |
| N8 주요: fixture·setup_method에서 provider가 돌면 G6 FAILED, REQ-G6-33과 모순 | 경로 A 실행 확인은 어느 단계든 인정, 근거 없는 주장은 FAILED가 아니라 경고/BLOCKED(REQ-G6-33 갱신) |
| N9 주요: 계측 상한 2만에서 조용히 잘림 → 거짓 FAILED | 노드 ID 매개변수 제거, 상한 10만, 절단 표지, 잘렸으면 BLOCKED |
| N10 주요: 모듈 수준 인스턴스(`cli = _Cli()`), `__init__`의 star 재내보내기 | 둘 다 추적 |
| N11 주요: 네임스페이스 패키지의 `from . import mod` | 경로 기준으로 해석 |
| P1(0.1.x부터): 자릿수 한도를 넘는 정수가 든 리뷰로 G4 내부 오류 | `load_json`이 ValueError·RecursionError를 산출물 오류로 |
| P2(0.1.x부터): provider·component가 목록이면 trace·report 내부 오류 | 문자열이 아닌 값 방어(`dangling`, `downstream`) |

1회차의 F2 G6 기대값(모든 IF-001 테스트가 목이면 FAILED)은 N8 결정에 따라 BLOCKED로 바꿨다(`test_F2_mocked_provider_in_every_test_of_the_interface_fails_g6`, 근거 주석).

### 7.3 3회차 (`08469ae`)
2회차 수정의 재검토. N1~N11·P1·P2 중 닫힘 9, 부분 5(N1·N5a·N6·N10·P1/P2 계열), 그리고 새 지적 14건(주요 7). 핵심은 **같은 프로세스 안의 테스트별 귀속이 양쪽으로 틀린다**는 것: 정상 코드(fixture가 띄운 서버, 모듈 수준 스레드 풀)가 거짓 BLOCKED가 되고, autouse·세션 fixture·asyncio 작업은 목 테스트에 근거를 줬다. 귀속 규칙을 덧대는 대신 판정에 믿을 수 있는 실행 사실만 쓰기로 했다(D43). 지적은 `tests/test_g6_review3.py`로 재현(RED 대상 = `git archive 08469ae plugins/vmodel`, 13/13 목표 assertion 실패) 후 수정 `14b34af`.

| 지적 | 처리 |
|---|---|
| R1 주요: autouse·teardown fixture가 provider를 돌리면 목 테스트가 근거 | D43: 테스트별 귀속은 경고만, 판정은 실행 전체의 provider 실행 + 함수 실행. 목 판단은 G4 리뷰(D41 결정 2) |
| R2 주요(회귀): fixture가 띄운 API 서버의 처리 스레드가 setup 단계로 기록돼 경로 B BLOCKED, 공유 스레드 풀 consumer가 BLOCKED | 스레드는 소유 테스트의 **현재** 단계로 기록(소유 테스트가 끝나면 detached), 경로 A 테스트별 귀속은 경고만 |
| R3 주요: asyncio 작업으로 목 테스트에 근거 | D43으로 경로 A 판정에서 테스트별 귀속을 쓰지 않음. 경로 B의 의도적 위조는 같은 프로세스 한계(F5) |
| R4 주요(회귀): 모듈 수준 `report.DEBUG = True`가 `report` 바인딩을 지움 | 대입 대상은 평범한 이름만 바인딩 |
| R5 주요(회귀): `try: import … except ImportError: x = None` 대체 값이 import를 덮음, 바인딩 순회가 너비 우선 | 실제 소스 순서, if/try 분기 병합에서 import·def·class·별칭이 다른 분기의 대체 값보다 우선. 함수 안에서도 같은 대체 패턴 인정 |
| R6 주요(회귀): `src/__init__.py` + `pythonpath = ["src"]`, 중첩 소스 루트 | import 루트를 프로젝트 루트·pyproject pythonpath(명시)·설정 source glob 접두사·최상위 디렉터리(추론)에서. 추론 루트에서는 표준 라이브러리 이름을 점유하지 않음 |
| R7 주요: 순환 star 별칭으로 RecursionError 내부 오류 | symbol() 재진입 방지, 분석 중 RecursionError는 판단 불가로 처리 |
| R8 부: 계측 상한(10만 줄)이 판독 상한(32MiB)보다 커서 잘림 표지가 사라짐 | 계측 바이트 상한 24MiB, 판독 상한을 넘는 파일은 잘린 것으로 |
| R9 부: `consumers: 5`로 trace 내부 오류 | 방어적 목록 처리 |
| R10 부(0.1.x부터): 원장 줄의 거대 정수로 status·gate·audit 내부 오류 | 원장 판독이 ValueError·RecursionError를 원장 오류로(BLOCKED) |
| R11 부: pytest.raises 등에 넘긴 모든 인자를 호출로 봄 | 호출되는 인자 위치만(raises·warns·assertRaises/Warns는 두 번째, *Regex는 세 번째, deprecated_call은 첫 번째) |
| R12 부(전부터): 매개변수 ID에 `::`(IPv6) | 노드 ID에서 `[`를 먼저 잘라 냄 |
| R13 nit: 계측이 `current_thread()`로 _DummyThread를 만듦 | `get_ident()`와 `threading._active` 조회 |
| R14 nit: IF_COVERAGE BLOCKED 설명이 항상 "declared runtime paths" | 일반 문구로 |

문서화로 남긴 것(검토자도 문서화가 맞다고 본 것): forkserver·이전 테스트가 만든 fork 풀의 귀속, 세션·모듈 범위 fixture 서버의 경로 B(BLOCKED, 보수적), 데이터 전용 IF(BLOCKED), "provider가 돎 = 파일의 어떤 함수든", 절단·삭제는 PASS가 아니라 BLOCKED, 의도적 위조(F5), lambda 추적 범위(N5d)의 선택. **3회차 수정(`14b34af`) 자체는 독립 재검토를 받지 않았다**(미검증, §8 이후 남은 위험).

### 7.4 최종 검증: 사용자 Case A~F와 4회차 (`c83df4b` = 코드 `14b34af`)
사용자 최종 검증 지시의 Case A~F를 먼저 테스트로 고정했다(`tests/test_g6_evidence.py`, RED 대상 `git archive 14b34af plugins/vmodel`, 10/10 목표 assertion 실패, 커밋 `cdd95dd`). D43 규칙에서 Case B·C(목만 쓴 테스트가 다른 테스트의 provider 실행으로 통과)와 Case D(연결 없는 동시 실행이 경고 없이 통과)가 재현됐다. 이를 D44(테스트 수준 증거만 셈)로 고쳤다(`57492d3`).
같은 시점에 별도 컨텍스트의 4회차 검토자가 `c83df4b`를 읽기 전용으로 검토했다(HIGH 4, MEDIUM 6, LOW 4). 지적 12개 시나리오를 검토자의 재현 파일을 참고해 다시 쓰고 직접 재현했다(`tests/test_g6_review4.py`, RED 대상 `14b34af`, 12/12, `e7c82c5`). 수정 `464d01b`, 보수 규칙 추가 `8130ee5`.

| 지적 | 처리 |
|---|---|
| H1 목 테스트가 다른 IF 테스트의 실행으로 인정(Case B·C) | D44: 테스트 수준 증거만 셈 |
| H2 import 시점 도우미 함수가 "provider가 돎"으로 셈 | D44: provider는 IF 심볼만, import 시점은 테스트 증거 아님 |
| H3 장수 자식 프로세스가 태어난 테스트에 귀속 | 계측 줄에 시각, 자식 머리에 `spawned_in`, pytest 프로세스의 테스트 경계로 다시 읽음(끝난 뒤 detached) |
| H4 provider·consumer 연결 미검증(무관한 consumer 함수, 경로 B 자식의 무관한 provider 함수) | 호출 스택 연결 기록(`e` 줄) + IF 심볼 단위 판정 |
| M1 함수 범위 fixture가 띄운 서버 프로세스가 setup 단계로 기록돼 BLOCKED | 시간 창으로 호출 단계 중 줄은 call |
| M2 suite-level 증거를 검증으로 표시 | D44 표시(Test-level / Suite-level / Insufficient) |
| M3 경로의 `[`로 거짓 FAILED(R12 수정의 회귀) | 파일 부분 뒤에서만 매개변수 자름 |
| M4 읽을 수 없는 최상위 디렉터리로 내부 오류(R6 수정의 회귀) | OSError 무시 |
| M5 남은 자식이 서명 뒤 trace를 바꿔 audit 실패 | `trace-live/` → 실행 직후 `trace/` 스냅샷으로 판정·서명 |
| M6 `mocker.patch`·내장 `setattr`·대입 목을 patch로 못 봄 | 셋 다 provider patch 경고 |
| L1 `pytest.ini` 등의 pythonpath 무시 | 읽음 |
| L2 if 분기의 단순 값이 이전 import를 지움 | 묶지 않은 분기는 이전 바인딩 유지 |
| L3 setprofile 경로에서 `sys.setprofile(None)`·쓰기 오류 시 줄이 표지 없이 사라짐 | 고치지 않음(문서화). Python 3.12+는 sys.monitoring이라 `setprofile(None)` 영향 없음 |
| L4 손자 프로세스가 파이프를 잡으면 실행이 시간 초과로 보고(0.1.x부터, G5 포함) | 고치지 않음(문서화) |

검토자가 맞다고 확인한 것: G1~G5 manifest가 0.1.5와 같음, G6은 자기 실행만 씀, trace 판독의 비정규·심볼릭·대형 파일 처리, 계측 없음·잘림 → BLOCKED, 경로 B 선언의 리뷰·파일 해시 검사, 다른 프로세스·호출 단계 조건, 스레드 detached, N/A 조건.

### 7.5 5회차 (`464d01b`)
4회차 12건 중 닫힘 10, 부분 1(H3), 판단 변경 1(S10: 처리기가 `summarize`를 부르면 IF-002 심볼 `main`이 아니므로 BLOCKED가 맞음, 검토자도 동의). 새 지적 HIGH 3, MEDIUM 4, 내부 오류 0. 검토자 재현 파일을 바탕으로 `tests/test_g6_review5.py`로 직접 재현(RED 대상 `git archive 464d01b plugins/vmodel`, 10/10, `4d4060c`) 후 수정 `e8a5a7e`.

| 지적 | 처리 |
|---|---|
| N7 HIGH: conftest autouse fixture가 setup에서 consumer→provider를 부르면 몸체가 목인 테스트가 Test-level(검토 3회차 R1과 같은 모양) | 연결·provider 실행 기록에 앵커(호출 스택의 가장 바깥 테스트 파일·conftest 함수, 스레드·풀 작업은 시작·제출 스택에서 상속). 테스트 함수 자신이나 그 테스트가 요청한 fixture·setUp일 때만 인정(정적 분석이 요청 fixture 함수 이름을 제공), 아니면 Suite-level |
| N1/N1b HIGH: 테스트 call에서 시작한 자식 프로세스가 teardown·감시 안 되는 다른 테스트 동안 한 일까지 call로 귀속(H3 부분) | Validator 소유 pytest 플러그인(`tracer/vmodel_trace_plugin.py`, `PYTEST_PLUGINS`)이 모든 테스트의 setup/call/teardown 시작과 끝을 기록. 자식 줄은 그 테스트의 call 구간 안일 때만 call. 경계가 없으면 귀속 안 함 |
| N3 HIGH: 클래스 시그니처 IF에서 `__init__` 실행이 provider 실행으로 셈 | 생성자·객체 프로토콜 메서드 제외 |
| N2 MEDIUM(회귀): `def parse(self, …)` 시그니처가 G4는 통과, G6은 `Parser.parse`와 안 맞아 거짓 BLOCKED | 메서드 이름 시그니처는 provider 파일의 그 이름 메서드와 맞춤 |
| N4/N5 MEDIUM(회귀): `asyncio.gather` 작업, consumer가 넘긴 provider 제너레이터는 연결이 스택에 안 보여 거짓 BLOCKED | 고치지 않음. 보수적 BLOCKED로 문서화(특성 테스트 `R5AsyncGenChar`), implementer 지침에 직접 호출·await 사용 안내 |
| N8 MEDIUM: 거친 시계(Windows CPython 3.12 이하)에서 같은 시각값이 단계를 정함 | 경계와 같은 시각은 credit 없음(call 시작과 같으면 setup, 끝과 같으면 detached). 사용자 Windows는 Python 3.13(정밀 시계) |
| 회귀에서 내가 발견: 계측 기록이 없는 테스트에서 `prov_runs` KeyError 내부 오류(`e8a5a7e` 이전 작업 트리) | 수정 후 커밋 |

검토자가 맞다고 확인한 것: trace 판독 퍼즈 300회 무크래시, spawned 프로세스의 경계 줄 무시, 스냅샷 단일 판독·해시, `parse`/`parse_all` 구분, 스레드 풀 패치의 동작 보존(결과·예외·run_in_executor, 20만 회 제출 1.7배 부하), `_test_windows` 8000 테스트 1.4초, forkserver·재사용 fork 풀은 이제 보수적(detached).

### 7.6 6회차 (`e8a5a7e`)
5회차 새 지적 중 N1·N1b·N2·N3(그 시나리오)·N7 닫힘, N4/N5는 문서화대로 BLOCKED, N8 보수적. 새 지적 HIGH 1, MEDIUM 4(그중 1은 설계 판단), 내부 오류 0. 검토자 재현 파일을 바탕으로 `tests/test_g6_review6.py`로 직접 재현(RED 대상 `e8a5a7e`, 5/5, `2b2b123`). 검토자의 M3(conftest `pytest_pyfunc_call`)는 G4.TEST_INTEGRITY가 이미 막아 G6에 이르지 않으므로 지적에서 뺐다(직접 실행해 G4 FAILED 확인).

| 지적 | 처리 |
|---|---|
| M1 HIGH: 생성자가 부르는 일반 메서드(`__init__` → `_compile`)가 인터페이스 실행으로 셈(N3 불완전) | 연결·provider 실행 기록의 함수를 "진입 함수"(consumer나 테스트가 들어간 가장 바깥 provider 함수)로. 생성자에서 불린 도우미는 생성자로 기록돼 제외 |
| M2(회귀): 테스트 파일·conftest의 데코레이터 래퍼가 가장 바깥 앵커가 되어 거짓 BLOCKED | 앵커를 스택의 테스트 파일 함수 집합으로 기록, 그중 하나가 허용 앵커면 인정 |
| M4(회귀, 검토 번호 M3/M4): `PYTEST_PLUGINS`가 테스트 안의 중첩 pytest로 새어 ImportError → 거짓 FAILED | 플러그인이 로드되면 그 환경 변수를 지움(자식에 상속 안 됨) |
| M5/M6: 거친 벽시계(Windows CPython 3.12 이하)에서 subprocess 시험이 자주 BLOCKED(시뮬레이션) | 모든 줄과 경계에 `perf_counter_ns`(시스템 단조 고해상도) 기록, 경계가 모두 갖고 있으면 그것으로 비교 |
| M7(설계 판단): 요청한 fixture가 연결을 실행하고 테스트 몸체는 provider를 목으로 대체 | 보수 쪽 선택: 테스트 함수가 provider를 patch하면(G4 정적 탐지) 요청 fixture에서만 일어난 연결은 세지 않음. 사용자 확인 사항으로 보고 |

### 7.7 7회차 (`ce59c33`)
6회차 5건 모두 닫힘(거친 시계 시뮬레이션 10/10 통과로 바뀜). HIGH 없음, MEDIUM 3(그중 2는 `ce59c33`의 회귀), LOW 2, 내부 오류 0. `tests/test_g6_review7.py`로 재현(RED 대상 `ce59c33`).

| 지적 | 처리 |
|---|---|
| R1(회귀): provider 모듈 안 데코레이터의 래퍼가 진입 함수가 되어 거짓 BLOCKED | 진입 함수 선택에서 `<locals>` 클로저(래퍼)는 건너뜀 |
| R2(기존): fixture 서버가 setup에서 준비 요청을 한 번 보내면 call 단계 실행이 중복 제거돼 BLOCKED | 고치지 않음(보수적 BLOCKED, 특성 테스트). 자식 프로세스는 함수마다 첫 실행만 기록하기 때문. 개선안: 자식이 pytest 프로세스의 현재 단계를 읽어 키에 포함 |
| R3(회귀): xdist 작업자가 플러그인을 못 받아 경계가 없음 → BLOCKED | `pytest_xdist_setupnodes`에서 설정을 되살려 작업자가 받게 하고, 작업자는 로드 시 다시 지움 |
| R4(판단): 클래스 provider의 다른 메서드를 목으로 바꾸고 팩토리 classmethod로 진입하면 test-level | 보수 쪽(Case B): 테스트 함수가 provider를 patch하면(G4 정적 탐지) test-level로 세지 않음. 6회차 M7 규칙을 일반화. 사용자 확인 사항 |
| R5: 앵커 수집 상한 16 | 64로 |

### 7.8 8회차 (`953d502`, 변경분만)
R1(클로저 래퍼)·R3·R4 닫힘, R2 문서화대로 BLOCKED. 새 거짓 PASS·크래시 없음. `tests/test_g6_review8.py`로 재현(RED 대상 `953d502`).

| 지적 | 처리 |
|---|---|
| P1 MEDIUM(`953d502` 회귀): provider 모듈의 무해한 속성(설정 상수)을 patch해도 R4 규칙으로 test-level에서 빠짐 | patch 대상이 인터페이스 심볼이나 그 메서드일 때만 provider 목으로 봄(G4 경고는 그대로) |
| P2 LOW(기존): 호출 가능한 클래스 데코레이터(`_Checked.__call__`)가 진입 함수를 가림 → 보수적 BLOCKED, 메시지가 "never ran"으로 부정확 | 고치지 않음: "심볼 프레임 우선"은 6회차 M1(생성자가 부르는 메서드)을 다시 연다. 특성 테스트로 고정, 한계로 기록 |

## 8. 실전 E2E 계획 (D8, 실행은 별도 승인)
- 예산: sonnet 최대 2회, 회당 `--max-budget-usd 2`, 합계 $4 상한. `--permission-mode auto`, `--setting-sources project,local`, `--plugin-dir dist/vmodel-0.2.0`, `--dangerously-skip-permissions` 금지. 실행 전 모델 호출 없는 준비(setup)와 기대 판정 확인을 먼저 한다.
- 시나리오 A (Provider/Consumer, G6 실패 → 결함 → 수정 → 재검증): 기존 코드가 있는 프로젝트(점수 파서 모듈과 그 통합 테스트가 이미 `tests/integration/`에 있어 `init`이 실제 경로를 등록 — D3 규칙을 그대로 지킴)에 "파서 결과를 소비하는 요약 보고 CLI를 추가해줘"를 요청한다. 파서의 오류 계약(형식 오류 줄 번호)과 소비 측 처리 사이의 불일치를 하나 미리 심어(D26 블라인드 시딩, 세션 프롬프트에 알리지 않음) 단위 테스트는 통과하고 IF 통합 테스트에서 드러나게 한다. 기대: G1~G5 PASSED → G6 FAILED(TEST_MAPPING·RESULTS) → DEFECT(gate G6, IF·TEST 연결) → 수정 → G4 재리뷰 → G5 → G6 PASSED, 결함 CLOSED. 관찰: placeholder·import-only 테스트를 쓰는지, 통합 테스트가 경로 A인지, verifier가 `interfaces` 항목을 쓰는지, guard 우회 0.
- 시나리오 B (통합 대상 없음): `samples/textstats`(단일 컴포넌트)에 단일 함수 기능을 요청한다. 기대: IF 0, integration 명세 0, verifier가 G2·G3 리뷰에 `integration_applicability`를 기록 → G6 N/A, WI PARTIALLY_VERIFIED, 최종 보고가 N/A를 "통합 테스트 통과"로 쓰지 않음, G1~G5 기록·증거 보존.
- 판정 기준(세션 뒤, 모델 호출 없음): 서명 원장과 증거로 Validator가 직접 확인(`vmodel status/audit/verify-evidence`), 트랜스크립트에서 guard 결정과 보고 문구 대조. 실패하면 결과를 그대로 기록하고 추가 실행은 다시 승인받는다.
- 준비 작업(승인 후): 시나리오 A 표본 프로젝트와 시딩 계획 봉인, `scripts/e2e/e2e_run.py`에 표본 선택 옵션.
