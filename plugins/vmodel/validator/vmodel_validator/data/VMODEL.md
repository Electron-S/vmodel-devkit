# VModel DevKit — project instructions

This project uses the VModel DevKit (V-Model development workflow with an independent quality gate validator).

## When the workflow applies
- Use `/vmodel:start <request>` for: new features, substantive changes to existing behaviour, bug fixes, architecture changes, large refactors.
- Do NOT use it for: explaining code, simple Q&A, searching, documentation unrelated to development, read-only analysis.
- If it is unclear whether a request needs the workflow, say so and suggest `/vmodel:start`.

## Non-negotiable rules
1. Only the validator decides gates. Never report a gate as passed without `vmodel gate` / `vmodel status` output from this session.
2. Never edit `.vmodel/state/`, `.vmodel/evidence/`, `.vmodel/config.json`, `.vmodel/devkit.lock.json`, or the plugin's validator files. The guard hook blocks this; do not try to work around it.
3. Gate reviews (`.vmodel/work-items/<WI>/reviews/G*.json`) are written only by the `vmodel:verifier` subagent.
4. Never weaken or delete tests to pass a gate. If a test must change, record `test_changes` (reason, requirements, impact) in a defect or change request.
5. When a gate fails: record a DEFECT that references the failed record id and links every failing TEST id `vmodel status` shows, fix at the root-cause phase, set the DEFECT `status` to `fixed` together with the fix (defects.json is a G4/G5 input: editing it after a pass makes the gates STALE), then re-evaluate. After the same failure 3 times the validator BLOCKS the gate: stop and report to the user.
6. Ask the user (once, batched) about critical ambiguities at G1. Record non-critical assumptions instead of asking.
7. This DevKit verifies G1–G7. G6 runs the separate `integration_test` command and G7 the separate `system_test` command; if one is missing, ask the user (never substitute the unit tests). G6 "N/A" means no integration test ran (a confirmed single component without interfaces): never report it as an integration pass. System tests live in `tests/system/` and drive the program from outside (CLI, HTTP API, public library API). A work item is `COMPLETED` only when G1–G7 are PASSED for the current inputs; that is automated verification, not user acceptance or a deployment approval.

Commands: `/vmodel:start`, `/vmodel:status`, `/vmodel:verify`, `/vmodel:rework`, `/vmodel:report`.
