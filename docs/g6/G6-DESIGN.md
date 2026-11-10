# G6 Integration Verification 확정 설계 (구현 전)

작성 2026-11-09. 상태: **정책 확정, 구현 전.** 정책은 사용자 결정(2026-11-09, "VModel DevKit v0.1.5 릴리스 확정 및 G6 설계 결정")이고 DECISIONS D41에 기록했다. 이 문서는 그 정책을 요구사항·아키텍처·상세 설계·테스트 명세로 구체화한 것이며, 구현은 별도 세션에서 §7 절차로 시작한다.
기준 코드: 태그 `v0.1.5`(core `sha256:37071459…`). "현재 코드" 언급은 이 버전을 읽고 확인한 사실이다. 추정은 따로 표시한다.
이 문서는 독립 검토(별도 컨텍스트, 읽기 전용) 1회를 거쳐 고쳤다. 지적과 처리는 §11.
이전 문서 `docs/g6/G6-DESIGN-PROPOSAL.md`(D39)는 결정 전 대안 비교로 남긴다. 결정 1·3은 사용자 결정이 제안 권장안과 다르다(§1).

## 1. 확정 정책과 제안안 대비 차이

| 결정 | 확정 정책 (사용자) | D39 권장안과 차이 |
|---|---|---|
| 1. 실행 명령 | config `integration_test`를 지원한다. G6 통합 검증이 필요하면 명시적 통합 테스트 명령을 요구하고, 없으면 G6은 BLOCKED다. 단위 테스트 재실행 결과로 G6을 PASS하지 않는다. G5는 Unit, G6은 Integration으로 책임을 나누고, G5 실행 범위에 통합 테스트가 섞인 문제를 정리한다. 기존 설정과 호환되게 마이그레이션한다 | 권장안 E의 "없으면 unit 명령으로 G6이 직접 재실행"을 **버린다**. 대체 실행 없음 |
| 2. G4/G6 역할 | G4는 인터페이스 구현 여부, provider/consumer 연결 설계, 통합 테스트 명세·추적, 통합 검증 가능한 코드 준비 상태를 검토한다. G6은 독립 Validator가 실제 실행, 실행 대상과 설정, 실제 종료 코드, 결과와 증거, 인터페이스↔테스트 매핑, 현재 코드·설정 해시, 판정 유효성을 확인한다. G6 최종 판정은 AI 리뷰만으로 PASS하지 않는다. gates.json의 G6 reviewer 정의가 구현과 충돌하지 않게 한다 | 권장안 A와 같은 방향. 연결(IF를 실제로 건너는가)을 G4·G6 모두 **기계적으로** 확인하도록 강화했다(§4.6, §4.3 IF_COVERAGE) |
| 3. IF 0개 | 다음을 **모두** 만족할 때만 N/A: 통합 대상 인터페이스 없음, 통합 테스트 명세 없음, 실제로 통합 검증할 컴포넌트 관계 없음, G2/G3 검토에서 불필요 사유 확인. 필요하면 PASSED + applicability=N/A로 기록하되 실행된 통합 테스트가 PASS한 것처럼 표시하지 않는다. 확인할 수 없으면 N/A로 처리하지 않는다. IF나 통합 명세가 있으면 검증한다 | 권장안 A+B에 **리뷰 확인 조건**과 **IF 삭제 정당화 조건**을 더했다 |
| 4. 기존 WI | G6 추가로 기존 PARTIALLY_VERIFIED WI가 IN_PROGRESS로 보이는 것을 승인. 단 G1~G5 PASS·실행 증거 보존, G6 추가만으로 G1~G5를 STALE로 만들지 않음, G6 미실행을 명확히 표시, Gate 결과와 WI 완료 상태를 구분 | 권장안 A에 표시 조건을 더했다 |

### 1.1 결정 4와 기존 무결성 규칙의 관계 (사용자 확인 필요, §9 1번)
SPEC §5 5항의 기존 규칙상 Validator Core 해시가 바뀌면 모든 PASS가 STALE이다(gates.json도 Core에 포함). 0.1.3→0.1.4, 0.1.4→0.1.5 업그레이드도 같았다. G6을 넣은 릴리스로 업그레이드하면 이 규칙 때문에 G1~G5가 한 번 STALE이 된다. 이 설계는 이것을 "G6 추가 때문의 STALE"로 보지 않는다. G6은 G1~G5의 manifest(입력 파일 목록)를 하나도 늘리지 않으며(불변식 C2), STALE은 Core 교체라는 별개 사건의 결과다. 기존 PASS 기록과 증거는 원장에 그대로 남는다. 사용자가 "업그레이드 후에도 G1~G5가 STALE이 되면 안 된다"는 뜻이었다면 Core 무결성 규칙 자체를 바꾸는 별도 결정이 필요하다(권하지 않는다: 판정 코드가 바뀐 Validator로 이전 판정을 그대로 믿게 된다).

### 1.2 G1~G5 판정이 바뀌는 범위 (정직한 호환 범위)
- G1~G5 manifest 계산: 모든 프로젝트에서 0.1.5와 같다.
- G1·G2·G3 판정: 모든 WI에서 0.1.5와 같다(리뷰의 새 키 `integration_applicability`는 G2·G3 판정에 쓰지 않는다).
- G5 판정: `integration_test`가 **없는** config에서는 0.1.5와 같다. 있으면 G5.SCOPE와 NO_WEAKENING 범위가 바뀐다(결정 1).
- G4 판정: IF도 integration 명세도 없는 WI에서는 0.1.5와 같다. IF나 integration 명세가 있는 WI에서는 결정 2에 따라 바뀐다(통합 테스트 코드, 연결 확인, 리뷰의 IF 항목). 이 차이는 의도된 변경이며 테스트 C5가 목록으로 고정한다.

### 1.3 확정 보수 정책 A·B (2026-11-10, 사용자 승인, DECISIONS D45)
구현 중 바뀐 판정 규칙의 정본은 D42~D45다. 이 설계의 "목 대체 판단은 G4 리뷰"(결정 2, §4.6 patch warn)는 D44·D45로 다음과 같이 확정됐다.
- **A. Provider patch**: patch된 provider 실행만으로는 실제 연결 검증이 아니다. 테스트 함수가 인터페이스 심볼이나 provider 모듈에 정의된 함수·클래스·메서드를 patch하면 그 테스트는 경로 A·B 모두 Test-level이 아니다. 다른 독립적이고 유효한 증거(patch하지 않은 다른 테스트의 Test-level 증거)가 있으면 IF는 덮인다. 근거가 없으면 BLOCKED(`integration_evidence_insufficient`). G4 patch 경고는 그대로 둔다.
- **B. Autouse fixture**: autouse·요청하지 않은 fixture 자체가 만든 연결(그 fixture 코드, 그 fixture가 시작한 스레드·서버·프로세스)은 개별 테스트의 증거가 아니다. 테스트 함수나 그 테스트가 요청한 fixture·setUp이 실행했거나 시작한 연결은 증거다. fixture 사용 자체는 막지 않는다.
- 근거가 불충분하면(출처를 이을 수 없는 프로세스 등) 통과가 아니라 BLOCKED다.

## 2. G6 Requirements

ID는 이 설계 안에서만 쓰는 번호다(구현 세션의 WORKITEM에서 그대로 쓴다). 각 요구사항의 수용 기준은 §6의 테스트로 검증한다.

### 2.1 실행 명령과 설정
- **REQ-G6-01** config에 선택 키 `integration_test`(`argv` 필수·문자열 1개 이상, `timeout_s` 필수·양의 정수, `plugin_autoload` 선택)를 둔다. 이 키가 없는 기존 config는 그대로 유효하다.
  - AC-01a 0.1.5 config(키 없음)가 스키마 검증을 통과하고, §1.2의 범위 밖에서 G1~G5 판정이 0.1.5와 같다.
  - AC-01b `integration_test`가 하위 스키마에 맞지 않거나(`argv`가 문자열, `timeout_s` 없음 등) argv에 `{junit}`이 없으면 G6은 명령을 실행하지 않고 BLOCKED(`misconfigured`)다. config는 init 때만 스키마 검증되므로(코드 확인) G6이 평가마다 하위 스키마를 검증한다.
- **REQ-G6-02** G6 적용 대상(§2.4)인데 `integration_test`가 없으면 G6은 BLOCKED(`misconfigured`)이고 어떤 명령도 실행하지 않는다. `unit_test` 명령으로 대체 실행하지 않는다.
  - AC-02a 이때 G6 기록의 실행 증거가 비어 있고, status·next_action이 "사용자가 `.vmodel/config.json`에 integration_test를 추가해야 함"을 알린다(config는 보호 파일이라 에이전트가 고칠 수 없다).
- **REQ-G6-03** G6은 G5의 실행 증거·결과를 판정에 쓰지 않고, G5도 G6 결과를 쓰지 않는다.

