from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import replace
from pathlib import Path

from scripts.run_case import main as run_case_main
from src.io import load_and_resolve
from src.io.execution_plan import build_execution_plan, method_adapter_identity
from src.io.native_capacity_profile import (
    SETUP_ONLY_5NM_INPUT_SHA256,
    SETUP_ONLY_5NM_PHYSICAL_SHA256,
    SETUP_ONLY_5NM_PROFILE,
    setup_only_5nm_identity_errors,
)
from src.io.resolved_config import canonical_json_bytes, resolved_config_bytes
from src.runners.task038_input_worker import validate_worker_contract
from src.runners.task038_launcher import launch_specification

ROOT = Path(__file__).resolve().parents[2]
INPUT_DIR = ROOT / "input/task39extra_para_workstation_capacity"
SETUP_ONLY_INPUT = INPUT_DIR / "v5_node1_5nm_p6h4_q4.dat"
SETUP_ONLY_CONTRACT = {
    "profile": SETUP_ONLY_5NM_PROFILE,
    "input_sha256": SETUP_ONLY_5NM_INPUT_SHA256,
    "physical_model_sha256": SETUP_ONLY_5NM_PHYSICAL_SHA256,
    "completion_marker": "SETUP_ONLY_COMPLETED",
}


def _target_specification():
    specification = load_and_resolve(SETUP_ONLY_INPUT)
    assert specification.input_sha256 == SETUP_ONLY_5NM_INPUT_SHA256
    assert specification.physical_model_sha256 == SETUP_ONLY_5NM_PHYSICAL_SHA256
    assert specification.solver["preconditioner"] == SETUP_ONLY_5NM_PROFILE
    return specification


def test_setup_only_cli_is_identity_limited_and_explicit(monkeypatch, capsys):
    wrong_input = INPUT_DIR / "v5_node1_2nm_p6h1p5_q4.dat"
    assert run_case_main([str(wrong_input), "--setup-only"]) == 2
    assert "setup-only is restricted" in capsys.readouterr().err

    from src.runners import native_capacity

    calls = []

    def fake_launch(specification, *, setup_only=False):
        calls.append((specification.input_sha256, setup_only))
        return {"result_classification": "setup_only"}

    monkeypatch.setattr(native_capacity, "launch_native_capacity", fake_launch)
    assert run_case_main([str(SETUP_ONLY_INPUT), "--setup-only"]) == 0
    assert calls == [(SETUP_ONLY_5NM_INPUT_SHA256, True)]
    assert json.loads(capsys.readouterr().out)["result_classification"] == "setup_only"

    errors = setup_only_5nm_identity_errors(
        profile=SETUP_ONLY_5NM_PROFILE,
        method="full3d_iterative",
        input_sha256=SETUP_ONLY_5NM_INPUT_SHA256,
        physical_model_sha256="0" * 64,
    )
    assert errors == ["setup-only physical SHA does not match the reviewed model"]


def test_worker_cli_manifest_mode_and_execution_plan_agree(tmp_path):
    specification = _target_specification()
    run_directory = tmp_path / "run"
    run_directory.mkdir()
    plan = build_execution_plan(
        specification,
        run_directory,
        source_sha="a" * 40,
        mpiexec_command="/opt/mpiexec",
        python_executable="/opt/python",
        setup_only=True,
    )
    assert plan.setup_only is True
    assert plan.argv[-1] == "--setup-only"

    full_plan = build_execution_plan(
        specification,
        run_directory,
        source_sha="a" * 40,
        mpiexec_command="/opt/mpiexec",
        python_executable="/opt/python",
    )
    assert full_plan.setup_only is False
    assert "--setup-only" not in full_plan.argv

    resolved_bytes = resolved_config_bytes(specification)
    plan.expected_resolved_config.write_bytes(resolved_bytes)
    (run_directory / "input_original.dat").write_bytes(specification.raw_input_bytes)
    snapshot = specification.as_jsonable()
    resolved_sha = hashlib.sha256(resolved_bytes).hexdigest()
    manifest = {
        "model_id": snapshot["model_id"],
        "run_id": snapshot["run_id"],
        "comparison_group": snapshot["comparison_group"],
        "input_path": snapshot["provenance"]["source_path"],
        "method": specification.method["kind"],
        "solver": snapshot["solver"],
        "mpi_size": specification.execution["mpi_size"],
        "requested_modes": specification.method.get("requested_modes_per_direction"),
        "input_sha256": specification.input_sha256,
        "physical_model_sha256": specification.physical_model_sha256,
        "source_sha": "a" * 40,
        "resolved_config_sha256": resolved_sha,
        "resolved_method_adapter": method_adapter_identity("full3d_iterative"),
        "output_directory": str(run_directory.resolve()),
        "numerical_output_directory": str(run_directory.resolve() / "numerical_output"),
        "execution_mode": "setup_only",
        "setup_only_contract": SETUP_ONLY_CONTRACT,
    }
    plan.expected_manifest.write_bytes(canonical_json_bytes(manifest) + b"\n")
    kwargs = {
        "resolved_config": plan.expected_resolved_config,
        "manifest": plan.expected_manifest,
        "expected_input_sha256": specification.input_sha256,
        "expected_physical_model_sha256": specification.physical_model_sha256,
        "expected_source_sha": "a" * 40,
        "expected_mpi_size": specification.execution["mpi_size"],
        "expected_method": "full3d_iterative",
        "expected_adapter": method_adapter_identity("full3d_iterative"),
        "expected_output_directory": run_directory,
        "expected_resolved_config_sha256": resolved_sha,
        "actual_mpi_size": specification.execution["mpi_size"],
        "setup_only": True,
    }
    assert validate_worker_contract(**kwargs) == []
    assert any(
        "execution mode mismatch" in error
        for error in validate_worker_contract(**{**kwargs, "setup_only": False})
    )


