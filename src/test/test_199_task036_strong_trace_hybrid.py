from __future__ import annotations

from dataclasses import replace
from time import perf_counter
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
from src.coupling.modal_trace_projection import (
    _trace_from_full_mode_vector,
    interface_convention,
)
from src.modes.cross_section_spaces import (
    build_cross_section_spaces,
    build_matching_cross_section,
)
from src.solvers.hybrid_local_dtn import assemble_hybrid_local_dtn_system
from src.solvers.hybrid_strong_trace_direct import (
    build_hybrid_strong_trace_direct_system,
    evaluate_hybrid_strong_trace_solution,
    exact_trace_dense_fixture,
    recover_hybrid_strong_trace_static_fields,
    solve_hybrid_strong_trace_direct,
)


class Task036ExactTraceDenseFixtureTests(unittest.TestCase):
    def test_lossy_petrov_system_excludes_trace_complement(self) -> None:
        rng = np.random.default_rng(36001)
        mode_count = 2
        local_rows = 6
        interface = np.asarray([1, 3, 4], dtype=np.int64)
        retained = np.asarray(
            [row for row in range(local_rows) if row not in set(interface)]
        )

        right_gamma = (
            rng.normal(size=(len(interface), mode_count))
            + 1j * rng.normal(size=(len(interface), mode_count))
        )
        raw_left_gamma = (
            rng.normal(size=(len(interface), mode_count))
            + 1j * rng.normal(size=(len(interface), mode_count))
        )
        mass_seed = (
            rng.normal(size=(len(interface), len(interface)))
            + 1j * rng.normal(size=(len(interface), len(interface)))
        )
        mass = mass_seed.conj().T @ mass_seed + np.eye(len(interface))
        gram = raw_left_gamma.conj().T @ mass @ right_gamma
        inverse_gram = np.linalg.inv(gram)
        left_gamma = (
            inverse_gram @ raw_left_gamma.conj().T @ mass
        )
        normalized_left_gamma = raw_left_gamma @ inverse_gram.conj().T
        self.assertGreater(
            np.linalg.norm(
                normalized_left_gamma - right_gamma
            ),
            1.0e-2,
        )
        self.assertGreater(
            np.linalg.norm(
                left_gamma - normalized_left_gamma.conj().T
            ),
            1.0e-2,
        )

        R = np.zeros((local_rows, mode_count), dtype=np.complex128)
        D = np.zeros((mode_count, local_rows), dtype=np.complex128)
        W = np.zeros((local_rows, mode_count), dtype=np.complex128)
        R[interface] = right_gamma
        D[:, interface] = left_gamma
        W[interface] = normalized_left_gamma
        np.testing.assert_allclose(
            D @ R,
            np.eye(mode_count),
            rtol=0.0,
            atol=1.0e-12,
        )

        trial = (
            rng.normal(size=(local_rows, local_rows))
            + 1j * rng.normal(size=(local_rows, local_rows))
        )
        A = trial + (8.0 + 0.7j) * np.eye(local_rows)
        C = (
            rng.normal(size=(local_rows, mode_count))
            + 1j * rng.normal(size=(local_rows, mode_count))
        )
        L = np.asarray(
            [[1.0, 0.15 - 0.03j], [-0.08 + 0.02j, 0.9 + 0.1j]],
            dtype=np.complex128,
        )
        b = (
            rng.normal(size=local_rows)
            + 1j * rng.normal(size=local_rows)
        )
        audit = exact_trace_dense_fixture(
            A, b, D, R, W, C, L, interface
        )
        self.assertEqual(
            audit["reduced_matrix"].shape,
            (len(retained) + mode_count, len(retained) + mode_count),
        )
        self.assertLess(audit["dr_identity_error"], 1.0e-12)
        self.assertLess(audit["noninterface_residual"], 1.0e-11)
        self.assertLess(audit["petrov_residual"], 1.0e-11)
        self.assertLess(audit["trace_identity_residual"], 1.0e-12)
        self.assertEqual(audit["trace_complement_unknown_count"], 0)
        self.assertFalse(audit["dense_interface_square_formed"])

        arbitrary = (
            rng.normal(size=local_rows)
            + 1j * rng.normal(size=local_rows)
        )
        complement = arbitrary - R @ (D @ arbitrary)
        self.assertGreater(np.linalg.norm(complement), 1.0e-3)
        self.assertLess(np.linalg.norm(D @ complement), 1.0e-12)


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
    trace_only_vector = mixed.x.petsc_vec.duplicate()
    mixed.x.petsc_vec.copy(trace_only_vector)
    owned_vectors.append(trace_only_vector)
    longitudinal_norm = 0.0
    if component == 1:
        longitudinal = fem.Function(spaces.longitudinal)

        def axial_field(x):
            return np.asarray(
                (0.35 + 0.12j)
                * np.exp(1j * (cfg.kx * x[0] + cfg.ky * x[1])),
                dtype=PETSc.ScalarType,
            )

        longitudinal.interpolate(axial_field)
        longitudinal.x.scatter_forward()
        mixed.x.array[spaces.longitudinal_to_mixed] = longitudinal.x.array
        mixed.x.scatter_forward()
        longitudinal_norm = float(longitudinal.x.petsc_vec.norm())
    vector = mixed.x.petsc_vec.duplicate()
    mixed.x.petsc_vec.copy(vector)
    owned_vectors.append(vector)
    return SimpleNamespace(
        beta=complex(beta),
        right=SimpleNamespace(right_full=vector),
        left_full=vector,
        trace_only_full=trace_only_vector,
        longitudinal_norm=longitudinal_norm,
        direction=direction,
        passive_branch_valid=True,
    )


