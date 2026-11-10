# HANDOFF

다음 세션이 이 파일만 읽고 이어갈 수 있게 정리한 인수인계입니다. 마지막 갱신: 2026-11-10(11차, v0.2.0 최종 독립 검증·실제 E2E, 브랜치 `g6-dev`).

## 현재 상태 한 줄
**v0.2.0 릴리스 후보(G6 Integration Verification) 최종 검증 완료, 사용자 확정 전.** 판정은 TEST_RESULTS §15.9(최종 판정)와 최종 보고를 볼 것. 확정 버전은 여전히 0.1.5(태그 `v0.1.5` = `main` = `78517d5`). 후보 코드는 `g6-dev`의 `5275b5d`(이후 커밋은 릴리스 기록·문서), 릴리스 `dist/vmodel-0.2.0`(core `sha256:9cc0997a…`, `releases/vmodel-0.2.0.json`). 결정 D44, 검토 처리표 `docs/g6/WORKITEM.md` §7.4~7.12.

## Git
- `main` = 태그 `v0.1.5` → `78517d5`(변경 없음). 태그 `v0.1.2`~`v0.1.5` 그대로. **`v0.2.0` 태그 없음, 병합 없음, 푸시 없음.**
- `g6-dev`: … `14b34af`(3회차 수정) → `c83df4b` → 이번 세션: Case A~F 테스트 `cdd95dd` → D44 `57492d3` → 4회차 `e7c82c5`·`464d01b`·`8130ee5` → 5회차 `4d4060c`·`e8a5a7e` → 6회차 `2b2b123`·`ce59c33` → 7회차 `953d502` → 8회차 `31ccb0d` → 9회차 `3a08592` → 릴리스 `589c779`(E2E에 쓴 빌드) → E2E 결함 `70f0b9b`·`5275b5d` → 릴리스 `83b3b9a` → 문서.
- 원격 `origin/main`은 `bbd6a3d`. 푸시는 승인되지 않았습니다(`test-results/` 로그·트랜스크립트에 `/home/cyyoo`·`/tmp` 경로가 있음).
- `dist/vmodel-0.2.0`(git 제외)과 `releases/vmodel-0.2.0.json`(추적)은 **후보**. 확정 전에 코드를 바꾸면 `python3 scripts/release.py --force`.
- 작업 트리에 `.claude/scheduled_tasks.lock`(Claude Code 예약 기능의 잠금 파일)이 있다. 커밋하지 않음.

## G6 판정 규칙 요약 (정본 D41~D44, `docs/g6/G6-DESIGN.md`, WORKITEM)
1. 실행·설정·N/A·G5 분리·OUT_OF_SCOPE는 D41/D42 그대로.
2. D44: 통합 테스트마다 증거 수준 **Test-level Verified / Suite-level Evidence Only / Insufficient Evidence**. 인터페이스는 Test-level 테스트가 있어야만 덮인다. 없으면 BLOCKED(`integration_evidence_insufficient`), 호출 경로조차 없으면 FAILED.
3. Test-level 조건: 테스트 함수가 실행·통과 + 정적 호출 경로(A) 또는 G4 선언(B) + 그 테스트 자신의 실행에서 연결 관찰. A는 provider 진입 함수가 시작될 때 호출 스택(스레드 시작·풀 제출 스택 포함)에 consumer 함수가 있고, 앵커(스택의 통합 테스트 파일·conftest 함수)가 테스트 함수나 그 테스트가 요청한 fixture·setUp. EXTERNAL consumer는 provider 진입 함수가 그 테스트에서 실행. B는 call 구간에 provider 진입 함수(subprocess·ipc는 다른 프로세스) + consumer.
4. provider = IF 심볼(시그니처 def/class + 인정된 G4 리뷰 `provider_symbols`, 메서드 포함, 생성자·객체 프로토콜 제외). 같은 모듈 IF는 시작된 함수로.
5. 자식 프로세스: Validator 소유 pytest 플러그인 `tracer/vmodel_trace_plugin.py`(`PYTEST_PLUGINS`, 로드 시 삭제, xdist 작업자에게만 복원)가 setup/call/teardown/end 경계를 기록. 비교는 `perf_counter_ns`. 경계 없으면 자식 증거 불인정.
6. 테스트 함수가 인터페이스 심볼이나 provider 모듈에 정의된 함수를 patch하면 그 테스트는 Test-level이 아님(보수 판단, 사용자 확인 대상).
7. 서명 증거: 계측은 `trace-live/`, Validator가 실행 직후 `trace/`로 스냅샷해 판정·해시.

## 다음 작업 (사용자 결정 필요)
1. **v0.2.0 확정 여부**와 보수 판단 2가지 확인(TEST_RESULTS §15.7): patch 테스트 불인정, autouse fixture 연결 불인정.
2. 실제 세션의 G6 FAILED → DEFECT → CLOSED 경로는 미관찰(E2E-A 시딩 함정 미발동). 원하면 추가 E2E 승인.
3. 원격 푸시: 승인 안 됨. 하려면 먼저 원격·포함 커밋·민감정보 점검을 보여 드리고 따로 결정.
4. 남은 미검증: TEST_RESULTS §15.7(+§14.9 이전 항목).

## 바로 쓰는 명령
```bash
cd /home/cyyoo/develop/vmodel-devkit && git switch g6-dev
cd tests && python3 -m unittest discover -s . -p "test_*.py"; cd ..     # 하네스 약 430개, 약 21분(WSL)
python3 -I test-results/v0.2.0/release_check.py /tmp/x.json             # 릴리스·태그·버전 재확인
python3 scripts/red_green.py --mode red --plugin <git archive 사본>/plugins/vmodel --marker RED-TARGET --log /tmp/r.log test_g6_evidence
python3 scripts/e2e/e2e_run.py --work <새 폴더> --sample scorepipe --setup-only     # 모델 호출 없음
python3 scripts/e2e/e2e_verify.py --work <E2E 폴더> --out <result.json>          # 세션 뒤 판정, 모델 호출 없음
claude plugin validate --strict plugins/vmodel
```

## 꼭 알아야 할 것
- 상태는 `.vmodel/state/ledger.jsonl`(서명 원장)에서만 나옵니다. 테스트·드릴은 항상 임시 `VMODEL_HOME`.
- 릴리스는 불변입니다. 기존 태그와 `releases/vmodel-0.1.x.json`은 고치지 않습니다.
- DevKit 자체는 DevKit Validator로 승인하지 않습니다(SPEC §5.8). 검토 지적은 검토한 빌드(`git archive <커밋> plugins/vmodel`)를 RED 대상으로 직접 재현한 뒤 고칩니다(`test_g6_review4~9.py`, `test_g6_e2e_findings.py`를 회차별로 분리).
- 실제 Claude 실행(`scripts/e2e/*` run)은 비용이 드므로 매번 사용자 승인. `--dangerously-skip-permissions` 금지. 이번 승인(sonnet 2회·회당 $2)은 모두 썼다(합계 약 $2.08).
- 검토자 에이전트를 회차마다 이어 썼다(별도 컨텍스트, 읽기 전용 worktree). 검토마다 새 형태가 나오는 구조라, 판정 규칙을 바꿀 때는 반드시 재검토와 회귀를 같이 할 것.
- Windows 회귀 사본: `%TEMP%\vmodel 한글 테스트\devkit-0.2.0-<커밋>`(git archive + `dist/vmodel-0.1.3`·`0.1.4`·`0.1.5` 복사), 스크립트 `win-0.2.0-<커밋>.ps1`(UTF-16 BOM, 기존 `.venv`). 약 40분.
