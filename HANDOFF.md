# HANDOFF

다음 세션이 이 파일만 읽고 이어갈 수 있게 정리한 인수인계입니다. 마지막 갱신: 2026-11-09(6차, v0.1.4 확정).

## 현재 상태 한 줄
**v0.1.4를 기준 버전으로 확정했습니다.** 이 문서가 들어 있는 최종 검증 커밋에 annotated 태그 `v0.1.4`를 붙이고 `main`을 fast-forward했습니다(로컬). **원격 푸시는 하지 않았고 승인되지 않았습니다.** 0.1.4 범위는 F1 결함 표시 상태 6종(OPEN·FIX_APPLIED·REVERIFY_REQUIRED·VERIFICATION_FAILED·CLOSED·UNKNOWN, D32 (C)·D37), F2 guard `/dev/null` 오탐 수정과 리디렉션 우회 차단(D36), F3 실패 TEST 증거 정확성(D35 P1)입니다. 검증은 WSL 186/186, Windows cp949 186 실행·실패 0·skip 6, 첫 0.1.4 빌드·0.1.3 대상 RED, 독립 검토 2회, 실제 Claude Code 세션 1회(sonnet, $0.15, guard 우회 0)로 했습니다. G6/G7·LITE/STRICT·WorkMind는 손대지 않았습니다.

## Git
- 태그: `v0.1.2`→`bbd6a3d`, `v0.1.3`→`0df13b7`(변경 없음), `v0.1.4`→ 최종 검증 커밋(`git rev-parse v0.1.4^{commit}`). 모두 로컬에만 있습니다. `origin/main`은 `bbd6a3d`입니다.
- `main`은 `v0.1.4`와 같은 커밋입니다(fast-forward). `v0.1.4-dev` 브랜치는 남겨 두었습니다.
- 0.1.4 커밋 흐름: `68f64e7` F2 → `14f46b5` F3 → `2d4f5c6` F1 → `817b9aa`·`4c13447`·`89ead99` 검토 반영 → `8ac43c8` 첫 릴리스 기록 → `48403ad` 첫 검증 문서 → `73d158e` 표시 상태 6종 → `c4e4da5` 검토 지적 → `e0358a5` 재검토 지적(마지막 코드 커밋) → 최종 검증 문서 커밋.
- 릴리스: `dist/vmodel-0.1.4/`(git 제외, 43개 파일, core `sha256:5dd1d010…`), 기록 `releases/vmodel-0.1.4.json`. 공개 전이라 같은 버전으로 세 번 다시 빌드했습니다(core 이력은 TEST_RESULTS §11.1). **이제 태그를 붙였으므로 플러그인 파일을 바꾸면 0.1.5로 올립니다.**

## 바로 쓰는 명령
```bash
cd /home/cyyoo/develop/vmodel-devkit
cd tests && python3 -m unittest discover -s . -p "test_*.py"; cd ..     # 하네스 186개, 약 11분
python3 scripts/red_green.py --mode green --log /tmp/y.log test_guard_redirects test_defect_closure test_defect_evidence test_version_compat test_defect_display_states
claude plugin validate --strict plugins/vmodel
dist/vmodel-0.1.4/bin/vmodel install --project <대상 프로젝트>          # 기존 설치는 재고정(TTY) 필요, 이전 PASS는 STALE
# 실제 세션 검증(비용 발생, 매번 사용자 승인): setup/expect/inspect는 모델 호출 없음
python3 -I scripts/e2e/live_session.py setup --work <새 폴더> --drill <drill-3 폴더>
python3 -I scripts/e2e/live_session.py expect --work <폴더>
python3 -I scripts/e2e/live_session.py run --work <폴더> --budget 1     # 승인 후에만
python3 -I scripts/e2e/live_session.py inspect --work <폴더>
```
`tests/helpers.py`의 `VMODEL_TEST_PLUGIN`으로 하네스 대상 플러그인을 바꿀 수 있습니다. `old_release("0.1.3")`은 `dist/vmodel-0.1.3`이 없으면 git 태그에서 복원하고 해시를 대조합니다. 표시 상태 RED 대상(첫 0.1.4 빌드, core `b1fee43f…`)은 git 태그가 없으므로 다시 만들려면 `8ac43c8`의 `plugins/vmodel`을 꺼내 쓰면 됩니다.

