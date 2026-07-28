from __future__ import annotations

import unittest
from types import SimpleNamespace

import numpy as np
from dolfinx import fem
from mpi4py import MPI
from petsc4py import PETSc

from src.common.config_3d import target_stage4_config
from src.coupling.hybrid_internal_modes import build_hybrid_internal_mode_coupling
from src.modes.cross_section_spaces import (
    build_cross_section_spaces,
    build_matching_cross_section,
)
from src.postprocessing.hybrid_field_reconstruction import (
    ModalFieldReconstructor,
    assembled_interface_field_continuity,
    interface_field_continuity,
)
from src.solvers.hybrid_fem_modal_augmented_direct import (
    build_hybrid_augmented_direct_system,
    evaluate_hybrid_augmented_solution,
    internal_modal_constraint_matrix,
    solve_hybrid_augmented_direct,
)
from src.solvers.hybrid_fem_modal_schur_direct import (
    build_hybrid_modal_schur_direct_system,
    build_hybrid_modal_schur_memory_minimal_system,
    solve_hybrid_modal_schur_direct,
)
from src.solvers.hybrid_local_dtn import assemble_hybrid_local_dtn_system


def _modal_vector(matrix: PETSc.Mat, values: np.ndarray) -> PETSc.Vec:
    vector = matrix.createVecRight()
    vector.set(0.0)
    first, last = vector.getOwnershipRange()
    if last > first:
        vector.setValues(
            np.arange(first, last, dtype=PETSc.IntType),
            np.asarray(values[first:last], dtype=PETSc.ScalarType),
        )
    vector.assemble()
    return vector


def _relative_vector_error(actual: PETSc.Vec, expected: PETSc.Vec) -> float:
    difference = actual.duplicate()
    try:
        actual.copy(difference)
        difference.axpy(PETSc.ScalarType(-1.0), expected)
        return float(difference.norm() / max(expected.norm(), 1.0e-30))
    finally:
        difference.destroy()


