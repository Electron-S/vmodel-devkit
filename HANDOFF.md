# HANDOFF

다음 세션이 이 파일만 읽고 이어갈 수 있게 정리한 인수인계입니다. 마지막 갱신: 2026-11-10(12차, 보수 정책 확정·guard 수정·G6 실패 드릴, 브랜치 `g6-dev`).

## 현재 상태 한 줄
**v0.2.0 릴리스 후보, 판정 RELEASE CONDITIONAL.** 판정 근거는 TEST_RESULTS §16.9와 최종 보고. 확정 버전은 여전히 0.1.5(태그 `v0.1.5` = `main` = `78517d5`). 후보 코드 `g6-dev`의 `20d2139`(이후 커밋은 기록·문서·드릴 스크립트), 릴리스 `dist/vmodel-0.2.0`(core `sha256:88edfac2…`, `releases/vmodel-0.2.0.json`). 이번 결정 D45(보수 정책 A·B), D46(guard 따옴표 텍스트), D47(드릴 결과).

## Git
- `main` = 태그 `v0.1.5` → `78517d5`(변경 없음). 태그 `v0.1.2`~`v0.1.5` 그대로. **`v0.2.0` 태그 없음, 병합 없음, 푸시 없음.**
- `g6-dev`: … `d9cae51`(11차 문서) → 이번 세션: 정책 RED `cb467ab` → `092a0fe` → `7c7b446` → 검토 12회차 `2efc0bc`·`c451a13` → 13회차 `c19aad5`·`9497d14` → 드릴 준비 `247297e` → 14회차 `ebcdf9d`·`fa815b3` → 릴리스 `0664a39` → 문서 → 드릴 S1 1차 → guard RED `d8541cf` → `11bb551` → 16회차 `f6ddc57`·`7526ce3` → 17회차 `50ebf4e`·`88971ac` → 18회차 `2c94801`·`690e757` → 19회차 `54013da`·`6f332f1`(허용 목록 문법) → 20회차 `6046e66`·`18bbcb8` → Windows 회귀 `629ab0a`·`20d2139` → 릴리스 `8874005` → 드릴 S1·S2 기록·문서.
- 원격 `origin/main`은 `bbd6a3d`. 푸시는 승인되지 않았습니다(`test-results/` 로그·트랜스크립트·드릴 산출물에 `/home/cyyoo`·`/tmp` 경로가 있음).
- `dist/vmodel-0.2.0`(git 제외)과 `releases/vmodel-0.2.0.json`(추적)은 **후보**. 확정 전에 코드를 바꾸면 `python3 scripts/release.py --force`.
- 작업 트리의 `.claude/`(예약 기능 잠금 파일)는 커밋하지 않음.

## G6 판정 규칙 요약 (정본 D41~D45, `docs/g6/G6-DESIGN.md` §1.3, WORKITEM §7.13)
1. 통합 테스트마다 증거 수준 Test-level / Suite-level / Insufficient. IF는 Test-level 테스트가 있어야 덮인다. 없으면 BLOCKED, 호출 경로조차 없으면 FAILED(D44).
2. **정책 A(D45)**: 테스트 함수나 그 테스트에 적용되는 fixture(요청·usefixtures·autouse)가 provider(인터페이스 심볼·provider 모듈 정의)를 patch하면 그 테스트는 경로 A·B 모두 Test-level이 아니다.
3. **정책 B(D45)**: 연결·provider 실행·(경로 B) consumer 실행은 앵커가 테스트 함수 또는 요청한 fixture·setUp일 때만 센다. 스레드는 시작·제출 스택에서, 프로세스는 계측의 spawn 줄과 `VMODEL_TRACE_ORIGIN` 토큰 사슬(Popen·os.system·posix_spawn·fork·multiprocessing)에서 출처를 잇는다. autouse·요청하지 않은 fixture가 한 일은 Suite-level.
4. 남은 공백(사용자 판단, D45 8항): 정적 patch 탐지가 닿지 않는 fixture 경로(import한 fixture, 기반 클래스, `pytest_plugins`, 루트 conftest, `MonkeyPatch.context()`), 조건부 autouse patch의 보수적 BLOCKED, 소켓 너머 요청 주체(H3), 자식 명령 문자열 속 patch(H4). 근본 대안은 실행 시점 patch 관찰(계측 재설계).

