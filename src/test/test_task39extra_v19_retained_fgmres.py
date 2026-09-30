"""Real PETSc checks for physical stopping on a smaller Krylov space."""

from types import SimpleNamespace

import numpy as np
import pytest
from petsc4py import PETSc

from src.runners.physical_retained_outer_adapter import RetainedOuterAdapter
from src.runners import physical_p4_schur_v14
from src.solvers.physical_retained_fgmres import run_retained_fgmres


def _solve(matrix, *, physical_scale=1.0, port_error=0.0, stop=lambda: False):
    rhs = PETSc.Vec().createSeq(len(matrix), comm=PETSc.COMM_SELF)
    rhs.array[:] = 1.0
    rows, checkpoints = [], []

    def action(source):
        target = source.duplicate()
        target.array[:] = matrix @ source.array_r
        return target

    def evaluate(y, residual):
        rho = float(residual.norm()) / rhs.norm()
        return {"original_A6_relative": physical_scale * rho,
                "port_closure_relative": port_error,
                "internal_residual_relative": 0.0,
                "native_identity_relative": 0.0,
                "schur_port_identity_relative": 0.0,
                "retained_solution_norm": float(y.norm())}

    try:
        result = run_retained_fgmres(
            rhs, action, lambda source: source.copy(), evaluate=evaluate,
            checkpoint=lambda it, y, facts: checkpoints.append((it, y.array_r.copy())),
            append=lambda name, row: rows.append((name, row)),
            seconds=lambda: 1e9, stop_requested=stop,
        )
        result["final_solution"].destroy()
        return result, rows, checkpoints
    finally:
        rhs.destroy()


def test_real_ksp_solves_retained_space_with_physical_terminal_check():
    matrix = np.array([[3.0, 1j, 0.0], [0.1, 2.0, 0.3j], [0.0, 0.2, 4.0]])
    result, rows, checkpoints = _solve(matrix)
    assert result["status"] == "TRUE_RESIDUAL_PASS"
    assert result["retained_global_size"] == 3
    assert result["ksp_create_count"] == result["ksp_solve_count"] == result["ksp_destroy_count"] == 1
    assert result["final_true_residual"] < 1e-12
    phase = result["ksp_phase"]
    assert phase["scope"] == "PETSc.KSP.solve_only"
    assert phase["end_monotonic_ns"] >= phase["start_monotonic_ns"]
    assert phase["elapsed_seconds"] == result["ksp_solve_monotonic_seconds"]
    assert result["elapsed_seconds_scope"] == (
        "retained_outer_solve_clock_through_terminal_snapshot"
    )
    assert checkpoints[0][0] == 0 and np.count_nonzero(checkpoints[0][1]) == 0
    assert checkpoints[-1][0] == result["iterations"]
    np.testing.assert_allclose(matrix @ checkpoints[-1][1], np.ones(3), atol=1e-12)
    assert result["time_gate_evaluated"] is False
    assert not any(
        name in {"primary_stop.jsonl", "ksp_solve_phase.jsonl"}
        for name, _row in rows
    )


def test_schur_convergence_cannot_bypass_port_closure():
    result, _rows, _checkpoints = _solve(np.eye(3), port_error=1e-4)
    assert result["status"] != "TRUE_RESIDUAL_PASS"
    assert result["final_evaluation"]["schur_true_relative_residual"] < 1e-12
    assert result["final_evaluation"]["physical_residual_pass"] is False


def test_user_stop_preserves_a_terminal_checkpoint_and_closes_ksp():
    result, _rows, checkpoints = _solve(np.eye(3), stop=lambda: True)
    assert result["status"] == "USER_CONTROLLED_STOP"
    assert result["iterations"] == 0
    assert len(checkpoints) == 1
    assert result["ksp_destroy_count"] == 1


