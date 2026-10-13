"""Selected regular-reference q0 build-only consumer for Task40 V25.

The route uses the frozen preflight mode inventory, a volume-only FFCx action,
and the production one-mode surface functional stream. It never constructs
the full carrier or an all-q reference operator.
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import struct
import time
from types import SimpleNamespace
from typing import Any, Callable, Mapping

import numpy as np
from scipy import sparse


_SCHEMA = "task40extra.review_v25_selected_reference_q0_consumer.v1"
_SURFACE_STREAM_HEADER = struct.Struct("<qQQd")
_VOLUME_STREAM_HEADER = struct.Struct("<II")
_CELL_STREAM_HEADER = struct.Struct("<iiii")


def _array_sha256(array: Any) -> str:
    value = np.asarray(array)
    view = memoryview(value).cast("B")
    digest = hashlib.sha256()
    chunk = 8 * 1024 * 1024
    for start in range(0, len(view), chunk):
        stop = min(start + chunk, len(view))
        digest.update(view[start:stop])
        _drop_mmap_pages(value, start, stop - start)
    return digest.hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        position = 0
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
            _advise_file_drop(stream, position, len(chunk))
            position += len(chunk)
    return digest.hexdigest()


def _verify_bound_payload_files(
    producer_root: Path,
    payload_records: Mapping[str, Any],
    required_names: tuple[str, ...],
) -> tuple[dict[str, Path], int, float]:
    """Verify real payload bytes against a service-bound size/SHA inventory."""
    started = time.perf_counter()
    paths: dict[str, Path] = {}
    total_bytes = 0
    root = Path(producer_root).resolve()
    for name in required_names:
        record = payload_records.get(name)
        path = (root / name).resolve()
        digest = record.get("sha256") if isinstance(record, Mapping) else None
        size = record.get("bytes") if isinstance(record, Mapping) else None
        if (
            Path(name).name != name
            or not path.is_relative_to(root)
            or not isinstance(record, Mapping)
            or type(size) is not int
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)
            or not path.is_file()
            or path.stat().st_size != size
        ):
            raise ValueError(f"V26 saved producer artifact size/hash binding is invalid: {name}")
        if _file_sha256(path) != digest:
            raise IOError(f"V26 saved producer payload differs from its verified SHA-256: {name}")
        paths[name] = path
        total_bytes += size
    return paths, total_bytes, float(time.perf_counter() - started)


def _drop_mmap_pages(array: Any, start: int, length: int) -> None:
    owner = array
    while getattr(owner, "base", None) is not None and not hasattr(owner, "_mmap"):
        owner = owner.base
    mapping = getattr(owner, "_mmap", None)
    advise = getattr(mapping, "madvise", None)
    option = getattr(__import__("mmap"), "MADV_DONTNEED", None)
    if callable(advise) and option is not None and length > 0:
        try:
            page = os.sysconf("SC_PAGE_SIZE")
            begin = start - start % page
            end = ((start + length + page - 1) // page) * page
            advise(option, begin, end - begin)
        except (OSError, ValueError, TypeError):
            pass


def _task_cgroup_memory_snapshot(
    *, cgroup_membership: str | None = None, cgroup_root: Path | None = None
) -> dict[str, Any]:
    """Read this process's cgroup v2 memory split without falling back to the host root."""
    try:
        membership = (
            Path("/proc/self/cgroup").read_text(encoding="utf-8")
            if cgroup_membership is None
            else cgroup_membership
        )
    except OSError as error:
        return {"status": "unavailable", "reason": f"cgroup_membership_read_failed:{type(error).__name__}"}
    unified_path = next(
        (line.split("::", 1)[1].strip() for line in membership.splitlines() if line.startswith("0::")),
        "",
    )
    if not unified_path or unified_path == "/":
        return {"status": "unavailable", "reason": "task_cgroup_membership_missing_or_root"}
    root = Path("/sys/fs/cgroup") if cgroup_root is None else Path(cgroup_root)
    try:
        resolved_root = root.resolve()
        relative = Path(unified_path.lstrip("/"))
        if ".." in relative.parts:
            return {"status": "unavailable", "reason": "task_cgroup_path_invalid"}
        target = (resolved_root / relative).resolve()
        if target == resolved_root or not target.is_relative_to(resolved_root):
            return {"status": "unavailable", "reason": "task_cgroup_path_invalid"}
        if not target.is_dir():
            return {"status": "unavailable", "reason": "task_cgroup_path_deleted"}
        memory_stat = {}
        for line in (target / "memory.stat").read_text(encoding="ascii").splitlines():
            fields = line.split()
            if len(fields) == 2 and fields[0] in {
                "anon", "file", "file_dirty", "file_writeback", "inactive_file",
                "active_file", "shmem", "kernel", "pagetables",
            }:
                memory_stat[fields[0]] = int(fields[1])
        current_path = target / "memory.current"
        current = int(current_path.read_text(encoding="ascii").strip()) if current_path.is_file() else None
    except (OSError, ValueError, TypeError) as error:
        return {"status": "unavailable", "reason": f"task_cgroup_memory_read_failed:{type(error).__name__}"}
    return {
        "status": "available",
        "cgroup_path": unified_path,
        "memory_current_bytes": current,
        "memory_stat_bytes": memory_stat,
    }


def _process_io_snapshot() -> dict[str, Any]:
    try:
        values = {}
        for line in Path("/proc/self/io").read_text(encoding="ascii").splitlines():
            key, separator, value = line.partition(":")
            if separator and key in {"rchar", "read_bytes", "syscr"}:
                values[key] = int(value.strip())
    except (OSError, ValueError) as error:
        return {"status": "unavailable", "reason": f"process_io_read_failed:{type(error).__name__}"}
    return {"status": "available", **values}


def _append_saved_stream_reader_sample(
    reader: str,
    telemetry: dict[str, Any],
    before_memory: Mapping[str, Any],
    before_io: Mapping[str, Any],
    start: float,
    advice_calls_before: int,
    advised_bytes_before: int,
    pass_completed: bool,
) -> None:
    after_memory = _task_cgroup_memory_snapshot()
    after_io = _process_io_snapshot()
    io_delta = {
        key: after_io[key] - before_io[key]
        for key in ("rchar", "read_bytes", "syscr")
        if before_io.get("status") == "available"
        and after_io.get("status") == "available"
        and type(before_io.get(key)) is int
        and type(after_io.get(key)) is int
    }
    telemetry.setdefault("samples", []).append({
        "reader": reader,
        "pass_completed": bool(pass_completed),
        "elapsed_seconds": float(time.perf_counter() - start),
        "advice_calls": int(telemetry.get("advice_calls", 0)) - advice_calls_before,
        "advised_bytes": int(telemetry.get("advised_bytes", 0)) - advised_bytes_before,
        "task_cgroup_memory_before": dict(before_memory),
        "task_cgroup_memory_after": after_memory,
        "process_io_before": dict(before_io),
        "process_io_after": after_io,
        "process_io_delta": io_delta,
    })


@contextmanager
def _saved_stream_reader_sample(reader: str, telemetry: dict[str, Any] | None):
    if telemetry is None:
        yield
        return
    start = time.perf_counter()
    memory_before = _task_cgroup_memory_snapshot()
    io_before = _process_io_snapshot()
    advice_calls_before = int(telemetry.get("advice_calls", 0))
    advised_bytes_before = int(telemetry.get("advised_bytes", 0))
    pass_completed = False
    try:
        yield
        pass_completed = True
    finally:
        _append_saved_stream_reader_sample(
            reader,
            telemetry,
            memory_before,
            io_before,
            start,
            advice_calls_before,
            advised_bytes_before,
            pass_completed,
        )


def _new_saved_stream_reader_telemetry() -> dict[str, Any]:
    return {
        "schema": "task40extra.review_v26_saved_stream_reader_telemetry.v1",
        "sample_scope": "per-reader pass; task cgroup only, unavailable if /proc/self/cgroup path is absent/deleted",
        "advice_policy": "POSIX_FADV_DONTNEED only for byte ranges already copied into owned arrays",
        "advised_bytes_semantics": "successful page-aligned advice-range lengths; not measured memory released",
        "advice_calls": 0,
        "advised_bytes": 0,
        "samples": [],
    }


def _advise_file_drop(
    stream: Any, start: int, length: int, *, telemetry: dict[str, Any] | None = None
) -> int:
    if length <= 0 or not hasattr(os, "posix_fadvise"):
        return 0
    option = getattr(os, "POSIX_FADV_DONTNEED", None)
    if option is None:
        return 0
    try:
        page = os.sysconf("SC_PAGE_SIZE")
        begin = start - start % page
        end = ((start + length + page - 1) // page) * page
        os.posix_fadvise(stream.fileno(), begin, end - begin, option)
    except (OSError, ValueError, TypeError):
        return 0
    advised = end - begin
    if telemetry is not None:
        telemetry["advice_calls"] = int(telemetry.get("advice_calls", 0)) + 1
        telemetry["advised_bytes"] = int(telemetry.get("advised_bytes", 0)) + advised
    return advised


def _array_equal_chunked(left: Any, right: Any, *, chunk_bytes: int = 8 * 1024 * 1024) -> bool:
    a, b = np.asarray(left), np.asarray(right)
    if a.shape != b.shape or a.dtype != b.dtype:
        return False
    a_view = memoryview(a).cast("B")
    b_view = memoryview(b).cast("B")
    for start in range(0, len(a_view), int(chunk_bytes)):
        stop = min(start + int(chunk_bytes), len(a_view))
        if a_view[start:stop] != b_view[start:stop]:
            return False
        _drop_mmap_pages(a, start, stop - start)
        _drop_mmap_pages(b, start, stop - start)
    return True


def _count_nonzero_chunked(array: Any, *, chunk_entries: int = 1_000_000) -> int:
    value = np.asarray(array)
    count = 0
    for start in range(0, value.size, int(chunk_entries)):
        stop = min(start + int(chunk_entries), value.size)
        count += int(np.count_nonzero(value[start:stop]))
        _drop_mmap_pages(value, start * value.dtype.itemsize, (stop - start) * value.dtype.itemsize)
    return count


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    temp = path.with_name(path.name + ".tmp")
    payload = (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        + "\n"
    ).encode("utf-8")
    with temp.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _save_npy(path: Path, array: Any) -> None:
    temp = path.with_name(path.name + ".tmp")
    with temp.open("xb") as stream:
        np.save(stream, np.asarray(array), allow_pickle=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def _save_npz_atomic(path: Path, **arrays: Any) -> None:
    """Atomically persist a related group of numeric arrays without pickle."""
    temp = path.with_name(path.name + ".tmp")
    if path.exists() or temp.exists():
        raise FileExistsError(f"refusing to replace existing numeric checkpoint: {path}")
    with temp.open("xb") as stream:
        np.savez(stream, **arrays)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _bound_consumer_artifact_reference(
    path: str | Path,
    *,
    output_root: str | Path,
    producer_root: str | Path | None = None,
) -> dict[str, str]:
    """Bind a read-only producer artifact to the directory that owns it."""
    artifact = Path(path).resolve()
    output = Path(output_root).resolve()
    producer = Path(producer_root).resolve() if producer_root is not None else None
    if producer is not None and artifact.is_relative_to(producer):
        return {
            "path": str(artifact.relative_to(producer)),
            "root_binding": "saved_v25_producer_root",
            "artifact_root": str(producer),
        }
    if artifact.is_relative_to(output):
        return {
            "path": str(artifact.relative_to(output)),
            "root_binding": "consumer_output_root",
            "artifact_root": str(output),
        }
    raise ValueError("selected q0 consumer artifact is outside its explicitly bound roots")


def _q0_source_mode_rows_from_runtime_view(
    runtime_rows: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]],
    modes: tuple[Any, ...] | list[Any],
    *,
    expected_manifest_sha256: str,
    boundary_planes_nm_by_side: Mapping[str, float],
) -> tuple[tuple[Mapping[str, Any], ...], dict[str, Any]]:
    """Recover only the frozen source rows after verifying the runtime plane view."""
    from .fullspace_dtn_action import (
        FULLSPACE_DTN_MANIFEST_SCHEMA,
        FULLSPACE_DTN_PROFILE,
        _canonical_json_bytes,
    )

    if not runtime_rows or len(runtime_rows) != len(modes):
        raise ValueError("q0 runtime mode rows differ from the complete frozen mode table")
    source_rows: list[dict[str, Any]] = []
    plane_counts = {"bottom": 0, "top": 0}
    for index, (runtime_row, mode) in enumerate(zip(runtime_rows, modes, strict=True)):
        if not isinstance(runtime_row, Mapping):
            raise ValueError("q0 runtime mode view contains a non-mapping row")
        side = str(runtime_row.get("side", ""))
        if side not in plane_counts or side not in boundary_planes_nm_by_side:
            raise ValueError("q0 runtime mode view contains an unsupported reference-plane side")
        expected_plane = float(boundary_planes_nm_by_side[side])
        runtime_plane = runtime_row.get("reference_plane_nm")
        if (
            isinstance(runtime_plane, bool)
            or not isinstance(runtime_plane, (int, float))
            or not np.isfinite(runtime_plane)
            or float(runtime_plane) != expected_plane
        ):
            raise ValueError("q0 runtime reference plane differs from the actual boundary-plane context")
        if (
            int(runtime_row.get("mode_index", -1)) != index
            or side != str(mode.side)
            or int(runtime_row.get("m", 0)) != int(mode.m)
            or int(runtime_row.get("n", 0)) != int(mode.n)
            or str(runtime_row.get("polarization")) != str(mode.polarization)
        ):
            raise ValueError("q0 runtime mode row identity differs from the frozen ordered mode table")
        source_row = dict(runtime_row)
        del source_row["reference_plane_nm"]
        if "reference_plane_nm" in source_row:
            raise ValueError("q0 source row unexpectedly retains a runtime-only reference plane")
        source_rows.append(source_row)
        plane_counts[side] += 1

    payload = {
        "schema": FULLSPACE_DTN_MANIFEST_SCHEMA,
        "profile": FULLSPACE_DTN_PROFILE,
        "mode_count": len(source_rows),
        "modes": source_rows,
    }
    source_sha256 = hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()
    if source_sha256 != str(expected_manifest_sha256):
        raise ValueError(
            "q0 runtime rows differ from the frozen source manifest after removing only reference_plane_nm"
        )
    planes = {
        side: float(boundary_planes_nm_by_side[side])
        for side in ("bottom", "top")
    }
    return tuple(source_rows), {
        "source_manifest_sha256": source_sha256,
        "runtime_view_added_only": "reference_plane_nm",
        "runtime_reference_plane_nm_by_side": planes,
        "runtime_mode_count_by_side": plane_counts,
        "source_rows_match_after_plane_removal": True,
    }


