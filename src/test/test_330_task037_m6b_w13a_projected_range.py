from __future__ import annotations

import inspect
import json
import math
from pathlib import Path

import numpy as np
import pytest

from benchmarks import run_task037_extra_m6b as runner
from src.solvers.hcurl_h2b_m6b_shifted_patch_pc import H2BM6BProjectedRangePC
from src.solvers.hcurl_m6b_w13a_projected_range import (
    W13A_RESIDUAL_ORDER,
    run_w13a_projected_range_measurements,
)


_HASH = "a" * 64


def _measurement(rhs: np.ndarray, *, closure: float = 1.0e-14) -> dict[str, object]:
    return {
        "finite": True,
        "rho_local_only": 0.9,
        "rho_range_only": 0.8,
        "rho_projected": 0.7,
        "linear_action_closure": closure,
        "complement_optimality": closure,
        "alpha": [0.25, -0.5],
        "omega": [0.75, 0.125],
        "projection_denominator": [2.0, 0.0],
        "local_exact_shifted_action_count": 1,
        "action_counts": {
            "local_apply": 1,
            "physical_outer_action": 5,
            "range_apply": 3,
        },
        "rhs_sha256": _HASH,
        "final_correction_sha256": _HASH,
        "final_action_sha256": _HASH,
        "final_residual_sha256": _HASH,
    }


def test_w13a_core_has_one_gate_and_records_fixed_wall_and_action_contract() -> None:
    residuals = {
        "w5_iter200": np.array([1 + 2j, -2 + 0.5j], dtype=np.complex128),
        "w7_cumulative400": np.array([0.5 - 1j, 3 + 0.25j], dtype=np.complex128),
    }
    calls: list[str] = []

    def apply(rhs: np.ndarray):
        calls.append("apply")
        return rhs.copy(), _measurement(rhs)

    result = run_w13a_projected_range_measurements(
        residuals, apply, beta=1.0
    )

    assert result["residual_order"] == list(W13A_RESIDUAL_ORDER)
    assert set(result) == {
        "schema",
        "beta",
        "residual_order",
        "measurements",
        "action_counts",
        "gate",
        "elapsed_wall_seconds",
    }
    assert result["gate"]["pass"] is True
    assert all(result["gate"]["checks"].values())
    assert all(type(value) is bool for value in result["gate"]["checks"].values())
    assert all(
        type(record[key]) is bool
        for record in result["measurements"].values()
        for key in ("repeat_exact", "closure_pass")
    )
    json.dumps(result, allow_nan=False)
    assert len(calls) == 4
    assert result["action_counts"] == {
        "local_apply": 4,
        "physical_outer_action": 20,
        "range_apply": 12,
        "local_exact_shifted_action_count": 4,
    }
    assert result["elapsed_wall_seconds"] >= 0.0
    for record in result["measurements"].values():
        assert record["repeat_exact"] is True
        assert record["local_exact_shifted_action_count"] == 1
        assert record["first_apply_wall_seconds"] >= 0.0
        assert record["repeat_apply_wall_seconds"] >= 0.0
        assert record["apply_wall_seconds"] >= 0.0


def test_w13a_core_closure_is_a_gate_and_fixed_beta_order_rejects_scans() -> None:
    residuals = {
        "w5_iter200": np.ones(2, dtype=np.complex128),
        "w7_cumulative400": np.ones(2, dtype=np.complex128),
    }

    def bad_apply(rhs: np.ndarray):
        return rhs.copy(), _measurement(rhs, closure=1.0e-8)

    failed = run_w13a_projected_range_measurements(
        residuals, bad_apply, beta=0.5
    )
    assert failed["gate"]["pass"] is False
    assert failed["gate"]["checks"]["action_closure"] is False
    with pytest.raises(ValueError, match="beta or residual order"):
        run_w13a_projected_range_measurements(residuals, bad_apply, beta=0.25)
    with pytest.raises(ValueError, match="beta or residual order"):
        run_w13a_projected_range_measurements(
            {"w7_cumulative400": residuals["w7_cumulative400"], "w5_iter200": residuals["w5_iter200"]},
            bad_apply,
            beta=0.5,
        )


