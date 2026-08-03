from __future__ import annotations

from pathlib import Path
import hashlib
import json
import tempfile
import unittest
from unittest.mock import patch

from dolfinx import fem
from mpi4py import MPI
import numpy as np
from petsc4py import PETSc
from slepc4py import SLEPc

from benchmarks.run_task036_one_cell_discrete_bloch import (
    _authority_config,
    _one_cell_config,
)
from benchmarks.task036_transfer_capacity import joint_cauchy_pairing
from benchmarks.run_task036_transfer_optimal_port_capacity import (
    _gc_projected_orthonormalize_block,
    build_b1_harmonic_extension,
    build_primal_reachable_pod_prefixes,
    solve_b1_reduced_petrov,
    build_global_two_end_petrov_fixture,
    load_v9_mode_pool,
    SparsePortTransfer,
    select_v9_block_prefixes,
    v9_core_complement_rank,
    v9_endpoint_cauchy_arrays,
)
from benchmarks.run_task036_r1_port_capacity import (
    MODE_POOL_EIGEN_TOL,
    MODE_POOL_FORMAL_GREEN_TOL,
    MODE_POOL_SPAN_TOL,
    MODE_POOL_STRICT_GREEN_DIAGNOSTIC_TOL,
    MODE_POOL_TARGETS,
    MODE_POOL_SOURCE_SCHEDULE,
    _canonical_npz_arrays,
    _canonicalize_candidate,
    _deduplicate_candidates,
    _closed_selected_component_indices,
    _select_pairing_subblock,
    _selected_pairing_gate,
    _bounded_right_components,
    _right_pool_gate,
    _residual_ok,
    _right_reciprocal_closure,
    _column_span_residual,
    _green_metrics_pass,
)
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.solvers.common_3d_forms import _build_variational_forms
from src.solvers.common_3d_solve import _create_nedelec_space
from src.solvers.hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
)
from src.solvers.hybrid_port_metric import (
    EndpointTraceMassSelection,
    build_endpoint_trace_mass_actions,
)
from src.solvers.one_cell_discrete_bloch import (
    AugmentedBlochPolynomial,
    OneCellTwoPortSchurAction,
    ProjectedTwoPortSchur,
    bloch_polynomial_action,
    build_augmented_bloch_polynomial,
    compose_projected_two_port_schur,
    build_reversed_hermitian_bloch_polynomial,
    endpoint_cauchy_columns,
    endpoint_cauchy_balance,
    identify_endpoint_active_rows,
)


