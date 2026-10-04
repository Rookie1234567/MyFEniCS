"""Final independent persisted-array audit and local cost decision.

No new producer, Basix tabulation, Bessel, FE action or solver is executed.
Every row keeps its original reference norm and near-zero denominator.
"""

import csv
import json
from pathlib import Path

import numpy as np

from benchmarks.portable_facet_checks import binding
from src.solvers.strict_port_admission import qualification


def _measure(a, b):
    numerator = float(np.linalg.norm(np.asarray(a) - np.asarray(b)))
    norm = float(np.linalg.norm(b))
    return dict(
        numerator=numerator,
        reference_norm=norm,
        denominator=max(norm, 1e-12),
        near_zero=norm < 1e-12,
        relative=numerator / max(norm, 1e-12),
    )


def audit(root, artifact, marker, budget):
    from src.runners.fixed_phase_campaign import ARTIFACTS, write

    # Read saved bindings, not the lifecycle/producer implementation.
    def index(stage, qualified=True):
        paths = sorted(ARTIFACTS.glob("index_" + stage + "_attempt*.json"))
        records = [json.loads(p.read_text()) for p in paths]
        flag = "stage_qualified" if qualified else "audit_completed"
        records = [
            (p, r) for p, r in zip(paths, records, strict=True) if r["result"].get(flag)
        ]
        if len(records) != 1:
            raise ValueError("UNIQUE_FROZEN_AUDIT_INPUT")
        path, record = records[0]
        for item in record["files"].values():
            if binding(item["path"])["sha256"] != item["sha256"]:
                raise ValueError("AUDIT_FILE_CHANGED")
        return path, record

    qp, q = index("v23_facet_qualification")
    pp, p0 = index("v23_admission_audit", False)
    roles = json.loads(Path(p0["files"]["strict_roles"]["path"]).read_text())
    strict = {k: qualification(v["evidence"], v["expected"]) for k, v in roles.items()}
    with np.load(q["files"]["oracle"]["path"], allow_pickle=False) as z:
        ref = {k: np.array(z[k]) for k in z.files}
    summary = {}
    lines = []
    bindings = dict(qualification=binding(qp), P0=binding(pp))
    for implementation, stage in [
        ("analytic", "v23_analytic_cold"),
        ("q60", "v23_q60_cold"),
    ]:
        budget("independent_saved_arrays")
        path, record = index(stage)
        bindings[implementation] = binding(path)
        with np.load(record["files"]["cold_arrays"]["path"], allow_pickle=False) as z:
            actual = {k: np.array(z[k]) for k in z.files}
        finite = all(np.isfinite(v).all() for v in actual.values())
        moment_abs = float(
            np.max(abs(actual["moment_values"] - ref["moment_oracle110"]))
        )
        interval_negative = float(
            np.max(
                abs(
                    ref["moment_oracle110"] / np.exp(0.5j * ref["frequencies"][:, None])
                    - ref["moment_oracle110"]
                )
            )
        )
        per_degree = {}
        for degree in (4, 6):
            c = ref[f"p{degree}_directions"]
            load = ref[f"p{degree}_load"]
            B, D, H = (ref[f"p{degree}_{k}"] for k in ("B", "D", "H"))
            expected = dict(
                B=B,
                D=D,
                H=H,
                forward=B @ c.T,
                projection=(D @ c.T + load[:, None]) / H[:, None],
                adjoint=B.conj().T @ load,
            )
            totals = {
                k: _measure(actual[f"p{degree}_{k}"], value)
                for k, value in expected.items()
            }
            worst = 0.0
            for row, key in enumerate(q["result"]["local"][str(degree)]["case_keys"]):
                for quantity in ("B", "D", "H", "forward", "projection"):
                    a = actual[f"p{degree}_{quantity}"][row]
                    b = expected[quantity][row]
                    vals = (
                        [_measure(a, b)]
                        if quantity in ("B", "D", "H")
                        else [_measure(a[j], b[j]) for j in range(3)]
                    )
                    for direction, value in enumerate(vals):
                        worst = max(worst, value["relative"])
                        lines.append(
                            dict(
                                implementation=implementation,
                                degree=degree,
                                local_mode_index=row,
                                mode_key=json.dumps(key),
                                quantity=quantity,
                                direction=direction if len(vals) == 3 else -1,
                                **value,
                            )
                        )
            per_degree[str(degree)] = dict(
                whole=totals,
                max_case_direction_relative=worst,
                passed=worst <= 1e-10
                and all(v["relative"] <= 1e-10 for v in totals.values()),
            )
        run = Path(record["run_directory"])
        cost = json.loads((run / "run_summary.json").read_text())
        assert (
            cost["classification"] == "COMPLETED"
            and cost["descendants_cleared"]
            and cost["sampled_process_tree_swap_peak_bytes"] == 0
        )
        summary[implementation] = dict(
            passed=bool(
                finite
                and moment_abs <= 1e-12
                and all(v["passed"] for v in per_degree.values())
            ),
            interval_max_absolute=moment_abs,
            omitted_center_phase_negative_absolute=interval_negative,
            per_degree=per_degree,
            source_sha=record["source_sha"],
            full_launch_seconds=cost["launch_to_summary_seconds_monotonic"],
            worker_seconds=record["result"]["worker_cold_seconds"],
            phase_seconds=record["result"]["phase_seconds"],
            simultaneous_tree_peak_bytes=cost["sampled_process_tree_rss_peak_bytes"],
            own_swap=0,
            cost_record=binding(run / "run_summary.json"),
        )
    a, b = summary["analytic"], summary["q60"]
    gain_time = 1 - a["full_launch_seconds"] / b["full_launch_seconds"]
    gain_rss = 1 - a["simultaneous_tree_peak_bytes"] / b["simultaneous_tree_peak_bytes"]
    local_gain = bool(
        a["passed"] and b["passed"] and (gain_time >= 0.2 or gain_rss >= 0.2)
    )
    decision = (
        "LOCAL_ANALYTIC_GAIN_CANDIDATE"
        if local_gain
        else "RECOMMEND_EXISTING_QUALIFIED_Q60_CLOSE_ANALYTIC_OPTIMIZATION"
        if b["passed"]
        else "LOCAL_STRICT_QUALIFICATION_NOT_AVAILABLE"
    )
    result = dict(
        stage_qualified=all(x["passed"] for x in summary.values()),
        audit_completed=True,
        implementations=summary,
        strict_saved_roles=strict,
        strict_roles_remain_rejected=all(
            not r["strict_complete_qualified"] for r in strict.values()
        ),
        decision=decision,
        time_improvement_fraction=gain_time,
        RSS_improvement_fraction=gain_rss,
        verified_local_20_percent_gain=local_gain,
        comparison="one complete cold lifecycle each, same source/fixed actions; shared-machine timing has no repeat/stability certificate",
        new_FE_actions_Maxwell_factors_solves_Gram_training=0,
        all32060_target_qualified=False,
        NN_gain=False,
        main_solver="FEINN_MAIN_SOLVER_ON_HOLD",
        neural_increment="NO_VERIFIED_NN_INCREMENT",
        target="FULL_TARGET_NOT_QUALIFIED",
        input_bindings=bindings,
    )
    write(artifact / "audit.json", result)
    csv_path = artifact / "local_case_errors.csv"
    with csv_path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(lines[0]))
        writer.writeheader()
        writer.writerows(lines)
    marker("saved_array_and_cost_audit", dict(decision=decision, rows=len(lines)))
    return result, dict(audit=artifact / "audit.json", local_case_errors=csv_path)
