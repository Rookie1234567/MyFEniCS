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

class PostSelectionRoleTests(AcceptedParentArtifactsTests):
    def test_diagnostic_record_cannot_be_accepted_parent(self) -> None:
        _write_json(self.selection_path, {
            "schema": "task43.post-selection-comparison.v1",
            "status": "COMPLETE_DIAGNOSTIC_NOT_ACCEPTANCE",
            "selection_eligible": False,
        })
        with self.assertRaisesRegex(ValueError, "frozen accepted decision"):
            load_accepted_parent_artifacts(self.selection_path, artifact_root=self.root,
                                          acceptance_contract_path=self.acceptance_path)

    def test_reserved_fields_reject_default_and_wrong_frozen_hash(self) -> None:
        from unittest.mock import patch

        from benchmarks.task43_hp_adaptivity import reference_restore as restore
        for label in ("Y5_1", "Y3", "Y3_2"):
            with self.assertRaisesRegex(ValueError, "explicit post-selection"):
                restore._load_inventory_entry(label)
        path = self.root / "stop.json"
        _write_json(path, {
            "schema": "task43.rejected-candidate-closeout.v1",
            "status": "REJECTED_UNDER_FROZEN_G_NOISE_GATE_SELECTION_STOPPED",
            "transition10_created": False,
            "last_accepted_state": {"frozen_after_selection_stop": True,
                                    "selection_sha256": "wrong"},
            "evidence": {"last_accepted_selection": {
                "path": str(self.selection_path), "sha256": _sha256(self.selection_path)}},
        })
        with patch.object(restore, "ROOT", self.root), self.assertRaisesRegex(ValueError, "frozen selection hash"):
            restore._post_selection_binding(path)

    def test_reserved_loader_checks_nested_identity_before_bundle(self) -> None:
        from unittest.mock import patch

        from benchmarks.task43_hp_adaptivity import (
            compare_initial_to_references as base,
        )
        directory = self.root / "Y5_1"
        directory.mkdir()
        # Bundle intentionally absent: failure must be role identity, not an I/O
        # error from opening field coefficients.
        manifest = self.root / "manifest.json"
        manifest.write_text("{}")
        binding = {"selection_sha256": "selection", "stop_sha256": "stop"}
        resolved = {"run_role": "post_selection_validation_only",
                    "selection_eligible": False, "frozen_selection_sha256": "wrong",
                    "selection_stop_record_sha256": "stop",
                    "assets_manifest_sha256": _sha256(manifest)}
        with patch.object(base, "_load_inventory_entry", return_value={}), \
             patch.object(base, "_post_selection_binding", return_value=binding):
            for record in ({"label": "Y5_1"}, {"label": "Y5_1", "resolved_identity": resolved}):
                _write_json(directory / "restore_identity_record.json", record)
                with self.assertRaisesRegex(ValueError, "invalid post-selection identity"):
                    base._load_field_case("Y5_1", self.root, reference_root=self.root,
                                          post_selection_record=self.root / "stop.json",
                                          assets_manifest=manifest)

    def test_cli_rejects_adaptive_post_selection_argument_mixing(self) -> None:
        from unittest.mock import patch

        from benchmarks.task43_hp_adaptivity import compare_round1_candidate as compare
        with patch("sys.argv", ["compare", "--attempt-id", "test",
                                "--post-selection-record", "stop.json",
                                "--candidate-run-root", "run"]), self.assertRaises(SystemExit) as error:
            compare.main()
        self.assertEqual(error.exception.code, 2)


