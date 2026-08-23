"""Pure K0 Krylov settings, linearity, and checker contracts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from petsc4py import PETSc

from benchmarks.task038_full3d_lor_hx_krylov_checker import (
    K0_CHECKPOINTS,
    K0_GMRES_MAX_IT,
    K0_GMRES_RESTART,
    K0_GMRES_RTOL,
    K0_TRUE_RESIDUAL_LIMIT,
    OLD_L2_RECORD_SHA,
    check_record,
)
from src.solvers.fullspace_lor_hx_krylov import (
    K0_ALPHA_PRODUCTION_APPLIED,
    K0_DIRECTION_COEFFICIENTS,
    K0_LINEARITY_LIMIT,
    K0_REPEAT_LIMIT,
    K0_SETTINGS,
    _checkpoint_statuses,
    alpha_diagnostic,
    canonical_direction_mask,
    canonical_key_set_sha256,
    destroy_k0_gmres_result,
    run_k0_gmres,
    two_direction_linearity,
)


def _write_artifact(
    raw_dir: Path,
    name: str,
    array: np.ndarray,
    descriptors: list[dict[str, object]],
) -> dict[str, str]:
    path = raw_dir / f"{name}.npy"
    array = np.asarray(array)
    np.save(path, array, allow_pickle=False)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    descriptors.append(
        {
            "name": name,
            "relative_path": path.name,
            "bytes": path.stat().st_size,
            "sha256": digest,
            "dtype": str(array.dtype),
            "shape": list(array.shape),
        }
    )
    return {"keys": f"{name}_keys", "values": name}


def _role(
    raw_dir: Path,
    name: str,
    values: np.ndarray,
    descriptors: list[dict[str, object]],
    canonical_keys: np.ndarray | None = None,
) -> dict[str, str]:
    values = np.asarray(values, dtype=np.complex128)
    keys = (
        np.asarray(canonical_keys, dtype="<U64")
        if canonical_keys is not None
        else np.asarray([f"k{index}" for index in range(values.size)], dtype="<U8")
    )
    key_name = f"{name}_keys"
    value_name = f"{name}_values"
    _write_artifact(raw_dir, key_name, keys, descriptors)
    _write_artifact(raw_dir, value_name, values, descriptors)
    return {"keys": key_name, "values": value_name}


def _synthetic_record(tmp_path: Path, *, late_only: bool = False) -> Path:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True)
    descriptors: list[dict[str, object]] = []
    source = np.asarray([1.0 + 1.0j, 2.0 - 1.0j, -1.0 + 0.5j, 3.0 + 0.25j])
    residual = np.asarray([2.0 + 0.5j, -1.0 + 1.0j, 0.5 - 2.0j, 1.0 + 0.25j])
    pc = 0.5 * residual
    action = residual.copy()
    zero = np.zeros_like(residual)
    direction_keys = np.asarray(
        ["global-row-a", "global-row-b", "global-row-c", "global-row-d"],
        dtype="<U64",
    )
    one_apply_roles = {
        "source_before": _role(raw_dir, "source_before", source, descriptors),
        "source_after": _role(raw_dir, "source_after", source, descriptors),
        "residual_before": _role(
            raw_dir, "residual_before", residual, descriptors, direction_keys
        ),
        "residual_after": _role(
            raw_dir, "residual_after", residual, descriptors, direction_keys
        ),
        "residual": _role(raw_dir, "residual", residual, descriptors, direction_keys),
        "pc_output": _role(raw_dir, "pc_output", pc, descriptors),
        "pc_repeat": _role(raw_dir, "pc_repeat", pc, descriptors),
        "applied_output": _role(
            raw_dir, "applied_output", action, descriptors, direction_keys
        ),
        "true_residual": _role(
            raw_dir, "true_residual", zero, descriptors, direction_keys
        ),
    }
    coefficient_a, coefficient_b = K0_DIRECTION_COEFFICIENTS
    direction_mask = canonical_direction_mask(direction_keys)
    r1 = np.zeros_like(residual)
    r1[direction_mask] = residual[direction_mask]
    r2 = residual - r1
    combined = coefficient_a * r1 + coefficient_b * r2
    output_keys = np.asarray(
        ["output-a", "output-b", "output-c"], dtype="<U64"
    )
    p1 = np.asarray([1.0 + 0.25j, -0.5 + 1.0j, 2.0 - 0.75j])
    p2 = np.asarray([-1.0 + 0.5j, 0.25 - 0.25j, 0.75 + 1.25j])
    pcombined = coefficient_a * p1 + coefficient_b * p2
    linearity_roles = {
        "r1": _role(raw_dir, "linearity_r1", r1, descriptors, direction_keys),
        "r2": _role(raw_dir, "linearity_r2", r2, descriptors, direction_keys),
        "combined": _role(raw_dir, "linearity_combined", combined, descriptors, direction_keys),
        "p1": _role(raw_dir, "linearity_p1", p1, descriptors, output_keys),
        "p2": _role(raw_dir, "linearity_p2", p2, descriptors, output_keys),
        "pcombined": _role(raw_dir, "linearity_pcombined", pcombined, descriptors, output_keys),
        "pcombined_repeat": _role(
            raw_dir,
            "linearity_pcombined_repeat",
            pcombined,
            descriptors,
            output_keys,
        ),
    }

    iterations = 81 if late_only else 1
    first_pass = 81 if late_only else 1
    reason = -3 if late_only else 2
    history = []
    checkpoint_records: dict[str, dict[str, object]] = {}
    for iteration in range(iterations + 1):
        passes = iteration == first_pass
        history.append(
            {
                "iteration": iteration,
                "reported_unpreconditioned_relative": 0.0 if passes else 1.0,
                "explicit_true_residual": 0.0 if passes else 1.0,
                "matvec_count": iteration,
                "pc_apply_count": iteration,
                "monitor_action_count": iteration + 1,
                "elapsed_seconds": float(iteration),
            }
        )
    for checkpoint in K0_CHECKPOINTS:
        if checkpoint <= iterations:
            checkpoint_roles = {
                "solution": _role(
                    raw_dir,
                    f"checkpoint_{checkpoint}_solution",
                    0.5 * residual if checkpoint > 0 and not late_only else zero,
                    descriptors,
                ),
                "action": _role(
                    raw_dir,
                    f"checkpoint_{checkpoint}_action",
                    action if checkpoint > 0 and not late_only else zero,
                    descriptors,
                ),
                "true_residual": _role(
                    raw_dir,
                    f"checkpoint_{checkpoint}_true",
                    zero if checkpoint > 0 and not late_only else residual,
                    descriptors,
                ),
            }
            checkpoint_records[str(checkpoint)] = {
                "status": "measured",
                "artifacts": checkpoint_roles,
            }
        else:
            checkpoint_records[str(checkpoint)] = {
                "status": "not_run_after_convergence"
                if first_pass is not None and checkpoint > first_pass
                else "not_reached"
            }

    path = tmp_path / "record.json"
    record = {
        "schema": "task038.lor-native-complex-hx.k0-record.v1",
        "stage": "k0",
        "scope": "krylov_requalification",
        "case": "p2-mpi1",
        "degree": 2,
        "mpi_size": 1,
        "raw_dir": str(raw_dir),
        "command": [
            "/usr/bin/python3",
            "-m",
            "benchmarks.run_task038_full3d_lor_hx_krylov",
            "--case",
            "p2-mpi1",
            "--raw-dir",
            str(raw_dir.resolve()),
            "--record",
            str(path.resolve()),
            "--expected-source-sha",
            "a" * 40,
            "--expected-mpi-size",
            "1",
        ],
        "source": {
            "expected_sha": "a" * 40,
            "commit_sha_start": "a" * 40,
            "commit_sha_end": "a" * 40,
            "branch": "codex/20260820-task38-extra-full3d-iterative-0p7nm",
            "clean_start": True,
            "clean_end": True,
        },
        "runtime": {
            "qualified_activation": "1",
            "mpi_size": 1,
            "petsc_scalar_type": "complex128",
            "petsc_int_type": "int32",
        },
        "settings": K0_SETTINGS.as_dict(),
        "old_l2_reference": {
            "record_sha256": OLD_L2_RECORD_SHA,
            "rho": 1.7348663090876784,
            "limit": 0.45,
            "classification": "CONTROLLED_NEGATIVE_BY_POSITIVE_AUXILIARY_CONTRACTION_GATE",
        },
        "source_facts": {
            "name": "random",
            "formula": (
                "analytic deterministic pseudo-random edge field from fixed noninteger "
                "trigonometric frequencies and phases"
            ),
            "phase_application": "algebraic_slave_zero_action_internal_finalized_mpc_once",
        },
        "one_apply": {
            "artifacts": one_apply_roles,
            "input_role": "dual",
            "output_role": "primal",
            "rho": 0.0,
            "finite": True,
            "source_unchanged": True,
            "residual_input_unchanged": True,
            "repeat_relative": 0.0,
            "alpha": {
                "alpha_star": {"real": 1.0, "imag": 0.0},
                "rho_alpha": 0.0,
                "production_pc_alpha_applied": False,
            },
        },
        "linearity": {
            "construction": "deterministic SHA256 parity of canonical full-space row keys",
            "input_role": "dual",
            "input_semantics": "full_fe_dual_canonical_packets_reconstructed_with_T_H_no_new_phase",
            "output_role": "primal",
            "output_semantics": "full_fe_primal_canonical_packets",
            "input_key_set_sha256": canonical_key_set_sha256(direction_keys),
            "output_key_set_sha256": canonical_key_set_sha256(output_keys),
            "direction_mask": direction_mask.tolist(),
            "coefficient_a": {"real": float(coefficient_a.real), "imag": float(coefficient_a.imag)},
            "coefficient_b": {"real": float(coefficient_b.real), "imag": float(coefficient_b.imag)},
            "relative": 0.0,
            "repeat_relative": 0.0,
            "finite": True,
            "input_unchanged": True,
            "artifacts": linearity_roles,
        },
        "krylov": {
            "history": history,
            "checkpoints": checkpoint_records,
            "reason": reason,
            "iterations": iterations,
            "first_true_pass_iteration": first_pass,
            "late_true_pass_iteration": None if not late_only else 81,
            "qualification_pass": not late_only,
            "reported_final_residual": 0.0 if not late_only else 0.0,
            "matvec_count": iterations,
            "pc_apply_count": iterations,
            "monitor_action_count": iterations + 1,
        },
        "production": {"production_pc_alpha_applied": False},
        "forbidden": {
            "global_numeric_allgather": False,
            "high_order_global_aij": False,
            "global_dense_transfer": False,
            "global_direct_coarse": False,
        },
        "artifacts": descriptors,
    }
    path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
    return path


def test_k0_settings_alpha_and_linearity_are_frozen() -> None:
    assert K0_SETTINGS.as_dict() == {
        "ksp_type": "gmres",
        "pc_side": "right",
        "norm_type": "unpreconditioned",
        "restart": K0_GMRES_RESTART,
        "max_it": K0_GMRES_MAX_IT,
        "rtol": K0_GMRES_RTOL,
        "atol": 0.0,
        "initial_guess_nonzero": False,
    }
    residual = np.asarray([1.0 + 2.0j, -2.0 + 1.0j, 0.5 - 1.0j, 3.0 + 0.25j])
    applied = np.asarray([2.0 - 1.0j, 1.0 + 0.5j, -0.5 + 2.0j, 1.0 - 2.0j])
    alpha = alpha_diagnostic(residual, applied)
    expected = np.vdot(applied, residual) / np.vdot(applied, applied)
    assert abs(alpha["alpha_star"] - expected) <= 1.0e-13
    assert alpha["production_pc_alpha_applied"] is K0_ALPHA_PRODUCTION_APPLIED is False

    keys = np.asarray(
        ["global-row-a", "global-row-b", "global-row-c", "global-row-d"],
        dtype="<U64",
    )
    facts = two_direction_linearity(lambda values: 2.0 * values, residual, keys)
    assert facts["relative"] <= K0_LINEARITY_LIMIT
    assert facts["repeat_relative"] <= K0_REPEAT_LIMIT
    assert facts["input_unchanged"] is True


def test_k0_linearity_catches_nonlinear_mutating_and_nonrepeat_maps() -> None:
    residual = np.asarray([1.0 + 0.5j, 2.0 - 1.0j, -1.0 + 0.25j, 0.5 + 2.0j])
    keys = np.asarray(
        ["global-row-a", "global-row-b", "global-row-c", "global-row-d"],
        dtype="<U64",
    )
    nonlinear = two_direction_linearity(
        lambda values: values * np.abs(values), residual, keys
    )
    assert nonlinear["relative"] > K0_LINEARITY_LIMIT

    def mutating(values: np.ndarray) -> np.ndarray:
        values[:] *= 2.0
        return values

    mutated = two_direction_linearity(mutating, residual, keys)
    assert mutated["input_unchanged"] is False

    calls = {"count": 0}

    def nonrepeat(values: np.ndarray) -> np.ndarray:
        calls["count"] += 1
        return (1.0 + 0.1 * calls["count"]) * values

    repeated = two_direction_linearity(nonrepeat, residual, keys)
    assert repeated["repeat_relative"] > K0_REPEAT_LIMIT


def test_k0_canonical_key_mask_is_partition_and_order_independent() -> None:
    keys = np.asarray(
        ["global-row-0", "global-row-1", "global-row-2", "global-row-3", "global-row-4", "global-row-5"],
        dtype="<U64",
    )
    values = np.arange(keys.size, dtype=np.float64) + 1.0j
    first = two_direction_linearity(lambda vector: 2.0 * vector, values, keys)
    permutation = np.asarray([5, 1, 4, 0, 3, 2], dtype=np.int32)
    second = two_direction_linearity(
        lambda vector: 2.0 * vector, values[permutation], keys[permutation]
    )
    first_mask = dict(zip(keys.tolist(), first["direction_mask"], strict=True))
    second_mask = dict(
        zip(keys[permutation].tolist(), second["direction_mask"], strict=True)
    )
    assert first_mask == second_mask
    assert first["input_key_set_sha256"] == second["input_key_set_sha256"]


def test_k0_fake_petsc_gmres_tracks_explicit_monitor_and_checkpoint_solution() -> None:
    matrix = PETSc.Mat().createAIJ([4, 4], comm=PETSc.COMM_SELF)
    matrix.setUp()
    for index in range(4):
        matrix.setValue(index, index, 1.0 + 0.0j)
    matrix.assemble()

    class FakeFixture:
        comm = PETSc.COMM_SELF

        def __init__(self, base_matrix: PETSc.Mat) -> None:
            self.high_action = SimpleNamespace(matrix=base_matrix)

        @staticmethod
        def apply_high_action_copy(source: PETSc.Vec) -> PETSc.Vec:
            return source.copy()

        @staticmethod
        def apply_high_preconditioner(source: PETSc.Vec) -> PETSc.Vec:
            return source.copy()

    fixture = FakeFixture(matrix)
    rhs = matrix.createVecRight()
    rhs.array[:] = np.asarray(
        [1.0 + 0.5j, -2.0 + 0.25j, 0.5 - 1.0j, 3.0 + 0.75j],
        dtype=np.complex128,
    )
    result = run_k0_gmres(fixture, rhs)
    try:
        assert result["ksp"].getType() == "gmres"
        assert result["ksp"].getPCSide() == PETSc.PC.Side.RIGHT
        assert result["ksp"].getNormType() == PETSc.KSP.NormType.UNPRECONDITIONED
        assert result["ksp"].getInitialGuessNonzero() is False
        history = result["history"]
        assert [row["iteration"] for row in history] == list(
            range(result["iterations"] + 1)
        )
        assert result["monitor_action_count"] == len(history)
        assert result["operator_context"].matvec_count == result["ksp"].getIterationNumber()
        assert result["pc_context"].apply_count > 0
        assert history[-1]["matvec_count"] == result["operator_context"].matvec_count
        assert history[-1]["pc_apply_count"] <= result["pc_context"].apply_count
        assert history[-1]["monitor_action_count"] == result["monitor_action_count"]
        for row in history:
            assert row["monitor_action_count"] == row["iteration"] + 1
        measured = result["checkpoints"][1]
        assert np.array_equal(measured["solution"].array, rhs.array)
        expected_true = rhs.array - measured["action"].array
        assert np.allclose(measured["true_residual"].array, expected_true)
        assert result["qualification_pass"] is True
    finally:
        destroy_k0_gmres_result(result)
        rhs.destroy()
        matrix.destroy()


def test_k0_breakdown_marks_later_checkpoints_not_reached() -> None:
    statuses = _checkpoint_statuses(2, None, -3)
    assert statuses[0] == "measured"
    assert statuses[2] == "measured"
    assert statuses[5] == "not_reached"


def test_k0_source_after_snapshot_follows_actual_source_action() -> None:
    runner_source = Path(
        "benchmarks/run_task038_full3d_lor_hx_krylov.py"
    ).read_text(encoding="utf-8")
    action_position = runner_source.index(
        "residual = fixture.apply_high_action_copy(source_before)"
    )
    after_position = runner_source.index("source_after = source_before.copy()")
    assert action_position < after_position


def test_k0_checker_requires_command_identity(tmp_path: Path) -> None:
    record_path = _synthetic_record(tmp_path)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["command"][4] = "p3-mpi1"
    record_path.write_text(json.dumps(record), encoding="utf-8")
    result = check_record(record_path)
    assert result["passed"] is False
    assert any("command provenance" in item for item in result["contract_errors"])


def test_k0_checker_accepts_early_explicit_pass(tmp_path: Path) -> None:
    result = check_record(_synthetic_record(tmp_path))
    assert result["passed"] is True, result


def test_k0_checker_rejects_raw_mutation_settings_history_and_old_reclassification(
    tmp_path: Path,
) -> None:
    record_path = _synthetic_record(tmp_path)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["settings"]["pc_side"] = "left"
    record["old_l2_reference"]["rho"] = 0.1
    record["krylov"]["history"].pop(1)
    record_path.write_text(json.dumps(record), encoding="utf-8")
    result = check_record(record_path)
    assert result["passed"] is False
    assert result["contract_errors"]
    assert any("old L2 rho" in item for item in result["contract_errors"])
    assert any("history" in item for item in result["contract_errors"])

    raw_mutation_path = _synthetic_record(tmp_path / "raw_mutation")
    raw_record = json.loads(raw_mutation_path.read_text(encoding="utf-8"))
    output_name = raw_record["one_apply"]["artifacts"]["applied_output"]["values"]
    output_path = Path(raw_record["raw_dir"]) / f"{output_name}.npy"
    values = np.load(output_path, allow_pickle=False)
    values[0] += 1.0
    np.save(output_path, values, allow_pickle=False)
    result = check_record(raw_mutation_path)
    assert result["passed"] is False
    assert any("SHA256 mismatch" in item for item in result["contract_errors"])


def test_k0_checker_rejects_late_only_convergence(tmp_path: Path) -> None:
    result = check_record(_synthetic_record(tmp_path, late_only=True))
    assert result["passed"] is False
    assert any("after the 80-step" in item for item in result["gate_failures"])


def test_k0_checker_rejects_formula_mutation(tmp_path: Path) -> None:
    record_path = _synthetic_record(tmp_path)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["source_facts"]["formula"] = "changed"
    record_path.write_text(json.dumps(record), encoding="utf-8")
    result = check_record(record_path)
    assert result["passed"] is False
    assert any("formula" in item for item in result["contract_errors"])

    phase_record_path = _synthetic_record(tmp_path / "phase_mutation")
    phase_record = json.loads(phase_record_path.read_text(encoding="utf-8"))
    phase_record["source_facts"]["phase_application"] = "phase-twice"
    phase_record_path.write_text(json.dumps(phase_record), encoding="utf-8")
    phase_result = check_record(phase_record_path)
    assert phase_result["passed"] is False
    assert any("phase application" in item for item in phase_result["contract_errors"])
