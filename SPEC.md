# VModel DevKit — SPEC

버전: 0.1 (MVP 범위 확정본, 2026-11-08)
상태 표기: **[MVP]** = 이번에 구현·검증, **[EXT]** = 설계만 하고 확장 단계로 남김

## 1. 목적과 범위

Claude Code 위에서 ASPICE V-Model을 따르는 개발 절차(요구사항 → 설계 → 구현 → 독립 검증 → 결함 수정 → 재검증)를 강제하는 재사용 가능한 개발환경이다. ASPICE 인증이 목적이 아니다. "AI가 PASS라고 말했다"가 아니라 **독립 Validator가 직접 실행·판정한 증거**만 완료로 인정하는 것이 핵심이다.

- MVP = STANDARD 프로파일의 G1~G5 실행. G6~G7, LITE, STRICT는 [EXT].
- MVP 완료는 V-Model 전체 완료가 아니다. Work Item은 G1~G5를 통과해도 `PARTIALLY_VERIFIED`까지만 간다(§6.2).
- WorkMind는 이 MVP 이후 첫 적용 대상이며 지금은 건드리지 않는다.

## 2. 구성 요소

| 구성 요소 | 위치 | 역할 |
|---|---|---|
| Validator Core | `plugins/vmodel/validator/` | 표준 라이브러리만 쓰는 Python 3.11+ 프로그램. 스키마 검증, 추적성, 테스트 직접 실행, 증거 생성, 서명 원장, STALE 판정 |
| Gate 정의 | `validator/vmodel_validator/data/gates.json` | 7개 Gate의 입력·출력·담당·필수 산출물·체크·PASS 기준, 프로파일 표 (기계 판독) |
| 산출물 스키마 | `validator/vmodel_validator/data/schemas/*.schema.json` | 요구사항·아키텍처·설계·테스트·리뷰·결함·CR·설정 스키마 |
| Plugin | `plugins/vmodel/` | Skills(명령), Subagents(역할), Hooks(보호·세션 복원), `bin/vmodel` |
| 릴리스 | `dist/vmodel-<ver>/` + `releases/vmodel-<ver>.json` | 고정 버전 스냅샷과 파일별 해시 기록 |
| 부트스트랩 하네스 | `tests/` | Validator 자체를 검증하는 unittest 스위트 (Validator가 자기 자신을 승인하지 않도록 분리) |

## 3. V-Model 단계와 Gate

테스트 계획은 대응되는 설계 단계에서 미리 만든다 (G1 수용 기준 → G2 통합 전략 → G3 Unit/Integration/System 명세 → G5 실행).

| 단계 | 활동 | Gate | 담당(작성) | 검토 | MVP |
|---|---|---|---|---|---|
| P1 | 요구사항 분석·검토 | G1 Requirements | 오케스트레이터(Requirements 역할) | vmodel:verifier, 중요 결정은 사용자 | MVP |
| P2 | 아키텍처 설계 | G2 Architecture | 오케스트레이터(Architecture 역할) | vmodel:verifier | MVP |
| P3 | 상세 설계·테스트 명세 | G3 Design & Test Planning | 오케스트레이터(Detailed Design) + vmodel:test-designer | vmodel:verifier | MVP |
| P4 | 구현·정적 분석·코드 리뷰 | G4 Implementation | 오케스트레이터(Implementation 역할) | vmodel:verifier | MVP |
| P5 | 단위 검증 | G5 Unit Verification | Validator가 직접 실행 | (기계 판정) | MVP |
| P6 | 통합 검증 | G6 Integration Verification | — | — | EXT |
| P7 | 시스템 검증 | G7 System Verification | — | — | EXT |

각 Gate의 입력·출력·필수 산출물·체크 ID·PASS 기준의 정본은 `gates.json`이다. 아래는 그 요약이다.

### 3.1 Gate별 판정 기준 (체크 ID는 gates.json과 동일)

체크 종류: `mechanical`(Validator가 기계적으로 판정), `execution`(Validator가 명령을 직접 실행), `ai_review`(Verifier 에이전트의 의미 검토 기록 — 기계 검증 아님, 결과에 `machine_verified:false`로 구분 기록).

