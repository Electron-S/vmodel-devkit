# v0.1.5 작업 항목: 업그레이드 시 권한 규칙 갱신 (V-Model 절차 기록)

작성 2026-11-09. 근거: 사용자 지시(2026-11-09, "업그레이드 안정성 보완 및 G6 개발 준비"), HANDOFF 미완료 4번, TEST_RESULTS §11.7 마지막 항목.
브랜치 `v0.1.5-dev`(기준 `main` = 태그 `v0.1.4` = `991af67`). main 병합·태그·푸시는 하지 않는다.

## 0. 절차

v0.1.4와 같다(`docs/v0.1.4/WORKITEM.md` §0). 절차는 G1~G5를 따르고 판정은 독립 하네스가 한다(SPEC §5.8, DevKit 코어를 DevKit Gate로 승인하지 않는다).

| 단계 | 이 작업에서 하는 일 | 산출물 |
|---|---|---|
| G1 | 요구사항·수용 기준 | §2 |
| G2 | 변경 영향 분석 | §3 |
| G3 | 상세 설계, 구현 전 테스트 명세 | §4, §5 |
| G4 | 최소 수정, ruff, 독립 검토(별도 컨텍스트, 읽기 전용) | 커밋, §7 |
| G5 | 불변 릴리스 0.1.4 대상 RED → 수정본 GREEN → 전체 회귀 | `test-results/v0.1.5/*.log`, §6 |

RED 대상은 불변 릴리스 `dist/vmodel-0.1.4`(core `5dd1d010…`, `releases/vmodel-0.1.4.json`과 43개 파일 일치)이다. 업그레이드 "이전 릴리스" 역할은 `dist/vmodel-0.1.3`이 맡는다(RED: 0.1.3 → 0.1.4 코드, GREEN: 0.1.3 → 0.1.5 코드). 실제 사용자 경로인 0.1.4 → 0.1.5는 GREEN 전용 인수 테스트와 릴리스 사본 재현 스크립트로 따로 확인한다.

## 1. 문제와 재현

`vmodel install`은 `.claude/settings.json`에 릴리스 절대경로가 든 규칙을 쓴다.
- deny `Edit(//<plugin_root>/**)` (Validator Core 보호, D06의 두 번째 보호층)
- allow `Bash(<plugin_root>/bin/vmodel *)`, `Bash("<plugin_root>/bin/vmodel" *)` (validator CLI를 묻지 않고 실행, 0.1.2)

설치 기록 `.vmodel/install-record.json`에는 `plugin_root`와 설치가 실제로 추가한 규칙(`added_deny`, `added_allow`)이 남는다.

재현(`test-results/v0.1.5/upgrade_repro.py`, 실제 릴리스 사본 `dist/vmodel-0.1.3` → `dist/vmodel-0.1.4`, 모델 호출 없음, 결과 `repro-0.1.3-to-0.1.4.json`)
- 절차 A(SPEC §11: 새 릴리스로 `lock --accept-current`): lock은 0.1.4를 가리키지만 settings.json은 바이트 그대로다. deny에 `Edit(//…/dist/vmodel-0.1.3/**)`, allow에 0.1.3 CLI 경로 2개가 남고 0.1.4 경로 규칙은 0개다. install-record의 `plugin_root`도 0.1.3이다. 새 Core는 guard(첫 번째 보호층)만 막는다(guard 직접 호출 deny). 세션이 안내받는 CLI(`"<0.1.4>/bin/vmodel"`)에 맞는 allow 규칙이 없어 대화형 세션에서는 Validator 호출마다 권한 확인이 뜬다.
- 절차 B(README의 0.1.1 → 0.1.2 절차: 옛 `uninstall` → 새 `install` → 재고정): 결과 경로는 맞지만 `uninstall`과 `install` 사이에 DevKit deny 규칙이 하나도 없다(`.vmodel/state/**` 등 보호 공백).
- 절차 C(새 릴리스로 `install`): "already installed …; run 'vmodel uninstall' first"로 거부하며 공백이 생기는 절차 B로 안내한다.
- 원인: SPEC §11 업그레이드 절차에 설정 갱신 단계가 없고, 재고정(`repin_lock`)은 lock과 원장만 쓴다. 덧붙여 `repin_lock`은 lock 파일을 먼저 쓰고 원장에 기록하므로, 원장 기록이 실패하면 lock만 바뀐 채 남는다(코드 확인, §5 U8에서 재현).

