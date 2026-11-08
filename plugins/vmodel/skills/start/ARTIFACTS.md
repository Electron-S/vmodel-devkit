# VModel artifact formats

All files live in `.vmodel/work-items/<WI>/`, are UTF-8 JSON, and every `work_item` field equals the WI id.
Ids are project-unique (`VM next-id <KIND>`). The authoritative schemas are the validator's data/schemas;
`VM lint <WI>` checks artifacts against them.

## requirements.json (P1)
```json
{
  "work_item": "WI-001",
  "requirements": [
    {"id": "REQ-001", "type": "functional", "title": "Count words", "priority": "must", "status": "active",
     "description": "count_words(text) returns the case-insensitive count of each word.",
     "source": "user request",
     "acceptance_criteria": [
       {"id": "AC-001-1", "criterion": "count_words('a b A') returns {'a': 2, 'b': 1}"},
       {"id": "AC-001-2", "criterion": "count_words('') returns {}"}]},
    {"id": "REQ-002", "type": "non-functional", "title": "Standard library only", "priority": "must",
     "status": "active", "description": "No third-party packages.", "acceptance_criteria": []}
  ],
  "conflict_analysis": {"performed": true, "method": "pairwise review", "conflicts": [
    {"ids": ["REQ-001", "REQ-002"], "description": "...", "status": "resolved", "resolution": "..."}]},
  "open_issues": [
    {"id": "ISSUE-001", "description": "Should Korean words count?", "critical": true, "status": "resolved",
     "resolution": "Yes", "decided_by": "user", "user_answer": "한글도 세 주세요"}],
  "assumptions": [{"id": "ASM-001", "description": "Input fits in memory", "impact": "no streaming"}]
}
```
- `type`: functional | non-functional | constraint. `priority`: must | should | could. `status`: active | deleted.
- Functional requirements need >= 1 acceptance criterion; AC ids are `AC-<req number>-<n>`.
- Critical issues need a user decision (`decided_by: "user"`); an open critical issue keeps G1 at REVIEW_REQUIRED.
- After G1 has passed once, changed requirements need a change request (`change-requests.json`) listing them in `affected`.

## architecture.json (P2)
```json
{
  "work_item": "WI-001",
  "components": [
    {"id": "ARCH-001", "name": "tokenizer", "responsibility": "split text into lowercase words",
     "requirements": ["REQ-001"], "location": "src/pkg/tokenizer.py"},
    {"id": "ARCH-002", "name": "wordfreq", "responsibility": "aggregate counts", "requirements": ["REQ-001"]}],
  "interfaces": [
    {"id": "IF-001", "name": "tokenize", "provider": "ARCH-001", "consumers": ["ARCH-002"],
     "description": "tokenize(text) -> list[str]", "signature": "def tokenize(text: str) -> list[str]"}],
  "data_flows": [{"from": "ARCH-001", "to": "ARCH-002", "data": "tokens", "via": "IF-001"}],
  "nfr_mapping": [{"requirement": "REQ-002", "approach": "re + collections only", "components": ["ARCH-001", "ARCH-002"]}],
  "tradeoffs": [{"topic": "tokenising", "options": ["str.split", "regex"], "decision": "regex \\w+",
                 "rationale": "handles punctuation and Korean"}],
  "integration_test_strategy": {"approach": "wordfreq through the real tokenizer", "interfaces_covered": ["IF-001"]}
}
```
- Every active functional requirement maps to a component. Every non-functional/constraint requirement appears in `nfr_mapping`.
- 2+ components need interfaces; `consumers` may contain `EXTERNAL`. `interfaces_covered` must list every interface
  (single component: empty list plus an approach explaining why).

