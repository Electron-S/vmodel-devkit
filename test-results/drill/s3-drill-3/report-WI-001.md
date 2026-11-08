# WI-001 — 점수 백분위수 계산(nearest-rank)

- Status: **PARTIALLY_VERIFIED** (profile STANDARD)
- Generated: 2026-11-08T12:58:52+00:00 by vmodel 0.1.3 (release, core `0208c7988516`)
- Validator integrity: OK; ledger: OK

> MVP scope: only G1-G5 are implemented. G6 (integration) and G7 (system) are extension gates, so a work item can reach PARTIALLY_VERIFIED at most. This is NOT a full V-Model completion.

## Gates

| Gate | Name | Status | Record | Evaluated | Manifest |
|---|---|---|---|---|---|
| G1 | Requirements | PASSED | R00014 | 2026-11-08T12:58:44.225Z | `87038dcf6980` |
| G2 | Architecture | PASSED | R00015 | 2026-11-08T12:58:44.248Z | `b880be5a93a0` |
| G3 | Detailed Design & Test Planning | PASSED | R00016 | 2026-11-08T12:58:44.264Z | `44df8a43a890` |
| G4 | Implementation | PASSED | R00017 | 2026-11-08T12:58:44.328Z | `49b4ad51a85c` |
| G5 | Unit Verification | PASSED | R00018 | 2026-11-08T12:58:45.150Z | `49b4ad51a85c` |
| G6 | Integration Verification | NOT_IMPLEMENTED | - | - | `-` |
| G7 | System Verification | NOT_IMPLEMENTED | - | - | `-` |

Next action: G1-G5 verified. G6+ are extension gates (not implemented); report PARTIALLY_VERIFIED.

## Checks (latest evaluation per gate)

### G1 — PASSED (R00014)

Mechanical / execution checks (decided by the validator):

- `G1.SCHEMA` **pass** — workitem.json, requirements.json valid
- `G1.IDS` **pass** — 12 ids unique
- `G1.ACCEPTANCE` **pass** — 2 functional requirements have acceptance criteria
- `G1.CONFLICTS` **pass** — 0 conflict(s), all resolved
- `G1.OPEN_ISSUES` **pass** — no open critical issues
- `G1.CHANGE_CONTROL` **pass** — no change since R00003
- `G1.AMBIGUITY` **pass** — no vague wording detected

AI review (semantic, not machine-verified):

- `G1.REVIEW` **pass** — approved by vmodel:verifier (AI review, not machine-verified)

### G2 — PASSED (R00015)

Mechanical / execution checks (decided by the validator):

- `G2.SCHEMA` **pass** — architecture.json valid
- `G2.IDS` **pass** — 1 ids unique
- `G2.REQ_MAPPING` **pass** — all functional requirements mapped
- `G2.INTERFACES` **pass** — 0 interface(s) consistent
- `G2.NFR` **pass** — 1 non-functional/constraint requirement(s) addressed
- `G2.INTEGRATION_STRATEGY` **pass** — integration test strategy covers all interfaces
- `G2.TRADEOFFS` **pass** — 1 trade-off(s) recorded

AI review (semantic, not machine-verified):

- `G2.REVIEW` **pass** — approved by vmodel:verifier (AI review, not machine-verified)

### G3 — PASSED (R00016)

Mechanical / execution checks (decided by the validator):

- `G3.SCHEMA` **pass** — design.json, tests.json valid
- `G3.IDS` **pass** — 17 ids unique
- `G3.DESIGN_COVERAGE` **pass** — 1 unit(s) cover all components and requirements
- `G3.CONTRACTS` **pass** — every unit has signature, contract, errors and boundaries
- `G3.UNIT_TESTS` **pass** — 12 unit test spec(s) cover all units
- `G3.INTEGRATION_SYSTEM_TESTS` **pass** — integration and system test specs cover interfaces and acceptance criteria
- `G3.TRACE` **pass** — requirements, design and tests are linked
- `G3.NO_SILENT_REMOVAL` **pass** — nothing removed

AI review (semantic, not machine-verified):

- `G3.REVIEW` **pass** — approved by vmodel:verifier (AI review, not machine-verified)

### G4 — PASSED (R00017)

Mechanical / execution checks (decided by the validator):

