# Technology Schema (v0)

This document defines the fields every entry in `data/technologies.jsonl` must have. The companion `technology_schema.json` is the machine-checkable JSON Schema; this doc is the human-readable spec with rationale.

**Why these fields:** every field maps to one or more requirements in `MarsToTable-main/01_ST1_systems_conops/outputs/requirements_register.md`. Field-to-REQ-SYS mapping is shown in the right column.

**Required vs. optional:** fields marked **REQUIRED** must be present in every entry. Fields marked *optional* should be filled when known — leave them out (or set to `null`) when not.

---

## Identity

| Field | Type | Required | Description | Maps to REQ |
|-------|------|----------|-------------|-------------|
| `id` | string `TECH-NNNN` | **REQUIRED** | Sequential ID, never reused. Reserve via `tools/next_id.py` if collisions risk. | — |
| `name` | string | **REQUIRED** | Common name. | — |
| `aliases` | string[] | optional | Other names this tech is known by. | — |
| `short_description` | string ≤200 chars | **REQUIRED** | One-sentence what-it-does. | — |
| `long_description` | string | optional | A paragraph. Used by the AI architecture composer for matching. | — |
| `category` | enum | **REQUIRED** | One of: `crop_production`, `microbial_production`, `cellular_agriculture`, `fungi_production`, `animal_production`, `food_processing`, `food_storage`, `food_prep`, `water_recovery`, `air_revitalization`, `waste_processing`, `thermal_control`, `power`, `isru`, `structures`, `monitoring_control`, `other`. | REQ-SYS-018 (variety) |
| `subsystem` | enum | **REQUIRED** | One of `ST1`, `ST2`, `ST3`, `ST4` per the agent repo decomposition. Multi-team techs list the primary owner. | — |
| `function_role` | string | **REQUIRED** | Free text: what function this serves. E.g. "convert CO2+H2O+light → leafy greens." | — |

---

## Requirements traceability

| Field | Type | Required | Description | Maps to REQ |
|-------|------|----------|-------------|-------------|
| `satisfies_requirements` | string[] | **REQUIRED** (≥1) | List of REQ-SYS IDs this tech could help satisfy. | — |
| `constrained_by_requirements` | string[] | optional | REQ-SYS IDs that constrain this tech (e.g. R009 gravity, R010 atmosphere). | — |
| `trace_notes` | string | optional | Free-text explanation of how this tech ties to the requirements. | — |

---

## Sources (per workflow_sop.md Rules 1 & 2)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `sources` | object[] | **REQUIRED** (≥1) | Each entry: `{source_id?, url?, title?, page?, excerpt?, flag?}`. `source_id` for registered sources (`SRC-001..006`). For external/unregistered sources, set `flag` to one of: `UNSOURCED` (no source yet), `EXTERNAL_PENDING_REGISTRATION` (URL/DOI provided, not yet in registry), `ENGINEERING_KNOWLEDGE_v0` (widely known engineering knowledge, needs sourcing later). |

---

## Inputs / outputs (machine-checkable interface flows)

This is the part that makes interface compatibility checks automatic. Every flow uses a `flow_id` from `schema/interface_ontology.md` — do not invent new flow IDs without adding them to that file.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `inputs` | object[] | **REQUIRED** | Each: `{flow_id, rate, units, conditions?, confidence, source_ref?}`. `confidence` is `HIGH|MED|LOW`. |
| `outputs` | object[] | **REQUIRED** | Same shape as inputs. For edible-biomass outputs, also include `nutrition_per_kg`: `{kcal, protein_g, carbs_g, fat_g, fiber_g, water_g, key_micros?: {vitamin_d_ug?, ...}}`. Maps to REQ-SYS-004, 006, 052. |

**Confidence guidance:**
- `HIGH`: rate measured in flight or BVAD-cited ground test
- `MED`: published in peer-reviewed paper or vendor spec sheet
- `LOW`: estimated, scaled, or back-of-envelope — must be flagged

