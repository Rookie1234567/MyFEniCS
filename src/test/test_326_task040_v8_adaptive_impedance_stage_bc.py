"""Focused distributed sparse coarse-component contract."""

from __future__ import annotations

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.hybrid_adaptive_impedance_stage_bc import (
    ADAPTIVE_ECONOMICAL_COARSE_RESOURCE_UNAVAILABLE,
    build_adaptive_impedance_stage_bc_action,
)
from src.solvers.hybrid_maxwell_harmonic_economical import (
    EconomicalMaxwellHarmonicSpace,
    EconomicalPatchRecord,
)


class _IdentityLocalAction:
    def __init__(self, metadata: tuple[dict[str, object], ...]) -> None:
        self._metadata = metadata
        self.apply_count = 0

    @property
    def diagnostics(self) -> dict[str, int]:
        return {"factor_bytes_global": 0}

    def patch_metadata(self) -> tuple[dict[str, object], ...]:
        return self._metadata

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        source.copy(target)
        self.apply_count += 1


def _reference_fine_matrix(comm: MPI.Intracomm) -> tuple[PETSc.Mat, np.ndarray]:
    values = np.diag(
        np.asarray(
            [2.0 + 0.1j, 2.2 - 0.2j, 1.8 + 0.3j, 2.4 - 0.1j],
            dtype=np.complex128,
        )
    )
    for row in range(4):
        values[row, (row + 1) % 4] = -0.25 + 0.05j * (row + 1)
    matrix = PETSc.Mat().createAIJ(size=(4, 4), nnz=2, comm=comm)
    first, last = map(int, matrix.getOwnershipRange())
    for row in range(first, last):
        columns = np.flatnonzero(values[row])
        matrix.setValues(
            row,
            np.asarray(columns, dtype=PETSc.IntType),
            np.asarray(values[row, columns], dtype=PETSc.ScalarType),
        )
    matrix.assemble()
    return matrix, values


def _fresh_space_and_action(
    comm: MPI.Intracomm,
) -> tuple[EconomicalMaxwellHarmonicSpace, _IdentityLocalAction]:
    metadata: tuple[dict[str, object], ...]
    if comm.rank == 0:
        rows = (0, 1, 2, 3)
        columns = np.asarray(
            [
                [1.0, 0.2],
                [0.3, 1.0],
                [1.0 + 0.1j, 0.4],
                [0.5, 1.0 - 0.2j],
            ],
            dtype=PETSc.ScalarType,
        )
        records = (
            EconomicalPatchRecord(
                patch_id=(0, 0),
                cell_index=0,
                rows=rows,
                weights=np.ones(4, dtype=np.float64),
                columns=columns,
                audit={"retained_rank": 2},
            ),
        )
        metadata = (
            {
                "patch_id": (0, 0),
                "cell_index": 0,
                "rows": rows,
                "weights": (1.0, 1.0, 1.0, 1.0),
                "class_key": "synthetic-class",
                "owner_rank": 0,
            },
        )
    else:
        records = ()
        metadata = ()
    return EconomicalMaxwellHarmonicSpace(records, {}), _IdentityLocalAction(metadata)