### 2.2 G5/G6 책임 분리
- **REQ-G6-04** G5는 unit 수준 TEST만 판정 책임으로 가진다(지금과 같다: G5.TEST_MAPPING은 unit ID만 요구).
- **REQ-G6-05** `integration_test`가 설정된 프로젝트에서 unit 명령이 integration 수준 TEST ID를 실행하면 G5는 FAILED(G5.SCOPE)다.
- **REQ-G6-06** `integration_test`가 없는(기존) 프로젝트에서 G5의 판정·기록 형식은 0.1.5와 같다. unit 명령이 integration 수준 TEST를 실행했다면 status·report가 G5 기록의 `executed_tests`에서 그 사실을 파생해 경고로 보이고, 그 결과는 통합 검증 증거가 아니라고 표시한다.
- **REQ-G6-07** `integration_test`가 설정된 프로젝트에서 G5.NO_WEAKENING의 "이전에 실행된 TEST ID 유지" 규칙은 **지금 tests.json에서 integration 수준인 ID만** 제외한다(그 ID는 G6.TEST_MAPPING·G6.NO_WEAKENING이 지킨다). unit 테스트를 지우거나 system 수준으로 바꿔 G5에서 빠지는 것은 지금처럼 실패다.
- **REQ-G6-08** G6 실행에서 unit 수준 TEST ID가 실행되면 G6은 FAILED(G6.SCOPE)다. system 수준 ID는 경고만 한다(G7 책임, 미구현). 수준은 프로젝트의 모든 WI `tests.json`을 합쳐 정한다(TEST ID는 프로젝트 전체 유일). 어느 WI에도 없는 ID는 `unmapped_cases`로만 남긴다.

### 2.3 G4: 통합 준비 상태
- **REQ-G6-09** G4.TEST_CODE는 unit과 integration 수준 TEST ID 모두에 "이름에 그 ID 하나만 가진 테스트 함수"를 요구한다. 체크 항목(items) 문자열 형식은 바꾸지 않는다(실패 서명 유지).
- **REQ-G6-10** G4.INTERFACE_IMPLEMENTED(기계, IF가 있을 때만 기록): IF `signature`에서 `def NAME`/`class NAME`을 읽을 수 있으면 그 심볼이 provider 컴포넌트의 설계 단위 모듈에 정의돼 있어야 한다(아니면 fail). 읽을 수 없으면 warn("구현 심볼은 G4 리뷰의 `provider_symbols`로 확인"). 컴포넌트에 구현된 단위가 있다는 것 자체는 G3.DESIGN_COVERAGE + G4.DESIGN_CONFORMANCE가 이미 보장한다.
- **REQ-G6-11** G4.INTEGRATION_WIRING(기계, integration 명세가 있을 때만 기록): 각 IF에 대해, 그 IF를 `verifies`에 가진 integration 테스트 함수 중 하나 이상이 §4.6의 **함수 단위 정적 도달**로 provider 모듈과(ARCH consumer가 있으면) consumer 모듈에 닿아야 한다. 하나도 닿지 않는 IF가 있으면 **fail**. provider 모듈을 `patch`/`monkeypatch` 대상으로 쓰는 테스트는 warn(판단은 리뷰).
- **REQ-G6-12** WI에 IF가 하나라도 있으면 G4.REVIEW는 리뷰 파일의 `interfaces`에 모든 IF 항목이 있어야 approve로 인정한다. 항목 형식 `{"id", "result": "ok"|"issue", "provider_symbols": [...], "note"}`. `provider_symbols`는 비어 있지 않고 각 심볼이 provider 컴포넌트 단위 모듈에 정의돼 있어야 한다(기계 확인). 빠진 IF·형식 오류 → REVIEW_REQUIRED(verifier), `issue` → FAILED.
- **REQ-G6-13** IF도 integration 명세도 없는 WI의 G4 기록(상태, 체크 ID·상태값, 실패 서명)은 0.1.5와 같다.

### 2.4 적용 판단 (N/A)
- **REQ-G6-14** G6은 평가마다 적용 여부를 기계적으로 계산한다. IF가 하나 이상이거나 integration 명세가 하나 이상이면 `required`다.
- **REQ-G6-15** 다음을 **모두** 만족할 때만 `not_applicable`이다.
  - (a) `architecture.interfaces`가 비어 있음.
  - (b) `tests.json`에 `level: integration` 명세 없음.
  - (c) 컴포넌트가 정확히 1개이고 `data_flows`의 `from`/`to`에 다른 ARCH ID가 없음.
  - (d) 현재 G2 PASS 기록이 인정한 G2 리뷰와 현재 G3 PASS 기록이 인정한 G3 리뷰가 모두 `integration_applicability: {decision: "not_required", reason: <비어 있지 않음>, endpoints_reviewed: [...]}`을 담고, 그 리뷰 파일이 지금 디스크의 파일과 같음. `endpoints_reviewed`는 `data_flows`의 ARCH ID가 아닌 끝점(사용자, 파일, DB 등) 전부를 담아야 함.
  - (e) 이 WI의 이전 G2 PASS 기록들의 `item_hashes`에 있던 IF ID가 지금 없다면, 그 ID가 모두 CR(rejected 아님)이나 DEFECT의 `removed_ids`에 있음.
- **REQ-G6-16** IF·integration 명세가 모두 0이지만 (c)·(d)·(e) 중 하나라도 확인할 수 없으면 G6은 BLOCKED(`applicability_unconfirmed`)다. N/A로 처리하지 않는다.
- **REQ-G6-17** N/A 평가는 상태 PASSED, `applicability: "not_applicable"`, 실행 증거 없음, 실행 체크는 `skip`으로 기록한다. `vmodel gate`/`verify` 출력, status, report, trace, next_action, 스킬 문구가 모두 "N/A"로 표시하고 "통합 테스트 통과"·"통합 검증 수행"·"G1-G5 verified" 같은 문구로 표시하지 않는다.

### 2.5 기계 판정과 증거
- **REQ-G6-18** G6에는 ai_review 체크가 없다. gates.json G6의 reviewer는 "none (mechanical)"이다.
- **REQ-G6-19** `required` G6의 PASS는 이번 평가에서 Validator가 직접 실행한 `integration_test` 명령의 증거와 Validator 자신의 정적 분석으로만 난다. 조건은 §4.3의 체크 전부. 특히 IF 커버리지는 "이름이 맞는 통과 케이스"가 아니라 "그 IF의 provider(와 consumer)에 정적으로 닿는 통과 테스트"를 요구한다.
- **REQ-G6-20** 증거는 G5와 같은 구조(원본 stdout/stderr, junit.xml, 서명된 record.json)에 G6 고유 항목(명령 출처·설정 해시, IF별 매핑·도달, 테스트 함수 위치, 근거 기록 ID)을 더한다. audit·verify-evidence가 G6 증거를 G5와 같은 방식으로 검사한다.

### 2.6 재작업·무효화·상태
- **REQ-G6-21** G6 FAILED는 G5와 같은 재작업 전제 조건(직전 실패 기록을 인용한 DEFECT), 3회 동일 실패 BLOCKED, 결함 추적(D35)·표시 상태(D37)를 따른다. defects와 change-requests 스키마의 `removed_ids`에 IF ID를 허용하고, defects `gate`에 G6, `root_cause_phase`에 P6을 더한다. 결함 추적의 TEST별 결과는 G6 기록에서도 같은 분류(실패 TEST, UNKNOWN, 무효 인용, 미연결)로 나온다.
- **REQ-G6-22** G6 manifest = 코드 manifest(G4/G5와 같음) + `reviews/G2.json` + `reviews/G3.json`. 어느 파일이든 바뀌거나 Core가 바뀌거나 G5가 PASSED가 아니면 G6 PASS(N/A 포함)는 STALE이다.
- **REQ-G6-23** G6.NO_WEAKENING: 기준은 마지막 `required` PASSED G6, 없으면 실행된 integration ID가 있는 가장 이른 G6 기록(실행 없는 BLOCKED 기록은 기준이 아니다). 기준에서 실행됐던 integration ID가 지금 실행되지 않으면, 그리고 이전 G2 PASS에 있던 IF가 지금 architecture에 없으면(기준과 무관), CR·DEFECT `removed_ids`로만 정당화된다. N/A 평가에서도 이 체크는 돈다.
- **REQ-G6-24** N/A 평가는 결함 검증으로 치지 않는다. `verified_by`·`verification_history`에서 N/A 기록을 뺀다. G6 실패를 인용한 결함은 G6이 N/A가 되어도 CLOSED가 아니고, 표시에 "G6 now N/A (scope removed by CR-…/DEFECT-…), not verified"를 단다(이 경우 종료 경로는 §9 7번 결정).
- **REQ-G6-25** WI 상태: G1~G5가 현재 PASSED이고 G6 평가 기록이 없으면 WI는 IN_PROGRESS, G6은 "평가 전(통합 검증 미실행)"으로 표시한다. status JSON은 Gate별 결과 요약(`gate_summary`)과 WI 상태를 따로 준다. G6 PASSED(N/A 포함)이고 G7이 미구현이면 WI는 PARTIALLY_VERIFIED다.
- **REQ-G6-26** G6 추가는 G1~G5 manifest를 바꾸지 않고, G1~G5 판정은 §1.2 범위 밖에서 0.1.5와 같다. 기존 원장 기록·증거는 다시 쓰지 않고, 0.1.5가 서명한 원장·증거는 새 버전에서 audit·verify-evidence를 통과한다.

## 3. G6 Architecture

### 3.1 구성 요소와 변경 범위

