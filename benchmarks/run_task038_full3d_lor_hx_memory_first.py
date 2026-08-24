"""Thin parameterized P1 memory-first runner.

The reusable restart-20 lifecycle is in
``src.solvers.fullspace_memory_first_krylov``.  This module only binds the
frozen positive LOR-HX fixture, four source formulas, case identity, and
per-rank canonical evidence.  It writes facts; the independent checker makes
all qualification decisions.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
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
    _prepare_paths,
    _runtime_identity,
    _source_identity,
)
from benchmarks.task034_wsl_resources import resource_authority_sample
from src.solvers.fullspace_memory_first_krylov import (
    CHECKPOINT_INTERVAL,
    destroy_krylov_result,
    run_restart20_cycles,
    write_solution_checkpoint,
)
from src.solvers.fullspace_lor_native_hx_fixture import (
    L2_SOURCE_NAMES,
    RealL2PositiveHXFixture,
    l2_source_formula,
)


BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
SCHEMA = "task038.lor-native-complex-hx.memory-first-p1-record.v1"
VARIANT = "sequential-v1"
CASES = {
    "p2-mpi1": (2, 1),
    "p2-mpi2": (2, 2),
    "p3-mpi1": (3, 1),
    "p3-mpi2": (3, 2),
}
SOURCES = tuple(L2_SOURCE_NAMES)
SUITE_ORDER = tuple(f"{case}/{source}" for case in CASES for source in SOURCES)
MAX_IT = 2000
RESTART = 20
RESIDUAL_LIMIT = 1.0e-8
CHECKPOINT_STATUS_POINTS = (20, 80, 200, 500, 1000, 2000)
OLD_L2_RECORD_SHA = "0a6ccfdb6a28b003167046e3ca3fc5e4de0d40825784786319661901a65389f3"
OLD_L2_RHO = 1.7348663090876784
OLD_L2_CLASSIFICATION = "CONTROLLED_NEGATIVE_BY_POSITIVE_AUXILIARY_CONTRACTION_GATE"


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


def _packet_digest(key: Any) -> str:
    return hashlib.sha256(_json_bytes(key)).hexdigest()


def _canonical_packets(fixture: Any, vector: Any, role: str) -> list[tuple[Any, complex]]:
    from src.solvers.hcurl_canonical_vector_dolfinx import (
        extract_canonical_full_fe_dual_packets,
        extract_canonical_full_fe_packets,
    )

    if role == "primal":
        return extract_canonical_full_fe_packets(
            fixture.high_space, vector, fixture.high_floquet
        )[0]
    if role == "dual":
        return extract_canonical_full_fe_dual_packets(
            fixture.high_space, fixture.high_floquet.mpc, vector
        )[0]
    raise ValueError(f"unknown canonical role {role!r}")


def _array_descriptor(path: Path, values: np.ndarray) -> dict[str, Any]:
    return {
        "relative_path": path.name,
        "bytes": int(path.stat().st_size),
        "sha256": _sha256(path),
        "dtype": str(values.dtype),
        "shape": list(values.shape),
    }


def _write_canonical_shard(
    raw_dir: Path, fixture: Any, vector: Any, role: str, vector_role: str, rank: int
) -> dict[str, Any]:
    packets = sorted(_canonical_packets(fixture, vector, vector_role), key=lambda item: _packet_digest(item[0]))
    keys = np.asarray([_packet_digest(key) for key, _value in packets], dtype="<U64")
    values = np.asarray([complex(value) for _key, value in packets], dtype=np.complex128)
    key_path = raw_dir / f"{role}.rank{rank}.keys.npy"
    value_path = raw_dir / f"{role}.rank{rank}.values.npy"
    np.save(key_path, keys, allow_pickle=False)
    np.save(value_path, values, allow_pickle=False)
    return {
        "rank": int(rank),
        "role": vector_role,
        "keys": _array_descriptor(key_path, keys),
        "values": _array_descriptor(value_path, values),
    }


def _write_layout_shard(
    raw_dir: Path, name: str, vector: Any, rank: int
) -> dict[str, Any]:
    """Write one owned PETSc layout shard, without gathering numeric values."""

    values = np.asarray(vector.getArray(readonly=True), dtype=np.complex128).copy()
    path = raw_dir / f"{name}.rank{rank}.values.npy"
    np.save(path, values, allow_pickle=False)
    start, stop = vector.getOwnershipRange()
    return {
        "rank": int(rank),
        "ownership_range": [int(start), int(stop)],
        "local_size": int(vector.getLocalSize()),
        "global_size": int(vector.getSize()),
        "values": _array_descriptor(path, values),
    }


def _global_relative(numerator: Any, denominator: Any) -> float:
    denominator_norm = max(float(denominator.norm()), np.finfo(float).tiny)
    return float(numerator.norm()) / denominator_norm


def _difference_relative(left: Any, right: Any) -> float:
    difference = left.copy()
    difference.axpy(-1.0, right)
    try:
        return _global_relative(difference, right)
    finally:
        difference.destroy()


def _finite(comm: MPI.Comm, vector: Any) -> bool:
    local = bool(np.all(np.isfinite(vector.getArray(readonly=True))))
    return bool(comm.allreduce(1 if local else 0, op=MPI.MIN))


def _pc_legality(
    fixture: Any, residual: Any, raw_dir: Path, rank: int
) -> dict[str, Any]:
    """Measure fixed parity linearity without changing the production PC."""

    comm = MPI.COMM_WORLD
    start, stop = residual.getOwnershipRange()
    row_ids = np.arange(start, stop, dtype=np.int64)
    first = residual.copy()
    second = residual.copy()
    first.array[row_ids % 2 != 0] = 0.0
    second.array[row_ids % 2 == 0] = 0.0
    before_first = first.copy()
    before_second = second.copy()
    before_residual = residual.copy()
    coefficient_a = 0.375 + 0.25j
    coefficient_b = -0.625 + 0.5j
    combined = residual.copy()
    combined.array[:] = coefficient_a * first.array + coefficient_b * second.array
    before_combined = combined.copy()
    output_first = fixture.apply_high_preconditioner(first)
    output_second = fixture.apply_high_preconditioner(second)
    output_combined = fixture.apply_high_preconditioner(combined)
    output_repeat = fixture.apply_high_preconditioner(combined)
    expected = output_first.copy()
    expected.scale(coefficient_a)
    expected.axpy(coefficient_b, output_second)
    linearity = _difference_relative(output_combined, expected)
    repeat = _difference_relative(output_repeat, output_combined)
    inputs_unchanged = all(
        np.array_equal(before.array, after.array)
        for before, after in (
            (before_first, first),
            (before_second, second),
            (before_combined, combined),
        )
    )
    finite = all(
        _finite(comm, vector)
        for vector in (first, second, combined, output_first, output_second, output_combined, output_repeat)
    )
    slave_rows = np.asarray(fixture.high_floquet.mpc.slaves, dtype=np.int32)
    slave_max = max(
        (
            float(np.max(np.abs(vector.array[slave_rows])))
            for vector in (output_first, output_second, output_combined, output_repeat)
            if slave_rows.size
        ),
        default=0.0,
    )
    audit = fixture.audit
    hx_audit = fixture.hx.audit
    pc_artifacts = {
        name: _write_layout_shard(raw_dir, name, vector, rank)
        for name, vector in {
            "pc_input_residual_before": before_residual,
            "pc_input_residual_after": residual,
            "pc_input_first_before": before_first,
            "pc_input_first_after": first,
            "pc_input_second_before": before_second,
            "pc_input_second_after": second,
            "pc_input_combined_before": before_combined,
            "pc_input_combined_after": combined,
            "pc_output_first": output_first,
            "pc_output_second": output_second,
            "pc_output_combined": output_combined,
            "pc_output_repeat": output_repeat,
        }.items()
    }
    facts = {
        "direction_construction": "PETSc_global_row_parity",
        "alpha": [float(coefficient_a.real), float(coefficient_a.imag)],
        "beta": [float(coefficient_b.real), float(coefficient_b.imag)],
        "first_global_norm": float(first.norm()),
        "second_global_norm": float(second.norm()),
        "combined_global_norm": float(combined.norm()),
        "linearity_relative": float(linearity),
        "repeat_relative": float(repeat),
        "finite": bool(finite),
        "input_unchanged": bool(inputs_unchanged and np.array_equal(before_residual.array, residual.array)),
        "slave_constraint_absolute": slave_max,
        "slave_rows_local": int(slave_rows.size),
        "slave_local_indices": [int(value) for value in slave_rows.tolist()],
        "slave_master_complete": bool(audit.get("slave_master_complete", False)),
        "phase_application": audit.get("phase_application"),
        "high_order_global_aij": bool(
            audit["high_order_global_aij"] or hx_audit["high_order_aij"]
        ),
        "global_direct_coarse": bool(hx_audit["global_direct_coarse"]),
        "global_numeric_allgather": bool(
            audit["global_numeric_allgather"] or hx_audit["global_numeric_allgather"]
        ),
        "global_dense_transfer": bool(
            audit["global_transfer_matrix"] or hx_audit["global_transfer_matrix"]
        ),
        "pc_artifacts": pc_artifacts,
    }
    for vector in (
        before_first,
        before_second,
        before_combined,
        before_residual,
        expected,
        first,
        second,
        combined,
        output_first,
        output_second,
        output_combined,
        output_repeat,
    ):
        vector.destroy()
    return facts


def _resource() -> dict[str, Any]:
    fact = dict(resource_authority_sample(os.getpid()))
    fact["scope"] = "rank_process_tree_diagnostic_excludes_launcher"
    return fact


def _checkpoint_status(result: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    final_iteration = int(result["iterations"])
    first_pass = next(
        (
            int(cycle["end_iteration"])
            for cycle in result["cycles"]
            if float(cycle["explicit_true_residual"]) <= RESIDUAL_LIMIT
        ),
        None,
    )
    measured = {int(item["iteration"]): item for item in result["checkpoint_facts"]}
    statuses: dict[str, dict[str, Any]] = {}
    for point in CHECKPOINT_STATUS_POINTS:
        if first_pass is not None and point > first_pass:
            statuses[str(point)] = {"status": "not_reached_after_pass"}
        elif point > final_iteration:
            statuses[str(point)] = {"status": "not_reached"}
        elif point in measured:
            statuses[str(point)] = {"status": "measured", "checkpoint": measured[point]}
        else:
            statuses[str(point)] = {"status": "measured_no_checkpoint"}
    return statuses


def _closeout(
    comm: MPI.Comm,
    raw_dir: Path,
    record_path: Path,
    rank_fact: dict[str, Any],
    build_record: Any,
) -> None:
    _append_stage_marker(raw_dir, "p1_rank_metadata_collect_enter", comm.rank)
    rank_facts = comm.allgather(rank_fact)
    _append_stage_marker(raw_dir, "p1_rank_metadata_collect_exit", comm.rank)
    result: dict[str, Any] = {"ok": False}
    if comm.rank == 0:
        try:
            _append_stage_marker(raw_dir, "p1_record_build_begin", comm.rank)
            record = build_record(rank_facts)
            payload = _json_bytes(record)
            _append_stage_marker(raw_dir, "p1_record_write_begin", comm.rank)
            record_path.write_bytes(payload)
            _append_stage_marker(raw_dir, "p1_record_write_end", comm.rank)
            result = {"ok": True, "bytes": len(payload)}
        except Exception as exc:
            result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    result = comm.bcast(result, root=0)
    if not result.get("ok"):
        raise RuntimeError(str(result.get("error", "P1 record closeout failed")))
    _append_stage_marker(raw_dir, "p1_record_written", comm.rank)
    comm.Barrier()


def run_p1_worker(
    raw_dir: Path,
    record_path: Path,
    expected_source_sha: str,
    expected_mpi_size: int,
    case: str,
    source_name: str,
) -> None:
    comm = MPI.COMM_WORLD
    if case not in CASES or source_name not in SOURCES:
        raise ValueError("P1 case/source is not frozen")
    degree, case_mpi_size = CASES[case]
    if case_mpi_size != expected_mpi_size or comm.size != expected_mpi_size:
        raise ValueError("P1 case MPI identity does not close")
    _prepare_paths(raw_dir, record_path, comm, stage="p1")
    _append_stage_marker(raw_dir, "p1_paths_ready", comm.rank)
    root = Path.cwd()
    source = _source_identity(root, expected_source_sha) if comm.rank == 0 else None
    source = comm.bcast(source, root=0)
    runtime = _runtime_identity(root, expected_mpi_size)
    _append_stage_marker(raw_dir, "p1_runtime_identity", comm.rank)

    fixture = None
    source_vector = rhs = pc_output = pc_action = final_action = final_true = None
    result: dict[str, Any] | None = None
    try:
        fixture = RealL2PositiveHXFixture(degree, comm, variant=VARIANT)
        _append_stage_marker(raw_dir, "p1_fixture_built", comm.rank)
        source_vector, source_facts = fixture.build_l2_source(source_name)
        rhs = fixture.apply_high_action_copy(source_vector)
        source_before = source_vector.copy()
        pc_facts = _pc_legality(fixture, rhs, raw_dir, comm.rank)
        source_unchanged = bool(np.array_equal(source_before.array, source_vector.array))
        source_facts["source_unchanged"] = source_unchanged
        source_before.destroy()
        pc_output = fixture.apply_high_preconditioner(rhs)
        pc_action = fixture.apply_high_action_copy(pc_output)
        true_one = rhs.copy()
        true_one.axpy(-1.0, pc_action)
        one_apply_rho = _global_relative(true_one, rhs)
        true_one.destroy()
        _append_stage_marker(raw_dir, "p1_one_apply", comm.rank)

        input_identity = _identity_sha(
            {
                "identity_schema": "task038.p1.partition-invariant-input.v1",
                "degree": degree,
                "source_name": source_name,
                "source_formula": l2_source_formula(source_name),
                "h_nm": 50.0,
            }
        )
        operator_identity = _identity_sha(
            {
                "identity_schema": "task038.p1.partition-invariant-operator.v1",
                "degree": degree,
                "operator": "matrix_free_positive_mu_inverse_curl_plus_k0_squared_abs_epsilon_mass",
                "complex_scalar": "complex128",
            }
        )
        physical_identity = _identity_sha(
            {
                "identity_schema": "task038.p1.partition-invariant-physical-model.v1",
                "degree": degree,
                "h_nm": 50.0,
                "regions": ["air", "substrate", "grating"],
                "coefficient_semantics": "piecewise_abs_mu_inverse_and_k0_squared_abs_epsilon",
            }
        )
        provenance = {
            "input_identity_sha256": input_identity,
            "operator_identity_sha256": operator_identity,
            "physical_model_sha256": physical_identity,
        }

        def checkpoint_writer(iteration: int, solution: Any, explicit: float) -> Mapping[str, Any]:
            return write_solution_checkpoint(
                raw_dir / f"checkpoint-{iteration}",
                solution,
                iteration=iteration,
                explicit_true_residual=explicit,
                input_identity_sha256=input_identity,
                operator_identity_sha256=operator_identity,
                physical_model_sha256=physical_identity,
                source_sha=expected_source_sha,
                ownership={
                    "rank": int(comm.rank),
                    "ownership_range": list(solution.getOwnershipRange()),
                    "local_size": int(solution.getLocalSize()),
                    "global_size": int(solution.getSize()),
                },
                comm=comm,
            )

        result = run_restart20_cycles(
            rhs,
            fixture.apply_high_action_copy,
            fixture.apply_high_preconditioner,
            max_it=MAX_IT,
            residual_limit=RESIDUAL_LIMIT,
            resource_sample=_resource,
            start_iteration=0,
            checkpoint_writer=checkpoint_writer,
            first_checkpoint_iteration=None,
            checkpoint_interval=CHECKPOINT_INTERVAL,
            stop_on_true_residual=True,
        )
        final_solution = result["final_solution"]
        final_action = fixture.apply_high_action_copy(final_solution)
        final_true = rhs.copy()
        final_true.axpy(-1.0, final_action)
        role_vectors = {
            "source": (source_vector, "primal"),
            "rhs": (rhs, "dual"),
            "final_solution": (final_solution, "primal"),
            "final_action": (final_action, "dual"),
            "final_true_residual": (final_true, "dual"),
        }
        local_artifacts = {
            role: _write_canonical_shard(raw_dir, fixture, vector, role, vector_role, comm.rank)
            for role, (vector, vector_role) in role_vectors.items()
        }
        _append_stage_marker(raw_dir, "p1_canonical_shards_written", comm.rank)
        if comm.rank == 0:
            end_source = _source_identity(root, expected_source_sha)
        else:
            end_source = None
        end_source = comm.bcast(end_source, root=0)
        source.update(
            {
                "commit_sha_end": end_source["commit_sha_end"],
                "tracked_status_end": end_source["tracked_status_end"],
                "clean_end": end_source["clean_end"],
            }
        )
        rank_fact = {
            "rank": int(comm.rank),
            "runtime": runtime,
            "matvec_count": int(result["matvec_count"]),
            "pc_apply_count": int(result["pc_apply_count"]),
            "explicit_action_count": int(result["explicit_action_count"]),
            "iterations": int(result["iterations"]),
            "reason": int(result["reason"]),
            "constraint": {
                "slave_constraint_absolute": float(pc_facts["slave_constraint_absolute"]),
                "slave_rows_local": int(pc_facts["slave_rows_local"]),
                "slave_master_complete": bool(pc_facts["slave_master_complete"]),
            },
            "pc_legality": pc_facts,
            "canonical_artifacts": local_artifacts,
            "cycle_ledger": result["cycles"],
            "final_finite": bool(_finite(comm, final_solution) and _finite(comm, final_action) and _finite(comm, final_true)),
        }

        def build_record(all_rank_facts: list[dict[str, Any]]) -> dict[str, Any]:
            artifacts = {
                role: {
                    "role": next(f["canonical_artifacts"][role]["role"] for f in all_rank_facts),
                    "shards": [f["canonical_artifacts"][role] for f in all_rank_facts],
                }
                for role in role_vectors
            }
            count_ranges = {
                key: {
                    "min": min(int(f[key]) for f in all_rank_facts),
                    "max": max(int(f[key]) for f in all_rank_facts),
                }
                for key in ("matvec_count", "pc_apply_count", "explicit_action_count", "iterations")
            }
            pc_artifacts = {
                role: {
                    "role": "dual" if role.startswith("pc_input") else "primal",
                    "shards": [
                        fact["pc_legality"]["pc_artifacts"][role]
                        for fact in all_rank_facts
                    ],
                }
                for role in (
                    "pc_input_residual_before",
                    "pc_input_residual_after",
                    "pc_input_first_before",
                    "pc_input_first_after",
                    "pc_input_second_before",
                    "pc_input_second_after",
                    "pc_input_combined_before",
                    "pc_input_combined_after",
                    "pc_output_first",
                    "pc_output_second",
                    "pc_output_combined",
                    "pc_output_repeat",
                )
            }
            fixture_audit = _jsonable(fixture.audit)
            hx_audit = _jsonable(fixture.hx.audit)
            aggregate_pc = dict(pc_facts)
            aggregate_pc.update(
                {
                    "finite": all(bool(fact["pc_legality"]["finite"]) for fact in all_rank_facts),
                    "input_unchanged": all(bool(fact["pc_legality"]["input_unchanged"]) for fact in all_rank_facts),
                    "linearity_relative": max(float(fact["pc_legality"]["linearity_relative"]) for fact in all_rank_facts),
                    "repeat_relative": max(float(fact["pc_legality"]["repeat_relative"]) for fact in all_rank_facts),
                    "slave_constraint_absolute": max(float(fact["pc_legality"]["slave_constraint_absolute"]) for fact in all_rank_facts),
                    "slave_local_indices_by_rank": {
                        str(fact["rank"]): fact["pc_legality"]["slave_local_indices"]
                        for fact in all_rank_facts
                    },
                    "pc_artifacts": pc_artifacts,
                }
            )
            return {
                "schema": SCHEMA,
                "stage": "p1",
                "scope": "memory_first_positive_krylov_suite",
                "case": case,
                "degree": degree,
                "h_nm": 50.0,
                "source_name": source_name,
                "variant": VARIANT,
                "mpi_size": expected_mpi_size,
                "source": source,
                "runtime": runtime,
                "raw_dir": str(raw_dir.resolve()),
                "record_path": str(record_path.resolve()),
                "command": [
                    str(Path(sys.executable).absolute()),
                    "-m",
                    "benchmarks.run_task038_full3d_lor_hx_memory_first",
                    "--stage",
                    "p1",
                    "--case",
                    case,
                    "--source",
                    source_name,
                    "--raw-dir",
                    str(raw_dir.resolve()),
                    "--record",
                    str(record_path.resolve()),
                    "--expected-source-sha",
                    expected_source_sha,
                    "--expected-mpi-size",
                    str(expected_mpi_size),
                ],
                "settings": {
                    "ksp_type": "gmres",
                    "pc_side": "right",
                    "norm_type": "unpreconditioned",
                    "restart": RESTART,
                    "max_it": MAX_IT,
                    "residual_limit": RESIDUAL_LIMIT,
                    "residual_replacement": True,
                    "checkpoint_interval": CHECKPOINT_INTERVAL,
                    "first_checkpoint_iteration": None,
                    "additive_v2": False,
                },
                "provenance": provenance,
                "provenance_basis": {
                    "partition_invariant": True,
                    "excludes": ["case_mpi_label", "mpi_size", "owner_local_counts", "rank_local_audit"],
                },
                "source_facts": {
                    **_jsonable(source_facts),
                    "name": source_name,
                    "formula": l2_source_formula(source_name),
                },
                "old_authorities": {
                    "old_l2_record_sha256": OLD_L2_RECORD_SHA,
                    "old_l2_one_apply_rho": OLD_L2_RHO,
                    "old_l2_classification": OLD_L2_CLASSIFICATION,
                    "old_k1_80_step": "FAIL",
                    "additive_v2": "CLOSED",
                },
                "pc_legality": aggregate_pc,
                "one_apply": {
                    "rho": float(one_apply_rho),
                    "rho_status": "diagnostic_only_not_a_gate",
                    "finite": bool(np.isfinite(one_apply_rho)),
                },
                "cycles": result["cycles"],
                "checkpoint_status": _checkpoint_status(result),
                "checkpoint_facts": result["checkpoint_facts"],
                "final": {
                    "iterations": int(result["iterations"]),
                    "reason": int(result["reason"]),
                    "explicit_true_residual": float(result["final_true_residual"]),
                    "finite": bool(all(bool(fact["final_finite"]) for fact in all_rank_facts)),
                },
                "rank_facts": all_rank_facts,
                "count_ranges": count_ranges,
                "production": {
                    "variant": VARIANT,
                    "high_order_global_aij": bool(
                        fixture_audit["high_order_global_aij"]
                        or hx_audit["high_order_aij"]
                    ),
                    "global_direct_coarse": bool(hx_audit["global_direct_coarse"]),
                    "global_numeric_allgather": bool(
                        fixture_audit["global_numeric_allgather"]
                        or hx_audit["global_numeric_allgather"]
                    ),
                    "global_dense_transfer": bool(
                        fixture_audit["global_transfer_matrix"]
                        or hx_audit["global_transfer_matrix"]
                    ),
                    "metadata_allgather": True,
                    "metadata_allgather_scope": "rank_runtime_cycle_scalar_and_artifact_facts_only",
                    "process_tree_resource_scope": "rank_root_diagnostic_excludes_launcher",
                },
                "forbidden": {
                    "additive_v2": False,
                    "high_order_global_aij": bool(
                        fixture_audit["high_order_global_aij"]
                        or hx_audit["high_order_aij"]
                    ),
                    "global_direct_coarse": bool(hx_audit["global_direct_coarse"]),
                    "global_numeric_allgather": bool(
                        fixture_audit["global_numeric_allgather"]
                        or hx_audit["global_numeric_allgather"]
                    ),
                    "global_dense_transfer": bool(
                        fixture_audit["global_transfer_matrix"]
                        or hx_audit["global_transfer_matrix"]
                    ),
                },
                "fixture_audit": fixture_audit,
                "hx_audit": hx_audit,
                "canonical_artifacts": artifacts,
                "status": "facts_written_no_worker_classification",
            }

        _closeout(comm, raw_dir, record_path, rank_fact, build_record)
        if comm.rank == 0:
            print(json.dumps({"record": str(record_path), "case": case, "source": source_name}, sort_keys=True), flush=True)
    finally:
        if result is not None:
            destroy_krylov_result(result)
            final_solution = None
        for vector in (final_true, final_action, final_solution, pc_action, pc_output, rhs, source_vector):
            if vector is not None:
                vector.destroy()
        if fixture is not None:
            fixture.destroy()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("p1",), required=True)
    parser.add_argument("--case", choices=tuple(CASES), required=True)
    parser.add_argument("--source", choices=SOURCES, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-mpi-size", type=int, required=True)
    args = parser.parse_args(argv)
    run_p1_worker(
        args.raw_dir,
        args.record,
        args.expected_source_sha,
        args.expected_mpi_size,
        args.case,
        args.source,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
