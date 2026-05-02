# Seed Entries — Provenance Note

The first ~20 entries in `technologies.jsonl` are **hand-seeded anchors** to prove the schema works end-to-end and to give the team something concrete to filter, browse, and critique on day one. They are deliberately spread across two subsystems (Food Production + ECLSS) so the interface compatibility checker has cross-subsystem flows to reason over.

## Source posture

Each anchor entry cites:

1. A registered `SRC-NNN` source where one applies (BVAD has good data on most of these).
2. An external public URL or paper for facts not in the registry — flagged `EXTERNAL_PENDING_REGISTRATION`.
3. The flag `ENGINEERING_KNOWLEDGE_v0` for widely-known design parameters (e.g., "Veggie uses red and blue LEDs at ~150 µmol/m²/s") that future cycles should harden by registering a primary source.

**Per workflow_sop.md Rules 1 & 2:** an entry with `ENGINEERING_KNOWLEDGE_v0` flag is `DRAFT` only — it cannot move to `REVIEWED` until each fact has either a registered SRC-NNN or an external citation that the team accepts.

## What's NOT in the seed (deliberate omissions)

- **No nuclear power options yet** — Mars surface power is its own trade study; placeholder flow `electric_power_dc` is consumed but the producer side starts blank so the team has to populate it from their power baseline.
- **No structures / habitat envelope** — out of scope for v0; assumed given.
- **No ISRU water/oxygen extraction techs** — flagged as a top-priority gap so the team sees the empty box.

These are deliberate empty boxes. They will appear as **function gaps** in the first gap-finder run.

## Suggested next-pass priorities

1. ISRU water mining (bring in MOXIE-class architectures from JPL).
2. Power generation (solar arrays w/ dust mitigation, RPS / fission options).
3. Cellular-agriculture bioreactors (BioBead, Aleph Farms, Upside) — terrestrial heritage matters here.
4. Mycelium-based food production — leverage Air Force/DARPA studies.
5. Black soldier fly / insect protein — closes inedible-biomass loop, REQ-SYS-018 gives credit for "other organisms."
