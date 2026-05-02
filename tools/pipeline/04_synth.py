#!/usr/bin/env python3
"""
04_synth.py — Stage 4 of the research pipeline.

Reads enriched records from data/pipeline/4_enriched/records_enriched.jsonl,
pre-computes summary tables in Python (REQ-SYS coverage, subsystem distribution,
TRL distribution), and asks the LLM to produce synthesis reports.

The LLM never reads raw page text. It reads:
  - Pre-computed Python summaries (cheap)
  - A tight per-record index (id + title + 1-line novelty + tags)
  - For deep questions, RAG-style: it requests specific record IDs.

Usage:
    python 04_synth.py                    # default: gap_report
    python 04_synth.py --report gap       # gap report
    python 04_synth.py --report coverage  # REQ-SYS coverage report
    python 04_synth.py --report all       # generate all reports
    python 04_synth.py --model haiku
"""
from __future__ import annotations
import argparse, csv, json, os, sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    import anthropic
except ImportError:
    sys.exit("Install: pip install -r requirements.txt")

ROOT = Path(__file__).resolve().parent.parent.parent
ENRICHED = ROOT / "data" / "pipeline" / "4_enriched" / "records_enriched.jsonl"
SYNTH_DIR = ROOT / "data" / "pipeline" / "5_synthesis"
REQS_FILE = ROOT / "data" / "requirements.json"
SUBSYSTEMS_FILE = ROOT / "data" / "subsystems.json"

DEFAULT_MODEL = "claude-sonnet-4-6"
MODEL_ALIAS = {
    "sonnet": "claude-sonnet-4-6",
    "haiku":  "claude-haiku-4-5-20251001",
    "opus":   "claude-opus-4-6",
}


def _load_records() -> list[dict]:
    if not ENRICHED.exists():
        sys.exit(f"missing {ENRICHED} — run 03_enrich.py first")
    return [json.loads(l) for l in ENRICHED.open(encoding="utf-8") if l.strip()]


def _build_index(records: list[dict]) -> list[dict]:
    """Tight per-record summary — what the LLM sees by default."""
    idx = []
    for r in records:
        s = r.get("structured", {})
        e = r.get("enriched", {})
        idx.append({
            "id": r["id"],
            "title": s.get("title"),
            "trl": s.get("trl_current"),
            "status": s.get("project_status"),
            "lead_org": s.get("lead_organization"),
            "applicable_subsystems": e.get("applicable_subsystems", []),
            "satisfies_requirements": e.get("satisfies_requirements", []),
            "tradespace_role": e.get("tradespace_role"),
            "novelty": e.get("novelty_summary", "")[:200],
        })
    return idx


def _coverage_table(records: list[dict]) -> dict:
    """Pre-compute REQ-SYS coverage table in Python (no LLM tokens)."""
    if not REQS_FILE.exists(): return {}
    reqs = json.loads(REQS_FILE.read_text(encoding="utf-8"))
    all_reqs = [r["id"] for r in reqs.get("requirements", [])]
    coverage = {rid: [] for rid in all_reqs}
    for r in records:
        for satisfied in r.get("enriched", {}).get("satisfies_requirements", []):
            if satisfied in coverage:
                coverage[satisfied].append(r["id"])
    return {
        "total_reqs": len(all_reqs),
        "covered_reqs": sum(1 for k in coverage if coverage[k]),
        "uncovered_reqs": [k for k in coverage if not coverage[k]],
        "best_covered": sorted(coverage.items(), key=lambda kv: -len(kv[1]))[:10],
    }


def _subsystem_counts(records: list[dict]) -> dict:
    cnt = Counter()
    for r in records:
        for s in r.get("enriched", {}).get("applicable_subsystems", []):
            cnt[s] += 1
    return dict(cnt.most_common())


def _trl_distribution(records: list[dict]) -> dict:
    cnt = Counter()
    for r in records:
        v = r.get("structured", {}).get("trl_current")
        if isinstance(v, (int, float)): cnt[int(v)] += 1
    return dict(sorted(cnt.items()))


