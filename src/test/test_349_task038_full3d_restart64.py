"""Focused contracts for the V18 restart-64 qualification lane."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from benchmarks import run_task038_v18_restart64 as runner
from benchmarks import task038_v18_restart64_checker as checker
from src.solvers import fullspace_memory_first_krylov as krylov


def test_restart20_wrapper_keeps_the_historical_fixed_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    def fake_fixed(*args: object, **kwargs: object) -> dict[str, object]:
        calls["args"] = args
        calls["kwargs"] = kwargs
        return {"sentinel": True}

    monkeypatch.setattr(krylov, "run_fixed_restart_cycles", fake_fixed)
    result = krylov.run_restart20_cycles(
        "rhs",
        "action",
        "pc",
        max_it=40,
        residual_limit=0.0,
        resource_sample=lambda: {},
        start_iteration=0,
        checkpoint_writer=None,
        first_checkpoint_iteration=20,
        checkpoint_interval=200,
        cycle_observer=None,
        stop_on_true_residual=True,
        ksp_type="gmres",
    )

    assert result == {"sentinel": True}
    assert calls["args"] == ("rhs", "action", "pc")
    assert calls["kwargs"]["restart"] == 20  # type: ignore[index]
    assert calls["kwargs"]["cycle_max_it"] == 20  # type: ignore[index]
    assert "checkpoint_from_start" not in calls["kwargs"]  # type: ignore[operator]


def test_restart64_keeps_checkpoint_offset_outside_solver_counter() -> None:
    cycle = {
        "start_iteration": 0,
        "end_iteration": 64,
        "iterations": 64,
        "explicit_true_residual": 0.2,
        "matvec_count": 65,
        "pc_apply_count": 65,
        "ksp_destroyed": True,
        "resource": {},
    }
    result = {
        "settings": {"start_iteration": 0},
        "cycles": [cycle],
        "iterations": 64,
        "initial_true_residual": 1.0,
        "final_true_residual": 0.2,
        "matvec_count": 65,
        "pc_apply_count": 65,
        "explicit_action_count": 2,
        "ksp_destroy_count": 1,
        "elapsed_seconds": 0.0,
        "checkpoint_facts": [],
    }

    facts = runner._cycle_facts(result, "continuation", base_offset=1024)

    assert facts["settings"]["start_iteration"] == 0
    assert facts["settings"]["additional_iteration_origin"] == 0
    assert facts["settings"]["absolute_iteration_origin"] == 1000
    assert facts["cycles"][0]["additional_iteration"] == 1088
    assert facts["cycles"][0]["absolute_iteration"] == 2088
    assert facts["absolute_end_iteration"] == 2088


def test_restart64_screen_limits_and_numeric_classification_are_frozen() -> None:
    screen = {
        "cycles": [
            {"additional_iteration": 512, "explicit_true_residual": 0.2},
            {"additional_iteration": 768, "explicit_true_residual": 0.4},
            {"additional_iteration": 1024, "explicit_true_residual": 0.05},
        ]
    }
    gates = runner._screen_gates(screen)
    assert gates["passed"] is True
    assert gates["step512"]["limit"] == 0.25
    assert gates["step1024"]["limit"] == 0.10
    assert gates["r1024_over_r768"]["limit"] == 0.85

    screen["cycles"][-1]["explicit_true_residual"] = 0.2
    gates = runner._screen_gates(screen)
    assert gates["passed"] is False
    assert "step1024" in gates["gate_failures"]
    assert checker._classification([], ["numerical:screen.step1024"]) == (
        "V18_RESTART64_NUMERICAL_GATE_FAIL"
    )

    screen["cycles"][-1]["resource"] = {
        "process_tree": {"rss_bytes": runner.RSS_HARD, "swap_bytes": 0}
    }
    gates = runner._screen_gates(screen)
    assert gates["passed"] is False
    assert "resource_rss" in gates["gate_failures"]
    screen["gates"] = gates
    errors: list[str] = []
    assert "resource_rss" in checker._screen_metrics(screen, errors)["gate_failures"]
    assert errors == []


def test_qualifier_gate_blocks_screen_before_its_stage_call() -> None:
    qualifier = {
        "settings": {
            "ksp_type": "fgmres",
            "pc_side": "right",
            "restart": 64,
            "cycle_max_it": 64,
            "start_iteration": 0,
            "residual_replacement": True,
        },
        "additional_iterations": 64,
        "cycles": [
            {
                "explicit_true_residual": 0.5,
                "resource": {"process_tree": {"rss_bytes": 100, "swap_bytes": 0}},
            }
        ],
    }
    facts = {"finite": True, "owned_slave_max": 0.0, "owned_slave_count": 0}
    probe = {
        "repeat_relative": 0.0,
        "input_before_sha256": "a",
        "input_after_sha256": "a",
    }
    action_probe = {**probe, "dual_facts": facts}
    pc_probe = {
        **probe,
        "input_role": "dual_residual",
        "input_facts": facts,
        "primal_facts": facts,
    }

    assert runner._qualifier_gate_failures(qualifier, action_probe, pc_probe) == []
    qualifier["cycles"][0]["resource"]["process_tree"]["rss_bytes"] = runner.RSS_HARD
    assert runner._qualifier_gate_failures(qualifier, action_probe, pc_probe)

    source = inspect.getsource(runner._run_worker)
    assert "pc_input = rhs.copy()" in source
    assert "pc_input.axpy(-1.0, action_first)" in source
    assert '"input_role": "dual_residual"' in source
    assert 'setup["upper_cycle"].apply(checkpoint_solution)' not in source
    guard = source.index("if qualifier_gate_failures:")
    screen_call = source.index('"screen"', guard)
    assert guard < screen_call


def test_checker_restart64_stage_uses_additional_iteration_ledger() -> None:
    stage = {
        "settings": {
            "ksp_type": "fgmres",
            "pc_side": "right",
            "norm_type": "unpreconditioned",
            "restart": 64,
            "cycle_max_it": 64,
            "start_iteration": 0,
            "residual_replacement": True,
            "checkpoint_interval": 256,
            "additional_iteration_origin": 0,
            "absolute_iteration_origin": 1000,
        },
        "base_offset": 1024,
        "additional_iterations": 64,
        "absolute_end_iteration": 2088,
        "final_true_residual": 0.2,
        "matvec_count": 65,
        "pc_apply_count": 65,
        "explicit_action_count": 2,
        "ksp_destroy_count": 1,
        "cycles": [
            {
                "start_iteration": 0,
                "end_iteration": 64,
                "iterations": 64,
                "additional_iteration": 1088,
                "absolute_iteration": 2088,
                "matvec_count": 65,
                "pc_apply_count": 65,
                "explicit_true_residual": 0.2,
                "ksp_destroyed": True,
                "resource": {
                    "process_tree": {"rss_bytes": 100, "swap_bytes": 0}
                },
            }
        ],
        "checkpoint_facts": [],
    }
    errors: list[str] = []
    gates: list[str] = []

    checker._check_stage(Path("/tmp"), stage, "qualifier", 64, errors, gates)

    assert errors == []
    assert gates == []
    stage["matvec_count"] = 64
    errors = []
    checker._check_stage(Path("/tmp"), stage, "qualifier", 64, errors, [])
    assert any("ledger mismatch" in error for error in errors)


def test_restart64_checker_and_runner_keep_basis_architecture_truthful() -> None:
    banned = {"basis_in_memory", "mmap", "full_vector_buffer_limit"}
    for path in (Path(runner.__file__), Path(checker.__file__)):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        source = path.read_text(encoding="utf-8")
        assert not any(token in source for token in banned), path
        assert "DISK_FREE_HARD" not in source
        assert "disk_free_hard_gate_bytes" not in source
        if path == Path(checker.__file__):
            imports = []
            for node in tree.body:
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.append(node.module)
            assert not any(
                name.startswith(("src.solvers", "petsc4py", "mpi4py", "dolfinx"))
                for name in imports
            )
            assert 'parser.add_argument("--expected-source-sha", required=True)' in source


def test_checker_treats_resource_termination_as_a_gate() -> None:
    result = {
        "returncode": -15,
        "sample_count": 1,
        "peak_rss_bytes": checker.RSS_HARD,
        "max_swap_bytes": 0,
        "rss_watchdog_bytes": checker.RSS_WATCHDOG,
        "stop_reason": "process_tree_rss_watchdog",
        "process_group_gone": True,
        "lifecycle_failure": False,
        "all_status_readable": True,
    }
    errors: list[str] = []
    gates: list[str] = []

    checker._check_stage_result(result, "worker", errors, gates)

    assert errors == []
    assert gates == ["resource:worker.process_tree_rss_watchdog", "resource:worker RSS >= 2000000000"]
    assert checker._classification(errors, gates) == "V18_RESTART64_RESOURCE_GATE_FAIL"
    assert checker.MARKER_ENDPOINTS[0] == (
        "paths_ready",
        "abi_ready",
        "case_built",
        "checkpoint_restored",
        "qualifier_complete",
        "record_written",
        "release_complete",
    )


def test_checker_skips_unrun_screen_start_residual(tmp_path: Path) -> None:
    import numpy as np

    raw = tmp_path / "raw"
    values = np.asarray([1.0 + 2.0j], dtype=np.complex128)
    rhs_descriptor = runner.v17._write_array(raw, "same_start/rhs.npy", values)
    initial_descriptor = runner.v17._write_array(
        raw, "same_start/initial_solution.npy", values
    )
    same = {
        "rhs": {
            "descriptor": rhs_descriptor,
            "array_sha256": rhs_descriptor["array_sha256"],
        },
        "initial_solution": {
            "descriptor": initial_descriptor,
            "array_sha256": initial_descriptor["array_sha256"],
        },
        "rhs_before_sha256": rhs_descriptor["array_sha256"],
        "rhs_after_sha256": rhs_descriptor["array_sha256"],
        "initial_solution_before_sha256": initial_descriptor["array_sha256"],
        "initial_solution_after_sha256": initial_descriptor["array_sha256"],
        "input_unchanged": True,
        "finite": True,
        "initial_true_residual": 0.5,
        "screen_initial_true_residual": None,
    }
    errors: list[str] = []
    gates: list[str] = []

    checker._check_same_start(
        tmp_path,
        {"same_start": same, "screen": None},
        errors,
        gates,
    )

    assert errors == []
    assert gates == []
