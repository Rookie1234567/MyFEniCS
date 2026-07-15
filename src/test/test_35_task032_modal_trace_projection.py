from __future__ import annotations

import unittest

import numpy as np
from basix.ufl import element
from dolfinx import default_real_type, fem
from mpi4py import MPI

from src.common.config_3d import target_stage4_config
from src.coupling.modal_trace_projection import (
    ModalTraceProjection,
    build_matched_interface_trace,
    extract_tangential_trace,
    interface_convention,
    trace_subspace_report,
)
from src.geometry.mesh_builder_3d import _structured_hexa_mesh, stage4_axis_plan
from src.modes.cross_section_spaces import (
    build_cross_section_spaces,
    build_matching_cross_section,
)
from src.modes.mode_classification import build_biorthogonal_mode_basis
from src.modes.quadratic_beta_eigenproblem import (
    analytic_homogeneous_beta,
    assemble_quadratic_beta_operators,
    solve_quadratic_beta_modes,
)


def _distributed_coefficient_relative_error(
    actual: fem.Function, expected: fem.Function
) -> float:
    index_map = actual.function_space.dofmap.index_map
    owned = int(index_map.size_local * actual.function_space.dofmap.index_map_bs)
    difference = actual.x.array[:owned] - expected.x.array[:owned]
    local_num = float(np.vdot(difference, difference).real)
    local_den = float(np.vdot(expected.x.array[:owned], expected.x.array[:owned]).real)
    numerator = MPI.COMM_WORLD.allreduce(local_num, op=MPI.SUM)
    denominator = MPI.COMM_WORLD.allreduce(local_den, op=MPI.SUM)
    return float(np.sqrt(numerator / max(denominator, 1.0e-30)))


class Task032MatchedTraceExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = target_stage4_config(degree=2, h_nm=10.0)
        cls.plan = stage4_axis_plan(cls.cfg, MPI.COMM_WORLD.size)
        cls.source_mesh = _structured_hexa_mesh(
            MPI.COMM_WORLD,
            cls.plan.x_values,
            cls.plan.y_values,
            cls.plan.z_values,
        )
        cls.cross_section = build_matching_cross_section(cls.cfg, "stage4_xy")
        cls.spaces = build_cross_section_spaces(
            cls.cross_section, transverse_degree=2
        )
        source_element = element(
            "N1curl",
            cls.source_mesh.basix_cell(),
            2,
            dtype=default_real_type,
        )
        cls.source_space = fem.functionspace(cls.source_mesh, source_element)

    def test_top_bottom_normals_are_explicit_opposites(self):
        bottom = interface_convention("bottom")
        top = interface_convention("top")
        self.assertEqual(bottom.z_nm, 10.0)
        self.assertEqual(top.z_nm, 110.0)
        self.assertEqual(bottom.local_fem_outward_normal_sign, +1)
        self.assertEqual(bottom.modal_outward_normal_sign, -1)
        self.assertEqual(top.local_fem_outward_normal_sign, -1)
        self.assertEqual(top.modal_outward_normal_sign, +1)
        values = np.asarray([[2.0 + 0.5j, -3.0 + 0.25j]])
        np.testing.assert_allclose(
            bottom.n_cross_tangential(values, domain="local_fem"),
            -bottom.n_cross_tangential(values, domain="modal"),
        )
        np.testing.assert_allclose(
            top.n_cross_tangential(values, domain="local_fem"),
            -top.n_cross_tangential(values, domain="modal"),
        )
        np.testing.assert_allclose(
            bottom.n_cross_tangential(values, domain="local_fem"),
            -top.n_cross_tangential(values, domain="local_fem"),
        )

    def test_affine_3d_nedelec_trace_matches_2d_reconstruction(self):
        source = fem.Function(self.source_space)

        def field(x):
            return np.vstack(
                (
                    1.0 + 0.25j + 0.02 * x[1] + 0.01 * x[2],
                    -0.4 + 0.15j + 0.03 * x[0] - 0.005 * x[2],
                    0.2 - 0.1j + 0.01 * x[0],
                )
            )

        source.interpolate(field)
        source.x.scatter_forward()
        extracted: dict[str, fem.Function] = {}
        for side in ("bottom", "top"):
            interface = build_matched_interface_trace(
                self.cfg,
                self.cross_section,
                self.spaces,
                self.source_mesh,
                side,
            )
            actual, report = extract_tangential_trace(source, interface)
            z_nm = interface.convention.z_nm
            expected = fem.Function(self.spaces.transverse)
            expected.interpolate(
                lambda x, z=z_nm: np.vstack(
                    (
                        1.0 + 0.25j + 0.02 * x[1] + 0.01 * z,
                        -0.4 + 0.15j + 0.03 * x[0] - 0.005 * z,
                    )
                )
            )
            expected.x.scatter_forward()
            self.assertEqual(
                interface.global_interface_facet_count,
                self.cross_section.mesh_cells[0] * self.cross_section.mesh_cells[1],
            )
            self.assertEqual(
                interface.global_middle_adjacent_cell_count,
                interface.global_interface_facet_count,
            )
            self.assertEqual(report.unresolved_points, 0)
            self.assertEqual(report.global_query_points, report.global_source_evaluations)
            self.assertFalse(report.field_vector_gathered)
            self.assertLess(
                _distributed_coefficient_relative_error(actual, expected), 1.0e-11
            )
            extracted[side] = actual

        # The physical E_t traces differ because the affine field depends on z;
        # orientation is represented explicitly by the convention, not by a
        # hidden sign applied to the canonical trace coefficients.
        self.assertGreater(
            _distributed_coefficient_relative_error(
                extracted["top"], extracted["bottom"]
            ),
            1.0e-3,
        )


