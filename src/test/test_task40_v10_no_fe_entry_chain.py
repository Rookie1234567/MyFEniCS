import json
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmarks import subreaper_watchdog
from src.runners import task038_launcher
from src.runners.task40_v10_campaign import (
    CAMPAIGN_ACCOUNTING_NAME,
    TASK40_V10_CAMPAIGN_WINDOW,
    load_fixed_campaign_window,
    read_campaign_state,
    time_namespace_identity,
)

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "input/task40extra_0p7nm_engineering/b0_p4_balh_control_v10.dat"
P6_INPUT = ROOT / "input/task40extra_0p7nm_engineering/b0_p6_y_orbit_reference_v10.dat"


def test_run_case_launcher_supervisor_worker_runtime_no_fe_chain(
    tmp_path: Path, monkeypatch, capsys
):
    if not TASK40_V10_CAMPAIGN_WINDOW.is_file():
        pytest.skip("the qualified local Task40 V10 campaign artifact is unavailable")

    source_window = load_fixed_campaign_window(TASK40_V10_CAMPAIGN_WINDOW)
    try:
        remaining_state = read_campaign_state(
            source_window, namespace_identity=time_namespace_identity()
        )
    except (OSError, RuntimeError, ValueError) as exc:
        pytest.skip(f"the historical Task40 V10 campaign state is unavailable: {exc}")
    if remaining_state["remaining_numerical_seconds"] <= 0.0:
        pytest.skip(
            "the immutable historical Task40 V10 campaign has reached its closeout reserve; "
            "the fixture does not reset or refresh that window"
        )
    fixture_window_path = tmp_path / "campaign_window.json"
    fixture_window_path.write_bytes(source_window.path.read_bytes())
    fixture_window = load_fixed_campaign_window(fixture_window_path)
    run_directory = tmp_path / "launcher_run"
    worker_script = tmp_path / "no_fe_worker.py"
    worker_script.write_text(
        textwrap.dedent(
            """
            import json
            import sys
            from pathlib import Path

            sys.path.insert(0, str(Path.cwd()))

            from src.io import load_and_resolve
            from src.io.physical_intermediate_profile import (
                TASK40_V10_P6_REFERENCE_PROFILE,
                profile_facts,
            )
            from src.runners.physical_dual_cell_condensed_lowmem_v20 import (
                _resolve_v20_worker_time_contract,
            )
            from src.runners.physical_p4_schur_v14 import _V14Runtime

            input_path = Path(sys.argv[1])
            run_directory = Path(sys.argv[2])
            resolved = load_and_resolve(input_path).as_jsonable()
            contract = resolved["derived"]["physical_intermediate_profile"]
            runtime = _V14Runtime(
                run_directory,
                "B0_CONTROL",
                contract,
                root=Path.cwd(),
                source_sha="b" * 40,
                batch_identity="review_v10_b0_control_no_fe_fixture",
                evidence_prefix="v10_fixture",
                require_zero_swap=True,
            )
            authority = _resolve_v20_worker_time_contract(
                resolved,
                runtime,
                profile=resolved["solver"]["preconditioner"],
                stage="B0_CONTROL",
            )
            before = runtime.sample("fixture_preflight")
            interval = runtime.workflow_clock_interval()
            runtime.begin_pc(1)
            pc_observation = runtime.finish_pc(completed=False)
            runtime.marker("fixture_time_gate_observed", interval)
            runtime.set_phase("cleanup")
            after = runtime.sample("fixture_post_cleanup")
            finalized = {
                "scope": "no_finite_element_or_PDE_action",
                "ledger_path": None if runtime._ledger_path is None else str(runtime._ledger_path),
                "campaign_context": runtime.campaign_context,
                "pc_limit_reserved_seconds": runtime.workflow_reserved_seconds,
                "time_budget_authority": authority,
                "workflow_interval": interval,
                "pc_observation": pc_observation,
                "preflight_sample": {
                    "all_status_readable": before["all_status_readable"],
                    "swap_bytes": before["swap_bytes"],
                    "pss_sampling_policy": before["pss_sampling_policy"],
                },
                "cleanup_sample": {
                    "all_status_readable": after["all_status_readable"],
                    "swap_bytes": after["swap_bytes"],
                    "pss_sampling_policy": after["pss_sampling_policy"],
                },
            }
            (run_directory / "fixture_summary.json").write_text(
                json.dumps(finalized, sort_keys=True), encoding="utf-8"
            )
            runtime.marker("fixture_finalize_complete", finalized)

            candidate_payload = load_and_resolve(
                Path.cwd() / "input/task40extra_0p7nm_engineering/"
                "b0_p6_y_orbit_reference_v10.dat"
            ).as_jsonable()
            candidate_runtime = _V14Runtime(
                run_directory,
                "B0_CANDIDATE",
                profile_facts(TASK40_V10_P6_REFERENCE_PROFILE),
                root=Path.cwd(),
                source_sha="d" * 40,
                batch_identity="review_v10_b0_candidate_runtime_no_fe_fixture",
                evidence_prefix="v10_candidate_fixture",
                require_zero_swap=True,
            )
            candidate_before = candidate_runtime.sample("candidate_fixture_preflight")
            candidate_runtime.set_phase("cleanup")
            candidate_after = candidate_runtime.sample("candidate_fixture_cleanup")
            candidate_record = {
                "scope": "no_finite_element_or_PDE_action",
                "stage": candidate_runtime.stage,
                "campaign_context": candidate_runtime.campaign_context,
                "shared_budget": candidate_runtime.shared_budget,
                "preflight_all_status_readable": candidate_before["all_status_readable"],
                "cleanup_all_status_readable": candidate_after["all_status_readable"],
                "candidate_payload_stage": candidate_payload["solver"]["stage"],
            }
            (run_directory / "candidate_runtime_summary.json").write_text(
                json.dumps(candidate_record, sort_keys=True), encoding="utf-8"
            )
            """
        ),
        encoding="utf-8",
    )

    service_cgroup = Path(
        "/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice/"
        "myfenics-case-v10-no-fe-fixture.service"
    )
    launcher_cgroup_paths = []

    def fixture_source_gate(_cwd, expected_sha):
        return {
            "source_sha": expected_sha,
            "tracked_and_nonignored_untracked_clean": False,
            "test_substitute": "dirty fixture source gate; not formal provenance",
        }

    def fixture_output_directory(_specification, _timestamp):
        run_directory.mkdir()
        return run_directory

    def fixture_plan(specification, plan_directory, **_kwargs):
        return SimpleNamespace(
            argv=(
                str(Path(sys.executable).resolve()),
                str(worker_script),
                str(INPUT),
                str(plan_directory),
            ),
            adapter_available=True,
            contract_probe=False,
        )

    def fixture_current_cgroup():
        launcher_cgroup_paths.append(service_cgroup)
        return service_cgroup

    def fixture_cgroup_snapshot(_pid):
        return {
            "path": str(service_cgroup),
            "readable": True,
            "dedicated_job_cgroup": True,
            "member_count": 2,
            "memory_current_bytes": 128 * 1024**2,
            "memory_peak_bytes": None,
            "memory_limit_bytes": None,
            "swap_current_bytes": 0,
        }

    monkeypatch.setattr(task038_launcher, "_physical_source_gate", fixture_source_gate)
    monkeypatch.setattr(task038_launcher, "_timestamp_directory", fixture_output_directory)
    monkeypatch.setattr(task038_launcher, "build_execution_plan", fixture_plan)
    monkeypatch.setattr(task038_launcher, "current_cgroup_path", fixture_current_cgroup)
    monkeypatch.setattr(subreaper_watchdog, "cgroup_snapshot", fixture_cgroup_snapshot)

    from scripts import run_case

    exit_code = run_case.main(
        [
            str(INPUT),
            "--task40-v10-campaign-window",
            str(fixture_window_path),
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 0, captured.err or captured.out
    result = json.loads(captured.out.strip().splitlines()[-1])
    assert result["result_classification"] == "worker_exit0"
    assert launcher_cgroup_paths == [service_cgroup]

    manifest = json.loads((run_directory / "run_manifest.json").read_text(encoding="utf-8"))
    watchdog = json.loads(
        (run_directory / "watchdog" / "summary.json").read_text(encoding="utf-8")
    )
    worker_record = json.loads(
        (run_directory / "fixture_summary.json").read_text(encoding="utf-8")
    )
    campaign_record = watchdog["task40_v10_campaign"]
    accounting_path = fixture_window_path.parent / CAMPAIGN_ACCOUNTING_NAME

    assert manifest["task40_v10_campaign"]["window_sha256"] == source_window.sha256
    assert manifest["task40_v10_campaign"]["t0_utc_ns"] == source_window.t0_utc_ns
    assert manifest["task40_v10_campaign"]["deadline_utc_ns"] == source_window.deadline_utc_ns
    assert Path(manifest["task40_v10_campaign"]["accounting_path"]) == accounting_path
    assert manifest["source_after"]["test_substitute"].startswith("dirty fixture source gate")
    assert watchdog["classification"] == "COMPLETED"
    assert watchdog["leader_exit_code"] == 0
    assert watchdog["descendants_cleared"] is True
    assert watchdog["pss_sampling_policy"] == "disabled_by_profile"
    assert watchdog["sampled_process_tree_pss_peak_bytes"] is None
    assert watchdog["process_tree_swap_gate_enforced"] is True
    assert watchdog["job_cgroup_swap_gate_enforced"] is True
    assert watchdog["job_cgroup_swap"]["passed"] is True
    assert watchdog["job_cgroup_swap"]["end"]["path"] == str(service_cgroup)
    assert watchdog["global_swap_gate_enforced"] is False
    assert watchdog["launch_envelope"]["tree_cap_bytes"] == 16 * 1024**3
    assert watchdog["launch_envelope"]["cap_policy"] == (
        "min(dynamic_memory_envelope, explicit_tree_cap)"
    )
    assert campaign_record["window_sha256"] == source_window.sha256
    assert campaign_record["t0_utc_ns"] == source_window.t0_utc_ns
    assert campaign_record["deadline_utc_ns"] == source_window.deadline_utc_ns
    assert Path(campaign_record["accounting_path"]) == accounting_path
    assert campaign_record["watchdog_end_accounting"]["campaign_window_sha256"] == (
        source_window.sha256
    )
    assert worker_record["scope"] == "no_finite_element_or_PDE_action"
    assert worker_record["ledger_path"] is None
    assert worker_record["campaign_context"]["read_only"] is True
    assert worker_record["time_budget_authority"]["campaign_window_sha256"] == (
        source_window.sha256
    )
    assert worker_record["preflight_sample"]["pss_sampling_policy"] == "disabled_by_profile"
    assert worker_record["cleanup_sample"]["pss_sampling_policy"] == "disabled_by_profile"
    assert worker_record["pc_observation"]["pc_limit_source"] == (
        "fixed_v10_campaign_remaining_at_worker_entry"
    )
    assert worker_record["pc_observation"]["soft_limit_seconds"] == worker_record[
        "pc_observation"
    ]["hard_limit_seconds"]
    assert worker_record["pc_observation"]["hard_limit_seconds"] == worker_record[
        "pc_limit_reserved_seconds"
    ]
    candidate_runtime_record = json.loads(
        (run_directory / "candidate_runtime_summary.json").read_text(encoding="utf-8")
    )
    assert candidate_runtime_record["scope"] == "no_finite_element_or_PDE_action"
    assert candidate_runtime_record["stage"] == "B0_CANDIDATE"
    assert candidate_runtime_record["candidate_payload_stage"] == "B0_CANDIDATE"
    assert candidate_runtime_record["campaign_context"]["read_only"] is True

    account_rows = [
        json.loads(line)
        for line in accounting_path.read_text(encoding="utf-8").splitlines()
    ]
    assert account_rows[0]["label"] == "launcher_entered_task40_v10"
    assert account_rows[-1]["label"] == "launcher_after_watchdog"
    assert all(row["campaign_window_sha256"] == source_window.sha256 for row in account_rows)
    assert all(
        row["label"].startswith(("launcher_", "watchdog_"))
        for row in account_rows
    )

    # Exercise the real dispatcher routes while replacing only the numerical
    # leaves.  This verifies identity and route arguments without FE assembly.
    from src.io import load_and_resolve
    from src.runners import task038_full3d_iterative as dispatcher
    from src.runners import physical_dual_cell_condensed_lowmem_v20 as lowmem
    from src.runners import task40_v10_worker as candidate_worker

    p4_payload = load_and_resolve(INPUT).as_jsonable()
    p6_payload = load_and_resolve(P6_INPUT).as_jsonable()
    assert p4_payload["geometry"] == p6_payload["geometry"]
    assert p4_payload["materials"] == p6_payload["materials"]
    assert p4_payload["discretization"]["mesh_axis_y_values"] == p6_payload[
        "discretization"
    ]["mesh_axis_y_values"]
    p4_calls = []

    def p4_leaf(*args, **kwargs):
        p4_calls.append((args, kwargs))
        return {"route": "p4_control", "kwargs": kwargs}

    monkeypatch.setattr(lowmem, "_run_physical_dual_cell_condensed_lowmem", p4_leaf)
    p4_result = dispatcher.run_full3d_iterative(
        p4_payload, tmp_path / "dispatcher_p4", source_sha="c" * 40
    )
    assert p4_result["route"] == "p4_control"
    assert len(p4_calls) == 1
    p4_kwargs = p4_calls[0][1]
    assert p4_kwargs["allowed_stages"] == ("B0_CONTROL",)
    assert p4_kwargs["coarse_degree"] == 4
    assert p4_kwargs["rhs_identity_policy"] == "case_bound_physical_rhs"
    assert p4_kwargs["reuse_qualified_jit"] is True
    assert p4_kwargs["write_ordered_mode_manifest"] is True
    assert p4_kwargs["write_geometry_audit"] is False
    assert p4_kwargs["write_rectangular_air_void_audit"] is True
    assert p4_kwargs["save_complete_field_packet"] is True
    assert p4_kwargs["notch_by_stage"] == {"B0_CONTROL": False}

    candidate_calls = []

    def candidate_leaf(*args, **kwargs):
        candidate_calls.append((args, kwargs))
        return {"route": "p6_candidate"}

    monkeypatch.setattr(
        candidate_worker, "run_task40_v10_p6_reference_worker", candidate_leaf
    )
    p6_result = dispatcher.run_full3d_iterative(
        p6_payload, tmp_path / "dispatcher_p6", source_sha="d" * 40
    )
    assert p6_result["route"] == "p6_candidate"
    assert len(candidate_calls) == 1
    assert candidate_calls[0][0][0]["solver"]["stage"] == "B0_CANDIDATE"
