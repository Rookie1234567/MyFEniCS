from __future__ import annotations

from dataclasses import replace
import inspect
from pathlib import Path
import tempfile
import unittest

import numpy as np
from basix.ufl import element
from mpi4py import MPI

from dolfinx import default_real_type, fem

from src.common.analytic_fields_3d import electric_field_code_values
from src.common.config_3d import (
    oblique_incidence_airbox_config,
    target_stage4_config,
)
from src.constraints import floquet_3d_high_order
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.constraints.floquet_3d_high_order import build_high_order_constraint_data
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.solvers.common_3d_solve import _create_nedelec_space


def _fixture(degree: int, h_nm: float = 5.0):
    cfg = oblique_incidence_airbox_config(
        case_name=f"task033_fixture_a_p{degree}_h{h_nm:g}",
        stage_case="floquet_airbox",
        geometry_kind="airbox",
        lambda0=13.5,
        period_x=10.0,
        period_y=10.0,
        z_min=0.0,
        z_max=10.0,
        use_floquet_xy=True,
        use_pml=False,
        incident_theta_deg=37.0,
        incident_phi_deg=23.0,
        polarization_kind="s",
        custom_polarization=None,
        nedelec_degree=int(degree),
        visualization_degree=1,
        mesh_target_size=float(h_nm),
        mesh_cell_type="hexahedron",
        floquet_constraint_mode="auto",
    )
    out_dir = Path(tempfile.mkdtemp(prefix=f"task033_p{degree}_"))
    mesh_data = build_airbox_mesh_3d(cfg, out_dir)
    V = fem.functionspace(
        mesh_data.mesh,
        element(
            "N1curl",
            mesh_data.mesh.basix_cell(),
            degree,
            dtype=default_real_type,
        ),
    )
    return cfg, mesh_data, V


def _fixed_target_fixture(degree: int, h_nm: float = 50.0):
    cfg = replace(
        target_stage4_config(degree=degree, h_nm=h_nm),
        mesh_cell_type="hexahedron",
        matrix_diagnostics_assemble_only=True,
        unique_output=False,
    )
    out_dir = Path(tempfile.mkdtemp(prefix=f"task035b_p{degree}_"))
    mesh_data = build_airbox_mesh_3d(cfg, out_dir)
    V = fem.functionspace(
        mesh_data.mesh,
        element(
            "N1curl",
            mesh_data.mesh.basix_cell(),
            degree,
            dtype=default_real_type,
        ),
    )
    return cfg, mesh_data, V


def _global_owned_coefficients(function) -> dict[int, complex]:
    V = function.function_space
    index_map = V.dofmap.index_map
    block_size = V.dofmap.index_map_bs
    owned_blocks = np.arange(index_map.size_local, dtype=np.int32)
    global_blocks = index_map.local_to_global(owned_blocks).astype(np.int64)
    local: dict[int, complex] = {}
    for local_block, global_block in enumerate(global_blocks):
        for component in range(block_size):
            local_dof = local_block * block_size + component
            global_dof = int(global_block * block_size + component)
            local[global_dof] = complex(function.x.array[local_dof])
    merged: dict[int, complex] = {}
    for packet in V.mesh.comm.allgather(local):
        overlap = set(merged).intersection(packet)
        if overlap:
            raise RuntimeError(
                f"Owned coefficient packets overlap: {sorted(overlap)[:5]}"
            )
        merged.update(packet)
    return merged


