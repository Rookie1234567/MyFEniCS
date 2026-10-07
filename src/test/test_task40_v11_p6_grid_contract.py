from __future__ import annotations

import json
import hashlib
from pathlib import Path
import sys
import textwrap
from types import SimpleNamespace

import pytest

from benchmarks import subreaper_watchdog
from src.io import load_and_resolve
from src.runners import task038_launcher


ROOT = Path(__file__).resolve().parents[2]
INPUT_ROOT = ROOT / "input/task40extra_0p7nm_engineering"
GX560_INPUT = INPUT_ROOT / "nonseparable_gx560_p6_y_orbit_v11.dat"
GX784_INPUT = INPUT_ROOT / "nonseparable_gx784_p6_y_orbit_v11.dat"
GX560_PHYSICAL_INPUT = INPUT_ROOT / "nonseparable_gx560_p6_q4_manual_m2_v3.dat"
GX784_PHYSICAL_INPUT = INPUT_ROOT / "nonseparable_gx784_p6_q4_review_v5.dat"
B0_P6_INPUT = INPUT_ROOT / "b0_p6_y_orbit_reference_v10.dat"
GX560_V14_LEGACY_INPUT = INPUT_ROOT / "nonseparable_gx560_p6_reference_v14_legacy.dat"
V11_ARTIFACTS = (
    ROOT / "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w11_wsl"
)
V11_WINDOW = V11_ARTIFACTS / "campaign_window_v11.json"
V11_ANCHOR = V11_ARTIFACTS / "campaign_start_anchor.json"


@pytest.mark.parametrize(
    ("input_path", "physical_input", "profile_name", "expected"),
    (
        (
            GX560_INPUT,
            GX560_PHYSICAL_INPUT,
            "task40extra_v11_p6_y_orbit_gx560_reference_v1",
            (560, 380040, 365760, 252000, 113760, 280, 195132, 182880, 126000, 56880),
        ),
        (
            GX784_INPUT,
            GX784_PHYSICAL_INPUT,
            "task40extra_v11_p6_y_orbit_gx784_reference_v1",
            (784, 530400, 512064, 352800, 159264, 392, 272340, 256032, 176400, 79632),
        ),
    ),
)
def test_v11_grid_inputs_bind_full_p6_profiles_without_changing_physical_case(
    input_path, physical_input, profile_name, expected
):
    selected = load_and_resolve(input_path).as_jsonable()
    physical = load_and_resolve(physical_input).as_jsonable()
    profile = selected["derived"]["physical_intermediate_profile"]
    periodic = __import__(
        "src.solvers.task40_v10_p6_periodic_profile",
        fromlist=["TASK40_P6_PERIODIC_PROFILES"],
    ).TASK40_P6_PERIODIC_PROFILES[profile_name]

    assert profile["identity"] == profile_name
    assert profile["resources"]["stage_budgets"]["Q4_ORIGINAL"][
        "workflow_seconds"
    ] == 86400
    assert selected["solver"]["stage"] == "Q4_ORIGINAL"
    assert selected["solver"]["preconditioner"] == profile_name
    for section in ("geometry", "materials", "incidence", "boundary"):
        assert selected[section] == physical[section]
    assert selected["discretization"]["mesh_axis_y_values"] == physical[
        "discretization"
    ]["mesh_axis_y_values"]
    assert selected["discretization"]["nedelec_degree"] == 6
    assert selected["boundary"]["dtn_manual_order_max_m"] == 8
    assert selected["boundary"]["dtn_manual_order_max_n"] == 2
    assert (
        periodic.global_cell_count,
        periodic.global_storage_rows,
        periodic.global_independent_rows,
        periodic.global_interior_rows,
        periodic.global_trace_rows,
        periodic.local_cell_count,
        periodic.local_storage_rows,
        periodic.local_independent_rows,
        periodic.local_interior_rows,
        periodic.local_trace_rows,
    ) == expected
    assert periodic.q_port_counts == (68, 68, 136, 68)
    assert periodic.mode_count == 340
    runtime_inventory = {
        "degree": periodic.degree,
        "global_cell_count": periodic.global_cell_count,
        "global_storage_rows": periodic.global_storage_rows,
        "global_independent_rows": periodic.global_independent_rows,
        "global_interior_rows": periodic.global_interior_rows,
        "global_trace_rows": periodic.global_trace_rows,
        "q_count": periodic.q_count,
        "rows_per_q": periodic.rows_per_q,
        "trace_rows_per_q": periodic.trace_rows_per_q,
        "local_cell_count": periodic.local_cell_count,
        "local_storage_rows": periodic.local_storage_rows,
        "local_independent_rows": periodic.local_independent_rows,
        "local_interior_rows": periodic.local_interior_rows,
        "local_trace_rows": periodic.local_trace_rows,
        "local_width_per_q": periodic.local_width_per_q,
        **{
            f"q_port_count_{q}": count
            for q, count in enumerate(periodic.q_port_counts)
        },
    }
    assert periodic.validate_runtime_inventory(runtime_inventory)["status"] == (
        "RUNTIME_INVENTORY_MATCH"
    )
    assert selected["execution"]["timeout_seconds"] == 86400
    assert selected["execution"]["memory_limit_gb"] == 16.0
    assert selected["execution"]["warning_memory_gib"] == 14.0
    assert selected["execution"]["terminate_memory_gib"] == 16.0


