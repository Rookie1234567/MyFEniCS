"""V30 input selects the reviewed exact H6 diagonal and monitor policy."""
import hashlib
import json
from pathlib import Path

import pytest

from src.io import load_and_resolve
from src.io.input_loader import InputError
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
V31_COMPLETION_INPUT = ROOT / (
    "input/task39extra/"
    "v31_projection_layout_original_h7p5_user_authorized_recovery_v1.dat"
)


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


def test_v31_authorized_completion_input_is_identity_only_and_whitelisted(tmp_path):
    original = load_and_resolve(V31_INPUT)
    completion = load_and_resolve(V31_COMPLETION_INPUT)
    old_lines = V31_INPUT.read_text(encoding="utf-8").splitlines()
    new_lines = V31_COMPLETION_INPUT.read_text(encoding="utf-8").splitlines()
    assert [i for i, pair in enumerate(zip(old_lines, new_lines), 1) if pair[0] != pair[1]] == [1, 4, 5]
    assert completion.physical_model_sha256 == original.physical_model_sha256
    for section in (
        "geometry", "materials", "incidence", "discretization", "boundary",
        "method", "solver", "execution", "output",
    ):
        assert completion.as_jsonable()[section] == original.as_jsonable()[section]
    invalid = tmp_path / "v31_unapproved_identity.dat"
    invalid.write_text(
        V31_COMPLETION_INPUT.read_text(encoding="utf-8").replace(
            "task39extra_v31_projection_layout_original_h7p5_user_authorized_recovery_v1",
            "task39extra_v31_projection_layout_original_h7p5_unapproved_v1",
            1,
        ),
        encoding="utf-8",
    )
    with pytest.raises(InputError, match="explicitly allowed run_id"):
        load_and_resolve(invalid)


def test_v31_authorized_completion_reservation_preserves_ledger_and_cost(tmp_path):
    from src.runners import task038_launcher as launcher

    measured = 10.0
    old_source = "b" * 40
    old_run = tmp_path / "results/old_v31_attempt"
    old_attempt = {
        "attempt": 1,
        "status": "USER_CONTROLLED_STOP",
        "watchdog_classification": "USER_CONTROLLED_STOP",
        "source_sha": old_source,
        "run_directory": str(old_run),
        "reserved_seconds": launcher.V31_WORKFLOW_BUDGET_SECONDS,
        "settled_seconds": measured,
        "actual_elapsed_seconds": measured,
        "replay": False,
        "bug_replay_count_before": 0,
    }
    ledger = {
        "schema": launcher.V31_PROJECTION_LAYOUT_LEDGER_SCHEMA,
        "batch_identity": launcher.V31_PROJECTION_LAYOUT_BATCH_IDENTITY,
        "total_budget_seconds": launcher.V31_WORKFLOW_BUDGET_SECONDS,
        "elapsed_seconds": measured,
        "conservative_allowance_seconds": 0.0,
        "policy_debits": [],
        "fresh_worker_count": 1,
        "source_attempts": [{"stage": "Q4_ORIGINAL", "source_sha": old_source, "attempt": 1}],
        "stages": {"Q4_ORIGINAL": {"attempts": [old_attempt], "active_attempt": None}},
        "unique_bug_replay_count": 0,
        "allowed_stages": ["Q4_ORIGINAL"],
    }
    ledger_path = (
        tmp_path / "benchmarks/artifacts/task39extra/projection_layout_v31/"
        "review_v29_evidence_and_projection_v31/shared_workflow_ledger.json"
    )
    ledger_path.parent.mkdir(parents=True)
    ledger_bytes = json.dumps(ledger, sort_keys=True).encode("utf-8")
    ledger_path.write_bytes(ledger_bytes)
    input_sha = hashlib.sha256(V31_COMPLETION_INPUT.read_bytes()).hexdigest()
    auth = json.loads(
        (ROOT / launcher.V31_AUTHORIZED_COMPLETION_RECORD).read_text(encoding="utf-8")
    )
    auth["prior_ledger_sha256"] = hashlib.sha256(ledger_bytes).hexdigest()
    auth["prior_attempt"]["measured_elapsed_seconds"] = measured
    auth_path = tmp_path / launcher.V31_AUTHORIZED_COMPLETION_RECORD
    auth_path.parent.mkdir(parents=True)
    auth_path.write_text(json.dumps(auth, sort_keys=True), encoding="utf-8")
    run_directory = tmp_path / (
        "results/" + launcher.V31_AUTHORIZED_COMPLETION_RUN_ID
        + "__full3d_iterative__mpi1__Mna/20260929T120000.000000Z"
    )
    kwargs = {
        "source_sha": "c" * 40,
        "stage": "Q4_ORIGINAL",
        "stage_budget": {"workflow_seconds": launcher.V31_WORKFLOW_BUDGET_SECONDS},
        "workflow_clock_start": {"monotonic": 1.0, "boottime": 1.0, "utc_ns": 1},
        "service_cgroup_path": Path("/sys/fs/cgroup/app.slice/myfenics-case-test.service"),
        "time_policy": "observe_only",
        "run_id": launcher.V31_AUTHORIZED_COMPLETION_RUN_ID,
        "comparison_group": launcher.V31_AUTHORIZED_COMPLETION_COMPARISON_GROUP,
        "input_sha256": input_sha,
    }
    lease = launcher._reserve_v31_projection_layout_budget(tmp_path, run_directory, **kwargs)
    saved = json.loads(ledger_path.read_text(encoding="utf-8"))
    attempts = saved["stages"]["Q4_ORIGINAL"]["attempts"]
    assert attempts[0] == old_attempt
    assert saved["elapsed_seconds"] == measured
    assert saved["total_budget_seconds"] == launcher.V31_WORKFLOW_BUDGET_SECONDS
    assert saved["unique_bug_replay_count"] == 0
    assert attempts[1]["replay"] is False
    assert attempts[1]["reserved_seconds"] == launcher.V31_WORKFLOW_BUDGET_SECONDS
    assert attempts[1]["authorized_performance_repeat"]["classification"] == (
        "USER_AUTHORIZED_COMPLETION_RERUN"
    )
    assert lease["elapsed_before_seconds"] == measured
    assert lease["effective_budget_after_reservation"]["measured_elapsed_seconds"] == measured
    with pytest.raises(InputError, match="original ledger identity changed"):
        launcher._reserve_v31_projection_layout_budget(tmp_path, run_directory, **kwargs)
