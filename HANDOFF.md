# HANDOFF

다음 세션이 이 파일만 읽고 이어갈 수 있게 정리한 인수인계입니다. 마지막 갱신: 2026-11-09(10차, v0.2.0 후보: G6 구현·검증, 브랜치 `g6-dev`).

## 현재 상태 한 줄
**v0.2.0 릴리스 후보(G6 Integration Verification) 준비 완료, 사용자 확정 전.** 확정 버전은 여전히 0.1.5(태그 `v0.1.5` = `main` = `78517d5`). 후보 코드는 `g6-dev`의 `14b34af`(이후 커밋은 테스트 1건 이동과 문서), 릴리스 `dist/vmodel-0.2.0`(core `sha256:f835ec91…`, `releases/vmodel-0.2.0.json`). 검증 TEST_RESULTS §14, 결정 D42·D43, 작업 기록 `docs/g6/WORKITEM.md`.

## Git
- `main` = 태그 `v0.1.5` → `78517d5`(변경 없음). 태그 `v0.1.2`→`bbd6a3d`, `v0.1.3`→`0df13b7`, `v0.1.4`→`991af67`, `v0.1.5`→`78517d5` 그대로. **`v0.2.0` 태그 없음, 병합 없음, 푸시 없음.**
- `g6-dev`: `fe38239`(설계) → 테스트 먼저(`c6bc3ce`…) → 구현 `3239eba` → 검토 수정 `c216910`·`08469ae`·`14b34af` → 문서·기록. 플러그인 트리는 `14b34af` 이후 바뀌지 않았다.
- 원격 `origin/main`은 `bbd6a3d`. 푸시는 승인되지 않았습니다.
- `dist/vmodel-0.2.0`(git 제외)과 `releases/vmodel-0.2.0.json`(추적)은 **후보**입니다. 확정 전에 코드를 바꾸면 `python3 scripts/release.py --force`로 같은 버전을 다시 만들고 기록을 갱신합니다. 확정 뒤에는 불변.

## G6 요약 (정본: D41·D42·D43, `docs/g6/G6-DESIGN.md`, `docs/g6/WORKITEM.md`)
1. 실행: config `integration_test`를 Validator가 직접 실행. 적용 대상인데 없으면 BLOCKED `misconfigured`(unit 명령 대체 없음). 새 `init`은 실제로 있고 테스트 함수가 있는 경로만 등록하고 unit에 `--ignore`(D3). 기존 프로젝트는 사용자 전용 `vmodel configure-tests --integration PATH`(TTY, 원장 `config` 기록).
2. G4: TEST_CODE에 integration, INTERFACE_IMPLEMENTED, INTEGRATION_WIRING(TEST ID를 가진 함수 하나하나가 경로 A 호출 기반 정적 경로 또는 verifier가 `runtime_paths`로 선언한 경로 B; placeholder·import-only·도달 없음 FAILED), 리뷰 `interfaces` 필수.
3. G6: 계측(`tracer/sitecustomize.py`)이 본 실행만 근거. 경로 A = 정적 경로 + 그 함수 실행 + 실행 전체에서 provider 실행(테스트별 귀속은 경고, D43). 경로 B = 호출 단계 증거, subprocess·ipc는 다른 프로세스. 증거 부족·계측 없음 = BLOCKED `integration_evidence_insufficient`.
4. N/A: IF 0·통합 명세 0·단일 컴포넌트·G2와 G3 리뷰의 `integration_applicability`·`removed_ids` 정당화가 모두 있을 때만. 표시 N/A, 결함 검증 아님. G6 실패 결함의 범위를 정당하게 지우면 결함 표시 OUT_OF_SCOPE(D7).
5. G1~G5: IF·통합 명세 없는 WI와 `integration_test` 없는 config는 0.1.5와 같은 판정·manifest. G5에는 설정 시만 SCOPE. Core 교체 STALE 규칙 유지(D1). settings.json은 G4 manifest에 그대로(D4).

