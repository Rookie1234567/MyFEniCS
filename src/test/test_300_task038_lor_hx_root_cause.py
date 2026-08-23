"""Focused M0 diagnostic and independent-checker contracts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from petsc4py import PETSc

from benchmarks.task038_full3d_lor_hx_root_cause_checker import (
    M0_EXACT_LIMIT,
    M0_TRACE_NAMES,
    OLD_L2_CLASSIFICATION,
    OLD_L2_LIMIT,
    OLD_L2_RECORD_SHA,
    OLD_L2_RHO,
    _required_role_names,
    check_record,
    check_records,
)
from benchmarks.task038_full3d_lor_hx_krylov_checker import (
    ADDITIVE_AUTHORITY_CASE,
    ADDITIVE_AUTHORITY_SOURCE,
    K0_FIRST_PASS_MAX_IT,
    K0_TRUE_RESIDUAL_LIMIT,
    K1_VARIANT_ADDITIVE,
)
from src.solvers.fullspace_lor_hx_root_cause import (
    M0_OUTER_CHECKPOINTS,
    destroy_outer_right_gmres,
    replay_multiplicative_components,
    run_outer_right_gmres,
    solve_exact,
)


BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
SOURCE_SHA = "0123456789abcdef0123456789abcdef01234567"
FORMULA = (
    "analytic deterministic pseudo-random edge field from fixed "
    "noninteger trigonometric frequencies and phases"
)
PHASE = "algebraic_slave_zero_action_internal_finalized_mpc_once"


def _write_array(
    raw_dir: Path,
    name: str,
    array: np.ndarray,
    descriptors: list[dict[str, object]],
) -> None:
    path = raw_dir / f"{name}.npy"
    array = np.asarray(array)
    np.save(path, array, allow_pickle=False)
    descriptors.append(
        {
            "name": name,
            "relative_path": path.name,
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "dtype": str(array.dtype),
            "shape": list(array.shape),
        }
    )


def _synthetic_m0_record(tmp_path: Path, case: str = "p2-mpi1") -> Path:
    degree, mpi_size = (2, 1) if case == "p2-mpi1" else (2, 2)
    raw_dir = tmp_path / case
    raw_dir.mkdir()
    record_path = tmp_path / f"{case}.json"
    role_kinds, _ = _required_role_names()
    descriptors: list[dict[str, object]] = []
    roles: dict[str, dict[str, str]] = {}
    primal_keys = np.asarray(["primal:a", "primal:b", "primal:c"], dtype="<U256")
    dual_keys = np.asarray(["dual:a", "dual:b", "dual:c"], dtype="<U256")
    for index, role in enumerate(role_kinds):
        keys = primal_keys if role_kinds[role] == "primal" else dual_keys
        if role in {"production_output", "production_repeat"}:
            values = np.asarray([1.0 + 0.25j, -0.5 + 1.0j, 2.0 - 0.75j])
        elif role in {"high_source_before", "high_source_after"}:
            values = np.asarray([1.0 + 0.5j, -0.5 + 1.0j, 0.25 - 0.75j])
        elif role in {"high_residual", "high_residual_before", "high_residual_after"}:
            values = np.asarray([2.0 + 0.5j, -1.0 + 1.0j, 0.5 - 2.0j])
        else:
            values = np.asarray(
                [
                    1.0 + 0.1j * (index + 1),
                    -0.25 + 0.05j * index,
                    0.5 - 0.2j * (index + 1),
                ],
                dtype=np.complex128,
            )
        key_name = f"{role}_keys"
        value_name = f"{role}_values"
        _write_array(raw_dir, key_name, keys, descriptors)
        _write_array(raw_dir, value_name, values, descriptors)
        roles[role] = {"keys": key_name, "values": value_name}

    outer_checkpoints = (0, 1, 2, 5, 10, 20, 40, 60, 80, 100, 120, 140, 160, 180, 200)
    for prefix in ("production_outer", "exact_nodal_outer"):
        for suffix, kind in (
            ("final_solution", "primal"),
            ("final_action", "dual"),
            ("final_true_residual", "dual"),
        ):
            role = f"{prefix}_{suffix}"
            role_kinds[role] = kind
            keys = primal_keys if kind == "primal" else dual_keys
            values = np.asarray(
                [0.5 + 0.1j, -0.25 + 0.2j, 0.75 - 0.05j],
                dtype=np.complex128,
            )
            key_name = f"{role}_keys"
            value_name = f"{role}_values"
            _write_array(raw_dir, key_name, keys, descriptors)
            _write_array(raw_dir, value_name, values, descriptors)
            roles[role] = {"keys": key_name, "values": value_name}
    outer_labels = [
        f"{prefix}_{suffix}"
        for prefix in ("production_outer", "exact_nodal_outer")
        for suffix in ("final_solution", "final_action", "final_true_residual")
    ]

    trace_facts = []
    for name in M0_TRACE_NAMES:
        solver: dict[str, object] = {}
        if name not in ("edge_jacobi_pre", "edge_jacobi_post"):
            solver = {
                "backend": "petsc-preonly-lu-mumps",
                "ksp_type": "preonly",
                "pc_type": "lu",
                "factor_solver_type": "mumps",
                "reason": 1,
                "iterations": 1,
                "rhs_norm": 1.0,
                "solution_norm": 1.0,
                "residual_norm": 1.0e-14,
                "relative_residual": 1.0e-14,
                "finite": True,
                "history": [],
            }
        trace_facts.append({"name": name, "solver": solver})

    runtime = {
        "qualified_activation": "1",
        "mpi_size": mpi_size,
        "sys_executable": "/qualified/.venv/bin/python",
        "petsc_scalar_type": "complex128",
        "petsc_int_type": "int32",
    }
    rank_facts = [
        {"rank": rank, "runtime": runtime, "mode": "diagnostic"}
        for rank in range(mpi_size)
    ]
    hx_audit = {
        "variant": "sequential-v1",
        "global_transfer_matrix": False,
        "global_numeric_allgather": False,
        "global_direct_coarse": False,
        "edge_jacobi_correction_count": 2,
        "nodal_correction_count": 4,
        "hierarchy_object_count": 1,
        "one_shared_scalar_hierarchy": True,
        "original_residual_for_all_corrections": False,
    }
    record = {
        "schema": "task038.lor-native-complex-hx.m0-record.v1",
        "stage": "m0",
        "status": "facts_written_not_qualified",
        "case": case,
        "degree": degree,
        "mpi_size": mpi_size,
        "raw_dir": str(raw_dir),
        "record": str(record_path),
        "source": {
            "expected_sha": SOURCE_SHA,
            "commit_sha_start": SOURCE_SHA,
            "commit_sha_end": SOURCE_SHA,
            "branch": BRANCH,
            "clean_start": True,
            "clean_end": True,
        },
        "runtime": runtime,
        "rank_facts": rank_facts,
        "settings": {
            "variant": "sequential-v1",
            "source": "random",
            "direct_backend": "petsc-preonly-lu-mumps",
            "exact_nodal_direct": {
                "ksp_type": "preonly",
                "pc_type": "lu",
                "factor_solver_type": "mumps",
                "factor_reused_within_diagnostic_apply": True,
            },
            "outer_gmres": {
                "ksp_type": "gmres",
                "pc_side": "right",
                "norm_type": "unpreconditioned",
                "restart": 20,
                "cycle_max_it": 20,
                "max_cycles": 10,
                "max_it": 200,
                "rtol": 1.0e-8,
                "atol": 0.0,
                "zero_initial_guess": True,
                "residual_replacement": True,
            },
            "pair_gates": {
                "input": 1.0e-12,
                "exact_correction_action": 1.0e-10,
                "exact_component": 1.0e-10,
            },
        },
        "old_l2_reference": {
            "record_sha256": OLD_L2_RECORD_SHA,
            "rho": OLD_L2_RHO,
            "limit": OLD_L2_LIMIT,
            "classification": OLD_L2_CLASSIFICATION,
        },
        "production": {
            "variant": "sequential-v1",
            "production_pc_alpha_applied": False,
            "global_transfer_matrix": False,
            "global_numeric_allgather": False,
            "global_direct_coarse": False,
            "high_order_global_aij": False,
            "additive_v2": False,
            "ordinary_default_changed": False,
        },
        "fixture_audit": {
            "variant": "sequential-v1",
            "global_transfer_matrix": False,
            "global_numeric_allgather": False,
            "global_direct_coarse": False,
            "hx_audit_after_diagnostic": hx_audit,
        },
        "facts": {
            "source_formula": FORMULA,
            "source_phase_application": PHASE,
            "source_unchanged": True,
            "residual_input_unchanged": True,
            "finite": True,
            "direct_edge": {
                "backend": "petsc-preonly-lu-mumps",
                "reason": 1,
                "iterations": 1,
                "rhs_norm": 1.0,
                "solution_norm": 1.0,
                "residual_norm": 1.0e-14,
                "relative_residual": 1.0e-14,
                "finite": True,
            },
            "trace_count": 6,
            "nodal_correction_count": 4,
            "production_replay_relative": 1.0e-14,
            "exact_nodal_vs_production_relative": 0.25,
            "production_repeat_relative": 0.0,
            "production_trace": trace_facts,
            "exact_nodal_trace": trace_facts,
            "outer_artifact_labels": outer_labels,
            "outer_histories": {
                name: {
                    "label": name,
                    "settings": {
                        "ksp_type": "gmres",
                        "pc_side": "right",
                        "norm_type": "unpreconditioned",
                        "restart": 20,
                        "cycle_max_it": 20,
                        "max_cycles": 10,
                        "max_it": 200,
                        "rtol": 1.0e-8,
                        "atol": 0.0,
                        "zero_initial_guess": True,
                        "residual_replacement": True,
                    },
                    "history": [
                        {
                            "iteration": iteration,
                            "reported_residual": 1.0 / (iteration + 1),
                            "reported_relative": 1.0 / (iteration + 1),
                            "explicit_true_residual": (
                                1.0 / (iteration + 1)
                                if iteration in (0, 1, 2, 5, 10, 20, 40)
                                else None
                            ),
                            "matvec_count": iteration,
                            "solver_pc_apply_count": iteration,
                            "monitor_reconstruction_pc_applies": 0,
                            "monitor_action_count": sum(
                                int(value <= iteration)
                                for value in (0, 1, 2, 5, 10, 20, 40)
                            ),
                        }
                        for iteration in (0, 1, 2, 5, 10, 20, 40)
                    ],
                    "checkpoint_status": {
                        str(checkpoint): "measured" for checkpoint in outer_checkpoints
                    },
                    "reason": -3,
                    "cycles": [
                        {
                            "cycle_index": 0,
                            "start_iteration": 0,
                            "iterations": 20,
                            "cumulative_end_iteration": 20,
                            "reason": -3,
                            "initial_guess_nonzero": False,
                            "reported_final_relative": 0.05,
                            "explicit_true_residual": 0.05,
                            "solver_pc_apply_count": 20,
                            "monitor_reconstruction_pc_applies": 0,
                            "monitor_action_count": 6,
                        },
                        {
                            "cycle_index": 1,
                            "start_iteration": 20,
                            "iterations": 20,
                            "cumulative_end_iteration": 40,
                            "reason": -3,
                            "initial_guess_nonzero": True,
                            "reported_final_relative": 0.01,
                            "explicit_true_residual": 0.01,
                            "solver_pc_apply_count": 20,
                            "monitor_reconstruction_pc_applies": 0,
                            "monitor_action_count": 1,
                        },
                    ],
                    "cycle_count": 2,
                    "iterations": 40,
                    "matvec_count": 40,
                    "solver_pc_apply_count": 40,
                    "monitor_reconstruction_pc_applies": 0,
                    "monitor_action_count": 7,
                    "final_action_count": 1,
                    "total_pc_apply_count": 40,
                }
                for name in ("production", "exact_nodal")
            },
        },
        "canonical_role_kinds": role_kinds,
        "canonical_roles": roles,
        "artifacts": descriptors,
    }
    record_path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n")
    assert set(roles) == set(role_kinds)
    assert set(name for descriptor in descriptors for name in [descriptor["name"]]) == {
        f"{role}_{suffix}"
        for role in role_kinds
        for suffix in ("keys", "values")
    }
    return record_path


def test_m0_checker_accepts_pair_and_keeps_pcgamm_diagnostic(tmp_path: Path) -> None:
    left = _synthetic_m0_record(tmp_path, "p2-mpi1")
    right = _synthetic_m0_record(tmp_path, "p2-mpi2")
    individual = check_record(left)
    pair = check_records([left, right])
    assert individual["passed"] is True
    assert pair["passed"] is True
    assert pair["contract_errors"] == []
    assert pair["gate_failures"] == []
    assert individual["diagnostics"]["production_pcgamg_vs_exact_nodal"] == 0.25


def test_m0_checker_rejects_missing_or_mutated_component(tmp_path: Path) -> None:
    record_path = _synthetic_m0_record(tmp_path)
    record = json.loads(record_path.read_text())
    raw_dir = Path(record["raw_dir"])
    missing = raw_dir / "exact_nodal_gradient_rhs_values.npy"
    missing.unlink()
    checked = check_record(record_path)
    assert checked["passed"] is False
    assert any("missing" in error or "SHA256" in error for error in checked["contract_errors"])


def test_m0_pair_catches_component_value_mismatch(tmp_path: Path) -> None:
    left = _synthetic_m0_record(tmp_path, "p2-mpi1")
    right = _synthetic_m0_record(tmp_path, "p2-mpi2")
    record = json.loads(right.read_text())
    descriptor = next(
        item
        for item in record["artifacts"]
        if item["name"] == "exact_nodal_gradient_edge_action_values"
    )
    path = Path(record["raw_dir"]) / descriptor["relative_path"]
    values = np.load(path, allow_pickle=False)
    values = np.asarray(values).copy()
    values[0] += 0.25
    np.save(path, values, allow_pickle=False)
    descriptor["bytes"] = path.stat().st_size
    descriptor["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    right.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n")
    assert check_record(right)["passed"] is True
    checked = check_records([left, right])
    assert checked["passed"] is False
    assert any("exact_nodal_gradient_edge_action" in error for error in checked["gate_failures"])


def test_m0_pair_reports_production_difference_without_gating(tmp_path: Path) -> None:
    left = _synthetic_m0_record(tmp_path, "p2-mpi1")
    right = _synthetic_m0_record(tmp_path, "p2-mpi2")
    record = json.loads(right.read_text())
    descriptor = next(
        item
        for item in record["artifacts"]
        if item["name"] == "production_gradient_rhs_values"
    )
    path = Path(record["raw_dir"]) / descriptor["relative_path"]
    values = np.asarray(np.load(path, allow_pickle=False)).copy()
    values[0] += 0.5
    np.save(path, values, allow_pickle=False)
    descriptor["bytes"] = path.stat().st_size
    descriptor["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    right.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n")
    assert check_record(right)["passed"] is True
    checked = check_records([left, right])
    assert checked["passed"] is True
    assert checked["gate_failures"] == []
    diagnostic = checked["production_pair_diagnostic"]
    assert diagnostic["diagnostic_only"] is True
    assert diagnostic["first_divergent_component"] == "gradient.rhs"
    assert diagnostic["metrics"]["gradient.rhs"]["relative"] > 1.0e-10


def test_m0_pair_requires_one_source_sha(tmp_path: Path) -> None:
    left = _synthetic_m0_record(tmp_path, "p2-mpi1")
    right = _synthetic_m0_record(tmp_path, "p2-mpi2")
    record = json.loads(right.read_text())
    alternate = "fedcba9876543210fedcba9876543210fedcba98"
    record["source"]["expected_sha"] = alternate
    record["source"]["commit_sha_start"] = alternate
    record["source"]["commit_sha_end"] = alternate
    right.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n")
    assert check_record(right)["passed"] is True
    checked = check_records([left, right])
    assert checked["passed"] is False
    assert any("exact source SHA" in error for error in checked["contract_errors"])


def test_m0_checker_rejects_changed_immutable_l2_authority(tmp_path: Path) -> None:
    record_path = _synthetic_m0_record(tmp_path)
    record = json.loads(record_path.read_text())
    record["old_l2_reference"]["rho"] = 0.45
    record_path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n")
    checked = check_record(record_path)
    assert checked["passed"] is False
    assert any("old L2" in error for error in checked["contract_errors"])


def test_m0_preserves_closed_v1_v2_authorities() -> None:
    assert OLD_L2_RHO == 1.7348663090876784
    assert OLD_L2_LIMIT == 0.45
    assert K0_FIRST_PASS_MAX_IT == 80
    assert K0_TRUE_RESIDUAL_LIMIT == 1.0e-8
    assert M0_EXACT_LIMIT == 1.0e-10
    assert K1_VARIANT_ADDITIVE == "additive-v2"
    assert ADDITIVE_AUTHORITY_CASE == "p2-mpi1"
    assert ADDITIVE_AUTHORITY_SOURCE == "random"


def _aij(block: np.ndarray) -> PETSc.Mat:
    block = np.asarray(block, dtype=np.complex128)
    matrix = PETSc.Mat().createAIJ(block.shape, nnz=max(1, int(np.count_nonzero(block, axis=1).max())))
    matrix.setUp()
    start, stop = matrix.getOwnershipRange()
    assert (start, stop) == (0, block.shape[0])
    for row in range(block.shape[0]):
        for col in np.flatnonzero(np.abs(block[row]) > 0.0):
            matrix.setValue(row, int(col), complex(block[row, col]))
    matrix.assemble()
    return matrix


class _FakeHX:
    def __init__(self, edge_count: int, node_count: int) -> None:
        self._edge_diagonal_inverse = np.ones(edge_count, dtype=np.float64)
        self._gradient = _aij(np.ones((edge_count, node_count), dtype=np.complex128))
        self._gradient_adjoint = self._gradient.hermitianTranspose()
        self._vector_prolongations = tuple(
            _aij(np.eye(edge_count, node_count, dtype=np.complex128))
            for _ in range(3)
        )
        self._vector_restrictions = tuple(
            matrix.hermitianTranspose() for matrix in self._vector_prolongations
        )
        self._nodal_ksp = None

    def destroy(self) -> None:
        self._gradient.destroy()
        self._gradient_adjoint.destroy()
        for matrix in (*self._vector_prolongations, *self._vector_restrictions):
            matrix.destroy()


class _FakeFixture:
    def __init__(self) -> None:
        self.edge_matrix = _aij(np.diag([2.0, 3.0]).astype(np.complex128))
        self.node_matrix = _aij(np.eye(2, dtype=np.complex128))
        self.hx = _FakeHX(2, 2)

    def destroy(self) -> None:
        self.edge_matrix.destroy()
        self.node_matrix.destroy()
        self.hx.destroy()


def test_m0_replay_sequence_preserves_input_and_has_six_components() -> None:
    fixture = _FakeFixture()
    residual = fixture.edge_matrix.createVecRight()
    residual.array[:] = np.asarray([1.0 + 2.0j, -0.5 + 0.25j])
    before = residual.array.copy()

    def nodal_solve(rhs: PETSc.Vec) -> tuple[PETSc.Vec, dict[str, object]]:
        return rhs.copy(), {"backend": "fake-exact", "relative_residual": 0.0, "finite": True}

    replay = replay_multiplicative_components(fixture, residual, nodal_solve)
    assert len(replay["traces"]) == 6
    assert np.array_equal(residual.array, before)
    assert np.all(np.isfinite(replay["result"].array))
    replay["result"].destroy()
    replay["remaining"].destroy()
    for trace in replay["traces"]:
        for value in trace.values():
            if hasattr(value, "destroy"):
                value.destroy()
    residual.destroy()
    fixture.destroy()


def test_m0_exact_edge_helper_has_finite_small_residual() -> None:
    matrix = _aij(np.asarray([[2.0 + 0.0j, 0.25], [0.25, 3.0]], dtype=np.complex128))
    rhs = matrix.createVecRight()
    rhs.array[:] = np.asarray([1.0 + 0.5j, -0.25 + 0.75j])
    solution, facts = solve_exact(matrix, rhs, label="test")
    assert facts["backend"] == "petsc-preonly-lu-mumps"
    assert facts["finite"] is True
    assert facts["relative_residual"] <= 1.0e-10
    solution.destroy()
    rhs.destroy()
    matrix.destroy()


def test_m0_outer_histories_use_fixed_right_gmres_and_explicit_actions() -> None:
    matrix = _aij(np.diag(np.logspace(0.0, 2.0, 35)).astype(np.complex128))
    rhs = matrix.createVecRight()
    rhs.array[:] = np.asarray(
        [1.0 + 0.1j * index for index in range(35)], dtype=np.complex128
    )

    def action(vector: PETSc.Vec) -> PETSc.Vec:
        result = matrix.createVecLeft()
        matrix.mult(vector, result)
        return result

    def preconditioner(vector: PETSc.Vec) -> PETSc.Vec:
        return vector.copy()

    result = run_outer_right_gmres(
        rhs, action, preconditioner, label="synthetic-m0"
    )
    try:
        assert result["settings"] == {
            "ksp_type": "gmres",
            "pc_side": "right",
            "norm_type": "unpreconditioned",
            "restart": 20,
            "cycle_max_it": 20,
            "max_cycles": 10,
            "max_it": 200,
            "rtol": 1.0e-8,
            "atol": 0.0,
            "zero_initial_guess": True,
            "residual_replacement": True,
        }
        assert result["history"]
        assert len(result["cycles"]) >= 2
        assert result["cycles"][1]["start_iteration"] == 20
        assert result["cycles"][1]["initial_guess_nonzero"] is True
        assert set(result["checkpoint_status"]) == {
            str(value) for value in M0_OUTER_CHECKPOINTS
        }
        assert result["monitor_reconstruction_pc_applies"] >= 0
        assert result["total_pc_apply_count"] == (
            result["solver_pc_apply_count"]
            + result["monitor_reconstruction_pc_applies"]
        )
        assert result["final_action_count"] == 1
        assert any(row["explicit_true_residual"] is None for row in result["history"])
        assert not isinstance(result.get("checkpoints"), dict)
        assert result["cycles"][-1]["explicit_true_residual"] <= 1.0e-8
        assert result["cycles"][-1]["reported_final_relative"] <= 1.0e-8
        assert result["matvec_count"] >= 0
        assert result["solver_pc_apply_count"] >= 0
        assert np.all(np.isfinite(result["final_solution"].array))
    finally:
        destroy_outer_right_gmres(result)
        rhs.destroy()
        matrix.destroy()