class SavedPostSelectionFieldsTests(unittest.TestCase):
    """Offline full-array fixture from the already solved36-cell backend pair."""

    def test_saved_full612_and_q8_q10_physical_metrics(self) -> None:
        import os

        import numpy as np

        from benchmarks.task43_hp_adaptivity import (
            compare_initial_to_references as base,
        )
        from benchmarks.task43_hp_adaptivity.compare_round1_candidate import (
            _j_infinity,
            _post_selection_full_mode_physics,
        )
        from benchmarks.task43_hp_adaptivity.profile import task43_initial_profile
        from src.postprocessing.physical_field_comparison import (
            magnetic_field_from_electric_curl,
        )

        fixture = os.environ.get("TASK43_SAVED_POST_SELECTION_FIXTURE")
        if fixture is None:
            self.skipTest("set TASK43_SAVED_POST_SELECTION_FIXTURE to existing36-cell pair; never solve here")
        root = Path(fixture)
        cases = {}
        for label in ("petsc", "mumps"):
            record = json.loads((root / label / "component_record.json").read_text())
            cases[label] = {"label": label, "power": record["power"],
                            "mode_payload": json.loads((root / label / "solve/dtn_port_diffraction_orders_3d.json").read_text())}
        modal = base._modal_comparison(cases["petsc"], cases["mumps"])
        self.assertEqual(modal["ordered_mode_count"], 612)
        self.assertEqual(len(modal["individual_channel_power_ratio_absolute_differences"]), 612)
        cfg = task43_initial_profile(case_name="post_selection_saved_array_fixture")
        for case in cases.values():
            case["cfg"] = cfg
            physics = _post_selection_full_mode_physics(case)
            self.assertEqual(len(physics["recomputed_all612_power_ratios"]), 612)
        for inventory_error in ("missing", "duplicate"):
            broken = copy.deepcopy(cases["petsc"])
            rows = broken["mode_payload"]["orders"]
            if inventory_error == "missing":
                rows.pop()
            else:
                for key in ("side", "m", "n", "polarization"):
                    rows[1][key] = rows[0][key]
            with self.subTest(inventory_error=inventory_error), self.assertRaises(ValueError):
                _post_selection_full_mode_physics(broken)
        # Algebraic normalization fixture derived from saved amplitudes. These
        # scaled metadata are not asserted to be a newly solved physical field.
        weak = [copy.deepcopy(cases["petsc"]) for _ in range(2)]
        for case, scale in zip(weak, (1e-4, 2e-4), strict=True):
            for row in case["mode_payload"]["orders"]:
                row["outgoing_amplitude_at_boundary"] = [scale * value for value in row["outgoing_amplitude_at_boundary"]]
        forward = base._modal_comparison(weak[0], weak[1])["boundary_amplitude_groups"]["top_s"]
        reverse = base._modal_comparison(weak[1], weak[0])["boundary_amplitude_groups"]["top_s"]
        self.assertLess(forward["reference_boundary_amplitude_l2"], 1.0)
        self.assertAlmostEqual(forward["relative_to_reference"], 1.0, places=12)
        self.assertAlmostEqual(reverse["relative_to_reference"], .5, places=12)
        self.assertAlmostEqual(forward["relative_with_unit_incident_modal_floor"], forward["reference_boundary_amplitude_l2"], places=12)
        self.assertAlmostEqual(forward["relative_with_unit_incident_modal_floor"], reverse["relative_with_unit_incident_modal_floor"], places=12)
        for mutation in ("power_ratio", "R", "boundary", "aggregate"):
            broken = copy.deepcopy(cases["petsc"])
            row = next(row for row in broken["mode_payload"]["orders"]
                       if row["side"] == "top" and row["m"] == row["n"] == 0 and row["polarization"] == "s")
            if mutation == "boundary":
                row["outgoing_amplitude_at_boundary"][0] += 1e-5
            elif mutation == "aggregate":
                broken["power"]["R_total"] += 1e-5
            else:
                row[mutation] += 1e-5
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                _post_selection_full_mode_physics(broken)
        with np.load(root / "petsc/raw_pair_arrays.npz", allow_pickle=False) as reference, \
             np.load(root / "mumps/raw_pair_arrays.npz", allow_pickle=False) as candidate:
            for q in ("q8", "q10"):
                weights = reference[f"{q}_weights_nm3"]
                self.assertAlmostEqual(float(np.sum(weights)), 350000.0, places=7)
                self.assertTrue(np.array_equal(weights, candidate[f"{q}_weights_nm3"]))
                samples = [{"E": archive[f"{q}_E_total"], "curl_E": archive[f"{q}_curl_E_total"]}
                           for archive in (reference, candidate)]
                field = base._field_metrics(samples[0], samples[1], reference[f"{q}_points_nm"], weights, cfg)
                # Verify the explicitly chosen reference determines the norm.
                expected = float(np.sqrt(np.sum(weights * np.sum(np.abs(samples[0]["E"]) ** 2, axis=1))))
                self.assertAlmostEqual(field["E_total_code"]["reference_l2"], expected, places=10)
                recovered_h = magnetic_field_from_electric_curl(
                    samples[0]["curl_E"], magnetic_field_scale_A_per_m=cfg.magnetic_field_scale_A_per_m,
                    k0_per_nm=cfg.k0, mu_r=cfg.mu_r)
                self.assertLess(float(np.max(np.abs(recovered_h - reference[f"{q}_H_total_A_per_m"]))), 1e-12)
                self.assertLess(_j_infinity(modal, field)["value"], 1e-6)
                weak_samples = [{name: values * scale for name, values in samples[0].items()}
                                for scale in (.01, .02)]
                forward_field = base._field_metrics(weak_samples[0], weak_samples[1], reference[f"{q}_points_nm"], weights, cfg)["E_total_code"]
                reverse_field = base._field_metrics(weak_samples[1], weak_samples[0], reference[f"{q}_points_nm"], weights, cfg)["E_total_code"]
                self.assertLess(forward_field["candidate_l2"], forward_field["reference_norm_floor"])
                self.assertAlmostEqual(forward_field["reference_l2"], .01 * expected, places=10)
                self.assertAlmostEqual(reverse_field["reference_l2"], .02 * expected, places=10)
                self.assertAlmostEqual(forward_field["relative_to_reference"], 1.0, places=12)
                self.assertAlmostEqual(reverse_field["relative_to_reference"], .5, places=12)
                self.assertAlmostEqual(forward_field["relative_to_reference_or_floor"], .01 * expected / forward_field["reference_norm_floor"], places=12)
                self.assertAlmostEqual(forward_field["relative_to_reference_or_floor"], reverse_field["relative_to_reference_or_floor"], places=12)


if __name__ == "__main__":
    unittest.main()
