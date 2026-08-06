from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.physical_slab_two_level import (
    DistributedPhysicalSlabSmoother,
    OwnerLocalSlabPlan,
)
from src.solvers.static_condensed_iterative import _relative_residual
from src.solvers.static_factor_free_slab_pc import FactorFreeLocalSlabKrylovPc
from src.solvers.static_residual_snapshot import (
    CANONICAL_ORDERING_RULE,
    RESIDUAL_SEMANTICS,
    RESIDUAL_SNAPSHOT_SCHEMA,
    write_residual_snapshot,
)
from src.solvers.static_slab_contraction import (
    measure_one_apply_contraction,
    measure_owner_local_slab_contractions,
)


def _read_rank_shards(manifest_path: Path, manifest: dict) -> tuple[np.ndarray, np.ndarray]:
    rows = []
    values = []
    for shard in manifest["per_rank_shards"]:
        with np.load(manifest_path.parent / shard["filename"], allow_pickle=False) as arrays:
            rows.append(np.asarray(arrays["row_ids"], dtype=np.int64))
            values.append(
                np.asarray(arrays["real"], dtype=np.float64)
                + 1j * np.asarray(arrays["imag"], dtype=np.float64)
            )
    return np.concatenate(rows), np.concatenate(values)


@pytest.mark.skipif(MPI.COMM_WORLD.size != 1, reason="serial slab contraction fixture")
def test_serial_owner_local_slab_contractions_keep_global_and_local_actions_distinct():
    def diagonal_matrix(value):
        matrix = PETSc.Mat().createAIJ(size=(4, 4), nnz=1, comm=PETSc.COMM_SELF)
        matrix.setUp()
        for row in range(4):
            matrix.setValue(row, row, value)
        matrix.assemble()
        return matrix

    base_operator = diagonal_matrix(2.0)
    shifted_local_operator = diagonal_matrix(2.0 - 0.1j)
    global_operator = diagonal_matrix(3.0 - 0.1j)
    shift = base_operator.createVecLeft()
    shift.set(PETSc.ScalarType(-0.1j))
    shift.assemble()
    residual = base_operator.createVecRight()
    residual.setValues(
        range(4), np.asarray([0.0, 0.0, 0.0, 3.0j])
    )
    residual.assemble()
    rows = (
        np.asarray([0, 1, 2], dtype=PETSc.IntType),
        np.asarray([1, 2, 3], dtype=PETSc.IntType),
    )
    plan = OwnerLocalSlabPlan(
        comm=MPI.COMM_SELF,
        active_rows=4,
        slab_owners=(0, 0),
        owner_rows=rows,
        local_cell_indices_by_slab=((0,), (1,)),
        slab_row_counts=(3, 3),
        partition_weights_by_slab=(
            np.asarray([1.0, 0.5, 0.5], dtype=PETSc.ScalarType),
            np.asarray([0.5, 0.5, 1.0], dtype=PETSc.ScalarType),
        ),
        ras_core_masks_by_slab=(
            np.asarray([True, False, False]),
            np.asarray([False, False, True]),
        ),
        interface_masks_by_slab=(
            np.asarray([False, True, True]),
            np.asarray([True, True, False]),
        ),
        ras_core_sum_error=0.0,
        interface_row_count=2,
    )
    smoother = DistributedPhysicalSlabSmoother(
        base_operator,
        rows,
        ilu_levels=0,
        local_ksp_iterations=1,
        diagonal_shift=shift,
        factor_only_storage=True,
        interpolation="partition",
    )
    b4 = FactorFreeLocalSlabKrylovPc(
        base_operator,
        plan,
        shift,
        local_krylov_steps=4,
        variant="partition",
    )
    try:
        smoother_count_before = smoother.apply_count
        b4_actions_before = b4._action_calls

        def fixed_two_step(source, target):
            source.copy(target)
            target.scale(PETSc.ScalarType(0.25))

        def full_two_level(source, target):
            source.copy(target)
            target.scale(PETSc.ScalarType(0.2))

        result = measure_owner_local_slab_contractions(
            global_operator,
            shifted_local_operator,
            residual,
            plan,
            smoother,
            b4,
            fixed_two_step_apply=fixed_two_step,
            m3a_two_level_apply=full_two_level,
        )

        local_metrics = result["local_slab_contractions"]
        assert len(local_metrics) == 2
        assert {
            "slab",
            "local_residual_norm",
            "current_trace_ilu_unweighted_local_one_solve_rho",
            "b4_fixed_gmres4_unweighted_local_one_solve_rho",
        } == set(local_metrics[0])
        for metric in local_metrics:
            assert np.isfinite(metric["local_residual_norm"])
            if metric["slab"] == 0:
                assert (
                    metric["current_trace_ilu_unweighted_local_one_solve_rho"]
                    is None
                    and metric["b4_fixed_gmres4_unweighted_local_one_solve_rho"]
                    is None
                )
            else:
                assert metric["local_residual_norm"] > 0.0
                assert metric["current_trace_ilu_unweighted_local_one_solve_rho"] < 1.0e-11
                assert metric["b4_fixed_gmres4_unweighted_local_one_solve_rho"] < 1.0e-11

        current = result["global_current_trace_ilu_one_additive_apply"]
        b4_global = result["global_b4_partition_weighted_one_apply"]
        direct_current = measure_one_apply_contraction(
            global_operator,
            residual,
            smoother._diagnostic_one_level_apply,
        )
        direct_b4 = measure_one_apply_contraction(
            global_operator,
            residual,
            b4.apply,
        )
        assert current["rho"] == pytest.approx(direct_current["rho"])
        assert b4_global["rho"] == pytest.approx(direct_b4["rho"])
        assert current["rho"] > 0.1
        assert b4_global["rho"] > 0.1
        assert smoother.apply_count == smoother_count_before
        assert b4._action_calls > b4_actions_before

        ablation = result["global_current_trace_ilu_ablation"]
        assert len(ablation) == len(rows)
        assert [item["excluded_subdomain"] for item in ablation] == [0, 1]
        assert all(np.isfinite(item["ablation_damage"]) for item in ablation)
        for label in (
            "global_fixed_two_step_smoother",
            "global_m3a_two_step_wave_coarse_post_smooth",
        ):
            payload = result[label]
            assert payload is not None
            assert all(np.isfinite(value) for value in payload.values())
        assert "hardest_slab" not in result
        assert "control_slab" not in result
    finally:
        b4.destroy()
        smoother.destroy()
        residual.destroy()
        shift.destroy()
        global_operator.destroy()
        shifted_local_operator.destroy()
        base_operator.destroy()


