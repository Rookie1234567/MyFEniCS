from __future__ import annotations

import copy
from pathlib import Path

import numpy as np

import benchmarks.run_task037_extra_h2b as runner
from src.solvers.hcurl_h2b_m4y_packed_patch_pc import (
    H2BM4YPackedPatchPC,
    build_h2b_m4y_packed_patch_pc,
)
from src.solvers.hcurl_h2b_packed_patch_store import (
    build_h2b_m3y_packed_factor,
    build_h2b_m3y_packed_patch_store,
    load_h2b_m3y_packed_patch_store,
    write_h2b_m3y_packed_patch_store,
)


def _patch_matrix() -> np.ndarray:
    seed = np.asarray(
        (
            (1.0 + 0.1j, 0.2 - 0.2j, 0.1 + 0.3j),
            (0.3 + 0.1j, 1.1 + 0.2j, -0.1 + 0.1j),
            (0.2 - 0.1j, 0.1 + 0.2j, 0.9 + 0.1j),
        ),
        dtype=np.complex128,
    )
    return np.ascontiguousarray(seed @ seed.conj().T + 2.0 * np.eye(3))


def _global_matrix() -> np.ndarray:
    seed = np.asarray(
        (
            (1.0 + 0.1j, 0.1 - 0.2j, 0.2 + 0.1j, 0.0 + 0.1j, 0.1),
            (0.2 + 0.1j, 1.2 + 0.1j, 0.1 + 0.2j, 0.2, 0.0 - 0.1j),
            (0.1 - 0.1j, 0.2 + 0.1j, 1.1 + 0.2j, 0.1, 0.2j),
            (0.1 + 0.2j, 0.0 + 0.1j, 0.2, 1.3 + 0.1j, 0.1 - 0.1j),
            (0.2, 0.1 + 0.1j, 0.1 - 0.2j, 0.1 + 0.1j, 0.8 + 0.1j),
        ),
        dtype=np.complex128,
    )
    return np.ascontiguousarray(seed @ seed.conj().T + 3.0 * np.eye(5))


def _store(tmp_path: Path):
    factor = build_h2b_m3y_packed_factor(
        _patch_matrix(), task037_extra_h2b=True
    )
    neighborhoods = (
        {
            "neighborhood_id": 0,
            "key_sha256": "0" * 64,
            "cell_ordinals": [0],
            "multiplicity": 1,
            "factor_id": 0,
        },
        {
            "neighborhood_id": 1,
            "key_sha256": "1" * 64,
            "cell_ordinals": [1],
            "multiplicity": 1,
            "factor_id": 0,
        },
    )
    store = build_h2b_m3y_packed_patch_store(
        (factor,),
        neighborhoods,
        np.asarray([0, 1], dtype=np.int32),
        np.asarray([0, 3, 6], dtype=np.int64),
        np.asarray([0, 1, 2, 1, 2, 3], dtype=np.int64),
        identity={"source_identity": "a" * 64, "scope": "m4y-test"},
        task037_extra_h2b=True,
    )
    manifest = write_h2b_m3y_packed_patch_store(
        store, tmp_path / "m3y_store", task037_extra_h2b=True
    )
    return store, load_h2b_m3y_packed_patch_store(
        manifest, task037_extra_h2b=True
    )


