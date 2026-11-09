---
name: start
description: Start or continue VModel DevKit V-Model development (requirements -> architecture -> design & test specs -> implementation -> unit verification -> integration verification, each gated by an independent validator). Use when the user asks to develop or implement a feature, substantively change existing behaviour, fix a bug, change the architecture or do a large refactor in a project that has a .vmodel/ directory (e.g. "이 기능을 개발해줘", "버그 고쳐줘", "add a feature"). Do not use for explaining code, Q&A, searching, docs unrelated to development or read-only analysis.
argument-hint: <development request>
---

# VModel workflow — orchestrator

Development request: $ARGUMENTS

Validator CLI (always call it exactly like this, through Bash): `"${CLAUDE_PLUGIN_ROOT}/bin/vmodel"` — below written as `VM`.
Artifact formats with examples: run `VM guide artifacts` once before writing any artifact. Role guides: `VM guide requirements|architecture|design|implementation` (plugin files live outside the project, so print them through the CLI instead of reading them).

## Ground rules
- Only the validator decides gates. Never say a gate passed unless `VM gate` printed PASSED in this session.
- Never edit `.vmodel/state`, `.vmodel/evidence`, `.vmodel/config.json`, `.vmodel/devkit.lock.json` or plugin files; never try to get around the guard hook. Never write `reviews/*.json` yourself. Write artifacts with the Write/Edit tools (shell writes into `.vmodel/` are blocked).
- Keep all code inside the configured source/test paths (`.vmodel/config.json`); Python files elsewhere, symlinks, and pytest hooks that touch results (e.g. `pytest_sessionfinish`, `exitstatus`, junit) fail G4.
- Never weaken, skip or delete tests to get a PASS.
- Subagents: only `vmodel:verifier` (reviews) and `vmodel:test-designer` (test specs) are used; at most 2 at a time. Pass them the absolute project root, the work item id, the gate, the target hash and the VM path (the absolute path above).
- Shell discipline: run every `VM` call as its own Bash command, exactly `"<absolute VM path>" <subcommand> ...`, from the project root. No `VM=` variables, no `$(...)`, no `;`/`&&`/`||` chains, no loops, no `cd`. Such commands need extra permission approval and are denied in non-interactive runs; if one is denied, re-issue the parts as separate plain commands.
- Answer the user in their language. Keep progress notes short.

## 0. Work item
1. `VM status`. If it reports no `.vmodel/config.json`, stop: tell the user to run `VM install --project <root>` themselves (it changes project settings).
2. If an unfinished work item clearly matches this request, continue it from its first non-PASSED gate. Otherwise `VM new-wi --title "<short title>" --request "<the user's request, verbatim>"` and use the printed id (WI below).
3. Ids are project-unique: get them with `VM next-id REQ --count 3` (also ARCH, IF, DESIGN, TEST, DEFECT, CR, ISSUE, ASM).

## Gate loop (used by every phase)
After writing a phase's artifacts:
1. `VM lint WI` — fix schema/trace problems first (lint is not a gate decision).
2. `VM hash WI Gn` -> target hash. Launch the verifier: Agent tool, subagent_type `vmodel:verifier`, prompt: "Review gate Gn of WI in project <root>. target_hash=<hash>. VM=<absolute VM path>. Write .vmodel/work-items/WI/reviews/Gn.json and submit it with review-submit." (Gn = G1..G4; G5 has no review.)
   Wait until the verifier has finished and reported (if it was started in the background, wait for its completion
   notification) before the next step; the review file must exist first. (G5 and G6 have no review: the validator runs
   the tests itself.)
3. `VM gate WI Gn` and act on the result:
   - PASSED -> next phase.
   - REVIEW_REQUIRED by `vmodel:verifier` -> the review is missing or targets an older hash: re-run step 2 for the current hash.
   - REVIEW_REQUIRED by `user` -> ask the user (one batched question), record the answer (`decided_by: "user"`, `user_answer`), re-run the loop. If you cannot ask (non-interactive run), stop and report what needs the user's decision.
   - FAILED -> follow "Rework" below, then repeat the loop.
   - BLOCKED -> stop and report the reasons to the user. Do not try to work around it.

## P1 Requirements -> G1  (role guide: `VM guide requirements`)
Read the relevant code first. Write `requirements.json`: atomic, testable requirements (functional / non-functional / constraint), acceptance criteria `AC-<req number>-<n>` for every functional requirement, a real conflict analysis, open issues and assumptions. Ask the user once, batched, only about critical ambiguities (security risk, data loss, essential conflicts, user-visible behaviour with no safe default); record everything else as an assumption. Then the gate loop for G1.

## P2 Architecture -> G2  (role guide: `VM guide architecture`)
Write `architecture.json`: components with responsibilities and the requirements they realise, interfaces (provider/consumers/signature with the `def`/`class` name the provider implements), data flows, how each non-functional/constraint requirement is addressed, trade-offs, and an integration test strategy covering every interface. Interfaces are verified in G6 by real integration tests; a single component with no interface is G6 N/A only after the verifier confirms it in the G2 and G3 reviews (it lists every external data flow endpoint). Never delete an interface to avoid G6: removing one needs a change request with `removed_ids`. Gate loop for G2.

