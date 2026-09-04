"""Thin V17 parent/worker orchestration for the two diagnostic oracles.

The parent owns the cold JIT cache and process-tree resource record.  Oracle A
uses three sequential children; Oracle B uses one child that runs the restart
and unrestarted comparisons in order.  PETSc, MPI, and DOLFINx are imported
only by the worker entry points.
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

from benchmarks import run_task038_full3d_physical_pcoarse_q1 as authority_runner


BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
MODULE = "benchmarks.run_task038_v17_oracles"
PHASES = ("oracle-a", "oracle-b")
ORACLE_A_STAGES = ("A1", "A2", "A3")
ORACLE_B_STAGES = ("B",)
JIT_GROUPS = authority_runner.JIT_GROUPS
EXPECTED_MPI_SIZES = (1, 2)
SOURCE_SHA = "be67787d1237e8676b33f91f28c7b0ffcb3fe06a"
INPUT_SHA256 = "819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41"
PHYSICAL_MODEL_SHA256 = (
    "9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"
)
MODE_MANIFEST_SHA256 = (
    "dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2"
)
CHECKPOINT_DIR = Path(
    "benchmarks/artifacts/task038_extra_full3d_iterative_0p7nm/"
    "j5_full_cold_staged_v3/ee5920b9fa977a39fea7bc09cfbe155303acdb2d/"
    "checkpoints/checkpoint-1000"
)
CHECKPOINT_MANIFEST_SHA256 = (
    "7f7d6fd29e6a3d6130de439fa510a19c6830061f59090cfd9f6ee4c51d8eb139"
)
CHECKPOINT_SOLUTION_SHA256 = (
    "00f55e5256e673687942f79d98398d0fd2524d6d956c3b7ef5264615ab2c659b"
)
CHECKPOINT_SOURCE_SHA = "ee5920b9fa977a39fea7bc09cfbe155303acdb2d"
CHECKPOINT_INPUT_IDENTITY_SHA256 = (
    "754dbf810cc38b32804bced03b8d4b8f702d5943671724e7529f47cadefe8b1f"
)
CHECKPOINT_OPERATOR_IDENTITY_SHA256 = (
    "bbe5737b41b56c9dddb0c0ae3e0dd0384197dc22dd2faf41a2c57cc781f0a6f3"
)
CHECKPOINT_EXPLICIT_RESIDUAL = 0.4837947981092168
CHECKPOINT_PHYSICAL_MODEL_SHA256 = PHYSICAL_MODEL_SHA256
ORACLE_A_WARNING_BYTES = 10_000_000_000
ORACLE_A_HARD_BYTES = 12_000_000_000
ORACLE_B_WARNING_BYTES = 1_800_000_000
ORACLE_B_HARD_BYTES = 2_000_000_000
ORACLE_B_STEPS = 500
ORACLE_B_START_ITERATION = 1000
ORACLE_B_CHECKPOINT_INTERVAL = 20
ORACLE_B_DISK_FREE_BYTES = 10_000_000_000
MARKER_SCHEMA = "task038.v17.oracle.marker.v1"
PARENT_SCHEMA = "task038.v17.oracle.parent.v1"
WORKER_SCHEMA = "task038.v17.oracle.worker.v1"
REPO_ROOT = authority_runner.REPO_ROOT


def _absolute(value: Path | str) -> Path:
    return Path(os.path.abspath(os.fspath(value)))


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    if hasattr(value, "item"):
        return _jsonable(value.item())
    return value


def _write_json(path: Path, value: Any) -> None:
    authority_runner._write_json(path, _jsonable(value))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _write_array(raw_dir: Path, relative: str, values: Any) -> dict[str, Any]:
    import numpy as np

    path = raw_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    array = np.asarray(values, dtype=np.complex128)
    if array.ndim != 1 or not np.all(np.isfinite(array)):
        raise ValueError("oracle vector must be a finite one-dimensional array")
    with path.open("xb") as stream:
        np.save(stream, array, allow_pickle=False)
        stream.flush()
        os.fsync(stream.fileno())
    return {
        "relative_path": str(path.relative_to(raw_dir.parent)),
        "bytes": int(path.stat().st_size),
        "sha256": _sha256(path),
        "array_sha256": hashlib.sha256(
            memoryview(np.ascontiguousarray(array)).cast("B")
        ).hexdigest(),
        "dtype": "complex128",
        "shape": [int(array.size)],
        "norm": float(np.linalg.norm(array)),
        "finite": True,
    }


def _read_array(raw_dir: Path, descriptor: dict[str, Any]) -> Any:
    import numpy as np

    path = (raw_dir.parent / str(descriptor["relative_path"])).resolve()
    if raw_dir.parent.resolve() not in path.parents or not path.is_file():
        raise FileNotFoundError(f"oracle vector is outside raw root: {path}")
    if _sha256(path) != descriptor.get("sha256"):
        raise ValueError(f"oracle vector SHA mismatch: {path.name}")
    values = np.asarray(np.load(path, allow_pickle=False))
    if (
        values.dtype != np.dtype(np.complex128)
        or values.ndim != 1
        or list(values.shape) != list(descriptor.get("shape", ()))
        or not np.all(np.isfinite(values))
    ):
        raise ValueError(f"oracle vector descriptor mismatch: {path.name}")
    return values


def _marker_order(phase: str) -> tuple[str, ...]:
    if phase == "oracle-a":
        return (
            "paths_ready",
            "abi_ready",
            "A1_complete",
            "A2_complete",
            "A3_complete",
            "record_written",
            "release_complete",
        )
    return (
        "paths_ready",
        "abi_ready",
        "reference_complete",
        "unrestarted_complete",
        "record_written",
        "release_complete",
    )


def _worker_marker(
    comm: Any,
    marker_dir: Path,
    phase: str,
    name: str,
    source_sha: str,
    **facts: Any,
) -> None:
    order = _marker_order(phase)
    if int(comm.rank) == 0:
        existing = authority_runner.marker_files(marker_dir, order=order)
        existing_names = {
            path.stem.split("_", 1)[1] for path in existing
        }
        if name not in existing_names:
            authority_runner.write_marker(
                marker_dir,
                name,
                {
                    "phase": phase,
                    "source_sha": source_sha,
                    "mpi_size": int(comm.size),
                    **_jsonable(facts),
                },
                order=order,
                schema=MARKER_SCHEMA,
            )
    comm.barrier()


def _prepare_stage_paths(root: Path, comm: Any) -> tuple[Path, Path]:
    error = None
    if int(comm.rank) == 0:
        try:
            if not root.is_dir():
                raise FileNotFoundError(f"oracle root is missing: {root}")
            (root / "raw").mkdir(exist_ok=True)
            (root / "markers").mkdir(exist_ok=True)
        except OSError as exc:
            error = f"{type(exc).__name__}: {exc}"
    error = comm.bcast(error, root=0)
    if error is not None:
        raise RuntimeError(error)
    comm.barrier()
    return root / "raw", root / "markers"


def _checkpoint_expected() -> dict[str, Any]:
    return {
        "iteration": 1000,
        "explicit_true_residual": CHECKPOINT_EXPLICIT_RESIDUAL,
        "input_identity_sha256": CHECKPOINT_INPUT_IDENTITY_SHA256,
        "operator_identity_sha256": CHECKPOINT_OPERATOR_IDENTITY_SHA256,
        "physical_model_sha256": CHECKPOINT_PHYSICAL_MODEL_SHA256,
        "source_sha": CHECKPOINT_SOURCE_SHA,
        "mpi_size": 1,
        "manifest_sha256": CHECKPOINT_MANIFEST_SHA256,
    }


def _ownership(vector: Any, comm: Any) -> dict[str, Any]:
    start, stop = vector.getOwnershipRange()
    return {
        "rank": int(comm.rank),
        "ownership_range": [int(start), int(stop)],
        "local_size": int(vector.getLocalSize()),
        "global_size": int(vector.getSize()),
    }


def _space_vector(levels: dict[str, Any], degree: int) -> Any:
    from dolfinx.la.petsc import create_vector

    space = levels["spaces"][int(degree)]
    return create_vector(
        [(space.dofmap.index_map, int(space.dofmap.index_map_bs))]
    )


def _vector_facts(vector: Any) -> dict[str, Any]:
    import numpy as np

    values = np.asarray(vector.getArray(readonly=True), dtype=np.complex128)
    norm = float(vector.norm())
    return {
        "norm": norm,
        "finite": bool(np.all(np.isfinite(values)) and np.isfinite(norm)),
        "local_size": int(values.size),
        "array_sha256": hashlib.sha256(
            memoryview(np.ascontiguousarray(values)).cast("B")
        ).hexdigest(),
    }


def _owned_vector_facts(vector: Any, mpc: Any, comm: Any) -> dict[str, Any]:
    return authority_runner._owned_slave_facts(vector, mpc, comm)


def _compact_vector_facts(facts: dict[str, Any]) -> dict[str, Any]:
    return {
        key: facts[key]
        for key in ("norm", "finite", "owned_slave_max", "owned_slave_count")
        if key in facts
    }


def _canonical_key_inventory_hash(packets: Any) -> str:
    from benchmarks.canonical_vector_artifacts import canonical_key_json_bytes

    digest = hashlib.sha256()
    for encoded in sorted(
        canonical_key_json_bytes(key) for key, _value in packets
    ):
        digest.update(encoded)
        digest.update(b"\n")
    return digest.hexdigest()


def _write_canonical_vector_manifest(
    raw_dir: Path,
    name: str,
    role: str,
    space: Any,
    floquet: Any,
    vector: Any,
    comm: Any,
) -> dict[str, Any]:
    from benchmarks.canonical_vector_artifacts import (
        canonical_shard_manifest,
        write_canonical_manifest,
        write_canonical_packet_shard,
    )
    from src.solvers.hcurl_canonical_vector_dolfinx import (
        extract_canonical_full_fe_dual_packets,
        extract_canonical_full_fe_packets,
    )

    if role == "full_fe_dual":
        packets, audit = extract_canonical_full_fe_dual_packets(
            space, floquet.mpc, vector
        )
    elif role == "full_fe":
        packets, audit = extract_canonical_full_fe_packets(
            space, vector, floquet
        )
    else:
        raise ValueError(f"unsupported canonical vector role: {role}")
    extractor_audit = {
        **_jsonable(dict(audit)),
        "numeric_allgather": False,
    }

    canonical_dir = raw_dir / "canonical"
    if int(comm.rank) == 0:
        canonical_dir.mkdir(parents=True, exist_ok=True)
    comm.barrier()
    shard_path = canonical_dir / f"{name}.rank{int(comm.rank):04d}.jsonl"
    shard = write_canonical_packet_shard(
        shard_path, packets, audit_packets=True
    )
    shard.update(
        {
            "rank": int(comm.rank),
            "key_inventory_sha256": _canonical_key_inventory_hash(packets),
        }
    )
    gathered = comm.gather(shard, root=0)
    descriptor = None
    if int(comm.rank) == 0:
        manifest = canonical_shard_manifest(
            role=role,
            mpi_size=int(comm.size),
            shard_metadata=gathered,
            extractor_audit=extractor_audit,
        )
        manifest["key_inventory_sha256"] = hashlib.sha256(
            json.dumps(
                [
                    {
                        "rank": int(item["rank"]),
                        "key_inventory_sha256": item["key_inventory_sha256"],
                    }
                    for item in gathered
                ],
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        manifest_path = canonical_dir / f"{name}.manifest.json"
        manifest_sha = write_canonical_manifest(manifest_path, manifest)
        descriptor = {
            "manifest_relative_path": str(
                manifest_path.relative_to(raw_dir.parent)
            ),
            "manifest_sha256": manifest_sha,
            "role": role,
            "packet_count": int(manifest["global_summed_packet_count"]),
            "key_inventory_sha256": manifest["key_inventory_sha256"],
            "extractor_audit": extractor_audit,
            "mpi_size": int(comm.size),
        }
    return comm.bcast(descriptor, root=0)


def _write_stage_record(raw_dir: Path, stage: str, record: dict[str, Any]) -> Path:
    path = raw_dir / f"{stage}_record.json"
    _write_json(path, record)
    return path


def _stage_source(root: Path, source_sha: str, input_path: Path) -> dict[str, Any]:
    return {
        **authority_runner._source_facts(REPO_ROOT, source_sha, input_path),
        "physical_model_sha256": PHYSICAL_MODEL_SHA256,
        "mode_manifest_sha256": MODE_MANIFEST_SHA256,
    }


def _run_a1(
    root: Path,
    raw_dir: Path,
    marker_dir: Path,
    source_sha: str,
    input_path: Path,
    comm: Any,
) -> None:
    import numpy as np

    from benchmarks.run_task038_full3d_r3 import _current_input
    from src.solvers.fullspace_memory_first_krylov import read_solution_checkpoint
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        build_physical_rhs,
        build_same_mesh_physical_action,
        destroy_same_mesh_physical_action,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_runtime import (
        build_same_mesh_hcurl_owner_transfer,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg import (
        build_same_mesh_hcurl_transfer,
    )

    if int(comm.size) != 1:
        raise ValueError("Oracle A is currently fixed to MPI1")
    _spec, cfg, _resolved, input_facts = _current_input(REPO_ROOT, input_path)
    input_facts = {**input_facts, "mode_manifest_sha256": MODE_MANIFEST_SHA256}
    levels = _build_same_mesh_levels(
        cfg, comm, (6, 3), include_positive_coefficients=False
    )
    owner_transfer = build_same_mesh_hcurl_owner_transfer(
        levels["spaces"][6],
        levels["floquets"][6],
        levels["spaces"][3],
        levels["floquets"][3],
        local_transfer=build_same_mesh_hcurl_transfer(6, 3),
    )
    levels["p63_owner_transfer"] = owner_transfer
    bundle = None
    solution = rhs = action = residual = r3 = None
    try:
        bundle = build_same_mesh_physical_action(levels, cfg, 6)
        solution = _space_vector(levels, 6)
        p6_mpc = levels["floquets"][6].mpc
        p3_mpc = levels["floquets"][3].mpc
        checkpoint_expected = _checkpoint_expected()
        checkpoint = read_solution_checkpoint(
            CHECKPOINT_DIR,
            solution,
            expected=checkpoint_expected,
            ownership=_ownership(solution, comm),
            comm=comm,
        )
        solution_facts_before = _owned_vector_facts(solution, p6_mpc, comm)
        rhs, rhs_facts = build_physical_rhs(bundle)
        rhs_facts = {
            **rhs_facts,
            **_owned_vector_facts(rhs, p6_mpc, comm),
        }
        rhs_facts_before = dict(rhs_facts)
        action = _space_vector(levels, 6)
        bundle["physical_action"].apply(solution, action)
        residual = rhs.copy()
        residual.axpy(-1.0, action)
        solution_facts_after = _owned_vector_facts(solution, p6_mpc, comm)
        rhs_facts_after = _owned_vector_facts(rhs, p6_mpc, comm)
        r3 = _space_vector(levels, 3)
        owner_transfer.apply_adjoint_into(residual, r3)
        r6_facts = _owned_vector_facts(residual, p6_mpc, comm)
        r3_facts = _owned_vector_facts(r3, p3_mpc, comm)
        r6_descriptor = _write_array(raw_dir, "A1/r6.npy", residual.array)
        r3_descriptor = _write_array(raw_dir, "A1/r3.npy", r3.array)
        r6_canonical = _write_canonical_vector_manifest(
            raw_dir,
            "A1_r6",
            "full_fe_dual",
            levels["spaces"][6],
            levels["floquets"][6],
            residual,
            comm,
        )
        r3_canonical = _write_canonical_vector_manifest(
            raw_dir,
            "A1_r3",
            "full_fe_dual",
            levels["spaces"][3],
            levels["floquets"][3],
            r3,
            comm,
        )
        r6_facts.update(r6_descriptor)
        r6_facts["canonical"] = r6_canonical
        r3_facts.update(r3_descriptor)
        r3_facts["canonical"] = r3_canonical
        expected_residual = float(CHECKPOINT_EXPLICIT_RESIDUAL)
        actual_residual = float(residual.norm()) / max(
            float(rhs_facts_before["norm"]), np.finfo(float).tiny
        )
        absolute_difference = abs(actual_residual - expected_residual)
        relative_difference = absolute_difference / max(
            abs(expected_residual), np.finfo(float).tiny
        )
        record = {
            "schema": "task038.v17.oracle-a1.v1",
            "stage": "A1",
            "source": _stage_source(root, source_sha, input_path),
            "input": input_facts,
            "checkpoint": {
                **checkpoint,
                **checkpoint_expected,
                "solution_sha256": CHECKPOINT_SOLUTION_SHA256,
            },
            "rhs": rhs_facts,
            "checkpoint_reproduction": {
                "expected": expected_residual,
                "actual": actual_residual,
                "absolute_difference": absolute_difference,
                "relative_difference": relative_difference,
                "relative_limit": 1.0e-8,
            },
            "input_unchanged": {
                "checkpoint_solution_before_sha256": solution_facts_before[
                    "array_sha256"
                ],
                "checkpoint_solution_after_sha256": solution_facts_after[
                    "array_sha256"
                ],
                "rhs_before_sha256": rhs_facts_before["array_sha256"],
                "rhs_after_sha256": rhs_facts_after["array_sha256"],
                "unchanged": (
                    solution_facts_before["array_sha256"]
                    == solution_facts_after["array_sha256"]
                    and rhs_facts_before["array_sha256"]
                    == rhs_facts_after["array_sha256"]
                ),
            },
            "vectors": {
                "r6": r6_facts,
                "r3": r3_facts,
            },
            "operation_counts": {
                "p6_action": 1,
                "p63_adjoint": 1,
                "p63_primal": 0,
            },
            "architecture": {
                "p6_matrix_free": True,
                "global_physical_aij": False,
                "global_schur": False,
                "dense_dtn": False,
                "factor": False,
                "numeric_allgather": False,
                "phase_once": True,
                "p63_owner_transfer": owner_transfer.audit,
            },
        }
        reproduction_failed = (
            not np.isfinite(relative_difference) or relative_difference > 1.0e-8
        )
        record["stage_outcome"] = (
            "numerical_gate_failed" if reproduction_failed else "complete"
        )
        record["gate_failures"] = (
            ["checkpoint_reproduction"] if reproduction_failed else []
        )
        _write_stage_record(raw_dir, "A1", record)
        if reproduction_failed:
            raise RuntimeError(
                "A1 checkpoint residual reproduction exceeded relative limit"
            )
        _worker_marker(
            comm,
            marker_dir,
            "oracle-a",
            "A1_complete",
            source_sha,
            vectors={
                "r6": _compact_vector_facts(r6_facts),
                "r3": _compact_vector_facts(r3_facts),
            },
        )
    finally:
        for vector in (r3, residual, action, rhs, solution):
            if vector is not None:
                vector.destroy()
        if bundle is not None:
            destroy_same_mesh_physical_action(bundle)
        owner_transfer.destroy()
        levels.clear()


def _run_a2(root: Path, raw_dir: Path, marker_dir: Path, source_sha: str, input_path: Path, comm: Any) -> None:
    import copy
    import numpy as np

    from benchmarks.run_task038_full3d_r3 import _current_input
    from benchmarks.task038_full3d_jit_staging import process_tree_snapshot
    from src.solvers.fullspace_v17_p3_oracle import (
        ORACLE_A_PARENT_HARD_BYTES,
        ORACLE_A_RESIDUAL_LIMIT,
        analyze_mumps_p3,
        build_p3_physical_diagnostic_matrix,
        solve_mumps_p3,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels

    if int(comm.size) != 1:
        raise ValueError("Oracle A is currently fixed to MPI1")
    _spec, cfg10, _resolved, input_facts = _current_input(REPO_ROOT, input_path)
    input_facts = {**input_facts, "mode_manifest_sha256": MODE_MANIFEST_SHA256}
    cfg3 = copy.deepcopy(cfg10)
    cfg3.nedelec_degree = 3
    cfg3.visualization_degree = 3
    cfg3.nedelec_trace_degree = None
    cfg3.nedelec_interior_degree = None
    cfg3.case_name = f"{cfg10.case_name}_v17_oracle_p3"
    levels = _build_same_mesh_levels(
        cfg3, comm, (3,), include_positive_coefficients=False
    )
    matrix = None
    factor = rhs = solution = residual = None
    gate_error = None
    gate_failures: list[str] = []
    try:
        matrix, matrix_audit = build_p3_physical_diagnostic_matrix(
            levels, cfg3, comm
        )
        r3_record = json.loads((raw_dir / "A1_record.json").read_text())
        r3_values = _read_array(raw_dir, r3_record["vectors"]["r3"])
        rhs = matrix.createVecLeft()
        rhs.array[:] = r3_values
        p3_mpc = levels["floquets"][3].mpc
        rhs_facts_before = _owned_vector_facts(rhs, p3_mpc, comm)
        factor, analysis_facts = analyze_mumps_p3(matrix)
        post_analysis = process_tree_snapshot(os.getpid(), "A2_post_analysis")
        post_analysis_rss = post_analysis.get("rss_bytes")
        infog16 = analysis_facts.get("raw_info", {}).get("infog", {}).get("16")
        if type(post_analysis_rss) is not int or post_analysis_rss < 0:
            raise RuntimeError("A2 post-analysis process-tree RSS is unreadable")
        if type(infog16) is not int:
            raise RuntimeError("A2 MUMPS INFOG(16) is unreadable")
        predicted = int(post_analysis_rss) + max(int(infog16), 0) * 1_000_000
        solution, solve_facts = solve_mumps_p3(
            factor,
            matrix,
            rhs,
            predicted_peak_bytes=predicted,
            hard_limit_bytes=ORACLE_A_PARENT_HARD_BYTES,
        )
        solve_facts = {**analysis_facts, **solve_facts}
        rhs_facts_after = _owned_vector_facts(rhs, p3_mpc, comm)
        rhs_unchanged = (
            rhs_facts_before["array_sha256"] == rhs_facts_after["array_sha256"]
        )
        solve_facts["resource_preflight_facts"] = {
            "formula": "post_analysis_process_tree_rss_bytes + max(INFOG(16), 0) * 1000000",
            "post_analysis_process_tree_rss_bytes": int(post_analysis_rss),
            "infog16": int(infog16),
            "predicted_peak_bytes": int(predicted),
            "hard_limit_bytes": ORACLE_A_PARENT_HARD_BYTES,
            "available_bytes": int(
                os.sysconf("SC_PAGE_SIZE")
                * os.sysconf("SC_AVPHYS_PAGES")
            ),
            "process_tree_snapshot": post_analysis,
        }
        record: dict[str, Any] = {
            "schema": "task038.v17.oracle-a2.v1",
            "stage": "A2",
            "source": _stage_source(root, source_sha, input_path),
            "input": input_facts,
            "matrix": matrix_audit,
            "direct_solve": solve_facts,
            "predicted_peak_bytes": int(predicted),
            "architecture": {
                "p3_only": True,
                "global_physical_aij": True,
                "static_condensation_used": False,
                "production_global_aij": False,
                "numeric_allgather": False,
                "factor_destroyed_before_a3": True,
            },
            "rhs": {
                "before": rhs_facts_before,
                "after": rhs_facts_after,
                "unchanged": rhs_unchanged,
            },
            "finite": bool(
                rhs_facts_before["finite"] and rhs_facts_after["finite"]
            ),
            "stage_outcome": "resource_blocked" if solution is None else "complete",
            "gate_failures": [],
        }
        if solution is not None:
            check = matrix.createVecLeft()
            try:
                matrix.mult(solution, check)
                residual = rhs.copy()
                residual.axpy(-1.0, check)
                rhs_vector_facts = dict(rhs_facts_before)
                rhs_vector_facts.update(
                    _write_array(raw_dir, "A2/rhs.npy", rhs.array)
                )
                action_facts = _owned_vector_facts(check, p3_mpc, comm)
                action_facts.update(
                    _write_array(raw_dir, "A2/action.npy", check.array)
                )
                residual_facts = _owned_vector_facts(residual, p3_mpc, comm)
                residual_facts.update(
                    _write_array(raw_dir, "A2/residual.npy", residual.array)
                )
                e3_facts = _owned_vector_facts(solution, p3_mpc, comm)
                e3_facts.update(
                    _write_array(raw_dir, "A2/e3.npy", solution.array)
                )
                e3_facts["canonical"] = _write_canonical_vector_manifest(
                    raw_dir,
                    "A2_e3",
                    "full_fe",
                    levels["spaces"][3],
                    levels["floquets"][3],
                    solution,
                    comm,
                )
                record["vectors"] = {
                    "r3": r3_record["vectors"]["r3"],
                    "rhs": rhs_vector_facts,
                    "action": action_facts,
                    "residual": residual_facts,
                    "e3": e3_facts,
                }
                record["explicit_true_residual"] = float(residual.norm()) / max(
                    float(rhs.norm()), np.finfo(float).tiny
                )
                record["finite"] = bool(
                    record["finite"]
                    and action_facts["finite"]
                    and residual_facts["finite"]
                    and e3_facts["finite"]
                )
            finally:
                check.destroy()
        if solution is not None:
            if not record["finite"]:
                gate_failures.append("finite")
            if not rhs_unchanged:
                gate_failures.append("input")
            if (
                not np.isfinite(record["explicit_true_residual"])
                or record["explicit_true_residual"] > ORACLE_A_RESIDUAL_LIMIT
            ):
                gate_failures.append("p3_explicit_residual")
            if (
                e3_facts["owned_slave_max"] != 0.0
                or e3_facts["owned_slave_count"] != 0
            ):
                gate_failures.append("slave")
            if gate_failures:
                record["stage_outcome"] = "numerical_gate_failed"
                record["gate_failures"] = gate_failures
                gate_error = "A2 p3 solve evidence Gate failed"
        _write_stage_record(raw_dir, "A2", record)
        if gate_error is None:
            _worker_marker(
                comm,
                marker_dir,
                "oracle-a",
                "A2_complete",
                source_sha,
                explicit_true_residual=record.get("explicit_true_residual"),
                resource_preflight=solve_facts.get(
                    "resource_preflight", "passed"
                ),
            )
    finally:
        for vector in (residual, solution, rhs):
            if vector is not None:
                vector.destroy()
        if factor is not None:
            factor.destroy()
        if matrix is not None:
            matrix.destroy()
        del levels
    if gate_error is not None:
        raise RuntimeError(gate_error)
    if solution is None:
        _worker_marker(comm, marker_dir, "oracle-a", "record_written", source_sha)
        _worker_marker(comm, marker_dir, "oracle-a", "release_complete", source_sha)


def _run_a3(root: Path, raw_dir: Path, marker_dir: Path, source_sha: str, input_path: Path, comm: Any) -> None:
    import numpy as np

    from benchmarks.run_task038_full3d_r3 import _current_input
    from src.solvers.fullspace_same_mesh_hcurl_pmg import (
        build_same_mesh_hcurl_transfer,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        build_same_mesh_physical_action,
        destroy_same_mesh_physical_action,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_runtime import (
        _mpc_constraint_residual,
        build_same_mesh_hcurl_owner_transfer,
    )
    from dolfinx import fem

    _spec, cfg, _resolved, input_facts = _current_input(REPO_ROOT, input_path)
    input_facts = {**input_facts, "mode_manifest_sha256": MODE_MANIFEST_SHA256}
    levels = _build_same_mesh_levels(
        cfg, comm, (6, 3), include_positive_coefficients=False
    )
    owner_transfer = build_same_mesh_hcurl_owner_transfer(
        levels["spaces"][6],
        levels["floquets"][6],
        levels["spaces"][3],
        levels["floquets"][3],
        local_transfer=build_same_mesh_hcurl_transfer(6, 3),
    )
    levels["p63_owner_transfer"] = owner_transfer
    bundle = None
    e3 = e6_full = e6_algebraic = action = r6 = r6_new = r3_new = None
    try:
        bundle = build_same_mesh_physical_action(levels, cfg, 6)
        a1 = json.loads((raw_dir / "A1_record.json").read_text())
        a2 = json.loads((raw_dir / "A2_record.json").read_text())
        r6_values = _read_array(raw_dir, a1["vectors"]["r6"])
        e3_values = _read_array(raw_dir, a2["vectors"]["e3"])
        r6 = _space_vector(levels, 6)
        r6.array[:] = r6_values
        p6_mpc = levels["floquets"][6].mpc
        p3_mpc = levels["floquets"][3].mpc
        r6_input_before = _owned_vector_facts(r6, p6_mpc, comm)
        e3 = _space_vector(levels, 3)
        e3.array[:] = e3_values
        e3_input_before = _owned_vector_facts(e3, p3_mpc, comm)
        e6_full = _space_vector(levels, 6)
        owner_transfer.apply_primal_into(e3, e6_full)
        transfer_last_apply_facts = dict(owner_transfer.last_apply_facts)
        e6_algebraic = fem.Function(p6_mpc.function_space)
        e6_full.copy(e6_algebraic.x.petsc_vec)
        e6_algebraic.x.scatter_forward()
        fine_mpc_constraint_residual = _mpc_constraint_residual(
            e6_algebraic, levels["floquets"][6]
        )
        levels["floquets"][6].mpc.homogenize(e6_algebraic)
        e6_algebraic.x.scatter_forward()
        action = _space_vector(levels, 6)
        bundle["physical_action"].apply(e6_algebraic.x.petsc_vec, action)
        r6_new = r6.copy()
        r6_new.axpy(-1.0, action)
        r3_new = _space_vector(levels, 3)
        owner_transfer.apply_adjoint_into(r6_new, r3_new)
        r6_input_after = _owned_vector_facts(r6, p6_mpc, comm)
        e3_input_after = _owned_vector_facts(e3, p3_mpc, comm)
        e3_loaded_canonical = _write_canonical_vector_manifest(
            raw_dir,
            "A3_e3_loaded",
            "full_fe",
            levels["spaces"][3],
            levels["floquets"][3],
            e3,
            comm,
        )
        e3_loaded_facts = dict(a2["vectors"]["e3"])
        e3_loaded_facts.update(
            {
                "source_array_sha256": a2["vectors"]["e3"]["array_sha256"],
                "loaded_array_sha256": e3_input_after["array_sha256"],
                "loaded_unchanged": (
                    e3_input_before["array_sha256"]
                    == e3_input_after["array_sha256"]
                ),
            }
        )
        e6_full_facts = _owned_vector_facts(e6_full, p6_mpc, comm)
        e6_full_facts.update(
            _write_array(raw_dir, "A3/e6_full.npy", e6_full.array)
        )
        e6_full_facts.update(
            {
                "fine_mpc_constraint_residual": float(
                    fine_mpc_constraint_residual
                ),
                "transfer_last_apply_facts": transfer_last_apply_facts,
            }
        )
        e6_full_facts["canonical"] = _write_canonical_vector_manifest(
            raw_dir,
            "A3_e6_full",
            "full_fe",
            levels["spaces"][6],
            levels["floquets"][6],
            e6_full,
            comm,
        )
        e6_algebraic_facts = _owned_vector_facts(
            e6_algebraic.x.petsc_vec, p6_mpc, comm
        )
        e6_algebraic_facts.update(
            _write_array(
                raw_dir,
                "A3/e6_algebraic.npy",
                e6_algebraic.x.petsc_vec.array,
            )
        )
        action_facts = _owned_vector_facts(action, p6_mpc, comm)
        action_facts.update(_write_array(raw_dir, "A3/action.npy", action.array))
        action_facts["input_array_sha256"] = e6_algebraic_facts[
            "array_sha256"
        ]
        action_facts["canonical"] = _write_canonical_vector_manifest(
            raw_dir,
            "A3_action",
            "full_fe_dual",
            levels["spaces"][6],
            levels["floquets"][6],
            action,
            comm,
        )
        r6_new_facts = _owned_vector_facts(r6_new, p6_mpc, comm)
        r6_new_facts.update(
            _write_array(raw_dir, "A3/r6_new.npy", r6_new.array)
        )
        r6_new_facts["canonical"] = _write_canonical_vector_manifest(
            raw_dir,
            "A3_r6_new",
            "full_fe_dual",
            levels["spaces"][6],
            levels["floquets"][6],
            r6_new,
            comm,
        )
        r3_new_facts = _owned_vector_facts(r3_new, p3_mpc, comm)
        r3_new_facts.update(
            _write_array(raw_dir, "A3/r3_new.npy", r3_new.array)
        )
        r3_new_facts["canonical"] = _write_canonical_vector_manifest(
            raw_dir,
            "A3_r3_new",
            "full_fe_dual",
            levels["spaces"][3],
            levels["floquets"][3],
            r3_new,
            comm,
        )
        rho_ref = float(r6_new.norm()) / max(float(r6.norm()), np.finfo(float).tiny)
        rho3 = float(r3_new.norm()) / max(float(a1["vectors"]["r3"]["norm"]), np.finfo(float).tiny)
        record = {
            "schema": "task038.v17.oracle-a3.v2",
            "stage": "A3",
            "source": _stage_source(root, source_sha, input_path),
            "input": input_facts,
            "vectors": {
                "r6": a1["vectors"]["r6"],
                "r3": a1["vectors"]["r3"],
                "e3_loaded": {
                    **e3_loaded_facts,
                    "canonical": e3_loaded_canonical,
                },
                "e6_full": e6_full_facts,
                "e6_algebraic": e6_algebraic_facts,
                "action": action_facts,
                "r6_new": r6_new_facts,
                "r3_new": r3_new_facts,
            },
            "loaded_inputs": {
                "r6": {
                    "before": r6_input_before,
                    "after": r6_input_after,
                    "unchanged": (
                        r6_input_before["array_sha256"]
                        == r6_input_after["array_sha256"]
                    ),
                },
                "e3": {
                    "before": e3_input_before,
                    "after": e3_input_after,
                    "unchanged": (
                        e3_input_before["array_sha256"]
                        == e3_input_after["array_sha256"]
                    ),
                },
            },
            "rho_ref": rho_ref,
            "rho3": rho3,
            "operation_counts": {
                "p6_action": 1,
                "p63_adjoint": 1,
                "p63_primal": 1,
            },
            "architecture": {
                "p6_matrix_free": True,
                "global_physical_aij": False,
                "global_schur": False,
                "dense_dtn": False,
                "factor": False,
                "numeric_allgather": False,
                "phase_once": True,
                "p63_owner_transfer": owner_transfer.audit,
            },
        }
        _write_stage_record(raw_dir, "A3", record)
        _worker_marker(comm, marker_dir, "oracle-a", "A3_complete", source_sha, rho_ref=rho_ref, rho3=rho3)
    finally:
        for vector in (r3_new, r6_new, action, e6_full, e3, r6):
            if vector is not None:
                vector.destroy()
        if e6_algebraic is not None:
            del e6_algebraic
        if bundle is not None:
            destroy_same_mesh_physical_action(bundle)
        owner_transfer.destroy()
        levels.clear()
    _worker_marker(comm, marker_dir, "oracle-a", "record_written", source_sha)
    _worker_marker(comm, marker_dir, "oracle-a", "release_complete", source_sha)


def _solver_resource_sample() -> dict[str, Any]:
    from benchmarks.task034_wsl_resources import resource_authority_sample

    sample = resource_authority_sample(os.getpid())
    tree = sample.get("process_tree")
    if hasattr(tree, "to_dict"):
        sample["process_tree"] = tree.to_dict()
    return _jsonable(sample)


def _run_b(root: Path, raw_dir: Path, marker_dir: Path, source_sha: str, input_path: Path, comm: Any) -> None:
    import numpy as np
    import shutil

    from benchmarks.run_task038_full3d_r3 import _current_input
    from src.solvers.fullspace_memory_first_krylov import (
        destroy_krylov_result,
        read_solution_checkpoint,
        run_restart20_cycles,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        build_p6_same_mesh_physical_bundle,
        build_physical_rhs,
        destroy_p6_same_mesh_physical_bundle,
    )
    from src.solvers.disk_backed_flexible_gmres import run_disk_backed_right_fgmres

    if int(comm.size) != 1:
        raise ValueError("Oracle B is currently fixed to MPI1")
    _spec, cfg, _resolved, input_facts = _current_input(REPO_ROOT, input_path)
    input_facts = {**input_facts, "mode_manifest_sha256": MODE_MANIFEST_SHA256}
    disk_free_bytes = int(shutil.disk_usage(root).free)
    if disk_free_bytes < ORACLE_B_DISK_FREE_BYTES:
        raise RuntimeError(
            f"Oracle B free-disk preflight failed: {disk_free_bytes} < {ORACLE_B_DISK_FREE_BYTES}"
        )
    bundle = None
    checkpoint_solution = rhs = None
    record_written = False
    try:
        bundle = build_p6_same_mesh_physical_bundle(cfg, comm)
        p6_matrix = bundle["setup"]["p6_shell"].matrix
        checkpoint_solution = p6_matrix.createVecRight()
        checkpoint = read_solution_checkpoint(
            CHECKPOINT_DIR,
            checkpoint_solution,
            expected=_checkpoint_expected(),
            ownership=_ownership(checkpoint_solution, comm),
            comm=comm,
        )
        rhs, rhs_facts = build_physical_rhs(bundle)
        initial_values = np.asarray(
            checkpoint_solution.getArray(readonly=True), dtype=np.complex128
        ).copy()
        rhs_values = np.asarray(
            rhs.getArray(readonly=True), dtype=np.complex128
        ).copy()
        def array_sha256(values: Any) -> str:
            array = np.asarray(values)
            return hashlib.sha256(
                memoryview(np.ascontiguousarray(array)).cast("B")
            ).hexdigest()

        same_start_rhs_sha256 = array_sha256(rhs_values)
        same_start_initial_sha256 = array_sha256(initial_values)
        reference_rhs_descriptor = _write_array(
            raw_dir, "reference/rhs.npy", rhs_values
        )
        reference_initial_descriptor = _write_array(
            raw_dir, "reference/initial_solution.npy", initial_values
        )
        reference_packets: list[dict[str, Any]] = []
        reference_observer_action_count = 0
        reference_rhs_before_sha256 = array_sha256(rhs.getArray(readonly=True))
        reference_initial_before_sha256 = array_sha256(
            checkpoint_solution.getArray(readonly=True)
        )

        def apply_action(source: Any) -> Any:
            target = p6_matrix.createVecLeft()
            bundle["physical_action"].apply(source, target)
            return target

        def apply_pc(source: Any) -> Any:
            return bundle["setup"]["upper_cycle"].apply(source)

        def reference_observer(
            iteration: int, solution: Any, _cycle: dict[str, Any]
        ) -> None:
            nonlocal reference_observer_action_count
            local_iteration = int(iteration - ORACLE_B_START_ITERATION)
            observed_action = apply_action(solution)
            try:
                action_descriptor = _write_array(
                    raw_dir,
                    f"reference/ax_{local_iteration:04d}.npy",
                    observed_action.getArray(readonly=True),
                )
            finally:
                observed_action.destroy()
            reference_packets.append(
                {
                    "iteration": local_iteration,
                    "rhs": reference_rhs_descriptor,
                    "ax": action_descriptor,
                }
            )
            reference_observer_action_count += 1

        reference = run_restart20_cycles(
            rhs,
            apply_action,
            apply_pc,
            max_it=ORACLE_B_START_ITERATION + ORACLE_B_STEPS,
            residual_limit=0.0,
            resource_sample=_solver_resource_sample,
            initial_solution=checkpoint_solution,
            start_iteration=ORACLE_B_START_ITERATION,
            checkpoint_writer=None,
            first_checkpoint_iteration=None,
            checkpoint_interval=ORACLE_B_CHECKPOINT_INTERVAL,
            cycle_observer=reference_observer,
            stop_on_true_residual=False,
            ksp_type="gmres",
        )
        reference_history = [
            {
                "iteration": int(cycle["end_iteration"] - ORACLE_B_START_ITERATION),
                "true_residual_norm": float(cycle["explicit_true_residual"] * rhs.norm()),
                "true_relative_residual": float(cycle["explicit_true_residual"]),
                "finite": True,
            }
            for cycle in reference["cycles"]
        ]
        reference_facts = {
            "algorithm": "right_gmres_restart20",
            "history": reference_history,
            "final_true_residual": float(reference["final_true_residual"]),
            "iterations": int(reference["iterations"] - ORACLE_B_START_ITERATION),
            "matvec_count": int(reference["matvec_count"]),
            "pc_apply_count": int(reference["pc_apply_count"]),
            "ksp_destroy_count": int(reference["ksp_destroy_count"]),
            "explicit_action_count": int(reference["explicit_action_count"]),
            "settings": dict(reference["settings"]),
            "residual_packets": reference_packets,
            "residual_packet_action_count": reference_observer_action_count,
            "observer_action_count": reference_observer_action_count,
            "cycles": [dict(cycle) for cycle in reference["cycles"]],
            "rhs_before_sha256": reference_rhs_before_sha256,
            "rhs_after_sha256": array_sha256(rhs.getArray(readonly=True)),
            "initial_solution_before_sha256": reference_initial_before_sha256,
            "initial_solution_after_sha256": array_sha256(
                checkpoint_solution.getArray(readonly=True)
            ),
            "input_unchanged": (
                reference_rhs_before_sha256 == same_start_rhs_sha256
                and array_sha256(rhs.getArray(readonly=True)) == same_start_rhs_sha256
                and reference_initial_before_sha256 == same_start_initial_sha256
                and array_sha256(checkpoint_solution.getArray(readonly=True))
                == same_start_initial_sha256
            ),
            "finite": bool(
                np.all(np.isfinite(rhs_values))
                and np.all(np.isfinite(initial_values))
                and np.isfinite(reference["initial_true_residual"])
                and np.isfinite(reference["final_true_residual"])
            ),
            "initial_true_residual": float(reference["initial_true_residual"]),
        }
        _worker_marker(
            comm,
            marker_dir,
            "oracle-b",
            "reference_complete",
            source_sha,
            iterations=reference_facts["iterations"],
        )
        destroy_krylov_result(reference)
        checkpoint_solution.array[:] = initial_values
        disk_rhs_descriptor = _write_array(
            raw_dir, "unrestarted/checkpoints/rhs.npy", rhs_values
        )
        disk_packets: list[dict[str, Any]] = []

        def array_action(values: np.ndarray) -> np.ndarray:
            source = p6_matrix.createVecRight()
            target = p6_matrix.createVecLeft()
            try:
                source.array[:] = values
                bundle["physical_action"].apply(source, target)
                return np.asarray(target.getArray(readonly=True), dtype=np.complex128).copy()
            finally:
                target.destroy()
                source.destroy()

        def array_pc(values: np.ndarray) -> np.ndarray:
            source = p6_matrix.createVecRight()
            correction = None
            try:
                source.array[:] = values
                correction = bundle["setup"]["upper_cycle"].apply(source)
                return np.asarray(correction.getArray(readonly=True), dtype=np.complex128).copy()
            finally:
                if correction is not None:
                    correction.destroy()
                source.destroy()

        def disk_observer(row: dict[str, Any]) -> None:
            iteration = int(row["iteration"])
            action_descriptor = _write_array(
                raw_dir,
                f"unrestarted/checkpoints/ax_{iteration:04d}.npy",
                row["action"],
            )
            disk_packets.append(
                {
                    "iteration": iteration,
                    "rhs": disk_rhs_descriptor,
                    "ax": action_descriptor,
                }
            )

        disk = run_disk_backed_right_fgmres(
            rhs_values,
            array_action,
            array_pc,
            scratch_root=raw_dir / "unrestarted" / "basis",
            max_steps=ORACLE_B_STEPS,
            initial_solution=initial_values,
            checkpoint_interval=ORACLE_B_CHECKPOINT_INTERVAL,
            observer=disk_observer,
        )
        disk_audit = dict(disk["audit"])
        disk_audit["scratch_manifest_sha256"] = _sha256(
            raw_dir / "unrestarted" / "basis" / "basis_manifest.json"
        )
        hessenberg_path = raw_dir / "unrestarted" / "basis" / "H.npy"
        disk_facts = {
            "algorithm": "right_fgmres_unrestarted_disk_backed",
            "history": disk["history"],
            "final_true_residual": float(disk["final_relative_residual"]),
            "iterations": int(disk["iterations"]),
            "action_count": int(disk_audit["action_count"]),
            "pc_count": int(disk_audit["pc_count"]),
            "explicit_action_count": int(disk_audit["explicit_action_count"]),
            "residual_packet_action_count": len(disk_packets),
            "audit": disk_audit,
            "hessenberg_shape": list(disk["hessenberg"].shape),
            "hessenberg": {
                "relative_path": str(hessenberg_path.relative_to(raw_dir.parent)),
                "bytes": hessenberg_path.stat().st_size,
                "sha256": _sha256(hessenberg_path),
                "dtype": "complex128",
                "shape": list(disk["hessenberg"].shape),
            },
            "residual_packets": disk_packets,
            "settings": {
                "pc_side": "right",
                "restart": None,
                "max_steps": ORACLE_B_STEPS,
                "checkpoint_interval": ORACLE_B_CHECKPOINT_INTERVAL,
                "initial_guess_nonzero": True,
                "ksp_type": "fgmres",
                "norm_type": "unpreconditioned",
                "residual_replacement": False,
            },
            "initial_true_residual": float(disk_audit["initial_true_residual"]),
            "finite": bool(
                np.all(np.isfinite(rhs_values))
                and np.all(np.isfinite(initial_values))
                and disk_audit["final_solution_finite"] is True
                and np.isfinite(disk_audit["initial_true_residual"])
                and np.isfinite(disk["final_relative_residual"])
            ),
        }
        _worker_marker(
            comm,
            marker_dir,
            "oracle-b",
            "unrestarted_complete",
            source_sha,
            iterations=disk_facts["iterations"],
        )
        checkpoint_facts = {
            **checkpoint,
            "explicit_true_residual": CHECKPOINT_EXPLICIT_RESIDUAL,
            "input_identity_sha256": CHECKPOINT_INPUT_IDENTITY_SHA256,
            "operator_identity_sha256": CHECKPOINT_OPERATOR_IDENTITY_SHA256,
            "physical_model_sha256": PHYSICAL_MODEL_SHA256,
            "source_sha": CHECKPOINT_SOURCE_SHA,
            "mpi_size": 1,
            "manifest_sha256": CHECKPOINT_MANIFEST_SHA256,
            "solution_sha256": CHECKPOINT_SOLUTION_SHA256,
        }
        record = {
            "schema": "task038.v17.oracle-b.v1",
            "stage": "B",
            "source": _stage_source(root, source_sha, input_path),
            "input": input_facts,
            "disk_preflight": {
                "required_free_bytes": ORACLE_B_DISK_FREE_BYTES,
                "free_bytes": disk_free_bytes,
            },
            "checkpoint": checkpoint_facts,
            "rhs": rhs_facts,
            "reference": reference_facts,
            "unrestarted": disk_facts,
            "same_start": {
                "rhs": {
                    "descriptor": reference_rhs_descriptor,
                    "sha256": same_start_rhs_sha256,
                    "finite": bool(np.all(np.isfinite(rhs_values))),
                },
                "initial_solution": {
                    "descriptor": reference_initial_descriptor,
                    "sha256": same_start_initial_sha256,
                    "finite": bool(np.all(np.isfinite(initial_values))),
                },
                "reference": {
                    "rhs_before_sha256": reference_facts["rhs_before_sha256"],
                    "rhs_after_sha256": reference_facts["rhs_after_sha256"],
                    "initial_solution_before_sha256": reference_facts[
                        "initial_solution_before_sha256"
                    ],
                    "initial_solution_after_sha256": reference_facts[
                        "initial_solution_after_sha256"
                    ],
                    "input_unchanged": reference_facts["input_unchanged"],
                    "initial_true_residual": reference_facts[
                        "initial_true_residual"
                    ],
                    "finite": reference_facts["finite"],
                },
                "unrestarted": {
                    "rhs_before_sha256": disk_audit["input_rhs_before_sha256"],
                    "rhs_after_sha256": disk_audit["input_rhs_after_sha256"],
                    "initial_solution_before_sha256": disk_audit[
                        "input_initial_before_sha256"
                    ],
                    "initial_solution_after_sha256": disk_audit[
                        "input_initial_after_sha256"
                    ],
                    "input_unchanged": disk_audit["input_unchanged"],
                    "initial_true_residual": disk_facts[
                        "initial_true_residual"
                    ],
                    "finite": disk_facts["finite"],
                },
            },
            "architecture": {
                "p6_matrix_free": True,
                "global_physical_aij": False,
                "global_schur": False,
                "dense_dtn": False,
                "factor": False,
                "numeric_allgather": False,
                "basis_in_memory": False,
                "mmap": False,
                "phase_once": True,
                "full_vector_buffer_limit": 8,
            },
        }
        _write_stage_record(raw_dir, "B", record)
        _worker_marker(comm, marker_dir, "oracle-b", "record_written", source_sha)
        record_written = True
    finally:
        if rhs is not None:
            rhs.destroy()
        if checkpoint_solution is not None:
            checkpoint_solution.destroy()
        if bundle is not None:
            destroy_p6_same_mesh_physical_bundle(bundle)
    if record_written:
        _worker_marker(comm, marker_dir, "oracle-b", "release_complete", source_sha)


def run_worker(root: Path, record_path: Path, source_sha: str, input_path: Path, phase: str, stage: str, expected_size: int) -> None:
    root = _absolute(root)
    cache_dir = (root / "jit_cache").resolve()
    os.environ["XDG_CACHE_HOME"] = str(cache_dir)
    if not cache_dir.is_dir() or Path(os.environ["XDG_CACHE_HOME"]).resolve() != cache_dir:
        raise FileNotFoundError("worker parent-owned JIT cache is not bound")
    from mpi4py import MPI
    from petsc4py import PETSc

    comm = MPI.COMM_WORLD
    if int(comm.size) != int(expected_size):
        raise RuntimeError("worker MPI size mismatch")
    raw_dir, marker_dir = _prepare_stage_paths(root, comm)
    record_path = _absolute(record_path)
    expected_record = raw_dir / f"{stage}_record.json"
    if record_path != expected_record:
        raise ValueError("worker record must be a stage record below raw")
    _worker_marker(comm, marker_dir, phase, "paths_ready", source_sha, cache_dir="jit_cache")
    runtime = authority_runner._runtime_facts(comm, PETSc, expected_size)
    _worker_marker(comm, marker_dir, phase, "abi_ready", source_sha, runtime=runtime)
    if phase == "oracle-a":
        if stage == "A1":
            _run_a1(root, raw_dir, marker_dir, source_sha, input_path, comm)
        elif stage == "A2":
            _run_a2(root, raw_dir, marker_dir, source_sha, input_path, comm)
        elif stage == "A3":
            _run_a3(root, raw_dir, marker_dir, source_sha, input_path, comm)
        else:
            raise ValueError(f"unknown Oracle A stage: {stage}")
    elif phase == "oracle-b" and stage == "B":
        _run_b(root, raw_dir, marker_dir, source_sha, input_path, comm)
    else:
        raise ValueError(f"unknown V17 phase/stage: {phase}/{stage}")


def _worker_command(root: Path, record: Path, source_sha: str, input_path: Path, phase: str, stage: str, size: int) -> list[str]:
    return [
        "mpiexec",
        "-n",
        str(size),
        str(Path(sys.executable)),
        "-m",
        MODULE,
        "--phase",
        phase,
        "--mode",
        "worker",
        "--stage",
        stage,
        "--artifact-root",
        str(root),
        "--record",
        str(record),
        "--source-sha",
        source_sha,
        "--input",
        str(input_path),
        "--mpi-size",
        str(size),
    ]


def _jit_child_command(
    group: str,
    cache: Path,
    record: Path,
    source_sha: str,
    input_path: Path,
) -> list[str]:
    command = authority_runner._child_command(
        group, cache, record, source_sha, input_path
    )
    command[0] = str(REPO_ROOT / ".venv" / "bin" / "python")
    return command


def _resource_contract(phase: str) -> tuple[int, int, int]:
    if phase == "oracle-a":
        return ORACLE_A_WARNING_BYTES, ORACLE_A_HARD_BYTES, ORACLE_A_HARD_BYTES
    return ORACLE_B_WARNING_BYTES, ORACLE_B_HARD_BYTES, ORACLE_B_HARD_BYTES


def run_parent(root: Path, record_path: Path, source_sha: str, input_path: Path, phase: str, expected_size: int) -> int:
    root, cache = authority_runner._prepare_parent_root(root)
    record_path = _absolute(record_path)
    if record_path.parent != root:
        raise ValueError("V17 parent record must be directly below artifact root")
    children_dir = root / "children"
    if phase != "oracle-a":
        children_dir.mkdir(exist_ok=False)
    process_path = root / "parent_process.jsonl"
    source = _stage_source(root, source_sha, input_path)
    warning, watchdog, hard = _resource_contract(phase)
    cache_initial = authority_runner._cache_snapshot(cache)
    children: list[dict[str, Any]] = []
    stage_results: list[dict[str, Any]] = []
    error = None
    cache_before = None
    cache_after = None
    stages: list[str] = []
    stage_cache: list[dict[str, Any]] = []
    a2_resource_blocked = False
    numeric_stop_stage = None
    try:
        if phase == "oracle-a":
            for stage in ("A1", "A2"):
                stage_record = root / "raw" / f"{stage}_record.json"
                result = authority_runner._run_parent_child(
                    _worker_command(
                        root,
                        stage_record,
                        source_sha,
                        _absolute(input_path),
                        phase,
                        stage,
                        expected_size,
                    ),
                    process_path,
                    stage,
                    root / f"{stage}.stdout.log",
                    root / f"{stage}.stderr.log",
                    rss_watchdog_bytes=watchdog,
                    rss_warning_bytes=warning,
                )
                result.update(
                    {"stage": stage, "record": str(stage_record.relative_to(root))}
                )
                stage_results.append(result)
                stages.append(stage)
                stage_record_data = None
                if stage_record.is_file():
                    try:
                        stage_record_data = json.loads(
                            stage_record.read_text(encoding="utf-8")
                        )
                    except (OSError, ValueError, TypeError):
                        stage_record_data = None
                numeric_stop = (
                    result["returncode"] != 0
                    and result["stop_reason"] is None
                    and result["process_group_gone"] is True
                    and result["lifecycle_failure"] is False
                    and result["signals"] == []
                    and result["max_swap_bytes"] == 0
                    and result["all_status_readable"] is True
                    and isinstance(stage_record_data, dict)
                    and stage_record_data.get("stage_outcome")
                    == "numerical_gate_failed"
                )
                stage_cache.append(
                    {"stage": stage, "snapshot": authority_runner._cache_snapshot(cache)}
                )
                if numeric_stop:
                    numeric_stop_stage = stage
                    error = f"{stage} numerical gate stop"
                    break
                if (
                    result["returncode"] != 0
                    or result["stop_reason"] is not None
                    or not result["process_group_gone"]
                ):
                    raise RuntimeError(f"oracle stage lifecycle failed: {stage}")
                if stage == "A2" and numeric_stop_stage is None:
                    a2 = json.loads(stage_record.read_text(encoding="utf-8"))
                    a2_resource_blocked = (
                        a2.get("direct_solve", {}).get("resource_preflight")
                        == "blocked"
                    )
                    if a2_resource_blocked:
                        break
            if not a2_resource_blocked and numeric_stop_stage is None:
                stage = "A3"
                stage_record = root / "raw" / f"{stage}_record.json"
                result = authority_runner._run_parent_child(
                    _worker_command(
                        root,
                        stage_record,
                        source_sha,
                        _absolute(input_path),
                        phase,
                        stage,
                        expected_size,
                    ),
                    process_path,
                    stage,
                    root / f"{stage}.stdout.log",
                    root / f"{stage}.stderr.log",
                    rss_watchdog_bytes=watchdog,
                    rss_warning_bytes=warning,
                )
                result.update(
                    {"stage": stage, "record": str(stage_record.relative_to(root))}
                )
                stage_results.append(result)
                stages.append(stage)
                if (
                    result["returncode"] != 0
                    or result["stop_reason"] is not None
                    or not result["process_group_gone"]
                ):
                    raise RuntimeError(f"oracle stage lifecycle failed: {stage}")
                stage_cache.append(
                    {"stage": stage, "snapshot": authority_runner._cache_snapshot(cache)}
                )
        else:
            for index, group in enumerate(JIT_GROUPS):
                stem = f"{index:02d}_{group.replace('-', '_')}"
                child_record = children_dir / f"{stem}.json"
                result = authority_runner._run_parent_child(
                    _jit_child_command(
                        group, cache, child_record, source_sha, _absolute(input_path)
                    ),
                    process_path,
                    f"precompile:{group}",
                    children_dir / f"{stem}.stdout.log",
                    children_dir / f"{stem}.stderr.log",
                    rss_watchdog_bytes=watchdog,
                    rss_warning_bytes=warning,
                )
                result.update(
                    {
                        "group": group,
                        "record": str(child_record.relative_to(root)),
                        "record_sha256": _sha256(child_record)
                        if child_record.is_file()
                        else None,
                    }
                )
                children.append(result)
                if (
                    result["returncode"] != 0
                    or result["stop_reason"] is not None
                    or not result["process_group_gone"]
                ):
                    raise RuntimeError(f"precompile lifecycle failed: {group}")
            cache_before = authority_runner._cache_snapshot(cache)
            for stage in ORACLE_B_STAGES:
                stage_record = root / "raw" / f"{stage}_record.json"
                result = authority_runner._run_parent_child(
                    _worker_command(
                        root,
                        stage_record,
                        source_sha,
                        _absolute(input_path),
                        phase,
                        stage,
                        expected_size,
                    ),
                    process_path,
                    stage,
                    root / f"{stage}.stdout.log",
                    root / f"{stage}.stderr.log",
                    rss_watchdog_bytes=watchdog,
                    rss_warning_bytes=warning,
                )
                result.update(
                    {"stage": stage, "record": str(stage_record.relative_to(root))}
                )
                stage_results.append(result)
                stages.append(stage)
                if (
                    result["returncode"] != 0
                    or result["stop_reason"] is not None
                    or not result["process_group_gone"]
                ):
                    raise RuntimeError(f"oracle stage lifecycle failed: {stage}")
            cache_after = authority_runner._cache_snapshot(cache)
            if cache_before != cache_after:
                raise RuntimeError("V17 oracle worker changed the parent-owned JIT cache")
    except Exception as exc:
        error = str(exc)
    process = authority_runner._process_summary(process_path) if process_path.is_file() else None
    marker_dir = root / "markers"
    marker_manifest_path = root / "marker_manifest.json"
    marker_rows = []
    if marker_dir.is_dir():
        for path in authority_runner.marker_files(marker_dir, order=_marker_order(phase)):
            marker_rows.append({"name": path.stem.split("_", 1)[1], "sha256": authority_runner.sha256_file(path)})
    if marker_rows and not marker_manifest_path.exists():
        _write_json(marker_manifest_path, marker_rows)
    stage_descriptors = []
    for stage in stages:
        path = root / "raw" / f"{stage}_record.json"
        if path.is_file():
            result = next(
                (item for item in stage_results if item.get("stage") == stage), None
            )
            stage_descriptors.append(
                {
                    **(result or {"stage": stage}),
                    "stage": stage,
                    "record": str(path.relative_to(root)),
                    "sha256": _sha256(path),
                }
            )
    parent_record = {
        "schema": PARENT_SCHEMA,
        "source": source,
        "workflow": "task038-v17-oracles",
        "phase": phase,
        "expected_mpi_size": int(expected_size),
        "resource_contract": {
            "warning_bytes": warning,
            "rss_watchdog_bytes": watchdog,
            "hard_gate_bytes": hard,
            "swap_gate_bytes": 0,
        },
        "command": {
            "argv": [str(value) for value in sys.argv],
            "cwd": str(REPO_ROOT),
        },
        "paths": {
            "jit_cache": "jit_cache",
            "process_samples": "parent_process.jsonl",
            "raw_dir": "raw",
            "marker_manifest": "marker_manifest.json",
        },
        "jit_groups": [] if phase == "oracle-a" else list(JIT_GROUPS),
        "cache": (
            {"initial": cache_initial, "stage_snapshots": stage_cache}
            if phase == "oracle-a"
            else {
                "initial": cache_initial,
                "before_worker": cache_before,
                "after_worker": cache_after,
            }
        ),
        "classification": (
            "ORACLE_A_NUMERICAL_GATE_STOP"
            if phase == "oracle-a" and numeric_stop_stage is not None
            else "A_ORACLE_BLOCKED_BY_RESOURCE_PREFLIGHT"
            if phase == "oracle-a" and a2_resource_blocked
            else "RAW_COMPLETE_PENDING_CHECKER"
            if error is None
            else None
        ),
        "a2_resource_blocked": a2_resource_blocked,
        "numeric_stop_stage": numeric_stop_stage,
        "children": children,
        "stages": stage_descriptors,
        "process": process,
        "markers": None if not marker_manifest_path.is_file() else {
            "relative_path": "marker_manifest.json",
            "sha256": _sha256(marker_manifest_path),
            "names": [row["name"] for row in marker_rows],
        },
        "error": error,
    }
    _write_json(record_path, parent_record)
    return 0 if error is None else 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=PHASES, required=True)
    parser.add_argument("--mode", choices=("parent", "worker"), required=True)
    parser.add_argument("--stage", choices=("A1", "A2", "A3", "B"))
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--record", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--mpi-size", choices=EXPECTED_MPI_SIZES, type=int, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = _absolute(args.artifact_root)
    record = _absolute(args.record)
    input_path = _absolute(args.input)
    if args.mode == "parent":
        return run_parent(root, record, args.source_sha, input_path, args.phase, args.mpi_size)
    if args.stage is None:
        raise ValueError("worker mode requires --stage")
    run_worker(root, record, args.source_sha, input_path, args.phase, args.stage, args.mpi_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
