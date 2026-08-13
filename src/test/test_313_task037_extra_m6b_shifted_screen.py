from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import pytest
from petsc4py import PETSc

import benchmarks.run_task037_extra_m6b as runner
from src.solvers.hcurl_h2b_m6b_shifted_lu_store import (
    H2BM6BShiftedLUFactor,
    H2BM6BShiftedLUPatchStore,
    build_h2b_m6b_shifted_lu_factor,
    build_h2b_m6b_shifted_lu_patch_store,
    load_h2b_m6b_shifted_lu_patch_store,
    shifted_lu_factor_nbytes,
    stream_write_h2b_m6b_shifted_lu_patch_store,
    write_h2b_m6b_shifted_lu_patch_store,
)
from src.solvers.hcurl_h2b_m6b_shifted_patch_pc import (
    H2BM6BShiftedPatchPC,
    M6BOuterMatPythonContext,
    M6BShiftedPCContext,
    build_m6b_outer_mat,
    compose_m6b_physical_rhs,
    evaluate_m6b_screen_gate,
)


def _local_matrix() -> np.ndarray:
    return np.asarray(
        (
            (2.0 + 0.4j, 0.2 - 0.1j, 0.1 + 0.2j),
            (0.3 + 0.1j, 1.7 + 0.2j, -0.2 + 0.1j),
            (0.1 - 0.3j, 0.2 + 0.2j, 1.4 + 0.5j),
        ),
        dtype=np.complex128,
        order="C",
    )


