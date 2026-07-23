from __future__ import annotations

from dataclasses import replace
from itertools import permutations
from pathlib import Path
import tempfile
import unittest

import numpy as np

from src.adaptivity.periodic_tetra_refinement import (
    _canonical_positive_tetra_coordinates,
    _contiguous_partition_owner,
    close_periodic_marked_cells,
    refine_periodic_marked_tetra_mesh,
)
from src.common.config_3d import target_stage4_config
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.geometry.tetra_mesh_audit import (
    audit_periodic_tetra_mesh,
    mesh_coordinate_tolerance,
    owned_tetra_cell_geometry,
)


def _target_mesh_data():
    cfg = replace(
        target_stage4_config(degree=2, h_nm=50.0),
        case_name="task035_periodic_tetra_refinement_fixture",
        mesh_cell_type="tetrahedron",
    )
    out_dir = Path(tempfile.mkdtemp(prefix="task035_tetra_refinement_"))
    return cfg, build_airbox_mesh_3d(cfg, out_dir)


def _canonical_x_min_cell(mesh_data, cfg) -> int:
    msh = mesh_data.mesh
    tolerance = mesh_coordinate_tolerance(msh)
    local_candidates = []
    for record in owned_tetra_cell_geometry(msh, tolerance=tolerance):
        on_x_min = np.count_nonzero(
            np.isclose(
                record.coordinates[:, 0],
                cfg.x_min,
                atol=tolerance,
                rtol=0.0,
            )
        )
        if on_x_min >= 3:
            local_candidates.append((record.key, record.global_index))
    candidates = [
        candidate
        for packet in msh.comm.allgather(local_candidates)
        for candidate in packet
    ]
    if not candidates:
        raise RuntimeError("target fixture has no x-min boundary tetrahedron")
    return int(min(candidates, key=lambda item: item[0])[1])


