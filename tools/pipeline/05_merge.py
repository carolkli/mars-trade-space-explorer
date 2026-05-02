#!/usr/bin/env python3
"""
05_merge.py — Stage 5 of the pipeline.

Reads enriched pipeline records from data/pipeline/4_enriched/records_enriched.jsonl
and writes them into data/technologies.jsonl in the schema the React viewer expects.

Backs up the existing data/technologies.jsonl to data/technologies_legacy.jsonl
before overwriting (one-time, won't clobber an existing legacy backup).

After running this, hard-refresh the React viewer (Ctrl+Shift+R) — all
2,437 enriched entries will show up in the Spreadsheet, Builder, Flows,
Compare, and Scorecard tabs with their TechPort URLs as click-throughs.

Usage:
    python 05_merge.py
    python 05_merge.py --dry-run         # preview, don't write
    python 05_merge.py --no-backup       # skip the legacy backup step
"""
from __future__ import annotations
import argparse, json, shutil, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
ENRICHED = ROOT / "data" / "pipeline" / "4_enriched" / "records_enriched.jsonl"
TARGET   = ROOT / "data" / "technologies.jsonl"
LEGACY   = ROOT / "data" / "technologies_legacy.jsonl"

# Map TX taxonomy code prefix -> (subsystem ST1-4, category enum used by React viewer)
TX_TO_SUBSYSTEM = [
    # most specific first, fall through to less specific
    ("TX06.1.1", "ST1", "air_revitalization"),
    ("TX06.1.2", "ST1", "water_recovery"),
    ("TX06.1.3", "ST1", "waste_processing"),
    ("TX06.1.4", "ST4", "structures"),
    ("TX06.1.5", "ST3", "monitoring_control"),
    ("TX06.1",   "ST1", "air_revitalization"),
    ("TX06.2",   "ST1", "air_revitalization"),     # EVA / PLSS
    ("TX06.3.5", "ST2", "food_processing"),
    ("TX06.3",   "ST2", "monitoring_control"),     # human health
    ("TX06.4",   "ST3", "monitoring_control"),
    ("TX06.5",   "ST1", "structures"),             # radiation
    ("TX06.6",   "ST3", "monitoring_control"),     # human factors
    ("TX06",     "ST2", "other"),
    ("TX07.1.1", "ST1", "isru"),
    ("TX07.1.2", "ST1", "isru"),
    ("TX07.1.3", "ST1", "isru"),
    ("TX07.1.4", "ST1", "isru"),
    ("TX07.1",   "ST1", "isru"),
    ("TX07",     "ST4", "structures"),
    ("TX03.1",   "ST1", "power"),
    ("TX03.2",   "ST1", "power"),
    ("TX03",     "ST1", "power"),
    ("TX14",     "ST1", "thermal_control"),
    ("TX12",     "ST4", "structures"),
    ("TX01",     "ST1", "other"),                   # propulsion
    ("TX08",     "ST3", "monitoring_control"),
    ("TX11",     "ST3", "monitoring_control"),     # software/sim
]


def _classify(primary_tax_codes: list[str]) -> tuple[str, str]:
    """Return (subsystem ST1-4, category enum) from primary taxonomy code list."""
    for code in primary_tax_codes or []:
        for prefix, subsys, cat in TX_TO_SUBSYSTEM:
            if code.startswith(prefix):
                return subsys, cat
    return "ST1", "other"


def _short_description(long_text: str, max_chars: int = 250) -> str:
    """First sentence(ish) of the description, truncated."""
    if not long_text: return ""
    s = long_text.strip()
    # Try to cut at first sentence end inside the budget
    end_marks = [".  ", ". ", ".\n", "!\n", "?\n"]
    cut = -1
    for m in end_marks:
        idx = s.find(m, 50, max_chars)
        if idx > 0 and (cut < 0 or idx < cut):
            cut = idx + 1
    if cut > 0:
        return s[:cut].strip()
    return (s[:max_chars].rsplit(" ", 1)[0] + "…") if len(s) > max_chars else s


def _build_techport_metadata(rec: dict) -> dict:
    """Build the techport_metadata block from pipeline structured fields."""
    s = rec.get("structured", {})
    e = rec.get("enriched", {})
    src = rec.get("source", {})
    meta = {
        "scraped_at":                       src.get("fetched_at"),
        "project_status":                   s.get("project_status"),
        "lead_organization":                s.get("lead_organization"),
        "responsible_program":              s.get("responsible_program"),
        "responsible_mission_directorate":  s.get("responsible_mission_directorate"),
        "start_date":                       s.get("start_date"),
        "end_date":                         s.get("end_date"),
        "primary_taxonomy":                 s.get("primary_taxonomy") or [],
        "target_destinations":              s.get("target_destinations") or [],
        "anticipated_benefits":             (s.get("anticipated_benefits") or "")[:1500],
        "novelty":                          e.get("novelty_summary"),
        "tradespace_role":                  e.get("tradespace_role"),
        "enrichment_confidence":            e.get("_confidence"),
        "enrichment_model":                 (e.get("_enrichment") or {}).get("model"),
        "enrichment_prompt_version":        (e.get("_enrichment") or {}).get("prompt_version"),
    }
    # drop nulls/empties to keep the JSON tidy
    return {k: v for k, v in meta.items() if v not in (None, "", [])}


