# DECISIONS

설계 결정과 근거. 새 결정은 아래에 번호를 이어 붙인다.

## D01. 상태 저장은 JSON, YAML 미사용 (2026-11-08)
표준 라이브러리만으로 읽고 쓸 수 있어야 Windows/CP949 환경과 격리된 실행에서 의존성 문제가 없다. PyYAML 의존을 피한다.

## D02. 스키마는 JSON Schema의 작은 부분집합을 자체 구현
`jsonschema` 패키지를 쓰지 않는다. type/required/properties/additionalProperties/items/enum/pattern/minItems/minLength만 지원. 스키마 파일 자체는 JSON Schema 문법과 호환되게 써서 나중에 외부 검증기로 바꿀 수 있다.

## D03. 상태의 유일한 원천은 서명된 원장
`.vmodel/state/ledger.jsonl`은 HMAC-SHA256 서명 + 해시 체인 + 서명된 head(꼬리 삭제 탐지). 에이전트가 만든 JSON(“PASS”라고 적힌 파일)은 원장에 없으면 아무 의미가 없다. Gate 상태 중 IN_PROGRESS·STALE·NOT_STARTED는 저장하지 않고 매번 계산한다.
대안으로 검토한 “서명 없이 매번 전부 재실행”은 원장 위조를 막지 못하고 3회 실패 규칙(이력 필요)을 구현할 수 없어 기각. 단 최종 판정용 `vmodel verify`는 저장 결과를 쓰지 않고 G1~G5를 처음부터 다시 실행한다.

## D04. 서명 키는 프로젝트 밖 `$VMODEL_HOME/keys`
기본 `~/.vmodel-devkit`. Claude 설정 디렉터리(`~/.claude`)가 아니므로 전역 Claude 설정 변경에 해당하지 않는다. 테스트·E2E는 `VMODEL_HOME`을 샌드박스로 지정해 실제 홈을 건드리지 않는다. 키가 없으면 BLOCKED.
한계: 같은 OS 사용자 권한의 임의 코드 실행은 키를 읽을 수 있다(SPEC §5.7). 최종 신뢰 경계는 CI/별도 사용자.

## D05. Hook은 fail-closed(`onFailure: block`)
조사 결과 Claude Code 훅은 기본이 fail-open(크래시·타임아웃·exit 1이면 도구 실행 진행). 2.1.295+의 `"onFailure": "block"`을 보호 훅에 지정한다. 실제 동작은 M3에서 헤드리스 실행으로 확인한다.

## D06. 보호는 이중 장치 + 정직한 한계 표기
1) PreToolUse 훅 `vmodel hook guard`: 보호 경로(원장·증거·설정·lock·Validator Core·키) 쓰기 차단, Bash 명령 문자열의 보호 경로 언급 차단(검증기 단독 호출만 허용), reviews/ 쓰기는 verifier 서브에이전트만, verifier는 reviews/ 외 쓰기 금지.
2) 프로젝트 `.claude/settings.json`의 `permissions.deny`(`Edit(...)`는 Write/MultiEdit/NotebookEdit까지 적용, `Write(...)`는 매칭 안 됨).
python 하위 프로세스 같은 간접 쓰기는 둘 다 못 막는다 → 서명(D03)이 최종 탐지 장치.

## D07. CLAUDE.md는 기본적으로 건드리지 않음
지침은 플러그인 SessionStart 훅이 `.vmodel/`이 있는 프로젝트에서만 주입한다. `@import`는 옵션(`install --claude-md-import`)으로만 기존 CLAUDE.md 끝에 한 줄 추가하며, 설치 기록에 남겨 제거 시 그 줄만 지운다. 이유: 덮어쓰기 금지 요구 + import 승인 대화상자(프로젝트 외부 경로) 회피. import 대상은 프로젝트 내부 `.vmodel/VMODEL.md`로 둔다.

## D08. 플러그인 이름 `vmodel`, 명령은 `/vmodel:<skill>`
Claude Code가 플러그인 스킬을 `/<plugin>:<skill>`로 네임스페이스한다. `/vmodel-start` → `/vmodel:start` 등으로 매핑(SPEC §8).

## D09. 고정 버전 = 릴리스 디렉터리 + Core 해시 lock
로컬 디렉터리 마켓플레이스/`--plugin-dir`은 원본을 그 자리에서 로드하므로 Claude Code의 버전 고정만으로는 “설치된 고정 사본”이 되지 않는다. `scripts/release.py`가 `dist/vmodel-<ver>/` 사본과 파일별 해시(`RELEASE_MANIFEST.json`, `releases/vmodel-<ver>.json`)를 만들고, 프로젝트 `devkit.lock.json`이 Core 해시를 고정한다. 실행할 때마다 Core 해시를 재계산해 다르면 BLOCKED. Validator가 `__pycache__`를 만들지 않도록 `sys.dont_write_bytecode`.

## D10. 전역 플러그인 레지스트리는 자동으로 건드리지 않음
`claude plugin marketplace add/install`은 `--scope project`여도 `~/.claude/plugins`의 레지스트리를 쓴다. 설치 스크립트는 프로젝트 파일만 바꾸고, 플러그인 등록 명령은 출력만 한다. E2E는 `--plugin-dir`로 세션 한정 로드. 등록 명령 자체의 동작은 `CLAUDE_CONFIG_DIR`를 임시 디렉터리로 바꿔 격리 검증한다.

## D11. 오케스트레이터가 작성, 독립 검증은 서브에이전트
서브에이전트는 사용자에게 질문할 수 없으므로 P1은 메인 세션이 수행. 비용을 줄이기 위해 작성 역할(P1/P2/P4)은 메인 세션이 역할 지침 파일을 읽고 수행하고, **독립성이 본질인 두 역할만** 서브에이전트로 띄운다: test-designer(구현 전·구현과 독립된 테스트 명세), verifier(G1~G4 리뷰). WI당 병렬 서브에이전트 최대 2.

## D12. G5는 순수 기계 판정, 테스트 적합성 의미 검토는 G3(명세)와 G4(코드)에서
G5에 별도 AI 리뷰를 두면 서브에이전트 호출이 늘고 실행 증거와 의미 검토가 섞인다. 테스트 적합성은 G3 리뷰(명세가 AC를 검증하는가)와 G4 리뷰(테스트 코드가 명세를 구현하는가)로 보고, G5는 실행·매핑·완화 금지만 기계적으로 본다.

## D13. 테스트-명세 연결은 이름 토큰 `TEST_001`
JUnit XML은 대부분의 러너가 내보내므로 언어 확장 시에도 같은 방식이 통한다. pytest 마커 같은 언어 종속 방식을 피한다.

## D14. 재작업 절차를 전제 조건으로 강제
직전 평가가 FAILED면 그 기록 ID를 `found_in_records`에 담은 DEFECT가 있어야 재평가할 수 있다(없으면 기록 없이 BLOCKED). 같은 `failure_signature` 3회 연속 FAILED → BLOCKED 기록, 해제는 TTY가 필요한 `vmodel unblock`(Claude의 Bash 도구에는 TTY가 없어 에이전트가 스스로 풀 수 없음).

## D15. Work Item 완료 상태를 정직하게
STANDARD는 G1~G7이 필수인데 MVP는 G1~G5만 구현 → G1~G5 전부 통과해도 `PARTIALLY_VERIFIED`. `COMPLETED`는 MVP에서 도달 불가. MVP 완료를 V-Model 전체 완료로 보고하지 않기 위한 장치.

## D16. CLI 메시지는 ASCII 영어, 파이프 출력은 UTF-8 강제
Windows CP949 콘솔에서 비-CP949 문자로 인한 UnicodeEncodeError를 원천 차단. 파이프(Claude Code Bash 도구)로 나갈 때는 UTF-8로 강제해 한글 산출물 내용이 모지바케가 되지 않게 한다.

## D17. Validator 부트스트랩 하네스는 unittest
pytest 없이 어떤 Python 3.11+에서도 돌아가야 Windows 등에서 바로 검증할 수 있다. 샘플 프로젝트는 요구대로 pytest를 쓴다.

## D18. 훅 실패 동작은 실측으로 확정 (2026-11-08, Claude Code 2.1.319)
haiku 헤드리스 실행으로 확인: `onFailure: "block"`이면 훅 크래시(exit 1)·타임아웃·exit 2·인터프리터 없음 모두 도구 호출 차단. 지정하지 않으면 크래시·타임아웃 모두 통과(fail-open). **예외: block 모드라도 훅이 exit 0으로 깨진 JSON을 출력하면 통과됨**(문서와 다름). guard는 JSON 또는 빈 출력만 내도록 유지하고, 내부 예외는 비-0 종료로 이어지게 한다.

## D19. 리뷰 진위는 원장 등록으로 확인
훅 입력의 `agent_type`이 플러그인 서브에이전트에 대해 `vmodel:verifier`로 전달됨을 실측 확인. guard가 `vmodel review-submit`을 verifier에게만 허용하고, `review-submit`은 리뷰 파일 해시를 서명 원장에 기록한다. Gate는 원장에 등록된 해시와 일치하는 리뷰만 인정한다. 메인 세션이 Bash로 리뷰 파일을 만들어도(차단되지만 우회되더라도) 등록이 없으면 REVIEW_REQUIRED.

## D20. 코드 Gate manifest = 프로젝트 전체 트리 (독립 리뷰 결과 반영)
glob에 걸린 `.py`만 해시하면 루트의 `pytest.py`, `__pycache__` 안의 `.py`, 테스트 데이터, 심볼릭 링크가 사각지대가 된다. G4/G5 manifest는 VCS·도구 캐시·가상환경·`build/`·`dist/`·`__pycache__`의 바이트코드를 제외한 모든 파일 + `.vmodel/config.json` + `defects.json` + `change-requests.json`을 해시한다. 설정된 경로(`source`/`tests`/`build_config`/`other`) 밖의 `.py`와 모든 심볼릭 링크는 G4.UNEXPECTED_CODE로 실패.

## D21. 테스트 실행 환경은 Validator가 통제
에이전트 셸의 `PYTHON*`(인코딩 스위치 제외)·`PYTEST_*`·`VMODEL_*` 변수를 제거하고, 바이트코드 쓰기 금지 + 빈 `PYTHONPYCACHEPREFIX`(트리 안의 위조 `.pyc` 무시) + `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`(설정 `unit_test.plugin_autoload: true`로 해제). 실행 인터프리터의 설치 패키지 목록과 해시를 증거에 기록(STALE 판정에는 쓰지 않음 — 한계). Validator 자신도 `-I -B`로 실행되고 `sys.pycache_prefix`를 임시 경로로 둬 코어 옆 `.pyc`를 읽지 않는다.

## D22. 테스트 코드가 결과 보고를 건드리면 G4 실패
같은 프로세스에서 도는 테스트 코드는 원리상 결과를 조작할 수 있다. G4.TEST_INTEGRITY가 테스트·지원 코드의 pytest 결과 훅(`pytest_sessionfinish`, `pytest_runtest_makereport` 등), `exitstatus`/`xmlpath` 등 속성, `os._exit`, `junitxml` 문자열을 AST로 찾아 실패시킨다. 휴리스틱이므로 G4 리뷰 체크리스트에도 명시.

## D23. TEST ID 매핑은 "함수 이름에 정확히 하나"
G4는 AST로 테스트 함수 이름만 보고(주석·문자열 불인정), G5는 JUnit `name`만 본다. 이름에 TEST ID가 2개 이상이면 실패 — 테스트 하나로 여러 명세를 충족시키는 것을 막는다.

## D24. 프로젝트 수명주기는 사용자 전용 + 외부 앵커
`.vmodel`을 지우고 다시 init하면 이력(3회 실패, 기준선)이 사라진다. 대응: (1) `$VMODEL_HOME/anchors/<경로 해시>.json`에 서명된 원장 head를 매 기록마다 저장해 원장 삭제·롤백·재초기화를 탐지(BLOCKED), (2) 앵커가 있는 경로의 `init` 거부, (3) `uninstall --purge`는 TTY 필요, (4) guard가 에이전트의 `vmodel init/install/uninstall/unblock`, 쓰기 명령의 `.vmodel` 대상, `git clean`·`find -delete`·`rm .`/`rm *`를 차단.

