#!/usr/bin/env python3
"""
tag_server.py — Drop-in replacement for `python -m http.server` that ALSO
accepts tagging updates from the React viewer.

Static file serving from the current directory (same as http.server) PLUS:
  POST /api/save-tech    body: {id, tags?, applicable_subsystems?, satisfies_requirements?, notes?}
                         updates the matching record in data/technologies.jsonl
                         returns: {ok: true, id, updated_fields: [...]}

Uses stdlib only — no Flask/FastAPI required.

Usage:
    cd "C:\\Users\\18478\\...\\05_trade_space_explorer"
    python tools\\tag_server.py            # serves on http://localhost:8000
    python tools\\tag_server.py --port 8001
"""
from __future__ import annotations
import argparse, json, os, shutil, sys, tempfile, time
from datetime import datetime, timezone
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # 05_trade_space_explorer/
DATA_FILE = ROOT / "data" / "technologies.jsonl"
BACKUP_DIR = ROOT / "data" / "_backups"

# Fields the React viewer is allowed to edit. Everything else stays as-is.
EDITABLE_FIELDS = {"tags", "applicable_subsystems", "satisfies_requirements", "notes", "status"}


def _load() -> list[dict]:
    if not DATA_FILE.exists(): return []
    out = []
    with DATA_FILE.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try: out.append(json.loads(line))
                except json.JSONDecodeError: pass
    return out


def _save_atomic(records: list[dict]) -> None:
    """Write atomically: temp file → fsync → rename. Daily backup before write."""
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(exist_ok=True)
    # One backup per day (avoid filling disk on every save)
    today = datetime.now().strftime("%Y%m%d")
    bk = BACKUP_DIR / f"technologies.{today}.jsonl"
    if DATA_FILE.exists() and not bk.exists():
        shutil.copy2(DATA_FILE, bk)

    fd, tmp_path = tempfile.mkstemp(dir=str(DATA_FILE.parent), prefix=".technologies.", suffix=".jsonl.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for r in sorted(records, key=lambda x: x.get("id", "")):
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, DATA_FILE)
    finally:
        if os.path.exists(tmp_path):
            try: os.unlink(tmp_path)
            except OSError: pass


class TaggingHandler(SimpleHTTPRequestHandler):
    """Static file server + tagging endpoint."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        # Discourage browser caching so JSONL edits show up on reload
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        if self.path.rstrip("/") != "/api/save-tech":
            self.send_error(404, "unknown endpoint")
            return
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length > 1_000_000:
            self.send_error(413, "payload too large")
            return
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            self._json(400, {"ok": False, "error": f"bad JSON: {e}"})
            return

        rid = body.get("id")
        if not rid:
            self._json(400, {"ok": False, "error": "missing 'id'"})
            return

        # Load DB, find record, apply allowed updates
        records = _load()
        match = None
        for r in records:
            if r.get("id") == rid:
                match = r
                break
        if not match:
            self._json(404, {"ok": False, "error": f"id not found: {rid}"})
            return

        updated = []
        for k, v in body.items():
            if k == "id": continue
            if k not in EDITABLE_FIELDS:
                continue  # silently ignore non-editable fields
            # Normalize lists: trim strings, drop empties, dedupe
            if isinstance(v, list):
                v = [str(x).strip() for x in v if str(x).strip()]
                seen, dedup = set(), []
                for x in v:
                    if x not in seen: seen.add(x); dedup.append(x)
                v = dedup
            elif isinstance(v, str):
                v = v.strip()
            match[k] = v
            updated.append(k)

        # Stamp the edit
        match["_edited"] = {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "fields": updated,
        }

        try:
            _save_atomic(records)
        except Exception as e:
            self._json(500, {"ok": False, "error": f"save failed: {e}"})
            return

        self._json(200, {"ok": True, "id": rid, "updated_fields": updated})

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        # Quieter than default (skip the timestamp prefix)
        sys.stderr.write(f"  {self.address_string()} {fmt % args}\n")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--bind", default="127.0.0.1")
    a = p.parse_args()

    if not DATA_FILE.exists():
        print(f"WARN: {DATA_FILE} does not exist yet — tagging will fail until you create it.", file=sys.stderr)

    server = HTTPServer((a.bind, a.port), TaggingHandler)
    url = f"http://{a.bind}:{a.port}/tools/react_viewer.html"
    print(f"Tag server up at http://{a.bind}:{a.port}/")
    print(f"  Open: {url}")
    print(f"  Editable fields: {sorted(EDITABLE_FIELDS)}")
    print(f"  Backups daily to: {BACKUP_DIR.relative_to(ROOT)}/")
    print(f"  Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
