# HANDOFF

다음 세션이 이 파일만 읽고 이어갈 수 있게 정리한 인수인계입니다. 마지막 갱신: 2026-11-09(8차, v0.1.5 확정).

## 현재 상태 한 줄
**v0.1.5 확정.** 이 커밋이 최종 검증 커밋이고 `main` fast-forward와 annotated 태그 `v0.1.5`가 이 커밋을 가리킵니다(TEST_RESULTS §13, DECISIONS D40). G6은 사용자가 정책 네 가지를 정했고, 확정 설계·구현 계획은 이 커밋 다음의 브랜치 `g6-dev`(D41, `docs/g6/G6-DESIGN.md`)에 있습니다. G6 구현은 시작하지 않았습니다.

## Git
- `main` = 태그 `v0.1.5` = 이 커밋(로컬). 이전 태그 `v0.1.2`→`bbd6a3d`, `v0.1.3`→`0df13b7`, `v0.1.4`→`991af67` 그대로. 원격 `origin/main`은 여전히 `bbd6a3d`이고 푸시는 승인되지 않았습니다.
- 브랜치 `v0.1.5-dev`도 이 커밋. G6 설계 문서는 `g6-dev`(이 커밋에서 시작).
- 릴리스: `dist/vmodel-0.1.5/`(git 제외, 43개 파일, core `sha256:37071459bd44…`), 기록 `releases/vmodel-0.1.5.json`. 이제 불변입니다. 플러그인 파일을 바꾸면 새 버전입니다.

## v0.1.5에서 바뀐 것 (정본: D38, SPEC §11, `docs/v0.1.5/WORKITEM.md`)
- 업그레이드는 새 릴리스의 `bin/vmodel lock --accept-current`(사용자 TTY) 한 번. 바뀔 규칙을 먼저 보여 주고, 검사 → 백업 → 설치 기록 소유권 → 새 규칙 추가 → 재고정(원장 기록 → lock) → 이전 DevKit 규칙 제거. 사용자 규칙은 남습니다.
- 확정 중 확인한 비용(D40): 업그레이드가 `.claude/settings.json`을 바꾸고 이 파일이 G4 코드 manifest에 있어서, **업그레이드 뒤 G4는 verifier 리뷰를 다시 받아야 합니다**(G1~G3은 리뷰 그대로 유효). SPEC §11·README에 반영했습니다.

## 확정 검증 요약 (TEST_RESULTS §13)
- 릴리스 0.1.0~0.1.5 사본·기록·소스 해시와 버전 문자열 일치(`test-results/v0.1.5/release_check.py`).
- 0.1.4 → 0.1.5 실제 사본 업그레이드: 쓰기 6지점과 각 지점 중단에서 권한 공백 없음, 사용자 규칙 유지, 재실행으로 마무리(`upgrade_gap_probe.py`).
- 릴리스 사본 대상 업그레이드·호환 테스트 42/42, 0.1.4 원장 보존·audit OK(`upgrade_review_cost_probe.py`).
- 깨끗한 worktree WSL 225/225(`8f0eaae`, 코드 트리가 확정 커밋과 같음). Windows는 `aae9a99` 결과(실패 0, skip 40)를 씁니다(트리 동일).

## 바로 쓰는 명령
```bash
cd /home/cyyoo/develop/vmodel-devkit
cd tests && python3 -m unittest discover -s . -p "test_*.py"; cd ..     # 하네스 225개, 약 12분
python3 -I test-results/v0.1.5/release_check.py /tmp/x.json             # 릴리스·태그·버전 재확인
python3 -I test-results/v0.1.5/upgrade_gap_probe.py dist/vmodel-0.1.4 dist/vmodel-0.1.5 /tmp/g.json
claude plugin validate --strict plugins/vmodel
```

## 다음 작업 (사용자 결정 필요)
1. G6: 브랜치 `g6-dev`의 `docs/g6/G6-DESIGN.md` §9 결정(해석 확인, N/A 리뷰 확인 범위, init 기본값, 업그레이드 G4 재리뷰 비용, 연결 정적 확인의 강도, 버전) 뒤 §7 절차로 구현.
2. 원격 푸시: 승인되지 않았습니다. 푸시 전 원격 정보, 포함 커밋·파일, 민감정보(`test-results/` 로그의 `/home/cyyoo`·`/tmp` 경로 등)를 점검해 보여 드리고 따로 결정합니다.
3. 남은 미검증: TEST_RESULTS §6, §9.13, §11.7, §12.7, §13.7.

## 꼭 알아야 할 것
- 상태는 `.vmodel/state/ledger.jsonl`(서명 원장)에서만 나옵니다. 테스트·드릴은 항상 임시 `VMODEL_HOME`을 씁니다.
- 릴리스는 불변입니다. 기존 태그와 `releases/*.json`은 고치지 않습니다.
- DevKit 자체는 DevKit Validator로 승인하지 않습니다(SPEC §5.8). 판정은 독립 하네스와 독립 검토가 합니다.
- 실제 Claude 실행(`scripts/e2e/*`의 run/probe)은 비용이 드므로 매번 사용자 승인을 받습니다. `--dangerously-skip-permissions`는 쓰지 않습니다.
- Windows 회귀 사본: `%TEMP%\vmodel 한글 테스트\devkit-0.1.5-aae9a99`, 실행 스크립트 `win-0.1.5-aae9a99.ps1`.