## 이번 세션에 바뀐 것 (정본: DECISIONS D37, SPEC §7, TEST_RESULTS §11, `docs/v0.1.4/WORKITEM.md` §9)
- 결함 표시 상태: VERIFIED를 없앴습니다. STALE·REVIEW_REQUIRED·BLOCKED면 REVERIFY_REQUIRED, 결함이 인용한 Gate 중 하나라도 마지막 PASS/실패 평가가 실패면 VERIFICATION_FAILED, 원장 무결성 실패나 증거 보류 PASS면 UNKNOWN입니다. "verified by"는 CLOSED에만 쓰고, 과거 성공은 "previously passed in"으로 표시합니다. JSON 추가 키는 `verification_history`, `last_verification`, `closure_action`입니다. defects.json·Gate 판정·원장·manifest는 그대로입니다.
- 독립 검토 2회: 1차 부 지적 4건, 2차 nit 1건을 재현 후 고쳤습니다. 교차 Gate 증상 동시 인용, 보류 PASS의 JSON 표시는 한계로 남겼습니다(D37).
- 실제 세션(§11.4): 정상 읽기·`/dev/null` 읽기·pytest 허용, Bash 쓰기 우회 8건 guard 차단, Edit/Write 2건은 프로젝트 deny 규칙이 guard보다 먼저 차단, 알려진 오탐 1건 차단, 우회 0. 워크플로우 REVERIFY_REQUIRED → G1~G5 재검증 → CLOSED, audit·verify-evidence·lint OK, 독립 확인과 일치.

## 미완료·다음 작업 (사용자 결정 필요)
1. 원격 푸시: 승인되지 않았습니다. 푸시하려면 먼저 원격 정보, 포함 커밋·파일, 민감정보(서명 키 값 없음 확인, `test-results/` 로그·세션 기록에 `/home/cyyoo`·`/tmp` 경로가 있음)를 점검해 보여 드리고 따로 결정합니다. 태그 `v0.1.2`~`v0.1.4`도 로컬에만 있습니다.
2. Extension 계획(PLAN.md §확장): M5 G6 → M6 G7 → M7. 자동으로 진입하지 않습니다.
3. 남은 미검증: TEST_RESULTS §6, §9.13, §11.7(guard의 Edit/Write 차단은 실제 세션에서 guard까지 가지 않음, 대화형·기본 권한 모드·Windows 세션, 신뢰된 작업 공간의 allow 규칙, Python 3.11).
4. 관찰(범위 밖): 업그레이드 때 프로젝트 `.claude/settings.json`의 allow·deny 규칙이 이전 릴리스 경로를 가리킨 채 남습니다(SPEC §11에 설정 갱신 절차 없음).

## 꼭 알아야 할 것
- 상태는 `.vmodel/state/ledger.jsonl`(서명 원장)에서만 나옵니다. 테스트·드릴은 항상 임시 `VMODEL_HOME`을 씁니다.
- 릴리스는 불변입니다. `v0.1.4` 태그 이후 플러그인 파일을 바꾸면 0.1.5로 올립니다.
- drill-3 샌드박스(서명 키 포함)는 이전 세션 스크래치(`/tmp/claude-1000/-home-cyyoo-develop-vmodel-devkit/3327e00b-…/scratchpad/drill-3`)에 있었고, 이번 세션의 실제 세션 샌드박스도 세션 스크래치라 다음 세션에는 없을 수 있습니다. 커밋된 사본은 서명 키가 없습니다.
- 실제 Claude 실행(`scripts/e2e/*`의 run/probe)은 비용이 드므로 매번 사용자 승인을 받습니다. `--dangerously-skip-permissions`는 쓰지 않습니다.
