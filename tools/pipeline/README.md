# TechPort Research Pipeline

A five-stage, token-efficient research pipeline. Designed to replace the slow browser-driven scraping we did earlier with a clean separation between **fetching** (no LLM) and **reasoning** (LLM only on already-clean data).

## Why this exists

Scraping pages while the LLM is in the loop burns context on HTML chrome the model shouldn't see. This pipeline:

1. Fetches raw data via APIs first (no LLM)
2. Parses to a canonical schema with deterministic Python (no LLM)
3. Calls the LLM **only** for judgment fields (subsystem tagging, requirement mapping, novelty summaries)
4. Synthesizes reports from the enriched index, never the raw pages

Cost on a typical run: hundreds of records → a few cents to a few dollars in LLM tokens, vs. tens to hundreds of dollars if the LLM did the parsing.

## The five stages

```
1_sources/      ← what to fetch (taxonomies, project IDs)
   ↓ 01_fetch.py (httpx async, no LLM)
2_raw/          ← raw API JSON, never touched by LLM
   ↓ 02_parse.py (deterministic dict→record, no LLM)
3_parsed/       ← canonical records.jsonl
   ↓ 03_enrich.py (LLM, batched, structured output)
4_enriched/     ← + applicable_subsystems, satisfies_reqs, novelty
   ↓ 04_synth.py (LLM reasons over index, not raw)
5_synthesis/    ← gap reports, architecture recommendations
```

Each stage reads its predecessor's output and writes to its own folder. Re-running a stage doesn't re-run the others — fetched data stays fetched, enriched data stays enriched (unless prompt version changes).

## Quickstart (Windows, PowerShell)

```powershell
# 1. Install dependencies (one-time)
cd "C:\Users\18478\OneDrive - Northwestern University\Desktop\trade space explorer\05_trade_space_explorer\tools\pipeline"
pip install -r requirements.txt

# 2. Set your Anthropic API key (one-time per shell)
$env:ANTHROPIC_API_KEY = "sk-ant-..."

# 3. Run the four stages
python 01_fetch.py        # ~2 min for ~500 projects
python 02_parse.py        # <10 sec
python 03_enrich.py       # ~$1-3 for ~500 records
python 04_synth.py        # ~$0.05 per report

# Or chain them:
python 01_fetch.py; python 02_parse.py; python 03_enrich.py; python 04_synth.py
```

## Customizing what gets fetched

Edit `data/pipeline/1_sources/seeds.csv`. Add taxonomy IDs (the pipeline expands them to project lists via the TechPort API) or specific project IDs. Format:

```csv
type,id,description,priority
taxonomy,TX06.1.1,Atmosphere Revitalization,high
taxonomy,TX06.3.5,Food Production Processing Preservation,high
project,95135,Impure Water Electrolysis - manual add,medium
```

## Cost expectations

| Stage | Per ~500 records | Notes |
|---|---|---|
| 01_fetch | $0 | Pure HTTP, no LLM |
| 02_parse | $0 | Pure Python, no LLM |
| 03_enrich | $1–3 | Batched (~15 records/call), structured output |
| 04_synth | $0.05–0.50 per report | Reads enriched index, not raw |

Numbers assume Claude Sonnet pricing. For Haiku (cheaper, fine for tagging): divide by ~10.

## Customizing the prompts

Prompts live in `prompts/` as plain Markdown. Bump the `prompt_version` field at the top of each one when you edit — re-running `03_enrich.py` will then re-process records that have older versions. (Records with the current version are skipped, saving cost.)

## Files in this directory

| File | Purpose |
|---|---|
| `01_fetch.py` | Async fetch from TechPort API into `2_raw/` |
| `02_parse.py` | Deterministic parse into canonical `3_parsed/records.jsonl` |
| `03_enrich.py` | LLM-batched enrichment into `4_enriched/records_enriched.jsonl` |
| `04_synth.py` | LLM synthesis (gap reports, etc.) into `5_synthesis/` |
| `requirements.txt` | Python deps (`httpx`, `anthropic`) |
| `prompts/` | Editable prompt templates with version tags |
| `schemas/canonical_record.json` | JSON Schema for the canonical record |

## Re-running individual stages

| Goal | Command |
|---|---|
| Add new taxonomies | Edit seeds.csv, then `python 01_fetch.py` (skips already-fetched) |
| Tweak parser rules | `python 02_parse.py --force` (re-parses everything) |
| Bump enrichment prompt | Edit prompt, bump version, then `python 03_enrich.py` |
| Generate a new report | Edit prompt, then `python 04_synth.py --report gap` |

## When to scale up

This pipeline is sized for hundreds to low-thousands of records, files-as-database. When you exceed ~10K records or need scheduled crawls:
- Swap JSONL files for DuckDB or PostgreSQL
- Swap `httpx` loop for Scrapy with proper crawler infrastructure
- Add Prefect/Dagster for orchestration
- Add embeddings (FAISS/Qdrant) for semantic retrieval in synth stage

The pipeline shape stays the same — you just swap implementations.