---

## ESM components (REQ-SYS-055)

Every tech needs these for the equivalent system mass trade. Use BVAD equivalency factors when computing ESM totals.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `mass_kg` | object | **REQUIRED** | `{value, status: SOURCED|TBR|UNSOURCED, source_ref?}` |
| `volume_m3` | object | **REQUIRED** | same shape |
| `power_w` | object | **REQUIRED** | `{nominal, peak?, status, source_ref?}` |
| `cooling_w` | object | optional | Heat rejection load. Same shape as power. |
| `crew_time_hr_per_sol` | object | **REQUIRED** | `{nominal, peak?, status, source_ref?}` — gates REQ-SYS-013 (45-hr/wk budget) |
| `consumables` | object[] | optional | `[{flow_id, rate, units, source_ref?}]` |
| `throughput` | object | optional | `{value, units, source_ref?}` e.g. `{value: 0.5, units: "kg edible biomass / sol"}` |
| `efficiency` | object | optional | `{value: 0–1, definition, source_ref?}` |

---

## Maturity, risk, redundancy (REQ-SYS-016, 021, 060)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `trl` | object | **REQUIRED** | `{value: 1–9, date: YYYY-Q[1-4], source_ref}` |
| `heritage` | object[] | optional | `[{program, mission_or_facility, dates, role, source_ref?}]` |
| `failure_modes` | object[] | optional | `[{description, likelihood: HIGH|MED|LOW, severity: HIGH|MED|LOW, mitigation, source_ref?}]` |
| `single_points_of_failure` | bool | optional | True if this tech, if it fails, halts an entire crew-feeding capability. |
| `mtbf_hr` | number | optional | Mean time between failures in hours. |
| `recovery_time_hr` | number | optional | Time from failure to restored production. Gates REQ-SYS-060 contingency analysis. |

---

## Mars environmental compatibility (REQ-SYS-009/010/011)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `mars_gravity_compatible` | enum | **REQUIRED** | `TRUE | FALSE | TBR` — operates at 3.71 m/s² |
| `gravity_sensitivity_notes` | string | optional | E.g. "convection-driven cooling needs reorientation." |
| `habitat_atmosphere_compatible` | enum | **REQUIRED** | `TRUE | FALSE | TBR` — 8.2 psi (56.5 kPa), 34% O2 |
| `temperature_range_c` | [number, number] | **REQUIRED** | `[min, max]` — must include 18–27°C per REQ-SYS-011 |
| `radiation_sensitivity` | enum | optional | `NONE | LOW | MED | HIGH` |
| `dust_sensitivity` | enum | optional | `NONE | LOW | MED | HIGH` |

---

## Food-system specifics (when relevant)

| Field | Type | Required | Description | Maps |
|-------|------|----------|-------------|------|
| `food_safety_notes` | string | optional | Microbial control, allergens, etc. | REQ-SYS-022, 044 |
| `microbial_control_method` | string | optional | E.g. UV, HEPA, sealed photobioreactor. | REQ-SYS-044 |
| `gmp_compatibility` | enum | optional | `TRUE | FALSE | TBR | N/A` | REQ-SYS-047 |
| `hedonic_acceptability` | object | optional | `{score_estimated, scale: "1-9", source_ref?, notes}` Target ≥6.0. | REQ-SYS-030, 041 |
| `storage_stability_days` | object | optional | `{value, conditions, packaging, source_ref?}` | REQ-SYS-008, 058 |
| `preparation_method` | string | optional | E.g. "boil + season; reconstitute with potable water." | REQ-SYS-029 |

---

## System-level capabilities (the soft-link layer)

