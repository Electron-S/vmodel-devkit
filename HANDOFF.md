# HANDOFF

다음 세션이 이 파일만 읽고 이어갈 수 있게 정리한 인수인계입니다. 마지막 갱신: 2026-11-11(13차, 최종 위험 판단·v0.2.0 확정, 브랜치 `g6-dev` → `main`).

## 현재 상태 한 줄
**v0.2.0 확정(RELEASE READY, TEST_RESULTS §17.7).** 태그 `v0.2.0`(annotated) = `main` = 이 문서를 담은 최종 기록 커밋, 최종 코드 `f49bc5c`(이후 플러그인 트리 변경 없음), 릴리스 `dist/vmodel-0.2.0`(core `sha256:2a95adb35aa82abc1ab6380350fd2f3b03ce3d645255d0263f4e48e234228a47`, `releases/vmodel-0.2.0.json`). 알려진 한계: 실제 세션의 G6 FAILED → DEFECT → CLOSED 경로 미관찰(하네스로만 검증, D47·§17.8). 이번 결정 D48(남은 거짓 PASS를 실행 시점 사실로 막음, guard `del,` 우회 수정, 위험 최종 분류).

## Git
- `main` = 태그 `v0.2.0` → 최종 기록 커밋(`--ff-only`). 태그 `v0.1.2`~`v0.1.5` 그대로(`v0.1.5` → `78517d5`). **원격 푸시 없음.**
- `g6-dev`: … 12차 기록 → 이번 세션: 출발 확인 `e4aaaf5` → 잔여 RED `65d3cc6`·guard RED → D48 `733d708` → 23회차 RED·`86dbf98` → 인스턴스 RED·`c399b1a` → 25회차 RED·`291d18b` → 26회차 RED·`8849672` → `e581b36`(14회차 C5 불변 시험 이동, `release_check.py --released`) → `f3c1cbb`(Case F: 컴포넌트 밖 import 제외) → `f49bc5c`(28회차: 절대 import 해석) → 최종 기록.
- 원격 `origin/main`은 `bbd6a3d`. 푸시는 승인되지 않았습니다(`test-results/` 로그·트랜스크립트·드릴 산출물에 `/home/cyyoo`·`/tmp` 경로가 있음). 하려면 `git log origin/main..main`과 민감정보 점검을 먼저 보여 드리고 따로 결정.
- `dist/vmodel-0.2.0`(git 제외)은 확정 릴리스입니다. **다시 빌드하지 마세요**(`release.py --force` 금지). 다음 변경은 새 버전으로.
- 작업 트리의 `.claude/`(예약 기능 잠금 파일)는 커밋하지 않음.

## G6 판정 규칙 요약 (정본 D41~D45·D48, `docs/g6/G6-DESIGN.md` §1.3, WORKITEM §7.13)
1. 통합 테스트마다 증거 수준 Test-level / Suite-level / Insufficient. IF는 Test-level 테스트가 있어야 덮인다. 없으면 BLOCKED, 호출 경로조차 없으면 FAILED(D44).
2. **정책 A(D45)**: 테스트 함수나 그 테스트에 적용되는 fixture(요청·usefixtures·autouse)가 provider를 patch하면 그 테스트는 경로 A·B 모두 Test-level이 아니다. **D48 R1**: 정적 탐지와 별도로, provider 함수가 시작될 때 계측이 provider 모듈의 이름(직접 정의한 def·class·메서드, 모듈 수준 인스턴스의 메서드, 다른 전역, 같은 컴포넌트에서 가져온 이름)이 mock·테스트 트리 코드·문자열 코드·테스트 트리 클래스(인스턴스)로 바뀌었는지 본다. 다른 컴포넌트·외부 라이브러리에서 가져온 이름의 스텁과 설정 상수 patch는 경고(G4 리뷰 몫).
3. **정책 B(D45)**: 연결·provider 실행·(경로 B) consumer 실행은 앵커가 테스트 함수 또는 요청한 fixture·setUp일 때만 센다. **D48 R2**: autouse·요청하지 않은 fixture가 그 테스트에서 스레드·풀 작업·프로세스를 시작했으면 메인 스레드 증거만 센다(정상 코드도 BLOCKED될 수 있음, 분류 A).
4. 위험 분류의 정본은 TEST_RESULTS §17.3(D45)·§17.4(guard). 재현된 분류 B(거짓 PASS)는 모두 BLOCKED.

## guard (D46·D48)
- Validator 호출의 따옴표 안 메타문자는 명령 전체가 좁은 허용 목록 문법에 맞을 때만 허용(D46). cmd 내장 쓰기 명령 뒤 `, ; = /`도 쓰기(D48, `del,` 실제 삭제 우회 수정).
- 남은 것: 정상 명령 차단(PowerShell 따옴표 안 `& | < > ^ %`, 문법 밖 Validator 호출). 주장하지 않음: 모든 셸 문법·임의 코드 실행의 통제(D24·D25).

## 다음 작업 (사용자 결정 필요)
1. **G7 System Verification(PLAN M6, 제안 0.3.0)**: 선행 조건은 갖춰졌지만 착수는 사용자 결정. 실제 Claude 실행은 횟수·상한 승인 후에만.
2. 실제 세션의 G6 FAILED 경로 관찰(D47 선택지)은 원하면 추가 유료 세션 승인 후.
3. 원격 푸시: 승인 안 됨.

## 바로 쓰는 명령
```bash
cd /home/cyyoo/develop/vmodel-devkit && git switch g6-dev
cd tests && python3 -m unittest discover -s . -p "test_*.py"; cd ..     # 하네스 503개, 약 35분(WSL)
python3 -I test-results/v0.2.0/release_check.py /tmp/x.json --released  # 확정 릴리스·태그·main 재확인
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
