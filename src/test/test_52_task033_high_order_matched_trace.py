from __future__ import annotations

import unittest

import numpy as np
from basix.ufl import element
from dolfinx import default_real_type, fem
from mpi4py import MPI

from src.common.config_3d import target_stage4_config
from src.coupling.modal_trace_projection import (
    build_matched_interface_trace,
    extract_tangential_trace,
)
from src.geometry.mesh_builder_3d import _structured_hexa_mesh, stage4_axis_plan
from src.modes.cross_section_spaces import (
    build_cross_section_spaces,
    build_matching_cross_section,
)


def _coefficient_relative_error(actual: fem.Function, expected: fem.Function) -> float:
    index_map = actual.function_space.dofmap.index_map
    owned = int(index_map.size_local * actual.function_space.dofmap.index_map_bs)
    difference = actual.x.array[:owned] - expected.x.array[:owned]
    local_num = float(np.vdot(difference, difference).real)
    local_den = float(
        np.vdot(expected.x.array[:owned], expected.x.array[:owned]).real
    )
    numerator = actual.function_space.mesh.comm.allreduce(local_num, op=MPI.SUM)
    denominator = actual.function_space.mesh.comm.allreduce(local_den, op=MPI.SUM)
    return float(np.sqrt(numerator / max(denominator, 1.0e-30)))


class Task033HighOrderMatchedTraceTests(unittest.TestCase):
    def test_p1_p5_bottom_top_trace_and_normal_contract(self) -> None:
        for degree in (1, 2, 3, 4, 5):
            with self.subTest(degree=degree):
                cfg = target_stage4_config(degree=degree, h_nm=10.0)
                plan = stage4_axis_plan(cfg, MPI.COMM_WORLD.size)
                source_mesh = _structured_hexa_mesh(
                    MPI.COMM_WORLD,
                    plan.x_values,
                    plan.y_values,
                    plan.z_values,
                )
                cross_section = build_matching_cross_section(cfg, "stage4_xy")
                spaces = build_cross_section_spaces(
                    cross_section, transverse_degree=degree
                )
                source_space = fem.functionspace(
                    source_mesh,
                    element(
                        "N1curl",
                        source_mesh.basix_cell(),
                        degree,
                        dtype=default_real_type,
                    ),
                )
                source = fem.Function(source_space)

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
                conventions = []
                for side in ("bottom", "top"):
                    interface = build_matched_interface_trace(
                        cfg,
                        cross_section,
                        spaces,
                        source_mesh,
                        side,
                    )
                    actual, report = extract_tangential_trace(source, interface)
                    z_nm = interface.convention.z_nm
                    expected = fem.Function(spaces.transverse)
                    expected.interpolate(
                        lambda x, z=z_nm: np.vstack(
                            (
                                1.0 + 0.25j + 0.02 * x[1] + 0.01 * z,
                                -0.4 + 0.15j + 0.03 * x[0] - 0.005 * z,
                            )
                        )
                    )
                    expected.x.scatter_forward()
                    self.assertLess(
                        _coefficient_relative_error(actual, expected), 2.0e-11
                    )
                    self.assertEqual(report.unresolved_points, 0)
                    self.assertEqual(
                        report.global_query_points,
                        report.global_source_evaluations,
                    )
                    self.assertFalse(report.field_vector_gathered)
                    conventions.append(interface.convention)
                self.assertEqual(
                    conventions[0].local_fem_outward_normal_sign,
                    -conventions[1].local_fem_outward_normal_sign,
                )
                self.assertEqual(
                    conventions[0].modal_outward_normal_sign,
                    -conventions[1].modal_outward_normal_sign,
                )


if __name__ == "__main__":
    unittest.main()
