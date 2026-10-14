from __future__ import annotations

import ast
import sys
from dataclasses import replace
from importlib import import_module
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType

from src.io.execution_plan import build_execution_plan
from src.io.input_validation import (
    load_and_resolve,
    simulation_config_3d_from_normalized,
)
from src.runners.task038_input_worker import (
    _dispatch_resolved_payload,
    _load_and_validate_worker_payload,
)
from src.runners.task038_launcher import _write_bootstrap, launch_specification

REPO = Path(__file__).resolve().parents[2]
INPUT = REPO / "input/task39extra_para_workstation_capacity/v7_0p7nm_si_p6_direct_n0_full.dat"
PROFILE = "dual_condensed_balh_native_0p7nm_aniso_n0_p6_direct_full_v1"


def test_direct_runner_imports_quadrature_metadata_from_runtime_module():
    runner_path = REPO / "src/runners/p6_condensed_direct.py"
    tree = ast.parse(runner_path.read_text(encoding="utf-8"))
    runner = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "run_p6_condensed_direct"
    )
    bindings = [
        (node.module, alias.name)
        for node in ast.walk(runner)
        if isinstance(node, ast.ImportFrom) and node.module is not None
        for alias in node.names
    ]
    assert (
        "src.solvers.fullspace_physical_intermediate_runtime",
        "fine_volume_quadrature_metadata",
    ) in bindings
    for module_name, symbol_name in bindings:
        module = import_module(module_name)
        if not hasattr(module, symbol_name):
            module = import_module(f"{module_name}.{symbol_name}")
        assert module is not None, f"missing {module_name}.{symbol_name}"


def test_v7_p6_direct_identity_roundtrips_through_real_worker_cfg(tmp_path):
    specification = load_and_resolve(INPUT)
    assert specification.method["kind"] == "full3d_direct"
    assert specification.solver["native_capacity_profile"] == PROFILE

    snapshot = specification.as_jsonable()
    facts = snapshot["derived"]["native_capacity_profile"]
    assert facts["identity"] == PROFILE
    assert facts["resources"]["rss_hard_limit_bytes"] == 1_800_000_000_000
    assert facts["condensed_route"]["degree"] == 6
    assert facts["condensed_route"]["rows"] == 9_281_372
    assert facts["backend"]["p4_operator"] == "NOT_BUILT"
    assert facts["backend"]["p4_factor"] == "NOT_BUILT"

    cfg = simulation_config_3d_from_normalized(snapshot)
    assert cfg.mesh_axis_cell_counts_requested == (100, 2, 234)
    assert cfg.lambda0 == 0.7
    assert cfg.petsc_direct_solver_profile == "default"

    plan = build_execution_plan(
        specification,
        tmp_path / "planned-run",
        source_sha="a" * 40,
        python_executable=REPO / ".venv/bin/python",
        mpiexec_command="/usr/bin/mpiexec",
    )
    assert plan.method == "full3d_direct"
    assert plan.adapter_identity == "task038.full3d_direct"
    assert plan.mpi_size == 1
    # The V7 rank policy is applied after mpiexec, to the actual MPI rank.
    assert plan.argv[:8] == (
        "/usr/bin/mpiexec",
        "-n",
        "1",
        "/usr/bin/numactl",
        "--interleave=0,1",
        "/usr/bin/taskset",
        "-c",
        "24",
    )
    assert plan.argv[8] == str(REPO / ".venv/bin/python")
    assert plan.argv[9:11] == ("-m", "src.runners.task038_input_worker")

    source_sha = "a" * 40
    with TemporaryDirectory(dir=tmp_path) as temporary:
        run_directory = Path(temporary) / "run"
        run_directory.mkdir()
        test_spec = replace(
            specification,
            expected_output_parent=str(run_directory.parent),
        )
        manifest, resolved_sha = _write_bootstrap(
            test_spec,
            run_directory,
            source_sha=source_sha,
            adapter_identity=plan.adapter_identity,
            start_time="2026-10-14T00:00:00Z",
        )
        assert manifest["native_capacity_profile_identity"] == PROFILE
        assert manifest["native_capacity_profile"] == facts
        assert manifest["native_capacity_contract"]["rss_hard_limit_bytes"] == 1_800_000_000_000

        resolved_path = run_directory / "resolved_config.json"
        manifest_path = run_directory / "run_manifest.json"
        resolved, errors = _load_and_validate_worker_payload(
            resolved_config=resolved_path,
            manifest=manifest_path,
            expected_input_sha256=specification.input_sha256,
            expected_physical_model_sha256=specification.physical_model_sha256,
            expected_source_sha=source_sha,
            expected_mpi_size=1,
            expected_method="full3d_direct",
            expected_adapter=plan.adapter_identity,
            expected_output_directory=run_directory,
            expected_resolved_config_sha256=resolved_sha,
            actual_mpi_size=1,
        )
        assert errors == []
        assert resolved is not None
        worker_facts = resolved["derived"]["native_capacity_profile"]
        assert worker_facts == facts
        worker_cfg = simulation_config_3d_from_normalized(resolved)
        assert worker_cfg.mesh_axis_cell_counts_requested == (100, 2, 234)


