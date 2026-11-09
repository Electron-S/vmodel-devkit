# G6 Integration Verification 설계 결정안 (검토용, 구현 전)

작성 2026-11-09. 상태: **사용자 결정 대기.** 구현하지 않았다(사용자 지시: "이번에는 G6 구현을 시작하지 말고 설계 결정안을 먼저 제시"). 결정되면 DECISIONS에 확정본을 남기고 PLAN M5(제안 버전 0.2.0)로 진행한다.
근거: PLAN.md "M5. G6 Integration Verification"의 "먼저 결정하고 DECISIONS에 남길 것" 1~4, `gates.json`, 0.1.5 후보 코드(`v0.1.5-dev`)를 읽고 확인한 사실(§0). 추정은 따로 표시한다.

## 0. 코드에서 확인한 현재 사실

| 항목 | 사실 | 위치 |
|---|---|---|
| G6 정의 | `implemented: false`, 체크 `G6.EXECUTION`·`G6.IF_COVERAGE`, manifest는 G4/G5와 같은 코드 manifest. `agents.reviewer`는 `vmodel:verifier`로 적혀 있어 PLAN의 "AI 리뷰 없는 기계 판정"과 어긋난다 | `data/gates.json` |
| 통합 대상 정의 | `architecture.json` `interfaces[]`(provider ARCH, consumers ARCH 또는 `EXTERNAL`), `integration_test_strategy`(approach 필수, interfaces_covered 필수, `na_reason` 선택) | architecture 스키마 |
| 상위 Gate가 이미 강제하는 것 | G2.INTERFACES: 컴포넌트 2개 이상이면 IF ≥1. G2.INTEGRATION_STRATEGY: 모든 IF가 전략에 포함. G3.INTEGRATION_SYSTEM_TESTS: IF마다 `level: integration`이고 `verifies`에 그 IF가 있는 TEST 명세. G3.NO_SILENT_REMOVAL: TEST ID 삭제는 CR/결함의 `removed_ids` 필요 | `gates.py` eval_g2·eval_g3 |
| G4 | G4.TEST_CODE는 **unit** TEST ID만 함수 존재를 요구한다(통합 ID가 코드에 있으면 고아가 아니므로 경고도 없음). G4.TEST_INTEGRITY는 수준과 무관하게 `paths.tests`의 모든 테스트 파일을 본다 | `gates.py` eval_g4 |
| G5 | `unit_test.argv`(기본 `pytest -q … --junitxml`)를 프로젝트 전체에 실행한다. 그래서 테스트 디렉터리에 있는 통합 테스트 코드도 G5에서 실행되고, 실패하면 G5.RESULTS가 실패한다. G5.TEST_MAPPING은 unit ID만 요구한다. G5.REQ_COVERAGE는 수준과 무관하게 통과한 TEST를 센다 | `gates.py` eval_g5 |
| 하네스 픽스처 | `tests/fixtures/wordfreq`는 컴포넌트 2개, IF-001 1개, TEST-010(integration)·TEST-011/012(system) 명세, `test_TEST_010_integration_punctuation`이 단위 테스트와 같은 파일에 있다 → 지금 G5가 실행한다 | fixture |
| 실제 세션 산출물 | E2E-3, drill-1/2/3의 아키텍처 4건 모두 컴포넌트 1개·IF 0개. `approach`에 "컴포넌트가 하나이고 … 통합 테스트 대상 인터페이스가 없다"가 적혀 있고 `na_reason`은 없다 | `test-results/e2e`, `test-results/drill` |
| 재작업·결함 | defects 스키마 `gate` enum이 G1~G5(G6 없음), `root_cause_phase` P1~P5. 결함 추적(D35)의 `TEST_EXECUTING_GATES = ("G5",)`(주석: "G6/G7 join when implemented") | 스키마, `gates.py` |
| WI 상태 | `wi_status`는 구현된 Gate만 본다. 프로파일의 필수 Gate가 모두 구현되지 않았으면 PASSED여도 PARTIALLY_VERIFIED. G6이 구현되면 G6이 NOT_STARTED인 WI는 IN_PROGRESS가 된다 | `status.py` |
| 추적 행렬 | `vmodel trace`는 마지막 G5 실행 결과만 보고 IF 행이 없다 | `status.py` trace_view |
| 무효화 | 코드 Gate manifest는 VCS·캐시·가상환경·`.vmodel`을 뺀 프로젝트 전체 파일 + 산출물 + config + defects·CR. 하나라도 바뀌면 STALE, 상위 Gate가 PASSED가 아니면 STALE, Core 해시가 바뀌면 STALE | `gates.py` compute_manifest·gate_state |

