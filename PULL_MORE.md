# How to expand the dataset

The bash sandbox can't reach NASA TechPort (network restrictions), so the fetch has to run on your local machine. The pipeline is already set up — this is a 3-step copy-paste.

## To pull TX06.3.* (human health) and TX06.5 (radiation)

The new taxonomy seeds are already added to `data/pipeline/1_sources/seeds.csv`. Just run:

```powershell
cd "C:\Users\18478\OneDrive - Northwestern University\Desktop\trade space explorer\05_trade_space_explorer\tools\pipeline"
python 01_fetch.py
python 02_parse.py
python 05_merge.py
```

What each step does:

1. **`01_fetch.py`** — paginates NASA TechPort, filters by primaryTx.code prefix, saves new raw JSON files under `data/pipeline/2_raw/`. The 2,437 already cached are skipped automatically. Expect ~5-10 minutes for the new pulls. Free, public API, no auth.
2. **`02_parse.py`** — extracts structured fields (title, TRL, taxonomy, dates, etc.) from the new raw files into `data/pipeline/3_parsed/records.jsonl`. Deterministic — no LLM, no API calls, takes seconds.
3. **`05_merge.py`** — rebuilds `data/technologies.jsonl` so the viewer picks up the new entries. The merge now backfills parsed-only records (without LLM tags) so they show up immediately. They'll appear with empty `applicable_subsystems` and `satisfies_requirements` — tag them by hand in the browser, or run `03_enrich.py` later if you want LLM tagging (not free).

After step 3, hard-refresh `http://127.0.0.1:8000/tools/browse.html` and you'll see the new entries — check the new categories appear in the pill bar.