def test_worker_dispatch_selects_p6_direct_adapter_without_running_fe(monkeypatch, tmp_path):
    calls = []
    fake_module = ModuleType("src.runners.p6_condensed_direct")

    def fake_runner(payload, directory, *, source_sha):
        calls.append((payload["run_id"], Path(directory), source_sha))
        return {"passed": True, "errors": []}

    fake_module.run_p6_condensed_direct = fake_runner
    monkeypatch.setitem(sys.modules, "src.runners.p6_condensed_direct", fake_module)
    resolved = load_and_resolve(INPUT).as_jsonable()
    status, errors = _dispatch_resolved_payload(
        resolved,
        expected_method="full3d_direct",
        output_directory=tmp_path,
        expected_source_sha="b" * 40,
    )
    assert (status, errors) == (0, [])
    assert calls == [
        (resolved["run_id"], tmp_path, "b" * 40),
    ]


def test_v7_direct_run_case_uses_the_native_rss_watchdog(monkeypatch, tmp_path):
    from benchmarks import subreaper_watchdog

    calls = []
    resources = load_and_resolve(INPUT).as_jsonable()["derived"][
        "native_capacity_profile"
    ]["resources"]

    def fake_supervise(command, directory, **kwargs):
        calls.append((tuple(command), Path(directory), kwargs))
        return {
            "leader_exit_code": 0,
            "classification": "COMPLETED",
            "job_swap_activity": "observed_only",
            "launch_envelope": {"launch_cap_bytes": 1_800_000_000_000},
            "rss_warning_bytes": resources["rss_warning_bytes"],
            "rss_hard_limit_bytes": resources["rss_hard_limit_bytes"],
            "resource_stop_policy": resources["resource_stop_policy"],
            "startup_headroom_bytes": resources["startup_headroom_bytes"],
            "swap_policy": resources["swap_policy"],
            "memory_scope": "sampled_process_tree",
        }

    monkeypatch.setattr(subreaper_watchdog, "supervise", fake_supervise)
    monkeypatch.setattr(
        "src.runners.task038_launcher._physical_source_gate",
        lambda _cwd, source: {"source_sha": source, "tracked_and_nonignored_untracked_clean": True},
    )
    specification = replace(
        load_and_resolve(INPUT), expected_output_parent=str(tmp_path)
    )
    result = launch_specification(
        specification,
        source_sha="c" * 40,
        timestamp="20261014T000000.000000Z",
        python_executable=REPO / ".venv/bin/python",
        mpiexec_command="/usr/bin/mpiexec",
        prelaunch_isolation={"status": "fake_prelaunch"},
    )

    assert result["result_classification"] == "worker_exit0"
    assert len(calls) == 1
    command, watchdog_directory, kwargs = calls[0]
    assert command[:8] == (
        "/usr/bin/mpiexec",
        "-n",
        "1",
        "/usr/bin/numactl",
        "--interleave=0,1",
        "/usr/bin/taskset",
        "-c",
        "24",
    )
    assert watchdog_directory == Path(result["run_directory"]) / "watchdog"
    assert kwargs["phase_path"] == Path(result["run_directory"]) / "workflow_phase.json"
    assert kwargs["wall_seconds"] is None
    assert kwargs["solve_seconds"] is None
    assert kwargs["rss_hard_limit_bytes"] == 1_800_000_000_000
    assert kwargs["startup_headroom_bytes"] == 137_438_953_472
    assert kwargs["resource_stop_policy"] == "measured_tree_rss_only_v3"
    assert kwargs["pss_sampling_policy"] == "disabled_by_profile"
    assert kwargs["stop_on_global_swap"] is False
    assert kwargs["grace_seconds"] == 60
    assert kwargs["hard_stop_immediate"] is True


def test_factor_lifecycle_uses_one_matrix_for_symbolic_numeric_solve(monkeypatch):
    fake_petsc4py = ModuleType("petsc4py")
    fake_petsc4py.PETSc = ModuleType("petsc4py.PETSc")
    monkeypatch.setitem(sys.modules, "petsc4py", fake_petsc4py)
    from src.runners.p6_condensed_direct import _factor_same_matrix

    class FakeFactor:
        def __init__(self):
            self.calls = []
            self.symbolic_calls = 0
            self.numeric_calls = 0
            self.solve_calls = 0
            self.preferred_ordering = "MMD_AT_PLUS_A"

        def symbolic(self, matrix):
            self.calls.append(("symbolic", matrix))
            self.symbolic_calls += 1

        def numeric(self, matrix):
            self.calls.append(("numeric", matrix))
            self.numeric_calls += 1

        def solve(self, rhs, solution):
            self.calls.append(("solve", matrix))
            self.solve_calls += 1

        def info(self):
            return {"INFOG(1)": 0}

        def refinement_settings(self):
            return {"count": 0}

    matrix, rhs, solution = object(), object(), object()
    factor = FakeFactor()
    markers = []
    identity = _factor_same_matrix(
        factor, matrix, rhs, solution, lambda *row: markers.append(row)
    )
    assert identity == id(matrix)
    assert [name for name, _value in factor.calls] == [
        "symbolic",
        "numeric",
        "solve",
    ]
    assert all(value is matrix for _name, value in factor.calls)
    assert len(markers) == 2