| 구성 요소 | 파일 | 변경 |
|---|---|---|
| Gate 정의 | `data/gates.json` | G6 `implemented: true`, 체크 10개(§4.3), reviewer "none (mechanical)", manifest에 `reviews/G2.json`·`reviews/G3.json`(§5). G4: 체크 2개 추가(INTERFACE_IMPLEMENTED, INTEGRATION_WIRING), TEST_CODE·REVIEW 설명 갱신. G5: SCOPE(조건부) 추가, NO_WEAKENING 설명 갱신. G2·G3 REVIEW 설명에 `integration_applicability`(G6이 쓰는 확인 기록, G2·G3 판정에는 쓰지 않음). STANDARD notes 갱신 |
| 스키마 | `config`, `review`, `defects`, `change_requests` | config `integration_test`(선택). review `integration_applicability`(선택, G2·G3), `interfaces`(선택, G4). defects `gate`+G6, `root_cause_phase`+P6, `removed_ids`에 IF. change_requests `removed_ids`에 IF |
| 실행부 | `gates.py` | `eval_g5`의 실행·증거·JUnit 파싱·환경 정리를 `_execute_suite(ctx, gate, cfg, kind)`로 분리(G5 불변식으로 보호). `eval_g6` 추가. `TEST_EXECUTING_GATES = ("G5", "G6")`, `citation_view`의 `"G5.TEST_MAPPING"` 고정을 `f"{gate}.TEST_MAPPING"`으로 |
| 정적 분석 | `gates.py`(또는 새 `wiring.py`) | 모듈 색인·import 그래프·함수 단위 도달(§4.6). G4와 G6이 같은 함수를 쓰고 G6은 자기 manifest로 다시 계산 |
| 적용 판단 | `gates.py` `g6_applicability()` | §4.2. 순수 함수(원장·산출물·리뷰 파일 읽기만). status도 미리보기로 호출 |
| G4 확장 | `gates.py` `eval_g4`, `check_review` | §4.6 |
| G5 범위 | `gates.py` `eval_g5`, `_no_weakening` | §4.5. `integration_test`가 있을 때만 동작이 바뀐다 |
| 결함 추적 | `gates.py` `defect_trace`, `status.closure_view` | N/A 기록 제외(REQ-24), G6 인용 |
| 표시 | `status.py`, `cli.py` `render_gate`, `GateRun.as_dict`, report, trace | `applicability`, N/A·미평가 표시, `gate_summary`, IF 행, REQ 행의 integration 결과는 G6에서, 범위 경고, next_action(차단 사유별, "G1-G5 verified" 고정 문구 교체) |
| 지침 | skills(start·verify·status·report·rework), agents(verifier·test-designer·implementer), `data/VMODEL.md` | G6 단계, 리뷰 기록 의무(§4.2, §4.6), 통합 테스트 작성 규칙(직접 호출, 하위 프로세스 금지), "MVP scope: only G1-G5" 문구 교체 |
| 설치 | `setup_project.init_project` | 새 프로젝트 기본 config(§4.1, 사용자 확인 대상 §9 3번) |

guard 훅(`hook.py`)·원장(`ledger.py`)·manifest 계산 함수(`compute_manifest`)·Core 무결성은 바꾸지 않는다. G6 manifest 확장은 gates.json 선언으로 한다.

### 3.2 책임 분리 (G2·G3·G4 리뷰 vs G5·G6 실행)

| 책임 | 어디서 | 종류 |
|---|---|---|
| IF 정의, provider/consumer, 통합 전략, IF 0개 사유 확인 | G2 (+리뷰 `integration_applicability`) | 기계 + AI 리뷰 |
| IF마다 integration 명세, 명세 불필요 사유 확인 | G3 (+리뷰 `integration_applicability`) | 기계 + AI 리뷰 |
| 인터페이스 구현 심볼, 통합 테스트 코드 존재, IF별 정적 도달, 목 대체 여부, IF별 리뷰 | G4 | 기계(INTERFACE_IMPLEMENTED, TEST_CODE, INTEGRATION_WIRING) + AI 리뷰(`interfaces` 항목 필수) |
| unit 명세 실행·매핑, unit 범위 유지 | G5 | 실행 + 기계 |
| integration 명령 실행, 설정·대상·종료 코드·결과·증거, IF↔TEST↔케이스 매핑과 정적 도달(재계산), 해시, 판정 유효성 | G6 | 실행 + 기계 (AI 없음) |

G6이 G4 리뷰에 기대는 것은 "목으로 대체하지 않았는가" 같은 의미 판단뿐이고, 이는 G6 PASS의 충분조건이 아니라 G6 전제(G4 PASSED)의 일부다. G6 PASS의 충분조건은 G6 자신의 실행 증거와 기계 체크(정적 도달 재계산 포함)다.

### 3.3 데이터 흐름 (required)
1. `vmodel gate WI G6` → 공통 전제 조건(무결성, G5가 현재 PASSED, 직전 실패의 DEFECT, 3회 실패 차단 해제) → 아니면 기록 없이 BLOCKED.
2. 적용 판단 → `required`.
3. 설정 확인(`integration_test` 하위 스키마, `{junit}`) → 아니면 BLOCKED 기록.
4. 새 실행 폴더 `.vmodel/evidence/<WI>/G6/<시각>-integration-<rand>/` 생성 → 정리된 환경(D21)으로 argv 직접 실행(셸 없음) → stdout/stderr 원본 바이트, junit.xml, 서명된 record.json.
5. 실행 후 manifest 재계산(INPUTS_UNCHANGED), JUnit 파싱, TEST ID 매핑, 수준별 분류(SCOPE), 정적 도달 재계산과 IF 커버리지, NO_WEAKENING.
6. 원장에 G6 gate 기록(서명, 해시 체인) → status·report·trace는 원장에서만 읽는다.

## 4. 상세 설계

### 4.1 Integration Test Configuration
```json
"integration_test": {
  "argv": ["{python}", "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/integration", "--junitxml={junit}"],
  "timeout_s": 900,
  "plugin_autoload": false
}
```
- 치환은 `unit_test`와 같다(`{python}`, `{junit}`). 하위 스키마 위반이나 `{junit}` 없음 → BLOCKED(`misconfigured`).
- 실행 환경은 G5와 같은 `runner.scrubbed_env`(에이전트의 `PYTHON*`·`PYTEST_*`·`VMODEL_*` 제거, 바이트코드 미사용, 플러그인 자동 로드 끔. `plugin_autoload: true`일 때만 켬).
- argv가 `unit_test.argv`와 같아도 거부하지 않는다. 그 경우 unit 테스트가 G6에서 실행되므로 G6.SCOPE가 FAILED를 낸다(문자열 비교보다 실제 실행된 것으로 판정).
- `.vmodel/config.json`은 보호 파일(설치 deny 규칙 + guard)이라 에이전트가 고칠 수 없다. G6 BLOCKED(`misconfigured`)의 next_action은 사용자 조치로 안내한다.
- 새 `init`(사용자 확인 §9 3번) 설계 기본값: `paths.tests`가 기본값(`tests/**/*.py`)이면 `unit_test.argv`에 `--ignore=tests/integration`, `integration_test`는 위 예시. `--tests`를 직접 준 경우에는 `--integration-tests <경로>`를 줄 때만 쓰고 아니면 안내만 출력한다.

### 4.2 적용 판단 `g6_applicability(ctx) -> dict`
입력: 현재 `architecture.json`, `tests.json`, 원장, `reviews/G2.json`, `reviews/G3.json`, defects·change-requests. 출력: `{"applicability": "required"|"not_applicable"|"unconfirmed", "basis": {...}, "problems": [...]}`.
1. IF 수 > 0 또는 integration 명세 수 > 0 → `required`.
2. 그렇지 않으면 REQ-G6-15 (c)·(d)·(e)를 확인하고, 하나라도 확인되지 않으면 `unconfirmed`(problems에 이유):
   - (c) 컴포넌트 수 == 1, `data_flows[*].from/to` 중 ARCH ID 패턴인 값이 모두 그 컴포넌트. ARCH ID가 아닌 끝점은 basis `external_endpoints`에 모은다.
   - (d) Gate g ∈ {G2, G3}마다: 원장에서 그 Gate의 마지막 PASSED 기록(전제 조건이 G2·G3 현재 PASSED를 이미 보장)의 `{g}.REVIEW` 체크 data `review_sha256`이 지금 `reviews/{g}.json`의 sha256과 같음, 그 리뷰의 `integration_applicability.decision == "not_required"`, `reason`이 공백이 아님, `endpoints_reviewed`가 `external_endpoints`를 모두 포함.
   - (e) 이 WI의 모든 G2 PASS 기록 `item_hashes`의 IF ID 합집합에서 지금 architecture에 없는 ID가 전부 `removed_ids`(CR은 rejected 제외, DEFECT 전부)에 있음.
   - `integration_test_strategy.na_reason`은 요구하지 않는다(있으면 basis에 기록). 요구하면 architecture.json이 바뀌어 G2~G4 리뷰와 G5 실행을 모두 다시 해야 한다. 리뷰 파일만 바뀌는 경로는 G2·G3 재평가와 G6만 다시 하면 된다(§4.11, 독립 검토가 원장 코드로 확인).
3. basis 기록: IF 수, integration 명세 수, 컴포넌트 ID, `external_endpoints`, `approach`, `na_reason`, G2·G3 PASS 기록 ID, 리뷰 sha256, 두 리뷰의 reason·endpoints_reviewed, 정당화된 삭제 IF와 근거 CR/DEFECT.

리뷰 스키마 추가(선택 키, G2·G3에서만 의미):
```json
"integration_applicability": {"decision": "not_required", "reason": "단일 컴포넌트(ARCH-001)이고 …",
                              "endpoints_reviewed": ["사용자 CLI 입력", "결과 JSON 파일"]}
```
verifier 지침: IF가 0개인 아키텍처의 G2 리뷰와 integration 명세가 0개인 G3 리뷰에는 이 항목을 반드시 쓴다. 단일 컴포넌트라도 외부 시스템(DB, 네트워크, 파일 형식 계약)과의 연동이 계약으로서 검증돼야 하면 `required`로 판단하고 IF(consumer `EXTERNAL` 또는 별도 컴포넌트)를 요구하는 지적을 남긴다. G2·G3 판정은 이 키를 보지 않는다(§1.2).

