from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.io import load_and_resolve


ROOT = Path(__file__).resolve().parents[2]
INPUT_ROOT = ROOT / "input/task40extra_0p7nm_engineering"
V20_INPUTS = (
    "nonseparable_e2_p6_reference_v20.dat",
    "target_original_ny8_resource_pilot_v20.dat",
)


@pytest.mark.parametrize("filename", V20_INPUTS)
def test_v20_dat_profile_facts_and_checker_inventory_use_registry(filename):
    from src.io.physical_intermediate_profile import profile_facts
    from src.runners.task40_v10_output_checker import _registered_v15_profile_inventory
    from src.solvers.task40_v10_p6_periodic_profile import TASK40_P6_PERIODIC_PROFILES
    from src.solvers.task40_v20_registry import TASK40_V20_CASES_BY_PROFILE

    payload = load_and_resolve(INPUT_ROOT / filename).as_jsonable()
    profile = payload["solver"]["preconditioner"]
    case = TASK40_V20_CASES_BY_PROFILE[profile]
    facts = profile_facts(profile)
    periodic = TASK40_P6_PERIODIC_PROFILES[profile]
    inventory = _registered_v15_profile_inventory(profile)

    assert payload["run_id"] == case.run_id == facts["run_id"]
    assert facts["stage"] == case.solver_stage
    assert facts["input_path"] == case.input_path
    assert facts["gates"]["task40_mesh_id"] == case.mesh_id
    assert payload["execution"]["task40_execution_stop_stage"] == "preflight"
    assert payload["derived"]["physical_intermediate_profile"] == facts
    assert inventory["identity"] == profile
    assert inventory["q_count"] == periodic.q_count
    assert inventory["q_port_counts"] == tuple(periodic.q_port_counts)


def test_target_component_resume_input_requires_hash_bound_local_port_manifest(tmp_path):
    from scripts.task40_v20_service_workflow import render_stage_input

    canonical = (INPUT_ROOT / "target_original_ny8_resource_pilot_v20.dat").read_text(
        encoding="utf-8"
    )
    manifest_path = (
        "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v20_wsl/"
        "target_component_resume_manifest.json"
    )
    manifest_sha = "f" * 64
    rendered = render_stage_input(
        canonical,
        "local_port_components",
        component_resume_manifest_path=manifest_path,
        component_resume_manifest_sha256=manifest_sha,
    )
    input_path = tmp_path / "target_component_resume.dat"
    input_path.write_text(rendered, encoding="utf-8")
    payload = load_and_resolve(input_path).as_jsonable()
    assert payload["execution"]["task40_execution_stop_stage"] == "local_port_components"
    assert payload["execution"]["task40_component_resume_manifest_path"] == manifest_path
    assert payload["execution"]["task40_component_resume_manifest_sha256"] == manifest_sha

    missing_hash = rendered.replace(
        f'task40_component_resume_manifest_sha256 = "{manifest_sha}"\n', ""
    )
    input_path.write_text(missing_hash, encoding="utf-8")
    with pytest.raises(ValueError, match="must be supplied together"):
        load_and_resolve(input_path)

    with pytest.raises(ValueError, match="restricted"):
        render_stage_input(
            canonical,
            "geometry_inventory",
            component_resume_manifest_path=manifest_path,
            component_resume_manifest_sha256=manifest_sha,
        )