def test_v10_memory_warning_contract_is_unchanged():
    old = load_and_resolve(B0_P6_INPUT).as_jsonable()
    assert old["execution"]["warning_memory_gib"] == 12.0
    assert old["execution"]["terminate_memory_gib"] == 16.0


def test_v14_legacy_assembly_passes_the_shared_worker_candidate_contract():
    from src.io.physical_intermediate_profile import profile_facts
    from src.runners import task40_v10_worker
    from src.runners.physical_v14_budget import V14_TIME_POLICY_ENFORCE

    payload = load_and_resolve(GX560_V14_LEGACY_INPUT).as_jsonable()
    profile_identity = payload["solver"]["preconditioner"]
    contract = profile_facts(profile_identity)
    window_sha = "a" * 64
    runtime = SimpleNamespace(
        stage=payload["solver"]["stage"],
        campaign_context={
            "read_only": True,
            "window_path": "fixture-window.json",
            "window_sha256": window_sha,
            "accounting_path": "fixture-accounting.json",
        },
        shared_budget={"campaign_window_sha256": window_sha},
        workflow_reserved_seconds=1000.0,
        require_zero_swap=True,
        _ledger_path=None,
        time_policy=V14_TIME_POLICY_ENFORCE,
    )

    authority = task40_v10_worker._candidate_contract(
        payload, contract, runtime, profile_identity=profile_identity
    )

    assert authority["checks"]["q_assembly_strategy"] is True
    assert all(authority["checks"].values())


def test_v14_legacy_assembly_reaches_the_task40_dispatcher(monkeypatch, tmp_path: Path):
    from src.runners import task038_full3d_iterative, task40_v10_worker

    payload = load_and_resolve(GX560_V14_LEGACY_INPUT).as_jsonable()
    captured = {}

    def fake_worker(resolved, run_directory, **kwargs):
        captured["run_id"] = resolved["run_id"]
        captured["q_assembly_strategy"] = resolved["solver"][
            "task40_q_assembly_strategy"
        ]
        captured["kwargs"] = kwargs
        return {"status": "dispatch_fixture_pass"}

    monkeypatch.setattr(
        task40_v10_worker, "run_task40_v10_p6_reference_worker", fake_worker
    )
    result = task038_full3d_iterative.run_full3d_iterative(
        payload, tmp_path, source_sha="f" * 40
    )

    assert result == {"status": "dispatch_fixture_pass"}
    assert captured["run_id"] == payload["run_id"]
    assert captured["q_assembly_strategy"] == "LEGACY_GLOBAL_CSR_SUM"
    assert captured["kwargs"]["share_transform_bank"] is True


def test_worker_packet_refuses_duplicate_witness_name_without_changing_old_hashes(
    tmp_path: Path,
):
    from src.runners import task40_v10_worker

    name = "v13_regular_inverse_gx560_initial"
    npz_path = Path(f"{tmp_path / name}.npz")
    json_path = Path(f"{tmp_path / name}.json")
    npz_path.write_bytes(b"old array packet")
    json_path.write_bytes(b"old metadata packet")
    old_hashes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (npz_path, json_path)
    }
    runtime = SimpleNamespace(directory=tmp_path)

    with pytest.raises(FileExistsError, match="refusing overwrite"):
        task40_v10_worker._save_packet(runtime, name, {})

    assert {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (npz_path, json_path)
    } == old_hashes


def test_profile_inventory_uses_trace_axes_and_keeps_all_q_branches():
    from src.runners.task40_v10_worker import _validate_target_p6_inventory
    from src.solvers.task40_v10_p6_periodic_profile import TASK40_P6_PERIODIC_PROFILES
    from src.solvers.task40_v10_p6_yorbit import _local_condensation_row_facts

    for profile_name in (
        "task40extra_v11_p6_y_orbit_gx560_reference_v1",
        "task40extra_v11_p6_y_orbit_gx784_reference_v1",
    ):
        profile = TASK40_P6_PERIODIC_PROFILES[profile_name]
        actual = SimpleNamespace(
            full_rows=profile.global_storage_rows,
            active_rows=profile.global_trace_rows,
            active_interior_rows=profile.global_interior_rows,
            appended_rows=profile.mode_count,
        )
        facts = _validate_target_p6_inventory(actual, profile)
        assert facts["trace_rows"] == profile.global_trace_rows
        assert facts["port_rows"] == 340
        with pytest.raises(ValueError, match=r"trace\+port retained inventory"):
            _validate_target_p6_inventory(
                SimpleNamespace(
                    full_rows=profile.global_storage_rows,
                    active_rows=profile.global_independent_rows,
                    active_interior_rows=profile.global_interior_rows,
                    appended_rows=profile.mode_count,
                ),
                profile,
            )

    local_facts = _local_condensation_row_facts(
        SimpleNamespace(active_rows=8496, active_interior_rows=18000)
    )
    assert local_facts == {"local_trace_rows": 8496, "local_interior_rows": 18000}


