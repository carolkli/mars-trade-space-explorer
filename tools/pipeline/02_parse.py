#!/usr/bin/env python3
"""
02_parse.py — Stage 2 of the research pipeline.

Reads raw TechPort JSON files from data/pipeline/2_raw/ and writes a canonical
record per project to data/pipeline/3_parsed/records.jsonl. NO LLM.

Deterministic only: pulls fixed JSON paths into a fixed schema. If a field is
missing, it stays null and gets a warning. Citations point back to the JSON path
in the raw record so downstream stages can audit any claim.

Usage:
    python 02_parse.py                 # parse only un-parsed (by content_hash)
    python 02_parse.py --force         # re-parse everything
"""
from __future__ import annotations
import argparse, csv, json, re, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = ROOT / "data" / "pipeline" / "2_raw"
MANIFEST = RAW_DIR / "manifest.csv"
PARSED_DIR = ROOT / "data" / "pipeline" / "3_parsed"
RECORDS_FILE = PARSED_DIR / "records.jsonl"
PARSER_LOG = PARSED_DIR / "parser_log.csv"

PARSER_VERSION = "techport_v1.1"  # bumped: corrected field names to match actual TechPort API


def _get(d, *path, default=None):
    """Safely walk nested dict by key path."""
    cur = d
    for k in path:
        if not isinstance(cur, dict): return default
        cur = cur.get(k)
        if cur is None: return default
    return cur


def _safe_list(d, *path) -> list:
    v = _get(d, *path)
    return v if isinstance(v, list) else []


def _strip_html(s) -> str:
    """Remove HTML tags, normalize whitespace and entity escapes. TechPort wraps text in <p>."""
    if not s: return ""
    if not isinstance(s, str): s = str(s)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"</p\s*>", "\n\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<[^>]+>", "", s)
    # Common HTML entities
    s = (s.replace("&nbsp;", " ").replace("&amp;", "&")
           .replace("&lt;", "<").replace("&gt;", ">")
           .replace("&quot;", '"').replace("&#39;", "'"))
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _find_project(raw):
    """TechPort response shapes vary. Walk a few common locations to find the project payload."""
    if not isinstance(raw, dict):
        return None
    # Shape A: project data at top level (most common per API docs)
    if raw.get("projectId") or raw.get("title"):
        return raw
    # Shape B: nested under "project" key
    if isinstance(raw.get("project"), dict):
        return raw["project"]
    # Shape C: nested inside technologyOutcomes[0].project (you saw this shape)
    tos = raw.get("technologyOutcomes")
    if isinstance(tos, list) and tos and isinstance(tos[0], dict):
        if isinstance(tos[0].get("project"), dict):
            return tos[0]["project"]
    return None


def _extract_taxonomy(proj: dict) -> list[str]:
    """Pull taxonomy codes from any of the known shapes."""
    taxonomy: list[str] = []
    # Shape A: primaryTaxonomyNodes / taxonomyNodes — array of node objects
    for key in ("primaryTaxonomyNodes", "taxonomyNodes", "primaryTaxonomyTree"):
        for n in _safe_list(proj, key):
            if isinstance(n, dict):
                code = n.get("code") or n.get("acronym") or n.get("title") or n.get("name")
                if code: taxonomy.append(str(code))
    # Shape B: primaryTaxonomyName as a single string
    if not taxonomy:
        ptn = _get(proj, "primaryTaxonomyName") or _get(proj, "taxonomy")
        if ptn: taxonomy.append(str(ptn))
    # Dedupe preserving order
    seen, out = set(), []
    for t in taxonomy:
        if t not in seen:
            seen.add(t); out.append(t)
    return out