These fields exist so the gap-finder and architecture composer can identify connections that aren't visible from raw mass-flow inputs/outputs alone. A tech might "provide redundancy for the leafy-greens function" without producing any new flow — that belongs here.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `provides_benefits` | string[] | optional but encouraged | Free-form capability tags. Suggested: `fresh_food_morale`, `vitamin_d_source`, `vitamin_b12_source`, `complete_protein`, `graceful_degradation`, `crew_time_buffer`, `interface_simplifier`, `enables_loop_closure_water`, `enables_loop_closure_carbon`, `dust_tolerant`, `radiation_hardened`, `low_complexity`, `educational_value`, `cultural_familiarity`. |
| `requires_capabilities` | string[] | optional but encouraged | What the tech needs *beyond* its mass-flow inputs. Suggested: `daily_skilled_attention`, `weekly_maintenance`, `isru_water_access`, `sterile_environment`, `dust_isolation`, `vibration_isolation`, `gravity_orientation_specific`, `seed_resupply_from_earth`, `pharmaceutical_grade_inputs`, `cold_chain_storage`. |
| `bridges_to` | string[] | optional | List of `flow_id`s that this tech could plausibly accept as input *with modification* — used by the bridge-gap finder to suggest "what's almost-compatible." E.g., a UPA could `bridge_to: ["greywater"]` even though its primary input is `urine_pretreated`. |
| `displaces` | string[] | optional | List of TECH-IDs this is a substitute for, even partially. Used by the architecture composer to swap-and-compare. |

**Why these matter for gap-finding:**
- *Function gaps*: a function with no candidate ≥ TRL 4 — found by scanning `satisfies_requirements`.
- *Interface gaps (hard)*: a `flow_id` produced by some tech but consumed by none (or vice versa) — found from `inputs`/`outputs`.
- *Interface gaps (bridge)*: a `flow_id` *almost* matches between A's output and B's input via the `bridges_to` list — surfaces "we need a buffer / preconditioner / converter here." This is where innovation work clusters.
- *Capability gaps*: a `requires_capability` that no other tech `provides_benefits` — surfaces missing infrastructure.

---

## Closed-loop integration (REQ-SYS-012, 026, 056, 057)

These are derived from the inputs/outputs above but exposed as top-level for fast filtering.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `eclss_interfaces` | string[] | **REQUIRED** | Subset of `["air", "water", "waste", "thermal", "power", "crew", "monitoring"]` |
| `loop_closure_role` | enum | **REQUIRED** | `producer | consumer | both | neither` |
| `o2_balance_kg_per_sol` | number | optional | + = produces, − = consumes |
| `co2_balance_kg_per_sol` | number | optional | sign convention same |
| `water_balance_l_per_sol` | number | optional | sign convention same |
| `waste_streams` | object[] | optional | `[{flow_id, rate, units, disposition, source_ref?}]` |

---

## Governance

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `status` | enum | **REQUIRED** | `DRAFT | REVIEWED | APPROVED` — per Rule 6, agents may not self-approve. APPROVED requires human signoff. |
| `entered_by` | string | **REQUIRED** | Human or agent name. |
| `reviewed_by` | string | optional | Reviewer name. |
| `date_added` | string | **REQUIRED** | YYYY-MM-DD |
| `date_modified` | string | optional | YYYY-MM-DD |
| `flags` | string[] | optional | E.g. `["TBR-005", "TBD-012", "UNSOURCED-mass"]` |
| `notes` | string | optional | Free text. |

---

## Tags (for filtering and clustering)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `tags` | string[] | optional | Free-form. Suggested tags: `bioregenerative`, `physico-chemical`, `low-mass`, `high-trl`, `crew-time-light`, `power-hungry`, `requires-isru-water`, `flight-heritage`, `terrestrial-only`, `transformational`, etc. |

---

## Worked example

See `data/technologies.jsonl` line 1 (TECH-0001 — VEGGIE plant growth chamber) for a fully-populated reference entry.

---

## Versioning

This is **schema v0**. Breaking changes (renaming or removing required fields) require a schema bump and a one-time migration script in `tools/migrations/`. Adding new optional fields does not require a bump.
