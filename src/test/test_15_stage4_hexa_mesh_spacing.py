from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from src.adaptivity.high_order_resource_audit import (
    partition_independent_linear_mesh_identity,
)
from src.common.config_3d import target_stage4_config
from src.geometry.mesh_builder_3d import _rank_cell_ids, _stage4_axis_plan, build_airbox_mesh_3d
from src.geometry.tetra_mesh_audit import (
    canonical_owned_cell_ids,
    geometry_key_sha256,
)
from src.test.stage2_test_utils import stage4_block_config


def _axis_sha256(values: np.ndarray) -> str:
    encoded = json.dumps(
        [float(value) for value in values],
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _max_spacing_inside(values: np.ndarray, low: float, high: float) -> float:
    widths = np.diff(values)
    mids = 0.5 * (values[:-1] + values[1:])
    selected = widths[(mids >= low) & (mids <= high)]
    if len(selected) == 0:
        raise AssertionError(f"No mesh intervals were found inside [{low}, {high}].")
    return float(np.max(selected))


class Stage4HexaMeshSpacingTests(unittest.TestCase):
    def test_exact_axis_counts_preserve_default_and_freeze_x_y_identities(
        self,
    ):
        default_cfg = target_stage4_config(degree=6, h_nm=15.0)
        self.assertIsNone(default_cfg.mesh_axis_cell_counts_requested)
        self.assertIsNone(default_cfg.mesh_axis_z_values_requested)
        self.assertIsNone(default_cfg.mesh_axis_z_profile)
        default_plan = _stage4_axis_plan(default_cfg, comm_size=8)
        self.assertEqual(default_plan.mesh_cells_resolved, (6, 2, 10))
        self.assertEqual(
            {
                "x": _axis_sha256(default_plan.x_values),
                "y": _axis_sha256(default_plan.y_values),
                "z": _axis_sha256(default_plan.z_values),
            },
            {
                "x": "86dc23ef348c79d9ed51d79c199cbaddf95416e04c51e5569c666234c6613cc3",
                "y": "d3aac691ebe8875dc45e5817b42b4f33c45277f999f2d010fd29fecd7ec1401f",
                "z": "f5aef6ea431298d9ebb46c16f2b674faf765046d3705d8b32dda6a2244bd6464",
            },
        )

        cases = {
            (7, 2, 10): {
                "axis_sha256": {
                    "x": "f99cf720acdbd78d426ef4f36cb22c0944de3a6b23f744750d48a51d85d342cd",
                    "y": "d3aac691ebe8875dc45e5817b42b4f33c45277f999f2d010fd29fecd7ec1401f",
                    "z": "f5aef6ea431298d9ebb46c16f2b674faf765046d3705d8b32dda6a2244bd6464",
                },
                "mesh_sha256": "326019d01cf2b98a83422e9c0aa520795daaa5bbc1fdeb73d567799504c705b1",
                "cell_tag_sha256": "1434790f1ba5bb102c57561dd9a925f8f6f46aa4ebcb7c37194e205ee2e3d11c",
                "facet_tag_sha256": "d2fa4745b79663b1838fa51473545f3b8290b0ed17212c28d162e27ae0e6c693",
                "geometry_sha256": "7bef1e3c0339f1cea57edc01219eceb0c2b5df266864bc3d6d18373ad2ee4342",
            },
            (6, 3, 10): {
                "axis_sha256": {
                    "x": "86dc23ef348c79d9ed51d79c199cbaddf95416e04c51e5569c666234c6613cc3",
                    "y": "d7841480e80baeda07536ebc44681af4488f7d61a2eaa7de4d33cdacb9fa19fb",
                    "z": "f5aef6ea431298d9ebb46c16f2b674faf765046d3705d8b32dda6a2244bd6464",
                },
                "mesh_sha256": "59d053ac70baaa80c6de82fcd2388d0076291f033cf074197c218055756eec8f",
                "cell_tag_sha256": "60209a26ca68027775dc54783cc44a67314804ced204928025d35607c4d999e0",
                "facet_tag_sha256": "270b60e1c061cd539e64219e349e29abe0deb6e414c35c979abb25e2660b9c75",
                "geometry_sha256": "e33f27c8967255bb8b1a8df556789fed1d408e95477f6d9cba44b9890a3f3c34",
            },
        }
        with tempfile.TemporaryDirectory(
            prefix="stage4_exact_axis_",
        ) as temp_dir:
            for counts, expected in cases.items():
                cfg = target_stage4_config(degree=6, h_nm=15.0)
                cfg.mesh_axis_cell_counts = counts
                plan = _stage4_axis_plan(cfg, comm_size=8)
                self.assertEqual(
                    plan.mesh_spacing_mode_resolved,
                    "boundary_fitted_exact_counts",
                )
                self.assertEqual(plan.mesh_cells_resolved, counts)
                self.assertTrue(
                    plan.material_plane_alignment["all_aligned"]
                )
                self.assertEqual(
                    {
                        "x": _axis_sha256(plan.x_values),
                        "y": _axis_sha256(plan.y_values),
                        "z": _axis_sha256(plan.z_values),
                    },
                    expected["axis_sha256"],
                )
                mesh_data = build_airbox_mesh_3d(
                    cfg,
                    Path(temp_dir) / "x".join(str(value) for value in counts),
                )
                identity = partition_independent_linear_mesh_identity(
                    mesh_data
                )
                self.assertEqual(
                    identity["partition_independent_mesh_sha256"],
                    expected["mesh_sha256"],
                )
                self.assertEqual(
                    identity["cell_tag_sha256"],
                    expected["cell_tag_sha256"],
                )
                self.assertEqual(
                    identity["facet_tag_sha256"],
                    expected["facet_tag_sha256"],
                )
                _ids, _rows, keys = canonical_owned_cell_ids(
                    mesh_data.mesh
                )
                self.assertEqual(
                    geometry_key_sha256(keys),
                    expected["geometry_sha256"],
                )

    def test_explicit_z_identity_preserves_h14_except_one_bisect(
        self,
    ):
        parent_cfg = target_stage4_config(degree=6, h_nm=14.0)
        parent = _stage4_axis_plan(parent_cfg, comm_size=8)
        expected_z = list(parent.z_values)
        expected_z.insert(
            2,
            0.5 * (float(parent.z_values[1]) + float(parent.z_values[2])),
        )
        cfg = target_stage4_config(degree=6, h_nm=14.0)
        cfg.mesh_axis_cell_counts = (6, 2, 12)
        cfg.mesh_axis_z_values = tuple(expected_z)
        cfg.mesh_axis_z_profile = "fixed_rectangular_h14_bisect_control"
        plan = _stage4_axis_plan(cfg, comm_size=8)

        self.assertEqual(
            plan.mesh_spacing_mode_resolved,
            "boundary_fitted_exact_counts_explicit_z",
        )
        self.assertEqual(plan.mesh_cells_resolved, (6, 2, 12))
        self.assertEqual(list(plan.x_values), list(parent.x_values))
        self.assertEqual(list(plan.y_values), list(parent.y_values))
        self.assertEqual(list(plan.z_values), expected_z)
        self.assertEqual(
            _axis_sha256(plan.z_values),
            "9048a25cdb01a0ef2aa123bc5f7ec66116a2320ed42376e63ec22679e5f3c6d8",
        )
        self.assertTrue(plan.material_plane_alignment["all_aligned"])

    def test_exact_axis_counts_fail_closed(self):
        cfg = target_stage4_config(degree=6, h_nm=15.0)
        cfg.mesh_axis_cell_counts = (1, 2, 10)
        with self.assertRaisesRegex(ValueError, "at least two x and y"):
            _stage4_axis_plan(cfg, comm_size=8)

        cfg.mesh_axis_cell_counts = (6, 2, 2)
        with self.assertRaisesRegex(ValueError, "material interval"):
            _stage4_axis_plan(cfg, comm_size=8)

        cfg.mesh_axis_cell_counts = (2, 2, 3)
        with self.assertRaisesRegex(ValueError, "fewer cells than MPI"):
            _stage4_axis_plan(cfg, comm_size=13)

        cfg.mesh_axis_cell_counts = (7, 2, 10)
        cfg.mesh_spacing_mode = "local_refined"
        with self.assertRaisesRegex(ValueError, "requires mesh_spacing_mode"):
            _stage4_axis_plan(cfg, comm_size=8)

        cfg.mesh_spacing_mode = "auto"
        cfg.mesh_cell_type = "tetrahedron"
        with self.assertRaisesRegex(ValueError, "Stage-4 hexahedra"):
            _stage4_axis_plan(cfg, comm_size=8)

        cfg.mesh_cell_type = "hexahedron"
        cfg.mesh_axis_cell_counts = (7, 2, 10.0)
        with self.assertRaisesRegex(ValueError, "three integers"):
            _stage4_axis_plan(cfg, comm_size=8)

        cfg.mesh_axis_cell_counts = 7
        with self.assertRaisesRegex(ValueError, "three integers"):
            _stage4_axis_plan(cfg, comm_size=8)

        cfg.mesh_axis_cell_counts = (7, 0, 10)
        with self.assertRaisesRegex(ValueError, "positive"):
            _stage4_axis_plan(cfg, comm_size=8)

        cfg = target_stage4_config(degree=6, h_nm=14.0)
        cfg.mesh_axis_z_values = (-10.0, 0.0, 120.0, 130.0)
        with self.assertRaisesRegex(
            ValueError,
            "must be supplied together",
        ):
            _stage4_axis_plan(cfg, comm_size=8)

        cfg.mesh_axis_z_profile = "h14_max-R5_slab_bisect"
        with self.assertRaisesRegex(
            ValueError,
            "requires mesh_axis_cell_counts",
        ):
            _stage4_axis_plan(cfg, comm_size=8)

        cfg.mesh_axis_cell_counts = (6, 2, 12)
        with self.assertRaisesRegex(ValueError, "length must equal"):
            _stage4_axis_plan(cfg, comm_size=8)

        cfg.mesh_axis_z_values = (
            -9.0,
            0.0,
            6.0,
            13.0,
            26.0,
            40.0,
            53.0,
            66.0,
            80.0,
            93.0,
            106.0,
            120.0,
            130.0,
        )
        with self.assertRaisesRegex(ValueError, "endpoints must equal"):
            _stage4_axis_plan(cfg, comm_size=8)

        cfg.mesh_axis_z_values = (-10.0, 0.0, 0.0, 130.0)
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            _stage4_axis_plan(cfg, comm_size=8)

    def test_auto_keeps_uniform_when_material_planes_align(self):
        cfg = stage4_block_config(
            use_pml=False,
            pml_top_thickness=0.0,
            pml_bottom_thickness=0.0,
            mesh_target_size=5.0,
            mesh_spacing_mode="auto",
        )
        plan = _stage4_axis_plan(cfg, comm_size=1)

        self.assertEqual(plan.mesh_spacing_mode_resolved, "uniform_strict")
        self.assertTrue(plan.material_plane_alignment["all_aligned"])
        self.assertEqual(plan.mesh_cells_resolved, (20, 20, 30))
        self.assertAlmostEqual(plan.axis_cell_stats["x"]["min"], 5.0)
        self.assertAlmostEqual(plan.axis_cell_stats["x"]["max"], 5.0)

    def test_auto_fits_material_planes_when_target_does_not_align(self):
        cfg = stage4_block_config(
            use_pml=False,
            pml_top_thickness=0.0,
            pml_bottom_thickness=0.0,
            mesh_target_size=6.0,
            mesh_spacing_mode="auto",
        )
        plan = _stage4_axis_plan(cfg, comm_size=1)

        self.assertEqual(plan.mesh_spacing_mode_resolved, "boundary_fitted")
        self.assertTrue(plan.material_plane_alignment["all_aligned"])
        for value in (cfg.grating_x_min, cfg.grating_x_max):
            self.assertTrue(np.any(np.isclose(plan.x_values, value)))
        for value in (cfg.grating_y_min, cfg.grating_y_max):
            self.assertTrue(np.any(np.isclose(plan.y_values, value)))
        for value in (cfg.interface_z, cfg.grating_z_max):
            self.assertTrue(np.any(np.isclose(plan.z_values, value)))

    def test_uniform_strict_still_rejects_nonaligned_material_planes(self):
        cfg = stage4_block_config(
            use_pml=False,
            pml_top_thickness=0.0,
            pml_bottom_thickness=0.0,
            mesh_target_size=6.0,
            mesh_spacing_mode="uniform_strict",
        )

        with self.assertRaisesRegex(ValueError, "uniform_strict"):
            _stage4_axis_plan(cfg, comm_size=1)

    def test_local_refined_uses_small_cells_near_grating_and_coarse_cells_away(self):
        cfg = stage4_block_config(
            use_pml=False,
            pml_top_thickness=0.0,
            pml_bottom_thickness=0.0,
            mesh_target_size=20.0,
            mesh_spacing_mode="local_refined",
            mesh_refined_size=2.5,
            mesh_refinement_radius=5.0,
        )
        plan = _stage4_axis_plan(cfg, comm_size=1)

        self.assertEqual(plan.mesh_spacing_mode_resolved, "local_refined")
        self.assertTrue(plan.material_plane_alignment["all_aligned"])
        x_region = plan.local_refinement_regions["x"][0]
        y_region = plan.local_refinement_regions["y"][0]
        z_region = plan.local_refinement_regions["z"][0]
        self.assertLessEqual(_max_spacing_inside(plan.x_values, *x_region), 2.5 + 1.0e-12)
        self.assertLessEqual(_max_spacing_inside(plan.y_values, *y_region), 2.5 + 1.0e-12)
        self.assertLessEqual(_max_spacing_inside(plan.z_values, *z_region), 2.5 + 1.0e-12)
        self.assertGreaterEqual(plan.axis_cell_stats["x"]["max"], 10.0)

    def test_boundary_fitted_plan_builds_a_dolfinx_hexa_mesh(self):
        cfg = stage4_block_config(
            use_pml=False,
            pml_top_thickness=0.0,
            pml_bottom_thickness=0.0,
            mesh_target_size=30.0,
            mesh_spacing_mode="auto",
        )
        mesh_data = build_airbox_mesh_3d(cfg, Path(tempfile.mkdtemp(prefix="stage4_mesh_spacing_")))

        self.assertEqual(mesh_data.mesh_spacing_mode_resolved, "boundary_fitted")
        self.assertTrue(mesh_data.material_plane_alignment["all_aligned"])
        self.assertEqual(mesh_data.mesh_cell_type_resolved, "hexahedron")
        self.assertIn("hexahedron", str(mesh_data.mesh.basix_cell()).lower())

    def test_custom_hexa_mpi_cell_slices_are_disjoint_and_complete(self):
        total_cells = 137
        size = 8
        ids = [cell_id for rank in range(size) for cell_id in _rank_cell_ids(total_cells, rank, size)]

        self.assertEqual(ids, list(range(total_cells)))
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
