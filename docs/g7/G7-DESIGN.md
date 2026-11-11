# G7 System Verification 설계 (v0.3.0)

작성 2026-11-11. 기준: 태그 `v0.2.0`(= `main` `c4b508a`, core `sha256:2a95adb3…`, 릴리스 사본 `dist/vmodel-0.2.0` 46개 파일 기록과 일치). 브랜치 `g7-dev`.
사용자 지시: "VModel DevKit v0.3.0 — G7 System Verification 개발"(2026-11-11). 목표는 복잡한 프레임워크가 아니라 **요구사항이 충족됐는지를 독립적으로 확인하는 최소한의 신뢰성 있는 검증 체계**다. 이 문서가 G7의 요구사항·수용 기준·영향 분석·설계·테스트 명세의 정본이다.

## 0. 원칙 (G6 경험에서 가져온 것)
- G7은 **블랙박스**다. 공개 인터페이스(CLI, HTTP API, 라이브러리 공개 API, 배치)로 시스템 테스트를 돌리고 결과만 본다. G6의 실행 계측(`tracer/`)을 G7에 넣지 않는다. 내부 호출 증거가 없다는 이유로 BLOCKED를 내지 않는다.
- 판정에는 Validator가 직접 실행해 얻은 사실(종료 코드, JUnit 케이스, TEST ID, 서명된 증거)과 산출물의 ID 관계(REQ → AC → TEST)만 쓴다. "시스템 테스트가 정말 외부 인터페이스를 쓰는가"는 정적 분석으로 판정하지 않고 G3(명세)·G4(코드) 리뷰의 몫으로 둔다(D12와 같은 구조).
- 기존 Runner 함수(`run_command`, `scrubbed_env`, `write_evidence`, `parse_junit`)와 G5/G6 규칙(실행 → 결과 → 범위 → 매핑 → 약화 → 입력 불변)을 재사용한다. G5·G6 실행부 코드는 고치지 않는다.
- G1~G6 판정과 manifest는 그대로 둔다. 바뀌는 곳은 `system_test`를 설정한 프로젝트의 G5·G6 범위 규칙뿐이다(§3.2).

## 1. 요구사항 (REQ-G7-xx)과 수용 기준

### 1.1 설정과 실행
- **REQ-G7-01** config에 선택 키 `system_test`(`argv` 문자열 1개 이상·`{junit}` 포함, `timeout_s` 양의 정수, `plugin_autoload` 선택)를 둔다. 키가 없는 0.2.0 config는 그대로 유효하다. G7은 평가마다 하위 스키마를 검증한다.
  - AC: 0.2.0 config가 스키마를 통과한다. 하위 스키마 위반·`{junit}` 없음 → G7 BLOCKED `misconfigured`, 아무것도 실행하지 않는다.
- **REQ-G7-02** `system_test`가 없으면 G7은 BLOCKED(`misconfigured`)이고 `unit_test`·`integration_test`로 대체하지 않는다. next_action은 사용자 조치(`vmodel configure-tests --system <path>`, TTY)를 안내한다. (T03)
- **REQ-G7-03** Validator가 `system_test` argv를 셸 없이 직접 실행한다. 환경은 G5와 같은 `scrubbed_env`(에이전트의 `PYTHON*`·`PYTEST_*`·`VMODEL_*` 제거, 바이트코드 끔, 플러그인 자동 로드 끔)이고 계측을 넣지 않는다. 새 실행 폴더 `.vmodel/evidence/<WI>/G7/<시각>-system-<rand>/`에 stdout/stderr 원본 바이트, junit.xml, 서명된 record.json(명령, 실행 파일 경로·버전·sha256, 런타임, 시작·종료 시각, 종료 코드, stdout/stderr 해시, Git HEAD·dirty, manifest 해시, Core 해시, 환경 정리 내역, 설치 패키지 목록, 검증 대상 파일 해시, `command_source: system_test`, `config_sha256`, `system_test_sha256`, JUnit 요약)을 남긴다. G7은 G5·G6의 증거를 쓰지 않는다.
- **REQ-G7-04** 실행 판정(G5/G6과 같은 의미): 시작 실패 → BLOCKED `tool_unavailable`(중립). 시간 초과·비 0 종료·junit 없음·파싱 불가 → FAILED(G7.EXECUTION). 케이스 0개 → FAILED(G7.RESULTS). 실패·오류 케이스 → FAILED. **종료 코드 0만으로는 PASS가 아니다**: RESULTS·TEST_MAPPING·AC_COVERAGE가 모두 통과해야 한다. (T06, T07)