def _valid_worker_payload() -> dict[str, object]:
    materialization = {
        key: False
        for key in (
            "global_matrix",
            "global_constraint_matrix",
            "patch_matrices",
            "static_condensation",
            "trace_slab",
            "schur",
            "slab_factor",
            "ql_qh_transform",
            "per_cell_factor",
        )
    }
    audit = {
        "cell_count": runner.H2B_FIXED_CELLS,
        "unique_factor_count": 84,
        "factor_reuse_count": 168,
        "factor_copy_count": 0,
        "per_cell_solution_retained": False,
        "m3y_retained_total_bytes": 1,
        "partition_of_unity_closure_error": 0.0,
        "fine_space": "uncondensed_fullspace",
        "ordinary_default_changed": False,
        "materialization_identity": materialization,
    }
    m3y_audit = {
        "packed_factor_count": 84,
        "cell_count": runner.H2B_FIXED_CELLS,
        "retained_total_bytes": 1,
        "retained_total_gate": True,
        "factorization_info_max": 0,
        "full_dense_factor_count": 0,
        "pivots_retained": False,
        "ordinary_default_changed": False,
        "materialization_identity": materialization,
    }
    action_audit = {
        "global_matrix_materialized": False,
        "global_constraint_matrix_materialized": False,
        "global_condensed_schur_materialized": False,
        "cell_schur_matrix_nnz": 0,
        "slab_matrix_nnz": 0,
        "cell_schur_matrix_materialized": False,
        "slab_matrix_materialized": False,
        "factor_count": 0,
        "ksp_created": False,
        "dtn_used": False,
        "ordinary_default_changed": False,
    }
    sources = [
        {
            "label": label,
            "rho": 0.1,
            "rho_limit": runner.H2B_M4Y_RHO_LIMITS[label],
            "finite": True,
            "deterministic": True,
            "action_repeat_relative_error": 0.0,
            "correction_repeat_relative_error": 0.0,
            "exact_action_count": 1,
            "partition_of_unity_closure_error": 0.0,
            "pc_action_wall_ratio": 1.0,
        }
        for label in runner.H2B_M4Y_SOURCE_LABELS
    ]
    return {
        "schema": runner.H2B_M4Y_WORKER_SCHEMA,
        "scope": runner._m4y_scope(),
        "p6": {
            "global_cells": runner.H2B_FIXED_CELLS,
            "local_cells": runner.H2B_FIXED_CELLS,
            "local_nloc": runner.H2B_FIXED_NLOC,
            "global_rows": runner.H2B_FIXED_ROWS,
            "constraint_count": runner.H2B_FIXED_CONSTRAINTS,
        },
        "form": {
            "role": "b0",
            "code_state": "hit_no_new_decl_impl",
            "jit_options": {},
            "form_compiler_options": {"scalar_type": "complex128"},
        },
        "measurement": {
            "p6": {
                "global_cells": runner.H2B_FIXED_CELLS,
                "local_cells": runner.H2B_FIXED_CELLS,
                "local_nloc": runner.H2B_FIXED_NLOC,
                "global_rows": runner.H2B_FIXED_ROWS,
                "constraint_count": runner.H2B_FIXED_CONSTRAINTS,
            },
            "m3y_store": {
                "source_sha256": runner.H2B_M4Y_M3Y_SOURCE_SHA,
                "manifest_sha256": runner.H2B_M4Y_M3Y_MANIFEST_SHA,
                "evidence_sha256": runner.H2B_M4Y_M3Y_EVIDENCE_SHA,
            },
            "pc_audit": audit,
            "m3y_store_audit": m3y_audit,
            "m3y_store_mmap_readonly": True,
            "action_audit": action_audit,
            "sources": sources,
            "array_artifacts": {},
            "exact_action_repeat_relative_error": 0.0,
            "pc_action_wall_ratio": 1.0,
            "resource": {"peak_rss_bytes": 1_000, "swap_bytes": 0},
            "cache": {"before": {}, "after": {}, "unchanged": True},
            "evidence_workspace_bytes": 0,
        },
    }


def test_m4y_overlap_pou_and_residual_minimizing_action(tmp_path):
    _store_unused, store = _store(tmp_path)
    matrix = _global_matrix()
    calls = []

    def exact_action(source: np.ndarray, target: np.ndarray) -> None:
        calls.append(1)
        target[:] = matrix @ source

    pc = build_h2b_m4y_packed_patch_pc(
        store,
        global_row_count=5,
        exact_action=exact_action,
        slave_identity_rows=(4,),
        task037_extra_h2b=True,
    )
    rhs = np.asarray(
        [1.0 + 0.2j, -0.2 + 0.4j, 0.7 - 0.1j, 0.3 + 0.5j, -0.4 + 0.2j],
        dtype=np.complex128,
    )
    correction, measurement = pc.apply_with_measurement(rhs)
    z0 = np.zeros(5, dtype=np.complex128)
    multiplicity = np.asarray([1.0, 2.0, 2.0, 1.0])
    for rows in (np.asarray([0, 1, 2]), np.asarray([1, 2, 3])):
        z0[rows] += store.solve(0, rhs[rows]) / multiplicity[rows]
    z0[4] = rhs[4]
    q = matrix @ z0
    omega = np.vdot(q, rhs) / np.vdot(q, q)
    assert np.allclose(correction, omega * z0, rtol=1e-13, atol=1e-13)
    assert measurement["omega"] == [float(omega.real), float(omega.imag)]
    assert "deterministic" not in measurement
    assert measurement["exact_action_count"] == 1
    assert len(calls) == 1
    assert pc.audit["partition_of_unity_closure_error"] == 0.0
    assert pc.audit["factor_copy_count"] == 0
    assert pc.audit["per_cell_solution_retained"] is False
    assert all(value is False for value in pc.audit["materialization_identity"].values())


