#!/usr/bin/env python3
"""
techport_scraper.py — pull NASA TechPort projects, extract structured technology entries via Claude.

Pre-reqs:
  - ANTHROPIC_API_KEY in environment
  - pip install anthropic requests
  - Network access to api.techport.nasa.gov
    (currently blocked in the Cowork workspace; run from your local Python or unblock the
     domain in Settings -> Capabilities)

Usage:
  python techport_scraper.py --list-taxonomy             # list TX taxonomy IDs
  python techport_scraper.py --pull TX06                 # pull all TX06 projects
  python techport_scraper.py --pull TX06.04 --max 20     # limit
  python techport_scraper.py --extract raw/TX06_raw.json # run AI extraction on a raw dump

Outputs land under outputs/techport_pulls/ for human review BEFORE merging into
data/technologies.jsonl. Per workflow_sop.md Rule 6, agents may not self-approve;
a human must move reviewed entries into the master DB.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "outputs" / "techport_pulls" / "raw"
EXTRACT_DIR = ROOT / "outputs" / "techport_pulls" / "extracted"
SCHEMA_FILE = ROOT / "schema" / "technology_schema.json"

TECHPORT_BASE = "https://api.techport.nasa.gov/api"

EXTRACTION_PROMPT = """You are extracting structured technology entries for the Mars to Table trade space database.

You will receive a NASA TechPort project description. Extract a SINGLE JSON object conforming to the
technology_schema.json. Follow these rules absolutely:

1. NEVER invent numeric values. If mass/power/throughput is not stated in the source, set the
   relevant field's `status` to "TBR" and `value` to null. Do not guess.
2. Cite the TechPort URL in the `sources` array with flag "EXTERNAL_PENDING_REGISTRATION".
3. Use only flow_ids from the interface_ontology.md provided in context. If a flow doesn't fit any
   existing flow_id, set the flow_id to "NEEDS_NEW_FLOW_ID:<your_proposed_name>" and flag the entry.
4. Set `status` to "DRAFT".
5. Set `entered_by` to "techport_scraper.py".
6. Set `flags` to include "EXTERNAL_PENDING_REGISTRATION".
7. Map the project to which REQ-SYS IDs it could plausibly satisfy by reading the requirements_register.md
   that will be provided. Be conservative; better to miss a mapping than invent one.
8. Confidence: HIGH only if the source explicitly cites the value; MED if it's a published spec sheet
   number; LOW if it's an estimate or scaling.

Return ONLY the JSON object, no preamble or postamble. No code fences.
"""


def _require_requests():
    try:
        import requests  # noqa: F401
    except ImportError:
        sys.exit("install requests: pip install requests")


def _require_anthropic():
    try:
        import anthropic  # noqa: F401
    except ImportError:
        sys.exit("install anthropic: pip install anthropic")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("set ANTHROPIC_API_KEY environment variable")


def list_taxonomy():
    _require_requests()
    import requests
    r = requests.get(f"{TECHPORT_BASE}/taxonomy", timeout=30)
    r.raise_for_status()
    print(json.dumps(r.json(), indent=2))


def pull_taxonomy(tax_id: str, max_n: int = 100):
    _require_requests()
    import requests
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Querying TechPort for taxonomy {tax_id}...")
    r = requests.get(f"{TECHPORT_BASE}/projects?taxonomy={tax_id}", timeout=60)
    r.raise_for_status()
    project_ids = [p["projectId"] for p in r.json().get("projects", [])][:max_n]
    print(f"Found {len(project_ids)} projects; fetching details...")
    projects = []
    for i, pid in enumerate(project_ids, 1):
        try:
            d = requests.get(f"{TECHPORT_BASE}/projects/{pid}", timeout=30)
            d.raise_for_status()
            projects.append(d.json().get("project", {}))
            print(f"  [{i}/{len(project_ids)}] {pid}")
            time.sleep(0.3)  # be polite
        except Exception as e:
            print(f"  [{i}/{len(project_ids)}] {pid} — error: {e}")
    out = RAW_DIR / f"{tax_id}_raw.json"
    out.write_text(json.dumps(projects, indent=2))
    print(f"\nWrote {len(projects)} raw project records to {out}")


def extract_from_raw(raw_file: str):
    _require_anthropic()
    import anthropic
    client = anthropic.Anthropic()

    raw_path = Path(raw_file)
    projects = json.loads(raw_path.read_text())
    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)

    # Load context the model needs
    schema_md = (ROOT / "schema" / "technology_schema.md").read_text(encoding="utf-8")
    ontology_md = (ROOT / "schema" / "interface_ontology.md").read_text(encoding="utf-8")
    reqs_md = (ROOT.parent / "MarsToTable-main" / "MarsToTable-main"
               / "01_ST1_systems_conops" / "outputs" / "requirements_register.md").read_text(encoding="utf-8")

    out_path = EXTRACT_DIR / (raw_path.stem.replace("_raw", "") + "_extracted.jsonl")
    with out_path.open("w", encoding="utf-8") as out:
        for i, p in enumerate(projects, 1):
            description = json.dumps({
                "title": p.get("title"),
                "description": p.get("description"),
                "benefits": p.get("benefits"),
                "trl_current": p.get("currentTrl"),
                "url": f"https://techport.nasa.gov/projects/{p.get('projectId')}",
            }, indent=2)
            print(f"[{i}/{len(projects)}] extracting {p.get('title','?')[:60]}")
            try:
                resp = client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=4000,
                    system=EXTRACTION_PROMPT + "\n\n# SCHEMA\n" + schema_md
                                              + "\n\n# ONTOLOGY\n" + ontology_md[:8000]
                                              + "\n\n# REQUIREMENTS\n" + reqs_md[:12000],
                    messages=[{"role": "user", "content": description}],
                )
                txt = resp.content[0].text.strip()
                # Strip code fences if model added any
                if txt.startswith("```"):
                    txt = txt.split("```", 2)[1].lstrip("json").strip()
                obj = json.loads(txt)
                out.write(json.dumps(obj) + "\n")
            except Exception as e:
                print(f"  ERROR: {e}")
                continue
            time.sleep(0.5)
    print(f"\nWrote extracted JSONL to {out_path}")
    print("REVIEW BEFORE MERGING into data/technologies.jsonl (per workflow_sop.md Rule 6).")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list-taxonomy", action="store_true")
    ap.add_argument("--pull", help="taxonomy id, e.g. TX06 or TX06.04")
    ap.add_argument("--max", type=int, default=100)
    ap.add_argument("--extract", help="path to a raw JSON dump from --pull")
    args = ap.parse_args()

    if args.list_taxonomy: list_taxonomy()
    elif args.pull: pull_taxonomy(args.pull, args.max)
    elif args.extract: extract_from_raw(args.extract)
    else: ap.print_help()


if __name__ == "__main__":
    main()
