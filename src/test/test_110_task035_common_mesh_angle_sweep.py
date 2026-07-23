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
