"""Contracts for the Task035 SHA-bound common-mesh angle sweep."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from mpi4py import MPI

from src.adaptivity.target_common_mesh_angle_sweep import (
    _evaluate_hp_budget,
    build_replayed_common_mesh,
    load_common_mesh_replay_contract,
)


ROOT = Path(__file__).resolve().parents[2]
AUTHORITY = (
    ROOT
    / "benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records"
    / (
        "actual_dwr_r_adaptive_tetra_p4_p5_h50_theta0p7_cycle1_"
        "full_periodic_closure_mpi8.json"
    )
)
AUTHORITY_SHA256 = "ca21d21ccbb9d7ed79b8be3d0b99153f59e77b414ae754a284d47a26ee0e900f"
SWEEP_RECORD = (
    ROOT
    / "benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records"
    / "actual_common_mesh_grazing_1_5_10_p4_p5_h50_mpi8.json"
)
SWEEP_RECORD_SHA256 = (
    "18a58264aa8508a5687a1b0a94a5c6a07c870a1dcb18ddd05cd0a0e4cc6744c0"
)
THETA03_AUTHORITY = (
    ROOT
    / "benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records"
    / "actual_dwr_r_adaptive_tetra_p3_p4_h50_theta0p3_cycle1_mpi8.json"
)
THETA03_AUTHORITY_SHA256 = (
    "2dfab0433836c347d317497b60ec83e33c868507d8f1a4f6fa3b45c0277d0010"
)
HP_FAILURE_RECORD = (
    ROOT
    / "benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records"
    / "actual_hp_budget_theta0p3_tetra_p5_p6_h50_mpi8.json"
)
HP_RECOVERY_RECORD = (
    ROOT
    / "benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records"
    / "actual_hp_budget_theta0p3_tetra_p5_p6_h50_mpi8_recovered.json"
)
THETA04_AUTHORITY = (
    ROOT
    / "benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records"
    / (
        "actual_dwr_r_adaptive_tetra_p4_p5_h50_theta0p4_cycle1_"
        "full_periodic_closure_mpi8.json"
    )
)
THETA04_AUTHORITY_SHA256 = "cf45f2fa22492ff5870158a3a8fc33ac01a8ba0487273a7987dd580d0b9c2468"


class Task035CommonMeshAngleSweepTests(unittest.TestCase):
    def test_replay_authority_is_sha_bound_and_complete(self) -> None:
        contract = load_common_mesh_replay_contract(
            AUTHORITY,
            expected_sha256=AUTHORITY_SHA256,
        )
        self.assertEqual(contract["source_sha"], "c2898da89b055f0e6a13df3f039c6a0c24942d04")
        self.assertEqual(contract["theta"], 0.7)
        self.assertEqual(contract["marker_policy"], "R_total")
        self.assertEqual(contract["marked_count"], 72)
        self.assertEqual(contract["initial_mesh_identity"]["global_cell_count"], 180)
        self.assertEqual(contract["final_mesh_identity"]["global_cell_count"], 1316)
        self.assertEqual(contract["source_mpi_size"], 8)

    def test_legacy_theta03_authority_is_explicitly_bound(self) -> None:
        contract = load_common_mesh_replay_contract(
            THETA03_AUTHORITY,
            expected_sha256=THETA03_AUTHORITY_SHA256,
            expected_theta=0.3,
            expected_final_cells=1200,
        )
        self.assertEqual(contract["source_sha"], "6c4b2aee9d7ef2673a66996540c5022defd270a9")
        self.assertEqual(contract["theta"], 0.3)
        self.assertEqual(contract["marked_count"], 23)
        self.assertEqual(contract["final_mesh_identity"]["global_cell_count"], 1200)
        with self.assertRaisesRegex(ValueError, "requested_theta"):
            load_common_mesh_replay_contract(
                THETA03_AUTHORITY,
                expected_sha256=THETA03_AUTHORITY_SHA256,
                expected_theta=0.7,
                expected_final_cells=1200,
            )

    def test_hp_budget_requires_both_dof_and_full_observable_accuracy(self) -> None:
        summary = {
            "num_nedelec_dofs": 161700,
            "R_total": 0.0007663133771040101,
            "T_total": 0.602677530502972,
            "A_volume_total": 0.3965561561199801,
        }
        angle_results = [
            {
                "grazing_angle_deg": 10.0,
                "actual_r5_pair": {
                    "enriched": {
                        "degree": 6,
                        "summary": summary,
                    },
                },
            }
        ]
        evaluation = _evaluate_hp_budget(
            angle_results,
            dof_ceiling=169946,
            accuracy_control_key="p4_h7p5",
        )
        self.assertTrue(evaluation["pass"])
        self.assertGreater(evaluation["candidate"]["dof_saving_fraction"], 0.5)
        summary["T_total"] = 0.61
        failed = _evaluate_hp_budget(
            angle_results,
            dof_ceiling=169946,
            accuracy_control_key="p4_h7p5",
        )
        self.assertFalse(failed["pass"])
        self.assertFalse(
            failed["checks"]["observable_vector_error_no_worse_than_control"]
        )

    def test_theta03_p6_failure_is_preserved_and_recovery_recomputes(self) -> None:
        record = json.loads(HP_RECOVERY_RECORD.read_bytes())
        self.assertEqual(record["status"], "controlled_negative")
        self.assertFalse(record["recovery"]["pde_rerun"])
        self.assertFalse(record["recovery"]["thresholds_relaxed"])
        self.assertEqual(
            hashlib.sha256(HP_FAILURE_RECORD.read_bytes()).hexdigest(),
            record["failure_record"]["sha256"],
        )
        candidate = record["candidate_p6"]
        evaluation = _evaluate_hp_budget(
            [
                {
                    "grazing_angle_deg": 10.0,
                    "actual_r5_pair": {
                        "enriched": {
                            "degree": candidate["degree"],
                            "summary": {
                                "num_nedelec_dofs": candidate[
                                    "num_nedelec_dofs"
                                ],
                                "R_total": candidate["R_total"],
                                "T_total": candidate["T_total"],
                                "A_volume_total": candidate["A_volume_total"],
                            },
                        }
                    },
                }
            ],
            dof_ceiling=record["evaluation"]["dof_ceiling"],
            accuracy_control_key=record["accuracy_control"]["key"],
        )
        self.assertEqual(evaluation["checks"], record["evaluation"]["checks"])
        self.assertFalse(evaluation["pass"])

    def test_theta04_authority_has_a_sub_half_p6_dof_preflight(self) -> None:
        payload = THETA04_AUTHORITY.read_bytes()
        self.assertEqual(hashlib.sha256(payload).hexdigest(), THETA04_AUTHORITY_SHA256)
        record = json.loads(payload)
        self.assertEqual(record["status"], "actual_dwr_adaptive_cycles_pass")
        self.assertTrue(record["qualification"]["pass"])
        self.assertEqual(
            record["source"]["commit_sha"],
            "e2162663fdfea49756c6ddf00f21b20e0372be1d",
        )
        self.assertEqual(record["theta_schedule"], [0.4])
        self.assertEqual(record["cycles"][0]["marker"]["kind"], "R_total")
        self.assertEqual(record["cycles"][0]["marker"]["marked_count"], 38)
        final_cycle = record["cycles"][1]
        cells = final_cycle["mesh_audit"]["global_cell_count"]
        p4_dofs = final_cycle["coarse"]["num_nedelec_dofs"]
        p5_dofs = final_cycle["enriched"]["num_nedelec_dofs"]
        self.assertEqual((cells, p4_dofs, p5_dofs), (1248, 55072, 101210))
        edge_plus_three_faces = (p4_dofs - 12 * cells) // 4
        edge_plus_four_faces = (p5_dofs - 30 * cells) // 5
        faces = edge_plus_four_faces - edge_plus_three_faces
        edges = edge_plus_three_faces - 3 * faces
        self.assertEqual((edges, faces), (1834, 2730))
        p6_dofs = 6 * edges + 30 * faces + 60 * cells
        self.assertEqual(p6_dofs, 167784)
        reference_dofs = 339892
        self.assertLessEqual(p6_dofs, reference_dofs // 2)
        self.assertGreaterEqual(1.0 - p6_dofs / reference_dofs, 0.5)

    def test_replay_authority_rejects_wrong_hash(self) -> None:
        with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
            load_common_mesh_replay_contract(
                AUTHORITY,
                expected_sha256="0" * 64,
            )

    def test_replay_refuses_partition_dependent_ids_at_wrong_mpi_size(self) -> None:
        if MPI.COMM_WORLD.size == 8:
            self.skipTest("wrong-MPI-size negative applies outside MPI8")
        with self.assertRaisesRegex(RuntimeError, "requires the authority MPI size 8"):
            build_replayed_common_mesh(
                Path(tempfile.gettempdir()) / "task035-common-mesh-wrong-mpi",
                replay_record=AUTHORITY,
                replay_record_sha256=AUTHORITY_SHA256,
            )

    @unittest.skipUnless(
        MPI.COMM_WORLD.size == 8,
        "accepted compact marker authority requires MPI8",
    )
    def test_replayed_mesh_matches_accepted_final_identity(self) -> None:
        directory = MPI.COMM_WORLD.bcast(
            tempfile.mkdtemp(prefix="task035-common-mesh-")
            if MPI.COMM_WORLD.rank == 0
            else None,
            root=0,
        )
        try:
            mesh_data, mesh_cfg, replay = build_replayed_common_mesh(
                Path(directory),
                replay_record=AUTHORITY,
                replay_record_sha256=AUTHORITY_SHA256,
                coarse_degree=4,
                h_nm=50.0,
                polarization_kind="s",
            )
        finally:
            MPI.COMM_WORLD.barrier()
            if MPI.COMM_WORLD.rank == 0:
                shutil.rmtree(directory)
        self.assertTrue(replay["pass"])
        self.assertEqual(
            replay["final_mesh_audit"]["partition_independent_mesh_sha256"],
            replay["contract"]["final_mesh_identity"][
                "partition_independent_mesh_sha256"
            ],
        )
        self.assertEqual(
            replay["final_mesh_audit"]["cell_tag_sha256"],
            replay["contract"]["final_mesh_identity"]["cell_tag_sha256"],
        )
        self.assertEqual(
            replay["final_mesh_audit"]["facet_tag_sha256"],
            replay["contract"]["final_mesh_identity"]["facet_tag_sha256"],
        )
        self.assertEqual(
            mesh_data.mesh.topology.index_map(mesh_data.mesh.topology.dim).size_global,
            1316,
        )
        self.assertEqual(mesh_cfg.mesh_cell_type, "tetrahedron")
        self.assertTrue(replay["single_in_memory_mesh_instance"])
        self.assertFalse(replay["ordinary_default_changed"])

    @unittest.skipUnless(
        MPI.COMM_WORLD.size == 8,
        "accepted compact marker authority requires MPI8",
    )
    def test_replayed_theta03_mesh_matches_accepted_final_identity(self) -> None:
        directory = MPI.COMM_WORLD.bcast(
            tempfile.mkdtemp(prefix="task035-common-mesh-theta03-")
            if MPI.COMM_WORLD.rank == 0
            else None,
            root=0,
        )
        try:
            mesh_data, _, replay = build_replayed_common_mesh(
                Path(directory),
                replay_record=THETA03_AUTHORITY,
                replay_record_sha256=THETA03_AUTHORITY_SHA256,
                coarse_degree=5,
                h_nm=50.0,
                polarization_kind="s",
                replay_expected_theta=0.3,
                replay_expected_final_cells=1200,
            )
        finally:
            MPI.COMM_WORLD.barrier()
            if MPI.COMM_WORLD.rank == 0:
                shutil.rmtree(directory)
        self.assertTrue(replay["pass"])
        self.assertEqual(
            replay["final_mesh_audit"]["partition_independent_mesh_sha256"],
            "5e3a6eb874c0b577a19a50f19f574b6c55930c88e0b1aa671463e9ddf1e7f87a",
        )
        self.assertEqual(
            replay["final_mesh_audit"]["cell_tag_sha256"],
            "5d9f511275f2107bb402dca18a7e03714125f23775b142b3d0dfe01164054b5f",
        )
        self.assertEqual(
            replay["final_mesh_audit"]["facet_tag_sha256"],
            "d1a04a4e450b671506c662ed7a8e47cccb92e902e01c0d1b92141ed3d5c075aa",
        )
        self.assertEqual(
            mesh_data.mesh.topology.index_map(mesh_data.mesh.topology.dim).size_global,
            1200,
        )

    def test_formal_mpi8_common_mesh_record_and_negative_boundary(self) -> None:
        payload = SWEEP_RECORD.read_bytes()
        self.assertEqual(hashlib.sha256(payload).hexdigest(), SWEEP_RECORD_SHA256)
        record = json.loads(payload)
        self.assertEqual(record["status"], "actual_common_mesh_angle_sweep_pass")
        self.assertTrue(record["qualification"]["pass"])
        self.assertEqual(record["qualification"]["failures"], [])
        self.assertEqual(
            record["source"]["commit_sha"],
            "782d9d1527796a4cae15255c630a02b69ff02f5c",
        )
        self.assertTrue(record["source"]["stable_and_clean_after"])
        self.assertEqual(record["resource_authority"]["max_observed_worker_rank_count"], 8)
        self.assertEqual(record["resource_authority"]["max_process_tree_swap_mb"], 0.0)
        self.assertTrue(record["warning_triggered"])
        self.assertFalse(record["terminated_for_memory"])
        self.assertFalse(record["terminated_for_timeout"])
        self.assertLess(record["resource_authority"]["memory_authority_gib"], 32.0)
        self.assertEqual(record["common_mesh_identity"]["global_cell_count"], 1316)
        self.assertEqual(
            record["common_mesh_identity"]["partition_independent_mesh_sha256"],
            "49543a772e47d10f55bf19d7c3421ef57bf6bdc16794c1b77a3c2e4e2384d176",
        )

        angles = record["angle_results"]
        self.assertEqual(
            [entry["grazing_angle_deg"] for entry in angles],
            [1.0, 5.0, 10.0],
        )
        self.assertTrue(
            all(entry["coarse"]["num_nedelec_dofs"] == 57828 for entry in angles)
        )
        self.assertTrue(
            all(entry["enriched"]["num_nedelec_dofs"] == 106355 for entry in angles)
        )
        self.assertTrue(
            all(
                entry[level]["linear_system_relative_residual"] <= 1.0e-9
                for entry in angles
                for level in ("coarse", "enriched")
            )
        )
        gaps = [entry["official_observable_delta_l2"] for entry in angles]
        self.assertAlmostEqual(gaps[0], 0.42375154748116367)
        self.assertAlmostEqual(gaps[1], 0.024638437652910242)
        self.assertAlmostEqual(gaps[2], 0.005871836205650593)
        self.assertGreater(gaps[0], gaps[1])
        self.assertGreater(gaps[1], gaps[2])


if __name__ == "__main__":
    unittest.main()