### 4.3 Quality Gate 판정 조건 (G6 체크, 모두 기계 판정)

| 체크 | required | not_applicable | 판정 |
|---|---|---|---|
| G6.PREREQ | pass | pass | G5가 현재 manifest로 PASSED (공통 전제 조건이 기록 전에 확인) |
| G6.APPLICABILITY | pass(`required`) | pass(`not_applicable`) | `unconfirmed` → blocked(`applicability_unconfirmed`). data에 basis |
| G6.CONFIG | 하위 스키마·`{junit}` 충족 → pass, 아니면 blocked(`misconfigured`) | skip | data에 명령 템플릿, `integration_test` 객체 sha256, `unit_test` 객체 sha256 |
| G6.EXECUTION | 종료 코드 0이고 junit.xml 생성 → pass. 시작 실패 → blocked(`tool_unavailable`). 시간 초과·비 0 종료·junit 없음·파싱 불가 → fail | skip("not executed: not applicable") | G5.EXECUTION과 같은 규칙 |
| G6.RESULTS | 케이스 수 > 0, 실패·오류 0 | skip | |
| G6.SCOPE | unit 수준 ID 실행 → fail, system 수준 → warn, 어느 WI에도 없는 ID·ID 없는 케이스 → data(`unmapped_cases`)만 | skip | 수준은 프로젝트 모든 WI tests.json 기준 |
| G6.TEST_MAPPING | 모든 integration 명세 ID에 이름에 그 ID 하나만 가진 `passed` 케이스. 실패·오류·skip 케이스가 하나라도 있으면 fail, 실행 안 됨 → fail(`TEST-xxx: not executed`, D35 UNKNOWN 분류와 같은 문구), 한 케이스 이름에 ID 둘 이상 → fail | skip | |
| G6.IF_COVERAGE | 모든 IF에 대해, `verifies`에 그 IF가 있고 이번 실행에서 passed이며 Validator가 다시 계산한 정적 도달(§4.6)로 provider 모듈과(ARCH consumer가 있으면) consumer 모듈에 닿는 integration 테스트가 하나 이상 | skip("no interfaces") | data에 IF별 테스트·상태·도달 |
| G6.NO_WEAKENING | REQ-G6-23 | 같은 규칙으로 실행 | |
| G6.INPUTS_UNCHANGED | 실행 전후 manifest 동일 | pass(실행 없음, 평가 전후 동일 확인) | |

상태: `derive_status`(blocked > fail > pending > warn·pass·skip). FAILED면 `failure_signature`와 3회 규칙. G6에는 pending(리뷰) 체크가 없으므로 REVIEW_REQUIRED는 생기지 않는다. `misconfigured`·`tool_unavailable`은 이미 `NEUTRAL_BLOCKS`에 있고 `applicability_unconfirmed`만 더한다.

### 4.4 형식적 Gate가 되지 않게 하는 장치 (반례 → 막는 체크)

| 반례 | 결과 |
|---|---|
| 통합 명령이 단위 테스트만 실행하고 종료 코드 0 | integration ID 미실행 → TEST_MAPPING fail, unit ID 실행 → SCOPE fail |
| 통합 명령이 아무 테스트도 수집하지 않고 0 종료(빈 디렉터리 등) | RESULTS fail(0 tests), TEST_MAPPING fail |
| 통합 테스트가 skip으로 끝남 | TEST_MAPPING fail(skipped) |
| `def test_TEST_010_x(): assert True`처럼 이름만 맞고 IF를 건너지 않는 테스트 | 정적 도달 없음 → G4.INTEGRATION_WIRING fail, G6.IF_COVERAGE fail(G6이 다시 계산) |
| 테스트는 통과했지만 일부 IF만 검증 | G3가 먼저 막고(IF마다 명세), G6 IF_COVERAGE가 이번 실행·도달 기준으로 다시 확인 |
| 종료 코드 0인데 junit 없음, 또는 에이전트가 미리 써 둔 junit | 실행 폴더는 실행 직전에 새로 만들고 Validator가 경로를 정한다. 증거 폴더는 보호된다. junit 없으면 EXECUTION fail |
| 다른 파일이 실행 중에 바뀜 | INPUTS_UNCHANGED fail |
| G5 증거나 이전 G6 증거로 PASS 주장 | G6은 자기 실행 결과만 쓴다. 원장 밖 결과 파일은 증거가 아니다(T07과 같은 방식으로 시험) |
| 통합 테스트를 지우거나 이름을 바꿔 범위를 줄임 | G3.NO_SILENT_REMOVAL, G5.NO_WEAKENING(파일 변경 정당화), G6.NO_WEAKENING(ID 유지) |
| IF를 지우고 단일 컴포넌트로 바꿔 N/A로 만들기 (G6이 `misconfigured`로 막힌 뒤 포함) | architecture 변경 → G2부터 재리뷰, N/A는 G2·G3 리뷰 확인 + 이전 G2 PASS에 있던 IF의 `removed_ids` 정당화 필요(REQ-15 (e)), G6.NO_WEAKENING도 같은 IF 규칙. 결함은 N/A로 닫히지 않음(REQ-24) |
| 통합 테스트가 provider를 목으로 대체 | 기계로는 patch 탐지 경고. G4 리뷰가 IF별로 `ok`를 기록해야 G4 PASSED. 판단 자체는 AI 몫(한계 §10) |
| 테스트 코드가 결과 보고를 조작 | G4.TEST_INTEGRITY(통합 테스트 파일 포함, 휴리스틱). 같은 프로세스 한계는 G5와 같다(SPEC §5.7) |

### 4.5 G5/G6 책임 분리 (G5 변경)
- `integration_test`가 없을 때: `eval_g5`의 체크 목록·판정·기록 키는 0.1.5와 같다(불변식 C1). status·report는 G5 기록의 `executed_tests`와 현재 tests.json 수준을 대조해 "unit 명령이 integration 테스트 TEST-xxx를 실행함: 이 결과는 G6 증거가 아님. 분리하려면 사용자에게 integration_test 설정을 요청" 경고를 파생한다(원장·판정 무관).
- `integration_test`가 있을 때: 체크 `G5.SCOPE`를 `G5.TEST_MAPPING` 뒤에 추가한다. integration 수준 ID가 G5 실행에 있으면 fail, system 수준은 warn. `G5.NO_WEAKENING`의 사라진 ID 판단에서 지금 integration 수준인 ID만 뺀다(REQ-G6-07).
- G5.REQ_COVERAGE는 바꾸지 않는다. 분리 후 G5 실행에는 unit 테스트만 있지만, G3.DESIGN_COVERAGE(모든 functional REQ → 설계 단위)와 G3.UNIT_TESTS(모든 설계 단위 → unit 명세)가 unit 경로의 REQ 커버리지를 보장한다(`tests_for_req`가 DESIGN 경유 연결을 센다. 독립 검토 확인).
- 실행부 분리 `_execute_suite`: 현재 `eval_g5`의 실행·증거·JUnit·EXECUTION/RESULTS 체크 생성을 그대로 옮기고 체크 ID 접두사와 증거 `kind`만 인자로 받는다. 분리 전후 G5 기록의 투영(상태·체크 ID와 상태값·실패 서명·executed_tests)과 증거 record.json의 키 집합이 같은지를 C1과 별도 테스트로 확인한다.

### 4.6 G4 변경과 정적 도달
- G4.TEST_CODE: `missing`을 `unit_tests() + integration_tests()`로 계산한다. items 문자열 형식은 그대로 두고(실패 서명 유지) 요약 문구에만 수준별 개수를 쓴다.
- G4.INTERFACE_IMPLEMENTED: REQ-G6-10.
- G4.INTEGRATION_WIRING: REQ-G6-11. 정적 도달 알고리즘(Python 전용, 설정 `language: python`과 같은 범위):
  1. 모듈 색인: 설정된 source 파일마다 "`__init__.py`가 없는 가장 깊은 상위 디렉터리"를 패키지 루트로 보고, 그 아래 경로의 점 표기를 모듈 이름으로 한다(`src/textstats/tokenizer.py` → `textstats.tokenizer`).
  2. import 그래프: 소스 모듈 사이의 `import`/`from … import`(상대 import 포함)를 해석한다. 색인에 없는 모듈은 무시한다.
  3. 함수 단위 시작점: 테스트 함수 본문이 참조하는 이름(`Name`, `Attribute`의 기준 이름)을 테스트 파일의 import 표로 소스 모듈에 연결한다. 같은 파일의 도우미 함수 호출과, 매개변수 이름으로 요청한 pytest fixture(같은 파일 또는 테스트 경로의 `conftest.py`)의 본문도 깊이 3까지 따라간다.
  4. 도달 집합 = 시작 모듈들의 import 폐포. provider 컴포넌트의 설계 단위 모듈 중 하나가 들어 있으면 provider 도달, consumer도 같다.
  5. patch 탐지: 같은 함수(와 따라간 fixture)의 `patch("…")`·`patch.object(X, …)`·`monkeypatch.setattr(…)` 대상 문자열이나 이름이 provider 모듈을 가리키면 warn.
  - 하위 프로세스(CLI) 실행, 동적 import, 진입점으로만 provider에 닿는 테스트는 도달로 인정되지 않는다. IF 수준 통합 테스트는 provider·consumer API를 프로세스 안에서 직접 호출해야 한다는 규칙으로 정한다(CLI 종단 시험은 G7 system 수준). test-designer·implementer 지침에 적는다. 강도는 §9 5번.
