# PAPER_SCIENTIFIC_RESULTS_CAMPAIGN

Git SHA: `6ac846a434255c0c327488f09f983ae760a81535`

Primary metric: **operational coverage** (energy + continuous replay + schedule/HOS).
Chargers are hypothetical. Scenario counts are not Moroccan traffic samples.

## DEM / site audit

- `agadir_casa`: dem_complete=True, amskroud_on_union=False
- `agadir_marrakech`: dem_complete=True, amskroud_on_union=False
- `marrakech_casa`: dem_complete=True, amskroud_on_union=False
- `casa_agadir`: dem_complete=True, amskroud_on_union=True
- `casa_marrakech`: dem_complete=True, amskroud_on_union=False
- `marrakech_agadir`: dem_complete=True, amskroud_on_union=True
- `tangier_casa`: dem_complete=True, amskroud_on_union=False
- `casa_tangier`: dem_complete=True, amskroud_on_union=False
- `casa_rabat`: dem_complete=True, amskroud_on_union=False
- `rabat_casa`: dem_complete=True, amskroud_on_union=False
- `rabat_fes`: dem_complete=True, amskroud_on_union=False
- `fes_rabat`: dem_complete=True, amskroud_on_union=False
- `tangier_rabat`: dem_complete=True, amskroud_on_union=False
- `rabat_tangier`: dem_complete=True, amskroud_on_union=False

## 1–2. Strongest findings & E vs C vs F (q=2 headline)

### eactros_600
| budget | C_ops | E_ops | F_ops | E−C | E=F | E_sites |
|---|---:|---:|---:|---:|---|---|
| B0 | 0.64 | 0.64 | 0.64 | 0.00 | True | nan |
| B1 | 0.71 | 0.79 | 0.79 | 0.07 | True | y_benguerir_ca |
| B2 | 0.79 | 0.79 | 0.79 | 0.00 | True | y_benguerir_ca |
| B3 | 0.79 | 0.79 | 0.79 | 0.00 | True | y_benguerir_ca |
| Ball | 0.79 | 0.79 | 0.79 | 0.00 | True | y_benguerir_ca |
- B2 denominator n_missions=14: E serves 11/14, C serves 11/14.

### volvo_475
| budget | C_ops | E_ops | F_ops | E−C | E=F | E_sites |
|---|---:|---:|---:|---:|---|---|
| B0 | 0.50 | 0.50 | 0.50 | 0.00 | True | nan |
| B1 | 0.57 | 0.57 | 0.57 | 0.00 | True | y_larache_rt |
| B2 | 0.57 | 0.57 | 0.57 | 0.00 | True | y_larache_rt |
| B3 | 0.57 | 0.57 | 0.57 | 0.00 | True | y_larache_rt |
| Ball | 0.57 | 0.57 | 0.57 | 0.00 | True | y_larache_rt |
- B2 denominator n_missions=14: E serves 8/14, C serves 8/14.

## 3. Payload × SOC frontier (does it hold under realistic dispatch?)