## 1. G6의 책임과 G5와의 경계 (네 결정의 공통 전제)

- G5 Unit Verification: 설계 단위(DESIGN)의 계약을 unit TEST 명세대로 검증한다. 판정 범위는 지금 그대로 둔다.
- G6 Integration Verification: 아키텍처의 인터페이스(IF)가 provider와 consumer를 실제로 연결했을 때 계약대로 동작하는지를 integration TEST 명세대로 검증한다. G7(시스템, AC)은 범위 밖이다.
- G6은 Validator가 직접 실행한 결과만 판정에 쓴다. 에이전트 출력, G5 증거의 재사용, 상태 파일은 증거가 아니다(SPEC §5.1). 판정은 기계 판정이고 AI 리뷰를 두지 않는다(결정 2).
- G6.PREREQ는 "G5가 현재 manifest로 PASSED"다. manifest가 G4/G5와 같으므로 G6이 PASSED면 같은 파일로 G4 리뷰·G5 실행도 통과한 것이다.

이 경계를 지키는 데 걸리는 현재 사실 하나: 기본 unit 명령이 통합 테스트까지 실행한다. G5 판정을 바꾸지 않는 한(0.1.x 이후 불변식 테스트가 지키는 계약) 통합 테스트 실패는 G6보다 먼저 G5 실패로 드러날 수 있다. 결정 1이 이를 다룬다.

## 2. 결정해야 할 네 가지

### 결정 1. 통합 테스트 실행 명령
PLAN 원문: "실행 명령: config에 `integration_test`(argv, timeout) 항목을 따로 두는 안을 권장한다. JUnit 기반이라 언어 중립(D13)을 유지한다. 대안은 unit 명령을 재사용하고 수준별로 선택하는 것."

문제: G6이 무엇을 실행할지, 그 설정을 누가 어떻게 정하는지. 언어 중립(argv + JUnit, D13)과 실행 환경 통제(D21)를 유지해야 한다.

| 대안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| A | `config.integration_test`(argv에 `{junit}` 필수, timeout_s, plugin_autoload) 필수. 없으면 G6 BLOCKED(misconfigured) | 실행 대상이 명시적. unit과 분리 실행 가능 | 기존 프로젝트는 config를 고쳐야 한다. config는 G4/G5 manifest라 고치면 G4 리뷰·G5 재실행 비용(IF가 있는 WI만 해당) |
| B | `unit_test` 명령을 G6이 다시 실행하고 integration ID만 판정 | 설정 추가 없음 | 통합 테스트가 G5·G6에서 두 번 돈다. 분리 실행을 원할 때 방법이 없다 |
| C | G6이 실행하지 않고 G5 실행 증거(JUnit)에서 integration ID만 매핑 | 가장 싸다 | "Gate는 자기 실행 증거로만 PASS"를 깬다. 통합 실패는 늘 G5 실패로만 보이고 G6은 커버리지 확인으로 축소된다 |
| D | Validator가 TEST ID로 선택 실행(`-k TEST_010 or …`) | 설정 없이 정확한 선택 | pytest 전용 문법이라 D13(언어 중립)을 깬다 |
| **E (권장)** | `integration_test`를 **선택 항목**으로 두고, 없으면 `unit_test` argv로 G6이 직접 다시 실행한다(B로 대체). 증거에 어느 명령인지(`command_source: integration_test | unit_test`) 남긴다. 새로 `init`하는 프로젝트는 분리 기본값(unit은 `--ignore=tests/integration`, integration은 `tests/integration`)을 쓴다 | 기존 프로젝트는 config 수정 없이 G6을 돌릴 수 있다. 분리하고 싶으면 명령 하나만 추가. 언어 중립·D21 그대로 | 분리하지 않은 프로젝트는 통합 테스트가 두 번 돌고, 통합 실패가 G5에서 먼저 잡힌다(결함의 `gate`가 G5가 됨. 원인 단계는 `root_cause_phase`로 따로 기록되므로 복귀 절차는 같다) |

