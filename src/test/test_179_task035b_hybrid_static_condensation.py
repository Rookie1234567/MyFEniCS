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
from src.geometry.tetra_mesh_audit import mesh_coordinate_tolerance
from src.modes.cross_section_spaces import (
    build_cross_section_spaces,
    build_matching_cross_section,
)
from src.solvers.hybrid_fem_modal_augmented_direct import (
    build_hybrid_augmented_direct_system,
    evaluate_hybrid_augmented_solution,
    solve_hybrid_augmented_direct,
)
from src.solvers.hybrid_fem_modal_schur_direct import (
    build_hybrid_modal_schur_memory_minimal_system,
    solve_hybrid_modal_schur_direct,
)
from src.solvers.hybrid_local_dtn import (
    assemble_hybrid_local_dtn_system,
)
from src.solvers.hybrid_strong_trace_direct import (
    build_hybrid_strong_trace_interface_map,
)
from src.solvers.hcurl_canonical_vector_dolfinx import (
    extract_canonical_active_trace_packets,
)
from src.solvers.static_modal_coarse_basis import HomogeneousEndcapExtender


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
        h_nm = 15.0 if MPI.COMM_WORLD.size >= 8 else 100.0
        base = replace(
            target_stage4_config(degree=2, h_nm=h_nm),
            matrix_diagnostics_assemble_only=False,
            matrix_diagnostics_factorization_only=False,
        )
        cls.standard_cfg = base
        cls.static_cfg = replace(
            base,
            stage4_full3d_assembly_backend=(ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND),
        )
        cls.cross_section = build_matching_cross_section(base, "stage4_xy")
        cls.spaces = build_cross_section_spaces(
            cls.cross_section,
            transverse_degree=2,
        )
        target = np.sqrt(
            (base.k0 * complex(base.n_air)) ** 2 - base.kx**2 - base.ky**2 + 0.0j
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
            assemble_hybrid_local_dtn_system(base, side) for side in ("bottom", "top")
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
        )
        cls.static_coupling = build_hybrid_internal_mode_coupling(
            cls.static_cfg,
            cls.spaces,
            cls.positive,
            cls.negative,
            *cls.static_systems,
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
            self.assertTrue(block.tangential_surface_trace_only_verified)
            self.assertFalse(block.interior_modal_pairwise_schur_evaluated)
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
            static["fe_modal_traction_equilibrium"]["bottom_relative_residual"],
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
                recovered.full_operator_residual["linear_system_relative_residual"],
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
                recovered.streaming_audit["full_surface_mode_matrix_retained"]
            )
            self.assertFalse(recovered.streaming_audit["full_global_matrix_allocated"])
            self.assertEqual(
                recovered.streaming_audit["internal_mode_surface_vectors_reassembled"],
                4,
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
                float(np.linalg.norm(self.static_solution.modal_amplitudes)),
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

    def test_static_endcap_homogeneous_extension_gate_c(self) -> None:
        static_systems = self.static_systems
        static_coupling = self.static_coupling
        interface_maps = tuple(
            build_hybrid_strong_trace_interface_map(
                system,
                static_coupling,
                research_opt_in=True,
            )
            for system in static_systems
        )
        extenders = tuple(
            HomogeneousEndcapExtender.from_system(
                system,
                interface_map,
                research_opt_in=True,
            )
            for system, interface_map in zip(
                static_systems,
                interface_maps,
                strict=True,
            )
        )
        mode_count = static_coupling.mode_count_per_direction
        negative_map = np.asarray(
            static_coupling.negative_trace_to_positive,
            dtype=np.complex128,
        )
        unit = np.zeros(mode_count, dtype=np.complex128)
        unit[0] = 1.0 + 0.0j
        forward_factors = np.asarray(
            static_coupling.propagation.forward.factors,
            dtype=np.complex128,
        )
        backward_factors = np.asarray(
            static_coupling.propagation.backward.factors,
            dtype=np.complex128,
        )
        cases = (
            ("forward", "bottom", unit),
            ("forward", "top", forward_factors[0] * unit),
            ("backward", "bottom", backward_factors[0] * negative_map[:, 0]),
            ("backward", "top", negative_map[:, 0]),
        )
        shared_tolerance = max(
            mesh_coordinate_tolerance(system.V.mesh) for system in static_systems
        )
        audits = []

        def modal_vector(interface_map, coefficients):
            vector = interface_map.right_prolongation.createVecRight()
            first, last = map(int, vector.getOwnershipRange())
            vector.getArray()[:] = coefficients[first:last]
            vector.assemble()
            return vector

        def direct_active_prefix(system, vector):
            condensed = system.static_condensation.condensed
            active = condensed.create_active_vector()
            vector_first, vector_last = map(
                int,
                vector.getOwnershipRange(),
            )
            active_first, active_last = map(
                int,
                active.getOwnershipRange(),
            )
            self.assertEqual(vector_first, active_first)
            self.assertEqual(
                active_last,
                min(vector_last, int(system.n_fe)),
            )
            local_count = active_last - active_first
            values = np.asarray(vector.getArray(readonly=True))
            self.assertGreaterEqual(local_count, 0)
            self.assertLessEqual(local_count, len(values))
            active.getArray()[:] = values[:local_count]
            active.assemble()
            return active

        def packet_map(packets):
            return {key: complex(value) for key, value in packets}

        def interface_map_for_packets(packets, system):
            plane = int(np.rint(system.local_mesh.interface_z_nm / shared_tolerance))
            return {
                key: value
                for key, value in packet_map(packets).items()
                if all(int(point[2]) == plane for point in key[2])
            }

        def outer_norm(packets, system):
            plane = int(np.rint(system.local_mesh.interface_z_nm / shared_tolerance))
            values = [
                value
                for key, value in packet_map(packets).items()
                if (
                    max(int(point[2]) for point in key[2]) < plane
                    if system.side == "bottom"
                    else min(int(point[2]) for point in key[2]) > plane
                )
            ]
            return float(np.linalg.norm(np.asarray(values, dtype=np.complex128)))

        def relative_packet_error(left, right):
            left_map = packet_map(left)
            right_map = packet_map(right)
            self.assertTrue(left_map)
            self.assertEqual(set(left_map), set(right_map))
            keys = sorted(left_map, key=repr)
            left_values = np.asarray(
                [left_map[key] for key in keys],
                dtype=np.complex128,
            )
            right_values = np.asarray(
                [right_map[key] for key in keys],
                dtype=np.complex128,
            )
            return float(
                np.linalg.norm(left_values - right_values)
                / max(
                    np.linalg.norm(left_values),
                    np.linalg.norm(right_values),
                    np.finfo(float).tiny,
                )
            )

        try:
            for direction, side, coefficients in cases:
                side_index = 0 if side == "bottom" else 1
                system = static_systems[side_index]
                interface_map = interface_maps[side_index]
                extender = extenders[side_index]
                full, audit = extender.apply(
                    coefficients,
                    research_opt_in=True,
                )
                observed_active = None
                expected_active = None
                modal = None
                trace = None
                try:
                    self.assertTrue(
                        np.all(
                            np.isfinite(
                                np.asarray(
                                    full.getArray(readonly=True),
                                    dtype=np.complex128,
                                )
                            )
                        )
                    )
                    observed_active = extender.extract_active_fe_prefix(
                        full,
                        research_opt_in=True,
                    )
                    observed_packets, _observed_audit = (
                        extract_canonical_active_trace_packets(
                            system.static_condensation.condensed,
                            system.V,
                            system.floquet_data,
                            observed_active,
                            geometry_tolerance=shared_tolerance,
                        )
                    )
                    modal = modal_vector(interface_map, coefficients)
                    trace = interface_map.right_prolongation.createVecLeft()
                    interface_map.right_prolongation.mult(modal, trace)
                    expected_active = direct_active_prefix(system, trace)
                    expected_packets, _expected_audit = (
                        extract_canonical_active_trace_packets(
                            system.static_condensation.condensed,
                            system.V,
                            system.floquet_data,
                            expected_active,
                            geometry_tolerance=shared_tolerance,
                        )
                    )
                    observed_interface = interface_map_for_packets(
                        observed_packets,
                        system,
                    )
                    expected_interface = interface_map_for_packets(
                        expected_packets,
                        system,
                    )
                    self.assertTrue(observed_interface)
                    self.assertEqual(
                        set(observed_interface),
                        set(expected_interface),
                    )
                    interface_error = relative_packet_error(
                        tuple(observed_interface.items()),
                        tuple(expected_interface.items()),
                    )
                    endcap_norm = outer_norm(observed_packets, system)
                    self.assertLessEqual(audit["retained_residual_relative"], 1.0e-10)
                    self.assertLessEqual(audit["interface_relative_mismatch"], 1.0e-10)
                    self.assertLessEqual(interface_error, 1.0e-10)
                    self.assertGreater(endcap_norm, 0.0)
                    self.assertTrue(
                        np.all(
                            np.isfinite(
                                np.asarray(
                                    [value for _key, value in observed_packets],
                                    dtype=np.complex128,
                                )
                            )
                        )
                    )
                    self.assertFalse(audit["normal_equations_used"])
                    audits.append(
                        {
                            "direction": direction,
                            "side": side,
                            "retained_residual_relative": audit[
                                "retained_residual_relative"
                            ],
                            "interface_relative_mismatch": audit[
                                "interface_relative_mismatch"
                            ],
                            "canonical_interface_relative_error": interface_error,
                            "outer_packet_norm": endcap_norm,
                            "factor_setup_count": audit["factor_setup_count"],
                            "factor_apply_count": audit["factor_apply_count"],
                        }
                    )
                finally:
                    if expected_active is not None:
                        expected_active.destroy()
                    if observed_active is not None:
                        observed_active.destroy()
                    if trace is not None:
                        trace.destroy()
                    if modal is not None:
                        modal.destroy()
                    full.destroy()

            for extender in extenders:
                self.assertEqual(extender.factor_setup_count, 1)
                self.assertEqual(extender.apply_count, 2)
                extender.destroy()
                self.assertTrue(extender.factor_released)
            for audit in audits:
                audit["factor_released"] = True
            print("E1C_HYBRID_ENDCAP_AUDIT", audits)
        finally:
            for extender in extenders:
                extender.destroy()
            for interface_map in interface_maps:
                interface_map.destroy()


if __name__ == "__main__":
    unittest.main()
