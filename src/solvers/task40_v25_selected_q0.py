"""Selected regular-reference q0 build-only consumer for Task40 V25.

The route uses the frozen preflight mode inventory, a volume-only FFCx action,
and the production one-mode surface functional stream. It never constructs
the full carrier or an all-q reference operator.
"""

from __future__ import annotations

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


def _advise_file_drop(stream: Any, start: int, length: int) -> None:
    if length <= 0 or not hasattr(os, "posix_fadvise"):
        return
    option = getattr(os, "POSIX_FADV_DONTNEED", None)
    if option is not None:
        try:
            page = os.sysconf("SC_PAGE_SIZE")
            begin = start - start % page
            end = ((start + length + page - 1) // page) * page
            os.posix_fadvise(stream.fileno(), begin, end - begin, option)
        except (OSError, ValueError, TypeError):
            pass


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
):
    """Replay one original selected port functional from the framed raw stream."""
    with path.open("rb") as stream:
        for port, global_index_value in enumerate(selected_indices):
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
            for rows_index, values_index in ((0, 1), (2, 3)):
                rows = arrays[rows_index].astype(np.int64, copy=False)
                values = arrays[values_index]
                positions = np.searchsorted(interior_rows, rows)
                internal = positions < len(interior_rows)
                candidates = np.flatnonzero(internal)
                internal[candidates] = interior_rows[positions[candidates]] == rows[candidates]
                # Exact-zero interior payloads remain in the authoritative
                # spool; omitting them from the numeric direct view is lossless.
                keep = ~internal | (values != 0.0)
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
    expected_disk_bytes = len(b"TASK40V25Q0VOLUME\0") + 8 + 8 * len(class_matrices) + sum(
        16 + int(cell.active_ids.nbytes + cell.expansion.indptr.nbytes
                 + cell.expansion.indices.nbytes + cell.expansion.data.nbytes)
        for cell in action._cells
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


def _apply_persisted_volume_stream(
    path: Path,
    active: np.ndarray,
    *,
    active_rows: int,
    allocation_gate: Callable,
) -> np.ndarray:
    """Apply the saved shared-class Schur owner without consulting live cells."""
    with path.open("rb") as stream:
        if stream.read(len(b"TASK40V25Q0VOLUME\0")) != b"TASK40V25Q0VOLUME\0":
            raise IOError("saved q0 volume stream has an unknown header")
        class_count, cell_count = struct.unpack("<II", stream.read(8))
        classes = []
        class_bytes = 0
        for _ in range(class_count):
            header = stream.read(8)
            if len(header) != 8:
                raise IOError("saved q0 volume stream ended inside class metadata")
            nrow, ncol = struct.unpack("<II", header)
            count = int(nrow) * int(ncol)
            class_bytes += count * np.dtype(np.complex128).itemsize
            if len(classes) == 0:
                allocation_gate("task40_v25_q0_volume_stream_reload", {
                    "matrix_payload_bytes": class_bytes,
                    "workspace_bytes": int(active.nbytes + active_rows * 16),
                    "disk_backed_source_bytes": path.stat().st_size,
                    "unique_classes_loaded_once": True,
                })
            values = np.fromfile(stream, dtype="<c16", count=count)
            if values.size != count:
                raise IOError("saved q0 volume stream has a truncated class matrix")
            matrix = values.reshape((int(nrow), int(ncol)))
            if not np.isfinite(matrix).all():
                raise ValueError("saved q0 volume class matrix contains non-finite values")
            classes.append(matrix)
        result = np.zeros(active_rows, dtype=np.complex128)
        for _ in range(cell_count):
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
            expansion = sparse.csr_matrix(
                (values, indices, indptr), shape=(int(ntrace), int(nactive)), copy=False
            )
            local_trace = expansion @ active[active_ids]
            local_result = classes[int(class_id)] @ local_trace
            np.add.at(result, active_ids, expansion.conjugate().T @ local_result)
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
) -> dict[str, np.ndarray]:
    """Reload and apply all persisted volume/port data in selected q coordinates."""
    reduced_input = np.asarray(input_map @ source, dtype=np.complex128).reshape(-1)
    active = reduced_input[:active_rows]
    ports = reduced_input[active_rows:]
    if len(ports) != len(local_modes):
        raise ValueError("persisted q map port width differs from the complete alias inventory")
    volume_trace = _apply_persisted_volume_stream(
        volume_stream_path, active, active_rows=active_rows, allocation_gate=allocation_gate
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


def _relative_error(actual: Any, expected: Any) -> dict[str, float]:
    left = np.asarray(actual, dtype=np.complex128).reshape(-1)
    right = np.asarray(expected, dtype=np.complex128).reshape(-1)
    if left.shape != right.shape:
        raise ValueError("selected-q0 projected vectors have different shapes")
    difference = left - right
    absolute = _l2(difference)
    scale = max(_l2(left), _l2(right), np.finfo(float).tiny)
    return {"absolute": absolute, "relative_to_component": absolute / scale}


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


def _native_volume_apply(volume_action: Any, full_field: np.ndarray, comm: Any) -> np.ndarray:
    from petsc4py import PETSc

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
    native_volume = _native_volume_apply(volume_action, field_trace, comm)
    volume_reduced = action.reduce_rhs(native_volume, rhs_is_mpc_dual=True)
    outputs["volume"] = np.asarray(volume_reduced, dtype=np.complex128).reshape(-1)

    # C block: native volume callback on the recovered port field plus raw B.
    reduced_port, field_port = field_for(zero_trace, port_input)
    if reduced_port.shape != (local_trace_rows + local_port_rows,):
        raise ValueError("native q map did not produce the complete local reduced vector")
    native_port_volume = _native_volume_apply(volume_action, field_port, comm)
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
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
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
    )
    native_reduced = sum(
        components.values(),
        np.zeros(int(action.reduced_size), dtype=np.complex128),
    )
    out0 = np.asarray(output_maps[0].conjugate().T @ native_reduced).reshape(-1)
    out1 = np.asarray(output_maps[1].conjugate().T @ native_reduced).reshape(-1)
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
    )
    from .task40_v10_p6_periodic_profile import TASK40_V20_P6_TARGET_ORIGINAL_NY8_PROFILE

    if not callable(allocation_gate):
        raise TypeError("selected q0 consumer requires the live whole-tree allocation gate")
    root = Path(output_directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
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
        geometry_identity="task40extra_v25.selected_q0_regular_reference",
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
        case_name=f"{regular_cfg.case_name}_v25_q0_twist0",
        period_y=float(context.local_axes["y"][-1] - context.local_axes["y"][0]),
        grating_width_y=float(context.local_axes["y"][-1] - context.local_axes["y"][0]),
        mesh_axis_cell_counts=(profile.global_cell_axes[0], 2, profile.global_cell_axes[2]),
        mesh_axis_y_values=tuple(context.local_axes["y"]),
        mesh_plan_id="task40extra_v25.selected_q0_twist0_local_reference",
        mesh_plan_sha256=None,
        geometry_identity="task40extra_v25.selected_q0_twist0_regular_reference",
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
    surface_stream_path = root / "v25_selected_q0_surface_functionals.bin"
    surface_stream_facts: dict[str, Any] = {}
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

        interior_parts = [
            np.asarray(cell.interior_original_dofs, dtype=np.int64).reshape(-1)
            for cell in condensed_system.cell_recovery_maps
            if len(cell.interior_original_dofs)
        ]
        interior_rows = np.concatenate(interior_parts) if interior_parts else np.empty(0, dtype=np.int64)
        interior_rows.sort()
        if interior_rows.size > 1 and np.any(interior_rows[1:] == interior_rows[:-1]):
            raise ValueError("selected-q0 interior row ownership is not unique")
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
        direct_provider = P6GlobalDirectCarrierProvider(
            lambda: _iter_saved_surface_functionals(
                surface_stream_path,
                selected_indices=selected,
                local_modes=local_modes,
                local_h=local_h,
                mode_rows=mode_rows,
                interior_rows=interior_rows,
            ),
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
            global_h=global_h,
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

        if _file_sha256(surface_stream_path) != surface_stream_facts["sha256"]:
            raise IOError("saved raw production surface stream failed its immediate SHA readback")
        if _file_sha256(volume_stream_path) != volume_stream_facts["sha256"]:
            raise IOError("saved shared-class volume stream failed its immediate SHA readback")
        loaded_lookup = np.load(active_lookup_path, mmap_mode="r", allow_pickle=False)
        if loaded_lookup.shape != (action.condensed.full_rows,) or loaded_lookup.dtype != np.dtype(np.int32):
            raise IOError("reloaded original-to-active mapping has an invalid shape or dtype")
        q0_saved, q4_saved = tuple(reloaded_q_maps)

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
            allocation_gate=allocation_gate,
        )
        stream_y2 = _apply_persisted_consumer(
            input_map=q0_saved, output_map=q0_saved, other_output_map=q4_saved,
            source=x2, surface_stream_path=surface_stream_path,
            volume_stream_path=volume_stream_path, active_lookup=loaded_lookup,
            active_rows=action.condensed.active_rows, local_modes=local_modes,
            selected_indices=selected, local_h=local_h, mode_rows=mode_rows,
            interior_rows=interior_rows, trace_q_rows=trace_q_rows,
            allocation_gate=allocation_gate,
        )
        stream_replay_seconds = float(time.perf_counter() - stream_replay_started)
        native_y1_q0, native_y1_q4, _ = _native_projected_action(
            action=action, volume_action=volume_action, comm=mesh_object.comm,
            input_map=q0_map, output_maps=q_maps, source=x1, trace_rows=trace_q_rows,
        )
        native_y2_q0, _native_y2_q4, _ = _native_projected_action(
            action=action, volume_action=volume_action, comm=mesh_object.comm,
            input_map=q0_map, output_maps=q_maps, source=x2, trace_rows=trace_q_rows,
        )
        stream_error_1 = _relative_error(stream_y1["total"], native_y1_q0)
        stream_error_2 = _relative_error(stream_y2["total"], native_y2_q0)
        if max(stream_error_1["relative_to_component"], stream_error_2["relative_to_component"]) > LIMITS["operator"]:
            raise RuntimeError("reloaded complete q0 stream failed two distinct native action replays")

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

        consumer_stream_manifest = {
            "schema": "task40extra.review_v25_selected_q0_complete_stream.v1",
            "mode_manifest_sha256": mode_sha,
            "ordered_mode_key_sha256": computed_key_sha,
            "q0_alias_count": int(len(aliases[0])),
            "q4_alias_count": int(len(aliases[1])),
            "q0_trace_rows": trace_q_rows,
            "q4_trace_rows": int(q4_map.shape[1] - len(aliases[1])),
            "q0_map": {"path": str(q_map_paths[0].relative_to(root)), "sha256": _file_sha256(q_map_paths[0])},
            "q4_map": {"path": str(q_map_paths[1].relative_to(root)), "sha256": _file_sha256(q_map_paths[1])},
            "active_map": {"path": str(active_lookup_path.relative_to(root)), "sha256": _file_sha256(active_lookup_path)},
            "local_H_p": {"path": str(hp_path.relative_to(root)), "sha256": _file_sha256(hp_path)},
            "surface_functionals": surface_stream_facts,
            "shared_volume_classes_and_cell_map": volume_stream_facts,
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
        try:
            matrices, assembly_audit = _assemble_bounded_v17_row_tile_q_patterns(
                action,
                q_maps,
                allocation_gate=allocation_gate,
                requested_blocks=((0, 0),),
                disk_backed_directory=tile_directory,
                disk_backed_stem="q0",
            )
        except Exception as error:
            operation = {
                "schema": _SCHEMA,
                "status": "PASS_COMPLETE_Q0_STREAM_CSR_NOT_BUILT",
                "classification": "COMPLETE_STREAM_PASS; CONDITIONAL_CSR_UPGRADE_NOT_BUILT",
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
                    "status": "NOT_BUILT",
                    "failure_type": type(error).__name__,
                    "failure_message": str(error),
                    "attempted_seconds": float(time.perf_counter() - assembly_started),
                },
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
            "volume": _relative_error(y_trace[:trace_q_rows], volume_native[:trace_q_rows]),
            "C": _relative_error(y_port[:trace_q_rows], c_native[:trace_q_rows]),
            "-D": _relative_error(y_trace[trace_q_rows:], d_native[trace_q_rows:]),
            "Hhat": _relative_error(y_port[trace_q_rows:], h_native[trace_q_rows:]),
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
                component_volume_native=volume_native,
                component_C_native=c_native,
                component_minus_D_native=d_native,
                component_Hhat_native=h_native,
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
            "row_tile_store": tile_manifest,
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