def test_v11_dispatch_binds_both_grid_profiles_to_shared_worker(monkeypatch, tmp_path):
    from src.runners import task038_full3d_iterative as dispatcher
    from src.runners import task40_v10_worker

    calls = []

    def no_fe_worker(payload, run_directory, *, source_sha, profile_identity=None,
                     share_transform_bank=False):
        calls.append((payload, Path(run_directory), source_sha, profile_identity,
                      share_transform_bank))
        return {"route": "no_fe_shared_worker_leaf"}

    monkeypatch.setattr(task40_v10_worker, "run_task40_v10_p6_reference_worker", no_fe_worker)
    for index, input_path in enumerate((GX560_INPUT, GX784_INPUT)):
        payload = load_and_resolve(input_path).as_jsonable()
        result = dispatcher.run_full3d_iterative(
            payload, tmp_path / f"dispatch_{index}", source_sha=f"{index + 1:040d}"
        )
        assert result["route"] == "no_fe_shared_worker_leaf"
        assert calls[-1][0]["solver"]["stage"] == "Q4_ORIGINAL"
        assert calls[-1][3] == payload["solver"]["preconditioner"]
        assert calls[-1][4] is True


def test_campaign_deadline_reads_active_v11_evidence_key():
    from src.runners.task038_launcher import _task40_campaign_time_exceeded

    record = {
        "task40_v11_campaign": {
            "launcher_post_watchdog_observation": {"remaining_numerical_seconds": 0.0}
        }
    }
    assert _task40_campaign_time_exceeded(record, "task40_v11_campaign")
    assert not _task40_campaign_time_exceeded(
        {
            "task40_v10_campaign": {
                "launcher_post_watchdog_observation": {
                    "remaining_numerical_seconds": 12.0
                }
            }
        },
        "task40_v10_campaign",
    )