## 다음 작업 (사용자 결정 필요)
1. **v0.2.0 확정 여부**: 확정하면 `main`에 `--ff-only` 병합, 최종 커밋에 annotated 태그 `v0.2.0`(0.1.5 확정 절차와 같게, 확정 검증 포함). 확정 전에 4회차 독립 검토(3회차 수정 `14b34af` 대상)를 할지도 결정할 것(§14.9).
2. **실전 E2E 승인**(D8): 계획 `docs/g6/WORKITEM.md` §8. 시나리오 A(Provider/Consumer, G6 실패→결함→수정→재검증, 기존 코드+통합 테스트가 있는 표본, 블라인드 시딩), 시나리오 B(단일 컴포넌트 N/A). sonnet 최대 2회, 회당 $2, 합계 $4. 승인 뒤 표본 준비·`scripts/e2e/e2e_run.py` 표본 선택 옵션 → 모델 호출 없는 setup/expect → run.
3. 원격 푸시: 승인되지 않았습니다. 푸시 전 원격 정보, 포함 커밋·파일, 민감정보(`test-results/` 로그의 `/home/cyyoo`·`/tmp` 경로 등)를 점검해 보여 드리고 따로 결정합니다.
4. 남은 미검증: TEST_RESULTS §6, §9.13, §11.7, §12.7, §13.7, §14.9.

## 바로 쓰는 명령
```bash
cd /home/cyyoo/develop/vmodel-devkit && git switch g6-dev
cd tests && python3 -m unittest discover -s . -p "test_*.py"; cd ..     # 하네스 360개, 약 18분(WSL)
python3 -I test-results/v0.2.0/release_check.py /tmp/x.json             # 릴리스·태그·버전 재확인
python3 scripts/red_green.py --mode red --plugin dist/vmodel-0.1.5 --marker RED-TARGET --log /tmp/r.log test_g6_gate ...
python3 -I test-results/v0.2.0/g6_demo.py dist/vmodel-0.2.0 /tmp/demo.txt   # G6 실행 시연(모델 호출 없음)
claude plugin validate --strict plugins/vmodel
```

## 꼭 알아야 할 것
- 상태는 `.vmodel/state/ledger.jsonl`(서명 원장)에서만 나옵니다. 테스트·드릴은 항상 임시 `VMODEL_HOME`을 씁니다.
- 릴리스는 불변입니다. 기존 태그와 `releases/vmodel-0.1.x.json`은 고치지 않습니다.
- 업그레이드 뒤에는 G4 verifier 리뷰를 다시 받아야 합니다(D40, D4 결정으로 유지).
- DevKit 자체는 DevKit Validator로 승인하지 않습니다(SPEC §5.8). 판정은 독립 하네스와 독립 검토가 합니다. 검토 지적은 검토한 빌드(`git archive <커밋> plugins/vmodel`)를 RED 대상으로 직접 재현한 뒤 고칩니다(지적 모듈 `test_g6_review*.py`를 회차별로 분리).
- `red_green.py --marker RED-TARGET`: Red 실패가 목표 assertion인지 확인합니다. 그래도 실패 사유는 로그에서 직접 읽습니다(1차 RED에서 도우미 결함으로 "엉뚱한 이유의 RED"가 섞였었음).
- 실제 Claude 실행(`scripts/e2e/*`의 run/probe)은 비용이 드므로 매번 사용자 승인을 받습니다. `--dangerously-skip-permissions`는 쓰지 않습니다.
- Windows 회귀 사본: `%TEMP%\vmodel 한글 테스트\devkit-0.2.0-5e64974`(git archive + `dist/vmodel-0.1.3`·`0.1.4`·`0.1.5` 복사), 실행 스크립트 `win-0.2.0-5e64974.ps1`(UTF-16 BOM, 기존 `.venv`). 약 40분.
