from __future__ import annotations

import unittest
from types import SimpleNamespace

import numpy as np
from dolfinx import fem
from mpi4py import MPI
from petsc4py import PETSc

from src.common.config_3d import target_stage4_config
from src.coupling.hybrid_internal_modes import (
    _ReusableInterfaceLifter,
    _ReusableModeTractionEvaluator,
    build_hybrid_internal_mode_coupling,
)
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


class Task032HybridInternalModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        def progress(message: str) -> None:
            if MPI.COMM_WORLD.rank == 0:
                print(message, flush=True)

        cls.cfg = target_stage4_config(degree=2, h_nm=10.0)
        cls.cross_section = build_matching_cross_section(cls.cfg, "stage4_xy")
        progress("Task32 test38: cross-section mesh complete")
        cls.spaces = build_cross_section_spaces(
            cls.cross_section, transverse_degree=2
        )
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
                    phase = np.exp(
                        1j * (self.cfg.kx * x[0] + self.cfg.ky * x[1])
                    )
                    values = np.zeros(
                        (3, x.shape[1]), dtype=PETSc.ScalarType
                    )
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


if __name__ == "__main__":
    unittest.main()
