"""Synthetic/software tests ONLY. These fixtures are not finite-element labels."""
from __future__ import annotations

import copy
import importlib.util
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.surrogate.data import CHECKS, FIXED_PHYSICS, select_records, validate_qualification
from src.surrogate.design import ANCHORS, digest, extend_training, make_design, permitted_batch_count, validate_design
from src.surrogate.workflow import evaluate_blind, fit_experiment, freeze_strategy, save_new


def synthetic_fixture():
    design = make_design()
    q = {"schema": "sixlayer-qualification-v1", "data_kind": "synthetic_test",
         "generator_sha256": "a" * 64, "materials_sha256": "b" * 64,
         "source_sha256": "c" * 64, "checks": []}
    for i, kind in enumerate(sorted(CHECKS)):
        q["checks"].append({"kind": kind, "thickness_nm": list(ANCHORS[i]),
                            "reference_config_sha256": "d" * 64,
                            "candidate_config_sha256": "e" * 64, "evidence_sha256": "f" * 64,
                            "gaps_nm": [0.5, 1.0], "bottom_reference_nm": -0.5,
                            "reference_outputs": {"R_total": 0.2, "T_total": 0.6, "R00_total": 0.1},
                            "candidate_outputs": {"R_total": 0.20001, "T_total": 0.59999, "R00_total": 0.10001}})
    groups = {"train": [], "dev": [], "blind": []}
    for point in design["points"]:
        x = [(t - 0.5) / 0.5 for t in point["thickness_nm"]]
        reflection = 0.2 + 0.02 * sum(x) / 6 + 0.003 * math.sin(x[0] * 3)
        transmission = 0.6 - 0.01 * x[1] + 0.002 * x[2] * x[4]
        zero = reflection * (0.7 + 0.02 * x[5])
        row = {"sample_id": point["sample_id"], "thickness_nm": point["thickness_nm"],
               "status": "completed", "data_kind": "synthetic_test",
               "generator_sha256": q["generator_sha256"], "materials_sha256": q["materials_sha256"],
               "source_sha256": q["source_sha256"], "qualification_sha256": digest(q),
               "full_true_residual": 1e-9, "dofs": 1,
               "physics": {**FIXED_PHYSICS, "thickness_nm": point["thickness_nm"],
                           "materials_sha256": q["materials_sha256"]},
               "outputs": {"R_total": reflection, "T_total": transmission, "R00_total": zero,
                           "R00_s": zero, "R00_p": 0.0, "A_balance": 1 - reflection - transmission,
                           "A_volume": 1 - reflection - transmission},
               "resources": {"task_swap_bytes": 0, "process_tree_peak_bytes": 1,
                             "full_wall_seconds": 1, "stage_seconds": {"synthetic": 1},
                             "measurement_scope": "simultaneous_process_tree_full_pipeline",
                             "supervision_sha256": "f" * 64, "exit_code": 0, "cleanup_complete": True,
                             "sampling_complete": True, "swap_samples_complete": True,
                             "available_memory_gate_passed": True, "sample_count": 2,
                             "minimum_available_bytes": 2_147_483_648}}
        for key in ("input_sha256", "physical_model_sha256", "run_manifest_sha256",
                    "evidence_sha256", "mesh_sha256", "dtn_modes_sha256"):
            row[key] = "f" * 64
        groups[point["split"]].append(row)
    for i, check in enumerate(q["checks"]):
        for prefix in ("reference", "candidate"):
            row = copy.deepcopy(groups["train"][i])
            row["config_sha256"] = check[f"{prefix}_config_sha256"]
            out = dict(check[f"{prefix}_outputs"])
            out.update({"R00_s": out["R00_total"], "R00_p": 0.0,
                        "A_balance": 1 - out["R_total"] - out["T_total"],
                        "A_volume": 1 - out["R_total"] - out["T_total"]})
            row["outputs"] = out
            row["numerical_configuration"] = {"x_subdivisions": 3, "y_subdivisions": 6,
                                               "layer_subdivisions": [1] * 8,
                                               "dtn_evanescent_orders": [4, 4], "top_gap_nm": 0.5}
            if prefix == "candidate":
                changed = {"propagation_mesh": ("y_subdivisions", 12),
                           "layer_z_mesh": ("layer_subdivisions", [1] + [2] * 6 + [1]),
                           "dtn_evanescent": ("dtn_evanescent_orders", [6, 6]),
                           "top_air_gap": ("top_gap_nm", 1.0)}[check["kind"]]
                row["numerical_configuration"][changed[0]] = changed[1]
            check[f"{prefix}_run"] = row
    for records in groups.values():
        for row in records:
            row["qualification_sha256"] = digest(q)
    return design, q, groups


