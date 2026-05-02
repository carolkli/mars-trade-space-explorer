#!/usr/bin/env python3
"""
01b_ntrs_fetch.py — Pull NASA Technical Reports Server (NTRS) citations.

Reads:  data/pipeline/1_sources/ntrs_queries.json
Writes: data/pipeline/2_raw/ntrs_{id}.json + appends to manifest.csv

Strategy: each "strategy" in the config has a list of search queries; we hit
NTRS POST /api/citations/search for each, dedupe by citation id, and save
each unique record as a raw JSON file. Subject-category and date filters are
applied at the API level so we only pull what's actually relevant — no PDF
downloads, metadata only (~2 KB per record).

Usage:
    python 01b_ntrs_fetch.py
    python 01b_ntrs_fetch.py --force            # overwrite cached records
    python 01b_ntrs_fetch.py --strategy food_approach_diversity   # one strategy only
    python 01b_ntrs_fetch.py --dry-run          # show what would be pulled
"""
from __future__ import annotations
import argparse, asyncio, csv, hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import httpx
except ImportError:
    sys.exit("Install: pip install httpx")

ROOT = Path(__file__).resolve().parent.parent.parent
QUERIES_FILE = ROOT / "data" / "pipeline" / "1_sources" / "ntrs_queries.json"
RAW_DIR      = ROOT / "data" / "pipeline" / "2_raw"
MANIFEST     = RAW_DIR / "manifest.csv"

API_BASE = "https://ntrs.nasa.gov/api"
RETRY_LIMIT = 3
RETRY_BACKOFF_S = 2.0


def _hash(b: bytes) -> str:
    return "sha256:" + hashlib.sha256(b).hexdigest()


def _load_manifest() -> dict[str, dict]:
    if not MANIFEST.exists(): return {}
    with MANIFEST.open(newline="", encoding="utf-8") as f:
        return {r["project_id"]: r for r in csv.DictReader(f)}


def _save_manifest(manifest: dict[str, dict]) -> None:
    fields = ["project_id", "url", "fetched_at", "http_status", "content_hash",
              "raw_path", "source_type", "source_id", "primary_tx"]
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in sorted(manifest.values(), key=lambda r: r["project_id"]):
            w.writerow({k: row.get(k, "") for k in fields})


async def _fetch_with_retry(client, method, url, **kw):
    for attempt in range(RETRY_LIMIT):
        try:
            r = await client.request(method, url, timeout=30.0, **kw)
            return r.status_code, r.content
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            if attempt == RETRY_LIMIT - 1:
                print(f"  GIVE UP: {url} -> {e}", file=sys.stderr)
                return 0, b""
            await asyncio.sleep(RETRY_BACKOFF_S * (2 ** attempt))
    return 0, b""


def _build_search_body(query: str, filters: dict, page_from: int, page_size: int) -> dict:
    """Build the NTRS search JSON body. The API accepts q + filters + page."""
    body = {
        "q": query,
        "page": {"size": page_size, "from": page_from},
    }
    f = {}
    if filters.get("subjectCategoryIds"):
        f["subjectCategoryIds"] = filters["subjectCategoryIds"]
    if filters.get("fromYear"):
        f["publishedYearRange"] = {"from": filters["fromYear"]}
    if filters.get("toYear"):
        f.setdefault("publishedYearRange", {})["to"] = filters["toYear"]
    if filters.get("documentTypes"):
        f["documentTypes"] = filters["documentTypes"]
    if f:
        body["filters"] = f
    return body


def _save_record(rec: dict, query_label: str, manifest: dict, force: bool) -> tuple[str, bool]:
    """Save one citation record. Returns (status_msg, was_new)."""
    cid = str(rec.get("id") or rec.get("citationId") or rec.get("publicId") or "")
    if not cid:
        return "  SKIP (no id)", False
    pid = f"ntrs_{cid}"  # namespaced to avoid colliding with techport ids
    if not force and pid in manifest:
        return f"  cached  {pid}", False

    out_path = RAW_DIR / f"{pid}.json"
    body = json.dumps(rec, ensure_ascii=False).encode("utf-8")
    out_path.write_bytes(body)

    # Subject categories — store first one as "primary_tx" equivalent
    primary = ""
    cats = rec.get("subjectCategories") or rec.get("subjects") or []
    if cats and isinstance(cats[0], dict):
        primary = cats[0].get("name") or str(cats[0].get("id", ""))
    elif cats:
        primary = str(cats[0])

    manifest[pid] = {
        "project_id":   pid,
        "url":          f"{API_BASE}/citations/{cid}",
        "fetched_at":   datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "http_status":  "200",
        "content_hash": _hash(body),
        "raw_path":     str(out_path.relative_to(ROOT)),
        "source_type":  "ntrs",
        "source_id":    query_label,
        "primary_tx":   primary,
    }
    title_short = (rec.get("title") or "")[:60]
    return f"  fetch   {pid}  {title_short!r}", True