- G4.REVIEW: REQ-G6-12. verifier 지침의 G4 체크리스트에 IF별 항목: provider·consumer 실제 연결, 검증 대상 IF를 목으로 대체하지 않음, IF가 선언한 오류 경로, `provider_symbols`, INTEGRATION_WIRING 경고마다 판단, `integration_test` 명령이 통합 테스트를 대상으로 하는지(config 읽기).
- IF 0·integration 명세 0 WI: 새 체크는 기록에 추가되지 않고 TEST_CODE 결과도 같으므로 G4 기록이 0.1.5와 같다(REQ-G6-13, 불변식 C1).

### 4.7 Test Runner Evidence
`runner.write_evidence(kind="integration_test")`. 파일: `stdout.bin`, `stderr.bin`, `junit.xml`, `record.json`(서명). record.json의 G5 공통 항목(명령, 실행 파일 경로·버전·sha256, 런타임, 시작·종료 시각, 종료 코드, stdout/stderr 해시, 시간 초과 여부, Git HEAD·dirty, manifest 해시, Core 해시, 환경 정리 내역, 설치 패키지 목록, 검증 대상 파일 해시)에 더해:
- `command_source: "integration_test"`, `config_sha256`(config.json), `integration_test_sha256`(그 객체의 정규 JSON 해시)
- `junit_summary`, `junit_error`

원장 G6 gate 기록의 추가 키:
- `applicability`, `applicability_basis`(§4.2)
- `executed_tests`(실행된 모든 TEST ID → 최악 상태), `executed_levels`(ID → 수준), `unmapped_cases`(50개까지)
- `test_files`(테스트 루트 아래 파일 해시, G5와 같은 정의)
- `integration_test_functions`(integration ID → `파일::함수`, 평가 시점 AST 색인)
- `interfaces`: `[{"id", "provider", "consumers", "provider_modules", "consumer_modules", "tests": {TEST-ID: {"status", "reaches_provider", "reaches_consumer", "patched_provider"}}, "covered": bool}]`
- `basis_records`: 현재 G4·G5 PASS 기록 ID(이 G6이 기대는 상위 판정)
- `junit`, `failed_cases`

N/A 기록은 `evidence: []`, `executed_tests: {}`, `interfaces: []`이고 basis만 있다.

### 4.8 Interface ↔ Integration Test Traceability
- 사슬: IF(architecture) → integration TEST(`verifies`에 IF, G3) → 테스트 함수(이름에 ID 하나, G4.TEST_CODE) → 정적 도달(G4.INTEGRATION_WIRING, G6 재계산) → JUnit 케이스(G6.TEST_MAPPING) → IF 커버리지(G6.IF_COVERAGE) → 원장 기록 ID.
- `vmodel trace`: IF 행(IF → provider/consumers → TEST → 함수 → 도달 → 마지막 G6 결과와 기록 ID)과 역방향(TEST → IF)을 추가한다. 마지막 G6이 N/A면 "N/A (no interfaces)". REQ 행의 TEST 결과는 수준별로 가져온다(unit은 마지막 G5, integration은 마지막 required G6). 지금 코드는 G5만 본다(`status.trace_view`).
- G6.NO_WEAKENING: REQ-G6-23. 테스트 파일 변경 정당화는 같은 manifest에서 먼저 통과한 G5.NO_WEAKENING이 이미 요구하므로 G6에서 다시 하지 않는다.
- 결함 추적: DEFECT `related`에 IF·TEST를 연결한다(스키마가 이미 IF 허용). `TEST_EXECUTING_GATES`에 G6을 넣고 `citation_view`의 TEST_MAPPING 체크 ID를 인용 기록의 Gate로 고른다. 그래야 G6 "not executed"가 UNKNOWN으로 분류된다.

### 4.9 무효화(STALE)
- G6 manifest(REQ-G6-22)는 gates.json 선언으로만 정한다. 코드·설정·산출물 변경 → G4·G5·G6 STALE. `reviews/G2.json`·`reviews/G3.json` 변경 → G6만 STALE(G3~G5 manifest에는 리뷰 파일이 없다. N/A 근거가 리뷰에 있으므로 G6은 리뷰 교체를 따라간다). 인터페이스 변경(architecture.json) → G2부터 전부 STALE. Core 변경 → 전부 STALE.
- G6은 G1~G5의 manifest에 아무것도 더하지 않는다. 0.1.5와 새 버전이 같은 프로젝트에서 G1~G5 manifest를 같게 계산하는지 불변식 C2로 확인한다.

### 4.10 Integration Failure 및 Rework
- G6 FAILED → 다음 평가 전에 그 기록 ID를 `found_in_records`에 둔 DEFECT 필요(D14). DEFECT `gate: "G6"`, `root_cause_phase`: P2(IF 계약·컴포넌트 경계), P3(단위 설계·통합 명세), P4(코드·테스트 코드·테스트 배치·정적 도달 부족), P6(통합 실행 환경: 테스트 데이터·외부 의존 준비 등. 설정 변경이 필요하면 사용자 조치).
- 원인 단계로 돌아가 고치면 manifest가 바뀌어 하위 Gate가 STALE → 위에서부터 재평가. P2 수정은 G2 재리뷰부터.
- 3회 동일 실패 → BLOCKED, 사용자 `vmodel unblock`(TTY). `misconfigured`·`tool_unavailable`·`applicability_unconfirmed` BLOCKED는 중립 차단이라 DEFECT를 요구하지 않고 3회 카운트를 끊거나 늘리지 않는다.
- 표시 상태(D37): 결함이 인용한 Gate가 G6이면 그 Gate의 평가로 OPEN·FIX_APPLIED·REVERIFY_REQUIRED·VERIFICATION_FAILED·CLOSED·UNKNOWN을 같은 규칙으로 계산하되, N/A 기록은 PASS로 치지 않는다(REQ-G6-24). G6이 STALE이면 CLOSED가 아니다.
- next_action(차단 사유별): `misconfigured` → "사용자에게 `.vmodel/config.json`의 integration_test 추가·수정을 요청(에이전트 수정 불가)", `applicability_unconfirmed` → "verifier가 G2·G3 리뷰에 integration_applicability를 기록(필요하면 removed_ids 정당화), 또는 IF/통합 명세 추가", `tool_unavailable` → 사용자 보고, 3회 실패 → 사용자 보고.

### 4.11 기존 프로젝트 마이그레이션
업그레이드는 지금처럼 새 릴리스의 `vmodel lock --accept-current`(TTY) 한 번이다(D38). 그 뒤 WI 종류별 절차:

| 경우 | 업그레이드 직후 | 해야 할 일 | AI 리뷰 비용 |
|---|---|---|---|
| A. IF 0·integration 명세 0 (지금까지 실제 산출물 4건 전부) | G1~G5 STALE(Core), G6 평가 전 → WI IN_PROGRESS. status가 적용 판단을 미리 계산해 "G2·G3 리뷰 확인 필요"를 next_action으로 보인다(쓸모없는 BLOCKED 기록을 만들지 않게) | G1~G3 재평가(리뷰 재작성 불필요), G4 재리뷰(아래 주의), G5 재실행, verifier가 G2·G3 리뷰에 `integration_applicability`를 써서 다시 제출 → G2·G3 재평가(G3~G5 PASSED 유지, 독립 검토가 `gate_state`로 확인) → G6 N/A | G4 1회 + G2·G3 각 1회 |
| B. IF 있음, 통합 테스트가 unit 명령에 섞여 있음 (하네스 wordfreq 형태) | 같음 | **먼저** 사용자가 config에 `integration_test`를 넣고 `unit_test`에서 통합 테스트를 빼며, 테스트 파일을 옮기면 CR에 `test_changes`(사유: G5/G6 분리, `since_record` = 마지막 0.1.5 G5 PASS)를 쓴다 → G4 재리뷰(IF별 `interfaces` 포함) → G5(SCOPE 적용) → G6 | G4 1회 |
| C. IF 있음, 통합 테스트 코드 없음 또는 provider에 닿지 않음 | 같음 | G4 FAILED(TEST_CODE 또는 INTEGRATION_WIRING) → DEFECT(P4) → 통합 테스트 작성 → B와 같음 | G4 1회 이상 |
| D. IF 0이지만 integration 명세 있음 | 같음 | `required`. B와 같음 | G4 1회 |

- 주의(0.1.5에서 확인한 사실, TEST_RESULTS §13.4): 업그레이드가 `.claude/settings.json`의 DevKit 규칙을 옮기므로, 이 파일이 들어 있는 G4 코드 manifest가 바뀌어 **G4 리뷰는 업그레이드마다 다시 받아야 한다.** 새 버전 업그레이드도 같다(§9 4번).
- B에서 config 수정과 CR 작성을 G4 재리뷰보다 먼저 해야 리뷰가 한 번으로 끝난다(config·change-requests.json도 G4 manifest에 있다). 마이그레이션 안내(README·업그레이드 출력·SessionStart 문구)에 이 순서를 적는다.
- B의 G5.NO_WEAKENING: 이전 G5 기록에서 실행된 integration ID가 G5에서 사라지는 것은 REQ-G6-07에 따라 약화가 아니다. 옮긴 파일의 변경 정당화(`test_changes`)는 지금 규칙 그대로 필요하다.
- 하위 호환: 새 버전은 0.1.x config(키 없음)를 그대로 읽는다. 0.1.5 이하 Validator는 config·리뷰의 새 키를 무시한다(스키마가 추가 키를 막지 않음, 독립 검토 확인). 다운그레이드는 지금처럼 수동 절차(D38 한계)이고, 0.1.5로 내리면 G6 기록은 "미구현 Gate"로만 보이며, defects·CR에 G6·P6·IF `removed_ids`를 쓴 WI는 0.1.5의 G1·G3 스키마 검사에서 실패한다.

