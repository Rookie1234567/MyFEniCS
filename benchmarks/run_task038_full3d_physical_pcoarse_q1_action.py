"""Run the V16 Q1.1 same-mesh physical-action identity oracle.

The parent reuses the reviewed cold staging and process-tree sampler.  The
worker owns only the action evidence paths and keeps the numerical construction
in ``src.solvers``; it writes owner-local canonical shards, never a global
physical matrix or a numeric allgather.
"""

from __future__ import annotations

import argparse
import copy
import gc
import json
import math
from pathlib import Path
import sys
from typing import Any

from benchmarks import run_task038_full3d_physical_pcoarse_q1 as authority_runner


BRANCH = authority_runner.BRANCH
MODULE = "benchmarks.run_task038_full3d_physical_pcoarse_q1_action"
PHASE = "action-identity"
WORKFLOW = "q1-physical-pcoarse-action-identity"
PARENT_SCHEMA = "task038.v16.q1.action-identity.parent.v1"
WORKER_SCHEMA = "task038.v16.q1.action-identity.worker.v1"
PROCESS_SCHEMA = authority_runner.PROCESS_SCHEMA
MARKER_SCHEMA = "task038.v16.q1.action-identity.marker.v1"
ACTION_MANIFEST_SCHEMA = "task038.v16.q1.action-identity.manifest.v1"
MARKER_ORDER = (
    "paths_ready",
    "abi_ready",
    "case_built",
    "probe_execution_started",
    "probe_execution_complete",
    "release_complete",
    "record_written",
)
JIT_GROUPS = authority_runner.JIT_GROUPS
EXPECTED_MPI_SIZES = (1, 2)
MODE_COUNT = 80
MODE_MANIFEST_SHA256 = authority_runner.MODE_MANIFEST_SHA256
INPUT_SHA256 = authority_runner.INPUT_SHA256
PHYSICAL_MODEL_SHA256 = (
    "9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"
)
R3_AUTHORITY_SOURCE_SHA = "6c9c97b71a31d54afe92b0858d1347c4815c9aa4"
R3_AUTHORITY_MANIFEST_SHA256 = (
    "1a3d3ca86276876dee3590da2de60876553e7d49afc060d5066ca10a9cb7b7b2"
)
R3_AUTHORITY_SHARD_SHA256 = (
    "ccfe99b98187e35cd316dc20eec5857559c6844d62bcd71eff9a41b450ea277a"
)
R3_AUTHORITY_PACKET_COUNT = 2538
R3_AUTHORITY_MANIFEST = Path(
    "benchmarks/artifacts/task038_extra_full3d_iterative_0p7nm/"
    "q1_source_authority_v7/6c9c97b71a31d54afe92b0858d1347c4815c9aa4/"
    "mpi1/raw/canonical/r3.manifest.json"
)
PROBE_NAMES = (
    "random",
    "gradient",
    "curl",
    "checkerboard",
    "physical_component_derived",
    "r3_long_tail_derived",
)
ALPHA = 0.37 + 0.19j
REPO_ROOT = authority_runner.REPO_ROOT


def _absolute(value: Path | str) -> Path:
    return Path(value).absolute()


def _write_json(path: Path, value: Any) -> None:
    authority_runner._write_json(path, value)


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    if hasattr(value, "item"):
        return _jsonable(value.item())
    return value


def _worker_marker(
    comm: Any, marker_dir: Path, name: str, source_sha: str, **facts: Any
) -> None:
    if int(comm.rank) == 0:
        authority_runner.write_marker(
            marker_dir,
            name,
            {
                "phase": PHASE,
                "workflow": WORKFLOW,
                "source_sha": source_sha,
                "mpi_size": int(comm.size),
                **_jsonable(facts),
            },
            order=MARKER_ORDER,
            schema=MARKER_SCHEMA,
        )
    comm.barrier()


