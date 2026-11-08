# HANDOFF

다음 세션이 이 파일만 읽고 이어갈 수 있게 정리한 인수인계입니다. 마지막 갱신: 2026-11-09(5차, v0.1.4 구현·검증 후).

## 현재 상태 한 줄
**v0.1.4 구현·검증을 마쳤고, 브랜치 `v0.1.4-dev`에만 있습니다.** main 병합, `v0.1.4` 태그, 원격 푸시는 하지 않았고 사용자 결정을 기다립니다. 범위는 사용자가 확정한 3개 항목입니다: F1 결함 종료 상태(OPEN/FIX_APPLIED/VERIFIED/CLOSED 파생), F2 guard `/dev/null` 오탐과 리디렉션 우회, F3 실패 TEST 증거 정확성(D35 P1, 정책 A·B·C). 검증은 하네스 WSL 162/162, Windows cp949 162 실행·실패 0·skip 5, 0.1.3 릴리스 대상 RED 확인, 항목별 독립 검토, drill-3 실제 원장 복사본 확인으로 했습니다. 0.1.4로 실제 Claude 세션은 돌리지 않았습니다(비용 0). WorkMind·G6/G7·LITE/STRICT는 손대지 않았습니다.

## Git
- `main` = `e6fc892`(변경 없음). 태그 `v0.1.2`→`bbd6a3d`, `v0.1.3`→`0df13b7` 그대로이며, 모두 로컬에만 있습니다. `origin/main`은 `bbd6a3d`입니다.
- `v0.1.4-dev`(main에서 분기, `git log --oneline main..v0.1.4-dev`): `68f64e7` F2 → `14f46b5` F3 → `2d4f5c6` F1 → `817b9aa` 검토 반영 → `4c13447`·`89ead99` 재검토 반영 → `8ac43c8` 버전 0.1.4·릴리스 기록·교차 버전 테스트·문서 → 검증 결과 문서 커밋.
- 릴리스: `dist/vmodel-0.1.4/`(git 제외, 43개 파일, core `sha256:b1fee43f…`), 기록 `releases/vmodel-0.1.4.json`. 0.1.0~0.1.3 사본·기록은 그대로입니다.

## 바로 쓰는 명령
```bash
cd /home/cyyoo/develop/vmodel-devkit
cd tests && python3 -m unittest discover -s . -p "test_*.py"; cd ..     # 하네스 162개, 약 5~8분
# RED/GREEN 대조 (클래스 접미사 Red/Char/Invariant/Accept). RED 대상은 불변 0.1.3 릴리스
python3 scripts/red_green.py --mode red --plugin dist/vmodel-0.1.3 --log /tmp/x.log test_guard_redirects test_defect_closure test_defect_evidence
python3 scripts/red_green.py --mode green --log /tmp/y.log test_guard_redirects test_defect_closure test_defect_evidence test_version_compat
claude plugin validate --strict plugins/vmodel
dist/vmodel-0.1.4/bin/vmodel install --project <대상 프로젝트>          # 기존 설치는 재고정(TTY) 필요, 이전 PASS는 STALE
```
`tests/helpers.py`의 `VMODEL_TEST_PLUGIN`으로 하네스 대상 플러그인을 바꿀 수 있습니다. `old_release("0.1.3")`은 `dist/vmodel-0.1.3`이 없으면 git 태그에서 복원하고 `releases/*.json`과 해시를 대조합니다.

## 이번에 바뀐 동작 (정본: DECISIONS D36, SPEC §5·§7, `docs/v0.1.4/WORKITEM.md`)
- guard: Bash 명령에서 쓸 수 없는 리디렉션(정확히 `/dev/null`로 가는 출력, fd 복제·닫기, 단순 입력)을 지운 뒤 쓰기를 판정합니다. 0.1.3이 놓친 `&>`, `>&파일`, `x2>&파일`, 동사·플래그 사이 리디렉션 쓰기를 새로 잡습니다. PowerShell 도구, `NUL`·`$null`은 예전처럼 차단합니다. 알려진 오탐은 2종입니다: 따옴표 안의 `&>`, fd 복제 바로 뒤의 따옴표.
- 결함 점검: 유효한 실패 증거는 같은 WI의 FAILED 또는 3회 BLOCKED 기록뿐입니다. 분류는 오류 `evidence_integrity`·`invalid_citation`, 경고 `unlinked_failing_test`·`unknown_test_result`이고, status·lint·report가 같은 이름을 씁니다. lint는 하나라도 있으면 1을 냅니다. report에는 `## Defect trace check` 절이 항상 있습니다. G1~G4 실패는 N/A로 표시합니다.
- 종료 상태: OPEN, FIX_APPLIED, VERIFIED(검증됐지만 그 Gate가 지금 PASSED 아님), CLOSED가 있고, 원장 무결성 실패 시에는 UNKNOWN입니다. 종료 Gate는 인용된 실패 중 가장 하위 Gate입니다.
- Gate 판정, 원장 형식, manifest 계산은 그대로입니다. 0.1.3과 같은 이력에서 판정 투영과 manifest가 일치합니다.

## 미완료·다음 작업 (사용자 결정 필요)
1. `v0.1.4-dev` → main 병합(fast-forward 가능), `v0.1.4` 태그, 원격 푸시. 푸시 전에 원격 정보, 포함 커밋·파일, 민감정보(서명 키 값, 로컬 경로가 든 로그: `test-results/v0.1.4/*.json·*.log`에 `/home/cyyoo`·`/tmp` 경로가 있음)를 점검해서 보여 드리고 따로 결정합니다.
2. VERIFIED 상태 이름: 독립 검토자가 "완료로 읽힐 수 있다"며 REVERIFY_NEEDED 같은 이름을 제안했습니다. 사용자가 정한 이름이라 유지했습니다. 바꿀지 결정이 필요합니다.
3. 선택: 0.1.4로 실제 Claude 세션 1회(비용 승인 필요). 특히 guard 변경이 auto 권한 모드와 함께 실제 세션에서 오탐 없이 동작하는지 확인합니다.
4. Extension 계획(PLAN.md §확장): M5 G6 → M6 G7 → M7. 자동으로 진입하지 않습니다.
5. 남은 미검증: TEST_RESULTS §6, §9.13, §10.8.

## 꼭 알아야 할 것
- 상태는 `.vmodel/state/ledger.jsonl`(서명 원장)에서만 나옵니다. 테스트·드릴은 항상 임시 `VMODEL_HOME`을 씁니다.
- 릴리스는 불변입니다. 0.1.4를 공개(태그·푸시)한 뒤 플러그인 파일을 바꾸면 0.1.5로 올립니다. 공개 전 같은 버전 재빌드는 `scripts/release.py --force`입니다.
- drill-3 샌드박스(서명 키 포함)는 이전 세션 스크래치(`/tmp/claude-1000/-home-cyyoo-develop-vmodel-devkit/3327e00b-…/scratchpad/drill-3`)에 아직 있었습니다. 다음 세션에는 없을 수 있습니다. `test-results/v0.1.4/drill3_check.py`는 원본을 복사본으로만 다룹니다.
- 실제 Claude 실행(`scripts/e2e/*`의 run/probe)은 비용이 드므로 매번 사용자 승인을 받습니다. `--dangerously-skip-permissions`는 쓰지 않습니다.