## 2. 요구사항 (G1)

- REQ-U1 업그레이드(새 릴리스의 `vmodel lock --accept-current`, 사용자 TTY)가 끝나면 DevKit이 관리하는 권한 규칙은 새 릴리스 경로를 가리킨다.
  - AC-U1a deny에 `Edit(//<새 root>/**)`, allow에 새 CLI 규칙 2개가 있고, DevKit이 이전 릴리스용으로 추가한 규칙(이전 root의 deny 1개·allow 2개)은 없다.
  - AC-U1b install-record의 `plugin_root`·`validator_version`이 새 릴리스이고, `added_deny`·`added_allow`가 지금 settings에 있는 DevKit 규칙과 같다.
- REQ-U2 사용자 정의 설정은 보존한다. 설치 기록에 없는 규칙(이전 릴리스 경로를 언급하는 사용자 규칙 포함), 순서, hooks·env 등 다른 키는 그대로다.
  - AC-U2a 업그레이드 전후 사용자 규칙 목록과 다른 키가 같다.
  - AC-U2b 업그레이드 뒤 `uninstall`이 설치 전 사용자 settings를 정확히 복원한다(새 코드·이전 코드 어느 쪽 uninstall로도).
- REQ-U3 DevKit 규칙은 설치 기록(`added_deny`, `added_allow`)으로만 식별한다. 경로 패턴으로 추정하지 않는다. 설치 전부터 있던 같은 문자열 규칙은 사용자 소유로 남는다.
  - AC-U3a 설치 전에 사용자가 넣어 둔 DevKit과 같은 문자열 규칙은 업그레이드·제거 후에도 남는다.
- REQ-U4 이전 규칙을 지울 때 보호 공백이 없다. 새 규칙을 먼저 더하고(이전+새 상위 집합), 재고정이 성공한 뒤에만 이전 규칙을 지운다. 파일은 매번 원자적으로 바꾼다.
  - AC-U4a 재고정 단계가 실패하면 settings·install-record·lock이 업그레이드 전 바이트로 돌아가고, 원장에 기록이 늘지 않는다.
  - AC-U4b 이전·새 규칙이 함께 있는 상위 집합 상태(중단된 업그레이드)에서 다시 실행하면 이전 DevKit 규칙만 지워지고 사용자 규칙은 남는다.
- REQ-U5 설치·업그레이드·제거는 멱등이다.
  - AC-U5a 같은 릴리스로 업그레이드를 두 번 하면 두 번째는 settings·install-record를 바꾸지 않는다(바이트 동일, 백업도 만들지 않는다).
  - AC-U5b 같은 프로젝트에 `install`을 다시 하면 거부하고 아무것도 바꾸지 않는다. 다른 릴리스가 설치한 프로젝트면 업그레이드 명령을 안내한다(uninstall을 권하지 않는다).
  - AC-U5c `uninstall` 두 번째 실행은 "nothing to do"이고 아무것도 바꾸지 않는다.
- REQ-U6 업그레이드 실패 시 복구·롤백 수단이 있다.
  - AC-U6a 시작 전 검사(settings·설치 기록의 JSON 형식, Validator 무결성, 서명 키·원장 무결성)가 실패하면 아무 파일도 바꾸지 않는다.
  - AC-U6b 설정을 바꾸는 업그레이드는 업그레이드 전 settings·install-record·lock 사본을 `.vmodel/install/backup/upgrade-<시각>/`에 남기고 출력에 경로를 보인다.
  - AC-U6c 재고정 성공 후 이전 규칙 제거만 실패하면 안전한 상위 집합으로 남기고, 다시 실행하면 마무리된다는 안내와 함께 비 0으로 끝난다(코드 검토로 확인, AC-U4b가 같은 상태의 재실행을 검사).
