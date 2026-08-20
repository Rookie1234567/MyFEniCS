from __future__ import annotations

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.hybrid_petrov_galerkin import (
    FixedLinearOwnerRowPetrovCorrectionAction,
    _adjoint_matvec_without_matrix_copy,
)
from src.solvers.hybrid_streamed_petrov import (
    run_streamed_owner_row_petrov_consumer,
)


class _DenseBaseAction:
    def __init__(self, diagonal: np.ndarray) -> None:
        self.diagonal = np.asarray(diagonal, dtype=np.complex128)
        self.apply_count = 0

    @property
    def diagnostics(self) -> dict[str, int | str]:
        return {
            "identity": "tiny_fixed_ilu0_base",
            "base_factor_count": 1,
            "exact_factor_count": 0,
            "global_direct_factor_count": 0,
            "nested_ksp_count": 0,
        }

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        first, last = (int(value) for value in source.getOwnershipRange())
        target.getArray()[:] = (
            np.asarray(source.getArray(readonly=True), dtype=np.complex128)
            / self.diagonal[first:last]
        )
        self.apply_count += 1


class _NonzeroExactBaseAction(_DenseBaseAction):
    @property
    def diagnostics(self) -> dict[str, int | str]:
        return {
            "identity": "tiny_exact_base_for_conflict_test",
            "base_factor_count": 1,
            "exact_factor_count": 1,
            "global_direct_factor_count": 0,
        }


class _DenseMatContext:
    def __init__(self, dense: np.ndarray) -> None:
        self.dense = np.asarray(dense, dtype=np.complex128)

    def mult(self, _matrix: PETSc.Mat, source: PETSc.Vec, target: PETSc.Vec) -> None:
        comm = source.getComm().tompi4py()
        first, last = (int(value) for value in source.getOwnershipRange())
        values = np.empty(source.getSize(), dtype=np.complex128)
        local = np.asarray(source.getArray(readonly=True), dtype=np.complex128).copy()
        for begin, end, packet in comm.allgather((first, last, local)):
            values[begin:end] = packet
        target_first, target_last = (int(value) for value in target.getOwnershipRange())
        target.getArray()[:] = (self.dense @ values)[target_first:target_last]


def _dense_mat(values: np.ndarray) -> PETSc.Mat:
    matrix = PETSc.Mat().createPython(
        values.shape,
        context=_DenseMatContext(values),
        comm=MPI.COMM_WORLD,
    )
    matrix.setUp()
    return matrix


def _vector(operator: PETSc.Mat, values: np.ndarray) -> PETSc.Vec:
    vector = operator.createVecRight()
    first, last = (int(value) for value in vector.getOwnershipRange())
    vector.getArray()[:] = np.asarray(values[first:last], dtype=PETSc.ScalarType)
    return vector


def _relative_error(actual: PETSc.Vec, expected: PETSc.Vec) -> float:
    difference = actual.duplicate()
    actual.copy(difference)
    difference.axpy(PETSc.ScalarType(-1.0), expected)
    try:
        return float(difference.norm()) / max(float(expected.norm()), 1.0e-30)
    finally:
        difference.destroy()