### 1.2 범위 분리
- **REQ-G7-05** G7.SCOPE: system 실행이 unit 수준(G5 몫) 또는 integration 수준(G6 몫) TEST ID를 실행하면 FAILED다. 수준은 프로젝트 모든 WI의 `tests.json`을 합쳐 정한다. 어느 WI에도 없는 ID·ID 없는 케이스는 `unmapped_cases`(기록)로만 남긴다. (T04)
- **REQ-G7-06** `system_test`가 설정된 프로젝트에서는 system 수준 TEST는 G7 명령에서만 실행돼야 한다: G5.SCOPE와 G6.SCOPE는 system ID 실행을 FAILED로 본다(지금은 경고). G5.SCOPE는 `integration_test`나 `system_test` 중 하나라도 설정되면 기록된다. G5.NO_WEAKENING의 "이전에 실행된 ID 유지"는 지금 system 수준인 ID를 뺀다(REQ-G6-07과 같은 규칙).
- **REQ-G7-07** `system_test`가 없는 프로젝트에서 G1~G6 판정·기록 키는 0.2.0과 같다. 다른 점은 G5/G6.SCOPE가 system ID를 경고할 때의 문구(0.2.0 "(G7, not implemented)" → G7이 별도 `system_test` 명령으로 실행함)뿐이다. status·report는 unit 명령이 system 테스트를 실행했다는 사실을 경고로 보인다(표시 전용).

### 1.3 요구사항 추적성
- **REQ-G7-08** G7.TEST_MAPPING: 이 WI의 모든 system 수준 TEST 명세에 이름에 그 ID 하나만 가진 `passed` 케이스가 있어야 한다. 실패·오류·skip → FAILED, 실행 안 됨 → `TEST-xxx: not executed`(결함 추적의 UNKNOWN 분류와 같은 문구), 이름에 ID 둘 이상 → FAILED. system 명세가 0개면 FAILED("G7 needs at least one system test spec").
- **REQ-G7-09** G7.AC_COVERAGE: 활성(`status: active`) functional REQ의 모든 AC마다, `acceptance_criteria`에 그 AC를 둔 system 명세 중 **이번 실행에서 passed**인 것이 하나 이상 있어야 한다(G3.INTEGRATION_SYSTEM_TESTS와 같은 범위를 실행 결과로 다시 확인). 없으면 FAILED, 항목은 `AC-001-2 (REQ-001): TEST-102 failed` / `... no system test spec` / `... TEST-102 not executed`. 활성 functional REQ에 AC가 없으면 FAILED. 활성 non-functional·constraint REQ의 AC에 system 명세가 없으면 **경고**(G3가 요구하지 않음, 실행으로 검증되지 않았다는 사실을 숨기지 않는다). 명세가 있으면 TEST_MAPPING으로 실행·통과가 요구된다. (T05)
- **REQ-G7-10** 기록: `requirements_coverage`(REQ → type·priority·AC → {system TEST → 이번 실행 결과, verified}, 범주별(normal·abnormal·boundary) TEST), `system_specs`, `executed_tests`, `executed_levels`, `unmapped_cases`, `test_files`, `junit`, `failed_cases`, `basis_records`(현재 G5·G6 PASS 기록 ID). 이 기록과 원장 기록 ID로 REQ → AC → TEST → 실행 결과 → 증거 해시를 따라갈 수 있다. (T08)

### 1.4 판정 기본
- **REQ-G7-11** G7.PREREQ: G6이 현재 manifest로 PASSED(N/A 포함). 공통 전제 조건(무결성, 직전 FAILED의 DEFECT, 3회 실패 해제)은 기존과 같다(기록 없는 BLOCKED).
- **REQ-G7-12** G7.NO_WEAKENING: 기준은 마지막 PASSED G7, 없으면 실행된 테스트가 있는 첫 G7 기록. 기준에서 실행된 system 명세 ID가 지금 실행되지 않으면 CR(rejected 아님)·DEFECT의 `removed_ids`로만 정당화된다. 테스트 파일 변경 정당화는 같은 manifest의 G5.NO_WEAKENING이 이미 요구한다(기대값을 바꾸려면 `test_changes`의 근거·관련 REQ·영향 + G4 리뷰).
- **REQ-G7-13** G7.INPUTS_UNCHANGED: 실행 전후 manifest 동일.
- **REQ-G7-14** G7에는 ai_review 체크가 없다. gates.json G7 reviewer는 "none (mechanical)". 사용자 수용 승인·배포 승인은 G7에 포함되지 않는다(자동화된 System Verification과 구분, 실제 배포·외부 시스템 변경·운영 데이터 수정은 기존 안전 정책대로 별도 승인).
- **REQ-G7-15** G7 manifest = G5와 같은 코드 manifest(산출물 5종 + 프로젝트 전체 파일 + config + defects + CR). 리뷰 파일은 넣지 않는다(G6이 STALE이 되면 "상위 Gate가 PASSED 아님" 규칙으로 G7도 STALE). G1~G6 manifest는 바뀌지 않는다.

