# HANDOFF

다음 세션이 이 파일만 읽고 이어갈 수 있게 정리한 인수인계입니다. 마지막 갱신: 2026-11-09(7차, v0.1.5 후보).

## 현재 상태 한 줄
**v0.1.5 릴리스 후보가 브랜치 `v0.1.5-dev`에 있습니다(병합·태그·푸시 안 함).** 업그레이드 때 프로젝트 `.claude/settings.json`의 DevKit allow·deny 규칙이 이전 릴리스 절대경로에 남던 문제를 재현하고 고쳤습니다(DECISIONS D38, TEST_RESULTS §12). 확정 버전은 여전히 **v0.1.4**(태그 `v0.1.4` = `main` = `991af67`, 로컬)입니다. G6은 착수 전 결정 네 가지의 결정안만 정리했고 구현하지 않았습니다(D39, `docs/g6/G6-DESIGN-PROPOSAL.md`, 사용자 결정 대기).

## Git
- 브랜치 `v0.1.5-dev`(기준 `991af67`): `0e691d0` 수정 → `c57f7c5` 1차 검토 반영 → `be372f4` 재검토 반영 → `aae9a99` 세 번째 확인 반영(마지막 코드 커밋) → 문서·검증 기록 커밋.
- `main`, 태그 `v0.1.2`·`v0.1.3`·`v0.1.4`는 바꾸지 않았습니다. 원격 `origin/main`은 여전히 `bbd6a3d`이고 푸시는 승인되지 않았습니다.
- 릴리스 후보: `dist/vmodel-0.1.5/`(git 제외, 43개 파일, core `sha256:37071459bd44…`), 기록 `releases/vmodel-0.1.5.json`, `dist/.claude-plugin/marketplace.json`이 0.1.5를 가리킵니다. 태그 전이라 코드가 바뀌면 `release.py --force`로 다시 빌드합니다. 이 PC에서 DevKit을 설치한 실제 프로젝트·마켓플레이스 등록은 없음을 확인했습니다(`~/.claude/plugins`, 프로젝트 settings 검색).

## 바뀐 것 (정본: D38, SPEC §11, `docs/v0.1.5/WORKITEM.md`)
- 업그레이드는 새 릴리스의 `bin/vmodel lock --accept-current`(사용자 TTY) 한 번입니다. 확인 전에 바뀔 규칙을 보여 주고, 검사(쓰기 없음) → 백업(`.vmodel/install/backup/upgrade-<시각>/`) → 설치 기록 소유권 → 새 규칙 추가 → 재고정(원장 기록 → lock) → 이전 DevKit 규칙 제거 순서입니다.
- DevKit 규칙은 설치 기록 `added_deny`·`added_allow`로만 식별합니다. 사용자 규칙은 남습니다. deny는 보호 하한이라 다시 넣고, 사용자가 지운 DevKit allow는 다시 허용하지 않습니다(`declined_allow`로 유지).
- 원장 기록 전 실패·Ctrl-C는 settings·설치 기록·lock을 바이트 그대로 복원합니다. 그 뒤 실패는 이전+새 규칙 상위 집합으로 남기고 재실행으로 마무리합니다. 바꿀 것이 없으면 쓰지 않습니다.
- 그 밖: 생성 deny 규칙에 `Edit(/.vmodel/install/**)` 추가, 하위 명령 옵션 축약 금지(`--accept`), 다른 경로·버전이 설치한 프로젝트에 install하면 재고정 안내, TTY 확인을 settings 읽기 전에.
- 바꾸지 않은 것: `hook.py`(0.1.4와 바이트 동일), Gate 판정, 원장 기록 형식, manifest, uninstall.

## 검증 요약 (TEST_RESULTS §12)
- 재현: 0.1.3 → 0.1.4 릴리스 사본으로 문제 재현, 0.1.4 → 0.1.5 사본으로 수정 확인(`test-results/v0.1.5/repro-*.json`).
- RED: `test_upgrade_settings`는 불변 0.1.4 릴리스에서 Red 10건 실패, 검토 지적 테스트는 각 수정 전 빌드(`0e691d0`·`c57f7c5`·`be372f4` 사본)에서 실패를 확인한 뒤 고쳤습니다. GREEN은 소스와 빌드된 0.1.5 사본 양쪽.
- 회귀: WSL·Windows 결과는 §12.3. 독립 검토 3회(지적은 재현 후 수정, 반영하지 않은 2건은 근거 기록).

## 바로 쓰는 명령
```bash
cd /home/cyyoo/develop/vmodel-devkit && git switch v0.1.5-dev
cd tests && python3 -m unittest discover -s . -p "test_*.py"; cd ..     # 하네스 225개, 약 11분
python3 scripts/red_green.py --mode green --log /tmp/y.log test_upgrade_settings test_upgrade_review test_upgrade_review2 test_upgrade_review3
python3 scripts/red_green.py --mode red --plugin dist/vmodel-0.1.4 --log /tmp/r.log test_upgrade_settings
python3 -I test-results/v0.1.5/upgrade_repro.py dist/vmodel-0.1.4 dist/vmodel-0.1.5 /tmp/repro.json
claude plugin validate --strict plugins/vmodel
```

## 미완료·다음 작업 (사용자 결정 필요)
1. v0.1.5 확정 여부: 확정하면 문서 커밋에 annotated 태그 `v0.1.5`, `main` fast-forward. 지금은 승인되지 않았습니다.
2. G6 결정 네 가지(D39): 1 실행 명령(권장: 선택 `integration_test`, 없으면 unit 명령으로 G6 직접 재실행), 2 테스트 코드 확인 위치(권장: G4.TEST_CODE 확장, G6은 기계 판정), 3 IF 0개(권장: IF 0·통합 명세 0일 때만 N/A, 기록 PASSED + applicability), 4 업그레이드 영향(권장: IN_PROGRESS 복귀를 의도된 동작으로 문서화). 결정 전 G6/G7 구현 금지.
3. 원격 푸시: 승인되지 않았습니다. 푸시 전 원격 정보, 포함 커밋·파일, 민감정보(`test-results/` 로그의 `/home/cyyoo`·`/tmp` 경로 등)를 점검해 보여 드리고 따로 결정합니다.
4. 남은 미검증: TEST_RESULTS §6, §9.13, §11.7, §12.7(실제 세션에서의 업그레이드, 마켓플레이스 캐시 경로, Windows pty 경로, 다운그레이드 자동화 없음).

## 꼭 알아야 할 것
- 상태는 `.vmodel/state/ledger.jsonl`(서명 원장)에서만 나옵니다. 테스트·드릴은 항상 임시 `VMODEL_HOME`을 씁니다.
- 릴리스는 불변입니다. 0.1.5 태그 전에는 같은 버전 재빌드(`--force`)가 가능하고, 태그 뒤 플러그인 파일을 바꾸면 0.1.6입니다.
- 이번 세션의 검토용·회귀용 worktree와 플러그인 사본은 세션 스크래치(`/tmp/claude-1000/…/scratchpad/`)에 있어 다음 세션에는 없을 수 있습니다. 수정 전 빌드는 `git archive <커밋> plugins/vmodel`로 다시 만들 수 있습니다.
- Windows 회귀 사본: `%TEMP%\vmodel 한글 테스트\devkit-0.1.5-aae9a99`, 실행 스크립트 `win-0.1.5-aae9a99.ps1`.
- 실제 Claude 실행(`scripts/e2e/*`의 run/probe)은 비용이 드므로 매번 사용자 승인을 받습니다. `--dangerously-skip-permissions`는 쓰지 않습니다.
