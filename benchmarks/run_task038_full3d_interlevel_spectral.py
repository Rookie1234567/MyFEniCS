"""Shared Route-A/Route-B worker with a prospective A0 stable-adjoint profile."""

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
ROUTE_B = "b"
ROUTE_B_STAGE = "r3"
ROUTE_B_SCHEMA = "task038.full3d.interlevel-spectral.r3-record.v1"
ROUTE_B_MARKER_SCHEMA = "task038.full3d.interlevel-spectral.r3-marker.v1"
ROUTE_B_PROBE_SCHEMA = "task038.route-b.global-probe.v1"
ROUTE_B_CANDIDATE = "lor_edge_geometric_mg_6_2_1_nested_v1"
A0_STAGE = "a0"
A0_CASES = ("p6-h10-mpi1", "p6-h10-mpi2")
A0_SCHEMA = "task038.full3d.interlevel-stable-adjoint.a0-record.v1"
A0_MARKER_SCHEMA = "task038.full3d.interlevel-stable-adjoint.a0-marker.v1"
A0_RAW_SCHEMA = "task038.full3d.interlevel-stable-adjoint.a0-raw-manifest.v1"
A0_MARKERS = (
    "startup", "preflight", "foundation", "class_inventory", "classes_complete",
    "level3_complete", "probes_complete", "release", "record_closeout",
)
A0_PROBE_NAMES = tuple(PROBE_NAMES)
MARKERS = (
    "startup",
    "preflight",
    "foundation",
    "class_inventory",
    "classes_complete",
    "level2_complete",
    "level2_not_run",
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
    marker_schema: str = "task038.full3d.interlevel-spectral.r1-marker.v1",
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
                    "schema": marker_schema,
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


def _write_raw_arrays(
    raw_dir: Path, arrays: Mapping[str, Any], *, filename: str = "route_a_arrays.npz",
) -> dict[str, Any]:
    import numpy as np

    path = raw_dir / filename
    np.savez_compressed(path, **{str(key): np.asarray(value) for key, value in arrays.items()})
    return {
        "relative_path": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "arrays": {str(key): _array_descriptor(value) for key, value in arrays.items()},
    }


def _probe_array_roles(name: str, *, coarse_action_role: str = "B3") -> dict[str, str]:
    coarse_key = "b2" if coarse_action_role == "B2" else "b3"
    return {
        role: f"probe__{name}__{role}"
        for role in (
            "source_before", "source_after", "source2", "projected",
            "projected_repeat", "projected2", "projected_combo", "fine_dual",
            "adjoint", coarse_key, "b6p",
        )
    }


def _a0_probe_array_roles(name: str) -> dict[str, str]:
    roles = (
        "source_before", "source_after", "source2", "projected",
        "projected_repeat", "projected2", "projected_combo", "fine_dual",
        "adjoint", "b3", "b6p",
        "fine_primal_local_ids", "fine_primal_local",
        "fine_dual_local_ids", "fine_dual_local",
        "coarse_source_local_ids", "coarse_source_local",
        "explicit_adjoint_local_ids", "explicit_adjoint_local",
        "implemented_adjoint_local_ids", "implemented_adjoint_local",
        "implemented_adjoint_owner_ids", "implemented_adjoint_owner",
    )
    return {role: f"a0__{name}__{role}" for role in roles}


def _owner_probe_array_roles() -> dict[str, str]:
    return {
        role: f"owner21__{role}"
        for role in (
            "source_before", "source_after", "source2", "projected",
            "projected_repeat", "projected2", "projected_combo", "fine_dual",
            "adjoint",
        )
    }


def _transfer_matrix_facts(value: Any) -> dict[str, Any]:
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


def _compact_local_transfer(transfer: Any) -> dict[str, Any]:
    """Serialize one actual cell-local transfer in the Route-B contract shape."""

    import numpy as np

    edge = np.ascontiguousarray(np.asarray(transfer.edge_transfer, dtype=np.complex128))
    node = np.ascontiguousarray(np.asarray(transfer.node_transfer, dtype=np.complex128))
    audit = dict(transfer.audit)
    audit["edge_nnz"] = int(np.count_nonzero(edge))
    audit["node_nnz"] = int(np.count_nonzero(node))
    return {
        "pair": [int(transfer.fine_degree), int(transfer.coarse_degree)],
        "global_transfer_matrix": bool(audit["global_transfer_matrix"]),
        "numeric_allgather": False,
        "local_map": {
            "edge_rows": int(edge.shape[0]),
            "edge_cols": int(edge.shape[1]),
            "edge_exact_nnz": int(np.count_nonzero(edge)),
            "edge_numeric_bytes": int(edge.nbytes),
            "node_rows": int(node.shape[0]),
            "node_cols": int(node.shape[1]),
            "node_exact_nnz": int(np.count_nonzero(node)),
            "node_numeric_bytes": int(node.nbytes),
        },
        "local_transfer": audit,
    }


def _forbidden_architecture(
    case_audit: Mapping[str, Any], extension_audit: Mapping[str, Any],
    *, route: str = "a",
) -> dict[str, bool]:
    case_names = (
        "global_high_order_aij", "global_dense_transfer", "global_numeric_allgather",
        "numeric_allgather", "scalar_node_matrix_built", "global_direct_coarse_built",
        "recovery_field_arrays_built", "p6_exact_edge_factor_built", "hx_hierarchy_built",
        "pcgamg_hierarchy_built", "physical_solve", "recovery",
    )
    extension_names = (
        "global_high_order_aij", "global_transfer_matrix", "numeric_allgather",
        "p1_global_direct_factor", "smoother_built", "ksp_created",
        "physical_solve", "recovery",
    )
    if route == "a":
        extension_names = extension_names[:3] + ("p1_built",) + extension_names[3:]
    else:
        extension_names = extension_names + (
            "p6_exact_factor", "hx_hierarchy_built", "pcgamg_hierarchy_built",
            "retains_per_apply_history",
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
        "p1_built": bool(extension_audit["p1_built"]) if route == "a" else False,
        "smoother_built": bool(extension_audit["smoother_built"]),
        "ksp_created": bool(extension_audit["ksp_created"]),
        "physical_solve": bool(case_audit["physical_solve"] or extension_audit["physical_solve"]),
        "recovery": bool(case_audit["recovery"] or extension_audit["recovery"]),
    })
    return result