**G1 Requirements** — 입력: `workitem.json`(원 요청). 출력: `requirements.json`, `reviews/G1.json`
- G1.SCHEMA 스키마 통과 / G1.IDS REQ·AC ID 형식과 프로젝트 전체 유일성
- G1.ACCEPTANCE 활성 functional REQ마다 수용 기준 ≥1
- G1.CONFLICTS 충돌 분석 수행 표시 + 모든 충돌에 해결 기록, 참조 ID 실재
- G1.OPEN_ISSUES critical 미해결 이슈 없음, 해결된 critical 이슈는 `decided_by: user`
- G1.CHANGE_CONTROL 이전 PASS 이후 REQ가 바뀌었으면 해당 REQ를 다루는 CR 존재
- G1.AMBIGUITY 모호어 경고 (경고만, 차단 안 함)
- G1.REVIEW 현재 해시 대상 Verifier 리뷰 approve, open major finding 없음. 리뷰 파일은 verifier가 `vmodel review-submit`으로 서명 원장에 등록한 해시와 일치해야 함(G2~G4 동일)

**G2 Architecture** — 출력: `architecture.json`, `reviews/G2.json`
- G2.SCHEMA / G2.IDS(ARCH, IF) / G2.REQ_MAPPING 활성 functional REQ 전부 컴포넌트에 매핑, 미존재 REQ 참조 없음
- G2.INTERFACES 컴포넌트 2개 이상이면 인터페이스 ≥1, provider/consumer 실재
- G2.NFR 활성 non-functional REQ 전부 `nfr_mapping`에 반영
- G2.INTEGRATION_STRATEGY 통합 테스트 전략 존재, 모든 IF 포함
- G2.TRADEOFFS 트레이드오프 기록 (경고) / G2.REVIEW

**G3 Detailed Design & Test Planning** — 출력: `design.json`, `tests.json`, `reviews/G3.json`
- G3.SCHEMA / G3.IDS(DESIGN, TEST) / G3.DESIGN_COVERAGE 모든 컴포넌트에 설계 단위 ≥1, 모든 functional REQ가 설계 단위에 연결
- G3.CONTRACTS 시그니처, 사전/사후 조건, 예외 목록(빈 목록이라도 명시), 경계조건 ≥1
- G3.UNIT_TESTS 모든 설계 단위에 unit 테스트 ≥1, 정상 테스트 ≥1, 선언된 예외가 있으면 abnormal 테스트, 경계조건이 있으면 boundary 테스트
- G3.INTEGRATION_SYSTEM_TESTS 모든 IF에 integration 테스트 명세, 모든 functional REQ의 AC에 system 테스트 명세
- G3.TRACE 테스트의 verifies/AC 참조 실재, 모든 functional REQ가 테스트에 연결
- G3.NO_SILENT_REMOVAL 이전 PASS 대비 사라진 DESIGN/TEST ID는 CR 또는 결함의 `removed_ids`에 있어야 함
- G3.REVIEW

**G4 Implementation** — 입력: G3 산출물 + 프로젝트 전체 파일 트리 + 설정 + defects/CR. 출력: 코드, `reviews/G4.json`
- G4.FILES 소스·테스트 파일 존재
- G4.UNEXPECTED_CODE 설정 경로(source/tests/build_config/other) 밖의 `.py` 파일과 심볼릭 링크 금지 (루트 `pytest.py` 가로채기, `__pycache__` 안 숨긴 테스트 차단)
- G4.SYNTAX Python AST 문법 검사(Validator 내장)
- G4.LINT 설정된 정적 분석 도구를 Validator가 직접 실행(증거 생성). 도구가 없으면 BLOCKED, 또는 사용자가 설정에 명시한 대체 범위(syntax-only)를 기록하고 진행
- G4.DESIGN_CONFORMANCE 설계 단위의 module 파일과 심볼(def/class) 실재
- G4.TEST_CODE 모든 unit TEST ID마다 이름에 그 ID 토큰 **하나만** 가진 테스트 함수가 존재 (AST 기준, 주석·문자열 불인정)
- G4.TEST_INTEGRITY 테스트·지원 코드가 결과 보고를 건드리지 않음 (pytest 결과 훅, `exitstatus`/`xmlpath`, `os._exit`, junit 문자열)
- G4.REQ_IMPLEMENTED 모든 functional REQ → DESIGN → 심볼 실재
- G4.REVIEW 코드 리뷰 + 테스트 코드 적합성 검토 (현재 코드 해시 대상)
- 검증 대상 파일 해시 전체를 기록

