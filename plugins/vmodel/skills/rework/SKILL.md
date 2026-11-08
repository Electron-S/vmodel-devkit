---
name: rework
description: VModel DevKit rework loop for a failed gate - analyse the failure, record a DEFECT with its root-cause phase, fix at that phase, invalidate and re-verify affected gates. Use after a gate FAILED or when the user asks to fix a failed V-Model verification.
argument-hint: "[WI-nnn]"
---

Validator: `"${CLAUDE_PLUGIN_ROOT}/bin/vmodel"` (VM). Artifact formats: `"${CLAUDE_PLUGIN_ROOT}/bin/vmodel" guide artifacts`.

1. `VM status $ARGUMENTS` — find the FAILED gate and its record id. If the gate is BLOCKED (e.g. same failure 3 times),
   stop: explain the failure history and what alternative you would propose; only the user can unblock.
2. Analyse the failure from the validator output (failed checks, failing test cases, review findings). Decide in which
   phase the error was introduced (P1 requirements, P2 architecture, P3 design/test spec, P4 code/test code).
3. Record a DEFECT in `defects.json` (`VM next-id DEFECT`) with `gate`, `found_in_records: [<record id>]`,
   `description`, `failed_checks`, `root_cause_phase`, `root_cause`, `fix_scope`, `related`, `status: "open"`.
   If the same defect recurs, append the new record id to its `found_in_records` instead of creating a new one.
4. Fix at the root-cause phase and update every affected artifact downstream. Never relax, skip or delete a test to make
   it pass. If a test really is wrong, change it and add `test_changes` (file, since_record = baseline record id named by
   the validator, reason, requirements, impact) to the defect.
5. Re-verify from the root-cause gate forward with the gate loop of `/vmodel:start` (lint -> verifier review for G1-G4
   -> `VM gate`). Gates whose inputs changed are STALE and must be re-reviewed.
6. When the gate passes, set the defect `status` to `fixed` and report what failed, why, what changed, and the new
   validator result.