def test_launcher_requires_setup_marker_and_records_setup_only_result(
    tmp_path, monkeypatch
):
    specification = replace(
        _target_specification(), expected_output_parent=tmp_path / "runs"
    )
    captured = {}

    def source_gate(_cwd, source_sha):
        return {
            "source_sha": source_sha,
            "tracked_and_nonignored_untracked_clean": True,
        }

    def fake_supervise(argv, _watchdog_directory, **_kwargs):
        captured["argv"] = argv
        run_directory = Path(argv[argv.index("--manifest") + 1]).parent
        if captured.get("write_setup_summary", True):
            worker_summary = {
                "status": "SETUP_ONLY_COMPLETED",
                "result_classification": "setup_only",
                "execution_mode": "setup_only",
                "retained_runtime": {"setup_checks": {"status": "PASS"}},
                "setup_only_facts": {"status": "SETUP_ONLY_COMPLETED"},
                "outer_solve_status": "NOT_RUN",
                "full_a6_recovery_status": "NOT_RUN",
                "rta_status": "NOT_RUN",
                "physical_checker_status": "NOT_RUN",
            }
            (run_directory / "physical_intermediate_summary.json").write_text(
                json.dumps(worker_summary), encoding="utf-8"
            )
        return {
            "leader_exit_code": 0,
            "classification": "COMPLETED",
            "job_swap_activity": "global_activity_observed_only",
            "launch_envelope": {"effective_available_bytes": 1_500_000_000_000},
            "rss_warning_bytes": 1_170_000_000_000,
            "rss_hard_limit_bytes": 1_300_000_000_000,
            "memory_scope": "process_tree",
            "resource_stop_policy": "measured_tree_rss_only_v3",
            "startup_headroom_bytes": 137_438_953_472,
            "swap_policy": "observe_only",
        }

    monkeypatch.setattr("src.runners.task038_launcher._physical_source_gate", source_gate)
    monkeypatch.setattr("benchmarks.subreaper_watchdog.supervise", fake_supervise)
    result = launch_specification(
        specification,
        source_sha="a" * 40,
        timestamp="setup-only-contract",
        setup_only=True,
    )
    run_directory = Path(result["run_directory"])
    manifest = json.loads((run_directory / "run_manifest.json").read_text())
    summary = json.loads((run_directory / "run_summary.json").read_text())
    assert "--setup-only" in captured["argv"]
    assert manifest["execution_mode"] == "setup_only"
    assert manifest["setup_only_contract"] == SETUP_ONLY_CONTRACT
    assert manifest["worker_command"] == captured["argv"]
    assert result["result_classification"] == "setup_only"
    assert summary["result_classification"] == "setup_only"
    assert summary["complete_solve"] is False
    assert summary["not_run"] == {
        "outer_solve": "NOT_RUN",
        "full_a6_recovery": "NOT_RUN",
        "rta": "NOT_RUN",
        "physical_checker": "NOT_RUN",
    }

    captured["write_setup_summary"] = False
    incomplete = launch_specification(
        specification,
        source_sha="a" * 40,
        timestamp="setup-only-missing-marker",
        setup_only=True,
    )
    assert incomplete["result_classification"] == "EVIDENCE_INCOMPLETE"
    incomplete_summary = json.loads(Path(incomplete["summary"]).read_text())
    assert incomplete_summary["setup_only"] is True
    assert incomplete_summary["complete_solve"] is False


def test_setup_only_branch_returns_before_outer_solver_dispatch():
    path = ROOT / "src/runners/physical_retained_condensed_v20.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    workflow = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "run_retained_condensed_workflow"
    )
    setup_branch = next(
        node
        for node in ast.walk(workflow)
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Name)
        and node.test.id == "setup_only"
        and any(isinstance(child, ast.Return) for child in ast.walk(node))
    )
    setup_return = min(
        child.lineno for child in ast.walk(setup_branch) if isinstance(child, ast.Return)
    )
    solve_phase = next(
        node.lineno
        for node in ast.walk(workflow)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "set_phase"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "solve"
    )
    fgmres_import = next(
        node.lineno
        for node in ast.walk(workflow)
        if isinstance(node, ast.ImportFrom)
        and node.module == "src.solvers.physical_retained_fgmres"
    )
    assert setup_return < solve_phase < fgmres_import
