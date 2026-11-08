# WI-001 — 문장 통계 기능

- Status: **PARTIALLY_VERIFIED** (profile STANDARD)
- Generated: 2026-11-08T09:05:21+00:00 by vmodel 0.1.2 (release, core `a0555e328413`)
- Validator integrity: OK; ledger: OK

> MVP scope: only G1-G5 are implemented. G6 (integration) and G7 (system) are extension gates, so a work item can reach PARTIALLY_VERIFIED at most. This is NOT a full V-Model completion.

## Gates

| Gate | Name | Status | Record | Evaluated | Manifest |
|---|---|---|---|---|---|
| G1 | Requirements | PASSED | R00013 | 2026-11-08T09:05:20.628Z | `56680e6a2795` |
| G2 | Architecture | PASSED | R00014 | 2026-11-08T09:05:20.695Z | `c7ede5df7f66` |
| G3 | Detailed Design & Test Planning | PASSED | R00015 | 2026-11-08T09:05:20.712Z | `f96175b0c49a` |
| G4 | Implementation | PASSED | R00016 | 2026-11-08T09:05:20.823Z | `a1aa5a502f11` |
| G5 | Unit Verification | PASSED | R00017 | 2026-11-08T09:05:21.460Z | `a1aa5a502f11` |
| G6 | Integration Verification | NOT_IMPLEMENTED | - | - | `-` |
| G7 | System Verification | NOT_IMPLEMENTED | - | - | `-` |

Next action: G1-G5 verified. G6+ are extension gates (not implemented); report PARTIALLY_VERIFIED.

## Checks (latest evaluation per gate)

### G1 — PASSED (R00013)

Mechanical / execution checks (decided by the validator):

- `G1.SCHEMA` **pass** — workitem.json, requirements.json valid
- `G1.IDS` **pass** — 14 ids unique
- `G1.ACCEPTANCE` **pass** — 3 functional requirements have acceptance criteria
- `G1.CONFLICTS` **pass** — 1 conflict(s), all resolved
- `G1.OPEN_ISSUES` **pass** — no open critical issues
- `G1.CHANGE_CONTROL` **pass** — no change since R00005
- `G1.AMBIGUITY` **pass** — no vague wording detected

AI review (semantic, not machine-verified):

- `G1.REVIEW` **pass** — approved by vmodel:verifier (AI review, not machine-verified)

### G2 — PASSED (R00014)

Mechanical / execution checks (decided by the validator):

- `G2.SCHEMA` **pass** — architecture.json valid
- `G2.IDS` **pass** — 1 ids unique
- `G2.REQ_MAPPING` **pass** — all functional requirements mapped
- `G2.INTERFACES` **pass** — 0 interface(s) consistent
- `G2.NFR` **pass** — 1 non-functional/constraint requirement(s) addressed
- `G2.INTEGRATION_STRATEGY` **pass** — integration test strategy covers all interfaces
- `G2.TRADEOFFS` **pass** — 2 trade-off(s) recorded

AI review (semantic, not machine-verified):

- `G2.REVIEW` **pass** — approved by vmodel:verifier (AI review, not machine-verified)

### G3 — PASSED (R00015)

Mechanical / execution checks (decided by the validator):

- `G3.SCHEMA` **pass** — design.json, tests.json valid
- `G3.IDS` **pass** — 7 ids unique
- `G3.DESIGN_COVERAGE` **pass** — 1 unit(s) cover all components and requirements
- `G3.CONTRACTS` **pass** — every unit has signature, contract, errors and boundaries
- `G3.UNIT_TESTS` **pass** — 4 unit test spec(s) cover all units
- `G3.INTEGRATION_SYSTEM_TESTS` **pass** — integration and system test specs cover interfaces and acceptance criteria
- `G3.TRACE` **pass** — requirements, design and tests are linked
- `G3.NO_SILENT_REMOVAL` **pass** — nothing removed

AI review (semantic, not machine-verified):

- `G3.REVIEW` **pass** — approved by vmodel:verifier (AI review, not machine-verified)

### G4 — PASSED (R00016)

Mechanical / execution checks (decided by the validator):

- `G4.FILES` **pass** — 2 source / 2 test file(s)
- `G4.UNEXPECTED_CODE` **pass** — no Python code outside the configured paths, no symlinks
- `G4.SYNTAX` **pass** — 4 file(s) parsed by the validator (Python AST)
- `G4.LINT` **pass** — ruff passed (exit 0)
- `G4.DESIGN_CONFORMANCE` **pass** — 1 design unit(s) implemented
- `G4.TEST_CODE` **pass** — 4 unit test spec(s) implemented
- `G4.TEST_INTEGRITY` **pass** — no result-reporting hooks in test or support code
- `G4.REQ_IMPLEMENTED` **pass** — every functional requirement reaches implemented code

AI review (semantic, not machine-verified):

- `G4.REVIEW` **pass** — approved by vmodel:verifier (AI review, not machine-verified)

Evidence:

- `.vmodel/evidence/WI-001/G4/20261108T090520753161Z-lint-dcb8a0/record.json` (`a2426e626f81`)

### G5 — PASSED (R00017)

Mechanical / execution checks (decided by the validator):

- `G5.PREREQ` **pass** — G4 PASSED for the current manifest hash
- `G5.EXECUTION` **pass** — exit code 0, junit produced
- `G5.RESULTS` **pass** — 5 passed, 0 skipped of 5
- `G5.TEST_MAPPING` **pass** — 4 unit test spec(s) passed
- `G5.REQ_COVERAGE` **pass** — every functional requirement has a passed test
- `G5.NO_WEAKENING` **pass** — no test change since R00012
- `G5.INPUTS_UNCHANGED` **pass** — inputs unchanged during the run

Evidence:

- `.vmodel/evidence/WI-001/G5/20261108T090520841119Z-unit-b08a3a/record.json` (`9a8e3cd811cc`)

## Traceability

| REQ | Type | ARCH | DESIGN | Tests (level:result) |
|---|---|---|---|---|
| REQ-001 문장 수와 문장당 평균 단어 수 계산 | functional | ARCH-001 | DESIGN-001 | TEST-001 (unit:passed), TEST-002 (unit:passed), TEST-003 (unit:passed), TEST-004 (unit:passed), TEST-005 (system:not run) |
| REQ-002 빈 텍스트 처리 | functional | ARCH-001 | DESIGN-001 | TEST-001 (unit:passed), TEST-002 (unit:passed), TEST-003 (unit:passed), TEST-004 (unit:passed), TEST-006 (system:not run) |
| REQ-003 문자열이 아닌 입력 거부 | functional | ARCH-001 | DESIGN-001 | TEST-001 (unit:passed), TEST-002 (unit:passed), TEST-003 (unit:passed), TEST-004 (unit:passed), TEST-006 (system:not run) |
| REQ-004 표준 라이브러리만 사용 | constraint | ARCH-001 | DESIGN-001 | TEST-001 (unit:passed), TEST-002 (unit:passed), TEST-003 (unit:passed), TEST-004 (unit:passed) |

## Defects

None recorded.

## Change requests

None recorded.

## Limitations

- AI review checks record that the vmodel:verifier approved the exact input hash; the semantic correctness of requirements and designs is not machine-verified.
- Hooks and permission rules are best-effort protection, not OS-level isolation; the final trust boundary is a re-verification on CI or by a separate user (`vmodel audit`, `vmodel verify`).
- G6/G7, LITE and STRICT profiles are not implemented in this DevKit version.