**G5 Unit Verification** — 입력: G4와 같은 manifest. 출력: 실행 증거
- G5.PREREQ G4가 현재 해시로 PASSED
- G5.EXECUTION Validator가 테스트 명령을 직접 실행(에이전트 셸의 `PYTHON*`·`PYTEST_*`·`VMODEL_*` 제거, 바이트코드 미사용, 플러그인 자동 로드 끔), 종료 코드 0, JUnit 결과 생성
- G5.RESULTS 테스트 수 > 0, 실패·오류 0
- G5.TEST_MAPPING 모든 unit TEST ID에 통과한 테스트 케이스 ≥1(JUnit `name`에 ID가 정확히 하나), 해당 ID 케이스의 실패·skip 없음
- G5.REQ_COVERAGE 모든 functional REQ가 통과한 테스트에 연결
- G5.NO_WEAKENING 직전 G5 기록 대비 변경·삭제된 테스트 파일은 결함/CR의 `test_changes`(근거·관련 REQ·영향)로 정당화, 이전에 실행된 TEST ID가 사라지지 않음
- G5.INPUTS_UNCHANGED 실행 중 검증 대상 파일이 바뀌지 않음

### 3.2 공통 전제 조건 (기록 없이 BLOCKED 반환)
- Validator 무결성 확인 실패, 서명 키 없음, 원장 변조·롤백(외부 앵커 불일치) → 모든 Gate BLOCKED
- 이전 Gate가 현재 해시로 PASSED가 아님
- 직전 평가가 FAILED인데 그 기록 ID를 가리키는 결함(DEFECT) 기록이 없음 (재작업 절차 강제)
- 동일 원인 3회 연속 실패로 BLOCKED된 뒤 사용자 `unblock`이 없음
- 미구현 Gate(G6, G7) 요청

## 4. 상태 정의

### 4.1 Gate 상태
| 상태 | 의미 | 설정 주체 |
|---|---|---|
| NOT_STARTED | 산출물도 평가 기록도 없음 | 파생 |
| IN_PROGRESS | 산출물이 있거나 앞 Gate가 통과했지만 아직 평가 기록 없음 | 파생 |
| REVIEW_REQUIRED | 기계 체크는 통과, 검토가 남음. `review_required_by`에 검토 주체 명시: `vmodel:verifier`(AI 리뷰 없음/구버전 해시) 또는 `user`(critical 이슈·보안·아키텍처 결정) | Validator 기록 |
| PASSED | 그 시점 manifest 해시로 모든 체크 통과 | Validator 기록 |
| FAILED | 기계 체크 실패 또는 리뷰 reject | Validator 기록 |
| BLOCKED | 무결성 실패·전제 미충족·도구 부재·동일 원인 3회 실패·미구현 | Validator 기록 또는 파생 |
| STALE | PASSED였지만 현재 manifest 해시 또는 Validator Core 해시가 기록과 다르거나, 상위 Gate가 더 이상 PASSED가 아님 | 파생 (status 계산 시) |

"설계 승인"은 해당 Gate PASSED를 뜻한다. 단 critical 이슈(보안 위험, 데이터 손실, 본질적 요구사항 충돌, 아키텍처·보안 변경)는 `decided_by: user` 기록이 있어야 한다.

### 4.2 Work Item 상태 (파생)
- `NOT_STARTED`, `IN_PROGRESS`, `BLOCKED`
- `PARTIALLY_VERIFIED` — 구현된 필수 Gate(G1~G5)는 모두 현재 해시로 PASSED, 그러나 프로파일이 요구하는 G6~G7이 DevKit에 미구현
- `COMPLETED` — 프로파일이 요구하는 **모든** Gate가 현재 해시로 PASSED (MVP의 STANDARD에서는 도달 불가 — 의도된 동작)

## 5. 증거 신뢰 모델

