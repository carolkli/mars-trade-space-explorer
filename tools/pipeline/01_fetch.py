#!/usr/bin/env python3
"""
01_fetch.py — Stage 1 of the research pipeline.

Strategy: TechPort's POST /api/projects/search returns FULL project records
(description, benefits, primaryTx, TRL, etc.) but ignores server-side filters.
So we paginate through ALL ~20K projects once, filter client-side by
primaryTx.code, and save each matching record as a raw JSON file. Plus we
fetch any explicitly-listed project IDs by direct GET.

Reads:  data/pipeline/1_sources/seeds.csv
Writes: data/pipeline/2_raw/techport_{id}.json + manifest.csv

Usage:
    python 01_fetch.py                    # default
    python 01_fetch.py --force            # overwrite existing
    python 01_fetch.py --max-pages 50     # cap pagination (debug)
    python 01_fetch.py --page-size 100    # records per search page
"""
from __future__ import annotations
import argparse, asyncio, csv, hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import httpx
except ImportError:
    sys.exit("Install: pip install -r requirements.txt")

ROOT = Path(__file__).resolve().parent.parent.parent
SOURCES = ROOT / "data" / "pipeline" / "1_sources" / "seeds.csv"
RAW_DIR = ROOT / "data" / "pipeline" / "2_raw"
MANIFEST = RAW_DIR / "manifest.csv"

API_BASE = "https://techport.nasa.gov/api"
RETRY_LIMIT = 3
RETRY_BACKOFF_S = 2.0
DEFAULT_PAGE_SIZE = 100
DEFAULT_MAX_PAGES = 250  # ~25k records max


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


async def _get_nonce(client: httpx.AsyncClient) -> str:
    """Fetch a fresh CSRF nonce from /api/nonce."""
    r = await client.get(f"{API_BASE}/nonce", timeout=15.0)
    return r.json()["nonce"]


async def _fetch_with_retry(client: httpx.AsyncClient, method: str, url: str, **kw) -> tuple[int, bytes]:
    for attempt in range(RETRY_LIMIT):
        try:
            r = await client.request(method, url, timeout=30.0, **kw)
            return r.status_code, r.content
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            if attempt == RETRY_LIMIT - 1:
                print(f"  GIVE UP after {RETRY_LIMIT} retries: {url} -> {e}", file=sys.stderr)
                return 0, b""
            await asyncio.sleep(RETRY_BACKOFF_S * (2 ** attempt))
    return 0, b""


async def _save_project_record(rec: dict, source_type: str, source_id: str,
                              manifest: dict[str, dict], force: bool) -> str:
    """Save a single project record as raw JSON. Skip if already cached unless --force."""
    pid = str(rec.get("projectId") or rec.get("id") or "")
    if not pid:
        return "  SKIP (no projectId)"
    if not force and pid in manifest:
        return f"  cached  {pid}"

    out_path = RAW_DIR / f"techport_{pid}.json"
    body = json.dumps(rec, ensure_ascii=False).encode("utf-8")
    out_path.write_bytes(body)

    primary_tx = ""
    if isinstance(rec.get("primaryTx"), dict):
        primary_tx = rec["primaryTx"].get("code") or ""

    manifest[pid] = {
        "project_id": pid,
        "url": f"{API_BASE}/projects/{pid}",
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "http_status": "200",
        "content_hash": _hash(body),
        "raw_path": str(out_path.relative_to(ROOT)),
        "source_type": source_type,
        "source_id": source_id,
        "primary_tx": primary_tx,
    }
    return f"  fetch   {pid} ({primary_tx or '(no tx)'})"


