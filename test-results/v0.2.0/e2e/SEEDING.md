# E2E-A seeding note (synthetic, written before the run)

Sample: samples/scorepipe. The existing provider `src/scorepipe/parser.py` returns scores as strings ("07", "90"),
documented in its module docstring (the export allows zero padding; callers convert). The request (prompt-e2e-a.txt)
asks the new consumer to compute with integer scores and to unit-test the report with an injected fake parser.

Intended trap (synthetic seeding, the discovery itself is natural): if the consumer is written against a fake parser
that returns integers, unit tests pass at G5 while the real provider/consumer connection fails in the integration
tests at G6 (e.g. summing strings). Whether this happens depends on the agent; the result is reported as observed.
Nothing is injected during the session. No harness-written review is used.
