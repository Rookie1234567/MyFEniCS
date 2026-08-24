"""Thin E-only final LOR-foundation worker and process-tree watchdog.

The worker is intentionally limited to the frozen p3/h50 MPI1 random case.
It reuses the production positive fixture, the Q0 exact LOR edge route, and
the generic restart-20 residual-authority lifecycle.  The watchdog is a
separate mode in this file so it can sample the complete worker process tree
without creating the worker-owned raw directory.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

import numpy as np
from mpi4py import MPI

from benchmarks.run_task038_full3d_lor_hx import (
    _append_stage_marker,
    _l2_canonical_payload,
    _l2_gather_payload,
    _prepare_paths,
    _runtime_identity,
    _source_identity,
)
from benchmarks.run_task038_full3d_lor_hx_krylov import _closeout_record
from benchmarks.task034_wsl_resources import resource_authority_sample
from benchmarks.watchdog_process_control import (
    terminate_process_tree,
    worker_process_group_popen_kwargs,
)
from src.solvers.fullspace_memory_first_krylov import (
    destroy_krylov_result,
    run_restart20_cycles,
    write_solution_checkpoint,
)
from src.solvers.fullspace_lor_hx_root_cause import (
    DiagnosticDirectSolver,
    lift_low_primal,
    low_input_from_high_dual,
)
from src.solvers.fullspace_lor_native_hx_fixture import RealL2PositiveHXFixture


SCHEMA = "task038.lor-native-complex-hx.foundation-e-record.v1"
WATCHDOG_SCHEMA = "task038.lor-native-complex-hx.foundation-e-watchdog.v1"
CASE = "p3-mpi1"
SOURCE_NAME = "random"
VARIANT = "sequential-v1"
DEGREE = 3
H_NM = 50.0
RESTART = 20
MAX_IT = 10_000
CHECKPOINT_INTERVAL = 500
RESIDUAL_LIMIT = 1.0e-8
DIRECT_LIMIT = 1.0e-12
REPEAT_LIMIT = 1.0e-13
INPUT_LIMIT = 1.0e-12
PRIMAL_LIMIT = 1.0e-12
WATCHDOG_POLL_SECONDS = 0.25
WATCHDOG_RSS_LIMIT = 500_000_000
DIRECT_BACKEND = "petsc-preonly-lu-mumps"
BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
PRIOR_Q0 = {
    "source_sha": "47c3e5b1ab7205ac5cd8f37b63f33e0a6f46355f",
    "record_path": "docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/p3_exact_reference_triage_v1.json",
    "record_sha256": "2d767143ce3b28ac9a4b45962faf370770e1e637f05b4f0b62bb279fe7f6ca82",
    "checker_path": "docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/p3_exact_reference_triage_v1_checker.json",
    "checker_sha256": "be70e0e559fea32023dfde58e4ede11009574c18f51e4b914d9b5034832a35ea",
    "rho": 4.203423379090078e-4,
}


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return [_jsonable(item) for item in value.tolist()]
    if isinstance(value, (np.integer, np.floating, np.bool_)):
        return _jsonable(value.item())
    if isinstance(value, complex):
        return {"real": float(value.real), "imag": float(value.imag)}
    return value


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            _jsonable(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _identity_sha(value: Any) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _relative(left: Any, right: Any) -> float:
    difference = left.copy()
    difference.axpy(-1.0, right)
    numerator = float(difference.norm())
    denominator = max(float(right.norm()), np.finfo(float).tiny)
    difference.destroy()
    return numerator / denominator


def _destroy(value: Any) -> None:
    destroy = getattr(value, "destroy", None)
    if destroy is not None:
        destroy()


def _apply_current_residual(
    residual: Any,
    restrict: Any,
    solve: Any,
    lift: Any,
) -> Any:
    """Apply the exact route to the current residual, never a cached vector."""

    low_input, _owner_packet = restrict(residual)
    try:
        low_solution, _facts = solve(low_input)
        try:
            return lift(low_solution)
        finally:
            _destroy(low_solution)
    finally:
        _destroy(low_input)


def _exact_edge_apply(
    fixture: RealL2PositiveHXFixture,
    direct_solver: DiagnosticDirectSolver,
    residual: Any,
) -> Any:
    return _apply_current_residual(
        residual,
        lambda value: low_input_from_high_dual(fixture, value),
        direct_solver.solve_lean,
        lambda value: lift_low_primal(fixture, value),
    )


def _array_descriptor(raw_dir: Path, name: str, values: np.ndarray) -> dict[str, Any]:
    values = np.asarray(values)
    path = raw_dir / f"{name}.npy"
    np.save(path, values, allow_pickle=False)
    return {
        "relative_path": path.name,
        "bytes": int(path.stat().st_size),
        "sha256": _sha256(path),
        "dtype": str(values.dtype),
        "shape": list(values.shape),
    }


def _role_descriptor(
    raw_dir: Path,
    name: str,
    semantic_role: str,
    keys: np.ndarray,
    values: np.ndarray,
) -> dict[str, Any]:
    keys = np.asarray(keys)
    values = np.asarray(values, dtype=np.complex128)
    if keys.ndim != 1 or values.ndim != 1 or keys.size != values.size:
        raise ValueError(f"invalid paired artifact {name}")
    return {
        "role": semantic_role,
        "keys": _array_descriptor(raw_dir, f"foundation_{name}_keys", keys),
        "values": _array_descriptor(raw_dir, f"foundation_{name}_values", values),
    }


def _matrix_csr(matrix: Any, raw_dir: Path, name: str) -> dict[str, Any]:
    indptr, indices, values = matrix.getValuesCSR()
    indptr = np.asarray(indptr)
    indices = np.asarray(indices)
    values = np.asarray(values, dtype=np.complex128)
    rows, cols = (int(value) for value in matrix.getSize())
    row_keys = np.asarray([f"lor-edge:{index}" for index in range(rows)], dtype="<U64")
    return {
        "rows": rows,
        "cols": cols,
        "type": str(matrix.getType()),
        "nnz": int(values.size),
        "numeric_bytes": int(values.nbytes),
        "index_bytes": int(indptr.nbytes + indices.nbytes),
        "indptr": _array_descriptor(raw_dir, f"foundation_{name}_indptr", indptr),
        "indices": _array_descriptor(raw_dir, f"foundation_{name}_indices", indices),
        "values": _array_descriptor(raw_dir, f"foundation_{name}_values", values),
        "row_keys": _array_descriptor(raw_dir, f"foundation_{name}_row_keys", row_keys),
    }


def _merge_pairs(parts: list[list[tuple[str, complex]]]) -> tuple[np.ndarray, np.ndarray]:
    merged: dict[str, complex] = {}
    for part in parts:
        for key, value in part:
            key = str(key)
            if key in merged:
                raise RuntimeError(f"duplicate canonical key {key}")
            merged[key] = complex(value)
    keys = np.asarray(sorted(merged), dtype="<U128")
    values = np.asarray([merged[key] for key in keys], dtype=np.complex128)
    return keys, values


def _merge_owner_pairs(parts: list[list[tuple[str, complex]]]) -> tuple[np.ndarray, np.ndarray]:
    merged: dict[str, complex] = {}
    for part in parts:
        for key, value in part:
            key = str(key)
            if key in merged:
                raise RuntimeError(f"duplicate owner key {key}")
            merged[key] = complex(value)
    keys = sorted(merged, key=lambda key: int(key.split(":", 1)[1]))
    return np.asarray(keys, dtype="<U128"), np.asarray(
        [merged[key] for key in keys], dtype=np.complex128
    )


def _owner_key_identity(left: Any, right: Any) -> bool:
    left_keys = {str(key) for key in np.asarray(left).tolist()}
    right_keys = {str(key) for key in np.asarray(right).tolist()}
    return len(left_keys) == len(np.asarray(left)) == len(right_keys) == len(np.asarray(right)) and left_keys == right_keys


def _constraint_rows(fixture: RealL2PositiveHXFixture) -> list[int]:
    index_map = fixture.high_space.dofmap.index_map
    owned = int(index_map.size_local)
    slaves = np.asarray(fixture.high_floquet.mpc.slaves, dtype=np.int32)
    slaves = slaves[(slaves >= 0) & (slaves < owned)]
    global_ids = np.asarray(index_map.local_to_global(slaves), dtype=np.int64)
    return sorted(set(int(value) for value in global_ids))


def _gather_constraint(
    comm: MPI.Comm, vector: Any, rows: list[int]
) -> tuple[np.ndarray, np.ndarray] | None:
    start, stop = vector.getOwnershipRange()
    local = [
        (f"high-slave:{row}", complex(vector.array[row - int(start)]))
        for row in rows
        if int(start) <= row < int(stop)
    ]
    gathered = comm.gather(local, root=0)
    if comm.rank != 0:
        return None
    return _merge_pairs(gathered)


def _gather_owner(
    comm: MPI.Comm,
    input_packet: tuple[np.ndarray, np.ndarray],
    solution_packet: tuple[np.ndarray, np.ndarray],
) -> dict[str, tuple[np.ndarray, np.ndarray]] | None:
    gathered = comm.gather(
        {
            "input": (np.asarray(input_packet[0]), np.asarray(input_packet[1])),
            "solution": (np.asarray(solution_packet[0]), np.asarray(solution_packet[1])),
        },
        root=0,
    )
    if comm.rank != 0:
        return None
    result: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for name in ("input", "solution"):
        parts = [
            [(f"owner:{int(key)}", complex(value)) for key, value in zip(item[name][0], item[name][1], strict=True)]
            for item in gathered
        ]
        result[name] = _merge_owner_pairs(parts)
    return result


def _constraint_relative(vector: Any, rows: list[int]) -> float:
    start, stop = vector.getOwnershipRange()
    values = np.asarray(
        [vector.array[row - int(start)] for row in rows if int(start) <= row < int(stop)],
        dtype=np.complex128,
    )
    local_max = float(np.max(np.abs(values), initial=0.0))
    norm = max(float(vector.norm()), np.finfo(float).tiny)
    return local_max / norm


class _TrackedExactPC:
    def __init__(self, fixture: RealL2PositiveHXFixture, solver: DiagnosticDirectSolver, rows: list[int]) -> None:
        self.fixture = fixture
        self.solver = solver
        self.rows = rows
        self.apply_count = 0
        self.max_input_unchanged_relative = 0.0
        self.max_primal_constraint_relative = 0.0
        self.all_finite = True

    def __call__(self, residual: Any) -> Any:
        before = residual.copy()
        output = _exact_edge_apply(self.fixture, self.solver, residual)
        after = residual.copy()
        try:
            self.max_input_unchanged_relative = max(
                self.max_input_unchanged_relative, _relative(after, before)
            )
            self.max_primal_constraint_relative = max(
                self.max_primal_constraint_relative,
                _constraint_relative(output, self.rows),
            )
            self.all_finite = self.all_finite and bool(
                np.all(np.isfinite(np.asarray(output.array)))
                and np.all(np.isfinite(np.asarray(residual.array)))
            )
            self.apply_count += 1
            return output
        finally:
            before.destroy()
            after.destroy()

    def facts(self) -> dict[str, Any]:
        return {
            "apply_count": int(self.apply_count),
            "max_input_unchanged_relative": float(self.max_input_unchanged_relative),
            "max_primal_constraint_relative": float(self.max_primal_constraint_relative),
            "finite": bool(self.all_finite),
        }


def _checkpoint_due(iteration: int) -> bool:
    return int(iteration) > 0 and int(iteration) % CHECKPOINT_INTERVAL == 0


def _expected_checkpoint_files(rank: int = 0) -> set[str]:
    return {"manifest.json", f"solution_rank{int(rank)}.npy"}


def _outer_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    summary = {
        key: _jsonable(value)
        for key, value in result.items()
        if key not in {"final_solution", "cycles", "checkpoint_facts"}
    }
    summary["total_high_action_count"] = int(result["matvec_count"]) + int(result["explicit_action_count"])
    return summary


def _boundary_facts(cycles: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    cumulative_matvec = 0
    cumulative_pc = 0
    cumulative_wall = 0.0
    cumulative_explicit = 1
    facts: list[dict[str, Any]] = []
    for cycle in cycles:
        cumulative_matvec += int(cycle["matvec_count"])
        cumulative_pc += int(cycle["pc_apply_count"])
        cumulative_wall += float(cycle["wall_seconds"])
        cumulative_explicit += 1
        if int(cycle["end_iteration"]) % CHECKPOINT_INTERVAL == 0:
            facts.append(
                {
                    "iteration": int(cycle["end_iteration"]),
                    "explicit_true_residual": float(cycle["explicit_true_residual"]),
                    "matvec_count": cumulative_matvec,
                    "pc_apply_count": cumulative_pc,
                    "cumulative_explicit_true_residual_action_count": cumulative_explicit,
                    "cumulative_high_action_count": cumulative_matvec + cumulative_explicit,
                    "wall_seconds": cumulative_wall,
                    "wall_semantics": "cumulative_cycle_wall_seconds_excludes_setup",
                    "resource": cycle["resource"],
                }
            )
    return facts


def _source_provenance(source_facts: Mapping[str, Any]) -> dict[str, str]:
    return {
        "input_identity_sha256": _identity_sha(
            {
                "mesh": "structured_refined_hexa_v1",
                "degree": DEGREE,
                "h_nm": H_NM,
                "source_name": SOURCE_NAME,
                "formula": source_facts["formula"],
            }
        ),
        "operator_identity_sha256": _identity_sha(
            {
                "operator": "positive_B_h",
                "degree": DEGREE,
                "h_nm": H_NM,
                "variant": VARIANT,
                "map": "owner_local_lor_hx_v1",
            }
        ),
        "physical_model_sha256": _identity_sha(
            {
                "model": "stage4_positive_auxiliary",
                "material_tags": ["air", "substrate", "grating"],
            }
        ),
    }


def _worker_record(
    raw_dir: Path,
    record_path: Path,
    source: dict[str, Any],
    runtime: dict[str, Any],
    rank_facts: list[dict[str, Any]],
    artifacts: dict[str, dict[str, Any]],
    matrix_artifacts: dict[str, dict[str, Any]],
    owner_artifacts: dict[str, dict[str, Any]],
    checkpoint_facts: list[dict[str, Any]],
    cycles: list[dict[str, Any]],
    outer: dict[str, Any],
    single_apply: dict[str, Any],
    pc_legality: dict[str, Any],
    route_audit: dict[str, Any],
    fixture_audit: dict[str, Any],
    provenance: dict[str, str],
    command: list[str],
) -> dict[str, Any]:
    component_hashes = {
        name: _identity_sha(
            {"keys_sha256": item["keys"]["sha256"], "values_sha256": item["values"]["sha256"]}
        )
        for name, item in {**artifacts, **owner_artifacts}.items()
    }
    hx_audit = fixture_audit.get("hx_audit", {})
    forbidden = {
        "high_order_global_aij": bool(
            fixture_audit.get("high_order_global_aij", False)
            or hx_audit.get("high_order_global_aij", hx_audit.get("high_order_aij", False))
        ),
        "global_dense_transfer": bool(
            fixture_audit.get("global_transfer_matrix", False)
            or hx_audit.get("global_transfer_matrix", False)
        ),
        "global_direct_coarse": bool(
            fixture_audit.get("global_direct_coarse", False)
            or hx_audit.get("global_direct_coarse", False)
        ),
        "global_numeric_allgather": bool(
            fixture_audit.get("global_numeric_allgather", False)
            or hx_audit.get("global_numeric_allgather", False)
        ),
    }
    return {
        "schema": SCHEMA,
        "stage": "foundation-e",
        "case": CASE,
        "degree": DEGREE,
        "h_nm": H_NM,
        "source_name": SOURCE_NAME,
        "variant": VARIANT,
        "mpi_size": 1,
        "raw_dir": str(raw_dir.resolve()),
        "record_path": str(record_path.resolve()),
        "command": command,
        "source": source,
        "runtime": runtime,
        "rank_facts": rank_facts,
        "provenance": provenance,
        "settings": {
            "ksp_type": "gmres",
            "pc_side": "right",
            "norm_type": "unpreconditioned",
            "restart": RESTART,
            "max_it": MAX_IT,
            "residual_replacement": True,
            "zero_initial_guess": True,
            "residual_limit": RESIDUAL_LIMIT,
            "checkpoint_interval": CHECKPOINT_INTERVAL,
            "first_checkpoint_iteration": None,
            "direct_backend": DIRECT_BACKEND,
        },
        "fixture_audit": fixture_audit,
        "production_forbidden": forbidden,
        "route_audit": route_audit,
        "canonical_artifacts": artifacts,
        "owner_artifacts": owner_artifacts,
        "matrix_artifacts": matrix_artifacts,
        "component_hashes": component_hashes,
        "checkpoint_facts": checkpoint_facts,
        "cycles": cycles,
        "boundary_facts": _boundary_facts(cycles),
        "outer": outer,
        "single_apply": single_apply,
        "pc_legality": pc_legality,
        "source_facts": {
            "name": SOURCE_NAME,
            "formula": "analytic deterministic pseudo-random edge field from fixed noninteger trigonometric frequencies and phases",
            "phase_application": "algebraic_slave_zero_action_internal_finalized_mpc_once",
        },
        "prior_q0_reference": PRIOR_Q0,
    }


def run_foundation_worker(
    raw_dir: Path,
    record_path: Path,
    expected_source_sha: str,
    expected_mpi_size: int,
) -> None:
    comm = MPI.COMM_WORLD
    root = Path(__file__).resolve().parents[1]
    if expected_mpi_size != 1 or comm.size != 1:
        raise ValueError("foundation E is frozen to p3-mpi1")
    _prepare_paths(raw_dir.resolve(), record_path.resolve(), comm, stage="foundation-e")
    _append_stage_marker(raw_dir, "setup", comm.rank)

    source_error: tuple[str, str] | None = None
    source: dict[str, Any] | None = None
    if comm.rank == 0:
        try:
            source = _source_identity(root, expected_source_sha)
        except Exception as exc:
            source_error = (type(exc).__name__, str(exc))
    source, source_error = comm.bcast((source, source_error), root=0)
    if source_error is not None or source is None:
        raise RuntimeError(f"foundation source identity failed: {source_error}")
    _append_stage_marker(raw_dir, "source_identity_closed", comm.rank)
    runtime = _runtime_identity(root, 1)
    _append_stage_marker(raw_dir, "runtime_identity", comm.rank)

    fixture: RealL2PositiveHXFixture | None = None
    source_vector = source_before = source_after = None
    rhs = rhs_repeat = None
    e_input_before = e_input_after = None
    e_output = e_repeat = None
    e_low_input = e_low_solution = None
    final_action = final_true = None
    outer: dict[str, Any] | None = None
    direct_solver: DiagnosticDirectSolver | None = None
    try:
        fixture = RealL2PositiveHXFixture(DEGREE, comm, variant=VARIANT)
        _append_stage_marker(raw_dir, "fixture_built", comm.rank)
        source_vector, source_facts = fixture.build_l2_source(SOURCE_NAME)
        source_before = source_vector.copy()
        rhs = fixture.apply_high_action_copy(source_vector)
        rhs_repeat = fixture.apply_high_action_copy(source_vector)
        source_after = source_vector.copy()

        constraint_rows = _constraint_rows(fixture)
        direct_solver = DiagnosticDirectSolver(fixture.edge_matrix, label="foundation-exact-edge")
        e_input_before = rhs.copy()
        e_low_input, _owner_input = low_input_from_high_dual(fixture, rhs)
        e_low_solution, direct_facts = direct_solver.solve(e_low_input)
        e_output = lift_low_primal(fixture, e_low_solution)
        e_repeat = _exact_edge_apply(fixture, direct_solver, rhs)
        e_input_after = rhs.copy()
        _append_stage_marker(raw_dir, "single_apply_legality", comm.rank)

        pc_probe = _TrackedExactPC(fixture, direct_solver, constraint_rows)
        _append_stage_marker(raw_dir, "outer_start", comm.rank)

        def checkpoint_writer(iteration: int, solution: Any, residual: float) -> Mapping[str, Any]:
            if not _checkpoint_due(iteration):
                raise RuntimeError(f"unexpected checkpoint boundary {iteration}")
            _append_stage_marker(raw_dir, f"checkpoint-{iteration}", comm.rank)
            ownership = {
                "rank": int(comm.rank),
                "ownership_range": [int(value) for value in solution.getOwnershipRange()],
                "local_size": int(solution.getLocalSize()),
                "global_size": int(solution.getSize()),
            }
            return write_solution_checkpoint(
                raw_dir / f"checkpoint-{iteration}",
                solution,
                iteration=iteration,
                explicit_true_residual=residual,
                input_identity_sha256=provenance["input_identity_sha256"],
                operator_identity_sha256=provenance["operator_identity_sha256"],
                physical_model_sha256=provenance["physical_model_sha256"],
                source_sha=expected_source_sha,
                ownership=ownership,
                comm=comm,
            )

        provenance = _source_provenance(source_facts)
        outer = run_restart20_cycles(
            rhs,
            fixture.apply_high_action_copy,
            pc_probe,
            max_it=MAX_IT,
            residual_limit=RESIDUAL_LIMIT,
            resource_sample=lambda: resource_authority_sample(os.getpid()),
            start_iteration=0,
            first_checkpoint_iteration=None,
            checkpoint_interval=CHECKPOINT_INTERVAL,
            checkpoint_writer=checkpoint_writer,
            cycle_observer=lambda iteration, _solution, _cycle: None,
            stop_on_true_residual=True,
        )
        final_solution = outer["final_solution"]
        final_action = fixture.apply_high_action_copy(final_solution)
        final_true = rhs.copy()
        final_true.axpy(-1.0 + 0.0j, final_action)
        _append_stage_marker(raw_dir, "final", comm.rank)

        high_vectors = {
            "source_before": (source_before, "primal"),
            "source_after": (source_after, "primal"),
            "high_rhs": (rhs, "dual"),
            "high_rhs_repeat": (rhs_repeat, "dual"),
            "e_input_before": (e_input_before, "dual"),
            "e_input_after": (e_input_after, "dual"),
            "e_output": (e_output, "primal"),
            "e_repeat": (e_repeat, "primal"),
            "e_final_solution": (final_solution, "primal"),
            "e_final_action": (final_action, "dual"),
            "e_final_true_residual": (final_true, "dual"),
        }
        high_payload = _l2_gather_payload(
            comm, _l2_canonical_payload(fixture, high_vectors)
        )
        constraint_payload = {
            "e_output_constraint": _gather_constraint(comm, e_output, constraint_rows),
            "e_repeat_constraint": _gather_constraint(comm, e_repeat, constraint_rows),
            "e_final_constraint": _gather_constraint(comm, final_solution, constraint_rows),
        }
        solution_owner = fixture._route_low_owner_packet(e_low_solution)
        owner_payload = _gather_owner(comm, _owner_input, solution_owner)
        _append_stage_marker(raw_dir, "canonical_packets_gathered", comm.rank)

        source_end: dict[str, Any] | None = None
        source_end_error: tuple[str, str] | None = None
        if comm.rank == 0:
            try:
                source_end = _source_identity(root, expected_source_sha)
            except Exception as exc:
                source_end_error = (type(exc).__name__, str(exc))
        source_end, source_end_error = comm.bcast((source_end, source_end_error), root=0)
        if source_end_error is not None or source_end is None:
            raise RuntimeError(f"foundation source end identity failed: {source_end_error}")
        source = {
            **source,
            "commit_sha_end": source_end["commit_sha_end"],
            "tracked_status_end": source_end["tracked_status_end"],
            "clean_end": source_end["clean_end"],
        }

        rank_fact = {
            "rank": int(comm.rank),
            "runtime": _jsonable(runtime),
            "pc_legality": pc_probe.facts(),
            "direct_factor_solve_count": int(direct_solver.solve_count),
            "outer_iterations": int(outer["iterations"]),
            "outer_matvec_count": int(outer["matvec_count"]),
            "outer_pc_apply_count": int(outer["pc_apply_count"]),
        }
        if comm.rank == 0:
            if high_payload is None or owner_payload is None:
                raise RuntimeError("foundation canonical payload missing at root")
            artifacts = {
                name: _role_descriptor(
                    raw_dir,
                    name,
                    "primal" if role == "primal" else "dual",
                    high_payload[f"{name}_keys"],
                    high_payload[f"{name}_values"],
                )
                for name, (_vector, role) in high_vectors.items()
            }
            for name, packet in constraint_payload.items():
                if packet is None:
                    raise RuntimeError(f"missing constraint artifact {name}")
                artifacts[name] = _role_descriptor(raw_dir, name, "constraint", *packet)
            owner_artifacts = {
                "e_low_input_owner": _role_descriptor(raw_dir, "e_low_input_owner", "dual", *owner_payload["input"]),
                "e_low_solution_owner": _role_descriptor(raw_dir, "e_low_solution_owner", "primal", *owner_payload["solution"]),
            }
            matrix_artifacts = {
                "edge": _matrix_csr(fixture.edge_matrix, raw_dir, "edge_matrix"),
                "e_low_input_matrix": _role_descriptor(
                    raw_dir,
                    "e_low_input_matrix",
                    "dual",
                    np.asarray([f"lor-edge:{i}" for i in range(e_low_input.getSize())], dtype="<U64"),
                    np.asarray(e_low_input.array, dtype=np.complex128),
                ),
                "e_low_solution_matrix": _role_descriptor(
                    raw_dir,
                    "e_low_solution_matrix",
                    "primal",
                    np.asarray([f"lor-edge:{i}" for i in range(e_low_solution.getSize())], dtype="<U64"),
                    np.asarray(e_low_solution.array, dtype=np.complex128),
                ),
            }
            fixture_audit = _jsonable(fixture.audit)
            owner_input_keys = np.asarray(owner_payload["input"][0], dtype="<U128")
            owner_solution_keys = np.asarray(owner_payload["solution"][0], dtype="<U128")
            expected_owner_keys = np.asarray(
                [f"owner:{int(value)}" for value in fixture.lor_topology.owned_edge_ids],
                dtype="<U128",
            )
            owner_route_equal = _owner_key_identity(owner_input_keys, owner_solution_keys)
            owner_inventory_equal = _owner_key_identity(owner_input_keys, expected_owner_keys)
            route_audit = {
                "owner_inventory_equal": owner_inventory_equal,
                "owner_count": int(owner_input_keys.size),
                "high_to_lor_owner_route": owner_inventory_equal,
                "lor_to_high_owner_route": owner_route_equal,
                "orientation_factor_count": int(fixture_audit.get("raw_edge_orientation_factor_count", 0)),
                "orientation_minus_count": int(fixture_audit.get("raw_edge_orientation_minus_count", 0)),
                "orientation_consistent": bool(fixture_audit.get("raw_edge_orientation_consistent", False)),
                "phase_application": fixture_audit.get("phase_application"),
                "slave_master_complete": bool(fixture_audit.get("slave_master_complete", False)),
            }
            direct_relative = float(direct_facts["relative_residual"])
            single_apply = {
                "direct_residual_relative": direct_relative,
                "direct_finite": bool(direct_facts["finite"]),
                "repeat_relative": _relative(e_output, e_repeat),
                "input_unchanged_relative": _relative(e_input_before, e_input_after),
                "primal_constraint_relative": _constraint_relative(e_output, constraint_rows),
                "direct_backend": DIRECT_BACKEND,
                "direct_solve_count_at_reference": 2,
            }
            pc_legality = pc_probe.facts()
            pc_legality["direct_factor_solve_count_total"] = int(direct_solver.solve_count)
            pc_legality["reference_repeat_relative"] = single_apply["repeat_relative"]
            pc_legality["reference_input_unchanged_relative"] = single_apply["input_unchanged_relative"]
            pc_legality["reference_primal_constraint_relative"] = single_apply["primal_constraint_relative"]
            build_record = lambda rank_facts: _worker_record(
                raw_dir,
                record_path,
                source,
                runtime,
                rank_facts,
                artifacts,
                matrix_artifacts,
                owner_artifacts,
                list(outer["checkpoint_facts"]),
                list(outer["cycles"]),
                _outer_summary(outer),
                single_apply,
                pc_legality,
                route_audit,
                fixture_audit,
                provenance,
                [
                    str(Path(sys.executable).absolute()),
                    "-m",
                    "benchmarks.run_task038_full3d_lor_hx_foundation",
                    "--stage",
                    "foundation-e",
                    "--case",
                    CASE,
                    "--raw-dir",
                    str(raw_dir.resolve()),
                    "--record",
                    str(record_path.resolve()),
                    "--expected-source-sha",
                    expected_source_sha,
                    "--expected-mpi-size",
                    "1",
                ],
            )
        else:
            build_record = None
        _append_stage_marker(raw_dir, "record_closeout", comm.rank)
        _closeout_record(comm, raw_dir, record_path, rank_fact, build_record)
        if comm.rank == 0:
            print(json.dumps({"record": str(record_path.resolve()), "schema": SCHEMA}, sort_keys=True), flush=True)
    finally:
        if outer is not None:
            destroy_krylov_result(outer)
        for value in (
            final_true,
            final_action,
            e_low_solution,
            e_low_input,
            e_repeat,
            e_output,
            e_input_after,
            e_input_before,
            rhs_repeat,
            rhs,
            source_after,
            source_before,
            source_vector,
        ):
            if value is not None:
                value.destroy()
        if direct_solver is not None:
            direct_solver.destroy()
        if fixture is not None:
            fixture.destroy()


def _watchdog_stop_reason(
    authority: Mapping[str, Any], rss_limit_bytes: int = WATCHDOG_RSS_LIMIT
) -> str | None:
    tree = authority.get("process_tree", {})
    if not bool(tree.get("all_status_readable", False)):
        return "authority_unreadable"
    if int(tree.get("swap_bytes", -1)) != 0:
        return "process_tree_swap_nonzero"
    cgroup = authority.get("job_cgroup", {})
    if bool(cgroup.get("dedicated_job_cgroup", False)) and int(cgroup.get("swap_current_bytes", -1)) != 0:
        return "dedicated_cgroup_swap_nonzero"
    if int(tree.get("rss_bytes", -1)) >= int(rss_limit_bytes):
        return "process_tree_rss_limit"
    return None


def _watchdog_terminal_exit_race(process: Any, reason: str | None) -> bool:
    return reason == "authority_unreadable" and process.poll() is not None


def _validate_watchdog_paths(worker_raw_dir: Path, watchdog_paths: tuple[Path, ...]) -> None:
    worker_root = worker_raw_dir.resolve()
    for path in watchdog_paths:
        resolved = path.resolve()
        if resolved == worker_root or worker_root in resolved.parents:
            raise ValueError(f"watchdog artifact must be sibling of worker raw_dir: {resolved}")


def _watchdog_argv_without_separator(argv: list[str]) -> list[str]:
    normalized = list(argv)
    marker = normalized.index("--worker-command")
    if marker + 1 < len(normalized) and normalized[marker + 1] == "--":
        del normalized[marker + 1]
    return normalized


def _watchdog_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Foundation E process-tree watchdog")
    parser.add_argument("--watchdog-raw", type=Path, required=True)
    parser.add_argument("--watchdog-compact", type=Path, required=True)
    parser.add_argument("--watchdog-log", type=Path, required=True)
    parser.add_argument("--worker-raw-dir", type=Path, required=True)
    parser.add_argument("--worker-record", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument(
        "--watchdog-rss-limit-bytes", type=int, default=WATCHDOG_RSS_LIMIT
    )
    parser.add_argument("--worker-command", nargs=argparse.REMAINDER, required=True)
    args = parser.parse_args(_watchdog_argv_without_separator(argv))
    if args.watchdog_rss_limit_bytes <= 0:
        parser.error("--watchdog-rss-limit-bytes must be a positive integer")
    command = list(args.worker_command)
    if not command:
        raise SystemExit("missing worker command")
    for path in (args.worker_raw_dir, args.worker_record, args.watchdog_raw, args.watchdog_compact, args.watchdog_log):
        if path.exists():
            raise FileExistsError(f"watchdog path already exists: {path}")
    _validate_watchdog_paths(
        args.worker_raw_dir,
        (args.watchdog_raw, args.watchdog_compact, args.watchdog_log),
    )
    for path in (args.watchdog_raw, args.watchdog_compact, args.watchdog_log):
        path.parent.mkdir(parents=True, exist_ok=True)
    samples: list[dict[str, Any]] = []
    started = time.monotonic()
    stop_reason = "natural_exit"
    termination: dict[str, Any] = {"requested": False, "method": "natural_exit"}
    terminal_exit_race_discard_count = 0
    with args.watchdog_log.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            command,
            stdout=log,
            stderr=subprocess.STDOUT,
            cwd=Path(__file__).resolve().parents[1],
            **worker_process_group_popen_kwargs(),
        )
        while process.poll() is None:
            authority = resource_authority_sample(process.pid)
            sample = {
                "wall_time_ns": time.time_ns(),
                "elapsed_seconds": time.monotonic() - started,
                "authority": _jsonable(authority),
            }
            samples.append(sample)
            reason = _watchdog_stop_reason(authority, args.watchdog_rss_limit_bytes)
            if _watchdog_terminal_exit_race(process, reason):
                samples.pop()
                terminal_exit_race_discard_count = 1
                stop_reason = "natural_exit"
                break
            if reason is not None:
                stop_reason = reason
                termination = terminate_process_tree(process)
                break
            time.sleep(WATCHDOG_POLL_SECONDS)
        if stop_reason == "natural_exit" and samples:
            samples[-1]["last_live_observation"] = True
        if stop_reason == "natural_exit":
            termination = terminate_process_tree(process)
        returncode = int(process.wait())
    raw_payload = b"".join(_json_bytes(sample) for sample in samples)
    args.watchdog_raw.write_bytes(raw_payload)
    rss_values = [
        int(sample.get("authority", {}).get("process_tree", {}).get("rss_bytes", 0))
        for sample in samples
        if "authority" in sample
    ]
    swap_values = [
        int(sample.get("authority", {}).get("process_tree", {}).get("swap_bytes", 0))
        for sample in samples
        if "authority" in sample
    ]
    compact = {
        "schema": WATCHDOG_SCHEMA,
        "source_sha": str(args.source_sha),
        "worker_command": command,
        "worker_raw_dir": str(args.worker_raw_dir.resolve()),
        "worker_record": str(args.worker_record.resolve()),
        "watchdog_raw": str(args.watchdog_raw.resolve()),
        "watchdog_log": str(args.watchdog_log.resolve()),
        "returncode": returncode,
        "natural_exit": stop_reason == "natural_exit" and returncode == 0,
        "no_orphan": termination.get("process_group_exited") is True,
        "stop_reason": stop_reason,
        "sample_count": len(samples),
        "all_status_readable": bool(samples) and all(
            bool(sample.get("authority", {}).get("process_tree", {}).get("all_status_readable", False))
            for sample in samples
        ),
        "peak_process_tree_rss_bytes": max(rss_values, default=-1),
        "max_process_tree_swap_bytes": max(swap_values, default=-1),
        "watchdog_poll_seconds": WATCHDOG_POLL_SECONDS,
        "watchdog_rss_limit_bytes": int(args.watchdog_rss_limit_bytes),
        "terminal_exit_race_discard_count": terminal_exit_race_discard_count,
        "raw_sha256": _sha256(args.watchdog_raw),
    }
    args.watchdog_compact.write_bytes(_json_bytes(compact))
    return returncode if stop_reason == "natural_exit" else 1


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if raw_argv and raw_argv[0] == "--watchdog":
        return _watchdog_main(raw_argv[1:])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watchdog", action="store_true")
    parser.add_argument("--stage", choices=("foundation-e",))
    parser.add_argument("--case", choices=(CASE,))
    parser.add_argument("--raw-dir", type=Path)
    parser.add_argument("--record", type=Path)
    parser.add_argument("--expected-source-sha")
    parser.add_argument("--expected-mpi-size", type=int)
    args = parser.parse_args(raw_argv)
    required = (args.stage, args.case, args.raw_dir, args.record, args.expected_source_sha, args.expected_mpi_size)
    if any(value is None for value in required):
        parser.error("worker mode requires stage, case, raw-dir, record, expected-source-sha, expected-mpi-size")
    run_foundation_worker(args.raw_dir, args.record, args.expected_source_sha, args.expected_mpi_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