class Task033HighOrderFloquetTopologyTests(unittest.TestCase):
    def test_production_builder_has_no_full_gather_or_dense_fit(self) -> None:
        source = inspect.getsource(floquet_3d_high_order)
        self.assertNotIn("allgather", source)
        self.assertNotIn("pinv", source)
        self.assertNotIn("lstsq", source)
        self.assertIn("distributed_match_periodic_records", source)
        self.assertIn("allreduce", source)

    def test_p1_to_p6_plane_wave_coefficients_satisfy_sparse_constraints(self) -> None:
        for degree in range(1, 7):
            with self.subTest(degree=degree):
                cfg, mesh_data, V = _fixture(degree)
                data = build_high_order_constraint_data(V, mesh_data, cfg)
                self.assertFalse(data.topology.used_full_boundary_gather)
                self.assertFalse(data.topology.created_dense_boundary_square)
                self.assertGreater(data.global_constraint_rows, 0)
                self.assertEqual(
                    data.global_constraint_rows,
                    data.num_edge_constraints + data.num_face_constraints,
                )
                # A partition-dependent Basix orientation can couple a trace
                # row.  For p5/p6 the quadrilateral face transform reaches
                # 2*(p-1) nonzeros, while edge transforms remain p-wide.
                transform_row_width = max(degree, 2 * (degree - 1))
                self.assertGreaterEqual(data.max_masters_per_slave, 1)
                self.assertLessEqual(
                    data.max_masters_per_slave, transform_row_width
                )
                self.assertLessEqual(
                    data.global_constraint_nnz,
                    data.global_constraint_rows * transform_row_width,
                )

                field = fem.Function(V)
                field.interpolate(lambda x: electric_field_code_values(cfg, x.T).T)
                field.x.scatter_forward()
                global_values = _global_owned_coefficients(field)
                max_error = 0.0
                for row, (slave_local, start, stop) in enumerate(
                    zip(
                        data.slave_local_dofs,
                        data.offsets[:-1],
                        data.offsets[1:],
                        strict=True,
                    )
                ):
                    masters = data.master_global_dofs[int(start) : int(stop)]
                    coefficients = data.coefficients[int(start) : int(stop)]
                    predicted = sum(
                        coefficient * global_values[int(master)]
                        for master, coefficient in zip(
                            masters, coefficients, strict=True
                        )
                    )
                    actual = complex(field.x.array[int(slave_local)])
                    max_error = max(max_error, abs(actual - predicted))
                    self.assertEqual(
                        int(data.slave_global_dofs[row]),
                        int(
                            V.dofmap.index_map.local_to_global(
                                np.asarray([int(slave_local)], dtype=np.int32)
                            )[0]
                        ),
                    )
                global_error = V.mesh.comm.allreduce(max_error, op=MPI.MAX)
                self.assertLessEqual(global_error, 2.0e-11)

    def test_second_angle_reuses_phase_independent_topology(self) -> None:
        cfg, mesh_data, V = _fixture(3)
        first = build_high_order_constraint_data(V, mesh_data, cfg)
        second_cfg = replace(
            cfg,
            incident_theta_deg=19.0,
            incident_phi_deg=41.0,
        )
        second = build_high_order_constraint_data(V, mesh_data, second_cfg)
        self.assertIs(first.topology, second.topology)
        self.assertTrue(second.topology_cache_hit)
        self.assertEqual(second.topology_build_seconds_current, 0.0)
        self.assertEqual(second.communication_bytes_sent_current, 0)
        self.assertEqual(second.communication_bytes_received_current, 0)
        local_coefficients_changed = not np.array_equal(
            first.coefficients, second.coefficients
        )
        self.assertTrue(V.mesh.comm.allreduce(local_coefficients_changed, op=MPI.LOR))
        for first_block, second_block in zip(
            first.topology.blocks, second.topology.blocks, strict=True
        ):
            self.assertIs(first_block, second_block)
            np.testing.assert_array_equal(
                first_block.coefficient_transform,
                second_block.coefficient_transform,
            )

    def test_non_exact_p4_trace_p6_interior_is_rejected(
        self,
    ) -> None:
        base_cfg, mesh_data, _ = _fixture(4)
        cfg = replace(
            base_cfg,
            nedelec_degree=6,
            nedelec_trace_degree=4,
            nedelec_interior_degree=6,
        )
        with self.assertRaisesRegex(
            ValueError,
            "qualified fixed-trace contract is p5 trace / p6 interior",
        ):
            _create_nedelec_space(mesh_data.mesh, cfg)

    def test_p1_to_p4_public_dispatcher_finalizes_sparse_mpc(self) -> None:
        for degree in range(1, 5):
            with self.subTest(degree=degree):
                cfg, mesh_data, V = _fixture(degree)
                result = build_double_floquet_mpc(V, mesh_data, cfg)
                expected_mode = (
                    "topological_edges_p1"
                    if degree == 1
                    else f"topological_trace_p{degree}"
                )
                self.assertEqual(
                    result.constraint_mode_resolved,
                    expected_mode,
                )
                self.assertGreater(result.num_constraints, 0)
                self.assertEqual(
                    result.num_constraints,
                    result.num_edge_constraints + result.num_face_constraints,
                )
                self.assertGreaterEqual(result.max_masters_per_slave, 1)
                self.assertLessEqual(result.max_masters_per_slave, degree)
                self.assertLessEqual(
                    result.raw_map_nnz,
                    result.num_constraints * degree,
                )
                self.assertFalse(result.used_full_boundary_gather)
                self.assertFalse(result.created_dense_boundary_square)
                self.assertEqual(result.num_face_transform_fits, 0)
                self.assertEqual(
                    result.orientation_factor_stats["mapping_kind"],
                    f"distributed_exact_{expected_mode}",
                )
                self.assertIsNotNone(result.phase_independent_topology)
                self.assertEqual(
                    result.phase_independent_topology.key.degree,
                    degree,
                )

    def test_fixed_target_hexa_p5_p6_public_dispatcher_is_sparse(self) -> None:
        for degree in (5, 6):
            with self.subTest(degree=degree):
                cfg, mesh_data, V = _fixed_target_fixture(degree)
                result = build_double_floquet_mpc(V, mesh_data, cfg)
                self.assertEqual(
                    result.constraint_mode_resolved,
                    f"topological_trace_p{degree}",
                )
                self.assertGreater(result.num_constraints, 0)
                self.assertFalse(result.used_full_boundary_gather)
                self.assertFalse(result.created_dense_boundary_square)
                self.assertEqual(result.num_face_transform_fits, 0)
                self.assertIsNotNone(result.phase_independent_topology)
                self.assertEqual(
                    result.phase_independent_topology.key.degree,
                    degree,
                )

    def test_generic_hexa_p5_remains_fail_closed(self) -> None:
        cfg, mesh_data, V = _fixture(5)
        with self.assertRaises(NotImplementedError):
            build_double_floquet_mpc(V, mesh_data, cfg)


if __name__ == "__main__":
    unittest.main()
