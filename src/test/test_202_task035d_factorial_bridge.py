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
BRIDGE_ID = "h15_top_air_remote_p5_interior_bridge_v1"
BRIDGE_PLAN = (
    CASE_DIR
    / "records"
    / "h15_top_air_remote_p5_interior_bridge_plan_v1.json"
)
ONE_SIDED_PLAN = CASE_DIR / "records" / "h15_top_air_local_h_plan_v1.json"


def _generator_module():
    path = CASE_DIR / "generate_local_h_production_authority.py"
    spec = importlib.util.spec_from_file_location(
        "task035d_local_h_production_authority",
        path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load the Task035d authority generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _analysis_module():
    path = CASE_DIR / "analyze_hp_factorial_bridge.py"
    spec = importlib.util.spec_from_file_location(
        "task035d_hp_factorial_bridge_analysis",
        path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load the Task035d factorial analyzer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_factorial_bridge_plan_is_exact_one_sided_h_plus_remote_pdown() -> None:
    module = _generator_module()
    generated = module.build_plan_payload(BRIDGE_ID)
    tracked = json.loads(BRIDGE_PLAN.read_text(encoding="utf-8"))
    one_sided = json.loads(ONE_SIDED_PLAN.read_text(encoding="utf-8"))

    assert generated == tracked
    assert tracked["marked_root_boxes"] == one_sided["marked_root_boxes"]
    assert tracked["expected_forest"] == one_sided["expected_forest"]
    assert tracked["trace_degree"] == 5
    assert tracked["cell_interior_degree"] == 6
    assert Counter(
        row["degree"] for row in tracked["cell_interior_degrees"]
    ) == Counter({6: 102, 5: 32})

    p5_boxes = {
        (
            *map(float, row["lower"]),
            *map(float, row["upper"]),
        )
        for row in tracked["cell_interior_degrees"]
        if row["degree"] == 5
    }
    assert len(p5_boxes) == 32
    assert all(
        lower_z >= 0.0
        and upper_z <= 120.0
        and (upper_x <= 8.25 or lower_x >= 41.75)
        for (
            lower_x,
            _lower_y,
            lower_z,
            upper_x,
            _upper_y,
            upper_z,
        ) in p5_boxes
    )
    assert tracked["provenance"]["factorial_bridge"] is True
    assert tracked["provenance"]["accuracy_credit"] is False
    assert tracked["provenance"]["complete_combined_hp_credit"] is False


def test_factorial_attribution_closes_remote_interior_pdown_lane() -> None:
    result = _analysis_module().analyze_factorial_bridge()

    assert result["pass"] is True
    assert (
        result["status"]
        == "remote_p5_interior_lane_closed_controlled_negative"
    )
    attribution = result["attribution"]
    assert attribution["A_pass_counts"] == {"power": 6, "amplitude": 6}
    assert attribution["B_pass_counts"] == {"power": 4, "amplitude": 4}
    assert attribution["D_pass_counts"] == {"power": 4, "amplitude": 4}
    assert attribution["A_to_B_lost_power_passes"] == 2
    assert attribution["A_to_B_gained_power_passes"] == 0
    assert attribution["A_to_B_lost_amplitude_passes"] == 2
    assert attribution["A_to_B_gained_amplitude_passes"] == 0
    assert attribution["B_and_D_same_pass_mask"] is True
    assert result["lane_decision"]["formal_negative_signal_count"] == 2
    assert result["lane_decision"]["closed"] is True
    assert result["lane_decision"]["eight_cell_C_discriminator"] == "not_run"
    assert result["selection_credit"]["actual_channel_dwr"] is False
