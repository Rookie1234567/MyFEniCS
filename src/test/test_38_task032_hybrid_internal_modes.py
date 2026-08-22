from __future__ import annotations

import unittest
import inspect
from unittest import mock
from types import SimpleNamespace

import numpy as np
from dolfinx import fem
from mpi4py import MPI
from petsc4py import PETSc

from src.common.config_3d import target_stage4_config
from src.coupling.hybrid_internal_modes import (
    _ReusableInterfaceLifter,
    _ReusableModeTractionEvaluator,
    _trace_from_streamed_local_values,
    build_hybrid_internal_mode_coupling,
    build_streamed_projection_only,
)
from src.coupling.modal_trace_projection import ModalTraceProjection
from src.modes.cross_section_spaces import (
    build_cross_section_spaces,
    build_matching_cross_section,
)
from src.solvers.hybrid_local_dtn import assemble_hybrid_local_dtn_system


def _small_vector_values(vector: PETSc.Vec) -> np.ndarray:
    start, end = vector.getOwnershipRange()
    payload = (start, end, np.asarray(vector.getArray(readonly=True)).copy())
    gathered = MPI.COMM_WORLD.allgather(payload)
    result = np.empty(vector.getSize(), dtype=np.complex128)
    for first, last, values in gathered:
        result[first:last] = values
    return result


def _augmented_local_field_vector(system, field) -> PETSc.Vec:
    # The assembled MPC operator acts on its homogenized solution-vector
    # representation; physical slave values are restored only afterwards by
    # mpc.backsubstitution.
    system.floquet_data.mpc.homogenize(field)
    field.x.scatter_forward()
    vector = system.b.duplicate()
    vector.set(0.0)
    index_map = field.function_space.dofmap.index_map
    block_size = field.function_space.dofmap.index_map_bs
    owned_size = int(index_map.size_local * block_size)
    start = int(system.A.getOwnershipRange()[0])
    end = start + owned_size
    values = np.asarray(field.x.array[:owned_size])
    if len(values):
        vector.setValues(
            np.arange(start, end, dtype=PETSc.IntType),
            values,
            addv=PETSc.InsertMode.INSERT_VALUES,
        )
    vector.assemble()
    return vector