class DesignAndQualificationTests(unittest.TestCase):
    def test_reproducible_unique_minimal_design_and_anchors(self):
        d = make_design()
        self.assertEqual(digest(d), digest(make_design()))
        self.assertEqual(d["planned_counts"], {"train": 8, "dev": 4, "blind": 6})
        self.assertEqual([p["thickness_nm"] for p in d["points"][:4]], [list(a) for a in ANCHORS])
        self.assertEqual(len(validate_design(d)), 18)
        self.assertNotEqual(digest(d), digest(make_design(seed=123)))

    def test_optional_legacy_counts_and_nested_prefixes(self):
        d = make_design(train_count=80, dev_count=10, blind_count=10)
        self.assertEqual(len(validate_design(d)), 100)
        train = [p["sample_id"] for p in d["points"] if p["split"] == "train"]
        self.assertTrue(set(train[:20]) < set(train[:40]) < set(train[:80]))

    def test_four_point_extension_does_not_move_holdouts(self):
        d = make_design()
        e = extend_training(d, reason="Synthetic development-only diagnostic, not actual FE evidence")
        self.assertEqual(e["planned_counts"]["train"], 12)
        self.assertEqual([p for p in d["points"] if p["split"] != "train"],
                         [p for p in e["points"] if p["split"] != "train"])
        self.assertEqual(d["points"][:8], e["points"][:8])

    def test_geometry_overlap_rejected(self):
        d = make_design()
        d["points"][-1]["thickness_nm"] = d["points"][0]["thickness_nm"]
        with self.assertRaises(ValueError):
            validate_design(d)

    def test_boolean_and_text_geometry_rejected(self):
        for value in (True, "0.5"):
            d = make_design()
            d["points"][0]["thickness_nm"][0] = value
            with self.assertRaises(ValueError):
                validate_design(d)

    def test_comparison_cannot_change_physics_or_unrelated_numerics(self):
        for key, value in (("degree", 4), ("lambda0_nm", 13.5), ("materials_sha256", "1" * 64)):
            _, q, _ = synthetic_fixture()
            q["checks"][0]["candidate_run"]["physics"][key] = value
            with self.assertRaises(ValueError):
                validate_qualification(q, allow_synthetic=True)
        _, q, _ = synthetic_fixture()
        q["checks"][0]["candidate_run"]["numerical_configuration"]["x_subdivisions"] = 6
        with self.assertRaises(ValueError):
            validate_qualification(q, allow_synthetic=True)

    def test_budget_uses_remaining_48h_window_not_old_stop(self):
        self.assertGreater(permitted_batch_count(10000, [700], 4)["count"], 0)
        self.assertEqual(permitted_batch_count(1800, [100], 4)["count"], 0)

    def test_synthetic_cannot_be_ingested_as_fe(self):
        d, q, g = synthetic_fixture()
        with self.assertRaises(ValueError):
            select_records(d, g["train"], q, "train", 8)
        self.assertEqual(len(select_records(d, g["train"], q, "train", 8, allow_synthetic=True)[0]), 8)

    def test_no_wrong_split_or_missing_failed_sample(self):
        d, q, g = synthetic_fixture()
        for bad in (g["train"][:-1], g["train"][:7] + g["blind"][:1], g["train"][:7] + g["train"][:1]):
            with self.assertRaises(ValueError):
                select_records(d, bad, q, "train", 8, allow_synthetic=True)

    def test_numeric_gates_not_status_only(self):
        d, q, g = synthetic_fixture()
        for key, value in (("full_true_residual", 1.01e-6), ("full_true_residual", float("nan")),
                           ("generator_sha256", "e" * 64), ("status", "failed")):
            bad = copy.deepcopy(g["train"])
            bad[0][key] = value
            with self.assertRaises(ValueError):
                select_records(d, bad, q, "train", 8, allow_synthetic=True)
        for key, value in (("task_swap_bytes", 1), ("process_tree_peak_bytes", 10_000_000_001),
                           ("cleanup_complete", False), ("exit_code", False),
                           ("sampling_complete", False), ("swap_samples_complete", False),
                           ("available_memory_gate_passed", False), ("minimum_available_bytes", 1_073_741_823)):
            bad = copy.deepcopy(g["train"])
            bad[0]["resources"][key] = value
            with self.assertRaises(ValueError):
                select_records(d, bad, q, "train", 8, allow_synthetic=True)

    def test_boolean_dofs_rejected(self):
        d, q, g = synthetic_fixture()
        g["train"][0]["dofs"] = True
        with self.assertRaises(ValueError):
            select_records(d, g["train"], q, "train", 8, allow_synthetic=True)
        with self.assertRaises(ValueError):
            select_records(d, g["dev"][:1], q, "dev", True, allow_synthetic=True)

    def test_power_and_refinement_failures_rejected(self):
        d, q, g = synthetic_fixture()
        bad = copy.deepcopy(g["train"])
        bad[0]["outputs"]["A_volume"] += 2e-5
        with self.assertRaises(ValueError):
            select_records(d, bad, q, "train", 8, allow_synthetic=True)
        q["checks"][0]["candidate_outputs"]["R_total"] += 1e-3
        with self.assertRaises(ValueError):
            validate_qualification(q, allow_synthetic=True)