1. **AI가 쓴 결과는 증거가 아니다.** 상태는 Validator가 쓴 서명 원장(`.vmodel/state/ledger.jsonl`)에서만 읽는다. 원장 항목은 HMAC-SHA256으로 서명되고 해시 체인으로 연결되며, 마지막 항목은 서명된 head 파일로 고정된다(꼬리 삭제 탐지). 같은 head가 프로젝트 밖 `$VMODEL_HOME/anchors/`에도 서명돼 저장되어, `.vmodel` 삭제·이전 상태로의 롤백·재초기화를 탐지한다.
2. **서명 키는 프로젝트 밖**(`$VMODEL_HOME/keys/<project_id>.key`, 기본 `~/.vmodel-devkit`)에 있다. 에이전트의 키 읽기는 Hook과 권한 규칙으로 막는다.
3. **테스트는 Validator가 직접 실행**한다(`subprocess`, shell 없이 argv 목록). stdout/stderr는 원본 바이트로 저장하고 해시를 기록한다. 디코딩은 표시용으로만 하며(UTF-8 → CP949 → replace), 해시·종료 코드는 디코딩과 무관하다.
4. **증거 기록**: Work Item, Gate, 명령, 실행 파일 경로·버전·해시, 런타임, 시작/종료 시각, 종료 코드, stdout/stderr 해시, JUnit 결과, Git HEAD·dirty 여부, 검증 대상 파일별 해시와 manifest 해시, Validator 버전과 Core 해시.
5. **최신성**: Gate별 manifest = 해당 Gate 산출물 + 모든 상위 산출물 (+ G4/G5는 VCS·도구 캐시·가상환경·`build/`·`dist/`·`__pycache__` 바이트코드를 뺀 **프로젝트 전체 파일**, `.vmodel/config.json`, `defects.json`, `change-requests.json`). 파일 하나라도 바뀌면 PASSED → STALE. Validator Core가 바뀌거나 상위 Gate가 PASSED가 아니게 되어도 STALE. dirty 작업 트리도 검증 가능하며 그 시점 파일 해시를 저장한다. 테스트 인터프리터의 설치 패키지 목록은 증거에 기록만 한다(STALE 판정 미포함 — 한계).
5-1. **리뷰 진위**: guard 훅이 `vmodel review-submit`을 `agent_type == vmodel:verifier`에게만 허용하고, Gate는 원장에 등록된 해시와 같은 리뷰만 인정한다.
6. **Validator 보호**: Core 해시를 프로젝트 `.vmodel/devkit.lock.json`에 고정. 실행 시 자기 파일 해시를 다시 계산해 lock과 다르면 BLOCKED. 릴리스 사본은 `RELEASE_MANIFEST.json`으로 파일별 대조. 쓰기 보호는 PreToolUse Hook(`onFailure: block`으로 fail-closed) + 프로젝트 권한 deny 규칙의 이중 장치.
7. **한계 (주장하지 않는 것)**: 같은 OS 사용자로 임의 코드를 실행할 수 있는 에이전트(자기가 쓴 스크립트 실행, pty로 TTY 흉내)는 이론상 키를 읽고 원장·앵커를 위조하거나 사용자 전용 명령을 실행할 수 있다. 테스트 코드는 테스트 러너와 같은 프로세스에서 돌기 때문에 G4.TEST_INTEGRITY가 못 잡는 방식으로 결과를 조작할 수 있다. 사용자 결정 기록(`decided_by: "user"`)은 자기 증명이다. Hook과 권한 규칙은 우발적·일반적 우회를 막는 장치이지 OS 수준 격리가 아니다. 최종 신뢰 경계는 별도 사용자/CI에서 신뢰 사본으로 `vmodel audit` 및 전체 재검증(`vmodel verify`)을 돌리는 것이다 [EXT: CI 연동].
8. **순환 검증 금지**: Validator 자체의 정확성은 독립 하네스(`tests/`, unittest)로만 판정한다. DevKit 개발 자체를 DevKit Validator로 승인하지 않는다.

## 6. Work Item과 추적성

