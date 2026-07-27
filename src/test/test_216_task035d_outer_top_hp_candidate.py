from __future__ import annotations

from collections import Counter
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
CANDIDATE_ID = "h15_outer_top_periodic_p5fine_v1"
PLAN = (
    CASE_DIR
    / "records"
    / "h15_outer_top_periodic_p5fine_plan_v1.json"
)
SELECTION = (
    CASE_DIR
    / "records"
    / "outer_top_periodic_p5fine_selection_v1.json"
)


def _module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, CASE_DIR / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_outer_top_hp_plan_physically_removes_fine_p6_interiors() -> None:
    generator = _module(
        "task035d_outer_top_hp_generator",
        "generate_local_h_production_authority.py",
    )
    tracked = json.loads(PLAN.read_text(encoding="utf-8"))

    assert generator.build_plan_payload(CANDIDATE_ID) == tracked
    assert tracked["marked_root_boxes"] == [
        {
            "lower": [41.75, 0.0, 120.0],
            "upper": [50.0, 12.5, 130.0],
        }
    ]
    assert tracked["expected_forest"]["closure_counts"] == {
        "balance": 0,
        "material": 0,
        "periodic": 3,
        "user": 1,
    }
    assert tracked["expected_forest"]["leaf_cell_count"] == 148
    assert tracked["expected_forest"]["hanging_patch_count"] == 8
    assert Counter(
        row["degree"] for row in tracked["cell_interior_degrees"]
    ) == Counter({5: 32, 6: 116})
    p5_rows = [
        row
        for row in tracked["cell_interior_degrees"]
        if row["degree"] == 5
    ]
    assert all(
        row["upper"][0] - row["lower"][0] <= 4.25
        and row["upper"][1] - row["lower"][1] == 6.25
        and row["upper"][2] - row["lower"][2] == 5.0
        and row["lower"][2] >= 120.0
        for row in p5_rows
    )
    assert "selected_p6_face_geometry_keys" not in tracked
    assert tracked["provenance"]["accuracy_credit"] is False
    assert tracked["provenance"]["complete_combined_hp_credit"] is False


def test_outer_top_hp_selection_closes_face_lane_and_bounds_one_pde() -> None:
    analyzer = _module(
        "task035d_outer_top_hp_selection",
        "analyze_outer_top_hp_selection.py",
    )
    tracked = json.loads(SELECTION.read_text(encoding="utf-8"))
    rebuilt = analyzer.analyze()

    assert rebuilt == tracked
    assert tracked["pass"] is True
    assert (
        tracked["selective_face_lane"]["decision"]
        == "close_top_port_selective_p6_face_lane"
    )
    subset = tracked["selective_face_lane"][
        "linear_signed_dwr_subset_screen"
    ]
    assert subset["subset_count"] == 32
    assert subset["no_subset_predicts_12_plus_12"] is True
    assert subset["maximum_predicted_power_pass_count"] <= 6
    assert subset["maximum_predicted_complex_amplitude_pass_count"] <= 7
    oracle = tracked["location_oracle"]
    assert oracle["outer_to_right_inner_support_ratio"] > 2.9
    assert (
        oracle["outer_periodic_failed_19_negative_error_dot_action"] > 0.0
    )
    assert (
        oracle["right_inner_failed_19_negative_error_dot_action"] < 0.0
    )
    action = tracked["selected_action"]
    assert action["predicted_actual_conforming_active_fe_dofs"] == 84_850
    assert action["predicted_direct_solve_rows"] == 20_360
    assert action["selected_p6_face_count"] == 0
    assert action["success_forecast"] is False