def _worker_command(
    root: Path, record: Path, source_sha: str, input_path: Path, mpi_size: int
) -> list[str]:
    return [
        "mpiexec",
        "-n",
        str(int(mpi_size)),
        str(Path(sys.executable)),
        "-m",
        MODULE,
        "--phase",
        PHASE,
        "--mode",
        "worker",
        "--artifact-root",
        str(root),
        "--record",
        str(record),
        "--source-sha",
        source_sha,
        "--input",
        str(input_path),
        "--mpi-size",
        str(int(mpi_size)),
    ]


def _rss_watchdog_bytes(mpi_size: int) -> int | None:
    return authority_runner.RSS_WATCHDOG if int(mpi_size) == 1 else None


def _packet_relative(left: Any, right: Any, comm: Any) -> float:
    left_map: dict[Any, complex] = {}
    right_map: dict[Any, complex] = {}
    for key, value in left:
        if key in left_map:
            raise RuntimeError("duplicate canonical packet key")
        left_map[key] = complex(value)
    for key, value in right:
        if key in right_map:
            raise RuntimeError("duplicate canonical packet key")
        right_map[key] = complex(value)
    if set(left_map) != set(right_map):
        raise RuntimeError("canonical packet key closure failed")
    numerator = comm.allreduce(
        math.fsum(abs(left_map[key] - right_map[key]) ** 2 for key in left_map)
    )
    denominator = comm.allreduce(
        math.fsum(abs(right_map[key]) ** 2 for key in right_map)
    )
    return float(math.sqrt(numerator / max(denominator, 1.0e-300)))


def _vector_relative(left: Any, right: Any) -> float:
    difference = left.copy()
    try:
        difference.axpy(-1.0, right)
        return float(
            difference.norm() / max(right.norm(), 1.0e-300)
        )
    finally:
        difference.destroy()


def _write_packet_manifest(
    raw_dir: Path,
    label: str,
    packets: Any,
    audit: dict[str, Any],
    comm: Any,
) -> dict[str, Any]:
    from benchmarks.canonical_vector_artifacts import (
        canonical_shard_manifest,
        write_canonical_manifest,
        write_canonical_packet_shard,
    )

    canonical_dir = raw_dir / "canonical"
    if int(comm.rank) == 0:
        canonical_dir.mkdir(parents=True, exist_ok=True)
    comm.barrier()
    shard_path = canonical_dir / f"{label}.rank{int(comm.rank):04d}.jsonl"
    shard = write_canonical_packet_shard(shard_path, packets, audit_packets=True)
    shard["rank"] = int(comm.rank)
    shard_rows = comm.gather(shard, root=0)
    descriptor = None
    if int(comm.rank) == 0:
        manifest = canonical_shard_manifest(
            role="full_fe_dual",
            mpi_size=int(comm.size),
            shard_metadata=shard_rows,
            extractor_audit=_jsonable(dict(audit)),
        )
        manifest_path = canonical_dir / f"{label}.manifest.json"
        manifest_sha = write_canonical_manifest(manifest_path, manifest)
        descriptor = {
            "manifest_relative_path": str(
                manifest_path.relative_to(raw_dir.parent)
            ),
            "manifest_sha256": manifest_sha,
            "role": "full_fe_dual",
            "packet_count": int(manifest["global_summed_packet_count"]),
            "mpi_size": int(comm.size),
        }
    return comm.bcast(descriptor, root=0)