G1~G5 호환: G5의 명령·판정·체크 목록을 바꾸지 않는다(교차 버전 불변식 `GateDecisionInvariant` 유지). 스키마는 `integration_test`를 선택 키로 추가하므로 기존 config가 그대로 유효하다. G6 실행부는 `eval_g5`의 실행·증거·JUnit 파싱·환경 정리를 함수로 나눠 재사용한다.

권장 근거: 증거 원칙(Gate는 자기 실행으로만 PASS)을 지키면서 기존 프로젝트에 설정 변경 비용을 강요하지 않는 유일한 안이다. 분리 실행 여부는 판정의 정확성(누락 없음)에 영향이 없고 실패가 드러나는 Gate만 달라진다. 배치가 틀려도 매핑 검사가 잡는다: integration ID가 G6 실행에 없으면 G6.TEST_MAPPING "not executed", unit ID가 G5 실행에 없으면 G5.TEST_MAPPING이 실패한다.

구현·테스트 영향: config 스키마(선택 키), `init` 기본값 2개, `eval_g6`(실행부 공용화), 증거 `kind: integration_test`. 하네스: 대체 실행, 전용 명령, `{junit}` 누락 → BLOCKED, 명령 없음·시작 실패 → BLOCKED, 시간 초과 → FAILED, 환경 정리(D21) 동일성, 한글 경로·Windows cp949.

### 결정 2. 통합 테스트 코드 확인 위치
PLAN 원문: "테스트 코드 확인 위치: G4.TEST_CODE/TEST_INTEGRITY를 integration 수준까지 넓혀 G4 리뷰가 함께 보게 하는 안을 권장한다. G5를 순수 기계 판정으로 둔 D12와 같은 구조다. 대안은 G6에서 따로 확인하는 것."

문제: 통합 테스트 코드가 명세(TEST)대로 있는지, 결과 보고를 조작하지 않는지, 실제로 인터페이스를 건너는지(목으로 대체하지 않는지)를 어느 Gate가 보는가.

| 대안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| **A (권장)** | G4.TEST_CODE가 unit과 **integration** ID 모두에 "이름에 그 ID 하나만 가진 테스트 함수"를 요구한다. G4.TEST_INTEGRITY는 이미 모든 테스트 파일을 보므로 그대로. G4 리뷰 체크리스트(verifier 지침)에 통합 테스트 적합성(선언된 IF의 실제 provider·consumer를 연결, 검증 대상 IF를 목으로 대체하지 않음, IF가 선언한 오류 경로)을 추가. G6은 기계 판정만, `gates.json` G6 reviewer를 "none (mechanical)"로 고친다 | D12와 같은 구조. 누락을 구현 단계(G4)에서 일찍 잡는다. 서브에이전트 호출이 늘지 않는다 | G4 리뷰 범위가 넓어진다. IF가 있는 WI는 통합 테스트 코드가 없으면 G4에서 막힌다(의도) |
| B | G6에 G6.TEST_CODE(AST)와 G6.REVIEW(verifier AI 리뷰)를 둔다(`gates.json`의 현재 표기) | G6이 자기 테스트 코드를 직접 책임 | 같은 결함을 G4 리뷰·G5 실행 뒤에야 잡는다. 실행 증거와 의미 검토가 섞인다(D12가 피한 것). 평가마다 서브에이전트 비용 |
| C | 기계 확인은 G6, 의미 검토는 G4 | 리뷰는 한 번 | 코드 누락이 G6에서야 FAILED → P4 결함인데 G6 결함으로 기록되고 G4 재리뷰가 다시 필요 |

