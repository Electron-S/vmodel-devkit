# PLAN

현재 목표: M0~M4 (MVP). M4 완료 후 Extension에 자동 진입하지 않는다.

| 마일스톤 | 내용 | 완료 기준 (테스트) | 상태 |
|---|---|---|---|
| M0 | 환경 조사, SPEC/DECISIONS 확정 | SPEC.md·DECISIONS.md 작성, 환경 사실 기록 | 완료 |
| M1 | WI 모델, 스키마, 상태 머신, 추적성, G1~G3 | 하네스: 스키마·ID·추적·리뷰 해시·STALE(산출물)·T10·T11 | 완료 |
| M2 | G4~G5, Test Runner, 증거, 해시·STALE, 재작업 루프 | 하네스: T05~T09, T12, T13, T17, 3회 실패 BLOCKED, 인코딩 | 완료 (+독립 리뷰 반영 하드닝) |
| M3 | Skills, Subagents, Hooks, 패키징, 설치/제거/버전 | 하네스: guard 훅 판정, 설치·제거·T15·T16, `claude plugin validate`, 실제 훅 동작(헤드리스 haiku ≤4회) | 완료 |
| M4 | 샘플 프로젝트 E2E | 스크립트 E2E(T01~T18 하네스), Windows 실행(T18), 실제 Claude 세션 3회(sonnet, 회당 $4 상한), 새 세션 상태 복원(T14) | 완료 (TEST_RESULTS §3) |

## 환경 사실 (M0 조사, 2026-11-08)
- 개발 OS: WSL2 Ubuntu 24.04 (Linux 6.6), Python 3.12.3, pytest 9.0.3, ruff 사용 가능
- Windows 측: Python 3.13.14 (Microsoft Store), PowerShell 5.1, Git for Windows(Git Bash), 콘솔 코드페이지 949(ko-KR)
- Claude Code 2.1.319, claude.ai 구독 로그인. `--plugin-dir`(디렉터리/zip), `claude plugin validate|install|uninstall|update|marketplace` 지원
- 훅: 기본 fail-open, `onFailure: "block"`(2.1.295+)로 fail-closed 가능 — 실제 동작은 M3에서 직접 확인
- Python 3.11 실물은 이 PC에 없음 → 3.12/3.13에서만 실측, 3.11 호환은 코드 규칙으로만 보장(미검증 표기)

## 헤드리스 실행 예산 (사용자 승인 2026-11-08)
- 훅 동작 확인: haiku 최대 4회, 회당 `--max-budget-usd 0.5`
- 샘플 E2E: sonnet 3회, 회당 `--max-budget-usd 4`
- 전부 임시 샌드박스에서만, `--setting-sources project,local`로 사용자 전역 설정 격리

## 현재 작업
MVP(M0~M4) 완료, 0.1.2 기준 버전 태그, 실전 재작업 드릴 완료(2026-11-08). 0.1.3은 하네스로만 검증. 다음은 사용자 결정 대기: 0.1.3 실제 세션 확인(재작업 1회), 남은 미검증 항목, Extension 착수 여부, WorkMind 적용 시점. Extension에는 자동 진입하지 않는다.

## 헤드리스 실행 예산 (실전 재작업 드릴, 사용자 승인 2026-11-08)
- 승인 3회만: haiku 권한 프로브 1회($0.3 상한) + sonnet S1·S2 각 1회($4 상한). 사용: $0.0025 + $0.70 + $0.33. 추가 실행은 다시 승인.

## 버전 이력
- 0.1.0 (releases/vmodel-0.1.0.json): 최초 고정 릴리스. E2E-1에서 사용.
- 0.1.1 (releases/vmodel-0.1.1.json): 스킬/에이전트가 프로젝트 밖 플러그인 파일을 Read하지 않도록 `vmodel guide <topic>` 추가. E2E-2에서 사용.
- 0.1.2 (releases/vmodel-0.1.2.json, 태그 `v0.1.2` → `bbd6a3d`): 단일 명령 규칙(스킬·에이전트), verifier 포기 금지, 설치 시 validator CLI allow 규칙. E2E-3에서 G1~G5 완주, 실전 재작업 드릴(TEST_RESULTS §8)의 기준 버전.
- 0.1.3 (releases/vmodel-0.1.3.json): 드릴에서 찾은 F1~F4 수정 — 결함 `fixed`는 수정과 함께, 원장 파생 결함 추적(`failing_tests`/`unlinked_failing_tests`/`verified_by`), status에 실패 체크 표시, verifier 원인 대조 체크리스트(D28~D30). 하네스 103/103. **현재 버전, 실제 세션 미검증.**
