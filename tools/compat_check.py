#!/usr/bin/env python3
"""
compat_check.py — interface compatibility + gap finder for the Mars to Table trade space.

Usage:
  python compat_check.py                            # human-readable summary to stdout
  python compat_check.py --gap-report               # writes outputs/gap_report.md
  python compat_check.py --architecture path/to/arch.json   # check one architecture
  python compat_check.py --audit                    # ontology audit (stray flow_ids etc.)

An "architecture" file is a JSON list of TECH-IDs:
  ["TECH-0001", "TECH-0011", "TECH-0014", "TECH-0015"]
"""
from __future__ import annotations
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "technologies.jsonl"
ONTOLOGY = ROOT / "schema" / "interface_ontology.md"
OUT_DIR = ROOT / "outputs"

# All REQ-SYS-001..060 the trade space should aim to cover (per requirements_register.md)
ALL_REQS = [f"REQ-SYS-{i:03d}" for i in range(1, 61)]


def load_db() -> list[dict]:
    if not DATA.exists():
        sys.exit(f"missing database file: {DATA}")
    out = []
    for i, line in enumerate(DATA.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as e:
            sys.exit(f"parse error on line {i}: {e}")
    return out


def known_flows() -> set[str]:
    """Pull flow_ids from interface_ontology.md (rows that look like `| flow_id | ... |`)."""
    if not ONTOLOGY.exists():
        return set()
    flows = set()
    for line in ONTOLOGY.read_text(encoding="utf-8").splitlines():
        if line.startswith("| `") and "` |" in line:
            inside = line.split("`")[1]
            if inside and inside not in {"flow_id", ""}:
                flows.add(inside)
    return flows


def function_gaps(db: list[dict]) -> list[str]:
    coverage = {r: [] for r in ALL_REQS}
    for d in db:
        for r in d.get("satisfies_requirements", []):
            coverage.setdefault(r, []).append(d["id"])
    return [r for r in ALL_REQS if not coverage[r]]


def interface_gaps(db: list[dict]) -> list[dict]:
    producers, consumers = defaultdict(list), defaultdict(list)
    for d in db:
        for o in d.get("outputs", []):
            producers[o["flow_id"]].append((d["id"], o.get("rate"), o.get("units")))
        for i in d.get("inputs", []):
            consumers[i["flow_id"]].append((d["id"], i.get("rate"), i.get("units")))
    gaps = []
    for f in set(producers) | set(consumers):
        p, c = producers.get(f, []), consumers.get(f, [])
        if not p and c:
            gaps.append({"kind": "no_producer", "flow": f, "consumers": c})
        elif not c and p:
            gaps.append({"kind": "no_consumer", "flow": f, "producers": p})
    return gaps


def bridge_gaps(db: list[dict]) -> list[dict]:
    out = []
    by_id = {d["id"]: d for d in db}
    for a in db:
        bridges = set(a.get("bridges_to") or [])
        if not bridges:
            continue
        for o in a.get("outputs", []):
            for b in db:
                if b["id"] == a["id"]:
                    continue
                for i in b.get("inputs", []):
                    if i["flow_id"] in bridges and i["flow_id"] != o["flow_id"]:
                        out.append({
                            "from": a["id"], "from_flow": o["flow_id"],
                            "to": b["id"], "to_flow": i["flow_id"]
                        })
    return out


def ontology_audit(db: list[dict]) -> list[str]:
    """Flag flow_ids used in the DB that aren't in interface_ontology.md."""
    known = known_flows()
    used = set()
    for d in db:
        for o in d.get("outputs", []):
            used.add(o["flow_id"])
        for i in d.get("inputs", []):
            used.add(i["flow_id"])
    return sorted(used - known) if known else []


def check_architecture(db: list[dict], tech_ids: list[str]) -> dict:
    by_id = {d["id"]: d for d in db}
    missing = [t for t in tech_ids if t not in by_id]
    if missing:
        sys.exit(f"unknown TECH-IDs: {missing}")
    chosen = [by_id[t] for t in tech_ids]

    balance = defaultdict(float)
    mass = vol = power = crew = 0.0
    for d in chosen:
        mass += float((d.get("mass_kg") or {}).get("value") or 0)
        vol += float((d.get("volume_m3") or {}).get("value") or 0)
        power += float((d.get("power_w") or {}).get("nominal") or 0)
        crew += float((d.get("crew_time_hr_per_sol") or {}).get("nominal") or 0)
        for o in d.get("outputs", []):
            try: balance[o["flow_id"]] += float(o.get("rate", 0))
            except (TypeError, ValueError): pass
        for i in d.get("inputs", []):
            try: balance[i["flow_id"]] -= float(i.get("rate", 0))
            except (TypeError, ValueError): pass
    return {
        "techs": tech_ids,
        "esm": {"mass_kg": mass, "volume_m3": vol, "power_w": power, "crew_hr_per_sol": crew},
        "balance": dict(balance),
    }


def write_gap_report(db: list[dict]) -> Path:
    OUT_DIR.mkdir(exist_ok=True)
    fp = OUT_DIR / "gap_report.md"
    fgaps = function_gaps(db)
    igaps = interface_gaps(db)
    bgaps = bridge_gaps(db)
    audit = ontology_audit(db)

    md = ["# Gap Report", f"\nDatabase: {len(db)} technologies\n"]

    md.append(f"## Function gaps ({len(fgaps)})\n")
    md.append("REQ-SYS entries with no candidate technology in the database.\n")
    if fgaps:
        for r in fgaps:
            md.append(f"- {r}")
    else:
        md.append("_(none)_")

    md.append(f"\n## Interface gaps ({len(igaps)})\n")
    md.append("Flows produced or consumed with no counterpart.\n")
    for g in igaps:
        if g["kind"] == "no_producer":
            md.append(f"- **No producer for `{g['flow']}`** — consumed by: " +
                      ", ".join(f"`{c[0]}` ({c[1]} {c[2]})" for c in g["consumers"]))
        else:
            md.append(f"- **No consumer for `{g['flow']}`** — produced by: " +
                      ", ".join(f"`{p[0]}` ({p[1]} {p[2]})" for p in g["producers"]))

    md.append(f"\n## Bridge gaps ({len(bgaps)})\n")
    md.append("Output A almost matches input B via a `bridges_to` hint — innovation slots.\n")
    for g in bgaps:
        md.append(f"- `{g['from']}` → bridge → `{g['to']}` (`{g['from_flow']}` → `{g['to_flow']}`)")

    md.append(f"\n## Ontology audit\n")
    if audit:
        md.append("Flow IDs used in the DB but not registered in `schema/interface_ontology.md`:\n")
        for f in audit:
            md.append(f"- `{f}`")
    else:
        md.append("All used flow IDs are registered.")

    fp.write_text("\n".join(md), encoding="utf-8")
    return fp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gap-report", action="store_true", help="write outputs/gap_report.md")
    ap.add_argument("--architecture", help="path to JSON list of TECH-IDs")
    ap.add_argument("--audit", action="store_true", help="run ontology audit only")
    args = ap.parse_args()

    db = load_db()

    if args.audit:
        bad = ontology_audit(db)
        if bad:
            print("Unregistered flow_ids:")
            for f in bad: print(f"  {f}")
            sys.exit(1)
        print(f"OK — all {len(db)} techs use registered flow_ids")
        return

    if args.architecture:
        ids = json.loads(Path(args.architecture).read_text())
        result = check_architecture(db, ids)
        print(json.dumps(result, indent=2))
        return

    if args.gap_report:
        fp = write_gap_report(db)
        print(f"wrote {fp}")
        return

    # Default: human summary
    fgaps = function_gaps(db)
    igaps = interface_gaps(db)
    bgaps = bridge_gaps(db)
    print(f"Database: {len(db)} technologies")
    print(f"Function gaps:  {len(fgaps)}  (e.g. {fgaps[:5]})")
    print(f"Interface gaps: {len(igaps)}")
    print(f"Bridge gaps:    {len(bgaps)}")
    print(f"\nRun --gap-report for the full markdown report.")


if __name__ == "__main__":
    main()