### 6.1 디렉터리 (대상 프로젝트)
```
.vmodel/
  config.json            # 프로파일, 경로 glob, 테스트/정적분석 명령 (보호)
  devkit.lock.json       # 고정된 Validator 버전·Core 해시 (보호)
  work-items/WI-001/
    workitem.json        # id, 제목, 원 요청, 프로파일
    requirements.json    # REQ, AC, 충돌, 미해결 이슈, 가정
    architecture.json    # ARCH(컴포넌트), IF, 데이터 흐름, NFR 매핑, 트레이드오프, 통합 테스트 전략
    design.json          # DESIGN(함수·클래스·모듈 계약, 예외, 경계조건, 상태)
    tests.json           # TEST(unit/integration/system, 정상/비정상/경계, verifies, AC)
    defects.json         # DEFECT(발견 기록, 원인 단계, 수정 범위, test_changes)
    change-requests.json # CR(변경 사유, 영향 ID, removed_ids, test_changes)
    reviews/G1..G4.json  # Verifier 리뷰 (vmodel:verifier만 쓰기 가능)
  state/ledger.jsonl, head.json   # Validator 전용 (보호)
  evidence/WI-001/G5/<run>/       # Validator 전용 (보호)
  reports/WI-001.md               # 파생 보고서
```
기계 판독 형식은 JSON(UTF-8)이다. YAML은 표준 라이브러리가 없어 쓰지 않는다.

### 6.2 ID 규칙
- `REQ-001`, `AC-001-1`, `ARCH-001`, `IF-001`, `DESIGN-001`, `TEST-001`, `DEFECT-001`, `CR-001` — 프로젝트 전체에서 유일 (`vmodel next-id <KIND>`로 발급)
- Work Item 프로필은 MVP에서 STANDARD만 생성 가능. 다른 값이면 COMPLETED 불가, 모르는 값이면 BLOCKED
- 테스트 코드는 함수 이름에 `TEST_001` 토큰을 넣는다 (예: `test_TEST_001_add_two_numbers`) → JUnit 결과와 명세를 기계적으로 연결

### 6.3 추적 관계 (양방향)
REQ ↔ ARCH(`components[].requirements`) ↔ DESIGN(`units[].component`, `units[].requirements`) ↔ TEST(`tests[].verifies`, `acceptance_criteria`) ↔ 코드 심볼(`units[].module`+`name`) ↔ 실행 결과(JUnit) ↔ DEFECT(`related`). `vmodel trace`가 정방향·역방향 행렬과 끊어진 링크를 출력한다.

### 6.4 변경 관리
요구사항 변경 → CR 작성(영향 ID 명시) → `vmodel impact`가 바뀐 항목 해시와 추적 그래프로 영향받는 ARCH/DESIGN/TEST와 STALE Gate를 계산 → 영향 Gate 재평가.

## 7. 재작업 루프

1. Gate FAILED → Validator가 실패 체크·실패 테스트를 기록, `failure_signature` 계산
2. 오케스트레이터가 DEFECT 작성: `found_in_records`(실패 기록 ID), `root_cause_phase`(P1~P4), `root_cause`, `fix_scope`
3. 원인 단계로 복귀해 산출물·코드 수정 → 영향 Gate 자동 STALE
4. 상위부터 재평가. 재평가 전 결함 기록이 없으면 BLOCKED
5. 같은 `failure_signature`로 3회 연속 FAILED → BLOCKED, 자동 반복 중지 후 사용자 보고. 해제는 사용자가 터미널(TTY)에서 `vmodel unblock`
6. 테스트 완화·삭제 금지: G3.NO_SILENT_REMOVAL, G5.NO_WEAKENING이 기계적으로 막는다. 테스트를 바꿔야 하면 `test_changes`에 근거·관련 REQ·영향을 기록하고 Verifier가 검토

## 8. 명령 (Plugin 네임스페이스 반영)

플러그인 이름이 `vmodel`이므로 Claude Code 규칙상 스킬은 `/vmodel:<skill>`로 노출된다. 원 요구의 `/vmodel-start`는 `/vmodel:start`로 매핑한다.

| 요구 이름 | 실제 명령 | 내용 |
|---|---|---|
| /vmodel-start | `/vmodel:start <요청>` | WI 생성 후 P1~P5 진행 (자동 트리거 대상) |
| /vmodel-status | `/vmodel:status [WI]` | Gate 상태·STALE·무결성 |
| /vmodel-verify | `/vmodel:verify [WI] [G#]` | Validator로 Gate 재평가 (G5는 테스트 재실행) |
| /vmodel-rework | `/vmodel:rework [WI]` | 실패 분석 → DEFECT → 원인 단계 수정 → 재검증 |
| /vmodel-report | `/vmodel:report [WI]` | Markdown 보고서 생성 |

