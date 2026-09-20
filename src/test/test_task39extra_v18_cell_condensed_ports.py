"""Independent U0 acceptance: real FFCx cells, complex MPC, two-sided ports."""

from types import SimpleNamespace

import dolfinx_mpc
import numpy as np
import pytest
import ufl
from basix.ufl import element
from dolfinx import fem, mesh
from mpi4py import MPI
from petsc4py import PETSc
from scipy.sparse import csr_matrix
from scipy.linalg import lu_solve

from src.solvers.hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
)
from src.solvers.hcurl_cell_static_condensation import owned_hcurl_cell_interior_dofs
from src.solvers import p4_cell_condensed_inverse as core
from src.solvers.fullspace_v17_p3_oracle import _MumpsFactor
from src.runners.physical_dual_cell_condensed_lowmem_v20 import (
    _v24_p4_prefix_diagnostic_payload,
)


class Factor:
    """Tiny qualified MUMPS fixture with one factor and no refinement."""

    def __init__(self, matrix):
        self.backend = _MumpsFactor(matrix)
        self.backend.set_icntl(35, 0)
        self.backend.set_icntl(10, 0)
        self.backend.symbolic(matrix)
        self.backend.numeric(matrix)
        self.calls = 0
        self.destroyed = False

    def solve_repeated(self, rhs, output):
        self.backend.solve_repeated(rhs, output)
        self.calls += 1

    def destroy(self):
        self.backend.destroy()
        self.destroyed = True


def test_real_petsc_hash_binds_shape_indices_and_complex_values():
    def matrix(columns, value=2 + 3j, index=1):
        result = PETSc.Mat().createAIJ([2, columns], nnz=1, comm=MPI.COMM_SELF)
        result.setValue(0, index, value)
        result.assemble()
        return result

    matrices = [matrix(3), matrix(3), matrix(4), matrix(3, value=2 + 4j), matrix(3, index=2)]
    try:
        hashes = [core.petsc_csr_content_identity(m)["csr_sha256"] for m in matrices]
        assert hashes[0] == hashes[1]
        assert all(hashes[0] != value for value in hashes[2:])
    finally:
        for item in matrices:
            item.destroy()


def test_legacy_retained_schur_inventory_is_not_zeroed_by_new_audit():
    from src.test.test_115_task035b_assembly_time_condensation import _two_cell_problem

    _domain, tags, space, form = _two_cell_problem(distinct_materials=False)
    condensed = build_unconstrained_assembly_time_condensation(
        form, space, tags, retain_local_schur_for_matrix_free=True,
    )
    try:
        actual = sum(a.nbytes for a in condensed.retained_local_schur_by_class.values())
        assert actual > 0
        assert condensed.build_audit["retained_local_schur_bytes_sum"] == actual
    finally:
        condensed.destroy()


