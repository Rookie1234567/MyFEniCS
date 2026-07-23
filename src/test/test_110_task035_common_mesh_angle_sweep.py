"""Contracts for the Task035 SHA-bound common-mesh angle sweep."""

from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