@unittest.skipUnless(importlib.util.find_spec("sklearn") is not None, "optional scikit-learn unavailable")
class SyntheticModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.design, cls.q, cls.groups = synthetic_fixture()
        cls.experiment = fit_experiment(cls.design, cls.q, cls.groups["train"], cls.groups["dev"],
                                        allow_synthetic=True)

    def test_train_only_scaler_and_ard(self):
        import numpy as np
        m = self.experiment["model"]
        np.testing.assert_allclose(m["scaler"]["mean"], np.mean(m["y_train_raw"], axis=0))
        self.assertEqual(m["strategy"]["name"], "matern52-ard-independent-v1")
        self.assertTrue(all(len(p["length_scale"]) == 6 for p in m["gp_parameters"]))
        self.assertEqual(m["linear_rank"], 7)
        self.assertEqual(self.experiment["data_kind"], "synthetic_test")

    def test_every_cv_scaler_excludes_held_fold(self):
        import numpy as np
        y = np.asarray(self.experiment["model"]["y_train_raw"])
        for fold in self.experiment["report"]["cross_validation"]["folds"]:
            self.assertFalse(set(fold["train_indices"]) & set(fold["held_indices"]))
            np.testing.assert_allclose(fold["scaler"]["mean"], y[fold["train_indices"]].mean(axis=0))

    def test_predict_reload_and_raw_unit_error(self):
        import numpy as np
        from src.surrogate.models import errors, predict_model
        model = self.experiment["model"]
        x = [r["thickness_nm"] for r in self.groups["dev"]]
        a = predict_model(model, x)
        b = predict_model(json.loads(json.dumps(model)), x)
        np.testing.assert_array_equal(a["gp"], b["gp"])
        y = [[0.2, 0.6, 0.1]] * 2
        err = errors(y, [[0.201, 0.602, 0.103]] * 2)
        self.assertAlmostEqual(err["R_total"]["max_absolute_error"], 0.001)
        self.assertTrue(np.isfinite(a["gp_std"]).all())

    def test_mean_sufficient_is_not_persuasive_gp_success(self):
        from src.surrogate.models import evaluation_report
        q = validate_qualification(self.q, allow_synthetic=True)
        constant = [[0.2, 0.6, 0.1]] * 4
        model = copy.deepcopy(self.experiment["model"])
        model["y_train_raw"] = constant * 2
        predictions = {name: constant for name in ("gp", "mean", "linear", "gp_std")}
        report = evaluation_report(model, self.groups["dev"], constant, predictions, q)
        self.assertTrue(report["all_max_error_targets_met"])
        self.assertTrue(all(row["generalization_evidence_insufficient"] for row in report["outputs"].values()))

    def test_observed_repeat_noise_can_make_effect_inconclusive(self):
        from src.surrogate.models import evaluation_report, predict_model
        q = validate_qualification(self.q, allow_synthetic=True)
        q["checked_point_refinement_difference"] = {name: 0 for name in ("R_total", "T_total", "R00_total")}
        q["repeat_noise_indicator"] = {"evidence_sha256": "a" * 64,
                                        "max_absolute_difference": {name: 0.1 for name in q["checked_point_refinement_difference"]}}
        x = [r["thickness_nm"] for r in self.groups["dev"]]
        y = [[r["outputs"][name] for name in ("R_total", "T_total", "R00_total")] for r in self.groups["dev"]]
        prediction = predict_model(self.experiment["model"], x)
        prediction["mean"] = [[1, 1, 1]] * len(y)  # ensure mean-sufficient does not cause this flag
        report = evaluation_report(self.experiment["model"], self.groups["dev"], y, prediction, q)
        for row in report["outputs"].values():
            self.assertFalse(row["mean_baseline_already_meets_target"])
            self.assertFalse(row["response_near_checked_refinement_difference"])
            self.assertTrue(row["response_near_measured_repeat_difference"])
            self.assertTrue(row["generalization_evidence_insufficient"])

    def test_prediction_runtime_mismatch_rejected(self):
        from src.surrogate.models import predict_model
        model = copy.deepcopy(self.experiment["model"])
        model["packages"]["sklearn"] = "wrong"
        with self.assertRaises(ValueError):
            predict_model(model, [self.groups["dev"][0]["thickness_nm"]])

    def test_learning_curve_rejects_changed_labels_and_holdouts(self):
        from src.surrogate.workflow import learning_curve
        bad = copy.deepcopy(self.experiment)
        bad["dev_records_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            learning_curve([self.experiment, bad])
        bad = copy.deepcopy(self.experiment)
        bad["model"]["y_train_raw"][0][0] += 1e-6
        with self.assertRaises(ValueError):
            learning_curve([self.experiment, bad])

    def test_freeze_mismatch_never_opens_blind_file(self):
        freeze = freeze_strategy(self.experiment, self.design, self.q,
                                 reason="Synthetic test decision only; no physical feasibility claim")
        freeze["experiment_sha256"] = "0" * 64
        with patch("src.surrogate.workflow.read_json", side_effect=AssertionError("blind opened")) as read:
            with self.assertRaises(ValueError):
                evaluate_blind(self.experiment, self.design, self.q, freeze, "DO_NOT_OPEN.json")
            read.assert_not_called()

    def test_runtime_mismatch_never_opens_blind_file(self):
        freeze = freeze_strategy(self.experiment, self.design, self.q,
                                 reason="Synthetic test decision only; no physical feasibility claim")
        with patch("src.surrogate.workflow.metadata.version", return_value="changed"):
            with patch("src.surrogate.workflow.read_json", side_effect=AssertionError("blind opened")) as read:
                with self.assertRaises(ValueError):
                    evaluate_blind(self.experiment, self.design, self.q, freeze, "DO_NOT_OPEN.json")
                read.assert_not_called()

    def test_blind_is_single_use_and_finite(self):
        freeze = freeze_strategy(self.experiment, self.design, self.q,
                                 reason="Synthetic test decision only; no physical feasibility claim")
        with tempfile.TemporaryDirectory() as temp:
            labels = Path(temp) / "protected_blind.json"
            save_new(labels, self.groups["blind"])
            report = evaluate_blind(self.experiment, self.design, self.q, freeze, labels)
            self.assertEqual(report["n"], 6)
            self.assertEqual(report["data_kind"], "synthetic_test")
            self.assertTrue(Path(str(labels) + ".evaluation_started.json").exists())
            with self.assertRaises(FileExistsError):
                evaluate_blind(self.experiment, self.design, self.q, freeze, labels)

    def test_failed_blind_exposure_is_retained(self):
        freeze = freeze_strategy(self.experiment, self.design, self.q,
                                 reason="Synthetic test decision only; no physical feasibility claim")
        with tempfile.TemporaryDirectory() as temp:
            labels = Path(temp) / "protected_blind.json"
            save_new(labels, self.groups["blind"][:-1])
            with self.assertRaises(ValueError):
                evaluate_blind(self.experiment, self.design, self.q, freeze, labels)
            self.assertTrue(Path(str(labels) + ".evaluation_started.json.failed.json").exists())


if __name__ == "__main__":
    unittest.main()
