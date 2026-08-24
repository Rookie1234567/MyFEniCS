"""Thin P0 memory-first diagnostic worker.

The reusable cycle and checkpoint lifecycle lives in
``src.solvers.fullspace_memory_first_krylov``.  This historical benchmark
entry point only binds the frozen p2/h50 random case and the existing positive
fixture; it does not change the multiplicative-v1 production operator.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import hashlib
import json
import os
from pathlib import Path
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
from src.solvers.fullspace_lor_native_hx_fixture import RealL2PositiveHXFixture
from src.solvers.fullspace_memory_first_krylov import (
    read_solution_checkpoint,
    destroy_krylov_result,
    run_restart20_cycles,
    write_solution_checkpoint,
)


BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
SCHEMA = "task038.lor-native-complex-hx.memory-first-p0-record.v1"
CASE = "p2-mpi1"
SOURCE = "random"
DEGREE = 2
MESH_H_NM = 50.0
VARIANT = "sequential-v1"
MAX_IT = 40
RESIDUAL_LIMIT = 1.0e-8
PAIR_SMALL_MARGIN = 1.0e-11


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


def _identity_sha(payload: Any) -> str:
    return hashlib.sha256(_json_bytes(payload)).hexdigest()


def _vector_relative(left: Any, right: Any) -> float:
    difference = left.copy()
    difference.axpy(-1.0, right)
    numerator = float(difference.norm())
    denominator = max(float(right.norm()), np.finfo(float).tiny)
    difference.destroy()
    return numerator / denominator


def _scalar_relative(left: float, right: float) -> float:
    return abs(float(left) - float(right)) / max(abs(float(right)), np.finfo(float).tiny)


def _checkpoint_expected(
    provenance: Mapping[str, Any],
    *,
    iteration: int,
    explicit_true_residual: float,
    manifest_sha256: str,
    mpi_size: int,
) -> dict[str, Any]:
    return {
        "iteration": int(iteration),
        "explicit_true_residual": float(explicit_true_residual),
        "input_identity_sha256": str(provenance["input_identity_sha256"]),
        "operator_identity_sha256": str(provenance["operator_identity_sha256"]),
        "physical_model_sha256": str(provenance["physical_model_sha256"]),
        "source_sha": str(provenance["source_sha"]),
        "mpi_size": int(mpi_size),
        "manifest_sha256": str(manifest_sha256),
    }


def _fixture_provenance(
    fixture: Any, source_facts: Mapping[str, Any], source_sha: str
) -> dict[str, str]:
    input_identity = _identity_sha(
        {
            "case": CASE,
            "degree": DEGREE,
            "h_nm": MESH_H_NM,
            "source": SOURCE,
            "source_formula": source_facts["formula"],
            "role": "fullspace_primal_source",
        }
    )
    operator_identity = _identity_sha(
        {
            "degree": DEGREE,
            "variant": VARIANT,
            "role": "matrix_free_positive_B_h",
            "high_action_audit": fixture.high_action.audit,
            "hx_audit": fixture.hx.audit,
        }
    )
    physical_identity = _identity_sha(
        {
            "role": "positive_auxiliary_model",
            "degree": DEGREE,
            "h_nm": MESH_H_NM,
            "piecewise_coefficients": fixture.audit["piecewise_coefficients"],
        }
    )
    return {
        "source_sha": str(source_sha),
        "input_identity_sha256": input_identity,
        "operator_identity_sha256": operator_identity,
        "physical_model_sha256": physical_identity,
    }


def _resource_sample() -> dict[str, Any]:
    authority = resource_authority_sample(os.getpid())
    process_tree = authority["process_tree"]
    cgroup = authority["job_cgroup"]
    dedicated = bool(cgroup["dedicated_job_cgroup"])
    return {
        "scope": "process_tree_and_dedicated_cgroup_when_available",
        "root_pid": int(process_tree["root_pid"]),
        "process_tree_rss_bytes": int(process_tree["rss_bytes"]),
        "process_tree_swap_bytes": int(process_tree["swap_bytes"]),
        "all_status_readable": bool(process_tree["all_status_readable"]),
        "dedicated_cgroup_observed": dedicated,
        "dedicated_cgroup_path": cgroup.get("path"),
        "dedicated_cgroup_readable": bool(cgroup.get("readable")),
        "dedicated_cgroup_swap_bytes": (
            cgroup.get("swap_current_bytes") if dedicated else None
        ),
        "memory_authority_bytes": int(authority["memory_authority_bytes"]),
        "job_no_swap": bool(authority["job_no_swap"]),
        "resource_authority": "task034.resource_authority_sample",
    }


def _ownership(vector: Any, rank: int) -> dict[str, Any]:
    start, stop = vector.getOwnershipRange()
    return {
        "rank": int(rank),
        "ownership_range": [int(start), int(stop)],
        "local_size": int(vector.getLocalSize()),
        "global_size": int(vector.getSize()),
    }


def _save_sharded_vector(
    raw_dir: Path, name: str, vector: Any, comm: MPI.Comm
) -> dict[str, Any]:
    values = np.asarray(vector.getArray(readonly=True), dtype=np.complex128).copy()
    path = raw_dir / f"{name}.rank{comm.rank}.npy"
    np.save(path, values, allow_pickle=False)
    local = {
        "rank": int(comm.rank),
        "relative_path": path.name,
        "bytes": int(path.stat().st_size),
        "sha256": _sha256(path),
        "dtype": str(values.dtype),
        "shape": list(values.shape),
        "ownership": _ownership(vector, comm.rank),
    }
    facts = comm.allgather(local)
    return {
        "name": name,
        "role": name,
        "root": str(raw_dir.resolve()),
        "shards": sorted(facts, key=lambda item: item["rank"]),
    }


def _resource_allranks(comm: MPI.Comm) -> dict[str, Any]:
    local = _resource_sample()
    return {
        **local,
        "rank_max_process_tree_rss_bytes": int(
            comm.allreduce(local["process_tree_rss_bytes"], op=MPI.MAX)
        ),
        "rank_max_process_tree_swap_bytes": int(
            comm.allreduce(local["process_tree_swap_bytes"], op=MPI.MAX)
        ),
    }


def _global_finite(comm: MPI.Comm, *vectors: Any) -> bool:
    local = all(
        bool(np.all(np.isfinite(vector.getArray(readonly=True))))
        for vector in vectors
    )
    return bool(comm.allreduce(int(local), op=MPI.MIN))


def _pc_legality(
    fixture: Any, residual: Any, raw_dir: Path, comm: MPI.Comm
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Measure one fixed two-direction legality probe of multiplicative-v1."""

    start, stop = residual.getOwnershipRange()
    global_rows = np.arange(int(start), int(stop), dtype=np.int64)
    first = residual.copy()
    second = residual.copy()
    first.array[global_rows % 2 != 0] = 0.0 + 0.0j
    second.array[global_rows % 2 == 0] = 0.0 + 0.0j
    alpha = 0.375 + 0.125j
    beta = -0.25 + 0.5j
    combined = first.copy()
    combined.scale(alpha)
    combined.axpy(beta, second)
    before = {
        "first": first.copy(),
        "second": second.copy(),
        "combined": combined.copy(),
    }
    first_output = fixture.apply_high_preconditioner(first)
    second_output = fixture.apply_high_preconditioner(second)
    combined_output = fixture.apply_high_preconditioner(combined)
    repeat_output = fixture.apply_high_preconditioner(combined)
    after = {
        "first": first.copy(),
        "second": second.copy(),
        "combined": combined.copy(),
    }
    expected = first_output.copy()
    expected.scale(alpha)
    expected.axpy(beta, second_output)
    slave_rows = np.asarray(fixture.high_floquet.mpc.slaves, dtype=np.int32)
    if slave_rows.size == 0 or np.any(slave_rows >= combined_output.getLocalSize()):
        raise RuntimeError("high-space slave row metadata is incomplete")
    local_slave_max = float(
        np.max(np.abs(combined_output.array[slave_rows]), initial=0.0)
    )
    slave_constraint = float(comm.allreduce(local_slave_max, op=MPI.MAX))
    artifacts = {
        "input_first_before": _save_sharded_vector(
            raw_dir, "input_first_before", before["first"], comm
        ),
        "input_first_after": _save_sharded_vector(
            raw_dir, "input_first_after", after["first"], comm
        ),
        "input_second_before": _save_sharded_vector(
            raw_dir, "input_second_before", before["second"], comm
        ),
        "input_second_after": _save_sharded_vector(
            raw_dir, "input_second_after", after["second"], comm
        ),
        "input_combined_before": _save_sharded_vector(
            raw_dir, "input_combined_before", before["combined"], comm
        ),
        "input_combined_after": _save_sharded_vector(
            raw_dir, "input_combined_after", after["combined"], comm
        ),
        "output_first": _save_sharded_vector(
            raw_dir, "output_first", first_output, comm
        ),
        "output_second": _save_sharded_vector(
            raw_dir, "output_second", second_output, comm
        ),
        "output_combined": _save_sharded_vector(
            raw_dir, "output_combined", combined_output, comm
        ),
        "output_repeat": _save_sharded_vector(
            raw_dir, "output_repeat", repeat_output, comm
        ),
    }
    facts = {
        "direction_construction": "PETSc_global_row_parity",
        "alpha": [float(alpha.real), float(alpha.imag)],
        "beta": [float(beta.real), float(beta.imag)],
        "first_global_norm": float(first.norm()),
        "second_global_norm": float(second.norm()),
        "combined_global_norm": float(combined.norm()),
        "linearity_relative": _vector_relative(combined_output, expected),
        "repeat_relative": _vector_relative(repeat_output, combined_output),
        "input_unchanged_relative": max(
            _vector_relative(after[name], before[name])
            for name in before
        ),
        "finite": _global_finite(
            comm, first, second, combined, first_output, second_output, combined_output, repeat_output
        ),
        "slave_constraint_absolute": slave_constraint,
        "slave_local_indices": [int(value) for value in slave_rows],
        "slave_master_complete": bool(fixture.audit["slave_master_complete"]),
        "phase_application": str(fixture.audit["phase_application"]),
        "high_order_global_aij": bool(
            fixture.audit["high_order_global_aij"]
            or fixture.hx.audit["high_order_aij"]
        ),
        "global_direct_coarse": bool(fixture.hx.audit["global_direct_coarse"]),
        "numeric_allgather": bool(
            fixture.audit["global_numeric_allgather"]
            or fixture.hx.audit["global_numeric_allgather"]
        ),
        "artifact_names": sorted(artifacts),
    }
    for vector in (*before.values(), *after.values(), first_output, second_output, combined_output, repeat_output, expected, first, second, combined):
        vector.destroy()
    return facts, artifacts