def _floquet_constraint_residual(system, source) -> float:
    """Recover physical slaves and check the oriented MPC relation."""

    mpc = system.floquet_data.mpc
    field = fem.Function(mpc.function_space)
    index_map = mpc.function_space.dofmap.index_map
    start, end = map(int, index_map.local_range)
    owned = int(index_map.size_local)
    source_vector = source if isinstance(source, PETSc.Vec) else source.x.petsc_vec
    field.x.array[:owned] = source_vector.getValues(
        np.arange(start, end, dtype=PETSc.IntType)
    )
    field.x.scatter_forward()
    mpc.backsubstitution(field)
    field.x.scatter_forward()

    coefficients, offsets = mpc.coefficients()
    coefficients = np.asarray(coefficients, dtype=np.complex128)
    offsets = np.asarray(offsets, dtype=np.int64)
    local_max = 0.0
    for slave in system.floquet_data.local_slave_dofs:
        slave = int(slave)
        masters = np.asarray(
            mpc.masters.links(slave),
            dtype=np.int32,
        )
        start = int(offsets[slave])
        stop = int(offsets[slave + 1])
        row = coefficients[start:stop]
        if len(masters) != len(row):
            raise AssertionError("MPC master/coefficient count mismatch.")
        predicted = np.dot(row, field.x.array[masters])
        local_max = max(
            local_max,
            float(abs(complex(field.x.array[slave] - predicted))),
        )
    return float(
        system.local_mesh.mesh.comm.allreduce(local_max, op=MPI.MAX)
    )