def _compact_action_audit(action: Any) -> dict[str, Any]:
    audit = dict(action.audit)
    volume = dict(audit["volume_action"])
    dtn = dict(audit["dtn_action"])
    components = tuple(dict(item) for item in volume["components"].values())
    return {
        "schema": audit["schema"],
        "volume_phase_application": volume["phase_application"],
        "dtn_mode_manifest_sha256": dtn["mode_manifest_sha256"],
        "dtn_mode_count": int(dtn["mode_count"]),
        "global_aij_materialized": bool(audit["global_aij_materialized"]),
        "global_schur_materialized": bool(audit["global_schur_materialized"]),
        "ksp_created": bool(audit["ksp_created"]),
        "numeric_allgather": bool(audit["numeric_allgather"]),
        "trace_matrix_materialized": bool(dtn["trace_matrix_materialized"]),
        "global_volume_matrix_materialized": any(
            bool(item["global_matrix_materialized"]) for item in components
        ),
        "global_constraint_matrix_materialized": any(
            bool(item["global_constraint_matrix_materialized"])
            for item in components
        ),
        "global_condensed_schur_materialized": any(
            bool(item["global_condensed_schur_materialized"])
            for item in components
        ),
        "dense_cell_tensor_materialized": any(
            bool(item["dense_cell_tensor_materialized_per_apply"])
            or int(item["retained_dense_cell_tensor_count"]) != 0
            for item in components
        ),
        "factor_count": sum(int(item["factor_count"]) for item in components),
        "explicit_c_matrix_count": int(audit["dtn_action"]["explicit_c_matrix_count"]),
        "explicit_d_matrix_count": int(audit["dtn_action"]["explicit_d_matrix_count"]),
    }


def _load_r3_packets(case: dict[str, Any], comm: Any) -> tuple[Any, dict[str, Any]]:
    from benchmarks.canonical_vector_artifacts import (
        read_canonical_manifest_metadata,
        read_selected_canonical_packet_shard,
    )
    from src.solvers.hcurl_canonical_vector_dolfinx import (
        iter_canonical_full_fe_dual_packets,
    )

    manifest_path = REPO_ROOT / R3_AUTHORITY_MANIFEST
    manifest = read_canonical_manifest_metadata(
        manifest_path, R3_AUTHORITY_MANIFEST_SHA256
    )
    shard = manifest["per_rank_shards"]
    if (
        manifest["role"] != "full_fe_dual"
        or int(manifest["mpi_size"]) != 1
        or int(manifest["global_summed_packet_count"]) != R3_AUTHORITY_PACKET_COUNT
        or len(shard) != 1
        or shard[0]["filename"] != "r3.rank0000.jsonl"
        or shard[0]["file_sha256"] != R3_AUTHORITY_SHARD_SHA256
    ):
        raise RuntimeError("v7 R3 canonical authority identity changed")
    p3_space = case["setup"]["spaces"][3]
    p3_floquet = case["setup"]["floquets"][3]
    zero = case["setup"]["p3_matrix"].createVecRight()
    try:
        wanted_keys = tuple(
            key
            for key, _value in iter_canonical_full_fe_dual_packets(
                p3_space, p3_floquet.mpc, zero
            )
        )
    finally:
        zero.destroy()
    selected, selected_facts = read_selected_canonical_packet_shard(
        manifest_path.parent / shard[0]["filename"],
        wanted_keys,
        R3_AUTHORITY_SHARD_SHA256,
    )
    del wanted_keys
    selected_count = int(comm.allreduce(len(selected)))
    return selected, {
        "source_sha": R3_AUTHORITY_SOURCE_SHA,
        "manifest_relative_path": R3_AUTHORITY_MANIFEST.as_posix(),
        "manifest_sha256": R3_AUTHORITY_MANIFEST_SHA256,
        "shard_sha256": R3_AUTHORITY_SHARD_SHA256,
        "packet_count": R3_AUTHORITY_PACKET_COUNT,
        "selected_packet_count": selected_count,
        "selected_facts": dict(selected_facts),
        "role": "full_fe_dual",
        "authority": "v7_mpi1_source_authority_r3_physical_key_packets",
    }


