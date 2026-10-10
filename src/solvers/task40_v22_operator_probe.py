"""Original-size Task40 V22 boundary descriptor and bounded operator probe.

This module deliberately stops before condensation, q CSR, factors, Krylov
vectors, and official scattering output.  It binds the saved boundary map to
the actual p6 mesh/MPC, then measures a small frozen set of fullspace B/D
functionals through the production surface assemblers.
"""

from __future__ import annotations

import gc
import hashlib
import os
import json
import sys
from pathlib import Path
import shutil
from time import perf_counter, process_time
from types import SimpleNamespace
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np


_SAVED_RUN = Path(
    "results/task40extra_nonseparable_0p7nm/"
    "task40extra_0p7nm_target_original_ny8_resource_pilot_v20__"
    "full3d_iterative__mpi1__Mna/20261009T155523.962924Z"
)
_GEOMETRY_RELATIVE = _SAVED_RUN / "v20_geometry_inventory.json"
_XDMF_RELATIVE = _SAVED_RUN / "target_geometry/mesh_3d.xdmf"
_H5_RELATIVE = _SAVED_RUN / "target_geometry/mesh_3d.h5"
_MAPPING_RELATIVE = (
    _SAVED_RUN / "target_geometry/v21_boundary_facet_class_mapping.json"
)
_GEOMETRY_SHA256 = "491dac32b7e3ba927ce44444f834ff1e27406c3dfe95a9438fac8cae45adce34"
_XDMF_SHA256 = "69187085a247671d31be04cb813d75c1c6ec2f8214f329f9008002f77ec33af1"
_H5_SHA256 = "0bcc83dea1fb912a88612732f088467b7cb2fd2e152e19370d98342709be1dba"
_MAPPING_FILE_SHA256 = "e5a38b003e3d061b04934a3158346a21448b6b2c6f884749c0182380676c3320"
_MAPPING_DIGEST = "164e1bf13f08beafc933528ace76315416e4be37bf10b97a03629cca53ab74b6"
_MODE_PHYSICAL_SHA256 = "a855565b82c1d88e84352dd355aec3531464261e5ab0df3e45de17e1879eaf1f"
_EXPECTED_FACETS_BY_SIDE = {"bottom": 2176, "top": 2176}
_EXPECTED_FULL_ROWS = 20_181_348
_EXPECTED_INDEPENDENT_ROWS = 19_897_344
_EXPLICIT_PROCESS_TREE_CAP_BYTES = 16 * 1024**3


class _ProbeResourceBlocked(RuntimeError):
    def __init__(self, stage: str, facts: Mapping[str, Any]):
        self.stage = stage
        self.facts = dict(facts)
        super().__init__(f"resource admission blocked before {stage}")


def _validate_v22_physical_identity_bindings(
    *,
    preflight: Mapping[str, Any],
    resolved: Mapping[str, Any],
    expected_mode_identity: str,
) -> None:
    """Keep resolved-input and target-mode physical identity domains distinct."""

    provenance = resolved.get("provenance", {})
    execution = resolved.get("execution", {})
    mode_inventory = preflight.get("target_mode_inventory")
    if not isinstance(provenance, Mapping) or not isinstance(execution, Mapping):
        raise ValueError("resolved V22 input omitted physical identity bindings")
    if not isinstance(mode_inventory, Mapping):
        raise ValueError("V22 preflight omitted the target mode physical identity")
    physical_model_sha256 = preflight.get("physical_model_sha256")
    if (
        not isinstance(physical_model_sha256, str)
        or len(physical_model_sha256) != 64
        or any(character not in "0123456789abcdef" for character in physical_model_sha256)
    ):
        raise ValueError("resolved-input physical-model identity is missing or malformed")
    if physical_model_sha256 != provenance.get("physical_model_sha256"):
        raise ValueError("resolved-input physical-model identity differs from preflight")
    if (
        mode_inventory.get("physical_identity_sha256") != expected_mode_identity
        or execution.get("task40_target_physical_identity_sha256")
        != expected_mode_identity
    ):
        raise ValueError("target-mode physical identity differs from its frozen input/manifest")


