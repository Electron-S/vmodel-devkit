# HANDOFF

다음 세션이 이 파일만 읽고 이어갈 수 있게 정리한 인수인계입니다. 마지막 갱신: 2026-11-08(2차, 실전 재작업 드릴 후).

## 현재 상태 한 줄
기준 버전 0.1.2는 태그 `v0.1.2`(커밋 `bbd6a3d`)로 고정했습니다. 그 위에 실전 재작업 드릴에서 찾은 결함 4건(F1~F4)을 고친 **0.1.3**을 별도 커밋으로 올렸습니다. 하네스는 WSL 103/103, Windows(cp949) 103 실행·실패 0·skip 4입니다. 0.1.3을 실제 Claude 세션으로 돌려보지는 않았습니다. WorkMind·G6/G7·LITE/STRICT는 손대지 않았습니다.

## Git
- `v0.1.2` 태그(annotated, 태그 객체 `f1ea8f7`) → 커밋 `bbd6a3d`. 로컬 태그이며 원격에 푸시하지 않았습니다.
- 0.1.3 변경은 브랜치 `rework-drill-0.1.3`의 `bbd6a3d` 다음 커밋 하나에 들어 있습니다(`git log --oneline main..rework-drill-0.1.3`). `main`은 v0.1.2 그대로입니다. 푸시·병합하지 않았고, `v0.1.3` 태그도 아직 없습니다(실제 세션 확인 후 사용자가 결정).

## 바로 쓰는 명령
```bash
cd /home/cyyoo/develop/vmodel-devkit
cd tests && python3 -m unittest discover -s . -p "test_*.py"; cd ..     # 하네스 103개, 약 3.8분
claude plugin validate --strict plugins/vmodel
python3 scripts/release.py                                               # 새 버전이면 dist/vmodel-<ver>/ (기존 버전 덮어쓰기 금지)
dist/vmodel-0.1.3/bin/vmodel install --project <대상 프로젝트>
claude --plugin-dir dist/vmodel-0.1.3                                    # 세션 한정 로드
# 실전 재작업 드릴 (비용 발생, 실행 전 사용자 승인)
python3 scripts/e2e/rework_drill.py setup|probe|run|fork|inspect ...     # 사용법: 파일 머리말, TEST_RESULTS §8.1
python3 scripts/e2e/drill_safety.py --work <drill dir> --tag <name>      # 모델 호출 없음, 변조 후 원상 복구
```

## 이번 세션에서 확인한 것 (정본: TEST_RESULTS §8)
- S1(실제 sonnet 세션): 요구사항부터 구현까지 진행하고 결함 1개를 블라인드 시딩했습니다. verifier는 pytest가 막힌 상태에서 코드를 손으로 추적해 결함을 잡았고 G4가 FAILED가 됐습니다. G5까지는 가지 않았습니다.
- G5 경로: S1의 실제 산출물에 G4 승인 리뷰 1건만 하네스로 주입했습니다(D27). 이후 Validator가 직접 pytest를 실행했고, 18개 중 5개가 실패해 G5 FAILED가 기록됐습니다(R00010). 안전장치 프로브는 11/11 통과했습니다.
- S2(실제 sonnet 세션, 시딩 정보 없음): DEFECT-001(원인 단계 P4, 봉인 계획과 일치)을 기록하고 2줄을 고쳤습니다. 테스트는 바꾸지 않았습니다. verifier 재리뷰 후 G5 PASSED(R00014), 최종 상태는 PARTIALLY_VERIFIED입니다. 이어서 독립 audit과 `vmodel verify`도 통과했습니다.
- 비용: haiku 1회와 sonnet 2회로 약 $1.04입니다. 승인받은 3회를 모두 썼습니다.

## 0.1.3 변경 (D28~D30)
- F1: `status: fixed`는 수정과 같은 단계에서, 재리뷰 전에 바꿉니다. 통과 뒤에는 defects.json을 건드리지 않습니다. 스킬(start, rework), verifier, VMODEL.md, ARTIFACTS.md에 반영했습니다.
- F2: 원장에서 결함 추적을 파생합니다. `failing_tests`, `unlinked_failing_tests`, `verified_by`를 status/lint/report에서 보여주며, 누락이 있어도 막지 않고 경고만 합니다.
- F3: `status`가 FAILED/BLOCKED Gate의 실패 체크와 실패 TEST ID를 출력합니다.
- F4: verifier의 G4 체크리스트에 "원인이 모든 실패를 설명하는가"를 넣고, 통과 후 defects.json 수정을 요구하지 못하게 했습니다.
- Core 해시가 바뀌었습니다(`a0555e32…` → `0208c798…`). 0.1.2로 설치된 프로젝트는 재고정 전까지 BLOCKED이고, 재고정하면 이전 PASS는 STALE이 됩니다(README의 업그레이드 절차).

## 꼭 알아야 할 것
- 상태는 `.vmodel/state/ledger.jsonl`(서명 원장)에서만 나옵니다. 서명 키와 앵커는 `$VMODEL_HOME`(기본 `~/.vmodel-devkit`)에 있고, 테스트·E2E·드릴은 항상 임시 `VMODEL_HOME`을 씁니다.
- 릴리스는 불변입니다. 플러그인 파일을 바꾸면 버전을 올리고 새로 릴리스합니다.
- 훅은 `onFailure: "block"`에 의존합니다(D05, D18).
- 실제 Claude 실행(`scripts/e2e/*`)은 비용이 드므로 매번 사용자 승인을 받습니다. `--dangerously-skip-permissions`는 쓰지 않습니다. `--permission-mode auto`에서는 스킬의 단일 명령 규칙을 어긴 묶음 명령도 통과합니다(D31).
- G5 FAILED는 G4 리뷰가 결함을 놓쳤을 때만 실제로 생깁니다. 이번 드릴에서는 verifier가 읽기만으로 결함을 잡았습니다.

## 미완료·다음 작업 (사용자 결정 필요)
1. 0.1.3 실제 세션 확인: drill-2와 같은 G5 FAILED 상태에서 0.1.3으로 재작업 세션 1회(sonnet, 예상 $0.3~0.6). `fixed` 시점, 링크 완전성, verifier의 원인 대조가 실제로 바뀌는지 봅니다. 확인되면 `v0.1.3` 태그.
2. 완전 실제 G4 FAILED 경로(drill-1)의 재작업 세션 1회. drill-1 샌드박스는 세션 스크래치에 있어 다음 세션에서는 없을 수 있으니 `rework_drill.py setup` + S1부터 다시 해야 할 수 있습니다.
3. 남은 미검증 항목(TEST_RESULTS §6): Python 3.11, Windows에서 Claude Code 세션 자체, Windows 절대경로 deny 규칙, 대화형 세션, 마켓플레이스 설치 상태의 세션.
4. Extension(G6/G7, LITE/STRICT, CI 독립 재검증, WorkMind 적용)은 자동으로 진입하지 않습니다.

증거 위치: `test-results/drill/`(봉인 계획, 측정·검사 JSON, 안전장치 결과, audit, 원장 사본, G5 증거 4건, 리뷰·결함·코드 사본). 원본 트랜스크립트는 `test-results/raw/transcript-drill-*.jsonl`(git 제외).