async def _run_strategy(client, strategy: dict, manifest: dict, force: bool, dry_run: bool) -> tuple[int, int, int]:
    """Returns (queries_run, records_seen, records_new)."""
    name = strategy["name"]
    queries = strategy.get("queries", [])
    filters = strategy.get("filters", {})
    page_size = int(strategy.get("limit_per_query", 25))
    print(f"\n[strategy: {name}] {len(queries)} queries, limit={page_size} each, filters={filters}")

    seen = new = 0
    for q in queries:
        body = _build_search_body(q, filters, page_from=0, page_size=page_size)
        if dry_run:
            print(f"  [dry] would POST /citations/search  q={q!r}  filters={filters}")
            continue
        status, raw = await _fetch_with_retry(
            client, "POST", f"{API_BASE}/citations/search",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            content=json.dumps(body).encode("utf-8"),
        )
        if status != 200:
            print(f"  query {q!r}: HTTP {status}, skipping")
            continue
        try:
            j = json.loads(raw)
        except json.JSONDecodeError:
            print(f"  query {q!r}: bad JSON, skipping")
            continue
        results = j.get("results") or j.get("citations") or []
        print(f"  query {q!r:60} -> {len(results)} results")
        for r in results:
            seen += 1
            msg, was_new = _save_record(r, query_label=name, manifest=manifest, force=force)
            if was_new: new += 1
        # Be polite: NTRS doesn't publish a rate limit but 4 req/sec is friendly
        await asyncio.sleep(0.25)

    return len(queries), seen, new


async def main(force: bool, dry_run: bool, only_strategy: str | None) -> int:
    if not QUERIES_FILE.exists():
        sys.exit(f"missing {QUERIES_FILE} — see README for the schema")
    cfg = json.loads(QUERIES_FILE.read_text(encoding="utf-8"))
    strategies = cfg.get("strategies", [])
    if only_strategy:
        strategies = [s for s in strategies if s["name"] == only_strategy]
        if not strategies:
            sys.exit(f"no strategy named {only_strategy!r}")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest()
    pre_count = sum(1 for v in manifest.values() if v.get("source_type") == "ntrs")

    print(f"Pipeline 01b_ntrs_fetch — {len(strategies)} strategies, {pre_count} NTRS records already cached")
    headers = {"User-Agent": "mars-to-table-pipeline/0.3 (ntrs-research)"}
    total_queries = total_seen = total_new = 0

    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        for s in strategies:
            q, seen, new = await _run_strategy(client, s, manifest, force, dry_run)
            total_queries += q
            total_seen += seen
            total_new += new

    if not dry_run:
        _save_manifest(manifest)
    print(f"\nDone. Ran {total_queries} queries, saw {total_seen} records, added {total_new} new.")
    print(f"Raw NTRS records in {RAW_DIR.relative_to(ROOT)}")
    if total_new and not dry_run:
        print(f"\nNext steps:")
        print(f"  1. python 02_parse.py        # parse the new NTRS records into the canonical schema")
        print(f"  2. python 03_enrich.py       # LLM-tag the new records (~$0.01 per 25 records)")
        print(f"  3. python 05_merge.py        # rebuild data/technologies.jsonl")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--force",    action="store_true", help="re-fetch even if cached")
    p.add_argument("--dry-run",  action="store_true", help="show what would be pulled, don't write")
    p.add_argument("--strategy", help="run only the named strategy (default: run all)")
    a = p.parse_args()
    sys.exit(asyncio.run(main(a.force, a.dry_run, a.strategy)))