def test_continues_same_ksp_past_64_steps_and_observes_large_time():
    # A fixed nonnormal Grcar system takes several restart cycles without
    # any PC, exposing the former 64-step hard screen on a tiny fixture.
    n = 100
    matrix = np.eye(n, dtype=complex) - np.eye(n, k=-1)
    for k in (1, 2, 3):
        matrix += np.eye(n, k=k)
    result, rows, checkpoints = _solve(matrix)
    assert result["iterations"] > 64
    assert result["status"] == "TRUE_RESIDUAL_PASS"
    assert result["screen_enabled"] is False
    assert result["ksp_solve_count"] == 1
    iterations = {row["iteration"] for name, row in rows if name == "monitor_residuals.jsonl"}
    assert set(range(0, result["iterations"], 8)) <= iterations
    saved = {it for it, _ in checkpoints}
    assert set(range(0, result["iterations"], 32)) <= saved
    assert result["elapsed_seconds"] == 1e9


def test_task40_persists_primary_and_solve_phase_before_terminal_snapshot_failure():
    rhs = PETSc.Vec().createSeq(3, comm=PETSc.COMM_SELF)
    rhs.array[:] = 1.0
    rows = []
    retained_saves = {}

    def action(source):
        target = source.duplicate()
        target.array[:] = source.array_r
        return target

    def evaluate(y, residual):
        rho = float(residual.norm()) / rhs.norm()
        return {
            "original_A6_relative": rho,
            "port_closure_relative": 0.0,
            "internal_residual_relative": 0.0,
            "native_identity_relative": 0.0,
            "schur_port_identity_relative": 0.0,
        }

    def save_retained(iteration, _vector):
        retained_saves[iteration] = retained_saves.get(iteration, 0) + 1
        if iteration > 0 and retained_saves[iteration] == 2:
            raise RuntimeError("terminal snapshot fixture failure")

    try:
        with pytest.raises(RuntimeError, match="terminal snapshot fixture failure"):
            run_retained_fgmres(
                rhs,
                action,
                lambda source: source.copy(),
                evaluate=evaluate,
                checkpoint=lambda *_args: None,
                append=lambda name, row: rows.append((name, row)),
                seconds=lambda: 0.0,
                save_retained=save_retained,
                persist_native_stop_records=True,
            )
    finally:
        rhs.destroy()

    names = [name for name, _row in rows]
    primary = next(row for name, row in rows if name == "primary_stop.jsonl")
    solve_phase = next(row for name, row in rows if name == "ksp_solve_phase.jsonl")
    failure = next(row for name, row in rows if name == "ksp_followup_failures.jsonl")
    assert primary["gate"] == "full_physical_residual_pass"
    assert primary["applied_status"] == "TRUE_RESIDUAL_PASS"
    assert primary["proposed_petsc_reason"] != 0
    assert solve_phase["solve_returned"] is True
    assert isinstance(solve_phase["converged_reason"], int)
    assert isinstance(solve_phase["iteration_count"], int)
    assert solve_phase["end_monotonic_ns"] >= solve_phase["start_monotonic_ns"]
    assert solve_phase["ksp_solve_monotonic_seconds"] >= 0.0
    assert failure["phase"] == "terminal_snapshot"
    assert failure["primary_stop_record_status"] == "persisted"
    assert failure["ksp_solve_record_status"] == "persisted"
    assert names.index("primary_stop.jsonl") < names.index("ksp_solve_phase.jsonl")
    assert names.index("ksp_solve_phase.jsonl") < names.index("ksp_followup_failures.jsonl")


