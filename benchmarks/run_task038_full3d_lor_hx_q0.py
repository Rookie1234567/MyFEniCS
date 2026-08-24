"""Thin Review V10 Q0 exact-reference diagnostic worker.

This route is intentionally limited to p3/h50 MPI1/random.  It reuses the
existing production fixture and multiplicative-v1 ordering, while replacing
the LOR edge inverse or the four scalar nodal solves with one reusable small
PREONLY+LU/MUMPS diagnostic factor.  It writes raw NumPy evidence; the
independent checker makes the Q0 decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
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
from src.solvers.fullspace_memory_first_krylov import (
    destroy_krylov_result,
    run_restart20_cycles,
)
from src.solvers.fullspace_lor_native_hx_fixture import RealL2PositiveHXFixture
from src.solvers.fullspace_lor_hx_root_cause import (
    DiagnosticDirectSolver,
    lift_low_primal,
    low_dual_owner_packet,
    low_input_from_high_dual,
    replay_multiplicative_components,
)


SCHEMA = "task038.lor-native-complex-hx.q0-record.v1"
CASE = "p3-mpi1"
SOURCE_NAME = "random"
VARIANT = "sequential-v1"
RESTART = 20
MAX_IT = 500
RESIDUAL_LIMIT = 1.0e-8
EXACT_LIMIT = 1.0e-12
REPEAT_LIMIT = 1.0e-13
INPUT_LIMIT = 1.0e-12
DIRECT_BACKEND = "petsc-preonly-lu-mumps"
TRACE_NAMES = (
    "edge_jacobi_pre",
    "gradient",
    "pi_x",
    "pi_y",
    "pi_z",
    "edge_jacobi_post",
)
NODAL_TRACE_NAMES = ("gradient", "pi_x", "pi_y", "pi_z")


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
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
            _jsonable(value), sort_keys=True, separators=(",", ":"), allow_nan=False
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


def _relative(left: np.ndarray, right: np.ndarray) -> float:
    left = np.asarray(left, dtype=np.complex128)
    right = np.asarray(right, dtype=np.complex128)
    return float(np.linalg.norm(left - right) / max(np.linalg.norm(right), np.finfo(float).tiny))


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
    role: str,
    semantic_role: str,
    keys: np.ndarray,
    values: np.ndarray,
) -> dict[str, Any]:
    keys = np.asarray(keys)
    values = np.asarray(values, dtype=np.complex128)
    if keys.ndim != 1 or values.ndim != 1 or keys.size != values.size:
        raise ValueError(f"Q0 role {role} is not a paired one-dimensional vector")
    return {
        "role": semantic_role,
        "keys": _array_descriptor(raw_dir, f"q0_{role}_keys", keys),
        "values": _array_descriptor(raw_dir, f"q0_{role}_values", values),
    }


def _merge_pairs(parts: list[list[tuple[str, complex]]]) -> tuple[np.ndarray, np.ndarray]:
    merged: dict[str, complex] = {}
    for part in parts:
        for key, value in part:
            key = str(key)
            if key in merged:
                raise RuntimeError(f"duplicate Q0 canonical key {key}")
            merged[key] = complex(value)
    keys = np.asarray(sorted(merged), dtype="<U128")
    values = np.asarray([merged[key] for key in keys], dtype=np.complex128)
    return keys, values


def _gather_constraint_payload(
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


def _gather_named_low_payload(
    comm: MPI.Comm,
    fixture: RealL2PositiveHXFixture,
    vectors: dict[str, tuple[str, Any]],
    direct_packets: dict[str, tuple[np.ndarray, np.ndarray]],
) -> dict[str, tuple[np.ndarray, np.ndarray]] | None:
    """Gather only evidence packets; no numeric allgather is used."""

    local: dict[str, list[tuple[str, complex]]] = {}
    for name, (kind, vector) in vectors.items():
        if kind == "node":
            from benchmarks.run_task038_full3d_lor_hx_root_cause import _node_pairs

            local[name] = _node_pairs(fixture, vector)
        elif kind == "node-global":
            index_map = fixture.lor_node_space.dofmap.index_map
            owned = int(index_map.size_local)
            global_ids = np.asarray(
                index_map.local_to_global(np.arange(owned, dtype=np.int32)),
                dtype=np.int64,
            )
            local[name] = [
                (f"node-global:{int(gid)}", complex(value))
                for gid, value in zip(global_ids, vector.array[:owned], strict=True)
            ]
        elif kind == "edge":
            start, stop = vector.getOwnershipRange()
            local[name] = [
                (f"lor-edge:{int(gid)}", complex(value))
                for gid, value in zip(range(int(start), int(stop)), vector.array, strict=True)
            ]
        elif kind == "dual":
            ids, values = low_dual_owner_packet(fixture, vector)
            local[name] = [
                (f"lor-edge:{int(gid)}", complex(value))
                for gid, value in zip(ids, values, strict=True)
            ]
        elif kind == "primal":
            ids, values = fixture._route_low_owner_packet(vector)
            local[name] = [
                (f"lor-edge:{int(gid)}", complex(value))
                for gid, value in zip(ids, values, strict=True)
            ]
        else:
            raise ValueError(f"unknown Q0 low evidence kind {kind!r}")
    for name, (ids, values) in direct_packets.items():
        local[name] = [
            (f"lor-edge:{int(gid)}", complex(value))
            for gid, value in zip(ids, values, strict=True)
        ]
    gathered = comm.gather(local, root=0)
    if comm.rank != 0:
        return None
    names = tuple(local)
    return {
        name: _merge_pairs([part[name] for part in gathered])
        for name in names
    }


def _gather_high_payload(
    comm: MPI.Comm,
    fixture: RealL2PositiveHXFixture,
    vectors: dict[str, tuple[Any, str]],
) -> dict[str, np.ndarray] | None:
    canonical = _l2_canonical_payload(fixture, vectors)
    return _l2_gather_payload(comm, canonical)


def _matrix_csr(matrix: Any, raw_dir: Path, name: str, row_prefix: str) -> dict[str, Any]:
    indptr, indices, values = matrix.getValuesCSR()
    indptr = np.asarray(indptr)
    indices = np.asarray(indices)
    values = np.asarray(values, dtype=np.complex128)
    row_count, col_count = (int(value) for value in matrix.getSize())
    row_keys = np.asarray(
        [f"{row_prefix}:{index}" for index in range(row_count)], dtype="<U64"
    )
    return {
        "rows": row_count,
        "cols": col_count,
        "type": str(matrix.getType()),
        "nnz": int(values.size),
        "numeric_bytes": int(values.nbytes),
        "index_bytes": int(indptr.nbytes + indices.nbytes),
        "indptr": _array_descriptor(raw_dir, f"q0_{name}_indptr", indptr),
        "indices": _array_descriptor(raw_dir, f"q0_{name}_indices", indices),
        "values": _array_descriptor(raw_dir, f"q0_{name}_values", values),
        "row_keys": _array_descriptor(raw_dir, f"q0_{name}_row_keys", row_keys),
    }


def _exact_edge_apply(
    fixture: RealL2PositiveHXFixture,
    direct_solver: DiagnosticDirectSolver,
    residual: Any,
) -> Any:
    low_input, _packet = low_input_from_high_dual(fixture, residual)
    try:
        low_solution, _facts = direct_solver.solve_lean(low_input)
        try:
            return lift_low_primal(fixture, low_solution)
        finally:
            low_solution.destroy()
    finally:
        low_input.destroy()


def _exact_nodal_apply(
    fixture: RealL2PositiveHXFixture,
    direct_solver: DiagnosticDirectSolver,
    residual: Any,
) -> Any:
    low_input, _packet = low_input_from_high_dual(fixture, residual)
    try:
        replay = replay_multiplicative_components(
            fixture, low_input, direct_solver.solve_lean, capture_traces=False
        )
        try:
            return lift_low_primal(fixture, replay["result"])
        finally:
            replay["result"].destroy()
            replay["remaining"].destroy()
    finally:
        low_input.destroy()


def _outer_summary(result: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _jsonable(value)
        for key, value in result.items()
        if key not in {"final_solution"}
    }


def _constraint_rows(fixture: RealL2PositiveHXFixture) -> list[int]:
    index_map = fixture.high_space.dofmap.index_map
    owned = int(index_map.size_local)
    slave_local = np.asarray(fixture.high_floquet.mpc.slaves, dtype=np.int32)
    slave_local = slave_local[(slave_local >= 0) & (slave_local < owned)]
    global_ids = np.asarray(index_map.local_to_global(slave_local), dtype=np.int64)
    return sorted(set(int(value) for value in global_ids))


def _constraint_absolute(vector: Any, rows: list[int]) -> float:
    start, stop = vector.getOwnershipRange()
    selected = [complex(vector.array[row - int(start)]) for row in rows if start <= row < stop]
    return float(max((abs(value) for value in selected), default=0.0))


def _build_record(
    raw_dir: Path,
    record_path: Path,
    source: dict[str, Any],
    runtime: dict[str, Any],
    rank_facts: list[dict[str, Any]],
    artifacts: dict[str, dict[str, Any]],
    matrix_artifacts: dict[str, dict[str, Any]],
    component_hashes: dict[str, str],
    fixture_audit: dict[str, Any],
    provenance: dict[str, str],
    facts: dict[str, Any],
    command: list[str],
) -> dict[str, Any]:
    hx_audit = fixture_audit.get("hx_audit", {})
    return {
        "schema": SCHEMA,
        "stage": "q0",
        "scope": "v10_exact_reference_triage",
        "case": CASE,
        "degree": 3,
        "h_nm": 50.0,
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
            "reference_outer": {
                "ksp_type": "gmres",
                "pc_side": "right",
                "norm_type": "unpreconditioned",
                "restart": RESTART,
                "max_it": MAX_IT,
                "residual_replacement": True,
                "zero_initial_guess": True,
                "residual_limit": RESIDUAL_LIMIT,
            },
            "edge_direct": {
                "backend": DIRECT_BACKEND,
                "ksp_type": "preonly",
                "pc_type": "lu",
                "factor_solver_type": "mumps",
                "factor_reused_per_reference": True,
            },
            "nodal_direct": {
                "backend": DIRECT_BACKEND,
                "ksp_type": "preonly",
                "pc_type": "lu",
                "factor_solver_type": "mumps",
                "factor_reused_for_four_components": True,
            },
            "exact_edge_limit": EXACT_LIMIT,
            "exact_nodal_limit": EXACT_LIMIT,
            "input_limit": INPUT_LIMIT,
            "repeat_limit": REPEAT_LIMIT,
        },
        "fixture_audit": fixture_audit,
        "route_audit": facts["route_audit"],
        "matrix_artifacts": matrix_artifacts,
        "component_hashes": component_hashes,
        "canonical_artifacts": artifacts,
        "reference_e": facts["reference_e"],
        "reference_n": facts["reference_n"],
        "primal_constraint_rows": facts["primal_constraint_rows"],
        "high_rhs_repeat_relative": facts["high_rhs_repeat_relative"],
        "source_unchanged_relative": facts["source_unchanged_relative"],
        "production": {
            "variant": VARIANT,
            "production_pc_direct_factor_applied": False,
            "global_transfer_matrix": bool(
                fixture_audit.get("global_transfer_matrix", False)
                or hx_audit.get("global_transfer_matrix", False)
            ),
            "global_numeric_allgather": bool(
                fixture_audit.get("global_numeric_allgather", False)
                or hx_audit.get("global_numeric_allgather", False)
            ),
            "global_direct_coarse": bool(
                fixture_audit.get("global_direct_coarse", False)
                or hx_audit.get("global_direct_coarse", False)
            ),
            "high_order_global_aij": bool(
                fixture_audit.get("high_order_global_aij", False)
                or hx_audit.get("high_order_global_aij", hx_audit.get("high_order_aij", False))
            ),
            "ordinary_default_changed": False,
        },
    }


def run_q0_worker(
    raw_dir: Path, record_path: Path, expected_source_sha: str, expected_mpi_size: int
) -> None:
    comm = MPI.COMM_WORLD
    root = Path(__file__).resolve().parents[1]
    if expected_mpi_size != 1 or comm.size != 1:
        raise ValueError("Q0 is frozen to p3-mpi1 and does not accept MPI2")
    _prepare_paths(raw_dir.resolve(), record_path.resolve(), comm, stage="q0")
    _append_stage_marker(raw_dir, "paths_ready", comm.rank)

    source_error: tuple[str, str] | None = None
    source: dict[str, Any] | None = None
    if comm.rank == 0:
        try:
            source = _source_identity(root, expected_source_sha)
        except Exception as exc:
            source_error = (type(exc).__name__, str(exc))
    source, source_error = comm.bcast((source, source_error), root=0)
    if source_error is not None or source is None:
        raise RuntimeError(f"Q0 source identity failed: {source_error}")
    _append_stage_marker(raw_dir, "source_identity_closed", comm.rank)
    runtime = _runtime_identity(root, expected_mpi_size)
    _append_stage_marker(raw_dir, "runtime_identity", comm.rank)

    fixture: RealL2PositiveHXFixture | None = None
    source_vector = None
    source_before = None
    source_after = None
    rhs = None
    rhs_repeat = None
    e_solver: DiagnosticDirectSolver | None = None
    n_solver: DiagnosticDirectSolver | None = None
    e_output = e_repeat = None
    n_output = n_repeat = None
    e_low_input = e_low_solution = None
    n_trace = None
    e_outer = n_outer = None
    e_final_action = e_final_true = None
    n_final_action = n_final_true = None
    e_input_before = e_input_after = None
    n_input_before = n_input_after = None
    n_low_input = None
    try:
        fixture = RealL2PositiveHXFixture(3, comm, variant=VARIANT)
        _append_stage_marker(raw_dir, "fixture_built", comm.rank)
        source_vector, source_facts = fixture.build_l2_source(SOURCE_NAME)
        source_before = source_vector.copy()
        rhs = fixture.apply_high_action_copy(source_vector)
        rhs_repeat = fixture.apply_high_action_copy(source_vector)
        source_after = source_vector.copy()
        _append_stage_marker(raw_dir, "source_built", comm.rank)

        e_solver = DiagnosticDirectSolver(fixture.edge_matrix, label="q0-exact-edge")
        e_input_before = rhs.copy()
        e_low_input, e_owner_packet = low_input_from_high_dual(fixture, rhs)
        e_low_solution, e_direct_facts = e_solver.solve(e_low_input)
        e_output = lift_low_primal(fixture, e_low_solution)
        e_input_after = rhs.copy()
        e_repeat = _exact_edge_apply(fixture, e_solver, rhs)
        _append_stage_marker(raw_dir, "reference_e_built", comm.rank)

        n_solver = DiagnosticDirectSolver(fixture.node_matrix, label="q0-exact-nodal")
        n_input_before = rhs.copy()
        n_low_input, n_owner_packet = low_input_from_high_dual(fixture, rhs)
        n_trace = replay_multiplicative_components(
            fixture, n_low_input, n_solver.solve, capture_traces=True
        )
        n_output = lift_low_primal(fixture, n_trace["result"])
        n_input_after = rhs.copy()
        n_repeat = _exact_nodal_apply(fixture, n_solver, rhs)
        _append_stage_marker(raw_dir, "reference_n_built", comm.rank)

        e_outer = run_restart20_cycles(
            rhs,
            fixture.apply_high_action_copy,
            lambda vector: _exact_edge_apply(fixture, e_solver, vector),
            max_it=MAX_IT,
            residual_limit=RESIDUAL_LIMIT,
            resource_sample=lambda: resource_authority_sample(os.getpid()),
            start_iteration=0,
            first_checkpoint_iteration=None,
            checkpoint_interval=MAX_IT,
            stop_on_true_residual=True,
        )
        e_final_action = fixture.apply_high_action_copy(e_outer["final_solution"])
        e_final_true = rhs.copy()
        e_final_true.axpy(-1.0 + 0.0j, e_final_action)
        _append_stage_marker(raw_dir, "outer_e_built", comm.rank)

        n_outer = run_restart20_cycles(
            rhs,
            fixture.apply_high_action_copy,
            lambda vector: _exact_nodal_apply(fixture, n_solver, vector),
            max_it=MAX_IT,
            residual_limit=RESIDUAL_LIMIT,
            resource_sample=lambda: resource_authority_sample(os.getpid()),
            start_iteration=0,
            first_checkpoint_iteration=None,
            checkpoint_interval=MAX_IT,
            stop_on_true_residual=True,
        )
        n_final_action = fixture.apply_high_action_copy(n_outer["final_solution"])
        n_final_true = rhs.copy()
        n_final_true.axpy(-1.0 + 0.0j, n_final_action)
        _append_stage_marker(raw_dir, "outer_n_built", comm.rank)

        high_vectors = {
            "source_before": (source_before, "primal"),
            "source_after": (source_after, "primal"),
            "high_rhs": (rhs, "dual"),
            "high_rhs_repeat": (rhs_repeat, "dual"),
            "e_input_before": (e_input_before, "dual"),
            "e_input_after": (e_input_after, "dual"),
            "e_output": (e_output, "primal"),
            "e_repeat": (e_repeat, "primal"),
            "e_final_solution": (e_outer["final_solution"], "primal"),
            "e_final_action": (e_final_action, "dual"),
            "e_final_true_residual": (e_final_true, "dual"),
            "n_input_before": (n_input_before, "dual"),
            "n_input_after": (n_input_after, "dual"),
            "n_output": (n_output, "primal"),
            "n_repeat": (n_repeat, "primal"),
            "n_final_solution": (n_outer["final_solution"], "primal"),
            "n_final_action": (n_final_action, "dual"),
            "n_final_true_residual": (n_final_true, "dual"),
        }
        high_payload = _gather_high_payload(comm, fixture, high_vectors)
        constraint_rows = _constraint_rows(fixture)
        constraint_payload = {
            "e_output_constraint": _gather_constraint_payload(
                comm, e_output, constraint_rows
            ),
            "e_repeat_constraint": _gather_constraint_payload(
                comm, e_repeat, constraint_rows
            ),
            "n_output_constraint": _gather_constraint_payload(
                comm, n_output, constraint_rows
            ),
            "n_repeat_constraint": _gather_constraint_payload(
                comm, n_repeat, constraint_rows
            ),
            "e_final_constraint": _gather_constraint_payload(
                comm, e_outer["final_solution"], constraint_rows
            ),
            "n_final_constraint": _gather_constraint_payload(
                comm, n_outer["final_solution"], constraint_rows
            ),
        }

        low_vectors: dict[str, tuple[str, Any]] = {
            "e_low_solution": ("primal", e_low_solution),
            "e_low_input_matrix": ("edge", e_low_input),
            "e_low_solution_matrix": ("edge", e_low_solution),
        }
        for trace in n_trace["traces"]:
            name = str(trace["name"])
            low_vectors[f"n_{name}_result"] = ("primal", trace["result"])
            low_vectors[f"n_{name}_remaining"] = ("dual", trace["remaining"])
            low_vectors[f"n_{name}_edge_delta"] = ("primal", trace["edge_delta"])
            low_vectors[f"n_{name}_edge_action"] = ("dual", trace["edge_action"])
            if trace["rhs"] is not None:
                low_vectors[f"n_{name}_rhs"] = ("node", trace["rhs"])
                low_vectors[f"n_{name}_nodal_delta"] = ("node", trace["nodal_delta"])
                low_vectors[f"n_{name}_rhs_matrix"] = ("node-global", trace["rhs"])
                low_vectors[f"n_{name}_nodal_delta_matrix"] = ("node-global", trace["nodal_delta"])
        low_payload = _gather_named_low_payload(
            comm,
            fixture,
            low_vectors,
            {"e_low_input": e_owner_packet, "n_low_input": n_owner_packet},
        )
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
            raise RuntimeError(f"Q0 source end identity failed: {source_end_error}")
        source = {**source, "commit_sha_end": source_end["commit_sha_end"], "tracked_status_end": source_end["tracked_status_end"], "clean_end": source_end["clean_end"]}

        rank_fact = {
            "rank": int(comm.rank),
            "runtime": _jsonable(runtime),
            "e_repeat_relative": _relative(np.asarray(e_output.array), np.asarray(e_repeat.array)),
            "n_repeat_relative": _relative(np.asarray(n_output.array), np.asarray(n_repeat.array)),
            "e_input_unchanged_relative": _relative(np.asarray(e_input_before.array), np.asarray(e_input_after.array)),
            "n_input_unchanged_relative": _relative(np.asarray(n_input_before.array), np.asarray(n_input_after.array)),
            "edge_direct_solve_count": int(e_solver.solve_count),
            "nodal_direct_solve_count": int(n_solver.solve_count),
        }

        if comm.rank == 0:
            if high_payload is None or low_payload is None:
                raise RuntimeError("Q0 root did not receive canonical payloads")
            artifacts: dict[str, dict[str, Any]] = {}
            for label in high_vectors:
                keys = high_payload[f"{label}_keys"]
                values = high_payload[f"{label}_values"]
                semantic = "primal" if label in {"source_before", "source_after", "e_output", "e_repeat", "e_final_solution", "n_output", "n_repeat", "n_final_solution"} else "dual"
                artifacts[label] = _role_descriptor(raw_dir, label, semantic, keys, values)
            for label, (keys, values) in low_payload.items():
                semantic = "node" if "rhs" in label or "nodal_delta" in label else ("dual" if "remaining" in label or "action" in label or "input" in label else "primal")
                artifacts[label] = _role_descriptor(raw_dir, label, semantic, keys, values)
            for label, packet in constraint_payload.items():
                if packet is None:
                    raise RuntimeError(f"missing Q0 constraint packet {label}")
                keys, values = packet
                artifacts[label] = _role_descriptor(
                    raw_dir, label, "constraint", keys, values
                )

            matrix_artifacts = {
                "edge": _matrix_csr(fixture.edge_matrix, raw_dir, "edge_matrix", "lor-edge"),
                "node": _matrix_csr(fixture.node_matrix, raw_dir, "node_matrix", "node-global"),
            }
            component_hashes = {
                role: _identity_sha(
                    {"keys_sha256": descriptor["keys"]["sha256"], "values_sha256": descriptor["values"]["sha256"]}
                )
                for role, descriptor in artifacts.items()
            }
            fixture_audit = _jsonable(fixture.audit)
            provenance = {
                "input_identity_sha256": _identity_sha({"degree": 3, "h_nm": 50.0, "source": SOURCE_NAME, "formula": source_facts["formula"]}),
                "operator_identity_sha256": _identity_sha({"operator": "positive_B_h", "degree": 3, "h_nm": 50.0, "variant": VARIANT, "maps": "owner_local_lor_hx_v1"}),
                "physical_model_sha256": _identity_sha({"model": "stage4_positive_auxiliary", "degree": 3, "h_nm": 50.0, "material_tags": "air_substrate_grating"}),
            }
            owner_ids = np.asarray(e_owner_packet[0], dtype=np.uint32)
            owner_inventory_equal = bool(
                np.array_equal(
                    owner_ids,
                    np.asarray(fixture.lor_topology.owned_edge_ids, dtype=np.uint32),
                )
            )
            route_audit = {
                "high_to_lor_owner_route": owner_inventory_equal,
                "lor_to_high_owner_route": owner_inventory_equal,
                "owner_inventory_equal": owner_inventory_equal,
                "owner_count": int(owner_ids.size),
                "orientation_factor_count": int(fixture_audit.get("raw_edge_orientation_factor_count", 0)),
                "orientation_minus_count": int(fixture_audit.get("raw_edge_orientation_minus_count", 0)),
                "orientation_consistent": bool(fixture_audit.get("raw_edge_orientation_consistent", False)),
                "phase_application": fixture_audit.get("phase_application"),
                "slave_master_complete": bool(fixture_audit.get("slave_master_complete", False)),
                "canonical_component_hashes": component_hashes,
            }
            facts = {
                "route_audit": route_audit,
                "high_rhs_repeat_relative": _relative(
                    np.asarray(rhs.array), np.asarray(rhs_repeat.array)
                ),
                "source_unchanged_relative": _relative(
                    np.asarray(source_before.array), np.asarray(source_after.array)
                ),
                "reference_e": {
                    "outer": _outer_summary(e_outer),
                    "direct_edge": _jsonable(e_direct_facts),
                    "input_unchanged_relative": _relative(
                        np.asarray(e_input_before.array), np.asarray(e_input_after.array)
                    ),
                    "repeat_relative": _relative(
                        np.asarray(e_output.array), np.asarray(e_repeat.array)
                    ),
                    "finite": bool(np.all(np.isfinite(np.asarray(e_output.array)))),
                    "primal_constraint_absolute": _constraint_absolute(
                        e_output, constraint_rows
                    ),
                    "direct_solve_count": rank_fact["edge_direct_solve_count"],
                    "direct_residual_limit": EXACT_LIMIT,
                    "final_residual_limit": RESIDUAL_LIMIT,
                },
                "reference_n": {
                    "outer": _outer_summary(n_outer),
                    "nodal_direct": [
                        {"name": trace["name"], **_jsonable(trace["solver"])}
                        for trace in n_trace["traces"]
                        if trace["name"] in NODAL_TRACE_NAMES
                    ],
                    "input_unchanged_relative": _relative(
                        np.asarray(n_input_before.array), np.asarray(n_input_after.array)
                    ),
                    "repeat_relative": _relative(
                        np.asarray(n_output.array), np.asarray(n_repeat.array)
                    ),
                    "finite": bool(np.all(np.isfinite(np.asarray(n_output.array)))),
                    "primal_constraint_absolute": _constraint_absolute(
                        n_output, constraint_rows
                    ),
                    "direct_solve_count": rank_fact["nodal_direct_solve_count"],
                    "direct_residual_limit": EXACT_LIMIT,
                    "final_residual_limit": RESIDUAL_LIMIT,
                    "component_trace_names": list(TRACE_NAMES),
                },
            }
            facts["primal_constraint_rows"] = constraint_rows
            def build_record(rank_facts: list[dict[str, Any]]) -> dict[str, Any]:
                record = _build_record(
                    raw_dir,
                    record_path,
                    source,
                    runtime,
                    rank_facts,
                    artifacts,
                    matrix_artifacts,
                    component_hashes,
                    fixture_audit,
                    provenance,
                    facts,
                    [
                        str(Path(sys.executable).absolute()),
                        "-m",
                        "benchmarks.run_task038_full3d_lor_hx_q0",
                        "--stage",
                        "q0",
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
                record["source_facts"] = {"name": SOURCE_NAME, "formula": source_facts["formula"], "phase_application": source_facts["phase_application"]}
                return record
        else:
            build_record = None
        _closeout_record(comm, raw_dir, record_path, rank_fact, build_record)
        if comm.rank == 0:
            print(json.dumps({"record": str(record_path.resolve()), "schema": SCHEMA}, sort_keys=True), flush=True)
    finally:
        for result in (e_outer, n_outer):
            if result is not None:
                destroy_krylov_result(result)
        for vector in (
            e_final_true,
            e_final_action,
            n_final_true,
            n_final_action,
            e_output,
            e_repeat,
            n_output,
            n_repeat,
            e_low_input,
            e_low_solution,
            n_low_input,
            e_input_before,
            e_input_after,
            n_input_before,
            n_input_after,
            rhs,
            rhs_repeat,
            source_before,
            source_after,
            source_vector,
        ):
            if vector is not None:
                vector.destroy()
        if n_trace is not None:
            for vector in (n_trace.get("result"), n_trace.get("remaining")):
                if vector is not None:
                    vector.destroy()
            for trace in n_trace.get("traces", []):
                for vector in trace.values():
                    if hasattr(vector, "destroy"):
                        vector.destroy()
        if e_solver is not None:
            e_solver.destroy()
        if n_solver is not None:
            n_solver.destroy()
        if fixture is not None:
            fixture.destroy()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("q0",), required=True)
    parser.add_argument("--case", choices=(CASE,), required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-mpi-size", type=int, required=True)
    args = parser.parse_args(argv)
    run_q0_worker(
        args.raw_dir,
        args.record,
        args.expected_source_sha,
        args.expected_mpi_size,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