async def _fetch_individual(client: httpx.AsyncClient, pid: str, manifest: dict[str, dict],
                           force: bool, source_id: str) -> str:
    if not force and pid in manifest:
        return f"  cached  {pid}"
    url = f"{API_BASE}/projects/{pid}"
    status, body = await _fetch_with_retry(client, "GET", url)
    if status != 200 or not body:
        return f"  FAIL    {pid} (HTTP {status})"
    try:
        rec = json.loads(body)
    except json.JSONDecodeError:
        return f"  FAIL    {pid} (bad JSON)"
    # /api/projects/{id} may return {"project": {...}}; unwrap so the parser sees the same shape
    if isinstance(rec, dict) and "project" in rec and isinstance(rec["project"], dict):
        rec = rec["project"]
    return await _save_project_record(rec, "manual", source_id, manifest, force)


async def main(force: bool, max_pages: int, page_size: int) -> int:
    if not SOURCES.exists():
        sys.exit(f"missing {SOURCES} — copy from the README example")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest()
    pre_count = len(manifest)

    seeds = list(csv.DictReader(SOURCES.open(encoding="utf-8")))
    taxonomy_codes = {s["id"].strip() for s in seeds if s["type"].strip() == "taxonomy"}
    project_ids   = [s["id"].strip() for s in seeds if s["type"].strip() == "project"]

    print(f"Pipeline 01_fetch — {len(taxonomy_codes)} taxonomy filters, {len(project_ids)} explicit projects")
    print(f"  Taxonomy codes (will match primaryTx.code prefix): {sorted(taxonomy_codes)}")
    print(f"  Already cached: {pre_count}")

    headers = {"User-Agent": "mars-to-table-pipeline/0.2 (techport-research)"}
    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:

        # Stage A: paginated client-side filtering of /api/projects/search
        if taxonomy_codes:
            print(f"\nStage A: paginating /api/projects/search and filtering by primaryTx.code...")
            kept = 0
            scanned = 0
            offset = 0
            for page in range(max_pages):
                nonce = await _get_nonce(client)
                body = {"nonce": nonce, "offset": offset, "limit": page_size}
                status, raw = await _fetch_with_retry(
                    client, "POST", f"{API_BASE}/projects/search",
                    headers={"Content-Type": "application/json"},
                    json=body,  # httpx will serialize
                )
                if status != 200:
                    print(f"  page {page}: HTTP {status}, abort", file=sys.stderr)
                    break
                try:
                    j = json.loads(raw)
                except json.JSONDecodeError:
                    print(f"  page {page}: bad JSON, abort", file=sys.stderr)
                    break

                results = j.get("results", [])
                total   = j.get("total", j.get("totalRecords", 0))
                if not results:
                    print(f"  page {page}: empty, done.")
                    break

                # Filter client-side by primaryTx.code prefix match
                # e.g., seed "TX06.1.1" matches projects with code "TX06.1.1"
                # seed "TX06" matches all of TX06.*
                for rec in results:
                    scanned += 1
                    pt = rec.get("primaryTx") or {}
                    code = pt.get("code") or ""
                    if not code: continue
                    matched_seed = None
                    for seed_code in taxonomy_codes:
                        if code == seed_code or code.startswith(seed_code + ".") or code.startswith(seed_code):
                            matched_seed = seed_code
                            break
                    if not matched_seed: continue
                    print(await _save_project_record(rec, "taxonomy", matched_seed, manifest, force))
                    kept += 1

                print(f"  page {page+1}: scanned {len(results)} / total {total} (kept so far: {kept})")
                offset += page_size
                if offset >= total:
                    print(f"  reached end of results.")
                    break
                if scanned >= total:
                    break

        # Stage B: explicit project IDs (cheap, small list)
        if project_ids:
            print(f"\nStage B: fetching {len(project_ids)} explicit project IDs...")
            for pid in project_ids:
                print(await _fetch_individual(client, pid, manifest, force, pid))

    _save_manifest(manifest)
    new_count = len(manifest) - pre_count
    print(f"\nDone. Manifest now has {len(manifest)} projects ({new_count} new). Raw in {RAW_DIR.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--force", action="store_true", help="re-fetch even if cached")
    p.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES, help="search pagination cap")
    p.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE, help="records per search page")
    args = p.parse_args()
    sys.exit(asyncio.run(main(args.force, args.max_pages, args.page_size)))