def test_w13a_scope_prediction_and_parser_are_fixed_without_beta_argument() -> None:
    scope = runner._m6b_w13a_scope()
    prediction = runner._m6b_w13a_predicted_live_set()
    assert scope["betas"] == [1.0, 0.5]
    assert scope["parameter_scan"] is False
    assert scope["old_beta05_bare_pc"] == "frozen_failure_not_reopened"
    expected_prediction = (
        runner.M6B_W2R_BASE_PREDICTED_LIVE_SET_BYTES
        + 2 * runner.M6B_W2R_EXTERNAL_RESIDUAL_BYTES
        + runner.M6B_W2R_PROJECTED_INCREMENTAL_BYTES
    )
    assert expected_prediction == 1_726_081_915
    assert prediction["bytes"] == expected_prediction
    assert prediction["gate"] is True
    assert prediction["derived_not_measured"] is True
    diagnostic_source = inspect.getsource(runner._run_m6b_w13a_diagnostic)
    assert '"beta_wall_seconds"' in diagnostic_source
    assert diagnostic_source.count("_m6b_w13a_predicted_live_set()") == 1
    assert diagnostic_source.index("prediction =") < diagnostic_source.index(
        "w5 = _m6b_w7_s1_load_w5_authority"
    )
    assert '"first_apply_wall_seconds"' in inspect.getsource(
        run_w13a_projected_range_measurements
    )

    args = runner._parser().parse_args(
        [
            "m6b-w13a-diagnostic",
            "--run-dir",
            "w13a-run",
            "--factor1-authority-dir",
            "beta1",
            "--factor05-authority-dir",
            "beta05",
            "--wave-authority-dir",
            "wave",
            "--jit-cache-source",
            "jit",
            "--w0-authority-file",
            "w0.json",
            "--w5-compact",
            "w5.json",
            "--w5-raw-dir",
            "w5",
            "--w7-compact",
            "w7.json",
            "--w7-raw-dir",
            "w7",
            "--output",
            "w13a.json",
            "--expected-source-sha",
            "a" * 40,
        ]
    )
    assert args.command == "m6b-w13a-diagnostic"
    assert not hasattr(args, "beta")


def test_w13a_beta05_child_mode_is_narrow_and_scope_is_bound() -> None:
    residuals = {
        "w5_iter200": np.ones(2, dtype=np.complex128),
        "w7_cumulative400": np.ones(2, dtype=np.complex128),
    }
    allowed = runner._m6b_w13a_beta05_mode_allowed
    assert allowed(
        w13a_residuals=residuals,
        projected=True,
        screen=False,
        shifted_beta=0.5,
    ) is True
    assert allowed(
        w13a_residuals=None,
        projected=True,
        screen=False,
        shifted_beta=0.5,
    ) is False
    assert allowed(
        w13a_residuals=residuals,
        projected=False,
        screen=False,
        shifted_beta=0.5,
    ) is False
    assert allowed(
        w13a_residuals=residuals,
        projected=True,
        screen=True,
        shifted_beta=0.5,
    ) is False
    assert allowed(
        w13a_residuals=residuals,
        projected=True,
        screen=False,
        shifted_beta=0.25,
    ) is False
    with pytest.raises(ValueError, match="remain fixed at beta=1"):
        runner._m6b_w13a_beta05_mode_guard(
            w13a_residuals=None,
            projected=True,
            screen=False,
            shifted_beta=0.5,
        )
    runner._m6b_w13a_beta05_mode_guard(
        w13a_residuals=residuals,
        projected=True,
        screen=False,
        shifted_beta=0.5,
    )
    source = inspect.getsource(runner._run_m6b_w2_diagnostic)
    assert "_m6b_w13a_beta05_mode_guard" in source

    child05 = runner._m6b_w13a_child_scope(shifted_beta=0.5)
    assert child05["phase"] == runner.M6B_W13A_PHASE
    assert child05["parent_phase"] == runner.M6B_W13A_PHASE
    assert child05["shifted_beta"] == 0.5
    assert child05["action_only"] is True
    assert child05["projected"] is True
    assert child05["screen"] is False
    assert child05["two_frozen_residuals"] == list(residuals)
    assert child05["parameter_scan"] is False
    assert child05["old_beta05_bare_pc"] == "frozen_failure_not_reopened"
    assert runner._m6b_w13a_predicted_live_set()["bytes"] == 1_726_081_915

    child1 = runner._m6b_w13a_child_scope(shifted_beta=1.0)
    assert child1["shifted_beta"] == 1.0
    assert child1["two_frozen_residuals"] == list(residuals)


