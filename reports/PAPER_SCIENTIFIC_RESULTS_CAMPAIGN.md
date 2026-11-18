# Paper scientific results campaign — national SOC CCS taper

**Status:** Regenerated after permanent deletion of constant-power corridor evidence.  
**Charging model:** `ccs_soc_taper_research_envelope` (research envelope; not OEM-measured).  
**Geography:** national motorway envelope (Tangier–Rabat–Casa–Fès–Oujda–Marrakech–Agadir).

## Scientific honesty

- Taper is a conservative SOC acceptance envelope, not an eActros/Volvo OEM curve.
- Evidence classes remain OSM + COP-DEM + ADM topology + constructed refrigerated OD scenarios — not observed truck counts.
- East Oujda / Msoun–Laâyoune: no invented `entrance_and_exit` attach where ADM×OSM fails; incomplete DEM arcs excluded from claims.

## DEM / site audit (`od_dem_site_audit.csv`)

14 audited ODs are **dem_complete=True**. Grounded on-union stations include:

| OD | stations on union |
|----|-------------------|
| casa_agadir | amskroud_ca, benguerir_ca, settat_ca |
| agadir_casa | benguerir_ac, settat_ac |
| tangier_casa | assilah_tr, bouznika_rc |
| casa_tangier | bouznika_cr, larache_rt |
| casa_rabat | bouznika_cr |
| rabat_fes | *(none — east ADM unmatched)* |

## Headline q=2 portfolio (`q2_critical_portfolio.csv`)

Equal-weight 6-mission national panel; 5-site tractable enumeration  
`{settat_ca, benguerir_ca, settat_ac, benguerir_ac, bouznika_rc}`.

### eActros 600

| Budget | C ops | E ops | F ops | E−C | E sites |
|--------|------:|------:|------:|----:|---------|
| B0 | 0.50 | 0.50 | 0.50 | 0 | — |
| B1 | 0.67 | 0.83 | 0.83 | +1/6 | y_benguerir_ca |
| B2 | 0.83 | **1.00** | **1.00** | +1/6 | y_benguerir_ac, y_benguerir_ca |
| Ball | 0.83 | 1.00 | 1.00 | +1/6 | y_benguerir_ac, y_benguerir_ca |

E=F tie at full coverage with the Benguerir directed pair.

### Volvo FH (475 usable)

| Budget | C ops | E ops | F ops | E−C | E sites |
|--------|------:|------:|------:|----:|---------|
| B0 | 0.33 | 0.33 | 0.33 | 0 | — |
| B2 | 0.50 | 0.67 | 0.67 | +1/6 | y_bouznika_rc, y_settat_ca |
| Ball | 0.50 | **0.83** | **0.83** | +2/6 | y_benguerir_ca, y_bouznika_rc, y_settat_ca |

## Payload × SOC frontier (`payload_soc_frontier.csv`, 80 rows)

Staged eActros grid: payloads `{5.3, 15}` t × SOC `{0.8, 1.0}` × national ODs above.

- At 5.3 t / SOC 0.8–1.0: all six frontier ODs admit **multi_ops=True** under at least one ladder (often even `none` for short legs).
- Stress cell: **agadir_casa @ 15 t / SOC 0.8** remains **multi_ops=False** across AC ladders; becomes operational at **SOC 1.0**.
- No multi-vs-fixed flexibility gains in this staged grid (`flexibility_ops_gain=0`); headline E−C gap remains the route-flexibility story.
- Expand `PAYLOADS`/`SOCS` to the full 3×3 panel for the camera-ready table.

## Artifacts

- `results/paper_campaign/od_dem_site_audit.csv`
- `results/paper_campaign/q2_critical_portfolio.csv`
- `results/paper_campaign/q2_critical_missions.csv`
- `results/paper_campaign/operational_efficiency.csv`
- `configs/optimization/national_longhaul_portfolio.yaml`

## Answers checklist

1. Strongest positive finding: eActros E=F=1.00 at B2 under SOC taper; E−C=+1/6 vs optimized fixed.
2. vs C and F: E ties F; beats C by one mission (eActros) / up to two (Volvo Ball).
3. National northern legs (Tangier→Casa, Casa→Rabat, Rabat→Fès) are DEM-complete and enter the headline panel.
4. Infrastructure: Benguerir directed pair for eActros full coverage; Volvo also uses Bouznika/Settat.
5. Charging credibility: taper-on by default; HOS pads appear on long legs (e.g. bouznika_rc).
6. Barriers: OEM taper unknown; no observed OD counts; east ADM attach incomplete.