def _fixture() -> tuple[
    PETSc.Mat, _DenseBaseAction, np.ndarray, np.ndarray, np.ndarray
]:
    rows = 8
    rng = np.random.default_rng(287)
    f_dense = np.asarray(
        [
            [2.0 + 0.3j, 0.1 - 0.2j, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [0.0, 2.4 - 0.1j, 0.2 + 0.1j, 0.0, 0.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 2.7 + 0.2j, 0.1 - 0.1j, 0.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 2.9 - 0.2j, 0.1 + 0.2j, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 0.0, 3.1 + 0.1j, 0.2 - 0.1j, 0.0, 0.0],
            [0.0, 0.0, 0.0, 0.0, 0.0, 3.3 - 0.3j, 0.1 + 0.1j, 0.0],
            [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 3.6 + 0.2j, 0.2 - 0.2j],
            [0.1 + 0.1j, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 3.9 - 0.1j],
        ],
        dtype=np.complex128,
    )
    z_global = rng.standard_normal((rows, 3)) + 1j * rng.standard_normal((rows, 3))
    y_global = rng.standard_normal((rows, 3)) + 1j * rng.standard_normal((rows, 3))
    f_operator = _dense_mat(f_dense)
    base = _DenseBaseAction(np.diag(f_dense))
    first, last = (int(value) for value in f_operator.getOwnershipRange())
    return f_operator, base, f_dense, z_global[first:last], y_global[first:last]


def test_petrov_adjoint_matvec_matches_explicit_complex_formula():
    rng = np.random.default_rng(2871)
    matrix = rng.standard_normal((19, 7)) + 1j * rng.standard_normal((19, 7))
    vector = rng.standard_normal(19) + 1j * rng.standard_normal(19)
    actual = _adjoint_matvec_without_matrix_copy(matrix, vector)
    expected = matrix.conj().T @ vector
    np.testing.assert_allclose(actual, expected, rtol=0.0, atol=1.0e-13)


def test_petrov_borrowed_readonly_basis_lifecycle_does_not_destroy_owner():
    f_operator, base, _f_dense, z_local, y_local = _fixture()
    z_owner = np.array(z_local, copy=True)
    y_owner = np.array(y_local, copy=True)
    z_owner.setflags(write=False)
    y_owner.setflags(write=False)
    try:
        action = FixedLinearOwnerRowPetrovCorrectionAction(
            base,
            f_operator,
            z_owner,
            y_owner,
            factor_inventory=base.diagnostics,
            basis_ownership="borrowed_readonly",
        )
        try:
            assert action.diagnostics["basis_ownership"] == "borrowed_readonly"
            assert action.diagnostics["basis_copied"] is False
            assert action.diagnostics["borrowed_basis_readonly"] is True
            assert np.shares_memory(action._z_local, z_owner)
            assert np.shares_memory(action._y_local, y_owner)
            np.testing.assert_array_equal(action._z_local, z_owner)
        finally:
            action.destroy()
        np.testing.assert_array_equal(z_owner, z_local)
        np.testing.assert_array_equal(y_owner, y_local)
    finally:
        f_operator.destroy()


@pytest.mark.parametrize("failure_kind", ["rank", "condition"])
def test_streamed_consumer_records_e_failure_and_stops_at_first_passing_rank(
    failure_kind,
):
    if MPI.COMM_WORLD.size not in (1, 2, 4):
        pytest.skip("focused streamed consumer fixture supports MPI1/2/4")
    rows = 128
    f_dense = np.eye(rows, dtype=np.complex128)
    f_operator = _dense_mat(f_dense)
    base = _DenseBaseAction(np.ones(rows, dtype=np.complex128))
    first, last = (int(value) for value in f_operator.getOwnershipRange())
    z128 = np.eye(rows, dtype=np.complex128)
    y128 = z128.copy()
    y64 = y128[:, :64].copy()
    if failure_kind == "rank":
        y64[:, 1] = y64[:, 0]
    else:
        y64[:, 63] *= 1.0e-13
    z64 = z128[:, :64]

    class _Packet:
        def prefix(self, checkpoint):
            if checkpoint == 64:
                z, y = z64[first:last], y64[first:last]
            elif checkpoint == 128:
                z, y = z128[first:last], y128[first:last]
            else:
                raise AssertionError("the fixture should stop at rank 128")
            z = np.array(z, copy=True)
            y = np.array(y, copy=True)
            z.setflags(write=False)
            y.setflags(write=False)
            return z, y, {"checkpoint": checkpoint}

    packet = _Packet()
    try:
        result = run_streamed_owner_row_petrov_consumer(
            packet,
            f_operator,
            base,
            holdout_evaluator=lambda _action, checkpoint: {
                "gate_pass": checkpoint == 128
            },
            factor_inventory=base.diagnostics,
        )
        assert result["first_passing_checkpoint"] == 128
        assert [item["status"] for item in result["reports"]] == [
            "numerical_e_failure",
            "completed",
        ]
        assert result["reports"][0]["post_destroy_diagnostics"] is None
        assert result["reports"][0]["correction_action_destroyed"] is True
        assert result["reports"][0]["e_failure"].startswith(
            "Petrov coarse E is rank deficient"
            if failure_kind == "rank"
            else "Petrov coarse E condition exceeds"
        )
        assert result["reports"][0]["factor_inventory"]["exact_factor_count"] == 0
        assert result["reports"][1]["post_destroy_diagnostics"]["destroyed"] is True
        assert result["all_corrections_destroyed"] is True
        assert result["exact_factor_count"] == 0
        assert result["global_direct_factor_count"] == 0
    finally:
        f_operator.destroy()


def test_petrov_formula_complex_adjoint_owner_rows_and_lifecycle():
    if MPI.COMM_WORLD.size not in (1, 2, 4):
        pytest.skip("focused owner-row fixture supports MPI1/2/4")
    f_operator, base, f_dense, z_local, y_local = _fixture()
    try:
        action = FixedLinearOwnerRowPetrovCorrectionAction(
            base,
            f_operator,
            z_local,
            y_local,
            factor_inventory=base.diagnostics,
        )
        try:
            z_global = np.empty((8, 3), dtype=np.complex128)
            y_global = np.empty((8, 3), dtype=np.complex128)
            first, last = (int(value) for value in f_operator.getOwnershipRange())
            for begin, end, z_packet, y_packet in MPI.COMM_WORLD.allgather(
                (first, last, z_local, y_local)
            ):
                z_global[begin:end] = z_packet
                y_global[begin:end] = y_packet
            e = y_global.conj().T @ f_dense @ z_global
            base_inverse = np.diag(1.0 / np.diag(f_dense))
            expected_operator = base_inverse + z_global @ np.linalg.solve(
                e, y_global.conj().T @ (np.eye(8) - f_dense @ base_inverse)
            )
            source_values = np.asarray(
                [
                    0.3 - 0.4j,
                    -0.8 + 0.1j,
                    0.2 + 0.7j,
                    0.5 - 0.2j,
                    -0.1 + 0.9j,
                    0.6 + 0.2j,
                    -0.7 - 0.3j,
                    0.4 + 0.5j,
                ],
                dtype=np.complex128,
            )
            source = _vector(f_operator, source_values)
            target = f_operator.createVecLeft()
            repeat = f_operator.createVecLeft()
            doubled = _vector(f_operator, 2.0 * source_values)
            doubled_target = f_operator.createVecLeft()
            try:
                action.apply(source, target)
                action.apply(source, repeat)
                action.apply(doubled, doubled_target)
                expected = _vector(f_operator, expected_operator @ source_values)
                expected_doubled = _vector(
                    f_operator, expected_operator @ (2.0 * source_values)
                )
                try:
                    assert _relative_error(target, expected) <= 1.0e-12
                    assert _relative_error(repeat, target) <= 1.0e-12
                    assert _relative_error(doubled_target, expected_doubled) <= 1.0e-12
                finally:
                    expected_doubled.destroy()
                    expected.destroy()
            finally:
                doubled_target.destroy()
                doubled.destroy()
                repeat.destroy()
                target.destroy()
                source.destroy()
            diagnostics = action.diagnostics
            assert diagnostics["basis_storage"] == "owner_row_local"
            assert diagnostics["global_basis_materialized"] is False
            assert diagnostics["coarse_rank"] == 3
            assert diagnostics["coarse_e_svd_rank"] == 3
            assert np.isfinite(diagnostics["coarse_e_condition"])
            assert diagnostics["coarse_e_condition"] <= diagnostics["condition_limit"]
            assert diagnostics["apply_count"] == 3
            assert diagnostics["base_action_count"] == 3
            assert diagnostics["f_action_count"] == 6
            assert diagnostics["setup_f_action_count"] == 3
            assert diagnostics["exact_factor_count"] == 0
            assert diagnostics["global_direct_factor_count"] == 0
            assert diagnostics["z_local_bytes"] == z_local.nbytes
            assert diagnostics["y_local_bytes"] == y_local.nbytes
        finally:
            action.destroy()
            assert action.diagnostics["destroyed"] is True
            assert action.diagnostics["lifecycle"]["coarse_factor_released"] is True
            assert action.diagnostics["lifecycle"]["owned_vectors_released"] is True
            check_source = f_operator.createVecRight()
            check_target = f_operator.createVecLeft()
            with pytest.raises(RuntimeError, match="destroyed"):
                action.apply(check_source, check_target)
            check_target.destroy()
            check_source.destroy()
    finally:
        f_operator.destroy()


@pytest.mark.parametrize(
    "inventory",
    [
        {"exact_factor_count": 1, "global_direct_factor_count": 0},
        {"exact_factor_count": 0, "global_direct_factor_count": 1},
    ],
)
def test_petrov_rejects_exact_or_global_factor_inventory(inventory):
    f_operator, base, _f_dense, z_local, y_local = _fixture()
    try:
        with pytest.raises(ValueError, match="factor"):
            FixedLinearOwnerRowPetrovCorrectionAction(
                base,
                f_operator,
                z_local,
                y_local,
                factor_inventory=inventory,
            )
    finally:
        f_operator.destroy()


def test_petrov_rejects_explicit_inventory_conflicting_with_base():
    f_operator, base, _f_dense, z_local, y_local = _fixture()
    conflicting_base = _NonzeroExactBaseAction(base.diagonal)
    try:
        with pytest.raises(ValueError, match="Conflicting factor inventory key"):
            FixedLinearOwnerRowPetrovCorrectionAction(
                conflicting_base,
                f_operator,
                z_local,
                y_local,
                factor_inventory={
                    "exact_factor_count": 0,
                    "global_direct_factor_count": 0,
                },
            )
    finally:
        f_operator.destroy()


def test_petrov_rejects_singular_coarse_operator():
    f_operator, base, _f_dense, z_local, _y_local = _fixture()
    singular_y = np.column_stack((z_local[:, 0], z_local[:, 0], z_local[:, 2]))
    try:
        with pytest.raises(ValueError, match="rank deficient"):
            FixedLinearOwnerRowPetrovCorrectionAction(
                base,
                f_operator,
                z_local,
                singular_y,
                factor_inventory=base.diagnostics,
            )
    finally:
        f_operator.destroy()
