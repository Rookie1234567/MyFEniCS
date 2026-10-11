"""FE-free q0 contribution view over the hash-bound V25 saved streams.

This adapter exposes the same layout/contribution seam consumed by the V17
row-tile CSR builder. It reads the already-produced volume Schur classes,
original-to-active lookup, processed surface functionals, and original H_p;
it never constructs a mesh, FE space, MPC object, form, or native action.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import struct
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Callable, Mapping

import numpy as np
from scipy import sparse

from .task40_v25_selected_q0 import (
    _CELL_STREAM_HEADER,
    _SURFACE_STREAM_HEADER,
    _advise_file_drop,
    _scan_persisted_volume_stream,
)


_VOLUME_MAGIC = b"TASK40V25Q0VOLUME\0"
_VOLUME_HEADER = struct.Struct("<II")
_VOLUME_CLASS_HEADER = struct.Struct("<II")


def _read_saved_npy_header(stream: Any) -> dict[str, Any]:
    """Read a NumPy header without materializing the array payload."""
    version = np.lib.format.read_magic(stream)
    if version not in {(1, 0), (2, 0), (3, 0)}:
        raise ValueError(f"unsupported saved q0 NPY format version: {version}")
    shape, fortran_order, dtype = np.lib.format._read_array_header(stream, version)
    dtype = np.dtype(dtype)
    if dtype.hasobject or any(int(dimension) < 0 for dimension in shape):
        raise ValueError("saved q0 NPY header contains an unsafe dtype or shape")
    return {
        "shape": [int(dimension) for dimension in shape],
        "dtype": dtype.str,
        "fortran_order": bool(fortran_order),
    }


def _read_saved_npz_headers(
    path: str | Path,
    *,
    expected_members: set[str],
    small_value_members: set[str] | frozenset[str] = frozenset(),
) -> dict[str, dict[str, Any]]:
    """Read NPZ member headers and, optionally, tiny metadata arrays only."""
    result: dict[str, dict[str, Any]] = {}
    with zipfile.ZipFile(path) as archive:
        members = [item.filename for item in archive.infolist() if not item.is_dir()]
        if len(members) != len(set(members)) or set(members) != expected_members:
            raise ValueError(
                "saved q0 NPZ member inventory differs from its frozen contract: "
                f"{Path(path).name} has {sorted(members)}"
            )
        for member_name in sorted(expected_members):
            with archive.open(member_name) as stream:
                header = _read_saved_npy_header(stream)
                if member_name in small_value_members:
                    item_count = math.prod(header["shape"]) if header["shape"] else 1
                    dtype = np.dtype(header["dtype"])
                    byte_count = item_count * int(dtype.itemsize)
                    if item_count > 2 or dtype.hasobject or byte_count > 16:
                        raise ValueError(
                            f"saved q0 NPZ metadata member is not a tiny fixed-width array: {member_name}"
                        )
                    payload = stream.read(byte_count)
                    if len(payload) != byte_count:
                        raise ValueError(f"saved q0 NPZ metadata member is truncated: {member_name}")
                    if dtype.kind == "S":
                        header["values"] = payload.decode("ascii").rstrip("\0")
                    elif dtype.kind == "U":
                        header["values"] = np.frombuffer(payload, dtype=dtype).tolist()
                    else:
                        header["values"] = [
                            int(value)
                            for value in np.frombuffer(payload, dtype=dtype).reshape(-1)
                        ]
                result[member_name] = header
    return result


def inspect_saved_q0_input_headers(
    *,
    q0_map_path: str | Path,
    active_lookup_path: str | Path,
    local_h_path: str | Path,
    row_witness_path: str | Path,
    profile: Any,
    q_index: int,
) -> dict[str, Any]:
    """Validate the complete saved q0 input inventory from NPY/NPZ headers.

    The H diagonal belongs to the q-sector aliases (for q0, q0 plus q4),
    while the profile's full mode inventory remains all eight q blocks.
    Only the small CSR ``shape.npy`` and ``format.npy`` payloads are read;
    sparse values, lookup values, H values, and row-witness arrays stay unread.
    """
    q_port_counts = tuple(int(value) for value in profile.q_port_counts)
    sector_port_counts = tuple(int(value) for value in profile.sector_port_counts)
    q_count = int(profile.q_count)
    replication_count = int(profile.replication_count)
    local_y_cells = int(profile.local_y_cells)
    q_index = int(q_index)
    if (
        q_count != len(q_port_counts)
        or replication_count <= 0
        or local_y_cells <= 0
        or len(sector_port_counts) != replication_count
        or len(q_port_counts) != local_y_cells * replication_count
        or not 0 <= q_index < q_count
    ):
        raise ValueError("saved q0 dimension check received an inconsistent frozen profile or q index")

    sector_index = q_index % replication_count
    alias_q_indices = tuple(
        sector_index + local_y_branch * replication_count
        for local_y_branch in range(local_y_cells)
    )
    sector_alias_count = sum(q_port_counts[index] for index in alias_q_indices)
    if sector_port_counts[sector_index] != sector_alias_count:
        raise ValueError("frozen sector port inventory disagrees with its q-alias counts")
    expected_map_shape = (
        int(profile.local_trace_rows) + sector_alias_count,
        int(profile.trace_rows_per_q) + q_port_counts[q_index],
    )
    expected_lookup_shape = (int(profile.local_storage_rows),)
    expected_h_shape = (sector_alias_count,)
    expected_row_count_shape = (expected_map_shape[1],)
    expected_offset_shape = (expected_map_shape[1] + 1,)

    map_headers = _read_saved_npz_headers(
        q0_map_path,
        expected_members={"data.npy", "indices.npy", "indptr.npy", "shape.npy", "format.npy"},
        small_value_members={"shape.npy", "format.npy"},
    )
    with Path(active_lookup_path).open("rb") as stream:
        lookup_header = _read_saved_npy_header(stream)
    with Path(local_h_path).open("rb") as stream:
        local_h_header = _read_saved_npy_header(stream)
    row_headers = _read_saved_npz_headers(
        row_witness_path,
        expected_members={"row_counts_int64.npy", "wide_offsets_int64.npy"},
    )

    expected_dtypes = {
        "complex128": np.dtype(np.complex128).str,
        "int32": np.dtype(np.int32).str,
        "int64": np.dtype(np.int64).str,
    }
    mismatches: dict[str, dict[str, Any]] = {}

    def require(name: str, actual: Any, expected: Any) -> None:
        if actual != expected:
            mismatches[name] = {"actual": actual, "expected": expected}

    require("q0_map.shape", map_headers["shape.npy"].get("values"), list(expected_map_shape))
    require("q0_map.shape_header.shape", map_headers["shape.npy"]["shape"], [2])
    require("q0_map.shape_header.dtype", map_headers["shape.npy"]["dtype"], expected_dtypes["int64"])
    require("q0_map.format", map_headers["format.npy"].get("values"), "csr")
    require("q0_map.format_header.shape", map_headers["format.npy"]["shape"], [])
    require("q0_map.format_header.dtype", map_headers["format.npy"]["dtype"], np.dtype("S3").str)
    require("q0_map.data.dtype", map_headers["data.npy"]["dtype"], expected_dtypes["complex128"])
    require("q0_map.indices.dtype", map_headers["indices.npy"]["dtype"], expected_dtypes["int32"])
    require("q0_map.indptr.dtype", map_headers["indptr.npy"]["dtype"], expected_dtypes["int32"])
    require("q0_map.indptr.shape", map_headers["indptr.npy"]["shape"], [expected_map_shape[0] + 1])
    require("q0_map.indices.shape", map_headers["indices.npy"]["shape"], map_headers["data.npy"]["shape"])
    require("active_lookup.shape", lookup_header["shape"], list(expected_lookup_shape))
    require("active_lookup.dtype", lookup_header["dtype"], expected_dtypes["int32"])
    require("local_H.shape", local_h_header["shape"], list(expected_h_shape))
    require("local_H.dtype", local_h_header["dtype"], expected_dtypes["complex128"])
    for label, header in (
        *((f"q0_map.{name}", value) for name, value in map_headers.items()),
        ("active_lookup", lookup_header),
        ("local_H", local_h_header),
        ("row_counts_int64", row_headers["row_counts_int64.npy"]),
        ("wide_offsets_int64", row_headers["wide_offsets_int64.npy"]),
    ):
        require(f"{label}.fortran_order", header["fortran_order"], False)
    require(
        "row_counts_int64.shape",
        row_headers["row_counts_int64.npy"]["shape"],
        list(expected_row_count_shape),
    )
    require(
        "row_counts_int64.dtype",
        row_headers["row_counts_int64.npy"]["dtype"],
        expected_dtypes["int64"],
    )
    require(
        "wide_offsets_int64.shape",
        row_headers["wide_offsets_int64.npy"]["shape"],
        list(expected_offset_shape),
    )
    require(
        "wide_offsets_int64.dtype",
        row_headers["wide_offsets_int64.npy"]["dtype"],
        expected_dtypes["int64"],
    )
    if mismatches:
        raise ValueError(
            "V27 saved q0 NPY/NPZ header inventory mismatch: "
            + json.dumps(mismatches, sort_keys=True)
        )

    return {
        "schema": "task40extra.review_v27_saved_q0_header_inventory.v1",
        "q_index": q_index,
        "sector_index": sector_index,
        "sector_alias_q_indices": list(alias_q_indices),
        "full_profile_mode_count": sum(q_port_counts),
        "sector_local_alias_count": sector_alias_count,
        "expected_shapes": {
            "q0_map": list(expected_map_shape),
            "active_lookup": list(expected_lookup_shape),
            "local_H": list(expected_h_shape),
            "row_counts_int64": list(expected_row_count_shape),
            "wide_offsets_int64": list(expected_offset_shape),
        },
        "headers": {
            "q0_map": map_headers,
            "active_lookup": lookup_header,
            "local_H": local_h_header,
            "row_counts_int64": row_headers["row_counts_int64.npy"],
            "wide_offsets_int64": row_headers["wide_offsets_int64.npy"],
        },
        "payload_arrays_materialized": False,
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        position = 0
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
            _advise_file_drop(stream, position, len(chunk))
            position += len(chunk)
    return digest.hexdigest()


def _sha256_array(array: np.ndarray, *, chunk_bytes: int = 4 * 1024 * 1024) -> str:
    array = np.asarray(array)
    if not array.flags.c_contiguous:
        raise ValueError("saved q0 source identity arrays must be C-contiguous")
    raw = memoryview(array).cast("B")
    digest = hashlib.sha256()
    for start in range(0, len(raw), chunk_bytes):
        digest.update(raw[start : start + chunk_bytes])
    return digest.hexdigest()


def _atomic_json(path: Path, facts: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent,
        prefix=f".{path.name}.", suffix=".tmp", delete=False,
    ) as stream:
        temporary = Path(stream.name)
        json.dump(facts, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _atomic_structure_npz(path: Path, row_counts: np.ndarray, offsets: np.ndarray) -> None:
    with tempfile.NamedTemporaryFile(
        dir=path.parent, prefix=f".{path.stem}.", suffix=".npz", delete=False
    ) as stream:
        temporary = Path(stream.name)
    try:
        np.savez_compressed(
            temporary,
            row_counts=np.asarray(row_counts, dtype=np.int64),
            offsets=np.asarray(offsets, dtype=np.int64),
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _expected_q0_structure(
    adapter: "SavedQ0ContributionAdapter",
    row_counts: np.ndarray,
    offsets: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, int, int]:
    row_counts = np.asarray(row_counts)
    offsets = np.asarray(offsets)
    q0_rows = int(adapter.q0_map.shape[1])
    if (
        row_counts.shape != (q0_rows,)
        or offsets.shape != (q0_rows + 1,)
        or row_counts.dtype != np.dtype(np.int64)
        or offsets.dtype != np.dtype(np.int64)
        or int(offsets[0]) != 0
        or int(offsets[-1]) < 0
        or np.any(row_counts < 0)
        or np.any(offsets[1:] < offsets[:-1])
        or not np.array_equal(np.diff(offsets), row_counts)
    ):
        raise ValueError("saved V26 q0 row-count/offset witness is malformed")
    index_bytes = int(adapter.q0_map.indices.dtype.itemsize)
    csr_payload = int((q0_rows + 1) * index_bytes + offsets[-1] * (index_bytes + 16))
    return row_counts, offsets, int(offsets[-1]), csr_payload


def preflight_saved_q0_csr(
    adapter: "SavedQ0ContributionAdapter",
    *,
    expected_row_counts: np.ndarray,
    expected_offsets: np.ndarray,
    allocation_gate: Callable[[str, Mapping[str, Any]], Any],
) -> dict[str, int]:
    """Admit the complete saved-only CSR and all known concurrent owners up front."""
    from .task40_v10_p6_yorbit import V16_Q_STAGING_BUDGET_BYTES

    if not callable(allocation_gate):
        raise ValueError("saved q0 CSR preflight requires the live allocation gate")
    row_counts, offsets, expected_nnz, csr_payload = _expected_q0_structure(
        adapter, expected_row_counts, expected_offsets
    )
    owners = adapter.owner_reserve_facts()
    additional_payload = (
        csr_payload + owners["shared_schur_class_payload_bytes"]
    )
    workspace = (
        int(V16_Q_STAGING_BUDGET_BYTES)
        + owners["maximum_cell_mapping_payload_bytes"]
        + owners["maximum_cell_contribution_payload_bytes"]
        + owners["maximum_cell_expansion_dense_workspace_bytes"]
        + owners["maximum_surface_frame_working_bytes"]
        + owners["q0_input_vectors_bytes"]
        + owners["saved_native_q0_outputs_bytes"]
        + owners["component_validation_outputs_bytes"]
        + owners["reduced_input_vectors_bytes"]
        + 4 * 1024 * 1024
    )
    facts = {
        "additional_payload_bytes": int(additional_payload),
        "workspace_bytes": int(workspace),
        "complete_q0_csr_payload_bytes": int(csr_payload),
        "expected_stored_structural_slots": int(expected_nnz),
        "q0_shape": [int(adapter.q0_map.shape[1])] * 2,
        "shared_schur_class_payload_bytes": owners["shared_schur_class_payload_bytes"],
        "maximum_surface_frame_working_bytes": owners["maximum_surface_frame_working_bytes"],
        "maximum_cell_mapping_payload_bytes": owners["maximum_cell_mapping_payload_bytes"],
        "maximum_cell_contribution_payload_bytes": owners[
            "maximum_cell_contribution_payload_bytes"
        ],
        "maximum_cell_expansion_dense_workspace_bytes": owners[
            "maximum_cell_expansion_dense_workspace_bytes"
        ],
        "q0_input_vectors_bytes": owners["q0_input_vectors_bytes"],
        "saved_native_q0_outputs_bytes": owners["saved_native_q0_outputs_bytes"],
        "component_validation_outputs_bytes": owners[
            "component_validation_outputs_bytes"
        ],
        "reduced_input_vectors_bytes": owners["reduced_input_vectors_bytes"],
        "v17_staging_budget_bytes": int(V16_Q_STAGING_BUDGET_BYTES),
        "hash_buffer_bytes": 4 * 1024 * 1024,
        "q_map_count": 1,
        "q_map_branch": 0,
        "saved_only_no_fe_or_native_rebuild": True,
        "disk_backed_csr_pages_counted_as_memory": True,
        "all_known_future_owner_reserves_included": True,
    }
    allocation_gate("task40_v27_saved_q0_full_csr_preflight", facts)
    return {
        "expected_nnz": int(expected_nnz),
        "csr_payload_bytes": int(csr_payload),
        "additional_payload_bytes": int(additional_payload),
        "workspace_bytes": int(workspace),
        "row_count_sum": int(row_counts.sum(dtype=np.int64)),
        "offset_terminal": int(offsets[-1]),
    }


def _read_exact(stream: Any, count: int, what: str) -> bytes:
    value = stream.read(int(count))
    if len(value) != int(count):
        raise IOError(f"saved q0 {what} is truncated")
    return value


class SavedQ0ContributionAdapter:
    """One q0-only view of saved contributions in reduced-action coordinates."""

    def __init__(
        self,
        *,
        volume_stream_path: str | Path,
        surface_stream_path: str | Path,
        active_lookup: np.ndarray,
        local_h: np.ndarray,
        q0_map: sparse.csr_matrix,
        active_rows: int,
        q0_trace_rows: int,
        q0_port_rows: int,
        allocation_gate: Callable[[str, Mapping[str, Any]], Any] | None = None,
        expected_cell_count: int | None = None,
        expected_class_count: int | None = None,
        reader_telemetry: dict[str, Any] | None = None,
    ) -> None:
        self.volume_stream_path = Path(volume_stream_path).resolve()
        self.surface_stream_path = Path(surface_stream_path).resolve()
        self.active_lookup = np.asarray(active_lookup)
        self.local_h = np.asarray(local_h)
        self.q0_map = q0_map
        self.active_rows = int(active_rows)
        self.q0_trace_rows = int(q0_trace_rows)
        self.q0_port_rows = int(q0_port_rows)
        self.reader_telemetry = reader_telemetry
        self._source_array_bindings_cache: dict[str, Any] | None = None
        self.allocation_gate = allocation_gate
        self.port_count = int(self.local_h.size)
        self.reduced_rows = self.active_rows + self.port_count
        self.volume_layout = _scan_persisted_volume_stream(self.volume_stream_path)
        self.maximum_surface_b_count = 0
        self.maximum_surface_d_count = 0
        self.maximum_surface_frame_entries = 0
        self.mode_indices = self._scan_surface_headers()
        self.expected_cell_count = expected_cell_count
        self.expected_class_count = expected_class_count
        self._validate_owner()

    def _validate_owner(self) -> None:
        if self.active_rows <= 0 or self.q0_trace_rows <= 0 or self.port_count <= 0:
            raise ValueError("saved q0 dimensions must be positive")
        int32_max = int(np.iinfo(np.int32).max)
        if self.reduced_rows > int32_max or self.active_rows > int32_max:
            raise OverflowError("saved q0 reduced rows exceed the qualified int32 index range")
        if (
            self.active_lookup.ndim != 1
            or self.active_lookup.dtype != np.dtype(np.int32)
            or np.any(self.active_lookup < -1)
            or int(self.active_lookup.max(initial=-1)) >= self.active_rows
        ):
            raise ValueError("saved q0 original-to-active lookup has invalid shape or indices")
        if (
            self.local_h.ndim != 1
            or self.local_h.dtype != np.dtype(np.complex128)
            or not np.isfinite(self.local_h).all()
            or np.any(self.local_h == 0.0)
        ):
            raise ValueError("saved q0 H_p must be a finite nonzero complex128 diagonal")
        if np.max(np.abs(self.local_h.imag), initial=0.0) != 0.0:
            raise ValueError("saved q0 H_p diagonal is expected to be exactly real")
        if (
            not sparse.isspmatrix_csr(self.q0_map)
            or self.q0_map.shape[0] != self.reduced_rows
            or self.q0_map.shape[1] != self.q0_trace_rows + self.q0_port_rows
            or self.q0_map.dtype != np.dtype(np.complex128)
            or self.q0_map.indices.dtype != np.dtype(np.int32)
            or self.q0_map.indptr.dtype != np.dtype(np.int32)
            or not self.q0_map.has_canonical_format
            or not self.q0_map.has_sorted_indices
        ):
            raise ValueError("saved q0 map is not the canonical int32 complex128 q0-only CSR")
        if self.expected_cell_count is not None and (
            self.volume_layout["cell_count"] != int(self.expected_cell_count)
        ):
            raise ValueError("saved q0 volume stream has the wrong complete-cell inventory")
        if self.expected_class_count is not None and (
            self.volume_layout["class_count"] != int(self.expected_class_count)
        ):
            raise ValueError("saved q0 volume stream has the wrong shared-Schur class inventory")

        # Every active row must be represented by the saved lookup. This is a
        # small bitmap relative to the FE space and avoids rebuilding its map.
        present = np.zeros(self.active_rows, dtype=np.bool_)
        chunk_rows = 1_000_000
        for start in range(0, len(self.active_lookup), chunk_rows):
            values = np.asarray(self.active_lookup[start : start + chunk_rows], dtype=np.int64)
            mapped = values[values >= 0]
            if mapped.size:
                present[mapped] = True
        if not np.all(present):
            raise ValueError("saved q0 lookup omits an active trace row")

    def _scan_surface_headers(self) -> tuple[int, ...]:
        if not self.surface_stream_path.is_file():
            raise FileNotFoundError("saved q0 surface functional stream is missing")
        file_size = self.surface_stream_path.stat().st_size
        indices: list[int] = []
        seen: set[int] = set()
        with self.surface_stream_path.open("rb") as stream:
            for port, expected_h in enumerate(self.local_h):
                header = _read_exact(stream, _SURFACE_STREAM_HEADER.size, "surface frame header")
                raw_index, b_count, d_count, h_value = _SURFACE_STREAM_HEADER.unpack(header)
                global_index = int(raw_index)
                if (
                    global_index < 0
                    or global_index in seen
                    or h_value != float(expected_h.real)
                    or b_count > np.iinfo(np.int32).max
                    or d_count > np.iinfo(np.int32).max
                ):
                    raise ValueError(f"saved q0 surface mode/H order is invalid at port {port}")
                seen.add(global_index)
                indices.append(global_index)
                self.maximum_surface_b_count = max(
                    self.maximum_surface_b_count, int(b_count)
                )
                self.maximum_surface_d_count = max(
                    self.maximum_surface_d_count, int(d_count)
                )
                self.maximum_surface_frame_entries = max(
                    self.maximum_surface_frame_entries,
                    int(b_count) + int(d_count),
                )
                payload_bytes = (int(b_count) + int(d_count)) * 20
                stream.seek(payload_bytes, os.SEEK_CUR)
                if stream.tell() > file_size:
                    raise IOError("saved q0 surface stream is truncated inside a mode frame")
            if stream.read(1):
                raise IOError("saved q0 surface stream has trailing bytes")
        return tuple(indices)

    def owner_reserve_facts(self) -> dict[str, int]:
        """Future saved-only owners needed after current maps/lookup are loaded."""
        q0_size = int(self.q0_map.shape[1])
        reduced_vector_bytes = self.reduced_rows * np.dtype(np.complex128).itemsize
        q0_vector_bytes = q0_size * np.dtype(np.complex128).itemsize
        max_surface_entries = self.maximum_surface_frame_entries
        maximum_active = int(self.volume_layout["maximum_active_count"])
        maximum_trace = int(self.volume_layout["maximum_trace_count"])
        mapping_bytes = int(self.volume_layout["maximum_cell_payload_bytes"])
        return {
            "shared_schur_class_payload_bytes": int(self.volume_layout["class_payload_bytes"]),
            "maximum_cell_active_count": maximum_active,
            "maximum_cell_trace_count": maximum_trace,
            "maximum_cell_contribution_payload_bytes": int(16 * maximum_active**2),
            "maximum_cell_expansion_dense_workspace_bytes": int(
                16 * maximum_active * maximum_trace
            ),
            "maximum_surface_b_entries": int(self.maximum_surface_b_count),
            "maximum_surface_d_entries": int(self.maximum_surface_d_count),
            "maximum_surface_frame_entries": int(max_surface_entries),
            "maximum_surface_frame_raw_payload_bytes": int(20 * max_surface_entries),
            "maximum_surface_frame_working_bytes": int(64 * max_surface_entries),
            "maximum_cell_mapping_payload_bytes": mapping_bytes,
        "q0_input_vectors_bytes": int(4 * q0_vector_bytes),
            "saved_native_q0_outputs_bytes": int(6 * q0_vector_bytes),
            "component_validation_outputs_bytes": int(5 * q0_vector_bytes),
            "reduced_input_vectors_bytes": int(2 * reduced_vector_bytes),
        }

    def _read_component(
        self, stream: Any, count: int, *, component: str
    ) -> tuple[np.ndarray, np.ndarray]:
        rows = np.fromfile(stream, dtype="<i4", count=int(count))
        values = np.fromfile(stream, dtype="<c16", count=int(count))
        if rows.size != int(count) or values.size != int(count):
            raise IOError(f"saved q0 {component} surface arrays are truncated")
        if (
            (rows.size > 1 and np.any(rows[1:] <= rows[:-1]))
            or (rows.size and (int(rows[0]) < 0 or int(rows[-1]) >= len(self.active_lookup)))
            or not np.isfinite(values).all()
        ):
            raise ValueError(f"saved q0 {component} surface rows or values are invalid")
        active = np.asarray(self.active_lookup[rows], dtype=np.int32)
        unmapped = active < 0
        if np.any(unmapped & (values != 0.0)):
            raise ValueError(f"nonzero saved q0 {component} row has no active trace mapping")
        keep = ~unmapped
        active = np.ascontiguousarray(active[keep], dtype=np.int32)
        values = np.ascontiguousarray(values[keep], dtype=np.complex128)
        if len(active) > 1 and len(np.unique(active)) != len(active):
            raise ValueError(f"saved q0 {component} rows alias the same active trace row")
        return active, values

    def _admit_surface_frame_pass(self, phase: str) -> None:
        if self.allocation_gate is None:
            return
        entries = self.maximum_surface_frame_entries
        self.allocation_gate(
            f"task40_v27_saved_q0_surface_frame/{phase}",
            {
                "additional_payload_bytes": int(20 * entries),
                "workspace_bytes": int(64 * entries),
                "maximum_b_entries_in_one_mode": int(self.maximum_surface_b_count),
                "maximum_d_entries_in_one_mode": int(self.maximum_surface_d_count),
                "actual_maximum_frame_from_hash_bound_headers": True,
                "all_surface_modes_not_co_resident": True,
            },
        )

    def _iter_surface_components(self, phase: str):
        self._admit_surface_frame_pass(phase)
        with self.surface_stream_path.open("rb") as stream:
            for port, global_index in enumerate(self.mode_indices):
                frame_start = stream.tell()
                header = _read_exact(stream, _SURFACE_STREAM_HEADER.size, "surface frame header")
                recorded_index, b_count, d_count, h_value = _SURFACE_STREAM_HEADER.unpack(header)
                if int(recorded_index) != global_index or h_value != float(self.local_h[port].real):
                    raise ValueError("saved q0 surface stream changed after its header scan")
                b_rows, b_values = self._read_component(stream, b_count, component="B")
                d_rows, d_values = self._read_component(stream, d_count, component="D")
                _advise_file_drop(
                    stream, frame_start, stream.tell() - frame_start,
                    telemetry=self.reader_telemetry,
                )
                yield port, b_rows, b_values, d_rows, d_values
                del b_rows, b_values, d_rows, d_values
            if stream.read(1):
                raise IOError("saved q0 surface stream has trailing bytes after replay")

    def _volume_stream_start(self, stream: Any) -> tuple[int, int, list[np.ndarray]]:
        if _read_exact(stream, len(_VOLUME_MAGIC), "volume magic") != _VOLUME_MAGIC:
            raise IOError("saved q0 volume stream has an unknown header")
        class_count, cell_count = _VOLUME_HEADER.unpack(
            _read_exact(stream, _VOLUME_HEADER.size, "volume inventory")
        )
        if (
            class_count != self.volume_layout["class_count"]
            or cell_count != self.volume_layout["cell_count"]
        ):
            raise IOError("saved q0 volume inventory changed after its scan")
        return int(class_count), int(cell_count), []

    def _iter_volume_mappings(self):
        with self.volume_stream_path.open("rb") as stream:
            class_count, cell_count, _ = self._volume_stream_start(stream)
            for _class_id in range(class_count):
                nrow, ncol = _VOLUME_CLASS_HEADER.unpack(
                    _read_exact(stream, _VOLUME_CLASS_HEADER.size, "Schur class header")
                )
                stream.seek(int(nrow) * int(ncol) * 16, os.SEEK_CUR)
            for cell_index in range(cell_count):
                frame_start = stream.tell()
                raw = _read_exact(stream, _CELL_STREAM_HEADER.size, "cell mapping header")
                class_id, nactive, ntrace, nnz = _CELL_STREAM_HEADER.unpack(raw)
                active_ids = np.fromfile(stream, dtype="<i4", count=int(nactive))
                if active_ids.size != int(nactive):
                    raise IOError("saved q0 cell active-row map is truncated")
                stream.seek(4 * (int(ntrace) + 1) + 4 * int(nnz) + 16 * int(nnz), os.SEEK_CUR)
                if (
                    int(class_id) < 0
                    or int(class_id) >= class_count
                    or nactive <= 0
                    or ntrace <= 0
                    or nnz < 0
                    or np.any(active_ids < 0)
                    or int(active_ids.max(initial=-1)) >= self.active_rows
                    or len(np.unique(active_ids)) != len(active_ids)
                ):
                    raise ValueError("saved q0 cell active-row map is invalid")
                _advise_file_drop(
                    stream, frame_start, stream.tell() - frame_start,
                    telemetry=self.reader_telemetry,
                )
                yield cell_index, np.ascontiguousarray(active_ids, dtype=np.int32)
                del active_ids
            if stream.read(1):
                raise IOError("saved q0 volume stream has trailing bytes after cell mappings")

    def iter_reduced_contribution_layouts(self, *, hhat_block_columns: int | None = None):
        """Yield only q0-relevant reduced row/column supports for V17 routing."""
        from .task40_v10_p6_yorbit import V16_HHAT_BLOCK_COLUMNS

        width = V16_HHAT_BLOCK_COLUMNS if hhat_block_columns is None else hhat_block_columns
        if type(width) is not int or width <= 0:
            raise ValueError("saved q0 Hhat block width must be a positive integer")
        ports = np.arange(self.active_rows, self.reduced_rows, dtype=np.int32)
        for start in range(0, self.port_count, width):
            stop = min(start + width, self.port_count)
            yield ports, ports[start:stop], f"ports/Hhat/{start}:{stop}"
        for cell_index, active_ids in self._iter_volume_mappings():
            yield active_ids, active_ids, f"volume/cell/{cell_index}"
        for port, b_rows, _b_values, d_rows, _d_values in self._iter_surface_components("layout"):
            if b_rows.size:
                port_row = np.asarray([self.active_rows + port], dtype=np.int32)
                yield b_rows, port_row, f"direct/C/provider/{port}"
                del port_row
            if d_rows.size:
                port_row = np.asarray([self.active_rows + port], dtype=np.int32)
                yield port_row, d_rows, f"direct/-D/provider/{port}"
                del port_row

    def _checked(self, rows: np.ndarray, columns: np.ndarray, values: np.ndarray, label: str):
        rows = np.asarray(rows)
        columns = np.asarray(columns)
        values = np.asarray(values)
        int32_max = int(np.iinfo(np.int32).max)
        if (
            rows.ndim != 1
            or columns.ndim != 1
            or rows.dtype.kind not in "iu"
            or columns.dtype.kind not in "iu"
            or (rows.size and (int(rows.min()) < 0 or int(rows.max()) >= self.reduced_rows))
            or (columns.size and (int(columns.min()) < 0 or int(columns.max()) >= self.reduced_rows))
            or (rows.size and int(rows.max()) > int32_max)
            or (columns.size and int(columns.max()) > int32_max)
            or len(np.unique(rows)) != len(rows)
            or len(np.unique(columns)) != len(columns)
            or values.shape != (len(rows), len(columns))
            or values.dtype != np.dtype(np.complex128)
            or not np.isfinite(values).all()
        ):
            raise ValueError(f"saved q0 contribution is invalid: {label}")
        rows = np.ascontiguousarray(rows, dtype=np.int32)
        columns = np.ascontiguousarray(columns, dtype=np.int32)
        values = np.ascontiguousarray(values, dtype=np.complex128)
        rows.setflags(write=False)
        columns.setflags(write=False)
        values.setflags(write=False)
        return rows, columns, values, label

    def iter_reduced_contributions(
        self,
        *,
        allocation_gate: Callable[[str, Mapping[str, Any]], None],
        hhat_block_columns: int | None = None,
    ):
        """Yield exact complex128 q0-source blocks one bounded contribution at a time."""
        from .hcurl_assembly_time_condensation import _constrain_local_schur
        from .task40_v10_p6_yorbit import V16_HHAT_BLOCK_COLUMNS

        if not callable(allocation_gate):
            raise ValueError("saved q0 contributions require the live allocation gate")
        width = V16_HHAT_BLOCK_COLUMNS if hhat_block_columns is None else hhat_block_columns
        if type(width) is not int or width <= 0:
            raise ValueError("saved q0 Hhat block width must be a positive integer")

        def gate(label: str, payload: int, workspace: int) -> None:
            allocation_gate("task40_v27_saved_q0/" + label, {
                "matrix_payload_bytes": int(payload),
                "workspace_bytes": int(workspace),
                "additional_objects_to_current_resident_RSS": True,
                "consumer_releases_contribution_before_next": True,
                "q_map_count": 1,
                "q_map_branch": 0,
            })

        ports = np.arange(self.active_rows, self.reduced_rows, dtype=np.int32)
        for start in range(0, self.port_count, width):
            stop = min(start + width, self.port_count)
            block_width = stop - start
            label = f"ports/Hhat/{start}:{stop}"
            payload = 16 * self.port_count * block_width
            gate(label, payload, 4 * (self.port_count + block_width))
            hhat = np.zeros((self.port_count, block_width), dtype=np.complex128)
            diagonal_rows = np.arange(start, stop, dtype=np.int64)
            hhat[diagonal_rows, np.arange(block_width, dtype=np.int64)] = self.local_h[start:stop]
            yield self._checked(ports, ports[start:stop], hhat, label)
            del diagonal_rows, hhat

        with self.volume_stream_path.open("rb") as stream:
            class_count, cell_count, _ = self._volume_stream_start(stream)
            gate(
                "volume/shared_schur_classes",
                self.volume_layout["class_payload_bytes"],
                0,
            )
            classes: list[np.ndarray] = []
            for class_id in range(class_count):
                frame_start = stream.tell()
                nrow, ncol = _VOLUME_CLASS_HEADER.unpack(
                    _read_exact(stream, _VOLUME_CLASS_HEADER.size, "Schur class header")
                )
                count = int(nrow) * int(ncol)
                values = np.fromfile(stream, dtype="<c16", count=count)
                if values.size != count or not np.isfinite(values).all():
                    raise IOError(f"saved q0 Schur class {class_id} is truncated or non-finite")
                classes.append(values.reshape((int(nrow), int(ncol))))
                _advise_file_drop(
                    stream, frame_start, stream.tell() - frame_start,
                    telemetry=self.reader_telemetry,
                )

            for cell_index in range(cell_count):
                frame_start = stream.tell()
                raw = _read_exact(stream, _CELL_STREAM_HEADER.size, "cell mapping header")
                class_id, nactive, ntrace, nnz = _CELL_STREAM_HEADER.unpack(raw)
                active_ids = np.fromfile(stream, dtype="<i4", count=int(nactive))
                indptr = np.fromfile(stream, dtype="<i4", count=int(ntrace) + 1)
                indices = np.fromfile(stream, dtype="<i4", count=int(nnz))
                expansion_values = np.fromfile(stream, dtype="<c16", count=int(nnz))
                if (
                    active_ids.size != int(nactive)
                    or indptr.size != int(ntrace) + 1
                    or indices.size != int(nnz)
                    or expansion_values.size != int(nnz)
                ):
                    raise IOError("saved q0 cell expansion is truncated")
                if (
                    int(class_id) < 0
                    or int(class_id) >= len(classes)
                    or len(active_ids) == 0
                    or np.any(active_ids < 0)
                    or int(active_ids.max(initial=-1)) >= self.active_rows
                    or len(np.unique(active_ids)) != len(active_ids)
                    or int(indptr[0]) != 0
                    or int(indptr[-1]) != int(nnz)
                    or np.any(indptr[1:] < indptr[:-1])
                    or (nnz and (int(indices.min()) < 0 or int(indices.max()) >= int(nactive)))
                    or not np.isfinite(expansion_values).all()
                ):
                    raise ValueError("saved q0 cell expansion failed CSR/index validation")
                schur = classes[int(class_id)]
                if schur.shape != (int(ntrace), int(ntrace)):
                    raise ValueError("saved q0 cell and Schur class dimensions differ")
                expansion = sparse.csr_matrix(
                    (expansion_values, indices, indptr),
                    shape=(int(ntrace), int(nactive)),
                    copy=False,
                )
                identity = (
                    int(ntrace) == int(nactive)
                    and int(nnz) == int(ntrace)
                    and np.array_equal(indptr, np.arange(int(ntrace) + 1, dtype=np.int32))
                    and np.array_equal(indices, np.arange(int(ntrace), dtype=np.int32))
                    and np.all(expansion_values == 1.0)
                )
                payload = 16 * int(nactive) * int(nactive)
                workspace = (
                    int(active_ids.nbytes + indptr.nbytes + indices.nbytes + expansion_values.nbytes)
                    + 16 * int(nactive) * int(ntrace)
                )
                label = f"volume/cell/{cell_index}"
                gate(label, payload, workspace)
                block = schur if identity else _constrain_local_schur(schur, expansion, False)
                block = np.asarray(block, dtype=np.complex128)
                _advise_file_drop(
                    stream, frame_start, stream.tell() - frame_start,
                    telemetry=self.reader_telemetry,
                )
                yield self._checked(active_ids, active_ids, block, label)
                del active_ids, indptr, indices, expansion_values, expansion, block

            if stream.read(1):
                raise IOError("saved q0 volume stream has trailing bytes after contributions")
        del classes

        for port, b_rows, b_values, d_rows, d_values in self._iter_surface_components("numeric"):
            if b_rows.size:
                label = f"direct/C/provider/{port}"
                port_column = np.asarray([self.active_rows + port], dtype=np.int32)
                block = b_values.reshape(-1, 1)
                gate(label, block.nbytes, b_rows.nbytes + port_column.nbytes)
                yield self._checked(b_rows, port_column, block, label)
                del port_column, block
            if d_rows.size:
                label = f"direct/-D/provider/{port}"
                port_row = np.asarray([self.active_rows + port], dtype=np.int32)
                block = -d_values.reshape(1, -1)
                gate(label, block.nbytes, d_rows.nbytes + port_row.nbytes + d_values.nbytes)
                yield self._checked(port_row, d_rows, block, label)
                del port_row, block
            del b_rows, b_values, d_rows, d_values


def _adapter_source_bindings(
    adapter: SavedQ0ContributionAdapter,
    donor_import_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if adapter._source_array_bindings_cache is None:
        arrays = {
            "active_lookup": adapter.active_lookup,
            "local_h": adapter.local_h,
            "q0_map_data": adapter.q0_map.data,
            "q0_map_indices": adapter.q0_map.indices,
            "q0_map_indptr": adapter.q0_map.indptr,
        }
        adapter._source_array_bindings_cache = {
            key: {
                "shape": list(np.asarray(value).shape),
                "dtype": np.asarray(value).dtype.str,
                "sha256": _sha256_array(value),
            }
            for key, value in arrays.items()
        }
    producer_identity = donor_import_identity
    if donor_import_identity is not None and "producer_identity" in donor_import_identity:
        producer_identity = donor_import_identity.get("producer_identity")
        if not isinstance(producer_identity, Mapping):
            raise ValueError("V27 donor import has no verified nested producer identity")
    payloads = {
        str(item.get("path")): item
        for item in (producer_identity or {}).get("payloads", [])
        if isinstance(item, Mapping)
    }

    def stream_binding(path: Path) -> dict[str, Any]:
        expected = payloads.get(path.name)
        size = int(path.stat().st_size)
        if expected is not None:
            if size != expected.get("bytes"):
                raise ValueError(f"saved q0 donor stream size changed: {path.name}")
            digest = expected.get("sha256")
        else:
            digest = _sha256_file(path)
        return {"path": str(path), "bytes": size, "sha256": digest}

    return {
        "volume_stream": stream_binding(adapter.volume_stream_path),
        "surface_stream": stream_binding(adapter.surface_stream_path),
        "arrays": dict(adapter._source_array_bindings_cache),
    }


def build_saved_q0_csr_structure(
    adapter: SavedQ0ContributionAdapter,
    *,
    output_directory: str | Path,
    expected_row_counts: np.ndarray,
    expected_offsets: np.ndarray,
    allocation_gate: Callable[[str, Mapping[str, Any]], Any],
    source_identity: Mapping[str, Any],
) -> tuple[dict[tuple[int, int], sparse.csr_matrix], dict[str, Any], Path]:
    """Persist the complete q0-only support, routes, and CSR structure once."""
    from .task40_v10_p6_yorbit import _assemble_v17_row_tile_patterns

    _preflight = preflight_saved_q0_csr(
        adapter,
        expected_row_counts=expected_row_counts,
        expected_offsets=expected_offsets,
        allocation_gate=allocation_gate,
    )
    expected_counts, expected_prefix, expected_nnz, expected_payload = _expected_q0_structure(
        adapter, expected_row_counts, expected_offsets
    )
    root = Path(output_directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / "task40_v27_q0_csr_manifest.json"
    structure_path = root / "task40_v27_q0_row_structure.npz"
    if manifest_path.exists() or structure_path.exists():
        raise FileExistsError("V27 q0 CSR output already has a manifest or structure checkpoint")
    source_identity_facts = dict(source_identity)
    json.dumps(source_identity_facts, sort_keys=True, allow_nan=False)
    donor_identity = source_identity.get("donor_identity")
    if not isinstance(donor_identity, Mapping):
        raise ValueError("V27 structure identity must include the verified V26 producer identity")
    source_bindings = _adapter_source_bindings(adapter, donor_identity)
    checkpoint_seen = False

    def structure_checkpoint(
        facts: Mapping[str, Any], row_counts: np.ndarray, offsets: np.ndarray
    ) -> None:
        nonlocal checkpoint_seen
        if checkpoint_seen:
            raise RuntimeError("V27 q0 structure checkpoint was emitted more than once")
        if (
            tuple(facts.get("block", ())) != (0, 0)
            or tuple(facts.get("shape", ())) != tuple(adapter.q0_map.shape[1:] * 2)
            or int(facts.get("nnz", -1)) != expected_nnz
            or not np.array_equal(row_counts, expected_counts)
            or not np.array_equal(offsets, expected_prefix)
        ):
            raise ValueError("rebuilt q0 row structure differs from the V26 complete witness")
        _atomic_structure_npz(structure_path, row_counts, offsets)
        checkpoint_facts = {
            "schema": "task40extra.review_v27_saved_q0_row_structure.v1",
            "status": "ROW_STRUCTURE_CHECKPOINTED",
            "source_identity": source_identity_facts,
            "source_bindings": source_bindings,
            "structure_facts": dict(facts),
            "row_structure_artifact": {
                "path": str(structure_path),
                "bytes": int(structure_path.stat().st_size),
                "sha256": _sha256_file(structure_path),
            },
            "expected_csr_payload_bytes": int(expected_payload),
            "support_route_database_persisted": True,
            "q_map_count": 1,
            "q_map_branch": 0,
            "saved_only_no_fe_or_native_rebuild": True,
        }
        _atomic_json(manifest_path, checkpoint_facts)
        checkpoint_seen = True

    blocks, pattern_facts, _pattern_seconds = _assemble_v17_row_tile_patterns(
        adapter,
        (adapter.q0_map,),
        allocation_gate=allocation_gate,
        requested_blocks=((0, 0),),
        disk_backed_directory=root,
        disk_backed_stem="task40_v27_q0",
        support_routes_directory=root,
        structure_checkpoint=structure_checkpoint,
    )
    if not checkpoint_seen:
        raise RuntimeError("V17 q0 builder returned without the full-structure checkpoint")
    matrix = blocks.get((0, 0))
    block_facts = pattern_facts["pattern_facts_by_block"].get("00")
    if matrix is None or block_facts is None or matrix.shape != (
        adapter.q0_map.shape[1], adapter.q0_map.shape[1]
    ):
        raise RuntimeError("V17 q0-only builder did not return the complete q0 CSR pattern")
    if int(block_facts.get("pattern_nnz", -1)) != expected_nnz:
        raise RuntimeError("V17 q0 CSR slots disagree with the V26 row-count witness")
    if not matrix.has_canonical_format or not matrix.has_sorted_indices:
        raise RuntimeError("V17 q0 CSR structure is not canonical and sorted")
    artifact_paths = dict(block_facts["disk_backed_artifacts"])
    array_artifacts = {
        key: {
            "path": str(Path(path).resolve()),
            "bytes": int(Path(path).stat().st_size),
            "sha256": _sha256_file(Path(path)),
        }
        for key, path in artifact_paths.items()
        if key in {"indptr", "indices"}
    }
    if set(array_artifacts) != {"indptr", "indices"}:
        raise RuntimeError("V17 q0 CSR did not persist both structure arrays")
    support_database_path = pattern_facts.get("support_route_database_path")
    if (
        not support_database_path
        or not Path(support_database_path).is_file()
        or not pattern_facts.get("support_route_database_sha256")
    ):
        raise RuntimeError("V17 q0 support/routes database was not preserved")
    manifest = {
        "schema": "task40extra.review_v27_saved_q0_csr.v1",
        "status": "STRUCTURE_COMPLETE_VALUES_PENDING",
        "source_identity": source_identity_facts,
        "source_bindings": source_bindings,
        "q_map_count": 1,
        "q_map_branch": 0,
        "shape": list(matrix.shape),
        "stored_structural_slots": int(matrix.nnz),
        "csr_index_dtype": matrix.indices.dtype.str,
        "csr_data_dtype": matrix.data.dtype.str,
        "csr_payload_bytes": int(expected_payload),
        "row_structure_artifact": {
            "path": str(structure_path),
            "bytes": int(structure_path.stat().st_size),
            "sha256": _sha256_file(structure_path),
        },
        "csr_artifacts": {
            **array_artifacts,
            "data": {
                "path": str(Path(artifact_paths["data"]).resolve()),
                "bytes": int(Path(artifact_paths["data"]).stat().st_size),
                "initially_zeroed": True,
                "sha256": None,
            },
        },
        "support_routes": {
            "path": str(Path(support_database_path).resolve()),
            "bytes": int(pattern_facts["support_route_database_file_bytes"]),
            "sha256": pattern_facts["support_route_database_sha256"],
            "support_descriptor_bytes": int(
                pattern_facts["support_descriptor_logical_bytes_written"]
            ),
            "route_count": int(pattern_facts["contribution_to_tile_route_count"]),
        },
        "pattern_facts": block_facts,
        "pattern_metadata": {
            key: value
            for key, value in pattern_facts.items()
            if key != "pattern_facts_by_block"
        },
        "row_count_witness_matches": True,
        "saved_only_no_fe_or_native_rebuild": True,
    }
    _atomic_json(manifest_path, manifest)
    return blocks, manifest, manifest_path


def fill_saved_q0_csr_values(
    adapter: SavedQ0ContributionAdapter,
    *,
    manifest_path: str | Path,
    allocation_gate: Callable[[str, Mapping[str, Any]], Any],
    source_identity: Mapping[str, Any],
) -> tuple[sparse.csr_matrix, dict[str, Any]]:
    """Fill or restart the q0 numeric pass without adding onto partial values."""
    from .task40_v10_p6_yorbit import (
        Q_ASSEMBLY_ROW_TILE_V17,
        _accumulate_bounded_q_pattern_values,
    )

    path = Path(manifest_path).resolve()
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "task40extra.review_v27_saved_q0_csr.v1":
        raise ValueError("V27 q0 numeric continuation manifest has an unknown schema")
    if manifest.get("status") not in {
        "STRUCTURE_COMPLETE_VALUES_PENDING",
        "NUMERIC_FILL_INCOMPLETE",
    }:
        raise ValueError("V27 q0 numeric continuation is not in a resumable state")
    if (
        not isinstance(manifest.get("source_identity"), Mapping)
        or manifest["source_identity"].get("donor_identity")
        != source_identity.get("donor_identity")
        or manifest.get("source_bindings")
        != _adapter_source_bindings(adapter, source_identity.get("donor_identity"))
        or manifest.get("q_map_count") != 1
        or manifest.get("q_map_branch") != 0
    ):
        raise ValueError("V27 q0 continuation source identity differs from its structure")
    csr_artifacts = manifest.get("csr_artifacts", {})
    indptr_path = Path(csr_artifacts.get("indptr", {}).get("path", ""))
    indices_path = Path(csr_artifacts.get("indices", {}).get("path", ""))
    data_path = Path(csr_artifacts.get("data", {}).get("path", ""))
    structure_record = manifest.get("row_structure_artifact", {})
    structure_path = Path(structure_record.get("path", ""))
    for artifact, record in (
        (indptr_path, csr_artifacts.get("indptr", {})),
        (indices_path, csr_artifacts.get("indices", {})),
        (structure_path, structure_record),
    ):
        if not artifact.is_file() or _sha256_file(artifact) != record.get("sha256"):
            raise ValueError(f"V27 q0 continuation structure artifact changed: {artifact.name}")
    indptr = np.load(indptr_path, mmap_mode="r+", allow_pickle=False)
    indices = np.load(indices_path, mmap_mode="r+", allow_pickle=False)
    data = np.load(data_path, mmap_mode="r+", allow_pickle=False)
    with np.load(structure_path, allow_pickle=False) as structure_archive:
        checkpoint_offsets = np.asarray(structure_archive["offsets"], dtype=np.int64)
    if (
        indptr.dtype != np.dtype(adapter.q0_map.indices.dtype)
        or indices.dtype != np.dtype(adapter.q0_map.indices.dtype)
        or data.dtype != np.dtype(np.complex128)
        or indptr.shape != (adapter.q0_map.shape[1] + 1,)
        or indices.ndim != 1
        or data.shape != indices.shape
        or int(indptr[-1]) != len(indices)
        or not np.array_equal(indptr.astype(np.int64), checkpoint_offsets)
    ):
        raise ValueError("V27 q0 numeric continuation arrays disagree with the saved structure")
    matrix = sparse.csr_matrix(
        (data, indices, indptr),
        shape=(adapter.q0_map.shape[1], adapter.q0_map.shape[1]),
        copy=False,
    )
    if not all(
        np.shares_memory(owner, view)
        for owner, view in ((data, matrix.data), (indices, matrix.indices), (indptr, matrix.indptr))
    ):
        raise RuntimeError("SciPy q0 CSR wrapper detached from its disk-backed arrays")
    if not matrix.has_canonical_format or not matrix.has_sorted_indices:
        raise ValueError("V27 q0 numeric continuation CSR columns are not sorted and unique")
    manifest["status"] = "NUMERIC_FILL_INCOMPLETE"
    manifest["numeric_pass"] = {
        "restart_policy": "clear_all_values_before_each_numeric_pass",
        "contribution_cursor": None,
        "started": True,
    }
    _atomic_json(path, manifest)
    for start in range(0, len(data), 1 << 20):
        data[start : start + (1 << 20)] = 0.0
    data.flush()
    pattern_facts = dict(manifest["pattern_facts"])
    blocks, numeric_facts = _accumulate_bounded_q_pattern_values(
        adapter,
        (adapter.q0_map,),
        {(0, 0): matrix},
        allocation_gate=allocation_gate,
        assembly_strategy=Q_ASSEMBLY_ROW_TILE_V17,
        pattern_algorithm=str(
            manifest["pattern_metadata"].get("pattern_algorithm", "")
        ),
        patterns={"00": pattern_facts},
        pattern_seconds=float(
            manifest["pattern_metadata"].get("pattern_seconds", 0.0)
        ),
        pattern_metadata=manifest["pattern_metadata"],
    )
    matrix = blocks[(0, 0)]
    if not np.shares_memory(data, matrix.data):
        raise RuntimeError("V27 numeric accumulator detached from the persistent data array")
    data.flush()
    if not matrix.has_canonical_format or not matrix.has_sorted_indices:
        raise RuntimeError("V27 q0 numeric pass changed the canonical CSR structure")
    numeric_facts = dict(numeric_facts)
    numeric_facts["stored_structural_slots"] = int(matrix.nnz)
    numeric_facts["numeric_nonzero_entries"] = int(
        numeric_facts["numeric_nonzero_entries_by_block"]["00"]
    )
    numeric_facts["exact_zero_slots_retained"] = int(
        numeric_facts["exact_zero_slots_retained_by_block"]["00"]
    )
    manifest["status"] = "COMPLETE_CSR"
    manifest["numeric_pass"] = {
        "restart_policy": "clear_all_values_before_each_numeric_pass",
        "contribution_cursor": None,
        "complete": True,
        "numeric_facts": numeric_facts,
    }
    manifest["csr_artifacts"]["data"]["sha256"] = _sha256_file(data_path)
    manifest["csr_artifacts"]["data"]["initially_zeroed"] = True
    manifest["numeric_fill_identity"] = dict(source_identity)
    _atomic_json(path, manifest)
    return matrix, manifest


def open_saved_q0_csr_from_manifest(
    manifest_path: str | Path,
) -> tuple[sparse.csr_matrix, dict[str, Any]]:
    """Reopen the completed q0 CSR payloads from their saved manifest."""
    path = Path(manifest_path).resolve()
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if (
        manifest.get("schema") != "task40extra.review_v27_saved_q0_csr.v1"
        or manifest.get("status") != "COMPLETE_CSR"
        or manifest.get("q_map_count") != 1
        or manifest.get("q_map_branch") != 0
        or manifest.get("saved_only_no_fe_or_native_rebuild") is not True
    ):
        raise ValueError("V27 q0 CSR manifest does not describe a complete saved-only matrix")
    shape = tuple(int(value) for value in manifest.get("shape", ()))
    artifacts = manifest.get("csr_artifacts", {})
    if len(shape) != 2 or shape[0] != shape[1] or not isinstance(artifacts, Mapping):
        raise ValueError("V27 q0 CSR manifest shape/artifact inventory is malformed")
    arrays: dict[str, np.ndarray] = {}
    for name in ("indptr", "indices", "data"):
        record = artifacts.get(name)
        if not isinstance(record, Mapping):
            raise ValueError(f"V27 q0 CSR manifest is missing its {name} artifact")
        artifact_path = Path(str(record.get("path", ""))).resolve()
        if (
            not artifact_path.is_relative_to(path.parent)
            or not artifact_path.is_file()
            or artifact_path.stat().st_size != record.get("bytes")
            or _sha256_file(artifact_path) != record.get("sha256")
        ):
            raise ValueError(f"V27 q0 CSR saved {name} artifact failed manifest verification")
        arrays[name] = np.load(artifact_path, mmap_mode="r", allow_pickle=False)
    indptr, indices, data = arrays["indptr"], arrays["indices"], arrays["data"]
    if (
        manifest.get("csr_index_dtype") != np.dtype(np.int32).str
        or manifest.get("csr_data_dtype") != np.dtype(np.complex128).str
        or indptr.dtype != np.dtype(np.int32)
        or indices.dtype != np.dtype(np.int32)
        or data.dtype != np.dtype(np.complex128)
        or indptr.shape != (shape[0] + 1,)
        or indices.ndim != 1
        or data.shape != indices.shape
        or int(indptr[0]) != 0
        or int(indptr[-1]) != len(indices)
        or len(indices) != manifest.get("stored_structural_slots")
    ):
        raise ValueError("V27 q0 CSR payload dimensions/dtypes differ from the manifest")
    matrix = sparse.csr_matrix((data, indices, indptr), shape=shape, copy=False)
    if (
        not all(
            np.shares_memory(owner, view)
            for owner, view in ((data, matrix.data), (indices, matrix.indices), (indptr, matrix.indptr))
        )
        or not matrix.has_canonical_format
        or not matrix.has_sorted_indices
    ):
        raise ValueError("V27 q0 CSR reopened arrays detached or are not canonical sorted CSR")
    return matrix, manifest

