"""Generate the artifact JSON schemas (JSON Schema subset, see DECISIONS D02).

Kept as a generator so the shared fragments stay consistent. Output is
committed under plugins/vmodel/validator/vmodel_validator/data/schemas/.
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "plugins/vmodel/validator/vmodel_validator/data/schemas"

S = {"type": "string", "minLength": 1}
OPT_S = {"type": "string"}


def ids(pattern: str, min_items: int = 0) -> dict:
    d = {"type": "array", "items": {"type": "string", "pattern": pattern}}
    if min_items:
        d["minItems"] = min_items
    return d


ANY_ID = r"^(REQ|AC|ARCH|IF|DESIGN|TEST)-\d{3,}(-\d+)?$"
TEST_CHANGE = {
    "type": "object",
    "required": ["file", "since_record", "reason", "requirements", "impact"],
    "properties": {
        "file": S,
        "since_record": {"type": "string", "pattern": r"^R\d{5,}$"},
        "reason": S,
        "requirements": ids(r"^REQ-\d{3,}$", 1),
        "impact": S,
    },
}

schemas = {
    "workitem": {
        "$id": "vmodel.workitem/1",
        "type": "object",
        "required": ["id", "title", "request", "profile", "created_at"],
        "properties": {
            "id": {"type": "string", "pattern": r"^WI-\d{3,}$"},
            "title": S,
            "request": S,
            "profile": {"enum": ["LITE", "STANDARD", "STRICT"]},
            "created_at": S,
        },
    },
    "requirements": {
        "$id": "vmodel.requirements/1",
        "type": "object",
        "required": ["work_item", "requirements", "conflict_analysis", "open_issues"],
        "properties": {
            "work_item": {"type": "string", "pattern": r"^WI-\d{3,}$"},
            "requirements": {"type": "array", "minItems": 1, "items": {"$ref": "#/definitions/req"}},
            "conflict_analysis": {
                "type": "object",
                "required": ["performed", "conflicts"],
                "properties": {
                    "performed": {"type": "boolean"},
                    "method": OPT_S,
                    "conflicts": {"type": "array", "items": {"$ref": "#/definitions/conflict"}},
                },
            },
            "open_issues": {"type": "array", "items": {"$ref": "#/definitions/issue"}},
            "assumptions": {"type": "array", "items": {"$ref": "#/definitions/assumption"}},
        },
        "definitions": {
            "req": {
                "type": "object",
                "required": ["id", "type", "title", "description", "priority", "status", "acceptance_criteria"],
                "properties": {
                    "id": {"type": "string", "pattern": r"^REQ-\d{3,}$"},
                    "type": {"enum": ["functional", "non-functional", "constraint"]},
                    "title": S,
                    "description": S,
                    "priority": {"enum": ["must", "should", "could"]},
                    "status": {"enum": ["active", "deleted"]},
                    "source": OPT_S,
                    "rationale": OPT_S,
                    "acceptance_criteria": {"type": "array", "items": {"$ref": "#/definitions/ac"}},
                },
            },
            "ac": {
                "type": "object",
                "required": ["id", "criterion"],
                "properties": {
                    "id": {"type": "string", "pattern": r"^AC-\d{3,}-\d+$"},
                    "criterion": S,
                    "given": OPT_S,
                    "when": OPT_S,
                    "then": OPT_S,
                },
            },
            "conflict": {
                "type": "object",
                "required": ["ids", "description", "status", "resolution"],
                "properties": {
                    "ids": ids(r"^REQ-\d{3,}$", 2),
                    "description": S,
                    "status": {"enum": ["open", "resolved"]},
                    "resolution": OPT_S,
                },
            },
            "issue": {
                "type": "object",
                "required": ["id", "description", "critical", "status"],
                "properties": {
                    "id": {"type": "string", "pattern": r"^ISSUE-\d{3,}$"},
                    "description": S,
                    "critical": {"type": "boolean"},
                    "status": {"enum": ["open", "resolved"]},
                    "resolution": OPT_S,
                    "decided_by": {"enum": ["user", "assumption", "orchestrator"]},
                    "user_answer": OPT_S,
                },
            },
            "assumption": {
                "type": "object",
                "required": ["id", "description"],
                "properties": {"id": {"type": "string", "pattern": r"^ASM-\d{3,}$"}, "description": S, "impact": OPT_S},
            },
        },
    },
    "architecture": {
        "$id": "vmodel.architecture/1",
        "type": "object",
        "required": ["work_item", "components", "interfaces", "data_flows", "nfr_mapping", "tradeoffs", "integration_test_strategy"],
        "properties": {
            "work_item": {"type": "string", "pattern": r"^WI-\d{3,}$"},
            "components": {"type": "array", "minItems": 1, "items": {
                "type": "object",
                "required": ["id", "name", "responsibility", "requirements"],
                "properties": {
                    "id": {"type": "string", "pattern": r"^ARCH-\d{3,}$"},
                    "name": S,
                    "responsibility": S,
                    "requirements": ids(r"^REQ-\d{3,}$"),
                    "location": OPT_S,
                },
            }},
            "interfaces": {"type": "array", "items": {
                "type": "object",
                "required": ["id", "name", "provider", "consumers", "description"],
                "properties": {
                    "id": {"type": "string", "pattern": r"^IF-\d{3,}$"},
                    "name": S,
                    "provider": {"type": "string", "pattern": r"^ARCH-\d{3,}$"},
                    "consumers": ids(r"^(ARCH-\d{3,}|EXTERNAL)$", 1),
                    "description": S,
                    "signature": OPT_S,
                },
            }},
            "data_flows": {"type": "array", "items": {
                "type": "object",
                "required": ["from", "to", "data"],
                "properties": {"from": S, "to": S, "data": S, "via": OPT_S},
            }},
            "nfr_mapping": {"type": "array", "items": {
                "type": "object",
                "required": ["requirement", "approach", "components"],
                "properties": {
                    "requirement": {"type": "string", "pattern": r"^REQ-\d{3,}$"},
                    "approach": S,
                    "components": ids(r"^ARCH-\d{3,}$", 1),
                },
            }},
            "tradeoffs": {"type": "array", "items": {
                "type": "object",
                "required": ["topic", "options", "decision", "rationale"],
                "properties": {"topic": S, "options": {"type": "array", "minItems": 1, "items": S}, "decision": S, "rationale": S},
            }},
            "integration_test_strategy": {
                "type": "object",
                "required": ["approach", "interfaces_covered"],
                "properties": {"approach": S, "interfaces_covered": ids(r"^IF-\d{3,}$"), "na_reason": OPT_S},
            },
        },
    },
    "design": {
        "$id": "vmodel.design/1",
        "type": "object",
        "required": ["work_item", "units"],
        "properties": {
            "work_item": {"type": "string", "pattern": r"^WI-\d{3,}$"},
            "units": {"type": "array", "minItems": 1, "items": {
                "type": "object",
                "required": ["id", "component", "module", "name", "kind", "signature", "description",
                             "requirements", "contract", "errors", "boundary_conditions"],
                "properties": {
                    "id": {"type": "string", "pattern": r"^DESIGN-\d{3,}$"},
                    "component": {"type": "string", "pattern": r"^ARCH-\d{3,}$"},
                    "module": S,
                    "name": {"type": "string", "pattern": r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$"},
                    "kind": {"enum": ["function", "class", "method"]},
                    "signature": S,
                    "description": S,
                    "requirements": ids(r"^REQ-\d{3,}$"),
                    "contract": {
                        "type": "object",
                        "required": ["preconditions", "postconditions"],
                        "properties": {
                            "preconditions": {"type": "array", "items": S},
                            "postconditions": {"type": "array", "minItems": 1, "items": S},
                        },
                    },
                    "errors": {"type": "array", "items": {
                        "type": "object",
                        "required": ["exception", "condition"],
                        "properties": {"exception": S, "condition": S},
                    }},
                    "boundary_conditions": {"type": "array", "minItems": 1, "items": S},
                    "states": {"type": "array", "items": S},
                },
            }},
        },
    },
    "tests": {
        "$id": "vmodel.tests/1",
        "type": "object",
        "required": ["work_item", "tests"],
        "properties": {
            "work_item": {"type": "string", "pattern": r"^WI-\d{3,}$"},
            "tests": {"type": "array", "minItems": 1, "items": {
                "type": "object",
                "required": ["id", "level", "title", "category", "verifies", "procedure", "expected"],
                "properties": {
                    "id": {"type": "string", "pattern": r"^TEST-\d{3,}$"},
                    "level": {"enum": ["unit", "integration", "system"]},
                    "title": S,
                    "category": {"enum": ["normal", "abnormal", "boundary"]},
                    "verifies": ids(r"^(REQ|ARCH|IF|DESIGN)-\d{3,}$", 1),
                    "acceptance_criteria": ids(r"^AC-\d{3,}-\d+$"),
                    "procedure": S,
                    "expected": S,
                    "automation": {"type": "object", "properties": {"file": OPT_S}},
                },
            }},
        },
    },
    "review": {
        "$id": "vmodel.review/1",
        "type": "object",
        "required": ["gate", "work_item", "reviewer", "target_hash", "reviewed_at", "verdict", "summary", "checklist", "findings"],
        "properties": {
            "gate": {"enum": ["G1", "G2", "G3", "G4"]},
            "work_item": {"type": "string", "pattern": r"^WI-\d{3,}$"},
            "reviewer": S,
            "target_hash": {"type": "string", "pattern": r"^sha256:[0-9a-f]{64}$"},
            "reviewed_at": S,
            "verdict": {"enum": ["approve", "reject"]},
            "summary": S,
            "checklist": {"type": "array", "minItems": 1, "items": {
                "type": "object",
                "required": ["item", "result"],
                "properties": {"item": S, "result": {"enum": ["ok", "issue", "na"]}, "note": OPT_S},
            }},
            "findings": {"type": "array", "items": {
                "type": "object",
                "required": ["id", "severity", "description", "status"],
                "properties": {
                    "id": S,
                    "severity": {"enum": ["major", "minor", "info"]},
                    "description": S,
                    "related": {"type": "array", "items": S},
                    "status": {"enum": ["open", "resolved"]},
                },
            }},
            # 0.2.0 (G6). Shapes are checked by the gates that use them, not here, so a malformed entry makes G4
            # REVIEW_REQUIRED (REQ-G6-12) and G6 BLOCKED (REQ-G6-16) instead of changing the G2/G3/G4 schema check.
            # integration_applicability (G2, G3): {"decision": "not_required", "reason": str,
            #                                      "endpoints_reviewed": [str]}
            # interfaces (G4): [{"id": "IF-nnn", "result": "ok"|"issue", "provider_symbols": [str], "note": str,
            #                    "runtime_paths": [{"test": "TEST-nnn", "kind": "subprocess"|"ipc"|"api"|"dynamic_import",
            #                                       "test_file_sha256": "sha256:...", "entry": str, "note": str}]}]
            "integration_applicability": {"type": "object"},
            "interfaces": {"type": "array", "items": {"type": "object"}},
        },
    },
    "defects": {
        "$id": "vmodel.defects/1",
        "type": "object",
        "required": ["work_item", "defects"],
        "properties": {
            "work_item": {"type": "string", "pattern": r"^WI-\d{3,}$"},
            "defects": {"type": "array", "items": {
                "type": "object",
                "required": ["id", "gate", "found_in_records", "description", "root_cause_phase", "root_cause", "fix_scope", "status"],
                "properties": {
                    "id": {"type": "string", "pattern": r"^DEFECT-\d{3,}$"},
                    "gate": {"enum": ["G1", "G2", "G3", "G4", "G5", "G6"]},
                    "found_in_records": {"type": "array", "minItems": 1, "items": {"type": "string", "pattern": r"^R\d{5,}$"}},
                    "description": S,
                    "failed_checks": {"type": "array", "items": S},
                    "root_cause_phase": {"enum": ["P1", "P2", "P3", "P4", "P5", "P6"]},
                    "root_cause": S,
                    "fix_scope": {"type": "array", "minItems": 1, "items": S},
                    "related": ids(ANY_ID),
                    "removed_ids": ids(r"^(IF|DESIGN|TEST)-\d{3,}$"),
                    "test_changes": {"type": "array", "items": TEST_CHANGE},
                    "status": {"enum": ["open", "fixed"]},
                },
            }},
        },
    },
    "change_requests": {
        "$id": "vmodel.change_requests/1",
        "type": "object",
        "required": ["work_item", "change_requests"],
        "properties": {
            "work_item": {"type": "string", "pattern": r"^WI-\d{3,}$"},
            "change_requests": {"type": "array", "items": {
                "type": "object",
                "required": ["id", "description", "reason", "affected", "status"],
                "properties": {
                    "id": {"type": "string", "pattern": r"^CR-\d{3,}$"},
                    "description": S,
                    "reason": S,
                    "requested_by": OPT_S,
                    "affected": ids(ANY_ID, 1),
                    "removed_ids": ids(r"^(REQ|IF|DESIGN|TEST)-\d{3,}$"),
                    "test_changes": {"type": "array", "items": TEST_CHANGE},
                    "status": {"enum": ["open", "applied", "rejected"]},
                },
            }},
        },
    },
    "config": {
        "$id": "vmodel.config/1",
        "type": "object",
        "required": ["schema", "project_id", "default_profile", "language", "python", "paths", "unit_test", "static_analysis"],
        "properties": {
            "schema": {"const": "vmodel.config/1"},
            "project_id": {"type": "string", "pattern": r"^[0-9a-f]{32}$"},
            "default_profile": {"enum": ["LITE", "STANDARD", "STRICT"]},
            "language": {"enum": ["python"]},
            "python": S,
            "paths": {
                "type": "object",
                "required": ["source", "tests", "build_config"],
                "properties": {
                    "source": {"type": "array", "minItems": 1, "items": S},
                    "tests": {"type": "array", "minItems": 1, "items": S},
                    "build_config": {"type": "array", "items": S},
                    "other": {"type": "array", "items": S},
                },
            },
            "unit_test": {
                "type": "object",
                "required": ["argv", "timeout_s"],
                "properties": {
                    "argv": {"type": "array", "minItems": 1, "items": S},
                    "timeout_s": {"type": "integer"},
                    "plugin_autoload": {"type": "boolean"},
                },
            },
            # 0.2.0 (G6, optional): the integration test command. G6 re-checks this shape on every evaluation
            # (config is schema-checked only at init) and needs {junit} in argv and a positive timeout.
            "integration_test": {
                "type": "object",
                "required": ["argv", "timeout_s"],
                "properties": {
                    "argv": {"type": "array", "minItems": 1, "items": S},
                    "timeout_s": {"type": "integer"},
                    "plugin_autoload": {"type": "boolean"},
                },
            },
            "static_analysis": {
                "type": "object",
                "required": ["lint", "on_missing_lint"],
                "properties": {
                    "lint": {"type": ["object", "null"], "required": ["name", "argv"],
                             "properties": {"name": S, "argv": {"type": "array", "minItems": 1, "items": S}}},
                    "on_missing_lint": {"enum": ["block", "syntax-only"]},
                },
            },
        },
    },
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, schema in schemas.items():
        path = OUT / f"{name}.schema.json"
        path.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {path.name}")


if __name__ == "__main__":
    main()
