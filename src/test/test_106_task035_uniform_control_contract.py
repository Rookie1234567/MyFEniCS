from __future__ import annotations

from argparse import Namespace
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from benchmarks.run_task035_actual_r5 import (
    _parse_args,
    _qualify_uniform,
)
from src.adaptivity.periodic_tetra_refinement import (
    refine_periodic_marked_tetra_mesh,
)
from src.adaptivity.target_uniform_tetra_control import _all_global_cell_ids
from src.common.config_3d import target_stage4_config
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d


def _uniform_result() -> dict:
    summary = {
        "official_result": True,
        "linear_system_relative_residual": 1.0e-12,
        "mesh_cell_type_actual": "tetrahedron",
    }
    return {
        "status": "actual_uniform_tetra_control_pass",
        "pass": True,
        "ordinary_default_changed": False,
        "refinement_levels": 2,
        "fixed_observable_reference": {
            "identity": "best_available_discrete_reference_for_case093",
            "record_sha256": "f5bad15f40ade652f6b4398e46852292ed323e3e5494b9fdb969c40bc6283111",
        },
        "refinements": [
            {"pass": True, "uniform_all_parent_cells_marked": True} for _ in range(2)
        ],
        "final_mesh_audit": {"pass": True},
        "actual_r5_pair": {
            "coarse": {"summary": summary},
            "enriched": {"summary": summary},
            "R5": {
                "correction_energy": {"relative_closure_error": 1.0e-14},
                "marking": {"captured_fraction": 0.51},
            },
        },
    }


class Task035UniformControlContractTests(unittest.TestCase):
    def test_uniform_and_adaptive_modes_are_mutually_exclusive(self) -> None:
        with self.assertRaises(SystemExit):
            _parse_args(
                [
                    "--mesh-cell-type",
                    "tetrahedron",
                    "--adaptive-marked-cycles",
                    "1",
                    "--uniform-refinement-levels",
                    "2",
                ]
            )

    def test_uniform_watchdog_qualification_is_fail_closed(self) -> None:
        args = Namespace(
            mpi_size=2,
            theta=0.5,
            uniform_refinement_levels=2,
        )
        sampler = {
            "max_observed_worker_rank_count": 2,
            "max_process_tree_swap_mb": 0.0,
        }
        result = _uniform_result()
        qualification = _qualify_uniform(
            result,
            args=args,
            return_code=0,
            terminated_for_memory=False,
            terminated_for_timeout=False,
            authority_readable=True,
            sampler=sampler,
        )
        self.assertTrue(qualification["pass"])
        result["refinements"][1]["uniform_all_parent_cells_marked"] = False
        failed = _qualify_uniform(
            result,
            args=args,
            return_code=0,
            terminated_for_memory=False,
            terminated_for_timeout=False,
            authority_readable=True,
            sampler=sampler,
        )
        self.assertFalse(failed["pass"])
        self.assertIn("all_parent_cells_uniformly_marked", failed["failures"])

    def test_two_uniform_levels_are_periodic_and_deterministic(self) -> None:
        cfg = replace(
            target_stage4_config(degree=2, h_nm=50.0),
            case_name="task035_uniform_control_fixture",
            mesh_cell_type="tetrahedron",
        )
        data = build_airbox_mesh_3d(
            cfg, Path(tempfile.mkdtemp(prefix="task035_uniform_fixture_"))
        )
        expected = {
            1440: "22204e1bdaef3321585f54d111ea1f8d070c0c202931817eb6d5b245a21891af",
            11520: "37d4f643572e77154af28b6c8dd69b8d31ceb40ee1a1ea5528ee9782199f28a8",
        }
        for expected_cells, expected_hash in expected.items():
            marked = _all_global_cell_ids(data.mesh)
            data, report = refine_periodic_marked_tetra_mesh(data, cfg, marked)
            self.assertTrue(report["pass"], report)
            self.assertEqual(report["parent_global_cells"], len(marked))
            self.assertEqual(report["refined_global_cells"], expected_cells)
            self.assertEqual(
                report["periodic_edge_closure"]["boundary_sleeve_edges_added"],
                0,
            )
            self.assertTrue(report["refined_mesh_audit"]["periodic_x"]["pass"])
            self.assertTrue(report["refined_mesh_audit"]["periodic_y"]["pass"])
            self.assertEqual(
                report["refined_mesh_audit"]["partition_independent_mesh_sha256"],
                expected_hash,
            )


if __name__ == "__main__":
    unittest.main()