@pytest.mark.skipif(MPI.COMM_WORLD.size != 1, reason="serial contraction fixture")
def test_serial_one_apply_contraction_uses_tiny_diagonal_and_keeps_residual():
    matrix = PETSc.Mat().createAIJ(size=(2, 2), nnz=1, comm=PETSc.COMM_SELF)
    matrix.setUp()
    matrix.setValue(0, 0, 2.0)
    matrix.setValue(1, 1, 2.0)
    matrix.assemble()
    residual = matrix.createVecLeft()
    residual.setValues((0, 1), np.asarray([1.0 + 1.0j, 2.0 - 1.0j]))
    residual.assemble()
    before = np.asarray(residual.getArray(readonly=True), dtype=np.complex128).copy()

    def exact_correction(source, target):
        source.copy(target)
        target.scale(PETSc.ScalarType(0.5))

    exact = measure_one_apply_contraction(matrix, residual, exact_correction)
    assert exact["rho"] == pytest.approx(0.0)
    assert exact["post_norm"] == pytest.approx(0.0)
    assert exact["correction_norm"] == pytest.approx(exact["input_norm"] / 2.0)
    np.testing.assert_array_equal(
        np.asarray(residual.getArray(readonly=True)), before
    )

    def fixed_approximate_correction(source, target):
        source.copy(target)
        target.scale(PETSc.ScalarType(0.25))

    approximate = measure_one_apply_contraction(
        matrix, residual, fixed_approximate_correction
    )
    assert approximate["rho"] == pytest.approx(0.5)
    assert approximate["post_norm"] == pytest.approx(approximate["input_norm"] / 2.0)
    np.testing.assert_array_equal(
        np.asarray(residual.getArray(readonly=True)), before
    )

    residual.destroy()
    matrix.destroy()


