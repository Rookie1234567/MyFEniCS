from __future__ import annotations

from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CASE_DIR = (
    ROOT
    / "benchmarks"
    / "cases"
    / "097_goal_oriented_exact_sequence_hp_adaptivity"
)
RECORDS = CASE_DIR / "records"
CANDIDATE_ID = "h15_left_grating_top_closure_p5fine_v1"
SELECTION = (
    RECORDS / "bounded_single_seed_top_air_hp_selection_v2.json"
)
PLAN = (
    RECORDS / "h15_left_grating_top_closure_p5fine_plan_v1.json"
)
LANE_CLOSURE = (
    RECORDS / "bounded_single_root_top_air_lane_closure_v1.json"
)
ANALYZER_RELATIVE = (
    "benchmarks/cases/"
    "097_goal_oriented_exact_sequence_hp_adaptivity/"
    "analyze_bounded_single_seed_top_air_hp_selection.py"
)


def _module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, CASE_DIR / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_bounded_single_seed_selection_is_narrow_and_cost_dominant() -> None:
    selection = json.loads(SELECTION.read_text(encoding="utf-8"))
    assert selection["pass"] is True
    assert (
        selection["status"]
        == "bounded_single_seed_top_air_hp_selection_pass"
    )
    assert (
        set(selection["source_identity"]["file_sha256"])
        == set(selection["inputs"]) | {ANALYZER_RELATIVE}
    )
    assert (
        selection["source_identity"][
            "verified_clean_algorithm_and_inputs"
        ]
        is True
    )
    assert (
        selection["frozen_ten_face_subset_lane"]["decision"]
        == "close_frozen_ten_face_subset_lane"
    )
    assert (
        selection["frozen_ten_face_subset_lane"][
            "whole_top_port_selective_p6_lane"
        ]
        == "not_closed_unrun_faces_orbits_and_edge_modes_remain"
    )
    assert selection["multi_seed_combinations"]["status"] == "not_evaluated"

    rows = {
        row["action_id"]: row
        for row in selection["location_oracle"]["action_rows"]
    }
    outer = rows["outer_periodic"]
    selected = rows["left_grating_top"]
    assert (
        outer[
            "failed_19_closure_combined_absolute_normalized_support"
        ]
        < outer["failed_19_sum_band_absolute_normalized_support"]
    )
    assert (
        selected["failed_19_negative_error_dot_action"]
        > outer["failed_19_negative_error_dot_action"]
    )
    assert (
        selected["alignment_per_1000_added_active_fe_dofs"]
        > outer["alignment_per_1000_added_active_fe_dofs"]
    )
    assert (
        selected["alignment_per_1000_added_solve_rows"]
        > outer["alignment_per_1000_added_solve_rows"]
    )
    unavailable = rows["left_inner_without_compact_dwr"]
    assert unavailable["dwr_status"] == "not_available_from_compact"
    assert unavailable["ranking_eligible"] is False

    action = selection["selected_action"]
    assert action["candidate_id"] == CANDIDATE_ID
    assert action["actual_full3d_equivalent_active_fe_dofs"] == 88_915
    assert action["predicted_direct_solve_rows"] == 21_650
    assert action["actual_local_h_dwr_surplus_available"] is False
    assert action["success_forecast"] is False


def test_selected_plan_physically_omits_fine_child_p6_interiors() -> None:
    generator = _module(
        "task035d_left_grating_top_generator",
        "generate_local_h_production_authority.py",
    )
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    assert generator.build_plan_payload(CANDIDATE_ID) == plan
    assert plan["marked_root_boxes"] == [
        {
            "lower": [16.5, 0.0, 120.0],
            "upper": [25.0, 12.5, 130.0],
        }
    ]
    assert plan["expected_forest"]["closure_counts"] == {
        "balance": 0,
        "material": 4,
        "periodic": 1,
        "user": 1,
    }
    assert plan["expected_forest"]["leaf_cell_count"] == 162
    assert plan["expected_forest"]["hanging_patch_count"] == 14
    assert Counter(
        int(row["degree"]) for row in plan["cell_interior_degrees"]
    ) == Counter({5: 48, 6: 114})
    assert "selected_p6_face_geometry_keys" not in plan
    authority = plan["provenance"]["selection_authority"]
    assert authority["path"] == str(SELECTION.relative_to(ROOT))
    assert authority["sha256"] == _sha256(SELECTION)
    assert authority["location_oracle_only"] is True
    assert authority["actual_local_h_dwr_surplus_available"] is False
    assert (
        plan["provenance"][
            "single_seed_closure_catalog_complete_for_available_compact_dwr"
        ]
        is True
    )
    assert plan["provenance"]["accuracy_credit"] is False
    assert plan["provenance"]["complete_combined_hp_credit"] is False


def test_bounded_single_root_lane_closes_without_overclaiming() -> None:
    closure = json.loads(LANE_CLOSURE.read_text(encoding="utf-8"))
    assert closure["pass"] is True
    assert closure["production_qualified"] is False
    assert (
        closure["status"]
        == "bounded_single_root_top_air_local_h_lane_closed"
    )
    assert (
        closure["lane"]["status"]
        == "closed_after_two_formal_accuracy_negatives"
    )
    assert closure["lane"]["formal_interior_variants"] == [
        {
            "candidate_id": "h15_top_air_local_h_v1",
            "fine_child_degree": 6,
        },
        {
            "candidate_id": CANDIDATE_ID,
            "fine_child_degree": 5,
        },
    ]

    negatives = closure["formal_negative_signals"]
    assert [row["candidate_id"] for row in negatives] == [
        "h15_top_air_local_h_v1",
        CANDIDATE_ID,
    ]
    assert all(
        row["accuracy_status"] == "controlled_negative"
        for row in negatives
    )
    assert [
        (
            row["significant_power_pass_count"],
            row["significant_complex_amplitude_pass_count"],
        )
        for row in negatives
    ] == [(6, 6), (4, 6)]

    tracked_bindings = [
        negatives[0]["record"],
        negatives[1]["full_checker"],
        negatives[1]["compact_checker"],
        closure["remaining_actions"]["outer_periodic"][
            "historical_stop_record"
        ],
        closure["remaining_actions"][
            "frozen_ten_face_selective_p6_subset"
        ]["record"],
    ]
    for binding in tracked_bindings:
        path = ROOT / binding["path"]
        assert path.is_file()
        assert _sha256(path) == binding["sha256"]

    remaining = closure["remaining_actions"]
    outer = remaining["outer_periodic"]
    assert outer["status"] == "not_run_by_lane_stop"
    assert outer["pde_failure"] is False
    assert (
        remaining["multi_seed_combinations"]["status"]
        == "not_evaluated_by_stop_rule"
    )
    assert (
        remaining["frozen_ten_face_selective_p6_subset"]["status"]
        == "closed_controlled_negative"
    )
    assert (
        remaining["whole_top_port_selective_p6_trace"]["status"]
        == "incomplete_not_run_no_authorized_candidate"
    )
    assert (
        remaining["hybrid_phase_f"]["status"]
        == "not_run_full3d_hp_gate_failed"
    )

    credit = closure["selection_credit"]
    assert credit["compact_dwr_location_oracle"] is True
    assert credit["actual_local_h_dwr_surplus"] is False
    assert credit["actual_channel_dwr"] is False
    assert credit["goal_oriented_selection_credit"] is False
    assert credit["complete_combined_hp_credit"] is False
    assert closure["ordinary_default_changed"] is False
