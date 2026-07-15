from __future__ import annotations

import unittest
from types import SimpleNamespace

import numpy as np
from dolfinx import fem
from petsc4py import PETSc

from src.common.config_3d import target_stage4_config
from src.coupling.hybrid_internal_modes import build_hybrid_internal_mode_coupling
from src.modes.cross_section_spaces import (
    build_cross_section_spaces,
    build_matching_cross_section,
)
from src.solvers.hybrid_local_dtn import assemble_hybrid_local_dtn_system


class Task033HighOrderHybridComponentTests(unittest.TestCase):
    def test_p3_p4_sparse_matching_interface_blocks(self) -> None:
        for degree in (3, 4):
            with self.subTest(degree=degree):
                cfg = target_stage4_config(degree=degree, h_nm=10.0)
                cross_section = build_matching_cross_section(cfg, "stage4_xy")
                spaces = build_cross_section_spaces(
                    cross_section, transverse_degree=degree
                )
                target = np.sqrt(
                    (cfg.k0 * complex(cfg.n_air)) ** 2
                    - cfg.kx**2
                    - cfg.ky**2
                    + 0.0j
                )
                vectors: list[PETSc.Vec] = []

                def synthetic_mode(component: int, beta: complex, direction: str):
                    trace = fem.Function(spaces.transverse)

                    def field(x):
                        phase = np.exp(1j * (cfg.kx * x[0] + cfg.ky * x[1]))
                        values = np.zeros(
                            (2, x.shape[1]), dtype=PETSc.ScalarType
                        )
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
                    vectors.append(vector)
                    return SimpleNamespace(
                        beta=complex(beta),
                        right=SimpleNamespace(right_full=vector),
                        left_full=vector,
                        direction=direction,
                        passive_branch_valid=True,
                    )

                positive = SimpleNamespace(
                    modes=[
                        synthetic_mode(0, target, "forward"),
                        synthetic_mode(1, target, "forward"),
                    ]
                )
                negative = SimpleNamespace(
                    modes=[
                        synthetic_mode(0, -target, "backward"),
                        synthetic_mode(1, -target, "backward"),
                    ]
                )
                bottom = assemble_hybrid_local_dtn_system(cfg, "bottom")
                top = assemble_hybrid_local_dtn_system(cfg, "top")
                coupling = None
                try:
                    coupling = build_hybrid_internal_mode_coupling(
                        cfg,
                        spaces,
                        positive,
                        negative,
                        bottom,
                        top,
                    )
                    self.assertEqual(coupling.mode_count_per_direction, 2)
                    self.assertEqual(coupling.internal_unknown_count, 4)
                    self.assertLess(
                        coupling.positive_projection_identity_error, 1.0e-9
                    )
                    self.assertEqual(
                        coupling.interface_quadrature_degree, 2 * degree + 4
                    )
                    self.assertEqual(
                        coupling.bottom.quadrature_degree,
                        coupling.top.quadrature_degree,
                    )
                    self.assertFalse(coupling.full_field_or_mode_gathered)
                    self.assertFalse(coupling.dense_interface_square_formed)
                    self.assertFalse(
                        bottom.floquet_data.used_full_boundary_gather
                    )
                    self.assertFalse(top.floquet_data.used_full_boundary_gather)
                    self.assertFalse(
                        bottom.floquet_data.created_dense_boundary_square
                    )
                    self.assertFalse(
                        top.floquet_data.created_dense_boundary_square
                    )
                    self.assertEqual(
                        coupling.bottom.local_fem_outward_normal_sign,
                        -coupling.top.local_fem_outward_normal_sign,
                    )
                    np.testing.assert_allclose(
                        coupling.negative_trace_to_positive,
                        np.eye(2),
                        atol=1.0e-9,
                        rtol=1.0e-9,
                    )
                    for matrix in (
                        coupling.bottom.projection,
                        coupling.top.projection,
                        coupling.bottom.positive_traction,
                        coupling.top.positive_traction,
                    ):
                        self.assertGreater(float(matrix.norm()), 0.0)
                finally:
                    if coupling is not None:
                        coupling.destroy()
                    for system in (bottom, top):
                        system.A.destroy()
                        system.b.destroy()
                    for vector in vectors:
                        vector.destroy()


if __name__ == "__main__":
    unittest.main()