def test_task40_release_failure_appends_without_overwriting_primary_stop():
    rows = []

    def fail_release_marker(_name, _facts):
        raise RuntimeError("release marker fixture failure")

    adapter = RetainedOuterAdapter.__new__(RetainedOuterAdapter)
    adapter._released_after_final_residual = False
    adapter._final_packet_saved = True
    adapter._released_facts = None
    adapter.runtime = SimpleNamespace(marker=fail_release_marker)
    adapter.identity_cache_mode = "shared_read_only_per_interior_shape"
    adapter.evidence_prefix = "task40"
    adapter.persist_native_stop_records = True
    adapter._append_record = lambda name, row: rows.append((name, row))
    adapter.primary_stop_record = {"gate": "full_physical_residual_pass"}
    adapter.ksp_solve_phase_record = {"converged_reason": 2}
    adapter.facts = lambda: {"primary_stop_record": adapter.primary_stop_record}

    with pytest.raises(RuntimeError, match="release marker fixture failure"):
        adapter.release_after_final_residual()

    assert len(rows) == 1
    name, record = rows[0]
    assert name == "ksp_followup_failures.jsonl"
    assert record["phase"] == "release_started_marker"
    assert record["primary_stop_record"] == {"gate": "full_physical_residual_pass"}
    assert record["ksp_solve_phase_record"] == {"converged_reason": 2}


def test_task40_ksp_exception_persists_elapsed_time_and_unknown_native_fields():
    rhs = PETSc.Vec().createSeq(2, comm=PETSc.COMM_SELF)
    rhs.array[:] = 1.0
    rows = []

    def action(source):
        target = source.duplicate()
        target.array[:] = source.array_r
        return target

    def fail_evaluation(_y, _residual):
        raise RuntimeError("KSP callback fixture failure")

    try:
        with pytest.raises(Exception):
            run_retained_fgmres(
                rhs,
                action,
                lambda source: source.copy(),
                evaluate=fail_evaluation,
                checkpoint=lambda *_args: None,
                append=lambda name, row: rows.append((name, row)),
                seconds=lambda: 0.0,
                persist_native_stop_records=True,
            )
    finally:
        rhs.destroy()

    solve_phase = next(row for name, row in rows if name == "ksp_solve_phase.jsonl")
    failure = next(row for name, row in rows if name == "ksp_followup_failures.jsonl")
    assert solve_phase["solve_returned"] is False
    assert solve_phase["solve_error"]["error_type"]
    assert solve_phase["end_monotonic_ns"] >= solve_phase["start_monotonic_ns"]
    assert solve_phase["ksp_solve_monotonic_seconds"] >= 0.0
    assert isinstance(solve_phase["outer_matvec_count"], int)
    assert isinstance(solve_phase["outer_pc_apply_count"], int)
    for key, read_error_key in (
        ("converged_reason", "converged_reason"),
        ("iteration_count", "iteration_count"),
    ):
        if solve_phase[key] == "unknown":
            assert read_error_key in solve_phase["read_errors"]
        else:
            assert isinstance(solve_phase[key], int)
    assert failure["phase"] == "ksp_solve"
    assert failure["ksp_solve_record_status"] == "persisted"


def _run_task40_recorded_small_solve(case):
    rhs = PETSc.Vec().createSeq(2, comm=PETSc.COMM_SELF)
    rhs.array[:] = 1.0
    rows = []

    def action(source):
        target = source.duplicate()
        if case == "nonfinite_metric":
            target.array[:] = source.array_r
        else:
            target.array[:] = np.eye(2, dtype=np.complex128) @ source.array_r
        return target

    def evaluate(y, residual):
        del y
        relative = float(residual.norm()) / float(rhs.norm())
        facts = {
            "original_A6_relative": relative,
            "port_closure_relative": 0.0,
            "internal_residual_relative": 0.0,
            "native_identity_relative": 0.0,
            "schur_port_identity_relative": 0.0,
        }
        if case == "strict_identity":
            facts["native_identity_relative"] = 2.0e-10
        elif case == "nonfinite_metric":
            facts["native_identity_relative"] = float("nan")
        elif case == "missing_metric":
            facts.pop("native_identity_relative")
        return facts

    result = None
    error = None
    try:
        result = run_retained_fgmres(
            rhs,
            action,
            lambda source: source.copy(),
            evaluate=evaluate,
            checkpoint=lambda *_args: None,
            append=lambda name, row: rows.append((name, row)),
            seconds=lambda: 0.0,
            persist_native_stop_records=True,
        )
    except BaseException as exc:
        error = exc
    finally:
        if result is not None:
            result["final_solution"].destroy()
        rhs.destroy()
    return result, rows, error