def test_v11_public_run_case_supervisor_dispatch_runtime_campaign_chain_no_fe(
    tmp_path: Path, monkeypatch, capsys
):
    if not all(path.is_file() for path in (GX560_INPUT, V11_WINDOW, V11_ANCHOR)):
        pytest.skip("qualified V11 inputs or fixed campaign artifacts are unavailable")

    source_anchor = json.loads(V11_ANCHOR.read_text(encoding="utf-8"))
    source_window_bytes = V11_WINDOW.read_bytes()
    source_window = json.loads(source_window_bytes)
    assert source_anchor["window_refreshed"] is False
    assert source_anchor["deadline_utc_ns"] == source_window["first_full_three_clock_sample"][
        "utc_ns"
    ] + 86400 * 1_000_000_000
    assert source_anchor["t0_utc_ns"] == source_window[
        "first_full_three_clock_sample"
    ]["utc_ns"]
    assert hashlib.sha256(V11_ANCHOR.read_bytes()).hexdigest() == source_window[
        "v11_anchor_sha256"
    ]
    assert source_window["old_costs_and_unknowns_preserved"] is True
    assert source_window["v10_historical_charge_seconds_preserved"] > 0.0

    fixture_window_path = tmp_path / "campaign_window_v11.json"
    fixture_window_path.write_bytes(source_window_bytes)
    run_directory = tmp_path / "launcher_v11_run"
    worker_script = tmp_path / "v11_no_fe_worker.py"
    worker_script.write_text(
        textwrap.dedent(
            """
            import json
            import sys
            from pathlib import Path

            sys.path.insert(0, str(Path.cwd()))
            from src.io import load_and_resolve
            from src.io.physical_intermediate_profile import profile_facts
            from src.runners import task038_full3d_iterative as dispatcher
            from src.runners import task40_v10_worker as worker
            from src.runners.physical_p4_schur_v14 import _V14Runtime

            input_path = Path(sys.argv[1])
            run_directory = Path(sys.argv[2])
            payload = load_and_resolve(input_path).as_jsonable()
            profile_identity = payload["solver"]["preconditioner"]
            contract = profile_facts(profile_identity)

            def no_fe_worker(resolved, directory, *, source_sha, profile_identity=None,
                             share_transform_bank=False):
                runtime = _V14Runtime(
                    directory,
                    resolved["solver"]["stage"],
                    profile_facts(profile_identity),
                    root=Path.cwd(),
                    source_sha=source_sha,
                    batch_identity="review_v11_gx560_no_fe_route_fixture",
                    evidence_prefix="v11_no_fe_fixture",
                    require_zero_swap=True,
                )
                authority = worker._candidate_contract(
                    resolved, profile_facts(profile_identity), runtime,
                    profile_identity=profile_identity,
                )
                before = runtime.sample("fixture_preflight")
                runtime.set_phase("cleanup")
                after = runtime.sample("fixture_cleanup")
                record = {
                    "scope": "no_finite_element_or_numeric_factorization",
                    "route": "dispatcher_to_shared_p6_worker_seam",
                    "profile_identity": profile_identity,
                    "share_transform_bank": share_transform_bank,
                    "run_id": resolved["run_id"],
                    "authority": authority,
                    "campaign_context": runtime.campaign_context,
                    "shared_budget": runtime.shared_budget,
                    "samples_readable": before["all_status_readable"] and after["all_status_readable"],
                }
                (directory / "fixture_summary.json").write_text(
                    json.dumps(record, sort_keys=True), encoding="utf-8"
                )
                return {"route": record["route"], "fixture_summary": str(directory / "fixture_summary.json")}

            worker.run_task40_v10_p6_reference_worker = no_fe_worker
            result = dispatcher.run_full3d_iterative(
                payload, run_directory, source_sha="f" * 40
            )
            (run_directory / "dispatch_summary.json").write_text(
                json.dumps(result, sort_keys=True), encoding="utf-8"
            )
            """
        ),
        encoding="utf-8",
    )

    service_cgroup = Path(
        "/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice/"
        "myfenics-case-v11-no-fe-fixture.service"
    )
    launcher_cgroup_paths = []

    def fixture_source_gate(_cwd, expected_sha):
        return {
            "source_sha": expected_sha,
            "tracked_and_nonignored_untracked_clean": False,
            "test_substitute": "dirty no-FE fixture source gate; not formal provenance",
        }

    def fixture_output_directory(_specification, _timestamp):
        run_directory.mkdir()
        return run_directory

    def fixture_plan(specification, plan_directory, **_kwargs):
        return SimpleNamespace(
            argv=(
                str(Path(sys.executable).resolve()),
                str(worker_script),
                str(specification.source_path),
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
        [str(GX560_INPUT), "--task40-v10-campaign-window", str(fixture_window_path)]
    )
    captured = capsys.readouterr()
    assert exit_code == 0, captured.err or captured.out
    result = json.loads(captured.out.strip().splitlines()[-1])
    assert result["result_classification"] == "worker_exit0"
    assert launcher_cgroup_paths == [service_cgroup]
    assert result["full_workflow_time_exceeded"] is False
    assert result["task40_v11_campaign"]["window_sha256"] == hashlib.sha256(
        source_window_bytes
    ).hexdigest()

    manifest = json.loads((run_directory / "run_manifest.json").read_text(encoding="utf-8"))
    watchdog = json.loads(
        (run_directory / "watchdog" / "summary.json").read_text(encoding="utf-8")
    )
    worker_record = json.loads(
        (run_directory / "fixture_summary.json").read_text(encoding="utf-8")
    )
    assert manifest["task40_v11_campaign"]["window_sha256"] == hashlib.sha256(
        source_window_bytes
    ).hexdigest()
    envelope = watchdog["launch_envelope"]
    assert envelope["tree_cap_bytes"] == 16 * 1024**3
    assert envelope["launch_cap_bytes"] == min(
        envelope["dynamic_launch_cap_bytes"], envelope["tree_cap_bytes"]
    )
    assert envelope["cap_policy"] == "min(dynamic_memory_envelope, explicit_tree_cap)"
    # The watchdog keeps its historical field name while binding it to V11's
    # fixed window; launcher and manifest use the V11 evidence key.
    assert watchdog["task40_v10_campaign"]["window_sha256"] == hashlib.sha256(
        source_window_bytes
    ).hexdigest()
    assert worker_record["scope"] == "no_finite_element_or_numeric_factorization"
    assert worker_record["profile_identity"] == "task40extra_v11_p6_y_orbit_gx560_reference_v1"
    assert worker_record["authority"]["effective_wall_clock_authority"] == (
        "existing_V11_fixed_deadline_and_cumulative_remaining"
    )
    assert worker_record["campaign_context"]["read_only"] is True
    assert worker_record["samples_readable"] is True
    assert worker_record["share_transform_bank"] is True
    assert watchdog["job_cgroup_swap"]["passed"] is True
    assert V11_WINDOW.read_bytes() == source_window_bytes
