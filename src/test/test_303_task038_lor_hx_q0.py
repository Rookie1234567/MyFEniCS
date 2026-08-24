"""Focused pure/PETSc contracts for the Review V10 Q0 lane."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from petsc4py import PETSc

from benchmarks import run_task038_full3d_lor_hx_q0 as q0_worker
from benchmarks.task038_full3d_lor_hx_q0_checker import (
    ALL_ROLES,
    CONSTRAINT_ROLES,
    HIGH_ROLES,
    LOW_ROLES,
    TRACE_NAMES,
    check_record,
)
from src.solvers.fullspace_memory_first_krylov import (
    destroy_krylov_result,
    run_restart20_cycles,
)
from src.solvers.fullspace_lor_hx_root_cause import (
    DiagnosticDirectSolver,
    replay_multiplicative_components,
)


SOURCE_SHA = "0" * 40
IDENTITY_SHA = "1" * 64


def test_q0_high_payload_canonicalizes_before_gather(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, object]] = []
    vectors = {"source": (object(), "primal")}
    canonical = {"source": [("canonical-key", 1.0 + 0.0j)]}

    def fake_canonical(fixture: object, value: object) -> dict[str, object]:
        calls.append(("canonical", (fixture, value)))
        return canonical

    def fake_gather(comm: object, payload: dict[str, object]) -> dict[str, object]:
        calls.append(("gather", payload))
        return payload

    monkeypatch.setattr(q0_worker, "_l2_canonical_payload", fake_canonical)
    monkeypatch.setattr(q0_worker, "_l2_gather_payload", fake_gather)

    result = q0_worker._gather_high_payload("comm", "fixture", vectors)

    assert result is canonical
    assert [name for name, _value in calls] == ["canonical", "gather"]
    assert calls[1][1] is canonical


def _identity_matrix(size: int = 1) -> PETSc.Mat:
    indptr = np.arange(size + 1, dtype=np.int32)
    indices = np.arange(size, dtype=np.int32)
    values = np.ones(size, dtype=np.complex128)
    matrix = PETSc.Mat().createAIJ(
        [size, size], csr=(indptr, indices, values), comm=PETSc.COMM_SELF
    )
    matrix.assemble()
    return matrix


def _destroy_replay(result: dict[str, object]) -> None:
    for key in ("result", "remaining"):
        value = result.get(key)
        if value is not None:
            value.destroy()
    for trace in result.get("traces", []):
        for value in trace.values():
            if hasattr(value, "destroy"):
                value.destroy()


def test_q0_exact_edge_solver_uses_each_current_rhs() -> None:
    matrix = _identity_matrix(2)
    solver = DiagnosticDirectSolver(matrix, label="q0-test")
    first = matrix.createVecRight()
    second = matrix.createVecRight()
    first.array[:] = (1.0 + 0.0j, 0.0 + 0.0j)
    second.array[:] = (0.0 + 0.0j, 2.0 + 0.0j)
    out_first, facts_first = solver.solve(first)
    out_second, facts_second = solver.solve_lean(second)
    assert np.allclose(out_first.array, first.array)
    assert np.allclose(out_second.array, second.array)
    assert solver.solve_count == 2
    assert facts_first["relative_residual"] <= 1.0e-12
    assert facts_second["finite"]
    out_first.destroy()
    out_second.destroy()
    first.destroy()
    second.destroy()
    solver.destroy()
    matrix.destroy()


def test_q0_nodal_replay_has_four_direct_components_and_frozen_order() -> None:
    edge = _identity_matrix(2)
    node = _identity_matrix(2)
    fixture = SimpleNamespace(
        edge_matrix=edge,
        node_matrix=node,
        hx=SimpleNamespace(
            _edge_diagonal_inverse=np.ones(2, dtype=np.float64),
            _gradient_adjoint=edge,
            _gradient=edge,
            _vector_restrictions=(edge, edge, edge),
            _vector_prolongations=(edge, edge, edge),
        ),
    )
    residual = edge.createVecRight()
    residual.array[:] = (1.0 + 0.0j, 2.0 + 0.0j)

    class Solver:
        calls = 0

        def __call__(self, rhs):
            self.calls += 1
            return rhs.copy(), {"relative_residual": 0.0, "name": self.calls}

    solver = Solver()
    replay = replay_multiplicative_components(
        fixture, residual, solver, capture_traces=True
    )
    assert solver.calls == 4
    assert [trace["name"] for trace in replay["traces"]] == list(TRACE_NAMES)
    assert sum(trace["rhs"] is not None for trace in replay["traces"]) == 4
    _destroy_replay(replay)
    residual.destroy()
    edge.destroy()
    node.destroy()


def test_q0_outer_contract_is_restart20_max500_with_true_boundary() -> None:
    matrix = _identity_matrix(2)
    rhs = matrix.createVecRight()
    rhs.array[:] = (1.0 + 0.0j, -2.0 + 0.0j)

    def copy_action(vector):
        return vector.copy()

    result = run_restart20_cycles(
        rhs,
        copy_action,
        copy_action,
        max_it=500,
        residual_limit=1.0e-8,
        resource_sample=lambda: {
            "process_tree": {"all_status_readable": True, "swap_bytes": 0}
        },
        start_iteration=0,
        first_checkpoint_iteration=None,
        checkpoint_interval=500,
    )
    assert result["settings"]["restart"] == 20
    assert result["settings"]["max_it"] == 500
    assert result["settings"]["residual_replacement"] is True
    assert result["iterations"] <= 20
    assert result["explicit_action_count"] == 1 + len(result["cycles"])
    assert result["cycles"][-1]["explicit_true_residual"] <= 1.0e-8
    destroy_krylov_result(result)
    rhs.destroy()
    matrix.destroy()


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        + b"\n"
    )


def _write_array(raw: Path, name: str, values: np.ndarray) -> dict[str, object]:
    path = raw / f"{name}.npy"
    np.save(path, np.asarray(values), allow_pickle=False)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "relative_path": path.name,
        "bytes": path.stat().st_size,
        "sha256": digest,
        "dtype": str(np.asarray(values).dtype),
        "shape": list(np.asarray(values).shape),
    }


def _role_descriptor(
    raw: Path, role: str, kind: str, keys: np.ndarray, values: np.ndarray
) -> dict[str, object]:
    return {
        "role": kind,
        "keys": _write_array(raw, f"{role}_keys", keys),
        "values": _write_array(raw, f"{role}_values", values),
    }


def _matrix_descriptor(raw: Path, name: str, row_key: str) -> dict[str, object]:
    return {
        "rows": 1,
        "cols": 1,
        "type": "aij",
        "nnz": 1,
        "numeric_bytes": np.asarray([1.0 + 0.0j], dtype=np.complex128).nbytes,
        "index_bytes": np.asarray([0, 1], dtype=np.int32).nbytes
        + np.asarray([0], dtype=np.int32).nbytes,
        "indptr": _write_array(raw, f"{name}_indptr", np.asarray([0, 1], dtype=np.int32)),
        "indices": _write_array(raw, f"{name}_indices", np.asarray([0], dtype=np.int32)),
        "values": _write_array(raw, f"{name}_values", np.asarray([1.0 + 0.0j], dtype=np.complex128)),
        "row_keys": _write_array(raw, f"{name}_row_keys", np.asarray([row_key], dtype="<U32")),
    }


def _resource_fact() -> dict[str, object]:
    return {
        "process_tree": {"all_status_readable": True, "swap_bytes": 0}
    }


def _outer_fact() -> dict[str, object]:
    cycle = {
        "cycle_index": 0,
        "start_iteration": 0,
        "end_iteration": 20,
        "iterations": 20,
        "reason": -3,
        "initial_guess_nonzero": False,
        "reported_final_residual": 0.0,
        "explicit_true_residual": 0.0,
        "matvec_count": 1,
        "pc_apply_count": 1,
        "wall_seconds": 0.0,
        "resource": _resource_fact(),
        "ksp_destroyed": True,
    }
    return {
        "settings": {"restart": 20, "max_it": 500},
        "initial_true_residual": 1.0,
        "cycles": [cycle],
        "iterations": 20,
        "reason": -3,
        "final_true_residual": 0.0,
        "matvec_count": 1,
        "pc_apply_count": 1,
        "explicit_action_count": 2,
        "ksp_destroy_count": 1,
        "elapsed_seconds": 0.0,
    }


def _synthetic_record(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    raw = tmp_path / "raw"
    raw.mkdir(parents=True)
    record_path = tmp_path / "record.json"
    keys_high = np.asarray(["high-key"], dtype="<U32")
    keys_edge = np.asarray(["lor-edge:0"], dtype="<U32")
    keys_node = np.asarray(["node:0"], dtype="<U32")
    keys_node_global = np.asarray(["node-global:0"], dtype="<U32")
    keys_constraint = np.asarray(["high-slave:0"], dtype="<U32")
    one = np.asarray([1.0 + 0.0j], dtype=np.complex128)
    zero = np.asarray([0.0 + 0.0j], dtype=np.complex128)
    artifacts: dict[str, dict[str, object]] = {}
    primal_high = {"source_before", "source_after", "e_output", "e_repeat", "e_final_solution", "n_output", "n_repeat", "n_final_solution"}
    for role in sorted(HIGH_ROLES):
        values = zero if role.endswith("true_residual") else one
        artifacts[role] = _role_descriptor(
            raw, role, "primal" if role in primal_high else "dual", keys_high, values
        )
    for role in sorted(LOW_ROLES):
        if role in {"e_low_input", "e_low_solution", "n_low_input", "e_low_input_matrix", "e_low_solution_matrix"}:
            keys = keys_edge
        elif role.endswith("rhs_matrix") or role.endswith("nodal_delta_matrix"):
            keys = keys_node_global
        elif role.endswith("rhs") or role.endswith("nodal_delta"):
            keys = keys_node
        else:
            keys = keys_edge
        if role == "n_low_input":
            values = np.asarray([2.0 + 0.0j], dtype=np.complex128)
        elif role == "n_edge_jacobi_pre_edge_delta":
            values = np.asarray([0.25 + 0.0j], dtype=np.complex128)
        elif role == "n_edge_jacobi_pre_result":
            values = np.asarray([0.25 + 0.0j], dtype=np.complex128)
        elif role == "n_edge_jacobi_pre_edge_action":
            values = np.asarray([0.5 + 0.0j], dtype=np.complex128)
        elif role == "n_edge_jacobi_pre_remaining":
            values = np.asarray([1.5 + 0.0j], dtype=np.complex128)
        elif role.endswith("result"):
            values = np.asarray([0.25 + 0.0j], dtype=np.complex128)
        elif role.endswith("remaining"):
            values = np.asarray([1.5 + 0.0j], dtype=np.complex128)
        else:
            values = one if role in {"e_low_input", "e_low_solution", "e_low_input_matrix", "e_low_solution_matrix"} else zero
        artifacts[role] = _role_descriptor(raw, role, "node" if "rhs" in role or "nodal_delta" in role else ("dual" if "input" in role or "remaining" in role or "action" in role else "primal"), keys, values)
    for role in sorted(CONSTRAINT_ROLES):
        artifacts[role] = _role_descriptor(raw, role, "constraint", keys_constraint, zero)
    component_hashes = {
        role: hashlib.sha256(
            _json_bytes({"keys_sha256": desc["keys"]["sha256"], "values_sha256": desc["values"]["sha256"]})
        ).hexdigest()
        for role, desc in artifacts.items()
    }
    direct_facts = [
        {"name": name, "relative_residual": 0.0, "finite": True}
        for name in ("gradient", "pi_x", "pi_y", "pi_z")
    ]
    rank_fact = {
        "rank": 0,
        "runtime": {
            "qualified_activation": "1",
            "mpi_size": 1,
            "petsc_scalar_type": "complex128",
            "petsc_int_type": "int32",
        },
        "e_repeat_relative": 0.0,
        "n_repeat_relative": 0.0,
        "e_input_unchanged_relative": 0.0,
        "n_input_unchanged_relative": 0.0,
        "edge_direct_solve_count": 3,
        "nodal_direct_solve_count": 12,
    }
    audit = {
        "variant": "sequential-v1",
        "degree": 3,
        "high_order_matrix_free": True,
        "high_order_global_aij": False,
        "global_transfer_matrix": False,
        "global_numeric_allgather": False,
        "phase_application": "finalized_floquet_mpc_once",
        "slave_master_complete": True,
        "raw_edge_orientation_factor_count": 1,
        "raw_edge_orientation_consistent": True,
        "raw_edge_orientation_owned_rows_closed": True,
        "hx_audit": {
            "variant": "sequential-v1",
            "composition": "sequential",
            "original_residual_for_all_corrections": False,
            "edge_jacobi_correction_count": 2,
            "gradient_correction_count": 1,
            "vector_correction_order": "x_then_y_then_z",
            "nodal_correction_count": 4,
            "one_v_cycle_per_nodal_correction": True,
            "one_shared_scalar_hierarchy": True,
            "hierarchy_object_count": 1,
            "global_transfer_matrix": False,
            "global_numeric_allgather": False,
            "global_direct_coarse": False,
            "high_order_aij": False,
            "real_imag_split": False,
            "hypre_ams": False,
        },
    }
    record = {
        "schema": "task038.lor-native-complex-hx.q0-record.v1",
        "stage": "q0",
        "scope": "v10_exact_reference_triage",
        "case": "p3-mpi1",
        "degree": 3,
        "h_nm": 50.0,
        "source_name": "random",
        "variant": "sequential-v1",
        "mpi_size": 1,
        "raw_dir": str(raw.resolve()),
        "record_path": str(record_path.resolve()),
        "command": [
            "/opt/.venv/bin/python",
            "-m",
            "benchmarks.run_task038_full3d_lor_hx_q0",
            "--stage",
            "q0",
            "--case",
            "p3-mpi1",
            "--raw-dir",
            str(raw.resolve()),
            "--record",
            str(record_path.resolve()),
            "--expected-source-sha",
            SOURCE_SHA,
            "--expected-mpi-size",
            "1",
        ],
        "source": {
            "expected_sha": SOURCE_SHA,
            "commit_sha_start": SOURCE_SHA,
            "commit_sha_end": SOURCE_SHA,
            "branch": "codex/20260820-task38-extra-full3d-iterative-0p7nm",
            "tracked_status_start": "",
            "tracked_status_end": "",
            "clean_start": True,
            "clean_end": True,
        },
        "runtime": {
            "qualified_activation": "1",
            "mpi_size": 1,
            "petsc_scalar_type": "complex128",
            "petsc_int_type": "int32",
        },
        "source_facts": {
            "name": "random",
            "formula": "analytic deterministic pseudo-random edge field from fixed noninteger trigonometric frequencies and phases",
            "phase_application": "algebraic_slave_zero_action_internal_finalized_mpc_once",
        },
        "provenance": {
            "input_identity_sha256": IDENTITY_SHA,
            "operator_identity_sha256": IDENTITY_SHA,
            "physical_model_sha256": IDENTITY_SHA,
        },
        "settings": {
            "reference_outer": {
                "ksp_type": "gmres",
                "pc_side": "right",
                "norm_type": "unpreconditioned",
                "restart": 20,
                "max_it": 500,
                "residual_replacement": True,
                "zero_initial_guess": True,
                "residual_limit": 1.0e-8,
            },
            "edge_direct": {"ksp_type": "preonly", "pc_type": "lu", "factor_solver_type": "mumps", "factor_reused_per_reference": True},
            "nodal_direct": {"ksp_type": "preonly", "pc_type": "lu", "factor_solver_type": "mumps", "factor_reused_for_four_components": True},
            "exact_edge_limit": 1.0e-12,
            "exact_nodal_limit": 1.0e-12,
            "input_limit": 1.0e-12,
            "repeat_limit": 1.0e-13,
        },
        "fixture_audit": audit,
        "route_audit": {"high_to_lor_owner_route": True, "lor_to_high_owner_route": True, "owner_inventory_equal": True, "owner_count": 1, "orientation_consistent": True, "phase_application": "finalized_floquet_mpc_once", "slave_master_complete": True, "canonical_component_hashes": component_hashes},
        "matrix_artifacts": {"edge": _matrix_descriptor(raw, "edge_matrix", "lor-edge:0"), "node": _matrix_descriptor(raw, "node_matrix", "node-global:0")},
        "component_hashes": component_hashes,
        "canonical_artifacts": artifacts,
        "rank_facts": [rank_fact],
        "reference_e": {"outer": _outer_fact(), "direct_edge": {"relative_residual": 0.0}, "input_unchanged_relative": 0.0, "repeat_relative": 0.0, "finite": True, "primal_constraint_absolute": 0.0, "direct_solve_count": 3, "direct_residual_limit": 1.0e-12, "final_residual_limit": 1.0e-8},
        "reference_n": {"outer": _outer_fact(), "nodal_direct": direct_facts, "input_unchanged_relative": 0.0, "repeat_relative": 0.0, "finite": True, "primal_constraint_absolute": 0.0, "direct_solve_count": 12, "direct_residual_limit": 1.0e-12, "final_residual_limit": 1.0e-8, "component_trace_names": list(TRACE_NAMES)},
        "primal_constraint_rows": [0],
        "high_rhs_repeat_relative": 0.0,
        "source_unchanged_relative": 0.0,
        "production": {"variant": "sequential-v1", "production_pc_direct_factor_applied": False, "global_transfer_matrix": False, "global_numeric_allgather": False, "global_direct_coarse": False, "high_order_global_aij": False, "ordinary_default_changed": False},
    }
    record_path.write_bytes(_json_bytes(record))
    return record_path, record


def _rewrite_role(record_path: Path, record: dict[str, object], role: str, values: np.ndarray) -> None:
    raw = Path(record["raw_dir"])
    descriptor = record["canonical_artifacts"][role]
    path = raw / descriptor["values"]["relative_path"]
    np.save(path, np.asarray(values, dtype=np.complex128), allow_pickle=False)
    descriptor["values"]["bytes"] = path.stat().st_size
    descriptor["values"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    descriptor["values"]["dtype"] = "complex128"
    record["component_hashes"][role] = hashlib.sha256(_json_bytes({"keys_sha256": descriptor["keys"]["sha256"], "values_sha256": descriptor["values"]["sha256"]})).hexdigest()
    record_path.write_bytes(_json_bytes(record))


def test_q0_checker_accepts_synthetic_record_and_rejects_missing_artifact(tmp_path: Path) -> None:
    record_path, record = _synthetic_record(tmp_path)
    result = check_record(record_path, SOURCE_SHA)
    assert result["passed"], result
    pre_delta = Path(record["raw_dir"]) / record["canonical_artifacts"]["n_edge_jacobi_pre_edge_delta"]["values"]["relative_path"]
    pre_remaining = Path(record["raw_dir"]) / record["canonical_artifacts"]["n_edge_jacobi_pre_remaining"]["values"]["relative_path"]
    assert np.linalg.norm(np.load(pre_delta, allow_pickle=False)) > 0.0
    assert np.linalg.norm(np.load(pre_remaining, allow_pickle=False)) > 0.0
    missing = Path(record["raw_dir"]) / record["canonical_artifacts"]["e_output"]["values"]["relative_path"]
    missing.unlink()
    result = check_record(record_path, SOURCE_SHA)
    assert not result["passed"]
    assert result["contract_errors"]


def test_q0_checker_distinguishes_e_gate_from_n_final_diagnostic(tmp_path: Path) -> None:
    record_path, record = _synthetic_record(tmp_path / "e")
    _rewrite_role(record_path, record, "e_final_action", np.asarray([0.5 + 0.0j]))
    _rewrite_role(record_path, record, "e_final_true_residual", np.asarray([0.5 + 0.0j]))
    record["reference_e"]["outer"]["final_true_residual"] = 0.5
    record["reference_e"]["outer"]["cycles"][0]["explicit_true_residual"] = 0.5
    record_path.write_bytes(_json_bytes(record))
    result = check_record(record_path, SOURCE_SHA)
    assert not result["passed"]
    assert any("E final true residual rho" in error for error in result["gate_failures"])

    record_path, record = _synthetic_record(tmp_path / "n")
    _rewrite_role(record_path, record, "n_final_action", np.asarray([0.5 + 0.0j]))
    _rewrite_role(record_path, record, "n_final_true_residual", np.asarray([0.5 + 0.0j]))
    record["reference_n"]["outer"]["final_true_residual"] = 0.5
    record["reference_n"]["outer"]["cycles"][0]["explicit_true_residual"] = 0.5
    record_path.write_bytes(_json_bytes(record))
    result = check_record(record_path, SOURCE_SHA)
    assert result["passed"], result
    assert any("N final true residual diagnostic" in item for item in result["diagnostics"])


def test_q0_checker_raw_input_mutation_is_a_gate(tmp_path: Path) -> None:
    record_path, record = _synthetic_record(tmp_path)
    _rewrite_role(record_path, record, "e_input_after", np.asarray([2.0 + 0.0j]))
    result = check_record(record_path, SOURCE_SHA)
    assert not result["passed"]
    assert any("E input unchanged" in error for error in result["gate_failures"])