@pytest.mark.parametrize(
    "case",
    ("strict_identity", "nonfinite_metric", "missing_metric"),
)
def test_task40_small_ksp_records_strict_invalid_and_missing_inputs(
    case,
):
    _result, rows, error = _run_task40_recorded_small_solve(case)
    primary = next(
        (row for name, row in rows if name == "primary_stop.jsonl"), None
    )
    solve_phase = next(
        (row for name, row in rows if name == "ksp_solve_phase.jsonl"), None
    )
    assert primary is not None
    assert solve_phase is not None

    if case == "strict_identity":
        assert primary["gate"] == "recovery_identity_strict_gate"
        assert primary["applied_status"] == "RECOVERY_IDENTITY_GATE_FAIL"
        assert primary["raw_metrics"]["native_identity_relative"] == 2.0e-10
    elif case == "nonfinite_metric":
        assert primary["gate"] == "recovered_residual_metrics_finite_nonnegative"
        assert primary["applied_status"] == "NONFINITE_RECOVERY_RESIDUAL"
        assert "native_identity_relative" in primary["raw_metrics"]["invalid_fields"]
        assert primary["raw_metrics"]["raw_values"]["native_identity_relative"]["value"] is None
    elif case == "missing_metric":
        assert primary["gate"] == "required_recovery_metrics_present"
        assert primary["applied_status"] == "RECOVERY_METRIC_FIELDS_MISSING"
        assert primary["raw_metrics"]["missing_fields"] == ["native_identity_relative"]
        assert error is not None
    else:
        assert error is not None


def test_task40_final_release_gate_keeps_primary_and_native_solve_records(
    tmp_path, monkeypatch
):
    rows = []
    packets = []
    monkeypatch.setattr(
        physical_p4_schur_v14,
        "_save_packet",
        lambda directory, name, facts, runtime=None: packets.append(
            (directory, name, dict(facts))
        )
        or {"name": name},
    )
    runtime = SimpleNamespace(
        directory=tmp_path,
        marker=lambda *_args, **_kwargs: None,
    )
    adapter = RetainedOuterAdapter.__new__(RetainedOuterAdapter)
    adapter.persist_native_stop_records = True
    adapter._append_record = lambda name, row: rows.append((name, row))
    adapter.primary_stop_record = {
        "gate": "recovery_identity_strict_gate",
        "iteration": 8,
    }
    adapter.ksp_solve_phase_record = {
        "converged_reason": -11,
        "iteration_count": 8,
        "ksp_solve_monotonic_seconds": 12.5,
    }
    solve_result = {
        "final_evaluation": {
            "port_closure_relative": 0.0,
            "internal_residual_relative": 0.0,
            "native_identity_relative": 2.0e-10,
            "schur_port_identity_relative": 0.0,
        }
    }

    with pytest.raises(physical_p4_schur_v14.V20ReleaseGateStop) as raised:
        physical_p4_schur_v14._run_v20_release_after_final_residual(
            runtime,
            {},
            {},
            adapter,
            stage="G0",
            prefix="task40",
            identity={},
            solve_result=solve_result,
            final_solution=None,
            rhs=None,
            rhs_norm=1.0,
            final_explicit_relative=0.0,
            release_after_final_residual=True,
        )

    failure = raised.value.facts
    evidence = failure["retained_ksp_evidence"]
    assert failure["classification"] == "V20_RELEASE_GATE_FAIL"
    assert evidence["primary_stop_record"] == adapter.primary_stop_record
    assert evidence["ksp_solve_phase_record"] == adapter.ksp_solve_phase_record
    assert packets[0][2]["retained_ksp_evidence"] == evidence
    name, followup = rows[0]
    assert name == "ksp_followup_failures.jsonl"
    assert followup["phase"] == "final_release_gate"
    assert followup["primary_stop_record"] == adapter.primary_stop_record
    assert followup["ksp_solve_phase_record"] == adapter.ksp_solve_phase_record