- REQ-U7 사용자 승인 없이 설정을 바꾸지 않는다. 설정 변경은 사용자 전용 TTY 명령에서만, 바뀔 규칙을 먼저 보여 준 뒤 'yes'를 받아야 일어난다. 에이전트는 guard가 막는다(기존 USER_ONLY 그대로).
  - AC-U7a TTY 없이 실행하면 거부(종료 코드 3)하고 아무것도 바꾸지 않는다.
  - AC-U7b 'yes'가 아니면 아무것도 바꾸지 않는다.
  - AC-U7c 확인 전에 추가·삭제될 규칙과 이전·새 root를 출력한다.
- REQ-U8 Guard 보호 수준을 낮추지 않는다. `hook.py`는 바꾸지 않는다. 업그레이드 뒤 새 Core는 guard와 deny 규칙 양쪽으로 보호된다.
- REQ-U9 Gate 판정·원장 기록 형식·manifest 계산·서명 증거는 바꾸지 않는다. 기존 릴리스 사본·기록·태그는 그대로다.

범위 밖(기록만): 0.1.4 이하로 내리는 다운그레이드는 그 릴리스에 설정 갱신 코드가 없어서 자동화하지 못한다(§4.6 수동 절차). 마켓플레이스로 등록해 Claude Code가 플러그인을 캐시 경로에서 실행하는 경우 규칙이 가리킬 경로는 미검증이다(TEST_RESULTS §6과 같은 미검증 항목).

## 3. 변경 영향 분석 (G2)

| 모듈 | 변경 | 바뀌지 않는 계약 |
|---|---|---|
| `validator/setup_project.py` | 설정 동기화 계획(`plan_settings_sync`)과 업그레이드 트랜잭션(`upgrade_project`) 추가, 이미 설치된 프로젝트의 install 오류 문구 | `install_claude`의 병합 결과, `uninstall`, `repin_lock`의 lock·원장 기록 형식 |
| `validator/cli.py` | `lock --accept-current`가 계획 출력 → TTY 확인 → 트랜잭션. 출력에 `re-pinned core …` 줄 유지 | 다른 명령, 종료 코드 규칙(사용자 거부 3, 설정 오류 2) |
| `validator/__init__.py`, `plugin.json` | 버전 0.1.5 | — |
| `hook.py`, `gates.py`, `ledger.py`, `runner.py`, `status.py`, `integrity.py`, 스키마, `gates.json` | 없음 | 보호 경로·USER_ONLY, Gate 판정, 원장·증거 형식, manifest |
| 문서 | SPEC §11, README 업그레이드 절차, DECISIONS D38, PLAN, TEST_RESULTS §12, HANDOFF | — |

Core 파일(`validator/`)이 바뀌므로 core 해시가 바뀐다. 설치된 프로젝트는 0.1.5로 재고정해야 하고 기존 PASS는 STALE이 된다(지금까지와 같다). 0.1.5의 재고정은 그 과정에서 설정도 옮긴다.

## 4. 상세 설계 (G3)

### 4.1 소유권
DevKit 규칙 = install-record의 `added_deny`·`added_allow`(설치가 그 시점에 없어서 실제로 추가한 문자열). 0.1.0·0.1.1 기록처럼 키가 없으면 빈 목록으로 본다. 업그레이드 뒤에도 같은 의미를 유지한다: 지금 settings에 있고 DevKit이 추가한 규칙만 목록에 남는다.

### 4.2 계획 (`plan_settings_sync`, 읽기 전용)
설치 기록이 없으면 계획 없음(설정을 건드리지 않고 재고정만). 있으면
- 생성 규칙 = 지금 릴리스의 `protected_deny_rules(root)`, `validator_allow_rules()`(설치와 같은 함수)
- 추가 = 생성 규칙 중 settings에 없는 것 (소유권 획득)
- 삭제 = 소유 규칙 중 생성 규칙이 아닌 것 (settings에 있으면 한 번만 지운다. 같은 문자열 사용자 사본이 더 있으면 남는다)
- 소유 유지 = 소유 규칙 중 생성 규칙이고 settings에 있는 것
- settings.json이 깨졌거나 객체가 아니면, `permissions`·`deny`·`allow`가 기대한 형식이 아니면 SetupError(아무것도 바꾸지 않음)
- 계획에는 settings·install-record의 해시를 담는다. 확인을 기다리는 사이 파일이 바뀌면 적용하지 않는다.