def _store(tmp_path: Path) -> H2BM6BShiftedLUPatchStore:
    factor = build_h2b_m6b_shifted_lu_factor(
        _local_matrix(), task037_extra_m6b=True
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
    store = build_h2b_m6b_shifted_lu_patch_store(
        (factor,),
        neighborhoods,
        np.asarray([0, 1], dtype=np.int32),
        np.asarray([0, 3, 6], dtype=np.int64),
        np.asarray([0, 1, 2, 1, 2, 3], dtype=np.int64),
        identity={
            "source_provenance": "test",
            "beta": 1.0,
            "operator": "synthetic shifted full-space",
        },
        task037_extra_m6b=True,
    )
    manifest = write_h2b_m6b_shifted_lu_patch_store(
        store, tmp_path / "shifted_store", task037_extra_m6b=True
    )
    return load_h2b_m6b_shifted_lu_patch_store(
        manifest, task037_extra_m6b=True
    )


def _single_cell_store(tmp_path: Path) -> H2BM6BShiftedLUPatchStore:
    factor = build_h2b_m6b_shifted_lu_factor(
        _local_matrix(), task037_extra_m6b=True
    )
    store = build_h2b_m6b_shifted_lu_patch_store(
        (factor,),
        ({
            "neighborhood_id": 0,
            "key_sha256": "2" * 64,
            "cell_ordinals": [0],
            "multiplicity": 1,
            "factor_id": 0,
        },),
        np.asarray([0], dtype=np.int32),
        np.asarray([0, 3], dtype=np.int64),
        np.asarray([0, 1, 2], dtype=np.int64),
        identity={"source_provenance": "test-slave", "beta": 1.0},
        task037_extra_m6b=True,
    )
    manifest = write_h2b_m6b_shifted_lu_patch_store(
        store, tmp_path / "single_shifted_store", task037_extra_m6b=True
    )
    return load_h2b_m6b_shifted_lu_patch_store(
        manifest, task037_extra_m6b=True
    )


def test_m6b_zgetrf_roundtrip_and_exact_factor_bytes(tmp_path: Path):
    matrix = _local_matrix()
    factor = build_h2b_m6b_shifted_lu_factor(
        matrix, task037_extra_m6b=True
    )
    rhs = np.asarray([1.0 + 0.2j, -0.3 + 0.4j, 0.5 - 0.1j], dtype=np.complex128)
    solution = factor.solve(rhs)
    assert np.linalg.norm(matrix @ solution - rhs) <= 1.0e-12
    assert factor.factorization_info == 0
    assert factor.factor_nbytes == shifted_lu_factor_nbytes(3)
    assert factor.audit_jsonable()["full_dense_patch_matrix_retained"] is False
    assert factor.audit_jsonable()["pivots_retained"] is not False


def test_m6b_cold_store_is_mmap_readonly_and_factor_is_shared(tmp_path: Path):
    store = _store(tmp_path)
    assert store.factor_for_cell(0) is store.factor_for_cell(1)
    factor = store.factor_for_cell(0)
    assert isinstance(factor.lu.base, np.memmap)
    assert isinstance(factor.pivots.base, np.memmap)
    assert factor.lu.flags.writeable is False
    assert factor.pivots.flags.writeable is False
    audit = store.audit_jsonable()
    assert audit["factor_count"] == 1
    assert audit["factor_reuse_count"] == 1
    assert audit["factor_copy_count"] == 0
    assert audit["full_dense_patch_matrix_retained"] is False
    assert audit["materialization_identity"]["global_matrix"] is False


def test_m6b_stream_writer_binds_repeat_matrix_and_factor_sha(tmp_path: Path):
    matrix = np.eye(882, dtype=np.complex128) * (2.0 + 0.25j)
    factor = build_h2b_m6b_shifted_lu_factor(
        matrix, task037_extra_m6b=True
    )
    record = {
        "neighborhood_id": 0,
        "key_sha256": "3" * 64,
        "first_matrix_sha256": factor.matrix_sha256,
        "repeat_matrix_sha256": factor.matrix_sha256,
        "expected_matrix_sha256": factor.matrix_sha256,
        "repeat_factor_sha256": factor.factor_sha256,
        "expected_factor_sha256": factor.factor_sha256,
    }

    def records():
        yield record, matrix

    manifest = stream_write_h2b_m6b_shifted_lu_patch_store(
        records(),
        tmp_path / "streamed_shifted_store",
        np.asarray([0], dtype=np.int32),
        np.asarray([0, 882], dtype=np.int64),
        np.arange(882, dtype=np.int64),
        neighborhoods=(
            {"neighborhood_id": 0, "key_sha256": "3" * 64},
        ),
        identity={"source_provenance": "test", "beta": 1.0},
        expected_factor_count=1,
        expected_neighborhood_count=1,
        task037_extra_m6b=True,
    )
    observed = json.loads(manifest.read_text(encoding="utf-8"))["neighborhoods"][0]
    assert observed["matrix_sha256"] == factor.matrix_sha256
    assert observed["factor_sha256"] == factor.factor_sha256

    bad_record = dict(record)
    bad_record["expected_factor_sha256"] = "0" * 64

    def bad_records():
        yield bad_record, matrix

    with pytest.raises(ValueError, match="factor SHA"):
        stream_write_h2b_m6b_shifted_lu_patch_store(
            bad_records(),
            tmp_path / "bad_streamed_shifted_store",
            np.asarray([0], dtype=np.int32),
            np.asarray([0, 882], dtype=np.int64),
            np.arange(882, dtype=np.int64),
            neighborhoods=(
                {"neighborhood_id": 0, "key_sha256": "3" * 64},
            ),
            identity={"source_provenance": "test", "beta": 1.0},
            expected_factor_count=1,
            expected_neighborhood_count=1,
            task037_extra_m6b=True,
        )


def test_m6b_nonhermitian_pc_uses_conjugate_omega_and_one_shifted_action(tmp_path: Path):
    store = _store(tmp_path)
    global_matrix = np.asarray(
        (
            (1.5 + 0.2j, 0.1, 0.0, 0.0),
            (0.2 - 0.1j, 1.2 + 0.3j, 0.1, 0.0),
            (0.0, 0.2, 1.4 - 0.1j, 0.2),
            (0.0, 0.0, 0.1 + 0.2j, 0.9 + 0.4j),
        ),
        dtype=np.complex128,
    )
    calls: list[np.ndarray] = []

    def shifted_action(values: np.ndarray) -> np.ndarray:
        calls.append(np.array(values, copy=True))
        return np.ascontiguousarray(global_matrix @ values)

    rhs = np.asarray([1.0 + 0.2j, -0.3 + 0.1j, 0.4 - 0.2j, 0.7 + 0.3j])
    pc = H2BM6BShiftedPatchPC(
        store,
        global_row_count=4,
        shifted_action=shifted_action,
        task037_extra_m6b=True,
    )
    correction, measurement = pc.apply_with_measurement(rhs)
    z0 = np.zeros(4, dtype=np.complex128)
    z0[:3] = store.solve(0, rhs[:3])
    z0[1:4] += store.solve(1, rhs[1:4])
    z0[1:3] /= 2.0
    q = global_matrix @ z0
    omega = np.vdot(q, rhs) / np.vdot(q, q)
    assert np.allclose(correction, omega * z0, rtol=1.0e-13, atol=1.0e-13)
    assert measurement["omega"] == [float(omega.real), float(omega.imag)]
    assert measurement["exact_shifted_action_count"] == 1
    assert len(calls) == 1
    assert measurement["rho_star"] <= measurement["rho_unit"]
    assert pc.audit["factor_reuse_count"] == 1
    assert pc.audit["per_cell_solution_retained"] is False


def test_m6b_pc_batches_reused_factor_solves_and_matches_cell_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = _store(tmp_path)
    calls = []
    original_solve = H2BM6BShiftedLUFactor.solve

    def counted_solve(self, rhs):
        calls.append(np.asarray(rhs).shape)
        return original_solve(self, rhs)

    monkeypatch.setattr(H2BM6BShiftedLUFactor, "solve", counted_solve)
    pc = H2BM6BShiftedPatchPC(
        store,
        global_row_count=4,
        shifted_action=lambda values: np.array(values, copy=True),
        task037_extra_m6b=True,
    )
    rhs = np.asarray([1.0 + 0.2j, -0.3 + 0.1j, 0.4 - 0.2j, 0.7 + 0.3j])
    observed, _ = pc.apply_with_measurement(rhs)
    local0 = store.solve(0, rhs[:3])
    local1 = store.solve(1, rhs[1:4])
    expected = np.zeros(4, dtype=np.complex128)
    expected[:3] += local0
    expected[1:4] += local1
    expected[1:3] /= 2.0
    omega = np.vdot(expected, rhs) / np.vdot(expected, expected)
    assert np.allclose(observed, expected * omega)
    assert calls[0] == (3, 2)
    assert pc.audit["solve_count_per_apply"] == 1
    assert pc.audit["rhs_count"] == 2
    assert pc.audit["factor_reuse_exercised"] == 1


def test_m6b_slave_identity_row_is_carried_without_a_patch_factor(tmp_path: Path):
    store = _single_cell_store(tmp_path)
    matrix = np.eye(4, dtype=np.complex128) * (1.0 + 0.2j)
    calls = []

    def shifted_action(values: np.ndarray) -> np.ndarray:
        calls.append(1)
        return matrix @ values

    rhs = np.asarray([1.0 + 0.1j, -0.2 + 0.4j, 0.5 - 0.3j, 0.7 + 0.8j])
    pc = H2BM6BShiftedPatchPC(
        store,
        global_row_count=4,
        shifted_action=shifted_action,
        slave_identity_rows=(3,),
        task037_extra_m6b=True,
    )
    correction, measurement = pc.apply_with_measurement(rhs)
    assert np.allclose(
        correction[3],
        rhs[3] * (measurement["omega"][0] + 1j * measurement["omega"][1]),
    )
    assert measurement["exact_shifted_action_count"] == 1
    assert len(calls) == 1


class _Volume:
    def __init__(self, values: np.ndarray) -> None:
        self.values = np.asarray(values, dtype=np.complex128)
        self.output = PETSc.Vec().createSeq(self.values.size, comm=PETSc.COMM_SELF)
        self.calls = 0

    def mult(self, source: PETSc.Vec) -> PETSc.Vec:
        self.output.getArray()[:] = self.values * source.getArray(readonly=True)
        self.calls += 1
        return self.output


class _Dtn:
    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        target.getArray()[:] = 2.0 * source.getArray(readonly=True)

    def compose_physical_rhs(self, base: PETSc.Vec, amplitudes: np.ndarray, target: PETSc.Vec) -> None:
        target.getArray()[:] = base.getArray(readonly=True) + amplitudes[0]


def test_m6b_outer_sum_and_complete_physical_rhs_without_global_matrix():
    volume = _Volume(np.asarray([1.0 + 0.1j, 2.0 - 0.2j]))
    dtn = _Dtn()
    context = M6BOuterMatPythonContext(volume, dtn, owned_rows=2, global_rows=2)
    source = PETSc.Vec().createSeq(2, comm=PETSc.COMM_SELF)
    target = source.duplicate()
    base = source.duplicate()
    rhs = source.duplicate()
    source.getArray()[:] = [1.0 + 0.2j, -0.5 + 0.1j]
    base.getArray()[:] = [3.0, 4.0]
    try:
        context.mult(None, source, target)
        assert np.allclose(
            target.getArray(readonly=True),
            volume.values * source.getArray(readonly=True)
            + 2.0 * source.getArray(readonly=True),
        )
        compose_m6b_physical_rhs(dtn, base, np.asarray([0.25 + 0.5j]), rhs)
        assert np.allclose(rhs.getArray(readonly=True), base.getArray(readonly=True) + 0.25 + 0.5j)
        assert context.audit["global_matrix"] is False
        assert context.audit["augmented_matrix"] is False
        assert context.audit["explicit_C_materialized_count"] == 0
        source.getArray()[:] = [0.25 - 0.1j, 0.75 + 0.2j]
        context.mult(None, source, target)
        assert np.allclose(
            target.getArray(readonly=True),
            volume.values * source.getArray(readonly=True)
            + 2.0 * source.getArray(readonly=True),
        )
    finally:
        rhs.destroy()
        base.destroy()
        target.destroy()
        source.destroy()
        context.destroy()
        volume.output.destroy()


def test_m6b_outer_mat_destroy_callback_is_idempotent_and_preserves_borrowed_output():
    volume = _Volume(np.asarray([1.0 + 0.1j, 2.0 - 0.2j]))
    dtn = _Dtn()
    matrix, context = build_m6b_outer_mat(
        volume,
        dtn,
        owned_rows=2,
        global_rows=2,
        comm=PETSc.COMM_SELF,
    )
    source = PETSc.Vec().createSeq(2, comm=PETSc.COMM_SELF)
    target = source.duplicate()
    try:
        source.getArray()[:] = [1.0 + 0.2j, -0.5 + 0.1j]
        matrix.mult(source, target)
        matrix.destroy()
        context.destroy()
        assert volume.output.getSize() == 2
    finally:
        context.destroy()
        target.destroy()
        source.destroy()
        volume.output.destroy()


def test_m6b_petsc_pc_context_uses_unmeasured_core_apply():
    class Core:
        audit = {}

        def apply(self, values):
            return np.array(values, dtype=np.complex128, copy=True)

        def apply_with_measurement(self, _values):
            raise AssertionError("production PC path must not collect diagnostics")

    source = PETSc.Vec().createSeq(2, comm=PETSc.COMM_SELF)
    target = source.duplicate()
    try:
        source.getArray()[:] = [1.0 + 0.2j, -0.5 + 0.1j]
        context = M6BShiftedPCContext(Core())
        context.apply(None, source, target)
        assert np.array_equal(target.getArray(readonly=True), source.getArray(readonly=True))
        assert context.audit["last_measurement"] is None
    finally:
        target.destroy()
        source.destroy()


def _valid_worker_payload() -> dict[str, object]:
    lifecycle = {
        "return_code": 0,
        "termination": None,
        "processes_gone": True,
        "peak_rss_bytes": runner.M6B_ONLINE_COMPLETION_RSS_LIMIT_BYTES - 1,
        "swap_bytes": 0,
        "compiler_descendant_pids": [],
        "watchdog_rss_limit_bytes": runner.M6B_WATCHDOG_RSS_LIMIT_BYTES,
        "completion_rss_limit_bytes": runner.M6B_ONLINE_COMPLETION_RSS_LIMIT_BYTES,
        "timeout_seconds": runner.M6B_ONLINE_TIMEOUT_SECONDS,
    }
    source = {
        "source_commit_full_sha": "a" * 40,
        "tracked_source_dirty": False,
    }
    runtime = {
        "qualified_activation": "1",
        "sys_executable": "/tmp/repo/.venv/bin/python",
        "petsc_scalar_type": "complex128",
        "petsc_int_type": "int32",
        "threads": {
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
        },
        "compiler": {"identity": "synthetic"},
        "mpi_size": 1,
    }
    probe_hashes = {
        "rhs_sha256": "b" * 64,
        "correction0_sha256": "c" * 64,
        "action_sha256": "d" * 64,
        "correction_sha256": "e" * 64,
        "residual_sha256": "f" * 64,
    }
    probe = {
        "wall_seconds": 1.0,
        "hashes": probe_hashes,
        "finite": True,
        "exact_shifted_action_count": 1,
        "partition_of_unity_closure_error": 0.0,
    }
    stage_lifecycle = dict(lifecycle)
    stage_lifecycle["timeout_seconds"] = runner.M6B_STAGE_TIMEOUT_SECONDS
    payload = {
        "schema": runner.M6B_WORKER_SCHEMA,
        "scope": runner._m6b_scope(phase="mpi1"),
        "p6": {
            "global_cells": runner.M6B_GLOBAL_CELLS,
            "local_cells": runner.M6B_GLOBAL_CELLS,
            "local_nloc": runner.M6B_LOCAL_NLOC,
            "global_rows": runner.M6B_GLOBAL_ROWS,
            "constraint_count": runner.M6B_CONSTRAINTS,
        },
        "source_at_start": source,
        "source_at_end": dict(source),
        "runtime_identity": runtime,
        "cache": {"stage": [], "before": [], "after": [], "final": [], "unchanged": True},
        "pc_repeat": {"first": probe, "second": copy.deepcopy(probe), "identical": True},
        "stage": stage_lifecycle,
        "online": dict(lifecycle),
        "factor_store": {
            "schema": "task037.extra.h2b.m6b.shifted-lu-store.v1",
            "beta": 1.0,
            "factor_order": 882,
            "factor_count": 84,
            "cell_count": 252,
            "factor_payload_bytes": runner.M6B_FACTOR_PAYLOAD_BYTES,
            "retained_total_bytes": runner.M6B_FACTOR_PAYLOAD_BYTES + 100,
            "retained_total_gate": True,
            "factor_reuse_count": 168,
            "factor_copy_count": 0,
            "mmap_loaded": True,
            "full_dense_patch_matrix_retained": False,
            "pivots_retained": True,
            "mmap_readonly": True,
            "max_live_patch_matrix_count": 1,
            "max_live_lu_factor_count": 1,
            "materialization_identity": {
                "global_matrix": False,
                "global_constraint_matrix": False,
                "patch_matrices": False,
                "per_cell_factor": False,
                "static_condensation": False,
                "trace_slab": False,
                "schur": False,
                "slab_factor": False,
            },
        },
        "screen": {
            "20": {"true_relative_residual": 0.50},
            "100": {"true_relative_residual": 0.10},
            "150": {"true_relative_residual": 0.10},
            "200": {"true_relative_residual": 0.05},
        },
        "architecture": {
            "global_matrix": False,
            "fine_space": "uncondensed_fullspace",
            "augmented_matrix": False,
            "static_condensation": False,
            "trace_slab_pc": False,
            "explicit_C_materialized_count": 0,
            "explicit_D_materialized_count": 0,
            "dtn": True,
            "pde": False,
        },
    }
    builder_factor = copy.deepcopy(payload["factor_store"])
    builder_factor["mmap_loaded"] = False
    builder_factor["mmap_readonly"] = False
    payload["builder_factor_audit"] = builder_factor
    screen_metadata = {
        "schema": "task037.extra.h2b.m6b.screen.v1",
        "rows": runner.M6B_GLOBAL_ROWS,
        "ksp_type": "fgmres",
        "pc_side": "right",
        "norm_type": "unpreconditioned",
        "restart_set": 20,
        "max_it": 200,
        "max_it_actual": 200,
        "rtol": 0.0,
        "atol": 0.0,
        "iterations": 200,
        "converged_reason": -3,
        "fixed_screen": True,
        "operator_apply_count": 200,
        "pc_apply_count": 200,
        "sample_action_count": 4,
        "samples": copy.deepcopy(payload["screen"]),
    }
    pc_audit = {
        "schema": "task037.extra.h2b.m6b.shifted-patch-pc.v1",
        "beta": 1.0,
        "unique_factor_count": 84,
        "solve_count_per_apply": 84,
        "factor_reuse_count": 168,
        "factor_reuse_exercised": 168,
        "rhs_count": 252,
        "factor_copy_count": 0,
        "per_cell_solution_retained": False,
        "fine_space": "uncondensed_fullspace",
        "partition_of_unity_closure_error": 0.0,
        "materialization_identity": {
            "global_matrix": False,
            "global_constraint_matrix": False,
            "patch_matrices": False,
            "per_cell_factor": False,
            "static_condensation": False,
            "trace_slab": False,
            "schur": False,
            "slab_factor": False,
        },
    }
    payload["screen_metadata"] = screen_metadata
    payload["phase_source_identity"] = {
        "pass": True,
        "source_commit_full_sha": source["source_commit_full_sha"],
        "phase_names": ["stage", "builder", "online", "watchdog"],
        "all_tracked_source_clean": True,
    }
    payload["online_measurement"] = {
        "screen": copy.deepcopy(screen_metadata),
        "pc_audit": pc_audit,
    }
    return payload


def test_m6b_checker_and_screen_gate_fail_closed_on_missing_or_tampered_keys():
    valid = _valid_worker_payload()
    assert runner._m6b_check_payload(valid)["pass"] is True
    assert valid["online_measurement"]["screen"]["samples"] == valid["screen"]
    assert evaluate_m6b_screen_gate(
        valid["screen"],
        online_peak_rss_bytes=runner.M6B_ONLINE_COMPLETION_RSS_LIMIT_BYTES - 1,
        online_swap_bytes=0,
        processes_gone=True,
    )["pass"] is True
    missing = copy.deepcopy(valid)
    del missing["factor_store"]["factor_payload_bytes"]
    assert runner._m6b_check_payload(missing)["pass"] is False
    bad_screen = copy.deepcopy(valid)
    bad_screen["screen"]["200"]["true_relative_residual"] = 0.50
    assert runner._m6b_check_payload(bad_screen)["pass"] is False
    bad_arch = copy.deepcopy(valid)
    bad_arch["architecture"]["global_matrix"] = True
    assert runner._m6b_check_payload(bad_arch)["pass"] is False
    bad_phase_source = copy.deepcopy(valid)
    bad_phase_source["phase_source_identity"]["source_commit_full_sha"] = "0" * 40
    assert runner._m6b_check_payload(bad_phase_source)["pass"] is False


def test_m6b_nonnegative_evidence_quantities_fail_closed():
    valid = _valid_worker_payload()
    bad_screen = copy.deepcopy(valid["screen"])
    bad_screen["20"]["true_relative_residual"] = -1.0
    assert runner._m6b_screen_valid(bad_screen) is False

    builder = {
        "sample_patch_action_closure": {"0": 0.0, "42": 0.0, "83": 0.0},
        "class_block_audit": {
            "class_count": 24,
            "factor_count": 24,
            "reconstruction_count": 24,
            "fresh_B_beta_class_count": 24,
            "fresh_B_beta_matrix_count": 24,
            "operator_identity": "B_beta=Kcurl-k0^2*M_epsilon+i*k0^2*M_abs_epsilon",
            "numeric_matrix_source": "fresh_transformed_B_beta_class_block",
            "r2_numeric_store_used_for_blocks": False,
            "global_matrix_materialized": False,
        },
        "cache": {"stage": [], "before": [], "after": [], "unchanged": True},
    }
    builder["sample_patch_action_closure"]["42"] = -1.0
    assert runner._m6b_builder_summary_valid(builder) is False

    bad_pc = copy.deepcopy(valid["online_measurement"]["pc_audit"])
    bad_pc["partition_of_unity_closure_error"] = -1.0
    assert runner._m6b_pc_audit_valid(bad_pc) is False

    for side in ("first", "second"):
        bad_repeat = copy.deepcopy(valid)
        bad_repeat["pc_repeat"][side]["partition_of_unity_closure_error"] = -1.0
        assert runner._m6b_check_payload(bad_repeat)["pass"] is False


def test_m6b_progress_constants_keep_dependency_order():
    assert runner.M6B_BUILDER_EVENTS.index("class_expansion_ready") < runner.M6B_BUILDER_EVENTS.index(
        "class_blocks_ready"
    ) < runner.M6B_BUILDER_EVENTS.index("neighborhood_ready")
    assert runner.M6B_ONLINE_EVENTS.index("cache_ready") < runner.M6B_ONLINE_EVENTS.index(
        "store_ready"
    )


def test_m6b_builder_and_loaded_audits_are_distinct_producer_shapes():
    valid = _valid_worker_payload()
    loaded = valid["factor_store"]
    builder = valid["builder_factor_audit"]
    assert runner._m6b_loaded_factor_audit_valid(loaded) is True
    assert runner._m6b_builder_factor_audit_valid(builder) is True
    assert runner._m6b_loaded_factor_audit_valid(builder) is False
    assert runner._m6b_builder_factor_audit_valid(loaded) is False


def test_m6b_phase_source_identity_binds_all_producer_phases():
    source = {
        "source_commit_full_sha": "a" * 40,
        "tracked_source_dirty": False,
    }
    summaries = {
        name: {
            "source_at_start": dict(source),
            "source_at_end": dict(source),
        }
        for name in ("stage", "builder", "online", "watchdog")
    }
    assert runner._m6b_phase_source_identity(summaries) == {
        "pass": True,
        "source_commit_full_sha": "a" * 40,
        "phase_names": ["stage", "builder", "online", "watchdog"],
        "all_tracked_source_clean": True,
    }
    tampered_sha = copy.deepcopy(summaries)
    tampered_sha["builder"]["source_at_start"]["source_commit_full_sha"] = "b" * 40
    assert runner._m6b_phase_source_identity(tampered_sha)["pass"] is False
    tampered_dirty = copy.deepcopy(summaries)
    tampered_dirty["watchdog"]["source_at_end"]["tracked_source_dirty"] = True
    assert runner._m6b_phase_source_identity(tampered_dirty)["pass"] is False


def test_m6b_dynamic_prediction_replaces_builder_store_reserve():
    valid = _valid_worker_payload()
    retained = valid["factor_store"]["retained_total_bytes"]
    prediction = runner._dynamic_predicted_live_set(retained)
    assert prediction["basis"] == "builder factor_audit.retained_total_bytes"
    assert prediction["components"]["shifted_store_retained_total_bytes"] == retained
    assert "shifted_lu_factor_payload_bytes" not in prediction["components"]


def test_m6b_patch_closure_borrows_action_output_without_destroy():
    class BorrowedResult:
        def __init__(self, values):
            self.values = values

        def getArray(self, readonly=True):
            return self.values

    class BorrowedAction:
        def __init__(self):
            self.result = None

        def mult(self, source):
            values = np.zeros(4, dtype=np.complex128)
            values[[1, 3]] = source.getArray(readonly=True)[[1, 3]]
            self.result = BorrowedResult(values)
            return self.result

    source = PETSc.Vec().createSeq(4, comm=PETSc.COMM_SELF)
    action = BorrowedAction()
    try:
        assert runner._m6b_patch_closure(
            np.eye(2, dtype=np.complex128), [1, 3], action, source
        ) == 0.0
        assert action.result is not None
    finally:
        source.destroy()


def test_m6b_scope_prediction_and_parser_are_fixed():
    assert runner.M6B_FACTOR_PAYLOAD_BYTES == 1_045_826_208
    prediction = runner._predicted_live_set()
    assert prediction["is_measurement"] is False
    assert prediction["gate"] is True
    assert not hasattr(runner, "_not_ready")
    parser = runner._parser()
    assert parser.parse_args(["m6b-stage-worker", "--run-dir", "/tmp/m6b"]).command == "m6b-stage-worker"
    assert parser.parse_args(
        ["m6b-check", "--run-dir", "/tmp/m6b", "--output", "/tmp/m6b.json"]
    ).command == "m6b-check"
