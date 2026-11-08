# VModel DevKit

Claude Code용 V-Model 개발 환경입니다. 요구사항(G1) → 아키텍처(G2) → 상세 설계·테스트 명세(G3) → 구현(G4) → 단위 검증(G5)을 Quality Gate로 나누고, **독립 Validator가 직접 실행하고 서명한 증거로만** Gate를 통과시킵니다. AI가 "통과했다"고 쓴 파일이나 보고는 증거로 인정하지 않습니다.

현재 버전은 **MVP(0.1.4)** 입니다. STANDARD 프로필의 G1~G5만 동작하고, G6(통합)·G7(시스템)·LITE·STRICT는 설계만 되어 있습니다. 그래서 G1~G5를 모두 통과한 Work Item도 `PARTIALLY_VERIFIED`까지만 갑니다. V-Model 전체 완료가 아닙니다.

자세한 요구사항과 Gate 정의는 [SPEC.md](SPEC.md), 설계 결정은 [DECISIONS.md](DECISIONS.md), 검증 결과는 [TEST_RESULTS.md](TEST_RESULTS.md)에 있습니다.

## 필요 환경

- Python 3.11 이상 (표준 라이브러리만 사용). 샘플/대상 프로젝트의 테스트 실행에는 pytest가 필요합니다.
- Claude Code 2.1.295 이상 (훅의 `onFailure: "block"` 필요). 2.1.319에서 검증했습니다.
- Windows: Git for Windows(Git Bash)가 있어야 훅과 `bin/vmodel` 런처가 동작합니다. `bin\vmodel.cmd`는 cmd/PowerShell용입니다.
- 정적 분석: ruff 권장(없으면 설치 시 사용자가 `--allow-syntax-only`로 문법 검사만 하겠다고 명시해야 함).

## 저장소 구성

```
plugins/vmodel/            Claude Code 플러그인 (이름: vmodel)
  validator/               Validator Core (vmodel.py + vmodel_validator/, gates.json, schemas)
  skills/                  /vmodel:start, status, verify, rework, report
  agents/                  verifier, test-designer (+ 역할 지침 4종)
  hooks/hooks.json         PreToolUse guard (fail-closed), SessionStart 상태 복원
  bin/vmodel, vmodel.cmd   런처 (Python 3.11+ 탐색, -I -B 격리 실행)
scripts/release.py         고정 릴리스 생성 (dist/vmodel-<ver>/ + 해시 매니페스트)
scripts/e2e/               실제 Claude 헤드리스 실행 도구 (비용 발생, 회당 상한)
releases/                  릴리스별 파일 해시 기록 (신뢰 기준)
samples/textstats/         Python + pytest 샘플 프로젝트
tests/                     Validator 부트스트랩 하네스 (unittest, 94개)
```

## 빠른 시작

1. 릴리스를 만듭니다. 이미 있는 버전 디렉터리는 덮어쓰지 않습니다.
   ```bash
   python3 scripts/release.py          # -> dist/vmodel-0.1.4/
   ```
2. 대상 프로젝트에 설치합니다. 프로젝트 파일만 바꿉니다: `.vmodel/` 생성, `.claude/settings.json`에 보호용 deny 규칙과 validator CLI 허용(allow) 규칙 병합(기존 값 보존·백업·충돌 보고). CLAUDE.md는 건드리지 않습니다.
   ```bash
   dist/vmodel-0.1.4/bin/vmodel install --project /path/to/project            # ruff 자동 탐지
   dist/vmodel-0.1.4/bin/vmodel install --project . --lint none --allow-syntax-only   # 린터 없이(축소 범위를 명시)
   dist/vmodel-0.1.4/bin/vmodel install --project . --claude-md-import        # 선택: CLAUDE.md 끝에 @.vmodel/VMODEL.md 한 줄 추가
   ```
   소스가 `src/`에 없으면 `--source 'mypkg/**/*.py'`를 지정합니다. 서명 키는 `$VMODEL_HOME`(기본 `~/.vmodel-devkit`)에 생깁니다.
3. 플러그인을 붙입니다. 둘 중 하나를 고르세요.
   - 세션 한정 (전역 설정 변경 없음): `claude --plugin-dir /path/to/dist/vmodel-0.1.4`
   - 프로젝트 범위 등록 (`~/.claude/plugins` 레지스트리에 기록됨):
     ```bash
     claude plugin marketplace add /path/to/dist --scope project
     claude plugin install vmodel@vmodel-devkit --scope project
     ```