def run_worker(
    root: Path,
    record_path: Path,
    source_sha: str,
    input_path: Path,
    expected_size: int,
) -> None:
    root = _absolute(root)
    cache_dir = root / "jit_cache"
    cache_dir = cache_dir.resolve()
    import os

    os.environ["XDG_CACHE_HOME"] = str(cache_dir)
    if not cache_dir.is_dir() or Path(os.environ["XDG_CACHE_HOME"]).resolve() != cache_dir:
        raise FileNotFoundError("worker parent-owned jit_cache is not bound")

    from mpi4py import MPI
    from petsc4py import PETSc

    comm = MPI.COMM_WORLD
    source = authority_runner._source_facts(REPO_ROOT, source_sha, input_path)
    raw_dir, marker_dir = authority_runner._prepare_worker_paths(root, comm)
    record_path = _absolute(record_path)
    if record_path != raw_dir / "worker_record.json":
        raise ValueError("action worker record must be raw/worker_record.json")
    cache_facts = {
        "xdg_cache_home": str(Path(os.environ["XDG_CACHE_HOME"]).resolve()),
        "binding": True,
    }
    _worker_marker(comm, marker_dir, "paths_ready", source_sha, cache=cache_facts)
    runtime = authority_runner._runtime_facts(comm, PETSc, expected_size)
    _worker_marker(comm, marker_dir, "abi_ready", source_sha, runtime=runtime)

    case = None
    r3_packets = None
    probe_facts: list[dict[str, Any]] = []
    action_manifests: dict[str, dict[str, Any]] = {}
    input_facts = None
    mode_facts = None
    try:
        from benchmarks.run_task038_full3d_r3 import _current_input
        from src.solvers.fullspace_dtn_action import build_dynamic_mode_inventory
        from src.solvers.fullspace_same_mesh_physical_pcoarse import (
            build_small_same_mesh_action_probe_source,
            build_small_same_mesh_physical_pcoarse_case,
            destroy_small_same_mesh_physical_pcoarse_case,
            measure_small_same_mesh_physical_action_identity,
        )
        from src.solvers.hcurl_canonical_vector_dolfinx import (
            extract_canonical_full_fe_dual_packets,
        )

        _specification, cfg10, _resolved, input_facts = _current_input(
            REPO_ROOT, _absolute(input_path)
        )
        cfg50 = copy.deepcopy(cfg10)
        cfg50.nedelec_degree = 6
        cfg50.mesh_target_size = 50.0
        modes, _rows, mode_sha = build_dynamic_mode_inventory(cfg50)
        if len(modes) != MODE_COUNT or str(mode_sha) != MODE_MANIFEST_SHA256:
            raise RuntimeError("h50 mode inventory identity changed")
        mode_facts = {
            "mode_count": MODE_COUNT,
            "mode_manifest_sha256": str(mode_sha),
            "tested_pair": [6, 3],
            "tested_mesh_target_size_nm": 50.0,
        }
        case = build_small_same_mesh_physical_pcoarse_case(cfg50, comm)
        _worker_marker(comm, marker_dir, "case_built", source_sha, mode=mode_facts)
        r3_packets, r3_authority = _load_r3_packets(case, comm)
        _worker_marker(
            comm,
            marker_dir,
            "probe_execution_started",
            source_sha,
            probe_names=list(PROBE_NAMES),
            r3_authority=r3_authority,
        )

        p3_space = case["setup"]["spaces"][3]
        p3_floquet = case["setup"]["floquets"][3]
        comm = p3_space.mesh.comm
        p3_audit = _compact_action_audit(case["p3_action"]["action"])
        p6_audit = _compact_action_audit(case["p6_action"]["action"])
        for name in PROBE_NAMES:
            source_vector = None
            direct = composed = direct_repeat = composed_repeat = None
            direct_scaled = composed_scaled = scaled_source = None
            try:
                source_vector, source_generation = build_small_same_mesh_action_probe_source(
                    case, name, r3_packets=r3_packets
                )
                source_before = authority_runner._owned_slave_facts(
                    source_vector, p3_floquet.mpc, comm
                )
                direct, composed, first_facts = (
                    measure_small_same_mesh_physical_action_identity(
                        case, source_vector
                    )
                )
                direct_repeat, composed_repeat, _ = (
                    measure_small_same_mesh_physical_action_identity(
                        case, source_vector
                    )
                )
                scaled_source = source_vector.copy()
                scaled_source.scale(ALPHA)
                direct_scaled, composed_scaled, _scaled_facts = (
                    measure_small_same_mesh_physical_action_identity(
                        case, scaled_source
                    )
                )
                source_after = authority_runner._owned_slave_facts(
                    source_vector, p3_floquet.mpc, comm
                )
                source_rank_facts = comm.gather(
                    {
                        "rank": int(comm.rank),
                        "before_sha256": source_before["array_sha256"],
                        "after_sha256": source_after["array_sha256"],
                        "input_unchanged": (
                            source_before["array_sha256"]
                            == source_after["array_sha256"]
                        ),
                    },
                    root=0,
                )
                direct_packets, direct_audit = extract_canonical_full_fe_dual_packets(
                    p3_space, p3_floquet.mpc, direct
                )
                composed_packets, composed_audit = extract_canonical_full_fe_dual_packets(
                    p3_space, p3_floquet.mpc, composed
                )
                direct_repeat_packets, direct_repeat_audit = extract_canonical_full_fe_dual_packets(
                    p3_space, p3_floquet.mpc, direct_repeat
                )
                composed_repeat_packets, composed_repeat_audit = extract_canonical_full_fe_dual_packets(
                    p3_space, p3_floquet.mpc, composed_repeat
                )
                direct_scaled_packets, direct_scaled_audit = extract_canonical_full_fe_dual_packets(
                    p3_space, p3_floquet.mpc, direct_scaled
                )
                composed_scaled_packets, composed_scaled_audit = extract_canonical_full_fe_dual_packets(
                    p3_space, p3_floquet.mpc, composed_scaled
                )
                galerk_relative = _packet_relative(
                    direct_packets, composed_packets, comm
                )
                repeat_relative = max(
                    _packet_relative(direct_packets, direct_repeat_packets, comm),
                    _packet_relative(composed_packets, composed_repeat_packets, comm),
                )
                direct_scale_expected = direct.copy()
                composed_scale_expected = composed.copy()
                direct_scale_expected.scale(ALPHA)
                composed_scale_expected.scale(ALPHA)
                linearity_relative = max(
                    _vector_relative(direct_scaled, direct_scale_expected),
                    _vector_relative(composed_scaled, composed_scale_expected),
                )
                direct_scale_expected.destroy()
                composed_scale_expected.destroy()
                labels = {
                    "direct": direct_packets,
                    "composed": composed_packets,
                    "direct_repeat": direct_repeat_packets,
                    "composed_repeat": composed_repeat_packets,
                    "direct_scaled": direct_scaled_packets,
                    "composed_scaled": composed_scaled_packets,
                }
                output_audits = {
                    "direct": direct_audit,
                    "composed": composed_audit,
                    "direct_repeat": direct_repeat_audit,
                    "composed_repeat": composed_repeat_audit,
                    "direct_scaled": direct_scaled_audit,
                    "composed_scaled": composed_scaled_audit,
                }
                descriptors = {
                    label: _write_packet_manifest(
                        raw_dir,
                        f"{name}.{label}",
                        packets,
                        {
                            **dict(output_audits[label]),
                            "probe": name,
                            "output": label,
                        },
                        comm,
                    )
                    for label, packets in labels.items()
                }
                action_manifests[name] = descriptors
                direct_facts = authority_runner._owned_slave_facts(
                    direct, p3_floquet.mpc, comm
                )
                composed_facts = authority_runner._owned_slave_facts(
                    composed, p3_floquet.mpc, comm
                )
                probe_facts.append(
                    {
                        "name": name,
                        "source_generation": _jsonable(source_generation),
                        "source_before": source_before,
                        "source_after": source_after,
                        "source_rank_facts": source_rank_facts,
                        "source_input_unchanged_relative": float(
                            first_facts["input_unchanged_relative"]
                        ),
                        "direct": direct_facts,
                        "composed": composed_facts,
                        "physical_galerkin_relative": float(galerk_relative),
                        "repeat_relative_l2": float(repeat_relative),
                        "linearity_relative_l2": float(linearity_relative),
                        "p_p_h_work_identity_relative": float(
                            first_facts["p_p_h_work_identity_relative"]
                        ),
                        "work_lhs": first_facts["work_lhs"],
                        "work_rhs": first_facts["work_rhs"],
                        "phase_application": first_facts["phase_application"],
                        "projected_full_constraint_residual": float(
                            first_facts["projected_full_constraint_residual"]
                        ),
                        "algebraic_owned_slave_max": float(
                            first_facts["algebraic_owned_slave_max"]
                        ),
                        "packet_manifests": descriptors,
                    }
                )
            finally:
                for vector in (
                    direct_scaled,
                    composed_scaled,
                    direct_repeat,
                    composed_repeat,
                    direct,
                    composed,
                    scaled_source,
                    source_vector,
                ):
                    if vector is not None:
                        vector.destroy()
        _worker_marker(
            comm,
            marker_dir,
            "probe_execution_complete",
            source_sha,
            probe_count=len(probe_facts),
        )
        del r3_packets
        r3_packets = None
        destroy_small_same_mesh_physical_pcoarse_case(case)
        case = None
        gc.collect()
        _worker_marker(comm, marker_dir, "release_complete", source_sha)
        action_manifest_path = raw_dir / "canonical" / "action.manifest.json"
        if int(comm.rank) == 0:
            action_manifest = {
                "schema": ACTION_MANIFEST_SCHEMA,
                "role": "full_fe_dual_action_outputs",
                "mpi_size": int(comm.size),
                "probe_order": list(PROBE_NAMES),
                "outputs": action_manifests,
            }
            _write_json(action_manifest_path, action_manifest)
        comm.barrier()
        action_manifest_sha256 = authority_runner.sha256_file(action_manifest_path)
        worker_record = {
            "schema": WORKER_SCHEMA,
            "raw_facts_only": True,
            "source": source,
            "runtime": runtime,
            "input": input_facts,
            "cache": cache_facts,
            "mode_inventory": mode_facts,
            "paths": {
                "cache_dir": "jit_cache",
                "record": "raw/worker_record.json",
                "action_manifest": "raw/canonical/action.manifest.json",
            },
            "action_manifest_sha256": action_manifest_sha256,
            "architecture": {
                "p3_action": p3_audit,
                "p6_action": p6_audit,
                "p63": {
                    "operator": "same_mesh_owner_transfer",
                    "numeric_allgather": False,
                    "global_matrix_materialized": False,
                },
                "canonical_output_role": "full_fe_dual",
                "phase_once": "finalized_floquet_mpc_once",
            },
            "r3_authority": r3_authority,
            "probes": probe_facts,
        }
        if int(comm.rank) == 0:
            _write_json(record_path, _jsonable(worker_record))
        comm.barrier()
        _worker_marker(comm, marker_dir, "record_written", source_sha)
    finally:
        if r3_packets is not None:
            del r3_packets
        if case is not None:
            destroy_small_same_mesh_physical_pcoarse_case(case)
        gc.collect()