@pytest.mark.skipif(
    MPI.COMM_WORLD.size not in (1, 2),
    reason="Stage-B/C focused coverage is serial and MPI2",
)
def test_task040_stage_bc_distributed_prefix_and_composite_lifecycle() -> None:
    comm = MPI.COMM_WORLD
    fine, fine_reference = _reference_fine_matrix(comm)
    try:
        denied_space, denied_action = _fresh_space_and_action(comm)
        denied = build_adaptive_impedance_stage_bc_action(
            harmonic_space=denied_space,
            action=denied_action,
            fine_operator=fine,
            current_process_tree_baseline_bytes=None,
            current_process_tree_baseline_source="unknown",
        )
        assert denied.action is None
        assert denied.status == ADAPTIVE_ECONOMICAL_COARSE_RESOURCE_UNAVAILABLE
        assert denied.diagnostics["allocated_object_count"] == {
            "P": 0,
            "P_H": 0,
            "FP": 0,
            "Ac": 0,
            "KSP": 0,
        }
        assert denied.diagnostics["memory_preflight"]["baseline_known"] is False
        assert denied.diagnostics["memory_preflight"]["hard_memory_bytes"] == (
            45 * 2**30
        )
        if comm.rank == 0:
            assert len(denied_space.local_patch_records) == 1
            assert denied_space.local_patch_records[0].columns is not None
        else:
            assert not denied_space.local_patch_records
        denied_space.destroy()

        space, local_action = _fresh_space_and_action(comm)
        phase_events: list[tuple[str, dict[str, object]]] = []

        def phase_callback(name: str, detail: dict[str, object]) -> None:
            phase_events.append((name, detail))

        override_hard_memory_bytes = 64 * 2**30
        result = build_adaptive_impedance_stage_bc_action(
            harmonic_space=space,
            action=local_action,
            fine_operator=fine,
            current_process_tree_baseline_bytes=0,
            current_process_tree_baseline_source="fixture",
            hard_memory_bytes=override_hard_memory_bytes,
            phase_callback=phase_callback,
        )
        assert result.status == "ready"
        assert result.action is not None
        coarse = result.action
        diagnostics = coarse.diagnostics
        assert diagnostics["memory_preflight"]["allocation_allowed"] is True
        assert diagnostics["memory_preflight"]["hard_memory_bytes"] == (
            override_hard_memory_bytes
        )
        assert [name for name, _detail in phase_events] == [
            "P_ready",
            "P_H_ready",
            "FP_ready",
            "Ac_ready",
            "coarse_ksp_ready",
        ]
        for name, detail in phase_events:
            assert detail["name"] == name
            assert len(detail["global_size"]) == 2
            assert len(detail["local_size"]) == 2
            for key in (
                "actual_global_nnz",
                "actual_global_memory_bytes",
            ):
                assert isinstance(detail[key], int)
                assert detail[key] >= 0
            assert detail["phase_wall_seconds"] >= 0.0
        assert phase_events[-1][1]["ksp"] == {
            "type": "gmres",
            "restart": 32,
            "rtol": 1.0e-6,
            "atol": 0.0,
            "max_it": 32,
            "zero_initial_guess": True,
            "pc": "jacobi",
            "set_from_options": False,
        }
        assert diagnostics["full_vector_numeric_allgather"] is False
        assert diagnostics["numeric_object_alltoall_count"] == 1
        assert diagnostics["transient_matrices_released"] == {
            "P_H": True,
            "F_times_P": True,
        }
        assert diagnostics["allocated_object_count"] == {
            "P": 1,
            "P_H": 0,
            "FP": 0,
            "Ac": 1,
            "KSP": 1,
        }
        assert diagnostics["ksp"] == {
            "type": "gmres",
            "restart": 32,
            "rtol": 1.0e-6,
            "atol": 0.0,
            "max_it": 32,
            "zero_initial_guess": True,
            "pc": "jacobi",
            "set_from_options": False,
        }
        scalar_bytes = np.dtype(PETSc.ScalarType).itemsize
        int_bytes = np.dtype(PETSc.IntType).itemsize
        packet_rows = 4 if comm.size == 1 else 2
        value_bytes = packet_rows * 2 * scalar_bytes
        packet_bound = 4 * (int_bytes + 2 * scalar_bytes)
        assert diagnostics["max_single_patch_payload_bytes"] > value_bytes
        assert diagnostics["max_single_patch_payload_bytes"] <= packet_bound
        for key in ("max_sender_payload_bytes", "max_receiver_payload_bytes"):
            assert 0 < diagnostics[key] <= packet_bound
        if comm.rank == 0:
            if comm.size == 2:
                assert diagnostics["coarse_column_ownership"] == (
                    (0, 0, 2),
                    (1, 2, 2),
                )
            else:
                assert diagnostics["coarse_column_ownership"] == ((0, 0, 2),)
            assert len(local_action.patch_metadata()) == 1
            assert len(space.local_patch_records) == 1
            assert space._destroyed is True
            assert space.local_patch_records[0].columns is None
            assert coarse.prolongation.getLocalSize()[1] == 2
        else:
            assert not local_action.patch_metadata()
            assert not space.local_patch_records
            assert space._destroyed is True
            assert coarse.prolongation.getLocalSize()[1] == 0
        prolongation = coarse.prolongation
        expected_columns = np.asarray(
            [
                [1.0, 0.2],
                [0.3, 1.0],
                [1.0 + 0.1j, 0.4],
                [0.5, 1.0 - 0.2j],
            ],
            dtype=np.complex128,
        )
        first, last = map(int, prolongation.getOwnershipRange())
        for row in range(first, last):
            columns, values = prolongation.getRow(row)
            actual = np.zeros(2, dtype=np.complex128)
            actual[np.asarray(columns, dtype=np.intp)] = values
            np.testing.assert_allclose(actual, expected_columns[row])

        coarse_reference = expected_columns.conj().T @ fine_reference @ expected_columns
        coarse_matrix = coarse.coarse_matrix
        first, last = map(int, coarse_matrix.getOwnershipRange())
        for row in range(first, last):
            columns, values = coarse_matrix.getRow(row)
            actual = np.zeros(2, dtype=np.complex128)
            actual[np.asarray(columns, dtype=np.intp)] = values
            np.testing.assert_allclose(actual, coarse_reference[row])
        assert np.linalg.norm(coarse_reference - coarse_reference.conj().T) > 0.0
        assert all(record.columns is None for record in space.local_patch_records)

        source = fine.createVecRight()
        target = fine.createVecRight()
        source_global = np.arange(4, dtype=np.complex128) + 1.0
        source_first, source_last = map(int, source.getOwnershipRange())
        source.array[:] = source_global[source_first:source_last]
        first_residual = source_global - fine_reference @ source_global
        coarse_correction = np.linalg.solve(
            coarse_reference,
            expected_columns.conj().T @ first_residual,
        )
        expected_x = source_global + expected_columns @ coarse_correction
        second_residual = source_global - fine_reference @ expected_x
        expected_target = expected_x + second_residual
        coarse.apply(source, target)
        assert np.all(np.isfinite(target.array))
        np.testing.assert_allclose(
            target.array,
            expected_target[source_first:source_last],
            rtol=1.0e-5,
            atol=1.0e-5,
        )
        live_diagnostics = result.diagnostics
        assert live_diagnostics["apply_count"] == 1
        assert live_diagnostics["local_action_apply_count"] == 2
        assert len(live_diagnostics["ksp_history"]) == 1
        history = live_diagnostics["ksp_history"][0]
        assert np.isfinite(history["residual"])
        assert np.isfinite(history["rhs_norm"])
        assert np.isfinite(history["relative_residual"])
        assert history["relative_residual"] == pytest.approx(
            history["residual"] / max(history["rhs_norm"], 1.0e-300)
        )
        result.destroy()
        result.destroy()
        assert result.diagnostics["destroyed"] is True
        probe = fine.createVecRight()
        fine.mult(source, probe)
        assert np.all(np.isfinite(probe.array))
        probe.destroy()
        source.destroy()
        target.destroy()
    finally:
        fine.destroy()
