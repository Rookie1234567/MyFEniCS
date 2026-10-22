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
    TASK43_VOLUME_QUADRATURE_DEGREE,
    TASK43_VOLUME_QUADRATURE_RULE,
    task43_initial_profile,
    task43_profile_identity,
)
from src.common.modes_3d import outgoing_port_modes_3d
from src.geometry.mesh_builder_3d import stage4_axis_plan
from src.geometry.task43_hp_adaptivity_axis_plan import task43_axis_plan


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
        self.assertEqual(resolved["axis_plan"]["global_cell_count"], 180)
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


if __name__ == "__main__":
    unittest.main()