G1~G5 호환: G4 판정이 바뀌는 경우는 integration TEST 명세가 있는데 그 코드가 없는 WI뿐이다. 그런 명세는 IF가 있을 때만 G3이 요구한다. 실제 세션 산출물 4건은 IF 0개라 영향이 없다. 하네스 픽스처는 TEST-010 코드가 이미 있어 기존 G4 테스트의 기대값이 바뀌지 않는다(구현 시 하네스로 확인). 업그레이드 직후에는 Core 해시 변경으로 어차피 모든 PASS가 STALE이라 재평가 시점에 새 규칙이 적용된다.

권장 근거: 테스트 적합성의 의미 검토는 G3(명세)·G4(코드)에서 하고 실행 Gate는 기계 판정만 한다는 D12를 통합 수준에 그대로 적용한다. 함수 존재 같은 기계 확인을 G4에 두면 같은 결함이 한 단계 일찍, 더 싼 재작업으로 잡힌다.

구현·테스트 영향: eval_g4 TEST_CODE 대상 확장, verifier 지침·스킬 문구, gates.json 표기. 하네스: 통합 ID 코드 누락 → G4 FAILED, ID 두 개 이름 → FAILED, 통합 테스트 파일의 결과 훅 → TEST_INTEGRITY FAILED, 기존 G4 테스트 무변경 확인.

### 결정 3. IF가 0개인 아키텍처에서 G6 판정
PLAN 원문: "IF가 0개인 아키텍처에서 G6 판정: N/A 사유를 기록하고 통과시킬지, 통합 테스트가 있으면 실행만 할지."

문제: 지금까지 실제 산출물은 모두 IF 0개였다. 이대로면 G6은 공허하게 통과하거나 영원히 막힌다. 어느 쪽도 "PASS = 검증했다"는 신뢰 모델과 맞지 않는다.

| 대안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| A | IF 0개 → G6 PASSED(N/A), 실행 없음. 사유 기록 | 단순 | 통합 명세가 있어도 실행하지 않음. PASSED가 "검증함"으로 오해될 수 있다 |
| B | IF 0개라도 integration 명세가 있으면 실행, 없으면 N/A | 쓴 테스트는 반드시 돈다 | N/A 표시 방식이 따로 필요 |
| C | IF 0개여도 통합 테스트 1개 이상 요구 | 공허한 통과 없음 | 단일 컴포넌트에 인위적 테스트를 강요. G2가 IF를 요구하지 않는 경우와 충돌 |
| D | 새 Gate 상태 `NOT_APPLICABLE` | 가장 정직한 표기 | 상태 머신(gates.json 상태 목록, STALE 계산, WI 상태, status·report·스킬, 하네스)을 넓게 바꾼다 |
| **A+B (권장)** | 적용 판단을 기계적으로 한다. **IF 0개이고 integration 명세도 0개**일 때만 N/A: 기록 상태는 PASSED, 기록에 `applicability: "not_applicable"`과 사유(`na_reason`이 있으면 그것, 없으면 G2에서 리뷰된 `integration_test_strategy.approach`)를 남기고, 실행 체크는 `skip`(N/A)로 기록한다. status·report·trace는 `PASSED (N/A: no interfaces)`로 표시하고 "통합 검증 수행"으로 보고하지 않는다. integration 명세가 하나라도 있으면 실행한다 | 쓴 테스트는 반드시 실행. N/A는 리뷰된 산출물에서 매번 다시 파생되고 manifest에 묶여 STALE 규칙을 그대로 탄다. 상태 머신 변경 없음 | 기록 상태가 PASSED라서 표시 계층에서 N/A를 반드시 구분해야 한다(구현 시 표시 테스트로 고정) |

공허한 N/A를 막는 장치(기존 Gate가 이미 하는 것): 컴포넌트 2개 이상이면 G2.INTERFACES가 IF를 요구하므로 N/A는 단일 컴포넌트에서만 가능하다. IF를 지우려면 architecture.json이 바뀌어 G2부터 다시 리뷰된다. integration TEST를 지우려면 G3.NO_SILENT_REMOVAL이 CR/결함의 `removed_ids`를 요구한다. 남는 빈틈(관찰): IF ID 삭제는 NO_SILENT_REMOVAL 대상이 아니라 G2 리뷰에만 기댄다(§4 위험).