def test_m4y_mmap_factor_is_shared_readonly_and_checker_missing_key_fails(tmp_path):
    _store_unused, store = _store(tmp_path)
    assert store.factor_for_cell(0) is store.factor_for_cell(1)
    assert isinstance(store.factor_for_cell(0).packed_values.base, np.memmap)
    assert store.factor_for_cell(0).packed_values.flags.writeable is False
    valid = _valid_worker_payload()
    assert runner._m4y_check_payload(valid)["pass"] is True
    for key in (
        "label",
        "rho",
        "rho_limit",
        "finite",
        "deterministic",
        "action_repeat_relative_error",
        "correction_repeat_relative_error",
        "exact_action_count",
        "partition_of_unity_closure_error",
        "pc_action_wall_ratio",
    ):
        candidate = copy.deepcopy(valid)
        del candidate["measurement"]["sources"][0][key]
        result = runner._m4y_check_payload(candidate)
        assert result["pass"] is False
    for key in (
        "cell_count",
        "unique_factor_count",
        "factor_reuse_count",
        "factor_copy_count",
        "per_cell_solution_retained",
        "m3y_retained_total_bytes",
        "partition_of_unity_closure_error",
        "fine_space",
        "ordinary_default_changed",
        "materialization_identity",
    ):
        candidate = copy.deepcopy(valid)
        del candidate["measurement"]["pc_audit"][key]
        result = runner._m4y_check_payload(candidate)
        assert result["pass"] is False
    for key in (
        "global_matrix_materialized",
        "global_constraint_matrix_materialized",
        "global_condensed_schur_materialized",
        "cell_schur_matrix_nnz",
        "slab_matrix_nnz",
        "cell_schur_matrix_materialized",
        "slab_matrix_materialized",
        "factor_count",
        "ksp_created",
        "dtn_used",
        "ordinary_default_changed",
    ):
        candidate = copy.deepcopy(valid)
        del candidate["measurement"]["action_audit"][key]
        result = runner._m4y_check_payload(candidate)
        assert result["pass"] is False
    for key in (
        "p6",
        "m3y_store",
        "m3y_store_audit",
        "m3y_store_mmap_readonly",
        "pc_audit",
        "action_audit",
        "sources",
        "array_artifacts",
        "exact_action_repeat_relative_error",
        "pc_action_wall_ratio",
        "resource",
        "cache",
        "evidence_workspace_bytes",
    ):
        candidate = copy.deepcopy(valid)
        del candidate["measurement"][key]
        result = runner._m4y_check_payload(candidate)
        assert result["pass"] is False


def test_m4y_cli_routes_and_build_only_audit_are_opt_in():
    parser = runner._parser()
    assert parser.parse_args(
        ["m4y-worker", "--run-dir", "/tmp/m4y", "--m3y-manifest", "/tmp/manifest.json"]
    ).command == "m4y-worker"
    assert parser.parse_args(["m4y-watchdog", "--run-dir", "/tmp/m4y"]).command == "m4y-watchdog"
    assert parser.parse_args(
        ["m4y-check", "--run-dir", "/tmp/m4y", "--output", "/tmp/m4y.json"]
    ).command == "m4y-check"
    assert H2BM4YPackedPatchPC.__module__.endswith("hcurl_h2b_m4y_packed_patch_pc")
