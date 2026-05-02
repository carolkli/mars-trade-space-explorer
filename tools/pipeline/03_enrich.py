#!/usr/bin/env python3
"""
03_enrich.py — Stage 3 of the research pipeline.

Reads canonical records from data/pipeline/3_parsed/records.jsonl and adds
LLM-derived judgment fields:
  - applicable_subsystems  (which Mars-to-Table subsystems this tech could fit)
  - satisfies_requirements (which REQ-SYS-NNN IDs it could help satisfy)
  - novelty_summary        (one-paragraph, paraphrased)
  - tradespace_role        (primary | alternative | redundancy_backup | bridge | transformational)

Batched: ~10 records per Anthropic API call. Idempotent: skips records whose
_enrichment.prompt_version matches the current version. Writes audit log of
every API call (model, input/output tokens, cost estimate).

Usage:
    python 03_enrich.py                    # only enrich missing/stale
    python 03_enrich.py --force            # re-enrich everything
    python 03_enrich.py --batch 5          # smaller batches (debug)
    python 03_enrich.py --model haiku      # cheaper model
    python 03_enrich.py --max 50           # cap API calls (dry-run-ish)
"""
from __future__ import annotations
import argparse, csv, json, os, sys, time
from datetime import datetime, timezone
from pathlib import Path

try:
    import anthropic
except ImportError:
    sys.exit("Install: pip install -r requirements.txt")

ROOT = Path(__file__).resolve().parent.parent.parent
PARSED = ROOT / "data" / "pipeline" / "3_parsed" / "records.jsonl"
ENRICHED_DIR = ROOT / "data" / "pipeline" / "4_enriched"
ENRICHED = ENRICHED_DIR / "records_enriched.jsonl"
AUDIT = ENRICHED_DIR / "enrichment_audit.csv"
PROMPTS = Path(__file__).parent / "prompts"
SUBSYSTEMS_FILE = ROOT / "data" / "subsystems.json"
REQS_FILE = ROOT / "data" / "requirements.json"

PROMPT_VERSION = "enrich_v1.0"
DEFAULT_MODEL = "claude-sonnet-4-6"
MODEL_ALIAS = {
    "sonnet": "claude-sonnet-4-6",
    "haiku":  "claude-haiku-4-5-20251001",
    "opus":   "claude-opus-4-6",
}
# Rough USD per million tokens (Sonnet pricing as anchor; bump for Opus, drop for Haiku)
COST_PER_M = {
    "claude-sonnet-4-6":         {"in": 3.0,  "out": 15.0},
    "claude-haiku-4-5-20251001": {"in": 0.25, "out": 1.25},
    "claude-opus-4-6":           {"in": 15.0, "out": 75.0},
}


def _load_jsonl(p: Path) -> list[dict]:
    if not p.exists(): return []
    return [json.loads(l) for l in p.open(encoding="utf-8") if l.strip()]


