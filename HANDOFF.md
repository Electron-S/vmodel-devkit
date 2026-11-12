# HANDOFF

다음 세션이 이 파일만 읽고 이어갈 수 있게 정리한 인수인계입니다. 마지막 갱신: 2026-11-11(15차, 실제 E2E·최종 회귀·v0.3.0 확정, 브랜치 `g7-dev` → `main`).

## 현재 상태 한 줄
**v0.3.0 확정(RELEASE READY, TEST_RESULTS §19.8).** 태그 `v0.3.0`(annotated) = `main` = 이 문서를 담은 최종 기록 커밋. 플러그인 트리는 `de270aa` 이후 그대로이고 릴리스 `dist/vmodel-0.3.0`(core `sha256:8abab9ec86fef66fb6e21b8b13aa29bc27bd29adbb76a2df75608dd1ceee4bb5`, `releases/vmodel-0.3.0.json`)과 같다. 결정 D49(G7 설계)·D50(확정), 설계 정본 `docs/g7/G7-DESIGN.md`. 알려진 한계: 실제 세션의 G7(그리고 G6) FAILED → DEFECT → CLOSED 경로 미관찰(하네스로만 검증), 나머지는 §19.9.

## 이번 확정의 근거 (TEST_RESULTS §19)
- 최종 회귀(`101711d`): WSL 559 통과·skip 1, Windows cp949·한글 경로 559 실행·실패 0·오류 0·skip 64(환경 의존). 실행 전후 남은 프로세스 없음(WSL·Windows).
- 실제 Claude Code E2E 1회(Sonnet `claude-sonnet-5-5`, $1.04, 56턴, `samples/textcli`, 샌드박스): G1 reject → 수정 → G1~G5 → G6 BLOCKED(applicability, 2회) → 리뷰 보완 → G6 N/A → G7 PASSED(R00021, AC 6/6, 서명 증거) → WI COMPLETED, audit OK, guard 거부 0. 사본에서 `vmodel verify` 재평가도 같은 결과.
- 0.2.0 실제 원장(드릴 S1/S2) 사본을 0.3.0 Core로 verify-evidence·재고정·audit OK. Plugin Validation 통과, release_check OK.

## Git
- 태그 `v0.3.0` → `645bf7a`(최종 기록 커밋). `main`은 그 위에 MIT 라이선스 커밋 하나(플러그인 트리 변경 없음). 태그 `v0.1.2`~`v0.2.0` 그대로(`v0.2.0` → `c4b508a`).
- `g7-dev`: 설계 `cfce1e9` → 테스트 `b3c79b2` → 구현 `68b4d67` → 검토 RED `2c26356` → 수정 `7939f97` → 재검토 RED `172a599` → 수정 `12e3caf` → 버전 `de270aa` → 릴리스 기록 `8eb93ff` → 문서·로그 `1deef79` → 시험 수정 `fa43a03` → 후보 기록 `13eb65c` → 점검 `101711d` → 최종 기록(이번, E2E·회귀·확정 문서, 플러그인 변경 없음).
- 태그 뒤 점검: `python3 -I test-results/v0.3.0/release_check.py <out> --released` (annotated 태그 = `main`, 태그된 플러그인 트리 = 0.3.0 기록, `v0.2.0` 조상, 이전 태그·기록 불변).
- 원격 `github.com/Electron-S/vmodel-devkit`는 **공개(public)**, MIT(2026-11-12, 사용자 지시). `main`과 태그 `v0.1.2`~`v0.3.0`을 푸시했다(force·태그 변경 없음). 공개 전 점검: 비밀·키 없음. `test-results/`의 로그·트랜스크립트·원장 사본에 로컬 경로(`/home/cyyoo`·`/tmp/claude-1000`·`C:\Users\cyyoo`), 세션 ID, `transcript-a.jsonl`의 claude.ai 커넥터 이름 목록이 있고, 커밋 메타데이터에 작성자 이메일이 있다. 다른 브랜치(`g6-dev`·`g7-dev`·`v0.1.x-dev`·`rework-drill-0.1.3`)는 푸시하지 않았다. 앞으로도 푸시할 때마다 `git log origin/main..main`을 보여 주고 대상을 명시해 올린다(`--force`·`--all`·`--mirror` 금지).
- `dist/vmodel-0.3.0` 이하는 확정 릴리스(git 제외). **다시 빌드하지 마세요**(`release.py --force` 금지). 다음 플러그인 변경은 새 버전으로. `dist/.claude-plugin/marketplace.json`은 0.3.0을 가리킨다.
- 작업 트리의 `.claude/`(예약 기능 잠금 파일)는 커밋하지 않음.