def test_w13a_keeps_projected_pc_default_behavior_and_no_heavy_dispatch() -> None:
    signature = inspect.signature(H2BM6BProjectedRangePC.__init__)
    assert signature.parameters["record_local_omega"].default is False
    core_source = inspect.getsource(run_w13a_projected_range_measurements)
    assert "dolfinx" not in core_source
    assert "PETSc" not in core_source
    assert "m6b-w13a-diagnostic" not in core_source


def test_w13a_compact_recomputes_measurement_gate_and_hash_bound_evidence() -> None:
    record_path = (
        Path(runner.ROOT)
        / "benchmarks/cases/101_task37_extra_development/records/"
        "m6b_w13a_projected_range_composition.json"
    )
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert runner._evidence_valid(record)
    json.dumps(record, allow_nan=False)
    assert record["status"] == "closed_negative"
    assert record["classification_layers"] == {
        "w13a": "W13A_DIAGNOSTIC_EXECUTION_COMPLETE",
        "w13b": "W13B_FIXED_IMPROVEMENT_GATE_FAIL",
        "overall": "W13B_FIXED_IMPROVEMENT_GATE_FAIL_LOCKED",
    }
    assert record["formal_pass"] is False
    assert record["pde_pass"] is False
    assert record["official_rta"] is False
    assert record["w13b_unlocked"] is False

    expected_artifacts = {
        "run1": {
            "beta1_progress": ("be918dc5e2dd08a0dc3eeb51011f28b1c7eb3376cced8c254c8e5156b964b6f3", None),
            "raw_progress": ("5c273ee4ebf6882557b3054e4fc2b429f575d18db7ed0ca0e3f611f6810ab55c", None),
            "raw_summary": ("1f48247f0cbcabd0128c26076a2a56b101cf11ad9b0d4432cf9ff402263f47c4", "b9e48eeeb67c40d5a09bd8023f4ec3410c88e6931f459643313e6ea6d8e56c7e"),
            "root_pid": ("1244827726038c1317fb1e59bc01ea0cc0d39bb1a4d25b994f25806fe4fe76e2", None),
            "stdout": ("f65e1843404638e8407f980fdfb4f74ba732a83a7e83826a891055b7000f12f7", None),
            "timeline": ("c2ce839169e7a60526c970c2e56cedacda9efb8fe6daf9ceb0e6c909d43026fc", None),
            "watchdog_summary": ("6917e933d9996d1637946df85bd03b2456b3c309159caa0bd1d3b159ede697c3", "3374dfd6e01e1fcb22e678eeaad522c2e90571debcc516c8d9caac210d5ece44"),
            "worker_time": ("09409897bb42a7ac37842413bb4ae8c05f330934e5eab4b11c5937fa0ccaa65d", None),
            "wrapper": ("0a2fba86ea206831e9a5b48808840f4b9f7cf88a69f04eff8c2bbd32d1ea6ab3", None),
        },
        "run2": {
            "beta1_progress": ("84a352acfbc563389288865ef9ec4b46326c572dfe8feb5596d41b0f2b02e2c0", None),
            "beta1_summary": ("38c24668f9d7046404f480110cedf711faaaf29d7a4822a41c97231031d75a6d", "adc243e06a15f594ab16d9469153662caaee1ddd9035cef9981d7656c573f73c"),
            "raw_progress": ("9d41952503c41b0350c3cc8059fd963d8b60e4539f8a914e8deba44fd865ea58", None),
            "raw_summary": ("2bb3520ee4c90fa0cd55bb8799160ecdd049c91472878d210bef36994bec253d", "959d2ab23584ceff7ce1aa945e088bdc2315170121da52de03f1668ab9af5d03"),
            "root_pid": ("7d40ac6f38fd33aeb1df8a918125c1a155b92b92b28534a8cde2dd46a4f63cf8", None),
            "stdout": ("8d2ef51bee7d5b699863580600b703ab511f6fe3f6ccabd9413bc2d4ad51e281", None),
            "timeline": ("6e4bad0bf2073fb4ea4dfa07cc5fdfc953063ec3834005808cadcc18babf9af6", None),
            "watchdog_summary": ("c61b08b5571c02c8219dd0a19948aa32555f2c6357fe09e46b58f740f816b508", "3a4bac116e4ea770750c59d2ed2b1ac9d026558d6d90900508e7b741aca1950a"),
            "worker_time": ("6b0e525b6a70e8857314f3afd24c1d7328ea28d5f69ddc682fb5511a9e841c4a", None),
            "wrapper": ("97c69be4b6cfd1a00d0c5e01f3904e9bb8d3f62bd7ecc6dd907cb3574ab4f445", None),
        },
        "run3": {
            "beta05_progress": ("5d8ec455b2f5ae40f9b684cc24cf807cd0557f63fdb4d2f2da74882c16ccf076", None),
            "beta05_summary": ("7aead7164ef2f7c97c033fe8fc7ff1d2460fc7da254b568e81adb85e4c597a87", "54fff273f2507e8236896f0d38720d610e48a912e38c4a1343b27810cf9f2252"),
            "beta1_progress": ("e66ceecf320a98da6ee2e228e6860fe695071c0757fba90ba6a1e91595668a2e", None),
            "beta1_summary": ("623f3e8723541146a138fe6ce162b5dc10e4f9726eecb7476bd5305e5e2fdae4", "1a421a24f6564aff722cb5d6b5ccaca1ff5ab6a0bcf4a9a68d42a9d9d8d84f95"),
            "raw_progress": ("9c9a906319b186e73f4b4139bd14c9e33497334e707be01397dadb5d21f5de2f", None),
            "raw_summary": ("604869eec33326428354b2f6772a3180ff8a5217a30d3308630b4a3dd661b46e", "b27193c7e43137ce58e26c350a38356962434b586b9790805012f6c64b1ada4e"),
            "root_pid": ("44aeba97b88d01b0e3f65835e17f32aaf7018c79baea5e5754350079f4a5a54a", None),
            "stdout": ("9e02334fd60a9e182d544af9392b8d86fe127c9f4cec04f3071ab078eac1e581", None),
            "timeline": ("e09d8899c8ff4471f07276682d783043c5c95356a3fa9406ad3cc3b455cd4878", None),
            "watchdog_summary": ("57c8462ed6eb01e487f34b80dfcad753ae4b9c73d11842934767afef747b5826", "cd5bf9fa2d9aaa9390cdd65bfff43b119ef1bc0e6041b05c2697f3b09cf6b8d9"),
            "worker_time": ("a53e464216f79debbde3aae30ef02e7b5002cfce65f936edd4945878dfb44ad9", None),
            "wrapper": ("1c09fba02597455f6d71c56a0cc972e5b96e5c080160b91f59704f3f3339ee65", None),
        },
    }
    for run_name, expected in expected_artifacts.items():
        artifacts = record["runs"][run_name]["artifacts"]
        assert set(artifacts) == set(expected)
        for name, (sha256, embedded) in expected.items():
            descriptor = artifacts[name]
            assert descriptor["present"] is True
            assert descriptor["bytes"] > 0
            assert descriptor["path"]
            assert descriptor["sha256"] == sha256
            if embedded is None:
                assert "embedded_evidence_sha256" not in descriptor
            else:
                assert descriptor["embedded_evidence_sha256"] == embedded

    run1 = record["runs"]["run1"]
    assert run1["classification"] == "PRE_SERIALIZATION_EXECUTION_FAIL"
    assert run1["failure_boundary"] == {
        "beta05_started": False,
        "beta05_summary_present": False,
        "beta1_completed": False,
        "error_detail": "json serialization rejected numpy.bool_ produced by all_repeat",
        "error_type": "TypeError",
        "numeric_measurement_available": False,
    }
    run2 = record["runs"]["run2"]
    assert run2["classification"] == "PRE_BETA05_GUARD_EXECUTION_FAIL"
    assert run2["failure_boundary"] == {
        "beta05_child_entered": False,
        "beta05_started": True,
        "beta05_summary_present": False,
        "beta1_completed": True,
        "error_detail": "old ordinary W2/W2R guard remained fixed at beta=1",
        "error_type": "ValueError",
        "numeric_measurement_available": "beta1_only",
    }

    run3 = record["runs"]["run3"]
    assert run3["source"] == {
        "end": {"clean": True, "source_commit_full_sha": "9f5c2c03ad9130c61941a9e58d11c36a589e7be3"},
        "raw_summary_evidence_present": True,
        "start": {"clean": True, "source_commit_full_sha": "9f5c2c03ad9130c61941a9e58d11c36a589e7be3"},
    }
    resource = run3["resource"]
    assert resource["compiler_descendant_pids"] == []
    assert resource["drain"]["gone"] is True
    assert resource["monitor"]["peak_rss_bytes"] == 1717895168
    assert resource["monitor"]["return_code"] == 0
    assert resource["monitor"]["swap_bytes"] == 0
    assert resource["monitor"]["termination"] is None
    assert resource["process_tree_peak_measured"] is True
    assert resource["time"]["max_rss_bytes"] == 1695490048
    assert resource["time"]["swap_bytes"] == 0
    assert run3["lifecycle"] == [
        {"beta": 1.0, "event": "shifted_store_loaded"},
        {"beta": 1.0, "event": "shifted_store_released"},
        {"beta": 0.5, "event": "shifted_store_loaded"},
        {"beta": 0.5, "event": "shifted_store_released"},
    ]
    for role in ("w5_iter200", "w7_cumulative400"):
        measurements = run3["numeric"]["measurements"][role]
        for beta in ("beta1", "beta05"):
            assert measurements[beta]["action_counts"] == {
                "local_apply": 1,
                "physical_outer_action": 5,
                "range_apply": 3,
            }
            assert measurements[beta]["local_exact_shifted_action_count"] == 1
        beta1 = float(measurements["beta1"]["rho_projected"])
        beta05 = float(measurements["beta05"]["rho_projected"])
        ratio = beta05 / beta1
        improvement = 1.0 - ratio
        threshold = 0.95 * beta1
        compact = run3["numeric"]["measurements"][role]
        assert math.isclose(compact["fixed_improvement_gate"]["ratio"], ratio, abs_tol=1e-15)
        assert math.isclose(
            compact["fixed_improvement_gate"]["relative_improvement"],
            improvement,
            abs_tol=1e-15,
        )
        assert math.isclose(compact["fixed_improvement_gate"]["threshold"], threshold, abs_tol=1e-15)
        assert compact["fixed_improvement_gate"]["pass"] is (beta05 <= threshold)
        difference = abs(
            float(measurements["beta1"]["rho_range_only"])
            - float(measurements["beta05"]["rho_range_only"])
        )
        assert compact["cross_beta_range"]["absolute_difference"] == difference == 0.0
    assert run3["numeric"]["fixed_improvement_gate"] is False
    assert record["run3_recomputed"]["process_tree_peak_bytes"] == 1717895168
    assert record["run3_recomputed"]["time_max_rss_bytes"] == 1695490048
