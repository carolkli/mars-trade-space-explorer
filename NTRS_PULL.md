# Pulling from NASA Technical Reports Server (NTRS)

NTRS is NASA's archive of technical reports, conference papers, and journal articles — 500K+ citations, deep coverage of life-support and bioregenerative-food research that TechPort underrepresents.

## What's already configured

`data/pipeline/1_sources/ntrs_queries.json` defines **5 search strategies** targeting the gaps in your current 3,069 TechPort entries:

| Strategy | Target | Queries | Est. yield |
|---|---|---|---|
| `food_approach_diversity` | algae, spirulina, insect, mushroom, vertical farming (you have 0-2 of each) | 8 | ~150-200 records |
| `plant_systems_heritage` | Veggie/APH/BIOS-3/MELISSA/CELSS heritage | 9 | ~200 records |
| `eclss_loop_closure` | atmosphere, water, urine, Sabatier, waste | 7 | ~140 records |
| `isru_food_water` | regolith food, perchlorate, Mars water | 6 | ~120 records |
| `trl_and_lessons_learned` | ISS/Mir/Skylab heritage + nutrition | 6 | ~120 records |

Total estimated: ~700-900 NTRS citations after dedup. Edit the JSON file to add more queries or change subject-category filters before running.

## How to run

The bash sandbox can't reach NTRS, so this runs on your Windows machine:

```powershell
cd "C:\Users\18478\OneDrive - Northwestern University\Desktop\trade space explorer\05_trade_space_explorer\tools\pipeline"

# 1. Pull from NTRS (~5-10 min, free, public API)
python 01b_ntrs_fetch.py

# 2. Parse the new NTRS records into the canonical schema (~10 sec, no LLM)
python 02_parse.py

# 3. (optional) Tag with LLM (~$0.30 for ~800 records)
$env:ANTHROPIC_API_KEY = "sk-ant-..."
python 03_enrich.py

# 4. Rebuild the viewer dataset
python 05_merge.py
```

After step 4, hard-refresh `browse.html` — NTRS records appear with `ntrs_NNNN` IDs and link out to https://ntrs.nasa.gov/citations/{id}.

## Useful flags

```powershell
python 01b_ntrs_fetch.py --dry-run              # show what would be pulled, no writes
python 01b_ntrs_fetch.py --strategy food_approach_diversity  # one strategy at a time
python 01b_ntrs_fetch.py --force                # re-fetch even if cached
```

## How to extend the queries

Open `data/pipeline/1_sources/ntrs_queries.json`. Each strategy is a JSON object with:

- `name` — unique identifier
- `queries` — list of search strings (sent to NTRS as `q` parameter)
- `filters.subjectCategoryIds` — NASA STI subject codes to filter at the source
  - 51 = Life Sciences (General)
  - 54 = Man/System Tech & Life Support
  - 91 = Lunar/Planetary Science & Exploration
  - 12 = Astronautics (General)
- `filters.fromYear` — only papers from this year onward
- `limit_per_query` — max results per query (NTRS pages cap at 100)

Add a new strategy by appending to the `strategies` array. Re-run `01b_ntrs_fetch.py` — anything cached is skipped.

## Why this is efficient

- **No PDF downloads** — metadata only, ~2 KB per record vs ~5 MB for full text
- **Source-side filtering** — subject categories applied at the API, so we never download irrelevant records
- **Idempotent caching** — re-running skips already-fetched records (matched by NTRS id)
- **Targeted searches** — designed to fill specific gaps in your TechPort dataset, not bulk-scrape