def _q0_reference_surface_inventory(mesh_data: Any, space: Any, cfg: Any):
    """Build exact native-rule rows from the actual local reference mesh."""
    mesh = space.mesh
    topology = mesh.topology
    if int(topology.dim) != 3:
        raise ValueError("q0 native surface mapping requires the actual three-dimensional reference mesh")
    topology.create_entity_permutations()
    topology.create_connectivity(2, 3)
    facet_to_cell = topology.connectivity(2, 3)
    owned_cells = int(topology.index_map(3).size_local)
    geometry_dofmap = np.asarray(mesh.geometry.dofmap, dtype=np.int32)
    geometry = np.asarray(mesh.geometry.x, dtype=np.float64)
    permutation_info = np.asarray(topology.get_cell_permutation_info(), dtype=np.uint32)
    if (
        geometry_dofmap.shape != (owned_cells, 8)
        or geometry.shape[1] != 3
        or permutation_info.shape != (owned_cells,)
    ):
        raise ValueError("q0 actual reference mesh is not the registered affine hexahedral inventory")

    axis_counts = tuple(int(value) for value in cfg.mesh_axis_cell_counts)
    if len(axis_counts) != 3 or min(axis_counts) <= 0:
        raise ValueError("q0 actual reference mesh axis-cell counts are invalid")
    expected_facets_per_side = axis_counts[0] * axis_counts[1]
    boundaries = (
        ("bottom", int(cfg.tags.z_min), float(cfg.physical_z_min), False),
        ("top", int(cfg.tags.z_max), float(cfg.physical_z_max), True),
    )
    mapping_rows: list[dict[str, Any]] = []
    cells_by_side: dict[str, set[int]] = {"bottom": set(), "top": set()}
    dofs_by_side: dict[str, list[np.ndarray]] = {"bottom": [], "top": []}
    seen_facets: set[int] = set()
    for side, tag, boundary_z, upper_face in boundaries:
        facets = np.asarray(mesh_data.facet_tags.find(tag), dtype=np.int32).reshape(-1)
        if (
            len(facets) != expected_facets_per_side
            or len(np.unique(facets)) != len(facets)
        ):
            raise ValueError(
                f"q0 {side} boundary-facet coverage differs from the complete local reference plane"
            )
        for facet_id in sorted(map(int, facets)):
            if facet_id in seen_facets:
                raise ValueError("q0 reference facet was assigned to more than one port side")
            seen_facets.add(facet_id)
            adjacent = tuple(int(cell) for cell in facet_to_cell.links(facet_id))
            if len(adjacent) != 1:
                raise ValueError("q0 reference port facet must have exactly one local adjacent cell")
            cell_id = adjacent[0]
            if cell_id < 0 or cell_id >= owned_cells or cell_id in cells_by_side[side]:
                raise ValueError("q0 reference facet has an invalid or duplicate adjacent cell")
            points = np.asarray(geometry[geometry_dofmap[cell_id]], dtype=np.float64)
            if points.shape != (8, 3) or not np.isfinite(points).all():
                raise ValueError("q0 reference cell geometry is not eight finite hexahedral vertices")
            lower = points.min(axis=0)
            upper = points.max(axis=0)
            if np.any(upper <= lower):
                raise ValueError("q0 reference cell has nonpositive axis-aligned geometry")
            ordered = np.asarray(
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
            if not np.array_equal(points, ordered):
                raise ValueError(
                    "q0 native facet rule requires the actual geometry-dofmap vertex order "
                    "to match its canonical affine hexahedron order"
                )
            actual_plane = float(upper[2] if upper_face else lower[2])
            if actual_plane != boundary_z:
                raise ValueError("q0 reference facet tag does not match its physical boundary plane")
            local_dofs = np.asarray(space.dofmap.cell_dofs(cell_id), dtype=np.int32)
            if local_dofs.shape != (882,):
                raise ValueError("q0 native facet rule requires all 882 p6 local cell rows")
            widths = np.ascontiguousarray(upper - lower, dtype="<f8")
            class_id = "reference-" + hashlib.sha256(widths.tobytes()).hexdigest()[:16]
            mapping_rows.append(
                {
                    "side": side,
                    "class_id": class_id,
                    "cell_id": cell_id,
                    "cell_permutation": int(permutation_info[cell_id]),
                    "facet_id": facet_id,
                    "cell_bounds_nm": np.column_stack((lower, upper)),
                    "ordered_cell_coordinates_nm": points,
                }
            )
            cells_by_side[side].add(cell_id)
            dofs_by_side[side].append(local_dofs.astype(np.int64, copy=False))
    if cells_by_side["bottom"] & cells_by_side["top"]:
        raise ValueError("q0 bottom and top reference planes share a boundary-adjacent cell")

    dof_index_map = space.dofmap.index_map
    cell_dof_digest = hashlib.sha256()
    for cell_id in range(owned_cells):
        local_dofs = np.asarray(space.dofmap.cell_dofs(cell_id), dtype=np.int32)
        global_dofs = np.ascontiguousarray(
            dof_index_map.local_to_global(local_dofs)
        )
        cell_dof_digest.update(np.asarray([cell_id], dtype="<i8").tobytes())
        cell_dof_digest.update(global_dofs.tobytes())
    support_groups = tuple(
        np.asarray(sorted(cells_by_side[side]), dtype=np.int32)
        for side in ("bottom", "top")
    )
    allowed_rows = tuple(
        np.unique(np.concatenate(dofs_by_side[side]))
        for side in ("bottom", "top")
    )
    inventory = {
        "facet_count_by_side": {
            side: sum(row["side"] == side for row in mapping_rows)
            for side in ("bottom", "top")
        },
        "boundary_cell_count_by_side": {
            side: int(len(cells_by_side[side])) for side in ("bottom", "top")
        },
        "cell_dofs_per_boundary_cell": 882,
        "cell_dofmap_sha256": cell_dof_digest.hexdigest(),
    }
    return tuple(mapping_rows), support_groups, allowed_rows, permutation_info, inventory


def _is_in_sorted_rows(rows: np.ndarray, allowed: np.ndarray) -> np.ndarray:
    if not rows.size:
        return np.empty(0, dtype=bool)
    positions = np.searchsorted(allowed, rows)
    valid = positions < len(allowed)
    candidates = np.flatnonzero(valid)
    valid[candidates] = allowed[positions[candidates]] == rows[candidates]
    return valid


def _write_surface_functional_stream(
    path: Path,
    entries: Any,
    *,
    selected_indices: np.ndarray,
    local_modes: tuple[Any, ...],
    local_h: np.ndarray,
    allowed_rows_by_side: tuple[np.ndarray, np.ndarray],
    interior_rows: np.ndarray,
) -> dict[str, Any]:
    """Persist the exact production B/D stream one mode at a time."""
    temp = path.with_name(path.name + ".tmp")
    if path.exists() or temp.exists():
        raise FileExistsError(f"refusing to replace existing selected-q surface stream: {path}")
    digest = hashlib.sha256()
    internal_counts = {"B": 0, "D": 0}
    internal_nonzero_counts = {"B": 0, "D": 0}
    rows_by_side = {"bottom": 0, "top": 0}
    byte_count = 0
    emitted = 0
    try:
        with temp.open("xb") as stream:
            for port, entry in enumerate(entries):
                if port >= len(selected_indices):
                    raise ValueError("production surface stream emitted more modes than selected aliases")
                global_index = int(selected_indices[port])
                mode = local_modes[port]
                expected_key = _mode_key(global_index, mode)
                if tuple(getattr(entry, "mode_key", ())) != expected_key:
                    raise ValueError("production surface stream order differs from the frozen alias inventory")
                normalization_h = float(entry.normalization_h)
                if not np.isfinite(normalization_h) or normalization_h != float(local_h[port]):
                    raise ValueError("production surface H_p differs from the frozen local/global scaling")
                side = str(mode.side)
                if side not in ("bottom", "top"):
                    raise ValueError("production surface stream emitted an unsupported port side")
                allowed = allowed_rows_by_side[0 if side == "bottom" else 1]
                arrays = []
                for component, row_name, value_name in (
                    ("B", "coupling_rows", "coupling_values"),
                    ("D", "projection_rows", "projection_values"),
                ):
                    rows = np.asarray(getattr(entry, row_name)).reshape(-1)
                    values = np.asarray(getattr(entry, value_name), dtype=np.complex128).reshape(-1)
                    if rows.dtype.kind not in "iu" or rows.size != values.size or not np.isfinite(values).all():
                        raise ValueError(f"production {component} stream has invalid finite row/value data")
                    if rows.size and (int(rows.min()) < 0 or int(rows.max()) > np.iinfo(np.int32).max):
                        raise OverflowError("saved direct row index exceeds qualified int32 PETSc")
                    if rows.size > 1 and np.any(rows[1:] <= rows[:-1]):
                        raise ValueError(f"production {component} rows are not sorted and unique")
                    rows64 = rows.astype(np.int64, copy=False)
                    if not np.all(_is_in_sorted_rows(rows64, allowed)):
                        raise ValueError(f"production {component} rows escape their tagged boundary slab")
                    internal_positions = np.searchsorted(interior_rows, rows64)
                    is_internal = internal_positions < len(interior_rows)
                    candidates = np.flatnonzero(is_internal)
                    is_internal[candidates] = interior_rows[internal_positions[candidates]] == rows64[candidates]
                    internal_counts[component] += int(np.count_nonzero(is_internal))
                    internal_nonzero_counts[component] += int(np.count_nonzero(values[is_internal] != 0.0))
                    arrays.extend((rows, values))
                header = _SURFACE_STREAM_HEADER.pack(
                    global_index, len(arrays[0]), len(arrays[2]), normalization_h
                )
                stream.write(header)
                digest.update(header)
                byte_count += len(header)
                for array, dtype in zip(arrays, ("<i4", "<c16", "<i4", "<c16"), strict=True):
                    value = np.ascontiguousarray(array, dtype=dtype)
                    raw = memoryview(value).cast("B")
                    stream.write(raw)
                    digest.update(raw)
                    byte_count += len(raw)
                rows_by_side[side] += len(arrays[0]) + len(arrays[2])
                emitted += 1
            if emitted != len(selected_indices):
                raise ValueError(f"production surface stream emitted {emitted} modes; expected {len(selected_indices)}")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    except Exception as error:
        partial_path = path.with_name(path.name + ".partial")
        if temp.exists():
            os.replace(temp, partial_path)
            partial_facts = {
                "schema": "task40extra.review_v25_selected_q0_surface_stream_partial.v1",
                "status": "INCOMPLETE_RETAINED",
                "completed_mode_count": emitted,
                "expected_mode_count": int(len(selected_indices)),
                "bytes_written": int(partial_path.stat().st_size),
                "sha256": _file_sha256(partial_path),
                "error_type": type(error).__name__,
                "error_message": str(error),
                "internal_row_entry_count_so_far": internal_counts,
                "internal_nonzero_entry_count_so_far": internal_nonzero_counts,
            }
            _write_json(Path(str(partial_path) + ".json"), partial_facts)
        raise
    return {
        "path": str(path),
        "bytes": byte_count,
        "sha256": digest.hexdigest(),
        "mode_count": emitted,
        "rows_by_side": rows_by_side,
        "internal_row_entry_count": internal_counts,
        "internal_nonzero_entry_count": internal_nonzero_counts,
        "numeric_internal_support_empty": not any(internal_nonzero_counts.values()),
        "format": "little-endian mode-framed int32 rows and complex128 values; original MPC-processed rows retained",
    }


def _iter_saved_surface_functionals(
    path: Path,
    *,
    selected_indices: np.ndarray,
    local_modes: tuple[Any, ...],
    local_h: np.ndarray,
    mode_rows: tuple[Mapping[str, Any], ...],
    interior_rows: np.ndarray,
    active_lookup: np.ndarray | None = None,
    active_rows: int | None = None,
    reader_telemetry: dict[str, Any] | None = None,
):
    """Replay one original selected port functional from the framed raw stream."""
    with _saved_stream_reader_sample(
        "surface", reader_telemetry
    ), path.open("rb") as stream:
        for port, global_index_value in enumerate(selected_indices):
            frame_start = stream.tell()
            header = stream.read(_SURFACE_STREAM_HEADER.size)
            if len(header) != _SURFACE_STREAM_HEADER.size:
                raise IOError("saved selected-q surface stream ended before its mode inventory")
            global_index, b_count, d_count, normalization_h = _SURFACE_STREAM_HEADER.unpack(header)
            global_index = int(global_index)
            if global_index != int(global_index_value) or normalization_h != float(local_h[port]):
                raise ValueError("saved selected-q surface stream mode/H identity changed")
            arrays = []
            for count, dtype in ((b_count, "<i4"), (b_count, "<c16"), (d_count, "<i4"), (d_count, "<c16")):
                value = np.fromfile(stream, dtype=np.dtype(dtype), count=int(count))
                if value.size != int(count):
                    raise IOError("saved selected-q surface stream contains a truncated array")
                arrays.append(value)
            frame_length = stream.tell() - frame_start
            _advise_file_drop(stream, frame_start, frame_length, telemetry=reader_telemetry)
            for rows_index, values_index in ((0, 1), (2, 3)):
                rows = arrays[rows_index].astype(np.int64, copy=False)
                values = arrays[values_index]
                if not np.isfinite(values).all():
                    raise ValueError("saved selected-q surface stream contains non-finite values")
                if active_lookup is not None:
                    if active_rows is None or active_rows < 0:
                        raise ValueError("saved surface row validation requires the active trace row bound")
                    if rows.size and (int(rows.min()) < 0 or int(rows.max()) >= len(active_lookup)):
                        raise ValueError("saved selected-q surface stream row is outside the original lookup")
                    active_ids = np.asarray(active_lookup[rows], dtype=np.int64)
                    if np.any(active_ids >= int(active_rows)):
                        raise ValueError("saved selected-q surface row maps beyond active trace rows")
                    unmapped = active_ids < 0
                    if np.any(unmapped & (values != 0.0)):
                        raise ValueError("nonzero saved surface functional row has no active trace mapping")
                else:
                    active_ids = None
                positions = np.searchsorted(interior_rows, rows)
                internal = positions < len(interior_rows)
                candidates = np.flatnonzero(internal)
                internal[candidates] = interior_rows[positions[candidates]] == rows[candidates]
                # Exact-zero interior payloads remain in the authoritative
                # spool; omitting them from the numeric direct view is lossless.
                keep = ~internal | (values != 0.0)
                if active_ids is not None:
                    keep &= ~unmapped
                arrays[rows_index] = np.ascontiguousarray(arrays[rows_index][keep], dtype=np.int32)
                arrays[values_index] = np.ascontiguousarray(values[keep], dtype=np.complex128)
            mode = local_modes[port]
            yield SimpleNamespace(
                mode_key=_mode_key(global_index, mode),
                normalization_h=float(normalization_h),
                mode_identity=mode_rows[global_index],
                coupling_rows=arrays[0],
                coupling_values=arrays[1],
                projection_rows=arrays[2],
                projection_values=arrays[3],
            )
        if stream.read(1):
            raise IOError("saved selected-q surface stream has trailing bytes after all modes")


def _load_saved_v26_active_lookup(
    active_lookup_path: str | Path,
    *,
    condensed_system: Any,
    expected_full_rows: int,
    allocation_gate: Callable[[str, Mapping[str, Any]], Any],
) -> tuple[np.ndarray, int]:
    """Compare the producer lookup with the fresh finalized MPC before action creation."""
    full_rows = int(condensed_system.full_rows)
    active_rows = int(condensed_system.active_rows)
    if full_rows != int(expected_full_rows) or active_rows < 0:
        raise ValueError("fresh condensed q0 row inventory differs from the registered profile")
    allocation_gate(
        "task40_v26_saved_lookup_compare_with_fresh_local_mpc",
        {
            "additional_payload_bytes": int(full_rows * np.dtype(np.int32).itemsize),
            "workspace_bytes": int(full_rows * np.dtype(np.int32).itemsize),
            "disk_payload_bytes": 0,
            "mapping_source": "fresh finalized condensation trace_constraints.original_to_active",
            "saved_lookup_source": "hash-bound V25 producer payload",
        },
    )
    expected_lookup = np.full(full_rows, -1, dtype=np.int32)
    for original, active_index in condensed_system.trace_constraints.original_to_active.items():
        expected_lookup[int(original)] = int(active_index)
    loaded_lookup = np.load(Path(active_lookup_path), mmap_mode="r", allow_pickle=False)
    if (
        loaded_lookup.shape != expected_lookup.shape
        or loaded_lookup.dtype != np.dtype(np.int32)
        or not _array_equal_chunked(loaded_lookup, expected_lookup)
    ):
        raise ValueError("saved V25 original-to-active lookup differs from the fresh local FE/MPC map")
    del expected_lookup
    return loaded_lookup, active_rows


def _make_saved_v26_surface_provider(
    *,
    path: Path,
    selected_indices: np.ndarray,
    local_modes: tuple[Any, ...],
    local_h: np.ndarray,
    mode_rows: tuple[Mapping[str, Any], ...],
    interior_rows: np.ndarray,
    active_lookup: np.ndarray | None,
    active_rows: int,
    counters: dict[str, int],
    reader_telemetry: dict[str, Any] | None = None,
):
    """Capture the finalized active-row count before action construction starts."""
    captured_active_rows = int(active_rows)

    def provider():
        counters["provider_sweep_count"] += 1
        yield from _iter_saved_surface_functionals(
            path,
            selected_indices=selected_indices,
            local_modes=local_modes,
            local_h=local_h,
            mode_rows=mode_rows,
            interior_rows=interior_rows,
            active_lookup=active_lookup,
            active_rows=captured_active_rows,
            reader_telemetry=reader_telemetry,
        )

    return provider


def _audit_saved_surface_functional_stream(
    path: Path,
    *,
    selected_indices: np.ndarray,
    local_modes: tuple[Any, ...],
    local_h: np.ndarray,
    allowed_rows_by_side: tuple[np.ndarray, np.ndarray],
    interior_rows: np.ndarray,
    active_lookup: np.ndarray,
    active_rows: int,
    allocation_gate: Callable[[str, Mapping[str, Any]], Any],
    reader_telemetry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate the complete saved B/D stream against the freshly built local FE rows."""
    file_size = int(path.stat().st_size)
    max_mode_payload = 0
    with path.open("rb") as stream:
        for port, global_index in enumerate(selected_indices):
            header = stream.read(_SURFACE_STREAM_HEADER.size)
            if len(header) != _SURFACE_STREAM_HEADER.size:
                raise IOError("saved V25 surface stream ended before all selected aliases")
            recorded_index, b_count, d_count, h_value = _SURFACE_STREAM_HEADER.unpack(header)
            if recorded_index != int(global_index) or h_value != float(local_h[port]):
                raise ValueError("saved V25 surface stream does not match the current alias/H inventory")
            if b_count > np.iinfo(np.int32).max or d_count > np.iinfo(np.int32).max:
                raise OverflowError("saved V25 surface row count exceeds the qualified index width")
            payload_bytes = (int(b_count) + int(d_count)) * (4 + 16)
            max_mode_payload = max(max_mode_payload, payload_bytes)
            stream.seek(payload_bytes, os.SEEK_CUR)
            if stream.tell() > file_size:
                raise IOError("saved V25 surface stream is truncated inside a mode payload")
        if stream.read(1):
            raise IOError("saved V25 surface stream has trailing bytes after all selected aliases")
    allocation_gate(
        "task40_v26_saved_surface_stream_audit_buffers",
        {
            "additional_payload_bytes": int(4 * max_mode_payload),
            "max_single_mode_raw_payload_bytes": int(max_mode_payload),
            "mode_count": int(len(selected_indices)),
            "disk_payload_bytes": 0,
            "one_mode_at_a_time": True,
        },
    )

    row_entries = {"B": 0, "D": 0}
    nonzero_entries = {"B": 0, "D": 0}
    rows_by_side = {"bottom": 0, "top": 0}
    digest = hashlib.sha256()
    with _saved_stream_reader_sample(
        "surface_audit", reader_telemetry
    ), path.open("rb") as stream:
        for port, global_index_value in enumerate(selected_indices):
            frame_start = stream.tell()
            header = stream.read(_SURFACE_STREAM_HEADER.size)
            if len(header) != _SURFACE_STREAM_HEADER.size:
                raise IOError("saved V25 surface stream ended during row audit")
            digest.update(header)
            global_index, b_count, d_count, h_value = _SURFACE_STREAM_HEADER.unpack(header)
            if int(global_index) != int(global_index_value) or h_value != float(local_h[port]):
                raise ValueError("saved V25 surface stream mode/H identity changed during row audit")
            mode = local_modes[port]
            side = str(mode.side)
            if side not in {"bottom", "top"}:
                raise ValueError("saved V25 surface stream contains an unsupported boundary side")
            allowed = allowed_rows_by_side[0 if side == "bottom" else 1]
            for component, count in (("B", int(b_count)), ("D", int(d_count))):
                rows = np.fromfile(stream, dtype=np.dtype("<i4"), count=count)
                if rows.size != count:
                    raise IOError("saved V25 surface stream has truncated row indices")
                values = np.fromfile(stream, dtype=np.dtype("<c16"), count=count)
                if values.size != count or not np.isfinite(values).all():
                    raise ValueError("saved V25 surface stream has truncated or non-finite values")
                digest.update(memoryview(rows).cast("B"))
                digest.update(memoryview(values).cast("B"))
                if rows.size and (
                    int(rows.min()) < 0
                    or int(rows.max()) >= len(active_lookup)
                    or (rows.size > 1 and np.any(rows[1:] <= rows[:-1]))
                    or not np.all(_is_in_sorted_rows(rows.astype(np.int64, copy=False), allowed))
                ):
                    raise ValueError("saved V25 surface rows are outside the sorted tagged boundary inventory")
                if rows.size:
                    active_ids = np.asarray(active_lookup[rows], dtype=np.int64)
                    if np.any(active_ids >= int(active_rows)):
                        raise ValueError("saved V25 surface row maps beyond the active trace domain")
                    unmapped = active_ids < 0
                    if np.any(unmapped & (values != 0.0)):
                        raise ValueError("nonzero saved V25 surface row has no active FE mapping")
                    row64 = rows.astype(np.int64, copy=False)
                    positions = np.searchsorted(interior_rows, row64)
                    is_internal = positions < len(interior_rows)
                    candidates = np.flatnonzero(is_internal)
                    is_internal[candidates] = interior_rows[positions[candidates]] == row64[candidates]
                    row_entries[component] += int(np.count_nonzero(is_internal))
                    nonzero_entries[component] += int(
                        np.count_nonzero(is_internal & (values != 0.0))
                    )
                    rows_by_side[side] += count
            _advise_file_drop(stream, frame_start, stream.tell() - frame_start, telemetry=reader_telemetry)
        if stream.read(1):
            raise IOError("saved V25 surface stream has trailing bytes after row audit")
    return {
        "path": str(path),
        "bytes": file_size,
        "sha256": digest.hexdigest(),
        "mode_count": int(len(selected_indices)),
        "rows_by_side": rows_by_side,
        "internal_row_entry_count": row_entries,
        "internal_nonzero_entry_count": nonzero_entries,
        "numeric_internal_support_empty": not any(nonzero_entries.values()),
        "row_route_validated_against_current_local_fe": True,
        "unmapped_row_policy": "only in-range exact-zero values may be skipped",
    }


def _write_volume_class_stream(path: Path, action: Any, allocation_gate: Callable) -> dict[str, Any]:
    """Persist each unique local Schur once and every cell's exact active map."""
    temp = path.with_name(path.name + ".tmp")
    if path.exists() or temp.exists():
        raise FileExistsError(f"refusing to replace existing volume stream: {path}")
    class_ids: dict[Any, int] = {}
    class_matrices: list[np.ndarray] = []
    cell_class_ids = np.empty(len(action._cells), dtype=np.int32)
    for index, cell in enumerate(action._cells):
        class_key = cell.class_key
        class_id = class_ids.get(class_key)
        if class_id is None:
            class_id = len(class_ids)
            class_ids[class_key] = class_id
            class_matrices.append(np.asarray(cell.S_V, dtype=np.complex128))
        cell_class_ids[index] = class_id
    class_payload = sum(int(matrix.nbytes) for matrix in class_matrices)
    max_cell_payload = max(
        (
            int(cell.active_ids.nbytes + cell.expansion.indptr.nbytes
                + cell.expansion.indices.nbytes + cell.expansion.data.nbytes)
            for cell in action._cells
        ),
        default=0,
    )
    expected_disk_bytes = (
        len(b"TASK40V25Q0VOLUME\0")
        + 8
        + 8 * len(class_matrices)
        + class_payload
        + sum(
        16 + int(cell.active_ids.nbytes + cell.expansion.indptr.nbytes
                 + cell.expansion.indices.nbytes + cell.expansion.data.nbytes)
        for cell in action._cells
        )
    )
    allocation_gate("task40_v25_q0_volume_stream_write", {
        "matrix_payload_bytes": int(max((matrix.nbytes for matrix in class_matrices), default=0)),
        "workspace_bytes": max_cell_payload,
        "disk_payload_bytes": int(expected_disk_bytes),
        "unique_class_schur_count": len(class_matrices),
        "cell_mapping_count": len(action._cells),
        "each_unique_class_schur_written_once": True,
        "per_cell_expanded_volume_coo_written": False,
    })
    try:
        with temp.open("xb") as stream:
            stream.write(b"TASK40V25Q0VOLUME\0")
            stream.write(struct.pack("<II", len(class_matrices), len(action._cells)))
            for matrix in class_matrices:
                if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1] or not np.isfinite(matrix).all():
                    raise ValueError("volume stream contains an invalid local Schur class")
                stream.write(struct.pack("<II", *matrix.shape))
                np.ascontiguousarray(matrix, dtype="<c16").tofile(stream)
            for class_id, cell in zip(cell_class_ids, action._cells, strict=True):
                expansion = sparse.csr_matrix(cell.expansion, copy=False)
                active = np.ascontiguousarray(cell.active_ids, dtype="<i4")
                indptr = np.ascontiguousarray(expansion.indptr, dtype="<i4")
                indices = np.ascontiguousarray(expansion.indices, dtype="<i4")
                values = np.ascontiguousarray(expansion.data, dtype="<c16")
                stream.write(struct.pack(
                    "<iiii", int(class_id), len(active), int(expansion.shape[0]), int(expansion.nnz)
                ))
                active.tofile(stream)
                indptr.tofile(stream)
                indices.tofile(stream)
                values.tofile(stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    except Exception:
        temp.unlink(missing_ok=True)
        raise
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": _file_sha256(path),
        "unique_class_schur_count": len(class_matrices),
        "unique_class_schur_payload_bytes": class_payload,
        "cell_mapping_count": len(action._cells),
        "maximum_single_cell_mapping_payload_bytes": max_cell_payload,
        "per_cell_expanded_volume_coo_written": False,
    }


def _scan_persisted_volume_stream(path: Path) -> dict[str, int]:
    """Validate all saved volume headers and size the complete reload before allocation."""
    file_size = int(path.stat().st_size)
    with path.open("rb") as stream:
        magic = b"TASK40V25Q0VOLUME\0"
        if stream.read(len(magic)) != magic:
            raise IOError("saved q0 volume stream has an unknown header")
        header = stream.read(8)
        if len(header) != 8:
            raise IOError("saved q0 volume stream has a truncated inventory header")
        class_count, cell_count = struct.unpack("<II", header)
        if class_count == 0 or cell_count == 0:
            raise ValueError("saved q0 volume stream has an empty class or cell inventory")
        class_payload_bytes = 0
        class_shapes: list[tuple[int, int]] = []
        for _ in range(class_count):
            raw = stream.read(8)
            if len(raw) != 8:
                raise IOError("saved q0 volume stream ended inside class metadata")
            nrow, ncol = struct.unpack("<II", raw)
            if nrow == 0 or nrow != ncol:
                raise ValueError("saved q0 volume stream contains a nonsquare or empty class")
            byte_count = int(nrow) * int(ncol) * np.dtype(np.complex128).itemsize
            class_payload_bytes += byte_count
            class_shapes.append((int(nrow), int(ncol)))
            stream.seek(byte_count, os.SEEK_CUR)
            if stream.tell() > file_size:
                raise IOError("saved q0 volume stream ended inside a class matrix")
        mapping_payload_bytes = 0
        maximum_cell_payload_bytes = 0
        maximum_active_count = 0
        maximum_trace_count = 0
        for _ in range(cell_count):
            raw = stream.read(_CELL_STREAM_HEADER.size)
            if len(raw) != _CELL_STREAM_HEADER.size:
                raise IOError("saved q0 volume stream ended inside cell mapping metadata")
            class_id, nactive, ntrace, nnz = _CELL_STREAM_HEADER.unpack(raw)
            if (
                class_id < 0
                or
                class_id >= class_count
                or nactive <= 0
                or ntrace <= 0
                or nnz < 0
                or class_shapes[int(class_id)][0] != ntrace
            ):
                raise ValueError("saved q0 volume stream contains invalid cell dimensions or class id")
            cell_payload = (
                4 * int(nactive)
                + 4 * (int(ntrace) + 1)
                + 4 * int(nnz)
                + np.dtype(np.complex128).itemsize * int(nnz)
            )
            mapping_payload_bytes += cell_payload
            maximum_cell_payload_bytes = max(maximum_cell_payload_bytes, cell_payload)
            maximum_active_count = max(maximum_active_count, int(nactive))
            maximum_trace_count = max(maximum_trace_count, int(ntrace))
            stream.seek(cell_payload, os.SEEK_CUR)
            if stream.tell() > file_size:
                raise IOError("saved q0 volume stream ended inside cell expansion data")
        if stream.read(1):
            raise IOError("saved q0 volume stream has trailing bytes")
    return {
        "class_count": int(class_count),
        "cell_count": int(cell_count),
        "class_payload_bytes": int(class_payload_bytes),
        "mapping_payload_bytes": int(mapping_payload_bytes),
        "maximum_cell_payload_bytes": int(maximum_cell_payload_bytes),
        "maximum_active_count": int(maximum_active_count),
        "maximum_trace_count": int(maximum_trace_count),
    }


def _apply_persisted_volume_stream(
    path: Path,
    active: np.ndarray,
    *,
    active_rows: int,
    allocation_gate: Callable,
    reader_telemetry: dict[str, Any] | None = None,
) -> np.ndarray:
    """Apply the saved shared-class Schur owner without consulting live cells."""
    layout = _scan_persisted_volume_stream(path)
    if len(active) == 0 or active_rows < 0:
        raise ValueError("saved q0 volume action requires a nonempty active vector")
    allocation_gate("task40_v25_q0_volume_stream_reload", {
        "matrix_payload_bytes": layout["class_payload_bytes"],
        "workspace_bytes": int(
            active.nbytes
            + active_rows * np.dtype(np.complex128).itemsize
            + layout["maximum_cell_payload_bytes"]
        ),
        "disk_backed_source_bytes": path.stat().st_size,
        "unique_classes_loaded_once": True,
        "class_count": layout["class_count"],
        "cell_count": layout["cell_count"],
        "cell_mapping_payload_bytes": layout["mapping_payload_bytes"],
        "future_co_resident_reserve_bytes": 0,
    })
    with _saved_stream_reader_sample(
        "volume", reader_telemetry
    ), path.open("rb") as stream:
        if stream.read(len(b"TASK40V25Q0VOLUME\0")) != b"TASK40V25Q0VOLUME\0":
            raise IOError("saved q0 volume stream has an unknown header")
        class_count, cell_count = struct.unpack("<II", stream.read(8))
        classes = []
        if int(class_count) != layout["class_count"] or int(cell_count) != layout["cell_count"]:
            raise IOError("saved q0 volume stream inventory changed between scan and load")
        for _ in range(class_count):
            frame_start = stream.tell()
            header = stream.read(8)
            if len(header) != 8:
                raise IOError("saved q0 volume stream ended inside class metadata")
            nrow, ncol = struct.unpack("<II", header)
            count = int(nrow) * int(ncol)
            values = np.fromfile(stream, dtype="<c16", count=count)
            if values.size != count:
                raise IOError("saved q0 volume stream has a truncated class matrix")
            matrix = values.reshape((int(nrow), int(ncol)))
            if not np.isfinite(matrix).all():
                raise ValueError("saved q0 volume class matrix contains non-finite values")
            classes.append(matrix)
            _advise_file_drop(stream, frame_start, stream.tell() - frame_start, telemetry=reader_telemetry)
        result = np.zeros(active_rows, dtype=np.complex128)
        for _ in range(cell_count):
            frame_start = stream.tell()
            header = stream.read(_CELL_STREAM_HEADER.size)
            if len(header) != _CELL_STREAM_HEADER.size:
                raise IOError("saved q0 volume stream ended inside cell mapping metadata")
            class_id, nactive, ntrace, nnz = _CELL_STREAM_HEADER.unpack(header)
            active_ids = np.fromfile(stream, dtype="<i4", count=int(nactive))
            indptr = np.fromfile(stream, dtype="<i4", count=int(ntrace) + 1)
            indices = np.fromfile(stream, dtype="<i4", count=int(nnz))
            values = np.fromfile(stream, dtype="<c16", count=int(nnz))
            if (
                active_ids.size != nactive or indptr.size != ntrace + 1
                or indices.size != nnz or values.size != nnz
            ):
                raise IOError("saved q0 volume stream has a truncated cell mapping")
            if (
                int(class_id) < 0
                or
                int(class_id) >= len(classes)
                or np.any(active_ids < 0)
                or np.any(active_ids >= len(active))
                or indptr[0] != 0
                or indptr[-1] != nnz
                or np.any(indptr[1:] < indptr[:-1])
                or (nnz and (int(indices.min()) < 0 or int(indices.max()) >= nactive))
                or not np.isfinite(values).all()
            ):
                raise ValueError("saved q0 volume cell mapping failed index/CSR validation")
            expansion = sparse.csr_matrix(
                (values, indices, indptr), shape=(int(ntrace), int(nactive)), copy=False
            )
            local_trace = expansion @ active[active_ids]
            local_result = classes[int(class_id)] @ local_trace
            np.add.at(result, active_ids, expansion.conjugate().T @ local_result)
            _advise_file_drop(stream, frame_start, stream.tell() - frame_start, telemetry=reader_telemetry)
            del active_ids, indptr, indices, values, expansion, local_trace, local_result
        if stream.read(1):
            raise IOError("saved q0 volume stream has trailing bytes")
    return result


def _apply_persisted_consumer(
    *,
    input_map: sparse.csr_matrix,
    output_map: sparse.csr_matrix,
    other_output_map: sparse.csr_matrix | None = None,
    source: np.ndarray,
    surface_stream_path: Path,
    volume_stream_path: Path,
    active_lookup: np.ndarray,
    active_rows: int,
    local_modes: tuple[Any, ...],
    selected_indices: np.ndarray,
    local_h: np.ndarray,
    mode_rows: tuple[Mapping[str, Any], ...],
    interior_rows: np.ndarray,
    trace_q_rows: int,
    allocation_gate: Callable,
    reader_telemetry: dict[str, Any] | None = None,
) -> dict[str, np.ndarray]:
    """Reload and apply all persisted volume/port data in selected q coordinates."""
    reduced_input = np.asarray(input_map @ source, dtype=np.complex128).reshape(-1)
    active = reduced_input[:active_rows]
    ports = reduced_input[active_rows:]
    if len(ports) != len(local_modes):
        raise ValueError("persisted q map port width differs from the complete alias inventory")
    volume_trace = _apply_persisted_volume_stream(
        volume_stream_path,
        active,
        active_rows=active_rows,
        allocation_gate=allocation_gate,
        reader_telemetry=reader_telemetry,
    )
    c_trace = np.zeros(active_rows, dtype=np.complex128)
    d_ports = np.zeros(len(local_modes), dtype=np.complex128)
    for port, entry in enumerate(_iter_saved_surface_functionals(
        surface_stream_path,
        selected_indices=selected_indices,
        local_modes=local_modes,
        local_h=local_h,
        mode_rows=mode_rows,
        interior_rows=interior_rows,
        active_lookup=active_lookup,
        active_rows=active_rows,
        reader_telemetry=reader_telemetry,
    )):
        for rows_name, values_name, target in (
            ("coupling_rows", "coupling_values", c_trace),
            ("projection_rows", "projection_values", None),
        ):
            rows = np.asarray(getattr(entry, rows_name), dtype=np.int64)
            values = np.asarray(getattr(entry, values_name), dtype=np.complex128)
            active_ids = np.asarray(active_lookup[rows], dtype=np.int64)
            if active_ids.size and (int(active_ids.min()) < 0 or int(active_ids.max()) >= active_rows):
                raise ValueError("persisted production port row does not map to an active trace row")
            if target is not None and rows.size:
                np.add.at(target, active_ids, values * ports[port])
            elif rows.size:
                d_ports[port] -= np.dot(values, active[active_ids])
    h_ports = np.asarray(local_h, dtype=np.complex128) * ports
    reduced_components = {
        "volume": np.concatenate((volume_trace, np.zeros(len(local_modes), dtype=np.complex128))),
        "C": np.concatenate((c_trace, np.zeros(len(local_modes), dtype=np.complex128))),
        "-D": np.concatenate((np.zeros(active_rows, dtype=np.complex128), d_ports)),
        "Hhat": np.concatenate((np.zeros(active_rows, dtype=np.complex128), h_ports)),
    }
    projected = {
        name: np.asarray(output_map.conjugate().T @ value, dtype=np.complex128).reshape(-1)
        for name, value in reduced_components.items()
    }
    projected["total"] = sum(
        (projected[name] for name in ("volume", "C", "-D", "Hhat")),
        np.zeros(output_map.shape[1], dtype=np.complex128),
    )
    if other_output_map is not None:
        other_components = {
            name: np.asarray(other_output_map.conjugate().T @ value, dtype=np.complex128).reshape(-1)
            for name, value in reduced_components.items()
        }
        projected["other_total"] = sum(
            (other_components[name] for name in ("volume", "C", "-D", "Hhat")),
            np.zeros(other_output_map.shape[1], dtype=np.complex128),
        )
        projected.update({f"other_{name}": value for name, value in other_components.items()})
    if projected["total"].shape != (output_map.shape[1],) or trace_q_rows <= 0:
        raise ValueError("persisted q0 consumer produced an invalid projected action")
    return projected


def _l2(values: Any) -> float:
    array = np.asarray(values, dtype=np.complex128).reshape(-1)
    return float(np.sqrt(np.vdot(array, array).real))


def _positive_finite_native_norm(values: Any, *, label: str) -> float:
    array = np.asarray(values, dtype=np.complex128).reshape(-1)
    if not np.isfinite(array).all():
        raise ValueError(f"{label} native diagonal output contains non-finite values")
    norm = _l2(array)
    if not np.isfinite(norm) or norm <= 0.0:
        raise ValueError(f"{label} native diagonal scale must be finite and strictly positive")
    return norm


def _relative_error(actual: Any, expected: Any) -> dict[str, float]:
    left = np.asarray(actual, dtype=np.complex128).reshape(-1)
    right = np.asarray(expected, dtype=np.complex128).reshape(-1)
    if left.shape != right.shape:
        raise ValueError("selected-q0 projected vectors have different shapes")
    if not np.isfinite(left).all() or not np.isfinite(right).all():
        raise ValueError("selected-q0 projected vectors contain non-finite values")
    difference = left - right
    absolute = _l2(difference)
    scale = max(_l2(left), _l2(right), np.finfo(float).tiny)
    return {"absolute": absolute, "relative_to_component": absolute / scale}


def _relative_error_with_scale(actual: Any, expected: Any, scale_source: Any) -> dict[str, float]:
    left = np.asarray(actual, dtype=np.complex128).reshape(-1)
    right = np.asarray(expected, dtype=np.complex128).reshape(-1)
    scale_values = np.asarray(scale_source, dtype=np.complex128).reshape(-1)
    if left.shape != right.shape:
        raise ValueError("selected-q projected vectors have different shapes")
    if not np.isfinite(left).all() or not np.isfinite(right).all() or not np.isfinite(scale_values).all():
        raise ValueError("selected-q scaled comparison contains non-finite values")
    absolute = _l2(left - right)
    scale = _positive_finite_native_norm(scale_values, label="selected-q")
    return {"absolute": absolute, "scale": scale, "relative_to_component": absolute / scale}


def run_task40_v26_saved_stream_replay(
    cfg: Any,
    axes: Mapping[str, Any],
    *,
    producer_root: str | Path,
    producer_identity: Mapping[str, Any],
    output_directory: str | Path,
    allocation_gate: Callable[[str, Mapping[str, Any]], Any],
    frozen_modes: tuple[Any, ...],
    frozen_mode_rows: tuple[Mapping[str, Any], ...],
    frozen_mode_manifest_sha256: str,
    expected_ordered_mode_key_sha256: str,
    frozen_mode_keys: tuple[tuple[int, str, int, int, str], ...] | None = None,
    current_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Replay frozen V25 q0/q4 streams without constructing a finite-element mesh."""
    from dataclasses import replace

    from .dtn_boundary_phase_gauge import BOUNDARY_PLANE, assembly_projection_denominator
    from .task40_v10_p6_periodic_profile import TASK40_V20_P6_TARGET_ORIGINAL_NY8_PROFILE
    from .task40_v10_p6_yorbit import build_task40_v10_sector_contexts
    from .task40_v20_mode_inventory import TARGET_MODE_MANIFEST_SHA256, TARGET_REFERENCE_PLANES_NM

    if not callable(allocation_gate):
        raise TypeError("V26 saved replay requires the live allocation gate")
    root = Path(output_directory).resolve()
    producer = Path(producer_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    parent_started = time.perf_counter()
    reader_telemetry = _new_saved_stream_reader_telemetry()
    profile = TASK40_V20_P6_TARGET_ORIGINAL_NY8_PROFILE
    if (
        not isinstance(producer_identity, Mapping)
        or producer_identity.get("producer_run_id") is None
        or producer_identity.get("failure_index_sha256") is None
        or producer_identity.get("verified_input_sha256") is None
    ):
        raise ValueError("V26 replay has no complete service-bound V25 producer identity")
    mode_keys, computed_key_sha = _validate_frozen_mode_identity(
        tuple(frozen_modes),
        tuple(frozen_mode_rows),
        expected_ordered_mode_key_sha256=expected_ordered_mode_key_sha256,
        frozen_mode_keys=frozen_mode_keys,
    )
    if frozen_mode_manifest_sha256 != TARGET_MODE_MANIFEST_SHA256:
        raise ValueError("V26 replay mode manifest differs from the frozen reference inventory")
    global_axes = {key: tuple(map(float, axes[key])) for key in ("x", "y", "z")}
    cell_axes = tuple(len(global_axes[key]) - 1 for key in ("x", "y", "z"))
    if cell_axes != profile.global_cell_axes or int(cfg.nedelec_degree) != 6 or len(global_axes["y"]) != 9:
        raise ValueError("V26 saved replay requires the exact p6 Ny8 regular-reference profile")
    regular_cfg = replace(
        cfg,
        air_void_box_nm=None,
        cell_notch=None,
        geometry_identity="task40extra_v26.saved_q0_reference",
    )
    runtime_planes = {
        "bottom": float(regular_cfg.physical_z_min),
        "top": float(regular_cfg.physical_z_max),
    }
    if runtime_planes != TARGET_REFERENCE_PLANES_NM:
        raise ValueError("V26 replay z planes differ from the frozen regular-reference inventory")
    contexts = build_task40_v10_sector_contexts(tuple(frozen_modes), regular_cfg, global_axes)
    context = next((row for row in contexts if 0 in row.global_q_indices), None)
    if context is None or tuple(map(int, context.global_q_indices)) != (0, 4):
        raise ValueError("V26 q0 replay does not resolve to the registered paired q4 sector")
    selected = np.asarray(context.original_mode_indices, dtype=np.int64)
    branches = np.asarray(context.local_branch_indices, dtype=np.int8)
    aliases = tuple(np.flatnonzero(branches == branch) for branch in (0, 1))
    local_modes = tuple(frozen_modes[int(index)] for index in selected)
    if (
        len(frozen_modes) != 32_060
        or len(selected) != 7_932
        or len(aliases[0]) != 4_076
        or len(aliases[1]) != 3_856
        or not np.array_equal(np.sort(np.concatenate(aliases)), np.arange(len(selected)))
    ):
        raise ValueError(
            "V26 replay requires all 32,060 frozen modes and a complete 7,932-mode q0/q4 sector"
        )
    global_h = np.asarray(
        [
            assembly_projection_denominator(mode, regular_cfg, BOUNDARY_PLANE)
            for mode in (frozen_modes[int(index)] for index in selected)
        ],
        dtype=np.float64,
    )
    local_h_expected = np.ascontiguousarray(
        global_h * (2.0 / float(len(global_axes["y"]) - 1)), dtype=np.float64
    )
    if not np.isfinite(local_h_expected).all() or np.any(local_h_expected <= 0.0):
        raise ValueError("V26 replay original H_p values are not finite positive")

    payloads = {
        str(item.get("path")): item
        for item in producer_identity.get("payloads", [])
        if isinstance(item, Mapping)
    }
    required_names = (
        "v25_selected_q0_surface_functionals.bin",
        "v25_selected_q0_volume_classes.bin",
        "v25_selected_q0_local_H_p.npy",
        "v25_selected_q0_original_to_active_int32.npy",
        "v25_selected_q0_map.npz",
        "v25_selected_q4_map.npz",
    )
    paths, expected_total_bytes, producer_hash_validation_seconds = _verify_bound_payload_files(
        producer, payloads, required_names
    )
    if expected_total_bytes != 12_175_610_924:
        raise ValueError("V26 saved producer payload total differs from the frozen six-file inventory")

    allocation_gate(
        "task40_v26_saved_replay_load_maps_and_checkpoint_space",
        {
            "additional_payload_bytes": int(
                payloads["v25_selected_q0_map.npz"]["bytes"]
                + payloads["v25_selected_q4_map.npz"]["bytes"]
                + payloads["v25_selected_q0_original_to_active_int32.npy"]["bytes"]
                + payloads["v25_selected_q0_local_H_p.npy"]["bytes"]
            ),
            "workspace_bytes": int(
                (len(aliases[0]) + len(aliases[1]) + 4 * profile.trace_rows_per_q)
                * np.dtype(np.complex128).itemsize
            ),
            "disk_payload_bytes": int(
                (3 * (2 * profile.trace_rows_per_q + len(aliases[0]) + len(aliases[1]))
                 + 3 * (len(aliases[0]) + len(aliases[1])))
                * np.dtype(np.complex128).itemsize
            ),
            "saved_producer_payload_bytes": expected_total_bytes,
            "future_co_resident_reserve_bytes": 0,
            "q0_q4_map_files_loaded_together": True,
        },
    )
    q0_map = sparse.load_npz(paths["v25_selected_q0_map.npz"]).tocsr()
    q4_map = sparse.load_npz(paths["v25_selected_q4_map.npz"]).tocsr()
    q_maps = (q0_map, q4_map)
    active_rows = int(profile.local_trace_rows)
    if any(
        matrix.dtype != np.dtype(np.complex128)
        or matrix.indices.dtype != np.dtype(np.int32)
        or matrix.indptr.dtype != np.dtype(np.int32)
        or not matrix.has_canonical_format
        or not matrix.has_sorted_indices
        for matrix in q_maps
    ):
        raise ValueError("V26 saved q maps have an invalid CSR dtype or ordering")
    expected_reduced_rows = active_rows + len(local_modes)
    expected_q_columns = (
        profile.trace_rows_per_q + len(aliases[0]),
        profile.trace_rows_per_q + len(aliases[1]),
    )
    if (
        q0_map.shape != (expected_reduced_rows, expected_q_columns[0])
        or q4_map.shape != (expected_reduced_rows, expected_q_columns[1])
    ):
        raise ValueError("V26 saved q maps do not cover the complete registered q0/q4 domain")
    local_h = np.load(paths["v25_selected_q0_local_H_p.npy"], allow_pickle=False)
    if (
        local_h.shape != (len(local_modes),)
        or local_h.dtype != np.dtype(np.complex128)
        or not np.isfinite(local_h).all()
        or np.max(np.abs(local_h.imag), initial=0.0) != 0.0
    ):
        raise ValueError("V26 saved original H_p array has invalid shape/dtype/values")
    h_error = _relative_error(local_h, local_h_expected)
    if h_error["relative_to_component"] > 1.0e-12:
        raise ValueError("V26 saved original H_p values differ from the regular-reference calculation")
    active_lookup = np.load(
        paths["v25_selected_q0_original_to_active_int32.npy"],
        mmap_mode="r",
        allow_pickle=False,
    )
    if active_lookup.shape != (profile.local_storage_rows,) or active_lookup.dtype != np.dtype(np.int32):
        raise ValueError("V26 saved original-to-active lookup has an invalid shape/dtype")
    if np.any(active_lookup < -1) or int(active_lookup.max(initial=-1)) >= active_rows:
        raise ValueError("V26 saved original-to-active lookup has an invalid active index")
    active_presence = np.zeros(active_rows, dtype=np.bool_)
    for start in range(0, len(active_lookup), 1_000_000):
        values = np.asarray(active_lookup[start : start + 1_000_000], dtype=np.int64)
        mapped = values[values >= 0]
        if mapped.size:
            active_presence[mapped] = True
    if not np.all(active_presence):
        raise ValueError("V26 original-to-active lookup omits at least one active trace row")
    volume_layout = _scan_persisted_volume_stream(paths["v25_selected_q0_volume_classes.bin"])
    if volume_layout["cell_count"] != profile.local_cell_count or volume_layout["class_count"] != 45:
        raise ValueError("V26 saved volume stream has the wrong complete-cell/class inventory")
    trace_rows_q0 = int(q0_map.shape[1] - len(aliases[0]))
    trace_rows_q4 = int(q4_map.shape[1] - len(aliases[1]))
    if trace_rows_q0 != profile.trace_rows_per_q or trace_rows_q4 != profile.trace_rows_per_q:
        raise ValueError("V26 saved q0/q4 maps have an unexpected trace width")

    rng_q0 = np.random.default_rng(402500)

    def nonzero_complex(rng: np.random.Generator, size: int) -> np.ndarray:
        return np.asarray(
            (rng.standard_normal(size) + 1j * rng.standard_normal(size)) / np.sqrt(2.0),
            dtype=np.complex128,
        )

    x0_1 = nonzero_complex(rng_q0, q0_map.shape[1])
    x0_2 = nonzero_complex(rng_q0, q0_map.shape[1])
    x4 = nonzero_complex(np.random.default_rng(402504), q4_map.shape[1])
    if np.array_equal(x0_1, x0_2) or not np.all(x0_1 != 0.0) or not np.all(x0_2 != 0.0) or not np.all(x4 != 0.0):
        raise RuntimeError("V26 replay inputs must be distinct q0 draws and all-elements-nonzero")

    producer_identity_sha = hashlib.sha256(
        json.dumps(producer_identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    input_vectors = {"q0_case_1": x0_1, "q0_case_2": x0_2, "q4_pair": x4}
    input_path = root / "v26_saved_q_replay_inputs.npz"
    input_manifest_path = root / "v26_saved_q_replay_inputs.json"
    input_hashes = {key: _array_sha256(value) for key, value in input_vectors.items()}
    if input_path.exists():
        if not input_manifest_path.is_file():
            raise FileExistsError("V26 saved replay inputs exist without their identity manifest")
        input_manifest = json.loads(input_manifest_path.read_text(encoding="utf-8"))
        if (
            _file_sha256(input_path) != input_manifest.get("sha256")
            or input_manifest.get("array_sha256") != input_hashes
            or input_manifest.get("producer_identity_sha256") != producer_identity_sha
        ):
            raise ValueError("existing V26 replay input checkpoint is not the same deterministic input set")
        with np.load(input_path, allow_pickle=False) as saved_inputs:
            if set(saved_inputs.files) != set(input_vectors) or any(
                not np.array_equal(saved_inputs[key], value)
                for key, value in input_vectors.items()
            ):
                raise ValueError("existing V26 replay input arrays differ from their fixed seeds")
    else:
        _save_npz_atomic(input_path, **input_vectors)
        input_manifest = {
            "schema": "task40extra.review_v26_saved_q_replay_inputs.v1",
            "array_sha256": input_hashes,
            "producer_identity_sha256": producer_identity_sha,
            "current_identity": dict(current_identity or {}),
            "path": input_path.name,
            "bytes": input_path.stat().st_size,
            "sha256": _file_sha256(input_path),
        }
        _write_json(input_manifest_path, input_manifest)
    input_file_identity = {
        "path": input_path.name,
        "bytes": input_path.stat().st_size,
        "sha256": _file_sha256(input_path),
        "array_sha256": input_hashes,
    }
    replay_manifest_path = root / "v26_saved_q_replay_manifest.json"
    if replay_manifest_path.exists():
        existing, existing_paths = _load_v26_saved_replay_manifest(root, producer_identity)
        if (
            existing.get("artifacts", {}).get("inputs", {}).get("sha256")
            != input_file_identity["sha256"]
            or existing.get("preflight_mode_manifest_sha256") != frozen_mode_manifest_sha256
            or existing.get("ordered_mode_key_sha256") != computed_key_sha
            or existing.get("mode_count_full_reference") != 32_060
            or existing.get("q0_alias_count", 0) + existing.get("q4_alias_count", 0) != 7_932
            or existing.get("current_identity") != dict(current_identity or {})
            or set(existing_paths) != {"inputs", "q0_case_1", "q0_case_2", "q4_pair"}
        ):
            raise ValueError("existing V26 saved replay manifest differs from this frozen full/sector identity")
        existing["manifest_path"] = replay_manifest_path.name
        existing["manifest_sha256"] = _file_sha256(replay_manifest_path)
        existing["replay_readback_seconds_this_invocation"] = float(time.perf_counter() - parent_started)
        return existing

    def persist_case(name: str, arrays: Mapping[str, np.ndarray], input_name: str) -> dict[str, Any]:
        path = root / f"v26_saved_q_replay_{name}.npz"
        manifest_path = path.with_suffix(".json")
        for key, value in arrays.items():
            array = np.asarray(value)
            if array.ndim != 1 or array.dtype != np.dtype(np.complex128) or not np.isfinite(array).all():
                raise ValueError(f"V26 replay output array {name}/{key} is not finite complex128 vector data")
        if path.exists():
            if not manifest_path.is_file():
                raise FileExistsError(f"V26 replay output exists without its case manifest: {path}")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if (
                _file_sha256(path) != manifest.get("sha256")
                or manifest.get("input_name") != input_name
                or manifest.get("input_sha256") != input_hashes[input_name]
                or manifest.get("producer_identity_sha256") != producer_identity_sha
                or manifest.get("array_names") != sorted(arrays)
            ):
                raise ValueError(f"existing V26 replay output identity changed: {name}")
            with np.load(path, allow_pickle=False) as saved:
                if set(saved.files) != set(arrays) or any(
                    saved[key].shape != np.asarray(value).shape
                    or saved[key].dtype != np.asarray(value).dtype
                    or not np.array_equal(saved[key], value)
                    for key, value in arrays.items()
                ):
                    raise ValueError(f"existing V26 replay output arrays changed: {name}")
            return manifest
        _save_npz_atomic(path, **dict(arrays))
        manifest = {
            "schema": "task40extra.review_v26_saved_q_replay_case.v1",
            "case": name,
            "input_name": input_name,
            "input_sha256": input_hashes[input_name],
            "producer_identity_sha256": producer_identity_sha,
            "array_names": sorted(arrays),
            "array_shapes": {key: list(np.asarray(value).shape) for key, value in arrays.items()},
            "array_sha256": {key: _array_sha256(value) for key, value in arrays.items()},
            "current_identity": dict(current_identity or {}),
            "path": path.name,
            "bytes": path.stat().st_size,
            "sha256": _file_sha256(path),
        }
        _write_json(manifest_path, manifest)
        return manifest

    surface_path = paths["v25_selected_q0_surface_functionals.bin"]
    volume_path = paths["v25_selected_q0_volume_classes.bin"]
    empty_interior = np.empty(0, dtype=np.int64)
    operation_started = time.perf_counter()
    case_records: dict[str, dict[str, Any]] = {}
    cases = (
        ("q0_case_1", q0_map, q0_map, q4_map, x0_1, trace_rows_q0),
        ("q0_case_2", q0_map, q0_map, q4_map, x0_2, trace_rows_q0),
        ("q4_pair", q4_map, q4_map, q0_map, x4, trace_rows_q4),
    )
    for case_name, input_map, output_map, other_map, source, trace_width in cases:
        case_path = root / f"v26_saved_q_replay_{case_name}.npz"
        case_manifest_path = case_path.with_suffix(".json")
        input_name = case_name
        if case_path.exists() and case_manifest_path.is_file():
            case_records[case_name] = json.loads(case_manifest_path.read_text(encoding="utf-8"))
            if (
                _file_sha256(case_path) != case_records[case_name].get("sha256")
                or case_records[case_name].get("input_sha256") != input_hashes[input_name]
                or case_records[case_name].get("producer_identity_sha256") != producer_identity_sha
            ):
                raise ValueError(f"existing V26 replay case failed its persisted identity: {case_name}")
            continue
        if case_path.exists() or case_manifest_path.exists():
            raise FileExistsError(f"incomplete V26 replay case checkpoint cannot be overwritten: {case_name}")
        started = time.perf_counter()
        result = _apply_persisted_consumer(
            input_map=input_map,
            output_map=output_map,
            other_output_map=other_map,
            source=source,
            surface_stream_path=surface_path,
            volume_stream_path=volume_path,
            active_lookup=active_lookup,
            active_rows=active_rows,
            local_modes=local_modes,
            selected_indices=selected,
            local_h=local_h,
            mode_rows=tuple(frozen_mode_rows),
            interior_rows=empty_interior,
            trace_q_rows=trace_width,
            allocation_gate=allocation_gate,
            reader_telemetry=reader_telemetry,
        )
        if case_name.startswith("q0_"):
            arrays = {
                "q0_total": result["total"],
                "q0_volume": result["volume"],
                "q0_C": result["C"],
                "q0_minus_D": result["-D"],
                "q0_Hhat": result["Hhat"],
                "q4_total_from_q0": result["other_total"],
                "q4_volume_from_q0": result["other_volume"],
                "q4_C_from_q0": result["other_C"],
                "q4_minus_D_from_q0": result["other_-D"],
                "q4_Hhat_from_q0": result["other_Hhat"],
            }
        else:
            arrays = {
                "q4_total": result["total"],
                "q4_volume": result["volume"],
                "q4_C": result["C"],
                "q4_minus_D": result["-D"],
                "q4_Hhat": result["Hhat"],
                "q0_total_from_q4": result["other_total"],
                "q0_volume_from_q4": result["other_volume"],
                "q0_C_from_q4": result["other_C"],
                "q0_minus_D_from_q4": result["other_-D"],
                "q0_Hhat_from_q4": result["other_Hhat"],
            }
        case_records[case_name] = persist_case(case_name, arrays, input_name)
        case_records[case_name]["elapsed_seconds"] = float(time.perf_counter() - started)
        del result, arrays

    if replay_manifest_path.exists():
        raise FileExistsError("V26 replay manifest appeared while this single-writer stage was active")
    artifacts = {"inputs": input_file_identity}
    for case_name, case_record in case_records.items():
        case_path = root / str(case_record["path"])
        if _file_sha256(case_path) != case_record["sha256"]:
            raise IOError(f"V26 saved replay output failed manifest readback: {case_name}")
        artifacts[case_name] = {
            "path": case_record["path"],
            "bytes": case_record["bytes"],
            "sha256": case_record["sha256"],
            "manifest_path": case_path.with_suffix(".json").name,
        }
    replay_manifest = {
        "schema": "task40extra.review_v26_saved_q_replay.v1",
        "status": "PASS_SAVED_STREAM_REPLAY_NO_NATIVE",
        "classification": "READ_ONLY_V25_PRODUCER_REPLAY_COMPLETE; NATIVE_REFERENCE_NOT_RUN",
        "official_result": False,
        "native_comparison": "NOT_RUN_IN_THIS_STAGE",
        "csr_built": False,
        "factor_or_solve_built": False,
        "producer_identity": dict(producer_identity),
        "producer_identity_sha256": producer_identity_sha,
        "current_identity": dict(current_identity or {}),
        "preflight_mode_manifest_sha256": frozen_mode_manifest_sha256,
        "ordered_mode_key_sha256": computed_key_sha,
        "mode_count_full_reference": len(frozen_modes),
        "selected_global_q_indices": list(context.global_q_indices),
        "q0_alias_count": int(len(aliases[0])),
        "q4_alias_count": int(len(aliases[1])),
        "selected_twist_alias_count": int(len(selected)),
        "local_storage_rows": int(profile.local_storage_rows),
        "active_trace_rows": active_rows,
        "q0_trace_rows": trace_rows_q0,
        "q4_trace_rows": trace_rows_q4,
        "local_cells": int(profile.local_cell_count),
        "original_H_p_relative_error": h_error,
        "active_lookup_unmapped_policy": "only in-range exact-zero B/D entries may be skipped; nonzero unmapped and negative/out-of-range rows are rejected",
        "producer_payload_total_bytes": expected_total_bytes,
        "producer_payloads": [dict(payloads[name]) for name in required_names],
        "producer_payload_sha256_validation_seconds": producer_hash_validation_seconds,
        "volume_stream_inventory": volume_layout,
        "all_saved_inputs_nonzero": True,
        "q0_inputs_distinct": True,
        "inputs_saved_before_replay": True,
        "each_case_output_saved_atomically_before_next_case": True,
        "native_volume_apply_count": 0,
        "provider_sweep_count": 0,
        "saved_stream_reader_telemetry": reader_telemetry,
        "cases": case_records,
        "artifacts": artifacts,
        "elapsed_seconds_scope": "three saved-stream consumer passes and their per-case atomic persistence/readback, starting after full producer, map, lookup, H, and input validation/loading",
        "elapsed_seconds": float(time.perf_counter() - operation_started),
        "parent_elapsed_seconds_scope": "function entry through producer SHA checks, inventory/map/input validation, all three full saved-stream passes, atomic outputs, and final manifest persistence",
        "parent_elapsed_seconds": float(time.perf_counter() - parent_started),
    }
    _write_json(replay_manifest_path, replay_manifest)
    replay_manifest["manifest_path"] = replay_manifest_path.name
    replay_manifest["manifest_sha256"] = _file_sha256(replay_manifest_path)
    return replay_manifest


def _load_v26_saved_replay_manifest(
    replay_root: str | Path, producer_identity: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Path]]:
    """Read back every V26 saved-replay artifact before native comparison."""
    root = Path(replay_root).resolve()
    manifest_path = root / "v26_saved_q_replay_manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError("V26 saved replay manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_producer_identity_sha = hashlib.sha256(
        json.dumps(producer_identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if (
        manifest.get("schema") != "task40extra.review_v26_saved_q_replay.v1"
        or manifest.get("status") != "PASS_SAVED_STREAM_REPLAY_NO_NATIVE"
        or manifest.get("producer_identity_sha256") != expected_producer_identity_sha
        or manifest.get("official_result") is not False
        or manifest.get("native_comparison") != "NOT_RUN_IN_THIS_STAGE"
    ):
        raise ValueError("V26 saved replay manifest does not match the registered producer identity")
    manifest["manifest_path"] = manifest_path.name
    manifest["manifest_sha256"] = _file_sha256(manifest_path)
    artifacts = manifest.get("artifacts", {})
    records: dict[str, Path] = {}
    input_item = artifacts.get("inputs")
    if not isinstance(input_item, Mapping):
        raise ValueError("V26 saved replay manifest omits its deterministic input checkpoint")
    input_path = (root / str(input_item.get("path", ""))).resolve()
    input_sidecar_path = root / "v26_saved_q_replay_inputs.json"
    input_sidecar = (
        json.loads(input_sidecar_path.read_text(encoding="utf-8"))
        if input_sidecar_path.is_file()
        else {}
    )
    input_array_hashes = input_item.get("array_sha256", {})
    if (
        not input_path.is_relative_to(root)
        or not input_path.is_file()
        or input_path.stat().st_size != input_item.get("bytes")
        or _file_sha256(input_path) != input_item.get("sha256")
        or input_sidecar.get("sha256") != input_item.get("sha256")
        or input_sidecar.get("array_sha256") != input_array_hashes
        or input_sidecar.get("producer_identity_sha256") != expected_producer_identity_sha
    ):
        raise IOError("V26 deterministic replay input checkpoint failed manifest readback")
    with np.load(input_path, allow_pickle=False) as inputs:
        expected_inputs = {"q0_case_1", "q0_case_2", "q4_pair"}
        if set(inputs.files) != expected_inputs or set(input_array_hashes) != expected_inputs:
            raise ValueError("V26 replay input checkpoint has an incomplete case inventory")
        input_values: dict[str, np.ndarray] = {}
        for name in sorted(expected_inputs):
            value = np.asarray(inputs[name])
            if (
                value.ndim != 1
                or value.dtype != np.dtype(np.complex128)
                or not np.isfinite(value).all()
                or np.any(value == 0.0)
                or _array_sha256(value) != input_array_hashes.get(name)
            ):
                raise ValueError(f"V26 saved replay input failed raw-array readback: {name}")
            input_values[name] = value
        if np.array_equal(input_values["q0_case_1"], input_values["q0_case_2"]):
            raise ValueError("V26 saved replay q0 input vectors are not distinct")
    records["inputs"] = input_path
    for name in ("inputs", "q0_case_1", "q0_case_2", "q4_pair"):
        item = artifacts.get(name)
        if not isinstance(item, Mapping):
            raise ValueError(f"V26 saved replay manifest omits artifact {name}")
        path = (root / str(item.get("path", ""))).resolve()
        if (
            not path.is_relative_to(root)
            or not path.is_file()
            or path.stat().st_size != item.get("bytes")
            or _file_sha256(path) != item.get("sha256")
        ):
            raise IOError(f"V26 saved replay artifact failed readback: {name}")
        if name != "inputs":
            sidecar = root / str(item.get("manifest_path", ""))
            case = manifest.get("cases", {}).get(name, {})
            sidecar_data = (
                json.loads(sidecar.read_text(encoding="utf-8"))
                if sidecar.is_file()
                else {}
            )
            if (
                not sidecar.is_file()
                or _file_sha256(path) != case.get("sha256")
                or case.get("producer_identity_sha256") != expected_producer_identity_sha
                or case.get("input_sha256")
                != artifacts.get("inputs", {}).get("array_sha256", {}).get(name)
                or sidecar_data.get("sha256") != case.get("sha256")
                or sidecar_data.get("array_sha256") != case.get("array_sha256")
                or sidecar_data.get("array_shapes") != case.get("array_shapes")
            ):
                raise ValueError(f"V26 saved replay case identity is inconsistent: {name}")
            case_array_hashes = case.get("array_sha256", {})
            case_array_shapes = case.get("array_shapes", {})
            with np.load(path, allow_pickle=False) as arrays:
                if set(arrays.files) != set(case_array_hashes) or set(arrays.files) != set(case_array_shapes):
                    raise ValueError(f"V26 saved replay case has an incomplete raw array inventory: {name}")
                for array_name in arrays.files:
                    value = np.asarray(arrays[array_name])
                    if (
                        value.ndim != 1
                        or value.dtype != np.dtype(np.complex128)
                        or list(value.shape) != case_array_shapes.get(array_name)
                        or not np.isfinite(value).all()
                        or _array_sha256(value) != case_array_hashes.get(array_name)
                    ):
                        raise ValueError(
                            f"V26 saved replay raw output array failed readback: {name}/{array_name}"
                        )
            records[name] = path
    return manifest, records


def _persist_v26_native_case(
    output_root: Path,
    case_name: str,
    arrays: Mapping[str, np.ndarray],
    *,
    producer_identity_sha256: str,
    replay_manifest_sha256: str,
    current_identity: Mapping[str, Any],
) -> dict[str, Any]:
    path = output_root / f"v26_native_{case_name}.npz"
    sidecar_path = path.with_suffix(".json")
    checked: dict[str, np.ndarray] = {}
    for name, raw in arrays.items():
        value = np.asarray(raw)
        if value.ndim != 1 or value.dtype != np.dtype(np.complex128) or not np.isfinite(value).all():
            raise ValueError(f"V26 native output {case_name}/{name} is not a finite complex128 vector")
        checked[name] = value
    if path.exists() or sidecar_path.exists():
        raise FileExistsError(f"refusing to overwrite an existing V26 native checkpoint: {path}")
    _save_npz_atomic(path, **checked)
    record = {
        "schema": "task40extra.review_v26_native_action_case.v1",
        "case": case_name,
        "producer_identity_sha256": producer_identity_sha256,
        "saved_replay_manifest_sha256": replay_manifest_sha256,
        "current_identity": dict(current_identity),
        "array_names": sorted(checked),
        "array_shapes": {name: list(value.shape) for name, value in checked.items()},
        "array_sha256": {name: _array_sha256(value) for name, value in checked.items()},
        "path": path.name,
        "bytes": path.stat().st_size,
        "sha256": _file_sha256(path),
    }
    _write_json(sidecar_path, record)
    return record


def _load_v26_native_action(
    native_root: str | Path,
    *,
    producer_identity_sha256: str,
    replay_manifest_sha256: str,
    manifest_path: str | Path | None = None,
    recovery_identity: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, np.ndarray]]]:
    """Reload native action checkpoints from raw arrays, verifying every sidecar and hash."""
    root = Path(native_root).resolve()
    manifest_path = (
        Path(manifest_path).resolve()
        if manifest_path is not None
        else root / "v26_native_action_manifest.json"
    )
    if not manifest_path.is_relative_to(root):
        raise ValueError("V26 native manifest path is outside the registered native root")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    standard_manifest = (
        manifest.get("schema") == "task40extra.review_v26_native_action.v1"
        and manifest.get("status") == "PASS_COMPLETE_Q0_NATIVE_CONSUMER"
        and manifest.get("current_identity") == recovery_identity
    )
    recovered_manifest = (
        manifest.get("schema") == "task40extra.review_v26_native_action_recovery.v1"
        and manifest.get("status") == "PASS_RECOVERED_THREE_NATIVE_CASES"
        and manifest.get("recovery_current_identity") == recovery_identity
        and isinstance(manifest.get("native_current_identity"), Mapping)
        and manifest.get("native_current_identity", {}).get("source_sha")
        != manifest.get("recovery_current_identity", {}).get("source_sha")
    )
    if (
        not (standard_manifest or recovered_manifest)
        or manifest.get("producer_identity_sha256") != producer_identity_sha256
        or manifest.get("saved_replay_manifest_sha256") != replay_manifest_sha256
    ):
        raise ValueError("V26 native action manifest does not match the saved producer/replay identity")
    manifest["manifest_path"] = manifest_path.name
    manifest["manifest_sha256"] = _file_sha256(manifest_path)
    loaded: dict[str, dict[str, np.ndarray]] = {}
    case_records = manifest.get("cases", {})
    for case_name in ("q0_case_1", "q0_case_2", "q4_pair"):
        item = case_records.get(case_name)
        if not isinstance(item, Mapping):
            raise ValueError(f"V26 native action manifest omits {case_name}")
        path = (root / str(item.get("path", ""))).resolve()
        sidecar_path = path.with_suffix(".json")
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        if (
            not path.is_relative_to(root)
            or not path.is_file()
            or path.stat().st_size != item.get("bytes")
            or _file_sha256(path) != item.get("sha256")
            or sidecar.get("sha256") != item.get("sha256")
            or sidecar.get("array_sha256") != item.get("array_sha256")
            or sidecar.get("producer_identity_sha256") != producer_identity_sha256
            or sidecar.get("saved_replay_manifest_sha256") != replay_manifest_sha256
            or sidecar.get("current_identity") != (
                manifest.get("native_current_identity")
                if recovered_manifest
                else manifest.get("current_identity")
            )
        ):
            raise IOError(f"V26 native action case failed persisted identity readback: {case_name}")
        with np.load(path, allow_pickle=False) as archive:
            array_hashes = item.get("array_sha256", {})
            array_shapes = item.get("array_shapes", {})
            if set(archive.files) != set(array_hashes) or set(archive.files) != set(array_shapes):
                raise ValueError(f"V26 native action case has an incomplete raw array inventory: {case_name}")
            current: dict[str, np.ndarray] = {}
            for name in archive.files:
                value = np.asarray(archive[name]).copy()
                if (
                    value.ndim != 1
                    or value.dtype != np.dtype(np.complex128)
                    or list(value.shape) != array_shapes.get(name)
                    or not np.isfinite(value).all()
                    or _array_sha256(value) != array_hashes.get(name)
                ):
                    raise ValueError(f"V26 native action raw array failed readback: {case_name}/{name}")
                current[name] = value
            loaded[case_name] = current
    return manifest, loaded


def _native_q0_components_from_saved_case(case_arrays: Mapping[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Restore saved native component arrays under the live action's canonical keys."""
    return {
        name: np.asarray(case_arrays[f"native_q0_{name.replace('-', 'minus_')}"])
        for name in ("volume", "C", "-D", "Hhat")
    }


def _mode_key(index: int, mode: Any) -> tuple[int, str, int, int, str]:
    return (
        int(index),
        str(mode.side),
        int(mode.m),
        int(mode.n),
        str(mode.polarization),
    )


def _validate_frozen_mode_identity(
    generated_modes: tuple[Any, ...],
    mode_rows: tuple[Mapping[str, Any], ...],
    *,
    expected_ordered_mode_key_sha256: str | None,
    frozen_mode_keys: tuple[tuple[int, str, int, int, str], ...] | None = None,
) -> tuple[tuple[tuple[int, str, int, int, str], ...], str]:
    """Bind full indexed mode rows to the ledger's canonical ordered-key digest."""
    if not generated_modes or len(mode_rows) != len(generated_modes):
        raise ValueError("selected q0 frozen mode rows do not cover the complete preflight mode inventory")

    mode_keys = tuple(_mode_key(index, mode) for index, mode in enumerate(generated_modes))
    if frozen_mode_keys is not None and tuple(frozen_mode_keys) != mode_keys:
        raise ValueError("regular-reference ordered mode keys differ from the frozen input inventory")
    if any(
        int(row.get("mode_index", -1)) != index
        or str(row.get("side")) != str(mode.side)
        or int(row.get("m", 0)) != int(mode.m)
        or int(row.get("n", 0)) != int(mode.n)
        or str(row.get("polarization")) != str(mode.polarization)
        for index, (mode, row) in enumerate(zip(generated_modes, mode_rows, strict=True))
    ):
        raise ValueError("regular-reference preflight mode rows differ from the frozen ordered mode table")

    # TARGET_LEDGER defines this digest over the ordered physical key only;
    # mode_index remains bound above by the full ordered mode rows.
    digest_keys = [
        [str(mode.side), int(mode.m), int(mode.n), str(mode.polarization)]
        for mode in generated_modes
    ]
    payload = json.dumps(
        digest_keys, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    computed_key_sha = hashlib.sha256(payload).hexdigest()
    if (
        expected_ordered_mode_key_sha256 is None
        or computed_key_sha != expected_ordered_mode_key_sha256
    ):
        raise ValueError("regular-reference mode-key identity differs from the frozen input key hash")
    return mode_keys, computed_key_sha


def _native_volume_apply(
    volume_action: Any,
    full_field: np.ndarray,
    comm: Any,
    *,
    counters: dict[str, int] | None = None,
) -> np.ndarray:
    from petsc4py import PETSc

    if counters is not None:
        counters["native_volume_apply_count"] = counters.get("native_volume_apply_count", 0) + 1
    source = PETSc.Vec().createWithArray(
        np.ascontiguousarray(full_field, dtype=np.complex128), comm=comm
    )
    try:
        result = volume_action.apply(source)
        # FullspaceSplitVolumeAction.apply returns its action-owned reusable
        # output Vec. Copy its values here, but leave the borrowed Vec alive.
        return np.asarray(result.getArray(readonly=True), dtype=np.complex128).copy()
    finally:
        source.destroy()


def _native_component_reduced_actions(
    *,
    action: Any,
    volume_action: Any,
    comm: Any,
    q_map: sparse.csr_matrix,
    trace_rows: int,
    trace_input: np.ndarray,
    port_input: np.ndarray,
    counters: dict[str, int] | None = None,
) -> dict[str, np.ndarray]:
    """Return native component actions in the full local reduced space."""
    full_rows = int(action.condensed.full_rows)
    local_trace_rows = int(action.condensed.active_rows)
    local_port_rows = int(action.condensed.appended_rows)
    if trace_input.shape != (trace_rows,):
        raise ValueError("selected-q0 trace input width differs from its trace rows")
    if port_input.shape != (q_map.shape[1] - trace_rows,):
        raise ValueError("selected-q0 trace input width differs from q map")
    reduced_input = np.concatenate((trace_input, port_input)).astype(
        np.complex128, copy=False
    )
    if reduced_input.shape != (q_map.shape[1],):
        raise ValueError("selected-q0 native split input has an invalid width")

    def field_for(trace: np.ndarray, ports: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        reduced = q_map @ np.concatenate((trace, ports))
        field = action.recover_storage(reduced, expand_trace=False)
        if field.shape != (full_rows,):
            raise ValueError("native p6 recovery did not return complete local FE storage")
        return np.asarray(reduced, dtype=np.complex128), np.asarray(field, dtype=np.complex128)

    zero_trace = np.zeros_like(trace_input)
    zero_ports = np.zeros_like(port_input)
    outputs: dict[str, np.ndarray] = {}

    # Volume Schur action: FE callback with alpha=0, dual-reduced to q0 rows.
    reduced_trace, field_trace = field_for(trace_input, zero_ports)
    native_volume = _native_volume_apply(volume_action, field_trace, comm, counters=counters)
    volume_reduced = action.reduce_rhs(native_volume, rhs_is_mpc_dual=True)
    outputs["volume"] = np.asarray(volume_reduced, dtype=np.complex128).reshape(-1)

    # C block: native volume callback on the recovered port field plus raw B.
    reduced_port, field_port = field_for(zero_trace, port_input)
    if reduced_port.shape != (local_trace_rows + local_port_rows,):
        raise ValueError("native q map did not produce the complete local reduced vector")
    native_port_volume = _native_volume_apply(volume_action, field_port, comm, counters=counters)
    native_B = action.apply_B_full(reduced_port[local_trace_rows:])
    c_reduced = action.reduce_rhs(native_port_volume + native_B, rhs_is_mpc_dual=True)
    outputs["C"] = np.asarray(c_reduced, dtype=np.complex128).reshape(-1)

    # -D block: raw original D on a trace-only recovered FE field.
    native_D_trace = action.apply_D_full(field_trace)
    d_reduced = action.reduce_rhs(
        np.zeros(full_rows, dtype=np.complex128),
        port_rhs=-native_D_trace,
        rhs_is_mpc_dual=True,
    )
    outputs["-D"] = np.asarray(d_reduced, dtype=np.complex128).reshape(-1)

    # Hhat block: original H_p and raw D on the recovered port-only field.
    native_D_port = action.apply_D_full(field_port)
    native_Hp = action._apply_original_h(reduced_port[local_trace_rows:])
    h_reduced = action.reduce_rhs(
        np.zeros(full_rows, dtype=np.complex128),
        port_rhs=-native_D_port + native_Hp,
        rhs_is_mpc_dual=True,
    )
    outputs["Hhat"] = np.asarray(h_reduced, dtype=np.complex128).reshape(-1)
    return outputs


def _project_native_components(
    *,
    action: Any,
    volume_action: Any,
    comm: Any,
    q_map: sparse.csr_matrix,
    trace_rows: int,
    trace_input: np.ndarray,
    port_input: np.ndarray,
) -> dict[str, np.ndarray]:
    """Project independent native component actions into a selected q space."""
    reduced_components = _native_component_reduced_actions(
        action=action,
        volume_action=volume_action,
        comm=comm,
        q_map=q_map,
        trace_rows=trace_rows,
        trace_input=trace_input,
        port_input=port_input,
    )
    return {
        key: np.asarray(q_map.conjugate().T @ value).reshape(-1)
        for key, value in reduced_components.items()
    }


def _native_projected_action(
    *,
    action: Any,
    volume_action: Any,
    comm: Any,
    input_map: sparse.csr_matrix,
    output_maps: tuple[sparse.csr_matrix, sparse.csr_matrix],
    source: np.ndarray,
    trace_rows: int,
    counters: dict[str, int] | None = None,
    include_components: bool = False,
) -> Any:
    split = int(trace_rows)
    trace_input = np.asarray(source[:split], dtype=np.complex128)
    port_input = np.asarray(source[split:], dtype=np.complex128)
    components = _native_component_reduced_actions(
        action=action,
        volume_action=volume_action,
        comm=comm,
        q_map=input_map,
        trace_rows=trace_rows,
        trace_input=trace_input,
        port_input=port_input,
        counters=counters,
    )
    native_reduced = sum(
        components.values(),
        np.zeros(int(action.reduced_size), dtype=np.complex128),
    )
    out0 = np.asarray(output_maps[0].conjugate().T @ native_reduced).reshape(-1)
    out1 = np.asarray(output_maps[1].conjugate().T @ native_reduced).reshape(-1)
    components0 = {
        key: np.asarray(output_maps[0].conjugate().T @ value).reshape(-1)
        for key, value in components.items()
    }
    components1 = {
        key: np.asarray(output_maps[1].conjugate().T @ value).reshape(-1)
        for key, value in components.items()
    }
    if include_components:
        return out0, out1, native_reduced, components0, components1
    return out0, out1, native_reduced


def run_task40_v25_selected_q0_consumer(
    cfg: Any,
    axes: Mapping[str, Any],
    *,
    output_directory: str | Path,
    allocation_gate: Callable[[str, Mapping[str, Any]], Any],
    resident_csr_admission: Callable[[str, int], Mapping[str, Any]] | None = None,
    frozen_modes: tuple[Any, ...] | None = None,
    frozen_mode_rows: tuple[Mapping[str, Any], ...] | None = None,
    frozen_mode_manifest_sha256: str | None = None,
    frozen_mode_keys: tuple[tuple[int, str, int, int, str], ...] | None = None,
    expected_ordered_mode_key_sha256: str | None = None,
    physical_model_sha256: str | None = None,
    jit_options: Mapping[str, Any] | None = None,
    build_csr: bool = True,
    structure_checkpoint_path: str | Path | None = None,
    structure_checkpoint_identity: Mapping[str, Any] | None = None,
    saved_producer_root: str | Path | None = None,
    saved_producer_identity: Mapping[str, Any] | None = None,
    saved_replay_root: str | Path | None = None,
    native_output_root: str | Path | None = None,
    saved_native_root: str | Path | None = None,
    saved_native_manifest_path: str | Path | None = None,
    current_identity: Mapping[str, Any] | None = None,
    perform_native_validation: bool = True,
) -> dict[str, Any]:
    """Build, persist, reload, and replay the complete regular-reference q0 consumer."""
    import gc
    from dataclasses import replace
    from dolfinx import fem, mesh as dmesh
    from mpi4py import MPI
    from petsc4py import PETSc

    from .dtn_boundary_phase_gauge import (
        BOUNDARY_PLANE,
        assembly_projection_denominator,
    )
    from .directional_boundary import FacetPolynomial
    from .dtn_port_3d import _dtn_surface_quadrature_degree
    from .fullspace_dtn_action import (
        iter_fullspace_dtn_functionals_from_surface,
    )
    from .fullspace_same_mesh_hcurl_pmg_physical import _build_split_volume_action
    from .task40_v20_mode_inventory import (
        TARGET_MODE_MANIFEST_SHA256,
        TARGET_REFERENCE_PLANES_NM,
    )
    from .task40_v22_operator_probe import (
        _V22NativeFacetRule,
        _build_v22_native_gauge_context,
        _global_mpc_expansions,
        _native_quadrature_identity,
    )
    from .fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS
    from .hcurl_assembly_time_condensation import build_unconstrained_assembly_time_condensation
    from .p6_cell_condensed_action import (
        P6GlobalDirectCarrierProvider,
        build_p6_cell_condensed_action_from_generated,
    )
    from .original_port_blocks import DiagonalOriginalPortBlock
    from .y_orbit_transform_bank import YOrbitTransformBank
    from .task40_v10_p6_yorbit import (
        LIMITS,
        TwoCellBranchCoordinates,
        _assemble_bounded_v17_row_tile_q_patterns,
        build_task40_v10_sector_contexts,
        collect_y_orbit_entities,
        trace_layout_coordinates,
        V16StagingLimitError,
    )
    from .task40_v10_p6_periodic_profile import TASK40_V20_P6_TARGET_ORIGINAL_NY8_PROFILE

    if not callable(allocation_gate):
        raise TypeError("selected q0 consumer requires the live whole-tree allocation gate")
    root = Path(output_directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    native_root = (
        Path(native_output_root).resolve()
        if native_output_root is not None
        else root
    )
    native_root.mkdir(parents=True, exist_ok=True)
    reuse_v25_producer = saved_producer_root is not None
    producer_root = Path(saved_producer_root).resolve() if reuse_v25_producer is True else None
    if reuse_v25_producer and (
        producer_root is None
        or not producer_root.is_dir()
        or not isinstance(saved_producer_identity, Mapping)
        or saved_replay_root is None
        or (not perform_native_validation and saved_native_root is None)
    ):
        raise ValueError("V26 native consumer requires its exact saved V25 producer and replay identities")
    replay_manifest: dict[str, Any] = {}
    replay_artifact_paths: dict[str, Path] = {}
    if reuse_v25_producer and saved_producer_identity is not None:
        replay_manifest, replay_artifact_paths = _load_v26_saved_replay_manifest(
            saved_replay_root, saved_producer_identity
        )
    reader_telemetry = _new_saved_stream_reader_telemetry()
    if MPI.COMM_SELF.Get_size() != 1 or np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
        raise RuntimeError("selected q0 requires MPI1 complex128 PETSc")
    if np.dtype(PETSc.IntType) != np.dtype(np.int32):
        raise RuntimeError("selected q0 is currently qualified only for int32 PETSc indices")

    profile = TASK40_V20_P6_TARGET_ORIGINAL_NY8_PROFILE
    global_axes = {key: tuple(map(float, axes[key])) for key in ("x", "y", "z")}
    cell_axes = tuple(len(global_axes[key]) - 1 for key in ("x", "y", "z"))
    if cell_axes != profile.global_cell_axes:
        raise ValueError(f"selected q0 reference axes differ from registered Ny8 grid: {cell_axes}")
    if int(cfg.nedelec_degree) != 6 or len(global_axes["y"]) != 9:
        raise ValueError("selected q0 requires the exact p6 Ny8 regular-reference input")

    regular_cfg = replace(
        cfg,
        air_void_box_nm=None,
        cell_notch=None,
        geometry_identity=(
            "task40extra_v26.saved_q0_regular_reference"
            if reuse_v25_producer
            else "task40extra_v25.selected_q0_regular_reference"
        ),
    )
    if (
        frozen_modes is None
        or frozen_mode_rows is None
        or frozen_mode_manifest_sha256 is None
    ):
        raise ValueError("selected q0 requires the complete frozen preflight mode inventory and manifest identity")
    generated_modes = tuple(frozen_modes)
    mode_rows = tuple(frozen_mode_rows)
    mode_sha = str(frozen_mode_manifest_sha256)
    mode_keys, computed_key_sha = _validate_frozen_mode_identity(
        generated_modes,
        mode_rows,
        expected_ordered_mode_key_sha256=expected_ordered_mode_key_sha256,
        frozen_mode_keys=frozen_mode_keys,
    )
    if mode_sha != TARGET_MODE_MANIFEST_SHA256:
        raise ValueError("q0 mode manifest SHA differs from the frozen source artifact")
    runtime_planes = {
        "bottom": float(regular_cfg.physical_z_min),
        "top": float(regular_cfg.physical_z_max),
    }
    if runtime_planes != TARGET_REFERENCE_PLANES_NM:
        raise ValueError("q0 actual configuration planes differ from the frozen mode-view planes")
    source_mode_rows, source_manifest_identity = _q0_source_mode_rows_from_runtime_view(
        mode_rows,
        generated_modes,
        expected_manifest_sha256=mode_sha,
        boundary_planes_nm_by_side=runtime_planes,
    )

    contexts = build_task40_v10_sector_contexts(generated_modes, regular_cfg, global_axes)
    context = next((row for row in contexts if 0 in row.global_q_indices), None)
    if context is None or tuple(map(int, context.global_q_indices)) != (0, 4):
        raise ValueError("Ny8 q0 must map to the registered twist-0 paired q4 sector")
    selected = np.asarray(context.original_mode_indices, dtype=np.int64)
    branches = np.asarray(context.local_branch_indices, dtype=np.int8)
    aliases = tuple(np.flatnonzero(branches == branch) for branch in (0, 1))
    if (
        len(np.unique(selected)) != len(selected)
        or not np.array_equal(np.sort(np.concatenate(aliases)), np.arange(len(selected)))
    ):
        raise ValueError("selected q0/q4 aliases do not form the complete actual twist-sector inventory")
    local_modes = tuple(generated_modes[int(index)] for index in selected)
    local_mode_rows = tuple(mode_rows[int(index)] for index in selected)
    local_inventory = (local_modes, local_mode_rows, mode_sha)
    global_h = np.full(len(generated_modes), np.nan, dtype=np.float64)
    for index in selected:
        global_h[int(index)] = assembly_projection_denominator(
            generated_modes[int(index)], regular_cfg, BOUNDARY_PLANE
        )
    if not np.isfinite(global_h[selected]).all() or np.any(global_h[selected] <= 0.0):
        raise ValueError("selected regular-reference original H_p values are not finite positive")

    local_cfg = replace(
        regular_cfg,
        case_name=f"{regular_cfg.case_name}_{'v26' if reuse_v25_producer else 'v25'}_q0_twist0",
        period_y=float(context.local_axes["y"][-1] - context.local_axes["y"][0]),
        grating_width_y=float(context.local_axes["y"][-1] - context.local_axes["y"][0]),
        mesh_axis_cell_counts=(profile.global_cell_axes[0], 2, profile.global_cell_axes[2]),
        mesh_axis_y_values=tuple(context.local_axes["y"]),
        mesh_plan_id=(
            "task40extra_v26.selected_q0_twist0_local_reference"
            if reuse_v25_producer
            else "task40extra_v25.selected_q0_twist0_local_reference"
        ),
        mesh_plan_sha256=None,
        geometry_identity=(
            "task40extra_v26.selected_q0_twist0_regular_reference"
            if reuse_v25_producer
            else "task40extra_v25.selected_q0_twist0_regular_reference"
        ),
    )
    phase_override = (complex(regular_cfg.floquet_phase_x), context.tau)
    local_levels = None
    volume_action = None
    surface_assemblers = None
    transform_bank = None
    condensed_system = None
    action = None
    direct_provider = None
    q_maps: tuple[sparse.csr_matrix, sparse.csr_matrix] | None = None
    saved_paths: dict[str, Path] = {}
    surface_stream_path = (
        producer_root / "v25_selected_q0_surface_functionals.bin"
        if reuse_v25_producer and producer_root is not None
        else root / "v25_selected_q0_surface_functionals.bin"
    )
    surface_stream_facts: dict[str, Any] = {}
    loaded_lookup: np.ndarray | None = None
    active_lookup_path: Path | None = None
    qmap_errors: dict[str, Any] = {}
    internal_B_nnz = 0
    internal_D_nnz = 0
    internal_port_references = 0
    internal_cell_ids = np.empty(0, dtype=np.int64)
    internal_direct_only_pass = False
    started = time.perf_counter()
    qdegree = _dtn_surface_quadrature_degree(regular_cfg, list(generated_modes))
    pre_fe_resource_gate = allocation_gate(
        "task40_v25_selected_q0_pre_fe_and_surface_phase",
        {
            "additional_payload_bytes": 8 * 1024**3,
            "disk_payload_bytes": 0,
            "reservation_kind": "whole-phase admission reservation, not measured peak RSS",
            "reserved_phase": "local p6 FE/MPC/maps, surface JIT and complete selected q0/q4 stream",
            "quadrature_degree": int(qdegree),
            "mode_count_full_reference": len(generated_modes),
            "selected_twist_alias_count_actual": int(len(selected)),
        },
    )
    try:
        from .fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels

        local_levels = _build_same_mesh_levels(
            local_cfg,
            MPI.COMM_SELF,
            (6,),
            include_positive_coefficients=False,
            research_phase_override=phase_override,
        )
        local_h = np.ascontiguousarray(
            global_h[selected] * (2.0 / float(len(global_axes["y"]) - 1)),
            dtype=np.float64,
        )
        expected_local_h = global_h[selected] / float(len(global_axes["y"]) - 1) * 2.0
        h_scale_error = _relative_error(local_h, expected_local_h)
        if h_scale_error["relative_to_component"] > 1.0e-12:
            raise ValueError("local/global original H_p scaling differs from the actual 2/8 cell ratio")
        saved_h_error: dict[str, float] | None = None
        if reuse_v25_producer:
            saved_h_path = producer_root / "v25_selected_q0_local_H_p.npy"
            saved_h = np.load(saved_h_path, allow_pickle=False)
            if saved_h.shape != local_h.shape or saved_h.dtype != np.dtype(np.complex128):
                raise ValueError("saved V25 local H_p does not match the complete q0/q4 alias inventory")
            saved_h_error = _relative_error(saved_h, local_h)
            if saved_h_error["relative_to_component"] > 1.0e-12:
                raise ValueError("saved V25 local H_p differs from the freshly derived regular-reference values")
            local_h = np.ascontiguousarray(saved_h.real, dtype=np.float64)

        mesh_object = local_levels["mesh"]
        function_space = local_levels["spaces"][6]
        floquet = local_levels["floquets"][6]
        local_cell_count = int(mesh_object.topology.index_map(3).size_local)
        if local_cell_count != int(profile.local_cell_count):
            raise ValueError("selected twist-0 mesh does not cover the complete 7,616-cell reference sector")
        mesh_data = local_levels["mesh_data"]
        side_facet_counts = {
            "bottom": int(len(mesh_data.facet_tags.find(int(local_cfg.tags.z_min)))),
            "top": int(len(mesh_data.facet_tags.find(int(local_cfg.tags.z_max)))),
        }
        finalized_mpc_slave_count = int(len(floquet.mpc.slaves))
        finalized_mpc_master_count = int(len(floquet.mpc.masters.array))
        native_inventory_bytes = (
            sum(side_facet_counts.values()) * (2048 + 882 * 24)
            + finalized_mpc_slave_count * 128
            + finalized_mpc_master_count * 24
        )
        allocation_gate(
            "task40_v25_q0_native_surface_inventory_and_mpc_closure",
            {
                "additional_payload_bytes": int(native_inventory_bytes),
                "disk_payload_bytes": 0,
                "reservation_kind": "admission estimate before native mapping/MPC materialization; not measured RSS",
                "facet_count_by_side": side_facet_counts,
                "local_dofs_per_boundary_cell": 882,
                "finalized_mpc_slave_count": finalized_mpc_slave_count,
                "finalized_mpc_master_count": finalized_mpc_master_count,
                "quadrature_degree": int(qdegree),
            },
        )
        (
            mapping_rows,
            support_groups,
            allowed_rows_by_side,
            permutation_info,
            native_inventory,
        ) = _q0_reference_surface_inventory(mesh_data, function_space, local_cfg)
        support_rows = tuple({"bottom": 0, "top": 1}[str(mode.side)] for mode in local_modes)
        dof_index_map = function_space.dofmap.index_map
        boundary_cell_ids = sorted(
            {int(row["cell_id"]) for row in mapping_rows}
        )
        boundary_global_rows = np.unique(
            np.concatenate(
                [
                    np.asarray(
                        dof_index_map.local_to_global(
                            np.asarray(function_space.dofmap.cell_dofs(cell), dtype=np.int32)
                        ),
                        dtype=np.int64,
                    )
                    for cell in boundary_cell_ids
                ]
            )
        )
        mpc_expansions = _global_mpc_expansions(
            floquet.mpc, dof_index_map, boundary_global_rows
        )
        compact_upper_rows = (
            len(boundary_cell_ids) * 882
            + sum(len(masters) for masters, _coefficients in mpc_expansions.values())
        )
        allocation_gate(
            "task40_v25_q0_native_surface_compact_rows",
            {
                "additional_payload_bytes": int(
                    compact_upper_rows
                    * (
                        np.dtype(PETSc.IntType).itemsize
                        + np.dtype(np.int64).itemsize
                        + 2 * np.dtype(np.complex128).itemsize
                    )
                ),
                "disk_payload_bytes": 0,
                "reservation_kind": "upper bound for native boundary row and finalized MPC master closure arrays",
                "boundary_cell_count": len(boundary_cell_ids),
                "boundary_global_row_count": int(len(boundary_global_rows)),
                "finalized_mpc_expansion_slave_count": len(mpc_expansions),
                "finalized_mpc_expansion_master_count": sum(
                    len(masters) for masters, _coefficients in mpc_expansions.values()
                ),
            },
        )
        native_rule = _V22NativeFacetRule(
            space=function_space,
            dof_index_map=dof_index_map,
            mapping_rows=mapping_rows,
            permutation_info=permutation_info,
            polynomial=FacetPolynomial(function_space.element.basix_element),
            quadrature_degree=qdegree,
            cfg=local_cfg,
            mpc_expansions=mpc_expansions,
        )
        surface_assemblers = native_rule.assemblers()
        native_quadrature_identity = _native_quadrature_identity(qdegree)
        assembly_context = _build_v22_native_gauge_context(
            space=function_space,
            mesh_data=mesh_data,
            mpc=floquet.mpc,
            cfg=local_cfg,
            quadrature_identity=native_quadrature_identity,
            permutation_info=permutation_info,
            cell_dofmap_sha256=native_inventory["cell_dofmap_sha256"],
        )
        local_entities = collect_y_orbit_entities(
            function_space,
            floquet,
            local_cfg,
            context.local_axes,
            transform_bank=(transform_bank := YOrbitTransformBank(
                mapping_limit=LIMITS["mapping"], allocation_gate=allocation_gate
            )),
        )
        volume_action = _build_split_volume_action(
            local_levels["mesh_data"],
            local_cfg,
            function_space,
            floquet,
            jit_options=dict(jit_options or SAME_MESH_JIT_OPTIONS),
        )
        compiled = fem.form(
            volume_action.bilinear_form,
            **({"jit_options": dict(jit_options or SAME_MESH_JIT_OPTIONS)}),
        )
        condensed_system = build_unconstrained_assembly_time_condensation(
            compiled,
            function_space,
            local_levels["mesh_data"].cell_tags,
            mpc=floquet.mpc,
            appended_global_rows=len(local_modes),
            appended_support_owned_cell_groups=support_groups,
            appended_support_group_by_row=support_rows,
            sum_duplicate_cell_integrals=True,
            strict_local_checks=True,
            materialize_global_matrix=False,
            retain_local_schur_for_matrix_free=True,
            share_identity_cache=True,
            preserve_exact_geometry=True,
            allocation_gate=allocation_gate,
        )
        actual_local_inventory = (
            int(condensed_system.full_rows),
            int(condensed_system.active_rows),
            int(condensed_system.active_interior_rows),
            int(condensed_system.appended_rows),
        )
        expected_local_inventory = (
            int(profile.local_storage_rows),
            int(profile.local_trace_rows),
            int(profile.local_interior_rows),
            len(local_modes),
        )
        if actual_local_inventory != expected_local_inventory:
            raise ValueError(f"selected-q0 local FE/MPC inventory differs: {actual_local_inventory}")
        active_trace_rows = int(condensed_system.active_rows)

        interior_parts = [
            np.asarray(cell.interior_original_dofs, dtype=np.int64).reshape(-1)
            for cell in condensed_system.cell_recovery_maps
            if len(cell.interior_original_dofs)
        ]
        interior_rows = np.concatenate(interior_parts) if interior_parts else np.empty(0, dtype=np.int64)
        interior_rows.sort()
        if interior_rows.size > 1 and np.any(interior_rows[1:] == interior_rows[:-1]):
            raise ValueError("selected-q0 interior row ownership is not unique")
        if reuse_v25_producer:
            active_lookup_path = producer_root / "v25_selected_q0_original_to_active_int32.npy"
            loaded_lookup, active_trace_rows = _load_saved_v26_active_lookup(
                active_lookup_path,
                condensed_system=condensed_system,
                expected_full_rows=profile.local_storage_rows,
                allocation_gate=allocation_gate,
            )
            surface_stream_facts = _audit_saved_surface_functional_stream(
                surface_stream_path,
                selected_indices=selected,
                local_modes=local_modes,
                local_h=local_h,
                allowed_rows_by_side=allowed_rows_by_side,
                interior_rows=interior_rows,
                active_lookup=loaded_lookup,
                active_rows=active_trace_rows,
                allocation_gate=allocation_gate,
                reader_telemetry=reader_telemetry,
            )
            producer_payloads = {
                str(item.get("path")): item
                for item in saved_producer_identity.get("payloads", [])
                if isinstance(item, Mapping)
            }
            if (
                surface_stream_facts["sha256"]
                != producer_payloads.get("v25_selected_q0_surface_functionals.bin", {}).get("sha256")
            ):
                raise IOError("saved V25 surface stream changed during the row/MPC support audit")
            surface_stream_facts["producer_identity_sha256"] = hashlib.sha256(
                json.dumps(saved_producer_identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            surface_stream_facts["source_mode_manifest_identity"] = source_manifest_identity
            surface_stream_facts["native_surface_adapter"] = {
                "implementation": "V25 producer stream row-audited against the newly built native q0 FE/MPC",
                "inventory": native_inventory,
                "geometry_class_ids_by_side": {
                    side: list(native_rule.class_ids_by_side[side])
                    for side in ("bottom", "top")
                },
                "candidate_global_row_count": int(len(native_rule.candidate_rows)),
                "candidate_global_rows_sha256": _array_sha256(native_rule.candidate_rows),
                "finalized_mpc_expansion_slave_count": int(len(mpc_expansions)),
                "native_quadrature_identity": native_quadrature_identity,
                "production_integrator_rerun": False,
            }
        else:
            stream_audit: dict[str, Any] = {}
            production_entries = iter_fullspace_dtn_functionals_from_surface(
                generated_modes,
                surface_assemblers,
                floquet.mpc,
                local_cfg,
                phase_gauge=BOUNDARY_PLANE,
                assembly_context=assembly_context,
                mode_indices=tuple(map(int, selected)),
                precomputed_mode_rows=source_mode_rows,
                precomputed_physical_manifest_sha256=mode_sha,
                audit=stream_audit,
            )
            surface_stream_facts = _write_surface_functional_stream(
                surface_stream_path,
                production_entries,
                selected_indices=selected,
                local_modes=local_modes,
                local_h=local_h,
                allowed_rows_by_side=allowed_rows_by_side,
                interior_rows=interior_rows,
            )
            surface_stream_facts["generation_audit"] = stream_audit
            surface_stream_facts["source_mode_manifest_identity"] = source_manifest_identity
            surface_stream_facts["native_surface_adapter"] = {
                "implementation": "_V22NativeFacetRule on the actual q0 regular-reference mesh",
                "inventory": native_inventory,
                "geometry_class_ids_by_side": {
                    side: list(native_rule.class_ids_by_side[side])
                    for side in ("bottom", "top")
                },
                "candidate_global_row_count": int(len(native_rule.candidate_rows)),
                "candidate_global_rows_sha256": _array_sha256(native_rule.candidate_rows),
                "finalized_mpc_expansion_slave_count": int(len(mpc_expansions)),
                "native_quadrature_identity": native_quadrature_identity,
                "assembly_stats": native_rule.assembly_stats,
            }
            saved_paths["production_surface_functionals"] = surface_stream_path
        internal_B_nnz = int(surface_stream_facts["internal_nonzero_entry_count"]["B"])
        internal_D_nnz = int(surface_stream_facts["internal_nonzero_entry_count"]["D"])
        if internal_B_nnz or internal_D_nnz:
            partial = {
                "schema": _SCHEMA,
                "status": "PARTIAL_REFERENCE_NONZERO_INTERNAL_DTN_SUPPORT",
                "classification": "RAW_PRODUCTION_SUPPORT_PRESERVED; DIRECT_ONLY_Q0_NOT_QUALIFIED",
                "official_result": False,
                "selected_q": 0,
                "paired_q": 4,
                "full_mode_manifest_sha256": mode_sha,
                "source_mode_manifest_identity": source_manifest_identity,
                "ordered_mode_key_sha256": computed_key_sha,
                "actual_q0_alias_count": len(aliases[0]),
                "actual_q4_alias_count": len(aliases[1]),
                "raw_surface_stream": surface_stream_facts,
                "internal_B_nonzero_count": internal_B_nnz,
                "internal_D_nonzero_count": internal_D_nnz,
                "reason": "The complete production stream contains real internal B/D values; no values were dropped or zeroed.",
                "target_volume_branch_independent": True,
                "not_run": ["complete q0 action", "q0/q4 replay", "optional CSR"],
            }
            partial_path = root / "v25_selected_q0_consumer.json"
            _write_json(partial_path, partial)
            saved_paths["operation"] = partial_path
            return partial

        local_mode_keys = tuple(
            _mode_key(int(index), mode)
            for index, mode in zip(selected, local_modes, strict=True)
        )
        original_hp = DiagonalOriginalPortBlock(np.asarray(local_h, dtype=np.complex128), local_mode_keys)
        provider_sweeps = {"provider_sweep_count": 0}

        def iter_native_surface_functionals():
            yield from _make_saved_v26_surface_provider(
                path=surface_stream_path,
                selected_indices=selected,
                local_modes=local_modes,
                local_h=local_h,
                mode_rows=mode_rows,
                interior_rows=interior_rows,
                active_lookup=loaded_lookup if reuse_v25_producer else None,
                active_rows=active_trace_rows,
                counters=provider_sweeps,
                reader_telemetry=reader_telemetry,
            )()

        direct_provider = P6GlobalDirectCarrierProvider(
            iter_native_surface_functionals,
            condensed=condensed_system,
            mode_count=len(local_modes),
            interior_rows_are_managed=False,
            interior_rows=interior_rows,
            source_label="saved_production_surface_functional_stream",
        )
        direct_provider.bind_original_port_block(original_hp)
        action = build_p6_cell_condensed_action_from_generated(
            condensed_system,
            original_hp,
            {},
            global_direct_provider=direct_provider,
            owns_condensed=True,
        )
        condensed_system = None
        trace = trace_layout_coordinates(
            local_entities,
            action.condensed,
            cell_phase_y=context.eta,
            allocation_gate=allocation_gate,
        )
        coordinates = TwoCellBranchCoordinates(
            trace,
            trace_rows=action.condensed.active_rows,
            local_modes=local_modes,
            local_h=local_h,
            context=context,
            allocation_gate=allocation_gate,
        )
        q_maps = tuple(
            coordinates.q_map(branch, allocation_gate=allocation_gate)
            for branch in (0, 1)
        )
        q0_map, q4_map = q_maps
        trace_q_rows = int(q0_map.shape[1] - len(aliases[0]))
        if trace_q_rows != int(profile.trace_rows_per_q):
            raise ValueError("locally derived reference q trace width differs from the registered FE profile")
        expected_q0_rows = int(trace_q_rows + len(aliases[0]))
        if q0_map.shape != (action.reduced_size, expected_q0_rows):
            raise ValueError(f"selected q0 map does not cover its complete profile row domain: {q0_map.shape}")
        if q4_map.shape[1] != int(profile.trace_rows_per_q + len(aliases[1])):
            raise ValueError("paired q4 local map does not cover its complete actual alias domain")
        q_map_paths: list[Path] = []
        q0_saved: sparse.csr_matrix | None = None
        q4_saved: sparse.csr_matrix | None = None
        if reuse_v25_producer:
            producer_map_bytes = sum(
                int(item["bytes"])
                for item in saved_producer_identity["payloads"]
                if item.get("path") in {"v25_selected_q0_map.npz", "v25_selected_q4_map.npz"}
            )
            allocation_gate(
                "task40_v26_saved_q_maps_compare_with_fresh_local_floquet_maps",
                {
                    "additional_payload_bytes": producer_map_bytes,
                    "workspace_bytes": 0,
                    "disk_payload_bytes": 0,
                    "mapping_tolerance": 1.0e-12,
                    "saved_maps_loaded_together": True,
                },
            )
            saved_maps: list[sparse.csr_matrix] = []
            for branch, fresh_map in enumerate(q_maps):
                q_index = 4 * branch
                q_map_path = producer_root / f"v25_selected_q{q_index}_map.npz"
                saved_map = sparse.load_npz(q_map_path).tocsr()
                if (
                    saved_map.shape != fresh_map.shape
                    or saved_map.dtype != np.dtype(np.complex128)
                    or saved_map.indices.dtype != np.dtype(np.int32)
                    or saved_map.indptr.dtype != np.dtype(np.int32)
                    or not saved_map.has_canonical_format
                    or not np.array_equal(saved_map.indptr, fresh_map.indptr)
                    or not np.array_equal(saved_map.indices, fresh_map.indices)
                ):
                    raise ValueError(f"saved V25 q{q_index} map structure differs from the fresh local FE/MPC map")
                value_error = _relative_error(saved_map.data, fresh_map.data)
                if value_error["relative_to_component"] > 1.0e-12:
                    raise ValueError(f"saved V25 q{q_index} map values exceed the local mapping tolerance")
                qmap_errors[f"q{q_index}"] = value_error
                saved_maps.append(saved_map)
                q_map_paths.append(q_map_path)
            q0_saved, q4_saved = saved_maps
            q_maps = (q0_saved, q4_saved)
            q0_map, q4_map = q_maps

        # Production direct-only evidence is restricted to the selected real sector.
        mesh_object = local_levels["mesh"]
        local_cell_count = int(mesh_object.topology.index_map(3).size_local)
        if local_cell_count != int(profile.local_cell_count) or len(action._cells) != local_cell_count:
            raise ValueError("selected twist-0 FE action does not cover all 7,616 regular-reference cells")
        midpoint = dmesh.compute_midpoints(
            mesh_object, 3, np.arange(local_cell_count, dtype=np.int32)
        )
        z_axis = np.asarray(context.local_axes["z"], dtype=np.float64)
        z_layers = np.searchsorted(z_axis, midpoint[:, 2], side="right") - 1
        z_layers = np.clip(z_layers, 0, len(z_axis) - 2)
        internal_cell_ids = np.flatnonzero((z_layers > 0) & (z_layers < len(z_axis) - 2))
        internal_port_references = sum(len(action._cells[int(cell)].ports) for cell in internal_cell_ids)
        internal_direct_only_pass = bool(
            surface_stream_facts.get("numeric_internal_support_empty") is True
            and internal_port_references == 0
        )

        # Persist and replay the complete matrix-free consumer before trying
        # the optional resident/full-q CSR upgrade.
        if reuse_v25_producer:
            volume_stream_path = producer_root / "v25_selected_q0_volume_classes.bin"
            volume_payload = next(
                item for item in saved_producer_identity["payloads"]
                if item.get("path") == "v25_selected_q0_volume_classes.bin"
            )
            volume_layout = _scan_persisted_volume_stream(volume_stream_path)
            if (
                volume_layout["class_count"] != 45
                or volume_layout["cell_count"] != profile.local_cell_count
                or volume_stream_path.stat().st_size != volume_payload["bytes"]
                or _file_sha256(volume_stream_path) != volume_payload["sha256"]
            ):
                raise IOError("saved V25 volume stream differs from its complete-cell producer identity")
            volume_stream_facts = {
                **dict(volume_payload),
                "unique_class_schur_count": volume_layout["class_count"],
                "unique_class_schur_payload_bytes": volume_layout["class_payload_bytes"],
                "cell_mapping_count": volume_layout["cell_count"],
                "maximum_single_cell_mapping_payload_bytes": volume_layout["maximum_cell_payload_bytes"],
                "reused_from_saved_producer": True,
            }
            active_lookup_path = producer_root / "v25_selected_q0_original_to_active_int32.npy"
            hp_path = producer_root / "v25_selected_q0_local_H_p.npy"
            if loaded_lookup is None or q0_saved is None or q4_saved is None:
                raise RuntimeError("V26 producer lookup/maps were not compared with the fresh local FE/MPC maps")
        else:
            volume_stream_path = root / "v25_selected_q0_volume_classes.bin"
            volume_stream_facts = _write_volume_class_stream(
                volume_stream_path, action, allocation_gate
            )
            saved_paths["shared_volume_class_and_cell_map"] = volume_stream_path
            hp_path = root / "v25_selected_q0_local_H_p.npy"
            _save_npy(hp_path, np.asarray(local_h, dtype=np.complex128))
            saved_paths["local_H_p"] = hp_path

            active_lookup_path = root / "v25_selected_q0_original_to_active_int32.npy"
            allocation_gate("task40_v25_q0_original_to_active_map", {
                "matrix_payload_bytes": int(action.condensed.full_rows * np.dtype(np.int32).itemsize),
                "workspace_bytes": int(action.condensed.full_rows * np.dtype(np.int32).itemsize),
                "mapping_source": "finalized condensation trace_constraints.original_to_active",
                "identity_rows_implicitly_expanded": True,
            })
            active_lookup = np.full(action.condensed.full_rows, -1, dtype=np.int32)
            for original, active_index in action.condensed.trace_constraints.original_to_active.items():
                active_lookup[int(original)] = int(active_index)
            _save_npy(active_lookup_path, active_lookup)
            saved_paths["original_to_active"] = active_lookup_path
            del active_lookup

            q_map_paths = []
            reloaded_q_maps = []
            for branch, q_map in enumerate(q_maps):
                q_map_path = root / f"v25_selected_q{4 * branch}_map.npz"
                q_map_temp = q_map_path.with_name(q_map_path.stem + ".tmp.npz")
                if q_map_path.exists() or q_map_temp.exists():
                    raise FileExistsError(f"refusing to replace saved q map {q_map_path}")
                with q_map_temp.open("xb") as stream:
                    sparse.save_npz(stream, q_map, compressed=False)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(q_map_temp, q_map_path)
                reloaded = sparse.load_npz(q_map_path).tocsr()
                if reloaded.shape != q_map.shape or reloaded.nnz != q_map.nnz:
                    raise IOError("reloaded q map has a different shape or structural count")
                q_map_paths.append(q_map_path)
                reloaded_q_maps.append(reloaded)
                saved_paths[f"q{4 * branch}_map"] = q_map_path
            loaded_lookup = np.load(active_lookup_path, mmap_mode="r", allow_pickle=False)
            if loaded_lookup.shape != (action.condensed.full_rows,) or loaded_lookup.dtype != np.dtype(np.int32):
                raise IOError("reloaded original-to-active mapping has an invalid shape or dtype")
            q0_saved, q4_saved = tuple(reloaded_q_maps)
            if _file_sha256(surface_stream_path) != surface_stream_facts["sha256"]:
                raise IOError("saved raw production surface stream failed its immediate SHA readback")
            if _file_sha256(volume_stream_path) != volume_stream_facts["sha256"]:
                raise IOError("saved shared-class volume stream failed its immediate SHA readback")

        if reuse_v25_producer:
            with np.load(replay_artifact_paths["inputs"], allow_pickle=False) as input_archive:
                x1 = np.asarray(input_archive["q0_case_1"]).copy()
                x2 = np.asarray(input_archive["q0_case_2"]).copy()
                x4 = np.asarray(input_archive["q4_pair"]).copy()

            def saved_stream_case(case_name: str, branch: str) -> dict[str, np.ndarray]:
                with np.load(replay_artifact_paths[case_name], allow_pickle=False) as archive:
                    if branch == "q0":
                        keys = {
                            "total": "q0_total",
                            "volume": "q0_volume",
                            "C": "q0_C",
                            "-D": "q0_minus_D",
                            "Hhat": "q0_Hhat",
                            "other_total": "q4_total_from_q0",
                            "other_volume": "q4_volume_from_q0",
                            "other_C": "q4_C_from_q0",
                            "other_-D": "q4_minus_D_from_q0",
                            "other_Hhat": "q4_Hhat_from_q0",
                        }
                    else:
                        keys = {
                            "total": "q4_total",
                            "volume": "q4_volume",
                            "C": "q4_C",
                            "-D": "q4_minus_D",
                            "Hhat": "q4_Hhat",
                            "other_total": "q0_total_from_q4",
                            "other_volume": "q0_volume_from_q4",
                            "other_C": "q0_C_from_q4",
                            "other_-D": "q0_minus_D_from_q4",
                            "other_Hhat": "q0_Hhat_from_q4",
                        }
                    return {name: np.asarray(archive[key]).copy() for name, key in keys.items()}

            stream_y1 = saved_stream_case("q0_case_1", "q0")
            stream_y2 = saved_stream_case("q0_case_2", "q0")
            stream_y4 = saved_stream_case("q4_pair", "q4")
            stream_replay_seconds = float(
                sum(
                    float(replay_manifest.get("cases", {}).get(name, {}).get("elapsed_seconds", 0.0))
                    for name in ("q0_case_1", "q0_case_2", "q4_pair")
                )
            )
        else:
            rng = np.random.default_rng(402500)
            x1 = np.asarray(
                (rng.standard_normal(q0_map.shape[1]) + 1j * rng.standard_normal(q0_map.shape[1]))
                / np.sqrt(2.0), dtype=np.complex128
            )
            x2 = np.asarray(
                (rng.standard_normal(q0_map.shape[1]) + 1j * rng.standard_normal(q0_map.shape[1]))
                / np.sqrt(2.0), dtype=np.complex128
            )
            if not np.all(x1 != 0) or not np.all(x2 != 0) or np.array_equal(x1, x2):
                raise RuntimeError("selected q0 replay inputs must be distinct and everywhere nonzero")
            stream_replay_started = time.perf_counter()
            stream_y1 = _apply_persisted_consumer(
                input_map=q0_saved, output_map=q0_saved, other_output_map=q4_saved,
                source=x1, surface_stream_path=surface_stream_path,
                volume_stream_path=volume_stream_path, active_lookup=loaded_lookup,
                active_rows=action.condensed.active_rows, local_modes=local_modes,
                selected_indices=selected, local_h=local_h, mode_rows=mode_rows,
                interior_rows=interior_rows, trace_q_rows=trace_q_rows,
                allocation_gate=allocation_gate, reader_telemetry=reader_telemetry,
            )
            stream_y2 = _apply_persisted_consumer(
                input_map=q0_saved, output_map=q0_saved, other_output_map=q4_saved,
                source=x2, surface_stream_path=surface_stream_path,
                volume_stream_path=volume_stream_path, active_lookup=loaded_lookup,
                active_rows=action.condensed.active_rows, local_modes=local_modes,
                selected_indices=selected, local_h=local_h, mode_rows=mode_rows,
                interior_rows=interior_rows, trace_q_rows=trace_q_rows,
                allocation_gate=allocation_gate, reader_telemetry=reader_telemetry,
            )
            stream_replay_seconds = float(time.perf_counter() - stream_replay_started)
            rng4_real = np.random.default_rng(402504)
            rng4_imag = np.random.default_rng(402505)
            x4 = np.asarray(
                rng4_real.standard_normal(q4_saved.shape[1])
                + 1j * rng4_imag.standard_normal(q4_saved.shape[1]), dtype=np.complex128
            ) / np.sqrt(2.0)
            if not np.all(x4 != 0):
                raise RuntimeError("paired q4 witness input must be nonzero")
            stream_y4 = _apply_persisted_consumer(
                input_map=q4_saved, output_map=q4_saved, other_output_map=q0_saved,
                source=x4, surface_stream_path=surface_stream_path,
                volume_stream_path=volume_stream_path, active_lookup=loaded_lookup,
                active_rows=action.condensed.active_rows, local_modes=local_modes,
                selected_indices=selected, local_h=local_h, mode_rows=mode_rows,
                interior_rows=interior_rows,
                trace_q_rows=int(q4_map.shape[1] - len(aliases[1])),
                allocation_gate=allocation_gate, reader_telemetry=reader_telemetry,
            )
        if (
            not np.all(x1 != 0)
            or not np.all(x2 != 0)
            or not np.all(x4 != 0)
            or np.array_equal(x1, x2)
        ):
            raise RuntimeError("V26 replay inputs must be distinct q0 vectors and nonzero q0/q4 vectors")

        native_counters = {"native_volume_apply_count": 0}
        native_case_records: dict[str, Any] = {}
        native_manifest: dict[str, Any] | None = None
        native_y1_components: dict[str, np.ndarray]
        native_y4_components: dict[str, np.ndarray]
        producer_identity_sha256 = (
            hashlib.sha256(
                json.dumps(
                    saved_producer_identity,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            if reuse_v25_producer
            else ""
        )
        replay_manifest_sha256 = str(replay_manifest.get("manifest_sha256", "")) if reuse_v25_producer else ""
        if reuse_v25_producer and not perform_native_validation:
            native_manifest, native_loaded = _load_v26_native_action(
                saved_native_root,
                producer_identity_sha256=producer_identity_sha256,
                replay_manifest_sha256=replay_manifest_sha256,
                manifest_path=saved_native_manifest_path,
                recovery_identity=current_identity,
            )
            native_counters = {
                "native_volume_apply_count": native_manifest.get("native_volume_apply_count"),
                "provider_sweep_count": native_manifest.get("provider_sweep_count"),
            }
            native_count_provenance = native_manifest.get("count_provenance", {})
            native_action_elapsed_seconds = native_manifest.get("elapsed_seconds")
            native_action_elapsed_seconds_status = native_manifest.get(
                "elapsed_seconds_status",
                "MEASURED" if native_action_elapsed_seconds is not None else "UNKNOWN",
            )
            native_y1_q0 = native_loaded["q0_case_1"]["native_q0_total"]
            native_y1_q4 = native_loaded["q0_case_1"]["native_q4_from_q0"]
            native_y2_q0 = native_loaded["q0_case_2"]["native_q0_total"]
            native_y4_q0 = native_loaded["q4_pair"]["native_q0_from_q4"]
            native_y4_q4 = native_loaded["q4_pair"]["native_q4_total"]
            native_y1_components = _native_q0_components_from_saved_case(
                native_loaded["q0_case_1"]
            )
            native_y4_components = {}
            native_case_records = dict(native_manifest["cases"])
        else:
            native_call_started = time.perf_counter()
            if reuse_v25_producer:
                native_y1_q0, native_y1_q4, _, native_y1_components, _native_y1_q4_components = _native_projected_action(
                    action=action, volume_action=volume_action, comm=mesh_object.comm,
                    input_map=q0_map, output_maps=q_maps, source=x1, trace_rows=trace_q_rows,
                    counters=native_counters, include_components=True,
                )
                native_case_records["q0_case_1"] = _persist_v26_native_case(
                    native_root,
                    "q0_case_1",
                    {
                        "native_q0_total": native_y1_q0,
                        "native_q4_from_q0": native_y1_q4,
                        **{f"native_q0_{name.replace('-', 'minus_')}": value for name, value in native_y1_components.items()},
                    },
                    producer_identity_sha256=producer_identity_sha256,
                    replay_manifest_sha256=replay_manifest_sha256,
                    current_identity=current_identity or {},
                )
                native_y2_q0, native_y2_q4, _, _native_y2_q0_components, _native_y2_q4_components = _native_projected_action(
                    action=action, volume_action=volume_action, comm=mesh_object.comm,
                    input_map=q0_map, output_maps=q_maps, source=x2, trace_rows=trace_q_rows,
                    counters=native_counters, include_components=True,
                )
                native_case_records["q0_case_2"] = _persist_v26_native_case(
                    native_root,
                    "q0_case_2",
                    {"native_q0_total": native_y2_q0, "native_q4_from_q0": native_y2_q4},
                    producer_identity_sha256=producer_identity_sha256,
                    replay_manifest_sha256=replay_manifest_sha256,
                    current_identity=current_identity or {},
                )
                native_y4_q0, native_y4_q4, _, native_y4_components, _native_y4_q4_components = _native_projected_action(
                    action=action, volume_action=volume_action, comm=mesh_object.comm,
                    input_map=q4_map, output_maps=q_maps, source=x4, trace_rows=trace_q_rows,
                    counters=native_counters, include_components=True,
                )
                native_case_records["q4_pair"] = _persist_v26_native_case(
                    native_root,
                    "q4_pair",
                    {"native_q0_from_q4": native_y4_q0, "native_q4_total": native_y4_q4},
                    producer_identity_sha256=producer_identity_sha256,
                    replay_manifest_sha256=replay_manifest_sha256,
                    current_identity=current_identity or {},
                )
                native_y4_components = {}
            else:
                native_y1_q0, native_y1_q4, _ = _native_projected_action(
                    action=action, volume_action=volume_action, comm=mesh_object.comm,
                    input_map=q0_map, output_maps=q_maps, source=x1, trace_rows=trace_q_rows,
                    counters=native_counters,
                )
                native_y2_q0, _native_y2_q4, _ = _native_projected_action(
                    action=action, volume_action=volume_action, comm=mesh_object.comm,
                    input_map=q0_map, output_maps=q_maps, source=x2, trace_rows=trace_q_rows,
                    counters=native_counters,
                )
                native_y4_q0, native_y4_q4, _ = _native_projected_action(
                    action=action, volume_action=volume_action, comm=mesh_object.comm,
                    input_map=q4_map, output_maps=q_maps, source=x4, trace_rows=trace_q_rows,
                    counters=native_counters,
                )
            native_action_elapsed_seconds = float(time.perf_counter() - native_call_started)
            native_action_elapsed_seconds_status = "MEASURED"
            native_count_provenance = {
                "native_volume_apply_count": "MEASURED",
                "provider_sweep_count": "MEASURED",
            }

        if reuse_v25_producer:
            if perform_native_validation:
                native_counters["provider_sweep_count"] = int(provider_sweeps["provider_sweep_count"])
            else:
                native_action_elapsed_seconds = native_manifest.get("elapsed_seconds")
                native_action_elapsed_seconds_status = native_manifest.get(
                    "elapsed_seconds_status",
                    "MEASURED" if native_action_elapsed_seconds is not None else "UNKNOWN",
                )

        stream_error_1 = _relative_error(stream_y1["total"], native_y1_q0)
        stream_error_2 = _relative_error(stream_y2["total"], native_y2_q0)
        if max(stream_error_1["relative_to_component"], stream_error_2["relative_to_component"]) > LIMITS["operator"]:
            raise RuntimeError("reloaded complete q0 stream failed two distinct native action replays")

        if reuse_v25_producer:
            native_volume = native_y1_components["volume"]
            native_c = native_y1_components["C"]
            native_minus_d = native_y1_components["-D"]
            native_h = native_y1_components["Hhat"]
            component_errors = {
                "volume": _relative_error(stream_y1["volume"], native_volume),
                "C": _relative_error(stream_y1["C"], native_c),
                "-D": _relative_error(stream_y1["-D"], native_minus_d),
                "Hhat": _relative_error(stream_y1["Hhat"], native_h),
            }
            cross_04_error = _relative_error_with_scale(
                stream_y1["other_total"], native_y1_q4, native_y1_q0
            )
            cross_40_error = _relative_error_with_scale(
                stream_y4["other_total"], native_y4_q0, native_y4_q4
            )
            q4_diagonal_error = _relative_error(stream_y4["total"], native_y4_q4)
            native_q0_diagonal_norm = _positive_finite_native_norm(
                native_y1_q0, label="q0"
            )
            native_q4_diagonal_norm = _positive_finite_native_norm(
                native_y4_q4, label="q4"
            )
            stream_offdiag_04 = _l2(stream_y1["other_total"]) / native_q0_diagonal_norm
            stream_offdiag_40 = _l2(stream_y4["other_total"]) / native_q4_diagonal_norm
            if (
                any(value["relative_to_component"] > LIMITS["operator"] for value in component_errors.values())
                or max(
                    cross_04_error["relative_to_component"],
                    cross_40_error["relative_to_component"],
                    q4_diagonal_error["relative_to_component"],
                    stream_offdiag_04,
                    stream_offdiag_40,
                ) > 1.0e-11
            ):
                raise RuntimeError("V26 saved stream failed the scaled native q0/q4 replay gates")
        else:
            x_trace = np.asarray(x1[:trace_q_rows], dtype=np.complex128)
            x_port = np.asarray(x1[trace_q_rows:], dtype=np.complex128)
            native_volume = _project_native_components(
                action=action, volume_action=volume_action, comm=mesh_object.comm,
                q_map=q0_map, trace_rows=trace_q_rows, trace_input=x_trace,
                port_input=np.zeros_like(x_port),
            )["volume"]
            native_c = _project_native_components(
                action=action, volume_action=volume_action, comm=mesh_object.comm,
                q_map=q0_map, trace_rows=trace_q_rows, trace_input=np.zeros_like(x_trace),
                port_input=x_port,
            )["C"]
            native_minus_d = _project_native_components(
                action=action, volume_action=volume_action, comm=mesh_object.comm,
                q_map=q0_map, trace_rows=trace_q_rows, trace_input=x_trace,
                port_input=np.zeros_like(x_port),
            )["-D"]
            native_h = _project_native_components(
                action=action, volume_action=volume_action, comm=mesh_object.comm,
                q_map=q0_map, trace_rows=trace_q_rows, trace_input=np.zeros_like(x_trace),
                port_input=x_port,
            )["Hhat"]
            component_errors = {
                "volume": _relative_error(stream_y1["volume"], native_volume),
                "C": _relative_error(stream_y1["C"], native_c),
                "-D": _relative_error(stream_y1["-D"], native_minus_d),
                "Hhat": _relative_error(stream_y1["Hhat"], native_h),
            }
            if any(value["relative_to_component"] > LIMITS["operator"] for value in component_errors.values()):
                raise RuntimeError("reloaded q0 stream component replay failed the native component gates")

            rng4_real = np.random.default_rng(402504)
            rng4_imag = np.random.default_rng(402505)
            x4 = np.asarray(
                rng4_real.standard_normal(q4_saved.shape[1])
                + 1j * rng4_imag.standard_normal(q4_saved.shape[1]), dtype=np.complex128
            ) / np.sqrt(2.0)
            if not np.all(x4 != 0):
                raise RuntimeError("paired q4 witness input must be nonzero")
            stream_y4 = _apply_persisted_consumer(
                input_map=q4_saved, output_map=q4_saved, other_output_map=q0_saved,
                source=x4, surface_stream_path=surface_stream_path,
                volume_stream_path=volume_stream_path, active_lookup=loaded_lookup,
                active_rows=action.condensed.active_rows, local_modes=local_modes,
                selected_indices=selected, local_h=local_h, mode_rows=mode_rows,
                interior_rows=interior_rows,
                trace_q_rows=int(q4_map.shape[1] - len(aliases[1])),
                allocation_gate=allocation_gate,
            )
            native_y4_q0, native_y4_q4, _ = _native_projected_action(
                action=action, volume_action=volume_action, comm=mesh_object.comm,
                input_map=q4_map, output_maps=q_maps, source=x4, trace_rows=trace_q_rows,
            )
            if max(
                _relative_error(stream_y4["total"], native_y4_q4)["relative_to_component"],
                _relative_error(stream_y4["other_total"], native_y4_q0)["relative_to_component"],
            ) > LIMITS["operator"]:
                raise RuntimeError("reloaded q4 paired stream differs from its native two-cell action")
            stream_offdiag_04 = _l2(stream_y1["other_total"]) / max(
                _l2(stream_y1["total"]), np.finfo(float).tiny
            )
            stream_offdiag_40 = _l2(stream_y4["other_total"]) / max(
                _l2(stream_y4["total"]), np.finfo(float).tiny
            )
            if max(stream_offdiag_04, stream_offdiag_40) > LIMITS["operator"]:
                raise RuntimeError("reloaded paired q0/q4 consumer exceeds the off-diagonal leakage gate")

        if reuse_v25_producer and perform_native_validation:
            native_manifest = {
                "schema": "task40extra.review_v26_native_action.v1",
                "status": "PASS_COMPLETE_Q0_NATIVE_CONSUMER",
                "producer_identity_sha256": producer_identity_sha256,
                "saved_replay_manifest_sha256": replay_manifest_sha256,
                "current_identity": dict(current_identity or {}),
                "cases": native_case_records,
                "native_volume_apply_count": int(native_counters["native_volume_apply_count"]),
                "provider_sweep_count": int(native_counters["provider_sweep_count"]),
                "count_provenance": native_count_provenance,
                "elapsed_seconds": native_action_elapsed_seconds,
                "elapsed_seconds_status": native_action_elapsed_seconds_status,
                "elapsed_seconds_scope": "native q0 case1, q0 case2, and q4 pair; includes provider sweeps",
                "saved_stream_reader_telemetry": reader_telemetry,
                "raw_stream_comparison_passed": True,
                "scaled_cross_q_comparison_limit": 1.0e-11,
            }
            native_manifest_path = native_root / "v26_native_action_manifest.json"
            _write_json(native_manifest_path, native_manifest)
            native_manifest["manifest_sha256"] = _file_sha256(native_manifest_path)
            native_manifest["manifest_path"] = str(native_manifest_path)

        consumer_replay_path = root / "v25_selected_q0_stream_replay.npz"
        with consumer_replay_path.open("xb") as stream:
            np.savez(
                stream,
                input_q0_case_1=x1,
                input_q0_case_2=x2,
                stream_q0_output_case_1=stream_y1["total"],
                stream_q0_output_case_2=stream_y2["total"],
                stream_q4_output_from_q0_case_1=stream_y1["other_total"],
                native_q0_output_case_1=native_y1_q0,
                native_q0_output_case_2=native_y2_q0,
                native_q4_output_from_q0_case_1=native_y1_q4,
                input_q4_pair=x4,
                stream_q4_output_case_pair=stream_y4["total"],
                stream_q0_output_from_q4=stream_y4["other_total"],
                native_q0_output_from_q4=native_y4_q0,
                native_q4_output_case_pair=native_y4_q4,
                component_volume_stream=stream_y1["volume"],
                component_C_stream=stream_y1["C"],
                component_minus_D_stream=stream_y1["-D"],
                component_Hhat_stream=stream_y1["Hhat"],
                component_volume_native=native_volume,
                component_C_native=native_c,
                component_minus_D_native=native_minus_d,
                component_Hhat_native=native_h,
            )
            stream.flush()
            os.fsync(stream.fileno())
        saved_paths["complete_consumer_replay"] = consumer_replay_path

        def artifact_reference(path: Path) -> dict[str, str]:
            return _bound_consumer_artifact_reference(
                path,
                output_root=root,
                producer_root=producer_root if reuse_v25_producer else None,
            )

        consumer_stream_manifest = {
            "schema": (
                "task40extra.review_v26_selected_q0_complete_stream.v1"
                if reuse_v25_producer
                else "task40extra.review_v25_selected_q0_complete_stream.v1"
            ),
            "mode_manifest_sha256": mode_sha,
            "ordered_mode_key_sha256": computed_key_sha,
            "q0_alias_count": int(len(aliases[0])),
            "q4_alias_count": int(len(aliases[1])),
            "q0_trace_rows": trace_q_rows,
            "q4_trace_rows": int(q4_map.shape[1] - len(aliases[1])),
            "q0_map": {**artifact_reference(q_map_paths[0]), "sha256": _file_sha256(q_map_paths[0])},
            "q4_map": {**artifact_reference(q_map_paths[1]), "sha256": _file_sha256(q_map_paths[1])},
            "active_map": {**artifact_reference(active_lookup_path), "sha256": _file_sha256(active_lookup_path)},
            "local_H_p": {**artifact_reference(hp_path), "sha256": _file_sha256(hp_path)},
            "surface_functionals": {
                **dict(surface_stream_facts),
                "artifact_reference": artifact_reference(surface_stream_path),
            },
            "shared_volume_classes_and_cell_map": {
                **dict(volume_stream_facts),
                "artifact_reference": artifact_reference(volume_stream_path),
            },
            "per_cell_expanded_volume_coo_written": False,
            "consumer_replay": {
                "reloaded_saved_data": True,
                "surface_integrator_reruns_during_replay": 0,
                "distinct_nonzero_q0_inputs": 2,
                "q0_replay_relative_errors": [stream_error_1, stream_error_2],
                "q0_component_relative_errors": component_errors,
                "q0_to_q4_relative_error": _relative_error(stream_y1["other_total"], native_y1_q4),
                "q4_to_q0_relative_error": _relative_error(stream_y4["other_total"], native_y4_q0),
                "q4_to_q4_relative_error": _relative_error(stream_y4["total"], native_y4_q4),
                **(
                    {
                        "q0_to_q4_scaled_error": cross_04_error,
                        "q4_to_q0_scaled_error": cross_40_error,
                        "cross_q_scale_q0_to_q4": "native q0 diagonal output norm",
                        "cross_q_scale_q4_to_q0": "native q4 diagonal output norm",
                        "scaled_cross_q_error_limit": 1.0e-11,
                        "native_volume_apply_count": native_counters["native_volume_apply_count"],
                        "provider_sweep_count": native_counters["provider_sweep_count"],
                        "native_action_elapsed_seconds": native_action_elapsed_seconds,
                        "native_action_elapsed_seconds_status": native_action_elapsed_seconds_status,
                        "native_count_provenance": native_count_provenance,
                        "source_derived_counts": native_manifest.get("source_derived_counts", {}),
                        "native_action_manifest_sha256": native_manifest["manifest_sha256"],
                    }
                    if reuse_v25_producer
                    else {}
                ),
                "q0_to_q4_leakage_ratio": stream_offdiag_04,
                "q4_to_q0_leakage_ratio": stream_offdiag_40,
                "replay_artifact": {
                    "path": str(consumer_replay_path.relative_to(root)),
                    "bytes": consumer_replay_path.stat().st_size,
                    "sha256": _file_sha256(consumer_replay_path),
                },
                "elapsed_seconds": stream_replay_seconds,
            },
            "complete_data_consumer_passed": True,
            "csr_built": False,
            "factor_or_solve_built": False,
        }
        consumer_manifest_path = root / "v25_selected_q0_complete_stream.json"
        _write_json(consumer_manifest_path, consumer_stream_manifest)
        saved_paths["complete_stream_manifest"] = consumer_manifest_path
        v26_artifact_binding = None
        if reuse_v25_producer:
            v26_artifact_binding = {
                "producer_identity": dict(saved_producer_identity or {}),
                "producer_identity_sha256": producer_identity_sha256,
                "saved_replay_root": str(Path(saved_replay_root).resolve()),
                "saved_replay_manifest_path": str(
                    Path(saved_replay_root).resolve() / "v26_saved_q_replay_manifest.json"
                ),
                "saved_replay_manifest_sha256": replay_manifest_sha256,
                "native_root": str(native_root),
                "native_manifest_path": str(
                    Path(saved_native_manifest_path).resolve()
                    if saved_native_manifest_path is not None
                    else native_root / "v26_native_action_manifest.json"
                ),
                "native_manifest_sha256": str(native_manifest.get("manifest_sha256", "")),
                "native_volume_apply_count": native_counters["native_volume_apply_count"],
                "provider_sweep_count": native_counters["provider_sweep_count"],
                "native_action_elapsed_seconds": native_action_elapsed_seconds,
                "native_action_elapsed_seconds_status": native_action_elapsed_seconds_status,
                "native_count_provenance": native_count_provenance,
                "source_derived_counts": native_manifest.get("source_derived_counts", {}),
                "mode_count_full_reference": len(generated_modes),
                "q0_alias_count": int(len(aliases[0])),
                "q4_alias_count": int(len(aliases[1])),
                "selected_twist_alias_count": int(len(selected)),
            }

        if not build_csr:
            operation = {
                "schema": _SCHEMA,
                "status": "PASS_COMPLETE_Q0_STREAM",
                "classification": "REFERENCE_Q0_COMPLETE_REPLAYABLE_STREAM; Q4_PAIRED_ACTION_ONLY; NO_SOLVE",
                "official_result": False,
                "selected_q": 0,
                "paired_q": 4,
                "pre_fe_resource_gate": pre_fe_resource_gate,
                "selected_twist_index": int(context.twist_index),
                "global_q_indices_in_local_sector": list(context.global_q_indices),
                "mode_inventory": {
                    "mode_count_full_reference": len(generated_modes),
                    "mode_manifest_sha256": mode_sha,
                    "ordered_mode_key_sha256": computed_key_sha,
                    "q0_alias_count_actual": len(aliases[0]),
                    "q4_alias_count_actual": len(aliases[1]),
                    "selected_twist_alias_count_actual": len(selected),
                    "source": "frozen V20 preflight inventory; no mode regeneration",
                },
                "complete_stream": consumer_stream_manifest,
                "v26_artifact_binding": v26_artifact_binding,
                "direct_only_support": {
                    "internal_B_nonzero_count": internal_B_nnz,
                    "internal_D_nonzero_count": internal_D_nnz,
                    "internal_cell_count": int(len(internal_cell_ids)),
                    "passed": internal_direct_only_pass,
                },
                "csr": {"status": "NOT_ATTEMPTED_BY_SELECTED_CONSUMER_STOP"},
                "not_built": {
                    "q0_csr": True, "q4_csr": True, "other_q_csr": True,
                    "factor": True, "ksp": True, "pde": True, "official_R_T_A": True,
                },
                "saved_artifacts": {
                    key: {
                        "path": str(path.relative_to(root)),
                        "bytes": path.stat().st_size,
                        "sha256": _file_sha256(path),
                    }
                    for key, path in saved_paths.items()
                },
                "elapsed_seconds": float(time.perf_counter() - started),
            }
            operation_path = root / "v25_selected_q0_consumer.json"
            _write_json(operation_path, operation)
            saved_paths["operation"] = operation_path
            return operation

        # The selected V17 block is only q0->q0; q4 is applied matrix-free below.
        tile_directory = root / "v25_selected_q0_row_tiles"
        assembly_started = time.perf_counter()
        structure_checkpoint_record: dict[str, Any] | None = None

        def save_structure_checkpoint(
            facts: Mapping[str, Any], row_counts_wide: np.ndarray, wide_offsets: np.ndarray
        ) -> None:
            nonlocal structure_checkpoint_record
            if structure_checkpoint_path is None:
                return
            checkpoint_path = Path(structure_checkpoint_path).resolve()
            if not checkpoint_path.is_relative_to(root):
                raise ValueError(
                    "selected q0 structure checkpoint must stay under its run output directory"
                )
            checkpoint_manifest_path = checkpoint_path.with_suffix(".json")
            allocation_gate(
                "task40_v26_q0_row_structure_checkpoint_persist",
                {
                    "additional_payload_bytes": 0,
                    "workspace_bytes": 0,
                    "disk_payload_bytes": int(
                        row_counts_wide.nbytes + wide_offsets.nbytes + 4096
                    ),
                    "row_count_dtype": row_counts_wide.dtype.str,
                    "wide_offsets_dtype": wide_offsets.dtype.str,
                    "support_route_sha256": facts.get("support_route_sha256"),
                    "future_co_resident_reserve_bytes": 0,
                },
            )
            _save_npz_atomic(
                checkpoint_path,
                row_counts_int64=np.asarray(row_counts_wide, dtype=np.int64),
                wide_offsets_int64=np.asarray(wide_offsets, dtype=np.int64),
            )
            record = {
                **dict(facts),
                "row_counts_sha256": _array_sha256(row_counts_wide),
                "wide_offsets_sha256": _array_sha256(wide_offsets),
                "array_artifact": {
                    "path": str(checkpoint_path.relative_to(root)),
                    "bytes": checkpoint_path.stat().st_size,
                    "sha256": _file_sha256(checkpoint_path),
                },
                "identity": dict(structure_checkpoint_identity or {}),
            }
            _write_json(checkpoint_manifest_path, record)
            saved_paths["preallocation_row_structure"] = checkpoint_path
            saved_paths["preallocation_row_structure_manifest"] = checkpoint_manifest_path
            structure_checkpoint_record = record

        try:
            matrices, assembly_audit = _assemble_bounded_v17_row_tile_q_patterns(
                action,
                q_maps,
                allocation_gate=allocation_gate,
                requested_blocks=((0, 0),),
                disk_backed_directory=tile_directory,
                disk_backed_stem="q0",
                structure_checkpoint=(
                    save_structure_checkpoint
                    if structure_checkpoint_path is not None
                    else None
                ),
            )
        except Exception as error:
            from .task40_v22_operator_probe import _ProbeResourceBlocked

            controlled_reason = None
            controlled_facts: dict[str, Any] = {}
            if isinstance(error, _ProbeResourceBlocked):
                controlled_reason = "LIVE_RESOURCE_ADMISSION_BLOCKED"
                controlled_facts = {"stage": error.stage, **dict(error.facts)}
            elif isinstance(error, V16StagingLimitError):
                controlled_reason = "V17_BOUNDED_STAGING_LIMIT"
                controlled_facts = error.evidence()
            elif isinstance(error, OverflowError) and "PETSc.IntType" in str(error):
                controlled_reason = "PETSC_INDEX_CAPACITY_EXCEEDED"
                controlled_facts = {"stage": "csr_index_width", "message": str(error)}
            elif isinstance(error, OSError) and any(
                marker in str(error)
                for marker in (
                    "full payload plus free-space reserve",
                    "required free-space reserve",
                    "fell below its required free-space reserve",
                )
            ):
                controlled_reason = "DISK_SPACE_ADMISSION_BLOCKED"
                controlled_facts = {"stage": "csr_or_row_tile_spool", "message": str(error)}
            if controlled_reason is None:
                raise
            operation = {
                "schema": _SCHEMA,
                "status": "PASS_COMPLETE_Q0_STREAM_CSR_NOT_BUILT",
                "classification": "COMPLETE_STREAM_PASS; CSR_CONTROLLED_STOP_AFTER_FULL_STRUCTURE_CHECKPOINT",
                "official_result": False,
                "selected_q": 0,
                "paired_q": 4,
                "pre_fe_resource_gate": pre_fe_resource_gate,
                "mode_inventory": {
                    "mode_count_full_reference": len(generated_modes),
                    "mode_manifest_sha256": mode_sha,
                    "ordered_mode_key_sha256": computed_key_sha,
                    "q0_alias_count_actual": int(len(aliases[0])),
                    "q4_alias_count_actual": int(len(aliases[1])),
                    "selected_twist_alias_count_actual": int(len(selected)),
                    "mode_key_source": "frozen V20 preflight inventory; no mode regeneration",
                },
                "mode_manifest_sha256": mode_sha,
                "ordered_mode_key_sha256": computed_key_sha,
                "actual_q0_alias_count": int(len(aliases[0])),
                "actual_q4_alias_count": int(len(aliases[1])),
                "complete_stream": consumer_stream_manifest,
                "csr": {
                    "status": "CONTROLLED_STOP_NOT_BUILT",
                    "controlled_stop_reason": controlled_reason,
                    "controlled_stop_facts": controlled_facts,
                    "failure_type": type(error).__name__,
                    "failure_message": str(error),
                    "attempted_seconds": float(time.perf_counter() - assembly_started),
                },
                "preallocation_row_structure": structure_checkpoint_record,
                "factor_or_solve_built": False,
                "not_built": {
                    "q4_csr": True, "other_q_csr": True, "factor": True,
                    "ksp": True, "pde": True, "official_R_T_A": True,
                },
                "saved_artifacts": {
                    key: {
                        "path": str(path.relative_to(root)),
                        "bytes": path.stat().st_size,
                        "sha256": _file_sha256(path),
                    }
                    for key, path in saved_paths.items() if path.is_file()
                },
                "elapsed_seconds": float(time.perf_counter() - started),
            }
            operation_path = root / "v25_selected_q0_consumer.json"
            _write_json(operation_path, operation)
            saved_paths["operation"] = operation_path
            return operation
        assembly_audit["assembly_total_seconds"] = float(time.perf_counter() - assembly_started)
        matrix = matrices[(0, 0)]
        if not matrix.has_canonical_format or not matrix.has_sorted_indices:
            raise RuntimeError("selected q0 V17 row-tile spool is not canonical sorted CSR")
        if matrix.dtype != np.dtype(np.complex128) or matrix.indices.dtype != np.dtype(PETSc.IntType):
            raise TypeError("selected q0 CSR/spool dtype differs from the qualified ABI")

        # Hash-bound full row domain, row counts, and tile offsets.
        row_counts = np.diff(matrix.indptr).astype(np.int64, copy=False)
        wide_offsets = np.asarray(matrix.indptr, dtype=np.int64)
        row_tile_offsets = []
        tile_rows = int(assembly_audit["pattern_facts_by_block"]["00"]["row_tile_rows"])
        for start in range(0, matrix.shape[0], tile_rows):
            stop = min(start + tile_rows, matrix.shape[0])
            row_tile_offsets.append(
                {"row_start": start, "row_stop": stop,
                 "nnz_start": int(wide_offsets[start]), "nnz_stop": int(wide_offsets[stop])}
            )
        wide_counts_path = root / "v25_selected_q0_row_counts_int64.npy"
        wide_offsets_path = root / "v25_selected_q0_row_offsets_int64.npy"
        _save_npy(wide_counts_path, row_counts)
        _save_npy(wide_offsets_path, wide_offsets)
        saved_paths["row_counts"] = wide_counts_path
        saved_paths["row_offsets"] = wide_offsets_path

        artifact_map = assembly_audit["pattern_facts_by_block"]["00"]["disk_backed_artifacts"]
        tile_paths = {key: Path(value) for key, value in artifact_map.items()}
        for key, path in tile_paths.items():
            saved_paths[f"csr_{key}"] = path
        spool_files = {
            key: {"path": str(path.relative_to(root)), "bytes": path.stat().st_size,
                  "sha256": _file_sha256(path)}
            for key, path in tile_paths.items()
        }
        tile_manifest = {
            "schema": "task40extra.review_v25_selected_q0_row_tile_store.v1",
            "shape": list(matrix.shape),
            "dtype": matrix.dtype.str,
            "index_dtype": matrix.indices.dtype.str,
            "row_tile_rows": tile_rows,
            "row_count": int(matrix.shape[0]),
            "nnz": int(matrix.nnz),
            "row_offsets_sha256": _array_sha256(wide_offsets),
            "row_counts_sha256": _array_sha256(row_counts),
            "tiles": row_tile_offsets,
            "files": spool_files,
            "complete_row_domain": True,
            "complete_column_domain": True,
            "sorted_unique_columns_per_row": bool(matrix.has_canonical_format),
        }
        tile_manifest_path = root / "v25_selected_q0_row_tiles.json"
        _write_json(tile_manifest_path, tile_manifest)
        saved_paths["tile_manifest"] = tile_manifest_path

        # Independently reload the full disk-backed CSR arrays and verify all hashes.
        loaded_indptr = np.load(tile_paths["indptr"], mmap_mode="r", allow_pickle=False)
        loaded_indices = np.load(tile_paths["indices"], mmap_mode="r", allow_pickle=False)
        loaded_data = np.load(tile_paths["data"], mmap_mode="r", allow_pickle=False)
        reload_ok = bool(
            loaded_indptr.shape == (matrix.shape[0] + 1,)
            and loaded_indices.shape == loaded_data.shape == (matrix.nnz,)
            and loaded_indptr.dtype == loaded_indices.dtype == np.dtype(PETSc.IntType)
            and loaded_data.dtype == np.dtype(np.complex128)
            and _array_equal_chunked(loaded_indptr, matrix.indptr)
            and _array_equal_chunked(loaded_indices, matrix.indices)
            and _array_equal_chunked(loaded_data, matrix.data)
        )
        if not reload_ok:
            raise IOError("selected q0 row-tile reload differs from the built complete matrix")
        reloaded_matrix = sparse.csr_matrix(
            (loaded_data, loaded_indices, loaded_indptr), shape=matrix.shape, copy=False
        )
        numeric_nonzero_entries = _count_nonzero_chunked(loaded_data)
        matrix_identity = {
            "shape": list(matrix.shape),
            "nnz": int(matrix.nnz),
            "complex128_value_count": int(matrix.data.size),
            "int32_index_count": int(matrix.indices.size),
            "structural_slots": int(matrix.nnz),
            "numeric_nonzero_entries": numeric_nonzero_entries,
            "exact_zero_slots_retained": int(matrix.nnz - numeric_nonzero_entries),
            "csr_payload_bytes": int(
                matrix.data.nbytes + matrix.indices.nbytes + matrix.indptr.nbytes
            ),
            "csr_array_sha256": {
                "data": _array_sha256(loaded_data),
                "indices": _array_sha256(loaded_indices),
                "indptr": _array_sha256(loaded_indptr),
            },
            "row_counts_int64_sha256": _file_sha256(wide_counts_path),
            "row_offsets_int64_sha256": _file_sha256(wide_offsets_path),
            "complete_q0_shape": list(matrix.shape),
            "complete_row_coverage": int(matrix.shape[0]),
            "complete_column_coverage": int(matrix.shape[1]),
        }

        # Reuse the two inputs and native reference outputs captured from the
        # persisted complete consumer before attempting this optional CSR.
        trace_columns = trace_q_rows
        replay_started = time.perf_counter()
        csr_y1 = np.asarray(reloaded_matrix @ x1, dtype=np.complex128)
        _drop_mmap_pages(loaded_data, 0, loaded_data.nbytes)
        csr_y2 = np.asarray(reloaded_matrix @ x2, dtype=np.complex128)
        _drop_mmap_pages(loaded_data, 0, loaded_data.nbytes)
        replay_seconds = float(time.perf_counter() - replay_started)
        action_error_1 = _relative_error(csr_y1, native_y1_q0)
        action_error_2 = _relative_error(csr_y2, native_y2_q0)
        if max(action_error_1["relative_to_component"], action_error_2["relative_to_component"]) > LIMITS["operator"]:
            raise RuntimeError("selected q0 complete CSR/spool failed two native nonzero action replays")

        # Compare CSR components with the native component witnesses captured
        # before CSR from the persisted consumer.
        x_trace = np.asarray(x1[:trace_columns], dtype=np.complex128)
        x_port = np.asarray(x1[trace_columns:], dtype=np.complex128)
        y_trace = np.asarray(reloaded_matrix @ np.concatenate((x_trace, np.zeros_like(x_port))))
        _drop_mmap_pages(loaded_data, 0, loaded_data.nbytes)
        y_port = np.asarray(reloaded_matrix @ np.concatenate((np.zeros_like(x_trace), x_port)))
        _drop_mmap_pages(loaded_data, 0, loaded_data.nbytes)
        component_errors = {
            "volume": _relative_error(y_trace[:trace_q_rows], native_volume[:trace_q_rows]),
            "C": _relative_error(y_port[:trace_q_rows], native_c[:trace_q_rows]),
            "-D": _relative_error(y_trace[trace_q_rows:], native_minus_d[trace_q_rows:]),
            "Hhat": _relative_error(y_port[trace_q_rows:], native_h[trace_q_rows:]),
        }
        if any(value["relative_to_component"] > LIMITS["operator"] for value in component_errors.values()):
            raise RuntimeError("selected q0 volume/C/-D/Hhat native component projection failed")

        # q4 leakage was measured from this same persisted consumer and the
        # same native action before the optional q0 CSR attempt.
        offdiag_04 = _l2(native_y1_q4) / max(_l2(native_y1_q0), np.finfo(float).tiny)
        offdiag_40 = _l2(native_y4_q0) / max(_l2(native_y4_q4), np.finfo(float).tiny)
        if max(offdiag_04, offdiag_40) > LIMITS["operator"]:
            raise RuntimeError("selected reference q0/q4 native branch leakage exceeds the existing off-diagonal gate")

        # H_p is independently checked before condensation in actual local/global scaling.
        q0_ids = aliases[0]
        q4_ids = aliases[1]
        hp_q0_diagonal = local_h[q0_ids] * np.square(coordinates.scale[q0_ids])
        hp_identity_error = float(np.max(np.abs(hp_q0_diagonal - 1.0), initial=0.0))
        hp_cross_support = int(np.intersect1d(q0_ids, q4_ids, assume_unique=True).size)
        if hp_identity_error > 1.0e-12 or hp_cross_support != 0:
            raise RuntimeError("selected reference original H_p normalization/branch identity failed")

        replay_path = root / "v25_selected_q0_replay.npz"
        replay_temp = replay_path.with_name(replay_path.name + ".tmp")
        with replay_temp.open("xb") as stream:
            np.savez(
                stream,
                input_q0_case_1=x1,
                input_q0_case_2=x2,
                q0_replay_output_case_1=csr_y1,
                q0_replay_output_case_2=csr_y2,
                native_q0_output_case_1=native_y1_q0,
                native_q0_output_case_2=native_y2_q0,
                native_q4_output_from_q0_case_1=native_y1_q4,
                input_q4_pair=x4,
                native_q0_output_from_q4=native_y4_q0,
                native_q4_output_case_pair=native_y4_q4,
                component_volume_native=native_volume,
                component_C_native=native_c,
                component_minus_D_native=native_minus_d,
                component_Hhat_native=native_h,
            )
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(replay_temp, replay_path)
        saved_paths["replay"] = replay_path

        # Try resident CSR only after the complete disk-backed consumer passes.
        csr_payload = int(matrix.data.nbytes + matrix.indices.nbytes + matrix.indptr.nbytes)
        resident_csr = None
        resident_csr_facts: Mapping[str, Any] = {"status": "NOT_ATTEMPTED"}
        if resident_csr_admission is not None:
            resident_csr_facts = dict(
                resident_csr_admission("task40_v25_selected_q0_resident_csr_upgrade", csr_payload)
            )
            if resident_csr_facts.get("passed") is True:
                resident_csr = sparse.csr_matrix(
                    (
                        np.array(loaded_data, dtype=np.complex128, copy=True),
                        np.array(loaded_indices, dtype=PETSc.IntType, copy=True),
                        np.array(loaded_indptr, dtype=PETSc.IntType, copy=True),
                    ),
                    shape=matrix.shape,
                    copy=False,
                )
                if not resident_csr.has_canonical_format:
                    raise RuntimeError("resident selected q0 CSR lost canonical form")
                resident_check = _relative_error(resident_csr @ x1, csr_y1)
                if resident_check["relative_to_component"] != 0.0:
                    raise RuntimeError("resident selected q0 CSR differs from the full row-tile store")
                resident_csr_facts = {**dict(resident_csr_facts), "readback_equal": True}
            else:
                resident_csr_facts = {**dict(resident_csr_facts), "status": "CSR_NOT_BUILT"}

        selected_alias_rows = []
        for local_alias, global_index in enumerate(selected):
            branch = int(branches[local_alias])
            mode = generated_modes[int(global_index)]
            selected_alias_rows.append(
                {
                    "global_mode_index": int(global_index),
                    "mode_key": list(_mode_key(int(global_index), mode)),
                    "global_q": int(context.global_q_indices[branch]),
                    "local_branch": branch,
                    "local_alias_index": local_alias,
                    "global_H_p": float(global_h[int(global_index)]),
                    "local_H_p": float(local_h[local_alias]),
                    "local_over_global_H_p": float(local_h[local_alias] / global_h[int(global_index)]),
                }
            )
        alias_path = root / "v25_selected_q0_alias_inventory.json"
        _write_json(
            alias_path,
            {
                "schema": "task40extra.review_v25_selected_q0_alias_inventory.v1",
                "selection_stages": [
                    {
                        "stage": "1_complete_regular_reference_mode_generation",
                        "mode_count": len(generated_modes),
                        "mode_manifest_sha256": mode_sha,
                        "ordered_mode_key_sha256": computed_key_sha,
                    },
                    {
                        "stage": "2_exact_ny8_bloch_q_assignment",
                        "assignment_source": "build_task40_v10_sector_contexts",
                        "selected_twist_index": int(context.twist_index),
                        "selected_q_indices": list(context.global_q_indices),
                        "q0_alias_count": len(aliases[0]),
                        "paired_q4_alias_count": len(aliases[1]),
                        "all_selected_modes_retained_without_32_or_64_cap": True,
                    },
                ],
                "aliases": selected_alias_rows,
            },
        )
        saved_paths["alias_inventory"] = alias_path

        # Physical/MPC identity that qualifies this reference-only direct-support claim.
        mpc = local_levels["floquets"][6].mpc
        mpc_coefficients, mpc_offsets = mpc.coefficients()
        facet_tags = local_levels["mesh_data"].facet_tags
        cell_tags = local_levels["mesh_data"].cell_tags
        support_row_facts = (
            np.asarray(sorted(support_rows.items()), dtype=np.int64)
            if isinstance(support_rows, Mapping)
            else np.asarray(support_rows, dtype=np.int64)
        )
        selected_keys_payload = json.dumps(
            [mode_keys[int(index)] for index in selected],
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("ascii")
        identity = {
            "regular_reference_physical_model_sha256": physical_model_sha256,
            "regular_reference_mode_manifest_sha256": mode_sha,
            "ordered_mode_key_sha256": computed_key_sha,
            "phase_gauge": BOUNDARY_PLANE,
            "phase_override": [[phase_override[0].real, phase_override[0].imag], [phase_override[1].real, phase_override[1].imag]],
            "reference_global_cell_axes": list(cell_axes),
            "selected_local_cell_axes": [profile.global_cell_axes[0], 2, profile.global_cell_axes[2]],
            "selected_local_cell_count": local_cell_count,
            "regular_reference_identity": str(regular_cfg.geometry_identity),
            "local_reference_identity": str(local_cfg.geometry_identity),
            "ordered_mode_keys_local_sha256": hashlib.sha256(selected_keys_payload).hexdigest(),
            "mpc": {
                "slave_sha256": _array_sha256(np.asarray(mpc.slaves, dtype=np.int64)),
                "master_sha256": _array_sha256(np.asarray(mpc.masters.array, dtype=np.int64)),
                "coefficient_sha256": _array_sha256(np.asarray(mpc_coefficients)),
                "offset_sha256": _array_sha256(np.asarray(mpc_offsets)),
            },
            "materials": {
                "cell_tag_sha256": _array_sha256(np.column_stack((cell_tags.indices, cell_tags.values))),
                "boundary_facet_tag_sha256": _array_sha256(np.column_stack((facet_tags.indices, facet_tags.values))),
            },
            "boundary_support_groups": len(support_groups),
            "boundary_support_rows": _array_sha256(support_row_facts),
        }
        operation = {
            "schema": _SCHEMA,
            "status": "PASS_COMPLETE_Q0_STREAM" if resident_csr is None else "PASS_COMPLETE_Q0_CSR",
            "classification": "REFERENCE_Q0_COMPLETE_CONSUMER; Q4_PAIRED_ACTION_ONLY; NO_SOLVE",
            "official_result": False,
            "selected_q": 0,
            "paired_q": 4,
            "pre_fe_resource_gate": pre_fe_resource_gate,
            "selected_twist_index": int(context.twist_index),
            "global_q_indices_in_local_sector": list(context.global_q_indices),
            "profile": profile.identity(),
            "reference_cell_axes": list(profile.global_cell_axes),
            "selected_local_reference_cell_axes": [profile.global_cell_axes[0], 2, profile.global_cell_axes[2]],
            "selected_local_reference_cell_count": local_cell_count,
            "mode_inventory": {
                "mode_count_full_reference": len(generated_modes),
                "mode_manifest_sha256": mode_sha,
                "source_mode_manifest_identity": source_manifest_identity,
                "ordered_mode_key_sha256": computed_key_sha,
                "q0_alias_count_actual": len(aliases[0]),
                "q4_alias_count_actual": len(aliases[1]),
                "selected_twist_alias_count_actual": len(selected),
                "mode_key_source": "frozen V20 preflight inventory; no mode regeneration",
                "surface_quadrature_degree": int(qdegree),
            },
            "complete_stream": consumer_stream_manifest,
            "v26_artifact_binding": v26_artifact_binding,
            "row_tile_store": tile_manifest,
            "preallocation_row_structure": structure_checkpoint_record,
            "matrix_identity": matrix_identity,
            "row_tile_assembly_audit": assembly_audit,
            "full_projected_data_generation_seconds": float(assembly_audit["assembly_total_seconds"]),
            "row_tile_write_seconds_and_hashing_included_in_generation": True,
            "row_tile_readback": {"passed": reload_ok, "resident_csr_conversion": "memory-mapped SciPy CSR view"},
            "replay": {
                "reload_generation_count": 1,
                "provider_generation_pass_count": int(assembly_audit["numeric_contribution_pass_count"]),
                "provider_generation_count_per_csr_replay": 0,
                "distinct_nonzero_q0_inputs": 2,
                "replay_elapsed_seconds": replay_seconds,
                "case_1_native_relative_error": action_error_1,
                "case_2_native_relative_error": action_error_2,
                "csr_replay_file_sha256": _file_sha256(replay_path),
            },
            "component_native_projection_errors": component_errors,
            "paired_q4_branch": {
                "q0_to_q4_relative": offdiag_04,
                "q4_to_q0_relative": offdiag_40,
                "q4_full_csr_built": False,
                "same_two_cell_native_action": True,
            },
            "original_H_p": {
                "global_H_p_values_sha256": _array_sha256(global_h[selected]),
                "local_H_p_values_sha256": _array_sha256(local_h),
                "local_global_scaling_error": h_scale_error,
                "q0_normalized_H_p_identity_max_abs": hp_identity_error,
                "q0_q4_H_p_alias_overlap": hp_cross_support,
                "expected_local_over_global_ratio": 2.0 / float(len(global_axes["y"]) - 1),
            },
            "direct_only_support": {
                "selected_q0_q4_actual_aliases_only": True,
                "internal_cell_count": int(len(internal_cell_ids)),
                "internal_B_nonzero_count": internal_B_nnz,
                "internal_minus_D_nonzero_count": internal_D_nnz,
                "internal_port_reference_count": internal_port_references,
                "passed": internal_direct_only_pass,
                "identity_binding": identity,
            },
            "csr_upgrade": {
                **dict(resident_csr_facts),
                "resident_csr_built": resident_csr is not None,
                "disk_backed_complete_q0_row_tiles_remain_authoritative": True,
            },
            "not_built": {
                "q4_csr": True,
                "other_q_csr": True,
                "factor": True,
                "ksp": True,
                "pde": True,
                "official_R_T_A": True,
            },
            "saved_artifacts": {
                key: {"path": str(path.relative_to(root)), "bytes": path.stat().st_size, "sha256": _file_sha256(path)}
                for key, path in saved_paths.items()
            },
            "elapsed_seconds": float(time.perf_counter() - started),
        }
        required_pass = bool(
            reload_ok
            and internal_direct_only_pass
            and max(action_error_1["relative_to_component"], action_error_2["relative_to_component"]) <= LIMITS["operator"]
            and max(value["relative_to_component"] for value in component_errors.values()) <= LIMITS["operator"]
            and max(offdiag_04, offdiag_40) <= LIMITS["operator"]
            and h_scale_error["relative_to_component"] <= 1.0e-12
            and hp_identity_error <= 1.0e-12
        )
        operation["status"] = (
            "PASS_COMPLETE_Q0_CSR" if tile_manifest.get("complete_row_domain") is True
            and tile_manifest.get("complete_column_domain") is True and required_pass
            else "PASS_COMPLETE_Q0_STREAM" if required_pass
            else "FAILED_SELECTED_Q0_GATES"
        )
        operation["resident_csr_built"] = resident_csr is not None
        operation["solve_ready"] = False
        operation["full_selected_q0_consumer_passed"] = required_pass
        operation_path = root / "v25_selected_q0_consumer.json"
        _write_json(operation_path, operation)
        saved_paths["operation"] = operation_path
        return operation
    finally:
        if action is not None:
            action.destroy()
        if condensed_system is not None:
            condensed_system.destroy()
        if volume_action is not None:
            volume_action.destroy()
        if transform_bank is not None:
            transform_bank.close()
        surface_assemblers = None
        local_levels = None
        direct_provider = None
        local_entities = None
        trace = None
        coordinates = None
        q_maps = None
        gc.collect()