def _saved_global_packet_to_boundary_plane(
    saved_b_global: Any,
    saved_d_global: Any,
    saved_h_global: float,
    global_z_phase: complex,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Convert one saved global-z B/D/H packet into the boundary-plane gauge."""

    b_global = np.asarray(saved_b_global, dtype=np.complex128)
    d_global = np.asarray(saved_d_global, dtype=np.complex128)
    h_global = float(saved_h_global)
    phase = complex(global_z_phase)
    if (
        b_global.shape != d_global.shape
        or not np.isfinite(b_global).all()
        or not np.isfinite(d_global).all()
        or not np.isfinite(h_global)
        or h_global <= 0.0
        or not np.isfinite(phase)
        or phase == 0.0
    ):
        raise ValueError("saved global-z B/D/H gauge conversion inputs are invalid")
    b_plane = np.ascontiguousarray(b_global / phase, dtype=np.complex128)
    # Keep the packet's original H_global for this D conversion.
    d_plane = np.ascontiguousarray(
        d_global * h_global / np.conjugate(phase), dtype=np.complex128
    )
    h_plane = h_global / abs(phase) ** 2
    if not np.isfinite(b_plane).all() or not np.isfinite(d_plane).all():
        raise ValueError("saved global-z B/D gauge conversion is nonfinite")
    if not np.isfinite(h_plane) or h_plane <= 0.0:
        raise ValueError("saved global-z H_p gauge conversion is nonfinite or nonpositive")
    return b_plane, d_plane, float(h_plane)


def _saved_packet_action_h(mode_identity: Mapping[str, Any]) -> float:
    """Select the boundary-plane H used by generated/cached local actions."""

    action_h = float(mode_identity.get("H_p"))
    packet_plane_h = float(mode_identity.get("H_p_boundary_plane_from_packet"))
    if (
        mode_identity.get("H_p_gauge") != "boundary_plane"
        or not np.isfinite(action_h)
        or action_h <= 0.0
        or action_h != packet_plane_h
    ):
        raise ValueError("saved packet action H_p is not the converted boundary-plane value")
    return action_h


def _transform_mode_basis_columns(
    space_element: Any, basis: Any, cell_info: Any
) -> np.ndarray:
    """Apply the real cell orientation to each contiguous modal basis column."""

    transformed = np.ascontiguousarray(basis, dtype=np.complex128)
    if transformed.ndim != 2 or not np.isfinite(transformed).all():
        raise ValueError("saved modal basis must be a finite two-dimensional array")
    if not space_element.needs_dof_transformations:
        return transformed
    info = np.asarray(cell_info, dtype=np.uint32).reshape(-1)
    if info.shape != (1,):
        raise ValueError("modal basis orientation requires exactly one cell_info value")
    for component in range(transformed.shape[1]):
        column = np.ascontiguousarray(transformed[:, component])
        space_element.T_apply(column, info, 1)
        transformed[:, component] = column
    return transformed


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


class _RollingDigest:
    """A compact, restartable hash chain over ordered update segments."""

    def __init__(self, state_hex: str | None = None) -> None:
        self._state = bytes(32) if state_hex is None else bytes.fromhex(state_hex)
        if len(self._state) != 32:
            raise ValueError("rolling digest state must be one SHA-256 value")

    def update(self, value: bytes | bytearray | memoryview) -> None:
        leaf = hashlib.sha256(bytes(value)).digest()
        self._state = hashlib.sha256(self._state + leaf).digest()

    def copy(self) -> "_RollingDigest":
        return _RollingDigest(self.hexdigest())

    def hexdigest(self) -> str:
        return self._state.hex()


def _array_sha256(value: Any) -> str:
    array = np.ascontiguousarray(value)
    digest = hashlib.sha256()
    digest.update(repr((array.shape, str(array.dtype))).encode("ascii"))
    digest.update(memoryview(array).cast("B"))
    return digest.hexdigest()


def _cell_support_row_counts(
    global_rows: Sequence[int],
    *,
    interior_rows_sorted: np.ndarray,
    interior_cell_ids_sorted: np.ndarray,
    cell_ids_sorted: np.ndarray,
) -> np.ndarray:
    """Count retained interior rows per cell for one already-filtered mode."""

    rows = np.unique(np.asarray(global_rows, dtype=np.int64).reshape(-1))
    counts = np.zeros(len(cell_ids_sorted), dtype=np.int64)
    if not rows.size or not interior_rows_sorted.size:
        return counts
    positions = np.searchsorted(interior_rows_sorted, rows)
    valid = positions < len(interior_rows_sorted)
    matched = np.zeros(len(rows), dtype=np.bool_)
    matched[valid] = interior_rows_sorted[positions[valid]] == rows[valid]
    if np.any(matched):
        cell_positions = np.searchsorted(
            cell_ids_sorted, interior_cell_ids_sorted[positions[matched]]
        )
        counts = np.bincount(cell_positions, minlength=len(cell_ids_sorted))
    return counts


def _accumulate_cell_mode_support(
    per_cell_mode_counts: np.ndarray,
    per_cell_row_memberships: np.ndarray,
    per_mode_row_counts: np.ndarray,
) -> None:
    """Count a cell once per mode while retaining raw row memberships separately."""

    counts = np.asarray(per_mode_row_counts, dtype=np.int64).reshape(-1)
    if counts.shape != per_cell_mode_counts.shape or counts.shape != per_cell_row_memberships.shape:
        raise ValueError("per-mode cell counts do not match the cell inventory")
    if np.any(counts < 0):
        raise ValueError("per-mode cell row counts cannot be negative")
    per_cell_mode_counts += counts > 0
    per_cell_row_memberships += counts


def _summarize_cell_mode_support(
    per_cell_mode_counts: np.ndarray, *, expected_mode_count: int
) -> dict[str, Any]:
    """Summarize m_c over cells; bins count cells with each mode multiplicity."""

    values = np.asarray(per_cell_mode_counts, dtype=np.int64).reshape(-1)
    if np.any(values < 0) or np.any(values > int(expected_mode_count)):
        raise ValueError("per-cell m_c is outside the side's expected mode count")
    return {
        "histogram_by_modes_0_to_expected": np.bincount(
            values, minlength=int(expected_mode_count) + 1
        ).tolist(),
        "sum": int(np.sum(values, dtype=np.int64)),
        "sum_squares": int(np.dot(values, values)),
        "per_cell_mode_count": values.tolist(),
        "cell_count": int(len(values)),
    }


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    def encode_default(item: Any) -> Any:
        if isinstance(item, np.generic):
            return item.item()
        if isinstance(item, np.ndarray):
            return item.tolist()
        if isinstance(item, complex):
            return {"real": float(item.real), "imag": float(item.imag)}
        if isinstance(item, Path):
            return str(item)
        raise TypeError(f"unsupported V22 receipt value: {type(item).__name__}")

    encoded = json.dumps(
        value, sort_keys=True, indent=2, allow_nan=False, default=encode_default
    ).encode("utf-8") + b"\n"
    with temporary.open("wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _copy_verified(source: Path, destination: Path, expected_sha256: str) -> None:
    if not source.is_file() or _sha256_file(source) != expected_sha256:
        raise ValueError(f"saved V21 source artifact failed its SHA-256: {source.name}")
    if destination.exists():
        if _sha256_file(destination) != expected_sha256:
            raise FileExistsError(
                f"refusing to replace a different target probe artifact: {destination.name}"
            )
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    if _sha256_file(destination) != expected_sha256:
        raise IOError(f"copied V22 artifact failed its SHA-256: {destination.name}")


def _load_verified_mapping(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    path = root / _MAPPING_RELATIVE
    if not path.is_file() or _sha256_file(path) != _MAPPING_FILE_SHA256:
        raise ValueError("saved V21 boundary mapping file identity changed")
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("facet_mappings")
    if (
        data.get("schema") != "task40extra.review_v21_boundary_facet_class_mapping.v1"
        or data.get("status") != "GEOMETRY_MAPPING_COMPLETE_SUPPORT_UNKNOWN"
        or data.get("mapping_sha256") != _MAPPING_DIGEST
        or not isinstance(rows, list)
        or len(rows) != sum(_EXPECTED_FACETS_BY_SIDE.values())
    ):
        raise ValueError("saved V21 boundary mapping header or inventory changed")
    side_counts = {side: 0 for side in _EXPECTED_FACETS_BY_SIDE}
    seen: set[tuple[str, int]] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("saved V21 boundary mapping contains a non-object row")
        side = str(row.get("side"))
        facet_id = int(row.get("facet_id", -1))
        cell_id = int(row.get("cell_id", -1))
        if (
            side not in side_counts
            or facet_id < 0
            or cell_id < 0
            or (side, facet_id) in seen
            or not isinstance(row.get("class_id"), str)
            or len(row.get("cell_bounds_nm", ())) != 3
            or len(row.get("ordered_cell_coordinates_nm", ())) != 8
        ):
            raise ValueError("saved V21 boundary mapping row has invalid identity fields")
        seen.add((side, facet_id))
        side_counts[side] += 1
    if side_counts != _EXPECTED_FACETS_BY_SIDE:
        raise ValueError("saved V21 boundary facet side counts changed")
    return data, {
        "path": str(path.relative_to(root)),
        "file_sha256": _MAPPING_FILE_SHA256,
        "mapping_sha256": _MAPPING_DIGEST,
        "facet_count": len(rows),
        "facet_count_by_side": side_counts,
        "status": data["status"],
        "support": dict(data.get("support", {})),
    }


def _memory_snapshot(resource_sample: Callable[[], Mapping[str, Any]]) -> dict[str, Any]:
    sample = dict(resource_sample())
    current_rss = None
    try:
        for line in Path("/proc/self/status").read_text(encoding="ascii").splitlines():
            if line.startswith("VmRSS:"):
                current_rss = int(line.split()[1]) * 1024
                break
    except (OSError, ValueError, IndexError):
        pass
    sample["current_process_rss_bytes"] = current_rss
    return sample


def _resource_admission(
    stage: str,
    additional_bytes: int,
    *,
    resource_sample: Callable[[], Mapping[str, Any]],
    process_tree: Mapping[str, Any] | None = None,
    memory_policy_sample: Mapping[str, Any] | None = None,
    require_task_cgroup: bool | None = None,
) -> dict[str, Any]:
    from benchmarks.subreaper_watchdog import (
        PHYSICAL_MEMORY_PRESSURE_POLICY,
        memory_envelope,
        runtime_tree_cap,
    )
    from benchmarks.task038_full3d_jit_staging import process_tree_snapshot

    additional_bytes = int(additional_bytes)
    if additional_bytes < 0:
        raise ValueError("resource admission additional bytes must be nonnegative")
    snapshot = dict(resource_sample())
    snapshot["current_process_rss_bytes"] = _memory_snapshot(
        lambda: snapshot
    ).get("current_process_rss_bytes")
    if process_tree is None:
        process_tree = process_tree_snapshot(
            os.getpid(),
            f"v22_resource_admission:{stage}",
            pss_sampling_policy="disabled_by_profile",
        )
    else:
        process_tree = dict(process_tree)
    if memory_policy_sample is None:
        memory_policy_sample = memory_envelope(PHYSICAL_MEMORY_PRESSURE_POLICY)
    else:
        memory_policy_sample = dict(memory_policy_sample)

    tree_rss = process_tree.get("rss_bytes")
    tree_authoritative = bool(
        process_tree.get("all_status_readable") is True
        and process_tree.get("identity_complete") is True
        and type(tree_rss) is int
    )
    dynamic_cap = None
    if tree_authoritative:
        dynamic_cap = runtime_tree_cap(
            _EXPLICIT_PROCESS_TREE_CAP_BYTES,
            int(tree_rss),
            memory_policy_sample,
            explicit_tree_cap_bytes=_EXPLICIT_PROCESS_TREE_CAP_BYTES,
            memory_policy=PHYSICAL_MEMORY_PRESSURE_POLICY,
        )
    cgroup = snapshot.get("current_process_cgroup", {})
    if not isinstance(cgroup, Mapping):
        cgroup = {}
    cgroup_current = cgroup.get("memory_current_bytes")
    cgroup_limit = cgroup.get("memory_limit_bytes")
    cgroup_reserve = int(memory_policy_sample.get("reserve_bytes", 0))
    host_available = memory_policy_sample.get("effective_available_bytes")
    host_reserve = int(memory_policy_sample.get("reserve_bytes", 0))
    needs_task_cgroup = (
        additional_bytes >= 512 * 2**20
        if require_task_cgroup is None
        else bool(require_task_cgroup)
    )
    task_cgroup_ready = bool(
        cgroup.get("readable") is True
        and cgroup.get("dedicated_job_cgroup") is True
        and type(cgroup_current) is int
        and type(cgroup_limit) is int
        and cgroup.get("swap_current_bytes") == 0
    )
    host_gate = bool(
        type(host_available) is int
        and additional_bytes <= max(int(host_available) - host_reserve, 0)
    )
    tree_gate = bool(
        tree_authoritative
        and dynamic_cap is not None
        and int(tree_rss) + additional_bytes <= dynamic_cap
    )
    cgroup_gate = bool(
        not needs_task_cgroup
        or (
            task_cgroup_ready
            and int(cgroup_current) + additional_bytes
            <= int(cgroup_limit) - cgroup_reserve
        )
    )
    facts = {
        "stage": stage,
        "additional_object_upper_bound_bytes": additional_bytes,
        "explicit_process_tree_cap_bytes": _EXPLICIT_PROCESS_TREE_CAP_BYTES,
        "dynamic_process_tree_cap_bytes": dynamic_cap,
        "current_process_tree_rss_bytes": tree_rss,
        "process_tree_snapshot": {
            "identity_complete": process_tree.get("identity_complete"),
            "all_status_readable": process_tree.get("all_status_readable"),
            "member_count": process_tree.get("identity_count"),
            "scope": "current process and descendants sampled at admission",
        },
        "host_effective_available_bytes": host_available,
        "physical_memory_policy": PHYSICAL_MEMORY_PRESSURE_POLICY,
        "memory_envelope": dict(memory_policy_sample),
        "current_process_cgroup": dict(cgroup),
        "task_cgroup_required": needs_task_cgroup,
        "task_cgroup_current_plus_additional_bytes": (
            None if type(cgroup_current) is not int else int(cgroup_current) + additional_bytes
        ),
        "task_cgroup_limit_minus_evidence_reserve_bytes": (
            None
            if type(cgroup_limit) is not int
            else int(cgroup_limit) - cgroup_reserve
        ),
        "host_gate_passed": host_gate,
        "process_tree_gate_passed": tree_gate,
        "task_cgroup_gate_passed": cgroup_gate,
        "swap_gate_status": (
            "PASS_ZERO_TASK_CGROUP_SWAP"
            if task_cgroup_ready
            else "BLOCKED_OR_UNKNOWN_TASK_CGROUP"
        ),
        "sample_scope": snapshot.get("scope"),
    }
    if not (host_gate and tree_gate and cgroup_gate):
        raise _ProbeResourceBlocked(stage, facts)
    return facts


def _verify_saved_mesh_mapping(
    msh: Any,
    mesh_data: Any,
    mapping_rows: Sequence[Mapping[str, Any]],
    cfg: Any,
) -> dict[str, Any]:
    from dolfinx import mesh

    tdim = int(msh.topology.dim)
    fdim = tdim - 1
    msh.topology.create_entity_permutations()
    msh.topology.create_connectivity(fdim, tdim)
    msh.topology.create_connectivity(fdim, 0)
    facet_to_cell = msh.topology.connectivity(fdim, tdim)
    facet_to_vertex = msh.topology.connectivity(fdim, 0)
    cell_permutations = np.asarray(msh.topology.get_cell_permutation_info())
    geometry_dofmap = np.asarray(msh.geometry.dofmap, dtype=np.int32)
    geometry = np.asarray(msh.geometry.x, dtype=np.float64)
    cell_count = int(msh.topology.index_map(tdim).size_local)
    cell_tag = {
        int(cell): int(tag)
        for cell, tag in zip(
            mesh_data.cell_tags.indices, mesh_data.cell_tags.values, strict=True
        )
    }
    facet_tag = {
        int(facet): int(tag)
        for facet, tag in zip(
            mesh_data.facet_tags.indices, mesh_data.facet_tags.values, strict=True
        )
    }
    if (
        cell_count != 30_464
        or geometry_dofmap.shape != (cell_count, 8)
        or cell_permutations.shape != (cell_count,)
        or len(cell_tag) != cell_count
    ):
        raise ValueError("saved XDMF mesh cell/topology inventory differs from V21")
    facet_ids = np.asarray(
        [int(row["facet_id"]) for row in mapping_rows], dtype=np.int32
    )
    centers = mesh.compute_midpoints(msh, fdim, facet_ids)
    bottom_z = float(cfg.domain_z_min)
    top_z = float(cfg.domain_z_max)
    matched_classes: dict[str, set[str]] = {"bottom": set(), "top": set()}
    unique_cells: dict[str, set[int]] = {"bottom": set(), "top": set()}
    row_by_facet = {
        (str(row["side"]), int(row["facet_id"])): row for row in mapping_rows
    }
    for position, row in enumerate(mapping_rows):
        side = str(row["side"])
        facet_id = int(row["facet_id"])
        saved_cell = int(row["cell_id"])
        adjacent = tuple(int(value) for value in facet_to_cell.links(facet_id))
        if adjacent != (saved_cell,):
            raise ValueError(
                f"saved facet {facet_id} adjacency differs from mapped cell {saved_cell}"
            )
        expected_tag = int(cfg.tags.z_min if side == "bottom" else cfg.tags.z_max)
        if facet_tag.get(facet_id) != expected_tag:
            raise ValueError(f"saved facet {facet_id} has a different reconstructed side tag")
        if int(cell_permutations[saved_cell]) != int(row["cell_permutation"]):
            raise ValueError(f"saved cell {saved_cell} permutation differs from mapping")
        cell_points = geometry[geometry_dofmap[saved_cell]]
        lower = cell_points.min(axis=0)
        upper = cell_points.max(axis=0)
        expected_bounds = np.asarray(row["cell_bounds_nm"], dtype=np.float64)
        if not np.array_equal(
            np.column_stack((lower, upper)), expected_bounds
        ):
            raise ValueError(f"saved cell {saved_cell} bounds differ from mapping")
        boundary_z = bottom_z if side == "bottom" else top_z
        if float(lower[2] if side == "bottom" else upper[2]) != boundary_z:
            raise ValueError(f"saved facet {facet_id} is not on its declared physical plane")
        center = np.asarray(centers[position], dtype=np.float64)
        saved_center = np.asarray(row["readback_facet_center_nm"], dtype=np.float64)
        if not np.array_equal(center, saved_center):
            raise ValueError(f"saved facet {facet_id} center differs from XDMF readback")
        mapped_vertices = tuple(
            sorted(int(value) for value in facet_to_vertex.links(facet_id))
        )
        saved_vertices = tuple(sorted(int(value) for value in row["saved_facet_vertex_ids"]))
        if mapped_vertices != saved_vertices:
            raise ValueError(f"saved facet {facet_id} vertex identity differs from mapping")
        widths = tuple(float(value) for value in upper - lower)
        saved_widths = tuple(float(value) for value in row["cell_widths_nm"])
        if widths != saved_widths or int(cell_tag[saved_cell]) != int(row["material_tag"]):
            raise ValueError(f"saved cell {saved_cell} material/metric differs from mapping")
        matched_classes[side].add(str(row["class_id"]))
        unique_cells[side].add(saved_cell)
    del row_by_facet
    return {
        "status": "PASS",
        "facet_to_cell_adjacency_count": len(mapping_rows),
        "facet_center_and_vertex_identity_count": len(mapping_rows),
        "cell_permutation_identity_count": len(mapping_rows),
        "unique_cell_count_by_side": {
            side: len(values) for side, values in unique_cells.items()
        },
        "boundary_class_count_by_side": {
            side: len(values) for side, values in matched_classes.items()
        },
        "boundary_class_ids_by_side": {
            side: sorted(values) for side, values in matched_classes.items()
        },
        "global_FE_or_MPC_created": False,
    }


def _selected_modes(
    modes: Sequence[Any], mode_rows: Sequence[Mapping[str, Any]]
) -> tuple[list[int], dict[str, list[int]]]:
    by_side: dict[str, list[int]] = {"bottom": [], "top": []}
    for index, mode in enumerate(modes):
        side = str(getattr(mode, "side", ""))
        if side not in by_side:
            raise ValueError("frozen target mode table contains an unknown side")
        by_side[side].append(index)
    if len(mode_rows) != len(modes) or any(len(v) != 16_030 for v in by_side.values()):
        raise ValueError("target ordered mode table differs from the V20 16,030-per-side inventory")
    selected_by_side = {
        side: sorted({indices[0], indices[len(indices) // 2], indices[-1]})
        for side, indices in by_side.items()
    }
    selected = sorted(index for values in selected_by_side.values() for index in values)
    return selected, selected_by_side


def _native_local_port_pair(
    *,
    polynomial: Any,
    space_element: Any,
    mode: Any,
    side: str,
    bounds: Sequence[Sequence[float]],
    cell_info: Any,
    cfg: Any,
    quadrature_degree: int,
) -> tuple[np.ndarray, np.ndarray]:
    from src.solvers.dtn_port_3d import _traction_vector

    box = np.asarray(bounds, dtype=np.float64)
    lower = box[:, 0]
    upper = box[:, 1]
    jacobian = np.diag(upper - lower)
    # Production uses the boundary-plane gauge: the z phase is exactly one
    # on the selected plane, while x/y Fourier phases remain physical.
    wave_vector = np.asarray(
        [complex(mode.alpha), complex(mode.gamma), 0.0 + 0.0j],
        dtype=np.complex128,
    )
    integrated = polynomial.integral_native(
        side, wave_vector, jacobian, lower, quadrature_degree
    )
    electric = np.asarray(
        [complex(value) for value in mode.e_vector[:2]], dtype=np.complex128
    )
    traction = np.asarray(_traction_vector(mode, cfg)[:2], dtype=np.complex128)
    raw_b = np.ascontiguousarray(integrated @ (-traction), dtype=np.complex128)
    raw_d = np.ascontiguousarray(np.conjugate(integrated @ electric), dtype=np.complex128)
    if space_element.needs_dof_transformations:
        permutations = np.asarray([cell_info], dtype=np.uint32)
        space_element.T_apply(raw_b, permutations, 1)
        space_element.T_apply(raw_d, permutations, 1)
    if not np.isfinite(raw_b).all() or not np.isfinite(raw_d).all():
        raise FloatingPointError("native boundary descriptor produced non-finite B/D rows")
    return raw_b, raw_d


def _native_local_component_basis(
    *,
    polynomial: Any,
    space_element: Any,
    mode: Any,
    side: str,
    bounds: Sequence[Sequence[float]],
    cell_info: Any,
    component: int,
    quadrature_degree: int,
) -> np.ndarray:
    """Integrate one raw component on an actual facet and apply its cell map."""

    if component not in (0, 1):
        raise ValueError("native production component must be zero or one")
    box = np.asarray(bounds, dtype=np.float64)
    lower = box[:, 0]
    upper = box[:, 1]
    integrated = polynomial.integral_native(
        side,
        np.asarray(
            [complex(mode.alpha), complex(mode.gamma), 0.0 + 0.0j],
            dtype=np.complex128,
        ),
        np.diag(upper - lower),
        lower,
        quadrature_degree,
    )
    values = np.ascontiguousarray(integrated[:, component], dtype=np.complex128)
    if space_element.needs_dof_transformations:
        space_element.T_apply(
            values,
            np.asarray([cell_info], dtype=np.uint32),
            1,
        )
    if not np.isfinite(values).all():
        raise FloatingPointError("direct native component contains non-finite rows")
    return values


def _direct_mpc_filtered_component_entries(
    work_vector: np.ndarray,
    facet_contributions: Iterable[tuple[Sequence[int], Sequence[complex]]],
    *,
    slave_rows: Sequence[int],
    master_rows: Sequence[int],
    dual_coefficients: Sequence[complex],
    master_counts: Sequence[int],
    index_dtype: Any,
    compact_row_domain: Sequence[int] | None = None,
    admit_additional_bytes: Callable[[str, int], None] | None = None,
    relative_tol: float = 1e-13,
    absolute_floor: float = 0.0,
    chunk_size: int = 262_144,
) -> tuple[tuple[np.ndarray, np.ndarray], dict[str, Any]]:
    """Directly sum facet rows, apply MPC E^H, then reproduce one global mask.

    Filtering scans are chunked so the only full-size numerical workspace is
    ``work_vector``. Retained sparse arrays are admitted by their measured size
    before allocation.
    """

    vector = np.asarray(work_vector)
    if (
        vector.ndim != 1
        or vector.dtype != np.dtype(np.complex128)
        or chunk_size <= 0
        or relative_tol < 0.0
        or absolute_floor < 0.0
    ):
        raise ValueError("direct component workspace or support-filter policy is invalid")
    vector.fill(0.0 + 0.0j)
    row_domain = (
        np.asarray(compact_row_domain, dtype=np.int64).reshape(-1)
        if compact_row_domain is not None
        else None
    )
    if row_domain is not None and (
        not len(row_domain)
        or (len(row_domain) > 1 and np.any(row_domain[1:] <= row_domain[:-1]))
        or len(row_domain) != len(vector)
    ):
        raise ValueError("compact component row domain must be sorted, unique, and match its workspace")

    def workspace_rows(global_rows: Sequence[int], label: str) -> np.ndarray:
        rows = np.asarray(global_rows, dtype=np.int64).reshape(-1)
        if row_domain is None:
            return rows
        positions = np.searchsorted(row_domain, rows)
        valid = positions < len(row_domain)
        matched = np.zeros(len(rows), dtype=np.bool_)
        matched[valid] = row_domain[positions[valid]] == rows[valid]
        if not np.all(matched):
            raise ValueError(f"{label} row escaped the compact boundary/MPC closure")
        return positions

    for global_rows, local_values in facet_contributions:
        rows = workspace_rows(global_rows, "direct facet")
        values = np.asarray(local_values, dtype=np.complex128).reshape(-1)
        if (
            rows.shape != values.shape
            or (rows.size and (int(rows.min()) < 0 or int(rows.max()) >= len(vector)))
            or not np.isfinite(values).all()
        ):
            raise ValueError("direct facet contribution has invalid rows or values")
        np.add.at(vector, rows, values)
    raw_nonzero_count = int(np.count_nonzero(vector))
    raw_norm = float(np.linalg.norm(vector))

    slave = workspace_rows(slave_rows, "MPC slave")
    masters = workspace_rows(master_rows, "MPC master")
    dual = np.asarray(dual_coefficients, dtype=np.complex128).reshape(-1)
    counts = np.asarray(master_counts, dtype=np.int64).reshape(-1)
    if (
        slave.shape != counts.shape
        or int(counts.sum()) != len(masters)
        or masters.shape != dual.shape
        or (slave.size and (int(slave.min()) < 0 or int(slave.max()) >= len(vector)))
        or (masters.size and (int(masters.min()) < 0 or int(masters.max()) >= len(vector)))
        or not np.isfinite(dual).all()
    ):
        raise ValueError("direct component MPC E^H rows are inconsistent")
    if slave.size:
        slave_values = vector[slave].copy()
        routed_values = np.repeat(slave_values, counts)
        np.add.at(vector, masters, dual * routed_values)
        vector[slave] = 0.0 + 0.0j

    scratch_bytes = int(chunk_size) * 64
    if admit_additional_bytes is not None:
        admit_additional_bytes("direct_component_filter_scratch", scratch_bytes)
    global_maximum = 0.0
    for start in range(0, len(vector), chunk_size):
        stop = min(start + chunk_size, len(vector))
        magnitudes = np.abs(vector[start:stop])
        global_maximum = max(global_maximum, float(np.max(magnitudes, initial=0.0)))
    cutoff = max(float(absolute_floor), float(relative_tol) * global_maximum)

    prefilter_nonzero_count = 0
    dropped_count = 0
    retained_count = 0
    prefilter_norm_squared = 0.0
    dropped_norm_squared = 0.0
    retained_norm_squared = 0.0
    for start in range(0, len(vector), chunk_size):
        stop = min(start + chunk_size, len(vector))
        values = vector[start:stop]
        magnitudes = np.abs(values)
        nonzero = magnitudes > 0.0
        keep = magnitudes > cutoff
        dropped = nonzero & ~keep
        prefilter_nonzero_count += int(np.count_nonzero(nonzero))
        prefilter_norm_squared += float(np.vdot(values, values).real)
        dropped_values = values[dropped]
        dropped_count += int(len(dropped_values))
        dropped_norm_squared += float(np.vdot(dropped_values, dropped_values).real)
        retained_values = values[keep]
        retained_count += int(len(retained_values))
        retained_norm_squared += float(np.vdot(retained_values, retained_values).real)

    output_dtype = np.dtype(index_dtype)
    output_bytes = retained_count * (output_dtype.itemsize + np.dtype(np.complex128).itemsize)
    if admit_additional_bytes is not None and output_bytes:
        admit_additional_bytes("direct_component_filtered_sparse_entries", int(output_bytes))
    output_rows = np.empty(retained_count, dtype=output_dtype)
    output_values = np.empty(retained_count, dtype=np.complex128)
    offset = 0
    for start in range(0, len(vector), chunk_size):
        stop = min(start + chunk_size, len(vector))
        values = vector[start:stop]
        keep = np.abs(values) > cutoff
        local_rows = np.flatnonzero(keep)
        count = len(local_rows)
        compact_rows = start + local_rows
        output_rows[offset : offset + count] = (
            row_domain[compact_rows] if row_domain is not None else compact_rows
        )
        output_values[offset : offset + count] = values[local_rows]
        offset += count
    if offset != retained_count:
        raise RuntimeError("direct component retained count changed during bounded extraction")
    digest = hashlib.sha256()
    digest.update(np.ascontiguousarray(output_rows).tobytes())
    digest.update(np.ascontiguousarray(output_values).tobytes())
    audit = {
        "scope": "direct per-facet vector after actual finalized MPC E^H, before weighted combination",
        "relative_tol": float(relative_tol),
        "absolute_floor": float(absolute_floor),
        "raw_assembled_nonzero_rows_before_mpc": raw_nonzero_count,
        "raw_assembled_norm_before_mpc": raw_norm,
        "global_maximum_abs_after_mpc": global_maximum,
        "global_cutoff_after_mpc": cutoff,
        "nonzero_rows_before_global_mask": prefilter_nonzero_count,
        "norm_before_global_mask": float(np.sqrt(prefilter_norm_squared)),
        "rows_dropped_by_global_mask": dropped_count,
        "dropped_norm": float(np.sqrt(dropped_norm_squared)),
        "retained_rows": retained_count,
        "retained_norm": float(np.sqrt(retained_norm_squared)),
        "retained_entries_sha256": digest.hexdigest(),
        "bounded_filter_chunk_rows": int(chunk_size),
        "filter_scratch_upper_bound_bytes": scratch_bytes,
    }
    return (output_rows, output_values), audit



def _global_mpc_expansions(
    mpc: Any,
    dof_index_map: Any,
    target_global_rows: Sequence[int],
) -> dict[int, tuple[np.ndarray, np.ndarray]]:
    """Extract only finalized MPC rows touched by the local packet trace."""

    slave_local = np.asarray(mpc.slaves, dtype=np.int32).reshape(-1)
    coefficients, offsets = mpc.coefficients()
    coefficients = np.asarray(coefficients).reshape(-1)
    offsets = np.asarray(offsets, dtype=np.int64).reshape(-1)
    slave_global = np.asarray(
        dof_index_map.local_to_global(slave_local), dtype=np.int64
    ).reshape(-1)
    if slave_global.size != slave_local.size:
        raise ValueError("finalized MPC slave rows do not map to global rows")
    targets = np.asarray(sorted(set(map(int, target_global_rows))), dtype=np.int64)
    selected = np.flatnonzero(np.isin(slave_global, targets))
    selected_global = slave_global[selected]
    if len(np.unique(selected_global)) != len(selected_global):
        raise ValueError("a local packet trace slave maps to multiple finalized MPC rows")
    result: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for slave_position in selected:
        local = slave_local[slave_position]
        global_row = slave_global[slave_position]
        row = int(local)
        masters_local = np.asarray(mpc.masters.links(row), dtype=np.int32).reshape(-1)
        masters_global = np.asarray(
            dof_index_map.local_to_global(masters_local), dtype=np.int64
        ).reshape(-1)
        if offsets.size > (int(np.max(slave_local, initial=-1)) + 1):
            start, stop = int(offsets[row]), int(offsets[row + 1])
        elif offsets.size == slave_local.size + 1:
            start, stop = int(offsets[slave_position]), int(offsets[slave_position + 1])
        elif offsets.size == 0 and coefficients.size == slave_local.size and len(masters_local) == 1:
            start, stop = slave_position, slave_position + 1
        else:
            raise ValueError("finalized MPC coefficient offsets have an unsupported layout")
        row_coefficients = np.ascontiguousarray(
            coefficients[start:stop], dtype=np.complex128
        )
        if (
            len(masters_global) == 0
            or len(masters_global) != len(row_coefficients)
            or not np.isfinite(row_coefficients).all()
        ):
            raise ValueError("finalized MPC master/coefficient row is empty or inconsistent")
        result[int(global_row)] = (masters_global, row_coefficients)
    return result


def _mapped_port_face_global_rows(
    mapping_rows: Sequence[Mapping[str, Any]],
    cell_to_facet: Any,
    boundary_cell_global_dofs: Mapping[int, np.ndarray],
    entity_closure_dofs: Sequence[Sequence[int]],
) -> set[int]:
    """Return global rows in actual mapped physical port face closures."""

    rows: set[int] = set()
    for row in mapping_rows:
        cell_id = int(row["cell_id"])
        facet_ids = np.asarray(cell_to_facet.links(cell_id), dtype=np.int64)
        local_facets = np.flatnonzero(facet_ids == int(row["facet_id"]))
        if len(local_facets) != 1:
            raise ValueError("saved port facet does not map to one local cell face")
        face_positions = np.asarray(
            entity_closure_dofs[int(local_facets[0])], dtype=np.int32
        )
        rows.update(map(int, boundary_cell_global_dofs[cell_id][face_positions]))
    return rows


def _same_v23_mpc_function_space_layout(space: Any, mpc_space: Any) -> bool:
    """Compare the MPC and caller FE spaces by their owned-cell dof layout."""

    try:
        space_dofmap = space.dofmap
        mpc_dofmap = mpc_space.dofmap
        space_index_map = space_dofmap.index_map
        mpc_index_map = mpc_dofmap.index_map
        if (
            mpc_space.mesh is not space.mesh
            or int(mpc_space.element.basix_element.hash())
            != int(space.element.basix_element.hash())
            or int(mpc_index_map.size_global) != int(space_index_map.size_global)
            or int(mpc_index_map.size_local) != int(space_index_map.size_local)
            or tuple(int(value) for value in mpc_index_map.local_range)
            != tuple(int(value) for value in space_index_map.local_range)
            or int(mpc_index_map.num_ghosts) != int(space_index_map.num_ghosts)
            or int(mpc_dofmap.index_map_bs) != int(space_dofmap.index_map_bs)
            or not np.array_equal(mpc_index_map.ghosts, space_index_map.ghosts)
            or not np.array_equal(mpc_index_map.owners, space_index_map.owners)
        ):
            return False

        topology = space.mesh.topology
        cell_dim = int(topology.dim)
        owned_cell_count = int(topology.index_map(cell_dim).size_local)
        for cell in range(owned_cell_count):
            if not np.array_equal(
                mpc_dofmap.cell_dofs(cell), space_dofmap.cell_dofs(cell)
            ):
                return False
        return True
    except (AttributeError, IndexError, TypeError, ValueError):
        return False


def _compact_reference_mode_indices(modes: Sequence[Any]) -> dict[str, list[int]]:
    """Select first/middle/last real k-vectors and any adjacent s/p partners."""

    by_side: dict[str, list[int]] = {"bottom": [], "top": []}
    k_keys: dict[int, tuple[complex, ...]] = {}
    for index, mode in enumerate(modes):
        side = str(getattr(mode, "side", ""))
        if side not in by_side:
            continue
        by_side[side].append(index)
        k_keys[index] = tuple(
            complex(value) for value in np.asarray(mode.k_vector).reshape(-1)
        )
    selected: dict[str, list[int]] = {"bottom": [], "top": []}
    for side, indices in by_side.items():
        grouped: dict[tuple[complex, ...], list[int]] = {}
        for index in indices:
            grouped.setdefault(k_keys[index], []).append(index)
        groups = list(grouped.values())
        if not groups:
            raise ValueError(f"target mode inventory omitted the {side} side")
        for group_index in sorted({0, len(groups) // 2, len(groups) - 1}):
            for index in groups[group_index]:
                if index not in selected[side]:
                    selected[side].append(index)
    return selected


class _V22NativeFacetRule:
    """Bounded native facet quadrature plus the production MPC dual pullback.

    The saved V22 surface is a verified axis-aligned affine hex mesh. Each
    geometry-class/orientation pair therefore shares one local polynomial
    integral per wavevector; physical x/y phase and global cell rows are
    applied per facet. Full component support is filtered only after MPC,
    matching the first production support-filter stage.
    """

    def __init__(
        self,
        *,
        space: Any,
        dof_index_map: Any,
        mapping_rows: Sequence[Mapping[str, Any]],
        permutation_info: np.ndarray,
        polynomial: Any,
        quadrature_degree: int,
        cfg: Any,
        mpc_expansions: Mapping[int, tuple[Any, Any]],
        rolling_filter_digest: bool = False,
    ) -> None:
        from petsc4py import PETSc

        if int(space.mesh.comm.size) != 1:
            raise ValueError("V22 native boundary rule is qualified only for MPI1")
        self.space = space
        self.dof_index_map = dof_index_map
        self.polynomial = polynomial
        self.quadrature_degree = int(quadrature_degree)
        self.cfg = cfg
        self.native_size = int(dof_index_map.size_global)
        self.index_dtype = np.dtype(PETSc.IntType)
        self.needs_transform = bool(space.element.needs_dof_transformations)
        self._wave_key: tuple[Any, ...] | None = None
        self._basis_cache: dict[tuple[str, str, int], tuple[np.ndarray, ...]] = {}
        self.class_ids_by_side: dict[str, tuple[str, ...]] = {}
        groups: dict[tuple[str, str, int], dict[str, Any]] = {}
        for row in mapping_rows:
            side = str(row["side"])
            class_id = str(row["class_id"])
            cell_id = int(row["cell_id"])
            permutation = int(row["cell_permutation"])
            if (
                side not in {"bottom", "top"}
                or cell_id < 0
                or cell_id >= len(permutation_info)
                or int(permutation_info[cell_id]) != permutation
            ):
                raise ValueError("V22 native class row has an invalid side/cell orientation")
            bounds = np.asarray(row["cell_bounds_nm"], dtype=np.float64)
            ordered = np.asarray(row["ordered_cell_coordinates_nm"], dtype=np.float64)
            if bounds.shape != (3, 2) or ordered.shape != (8, 3):
                raise ValueError("V22 native facet class has unsupported geometry dimensions")
            lower, upper = bounds[:, 0], bounds[:, 1]
            if not np.isfinite(bounds).all() or np.any(upper <= lower):
                raise ValueError("V22 native facet class has nonpositive/nonfinite affine bounds")
            expected_order = np.asarray(
                [
                    [lower[0], lower[1], lower[2]],
                    [upper[0], lower[1], lower[2]],
                    [lower[0], upper[1], lower[2]],
                    [upper[0], upper[1], lower[2]],
                    [lower[0], lower[1], upper[2]],
                    [upper[0], lower[1], upper[2]],
                    [lower[0], upper[1], upper[2]],
                    [upper[0], upper[1], upper[2]],
                ],
                dtype=np.float64,
            )
            if not np.array_equal(ordered, expected_order):
                raise ValueError(
                    f"V22 native class {class_id} is not a qualified axis-aligned affine hexahedron"
                )
            key = (side, class_id, permutation)
            group = groups.get(key)
            if group is None:
                group = {
                    "side": side,
                    "class_id": class_id,
                    "permutation": permutation,
                    "widths": upper - lower,
                    "origins": [],
                    "global_dofs": [],
                    "facet_ids": [],
                }
                groups[key] = group
            elif not np.array_equal(group["widths"], upper - lower):
                raise ValueError(
                    f"V22 geometry class {class_id} contains different exact cell widths"
                )
            local_dofs = np.asarray(space.dofmap.cell_dofs(cell_id), dtype=np.int32)
            if local_dofs.shape != (882,):
                raise ValueError("V22 native geometry class is not bound to 882 local p6 rows")
            global_dofs = np.asarray(
                dof_index_map.local_to_global(local_dofs), dtype=PETSc.IntType
            )
            group["origins"].append(lower[:2].copy())
            group["global_dofs"].append(global_dofs.copy())
            group["facet_ids"].append(int(row["facet_id"]))
        self.groups: dict[str, dict[tuple[str, str, int], dict[str, Any]]] = {
            "bottom": {},
            "top": {},
        }
        for key, group in groups.items():
            group["origins"] = np.ascontiguousarray(group["origins"], dtype=np.float64)
            group["global_dofs"] = np.ascontiguousarray(
                group["global_dofs"], dtype=self.index_dtype
            )
            group["facet_ids"] = np.asarray(group["facet_ids"], dtype=np.int64)
            self.groups[group["side"]][key] = group
        for side in ("bottom", "top"):
            self.class_ids_by_side[side] = tuple(
                sorted({key[1] for key in self.groups[side]})
            )
            if not self.groups[side]:
                raise ValueError(f"V22 native surface omitted {side} geometry classes")

        slave_rows: list[int] = []
        master_rows: list[int] = []
        dual_coefficients: list[complex] = []
        for slave, (masters, coefficients) in sorted(mpc_expansions.items()):
            masters = np.asarray(masters, dtype=np.int64).reshape(-1)
            coefficients = np.asarray(coefficients, dtype=np.complex128).reshape(-1)
            if len(masters) != len(coefficients) or not len(masters):
                raise ValueError("V22 selected MPC expansion is empty or inconsistent")
            slave_rows.append(int(slave))
            master_rows.extend(map(int, masters))
            dual_coefficients.extend(np.conjugate(coefficients))
        self._slave_rows = np.asarray(slave_rows, dtype=self.index_dtype)
        self._master_rows = np.asarray(master_rows, dtype=self.index_dtype)
        self._dual_coefficients = np.asarray(dual_coefficients, dtype=np.complex128)
        candidate_parts = [
            np.asarray(group["global_dofs"], dtype=np.int64).reshape(-1)
            for side_groups in self.groups.values()
            for group in side_groups.values()
        ]
        if self._master_rows.size:
            candidate_parts.append(self._master_rows.astype(np.int64, copy=False))
        self.candidate_rows = np.unique(np.concatenate(candidate_parts)).astype(
            self.index_dtype, copy=False
        )
        if not self.candidate_rows.size:
            raise ValueError("V23 compact boundary/MPC row domain is empty")
        for side_groups in self.groups.values():
            for group in side_groups.values():
                compact_dofs = np.searchsorted(self.candidate_rows, group["global_dofs"])
                if not np.array_equal(self.candidate_rows[compact_dofs], group["global_dofs"]):
                    raise ValueError("V23 boundary cell row escaped the compact candidate domain")
                group["compact_dofs"] = np.ascontiguousarray(
                    compact_dofs, dtype=self.index_dtype
                )
        self._compact_slave_rows = np.ascontiguousarray(
            np.searchsorted(self.candidate_rows, self._slave_rows), dtype=self.index_dtype
        )
        self._compact_master_rows = np.ascontiguousarray(
            np.searchsorted(self.candidate_rows, self._master_rows), dtype=self.index_dtype
        )
        if (
            not np.array_equal(self.candidate_rows[self._compact_slave_rows], self._slave_rows)
            or not np.array_equal(self.candidate_rows[self._compact_master_rows], self._master_rows)
        ):
            raise ValueError("V23 MPC closure row escaped the compact candidate domain")
        self._master_counts = np.asarray(
            [len(mpc_expansions[int(row)][0]) for row in slave_rows], dtype=np.int64
        )
        self._class_facets_by_side = {
            side: {
                class_id: sum(
                    len(group["facet_ids"])
                    for key, group in self.groups[side].items()
                    if key[1] == class_id
                )
                for class_id in self.class_ids_by_side[side]
            }
            for side in ("bottom", "top")
        }
        self._rolling_filter_digest = bool(rolling_filter_digest)
        self._component_filter_hashers = {
            (side, component): (
                _RollingDigest() if self._rolling_filter_digest else hashlib.sha256()
            )
            for side in ("bottom", "top")
            for component in (0, 1)
        }
        self._component_filter_totals = {
            (side, component): {
                "assembled_component_vector_count": 0,
                "global_maximum_abs_max": 0.0,
                "global_cutoff_max": 0.0,
                "exact_nonzero_rows_before_filter": 0,
                "rows_dropped_by_global_mask": 0,
                "retained_rows": 0,
                "retained_norm_squared_sum": 0.0,
                "raw_rows_nonzero_before_mpc": 0,
                "raw_rows_tiny_before_mpc_relative_filter": 0,
                "raw_slave_rows_nonzero_before_mpc": 0,
            }
            for side in ("bottom", "top")
            for component in (0, 1)
        }
        self.assembly_stats = {
            "component_assembly_calls": 0,
            "native_group_integral_builds": 0,
            "native_facet_contributions": 0,
            "component_wall_seconds_total": 0.0,
            "component_process_cpu_seconds_total": 0.0,
            "group_integral_phase_wall_seconds_total": 0.0,
            "group_integral_phase_process_cpu_seconds_total": 0.0,
            "mpc_pullback_phase_wall_seconds_total": 0.0,
            "mpc_pullback_phase_process_cpu_seconds_total": 0.0,
            "global_filter_phase_wall_seconds_total": 0.0,
            "global_filter_phase_process_cpu_seconds_total": 0.0,
            "last_mode_key": None,
            "last_class_ids_by_side": {},
            "last_component_wall_seconds": None,
            "last_component_process_cpu_seconds": None,
            "support_filter": {
                "stage": "after actual finalized-MPC E^H pullback",
                "relative_tol": 1e-13,
                "absolute_floor": 0.0,
                "zero_entries_removed_only_by_exact_zero_or_global_filter": True,
            },
        }

    def compact_positions(self, global_rows: Sequence[int]) -> np.ndarray:
        rows = np.asarray(global_rows, dtype=np.int64).reshape(-1)
        positions = np.searchsorted(self.candidate_rows, rows)
        valid = positions < len(self.candidate_rows)
        matched = np.zeros(len(rows), dtype=np.bool_)
        matched[valid] = self.candidate_rows[positions[valid]] == rows[valid]
        if not np.all(matched):
            missing = rows[~matched][:8].tolist()
            raise ValueError(f"global rows escaped the compact boundary/MPC closure: {missing}")
        return positions

    def _mode_local_rows(self, side: str, class_id: str, permutation: int, mode: Any):
        wave_key = (
            side,
            complex(mode.alpha),
            complex(mode.gamma),
            complex(mode.k_vector[2]),
            self.quadrature_degree,
        )
        if wave_key != self._wave_key:
            self._wave_key = wave_key
            self._basis_cache.clear()
        cache_key = (side, class_id, int(permutation))
        cached = self._basis_cache.get(cache_key)
        if cached is not None:
            return cached, False
        group = self.groups[side][cache_key]
        integrated = self.polynomial.integral_native(
            side,
            np.asarray(
                [complex(mode.alpha), complex(mode.gamma), 0.0 + 0.0j],
                dtype=np.complex128,
            ),
            np.diag(group["widths"]),
            np.zeros(3, dtype=np.float64),
            self.quadrature_degree,
        )
        local_rows: list[np.ndarray] = []
        for component in (0, 1):
            values = np.ascontiguousarray(integrated[:, component], dtype=np.complex128)
            if self.needs_transform:
                self.space.element.T_apply(
                    values,
                    np.asarray([permutation], dtype=np.uint32),
                    1,
                )
            local_rows.append(values)
        cached = tuple(local_rows)
        self._basis_cache[cache_key] = cached
        self.assembly_stats["native_group_integral_builds"] += 1
        return cached, True

    def assemble_component(self, mode: Any, component: int) -> tuple[np.ndarray, np.ndarray]:
        if component not in (0, 1) or str(mode.side) not in self.groups:
            raise ValueError("V22 native surface component/side is unsupported")
        if int(self.space.mesh.comm.size) != 1:
            raise ValueError("V22 native surface assembly is qualified only for MPI1")
        assembled_at = perf_counter()
        assembled_cpu_at = process_time()
        vector = np.zeros(len(self.candidate_rows), dtype=np.complex128)
        side = str(mode.side)
        group_wall_at = perf_counter()
        group_cpu_at = process_time()
        for key, group in self.groups[side].items():
            local_pair, _built = self._mode_local_rows(
                side, key[1], key[2], mode
            )
            local_values = local_pair[component]
            active = np.flatnonzero(local_values != 0.0)
            if not active.size:
                continue
            phase = np.exp(
                1j
                * (
                    complex(mode.alpha) * group["origins"][:, 0]
                    + complex(mode.gamma) * group["origins"][:, 1]
                )
            )
            rows = group["compact_dofs"][:, active]
            values = phase[:, None] * local_values[active][None, :]
            np.add.at(vector, rows.reshape(-1), values.reshape(-1))
            self.assembly_stats["native_facet_contributions"] += len(
                group["facet_ids"]
            )
        group_wall_seconds = perf_counter() - group_wall_at
        group_cpu_seconds = process_time() - group_cpu_at
        mpc_wall_at = perf_counter()
        mpc_cpu_at = process_time()

        raw_magnitudes = np.abs(vector)
        raw_maximum = float(np.max(raw_magnitudes, initial=0.0))
        raw_cutoff = 1e-13 * raw_maximum
        filter_total = self._component_filter_totals[(side, component)]
        filter_total["raw_rows_nonzero_before_mpc"] += int(
            np.count_nonzero(raw_magnitudes)
        )
        filter_total["raw_rows_tiny_before_mpc_relative_filter"] += int(
            np.count_nonzero((raw_magnitudes > 0.0) & (raw_magnitudes < raw_cutoff))
        )
        filter_total["raw_slave_rows_nonzero_before_mpc"] += int(
            np.count_nonzero(vector[self._compact_slave_rows])
        )
        del raw_magnitudes
        if self._slave_rows.size:
            slave_values = vector[self._compact_slave_rows].copy()
            routed_values = np.repeat(slave_values, self._master_counts)
            np.add.at(
                vector,
                self._compact_master_rows,
                self._dual_coefficients * routed_values,
            )
            vector[self._compact_slave_rows] = 0.0 + 0.0j
        mpc_wall_seconds = perf_counter() - mpc_wall_at
        mpc_cpu_seconds = process_time() - mpc_cpu_at
        filter_wall_at = perf_counter()
        filter_cpu_at = process_time()
        magnitudes = np.abs(vector)
        maximum = float(np.max(magnitudes, initial=0.0))
        cutoff = 1e-13 * maximum
        nonzero_before = int(np.count_nonzero(magnitudes))
        compact_rows = np.flatnonzero(magnitudes > cutoff)
        rows = np.ascontiguousarray(self.candidate_rows[compact_rows], dtype=self.index_dtype)
        values = np.ascontiguousarray(vector[compact_rows], dtype=np.complex128)
        filter_total["assembled_component_vector_count"] += 1
        filter_total["global_maximum_abs_max"] = max(
            filter_total["global_maximum_abs_max"], maximum
        )
        filter_total["global_cutoff_max"] = max(
            filter_total["global_cutoff_max"], cutoff
        )
        filter_total["exact_nonzero_rows_before_filter"] += nonzero_before
        filter_total["rows_dropped_by_global_mask"] += nonzero_before - len(rows)
        filter_total["retained_rows"] += len(rows)
        filter_total["retained_norm_squared_sum"] += float(np.vdot(values, values).real)
        filter_hasher = self._component_filter_hashers[(side, component)]
        filter_hasher.update(
            np.asarray(
                [int(mode.m), int(mode.n)], dtype="<i8"
            ).tobytes()
        )
        filter_hasher.update(str(mode.polarization).encode("ascii"))
        filter_hasher.update(np.ascontiguousarray(rows).tobytes())
        filter_hasher.update(values.tobytes())
        filter_wall_seconds = perf_counter() - filter_wall_at
        filter_cpu_seconds = process_time() - filter_cpu_at
        self.assembly_stats["component_assembly_calls"] += 1
        self.assembly_stats["last_mode_key"] = [
            side,
            int(mode.m),
            int(mode.n),
            str(mode.polarization),
        ]
        self.assembly_stats["last_class_ids_by_side"] = {
            side: list(self.class_ids_by_side[side])
        }
        component_wall_seconds = perf_counter() - assembled_at
        component_cpu_seconds = process_time() - assembled_cpu_at
        self.assembly_stats["component_wall_seconds_total"] += component_wall_seconds
        self.assembly_stats["component_process_cpu_seconds_total"] += component_cpu_seconds
        self.assembly_stats["group_integral_phase_wall_seconds_total"] += group_wall_seconds
        self.assembly_stats["group_integral_phase_process_cpu_seconds_total"] += group_cpu_seconds
        self.assembly_stats["mpc_pullback_phase_wall_seconds_total"] += mpc_wall_seconds
        self.assembly_stats["mpc_pullback_phase_process_cpu_seconds_total"] += mpc_cpu_seconds
        self.assembly_stats["global_filter_phase_wall_seconds_total"] += filter_wall_seconds
        self.assembly_stats["global_filter_phase_process_cpu_seconds_total"] += filter_cpu_seconds
        self.assembly_stats["last_component_wall_seconds"] = component_wall_seconds
        self.assembly_stats["last_component_process_cpu_seconds"] = component_cpu_seconds
        # Preserve the historical field as an alias for existing V22 consumers.
        self.assembly_stats["last_component_seconds"] = component_wall_seconds
        return rows, values

    def compare_full_domain_reference(
        self,
        mode: Any,
        component: int,
        *,
        field_values_by_candidate_rows: np.ndarray | None = None,
        alpha: complex = 1.0 + 0.0j,
    ) -> dict[str, Any]:
        """Require exact compact/full-domain equivalence for a bounded witness."""

        field_values = (
            None
            if field_values_by_candidate_rows is None
            else np.asarray(field_values_by_candidate_rows, dtype=np.complex128)
        )
        if field_values is not None and field_values.shape != self.candidate_rows.shape:
            raise ValueError("paired timing field differs from the compact candidate-row domain")
        alpha_value = complex(alpha)
        if not np.isfinite(alpha_value.real) or not np.isfinite(alpha_value.imag) or alpha_value == 0.0:
            raise ValueError("paired timing alpha must be finite and nonzero")

        self._basis_cache.clear()
        compact_wall_at = perf_counter()
        compact_cpu_at = process_time()
        compact_rows, compact_values = self.assemble_component(mode, component)
        compact_b_alpha = alpha_value * compact_values
        compact_d_x = (
            None
            if field_values is None
            else np.dot(compact_values, field_values[self.compact_positions(compact_rows)])
        )
        compact_wall_seconds = perf_counter() - compact_wall_at
        compact_cpu_seconds = process_time() - compact_cpu_at

        self._basis_cache.clear()
        reference_wall_at = perf_counter()
        reference_cpu_at = process_time()
        reference = np.zeros(self.native_size, dtype=np.complex128)
        side = str(mode.side)
        for key, group in self.groups[side].items():
            local_pair, _built = self._mode_local_rows(side, key[1], key[2], mode)
            local_values = local_pair[component]
            active = np.flatnonzero(local_values != 0.0)
            if not active.size:
                continue
            phase = np.exp(
                1j
                * (
                    complex(mode.alpha) * group["origins"][:, 0]
                    + complex(mode.gamma) * group["origins"][:, 1]
                )
            )
            values = phase[:, None] * local_values[active][None, :]
            np.add.at(
                reference,
                group["global_dofs"][:, active].reshape(-1),
                values.reshape(-1),
            )
        raw_slave_nonzero = int(np.count_nonzero(reference[self._slave_rows]))
        if self._slave_rows.size:
            slave_values = reference[self._slave_rows].copy()
            routed_values = np.repeat(slave_values, self._master_counts)
            np.add.at(
                reference,
                self._master_rows,
                self._dual_coefficients * routed_values,
            )
            reference[self._slave_rows] = 0.0 + 0.0j
        magnitudes = np.abs(reference)
        maximum = float(np.max(magnitudes, initial=0.0))
        cutoff = 1e-13 * maximum
        reference_rows = np.flatnonzero(magnitudes > cutoff).astype(
            self.index_dtype, copy=False
        )
        reference_values = np.ascontiguousarray(reference[reference_rows])
        reference_b_alpha = alpha_value * reference_values
        reference_d_x = (
            None
            if field_values is None
            else np.dot(
                reference_values,
                field_values[self.compact_positions(reference_rows)],
            )
        )
        reference_wall_seconds = perf_counter() - reference_wall_at
        reference_cpu_seconds = process_time() - reference_cpu_at
        support_equal = np.array_equal(compact_rows, reference_rows)
        values_equal = np.array_equal(compact_values, reference_values)
        b_alpha_equal = np.array_equal(compact_b_alpha, reference_b_alpha)
        d_x_equal = (
            field_values is None
            or (compact_d_x == reference_d_x)
        )
        positive = magnitudes[magnitudes > 0.0]
        cutoff_distance = (
            float(np.min(np.abs(positive / cutoff - 1.0))) if cutoff > 0.0 and positive.size else None
        )
        result = {
            "mode_key": [side, int(mode.m), int(mode.n), str(mode.polarization)],
            "component": int(component),
            "status": "PASS_EXACT" if support_equal and values_equal else "FAILED",
            "support_rows_equal": bool(support_equal),
            "retained_values_bitwise_equal": bool(values_equal),
            "B_alpha_bitwise_equal": bool(b_alpha_equal),
            "D_x_bitwise_equal": bool(d_x_equal),
            "compact_row_count": int(len(compact_rows)),
            "reference_row_count": int(len(reference_rows)),
            "compact_rows_sha256": _array_sha256(compact_rows),
            "reference_rows_sha256": _array_sha256(reference_rows),
            "compact_values_sha256": _array_sha256(compact_values),
            "reference_values_sha256": _array_sha256(reference_values),
            "maximum_abs": maximum,
            "cutoff": cutoff,
            "closest_nonzero_to_cutoff_relative_distance": cutoff_distance,
            "raw_mpc_slave_rows_nonzero_before_pullback": raw_slave_nonzero,
            "full_vector_bytes": int(self.native_size * np.dtype(np.complex128).itemsize),
            "paired_timing": {
                "status": "MEASURED_SAME_MODE_FIELD_ALPHA_COLD_CACHE" if field_values is not None else "MEASURED_SAME_MODE_COLD_CACHE",
                "mode_key": [side, int(mode.m), int(mode.n), str(mode.polarization)],
                "component": int(component),
                "field_sha256": None if field_values is None else _array_sha256(field_values),
                "alpha": {"real": alpha_value.real, "imag": alpha_value.imag},
                "alpha_sha256": _array_sha256(np.asarray([alpha_value], dtype=np.complex128)),
                "cache_policy": "basis cache cleared before each path; equal integral/cache state",
                "compact_wall_seconds": compact_wall_seconds,
                "compact_process_cpu_seconds": compact_cpu_seconds,
                "full_domain_reference_wall_seconds": reference_wall_seconds,
                "full_domain_reference_process_cpu_seconds": reference_cpu_seconds,
                "compact_B_alpha_sha256": _array_sha256(compact_b_alpha),
                "reference_B_alpha_sha256": _array_sha256(reference_b_alpha),
                "compact_D_x_sha256": None if compact_d_x is None else _array_sha256(np.asarray([compact_d_x], dtype=np.complex128)),
                "reference_D_x_sha256": None if reference_d_x is None else _array_sha256(np.asarray([reference_d_x], dtype=np.complex128)),
            },
        }
        if result["status"] != "PASS_EXACT" or not b_alpha_equal or not d_x_equal:
            raise ValueError(
                "compact boundary component differs from the complete global-row reference: "
                f"{result}"
            )
        return result

    def restore_filter_audit(self, audit: Mapping[str, Any]) -> None:
        if not self._rolling_filter_digest:
            raise ValueError("only V23 rolling component digests are restartable")
        for side in ("bottom", "top"):
            for component in (0, 1):
                row = audit.get(side, {}).get(str(component), {})
                if not isinstance(row, Mapping):
                    raise ValueError("V23 checkpoint component filter audit is incomplete")
                digest = row.get("retained_stream_sha256")
                if not isinstance(digest, str) or len(digest) != 64:
                    raise ValueError("V23 checkpoint component digest is malformed")
                self._component_filter_hashers[(side, component)] = _RollingDigest(digest)
                totals = self._component_filter_totals[(side, component)]
                for key in tuple(totals):
                    if key in row:
                        totals[key] = row[key]
                for key in (
                    "assembled_component_vector_count",
                    "exact_nonzero_rows_before_filter",
                    "rows_dropped_by_global_mask",
                    "retained_rows",
                    "raw_rows_nonzero_before_mpc",
                    "raw_rows_tiny_before_mpc_relative_filter",
                    "raw_slave_rows_nonzero_before_mpc",
                ):
                    value = totals[key]
                    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                        raise ValueError("V23 checkpoint component filter counter is invalid")
    def filter_audit(self) -> dict[str, Any]:
        return {
            side: {
                str(component): {
                    **dict(self._component_filter_totals[(side, component)]),
                    "retained_value_norm": float(
                        np.sqrt(
                            self._component_filter_totals[(side, component)][
                                "retained_norm_squared_sum"
                            ]
                        )
                    ),
                    "retained_stream_sha256": self._component_filter_hashers[
                        (side, component)
                    ].copy().hexdigest(),
                    "scope": "complete 882-row boundary-cell union plus finalized MPC master closure after MPC E^H; rank 0/MPI1",
                }
                for component in (0, 1)
            }
            for side in ("bottom", "top")
        }

    def assemblers(self) -> dict[tuple[str, int], Any]:
        result = {}
        for side in ("bottom", "top"):
            for component in (0, 1):
                result[(side, component)] = _V22NativeSurfaceComponent(self, side, component)
        return result


class _V22NativeSurfaceComponent:
    def __init__(self, rule: _V22NativeFacetRule, side: str, component: int) -> None:
        self.rule = rule
        self.side = side
        self.component = int(component)
        self.boundary_reference_z = float(
            rule.cfg.physical_z_max if side == "top" else rule.cfg.physical_z_min
        )
        self.boundary_tag = int(rule.cfg.tags.z_max if side == "top" else rule.cfg.tags.z_min)
        self.quadrature_degree = rule.quadrature_degree

    def assemble_entries(self, mode: Any, _mpc: Any) -> tuple[np.ndarray, np.ndarray]:
        if str(mode.side) != self.side:
            raise ValueError("V22 native surface adapter received a different mode side")
        return self.rule.assemble_component(mode, self.component)


def _native_quadrature_identity(quadrature_degree: int) -> dict[str, Any]:
    import basix

    points, weights = basix.make_quadrature(basix.CellType.interval, int(quadrature_degree))
    return {
        "degree": int(quadrature_degree),
        "rule": "Basix default interval Gauss-Legendre tensor product used by FacetPolynomial.integral_native",
        "facet_cell": "quadrilateral",
        "interval_point_count": int(len(points)),
        "tensor_product_point_count": int(len(points) ** 2),
        "interval_points_sha256": _array_sha256(points),
        "interval_weights_sha256": _array_sha256(weights),
        "tensor_product_weights_sha256": _array_sha256(np.outer(weights, weights)),
        "ffcx_compiled_forms_used": False,
        "local_polynomial_degree": 6,
    }


def _build_v22_native_gauge_context(
    *, space: Any, mesh_data: Any, mpc: Any, cfg: Any,
    quadrature_identity: Mapping[str, Any], permutation_info: np.ndarray,
    cell_dofmap_sha256: str,
) -> dict[str, Any]:
    import basix
    import dolfinx
    from petsc4py import PETSc
    from importlib.metadata import version as package_version

    from src.solvers.fullspace_dtn_action import _canonical_json_bytes

    module_paths = (
        Path(__file__),
        Path(__file__).with_name("fullspace_dtn_action.py"),
        Path(__file__).with_name("dtn_port_3d.py"),
        Path(__file__).with_name("directional_boundary.py"),
    )
    coefficients, offsets = mpc.coefficients()
    mesh = space.mesh
    payload = {
        "schema": "task40extra.dtn-plane-discrete-context.v1",
        "source_sha256": {
            path.name: _sha256_file(path) for path in module_paths
        },
        "mesh": {
            "geometry_x": _array_sha256(mesh.geometry.x),
            "geometry_dofmap": _array_sha256(mesh.geometry.dofmap),
            "facet_indices": _array_sha256(mesh_data.facet_tags.indices),
            "facet_values": _array_sha256(mesh_data.facet_tags.values),
            "cell_indices": _array_sha256(mesh_data.cell_tags.indices),
            "cell_values": _array_sha256(mesh_data.cell_tags.values),
        },
        "cell_dofmap_sha256": str(cell_dofmap_sha256),
        "orientation": _array_sha256(permutation_info),
        "needs_dof_transformations": bool(space.element.needs_dof_transformations),
        "basix_coefficients": _array_sha256(space.element.basix_element.coefficient_matrix),
        "element_degree": int(space.element.basix_element.degree),
        "element_map_type": space.element.basix_element.map_type.name,
        "MPC": {
            "slaves": _array_sha256(mpc.slaves),
            "masters": _array_sha256(mpc.masters.array),
            "coefficients": _array_sha256(coefficients),
            "offsets": _array_sha256(offsets),
        },
        "config_sha256": hashlib.sha256(_canonical_json_bytes(cfg.as_jsonable())).hexdigest(),
        "gauss": dict(quadrature_identity),
        "ABI": {
            "python": sys.version,
            "numpy": np.__version__,
            "basix": basix.__version__,
            "dolfinx": dolfinx.__version__,
            "dolfinx_mpc": package_version("dolfinx_mpc"),
            "PETSc": PETSc.Sys.getVersion(),
            "scalar": str(np.dtype(PETSc.ScalarType)),
            "integer": str(np.dtype(PETSc.IntType)),
        },
    }
    return payload


def _read_v22_campaign_state(root: Path) -> dict[str, Any]:
    from src.runners.task40_v10_campaign import (
        CAMPAIGN_ACCOUNTING_NAME,
        TASK40_V22_CAMPAIGN_WINDOW,
        load_fixed_campaign_window,
        read_campaign_state,
        time_namespace_identity,
    )

    registered_path = os.environ.get("TASK40_V10_CAMPAIGN_WINDOW")
    window_path = (
        Path(registered_path).resolve()
        if registered_path
        else (root / TASK40_V22_CAMPAIGN_WINDOW).resolve()
    )
    window = load_fixed_campaign_window(window_path)
    expected_sha = os.environ.get("TASK40_V10_CAMPAIGN_WINDOW_SHA256")
    if expected_sha is not None and expected_sha != window.sha256:
        raise ValueError("probe campaign window differs from the supervised V24/V23/V22 SHA")
    expected_accounting = os.environ.get("TASK40_V10_CAMPAIGN_ACCOUNTING")
    accounting_path = window.path.parent / CAMPAIGN_ACCOUNTING_NAME
    if expected_accounting is not None and Path(expected_accounting).resolve() != accounting_path:
        raise ValueError("probe campaign ledger differs from the registered window directory")
    return read_campaign_state(
        window,
        accounting_path,
        namespace_identity=time_namespace_identity(),
    )


def _write_v22_action_checkpoint(
    output_directory: Path,
    *,
    preflight: Mapping[str, Any],
    mode_inventory: Mapping[str, Any],
    mode_count: int,
    mode_counts_by_side: Mapping[str, int],
    class_mode_prefix: Mapping[str, Mapping[str, int]],
    support_rows_by_side: Mapping[str, Mapping[str, int]],
    stream_digest: Any,
    component_filter_audit: Mapping[str, Any],
    b_action: np.ndarray,
    d_values: np.ndarray,
    h_values: np.ndarray,
    candidate_rows: np.ndarray | None = None,
    checkpoint_directory: Path | None = None,
    restart_state: Mapping[str, Any] | None = None,
    checkpoint_interval: int = 8,
    failure_facts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    from src.runners.task40_v10_campaign import TASK40_V23_CAMPAIGN_SHA256

    is_v23 = os.environ.get("TASK40_V10_CAMPAIGN_WINDOW_SHA256") == TASK40_V23_CAMPAIGN_SHA256
    if is_v23 and restart_state is None:
        raise ValueError("V23 action checkpoints require the complete restart state")
    storage_directory = Path(checkpoint_directory or output_directory).resolve()
    storage_directory.mkdir(parents=True, exist_ok=True)
    prefix = "v23" if is_v23 else "v22"
    slot = (mode_count // max(int(checkpoint_interval), 1)) % 2
    data_path = storage_directory / f"{prefix}_mode_sweep_checkpoint_{slot}.npz"
    checkpoint_json_name = f"{prefix}_mode_sweep_checkpoint.json"
    temporary = data_path.with_suffix(data_path.suffix + ".tmp")
    b_compact_rows = np.flatnonzero(b_action != 0.0 + 0.0j)
    b_rows = (
        np.asarray(candidate_rows, dtype=np.int64)[b_compact_rows]
        if candidate_rows is not None
        else b_compact_rows.astype(np.int64, copy=False)
    )
    arrays = {
        "B_nonzero_rows": np.ascontiguousarray(b_rows, dtype=np.int64),
        "B_nonzero_values": np.ascontiguousarray(b_action[b_compact_rows], dtype=np.complex128),
        "D_completed_values": np.ascontiguousarray(d_values[:mode_count], dtype=np.complex128),
        "H_completed_values": np.ascontiguousarray(h_values[:mode_count], dtype=np.float64),
    }
    if is_v23:
        assert restart_state is not None
        cell_state = restart_state.get("m_c_state")
        if not isinstance(cell_state, Mapping):
            raise ValueError("V23 checkpoint omitted per-cell multiplicity state")
        for side in ("bottom", "top"):
            side_state = cell_state.get(side)
            if not isinstance(side_state, Mapping):
                raise ValueError("V23 checkpoint omitted one side's per-cell state")
            for metric in ("B", "D", "union"):
                metric_state = side_state.get(metric)
                if not isinstance(metric_state, Mapping):
                    raise ValueError("V23 checkpoint omitted one per-cell support metric")
                for state_name in (
                    "per_cell_mode_counts",
                    "per_cell_interior_row_memberships",
                ):
                    array_name = f"m_c_{side}_{metric}_{state_name}"
                    arrays[array_name] = np.ascontiguousarray(
                        metric_state[state_name], dtype=np.int64
                    )
    with temporary.open("wb") as stream:
        np.savez(stream, **arrays)
        stream.flush()
        os.fsync(stream.fileno())
    payload_sha256 = _sha256_file(temporary)
    temporary.replace(data_path)
    directory_fd = os.open(storage_directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    checkpoint = {
        "schema": (
            "task40extra.review_v23_compact_mode_sweep_checkpoint.v1"
            if is_v23
            else "task40extra.review_v22_mode_sweep_checkpoint.v2"
        ),
        "run_id": preflight.get("run_id"),
        "source_sha": preflight.get("source_sha"),
        "input_sha256": preflight.get("input_sha256"),
        "physical_model_sha256": preflight.get("physical_model_sha256"),
        "mode_manifest_sha256": mode_inventory.get("mode_manifest_sha256"),
        "ordered_mode_key_sha256": mode_inventory.get("ordered_mode_key_sha256"),
        "campaign_window_sha256": os.environ.get("TASK40_V10_CAMPAIGN_WINDOW_SHA256"),
        "compact_candidate_row_count": (
            int(len(candidate_rows)) if candidate_rows is not None else None
        ),
        "compact_candidate_rows_sha256": (
            _array_sha256(candidate_rows) if candidate_rows is not None else None
        ),
        "checkpoint_json_path": os.path.relpath(
            storage_directory / checkpoint_json_name, Path(output_directory).resolve()
        ),
        "checkpoint_interval_modes": int(checkpoint_interval),
        "completed_mode_count": int(mode_count),
        "next_mode_index": int(mode_count),
        "mode_count_by_side": dict(mode_counts_by_side),
        "completed_side_class_mode_prefix": {
            side: dict(class_mode_prefix[side]) for side in ("bottom", "top")
        },
        "global_B_support_row_count_by_side": {
            side: int(support_rows_by_side[side]["B"]) for side in ("bottom", "top")
        },
        "global_D_support_row_count_by_side": {
            side: int(support_rows_by_side[side]["D"]) for side in ("bottom", "top")
        },
        "global_B_D_support_row_count_by_side": {
            side: {
                key: int(value)
                for key, value in support_rows_by_side[side].items()
            }
            for side in ("bottom", "top")
        },
        "stream_prefix_sha256": stream_digest.copy().hexdigest(),
        "component_filter_prefix": {
            side: {
                str(component): dict(component_filter_audit[side][str(component)])
                for component in (0, 1)
            }
            for side in ("bottom", "top")
        },
        "actual_action_payload": {
            "path": data_path.name,
            "sha256": payload_sha256,
            "B_exact_nonzero_row_count": int(len(b_rows)),
            "D_completed_value_count": int(mode_count),
            "H_completed_value_count": int(mode_count),
            "B_values_are_exact_nonzeros_without_numeric_threshold": True,
        },
        "checkpoint_scope": (
            "atomic latest two-slot checkpoint of the actual B action sparse support and values, "
            "completed D/H mode values, streaming digest, and exact side/class/mode prefix"
        ),
    }
    if is_v23:
        assert restart_state is not None
        checkpoint["restart_state"] = {
            "field_sha256": restart_state.get("field_sha256"),
            "rng_bit_generator_state_after_completed_mode_prefix": restart_state.get(
                "rng_state"
            ),
            "stream_digest_state": stream_digest.copy().hexdigest(),
            "support_category_totals": restart_state.get("support_category_totals"),
            "calibration_results": restart_state.get("calibration_results"),
            "mode_sweep_elapsed_seconds": float(
                restart_state.get("mode_sweep_elapsed_seconds", 0.0)
            ),
            "mode_sweep_process_cpu_seconds": float(
                restart_state.get("mode_sweep_process_cpu_seconds", 0.0)
            ),
            "mode_timing_by_side": restart_state.get("mode_timing_by_side"),
            "expected_mode_counts_by_side": restart_state.get(
                "expected_mode_counts_by_side"
            ),
            "per_cell_state_array_prefix": "m_c_{side}_{metric}_",
        }
        checkpoint["checkpoint_scope"] = (
            "restartable V23 compact B action by global row IDs, completed D/H prefix, "
            "field identity, alpha RNG state, per-cell per-mode inventory and separate raw "
            "row memberships, support categories, component-filter audit, calibration state, "
            "stream digest, and exact side/class/mode prefix"
        )
    if failure_facts is not None:
        checkpoint["fail_fast_operator_gate_failure"] = dict(failure_facts)
    _write_json(storage_directory / checkpoint_json_name, checkpoint)
    return checkpoint


def _v23_checkpoint_directory(
    root: Path,
    *,
    preflight: Mapping[str, Any],
    mode_inventory: Mapping[str, Any],
    campaign_window_sha256: str,
) -> Path:
    identity = {
        "source_sha": preflight.get("source_sha"),
        "input_sha256": preflight.get("input_sha256"),
        "physical_model_sha256": preflight.get("physical_model_sha256"),
        "mode_manifest_sha256": mode_inventory.get("mode_manifest_sha256"),
        "ordered_mode_key_sha256": mode_inventory.get("ordered_mode_key_sha256"),
        "campaign_window_sha256": campaign_window_sha256,
    }
    source_sha = identity["source_sha"]
    content_hashes = tuple(
        value for key, value in identity.items() if key != "source_sha"
    )
    valid_source_sha = (
        isinstance(source_sha, str)
        and len(source_sha) == 40
        and all(character in "0123456789abcdef" for character in source_sha.lower())
    )
    valid_content_hashes = all(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
        for value in content_hashes
    )
    if not valid_source_sha or not valid_content_hashes:
        raise ValueError("V23 checkpoint identity is incomplete or malformed")
    key = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return (
        Path(root).resolve()
        / "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v23_wsl/operator_checkpoints"
        / key
    )


def _load_v23_action_checkpoint(
    checkpoint_directory: Path,
    *,
    preflight: Mapping[str, Any],
    mode_inventory: Mapping[str, Any],
    campaign_window_sha256: str,
    candidate_rows: np.ndarray,
    modes: Sequence[Any],
    h_values: np.ndarray,
    side_cell_counts: Mapping[str, int],
    expected_field_sha256: str,
) -> dict[str, Any] | None:
    """Load a hash-bound V23 prefix, refusing any stale or partial identity."""

    checkpoint_directory = Path(checkpoint_directory).resolve()
    metadata_path = checkpoint_directory / "v23_mode_sweep_checkpoint.json"
    if not metadata_path.exists():
        return None
    checkpoint = json.loads(metadata_path.read_text(encoding="utf-8"))
    if checkpoint.get("schema") != "task40extra.review_v23_compact_mode_sweep_checkpoint.v1":
        raise ValueError("V23 checkpoint schema differs from the restart contract")
    identity = {
        "source_sha": preflight.get("source_sha"),
        "input_sha256": preflight.get("input_sha256"),
        "physical_model_sha256": preflight.get("physical_model_sha256"),
        "mode_manifest_sha256": mode_inventory.get("mode_manifest_sha256"),
        "ordered_mode_key_sha256": mode_inventory.get("ordered_mode_key_sha256"),
        "campaign_window_sha256": campaign_window_sha256,
        "compact_candidate_row_count": int(len(candidate_rows)),
        "compact_candidate_rows_sha256": _array_sha256(candidate_rows),
    }
    for key, expected in identity.items():
        if checkpoint.get(key) != expected:
            raise ValueError(f"V23 checkpoint identity mismatch for {key}")
    if checkpoint.get("fail_fast_operator_gate_failure") is not None:
        raise ValueError("V23 checkpoint records a failed numerical gate and cannot resume")
    count = checkpoint.get("completed_mode_count")
    next_index = checkpoint.get("next_mode_index")
    if (
        not isinstance(count, int)
        or isinstance(count, bool)
        or not 0 <= count <= len(modes)
        or next_index != count
    ):
        raise ValueError("V23 checkpoint mode prefix is invalid")
    expected_side_counts = {
        side: sum(str(mode.side) == side for mode in modes[:count])
        for side in ("bottom", "top")
    }
    if checkpoint.get("mode_count_by_side") != expected_side_counts:
        raise ValueError("V23 checkpoint side-mode prefix is inconsistent with ordered modes")
    prefix = checkpoint.get("completed_side_class_mode_prefix")
    if not isinstance(prefix, Mapping) or any(
        not isinstance(prefix.get(side), Mapping)
        or any(value != expected_side_counts[side] for value in prefix[side].values())
        for side in ("bottom", "top")
    ):
        raise ValueError("V23 checkpoint side/class prefix is inconsistent")
    payload = checkpoint.get("actual_action_payload")
    if not isinstance(payload, Mapping) or payload.get("B_values_are_exact_nonzeros_without_numeric_threshold") is not True:
        raise ValueError("V23 checkpoint action payload declaration is invalid")
    data_path = (checkpoint_directory / str(payload.get("path", ""))).resolve()
    if data_path.parent != checkpoint_directory or not data_path.is_file():
        raise ValueError("V23 checkpoint NPZ payload is missing or escaped its directory")
    if _sha256_file(data_path) != payload.get("sha256"):
        raise ValueError("V23 checkpoint NPZ hash does not match its receipt")
    restart = checkpoint.get("restart_state")
    if not isinstance(restart, Mapping) or restart.get("field_sha256") != expected_field_sha256:
        raise ValueError("V23 checkpoint saved-field identity differs from the regenerated field")
    rng_state = restart.get("rng_bit_generator_state_after_completed_mode_prefix")
    stream_state = restart.get("stream_digest_state")
    elapsed_prefix = float(restart.get("mode_sweep_elapsed_seconds", 0.0))
    cpu_elapsed_prefix = float(restart.get("mode_sweep_process_cpu_seconds", 0.0))
    mode_timing_by_side = restart.get("mode_timing_by_side")
    if not isinstance(rng_state, Mapping) or not isinstance(stream_state, str) or len(stream_state) != 64:
        raise ValueError("V23 checkpoint omitted its RNG or stream-digest continuation state")
    if (
        not np.isfinite(elapsed_prefix)
        or elapsed_prefix < 0.0
        or not np.isfinite(cpu_elapsed_prefix)
        or cpu_elapsed_prefix < 0.0
    ):
        raise ValueError("V23 checkpoint cumulative mode time is invalid")
    if not isinstance(mode_timing_by_side, Mapping):
        raise ValueError("V23 checkpoint omitted side-specific wall/CPU timing state")
    for side in ("bottom", "top"):
        side_timing = mode_timing_by_side.get(side)
        expected = expected_side_counts[side]
        if (
            not isinstance(side_timing, Mapping)
            or side_timing.get("completed_modes") != expected
            or not isinstance(side_timing.get("wall_seconds"), (int, float))
            or not np.isfinite(float(side_timing["wall_seconds"]))
            or float(side_timing["wall_seconds"]) < 0.0
            or not isinstance(side_timing.get("process_cpu_seconds"), (int, float))
            or not np.isfinite(float(side_timing["process_cpu_seconds"]))
            or float(side_timing["process_cpu_seconds"]) < 0.0
        ):
            raise ValueError("V23 checkpoint side-specific timing does not match its mode prefix")
    try:
        bytes.fromhex(stream_state)
    except ValueError as error:
        raise ValueError("V23 checkpoint stream digest is malformed") from error
    with np.load(data_path, allow_pickle=False) as archive:
        required = {
            "B_nonzero_rows",
            "B_nonzero_values",
            "D_completed_values",
            "H_completed_values",
        }
        if not required.issubset(archive.files):
            raise ValueError("V23 checkpoint omitted an action payload array")
        b_rows = np.asarray(archive["B_nonzero_rows"], dtype=np.int64)
        b_values = np.asarray(archive["B_nonzero_values"], dtype=np.complex128)
        d_values = np.asarray(archive["D_completed_values"], dtype=np.complex128)
        h_completed = np.asarray(archive["H_completed_values"], dtype=np.float64)
        candidate = np.asarray(candidate_rows, dtype=np.int64)
        if (
            b_rows.ndim != 1
            or b_values.shape != b_rows.shape
            or (
                len(b_rows)
                and (np.any(np.diff(b_rows) <= 0) or np.any(b_values == 0.0))
            )
            or d_values.shape != (count,)
            or h_completed.shape != (count,)
            or not np.isfinite(b_values).all()
            or not np.isfinite(d_values).all()
            or not np.isfinite(h_completed).all()
            or not np.array_equal(h_completed, np.asarray(h_values[:count], dtype=np.float64))
        ):
            raise ValueError("V23 checkpoint action arrays have invalid shape/order/value")
        positions = np.searchsorted(candidate, b_rows)
        if len(b_rows) and (
            np.any(positions >= len(candidate))
            or not np.array_equal(candidate[positions], b_rows)
        ):
            raise ValueError("V23 checkpoint B global rows escaped the compact candidate domain")
        b_action = np.zeros(len(candidate), dtype=np.complex128)
        b_action[positions] = b_values
        cell_state: dict[str, dict[str, dict[str, np.ndarray]]] = {}
        for side in ("bottom", "top"):
            cell_state[side] = {}
            for metric in ("B", "D", "union"):
                cell_state[side][metric] = {}
                for state_name in (
                    "per_cell_mode_counts",
                    "per_cell_interior_row_memberships",
                ):
                    key = f"m_c_{side}_{metric}_{state_name}"
                    if key not in archive.files:
                        raise ValueError(f"V23 checkpoint omitted {key}")
                    value = np.asarray(archive[key], dtype=np.int64)
                    if value.shape != (int(side_cell_counts[side]),) or np.any(value < 0):
                        raise ValueError(f"V23 checkpoint array {key} has invalid dimensions or values")
                    if state_name == "per_cell_mode_counts" and np.any(
                        value > expected_side_counts[side]
                    ):
                        raise ValueError(f"V23 checkpoint array {key} exceeds the mode prefix")
                    if state_name == "per_cell_interior_row_memberships" and np.any(
                        value > expected_side_counts[side] * 450
                    ):
                        raise ValueError(f"V23 checkpoint array {key} exceeds the row prefix")
                    cell_state[side][metric][state_name] = value.copy()
    support_rows = checkpoint.get("global_B_support_row_count_by_side")
    support_d = checkpoint.get("global_D_support_row_count_by_side")
    category_totals = restart.get("support_category_totals")
    calibration_results = restart.get("calibration_results")
    if not all(isinstance(value, Mapping) for value in (support_rows, support_d, category_totals, calibration_results)):
        raise ValueError("V23 checkpoint omitted accumulated support/calibration state")
    support_by_side = {
        side: {
            "B": int(support_rows[side]),
            "D": int(support_d[side]),
            "nonempty_B_modes": 0,
            "nonempty_D_modes": 0,
        }
        for side in ("bottom", "top")
    }
    raw_support = checkpoint.get("global_B_D_support_row_count_by_side")
    if isinstance(raw_support, Mapping):
        for side in ("bottom", "top"):
            support_by_side[side]["B"] = int(raw_support[side]["B"])
            support_by_side[side]["D"] = int(raw_support[side]["D"])
            support_by_side[side]["nonempty_B_modes"] = int(raw_support[side]["nonempty_B_modes"])
            support_by_side[side]["nonempty_D_modes"] = int(raw_support[side]["nonempty_D_modes"])
    else:
        raise ValueError("V23 checkpoint omitted support mode counters")
    return {
        "checkpoint": checkpoint,
        "mode_count": count,
        "b_action": b_action,
        "d_values": d_values.copy(),
        "cell_state": cell_state,
        "support_rows_by_side": support_by_side,
        "support_category_totals": category_totals,
        "class_mode_prefix": prefix,
        "component_filter_audit": checkpoint.get("component_filter_prefix"),
        "calibration_results": calibration_results,
        "rng_state": rng_state,
        "stream_digest_state": stream_state,
        "mode_sweep_elapsed_seconds": elapsed_prefix,
        "mode_sweep_process_cpu_seconds": cpu_elapsed_prefix,
        "mode_timing_by_side": {
            side: {
                "completed_modes": int(mode_timing_by_side[side]["completed_modes"]),
                "wall_seconds": float(mode_timing_by_side[side]["wall_seconds"]),
                "process_cpu_seconds": float(mode_timing_by_side[side]["process_cpu_seconds"]),
            }
            for side in ("bottom", "top")
        },
    }


def _native_calibration_gate_failure(
    *,
    side: str,
    mode_index: int,
    mode_key: Sequence[Any],
    calibration_result: Mapping[str, Any],
    relative_limit: float = 1e-10,
) -> dict[str, Any] | None:
    """Return compact failure facts when the first native witness misses a gate."""

    def finite_metric(name: str) -> float | None:
        try:
            value = float(calibration_result[name])
        except (KeyError, TypeError, ValueError):
            return None
        return value if np.isfinite(value) else None

    b_relative = finite_metric("production_B_relative")
    d_relative = finite_metric("production_D_relative")
    d_vector_relative = finite_metric("production_D_vector_relative")
    raw_scope_relative = finite_metric("raw_B_interior_vs_filtered_relative")
    b_domain = calibration_result.get("production_B_reference_domain")
    d_domain = calibration_result.get("production_D_reference_domain")
    b_support_digest = calibration_result.get("production_B_support_digest")
    d_support_digest = calibration_result.get("production_D_support_digest")
    b_support_mismatch = calibration_result.get("production_B_support_mismatch_count")
    d_support_mismatch = calibration_result.get("production_D_support_mismatch_count")

    def valid_support_digest(value: Any) -> bool:
        return bool(
            isinstance(value, Mapping)
            and all(
                isinstance(value.get(name), str)
                and len(value[name]) == 64
                and all(character in "0123456789abcdef" for character in value[name])
                for name in (
                    "direct_rows_sha256",
                    "grouped_rows_sha256",
                    "direct_values_sha256",
                    "grouped_values_sha256",
                )
            )
        )

    valid_production_support = bool(
        valid_support_digest(b_support_digest)
        and valid_support_digest(d_support_digest)
        and isinstance(b_support_mismatch, int)
        and not isinstance(b_support_mismatch, bool)
        and b_support_mismatch >= 0
        and isinstance(d_support_mismatch, int)
        and not isinstance(d_support_mismatch, bool)
        and d_support_mismatch >= 0
        and calibration_result.get("production_B_path_consistency_only") is True
        and calibration_result.get("production_D_path_consistency_only") is True
    )
    api_witness = calibration_result.get("generated_action_api_witness")
    api_status = (
        api_witness.get("status") if isinstance(api_witness, Mapping) else None
    )
    failed_checks = []
    if b_relative is None or b_relative > relative_limit:
        failed_checks.append("native_production_B_relative")
    if d_relative is None or d_relative > relative_limit:
        failed_checks.append("native_production_D_relative")
    if (
        d_vector_relative is None
        or not 0.0 <= d_vector_relative <= relative_limit
    ):
        failed_checks.append("native_production_D_vector_relative")
    if (
        not isinstance(b_domain, str)
        or not b_domain
        or not isinstance(d_domain, str)
        or not d_domain
        or not valid_production_support
    ):
        failed_checks.append("native_production_B_reference_domain")
    if api_status != "PASS_RAW_LOCAL_CALLBACK_TILES":
        failed_checks.append("generated_action_api_witness")
    if not failed_checks:
        return None
    return {
        "status": "FAILED_NATIVE_OPERATOR_GATE",
        "side": str(side),
        "mode_index": int(mode_index),
        "mode_key": list(mode_key),
        "production_B_relative": b_relative,
        "production_D_relative": d_relative,
        "production_D_vector_relative": d_vector_relative,
        "raw_B_interior_vs_filtered_relative": raw_scope_relative,
        "production_B_reference_domain": b_domain,
        "production_D_reference_domain": d_domain,
        "production_B_support_digest": (
            dict(b_support_digest) if isinstance(b_support_digest, Mapping) else None
        ),
        "production_B_support_mismatch_count": b_support_mismatch,
        "production_D_support_digest": (
            dict(d_support_digest) if isinstance(d_support_digest, Mapping) else None
        ),
        "production_D_support_mismatch_count": d_support_mismatch,
        "generated_action_api_status": api_status,
        "relative_limit": float(relative_limit),
        "failed_checks": failed_checks,
    }


def _exercise_saved_packet_generated_action(
    root: str | Path,
    *,
    space: Any | None = None,
    dof_index_map: Any | None = None,
    mpc: Any | None = None,
    mapping_rows: Sequence[Mapping[str, Any]] | None = None,
    permutation_info: Any | None = None,
    polynomial: Any | None = None,
    cfg: Any | None = None,
    modes: Sequence[Any] | None = None,
    mode_normalizations: Any | None = None,
    quadrature_degree: int | None = None,
    cell_global_dofs_by_side: Mapping[str, Any] | None = None,
    mpc_expansions: Mapping[int, tuple[Any, Any]] | None = None,
) -> dict[str, Any]:
    """Run real saved-cell packets through the generated factory and V17 q consumer.

    The local action uses two hash-bound V20 cell tensors and two independent
    modal B/D witnesses. The optional live FE arguments bind those witnesses
    to this probe's actual mode table, p6 cell dofmaps, and finalized MPC.
    Only a 2-by-2 q projection is assembled; target q CSR is never created.
    """

    from mpi4py import MPI
    from petsc4py import PETSc
    from scipy import sparse
    from scipy.linalg import lu_solve

    from src.solvers.hcurl_assembly_time_condensation import CellRecoveryMap
    from src.solvers.original_port_blocks import DiagonalOriginalPortBlock
    from src.solvers.p6_cell_condensed_action import (
        P6CellCondensedAction,
        P6CellPortTerms,
        P6DirectTracePortTerms,
        P6GeneratedCellPortAction,
        build_p6_cell_condensed_action_from_generated,
        condense_physical_cell_blocks,
    )
    from src.solvers.retained_port_block_layout import RESEARCH_PORT_LAYOUT
    from src.solvers.task40_v10_p6_yorbit import _assemble_bounded_v17_row_tile_q_patterns

    packet_run = Path(
        "results/task40extra_nonseparable_0p7nm/"
        "task40extra_0p7nm_target_original_ny8_resource_pilot_v20__"
        "full3d_iterative__mpi1__Mna/20261009T175922.461391Z"
    )
    packet_records: dict[str, dict[str, Any]] = {}
    modes_by_side: dict[str, dict[str, Any]] = {}
    cell_rows_by_side: dict[str, np.ndarray] = {}
    raw_pair_factories: dict[str, Callable[[], tuple[np.ndarray, np.ndarray]]] = {}
    source_kind: dict[str, str] = {}
    cell_info_by_side: dict[str, Any] = {}

    def checked_array(archive: Any, metadata: Mapping[str, Any], name: str) -> np.ndarray:
        item = metadata.get(name)
        if not isinstance(item, Mapping):
            raise ValueError(f"saved local packet omits array descriptor {name}")
        key = item.get("array_key")
        if not isinstance(key, str) or key not in archive.files:
            raise ValueError(f"saved local packet array key is missing: {name}")
        value = np.asarray(archive[key])
        if list(value.shape) != item.get("shape") or str(value.dtype) != item.get("dtype"):
            raise ValueError(f"saved local packet array identity changed: {name}")
        return np.array(value, copy=True, order="C")

    for side in ("bottom", "top"):
        json_path = Path(root) / packet_run / f"v20_port_{side}.json"
        if not json_path.is_file():
            raise FileNotFoundError(f"saved {side} local physical packet is missing")
        packet = json.loads(json_path.read_text(encoding="utf-8"))
        array_file = packet.get("arrays")
        facts = packet.get("facts")
        raw_metadata = packet.get("raw_arrays")
        if not isinstance(array_file, Mapping) or not isinstance(facts, Mapping) or not isinstance(raw_metadata, Mapping):
            raise ValueError(f"saved {side} local packet has an incomplete schema")
        npz_path = Path(str(array_file.get("path", ""))).resolve()
        expected_npz = (Path(root) / packet_run / f"v20_port_{side}.npz").resolve()
        if npz_path != expected_npz or not npz_path.is_file():
            raise ValueError(f"saved {side} packet NPZ path differs from its registered artifact")
        packet_sha = _sha256_file(npz_path)
        if packet_sha != array_file.get("sha256"):
            raise ValueError(f"saved {side} packet NPZ hash differs from its JSON receipt")
        if (
            facts.get("side") != side
            or facts.get("degree") != 6
            or facts.get("full_local_rows") != 882
            or facts.get("internal_rows") != 450
            or facts.get("trace_rows") != 432
        ):
            raise ValueError(f"saved {side} packet no longer describes the actual p6 local cell")
        direct_facts = facts.get("small_key_native_carrier_witness")
        saved_b_relative = (
            direct_facts.get("full_dof_direct_B_relative")
            if isinstance(direct_facts, Mapping)
            else None
        )
        if saved_b_relative is None and isinstance(direct_facts, Mapping):
            saved_b_relative = direct_facts.get("full_dof_direct_q30_B_relative")
        saved_d_relative = (
            direct_facts.get("full_dof_direct_D_relative")
            if isinstance(direct_facts, Mapping)
            else None
        )
        if saved_d_relative is None and isinstance(direct_facts, Mapping):
            saved_d_relative = direct_facts.get("full_dof_direct_q30_D_relative")
        if (
            not isinstance(direct_facts, Mapping)
            or not isinstance(saved_b_relative, (int, float))
            or float(saved_b_relative) > 1e-10
            or not isinstance(saved_d_relative, (int, float))
            or float(saved_d_relative) > 1e-10
            or direct_facts.get("D_constructed_independently_from_B") is not True
        ):
            raise ValueError(f"saved {side} packet lacks an independent full-row B/D witness")
        with np.load(npz_path, allow_pickle=False) as archive:
            tensor = checked_array(archive, raw_metadata, "local_native_tensor")
            interior = checked_array(archive, raw_metadata, "interior_positions").astype(np.int64)
            trace = checked_array(archive, raw_metadata, "trace_positions").astype(np.int64)
            integrated = checked_array(
                archive, raw_metadata, "witness_direct_q30_integrated_basis"
            )
            saved_b = checked_array(archive, raw_metadata, "witness_direct_q30_B_native")
            saved_d = checked_array(archive, raw_metadata, "witness_direct_q30_D_native")
            mode_e = checked_array(archive, raw_metadata, "witness_mode_e")
            mode_k = checked_array(archive, raw_metadata, "witness_mode_k")
            mode_traction = checked_array(archive, raw_metadata, "witness_mode_traction")
            h_value = float(checked_array(
                archive, raw_metadata, "witness_mode_projection_denominator"
            ).reshape(()))
            local_orientation = checked_array(
                archive, raw_metadata, "local_cell_orientation"
            ).reshape(-1)
        if (
            tensor.shape != (882, 882)
            or tensor.dtype != np.dtype(np.complex128)
            or interior.shape != (450,)
            or trace.shape != (432,)
            or not np.array_equal(np.sort(np.r_[interior, trace]), np.arange(882))
            or integrated.shape != (882, 2)
            or saved_b.shape != (882,)
            or saved_d.shape != (882,)
            or mode_e.shape != (2,)
            or mode_k.shape != (3,)
            or mode_traction.shape != (2,)
            or not np.isfinite(tensor).all()
            or not np.isfinite(h_value)
            or h_value == 0.0
        ):
            raise ValueError(f"saved {side} packet has invalid local dimensions or nonfinite values")
        key = direct_facts.get("key")
        mode_index = direct_facts.get("ordered_key_index")
        if (
            not isinstance(key, list)
            or len(key) != 4
            or key[0] != side
            or not isinstance(mode_index, int)
            or mode_index < 0
        ):
            raise ValueError(f"saved {side} packet mode identity is incomplete")
        z_face = float(
            facts["actual_boundary_bounds_nm"][2][0 if side == "bottom" else 1]
        )
        global_z_phase = complex(np.exp(1j * mode_k[2] * z_face))
        saved_b_plane, saved_d_plane_raw, saved_boundary_h = (
            _saved_global_packet_to_boundary_plane(
                saved_b, saved_d, h_value, global_z_phase
            )
        )
        mode_identity = {
            "mode_index": mode_index,
            "mode_key": (side, int(key[1]), int(key[2]), str(key[3])),
            "cell_id": int(facts["actual_boundary_cell"]),
            "e": mode_e,
            "k": mode_k,
            "traction": mode_traction,
            "H_p": saved_boundary_h,
            "H_p_gauge": "boundary_plane",
            "H_p_global_z": h_value,
            "H_p_boundary_plane_from_packet": saved_boundary_h,
            "global_z_phase": global_z_phase,
            "npz_sha256": packet_sha,
        }
        modes_by_side[side] = mode_identity

        if modes is not None:
            if mode_index >= len(modes):
                raise ValueError(f"saved {side} witness mode index exceeds current frozen table")
            mode = modes[mode_index]
            current_key = (
                str(mode.side), int(mode.m), int(mode.n), str(mode.polarization)
            )
            if current_key != mode_identity["mode_key"]:
                raise ValueError(f"saved {side} witness mode differs from the current ordered mode table")
            if not np.allclose(np.asarray(mode.e_vector[:2]), mode_e, rtol=0.0, atol=1e-14):
                raise ValueError(f"saved {side} electric polarization differs from the current mode")
            if not np.allclose(np.asarray(mode.k_vector), mode_k, rtol=0.0, atol=1e-14):
                raise ValueError(f"saved {side} wavevector differs from the current mode")
            if cfg is not None:
                from src.solvers.dtn_port_3d import _traction_vector

                current_traction = np.asarray(_traction_vector(mode, cfg)[:2])
                if not np.allclose(current_traction, mode_traction, rtol=0.0, atol=1e-13):
                    raise ValueError(f"saved {side} traction differs from the current production mode")
            if mode_normalizations is not None:
                current_boundary_h = float(mode_normalizations[mode_index])
                if abs(saved_boundary_h - current_boundary_h) > 1e-12 * max(
                    abs(saved_boundary_h), abs(current_boundary_h), 1.0
                ):
                    raise ValueError(
                        f"saved {side} global-z H_p converts to boundary-plane "
                        "H_p different from the current production normalization "
                        f"(saved_global={h_value:.17g}, "
                        f"saved_boundary={saved_boundary_h:.17g}, "
                        f"current_boundary={current_boundary_h:.17g})"
                    )

        cell_id = int(facts["actual_boundary_cell"])
        cell_info_by_side[side] = local_orientation
        if space is not None:
            if dof_index_map is None or permutation_info is None or polynomial is None or cfg is None or quadrature_degree is None:
                raise ValueError("live FE packet binding requires its p6 element, map, permutation, gauge, and rule")
            current_info = int(np.asarray(permutation_info)[cell_id])
            if local_orientation.size != 1 or int(local_orientation[0]) != current_info:
                raise ValueError(f"saved {side} packet cell permutation differs from live FE dofmap")
            cell_dofs = np.asarray(space.dofmap.cell_dofs(cell_id), dtype=np.int32)
            if len(cell_dofs) != 882:
                raise ValueError(f"live {side} p6 cell has a different local dof dimension")
            global_dofs = np.asarray(
                dof_index_map.local_to_global(cell_dofs), dtype=np.int64
            )
            cell_global_dofs_by_side = dict(cell_global_dofs_by_side or {})
            cell_global_dofs_by_side[side] = global_dofs
            saved_bounds = np.asarray(facts["actual_boundary_bounds_nm"], dtype=np.float64)
            mapped = [
                row for row in (mapping_rows or ())
                if str(row.get("side")) == side
                and int(row.get("cell_id", -1)) == cell_id
                and np.array_equal(np.asarray(row.get("cell_bounds_nm")), saved_bounds)
            ]
            if not mapped:
                raise ValueError(f"saved {side} local packet cell is not present in the verified boundary map")
            mode_identity["class_id"] = str(mapped[0]["class_id"])
            bounds = mapped[0]["cell_bounds_nm"]
            cell_info = np.asarray(permutation_info)[cell_id]
            raw_pair_factories[side] = lambda mode=mode, side=side, bounds=bounds, cell_info=cell_info: _native_local_port_pair(
                polynomial=polynomial,
                space_element=space.element,
                mode=mode,
                side=side,
                bounds=bounds,
                cell_info=cell_info,
                cfg=cfg,
                quadrature_degree=quadrature_degree,
            )
            source_kind[side] = "live V22 boundary-plane raw B/D integral on the hash-bound saved cell"
        else:
            def saved_pair(
                b=saved_b_plane,
                d=saved_d_plane_raw,
            ) -> tuple[np.ndarray, np.ndarray]:
                return b.copy(), d.copy()
            raw_pair_factories[side] = saved_pair
            source_kind[side] = "boundary-plane conversion of the saved degree-60 full-row packet witness"

        probe_b, probe_d = raw_pair_factories[side]()
        probe_b = np.ascontiguousarray(probe_b, dtype=np.complex128)
        probe_d = np.ascontiguousarray(probe_d, dtype=np.complex128)
        if probe_b.shape != (882,) or probe_d.shape != (882,) or not np.isfinite(probe_b).all() or not np.isfinite(probe_d).all():
            raise ValueError(f"generated {side} raw local B/D action has invalid rows")
        b_error = float(np.linalg.norm(probe_b - saved_b_plane) / max(np.linalg.norm(probe_b), np.linalg.norm(saved_b_plane), np.finfo(float).tiny))
        d_error = float(np.linalg.norm(probe_d - saved_d_plane_raw) / max(np.linalg.norm(probe_d), np.linalg.norm(saved_d_plane_raw), np.finfo(float).tiny))
        if b_error > 1e-10 or d_error > 1e-10:
            raise ValueError(f"generated {side} B/D differs from saved raw packet after gauge/H_p conversion")
        packet_records[side] = {
            "facts": facts,
            "tensor": tensor,
            "interior_positions": interior,
            "trace_positions": trace,
            "saved_b_plane": saved_b_plane,
            "saved_d_plane_raw": saved_d_plane_raw,
            "integrated_basis_global": np.ascontiguousarray(integrated, dtype=np.complex128),
            "global_z_phase": global_z_phase,
            "b_relative_to_packet": b_error,
            "d_relative_to_packet": d_error,
        }

    if cell_global_dofs_by_side is None:
        cell_global_dofs_by_side = {
            "bottom": np.arange(882, dtype=np.int64),
            "top": np.arange(882, 1764, dtype=np.int64),
        }
    physical_globals: set[int] = set()
    trace_globals: set[int] = set()
    raw_cell_globals: dict[str, np.ndarray] = {}
    for side in ("bottom", "top"):
        rows = np.asarray(cell_global_dofs_by_side[side], dtype=np.int64).reshape(-1)
        record = packet_records[side]
        if rows.shape != (882,) or len(np.unique(rows)) != 882:
            raise ValueError(f"{side} packet cell global dofmap is not a unique 882-row map")
        raw_cell_globals[side] = rows
        physical_globals.update(map(int, rows))
        trace_globals.update(map(int, rows[record["trace_positions"]]))
    if mpc is not None:
        if dof_index_map is None:
            raise ValueError("actual MPC expansion requires its FE dof index map")
        mpc_expansions = _global_mpc_expansions(
            mpc, dof_index_map, sorted(trace_globals)
        )
    local_mpc_rows = trace_globals.intersection(mpc_expansions or {})
    normalized_mpc: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for slave in local_mpc_rows:
        pair = (mpc_expansions or {})[slave]
        masters = np.asarray(pair[0], dtype=np.int64).reshape(-1)
        coefficients = np.asarray(pair[1], dtype=np.complex128).reshape(-1)
        if (
            not len(masters)
            or len(masters) != len(coefficients)
            or not np.isfinite(coefficients).all()
        ):
            raise ValueError("local generated action MPC expansion is malformed")
        normalized_mpc[int(slave)] = (masters, coefficients)
    slave_globals = set(normalized_mpc)
    if any(int(master) in slave_globals for masters, _values in normalized_mpc.values() for master in masters):
        raise NotImplementedError("local packet action does not admit chained MPC masters")
    trace_closure = set(trace_globals)
    for slave in tuple(trace_globals & slave_globals):
        trace_closure.update(map(int, normalized_mpc[slave][0]))
    if trace_closure & set().union(
        *(set(map(int, raw_cell_globals[side][packet_records[side]["interior_positions"]])) for side in ("bottom", "top"))
    ):
        raise ValueError("a boundary MPC master aliases a local cell-interior row")
    active_globals = sorted(trace_closure - slave_globals)
    if not active_globals or any(
        int(master) not in set(active_globals)
        for slave in trace_closure & slave_globals
        for master in normalized_mpc[slave][0]
    ):
        raise ValueError("local trace MPC closure has no independent master coordinates")
    all_globals = sorted(physical_globals | set(active_globals))
    compact = {global_row: index for index, global_row in enumerate(all_globals)}
    active_index = {global_row: index for index, global_row in enumerate(active_globals)}
    expansion_by_original: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for global_row in sorted(trace_closure):
        if global_row in normalized_mpc:
            masters, coefficients = normalized_mpc[global_row]
            ids = np.asarray([active_index[int(master)] for master in masters], dtype=PETSc.IntType)
            values = np.ascontiguousarray(coefficients, dtype=np.complex128)
        else:
            ids = np.asarray([active_index[global_row]], dtype=PETSc.IntType)
            values = np.asarray([1.0 + 0.0j], dtype=np.complex128)
        expansion_by_original[compact[global_row]] = (ids, values)
    original_to_active = {
        compact[global_row]: index for index, global_row in enumerate(active_globals)
    }
    trace_constraint = SimpleNamespace(
        owned_active_original_dofs=np.asarray(
            [compact[row] for row in active_globals], dtype=PETSc.IntType
        ),
        original_to_active=original_to_active,
        expansion_by_original=expansion_by_original,
        full_trace_rows=len(trace_closure),
        active_rows=len(active_globals),
        slave_rows=len(trace_closure & slave_globals),
        build_audit={"scope": "two saved local boundary cells; actual MPC rows when live probe objects are supplied"},
    )
    if trace_constraint.active_rows + trace_constraint.slave_rows != trace_constraint.full_trace_rows:
        raise ValueError("local trace constraint inventory does not close active and slave rows")

    mode_specs_by_side: dict[str, list[dict[str, Any]]] = {}
    crossmode_facts_by_side: dict[str, dict[str, Any]] = {}
    for side in ("bottom", "top"):
        record = packet_records[side]
        if modes is None:
            mode_specs_by_side[side] = [{
                "mode_index": None,
                "mode_key": modes_by_side[side]["mode_key"],
                "H_p": _saved_packet_action_h(modes_by_side[side]),
                "factory": raw_pair_factories[side],
                "cached_pair": (
                    record["saved_b_plane"], record["saved_d_plane_raw"]
                ),
            }]
            crossmode_facts_by_side[side] = {
                "status": "NOT_TESTED_WITHOUT_FROZEN_MODE_TABLE",
                "same_cell_s_p_offdiagonal": "NOT_RUN",
            }
            continue
        if space is None or cfg is None:
            raise ValueError("actual same-cell s/p witness requires the live p6 element and physical configuration")
        base_index = int(modes_by_side[side]["mode_index"])
        base_mode = modes[base_index]
        partners = [
            (index, mode)
            for index, mode in enumerate(modes)
            if str(mode.side) == side
            and int(mode.m) == int(base_mode.m)
            and int(mode.n) == int(base_mode.n)
            and str(mode.polarization) != str(base_mode.polarization)
        ]
        if len(partners) != 1:
            raise ValueError(f"frozen {side} mode table does not contain one same-order s/p partner")
        partner_index, partner_mode = partners[0]
        if {str(base_mode.polarization), str(partner_mode.polarization)} != {"s", "p"}:
            raise ValueError("same-cell mode coupling witness requires the actual s/p pair")
        if not np.allclose(
            np.asarray(base_mode.k_vector),
            np.asarray(partner_mode.k_vector),
            rtol=0.0,
            atol=1e-14,
        ):
            raise ValueError("saved s/p packet pair has different wavevectors")
        if mode_normalizations is None:
            raise ValueError("actual same-cell s/p witness requires frozen per-mode H_p values")
        basis = np.ascontiguousarray(
            record["integrated_basis_global"] / record["global_z_phase"],
            dtype=np.complex128,
        )
        cell_transform = np.asarray(
            [int(np.asarray(cell_info_by_side[side]).reshape(-1)[0])],
            dtype=np.uint32,
        )
        basis = _transform_mode_basis_columns(
            space.element, basis, cell_transform
        )
        from src.solvers.dtn_port_3d import _traction_vector

        def table_pair(mode: Any, basis: np.ndarray = basis) -> tuple[np.ndarray, np.ndarray]:
            raw_b = np.ascontiguousarray(
                basis @ (-np.asarray(_traction_vector(mode, cfg)[:2], dtype=np.complex128)),
                dtype=np.complex128,
            )
            raw_d = np.ascontiguousarray(
                np.conjugate(basis @ np.asarray(mode.e_vector[:2], dtype=np.complex128)),
                dtype=np.complex128,
            )
            return raw_b, raw_d

        actual_modes = [(base_index, base_mode), (int(partner_index), partner_mode)]
        side_specs: list[dict[str, Any]] = []
        table_b_error = table_d_error = None
        for mode_index, mode in actual_modes:
            pair = table_pair(mode)
            if mode_index == base_index:
                table_b_error = float(
                    np.linalg.norm(pair[0] - record["saved_b_plane"])
                    / max(np.linalg.norm(pair[0]), np.linalg.norm(record["saved_b_plane"]), np.finfo(float).tiny)
                )
                table_d_error = float(
                    np.linalg.norm(pair[1] - record["saved_d_plane_raw"])
                    / max(np.linalg.norm(pair[1]), np.linalg.norm(record["saved_d_plane_raw"]), np.finfo(float).tiny)
                )
                if table_b_error > 1e-10 or table_d_error > 1e-10:
                    raise ValueError("saved 882x2 basis does not reproduce the s-mode B/D packet")
            side_specs.append({
                "mode_index": int(mode_index),
                "mode_key": (
                    str(mode.side), int(mode.m), int(mode.n), str(mode.polarization)
                ),
                "H_p": float(mode_normalizations[mode_index]),
                "factory": lambda mode=mode, table_pair=table_pair: table_pair(mode),
                "cached_pair": pair,
            })
        mode_specs_by_side[side] = side_specs
        crossmode_facts_by_side[side] = {
            "status": "MEASURED_ACTUAL_SAME_WAVEVECTOR_S_P_PAIR",
            "mode_indices": [int(base_index), int(partner_index)],
            "mode_keys": [list(spec["mode_key"]) for spec in side_specs],
            "same_wavevector": True,
            "shared_saved_integrated_basis_shape": list(basis.shape),
            "saved_integrated_basis_quadrature_degree": int(record["facts"]["boundary_quadrature_degree"]),
            "new_mode_surface_integral_for_partner": False,
            "s_packet_table_B_relative": table_b_error,
            "s_packet_table_D_relative": table_d_error,
        }

    zero_key: dict[tuple[Any, ...], Any] = {}
    cell_maps = []
    interior_from_trace: dict[tuple[Any, ...], np.ndarray] = {}
    local_factors: dict[tuple[Any, ...], Any] = {}
    trace_from_interior: dict[tuple[Any, ...], np.ndarray] = {}
    retained_schur: dict[tuple[Any, ...], np.ndarray] = {}
    local_blocks: dict[str, dict[str, Any]] = {}
    generated_terms: dict[int, P6GeneratedCellPortAction] = {}
    cached_terms: dict[int, P6CellPortTerms] = {}
    cached_direct_trace_terms: list[P6DirectTracePortTerms] = []
    normalizations: list[float] = []
    mode_keys: list[tuple[Any, ...]] = []
    reduced_cell_traces: dict[str, int] = {}
    for cell_number, side in enumerate(("bottom", "top")):
        record = packet_records[side]
        tensor = record["tensor"]
        interior = record["interior_positions"]
        trace = record["trace_positions"]
        vi_i = np.asarray(tensor[np.ix_(interior, interior)], dtype=np.complex128)
        vi_t = np.asarray(tensor[np.ix_(interior, trace)], dtype=np.complex128)
        vt_i = np.asarray(tensor[np.ix_(trace, interior)], dtype=np.complex128)
        vt_t = np.asarray(tensor[np.ix_(trace, trace)], dtype=np.complex128)
        side_specs = mode_specs_by_side[side]
        bi = np.ascontiguousarray(
            np.column_stack([spec["cached_pair"][0][interior] for spec in side_specs]),
            dtype=np.complex128,
        )
        bt = np.ascontiguousarray(
            np.column_stack([spec["cached_pair"][0][trace] for spec in side_specs]),
            dtype=np.complex128,
        )
        di = np.ascontiguousarray(
            np.vstack([spec["cached_pair"][1][interior] for spec in side_specs]),
            dtype=np.complex128,
        )
        dt = np.ascontiguousarray(
            np.vstack([spec["cached_pair"][1][trace] for spec in side_specs]),
            dtype=np.complex128,
        )
        condensed_cell = condense_physical_cell_blocks(
            vi_i,
            vi_t,
            vt_i,
            vt_t,
            np.zeros((len(interior), len(side_specs)), dtype=np.complex128),
            np.zeros((len(trace), len(side_specs)), dtype=np.complex128),
            np.zeros((len(side_specs), len(interior)), dtype=np.complex128),
            np.zeros((len(side_specs), len(trace)), dtype=np.complex128),
            np.zeros((len(side_specs), len(side_specs)), dtype=np.complex128),
        )
        class_key = ("saved-v20-local-packet", side, modes_by_side[side]["npz_sha256"])
        local_factors[class_key] = condensed_cell.interior_lu
        interior_from_trace[class_key] = np.ascontiguousarray(-condensed_cell.Xit)
        trace_from_interior[class_key] = condensed_cell.trace_from_interior
        retained_schur[class_key] = condensed_cell.S_V
        cell_dofs = np.asarray(
            [compact[int(row)] for row in raw_cell_globals[side]], dtype=PETSc.IntType
        )
        cell_maps.append(
            CellRecoveryMap(
                interior_original_dofs=np.ascontiguousarray(cell_dofs[interior]),
                trace_original_dofs=np.ascontiguousarray(cell_dofs[trace]),
                class_key=class_key,
            )
        )
        port_start = len(normalizations)
        ports = np.arange(
            port_start, port_start + len(side_specs), dtype=PETSc.IntType
        )
        factories = tuple(spec["factory"] for spec in side_specs)

        def generated_b(alpha: Any, factories=factories, interior=interior, trace=trace):
            amplitudes = np.asarray(alpha, dtype=np.complex128).reshape(-1)
            if amplitudes.shape != (len(factories),):
                raise ValueError("local generated B action received an invalid mode vector")
            bi_value = np.zeros(len(interior), dtype=np.complex128)
            bt_value = np.zeros(len(trace), dtype=np.complex128)
            for coefficient, factory in zip(amplitudes, factories, strict=True):
                if coefficient == 0.0:
                    continue
                raw_b_value, _raw_d_value = factory()
                bi_value += raw_b_value[interior] * coefficient
                bt_value += raw_b_value[trace] * coefficient
            return np.ascontiguousarray(bi_value), np.ascontiguousarray(bt_value)

        def generated_d(xi: Any, xt: Any, factories=factories, interior=interior, trace=trace):
            interior_values = np.asarray(xi, dtype=np.complex128)
            trace_values = np.asarray(xt, dtype=np.complex128)
            result = np.empty(len(factories), dtype=np.complex128)
            for index, factory in enumerate(factories):
                _raw_b_value, raw_d_value = factory()
                result[index] = (
                    raw_d_value[interior] @ interior_values
                    + raw_d_value[trace] @ trace_values
                )
            return np.ascontiguousarray(result)

        def generated_b_tile(
            selected_ports: Any,
            amplitude_tile: Any,
            factories=factories,
            ports=ports,
            interior=interior,
            trace=trace,
        ):
            selected = np.asarray(selected_ports, dtype=np.int64).reshape(-1)
            amplitudes = np.asarray(amplitude_tile, dtype=np.complex128)
            positions = np.searchsorted(ports, selected)
            if (
                amplitudes.ndim != 2
                or amplitudes.shape[0] != len(selected)
                or np.any(positions >= len(ports))
                or not np.array_equal(ports[positions], selected)
            ):
                raise ValueError("local generated B tile changed its bounded port identity")
            bi_tile = np.zeros((len(interior), amplitudes.shape[1]), dtype=np.complex128)
            bt_tile = np.zeros((len(trace), amplitudes.shape[1]), dtype=np.complex128)
            for tile_row, position in enumerate(positions):
                raw_b_value, _raw_d_value = factories[int(position)]()
                bi_tile += raw_b_value[interior, None] * amplitudes[tile_row : tile_row + 1, :]
                bt_tile += raw_b_value[trace, None] * amplitudes[tile_row : tile_row + 1, :]
            return np.ascontiguousarray(bi_tile), np.ascontiguousarray(bt_tile)

        def generated_d_tile(
            selected_ports: Any,
            xi: Any,
            xt: Any,
            factories=factories,
            ports=ports,
            interior=interior,
            trace=trace,
        ):
            selected = np.asarray(selected_ports, dtype=np.int64).reshape(-1)
            interior_values = np.asarray(xi, dtype=np.complex128)
            trace_values = np.asarray(xt, dtype=np.complex128)
            positions = np.searchsorted(ports, selected)
            if (
                np.any(positions >= len(ports))
                or not np.array_equal(ports[positions], selected)
                or interior_values.ndim != 2
                or trace_values.ndim != 2
            ):
                raise ValueError("local generated D tile changed its bounded port identity")
            result = np.empty((len(selected), interior_values.shape[1]), dtype=np.complex128)
            for tile_row, position in enumerate(positions):
                _raw_b_value, raw_d_value = factories[int(position)]()
                result[tile_row] = (
                    raw_d_value[interior] @ interior_values
                    + raw_d_value[trace] @ trace_values
                )
            return np.ascontiguousarray(result)

        generated_terms[cell_number] = P6GeneratedCellPortAction(
            port_indices=ports,
            apply_B=generated_b,
            apply_D=generated_d,
            callback_workspace_bytes=2 * 882 * np.dtype(np.complex128).itemsize,
            apply_B_tile=generated_b_tile,
            apply_D_tile=generated_d_tile,
        )
        cached_terms[cell_number] = P6CellPortTerms(bi, di, ports)
        active_compact_rows = np.asarray(
            trace_constraint.owned_active_original_dofs, dtype=PETSc.IntType
        )
        for mode_position, port in enumerate(ports):
            direct_b: dict[int, complex] = {}
            direct_d: dict[int, complex] = {}
            for trace_position, global_row in enumerate(raw_cell_globals[side][trace]):
                original = compact[int(global_row)]
                active_ids, coefficients = expansion_by_original[original]
                for active_id, coefficient in zip(active_ids, coefficients, strict=True):
                    active_original = int(active_compact_rows[int(active_id)])
                    direct_b[active_original] = direct_b.get(active_original, 0.0 + 0.0j) + np.conjugate(coefficient) * bt[trace_position, mode_position]
                    direct_d[active_original] = direct_d.get(active_original, 0.0 + 0.0j) + coefficient * dt[mode_position, trace_position]
            b_rows = np.asarray(sorted(direct_b), dtype=PETSc.IntType)
            d_rows = np.asarray(sorted(direct_d), dtype=PETSc.IntType)
            cached_direct_trace_terms.append(
                P6DirectTracePortTerms(
                    port_index=int(port),
                    B_original_rows=b_rows,
                    B_values=np.ascontiguousarray(
                        [direct_b[int(row)] for row in b_rows], dtype=np.complex128
                    ),
                    D_original_rows=d_rows,
                    D_values=np.ascontiguousarray(
                        [direct_d[int(row)] for row in d_rows], dtype=np.complex128
                    ),
                )
            )
        normalizations.extend(float(spec["H_p"]) for spec in side_specs)
        mode_keys.extend(
            (int(port), *spec["mode_key"])
            for port, spec in zip(ports, side_specs, strict=True)
        )
        trace_score = np.linalg.norm(bt, axis=1) + np.linalg.norm(dt, axis=0)
        side_active = [
            (float(trace_score[index]), active_index[int(global_row)])
            for index, global_row in enumerate(raw_cell_globals[side][trace])
            if int(global_row) in active_index
        ]
        if not side_active:
            raise ValueError(f"saved {side} cell has no independent trace rows for q projection")
        reduced_cell_traces[side] = max(side_active)[1]
        local_blocks[side] = {
            "tensor": tensor,
            "cell_dofs": cell_dofs,
            "bi": bi,
            "bt": bt,
            "di": di,
            "dt": dt,
            "factor": condensed_cell.interior_lu,
            "ports": ports,
            "b_error_to_packet": record["b_relative_to_packet"],
            "d_error_to_packet": record["d_relative_to_packet"],
            "source_kind": source_kind[side],
            "mode_specs": side_specs,
        }

    full_rows = len(all_globals)
    active_rows = len(active_globals)
    trace_rows_count = len(trace_closure)
    condensed = SimpleNamespace(
        matrix=None,
        owned_trace_original_dofs=np.asarray(
            [compact[row] for row in sorted(trace_closure)], dtype=PETSc.IntType
        ),
        original_to_trace={
            compact[row]: index for index, row in enumerate(sorted(trace_closure))
        },
        trace_constraints=trace_constraint,
        cell_recovery_maps=tuple(cell_maps),
        interior_from_trace_by_class=interior_from_trace,
        interior_lu_by_class=local_factors,
        interior_rhs_projection_by_class={},
        interior_solution_embedding_by_class={},
        trace_from_interior_rhs_by_class=trace_from_interior,
        interior_residual_projection_by_class={},
        full_rows=full_rows,
        trace_rows=trace_rows_count,
        active_rows=active_rows,
        appended_rows=len(normalizations),
        interior_rows=900,
        active_interior_rows=900,
        build_audit={},
        comm=MPI.COMM_SELF,
        owned_active_rows=active_rows,
        owned_appended_rows=len(normalizations),
        retained_local_schur_by_class=retained_schur,
    )
    hp = DiagonalOriginalPortBlock(
        np.asarray(normalizations, dtype=np.complex128), mode_keys
    )
    cached = P6CellCondensedAction(
        condensed,
        H_p=None,
        port_terms=cached_terms,
        direct_trace_terms=cached_direct_trace_terms,
        original_port_block=hp,
        port_block_layout=RESEARCH_PORT_LAYOUT,
    )
    generated = build_p6_cell_condensed_action_from_generated(
        condensed, hp, generated_terms
    )
    try:
        rng = np.random.default_rng(20261010)
        reduced_solution = np.ascontiguousarray(
            rng.standard_normal(generated.reduced_size)
            + 1j * rng.standard_normal(generated.reduced_size),
            dtype=np.complex128,
        )
        raw_full_rhs = np.zeros(full_rows, dtype=np.complex128)
        physical_compact = np.asarray(
            [compact[row] for row in sorted(physical_globals)], dtype=PETSc.IntType
        )
        raw_full_rhs[physical_compact] = (
            rng.standard_normal(len(physical_compact))
            + 1j * rng.standard_normal(len(physical_compact))
        )
        full_rhs = raw_full_rhs.copy()
        dual_active_rhs = np.zeros(active_rows, dtype=np.complex128)
        for original in sorted(trace_closure):
            ids, coefficients = expansion_by_original[compact[original]]
            dual_active_rhs[ids] += np.conjugate(coefficients) * raw_full_rhs[
                compact[original]
            ]
            full_rhs[compact[original]] = 0.0
        for original, active_id in original_to_active.items():
            full_rhs[original] = dual_active_rhs[active_id]
        raw_rhs_reduced = generated.reduce_rhs(
            raw_full_rhs, port_rhs=None, rhs_is_mpc_dual=False
        )
        dual_rhs_reduced = generated.reduce_rhs(
            full_rhs, port_rhs=None, rhs_is_mpc_dual=True
        )
        raw_rhs_dual_error = float(
            np.linalg.norm(raw_rhs_reduced - dual_rhs_reduced)
            / max(np.linalg.norm(raw_rhs_reduced), np.linalg.norm(dual_rhs_reduced), np.finfo(float).tiny)
        )
        if raw_rhs_dual_error > 1e-12:
            raise ValueError("raw-to-dual RHS conversion changed the local MPC pullback")
        port_rhs = np.ascontiguousarray(
            rng.standard_normal(len(normalizations))
            + 1j * rng.standard_normal(len(normalizations)),
            dtype=np.complex128,
        )

        def native_apply(field: np.ndarray) -> np.ndarray:
            result = np.zeros(full_rows, dtype=np.complex128)
            for side in ("bottom", "top"):
                cell = local_blocks[side]
                trace_positions = packet_records[side]["trace_positions"]
                interior_positions = packet_records[side]["interior_positions"]
                local_field = np.ascontiguousarray(
                    field[cell["cell_dofs"]], dtype=np.complex128
                )
                for local_trace_position, global_row in zip(
                    trace_positions, raw_cell_globals[side][trace_positions], strict=True
                ):
                    local_original = compact[int(global_row)]
                    active_ids, coefficients = expansion_by_original[local_original]
                    active_values = field[
                        np.asarray(
                            trace_constraint.owned_active_original_dofs,
                            dtype=PETSc.IntType,
                        )[active_ids]
                    ]
                    local_field[int(local_trace_position)] = np.dot(
                        coefficients, active_values
                    )
                local_output = cell["tensor"] @ local_field
                result[cell["cell_dofs"][interior_positions]] += local_output[
                    interior_positions
                ]
                for local_trace_position, global_row in zip(
                    trace_positions, raw_cell_globals[side][trace_positions], strict=True
                ):
                    local_original = compact[int(global_row)]
                    active_ids, coefficients = expansion_by_original[local_original]
                    active_originals = np.asarray(
                        trace_constraint.owned_active_original_dofs,
                        dtype=PETSc.IntType,
                    )[active_ids]
                    result[active_originals] += (
                        np.conjugate(coefficients) * local_output[int(local_trace_position)]
                    )
            port_action = generated.apply_D_full(field)
            effective_port = generated.original_hp_solve(port_action)
            result += generated.apply_B_full(effective_port)
            return np.ascontiguousarray(result)

        generated_native = generated.evaluate_native_residual(
            reduced_solution, full_rhs, native_apply, port_rhs=port_rhs,
            rhs_is_mpc_dual=True,
        )
        cached_native = cached.evaluate_native_residual(
            reduced_solution, full_rhs, native_apply, port_rhs=port_rhs,
            rhs_is_mpc_dual=True,
        )
        if (
            generated_native["native_identity_relative"] > 1e-10
            or generated_native["schur_port_identity_relative"] > 1e-10
            or not np.allclose(
                generated_native["native_residual"],
                cached_native["native_residual"],
                rtol=2e-11,
                atol=2e-12,
            )
        ):
            raise ValueError(
                "generated local packet native residual did not match its cached oracle: "
                f"native={generated_native['native_identity_relative']:.6g}, "
                f"schur_port={generated_native['schur_port_identity_relative']:.6g}, "
                f"cached_max={float(np.max(np.abs(generated_native['native_residual'] - cached_native['native_residual']), initial=0.0)):.6g}"
            )
        def collect_reduced_contributions(action: Any):
            entries: dict[tuple[int, int], complex] = {}
            labels: list[str] = []
            hhat_block = np.zeros(
                (generated.condensed.appended_rows, generated.condensed.appended_rows),
                dtype=np.complex128,
            )
            for rows, columns, values, label in action.iter_reduced_contributions(
                allocation_gate=lambda *_args: None, hhat_block_columns=1
            ):
                row_ids = np.asarray(rows, dtype=np.int64).reshape(-1)
                column_ids = np.asarray(columns, dtype=np.int64).reshape(-1)
                matrix = np.asarray(values, dtype=np.complex128)
                if matrix.shape != (len(row_ids), len(column_ids)):
                    raise ValueError(f"local reduced contribution {label} has inconsistent dimensions")
                for row_index, row_id in enumerate(row_ids):
                    for column_index, column_id in enumerate(column_ids):
                        value = complex(matrix[row_index, column_index])
                        if value != 0.0:
                            key = (int(row_id), int(column_id))
                            entries[key] = entries.get(key, 0.0 + 0.0j) + value
                labels.append(str(label))
                if str(label).startswith("ports/Hhat/"):
                    start, stop = map(int, str(label).rsplit("/", 1)[1].split(":"))
                    hhat_block[:, start:stop] += matrix
            return entries, labels, hhat_block

        generated_entries, labels, hhat = collect_reduced_contributions(generated)
        cached_entries, cached_labels, cached_hhat = collect_reduced_contributions(cached)
        contribution_keys = set(generated_entries) | set(cached_entries)
        contribution_difference = np.asarray(
            [generated_entries.get(key, 0.0) - cached_entries.get(key, 0.0) for key in contribution_keys],
            dtype=np.complex128,
        )
        contribution_reference = np.asarray(
            [cached_entries.get(key, 0.0) for key in contribution_keys],
            dtype=np.complex128,
        )
        contribution_relative = float(
            np.linalg.norm(contribution_difference)
            / max(np.linalg.norm(contribution_reference), np.finfo(float).tiny)
        )
        contribution_max = float(np.max(np.abs(contribution_difference), initial=0.0))
        if contribution_relative > 1e-11:
            raise ValueError(
                "generated local reduced contributions differ from cached oracle: "
                f"relative_frobenius={contribution_relative:.6g}, max_abs={contribution_max:.6g}"
            )
        if not np.allclose(hhat, cached_hhat, rtol=1e-11, atol=1e-12):
            raise ValueError("generated Hhat block tiles differ from cached Hhat block")
        expected_hhat = np.diag(np.asarray(normalizations, dtype=np.complex128))
        hhat_corrections = []
        for side in ("bottom", "top"):
            cell = local_blocks[side]
            correction = cell["di"] @ lu_solve(cell["factor"], cell["bi"])
            expected_hhat[np.ix_(cell["ports"], cell["ports"])] += correction
            hhat_corrections.append({
                "side": side,
                "port_indices": [int(value) for value in cell["ports"]],
                "raw_D_solve_B_correction": [
                    [
                        {"real": float(value.real), "imag": float(value.imag)}
                        for value in row
                    ]
                    for row in correction
                ],
            })
        if not np.allclose(hhat, expected_hhat, rtol=2e-11, atol=1e-27):
            raise ValueError("bounded generated Hhat tiles omitted or changed the local D Vii^-1 B correction")
        if not any(label.startswith("cell/C_hat") for label in labels) or not any(
            label.startswith("cell/-D_hat") for label in labels
        ) or not any(label.startswith("ports/Hhat/") for label in labels):
            raise ValueError("generated contribution stream omitted C_hat, -D_hat, or bounded Hhat terms")

        trace_selector = sparse.csr_matrix(
            (
                np.ones(2, dtype=np.complex128),
                (
                    np.asarray([reduced_cell_traces["bottom"], reduced_cell_traces["top"]], dtype=PETSc.IntType),
                    np.asarray([0, 1], dtype=PETSc.IntType),
                ),
            ),
            shape=(generated.reduced_size, 2),
            dtype=np.complex128,
        )
        bottom_ports = local_blocks["bottom"]["ports"]
        if len(bottom_ports) >= 2:
            selected_ports = bottom_ports[:2]
        else:
            selected_ports = np.asarray(
                [bottom_ports[0], local_blocks["top"]["ports"][0]],
                dtype=PETSc.IntType,
            )
        port_selector = sparse.csr_matrix(
            (
                np.ones(2, dtype=np.complex128),
                (
                    np.asarray(active_rows + selected_ports, dtype=PETSc.IntType),
                    np.asarray([0, 1], dtype=PETSc.IntType),
                ),
            ),
            shape=(generated.reduced_size, 2),
            dtype=np.complex128,
        )
        q_maps = (trace_selector, port_selector)
        generated_q, generated_q_facts = _assemble_bounded_v17_row_tile_q_patterns(
            generated, q_maps, allocation_gate=lambda *_args: None
        )
        cached_q, cached_q_facts = _assemble_bounded_v17_row_tile_q_patterns(
            cached, q_maps, allocation_gate=lambda *_args: None
        )
        q_difference_max = 0.0
        q_difference_frobenius = 0.0
        q_reference_frobenius = 0.0
        q_block_facts: dict[str, dict[str, float | int]] = {}
        for key in ((0, 0), (0, 1), (1, 0), (1, 1)):
            difference = (generated_q[key] - cached_q[key]).tocsr()
            difference.eliminate_zeros()
            q_difference_max = max(
                q_difference_max,
                float(np.max(np.abs(difference.data), initial=0.0)),
            )
            q_difference_frobenius += float(np.linalg.norm(difference.data) ** 2)
            q_reference_frobenius += float(np.linalg.norm(cached_q[key].data) ** 2)
            q_block_facts[f"{key[0]}{key[1]}"] = {
                "generated_frobenius": float(np.linalg.norm(generated_q[key].data)),
                "cached_frobenius": float(np.linalg.norm(cached_q[key].data)),
                "generated_nnz": int(generated_q[key].nnz),
            }
        q_difference_frobenius = float(np.sqrt(q_difference_frobenius))
        q_reference_frobenius = float(np.sqrt(q_reference_frobenius))
        q_relative_frobenius = q_difference_frobenius / max(
            q_reference_frobenius, np.finfo(float).tiny
        )
        if q_relative_frobenius > 1e-11:
            raise ValueError("V17 row-tile consumer changed generated local q blocks vs cached oracle")
        if not all(
            q_block_facts[key]["generated_nnz"] > 0 for key in ("01", "10", "11")
        ):
            raise ValueError("local q selectors did not consume nonzero C_hat, -D_hat, and Hhat terms")
        crossmode_measured = (
            crossmode_facts_by_side["bottom"].get("status")
            == "MEASURED_ACTUAL_SAME_WAVEVECTOR_S_P_PAIR"
            and len(local_blocks["bottom"]["ports"]) == 2
        )
        q01_dense = generated_q[(0, 1)].toarray()
        q10_dense = generated_q[(1, 0)].toarray()
        q11_dense = generated_q[(1, 1)].toarray()
        crossmode_q11 = complex(q11_dense[0, 1])
        hhat_only_port_projection = np.ascontiguousarray(
            hhat[np.ix_(selected_ports, selected_ports)], dtype=np.complex128
        )
        same_cell_pair_in_port_projection = bool(
            crossmode_measured
            and np.array_equal(np.asarray(selected_ports), np.asarray(bottom_ports))
        )

        def complex_matrix_records(matrix: np.ndarray) -> list[list[dict[str, float]]]:
            return [
                [
                    {"real": float(value.real), "imag": float(value.imag)}
                    for value in row
                ]
                for row in np.asarray(matrix, dtype=np.complex128)
            ]
        return {
            "status": "PASS_GENERATED_FACTORY_AND_BOUNDED_Q_TILES",
            "P6CellCondensedAction_factory_connected": True,
            "row_tile_q_consumer_connected": True,
            "actual_local_packet_sides": ["bottom", "top"],
            "independent_saved_full_row_packet_reference": {
                "status": "PASS_HASH_BOUND_SAVED_DEGREE60_FULL_ROW_B_D_PACKETS",
                "quadrature_degree_by_side": {
                    side: int(packet_records[side]["facts"]["boundary_quadrature_degree"])
                    for side in ("bottom", "top")
                },
                "full_local_rows_by_side": {
                    side: int(packet_records[side]["facts"]["full_local_rows"])
                    for side in ("bottom", "top")
                },
                "independent_B_D_construction_by_side": {
                    side: packet_records[side]["facts"][
                        "small_key_native_carrier_witness"
                    ]["D_constructed_independently_from_B"]
                    for side in ("bottom", "top")
                },
                "B_relative_to_live_native_by_side": {
                    side: float(packet_records[side]["b_relative_to_packet"])
                    for side in ("bottom", "top")
                },
                "D_relative_to_live_native_by_side": {
                    side: float(packet_records[side]["d_relative_to_packet"])
                    for side in ("bottom", "top")
                },
                "mode_indices_by_side": {
                    side: int(modes_by_side[side]["mode_index"])
                    for side in ("bottom", "top")
                },
                "actual_cell_ids_by_side": {
                    side: int(modes_by_side[side]["cell_id"])
                    for side in ("bottom", "top")
                },
                "actual_class_ids_by_side": {
                    side: str(modes_by_side[side].get("class_id", "UNAVAILABLE"))
                    for side in ("bottom", "top")
                },
                "packet_npz_sha256_by_side": {
                    side: str(modes_by_side[side]["npz_sha256"])
                    for side in ("bottom", "top")
                },
                "qualification_scope": (
                    "two independent hash-bound 882-row degree-60 packets, one per side; "
                    "their frozen mode/cell/class identities are checked against actual p6/MPC geometry"
                ),
            },
            "mode_keys": {side: list(modes_by_side[side]["mode_key"]) for side in ("bottom", "top")},
            "mode_indices_by_side": {
                side: int(modes_by_side[side]["mode_index"])
                for side in ("bottom", "top")
            },
            "actual_cell_ids_by_side": {
                side: int(modes_by_side[side]["cell_id"])
                for side in ("bottom", "top")
            },
            "actual_class_ids_by_side": {
                side: str(modes_by_side[side].get("class_id", "UNAVAILABLE"))
                for side in ("bottom", "top")
            },
            "actual_mode_keys_by_side": {
                side: [list(spec["mode_key"]) for spec in local_blocks[side]["mode_specs"]]
                for side in ("bottom", "top")
            },
            "packet_npz_sha256": {side: modes_by_side[side]["npz_sha256"] for side in ("bottom", "top")},
            "raw_B_D_packet_conversion": {
                side: {
                    "source": source_kind[side],
                    "gauge": (
                        "boundary_plane; B_plane=B_global/g, "
                        "D_plane=D_global*H_global/conj(g), "
                        "H_plane=H_global/|g|^2"
                    ),
                    "B_relative_to_converted_saved_packet": packet_records[side]["b_relative_to_packet"],
                    "raw_D_relative_to_converted_saved_packet": packet_records[side]["d_relative_to_packet"],
                    "original_H_p": modes_by_side[side]["H_p_global_z"],
                    "original_H_p_gauge": "global_z",
                    "global_z_phase": {
                        "real": float(modes_by_side[side]["global_z_phase"].real),
                        "imag": float(modes_by_side[side]["global_z_phase"].imag),
                    },
                    "boundary_plane_H_p_from_saved_packet": modes_by_side[side][
                        "H_p_boundary_plane_from_packet"
                    ],
                    "production_boundary_plane_H_p": float(
                        mode_normalizations[modes_by_side[side]["mode_index"]]
                    ) if mode_normalizations is not None else None,
                    "saved_packet_npz_sha256": modes_by_side[side]["npz_sha256"],
                    "raw_D_conversion_uses_original_global_H": True,
                    "raw_D_kept_independent": True,
                }
                for side in ("bottom", "top")
            },
            "local_constraint_scope": {
                "global_mpc_expansion_rows_used": len(normalized_mpc),
                "slave_rows_in_two_cell_trace_closure": trace_constraint.slave_rows,
                "active_trace_coordinates": active_rows,
                "nontrivial_complex_coefficients": sum(
                    int(np.count_nonzero(np.abs(values.imag) > 1e-14))
                    for _masters, values in normalized_mpc.values()
                ),
                "identity_MPC_only": not normalized_mpc,
                "mpc_phase_is_conjugated_on_residual_pullback": True,
            },
            "same_cell_s_p_crossmode": {
                "by_side": crossmode_facts_by_side,
                "bottom_ports": [int(value) for value in local_blocks["bottom"]["ports"]],
                "Hhat_s_p_offdiagonal": {
                    "real": float(crossmode_q11.real),
                    "imag": float(crossmode_q11.imag),
                    "absolute": float(abs(crossmode_q11)),
                },
                "Hhat_only_s_p_projection": complex_matrix_records(
                    hhat_only_port_projection
                ),
                "full_q11_s_p_projection": complex_matrix_records(q11_dense),
                "consumed_by_local_q11_tile": same_cell_pair_in_port_projection,
                "full_target_q_identity_claimed": False,
            },
            "native_residual": {
                "relative": float(generated_native["native_identity_relative"]),
                "relative_limit": 1e-10,
                "raw_to_dual_rhs_conversion_relative": raw_rhs_dual_error,
                "schur_port_relative": float(generated_native["schur_port_identity_relative"]),
                "formula": generated_native["native_identity_formula"],
                "nonzero_interior_rhs_norm": float(np.linalg.norm(full_rhs[np.asarray([
                    compact[row] for side in ("bottom", "top")
                    for row in raw_cell_globals[side][packet_records[side]["interior_positions"]]
                ], dtype=PETSc.IntType)])),
                "nonzero_trace_rhs_norm": float(np.linalg.norm(full_rhs[np.asarray([
                    compact[row] for side in ("bottom", "top")
                    for row in raw_cell_globals[side][packet_records[side]["trace_positions"]]
                ], dtype=PETSc.IntType)])),
                "nonzero_port_rhs_norm": float(np.linalg.norm(port_rhs)),
                "cached_native_residual_max_difference": float(np.max(np.abs(
                    generated_native["native_residual"] - cached_native["native_residual"]
                ), initial=0.0)),
            },
            "bounded_reduced_contributions": {
                "matched_labels": labels,
                "cached_labels": cached_labels,
                "generated_vs_cached_relative_frobenius": contribution_relative,
                "generated_vs_cached_max_absolute": contribution_max,
                "Hhat_correction": hhat_corrections,
                "generated_callback_calls": int(generated.audit["generated_callback_call_count"]),
                "full_Hhat_materialized": False,
                "full_target_q_csr_created": False,
            },
            "local_q_row_tile_consumer": {
                "consumer": "_assemble_bounded_v17_row_tile_q_patterns",
                "projected_shape_per_block": [2, 2],
                "generated_numeric_contribution_count": generated_q_facts.get("numeric_contribution_count"),
                "cached_numeric_contribution_count": cached_q_facts.get("numeric_contribution_count"),
                "maximum_generated_vs_cached_block_error": q_difference_max,
                "generated_vs_cached_frobenius_relative": q_relative_frobenius,
                "generated_vs_cached_frobenius_limit": 1e-11,
                "block_facts": q_block_facts,
                "trace_only_selector": True,
                "same_cell_s_p_port_only_selector": True,
                "Hhat_only_projection_recorded_independently": True,
                "full_port_port_tile_recorded": True,
                "trace_to_port_nonzero": q_block_facts["01"]["generated_nnz"] > 0,
                "port_to_trace_nonzero": q_block_facts["10"]["generated_nnz"] > 0,
                "port_port_nonzero": q_block_facts["11"]["generated_nnz"] > 0,
                "target_q_count": 8,
                "target_q_built_count": 0,
                "scope": "two saved local cell/mode packets projected through trace and port selectors; local interface consumer check only, not target Ny8 q maps or global q CSR",
            },
            "saved_local_direct_quadrature_degree_by_side": {
                side: int(packet_records[side]["facts"]["boundary_quadrature_degree"])
                for side in ("bottom", "top")
            },
            "current_live_native_quadrature_degree": quadrature_degree,
            "official_result": False,
            "production_support_filter_applied_to_local_raw_rows": False,
        }
    finally:
        generated.destroy()
        cached.destroy()


def _packet_apply_B(
    factory: Callable[[], tuple[np.ndarray, np.ndarray]], record: Mapping[str, Any], alpha: Any
) -> tuple[np.ndarray, np.ndarray]:
    values = np.asarray(alpha, dtype=np.complex128).reshape(-1)
    if values.shape != (1,):
        raise ValueError("one saved local packet port expects one B amplitude")
    raw_b, _raw_d = factory()
    return (
        np.ascontiguousarray(raw_b[record["interior_positions"]] * values[0]),
        np.ascontiguousarray(raw_b[record["trace_positions"]] * values[0]),
    )


def _packet_apply_D(
    factory: Callable[[], tuple[np.ndarray, np.ndarray]],
    record: Mapping[str, Any],
    interior: Any,
    trace: Any,
) -> np.ndarray:
    _raw_b, raw_d = factory()
    xi = np.asarray(interior, dtype=np.complex128)
    xt = np.asarray(trace, dtype=np.complex128)
    result = np.dot(raw_d[record["interior_positions"]], xi)
    result += np.dot(raw_d[record["trace_positions"]], xt)
    return np.asarray([result], dtype=np.complex128)


def _packet_apply_B_tile(
    factory: Callable[[], tuple[np.ndarray, np.ndarray]],
    record: Mapping[str, Any],
    ports: Any,
    amplitudes: Any,
    expected_port: int,
) -> tuple[np.ndarray, np.ndarray]:
    port_ids = np.asarray(ports, dtype=np.int64).reshape(-1)
    alpha = np.asarray(amplitudes, dtype=np.complex128)
    if port_ids.shape != (1,) or int(port_ids[0]) != expected_port or alpha.ndim != 2 or alpha.shape[0] != 1:
        raise ValueError("saved local B tile does not match its bounded port row")
    raw_b, _raw_d = factory()
    return (
        np.ascontiguousarray(raw_b[record["interior_positions"], None] @ alpha),
        np.ascontiguousarray(raw_b[record["trace_positions"], None] @ alpha),
    )


def _packet_apply_D_tile(
    factory: Callable[[], tuple[np.ndarray, np.ndarray]],
    record: Mapping[str, Any],
    ports: Any,
    interior: Any,
    trace: Any,
    expected_port: int,
) -> np.ndarray:
    port_ids = np.asarray(ports, dtype=np.int64).reshape(-1)
    xi = np.asarray(interior, dtype=np.complex128)
    xt = np.asarray(trace, dtype=np.complex128)
    if port_ids.shape != (1,) or int(port_ids[0]) != expected_port or xi.ndim != 2 or xt.ndim != 2:
        raise ValueError("saved local D tile does not match its bounded port row")
    _raw_b, raw_d = factory()
    result = raw_d[record["interior_positions"]][None, :] @ xi
    result += raw_d[record["trace_positions"]][None, :] @ xt
    return np.ascontiguousarray(result)


def _sparse_csr_sha256(matrix: Any) -> str:
    from scipy import sparse

    value = sparse.csr_matrix(matrix, dtype=np.complex128, copy=True)
    value.sort_indices()
    digest = hashlib.sha256()
    digest.update(np.asarray(value.shape, dtype="<i8").tobytes())
    for array in (value.data, value.indices, value.indptr):
        digest.update(array.dtype.str.encode("ascii"))
        digest.update(np.asarray(array.shape, dtype="<i8").tobytes())
        digest.update(np.ascontiguousarray(array).tobytes())
    return digest.hexdigest()


def _v23_q_coverage_record(q_tile: Mapping[str, Any]) -> dict[str, Any]:
    status = str(q_tile.get("status", "NOT_RUN"))
    base = {
        "expected_q_count": 8,
        "built_q_count": 0,
        "full_q_matrix_coverage": "0/8",
        "selected_q_port_tile": q_tile.get("artifact_path", "NOT_RUN"),
        "selected_q_port_tile_sha256": q_tile.get("artifact_sha256"),
        "volume_qualification": "PARTIAL_NOT_RUN",
    }
    if status == "PASS_REAL_ORIGINAL_NY8_Q_PORT_TILE":
        return {
            **base,
            "status": "PARTIAL_REAL_Q_PORT_TILE",
            "reason": "one actual q=0 port tile is measured; full q matrices and volume Schur blocks remain unbuilt",
        }
    if status == "NOT_RUN_RESOURCE_GATE":
        return {
            **base,
            "status": "NOT_RUN_RESOURCE_GATE",
            "volume_qualification": "NOT_RUN",
            "reason": "the selected real q port tile stopped at its recorded memory admission gate",
        }
    if status == "NOT_RUN_TIME_STOP":
        return {
            **base,
            "status": "NOT_RUN_TIME_STOP",
            "volume_qualification": "NOT_RUN",
            "reason": "the fixed campaign numerical cutoff arrived before the selected q tile started",
        }
    if status == "NOT_RUN":
        return {
            **base,
            "status": "NOT_RUN",
            "volume_qualification": "NOT_RUN",
            "reason": "the selected real q tile was not attempted",
        }
    return {
        **base,
        "status": "FAILED",
        "volume_qualification": "NOT_RUN",
        "failure_type": q_tile.get("failure_type"),
        "failure_message": q_tile.get("failure_message"),
    }


def _v23_scan_time_forecast(
    modes: Sequence[Any],
    *,
    next_mode_index: int,
    mode_timing_by_side: Mapping[str, Mapping[str, Any]],
    observed_wall_seconds: float,
    observed_process_cpu_seconds: float,
) -> dict[str, Any]:
    remaining = {side: 0 for side in ("bottom", "top")}
    for mode in modes[next_mode_index:]:
        side = str(mode.side)
        if side not in remaining:
            raise ValueError("V23 timing forecast encountered an unknown port side")
        remaining[side] += 1
    measured_rates: dict[str, dict[str, float]] = {}
    for side in ("bottom", "top"):
        record = mode_timing_by_side.get(side, {})
        count = int(record.get("completed_modes", 0))
        if count > 0:
            measured_rates[side] = {
                "wall_seconds_per_mode": float(record["wall_seconds"]) / count,
                "process_cpu_seconds_per_mode": float(record["process_cpu_seconds"]) / count,
            }
    if not measured_rates:
        return {
            "status": "NOT_ESTIMABLE_BEFORE_A_MEASURED_MODE",
            "remaining_modes_by_side": remaining,
            "estimated_remaining_wall_seconds": None,
            "estimated_remaining_process_cpu_seconds": None,
            "rate_by_side": {},
        }
    conservative_wall_rate = max(
        values["wall_seconds_per_mode"] for values in measured_rates.values()
    )
    conservative_cpu_rate = max(
        values["process_cpu_seconds_per_mode"] for values in measured_rates.values()
    )
    completed_count = sum(
        int(mode_timing_by_side.get(side, {}).get("completed_modes", 0))
        for side in ("bottom", "top")
    )
    attributed_wall = sum(
        float(mode_timing_by_side.get(side, {}).get("wall_seconds", 0.0))
        for side in ("bottom", "top")
    )
    attributed_cpu = sum(
        float(mode_timing_by_side.get(side, {}).get("process_cpu_seconds", 0.0))
        for side in ("bottom", "top")
    )
    shared_wall_overhead_per_mode = (
        max(float(observed_wall_seconds) - attributed_wall, 0.0) / completed_count
        if completed_count
        else 0.0
    )
    shared_cpu_overhead_per_mode = (
        max(float(observed_process_cpu_seconds) - attributed_cpu, 0.0) / completed_count
        if completed_count
        else 0.0
    )
    rate_by_side = {}
    wall_estimate = 0.0
    cpu_estimate = 0.0
    for side in ("bottom", "top"):
        measured = measured_rates.get(side)
        wall_rate = (
            measured["wall_seconds_per_mode"] if measured else conservative_wall_rate
        )
        cpu_rate = (
            measured["process_cpu_seconds_per_mode"] if measured else conservative_cpu_rate
        )
        rate_by_side[side] = {
            "wall_seconds_per_mode": wall_rate,
            "process_cpu_seconds_per_mode": cpu_rate,
            "source": "measured_side_block_rate" if measured else "conservative_max_measured_side_rate",
            "completed_modes": int(
                mode_timing_by_side.get(side, {}).get("completed_modes", 0)
            ),
        }
        wall_estimate += remaining[side] * (wall_rate + shared_wall_overhead_per_mode)
        cpu_estimate += remaining[side] * (cpu_rate + shared_cpu_overhead_per_mode)
    return {
        "status": "MEASURED_SIDE_RATE_FORECAST",
        "remaining_modes_by_side": remaining,
        "rate_by_side": rate_by_side,
        "shared_wall_overhead_per_mode_seconds": shared_wall_overhead_per_mode,
        "shared_process_cpu_overhead_per_mode_seconds": shared_cpu_overhead_per_mode,
        "estimated_remaining_wall_seconds": wall_estimate,
        "estimated_remaining_process_cpu_seconds": cpu_estimate,
        "planning_only_not_a_numerical_gate": True,
    }


def _run_v23_original_ny8_q_port_tile(
    root: Path,
    output_directory: Path,
    *,
    preflight: Mapping[str, Any],
    modes: Sequence[Any],
    mode_rows: Sequence[Mapping[str, Any]],
    space: Any,
    mpc: Any,
    cfg: Any,
    assemblers: Mapping[tuple[str, int], Any],
    assembly_context: Mapping[str, Any],
    axes_values: Mapping[str, Any],
    mapping_rows: Sequence[Mapping[str, Any]],
    boundary_global_rows: Sequence[int],
    interior_rows: np.ndarray,
    h_values: np.ndarray,
    resource_sample: Callable[[], Mapping[str, Any]],
) -> dict[str, Any]:
    """Build one real Ny8 boundary port tile using the probe's existing FE/MPC."""
    from dolfinx import cpp
    from petsc4py import PETSc
    from scipy import sparse

    from src.solvers.dtn_boundary_phase_gauge import BOUNDARY_PLANE
    from src.solvers.fullspace_dtn_action import iter_fullspace_dtn_functionals_from_surface
    from src.solvers.hcurl_canonical_vector_dolfinx import _physical_entity_transform
    from src.solvers.original_port_blocks import DiagonalOriginalPortBlock
    from src.solvers.p6_cell_condensed_action import P6GlobalDirectCarrierProvider
    from src.solvers.task40_v10_p6_periodic_profile import (
        TASK40_V20_P6_TARGET_ORIGINAL_NY8_PROFILE,
    )
    from src.solvers.task40_v10_p6_yorbit import (
        Task40V10FullLayout,
        build_task40_v10_sector_contexts,
    )

    started = perf_counter()
    cpu_started = process_time()
    output_path = output_directory / "v23_reference_q_port_tile.json"
    oracle_path = output_directory / "v23_selected_mode_production_B_D_H.npz"
    projection_readback_path = output_directory / "v23_selected_q_projection_readback.npz"
    profile = TASK40_V20_P6_TARGET_ORIGINAL_NY8_PROFILE
    resource_gates: list[dict[str, Any]] = []
    result: dict[str, Any] = {
        "schema": "task40extra.review_v23_original_ny8_selected_q_port_tile.v1",
        "status": "NOT_RUN",
        "official_result": False,
        "run_id": preflight.get("run_id"),
        "source_sha": preflight.get("source_sha"),
        "input_sha256": preflight.get("input_sha256"),
        "target_physical_model_sha256": preflight.get("physical_model_sha256"),
        "profile_identity": profile.identity(),
        "expected_q_count": int(profile.q_count),
        "full_q_matrix_coverage": "0/8",
        "factor_count": 0,
        "ksp_created": False,
        "pde_solved": False,
        "official_R_T_A_created": False,
        "resource_gates": resource_gates,
    }
    provider = tile_iterator = q_map = None
    try:
        from src.runners.task40_v10_campaign import (
            TASK40_V23_CAMPAIGN_SHA256,
            TASK40_V24_CAMPAIGN_SHA256,
        )

        campaign_before = _read_v22_campaign_state(root)
        if campaign_before["campaign_window_sha256"] not in {
            TASK40_V23_CAMPAIGN_SHA256,
            TASK40_V24_CAMPAIGN_SHA256,
        }:
            raise ValueError("selected q tile requires the registered fixed V23 or V24 execution window")
        result["campaign_before"] = {
            "window_sha256": campaign_before["campaign_window_sha256"],
            "remaining_numerical_seconds": campaign_before["remaining_numerical_seconds"],
        }
        result["execution_campaign_window_sha256"] = campaign_before[
            "campaign_window_sha256"
        ]
        result["artifact_campaign_window_sha256"] = TASK40_V23_CAMPAIGN_SHA256
        if campaign_before["remaining_numerical_seconds"] <= 0.0:
            result.update(
                status="NOT_RUN_TIME_STOP",
                time_stop={
                    "classification": "NUMERICAL_TIME_STOP",
                    "remaining_numerical_seconds": 0.0,
                    "source": "fixed V23 campaign numerical cutoff",
                },
            )
            return result
        if int(space.mesh.comm.size) != 1 or not _same_v23_mpc_function_space_layout(
            space, mpc.function_space
        ):
            raise ValueError("selected original Ny8 q tile requires the existing MPI1 p6 space/MPC")
        axes = {name: np.asarray(axes_values[name], dtype=np.float64) for name in ("x", "y", "z")}
        if any(
            values.ndim != 1 or len(values) < 2 or not np.isfinite(values).all()
            or np.any(np.diff(values) <= 0.0)
            for values in axes.values()
        ):
            raise ValueError("saved actual Ny8 axes are incomplete or non-monotone")
        if tuple(len(axes[name]) - 1 for name in ("x", "y", "z")) != profile.global_cell_axes:
            raise ValueError("existing target axes differ from the registered Ny8 profile")
        full_rows = int(space.dofmap.index_map.size_global)
        if full_rows != profile.global_storage_rows:
            raise ValueError("existing p6 storage rows differ from the registered Ny8 profile")
        if full_rows - int(len(mpc.slaves)) != profile.global_independent_rows:
            raise ValueError("existing finalized MPC rows differ from the registered Ny8 profile")
        if (
            h_values.shape != (len(modes),)
            or not np.isfinite(h_values).all()
            or np.any(h_values <= 0.0)
            or len(interior_rows) > 1 and np.any(interior_rows[1:] <= interior_rows[:-1])
        ):
            raise ValueError("frozen original H_p or existing interior-row classifier is invalid")

        axis_tuples = {name: tuple(map(float, axes[name])) for name in ("x", "y", "z")}
        contexts = build_task40_v10_sector_contexts(
            tuple(modes),
            cfg,
            axis_tuples,
            expected_q_counts=profile.q_port_counts,
            expected_sector_counts=profile.sector_port_counts,
        )
        q0_context = contexts[0]
        q0_aliases = np.flatnonzero(np.asarray(q0_context.local_branch_indices) == 0)
        if tuple(q0_context.global_q_indices) != (0, profile.q_count // 2):
            raise ValueError("actual q=0 Ny8 sector assignment differs from the registered profile")
        if len(q0_aliases) != profile.q_port_counts[0] or not len(q0_aliases):
            raise ValueError("actual q=0 physical port alias count differs from the profile")
        local_mode_index = int(q0_aliases[0])
        mode_index = int(q0_context.original_mode_indices[local_mode_index])
        mode = modes[mode_index]
        mode_row = mode_rows[mode_index]
        mode_keys = tuple(
            (
                int(row["mode_index"]), str(row["side"]), int(row["m"]),
                int(row["n"]), str(row["polarization"]),
            )
            for row in mode_rows
        )
        original_h = DiagonalOriginalPortBlock(h_values, mode_keys)
        expected_key = original_h.mode_keys[mode_index]
        if expected_key[1:] != (
            str(mode.side), int(mode.m), int(mode.n), str(mode.polarization)
        ):
            raise ValueError("selected q=0 physical mode differs from the original H_p key")
        result["q_assignment"] = {
            "status": "PASS_PROFILE_BOUND_ACTUAL_MODE_ASSIGNMENT",
            "global_q": 0,
            "paired_global_q": int(q0_context.global_q_indices[1]),
            "twist_index": int(q0_context.twist_index),
            "q_port_count": len(q0_aliases),
            "expected_q_port_count": int(profile.q_port_counts[0]),
            "selected_local_mode_index": local_mode_index,
            "selected_original_mode_index": mode_index,
            "selected_q_port_alias_column": 0,
            "mode_key": list(expected_key),
            "mode_assignment_source": "build_task40_v10_sector_contexts over the original Ny8 axes and complete frozen mode table",
        }
        result["original_H_p_identity"] = {
            **original_h.audit,
            "selected_original_H_p": float(original_h.diagonal[mode_index].real),
            "mode_manifest_sha256": preflight.get("target_mode_inventory", {}).get(
                "mode_manifest_sha256"
            ),
        }

        # Reuse the original full-layout Ny8 DFT only; no global entity records
        # or q matrix are constructed here.
        layout_metadata = SimpleNamespace(
            ny=int(profile.q_count),
            width=int(profile.rows_per_q),
            independent=range(profile.global_independent_rows),
            full_rows=int(profile.global_storage_rows),
            dimension_counts={3: int(profile.global_interior_rows)},
        )
        full_layout = Task40V10FullLayout(
            layout_metadata,
            cfg,
            expected_inventory={
                "ny": profile.q_count,
                "width": profile.rows_per_q,
                "independent_rows": profile.global_independent_rows,
                "storage_rows": profile.global_storage_rows,
                "interior_rows": profile.global_interior_rows,
            },
        )
        result["full_layout_formula"] = {
            **dict(full_layout.audit),
            "q0_dft_column_sha256": _array_sha256(full_layout.cell_dft[:, 0]),
            "full_FE_entity_map_materialized": False,
        }

        # Prove the target and filled-reference port patches share the same
        # complete facet rectangles; their volume/material identities stay separate.
        nx, ny, nz = profile.global_cell_axes
        actual_bounds = {"bottom": [], "top": []}
        for row in mapping_rows:
            side = str(row["side"])
            if side not in actual_bounds:
                raise ValueError("target boundary mapping contains an unknown port side")
            actual_bounds[side].append(
                tuple(float(value) for value in np.asarray(row["cell_bounds_nm"]).reshape(-1))
            )
        expected_bounds = {"bottom": [], "top": []}
        for side, iz in (("bottom", 0), ("top", nz - 1)):
            for iy in range(ny):
                for ix in range(nx):
                    expected_bounds[side].append(
                        tuple(float(value) for value in np.asarray(
                            [
                                [axes["x"][ix], axes["x"][ix + 1]],
                                [axes["y"][iy], axes["y"][iy + 1]],
                                [axes["z"][iz], axes["z"][iz + 1]],
                            ], dtype=np.float64
                        ).reshape(-1))
                    )
        max_boundary_delta = 0.0
        for side in ("bottom", "top"):
            if len(actual_bounds[side]) != _EXPECTED_FACETS_BY_SIDE[side]:
                raise ValueError("actual production port facet count differs from the frozen descriptor")
            if len(expected_bounds[side]) != _EXPECTED_FACETS_BY_SIDE[side]:
                raise ValueError("filled-reference port facet count differs from the Ny8 profile")
            left, right = sorted(actual_bounds[side]), sorted(expected_bounds[side])
            for actual, reference in zip(left, right, strict=True):
                delta = max(abs(a - b) for a, b in zip(actual, reference, strict=True))
                max_boundary_delta = max(max_boundary_delta, delta)
                if delta > 1.0e-10:
                    raise ValueError("target and filled-reference port boundary descriptors differ")
        descriptor = {
            side: [list(row) for row in sorted(actual_bounds[side])]
            for side in ("bottom", "top")
        }
        descriptor_sha = hashlib.sha256(
            json.dumps(descriptor, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        result["boundary_descriptor_equivalence"] = {
            "status": "PASS_COMPLETE_SAME_PORT_CELL_RECTANGLES",
            "descriptor_sha256": descriptor_sha,
            "target_physical_model_sha256": preflight.get("physical_model_sha256"),
            "filled_reference_geometry_identity": "same actual Ny8 axes/profile with filled interior; not assembled as a second mesh",
            "target_material_and_void_identity_preserved_separately": True,
            "facets_by_side": {side: len(actual_bounds[side]) for side in actual_bounds},
            "maximum_cell_bound_difference_nm": max_boundary_delta,
            "phase_gauge": BOUNDARY_PLANE,
        }

        # Freeze original production B/D/H independently, then compare a fresh
        # provider replay against that read-back record.
        oracle_audit: dict[str, Any] = {}
        oracle_iterator = iter_fullspace_dtn_functionals_from_surface(
            modes, assemblers, mpc, cfg, phase_gauge=BOUNDARY_PLANE,
            assembly_context=assembly_context, start_index=mode_index,
            stop_index=mode_index + 1, audit=oracle_audit,
        )
        try:
            oracle = next(oracle_iterator)
            if tuple(oracle.mode_key) != expected_key:
                raise ValueError("frozen production oracle key differs from original H_p")
            if complex(oracle.normalization_h) != complex(original_h.diagonal[mode_index]):
                raise ValueError("frozen production oracle H_p differs from original H_p")
            b_rows = np.array(oracle.coupling_rows, copy=True)
            b_values = np.array(oracle.coupling_values, copy=True)
            d_rows = np.array(oracle.projection_rows, copy=True)
            d_values = np.array(oracle.projection_values, copy=True)
            hp_value = float(oracle.normalization_h)
            oracle_key = tuple(oracle.mode_key)
            if next(oracle_iterator, None) is not None:
                raise ValueError("bounded production oracle emitted more than one mode")
        finally:
            oracle_iterator.close()
        support_rows = np.unique(np.concatenate((b_rows, d_rows))).astype(np.int64, copy=False)
        if not len(support_rows) or not len(b_rows) or not len(d_rows):
            raise ValueError("selected real production mode has empty B or independent D support")
        boundary_rows = np.asarray(boundary_global_rows, dtype=np.int64)
        boundary_positions = np.searchsorted(boundary_rows, support_rows)
        boundary_ok = boundary_positions < len(boundary_rows)
        boundary_match = np.zeros(len(support_rows), dtype=np.bool_)
        boundary_match[boundary_ok] = boundary_rows[boundary_positions[boundary_ok]] == support_rows[boundary_ok]
        if not np.all(boundary_match):
            raise ValueError("production B/D support escapes the complete mapped port-adjacent cell set")
        interior_positions = np.searchsorted(interior_rows, support_rows)
        interior_ok = interior_positions < len(interior_rows)
        is_interior = np.zeros(len(support_rows), dtype=np.bool_)
        is_interior[interior_ok] = interior_rows[interior_positions[interior_ok]] == support_rows[interior_ok]
        if np.any(is_interior):
            raise ValueError("selected B/D contains a cell-interior row without a qualified local term")
        with oracle_path.open("wb") as stream:
            np.savez(
                stream,
                mode_key_json=np.asarray(json.dumps(list(oracle_key), separators=(",", ":"))),
                B_rows=np.asarray(b_rows, dtype="<i8"), B_values=np.asarray(b_values, dtype="<c16"),
                D_rows=np.asarray(d_rows, dtype="<i8"), D_values=np.asarray(d_values, dtype="<c16"),
                H_p=np.asarray([hp_value], dtype="<f8"),
                original_H_identity_sha256=np.asarray(original_h.identity_sha256),
            )
            stream.flush()
            os.fsync(stream.fileno())
        oracle_sha = _sha256_file(oracle_path)
        with np.load(oracle_path, allow_pickle=False) as frozen:
            if str(frozen["mode_key_json"].item()) != json.dumps(list(oracle_key), separators=(",", ":")):
                raise ValueError("hash-bound production B/D/H read-back changed its mode key")
            b_rows = np.array(frozen["B_rows"], dtype=np.int64, copy=True)
            b_values = np.array(frozen["B_values"], dtype=np.complex128, copy=True)
            d_rows = np.array(frozen["D_rows"], dtype=np.int64, copy=True)
            d_values = np.array(frozen["D_values"], dtype=np.complex128, copy=True)
            hp_value = float(frozen["H_p"][0])
            if str(frozen["original_H_identity_sha256"].item()) != original_h.identity_sha256:
                raise ValueError("frozen production oracle is bound to a different original H_p block")

        topology = space.mesh.topology
        for dim in (1, 2):
            topology.create_entities(dim)
            topology.create_connectivity(dim, topology.dim)
            topology.create_connectivity(topology.dim, dim)
        topology.create_entity_permutations()
        counts = {dim: int(topology.index_map(dim).size_local) for dim in (1, 2)}
        geometry_bytes = 3 * 8 * (2 * counts[1] + 4 * counts[2])
        inventory_reserve = (counts[1] + counts[2]) * 768 + geometry_bytes
        resource_gates.append(_resource_admission(
            "v23_actual_edge_face_orbit_inventory", inventory_reserve,
            resource_sample=resource_sample, require_task_cgroup=True,
        ))
        geometry_by_dim = {
            1: np.asarray(cpp.mesh.entities_to_geometry(
                space.mesh._cpp_object, 1, np.arange(counts[1], dtype=np.int32), True
            ), dtype=np.int32),
            2: np.asarray(cpp.mesh.entities_to_geometry(
                space.mesh._cpp_object, 2, np.arange(counts[2], dtype=np.int32), True
            ), dtype=np.int32),
        }
        slave_rows = np.asarray(mpc.slaves, dtype=np.int64)
        slave_rows.sort()
        grid = tuple(axes[name] for name in ("x", "y", "z"))
        layout = space.dofmap.dof_layout
        base_sizes: dict[Any, int] = {}
        base_masks: dict[Any, int] = {}
        orbit_rows = [0] * profile.q_count

        def block_stream():
            for dim in (1, 2):
                entity_to_cell = topology.connectivity(dim, topology.dim)
                cell_to_entity = topology.connectivity(topology.dim, dim)
                for entity in range(counts[dim]):
                    incident = entity_to_cell.links(entity)
                    if not len(incident):
                        continue
                    cell = int(incident[0])
                    local_entity = np.flatnonzero(np.asarray(cell_to_entity.links(cell)) == entity)
                    if len(local_entity) != 1:
                        raise ValueError("actual entity/cell incidence is not unique")
                    positions = np.asarray(layout.entity_dofs(dim, int(local_entity[0])), dtype=np.int32)
                    if not len(positions):
                        continue
                    local_dofs = np.asarray(space.dofmap.cell_dofs(cell), dtype=np.int32)
                    rows = np.asarray(space.dofmap.index_map.local_to_global(local_dofs[positions]), dtype=np.int64)
                    sp = np.searchsorted(slave_rows, rows)
                    valid = sp < len(slave_rows)
                    slave = np.zeros(len(rows), dtype=np.bool_)
                    slave[valid] = slave_rows[sp[valid]] == rows[valid]
                    if np.all(slave):
                        continue
                    if np.any(slave):
                        raise ValueError("actual edge/face p6 block is partly eliminated by the y MPC")
                    coords = space.mesh.geometry.x[geometry_by_dim[dim][entity]].astype(np.float64, copy=False)
                    indexed = []
                    for point in coords:
                        ijk = []
                        for values, value in zip(grid, point, strict=True):
                            pos = int(np.searchsorted(values, value))
                            choices = [p for p in (pos - 1, pos) if 0 <= p < len(values)]
                            nearest = min(choices, key=lambda p: abs(float(values[p]) - float(value)))
                            if abs(float(values[nearest]) - float(value)) > 1.0e-9:
                                raise ValueError("actual edge/face coordinate misses the saved grid")
                            ijk.append(nearest)
                        indexed.append(tuple(ijk))
                    orbit = min(point[1] for point in indexed)
                    if orbit >= profile.q_count:
                        raise ValueError("uneliminated Ny8 y-maximum entity cannot own an orbit")
                    base = (dim, tuple(sorted((x, y - orbit, z) for x, y, z in indexed)))
                    yield dim, entity, rows, coords, orbit, base

        for dim, _entity, rows, _coords, orbit, base in block_stream():
            mask = 1 << orbit
            if base_masks.get(base, 0) & mask:
                raise ValueError("duplicate actual edge/face block in the same y orbit")
            base_masks[base] = base_masks.get(base, 0) | mask
            if base in base_sizes and base_sizes[base] != len(rows):
                raise ValueError("canonical edge/face block width changes across Ny8 orbits")
            base_sizes[base] = len(rows)
            orbit_rows[orbit] += len(rows)
        full_mask = (1 << profile.q_count) - 1
        trace_width = sum(base_sizes.values())
        if (
            not base_sizes or any(mask != full_mask for mask in base_masks.values())
            or trace_width != profile.trace_rows_per_q
            or sum(orbit_rows) != profile.global_trace_rows
            or any(value != trace_width for value in orbit_rows)
        ):
            raise ValueError("actual edge/face inventory differs from the registered complete Ny8 trace")
        slots: dict[Any, tuple[int, int]] = {}
        offset = 0
        for base in sorted(base_sizes):
            size = base_sizes[base]
            slots[base] = (offset, size)
            offset += size

        max_block = max(base_sizes.values())
        nnz_bound = len(support_rows) * max_block
        tile_reserve = (
            32 * nnz_bound + 8 * (len(support_rows) + 1)
            + 4 * trace_width * 16 + 32 * len(support_rows)
            + 16 * max_block * max_block
        )
        resource_gates.append(_resource_admission(
            "v23_selected_original_ny8_q_port_map_tile", tile_reserve,
            resource_sample=resource_sample, require_task_cgroup=True,
        ))
        q_rows = np.empty(nnz_bound, dtype=np.int32)
        q_cols = np.empty(nnz_bound, dtype=np.int32)
        q_data = np.empty(nnz_bound, dtype=np.complex128)
        b_oracle_q = np.zeros(trace_width, dtype=np.complex128)
        d_oracle_q = np.zeros(trace_width, dtype=np.complex128)
        covered = np.zeros(len(support_rows), dtype=np.bool_)
        predecessors: list[dict[str, Any]] = []
        q_nnz = 0
        for dim, entity, rows, coords, orbit, base in block_stream():
            pos = np.searchsorted(support_rows, rows)
            valid = pos < len(support_rows)
            selected = np.zeros(len(rows), dtype=np.bool_)
            selected[valid] = support_rows[pos[valid]] == rows[valid]
            if not np.any(selected):
                continue
            selected_pos = pos[selected]
            if np.any(covered[selected_pos]):
                raise ValueError("selected production rows appear in multiple FE entity blocks")
            covered[selected_pos] = True
            first, width = slots[base]
            transform, state = _physical_entity_transform(coords, dim, 6, 1.0e-9)
            if transform.shape != (width, width) or not np.isfinite(transform).all():
                raise ValueError("actual selected p6 entity transform is invalid")
            phase = complex(full_layout.cell_dft[orbit, 0])
            bv = np.zeros(width, dtype=np.complex128)
            dv = np.zeros(width, dtype=np.complex128)
            bi = np.searchsorted(b_rows, rows)
            bm = (bi < len(b_rows))
            bm[bm] &= b_rows[bi[bm]] == rows[bm]
            bv[bm] = b_values[bi[bm]]
            di = np.searchsorted(d_rows, rows)
            dm = (di < len(d_rows))
            dm[dm] &= d_rows[di[dm]] == rows[dm]
            dv[dm] = d_values[di[dm]]
            b_oracle_q[first:first + width] += np.conjugate(phase) * (transform.conj().T @ bv)
            d_oracle_q[first:first + width] += phase * (transform.T @ dv)
            for local_row in np.flatnonzero(selected):
                nz = np.flatnonzero(transform[local_row] != 0.0)
                stop = q_nnz + len(nz)
                if stop > nnz_bound:
                    raise RuntimeError("selected q map exceeded its admitted sparse bound")
                q_rows[q_nnz:stop] = int(pos[local_row])
                q_cols[q_nnz:stop] = first + nz
                q_data[q_nnz:stop] = transform[local_row, nz] * phase
                q_nnz = stop
            predecessors.append({
                "dimension": int(dim), "orbit": int(orbit),
                "canonical_base": [int(base[0]), [list(map(int, p)) for p in base[1]]],
                "canonical_trace_columns": list(range(first, first + width)),
                "all_native_entity_rows": list(map(int, rows)),
                "selected_production_rows": list(map(int, rows[selected])),
                "entity_coordinates_sha256": _array_sha256(coords),
                "primal_transform_state": list(state),
                "canonical_to_native_transform_sha256": _array_sha256(transform),
                "q0_dft_phase": {"real": phase.real, "imag": phase.imag},
            })
        if not np.all(covered):
            raise ValueError("some production B/D rows have no complete edge/face block predecessor")
        q_map = sparse.csr_matrix(
            (q_data[:q_nnz], (q_rows[:q_nnz], q_cols[:q_nnz])),
            shape=(len(support_rows), trace_width), dtype=np.complex128,
        )
        q_map.sum_duplicates()
        q_map.sort_indices()
        q_map_sha = _sparse_csr_sha256(q_map)

        if (
            support_rows.ndim != 1
            or support_rows.dtype.kind not in "iu"
            or support_rows.dtype.kind == "b"
            or (len(support_rows) > 1 and np.any(support_rows[1:] <= support_rows[:-1]))
        ):
            raise ValueError("selected q trace support must be sorted unique integer global rows")

        class CompactSelectedRows:
            def __getitem__(self, row: int) -> int:
                pos = int(np.searchsorted(support_rows, int(row)))
                if pos >= len(support_rows) or int(support_rows[pos]) != int(row):
                    raise KeyError(row)
                return pos

            def map_original_rows(self, rows: Any) -> np.ndarray:
                values = np.asarray(rows)
                if values.ndim != 1 or values.dtype.kind not in "iu" or values.dtype.kind == "b":
                    raise ValueError("selected q rows must be a one-dimensional integer array")
                positions = np.searchsorted(support_rows, values)
                found = positions < len(support_rows)
                if np.any(found):
                    candidates = np.flatnonzero(found)
                    found[candidates] = support_rows[positions[candidates]] == values[candidates]
                if not np.all(found):
                    raise ValueError("selected q row is outside the admitted trace support")
                return np.asarray(positions, dtype=PETSc.IntType)

        compact_selected_rows = CompactSelectedRows()
        provider_owner = SimpleNamespace(
            full_rows=full_rows, active_rows=len(support_rows), appended_rows=1,
            trace_constraints=SimpleNamespace(
                original_to_active=compact_selected_rows,
                map_original_rows=compact_selected_rows.map_original_rows,
            ),
            cell_recovery_maps=(),
        )
        provider_audit: dict[str, Any] = {}
        def entry_factory():
            return iter_fullspace_dtn_functionals_from_surface(
                modes, assemblers, mpc, cfg, phase_gauge=BOUNDARY_PLANE,
                assembly_context=assembly_context, start_index=mode_index,
                stop_index=mode_index + 1, audit=provider_audit,
            )
        provider = P6GlobalDirectCarrierProvider(
            entry_factory, condensed=provider_owner, mode_count=1,
            interior_rows_are_managed=False, interior_rows=interior_rows,
            source_label="full_original_ny8_surface_functional_stream",
        )
        provider.bind_original_port_block(original_h, mode_indices=(mode_index,))
        candidate_b = np.zeros(len(support_rows), dtype=np.complex128)
        candidate_d = np.zeros(len(support_rows), dtype=np.complex128)
        tile_iterator = iter(provider.iter_reduced_direct_tiles())
        try:
            port, b_data, d_data = next(tile_iterator)
            if int(port) != 0 or b_data is None or d_data is None:
                raise ValueError("original-size direct provider omitted the selected B or D rows")
            br, bv, bp = b_data
            dr, dv, dp = d_data
            if not (
                np.array_equal(br, b_rows) and np.array_equal(bv, b_values)
                and np.array_equal(dr, d_rows) and np.array_equal(dv, d_values)
            ):
                raise ValueError("provider replay differs bitwise from frozen production B/D")
            if not np.array_equal(br, support_rows[bp]) or not np.array_equal(dr, support_rows[dp]):
                raise ValueError("provider active indices differ from original FE row identities")
            candidate_b[bp] = bv
            candidate_d[dp] = dv
            b_candidate_q = np.asarray(q_map.conj().T @ candidate_b, dtype=np.complex128)
            d_candidate_q = np.asarray(q_map.T @ candidate_d, dtype=np.complex128)
            # Release the borrowed current-mode payload before advancing the
            # provider generator, even though this bounded provider has one mode.
            del br, bv, bp, dr, dv, dp, b_data, d_data
            try:
                next(tile_iterator)
            except StopIteration:
                pass
            else:
                raise ValueError("one-mode original-size provider emitted an extra port")
        finally:
            tile_iterator.close()
            tile_iterator = None

        hp_global = float(original_h.diagonal[mode_index].real)
        scale = 1.0 / np.sqrt(hp_global)
        c_candidate = b_candidate_q * scale
        d_candidate = -scale * d_candidate_q
        c_oracle = b_oracle_q * scale
        d_oracle_q_scaled = -scale * d_oracle_q
        h_candidate = hp_global * scale * scale
        h_oracle = hp_value * scale * scale
        def relative_error(candidate: np.ndarray, oracle_value: np.ndarray) -> float:
            norm = float(np.linalg.norm(oracle_value))
            delta = float(np.linalg.norm(candidate - oracle_value))
            return (0.0 if delta == 0.0 else float("inf")) if norm == 0.0 else delta / norm
        errors = {
            "C_direct": relative_error(c_candidate, c_oracle),
            "minus_D_direct": relative_error(d_candidate, d_oracle_q_scaled),
            "H_original": abs(h_candidate - h_oracle) / abs(h_oracle) if h_oracle else float("inf"),
        }
        if any(value > 1.0e-11 for value in errors.values()) or not np.isclose(
            h_candidate, 1.0, rtol=1.0e-13, atol=1.0e-15
        ):
            raise ValueError(f"selected real q port tile failed independent projection: {errors}")
        selected_i = np.flatnonzero(
            (c_candidate != 0.0) | (d_candidate != 0.0)
            | (c_oracle != 0.0) | (d_oracle_q_scaled != 0.0)
        ).astype(np.int32, copy=False)
        if not len(selected_i):
            raise ValueError("selected q=0 port tile is an exact zero block under the frozen support gates")
        oracle_b_support = np.zeros_like(candidate_b)
        oracle_d_support = np.zeros_like(candidate_d)
        oracle_b_support[np.searchsorted(support_rows, b_rows)] = b_values
        oracle_d_support[np.searchsorted(support_rows, d_rows)] = d_values
        with projection_readback_path.open("wb") as stream:
            np.savez(
                stream,
                q_map_data=np.asarray(q_map.data, dtype="<c16"),
                q_map_indices=np.asarray(q_map.indices),
                q_map_indptr=np.asarray(q_map.indptr),
                q_map_shape=np.asarray(q_map.shape, dtype="<i8"),
                q_map_support_global_rows=np.asarray(support_rows, dtype="<i8"),
                selected_q_trace_rows=np.asarray(selected_i, dtype="<i8"),
                candidate_B_support=np.asarray(candidate_b, dtype="<c16"),
                oracle_B_support=np.asarray(oracle_b_support, dtype="<c16"),
                candidate_D_support=np.asarray(candidate_d, dtype="<c16"),
                oracle_D_support=np.asarray(oracle_d_support, dtype="<c16"),
                candidate_C_direct=np.asarray(c_candidate, dtype="<c16"),
                oracle_C_direct=np.asarray(c_oracle, dtype="<c16"),
                candidate_minus_D_direct=np.asarray(d_candidate, dtype="<c16"),
                oracle_minus_D_direct=np.asarray(d_oracle_q_scaled, dtype="<c16"),
                candidate_H_original=np.asarray([h_candidate], dtype="<f8"),
                oracle_H_original=np.asarray([h_oracle], dtype="<f8"),
                original_H_p=np.asarray([hp_value], dtype="<f8"),
                selected_mode_key_json=np.asarray(
                    json.dumps(list(expected_key), separators=(",", ":"))
                ),
            )
            stream.flush()
            os.fsync(stream.fileno())
        projection_readback_sha = _sha256_file(projection_readback_path)
        tile = {
            "row_global_q": 0,
            "column_global_q": 0,
            "q_port_alias_column": 0,
            "mode_key": list(expected_key),
            "mode_manifest_row": dict(mode_row),
            "I_trace_q_rows": selected_i.tolist(),
            "J_port_q_column": 0,
            "q_trace_map_shape": list(map(int, q_map.shape)),
            "q_trace_map_nnz": int(q_map.nnz),
            "q_trace_map_sha256": q_map_sha,
            "candidate_vs_independent_oracle_relative_errors": {**errors, "limit_each": 1.0e-11},
            "provider_B_D_bitwise_match_to_frozen_production": True,
            "provider_audit": dict(provider.audit),
            "selected_mapping_predecessor_count": len(predecessors),
            "selected_mapping_predecessors": predecessors,
            "contributions": {
                "C_direct": {
                    "status": "MEASURED_AND_INDEPENDENTLY_CHECKED",
                    "shape": [len(selected_i), 1], "I": selected_i.tolist(), "J": [0],
                    "values": [{"real": float(x.real), "imag": float(x.imag)} for x in c_candidate[selected_i]],
                    "relative_error": errors["C_direct"], "limit": 1.0e-11,
                    "candidate_values_sha256": _array_sha256(c_candidate[selected_i]),
                    "oracle_values_sha256": _array_sha256(c_oracle[selected_i]),
                    "oracle_values": [
                        {"real": float(x.real), "imag": float(x.imag)}
                        for x in c_oracle[selected_i]
                    ],
                },
                "minus_D_direct": {
                    "status": "MEASURED_AND_INDEPENDENTLY_CHECKED",
                    "shape": [1, len(selected_i)], "I": [0], "J": selected_i.tolist(),
                    "values": [{"real": float(x.real), "imag": float(x.imag)} for x in d_candidate[selected_i]],
                    "relative_error": errors["minus_D_direct"], "limit": 1.0e-11,
                    "candidate_values_sha256": _array_sha256(d_candidate[selected_i]),
                    "oracle_values_sha256": _array_sha256(d_oracle_q_scaled[selected_i]),
                    "oracle_values": [
                        {"real": float(x.real), "imag": float(x.imag)}
                        for x in d_oracle_q_scaled[selected_i]
                    ],
                },
                "H_original": {
                    "status": "MEASURED_AND_INDEPENDENTLY_CHECKED",
                    "shape": [1, 1], "I": [0], "J": [0], "value": {"real": h_candidate, "imag": 0.0},
                    "relative_error": errors["H_original"], "limit": 1.0e-11,
                    "candidate_values_sha256": _array_sha256(np.asarray([h_candidate], dtype=np.float64)),
                    "oracle_values_sha256": _array_sha256(np.asarray([h_oracle], dtype=np.float64)),
                    "oracle_value": {"real": h_oracle, "imag": 0.0},
                },
                "volume": {"status": "PARTIAL_NOT_RUN", "scope": "local trace-trace Schur block and Kcond"},
                "local_interior_schur_correction": {"status": "NOT_RUN", "reason": "no local inverse or callback was built"},
            },
            "production_functional_scope": {
                "selected_side": str(mode.side),
                "complete_side_facets": len(actual_bounds[str(mode.side)]),
                "expected_side_facets": _EXPECTED_FACETS_BY_SIDE[str(mode.side)],
                "global_MPC_and_both_global_support_filters": True,
                "oracle_stream_audit": dict(oracle_audit),
                "candidate_provider_stream_audit": dict(provider_audit),
            },
            "frozen_B_D_H_oracle": {
                "artifact_path": oracle_path.name, "artifact_sha256": oracle_sha,
                "B_rows": len(b_rows), "D_rows": len(d_rows), "H_p": hp_value,
                "B_values_sha256": _array_sha256(b_values),
                "D_values_sha256": _array_sha256(d_values),
            },
            "full_q_matrices": "0/8",
            "volume_qualification": "PARTIAL_NOT_RUN",
        }
        result.update(
            status="PASS_REAL_ORIGINAL_NY8_Q_PORT_TILE",
            selected_q_port_tile_built=True,
            q_tile=tile,
            q_tile_sha256=hashlib.sha256(
                json.dumps(tile, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            production_oracle_artifact_path=oracle_path.name,
            production_oracle_artifact_sha256=oracle_sha,
            q_projection_readback_artifact={
                "artifact_path": projection_readback_path.name,
                "artifact_sha256": projection_readback_sha,
                "q_trace_map_shape": list(map(int, q_map.shape)),
                "q_trace_map_nnz": int(q_map.nnz),
                "q_trace_map_sha256": q_map_sha,
                "selected_q_trace_rows_sha256": _array_sha256(selected_i),
                "purpose": "finite q-map CSR and candidate/oracle C,-D,H values for independent readback",
            },
            complete_q_matrices="0/8",
            volume_qualification="PARTIAL_NOT_RUN",
        )
        campaign_after = _read_v22_campaign_state(root)
        if campaign_after["campaign_window_sha256"] != campaign_before["campaign_window_sha256"]:
            raise ValueError("fixed execution campaign identity changed during selected original q tile")
        result["campaign_after"] = {
            "window_sha256": campaign_after["campaign_window_sha256"],
            "remaining_numerical_seconds": campaign_after["remaining_numerical_seconds"],
        }
    except _ProbeResourceBlocked as error:
        result.update(status="NOT_RUN_RESOURCE_GATE", resource_blocker=error.facts, failure_message=None)
    except Exception as error:
        result.update(status="FAILED", failure_type=type(error).__name__,
                      failure_message=f"{type(error).__name__}: {error}")
    finally:
        provider = tile_iterator = q_map = None
        result["resource_gates"] = resource_gates
        result["resource_after_q_tile"] = _memory_snapshot(resource_sample)
        result["elapsed_wall_seconds"] = perf_counter() - started
        result["elapsed_process_cpu_seconds"] = process_time() - cpu_started
        result["artifact_path"] = output_path.name
        _write_json(output_path, result)
        result["artifact_sha256"] = _sha256_file(output_path)
    return result


def _v23_actual_axis_values(resolved: Mapping[str, Any]) -> dict[str, Any]:
    """Return coordinate vectors; geometry inventory ``actual_axes`` are cell counts."""

    discretization = resolved.get("discretization")
    if not isinstance(discretization, Mapping):
        raise ValueError("resolved input omitted the V23 actual mesh-axis coordinate vectors")
    values = {
        axis: discretization.get(f"mesh_axis_{axis}_values")
        for axis in ("x", "y", "z")
    }
    if any(value is None for value in values.values()):
        raise ValueError("resolved input omitted one or more V23 mesh-axis coordinate vectors")
    return values


def _run_probe(
    resolved: Mapping[str, Any],
    output_directory: Path,
    *,
    preflight: Mapping[str, Any],
    modes: Sequence[Any],
    mode_rows: Sequence[Mapping[str, Any]],
    resource_sample: Callable[[], Mapping[str, Any]],
) -> dict[str, Any]:
    from basix.ufl import element
    from dolfinx import default_real_type, fem
    from dolfinx.io import XDMFFile
    from mpi4py import MPI
    from petsc4py import PETSc

    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.geometry.mesh_builder_3d import _mark_boundary_facets, _mark_cells
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.solvers.directional_boundary import FacetPolynomial
    from src.solvers.dtn_boundary_phase_gauge import (
        BOUNDARY_PLANE,
        assembly_projection_denominator,
    )
    from src.solvers.dtn_port_3d import (
        _combine_owned_entries,
        _dtn_surface_quadrature_degree,
        _traction_vector,
    )
    from src.solvers.fullspace_dtn_action import iter_fullspace_dtn_functionals_from_surface
    from src.solvers.p6_cell_condensed_action import P6GeneratedCellPortAction
    from src.solvers.task40_v20_mode_inventory import TARGET_MODE_PHYSICAL_IDENTITY_SHA256

    root = Path(__file__).resolve().parents[2]
    completed: list[str] = []
    attempted: list[str] = []
    facts: dict[str, Any] = {
        "schema": "task40extra.review_v22_target_operator_probe.v1",
        "status": "NOT_RUN",
        "official_result": False,
        "run_id": preflight.get("run_id"),
        "source_sha": preflight.get("source_sha"),
        "input_sha256": preflight.get("input_sha256"),
        "physical_model_sha256": preflight.get("physical_model_sha256"),
        "mode_manifest_sha256": (
            preflight.get("target_mode_inventory", {}).get("mode_manifest_sha256")
            if isinstance(preflight.get("target_mode_inventory"), Mapping)
            else None
        ),
        "attempted_stages": attempted,
        "completed_stages": completed,
        "partial_stages": [],
        "failed_stage": None,
        "expected_q_count": 8,
        "built_q_count": 0,
        "q_csr_created": False,
        "factor_created": False,
        "ksp_created": False,
        "pde_solved": False,
        "official_R_T_A_created": False,
        "official_result": False,
    }
    resource_gates: list[dict[str, Any]] = []
    current_stage: str | None = None
    field = field_values = selected_field_values = None
    mesh_object = space = mpc_data = mpc = None
    mesh_data = cell_tags = facet_tags = boundary_facets = None
    assemblers = context = native_rule = cfg = mapping = mapping_rows = None
    operator_iterator = functional = None
    b_action = d_values = h_values = None
    polynomial = permutation_info = dof_index_map = None
    geometry_facts = None
    v23_q_tile_facts: dict[str, Any] | None = None
    mpc_expansions = native_quadrature_identity = generated_packet_witness = None
    try:
        current_stage = "geometry_inventory"
        attempted.append(current_stage)
        campaign_state_entry = _read_v22_campaign_state(root)
        from src.runners.task40_v10_campaign import (
            TASK40_V23_CAMPAIGN_SHA256,
            TASK40_V24_CAMPAIGN_SHA256,
        )

        is_v23_campaign = (
            campaign_state_entry["campaign_window_sha256"] == TASK40_V23_CAMPAIGN_SHA256
        )
        is_v24_campaign = (
            campaign_state_entry["campaign_window_sha256"] == TASK40_V24_CAMPAIGN_SHA256
        )
        if is_v23_campaign:
            facts["schema"] = "task40extra.review_v23_compact_boundary_operator_probe.v1"
            facts["q_coverage"] = _v23_q_coverage_record({"status": "NOT_RUN"})
        elif is_v24_campaign:
            facts["schema"] = "task40extra.review_v24_compact_boundary_operator_probe.v1"
            facts["q_coverage"] = _v23_q_coverage_record({"status": "NOT_RUN"})
        facts["campaign_window"] = {
            "campaign_version": (
                "V24" if is_v24_campaign else "V23" if is_v23_campaign else "V22"
            ),
            "window_sha256": campaign_state_entry["campaign_window_sha256"],
            "read_only": True,
            "remaining_numerical_seconds_at_probe_entry": campaign_state_entry[
                "remaining_numerical_seconds"
            ],
            "accounting_path": campaign_state_entry["path"],
        }
        if campaign_state_entry["remaining_numerical_seconds"] <= 0.0:
            raise _ProbeResourceBlocked(
                "geometry_inventory",
                {
                    "gate_type": "fixed_campaign_time_cooperative_stop",
                    "remaining_numerical_seconds": 0.0,
                    "source": "read_campaign_state read-only fixed execution window",
                },
            )
        geometry_path = root / _GEOMETRY_RELATIVE
        xdmf_path = root / _XDMF_RELATIVE
        h5_path = root / _H5_RELATIVE
        _copy_verified(
            geometry_path,
            output_directory / "v20_geometry_inventory.json",
            _GEOMETRY_SHA256,
        )
        geometry_facts = json.loads(geometry_path.read_text(encoding="utf-8"))
        if (
            geometry_facts.get("schema")
            != "task40extra.review_v20_original_geometry_inventory.v1"
            or geometry_facts.get("status") != "PASS"
            or geometry_facts.get("mesh_id") != "TARGET_ORIGINAL_NY8"
            or geometry_facts.get("actual_cell_count") != 30_464
        ):
            raise ValueError("saved V20 original-size geometry inventory is not the verified Ny8 source")
        mapping, mapping_identity = _load_verified_mapping(root)
        mapping_rows = mapping["facet_mappings"]
        for relative, expected in (
            (_XDMF_RELATIVE, _XDMF_SHA256),
            (_H5_RELATIVE, _H5_SHA256),
        ):
            path = root / relative
            if not path.is_file() or _sha256_file(path) != expected:
                raise ValueError(f"saved V20 XDMF/HDF5 identity changed: {path.name}")
        provenance = resolved.get("provenance", {})
        mode_inventory = preflight.get("target_mode_inventory")
        _validate_v22_physical_identity_bindings(
            preflight=preflight,
            resolved=resolved,
            expected_mode_identity=_MODE_PHYSICAL_SHA256,
        )
        if (
            TARGET_MODE_PHYSICAL_IDENTITY_SHA256 != _MODE_PHYSICAL_SHA256
        ):
            raise ValueError("installed and frozen target-mode physical identities differ")
        if (
            not isinstance(mode_inventory, Mapping)
            or len(mode_rows) != 32_060
            or len(modes) != 32_060
            or mode_inventory.get("mode_count") != 32_060
            or mode_inventory.get("side_counts") != {"bottom": 16_030, "top": 16_030}
            or not isinstance(mode_inventory.get("mode_manifest_sha256"), str)
            or not isinstance(mode_inventory.get("ordered_mode_key_sha256"), str)
        ):
            raise ValueError("preflight did not bind the complete frozen 32,060-mode table")

        resource_gates.append(
            _resource_admission(
                "saved_mesh_readback",
                128 * 2**20,
                resource_sample=resource_sample,
                require_task_cgroup=False,
            )
        )
        cfg = simulation_config_3d_from_normalized(resolved)
        with XDMFFile(MPI.COMM_SELF, str(xdmf_path), "r") as xdmf:
            mesh_object = xdmf.read_mesh(name=cfg.case_name)
        facet_tags, boundary_facets = _mark_boundary_facets(mesh_object, cfg)
        cell_tags = _mark_cells(mesh_object, cfg)
        mesh_data = SimpleNamespace(
            mesh=mesh_object,
            cell_tags=cell_tags,
            facet_tags=facet_tags,
            rectangular_air_void_audit=None,
        )
        mapping_validation = _verify_saved_mesh_mapping(
            mesh_object, mesh_data, mapping_rows, cfg
        )
        geometry_facts = {
            "schema": geometry_facts["schema"],
            "status": geometry_facts["status"],
            "mesh_id": geometry_facts["mesh_id"],
            "actual_axes": geometry_facts["actual_axes"],
            "actual_cell_count": geometry_facts["actual_cell_count"],
            "artifact_sha256": _GEOMETRY_SHA256,
            "saved_mesh": {
                "xdmf_sha256": _XDMF_SHA256,
                "h5_sha256": _H5_SHA256,
            },
            "boundary_mapping": mapping_identity,
            "actual_mesh_mapping_validation": mapping_validation,
            "global_FE_or_MPC_created": False,
        }
        facts["geometry_inventory"] = geometry_facts
        facts["geometry_mapping_validation"] = mapping_validation
        facts["boundary_mapping_identity"] = mapping_identity
        completed.append("geometry_inventory")

        current_stage = "target_operator_probe"
        attempted.append(current_stage)
        resource_gates.append(
            _resource_admission(
                "p6_space_creation",
                1536 * 2**20,
                resource_sample=resource_sample,
                require_task_cgroup=True,
            )
        )
        space = fem.functionspace(
            mesh_object,
            element("N1curl", mesh_object.basix_cell(), 6, dtype=default_real_type),
        )
        if int(space.element.space_dimension) != 882:
            raise ValueError("actual p6 hexahedral cell dimension is not 882")
        dof_index_map = space.dofmap.index_map
        full_rows = int(dof_index_map.size_global)
        if full_rows != _EXPECTED_FULL_ROWS:
            raise ValueError(f"actual p6 global storage rows changed: {full_rows}")

        resource_gates.append(
            _resource_admission(
                "double_floquet_mpc_creation",
                1024 * 2**20,
                resource_sample=resource_sample,
                require_task_cgroup=True,
            )
        )
        mpc_data = build_double_floquet_mpc(space, mesh_data, cfg)
        mpc = mpc_data.mpc
        slaves_local = np.asarray(mpc.slaves, dtype=np.int32)
        local_owned = int(dof_index_map.size_local)
        owned_slaves = slaves_local[slaves_local < local_owned]
        slave_rows = np.asarray(
            dof_index_map.local_to_global(owned_slaves), dtype=PETSc.IntType
        )
        independent_rows = full_rows - int(len(slave_rows))
        if independent_rows != _EXPECTED_INDEPENDENT_ROWS:
            raise ValueError(
                f"actual p6/MPC independent rows changed: {independent_rows}"
            )
        coefficients, offsets = mpc.coefficients()
        mpc_identity = {
            "global_storage_rows": full_rows,
            "global_independent_rows": independent_rows,
            "owned_slave_count": int(len(slave_rows)),
            "slave_rows_sha256": _array_sha256(slave_rows),
            "master_local_indices_sha256": _array_sha256(mpc.masters.array),
            "coefficients_sha256": _array_sha256(coefficients),
            "offsets_sha256": _array_sha256(offsets),
            "coefficient_count": int(len(coefficients)),
            "offset_count": int(len(offsets)),
            "constraint_mode": str(
                getattr(mpc_data, "constraint_mode_resolved", "qualified_double_floquet")
            ),
            "mpc_finalized": True,
        }
        cell_dof_digest = hashlib.sha256()
        boundary_cell_dof_digest = hashlib.sha256()
        boundary_dof_count_by_side = {"bottom": 0, "top": 0}
        unique_boundary_dofs_by_side: dict[str, set[int]] = {
            "bottom": set(),
            "top": set(),
        }
        boundary_cell_global_dofs: dict[int, np.ndarray] = {}
        boundary_cell_side: dict[int, str] = {}
        mapped_cell_ids = sorted({int(row["cell_id"]) for row in mapping_rows})
        mapped_cell_id_set = set(mapped_cell_ids)
        for cell_id in range(int(mesh_object.topology.index_map(3).size_local)):
            local_dofs = np.asarray(space.dofmap.cell_dofs(cell_id), dtype=np.int32)
            global_dofs = np.asarray(
                dof_index_map.local_to_global(local_dofs), dtype=PETSc.IntType
            )
            if len(local_dofs) != 882:
                raise ValueError(f"actual cell {cell_id} p6 dofmap length is not 882")
            cell_dof_digest.update(np.asarray([cell_id], dtype="<i8").tobytes())
            cell_dof_digest.update(np.ascontiguousarray(global_dofs).tobytes())
            if cell_id in mapped_cell_id_set:
                boundary_cell_dof_digest.update(
                    np.asarray([cell_id], dtype="<i8").tobytes()
                )
                boundary_cell_dof_digest.update(
                    np.ascontiguousarray(global_dofs).tobytes()
                )
            del local_dofs, global_dofs
        mesh_object.topology.create_connectivity(2, 3)
        interior_positions = np.asarray(
            space.element.basix_element.entity_dofs[3][0], dtype=np.int32
        )
        if len(interior_positions) != 450:
            raise ValueError("actual p6 Basix cell-interior row inventory changed")
        trace_positions = np.setdiff1d(
            np.arange(882, dtype=np.int32), interior_positions, assume_unique=False
        )
        mesh_object.topology.create_connectivity(3, 2)
        cell_to_facet = mesh_object.topology.connectivity(3, 2)
        facet_entity_closure_dofs = space.element.basix_element.entity_closure_dofs[2]
        for row in mapping_rows:
            cell_id = int(row["cell_id"])
            side = str(row["side"])
            local_dofs = np.asarray(space.dofmap.cell_dofs(cell_id), dtype=np.int32)
            global_dofs = np.asarray(
                dof_index_map.local_to_global(local_dofs), dtype=PETSc.IntType
            )
            previous = boundary_cell_global_dofs.setdefault(cell_id, global_dofs.copy())
            if not np.array_equal(previous, global_dofs):
                raise ValueError("one boundary cell produced inconsistent global dofmaps")
            previous_side = boundary_cell_side.setdefault(cell_id, side)
            if previous_side != side:
                raise ValueError("one boundary-adjacent cell maps to both physical port sides")
            boundary_dof_count_by_side[side] += int(len(global_dofs))
            unique_boundary_dofs_by_side[side].update(map(int, global_dofs))
            boundary_cell_dof_digest.update(
                np.asarray([int(row["facet_id"]), cell_id], dtype="<i8").tobytes()
            )
            del local_dofs, global_dofs
        cell_ids_sorted = np.asarray(sorted(boundary_cell_side), dtype=np.int64)
        cell_sides_sorted = np.asarray(
            [boundary_cell_side[int(cell_id)] for cell_id in cell_ids_sorted],
            dtype="U6",
        )
        side_cell_positions = {
            side: np.flatnonzero(cell_sides_sorted == side)
            for side in ("bottom", "top")
        }
        actual_port_face_rows = _mapped_port_face_global_rows(
            mapping_rows,
            cell_to_facet,
            boundary_cell_global_dofs,
            facet_entity_closure_dofs,
        )
        boundary_global_rows = sorted(
            unique_boundary_dofs_by_side["bottom"]
            | unique_boundary_dofs_by_side["top"]
        )
        mpc_expansions = _global_mpc_expansions(
            mpc, dof_index_map, boundary_global_rows
        )
        boundary_rows_array = np.asarray(boundary_global_rows, dtype=np.int64)
        interior_pairs = [
            (int(global_row), int(cell_id))
            for cell_id, global_dofs in boundary_cell_global_dofs.items()
            for global_row in global_dofs[interior_positions]
        ]
        interior_pairs.sort(key=lambda row_cell: row_cell[0])
        interior_rows_sorted = np.asarray(
            [row for row, _cell_id in interior_pairs], dtype=np.int64
        )
        interior_cell_ids_sorted = np.asarray(
            [cell_id for _row, cell_id in interior_pairs], dtype=np.int64
        )
        if len(np.unique(interior_rows_sorted)) != len(interior_rows_sorted):
            raise ValueError("boundary cell interior rows are not unique global DoFs")
        interior_row_set = set(map(int, interior_rows_sorted))
        actual_port_face_rows.difference_update(interior_row_set)
        other_trace_rows = set(boundary_global_rows) - interior_row_set - actual_port_face_rows
        support_category_rows = {
            "interior": interior_rows_sorted,
            "actual_port_face_trace": np.asarray(sorted(actual_port_face_rows), dtype=np.int64),
            "other_trace": np.asarray(sorted(other_trace_rows), dtype=np.int64),
        }
        expansion_digest = hashlib.sha256()
        for slave, (masters, coefficients_for_row) in sorted(mpc_expansions.items()):
            expansion_digest.update(np.asarray([slave], dtype="<i8").tobytes())
            expansion_digest.update(np.asarray(masters, dtype="<i8").tobytes())
            expansion_digest.update(np.asarray(coefficients_for_row, dtype="<c16").tobytes())
        descriptor_identity = {
            "schema": "task40extra.review_v22_target_boundary_descriptor.v1",
            "canonical_preflight_input": str(provenance.get("source_path", "UNKNOWN")),
            "staged_input_sha256": preflight.get("input_sha256"),
            "physical_model_sha256": preflight.get("physical_model_sha256"),
            "mode_physical_identity_sha256": _MODE_PHYSICAL_SHA256,
            "mode_manifest_sha256": mode_inventory.get("mode_manifest_sha256"),
            "ordered_mode_key_sha256": mode_inventory.get("ordered_mode_key_sha256"),
            "gauge": BOUNDARY_PLANE,
            "saved_mesh_xdmf_sha256": _XDMF_SHA256,
            "saved_mesh_h5_sha256": _H5_SHA256,
            "saved_boundary_mapping_sha256": _MAPPING_FILE_SHA256,
            "saved_boundary_mapping_digest": _MAPPING_DIGEST,
            "actual_cell_dofmap_sha256": cell_dof_digest.hexdigest(),
            "mapped_boundary_cell_dof_sha256": boundary_cell_dof_digest.hexdigest(),
            "mapped_boundary_local_rows_per_facet": 882,
            "mapped_boundary_unique_global_dofs_by_side": {
                side: len(values) for side, values in unique_boundary_dofs_by_side.items()
            },
            "mapped_boundary_cell_dof_rows_by_side": boundary_dof_count_by_side,
            "p6_local_partition": {"interior_rows": 450, "trace_rows": 432},
            "global_mpc_identity": mpc_identity,
            "boundary_mpc_dual_pullback": {
                "target_global_row_count": len(boundary_global_rows),
                "selected_slave_expansion_count": len(mpc_expansions),
                "selected_expansion_sha256": expansion_digest.hexdigest(),
                "coefficient_action": "E^H on actual finalized global Floquet MPC rows",
            },
            "production_support_semantics": {
                "component_stage": "_vec_nonzero_owned_entries after MPC assembly; global relative_tol=1e-13 and absolute_floor=0.0",
                "combined_stage": "_combine_owned_entries after weighted component merge; global relative_tol=1e-13 and absolute_floor=0.0",
                "tiny_entries": "retained by local raw descriptor; production iterator applies both global stages",
            },
            "scope": "actual geometry/facet/cell/class, p6 dofmap and global Floquet MPC; all 32,060 global functionals are streamed one at a time",
        }
        facts["p6_space"] = {
            "cell_count": int(mesh_object.topology.index_map(3).size_local),
            "cell_dof_dimension": int(space.element.space_dimension),
            "global_storage_rows": full_rows,
            "global_independent_rows": independent_rows,
            "interior_rows_per_cell": int(len(interior_positions)),
            "trace_rows_per_cell": int(len(trace_positions)),
        }
        facts["descriptor"] = descriptor_identity
        facts["mode_coverage_target"] = {
            "expected_mode_count": 32_060,
            "expected_by_side": {"bottom": 16_030, "top": 16_030},
            "expected_boundary_facets_by_side": _EXPECTED_FACETS_BY_SIDE,
            "potential_side_specific_mode_facet_pairs": 69_762_560,
            "support_by_cell_and_sum_m_c_squared": "COMPACT_CELL_INVENTORY_PENDING_MODE_SWEEP",
        }

        resource_gates.append(
            _resource_admission(
                "native_boundary_rule_and_gauge_context",
                1024 * 2**20,
                resource_sample=resource_sample,
                require_task_cgroup=True,
            )
        )
        qdegree = _dtn_surface_quadrature_degree(cfg, list(modes))
        native_quadrature_identity = _native_quadrature_identity(qdegree)
        polynomial = FacetPolynomial(space.element.basix_element)
        permutation_info = np.asarray(mesh_object.topology.get_cell_permutation_info())
        if permutation_info.shape != (30_464,):
            raise ValueError("actual target hexahedral permutation inventory changed")
        candidate_upper_rows = (
            len(mapped_cell_ids) * int(space.element.space_dimension)
            + sum(len(masters) for masters, _coefficients in mpc_expansions.values())
        )
        candidate_upper_bytes = candidate_upper_rows * (
            np.dtype(PETSc.IntType).itemsize
            + np.dtype(np.complex128).itemsize * 2
            + np.dtype(np.int64).itemsize
        )
        resource_gates.append(
            _resource_admission(
                "compact_boundary_rows_mpc_closure_and_action_arrays",
                candidate_upper_bytes,
                resource_sample=resource_sample,
                require_task_cgroup=True,
            )
        )
        native_rule = _V22NativeFacetRule(
            space=space,
            dof_index_map=dof_index_map,
            mapping_rows=mapping_rows,
            permutation_info=permutation_info,
            polynomial=polynomial,
            quadrature_degree=qdegree,
            cfg=cfg,
            mpc_expansions=mpc_expansions,
            rolling_filter_digest=is_v23_campaign,
        )
        assemblers = native_rule.assemblers()
        context = _build_v22_native_gauge_context(
            space=space,
            mesh_data=mesh_data,
            mpc=mpc,
            cfg=cfg,
            quadrature_identity=native_quadrature_identity,
            permutation_info=permutation_info,
            cell_dofmap_sha256=cell_dof_digest.hexdigest(),
        )
        facts["native_surface_quadrature_identity"] = native_quadrature_identity
        facts["compact_boundary_domain"] = {
            "status": "PASS_COMPLETE_BOUNDARY_CELL_UNION_AND_GLOBAL_MPC_MASTER_CLOSURE",
            "candidate_global_row_count": int(len(native_rule.candidate_rows)),
            "candidate_global_rows_sha256": _array_sha256(native_rule.candidate_rows),
            "full_global_storage_rows": int(full_rows),
            "candidate_fraction_of_global_rows": float(len(native_rule.candidate_rows) / full_rows),
            "cell_dof_order_preserved": True,
            "global_mpc_master_order_preserved": True,
            "filter_scope_includes_all_possible_nonzero_rows": True,
            "inventory_cell_count_by_side": {
                side: int(len(side_cell_positions[side])) for side in ("bottom", "top")
            },
            "row_categories": {
                name: int(len(rows)) for name, rows in support_category_rows.items()
            },
        }
        support_category_rows["slave"] = np.unique(
            np.asarray(native_rule._slave_rows, dtype=np.int64)
        )
        support_category_rows["unknown"] = np.setdiff1d(
            np.asarray(native_rule.candidate_rows, dtype=np.int64),
            boundary_rows_array,
            assume_unique=True,
        )
        expected_mode_counts_by_side = {
            side: sum(str(mode.side) == side for mode in modes)
            for side in ("bottom", "top")
        }
        m_c_state = {
            side: {
                metric: {
                    "per_cell_mode_counts": np.zeros(
                        len(side_cell_positions[side]), dtype=np.int64
                    ),
                    "per_cell_interior_row_memberships": np.zeros(
                        len(side_cell_positions[side]), dtype=np.int64
                    ),
                }
                for metric in ("B", "D", "union")
            }
            for side in ("bottom", "top")
        }
        support_category_totals = {
            side: {
                component: {
                    category: 0
                    for category in (
                        "interior",
                        "actual_port_face_trace",
                        "other_trace",
                        "slave",
                        "unknown",
                    )
                }
                for component in ("B", "D")
            }
            for side in ("bottom", "top")
        }
        facts["native_surface_adapter"] = {
            "status": "QUALIFIED_AXIS_ALIGNED_AFFINE_CLASS_RULE",
            "geometry_class_count": len(
                {str(row["class_id"]) for row in mapping_rows}
            ),
            "geometry_class_ids_by_side": {
                side: list(native_rule.class_ids_by_side[side])
                for side in ("bottom", "top")
            },
            "facet_count_by_side": {
                side: sum(
                    native_rule._class_facets_by_side[side].values()
                )
                for side in ("bottom", "top")
            },
            "actual_p6_orientation_transform": bool(space.element.needs_dof_transformations),
            "actual_mpc_expansion_count": len(mpc_expansions),
            "first_component_filter": {
                "stage": "global owned component vector after MPC dual pullback",
                "relative_tol": 1e-13,
                "absolute_floor": 0.0,
            },
            "ffcx_surface_forms_compiled": False,
        }

        representative_indices = _compact_reference_mode_indices(modes)
        full_reference_bytes = full_rows * (
            np.dtype(np.complex128).itemsize + np.dtype(np.float64).itemsize
        )
        resource_gates.append(
            _resource_admission(
                "bounded_compact_vs_legacy_full_domain_equivalence",
                full_reference_bytes,
                resource_sample=resource_sample,
                require_task_cgroup=True,
            )
        )
        compact_equivalence_checks: list[dict[str, Any]] = []
        h_values = np.asarray(
            [
                assembly_projection_denominator(mode, cfg, BOUNDARY_PLANE)
                for mode in modes
            ],
            dtype=np.float64,
        )
        v23_q_tile_facts: dict[str, Any] | None = None
        q_only_scan_directory = os.environ.get("TASK40_V23_Q_ONLY_SCAN_RUN_DIR")
        if q_only_scan_directory is not None:
            if not (is_v23_campaign or is_v24_campaign):
                raise ValueError("V23 q-only supplement requires the registered V23 or V24 execution window")
            expected_old_source = "1291aeef089e6c02c4b9e28125f60072aa769340"
            expected_old_window_path = (
                root
                / "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v23_wsl/campaign_window_v23.json"
            ).resolve()
            expected_old_accounting_path = expected_old_window_path.with_name(
                "campaign_accounting_v10.jsonl"
            )
            scan_directory = Path(q_only_scan_directory).resolve()
            scan_manifest_path = scan_directory / "run_manifest.json"
            scan_manifest = json.loads(scan_manifest_path.read_text(encoding="utf-8"))
            scan_campaign = scan_manifest.get("task40_v20_campaign", {})
            if (
                scan_manifest.get("source_sha") != expected_old_source
                or scan_manifest.get("input_sha256") != preflight.get("input_sha256")
                or scan_manifest.get("physical_model_sha256")
                != preflight.get("physical_model_sha256")
                or scan_campaign.get("window_sha256") != TASK40_V23_CAMPAIGN_SHA256
                or Path(str(scan_campaign.get("window_path", ""))).resolve()
                != expected_old_window_path
                or Path(str(scan_campaign.get("accounting_path", ""))).resolve()
                != expected_old_accounting_path
                or os.environ.get("TASK40_V23_Q_ONLY_SCAN_WINDOW_SHA256")
                != TASK40_V23_CAMPAIGN_SHA256
                or _sha256_file(scan_manifest_path)
                != os.environ.get("TASK40_V23_Q_ONLY_SCAN_MANIFEST_SHA256")
            ):
                raise ValueError("old V23 scan source/input/model/window/manifest identity differs")
            scan_output = Path(
                os.environ["TASK40_V23_Q_ONLY_SCAN_NUMERICAL_OUTPUT"]
            ).resolve()
            scan_preflight_path = Path(os.environ["TASK40_V23_Q_ONLY_SCAN_PREFLIGHT"]).resolve()
            scan_witness_path = Path(os.environ["TASK40_V23_Q_ONLY_SCAN_WITNESS"]).resolve()
            old_q_failure_path = Path(os.environ["TASK40_V23_Q_ONLY_OLD_Q_FAILURE"]).resolve()
            checkpoint_metadata_path = Path(
                os.environ["TASK40_V23_Q_ONLY_CHECKPOINT_METADATA"]
            ).resolve()
            checkpoint_payload_path = Path(
                os.environ["TASK40_V23_Q_ONLY_CHECKPOINT_PAYLOAD"]
            ).resolve()
            old_probe_path = scan_output / "v22_target_operator_probe.json"
            old_probe = json.loads(old_probe_path.read_text(encoding="utf-8"))
            old_q_failure = json.loads(old_q_failure_path.read_text(encoding="utf-8"))
            old_preflight = json.loads(scan_preflight_path.read_text(encoding="utf-8"))
            old_witness = json.loads(scan_witness_path.read_text(encoding="utf-8"))
            checkpoint = json.loads(checkpoint_metadata_path.read_text(encoding="utf-8"))
            payload_record = checkpoint.get("actual_action_payload", {})
            if (
                old_probe.get("status") != "FAILED_SELECTED_Q_PORT_TILE"
                or old_q_failure.get("status") != "FAILED"
                or old_q_failure.get("failure_type") != "TypeError"
                or "list indices" not in str(old_q_failure.get("failure_message", ""))
                or _sha256_file(old_q_failure_path)
                != os.environ.get("TASK40_V23_Q_ONLY_OLD_Q_FAILURE_SHA256")
                or _sha256_file(checkpoint_metadata_path)
                != os.environ.get("TASK40_V23_Q_ONLY_CHECKPOINT_METADATA_SHA256")
                or checkpoint.get("source_sha") != expected_old_source
                or checkpoint.get("completed_mode_count") != len(modes)
                or checkpoint.get("mode_count_by_side")
                != {"bottom": 16_030, "top": 16_030}
                or old_preflight.get("source_sha") != expected_old_source
                or old_witness.get("source_sha") != expected_old_source
                or old_witness.get("input_sha256") != preflight.get("input_sha256")
                or old_witness.get("physical_model_sha256")
                != preflight.get("physical_model_sha256")
                or old_witness.get("mode_manifest_sha256")
                != mode_inventory.get("mode_manifest_sha256")
                or old_witness.get("ordered_mode_key_sha256")
                != mode_inventory.get("ordered_mode_key_sha256")
                or old_witness.get("actual_p6_space") != facts.get("p6_space")
                or old_witness.get("actual_global_mpc_identity") != mpc_identity
                or old_witness.get("boundary_mpc_dual_pullback")
                != descriptor_identity["boundary_mpc_dual_pullback"]
                or checkpoint != old_probe.get("latest_mode_checkpoint")
                or not checkpoint_payload_path.is_file()
                or checkpoint_payload_path.parent != checkpoint_metadata_path.parent
                or _sha256_file(checkpoint_payload_path)
                != payload_record.get("sha256")
                or payload_record.get("sha256")
                != os.environ.get("TASK40_V23_Q_ONLY_CHECKPOINT_PAYLOAD_SHA256")
            ):
                raise ValueError("old V23 terminal q failure/checkpoint or FE/MPC/H identity changed")
            old_preflight = dict(old_preflight)
            old_preflight["source_sha"] = expected_old_source
            restored = _load_v23_action_checkpoint(
                checkpoint_metadata_path.parent,
                preflight=old_preflight,
                mode_inventory=mode_inventory,
                campaign_window_sha256=TASK40_V23_CAMPAIGN_SHA256,
                candidate_rows=native_rule.candidate_rows,
                modes=modes,
                h_values=h_values,
                side_cell_counts={
                    side: len(side_cell_positions[side]) for side in ("bottom", "top")
                },
                expected_field_sha256=str(
                    checkpoint.get("restart_state", {}).get("field_sha256", "")
                ),
            )
            if restored is None or restored.get("mode_count") != len(modes):
                raise ValueError("old V23 checkpoint failed complete-prefix validation")
            old_field_sha256 = checkpoint["restart_state"]["field_sha256"]
            del restored
            axes_values = _v23_actual_axis_values(resolved)
            v23_q_tile_facts = _run_v23_original_ny8_q_port_tile(
                root,
                output_directory,
                preflight=preflight,
                modes=modes,
                mode_rows=mode_rows,
                space=space,
                mpc=mpc,
                cfg=cfg,
                assemblers=assemblers,
                assembly_context=context,
                axes_values=axes_values,
                mapping_rows=mapping_rows,
                boundary_global_rows=boundary_global_rows,
                interior_rows=interior_rows_sorted,
                h_values=h_values,
                resource_sample=resource_sample,
            )
            facts["v23_selected_q_port_tile"] = v23_q_tile_facts
            facts["q_coverage"] = _v23_q_coverage_record(v23_q_tile_facts)
            supplement = {
                "schema": "task40extra.review_v23_q_only_supplement.v1",
                "status": "PASS_Q_TILE_ONLY" if v23_q_tile_facts.get("status") == "PASS_REAL_ORIGINAL_NY8_Q_PORT_TILE" else v23_q_tile_facts.get("status"),
                "patched_q_source_sha": preflight.get("source_sha"),
                "old_scan_source_sha": expected_old_source,
                "old_scan_run_directory": str(scan_directory),
                "execution_campaign_window_sha256": campaign_state_entry[
                    "campaign_window_sha256"
                ],
                "old_scan_campaign_window_path": str(expected_old_window_path),
                "old_scan_campaign_window_sha256": TASK40_V23_CAMPAIGN_SHA256,
                "old_scan_campaign_accounting_path": str(expected_old_accounting_path),
                "old_scan_manifest_sha256": _sha256_file(scan_manifest_path),
                "old_q_failure_path": str(old_q_failure_path),
                "old_q_failure_sha256": _sha256_file(old_q_failure_path),
                "old_q_failure_type": old_q_failure.get("failure_type"),
                "old_q_failure_message": old_q_failure.get("failure_message"),
                "old_checkpoint_metadata_path": str(checkpoint_metadata_path),
                "old_checkpoint_metadata_sha256": _sha256_file(checkpoint_metadata_path),
                "old_checkpoint_payload_path": str(checkpoint_payload_path),
                "old_checkpoint_payload_sha256": _sha256_file(checkpoint_payload_path),
                "old_checkpoint_completed_mode_count": int(checkpoint["completed_mode_count"]),
                "old_checkpoint_field_sha256": old_field_sha256,
                "mesh_mpc_h_and_mode_identity_revalidated": True,
                "mode_scan_repeated": False,
                "full_q_matrix_coverage": "0/8",
                "factor_count": 0,
                "ksp_created": False,
                "pde_solved": False,
                "official_result": False,
                "q_tile_status": v23_q_tile_facts.get("status"),
                "q_tile_artifact_path": v23_q_tile_facts.get("artifact_path"),
            }
            supplement_path = output_directory / "v23_q_only_supplement.json"
            _write_json(supplement_path, supplement)
            supplement["artifact_path"] = supplement_path.name
            supplement["artifact_sha256"] = _sha256_file(supplement_path)
            facts["q_only_supplement"] = supplement
            facts["status"] = (
                "PASS_V23_Q_ONLY_SUPPLEMENT"
                if supplement["status"] == "PASS_Q_TILE_ONLY"
                else "FAILED_V23_Q_ONLY_SUPPLEMENT"
            )
            facts["failed_stage"] = None if supplement["status"] == "PASS_Q_TILE_ONLY" else "target_operator_probe"
            if supplement["status"] == "PASS_Q_TILE_ONLY":
                completed.append("target_operator_probe")
            return facts
        if is_v23_campaign:
            facts["scan_schedule"] = {
                "q_tile_planned_reserve_seconds": 3600.0,
                "q_tile_planned_reserve_scope": "planning amount only; not a numerical or resource gate",
                "q_tile_runs_before_mode_sweep": True,
                "original_H_p_source": "assembly_projection_denominator over the full frozen mode table; no integral iterator pass",
            }
            v23_q_tile_facts = _run_v23_original_ny8_q_port_tile(
                root,
                output_directory,
                preflight=preflight,
                modes=modes,
                mode_rows=mode_rows,
                space=space,
                mpc=mpc,
                cfg=cfg,
                assemblers=assemblers,
                assembly_context=context,
                axes_values=_v23_actual_axis_values(resolved),
                mapping_rows=mapping_rows,
                boundary_global_rows=boundary_global_rows,
                interior_rows=interior_rows_sorted,
                h_values=h_values,
                resource_sample=resource_sample,
            )
            facts["v23_selected_q_port_tile"] = v23_q_tile_facts
            resource_gates.extend(v23_q_tile_facts.get("resource_gates", ()))
            facts["q_coverage"] = _v23_q_coverage_record(v23_q_tile_facts)
            facts["scan_schedule"].update(
                {
                    "q_tile_actual_wall_seconds": v23_q_tile_facts.get("elapsed_wall_seconds"),
                    "q_tile_actual_process_cpu_seconds": v23_q_tile_facts.get("elapsed_process_cpu_seconds"),
                    "q_tile_status_before_mode_sweep": v23_q_tile_facts.get("status"),
                    "q_tile_planned_reserve_released_after_attempt": True,
                }
            )
        resource_gates.append(
            _resource_admission(
                "two_saved_cell_generated_action_and_local_q_tiles",
                256 * 2**20,
                resource_sample=resource_sample,
                require_task_cgroup=True,
            )
        )
        generated_packet_witness = _exercise_saved_packet_generated_action(
            root,
            space=space,
            dof_index_map=dof_index_map,
            mpc=mpc,
            mapping_rows=mapping_rows,
            permutation_info=permutation_info,
            polynomial=polynomial,
            cfg=cfg,
            modes=modes,
            mode_normalizations=h_values,
            quadrature_degree=qdegree,
        )
        if generated_packet_witness.get("status") != "PASS_GENERATED_FACTORY_AND_BOUNDED_Q_TILES":
            raise ValueError("saved-cell generated P6 factory and local q-tile witness did not pass")
        for side in ("bottom", "top"):
            packet_mode_index = generated_packet_witness["mode_indices_by_side"][side]
            packet_cell_id = generated_packet_witness["actual_cell_ids_by_side"][side]
            matching_packet_cells = [
                row
                for row in mapping_rows
                if str(row["side"]) == side
                and int(row["cell_id"]) == packet_cell_id
            ]
            if (
                packet_mode_index < 0
                or packet_mode_index >= len(modes)
                or str(modes[packet_mode_index].side) != side
                or not matching_packet_cells
                or set(str(row["class_id"]) for row in matching_packet_cells)
                != {generated_packet_witness["actual_class_ids_by_side"][side]}
                or len(generated_packet_witness["packet_npz_sha256"][side]) != 64
            ):
                raise ValueError(
                    f"generated {side} packet witness is not bound to the actual target mode/cell"
                )
        facts["operator_witness"] = {
            "status": "PREFLIGHTED_ACTUAL_FE_MPC_AND_LOCAL_GENERATED_FACTORY",
            "generated_p6_api_witness": generated_packet_witness,
            "independent_saved_full_row_packet_reference": generated_packet_witness[
                "independent_saved_full_row_packet_reference"
            ],
            "all_q_csr_factor_ksp_and_full_field": "NOT_RUN",
        }
        presweep_witness = {
            "schema": "task40extra.review_v22_pre_sweep_witness.v1",
            "run_id": preflight.get("run_id"),
            "source_sha": preflight.get("source_sha"),
            "input_sha256": preflight.get("input_sha256"),
            "physical_model_sha256": preflight.get("physical_model_sha256"),
            "mode_manifest_sha256": mode_inventory.get("mode_manifest_sha256"),
            "ordered_mode_key_sha256": mode_inventory.get("ordered_mode_key_sha256"),
            "actual_p6_space": facts["p6_space"],
            "actual_global_mpc_identity": mpc_identity,
            "boundary_mpc_dual_pullback": descriptor_identity[
                "boundary_mpc_dual_pullback"
            ],
            "native_quadrature_identity": native_quadrature_identity,
            "native_geometry_class_ids_by_side": facts["native_surface_adapter"][
                "geometry_class_ids_by_side"
            ],
            "generated_p6_api_witness": generated_packet_witness,
            "q_csr_factor_ksp_and_full_field": "NOT_RUN",
        }
        _write_json(output_directory / "v22_pre_sweep_witness.json", presweep_witness)
        facts["pre_sweep_witness_artifact"] = {
            "path": "v22_pre_sweep_witness.json",
            "sha256": _sha256_file(output_directory / "v22_pre_sweep_witness.json"),
        }
        campaign_state_before_sweep = _read_v22_campaign_state(root)
        if campaign_state_before_sweep["campaign_window_sha256"] != campaign_state_entry[
            "campaign_window_sha256"
        ]:
            raise ValueError("fixed Task40 V22 campaign identity changed during pre-sweep setup")
        facts["campaign_window"]["remaining_numerical_seconds_before_sweep"] = (
            campaign_state_before_sweep["remaining_numerical_seconds"]
        )

        resource_gates.append(
            _resource_admission(
                "nonzero_Dx_field_vector",
                full_rows * np.dtype(np.complex128).itemsize,
                resource_sample=resource_sample,
                require_task_cgroup=True,
            )
        )
        field = fem.Function(space, dtype=PETSc.ScalarType)
        field_values = np.asarray(field.x.array, dtype=np.complex128)
        if field_values.size != full_rows:
            raise ValueError("serial p6 Function vector does not match global storage rows")
        rng = np.random.default_rng(20261010)
        for start in range(0, full_rows, 1 << 20):
            stop = min(start + (1 << 20), full_rows)
            field_values.real[start:stop] = rng.standard_normal(stop - start)
            field_values.imag[start:stop] = rng.standard_normal(stop - start)
        mpc.homogenize(field)
        field.x.scatter_forward()
        mpc.backsubstitution(field)
        field.x.scatter_forward()
        selected_field_values = np.ascontiguousarray(
            field_values[native_rule.candidate_rows], dtype=np.complex128
        )
        del field
        field = None
        del field_values
        field_values = None
        gc.collect()

        for side in ("bottom", "top"):
            for mode_index in representative_indices[side]:
                mode = modes[mode_index]
                for component in (0, 1):
                    compact_equivalence_checks.append(
                        native_rule.compare_full_domain_reference(
                            mode,
                            component,
                            field_values_by_candidate_rows=selected_field_values,
                            alpha=complex(0.75, -0.125),
                        )
                    )
                gc.collect()
        nontrivial_mpc_witnesses = [
            row
            for row in compact_equivalence_checks
            if row["raw_mpc_slave_rows_nonzero_before_pullback"] > 0
        ]
        if not nontrivial_mpc_witnesses:
            raise ValueError(
                "representative compact/full-domain comparisons did not exercise a nonzero MPC slave row"
            )
        cutoff_distances = [
            row["closest_nonzero_to_cutoff_relative_distance"]
            for row in compact_equivalence_checks
            if row["closest_nonzero_to_cutoff_relative_distance"] is not None
        ]
        compact_timing = [row["paired_timing"] for row in compact_equivalence_checks]
        facts["compact_domain_equivalence"] = {
            "status": "PASS_EXACT_ROWS_MASKS_VALUES_B_ALPHA_AND_D_X",
            "comparison_count": len(compact_equivalence_checks),
            "representative_mode_indices_by_side": representative_indices,
            "first_middle_last_k_vectors_and_same_k_s_p_partners": True,
            "nontrivial_mpc_rows_exercised": True,
            "raw_mpc_slave_nonzero_comparison_count": len(nontrivial_mpc_witnesses),
            "cutoff_policy": {"relative_tol": 1e-13, "absolute_floor": 0.0},
            "minimum_cutoff_distance_relative": min(cutoff_distances) if cutoff_distances else None,
            "paired_timing_summary": {
                "field_source": "same seeded random field after actual MPC homogenization/backsubstitution used by the subsequent Dx scan",
                "alpha": {"real": 0.75, "imag": -0.125},
                "cache_policy": "basis cache cleared before each compact and full-domain path",
                "compact_wall_seconds_total": sum(row["compact_wall_seconds"] for row in compact_timing),
                "compact_process_cpu_seconds_total": sum(row["compact_process_cpu_seconds"] for row in compact_timing),
                "full_domain_reference_wall_seconds_total": sum(row["full_domain_reference_wall_seconds"] for row in compact_timing),
                "full_domain_reference_process_cpu_seconds_total": sum(row["full_domain_reference_process_cpu_seconds"] for row in compact_timing),
            },
            "rows_values_and_hashes_by_mode_component": compact_equivalence_checks,
        }

        resource_gates.append(
            _resource_admission(
                "compact_B_alpha_accumulator",
                len(native_rule.candidate_rows) * np.dtype(np.complex128).itemsize,
                resource_sample=resource_sample,
                require_task_cgroup=True,
            )
        )
        b_action = np.zeros(len(native_rule.candidate_rows), dtype=np.complex128)
        d_values = np.empty(len(modes), dtype=np.complex128)
        mode_counts_by_side = {"bottom": 0, "top": 0}
        support_rows_by_side = {
            side: {"B": 0, "D": 0, "nonempty_B_modes": 0, "nonempty_D_modes": 0}
            for side in ("bottom", "top")
        }
        field_sha256 = _array_sha256(selected_field_values)
        calibration_index_by_side: dict[str, int] = {}
        for index, mode in enumerate(modes):
            side = str(getattr(mode, "side", ""))
            if side not in calibration_index_by_side:
                calibration_index_by_side[side] = index
        if set(calibration_index_by_side) != {"bottom", "top"}:
            raise ValueError("target mode inventory omitted a top or bottom side")
        rows_by_side = {
            side: [row for row in mapping_rows if str(row["side"]) == side]
            for side in ("bottom", "top")
        }
        stream_digest = _RollingDigest() if is_v23_campaign else hashlib.sha256()
        mode_started = perf_counter()
        mode_cpu_started = process_time()
        mode_elapsed_offset = 0.0
        mode_cpu_elapsed_offset = 0.0
        mode_timing_by_side = {
            side: {"completed_modes": 0, "wall_seconds": 0.0, "process_cpu_seconds": 0.0}
            for side in ("bottom", "top")
        }
        calibration_results: dict[str, dict[str, Any]] = {}
        checkpoint_interval = 256 if is_v23_campaign else 8
        class_mode_prefix = {
            side: {class_id: 0 for class_id in native_rule.class_ids_by_side[side]}
            for side in ("bottom", "top")
        }
        stream_audit: dict[str, Any] = {}

        checkpoint_directory = (
            _v23_checkpoint_directory(
                root,
                preflight=preflight,
                mode_inventory=mode_inventory,
                campaign_window_sha256=campaign_state_entry[
                    "campaign_window_sha256"
                ],
            )
            if is_v23_campaign
            else output_directory
        )
        mode_index = 0
        if is_v23_campaign:
            resume = _load_v23_action_checkpoint(
                checkpoint_directory,
                preflight=preflight,
                mode_inventory=mode_inventory,
                campaign_window_sha256=campaign_state_entry[
                    "campaign_window_sha256"
                ],
                candidate_rows=native_rule.candidate_rows,
                modes=modes,
                h_values=h_values,
                side_cell_counts={
                    side: len(side_cell_positions[side]) for side in ("bottom", "top")
                },
                expected_field_sha256=field_sha256,
            )
            if resume is not None:
                checkpoint = resume["checkpoint"]
                b_action[:] = resume["b_action"]
                d_values[: resume["mode_count"]] = resume["d_values"]
                mode_index = int(resume["mode_count"])
                mode_counts_by_side.update(checkpoint["mode_count_by_side"])
                support_rows_by_side.update(resume["support_rows_by_side"])
                for side in ("bottom", "top"):
                    if set(resume["class_mode_prefix"][side]) != set(
                        class_mode_prefix[side]
                    ):
                        raise ValueError("V23 checkpoint boundary-class inventory changed")
                    class_mode_prefix[side] = {
                        str(key): int(value)
                        for key, value in resume["class_mode_prefix"][side].items()
                    }
                    for metric in ("B", "D", "union"):
                        for state_name in (
                            "per_cell_mode_counts",
                            "per_cell_interior_row_memberships",
                        ):
                            m_c_state[side][metric][state_name][:] = resume[
                                "cell_state"
                            ][side][metric][state_name]
                    for component in ("B", "D"):
                        for category in support_category_totals[side][component]:
                            support_category_totals[side][component][category] = int(
                                resume["support_category_totals"][side][component][category]
                            )
                native_rule.restore_filter_audit(resume["component_filter_audit"])
                calibration_results.update(resume["calibration_results"])
                rng.bit_generator.state = dict(resume["rng_state"])
                stream_digest = _RollingDigest(resume["stream_digest_state"])
                mode_elapsed_offset = float(resume["mode_sweep_elapsed_seconds"])
                mode_cpu_elapsed_offset = float(resume["mode_sweep_process_cpu_seconds"])
                mode_timing_by_side = resume["mode_timing_by_side"]
                stream_audit["prior_prefix_audit"] = {
                    "status": "PREFIX_RESTORED_FROM_CHECKPOINT",
                    "completed_mode_count": mode_index,
                    "global_combination_filter_audit": "SUFFIX_ONLY_REGENERATED_BY_ITERATOR",
                }
                facts["action_checkpoint_resume"] = {
                    "status": "RESTORED_HASH_BOUND_PREFIX",
                    "checkpoint_path": str(
                        (checkpoint_directory / "v23_mode_sweep_checkpoint.json").relative_to(
                            root
                        )
                    ),
                    "completed_mode_count": mode_index,
                    "field_sha256": field_sha256,
                    "candidate_rows_sha256": _array_sha256(native_rule.candidate_rows),
                    "alpha_rng_state_restored": True,
                    "per_cell_inventory_restored": True,
                }
            else:
                facts["action_checkpoint_resume"] = {
                    "status": "STARTED_WITH_EMPTY_PREFIX",
                    "checkpoint_directory": str(checkpoint_directory.relative_to(root)),
                }

        mode_started = perf_counter()
        mode_cpu_started = process_time()

        def write_action_checkpoint(**checkpoint_arguments: Any) -> dict[str, Any]:
            restart_state = None
            if is_v23_campaign:
                restart_state = {
                    "field_sha256": field_sha256,
                    "rng_state": rng.bit_generator.state,
                    "m_c_state": m_c_state,
                    "support_category_totals": support_category_totals,
                    "calibration_results": calibration_results,
                    "mode_sweep_elapsed_seconds": mode_elapsed_offset
                    + perf_counter()
                    - mode_started,
                    "mode_sweep_process_cpu_seconds": mode_cpu_elapsed_offset
                    + process_time()
                    - mode_cpu_started,
                    "mode_timing_by_side": {
                        side: dict(record) for side, record in mode_timing_by_side.items()
                    },
                    "expected_mode_counts_by_side": expected_mode_counts_by_side,
                }
            return _write_v22_action_checkpoint(
                output_directory,
                checkpoint_directory=checkpoint_directory,
                restart_state=restart_state,
                **checkpoint_arguments,
            )

        def accumulate_cell_multiplicity(
            side_name: str, metric: str, global_rows: Sequence[int]
        ) -> None:
            counts = _cell_support_row_counts(
                global_rows,
                interior_rows_sorted=interior_rows_sorted,
                interior_cell_ids_sorted=interior_cell_ids_sorted,
                cell_ids_sorted=cell_ids_sorted,
            )
            local = counts[side_cell_positions[side_name]]
            if local.size and int(np.max(local)) > 450:
                raise ValueError("per-cell production support exceeds the 450 interior rows")
            state = m_c_state[side_name][metric]
            _accumulate_cell_mode_support(
                state["per_cell_mode_counts"],
                state["per_cell_interior_row_memberships"],
                local,
            )

        def accumulate_support_categories(
            side_name: str, component_name: str, global_rows: Sequence[int]
        ) -> None:
            rows = np.asarray(global_rows, dtype=np.int64).reshape(-1)
            category_counts: dict[str, int] = {}
            for category, category_rows in support_category_rows.items():
                positions = np.searchsorted(category_rows, rows)
                valid = positions < len(category_rows)
                matched = np.zeros(len(rows), dtype=np.bool_)
                matched[valid] = category_rows[positions[valid]] == rows[valid]
                category_counts[category] = int(np.count_nonzero(matched))
            if category_counts["slave"]:
                raise ValueError("production support retained MPC slave rows after finalized E^H")
            classified = sum(
                category_counts[name]
                for name in (
                    "interior",
                    "actual_port_face_trace",
                    "other_trace",
                    "unknown",
                )
            )
            if classified != len(rows):
                raise ValueError(
                    f"production {component_name} support has unclassified global rows: "
                    f"{len(rows) - classified}"
                )
            totals = support_category_totals[side_name][component_name]
            for category, count in category_counts.items():
                totals[category] += count

        state_before_first_batch = _read_v22_campaign_state(root)
        if state_before_first_batch["campaign_window_sha256"] != campaign_state_entry[
            "campaign_window_sha256"
        ]:
            raise ValueError("fixed Task40 V22 campaign identity changed before the first batch")
        if state_before_first_batch["remaining_numerical_seconds"] <= 120.0:
            checkpoint = write_action_checkpoint(
                preflight=preflight,
                mode_inventory=mode_inventory,
                mode_count=mode_index,
                mode_counts_by_side=mode_counts_by_side,
                class_mode_prefix=class_mode_prefix,
                support_rows_by_side=support_rows_by_side,
                stream_digest=stream_digest,
                component_filter_audit=native_rule.filter_audit(),
                b_action=b_action,
                d_values=d_values,
                candidate_rows=native_rule.candidate_rows,
                checkpoint_interval=checkpoint_interval,
                h_values=h_values,
            )
            checkpoint["campaign_remaining_numerical_seconds"] = state_before_first_batch[
                "remaining_numerical_seconds"
            ]
            _write_json(output_directory / checkpoint["checkpoint_json_path"], checkpoint)
            facts.update(
                status="RESOURCE_CONTROLLED_STOP",
                failed_stage=None,
                partial_stages=["target_operator_probe"],
                blocked_task_stage="target_operator_probe",
                resource_blocker={
                    "gate_type": "fixed_campaign_time_cooperative_stop",
                    "remaining_numerical_seconds": state_before_first_batch[
                        "remaining_numerical_seconds"
                    ],
                    "next_batch_estimated_seconds": None,
                    "output_closeout_margin_seconds": 120.0,
                    "checkpoint_mode_count": mode_index,
                    "source": "read_campaign_state read-only fixed V22 window",
                },
                partial_mode_coverage={
                    "expected_mode_count": len(modes),
                    "completed_mode_count": mode_index,
                    "completed_by_side": dict(mode_counts_by_side),
                    "completed_side_class_mode_prefix": {
                        side_name: dict(class_mode_prefix[side_name])
                        for side_name in ("bottom", "top")
                    },
                    "stream_prefix_sha256": stream_digest.hexdigest(),
                },
                partial_action_result={
                    "checkpoint_path": checkpoint["checkpoint_json_path"],
                    "checkpoint_sha256": _sha256_file(
                        output_directory / checkpoint["checkpoint_json_path"]
                    ),
                    "actual_B_D_H_values_saved": True,
                    "official_R_T_A": "NOT_RUN",
                },
                q_coverage={
                    **(
                        _v23_q_coverage_record(v23_q_tile_facts or {"status": "NOT_RUN"})
                        if is_v23_campaign
                        else {
                            "status": "NOT_RUN",
                            "expected_q_count": 8,
                            "built_q_count": 0,
                            "reason": "cooperative fixed campaign time stop before the first mode batch",
                        }
                    ),
                },
            )
            return facts
        operator_iterator = iter_fullspace_dtn_functionals_from_surface(
            modes,
            assemblers,
            mpc,
            cfg,
            phase_gauge=BOUNDARY_PLANE,
            assembly_context=context,
            start_index=mode_index,
            audit=stream_audit,
        )

        def record_mode_block_timing(
            side_name: str, wall_started: float, cpu_started: float
        ) -> None:
            timing = mode_timing_by_side[side_name]
            timing["completed_modes"] += 1
            timing["wall_seconds"] += perf_counter() - wall_started
            timing["process_cpu_seconds"] += process_time() - cpu_started

        def controlled_resource_stop(
            error: _ProbeResourceBlocked,
            completed_mode_count: int,
            *,
            completed_current_side: str | None = None,
        ) -> dict[str, Any]:
            if completed_current_side is not None:
                for class_id in class_mode_prefix[completed_current_side]:
                    class_mode_prefix[completed_current_side][class_id] += 1
            if operator_iterator is not None:
                operator_iterator.close()
            checkpoint = write_action_checkpoint(
                preflight=preflight,
                mode_inventory=mode_inventory,
                mode_count=completed_mode_count,
                mode_counts_by_side=mode_counts_by_side,
                class_mode_prefix=class_mode_prefix,
                support_rows_by_side=support_rows_by_side,
                stream_digest=stream_digest,
                component_filter_audit=native_rule.filter_audit(),
                b_action=b_action,
                d_values=d_values,
                candidate_rows=native_rule.candidate_rows,
                checkpoint_interval=checkpoint_interval,
                h_values=h_values,
            )
            campaign_state = _read_v22_campaign_state(root)
            checkpoint["campaign_remaining_numerical_seconds"] = campaign_state[
                "remaining_numerical_seconds"
            ]
            _write_json(output_directory / checkpoint["checkpoint_json_path"], checkpoint)
            checkpoint_sha = _sha256_file(
                output_directory / checkpoint["checkpoint_json_path"]
            )
            facts.update(
                status="RESOURCE_CONTROLLED_STOP",
                failed_stage=None,
                partial_stages=["target_operator_probe"],
                blocked_task_stage="target_operator_probe",
                resource_blocker={
                    **error.facts,
                    "checkpoint_mode_count": completed_mode_count,
                    "checkpoint_sha256": checkpoint_sha,
                },
                probe_scope=(
                    "the exact completed ordered prefix is checkpointed; the unstarted suffix is not credited"
                ),
                partial_mode_coverage={
                    "expected_mode_count": len(modes),
                    "completed_mode_count": completed_mode_count,
                    "completed_by_side": dict(mode_counts_by_side),
                    "completed_side_class_mode_prefix": {
                        side_name: dict(class_mode_prefix[side_name])
                        for side_name in ("bottom", "top")
                    },
                    "stream_prefix_sha256": stream_digest.copy().hexdigest(),
                },
                partial_action_result={
                    "checkpoint_path": checkpoint["checkpoint_json_path"],
                    "checkpoint_sha256": checkpoint_sha,
                    "actual_B_D_H_values_saved": True,
                    "official_R_T_A": "NOT_RUN",
                },
                resource_gates=resource_gates,
                q_coverage={
                    **(
                        _v23_q_coverage_record(v23_q_tile_facts or {"status": "NOT_RUN"})
                        if is_v23_campaign
                        else {
                            "status": "NOT_RUN",
                            "expected_q_count": 8,
                            "built_q_count": 0,
                            "reason": "resource admission stopped during the actual B/D operator probe",
                        }
                    ),
                },
            )
            facts["native_same_rule_path_consistency_by_side"] = {
                name: dict(result) for name, result in calibration_results.items()
            }
            return facts

        while True:
            mode_item_wall_started = perf_counter()
            mode_item_cpu_started = process_time()
            try:
                functional = next(operator_iterator)
            except StopIteration:
                functional = None
                break
            current_index = int(functional.mode_key[0])
            if current_index != mode_index:
                raise ValueError(
                    f"production iterator emitted mode {current_index} while {mode_index} was expected"
                )
            side = str(functional.mode_key[1])
            if side not in mode_counts_by_side:
                raise ValueError("production iterator emitted an unknown target side")
            mode_timing_recorded = False
            production_component_work = None
            if current_index in calibration_index_by_side.values():
                workspace_bytes = len(native_rule.candidate_rows) * np.dtype(np.complex128).itemsize
                try:
                    workspace_gate = _resource_admission(
                        f"native_direct_B_calibration_vector_{side}",
                        workspace_bytes,
                        resource_sample=resource_sample,
                        require_task_cgroup=True,
                    )
                except _ProbeResourceBlocked as error:
                    resource_gates.append(error.facts)
                    return controlled_resource_stop(error, mode_index)
                resource_gates.append(workspace_gate)
                production_component_work = np.empty(
                    len(native_rule.candidate_rows), dtype=np.complex128
                )
            alpha = complex(rng.standard_normal(), rng.standard_normal())
            if len(functional.coupling_rows):
                compact_b_rows = native_rule.compact_positions(functional.coupling_rows)
                b_action[compact_b_rows] += functional.coupling_values * alpha
            compact_d_rows = native_rule.compact_positions(functional.projection_rows)
            d_value = (
                np.dot(
                    functional.projection_values,
                    selected_field_values[compact_d_rows],
                )
                if len(functional.projection_rows)
                else 0.0 + 0.0j
            )
            d_values[current_index] = d_value
            if float(functional.normalization_h) != float(h_values[current_index]):
                raise ValueError(
                    f"production H_p differs from the precomputed original mode scalar at mode {current_index}"
                )
            h_values[current_index] = float(functional.normalization_h)
            mode_counts_by_side[side] += 1
            support = support_rows_by_side[side]
            support["B"] += int(len(functional.coupling_rows))
            support["D"] += int(len(functional.projection_rows))
            support["nonempty_B_modes"] += int(bool(len(functional.coupling_rows)))
            support["nonempty_D_modes"] += int(bool(len(functional.projection_rows)))
            accumulate_support_categories(side, "B", functional.coupling_rows)
            accumulate_support_categories(side, "D", functional.projection_rows)
            union_support_rows = np.union1d(
                functional.coupling_rows, functional.projection_rows
            )
            accumulate_cell_multiplicity(side, "B", functional.coupling_rows)
            accumulate_cell_multiplicity(side, "D", functional.projection_rows)
            accumulate_cell_multiplicity(side, "union", union_support_rows)
            stream_digest.update(np.asarray([current_index], dtype="<i8").tobytes())
            stream_digest.update(_array_sha256(functional.coupling_rows).encode("ascii"))
            stream_digest.update(_array_sha256(functional.coupling_values).encode("ascii"))
            stream_digest.update(_array_sha256(functional.projection_rows).encode("ascii"))
            stream_digest.update(_array_sha256(functional.projection_values).encode("ascii"))
            stream_digest.update(np.asarray([functional.normalization_h, alpha, d_value], dtype="<c16").tobytes())

            if current_index in calibration_index_by_side.values():
                calibration_side = side
                b_error_sq = 0.0
                b_reference_sq = 0.0
                b_max_abs = 0.0
                b_worst = None
                raw_tiny_count = 0
                direct_dx = 0.0 + 0.0j
                local_started = perf_counter()
                for row in rows_by_side[side]:
                    cell_id = int(row["cell_id"])
                    local_dofs = np.asarray(
                        space.dofmap.cell_dofs(cell_id), dtype=np.int32
                    )
                    global_dofs = np.asarray(
                        dof_index_map.local_to_global(local_dofs), dtype=PETSc.IntType
                    )
                    interior_ids = global_dofs[interior_positions]
                    raw_b, raw_d = _native_local_port_pair(
                        polynomial=polynomial,
                        space_element=space.element,
                        mode=modes[current_index],
                        side=side,
                        bounds=row["cell_bounds_nm"],
                        cell_info=permutation_info[cell_id],
                        cfg=cfg,
                        quadrature_degree=qdegree,
                    )
                    direct_dx += np.dot(
                        raw_d, selected_field_values[native_rule.compact_positions(global_dofs)]
                    )
                    production_b = np.zeros(len(interior_ids), dtype=np.complex128)
                    if len(functional.coupling_rows):
                        positions = np.searchsorted(
                            functional.coupling_rows, interior_ids
                        )
                        valid = positions < len(functional.coupling_rows)
                        matched = np.zeros(len(interior_ids), dtype=np.bool_)
                        matched[valid] = (
                            functional.coupling_rows[positions[valid]] == interior_ids[valid]
                        )
                        production_b[matched] = functional.coupling_values[
                            positions[matched]
                        ]
                    local_b = raw_b[interior_positions]
                    error = local_b - production_b
                    b_error_sq += float(np.vdot(error, error).real)
                    b_reference_sq += float(np.vdot(local_b, local_b).real)
                    max_error = float(np.max(np.abs(error), initial=0.0))
                    raw_tiny_count += int(
                        np.count_nonzero(
                            (np.abs(local_b) > 0.0) & (np.abs(local_b) < 1e-13)
                        )
                    )
                    if max_error > b_max_abs:
                        b_max_abs = max_error
                        b_worst = {
                            "facet_id": int(row["facet_id"]),
                            "cell_id": cell_id,
                            "class_id": str(row["class_id"]),
                            "mode_index": current_index,
                            "mode_key": [
                                int(modes[current_index].m),
                                int(modes[current_index].n),
                                str(modes[current_index].polarization),
                            ],
                        }
                    if row is rows_by_side[side][0]:
                        generated_port = np.asarray([current_index], dtype=PETSc.IntType)
                        local_trace = global_dofs[trace_positions]
                        local_xi = np.ascontiguousarray(
                            selected_field_values[native_rule.compact_positions(interior_ids)],
                            dtype=np.complex128,
                        )
                        local_xt = np.ascontiguousarray(
                            selected_field_values[native_rule.compact_positions(local_trace)],
                            dtype=np.complex128,
                        )

                        def generate_raw_pair():
                            return _native_local_port_pair(
                                polynomial=polynomial,
                                space_element=space.element,
                                mode=modes[current_index],
                                side=side,
                                bounds=row["cell_bounds_nm"],
                                cell_info=permutation_info[cell_id],
                                cfg=cfg,
                                quadrature_degree=qdegree,
                            )

                        def generated_b(amplitudes):
                            amplitude = np.asarray(amplitudes, dtype=np.complex128)
                            if amplitude.shape != (1,):
                                raise ValueError("single-cell B callback expected one actual port")
                            local_b_value, _ = generate_raw_pair()
                            return (
                                np.ascontiguousarray(local_b_value[interior_positions] * amplitude[0]),
                                np.ascontiguousarray(local_b_value[trace_positions] * amplitude[0]),
                            )

                        def generated_d(interior, trace):
                            _, local_d_value = generate_raw_pair()
                            return np.asarray(
                                [
                                    np.dot(local_d_value[interior_positions], interior)
                                    + np.dot(local_d_value[trace_positions], trace)
                                ],
                                dtype=np.complex128,
                            )

                        def generated_b_tile(ports, amplitudes):
                            if not np.array_equal(np.asarray(ports), generated_port):
                                raise ValueError("actual-cell B tile changed its one-mode port identity")
                            amplitude_tile = np.asarray(amplitudes, dtype=np.complex128)
                            if amplitude_tile.ndim != 2 or amplitude_tile.shape[0] != 1:
                                raise ValueError("actual-cell B tile requires one bounded mode row")
                            local_b_value, _ = generate_raw_pair()
                            return (
                                np.ascontiguousarray(
                                    local_b_value[interior_positions, None]
                                    * amplitude_tile[0, None, :]
                                ),
                                np.ascontiguousarray(
                                    local_b_value[trace_positions, None]
                                    * amplitude_tile[0, None, :]
                                ),
                            )

                        def generated_d_tile(ports, interior, trace):
                            if not np.array_equal(np.asarray(ports), generated_port):
                                raise ValueError("actual-cell D tile changed its one-mode port identity")
                            _, local_d_value = generate_raw_pair()
                            result = (
                                local_d_value[interior_positions] @ np.asarray(interior)
                                + local_d_value[trace_positions] @ np.asarray(trace)
                            )
                            return np.ascontiguousarray(result.reshape(1, -1))

                        generated_action = P6GeneratedCellPortAction(
                            port_indices=generated_port,
                            apply_B=generated_b,
                            apply_D=generated_d,
                            callback_workspace_bytes=2 * 882 * np.dtype(np.complex128).itemsize,
                            apply_B_tile=generated_b_tile,
                            apply_D_tile=generated_d_tile,
                        )
                        b_tile_i, b_tile_t = generated_action.apply_B_tile(
                            generated_port, np.ones((1, 1), dtype=np.complex128)
                        )
                        d_tile = generated_action.apply_D_tile(
                            generated_port,
                            local_xi[:, None],
                            local_xt[:, None],
                        )
                        api_b, api_d = generated_action.apply_B(np.ones(1, dtype=np.complex128)), generated_action.apply_D(local_xi, local_xt)
                        api_match = bool(
                            np.array_equal(b_tile_i[:, 0], api_b[0])
                            and np.array_equal(b_tile_t[:, 0], api_b[1])
                            and d_tile.shape == (1, 1)
                            and np.isfinite(d_tile).all()
                            and np.allclose(d_tile[:, 0], api_d, rtol=1e-14, atol=0.0)
                        )
                        calibration_results.setdefault(side, {})["generated_action_api_witness"] = {
                            "status": "PASS_RAW_LOCAL_CALLBACK_TILES" if api_match else "FAILED_RAW_LOCAL_CALLBACK_TILES",
                            "facet_id": int(row["facet_id"]),
                            "cell_id": cell_id,
                            "class_id": str(row["class_id"]),
                            "port_index": current_index,
                            "native_rows": 882,
                            "interior_rows": int(len(interior_positions)),
                            "trace_rows": int(len(trace_positions)),
                            "B_tile_shape": [int(b_tile_i.shape[0]), int(b_tile_i.shape[1])],
                            "D_tile_shape": [int(d_tile.shape[0]), int(d_tile.shape[1])],
                        }
                        del generated_action, b_tile_i, b_tile_t, d_tile, api_b, api_d
                        del generated_port, local_trace, local_xi, local_xt
                    del raw_b, raw_d, local_b, production_b, error
                    del local_dofs, global_dofs, interior_ids
                production_dx = (
                    np.dot(
                        functional.projection_values,
                        selected_field_values[
                            native_rule.compact_positions(functional.projection_rows)
                        ],
                    )
                    if len(functional.projection_rows)
                    else 0.0 + 0.0j
                )
                b_relative = float(
                    np.sqrt(b_error_sq) / max(np.sqrt(b_reference_sq), np.finfo(float).tiny)
                )
                dx_relative = float(
                    abs(direct_dx - production_dx)
                    / max(abs(direct_dx), abs(production_dx), np.finfo(float).tiny)
                )
                calibration_result = calibration_results.setdefault(side, {})
                calibration_result.update(
                    {
                    "raw_B_interior_vs_filtered_relative": b_relative,
                    # Retain the historical field as the exact old raw-scope
                    # diagnostic; it is no longer the production consistency gate.
                    "B_interior_relative": b_relative,
                    "B_interior_max_absolute": float(b_max_abs),
                    "B_interior_worst": b_worst,
                    "raw_tiny_B_interior_count_below_1e-13": raw_tiny_count,
                    "raw_D_x_vs_filtered_relative": dx_relative,
                    "D_x_relative": dx_relative,
                    "raw_native_D_x": {"real": float(direct_dx.real), "imag": float(direct_dx.imag)},
                    "grouped_production_D_x": {
                        "real": float(production_dx.real),
                        "imag": float(production_dx.imag),
                    },
                    "raw_D_x_comparison_domain": (
                        "direct full-facet D action on the selected actual field versus the grouped "
                        "production projection action after the existing two global filters"
                    ),
                    }
                )

                def admit_calibration_bytes(stage: str, additional_bytes: int) -> None:
                    try:
                        gate = _resource_admission(
                            f"{stage}_{side}",
                            additional_bytes,
                            resource_sample=resource_sample,
                            require_task_cgroup=True,
                        )
                    except _ProbeResourceBlocked as error:
                        resource_gates.append(error.facts)
                        raise
                    resource_gates.append(gate)

                def direct_component_facet_contributions(component: int):
                    for facet_row in rows_by_side[side]:
                        facet_cell = int(facet_row["cell_id"])
                        facet_local_dofs = np.asarray(
                            space.dofmap.cell_dofs(facet_cell), dtype=np.int32
                        )
                        facet_global_dofs = np.asarray(
                            dof_index_map.local_to_global(facet_local_dofs),
                            dtype=PETSc.IntType,
                        )
                        component_values = _native_local_component_basis(
                            polynomial=polynomial,
                            space_element=space.element,
                            mode=modes[current_index],
                            side=side,
                            bounds=facet_row["cell_bounds_nm"],
                            cell_info=permutation_info[facet_cell],
                            component=component,
                            quadrature_degree=qdegree,
                        )
                        yield facet_global_dofs, component_values

                try:
                    if production_component_work is None:
                        raise RuntimeError("direct production B workspace was not admitted")
                    direct_component_entries = []
                    direct_component_audit = {}
                    for component in (0, 1):
                        entries, component_audit = _direct_mpc_filtered_component_entries(
                            production_component_work,
                            direct_component_facet_contributions(component),
                            slave_rows=native_rule._slave_rows,
                            master_rows=native_rule._master_rows,
                            dual_coefficients=native_rule._dual_coefficients,
                            master_counts=native_rule._master_counts,
                            index_dtype=native_rule.index_dtype,
                            compact_row_domain=native_rule.candidate_rows,
                            admit_additional_bytes=admit_calibration_bytes,
                        )
                        direct_component_entries.append(entries)
                        direct_component_audit[str(component)] = component_audit
                        calibration_result["direct_component_filter_audit"] = dict(
                            direct_component_audit
                        )
                    traction = np.asarray(
                        _traction_vector(modes[current_index], cfg)[:2],
                        dtype=np.complex128,
                    )
                    combination_reserve = int(
                        (
                            len(direct_component_entries[0][0])
                            + len(direct_component_entries[1][0])
                            + len(functional.coupling_rows)
                            + len(functional.projection_rows)
                        )
                        * 384
                    )
                    admit_calibration_bytes(
                        "direct_weighted_B_D_combination_and_comparison", combination_reserve
                    )
                    direct_B_audit: dict[str, Any] = {}
                    direct_B_rows, direct_B_values = _combine_owned_entries(
                        tuple(direct_component_entries),
                        (-traction[0], -traction[1]),
                        comm=MPI.COMM_WORLD,
                        audit=direct_B_audit,
                    )
                    support_union = np.union1d(
                        direct_B_rows, functional.coupling_rows
                    )
                    direct_aligned = np.zeros(len(support_union), dtype=np.complex128)
                    grouped_aligned = np.zeros(len(support_union), dtype=np.complex128)
                    if len(direct_B_rows):
                        direct_aligned[
                            np.searchsorted(support_union, direct_B_rows)
                        ] = direct_B_values
                    if len(functional.coupling_rows):
                        grouped_aligned[
                            np.searchsorted(support_union, functional.coupling_rows)
                        ] = functional.coupling_values
                    direct_error = direct_aligned - grouped_aligned
                    production_B_relative = float(
                        np.linalg.norm(direct_error)
                        / max(
                            np.linalg.norm(direct_B_values),
                            np.linalg.norm(functional.coupling_values),
                            np.finfo(float).tiny,
                        )
                    )
                    production_B_max_absolute = float(
                        np.max(np.abs(direct_error), initial=0.0)
                    )
                    production_B_support_mismatch = int(
                        len(
                            np.setxor1d(
                                direct_B_rows,
                                functional.coupling_rows,
                                assume_unique=True,
                            )
                        )
                    )
                    calibration_result.update(
                        production_B_relative=production_B_relative,
                        production_B_max_absolute=production_B_max_absolute,
                        production_B_support_mismatch_count=production_B_support_mismatch,
                        production_B_reference_domain=(
                            "direct per-facet native component vectors after actual MPC E^H, "
                            "component global-max masks, production traction weighting, and "
                            "the second global-max mask; compared on the full sorted support union"
                        ),
                        production_B_path_consistency_only=True,
                        production_B_support_digest={
                            "direct_rows_sha256": _array_sha256(direct_B_rows),
                            "grouped_rows_sha256": _array_sha256(functional.coupling_rows),
                            "direct_values_sha256": _array_sha256(direct_B_values),
                            "grouped_values_sha256": _array_sha256(functional.coupling_values),
                            "direct_row_count": int(len(direct_B_rows)),
                            "grouped_row_count": int(len(functional.coupling_rows)),
                            "support_union_row_count": int(len(support_union)),
                        },
                        production_B_combination_filter_audit=direct_B_audit,
                        direct_component_filter_audit=direct_component_audit,
                    )
                    electric = np.asarray(
                        modes[current_index].e_vector[:2], dtype=np.complex128
                    )
                    direct_D_audit: dict[str, Any] = {}
                    direct_D_rows, direct_D_projected = _combine_owned_entries(
                        tuple(direct_component_entries),
                        (electric[0], electric[1]),
                        comm=MPI.COMM_WORLD,
                        audit=direct_D_audit,
                    )
                    direct_D_values = np.ascontiguousarray(
                        np.conjugate(direct_D_projected), dtype=np.complex128
                    )
                    direct_D_x_same_domain = (
                        np.dot(
                            direct_D_values,
                            selected_field_values[native_rule.compact_positions(direct_D_rows)],
                        )
                        if len(direct_D_rows)
                        else 0.0 + 0.0j
                    )
                    grouped_D_x_same_domain = (
                        np.dot(
                            functional.projection_values,
                            selected_field_values[
                                native_rule.compact_positions(functional.projection_rows)
                            ],
                        )
                        if len(functional.projection_rows)
                        else 0.0 + 0.0j
                    )
                    production_D_relative = float(
                        abs(direct_D_x_same_domain - grouped_D_x_same_domain)
                        / max(
                            abs(direct_D_x_same_domain),
                            abs(grouped_D_x_same_domain),
                            np.finfo(float).tiny,
                        )
                    )
                    production_D_support_mismatch = int(
                        len(
                            np.setxor1d(
                                direct_D_rows,
                                functional.projection_rows,
                                assume_unique=True,
                            )
                        )
                    )
                    d_support_union = np.union1d(
                        direct_D_rows, functional.projection_rows
                    )
                    direct_D_aligned = np.zeros(
                        len(d_support_union), dtype=np.complex128
                    )
                    grouped_D_aligned = np.zeros(
                        len(d_support_union), dtype=np.complex128
                    )
                    if len(direct_D_rows):
                        direct_D_aligned[
                            np.searchsorted(d_support_union, direct_D_rows)
                        ] = direct_D_values
                    if len(functional.projection_rows):
                        grouped_D_aligned[
                            np.searchsorted(d_support_union, functional.projection_rows)
                        ] = functional.projection_values
                    production_D_vector_relative = float(
                        np.linalg.norm(direct_D_aligned - grouped_D_aligned)
                        / max(
                            np.linalg.norm(direct_D_values),
                            np.linalg.norm(functional.projection_values),
                            np.finfo(float).tiny,
                        )
                    )
                    calibration_result.update(
                        production_D_relative=production_D_relative,
                        production_D_vector_relative=production_D_vector_relative,
                        production_D_support_mismatch_count=production_D_support_mismatch,
                        production_D_reference_domain=(
                            "direct per-facet components after actual MPC E^H and component global-max "
                            "masks, original electric weights, second global-max mask, conjugated raw D, "
                            "and action on the same selected field"
                        ),
                        production_D_path_consistency_only=True,
                        production_D_x_same_domain={
                            "direct": {
                                "real": float(direct_D_x_same_domain.real),
                                "imag": float(direct_D_x_same_domain.imag),
                            },
                            "grouped": {
                                "real": float(grouped_D_x_same_domain.real),
                                "imag": float(grouped_D_x_same_domain.imag),
                            },
                        },
                        production_D_support_digest={
                            "direct_rows_sha256": _array_sha256(direct_D_rows),
                            "grouped_rows_sha256": _array_sha256(functional.projection_rows),
                            "direct_values_sha256": _array_sha256(direct_D_values),
                            "grouped_values_sha256": _array_sha256(
                                functional.projection_values
                            ),
                            "direct_row_count": int(len(direct_D_rows)),
                            "grouped_row_count": int(len(functional.projection_rows)),
                            "support_union_row_count": int(len(d_support_union)),
                        },
                        production_D_combination_filter_audit=direct_D_audit,
                    )
                except _ProbeResourceBlocked as error:
                    return controlled_resource_stop(
                        error,
                        mode_index + 1,
                        completed_current_side=side,
                    )

                local_seconds = perf_counter() - local_started
                calibration_results[side].update(
                    status="MEASURED_RAW_PACKET_AND_PRODUCTION_SUPPORT_PATH_CONSISTENCY",
                    independent_reference=False,
                    shared_integral_kernel="FacetPolynomial.integral_native",
                    mode_index=current_index,
                    mode_key=[
                        int(modes[current_index].m),
                        int(modes[current_index].n),
                        str(modes[current_index].polarization),
                    ],
                    facet_count=len(rows_by_side[side]),
                    boundary_class_count=len({str(row["class_id"]) for row in rows_by_side[side]}),
                    raw_B_interior_vs_filtered_domain=(
                        "legacy diagnostic only: unfiltered raw local interior entries versus "
                        "the grouped production functional after MPC and both global filters"
                    ),
                    seconds=local_seconds,
                    source=(
                        "direct and grouped routes share FacetPolynomial.integral_native but use "
                        "different per-facet versus class-grouped accumulation paths; production "
                        "comparison is path consistency, not an independent quadrature oracle; "
                        "independent full 882-row qualification remains the saved packet witness"
                    ),
                )
                del direct_component_entries, direct_component_audit
                del direct_B_rows, direct_B_values, direct_B_audit
                del direct_D_rows, direct_D_projected, direct_D_values, direct_D_audit
                del d_support_union, direct_D_aligned, grouped_D_aligned
                del support_union, direct_aligned, grouped_aligned, direct_error
                del production_component_work
                facts["native_same_rule_path_consistency_by_side"] = {
                    name: dict(result) for name, result in calibration_results.items()
                }
                record_mode_block_timing(
                    side, mode_item_wall_started, mode_item_cpu_started
                )
                mode_timing_recorded = True
                gate_failure = _native_calibration_gate_failure(
                    side=side,
                    mode_index=current_index,
                    mode_key=calibration_results[side]["mode_key"],
                    calibration_result=calibration_results[side],
                )
                if gate_failure is not None:
                    for class_id in class_mode_prefix[side]:
                        class_mode_prefix[side][class_id] += 1
                    checkpoint = write_action_checkpoint(
                        preflight=preflight,
                        mode_inventory=mode_inventory,
                        mode_count=mode_index + 1,
                        mode_counts_by_side=mode_counts_by_side,
                        class_mode_prefix=class_mode_prefix,
                        support_rows_by_side=support_rows_by_side,
                        stream_digest=stream_digest,
                        component_filter_audit=native_rule.filter_audit(),
                        b_action=b_action,
                        d_values=d_values,
                        candidate_rows=native_rule.candidate_rows,
                        checkpoint_interval=checkpoint_interval,
                        h_values=h_values,
                        failure_facts=gate_failure,
                    )
                    facts.update(
                        status="FAILED_NATIVE_OPERATOR_GATE",
                        failed_stage="target_operator_probe",
                        failure_type="NativeOperatorGateFailure",
                        failure_message=(
                            f"{side} first native calibration failed: "
                            f"{', '.join(gate_failure['failed_checks'])}"
                        ),
                        early_operator_gate_failure=gate_failure,
                        latest_mode_checkpoint=checkpoint,
                        partial_stages=["target_operator_probe"],
                        partial_mode_coverage={
                            "expected_mode_count": len(modes),
                            "completed_mode_count": mode_index + 1,
                            "completed_by_side": dict(mode_counts_by_side),
                            "completed_side_class_mode_prefix": {
                                side_name: dict(class_mode_prefix[side_name])
                                for side_name in ("bottom", "top")
                            },
                            "stream_prefix_sha256": stream_digest.copy().hexdigest(),
                        },
                        partial_action_result={
                            "checkpoint_path": checkpoint["checkpoint_json_path"],
                            "checkpoint_sha256": _sha256_file(
                                output_directory / checkpoint["checkpoint_json_path"]
                            ),
                            "actual_B_D_H_values_saved": True,
                            "official_R_T_A": "NOT_RUN",
                        },
                        q_coverage={
                            **(
                                _v23_q_coverage_record(v23_q_tile_facts or {"status": "NOT_RUN"})
                                if is_v23_campaign
                                else {
                                    "status": "NOT_RUN",
                                    "expected_q_count": 8,
                                    "built_q_count": 0,
                                    "reason": (
                                        "first native calibration gate failed before the remaining "
                                        "mode sweep or q construction"
                                    ),
                                }
                            ),
                        },
                    )
                    return facts
            if not mode_timing_recorded:
                record_mode_block_timing(
                    side, mode_item_wall_started, mode_item_cpu_started
                )
            for class_id in class_mode_prefix[side]:
                class_mode_prefix[side][class_id] += 1
            mode_index += 1
            functional = None

            if mode_index % checkpoint_interval == 0 or mode_index == len(modes):
                checkpoint = write_action_checkpoint(
                    preflight=preflight,
                    mode_inventory=mode_inventory,
                    mode_count=mode_index,
                    mode_counts_by_side=mode_counts_by_side,
                    class_mode_prefix=class_mode_prefix,
                    support_rows_by_side=support_rows_by_side,
                    stream_digest=stream_digest,
                    component_filter_audit=native_rule.filter_audit(),
                    b_action=b_action,
                    d_values=d_values,
                    h_values=h_values,
                    candidate_rows=native_rule.candidate_rows,
                    checkpoint_interval=checkpoint_interval,
                )
                elapsed = mode_elapsed_offset + perf_counter() - mode_started
                seconds_per_mode = elapsed / max(mode_index, 1)
                campaign_checkpoint_state = _read_v22_campaign_state(root)
                if campaign_checkpoint_state["campaign_window_sha256"] != campaign_state_entry[
                    "campaign_window_sha256"
                ]:
                    raise ValueError("fixed Task40 V22 campaign identity changed during the mode sweep")
                checkpoint["campaign_remaining_numerical_seconds"] = campaign_checkpoint_state[
                    "remaining_numerical_seconds"
                ]
                _write_json(output_directory / checkpoint["checkpoint_json_path"], checkpoint)
                facts["latest_mode_checkpoint"] = checkpoint
                scan_forecast = None
                if is_v23_campaign:
                    scan_forecast = _v23_scan_time_forecast(
                        modes,
                        next_mode_index=mode_index,
                        mode_timing_by_side=mode_timing_by_side,
                        observed_wall_seconds=elapsed,
                        observed_process_cpu_seconds=(
                            mode_cpu_elapsed_offset
                            + process_time()
                            - mode_cpu_started
                        ),
                    )
                    campaign_available = max(
                        float(campaign_checkpoint_state["remaining_numerical_seconds"])
                        - 120.0,
                        0.0,
                    )
                    facts["scan_time_forecast"] = {
                        **scan_forecast,
                        "current_mode_count": mode_index,
                        "campaign_remaining_numerical_seconds": float(
                            campaign_checkpoint_state["remaining_numerical_seconds"]
                        ),
                        "output_closeout_reserve_seconds": 120.0,
                        "available_numerical_seconds_after_closeout_reserve": campaign_available,
                    }

                if mode_index < len(modes) and campaign_checkpoint_state[
                    "remaining_numerical_seconds"
                ] <= max(120.0, 2.0 * checkpoint_interval * seconds_per_mode):
                    facts.update(
                        status="RESOURCE_CONTROLLED_STOP",
                        failed_stage=None,
                        partial_stages=["target_operator_probe"],
                        blocked_task_stage="target_operator_probe",
                        resource_blocker={
                            "gate_type": "fixed_campaign_time_cooperative_stop",
                            "remaining_numerical_seconds": campaign_checkpoint_state[
                                "remaining_numerical_seconds"
                            ],
                            "next_batch_estimated_seconds": checkpoint_interval
                            * seconds_per_mode,
                            "output_closeout_margin_seconds": 120.0,
                            "checkpoint_mode_count": mode_index,
                            "checkpoint_payload_sha256": checkpoint["actual_action_payload"][
                                "sha256"
                            ],
                            "source": "read_campaign_state read-only fixed V22 window",
                        },
                        probe_scope=(
                            "completed modes are a durable exact ordered prefix; the unstarted suffix is not credited"
                        ),
                        partial_mode_coverage={
                            "expected_mode_count": len(modes),
                            "completed_mode_count": mode_index,
                            "completed_by_side": dict(mode_counts_by_side),
                            "completed_side_class_mode_prefix": {
                                side_name: dict(class_mode_prefix[side_name])
                                for side_name in ("bottom", "top")
                            },
                            "stream_prefix_sha256": stream_digest.copy().hexdigest(),
                        },
                        partial_action_result={
                            "checkpoint_path": checkpoint["checkpoint_json_path"],
                            "checkpoint_sha256": _sha256_file(
                                output_directory / checkpoint["checkpoint_json_path"]
                            ),
                            "actual_B_D_H_values_saved": True,
                            "official_R_T_A": "NOT_RUN",
                        },
                        q_coverage={
                            "status": "NOT_RUN",
                            "expected_q_count": 8,
                            "built_q_count": 0,
                            "reason": "cooperative fixed campaign time stop before any q construction",
                        },
                    )
                    return facts

        mode_sweep_seconds = mode_elapsed_offset + perf_counter() - mode_started
        if mode_index != len(modes) or mode_counts_by_side != {"bottom": 16_030, "top": 16_030}:
            raise ValueError("production surface iterator did not cover the complete 32,060-mode table")
        # The iterator audit reuses the same full ordered manifest for this one pass.
        b_facts = {
            "status": "MEASURED_ALL_32_060_MODES",
            "vector_scope": "compact B alpha accumulator indexed by complete boundary-cell and MPC-master global-row identities",
            "mode_count": mode_index,
            "mode_count_by_side": mode_counts_by_side,
            "support_rows_by_side": support_rows_by_side,
            "nonzero_rows": int(np.count_nonzero(b_action)),
            "norm": float(np.linalg.norm(b_action)),
            "sha256": _array_sha256(b_action),
            "candidate_global_rows_sha256": _array_sha256(native_rule.candidate_rows),
            "candidate_global_row_count": int(len(native_rule.candidate_rows)),
            "mode_sweep_seconds": mode_sweep_seconds,
            "mode_functional_stream_sha256": stream_digest.hexdigest(),
        }
        d_facts = {
            "status": "MEASURED_ALL_32_060_MODES",
            "field_vector_rows": int(len(selected_field_values)),
            "field_vector_scope": "one gather of MPC-backsubstituted values at compact candidate global rows",
            "field_sha256": _array_sha256(selected_field_values),
            "candidate_global_rows_sha256": _array_sha256(native_rule.candidate_rows),
            "field_slave_rows_backsubstituted": True,
            "mode_values_sha256": _array_sha256(d_values),
            "mode_values_norm": float(np.linalg.norm(d_values)),
            "normalization_h_sha256": _array_sha256(h_values),
            "normalization_h_min": float(np.min(h_values)),
            "normalization_h_max": float(np.max(h_values)),
            "mode_sweep_seconds": mode_sweep_seconds,
        }
        support_mismatch_by_side = {
            side: {
                "B": result.get("production_B_support_mismatch_count"),
                "D": result.get("production_D_support_mismatch_count"),
            }
            for side, result in calibration_results.items()
        }
        support_mismatch_detected = any(
            isinstance(count, int)
            and not isinstance(count, bool)
            and count > 0
            for side_counts in support_mismatch_by_side.values()
            for count in side_counts.values()
        )
        facts["production_support"] = {
            "status": "MEASURED_ALL_MODES_AFTER_BOTH_GLOBAL_FILTER_STAGES",
            "support_semantics": descriptor_identity["production_support_semantics"],
            "direct_filtered_support_qualification": {
                "status": (
                    "PARTIAL_SUPPORT_MISMATCH"
                    if support_mismatch_detected
                    else "MATCHED_ON_TWO_CALIBRATED_MODES"
                ),
                "production_exact_qualification": "PARTIAL",
                "support_mismatch_count_by_side": support_mismatch_by_side,
                "scope": (
                    "two representative first-mode all-facet side calibrations; "
                    "shared-kernel path consistency only"
                ),
            },
            "mode_count_by_side": mode_counts_by_side,
            "global_B_D_support_rows_by_side": support_rows_by_side,
            "online_cell_inventory": {
                "status": "MEASURED_IN_THE_SAME_PRODUCTION_MODE_SWEEP",
                "m_c_definition": (
                    "for each boundary-adjacent cell, the number of distinct modes in which "
                    "at least one retained production B row, D row, or B/D union row belongs "
                    "to that cell's 450 interior global rows; each cell contributes at most "
                    "once per mode, regardless of how many rows are supported"
                ),
                "expected_mode_count_by_side": expected_mode_counts_by_side,
                "cell_ids_by_side": {
                    side: cell_ids_sorted[side_cell_positions[side]].tolist()
                    for side in ("bottom", "top")
                },
                "cell_ids_sha256": {
                    side: _array_sha256(cell_ids_sorted[side_cell_positions[side]])
                    for side in ("bottom", "top")
                },
                "m_c_by_side": {
                    side: {
                        metric: _summarize_cell_mode_support(
                            state["per_cell_mode_counts"],
                            expected_mode_count=expected_mode_counts_by_side[side],
                        )
                        for metric, state in m_c_state[side].items()
                    }
                    for side in ("bottom", "top")
                },
                "raw_interior_row_memberships_by_side": {
                    side: {
                        metric: {
                            "total_across_modes_and_cells": int(
                                np.sum(
                                    state["per_cell_interior_row_memberships"],
                                    dtype=np.int64,
                                )
                            ),
                            "per_cell_row_membership_sum": state[
                                "per_cell_interior_row_memberships"
                            ].tolist(),
                        }
                        for metric, state in m_c_state[side].items()
                    }
                    for side in ("bottom", "top")
                },
                "filtered_support_category_entries_by_side": support_category_totals,
                "category_definitions": {
                    "interior": "unique boundary-cell interior global rows",
                    "actual_port_face_trace": (
                        "Basix entity-closure DoFs, including face edges, "
                        "on the mapped physical port facets"
                    ),
                    "other_trace": "remaining boundary-cell trace rows outside actual port facets",
                    "slave": "raw finalized MPC slave support before E^H; absent from retained output by contract",
                    "unknown": "retained MPC master-closure rows outside the boundary-cell dof union",
                },
                "unclassified_retained_rows": 0,
                "raw_component_filter_audit": native_rule.filter_audit(),
                "weighted_production_filter_audit": stream_audit,
            },
            "raw_tiny_local_B_interior_entries_below_1e-13_by_calibration_side": {
                side: result.get("raw_tiny_B_interior_count_below_1e-13")
                for side, result in calibration_results.items()
            },
        }
        facts["operator_witness"] = {
            "status": "ALL_MODE_GLOBAL_B_D_STREAM_WITH_TWO_SIDE_NATIVE_CALIBRATION",
            "gauge": BOUNDARY_PLANE,
            "quadrature_degree": int(qdegree),
            "mode_coverage": {
                "expected": 32_060,
                "completed": mode_index,
                "completed_by_side": mode_counts_by_side,
                "checkpoint_interval_modes": checkpoint_interval,
                "checkpoint_path": checkpoint["checkpoint_json_path"],
                "resume_scope": "the latest atomic checkpoint retains exact B nonzeros and completed D/H values for inspection/recovery",
                "completed_side_class_mode_prefix": {
                    side: dict(class_mode_prefix[side]) for side in ("bottom", "top")
                },
            },
            "B_alpha": b_facts,
            "D_x": d_facts,
            "native_882_row_calibration_by_side": calibration_results,
            "online_support_inventory": facts["production_support"]["online_cell_inventory"],
            "generated_p6_api_witness": generated_packet_witness,
            "all_ordered_modes": 32_060,
            "potential_side_specific_mode_facet_pairs": 69_762_560,
            "all_q_csr_factor_ksp_and_full_field": "NOT_RUN",
            "R_T_A": "NOT_RUN",
        }
        facts["stream_iterator_audit"] = stream_audit
        facts["native_surface_rule_assembly_stats"] = native_rule.assembly_stats
        facts["native_surface_component_filter_audit"] = native_rule.filter_audit()
        facts["resource_gates"] = resource_gates
        facts["resource_before_release"] = _memory_snapshot(resource_sample)
        native_limits_passed = all(
            result.get("production_B_relative", np.inf) <= 1e-10
            and result.get("production_D_relative", np.inf) <= 1e-10
            and 0.0 <= result.get("production_D_vector_relative", -1.0) <= 1e-10
            and result.get("generated_action_api_witness", {}).get("status")
            == "PASS_RAW_LOCAL_CALLBACK_TILES"
            for result in calibration_results.values()
        ) and generated_packet_witness.get("status") == "PASS_GENERATED_FACTORY_AND_BOUNDED_Q_TILES"
        facts["operator_gate_limits"] = {
            "production_B_relative": 1e-10,
            "production_D_relative": 1e-10,
            "production_D_vector_relative": 1e-10,
            "independent_raw_882_row_packet_B_D_relative": 1e-10,
            "legacy_raw_B_interior_vs_filtered_relative": "diagnostic_only_not_a_gate",
            "scope": (
                "two all-facet side calibrations; B is direct per-facet MPC/two-filter path "
                "consistency against grouped production, while independent raw 882-row packet "
                "qualification remains a separate pre-sweep gate"
            ),
        }
        if not native_limits_passed:
            facts["status"] = "FAILED_NATIVE_OPERATOR_GATE"
            facts["failed_stage"] = "target_operator_probe"
            facts["failure_message"] = "native 882-row B/D or generated callback tile calibration exceeded its recorded gate"
        elif is_v23_campaign:
            q_status = (v23_q_tile_facts or {}).get("status")
            if q_status == "PASS_REAL_ORIGINAL_NY8_Q_PORT_TILE":
                facts["status"] = "PASS_ALL_MODE_B_D_STREAM_WITH_PARTIAL_Q_PORT_TILE"
                completed.append("target_operator_probe")
            elif q_status in {"NOT_RUN_RESOURCE_GATE", "NOT_RUN_TIME_STOP"}:
                facts.update(
                    status="RESOURCE_CONTROLLED_STOP",
                    failed_stage=None,
                    blocked_task_stage="target_operator_probe",
                    partial_stages=["target_operator_probe"],
                    resource_blocker={
                        "gate_type": (
                            "fixed_campaign_time_cooperative_stop"
                            if q_status == "NOT_RUN_TIME_STOP"
                            else "selected_q_port_tile_resource_admission"
                        ),
                        "q_tile_status": q_status,
                        "q_tile_resource_blocker": (v23_q_tile_facts or {}).get(
                            "resource_blocker"
                        ),
                        "q_tile_time_stop": (v23_q_tile_facts or {}).get(
                            "time_stop"
                        ),
                        "checkpoint_mode_count": mode_index,
                        "checkpoint_path": checkpoint["checkpoint_json_path"],
                    },
                    partial_mode_coverage={
                        "expected_mode_count": len(modes),
                        "completed_mode_count": mode_index,
                        "completed_by_side": dict(mode_counts_by_side),
                        "completed_side_class_mode_prefix": {
                            side_name: dict(class_mode_prefix[side_name])
                            for side_name in ("bottom", "top")
                        },
                        "stream_prefix_sha256": stream_digest.copy().hexdigest(),
                    },
                    partial_action_result={
                        "checkpoint_path": checkpoint["checkpoint_json_path"],
                        "checkpoint_sha256": _sha256_file(
                            output_directory / checkpoint["checkpoint_json_path"]
                        ),
                        "actual_B_D_H_values_saved": True,
                        "official_R_T_A": "NOT_RUN",
                    },
                )
            else:
                facts["status"] = "FAILED_SELECTED_Q_PORT_TILE"
                facts["failed_stage"] = "target_operator_probe"
                facts["failure_message"] = (
                    (v23_q_tile_facts or {}).get("failure_message")
                    or f"V23 q port tile did not pass: {q_status}"
                )
        else:
            facts["status"] = "PASS_ALL_MODE_B_D_STREAM_WITH_Q_UNBUILT"
            completed.append("target_operator_probe")
            facts["q_coverage"] = {
                "status": "NOT_RUN",
                "expected_q_count": 8,
                "built_q_count": 0,
                "full_q_matrix_coverage": "0/8",
                "reason": "V22 selected q port tile is outside this campaign",
            }
        return facts
    except _ProbeResourceBlocked as error:
        facts.update(
            status="RESOURCE_CONTROLLED_STOP",
            failed_stage=None,
            partial_stages=[current_stage] if current_stage is not None else [],
            blocked_task_stage=current_stage,
            resource_blocker=error.facts,
            resource_gates=resource_gates,
            failure_message=None,
            probe_scope=(
                "only the actual completed prefix is credited; the blocked stage remains partial and is not complete"
            ),
            q_coverage=(
                _v23_q_coverage_record(v23_q_tile_facts or {"status": "NOT_RUN"})
                if is_v23_campaign
                else {
                    "status": "NOT_RUN",
                    "expected_q_count": 8,
                    "built_q_count": 0,
                    "reason": "resource admission stopped before q construction",
                }
            ),
        )
        return facts
    except Exception as error:
        facts.update(
            status="FAILED",
            failed_stage=current_stage,
            completed_stages=list(completed),
            failure_message=f"{type(error).__name__}: {error}",
            failure_type=type(error).__name__,
            resource_gates=resource_gates,
            q_coverage=(
                _v23_q_coverage_record(v23_q_tile_facts or {"status": "NOT_RUN"})
                if is_v23_campaign
                else {
                    "status": "NOT_RUN",
                    "expected_q_count": 8,
                    "built_q_count": 0,
                    "reason": "probe failed before q construction",
                }
            ),
        )
        return facts
    finally:
        facts["attempted_stages"] = list(attempted)
        facts["completed_stages"] = list(completed)
        facts.setdefault("resource_gates", resource_gates)
        facts["resource_before_release"] = facts.get(
            "resource_before_release", _memory_snapshot(resource_sample)
        )
        release_names = (
            "functional",
            "operator_iterator",
            "field_values",
            "selected_field_values",
            "b_action",
            "d_values",
            "h_values",
            "polynomial",
            "permutation_info",
            "assemblers",
            "context",
            "mpc",
            "mpc_data",
            "space",
            "mesh_data",
            "cell_tags",
            "facet_tags",
            "boundary_facets",
            "mesh_object",
            "mapping_rows",
            "mapping",
            "geometry_facts",
            "cfg",
        )
        functional = operator_iterator = None
        field_values = selected_field_values = None
        b_action = d_values = h_values = None
        polynomial = permutation_info = dof_index_map = None
        assemblers = context = None
        mpc = mpc_data = None
        space = mesh_data = None
        cell_tags = facet_tags = boundary_facets = None
        mesh_object = None
        mapping_rows = mapping = geometry_facts = cfg = None
        field = None
        gc.collect()
        after_release = _memory_snapshot(resource_sample)
        facts["cleanup"] = {
            "status": "UNKNOWN",
            "reason": "Python aliases were cleared; native owners and launcher descendants require independent receipts",
            "known_python_reference_aliases_cleared": list(release_names),
            "native_owners_released": None,
            "temporary_stage_objects_released": None,
            "process_descendants_cleared": None,
            "descendant_process_tree_cleanup": "external launcher/watchdog receipt required",
            "resource_after_reference_clear": after_release,
        }
        facts.setdefault("q_coverage", {
            "status": "NOT_RUN",
            "expected_q_count": 8,
            "built_q_count": 0,
            "reason": "q construction is outside this probe",
        })
        facts.setdefault("expected_q_count", 8)
        facts.setdefault("built_q_count", 0)
        facts["official_result"] = False
        facts["official_R_T_A_created"] = False
        _write_json(output_directory / "v22_target_operator_probe.json", facts)

def run_v22_target_operator_probe(
    resolved_payload: Mapping[str, Any],
    output_directory: str | Path,
    *,
    source_sha: str,
    preflight: Mapping[str, Any],
    modes: Sequence[Any] | None,
    mode_rows: Sequence[Mapping[str, Any]] | None,
    resource_sample: Callable[[], Mapping[str, Any]],
) -> dict[str, Any]:
    """Run the independent target operator stage and always preserve a receipt."""

    output_directory = Path(output_directory).resolve()
    if modes is None or mode_rows is None:
        facts: dict[str, Any] = {
            "schema": "task40extra.review_v22_target_operator_probe.v1",
            "status": "FAILED",
            "official_result": False,
            "run_id": preflight.get("run_id"),
            "source_sha": source_sha,
            "input_sha256": preflight.get("input_sha256"),
            "physical_model_sha256": preflight.get("physical_model_sha256"),
            "attempted_stages": ["geometry_inventory"],
            "completed_stages": [],
            "failed_stage": "geometry_inventory",
            "failure_message": "V20 preflight omitted the frozen target mode table",
        }
        _write_json(output_directory / "v22_target_operator_probe.json", facts)
        return facts
    try:
        facts = _run_probe(
            resolved_payload,
            output_directory,
            preflight=preflight,
            modes=modes,
            mode_rows=mode_rows,
            resource_sample=resource_sample,
        )
        facts.setdefault("source_sha", source_sha)
        return facts
    except Exception as error:
        facts = {
            "schema": "task40extra.review_v22_target_operator_probe.v1",
            "status": "FAILED",
            "official_result": False,
            "run_id": preflight.get("run_id"),
            "source_sha": source_sha,
            "input_sha256": preflight.get("input_sha256"),
            "physical_model_sha256": preflight.get("physical_model_sha256"),
            "attempted_stages": ["geometry_inventory"],
            "completed_stages": [],
            "failed_stage": "geometry_inventory",
            "failure_type": type(error).__name__,
            "failure_message": f"{type(error).__name__}: {error}",
            "official_R_T_A_created": False,
            "q_csr_created": False,
            "factor_created": False,
        }
        _write_json(output_directory / "v22_target_operator_probe.json", facts)
        return facts


__all__ = ["run_v22_target_operator_probe"]
