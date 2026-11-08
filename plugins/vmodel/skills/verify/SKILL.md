---
name: verify
description: Re-verify a VModel work item with the independent validator - re-evaluates G1..G5 (or one gate) from scratch, re-running the unit tests, without trusting earlier results. Use when the user asks to verify, re-check or confirm a work item, or before declaring work done.
argument-hint: "<WI-nnn> [G1..G5]"
---

1. If no work item id was given, run `"${CLAUDE_PLUGIN_ROOT}/bin/vmodel" status` and pick the work item the user means
   (ask if ambiguous).
2. Run `"${CLAUDE_PLUGIN_ROOT}/bin/vmodel" verify $ARGUMENTS`. It evaluates the gates in order and stops at the first
   gate that is not PASSED; G5 executes the tests again and records new evidence.
3. Report exactly what the validator printed: per-gate status, failed checks, evidence path, final work item status.
   Never claim a PASS the validator did not print.
4. If a gate is REVIEW_REQUIRED because a review is missing or targets old inputs, launch the `vmodel:verifier` subagent
   for that gate (give it the project root, WI, gate, the `vmodel hash` target hash and the absolute vmodel path), then
   verify again. If it FAILED, suggest `/vmodel:rework`. If BLOCKED, stop and explain.
5. Remind the user that G6/G7 are not implemented in this DevKit version (PARTIALLY_VERIFIED is the best result).