def _build_viewer_record(rec: dict) -> dict | None:
    """Convert a pipeline canonical record into the React viewer's schema."""
    s = rec.get("structured", {})
    e = rec.get("enriched", {})
    pid = s.get("project_id") or rec.get("id", "").replace("techport_", "")
    if not pid: return None

    subsystem, category = _classify(s.get("primary_taxonomy") or [])

    # Source URLs
    techport_url = f"https://techport.nasa.gov/projects/{pid}"
    sources = [{
        "url": techport_url,
        "title": f"NASA TechPort {pid}",
        "flag": "TECHPORT_SCRAPED_AUTHORITATIVE",
    }]

    # TRL block
    trl = {}
    if s.get("trl_current") is not None:
        trl["value"] = s["trl_current"]
    if s.get("trl_start") is not None:
        trl["trl_start"] = s["trl_start"]
    if s.get("trl_current") is not None:
        trl["trl_current"] = s["trl_current"]
    if s.get("trl_end_target") is not None:
        trl["trl_end_target"] = s["trl_end_target"]
    if s.get("end_date"):
        trl["date"] = s["end_date"]
    trl["source_ref"] = f"TechPort {pid}"

    record = {
        "id":                       rec["id"],            # techport_NNNNN format, unique + traceable
        "name":                     s.get("title", ""),
        "short_description":        _short_description(s.get("description") or "", 250),
        "category":                 category,
        "subsystem":                subsystem,
        "function_role":            (e.get("novelty_summary") or "")[:300],
        "applicable_subsystems":    e.get("applicable_subsystems") or [],
        "satisfies_requirements":   e.get("satisfies_requirements") or [],
        "techport_url":             techport_url,
        "sources":                  sources,
        "trl":                      trl,
        "techport_metadata":        _build_techport_metadata(rec),
        # Mars-environment fields default to TBR — not derivable from TechPort
        "mars_gravity_compatible":      "TBR",
        "habitat_atmosphere_compatible":"TBR",
        "temperature_range_c":          [10, 40],
        # ECLSS fields — empty by default, the team can add later
        "provides_benefits":            [],
        "requires_capabilities":        [],
        "eclss_interfaces":             [],
        "loop_closure_role":            "neither",
        # Governance
        "status":      "DRAFT",
        "entered_by":  "pipeline (05_merge.py from 04_enriched)",
        "date_added":  datetime.now(timezone.utc).date().isoformat(),
        "flags":       ["TECHPORT_SCRAPED_AUTHORITATIVE"],
        "tags":        ["techport", e.get("tradespace_role") or "primary"],
    }
    return record


def main(dry_run: bool, no_backup: bool) -> int:
    if not ENRICHED.exists():
        sys.exit(f"missing {ENRICHED} — run 03_enrich.py first")

    # Load enriched records
    print(f"Loading enriched records from {ENRICHED.relative_to(ROOT)}...")
    records: list[dict] = []
    with ENRICHED.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"  WARN bad JSON line: {e}", file=sys.stderr)

    print(f"  {len(records)} records loaded")

    # Convert
    converted = []
    skipped = 0
    for r in records:
        v = _build_viewer_record(r)
        if v is None:
            skipped += 1
            continue
        converted.append(v)

    print(f"  {len(converted)} converted to viewer schema")
    if skipped: print(f"  {skipped} skipped (no project_id)")

    # Distribution check
    from collections import Counter
    by_subsystem = Counter(r["subsystem"] for r in converted)
    by_category = Counter(r["category"] for r in converted)
    enriched_count = sum(1 for r in converted if r["applicable_subsystems"])
    req_tagged = sum(1 for r in converted if r["satisfies_requirements"])
    print(f"\n  By subsystem (ST): {dict(by_subsystem)}")
    print(f"  By category: {dict(by_category.most_common(10))}")
    print(f"  With applicable_subsystems tagged: {enriched_count}")
    print(f"  With REQ-SYS satisfied: {req_tagged}")

    if dry_run:
        print(f"\nDRY RUN — would have written {len(converted)} records to {TARGET.relative_to(ROOT)}")
        if converted:
            print(f"\nSample (first record):")
            print(json.dumps(converted[0], indent=2)[:1500])
        return 0

    # Backup current technologies.jsonl
    if TARGET.exists() and not no_backup and not LEGACY.exists():
        shutil.copy2(TARGET, LEGACY)
        print(f"\n  Backed up existing {TARGET.relative_to(ROOT)} -> {LEGACY.relative_to(ROOT)}")

    # Write the new master file
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    with TARGET.open("w", encoding="utf-8") as f:
        for r in sorted(converted, key=lambda x: x["id"]):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"  Wrote {len(converted)} records to {TARGET.relative_to(ROOT)}")
    print(f"\nDone. Hard-refresh the React viewer (Ctrl+Shift+R) to see all {len(converted)} entries.")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run",   action="store_true", help="show stats, don't overwrite technologies.jsonl")
    p.add_argument("--no-backup", action="store_true", help="don't backup existing technologies.jsonl")
    a = p.parse_args()
    sys.exit(main(a.dry_run, a.no_backup))