### 4.3 트랜잭션 (`upgrade_project`, 사용자 확인 후)
1. 시작 전 검사: Validator 무결성(`check_self`), 원장 읽기(`Ledger.entries()` — 서명 키·서명·체인·head·앵커), 계획 재계산 후 해시 대조. 실패하면 SetupError/LedgerError, 아무것도 쓰지 않는다.
2. 메모리 스냅샷(settings·install-record·lock 바이트, settings가 없었으면 없음)과 디스크 백업 `.vmodel/install/backup/upgrade-<시각>/`(설정 변경이 있을 때만).
3. 1단계(추가): settings = 기존 + 추가 규칙. install-record 소유 목록 = 기존 소유 + 추가, `upgrade_pending`(이전·새 root, 백업 경로). 둘 다 원자적 교체(`write_json`).
4. 2단계(재고정): `repin_lock`(lock 쓰기 + 원장 lock 기록).
5. 1~2단계 중 예외 → 스냅샷으로 settings·install-record·lock 복원(settings가 없었으면 삭제), "rolled back" 오류(종료 코드 2). 원장은 append 전 실패면 그대로다.
6. 3단계(삭제): settings에서 삭제 규칙 제거, install-record 확정(`plugin_root`·`validator_version` 갱신, 소유 목록 확정, `upgrade_pending` 제거, `upgrades` 이력 추가). 여기서 예외가 나면 롤백하지 않는다(재고정은 이미 원장에 기록됨). 상위 집합으로 남은 상태를 알리고 같은 명령을 다시 실행하라고 안내한다(종료 코드 2). 재실행은 기록상 소유 목록으로 같은 계획을 다시 만든다.
7. 바꿀 것이 없으면(같은 릴리스 재고정) settings·install-record에 쓰지 않는다.

설치 기록이 없는 프로젝트(`init`만 한 경우)도 같은 트랜잭션을 지나므로 원장 기록이 실패하면 lock이 복원된다(§1의 lock 선기록 문제 해소).

### 4.4 CLI
`vmodel lock --accept-current [--reason]` (USER ONLY, TTY): 계획을 계산해 출력(이전·새 root, 추가·삭제 규칙, "user rules are not changed") → `_require_tty`의 확인 문구에 설정 갱신을 포함 → 트랜잭션 → `re-pinned core <hash> (validator <ver>)`, 설정 변경 요약, 백업 경로. 메시지는 ASCII 영어(D16).

### 4.5 install 재실행
기록이 있으면 지금처럼 거부한다(종료 코드 2, 변경 없음). 기록의 `plugin_root`가 지금 릴리스와 다르면 "this project was installed by validator <ver> from <root>; to upgrade, run '<이 릴리스>/bin/vmodel lock --accept-current' in a terminal …"로 안내한다.

### 4.6 롤백 절차 (문서)
- 자동: 4.3의 5.
- 중단된 업그레이드: 같은 명령 재실행(멱등).
- 수동 복원: 백업 폴더의 사본. 재고정은 원장에 남으므로 lock을 손으로 되돌리지 않고, 되돌리려면 그 릴리스로 다시 재고정한다.
- 0.1.5 이상 릴리스로 내리기: 그 릴리스의 `lock --accept-current`(같은 트랜잭션).
- 0.1.4 이하로 내리기: 그 릴리스에는 설정 갱신이 없다. Claude 세션을 모두 닫고 `<현재>/bin/vmodel uninstall` → `<이전>/bin/vmodel install` → `<이전>/bin/vmodel lock --accept-current`. uninstall과 install 사이에는 DevKit 규칙이 없으므로 세션이 없을 때만 한다.

## 5. 테스트 명세 (구현 전 작성, `tests/test_upgrade_settings.py`)

공통: `Sandbox(plugin=0.1.3 릴리스)`로 사용자 settings(사용자 allow 2개 — 그중 하나는 0.1.3 경로를 언급, 사용자 deny 1개, hooks, env)가 있는 프로젝트에 설치 → `sb.plugin`을 시험 대상(`helpers.PLUGIN`)으로 바꾸고 pty로 재고정. POSIX 전용(pty). 0.1.3 릴리스를 찾지 못하면 skip.