def parse_techport(raw: dict, manifest_row: dict) -> dict | None:
    """Convert TechPort API JSON into canonical record. Returns None on parse failure."""
    proj = _find_project(raw)
    if not proj:
        return None
    pid = str(_get(proj, "projectId") or _get(proj, "id") or manifest_row["project_id"])
    title = _get(proj, "title") or _get(proj, "name")
    if not title:
        return None

    # Tech maturity — actual TechPort API uses trlBegin/trlCurrent/trlEnd
    trl_start = _get(proj, "trlBegin") or _get(proj, "startTrl")
    trl_curr  = _get(proj, "trlCurrent") or _get(proj, "currentTrl")
    trl_end   = _get(proj, "trlEnd") or _get(proj, "endTrl")

    taxonomy = _extract_taxonomy(proj)

    # Dates — both raw ISO and human-readable string forms exist
    start = _get(proj, "startDate") or _get(proj, "startDateString")
    end = _get(proj, "endDate") or _get(proj, "endDateString")

    # Lead organization (often nested)
    lead_org = (_get(proj, "leadOrganization", "organizationName")
             or _get(proj, "leadOrganization", "name")
             or _get(proj, "leadOrganization"))
    if isinstance(lead_org, dict): lead_org = lead_org.get("name")

    # Program info nested under .program
    program = (_get(proj, "program", "title")
            or _get(proj, "program", "acronymOrTitle")
            or _get(proj, "responsibleProgram", "name")
            or _get(proj, "responsibleProgram"))
    if isinstance(program, dict): program = program.get("title")

    # Mission directorate nested under .program.responsibleMd
    directorate = (_get(proj, "program", "responsibleMd", "organizationName")
                or _get(proj, "responsibleMissionDirectorate", "name")
                or _get(proj, "responsibleMissionDirectorate"))
    if isinstance(directorate, dict): directorate = directorate.get("name")

    # Status field
    status = _get(proj, "status") or _get(proj, "projectStatus") or _get(proj, "releaseStatus")

    # Description and benefits — TechPort wraps these in <p>...</p> HTML
    description = _strip_html(_get(proj, "description") or "")
    benefits = _strip_html(_get(proj, "benefits") or _get(proj, "anticipatedBenefits") or "")

    # Target destinations — actual API field is destinationType (flat string array)
    targets = _safe_list(proj, "destinationType")
    if not targets:
        # Fallback to older shape: destinations = list of objects
        for d in _safe_list(proj, "destinations"):
            targets.append(d.get("name", "") if isinstance(d, dict) else str(d))
    targets = [str(t).replace("_", " ") for t in targets if t]

    return {
        "id": f"techport_{pid}",
        "source": {
            "url": manifest_row["url"],
            "fetched_at": manifest_row["fetched_at"],
            "raw_path": manifest_row["raw_path"],
            "content_hash": manifest_row["content_hash"],
            "parser_version": PARSER_VERSION,
            "parsed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        "structured": {
            "project_id": pid,
            "title": title,
            "description": description,
            "anticipated_benefits": benefits,
            "trl_start": trl_start,
            "trl_current": trl_curr,
            "trl_end_target": trl_end,
            "project_status": status,
            "start_date": start,
            "end_date": end,
            "lead_organization": lead_org,
            "responsible_program": program,
            "responsible_mission_directorate": directorate,
            "primary_taxonomy": taxonomy,
            "target_destinations": targets,
        },
        "citations": {
            # Field path inside the raw JSON — auditable
            "title": "project.title",
            "trl_current": "project.currentTrl",
            "description": "project.description",
            "anticipated_benefits": "project.benefits",
            "primary_taxonomy": "project.primaryTaxonomyNodes",
        },
    }


def _load_existing() -> dict[str, dict]:
    """Load existing parsed records keyed by id."""
    if not RECORDS_FILE.exists(): return {}
    out = {}
    with RECORDS_FILE.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            try:
                r = json.loads(line)
                out[r["id"]] = r
            except json.JSONDecodeError: continue
    return out


def _save(records: dict[str, dict]) -> None:
    PARSED_DIR.mkdir(parents=True, exist_ok=True)
    with RECORDS_FILE.open("w", encoding="utf-8") as f:
        for rid in sorted(records):
            f.write(json.dumps(records[rid], ensure_ascii=False) + "\n")


def _save_log(rows: list[dict]) -> None:
    fields = ["project_id", "raw_path", "status", "message", "ts"]
    with PARSER_LOG.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows: w.writerow({k: r.get(k, "") for k in fields})


def main(force: bool) -> int:
    if not MANIFEST.exists():
        sys.exit(f"missing {MANIFEST} — run 01_fetch.py first")
    manifest = list(csv.DictReader(MANIFEST.open(encoding="utf-8")))
    print(f"Pipeline 02_parse — {len(manifest)} raw records to consider")

    existing = _load_existing()
    log: list[dict] = []
    parsed = dict(existing)
    new_count = updated_count = skipped_count = failed_count = 0

    for row in manifest:
        rid = f"techport_{row['project_id']}"
        # Skip if already parsed at same content hash (idempotent)
        if not force and rid in existing:
            existing_hash = existing[rid].get("source", {}).get("content_hash")
            if existing_hash == row["content_hash"]:
                skipped_count += 1
                continue
            updated_count += 1
        raw_path = ROOT / row["raw_path"]
        if not raw_path.exists():
            log.append({"project_id": row["project_id"], "raw_path": row["raw_path"],
                        "status": "MISSING", "message": "raw file not found",
                        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds")})
            failed_count += 1
            continue
        try:
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            log.append({"project_id": row["project_id"], "raw_path": row["raw_path"],
                        "status": "BAD_JSON", "message": str(e),
                        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds")})
            failed_count += 1
            continue
        rec = parse_techport(raw, row)
        if rec is None:
            log.append({"project_id": row["project_id"], "raw_path": row["raw_path"],
                        "status": "NO_TITLE", "message": "no title found, skipped",
                        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds")})
            failed_count += 1
            continue
        parsed[rid] = rec
        if rid not in existing: new_count += 1

    _save(parsed)
    _save_log(log)
    print(f"  new:     {new_count}")
    print(f"  updated: {updated_count}")
    print(f"  skipped: {skipped_count}")
    print(f"  failed:  {failed_count} (see {PARSER_LOG.relative_to(ROOT)})")
    print(f"Total records in {RECORDS_FILE.relative_to(ROOT)}: {len(parsed)}")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--force", action="store_true", help="re-parse all even if cached")
    sys.exit(main(p.parse_args().force))
