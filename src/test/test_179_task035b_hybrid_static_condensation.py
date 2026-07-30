from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
import unittest

import numpy as np
from dolfinx import fem
from mpi4py import MPI
from petsc4py import PETSc

from src.common.config_3d import (
    ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
    target_stage4_config,
)
from src.coupling.hybrid_internal_modes import (
    build_hybrid_internal_mode_coupling,
)
from src.modes.cross_section_spaces import (
    build_cross_section_spaces,
    build_matching_cross_section,
)
from src.solvers.hybrid_fem_modal_augmented_direct import (
    build_hybrid_augmented_direct_system,
    evaluate_hybrid_augmented_solution,
    evaluate_hybrid_recovered_direct_projection_audit,
    solve_hybrid_augmented_direct,
)
from src.solvers.hybrid_fem_modal_schur_direct import (
    build_hybrid_modal_schur_memory_minimal_system,
    solve_hybrid_modal_schur_direct,
)
from src.solvers.hybrid_local_dtn import (
    assemble_hybrid_local_dtn_system,
)
from src.postprocessing.hybrid_field_reconstruction import (
    assign_local_total_electric_field,
)


def _synthetic_mode(
    spaces,
    cfg,
    *,
    component: int,
    beta: complex,
    direction: str,
    owned_vectors: list[PETSc.Vec],
):
    trace = fem.Function(spaces.transverse)

    def field(x):
        phase = np.exp(1j * (cfg.kx * x[0] + cfg.ky * x[1]))
        values = np.zeros((2, x.shape[1]), dtype=PETSc.ScalarType)
        values[component, :] = phase
        return values

    trace.interpolate(field)
    trace.x.scatter_forward()
    mixed = fem.Function(spaces.mixed)
    mixed.x.array[:] = 0.0
    mixed.x.array[spaces.transverse_to_mixed] = trace.x.array
    mixed.x.scatter_forward()
    vector = mixed.x.petsc_vec.duplicate()
    mixed.x.petsc_vec.copy(vector)
    owned_vectors.append(vector)
    return SimpleNamespace(
        beta=complex(beta),
        right=SimpleNamespace(right_full=vector),
        left_full=vector,
        direction=direction,
        passive_branch_valid=True,
    )


