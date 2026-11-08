# HANDOFF

다음 세션이 이 파일만 읽고 이어갈 수 있게 정리한 인수인계입니다. 마지막 갱신: 2026-11-08.

## 현재 상태 한 줄
VModel DevKit MVP(0.1.2): M0~M4 완료. 하네스 94/94(WSL), Windows 94 실행·실패 0. 실제 Claude 새 세션이 샘플 WI를 G1~G5 PASSED(PARTIALLY_VERIFIED)까지 완주. WorkMind는 손대지 않았습니다(범위 밖). Extension에는 진입하지 않았습니다.

## 바로 쓰는 명령
```bash
cd /home/cyyoo/develop/vmodel-devkit
cd tests && python3 -m unittest discover -s . -p "test_*.py"; cd ..     # 하네스 94개, 약 2.5분
claude plugin validate --strict plugins/vmodel
python3 scripts/release.py                                               # 새 버전이면 dist/vmodel-<ver>/ 생성 (기존 버전 덮어쓰기 금지)
dist/vmodel-0.1.2/bin/vmodel install --project <대상 프로젝트>
claude --plugin-dir dist/vmodel-0.1.2                                    # 세션 한정 로드
```

## 꼭 알아야 할 것
- 상태는 `.vmodel/state/ledger.jsonl`(서명 원장)에서만 나옵니다. 서명 키와 앵커는 `$VMODEL_HOME`(기본 `~/.vmodel-devkit`). 테스트·E2E는 항상 임시 `VMODEL_HOME`을 씁니다.
- 릴리스는 불변입니다. 플러그인 파일을 바꾸면 버전을 올리고(`validator/vmodel_validator/__init__.py`, `.claude-plugin/plugin.json`) 새로 릴리스합니다. 이력: PLAN.md "버전 이력".
- 훅은 Claude Code 2.1.295+의 `onFailure: "block"`에 의존합니다(D05, D18 실측).
- 헤드리스 실행에서 플러그인 파일 Read는 거부됩니다(프로젝트 밖) → 스킬·에이전트는 `vmodel guide <topic>`을 씁니다(0.1.1).
- 에이전트가 명령을 `;`/`&&`/변수/루프로 묶으면 권한 매칭이 안 됩니다 → 스킬·에이전트에 "한 번에 한 명령" 규칙(0.1.2).
- 실제 Claude 실행 도구: `scripts/e2e/hook_probe.py`(haiku), `scripts/e2e/e2e_run.py`(sonnet, `--continue`로 새 세션 이어가기, `--permission-mode auto|acceptEdits`). **비용이 드니 실행 전 사용자 승인 필요.** 이번 세션 승인(haiku 4회·sonnet 3회) 중 haiku 3회·sonnet 3회 사용, 총 약 $1.02. `--dangerously-skip-permissions`는 자동 모드 분류기가 막으니 쓰지 말 것.

## 미검증·남은 일 (MVP 범위)
TEST_RESULTS.md의 "미검증 항목"이 정본입니다. 요약: Python 3.11 실물 실행, Windows에서 Claude Code 세션 자체(훅·스킬)를 띄우는 것, Windows 경로용 절대경로 deny 규칙 형식, 실제 세션에서의 FAILED→재작업 루프(하네스로만 검증), 대화형(사람이 승인하는) 세션 측정, 마켓플레이스 설치 상태로의 세션 실행.

증거 위치: `test-results/`(E2E 측정 JSON, 훅 실측, E2E-3 산출물 사본과 보고서, Windows 로그), 원본 트랜스크립트 `test-results/raw/`(git 제외). Windows 테스트 사본과 venv는 `%TEMP%\vmodel 한글 테스트`에 남아 있음(재실행용, 지워도 됨).

## Extension (자동 진입 금지, 사용자 결정 후)
G6/G7 실행, LITE/STRICT, 다중 언어(JUnit 일반화), 커버리지 기준, CI 독립 재검증(`vmodel audit`/`verify`를 별도 사용자로), 사용자 결정의 암호학적 결속, 서명 릴리스, WorkMind 적용.
