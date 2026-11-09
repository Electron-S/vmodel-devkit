---
name: report
description: Generate the VModel DevKit Markdown report for a work item (gate results, mechanical vs AI-review checks, evidence, traceability matrix, defects, change requests, limitations). Use when the user asks for a report or summary of a V-Model work item.
argument-hint: "<WI-nnn>"
---

1. Run `"${CLAUDE_PLUGIN_ROOT}/bin/vmodel" report $ARGUMENTS` (if no id was given, pick it from
   `"${CLAUDE_PLUGIN_ROOT}/bin/vmodel" status`). It writes `.vmodel/reports/<WI>.md`.
2. Read the report and give the user a short summary in their language: work item status, each gate's status, where the
   evidence is, defects and their state, and the limitations section (AI reviews are not machine-verified; G7 is not
   implemented, so PARTIALLY_VERIFIED is not a full V-Model completion; a G6 N/A executed no integration test).
3. Give the report path. Do not edit the report by hand; it is regenerated from the signed ledger.
