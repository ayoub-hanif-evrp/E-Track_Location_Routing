"""Stage D: immutable release package + claim crosswalk refresh from Stage C CSVs."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/paper_campaign"
PAPER = ROOT / "paper"
REL = ROOT / "results/paper_campaign/RELEASE"


def _git_sha() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT)
            .decode()
            .strip()
        )
    except Exception:  # noqa: BLE001
        return "unknown"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def refresh_crosswalk() -> None:
    sha = _git_sha()
    port = OUT / "q2_critical_portfolio.csv"
    claims = []
    if port.exists():
        df = pd.read_csv(port)
        e2 = df[(df.vehicle_key == "eactros_600") & (df.budget.astype(str) == "B2")]
        if not e2.empty:
            r = e2.iloc[0]
            claims.append(
                {
                    "claim_id": "C001",
                    "manuscript_location": "Abstract; Results",
                    "claim_text_short": f"eActros B2 E={r.E_ops:.2f} vs C={r.C_ops:.2f}",
                    "result_file_path": "results/paper_campaign/q2_critical_portfolio.csv",
                    "evidence_status": "stage_c",
                    "notes": str(r.get("pipeline", "")),
                    "git_sha": sha,
                }
            )
            claims.append(
                {
                    "claim_id": "C002",
                    "manuscript_location": "Abstract; Results",
                    "claim_text_short": f"E_equals_F_ops={bool(r.E_equals_F_ops)} at B2 (frozen-site or enum)",
                    "result_file_path": "results/paper_campaign/q2_critical_portfolio.csv",
                    "evidence_status": "stage_c",
                    "notes": "F is greedy-over-enum unless blind_greedy_vs_enum.csv shows otherwise",
                    "git_sha": sha,
                }
            )
    for cid, loc, text, path, status, notes in [
        (
            "C003",
            "Results",
            "B2 placement vs flexibility identical-site cross table",
            "results/paper_campaign/placement_flexibility_ablation.csv",
            "stage_c",
            "columns ops_*_on_{C,E} + placement_effect_* / flexibility_effect_*",
        ),
        (
            "C004",
            "Results",
            "flex SOC>=0.8 retained via survives_q2_flex",
            "results/paper_campaign/payload_soc_frontier_q2_confirm.csv",
            "stage_a_confirm",
            "do not use survives_q2 alone",
        ),
        (
            "C005",
            "Results",
            "AC 15t SOC0.8 discretization-sensitive",
            "results/paper_campaign/q_resolution_flip_inventory.csv",
            "stage_a",
            "see also q1_boundary_refinement.csv",
        ),
        (
            "C006",
            "Results",
            "robustness matrix",
            "results/paper_campaign/robustness_matrix.csv",
            "legacy_or_stage_c",
            "refresh under HOS before submission claims",
        ),
        (
            "C007",
            "Methods",
            "HOS-in-search Label.drive_since_break_steps",
            "tests/unit/test_hos_in_search.py",
            "stage_b",
            "Gate B unit + smoke",
        ),
        (
            "C008",
            "Results",
            "hos mini panel audit-only",
            "results/paper_campaign/hos_mini_panel_gate.csv",
            "stage_c",
            "ops-true => hos_search_audit_only",
        ),
        (
            "C009",
            "Results",
            "q1 boundary under HOS",
            "results/paper_campaign/q1_boundary_refinement.csv",
            "stage_c",
            "flip / near-reserve cells",
        ),
        (
            "C010",
            "Results",
            "solver certification + larger instance",
            "results/paper_campaign/solver_certification_table.csv",
            "stage_c",
            "also solver_larger_instance_table.csv; blind_greedy_vs_enum.csv",
        ),
    ]:
        claims.append(
            {
                "claim_id": cid,
                "manuscript_location": loc,
                "claim_text_short": text,
                "result_file_path": path,
                "evidence_status": status,
                "notes": notes,
                "git_sha": sha,
            }
        )
    out = PAPER / "claims_to_results_crosswalk.csv"
    pd.DataFrame(claims).to_csv(out, index=False)
    print(f"Wrote {out}", flush=True)


def write_release() -> None:
    REL.mkdir(parents=True, exist_ok=True)
    sha = _git_sha()
    files = {}
    for p in sorted(OUT.glob("*")):
        if not p.is_file():
            continue
        if p.suffix not in {".csv", ".json", ".md"}:
            continue
        if p.name == "RELEASE_MANIFEST.json":
            continue
        files[p.name] = {"sha256": _sha256(p), "bytes": p.stat().st_size}
    payload = {
        "release_name": f"stage-c-hos-{sha[:12]}",
        "git_sha": sha,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "pipeline": "hos_in_search_stage_c",
        "files": files,
        "reproduce": [
            "pip install -e \".[dev]\"",
            "pytest -q -m \"not integration\"",
            "python scripts/run_stage_c_hos_national.py --phase all_fast",
        ],
        "contribution_statement": (
            "Moroccan refrigerated eHDT + DEM + directional ADM + operational joint "
            "siting under HOS-in-search — not a new generic LRP."
        ),
    }
    text = json.dumps(payload, indent=2, sort_keys=True)
    man = REL / "RELEASE_MANIFEST.json"
    man.write_text(text, encoding="utf-8")
    # Also mirror at paper_campaign root for campaign_manifest compatibility
    root_man = OUT / "campaign_manifest.json"
    root_payload = json.loads(text)
    root_payload["manifest_sha256"] = hashlib.sha256(text.encode()).hexdigest()
    root_man.write_text(json.dumps(root_payload, indent=2, sort_keys=True), encoding="utf-8")
    notes = REL / "RELEASE_NOTES.md"
    notes.write_text(
        f"""# Stage C/D release `{payload['release_name']}`