CLI(`bin/vmodel`): `init`, `install`, `uninstall`, `new-wi`, `next-id`, `lint`, `hash`, `review-submit`, `gate`, `verify`, `status`, `trace`, `impact`, `report`, `audit`, `verify-evidence`, `unblock`, `lock`, `hook`, `version`.
사용자 전용(guard가 에이전트 실행 차단): `init`, `install`, `uninstall`, `unblock`(TTY), `lock --accept-current`(TTY), `uninstall --purge`(TTY). verifier 전용: `review-submit`.

### 8.1 자동 실행 정책
자동 대상: 신규 기능 개발, 기존 기능의 실질적 변경, 버그 수정, 아키텍처 변경, 대규모 리팩터링.
자동 비대상: 코드 설명, 간단한 질의응답, 자료 검색, 개발과 무관한 문서 작성, 변경 없는 코드 분석.
스킬 자동 트리거는 보장되지 않으므로 표준 경로는 명시적 명령이다. 판단이 불확실하면 사용자에게 `/vmodel:start` 사용을 안내한다. 정책 텍스트는 SessionStart Hook이 `.vmodel/`이 있는 프로젝트에서만 주입한다.

### 8.2 사용자 질문 정책
G1에서 필수 모호점을 모아 한 번에 묻는다. 안전한 기본값이 있는 비핵심 사항은 `assumptions`에 기록하고 진행한다. 보안 위험·데이터 손실·본질적 충돌은 임의로 결정하지 않는다(critical 이슈 → REVIEW_REQUIRED by user).

## 9. Agent 구성

| Agent | 파일 | MVP 활성 | 비고 |
|---|---|---|---|
| Requirements | `agents/requirements-analyst.md` | 역할 지침으로 사용 (오케스트레이터가 직접 수행: 사용자 질문이 필요) | |
| Architecture | `agents/architect.md` | 역할 지침 (큰 WI는 서브에이전트 위임 가능) | |
| Detailed Design | `agents/detailed-designer.md` | 역할 지침 | |
| Test Design | `agents/test-designer.md` | **서브에이전트로 활성** — 구현과 독립적으로 테스트 명세 작성 | |
| Implementation | `agents/implementer.md` | 역할 지침 (큰 WI는 위임 가능) | |
| Verification | `agents/verifier.md` | **서브에이전트로 활성** — 별도 컨텍스트, G1~G4 리뷰만 작성 | Hook이 reviews/ 쓰기를 verifier로 제한 |

WI 하나당 병렬 서브에이전트는 최대 2개. Agent 리뷰만으로 Gate를 통과시키지 않는다(리뷰는 체크 하나일 뿐, 판정은 Validator).

## 10. 개발 프로파일

| Gate / 산출물 | LITE [EXT] | STANDARD [MVP: G1~G5] | STRICT [EXT] |
|---|---|---|---|
| G1 Requirements | 필수 (영향 분석 중심, 변경 REQ만) | 필수 | 필수 + 사용자 승인 |
| G2 Architecture | N/A 사유 기록 가능 | 필수 | 필수 + 대안 2개 이상 트레이드오프 |
| G3 Design & Test Planning | 변경 단위 설계 + 테스트 명세 필수 | 필수 | 필수 + 모든 경계조건별 테스트 |
| G4 Implementation | 필수 (정적 분석 + 리뷰) | 필수 | 필수 + 리뷰 2회(독립 2인) |
| G5 Unit Verification | 필수 | 필수 | 필수 + 커버리지 기준 |
| G6 Integration | 선택 | 필수 [EXT] | 필수 [EXT] |
| G7 System | 선택 | 필수 [EXT] | 필수 [EXT] |
| WI 완료 상태 | COMPLETED 가능 (G6/7 미구현 시에도 선택이므로) [EXT] | MVP에서는 PARTIALLY_VERIFIED | [EXT] |

## 11. 설치·버전·제거

