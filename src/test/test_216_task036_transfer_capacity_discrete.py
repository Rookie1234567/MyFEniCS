from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from dolfinx import fem
from dolfinx.fem import petsc as fem_petsc
from mpi4py import MPI
import numpy as np
from petsc4py import PETSc
import ufl

from benchmarks.run_task036_one_cell_discrete_bloch import (
    _authority_config,
    _one_cell_config,
)
from benchmarks.task036_transfer_capacity import joint_cauchy_pairing
from src.constraints.cross_section_floquet import reduce_matrix_hermitian
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.solvers.common_3d_forms import _build_variational_forms
from src.solvers.common_3d_solve import _create_nedelec_space
from src.solvers.hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
)
from src.solvers.one_cell_discrete_bloch import identify_endpoint_active_rows


def _endpoint_constraint_matrix(
    original_rows: np.ndarray,
    active_rows: np.ndarray,
    constraints,
    comm,
) -> PETSc.Mat:
    active_local = {int(active): index for index, active in enumerate(active_rows)}
    row_expansions = [
        constraints.expansion_by_original[int(original)] for original in original_rows
    ]
    transform = PETSc.Mat().createAIJ(
        size=(len(original_rows), len(active_rows)),
        nnz=max(len(active) for active, _coefficients in row_expansions),
        comm=comm,
    )
    for row, (active, coefficients) in enumerate(row_expansions):
        columns = np.asarray(
            [active_local[int(value)] for value in active],
            dtype=PETSc.IntType,
        )
        transform.setValues(
            np.asarray([row], dtype=PETSc.IntType),
            columns,
            np.asarray(coefficients, dtype=PETSc.ScalarType)[None, :],
        )
    transform.assemble()
    return transform


def _qualify_endpoint_mass(
    testcase: unittest.TestCase,
    V,
    mesh_data,
    tag: int,
    original_rows: np.ndarray,
    active_rows: np.ndarray,
    constraints,
    *,
    seed: int,
) -> None:
    trial = ufl.TrialFunction(V)
    test = ufl.TestFunction(V)
    normal = ufl.FacetNormal(mesh_data.mesh)
    ds = ufl.Measure(
        "ds",
        domain=mesh_data.mesh,
        subdomain_data=mesh_data.facet_tags,
        metadata={"quadrature_degree": 14},
    )
    full = fem_petsc.assemble_matrix(
        fem.form(
            ufl.inner(
                ufl.cross(normal, trial),
                ufl.cross(normal, test),
            )
            * ds(tag)
        ),
        bcs=[],
    )
    full.assemble()
    endpoint_is = PETSc.IS().createGeneral(
        np.asarray(original_rows, dtype=PETSc.IntType),
        comm=full.getComm(),
    )
    face_mass = full.createSubMatrix(endpoint_is, endpoint_is)
    transform = _endpoint_constraint_matrix(
        original_rows,
        active_rows,
        constraints,
        full.getComm(),
    )
    reduced_mass = reduce_matrix_hermitian(face_mass, transform)
    hermitian = PETSc.Mat()
    reduced_mass.hermitianTranspose(hermitian)
    difference = reduced_mass.copy()
    difference.axpy(
        PETSc.ScalarType(-1.0),
        hermitian,
        structure=PETSc.Mat.Structure.DIFFERENT_NONZERO_PATTERN,
    )
    rng = np.random.default_rng(seed)
    probe = reduced_mass.createVecRight()
    probe.getArray()[:] = rng.standard_normal(
        len(active_rows)
    ) + 1j * rng.standard_normal(len(active_rows))
    probe.assemble()
    direct_action = reduced_mass.createVecLeft()
    expanded = transform.createVecLeft()
    face_action = face_mass.createVecLeft()
    chained_action = transform.createVecRight()
    action_error = reduced_mass.createVecLeft()
    reduced_mass.mult(probe, direct_action)
    transform.mult(probe, expanded)
    face_mass.mult(expanded, face_action)
    transform.multHermitian(face_action, chained_action)
    direct_action.copy(action_error)
    action_error.axpy(PETSc.ScalarType(-1.0), chained_action)
    right_hand_side = direct_action.copy()
    solution = reduced_mass.createVecRight()
    residual = reduced_mass.createVecLeft()
    solver = PETSc.KSP().create(reduced_mass.getComm())
    options_prefix = "task036_face_mass_"
    options = PETSc.Options(options_prefix)
    options["mat_cholmod_final_asis"] = False
    options["mat_cholmod_final_ll"] = True
    try:
        for matrix in (face_mass, transform, reduced_mass):
            testcase.assertIn("aij", matrix.getType().lower())
        testcase.assertEqual(face_mass.getSize(), (1250, 1250))
        testcase.assertEqual(transform.getSize(), (1250, 1200))
        testcase.assertEqual(reduced_mass.getSize(), (1200, 1200))
        testcase.assertLessEqual(
            difference.norm() / max(reduced_mass.norm(), 1.0e-30),
            1.0e-12,
        )
        testcase.assertLessEqual(
            action_error.norm() / max(direct_action.norm(), 1.0e-30),
            1.0e-12,
        )
        reduced_mass.setOption(PETSc.Mat.Option.HERMITIAN, True)
        solver.setOptionsPrefix(options_prefix)
        solver.setType(PETSc.KSP.Type.PREONLY)
        solver.getPC().setType(PETSc.PC.Type.CHOLESKY)
        solver.getPC().setFactorSolverType("cholmod")
        solver.setOperators(reduced_mass)
        solver.setErrorIfNotConverged(True)
        solver.setFromOptions()
        solver.setUp()
        solver.solve(right_hand_side, solution)
        testcase.assertGreater(solver.getConvergedReason(), 0)
        reduced_mass.mult(solution, residual)
        residual.axpy(PETSc.ScalarType(-1.0), right_hand_side)
        testcase.assertLessEqual(
            residual.norm() / max(right_hand_side.norm(), 1.0e-30),
            1.0e-11,
        )
    finally:
        solver.destroy()
        options.delValue("mat_cholmod_final_asis")
        options.delValue("mat_cholmod_final_ll")
        residual.destroy()
        solution.destroy()
        right_hand_side.destroy()
        action_error.destroy()
        chained_action.destroy()
        face_action.destroy()
        expanded.destroy()
        direct_action.destroy()
        probe.destroy()
        difference.destroy()
        hermitian.destroy()
        reduced_mass.destroy()
        transform.destroy()
        face_mass.destroy()
        endpoint_is.destroy()
        full.destroy()


class Task036TransferCapacityDiscreteTests(unittest.TestCase):
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
                _qualify_endpoint_mass(
                    self,
                    V,
                    mesh_data,
                    cfg.tags.z_min,
                    endpoints.left_original,
                    endpoints.left_active,
                    condensed.trace_constraints,
                    seed=36062,
                )
                _qualify_endpoint_mass(
                    self,
                    V,
                    mesh_data,
                    cfg.tags.z_max,
                    endpoints.right_original,
                    endpoints.right_active,
                    condensed.trace_constraints,
                    seed=36063,
                )
            finally:
                condensed.destroy()


if __name__ == "__main__":
    unittest.main()