def test_actual_adapter_complex_mpc_nonzero_interior_ports_and_new_rhs():
    domain = mesh.create_unit_cube(
        MPI.COMM_SELF, 2, 1, 1, cell_type=mesh.CellType.hexahedron
    )
    tags = mesh.meshtags(domain, 3, np.array([0, 1], np.int32), np.array([1, 2], np.int32))
    space = fem.functionspace(domain, element("N1curl", domain.basix_cell(), 2))
    u, v = ufl.TrialFunction(space), ufl.TestFunction(space)
    dx = ufl.Measure("dx", domain=domain, subdomain_data=tags)
    form = fem.form(sum(
        ufl.inner(ufl.curl(u), ufl.curl(v)) * dx(tag, metadata={"quadrature_degree": 4})
        + mass * ufl.inner(u, v) * dx(tag, metadata={"quadrature_degree": 6})
        for tag, mass in [(1, -2.5 + 0.2j), (2, -1.7 + 0.1j)]
    ))
    interiors = np.concatenate(owned_hcurl_cell_interior_dofs(space))
    n = space.dofmap.index_map.size_global
    trace = np.setdiff1d(np.arange(n), interiors)
    master, slave = int(trace[0]), int(trace[-1])
    mpc = dolfinx_mpc.MultiPointConstraint(space)
    mpc.add_constraint(
        space, np.array([slave], np.int32), np.array([master], np.int64),
        np.array([np.exp(0.43j)], np.complex128), np.array([0], np.int32),
        np.array([0, 1], np.int32),
    )
    mpc.finalize()
    full = dolfinx_mpc.assemble_matrix(form, mpc, bcs=[])
    full.assemble()
    condensed = build_unconstrained_assembly_time_condensation(
        form, space, tags, mpc=mpc, appended_global_rows=2,
        appended_support_owned_cell_groups=(np.array([0, 1], np.int32),),
        appended_support_group_by_row=(0, 0), defer_final_assembly=True,
        dense_appended_block=True,
        sum_duplicate_cell_integrals=True,
    )
    rng = np.random.default_rng(18039)
    B = 0.02 * (rng.normal(size=(n, 2)) + 1j * rng.normal(size=(n, 2)))
    D = 0.03 * (rng.normal(size=(2, n)) + 1j * rng.normal(size=(2, n)))
    B[slave, :] = 0
    D[:, slave] = 0
    H = np.diag([1.1 + 0.3j, 0.9 - 0.2j])
    entries = tuple(SimpleNamespace(
        coupling_rows=np.flatnonzero(B[:, j]).astype(PETSc.IntType),
        coupling_values=B[B[:, j] != 0, j].copy(),
        projection_rows=np.flatnonzero(D[j]).astype(PETSc.IntType),
        projection_values=D[j, D[j] != 0].copy(), normalization_h=H[j, j],
    ) for j in range(2))
    carrier = SimpleNamespace(entries=entries, global_rows=n, ownership_range=(0, n))
    inverse = factor = None
    volume_action = None
    vectors = []
    try:
        terms = core.assemble_condensed_ports(condensed, carrier)
        identity = core.petsc_csr_content_identity(condensed.matrix)
        # Audit the assembled reduction itself before involving a factor.
        indptr, indices, values = full.getValuesCSR()
        V = csr_matrix((values, indices, indptr), shape=(n, n)).toarray()
        augmented = np.block([[V, B], [-D, H]])
        retained = np.r_[condensed.trace_constraints.owned_active_original_dofs, n + np.arange(2)]
        expected_schur = augmented[np.ix_(retained, retained)] - augmented[np.ix_(retained, interiors)] @ np.linalg.solve(
            augmented[np.ix_(interiors, interiors)], augmented[np.ix_(interiors, retained)]
        )
        sp, sj, sa = condensed.matrix.getValuesCSR()
        actual_schur = csr_matrix((sa, sj, sp), shape=expected_schur.shape).toarray()
        local_inverse_defects = [float(np.linalg.norm(
            V[np.ix_(cell.interior_original_dofs, cell.interior_original_dofs)]
            @ lu_solve(condensed.interior_lu_by_class[cell.class_key], np.eye(len(cell.interior_original_dofs)))
            - np.eye(len(cell.interior_original_dofs))
        )) for cell in condensed.cell_recovery_maps]
        first, last = map(int, [form.ufcx_form.form_integral_offsets[0], form.ufcx_form.form_integral_offsets[1]])
        detail = dict(local_inverse_defects=local_inverse_defects, integral_ids=[int(form.ufcx_form.form_integral_ids[j]) for j in range(first, last)])
        delta = actual_schur - expected_schur
        nt = condensed.active_rows
        detail["block_difference_norms"] = {"S": float(np.linalg.norm(delta[:nt, :nt])), "Bhat": float(np.linalg.norm(delta[:nt, nt:])), "minus_Dhat": float(np.linalg.norm(delta[nt:, :nt])), "Hhat": float(np.linalg.norm(delta[nt:, nt:]))}
        assert np.linalg.norm(actual_schur - expected_schur) / np.linalg.norm(expected_schur) <= 1e-10, detail
        factor = Factor(condensed.matrix)
        inverse = core.P4CellCondensedInverse(
            condensed, factor, port_terms=terms, owns_factor=True, owns_condensed=True,
        )
        class _ReusableMatrixAction:
            def __init__(self, matrix):
                self.matrix = np.asarray(matrix, dtype=np.complex128)
                self.output = None
                self.calls = 0
                self.component_actions = {"volume": self}

            def apply(self, source):
                if self.output is None:
                    self.output = source.duplicate()
                self.output.array[:] = self.matrix @ source.array
                self.output.assemble()
                self.calls += 1
                return self.output

            def destroy(self):
                if self.output is not None:
                    self.output.destroy()
                    self.output = None

        class _TargetMatrixAction:
            def __init__(self, matrix):
                self.matrix = np.asarray(matrix, dtype=np.complex128)

            def apply(self, source, target):
                target.array[:] = self.matrix @ source.array
                target.assemble()

        volume_action = _ReusableMatrixAction(V)
        physical_action = _TargetMatrixAction(V + B @ np.linalg.solve(H, D))
        diagnostic_common = {
            "levels": {"spaces": {4: space}},
            "p4": {
                "volume_action": volume_action,
                "physical_action": physical_action,
                "dtn_action": SimpleNamespace(carrier=carrier),
            },
        }
        local_lu_identity = {key: (id(lu[0]), id(lu[1])) for key, lu in condensed.interior_lu_by_class.items()}
        # The sole dense full-system oracle is confined to this two-cell test.
        rhs1 = rng.normal(size=n) + 1j * rng.normal(size=n)
        rhs2 = rng.normal(size=n) + 1j * rng.normal(size=n)
        rhs1[slave] = rhs2[slave] = 0
        solutions = []
        for loop_index, values in enumerate([rhs1, rhs2, rhs1, rhs1 + 1j * rhs2, rhs2 - rhs1]):
            rhs = full.createVecRight()
            rhs.array[:] = values
            vectors.append(rhs)
            result = inverse.apply(rhs)
            vectors.append(result)
            solutions.append(result.array.copy())
            if loop_index == 0:
                diagnostic_facts = {
                    "g": values.copy(),
                    "correction": result.array.copy(),
                    "alpha": inverse.last_port_solution.copy(),
                    "logical_call_sequence": 3,
                    "pc_apply_sequence": 1,
                }
                factor_calls_before_diagnostic = factor.calls
                diagnostic = _v24_p4_prefix_diagnostic_payload(
                    diagnostic_common,
                    {"inverse": inverse},
                    diagnostic_facts,
                    phase="v18_fixture_first",
                )
                repeated_diagnostic = _v24_p4_prefix_diagnostic_payload(
                    diagnostic_common,
                    {"inverse": inverse},
                    diagnostic_facts,
                    phase="v18_fixture_repeat",
                )
                for packet in (diagnostic, repeated_diagnostic):
                    assert packet["augmented_residual_identity"]["passed"] is True
                    assert packet["internal_recovery"]["recovery_difference_norm"] <= 1.0e-10
                    assert packet["port_action_norms"]["FE_B_alpha_absolute_norm"] > 0.0
                    assert packet["diagnostic_runtime"]["global_mat_solve_count_delta"] == 0
                assert factor.calls == factor_calls_before_diagnostic
                assert volume_action.calls == 4
            expected = np.linalg.solve(augmented, np.r_[values, np.zeros(2)])
            np.testing.assert_array_equal(rhs.array, values)
            assert result.array[slave] == 0
            np.testing.assert_allclose(result.array, expected[:n], rtol=1e-10, atol=1e-11)
            np.testing.assert_allclose(inverse.last_port_solution, expected[n:], rtol=1e-10, atol=1e-11)
            r4 = values - V @ result.array - B @ np.linalg.solve(H, D @ result.array)
            assert np.linalg.norm(r4) / np.linalg.norm(values) <= 1e-10
            et = values - V @ result.array - B @ inverse.last_port_solution
            ep = D @ result.array - H @ inverse.last_port_solution
            scale = np.linalg.norm(values) + np.linalg.norm(V @ result.array) + np.linalg.norm(B @ inverse.last_port_solution)
            assert np.linalg.norm(r4 - (et - B @ np.linalg.solve(H, ep))) / scale <= 1e-10
        assert factor.calls == inverse.solve_count == 5
        np.testing.assert_allclose(solutions[0], solutions[2], rtol=1e-12, atol=1e-12)
        np.testing.assert_allclose(solutions[3], solutions[0] + 1j * solutions[1], rtol=1e-10, atol=1e-11)
        np.testing.assert_allclose(solutions[4], solutions[1] - solutions[0], rtol=1e-10, atol=1e-11)
        assert core.petsc_csr_content_identity(condensed.matrix) == identity
        assert {key: (id(lu[0]), id(lu[1])) for key, lu in condensed.interior_lu_by_class.items()} == local_lu_identity
        zero = full.createVecRight()
        zero.set(0)
        vectors.append(zero)
        zero_result = inverse.apply(zero)
        vectors.append(zero_result)
        assert zero_result.norm() == 0 and factor.calls == 5
        failed_vectors = []

        def fail_solve(rhs, output):
            failed_vectors.extend([rhs, output])
            raise RuntimeError("injected backend failure")

        factor.solve_repeated = fail_solve
        with pytest.raises(RuntimeError, match="injected backend failure"):
            inverse.apply(vectors[0])
        assert len(failed_vectors) == 2
        assert all(value.handle == 0 for value in failed_vectors)
        inverse.destroy()
        inverse.destroy()
        assert factor.destroyed
        assert not condensed.interior_lu_by_class
        assert not condensed.interior_from_trace_by_class
        assert not condensed.trace_from_interior_rhs_by_class
        assert not condensed.cell_recovery_maps
        with pytest.raises(RuntimeError, match="destroyed"):
            inverse.apply(zero)
    finally:
        for vector in vectors:
            vector.destroy()
        if volume_action is not None:
            volume_action.destroy()
        if inverse is not None:
            inverse.destroy()
        elif factor is not None:
            factor.destroy()
        condensed.destroy()
        full.destroy()