def test_component_resume_input_matches_original_except_manifest_bindings(tmp_path):
    from src.runners.task40_v20_stage_runner import (
        _validate_component_resume_input_identity,
    )

    manifest_path = "benchmarks/artifacts/component_resume.json"
    manifest_sha = "a" * 64
    original = tmp_path / "original.dat"
    continuation = tmp_path / "continuation.dat"
    original.write_text(
        '[execution]\n'
        'task40_execution_stop_stage = "local_port_components"\n'
        '\n[physics]\nfrequency_hz = 1.0\n',
        encoding="utf-8",
    )
    continuation.write_text(
        '[execution]\n'
        'task40_execution_stop_stage = "local_port_components"\n'
        f'task40_component_resume_manifest_path = "{manifest_path}"\n'
        f'task40_component_resume_manifest_sha256 = "{manifest_sha}"\n'
        '\n[physics]\nfrequency_hz = 1.0\n',
        encoding="utf-8",
    )

    _validate_component_resume_input_identity(
        original,
        continuation,
        resume_manifest_path=manifest_path,
        resume_manifest_sha256=manifest_sha,
    )

    continuation.write_text(
        continuation.read_text(encoding="utf-8").replace("frequency_hz = 1.0", "frequency_hz = 2.0"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="differs from the original"):
        _validate_component_resume_input_identity(
            original,
            continuation,
            resume_manifest_path=manifest_path,
            resume_manifest_sha256=manifest_sha,
        )


def test_user_service_prevalidation_accepts_only_exact_target_resume_variant(tmp_path):
    from scripts.task40_v20_service_workflow import (
        ARTIFACT_ROOT,
        _validate_service_stage_input_variant,
        render_stage_input,
    )

    canonical_source = INPUT_ROOT / "target_original_ny8_resource_pilot_v20.dat"
    canonical_text = canonical_source.read_text(encoding="utf-8")
    canonical_path = (
        tmp_path / "input/task40extra_0p7nm_engineering" / canonical_source.name
    )
    canonical_path.parent.mkdir(parents=True)
    canonical_path.write_text(canonical_text, encoding="utf-8")
    stage_root = tmp_path / ARTIFACT_ROOT / "stage_inputs"
    resume_path = (
        stage_root / "local_port_components_resume_full_prefix_v2" / canonical_source.name
    )
    resume_path.parent.mkdir(parents=True)
    manifest_path = (
        "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v20_wsl/"
        "component_resume/target_original_ny8_from_c00_manifest_v1.json"
    )
    manifest_sha256 = "f" * 64
    resume_text = render_stage_input(
        canonical_text,
        "local_port_components",
        component_resume_manifest_path=manifest_path,
        component_resume_manifest_sha256=manifest_sha256,
    )
    resume_path.write_text(resume_text, encoding="utf-8")
    resume_data = load_and_resolve(resume_path).as_jsonable()

    _validate_service_stage_input_variant(
        resume_path.resolve(),
        canonical_path.resolve(),
        canonical_text,
        "local_port_components",
        resume_data,
        repo_root=tmp_path,
    )

    ordinary_path = stage_root / "local_port_components" / canonical_source.name
    ordinary_path.parent.mkdir(parents=True)
    ordinary_text = render_stage_input(canonical_text, "local_port_components")
    ordinary_path.write_text(ordinary_text, encoding="utf-8")
    ordinary_data = load_and_resolve(ordinary_path).as_jsonable()
    _validate_service_stage_input_variant(
        ordinary_path.resolve(),
        canonical_path.resolve(),
        canonical_text,
        "local_port_components",
        ordinary_data,
        repo_root=tmp_path,
    )

    physical_change = resume_text.replace(
        "period_x_nm = 50.0", "period_x_nm = 50.01", 1
    )
    assert physical_change != resume_text
    resume_path.write_text(physical_change, encoding="utf-8")
    with pytest.raises(ValueError, match="same-basename variant"):
        _validate_service_stage_input_variant(
            resume_path.resolve(),
            canonical_path.resolve(),
            canonical_text,
            "local_port_components",
            resume_data,
            repo_root=tmp_path,
        )

    missing_hash = resume_text.replace(
        f'task40_component_resume_manifest_sha256 = "{manifest_sha256}"\n', ""
    )
    resume_path.write_text(missing_hash, encoding="utf-8")
    missing_hash_data = {
        **resume_data,
        "execution": dict(resume_data["execution"]),
    }
    missing_hash_data["execution"].pop(
        "task40_component_resume_manifest_sha256"
    )
    with pytest.raises(ValueError, match="must be supplied together"):
        _validate_service_stage_input_variant(
            resume_path.resolve(),
            canonical_path.resolve(),
            canonical_text,
            "local_port_components",
            missing_hash_data,
            repo_root=tmp_path,
        )

    resume_path.write_text(resume_text, encoding="utf-8")
    wrong_profile_data = {
        **resume_data,
        "solver": dict(resume_data["solver"]),
    }
    wrong_profile_data["solver"]["preconditioner"] = (
        "task40extra_v20_p6_y_orbit_e2_reference_v1"
    )
    with pytest.raises(ValueError, match="restricted to the exact target"):
        _validate_service_stage_input_variant(
            resume_path.resolve(),
            canonical_path.resolve(),
            canonical_text,
            "local_port_components",
            wrong_profile_data,
            repo_root=tmp_path,
        )

    with pytest.raises(ValueError, match="restricted to the exact target"):
        _validate_service_stage_input_variant(
            resume_path.resolve(),
            canonical_path.resolve(),
            canonical_text,
            "geometry_inventory",
            resume_data,
            repo_root=tmp_path,
        )


def test_real_target_resume_path_reaches_minimal_component_fixture(tmp_path, monkeypatch):
    import hashlib
    import os
    import subprocess

    if os.environ.get("TASK40_V20_REAL_RESUME_FIXTURE") != "1":
        pytest.skip("set TASK40_V20_REAL_RESUME_FIXTURE=1 to read the preserved target run")

    from src.runners.task40_v20_stage_runner import (
        _load_target_component_resume,
        _preflight,
        _write_json,
    )
    from src.solvers import task40_v20_local_components as local_components

    resume_input = ROOT / (
        "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v20_wsl/"
        "stage_inputs/local_port_components_resume/"
        "target_original_ny8_resource_pilot_v20.dat"
    )
    resolved = load_and_resolve(resume_input).as_jsonable()
    source_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    preflight, _modes, mode_rows = _preflight(
        resolved,
        source_sha=source_sha,
        profile=resolved["solver"]["preconditioner"],
        mesh_id="TARGET_ORIGINAL_NY8",
    )
    manifest_path = ROOT / resolved["execution"][
        "task40_component_resume_manifest_path"
    ]
    resume_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    campaign = resume_manifest["original_run"]
    _write_json(
        tmp_path / "run_manifest.json",
        {
            "schema": "component_fixture_current_run_envelope_only",
            "run_id": resolved["run_id"],
            "source_sha": source_sha,
            "input_path": str(resume_input.resolve()),
            "input_sha256": hashlib.sha256(resume_input.read_bytes()).hexdigest(),
            "physical_model_sha256": preflight["physical_model_sha256"],
            "task40_v20_campaign": {
                "window_path": campaign["campaign_window_path"],
                "window_sha256": campaign["campaign_window_sha256"],
            },
        },
    )

    geometry, cfg, classes, axes, completed_rows, resume_receipt = (
        _load_target_component_resume(
            resolved,
            tmp_path,
            source_sha=source_sha,
            preflight=preflight,
        )
    )
    assert len(classes) == 60
    assert [len(axis) - 1 for axis in axes] == [272, 8, 14]
    assert completed_rows[0]["class_id"] == "c00"
    assert resume_receipt["original_run"]["source_sha"] != source_sha

    # Keep the fixture narrow: stub the next class kernel and port algebra, while
    # passing the complete ordered mode table through each saved top/bottom face.
    selected_faces = [
        next(
            row
            for row in geometry["periodic_face_inventory"]["boundary_face_cells"]
            if row["side"] == side
        )
        for side in ("top", "bottom")
    ]
    fixture_geometry = dict(geometry)
    fixture_periodic = dict(geometry["periodic_face_inventory"])
    fixture_periodic["boundary_face_cells"] = selected_faces
    fixture_geometry["periodic_face_inventory"] = fixture_periodic
    selected_local_class_ids = []
    port_mode_rows = []

    def measure_selected_class(item, _cfg, *, output_directory, resource_sample):
        selected_local_class_ids.append(item["class_id"])
        resource_sample()
        return (
            {
                "class_id": item["class_id"],
                "passed": True,
                "status": "PASS",
                "local_lu_factor_count": 1,
                "representative_geometry_match": True,
                "representative_cell_permutation_match": True,
                "array_inventory": {
                    "named_array_payload_bytes_with_aliases": 0,
                    "unique_backing_bytes": 0,
                },
            },
            object(),
        )

    class StubFacetPolynomial:
        def __init__(self, _element):
            pass

    class StubBoundaryLayout:
        rows = 4

        def __init__(self, *_args):
            pass

    def check_full_port_rows(**kwargs):
        actual_rows = kwargs["modes"]
        assert actual_rows == list(mode_rows)
        port_mode_rows.append(len(actual_rows))
        return {
            "local_recovery_equation_relative": 0.0,
            "local_original_trace_equation_relative": 0.0,
            "local_reduced_trace_equation_relative": 0.0,
            "local_trace_elimination_identity_relative": 0.0,
            "local_port_equation_relative": 0.0,
            "local_reduced_port_equation_relative": 0.0,
            "local_port_elimination_identity_relative": 0.0,
            "known_interior_solution_relative": 0.0,
            "small_key_native_carrier_witness": {
                "direct_trace_B_relative": 0.0,
                "direct_trace_D_relative": 0.0,
                "full_dof_direct_q30_B_relative": 0.0,
                "full_dof_direct_q30_D_relative": 0.0,
                "full_dof_direct_q30_gate_pass": True,
            },
            "arrays": {"fixture_probe": np.zeros(1, dtype=np.complex128)},
        }

    from src.solvers import directional_boundary, task40_w1_local_probe

    monkeypatch.setattr(local_components, "_local_class_measurement", measure_selected_class)
    monkeypatch.setattr(directional_boundary, "FacetPolynomial", StubFacetPolynomial)
    monkeypatch.setattr(directional_boundary, "BoundaryLayout", StubBoundaryLayout)
    monkeypatch.setattr(task40_w1_local_probe, "stream_boundary_correction", check_full_port_rows)
    report = local_components.run_v20_local_port_components(
        resolved,
        tmp_path,
        axis_coordinates=axes,
        cfg=cfg,
        geometry_facts=fixture_geometry,
        classes=classes[:2],
        mode_rows=mode_rows,
        resource_sample=lambda: {"sample_scope": "minimal resume fixture"},
        completed_local_rows=completed_rows[:1],
        reused_packet_validation=completed_rows[0]["saved_packet_independent_readback"],
    )
    _write_json(tmp_path / "v20_local_port_components.json", report)

    assert report["reused_local_class_ids"] == ["c00"]
    assert [row["class_id"] for row in report["local_cell_classes"]] == ["c00", "c01"]
    assert report["local_cell_classes"][1]["status"] == "PASS"
    assert selected_local_class_ids == ["c01"]
    assert {row["side"] for row in report["boundary_components"]} == {"top", "bottom"}
    assert port_mode_rows == [32060, 32060]
    assert all(row["target_mode_count_full_ordered"] == 32060 for row in report["boundary_components"])
    assert report["global_p6_space_created"] is False
    assert report["global_MPC_created"] is False
    assert report["full_target_field_qualified"] is False


@pytest.mark.parametrize("filename", V20_INPUTS)
def test_v20_worker_contract_accepts_exact_registered_case(filename):
    from src.io.physical_intermediate_profile import profile_facts
    from src.runners import task40_v10_worker
    from src.runners.physical_v14_budget import V14_TIME_POLICY_ENFORCE
    from src.solvers.task40_v20_registry import TASK40_V20_CASES_BY_PROFILE

    payload = load_and_resolve(INPUT_ROOT / filename).as_jsonable()
    profile = payload["solver"]["preconditioner"]
    case = TASK40_V20_CASES_BY_PROFILE[profile]
    window_sha = "a" * 64
    runtime = SimpleNamespace(
        stage=case.solver_stage,
        campaign_context={
            "read_only": True,
            "window_path": "fixed-window.json",
            "window_sha256": window_sha,
            "accounting_path": "accounting.json",
        },
        shared_budget={"campaign_window_sha256": window_sha},
        workflow_reserved_seconds=1000.0,
        require_zero_swap=True,
        _ledger_path=None,
        time_policy=V14_TIME_POLICY_ENFORCE,
    )
    contract = task40_v10_worker._candidate_contract(
        payload,
        profile_facts(profile),
        runtime,
        profile_identity=profile,
    )
    assert contract["checks"] and all(contract["checks"].values())
    assert contract["schema"] == "task40extra.review_v20_one_q_p6_reference_worker_contract.v1"

    payload["run_id"] = "unreviewed_v20_run"
    with pytest.raises(ValueError, match="worker contract failed"):
        task40_v10_worker._candidate_contract(
            payload,
            profile_facts(profile),
            runtime,
            profile_identity=profile,
        )


def test_v17_profile_cannot_inherit_v20_one_q_scope():
    from src.io.physical_intermediate_profile import (
        TASK40_V17_P6_B0_PROFILE,
        profile_facts,
    )
    from src.runners import task40_v10_worker
    from src.runners.physical_v14_budget import V14_TIME_POLICY_ENFORCE

    payload = load_and_resolve(INPUT_ROOT / "b0_p6_reference_v17.dat").as_jsonable()
    payload["solver"]["task40_factor_lifecycle_strategy"] = "ONE_Q_REFACTOR_V19"
    facts = profile_facts(TASK40_V17_P6_B0_PROFILE)
    window_sha = "b" * 64
    runtime = SimpleNamespace(
        stage=payload["solver"]["stage"],
        campaign_context={
            "read_only": True,
            "window_path": "fixed-window.json",
            "window_sha256": window_sha,
            "accounting_path": "accounting.json",
        },
        shared_budget={"campaign_window_sha256": window_sha},
        workflow_reserved_seconds=1000.0,
        require_zero_swap=True,
        _ledger_path=None,
        time_policy=V14_TIME_POLICY_ENFORCE,
    )
    with pytest.raises(ValueError, match="does not support"):
        task40_v10_worker._candidate_contract(
            payload,
            facts,
            runtime,
            profile_identity=TASK40_V17_P6_B0_PROFILE,
        )


@pytest.mark.parametrize("filename", V20_INPUTS)
def test_v20_dispatcher_calls_only_the_staged_adapter(filename, monkeypatch, tmp_path):
    from src.runners import task038_full3d_iterative, task40_v20_stage_runner
    from src.solvers.task40_v20_registry import TASK40_V20_CASES_BY_PROFILE

    payload = load_and_resolve(INPUT_ROOT / filename).as_jsonable()
    profile = payload["solver"]["preconditioner"]
    case = TASK40_V20_CASES_BY_PROFILE[profile]
    captured = {}

    def fake_stage(resolved, run_directory, *, source_sha):
        captured.update(
            run_id=resolved["run_id"],
            profile=resolved["solver"]["preconditioner"],
            stage=resolved["execution"]["task40_execution_stop_stage"],
            run_directory=run_directory,
            source_sha=source_sha,
        )
        return {"status": "staged_fixture"}

    monkeypatch.setattr(task40_v20_stage_runner, "run_task40_v20_stage", fake_stage)
    result = task038_full3d_iterative.run_full3d_iterative(
        payload, tmp_path, source_sha="f" * 40
    )
    assert result == {"status": "staged_fixture"}
    assert captured == {
        "run_id": case.run_id,
        "profile": case.profile,
        "stage": "preflight",
        "run_directory": tmp_path,
        "source_sha": "f" * 40,
    }


@pytest.mark.parametrize("stop_stage", ["full", "build_and_symbolic", "one_q_numeric"])
def test_original_target_unapproved_heavy_stages_stop_before_geometry(
    stop_stage, monkeypatch, tmp_path
):
    from src.runners import task40_v20_stage_runner
    from src.solvers.task40_v20_registry import TASK40_V20_CASES_BY_PROFILE

    payload = load_and_resolve(
        INPUT_ROOT / "target_original_ny8_resource_pilot_v20.dat"
    ).as_jsonable()
    profile = payload["solver"]["preconditioner"]
    case = TASK40_V20_CASES_BY_PROFILE[profile]
    payload["execution"]["task40_execution_stop_stage"] = stop_stage
    preflight = {
        "run_id": case.run_id,
        "case_profile": profile,
        "source_sha": "f" * 40,
        "input_sha256": "a" * 64,
        "physical_model_sha256": "b" * 64,
        "resources": {"scope": "fixture"},
    }
    monkeypatch.setattr(
        task40_v20_stage_runner,
        "_preflight",
        lambda *_args, **_kwargs: (preflight, None, None),
    )
    monkeypatch.setattr(
        "src.geometry.task40_v20_geometry.build_v20_geometry_inventory",
        lambda *_args, **_kwargs: pytest.fail("full-field stop must precede geometry work"),
    )

    result = task40_v20_stage_runner.run_task40_v20_stage(
        payload, tmp_path, source_sha="f" * 40
    )

    assert result["status"] == "controlled_stop"
    assert result["summary"]["official_result"] is False
    assert result["summary"]["completed_stages"] == ["preflight"]
    assert result["summary"]["full_field_release_allowed"] is False
    if stop_stage in {"build_and_symbolic", "one_q_numeric"}:
        assert result["summary"]["target_heavy_authorized"] is False


def test_v20_resource_snapshot_labels_current_process_cgroup(monkeypatch):
    from benchmarks import task034_wsl_resources
    from src.runners import task40_v20_stage_runner

    monkeypatch.setattr(
        task034_wsl_resources,
        "cgroup_snapshot",
        lambda _pid: {
            "path": "/init.scope",
            "readable": True,
            "dedicated_job_cgroup": False,
            "memory_current_bytes": 1234,
            "memory_peak_bytes": 5678,
            "memory_limit_bytes": None,
            "swap_current_bytes": 0,
        },
    )
    snapshot = task40_v20_stage_runner._resource_snapshot()
    cgroup = snapshot["current_process_cgroup"]
    assert cgroup["path"] == "/init.scope"
    assert cgroup["dedicated_job_cgroup"] is False
    assert cgroup["memory_current_bytes"] == 1234
    assert "task-specific only when dedicated_job_cgroup is true" in cgroup["sample_scope"]
    assert "not a simultaneous process-tree peak" in snapshot["scope"]



def _copy_current_campaign_snapshot(tmp_path):
    import hashlib
    import json

    from src.runners.task40_v10_campaign import CAMPAIGN_ACCOUNTING_NAME

    source = ROOT / (
        "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w19_wsl/"
        "campaign_window_v19.json"
    )
    accounting = source.parent / CAMPAIGN_ACCOUNTING_NAME
    if not source.is_file() or not accounting.is_file():
        pytest.skip("the active fixed Task40 campaign artifacts are unavailable")
    payload = source.read_bytes()
    window_sha256 = hashlib.sha256(payload).hexdigest()
    window_copy = tmp_path / "campaign_window_fixture.json"
    window_copy.write_bytes(payload)

    with accounting.open("rb") as stream:
        stream.seek(0, 2)
        end = stream.tell()
        block_size = 65536
        while True:
            start = max(0, end - block_size)
            stream.seek(start)
            tail = stream.read()
            lines = [line for line in tail.splitlines() if line]
            if start == 0 or len(lines) >= 2:
                break
            block_size *= 2
    record_line = lines[-1]
    record = json.loads(record_line)
    assert record["campaign_window_sha256"] == window_sha256
    (tmp_path / CAMPAIGN_ACCOUNTING_NAME).write_bytes(record_line + b"\n")
    return window_copy, window_sha256


@pytest.mark.parametrize("filename", V20_INPUTS)
def test_v20_run_case_reaches_real_launcher_before_worker(
    filename, monkeypatch, tmp_path
):
    """Run the public route and real launcher, then stop at the no-FE worker boundary."""

    from scripts import run_case
    from src.runners import task038_launcher
    from src.solvers.task40_v20_registry import TASK40_V20_CASES_BY_PROFILE

    campaign_window, campaign_sha256 = _copy_current_campaign_snapshot(tmp_path)
    real_launcher = task038_launcher.launch_specification
    reached = {}

    class WorkerBoundaryReached(RuntimeError):
        pass

    def contract_probe_launcher(specification, **kwargs):
        return real_launcher(specification, contract_probe=True, **kwargs)

    def stop_before_worker(plan, specification, run_directory, **_kwargs):
        manifest = json.loads((run_directory / "run_manifest.json").read_text())
        reached.update(
            run_id=specification.identity["run_id"],
            profile=specification.solver["preconditioner"],
            stop_stage=specification.execution["task40_execution_stop_stage"],
            contract_probe=plan.contract_probe,
            campaign=manifest.get("task40_v20_campaign"),
            budget=manifest.get("task40_v20_budget_admission"),
        )
        raise WorkerBoundaryReached

    def temporary_run_directory(specification, _timestamp=None):
        path = tmp_path / specification.identity["run_id"]
        path.mkdir()
        return path

    monkeypatch.setattr(task038_launcher, "launch_specification", contract_probe_launcher)
    monkeypatch.setattr(task038_launcher, "_run_worker", stop_before_worker)
    monkeypatch.setattr(task038_launcher, "_timestamp_directory", temporary_run_directory)

    with pytest.raises(WorkerBoundaryReached):
        run_case.main([
            str(INPUT_ROOT / filename),
            "--task40-v10-campaign-window",
            str(campaign_window),
        ])

    case = next(
        case
        for case in TASK40_V20_CASES_BY_PROFILE.values()
        if case.run_id == reached["run_id"]
    )
    assert reached["profile"] == case.profile
    assert reached["stop_stage"] == "preflight"
    assert reached["contract_probe"] is True
    assert reached["campaign"]["window_sha256"] == campaign_sha256
    assert reached["campaign"]["effective_window_scope"] == (
        "shared_V20_fixed_deadline_and_remaining_budget"
    )
    assert reached["budget"]["model_id"] == case.model_id
    assert reached["budget"]["run_id"] == case.run_id
    assert reached["budget"]["profile"] == case.profile
    assert reached["budget"]["solver_stage"] == case.solver_stage
    assert reached["budget"]["execution_stop_stage"] == "preflight"
    assert reached["budget"]["campaign_window_sha256"] == campaign_sha256
    assert reached["budget"]["configured_stage_budget"]["workflow_seconds"] > 0
    assert reached["budget"]["configured_stage_budget"]["solve_seconds"] > 0


@pytest.mark.parametrize(
    ("filename", "stop_stage"),
    [
        ("target_original_ny8_resource_pilot_v20.dat", "local_port_components"),
        ("nonseparable_e2_p6_reference_v20.dat", "full"),
    ],
)
def test_v20_staged_input_selects_requested_stage_through_real_launcher_without_worker(
    filename, stop_stage, monkeypatch, tmp_path
):
    """Exercise the public route and launcher while stopping before any FE worker."""

    from scripts import run_case
    from scripts.task40_v20_service_workflow import render_stage_input
    from src.runners import task038_launcher

    canonical = INPUT_ROOT / filename
    stage_input = tmp_path / "stage_inputs" / stop_stage / canonical.name
    stage_input.parent.mkdir(parents=True)
    stage_input.write_text(
        render_stage_input(canonical.read_text(encoding="utf-8"), stop_stage),
        encoding="utf-8",
    )
    assert stage_input.name == canonical.name
    campaign_window, campaign_sha256 = _copy_current_campaign_snapshot(tmp_path)
    real_launcher = task038_launcher.launch_specification
    reached = {}

    class WorkerBoundaryReached(RuntimeError):
        pass

    def contract_probe_launcher(specification, **kwargs):
        return real_launcher(specification, contract_probe=True, **kwargs)

    def stop_before_worker(plan, specification, run_directory, **_kwargs):
        manifest = json.loads((run_directory / "run_manifest.json").read_text())
        reached.update(
            run_id=specification.identity["run_id"],
            profile=specification.solver["preconditioner"],
            stop_stage=specification.execution["task40_execution_stop_stage"],
            contract_probe=plan.contract_probe,
            campaign=manifest.get("task40_v20_campaign"),
            budget=manifest.get("task40_v20_budget_admission"),
        )
        raise WorkerBoundaryReached

    def temporary_run_directory(specification, _timestamp=None):
        path = tmp_path / "runs" / specification.identity["run_id"]
        path.mkdir(parents=True)
        return path

    monkeypatch.setattr(task038_launcher, "launch_specification", contract_probe_launcher)
    monkeypatch.setattr(task038_launcher, "_run_worker", stop_before_worker)
    monkeypatch.setattr(task038_launcher, "_timestamp_directory", temporary_run_directory)

    with pytest.raises(WorkerBoundaryReached):
        run_case.main(
            [
                str(stage_input),
                "--task40-v10-campaign-window",
                str(campaign_window),
            ]
        )

    assert reached["stop_stage"] == stop_stage
    assert reached["contract_probe"] is True
    assert reached["campaign"]["window_sha256"] == campaign_sha256
    assert reached["budget"]["execution_stop_stage"] == stop_stage
    assert reached["budget"]["campaign_window_sha256"] == campaign_sha256


def test_user_service_wrapper_routes_v20_to_clocked_workflow_without_starting_service(
    tmp_path,
):
    import os
    import subprocess

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    capture = tmp_path / "systemd_run_argv.bin"
    fake_systemd_run = fake_bin / "systemd-run"
    fake_systemd_run.write_text(
        "#!/usr/bin/env bash\nprintf '%s\\0' \"$@\" > \"$CAPTURE_SYSTEMD_ARGV\"\n",
        encoding="utf-8",
    )
    fake_systemd_run.chmod(0o755)
    environment = dict(os.environ)
    environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
    environment["CAPTURE_SYSTEMD_ARGV"] = str(capture)
    result = subprocess.run(
        [
            "bash",
            str(ROOT / "scripts/run_case_in_user_service.sh"),
            str(INPUT_ROOT / "target_original_ny8_resource_pilot_v20.dat"),
            "--task40-v10-campaign-window",
            str(ROOT / "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w19_wsl/campaign_window_v19.json"),
        ],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    argv = capture.read_bytes().decode().split("\0")
    argv_text = " ".join(argv)
    assert "MemoryMax=16G" in argv_text
    assert "MemorySwapMax=0" in argv_text
    assert "runtime_prefix/bin/python -S scripts/task40_v20_service_workflow.py run-service" in argv_text
    assert "--runtime-prefix" in argv_text
    assert "--abi-receipt" in argv_text
    assert "--jit-cache" in argv_text
    assert "target_original_ny8_resource_pilot_v20.dat" in argv_text


def test_v20_service_accepts_only_the_official_checker_pass_marker():
    from scripts.task40_v20_service_workflow import _official_checker_passed

    assert _official_checker_passed(0, {"status": "PASS"}) is True
    assert _official_checker_passed(0, {"passed": True}) is False
    assert _official_checker_passed(0, {"status": "REJECTED"}) is False
    assert _official_checker_passed(1, {"status": "PASS"}) is False


def test_v20_service_validates_actual_target_manifest_campaign_identity():
    import copy

    from scripts.task40_v20_service_workflow import (
        CAMPAIGN_RELATIVE,
        CAMPAIGN_SHA256,
        _campaign_accounting_path_from_manifest,
    )

    manifest_path = ROOT / (
        "results/task40extra_nonseparable_0p7nm/"
        "task40extra_0p7nm_target_original_ny8_resource_pilot_v20__"
        "full3d_iterative__mpi1__Mna/20261009T153003.130200Z/run_manifest.json"
    )
    if not manifest_path.is_file():
        pytest.skip("the saved V20 target preflight manifest is unavailable")
    actual_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    case_data = load_and_resolve(INPUT_ROOT / V20_INPUTS[1]).as_jsonable()
    expected_accounting = ROOT / CAMPAIGN_RELATIVE.parent / "campaign_accounting_v10.jsonl"
    expected = {
        "expected_window_sha256": CAMPAIGN_SHA256,
        "expected_accounting_path": expected_accounting,
        "expected_run_id": case_data["run_id"],
        "expected_profile": case_data["solver"]["preconditioner"],
    }

    assert actual_manifest["source_sha"] == "776b0d9c990faca42d5669dcb170f35ad2f35849"
    assert _campaign_accounting_path_from_manifest(actual_manifest, **expected) == (
        expected_accounting.resolve()
    )

    missing_identity = copy.deepcopy(actual_manifest)
    missing_identity.pop("task40_v20_campaign")
    wrong_window = copy.deepcopy(actual_manifest)
    wrong_window["task40_v20_campaign"]["window_sha256"] = "0" * 64
    wrong_accounting = copy.deepcopy(actual_manifest)
    wrong_accounting["task40_v20_campaign"]["accounting_path"] = str(
        expected_accounting.with_name("other_campaign_accounting.jsonl")
    )
    wrong_case = copy.deepcopy(actual_manifest)
    wrong_case["run_id"] += "_near_miss"
    wrong_profile = copy.deepcopy(actual_manifest)
    wrong_profile["solver"]["preconditioner"] += "_near_miss"

    for invalid_manifest in (
        missing_identity,
        wrong_window,
        wrong_accounting,
        wrong_case,
        wrong_profile,
    ):
        with pytest.raises(ValueError):
            _campaign_accounting_path_from_manifest(invalid_manifest, **expected)


def test_v20_service_rejects_legacy_campaign_field_for_v20_run(tmp_path):
    from scripts.task40_v20_service_workflow import (
        CAMPAIGN_SHA256,
        _campaign_accounting_path_from_manifest,
    )

    with pytest.raises(ValueError, match="Task40 V20 campaign accounting identity"):
        _campaign_accounting_path_from_manifest(
            {"task40_v10_campaign": {"accounting_path": "ignored"}},
            expected_window_sha256=CAMPAIGN_SHA256,
            expected_accounting_path=tmp_path / "campaign_accounting_v10.jsonl",
            expected_run_id="target_v20",
            expected_profile="target_profile_v20",
        )


def test_v20_service_finds_footer_in_actual_saved_root_and_rejects_absence(tmp_path):
    import json

    from scripts.task40_v20_service_workflow import (
        _check_partial_result,
        _checker_numerical_output_directory,
    )

    run_directory = ROOT / (
        "results/task40extra_nonseparable_0p7nm/"
        "task40extra_0p7nm_target_original_ny8_resource_pilot_v20__"
        "full3d_iterative__mpi1__Mna/20261009T153003.130200Z"
    )
    if not run_directory.is_dir():
        pytest.skip("the saved V20 target preflight run directory is unavailable")
    summary_path = run_directory / "run_summary.json"
    manifest_path = run_directory / "run_manifest.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    declared_output = Path(summary["numerical_output_directory"])
    input_path = INPUT_ROOT / V20_INPUTS[1]

    assert (run_directory / "v20_partial_result.json").is_file()
    assert not declared_output.is_dir()
    assert _checker_numerical_output_directory(run_directory, declared_output) == run_directory
    missing_footer = _check_partial_result(
        input_path=input_path,
        summary_path=summary_path,
        manifest_path=manifest_path,
        numerical_output=tmp_path / "missing-footer",
        expected_stop_stage="preflight",
    )
    assert missing_footer["status"] == "NO_PARTIAL_FOOTER"
    assert missing_footer["checker_passed"] is False
    assert missing_footer["official_result"] is False


def test_v20_service_reads_the_actual_run_case_launcher_result_object():
    import json

    from scripts.task40_v20_service_workflow import _parse_run_case_result

    launcher_result = {
        "run_directory": "/tmp/run",
        "manifest": "/tmp/run/run_manifest.json",
        "summary": "/tmp/run/run_summary.json",
        "result_classification": "worker_exit0",
        "exit_status": 0,
        "resource_authority": {"classification": "COMPLETED"},
    }
    stdout = "launcher notice\n" + json.dumps(
        launcher_result, sort_keys=True, separators=(",", ":")
    ) + "\n"
    assert _parse_run_case_result(stdout) == launcher_result


def test_v20_required_checker_runtime_reuses_campaign_subreaper_limits(
    monkeypatch, tmp_path
):
    import json
    import os
    import sys

    from benchmarks import subreaper_watchdog
    from scripts.task40_v20_service_workflow import (
        _run_required_checker_supervision,
        _unified_cgroup_membership,
    )

    observed = {}
    output = {"status": "PASS"}

    def fake_supervise(command, directory, **kwargs):
        observed.update(command=command, directory=directory, kwargs=kwargs)
        directory.mkdir(parents=True)
        (directory / "worker.log").write_text(json.dumps(output), encoding="utf-8")
        return {
            "classification": "COMPLETED",
            "leader_exit_code": 0,
            "descendants_cleared": True,
        }

    monkeypatch.setattr(subreaper_watchdog, "supervise", fake_supervise)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    request = {
        "command": ["python", "-m", "checker"],
        "checker_kind": "task40_v10_independent_output_checker",
        "evidence_directory": str(evidence),
        "runtime_prefix": str(Path(sys.prefix)),
        "activation_marker": "1",
        "numeric_environment": {},
        "service_parent_pid": os.getpid(),
        "service_cgroup_membership": _unified_cgroup_membership(),
        "repo_root": str(ROOT),
        "campaign_window": str(ROOT / "fixed-window.json"),
        "campaign_sha256": "a" * 64,
        "campaign_accounting": str(ROOT / "campaign-accounting.jsonl"),
        "source_state": {
            "branch": "task40extra_0p7nm_engineering",
            "clean": True,
        },
        "profile": "task40extra_v20_p6_y_orbit_target_original_ny8_v1",
    }

    result = _run_required_checker_supervision(request)

    assert result["return_code"] == 0
    assert result["payload"] == output
    assert observed["kwargs"]["wall_seconds"] == 86400.0
    assert observed["kwargs"]["campaign_window_sha256"] == "a" * 64
    assert observed["kwargs"]["require_job_cgroup_zero_swap"] is True
    assert observed["kwargs"]["allow_physical_pressure_tree_cap"] is True
    assert observed["kwargs"]["tree_cap_bytes"] == 16 * 1024**3
    assert observed["kwargs"]["campaign_window_path"] == ROOT / "fixed-window.json"
    assert observed["kwargs"]["campaign_accounting_path"] == ROOT / "campaign-accounting.jsonl"
    assert observed["kwargs"]["tree_accounting_root_pid"] == os.getpid()
    assert result["details"]["supervision"]["process_tree_root_pid"] == os.getpid()
    assert result["details"]["supervision"]["service_cgroup_membership"] == _unified_cgroup_membership()
    assert result["details"]["supervision"]["campaign_closeout_reserve_seconds"] == 600
    assert result["details"]["supervision"]["process_tree_cleanup_required"] is True


def test_v20_service_minus_s_parent_launches_qualified_checker_child(
    tmp_path,
):
    import json
    import os
    import subprocess
    import sys

    harness = r"""
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

root = Path.cwd()
sys.path.insert(0, str(root))
import scripts.task40_v20_service_workflow as workflow

assert "numpy" not in sys.modules
evidence = Path(sys.argv[1])
evidence.mkdir(parents=True)
event_log = evidence / "clock.jsonl"
event_log.touch()
captured = {}
real_run = workflow.subprocess.run
child_response = {
    "return_code": 0,
    "payload": {"status": "PASS"},
    "details": {"kind": "test-checker", "returncode": 0},
}

def fake_run(argv, *, cwd, env, capture_output, text):
    captured.update(argv=argv, cwd=str(cwd), env=env)
    assert argv[0] == "/qualified/runtime/bin/python"
    assert "-S" not in argv
    assert env["_MYFENICS_WSL_QUALIFIED_ACTIVATION"] == "1"
    request = json.loads(Path(argv[-1]).read_text(encoding="utf-8"))
    assert "environment" not in request
    assert request["activation_marker"] == "1"
    assert request["service_parent_pid"] == os.getpid()
    probe = real_run(
        [
            sys.executable,
            "-c",
            "import json,os; from benchmarks.task038_full3d_jit_staging import process_tree_snapshot; root=os.getppid(); sample=process_tree_snapshot(root,'workflow',0,pss_sampling_policy='disabled_by_profile'); print(json.dumps({'parent_pid':root,'child_pid':os.getpid(),'cgroup':next(x.split(':',2)[2].strip() for x in open('/proc/self/cgroup') if x.startswith('0::')),'root_pid':sample['root_pid'],'member_pids':[member['pid'] for member in sample['members']],'rss_bytes':sample['rss_bytes']}))",
        ],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    child_identity = json.loads(probe.stdout)
    assert child_identity["parent_pid"] == os.getpid()
    assert child_identity["cgroup"] == request["service_cgroup_membership"]
    assert child_identity["root_pid"] == request["service_parent_pid"]
    assert child_identity["parent_pid"] in child_identity["member_pids"]
    assert child_identity["child_pid"] in child_identity["member_pids"]
    assert child_identity["rss_bytes"] > 0
    captured["child_cgroup"] = child_identity["cgroup"]
    Path(request["response_path"]).write_text(
        json.dumps(child_response), encoding="utf-8"
    )
    return SimpleNamespace(returncode=0, stdout="", stderr="")

workflow.subprocess.run = fake_run
events = []
result = workflow._supervise_required_checker(
    command=["/qualified/runtime/bin/python", "-m", "checker"],
    checker_kind="test-checker",
    evidence_directory=evidence,
    runtime_prefix=Path("/qualified/runtime"),
    environment={
        **os.environ,
        "_MYFENICS_WSL_QUALIFIED_ACTIVATION": "1",
    },
    repo_root=root,
    campaign_window=root / "fixed-window.json",
    campaign_sha256="a" * 64,
    campaign_accounting=root / "campaign-accounting.jsonl",
    source_state={"branch": "test", "clean": True},
    profile="task40extra_v20_p6_y_orbit_target_original_ny8_v1",
    events=events,
    event_log=event_log,
    event_identity={"source_sha": "b" * 40},
)
assert "numpy" not in sys.modules
print(json.dumps({
    "argv": captured["argv"],
    "activation": captured["env"]["_MYFENICS_WSL_QUALIFIED_ACTIVATION"],
    "child_cgroup": captured["child_cgroup"],
    "numpy_loaded": "numpy" in sys.modules,
    "return_code": result[0],
    "checker_payload": result[1],
    "clock_event": events[-1]["label"],
}))
"""
    completed = subprocess.run(
        [sys.executable, "-S", "-c", harness, str(tmp_path / "minus-s-evidence")],
        cwd=ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=True,
    )
    result = json.loads(completed.stdout)

    assert result["numpy_loaded"] is False
    assert result["activation"] == "1"
    assert result["child_cgroup"]
    assert result["argv"][0] == "/qualified/runtime/bin/python"
    assert "-S" not in result["argv"]
    assert result["return_code"] == 0
    assert result["checker_payload"] == {"status": "PASS"}
    assert result["clock_event"] == "required_checker_finished"


@pytest.mark.parametrize("filename", V20_INPUTS)
def test_v20_run_case_real_launcher_rejects_run_identity_near_miss(
    filename, monkeypatch, tmp_path, capsys
):
    from dataclasses import replace

    from scripts import run_case
    from src.runners import task038_launcher, task40_v10_campaign

    real_launcher = task038_launcher.launch_specification
    called = {}

    def alter_then_call_real_launcher(specification, **kwargs):
        identity = dict(specification.identity)
        identity["run_id"] = str(identity["run_id"]) + "_near_miss"
        altered = replace(specification, identity=identity)
        called["run_id"] = altered.identity["run_id"]
        return real_launcher(altered, contract_probe=True, **kwargs)

    monkeypatch.setattr(
        task038_launcher, "launch_specification", alter_then_call_real_launcher
    )
    monkeypatch.setattr(
        task40_v10_campaign,
        "load_fixed_campaign_window",
        lambda *_args, **_kwargs: pytest.fail(
            "an unregistered V20 identity reached campaign loading"
        ),
    )

    return_code = run_case.main([
        str(INPUT_ROOT / filename),
        "--task40-v10-campaign-window",
        str(tmp_path / "must-not-be-read.json"),
    ])
    captured = capsys.readouterr()
    assert return_code == 2
    assert called["run_id"].endswith("_near_miss")
    assert "Task40 V20 run/profile/model/stage/strategy/stop-stage identity is not registered" in captured.err


@pytest.mark.parametrize(
    "profile_identity",
    [
        "task40extra_v20_p6_y_orbit_e2_reference_v1",
        "task40extra_v20_p6_y_orbit_target_original_ny8_v1",
    ],
)
def test_v20_e2_and_target_v14_runtime_use_fixed_v10_campaign_view_without_fe(
    profile_identity, monkeypatch, tmp_path: Path
):
    from src.io.physical_intermediate_profile import profile_facts
    from src.runners import task40_v10_campaign
    from src.runners.physical_p4_schur_v14 import _V14Runtime, _abi_facts
    from src.runners.task40_v10_worker import _candidate_contract
    from src.runners.workflow_timebase import clock_sample
    from src.solvers.task40_v20_registry import TASK40_V20_CASES_BY_PROFILE

    window_path = tmp_path / "fixed-window.json"
    accounting_path = tmp_path / "fixed-accounting.jsonl"
    window_sha = "a" * 64
    window = SimpleNamespace(
        sha256=window_sha,
        path=window_path,
        total_seconds=86_400.0,
    )
    state = {
        "remaining_numerical_seconds": 12_345.0,
        "sample": clock_sample(),
        "path": str(accounting_path),
    }

    def load_window(path):
        assert Path(path) == window_path
        return window

    def read_state(requested_window, path, *, namespace_identity):
        assert requested_window is window
        assert Path(path) == accounting_path
        assert namespace_identity
        return state

    monkeypatch.setattr(task40_v10_campaign, "load_fixed_campaign_window", load_window)
    monkeypatch.setattr(task40_v10_campaign, "read_campaign_state", read_state)
    monkeypatch.setenv("TASK40_V10_CAMPAIGN_WINDOW", str(window_path))
    monkeypatch.setenv("TASK40_V10_CAMPAIGN_WINDOW_SHA256", window_sha)
    monkeypatch.setenv("TASK40_V10_CAMPAIGN_ACCOUNTING", str(accounting_path))
    monkeypatch.setenv(
        "PHYSICAL_WATCHDOG_PHASE_PATH", str(tmp_path / "workflow_phase.json")
    )

    case = TASK40_V20_CASES_BY_PROFILE[profile_identity]
    contract = profile_facts(profile_identity)
    resources = contract["resources"]
    if "pss_sampling_policy" in resources:
        monkeypatch.setenv(
            "PHYSICAL_WATCHDOG_PSS_POLICY", resources["pss_sampling_policy"]
        )
    if "watchdog_memory_policy" in resources:
        monkeypatch.setenv(
            "PHYSICAL_WATCHDOG_MEMORY_POLICY", resources["watchdog_memory_policy"]
        )
    runtime = _V14Runtime(
        tmp_path,
        case.solver_stage,
        contract,
        root=ROOT,
        source_sha="a" * 40,
        batch_identity=f"task40_review_v20_{case.mesh_id.lower()}_p6_reference",
        evidence_prefix=f"v20_{case.mesh_id.lower()}_campaign_fixture",
    )

    abi = _abi_facts(profile_identity=profile_identity)
    payload = load_and_resolve(ROOT / case.input_path).as_jsonable()
    worker_contract = _candidate_contract(
        payload,
        contract,
        runtime,
        profile_identity=profile_identity,
    )

    assert abi["profile_identity"] == profile_identity
    assert abi["scalar"] == "complex128"
    assert abi["integer"] == "int32"
    assert runtime.campaign_context["read_only"] is True
    assert runtime.campaign_context["window_sha256"] == window_sha
    assert runtime.shared_budget["schema"] == (
        "task40extra.review_v10_campaign_worker_view.v1"
    )
    assert runtime.workflow_clock_source == (
        "task40_v10_fixed_campaign_read_only_projection"
    )
    assert runtime.workflow_reserved_seconds == state["remaining_numerical_seconds"]
    assert worker_contract["checks"] and all(worker_contract["checks"].values())
    assert worker_contract["schema"] == (
        "task40extra.review_v20_one_q_p6_reference_worker_contract.v1"
    )


@pytest.mark.parametrize(
    "profile_identity",
    [
        "task40extra_v20_p6_y_orbit_e2_reference_v1",
        "task40extra_v20_p6_y_orbit_target_original_ny8_v1",
    ],
)
def test_v20_v14_runtime_rejects_unregistered_campaign_scope_before_window_read(
    profile_identity, monkeypatch, tmp_path: Path
):
    from src.io.physical_intermediate_profile import profile_facts
    from src.runners import task40_v10_campaign
    from src.runners.physical_p4_schur_v14 import _V14Runtime
    from src.solvers.task40_v20_registry import TASK40_V20_CASES_BY_PROFILE

    contract = profile_facts(profile_identity)
    contract["scope"] += "_unregistered"
    monkeypatch.setenv(
        "TASK40_V10_CAMPAIGN_WINDOW", str(tmp_path / "must_not_be_read.json")
    )
    monkeypatch.setattr(
        task40_v10_campaign,
        "load_fixed_campaign_window",
        lambda *_args, **_kwargs: pytest.fail(
            "an unregistered campaign scope reached window loading"
        ),
    )
    resources = contract["resources"]
    if "pss_sampling_policy" in resources:
        monkeypatch.setenv(
            "PHYSICAL_WATCHDOG_PSS_POLICY", resources["pss_sampling_policy"]
        )
    if "watchdog_memory_policy" in resources:
        monkeypatch.setenv(
            "PHYSICAL_WATCHDOG_MEMORY_POLICY", resources["watchdog_memory_policy"]
        )
    case = TASK40_V20_CASES_BY_PROFILE[profile_identity]
    with pytest.raises(RuntimeError, match="rejected this exact stage/profile/scope"):
        _V14Runtime(
            tmp_path,
            case.solver_stage,
            contract,
            root=ROOT,
            source_sha="b" * 40,
            batch_identity=f"task40_review_v20_{case.mesh_id.lower()}_wrong_scope",
            evidence_prefix=f"v20_{case.mesh_id.lower()}_wrong_scope_fixture",
        )
