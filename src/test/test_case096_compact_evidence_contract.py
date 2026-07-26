from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CASE = ROOT / "benchmarks/cases/096_hybrid_channel_memory_closure"
RECORDS = CASE / "records"


def _load(name: str) -> dict[str, Any]:
    payload = json.loads((RECORDS / name).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _channel_map(model: dict[str, Any]) -> dict[tuple[Any, ...], dict[str, Any]]:
    return {tuple(row["key"]): row for row in model["channels"]}


def _pairwise_recompute(
    left: dict[str, Any],
    right: dict[str, Any],
) -> tuple[int, int, float, float]:
    left_rows = _channel_map(left)
    right_rows = _channel_map(right)
    keys = [
        key
        for key in sorted(left_rows)
        if max(left_rows[key]["power"], right_rows[key]["power"]) >= 1.0e-8
    ]
    power_errors = []
    amplitude_errors = []
    for key in keys:
        left_row = left_rows[key]
        right_row = right_rows[key]
        left_power = float(left_row["power"])
        right_power = float(right_row["power"])
        power_errors.append(
            abs(right_power - left_power)
            / max(abs(left_power), abs(right_power), 1.0e-8)
        )
        left_amplitude = complex(*left_row["boundary_complex_amplitude"])
        right_amplitude = complex(*right_row["boundary_complex_amplitude"])
        amplitude_errors.append(
            abs(right_amplitude - left_amplitude)
            / max(abs(left_amplitude), abs(right_amplitude), 1.0e-15)
        )
    return (
        sum(error <= 1.0e-3 for error in power_errors),
        sum(error <= 1.0e-3 for error in amplitude_errors),
        max(power_errors),
        max(amplitude_errors),
    )


def test_case096_manifest_binds_every_compact_record() -> None:
    manifest = _load("compact_authority_v1.json")
    assert manifest["status"] == "case096_compact_authority"
    assert manifest["record_count"] == 5
    assert manifest["ordinary_default_changed"] is False
    assert manifest["numerical_source_sha"] == (
        "244b62e1fb4f299a468363cf90a2dd548dc34ff6"
    )
    for row in manifest["records"]:
        path = RECORDS / row["name"]
        assert path.is_file()
        assert _sha256(path) == row["sha256"]
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["schema_version"] == row["schema_version"]
        assert payload["status"] == row["status"]


def test_case096_p6_six_path_channels_are_independently_recomputable() -> None:
    record = _load("p6_h10_mpi8_six_path_v1.json")
    assert record["pass"] is True
    assert len(record["models"]) == 6
    assert all(
        model["source_sha"] == record["numerical_source_sha"]
        for model in record["models"].values()
    )
    for comparison in record["pairwise_channel_comparisons"].values():
        left = record["models"][comparison["left"]]
        right = record["models"][comparison["right"]]
        power_count, amplitude_count, max_power, max_amplitude = (
            _pairwise_recompute(left, right)
        )
        assert power_count == comparison["power_pass_count"] == 12
        assert amplitude_count == comparison["complex_amplitude_pass_count"] == 12
        assert math.isclose(
            max_power,
            comparison["max_power_relative_error"],
            rel_tol=0.0,
            abs_tol=1.0e-20,
        )
        assert math.isclose(
            max_amplitude,
            comparison["max_complex_amplitude_relative_error"],
            rel_tol=0.0,
            abs_tol=1.0e-20,
        )
        assert comparison["pass"] is True
    for gate in record["frozen_reference_v1_gates"].values():
        assert gate["channel_count"] == 12
        assert sum(row["power_pass"] for row in gate["channels"]) == 12
        assert sum(row["complex_amplitude_pass"] for row in gate["channels"]) == 12
        assert gate["pass"] is True


def test_case096_resource_gates_are_recomputed_from_models() -> None:
    record = _load("p6_h10_mpi8_six_path_v1.json")
    models = record["models"]
    for modes in (120, 160):
        standard = models[f"hybrid_standard_m{modes}"]
        static = models[f"hybrid_static_m{modes}"]
        gate = record["resource_comparisons"][
            f"m{modes}_standard_vs_static"
        ]
        memory_saving = (
            standard["peak_memory_gib"] - static["peak_memory_gib"]
        ) / standard["peak_memory_gib"]
        modal_memory_saving = (
            standard["modal_coupling_stage_peak_gib"]
            - static["modal_coupling_stage_peak_gib"]
        ) / standard["modal_coupling_stage_peak_gib"]
        total_ratio = static["total_seconds"] / standard["total_seconds"]
        modal_ratio = (
            static["modal_coupling_seconds"]
            / standard["modal_coupling_seconds"]
        )
        assert math.isclose(
            memory_saving,
            gate["memory_saving_fraction"],
            rel_tol=0.0,
            abs_tol=1.0e-15,
        )
        assert math.isclose(
            modal_memory_saving,
            gate["modal_coupling_stage_memory_saving_fraction"],
            rel_tol=0.0,
            abs_tol=1.0e-15,
        )
        assert math.isclose(
            total_ratio,
            gate["static_to_standard_total_time_ratio"],
            rel_tol=0.0,
            abs_tol=1.0e-15,
        )
        assert math.isclose(
            modal_ratio,
            gate["static_to_standard_modal_coupling_time_ratio"],
            rel_tol=0.0,
            abs_tol=1.0e-15,
        )
        assert gate["mandatory_15_percent_pass"] is True
        assert gate["preferred_25_percent_pass"] is True
        assert gate["user_target_50_percent_pass"] is False
        assert gate["total_time_1p35_gate_pass"] is True
        assert gate["modal_time_is_report_only_not_hard_gate_by_user"] is True
        assert gate["pass"] is True


def test_case096_p2_and_rank_negatives_are_preserved() -> None:
    p2 = _load("p2_h5_root_cause_v1.json")
    assert p2["pass"] is True
    assert all(item["pass"] for item in p2["comparisons"].values())
    phase = p2["phase_only_controlled_negative"]
    assert phase["classification"] == "controlled_negative"
    assert phase["comparison"]["power_pass_count"] == 4
    assert phase["comparison"]["complex_amplitude_pass_count"] == 4
    assert phase["comparison"]["pass"] is False

    rank = _load("p6_h10_static_rank_study_v1.json")
    mpi1 = rank["classification"]["mpi1"]
    assert mpi1["status"] == "failed_numerical_gate"
    assert mpi1["actual"] == 1.1975997613347697e-6
    assert mpi1["actual"] > mpi1["limit"]
    mpi2 = rank["classification"]["mpi2"]
    assert mpi2["status"] == "numeric_pass_resource_nonformal"
    assert mpi2["numeric_pass"] is True
    assert mpi2["resource_authority_pass"] is False
    assert rank["classification"]["mpi8"]["status"] == "formal_pass"


def test_case096_scope_and_dependency_failure_contract() -> None:
    config = json.loads((CASE / "config.json").read_text(encoding="utf-8"))
    assert config["ordinary_default"] == "standard_full"
    assert config["ordinary_default_changed"] is False
    assert config["out_of_scope"]["p3_h7p5"] == (
        "out_of_scope_by_user_not_run_not_completion_gate"
    )
    ledger = _load("execution_ledger_v1.json")
    p3 = next(row for row in ledger["entries"] if row["lane"] == "p3_h7p5")
    assert p3 == {
        "lane": "p3_h7p5",
        "classification": "out_of_scope_by_user",
        "execution": "not_run",
        "completion_gate": False,
    }
    failures = _load("dependency_failures_v1.json")["failures"]
    assert len(failures) == 3
    assert sum(
        row["classification"] == "failed_dependency_exception"
        for row in failures
    ) == 2
    assert all(row["later_success_does_not_delete_this_evidence"] for row in failures)
