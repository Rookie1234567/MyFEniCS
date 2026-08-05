"""Case144 checker for the four fixed-identity retry records."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
OUTCOMES = ROOT / "surrogate_tasks/task006_fixed_illumination_hw_surrogate/outcomes"
MANIFEST = ROOT / "benchmarks/artifacts/cases/144_task006_blind_retry_requalification/BLIND_RETRY_CAMPAIGN.json"
CASE143 = ROOT / "benchmarks/cases/143_task006_blind_retry_preflight/records/case143_check.json"
LOCK = OUTCOMES / "TASK006_MODEL_SELECTION_LOCK.json"
RECORD = Path(__file__).resolve().parent / "records/case144_check.json"

FORWARD_SHA = "fdf961545f217d620e22800f2704ae9913a6d270"
MODEL_ID = "S_PROD_FULL3D_STATIC_P5_H10_NY4"
ROUTE_ID = "full3d_static_uniform_n1curl_p5_h10_ny4"
OBSERVABLE = "task002.fixed-n0-orders.v3"
EXPECTED = ("117.5,17.25/A07", "117.5,17.25/A09")
EXPECTED_ANGLES = {"A07": (2.0, 90.0), "A09": (4.0, 60.0)}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def compare(left: dict[str, Any], right: dict[str, Any], tol: float = 1.0e-10) -> bool:
    if left["aggregates"].keys() != right["aggregates"].keys():
        return False
    if any(abs(left["aggregates"][key] - right["aggregates"][key]) > tol for key in left["aggregates"]):
        return False
    if len(left["orders"]) != len(right["orders"]):
        return False
    for a, b in zip(left["orders"], right["orders"]):
        if (a["side"], a["m"], a["n"], a["power_carrying"]) != (b["side"], b["m"], b["n"], b["power_carrying"]):
            return False
        for group in ("s", "p"):
            for name in ("amplitude_re", "amplitude_im", "power"):
                x, y = a[group][name], b[group][name]
                if x is None or y is None:
                    if x != y:
                        return False
                elif abs(x - y) > tol:
                    return False
        x, y = a["order_total_power"], b["order_total_power"]
        if x is None or y is None:
            if x != y:
                return False
        elif abs(x - y) > tol:
            return False
    return True


def formal_response(formal: dict[str, Any]) -> dict[str, Any]:
    """Extract the retry comparison vector from the formal record only.

    A numerical-gate failure is not allowed to produce a production sample, so
    this checker deliberately reads the ordinary formal observable rather than
    treating a missing compact sample as an error in the evidence package.
    """
    observables = formal["observables"]
    mother = observables["mother_response"]
    orders = []
    for order in mother["orders"]:
        components = order.get("components", {})
        orders.append({
            "side": order.get("side"),
            "m": int(order.get("m")),
            "n": int(order.get("n")),
            "power_carrying": bool(order.get("power_carrying")),
            "order_total_power": order.get("order_total_power"),
            "s": {name: components.get("s", {}).get(name) for name in ("amplitude_re", "amplitude_im", "power")},
            "p": {name: components.get("p", {}).get(name) for name in ("amplitude_re", "amplitude_im", "power")},
        })
    return {
        "aggregates": {name: float(observables[name]) for name in ("R_total", "T_total", "A_balance")},
        "orders": orders,
    }


def expected_failed_gate(formal: dict[str, Any]) -> bool:
    gates = formal.get("gates", {})
    failed = [name for name, value in gates.items() if value is False]
    return failed == ["true_residual_le_1e-9"] and all(
        value is True for name, value in gates.items() if name != "true_residual_le_1e-9"
    )


def main() -> int:
    manifest = read(MANIFEST)
    case143 = read(CASE143)
    checks: dict[str, bool] = {}
    checks["case143_pass"] = case143.get("status") == "pass" and case143.get("retry_authorized") is True
    checks["manifest_four_records"] = manifest.get("fem_count") == 4 and len(manifest.get("records", [])) == 4
    checks["manifest_model_lock"] = manifest.get("model_lock_sha256") == sha(LOCK)
    checks["manifest_forward_sha"] = manifest.get("forward_solver_sha") == FORWARD_SHA
    checks["no_model_tuning"] = manifest.get("model_tuned_after_retry") is False and manifest.get("original_case141_modified") is False
    grouped = {key: [row for row in manifest.get("records", []) if row.get("key") == key] for key in EXPECTED}
    checks["exact_two_per_tuple"] = all(len(rows) == 2 and [row.get("attempt") for row in rows] == [2, 3] for rows in grouped.values())
    for key, rows in grouped.items():
        checks[f"{key}_controlled_failure_status"] = all(
            row.get("status") == "failed_numerical_gate" and row.get("return_code") == 2 for row in rows
        )
        checks[f"{key}_source_fixed"] = all(row.get("source_sha") == FORWARD_SHA for row in rows)
        checks[f"{key}_paths_distinct"] = len({row.get("run_directory") for row in rows}) == 2 and all(Path(row["run_directory"]).is_dir() for row in rows)
        formal_responses = []
        for row in rows:
            formal_value = row.get("formal_record_path")
            sample_value = row.get("sample_path")
            formal_path = Path(formal_value) if formal_value else Path("/__missing_formal_record__")
            execution_path = Path(row.get("run_directory", "")) / "execution.json"
            sample_path = Path(sample_value) if sample_value else Path("/__missing_sample__")
            checks[f"{key}_attempt_{row.get('attempt')}_hashes"] = (
                formal_path.is_file()
                and execution_path.is_file()
                and row.get("formal_record_sha256") == sha(formal_path)
                and row.get("execution_sha256") == sha(execution_path)
                and sample_value is None
                and row.get("sample_sha256") is None
            )
            if formal_path.is_file():
                formal = read(formal_path)
                params = formal.get("parameters", {})
                execution = params.get("execution", {})
                config = formal.get("config_identity", {})
                mesh = config.get("mesh", {})
                linear_solver = config.get("linear_solver", {})
                illumination = config.get("illumination", {})
                angle_id = key.split("/")[-1]
                expected_grazing, expected_azimuth = EXPECTED_ANGLES[angle_id]
                actual_solver = formal.get("solver_identity", {})
                checks[f"{key}_attempt_{row.get('attempt')}_identity"] = (
                    formal.get("source_sha") == FORWARD_SHA
                    and formal.get("source_dirty") is False
                    and formal.get("model_id") == MODEL_ID
                    and formal.get("solver_route_id") == ROUTE_ID
                    and params.get("observable_schema_version") == OBSERVABLE
                    and formal.get("output_profile") == "compact_surrogate_record"
                    and execution.get("mpi_ranks") == 2
                    and execution.get("threads_per_rank") == 1
                    and config.get("solver_route_id") == ROUTE_ID
                    and config.get("geometry", {}).get("height_nm") == 117.5
                    and config.get("geometry", {}).get("width_x_nm") == 17.25
                    and mesh.get("axis_cell_counts") == [6, 4, 14]
                    and mesh.get("target_h_nm") == 10.0
                    and config.get("element", {}).get("degree") == 5
                    and linear_solver.get("mat_mumps_icntl_14") == 40
                    and linear_solver.get("mat_mumps_icntl_22") == 0
                    and illumination.get("grazing_deg") == expected_grazing
                    and illumination.get("azimuth_deg") == expected_azimuth
                    and actual_solver.get("requested_mat_mumps_icntl_14") == 40
                    and actual_solver.get("actual_mat_mumps_icntl_14") == 40
                    and actual_solver.get("actual_ksp_type") == "preonly"
                    and actual_solver.get("actual_pc_factor_solver_type") == "mumps"
                    and formal.get("actual_runtime_topology_identity", {}).get("axis_cell_counts") == [6, 4, 14]
                    and formal.get("planned_vs_actual", {}).get("pass") is True
                )
                checks[f"{key}_attempt_{row.get('attempt')}_gates"] = expected_failed_gate(formal)
                formal_responses.append(formal_response(formal))
            else:
                formal_responses.append(None)
        checks[f"{key}_responses_consistent"] = (
            len(formal_responses) == 2
            and all(value is not None for value in formal_responses)
            and compare(formal_responses[0], formal_responses[1])
        )
    errors = [name for name, value in checks.items() if not value]
    result = {
        "schema_version": "task006.case144-retry-check.v1", "status": "pass" if not errors else "failed",
        "qualification_status": "blind_forward_route_not_reproducibly_qualified",
        "checks": checks, "errors": errors, "retry_reproducibly_qualified": False if not errors else False,
        "canonical_rule": "attempt_2 is canonical only after attempt_2 and attempt_3 both pass and compare",
        "model_lock_modified": False,
    }
    RECORD.parent.mkdir(parents=True, exist_ok=True)
    RECORD.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