def _save_jsonl(p: Path, records: list[dict]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for r in records: f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _build_context() -> str:
    """One-time context the LLM needs: the subsystems list and the REQ-SYS shortlist."""
    ctx_parts = []
    if SUBSYSTEMS_FILE.exists():
        ss = json.loads(SUBSYSTEMS_FILE.read_text(encoding="utf-8"))
        lines = ["SUBSYSTEMS (use these exact IDs in `applicable_subsystems`):"]
        for s in ss.get("subsystems", []):
            lines.append(f"  - {s['id']}: {s.get('name','')} ({s.get('description','')[:80]})")
        ctx_parts.append("\n".join(lines))
    if REQS_FILE.exists():
        rq = json.loads(REQS_FILE.read_text(encoding="utf-8"))
        lines = ["REQUIREMENTS (use these exact IDs in `satisfies_requirements`, only those marked tech-satisfiable):"]
        for r in rq.get("requirements", []):
            if r.get("can_be_satisfied_by_tech", True):
                lines.append(f"  - {r['id']}: {r.get('short','')}")
        ctx_parts.append("\n".join(lines))
    return "\n\n".join(ctx_parts)


SYSTEM_PROMPT_TEMPLATE = """You are an enrichment agent for the Mars to Table trade space database.
For each input project record, produce JSON enrichment with these fields:

  applicable_subsystems: array of subsystem IDs this tech could fit (be GENEROUS — multi-use is the norm)
  satisfies_requirements: array of REQ-SYS-NNN IDs this tech could plausibly help satisfy
  novelty_summary: 1-2 sentence paraphrase of what's distinctive about this tech (no copyright reproduction)
  tradespace_role: one of [primary, alternative, redundancy_backup, bridge, transformational]
  _confidence: HIGH | MED | LOW for the overall enrichment

Reasoning rules:
- Multi-tag liberally in applicable_subsystems — if you're unsure, include it. Innovation lives in unexpected fits.
- For satisfies_requirements: only include IDs from the provided list. If a project has no clear fit (e.g., propulsion-only), return an empty array.
- novelty_summary: paraphrase, never quote. Focus on what's NEW relative to baseline approaches.
- tradespace_role:
  * primary = mature, default candidate for its subsystem
  * alternative = viable substitute with different trade-offs
  * redundancy_backup = lower throughput but adds resilience
  * bridge = plugs an interface gap, not a primary functional unit
  * transformational = low TRL but enables new architectures

Return STRICT JSON: {"results": [{...one object per input record...}]}.
Each result MUST include the input record's `id` field unchanged.

CONTEXT:
{context}
"""


def _enrich_batch(client: anthropic.Anthropic, model: str, records: list[dict], context: str) -> tuple[list[dict], dict]:
    """Send one batch to the LLM. Returns (enriched_results, usage_dict)."""
    # Build a tight per-record summary — only the fields the LLM needs for judgment
    user_payload = []
    for r in records:
        s = r.get("structured", {})
        user_payload.append({
            "id": r["id"],
            "title": s.get("title"),
            "description": (s.get("description") or "")[:1500],  # truncate to control tokens
            "anticipated_benefits": (s.get("anticipated_benefits") or "")[:800],
            "trl_current": s.get("trl_current"),
            "lead_organization": s.get("lead_organization"),
            "primary_taxonomy": s.get("primary_taxonomy"),
            "target_destinations": s.get("target_destinations"),
        })
    user_msg = "Enrich each of these records:\n" + json.dumps(user_payload, indent=2)

    resp = client.messages.create(
        model=model,
        max_tokens=4000,
        system=SYSTEM_PROMPT_TEMPLATE.replace("{context}", context),
        messages=[{"role": "user", "content": user_msg}],
    )
    txt = resp.content[0].text.strip()
    if txt.startswith("```"):
        txt = txt.split("```", 2)[1].lstrip("json").strip()
    try:
        parsed = json.loads(txt)
    except json.JSONDecodeError as e:
        # Fall back: try to recover by extracting the first {...} block
        import re
        m = re.search(r"\{[\s\S]*\}", txt)
        if not m: raise
        parsed = json.loads(m.group(0))
    results = parsed.get("results", parsed if isinstance(parsed, list) else [])
    usage = {
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
        "model": model,
    }
    return results, usage


def _audit(rows: list[dict]) -> None:
    fields = ["batch", "ts", "model", "input_tokens", "output_tokens", "est_cost_usd", "n_records", "ids"]
    write_header = not AUDIT.exists()
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if write_header: w.writeheader()
        for r in rows: w.writerow({k: r.get(k, "") for k in fields})


def main(force: bool, batch_size: int, model_alias: str, max_calls: int) -> int:
    if not PARSED.exists():
        sys.exit(f"missing {PARSED} — run 02_parse.py first")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("set ANTHROPIC_API_KEY environment variable")

    model = MODEL_ALIAS.get(model_alias, model_alias) or DEFAULT_MODEL
    rate = COST_PER_M.get(model, COST_PER_M[DEFAULT_MODEL])
    print(f"Pipeline 03_enrich — model={model}, batch={batch_size}, prompt={PROMPT_VERSION}")

    parsed = _load_jsonl(PARSED)
    enriched = {r["id"]: r for r in _load_jsonl(ENRICHED)}

    # Determine which records need enrichment
    todo = []
    for r in parsed:
        existing = enriched.get(r["id"])
        if not force and existing and existing.get("enriched", {}).get("_enrichment", {}).get("prompt_version") == PROMPT_VERSION:
            continue
        todo.append(r)
    print(f"  parsed: {len(parsed)}, already enriched at v{PROMPT_VERSION}: {len(parsed)-len(todo)}, to do: {len(todo)}")

    if not todo:
        print("Nothing to do. Exiting clean.")
        return 0

    client = anthropic.Anthropic()
    context = _build_context()
    audit_rows = []
    n_calls = 0
    t0 = time.time()

    for i in range(0, len(todo), batch_size):
        if max_calls and n_calls >= max_calls:
            print(f"  hit --max {max_calls}, stopping")
            break
        batch = todo[i : i + batch_size]
        n_calls += 1
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            results, usage = _enrich_batch(client, model, batch, context)
        except Exception as e:
            print(f"  batch {n_calls} ERROR: {e}", file=sys.stderr)
            continue
        cost = (usage["input_tokens"] * rate["in"] + usage["output_tokens"] * rate["out"]) / 1_000_000
        # Merge results back into the canonical records
        results_by_id = {res.get("id"): res for res in results if isinstance(res, dict)}
        merged = 0
        for orig in batch:
            rid = orig["id"]
            res = results_by_id.get(rid)
            if not res:
                print(f"  WARN no result for {rid}")
                continue
            # Strip id and any internal junk; everything else is enrichment payload
            payload = {k: v for k, v in res.items() if k != "id"}
            payload["_enrichment"] = {
                "model": usage["model"],
                "prompt_version": PROMPT_VERSION,
                "enriched_at": ts,
            }
            enriched_record = {**orig, "enriched": payload}
            enriched[rid] = enriched_record
            merged += 1
        audit_rows.append({
            "batch": n_calls, "ts": ts, "model": model,
            "input_tokens": usage["input_tokens"], "output_tokens": usage["output_tokens"],
            "est_cost_usd": f"{cost:.4f}", "n_records": merged,
            "ids": ",".join(r["id"] for r in batch),
        })
        print(f"  batch {n_calls}: {merged}/{len(batch)} merged, ${cost:.4f}, "
              f"in={usage['input_tokens']} out={usage['output_tokens']}")

    _save_jsonl(ENRICHED, [enriched[k] for k in sorted(enriched)])
    _audit(audit_rows)
    total_cost = sum(float(r["est_cost_usd"]) for r in audit_rows)
    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.0f}s. {n_calls} API calls, est total cost ${total_cost:.3f}.")
    print(f"Enriched records: {len(enriched)} -> {ENRICHED.relative_to(ROOT)}")
    print(f"Audit log:        {AUDIT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--force",  action="store_true", help="re-enrich even if at current prompt version")
    p.add_argument("--batch",  type=int, default=10, help="records per API call")
    p.add_argument("--model",  default="sonnet", help="sonnet|haiku|opus or full model id")
    p.add_argument("--max",    type=int, default=0, help="max API calls (0 = unlimited)")
    a = p.parse_args()
    sys.exit(main(a.force, a.batch, a.model, a.max))
