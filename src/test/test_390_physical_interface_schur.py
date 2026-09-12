"""Tiny PETSc tests for the V14 physical interface core."""
from types import SimpleNamespace

import numpy as np
from petsc4py import PETSc

from src.solvers.physical_interface_schur import (
    SchurPartition,
    _compact_port_data,
    build_physical_interface_schur,
    factorize_interface_schur,
    v11_memory_request_mb,
)


class NumpyFactor:
    """Injectable factor used to test production assembly and lifecycle."""

    def __init__(self, matrix):
        self.matrix = matrix
        self.dense = np.asarray(
            matrix.getValues(
                list(range(matrix.getSize()[0])),
                list(range(matrix.getSize()[1])),
            ),
            dtype=np.complex128,
        )
        self.symbolic_calls = 0
        self.numeric_calls = 0
        self.solve_calls = 0
        self.destroyed = False

    def symbolic(self, matrix):
        assert matrix is self.matrix
        self.symbolic_calls += 1

    def info(self, extra_indices=()):
        del extra_indices
        n = self.matrix.getSize()[0]
        return {"infog": {"16": 0, "17": 0}, "rows": int(n)}

    def symbolic_memory_settings(self):
        return {"icntl": {"7": 7, "10": 0, "14": 120, "18": 0, "22": 0, "23": 0}}

    def set_memory_limit_mb(self, value):
        assert value == 34

    def get_icntl(self, index):
        assert index == 23
        return 34

    def numeric(self, matrix):
        assert matrix is self.matrix
        self.numeric_calls += 1

    def solve_repeated(self, rhs, solution):
        solution.array[:] = np.linalg.solve(self.dense, rhs.array)
        self.solve_calls += 1

    def solve_adjoint(self, rhs, solution):
        solution.array[:] = np.linalg.solve(self.dense.conj().T, rhs.array)
        self.solve_calls += 1

    def destroy(self):
        self.destroyed = True


def _matrix(values):
    matrix = PETSc.Mat().createAIJ(
        values.shape,
        nnz=np.full(values.shape[0], values.shape[1], dtype=PETSc.IntType),
        comm=PETSc.COMM_SELF,
    )
    matrix.setValues(range(values.shape[0]), range(values.shape[1]), values)
    matrix.assemble()
    return matrix


def _core():
    rng = np.random.default_rng(39)
    volume = rng.normal(size=(7, 7)) + 1j * rng.normal(size=(7, 7))
    internal_a = [0, 1]
    internal_b = [2, 3]
    gamma = [4, 5, 6]
    volume[np.ix_(internal_a, internal_b)] = 0
    volume[np.ix_(internal_b, internal_a)] = 0
    volume[np.ix_(internal_a, internal_a)] += 5 * np.eye(2)
    volume[np.ix_(internal_b, internal_b)] += 5 * np.eye(2)
    B = np.zeros((7, 2), dtype=complex)
    B[[4, 5], 0] = rng.normal(size=2) + 1j * rng.normal(size=2)
    B[[5, 6], 1] = rng.normal(size=2) + 1j * rng.normal(size=2)
    D = np.zeros((2, 7), dtype=complex)
    D[0, [5, 6]] = rng.normal(size=2) + 1j * rng.normal(size=2)
    D[1, [4, 6]] = rng.normal(size=2) + 1j * rng.normal(size=2)
    H = np.diag([2 + 1j, 3 - 0.5j]).astype(complex)
    entry0 = SimpleNamespace(
        coupling_rows=np.array([4, 5]),
        coupling_values=B[[4, 5], 0],
        projection_rows=np.array([5, 6]),
        projection_values=D[0, [5, 6]],
        normalization_h=H[0, 0],
    )
    entry1 = SimpleNamespace(
        coupling_rows=np.array([5, 6]),
        coupling_values=B[[5, 6], 1],
        projection_rows=np.array([4, 6]),
        projection_values=D[1, [4, 6]],
        normalization_h=H[1, 1],
    )
    carrier = SimpleNamespace(entries=(entry0, entry1), global_rows=7)
    partition = SchurPartition(
        storage_size=7,
        active_full_indices=np.arange(7),
        slave_full_indices=np.empty(0, dtype=np.int64),
        gamma_full_indices=np.asarray(gamma),
        gamma_active_indices=np.asarray(gamma),
        internal_blocks_full=(
            np.asarray(internal_a),
            np.asarray(internal_b),
        ),
        internal_blocks_active=(
            np.asarray(internal_a),
            np.asarray(internal_b),
        ),
        seed_group_count=2,
        port_support_full_indices=np.asarray(gamma),
    )
    matrix = _matrix(volume)
    core = build_physical_interface_schur(
        matrix,
        partition,
        carrier,
        factor_factory=NumpyFactor,
        owns_volume=False,
    )
    return core, matrix, volume, B, D, H