### 1.5 결함·재작업
- **REQ-G7-16** G7 FAILED는 기존 재작업 전제 조건(실패 기록을 `found_in_records`에 둔 DEFECT), 3회 동일 실패 BLOCKED, 중립 차단(`misconfigured`·`tool_unavailable`)을 따른다. defects `gate`에 G7, `root_cause_phase`에 P7(시스템 테스트 실행 환경: 테스트 데이터·외부 의존 준비, 설정 변경이 필요하면 사용자 조치)을 더한다. `TEST_EXECUTING_GATES`에 G7을 넣어 결함 추적이 실패 TEST·UNKNOWN·무효 인용·미연결을 G5/G6과 같은 분류로 낸다. 결함 종료 Gate가 G7이면 표시 상태 규칙(D37)을 그대로 쓴다: G7 PASS(인용 실패 이후) + G7 현재 PASSED일 때만 CLOSED, STALE·BLOCKED는 REVERIFY_REQUIRED, 재검증 실패는 VERIFICATION_FAILED. BLOCKED나 상위 Gate PASS만으로는 닫히지 않는다. G7에는 N/A가 없다. (T11, T12)

### 1.6 Work Item 완료
- **REQ-G7-17** STANDARD WI는 G1~G7이 모두 현재 해시로 PASSED일 때만 COMPLETED다(G6 N/A는 PASSED로 기록되므로 허용). G7 미평가·STALE·FAILED·BLOCKED·REVIEW_REQUIRED면 COMPLETED가 아니다. G1~G6이 PASSED이고 G7 기록이 없으면 WI는 IN_PROGRESS, G7은 "not evaluated yet"(G6 결정 4와 같은 방식). STANDARD에서는 PARTIALLY_VERIFIED가 더 이상 나오지 않는다(상태 값은 미구현 프로파일용으로 남김). (T13~T16)
- **REQ-G7-18** 표시: status·`vmodel gate`·report·trace·next_action·SessionStart 문구가 G7 결과(검증된 AC 수/전체, 통과한 system 테스트 수, 시스템 테스트로 검증되지 않은 비기능 AC)를 보인다. `vmodel verify`는 G1~G7을 돈다. MVP 문구는 "G1~G7 구현, COMPLETED는 자동 검증이지 사용자 수용·배포 승인이 아님, LITE/STRICT 미구현"으로 바꾼다.
- **REQ-G7-19** trace: REQ 행의 system TEST 결과는 마지막 G7 실행에서 가져오고(unit은 G5, integration은 G6), REQ → AC → system TEST → 결과 → 기록 ID 행을 더한다.