class Task035PeriodicTetraRefinementTests(unittest.TestCase):
    def test_positive_orientation_is_canonical_across_all_input_orders(self) -> None:
        coordinates = np.asarray(
            (
                (0.0, 0.0, 0.0),
                (1.0, 0.0, 0.0),
                (0.0, 1.0, 0.0),
                (0.0, 0.0, 1.0),
            )
        )
        outputs = []
        for order in permutations(range(4)):
            canonical, _ = _canonical_positive_tetra_coordinates(
                coordinates[np.asarray(order)], tolerance=1.0e-12
            )
            determinant = np.linalg.det(
                np.column_stack(
                    (
                        canonical[1] - canonical[0],
                        canonical[2] - canonical[0],
                        canonical[3] - canonical[0],
                    )
                )
            )
            self.assertGreater(determinant, 0.0)
            outputs.append(canonical)
        for output in outputs[1:]:
            np.testing.assert_array_equal(output, outputs[0])

    def test_contiguous_partition_owner_has_exact_rank_blocks(self) -> None:
        owners = [
            _contiguous_partition_owner(
                index,
                global_count=10,
                partition_count=3,
            )
            for index in range(10)
        ]
        self.assertEqual(owners, [0, 0, 0, 1, 1, 1, 2, 2, 2, 2])
        with self.assertRaises(ValueError):
            _contiguous_partition_owner(-1, global_count=10, partition_count=3)
        with self.assertRaises(ValueError):
            _contiguous_partition_owner(10, global_count=10, partition_count=3)
        with self.assertRaises(ValueError):
            _contiguous_partition_owner(0, global_count=0, partition_count=3)

    def test_target_tetra_audit_is_orientation_and_partition_strict(self) -> None:
        cfg, mesh_data = _target_mesh_data()
        audit = audit_periodic_tetra_mesh(
            mesh_data.mesh,
            mesh_data.cell_tags,
            mesh_data.facet_tags,
            cfg,
        )
        self.assertEqual(
            audit["partition_independent_mesh_sha256"],
            "67478577ac6a06120df59fbd7b73620b8241faa2fb3890dc98245da6006ee824",
        )
        self.assertTrue(audit["pass"])
        self.assertEqual(audit["global_cell_count"], 180)
        self.assertEqual(audit["orientation"]["nonpositive_count"], 0)
        self.assertGreater(
            audit["orientation"]["determinant_quantiles"]["minimum"], 0.0
        )
        self.assertGreater(audit["shape_quality"]["quantiles"]["minimum"], 0.0)
        self.assertTrue(audit["periodic_x"]["pass"])
        self.assertTrue(audit["periodic_y"]["pass"])

    def test_periodic_closure_and_marked_refinement_pass(self) -> None:
        cfg, mesh_data = _target_mesh_data()
        marked = [_canonical_x_min_cell(mesh_data, cfg)]
        closure = close_periodic_marked_cells(mesh_data.mesh, cfg, marked)
        self.assertEqual(closure["status"], "pass")
        self.assertEqual(closure["initial_count"], 1)
        self.assertGreater(closure["periodic_mates_added"], 0)
        refined, report = refine_periodic_marked_tetra_mesh(mesh_data, cfg, marked)
        self.assertEqual(
            closure["closed_geometry_sha256"],
            "2b4fa13e795819392b8243bbda48b7c59fce1c2d593c9122785c5ed24a8a27fd",
        )
        self.assertEqual(
            report["refined_mesh_audit"]["partition_independent_mesh_sha256"],
            "65c11dbeb106e9f080a7bdce6cab1452de6cc54bc1c9a60710d6f54a7729b0ac",
        )
        self.assertTrue(report["pass"], report)
        self.assertEqual(report["periodic_edge_closure"]["status"], "pass")
        self.assertGreater(
            report["orientation_rebuild"]["input_negative_oriented_cell_count"],
            0,
        )
        for rebuild_name in ("serial_rebuild", "orientation_rebuild"):
            rebuild = report[rebuild_name]
            self.assertTrue(rebuild["canonical_positive_vertex_ordering"])
            self.assertEqual(len(rebuild["canonical_connectivity_sha256"]), 64)
            self.assertEqual(rebuild["partitioner"], "canonical_contiguous_v1")
            self.assertEqual(
                rebuild["partition_owner_rule"],
                "ceil((global_cell_index+1)*mpi_size/N)-1",
            )
            self.assertEqual(
                rebuild["partition_ghost_rule"],
                "official_incoming_dual_graph_owner_destinations",
            )
            self.assertTrue(rebuild["partition_graph_replication"])
            self.assertEqual(
                sum(rebuild["owned_cell_counts_by_rank"]),
                rebuild["reconstructed_global_cell_count"],
            )

        self.assertGreater(report["refined_global_cells"], 180)
        self.assertTrue(report["refined_mesh_audit"]["pass"])
        self.assertEqual(
            report["periodic_closure"]["closed_geometry_sha256"],
            closure["closed_geometry_sha256"],
        )
        for tag in (cfg.tags.air, cfg.tags.substrate, cfg.tags.grating):
            self.assertGreater(
                report["refined_mesh_audit"]["cell_tag_counts"][str(tag)], 0
            )
        self.assertEqual(refined.mesh.topology.cell_type.name, "tetrahedron")
        second_marked = [_canonical_x_min_cell(refined, cfg)]
        refined_twice, second_report = refine_periodic_marked_tetra_mesh(
            refined, cfg, second_marked
        )
        self.assertTrue(second_report["pass"], second_report)
        self.assertTrue(
            second_report["periodic_edge_closure"][
                "full_periodic_boundary_synchronization"
            ]
        )
        self.assertEqual(
            second_report["refined_mesh_audit"]["partition_independent_mesh_sha256"],
            "f4c0533e59ae45e308c1c2ca2904d88975226fcaae2b245fe6c241e44fa349fc",
        )
        self.assertEqual(refined_twice.mesh.topology.cell_type.name, "tetrahedron")


if __name__ == "__main__":
    unittest.main()