- `G4.FILES` **pass** — 2 source / 2 test file(s)
- `G4.UNEXPECTED_CODE` **pass** — no Python code outside the configured paths, no symlinks
- `G4.SYNTAX` **pass** — 4 file(s) parsed by the validator (Python AST)
- `G4.LINT` **pass** — ruff passed (exit 0)
- `G4.DESIGN_CONFORMANCE` **pass** — 1 design unit(s) implemented
- `G4.TEST_CODE` **pass** — 12 unit test spec(s) implemented
- `G4.TEST_INTEGRITY` **pass** — no result-reporting hooks in test or support code
- `G4.REQ_IMPLEMENTED` **pass** — every functional requirement reaches implemented code

AI review (semantic, not machine-verified):

- `G4.REVIEW` **pass** — approved by vmodel:verifier (AI review, not machine-verified)

Evidence:

- `.vmodel/evidence/WI-001/G4/20261108T125844316584Z-lint-485473/record.json` (`c9b9359aa728`)

### G5 — PASSED (R00018)

Mechanical / execution checks (decided by the validator):

- `G5.PREREQ` **pass** — G4 PASSED for the current manifest hash
- `G5.EXECUTION` **pass** — exit code 0, junit produced
- `G5.RESULTS` **pass** — 18 passed, 0 skipped of 18
- `G5.TEST_MAPPING` **pass** — 12 unit test spec(s) passed
- `G5.REQ_COVERAGE` **pass** — every functional requirement has a passed test
- `G5.NO_WEAKENING` **pass** — no test change since R00013
- `G5.INPUTS_UNCHANGED` **pass** — inputs unchanged during the run

Evidence:

- `.vmodel/evidence/WI-001/G5/20261108T125844356280Z-unit-4ad0f9/record.json` (`bbda1c94e5da`)

## Traceability

| REQ | Type | ARCH | DESIGN | Tests (level:result) |
|---|---|---|---|---|
| REQ-001 nearest-rank 백분위수 계산 | functional | ARCH-001 | DESIGN-001 | TEST-001 (unit:passed), TEST-002 (unit:passed), TEST-003 (unit:passed), TEST-004 (unit:passed), TEST-005 (unit:passed), TEST-006 (unit:passed), TEST-007 (unit:passed), TEST-008 (unit:passed), TEST-009 (unit:passed), TEST-010 (unit:passed), TEST-011 (unit:passed), TEST-012 (unit:passed), TEST-013 (system:not run), TEST-014 (system:not run) |
| REQ-002 입력 검증 | functional | ARCH-001 | DESIGN-001 | TEST-001 (unit:passed), TEST-002 (unit:passed), TEST-003 (unit:passed), TEST-004 (unit:passed), TEST-005 (unit:passed), TEST-006 (unit:passed), TEST-007 (unit:passed), TEST-008 (unit:passed), TEST-009 (unit:passed), TEST-010 (unit:passed), TEST-011 (unit:passed), TEST-012 (unit:passed), TEST-015 (system:not run) |
| REQ-003 입력 목록 불변 | constraint | ARCH-001 | DESIGN-001 | TEST-001 (unit:passed), TEST-002 (unit:passed), TEST-003 (unit:passed), TEST-004 (unit:passed), TEST-005 (unit:passed), TEST-006 (unit:passed), TEST-007 (unit:passed), TEST-008 (unit:passed), TEST-009 (unit:passed), TEST-010 (unit:passed), TEST-011 (unit:passed), TEST-012 (unit:passed), TEST-016 (system:not run) |

## Defects

- DEFECT-001 [fixed — verified by R00013] G5 percentile()가 nearest-rank 순위를 올림이 아닌 내림(부동소수점 나눗셈 후 int())으로 계산해 TEST-001/002/010/011/012가 실패한다. (root cause P4: src/scorestats/percentile.py가 DESIGN-001(순위 r = ceil(p*N/100), 정수 연산 -(-p*N // 100), 인덱스 r-1)과 달리 index = min(int(p*count/100), count-1)로 구현했다. int()는 내림이고 인덱스에서 1을 빼지 않아 한 칸 뒤 값을 고르며, 부동소수점 나눗셈도 사용한다)
  - failing tests in R00010 (from the signed ledger): TEST-001, TEST-002, TEST-010, TEST-011, TEST-012

## Change requests

None recorded.

## Limitations

- AI review checks record that the vmodel:verifier approved the exact input hash; the semantic correctness of requirements and designs is not machine-verified.
- Hooks and permission rules are best-effort protection, not OS-level isolation; the final trust boundary is a re-verification on CI or by a separate user (`vmodel audit`, `vmodel verify`).
- G6/G7, LITE and STRICT profiles are not implemented in this DevKit version.
