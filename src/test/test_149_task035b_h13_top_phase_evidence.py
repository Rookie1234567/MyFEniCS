"""Contracts for the formal h13 top-phase redistribution evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RECORDS = (
    ROOT
    / "benchmarks"
    / "cases"
    / "095_high_order_local_hp_resource_envelope"
    / "records"
)
BASE_RECORD = RECORDS / "fixed_p5trace_p6interior_h13_directional_z_mpi8.json"
TOP_PHASE_RECORD = (
    RECORDS
    / "fixed_p5trace_p6interior_h13_top2_phase_redistribution_mpi8_v1.json"
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _failed_union(record: dict) -> set[tuple[str, int, int, str]]:
    return {
        (
            channel["side"],
            channel["m"],
            channel["n"],
            channel["polarization"],
        )
        for channel in record["diffraction_channel_comparison"]["channels"]
        if not channel["power_pass"]
        or not channel["complex_amplitude_pass"]
    }


def test_top_phase_record_is_hash_and_clean_source_bound() -> None:
    record = _load(TOP_PHASE_RECORD)

    assert _sha256(TOP_PHASE_RECORD) == (
        "ff12b909aa1c75dcf15246ba48a8169bf9653d13ddf36709c46367217d799b4b"
    )
    assert record["source"]["commit_sha"] == (
        "7e4a2eb4ab5096d88b9e79b176b1e3778767caa4"
    )
    assert record["source"]["verified_clean_sha"] == (
        record["source"]["commit_sha"]
    )
    assert record["source"]["tracked_source_dirty"] is False
    assert record["source"]["stable_and_clean_after"] is True
    assert record["qualification"]["pass"] is True
    assert record["ordinary_default_changed"] is False
    assert record["terminated_for_memory"] is False
    assert record["terminated_for_timeout"] is False


def test_top_phase_mesh_and_resource_identity_are_frozen() -> None:
    record = _load(TOP_PHASE_RECORD)
    target = record["target_identity"]
    candidate = record["candidate"]
    mesh = candidate["high_order_resource_audit"]["mesh_identity"]

    assert target["geometry"] == "Task034 fixed rectangular block grating"
    assert target["explicit_z_profile"] == (
        "h13_top2_phase_redistribution_v1"
    )
    assert target["directional_mesh_change_semantics"] == (
        "fixed_dof_h13_top2_phase_redistribution_not_refinement"
    )
    assert target["mesh_axis_cell_counts_requested"] == [6, 2, 12]
    assert target["trace_degree"] == 5
    assert target["interior_degree"] == 6
    assert mesh["partition_independent_mesh_sha256"] == (
        "6d4bf800caedc07020e8d93e8fdb49cac4abd0e71a2cc29d1aea88f3a2927b08"
    )
    assert mesh["cell_tag_sha256"] == (
        "46d288e1fae15f801988516b1579ecc14285f1472a9220f451cfa89efb6ef71e"
    )
    assert mesh["facet_tag_sha256"] == (
        "442cd53e48103cfe55224a270b04c92cc61032ac128a5490d5349936d7d850d5"
    )
    assert mesh["material_plane_alignment"]["all_aligned"] is True
    assert candidate["mpi_size"] == 8
    assert candidate["num_mesh_cells"] == 144
    assert candidate["num_nedelec_dofs"] == 89_740
    assert record["dof_target"]["minimum_le_90000"] is True
    assert record["dof_target"][
        "inactive_p6_trace_modes_physically_absent"
    ] is True


def test_top_phase_is_a_controlled_negative_despite_valid_core_gates() -> None:
    record = _load(TOP_PHASE_RECORD)
    candidate = record["candidate"]
    channels = record["diffraction_channel_comparison"]
    resources = record["resource_authority"]

    assert record["status"] == "actual_fixed_trace_controlled_negative"
    assert record["candidate_accuracy_pass"] is False
    assert record["formal_candidate_eligible"] is False
    assert candidate["linear_system_relative_residual"] <= 1.0e-9
    assert record["observable_comparison"]["pass"] is True
    assert record["selected_field_interface_error_gate"]["pass"] is True
    assert channels["thresholds_relaxed"] is False
    assert channels["significant_power_pass_count"] == 8
    assert channels["significant_complex_amplitude_pass_count"] == 8
    assert channels["pass"] is False
    assert _failed_union(record) == {
        ("bottom", -5, 0, "s"),
        ("bottom", -4, 0, "s"),
        ("top", -5, 0, "s"),
        ("top", -4, 0, "s"),
        ("top", -2, 0, "s"),
    }
    assert resources["max_process_tree_rss_mb"] == 6027.64453125
    assert resources["max_worker_rank_pss_sum_mb"] == 4603.876953125
    assert resources["max_worker_rank_uss_sum_mb"] == 4419.78515625
    assert resources["max_process_tree_swap_mb"] == 0.0


def test_positive_seed_signal_does_not_hide_regression_from_best_h13() -> None:
    base = _load(BASE_RECORD)
    candidate = _load(TOP_PHASE_RECORD)
    signal = candidate["directional_recovery_signal"]
    base_channels = base["diffraction_channel_comparison"]
    candidate_channels = candidate["diffraction_channel_comparison"]

    assert _sha256(BASE_RECORD) == (
        "81ba43d91c4c9a35121676ae40368d56116f3a381e4559d630fb547a94dc4a5c"
    )
    assert signal["status"] == "positive_seed_recovery_signal"
    assert signal["positive_signal"] is True
    assert signal["seed_power_pass_count"] == 6
    assert signal["candidate_power_pass_count"] == 8
    assert signal["seed_complex_amplitude_pass_count"] == 7
    assert signal["candidate_complex_amplitude_pass_count"] == 8
    assert signal["power_relative_error_reduction"] > 0.7
    assert signal["amplitude_relative_error_reduction"] > 0.3

    assert base_channels["significant_power_pass_count"] == 10
    assert base_channels["significant_complex_amplitude_pass_count"] == 10
    assert candidate_channels["significant_power_pass_count"] == 8
    assert candidate_channels["significant_complex_amplitude_pass_count"] == 8
    assert _failed_union(base) == {
        ("bottom", -4, 0, "s"),
        ("top", -5, 0, "s"),
        ("top", -4, 0, "s"),
    }
    assert _failed_union(candidate) > _failed_union(base)
