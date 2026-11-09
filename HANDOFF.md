# HANDOFF

다음 세션이 이 파일만 읽고 이어갈 수 있게 정리한 인수인계입니다. 마지막 갱신: 2026-11-09(9차, v0.1.5 확정 + G6 설계 확정, 브랜치 `g6-dev`).

## 현재 상태 한 줄
**v0.1.5 확정**(태그 `v0.1.5` = `main` = `78517d5`, 로컬, TEST_RESULTS §13, D40). **G6은 정책 확정·설계 완료, 구현 전**입니다(D41, `docs/g6/G6-DESIGN.md`). 이 브랜치 `g6-dev`(기준 `v0.1.5`)에는 문서만 있고 플러그인·테스트 코드는 0.1.5와 같습니다.

## Git
- `main` = `v0.1.5-dev` = 태그 `v0.1.5`(태그 객체 `cc00936`) → 커밋 `78517d5`. 이전 태그 `v0.1.2`→`bbd6a3d`, `v0.1.3`→`0df13b7`, `v0.1.4`→`991af67` 그대로.
- `g6-dev`: `78517d5` 위에 G6 설계 문서 커밋. G6 구현도 이 브랜치에서 이어 갑니다.
- 원격 `origin/main`은 여전히 `bbd6a3d`. 푸시는 승인되지 않았습니다.
- 릴리스 `dist/vmodel-0.1.5/`(git 제외, 43개 파일, core `sha256:37071459bd44…`)와 `releases/vmodel-0.1.5.json`은 이제 불변입니다. 플러그인 파일을 바꾸면 새 버전(제안 0.2.0)입니다.

## G6 확정 정책 (정본: D41, 설계 `docs/g6/G6-DESIGN.md`)
1. `integration_test` 명령 필수(적용 대상일 때). 없으면 G6 BLOCKED, unit 명령 대체 실행 없음. 설정된 프로젝트는 G5.SCOPE/G6.SCOPE로 unit·integration 실행 범위를 나눔. 설정 없는 기존 프로젝트의 G5는 0.1.5와 같음(경고만).
2. G4가 통합 준비 상태(인터페이스 구현 심볼·통합 테스트 코드·IF별 함수 단위 정적 도달·IF별 리뷰), G6은 AI 리뷰 없이 자기 실행 증거와 다시 계산한 정적 도달로만 판정. gates.json G6 reviewer = none (mechanical).
3. N/A는 IF 0·integration 명세 0·단일 컴포넌트·G2와 G3 리뷰의 `integration_applicability` 확인(외부 끝점 포함)·이전 IF 삭제의 `removed_ids` 정당화가 모두 있을 때만. PASSED + `applicability: not_applicable`, 표시는 N/A, 결함 검증으로 치지 않음. 못 확인하면 BLOCKED.
4. 기존 WI는 G6 평가 전 IN_PROGRESS. G1~G5 manifest·판정 입력·기존 기록은 그대로. `gate_summary`로 Gate 결과와 WI 상태를 구분.

## 다음 작업 (사용자 결정 필요)
1. G6 구현 전 결정(설계 §9): (1) Core 교체 시 STALE 규칙 유지 해석 확인, (2) N/A 리뷰 확인을 G2·G3 둘 다(기본) 또는 G2만, (3) 새 init에 분리 명령 기본값, (4) 업그레이드마다 G4 재리뷰 비용(`.claude/settings.json`을 코드 manifest에서 뺄지), (5) 정적 도달 실패(기본)/경고, (6) 버전 0.2.0, (7) 범위를 지워 N/A가 된 G6 결함의 종료 표시, (8) E2E 비용.
   - 설계 초안은 독립 검토 1회(주요 6·부 8)를 반영했습니다(설계 §11). 구현 시작 전 기존 하네스 중 기대값이 바뀌는 목록(§6.1)을 다시 만듭니다.
2. 결정 뒤 설계 §7 절차: `docs/g6/WORKITEM.md` → 테스트 먼저 → RED(`dist/vmodel-0.1.5`) → 구현 → GREEN → 독립 검토 → 회귀 → E2E(비용 승인).
3. 원격 푸시: 승인되지 않았습니다. 푸시 전 원격 정보, 포함 커밋·파일, 민감정보(`test-results/` 로그의 `/home/cyyoo`·`/tmp` 경로 등)를 점검해 보여 드리고 따로 결정합니다.
4. 남은 미검증: TEST_RESULTS §6, §9.13, §11.7, §12.7, §13.7.

## 바로 쓰는 명령
```bash
cd /home/cyyoo/develop/vmodel-devkit && git switch g6-dev
cd tests && python3 -m unittest discover -s . -p "test_*.py"; cd ..     # 하네스 225개, 약 12분
python3 -I test-results/v0.1.5/release_check.py /tmp/x.json             # 릴리스·태그·버전 재확인
python3 scripts/red_green.py --mode red --plugin dist/vmodel-0.1.5 --log /tmp/r.log <test_g6_...>   # G6 RED (구현 세션)
claude plugin validate --strict plugins/vmodel
```

## 꼭 알아야 할 것
- 상태는 `.vmodel/state/ledger.jsonl`(서명 원장)에서만 나옵니다. 테스트·드릴은 항상 임시 `VMODEL_HOME`을 씁니다.
- 릴리스는 불변입니다. 기존 태그와 `releases/*.json`은 고치지 않습니다.
- 업그레이드 뒤에는 G4 verifier 리뷰를 다시 받아야 합니다(0.1.5에서 확인, D40).
- DevKit 자체는 DevKit Validator로 승인하지 않습니다(SPEC §5.8). 판정은 독립 하네스와 독립 검토가 합니다.
- 실제 Claude 실행(`scripts/e2e/*`의 run/probe)은 비용이 드므로 매번 사용자 승인을 받습니다. `--dangerously-skip-permissions`는 쓰지 않습니다.
- Windows 회귀 사본: `%TEMP%\vmodel 한글 테스트\devkit-0.1.5-aae9a99`, 실행 스크립트 `win-0.1.5-aae9a99.ps1`.
