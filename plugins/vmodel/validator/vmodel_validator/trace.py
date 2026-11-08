"""Traceability graph: REQ <-> ARCH <-> DESIGN <-> TEST <-> code <-> results."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

TEST_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])TEST[-_](\d{3,})(?!\d)")


def test_ids_in_text(text: str) -> set[str]:
    return {f"TEST-{m}" for m in TEST_TOKEN_RE.findall(text)}


def _ids(value: Any) -> list[str]:
    """Agent-written id lists may have any JSON shape; keep only strings."""
    return [x for x in value if isinstance(x, str)] if isinstance(value, list) else []


def _list(obj: Any, key: str) -> list:
    if isinstance(obj, dict) and isinstance(obj.get(key), list):
        return [x for x in obj[key] if isinstance(x, dict)]
    return []


@dataclass
class TraceGraph:
    reqs: dict[str, dict] = field(default_factory=dict)
    acs: dict[str, str] = field(default_factory=dict)  # AC id -> REQ id
    comps: dict[str, dict] = field(default_factory=dict)
    ifaces: dict[str, dict] = field(default_factory=dict)
    units: dict[str, dict] = field(default_factory=dict)
    tests: dict[str, dict] = field(default_factory=dict)

    @staticmethod
    def build(arts: dict[str, Any]) -> "TraceGraph":
        g = TraceGraph()
        for r in _list(arts.get("requirements.json"), "requirements"):
            if isinstance(r.get("id"), str):
                g.reqs[r["id"]] = r
                for ac in (r.get("acceptance_criteria") if isinstance(r.get("acceptance_criteria"), list) else []):
                    if isinstance(ac, dict) and isinstance(ac.get("id"), str):
                        g.acs[ac["id"]] = r["id"]
        for c in _list(arts.get("architecture.json"), "components"):
            if isinstance(c.get("id"), str):
                g.comps[c["id"]] = c
        for i in _list(arts.get("architecture.json"), "interfaces"):
            if isinstance(i.get("id"), str):
                g.ifaces[i["id"]] = i
        for u in _list(arts.get("design.json"), "units"):
            if isinstance(u.get("id"), str):
                g.units[u["id"]] = u
        for t in _list(arts.get("tests.json"), "tests"):
            if isinstance(t.get("id"), str):
                g.tests[t["id"]] = t
        return g

    # ---- requirement classes ----------------------------------------
    def active(self, rtype: str | None = None) -> list[str]:
        return sorted(rid for rid, r in self.reqs.items()
                      if r.get("status", "active") == "active" and (rtype is None or r.get("type") == rtype))

    def exists(self, any_id: str) -> bool:
        return any(any_id in m for m in (self.reqs, self.acs, self.comps, self.ifaces, self.units, self.tests))

    # ---- forward links ----------------------------------------------
    def comps_for_req(self, rid: str) -> list[str]:
        return sorted(cid for cid, c in self.comps.items() if rid in _ids(c.get("requirements")))

    def units_for_req(self, rid: str) -> list[str]:
        return sorted(uid for uid, u in self.units.items() if rid in _ids(u.get("requirements")))

    def reqs_covered_by_test(self, tid: str) -> set[str]:
        t = self.tests.get(tid) or {}
        out: set[str] = set()
        for ref in _ids(t.get("verifies")):
            if ref in self.reqs:
                out.add(ref)
            elif ref in self.units:
                out.update(_ids(self.units[ref].get("requirements")))
            elif ref in self.comps:
                out.update(_ids(self.comps[ref].get("requirements")))
        for ac in _ids(t.get("acceptance_criteria")):
            if ac in self.acs:
                out.add(self.acs[ac])
        return out

    def tests_for_req(self, rid: str) -> list[str]:
        return sorted(tid for tid in self.tests if rid in self.reqs_covered_by_test(tid))

    def tests_for_unit(self, uid: str, level: str | None = "unit") -> list[str]:
        return sorted(tid for tid, t in self.tests.items()
                      if uid in _ids(t.get("verifies")) and (level is None or t.get("level") == level))

    def unit_tests(self) -> list[str]:
        return sorted(tid for tid, t in self.tests.items() if t.get("level") == "unit")

    # ---- dangling references ----------------------------------------
    def dangling(self) -> list[str]:
        problems: list[str] = []
        for cid, c in self.comps.items():
            for rid in _ids(c.get("requirements")):
                if rid not in self.reqs:
                    problems.append(f"{cid} -> {rid} (requirement does not exist)")
        for iid, i in self.ifaces.items():
            for ref in [i.get("provider"), *_ids(i.get("consumers"))]:
                if ref and ref != "EXTERNAL" and ref not in self.comps:
                    problems.append(f"{iid} -> {ref} (component does not exist)")
        for uid, u in self.units.items():
            if u.get("component") and u["component"] not in self.comps:
                problems.append(f"{uid} -> {u['component']} (component does not exist)")
            for rid in _ids(u.get("requirements")):
                if rid not in self.reqs:
                    problems.append(f"{uid} -> {rid} (requirement does not exist)")
        for tid, t in self.tests.items():
            for ref in _ids(t.get("verifies")):
                if not self.exists(ref):
                    problems.append(f"{tid} -> {ref} (verified item does not exist)")
            for ac in _ids(t.get("acceptance_criteria")):
                if ac not in self.acs:
                    problems.append(f"{tid} -> {ac} (acceptance criterion does not exist)")
        return problems

    # ---- impact -----------------------------------------------------
    def downstream(self, ids: set[str]) -> set[str]:
        """Items that trace (directly or transitively) to any of ids."""
        out: set[str] = set()
        frontier = set(ids)
        while frontier:
            nxt: set[str] = set()
            for cid, c in self.comps.items():
                if cid not in out and frontier & set(_ids(c.get("requirements"))):
                    nxt.add(cid)
            for iid, i in self.ifaces.items():
                if iid not in out and frontier & {i.get("provider"), *_ids(i.get("consumers"))}:
                    nxt.add(iid)
            for uid, u in self.units.items():
                if uid not in out and (frontier & set(_ids(u.get("requirements"))) or u.get("component") in frontier):
                    nxt.add(uid)
            for tid, t in self.tests.items():
                refs = set(_ids(t.get("verifies"))) | {self.acs.get(a) for a in _ids(t.get("acceptance_criteria"))}
                if tid not in out and frontier & refs:
                    nxt.add(tid)
            nxt -= out | ids
            out |= nxt
            frontier = nxt
        return out


def item_hashes(arts: dict[str, Any], names: list[str]) -> dict[str, str]:
    """Per-item content hashes for change control (G1/G2/G3 records)."""
    from .hashing import hash_obj

    keys = {"requirements.json": ["requirements"], "architecture.json": ["components", "interfaces"],
            "design.json": ["units"], "tests.json": ["tests"]}
    out: dict[str, str] = {}
    for name in names:
        for key in keys.get(name, []):
            for item in _list(arts.get(name), key):
                if isinstance(item.get("id"), str):
                    out[item["id"]] = hash_obj(item)
    return out
