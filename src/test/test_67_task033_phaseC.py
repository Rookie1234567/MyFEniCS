from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from benchmarks.task033_phaseC import (
    build_phasec_preflight,
    build_phasec_summary_from_paths,
    full3d_p3_h5_phasec1_prediction,
    full3d_p3_h5_prediction,
    validate_preflight_for_candidate,
)


ROOT = Path(__file__).resolve().parents[2]
RESOURCE = (
    ROOT
    / "benchmarks"
    / "cases"
    / "091_hybrid_hp_adaptivity_feasibility"
    / "records"
    / "resource_matrix.json"
)
SHA = "a" * 40


class Task033PhaseCTest(unittest.TestCase):
    @staticmethod
    def _write_json(path: Path, payload: dict) -> Path:
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_full3d_factor_chain_veto_is_preserved(self) -> None:
        prediction = full3d_p3_h5_prediction()
        centers = prediction["centers_gib"]
        self.assertLess(centers["effective_p_over_h_power_law_gib"], 11.5)
        self.assertGreater(
            centers["assembled_nnz_fill_factor_payload_gib"], 11.5
        )
        self.assertGreater(prediction["conservative_upper_gib"], 12.8)
        self.assertGreater(prediction["projected_factor_nnz"], 500_000_000)

    def test_phasec1_exact_assembly_replaces_case090_nnz_transfer(self) -> None:
        old = full3d_p3_h5_prediction()
        exact = full3d_p3_h5_phasec1_prediction(
            {
                "status": "assembly_calibration_pass",
                "degree": 3,
                "h_nm": 5.0,
                "run_kind": "assembly-only",
                "mpi_size": 4,
                "no_swap": True,
                "qualification": {"pass": True},
                "calibration": {
                    "exact_rows": 145_943,
                    "exact_assembled_nnz": 35_566_727,
                    "factorization_or_solve_stage_seen": False,
                },
            }
        )
        self.assertEqual(exact["exact_rows"], 145_943)
        self.assertEqual(exact["exact_assembled_nnz"], 35_566_727)
        self.assertGreater(
            exact["exact_assembled_nnz"], old["projected_assembled_nnz"]
        )
        self.assertGreater(
            exact["centers_gib"][
                "exact_assembly_nnz_fill_factor_payload_gib"
            ],
            old["centers_gib"]["assembled_nnz_fill_factor_payload_gib"],
        )
        self.assertGreater(exact["conservative_upper_gib"], 19.0)
        self.assertIn(
            "not a proxy",
            " ".join(exact["limitations"]),
        )

    def test_preflight_blocks_full3d_but_keeps_hybrid_candidates(self) -> None:
        resource = json.loads(RESOURCE.read_text(encoding="utf-8"))
        record = build_phasec_preflight(
            resource,
            source_commit_full_sha=SHA,
            container_limit_bytes=14 * 1024**3,
            host_available_memory_bytes=20 * 1024**3,
            container_current_bytes=512 * 1024**2,
            container_swap_current_bytes=0,
            pswpin_pages=0,
            pswpout_pages=0,
        )
        self.assertEqual(
            record["status"],
            "full3d_memory_gated_hybrid_candidates_eligible",
        )
        self.assertFalse(
            record["qualification"]["full_phaseC_chain_launchable"]
        )
        self.assertTrue(
            record["qualification"]["hybrid_component_chain_launchable"]
        )
        decisions = {
            row["candidate_id"]: row["gate"]["decision"]
            for row in record["candidates"]
        }
        self.assertEqual(
            decisions["p3_h5_full3d_direct"], "not_run_by_memory_gate"
        )
        self.assertTrue(
            all(
                decision == "launch_eligible"
                for key, decision in decisions.items()
                if key != "p3_h5_full3d_direct"
            )
        )
        self.assertTrue(
            validate_preflight_for_candidate(
                record,
                candidate_id="p3_h5_schur_minimal_m160",
                source_commit_full_sha=SHA,
            )["pass"]
        )
        self.assertFalse(
            validate_preflight_for_candidate(
                record,
                candidate_id="p3_h5_full3d_direct",
                source_commit_full_sha=SHA,
            )["pass"]
        )

    def test_smaller_live_ceiling_scales_limits_without_widening(self) -> None:
        resource = json.loads(RESOURCE.read_text(encoding="utf-8"))
        record = build_phasec_preflight(
            resource,
            source_commit_full_sha=SHA,
            container_limit_bytes=13 * 1024**3,
            host_available_memory_bytes=20 * 1024**3,
            container_current_bytes=512 * 1024**2,
            container_swap_current_bytes=0,
            pswpin_pages=0,
            pswpout_pages=0,
        )
        self.assertLess(record["limits"]["two_center_limit_gib"], 11.5)
        self.assertLess(
            record["limits"]["conservative_upper_limit_gib"], 12.8
        )

    def test_aggregate_closes_only_hybrid_component(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            preflight = self._write_json(
                root / "preflight.json",
                {
                    "identity": {"source_commit_full_sha": SHA},
                    "qualification": {
                        "full3d_disposition": "not_run_by_memory_gate",
                        "hybrid_component_chain_launchable": True,
                    },
                },
            )
            funnel = self._write_json(
                root / "funnel.json",
                {
                    "status": "qualified",
                    "qualification": {"pass": True},
                    "comparisons": [],
                },
            )
            hybrid_paths = []
            for mode in (80, 120, 160):
                hybrid_paths.append(
                    self._write_json(
                        root / f"m{mode}.json",
                        {
                            "status": "measured_shard_pass",
                            "target": "hybrid",
                            "requested_modes": mode,
                            "memory_authority_pass": True,
                            "no_swap": True,
                            "terminated_for_memory": False,
                            "terminated_for_timeout": False,
                            "source": {"head_before_sha": SHA},
                            "resource_authority": {
                                "memory_authority_gib": 4.0
                            },
                        },
                    )
                )
            augmented = self._write_json(
                root / "augmented.json",
                {
                    "status": "measured_shard_pass",
                    "target": "hybrid",
                    "source": {"head_before_sha": SHA},
                    "resource_authority": {"memory_authority_gib": 5.0},
                    "measurements": {
                        "modal_schur_comparison": {
                            "gates": {
                                "rta": True,
                                "orders": True,
                                "selected_plane": True,
                            }
                        }
                    },
                },
            )
            record = build_phasec_summary_from_paths(
                preflight_path=preflight,
                funnel_path=funnel,
                hybrid_paths=hybrid_paths,
                augmented_path=augmented,
            )
        self.assertFalse(record["failures"])
        self.assertEqual(
            record["status"],
            "hybrid_component_closed_full3d_not_run_by_memory_gate",
        )
        self.assertFalse(record["identity"]["whole_phaseC_pass"])
        self.assertEqual(
            record["disposition"]["selected_plane_e_h_against_same_degree_full3d"],
            "not_available",
        )

    def test_aggregate_rejects_formal_not_pass_for_every_required_mode(self) -> None:
        for rejected_mode in (80, 120, 160):
            with self.subTest(rejected_mode=rejected_mode):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    preflight = self._write_json(
                        root / "preflight.json",
                        {
                            "identity": {"source_commit_full_sha": SHA},
                            "qualification": {
                                "full3d_disposition": "not_run_by_memory_gate",
                                "hybrid_component_chain_launchable": True,
                            },
                        },
                    )
                    funnel = self._write_json(
                        root / "funnel.json",
                        {"status": "qualified"},
                    )
                    hybrid_paths = [
                        self._write_json(
                            root / f"m{mode}.json",
                            {
                                "status": (
                                    "formal_not_pass"
                                    if mode == rejected_mode
                                    else "measured_shard_pass"
                                ),
                                "target": "hybrid",
                                "requested_modes": mode,
                                "memory_authority_pass": True,
                                "no_swap": True,
                                "terminated_for_memory": False,
                                "terminated_for_timeout": False,
                                "source": {"head_before_sha": SHA},
                            },
                        )
                        for mode in (80, 120, 160)
                    ]
                    augmented = self._write_json(
                        root / "augmented.json",
                        {
                            "status": "measured_shard_pass",
                            "target": "hybrid",
                            "source": {"head_before_sha": SHA},
                            "measurements": {
                                "modal_schur_comparison": {
                                    "gates": {"all": True}
                                }
                            },
                        },
                    )
                    record = build_phasec_summary_from_paths(
                        preflight_path=preflight,
                        funnel_path=funnel,
                        hybrid_paths=hybrid_paths,
                        augmented_path=augmented,
                    )
                self.assertIn(
                    "all_hybrid_watchdogs_measured", record["failures"]
                )
                self.assertEqual(record["status"], "phaseC_not_closed")

    def test_aggregate_rejects_mixed_source_sha(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            preflight = self._write_json(
                root / "preflight.json",
                {
                    "identity": {"source_commit_full_sha": SHA},
                    "qualification": {
                        "full3d_disposition": "not_run_by_memory_gate",
                        "hybrid_component_chain_launchable": True,
                    },
                },
            )
            funnel = self._write_json(
                root / "funnel.json",
                {"status": "qualified"},
            )
            hybrid_paths = [
                self._write_json(
                    root / f"m{mode}.json",
                    {
                        "status": "measured_shard_pass",
                        "target": "hybrid",
                        "requested_modes": mode,
                        "memory_authority_pass": True,
                        "no_swap": True,
                        "terminated_for_memory": False,
                        "terminated_for_timeout": False,
                        "source": {
                            "head_before_sha": "b" * 40
                            if mode == 120
                            else SHA
                        },
                    },
                )
                for mode in (80, 120, 160)
            ]
            augmented = self._write_json(
                root / "augmented.json",
                {
                    "status": "measured_shard_pass",
                    "target": "hybrid",
                    "source": {"head_before_sha": SHA},
                    "measurements": {
                        "modal_schur_comparison": {
                            "gates": {"all": True}
                        }
                    },
                },
            )
            record = build_phasec_summary_from_paths(
                preflight_path=preflight,
                funnel_path=funnel,
                hybrid_paths=hybrid_paths,
                augmented_path=augmented,
            )
        self.assertIn("one_same_clean_numerical_source", record["failures"])
        self.assertEqual(record["status"], "phaseC_not_closed")


if __name__ == "__main__":
    unittest.main()