- Git SHA: `{sha}`
- Pipeline: HOS-in-search Stage C artifacts under `results/paper_campaign/`
- Claims crosswalk: `paper/claims_to_results_crosswalk.csv`
- Manuscript: `paper/manuscript.tex` (claims ⊆ Stage C tables)

## Reproduce

```bash
pip install -e ".[dev]"
pytest -q -m "not integration"
python scripts/run_stage_c_hos_national.py --phase all_fast
```

## Contribution (scoped)

{payload['contribution_statement']}
""",
        encoding="utf-8",
    )
    print(f"Wrote {man} and {notes}", flush=True)


def patch_manuscript_results_from_csv() -> None:
    """Rewrite Results subsection numbers from Stage C portfolio when available."""
    port = OUT / "q2_critical_portfolio.csv"
    if not port.exists():
        return
    df = pd.read_csv(port)
    e2 = df[(df.vehicle_key == "eactros_600") & (df.budget.astype(str) == "B2")]
    e_all = df[(df.vehicle_key == "eactros_600") & (df.budget.astype(str) == "Ball")]
    if e2.empty:
        return
    r = e2.iloc[0]
    pipe = str(r.get("pipeline", "unknown"))
    ball = ""
    if not e_all.empty:
        b = e_all.iloc[0]
        ball = (
            f" Ball E$=$F$={float(b.E_ops):.2f}$ vs C$={float(b.C_ops):.2f}$."
        )
    ms = PAPER / "manuscript.tex"
    text = ms.read_text(encoding="utf-8")
    old = None
    import re

    pat = r"\\subsection\{Headline coverage.*?\\subsection\{Discretization"
    repl = (
        "\\subsection{Headline coverage (Stage~C)}\n"
        f"Pipeline tag: \\texttt{{{pipe}}}.\n"
        f"\\texttt{{q2\\_critical\\_portfolio.csv}}: eActros B2 E$=${float(r.E_ops):.2f}$"
        f" vs C$=${float(r.C_ops):.2f}$"
        + (
            f"; E$=$F at B2"
            if bool(r.E_equals_F_ops)
            else "; E and F differ at B2 — see blind greedy"
        )
        + f".{ball}\n"
        "\\texttt{placement\\_flexibility\\_ablation.csv}: identical-site cross masks "
        "decompose placement vs flexibility.\n\n"
        "\\subsection{Discretization"
    )
    new, n = re.subn(pat, lambda _m: repl, text, count=1, flags=re.S)
    if n:
        ms.write_text(new, encoding="utf-8")
        print("Patched manuscript Results headline", flush=True)
    else:
        print("Manuscript headline already current (manual Stage C text)", flush=True)


def main() -> None:
    refresh_crosswalk()
    write_release()
    patch_manuscript_results_from_csv()


if __name__ == "__main__":
    main()
