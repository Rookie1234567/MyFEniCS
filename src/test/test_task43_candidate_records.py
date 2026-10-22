from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from benchmarks.task43_hp_adaptivity.candidate_records import (
    load_accepted_parent_artifacts,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


class AcceptedParentArtifactsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.acceptance_path = self.root / "acceptance.json"
        _write_json(
            self.acceptance_path,
            {
                "evidence": {
                    "comparison_contract": {"sha256": "comparison-contract"},
                    "reference_and_quadrature": {"sha256": "calibration"},
                }
            },
        )
        self.run_root = self.root / "run"
        self.run_root.mkdir()
        self.record_path = self.run_root / "task43_round1_candidate_record.json"
        self.storage_path = self.run_root / "candidate_recovered_solution_storage.npz"
        self.plan_path = self.run_root / "candidate_plan.json"
        self.comparison_path = self.root / "comparison.json"
        self.selection_path = self.root / "selection.json"
        self.storage_path.write_bytes(b"storage bytes")
        _write_json(
            self.plan_path,
            {"task43_candidate": {"candidate_id": "candidate-A"}},
        )
        _write_json(
            self.record_path,
            {
                "candidate_identity": {"candidate_id": "candidate-A"},
                "gates": {"pass": True},
                "solver": {"official_result": True, "case_status": "completed"},
                "recovered_solution_storage": {
                    "sha256": _sha256(self.storage_path),
                    "independent_active_fe_dofs": 17,
                },
            },
        )
        acceptance_sha = _sha256(self.acceptance_path)
        comparison = {
            "candidate_id": "candidate-A",
            "selection": {"gates": {"pass": True}},
            "verified_source_contracts": {
                "candidate_raw_hard_gate_recalculation": {"pass": True},
                "round1_acceptance_contract_sha256": acceptance_sha,
                "comparison_contract_sha256": "comparison-contract",
                "reference_calibration_sha256": "calibration",
            },
            "selection_reference": "Y6_1",
            "holdout_read": False,
            "final_p6_control_read": False,
            "candidate_record_sha256": _sha256(self.record_path),
            "candidate_storage_sha256": _sha256(self.storage_path),
            "candidate_plan_sha256": _sha256(self.plan_path),
        }
        _write_json(self.comparison_path, comparison)
        _write_json(
            self.selection_path,
            {
                "schema": "task43.selection-decision.v1",
                "status": "accepted",
                "selected_candidate": {
                    "candidate_id": "candidate-A",
                    "run_root": str(self.run_root),
                    "comparison_record_path": str(self.comparison_path),
                    "record_sha256": _sha256(self.record_path),
                    "storage_sha256": _sha256(self.storage_path),
                    "plan_sha256": _sha256(self.plan_path),
                    "comparison_record_sha256": _sha256(self.comparison_path),
                    "acceptance_contract_sha256": acceptance_sha,
                    "independent_FE_dofs": 17,
                },
            },
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_reads_matching_accepted_selection_and_all_artifact_hashes(self) -> None:
        loaded = load_accepted_parent_artifacts(
            self.selection_path,
            artifact_root=self.root,
            acceptance_contract_path=self.acceptance_path,
        )
        self.assertEqual(loaded["candidate_id"], "candidate-A")
        self.assertEqual(loaded["independent_FE_dofs"], 17)
        self.assertEqual(loaded["plan"]["task43_candidate"]["candidate_id"], "candidate-A")

    def test_rejects_stale_selected_storage_hash(self) -> None:
        selection = json.loads(self.selection_path.read_text(encoding="utf-8"))
        selection["selected_candidate"]["storage_sha256"] = "stale"
        _write_json(self.selection_path, selection)
        with self.assertRaisesRegex(ValueError, "hashes differ"):
            load_accepted_parent_artifacts(
                self.selection_path,
                artifact_root=self.root,
                acceptance_contract_path=self.acceptance_path,
            )


if __name__ == "__main__":
    unittest.main()