| TEST | 클래스(기대) | 메서드 | AC |
|---|---|---|---|
| U-1 | `UpgradeSettingsRed` | `test_rules_follow_the_new_release_after_repin` | U1a |
| U-2 | `UpgradeSettingsRed` | `test_install_record_tracks_the_new_release` | U1b, U3 |
| U-3 | `UpgradeSettingsRed` | `test_user_rule_equal_to_a_devkit_rule_stays_user_owned` | U3a (같은 문자열 사용자 규칙은 업그레이드·제거 후에도 남고, DevKit 새 규칙은 들어간다) |
| U-4 | `UpgradeSettingsRed` | `test_failed_repin_restores_settings_record_and_lock` | U4a (원장 잠금 파일을 잡아 원장 기록을 실패시킴, 약 30초) |
| U-5 | `UpgradeSettingsRed` | `test_unwritable_settings_aborts_without_repinning` | U6a (`.claude/` 쓰기 금지 → 재고정도 하지 않음, lock·원장 그대로) |
| U-6 | `UpgradeSettingsRed` | `test_interrupted_upgrade_superset_is_completed_on_rerun` | U4b (이전+새 규칙 상위 집합과 둘 다 소유한 기록에서 재실행) |
| U-7 | `UpgradeSettingsRed` | `test_plan_is_shown_before_confirmation_and_backup_is_kept` | U7c, U6b |
| U-8 | `UpgradeSettingsRed` | `test_install_over_another_release_points_to_the_upgrade` | U5b 안내 |
| U-9 | `UpgradeSettingsRed` | `test_invalid_settings_aborts_before_repin` | U6a (깨진 settings → lock·원장 그대로) |
| U-10 | `UpgradeSettingsChar` | `test_user_settings_survive_upgrade_and_uninstall` | U2a, U2b (사용자 규칙·다른 키 보존, 업그레이드 뒤 uninstall이 원래 사용자 settings 복원) |
| U-11 | `UpgradeSettingsChar` | `test_repin_without_tty_or_without_yes_changes_nothing` | U7a, U7b |
| U-12 | `UpgradeSettingsChar` | `test_second_install_and_second_uninstall_change_nothing` | U5b, U5c |
| U-13 | `UpgradeSettingsChar` | `test_repin_of_init_only_project_leaves_settings_alone` | 설치 기록 없는 프로젝트는 settings를 만들지 않는다 |
| U-14 | `UpgradeSettingsInvariant` | `test_guard_still_blocks_agents_and_protects_the_running_core` | U7(에이전트의 `lock --accept-current`·`install`·`uninstall` deny), U8(실행 중 Core 쓰기 deny), hook.py 무변경 |
| U-15 | `UpgradeSettingsAccept` | `test_second_upgrade_is_a_no_op_for_settings` | U5a |
| U-16 | `UpgradeSettingsAccept` | `test_upgrade_from_014_release_then_014_uninstall` | 실제 경로 0.1.4 → 0.1.5, 0.1.4 CLI의 uninstall이 원래 settings 복원(교차 버전) |
| U-17 | `UpgradeSettingsAccept` | `test_plan_and_transaction_in_process` | Windows에서도 도는 계획·트랜잭션 직접 호출(TTY 없음): 경로 갱신, 사용자 규칙 보존, 재실행 무변경 |
| U-18 | `UpgradeSettingsAccept` | `test_gates_still_pass_after_upgrade` | U9: 업그레이드 뒤 이전 PASS STALE, 재검증 PASS, audit OK |

U-10~U-13은 0.1.4에서도 통과해야 하는 특성 테스트다(지금 동작 중 지켜야 할 것). U-15는 0.1.4에서 "변경 없음"이 공허하게 참이므로 GREEN 전용으로 둔다. U-4는 0.1.4에서 lock만 바뀌어 실패한다(§1의 lock 선기록).

## 6. 결과
(구현 후 기록)

## 7. 독립 검토
(구현 후 기록)
