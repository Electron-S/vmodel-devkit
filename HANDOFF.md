# HANDOFF

다음 세션이 이 파일만 읽고 이어갈 수 있게 정리한 인수인계입니다. 마지막 갱신: 2026-11-11(14차, G7 System Verification 구현·v0.3.0 릴리스 후보, 브랜치 `g7-dev`).

## 현재 상태 한 줄
**v0.3.0 릴리스 후보 준비 완료(TEST_RESULTS §18.9), 확정은 사용자 결정.** 브랜치 `g7-dev`(마지막 판정 코드 `12e3caf`, 릴리스 기록 `8eb93ff`), 후보 릴리스 `dist/vmodel-0.3.0`(core `sha256:8abab9ec86fef66fb6e21b8b13aa29bc27bd29adbb76a2df75608dd1ceee4bb5`, `releases/vmodel-0.3.0.json`). 확정 버전은 여전히 0.2.0(`main` = 태그 `v0.2.0` = `c4b508a`). 결정 D49, 설계 정본 `docs/g7/G7-DESIGN.md`.

## Git
- `main` = 태그 `v0.2.0` = `c4b508a`(이번에 움직이지 않음). 태그 `v0.1.2`~`v0.2.0` 그대로. `v0.3.0` 태그 없음. **원격 푸시 없음.**
- `g7-dev`: 설계 `cfce1e9` → 테스트 `b3c79b2` → 구현 `68b4d67` → 검토 RED `2c26356` → 수정 `7939f97` → 재검토 RED `172a599` → 수정 `12e3caf` → 버전 `de270aa` → 릴리스 기록 `8eb93ff` → 문서·로그 `1deef79` → 시험 수정 `fa43a03` → 결과 기록.
- 확정하려면(사용자 승인 후): 이 브랜치 최종 커밋을 `main`에 `--ff-only` 병합, annotated 태그 `v0.3.0`, `python3 -I test-results/v0.3.0/release_check.py <out> --released`. 플러그인 트리가 바뀌면 같은 버전 재빌드는 `release.py --force`(공개 전만).
- 원격 `origin/main`은 `bbd6a3d`. 푸시는 승인되지 않았다(`test-results/` 로그·데모 출력에 `/home/cyyoo`·`/tmp` 경로). 하려면 `git log origin/main..main`과 민감정보 점검을 먼저 보여 주고 따로 결정.
- `dist/vmodel-0.2.0` 이하는 확정 릴리스(다시 빌드 금지). `dist/.claude-plugin/marketplace.json`은 0.3.0 후보를 가리킨다(git 제외).
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
1. **v0.3.0 확정**(병합·태그): 위 Git 절차.
2. 실제 Claude 세션 E2E(G7 포함 `/vmodel:start`~COMPLETED, G7 FAILED 재작업, 0.2.0 → 0.3.0 업그레이드)는 횟수·상한 승인 후에만.
3. 원격 푸시: 승인 안 됨.
4. 이번에 남긴 위험(TEST_RESULTS §18.9): 시스템 테스트의 블랙박스 여부는 리뷰 판단, G5·G6은 여전히 파이프 출력(남은 자식 프로세스 대기 가능성), Windows는 끝난 뒤 남은 자식 프로세스를 종료하지 않음.

## 바로 쓰는 명령
```bash
cd /home/cyyoo/develop/vmodel-devkit && git switch g7-dev
cd tests && python3 -m unittest discover -s . -p "test_*.py"; cd ..     # 하네스 559개, 약 33분(WSL)
python3 -I test-results/v0.3.0/release_check.py /tmp/x.json              # 후보 점검(태그 없음, main = v0.2.0)
python3 scripts/red_green.py --mode red --plugin dist/vmodel-0.2.0 --marker RED-TARGET --log /tmp/r.log test_g7_gate ...
python3 -I test-results/v0.3.0/g7_demo.py dist/vmodel-0.3.0 /tmp/demo.txt   # 실제 G7 실행 시연(모델 호출 없음)
claude plugin validate --strict plugins/vmodel
```

## 꼭 알아야 할 것
- 상태는 `.vmodel/state/ledger.jsonl`(서명 원장)에서만 나옵니다. 테스트·드릴은 항상 임시 `VMODEL_HOME`.
- 릴리스는 불변입니다. 기존 태그와 `releases/vmodel-0.1.x.json`·`0.2.0.json`은 고치지 않습니다.
- DevKit 자체는 DevKit Validator로 승인하지 않습니다(SPEC §5.8). 검토 지적은 검토한 빌드(`git archive <커밋> plugins/vmodel`)를 RED 대상으로 직접 재현한 뒤 고칩니다(회차별 모듈: `test_g7_review.py`, `test_g7_review2.py`).
- 표시 문구에 "verified by"를 쓰면 안 됩니다: CLOSED 결함 전용(D37, 기존 시험이 status 전체 텍스트에서 확인).
- 시스템 테스트 시나리오의 시드 버그는 unit 테스트가 닿지 않는 곳(CLI 진입점, HTTP 처리기)에 둬야 G7까지 갑니다.
- 실제 Claude 실행은 비용이 드므로 매번 사용자 승인. `--dangerously-skip-permissions` 금지.
- Windows 회귀 사본: `%TEMP%\vmodel 한글 테스트\devkit-0.3.0-<커밋>`(git archive + `dist/vmodel-0.1.3`·`0.1.4`·`0.1.5`·`0.2.0`), 스크립트 `win-0.3.0-<커밋>.ps1`(UTF-16 BOM, 기존 `.venv`). 준비 스크립트는 이번 세션 scratchpad의 `prep_windows.sh`(같은 절차).
- `test_integrity.Upgrade.test_upgrade_requires_user_repin…`은 플러그인 사본의 파일을 고치는 시험이라 릴리스 사본 대상(`VMODEL_TEST_PLUGIN=dist/...`)에서는 원래 실패합니다(0.2.0 사본도 같음).
