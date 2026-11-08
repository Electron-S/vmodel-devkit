---
name: rework
description: VModel DevKit rework loop for a failed gate - analyse the failure, record a DEFECT with its root-cause phase, fix at that phase, invalidate and re-verify affected gates. Use after a gate FAILED or when the user asks to fix a failed V-Model verification.
argument-hint: "[WI-nnn]"
---

Validator: `"${CLAUDE_PLUGIN_ROOT}/bin/vmodel"` (VM). Artifact formats: `"${CLAUDE_PLUGIN_ROOT}/bin/vmodel" guide artifacts`.
Run every VM call as its own Bash command (no `VM=` variables, `;`/`&&` chains or `cd`), as in `/vmodel:start`.

1. `VM status $ARGUMENTS` — find the FAILED gate, its record id, and the failed checks, failing test cases and failing
   TEST ids shown under it. If the gate is BLOCKED (e.g. same failure 3 times), stop: explain the failure history and
   what alternative you would propose; only the user can unblock.
2. Analyse the failure from the validator output (failed checks, failing test cases, review findings), not from earlier
   explanations by whoever wrote the code. Decide in which phase the error was introduced (P1 requirements,
   P2 architecture, P3 design/test spec, P4 code/test code). The root cause must explain every failing case.
3. Record a DEFECT in `defects.json` (`VM next-id DEFECT`) with `gate`, `found_in_records: [<record id>]`,
   `description`, `failed_checks`, `root_cause_phase`, `root_cause`, `fix_scope`, `related` (REQ/DESIGN ids and every
   failing TEST id listed by `VM status`), `status: "open"`.
   If the same defect recurs, append the new record id to its `found_in_records` instead of creating a new one.
4. Fix at the root-cause phase and update every affected artifact downstream. In the same step set the defect `status`
   to `fixed` — before the re-review: `defects.json` is a G4/G5 input, so editing it after a gate passed makes G4/G5
   STALE again and costs another review. `fixed` is only your claim; the validator proves the closure (`VM status`
   shows "verified by <record>" once the gate passes). Never relax, skip or delete a test to make it pass. If a test
   really is wrong, change it and add `test_changes` (file, since_record = baseline record id named by the validator,
   reason, requirements, impact) to the defect.
5. `VM lint $ARGUMENTS` (ERROR: invalid citations, evidence integrity; WARNING: failing TEST ids the defect does
   not link, UNKNOWN per-TEST results), then re-verify from the root-cause gate
   forward with the gate loop of `/vmodel:start` (lint -> verifier review for G1-G4 -> `VM gate`). Gates whose inputs
   changed are STALE and must be re-reviewed.
6. When the gate passes, leave `defects.json` as it is and report what failed, why, what changed, and the new validator
   result, including the "verified by" record `VM status` shows for the defect. Report every ERROR and WARNING line of
   the defect trace check (`VM status` / the `## Defect trace check` section of `VM report`) as it is: evidence
   errors (`evidence_integrity`, `invalid_citation`) and trace warnings (`unlinked_failing_test`,
   `unknown_test_result`) must not be dropped, even when the work item is PARTIALLY_VERIFIED.