def _checkpoint_callback(
    raw_dir: Path,
    comm: MPI.Comm,
    provenance: Mapping[str, Any],
):
    def write(
        iteration: int, solution: Any, explicit_true_residual: float
    ) -> Mapping[str, Any]:
        before = solution.copy()
        try:
            info = write_solution_checkpoint(
                raw_dir / f"checkpoint-{int(iteration)}",
                solution,
                iteration=iteration,
                explicit_true_residual=explicit_true_residual,
                input_identity_sha256=str(provenance["input_identity_sha256"]),
                operator_identity_sha256=str(provenance["operator_identity_sha256"]),
                physical_model_sha256=str(provenance["physical_model_sha256"]),
                source_sha=str(provenance["source_sha"]),
                ownership=_ownership(solution, comm.rank),
                comm=comm,
            )
            restored = solution.duplicate()
            try:
                read_solution_checkpoint(
                    raw_dir / f"checkpoint-{int(iteration)}",
                    restored,
                    expected=_checkpoint_expected(
                        provenance,
                        iteration=int(iteration),
                        explicit_true_residual=float(explicit_true_residual),
                        manifest_sha256=str(info["manifest_sha256"]),
                        mpi_size=int(comm.Get_size()),
                    ),
                    ownership=_ownership(restored, comm.rank),
                    comm=comm,
                )
                roundtrip = _vector_relative(restored, before)
                roundtrip = float(comm.allreduce(roundtrip, op=MPI.MAX))
            finally:
                restored.destroy()
            return {**info, "roundtrip_relative": roundtrip}
        finally:
            before.destroy()

    return write