| vehicle | od | payload_t | soc | multi_any | fixed_any | flex_gain |
|---|---|---:|---:|---|---|---|
| eactros_600 | agadir_casa | 5.3 | 0.5 | False | False | False |
| eactros_600 | agadir_casa | 5.3 | 0.8 | True | True | False |
| eactros_600 | agadir_casa | 5.3 | 1.0 | True | True | False |
| eactros_600 | agadir_casa | 10.0 | 0.5 | False | False | False |
| eactros_600 | agadir_casa | 10.0 | 0.8 | True | True | False |
| eactros_600 | agadir_casa | 10.0 | 1.0 | True | True | False |
| eactros_600 | agadir_casa | 15.0 | 0.5 | False | False | False |
| eactros_600 | agadir_casa | 15.0 | 0.8 | False | False | False |
| eactros_600 | agadir_casa | 15.0 | 1.0 | True | True | False |
| eactros_600 | agadir_marrakech | 5.3 | 0.5 | False | False | False |
| eactros_600 | agadir_marrakech | 5.3 | 0.8 | True | True | False |
| eactros_600 | agadir_marrakech | 5.3 | 1.0 | True | True | False |
| eactros_600 | agadir_marrakech | 10.0 | 0.5 | False | False | False |
| eactros_600 | agadir_marrakech | 10.0 | 0.8 | True | True | False |
| eactros_600 | agadir_marrakech | 10.0 | 1.0 | True | True | False |
| eactros_600 | agadir_marrakech | 15.0 | 0.5 | False | False | False |
| eactros_600 | agadir_marrakech | 15.0 | 0.8 | True | True | False |
| eactros_600 | agadir_marrakech | 15.0 | 1.0 | True | True | False |
| eactros_600 | casa_agadir | 5.3 | 0.5 | True | True | False |
| eactros_600 | casa_agadir | 5.3 | 0.8 | True | True | False |
| eactros_600 | casa_agadir | 5.3 | 1.0 | True | True | False |
| eactros_600 | casa_agadir | 10.0 | 0.5 | False | False | False |
| eactros_600 | casa_agadir | 10.0 | 0.8 | True | True | False |
| eactros_600 | casa_agadir | 10.0 | 1.0 | True | True | False |
| eactros_600 | casa_agadir | 15.0 | 0.5 | False | False | False |
| eactros_600 | casa_agadir | 15.0 | 0.8 | True | True | False |
| eactros_600 | casa_agadir | 15.0 | 1.0 | True | True | False |
| eactros_600 | casa_marrakech | 5.3 | 0.5 | True | False | True |
| eactros_600 | casa_marrakech | 5.3 | 0.8 | True | True | False |
| eactros_600 | casa_marrakech | 5.3 | 1.0 | True | True | False |
| eactros_600 | casa_marrakech | 10.0 | 0.5 | True | False | True |
| eactros_600 | casa_marrakech | 10.0 | 0.8 | True | True | False |
| eactros_600 | casa_marrakech | 10.0 | 1.0 | True | True | False |
| eactros_600 | casa_marrakech | 15.0 | 0.5 | True | False | True |
| eactros_600 | casa_marrakech | 15.0 | 0.8 | True | True | False |
| eactros_600 | casa_marrakech | 15.0 | 1.0 | True | True | False |
| eactros_600 | casa_rabat | 5.3 | 0.5 | True | True | False |
| eactros_600 | casa_rabat | 5.3 | 0.8 | True | True | False |
| eactros_600 | casa_rabat | 5.3 | 1.0 | True | True | False |
| eactros_600 | casa_rabat | 10.0 | 0.5 | True | True | False |
| eactros_600 | casa_rabat | 10.0 | 0.8 | True | True | False |
| eactros_600 | casa_rabat | 10.0 | 1.0 | True | True | False |
| eactros_600 | casa_rabat | 15.0 | 0.5 | True | True | False |
| eactros_600 | casa_rabat | 15.0 | 0.8 | True | True | False |
| eactros_600 | casa_rabat | 15.0 | 1.0 | True | True | False |
| eactros_600 | casa_tangier | 5.3 | 0.5 | False | False | False |
| eactros_600 | casa_tangier | 5.3 | 0.8 | True | True | False |
| eactros_600 | casa_tangier | 5.3 | 1.0 | True | True | False |
| eactros_600 | casa_tangier | 10.0 | 0.5 | False | True | False |
| eactros_600 | casa_tangier | 10.0 | 0.8 | True | True | False |
| eactros_600 | casa_tangier | 10.0 | 1.0 | True | True | False |
| eactros_600 | casa_tangier | 15.0 | 0.5 | False | True | False |
| eactros_600 | casa_tangier | 15.0 | 0.8 | False | True | False |
| eactros_600 | casa_tangier | 15.0 | 1.0 | True | True | False |
| eactros_600 | fes_rabat | 5.3 | 0.5 | True | True | False |
| eactros_600 | fes_rabat | 5.3 | 0.8 | True | True | False |
| eactros_600 | fes_rabat | 5.3 | 1.0 | True | True | False |
| eactros_600 | fes_rabat | 10.0 | 0.5 | False | False | False |
| eactros_600 | fes_rabat | 10.0 | 0.8 | True | True | False |
| eactros_600 | fes_rabat | 10.0 | 1.0 | True | True | False |
| eactros_600 | fes_rabat | 15.0 | 0.5 | False | False | False |
| eactros_600 | fes_rabat | 15.0 | 0.8 | True | True | False |
| eactros_600 | fes_rabat | 15.0 | 1.0 | True | True | False |
| eactros_600 | marrakech_agadir | 5.3 | 0.5 | False | False | False |
| eactros_600 | marrakech_agadir | 5.3 | 0.8 | True | True | False |
| eactros_600 | marrakech_agadir | 5.3 | 1.0 | True | True | False |
| eactros_600 | marrakech_agadir | 10.0 | 0.5 | False | False | False |
| eactros_600 | marrakech_agadir | 10.0 | 0.8 | True | True | False |
| eactros_600 | marrakech_agadir | 10.0 | 1.0 | True | True | False |
| eactros_600 | marrakech_agadir | 15.0 | 0.5 | False | False | False |
| eactros_600 | marrakech_agadir | 15.0 | 0.8 | True | True | False |
| eactros_600 | marrakech_agadir | 15.0 | 1.0 | True | True | False |
| eactros_600 | marrakech_casa | 5.3 | 0.5 | True | True | False |
| eactros_600 | marrakech_casa | 5.3 | 0.8 | True | True | False |
| eactros_600 | marrakech_casa | 5.3 | 1.0 | True | True | False |
| eactros_600 | marrakech_casa | 10.0 | 0.5 | True | True | False |
| eactros_600 | marrakech_casa | 10.0 | 0.8 | True | True | False |
| eactros_600 | marrakech_casa | 10.0 | 1.0 | True | True | False |
| eactros_600 | marrakech_casa | 15.0 | 0.5 | True | True | False |
| eactros_600 | marrakech_casa | 15.0 | 0.8 | True | True | False |
| eactros_600 | marrakech_casa | 15.0 | 1.0 | True | True | False |
| eactros_600 | rabat_casa | 5.3 | 0.5 | True | True | False |
| eactros_600 | rabat_casa | 5.3 | 0.8 | True | True | False |
| eactros_600 | rabat_casa | 5.3 | 1.0 | True | True | False |
| eactros_600 | rabat_casa | 10.0 | 0.5 | True | True | False |
| eactros_600 | rabat_casa | 10.0 | 0.8 | True | True | False |
| eactros_600 | rabat_casa | 10.0 | 1.0 | True | True | False |
| eactros_600 | rabat_casa | 15.0 | 0.5 | True | True | False |
| eactros_600 | rabat_casa | 15.0 | 0.8 | True | True | False |
| eactros_600 | rabat_casa | 15.0 | 1.0 | True | True | False |
| eactros_600 | rabat_fes | 5.3 | 0.5 | False | False | False |
| eactros_600 | rabat_fes | 5.3 | 0.8 | True | True | False |
| eactros_600 | rabat_fes | 5.3 | 1.0 | True | True | False |
| eactros_600 | rabat_fes | 10.0 | 0.5 | False | False | False |
| eactros_600 | rabat_fes | 10.0 | 0.8 | True | True | False |
| eactros_600 | rabat_fes | 10.0 | 1.0 | True | True | False |
| eactros_600 | rabat_fes | 15.0 | 0.5 | False | False | False |
| eactros_600 | rabat_fes | 15.0 | 0.8 | True | True | False |
| eactros_600 | rabat_fes | 15.0 | 1.0 | True | True | False |
| eactros_600 | tangier_casa | 5.3 | 0.5 | False | False | False |
| eactros_600 | tangier_casa | 5.3 | 0.8 | True | True | False |
| eactros_600 | tangier_casa | 5.3 | 1.0 | True | True | False |
| eactros_600 | tangier_casa | 10.0 | 0.5 | False | False | False |
| eactros_600 | tangier_casa | 10.0 | 0.8 | True | True | False |
| eactros_600 | tangier_casa | 10.0 | 1.0 | True | True | False |
| eactros_600 | tangier_casa | 15.0 | 0.5 | False | False | False |
| eactros_600 | tangier_casa | 15.0 | 0.8 | False | True | False |
| eactros_600 | tangier_casa | 15.0 | 1.0 | True | True | False |
| eactros_600 | tangier_rabat | 5.3 | 0.5 | True | True | False |