### 4.12 기존 검증 증거와의 호환성
- 원장 기록 형식(서명·체인·head·앵커)은 바뀌지 않는다. G6 gate 기록은 기존 `type: gate` 형식에 키를 더한 것이다. 기존 기록·증거 파일은 읽기만 하고 다시 쓰지 않는다.
- 0.1.5가 서명한 원장·G5 증거는 새 버전의 audit·verify-evidence를 통과하고, 기록의 `validator.version`·`core_hash`는 0.1.5 값으로 남는다(테스트 C3).
- G1~G5 PASS 기록은 원장에 남는다. 현재 상태가 STALE이 되는 것은 Core 교체 때문이며(§1.1), 재평가는 새 기록을 더한다. 판정이 바뀌는 범위는 §1.2.
- status JSON: 기존 키는 모두 남는다. 추가 키는 Gate별 `applicability`, `not_evaluated`, WI별 `gate_summary`(`passed_current`, `na`, `not_evaluated`, `stale`, `failed`, `blocked`, `not_implemented`), `scope_warnings`, `g6_applicability_preview`. `mvp_note` 문구는 바뀐다. `vmodel gate` JSON(`GateRun.as_dict`)에 `applicability`를 더한다.
- 결함 표시: `closure_state` 값과 규칙은 그대로이고, G6 기록이 대상 Gate에 더해지며 N/A 기록은 검증으로 치지 않는다.

### 4.13 WI 상태와 표시 (결정 4)
- 파생 규칙 `wi_status`는 바꾸지 않는다. 입력(구현된 Gate 목록)에 G6이 더해진다. G6 기록이 없으면 G6은 IN_PROGRESS(G5 PASSED 뒤)라서 WI는 IN_PROGRESS다(독립 검토 확인).
- G6 미평가: status 텍스트 `G6 IN_PROGRESS  not evaluated yet: no integration verification has run`, JSON `not_evaluated: true`. N/A: `G6 N/A  (recorded PASSED R…, no integration tests executed: <reason>; external endpoints reviewed: …)`. required PASS: `G6 PASSED  R…  IF 2/2 covered (static reach + passed), 3 integration tests passed`. `vmodel gate`·`verify` 출력(`render_gate`)도 같은 구분을 쓴다.
- WI 줄은 WI 상태와 Gate 결과를 나눠 쓴다: `WI-001 IN_PROGRESS — gates: G1-G5 PASSED (current), G6 not evaluated, G7 not implemented`. report의 요약 절도 같은 구분을 쓴다.
- next_action: G6 평가 전이면 적용 판단 미리보기에 따라 "run 'vmodel gate WI G6'", "integration_test 설정 필요(사용자)", "G2·G3 리뷰에 integration_applicability 필요(verifier)" 중 하나. G7 미구현 문구는 "G1-G6 verified (G6 N/A면 'G6 N/A'). G7 is an extension gate; report PARTIALLY_VERIFIED"로 바꾼다.
- MVP_NOTE는 "G1-G6 implemented; G7 (system) is an extension gate"로 바꾼다.

## 5. gates.json G6 항목 (구현 시 쓸 정의)
```json
{"id": "G6", "phase": "P6", "name": "Integration Verification", "implemented": true,
 "inputs": ["G5 manifest (architecture interfaces, tests spec, source, test code, config)", "reviews/G2.json, reviews/G3.json (N/A confirmation)"],
 "outputs": ["integration test execution evidence (stdout/stderr/junit, hashes, environment, interface reach) or a recorded N/A decision"],
 "agents": {"author": "validator (executes the configured integration_test command itself)",
            "reviewer": "none (mechanical); interface wiring and integration test adequacy are reviewed at G4, N/A reasons at G2/G3"},
 "required_artifacts": ["architecture.json", "tests.json"],
 "manifest": {"artifacts": ["workitem.json", "requirements.json", "architecture.json", "design.json", "tests.json", "reviews/G2.json", "reviews/G3.json"], "code": true},
 "checks": ["G6.PREREQ", "G6.APPLICABILITY", "G6.CONFIG", "G6.EXECUTION", "G6.RESULTS", "G6.SCOPE", "G6.TEST_MAPPING", "G6.IF_COVERAGE", "G6.NO_WEAKENING", "G6.INPUTS_UNCHANGED"],
 "pass_criteria": "required: every check passes on this run's own evidence and the validator's own static reach analysis; not_applicable: only when all N/A conditions are confirmed (recorded PASSED with applicability=not_applicable, no execution claimed, never counted as defect verification); unconfirmed applicability or missing/invalid integration_test -> BLOCKED"}
```
(체크는 실제 파일에서 다른 Gate처럼 `{id, kind, desc}` 객체로 쓴다. kind: PREREQ·APPLICABILITY·CONFIG·SCOPE·TEST_MAPPING·IF_COVERAGE·NO_WEAKENING·INPUTS_UNCHANGED는 mechanical, EXECUTION·RESULTS는 execution. ai_review 없음.)

## 6. 테스트 명세 (구현 전 고정, RED → GREEN)

규칙은 0.1.4·0.1.5와 같다. 클래스 접미사: `Red`(불변 0.1.5 릴리스에서 assertion으로 실패해야 함), `Char`·`Invariant`(둘 다 통과), `Accept`(새 코어에서만). RED 대상은 `dist/vmodel-0.1.5`(core `37071459…`, 기록과 43개 파일 일치)이며 `scripts/red_green.py --mode red --plugin dist/vmodel-0.1.5`로 판정한다. 0.1.5는 G6 요청에 기록 없이 BLOCKED("extension gate … not implemented")를 돌려준다(독립 검토 확인). Red 테스트는 이 응답을 받아 **목표 assertion**에서 실패해야 한다. red_green은 helper·setUp 안의 assert 실패도 FAIL로 세므로, Red의 목표 assertion 메시지에 `RED-TARGET` 표지를 넣고 RED 로그에서 모든 Red 실패가 그 표지로 끝나는지 확인한다.

### 6.1 기존 테스트 225개
G6 구현은 결정 4 자체로 일부 기존 기대값을 바꾼다(G6이 NOT_IMPLEMENTED가 아니고, G1~G5만 통과한 WI가 PARTIALLY_VERIFIED가 아님). "무수정 통과"가 아니라 아래 목록만 의도적으로 바꾸고 나머지는 그대로 통과시킨다. 바꿀 때마다 같은 테스트의 0.1.5 기대값을 주석으로 남기고, 바뀐 이유를 REQ ID로 적는다.
- `test_gates.py` 32~35·43행(G5 뒤 WI 상태·G6 상태·verify 결과 수), `mvp_note` 문구 → REQ-25.
- `test_rework_flow.py` 47·65행, `test_defect_evidence.py` 126·130행, `test_defect_closure.py` 219행(PARTIALLY_VERIFIED, G6 NOT_IMPLEMENTED) → REQ-25. 픽스처가 G6까지 가도록 바꾸지 않고 기대값을 IN_PROGRESS + `gate_summary`로 바꾼다.
- `test_version_compat.py`: 투영에서 G6 기록을 빼고, wordfreq 이력의 G4 차이는 C5로 옮긴다.
- `helpers.Sandbox.review()`: IF가 있는 WI의 G4 리뷰에 `interfaces`(IF별 `ok`, `provider_symbols`)를 쓴다. 0.1.5는 이 키를 무시하므로 0.1.5 대상 실행 결과가 바뀌지 않는다(구현 전 0.1.5 대상 하네스로 먼저 확인).
- 구현 세션 첫 단계에서 위 목록을 grep(`PARTIALLY_VERIFIED`, `NOT_IMPLEMENTED`, `G1-G5`, `mvp_note`)으로 다시 만들고, 목록 밖 테스트가 실패하면 회귀로 본다.

### 6.2 새 픽스처
- `tests/fixtures/pipeline`: 컴포넌트 2개(파서 ARCH-001, 집계기 ARCH-002), IF-001(parse, provider ARCH-001 → consumer ARCH-002), IF-002(report, provider ARCH-002 → `EXTERNAL`), unit 명세와 integration 명세 3개, 통합 테스트는 `tests/integration/`(consumer API를 직접 호출). config는 분리 명령.
- `tests/fixtures/single`: 컴포넌트 1개, IF 0, integration 명세 0, `data_flows`에 외부 끝점 2개(실제 세션 산출물과 같은 형태).
- 기존 `wordfreq`(통합 테스트가 단위 파일에 섞임, `test_TEST_010`이 consumer `count_words`를 호출)는 마이그레이션 B 시나리오에 쓴다.

### 6.3 새 모듈

