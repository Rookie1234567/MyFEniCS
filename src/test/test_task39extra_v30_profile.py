"""V30 input selects the reviewed exact H6 diagonal and monitor policy."""
from pathlib import Path

from src.io import load_and_resolve
from src.io.physical_intermediate_profile import (
    WORKSTATION_GUIDED_LOCAL_V30_PROFILE,
    profile_facts,
)
from src.io.run_specification import thaw


ROOT = Path(__file__).resolve().parents[2]
V29_INPUT = ROOT / "input/task39extra/v29_a4_tensor_h6_original_h7p5.dat"
V30_INPUT = ROOT / "input/task39extra/v30_workstation_guided_original_h7p5.dat"


def test_v30_input_is_physical_v29_inheritance_with_selected_l2_and_l1():
    v29 = load_and_resolve(V29_INPUT)
    v30 = load_and_resolve(V30_INPUT)
    assert v30.identity["run_id"] == (
        "task39extra_v30_workstation_guided_original_h7p5_v1"
    )
    assert v30.identity["comparison_group"] == (
        "review_v28_workstation_guided_local_v30"
    )
    assert v30.solver["preconditioner"] == WORKSTATION_GUIDED_LOCAL_V30_PROFILE
    assert v30.physical_model_sha256 == v29.physical_model_sha256
    for section in ("geometry", "materials", "incidence", "discretization", "boundary"):
        assert v30.as_jsonable()[section] == v29.as_jsonable()[section]

    v29_text = V29_INPUT.read_text(encoding="utf-8")
    expected_v30_text = (
        v29_text.replace("# V29:", "# V30:", 1)
        .replace(
            "task39extra_v29_a4_tensor_h6_original_h7p5_v1",
            "task39extra_v30_workstation_guided_original_h7p5_v1",
            1,
        )
        .replace(
            "review_v27_a4_tensor_h6_continue_outer",
            "review_v28_workstation_guided_local_v30",
            1,
        )
        .replace(
            "physical_p6_trace_a4_tensor_h6_v29",
            "physical_p6_trace_workstation_guided_v30",
            1,
        )
    )
    assert V30_INPUT.read_text(encoding="utf-8") == expected_v30_text

    facts = profile_facts(WORKSTATION_GUIDED_LOCAL_V30_PROFILE)
    assert facts["route_selection"]["h6_diagonal_builder"] == (
        "reference_energy_actual_affine_metric_v1"
    )
    assert facts["resources"]["pss_sampling_policy"] == "disabled_by_profile"
    assert v30.as_jsonable()["derived"]["physical_intermediate_profile"] == thaw(
        facts
    )


def test_v30_input_validate_only(capsys):
    from scripts.run_case import main as run_case_main

    assert run_case_main(
        [str(V30_INPUT), "--validate-only", "--v14-time-policy", "observe_only"]
    ) == 0
    capsys.readouterr()