def _run_outer(
    fixture: Any,
    residual: Any,
    raw_dir: Path,
    comm: MPI.Comm,
    provenance: Mapping[str, Any],
) -> dict[str, Any]:
    def scalar_result(result: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "settings": dict(result["settings"]),
            "initial_true_residual": float(result["initial_true_residual"]),
            "cycles": list(result["cycles"]),
            "iterations": int(result["iterations"]),
            "reason": int(result["reason"]),
            "final_true_residual": float(result["final_true_residual"]),
            "matvec_count": int(result["matvec_count"]),
            "pc_apply_count": int(result["pc_apply_count"]),
            "ksp_destroy_count": int(result["ksp_destroy_count"]),
            "explicit_action_count": int(result["explicit_action_count"]),
            "elapsed_seconds": float(result["elapsed_seconds"]),
        }

    checkpoint_writer = _checkpoint_callback(raw_dir, comm, provenance)
    first = run_restart20_cycles(
        residual,
        fixture.apply_high_action_copy,
        fixture.apply_high_preconditioner,
        max_it=20,
        start_iteration=0,
        residual_limit=RESIDUAL_LIMIT,
        resource_sample=lambda: _resource_allranks(comm),
        checkpoint_writer=checkpoint_writer,
    )
    first_facts = scalar_result(first)
    checkpoints = list(first["checkpoint_facts"])
    if len(checkpoints) != 1 or int(checkpoints[0]["iteration"]) != 20:
        destroy_krylov_result(first)
        fixture.destroy()
        raise RuntimeError("the first cycle must produce exactly one iteration-20 checkpoint")
    checkpoint = dict(checkpoints[0])
    boundary_residual = float(first["final_true_residual"])
    if not np.isclose(
        float(checkpoint["explicit_true_residual"]),
        boundary_residual,
        rtol=1.0e-14,
        atol=1.0e-15,
    ):
        destroy_krylov_result(first)
        fixture.destroy()
        raise RuntimeError("checkpoint residual does not match cycle-20 boundary")
    x20_reference = first.pop("final_solution")
    destroy_krylov_result(first)
    fixture.destroy()

    resumed_fixture = RealL2PositiveHXFixture(DEGREE, comm, variant=VARIANT)
    resumed_source, resumed_source_facts = resumed_fixture.build_l2_source(SOURCE)
    resumed_rhs = resumed_fixture.apply_high_action_copy(resumed_source)
    resumed_solution = resumed_rhs.duplicate()
    rebuilt_provenance: dict[str, Any]
    try:
        resumed_provenance = _fixture_provenance(
            resumed_fixture, resumed_source_facts, str(provenance["source_sha"])
        )
        if resumed_provenance != dict(provenance):
            raise RuntimeError("rebuilt fixture provenance differs from the first fixture")
        read_solution_checkpoint(
            raw_dir / "checkpoint-20",
            resumed_solution,
            expected=_checkpoint_expected(
                resumed_provenance,
                iteration=20,
                explicit_true_residual=float(checkpoint["explicit_true_residual"]),
                manifest_sha256=str(checkpoint["manifest_sha256"]),
                mpi_size=int(comm.Get_size()),
            ),
            ownership=_ownership(resumed_solution, comm.rank),
            comm=comm,
        )
        rebuilt_provenance = dict(resumed_provenance)
        post_rebuild_roundtrip = float(
            comm.allreduce(
                _vector_relative(resumed_solution, x20_reference), op=MPI.MAX
            )
        )
        restarted = run_restart20_cycles(
            resumed_rhs,
            resumed_fixture.apply_high_action_copy,
            resumed_fixture.apply_high_preconditioner,
            max_it=40,
            start_iteration=20,
            initial_solution=resumed_solution,
            residual_limit=RESIDUAL_LIMIT,
            resource_sample=lambda: _resource_allranks(comm),
        )
        restart_facts = scalar_result(restarted)
        restart_boundary_relative = _scalar_relative(
            boundary_residual, restarted["initial_true_residual"]
        )
        restarted_first = (
            float(restarted["cycles"][0]["explicit_true_residual"])
            if restarted["cycles"]
            else None
        )
        destroy_krylov_result(restarted)
    finally:
        x20_reference.destroy()
        resumed_solution.destroy()
        resumed_rhs.destroy()
        resumed_source.destroy()
        resumed_fixture.destroy()

    reference_fixture = RealL2PositiveHXFixture(DEGREE, comm, variant=VARIANT)
    reference_source, _ = reference_fixture.build_l2_source(SOURCE)
    reference_rhs = reference_fixture.apply_high_action_copy(reference_source)
    try:
        continuous = run_restart20_cycles(
            reference_rhs,
            reference_fixture.apply_high_action_copy,
            reference_fixture.apply_high_preconditioner,
            max_it=40,
            start_iteration=0,
            residual_limit=RESIDUAL_LIMIT,
            resource_sample=lambda: _resource_allranks(comm),
            stop_on_true_residual=False,
        )
        continuous_facts = scalar_result(continuous)
        continuous_second = (
            float(continuous["cycles"][1]["explicit_true_residual"])
            if len(continuous["cycles"]) >= 2
            else None
        )
        next_cycle_relative = (
            None
            if restarted_first is None or continuous_second is None
            else _scalar_relative(restarted_first, continuous_second)
        )
        destroy_krylov_result(continuous)
    finally:
        reference_rhs.destroy()
        reference_source.destroy()
        reference_fixture.destroy()

    return {
        "production_first_cycle": first_facts,
        "restart": restart_facts,
        "continuous_reference": continuous_facts,
        "checkpoint": checkpoint,
        "boundary_true_residual": boundary_residual,
        "restart_boundary_true_residual_relative": restart_boundary_relative,
        "post_rebuild_solution_roundtrip_relative": post_rebuild_roundtrip,
        "rebuilt_provenance": rebuilt_provenance,
        "next_cycle_first_true_residual_relative": next_cycle_relative,
        "pair_bound_inputs": {
            "rho_one": boundary_residual,
            "rho_two": float(restart_facts["final_true_residual"]),
            "rhs_identity": float(restart_boundary_relative),
            "small_margin": PAIR_SMALL_MARGIN,
        },
    }