| 모듈 | 클래스 | 테스트 (요구사항) |
|---|---|---|
| `test_g6_config.py` | Red | A1 `integration_test` 없음 + IF 있음 → G6 BLOCKED `misconfigured`, 증거 없음, unit 명령 미실행(REQ-02). A2 `{junit}` 없음 → BLOCKED. A3 `argv`가 문자열·`timeout_s` 없음 → BLOCKED `misconfigured`, 크래시 없음(REQ-01b). A4 next_action이 사용자 조치 안내(REQ-02a) |
| | Char | A5 0.1.5 config(키 없음)가 스키마를 통과(REQ-01a) |
| `test_g6_gate.py` | Red | B1 pipeline 정상 → G6 PASSED, 증거 kind `integration_test`, record에 명령·종료 코드·해시·IF별 도달(REQ-19,20). B2 통합 테스트 실패 → FAILED, `failed_cases`. B3 skip → FAILED(TEST_MAPPING). B4 integration ID 미실행 → FAILED. B5 IF-002 테스트 제거(명세 유지) → FAILED. B6 통합 명령이 unit 테스트 실행 → FAILED(SCOPE, REQ-08). B6b 다른 WI의 unit 테스트 실행 → FAILED(프로젝트 전체 수준표). B7 종료 0인데 0 tests → FAILED. B8 종료 0인데 junit 없음 → FAILED. B9 시간 초과 → FAILED, 시작 실패 → BLOCKED `tool_unavailable`. B10 실행 중 소스 변경 → FAILED(INPUTS_UNCHANGED). B11 G5 STALE → 기록 없이 BLOCKED이고 사유가 "G5 must be PASSED"(0.1.5의 "not implemented" 사유와 구분). B12 가짜 G6 증거·결과 파일·status 파일 주입 → PASS로 인정 안 됨(T07 방식). B13 환경 정리(에이전트 `PYTEST_ADDOPTS` 등 무시)가 G5와 같음. B14 gates.json G6 reviewer가 "none (mechanical)"로 시작하고 G6 체크에 `ai_review` kind 없음(REQ-18, 0.1.5는 "vmodel:verifier"라 Red). B15 `assert True`만 있는 `test_TEST_0xx` → G6 FAILED(IF_COVERAGE: no reach)(REQ-19) |
| `test_g6_applicability.py` | Red | C-a single + G2·G3 리뷰 확인 → PASSED `applicability: not_applicable`, 증거 없음, `vmodel gate` 출력·status·report·trace·next_action이 "N/A"이고 "integration tests passed"·"G1-G5 verified" 문구 없음(REQ-15,17). C-b G2 확인만 → BLOCKED `applicability_unconfirmed`(REQ-16). C-c G3 확인만 → 같음. C-d `reason` 빈 문자열 → 같음. C-e 리뷰 파일이 PASS 기록의 리뷰와 다름(제출 안 한 수정본) → 같음. C-f IF 0 + integration 명세 1 → `required`(REQ-14). C-g `data_flows`에 다른 ARCH ID → BLOCKED(조건 c). C-g2 외부 끝점을 `endpoints_reviewed`에서 뺌 → BLOCKED. C-h N/A 뒤 G2 리뷰 교체 → G6 STALE(REQ-22). C-i N/A 뒤 IF 추가(G2부터 재평가) → `required`. C-j 리뷰 경로 검증: G2·G3 리뷰만 다시 제출·재평가해도 G3~G5가 PASSED로 남음 |
| `test_g6_scope.py` | Red | D1 분리 config에서 unit 명령이 integration 테스트 실행 → G5 FAILED(G5.SCOPE, REQ-05). D2 분리 config에서 이전 G5에 있던 integration ID가 G5에서 사라짐 → NO_WEAKENING 통과(REQ-07). D3 기존 config + 섞인 실행 → status·report에 범위 경고(REQ-06) |
| | Char | D5 분리 config에서 unit TEST를 system 수준으로 바꾸거나 지움(removed_ids 없음) → G5.NO_WEAKENING fail(0.1.5와 같은 결과, REQ-07의 경계) |
| | Invariant | D4 기존 config wordfreq 이력(G4 리뷰는 `interfaces` 포함 helper로 작성)의 G5 기록 투영(상태·체크 ID·상태값·실패 서명·executed_tests)이 0.1.5와 같음(REQ-06) |
| `test_g6_g4.py` | Red | E1 integration 함수 없음 → G4 FAILED(TEST_CODE, REQ-09), items 문자열 형식은 unit 누락과 같음. E2 IF signature 심볼이 provider에 없음 → FAILED(INTERFACE_IMPLEMENTED, REQ-10). E3 통합 테스트가 provider에 닿지 않음 → FAILED(INTEGRATION_WIRING), fixture·도우미 경유 도달은 인정, provider patch → warn(REQ-11). E4 IF 있는데 리뷰 `interfaces` 누락·`provider_symbols`가 없는 심볼 → REVIEW_REQUIRED, `issue` → FAILED(REQ-12) |
| | Invariant | E5 single 이력의 G4 기록 투영이 0.1.5와 같음(REQ-13) |
| `test_g6_rework.py` | Red | F1 G6 FAILED → DEFECT 없으면 재평가 BLOCKED → DEFECT(`gate: G6`, P4) → 수정 → PASSED, 결함 CLOSED(REQ-21). F2 같은 실패 3회 → BLOCKED, unblock(pty). F3 G6 실패(일부 integration ID "not executed") 인용 결함 → 실패 TEST와 UNKNOWN을 나눠 표시(`citation_view`). F4 이전 G2 PASS에 있던 IF를 `removed_ids` 없이 지움 → N/A 불가(BLOCKED)·required면 NO_WEAKENING fail. CR에 `removed_ids: ["IF-001"]` → 스키마 통과, 정당화 인정(REQ-15e, 23). F5 `misconfigured` BLOCKED 기록만 있고 실행 기록이 없을 때 NO_WEAKENING 기준이 생기지 않음, 이후 IF 삭제는 여전히 정당화 필요(독립 검토 반례). F6 G6 FAILED 결함 뒤 범위를 지워 N/A PASS → 결함이 CLOSED가 아니고 "G6 now N/A … not verified" 표시(REQ-24). F7 `misconfigured` BLOCKED가 3회 카운트를 바꾸지 않음 |
| `test_g6_status.py` | Red | G1 G1~G5 PASSED·G6 기록 없음 → WI IN_PROGRESS, G6 `not_evaluated`, `gate_summary`에 G1~G5 `passed_current`(REQ-25). G2 required PASS → PARTIALLY_VERIFIED, 텍스트 IF 커버리지. G3 N/A → PARTIALLY_VERIFIED, N/A 문구. G4 `vmodel verify`가 G1~G6. G5 `mvp_note`·next_action 문구. G6 trace IF 행, REQ 행의 integration 결과가 G6에서 옴. G7 적용 판단 미리보기에 따른 next_action 3종 |
| `test_g6_compat.py` | Invariant | C1 같은 이력(single 전 Gate, wordfreq는 G1~G3·G5)에서 G1~G5 원장 투영이 0.1.5와 같음(G6 기록 제외). C2 같은 프로젝트에서 G1~G5 manifest 해시가 0.1.5와 같음(REQ-26) |
| | Accept | C3 0.1.5가 서명한 원장·G5 증거가 audit·verify-evidence 통과, 기록 버전·해시 유지. C4 0.1.5 설치 프로젝트 → 새 버전 재고정(pty) → 이전 기록 바이트 유지, G1~G3 리뷰 재작성 없이 PASSED, G4는 settings 변경으로 재리뷰 필요(현재 사실 고정), G6 평가 전 IN_PROGRESS. C5 wordfreq 기존 config의 G4 차이 목록(새 체크 2개, REVIEW의 `interfaces` 요구) 외에는 G4 투영이 0.1.5와 같음. C6 `_execute_suite` 분리 전후 G5 증거 record.json 키 집합 동일 |

- Windows(cp949, 한글·공백 경로): pty가 필요 없는 위 테스트 전부. G6 증거의 비 UTF-8 출력(CP949 바이트) 처리 1건 추가.
- 하네스 밖 확인: 릴리스 사본으로 0.1.5 → 새 버전 업그레이드 재현(모델 호출 없음, `test-results/<ver>/`), `claude plugin validate --strict`.
- E2E(실제 Claude 세션, 비용 승인 후, M7): pipeline 형태 새 샘플로 `/vmodel:start`부터 G6 PASS까지 1회, G6 실패에서 시작하는 재작업 1회, 단일 컴포넌트 샘플로 N/A 경로 1회. 세션 수·상한은 그때 승인받는다.

## 7. 구현 계획 (V-Model 절차)

| 단계 | 내용 | 완료 기준 |
|---|---|---|
| 0 | 브랜치 `g6-dev`(태그 `v0.1.5`에서). `docs/g6/WORKITEM.md` 생성(이 문서 §2·§4·§6을 작업 항목 형식으로 옮기고 §9 결정 반영) | 문서 커밋 |
| 1 요구사항 | §2 확정(§9 결정 반영) | 사용자 결정 기록 |
| 2 아키텍처 | §3 변경 범위 확정, gates.json 정의 §5 | 문서 |
| 3 상세 설계 | §4 함수 단위 설계 | 문서 |
| 4 테스트 설계 | §6 테스트 코드 작성(구현 전), 픽스처 2개, §6.1 기존 테스트 변경 목록 재생성 | 테스트 파일 커밋 |
| 5 RED | `red_green.py --mode red --plugin dist/vmodel-0.1.5` | Red 전부 `RED-TARGET` assertion 실패, Char·Invariant 통과, 로그 보존 |
| 6 구현 | 순서: 스키마 → gates.json → `_execute_suite` 분리(C1·C6 먼저 GREEN) → G5.SCOPE·NO_WEAKENING → 정적 도달 → G4 체크·리뷰 → `g6_applicability` → `eval_g6` → 결함 추적(N/A 제외, `citation_view`)·NEUTRAL_BLOCKS → status·report·trace·render_gate → 스킬·에이전트·VMODEL.md → init 기본값 → 버전 | 단계마다 해당 모듈 GREEN |
| 7 GREEN | 새 모듈 전부 + 기존 225개(§6.1 목록만 의도 변경) 통과 | 로그, 변경 목록 |
| 8 독립 검토 | 별도 컨텍스트 읽기 전용 검토자(직접 만든 detached worktree). 지적은 그 빌드에서 실패하는 테스트로 먼저 고정한 뒤 수정, 재검토 | 처리표 |
| 9 회귀 | 깨끗한 worktree WSL 전체, Windows cp949 전체, 릴리스 빌드·기록, 0.1.5→새 버전 업그레이드 재현, plugin validate | TEST_RESULTS 절 |
| 10 E2E | 실제 세션(비용 승인 후) | TEST_RESULTS 절 |
| 11 확정 | 사용자 결정(병합·태그) | — |

