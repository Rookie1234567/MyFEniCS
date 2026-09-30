#!/usr/bin/env python3
"""Re-evaluate v2 exact-geometry numeric gates separately from input coverage."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ATTEMPT = (
    ROOT
    / "benchmarks/artifacts/task40extra_0p7nm_engineering/"
    "exact_geometry_iteration8_replay_v2"
)
NUMERIC_LIMIT = 1.0e-10


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha_array(value: np.ndarray) -> str:
    array = np.ascontiguousarray(value)
    digest = hashlib.sha256(repr((array.shape, str(array.dtype))).encode())
    digest.update(memoryview(array).cast("B"))
    return digest.hexdigest()


def _relative_pass(value: Any) -> bool:
    return float(value) <= NUMERIC_LIMIT


def recheck(attempt: Path) -> dict[str, Any]:
    summary_path = attempt / "replay_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    watchdog_path = attempt / "watchdog_wrapper_result.json"
    watchdog = json.loads(watchdog_path.read_text(encoding="utf-8"))
    packet_path = attempt / "iteration8_exact_geometry_vectors.npz"
    packet = summary["residual_evaluation"]
    vector_facts = packet["vector_facts"]
    vector_checks: dict[str, Any] = {}
    with np.load(packet_path) as arrays:
        for name in arrays.files:
            value = np.asarray(arrays[name])
            expected = vector_facts[name]
            vector_checks[name] = {
                "finite": bool(np.isfinite(value).all()),
                "shape_matches": list(value.shape) == expected["shape"],
                "dtype_matches": str(value.dtype) == expected["dtype"],
                "content_hash_matches": _sha_array(value) == expected["sha256"],
            }
    vectors_bound_and_finite = bool(vector_checks) and all(
        all(check.values()) for check in vector_checks.values()
    )
    if _sha_file(packet_path) != packet["vectors_packet_sha256"]:
        vectors_bound_and_finite = False

    metrics = packet
    numeric_metrics = {
        "native_identity_relative": float(metrics["native_identity_relative"]),
        "internal_residual_relative": float(metrics["internal_residual_relative"]),
        "schur_port_identity_relative": float(
            metrics["schur_port_identity_relative"]
        ),
    }
    residual_numeric_pass = all(
        _relative_pass(value) for value in numeric_metrics.values()
    )
    raw_checks = summary["raw_tensor_spotchecks"]["checked_cells"]
    cell_rechecks = []
    for item in raw_checks:
        local = item["local_recovery_equation"]
        block_values = {
            name: float(block["relative_frobenius_error"])
            for name, block in item["blocks"].items()
        }
        numeric_values = {
            "raw_relative_frobenius_error": float(
                item["raw_relative_frobenius_error"]
            ),
            "oriented_relative_frobenius_error": float(
                item["oriented_relative_frobenius_error"]
            ),
            **{f"{name}_block_relative_error": value for name, value in block_values.items()},
            "raw_internal_residual_relative": float(
                local["raw_internal_residual_relative"]
            ),
            "difference_from_action_internal_residual_relative": float(
                local["difference_from_action_internal_residual_relative"]
            ),
        }
        numeric_pass = all(_relative_pass(value) for value in numeric_values.values())
        nonzero_terms = {
            "rhs_interior_nonzero_count": int(local["rhs_interior_nonzero_count"]),
            "Bi_alpha_nonzero_count": int(local["Bi_alpha_nonzero_count"]),
        }
        cell_rechecks.append(
            {
                "cell": int(item["cell"]),
                "numeric_values": numeric_values,
                "numeric_pass": numeric_pass,
                "nonzero_terms": nonzero_terms,
                "nonzero_term_coverage": all(value > 0 for value in nonzero_terms.values()),
            }
        )
    raw_numeric_pass = bool(cell_rechecks) and all(
        item["numeric_pass"] for item in cell_rechecks
    )
    term_coverage_complete = bool(cell_rechecks) and all(
        item["nonzero_term_coverage"] for item in cell_rechecks
    )
    watchdog_pass = (
        watchdog.get("classification") == "COMPLETED"
        and watchdog.get("leader_exit_code") == 0
        and watchdog.get("descendants_cleared") is True
    )
    numerical_pass = (
        vectors_bound_and_finite
        and residual_numeric_pass
        and raw_numeric_pass
        and watchdog_pass
    )
    r1 = json.loads(
        (ROOT / "docs/task40extra_0p7nm_engineering/outcomes/records/identity_localization_v1.json").read_text(
            encoding="utf-8"
        )
    )["R1"]["independent_internal_recovery"]
    return {
        "schema": "task40.exact_geometry_replay.postcheck.v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "attempt_directory": str(attempt),
        "source_sha": summary["source_sha"],
        "replay_script_sha256": summary["script_sha256"],
        "checker_script_sha256": _sha_file(Path(__file__).resolve()),
        "original_worker_status_preserved": summary["status"],
        "watchdog": {
            "classification": watchdog.get("classification"),
            "leader_exit_code": watchdog.get("leader_exit_code"),
            "elapsed_seconds": watchdog.get("elapsed_seconds"),
            "process_tree_rss_peak_bytes": watchdog.get(
                "sampled_process_tree_rss_peak_bytes"
            ),
            "swap_peak_bytes": watchdog.get("sampled_process_tree_swap_peak_bytes"),
            "descendants_cleared": watchdog.get("descendants_cleared"),
            "pass": watchdog_pass,
        },
        "vector_packet": {
            "sha256_matches_record": _sha_file(packet_path)
            == packet["vectors_packet_sha256"],
            "array_checks": vector_checks,
            "all_finite_and_hash_bound": vectors_bound_and_finite,
        },
        "numeric_gate_recheck": {
            "limit": NUMERIC_LIMIT,
            "residual_metrics": numeric_metrics,
            "residual_numeric_pass": residual_numeric_pass,
            "raw_cell_rechecks": cell_rechecks,
            "raw_numeric_pass": raw_numeric_pass,
            "native_residual_relative": float(metrics["native_residual_relative"]),
            "native_residual_is_convergence_gate": False,
            "iteration8_port_residual_relative": float(
                summary["iteration8_port_residual"]["relative"]
            ),
            "iteration8_port_residual_is_final_solve_gate": False,
            "numeric_checks_passed": numerical_pass,
        },
        "coverage": {
            "three_dominant_cells": [item["cell"] for item in cell_rechecks],
            "nonzero_local_rhs_and_Bi_alpha_required_for_numeric_pass": False,
            "nonzero_term_coverage_complete": term_coverage_complete,
            "observed_terms_by_cell": [item["nonzero_terms"] for item in cell_rechecks],
            "r1_global_Bi_nonzero_entries": int(r1["Bi_nonzero_entries"]),
            "r1_global_Di_nonzero_entries": int(r1["Di_nonzero_entries"]),
            "interpretation": (
                "The three geometry-dominant sample cells exercise zero local rhs and Bi*alpha; "
                "this is a coverage gap, not a numerical failure. Existing V19 fixtures cover "
                "nonzero complex local RHS and Bi/Di port terms."
            ),
            "existing_fixture_sources": [
                "src/test/test_task39extra_v19_p6_cell_condensed_action.py",
                "src/test/test_task39extra_v19_adapter_identity.py",
            ],
        },
        "recomputed_classification": (
            "numerical_pass_with_local_input_coverage_gap"
            if numerical_pass and not term_coverage_complete
            else "numerical_pass_and_coverage_complete"
            if numerical_pass
            else "numerical_gate_failure"
        ),
        "full_g0_run_count": 0,
        "direct_reference": "not_run",
        "finite_precision_budget_B": "not_enabled",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt", type=Path, default=DEFAULT_ATTEMPT)
    args = parser.parse_args()
    attempt = args.attempt.resolve()
    output = attempt / "numerical_gate_recheck.json"
    if output.exists():
        raise FileExistsError(f"refusing to overwrite additive recheck: {output}")
    result = recheck(attempt)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
