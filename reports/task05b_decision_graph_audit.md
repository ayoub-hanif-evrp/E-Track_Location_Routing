# Task 05B — Decision-graph audit

## Scope

Audit and regenerate the Task 05A path-union decision graph under `data/processed/multiroute/` without overwriting Task 01–04 A3 artifacts.

Regeneration: `python scripts/regenerate_multiroute_decision_graph.py`

## Structural fixes

| Issue | Resolution |
|---|---|
| City + `{od}__o/__d` alias duplication | Canonical one label per OSM id (`canonicalize_terminals`) |
| Missing `osm_edge_pairs` / `arc_id` in JSON | Persisted; `arc_id = sha256(edge sequence)[:16]` |
| Length vs OSM edges | `verify_arc_length`; **0 failures** on regenerate |
| Parallel macros same `(u,v)` | Kept; distinguished by `arc_id` |
| Silent fabricated links | None; union of verified OD paths only |

## Graph size after regenerate

| Metric | Count |
|---:|---:|
| Decision nodes | 162 |
| Decision arcs | 241 |
| Path records | 24 (6 OD × 4) |
| Arc length failures | 0 |

## Path diversity (see `path_diversity_audit.csv`)

Classification uses directed-edge Jaccard vs shortest and length ratio:

- **substantial** — Jaccard ≥ 0.35 (true corridor alternatives)
- **minor_detour** — Jaccard low and length ratio ≤ 1.12
- **substantial_length_detour** — longer with moderate Jaccard

Examples:

| OD | Shortest km | Alt Jaccard / ratio notes |
|---|---:|---|
| casa_marrakech | ~237 | Alternatives with Jaccard ~0.78–0.98 (**substantial**) |
| casa_agadir | ~446 | Mix of high Jaccard (~0.9) and moderate (~0.57) |
| marrakech_agadir | ~268 | One alt Jaccard ~0.35 (borderline / length detour) |

A path that is only ~5–9% longer with low Jaccard is labeled **minor_detour** and must not be oversold as a distinct freight corridor.

## Scientific MRLS instance construction

For Task 05B solves, each mission uses **`contract_od_path_union`**: rebuild a compact decision graph from that OD’s selected alternatives (default: shortest + most diverse other). This avoids inheriting every junction from the global 241-arc union (which over-quantized long ODs).

Claim scope remains: **path_union_of_verified_alternatives_only** (not full Moroccan OSM).
