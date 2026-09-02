"""Focused contracts for the Task040 fixed-LOR L2 action-only route."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from mpi4py import MPI
from petsc4py import PETSc

from benchmarks.task040_level_a import (
    V9_E_LOR_L2_MARKER_SEQUENCE,
    V9_E_LOR_L2_ONLY_FLAG,
    V9_E_LOR_L2_ONLY_HARD_STOP_BYTES,
    V9_E_LOR_L2_ONLY_TIMEOUT_SECONDS,
    build_task040_level_a_plan,
)
from benchmarks.task040_level_a_watchdog import (
    V9_E_LOR_L2_MARKER_SEQUENCE as WATCHDOG_L2_MARKER_SEQUENCE,
)
from benchmarks.task040_level_a_watchdog import (
    build_task040_level_a_watchdog_plan,
)
from src.solvers.hcurl_fixed_lor_positive_screen import (
    V9_E_LOR_L2_MARKER_SEQUENCE as CORE_L2_MARKER_SEQUENCE,
)
from src.solvers.hcurl_fixed_lor_positive_screen import (
    _create_counted_action,
    _deterministic_probe,
    _explicit_true_residual,
    _marker,
    _run_fixed_right_fgmres,
    _validate_input,
)


def _paths(tmp_path: Path) -> tuple[Path, Path]:
    root = Path(__file__).resolve().parents[2]
    official = root / "input/official/task039/5nm_p6h10_full3d_direct_mpi8.dat"
    spool = tmp_path / "unused_exact_spool"
    return official, spool


def test_l2c_plan_binds_only_official_inputs_and_watchdog(tmp_path: Path) -> None:
    official, spool = _paths(tmp_path)
    values = {
        "input_path": official,
        "exact_spool_root": spool,
        "run_directory": tmp_path / "l2c-plan",
        "source_sha": "a" * 40,
        "v9_e_lor_l2_only": True,
    }
    plan = build_task040_level_a_plan(**values)
    assert plan["route"] == "V9_E_LOR_L2"
    assert tuple(plan["marker_sequence"]) == V9_E_LOR_L2_MARKER_SEQUENCE
    assert CORE_L2_MARKER_SEQUENCE == V9_E_LOR_L2_MARKER_SEQUENCE
    assert WATCHDOG_L2_MARKER_SEQUENCE == V9_E_LOR_L2_MARKER_SEQUENCE
    with pytest.raises(ValueError, match="official"):
        _validate_input(Path("input/official/task039/not_l2c.dat"), "0" * 64)
    assert plan["input"] == str(official.resolve())
    assert plan["mpi_size"] == 8
    assert plan["threads"] == 1
    assert plan["timeout_seconds"] == V9_E_LOR_L2_ONLY_TIMEOUT_SECONDS
    assert plan["absolute_terminate_memory_bytes"] == (
        V9_E_LOR_L2_ONLY_HARD_STOP_BYTES
    )
    assert plan["fixed_configuration"]["mass_coefficient"] == 1.0
    assert plan["fixed_configuration"]["additional_absorbing_shift"] == 0.0
    watched = build_task040_level_a_watchdog_plan(**values)
    assert watched["watchdog"]["hard_stop_bytes"] == (
        V9_E_LOR_L2_ONLY_HARD_STOP_BYTES
    )
    assert watched["watchdog"]["timeout_seconds"] == (
        V9_E_LOR_L2_ONLY_TIMEOUT_SECONDS
    )
    assert watched["watchdog"]["swap_limit_bytes"] == 0
    assert watched["watchdog"]["cleanup_stage"] == (
        "v9_e_lor_l2_cleanup_complete"
    )
    assert V9_E_LOR_L2_ONLY_FLAG in watched["worker_argv"]
    with pytest.raises(ValueError, match="mutually exclusive"):
        build_task040_level_a_plan(
            **values,
            v8_full_spectrum_only=True,
        )


def test_l2c_marker_collective_keeps_nonroot_in_collective() -> None:
    records = []
    callback = (
        (lambda stage, detail: records.append((stage, detail)))
        if MPI.COMM_WORLD.rank == 0
        else None
    )
    _marker(
        "v9_e_lor_l2_preflight", callback, MPI.COMM_WORLD, time.monotonic(), None
    )
    assert MPI.COMM_WORLD.allreduce(len(records), op=MPI.SUM) == 1
    if MPI.COMM_WORLD.rank == 0:
        assert records[0][0] == "v9_e_lor_l2_preflight"
        assert records[0][1]["action_apply_count"] == 0


class _IdentityOperatorContext:
    def __init__(self) -> None:
        self.destroyed = False

    def mult(self, _matrix, source, target) -> None:
        target.set(0.0)
        target.axpy(PETSc.ScalarType(1.0), source)

    def destroy(self, _matrix=None) -> None:
        self.destroyed = True


class _IdentityService:
    def __init__(self) -> None:
        self.apply_count = 0

    def apply(self, _pc, source, target) -> None:
        self.apply_count += 1
        target.set(0.0)
        target.axpy(PETSc.ScalarType(1.0), source)


def test_l2c_fixed_ksp_probe_residual_and_lifecycle() -> None:
    raw_context = _IdentityOperatorContext()
    global_size = 4 * MPI.COMM_WORLD.size
    raw_operator = PETSc.Mat().createPython(
        ((4, global_size), (4, global_size)),
        context=raw_context,
        comm=MPI.COMM_WORLD,
    )
    raw_operator.setUp()
    counted, counter = _create_counted_action(raw_operator)
    probe = _deterministic_probe(counted.createVecRight())
    rhs = counted.createVecLeft()
    repeated = counted.createVecLeft()
    scaled = counted.createVecLeft()
    scaled_probe = probe.copy()
    try:
        counted.mult(probe, rhs)
        counted.mult(probe, repeated)
        repeated.axpy(PETSc.ScalarType(-1.0), rhs)
        assert repeated.norm() == 0.0
        scaled_probe.scale(PETSc.ScalarType(0.25 - 0.5j))
        counted.mult(scaled_probe, scaled)
        scaled.axpy(PETSc.ScalarType(-0.25 + 0.5j), rhs)
        assert scaled.norm() == 0.0
        before_ksp = counter.apply_count
        service = _IdentityService()
        checkpoint_values: list[tuple[int, float]] = []

        def checkpoint(iteration: int, residual: float) -> None:
            checkpoint_values.append((iteration, float(residual)))

        solution, diagnostics = _run_fixed_right_fgmres(
            counted, rhs, service, checkpoint_callback=checkpoint
        )
        assert counter.apply_count == diagnostics["exact_action_apply_count"]
        assert counter.apply_count > before_ksp
        residual = _explicit_true_residual(counted, solution, rhs)
        assert residual <= 1.0e-12
        assert counter.apply_count == diagnostics["exact_action_apply_count"] + 1
        assert diagnostics["ksp_type"] == "fgmres"
        assert diagnostics["pc_side"] == "right"
        assert diagnostics["pc_type"] == "python"
        assert diagnostics["ksp_destroyed"] is True
        assert diagnostics["pc_context_destroyed_after_ksp_destroy"] is True
        assert diagnostics["restart"] == 64
        assert diagnostics["max_it"] == 256
        assert diagnostics["rtol"] == 1.0e-8
        assert diagnostics["atol"] == 0.0
        assert diagnostics["norm_type"] == "unpreconditioned"
        assert diagnostics["initial_guess_nonzero"] is False
        assert diagnostics["zero_initial_guess"] is True
        assert diagnostics["reason"] > 0
        assert service.apply_count > 0
        assert diagnostics["service_pc_apply_count"] == service.apply_count
        assert any(iteration == 0 for iteration, _ in checkpoint_values)
        assert {
            str(iteration): residual for iteration, residual in checkpoint_values
        } == diagnostics["checkpoints"]
        assert set(diagnostics["checkpoints"]) <= {
            "0",
            "8",
            "16",
            "32",
            "64",
            "128",
            "256",
        }
    finally:
        if "solution" in locals():
            solution.destroy()
        for vector in (rhs, probe, repeated, scaled, scaled_probe):
            vector.destroy()
        counted.destroy()
        counter.destroy()
        assert counter.destroyed is True
        raw_operator.destroy()
        raw_context.destroy()
        assert raw_context.destroyed is True
