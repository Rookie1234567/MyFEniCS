from __future__ import annotations

import numpy as np

import benchmarks.run_task037_extra_h2b as runner
from src.solvers.hcurl_h2b_packed_patch_store import build_h2b_m3y_packed_factor


def _small_hpd() -> np.ndarray:
    seed = np.asarray(
        ((1.0 + 0.2j, 0.1 - 0.1j), (0.3 + 0.1j, 1.2 + 0.0j)),
        dtype=np.complex128,
        order="C",
    )
    return np.asarray(seed @ seed.conj().T + np.eye(2), dtype=np.complex128, order="C")


def _valid_audit() -> dict[str, object]:
    components = {"packed": 64, "metadata": 36}
    materialization = {
        "patch_matrices": False,
        "global_matrix": False,
        "global_constraint_matrix": False,
        "static_condensation": False,
        "trace_slab": False,
        "slab_factor": False,
        "schur": False,
        "ql_qh_transform": False,
        "per_cell_factor": False,
    }
    return {
        "schema": "task037.extra.h2b.m3y.packed-factor-store.v1",
        "packed_cholesky": True,
        "packed_factor_count": 1,
        "neighborhood_count": 84,
        "cell_count": 252,
        "packed_factor_bytes": 64,
        "metadata_mapping_bytes": 36,
        "retained_total_bytes": 100,
        "retained_total_limit_bytes": runner.H2B_M3Y_RETAINED_LIMIT_BYTES,
        "retained_total_gate": True,
        "retained_payload_components": components,
        "full_dense_factor_count": 0,
        "pivots_retained": False,
        "factorization_info_max": 0,
        "finite": True,
        "deterministic": True,
        "materialization_identity": materialization,
        "ordinary_default_changed": False,
    }


def test_m3y_fixed_rhs_and_packed_measurement_are_deterministic():
    matrix = _small_hpd()
    factor = build_h2b_m3y_packed_factor(matrix, task037_extra_h2b=True)
    first = runner._m3y_measure_factor(matrix, factor, 7)
    second = runner._m3y_measure_factor(matrix, factor, 7)
    assert first == second
    assert first["finite"] is True
    assert first["deterministic"] is True
    assert first["action_closure_relative_error"] <= runner.H2B_M3Y_CLOSURE_LIMIT
    assert runner._m3y_fixed_rhs(7, 2).dtype == np.dtype(np.complex128)


def test_m3y_audit_missing_key_fails_closed():
    audit = _valid_audit()
    assert runner._m3y_audit_valid(audit)
    del audit["factorization_info_max"]
    assert not runner._m3y_audit_valid(audit)


def test_m3y_phase_gate_is_strict_and_requires_process_cleanup():
    phase = {
        "return_code": 0,
        "termination": None,
        "processes_gone_before_m3y_loader": True,
        "peak_rss_bytes": runner.H2B_M3Y_BUILDER_RSS_LIMIT_BYTES - 1,
        "swap_bytes": 0,
    }
    assert runner._m3y_phase_ok(
        phase, runner.H2B_M3Y_BUILDER_RSS_LIMIT_BYTES, "processes_gone_before_m3y_loader"
    )
    phase["peak_rss_bytes"] = runner.H2B_M3Y_BUILDER_RSS_LIMIT_BYTES
    assert not runner._m3y_phase_ok(
        phase, runner.H2B_M3Y_BUILDER_RSS_LIMIT_BYTES, "processes_gone_before_m3y_loader"
    )


def test_m3y_parser_exposes_only_opt_in_routes_and_fixed_scope():
    parser = runner._parser()
    args = parser.parse_args(["m3y-builder", "--run-dir", "/tmp/m3y"])
    assert args.command == "m3y-builder"
    args = parser.parse_args(
        ["m3y-check", "--run-dir", "/tmp/m3y", "--output", "/tmp/m3y.json"]
    )
    assert args.command == "m3y-check"
    scope = runner._m3y_scope()
    assert scope["neighborhood_count"] == 84
    assert scope["global_matrix_materialized"] is False
    assert scope["static_condensation"] is False
    assert scope["trace_slab"] is False
    assert scope["schur"] is False
    assert runner._m3y_fixed_preflight()["predicted_live_set_gate"] is True
