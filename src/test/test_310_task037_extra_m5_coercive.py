from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import numpy as np
from petsc4py import PETSc

import benchmarks.run_task037_extra_m5 as runner
from src.solvers.hcurl_h2b_m5_coercive import (
    M5M4YPCContext,
    M5ResidualCheckpointWriter,
    build_m5_b0_mat,
    evaluate_m5_screen_gate,
    run_m5_right_fgmres_screen,
)


class _Action:
    def __init__(self, diagonal: np.ndarray) -> None:
        self.diagonal = np.asarray(diagonal, dtype=np.complex128)
        self.output = PETSc.Vec().createSeq(self.diagonal.size, comm=PETSc.COMM_SELF)
        self.calls = 0

    def mult(self, source: PETSc.Vec) -> PETSc.Vec:
        self.output.getArray()[:] = self.diagonal * source.getArray(readonly=True)
        self.calls += 1
        return self.output

    def destroy(self) -> None:
        self.output.destroy()


def _vec(values: np.ndarray) -> PETSc.Vec:
    result = PETSc.Vec().createSeq(values.size, comm=PETSc.COMM_SELF)
    result.getArray()[:] = np.asarray(values, dtype=np.complex128)
    return result


def test_m5_matpython_and_right_pc_adapters_copy_owned_values():
    action = _Action(np.asarray([2.0 + 0.1j, 1.5 - 0.2j, 0.75 + 0.3j]))
    matrix, matrix_context = build_m5_b0_mat(
        action, owned_rows=3, global_rows=3, comm=PETSc.COMM_SELF
    )
    source = _vec(np.asarray([1.0 + 0.2j, -0.3 + 0.1j, 0.5 - 0.4j]))
    target = source.duplicate()
    pc_context = M5M4YPCContext(
        type("PC", (), {"apply": lambda self, values: 0.5 * values})(),
        global_rows=3,
    )
    pc_target = source.duplicate()
    try:
        matrix.mult(source, target)
        assert np.allclose(
            target.getArray(readonly=True), action.diagonal * source.getArray(readonly=True)
        )
        pc_context.apply(None, source, pc_target)
        assert np.allclose(pc_target.getArray(readonly=True), 0.5 * source.getArray(readonly=True))
        assert action.calls == 1
        assert matrix_context.audit["global_matrix_materialized"] is False
        assert matrix_context.audit["borrowed_action_output_copied"] is True
        assert pc_context.audit["pc_side"] == "right"
    finally:
        pc_target.destroy()
        target.destroy()
        source.destroy()
        matrix.destroy()
        action.destroy()


def test_m5_fixed_right_fgmres_writes_only_three_true_checkpoints(tmp_path: Path):
    diagonal = np.linspace(1.0, 2.0, 128).astype(np.complex128)
    action = _Action(diagonal)
    matrix, matrix_context = build_m5_b0_mat(
        action, owned_rows=diagonal.size, global_rows=diagonal.size, comm=PETSc.COMM_SELF
    )
    rhs = _vec(np.ones(diagonal.size, dtype=np.complex128))
    pc_context = M5M4YPCContext(
        type("PC", (), {"apply": lambda self, values: 0.5 * values})(),
        global_rows=diagonal.size,
    )
    try:
        screen = run_m5_right_fgmres_screen(
            matrix,
            rhs,
            pc_context=pc_context,
            operator_context=matrix_context,
            checkpoint_dir=tmp_path,
        )
        assert screen["ksp_type"] == "fgmres"
        assert screen["pc_side"] == "right"
        assert screen["norm_type"] == "unpreconditioned"
        assert screen["restart"] == 20
        assert screen["max_it"] == 100
        assert set(screen["samples"]) == {"20", "50", "100"}
        assert screen["sample_action_count"] == 3
        assert screen["operator_apply_count"] >= 3
        assert screen["pc_apply_count"] > 0
        for iteration in (20, 50, 100):
            assert (tmp_path / f"m5_iter{iteration}_rhs.npy").is_file()
            assert (tmp_path / f"m5_iter{iteration}_b0_action.npy").is_file()
            assert (tmp_path / f"m5_iter{iteration}_residual.npy").is_file()
            assert (tmp_path / f"m5_iter{iteration}_solution.npy").is_file()
    finally:
        rhs.destroy()
        matrix.destroy()
        action.destroy()