- Flexibility ops-gains at SOC≥80% (q=5 screen): **0** cells (denominator 72 veh×od×payload×soc summaries). Retained flex advantage at q=2 (`survives_q2_flex` / flex True): **2** unique scenarios (not 0). q-resolution flips logged: **8** rows.
- Agadir→Casablanca 15 t / SOC 0.8 is **discretization-sensitive**: unserved at q=5 ladders but eActros served at q=2 with Benguerir AC (min SOC≈0.107). Do not treat SOC=1.0 as a categorical physical requirement pending HOS-in-search re-run.

## 4. Infrastructure required / Amskroud CA value

- `casa_agadir`: amskroud_on_union=True
  - p=5300.0 soc=0.5: without=True with=True
  - p=5300.0 soc=0.8: without=True with=True
  - p=10000.0 soc=0.8: without=True with=True
- `casa_marrakech`: amskroud_on_union=False
- `marrakech_agadir`: amskroud_on_union=True
  - p=5300.0 soc=0.5: without=False with=False
  - p=5300.0 soc=0.8: without=True with=True
  - p=10000.0 soc=0.8: without=True with=True

## 5. Charging / rest / time credibility

- Matched-time comparisons (both C and E ops-feasible): **87**
- Serviceability-only gains (E yes, C no): **5**
- Matched Δtrip_min median=0.00 (positive ⇒ E slower).

