# HANDOFF

다음 세션이 이 파일만 읽고 이어갈 수 있게 정리한 인수인계입니다. 마지막 갱신: 2026-11-08(3차, 0.1.3 실제 재작업 세션 검증 후).

## 현재 상태 한 줄
기준 버전 0.1.2는 태그 `v0.1.2`(커밋 `bbd6a3d`)입니다. 그 위의 **0.1.3**(F1~F4 수정)을 이번에 실제 Claude 재작업 세션 1회(drill-3)로 검증했습니다. G5 FAILED 상태에서 DEFECT 기록, 수정, 재리뷰, G4·G5 PASS까지 진행해 PARTIALLY_VERIFIED가 됐고, 독립 audit·verify도 통과했습니다. 코드 수정은 필요 없었습니다. 회귀는 WSL 103/103, Windows(cp949) 103 실행·실패 0·skip 4(이전과 같은 4건)입니다. `v0.1.3` 태그는 아직 없고 사용자 결정을 기다립니다. WorkMind·G6/G7·LITE/STRICT는 손대지 않았습니다.

## Git
- `v0.1.2` 태그(annotated, 태그 객체 `f1ea8f7`) → 커밋 `bbd6a3d`. 로컬 태그이며 원격에 푸시하지 않았습니다.
- 브랜치 `rework-drill-0.1.3`: `021ddcb`(0.1.3 코드·드릴 결과) 다음에 이번 검증 문서·증거 커밋 1개가 있습니다(`git log --oneline main..rework-drill-0.1.3`). 코드·릴리스 파일은 `021ddcb`와 같습니다.
- `main`은 v0.1.2 그대로입니다. 병합·푸시하지 않았고 `v0.1.3` 태그도 없습니다.

## 바로 쓰는 명령
```bash
cd /home/cyyoo/develop/vmodel-devkit
cd tests && python3 -m unittest discover -s . -p "test_*.py"; cd ..     # 하네스 103개, 약 3.3~3.8분
claude plugin validate --strict plugins/vmodel
python3 scripts/release.py                                               # 새 버전이면 dist/vmodel-<ver>/ (기존 버전 덮어쓰기 금지)
dist/vmodel-0.1.3/bin/vmodel install --project <대상 프로젝트>
claude --plugin-dir dist/vmodel-0.1.3                                    # 세션 한정 로드
# 실전 재작업 드릴 (run은 비용 발생, 실행 전 사용자 승인). --release는 반드시 절대 경로
python3 scripts/e2e/rework_drill.py fork --source <drill-1> --work <new> --release "$PWD/dist/vmodel-0.1.3"
python3 scripts/e2e/drill_safety.py --work <dir> --tag <name> --release "$PWD/dist/vmodel-0.1.3"
python3 scripts/e2e/rework_drill.py run --work <dir> --phase s3 --prompt-file <p> --release "$PWD/dist/vmodel-0.1.3" --budget 1
```

## 이번 세션에서 확인한 것 (정본: TEST_RESULTS §9)
- 시작 상태: 이전 drill-1(S1 실제 산출물, 커밋된 사본과 바이트 동일)을 0.1.3으로 포크해 G5 FAILED(R00010, pytest 5/18 실패, stdout 해시가 drill-2와 동일)를 재현했습니다. **G4 승인 1건(R00008)은 하네스가 주입한 합성 픽스처**이고, 결함도 블라인드 시딩입니다. 자연 발생 실패가 아닙니다.
- 실제 세션 S3(sonnet 1회, $0.26/$1, 77초, S2와 같은 프롬프트): status로 실패를 확인한 뒤 DEFECT-001을 기록했습니다(P4, 실패 TEST 5/5 연결, `fixed`는 수정과 함께). 2줄 수정, lint, verifier 재리뷰 1회(R00011) 뒤 G4 PASSED(R00012), G5 PASSED(R00013)로 끝났습니다. 원장 직접 읽기·에이전트 pytest·테스트 수정은 모두 0회였습니다.
- 0.1.2(S2)와 비교하면 재작업 원장이 9건에서 3건으로, REVIEW_REQUIRED가 3건에서 0건으로, 재리뷰가 2회에서 1회로 줄었고 링크는 3/5에서 5/5가 됐습니다.
- F1·F3·F4는 통과, F2는 부분 통과입니다. 조회와 완전 연결은 실측했지만, 누락 경고 → 보완 경로는 실제 세션에서 생기지 않아 Validator 프로브(P-F2)로만 확인했습니다.
- 독립 audit OK(13→18건), `verify` 재평가 G1~G5 PASSED(pytest 18/18 재실행), 증거 4건 `verify-evidence` OK, core hash는 하나(`0208c798…`)였습니다. 원인 설명은 실패 5건과 독립 계산으로 일치했습니다(`root_cause_check.py`).
- 예산: `--max-budget-usd`는 print 모드에서 누적 추정 비용이 상한에 닿으면 실행을 멈춥니다. 다만 추정치이고 사후 검사라 진행 중인 요청만큼 넘을 수 있으며, 이번에는 상한에 닿지 않아 멈추는 동작은 실측하지 못했습니다.