### 1.7 설정 도구·호환·변경
- **REQ-G7-20** `init`: `--system-tests PATH`를 주거나 `tests/system/`에 테스트 함수가 있을 때만 `system_test`를 등록하고 unit argv에 `--ignore=<경로>`를 더한다(G6 D3과 같은 경로 검사: 프로젝트 안, tests 경로 아래, unit 전체 범위 아님, 테스트 함수 있음). integration 경로와 겹치면(같거나 한쪽이 다른 쪽 안) 거부한다.
- **REQ-G7-21** `configure-tests`(사용자 전용, TTY): `--integration PATH`와 `--system PATH` 중 하나 이상. 같은 경로 검사와 겹침 검사, unit argv에 `--ignore`, 기존 `integration_test` argv가 system 경로(또는 그 상위)를 실행 대상으로 이름에 두면 거부. 서명 원장 `config` 기록을 먼저 쓰고 config를 쓴다.
- **REQ-G7-22** 호환: G1~G6 manifest 계산은 0.2.0과 같다. `system_test` 없는 프로젝트의 G1~G6 원장 투영(상태, 체크 ID·상태값, 실패 서명, executed_tests)은 같은 이력에서 0.2.0과 같다. 원장 형식(서명·체인·head·앵커)은 그대로이고 기존 기록·증거는 다시 쓰지 않는다. 0.2.0이 서명한 원장·증거는 새 코어의 `audit`·`verify-evidence`를 통과하고, 기록의 버전·Core 해시는 0.2.0 값으로 남는다. (T17)
- **REQ-G7-23** 업그레이드는 기존처럼 새 릴리스의 `lock --accept-current`(TTY) 한 번이다. Core 해시가 바뀌므로 기존 PASS는 STALE(기존 규칙 유지, G7 때문이 아님). 그 뒤 G7은 평가 전이고 WI는 IN_PROGRESS다. 완료하려면 시스템 테스트 작성(없으면 G7 FAILED가 알려 준다) → 사용자 `configure-tests --system` → G4 재리뷰(config 변경) → G5 → G6 → G7. (T20)
- **REQ-G7-24** 최신성: G7 PASS는 manifest 파일 변경, Core 변경, G6이 PASSED가 아님 중 하나면 STALE이다. 요구사항 변경(requirements.json)은 G1부터 G7까지 STALE로 만들고, `vmodel impact`가 바뀐 REQ·AC와 영향받는 system TEST, STALE Gate(G7 포함)를 보인다. (T18)

## 2. 영향 분석

| 영역 | 파일 | 변경 | 기존 판정 영향 |
|---|---|---|---|
| Gate 정의 | `data/gates.json` | G7 `implemented: true`, 체크 9개, reviewer "none (mechanical)", required_artifacts. G5.SCOPE·NO_WEAKENING, G6.SCOPE 설명 갱신. STANDARD notes | Core 해시 변경(→ 기존 PASS STALE, 기존 규칙) |
| 스키마 | `config`, `defects` | config `system_test`(선택). defects `gate` G7, `root_cause_phase` P7 | 없음(선택 키·enum 확장) |
| 판정 | `gates.py` | `eval_g7`, `system_config_problems`, `_scope_check` 수준 집합화, G5·G6의 SCOPE 호출과 G5.NO_WEAKENING skip, `TEST_EXECUTING_GATES`, `_g7_state` | `system_test` 설정 시 G5·G6.SCOPE·G5.NO_WEAKENING만(REQ-G7-06) |
| 표시 | `status.py`, `cli.py` | wi 상태 문구, gate_summary, next_action, MVP_NOTE, trace(AC 행), impact, report(G7 절·수용 기준 표·한계), `verify` 도움말, `init`·`lock` 안내 | 표시만 |
| 설정 도구 | `setup_project.py`, `cli.py` | `init --system-tests`, `configure-tests --system` | 새 config만 |
| 지침 | skills, agents, `data/VMODEL.md`, README | P7 단계, 시스템 테스트 작성 규칙(외부 인터페이스, AC별 정상·경계·오류, `tests/system/`), verifier G3·G4 체크리스트, 완료 보고 | 판정 무관 |
| 하네스 | `tests/` | 새 픽스처 `gradecalc`, `pipeline` 시스템 테스트 오버레이, 새 모듈, §5.4 목록의 기대값 변경 | — |

바꾸지 않는 것: guard 훅, 원장, manifest 계산 함수, Core 무결성, G6 계측, G1~G4 판정 코드, G5·G6 실행부.

## 3. 아키텍처와 상세 설계

### 3.1 G7 체크 (모두 기계 판정, `eval_g7`)
| 체크 | kind | 판정 |
|---|---|---|
| G7.PREREQ | mechanical | G6 PASSED(전제 조건이 기록 전에 확인) |
| G7.CONFIG | mechanical | `system_config_problems(cfg)`가 비면 pass, 아니면 blocked `misconfigured`(이후 체크 없음) |
| G7.EXECUTION | execution | G5와 같은 규칙(REQ-G7-04) |
| G7.RESULTS | execution | 케이스 > 0, 실패·오류 0 |
| G7.SCOPE | mechanical | unit·integration ID 실행 → fail |
| G7.TEST_MAPPING | mechanical | REQ-G7-08 |
| G7.AC_COVERAGE | mechanical | REQ-G7-09 |
| G7.NO_WEAKENING | mechanical | REQ-G7-12 |
| G7.INPUTS_UNCHANGED | mechanical | REQ-G7-13 |

