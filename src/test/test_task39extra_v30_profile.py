"""V30 input selects the reviewed exact H6 diagonal and monitor policy."""
from pathlib import Path

from src.io import load_and_resolve
from src.io.physical_intermediate_profile import (
    PROJECTION_LAYOUT_V31_PROFILE,
    WORKSTATION_GUIDED_LOCAL_V30_PROFILE,
    profile_facts,
)
from src.runners import task038_full3d_iterative as dispatch
from src.io.run_specification import thaw


ROOT = Path(__file__).resolve().parents[2]
V29_INPUT = ROOT / "input/task39extra/v29_a4_tensor_h6_original_h7p5.dat"
V30_INPUT = ROOT / "input/task39extra/v30_workstation_guided_original_h7p5.dat"
V31_INPUT = ROOT / "input/task39extra/v31_projection_layout_original_h7p5.dat"


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


def test_v31_input_is_h6_only_natural_order_and_dispatches_through_own_ledger(
    monkeypatch, tmp_path, capsys
):
    v30 = load_and_resolve(V30_INPUT)
    v31 = load_and_resolve(V31_INPUT)
    facts = profile_facts(PROJECTION_LAYOUT_V31_PROFILE)
    payload = v31.as_jsonable()
    assert v31.identity["run_id"] == (
        "task39extra_v31_projection_layout_original_h7p5_v1"
    )
    assert v31.identity["comparison_group"] == (
        "review_v29_evidence_and_projection_v31"
    )
    assert v31.solver["preconditioner"] == PROJECTION_LAYOUT_V31_PROFILE
    assert v31.physical_model_sha256 == v30.physical_model_sha256
    for section in ("geometry", "materials", "incidence", "discretization", "boundary"):
        assert v31.as_jsonable()[section] == v30.as_jsonable()[section]
    route = facts["route_selection"]
    assert route["h6_projection_layout_v31"] == "natural_order_internal"
    assert route["h6_fixed_projection_matmul"] is False
    assert route["a6_projection_layout"] == "unchanged_v30_route"
    assert route["a4_projection_layout"] == "unchanged_v30_route"
    assert facts["gates"]["h6_natural_order_internal"] is True
    assert facts["resources"]["pss_sampling_policy"] == "disabled_by_profile"
    assert payload["derived"]["physical_intermediate_profile"] == thaw(facts)

    from scripts.run_case import main as run_case_main

    assert run_case_main(
        [str(V31_INPUT), "--validate-only", "--v14-time-policy", "observe_only"]
    ) == 0
    capsys.readouterr()

    worker = {}

    def fake_worker(resolved_payload, run_directory, **kwargs):
        worker.update(kwargs)
        worker["payload"] = resolved_payload
        worker["run_directory"] = run_directory
        return {"mock_worker": True}

    from src.runners import physical_dual_cell_condensed_lowmem_v20 as lowmem

    monkeypatch.setattr(
        lowmem, "_run_physical_dual_cell_condensed_lowmem", fake_worker
    )
    assert dispatch.run_full3d_iterative(
        payload, tmp_path / "v31-worker", source_sha="e" * 40
    ) == {"mock_worker": True}
    assert worker["profile_identity"] == PROJECTION_LAYOUT_V31_PROFILE
    assert worker["allowed_stages"] == ("Q4_ORIGINAL",)
    assert worker["batch_identity"] == "review_v29_evidence_and_projection_v31"
    assert worker["evidence_prefix"] == "v31q4"
    assert worker["summary_schema"] == (
        "task039extra.v31.projection-layout.worker-summary.v1"
    )
    assert worker["require_zero_swap"] is False