## G7 판정 규칙 요약 (D49)
1. config `system_test`(argv에 `{junit}`)를 Validator가 직접 실행(블랙박스, 계측 없음, 출력은 임시 파일 `runner.run_command_files`, POSIX 프로세스 그룹 정리). 없거나 잘못되면 BLOCKED `misconfigured`, unit·integration 명령으로 대체 안 함. 시작 실패만 BLOCKED `tool_unavailable`, 나머지 실행 문제는 FAILED. 종료 코드 0만으로 PASS 아님.
2. 체크: PREREQ(G6 PASSED/N/A), CONFIG, EXECUTION, RESULTS, SCOPE(unit·integration ID → 실패), TEST_MAPPING(system 명세마다 이번 실행 통과, 0개 → 실패), AC_COVERAGE(활성 functional REQ의 모든 AC: 그 AC를 가리키는 system 명세 전부 통과; 비기능 AC 명세 없음 → 경고), NO_WEAKENING, INPUTS_UNCHANGED. ai_review 없음.
3. 블랙박스 여부(외부 인터페이스)는 기계 판정 안 함 → G3·G4 verifier 리뷰. 시스템 테스트 함수 존재는 G4가 아니라 G7(not executed)이 확인하고 status next_action이 미리 알려 줌.
4. `system_test` 설정 시 G5·G6이 system ID를 실행하면 SCOPE 실패, G5.NO_WEAKENING은 system ID 제외. 설정 없으면 G1~G6 판정·manifest·실패 서명은 0.2.0과 같음.
5. WI: STANDARD는 G1~G7 PASSED(G6 N/A 포함)일 때만 COMPLETED. G7 미평가는 IN_PROGRESS. COMPLETED는 자동 검증이지 사용자 수용·배포 승인이 아님.
6. 결함: gate G7, root_cause_phase P7. G7 실패 결함은 현재 G7 PASS로만 CLOSED.

## G6 판정 규칙 (0.2.0, 정본 D41~D45·D48, `docs/g6/G6-DESIGN.md`)
변경 없음. 요약은 TEST_RESULTS §17.3과 D48.

## 다음 작업 (사용자 결정 필요)
1. 플러그인 매니페스트 `"license": "UNLICENSED"`를 `"MIT"`로 맞추기: 확정 0.3.0 트리는 불변이라 다음 릴리스(0.3.1 이상)에서. 공개 저장소 설명이 아직 "MVP G1~G5"라 갱신 여부도 사용자 결정.
2. 실제 세션 미관찰 경로를 볼지: G7(또는 G6) FAILED → DEFECT → 수정 → CLOSED, 0.2.0 → 0.3.0 실제 업그레이드(재고정 → `configure-tests --system` → 재평가). 실제 Claude 실행은 횟수·상한 승인 후에만. G7 실패를 자연스럽게 내려면 시드 버그를 unit 테스트가 닿지 않는 곳(CLI 진입점·HTTP 처리기)에 두되, G4 verifier가 명세·코드 읽기로 잡을 수 있다는 점(D47)을 감안.
3. 작은 개선 후보(판정 변경 없이 가능): AC 없는 constraint·non-functional REQ를 G7·report에 "리뷰로만 확인"으로 표시(D50 결정 3), Windows 하네스가 남기는 `%TEMP%\vmodel-test-*`(git 읽기 전용 객체) 정리.
4. 확장(사용자 결정 전 자동 진입 금지): LITE/STRICT 프로파일, CI 연동(별도 사용자/CI에서 `vmodel audit`·`verify`), WorkMind 첫 적용.