## design.json (P3)
```json
{
  "work_item": "WI-001",
  "units": [
    {"id": "DESIGN-001", "component": "ARCH-001", "module": "src/pkg/tokenizer.py", "name": "tokenize",
     "kind": "function", "signature": "def tokenize(text: str) -> list[str]",
     "description": "regex \\w+, lowercased", "requirements": ["REQ-001"],
     "contract": {"preconditions": ["text is str"], "postconditions": ["every item is a lowercase word"]},
     "errors": [{"exception": "TypeError", "condition": "text is not str"}],
     "boundary_conditions": ["empty string -> []"]}]
}
```
- `kind`: function | class | method (method names are `Class.method`). `module` is a `.py` path relative to the
  project root inside the configured source paths. `errors` may be `[]` but must be present; at least one boundary.
- Every component needs >= 1 unit; every functional requirement must reach >= 1 unit.

## tests.json (P3, written by vmodel:test-designer)
```json
{
  "work_item": "WI-001",
  "tests": [
    {"id": "TEST-001", "level": "unit", "title": "tokenize lowercases", "category": "normal",
     "verifies": ["DESIGN-001"], "procedure": "tokenize('Hello, hello')", "expected": "['hello', 'hello']",
     "automation": {"file": "tests/test_tokenizer.py"}},
    {"id": "TEST-002", "level": "unit", "title": "empty input", "category": "boundary", "verifies": ["DESIGN-001"],
     "procedure": "tokenize('')", "expected": "[]"},
    {"id": "TEST-003", "level": "unit", "title": "non-str rejected", "category": "abnormal",
     "verifies": ["DESIGN-001"], "procedure": "tokenize(None)", "expected": "TypeError"},
    {"id": "TEST-004", "level": "integration", "title": "wordfreq via tokenizer", "category": "normal",
     "verifies": ["IF-001"], "procedure": "...", "expected": "..."},
    {"id": "TEST-005", "level": "system", "title": "AC-001 scenarios", "category": "normal",
     "verifies": ["REQ-001"], "acceptance_criteria": ["AC-001-1", "AC-001-2"], "procedure": "...", "expected": "..."}]
}
```
- Per design unit: >= 1 unit test with category `normal`; `abnormal` if it declares errors; `boundary` (always, since
  every unit declares boundaries). Every interface needs an integration test spec; every acceptance criterion of a
  functional requirement needs a system test spec. Integration/system specs are planned now and executed in G6/G7
  (extension, not in the MVP).
- Test code: each unit-level spec is implemented by test function(s) whose name contains the token, e.g.
  `def test_TEST_001_tokenize_lowercases():`.

## reviews/G1..G4.json (written only by vmodel:verifier)
```json
{"gate": "G2", "work_item": "WI-001", "reviewer": "vmodel:verifier", "target_hash": "sha256:<from VM hash WI G2>",
 "reviewed_at": "2026-11-08T10:00:00Z", "verdict": "approve", "summary": "...",
 "checklist": [{"item": "every requirement realised by a component", "result": "ok", "note": "..."}],
 "findings": [{"id": "F-1", "severity": "minor", "description": "...", "related": ["ARCH-002"], "status": "open"}]}
```
`verdict` approve | reject; `severity` major | minor | info; an open major finding means reject.

## defects.json (rework)
```json
{"work_item": "WI-001", "defects": [
  {"id": "DEFECT-001", "gate": "G5", "found_in_records": ["R00012"], "description": "TEST-007 fails: wrong order",
   "failed_checks": ["G5.RESULTS", "G5.TEST_MAPPING"], "root_cause_phase": "P4",
   "root_cause": "sort key ignores ties", "fix_scope": ["src/pkg/wordfreq.py"], "related": ["DESIGN-003", "TEST-007"],
   "status": "fixed",
   "test_changes": [{"file": "tests/test_x.py", "since_record": "R00010", "reason": "...",
                     "requirements": ["REQ-002"], "impact": "..."}]}]}
```
`removed_ids` (DESIGN/TEST ids) is allowed on defects and change requests when an item is intentionally removed.

## change-requests.json (requirement changes after G1 passed)
```json
{"work_item": "WI-001", "change_requests": [
  {"id": "CR-001", "description": "tie order changes", "reason": "user request", "requested_by": "user",
   "affected": ["REQ-002", "DESIGN-003", "TEST-007"], "removed_ids": [], "status": "applied"}]}
```