## D25. 받아들인 한계 (문서화만)
- 사용자 결정(`decided_by: "user"`)은 오케스트레이터가 기록하므로 자기 증명이다. 암호학적 결속(TTY 서명 명령)은 UX 비용 때문에 Extension.
- pty를 쓰는 스크립트, 에이전트가 작성한 python 스크립트 실행 같은 임의 코드 실행은 guard가 문자열로 판별할 수 없다. 서명·앵커·재검증이 탐지 장치이며, 최종 신뢰 경계는 CI/별도 사용자.
- 프로필은 STANDARD만 생성 가능. 다른 값이 들어 있으면 WI는 COMPLETED가 될 수 없고, 모르는 값이면 BLOCKED.

## D26. 실전 재작업 드릴 설계: 블라인드 시딩 + 에이전트 pytest 차단 (2026-11-08)
목표는 "실제 Claude 세션에서 테스트 실패 → 결함 → 수정 → 재검증"이다. 실패는 결함 주입으로 만들고, 주입 내용은 실행 전에 세션 밖 파일에 봉인했다(`drill-plan.json`, sha256 기록). 오케스트레이터는 결함을 알지만 verifier·test-designer에게는 표준 프롬프트만 준다(블라인드). S1에서는 `--disallowedTools "Bash(*pytest*)"`로 에이전트의 pytest 실행을 막았다. DevKit 역할 정의상 테스트 실행은 Validator의 G5 몫이고(D12), 막지 않으면 G4 리뷰어가 pytest를 돌려 G5까지 가지 않기 때문이다(E2E-3에서 verifier가 G4 리뷰 중 pytest 실행 확인). 이 규칙이 묶음 명령과 `python3 -I -c "import pytest"`까지 막는지는 haiku 프로브로 먼저 확인했다.
결과적으로 verifier는 pytest 없이 코드를 손으로 추적해 결함을 잡았다(G4 FAILED). 그래서 G5 경로는 D27 방식으로 확인했다.

## D27. G5 경로는 "놓친 리뷰" 주입 포크로 검증 (2026-11-08)
G5는 G4 PASSED가 전제이므로, 실제 흐름에서 G5 FAILED는 G4 리뷰가 결함을 놓쳤을 때만 생긴다. S1의 실제 산출물(요구사항~코드·테스트)과 실제 verifier의 G1~G3 리뷰 파일(바이트 동일, 같은 target_hash)을 새 샌드박스로 옮기고, G4 승인 리뷰만 하네스가 썼다. 그 summary에 `[DRILL FAULT INJECTION ...]`을 명시해 두었고, 이 내용은 원장 해시에 묶인다. 이 상태에서 Validator가 실제 pytest를 돌려 G5 FAILED를 기록했고, 이어서 시딩 사실을 모르는 새 Claude 세션(S2)이 `/vmodel:rework`로 재작업을 수행했다. 주입은 G4 승인 하나뿐이며, 이후의 G4 재리뷰는 실제 verifier가 했다.
기각한 대안: (a) 시딩 결함을 리뷰어가 못 보게 위장하기 — 실험 조작이고, 통한다는 보장도 없다. (b) verifier 모델 교체 — 검증 대상인 플러그인을 바꾸는 것이다.

## D28. 결함 종료(`status: fixed`)는 수정과 함께, 증명은 원장이 (0.1.3)
defects.json은 G4/G5 입력이다(test_changes 리뷰, NO_WEAKENING). 0.1.2 스킬은 "Gate 통과 후 fixed로 바꾸라"고 지시했고, 그대로 하면 G4/G5가 STALE이 되어 리뷰 1회와 G4·G5 재실행이 더 든다. 실제 S2에서 그대로 일어났다(R00015~R00019). G4 verifier도 "이 Gate 뒤에 결함을 닫으라"는 info finding으로 같은 행동을 부추겼다.
조치: 스킬(start, rework), verifier 지침, VMODEL.md, ARTIFACTS.md에 "fixed는 수정과 같은 단계, 재리뷰 전에. 통과 후에는 defects.json을 건드리지 않는다"를 명시했다. 이때 `fixed`는 에이전트의 주장일 뿐이고, 종료 증거는 Validator가 원장에서 찾은 "실패 기록 이후 그 Gate의 첫 PASS"(`verified_by`)다.
기각한 대안: defects.json 해시에서 `status` 필드를 빼는 방식. manifest 의미를 바꾸고 Core를 더 크게 건드려야 해서 택하지 않았다.

## D29. 결함↔실패 테스트 추적은 원장에서 파생, 누락은 경고 (0.1.3)
S2의 DEFECT는 실패한 TEST 5개 중 3개만 `related`에 연결했지만 아무 장치도 이를 잡지 못했다. 이제 Validator가 DEFECT가 인용한 실패 기록에서 실패 TEST ID를 직접 꺼내 `failing_tests`, `unlinked_failing_tests`, `verified_by`를 계산하고, `status`(텍스트·JSON)·`lint`·`report`에 보여준다(`gates.defect_trace`).
누락을 BLOCKED로 막지 않은 이유: 막으면 링크를 하나 빠뜨릴 때마다 defects.json 수정 → G4 STALE → 리뷰 재실행 비용이 생기는데, 추적 정보 자체는 이미 원장에서 완전하게 얻을 수 있다. 원인이 모든 실패를 설명하는지라는 의미 판단은 verifier의 G4 체크리스트에 넣었다("root cause must explain every failing case"). 이것도 AI 리뷰이므로 기계 검증이 아니다.

## D30. `status`가 실패한 Gate의 실패 체크·실패 테스트를 보여준다 (0.1.3)
S2 오케스트레이터는 무엇이 실패했는지 보려고 `.vmodel/state/ledger.jsonl`을 `tail`로 직접 읽었다. 스킬은 "`VM status`로 실패 체크를 보라"고 했지만 0.1.2의 status는 실패 체크를 출력하지 않았다. 이제 FAILED/BLOCKED Gate에 `failed_checks`(ID, 상세, 항목 최대 8개)와 `failing_tests`가 붙고, 텍스트 출력에도 나온다.

## D31. 드릴에서 관찰했지만 고치지 않은 것 (문서화만)
- 오케스트레이터가 시스템 테스트(TEST-013)의 예시를 단위 테스트로 돌리려고 함수 이름에 TEST_001 토큰을 붙였다. G4.TEST_CODE는 ID당 함수가 하나 이상 있는지만 보기 때문에 명세와 다른 테스트가 그 ID로 추적된다. 의미 검토(G4 리뷰)의 몫으로 남긴다.
- auto 권한 모드에서는 스킬의 "한 번에 한 명령" 규칙을 어긴 묶음 명령(`VM=…; "$VM" …`, `cd`)과 python heredoc 쓰기가 분류기를 통과했다. heredoc으로 work-items 산출물을 쓰는 것은 guard의 문자열 판별 밖이다(D25). defects.json은 원래 에이전트가 쓰는 파일이고 리뷰·스키마 검증을 거치므로 신뢰 모델에는 영향이 없다. 다만 스킬의 "shell writes into .vmodel/ are blocked"는 보호 경로(state/evidence/config/lock)에 대해서만 맞는 말이다.
- 설계 단위가 하나면 모든 단위 테스트가 모든 REQ로 추적된다(E2E-3에 이어 재확인).

## D32. 결함 상태 모델 검토: 현행 `open/fixed` + 원장 파생 vs `OPEN → FIX_APPLIED → VERIFIED → CLOSED` (2026-11-08, 검토만, 구현 안 함)
배경: 0.1.3 실제 세션(drill-3, TEST_RESULTS §9)에서 F1 수정은 의도대로 동작했다. 에이전트는 수정과 같은 단계에서 `fixed`를 쓰고 재리뷰를 받았고, 통과 후에는 defects.json을 건드리지 않았다. 재작업 원장은 R00011~R00013 3건으로, 0.1.2 S2의 9건보다 적다. status는 수정 직후 `[fixed; not verified yet]`, G5 통과 후 `[fixed; verified by R00013]`를 보여 줬다. "고쳤다는 주장"과 "검증됐다는 사실"은 이미 따로 표시된다.

4단계 모델의 각 상태를 누가 쓰는지와 Gate 최신성에 주는 영향:
- OPEN(결함 기록)은 에이전트가 파일에 쓴다. 현행 `open`과 같다.
- FIX_APPLIED(수정 적용 주장)도 에이전트가 파일에 쓴다. D28 이후의 `fixed`가 바로 이 의미다. 수정과 같은 편집에서 바뀌므로 STALE이 추가로 생기지 않는다.
- VERIFIED(수정 후 그 Gate PASS)는 Validator가 확인하는 사실이다. 에이전트가 defects.json에 쓰면 G4/G5 입력이 바뀌어 F1이 그대로 재발한다. drill-3 프로브 P-F1에서 status 값 하나만 바꿔도 G4·G5가 STALE이 됐다. 따라서 VERIFIED는 반드시 원장에서 파생해야 하고, 현행 `verified_by`가 이미 그 역할을 한다.
- CLOSED(종료)를 에이전트가 쓰면 VERIFIED와 같은 STALE 문제가 생긴다. 사용자가 쓰면 사용자 결정의 자기 증명 문제(D25)가 생긴다.

발견한 구조적 문제: `verified_by`는 과거 사실이라 이후 입력이 바뀌어 G5가 STALE이 돼도 그대로 "verified by R00013"으로 나온다. P-F1에서 G4·G5가 STALE인데 status 표시가 `[open; verified by R00013]`이었다. 지금 표시만으로는 "검증된 적이 있다"와 "지금도 유효하다"를 구분할 수 없다. 4단계 모델의 VERIFIED와 CLOSED를 나누면 바로 이 차이를 담을 수 있다.

대안:
- (A) 현행 유지: 바꿀 것이 없다. 다만 위의 "지금도 유효한가"가 보이지 않고, `fixed`가 "검증됨"으로 읽힐 수 있다.
- (B) defects.json의 enum을 4단계로 확장: VERIFIED/CLOSED를 에이전트가 쓰게 되어 F1이 재발한다. 0.1.x defects.json이 스키마를 통과하지 못해 마이그레이션도 필요하다. **기각.**
- (C) 파일은 2단계 그대로 두고(`open`, `fixed`=FIX_APPLIED), 표시 상태를 Validator가 원장에서 파생한다. OPEN과 FIX_APPLIED는 `verified_by`가 없는 경우의 주장값이다. VERIFIED는 `verified_by`가 있지만 그 Gate가 지금 PASSED가 아닌 경우(재확인 필요), CLOSED는 `verified_by`가 있고 그 Gate와 상위 Gate가 현재 해시로 PASSED인 경우다. 주장과 파생이 어긋나면(예: 주장 `open`인데 검증됨) 주석으로 보여 준다. 스키마는 그대로라 기존 defects.json과 호환된다. status.py(Core)만 바뀌므로 버전을 올려야 하고, 재고정하면 이전 PASS가 한 번 STALE이 된다(업그레이드 절차와 같다). Gate 판정에는 쓰지 않는 표시 전용이다.
- (D) Validator가 원장에 `defect_closed` 기록을 남기는 사용자 전용 TTY 명령: 종료를 사람의 결정으로 묶을 수 있다. 하지만 UX 비용이 크고, 사용자 결정의 암호학적 결속(Extension)과 같은 문제라서 지금은 범위 밖이다.

권장: 다음 버전에서 (C). enum 이름 `fixed`는 유지하고 문서에서 "FIX_APPLIED(주장)"로 정의한다. CLOSED를 사람의 승인으로 만들어야 하면 (D)를 Extension의 사용자 결정 결속과 함께 다룬다.