def test_v11_delegates_zero_and_checks_both_mumps_fields():
    result = v11_memory_request_mb({"infog": {"16": 0, "17": 0}})
    assert result["estimate_bytes"] == 1_000_000
    assert result["request_mb"] == 34
    with np.testing.assert_raises(RuntimeError):
        v11_memory_request_mb({"infog": {"16": 20, "17": 21}})


def test_port_mapping_projects_full_storage_rows_around_a_slave():
    mapped = _compact_port_data(
        [
            {
                "port": 0,
                "coupling_rows": np.array([1, 5]),
                "coupling_values": np.array([0, 2 + 1j]),
                "projection_rows": np.array([1, 6]),
                "projection_values": np.array([0, -1j]),
                "normalization_h": 2,
            }
        ],
        np.array([0, -1, 1, 2, 3, 4, 5, 6]),
        {4: 0, 5: 1, 6: 2},
    )
    np.testing.assert_array_equal(mapped[0]["b_gamma"], [0])
    np.testing.assert_array_equal(mapped[0]["d_gamma"], [1])
    np.testing.assert_allclose(mapped[0]["b_values"], [2 + 1j])
    np.testing.assert_allclose(mapped[0]["d_values"], [-1j])


def test_production_schur_apply_adjoint_recover_and_nonhermitian_ports():
    core, volume_matrix, volume, B, D, H = _core()
    try:
        rng = np.random.default_rng(40)
        rhs = rng.normal(size=7) + 1j * rng.normal(size=7)
        rhs_vec = volume_matrix.createVecRight()
        rhs_vec.array[:] = rhs
        x_gamma = core.S_V.createVecRight()
        x_gamma.array[:] = rng.normal(size=3) + 1j * rng.normal(size=3)
        explicit = core.S_V.createVecLeft()
        core.S_V.mult(x_gamma, explicit)
        matrix_free = core.apply_volume_schur(x_gamma)
        np.testing.assert_allclose(matrix_free.array, explicit.array, rtol=0, atol=2e-12)

        explicit_adj = core.S_V.createVecRight()
        core.S_V.multHermitian(x_gamma, explicit_adj)
        matrix_free_adj = core.apply_volume_schur_adjoint(x_gamma)
        np.testing.assert_allclose(
            matrix_free_adj.array, explicit_adj.array, rtol=0, atol=2e-12
        )

        physical = core.apply_physical_schur(x_gamma)
        gamma = core.partition.gamma_active_indices
        s_volume = volume[np.ix_(gamma, gamma)].copy()
        for block in ([0, 1], [2, 3]):
            s_volume -= volume[np.ix_(gamma, block)] @ np.linalg.solve(
                volume[np.ix_(block, block)], volume[np.ix_(block, gamma)]
            )
        expected_physical = s_volume + B[gamma, :] @ np.linalg.solve(H, D[:, gamma])
        np.testing.assert_allclose(
            physical.array,
            expected_physical @ x_gamma.array,
            rtol=0,
            atol=2e-12,
        )
        physical_adj = core.apply_physical_schur_adjoint(x_gamma)
        np.testing.assert_allclose(
            physical_adj.array,
            expected_physical.conj().T @ x_gamma.array,
            rtol=0,
            atol=2e-12,
        )

        x_interface = core.interface_matrix.createVecRight()
        x_interface.array[:] = rng.normal(size=5) + 1j * rng.normal(size=5)
        explicit_interface = core.interface_matrix.createVecLeft()
        core.interface_matrix.mult(x_interface, explicit_interface)
        matrix_free_interface = core.apply_interface_matrix_free(x_interface)
        np.testing.assert_allclose(
            matrix_free_interface.array,
            explicit_interface.array,
            rtol=0,
            atol=2e-12,
        )

        recovered_before = core.recover(rhs_vec, x_gamma)
        factorize_interface_schur(core, factor_factory=NumpyFactor)
        solution, facts = core.solve(rhs_vec, return_facts=True)
        augmented = np.block([[volume, B], [-D, H]])
        expected_rhs = np.r_[rhs, np.zeros(2, dtype=complex)]
        got = np.r_[solution.array, facts["interface_solution"][3:]]
        np.testing.assert_allclose(
            augmented @ got,
            expected_rhs,
            rtol=0,
            atol=2e-12,
        )
        assert facts["interface_solves"] == 1
        core.release_global_factor()
        core.release_explicit_schur()
        recovered_after_factor_release = core.recover(rhs_vec, x_gamma)
        np.testing.assert_allclose(
            recovered_after_factor_release.array,
            recovered_before.array,
            rtol=0,
            atol=2e-12,
        )
        physical_after_release = core.apply_physical_schur(x_gamma)
        np.testing.assert_allclose(
            physical_after_release.array,
            physical.array,
            rtol=0,
            atol=2e-12,
        )
        assert not np.allclose(B, D.conj().T)
    finally:
        for value in (
            locals().get("rhs_vec"),
            locals().get("x_gamma"),
            locals().get("explicit"),
            locals().get("matrix_free"),
            locals().get("explicit_adj"),
            locals().get("matrix_free_adj"),
            locals().get("physical"),
            locals().get("physical_adj"),
            locals().get("x_interface"),
            locals().get("explicit_interface"),
            locals().get("matrix_free_interface"),
            locals().get("recovered_before"),
            locals().get("recovered_after_schur_release"),
            locals().get("recovered_after_factor_release"),
            locals().get("physical_after_release"),
        ):
            if value is not None:
                value.destroy()
        core.destroy()
        volume_matrix.destroy()