def test_m5_checkpoints_recompute_true_residual_and_gate(tmp_path: Path):
    rhs_values = np.asarray([1.0 + 0.0j, 2.0 - 0.5j, -0.25 + 0.75j])
    rhs = _vec(rhs_values)
    solution = _vec(np.asarray([0.1 + 0.2j, -0.2 + 0.1j, 0.4 - 0.3j]))
    b0_action = _vec(rhs_values.copy())
    residual = _vec(rhs_values.copy())
    writer = M5ResidualCheckpointWriter(tmp_path)
    records = {}
    try:
        for iteration, fraction in ((20, 0.30), (50, 0.20), (100, 0.0005)):
            b0_action.getArray()[:] = (1.0 - fraction) * rhs_values
            residual.getArray()[:] = fraction * rhs_values
            records[str(iteration)] = writer.write_checkpoint(
                iteration,
                solution=solution,
                b0_action=b0_action,
                residual=residual,
                rhs=rhs,
            )
    finally:
        residual.destroy()
        b0_action.destroy()
        solution.destroy()
        rhs.destroy()
    assert all(
        record["artifacts"]["rhs"]["path"].endswith("_rhs.npy")
        for record in records.values()
    )
    gate = evaluate_m5_screen_gate(
        records,
        online_peak_rss_bytes=runner.M5_ONLINE_RSS_LIMIT_BYTES - 1,
        online_swap_bytes=0,
        processes_gone=True,
    )
    assert gate["pass"] is True
    assert np.isclose(gate["true_residuals"]["20"], 0.3)
    assert np.isclose(gate["true_residuals"]["50"], 0.2)
    assert np.isclose(gate["true_residuals"]["100"], 0.0005)
    altered = copy.deepcopy(records)
    altered["100"]["true_relative_residual"] = 0.9
    assert evaluate_m5_screen_gate(
        altered,
        online_peak_rss_bytes=runner.M5_ONLINE_RSS_LIMIT_BYTES - 1,
        online_swap_bytes=0,
        processes_gone=True,
    )["pass"] is False


def test_m5_checkpoint_contract_binds_arrays_and_rhs(tmp_path: Path, monkeypatch):
    values = np.asarray([1.0 + 0.25j, -0.5 + 0.75j, 0.125 - 0.25j])
    rhs_sha = hashlib.sha256(values.tobytes()).hexdigest()
    monkeypatch.setattr(runner, "M5_RHS_SHA256", rhs_sha)
    rhs = _vec(values)
    solution = _vec(np.zeros(values.size, dtype=np.complex128))
    b0_action = _vec(0.75 * values)
    residual = _vec(0.25 * values)
    try:
        record = M5ResidualCheckpointWriter(tmp_path).write_checkpoint(
            20,
            solution=solution,
            b0_action=b0_action,
            residual=residual,
            rhs=rhs,
        )
    finally:
        residual.destroy()
        b0_action.destroy()
        solution.destroy()
        rhs.destroy()
    assert runner._m5_checkpoint_contract(tmp_path, record)[0] is True

    original = (tmp_path / "m5_iter20_b0_action.npy").read_bytes()
    np.save(
        tmp_path / "m5_iter20_b0_action.npy",
        np.ones(values.size, dtype=np.complex128),
        allow_pickle=False,
    )
    assert runner._m5_checkpoint_contract(tmp_path, record)[0] is False
    (tmp_path / "m5_iter20_b0_action.npy").write_bytes(original)

    tampered_rhs = copy.deepcopy(record)
    tampered_rhs["artifacts"]["rhs"]["array_sha256"] = "0" * 64
    assert runner._m5_checkpoint_contract(tmp_path, tampered_rhs)[0] is False
    tampered_path = copy.deepcopy(record)
    tampered_path["artifacts"]["solution"]["path"] = "other.npy"
    assert runner._m5_checkpoint_contract(tmp_path, tampered_path)[0] is False