## D33. 실패 TEST가 DEFECT에 연결되지 않을 때: 경고 vs 차단 (2026-11-08, 검토만, 구현 안 함)
실측: 0.1.3 실제 세션(drill-3)의 DEFECT-001은 실패 TEST 5개를 모두 `related`에 연결했다. `failed_checks`도 3개 모두 적었다. 0.1.2 S2에서는 5개 중 3개만 연결했다. 그래서 실제 세션에서는 미연결 경고 경로가 한 번도 실행되지 않았다. 같은 실제 원장에서 Validator만 돌린 프로브(P-F2)에서는 TEST-011·012를 빼자 Validator가 서명된 R00010에서 정확히 그 둘을 찾아냈다. status와 report에는 "NOT linked"가 표시됐고 lint는 종료 코드 1을 냈다. 동시에 G5 통과 뒤 링크를 보완하면 G4·G5가 STALE이 된다는 비용도 확인했다.

대안:
1. 경고만(현행): status·report·lint에 표시한다. 추가 비용이 없고, 추적 정보는 원장에서 완전히 파생되므로 보고서에서 사라지지 않는다. 대신 에이전트가 무시할 수 있고, defects.json 자체는 불완전하게 남을 수 있다.
2. 최종 완료(PARTIALLY_VERIFIED) 차단: 누락을 G5 통과 뒤에야 알게 된다. 그러면 defects.json 수정 → G4/G5 STALE → 재리뷰·재실행이 필요하고, 이는 P-F2에서 확인한 비용 그대로다. F1과 같은 낭비 구조를 다시 만든다. **기각.**
3. 재평가 전제 조건으로 차단: 결함 이후 첫 Gate 평가(보통 G4) 시 기록 없이 BLOCKED를 내고 누락 TEST를 보여 준다. 결함을 쓰는 시점, 즉 수정 전·리뷰 전에 잡으므로 스킬 순서(lint → 리뷰 → gate)를 지키면 STALE 비용이 0이다. 리뷰 뒤 gate에서 막히면 리뷰 1회가 무효가 된다. 실패 TEST가 없는 실패(G4 리뷰 reject, 정적 분석 실패)에는 해당하지 않는다. Core 변경이 필요하다.
4. `related`에서 TEST 연결을 요구하지 않고 원장 파생을 정본으로 삼기: 같은 정보를 두 번 적지 않는다. 대신 `related`의 의미가 바뀌고, 사람이 defects.json만 읽으면 실패 TEST가 보이지 않는다(보고서에는 보인다).

권장: 지금은 1을 유지한다. 실측 1회에서 0.1.3 지침만으로 5/5를 연결했고(0.1.2는 3/5), 차단의 이득이 아직 증명되지 않았다. 강제가 필요해지면 2가 아니라 3으로 간다. 그때는 "lint → 리뷰 → gate 순서에서 STALE 0회"와 "리뷰 후 차단 시 리뷰 1회 무효" 회귀 테스트를 먼저 만든다.

## D34. drill-3에서 관찰했지만 고치지 않은 것 (문서화만)
이번 검증에서는 코드 수정이 필요한 결함을 찾지 못했다. 아래는 Core나 측정 스크립트를 바꿔야 하는 항목이라서, 실전 검증 범위에서 제외하고 기록만 한다.
- guard 오탐: `cat ../../defects.json 2>/dev/null`처럼 `.vmodel`을 읽는 명령이 "shell로 .vmodel을 수정한다"는 이유로 거부됐다. `WRITE_VERBS`의 `[0-9]>(?!&)`가 `2>/dev/null`을 쓰기로 보기 때문이다(재현 확인). 막는 쪽으로 틀린 오탐이라 보안 문제는 아니고, 에이전트는 다음 호출에서 명령을 나눠 다시 읽었다. 다음 버전 후보는 `/dev/null`로 가는 리디렉션 예외와 그 회귀 테스트다(hook.py는 Core라서 버전을 올려야 한다).
- verifier가 리뷰 파일에 쓰는 `reviewed_at`은 실제 시각이 아니다. drill-3은 원장 `submitted_at`(12:56:31Z)보다 14분 뒤인 13:10:00Z를, S2는 `00:00:00Z`를 썼다. Gate는 이 값을 쓰지 않고 원장 시각이 정본이므로 신뢰 모델에는 영향이 없다.
- verifier가 백그라운드 서브에이전트로 실행되면 헤드리스 출력에 result 이벤트가 2개 생긴다. `claude_run.summarise`는 마지막 것만 가져가서 턴 수와 시간을 적게 기록했다(4턴·15초. 실제는 메인 11+4턴, 벽시계 77초). `total_cost_usd`는 세션 누적값이라 정확하다. 측정 스크립트의 한계로 기록한다.
- 샌드박스 `.claude/settings.json`의 allow 규칙 3개가 "workspace not trusted"로 무시됐다. S2와 같은 메시지이고, 헤드리스 드릴에서는 `--allowedTools`로만 허용이 적용된다. 실제 프로젝트(신뢰된 작업 공간)에서는 설치된 allow 규칙이 적용된다. 다만 이것을 헤드리스로 확인하지는 않았다.
- 메인 세션은 Validator 호출을 모두 단독 명령으로 실행했다(0.1.3 rework 스킬 규칙, S2는 `VM=…;` 묶음). 일반 읽기 명령은 여전히 `;`·`&&`·`|`로 묶었고 auto 모드가 허용했다. 스킬 규칙은 VM 호출에만 적용되므로 규칙 위반은 아니다.
- DEFECT-001 원인의 "부동소수점 나눗셈도 사용한다"는 사실이지만 실패 원인은 아니다. p·N이 정수이면 p·N/100은 정확히 표현된다. 핵심 원인(내림 + 1을 빼지 않음 → p·N/100이 N보다 작은 정수일 때 한 칸 뒤)은 실패 5건과 일치한다(`root_cause_check.py`).

## D35. 실패 TEST 추적 누락과 증거 인용 처리: P1 채택 (2026-11-08, 사용자 결정, 구현은 v0.1.4)
배경: D33에서 경고 유지(대안 1)와 재평가 전제 조건 차단(대안 3)을 비교했다. v0.1.3 릴리스를 확정하면서 코드를 다시 읽어 표시 쪽 빈틈 두 가지를 더 찾았다. 첫째, 인용한 실패 기록에 TEST별 결과가 없으면 DEFECT 줄이 `failing tests (ledger): -`가 되어 "실패 TEST 없음"과 "알 수 없음"이 구분되지 않는다. 둘째, 같은 WI의 실패하지 않은 gate 기록(예: PASSED)을 인용해도 정상 인용으로 처리된다. `defect_trace()`는 인용 중 가장 나중 기록을 종료 기준으로 삼기 때문에, PASSED 기록을 함께 인용하면 그 뒤의 엉뚱한 PASS가 `verified_by`로 표시된다. 사용자는 P1(차단 없이 경고 유지)을 택하고 아래 조건을 붙였다.

결정
1. 실패 TEST가 DEFECT `related`에 없으면 경고로 표시한다. Gate는 막지 않는다. D33의 대안 2(최종 완료 차단)와 대안 3(재평가 전제 조건 차단)은 채택하지 않는다.
2. 인용한 실패 기록에서 TEST별 실제 결과를 확인할 수 없으면 UNKNOWN으로 표시한다. 판정에는 서명된 기록만 쓰고 현재 tests.json은 쓰지 않는다. 대상은 테스트를 실행한 Gate(현재 G5) 기록 가운데 `executed_tests`가 없거나 빈 경우, 그리고 G5.TEST_MAPPING이 "not executed"로 적은 TEST ID다. 테스트를 실행하지 않는 Gate(G1~G4)의 실패 기록은 UNKNOWN이 아니라 "해당 없음"으로 표시한다. 그래야 G4 리뷰 reject 같은 실패마다 쓸모없는 경고가 붙지 않는다.
3. 실패하지 않은 기록을 실패 증거로 인용하면 유효한 증거로 인정하지 않는다. 유효한 실패 증거의 정의는 재작업 전제 조건(`gates.py`의 needs_defect)과 같다. 같은 WI의 서명된 gate 기록이면서 status가 FAILED이거나, 3회 동일 실패로 BLOCKED(`blocked_reason: three_consecutive_identical_failures`)인 기록이다. 3회 실패 BLOCKED 기록은 세 번째 FAILED 평가를 BLOCKED로 바꿔 쓴 것이라 TEST별 결과를 그대로 가진다. 그 밖의 인용은 무효 인용으로 표시하고 `failing_tests`와 `verified_by` 기준 기록 계산에서 뺀다. 그 밖의 인용이란 원장에 없는 ID, 다른 WI, gate 기록이 아닌 것, PASSED·REVIEW_REQUIRED·환경 원인 BLOCKED 기록이다.
4. 증거 오류와 추적성 누락을 구분한다.
   - 증거 오류(error)에는 두 가지가 있다. 하나는 증거 무결성 오류로, 원장 서명·해시 체인·head·외부 앵커 불일치, 또는 인용된 실패 기록의 증거 파일이 원장에 기록된 해시와 다른 경우다. 다른 하나는 3의 무효 인용이다.
   - 추적성 경고(warning)에는 1의 미연결 실패 TEST와 2의 UNKNOWN이 있다.
   - status(텍스트·JSON), lint, report는 같은 분류 이름을 쓴다. lint 종료 코드는 지금처럼 오류든 경고든 하나라도 있으면 1이고, 출력에 분류를 붙인다.
5. 경고가 있더라도 최종 보고에서 누락 사항을 확인할 수 있어야 한다.
   - `vmodel report` 보고서에는 결함 추적 점검 절을 항상 넣는다. 항목이 없으면 "없음"을 적어서 "점검했더니 없음"과 "절이 빠짐"을 구분한다.
   - status의 WI 요약 줄에 오류·경고 개수를 붙인다. WI 상태 값(PARTIALLY_VERIFIED 등)은 바꾸지 않는다.
   - rework·start 스킬의 마지막 보고 단계에 "status·report의 증거 오류와 추적성 경고를 빠짐없이 옮긴다"를 넣는다.
6. Gate 판정은 바꾸지 않는다. 원장 무결성 실패는 지금처럼 모든 Gate를 BLOCKED로 만들고, 증거 파일 불일치는 지금처럼 audit FAILED가 된다. 무효 인용만 있는 DEFECT는 지금도 재평가 전제 조건을 통과하지 못한다. 전제 조건은 직전 실패 기록 ID 자체의 인용을 요구하기 때문이다(`gates.py`, "rework record missing"). 그래서 무효 인용에 Gate 차단을 새로 더하지 않는다.

근거: 대안 1을 유지하는 이유는 D33과 같다. 실제 세션 1회에서 0.1.3 지침만으로 5/5를 연결했고, 차단의 이득은 아직 증명되지 않았으며, 추적 정보는 원장에서 완전히 파생된다. 세 분류는 성격이 달라서 따로 둔다. 무결성 오류는 신뢰 경계 위반이므로 Gate가 막히고 사용자에게 보고해야 한다. 무효 인용은 에이전트가 defects.json을 고쳐야 하는 기록 오류다. 무효 인용은 Gate 통과 수단은 아니지만, 그대로 두면 표시와 종료 증거(`verified_by`)를 오염시킨다. 추적성 경고는 보완을 권하는 품질 문제다.

다시 검토할 조건: 반복된 실제 세션에서 미연결이 관찰되고 경고가 보완으로 이어지지 않으면 대안 3을 다시 검토한다. 그때는 D33에 적은 회귀 테스트를 먼저 만든다.

구현·회귀 테스트 계획은 PLAN.md §v0.1.4 항목 3에 있다. v0.1.3 코드에서 실패하는 재현 테스트를 먼저 쓴 뒤 고친다.

## D36. v0.1.4 구현 결정과 독립 검토 결과 (2026-11-09, 구현 완료)
사용자 지시(2026-11-08): 정책 A(증거 무결성), B(N/A·UNKNOWN), C(lint 종료 코드 유지, 출력에 ERROR/WARNING 구분)를 승인하고 D32 (C), D34 guard 오탐, D35 P1을 구현한다.

