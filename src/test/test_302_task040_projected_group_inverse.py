"""Focused distributed Woodbury carrier tests for the conditional Run-B path."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.hybrid_interface_schur import (
    build_distributed_petrov_action,
    build_petsc_interface_schur_oracle,
    build_fixed_projected_group_inverse,
)
from src.solvers.hybrid_interface_run_b import build_v1_3_projected_transmission
from src.solvers.hybrid_local_dtn_woodbury import ResearchExactFactorInverse
from src.solvers.hybrid_side_impedance import ArtificialZTraceMass


def _dense_base() -> np.ndarray:
    return np.asarray(
        [
            [2.1 + 0.2j, 0.3 - 0.1j, 0.1 + 0.05j],
            [0.2 + 0.4j, 1.7 - 0.1j, -0.2j],
            [0.05 - 0.1j, 0.25 + 0.2j, 1.4 + 0.3j],
        ],
        dtype=np.complex128,
    )


def _dense_u() -> np.ndarray:
    return np.asarray(
        [
            [0.7 + 0.2j, -0.1 + 0.3j],
            [0.2 - 0.4j, 0.5 + 0.1j],
            [-0.3 + 0.2j, 0.4 - 0.2j],
        ],
        dtype=np.complex128,
    )


def _dense_v() -> np.ndarray:
    return np.asarray(
        [
            [0.1 - 0.5j, 0.6 + 0.2j],
            [0.8 + 0.1j, -0.2 + 0.4j],
            [0.3 + 0.3j, 0.2 - 0.6j],
        ],
        dtype=np.complex128,
    )


def _distributed_matrix(values: np.ndarray) -> PETSc.Mat:
    size = int(values.shape[0])
    matrix = PETSc.Mat().createAIJ(
        size=((PETSc.DECIDE, size), (PETSc.DECIDE, size)),
        nnz=size,
        comm=MPI.COMM_WORLD,
    )
    first, last = map(int, matrix.getOwnershipRange())
    for row in range(first, last):
        for column in range(size):
            matrix.setValue(row, column, PETSc.ScalarType(values[row, column]))
    matrix.assemble()
    return matrix


def _set_global(vector: PETSc.Vec, values: np.ndarray) -> None:
    first, last = map(int, vector.getOwnershipRange())
    vector.array[:] = np.asarray(values[first:last], dtype=PETSc.ScalarType)
    vector.assemble()


def _collect_global(vector: PETSc.Vec) -> np.ndarray:
    first, _last = map(int, vector.getOwnershipRange())
    local = np.asarray(vector.array, dtype=np.complex128).copy()
    pieces = MPI.COMM_WORLD.allgather((first, local))
    values = np.empty(int(vector.getSize()), dtype=np.complex128)
    for start, part in pieces:
        values[start : start + part.size] = part
    return values


def test_fixed_projected_group_inverse_matches_dense_reference_and_releases():
    base = _dense_base()
    u = _dense_u()
    v = _dense_v()
    operator = base + u @ v.conj().T
    matrix = _distributed_matrix(base)
    layout = matrix.createVecRight()
    factor = None
    carrier = None
    vectors: list[PETSc.Vec] = []
    try:
        factor = ResearchExactFactorInverse(
            matrix,
            factor_solver_type="mumps",
            factor_only_storage=True,
        )
        factor.release_borrowed_matrix()
        matrix.destroy()
        matrix = None
        first, last = map(int, layout.getOwnershipRange())
        carrier = build_fixed_projected_group_inverse(
            layout,
            factor,
            u[first:last],
            v[first:last],
        )
        diagnostics = carrier.diagnostics
        assert diagnostics["operator_identity"] == "B_plus_U_VH"
        assert diagnostics["normal_equations"] is False
        assert diagnostics["fe_numeric_allgather"] is False
        assert diagnostics["nested_ksp_count"] == 0
        assert diagnostics["small_replicated_shapes"]["K"] == [2, 2]
        assert diagnostics["K_rank"] == 2
        assert diagnostics["base_solve_count"] == 2
        if MPI.COMM_WORLD.size >= 4:
            assert MPI.COMM_WORLD.allreduce(layout.getLocalSize() == 0, op=MPI.LOR)

        source_values = np.asarray([1.0 - 0.4j, -0.3 + 0.8j, 0.6 + 0.2j])
        second_values = np.asarray([-0.2 + 0.5j, 0.7 + 0.1j, 0.4 - 0.6j])
        outputs: list[np.ndarray] = []
        for values in (source_values, second_values, source_values):
            source = layout.duplicate()
            target = layout.duplicate()
            vectors.extend((source, target))
            _set_global(source, values)
            carrier.apply(source, target)
            outputs.append(_collect_global(target))
        combined = (1.2 - 0.3j) * source_values + (-0.4 + 0.2j) * second_values
        source = layout.duplicate()
        target = layout.duplicate()
        vectors.extend((source, target))
        _set_global(source, combined)
        carrier.apply(source, target)
        outputs.append(_collect_global(target))

        expected = [
            np.linalg.solve(operator, values)
            for values in (source_values, second_values, source_values, combined)
        ]
        for actual, reference in zip(outputs, expected):
            assert np.allclose(actual, reference, rtol=0.0, atol=1.0e-11)
        assert np.allclose(
            outputs[3],
            (1.2 - 0.3j) * outputs[0] + (-0.4 + 0.2j) * outputs[1],
            rtol=0.0,
            atol=1.0e-11,
        )
        assert carrier.diagnostics["apply_count"] == 4
        assert carrier.diagnostics["base_solve_count"] == 6
    finally:
        for vector in vectors:
            vector.destroy()
        if carrier is not None:
            carrier.destroy()
            assert carrier.diagnostics["destroyed"] is True
            assert carrier.diagnostics["base_factor_reference_released"] is True
            assert factor is not None
            assert factor.diagnostics["factor_destroyed"] is False
        layout.destroy()
        if factor is not None:
            factor.destroy()
            assert factor.diagnostics["factor_destroyed"] is True
        if matrix is not None:
            matrix.destroy()


def test_fixed_projected_group_inverse_singular_k_cleans_borrowed_state():
    base = np.eye(3, dtype=np.complex128)
    matrix = _distributed_matrix(base)
    layout = matrix.createVecRight()
    factor = ResearchExactFactorInverse(
        matrix,
        factor_solver_type="mumps",
        factor_only_storage=True,
    )
    factor.release_borrowed_matrix()
    matrix.destroy()
    first, last = map(int, layout.getOwnershipRange())
    local_u = np.zeros((last - first, 1), dtype=np.complex128)
    local_v = np.zeros_like(local_u)
    if first <= 0 < last:
        local_u[0 - first, 0] = 1.0
        local_v[0 - first, 0] = -1.0
    try:
        with pytest.raises(ValueError, match="small K is singular"):
            build_fixed_projected_group_inverse(layout, factor, local_u, local_v)
        assert factor.diagnostics["factor_destroyed"] is False
    finally:
        layout.destroy()
        factor.destroy()


def test_v1_3_projected_transmission_owns_three_base_factors_and_sweep(monkeypatch):
    base = np.diag(
        np.asarray(
            [
                2.0 + 0.1j,
                2.2 - 0.2j,
                2.4 + 0.3j,
                2.6 - 0.1j,
                2.8 + 0.2j,
                3.0 - 0.3j,
            ]
        )
    )
    base += 0.04j * np.triu(np.ones((6, 6), dtype=np.complex128), 1)
    base += 0.03 * np.tril(np.ones((6, 6), dtype=np.complex128), -1)
    matrix = _distributed_matrix(base)
    first, last = map(int, matrix.getOwnershipRange())
    global_groups = ((0, 1), (0, 2, 3, 5), (4, 5))
    group_rows = tuple(
        np.asarray([row for row in rows if first <= row < last], dtype=PETSc.IntType)
        for rows in global_groups
    )
    supports = (
        {"active_support": (0,)},
        {"active_support": (5,)},
    )
    oracle = build_petsc_interface_schur_oracle(matrix, group_rows, supports)
    petrov: list[Any] = []
    layouts: list[PETSc.Vec] = []
    masses: list[ArtificialZTraceMass] = []
    sweep = owner = None
    try:
        for row in (0, 5):
            values = np.zeros((6, 6), dtype=np.complex128)
            values[row, row] = 1.0
            masses.append(
                ArtificialZTraceMass(
                    _distributed_matrix(values), {"interface_z": float(row)}
                )
            )
        for group in range(3):
            gamma_rows = oracle.group_gamma_rows_local(group)
            layout = oracle.create_group_gamma_vector(group)
            layouts.append(layout)
            width = 2 if group == 1 else 1
            z_local = np.zeros((len(gamma_rows), width), dtype=np.complex128)
            y_local = np.zeros_like(z_local)
            for local, row in enumerate(gamma_rows):
                column = 0 if int(row) == 0 else min(1, width - 1)
                z_local[local, column] = 1.0 + 0.2j * (group + 1)
                y_local[local, column] = 1.3 - 0.1j * (group + 1)

            def scalar_apply(source, target):
                source.copy(target)

            def exact_apply(source, target, group=group):
                oracle.apply_group(group, source, target)

            petrov.append(
                build_distributed_petrov_action(
                    layout,
                    scalar_apply,
                    exact_apply,
                    z_local,
                    y_local,
                    local_row_ids=gamma_rows,
                )
            )
        assert oracle.diagnostics["factor_count_ready"] == 3
        oracle.destroy()
        assert oracle.diagnostics["factor_count_after_cleanup"] == 0
        oracle = None
        sweep, owner, diagnostics = build_v1_3_projected_transmission(
            bare_f=matrix,
            group_rows=group_rows,
            interface_masses=tuple(masses),
            beta=0.7 + 0.2j,
            group_audit={"interface_support_coverage": []},
            petrov_actions=tuple(petrov),
        )
        assert diagnostics["factor_count_ready"] == 3
        assert diagnostics["projected_factor_count_ready"] == 3
        assert diagnostics["simultaneous_factor_count_max"] == 3
        assert sweep.diagnostics["sweep_mode"] == "multiplicative_schwarz"
        assert sweep.diagnostics["multiplicative_sequence"] == [0, 1, 2, 2, 1, 0]
        destroy_events: list[str] = []
        for auxiliary in owner._auxiliary_owners:
            original_destroy = auxiliary.destroy

            def destroy_projected(original_destroy=original_destroy):
                destroy_events.append("projected")
                original_destroy()

            monkeypatch.setattr(auxiliary, "destroy", destroy_projected)
        for factor in owner._factors:
            original_destroy = factor.destroy

            def destroy_base(original_destroy=original_destroy):
                destroy_events.append("base")
                original_destroy()

            monkeypatch.setattr(factor, "destroy", destroy_base)
        source = matrix.createVecRight()
        target = matrix.createVecLeft()
        repeated = matrix.createVecLeft()
        try:
            _set_global(source, np.asarray([1.0 + 0.2j * i for i in range(6)]))
            sweep.apply(source, target)
            sweep.apply(source, repeated)
            assert np.isfinite(target.norm())
            assert np.allclose(_collect_global(target), _collect_global(repeated))
            assert sweep.diagnostics["apply_count"] == 2
        finally:
            source.destroy()
            target.destroy()
            repeated.destroy()
    finally:
        if owner is not None:
            assert owner.diagnostics["factor_count_ready"] == 3
            owner.destroy()
            assert owner.diagnostics["factor_count_ready"] == 0
            assert owner.diagnostics["auxiliary_owner_count"] == 0
            assert destroy_events == ["projected"] * 3 + ["base"] * 3
        for carrier in petrov:
            carrier.destroy()
        for layout in layouts:
            layout.destroy()
        if oracle is not None:
            oracle.destroy()
        for mass in masses:
            mass.destroy()
        matrix.destroy()