## 설계 검토 (DECISIONS D32~D34, 구현 안 함)
- D32 결함 상태: 4단계 중 VERIFIED/CLOSED를 defects.json에 쓰면 F1이 재발합니다. 권장안은 (C)입니다. 파일은 `open/fixed`를 유지하고, Validator가 원장에서 OPEN/FIX_APPLIED/VERIFIED/CLOSED를 파생해 표시합니다. CLOSED는 "검증됐고 지금도 그 Gate가 PASSED"를 뜻합니다. 현재 `verified_by`는 STALE이 돼도 그대로 표시되는 구조적 빈틈이 있습니다.
- D33 미연결 실패 TEST: 지금은 경고만 유지합니다. 강제가 필요하면 "최종 완료 차단"(STALE 비용 재발, 기각)이 아니라 "재평가 전제 조건, 기록 없는 BLOCKED"로 갑니다.
- D34 고치지 않은 관찰 4건: guard의 `2>/dev/null` 오탐, verifier `reviewed_at` 부정확, 백그라운드 verifier 때문에 측정 턴 수가 적게 잡힘, 비신뢰 작업 공간에서 allow 규칙 무시.

## 꼭 알아야 할 것
- 상태는 `.vmodel/state/ledger.jsonl`(서명 원장)에서만 나옵니다. 서명 키와 앵커는 `$VMODEL_HOME`(기본 `~/.vmodel-devkit`)에 있고, 테스트·E2E·드릴은 항상 임시 `VMODEL_HOME`을 씁니다.
- 릴리스는 불변입니다. 플러그인 파일을 바꾸면 버전을 올리고 새로 릴리스합니다(D32·D34를 구현하면 0.1.4 이상).
- 훅은 `onFailure: "block"`에 의존합니다(D05, D18).
- 실제 Claude 실행(`scripts/e2e/*`의 run/probe)은 비용이 드므로 매번 사용자 승인을 받습니다. `--dangerously-skip-permissions`는 쓰지 않습니다.
- 드릴 샌드박스는 세션 스크래치에 있어 다음 세션에서는 사라질 수 있습니다. drill-1의 S1 산출물은 `test-results/drill/s1-drill-1/`에 사본이 있지만, 그 사본만으로 포크하려면 `rework_drill.py fork`의 `--source` 형식(프로젝트 폴더)에 맞춰 재구성해야 합니다.

## 미완료·다음 작업 (사용자 결정 필요)
1. `v0.1.3` 태그 여부(권장: 이번 문서 커밋에 태그, 코드는 `021ddcb`와 같음). main 병합·푸시도 사용자 결정입니다.
2. 다음 버전 후보(작게): D32 (C) 파생 표시 상태, D34의 guard `/dev/null` 예외, 측정 스크립트의 다중 result 집계. 각각 재현 테스트부터 만듭니다.
3. 남은 실제 세션 검증: 링크 누락 → 경고 → 보완 경로, 반복 표본, 주입 없는 G5 FAILED, drill-1(G4 FAILED)에서 시작하는 재작업, 상한 도달 시 멈춤.
4. 남은 미검증 항목(TEST_RESULTS §6, §9.13): Python 3.11, Windows에서 Claude Code 세션 자체, Windows 절대경로 deny 규칙, 대화형 세션, 마켓플레이스 설치 상태의 세션.
5. Extension(G6/G7, LITE/STRICT, CI 독립 재검증, WorkMind 적용)은 자동으로 진입하지 않습니다.

증거 위치: `test-results/drill/s3-drill-3/`(포크 계획·로그, 안전장치 결과, 세션 측정·검사·도구 호출 타임라인, 프로브 P-F1/P-F2, 원인 대조 스크립트와 결과, 세션 직후·최종 원장, audit, report, G5 증거 3건, 리뷰·결함·코드 사본). 원본 트랜스크립트는 `test-results/raw/transcript-drill-3-s3.jsonl`(git 제외). 이전 드릴은 `s1-drill-1/`, `s2-drill-2/`.