상태는 기존 `derive_status`(blocked > fail > pending > warn·pass). FAILED면 `failure_signature`와 3회 규칙. 시작 실패만 BLOCKED이고 그 밖의 실행 문제는 FAILED다(G5·G6과 같은 의미). 실행 체크 구현은 G5·G6의 같은 규칙을 G7 전용 도우미(`_suite_checks`)로 옮겨 쓰고, G5·G6 코드는 건드리지 않는다.

### 3.2 범위 규칙 `_scope_check(cid, executed, levels, wrong: dict[level, owner], command)`
- `wrong`에 든 수준의 ID가 실행되면 fail(항목: `TEST-xxx: <level> test executed by the <command> command (it belongs to <owner>)`).
- system이 `wrong`에 없고 system ID가 실행되면 warn(문구: G7이 별도 `system_test` 명령으로 실행함).
- G5: `integration_test` 설정 → `{integration: G6}`, `system_test` 설정 → `{system: G7}`. 둘 다 없으면 G5.SCOPE 없음(0.2.0과 같음).
- G6: `{unit: G5}` + `system_test` 설정 시 `{system: G7}`.
- G7: `{unit: G5, integration: G6}`.
- 단일 수준일 때의 fail/pass 상세 문구는 0.2.0과 같다.

### 3.3 G7 기록 추가 키
`executed_tests`, `executed_levels`, `unmapped_cases`(50개까지), `system_specs`, `test_files`, `requirements_coverage`, `basis_records`, `junit`, `failed_cases`. N/A가 없으므로 `applicability` 키를 쓰지 않는다.

### 3.4 상태·표시
- `gate_state`: G7이면 `_g7_state`가 기록 없음(`not_evaluated`), PASSED면 `acceptance`(AC 수, 검증된 AC 수, 통과한 system 테스트 수, 시스템 테스트 없는 비기능 AC)를 더한다.
- `wi_status`는 바꾸지 않는다. 입력(구현된 Gate)에 G7이 들어가 COMPLETED에 도달할 수 있다.
- next_action: G7 평가 전 → `system_test` 문제가 있으면 사용자 조치, 아니면 `vmodel gate WI G7`. BLOCKED `misconfigured` → 사용자 조치. 모두 PASSED → "all gates passed: G1-G7 verified (COMPLETED)" (G6 N/A면 그 사실을 함께).
- `scope_warnings`: `system_test`가 없고 마지막 G5가 system ID를 실행했으면 경고.
- report: G7 절(검증 AC 수, system 테스트 수, 비기능 AC 경고), "## Acceptance (system verification)" 표(REQ, AC, system TEST(결과), 기록 ID), 한계 절 갱신.
- trace: 위 REQ-G7-19.

### 3.5 결함 추적
- `TEST_EXECUTING_GATES = ("G5", "G6", "G7")`. `citation_view`는 이미 `f"{gate}.TEST_MAPPING"`을 쓰므로 G7 "not executed"가 UNKNOWN으로 분류된다.
- `defect_trace`의 종료 Gate는 인용된 실패 중 가장 하위 Gate(GATE_ORDER)라서 G7 실패를 인용한 결함은 G7 PASS로만 `verified_by`를 얻는다. G7에는 N/A 기록이 없다.

### 3.6 설정 도구
- `setup_project.test_path_problems(root, given, globs, label)`: 지금의 `integration_path_problems` 본문을 label만 바꿔 공유(`integration_path_problems`는 label "integration"으로 이 함수를 부르는 얇은 래퍼로 남겨 기존 문구 유지). 겹침 검사 `_overlaps(a, b)`.
- `plan_configure_tests(project, integration=None, system=None, timeout_s)`: 둘 중 하나 이상. 원장 기록 `change`는 `integration_test`·`system_test`·`integration_test+system_test`.