절차. "이 작업에도 G1~G5를 적용하라"는 지시와 SPEC §5.8(DevKit 개발을 DevKit Validator로 승인하지 않음)을 함께 지키기 위해 절차는 G1~G5를 따르고 판정은 독립 하네스가 했다(`docs/v0.1.4/WORKITEM.md` §0). RED는 "고치기 전에 실패"가 아니라 불변 릴리스 0.1.3 코어를 대상으로 `scripts/red_green.py`가 클래스 접미사(Red/Char/Invariant/Accept)로 기계 대조했다. 항목마다 별도 컨텍스트의 Verification Agent가 읽기 전용으로 검토했고, 지적은 재현해 확인한 것만 RED 테스트로 고정한 뒤 고쳤다.

F2 guard (hook.py)
- Bash 명령에서 쓸 수 없는 리디렉션(정확히 `/dev/null`로 가는 출력, fd 복제·닫기, 단순 입력)을 지운 뒤 쓰기를 판정한다. `/dev/null` 뒤는 공백·탭·개행·`;&|)`·끝만 인정한다. bash 실측: `2>/dev/null"x"`, `` 2>/dev/null`…` ``, `>/dev/null#c`, `/dev/null\r`는 다른 경로다.
- 0.1.3이 놓친 쓰기를 새로 잡는다: `&>`, `&>>`, `>&파일`·`1>&파일`(n 생략 또는 1), `x2>&파일`(숫자로 끝나는 일반 단어), 동사와 플래그 사이 리디렉션(`sed 2>&1 -i`, `find . 2>&1 -delete`). bash 실측: `2>&파일`은 ambiguous redirect라 쓰지 않는다.
- 저장소 전체 삭제 규칙은 원문과 정규화한 명령 양쪽에 적용한다. PowerShell 도구에는 예외를 적용하지 않는다(PowerShell 5.1은 `/dev/null`을 `C:\dev\null`로 해석). Windows `NUL`, PowerShell `$null`은 범위 밖이며 기존처럼 차단한다.
- 독립 검토가 찾은 것: 처음 수정본은 `sed >/dev/null 2>&1 -i …`처럼 동사·플래그 사이에 `/dev/null`이 끼면 0.1.3이 막던 쓰기를 통과시켰다(보호 약화, bash로 원장 변조 확인). 정규화 범위를 넓혀 고쳤고, 재검토 퍼저 2,483건에서 0.1.3 대비 손실 0이다. 이 밖에 `2>&1`을 따옴표 안에서 쓰기로 본 새 오탐, `\r`, PowerShell 적용, `x2>&파일`(0.1.3부터 있던 빈틈)도 고쳤다.
- 알려진 오탐(불확실하므로 차단 유지): 따옴표 안의 `&>` 문자열(`grep '&>' …`), fd 복제 바로 뒤의 따옴표·백틱(`bash -c "echo x >&2"`; `>&2"y"`는 실제로 파일 `2y`를 만든다).
- 두 버전 공통 미탐(기록만, 이번 범위 밖): `python3 - <<EOF`, `gzip`, `sort -o`, `curl -o`, `uniq a out`, `find -fprint`, PowerShell 별칭 `ni`/`ri`/`sc`/`ac`/`clc`. guard는 최선 노력 보호이며 OS 격리가 아니다(SPEC §5.7).

F3 결함 추적 점검 (gates.py, status.py, cli.py, runner.py)
- 유효한 실패 증거 = 재작업 전제 조건과 같은 `is_failure_record()`(FAILED, 3회 동일 실패 BLOCKED). preconditions()도 같은 함수를 쓰도록 바꿨고 식은 그대로다(Gate 판정 불변식 테스트로 확인).
- TEST별 결과는 서명 기록만 본다: G5는 recorded/partial/unknown, G1~G4는 not_applicable. UNKNOWN 경고는 결함당 하나이며, 다른 유효 인용 기록에 결과가 있는 TEST는 뺀다.
- 무결성 오류는 증거 기록을 audit·verify-evidence와 같은 `runner.check_evidence()`로 검사한다. 인용된 실패 기록이나 검증 PASS 기록의 증거가 원장과 다르면 `verified_by`를 보류한다(`verification_withheld`). 원장은 고치지 않는다.
- 독립 검토가 찾은 것: (주요) DEFECT가 G5 실패와 G4 실패를 함께 인용하면 마지막 인용 기록의 Gate(G4)로 종료를 판단해, G5가 아직 FAILED인데 G4 재PASS가 `verified_by`가 되고 F1에서 CLOSED로 보였다. 0.1.3부터 있던 기준 선택 방식이다. 종료 Gate를 인용된 실패 중 가장 하위 Gate로 바꿨다(G5 PASS는 G4 PASSED를 전제로 한다). (주요) 형식이 깨진 증거 record.json 하나로 status·lint·report가 종료 코드 2로 죽었다. 0.1.3의 status는 증거를 읽지 않았으므로 새 회귀였고, 고쳤다(audit·verify-evidence의 같은 크래시도 함께 사라졌다). (부) 3회 실패 사슬에서 같은 누락을 세 번 셈, 인용이 없는 결함이 점검에 안 나옴 → 고침. 재검토에서 이 묶기 수정이 새 회귀를 만든 것을 찾았다: 결과가 있는 오래된 실행을 함께 인용하면 더 최근 실행의 UNKNOWN이 가려졌다. TEST마다 가장 최근 인용 기록의 결과를 쓰도록 고쳤고, 경고의 `records`도 아직 결정권이 있는 실행만 적는다.
- status JSON 호환: 0.1.3 키는 모두 남는다. 의미가 바뀐 것은 둘이다. `failing_tests_by_record`는 유효 인용만 담고, `verified_by`는 유효 인용과 무결성을 통과한 경우에만 있다.

F1 종료 상태 (status.py)
- OPEN, FIX_APPLIED, VERIFIED, CLOSED는 D32 (C) 그대로다. 원장 무결성 실패로 판정할 수 없을 때는 UNKNOWN을 쓴다. "확인할 수 없으면 UNKNOWN"(정책 B)과 같은 원칙이며, 이때 "아직 검증 안 됨"으로 단정하지 않는다.
- VERIFIED는 그 Gate가 지금 PASSED가 아니라는 뜻이다(STALE·FAILED·BLOCKED). 텍스트는 항상 현재 Gate 상태를 함께 보이고, STALE·FAILED면 re-verify, BLOCKED면 차단 해소를 안내한다. 재실행 뒤에는 현재 PASS 기록을 `G5 PASSED (R…)`로 함께 표시한다.
- 검토 의견 중 반영하지 않은 것: VERIFIED라는 이름이 "완료"로 읽힐 수 있으니 바꾸자는 의견. 상태 이름은 사용자 지시와 D32에서 정한 것이라 유지했다. 바꾸려면 사용자 결정이 필요하다.

버전·증거 관리
- 0.1.4는 원장 기록 형식, manifest 계산, Gate 판정을 바꾸지 않는다. 0.1.3 릴리스와 같은 이력을 돌린 투영(상태·체크·실패 서명·TEST별 결과)과 같은 프로젝트의 Gate별 manifest가 일치한다(`test_version_compat`).
- 증거 검증은 코어 해시와 무관하다(HMAC 서명 + 파일 해시). 0.1.3이 서명한 원장·증거는 0.1.4에서 audit·verify-evidence가 그대로 통과하고, 기존 기록의 `validator.version`·`core_hash`는 0.1.3 값으로 남는다. 서명된 증거를 새 해시로 다시 쓰는 경로는 없다.
- 업그레이드 절차는 SPEC §11 그대로다. 사용자가 TTY에서 재고정(원장에 lock 기록 추가)하면 이전 PASS는 STALE이 되고, 재검증한 새 기록에 0.1.4 버전·해시가 붙는다. 한계: 재고정 전에는 새 코어가 무결성 검사로 모든 Gate를 BLOCKED로 본다. 거꾸로 0.1.4로 재고정한 프로젝트를 0.1.3으로 열어도 같은 이유로 BLOCKED다(다운그레이드도 재고정 필요).

## D37. 결함 표시 상태 6종: VERIFIED를 없애고 REVERIFY_REQUIRED·VERIFICATION_FAILED로 나눈다 (2026-11-09, 사용자 지시, 0.1.4 공개 전 재빌드)
배경: 0.1.4 첫 빌드(core `b1fee43f…`)의 VERIFIED는 "검증된 적은 있지만 그 Gate가 지금 PASSED가 아님"이었다. 그래서 Gate가 STALE이거나 다시 FAILED여도 상태 칸에 완료처럼 읽히는 VERIFIED가 찍혔다. 독립 검토가 지적했고(D36), 사용자가 상태 이름과 규칙을 정했다: OPEN, FIX_APPLIED, REVERIFY_REQUIRED, VERIFICATION_FAILED, CLOSED, UNKNOWN. 저장 구조(`open`/`fixed`)는 유지하고, 상태는 원장과 현재 Gate 결과에서 파생하며, 과거 검증 성공 이력은 따로 남긴다. STALE이면 VERIFIED·CLOSED로 표시하지 않고, 현재 검증이 실패하면 완료로 표시하지 않으며, 원장 무결성이 깨지면 추측하지 않고 UNKNOWN이다. Gate 판정 정책과 서명된 증거는 바꾸지 않는다.

파생 규칙 (`status.closure_view`, 앞 조건이 우선)
1. UNKNOWN: 원장 무결성 실패(서명·체인·head·앵커).
2. VERIFICATION_FAILED: 결함이 실패를 인용한 Gate마다 첫 인용 실패 이후 마지막 결정적 평가(PASSED 또는 실패)를 보고, 그중 하나라도 실패(FAILED, 또는 3회 동일 실패 BLOCKED = `is_failure_record`)인 경우. REVIEW_REQUIRED와 환경 BLOCKED는 3회 실패 카운터(`consecutive_same_failures`)처럼 건너뛴다. Gate마다 보므로 상위 Gate(G4)의 재통과가 아직 다시 돌리지 않은 하위 Gate(G5)의 실패를 가리지 않는다.
3. UNKNOWN: 그 Gate의 검증 PASS가 있지만 그 PASS나 인용된 실패 기록의 증거가 원장과 다름(`verification_withheld`).
4. CLOSED: `verified_by`가 있고 그 Gate가 현재 입력으로 PASSED(상위 Gate가 PASSED가 아니면 `gate_state`가 이미 STALE을 낸다).
5. REVERIFY_REQUIRED: `verified_by`가 있지만 그 Gate가 지금 PASSED가 아님(STALE, REVIEW_REQUIRED, BLOCKED).
6. FIX_APPLIED / OPEN: 검증 없음, 주장 `fixed` / `open`.

과거 성공 이력: `verified_by`(0.1.3과 같은 의미: 가장 최근 인용 실패 이후 종료 Gate의 첫 PASS)는 모든 상태에서 그대로 남는다. 새 키는 `verification_history`(첫 인용 실패 이후 종료 Gate의 PASS 기록 목록), `last_verification`(위 2의 마지막 결정적 평가: 기록·Gate·상태·실패 여부), `closure_action`(다음 조치: reverify, rework, unblock, resolve_block, check_integrity 또는 없음)이다. 텍스트에서 "verified by R…"는 CLOSED에만 쓴다. 다른 상태의 과거 성공은 "previously passed in R… (last PASS R…)"로 쓰고, 증거가 보류된 PASS는 과거 성공으로 치지 않고 "PASS R… withheld"로만 쓴다(claim_note와 report도 같다).