class Task036TransferCapacityDiscreteTests(unittest.TestCase):
    def test_sparse_port_transfer_bulk_primal_dual_matches_columns(self) -> None:
        transfer = SparsePortTransfer(
            source_size=4,
            target_size=3,
            rows={
                0: (
                    np.asarray([0, 2], dtype=np.int64),
                    np.asarray([1.0 + 0.2j, -0.3 + 0.1j]),
                ),
                1: (
                    np.asarray([1, 3], dtype=np.int64),
                    np.asarray([0.4 - 0.2j, 0.7 + 0.05j]),
                ),
                2: (
                    np.asarray([0, 1, 3], dtype=np.int64),
                    np.asarray([-0.2 + 0.3j, 0.6 - 0.1j, 0.15 + 0.4j]),
                ),
            },
        )
        source = np.asarray(
            [
                [0.2 + 0.1j, -0.4 + 0.3j, 0.7 - 0.2j],
                [1.0 - 0.2j, 0.5 + 0.4j, -0.1 + 0.6j],
                [-0.3 + 0.8j, 0.9 - 0.5j, 0.2 + 0.7j],
                [0.6 + 0.2j, -0.8 + 0.1j, 0.3 - 0.4j],
            ],
            dtype=np.complex128,
        )
        target_dual = np.asarray(
            [
                [0.3 - 0.2j, 0.8 + 0.1j, -0.5 + 0.4j],
                [-0.7 + 0.6j, 0.2 - 0.3j, 0.9 + 0.05j],
                [0.4 + 0.7j, -0.1 + 0.8j, 0.6 - 0.2j],
            ],
            dtype=np.complex128,
        )
        primal_bulk = transfer.primal(source)
        dual_bulk = transfer.dual(target_dual)
        primal_columns = np.column_stack(
            [transfer.primal(source[:, column]) for column in range(source.shape[1])]
        )
        dual_columns = np.column_stack(
            [
                transfer.dual(target_dual[:, column])
                for column in range(target_dual.shape[1])
            ]
        )
        np.testing.assert_allclose(primal_bulk, primal_columns, atol=1.0e-13)
        np.testing.assert_allclose(dual_bulk, dual_columns, atol=1.0e-13)
        np.testing.assert_allclose(
            np.vdot(target_dual, primal_bulk),
            np.vdot(dual_bulk, source),
            atol=1.0e-13,
        )

        forward = SparsePortTransfer(
            source_size=2,
            target_size=2,
            rows={
                0: (np.asarray([0, 1]), np.asarray([1.0, 1.0])),
                1: (np.asarray([1]), np.asarray([2.0])),
            },
        )
        reverse = SparsePortTransfer(
            source_size=2,
            target_size=2,
            rows={
                0: (np.asarray([0, 1]), np.asarray([1.0, -0.5])),
                1: (np.asarray([1]), np.asarray([0.5])),
            },
        )
        source_e = np.asarray([[0.3 + 0.2j], [-0.4 + 0.1j]])
        source_q = np.asarray([[0.6 - 0.3j], [0.2 + 0.5j]])
        target_e = forward.primal(source_e)
        target_q = reverse.dual(source_q)
        np.testing.assert_allclose(
            np.vdot(target_q, target_e), np.vdot(source_q, source_e)
        )
        self.assertFalse(np.allclose(target_q, forward.primal(source_q)))

        class Action:
            left_rows = 2

        pool = {
            "right_states": np.zeros((3, 1), dtype=np.complex128),
            "adjoint_states": np.zeros((3, 1), dtype=np.complex128),
            "right_multipliers": np.asarray([3.0 + 0.0j]),
            "adjoint_multipliers": np.asarray([2.0 + 0.0j]),
            "right_block_ids": np.asarray([7], dtype=np.int64),
        }
        columns = (
            np.asarray([[1.0], [2.0], [3.0], [6.0]]),
            np.asarray([[4.0], [5.0], [-12.0], [-15.0]]),
            np.asarray([[1.0], [2.0], [2.0], [4.0]]),
            np.asarray([[7.0], [8.0], [-14.0], [-16.0]]),
        )
        with patch(
            "benchmarks.run_task036_transfer_optimal_port_capacity.endpoint_cauchy_columns",
            return_value=columns,
        ):
            top_forward = SparsePortTransfer(
                source_size=2,
                target_size=2,
                rows={
                    0: (np.asarray([0]), np.asarray([1.5])),
                    1: (np.asarray([0, 1]), np.asarray([0.25, 0.75])),
                },
            )
            top_reverse = SparsePortTransfer(
                source_size=2,
                target_size=2,
                rows={
                    0: (np.asarray([0, 1]), np.asarray([0.8, -0.2])),
                    1: (np.asarray([1]), np.asarray([1.4])),
                },
            )
            mapped = v9_endpoint_cauchy_arrays(
                Action(),
                pool,
                {
                    "bottom": (forward, reverse),
                    "top": (top_forward, top_reverse),
                },
            )
        np.testing.assert_allclose(
            mapped["right_electric"][:2], top_forward.primal([1, 2])[:, None]
        )
        np.testing.assert_allclose(
            mapped["right_electric"][2:], forward.primal([1, 2])[:, None]
        )
        np.testing.assert_allclose(
            mapped["right_traction"][:2], top_reverse.dual([4, 5])[:, None]
        )
        np.testing.assert_allclose(
            mapped["right_traction"][2:], reverse.dual([4, 5])[:, None]
        )
        self.assertFalse(
            np.allclose(
                mapped["right_electric"][:2], mapped["right_electric"][2:]
            )
        )
        self.assertFalse(
            np.allclose(
                mapped["right_traction"][:2], mapped["right_traction"][2:]
            )
        )
        np.testing.assert_array_equal(
            mapped["right_multipliers"], pool["right_multipliers"]
        )
        np.testing.assert_array_equal(
            mapped["adjoint_multipliers"], pool["adjoint_multipliers"]
        )
        self.assertFalse(
            np.allclose(
                mapped["right_traction"][:2], forward.primal([4, 5])[:, None]
            )
        )
        J = np.array([[2.0, 0.4], [0.0, 1.3]], dtype=np.complex128)
        J_inverse = np.linalg.inv(J)
        w_local = np.array([[0.7 + 0.2j], [-0.3 + 0.5j]])
        residual_local = np.array([[0.2 - 0.1j], [0.6 + 0.4j]])
        residual_canonical = J.conj().T @ residual_local
        w_canonical = J_inverse @ w_local
        np.testing.assert_allclose(
            np.vdot(w_canonical, residual_canonical),
            np.vdot(w_local, residual_local),
            atol=1.0e-13,
        )
        self.assertFalse(np.allclose(J.conj().T @ w_local, w_canonical))

    def test_projected_metric_qr_preserves_complement_and_existing(self) -> None:
        metric = np.diag(np.arange(1.0, 7.0))

        def gc_action(values: np.ndarray) -> np.ndarray:
            return metric @ values

        existing = np.zeros((6, 1), dtype=np.complex128)
        existing[0, 0] = 1.0
        candidate = np.array(
            [
                [0.25 + 0.1j, -0.5 + 0.2j],
                [1.0 + 0.3j, 0.2 - 0.4j],
                [0.1 - 0.2j, 0.8 + 0.1j],
                [0.4 + 0.5j, -0.3 + 0.6j],
                [0.7 - 0.1j, 0.5 + 0.2j],
                [-0.2 + 0.4j, 0.9 - 0.3j],
            ]
        )

        def projector(values: np.ndarray) -> np.ndarray:
            return values - existing @ (existing.conj().T @ gc_action(values))

        block = _gc_projected_orthonormalize_block(
            candidate, existing, gc_action, projector
        )
        np.testing.assert_allclose(projector(block), block, atol=1.0e-12)
        np.testing.assert_allclose(
            block.conj().T @ gc_action(block),
            np.eye(block.shape[1]),
            atol=1.0e-12,
        )
        np.testing.assert_allclose(
            existing.conj().T @ gc_action(block),
            np.zeros((1, block.shape[1])),
            atol=1.0e-12,
        )

    def test_joint_cauchy_pairing_is_hpd_and_unit_invariant(self) -> None:
        rng = np.random.default_rng(36061)
        seed = rng.standard_normal((4, 4)) + 1j * rng.standard_normal((4, 4))
        mass_nm = seed.conj().T @ seed + 0.8 * np.eye(4)
        electric = rng.standard_normal(4) + 1j * rng.standard_normal(4)
        traction = rng.standard_normal(4) + 1j * rng.standard_normal(4)
        other_electric = rng.standard_normal(4) + 1j * rng.standard_normal(4)
        other_traction = rng.standard_normal(4) + 1j * rng.standard_normal(4)
        k0_nm = 0.46542113386515455
        area_nm = 1250.0
        reference = 1.0 + 0.0j

        forward = joint_cauchy_pairing(
            electric,
            traction,
            other_electric,
            other_traction,
            mass_nm,
            k0=k0_nm,
            area=area_nm,
            electric_reference=reference,
        )
        reverse = joint_cauchy_pairing(
            other_electric,
            other_traction,
            electric,
            traction,
            mass_nm,
            k0=k0_nm,
            area=area_nm,
            electric_reference=reference,
        )
        self.assertLess(abs(forward - reverse.conjugate()), 1.0e-12)
        self.assertGreater(
            joint_cauchy_pairing(
                electric,
                traction,
                electric,
                traction,
                mass_nm,
                k0=k0_nm,
                area=area_nm,
                electric_reference=reference,
            ).real,
            0.0,
        )

        length_scale = 1.0e-9
        metric_nm = joint_cauchy_pairing(
            electric,
            traction,
            other_electric,
            other_traction,
            mass_nm,
            k0=k0_nm,
            area=area_nm,
            electric_reference=reference,
        )
        metric_m = joint_cauchy_pairing(
            length_scale * electric,
            traction,
            length_scale * other_electric,
            other_traction,
            mass_nm,
            k0=k0_nm / length_scale,
            area=length_scale**2 * area_nm,
            electric_reference=reference,
        )
        np.testing.assert_allclose(metric_m, metric_nm, rtol=1.0e-12, atol=1.0e-12)
        rho = -0.7 + 1.3j
        rescaled = joint_cauchy_pairing(
            rho * electric,
            rho * traction,
            rho * other_electric,
            rho * other_traction,
            mass_nm,
            k0=k0_nm,
            area=area_nm,
            electric_reference=rho * reference,
        )
        np.testing.assert_allclose(rescaled, metric_nm, rtol=1.0e-12, atol=1.0e-12)

    @unittest.skipUnless(
        MPI.COMM_WORLD.size == 1,
        "The deterministic PEP fixture is serial.",
    )
    def test_full_interface_bloch_polynomial_uses_batched_schur_action(self) -> None:
        self.assertEqual(MODE_POOL_EIGEN_TOL, 1.0e-12)

        def matrix(values: np.ndarray) -> PETSc.Mat:
            rows, cols = values.shape
            indptr = [0]
            indices: list[int] = []
            data: list[complex] = []
            for row in range(rows):
                nonzero = np.flatnonzero(values[row])
                indices.extend(nonzero.tolist())
                data.extend(values[row, nonzero].tolist())
                indptr.append(len(indices))
            result = PETSc.Mat().createAIJ(
                size=(rows, cols),
                csr=(
                    np.asarray(indptr, dtype=PETSc.IntType),
                    np.asarray(indices, dtype=PETSc.IntType),
                    np.asarray(data, dtype=np.complex128),
                ),
                comm=PETSc.COMM_SELF,
            )
            result.assemble()
            return result

        action = OneCellTwoPortSchurAction(
            A_pp=matrix(np.asarray([[0.0, 1.0], [-1.0, 0.0]])),
            A_pi=matrix(np.asarray([[1.0], [0.0]])),
            A_ip=matrix(np.asarray([[0.0, 1.5]])),
            A_ii=matrix(np.asarray([[2.0]])),
            factor=PETSc.KSP().create(PETSc.COMM_SELF),
            left_rows=1,
            right_rows=1,
            interior_rows=1,
            interior_matrix_nnz=1,
            port_active=np.asarray([0, 1], dtype=PETSc.IntType),
            interior_active=np.asarray([2], dtype=PETSc.IntType),
        )
        action.factor.setOperators(action.A_ii)
        action.factor.setType("preonly")
        action.factor.getPC().setType("lu")
        action.factor.setUp()
        augmented: AugmentedBlochPolynomial | None = None
        pep = None
        prev_pep = None
        linear_left = None
        prev_vector = None
        try:
            augmented = build_augmented_bloch_polynomial(action)
            self.assertFalse(action.dense_interface_square_formed)
            self.assertFalse(augmented.dense_interface_square_formed)
            self.assertEqual(augmented.state_rows, 2)

            def sparse_apply(operator: PETSc.Mat, values: np.ndarray) -> np.ndarray:
                vector = operator.createVecRight()
                result = operator.createVecLeft()
                try:
                    vector.array[:] = values
                    operator.mult(vector, result)
                    return np.asarray(result.array, dtype=np.complex128).copy()
                finally:
                    result.destroy()
                    vector.destroy()

            def sparse_apply_h(operator: PETSc.Mat, values: np.ndarray) -> np.ndarray:
                vector = operator.createVecLeft()
                result = operator.createVecRight()
                try:
                    vector.array[:] = values
                    operator.multHermitian(vector, result)
                    return np.asarray(
                        result.array,
                        dtype=np.complex128,
                    ).copy()
                finally:
                    result.destroy()
                    vector.destroy()

            def create_two_sided_pep(
                operators: tuple[PETSc.Mat, PETSc.Mat, PETSc.Mat],
                nev: int,
            ) -> SLEPc.PEP:
                pep = SLEPc.PEP().create(comm=PETSc.COMM_SELF)
                pep.setOperators(list(operators))
                pep.setProblemType(SLEPc.PEP.ProblemType.GENERAL)
                pep.setType(SLEPc.PEP.Type.LINEAR)
                pep.setLinearExplicitMatrix(True)
                pep.setLinearLinearization(alpha=1.0, beta=0.0)
                pep.setDimensions(nev=nev)
                pep.setTarget(0.7)
                pep.setWhichEigenpairs(SLEPc.PEP.Which.TARGET_MAGNITUDE)
                pep.setTolerances(tol=1.0e-12, max_it=100)
                eps = pep.getLinearEPS()
                eps.setType(SLEPc.EPS.Type.KRYLOVSCHUR)
                eps.setTwoSided(True)
                eps.setDimensions(nev=nev)
                eps.setTarget(0.7)
                eps.setWhichEigenpairs(SLEPc.EPS.Which.TARGET_MAGNITUDE)
                eps.setTolerances(tol=1.0e-12, max_it=100)
                spectral_transform = eps.getST()
                spectral_transform.setType(SLEPc.ST.Type.SINVERT)
                ksp = spectral_transform.getKSP()
                ksp.setType(PETSc.KSP.Type.PREONLY)
                pc = ksp.getPC()
                pc.setType(PETSc.PC.Type.LU)
                pc.setFactorSolverType("mumps")
                return pep

            for multiplier, electric in (
                (0.73 + 0.11j, 0.4 - 0.2j),
                (-0.61 + 0.27j, -0.3 + 0.6j),
            ):
                interior = -0.75 * multiplier * electric
                state = np.asarray([electric, interior], dtype=np.complex128)
                augmented_value = (
                    sparse_apply(augmented.K0, state)
                    + multiplier * sparse_apply(augmented.K1, state)
                    + multiplier**2 * sparse_apply(augmented.K2, state)
                )
                coefficients = bloch_polynomial_action(
                    action,
                    np.asarray([[electric]], dtype=np.complex128),
                )
                schur_value = (
                    coefficients[0][:, 0]
                    + multiplier * coefficients[1][:, 0]
                    + multiplier**2 * coefficients[2][:, 0]
                )
                np.testing.assert_allclose(
                    augmented_value[:1], schur_value, rtol=0.0, atol=1.0e-12
                )
                np.testing.assert_allclose(
                    augmented_value[1:], np.zeros(1), rtol=0.0, atol=1.0e-12
                )

            pep = create_two_sided_pep((augmented.K0, augmented.K1, augmented.K2), 2)
            eps = pep.getLinearEPS()
            pep.solve()
            self.assertGreaterEqual(pep.getConverged(), 2)
            self.assertEqual(eps.getConverged(), pep.getConverged())
            linear_left = PETSc.Vec().create(comm=PETSc.COMM_SELF)
            linear_left.setSizes((4, 4))
            linear_left.setUp()
            right_vector = augmented.K0.createVecRight()
            for index in range(2):
                eigenvalue = complex(pep.getEigenpair(index, right_vector))
                self.assertLess(
                    min(abs(eigenvalue - 2.0), abs(eigenvalue + 2.0)),
                    1.0e-9,
                )
                self.assertLess(
                    float(pep.computeError(index, SLEPc.PEP.ErrorType.RELATIVE)),
                    1.0e-9,
                )
                self.assertLess(
                    abs(eigenvalue - complex(eps.getEigenvalue(index))),
                    1.0e-9,
                )
                right_state = np.asarray(
                    right_vector.getArray(readonly=True), dtype=np.complex128
                ).copy()
                right_residual = sum(
                    coefficient * sparse_apply(operator, right_state)
                    for coefficient, operator in zip(
                        (1.0, eigenvalue, eigenvalue**2),
                        (augmented.K0, augmented.K1, augmented.K2),
                    )
                )
                self.assertLess(np.linalg.norm(right_residual), 1.0e-9)
                eps.getLeftEigenvector(index, linear_left)
                linear_state = np.asarray(
                    linear_left.getArray(readonly=True), dtype=np.complex128
                )
                self.assertEqual(len(linear_state), 2 * augmented.state_rows)
                left_state = linear_state[augmented.state_rows :]
                left_residual = sum(
                    coefficient * sparse_apply_h(operator, left_state)
                    for coefficient, operator in zip(
                        (1.0, np.conj(eigenvalue), np.conj(eigenvalue) ** 2),
                        (augmented.K0, augmented.K1, augmented.K2),
                    )
                )
                self.assertLess(np.linalg.norm(left_residual), 1.0e-9)
                _, qrev_nu, _, _ = _canonicalize_candidate(
                    "Qrev",
                    np.conj(eigenvalue),
                    left_state,
                    endpoint_rows=1,
                )
                _, q_nu, _, _ = _canonicalize_candidate(
                    "Q",
                    np.conj(1.0 / eigenvalue),
                    left_state,
                    endpoint_rows=1,
                )
                np.testing.assert_allclose(
                    qrev_nu,
                    1.0 / np.conj(eigenvalue),
                    rtol=0.0,
                    atol=1.0e-12,
                )
                np.testing.assert_allclose(
                    q_nu,
                    qrev_nu,
                    rtol=0.0,
                    atol=1.0e-12,
                )
                p_green = endpoint_cauchy_balance(
                    action,
                    right_state,
                    left_state,
                    multipliers=[eigenvalue],
                    adjoint_multipliers=[qrev_nu],
                )
                self.assertLessEqual(
                    p_green["primal_outward_balance_relative"], 1.0e-10
                )
                self.assertLessEqual(
                    p_green["adjoint_outward_balance_relative"], 1.0e-10
                )
                self.assertLessEqual(p_green["green_pairing_relative"], 1.0e-10)
                electric, traction, adjoint, adjoint_traction = endpoint_cauchy_columns(
                    action,
                    right_state,
                    left_state,
                    multipliers=[eigenvalue],
                    adjoint_multipliers=[qrev_nu],
                )
                self.assertEqual(electric.shape, (2, 1))
                self.assertEqual(traction.shape, (2, 1))
                self.assertEqual(adjoint.shape, (2, 1))
                self.assertEqual(adjoint_traction.shape, (2, 1))
                np.testing.assert_allclose(
                    electric[1], eigenvalue * electric[0], atol=1.0e-12
                )
                np.testing.assert_allclose(
                    adjoint[1], qrev_nu * adjoint[0], atol=1.0e-12
                )
            right_vector.destroy()
            prev_pep = create_two_sided_pep(
                (augmented.K2, augmented.K1, augmented.K0), 2
            )
            prev_eps = prev_pep.getLinearEPS()
            prev_pep.solve()
            self.assertGreaterEqual(prev_pep.getConverged(), 2)
            self.assertEqual(prev_eps.getConverged(), prev_pep.getConverged())
            prev_vector = augmented.K0.createVecRight()
            prev_indices: list[int] = []
            for index in range(prev_pep.getConverged()):
                zeta = complex(prev_pep.getEigenpair(index, prev_vector))
                if np.isfinite(zeta) and abs(zeta - 0.5) < 1.0e-6:
                    prev_indices.append(index)
            self.assertEqual(len(prev_indices), 1)
            for index in prev_indices:
                zeta = complex(prev_pep.getEigenpair(index, prev_vector))
                self.assertLess(
                    min(abs(zeta - 0.5), abs(zeta + 0.5)),
                    1.0e-9,
                )
                self.assertLess(
                    float(
                        prev_pep.computeError(
                            index,
                            SLEPc.PEP.ErrorType.RELATIVE,
                        )
                    ),
                    1.0e-9,
                )
                self.assertLess(
                    abs(zeta - complex(prev_eps.getEigenvalue(index))),
                    1.0e-9,
                )
                prev_state = np.asarray(
                    prev_vector.getArray(readonly=True), dtype=np.complex128
                ).copy()
                _, canonical_lambda, mapped_state, prev_mapping = (
                    _canonicalize_candidate(
                        "Prev",
                        zeta,
                        prev_state,
                        endpoint_rows=1,
                    )
                )
                np.testing.assert_array_equal(mapped_state, prev_state)
                np.testing.assert_allclose(
                    canonical_lambda,
                    1.0 / zeta,
                    rtol=0.0,
                    atol=1.0e-12,
                )
                self.assertEqual(prev_mapping["state_map"], "identity")
                canonical_residual = sum(
                    coefficient * sparse_apply(operator, prev_state)
                    for coefficient, operator in zip(
                        (1.0, canonical_lambda, canonical_lambda**2),
                        (augmented.K0, augmented.K1, augmented.K2),
                    )
                )
                self.assertLess(np.linalg.norm(canonical_residual), 1.0e-9)
                prev_eps.getLeftEigenvector(index, linear_left)
                prev_linear_state = np.asarray(
                    linear_left.getArray(readonly=True), dtype=np.complex128
                )
                prev_left_state = prev_linear_state[augmented.state_rows :]
                _, prev_nu, mapped_left, prev_left_mapping = _canonicalize_candidate(
                    "Q",
                    np.conj(zeta),
                    prev_left_state,
                    endpoint_rows=1,
                )
                np.testing.assert_array_equal(mapped_left, prev_left_state)
                self.assertEqual(prev_left_mapping["state_map"], "identity")
                np.testing.assert_allclose(
                    prev_nu,
                    np.conj(zeta),
                    rtol=0.0,
                    atol=1.0e-12,
                )
                left_q_residual = sum(
                    coefficient * sparse_apply_h(operator, prev_left_state)
                    for coefficient, operator in zip(
                        (1.0, prev_nu, prev_nu**2),
                        (augmented.K2, augmented.K1, augmented.K0),
                    )
                )
                self.assertLess(np.linalg.norm(left_q_residual), 1.0e-9)
                prev_green = endpoint_cauchy_balance(
                    action,
                    prev_state,
                    prev_left_state,
                    multipliers=[canonical_lambda],
                    adjoint_multipliers=[prev_nu],
                )
                self.assertLessEqual(
                    prev_green["primal_outward_balance_relative"], 1.0e-10
                )
                self.assertLessEqual(
                    prev_green["adjoint_outward_balance_relative"], 1.0e-10
                )
                self.assertLessEqual(prev_green["green_pairing_relative"], 1.0e-10)
        finally:
            if prev_vector is not None:
                prev_vector.destroy()
            if linear_left is not None:
                linear_left.destroy()
            if prev_pep is not None:
                prev_pep.destroy()
            if pep is not None:
                pep.destroy()
            if augmented is not None:
                augmented.destroy()
            action.destroy()

    @unittest.skipUnless(
        MPI.COMM_WORLD.size == 1,
        "The deterministic adjoint Bloch fixture is serial.",
    )
    def test_reversed_hermitian_bloch_and_endpoint_green_contract(self) -> None:
        def matrix(values: np.ndarray) -> PETSc.Mat:
            rows, cols = values.shape
            indptr = [0]
            indices: list[int] = []
            data: list[complex] = []
            for row in range(rows):
                nonzero = np.flatnonzero(values[row])
                indices.extend(nonzero.tolist())
                data.extend(values[row, nonzero].tolist())
                indptr.append(len(indices))
            result = PETSc.Mat().createAIJ(
                size=(rows, cols),
                csr=(
                    np.asarray(indptr, dtype=PETSc.IntType),
                    np.asarray(indices, dtype=PETSc.IntType),
                    np.asarray(data, dtype=np.complex128),
                ),
                comm=PETSc.COMM_SELF,
            )
            result.assemble()
            return result

        A_pp = np.asarray(
            [
                [1.2 + 0.3j, 0.4 - 0.2j],
                [-0.7 + 0.1j, 1.1 - 0.25j],
            ],
            dtype=np.complex128,
        )
        A_pi = np.asarray(
            [[0.8 + 0.15j], [-0.35 + 0.2j]],
            dtype=np.complex128,
        )
        A_ip = np.asarray(
            [[0.2 - 0.4j, 0.55 + 0.1j]],
            dtype=np.complex128,
        )
        A_ii = np.asarray([[2.3 + 0.4j]], dtype=np.complex128)
        blocks = [matrix(values) for values in (A_pp, A_pi, A_ip, A_ii)]
        factor = PETSc.KSP().create(PETSc.COMM_SELF)
        factor.setType(PETSc.KSP.Type.PREONLY)
        factor.getPC().setType(PETSc.PC.Type.LU)
        factor.setOperators(blocks[3])
        factor.setUp()
        action = OneCellTwoPortSchurAction(
            *blocks,
            factor=factor,
            left_rows=1,
            right_rows=1,
            interior_rows=1,
            interior_matrix_nnz=1,
            port_active=np.asarray([0, 1], dtype=PETSc.IntType),
            interior_active=np.asarray([2], dtype=PETSc.IntType),
        )
        augmented: AugmentedBlochPolynomial | None = None
        reversed_polynomial = None
        try:
            augmented = build_augmented_bloch_polynomial(action)
            reversed_polynomial = build_reversed_hermitian_bloch_polynomial(augmented)
            Schur = A_pp - A_pi @ np.linalg.solve(A_ii, A_ip)
            K0 = Schur[1:2, 0:1]
            K1 = Schur[1:2, 1:2] + Schur[0:1, 0:1]
            K2 = Schur[0:1, 1:2]
            multiplier = min(
                np.roots([K2[0, 0], K1[0, 0], K0[0, 0]]),
                key=abs,
            )
            adjoint_multiplier = 1.0 / np.conj(multiplier)
            left_electric = np.asarray([[1.0 + 0.0j]])
            left_adjoint = np.asarray([[1.0 + 0.0j]])
            endpoint_electric = np.vstack((left_electric, multiplier * left_electric))
            endpoint_adjoint = np.vstack(
                (left_adjoint, adjoint_multiplier * left_adjoint)
            )
            interior = -np.linalg.solve(
                A_ii,
                A_ip @ endpoint_electric,
            )
            adjoint_interior = (
                -np.linalg.solve(
                    A_ii.conj().T,
                    A_pi.conj().T @ endpoint_adjoint,
                )
                / adjoint_multiplier
            )
            state = np.vstack((left_electric, interior))
            adjoint_state = np.vstack((left_adjoint, adjoint_interior))

            def sparse_apply(
                operator: PETSc.Mat,
                values: np.ndarray,
            ) -> np.ndarray:
                vector = operator.createVecRight()
                result = operator.createVecLeft()
                try:
                    vector.array[:] = values[:, 0]
                    operator.mult(vector, result)
                    return np.asarray(
                        result.array,
                        dtype=np.complex128,
                    ).copy()[:, None]
                finally:
                    result.destroy()
                    vector.destroy()

            right_residual = sum(
                coefficient * sparse_apply(operator, state)
                for coefficient, operator in (
                    (1.0, augmented.K0),
                    (multiplier, augmented.K1),
                    (multiplier**2, augmented.K2),
                )
            )
            adjoint_residual = sum(
                coefficient * sparse_apply(operator, adjoint_state)
                for coefficient, operator in (
                    (1.0, reversed_polynomial.K0),
                    (adjoint_multiplier, reversed_polynomial.K1),
                    (adjoint_multiplier**2, reversed_polynomial.K2),
                )
            )
            self.assertLess(np.linalg.norm(right_residual), 1.0e-12)
            self.assertLess(np.linalg.norm(adjoint_residual), 1.0e-12)
            self.assertLess(
                np.linalg.norm(
                    K2.conj().T
                    + adjoint_multiplier * K1.conj().T
                    + adjoint_multiplier**2 * K0.conj().T
                ),
                1.0e-12,
            )
            wrong_order = (
                K0.conj().T
                + adjoint_multiplier * K1.conj().T
                + adjoint_multiplier**2 * K2.conj().T
            )
            self.assertGreater(np.linalg.norm(wrong_order), 1.0e-3)
            self.assertLess(
                abs(adjoint_multiplier - 1.0 / np.conj(multiplier)),
                1.0e-14,
            )
            metrics = endpoint_cauchy_balance(
                action,
                state,
                adjoint_state,
                multipliers=[multiplier],
                adjoint_multipliers=[adjoint_multiplier],
            )
            np.testing.assert_allclose(
                action.apply_adjoint_columns(endpoint_adjoint),
                Schur.conj().T @ endpoint_adjoint,
                rtol=0.0,
                atol=1.0e-12,
            )
            self.assertLess(
                metrics["primal_outward_balance_relative"],
                1.0e-12,
            )
            self.assertLess(
                metrics["adjoint_outward_balance_relative"],
                1.0e-12,
            )
            self.assertLess(metrics["green_pairing_relative"], 1.0e-12)
            tampered_state = state.copy()
            tampered_state[-1, 0] += 0.37 - 0.21j
            tampered_metrics = endpoint_cauchy_balance(
                action,
                tampered_state,
                adjoint_state,
                multipliers=[multiplier],
                adjoint_multipliers=[adjoint_multiplier],
            )
            self.assertGreater(
                tampered_metrics["primal_outward_balance_relative"],
                1.0e-3,
            )
            tampered_adjoint = adjoint_state.copy()
            tampered_adjoint[-1, 0] += 0.19 + 0.27j
            tampered_adjoint_metrics = endpoint_cauchy_balance(
                action,
                state,
                tampered_adjoint,
                multipliers=[multiplier],
                adjoint_multipliers=[adjoint_multiplier],
            )
            self.assertGreater(
                tampered_adjoint_metrics["adjoint_outward_balance_relative"],
                1.0e-3,
            )
        finally:
            if reversed_polynomial is not None:
                reversed_polynomial.destroy()
            if augmented is not None:
                augmented.destroy()
            action.destroy()

    def test_r1b_fixed_family_pool_contracts_without_pep(self) -> None:
        self.assertEqual(MODE_POOL_FORMAL_GREEN_TOL, 1.0e-8)
        self.assertEqual(MODE_POOL_STRICT_GREEN_DIAGNOSTIC_TOL, 1.0e-10)
        self.assertEqual(MODE_POOL_SPAN_TOL, 1.0e-8)
        self.assertEqual(
            MODE_POOL_TARGETS,
            (
                1.0 + 0.0j,
                1.0j,
                -1.0 + 0.0j,
                -1.0j,
                0.38268343236508984 + 0.9238795325112867j,
                0.38268343236508984 - 0.9238795325112867j,
            ),
        )
        self.assertEqual(
            MODE_POOL_SOURCE_SCHEDULE,
            (("P", 0), ("P", 1), ("P", 2), ("P", 3), ("P", 4), ("P", 5), ("Prev", 2)),
        )
        unit = np.eye(5, dtype=np.complex128)
        right_pool = np.column_stack(
            (np.sqrt(50.0) * unit[:, 0], np.sqrt(50.0) * unit[:, 1],
             np.sqrt(10.0) * unit[:, 4], np.sqrt(40.0) * unit[:, 2],
             np.sqrt(40.0) * unit[:, 3])
        )
        adjoint_pool = np.column_stack(
            (np.sqrt(0.5) * unit[:, 0], np.sqrt(0.5) * unit[:, 1],
             np.sqrt(120.0) * unit[:, 4], np.sqrt(40.0) * unit[:, 2],
             np.sqrt(40.0) * unit[:, 3])
        )
        block_columns = ((0, 1), (2,), (3, 4))
        right_energy = [
            np.linalg.norm(right_pool[:, cols]) ** 2 for cols in block_columns
        ]
        adjoint_energy = [
            np.linalg.norm(adjoint_pool[:, cols]) ** 2 for cols in block_columns
        ]
        self.assertEqual(int(np.argmax(right_energy)), 0)
        self.assertEqual(int(np.argmax(adjoint_energy)), 1)
        prefixes = select_v9_block_prefixes(
            {"bottom": right_pool, "top": right_pool},
            {"bottom": adjoint_pool, "top": adjoint_pool},
            np.array([0, 0, 1, 2, 2]),
            {"bottom": right_pool, "top": right_pool},
            {"bottom": adjoint_pool, "top": adjoint_pool},
            requested=(2, 3, 5),
        )
        prefix_values = prefixes["prefixes"]
        self.assertEqual(prefixes["ordering"], [2, 1, 0])
        self.assertEqual(
            [prefix_values[str(target)]["effective_r"] for target in (2, 3, 5)],
            [2, 3, 5],
        )
        self.assertEqual(
            [
                prefix_values[str(target)]["raw_column_count"]
                for target in (2, 3, 5)
            ],
            [2, 3, 5],
        )
        expected_blocks = ([2], [2, 1], [2, 1, 0])
        expected_indices = ([3, 4], [3, 4, 2], [3, 4, 2, 0, 1])
        for target, blocks, indices in zip(
            (2, 3, 5), expected_blocks, expected_indices
        ):
            prefix = prefix_values[str(target)]
            self.assertEqual(prefix["selected_block_count"], len(blocks))
            self.assertEqual(
                prefix["selected_block_ids_sha256"],
                hashlib.sha256(
                    np.asarray(blocks, dtype=np.int64).tobytes()
                ).hexdigest(),
            )
            self.assertEqual(
                prefix["selected_indices_sha256"],
                hashlib.sha256(
                    np.asarray(indices, dtype=np.int64).tobytes()
                ).hexdigest(),
            )
            self.assertEqual(
                prefix["selected_right_rank_by_side"]["bottom"], target
            )
            self.assertEqual(
                prefix["selected_adjoint_rank_by_side"]["bottom"], target
            )
            self.assertEqual(
                prefix["selected_right_rank_by_side"]["bottom"],
                prefix["per_side"]["bottom"]["right"]["selected_rank"],
            )
            self.assertEqual(
                prefix["selected_adjoint_rank_by_side"]["bottom"],
                prefix["per_side"]["bottom"]["adjoint"]["selected_rank"],
            )
            self.assertEqual(
                prefix["pairing_by_side"]["bottom"]["rank"],
                prefix["pairing_by_side"]["top"]["rank"],
            )
            self.assertEqual(
                prefix["pairing_by_side"]["bottom"]["rank"], target
            )
        duplicate_pool = np.column_stack(
            (
                np.array([1, 0, 0], dtype=np.complex128),
                np.array([1, 0, 0], dtype=np.complex128),
            )
        )
        duplicate = select_v9_block_prefixes(
            {"bottom": duplicate_pool},
            {"bottom": duplicate_pool},
            np.array([0, 0]),
            {"bottom": duplicate_pool},
            {"bottom": duplicate_pool},
            requested=(1,),
        )["prefixes"]["1"]
        self.assertEqual(duplicate["raw_column_count"], 2)
        self.assertEqual(
            duplicate["selected_right_rank_by_side"]["bottom"], 1
        )
        self.assertEqual(
            duplicate["selected_adjoint_rank_by_side"]["bottom"], 1
        )
        self.assertEqual(
            duplicate["pairing_by_side"]["bottom"]["rank"], 1
        )
        self.assertAlmostEqual(duplicate["pairing_by_side"]["bottom"]["condition"], 1.0)
        scale_spread = np.column_stack(
            (
                np.array([1.0, 0.0], dtype=np.complex128),
                1.0e-11 * np.array([0.0, 1.0], dtype=np.complex128),
            )
        )
        spread = select_v9_block_prefixes(
            {"bottom": scale_spread},
            {"bottom": scale_spread},
            np.array([0, 1]),
            {"bottom": scale_spread},
            {"bottom": scale_spread},
            requested=(2,),
        )["prefixes"]["2"]
        self.assertEqual(spread["effective_r"], 1)
        self.assertEqual(spread["selected_right_rank_by_side"]["bottom"], 1)
        self.assertEqual(spread["selected_adjoint_rank_by_side"]["bottom"], 1)
        self.assertEqual(spread["raw_column_count"], 2)
        self.assertEqual(spread["pairing_by_side"]["bottom"]["rank"], 1)
        empty_prefix = select_v9_block_prefixes(
            {"bottom": np.eye(2, dtype=np.complex128)},
            {"bottom": np.eye(2, dtype=np.complex128)},
            np.array([0, 0], dtype=np.int64),
            {"bottom": np.eye(2, dtype=np.complex128)},
            {"bottom": np.eye(2, dtype=np.complex128)},
            requested=(1,),
        )["prefixes"]["1"]
        self.assertEqual(empty_prefix["effective_r"], 0)
        self.assertEqual(empty_prefix["raw_column_count"], 0)
        self.assertEqual(empty_prefix["selected_block_count"], 0)
        self.assertEqual(empty_prefix["selected_right_rank_by_side"]["bottom"], 0)
        self.assertEqual(
            empty_prefix["selected_adjoint_rank_by_side"]["bottom"], 0
        )
        self.assertEqual(empty_prefix["pairing_by_side"]["bottom"]["rank"], 0)
        self.assertIsNone(empty_prefix["pairing_by_side"]["bottom"]["condition"])
        ill_adjoint = np.column_stack(
            (
                np.array([1, 0, 0], dtype=np.complex128),
                np.array([0, 0, 1], dtype=np.complex128),
            )
        )
        ill = select_v9_block_prefixes(
            {"bottom": np.eye(3, 2, dtype=np.complex128)},
            {"bottom": ill_adjoint},
            np.array([0, 0]),
            {"bottom": np.eye(3, 2, dtype=np.complex128)},
            {"bottom": ill_adjoint},
            requested=(2,),
        )["prefixes"]["2"]["pairing_by_side"]["bottom"]
        self.assertEqual(ill["right_trial_rank"], 2)
        self.assertEqual(ill["adjoint_test_rank"], 2)
        self.assertEqual(ill["rank"], 1)
        self.assertIsNone(ill["condition"])
        duplicate_pairing = _select_pairing_subblock(
            np.ones((3, 3), dtype=np.complex128),
            [10, 11, 12],
            [20, 21, 22],
        )
        self.assertEqual(duplicate_pairing["numerical_rank"], 1)
        self.assertEqual(
            duplicate_pairing["selected"]["right_indices"],
            [10],
        )
        self.assertEqual(
            duplicate_pairing["selected"]["adjoint_indices"],
            [20],
        )
        full_pairing = _select_pairing_subblock(
            np.diag([1.0, 0.5]).astype(np.complex128),
            [30, 31],
            [40, 41],
        )
        self.assertEqual(full_pairing["numerical_rank"], 2)
        self.assertEqual(full_pairing["selected"]["right_indices"], [30, 31])
        self.assertLessEqual(full_pairing["selected"]["condition"], 1.0e10)
        green = {
            "green_pairing_relative": 1.0e-12,
            "primal_outward_balance_relative": 2.0e-12,
            "adjoint_outward_balance_relative": 3.0e-12,
        }
        self.assertTrue(_selected_pairing_gate(2.0, green))
        self.assertFalse(_selected_pairing_gate(1.0e10 + 1.0, green))
        for key in green:
            failed_green = dict(green)
            failed_green[key] = MODE_POOL_FORMAL_GREEN_TOL + 1.0e-12
            self.assertFalse(_selected_pairing_gate(2.0, failed_green))
        diagnostic_only_green = {key: 5.0e-9 for key in green}
        self.assertTrue(_selected_pairing_gate(2.0, diagnostic_only_green))
        self.assertFalse(
            _green_metrics_pass(
                diagnostic_only_green,
                MODE_POOL_STRICT_GREEN_DIAGNOSTIC_TOL,
            )
        )
        self.assertFalse(
            _selected_pairing_gate(
                2.0,
                {key: MODE_POOL_FORMAL_GREEN_TOL + 1.0e-12 for key in green},
            )
        )
        duplicate_states = np.ones((2, 3), dtype=np.complex128)
        self.assertLessEqual(
            _column_span_residual(duplicate_states, duplicate_states[:, [0]]),
            MODE_POOL_SPAN_TOL,
        )
        independent_states = np.eye(2, dtype=np.complex128)
        self.assertGreater(
            _column_span_residual(independent_states, independent_states[:, [0]]),
            MODE_POOL_SPAN_TOL,
        )
        self.assertLessEqual(
            _column_span_residual(independent_states, independent_states),
            MODE_POOL_SPAN_TOL,
        )
        self.assertEqual(
            _closed_selected_component_indices(
                [[0, 1]],
                {0: {"selected_rank": 1}, 1: {"selected_rank": 2}},
            ),
            [],
        )
        self.assertEqual(
            _closed_selected_component_indices(
                [[0, 1]],
                {0: {"selected_rank": 2}, 1: {"selected_rank": 2}},
            ),
            [0, 1],
        )
        state = np.asarray([1.0 + 0.0j, 0.0j], dtype=np.complex128)
        variable, multiplier, mapped, metadata = _canonicalize_candidate(
            "Prev",
            0.5 + 0.0j,
            state,
            endpoint_rows=1,
        )
        self.assertEqual(variable, "lambda")
        self.assertEqual(multiplier, 2.0 + 0.0j)
        np.testing.assert_array_equal(mapped, state)
        self.assertEqual(metadata["state_map"], "identity")
        variable, multiplier, mapped, metadata = _canonicalize_candidate(
            "Qrev",
            2.0 + 0.0j,
            state,
            endpoint_rows=1,
        )
        self.assertEqual(variable, "nu")
        self.assertEqual(multiplier, 0.5 + 0.0j)
        np.testing.assert_array_equal(mapped, state)
        self.assertEqual(metadata["state_map"], "identity")
        for family, variable in (("P", "lambda"), ("Q", "nu")):
            mapped_variable, mapped_multiplier, _, _ = _canonicalize_candidate(
                family,
                0.0,
                state,
                endpoint_rows=1,
            )
            self.assertEqual(mapped_variable, variable)
            self.assertEqual(mapped_multiplier, 0.0j)
        for family in ("Prev", "Qrev"):
            with self.assertRaises(ValueError):
                _canonicalize_candidate(family, 0.0, state, endpoint_rows=1)

        def entry(
            family: str,
            target_index: int,
            multiplier: complex,
            vector: list[complex],
        ) -> dict[str, object]:
            record = {
                "full_augmented_relative_residual": 1.0e-9,
                "schur_polynomial_relative_residual": 2.0e-9,
            }
            return {
                "family": family,
                "target_index": target_index,
                "source_key": (family, target_index),
                "multiplier": multiplier,
                "state": np.asarray(vector, dtype=np.complex128),
                "record": record,
            }

        entries = [
            entry("P", 0, 2.0, [1.0, 0.0]),
            entry("P", 0, 2.0 + 5.0e-7, [0.0, 1.0]),
            entry("Prev", 1, 0.5, [1.0, 0.0]),
            entry("P", 1, 0.5, [1.0, 0.0]),
            entry("P", 1, 0.5 + 4.0e-7, [0.0, 1.0]),
            entry("Prev", 2, 2.0, [1.0, 0.0]),
            entry("Prev", 3, 2.0 - 4.0e-7, [0.0, 1.0]),
        ]
        kept, removed = _deduplicate_candidates(entries)
        self.assertEqual(len(kept), 4)
        self.assertEqual(removed["Prev"], 2)
        self.assertEqual(
            {(item["family"], item["target_index"]) for item in kept},
            {("P", 0), ("Prev", 1), ("P", 1)},
        )
        closure = _right_reciprocal_closure(
            [item["multiplier"] for item in kept],
            kept,
        )
        self.assertEqual(closure["effective_columns"], 4)
        self.assertEqual(len(closure["components"]), 1)
        poisoned = entry("P", 0, 2.0, [1.0, 0.0])
        poisoned["record"]["full_augmented_relative_residual"] = 1.0e-3
        poisoned_closure = _right_reciprocal_closure(
            [item["multiplier"] for item in kept + [poisoned]],
            kept + [poisoned],
        )
        self.assertEqual(poisoned_closure["effective_columns"], 0)
        residual_first = [item for item in kept + [poisoned] if _residual_ok(item)]
        residual_first_closure = _right_reciprocal_closure(
            [item["multiplier"] for item in residual_first],
            residual_first,
        )
        self.assertEqual(residual_first_closure["effective_columns"], 4)
        self.assertFalse(_right_pool_gate(4)["passed"])
        self.assertEqual(
            _right_pool_gate(4)["status_if_failed"],
            "MODE_POOL_INCOMPLETE_AT_TARGET_SET",
        )
        partial_run = {
            "family": "P",
            "target_index": 1,
            "convergence_reason": -1,
            "residual_qualified_count": 3,
        }
        partial_gate = _right_pool_gate(
            120,
            phase_bins=[1] * 8,
            full_residual_max=1.0e-8,
            schur_residual_max=9.0e-8,
            partial_runs=[partial_run],
        )
        self.assertTrue(partial_gate["passed"])
        self.assertEqual(partial_gate["partial_runs"], [partial_run])
        missing_evidence_gate = _right_pool_gate(120, phase_bins=[1] * 8)
        self.assertFalse(missing_evidence_gate["passed"])
        self.assertEqual(
            missing_evidence_gate["reason"],
            "right_pool_gate_evidence_missing",
        )
        zero_gate = _right_pool_gate(
            120,
            phase_bins=[1] * 8,
            full_residual_max=1.0e-8,
            schur_residual_max=9.0e-8,
            unusable_runs=[
                {
                    "family": "P",
                    "target_index": 2,
                    "convergence_reason": 1,
                    "residual_qualified_count": 0,
                }
            ],
        )
        self.assertFalse(zero_gate["passed"])
        self.assertEqual(zero_gate["reason"], "right_solver_failed")
        self.assertEqual(zero_gate["status_if_failed"], "MODE_POOL_SOLVER_FAILED")
        empty_phase_gate = _right_pool_gate(
            120,
            phase_bins=[1, 1, 1, 1, 1, 1, 1, 0],
            full_residual_max=1.0e-8,
            schur_residual_max=9.0e-8,
        )
        self.assertFalse(empty_phase_gate["passed"])
        self.assertEqual(
            empty_phase_gate["reason"],
            "right_pool_phase_coverage_incomplete",
        )
        zero_entry = entry("P", 3, 0.0, [1.0, 0.0])
        zero_closure = _right_reciprocal_closure(
            [item["multiplier"] for item in kept] + [zero_entry["multiplier"]],
            kept + [zero_entry],
        )
        zero_block = next(
            index for index, block in enumerate(zero_closure["blocks"]) if 4 in block
        )
        self.assertNotIn(zero_block, zero_closure["effective_block_indices"])
        oversized = _bounded_right_components(
            {
                "blocks": [list(range(250)), list(range(250, 500))],
                "components": [[0], [1]],
                "effective_block_indices": [0, 1],
                "effective_columns": 500,
            }
        )
        self.assertEqual(oversized["raw_effective_columns"], 500)
        self.assertEqual(oversized["bounded_effective_columns"], 250)
        self.assertEqual(oversized["bounded_effective_block_indices"], [0])
        self.assertLessEqual(oversized["bounded_effective_columns"], 360)
        arrays = _canonical_npz_arrays(
            kept,
            closure["blocks"],
            state_rows=2,
            prefix="right",
        )
        with tempfile.TemporaryDirectory(prefix="task036-r1b-contract-") as tmp:
            path = Path(tmp) / "pool.npz"
            np.savez_compressed(path, **arrays)
            with np.load(path) as loaded:
                self.assertEqual(loaded["right_states"].shape, (2, 4))
                self.assertEqual(loaded["right_multipliers"].shape, (4,))
                self.assertEqual(loaded["right_block_ids"].shape, (4,))
                self.assertEqual(loaded["right_target_index"].dtype, np.dtype(np.int32))

        with tempfile.TemporaryDirectory(prefix="task036-v9-identity-") as tmp:
            root = Path(tmp)
            npz_path = root / "runner_result.npz"
            arrays = {
                "right_multipliers": np.ones(184, dtype=np.complex128),
                "right_states": np.zeros((3240, 184), dtype=np.complex128),
                "right_block_ids": np.arange(184, dtype=np.int32),
                "right_family": np.full(184, "P", dtype="U4"),
                "right_target_index": np.zeros(184, dtype=np.int32),
                "adjoint_multipliers": np.ones(184, dtype=np.complex128),
                "adjoint_states": np.zeros((3240, 184), dtype=np.complex128),
                "adjoint_block_ids": np.arange(184, dtype=np.int32),
                "adjoint_family": np.full(184, "Qrev", dtype="U8"),
                "adjoint_target_index": np.zeros(184, dtype=np.int32),
            }
            np.savez_compressed(npz_path, **arrays)
            digest = hashlib.sha256(npz_path.read_bytes()).hexdigest()
            json_path = root / "runner_result.json"
            json_path.write_text(
                json.dumps(
                    {
                        "status": "mode-pool-qualified",
                        "source": {
                            "sha": "d3bed04a33778baf84d6c0938bd4ad305cb36edf"
                        },
                        "canonical_npz_manifest": {"sha256": digest},
                    }
                ),
                encoding="utf-8",
            )
            json_digest = hashlib.sha256(json_path.read_bytes()).hexdigest()
            loaded = load_v9_mode_pool(
                json_path,
                npz_path,
                expected_json_sha=json_digest,
                expected_npz_sha=digest,
            )
            self.assertEqual(loaded["right_states"].shape, (3240, 184))
            self.assertTrue(np.array_equal(loaded["right_block_ids"], loaded["adjoint_block_ids"]))

        core = np.zeros((2400, 240), dtype=np.complex128)
        core[:240] = np.eye(240, dtype=np.complex128)
        complement_columns = np.zeros((2400, 3), dtype=np.complex128)
        complement_columns[300, 0] = 1.0
        complement_columns[301, 1] = 1.0
        complement_columns[302, 2] = 1.0
        complement_rank = v9_core_complement_rank(
            complement_columns, core, lambda values: values
        )
        self.assertEqual(complement_rank["raw_columns"], 3)
        self.assertEqual(complement_rank["complement_rank_rcond_1e_10"], 3)

        p = 2
        cell_left_left = np.array(
            [[1.2, 0.1 + 0.2j], [0.3j, 0.8]], dtype=np.complex128
        )
        cell_right_right = np.array(
            [[0.9 - 0.1j, 0.2], [0.05, 1.1]], dtype=np.complex128
        )
        lower = np.array(
            [[-0.2, 0.03], [0.01j, -0.15]], dtype=np.complex128
        )
        upper = np.array(
            [[-0.17, -0.02j], [0.04, -0.21]], dtype=np.complex128
        )
        endpoint_left = np.array(
            [[0.4, 0.02j], [-0.03, 0.25]], dtype=np.complex128
        )
        endpoint_right = np.array(
            [[0.35 - 0.02j, 0.01], [0.04j, 0.3]], dtype=np.complex128
        )
        teacher_trace = np.array(
            [
                [1.0, 0.2j, 0.4],
                [0.3, 0.7, -0.1j],
                [-0.2j, 0.6, 0.8],
                [0.5, -0.4j, 0.1],
                [0.9, 0.2, -0.3j],
                [-0.7j, 0.1, 0.6],
            ],
            dtype=np.complex128,
        )
        x_bottom, x_middle, x_top = (
            teacher_trace[:p],
            teacher_trace[p : 2 * p],
            teacher_trace[2 * p :],
        )
        bottom_cell_q = cell_left_left @ x_bottom + upper @ x_middle
        top_cell_q = lower @ x_middle + cell_right_right @ x_top
        bottom_total_q = (cell_left_left + endpoint_left) @ x_bottom + upper @ x_middle
        top_total_q = lower @ x_middle + (cell_right_right + endpoint_right) @ x_top
        self.assertFalse(np.allclose(bottom_cell_q, bottom_total_q))
        self.assertFalse(np.allclose(top_cell_q, top_total_q))
        teacher_by_side = {
            "bottom": np.vstack((x_bottom, bottom_cell_q)),
            "top": np.vstack((x_top, top_cell_q)),
        }
        core_by_side = {
            "bottom": np.vstack((np.eye(2), np.zeros((2, 2)))),
            "top": np.vstack((np.zeros((2, 2)), np.eye(2))),
        }
        source_keys = (("source", 0), ("source", 1), ("source", 2))
        pod = build_primal_reachable_pod_prefixes(
            teacher_by_side,
            {side: values.copy() for side, values in teacher_by_side.items()},
            core_by_side,
            {side: values.copy() for side, values in core_by_side.items()},
            {"bottom": source_keys, "top": source_keys},
        )
        self.assertEqual(pod["status"], "trial_capacity_scaffold")
        self.assertEqual(pod["raw_source_columns"], 3)
        self.assertEqual(pod["raw_source_rank"], 3)
        self.assertEqual(pod["effective_source_rank"], 3)
        self.assertLessEqual(pod["global_core_orthogonality_relative"], 1.0e-12)
        self.assertLessEqual(
            pod["joint_corrector_metric_identity_relative"], 1.0e-12
        )
        for target in (40, 80, 96, 120):
            prefix = pod["prefixes"][str(target)]
            self.assertEqual(prefix["effective_r"], 3)
            self.assertEqual(prefix["raw_checkpoint_dimension"], 5)
        self.assertEqual(pod["corrector_by_side"]["bottom"].shape, (4, 3))
        self.assertEqual(pod["corrector_by_side"]["top"].shape, (4, 3))
        zero_prefix = pod["prefixes"]["0"]
        self.assertEqual(zero_prefix["requested_r"], 0)
        self.assertEqual(zero_prefix["effective_r"], 0)
        self.assertEqual(zero_prefix["raw_checkpoint_dimension"], 2)
        self.assertAlmostEqual(zero_prefix["discarded_energy_relative"], 1.0)
        swapped_teacher = dict(teacher_by_side)
        swapped_teacher["top"] = teacher_by_side["top"][:, [1, 0, 2]]
        with self.assertRaises(ValueError):
            build_primal_reachable_pod_prefixes(
                swapped_teacher,
                {side: values.copy() for side, values in swapped_teacher.items()},
                core_by_side,
                {side: values.copy() for side, values in core_by_side.items()},
                {"bottom": source_keys, "top": (source_keys[1], source_keys[0], source_keys[2])},
            )

    def test_global_two_end_petrov_shared_columns_and_independent_rhs(self) -> None:
        left_port = ProjectedTwoPortSchur(
            S_LL=np.array([[2.0 + 0.1j, 0.1], [0.02j, 1.8 - 0.1j]]),
            S_LR=np.array([[0.2, 0.05j], [-0.04, 0.15]]),
            S_RL=np.array([[0.1 + 0.02j, -0.03], [0.04j, 0.12]]),
            S_RR=np.array([[2.5, 0.08j], [0.01, 2.3 + 0.05j]]),
            port_rows=4,
            interior_rows=2,
            interior_matrix_nnz=8,
        )
        right_port = ProjectedTwoPortSchur(
            S_LL=np.array([[2.7 - 0.05j, -0.03], [0.01j, 2.4 + 0.08j]]),
            S_LR=np.array([[0.16, -0.02j], [0.03, 0.11]]),
            S_RL=np.array([[0.07j, 0.02], [-0.05, 0.09 - 0.01j]]),
            S_RR=np.array([[2.9 + 0.04j, 0.02], [-0.01j, 2.6]]),
            port_rows=4,
            interior_rows=3,
            interior_matrix_nnz=9,
        )
        composed, _ = compose_projected_two_port_schur(left_port, right_port)
        operator = np.block(
            [[composed.S_LL, composed.S_LR], [composed.S_RL, composed.S_RR]]
        )
        reachable_coefficients = np.array(
            [0.3 + 0.2j, -0.4 + 0.1j, 0.5 - 0.3j, -0.2 + 0.6j]
        )
        kwargs = {
            "bottom_core": np.eye(2, dtype=np.complex128),
            "top_core": np.diag([0.65 + 0.02j, 0.72 - 0.03j]),
            "right_bottom_scale": np.array([1.0, 0.9 + 0.02j]),
            "right_top_scale": np.array([0.8 - 0.01j, 0.7 + 0.03j]),
            "adjoint_bottom_core": np.array([[1.0, 0.08j], [0.04, 0.96 - 0.02j]]),
            "adjoint_top_core": np.array(
                [[0.58 + 0.02j, 0.03], [-0.02j, 0.68 - 0.01j]]
            ),
            "adjoint_bottom_scale": np.array([1.0, 0.94 - 0.01j]),
            "adjoint_top_scale": np.array([0.76 + 0.02j, 0.66 - 0.02j]),
            "bottom_corrector": np.eye(2, dtype=np.complex128),
            "top_corrector": 0.2 * np.eye(2, dtype=np.complex128),
            "adjoint_bottom_corrector": np.array([[1.0, 0.03], [-0.02j, 0.98]]),
            "adjoint_top_corrector": 0.16 * np.eye(2, dtype=np.complex128),
            "block_ids": np.array([7, 7], dtype=np.int64),
            "selected_indices": np.array([0, 1], dtype=np.int64),
            "top_block_ids": np.array([7, 7], dtype=np.int64),
            "requested_r": 40,
            "left_port": left_port,
            "right_port": right_port,
            # Manufactured reachable RHS; the helper never constructs it.
            "rhs": operator @ reachable_coefficients,
        }
        report = build_global_two_end_petrov_fixture(**kwargs)
        self.assertEqual(report["global_primal_shape"], [4, 4])
        self.assertEqual(report["raw_trial_rank"], 4)
        self.assertEqual(report["raw_test_rank"], 4)
        self.assertEqual(report["paired_effective_rank"], 4)
        self.assertEqual(report["reduced_dimension"], 4)
        self.assertEqual(report["selected_raw_corrector_columns"], 2)
        self.assertEqual(report["selected_whole_block_count"], 1)
        self.assertLess(report["pairing_condition"], 1.0e3)
        self.assertLess(report["petrov_stationarity_relative"], 1.0e-12)
        self.assertLess(report["direct_solution_relative"], 1.0e-12)
        redundant = {
            **kwargs,
            "bottom_corrector": np.ones((2, 2), dtype=np.complex128),
            "top_corrector": 0.2 * np.ones((2, 2), dtype=np.complex128),
            "adjoint_bottom_corrector": np.ones((2, 2), dtype=np.complex128),
            "adjoint_top_corrector": 0.16 * np.ones((2, 2), dtype=np.complex128),
        }
        redundant_report = build_global_two_end_petrov_fixture(**redundant)
        self.assertEqual(redundant_report["raw_trial_rank"], 3)
        self.assertEqual(redundant_report["raw_test_rank"], 3)
        self.assertEqual(redundant_report["paired_effective_rank"], 3)
        self.assertEqual(redundant_report["selected_raw_corrector_columns"], 2)
        with self.assertRaises(ValueError):
            build_global_two_end_petrov_fixture(
                **{
                    **kwargs,
                    "top_corrector": kwargs["top_corrector"][:, ::-1],
                    "top_block_ids": np.array([7, 8], dtype=np.int64),
                }
            )

    def test_b1_harmonic_extension_uses_endpoint_action_and_shared_prefix(self) -> None:
        compact = {
            "bottom_diagonal": np.array([[1.3, 0.08j], [0.04, 1.1]]),
            "middle_diagonal": np.array([[2.0, 0.12j], [0.03, 1.7]]),
            "top_diagonal": np.array([[1.4, -0.05j], [0.06, 1.2]]),
            "lower": np.array([[-0.22, 0.03j], [0.01, -0.19]]),
            "upper": np.array([[-0.17, -0.02j], [0.05, -0.21]]),
        }
        endpoint_basis = np.array(
            [
                [1.0, 0.1j, 0.3],
                [0.2, 0.9, -0.15j],
                [0.6, -0.2j, 0.8],
                [-0.1, 0.7, 0.25j],
            ],
            dtype=np.complex128,
        )
        test_basis = np.array(
            [
                [0.9, -0.05j, 0.2],
                [0.1j, 1.1, -0.1],
                [0.4, 0.03, 0.7j],
                [0.2, -0.6j, 0.5],
            ],
            dtype=np.complex128,
        )

        def chain_action(values: np.ndarray) -> np.ndarray:
            planes = np.asarray(values).reshape(11, 2, -1)
            result = np.zeros_like(planes)
            result[0] = compact["bottom_diagonal"] @ planes[0] + compact["upper"] @ planes[1]
            for index in range(1, 10):
                result[index] = (
                    compact["lower"] @ planes[index - 1]
                    + compact["middle_diagonal"] @ planes[index]
                    + compact["upper"] @ planes[index + 1]
                )
            result[10] = (
                compact["lower"] @ planes[9] + compact["top_diagonal"] @ planes[10]
            )
            return result.reshape(22, -1)

        trace, endpoint_action, _ = build_b1_harmonic_extension(compact, endpoint_basis)
        trace_action = chain_action(trace)
        np.testing.assert_allclose(trace_action[2:-2], 0.0, atol=1.0e-12)
        np.testing.assert_allclose(
            endpoint_action,
            np.vstack((trace_action[:2], trace_action[-2:])),
            atol=1.0e-12,
            rtol=0.0,
        )
        coefficients = np.asarray([[0.4 - 0.1j], [-0.2 + 0.3j], [0.5 + 0.2j]])
        full_rhs = chain_action(trace @ coefficients)
        endpoint_rhs = np.vstack((full_rhs[:2], full_rhs[-2:]))
        report = solve_b1_reduced_petrov(
            trace,
            endpoint_basis,
            endpoint_action,
            test_basis,
            endpoint_rhs,
            full_rhs,
            chain_action,
        )
        self.assertEqual(report["trial_rank"], 3)
        self.assertEqual(report["test_rank"], 3)
        self.assertEqual(report["petrov_operator_rank"], 3)
        self.assertEqual(report["reduced_dimension"], 3)
        self.assertLess(report["petrov_operator_condition"], 1.0e3)
        self.assertLess(report["best_trial_endpoint_residual_relative"], 1.0e-12)
        self.assertLess(report["petrov_stationarity_relative"], 1.0e-12)
        self.assertLess(report["full_trace_residual_relative"], 1.0e-12)

        core_trace, core_action, _ = build_b1_harmonic_extension(
            compact, endpoint_basis[:, :2]
        )
        np.testing.assert_allclose(core_trace, trace[:, :2], atol=1.0e-12, rtol=0.0)
        np.testing.assert_allclose(
            core_action, endpoint_action[:, :2], atol=1.0e-12, rtol=0.0
        )
        core_rhs = chain_action(core_trace @ coefficients[:2])
        core_report = solve_b1_reduced_petrov(
            core_trace,
            endpoint_basis[:, :2],
            core_action,
            test_basis[:, :2],
            np.vstack((core_rhs[:2], core_rhs[-2:])),
            core_rhs,
            chain_action,
        )
        self.assertEqual(core_report["petrov_operator_rank"], 2)

        negative_trace = np.eye(4, 2, dtype=np.complex128)
        negative_test = np.vstack((np.zeros((2, 2)), np.eye(2)))
        negative_operator = np.zeros((4, 4), dtype=np.complex128)
        negative_operator[2:, :2] = np.eye(2)
        negative_action = negative_operator @ negative_trace
        negative_coefficients = np.array([[0.2 + 0.1j], [-0.4 + 0.3j]])
        negative_rhs = negative_action @ negative_coefficients
        negative = solve_b1_reduced_petrov(
            negative_trace,
            negative_trace,
            negative_action,
            negative_test,
            negative_rhs,
            negative_rhs,
            lambda values: negative_operator @ values,
        )
        self.assertEqual(negative["coordinate_overlap_rank_diagnostic"], 0)
        self.assertEqual(negative["petrov_operator_rank"], 2)
        self.assertLess(negative["best_trial_endpoint_residual_relative"], 1.0e-12)

        rank_deficient_action = np.column_stack(
            (np.eye(4, dtype=np.complex128)[:, 0], np.zeros(4, dtype=np.complex128))
        )
        rank_deficient_rhs = rank_deficient_action @ np.array([[0.3], [0.0]])
        rank_deficient = solve_b1_reduced_petrov(
            np.eye(4, 2, dtype=np.complex128),
            np.eye(4, 2, dtype=np.complex128),
            rank_deficient_action,
            np.eye(4, 2, dtype=np.complex128),
            rank_deficient_rhs,
            rank_deficient_rhs,
            lambda values: rank_deficient_action @ values,
        )
        self.assertEqual(
            (
                rank_deficient["solve_status"],
                rank_deficient["trial_rank"],
                rank_deficient["petrov_operator_rank"],
                rank_deficient["petrov_operator_condition"],
                rank_deficient["petrov_operator_min_relative_singular_value"],
            ),
            ("petrov_operator_rank_deficient", 2, 1, None, 0.0),
        )
        self.assertLess(rank_deficient["best_trial_endpoint_residual_relative"], 1.0e-12)
        self.assertTrue(
            all(
                rank_deficient[key] is None
                for key in (
                    "petrov_stationarity_relative",
                    "endpoint_residual_relative",
                    "full_trace_residual_relative",
                    "lifted_trace",
                )
            )
        )

    @unittest.skipUnless(
        MPI.COMM_WORLD.size == 1,
        "Task036 frozen face-mass qualification is plain serial",
    )
    def test_frozen_p5_one_cell_face_mass_is_sparse_hpd(self) -> None:
        cfg = _one_cell_config(_authority_config())
        with tempfile.TemporaryDirectory(prefix="task036-t0b-face-mass-") as tmp:
            mesh_data = build_airbox_mesh_3d(cfg, Path(tmp) / "mesh")
            V = _create_nedelec_space(mesh_data.mesh, cfg)
            floquet = build_double_floquet_mpc(V, mesh_data, cfg)
            volume_form, _ = _build_variational_forms(
                mesh_data.mesh,
                mesh_data,
                cfg,
                V,
                field_formulation="total_field_dtn_port",
            )
            condensed = build_unconstrained_assembly_time_condensation(
                fem.form(volume_form),
                V,
                mesh_data.cell_tags,
                mpc=floquet.mpc,
            )
            try:
                endpoints = identify_endpoint_active_rows(
                    V,
                    condensed,
                    left_facets=mesh_data.facet_tags.find(cfg.tags.z_min),
                    right_facets=mesh_data.facet_tags.find(cfg.tags.z_max),
                )
                self.assertEqual(len(endpoints.left_original), 1250)
                self.assertEqual(len(endpoints.right_original), 1250)
                self.assertEqual(len(endpoints.left_active), 1200)
                self.assertEqual(len(endpoints.right_active), 1200)
                actions = build_endpoint_trace_mass_actions(
                    V,
                    mesh_data,
                    condensed.trace_constraints,
                    (
                        EndpointTraceMassSelection(
                            cfg.tags.z_min,
                            endpoints.left_original,
                            endpoints.left_active,
                        ),
                        EndpointTraceMassSelection(
                            cfg.tags.z_max,
                            endpoints.right_original,
                            endpoints.right_active,
                        ),
                    ),
                )
                try:
                    for action in actions:
                        self.assertEqual(action.shape, (1200, 1200))
                        self.assertLessEqual(action.hermitian_relative_defect, 1.0e-12)
                        self.assertLessEqual(
                            action.constraint_action_relative_error, 1.0e-12
                        )
                        self.assertLessEqual(action.solve_relative_residual, 1.0e-11)
                finally:
                    for action in actions:
                        action.destroy()
            finally:
                condensed.destroy()


if __name__ == "__main__":
    unittest.main()