def test_m5_worker_contract_is_narrow_and_missing_keys_fail_closed():
    false_materialization = {
        "global_matrix": False,
        "global_constraint_matrix": False,
        "patch_matrices": False,
        "static_condensation": False,
        "trace_slab": False,
        "schur": False,
        "slab_factor": False,
        "ql_qh_transform": False,
        "per_cell_factor": False,
    }
    valid = {
        "schema": runner.M5_WORKER_SCHEMA,
        "scope": runner._m5_scope(),
        "measurement": {
            "p6": {
                "global_cells": 252,
                "local_cells": 252,
                "local_nloc": 882,
                "global_rows": 173802,
                "constraint_count": 9210,
            },
            "rhs": {
                "label": "physical-RHS-like",
                "sha256": runner.M5_RHS_SHA256,
                "definition": "physical-RHS-like primal, slave rows zero, exact B0 action",
            },
            "rhs_binding": {
                "label": "physical-RHS-like",
                "sha256": runner.M5_RHS_SHA256,
                "definition": "physical-RHS-like primal, slave rows zero, exact B0 action",
            },
            "m3y_binding": {
                "source_sha256": runner.h2b.H2B_M4Y_M3Y_SOURCE_SHA,
                "manifest_sha256": runner.h2b.H2B_M4Y_M3Y_MANIFEST_SHA,
                "evidence_sha256": runner.h2b.H2B_M4Y_M3Y_EVIDENCE_SHA,
            },
            "screen": {
                "ksp_type": "fgmres",
                "pc_side": "right",
                "norm_type": "unpreconditioned",
                "restart": 20,
                "max_it": 100,
                "fixed_screen": True,
                "iterations": 100,
                "final": None,
                "sample_action_count": 3,
                "operator_apply_count": 3,
                "pc_apply_count": 4,
                "rtol": 0.0,
                "atol": 0.0,
                "restart_set": 20,
                "max_it_actual": 100,
                "samples": {"20": {}, "50": {}, "100": {}},
            },
            "m3y_store_audit": {
                "packed_factor_count": 84,
                "cell_count": 252,
                "retained_total_bytes": 525196562,
                "retained_total_gate": True,
                "factorization_info_max": 0,
                "full_dense_factor_count": 0,
                "pivots_retained": False,
                "ordinary_default_changed": False,
                "materialization_identity": false_materialization,
            },
            "m3y_store_mmap_readonly": True,
            "operator_action_audit": {"apply_count": 3},
            "pc_action_audit": {"apply_count": 4},
            "form": {"role": "b0", "code_state": "hit_no_new_decl_impl"},
            "cache": {"before": [], "after": [], "unchanged": True},
            "action_audit": {
                "global_matrix_materialized": False,
                "global_constraint_matrix_materialized": False,
                "global_condensed_schur_materialized": False,
                "cell_schur_matrix_nnz": 0,
                "slab_matrix_nnz": 0,
                "cell_schur_matrix_materialized": False,
                "slab_matrix_materialized": False,
                "dtn_used": False,
                "ordinary_default_changed": False,
                "factor_count": 0,
                "ksp_created": False,
                "apply_count": 8,
            },
            "pc_audit": {
                "unique_factor_count": 84,
                "factor_reuse_count": 168,
                "factor_copy_count": 0,
                "per_cell_solution_retained": False,
                "m3y_retained_total_bytes": 525196562,
                "partition_of_unity_closure_error": 0.0,
                "fine_space": "uncondensed_fullspace",
                "ordinary_default_changed": False,
                "materialization_identity": false_materialization,
            },
            "architecture": {
                "fine_space": "uncondensed_fullspace",
                "global_matrix_materialized": False,
                "static_condensation": False,
                "trace_slab": False,
                "dtn": False,
                "coarse_constructed": False,
                "pde": False,
                "ordinary_default_changed": False,
            },
        },
    }
    assert runner._m5_check_payload(valid)["pass"] is True
    for path in (
        ("scope",),
        ("measurement", "p6"),
        ("measurement", "screen"),
        ("measurement", "rhs_binding"),
        ("measurement", "m3y_binding"),
        ("measurement", "m3y_store_audit"),
        ("measurement", "pc_audit"),
        ("measurement", "action_audit"),
        ("measurement", "screen", "fixed_screen"),
        ("measurement", "architecture"),
    ):
        candidate = copy.deepcopy(valid)
        cursor = candidate
        for key in path[:-1]:
            cursor = cursor[key]
        del cursor[path[-1]]
        result = runner._m5_check_payload(candidate)
        assert result["pass"] is False
        assert result["problems"]
    assert runner._parser().parse_args(
        ["m5-worker", "--run-dir", "/tmp/m5"]
    ).command == "m5-worker"
    assert runner._parser().parse_args(
        ["m5-check", "--run-dir", "/tmp/m5", "--output", "/tmp/m5.json"]
    ).command == "m5-check"


def test_m5_progress_events_include_space_before_cache():
    assert runner.M5_EVENTS == (
        "authority_validated",
        "mesh_ready",
        "space_ready",
        "floquet_mpc_ready",
        "cache_load_ready",
        "source_ready",
        "outer_ksp_ready",
        "summary_ready",
    )
