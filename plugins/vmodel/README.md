# vmodel — VModel DevKit plugin

V-Model development workflow for Claude Code with an independent, evidence-based quality gate validator.
Requirements (G1), architecture (G2), detailed design and test planning (G3), implementation (G4), unit
verification (G5), integration verification (G6, since 0.2.0) and system verification (G7, since 0.3.0) are each gated
by a standard-library Python validator that runs the tests itself, signs its records and marks results STALE when any
verified file changes. G6 runs the project's separate integration_test command and checks every interface against a
static call analysis or, for declared runtime paths, a runtime trace; it is N/A only for a confirmed single component
without interfaces. G7 runs the separate system_test command as a black box and needs every acceptance criterion of
the active functional requirements verified by system tests that passed in that run. A work item is COMPLETED only
when G1-G7 are PASSED for the current inputs (automated verification, not user acceptance).

Commands: `/vmodel:start <request>`, `/vmodel:status`, `/vmodel:verify`, `/vmodel:rework`, `/vmodel:report`.
Agents: `vmodel:verifier` (independent reviews), `vmodel:test-designer` (test specs), plus role guides.
Hooks: a fail-closed PreToolUse guard protecting validator-owned files, and SessionStart status restoration.

Setup and details: see the repository README (installation, versioning, removal) and SPEC.md.