## 4. 결정 (DECISIONS D49로 기록)
1. 시스템 테스트 함수의 존재는 G4가 아니라 G7이 실행 결과로 확인한다(G7.TEST_MAPPING "not executed"). 기존 WI는 모두 G3 때문에 system 명세를 갖고 있으므로 G4.TEST_CODE를 system까지 넓히면 모든 기존 WI의 G4 판정이 바뀐다(G6 때 REQ-G6-09와 다른 선택, 근거: "G1~G6 PASS 결과가 부당하게 변경되지 않도록").
2. 블랙박스 여부(외부 인터페이스 사용)는 기계 판정하지 않는다. 정적 분석·계측으로 판정하면 G6처럼 우회와 오판이 반복된다. 기계로는 실행 사실(SCOPE·TEST_MAPPING·AC_COVERAGE)만 판정하고, 외부 인터페이스 사용·정상/경계/오류 시나리오 적합성·기대값 정당성은 G3·G4 verifier 리뷰가 맡는다(체크리스트 추가).
3. G7에는 N/A가 없다. system 명세가 0개면 FAILED다(G1·G3 규칙상 활성 functional REQ가 없는 WI에서만 생김).
4. AC 커버리지 범위는 G3와 같은 "활성 functional REQ의 모든 AC". 비기능 AC는 system 명세가 있으면 실행·통과를 요구하고, 없으면 경고만 한다(G3가 요구하지 않는데 G7에서 차단하면 G3를 통과한 WI가 G7에서 설계 단계 결함으로 막힌다).
5. `system_test`를 설정한 프로젝트에서 G5·G6이 system 테스트를 실행하면 SCOPE FAILED(D41 결정 1과 같은 분리). 설정하지 않은 프로젝트는 0.2.0 판정 유지.
6. G7 manifest는 G5 코드 manifest와 같다(리뷰 파일 불필요, 상위 STALE 전파로 충분).
7. `root_cause_phase` P7 추가(G6의 P6과 대칭).
8. WI 완료: G1~G7 PASSED → COMPLETED. G1~G6 PASSED·G7 미평가 → IN_PROGRESS(D41 결정 4와 같은 방식, 업그레이드 때 Core STALE 규칙 유지).
9. 사용자 수용·배포 승인은 G7과 분리한다. G7 reviewer는 "none (mechanical)".
10. 실행 문제의 FAILED/BLOCKED 구분은 G5·G6과 같다(시작 실패·설정 부재만 BLOCKED).
11. 버전 0.3.0(Gate 의미 추가).

## 5. 테스트 명세

규칙은 0.2.0과 같다. 클래스 접미사 `Red`(불변 0.2.0 릴리스에서 `RED-TARGET` 표지가 있는 assertion으로 실패), `Char`·`Invariant`(둘 다 통과), `Accept`(새 코어에서만). RED 대상 `dist/vmodel-0.2.0`. 0.2.0은 G7 요청에 기록 없는 BLOCKED("extension gate ... not implemented")를 돌려준다.

### 5.1 새 픽스처
- `tests/fixtures/gradecalc`: 컴포넌트 1개(ARCH-001), IF 0, 외부 끝점 2개(CLI 사용자, HTTP 클라이언트). 소스 `grading.grade`, `cli.main`(`python -m gradecalc.cli <점수>`: 등급 출력·잘못된 입력은 종료 코드 2와 한국어 오류 메시지), `server.handle`·`server.main`(`python -m gradecalc.server --port 0`: 포트를 한 줄 출력하고 `GET /grade?score=N` 처리). REQ-001(CLI, AC 3개: 정상·경계·오류), REQ-002(HTTP API, AC 2개: 정상·오류), REQ-003(비기능: 오류 메시지는 한국어, AC 1개, system 테스트 있음). unit 명세 9개, system 명세 6개(`tests/system/`, CLI는 하위 프로세스, API는 하위 프로세스 서버 + urllib). G6은 N/A(G2·G3 리뷰 확인).
- `tests/fixtures/pipeline_system`: `pipeline` 픽스처(G6 required)에 더하는 시스템 테스트 오버레이(`tests/system/test_system.py`, TEST-020·021, CLI 하위 프로세스). 기존 `pipeline` 픽스처는 바꾸지 않는다.

### 5.2 사용자 시나리오 T01~T20 대응