## P3 Detailed design + test planning -> G3  (role guide: `VM guide design`)
1. Write `design.json`: one unit per function/class/method to implement, with module path (relative to the project root, inside the configured source paths), name, signature, contract (pre/postconditions), explicit error list, boundary conditions.
2. Launch `vmodel:test-designer` (prompt: project root, WI, VM path) to write `tests.json` independently: unit tests per design unit (normal + abnormal for declared errors + boundary), integration tests per interface, system tests per acceptance criterion. Wait for it to finish.
3. Gate loop for G3.

## P4 Implementation -> G4  (role guide: `VM guide implementation`)
Implement exactly the designed units. Write unit tests for every unit-level TEST spec and integration tests for every integration-level TEST spec; each test function name contains the id token, e.g. `def test_TEST_004_counts_words():`. Integration tests go in the integration folder the user configured (`integration_test` in `.vmodel/config.json`, normally `tests/integration/`; unit tests stay out of it) and must really drive the interface: call the consumer (or provider) API so the real provider runs — no placeholders, no import-only tests, no mocking of the provider under test. If an interface can only be exercised through a subprocess, IPC or an HTTP API, keep the inherited `PYTHONPATH` when starting Python (no `-I`/`-E`): the verifier then declares that runtime path at G4 and G6 must see the provider run in its runtime trace. `VM wiring WI` shows how the validator classifies each integration test. You may run the tests yourself while developing (that is not evidence). Then gate loop for G4 (the verifier reviews code, test code and every interface).

## P5 Unit verification -> G5
`VM gate WI G5` — the validator runs the unit tests itself and records evidence. FAILED -> Rework.

## P6 Integration verification -> G6
`VM gate WI G6` — the validator runs the `integration_test` command itself, maps every integration TEST id and checks that each interface is covered by a passed test that reaches its provider (static call path, or the runtime trace for a declared runtime path). FAILED -> Rework (root cause may be P2 interface contract, P3 integration spec, P4 code/test code, P6 integration environment). BLOCKED `misconfigured` -> the project has no usable `integration_test`: stop and ask the user to add it (`VM configure-tests --integration <path>` in a terminal); never run the unit tests instead. BLOCKED `applicability_unconfirmed` -> no interface and no integration spec, but N/A is not confirmed: the verifier records `integration_applicability` in the G2 and G3 reviews (or the removal of interfaces needs `removed_ids`). BLOCKED `integration_evidence_insufficient` -> a declared runtime path left no runtime proof: fix the test or report. N/A (PASSED with applicability not_applicable) is not an integration test pass and never verifies a defect fix.

## Rework (any FAILED gate)
1. Read the failure: `VM status WI` lists, under the failed gate, its failed checks, failing test cases and failing TEST ids.
2. Add a DEFECT to `defects.json` (`VM next-id DEFECT`): `gate`, `found_in_records: ["<failed record id>"]`, `description`, `failed_checks`, `root_cause_phase` (P1-P4 where the error was introduced, P6 for the integration environment), `root_cause` (it must explain every failing case, not only the first), `fix_scope`, `related` (the REQ/DESIGN ids and every failing TEST id `VM status` lists), `status: "open"`. The validator refuses to re-evaluate without it.
3. Fix at the root-cause phase and, in the same step, set the defect `status` to `fixed` — before the re-review. `defects.json` and `change-requests.json` are G4/G5 inputs: editing them after a gate passed makes G4/G5 STALE again and costs another review, so leave them alone once G5 passed. `fixed` is only your claim (shown as FIX_APPLIED); the validator proves the closure: `VM status` shows the defect CLOSED, "verified by <record>", after the gate passes. Other states are not closed: REVERIFY_REQUIRED (it passed once, but the gate is not PASSED now, e.g. STALE: re-run it), VERIFICATION_FAILED (the re-verification failed: cite that record and rework), UNKNOWN (ledger or evidence integrity failed: stop and report), OUT_OF_SCOPE (a G6 defect whose interfaces were removed by a justified change request: not verified, report it as such).
4. If a test file must change, add `test_changes` to the defect: `file`, `since_record` (the baseline record id the validator names), `reason`, `requirements`, `impact`.
5. `VM lint WI` (it also flags failing TEST ids the defect does not link), then re-run the gate loop from the root-cause phase forward; changing upstream artifacts makes downstream gates STALE, and G4 needs a fresh review before G5. If the validator BLOCKS after 3 identical failures, stop and report.

## Finish
`VM status WI` and `VM report WI`. Tell the user: final status (normally `PARTIALLY_VERIFIED`), whether G6 ran integration tests or is N/A (say N/A as N/A, never as "integration tests passed"), that G7 is not implemented in this DevKit version so this is not a full V-Model completion, the report path, the evidence paths from G5 and G6, defects found, and any assumptions they should check. Report every ERROR and WARNING line of the defect trace check (`VM status` / the `## Defect trace check` section of the report) to the user as it is — evidence errors and unlinked or UNKNOWN failing TESTs must not be dropped, even when the work item is PARTIALLY_VERIFIED.
