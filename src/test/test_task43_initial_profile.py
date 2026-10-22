from __future__ import annotations

import unittest
from itertools import product

import numpy as np
from mpi4py import MPI

from benchmarks.task43_hp_adaptivity.profile import (
    TASK43_MODE_COUNT,
    TASK43_PORT_BOUNDARY_AMPLITUDE_SCALE_POLICY,
    TASK43_PORT_QUADRATURE_DEGREE,
    TASK43_R13_MAX_M,
    TASK43_R13_MAX_N,
    TASK43_RAW_TENSOR_BACKEND,
    TASK43_SPARSE_CUTOFF_POLICY,
    TASK43_VARIABLE_P_ACTIVE_FE_DOF_GATE_POLICY,
    TASK43_VOLUME_QUADRATURE_DEGREE,
    TASK43_VOLUME_QUADRATURE_RULE,
    task43_initial_profile,
    task43_profile_identity,
)
from src.common.modes_3d import outgoing_port_modes_3d
from src.geometry.mesh_builder_3d import stage4_axis_plan
from src.geometry.task43_hp_adaptivity_axis_plan import (
    TASK43_AXES_NM,
    task43_axis_plan,
)


class Task43InitialProfileTests(unittest.TestCase):
    def test_profile_closes_exact_geometry_and_numeric_controls(self) -> None:
        cfg = task43_initial_profile()
        axes = stage4_axis_plan(cfg, MPI.COMM_WORLD.size)
        modes = outgoing_port_modes_3d(cfg)
        identity = task43_profile_identity(cfg, modes)

        self.assertEqual(axes.mesh_cells_resolved, (3, 10, 6))
        self.assertEqual(
            tuple(float(value) for value in axes.x_values),
            tuple(task43_axis_plan()["axes_nm"]["x"]),
        )
        self.assertEqual(
            tuple(float(value) for value in axes.y_values),
            tuple(task43_axis_plan()["axes_nm"]["y"]),
        )
        self.assertEqual(
            tuple(float(value) for value in axes.z_values),
            tuple(task43_axis_plan()["axes_nm"]["z"]),
        )
        self.assertTrue(axes.material_plane_alignment["all_aligned"])
        self.assertEqual(
            (
                cfg.grating_x_min,
                cfg.grating_x_max,
                cfg.grating_y_min,
                cfg.grating_y_max,
                cfg.grating_z_min,
                cfg.grating_z_max,
            ),
            (16.5, 33.5, 15.0, 35.0, 0.0, 120.0),
        )
        self.assertEqual(cfg.stage4_dtn_rectangle_max_m, TASK43_R13_MAX_M)
        self.assertEqual(cfg.stage4_dtn_rectangle_max_n, TASK43_R13_MAX_N)
        self.assertEqual(cfg.stage4_dtn_quadrature_degree, TASK43_PORT_QUADRATURE_DEGREE)
        self.assertEqual(cfg.stage4_incident_quadrature_degree, TASK43_PORT_QUADRATURE_DEGREE)
        self.assertEqual(cfg.stage4_volume_quadrature_degree, TASK43_VOLUME_QUADRATURE_DEGREE)
        self.assertEqual(cfg.stage4_volume_quadrature_rule, TASK43_VOLUME_QUADRATURE_RULE)
        self.assertEqual(cfg.stage4_dtn_sparse_cutoff_policy, TASK43_SPARSE_CUTOFF_POLICY)
        self.assertEqual(cfg.stage4_dtn_sparse_cutoff_relative_tolerance, 1.0e-13)
        self.assertEqual(
            cfg.stage4_port_boundary_amplitude_scale_policy,
            TASK43_PORT_BOUNDARY_AMPLITUDE_SCALE_POLICY,
        )
        self.assertEqual(
            cfg.stage4_variable_p_raw_tensor_backend,
            TASK43_RAW_TENSOR_BACKEND,
        )
        self.assertEqual(
            cfg.stage4_variable_p_geometry_identity_policy,
            "raw_unrounded",
        )
        self.assertEqual(
            cfg.stage4_variable_p_active_fe_dof_gate_policy,
            TASK43_VARIABLE_P_ACTIVE_FE_DOF_GATE_POLICY,
        )
        expected_mode_keys = {
            key
            for key in product(
                ("bottom", "top"),
                range(-TASK43_R13_MAX_M, TASK43_R13_MAX_M + 1),
                range(-TASK43_R13_MAX_N, TASK43_R13_MAX_N + 1),
                ("p", "s"),
            )
        }
        resolved = identity["resolved"]
        mode_identity = resolved["mode_selection"]
        self.assertEqual(len(modes), TASK43_MODE_COUNT)
        self.assertEqual(mode_identity["mode_count"], TASK43_MODE_COUNT)
        actual_mode_keys = {
            tuple(key) for key in mode_identity["mode_keys"]
        }
        self.assertEqual(actual_mode_keys, expected_mode_keys)
        self.assertEqual(
            len(mode_identity["mode_keys"]),
            TASK43_MODE_COUNT,
        )
        self.assertEqual(resolved["lambda0_nm"], cfg.lambda0)
        self.assertEqual(
            identity["expected_contract"]["lambda0_nm"],
            resolved["lambda0_nm"],
        )
        self.assertEqual(
            resolved["material_indices"]["substrate"],
            [cfg.substrate_index.real, cfg.substrate_index.imag],
        )
        self.assertEqual(
            resolved["material_indices"]["grating"],
            [cfg.grating_index.real, cfg.grating_index.imag],
        )
        self.assertEqual(
            resolved["incidence"]["amplitude"],
            [cfg.incident_amplitude.real, cfg.incident_amplitude.imag],
        )
        self.assertEqual(
            resolved["incidence"]["direction_vector"],
            [float(value) for value in cfg.direction_vector],
        )
        np.testing.assert_allclose(
            resolved["incidence"]["direction_vector"],
            identity["expected_contract"]["incidence"]["direction_vector"],
            rtol=0.0,
            atol=1.0e-15,
        )
        self.assertEqual(
            resolved["incidence"]["polarization_vector"],
            [[value.real, value.imag] for value in cfg.polarization_vector],
        )
        np.testing.assert_allclose(
            resolved["incidence"]["polarization_vector"],
            identity["expected_contract"]["incidence"]["polarization_vector"],
            rtol=0.0,
            atol=1.0e-15,
        )
        self.assertEqual(
            resolved["base_axis_plan"]["axes_nm"]["x"],
            list(TASK43_AXES_NM["x"]),
        )
        self.assertIsNone(resolved["actual_mesh"]["axes_nm"])
        self.assertIsNone(resolved["actual_mesh"]["global_cell_count"])
        self.assertEqual(
            identity["expected_contract"]["active_fe_dof_gate_policy"],
            TASK43_VARIABLE_P_ACTIVE_FE_DOF_GATE_POLICY,
        )
        self.assertEqual(
            identity["resource_profile"]["identity"],
            "task43_hp_adaptivity_resource_v1",
        )
        self.assertEqual(
            identity["resource_profile"]["resources"]["absolute_cap_bytes"],
            192 * 1024**3,
        )
        self.assertEqual(
            resolved["quadrature_degree"],
            {"volume": 15, "incident": 28, "ports": 28},
        )
        self.assertEqual(
            identity["expected_contract"]["quadrature_rule"],
            {"volume": "default"},
        )
        self.assertEqual(
            resolved["quadrature_rule"],
            {"volume": "default"},
        )
        self.assertEqual(
            resolved["port_basis_scaling"]["policy"],
            TASK43_PORT_BOUNDARY_AMPLITUDE_SCALE_POLICY,
        )
        self.assertEqual(
            resolved["variable_p_raw_tensor_backend"],
            TASK43_RAW_TENSOR_BACKEND,
        )
        self.assertTrue(
            any(mode.boundary_amplitude_scale != 1.0 for mode in modes)
        )
        np.testing.assert_allclose(
            [mode.boundary_amplitude_scale for mode in modes],
            np.exp([mode.boundary_amplitude_log_scale for mode in modes]),
            rtol=2.0e-14,
            atol=0.0,
        )

    def test_profile_identity_tracks_resolved_mode_window(self) -> None:
        cfg = task43_initial_profile()
        cfg.stage4_dtn_rectangle_max_m = TASK43_R13_MAX_M + 1
        cfg.stage4_dtn_rectangle_max_n = TASK43_R13_MAX_N + 1
        modes = outgoing_port_modes_3d(cfg)

        identity = task43_profile_identity(cfg, modes)
        resolved_modes = identity["resolved"]["mode_selection"]

        self.assertEqual(len(modes), 836)
        self.assertEqual(resolved_modes["mode_count"], 836)
        self.assertEqual(resolved_modes["rectangle_max_m"], 5)
        self.assertEqual(resolved_modes["rectangle_max_n"], 9)
        self.assertNotEqual(
            resolved_modes["mode_inventory_sha256"],
            task43_profile_identity(
                task43_initial_profile(),
                outgoing_port_modes_3d(task43_initial_profile()),
            )["resolved"]["mode_selection"]["mode_inventory_sha256"],
        )

    def test_actual_mesh_axes_and_leaf_count_are_not_their_cartesian_product(self):
        cfg = task43_initial_profile()
        modes = outgoing_port_modes_3d(cfg)
        # One root cell is bisected in x/y/z.  The global union axes therefore
        # describe a larger Cartesian integration partition than the 187-leaf
        # local forest actually contains.
        actual_axes = {
            "x": [0.0, 8.25, 16.5, 33.5, 50.0],
            "y": [0.0, 2.5, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 50.0],
            "z": [-10.0, -5.0, 0.0, 30.0, 60.0, 90.0, 120.0, 130.0],
        }
        identity = task43_profile_identity(
            cfg,
            modes,
            resolved_axes_nm=actual_axes,
            resolved_mesh_audit={
                "global_cell_count": 187,
                "leaf_cell_count": 187,
            },
        )
        mesh = identity["resolved"]["actual_mesh"]
        self.assertEqual(mesh["axes_nm"], actual_axes)
        self.assertEqual(mesh["global_cell_count"], 187)
        self.assertEqual(mesh["leaf_cell_count"], 187)
        self.assertEqual(
            mesh["common_cartesian_partition_cell_counts_xyz"],
            {"x": 4, "y": 11, "z": 7},
        )
        self.assertEqual(mesh["common_cartesian_partition_cell_count"], 308)
        self.assertEqual(
            identity["resolved"]["base_axis_plan"]["axes_nm"]["x"],
            list(TASK43_AXES_NM["x"]),
        )

    def test_mesh_counts_require_resolved_axes(self):
        cfg = task43_initial_profile()
        modes = outgoing_port_modes_3d(cfg)
        with self.assertRaisesRegex(ValueError, "actual resolved mesh axes"):
            task43_profile_identity(
                cfg,
                modes,
                resolved_mesh_audit={"global_cell_count": 180},
            )


if __name__ == "__main__":
    unittest.main()