class Task032ModalTraceProjectionTests(unittest.TestCase):
    def test_actual_near_degenerate_modes_round_trip_by_subspace(self):
        cfg = target_stage4_config(degree=2, h_nm=10.0)
        cross_section = build_matching_cross_section(cfg, "air")
        spaces = build_cross_section_spaces(cross_section, transverse_degree=2)
        operators = assemble_quadratic_beta_operators(cfg, cross_section, spaces)
        target = analytic_homogeneous_beta(cfg, cfg.n_air)
        right_modes, _ = solve_quadratic_beta_modes(
            operators, target=target, requested_modes=2
        )
        basis = build_biorthogonal_mode_basis(
            cfg,
            cross_section,
            spaces,
            operators,
            right_modes,
            adjoint_target=np.conj(target),
            requested_left_modes=2,
        )
        projection = None
        try:
            self.assertTrue(any(len(group.indices) == 2 for group in basis.groups))
            projection = ModalTraceProjection(spaces, basis)
            coefficients = np.asarray([0.7 + 0.2j, -0.3 + 0.4j])
            report = projection.round_trip(coefficients)
            self.assertLess(report.coefficient_relative_error, 1.0e-10)
            self.assertLess(report.trace_relative_residual, 1.0e-10)
            self.assertLess(report.gram_condition, 1.0e12)
            self.assertEqual(projection.reconstruction_shape[1], 2)
            self.assertEqual(projection.projection_shape[0], 2)
            self.assertEqual(projection.small_dense_shape, (2, 2))
            self.assertFalse(projection.full_vector_gathered)
            self.assertFalse(projection.dense_interface_operator_formed)

            unitary = np.asarray(
                [[1.0, 1.0j], [1.0j, 1.0]], dtype=np.complex128
            ) / np.sqrt(2.0)
            rotated: list[fem.Function] = []
            for column in range(2):
                field = fem.Function(spaces.transverse)
                field.x.array[:] = 0.0
                for row, original in enumerate(projection.right_traces):
                    field.x.array[:] += unitary[row, column] * original.x.array
                field.x.scatter_forward()
                rotated.append(field)
            subspace = trace_subspace_report(
                projection.mass, projection.right_traces, rotated
            )
            self.assertEqual(subspace.dimension, 2)
            self.assertLess(subspace.projector_error, 1.0e-7)
            self.assertLess(subspace.max_principal_angle_rad, 1.0e-7)
            # The first rotated vector is deliberately not the first original
            # vector, demonstrating why an individual-vector equality gate is
            # invalid for this near-degenerate block.
            self.assertGreater(
                _distributed_coefficient_relative_error(
                    rotated[0], projection.right_traces[0]
                ),
                1.0e-2,
            )
        finally:
            if projection is not None:
                projection.destroy()
            basis.destroy()
            operators.destroy()


if __name__ == "__main__":
    unittest.main()
