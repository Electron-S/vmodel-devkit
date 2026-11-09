---
name: status
description: Show VModel DevKit gate and work item status (G1-G6 PASSED/N/A/FAILED/STALE/BLOCKED..., validator integrity, ledger health, next action). Use when the user asks where a V-Model work item stands or after a session restart.
argument-hint: "[WI-nnn]"
---

Run `"${CLAUDE_PLUGIN_ROOT}/bin/vmodel" status $ARGUMENTS` with Bash and report the result to the user in their language.

- Quote statuses exactly as the validator prints them; do not upgrade or reinterpret them (STALE is not PASSED,
  PARTIALLY_VERIFIED is not COMPLETED).
- For STALE gates, list the changed files the validator shows. For REVIEW_REQUIRED, name who must review.
- G6 "N/A" means no integration test was executed (a confirmed single component without interfaces); "not evaluated
  yet" means integration verification has not run. Report both exactly so, and pass on any scope warning.
- If the validator integrity or the ledger is not OK, say so first: every gate is BLOCKED until a user resolves it.
- End with the validator's `next:` line as the suggested next step (e.g. `/vmodel:start` to continue, `/vmodel:rework`).