class Task035bHybridStaticCondensationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        h_nm = 20.0 if MPI.COMM_WORLD.size >= 8 else 100.0
        base = replace(
            target_stage4_config(degree=2, h_nm=h_nm),
            matrix_diagnostics_assemble_only=False,
            matrix_diagnostics_factorization_only=False,
        )
        cls.standard_cfg = base
        cls.static_cfg = replace(
            base,
            stage4_full3d_assembly_backend=(
                ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND
            ),
        )
        cls.cross_section = build_matching_cross_section(base, "stage4_xy")
        cls.spaces = build_cross_section_spaces(
            cls.cross_section,
            transverse_degree=2,
        )
        target = np.sqrt(
            (base.k0 * complex(base.n_air)) ** 2
            - base.kx**2
            - base.ky**2
            + 0.0j
        )
        cls.mode_vectors: list[PETSc.Vec] = []
        cls.positive = SimpleNamespace(
            modes=[
                _synthetic_mode(
                    cls.spaces,
                    base,
                    component=component,
                    beta=target,
                    direction="forward",
                    owned_vectors=cls.mode_vectors,
                )
                for component in (0, 1)
            ]
        )
        cls.negative = SimpleNamespace(
            modes=[
                _synthetic_mode(
                    cls.spaces,
                    base,
                    component=component,
                    beta=-target,
                    direction="backward",
                    owned_vectors=cls.mode_vectors,
                )
                for component in (0, 1)
            ]
        )
        cls.standard_systems = tuple(
            assemble_hybrid_local_dtn_system(base, side)
            for side in ("bottom", "top")
        )
        cls.static_systems = tuple(
            assemble_hybrid_local_dtn_system(cls.static_cfg, side)
            for side in ("bottom", "top")
        )
        cls.standard_coupling = build_hybrid_internal_mode_coupling(
            base,
            cls.spaces,
            cls.positive,
            cls.negative,
            *cls.standard_systems,
            propagation_model="full3d_uniform_cg",
            modal_traction_model="scalar_cg_discrete_derivative",
        )
        cls.static_coupling = build_hybrid_internal_mode_coupling(
            cls.static_cfg,
            cls.spaces,
            cls.positive,
            cls.negative,
            *cls.static_systems,
            propagation_model="full3d_uniform_cg",
            modal_traction_model="scalar_cg_discrete_derivative",
        )
        cls.standard_augmented = build_hybrid_augmented_direct_system(
            *cls.standard_systems,
            cls.standard_coupling,
        )
        cls.static_augmented = build_hybrid_augmented_direct_system(
            *cls.static_systems,
            cls.static_coupling,
        )
        cls.standard_solution = solve_hybrid_augmented_direct(
            cls.standard_augmented,
            *cls.standard_systems,
        )
        cls.static_solution = solve_hybrid_augmented_direct(
            cls.static_augmented,
            *cls.static_systems,
            cls.static_coupling,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.standard_solution.destroy()
        cls.static_solution.destroy()
        cls.standard_augmented.destroy()
        cls.static_augmented.destroy()
        cls.standard_coupling.destroy()
        cls.static_coupling.destroy()
        for system in (*cls.standard_systems, *cls.static_systems):
            system.destroy()
        for vector in cls.mode_vectors:
            vector.destroy()

    def test_local_rows_are_physically_reduced(self) -> None:
        for standard, static in zip(
            self.standard_systems,
            self.static_systems,
            strict=True,
        ):
            self.assertEqual(
                static.assembly_backend_actual,
                ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
            )
            self.assertIsNotNone(static.static_condensation)
            self.assertEqual(static.full_fe_rows, standard.n_fe)
            self.assertLess(static.n_fe, standard.n_fe)
            self.assertEqual(
                static.A.getSize()[0],
                static.n_fe + static.n_external_aux,
            )
            self.assertEqual(
                static.static_condensation.metadata.local_algebra_rows,
                static.global_size,
            )
            self.assertFalse(
                static.static_condensation.metadata.full_global_matrix_allocated
            )
            self.assertEqual(
                static.augmented_matrix_stats["matrix_mallocs"],
                0.0,
            )

    def test_interface_blocks_close_after_two_sided_reduction(self) -> None:
        for block, system in (
            (self.static_coupling.bottom, self.static_systems[0]),
            (self.static_coupling.top, self.static_systems[1]),
        ):
            self.assertEqual(block.projection.getSize(), (2, system.global_size))
            self.assertEqual(
                block.positive_traction.getSize(),
                (system.global_size, 2),
            )
            self.assertEqual(
                block.negative_traction.getSize(),
                (system.global_size, 2),
            )
            self.assertEqual(block.positive_interior_correction.shape, (2, 2))
            self.assertEqual(block.negative_interior_correction.shape, (2, 2))
            self.assertEqual(block.modal_rhs_correction.shape, (2,))
            self.assertTrue(
                block.tangential_surface_trace_only_verified
            )
            self.assertFalse(
                block.interior_modal_pairwise_schur_evaluated
            )
            self.assertEqual(
                float(np.linalg.norm(block.positive_interior_correction)),
                0.0,
            )
            self.assertEqual(
                float(np.linalg.norm(block.negative_interior_correction)),
                0.0,
            )
            self.assertEqual(
                float(np.linalg.norm(block.modal_rhs_correction)),
                0.0,
            )
            self.assertFalse(block.full_surface_mode_vectors_retained)
            self.assertLess(block.positive_projection_identity_error, 1.0e-9)
            self.assertLessEqual(
                block.canonical_trace_raw_consistency_error,
                1.0e-12,
            )
            self.assertLessEqual(
                block.canonical_trace_representation_error,
                1.0e-12,
            )
            self.assertEqual(len(block.surface_reduction_audits), 6)
            for audit in block.surface_reduction_audits:
                self.assertTrue(audit["pass"])
                self.assertEqual(
                    audit["coefficient_degree"],
                    self.static_cfg.nedelec_degree,
                )
                self.assertEqual(audit["slave_absolute_cutoff"], 0.0)
                self.assertEqual(audit["max_slave"], 0.0)
                self.assertLessEqual(
                    audit["max_cell_interior"],
                    audit["cell_interior_cutoff"],
                )

    def test_static_augmented_matches_standard_observables(self) -> None:
        standard = evaluate_hybrid_augmented_solution(
            self.standard_cfg,
            *self.standard_systems,
            self.standard_coupling,
            self.standard_solution,
        )
        static = evaluate_hybrid_augmented_solution(
            self.static_cfg,
            *self.static_systems,
            self.static_coupling,
            self.static_solution,
        )
        modal_scale = max(
            float(np.linalg.norm(self.standard_solution.modal_amplitudes)),
            1.0e-30,
        )
        self.assertLess(
            float(
                np.linalg.norm(
                    self.static_solution.modal_amplitudes
                    - self.standard_solution.modal_amplitudes
                )
                / modal_scale
            ),
            1.0e-10,
        )
        for key in ("R_total", "T_total", "A_balance"):
            self.assertAlmostEqual(
                static["port_power"][key],
                standard["port_power"][key],
                places=10,
            )
        self.assertLess(
            static["interface_e_projection"]["combined_relative_residual"],
            1.0e-10,
        )
        self.assertLess(
            static["fe_modal_traction_equilibrium"][
                "bottom_relative_residual"
            ],
            1.0e-10,
        )
        self.assertLess(
            static["fe_modal_traction_equilibrium"]["top_relative_residual"],
            1.0e-10,
        )
        self.assertLess(self.static_solution.relative_residual, 1.0e-10)
        self.assertLess(self.standard_solution.relative_residual, 1.0e-10)

    def test_streaming_recovery_audits_every_eliminated_equation(self) -> None:
        for recovered, system in (
            (self.static_solution.bottom_recovered, self.static_systems[0]),
            (self.static_solution.top_recovered, self.static_systems[1]),
        ):
            self.assertIsNotNone(recovered)
            self.assertIs(
                recovered.electric_field.function_space.mesh,
                system.V.mesh,
            )
            self.assertLess(
                recovered.full_operator_residual[
                    "linear_system_relative_residual"
                ],
                1.0e-9,
            )
            self.assertLess(
                recovered.full_operator_residual[
                    "eliminated_cell_interior_max_abs_residual"
                ],
                1.0e-9,
            )
            self.assertEqual(
                recovered.recovery_audit["recovered_interior_rows"],
                system.static_condensation.metadata.cell_interior_rows,
            )
            self.assertFalse(
                recovered.streaming_audit[
                    "full_surface_mode_matrix_retained"
                ]
            )
            self.assertFalse(
                recovered.streaming_audit["full_global_matrix_allocated"]
            )
            self.assertEqual(
                recovered.streaming_audit[
                    "internal_mode_surface_vectors_reassembled"
                ],
                4,
            )
            self.assertEqual(
                recovered.streaming_audit["traction_beta_source"],
                "coupling_selected_traction_beta_per_nm",
            )
            self.assertEqual(
                recovered.streaming_audit["positive_traction_beta_count"],
                2,
            )
            self.assertEqual(
                recovered.streaming_audit["negative_traction_beta_count"],
                2,
            )

        for standard_system, standard_solution, static_solution in (
            (
                self.standard_systems[0],
                self.standard_solution.bottom,
                self.static_solution.bottom_recovered,
            ),
            (
                self.standard_systems[1],
                self.standard_solution.top,
                self.static_solution.top_recovered,
            ),
        ):
            standard_field = assign_local_total_electric_field(
                standard_system,
                standard_solution,
            )
            self.assertIsNotNone(static_solution)
            difference = standard_field.x.petsc_vec.duplicate()
            try:
                static_solution.electric_field.x.petsc_vec.copy(difference)
                difference.axpy(
                    PETSc.ScalarType(-1.0),
                    standard_field.x.petsc_vec,
                )
                self.assertLess(
                    float(
                        difference.norm()
                        / max(standard_field.x.petsc_vec.norm(), 1.0e-30)
                    ),
                    1.0e-10,
                )
            finally:
                difference.destroy()

    def test_recovered_trace_direct_projection_audits_candidate_itself(
        self,
    ) -> None:
        cfg = replace(
            self.static_cfg,
            dtn_auxiliary_direct_projection_audit=True,
            dtn_auxiliary_direct_projection_tolerance=1.0e-10,
        )
        audit = evaluate_hybrid_recovered_direct_projection_audit(
            cfg,
            *self.static_systems,
            self.static_solution,
        )
        self.assertTrue(audit["requested"])
        self.assertEqual(audit["scope"], "hybrid_candidate")
        self.assertEqual(
            audit["audited_mode_count"],
            audit["expected_mode_count"],
        )
        self.assertEqual(
            set(audit["side_mode_count"]),
            {"bottom", "top"},
        )
        self.assertTrue(audit["pass"], audit)
        self.assertLessEqual(
            audit["max_absolute_outgoing_projection_difference"],
            1.0e-10,
        )

    def test_static_modal_schur_matches_static_augmented(self) -> None:
        schur = build_hybrid_modal_schur_memory_minimal_system(
            *self.static_systems,
            self.static_coupling,
        )
        solution = solve_hybrid_modal_schur_direct(
            schur,
            *self.static_systems,
            self.static_coupling,
        )
        try:
            scale = max(
                float(
                    np.linalg.norm(
                        self.static_solution.modal_amplitudes
                    )
                ),
                1.0e-30,
            )
            self.assertLess(
                float(
                    np.linalg.norm(
                        solution.modal_amplitudes
                        - self.static_solution.modal_amplitudes
                    )
                    / scale
                ),
                1.0e-10,
            )
            self.assertLess(solution.relative_residual, 1.0e-9)
            self.assertLess(solution.modal_relative_residual, 1.0e-9)
            self.assertIsNotNone(solution.bottom_recovered)
            self.assertIsNotNone(solution.top_recovered)
            self.assertEqual(
                schur.lifecycle_strategy,
                "memory_minimal_direct",
            )
            self.assertTrue(schur.recovery_refactor_required)
        finally:
            solution.destroy()
            schur.destroy()


if __name__ == "__main__":
    unittest.main()