## guard (D46)
- Validator 호출의 따옴표 안 메타문자는 명령 전체가 좁은 허용 목록 문법에 맞을 때만 허용(따옴표 밖 `[A-Za-z0-9_./:=+-]`, 작은따옴표 안 따옴표류 없음, 큰따옴표 안 백틱·`$(`·`${`·`$[`·따옴표류 없음, bash 백슬래시 쌍은 줄바꿈 제외 허용, `.cmd`/`.bat` 제외, PowerShell은 따옴표 안 `& | < > ^ %`도 불허). 문법 밖은 0.1.x 판정 + 따옴표 밖 줄바꿈·PowerShell `(`.
- 남은 공백: PowerShell에서 cmd 내장 명령 뒤 `,`·`;`·`=`(예: `del,`)는 쓰기로 보지 않음(0.1.x부터).

## 다음 작업 (사용자 결정 필요)
1. **v0.2.0 확정 여부**: 실제 세션의 G6 FAILED → DEFECT → CLOSED는 미관찰(D47). 선택지: G4가 읽어서는 못 보는 유형(P6 환경, 검토 밖 의존 컴포넌트, 실행 시점 성질)으로 다시 드릴 / "놓친 G4 리뷰" 명시 주입(D27 방식, 이번 조건과 충돌) / 하네스 검증으로 수용. 모두 추가 유료 세션 승인 필요(이번 승인 3회 모두 사용, 합계 약 $1.15).
2. D45 8항·D46의 남은 공백을 받아들일지.
3. 원격 푸시: 승인 안 됨. 하려면 원격·포함 커밋·민감정보 점검을 먼저 보여 드리고 따로 결정.

## 바로 쓰는 명령
```bash
cd /home/cyyoo/develop/vmodel-devkit && git switch g6-dev
cd tests && python3 -m unittest discover -s . -p "test_*.py"; cd ..     # 하네스 474개, 약 24분(WSL)
python3 -I test-results/v0.2.0/release_check.py /tmp/x.json             # 릴리스·태그·버전 재확인
python3 scripts/red_green.py --mode red --plugin <git archive 사본>/plugins/vmodel --marker RED-TARGET --log /tmp/r.log <module>
python3 scripts/e2e/g6_drill.py setup --work <새 폴더>                     # 드릴 샌드박스(모델 호출 없음), 봉인 폴더는 <work>-sealed
python3 scripts/e2e/g6_drill.py seed-check|seed-apply --work <폴더> --seed <seed.json>   # 사본 확인 후 적용
python3 scripts/e2e/g6_drill.py verify --work <폴더> --tag <이름>          # 세션 뒤 판정, 모델 호출 없음
claude plugin validate --strict plugins/vmodel
```

## 꼭 알아야 할 것
- 상태는 `.vmodel/state/ledger.jsonl`(서명 원장)에서만 나옵니다. 테스트·드릴은 항상 임시 `VMODEL_HOME`.
- 릴리스는 불변입니다. 기존 태그와 `releases/vmodel-0.1.x.json`은 고치지 않습니다.
- DevKit 자체는 DevKit Validator로 승인하지 않습니다(SPEC §5.8). 검토 지적은 검토한 빌드(`git archive <커밋> plugins/vmodel`)를 RED 대상으로 직접 재현한 뒤 고칩니다(회차별 모듈 `test_g6_review12~14.py`, `test_guard_quoted*.py`).
- 실제 Claude 실행은 비용이 드므로 매번 사용자 승인. `--dangerously-skip-permissions` 금지.
- 계측 귀속·guard 인용 처리 모두 "고칠 때마다 반대쪽 오판이나 다른 우회"가 반복됐다. 규칙을 바꾸면 반드시 좁은 재검토 + WSL·Windows 전체 회귀. guard는 손으로 흉내 내지 말고 허용 목록으로.
- Windows 회귀가 WSL에서 못 잡은 결함(Windows 경로의 백슬래시)을 잡았다. 판정 경로를 바꾸면 Windows 회귀를 생략하지 말 것.
- Windows 회귀 사본: `%TEMP%\vmodel 한글 테스트\devkit-0.2.0-<커밋>`(git archive + `dist/vmodel-0.1.3`·`0.1.4`·`0.1.5`), 스크립트 `win-0.2.0-<커밋>.ps1`(UTF-16 BOM, 기존 `.venv`). 약 55분. 검토자가 만든 `%TEMP%\vmodel-reviewer-r19` 폴더는 지워도 됨.