class Task036StrongTraceBackendFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        started = perf_counter()

        def checkpoint(label: str) -> None:
            if MPI.COMM_WORLD.rank == 0:
                print(
                    f"Task036 strong fixture: {label} "
                    f"elapsed={perf_counter() - started:.3f}s",
                    flush=True,
                )

        # Keep the MPI8 qualification a true micro-fixture.  The purpose is
        # ownership/empty-rank/collective coverage, not a second benchmark.
        h_nm = 100.0
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
        cross_section = build_matching_cross_section(base, "stage4_xy")
        cls.spaces = build_cross_section_spaces(
            cross_section, transverse_degree=2
        )
        beta = np.sqrt(
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
                    beta=beta,
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
                    beta=-beta,
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
        checkpoint("standard local systems complete")
        cls.static_systems = tuple(
            assemble_hybrid_local_dtn_system(cls.static_cfg, side)
            for side in ("bottom", "top")
        )
        checkpoint("static local systems complete")
        cls.standard_coupling = build_hybrid_internal_mode_coupling(
            base,
            cls.spaces,
            cls.positive,
            cls.negative,
            *cls.standard_systems,
            propagation_model="full3d_uniform_cg",
            modal_traction_model="scalar_cg_discrete_derivative",
        )
        checkpoint("standard coupling complete")
        cls.static_coupling = build_hybrid_internal_mode_coupling(
            cls.static_cfg,
            cls.spaces,
            cls.positive,
            cls.negative,
            *cls.static_systems,
            propagation_model="full3d_uniform_cg",
            modal_traction_model="scalar_cg_discrete_derivative",
        )
        checkpoint("static coupling complete")
        cls.standard_strong = build_hybrid_strong_trace_direct_system(
            *cls.standard_systems, cls.standard_coupling
        )
        checkpoint("standard strong matrix complete")
        cls.static_strong = build_hybrid_strong_trace_direct_system(
            *cls.static_systems, cls.static_coupling
        )
        checkpoint("static strong matrix complete")
        cls.standard_solution = solve_hybrid_strong_trace_direct(
            cls.standard_strong,
            *cls.standard_systems,
            cls.standard_coupling,
        )
        checkpoint("standard strong solve complete")
        cls.static_solution = solve_hybrid_strong_trace_direct(
            cls.static_strong,
            *cls.static_systems,
            cls.static_coupling,
            recover_static=False,
        )
        checkpoint("static strong solve complete")
        if cls.static_solution.bottom_recovered is not None:
            raise AssertionError("Deferred static recovery unexpectedly ran.")
        cls.static_solution.release_factorization()
        recover_hybrid_strong_trace_static_fields(
            cls.static_solution,
            *cls.static_systems,
            cls.static_coupling,
        )
        checkpoint("static recovery after factor release complete")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.standard_solution.destroy()
        cls.static_solution.destroy()
        cls.standard_strong.destroy()
        cls.static_strong.destroy()
        cls.standard_coupling.destroy()
        cls.static_coupling.destroy()
        for system in (*cls.standard_systems, *cls.static_systems):
            system.destroy()
        for vector in cls.mode_vectors:
            vector.destroy()

    def test_backend_native_maps_and_no_dense_interface_square(self) -> None:
        self.assertEqual(
            interface_convention("bottom").local_fem_outward_normal_sign,
            +1,
        )
        self.assertEqual(
            interface_convention("top").local_fem_outward_normal_sign,
            -1,
        )
        p_mode = self.positive.modes[1]
        self.assertGreater(p_mode.longitudinal_norm, 0.0)
        with_longitudinal = _trace_from_full_mode_vector(
            p_mode.right.right_full,
            self.spaces,
            name="task036_p_with_longitudinal",
        )
        trace_only = _trace_from_full_mode_vector(
            p_mode.trace_only_full,
            self.spaces,
            name="task036_p_trace_only",
        )
        np.testing.assert_allclose(
            with_longitudinal.x.array,
            trace_only.x.array,
            rtol=0.0,
            atol=0.0,
        )
        for strong, systems in (
            (self.standard_strong, self.standard_systems),
            (self.static_strong, self.static_systems),
        ):
            self.assertEqual(strong.A.getSize()[0], strong.A.getSize()[1])
            self.assertFalse(strong.dense_interface_square_formed)
            self.assertFalse(strong.old_modal_constraint_retained)
            for interface, system in zip(
                (strong.bottom_interface, strong.top_interface),
                systems,
                strict=True,
            ):
                self.assertLess(interface.projection_identity_error, 1.0e-10)
                self.assertEqual(interface.trace_complement_unknown_count, 0)
                self.assertEqual(
                    interface.interface_rows.dtype,
                    np.dtype(PETSc.IntType),
                )
                retained = set(map(int, interface.retained_rows))
                trace = set(map(int, interface.interface_rows))
                slaves = set(map(int, interface.removed_slave_rows))
                self.assertFalse(retained & trace)
                self.assertFalse(retained & slaves)
                self.assertTrue(
                    set(range(system.n_fe, system.global_size)).issubset(
                        retained
                    )
                )

    def test_petrov_left_and_floquet_orientation_are_explicit(self) -> None:
        for strong, systems, solution in (
            (
                self.standard_strong,
                self.standard_systems,
                self.standard_solution,
            ),
            (
                self.static_strong,
                self.static_systems,
                self.static_solution,
            ),
        ):
            for interface, system, physical in zip(
                (strong.bottom_interface, strong.top_interface),
                systems,
                (solution.bottom_physical, solution.top_physical),
                strict=True,
            ):
                difference = interface.petrov_left_columns.copy()
                try:
                    difference.axpy(
                        PETSc.ScalarType(-1.0),
                        interface.right_prolongation,
                        structure=(
                            PETSc.Mat.Structure.DIFFERENT_NONZERO_PATTERN
                        ),
                    )
                    self.assertGreater(difference.norm(), 1.0e-6)
                finally:
                    difference.destroy()
                floquet = system.floquet_data
                self.assertGreater(abs(floquet.phase_x - 1.0), 1.0e-6)
                self.assertEqual(
                    floquet.num_slave_edges,
                    floquet.num_matched_master_edges,
                )
                self.assertEqual(
                    floquet.num_slave_faces,
                    floquet.num_matched_master_faces,
                )
                self.assertLessEqual(floquet.edge_corner_phase_mismatch, 1.0e-12)
                self.assertLessEqual(
                    floquet.max_face_transform_fit_residual,
                    2.0e-11,
                )
                self.assertFalse(floquet.created_dense_boundary_square)
                self.assertLessEqual(
                    _floquet_constraint_residual(system, physical),
                    2.0e-11,
                )

    def test_standard_static_strong_trace_equivalence(self) -> None:
        standard = evaluate_hybrid_strong_trace_solution(
            self.standard_cfg,
            *self.standard_systems,
            self.standard_coupling,
            self.standard_solution,
        )
        static = evaluate_hybrid_strong_trace_solution(
            self.static_cfg,
            *self.static_systems,
            self.static_coupling,
            self.static_solution,
        )
        modal_scale = max(
            np.linalg.norm(self.standard_solution.modal_amplitudes),
            1.0e-30,
        )
        self.assertLess(
            np.linalg.norm(
                self.static_solution.modal_amplitudes
                - self.standard_solution.modal_amplitudes
            )
            / modal_scale,
            1.0e-9,
        )
        for result in (standard, static):
            self.assertTrue(
                result["strong_trace"][
                    "formal_component_gates_pass"
                ],
                msg=result["strong_trace"],
            )
            for side in ("bottom", "top"):
                split = result["strong_trace"][side]
                for key in (
                    "noninterface_fe",
                    "modal_petrov_flux",
                    "strong_trace_identity",
                    "external_dtn",
                ):
                    self.assertLess(split[key]["relative"], 1.0e-9)
        for key in ("R_total", "T_total", "A_balance"):
            self.assertAlmostEqual(
                standard["port_power"][key],
                static["port_power"][key],
                places=9,
            )


if __name__ == "__main__":
    unittest.main()