def run_parent(
    root: Path,
    record_path: Path,
    source_sha: str,
    input_path: Path,
    expected_size: int,
) -> int:
    root, cache = authority_runner._prepare_parent_root(root)
    record_path = _absolute(record_path)
    if record_path.parent != root:
        raise ValueError("action parent record must be directly below root")
    children_dir = root / "children"
    children_dir.mkdir(exist_ok=False)
    process_path = root / "parent_process.jsonl"
    source = authority_runner._source_facts(REPO_ROOT, source_sha, input_path)
    cache_initial = authority_runner._cache_snapshot(cache)
    children: list[dict[str, Any]] = []
    worker_result = None
    error = None
    cache_before = None
    cache_after = None
    rss_watchdog_bytes = _rss_watchdog_bytes(expected_size)
    try:
        for index, group in enumerate(JIT_GROUPS):
            stem = f"{index:02d}_{group.replace('-', '_')}"
            child_record = children_dir / f"{stem}.json"
            child = authority_runner._run_parent_child(
                authority_runner._child_command(
                    group, cache, child_record, source_sha, _absolute(input_path)
                ),
                process_path,
                f"precompile:{group}",
                children_dir / f"{stem}.stdout.log",
                children_dir / f"{stem}.stderr.log",
                rss_watchdog_bytes=rss_watchdog_bytes,
            )
            child["group"] = group
            children.append(child)
            if (
                child["returncode"] != 0
                or child["stop_reason"] is not None
                or not child["process_group_gone"]
            ):
                raise RuntimeError(f"precompile lifecycle failed: {group}")
        cache_before = authority_runner._cache_snapshot(cache)
        worker_record = root / "raw" / "worker_record.json"
        worker_result = authority_runner._run_parent_child(
            _worker_command(
                root, worker_record, source_sha, _absolute(input_path), expected_size
            ),
            process_path,
            "worker",
            root / "worker.stdout.log",
            root / "worker.stderr.log",
            rss_watchdog_bytes=rss_watchdog_bytes,
        )
        cache_after = authority_runner._cache_snapshot(cache)
        if (
            worker_result["returncode"] != 0
            or worker_result["stop_reason"] is not None
            or not worker_result["process_group_gone"]
        ):
            raise RuntimeError("action worker lifecycle failed")
        if cache_before != cache_after:
            raise RuntimeError("action worker changed the parent-owned JIT cache")
    except Exception as exc:
        error = str(exc)

    process = (
        authority_runner._process_summary(process_path)
        if process_path.is_file()
        else None
    )
    marker_dir = root / "markers"
    marker_manifest_path = root / "marker_manifest.json"
    marker_rows = []
    if marker_dir.is_dir():
        for path in authority_runner.marker_files(marker_dir, order=MARKER_ORDER):
            marker_rows.append(
                {
                    "name": path.stem.split("_", 1)[1],
                    "sha256": authority_runner.sha256_file(path),
                }
            )
    if marker_rows and not marker_manifest_path.exists():
        _write_json(marker_manifest_path, marker_rows)
    worker_record = root / "raw" / "worker_record.json"
    parent_record = {
        "schema": PARENT_SCHEMA,
        "source": source,
        "workflow": WORKFLOW,
        "phase": PHASE,
        "expected_mpi_size": int(expected_size),
        "rss_watchdog_bytes": rss_watchdog_bytes,
        "command": {
            "argv": [str(value) for value in sys.argv],
            "worker_argv": [] if worker_result is None else worker_result["argv"],
            "cwd": str(REPO_ROOT),
        },
        "paths": {
            "jit_cache": "jit_cache",
            "process_samples": "parent_process.jsonl",
            "worker_record": "raw/worker_record.json",
            "action_manifest": "raw/canonical/action.manifest.json",
            "marker_manifest": "marker_manifest.json",
        },
        "jit_groups": list(JIT_GROUPS),
        "cache": {
            "initial": cache_initial,
            "before_worker": cache_before,
            "after_worker": cache_after,
        },
        "children": children,
        "process": process,
        "worker": (
            None
            if worker_result is None
            else {
                **worker_result,
                "record_present": worker_record.is_file(),
                "record_sha256": (
                    authority_runner.sha256_file(worker_record)
                    if worker_record.is_file()
                    else None
                ),
                "stdout_sha256": authority_runner.sha256_file(root / "worker.stdout.log"),
                "stderr_sha256": authority_runner.sha256_file(root / "worker.stderr.log"),
            }
        ),
        "markers": (
            None
            if not marker_manifest_path.is_file()
            else {
                "manifest_relative_path": "marker_manifest.json",
                "manifest_sha256": authority_runner.sha256_file(marker_manifest_path),
                "names": [row["name"] for row in marker_rows],
            }
        ),
        "error": error,
    }
    _write_json(record_path, parent_record)
    return 0 if error is None else 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=(PHASE,), required=True)
    parser.add_argument("--mode", choices=("parent", "worker"), required=True)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--record", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument(
        "--mpi-size",
        "--expected-mpi-size",
        dest="mpi_size",
        type=int,
        choices=EXPECTED_MPI_SIZES,
        required=True,
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = _absolute(args.artifact_root)
    record = _absolute(args.record)
    input_path = _absolute(args.input)
    if args.mode == "parent":
        return run_parent(root, record, args.source_sha, input_path, args.mpi_size)
    run_worker(root, record, args.source_sha, input_path, args.mpi_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