4. Claude Code에서 사용합니다.

| 원래 이름 | 실제 명령 | 하는 일 |
|---|---|---|
| /vmodel-start | `/vmodel:start <요청>` | Work Item을 만들고 P1~P5 진행 (개발 요청에는 자동 트리거되기도 함) |
| /vmodel-status | `/vmodel:status [WI]` | Gate 상태, STALE 파일, 무결성, 다음 할 일 |
| /vmodel-verify | `/vmodel:verify <WI> [G#]` | 저장된 결과를 믿지 않고 처음부터 재검증 (G5는 테스트 재실행) |
| /vmodel-rework | `/vmodel:rework [WI]` | 실패 분석 → DEFECT 기록 → 원인 단계 수정 → 재검증 |
| /vmodel-report | `/vmodel:report <WI>` | `.vmodel/reports/<WI>.md` 생성 |

플러그인 네임스페이스 규칙 때문에 `/vmodel-start`가 아니라 `/vmodel:start`입니다.

## 사용자만 할 수 있는 일

guard 훅이 에이전트의 실행을 막습니다. 터미널에서 직접 실행하세요.

- 3회 연속 같은 원인으로 막힌 Gate 해제: `vmodel unblock WI-001 G5 --reason "..."` (TTY 필요)
- Validator 업그레이드 후 재고정: `vmodel lock --accept-current --reason "0.1.4로 업그레이드"` (TTY 필요, 이전 PASS는 모두 STALE)
- 설치/제거: `vmodel install`, `vmodel uninstall`, 데이터까지 삭제 `vmodel uninstall --purge` (TTY 필요)

## 업그레이드와 제거

- 업그레이드 (0.1.1 → 0.1.2로 실제 검증한 절차):
  1. `dist/vmodel-0.1.1/bin/vmodel uninstall --project <dir>` — 옛 버전이 추가한 settings 항목 제거(데이터 유지)
  2. `dist/vmodel-0.1.2/bin/vmodel install --project <dir>` — 새 버전 경로로 deny/allow 규칙 추가
  3. 터미널에서 `dist/vmodel-0.1.2/bin/vmodel lock --accept-current --reason "..."` — Core 해시 재고정(재고정 전에는 모든 Gate BLOCKED)
  4. 플러그인 경로(`--plugin-dir` 또는 마켓플레이스)를 새 릴리스로 바꿉니다. 원장 이력은 유지되고, 기존 PASS는 Core가 바뀌었으므로 모두 STALE이 되어 다시 검증해야 합니다.
- 제거: `vmodel uninstall --project <dir>`는 설치 기록에 있는 항목만 되돌립니다(deny 규칙, 선택적으로 추가한 CLAUDE.md 한 줄·플러그인 항목). 프로젝트 범위로 등록했다면 `claude plugin uninstall vmodel@vmodel-devkit --scope project`, `claude plugin marketplace remove vmodel-devkit --scope project`도 실행합니다.

## DevKit 자체 테스트

```bash
cd tests && python3 -m unittest discover -s . -p "test_*.py"      # 약 2~3분
python3 scripts/release.py --out /tmp/x --no-record                 # 릴리스 빌드 점검
claude plugin validate --strict plugins/vmodel
```

Validator의 정확성은 이 하네스로만 판정합니다. DevKit 개발 자체를 DevKit Validator로 승인하지 않습니다(순환 검증 금지).

## 신뢰 모델과 한계 (요약)

- 상태의 유일한 원천은 HMAC 서명·해시 체인 원장이고, 프로젝트 밖 앵커가 삭제·롤백·재초기화를 잡습니다.
- 테스트는 Validator가 정리된 환경에서 직접 실행하고, 원본 출력 바이트와 해시를 증거로 남깁니다.
- 코드 Gate는 프로젝트 전체 파일을 해시합니다. 무엇이든 바뀌면 PASS는 STALE이 됩니다.
- Gate 리뷰는 verifier 서브에이전트만 원장에 등록할 수 있습니다(훅이 `agent_type`으로 확인).
- **한계**: 같은 OS 사용자 권한으로 임의 코드를 실행하는 에이전트를 완전히 막지는 못합니다(키 읽기, 스크립트를 통한 우회, 테스트 코드의 같은 프로세스 내 조작). 훅과 권한 규칙은 OS 격리가 아닙니다. 최종 신뢰 경계는 CI나 별도 사용자가 신뢰 사본으로 `vmodel audit`와 `vmodel verify`를 돌리는 것입니다(Extension).
