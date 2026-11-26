# Invalid DEM profile investigation

## Record

- `arc_id`: `fe603377792cc7cb`
- Provenance OD: `casa_oujda`
- Meta: `quality=invalid`, `skipped=True`, `source=copdem_glo30`
- Profile file: **absent** (`arc_fe603377792cc7cb.json` not written)
- Blockers: `DEM unavailable → not writing dem profile`; `terrain quality INVALID — skipped`
- Decision endpoints: `J1544967842 → J1595316133` (~42.3 km)

## Impact

- Appears only on the **edge_penalty** diversity alternative for `casa_oujda` (coverage ≈ 93.5% on that alt).
- **Shortest-distance** `casa_oujda` reconstruction has full DEM coverage (100%) and does not use this arc.
- Headline 14-mission panel does not include Oujda ODs.

## Interpretation

This is a documented sampling failure on a non-headline diversity alternative, not a silent hole in the primary corridor elevation statistics used for D-Figure 5 / D-T05 shortest-path rows.
