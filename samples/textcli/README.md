# textcli (sample)

VModel DevKit sample project for the G7 (system verification) E2E. Starts with an empty package and one smoke test
per level: `tests/unit`, `tests/integration` and `tests/system`. Because `tests/integration` and `tests/system` hold
tests, `vmodel install` registers the `integration_test` and `system_test` commands (the user-only configuration step),
so a headless session can run G6 and G7 without stopping for `vmodel configure-tests`. Features are added through the
V-Model workflow.
