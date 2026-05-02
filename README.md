# Mars Trade Space Explorer

A trade-space exploration toolkit for the **NASA Mars-to-Table Centennial Challenge** — designing a complete food system + ECLSS for a 15-person, 500-sol Mars surface mission.

This repo provides:

1. **A research pipeline** that pulls candidate technologies from NASA TechPort, parses them deterministically, and uses an LLM to tag each entry with applicable subsystems and the requirements it satisfies.
2. **An interactive viewer** for browsing, filtering, composing trial architectures, finding gaps, and tagging entries collaboratively.
3. **A schema** of 14 subsystems grouped into 4 domains (ECLSS, Food, Infrastructure, Crew) and 60 system-level requirements (REQ-SYS-001 through 060) for traceability.

The repo ships with **2,437 enriched TechPort entries** ready to browse — no scraping or LLM credits needed to get started.

## Quick start (5 minutes)

```bash
git clone https://github.com/<you>/mars-trade-space-explorer.git
cd mars-trade-space-explorer
python tools/tag_server.py
```

Then open one of:

- **http://127.0.0.1:8000/tools/browse.html** — fast vanilla-JS browser, instant load, inline tag editor
- **http://127.0.0.1:8000/tools/react_viewer.html** — full React viewer with architecture builder, flow analysis, gap report, scorecard, and CSV export

Edits made in either viewer are POSTed to `/api/save-tech` and persisted atomically to `data/technologies.jsonl` with daily backups in `data/_backups/`.

## What's where

```
data/
  technologies.jsonl         # main dataset (2,437 records, viewer reads this)
  technologies_legacy.jsonl  # original hand-curated entries (66, kept for reference)
  subsystems.json            # 14 subsystems x 4 groups, expected inputs/outputs
  requirements.json          # REQ-SYS-001 through 060
  pipeline/
    1_sources/seeds.csv      # taxonomy codes + project IDs to pull
    4_enriched/              # LLM-enriched records (source for the merge)
    5_synthesis/gap_report.md  # auto-generated gap analysis
schema/
  technology_schema.md       # full record schema
  interface_ontology.md      # flow / interface vocabulary
tools/
  browse.html                # vanilla-JS fast browser (recommended for daily use)
  react_viewer.html          # full React viewer (5 tabs)
  tag_server.py              # serves the viewers + persists tag edits
  pipeline/
    01_fetch.py              # pulls raw TechPort JSON
    02_parse.py              # deterministic field extraction (no LLM)
    03_enrich.py             # LLM tagging (Anthropic API)
    04_synth.py              # LLM gap synthesis
    05_merge.py              # converts enriched records to viewer schema
```

## Re-running the pipeline (optional)

The repo includes the final enriched output, so the viewer works out-of-the-box. To rerun the pipeline (e.g., to expand to new taxonomy codes or rerun enrichment with a newer model):

```bash
cd tools/pipeline
pip install -r requirements.txt
export ANTHROPIC_API_KEY="sk-ant-..."

python 01_fetch.py     # pulls raw TechPort JSON (paginates client-side, ~5 min)
python 02_parse.py     # deterministic structured extraction
python 03_enrich.py    # LLM enrichment (~$0.50-$1.00 with Sonnet for 2,500 records)
python 04_synth.py     # generates gap_report.md
python 05_merge.py     # writes data/technologies.jsonl
```

The fetch and parse stages cache to `data/pipeline/2_raw/` and `3_parsed/` (gitignored — regenerate locally).

## Key design choices

**Why client-side filtering on TechPort?** The `/api/projects/search` endpoint ignores server-side `taxonomyCodes` filters and returns all ~20,000 projects. Faster to paginate everything once and filter by `primaryTx.code` locally than to hit the per-project endpoint 2,500 times.

**Why a separate vanilla-JS browser?** The React viewer transpiles JSX in-browser via Babel-standalone, which adds 5-10s to cold-start. `browse.html` is for the 90% case (browse, search, tag) and loads instantly. Use the React viewer for architecture composition and flow analysis where the heavier UI is worth it.

**Why JSONL not SQLite?** Diffable in git, editable by hand, easy to merge across teammates' branches. The dataset is small enough (~6 MB) that a full in-memory load is fine.

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgments

- NASA TechPort for the source data
- Anthropic Claude for the enrichment + gap synthesis
- The Mars-to-Table Challenge for the problem
