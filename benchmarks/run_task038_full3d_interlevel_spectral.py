"""Thin Route-A p6/h10 material-class and global-probe worker."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping

from src.solvers.fullspace_lor_interlevel_route_selection import PROBE_NAMES


BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
STAGE = "r1"
CASE = "p6-h10-mpi1"
MODULE = "benchmarks.run_task038_full3d_interlevel_spectral"
DEGREE = 6
H_NM = 10.0
MPI_SIZE = 1
MARKERS = (
    "startup",
    "preflight",
    "foundation",
    "class_inventory",
    "classes_complete",
    "local_gate_failed",
    "level3_complete",
    "level3_not_run",
    "probes_complete",
    "probes_not_run",
    "release",
    "record_closeout",
)
SOURCE_NAMES = tuple(PROBE_NAMES)
PASS_MARKERS = (
    "startup", "preflight", "foundation", "class_inventory", "classes_complete",
    "level3_complete", "probes_complete", "release",
)
FAIL_MARKERS = (
    "startup", "preflight", "foundation", "class_inventory", "classes_complete",
    "local_gate_failed", "level3_not_run", "probes_not_run", "release",
)


def _marker(
    marker_root: Path,
    name: str,
    source_sha: str,
    comm: Any,
    jsonable: Any,
    **facts: Any,
) -> int:
    if name not in MARKERS:
        raise ValueError(f"unknown Route-A marker: {name}")
    import time

    wall_time_ns = comm.bcast(time.time_ns() if comm.rank == 0 else None, root=0)
    if comm.rank == 0:
        path = marker_root / "markers" / f"{name}.json"
        path.write_bytes(
            json.dumps(
                {
                    "schema": "task038.full3d.interlevel-spectral.r1-marker.v1",
                    "marker": name,
                    "source_sha": source_sha,
                    "wall_time_ns": int(wall_time_ns),
                    "facts": jsonable(facts),
                },
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            + b"\n"
        )
        with path.open("rb") as stream:
            os.fsync(stream.fileno())
    comm.barrier()
    return int(wall_time_ns)


def _array_descriptor(value: Any) -> dict[str, Any]:
    import numpy as np

    array = np.ascontiguousarray(np.asarray(value))
    if array.dtype.hasobject:
        raise TypeError("object dtype is forbidden in raw arrays")
    return {
        "dtype": str(array.dtype),
        "shape": [int(item) for item in array.shape],
        "sha256": hashlib.sha256(array.view(np.uint8)).hexdigest(),
    }


def _write_raw_arrays(raw_dir: Path, arrays: Mapping[str, Any]) -> dict[str, Any]:
    import numpy as np

    path = raw_dir / "route_a_arrays.npz"
    np.savez_compressed(path, **{str(key): np.asarray(value) for key, value in arrays.items()})
    return {
        "relative_path": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "arrays": {str(key): _array_descriptor(value) for key, value in arrays.items()},
    }


def _probe_array_roles(name: str) -> dict[str, str]:
    return {
        role: f"probe__{name}__{role}"
        for role in (
            "source_before", "source_after", "source2", "projected",
            "projected_repeat", "projected2", "projected_combo", "fine_dual",
            "adjoint", "b3", "b6p",
        )
    }


def _p63_facts(value: Any) -> dict[str, Any]:
    import numpy as np

    matrix = np.ascontiguousarray(np.asarray(value, dtype=np.complex128))
    singular = np.linalg.svd(matrix, compute_uv=False)
    sigma_max = float(singular[0])
    threshold = max(matrix.shape) * np.finfo(float).eps * sigma_max
    return {
        "shape": [int(item) for item in matrix.shape],
        "dtype": str(matrix.dtype),
        "sigma_min": float(singular[-1]),
        "sigma_max": sigma_max,
        "rank_threshold": float(threshold),
        "rank": int(np.count_nonzero(singular > threshold)),
        "finite": bool(np.all(np.isfinite(matrix))),
    }


def _forbidden_architecture(case_audit: Mapping[str, Any], extension_audit: Mapping[str, Any]) -> dict[str, bool]:
    case_names = (
        "global_high_order_aij", "global_dense_transfer", "global_numeric_allgather",
        "numeric_allgather", "scalar_node_matrix_built", "global_direct_coarse_built",
        "recovery_field_arrays_built", "p6_exact_edge_factor_built", "hx_hierarchy_built",
        "pcgamg_hierarchy_built", "physical_solve", "recovery",
    )
    extension_names = (
        "global_high_order_aij", "global_transfer_matrix", "numeric_allgather",
        "p1_global_direct_factor", "p1_built", "smoother_built", "ksp_created",
        "physical_solve", "recovery",
    )
    result: dict[str, bool] = {}
    for name in case_names:
        result[f"case.{name}"] = bool(case_audit[name])
    for name in extension_names:
        result[f"extension.{name}"] = bool(extension_audit[name])
    result.update({
        "global_high_order_aij": bool(case_audit["global_high_order_aij"] or extension_audit["global_high_order_aij"]),
        "global_transfer_matrix": bool(case_audit["global_transfer_matrix"] or extension_audit["global_transfer_matrix"]),
        "numeric_allgather": bool(case_audit["numeric_allgather"] or extension_audit["numeric_allgather"]),
        "p1_global_direct_factor": bool(extension_audit["p1_global_direct_factor"]),
        "p1_built": bool(extension_audit["p1_built"]),
        "smoother_built": bool(extension_audit["smoother_built"]),
        "ksp_created": bool(extension_audit["ksp_created"]),
        "physical_solve": bool(case_audit["physical_solve"] or extension_audit["physical_solve"]),
        "recovery": bool(case_audit["recovery"] or extension_audit["recovery"]),
    })
    return result


def run_worker(
    raw_dir: Path,
    record_path: Path,
    input_path: Path,
    expected_sha: str,
    expected_mpi: int,
    r3_manifest: Path,
) -> None:
    """Build one MPI1 evidence case; no worker status is written."""

    from mpi4py import MPI

    from benchmarks.run_task038_full3d_lor_s2_memory_first import (
        _input_identity,
        _prepare_paths,
        _runtime,
        _source_identity,
        _write_json,
    )
    from benchmarks.canonical_vector_artifacts import (
        read_canonical_manifest,
        read_canonical_packet_shards,
    )
    from benchmarks.run_task038_full3d_r4 import _resolve_case
    from src.solvers.fullspace_lor_interlevel_spectral import (
        build_route_a_probe_extension_from_foundation,
    )
    from src.solvers.fullspace_lor_interlevel_spectral_dolfinx import (
        R3_LONG_TAIL_MANIFEST_SHA256,
        audit_material_classes,
        build_material_class_inventory,
        build_probe_source,
        measure_probe,
        source_generation_identity,
    )
    from src.solvers.fullspace_lor_memory_first_foundation import (
        build_s2_foundation_case,
    )
    from src.solvers.fullspace_lor_memory_hierarchy import build_local_interlevel_edge_transfer

    comm = MPI.COMM_WORLD
    if int(expected_mpi) != MPI_SIZE or comm.size != MPI_SIZE:
        raise RuntimeError("Route-A evidence worker is fixed to MPI1")
    root = Path(__file__).resolve().parents[1]
    raw_dir = (raw_dir if raw_dir.is_absolute() else root / raw_dir).resolve()
    record_path = (record_path if record_path.is_absolute() else root / record_path).resolve()
    input_path = (input_path if input_path.is_absolute() else root / input_path).resolve()
    r3_manifest = (r3_manifest if r3_manifest.is_absolute() else root / r3_manifest).resolve()
    _prepare_paths(raw_dir, record_path, comm)
    jsonable = __import__(
        "benchmarks.run_task038_full3d_lor_s2_memory_first",
        fromlist=["_jsonable"],
    )._jsonable
    marker_times: dict[str, int] = {}
    marker_names: list[str] = []

    def emit(name: str, **facts: Any) -> None:
        marker_names.append(name)
        marker_times[name] = _marker(raw_dir, name, expected_sha, comm, jsonable, **facts)

    emit("startup", raw_dir=str(raw_dir))
    runtime = _runtime(root, expected_sha, comm)
    emit("preflight", runtime=runtime)
    specification, cfg, resolved = _resolve_case(root, input_path, DEGREE, H_NM)
    input_identity = _input_identity(root, input_path, specification, resolved)
    r3_manifest = r3_manifest.resolve()
    r3_manifest_data = read_canonical_manifest(r3_manifest, R3_LONG_TAIL_MANIFEST_SHA256)
    r3_shards = tuple(r3_manifest.parent / item["filename"] for item in r3_manifest_data["per_rank_shards"])
    r3_packets = read_canonical_packet_shards(
        r3_shards, tuple(item["file_sha256"] for item in r3_manifest_data["per_rank_shards"])
    )
    r3_sha = hashlib.sha256(r3_manifest.read_bytes()).hexdigest()
    case = None
    extension = None
    try:
        case = build_s2_foundation_case(
            raw_dir, comm, cfg, resolved_config=resolved,
            resource_sample=None,
        )
        case_audit = dict(case.audit)
        case_audit["global_transfer_matrix"] = bool(
            case_audit.get("global_transfer_matrix", case_audit.get("global_dense_transfer", False))
        )
        case_audit["physical_solve"] = bool(case_audit.get("physical_solve", False))
        case_audit["recovery"] = bool(case_audit.get("recovery", False))
        emit("foundation", architecture=case_audit)
        inventory = build_material_class_inventory(case)
        emit("class_inventory", inventory={key: value for key, value in inventory.items() if key != "class_inventory_by_rank"})
        local_transfer = build_local_interlevel_edge_transfer(6, 3)
        class_audits, arrays = audit_material_classes(
            inventory, local_transfer.edge_transfer,
        )
        emit("classes_complete", class_count=len(class_audits), p63_shape=list(local_transfer.edge_shape))
        local_gate_passed = bool(class_audits) and all(
            audit.get("gate_passed") is True and audit.get("gate_failures") == []
            for audit in class_audits
        )
        extension_audit: dict[str, Any] = {
            "global_high_order_aij": False, "global_transfer_matrix": False,
            "numeric_allgather": False, "p1_global_direct_factor": False,
            "p1_built": False, "smoother_built": False, "ksp_created": False,
            "physical_solve": False, "recovery": False,
            "not_run_by_local_gate": not local_gate_passed,
        }
        level_facts: dict[str, Any] = {}
        probe_facts: list[dict[str, Any]] = []
        if local_gate_passed:
            extension = build_route_a_probe_extension_from_foundation(case, local_transfer)
            extension_audit = dict(extension.audit)
            emit("level3_complete", extension=extension_audit)
            for name in SOURCE_NAMES:
                source = build_probe_source(name, case, extension, r3_packets)
                try:
                    facts, probe_arrays = measure_probe(name, case, extension, source)
                finally:
                    source.destroy()
                roles = _probe_array_roles(name)
                for role, key in roles.items():
                    arrays[key] = probe_arrays[role]
                facts["raw_roles"] = roles
                facts["source_generation"] = source_generation_identity(name)
                probe_facts.append(facts)
            emit("probes_complete", probe_names=list(SOURCE_NAMES), probe_count=len(probe_facts))
            for degree, level in ((6, extension.levels[0]), (3, extension.levels[1])):
                facts = dict(level.audit)
                facts["parent_topology"] = dict(level.parent_topology.audit)
                facts["raw_topology"] = dict(level.raw_topology.audit)
                level_facts[f"level{degree}"] = facts
        else:
            emit("local_gate_failed", class_gate_failures=[audit.get("gate_failures", []) for audit in class_audits])
            emit("level3_not_run", reason="local_material_class_gate")
            emit("probes_not_run", reason="local_material_class_gate")
            level_facts = {
                "level6": {"foundation_built": True, "not_run_by_local_gate": False},
                "level3": {"foundation_built": False, "not_run_by_local_gate": True},
            }
        raw_descriptor = _write_raw_arrays(raw_dir, arrays)
        record = {
            "schema": "task038.full3d.interlevel-spectral.r1-record.v1",
            "stage": STAGE,
            "case": CASE,
            "degree": DEGREE,
            "h_nm": H_NM,
            "wavelength_nm": 13.5,
            "mpi_size": int(comm.size),
            "branch": BRANCH,
            "raw_dir": str(raw_dir),
            "record_path": str(record_path),
            "command": [
                str(Path(sys.executable).absolute()), "-m", MODULE,
                "--stage", STAGE, "--case", CASE,
                "--raw-dir", str(raw_dir), "--record", str(record_path),
                "--expected-source-sha", expected_sha,
                "--expected-mpi-size", str(expected_mpi),
                "--input", str(input_path),
                "--r3-long-tail-manifest", str(r3_manifest),
            ],
            "source": {"start": runtime["source"], "end": _source_identity(root, expected_sha)},
            "runtime": runtime,
            "input_identity": input_identity,
            "provenance": {
                "r3_long_tail_manifest_path": str(r3_manifest),
                "r3_long_tail_manifest_sha256": r3_sha,
                "r3_long_tail_expected_sha256": R3_LONG_TAIL_MANIFEST_SHA256,
                "r3_long_tail_source_sha": "2c8fca90c7300b85b30021081868b699c0b306d2",
                "p63_constructed_once": True,
                "p63_construction_count": 1,
                "p63_construction_source": "build_local_interlevel_edge_transfer(6,3)",
            },
            "settings": {
                "probe_names": list(SOURCE_NAMES),
                "probe_alpha": [0.37, 0.19],
                "probe_beta": [-0.23, 0.41],
                "source_canonicalization": "owner_roundtrip_reduced_primal",
                "rank": 144,
                "levels": [6, 3],
                "transfer_pair": [6, 3],
                "lambda_min_limit": 0.10,
                "lambda_max_limit": 10.0,
                "condition_limit": 100.0,
                "hermitian_limit": 1.0e-12,
                "endpoint_residual_limit": 1.0e-10,
                "adjoint_limit": 1.0e-12,
                "linearity_limit": 1.0e-12,
                "repeat_limit": 1.0e-13,
                "probe_q_interval": [0.10, 10.0],
                "phase_once": "once_in_canonical_owner_route",
            },
            "architecture": {
                "case": case_audit,
                "extension": extension_audit,
                "forbidden": _forbidden_architecture(case_audit, extension_audit),
                "levels": level_facts,
                "global_high_order_aij": False,
                "global_transfer_matrix": False,
                "numeric_allgather": False,
                "p1_built": False,
                "level1_built": False,
                "smoother_built": False,
                "ksp_created": False,
                "physical_solve": False,
                "recovery": False,
            },
            "material_inventory": inventory,
            "material_classes": class_audits,
            "local_gate_passed": local_gate_passed,
            "not_run_by_local_gate": [] if local_gate_passed else ["level3", "global_probes"],
            "raw_arrays": raw_descriptor,
            "probes": probe_facts,
            "p63_audit": _p63_facts(local_transfer.edge_transfer),
            "markers": {"relative_dir": "markers", "names": marker_names, "wall_time_ns": marker_times},
            "record_authority": "raw-facts-only; checker derives classification",
        }
        if extension is not None:
            extension.destroy()
            extension = None
        case.destroy()
        case = None
        emit("release", destroyed=True)
        record["markers"]["wall_time_ns"] = marker_times
        if comm.rank == 0:
            _write_json(record_path, record)
        comm.barrier()
        emit(
            "record_closeout",
            record_path=str(record_path),
            record_sha256=hashlib.sha256(record_path.read_bytes()).hexdigest() if comm.rank == 0 else None,
        )
    finally:
        if extension is not None:
            extension.destroy()
        if case is not None:
            case.destroy()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=(STAGE,), required=True)
    parser.add_argument("--case", choices=(CASE,), required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-mpi-size", type=int, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--r3-long-tail-manifest", type=Path, required=True)
    args = parser.parse_args(argv)
    run_worker(
        args.raw_dir, args.record, args.input, args.expected_source_sha,
        args.expected_mpi_size, args.r3_long_tail_manifest,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