def _a0_merge_inventory_groups(
    inventory_groups: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Merge local class rows while retaining the adapter's per-rank authority."""

    inventory = dict(inventory_groups[0])
    inventory_reference = inventory_groups[0]
    for group in inventory_groups[1:]:
        if (
            group.get("schema") != inventory_reference.get("schema")
            or group.get("exact_float64_identity")
            is not inventory_reference.get("exact_float64_identity")
            or group.get("numeric_allgather")
            is not inventory_reference.get("numeric_allgather")
            or group.get("cell_count_global")
            != inventory_reference.get("cell_count_global")
            or group.get("class_inventory_by_rank")
            != inventory_reference.get("class_inventory_by_rank")
        ):
            raise RuntimeError("MPI material inventory authorities disagree")
    inventory_items: dict[str, dict[str, Any]] = {}
    for group in inventory_groups:
        for item in group["classes"]:
            digest = str(item["class_digest"])
            existing = inventory_items.get(digest)
            if existing is None:
                inventory_items[digest] = dict(item)
            else:
                if any(
                    existing.get(field) != item.get(field)
                    for field in ("class_identity", "tag", "material_role")
                ):
                    raise RuntimeError("MPI material class identities disagree")
                existing["cell_count_local"] += int(item["cell_count_local"])
    inventory["classes"] = sorted(
        inventory_items.values(), key=lambda item: item["class_digest"]
    )
    inventory["class_count"] = len(inventory["classes"])
    inventory["cell_count_local"] = int(
        sum(int(group["cell_count_local"]) for group in inventory_groups)
    )
    inventory["class_inventory_by_rank"] = [
        list(items) for items in inventory_reference["class_inventory_by_rank"]
    ]
    return inventory


def run_worker(
    raw_dir: Path,
    record_path: Path,
    input_path: Path,
    expected_sha: str,
    expected_mpi: int,
    r3_manifest: Path,
    route: str = "a",
) -> None:
    """Build one explicit Route-A or Route-B MPI1 evidence case."""

    import numpy as np

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
    route = str(route).lower()
    if route not in {"a", ROUTE_B}:
        raise ValueError("route must be 'a' or 'b'")
    from src.solvers.fullspace_lor_interlevel_spectral import (
        build_route_a_probe_extension_from_foundation,
    )
    from src.solvers.fullspace_lor_nested_interlevel_runtime import (
        build_route_b_nested_hierarchy_extension,
    )
    from src.solvers.fullspace_lor_interlevel_spectral_dolfinx import (
        R3_LONG_TAIL_MANIFEST_SHA256,
        ROUTE_B_SOURCE_GENERATION,
        audit_material_classes,
        build_material_class_inventory,
        build_probe_source,
        measure_probe,
        measure_owner_probe,
        source_generation_identity,
        audit_nested_material_classes,
    )
    from src.solvers.fullspace_lor_memory_first_foundation import (
        build_s2_foundation_case,
    )
    from src.solvers.fullspace_lor_memory_hierarchy import build_local_interlevel_edge_transfer

    comm = MPI.COMM_WORLD
    if int(expected_mpi) != MPI_SIZE or comm.size != MPI_SIZE:
        raise RuntimeError("interlevel evidence worker is fixed to MPI1")
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

    marker_schema = (
        ROUTE_B_MARKER_SCHEMA if route == ROUTE_B
        else "task038.full3d.interlevel-spectral.r1-marker.v1"
    )

    def emit(name: str, **facts: Any) -> None:
        marker_names.append(name)
        marker_times[name] = _marker(
            raw_dir, name, expected_sha, comm, jsonable,
            marker_schema=marker_schema, **facts,
        )

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
        coarse_degree = 2 if route == ROUTE_B else 3
        local_transfer = build_local_interlevel_edge_transfer(6, coarse_degree)
        local_transfer_21 = (
            build_local_interlevel_edge_transfer(2, 1)
            if route == ROUTE_B else None
        )
        if route == ROUTE_B:
            class_audits, arrays = audit_nested_material_classes(
                inventory, local_transfer.edge_transfer,
            )
            arrays["p21"] = np.asarray(
                local_transfer_21.edge_transfer, dtype=np.complex128
            ).copy()
        else:
            class_audits, arrays = audit_material_classes(
                inventory, local_transfer.edge_transfer,
            )
        emit(
            "classes_complete",
            class_count=len(class_audits),
            **({"p62_shape": list(local_transfer.edge_shape)} if route == ROUTE_B
               else {"p63_shape": list(local_transfer.edge_shape)}),
        )
        local_gate_passed = bool(class_audits) and all(
            audit.get("gate_passed") is True and audit.get("gate_failures") == []
            for audit in class_audits
        )
        extension_audit: dict[str, Any] = {
            "global_high_order_aij": False, "global_transfer_matrix": False,
            "numeric_allgather": False, "p1_global_direct_factor": False,
            "p1_built": False,
            "smoother_built": False, "ksp_created": False,
            "physical_solve": False, "recovery": False,
            "not_run_by_local_gate": not local_gate_passed,
        }
        if route == ROUTE_B:
            extension_audit.update({
                "level1_raw_matrix_built": False,
                "p6_exact_factor": False,
                "hx_hierarchy_built": False,
                "pcgamg_hierarchy_built": False,
                "retains_per_apply_history": False,
            })
        level_facts: dict[str, Any] = {}
        probe_facts: list[dict[str, Any]] = []
        owner_probe_facts: dict[str, Any] | None = None
        if local_gate_passed:
            if route == ROUTE_B:
                extension = build_route_b_nested_hierarchy_extension(
                    case,
                    local_transfer_62=local_transfer,
                    local_transfer_21=local_transfer_21,
                )
            else:
                extension = build_route_a_probe_extension_from_foundation(case, local_transfer)
            extension_audit = dict(extension.audit)
            complete_marker = "level2_complete" if route == ROUTE_B else "level3_complete"
            emit(complete_marker, extension=extension_audit)
            probe_schema = (
                ROUTE_B_PROBE_SCHEMA if route == ROUTE_B
                else "task038.full3d.route-a.global-probe.v1"
            )
            source_generation = (
                ROUTE_B_SOURCE_GENERATION if route == ROUTE_B else None
            )
            for name in SOURCE_NAMES:
                source_kwargs = {
                    "fine_degree": 6,
                    "coarse_degree": coarse_degree,
                    "probe_schema": probe_schema,
                }
                if source_generation is not None:
                    source_kwargs["source_generation"] = source_generation
                source = build_probe_source(
                    name, case, extension, r3_packets, **source_kwargs
                )
                try:
                    measure_kwargs = dict(source_kwargs)
                    measure_kwargs["coarse_action_role"] = "B2" if route == ROUTE_B else "B3"
                    facts, probe_arrays = measure_probe(
                        name, case, extension, source, **measure_kwargs
                    )
                finally:
                    source.destroy()
                roles = _probe_array_roles(
                    name, coarse_action_role="B2" if route == ROUTE_B else "B3"
                )
                for role, key in roles.items():
                    arrays[key] = probe_arrays[role]
                facts["raw_roles"] = roles
                facts["source_generation"] = source_generation_identity(
                    name, source_generation
                ) if source_generation is not None else source_generation_identity(name)
                probe_facts.append(facts)
            emit("probes_complete", probe_names=list(SOURCE_NAMES), probe_count=len(probe_facts))
            if route == ROUTE_B:
                owner_probe_facts, owner_arrays = measure_owner_probe(extension)
                owner_roles = _owner_probe_array_roles()
                for role, key in owner_roles.items():
                    arrays[key] = owner_arrays[role]
                owner_probe_facts["raw_roles"] = owner_roles
            level_specs = (
                ((6, extension.levels[6]), (2, extension.levels[2]), (1, extension.levels[1]))
                if route == ROUTE_B
                else ((6, extension.levels[0]), (3, extension.levels[1]))
            )
            for degree, level in level_specs:
                facts = dict(level.audit)
                facts["parent_topology"] = dict(level.parent_topology.audit)
                facts["raw_topology"] = dict(level.raw_topology.audit)
                level_facts[f"level{degree}"] = facts
        else:
            emit("local_gate_failed", class_gate_failures=[audit.get("gate_failures", []) for audit in class_audits])
            emit(
                "level2_not_run" if route == ROUTE_B else "level3_not_run",
                reason="local_material_class_gate",
            )
            emit("probes_not_run", reason="local_material_class_gate")
            level_facts = {
                "level6": {"foundation_built": True, "not_run_by_local_gate": False},
            }
            for degree in ((2, 1) if route == ROUTE_B else (3,)):
                level_facts[f"level{degree}"] = {
                    "foundation_built": False, "not_run_by_local_gate": True,
                }
        raw_descriptor = _write_raw_arrays(
            raw_dir, arrays,
            filename="route_b_arrays.npz" if route == ROUTE_B else "route_a_arrays.npz",
        )
        stage = ROUTE_B_STAGE if route == ROUTE_B else STAGE
        schema = ROUTE_B_SCHEMA if route == ROUTE_B else "task038.full3d.interlevel-spectral.r1-record.v1"
        command = [
            str(Path(sys.executable).absolute()), "-m", MODULE,
            "--stage", stage, "--case", CASE,
            "--raw-dir", str(raw_dir), "--record", str(record_path),
            "--expected-source-sha", expected_sha,
            "--expected-mpi-size", str(expected_mpi),
            "--input", str(input_path),
            "--r3-long-tail-manifest", str(r3_manifest),
        ]
        if route == ROUTE_B:
            command.extend(("--route", ROUTE_B))
        if route == ROUTE_B:
            settings = {
                "probe_names": list(SOURCE_NAMES),
                "probe_alpha": [0.37, 0.19], "probe_beta": [-0.23, 0.41],
                "source_canonicalization": "owner_roundtrip_reduced_primal",
                "rank": 54, "levels": [6, 2, 1], "transfer_pair": [6, 2],
                "lambda_min_limit": 0.50, "lambda_max_limit": 2.0,
                "condition_limit": 4.0, "nested_energy_limit": 1.0e-9,
                "hermitian_limit": 1.0e-12, "endpoint_residual_limit": 1.0e-10,
                "adjoint_limit": 1.0e-11, "linearity_limit": 1.0e-12,
                "repeat_limit": 1.0e-13, "probe_q_center": 1.0,
                "probe_q_abs_limit": 1.0e-9,
                "phase_once": "once_in_canonical_owner_route",
            }
        else:
            settings = {
                "probe_names": list(SOURCE_NAMES),
                "probe_alpha": [0.37, 0.19], "probe_beta": [-0.23, 0.41],
                "source_canonicalization": "owner_roundtrip_reduced_primal",
                "rank": 144, "levels": [6, 3], "transfer_pair": [6, 3],
                "lambda_min_limit": 0.10, "lambda_max_limit": 10.0,
                "condition_limit": 100.0, "hermitian_limit": 1.0e-12,
                "endpoint_residual_limit": 1.0e-10, "adjoint_limit": 1.0e-12,
                "linearity_limit": 1.0e-12, "repeat_limit": 1.0e-13,
                "probe_q_interval": [0.10, 10.0],
                "phase_once": "once_in_canonical_owner_route",
            }
        architecture = {
            "case": case_audit,
            "extension": extension_audit,
            "forbidden": _forbidden_architecture(
                case_audit, extension_audit, route=route,
            ),
            "levels": level_facts,
            "global_high_order_aij": False,
            "global_transfer_matrix": False,
            "numeric_allgather": False,
            "smoother_built": False,
            "ksp_created": False,
            "physical_solve": False,
            "recovery": False,
        }
        if route == ROUTE_B:
            architecture.update({
                "level1_raw_matrix_built": True if local_gate_passed else False,
                "level1_global_direct_factor": False,
                "p1_global_direct_factor": False,
            })
        else:
            architecture.update({"p1_built": False, "level1_built": False})
        local_transfer_facts = None
        if route == ROUTE_B:
            local_transfer_facts = {
                "6_2": _compact_local_transfer(local_transfer),
                "2_1": _compact_local_transfer(local_transfer_21),
            }
        record = {
            "schema": schema,
            "stage": stage,
            "case": CASE,
            "degree": DEGREE,
            "h_nm": H_NM,
            "wavelength_nm": 13.5,
            "mpi_size": int(comm.size),
            "branch": BRANCH,
            "raw_dir": str(raw_dir),
            "record_path": str(record_path),
            "command": command,
            "source": {"start": runtime["source"], "end": _source_identity(root, expected_sha)},
            "runtime": runtime,
            "input_identity": input_identity,
            "provenance": {
                "r3_long_tail_manifest_path": str(r3_manifest),
                "r3_long_tail_manifest_sha256": r3_sha,
                "r3_long_tail_expected_sha256": R3_LONG_TAIL_MANIFEST_SHA256,
                "r3_long_tail_source_sha": "2c8fca90c7300b85b30021081868b699c0b306d2",
                **({
                    "p62_constructed_once": True,
                    "p62_construction_count": 1,
                    "p62_construction_source": "build_local_interlevel_edge_transfer(6,2)",
                    "p21_construction_count": 1,
                    "p21_construction_source": "build_local_interlevel_edge_transfer(2,1)",
                } if route == ROUTE_B else {
                    "p63_constructed_once": True,
                    "p63_construction_count": 1,
                    "p63_construction_source": "build_local_interlevel_edge_transfer(6,3)",
                }),
            },
            "settings": settings,
            "architecture": architecture,
            "material_inventory": inventory,
            "material_classes": class_audits,
            "local_gate_passed": local_gate_passed,
            "not_run_by_local_gate": (
                [] if local_gate_passed else (
                    ["level2", "global_probes", "owner_probe"]
                    if route == ROUTE_B else ["level3", "global_probes"]
                )
            ),
            "raw_arrays": raw_descriptor,
            "probes": probe_facts,
            "markers": {"relative_dir": "markers", "names": marker_names, "wall_time_ns": marker_times},
            "record_authority": "raw-facts-only; checker derives classification",
            **({
                "route": "B",
                "candidate": ROUTE_B_CANDIDATE,
                "local_transfers": local_transfer_facts,
                "p62_audit": _transfer_matrix_facts(local_transfer.edge_transfer),
                "p21_audit": _transfer_matrix_facts(local_transfer_21.edge_transfer),
                "owner_probe": owner_probe_facts,
            } if route == ROUTE_B else {
                "p63_audit": _transfer_matrix_facts(local_transfer.edge_transfer),
            }),
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


def run_a0_worker(
    raw_dir: Path,
    record_path: Path,
    input_path: Path,
    expected_sha: str,
    expected_mpi: int,
    r3_manifest: Path,
    case_name: str,
) -> None:
    """Run the prospective A0 stable-adjoint profile with rank shards."""

    import numpy as np
    from mpi4py import MPI

    from benchmarks.run_task038_full3d_lor_s2_memory_first import (
        _input_identity, _prepare_paths, _runtime, _source_identity, _write_json,
    )
    from benchmarks.canonical_vector_artifacts import (
        read_canonical_manifest, read_canonical_packet_shards,
    )
    from benchmarks.run_task038_full3d_r4 import _resolve_case
    from src.solvers.fullspace_lor_interlevel_spectral import (
        build_route_a_probe_extension_from_foundation,
    )
    from src.solvers.fullspace_lor_interlevel_spectral_dolfinx import (
        R3_LONG_TAIL_MANIFEST_SHA256, audit_material_classes,
        build_material_class_inventory, build_probe_source, measure_probe,
        source_generation_identity,
    )
    from src.solvers.fullspace_lor_memory_first_foundation import (
        build_s2_foundation_case,
    )
    from src.solvers.fullspace_lor_memory_hierarchy import (
        build_local_interlevel_edge_transfer,
    )
    from src.solvers.fullspace_lor_stable_adjoint import (
        audit_stable_adjoint,
    )

    comm = MPI.COMM_WORLD
    if case_name not in A0_CASES or int(expected_mpi) not in (1, 2):
        raise RuntimeError("A0 supports only p6/h10 MPI1 or MPI2")
    if comm.size != int(expected_mpi) or case_name != f"p6-h10-mpi{comm.size}":
        raise RuntimeError("A0 case and MPI size do not match")
    root = Path(__file__).resolve().parents[1]
    raw_dir = (raw_dir if raw_dir.is_absolute() else root / raw_dir).resolve()
    record_path = (record_path if record_path.is_absolute() else root / record_path).resolve()
    input_path = (input_path if input_path.is_absolute() else root / input_path).resolve()
    r3_manifest = (r3_manifest if r3_manifest.is_absolute() else root / r3_manifest).resolve()
    _prepare_paths(raw_dir, record_path, comm)
    marker_times: dict[str, int] = {}
    marker_names: list[str] = []

    def emit(name: str, **facts: Any) -> None:
        if name not in A0_MARKERS:
            raise ValueError(f"unknown A0 marker: {name}")
        marker_names.append(name)
        marker_times[name] = _marker(
            raw_dir, name, expected_sha, comm, _jsonable,
            marker_schema=A0_MARKER_SCHEMA, **facts,
        )

    emit("startup", raw_dir=str(raw_dir), case=case_name)
    runtime = _runtime(root, expected_sha, comm)
    emit("preflight", runtime=runtime)
    specification, cfg, resolved = _resolve_case(root, input_path, DEGREE, H_NM)
    input_identity = _input_identity(root, input_path, specification, resolved)
    r3_data = read_canonical_manifest(r3_manifest, R3_LONG_TAIL_MANIFEST_SHA256)
    r3_shards = tuple(
        r3_manifest.parent / item["filename"]
        for item in r3_data["per_rank_shards"]
    )
    r3_packets = read_canonical_packet_shards(
        r3_shards,
        tuple(item["file_sha256"] for item in r3_data["per_rank_shards"]),
    )
    r3_sha = hashlib.sha256(r3_manifest.read_bytes()).hexdigest()
    case = None
    extension = None
    try:
        case = build_s2_foundation_case(
            raw_dir, comm, cfg, resolved_config=resolved, resource_sample=None,
        )
        case_audit = dict(case.audit)
        emit("foundation", architecture=case_audit)
        inventory_local = build_material_class_inventory(case)
        emit(
            "class_inventory",
            inventory={
                key: value for key, value in inventory_local.items()
                if key != "class_inventory_by_rank"
            },
        )
        p63_transfer = build_local_interlevel_edge_transfer(6, 3)
        class_audits_local, arrays = audit_material_classes(
            inventory_local, p63_transfer.edge_transfer,
        )
        emit(
            "classes_complete",
            class_count=len(class_audits_local),
            p63_shape=list(p63_transfer.edge_shape),
        )
        extension = build_route_a_probe_extension_from_foundation(
            case, p63_transfer,
        )
        extension_audit = dict(extension.audit)
        emit("level3_complete", extension=extension_audit)
        probe_facts_local: list[dict[str, Any]] = []
        for name in A0_PROBE_NAMES:
            source = build_probe_source(name, case, extension, r3_packets)
            try:
                facts, probe_arrays = measure_probe(
                    name, case, extension, source, stable_adjoint=True,
                )
            finally:
                source.destroy()
            roles = _a0_probe_array_roles(name)
            local_arrays = {
                role: probe_arrays[role]
                for role in (
                    "fine_primal_local_ids", "fine_primal_local",
                    "fine_dual_local_ids", "fine_dual_local",
                    "coarse_source_local_ids", "coarse_source_local",
                    "explicit_adjoint_local_ids", "explicit_adjoint_local",
                    "implemented_adjoint_local_ids", "implemented_adjoint_local",
                )
            }
            if comm.size == 1:
                stable_facts = audit_stable_adjoint(
                    coarse_source=probe_arrays["source_before"],
                    fine_primal=probe_arrays["projected"],
                    fine_dual=probe_arrays["fine_dual"],
                    implemented_adjoint=probe_arrays["adjoint"],
                    explicit_adjoint=None,
                    lhs_owner=(
                        local_arrays["fine_primal_local_ids"],
                        local_arrays["fine_primal_local"],
                        local_arrays["fine_dual_local"],
                    ),
                    rhs_owner=(
                        local_arrays["implemented_adjoint_local_ids"],
                        local_arrays["coarse_source_local"],
                        local_arrays["implemented_adjoint_local"],
                        local_arrays["explicit_adjoint_local"],
                    ),
                    ordinary_lhs=(probe_arrays["projected"], probe_arrays["fine_dual"]),
                    ordinary_rhs=(probe_arrays["source_before"], probe_arrays["adjoint"]),
                    reduce_sum=comm.allreduce,
                    reduce_count=lambda value: comm.allreduce(value, op=MPI.SUM),
                    reduce_real=lambda value: float(comm.allreduce(value, op=MPI.SUM)),
                )
            else:
                stable_facts = {
                    "schema": "task038.full3d.interlevel-stable-adjoint.a0.v1",
                    "scope": "per_rank_canonical_packets; checker_global_authority",
                    "vector_norm_reduction": "checker_global_sum_of_squares_by_key",
                }
            for role, key in roles.items():
                if role in probe_arrays:
                    arrays[key] = probe_arrays[role]
            facts["stable_adjoint"] = stable_facts
            facts["raw_roles"] = roles
            facts["source_generation"] = source_generation_identity(name)
            probe_facts_local.append(facts)
        emit(
            "probes_complete",
            probe_names=list(A0_PROBE_NAMES), probe_count=len(probe_facts_local),
            raw_shards=True, checker_global_authority=True,
        )
        local_shard = _write_raw_arrays(
            raw_dir, arrays, filename=f"a0_arrays.rank{comm.rank}.npz",
        )
        local_shard = {"rank": int(comm.rank), **local_shard}
        shard_list = comm.gather(local_shard, root=0)
        if comm.rank == 0:
            shards = sorted(shard_list, key=lambda item: int(item["rank"]))
            manifest_payload = {
                "schema": A0_RAW_SCHEMA,
                "mpi_size": int(comm.size),
                "shards": shards,
                "canonical_key_authority": "physical/canonical packed edge key; no PETSc row, rank, or local order",
            }
            manifest_path = raw_dir / "a0_arrays.manifest.json"
            manifest_sha = _write_json(manifest_path, manifest_payload)
            raw_manifest = {
                "schema": A0_RAW_SCHEMA,
                "relative_path": manifest_path.name,
                "sha256": manifest_sha,
                "mpi_size": int(comm.size),
                "shards": shards,
            }
        else:
            raw_manifest = None
        raw_manifest = comm.bcast(raw_manifest, root=0)
        inventory_groups = comm.gather(inventory_local, root=0)
        audit_groups = comm.gather(class_audits_local, root=0)
        if comm.rank == 0:
            inventory = _a0_merge_inventory_groups(inventory_groups)
            audit_items: dict[str, dict[str, Any]] = {}
            for group in audit_groups:
                for item in group:
                    digest = str(item["class_digest"])
                    existing = audit_items.get(digest)
                    if existing is None:
                        audit_items[digest] = dict(item)
                    elif (
                        existing.get("class_identity") != item.get("class_identity")
                        or existing.get("tag") != item.get("tag")
                        or existing.get("material_role") != item.get("material_role")
                    ):
                        raise RuntimeError("MPI class audit identities disagree")
            merged_audits = sorted(
                audit_items.values(), key=lambda item: item["class_digest"]
            )
            architecture = {
                "case": case_audit,
                "extension": extension_audit,
                "forbidden": _forbidden_architecture(case_audit, extension_audit),
                "levels": {
                    "level6": dict(extension.levels[0].audit),
                    "level3": dict(extension.levels[1].audit),
                },
            }
            for degree, level in ((6, extension.levels[0]), (3, extension.levels[1])):
                architecture["levels"][f"level{degree}"]["parent_topology"] = dict(
                    level.parent_topology.audit
                )
                architecture["levels"][f"level{degree}"]["raw_topology"] = dict(
                    level.raw_topology.audit
                )
            record = {
                "schema": A0_SCHEMA,
                "stage": A0_STAGE,
                "case": case_name,
                "degree": DEGREE,
                "h_nm": H_NM,
                "wavelength_nm": 13.5,
                "mpi_size": int(comm.size),
                "branch": BRANCH,
                "raw_dir": str(raw_dir),
                "record_path": str(record_path),
                "command": [
                    str(Path(sys.executable).absolute()), "-m", MODULE,
                    "--stage", A0_STAGE, "--case", case_name,
                    "--raw-dir", str(raw_dir), "--record", str(record_path),
                    "--expected-source-sha", expected_sha,
                    "--expected-mpi-size", str(expected_mpi),
                    "--input", str(input_path),
                    "--r3-long-tail-manifest", str(r3_manifest),
                ],
                "source": {"start": runtime["source"]},
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
                    "mpi_shard_count": int(comm.size),
                },
                "settings": {
                    "probe_names": list(A0_PROBE_NAMES),
                    "levels": [6, 3], "transfer_pair": [6, 3],
                    "canonical_key": "physical/canonical packed owner edge key",
                    "canonical_order": "sort by canonical key after rank-shard merge",
                    "canonical_packet_source": "topology canonical IDs; never PETSc row/local/rank order",
                    "ordinary_terms": "conjugate(original raw left) * original raw right",
                    "canonical_terms": "conjugate(key-aligned canonical values) * key-aligned canonical values",
                    "forward_bound_scope": "ordinary raw terms only",
                    "pairwise_limit": 1.0e-13,
                    "compensated_limit": 1.0e-12,
                    "vector_limit": 1.0e-11,
                    "ordinary_bound_factor": 4.0,
                    "phase_once": "once_in_canonical_owner_route",
                    "mpi_sizes_supported": [1, 2],
                },
                "architecture": architecture,
                "material_inventory": inventory,
                "material_classes": merged_audits,
                "p63_audit": _transfer_matrix_facts(p63_transfer.edge_transfer),
                "probes": probe_facts_local,
                "raw_arrays": raw_manifest,
                "markers": {
                    "relative_dir": "markers",
                    "names": list(marker_names),
                    "wall_time_ns": dict(marker_times),
                },
                "record_authority": "raw-shards-only; checker derives A0 classification",
            }
        if extension is not None:
            extension.destroy()
            extension = None
        case.destroy()
        case = None
        emit("release", destroyed=True)
        source_end = _source_identity(root, expected_sha)
        if comm.rank == 0:
            record["source"]["end"] = source_end
            record["markers"]["names"] = list(marker_names)
            record["markers"]["wall_time_ns"] = dict(marker_times)
            _write_json(record_path, record)
        comm.barrier()
        emit(
            "record_closeout",
            record_path=str(record_path),
            record_sha256=(
                hashlib.sha256(record_path.read_bytes()).hexdigest()
                if comm.rank == 0 else None
            ),
        )
    finally:
        if extension is not None:
            extension.destroy()
        if case is not None:
            case.destroy()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    # Legacy A/B contract remains choices=(STAGE, ROUTE_B_STAGE); A0 is opt-in.
    parser.add_argument("--stage", choices=(STAGE, ROUTE_B_STAGE, A0_STAGE), required=True)
    parser.add_argument("--case", choices=(CASE, *A0_CASES), required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-mpi-size", type=int, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--r3-long-tail-manifest", type=Path, required=True)
    parser.add_argument("--route", choices=("a", "b"), default="a")
    args = parser.parse_args(argv)
    if args.stage == A0_STAGE:
        if args.route != "a":
            parser.error("A0 uses the shared runner without --route")
        run_a0_worker(
            args.raw_dir, args.record, args.input, args.expected_source_sha,
            args.expected_mpi_size, args.r3_long_tail_manifest, args.case,
        )
        return 0
    if args.case != CASE:
        parser.error("Route-A/Route-B p6/h10 worker is fixed to MPI1")
    if (args.route == ROUTE_B) != (args.stage == ROUTE_B_STAGE):
        parser.error("Route-A uses --stage r1 and Route-B uses --stage r3")
    run_worker(
        args.raw_dir, args.record, args.input, args.expected_source_sha,
        args.expected_mpi_size, args.r3_long_tail_manifest, args.route,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