class Task032HybridAugmentedDirectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        def progress(message: str) -> None:
            if MPI.COMM_WORLD.rank == 0:
                print(message, flush=True)

        cls.cfg = target_stage4_config(degree=2, h_nm=10.0)
        cross_section = build_matching_cross_section(cls.cfg, "stage4_xy")
        cls.cross_section = cross_section
        cls.spaces = build_cross_section_spaces(
            cross_section, transverse_degree=2
        )
        target = np.sqrt(
            (cls.cfg.k0 * complex(cls.cfg.n_air)) ** 2
            - cls.cfg.kx**2
            - cls.cfg.ky**2
            + 0.0j
        )
        cls.mode_vectors = []

        def synthetic_mode(component: int, beta: complex, direction: str):
            trace = fem.Function(cls.spaces.transverse)

            def field(x):
                phase = np.exp(
                    1j * (cls.cfg.kx * x[0] + cls.cfg.ky * x[1])
                )
                values = np.zeros((2, x.shape[1]), dtype=PETSc.ScalarType)
                values[component, :] = phase
                return values

            trace.interpolate(field)
            trace.x.scatter_forward()
            mixed = fem.Function(cls.spaces.mixed)
            mixed.x.array[:] = 0.0
            mixed.x.array[cls.spaces.transverse_to_mixed] = trace.x.array
            mixed.x.scatter_forward()
            mixed_vector = mixed.x.petsc_vec
            vector = mixed_vector.duplicate()
            mixed_vector.copy(vector)
            cls.mode_vectors.append(vector)
            return SimpleNamespace(
                beta=complex(beta),
                right=SimpleNamespace(right_full=vector),
                left_full=vector,
                direction=direction,
                passive_branch_valid=True,
            )

        cls.positive = SimpleNamespace(
            modes=[
                synthetic_mode(0, target, "forward"),
                synthetic_mode(1, target, "forward"),
            ]
        )
        cls.negative = SimpleNamespace(
            modes=[
                synthetic_mode(0, -target, "backward"),
                synthetic_mode(1, -target, "backward"),
            ]
        )
        cls.bottom_system = assemble_hybrid_local_dtn_system(
            cls.cfg, "bottom"
        )
        cls.top_system = assemble_hybrid_local_dtn_system(cls.cfg, "top")
        cls.coupling = build_hybrid_internal_mode_coupling(
            cls.cfg,
            cls.spaces,
            cls.positive,
            cls.negative,
            cls.bottom_system,
            cls.top_system,
        )
        progress("Task32 test39: internal coupling complete")
        cls.system = build_hybrid_augmented_direct_system(
            cls.bottom_system,
            cls.top_system,
            cls.coupling,
        )
        cls.solution = None
        progress("Task32 test39: monolithic augmented matrix complete")

    @classmethod
    def tearDownClass(cls):
        if cls.solution is not None:
            cls.solution.destroy()
            cls.solution.destroy()
        cls.system.destroy()
        cls.system.destroy()
        cls.coupling.destroy()
        for system in (cls.bottom_system, cls.top_system):
            system.A.destroy()
            system.b.destroy()
        for vector in cls.mode_vectors:
            vector.destroy()

    def test_rank_major_layout_and_modal_constraint(self):
        expected_size = (
            self.bottom_system.global_size
            + self.top_system.global_size
            + self.coupling.internal_unknown_count
        )
        self.assertEqual(self.system.A.getSize(), (expected_size, expected_size))
        self.assertEqual(self.system.b.getSize(), expected_size)
        self.assertEqual(
            sum(MPI.COMM_WORLD.allgather(self.system.layout.local_size)),
            expected_size,
        )
        np.testing.assert_allclose(
            self.system.modal_constraint,
            internal_modal_constraint_matrix(self.coupling),
            atol=0.0,
            rtol=0.0,
        )
        self.assertEqual(self.system.modal_constraint.shape, (4, 4))
        self.assertFalse(self.system.dense_interface_square_formed)
        self.assertGreater(self.system.matrix_stats["matrix_nnz_used"], 0)
        self.assertIn("aij", self.system.matrix_stats["matrix_type"])

    def test_solution_interface_and_external_port_metrics_are_finite(self):
        if type(self).solution is None:
            type(self).solution = solve_hybrid_augmented_direct(
                self.system,
                self.bottom_system,
                self.top_system,
            )
        metrics = evaluate_hybrid_augmented_solution(
            self.cfg,
            self.bottom_system,
            self.top_system,
            self.coupling,
            self.solution,
        )
        interface = metrics["interface_e_projection"]
        traction = metrics["fe_modal_traction_equilibrium"]
        power = metrics["port_power"]
        self.assertLess(interface["combined_relative_residual"], 1.0e-10)
        self.assertLess(traction["bottom_relative_residual"], 1.0e-10)
        self.assertLess(traction["top_relative_residual"], 1.0e-10)
        self.assertEqual(
            traction["interpretation"],
            "variational_FE_rows_with_modal_traction_not_pointwise_H_jump",
        )
        for key in ("R_total", "T_total", "A_balance", "R_plus_T"):
            self.assertTrue(np.isfinite(power[key]))
        self.assertEqual(
            metrics["external_auxiliary_amplitudes"]["bottom"].shape,
            (self.bottom_system.n_external_aux,),
        )
        self.assertEqual(
            metrics["external_auxiliary_amplitudes"]["top"].shape,
            (self.top_system.n_external_aux,),
        )

    def test_rhs_pack_and_modal_only_action_match_explicit_blocks(self):
        bottom_rhs, top_rhs, modal_rhs = self.system.layout.split(
            self.system.b,
            self.bottom_system.b,
            self.top_system.b,
        )
        try:
            self.assertLess(
                _relative_vector_error(bottom_rhs, self.bottom_system.b),
                1.0e-15,
            )
            self.assertLess(
                _relative_vector_error(top_rhs, self.top_system.b),
                1.0e-15,
            )
            np.testing.assert_array_equal(modal_rhs, np.zeros(4))
        finally:
            bottom_rhs.destroy()
            top_rhs.destroy()

        modal = np.asarray(
            (0.25 + 0.1j, -0.35 + 0.2j, 0.15 - 0.05j, 0.4 + 0.3j),
            dtype=np.complex128,
        )
        zero_bottom = self.bottom_system.b.duplicate()
        zero_top = self.top_system.b.duplicate()
        zero_bottom.set(0.0)
        zero_top.set(0.0)
        source = self.system.layout.pack(zero_bottom, zero_top, modal)
        target = self.system.A.createVecLeft()
        self.system.A.mult(source, target)
        actual_bottom, actual_top, actual_modal = self.system.layout.split(
            target,
            self.bottom_system.b,
            self.top_system.b,
        )
        mode_count = self.coupling.mode_count_per_direction
        bottom_positive = _modal_vector(
            self.coupling.bottom.positive_traction, modal[:mode_count]
        )
        bottom_negative = _modal_vector(
            self.coupling.bottom.negative_traction,
            np.asarray(self.coupling.propagation.backward.factors)
            * modal[mode_count:],
        )
        top_positive = _modal_vector(
            self.coupling.top.positive_traction,
            np.asarray(self.coupling.propagation.forward.factors)
            * modal[:mode_count],
        )
        top_negative = _modal_vector(
            self.coupling.top.negative_traction, modal[mode_count:]
        )
        expected_bottom = self.coupling.bottom.positive_traction.createVecLeft()
        expected_top = self.coupling.top.positive_traction.createVecLeft()
        temporary_bottom = expected_bottom.duplicate()
        temporary_top = expected_top.duplicate()
        try:
            self.coupling.bottom.positive_traction.mult(
                bottom_positive, expected_bottom
            )
            self.coupling.bottom.negative_traction.mult(
                bottom_negative, temporary_bottom
            )
            expected_bottom.axpy(PETSc.ScalarType(1.0), temporary_bottom)
            self.coupling.top.positive_traction.mult(top_positive, expected_top)
            self.coupling.top.negative_traction.mult(
                top_negative, temporary_top
            )
            expected_top.axpy(PETSc.ScalarType(1.0), temporary_top)
            self.assertLess(
                _relative_vector_error(actual_bottom, expected_bottom),
                1.0e-13,
            )
            self.assertLess(
                _relative_vector_error(actual_top, expected_top),
                1.0e-13,
            )
            np.testing.assert_allclose(
                actual_modal,
                self.system.modal_constraint @ modal,
                atol=1.0e-13,
                rtol=1.0e-13,
            )
        finally:
            temporary_bottom.destroy()
            temporary_top.destroy()
            expected_bottom.destroy()
            expected_top.destroy()
            for vector in (
                bottom_positive,
                bottom_negative,
                top_positive,
                top_negative,
                actual_bottom,
                actual_top,
                source,
                target,
                zero_bottom,
                zero_top,
            ):
                vector.destroy()

    def test_mumps_direct_solve_has_small_true_residual(self):
        type(self).solution = solve_hybrid_augmented_direct(
            self.system,
            self.bottom_system,
            self.top_system,
        )
        solution = self.solution
        if MPI.COMM_WORLD.rank == 0:
            print(
                "Task32 test39 metrics: "
                f"size={self.system.A.getSize()[0]} "
                f"nnz={self.system.matrix_stats['matrix_nnz_used']:.0f} "
                f"relative_residual={solution.relative_residual:.6e} "
                f"setup_seconds={solution.setup_seconds:.6f} "
                f"solve_seconds={solution.solve_seconds:.6f}",
                flush=True,
            )
        self.assertGreater(solution.converged_reason, 0)
        self.assertLess(solution.relative_residual, 1.0e-10)
        self.assertEqual(solution.modal_amplitudes.shape, (4,))
        self.assertTrue(np.all(np.isfinite(solution.modal_amplitudes)))
        self.assertGreaterEqual(solution.setup_seconds, 0.0)
        self.assertGreaterEqual(solution.solve_seconds, 0.0)

    def test_modal_schur_multi_rhs_matches_augmented_solution(self):
        if type(self).solution is None:
            type(self).solution = solve_hybrid_augmented_direct(
                self.system,
                self.bottom_system,
                self.top_system,
            )
        schur_system = build_hybrid_modal_schur_direct_system(
            self.bottom_system,
            self.top_system,
            self.coupling,
        )
        schur_solution = None
        try:
            schur_solution = solve_hybrid_modal_schur_direct(
                schur_system,
                self.bottom_system,
                self.top_system,
                self.coupling,
            )
            self.assertEqual(schur_system.modal_schur.shape, (4, 4))
            self.assertEqual(schur_system.multi_rhs_count, 5)
            self.assertFalse(schur_system.dense_interface_square_formed)
            self.assertFalse(schur_system.full_field_or_mode_gathered)
            self.assertTrue(np.isfinite(schur_system.modal_schur_condition))
            for inventory in schur_system.factor_inventory.values():
                self.assertEqual(
                    inventory["mumps_icntl_14_requested_percent"], 100
                )
                self.assertEqual(
                    inventory["mumps_icntl_14_observed_percent"], 100
                )
                self.assertTrue(inventory["mumps_workspace_relaxation_verified"])
            self.assertLess(schur_solution.relative_residual, 1.0e-9)
            self.assertLess(schur_solution.bottom_relative_residual, 1.0e-10)
            self.assertLess(schur_solution.top_relative_residual, 1.0e-10)
            self.assertLess(schur_solution.modal_relative_residual, 1.0e-10)
            np.testing.assert_allclose(
                schur_solution.modal_amplitudes,
                self.solution.modal_amplitudes,
                atol=1.0e-10,
                rtol=1.0e-10,
            )
            self.assertLess(
                _relative_vector_error(schur_solution.bottom, self.solution.bottom),
                1.0e-10,
            )
            self.assertLess(
                _relative_vector_error(schur_solution.top, self.solution.top),
                1.0e-10,
            )
            augmented_metrics = evaluate_hybrid_augmented_solution(
                self.cfg,
                self.bottom_system,
                self.top_system,
                self.coupling,
                self.solution,
            )
            schur_metrics = evaluate_hybrid_augmented_solution(
                self.cfg,
                self.bottom_system,
                self.top_system,
                self.coupling,
                schur_solution,
            )
            for key in ("R_total", "T_total", "A_balance"):
                self.assertAlmostEqual(
                    schur_metrics["port_power"][key],
                    augmented_metrics["port_power"][key],
                    places=11,
                )
        finally:
            if schur_solution is not None:
                schur_solution.destroy()
                schur_solution.destroy()
            schur_system.destroy()
            schur_system.destroy()

    def test_memory_minimal_modal_schur_releases_and_refactors_local_factors(self):
        if type(self).solution is None:
            type(self).solution = solve_hybrid_augmented_direct(
                self.system,
                self.bottom_system,
                self.top_system,
            )
        schur_system = build_hybrid_modal_schur_memory_minimal_system(
            self.bottom_system,
            self.top_system,
            self.coupling,
        )
        schur_solution = None
        try:
            self.assertEqual(schur_system.lifecycle_strategy, "memory_minimal_direct")
            self.assertTrue(schur_system.recovery_refactor_required)
            self.assertIsNone(schur_system.bottom_factor)
            self.assertIsNone(schur_system.top_factor)
            for inventory in schur_system.factor_inventory.values():
                self.assertEqual(
                    inventory["mumps_icntl_14_requested_percent"], 100
                )
                self.assertEqual(
                    inventory["mumps_icntl_14_observed_percent"], 100
                )
                self.assertTrue(inventory["mumps_workspace_relaxation_verified"])
            schur_solution = solve_hybrid_modal_schur_direct(
                schur_system,
                self.bottom_system,
                self.top_system,
                self.coupling,
            )
            self.assertEqual(
                set(schur_solution.recovery_factor_setup_seconds),
                {"bottom", "top"},
            )
            self.assertLess(schur_solution.relative_residual, 1.0e-9)
            np.testing.assert_allclose(
                schur_solution.modal_amplitudes,
                self.solution.modal_amplitudes,
                atol=1.0e-10,
                rtol=1.0e-10,
            )
            self.assertLess(
                _relative_vector_error(schur_solution.bottom, self.solution.bottom),
                1.0e-10,
            )
            self.assertLess(
                _relative_vector_error(schur_solution.top, self.solution.top),
                1.0e-10,
            )
        finally:
            if schur_solution is not None:
                schur_solution.destroy()
                schur_solution.destroy()
            schur_system.destroy()
            schur_system.destroy()

    def test_selected_middle_field_reconstruction_is_bounded_and_finite(self):
        if type(self).solution is None:
            type(self).solution = solve_hybrid_augmented_direct(
                self.system,
                self.bottom_system,
                self.top_system,
            )
        reconstructor = ModalFieldReconstructor(
            self.cfg,
            self.cross_section,
            self.spaces,
            self.positive,
            self.negative,
        )
        x_values = np.asarray([0.25, 0.75]) * self.cfg.period_x
        y_values = np.asarray([0.25, 0.75]) * self.cfg.period_y
        samples = reconstructor.selected_planes(
            self.solution.modal_amplitudes,
            x_values,
            y_values,
            [10.0, 60.0, 110.0],
        )
        self.assertEqual(samples.electric_V_per_m.shape, (3, 2, 2, 3))
        self.assertEqual(samples.magnetic_A_per_m.shape, (3, 2, 2, 3))
        self.assertTrue(np.all(np.isfinite(samples.electric_V_per_m)))
        self.assertTrue(np.all(np.isfinite(samples.magnetic_A_per_m)))
        self.assertEqual(samples.electric_V_per_m.nbytes, 576)
        self.assertEqual(samples.magnetic_A_per_m.nbytes, 576)
        interfaces = reconstructor.selected_planes(
            self.solution.modal_amplitudes,
            x_values,
            y_values,
            [10.0, 110.0],
        )
        continuity = interface_field_continuity(
            self.cfg,
            self.bottom_system,
            self.top_system,
            self.solution.bottom,
            self.solution.top,
            interfaces,
        )
        assembled = assembled_interface_field_continuity(
            self.cfg,
            self.bottom_system,
            self.top_system,
            self.solution.bottom_physical,
            self.solution.top_physical,
            self.coupling,
            self.solution.modal_amplitudes,
        )
        for side in ("bottom", "top"):
            for field in ("electric_tangential", "magnetic_tangential"):
                self.assertTrue(
                    np.isfinite(continuity[side][field]["relative_l2"])
                )
            for field in ("electric_tangential", "traction_density_l2_proxy"):
                self.assertTrue(
                    np.isfinite(assembled[side][field]["relative_l2"])
                )
        absorption = reconstructor.absorbed_power_code_units(
            self.solution.modal_amplitudes
        )
        self.assertGreaterEqual(absorption["absorbed_power_code_units"], 0.0)
        self.assertGreater(absorption["z_evaluation_count"], 0)
        self.assertTrue(
            np.isfinite(absorption["poynting_flux_loss_code_units"])
        )


if __name__ == "__main__":
    unittest.main()
