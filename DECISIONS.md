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