@pytest.mark.skipif(MPI.COMM_WORLD.size != 1, reason="serial snapshot fixture")
def test_serial_snapshot_has_global_row_identity_and_exact_true_residual(tmp_path):
    comm = MPI.COMM_WORLD
    matrix = PETSc.Mat().createAIJ(size=(3, 3), nnz=3, comm=PETSc.COMM_SELF)
    matrix.setUp()
    for row, diagonal in enumerate((2.0, 3.0, 4.0)):
        matrix.setValue(row, row, diagonal)
    matrix.assemble()
    rhs = matrix.createVecRight()
    solution = matrix.createVecRight()
    work = matrix.createVecLeft()
    rhs.setValues(range(3), np.asarray([4.0 + 1.0j, 6.0, 8.0 - 2.0j]))
    solution.setValues(range(3), np.asarray([1.0, 1.0, 1.0 + 0.5j]))
    rhs.assemble()
    solution.assemble()
    relative = _relative_residual(matrix, rhs, solution, work, float(rhs.norm()))
    expected = np.asarray([2.0 + 1.0j, 3.0, 4.0 - 4.0j])
    np.testing.assert_allclose(
        np.asarray(work.getArray(readonly=True)),
        expected,
    )
    assert relative == pytest.approx(float(np.linalg.norm(expected)) / float(rhs.norm()))

    callback_copy = np.asarray(work.getArray(readonly=True), dtype=np.complex128).copy()
    record = write_residual_snapshot(
        tmp_path,
        work,
        iteration=0,
        profile="fixture_m3a",
        source_sha="a" * 40,
        true_relative_residual=0.25,
        reported_relative_residual=0.5,
        comm=comm,
    )
    manifest = record["manifest"]
    manifest_path = tmp_path / record["manifest_filename"]
    loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert loaded == manifest
    assert loaded["schema_version"] == RESIDUAL_SNAPSHOT_SCHEMA
    assert loaded["residual_semantics"] == RESIDUAL_SEMANTICS
    assert loaded["row_identity"] == "active_trace_residual_global_row"
    assert loaded["canonical_ordering_rule"] == CANONICAL_ORDERING_RULE
    assert loaded["full_source_sha"] == "a" * 40
    assert loaded["rank_ownership_not_part_of_identity"] is True
    assert loaded["repartition_invariant_global_numbering"] == "not_claimed"
    assert "owner_independent" not in loaded

    rows, values = _read_rank_shards(manifest_path, loaded)
    np.testing.assert_array_equal(rows, np.arange(3, dtype=np.int64))
    np.testing.assert_allclose(values, callback_copy)
    assert loaded["per_rank_shards"][0]["file_sha256"]
    assert len(loaded["canonical_sha256"]) == 64
    assert record["manifest_sha256"]

    work.destroy()
    solution.destroy()
    rhs.destroy()
    matrix.destroy()


@pytest.mark.skipif(MPI.COMM_WORLD.size != 2, reason="MPI2 zero-local-row contract")
def test_mpi2_snapshot_collective_completes_with_zero_local_row(tmp_path):
    comm = MPI.COMM_WORLD
    root_path = Path(tmp_path) if comm.rank == 0 else None
    root_path = Path(comm.bcast(str(root_path) if root_path is not None else None, root=0))
    vector = PETSc.Vec().createMPI((PETSc.DECIDE, 1), comm=comm)
    start, end = map(int, vector.getOwnershipRange())
    vector.getArray()[:] = np.asarray(
        [7.0 + 2.0j + start], dtype=PETSc.ScalarType
    )
    vector.assemble()
    assert comm.allreduce(int(end == start), op=MPI.SUM) == 1
    record = write_residual_snapshot(
        root_path,
        vector,
        iteration=20,
        profile="fixture_m3a",
        source_sha="b" * 40,
        comm=comm,
    )
    assert record["manifest"]["global_active_row_count"] == 1
    assert len(record["manifest"]["per_rank_shards"]) == 2
    if comm.rank == 0:
        assert sum(item["row_count"] for item in record["manifest"]["per_rank_shards"]) == 1
        assert any(item["row_count"] == 0 for item in record["manifest"]["per_rank_shards"])
    comm.barrier()
    vector.destroy()
    comm.barrier()
    if comm.rank == 0:
        shutil.rmtree(root_path)