DevKit 자체는 DevKit Validator로 승인하지 않는다(SPEC §5.8). 판정은 독립 하네스와 독립 검토가 한다.

## 8. 구현 범위 밖 (이번 설계에서 다루지 않음)
G7(System), LITE/STRICT 프로파일, IF의 consumer별 테스트 요구(STRICT 후보), 실행 중 모듈 로드 기록 같은 런타임 연결 증거(STRICT 후보), G2 판정에 IF 삭제 정당화 넣기(지금은 G6에서만 요구, G1~G5 판정 불변을 위해), CI 독립 재검증, 사용자 결정 결속, WorkMind 적용.

## 9. 구현 전 사용자 결정이 필요한 것
1. §1.1 해석 확인: G6 추가 자체는 G1~G5를 STALE로 만들지 않지만, 업그레이드(Core 교체) 시의 기존 STALE 규칙은 유지한다. 이대로 진행할지.
2. N/A 리뷰 확인을 G2와 G3 **둘 다** 요구(설계 기본값)할지, G2만 요구할지. 둘 다면 기존 IF 0 WI 마이그레이션에 verifier 리뷰가 1회 더 든다.
3. 새 `init` 기본값으로 분리 명령(unit은 `tests/integration` 제외, integration은 그 폴더)을 써 둘지(설계 기본값), 사용자가 옵션으로 줄 때만 쓸지.
4. 업그레이드마다 G4 재리뷰가 필요한 문제(0.1.5에서 확인, `.claude/settings.json`이 G4 코드 manifest에 포함): 그대로 둘지, `.claude/settings.json`·`.claude/settings.local.json`을 코드 manifest에서 뺄지. 빼더라도 그 변경을 담은 버전으로 올라가는 업그레이드 자체에서는 manifest 구성이 바뀌어 G4 재리뷰가 한 번 더 필요하고, 효과는 그다음 업그레이드부터다. 또 G1~G5 manifest가 바뀌므로 REQ-26·C2를 그 범위에서 고쳐야 한다. 두 파일은 Validator의 테스트 실행에 영향이 없다(정리된 환경으로 직접 실행).
5. 정적 도달의 강도: 설계 기본값은 **실패**(IF마다 provider에 닿는 통합 테스트 필요, 하위 프로세스·동적 import 테스트는 인정 안 함 → IF 수준 통합 테스트는 프로세스 안 직접 호출로 작성). 대안은 경고 + G4 리뷰의 명시적 사유인데, 그러면 IF 커버리지가 AI 판단에만 기대게 되어 결정 2와 충돌한다.
6. 버전 번호: Gate 의미가 바뀌므로 0.2.0(PLAN 제안).
7. G6 실패 결함의 범위를 CR로 지워 G6이 N/A가 된 경우의 종료 표시: 설계 기본값은 CLOSED가 아니라 기존 상태(FIX_APPLIED/OPEN) + "scope removed, not verified" 주석(D37 6종 유지). 이 경우를 닫힌 것으로 볼 별도 상태를 원하면 D37 상태 정의를 바꾸는 결정이 필요하다.
8. E2E 실제 세션 횟수·비용 상한(구현 후).

## 10. 남은 위험
- "목으로 대체하지 않음"은 정적 경고 + AI 리뷰 판단이다. 기계 검증이 아니다(SPEC §5.7). 런타임 증거는 STRICT 후보로 남긴다.
- 정적 도달은 Python 전용 근사다. "provider 모듈이 import 폐포에 있다"는 것이 "그 IF 함수를 실제로 호출했다"는 증명은 아니다(예: 같은 모듈의 다른 함수만 호출). 이름만 맞는 빈 테스트는 막지만 의미 있는 검증인지는 G4 리뷰 몫이다.
- 단일 컴포넌트의 외부 의존(DB·네트워크)은 아키텍처에 IF로 표현되지 않으면 N/A가 될 수 있다. `data_flows` 외부 끝점의 리뷰 확인(`endpoints_reviewed`)으로 좁혔지만 `data_flows`에 아예 적지 않은 의존은 리뷰 판단에 기댄다.
- 테스트 코드는 러너와 같은 프로세스에서 돈다(G4.TEST_INTEGRITY 휴리스틱 한계, 통합 테스트도 같음).
- 실제 세션 산출물에 IF가 있던 적이 없다. 실제 G6 경로는 M7 E2E 전까지 하네스로만 확인된다.
- 업그레이드마다 G4 재리뷰 비용(§9 4번)이 결정 전까지 남는다.

## 11. 독립 검토 반영 (2026-11-09, 설계 1회차)
별도 컨텍스트의 검토자가 `v0.1.5` 코드와 이 문서 초안을 읽기 전용으로 대조했다. 주요 6, 부 8, nit 8. 아래 주요·부 지적은 코드에서 직접 확인한 뒤 반영했다(테스트 기대값 위치 `test_gates.py:32-43`, CR `removed_ids` 패턴 `^(REQ|DESIGN|TEST)`, `citation_view`의 `"G5.TEST_MAPPING"` 고정, `defect_trace`의 `verified_by`가 모든 PASS를 셈).

| 지적 | 처리 |
|---|---|
| M1 기존 225개 "무수정 통과"는 결정 4와 모순(G6 NOT_IMPLEMENTED·PARTIALLY_VERIFIED 기대 테스트, helper 리뷰에 `interfaces` 없음) | §6.1 의도된 기대값 변경 목록, helper 변경과 0.1.5 무영향 확인 절차 |
| M2 IF 삭제로 N/A 만들기가 막히지 않음(`misconfigured` 기록이 빈 기준, 커버되지 않은 IF 미보호, G2에 IF 삭제 검사 없음, CR 스키마에 IF 없음) | REQ-15 (e)(이전 G2 PASS `item_hashes`의 IF는 `removed_ids` 필요), REQ-23 기준을 실행 기록으로, CR 스키마에 IF, 테스트 F4·F5 |
| M3 G6의 IF↔테스트 연결이 이름 매칭뿐, 연결은 G4 경고뿐 | 함수 단위 정적 도달을 G4에서 fail, G6이 다시 계산해 IF_COVERAGE 조건으로(REQ-11, 19, §4.6), 테스트 B15·E3, 강도는 §9 5번 |
| M4 N/A PASS가 G6 결함의 `verified_by`가 됨 | REQ-24(N/A는 검증 아님), 테스트 F6, 종료 표시 §9 7번 |
| M5 호환 주장이 요구사항과 모순 | §1.2 판정 변경 범위 명시, REQ-26 문구, C1 이력 지정·G6 기록 제외, C5 |
| M6 REQ-07이 G5.NO_WEAKENING을 약화 | 지금 integration 수준인 ID만 제외, 테스트 D5 |
| m1 `citation_view` 고정 문자열 | §4.8, 테스트 F3 |
| m2 B14 Invariant 분류 오류, B11 0.1.5와 같은 결과, helper assert가 RED로 오인 | B14 Red, B11 사유 문구 비교, `RED-TARGET` 표지 |
| m3 config는 init에서만 스키마 검증 | REQ-01b G6.CONFIG 하위 스키마 검증, 테스트 A3 |
| m4 settings를 manifest에서 빼도 그 업그레이드에서는 재리뷰 필요, C2와 충돌 | §9 4번 문구 정정 |
| m5 N/A가 일반 PASS로 보이는 출력(`render_gate`, next_action 고정 문구, trace REQ 행) | REQ-17 범위 확대, §4.13, §4.8, 테스트 C-a·G5·G6 |
| m6 data_flow의 외부 끝점 무시 | `external_endpoints`와 리뷰 `endpoints_reviewed` 필수, 테스트 C-g2 |
| m7 INTERFACE_IMPLEMENTED가 signature 없으면 무의미 | REQ-10 범위 명시, 리뷰 `provider_symbols` 기계 확인(REQ-12) |
| m8 TEST_CODE items에 수준을 넣으면 실패 서명이 바뀜 | REQ-09 items 형식 유지 |
| nit: 절 번호, NEUTRAL_BLOCKS 기존 항목, 다운그레이드 시 스키마 실패, gates.json 설명 갱신 누락, 다른 WI의 TEST ID, 사례 A의 불필요한 BLOCKED 기록, "바이트 단위" 주장 | 모두 본문에 반영(§4.3, §4.11, §3.1, REQ-08, §4.13, §4.5·C6) |

검토자가 맞다고 확인한 것: 리뷰 파일은 G1~G5 manifest에 없음, G2·G3 리뷰 재제출 뒤 G3~G5 PASSED 유지(사례 A 경로와 비용), 사례 B의 순서와 `since_record`, 0.1.5의 G6 응답(기록 없는 BLOCKED), 스키마의 추가 키 허용, Core 변경 STALE과 gates.json의 Core 포함(§1.1 근거), `wi_status` 결과, REQ_COVERAGE 논거, 3회·중립 차단 처리, guard 보호 범위.
