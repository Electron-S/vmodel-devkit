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