G1~G5 호환: `na_reason` 필수화는 하지 않는다. 필수화하면 기존 WI의 architecture.json을 고쳐야 하고 G2부터 리뷰가 다시 돈다. `approach`는 필수 필드이고 이미 G2에서 리뷰되며 실제 산출물 4건이 모두 사유를 담고 있다. STRICT 프로파일(EXT)은 `na_reason`과 사용자 결정을 요구하는 안을 따로 검토할 수 있다.

권장 근거: 정직한 완료 표시(D15)를 지키면서 상태 머신을 넓게 흔들지 않는다. N/A 여부는 사람이나 에이전트의 주장이 아니라 리뷰된 산출물에서 Validator가 매번 계산한다.

구현·테스트 영향: eval_g6 적용 판단, 기록 키 `applicability`, status·report·trace 표시. 하네스: IF 0·명세 0 → N/A PASSED(실행 없음, 표시 확인), IF 0·명세 있음 → 실행, IF 추가 → STALE 후 N/A 아님, N/A 기록이 "통합 검증 수행"으로 표시되지 않음.

### 결정 4. 업그레이드 영향 (기존 PARTIALLY_VERIFIED WI)
PLAN 원문: "업그레이드 영향: G6이 구현되면 기존 PARTIALLY_VERIFIED WI는 G6이 NOT_STARTED라서 IN_PROGRESS로 돌아간다. 의도된 동작으로 문서화한다."

문제: G6 구현 버전으로 올리면 `wi_status`가 G6을 구현된 Gate로 세므로, G1~G5를 통과한 WI가 IN_PROGRESS로 보인다. 이것을 받아들일지, 예외를 둘지.

| 대안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| **A (권장)** | 받아들인다. G6 평가 전까지 IN_PROGRESS, `next_action`은 "run `vmodel gate <WI> G6`", `vmodel verify`는 G1~G6. 문서·스킬·SessionStart 문구(지금 "MVP scope: only G1-G5")를 바꾼다 | 상태는 원장과 현재 Gate에서만 파생된다는 원칙 유지. 어차피 업그레이드 때 Core 해시가 바뀌어 G1~G5 PASS가 모두 STALE이라 재검증이 필요하고, G6은 그 끝에 한 단계 더하는 것뿐이다. 결정 3에 따라 IF 0개 WI는 실행 없이 N/A로 끝난다 | 사용자에게는 "상태가 내려갔다"로 보인다(문서·업그레이드 출력으로 안내 필요) |
| B | 이전 버전에서 PARTIALLY_VERIFIED였던 WI는 G6 없이 유지(grandfather) | 표시 변화 없음 | 같은 원장에서 버전에 따라 다른 결론. 원장 밖의 예외 규칙 |
| C | 업그레이드(재고정) 때 Validator가 G6을 자동 평가 | 사용자 조작 없음 | 사용자가 요청하지 않은 Gate 기록이 원장에 생긴다. 재고정 직후는 G1~G5가 STALE이라 G6 전제 조건이 성립하지 않는다 |
| D | 프로파일 버전(STANDARD@1=G1~G5, @2=G1~G6) | 이전 결론 보존 | 과설계. 결국 G7에서 또 바뀐다 |

G1~G5 호환: G1~G5 판정·원장·manifest는 그대로다. WI 상태의 파생 규칙(`wi_status`)도 그대로이고 입력(구현된 Gate 목록)만 늘어난다. STANDARD는 G7이 없으므로 G6까지 통과해도 계속 PARTIALLY_VERIFIED이고 COMPLETED는 M6 이후다. 표시 상태(D37)의 결함 종료 판단은 결함이 인용한 Gate만 보므로 G5 결함의 표시가 바뀌지 않는다.

권장 근거: 상태의 유일한 원천은 서명 원장이고(D03), 정직한 완료 표시(D15)가 원칙이다. 업그레이드 재검증은 이미 필요한 절차라 추가 비용이 작다.

