from __future__ import annotations

import copy
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


class ComparisonParentRawGateTests(unittest.TestCase):
    """Frozen initial record layout and its real residual/count metadata.

    Finite modal rows are only a checker fixture, not a new PDE qualification.
    """

    def setUp(self) -> None:
        from benchmarks.task43_hp_adaptivity.compare_round1_candidate import (
            _recompute_candidate_hard_gates,
        )
        self.check = _recompute_candidate_hard_gates
        self.record = {
            "schema": "task43.initial_180_cell_active_p3_current.v1",
            "case_id": "current_active_p3_initial180_mpi1",
            "solver": {
                "official_result": True,
                "independent_active_action": {
                    "full_solver_gauge_residual": {"raw_l2_norm": 1.744290778417178e-10},
                    "rhs": {"raw_l2_norm": 0.7314141875644989},
                    "rows": {"independent_trace": 8640, "active_cell_interior": 6480, "modal_lower": 612},
                    "groups": {
                        "independent_active_trace_residual": {"row_count": 8640},
                        "independent_active_interior_residual": {"row_count": 6480},
                    },
                },
                "condensed_residual": {
                    "linear_system_residual_norm": 4.612554194533421e-11,
                    "linear_system_rhs_norm": 0.7314003724959292,
                },
            },
            "power": {
                "aggregate": {"R_total": 0.8074736775832397, "T_total": 0.005279003522897643},
                "A_volume_total": 0.18724731889353746,
            },
            "recovered_solution_storage": {"active_trace_rows": 8640, "active_cell_interior_rows": 6480},
            "numerical_controls": {"local_h_actual_audit": {"pass": True}},
            "gates": {"pass": True},
        }
        self.modes = {"orders": [
            {"side": side, "m": m, "n": n, "polarization": pol,
             "power_ratio": 0.0, "R": 0.0, "T": 0.0,
             **{key: [0.0, 0.0] for key in (
                 "outgoing_amplitude_at_boundary", "alpha", "gamma", "beta", "kz", "refractive_index",
             )}}
            for side in ("top", "bottom") for m in range(-4, 5)
            for n in range(-8, 9) for pol in ("s", "p")
        ]}
        self.contract = {"final_tolerances": {
            "independent_full_active_relative_residual": 1e-6,
            "condensed_direct_relative_residual": 1e-9,
            "absolute_energy_closure_1_minus_R_minus_T_minus_A_volume": 1e-5,
        }}

    def test_frozen_initial_requires_explicit_role_and_keeps_absent_declarations(self) -> None:
        original = copy.deepcopy(self.record)
        self.assertFalse(self.check(self.record, self.modes, self.contract)["pass"])
        result = self.check(self.record, self.modes, self.contract, allow_legacy_initial_parent=True)
        self.assertTrue(result["pass"])
        self.assertEqual(result["actual_space"]["independent_FE_dofs"], 15120)
        self.assertIsNone(result["actual_space"]["storage_declared_independent_FE_dofs"])
        self.assertIsNone(result["actual_space"]["active_space_declared_independent_FE_dofs"])
        self.assertFalse(result["actual_space"]["both_declarations_match_recomputed_sum"])
        self.assertNotIn("independent_dofs_match_both_record_declarations", result["hard_checks"])
        self.assertEqual(self.record, original)

    def test_legacy_exception_rejects_wrong_identity_counts_and_failed_physics(self) -> None:
        changes = [
            ("schema",), ("case_id",), ("storage_count",), ("A6_group_count",),
            ("A6_total_rows",), ("failed_A6",), ("failed_closure",),
            ("failed_mesh",), ("partial_declaration",), ("null_active_space",),
        ]
        for (change,) in changes:
            with self.subTest(change=change):
                record = copy.deepcopy(self.record)
                if change in ("schema", "case_id"):
                    record[change] = "different"
                elif change == "storage_count":
                    record["recovered_solution_storage"]["active_trace_rows"] += 1
                elif change == "A6_group_count":
                    record["solver"]["independent_active_action"]["groups"]["independent_active_interior_residual"]["row_count"] -= 1
                elif change == "A6_total_rows":
                    record["solver"]["independent_active_action"]["rows"]["modal_lower"] -= 1
                elif change == "failed_A6":
                    record["solver"]["independent_active_action"]["full_solver_gauge_residual"]["raw_l2_norm"] = 1e-3
                elif change == "failed_closure":
                    record["power"]["A_volume_total"] += 1e-3
                elif change == "failed_mesh":
                    record["numerical_controls"]["local_h_actual_audit"]["pass"] = False
                elif change == "partial_declaration":
                    record["recovered_solution_storage"]["independent_active_fe_dofs"] = 15120
                else:
                    record["numerical_controls"]["active_space"] = None
                self.assertFalse(self.check(record, self.modes, self.contract, allow_legacy_initial_parent=True)["pass"])

    def test_modern_candidate_still_requires_both_matching_declarations(self) -> None:
        record = copy.deepcopy(self.record)
        record["schema"] = "task43.round1_candidate.v1"
        record["recovered_solution_storage"]["independent_active_fe_dofs"] = 15120
        record["numerical_controls"]["active_space"] = {"independent_active_fe_dofs": 15120}
        self.assertTrue(self.check(record, self.modes, self.contract)["pass"])
        for section in ("recovered_solution_storage", "numerical_controls"):
            with self.subTest(section=section):
                broken = copy.deepcopy(record)
                if section == "numerical_controls":
                    broken[section]["active_space"].pop("independent_active_fe_dofs")
                else:
                    broken[section].pop("independent_active_fe_dofs")
                self.assertFalse(self.check(broken, self.modes, self.contract, allow_legacy_initial_parent=True)["pass"])


if __name__ == "__main__":
    unittest.main()
