"""Read-only raw-output checker for the Task39extra V31 authority-limited run.

This checker does not import the solver. It recomputes residual norms from the
saved vectors and recomputes modal power and energy closures from raw outputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

SCHEMA = "task039extra.v31.raw-output-checker.v1"
EXPECTED_RUN_ID = "task39extra_v31_projection_layout_original_h7p5_user_authorized_recovery_v1"
RESIDUAL_LIMIT = 1.0e-6
PHYSICAL_LIMIT = 1.0e-5
POWER_SUM_LIMIT = 1.0e-12


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _json(root: Path, relative: str) -> Any:
    return json.loads((root / relative).read_text(encoding="utf-8"))


def _finite_tree(value: Any) -> bool:
    if isinstance(value, dict):
        return all(_finite_tree(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return all(_finite_tree(item) for item in value)
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return True
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    return False


def _close(left: float, right: float, tolerance: float) -> bool:
    return math.isfinite(left) and math.isfinite(right) and abs(left - right) <= tolerance


def _residual_facts(root: Path, sidecar_name: str) -> dict[str, Any]:
    sidecar = _json(root, sidecar_name)
    archive_path = Path(sidecar["arrays"]["path"]).resolve()
    if not archive_path.is_relative_to(root.resolve()):
        raise ValueError(f"{sidecar_name}: residual archive escapes run directory")
    archive_sha = _sha256(archive_path)
    if archive_sha != sidecar["arrays"]["sha256"]:
        raise ValueError(f"{sidecar_name}: residual archive SHA mismatch")
    with np.load(archive_path, allow_pickle=False) as arrays:
        rhs = np.asarray(arrays[sidecar["rhs"]["array_key"]], dtype=np.complex128)
        applied = np.asarray(arrays[sidecar["applied"]["array_key"]], dtype=np.complex128)
        residual = np.asarray(arrays[sidecar["residual"]["array_key"]], dtype=np.complex128)
        solution = np.asarray(arrays[sidecar["solution"]["array_key"]], dtype=np.complex128)
        if not all(np.isfinite(vector).all() for vector in (rhs, applied, residual, solution)):
            raise ValueError(f"{sidecar_name}: residual archive contains non-finite values")
        if not (rhs.shape == applied.shape == residual.shape == solution.shape):
            raise ValueError(f"{sidecar_name}: residual vector shapes differ")
        rhs_norm = float(np.linalg.norm(rhs))
        residual_norm = float(np.linalg.norm(residual))
        relative = residual_norm / rhs_norm
        relation_error = float(np.linalg.norm(rhs - applied - residual)) / rhs_norm
    if not math.isclose(rhs_norm, float(sidecar["rhs_norm"]), rel_tol=5e-12, abs_tol=1e-14):
        raise ValueError(f"{sidecar_name}: saved RHS norm does not match raw vector")
    if not math.isclose(
        relative,
        float(sidecar["explicit_relative_residual"]),
        rel_tol=5e-12,
        abs_tol=1e-15,
    ):
        raise ValueError(f"{sidecar_name}: saved residual scalar does not match raw vectors")
    return {
        "archive_sha256": archive_sha,
        "vector_size": int(rhs.size),
        "rhs_norm": rhs_norm,
        "residual_norm": residual_norm,
        "relative_residual": relative,
        "rhs_minus_applied_relative_error": relation_error,
        "independent_action_count": sidecar.get("independent_action_count"),
        "passed": relative <= RESIDUAL_LIMIT and relation_error <= 1e-12,
    }


def check_run(root: Path) -> dict[str, Any]:
    root = root.resolve()
    checks: dict[str, bool] = {}
    failures: list[str] = []

    def require(name: str, condition: bool) -> None:
        checks[name] = bool(condition)
        if not condition:
            failures.append(name)

    manifest = _json(root, "run_manifest.json")
    run_summary = _json(root, "run_summary.json")
    resolved = _json(root, "resolved_config.json")
    worker = _json(root, "physical_dual_condensed_projection_layout_v31_summary.json")
    require(
        "run_finished_exit0",
        manifest.get("status") == "finished" and manifest.get("exit_status") == 0,
    )
    require(
        "workflow_finished_exit0",
        run_summary.get("status") == "finished"
        and run_summary.get("exit_status") == 0,
    )
    require(
        "run_identity",
        manifest.get("run_id") == EXPECTED_RUN_ID
        and resolved.get("run_id") == EXPECTED_RUN_ID
        and run_summary.get("run_id") == EXPECTED_RUN_ID,
    )
    source_text = (root / "source_sha.txt").read_text(encoding="utf-8").strip()
    require(
        "source_identity",
        manifest.get("source_sha") == source_text == worker.get("source_sha"),
    )
    input_sha = _sha256(root / "input_original.dat")
    require("input_identity", manifest.get("input_sha256") == input_sha)
    require(
        "worker_authority_classification",
        worker.get("result_classification")
        == "DISCRETE_SOLVE_AND_CONSISTENCY_PASS_AUTHORITY_LIMITED"
        and worker.get("official_result") is True,
    )

    final = _residual_facts(root, "final_residual/q4_final.json")
    released = _residual_facts(root, "post_release_final_residual/q4_post_release_final.json")
    require("final_explicit_residual", final["passed"])
    require("post_release_explicit_residual", released["passed"])
    require("final_residual_action", final["independent_action_count"] == 1)
    require("post_release_released_after_check", worker.get("release_after_final_residual") is True)
    require(
        "worker_residual_agreement",
        math.isclose(
            final["relative_residual"],
            float(worker["final_explicit_relative_residual"]),
            rel_tol=5e-12,
            abs_tol=1e-15,
        )
        and math.isclose(
            released["relative_residual"],
            float(worker["post_release_explicit_relative_residual"]),
            rel_tol=5e-12,
            abs_tol=1e-15,
        ),
    )

    output_sidecar = _json(root, "official_output/q4_output.json")
    output_archive = root / "official_output/q4_output.npz"
    output_sha = _sha256(output_archive)
    require("official_vector_sha", output_sidecar["arrays"]["sha256"] == output_sha)
    with np.load(output_archive, allow_pickle=False) as arrays:
        output_vector = np.asarray(arrays[output_sidecar["output"]["auxiliary"]["array_key"]])
        output_vector_finite = bool(np.isfinite(output_vector).all())
        output_vector_shape = list(output_vector.shape)
    require("official_vector_finite", output_vector_finite and output_vector_shape == [80])

    modes = _json(root, "v31q4_ordered_mode_manifest.json")
    modal = _json(root, "numerical_output/dtn_port_diffraction_orders_3d.json")
    power = _json(root, "numerical_output/dtn_port_power_metrics_3d.json")
    port = _json(root, "numerical_output/port_power.json")
    absorption = _json(root, "numerical_output/volume_absorption.json")
    amplitudes = _json(root, "numerical_output/dtn_auxiliary_amplitudes_3d.json")
    mode_rows = modes.get("modes", [])
    order_rows = modal.get("orders", [])
    def mode_key(row: dict[str, Any]) -> tuple[Any, ...]:
        return (row.get("side"), row.get("m"), row.get("n"), row.get("polarization"))

    expected_keys = [mode_key(row) for row in mode_rows]
    observed_keys = [mode_key(row) for row in order_rows]
    require(
        "ordered_modal_identity",
        len(mode_rows) == len(order_rows) == len(amplitudes) == 80
        and len(set(observed_keys)) == 80
        and observed_keys == expected_keys,
    )
    require(
        "modal_outputs_finite_and_passive",
        _finite_tree(order_rows)
        and all(float(row.get("R", -1.0)) >= -1e-12 for row in order_rows)
        and all(float(row.get("T", -1.0)) >= -1e-12 for row in order_rows)
        and _finite_tree(amplitudes),
    )

    r = float(power["R_total"])
    t = float(power["T_total"])
    a = float(power["A_balance"])
    av = float(absorption["A_volume_total"])
    r00s = float(power["R00_s"])
    r00p = float(power["R00_p"])
    r00 = float(power["R00_total"])
    volume_components = (
        float(absorption["A_volume_grating"])
        + float(absorption["A_volume_substrate"])
    )
    r_orders = sum(float(row["R"]) for row in order_rows)
    t_orders = sum(float(row["T"]) for row in order_rows)
    metrics = {
        "R_total": r,
        "T_total": t,
        "A_balance": a,
        "A_volume_total": av,
        "R00_s": r00s,
        "R00_p": r00p,
        "R00_total": r00,
        "R_plus_T": r + t,
        "R_plus_T_plus_A_volume": r + t + av,
        "energy_closure_error": abs(r + t + av - 1.0),
        "port_volume_absorption_difference": abs(a - av),
        "modal_R_sum": r_orders,
        "modal_T_sum": t_orders,
        "mode_count": len(order_rows),
    }
    require(
        "aggregate_power_finite_and_passive",
        _finite_tree(metrics) and min(r, t, a, av) >= -1e-12,
    )
    require(
        "aggregate_power_identity",
        _close(float(power["R_plus_T"]), r + t, POWER_SUM_LIMIT)
        and _close(a, 1.0 - r - t, POWER_SUM_LIMIT)
        and _close(r00, r00s + r00p, POWER_SUM_LIMIT),
    )
    require(
        "modal_sums_match_official_R_T",
        _close(r_orders, r, POWER_SUM_LIMIT) and _close(t_orders, t, POWER_SUM_LIMIT),
    )
    require(
        "volume_absorption_components",
        _close(volume_components, av, POWER_SUM_LIMIT),
    )
    require(
        "energy_and_absorption_closure",
        metrics["energy_closure_error"] <= PHYSICAL_LIMIT
        and metrics["port_volume_absorption_difference"] <= PHYSICAL_LIMIT,
    )
    require(
        "duplicated_port_record_agrees",
        all(
            _close(float(port[k]), float(power[k]), POWER_SUM_LIMIT)
            for k in (
                "R_total", "T_total", "R_plus_T", "A_balance",
                "R00_s", "R00_p", "R00_total",
            )
        ),
    )

    reference_authority = worker.get("reference_authority")
    reference_eval = worker.get("reference_evaluation", {})
    limitation = (
        reference_authority == "MATCHED_REFERENCE_NOT_AVAILABLE"
        and reference_eval.get("attempted") is False
    )
    require("reference_limit_recorded", limitation)
    status = (
        "PASS_WITH_AUTHORITY_LIMITATION"
        if not failures and limitation
        else "RAW_OUTPUT_CHECK_FAIL"
    )
    return {
        "schema": SCHEMA,
        "status": status,
        "run_id": manifest.get("run_id"),
        "source_sha": manifest.get("source_sha"),
        "input_sha256": input_sha,
        "checks": checks,
        "failures": failures,
        "residuals": {"final": final, "post_release": released},
        "physical_metrics": metrics,
        "artifacts": {
            "worker_summary_sha256": _sha256(
                root / "physical_dual_condensed_projection_layout_v31_summary.json"
            ),
            "run_manifest_sha256": _sha256(root / "run_manifest.json"),
            "run_summary_sha256": _sha256(root / "run_summary.json"),
            "final_residual_npz_sha256": final["archive_sha256"],
            "post_release_residual_npz_sha256": released["archive_sha256"],
            "official_output_npz_sha256": output_sha,
            "modal_orders_sha256": _sha256(
                root / "numerical_output/dtn_port_diffraction_orders_3d.json"
            ),
            "power_metrics_sha256": _sha256(
                root / "numerical_output/dtn_port_power_metrics_3d.json"
            ),
            "volume_absorption_sha256": _sha256(root / "numerical_output/volume_absorption.json"),
            "ordered_mode_manifest_sha256": _sha256(root / "v31q4_ordered_mode_manifest.json"),
        },
        "qualification": {
            "reference_authority": reference_authority,
            "field_error_l2_and_curl": "NOT_ATTEMPTED_NO_MATCHED_REFERENCE",
            "scope": (
                "raw residual-vector norms, official modal-power rows, and "
                "volume/port energy closure; no operator reconstruction or "
                "continuum-convergence claim"
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.run_directory.resolve()
    output = args.output.resolve() if args.output else root / "v31_raw_output_checker.json"
    try:
        result = check_run(root)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        result = {
            "schema": SCHEMA,
            "status": "EVIDENCE_INCOMPLETE",
            "failures": [f"{type(exc).__name__}: {exc}"],
        }
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "failures": result.get("failures", [])}))
    return 0 if result["status"] == "PASS_WITH_AUTHORITY_LIMITATION" else 2


if __name__ == "__main__":
    raise SystemExit(main())