def test_mumps_adjoint_reuses_one_live_complex_factor():
    from src.solvers.fullspace_v17_p3_oracle import _MumpsFactor

    values = np.array(
        [[3 + 1j, 1 - 2j, 0.2], [0.5 + 0.3j, 4 - 1j, 1 + 0.1j], [0, 0.7, 3 + 2j]],
        dtype=complex,
    )
    matrix = _matrix(values)
    rhs = matrix.createVecRight()
    rhs.array[:] = [1 + 2j, 2 - 1j, 3 + 0.5j]
    rhs_before = rhs.array.copy()
    forward = rhs.duplicate()
    adjoint = rhs.duplicate()
    forward_again = rhs.duplicate()
    checked = rhs.duplicate()
    factor = None
    try:
        factor = _MumpsFactor(matrix)
        factor.symbolic(matrix)
        factor.set_memory_limit_mb(512)
        factor.numeric(matrix)
        factor.solve(rhs, forward)
        factor.solve_adjoint(rhs, adjoint)
        factor.solve_repeated(rhs, forward_again)
        matrix.mult(forward, checked)
        np.testing.assert_allclose(checked.array, rhs_before, rtol=0, atol=2e-12)
        matrix.multHermitian(adjoint, checked)
        np.testing.assert_allclose(checked.array, rhs_before, rtol=0, atol=2e-12)
        np.testing.assert_allclose(forward_again.array, forward.array, rtol=0, atol=2e-12)
        np.testing.assert_array_equal(rhs.array, rhs_before)
        assert factor.symbolic_calls == 1
        assert factor.numeric_calls == 1
        assert factor.solve_calls == 3
    finally:
        if factor is not None:
            factor.destroy()
        for value in (checked, forward_again, adjoint, forward, rhs, matrix):
            value.destroy()