판단이 필요했던 지점
- 재평가 실패를 같은 결함에 다시 인용하는 경우(재작업 전제 조건이 그 인용을 요구한다): 기준을 "가장 최근 인용 실패"로 잡으면 상태가 FIX_APPLIED로 돌아가 "검증 대기"처럼 보인다. 그래서 VERIFICATION_FAILED는 첫 인용 실패 이후 마지막 결정적 평가로 판단하고, 다음 PASS에서 풀린다.
- 인용한 상위 Gate의 실패(예: G5 실패 결함의 수정이 G4 재리뷰에서 거절되고 그 기록을 같은 결함에 인용): 종료 Gate(G5)만 보면 FIX_APPLIED("검증 대기")가 된다. 결함이 인용한 Gate 전체를 보므로 VERIFICATION_FAILED이고, 그 Gate가 다시 PASS하면(다른 인용 Gate에 남은 실패가 없을 때) 재검증이 그 단계를 넘어선 것이므로 FIX_APPLIED, 종료 Gate PASS에서 CLOSED다. 결함이 인용하지 않은 Gate(다른 결함 소유)의 실패는 그 결함 기준으로 보지 않는다. 대신 종료 Gate가 STALE이 되므로 CLOSED는 아니다.
- 알려진 한계(재검토 지적, 고치지 않음): G5 실패 뒤 수정 없이 G4가 다시 거절되고 새 결함이 두 기록을 함께 인용하면, 수정을 시도하지 않았어도 VERIFICATION_FAILED("G4 re-verification … FAILED")로 보인다. "수정이 G4에서 거절된 경우"와 원장 이력이 같아서 원장만으로는 구분할 수 없다(주장 `open`/`fixed`는 검증되지 않은 값이라 판단에 쓰지 않았다). 어느 쪽이든 완료로 보이지 않는다.
- `verification_history`는 서명 원장의 PASS 기록 목록이라, 증거가 보류된 PASS도 그대로 들어 있다. 보류된 기록은 `verification_withheld`로 알 수 있다. 목록 형식을 바꾸지 않으려고 표시를 따로 달지 않았다(텍스트에서는 과거 성공으로 쓰지 않는다).
- Gate 단위 판단(보수적): 종료 Gate에 다른 결함 소유의 실패가 새로 생겨도, 이 결함은 그 Gate의 마지막 평가가 실패이므로 VERIFICATION_FAILED가 된다. 회귀인지 다른 결함인지는 기계적으로 가리지 않고, 완료로 보이지 않는 쪽을 택했다.
- 증거 보류: 첫 빌드는 FIX_APPLIED("not verified")였다. 서명 원장에는 PASS가 있으므로 "검증 안 됨"은 추측이다. 정책 B("확인할 수 없으면 UNKNOWN")에 따라 UNKNOWN으로 바꿨다. 다만 마지막 평가가 실패면 그 사실은 서명 원장으로 확정되므로 VERIFICATION_FAILED가 앞선다.
- Validator Core 불일치(재고정 전)로 모든 Gate가 BLOCKED인 경우: 원장 무결성 실패가 아니므로 UNKNOWN이 아니라 REVERIFY_REQUIRED(또는 마지막 재검증이 실패였으면 VERIFICATION_FAILED)이고, 조치는 resolve_block("resolve the block first")이다. 재고정하면 STALE → 재검증이다.
- 3회 동일 실패 BLOCKED는 실패이므로 VERIFICATION_FAILED이고, 그 Gate가 지금도 그 사유로 BLOCKED일 때만 조치가 unblock(사용자 TTY)이다. `vmodel unblock`은 3회 실패 차단만 푼다. 사용자가 풀면 rework다.
- 주장 `open`인데 원장에 PASS가 있다는 주석(`claim_note`)은 CLOSED("verified by")와 REVERIFY_REQUIRED("passed … (no longer current)")에서만 단다. VERIFICATION_FAILED에서 "verified"라는 주석은 오해를 부른다.

호환
- defects.json 스키마·enum 불변. status JSON의 0.1.3 키와 0.1.4 첫 빌드 키는 모두 남는다(`closure_action`, `verification_history`, `last_verification`은 추가). `closure_state` 값에서 VERIFIED가 사라지고 두 값이 생겼다. 0.1.4는 아직 공개(태그·푸시)하지 않았으므로 이 값을 쓰는 외부 사용자는 없다. `closure_gate_record`는 CLOSED·REVERIFY_REQUIRED에서 현재 Gate 기록, VERIFICATION_FAILED에서 실패한 재평가 기록이다.
- 텍스트: CLOSED 줄(`verified by R…, G5 PASSED`)과 report의 `DEFECT-001 [fixed — verified by R…]`(0.1.3 문구)는 그대로다. 기존 하네스 103개는 고치지 않았다.
- 첫 빌드용 0.1.4 테스트 중 기대값을 바꾼 것(상태 이름 변경이 원인): `test_defect_closure`의 7개 메서드(STALE·상위 변경·report·session-start·BLOCKED → REVERIFY_REQUIRED, 통과 뒤 실패 → VERIFICATION_FAILED, 증거 보류 → UNKNOWN)와 `test_version_compat` 1곳(재고정 직후 → REVERIFY_REQUIRED).
- 스킬(start, rework)의 VERIFIED 설명을 새 상태 설명으로 바꿨다. verifier 지침에는 상태 이름이 없다.

독립 검토: 첫 수정본(`73d158e`)을 별도 컨텍스트의 검토자가 읽기 전용으로 보고 부 지적 4건을 냈다(교차 Gate 실패가 FIX_APPLIED, REVIEW_REQUIRED가 실패를 지움, 무결성 BLOCKED에서 unblock 안내, 보류 PASS를 과거 성공으로 표시). 모두 `73d158e`에서 실패하는 테스트로 재현한 뒤 `c4e4da5`에서 고쳤다. Gate 단위 판단은 보수적이라 유지했다. `c4e4da5` 재검토: 주요 0, 지적 1~4 해결 확인. 새 지적 중 "상위 Gate 재통과가 하위 실패를 가려 같은 원장에서 결함끼리 표시가 엇갈림"(nit 2건)은 재현 후 Gate별 판단으로 고쳤고, `closure_action` 표기를 `reverify`로 통일했다. 교차 Gate 증상 동시 인용(부)과 보류 PASS의 JSON 표시(nit)는 위 한계로 남겼다.

검증: RED는 첫 0.1.4 빌드를 해시 대조 후 보존한 사본 대상(`scripts/red_green.py`), GREEN·전체 회귀·실제 세션은 TEST_RESULTS §11. Core가 바뀌었으므로 공개 전 같은 버전으로 재빌드했다(`release.py --force`, 중간 `144428fb…`(`73d158e`)·`f837a465…`(`c4e4da5`), 최종 `sha256:5dd1d010…`(`e0358a5`)).

## D38. 업그레이드 때 DevKit 권한 규칙을 새 릴리스로 옮긴다: 재고정 한 번, 추가 → 재고정 → 제거 (2026-11-09, 사용자 지시, v0.1.5 후보)
배경: `install`은 `.claude/settings.json`에 릴리스 절대경로가 든 규칙(Core deny `Edit(//<root>/**)`, CLI allow 2개)을 쓴다. SPEC §11의 업그레이드(새 릴리스로 `lock --accept-current`)는 lock과 원장만 바꿔서, 규칙이 이전 릴리스를 가리킨 채 남았다(새 Core는 guard만 보호, 새 CLI allow 없음). README의 다른 절차(옛 `uninstall` → 새 `install`)는 두 명령 사이에 DevKit deny 규칙이 하나도 없다. 새 릴리스로 `install`을 하면 uninstall을 권해서 그 절차로 유도했다. 0.1.3 → 0.1.4 실제 릴리스 사본으로 세 가지를 모두 재현했다(`test-results/v0.1.5/repro-0.1.3-to-0.1.4.json`). 덧붙여 `repin_lock`이 lock을 먼저 쓰고 원장에 기록하므로, 원장 기록이 실패하면 lock만 바뀐 채 남는다(테스트로 재현).

결정
1. 업그레이드 명령은 새로 만들지 않고 기존 사용자 전용 단계 `lock --accept-current`(TTY)가 규칙 이동까지 한다. 절차가 두 단계가 되면 하나를 빠뜨려 같은 문제가 다시 생긴다. guard의 USER_ONLY(`accept-current`)가 이미 에이전트를 막는다.
2. DevKit 규칙은 설치 기록의 `added_deny`·`added_allow` 문자열로만 식별한다. 경로 패턴으로 추정하지 않는다. 그래서 이전 릴리스 경로를 언급하는 사용자 규칙, 설치 전부터 있던 DevKit과 같은 문자열은 사용자 소유로 남는다. 제거는 문자열마다 한 번만 한다(첫 번째 것. 설치가 DevKit 규칙을 끝에 붙이고 사용자의 같은 문자열은 보통 그 뒤에 추가되므로). deny 규칙은 보호 하한이라 사용자가 지웠어도 다시 넣고 확인 전에 보여 준다. allow 규칙은 권한 부여라서, DevKit이 추가했던 이전 릴리스의 같은 자리 규칙(`validator_allow_rules`의 순서)을 사용자가 지웠으면 새 릴리스 것을 다시 허용하지 않고(`keep_removed_allow`, 검토 지적 5), 그 결정을 설치 기록 `declined_allow`로 다음 업그레이드에 이어 간다(이전 자리 규칙이 지금도 없을 때만. 사용자가 다시 넣었으면 새로 허용한다). DevKit이 소유한 적이 없는 자리(0.1.0·0.1.1 기록처럼 `added_allow`가 없는 경우)는 추가한다(재검토). 설치 기록의 `added_*` 순서는 설치 때처럼 settings에 놓인 순서를 따른다.
3. 순서: TTY 확인(설정을 읽기 전, 없으면 종료 코드 3) → 쓰기 없는 검사(settings·설치 기록을 읽을 수 있는지와 형식, Validator 무결성, 서명 키·원장 전체 검증, 보여 준 계획(계획 없음 포함)과 지금 파일이 같은지) → 백업(`.vmodel/install/backup/upgrade-<시각>/`, 생성 deny 규칙 `Edit(/.vmodel/install/**)`로 보호) → 설치 기록에 새 규칙 소유권 → settings에 새 규칙 추가 → 재고정(서명된 원장 lock 기록 → lock 파일) → 이전 규칙 제거와 설치 기록 확정. 모든 파일은 원자적 교체(`write_json`)로 쓴다. 어느 시점에 멈춰도 settings에는 이전 규칙이나 새 규칙 중 적어도 하나가 있다. 소유권을 settings보다 먼저 적는 이유는, 그 사이에 프로세스가 죽어도 재실행이 새 규칙을 DevKit 것으로 알기 때문이다.
4. `repin_lock`은 원장 기록을 먼저, lock 파일을 나중에 쓴다(lock은 서명 기록 없이 바뀌지 않는다. 0.1.4는 반대 순서라 원장 기록이 실패하면 lock만 바뀌었다). 실패나 중단(Ctrl-C 포함 BaseException)이 나면 원장을 다시 읽는다. 원장이 그대로면 메모리 스냅샷으로 lock → settings → 설치 기록 순서로 바이트 그대로 복원한다. settings 복원이 실패하면 설치 기록은 상위 집합 소유로 남겨 settings에 남은 DevKit 규칙이 사용자 소유로 둔갑하지 않게 한다. 원장이 늘었거나 읽을 수 없으면(예: 원장 기록은 서명됐는데 앵커 쓰기가 실패) 되돌리지 않고 이전+새 규칙 상위 집합으로 남긴 채 그 사실을 알린다. 재고정 뒤 제거 단계 실패도 되돌리지 않는다. 두 경우 모두 종료 코드 2이고 같은 명령을 다시 실행하면 마무리된다.
5. 멱등: 바꿀 것이 없으면 settings·설치 기록을 쓰지 않고 백업도 만들지 않는다(재고정 자체는 지금처럼 원장에 lock 기록을 하나 더한다). 같은 릴리스로 `install`을 다시 하면 지금처럼 거부한다. 다른 릴리스가 설치한 프로젝트면 uninstall 대신 이 재고정을 안내한다.
6. settings를 해석할 수 없으면(JSON 오류, 객체가 아님, `permissions`·`deny`·`allow` 형식 오류) 재고정도 하지 않는다. 0.1.4는 이 경우에도 재고정을 했지만, 그러면 규칙이 다시 이전 릴리스에 남는다. 설치 기록이 없는 프로젝트(`init`만)는 settings를 건드리지 않고 지금처럼 재고정만 한다.
7. 확인 문구 전에 이전·새 릴리스, 추가·제거할 규칙, 다시 허용하지 않는 allow 규칙, "직접 추가한 규칙은 그대로"를 출력한다. 출력 후 확인을 기다리는 사이 settings나 설치 기록이 바뀌면(설치 기록이 새로 생긴 경우 포함) 적용하지 않는다. 원장 잠금을 다른 프로세스가 잡고 있으면 최대 30초 기다린다는 안내를 출력한다. 하위 명령 옵션의 축약(`--accept`)은 받지 않는다(guard의 사용자 전용 문자열 검사 `accept-current`를 피하지 못하게, cli.py만 변경).
8. 바꾸지 않은 것: `hook.py`(guard), Gate 판정, 원장 기록 형식, manifest 계산, `uninstall`. `install`은 병합 방식이 같고 생성 deny 규칙이 하나(`Edit(/.vmodel/install/**)`) 늘었으며, 다른 경로나 다른 버전이 설치한 프로젝트에서는 uninstall 대신 재고정을 안내한다. 0.1.4의 `uninstall`도 0.1.5가 갱신한 설치 기록을 그대로 읽어 원래 사용자 settings를 복원한다(교차 버전 테스트).

