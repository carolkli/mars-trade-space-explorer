# Interface Ontology (v0)

Controlled vocabulary for the `flow_id` field used in every entry's `inputs` and `outputs`. **Do not invent new flow IDs without adding them here.** Compatibility checks rely on exact-match string equality — `co2_gas` and `CO2_gas` are different to the checker.

---

## Conventions

- All lowercase, snake_case.
- Suffix indicates phase: `_gas`, `_liquid`, `_solid`, `_slurry`, `_vapor`, `_powder`, `_pellet`.
- Suffix `_kcal` for energy-content-bearing food items.
- Use SI units in the `units` field (`kg/sol`, `L/sol`, `W`, `kJ/sol`, `m3/sol`).
- For temperatures use `_warm` / `_chilled` / `_hot` suffixes if a temperature class matters for compatibility (e.g., warm air for greenhouse vs. chilled for storage).

---

## Atmosphere (gas-phase)

| flow_id | Definition | Typical units | Notes |
|---------|------------|---------------|-------|
| `air_habitat` | 8.2 psi cabin air, 34% O2, balance N2, ~50% RH | kg/sol or m3/sol | Per REQ-SYS-010 |
| `co2_gas` | Carbon dioxide gas | kg/sol | |
| `o2_gas` | Oxygen gas | kg/sol | |
| `n2_gas` | Nitrogen gas | kg/sol | |
| `h2_gas` | Hydrogen gas | kg/sol | Sabatier feed; off-gas of some bioreactors |
| `ch4_gas` | Methane | kg/sol | Sabatier product; vented or used |
| `humid_air_warm` | Warm humid air, ≥800 ppm CO2 | m3/sol | Greenhouse exhaust |
| `vented_gas` | Generic to-vent stream | kg/sol | Sink — anything dumped overboard |
| `ethylene_gas` | C2H4 | g/sol | Plant ripening signal; also off-gas |
| `voc_trace` | Volatile organic compounds, trace contaminants | mg/sol | Routes to TCCS |

---

## Water and aqueous streams

| flow_id | Definition | Typical units |
|---------|------------|---------------|
| `potable_water` | Drinking-quality water, per NASA-STD-3001 V2 §7 | L/sol |
| `hygiene_water` | Wash water, lower spec | L/sol |
| `nutrient_solution` | Hydroponic feed, balanced macro+micro | L/sol |
| `irrigation_water` | Plant-grade water | L/sol |
| `condensate_humidity` | Recovered atmospheric water | L/sol |
| `urine_raw` | Pre-treatment urine | L/sol |
| `urine_pretreated` | Acidified, filtered urine | L/sol |
| `brine_concentrated` | UPA reject brine | L/sol |
| `greywater` | Hygiene waste water | L/sol |
| `process_water_warm` | 30–40°C process water | L/sol |
| `cleaning_solution_used` | Spent sanitizer, surfactant-laden | L/sol |

---

## Solid biomass and food

| flow_id | Definition | Typical units |
|---------|------------|---------------|
| `seeds` | Seed stock for planting | g/sol or kg/cycle |
| `edible_biomass_leafy` | Leafy greens (lettuce, mizuna, kale) | kg/sol; include `nutrition_per_kg` |
| `edible_biomass_fruiting` | Tomatoes, peppers, strawberries | kg/sol |
| `edible_biomass_root` | Potatoes, sweet potatoes, carrots | kg/sol |
| `edible_biomass_grain` | Wheat, rice, quinoa | kg/sol |
| `edible_biomass_legume` | Soy, beans, peas | kg/sol |
| `edible_biomass_microbial` | Spirulina, chlorella, single-cell protein | kg/sol |
| `edible_biomass_fungal` | Mushroom, mycelium, yeast biomass | kg/sol |
| `edible_biomass_cell_culture` | Cultured meat / fish | kg/sol |
| `inedible_biomass` | Roots, stalks, leaves not consumed | kg/sol |
| `processed_food_dry` | Stable-shelf processed product | kg/cycle |
| `processed_food_chilled` | Refrigerated product | kg/cycle |
| `meal_ready` | Plated meal, ready to serve | meals/sol |

---

## Waste streams

| flow_id | Definition | Typical units |
|---------|------------|---------------|
| `food_waste_organic` | Spoiled / leftover food, organic | kg/sol |
| `food_packaging_waste` | Wrappers, pouches | kg/sol |
| `feces_solid` | Crew solid waste | kg/sol |
| `urine_processed_solids` | Salts, mineral residue post-UPA | kg/sol |
| `compost_finished` | Mature compost | kg/cycle |
| `digester_effluent` | Anaerobic digester liquid product | L/sol |
| `ash_inorganic` | Combustion or oxidation ash | kg/sol |
| `general_trash` | Non-recyclable solid waste | kg/sol |

---

## Energy and thermal

| flow_id | Definition | Typical units |
|---------|------------|---------------|
| `electric_power_dc` | DC power | W |
| `electric_power_ac` | AC power | W |
| `light_par_umol` | PAR light for crops, μmol/m²/s | μmol/m²/s × area |
| `light_visible_lux` | Crew-area lighting | lux × area |
| `heat_high_grade` | >100°C process heat | W |
| `heat_low_grade` | 30–60°C heat | W |
| `heat_reject_to_radiator` | Waste heat to thermal control | W |

---

## Information / control / crew time

| flow_id | Definition | Typical units |
|---------|------------|---------------|
| `crew_time_routine` | Routine crew labor (food prep, harvest) | hr/sol |
| `crew_time_skilled` | Skilled labor (food systems engineer) | hr/sol |
| `monitoring_telemetry` | Data stream out | kbit/sol |
| `control_setpoint` | Setpoint command in | events/sol |

---

## How to add a new flow_id

1. Pick a snake_case name following the conventions above.
2. Add a row to the relevant section of this file with a one-line definition.
3. Bump the version note at the bottom.
4. Notify the team — flow_ids are immutable once published, like requirement IDs.

---

## Compatibility check semantics

Two technologies are *interface-compatible* on a flow if:
- Tech A has an `output` with `flow_id = X`,
- Tech B has an `input` with `flow_id = X`,
- B's input rate ≤ A's output rate (or both rates can be reconciled by a buffer/scaling).

Conditions strings (e.g. "≥800 ppm CO2") are not yet machine-parsed in v0 — they are flagged for human review by the checker. v1 will add a small condition DSL.

---

**Schema version:** 0.1 (2026-04-29)
