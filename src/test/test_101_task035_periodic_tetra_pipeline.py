from __future__ import annotations

from dataclasses import replace
import tempfile
from pathlib import Path
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
from src.constraints.floquet_3d_high_order import (
    build_high_order_constraint_data,
)
from src.constraints.high_order_floquet_trace import (
    tetrahedral_trace_layout,
    triangle_face_basis_transform,
    triangle_face_coefficient_transform,
    triangle_s3_vertex_permutations,
)
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d


def _space(mesh_data, degree: int):
    return fem.functionspace(
        mesh_data.mesh,
        element(
            "N1curl",
            mesh_data.mesh.basix_cell(),
            degree,
            dtype=default_real_type,
        ),
    )


def _global_owned_coefficients(function) -> dict[int, complex]:
    space = function.function_space
    index_map = space.dofmap.index_map
    block_size = space.dofmap.index_map_bs
    owned_blocks = np.arange(index_map.size_local, dtype=np.int32)
    global_blocks = index_map.local_to_global(owned_blocks).astype(np.int64)
    local = {
        int(global_block * block_size + component): complex(
            function.x.array[local_block * block_size + component]
        )
        for local_block, global_block in enumerate(global_blocks)
        for component in range(block_size)
    }
    merged: dict[int, complex] = {}
    for packet in space.mesh.comm.allgather(local):
        if set(merged).intersection(packet):
            raise RuntimeError("owned coefficient packets overlap")
        merged.update(packet)
    return merged


def _constraint_error(space, cfg, data) -> float:
    field = fem.Function(space)
    field.interpolate(lambda x: electric_field_code_values(cfg, x.T).T)
    field.x.scatter_forward()
    global_values = _global_owned_coefficients(field)
    local_error = 0.0
    for slave_local, start, stop in zip(
        data.slave_local_dofs,
        data.offsets[:-1],
        data.offsets[1:],
        strict=True,
    ):
        predicted = sum(
            coefficient * global_values[int(master)]
            for master, coefficient in zip(
                data.master_global_dofs[int(start) : int(stop)],
                data.coefficients[int(start) : int(stop)],
                strict=True,
            )
        )
        local_error = max(
            local_error,
            abs(complex(field.x.array[int(slave_local)]) - predicted),
        )
    return float(space.mesh.comm.allreduce(local_error, op=MPI.MAX))


def _minimum_oriented_jacobian(mesh_data) -> tuple[float, int]:
    msh = mesh_data.mesh
    cell_map = msh.topology.index_map(msh.topology.dim)
    minimum = float("inf")
    nonpositive = 0
    for cell in range(cell_map.size_local):
        points = msh.geometry.x[msh.geometry.dofmap[cell]][:4]
        jacobian = np.column_stack(
            (points[1] - points[0], points[2] - points[0], points[3] - points[0])
        )
        determinant = float(np.linalg.det(jacobian))
        minimum = min(minimum, determinant)
        nonpositive += determinant <= 0.0
    return (
        float(msh.comm.allreduce(minimum, op=MPI.MIN)),
        int(msh.comm.allreduce(nonpositive, op=MPI.SUM)),
    )


class Task035PeriodicTetraPipelineTests(unittest.TestCase):
    def test_tetra_trace_layout_and_s3_transforms_are_basix_bound(self) -> None:
        expected = {
            1: (6, 1, 0, 0, 3),
            2: (20, 2, 2, 0, 8),
            3: (45, 3, 6, 3, 15),
            4: (84, 4, 12, 12, 24),
            5: (140, 5, 20, 30, 35),
            6: (216, 6, 30, 60, 48),
        }
        for degree, values in expected.items():
            layout = tetrahedral_trace_layout(degree)
            self.assertEqual(
                (
                    layout.tetrahedron_dimension,
                    layout.edge_dofs,
                    layout.face_interior_dofs,
                    layout.cell_interior_dofs,
                    layout.face_trace_dofs,
                ),
                values,
            )
            self.assertEqual(
                layout.face_trace_dofs,
                layout.triangle_n1curl_dimension,
            )
        mapping = triangle_s3_vertex_permutations()
        self.assertEqual(len(mapping), 6)
        for degree in range(2, 7):
            for permutation, face_info in mapping.items():
                np.testing.assert_allclose(
                    triangle_face_coefficient_transform(degree, permutation),
                    triangle_face_basis_transform(degree, face_info).T,
                    atol=1.0e-14,
                )

    def test_periodic_tetra_p1_p2_plane_wave_trace_identity(self) -> None:
        for degree in (1, 2):
            cfg = oblique_incidence_airbox_config(
                case_name=f"task035_periodic_tetra_p{degree}",
                stage_case="floquet_airbox",
                geometry_kind="airbox",
                lambda0=13.5,
                period_x=10.0,
                period_y=10.0,
                z_min=0.0,
                z_max=10.0,
                use_floquet_xy=True,
                incident_theta_deg=37.0,
                incident_phi_deg=23.0,
                polarization_kind="s",
                custom_polarization=None,
                nedelec_degree=degree,
                mesh_target_size=5.0,
                mesh_cell_type="tetrahedron",
                floquet_constraint_mode="auto",
            )
            out_dir = Path(tempfile.mkdtemp(prefix=f"task035_tetra_p{degree}_"))
            mesh_data = build_airbox_mesh_3d(cfg, out_dir)
            space = _space(mesh_data, degree)
            data = build_high_order_constraint_data(space, mesh_data, cfg)
            self.assertGreater(data.global_constraint_rows, 0)
            self.assertEqual(
                data.global_constraint_rows,
                data.num_edge_constraints + data.num_face_constraints,
            )
            self.assertLessEqual(_constraint_error(space, cfg, data), 2.0e-11)

    def test_target_tetra_mesh_has_exact_tags_and_positive_orientation(self) -> None:
        cfg = replace(
            target_stage4_config(degree=2, h_nm=50.0),
            mesh_cell_type="tetrahedron",
        )
        out_dir = Path(tempfile.mkdtemp(prefix="task035_target_tetra_"))
        mesh_data = build_airbox_mesh_3d(cfg, out_dir)
        self.assertEqual(mesh_data.mesh_cell_type_resolved, "tetrahedron")
        self.assertTrue(mesh_data.material_plane_alignment["all_aligned"])
        for tag in (cfg.tags.air, cfg.tags.substrate, cfg.tags.grating):
            count = mesh_data.mesh.comm.allreduce(
                len(mesh_data.cell_tags.find(tag)), op=MPI.SUM
            )
            self.assertGreater(count, 0)
        for left, right in (
            (cfg.tags.x_min, cfg.tags.x_max),
            (cfg.tags.y_min, cfg.tags.y_max),
        ):
            left_count = mesh_data.mesh.comm.allreduce(
                len(mesh_data.facet_tags.find(left)), op=MPI.SUM
            )
            right_count = mesh_data.mesh.comm.allreduce(
                len(mesh_data.facet_tags.find(right)), op=MPI.SUM
            )
            self.assertGreater(left_count, 0)
            self.assertEqual(left_count, right_count)
        minimum, nonpositive = _minimum_oriented_jacobian(mesh_data)
        self.assertGreater(minimum, 0.0)
        self.assertEqual(nonpositive, 0)
        space = _space(mesh_data, 2)
        data = build_high_order_constraint_data(space, mesh_data, cfg)
        self.assertLessEqual(_constraint_error(space, cfg, data), 2.0e-11)


if __name__ == "__main__":
    unittest.main()