## 6–7. Generalization & strength vs prior 3-mission pilot

- Headline q=2 confirms whether prior B2 claims survive finer energy grid.
- Frontier expands evidence across payload×SOC; unique ODs separated from scenario rows.
- DEM recovery for `marrakech_casa` / `agadir_marrakech` succeeded via COP-DEM on verified OSM macros.

## 8. Remaining barriers to journal submission

- No observed OD truck counts / charger availability / grid capacity.
- Axle-law compliance unverified; HGV access at ADM sites unknown.
- CCS taper is a research envelope, not OEM-measured curves.
- Equal / illustrative weights ≠ traffic sample.
- If heavy-payload cells remain unserved, that is a physical/operating finding—not a solver bug.

## Artifacts

- Directory: `C:/Users/AYOUB/OneDrive - EMSI/Bureau/PHD_WORK/E-Track_Location_Routing/results/paper_campaign`
- Figures: `C:/Users/AYOUB/OneDrive - EMSI/Bureau/PHD_WORK/E-Track_Location_Routing/results/paper_campaign/figures`

## Answers checklist

1. Strongest three positive findings: see q=2 B2 E−C gaps and frontier flexibility cells above.
2. vs optimized fixed (C) and greedy (F): tables above; ties reported when E=F.
3. Realistic SOC/payload: frontier section.
4. Infrastructure required: E_sites columns + Amskroud section.
5. Charging/rest credibility: efficiency section + HOS pads in mission CSVs.
6. General vs case-specific: compare headline vs frontier vs expanded depot panel.
7. Stronger than 3-mission? Only if frontier + expanded OD panel add mechanism-separated gains.
8. Barriers: listed above.
