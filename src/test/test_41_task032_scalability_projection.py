from __future__ import annotations

import json
import unittest
from pathlib import Path

from benchmarks.run_task032_scalability_projection import build_projection


ROOT = Path(__file__).resolve().parents[2]


class Task032ScalabilityProjectionTests(unittest.TestCase):
    def _record(self) -> dict:
        return build_projection(
            wavelength_nm=0.7,
            period_x_nm=50.0,
            period_y_nm=25.0,
            local_thickness_nm=20.0,
            mesh_target_nm=0.1,
            mode_safety_factor=3.7,
            mpi_size=4,
        )

    def test_projection_is_deterministic_and_never_a_solver_pass(self) -> None:
        first = self._record()
        second = self._record()
        self.assertEqual(
            json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True)
        )
        self.assertEqual(first["record_type"], "analytical_resource_projection")
        self.assertFalse(first["identity"]["is_pde_run"])
        self.assertFalse(first["identity"]["is_solver_pass"])
        self.assertNotIn("status", first)

    def test_generic_mode_and_uniform_local_row_scaling(self) -> None:
        record = self._record()
        modal = record["generic_2d_modal_estimate"]
        uniform = record["uniform_grid_estimates"]
        self.assertGreater(modal["two_polarization_modes_per_direction_lower_bound"], 16_000)
        self.assertGreater(modal["retained_modes_per_direction_after_safety_factor"], 59_000)
        self.assertEqual(
            modal["internal_modal_amplitudes_2m"],
            2 * modal["retained_modes_per_direction_after_safety_factor"],
        )
        self.assertEqual(uniform["local_fe_rows"], 923_346_000)
        self.assertEqual(
            uniform["local_system_rows_mechanical_proxy"], 924_426_000
        )
        self.assertFalse(
            uniform["external_fourier_dtn_auxiliary_count_projected"]
        )
        self.assertFalse(
            record["optional_current_geometry_diagnostic"][
                "allowed_for_future_service_budget"
            ]
        )

    def test_invalid_inputs_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            build_projection(
                wavelength_nm=0.0,
                period_x_nm=50.0,
                period_y_nm=25.0,
                local_thickness_nm=20.0,
                mesh_target_nm=0.1,
                mode_safety_factor=3.7,
                mpi_size=4,
            )

    def test_checked_in_projection_matches_the_script(self) -> None:
        path = (
            ROOT
            / "docs"
            / "task032_hybrid_fem_modal_direct_baseline"
            / "outcomes"
            / "task032_0p7nm_projection.json"
        )
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), self._record())


if __name__ == "__main__":
    unittest.main()
