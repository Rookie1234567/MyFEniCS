import hashlib
import json
from pathlib import Path

r = Path(__file__).resolve().parents[3]
records = r / "docs/task43_hp_adaptivity/outcomes/records"
rows = []
provenance = {}


def load(p):
    p = Path(p)
    p = p if p.is_absolute() else r / p
    provenance[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    return json.loads(p.read_text())


def strings(v):
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for x in v.values():
            yield from strings(x)
    elif isinstance(v, list):
        for x in v:
            yield from strings(x)


hfe = {
    1: 47235,
    2: 80028,
    3: 103652,
    4: 127397,
    5: 215092,
    6: 171122,
    7: 273728,
    8: 251732,
    9: None,
    10: None,
}
hi = {
    1: 21600,
    2: 44820,
    3: 61848,
    4: 74058,
    5: 137082,
    6: 111102,
    7: 184614,
    8: 171510,
    9: 309060,
    10: 292260,
}
for i in range(1, 11):
    if i < 10:
        selection = load(records / f"round{i}_selection_transition{i}_v1.json")
        pp = Path(selection["selected_candidate"]["run_root"]) / "candidate_plan.json"
        c = load(selection["selected_candidate"]["comparison_record_path"])
    else:
        selection = load(records / "round10_rejected_candidate_v1.json")
        pp = (
            r
            / "benchmarks/artifacts/task43/round10_p_up_attempt1/run/candidate_plan.json"
        )
        c = load(selection["evidence"]["comparison_raw_record"]["path"])
    p = load(pp)
    prov = p["task43_candidate"]["provenance"]
    closure = prov.get("closure_or_inheritance", prov.get("p_up_closure", {}))
    stats = {
        k: closure.get(k)
        for k in [
            "requested_mark_count",
            "requested_raised_count",
            "saturated_mark_count",
            "forced_cell_count",
        ]
    }
    if i == 1:
        stats = {
            "requested_mark_count": 46,
            "requested_raised_count": 46,
            "saturated_mark_count": 0,
            "forced_cell_count": 0,
        }
    if i == 2:
        stats.update(
            {
                "requested_mark_count": 51,
                "requested_raised_count": 51,
                "saturated_mark_count": 0,
                "forced_cell_count": 41,
            }
        )
    hpaths = [
        Path(s) for s in strings(selection) if s.endswith(f"round{i}_h_refine.json")
    ]
    if not hpaths and i < 9:
        audit = records / f"round{i}_independent_audit_v1.json"
        if audit.exists():
            hpaths = [
                Path(s)
                for s in strings(load(audit))
                if s.endswith(f"round{i}_h_refine.json")
            ]
    if not hpaths:
        for related in records.glob(f"round{i}_*.json"):
            hpaths.extend(
                Path(s)
                for s in strings(load(related))
                if s.endswith(f"round{i}_h_refine.json")
            )
    if i == 1:
        hpaths = [Path(selection["h_candidate"]["plan"]["path"])]
    if i == 9:
        hpaths = [
            r
            / "benchmarks/artifacts/task43/round9_light_preview_attempt1/plans/round9_h_refine.json"
        ]
    if i == 10:
        hpaths = [
            r
            / "benchmarks/artifacts/task43/round10_light_preview_attempt1/plans/round10_h_refine.json"
        ]
    assert hpaths, (i, "missing hplan")
    hp = hpaths[0]
    hp = hp if hp.is_absolute() else r / hp
    h = load(hp)
    hc = h["expected_forest"]["closure_counts"]
    hcl = sum(v for k, v in hc.items() if k != "user")
    row = {
        "cycle": i,
        "p_marks": stats,
        "p_FE": c["selection"]["candidate_independent_FE_dofs"],
        "p_added_FE": c["selection"]["actual_added_independent_FE_dofs"],
        "eta": c["selection"]["eta_candidate"],
        "J": c["J_infinity"]["candidate"]["value"],
        "p_state": "accepted" if i < 10 else "rejected_G_noise",
        "h_requested": hc["user"],
        "h_closure": hcl,
        "h_leaves": h["expected_forest"]["leaf_cell_count"],
        "h_actual_FE": hfe[i],
        "h_interior": hi[i],
        "h_trace": hfe[i] - hi[i] if hfe[i] is not None else None,
        "h_status": "real_h_retry_qualified_not_spatial_pass"
        if i == 1
        else (
            "not_run_score_pruned"
            if i < 10
            else "not_run_goal_DoF_infeasible_not_score_pruned"
        ),
        "p_plan": str(pp),
        "h_plan": str(hp),
    }
    rows.append(row)
path = records / "cycle_index_v1.json"
path.write_text(
    json.dumps(
        {
            "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "rows": rows,
            "input_sha256": provenance,
            "scope": "Actual h FE only1–8;9/10 cell-interior lower bounds not actual totalFE. No new authority or PDE.",
        },
        indent=2,
    )
    + "\n"
)
print(rows)