class Task032HybridInternalModeFailureCleanupTests(unittest.TestCase):
    @staticmethod
    def _inputs():
        positive_mode = SimpleNamespace(
            beta=0.2 + 0.01j,
            direction="forward",
            right=SimpleNamespace(right_full=object()),
        )
        negative_mode = SimpleNamespace(
            beta=-0.2 - 0.01j,
            direction="backward",
            right=SimpleNamespace(right_full=object()),
        )
        return {
            "cfg": SimpleNamespace(nedelec_degree=2, mesh_target_size=5.0),
            "spaces": object(),
            "positive_basis": SimpleNamespace(modes=[positive_mode]),
            "negative_basis": SimpleNamespace(modes=[negative_mode]),
            "bottom_system": SimpleNamespace(
                side="bottom", assembly_backend_actual="test"
            ),
            "top_system": SimpleNamespace(side="top", assembly_backend_actual="test"),
        }

    def test_projection_is_destroyed_when_negative_trace_extraction_fails(self):
        projection = SimpleNamespace(
            right_traces=(object(),),
            project=mock.Mock(return_value=np.ones(1, dtype=np.complex128)),
            destroy=mock.Mock(),
        )
        with (
            mock.patch(
                "src.coupling.hybrid_internal_modes.ModalTraceProjection",
                return_value=projection,
            ),
            mock.patch(
                "src.coupling.hybrid_internal_modes._trace_from_full_mode_vector",
                side_effect=RuntimeError("controlled trace failure"),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "controlled trace failure"):
                build_hybrid_internal_mode_coupling(**self._inputs())
        projection.destroy.assert_called_once_with()

    def test_projection_is_destroyed_when_discrete_traction_fails(self):
        projection = SimpleNamespace(
            right_traces=(object(),),
            project=mock.Mock(return_value=np.ones(1, dtype=np.complex128)),
            destroy=mock.Mock(),
        )
        patches = (
            mock.patch(
                "src.coupling.hybrid_internal_modes.ModalTraceProjection",
                return_value=projection,
            ),
            mock.patch(
                "src.coupling.hybrid_internal_modes._trace_from_full_mode_vector",
                return_value=object(),
            ),
            mock.patch(
                "src.coupling.hybrid_internal_modes.build_two_sided_propagation",
                return_value=object(),
            ),
            mock.patch(
                "src.coupling.hybrid_internal_modes.scalar_cg_discrete_traction_beta",
                side_effect=RuntimeError("controlled traction failure"),
            ),
        )
        with patches[0], patches[1], patches[2], patches[3]:
            with self.assertRaisesRegex(RuntimeError, "controlled traction failure"):
                build_hybrid_internal_mode_coupling(
                    **self._inputs(),
                    propagation_model="full3d_uniform_cg",
                    modal_traction_model="scalar_cg_discrete_derivative",
                )
        projection.destroy.assert_called_once_with()


class Task032HybridInternalModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        def progress(message: str) -> None:
            if MPI.COMM_WORLD.rank == 0:
                print(message, flush=True)

        cls.cfg = target_stage4_config(degree=2, h_nm=10.0)
        cls.cross_section = build_matching_cross_section(cls.cfg, "stage4_xy")
        progress("Task32 test38: cross-section mesh complete")
        cls.spaces = build_cross_section_spaces(cls.cross_section, transverse_degree=2)
        progress("Task32 test38: cross-section spaces complete")
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
                phase = np.exp(1j * (cls.cfg.kx * x[0] + cls.cfg.ky * x[1]))
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

        # This unit test exercises MPI ownership and 2D-to-3D coupling with
        # two independent Bloch traces.  Formal runners independently solve
        # the positive/negative right and adjoint QEP bases.
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
        progress("Task32 test38: synthetic reciprocal modes complete")
        cls.bottom_system = assemble_hybrid_local_dtn_system(cls.cfg, "bottom")
        progress("Task32 test38: bottom local DtN complete")
        cls.top_system = assemble_hybrid_local_dtn_system(cls.cfg, "top")
        progress("Task32 test38: top local DtN complete")
        cls.coupling = build_hybrid_internal_mode_coupling(
            cls.cfg,
            cls.spaces,
            cls.positive,
            cls.negative,
            cls.bottom_system,
            cls.top_system,
            log=(
                (lambda message: print(message, flush=True))
                if MPI.COMM_WORLD.rank == 0
                else None
            ),
        )

    @classmethod
    def tearDownClass(cls):
        cls.coupling.destroy()
        for system in (cls.bottom_system, cls.top_system):
            system.A.destroy()
            system.b.destroy()
        for vector in cls.mode_vectors:
            vector.destroy()

    def test_dimension_contract_is_square_without_four_dimensional_trace(self):
        coupling = self.coupling
        self.assertEqual(coupling.mode_count_per_direction, 2)
        self.assertEqual(coupling.internal_unknown_count, 4)
        self.assertEqual(coupling.internal_equation_count, 4)
        self.assertEqual(coupling.negative_trace_to_positive.shape, (2, 2))
        self.assertLess(coupling.positive_projection_identity_error, 1.0e-10)
        self.assertFalse(coupling.dense_interface_square_formed)
        self.assertFalse(coupling.full_field_or_mode_gathered)

    def test_stable_propagation_uses_no_growing_inverse(self):
        propagation = self.coupling.propagation
        self.assertEqual(propagation.forward.mode_count, 2)
        self.assertEqual(propagation.backward.mode_count, 2)
        self.assertFalse(propagation.growing_inverse_factors_present)
        self.assertTrue(propagation.passivity_valid)
        self.assertLessEqual(propagation.max_factor_magnitude, 1.0 + 1.0e-14)

    def test_projection_rows_recover_positive_and_negative_traces(self):
        for system, blocks in (
            (self.bottom_system, self.coupling.bottom),
            (self.top_system, self.coupling.top),
        ):
            for column in range(2):
                lifted = fem.Function(system.V)

                def field(x, component=column):
                    phase = np.exp(1j * (self.cfg.kx * x[0] + self.cfg.ky * x[1]))
                    values = np.zeros((3, x.shape[1]), dtype=PETSc.ScalarType)
                    values[component, :] = phase
                    return values

                lifted.interpolate(field)
                lifted.x.scatter_forward()
                result = blocks.projection.createVecLeft()
                augmented = _augmented_local_field_vector(system, lifted)
                try:
                    blocks.projection.mult(augmented, result)
                    expected = np.eye(2, dtype=np.complex128)[:, column]
                    np.testing.assert_allclose(
                        _small_vector_values(result), expected, atol=1.0e-9, rtol=1.0e-9
                    )
                finally:
                    augmented.destroy()
                    result.destroy()
            np.testing.assert_allclose(
                blocks.negative_trace_to_positive,
                np.eye(2),
                atol=1.0e-10,
                rtol=1.0e-10,
            )

    def test_streamed_projection_matches_full_owner_without_traction_matrix(self):
        if MPI.COMM_WORLD.size >= 4:
            self.skipTest(
                "Retained full-owner plus second-D exact authority is limited to "
                "serial/MPI2; MPI4 uses the fresh single-build action/lifecycle test."
            )
        self.assertNotIn(
            ".petsc_vec",
            inspect.getsource(_trace_from_streamed_local_values),
        )

        def mode_pair(branch, index):
            mode = (self.positive if branch == "positive" else self.negative).modes[
                index
            ]
            right = mode.right.right_full
            left = mode.left_full
            return {
                "right_local": np.array(
                    right.getArray(readonly=True), dtype=np.complex128, copy=True
                ),
                "left_local": np.array(
                    left.getArray(readonly=True), dtype=np.complex128, copy=True
                ),
                "ownership_range": list(right.getOwnershipRange()),
                "global_size": int(right.getSize()),
            }

        negative_mix = np.asarray([[1.0, 0.25], [-0.5, 1.5]])
        raw_negative_right = [
            np.array(
                mode.right.right_full.getArray(readonly=True),
                dtype=np.complex128,
                copy=True,
            )
            for mode in self.negative.modes
        ]

        def mixed_mode_pair(branch, index):
            pair = mode_pair(branch, index)
            if branch == "negative":
                pair["right_local"] = sum(
                    negative_mix[row, index] * raw_negative_right[row]
                    for row in range(2)
                )
            return pair

        with (
            mock.patch(
                "src.coupling.hybrid_internal_modes._build_traction_matrix",
                side_effect=AssertionError("streamed projection built traction"),
            ),
            mock.patch(
                "src.coupling.hybrid_internal_modes._canonicalized_negative_traces",
                side_effect=AssertionError(
                    "streamed projection eagerly materialized canonical traces"
                ),
            ),
            mock.patch(
                "src.coupling.modal_trace_projection._assemble_trace_mass",
                side_effect=AssertionError(
                    "streamed projection materialized trace mass matrix"
                ),
            ),
        ):
            streamed = build_streamed_projection_only(
                self.bottom_system,
                self.spaces,
                mixed_mode_pair,
                mode_count=2,
            )
        source = self.bottom_system.A.createVecRight()
        streamed_output = streamed.projection.createVecLeft()
        owner_output = self.coupling.bottom.projection.createVecLeft()
        difference = streamed_output.duplicate()
        try:
            first, last = source.getOwnershipRange()
            source.set(0.0)
            source.getArray()[:] = np.arange(first, last) + 0.25j
            source.assemble()
            streamed.projection.mult(source, streamed_output)
            self.coupling.bottom.projection.mult(source, owner_output)
            streamed_output.copy(difference)
            difference.axpy(-1.0, owner_output)
            relative_error = float(difference.norm()) / max(
                float(owner_output.norm()), 1.0e-30
            )
            self.assertLessEqual(relative_error, 1.0e-12)
            self.assertAlmostEqual(
                streamed.audit["trace_gram_condition"],
                self.coupling.bottom.trace_gram_condition,
                places=10,
            )
            self.assertGreater(streamed.audit["canonical_mapping_condition"], 1.0)
            self.assertEqual(streamed.audit["canonical_trace_peak_live_count"], 1)
            self.assertEqual(streamed.audit["canonical_trace_retained_count"], 0)
            self.assertEqual(
                streamed.audit["canonical_trace_materialization"],
                "single_reusable",
            )
            self.assertFalse(streamed.audit["trace_mass_matrix_materialized"])
            self.assertEqual(
                streamed.audit["trace_mass_action"], "reusable_form_action"
            )
            self.assertFalse(streamed.audit["full_mode_vectors_retained"])
            self.assertFalse(streamed.audit["positive_traction_matrix"])
            self.assertFalse(streamed.audit["negative_traction_matrix"])

            base_right = self.coupling.projection.right_traces[0]
            base_left = self.coupling.projection.left_traces[0]
            scaled_right = fem.Function(self.spaces.transverse)
            scaled_left = fem.Function(self.spaces.transverse)
            scaled_right.x.array[:] = 2.0 * base_right.x.array
            scaled_left.x.array[:] = base_left.x.array
            scaled_right.x.scatter_forward()
            scaled_left.x.scatter_forward()
            nonunit = ModalTraceProjection.from_traces(
                self.spaces, [scaled_right], [scaled_left]
            )
            try:
                self.assertFalse(np.allclose(nonunit.gram, np.eye(1)))
                round_trip = nonunit.round_trip([1.0 + 0.25j])
                self.assertLessEqual(round_trip.coefficient_relative_error, 1.0e-12)
                self.assertLessEqual(round_trip.trace_relative_residual, 1.0e-12)
            finally:
                nonunit.destroy()
        finally:
            difference.destroy()
            owner_output.destroy()
            streamed_output.destroy()
            source.destroy()
            streamed.destroy()

    def test_top_bottom_blocks_encode_explicit_opposite_normals(self):
        bottom = self.coupling.bottom
        top = self.coupling.top
        self.assertEqual(bottom.local_fem_outward_normal_sign, +1)
        self.assertEqual(top.local_fem_outward_normal_sign, -1)
        self.assertGreater(bottom.lifted_query_points, 0)
        self.assertEqual(bottom.lifted_query_points, top.lifted_query_points)

        self.assertGreater(float(bottom.projection.norm()), 0.0)
        self.assertGreater(float(top.projection.norm()), 0.0)
        # Bottom and top use independent FE/MPC coordinate representations,
        # so their raw sparse-matrix Frobenius norms are not a physical
        # invariant.  Each block must instead be finite/nonzero, while the
        # field-level check below verifies the actual normal-sign convention.
        for matrix in (
            bottom.positive_traction,
            bottom.negative_traction,
            top.positive_traction,
            top.negative_traction,
        ):
            norm = float(matrix.norm())
            self.assertTrue(np.isfinite(norm))
            self.assertGreater(norm, 0.0)

        evaluator = _ReusableModeTractionEvaluator(self.spaces)
        for mode in (*self.positive.modes, *self.negative.modes):
            plus = evaluator.evaluate(mode, local_outward_normal_sign=+1)
            plus_values = plus.x.array.copy()
            minus = evaluator.evaluate(mode, local_outward_normal_sign=-1)
            np.testing.assert_allclose(
                plus_values,
                -minus.x.array,
                atol=1.0e-12,
                rtol=1.0e-12,
            )

    def test_interface_lifter_routes_independently_refined_modal_mesh(self):
        modal_cfg = target_stage4_config(degree=2, h_nm=5.0)
        modal_mesh = build_matching_cross_section(modal_cfg, "stage4_xy")
        modal_spaces = build_cross_section_spaces(
            modal_mesh,
            transverse_degree=2,
        )
        source = fem.Function(modal_spaces.transverse)

        def constant_trace(x):
            values = np.zeros((2, x.shape[1]), dtype=PETSc.ScalarType)
            values[0, :] = 1.0
            values[1, :] = -0.5j
            return values

        source.interpolate(constant_trace)
        source.x.scatter_forward()
        lifter = _ReusableInterfaceLifter(self.bottom_system)
        lifted, query_count = lifter.lift(source)
        self.assertGreater(query_count, 0)
        self.assertGreater(float(np.linalg.norm(lifted.x.array)), 0.0)


class Task032StreamedProjectionFreshLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = target_stage4_config(degree=2, h_nm=10.0)
        cls.cross_section = build_matching_cross_section(cls.cfg, "stage4_xy")
        cls.spaces = build_cross_section_spaces(
            cls.cross_section,
            transverse_degree=2,
        )
        cls.system = assemble_hybrid_local_dtn_system(cls.cfg, "bottom")

        target = np.sqrt(
            (cls.cfg.k0 * complex(cls.cfg.n_air)) ** 2
            - cls.cfg.kx**2
            - cls.cfg.ky**2
            + 0.0j
        )

        def packet(component: int, beta: complex, direction: str):
            trace = fem.Function(cls.spaces.transverse)

            def field(x):
                values = np.zeros((2, x.shape[1]), dtype=PETSc.ScalarType)
                values[component, :] = np.exp(
                    1j * (cls.cfg.kx * x[0] + cls.cfg.ky * x[1])
                )
                return values

            trace.interpolate(field)
            trace.x.scatter_forward()
            mixed = fem.Function(cls.spaces.mixed)
            mixed.x.array[:] = 0.0
            mixed.x.array[cls.spaces.transverse_to_mixed] = trace.x.array
            mixed.x.scatter_forward()
            index_map = cls.spaces.mixed.dofmap.index_map
            block_size = int(cls.spaces.mixed.dofmap.index_map_bs)
            block_start, block_end = map(int, index_map.local_range)
            owned_size = (block_end - block_start) * block_size
            values = np.asarray(mixed.x.array[:owned_size]).copy()
            del mixed, trace
            return {
                "right_local": values,
                "left_local": values.copy(),
                "ownership_range": (
                    block_start * block_size,
                    block_end * block_size,
                ),
                "global_size": int(index_map.size_global * block_size),
                "beta": beta,
                "direction": direction,
            }

        cls.positive_packets = [
            packet(component, target, "forward") for component in range(2)
        ]
        for index, scale in enumerate((2.0, 3.0)):
            cls.positive_packets[index]["left_local"] *= scale
        cls.negative_packets = [
            packet(component, -target, "backward") for component in range(2)
        ]

    @classmethod
    def tearDownClass(cls):
        cls.system.A.destroy()
        cls.system.b.destroy()

    def test_streamed_projection_fresh_single_build_action_identity(self):
        negative_mix = np.asarray([[1.0, 0.25], [-0.5, 1.5]])

        def mode_pair(branch, index):
            source = (
                self.positive_packets[index]
                if branch == "positive"
                else self.negative_packets[index]
            )
            result = dict(source)
            if branch == "negative":
                result["right_local"] = sum(
                    negative_mix[row, index] * self.negative_packets[row]["right_local"]
                    for row in range(2)
                )
            return result

        with mock.patch(
            "src.coupling.modal_trace_projection._assemble_trace_mass",
            side_effect=AssertionError(
                "streamed projection materialized trace mass matrix"
            ),
        ):
            streamed = build_streamed_projection_only(
                self.system,
                self.spaces,
                mode_pair,
                mode_count=2,
            )
        try:
            self.assertGreater(streamed.audit["trace_gram_condition"], 1.0)
            self.assertGreater(streamed.audit["canonical_mapping_condition"], 1.0)
            self.assertEqual(streamed.audit["canonical_trace_peak_live_count"], 1)
            self.assertEqual(streamed.audit["canonical_trace_retained_count"], 0)
            self.assertEqual(
                streamed.audit["canonical_trace_materialization"],
                "single_reusable",
            )
            self.assertFalse(streamed.audit["trace_mass_matrix_materialized"])
            self.assertEqual(
                streamed.audit["trace_mass_action"], "reusable_form_action"
            )
            self.assertFalse(streamed.audit["positive_traction_matrix"])
            self.assertFalse(streamed.audit["negative_traction_matrix"])
            for component in range(2):
                lifted = fem.Function(self.system.V)

                def field(x, component=component):
                    values = np.zeros((3, x.shape[1]), dtype=PETSc.ScalarType)
                    values[component, :] = np.exp(
                        1j * (self.cfg.kx * x[0] + self.cfg.ky * x[1])
                    )
                    return values

                lifted.interpolate(field)
                lifted.x.scatter_forward()
                source = _augmented_local_field_vector(self.system, lifted)
                output = streamed.projection.createVecLeft()
                try:
                    streamed.projection.mult(source, output)
                    np.testing.assert_allclose(
                        _small_vector_values(output),
                        np.eye(2, dtype=np.complex128)[:, component],
                        atol=1.0e-9,
                        rtol=1.0e-9,
                    )
                finally:
                    output.destroy()
                    source.destroy()
        finally:
            streamed.destroy()


if __name__ == "__main__":
    unittest.main()