def _closeout(
    comm: MPI.Comm,
    raw_dir: Path,
    record_path: Path,
    record: dict[str, Any],
    rank_fact: dict[str, Any],
) -> None:
    _append_stage_marker(raw_dir, "rank_metadata_collect_enter", comm.rank)
    rank_facts = comm.allgather(rank_fact)
    _append_stage_marker(raw_dir, "rank_metadata_collect_exit", comm.rank)
    error: str | None = None
    if comm.rank == 0:
        try:
            _append_stage_marker(raw_dir, "record_build_begin", comm.rank)
            record["rank_facts"] = rank_facts
            _append_stage_marker(raw_dir, "record_build_end", comm.rank)
            _append_stage_marker(raw_dir, "record_encode_begin", comm.rank)
            payload = _json_bytes(record)
            _append_stage_marker(raw_dir, "record_encode_end", comm.rank)
            _append_stage_marker(raw_dir, "record_write_begin", comm.rank)
            record_path.write_bytes(payload)
            _append_stage_marker(raw_dir, "record_write_end", comm.rank)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
    error = comm.bcast(error, root=0)
    if error is not None:
        raise RuntimeError(f"record closeout failed: {error}")
    _append_stage_marker(raw_dir, "record_written", comm.rank)
    comm.barrier()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-mpi-size", type=int, required=True)
    args = parser.parse_args(argv)
    comm = MPI.COMM_WORLD
    root = Path(__file__).resolve().parents[1]
    if args.stage != "p0" or args.case != CASE or args.expected_mpi_size != 1:
        raise ValueError("the prepared P0 entry point is exactly p2/h50 random MPI1")
    _prepare_paths(args.raw_dir, args.record, comm, stage="p0")
    _append_stage_marker(args.raw_dir, "paths_ready", comm.rank)
    source = None
    if comm.rank == 0:
        source = _source_identity(root, args.expected_source_sha)
    source = comm.bcast(source, root=0)
    runtime = _runtime_identity(root, args.expected_mpi_size)
    _append_stage_marker(args.raw_dir, "source_identity_closed", comm.rank)
    _append_stage_marker(args.raw_dir, "runtime_identity", comm.rank)
    fixture = None
    primal_source = None
    residual = None
    try:
        fixture = RealL2PositiveHXFixture(DEGREE, comm, variant=VARIANT)
        _append_stage_marker(args.raw_dir, "fixture_built", comm.rank)
        primal_source, source_facts = fixture.build_l2_source(SOURCE)
        residual = fixture.apply_high_action_copy(primal_source)
        _append_stage_marker(args.raw_dir, "source_and_residual_built", comm.rank)
        provenance = _fixture_provenance(
            fixture, source_facts, str(source["expected_sha"])
        )
        artifacts = {
            "source": _save_sharded_vector(args.raw_dir, "source", primal_source, comm),
            "residual": _save_sharded_vector(args.raw_dir, "residual", residual, comm),
        }
        pc_legality, pc_artifacts = _pc_legality(
            fixture, residual, args.raw_dir, comm
        )
        artifacts.update(pc_artifacts)
        fixture_audit = {
            **_jsonable(fixture.audit),
            "hx_audit": _jsonable(fixture.hx.audit),
        }
        _append_stage_marker(args.raw_dir, "production_apply_ready", comm.rank)
        outer = _run_outer(fixture, residual, args.raw_dir, comm, provenance)
        fixture = None
        _append_stage_marker(args.raw_dir, "outer_cycles_complete", comm.rank)
        source_end = None
        source_end_error: str | None = None
        if comm.rank == 0:
            try:
                source_end = _source_identity(root, str(source["expected_sha"]))
            except Exception as exc:
                source_end_error = f"{type(exc).__name__}: {exc}"
        source_end_error = comm.bcast(source_end_error, root=0)
        if source_end_error is not None:
            raise RuntimeError(f"source closeout probe failed: {source_end_error}")
        source_end = comm.bcast(source_end, root=0)
        if not isinstance(source_end, dict):
            raise RuntimeError("source closeout probe returned no identity")
        source["commit_sha_end"] = str(source_end["commit_sha_end"])
        source["tracked_status_end"] = str(source_end["tracked_status_end"])
        source["clean_end"] = bool(source_end["clean_end"])
        _append_stage_marker(args.raw_dir, "source_identity_end_closed", comm.rank)
        record = {
            "schema": SCHEMA,
            "stage": "p0",
            "case": CASE,
            "degree": DEGREE,
            "h_nm": MESH_H_NM,
            "source_name": SOURCE,
            "source": source,
            "runtime": runtime,
            "raw_dir": str(args.raw_dir.resolve()),
            "settings": {
                "variant": VARIANT,
                "restart": 20,
                "cycle_max_it": 20,
                "max_it": MAX_IT,
                "right_preconditioned": True,
                "norm_type": "unpreconditioned",
                "residual_replacement": True,
                "additive_v2": False,
            },
            "provenance": provenance,
            "source_facts": source_facts,
            "fixture_audit": fixture_audit,
            "pc_legality": pc_legality,
            "artifacts": artifacts,
            "outer": outer,
            "old_authorities": {
                "old_l2_one_apply_rho": 1.7348663090876784,
                "old_l2_classification": "CONTROLLED_NEGATIVE_BY_POSITIVE_AUXILIARY_CONTRACTION_GATE",
                "old_k1_v1_80_step": "FAIL",
                "additive_v2": "CLOSED",
            },
            "worker_status": "completed_facts_only",
        }
        rank_fact = {
            "rank": int(comm.rank),
            "runtime": runtime,
            "explicit_action_count": int(
                outer["production_first_cycle"]["explicit_action_count"]
            ),
            "matvec_count": int(outer["production_first_cycle"]["matvec_count"]),
            "pc_apply_count": int(outer["production_first_cycle"]["pc_apply_count"]),
            "resource": _resource_sample(),
        }
        _closeout(comm, args.raw_dir, args.record, record, rank_fact)
        return 0
    finally:
        if residual is not None:
            residual.destroy()
        if primal_source is not None:
            primal_source.destroy()
        if fixture is not None:
            fixture.destroy()


if __name__ == "__main__":
    raise SystemExit(main())
