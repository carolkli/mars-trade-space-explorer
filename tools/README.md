# Tools

## react_viewer.html (recommended)

Five-tab React app — Architecture Builder, Spreadsheet, Flows & Integration, Compare, Scorecard. Open in any modern browser. Same data sources as `viewer.html` (`data/technologies.jsonl` + `data/subsystems.json`) plus `data/requirements.json` for the REQ-SYS coverage scorecard.

**To open:**
- *With auto-load (recommended):* `python -m http.server 8000` from the `05_trade_space_explorer/` root, then open `http://localhost:8000/tools/react_viewer.html`. The app fetches all three data files on load.
- *Without a server:* double-click `react_viewer.html` and use the three Load buttons to pick the files manually from `data/`. Browsers block file:// → file:// fetch by default, so this is the workaround.

**The five tabs:**

| Tab | What it does |
|---|---|
| **Architecture Builder** | Subsystem grid grouped by ECLSS / Food / Infra / Crew. Pick one or more techs per subsystem (parallel selection allowed for redundancy). Live SCALE / TRL / NET BALANCES totals at the top. Header has Suggest buttons (High-TRL, Low-Mass, Low-Power, Bioregen) that auto-fill an architecture in one click. |
| **Spreadsheet** | Excel-like sortable / filterable table of every tech in the DB. Search box, category filter, TRL filter, sort by any column, export filtered set as CSV. |
| **Flows & Integration** | Flow-by-flow integration matrix for the current architecture. Green = balanced, Red = deficit, Yellow = surplus, Blue = orphan/bridge. Bridge slots panel below lists every empty box that needs a tech. |
| **Compare** | Pick up to 4 saved architectures and view their metrics side-by-side. |
| **Scorecard** | System totals (mass, vol, power, ESM, energy waste = heat reject load, man-hours, TRL stats), and a per-REQ-SYS coverage check across all 60 requirements grouped into 14 categories. ✓ green = at least one selected tech satisfies it; ✗ red = unsatisfied tech-satisfiable; ◯ gray = administrative/documentation requirement that won't be satisfied by a tech. |

**Saving architectures:** the Save button stores the current selections (with name) to your browser's localStorage. They survive page reloads on the same browser. Use the Compare tab to load 2-4 of them and contrast.

---

## viewer.html (legacy single-file)

Single-file HTML browser for the technology database. Open in any modern browser.

**Quickest path:** double-click `viewer.html`, then click "Load technologies.jsonl" and pick `data/technologies.jsonl`. Browsers block file:// → file:// fetch by default, so the file picker is the simplest way.

**With a local server (auto-load works):**

```bash
cd 05_trade_space_explorer
python -m http.server 8000
# then open http://localhost:8000/tools/viewer.html
```

The viewer has four panels: **Gaps** (default — function/interface/bridge gaps), **Browse** (filterable table), **Compose** (architecture builder with live mass balance), **Requirements coverage** (REQ-SYS-001..060 → satisfying techs).

---

## compat_check.py

Command-line gap finder + architecture compatibility checker. No external Python dependencies.

```bash
python tools/compat_check.py                       # short summary
python tools/compat_check.py --gap-report          # full markdown report → outputs/gap_report.md
python tools/compat_check.py --audit               # check for stray flow_ids
python tools/compat_check.py --architecture path/to/arch.json
```

`arch.json` is just a list of TECH-IDs:

```json
["TECH-0001", "TECH-0002", "TECH-0011", "TECH-0012", "TECH-0013", "TECH-0014", "TECH-0015"]
```

Output gives ESM totals (mass, volume, power, crew time) and a per-flow mass balance — negative numbers = unmet demand, positive = surplus.

---

## techport_scraper.py

Pulls NASA TechPort projects and uses Claude to extract structured entries matching the schema. Outputs go to `outputs/techport_pulls/extracted/` for **human review before merging** — per `workflow_sop.md` Rule 6, no self-approval.

**Pre-requisites:**

```bash
pip install anthropic requests
export ANTHROPIC_API_KEY="sk-ant-..."   # or set in your shell profile
```

**Network:** `api.techport.nasa.gov` is currently blocked in the Cowork workspace allowlist. Either run this script from your own laptop's Python, or unblock the domain in Settings → Capabilities.

**Recommended first run** — get the Bioregenerative Food Production taxonomy:

```bash
python tools/techport_scraper.py --list-taxonomy            # find the right TX id
python tools/techport_scraper.py --pull TX06.04 --max 30    # ~30 projects
python tools/techport_scraper.py --extract outputs/techport_pulls/raw/TX06.04_raw.json
```

Then review the resulting JSONL by hand and append valid entries to `data/technologies.jsonl`.

---

## What's not built yet (v0 backlog)

- **Pareto explorer** — once 100+ techs land, generate ~1000 valid architectures and plot them on (mass, power, crew_time, TRL) axes.
- **Natural-language architecture composer** — "build me three low-mass architectures using only TRL ≥ 6" via Claude API call from the viewer.
- **Critic agent** — given an architecture, attack it from a NASA-reviewer perspective.
- **JSON Schema validator** — `tools/validate.py` to run before merging extracted entries.
- **Diff/promote tool** — promote DRAFT → REVIEWED → APPROVED with audit log.
