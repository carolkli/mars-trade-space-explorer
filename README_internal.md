# 05 — Trade Space Explorer

**Purpose.** A queryable, growable database of candidate technologies and an architecture-composition tool, so the Mars to Table team can sweep the design space, identify gaps, and justify subsystem selections traceably back to `REQ-SYS-001..060`.

**Relationship to the agent repo (`MarsToTable-main/`).** This folder is a *sibling* project for now (the "original prize"). It uses the same conventions — SRC-NNN source IDs, REQ-SYS-NNN traceability, the 8 SOP rules in `00_shared/sop/workflow_sop.md`, and the handoff schema in `00_shared/schemas/handoff_schema.md` — so when the team is ready, it can be lifted into the agent repo as `05_ST5_trade_space/` with no schema changes.

---

## What's in here

```
05_trade_space_explorer/
├── README.md                          ← you are here
├── schema/
│   ├── technology_schema.md           ← human-readable field spec
│   ├── technology_schema.json         ← JSON Schema (validation)
│   └── interface_ontology.md          ← controlled vocab for I/O flows
├── data/
│   ├── technologies.jsonl             ← master database (one tech per line)
│   └── seed_entries_README.md         ← provenance of the hand-seeded entries
├── tools/
│   ├── techport_scraper.py            ← pulls NASA TechPort + AI extraction
│   ├── compat_check.py                ← interface compatibility checker
│   ├── viewer.html                    ← single-file browser GUI (no install)
│   └── README.md                      ← how to run each tool
└── outputs/                           ← generated reports, gap analyses, Pareto
```

---

## How to use it (right now)

**To browse the database:** double-click `tools/viewer.html`. Filter by subsystem, category, TRL, or REQ-SYS satisfied. Click a row for the full record. Compose architectures by selecting one tech per function and watch the compatibility checks run live.

**To add a technology by hand:** open `data/technologies.jsonl`, append a new line as a single JSON object matching `schema/technology_schema.json`. Save. Reopen the viewer.

**To bulk-import from NASA TechPort:** see `tools/README.md`. The scraper pulls projects under TX06 (Human Health, Life Support, Habitation) and TX07 (Exploration Destination Systems), runs each description through Claude with a strict extraction prompt, and lands results in a review queue. Note: `api.techport.nasa.gov` is currently blocked by this workspace's allowlist — you can either run the script from your local Python (it just needs an Anthropic API key in `ANTHROPIC_API_KEY`), or add the domain in Settings → Capabilities.

**To check whether two architectures are compatible:** `python tools/compat_check.py --architecture path/to/arch.json`. Reports unmatched inputs, unconsumed outputs, and ESM totals.

---

## How AI gets used (six distinct jobs)

| # | Job | Tool / prompt | When |
|---|-----|---------------|------|
| 1 | **Decomposer** — propose function tree from rules | one-shot Claude call | Done (see schema/) |
| 2 | **Extractor** — TechPort/paper text → JSON entry | `tools/techport_scraper.py` | On scrape |
| 3 | **Ontology-keeper** — flag duplicate flow IDs / typos | `tools/compat_check.py --audit` | Weekly |
| 4 | **Gap-finder** — which functions / interfaces are bare | runs against full DB | Weekly / on demand |
| 5 | **Architecture composer** — natural-language → valid architectures | viewer.html "Ask Claude" panel | On demand |
| 6 | **Critic** — attack a proposed architecture | one-shot Claude call | Before any architecture leaves the team |

Job #6 is the one most teams skip. Don't.

---

## Source discipline (per workflow_sop.md Rule 1 + 2)

Every entry must trace claims to one of:

1. **Registered sources** in `MarsToTable-main/00_shared/source_registry.md` (SRC-001..006). Cite as `SRC-001, p.13`.
2. **External sources** that are *not yet* in the registry. Cite the URL/DOI and tag the entry with `flag: UNSOURCED`. The team should later register the source (assign next SRC-NNN) and re-cite.

Hand-seeded entries that draw on widely-known engineering knowledge are tagged `flag: ENGINEERING_KNOWLEDGE_v0` so they can be hardened later by sourcing.

---

## Status

This is the **v0 scaffold**. Schema is intentionally lean — extend by adding optional fields, not by changing required ones. The seeded entries (~15) span Food Production and ECLSS to prove the loop works end-to-end. Scaling to 200+ is a job for the TechPort scraper + a team-wide hand-entry sprint.

**Next milestones:**

1. Validate schema with the team (15-min review).
2. Run TechPort scraper on TX06.04 (Bioregenerative Food Production) — expected ~50–100 candidate entries.
3. Add patent / paper sources (Google Patents, Semantic Scholar) — same extractor, different parser.
4. Build the architecture composer's natural-language interface.
5. Promote into agent repo as `05_ST5_trade_space/` with handoff.md + agent prompt.