| T | 내용 | 모듈::클래스 (종류) | 기대 결과 |
|---|---|---|---|
| T01 | 정상 System Test PASS | `test_g7_gate::GateRed` | G7 PASSED, 증거 kind `system_test`, record·증거에 명령·종료 코드 0·해시·TEST ID·REQ/AC 커버리지 |
| T02 | 실제 기능 오류 → FAILED | `test_g7_gate::GateRed` | CLI 경계 버그(90 → B) → G7 FAILED, RESULTS·TEST_MAPPING·AC_COVERAGE에 TEST-102·AC-001-2 |
| T03 | system_test 누락 | `test_g7_config::ConfigRed` | BLOCKED `misconfigured`, 증거 없음, unit·integration 명령 미실행, next_action 사용자 조치. 하위 스키마 오류·`{junit}` 없음도 같음 |
| T04 | Unit Test 재사용 우회 | `test_g7_scope::ScopeRed` | system_test argv = unit argv → G7 FAILED(SCOPE unit ID, TEST_MAPPING); system_test가 `tests/unit` → FAILED; unit 테스트 함수를 system ID로 개명해 system 폴더로 옮김 → G5 FAILED(unit ID not executed). unit 테스트 본문을 **복사**해 system 이름을 붙인 화이트박스 테스트는 기계로 막지 않는다(G4 리뷰, §7) |
| T05 | REQ ↔ System Test 매핑 누락 | `test_g7_trace::TraceRed` | AC-002-2 명세의 테스트 함수 이름에 ID 없음 → G7 FAILED(TEST_MAPPING not executed, AC_COVERAGE `AC-002-2 (REQ-002)`); 비기능 AC에 명세 없음 → 경고만(PASSED) |
| T06 | 실행 결과 없는 PASS | `test_g7_gate::GateRed` | 가짜 G7 증거·junit·PASS 보고서 파일 주입 → G7 미평가 유지, 평가 시 자기 실행만 사용; 종료 0이지만 junit 없음 → FAILED(EXECUTION) |
| T07 | 테스트 0개 | `test_g7_gate::GateRed` | 빈 폴더 대상(종료 5) → FAILED(RESULTS 0 tests); 종료 0 + 빈 junit → FAILED(RESULTS) |
| T08 | 정상·경계·오류 | `test_g7_gate::GateRed` | 범주별 TEST가 모두 실행·통과, `requirements_coverage`에 범주별 TEST; 오류 시나리오(종료 코드 2·HTTP 400) 기대값이 실제로 확인됨 |
| T09 | CLI System Test | `test_g7_gate::GateRed` | TEST-101~103·106이 하위 프로세스 CLI로 실행되어 passed |
| T10 | API System Test | `test_g7_gate::GateRed` | TEST-104·105가 하위 프로세스 HTTP 서버로 실행되어 passed |
| T11 | FAILED → DEFECT → 수정 → 재검증 | `test_g7_rework::ReworkRed` | DEFECT 없으면 재평가 BLOCKED, DEFECT(`gate: G7`, P4) → 수정 → G4~G7 → G7 PASSED, 결함 CLOSED `verified_by` G7 |
| T12 | 결함 CLOSED 정확성 | `test_g7_rework::ReworkRed` | G5·G6만 다시 PASS → FIX_APPLIED(종료 Gate G7); G7 재실패 → VERIFICATION_FAILED; G7 PASS 뒤 소스 변경 → REVERIFY_REQUIRED; G7 BLOCKED(misconfigured) → CLOSED 아님; not executed → UNKNOWN 분류; 3회 동일 실패 → BLOCKED; P7 스키마 통과 |
| T13 | G1~G7 PASS → COMPLETED | `test_g7_status::StatusRed` | pipeline + 시스템 오버레이(G6 required) → COMPLETED, `vmodel verify` G1~G7 종료 코드 0 |
| T14 | G7 STALE → COMPLETED 차단 | `test_g7_status::StatusRed` | 소스 변경·G6 STALE(리뷰 교체)·Core 변경 → G7 STALE, WI IN_PROGRESS |
| T15 | G6 N/A + G7 PASS → COMPLETED | `test_g7_status::StatusRed` | gradecalc → COMPLETED, 표시에 G6 N/A |
| T16 | G7 FAILED/BLOCKED → 차단 | `test_g7_status::StatusRed` | FAILED·BLOCKED·미평가에서 COMPLETED 아님, next_action 구분 |
| T17 | 기존 Ledger·Manifest 호환 | `test_g7_compat::CompatInvariant`, `CompatAccept` | 같은 이력에서 G1~G6 투영·manifest가 0.2.0과 같음; 0.2.0 원장·증거가 새 코어에서 audit·verify-evidence 통과 |
| T18 | 요구사항 변경 → 최신성 | `test_g7_trace::TraceRed` | AC 문구 변경 → G1~G7 STALE, impact가 AC·system TEST·G7 표시, 재평가 경로 |
| T19 | Windows 경로·인코딩 | 전체 하네스(한글·공백 경로) + `test_g7_gate`의 한국어 출력 시나리오, Windows cp949 회귀 | 실패 0 |
| T20 | 0.2.0 → 0.3.0 업그레이드 | `test_g7_compat::CompatAccept` | 0.2.0으로 G1~G6 → 재고정(pty) → 이전 기록 바이트 유지, G1~G6 STALE(Core), G7 미평가 → configure-tests --system → G4 재리뷰 → G5~G7 → COMPLETED |