기각한 대안: (a) 별도 `vmodel upgrade` 명령 — 재고정과 따로 실행하면 빠뜨리기 쉽다. (b) 경로 패턴으로 이전 릴리스 규칙을 찾아 바꾸기 — 사용자 규칙을 지울 수 있다. (c) 이전 규칙을 먼저 지우고 새 규칙 추가(uninstall → install) — 보호 공백. (d) 이전 규칙을 남겨 두기 — 쓰지 않는 CLI에 대한 allow가 남고, 설치 기록이 실제 settings와 어긋난다.

한계: 0.1.4 이하로 내리는 다운그레이드는 그 릴리스에 설정 갱신이 없어 자동화하지 못한다(SPEC §11 수동 절차, 그 사이 규칙 공백). 마켓플레이스로 등록해 Claude Code가 플러그인을 다른 경로(캐시)에서 실행하면 규칙이 가리킬 경로는 미검증이다(TEST_RESULTS §6과 같은 미검증 항목). Windows에서 Claude Code가 settings.json을 연 채로 있으면 원자적 교체가 실패할 수 있다(그 경우 재고정 전 실패로 복원된다, 미실측). `.claude/settings.json`은 G4/G5 manifest에 포함되므로 업그레이드로 settings가 바뀌면 G4/G5가 STALE이 되는데, Core 해시 변경으로 어차피 모든 PASS가 STALE이라 추가 비용은 없다. (D40에서 정정: 재실행 비용은 같지만 G4 리뷰 대상 해시가 바뀌어 G4 verifier 리뷰를 다시 받아야 한다.)

독립 검토: 첫 수정본(`0e691d0`)에서 지적 12건을 받아 재현 테스트(`tests/test_upgrade_review.py`)로 고정한 뒤 고쳤다. 재검토(`c57f7c5`)는 지적 5의 수정이 0.1.2 이전 기록을 오판하는 부 지적 1건과 nit 3건을 냈고, 같은 방식(`tests/test_upgrade_review2.py`)으로 고쳤다. 처리표는 `docs/v0.1.5/WORKITEM.md` §7. 원장 증가 판단은 개수가 아니라 우리 lock 기록(사유·새 core 해시) 유무로 하고, 롤백 중에는 SIGINT를 무시한다. 세 번째 확인(`be372f4`)의 부 지적 1건(사용자가 다시 넣은 규칙을 남은 `declined_allow`가 보류)과 nit 1건도 같은 방식(`tests/test_upgrade_review3.py`)으로 고쳤다. 반영하지 않은 것: 같은 문자열 중 첫 번째 제거(위 2), 0.1.5 업그레이드 뒤 이전 CLI로 재고정할 때의 deny 공백(다운그레이드 수동 절차의 한계).

검증: `docs/v0.1.5/WORKITEM.md`, TEST_RESULTS §12.

## D39. G6 Integration Verification 설계 결정안 (2026-11-09, 검토만, 사용자 결정 대기, 구현 안 함)
PLAN M5의 "먼저 결정하고 DECISIONS에 남길 것" 네 가지에 대한 결정안이다. 상세(대안별 장단점, G1~G5 호환, 구현·테스트 영향, 체크 초안)는 `docs/g6/G6-DESIGN-PROPOSAL.md`.
1. 실행 명령: 권장 E. config `integration_test`(argv에 `{junit}`, timeout_s)를 선택 키로 두고, 없으면 G6이 `unit_test` 명령을 직접 다시 실행해 integration ID만 판정한다. 증거에 어느 명령인지 남긴다. 새 `init`은 분리 기본값을 쓴다. G5 판정은 바꾸지 않는다. 기각 후보: G5 증거 재사용(자기 실행 증거 원칙 위반), Validator의 `-k` 선택(언어 중립 위반).
2. 테스트 코드 확인 위치: 권장 A. G4.TEST_CODE를 integration ID까지 넓히고 G4 리뷰 체크리스트에 통합 적합성(실제 provider·consumer 연결, 검증 대상 IF 목 대체 금지)을 넣는다. G6은 AI 리뷰 없는 기계 판정이며 `gates.json`의 G6 reviewer 표기(`vmodel:verifier`)를 고친다. D12와 같은 구조.
3. IF 0개: 권장 A+B. IF 0개이고 integration 명세도 0개일 때만 N/A. 기록 상태는 PASSED, `applicability: not_applicable`과 사유(`na_reason`, 없으면 G2에서 리뷰된 `integration_test_strategy.approach`)를 남기고 실행 체크는 skip. 표시는 `PASSED (N/A: no interfaces)`. integration 명세가 있으면 실행한다. `na_reason` 필수화는 하지 않는다(기존 WI의 G2 재리뷰 비용). 대안 D(새 상태 NOT_APPLICABLE)는 상태 머신 변경이 넓어 권하지 않는다.
4. 업그레이드 영향: 권장 A. G6 구현 버전에서 기존 PARTIALLY_VERIFIED WI가 G6 평가 전까지 IN_PROGRESS로 보이는 것을 의도된 동작으로 문서화한다. 업그레이드는 Core 해시 변경으로 어차피 G1~G5 재검증이 필요하고, IF 0개 WI는 G6이 N/A로 끝난다. grandfather·자동 평가·프로파일 버전은 권하지 않는다.
버전은 0.2.0(PLAN 제안). 결정되면 이 항목을 확정본으로 바꾸고 M5에 착수한다.

## D40. v0.1.5 확정과 업그레이드 리뷰 비용 정정 (2026-11-09, 사용자 조건부 승인)
사용자 결정: 필수 검증이 통과하면 v0.1.5를 확정한다(`main` fast-forward, 최종 검증 커밋에 annotated 태그 `v0.1.5`, 기존 태그·릴리스 기록 불변, 원격 푸시 없음). 검증 결과는 TEST_RESULTS §13: 릴리스 0.1.0~0.1.5 사본·기록·소스 해시와 버전 문자열 일치, 0.1.4 → 0.1.5 실제 사본 업그레이드의 모든 쓰기 지점과 중단 지점에서 권한 공백 없음·사용자 규칙 유지, 릴리스 사본 대상 업그레이드·호환 테스트 42/42, 깨끗한 worktree WSL 225/225. 필수 검증 실패가 없어 확정했다.

정정: D38 한계 절의 "업그레이드로 settings가 바뀌어 G4/G5가 STALE이 되는 데 추가 비용은 없다"는 재실행 비용에만 맞다. `.claude/settings.json`은 G4/G5 코드 manifest에 들어 있고 G4 리뷰는 그 manifest 해시를 대상으로 하므로, 0.1.5 업그레이드 뒤 G4는 verifier 리뷰를 다시 받아야 REVIEW_REQUIRED에서 벗어난다(0.1.4 → 0.1.5 프로브로 확인, 0.1.3 → 0.1.4는 settings가 그대로라 리뷰 없이 통과했다). 판정 규칙·원장 형식·보호 정책 문제는 아니라서 확정을 막지 않았다. 문서(SPEC §11, README 업그레이드 절)에 비용을 적었고, manifest에서 settings 파일을 뺄지는 G6 설계의 사용자 결정 항목으로 넘겼다(`docs/g6/G6-DESIGN.md` §9 4번). 업그레이드 프로브에서 본 nit 하나(제거 쓰기 직후 중단 시 안내 문구가 "이전+새 규칙이 남음"이라고 하지만 이전 규칙은 이미 지워짐, 보호는 유지)도 다음 버전 후보로 남긴다.

Windows 회귀는 `aae9a99`에서 돈 결과(실패 0, skip 40)를 쓴다. 확정 커밋과 `plugins`·`tests`·`scripts` 트리 해시가 같다. pty가 필요한 Windows 경로, 실제 Claude 세션에서의 업그레이드는 미검증으로 남는다(TEST_RESULTS §13.7).

## D41. G6 Integration Verification 정책 확정 (2026-11-09, 사용자 결정, 구현 전)
D39의 결정안에 대한 사용자 결정이다. 확정 설계(요구사항 REQ-G6-01~26, 아키텍처, 상세 설계, 테스트 명세, 구현 계획)는 `docs/g6/G6-DESIGN.md`. 초안은 독립 검토(읽기 전용, 주요 6·부 8)를 거쳐 고쳤다(설계 §11). 구현은 그 문서 §9의 남은 결정 뒤 별도 세션에서 V-Model 절차(요구사항 → 아키텍처 → 상세 설계 → 구현 전 테스트 설계 → RED → 구현 → GREEN → 독립 검토 → 회귀)로 한다.

1. 실행 명령: config `integration_test`(argv에 `{junit}`, timeout_s, 선택 plugin_autoload, G6이 평가마다 하위 스키마 검증)를 지원한다. G6이 적용 대상인데 이 명령이 없으면 G6은 BLOCKED(`misconfigured`)이고, `unit_test` 명령으로 대체 실행하지 않는다(D39 권장안 E 기각). G5는 unit, G6은 integration 책임이다. `integration_test`가 설정된 프로젝트에서는 unit 명령이 integration 테스트를 실행하면 G5.SCOPE FAILED, G6 명령이 unit 테스트를 실행하면 G6.SCOPE FAILED다. 설정이 없는 기존 프로젝트의 G5 판정·기록은 0.1.5와 같고, 섞인 실행은 status·report에 경고로만 보인다. 설정된 프로젝트의 G5.NO_WEAKENING은 지금 integration 수준인 ID만 "사라진 ID" 판단에서 뺀다(unit을 지우거나 system으로 바꾸는 것은 지금처럼 실패).
2. G4/G6 역할: G4는 인터페이스 구현(기계: G4.INTERFACE_IMPLEMENTED), 통합 테스트 코드 존재(기계: G4.TEST_CODE를 integration ID까지), IF별 함수 단위 정적 도달(기계: G4.INTEGRATION_WIRING, 닿지 않는 IF가 있으면 실패, provider patch는 경고), IF별 연결 설계·목 대체 여부·구현 심볼(AI: G4 리뷰의 `interfaces` 항목이 모든 IF를 덮고 `provider_symbols`가 실재해야 approve 인정)을 맡는다. G6은 AI 리뷰 없는 기계 판정이며, 이번 실행의 증거와 자신이 다시 계산한 정적 도달로만 PASS한다(설정·실행 대상·종료 코드·결과·IF↔TEST↔케이스 매핑·도달·해시·판정 유효성). 이름만 맞는 빈 테스트로는 IF 커버리지가 성립하지 않는다. gates.json G6 reviewer는 "none (mechanical)". 정적 도달의 강도(실패/경고)는 설계 §9 5번 확인 항목이다.
3. N/A: IF 0, integration 명세 0, 컴포넌트 1개이고 다른 ARCH와의 data_flow 없음, 현재 G2·G3 PASS가 인정한 리뷰 둘 다 `integration_applicability: {decision: not_required, reason, endpoints_reviewed}`을 담음(외부 data_flow 끝점 전부 포함), 이전 G2 PASS에 있던 IF가 지금 없으면 CR·DEFECT `removed_ids`로 정당화됨 — 모두 확인할 때만 N/A다. N/A PASS는 결함 검증(`verified_by`)으로 치지 않는다. 기록은 PASSED + `applicability: not_applicable`, 실행 증거 없음, 표시는 N/A. 하나라도 확인할 수 없으면 BLOCKED(`applicability_unconfirmed`). IF나 integration 명세가 있으면 실행한다. G6 manifest에 `reviews/G2.json`·`reviews/G3.json`을 넣어 N/A 근거가 바뀌면 STALE이 된다.
4. 기존 WI: G6이 생기면 G1~G5 PASSED WI는 G6 평가 전까지 IN_PROGRESS로 보인다. G6은 G1~G5 manifest·판정 입력을 늘리지 않고, 기존 기록·증거는 다시 쓰지 않는다. status는 Gate별 결과 요약(`gate_summary`)과 WI 상태를 나누고, G6 미평가를 "not evaluated yet"으로 표시한다. 업그레이드 때 Core 해시 변경으로 생기는 STALE은 G6과 무관한 기존 무결성 규칙(SPEC §5 5항)이며 유지한다(사용자 확인 항목, 설계 §1.1·§9 1번).