## 바로 쓰는 명령
```bash
cd /home/cyyoo/develop/vmodel-devkit && git switch main
cd tests && python3 -m unittest discover -s . -p "test_*.py"; cd ..     # 하네스 559개, 약 33분(WSL)
python3 -I test-results/v0.3.0/release_check.py /tmp/x.json --released   # 확정 점검(v0.3.0 = main)
python3 scripts/red_green.py --mode red --plugin dist/vmodel-0.2.0 --marker RED-TARGET --log /tmp/r.log test_g7_gate ...
python3 -I test-results/v0.3.0/g7_demo.py dist/vmodel-0.3.0 /tmp/demo.txt   # 실제 G7 실행 시연(모델 호출 없음)
claude plugin validate --strict plugins/vmodel
python3 scripts/e2e/e2e_run.py --work <새 폴더> --sample textcli --setup-only   # E2E 샌드박스 확인(모델 호출 없음)
python3 scripts/e2e/e2e_verify.py --work <E2E 폴더> --out <json>             # E2E 판정(모델 호출 없음, G7 요약 포함)
```

## 꼭 알아야 할 것
- 상태는 `.vmodel/state/ledger.jsonl`(서명 원장)에서만 나옵니다. 테스트·드릴은 항상 임시 `VMODEL_HOME`.
- 릴리스는 불변입니다. 기존 태그와 `releases/vmodel-0.1.x.json`·`0.2.0.json`은 고치지 않습니다.
- DevKit 자체는 DevKit Validator로 승인하지 않습니다(SPEC §5.8). 검토 지적은 검토한 빌드(`git archive <커밋> plugins/vmodel`)를 RED 대상으로 직접 재현한 뒤 고칩니다(회차별 모듈: `test_g7_review.py`, `test_g7_review2.py`).
- 표시 문구에 "verified by"를 쓰면 안 됩니다: CLOSED 결함 전용(D37, 기존 시험이 status 전체 텍스트에서 확인).
- 시스템 테스트 시나리오의 시드 버그는 unit 테스트가 닿지 않는 곳(CLI 진입점, HTTP 처리기)에 둬야 G7까지 갑니다.
- 실제 Claude 실행은 비용이 드므로 매번 사용자 승인. `--dangerously-skip-permissions` 금지.
- 샌드박스를 판정할 때 `vmodel` 명령은 반드시 그 샌드박스의 `VMODEL_HOME`으로 실행합니다(없으면 서명 키를 못 찾아 전체 BLOCKED로 보이고 `report`는 그 내용으로 보고서 파일을 덮어씁니다, §19.4).
- 헤드리스 E2E에서 `system_test`·`integration_test`는 샘플의 `tests/system`·`tests/integration`에 테스트가 있어야 install이 등록합니다(`configure-tests`는 TTY 전용).
- Windows 회귀 사본: `%TEMP%\vmodel 한글 테스트\devkit-0.3.0-<커밋>`(git archive + `dist/vmodel-0.1.3`·`0.1.4`·`0.1.5`·`0.2.0`), 스크립트 `win-0.3.0-<커밋>.ps1`(UTF-16 BOM, 기존 `.venv`). 준비 스크립트 `test-results/v0.3.0/prep_windows.sh <커밋>`(ps1이 실행 전·직후·60초 뒤 Windows python 프로세스 목록도 남김; 스크립트 안 scratchpad 경로는 세션마다 바꿔 쓸 것). 실행: `cd /mnt/c && powershell.exe -NoProfile -ExecutionPolicy Bypass -File '<ps1 Windows 경로>'`(약 70분).
- `test_integrity.Upgrade.test_upgrade_requires_user_repin…`은 플러그인 사본의 파일을 고치는 시험이라 릴리스 사본 대상(`VMODEL_TEST_PLUGIN=dist/...`)에서는 원래 실패합니다(0.2.0 사본도 같음).