def _ask(client: anthropic.Anthropic, model: str, system: str, user: str, max_tokens: int = 4000) -> str:
    resp = client.messages.create(
        model=model, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": user}],
    )
    return resp.content[0].text.strip(), resp.usage.input_tokens, resp.usage.output_tokens


def report_gap(client, model, records) -> str:
    cov = _coverage_table(records)
    ssc = _subsystem_counts(records)
    trl = _trl_distribution(records)
    idx = _build_index(records)
    system = """You are a NASA-style systems engineering reviewer for a Mars-to-Table trade study.
Identify gaps in the technology database: requirements with no candidates, subsystems with sparse coverage,
TRL gaps, and architectural single-points-of-failure. Use ONLY the provided index — do not invent records.

Output a concise markdown gap report (under 1500 words) with sections:
1. Coverage summary
2. Function gaps (REQ-SYS with no candidate tech)
3. Subsystem gaps (subsystems with <2 candidates)
4. TRL gaps (subsystems with no high-TRL options)
5. Innovation opportunities (where a bridge tech would unlock new architectures)
"""
    user = f"""# Pre-computed summaries

## REQ-SYS coverage
- {cov['covered_reqs']}/{cov['total_reqs']} requirements have at least one candidate tech
- Uncovered: {cov['uncovered_reqs'][:30]}{'...' if len(cov['uncovered_reqs'])>30 else ''}
- Best-covered: {[(k, len(v)) for k,v in cov['best_covered']]}

## Subsystem candidate counts
{json.dumps(ssc, indent=2)}

## TRL distribution
{json.dumps(trl, indent=2)}

## Index ({len(idx)} records, lightweight summaries)
{json.dumps(idx, indent=2, ensure_ascii=False)}
"""
    out, in_tok, out_tok = _ask(client, model, system, user)
    return out, in_tok, out_tok


def report_coverage(client, model, records) -> str:
    cov = _coverage_table(records)
    system = """You are summarizing REQ-SYS coverage for the Mars-to-Table team.
Produce a concise markdown report (under 1000 words) with:
1. Headline numbers (X/60 covered, distribution)
2. Top-5 best-covered REQ-SYS with candidate counts
3. Bottom-15 uncovered requirements grouped by category
4. Recommendations for which uncovered REQs to prioritize next
"""
    user = f"Coverage data:\n{json.dumps(cov, indent=2)}"
    out, in_tok, out_tok = _ask(client, model, system, user, max_tokens=2000)
    return out, in_tok, out_tok


REPORTS = {
    "gap": ("gap_report.md", report_gap),
    "coverage": ("coverage_report.md", report_coverage),
}


def main(report: str, model_alias: str) -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("set ANTHROPIC_API_KEY environment variable")
    model = MODEL_ALIAS.get(model_alias, model_alias) or DEFAULT_MODEL

    records = _load_records()
    print(f"Pipeline 04_synth — {len(records)} enriched records loaded")
    SYNTH_DIR.mkdir(parents=True, exist_ok=True)

    targets = list(REPORTS.keys()) if report == "all" else [report]
    for tgt in targets:
        if tgt not in REPORTS:
            print(f"  unknown report '{tgt}' (options: {list(REPORTS)} or 'all')")
            continue
        filename, fn = REPORTS[tgt]
        print(f"  generating {tgt} -> {filename}...")
        try:
            client = anthropic.Anthropic()
            text, in_tok, out_tok = fn(client, model, records)
            out_path = SYNTH_DIR / filename
            ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
            header = f"<!-- generated by 04_synth.py at {ts} using {model} -->\n<!-- input_tokens={in_tok} output_tokens={out_tok} -->\n\n"
            out_path.write_text(header + text, encoding="utf-8")
            print(f"    wrote {out_path.relative_to(ROOT)} ({in_tok} in, {out_tok} out tokens)")
        except Exception as e:
            print(f"    ERROR generating {tgt}: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--report", default="gap", help="gap | coverage | all")
    p.add_argument("--model",  default="sonnet")
    a = p.parse_args()
    sys.exit(main(a.report, a.model))