추가: G5/G6 분리(`test_g7_scope`): `system_test` 설정 시 unit 명령이 system 테스트 실행 → G5 FAILED(SCOPE); 이전 G5에 있던 system ID가 빠져도 G5.NO_WEAKENING 통과(Red). 설정 없으면 G5 판정 0.2.0과 같고 status에 경고(Char/Invariant). 설정 도구(`test_g7_config`): `init`이 `tests/system`을 등록, 겹치는 경로 거부, `configure-tests --system`(pty) 기록 후 쓰기.

### 5.3 RED 확인
`python3 scripts/red_green.py --mode red --plugin dist/vmodel-0.2.0 --marker RED-TARGET <모듈들>`: Red 전부가 표지 있는 assertion으로 실패, Char·Invariant 통과. 로그 `test-results/v0.3.0/red-*.log`.

### 5.4 기존 테스트의 의도된 기대값 변경 (REQ-G7-17·18)
G7 구현으로 다음 기대값만 바뀐다. 바꾸는 곳마다 0.2.0 기대값을 주석으로 남긴다. 목록 밖 테스트가 실패하면 회귀로 본다.
- `test_gates.py` 33~46행: G6 평가 전 G7 상태 NOT_IMPLEMENTED → IN_PROGRESS, `mvp_note` 문구.
- `test_g6_status.py`: G1(gate_summary `not_implemented` → `not_evaluated`에 G7), G2(PARTIALLY_VERIFIED → IN_PROGRESS, next_action, mvp_note), G4(`verify`가 G7까지 돌고 `system_test`가 없으므로 G7 BLOCKED `misconfigured`).
- `test_g6_applicability.py` 45·103행, `test_g6_compat.py` 42행, `test_defect_closure.py` 220행: G7 NOT_IMPLEMENTED·PARTIALLY_VERIFIED → G7 미평가·IN_PROGRESS.
- 구현 뒤 `PARTIALLY_VERIFIED|NOT_IMPLEMENTED|G7|mvp_note|G1-G6` grep과 전체 실행으로 목록을 다시 확인한다.

## 6. 구현 절차
1. 이 설계 커밋 → 독립 검토(설계) → 반영.
2. 픽스처·테스트 코드(구현 전) → RED(0.2.0) 로그.
3. 구현: 스키마 → gates.json → `_scope_check`·G5/G6 범위 → `eval_g7` → 결함 추적 → status·report·trace·cli → setup(init·configure-tests) → 지침 → 버전 0.3.0.
4. GREEN(새 모듈) → 기존 하네스(§5.4만 의도 변경) → 독립 검토(구현) → 지적은 검토 빌드 대상 RED 후 수정.
5. 깨끗한 worktree WSL 전체 회귀, Windows cp949 전체 회귀, 릴리스 후보(`release.py`, 해시 검증, plugin validate, 이전 릴리스 불변), 0.2.0 → 0.3.0 업그레이드 재현.
하지 않는 것: main 병합, v0.3.0 태그, 원격 푸시, 유료 Claude 헤드리스 E2E, LITE/STRICT, 운영 배포.

## 7. 남은 위험 (설계 시점)
- 시스템 테스트가 외부 인터페이스 대신 내부 함수를 직접 부르는 화이트박스 테스트여도 G7은 기계적으로 막지 못한다(리뷰 판단). 기계로 막는 것은 unit·integration 테스트 재사용(SCOPE), 이름만 있는 매핑(실행·통과 요구), 실행 없는 보고(자기 실행만 사용)다.
- 테스트 코드는 러너와 같은 프로세스에서 돈다(SPEC §5.7 신뢰 경계, G4.TEST_INTEGRITY 휴리스틱).
- 비기능 AC는 system 테스트가 없으면 경고만 한다.
- 실제 Claude 세션의 G7 경로는 이번에 관찰하지 않는다(유료 E2E 별도 승인).