구현·테스트 영향: status 문구(MVP_NOTE, next_action), report 한계 절, 스킬(start·verify·status·report)·SessionStart 문구, `vmodel verify` 범위(구현된 Gate 목록을 쓰므로 코드 변경 없음, 하네스로 확인). 하네스: 이전 릴리스로 PARTIALLY_VERIFIED → 재고정 → STALE → G1~G5 재검증 → IN_PROGRESS(G6 NOT_STARTED) → G6 → PARTIALLY_VERIFIED, 기존 원장·증거 audit OK(0.1.4·0.1.5 교차 버전 테스트와 같은 방식).

## 3. 사용자가 요구한 설계 항목별 정리

1. 아키텍처 인터페이스와 Integration Test 간 추적성: IF(architecture) → integration TEST(`verifies`에 IF, G3) → 테스트 함수(이름에 ID 하나, G4) → G6 JUnit 결과(G6.TEST_MAPPING) → IF별 통과 여부(G6.IF_COVERAGE). `vmodel trace`에 IF 행과 G6 결과 열을 추가한다. DEFECT `related`에 IF·TEST를 연결하고 결함 추적(D35)은 G6 기록에도 같은 분류(실패 TEST·UNKNOWN·무효 인용)를 쓴다.
2. 통합 테스트 실행 증거: G5와 같은 구조로 `.vmodel/evidence/<WI>/G6/<run>/`에 stdout·stderr 원본 바이트, junit.xml, 서명된 record.json(명령·실행 파일 해시·런타임·시각·종료 코드·환경 정리 내역·검증 대상 파일 해시·manifest 해시·Core 해시·`command_source`). 원장 기록에 `executed_tests`(integration ID별 결과). audit·verify-evidence는 Gate 구분 없이 같은 검사를 한다.
3. G5와 G6 검증 책임의 구분: §1. G5는 unit 명세, G6은 IF. G6.PREREQ = G5 PASSED(같은 manifest). G5 판정은 바꾸지 않는다. 분리 실행은 결정 1(E).
4. 통합 대상과 테스트 범위: 대상은 `architecture.json` `interfaces[]`(provider → consumers, `EXTERNAL` 포함). 범위는 IF마다 integration TEST ≥1(G3), 그 테스트가 G6 실행에서 통과(G6.IF_COVERAGE). 실제 provider·consumer 연결(목 대체 금지)과 IF가 선언한 오류 경로는 G4 리뷰(AI, 기계 검증 아님). consumer가 여럿인 IF의 consumer별 테스트 요구는 STRICT 후보로 남긴다.
5. 통합 실패 시 원인 단계 복귀: G6 FAILED → 재작업 전제 조건(직전 G6 실패 기록을 인용한 DEFECT, D14) → `root_cause_phase` P2(IF 계약), P3(단위 설계·통합 명세), P4(코드·테스트 코드)로 복귀 → 수정하면 manifest가 바뀌어 그 아래 Gate가 자동 STALE → 위에서부터 재평가. 3회 동일 실패 BLOCKED, 결함 표시 상태(D37) 그대로. defects 스키마 `gate` enum에 G6 추가, `TEST_EXECUTING_GATES`에 G6 추가.
6. 소스·인터페이스 변경에 따른 기존 증거 무효화: G6 manifest는 코드 manifest(프로젝트 전체 + architecture·design·tests·config·defects·CR). 소스·테스트·설정 변경 → G4·G5·G6 STALE. 인터페이스 변경(architecture.json) → G2 STALE → 하위 전부 STALE. Core 변경 → STALE. 기존 증거는 원장에 그대로 남지만(불변) STALE 이후 판정에 쓰이지 않는다. G6.NO_WEAKENING: 마지막 PASSED G6(없으면 첫 G6) 대비 실행됐던 integration ID가 사라지면 실패(삭제는 CR/결함 `removed_ids`). 테스트 파일 변경 정당화는 같은 manifest에서 먼저 통과해야 하는 G5.NO_WEAKENING이 이미 요구하므로 G6에서 중복하지 않는다(통합 테스트 파일도 `paths.tests` 아래여야 G4.TEST_CODE가 찾는다).
7. 통합할 인터페이스가 없는 프로젝트: 결정 3(A+B).
8. 실제 테스트 실행과 Gate PASS 판정의 관계: PASS는 그 평가에서 Validator가 직접 실행한 integration 명령의 증거로만 난다(종료 코드 0, JUnit, 실패·오류 0, 매핑·IF 커버리지, 실행 중 입력 불변). 에이전트 보고·G5 증거·이전 실행은 쓰지 않는다. 유일한 예외인 N/A는 실행했다고 주장하지 않고 N/A로 기록·표시한다. `vmodel verify`는 저장 결과를 믿지 않고 다시 실행한다.