함께 정한 것: G6 FAILED는 G5와 같은 재작업 전제 조건·3회 실패 차단·결함 추적(D35)·표시 상태(D37)를 따른다(defects `gate` G6, `root_cause_phase` P6, `removed_ids`에 IF). `applicability_unconfirmed`를 중립 차단에 더한다(`misconfigured`·`tool_unavailable`은 이미 중립). G6.NO_WEAKENING은 실행 기록이 있는 기준(마지막 required PASS, 없으면 실행된 첫 G6)에서 실행된 integration ID와, 이전 G2 PASS에 있던 IF가 사라지면 `removed_ids`를 요구한다(CR·defects 스키마에 IF 허용). D39 §6의 "IF 삭제로 N/A 만들기" 빈틈을 닫는다. `citation_view`의 TEST_MAPPING 체크 ID를 Gate별로 바꿔 G6 결함 추적이 G5와 같은 분류를 낸다. 기존 하네스 중 결정 4로 기대값이 바뀌는 테스트(G6 NOT_IMPLEMENTED·G5 뒤 PARTIALLY_VERIFIED)는 설계 §6.1 목록으로만 의도 변경한다.

## D42. G6 Integration Verification 구현 결정 (2026-11-09, 사용자 결정 D1~D8 승인, v0.2.0 후보)
사용자가 설계 §9의 여덟 가지를 정했다("VModel DevKit v0.2.0 — G6 Integration Verification 개발"). 작업 기록과 요구사항 변경은 `docs/g6/WORKITEM.md`(REQ-G6-27~34), 설계 정본은 `docs/g6/G6-DESIGN.md`(REQ-G6-01~26)다.

사용자 결정과 설계 대비 바뀐 것
1. D1 Core 변경: 설계 §1.1 그대로. G6 추가는 G1~G5 manifest·판정 입력을 늘리지 않고, Core 교체 STALE 규칙은 유지한다(T16, C2).
2. D2 N/A: G2·G3 리뷰 둘 다 확인(설계 기본값). 내부 PASSED + `applicability: not_applicable`, 표시 N/A.
3. D3 명령 분리: 설계 기본값(경로가 없어도 기본 argv를 써 둠)을 버렸다. `init`은 **실제로 있고 테스트 함수가 있는** 경로만 `integration_test`로 등록하고 unit argv에 `--ignore=<경로>`를 더한다(`--integration-tests PATH` 또는 `tests/integration/` 자동). 없는 경로·테스트 없는 경로·unit 전체 범위·tests 경로 밖은 거부하고 아무것도 만들지 않는다. 기존 프로젝트는 사용자 전용 `vmodel configure-tests --integration PATH`(TTY + guard USER_ONLY, 같은 경로 검증, 서명 원장 `config` 기록 후 config 쓰기)로 옮긴다. `integration_test` 없는 0.1.x config는 그대로 유효하다.
4. D4 G4 manifest: `.claude/settings.json`을 코드 manifest에 그대로 둔다. 업그레이드마다 G4 재리뷰 비용은 남는다(D40).
5. D5 정적 도달 + 실제 통합 증거: 설계 §4.6의 "하위 프로세스·동적 import는 도달 아님"을 버리고 두 경로로 나눴다.
   - 경로 A(정적): 테스트 함수의 **호출식**에서 시작한 소스 모듈 import 폐포에 provider(와 ARCH consumer)가 있어야 한다. import·참조만으로는 도달이 아니고, 테스트 안의 중첩 def·class·lambda 본문은 테스트가 이름으로 부를 때만 따라간다(호출 없는 함수는 placeholder로 G4 FAILED).
   - 경로 B(실행 경로): 정적 호출 경로는 없지만 subprocess·IPC·API·동적 import 호출이 있는 테스트. G4는 verifier 리뷰의 `interfaces[].runtime_paths`(TEST, 종류, 테스트 파일 sha256)가 Validator가 찾은 종류·현재 해시와 맞을 때만 인정하고, 아니면 REVIEW_REQUIRED다. G6은 Validator Core의 계측 모듈(`tracer/sitecustomize.py`)을 `PYTHONPATH`로 실행 중 모든 Python 프로세스에 넣어, 그 테스트(`PYTEST_CURRENT_TEST`) 동안 provider(와 consumer) 함수가 실행됐는지 기록하고 해시를 서명 증거에 넣는다. 선언은 있는데 실행 증거가 없으면 BLOCKED(`integration_evidence_insufficient`, 중립)이고 PASS하지 않는다. AI 리뷰 문장만으로는 IF를 덮지 않는다.
   - (D43이 이 항목을 대체: 경로 A의 테스트별 귀속은 경고만, 판정은 함수 실행 + 실행 전체의 provider 실행.) 경로 A도 실행 확인을 받는다(REQ-G6-33). G6은 계측이 실행을 본 분석 대상 함수만 근거로 쓰고, 그 테스트 동안(어느 단계든, 그 테스트가 시작한 스레드 포함) provider가 실제로 돌아야 근거다. 근거 없는 주장은 IF가 다른 테스트로 덮이면 경고, 아니면 BLOCKED. 계측이 없으면 BLOCKED(JUnit만으로 인정하지 않음). 처음 구현은 경고만 했고 "실행되지 않은 함수"도 근거로 썼다(검토 1회차 F1·F2). 2회차 구현은 호출 단계만 인정하고 FAILED를 냈는데 fixture·setup_method 테스트를 거짓으로 떨어뜨려(N8) 어느 단계든 인정·BLOCKED로 바꿨다(`docs/g6/WORKITEM.md` §7).
   - 별도 프로세스라는 이유로 G7로 보내지 않는다. 판정 대상은 인터페이스다.
6. D6 버전 0.2.0. 0.1.5 태그·릴리스 사본은 그대로다.
7. D7 범위 삭제된 G6 결함: 설계 기본값(기존 상태 + 주석)을 버리고 표시 상태 OUT_OF_SCOPE를 더했다(D37의 6종 + 1). 결함의 종료 Gate가 G6이고 G6이 지금 N/A(현재 manifest)일 때다. `scope_removal`에 실패 기록의 IF·통합 TEST ID와 그것을 `removed_ids`에 둔 CR/DEFECT와 사유를 보인다. CLOSED가 아니고 `verified_by`·`verification_history`는 N/A 기록을 세지 않는다. 결함 저장 형식은 enum(G6, P6, IF)만 넓혔다.
8. D8 실전 E2E: 계획만 했다(시나리오 A·B, sonnet 2회, 회당 $2, 합계 $4). 유료 실행은 별도 승인.

구현에서 정한 것
- G5 실행부(`eval_g5`)는 고치지 않았다. 설계 §4.5의 `_execute_suite` 분리 대신 G6이 같은 runner 함수를 따로 호출한다(G5 무변경 우선). G5에 더한 것은 `integration_test`가 설정됐을 때만 도는 G5.SCOPE와 NO_WEAKENING의 integration 수준 ID 제외뿐이다.
- G6 manifest에 `reviews/G4.json`을 더했다(경로 B 선언의 근거). G4 PASS가 인정한 리뷰와 지금 파일이 다르면 경로 B 선언을 쓰지 않는다.
- 리뷰 스키마의 새 키(`integration_applicability`, `interfaces`)는 형태만 느슨하게 두고 내용은 그 키를 쓰는 Gate 코드가 검사한다. 잘못된 항목이 G2·G3 판정을 바꾸지 않게(설계 §1.2), G4에서는 REVIEW_REQUIRED가 되게 하기 위해서다.
- G6.IF_COVERAGE 안에서는 실패 항목이 있으면 FAILED(재작업·결함 필요), 실패 없이 증거 부족만 있으면 BLOCKED다. 근거 없는 주장(경로 A·B)은 같은 IF가 다른 테스트로 덮이면 경고, 아니면 BLOCKED다(경로 A와 B를 같은 규칙으로). 경로 B 증거는 pytest 호출 단계의 것만 세고, subprocess·ipc 선언이면 테스트 함수와 다른 프로세스의 것이어야 한다(검토 F6). 계측은 다른 스레드를 그 스레드를 시작한 테스트에 귀속하고(N1), fork 자식은 자기 파일을 쓴다(N2).
- G4는 TEST ID를 가진 함수 **하나하나**를 판정한다(가장 좋은 함수 하나만 보면 수집되지 않거나 꺼진 사본이 실제 테스트를 대신할 수 있었다, 검토 F1).
- 정적 분석은 모듈을 파일 경로로 식별하고 함수 지역 범위를 먼저 본다(모듈 수준은 문장 순서). 호출은 소스 모듈의 최상위 def/class(또는 그 클래스 메서드, 모듈 수준 인스턴스의 메서드)로 풀릴 때만 센다. 사용자 지시의 DI는 "consumer 호출의 인자로 넘긴 소스 def/class"로 경로 A에서 인정하고, 경로 B 종류는 subprocess·ipc·api·dynamic_import다. 파일이 점유하는 import 이름은 프로젝트 루트 기준, 최상위 소스 루트 기준, 두 부분 이상인 일반 패키지 이름으로 제한해 표준 라이브러리 이름을 빼앗지 않는다(검토 F2·F7·F8·F9, N5·N6·N10·N11).
- 계측 한계로 문서화한 것: forkserver 자식은 서버를 시작한 테스트의 환경을 물려받아 귀속이 틀릴 수 있고, 테스트 사이에 재사용되는 스레드 풀 작업자는 처음 만든 테스트에 귀속된다(이후 테스트의 실행이 보이지 않아 BLOCKED가 될 수 있음, 보수적). 데이터 전용 IF는 BLOCKED.
- placeholder 탐지는 integration 수준 테스트에만 한다(unit 테스트 G4 판정 불변, REQ-G6-13).
- 계측 한계(SPEC §5.7과 같은 같은 프로세스 신뢰 경계): 테스트 코드는 계측 파일을 위조할 수 있다(검토 F5에서 재현, 환경 변수를 훑어 찾으면 된다). G4.TEST_INTEGRITY의 `VMODEL_TRACE` 문자열 검사는 우발적 언급만 잡고 의도적 위조는 막지 못한다. 기존 증거 신뢰 모델(최종 신뢰 경계는 CI·별도 사용자 재검증)을 그대로 따른다. `-I`/`-E`로 시작한 Python, 세션 범위 fixture가 띄운 하위 프로세스(처음 테스트에 귀속), pytest가 아닌 러너는 경로 B를 증명하지 못해 BLOCKED가 된다(보수적).
- 읽기 전용 `vmodel wiring WI`: verifier가 경로 B를 선언할 때 쓰는 분류·해시를 보인다.

## D43. G6 판정에는 믿을 수 있는 실행 사실만 쓴다 (2026-11-09, 독립 검토 3회차 반영, v0.2.0 후보)
배경: 검토 1회차(F2)는 "목으로 provider를 대체한 경로 A 테스트"를 G6에서 막자고 제안했고, 2·3회차 구현은 계측의 **테스트별 귀속**(이 테스트 동안 provider가 돌았는가)을 판정 조건으로 썼다. 3회차 검토는 같은 프로세스 안의 귀속이 양쪽으로 틀린다는 것을 재현했다: 함수 범위 fixture가 띄운 HTTP 서버의 처리 스레드, 모듈 수준 `ThreadPoolExecutor`를 쓰는 consumer처럼 정상 코드가 거짓 BLOCKED가 되고(R2), 반대로 autouse·세션 fixture나 asyncio 작업이 provider를 돌리면 목 테스트가 근거를 얻었다(R1, R3). 귀속 규칙을 계속 덧대면 수렴하지 않는다고 판단했다.