- 개발 중: `claude --plugin-dir plugins/vmodel` (세션 한정, 전역 변경 없음)
- 릴리스: `python3 scripts/release.py` → `dist/vmodel-<ver>/`(불변 사본 + `RELEASE_MANIFEST.json`) + `dist/.claude-plugin/marketplace.json` + `releases/vmodel-<ver>.json`(저장소에 남는 해시 기록)
- 프로젝트 설치: `<release>/bin/vmodel install --project <dir>` → `.vmodel/` 생성, lock 고정, `.claude/settings.json`에 deny 규칙 **병합**(기존 값 보존, 백업, 충돌 보고), 설치 기록 저장. CLAUDE.md는 기본적으로 건드리지 않고 SessionStart Hook으로 지침을 주입한다. 옵션 `--claude-md-import`일 때만 기존 CLAUDE.md 끝에 `@.vmodel/VMODEL.md` 한 줄을 추가한다.
- 플러그인 등록: 전역 레지스트리(`~/.claude/plugins`)를 건드리므로 설치 스크립트가 자동 실행하지 않고, 사용자가 실행할 명령(`claude plugin marketplace add <dist> --scope project`, `claude plugin install vmodel@vmodel-devkit --scope project`)을 출력한다. 세션 한정 사용은 `--plugin-dir dist/vmodel-<ver>`.
- 업그레이드: 새 릴리스로 플러그인 경로를 바꾸고 사용자가 `vmodel lock --accept-current`(TTY)로 재고정. Core 해시가 바뀌므로 기존 PASS는 전부 STALE.
- 제거: `vmodel uninstall --project <dir>` → 설치 기록에 있는 항목만 되돌림. `.vmodel/` 데이터·서명 키·앵커는 `--purge`(TTY 필요)일 때만 삭제. 앵커가 남은 경로에서는 `init`이 거부된다(이력 보호).

## 12. 실행 환경

- Python 3.11+ 표준 라이브러리. 경로는 pathlib. DevKit JSON·로그·보고서는 UTF-8(읽을 때 BOM 허용). UTF-8이 아닌 산출물은 크래시 대신 "CP949/UTF-16로 보임" 체크 실패로 보고.
- CLI 출력: 파이프면 UTF-8로 강제(Claude Code가 UTF-8로 읽음), 콘솔이면 그대로, `errors=replace`. stdout/stderr가 None인 환경(pythonw)도 안전하게 무시.
- 메시지는 ASCII 영어(CP949 콘솔에서도 깨지지 않음). 산출물 안의 한글은 그대로 통과.
- 훅 명령은 `sh`로 python3/python/py를 탐색 (Windows는 Git Bash 필요).

## 13. 테스트 시나리오 (T01~T18)

| ID | 내용 | 검증 방법 |
|---|---|---|
| T01~T04 | 요청→REQ/AC, 아키텍처, 설계·테스트 명세, 구현 | 실제 Claude 세션 산출물을 Validator 스키마·추적·리뷰로 평가 (+ 하네스 픽스처) |
| T05 | 실제 단위 테스트 실행·증거 생성 | 하네스 + 실제 세션 |
| T06 | 테스트 실패 시 G5 차단 | 하네스 |
| T07 | 실행 없이 만든 PASS 보고 거부 | 하네스 (가짜 evidence/리뷰/상태 파일) |
| T08 / T09 | 소스 / 테스트 파일 변경 → STALE, 테스트 변경 정당화 요구 | 하네스 |
| T10 | 필수 산출물 누락 → 차단 | 하네스 |
| T11 | 잘못된 추적 관계 탐지 | 하네스 |
| T12 | Validator Core 변조 → BLOCKED | 하네스 |
| T13 | 실패 → 결함 → 수정 → 재검증 PASS | 하네스 (+ 실제 세션에서 관찰되면 기록) |
| T14 | 세션 재시작 후 상태 복원 | 하네스(새 프로세스) + 실제 새 세션 |
| T15 | 다른 임시 프로젝트에 적용 | 하네스 |
| T16 | 기존 Claude 설정 보존·충돌 검사 | 하네스 |
| T17 | 가짜 PASS 데이터 주입 | 하네스 (원장 위조·꼬리 삭제·head 위조) |
| T18 | 한글·공백 경로, Windows 실행 | WSL + 실제 Windows Python(CP949) |

T01~T04의 의미적 정확성(요구사항이 사용자 의도와 맞는지 등)은 자동 평가로 보장할 수 없으며 Verifier 리뷰와 사람 검토의 몫이다.

## 14. 확장 단계 [EXT] (구현하지 않음)
G6 통합 검증 실행, G7 시스템 수용 검증, LITE/STRICT 프로파일 실행, 다중 언어 어댑터(JUnit 기반 일반화), 커버리지 기준, 강화된 배포(서명 릴리스), CI 독립 검증, WorkMind 적용.