## 4. 체크 초안 (권장안 기준, 모두 기계 판정)

| 체크 | 판정 |
|---|---|
| G6.PREREQ | G5가 현재 manifest로 PASSED |
| G6.APPLICABILITY | IF 수·integration 명세 수로 적용/N/A 결정, 사유 기록 |
| G6.EXECUTION | `integration_test`(없으면 `unit_test`) argv를 Validator가 정리된 환경(D21)으로 실행, `{junit}` 필수(없으면 BLOCKED misconfigured), 시작 실패 BLOCKED, 시간 초과·비 0 종료·JUnit 없음 FAILED |
| G6.RESULTS | 테스트 수 > 0, 실패·오류 0 (대체 실행이면 unit 케이스도 포함된다) |
| G6.TEST_MAPPING | 모든 integration TEST ID에 이름에 그 ID 하나만 가진 통과 케이스, 실패·skip 없음 |
| G6.IF_COVERAGE | 모든 IF에 그 IF를 `verifies`에 가진 integration TEST가 이번 실행에서 통과 |
| G6.NO_WEAKENING | 이전 실행된 integration ID 유지(삭제는 removed_ids) |
| G6.INPUTS_UNCHANGED | 실행 중 검증 대상 파일 불변 |

## 5. 사용자 결정이 필요한 것 (요약)

1. 결정 1: E(선택 `integration_test`, 없으면 unit 명령으로 G6이 직접 재실행, 새 init은 분리 기본값)를 받아들일지.
2. 결정 2: A(G4.TEST_CODE를 integration까지, G4 리뷰에 통합 적합성, G6은 기계 판정·gates.json reviewer 수정)를 받아들일지.
3. 결정 3: A+B(IF 0·integration 명세 0일 때만 N/A, 기록 PASSED + `applicability`, 표시는 N/A, `na_reason` 필수화 안 함)를 받아들일지. 또는 D(새 상태 NOT_APPLICABLE)를 원하는지.
4. 결정 4: A(IN_PROGRESS로 돌아가는 것을 의도된 동작으로 문서화)를 받아들일지.
5. 버전: G6 구현은 Gate 의미가 바뀌므로 0.2.0(PLAN 제안). 새 샘플(컴포넌트 2개 이상, IF 1개 이상)과 실제 Claude 세션 E2E(M7)는 비용 승인 후.

## 6. 위험·미정

- 대체 실행(E)에서 통합 테스트가 G5에서 먼저 실패하면 결함의 `gate`가 G5가 된다. 원인 단계는 `root_cause_phase`로 남지만, 통계를 낼 때 G6 실패가 적게 보일 수 있다.
- IF ID 삭제는 G3.NO_SILENT_REMOVAL 대상이 아니라 G2 리뷰에만 기댄다. IF를 지워 N/A로 만드는 경로는 컴포넌트 2개 이상이면 G2.INTERFACES가 막지만, 1개면 리뷰 판단이다. 필요하면 G2에 IF 삭제 정당화(CR/결함 `removed_ids`)를 넣는 안을 따로 검토한다(G2 판정 변경이라 이번 결정과 분리).
- "목으로 대체하지 않음"은 AI 리뷰 판단이며 기계 검증이 아니다(SPEC §5.7의 한계와 같다).
- 테스트 코드는 러너와 같은 프로세스에서 돈다는 한계(G4.TEST_INTEGRITY 휴리스틱)는 통합 테스트에도 같다.
- 지금까지 실제 세션 산출물에 IF가 없어서, 실제 세션에서 G6 적용 경로를 본 적이 없다. M5 하네스용 새 샘플과 M7 실제 세션이 필요하다.