결정: G6 판정 조건에는 다음처럼 믿을 수 있는 실행 사실만 쓴다.
1. 근거가 되는 테스트 함수는 계측이 실제 실행을 본 것이어야 한다(테스트 함수 본문은 pytest 메인 스레드에서 돌아 `PYTEST_CURRENT_TEST`로 정확히 귀속된다).
2. 경로 A: 정적 호출 경로 + 그 함수의 실행 + **실행 전체에서** provider(와 ARCH consumer) 함수가 한 번이라도 실행됨. 아무 데서도 안 돌았으면 BLOCKED(`integration_evidence_insufficient`: 전부 목이거나 데이터 전용 IF). 테스트별로 provider가 귀속되지 않으면 **경고**만 낸다("mocked? or run in a shared thread/pool").
3. 경로 B: 선언(G4 리뷰, 테스트 파일 해시) + 그 테스트의 호출 단계에서 provider 실행. subprocess·ipc는 테스트 함수와 다른 프로세스(자식은 환경을 물려받아 정확히 귀속), api·dynamic_import는 그 테스트가 시작한 스레드(소유 테스트가 실행 중일 때의 단계로 기록, 끝난 뒤는 detached) 또는 메인 스레드. 근거 없는 선언은 IF가 다른 테스트로 덮이면 경고, 아니면 BLOCKED.
4. 계측이 아예 없으면 BLOCKED, 잘렸으면 "실행되지 않음" 판단은 BLOCKED.

결과와 대가: 목만 쓴 경로 A 테스트도 그 IF의 provider가 실행 어딘가에서 돌면 **경고와 함께 통과**한다. 이는 D41 결정 2(목 대체 여부는 G4 리뷰의 판단)와 같은 자리로 돌아간 것이며, 기계적으로는 G4 patch 경고, G6 테스트별 경고, "실행 전체에서 provider가 안 돎" BLOCKED가 남는다. 검토 1회차 F2의 G6 시나리오와 2회차 N1 시나리오의 기대값은 이 결정으로 "경고 있는 PASSED"로 바뀌었다(테스트에 근거 주석). 같은 프로세스 신뢰 경계(SPEC §5.7) 안에서 의도적으로 테스트 결과·계측을 꾸미는 코드는 막지 못한다(F5).

문서화한 한계: forkserver 자식과 이전 테스트가 만든 fork 풀의 작업자는 그 서버·풀을 시작한 테스트의 환경을 물려받는다(경로 B 귀속이 틀릴 수 있음, Python 3.14부터 Linux 기본값이 forkserver). 세션·모듈 범위 fixture가 띄운 서버는 처음 테스트에만 귀속돼 이후 테스트의 경로 B는 BLOCKED가 될 수 있다(보수적). 데이터 전용 IF는 BLOCKED. "provider가 돎"은 provider 파일의 어떤 함수든 실행됐다는 뜻이다. 정적 분석은 Python 근사이며 의도적으로 꾸민 코드(동적 setattr, exec 등)를 모두 잡지 못한다.

## D44. G6는 테스트 수준 증거만 인터페이스 검증으로 센다 (2026-11-09, 최종 독립 검증 지시 반영, v0.2.0 후보)
배경: 사용자의 최종 검증 지시("VModel DevKit v0.2.0 — 최종 독립 검증 및 E2E")가 Case A~F를 요구했다. 특히 "다른 테스트의 실행 증거를 잘못 귀속하지 않는다", "Suite-level 증거만으로 Test-level 검증을 완료했다고 표시하지 마라", "G6의 기본 신뢰 수준을 낮추는 방식으로 문제를 숨기지 마라". D43 규칙(경로 A는 실행 전체에서 provider가 한 번이라도 돌면 통과, 테스트별 귀속은 경고만)으로는 14b34af에서 다음이 재현됐다(`tests/test_g6_evidence.py`, RED 10/10): 목만 쓴 IF-001 테스트가 다른 IF의 테스트(TEST-012)에서 돈 parser 덕분에 PASSED(Case B·C, `covered_by`에 목 테스트 포함), 테스트가 provider를 직접 부르고 consumer 안의 호출만 목으로 바꾼 경우는 경고도 없이 PASSED(Case D). 4회차 독립 검토(c83df4b)도 같은 지적(H1·H4)과 함께 H2(import 시점 함수가 "provider 실행"으로 셈), H3(오래 사는 자식 프로세스가 태어난 테스트에 계속 귀속), M1~M6, L1~L4를 냈다(`docs/g6/WORKITEM.md` §7.4).

결정:
1. 통합 테스트마다 증거 수준을 매긴다: **Test-level Verified**(`test_level`), **Suite-level Evidence Only**(`suite_level`: provider가 실행 어딘가에서 돌았지만 이 테스트 자신의 실행이 아님), **Insufficient Evidence**(`insufficient`: 계측 없음, provider가 전혀 안 돎, 연결이 관찰되지 않음, 테스트 실패). 인터페이스는 `test_level` 테스트가 하나 이상일 때만 덮인다. 없으면 호출 경로가 있는 통과 테스트가 있는 한 BLOCKED(`integration_evidence_insufficient`, 중립 차단), 호출 경로조차 없으면 FAILED. Suite-level·불충분 테스트는 표시만 하고 세지 않는다(status·report·trace·gate 출력, 기록 `interfaces[].verification`, `tests[].evidence_level`·`evidence_reason`).
2. `test_level` 조건: 그 테스트 함수가 실제로 실행되고 통과, 경로 A(정적 호출 경로) 또는 경로 B(G4 선언), 그리고 그 테스트 자신의 실행에서 연결이 관찰됨.
   - 경로 A, ARCH consumer: provider 심볼 함수가 시작될 때 호출 스택에 consumer 함수가 있음(계측의 `e` 줄). 같은 스레드 스택, 또는 그 스레드를 시작한 스택, 스레드 풀 작업을 제출한 스택. 모듈 본문(import 시점)은 consumer 호출이 아니다.
   - 경로 A, EXTERNAL consumer: provider 심볼 함수가 그 테스트에서 실행됨.
   - 경로 B: 호출 단계에서 provider 심볼 함수 실행(subprocess·ipc는 테스트와 다른 프로세스) + consumer 실행.
   - "그 테스트에서": 메인 스레드는 `PYTEST_CURRENT_TEST`, 다른 스레드는 그 스레드를 시작한 테스트, 스레드 풀 작업은 제출한 테스트, 자식 프로세스는 그 테스트의 단계 구간 안에서 한 일만(Validator 소유 pytest 플러그인 `vmodel_trace_plugin`이 `PYTEST_PLUGINS`로 실려 모든 테스트의 setup/call/teardown 시작과 끝을 기록하고, 자식 줄은 시각으로 다시 읽는다: call 구간 안이면 call, 밖이면 setup/teardown/detached, 경계와 같은 시각은 credit 없음, 경계가 없으면 귀속 안 함).
   - 기록하는 provider 함수는 실행이 시작된 함수가 아니라 진입 함수(consumer나 테스트가 들어간 가장 바깥 provider 함수)다. 생성자가 부르는 도우미는 생성자로 기록돼 인터페이스 실행이 아니다(6회차 M1). 줄마다 `perf_counter_ns`도 기록해 거친 벽시계 대신 비교한다(6회차 M5·M6).
   - 그리고 "그 테스트 자신이 한 일"이어야 한다(5회차 N7): 연결·provider 실행 기록의 앵커(호출 스택의 가장 바깥 통합 테스트 파일·conftest 함수, 스레드·풀 작업은 시작·제출한 스택에서 상속)가 테스트 함수 자신이거나 그 테스트가 요청한 fixture·setUp이어야 한다. autouse·요청하지 않은 fixture가 한 일은 Suite-level. 앵커는 스택의 테스트 파일 함수 집합이라 데코레이터 래퍼가 가리지 않는다(6회차 M2). 요청한 fixture에서만 연결이 일어났고 테스트 함수가 provider를 patch하면(G4 정적 탐지) 세지 않는다(6회차 M7, 보수 쪽 설계 판단, 사용자 확인 사항).
3. provider는 인터페이스 심볼이다: 시그니처의 def/class와 인정된 G4 리뷰의 `provider_symbols`(그 메서드·중첩 함수 포함, 단 생성자·객체 프로토콜 메서드는 제외; 메서드 이름 시그니처는 provider 파일의 그 이름 메서드). provider 파일의 아무 함수나 import 시점 도우미는 근거가 아니다(검토 4회차 H4·H2, 5회차 N2·N3).
4. 서명 증거: 계측은 실행 폴더의 `trace-live/`에 쓰고, Validator가 실행 직후 한 번 읽은 바이트를 `trace/`에 스냅샷해 그것으로 판정하고 해시·서명한다. 실행 뒤에도 살아 있는 프로세스가 서명된 증거를 바꾸지 못한다(M5).
5. 함께 고친 것(4회차): 노드 ID의 `[`는 파일 부분 뒤에서만 매개변수로 자름(M3), 읽을 수 없는 최상위 디렉터리로 인한 내부 오류 제거(M4), `mocker.patch`·내장 `setattr`·`module.symbol = fake`를 provider patch 경고로(M6), `pytest.ini`·`tox.ini`·`setup.cfg`의 pythonpath(L1), if 분기에서 묶지 않은 이름은 이전 바인딩 유지(L2). pytest 프로세스 계측 파일이 잘렸거나 없으면 자식 프로세스 줄은 귀속하지 않는다(보수).

대가와 한계(보수적 BLOCKED가 될 수 있는 정상 코드): 테스트가 provider를 부르고 그 결과를 consumer에 넘기는 데이터 전달형 테스트(호출 연결이 아님), consumer가 provider를 별도 asyncio 작업(`gather`·`create_task`)으로 돌리거나 provider 제너레이터를 넘겨 테스트가 순회하는 경우(5회차 N4·N5), pytest가 아닌 러너(테스트 경계 없음 → 자식 프로세스 증거 불인정), 세션·모듈 범위 fixture의 서버·프로세스(첫 테스트 외), 다음 테스트가 시작된 뒤에 일하는 장수 프로세스, 테스트가 시작하지 않은 전역 백그라운드 작업자, 다른 태스크 경로의 asyncio 작업, 데이터 전용 IF, 리뷰의 `provider_symbols`가 실제로 쓰인 심볼을 빠뜨린 경우(API 처리기가 `summarize`를 부르는데 IF 시그니처는 `main`). 같은 프로세스 신뢰 경계(SPEC §5.7, F5)는 그대로다: 계측 줄(연결, 경계, 시각, spawned_in)은 테스트 코드가 의도적으로 위조할 수 있다. function 범위 autouse fixture가 consumer 경유로 provider를 돌리면 그것은 그 테스트의 실행으로 센다. 스택 스캔은 (테스트, 단계, 함수)마다 2000회·깊이 256 상한(넘으면 표지를 남기고 "불확실"). 같은 (테스트, 단계, 함수)에서 테스트 자신의 앵커로 연결이 확인되면 이후 스캔은 생략한다. Windows CPython 3.12 이하처럼 시계가 거칠면 경계 직후의 자식 줄이 보수적으로 버려져 간헐적 BLOCKED가 날 수 있다(사용자 Windows는 3.13).

D43과의 관계: "판정에는 믿을 수 있는 사실만"이라는 D43 원칙은 유지한다. D43이 포기한 테스트별 귀속을, 추정이 아닌 사실(호출 스택, 스레드 시작·작업 제출 관계, 프로세스가 태어난 테스트와 시각)로 다시 세웠고, 그 사실로 증명하지 못한 것은 통과가 아니라 BLOCKED다. D43의 "목만 쓴 경로 A 테스트도 경고와 함께 통과"는 폐기한다.
