"""Selected-q V30 production from saved or live reduced contributions.

The saved-data path deliberately reuses the V17 row-tile support/prefix builder
and sparse-local numeric projector.  Its optional direct-H path forms only the
selected q port block, so q4 does not route through a dense projection or reuse
q0's row offsets.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
from scipy import sparse


V30_SELECTED_Q_MANIFEST_SCHEMA = "task40extra.review_v30_q_csr.v1"
V30_SELECTED_Q_NATIVE_SCHEMA = "task40extra.review_v30_q_csr_native_qualification.v1"
V30_SELECTED_Q_SELECTOR_SCHEMA = "task40extra.review_v30_qualified_q_csr_selector.v1"
_NATIVE_LIMIT = 1.0e-11


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent,
        prefix=f".{path.name}.", suffix=".tmp", delete=False,
    ) as stream:
        temporary = Path(stream.name)
        json.dump(dict(value), stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _checked_selected_map(q_map: sparse.csr_matrix, *, local_rows: int) -> None:
    if (
        not sparse.isspmatrix_csr(q_map)
        or q_map.dtype != np.dtype(np.complex128)
        or q_map.indices.dtype != np.dtype(np.int32)
        or q_map.indptr.dtype != np.dtype(np.int32)
        or q_map.shape[0] != local_rows
        or q_map.shape[1] <= 0
        or not q_map.has_canonical_format
        or not q_map.has_sorted_indices
        or not np.isfinite(q_map.data).all()
    ):
        raise ValueError("selected q map must be finite canonical complex128/int32 CSR")


class SavedSelectedQContributionView:
    """View a saved local contribution stream through one actual q map."""

    def __init__(
        self,
        source: Any,
        q_map: sparse.csr_matrix,
        *,
        q_index: int,
        twist_index: int,
        trace_rows: int,
    ) -> None:
        if type(q_index) is not int or q_index < 0:
            raise ValueError("selected q index must be a nonnegative integer")
        if type(twist_index) is not int or twist_index < 0:
            raise ValueError("selected twist index must be a nonnegative integer")
        if not callable(getattr(source, "iter_reduced_contributions", None)) or not callable(
            getattr(source, "iter_reduced_contribution_layouts", None)
        ):
            raise TypeError("saved selected-q source needs the accepted contribution iterator")
        _checked_selected_map(q_map, local_rows=int(source.reduced_rows))
        self.source = source
        self.q_map = q_map
        self.q_index = q_index
        self.twist_index = twist_index
        self.selected_hhat_trace_rows = int(trace_rows)
        self.active_rows = int(source.active_rows)
        self.reduced_rows = int(source.reduced_rows)
        self.port_count = int(source.port_count)
        if not 0 < self.selected_hhat_trace_rows < q_map.shape[1]:
            raise ValueError("selected q map needs nonempty trace and port columns")
        self.selected_port_rows = int(q_map.shape[1] - self.selected_hhat_trace_rows)
        if self.selected_port_rows <= 0 or self.active_rows + self.port_count != self.reduced_rows:
            raise ValueError("selected q map and saved local contribution dimensions differ")

    def iter_reduced_contribution_layouts(self, *, hhat_block_columns: int | None = None):
        yield from self.source.iter_reduced_contribution_layouts(
            hhat_block_columns=hhat_block_columns
        )

    def iter_reduced_contributions(self, **kwargs: Any):
        yield from self.source.iter_reduced_contributions(**kwargs)

    def selected_hhat_sparse_term(
        self,
        *,
        allocation_gate: Callable[[str, Mapping[str, Any]], Any],
    ) -> sparse.csr_matrix:
        """Form U_q^H diag(H) U_q from the selected q port map."""
        if not callable(allocation_gate):
            raise TypeError("selected direct-H construction requires a live allocation gate")
        row_start, row_stop = self.active_rows, self.reduced_rows
        port_map = self.q_map[row_start:row_stop, self.selected_hhat_trace_rows :].tocsr()
        row_counts = np.diff(port_map.indptr).astype(np.int64, copy=False)
        if len(row_counts) != self.port_count:
            raise ValueError("selected q port map does not cover the saved local H rows")
        map_nnz = int(row_counts.sum(dtype=np.int64))
        product_nnz_upper = int(np.dot(row_counts, row_counts))
        index_bytes = int(self.q_map.indices.dtype.itemsize)
        row_map_bytes = map_nnz * (
            int(self.q_map.data.dtype.itemsize) + index_bytes
        ) + (self.port_count + 1) * int(self.q_map.indptr.dtype.itemsize)
        output_bytes_upper = product_nnz_upper * (
            np.dtype(np.complex128).itemsize + index_bytes
        ) + (self.selected_port_rows + 1) * int(self.q_map.indptr.dtype.itemsize)
        workspace = 3 * row_map_bytes + 3 * output_bytes_upper + 16 * map_nnz + int(row_counts.nbytes)
        allocation_gate(
            f"task40_v30_q{self.q_index}_direct_hhat",
            {
                "additional_payload_bytes": output_bytes_upper,
                "workspace_bytes": workspace,
                "q_index": self.q_index,
                "twist_index": self.twist_index,
                "selected_map_nnz": map_nnz,
                "uncoalesced_product_nnz_upper": product_nnz_upper,
                "formula": "U_q^H diag(H) U_q",
                "dense_hhat_materialized": False,
            },
        )
        if map_nnz != int(port_map.nnz):
            raise RuntimeError("selected q port-map support changed during H projection")
        weighted = port_map.copy()
        per_entry_h = np.repeat(np.asarray(self.source.local_h, dtype=np.complex128), row_counts)
        np.multiply(weighted.data, per_entry_h, out=weighted.data)
        term = (port_map.getH() @ weighted).tocsr()
        term.sum_duplicates()
        term.sort_indices()
        if (
            term.shape != (self.selected_port_rows, self.selected_port_rows)
            or term.dtype != np.dtype(np.complex128)
            or not term.has_canonical_format
            or not term.has_sorted_indices
            or not np.isfinite(term.data).all()
        ):
            raise RuntimeError("selected q direct-H term is not finite canonical CSR")
        return term


class LiveP6SelectedQContributionSource:
    """Expose one live sector action through the selected-q source interface."""

    def __init__(self, action: Any, local_h: np.ndarray) -> None:
        active_rows = int(action.condensed.active_rows)
        reduced_rows = int(action.reduced_size)
        port_count = int(action.condensed.appended_rows)
        h = np.ascontiguousarray(local_h, dtype=np.complex128)
        if (
            active_rows <= 0
            or reduced_rows != active_rows + port_count
            or h.shape != (port_count,)
            or not np.isfinite(h).all()
            or not callable(getattr(action, "iter_reduced_contribution_layouts", None))
            or not callable(getattr(action, "iter_reduced_contributions", None))
        ):
            raise ValueError("live selected-q source does not expose one complete reduced sector")
        self.action = action
        self.active_rows = active_rows
        self.reduced_rows = reduced_rows
        self.port_count = port_count
        self.local_h = h

    def iter_reduced_contribution_layouts(self, **kwargs: Any):
        yield from self.action.iter_reduced_contribution_layouts(**kwargs)

    def iter_reduced_contributions(self, **kwargs: Any):
        yield from self.action.iter_reduced_contributions(**kwargs)


def require_direct_hhat_evidence(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Permit the saved direct-H shortcut only with the recorded empty B/D gate."""
    facts = dict(evidence)
    if (
        facts.get("numeric_internal_support_empty") is not True
        or facts.get("internal_B_nnz") != 0
        or facts.get("internal_D_nnz") != 0
    ):
        raise ValueError("selected direct-H requires proven empty internal B and D support")
    return {
        "numeric_internal_support_empty": True,
        "internal_B_nnz": 0,
        "internal_D_nnz": 0,
        "source_facts": facts,
    }


def build_saved_selected_q_pattern(
    source: Any,
    q_map: sparse.csr_matrix,
    *,
    q_index: int,
    twist_index: int,
    trace_rows: int,
    output_directory: str | Path,
    allocation_gate: Callable[[str, Mapping[str, Any]], Any],
) -> tuple[sparse.csr_matrix, SavedSelectedQContributionView, dict[str, Any]]:
    """Build this q's own row-tile pattern from the saved local producer stream."""
    from .task40_v10_p6_yorbit import _assemble_v17_row_tile_patterns

    view = SavedSelectedQContributionView(
        source, q_map, q_index=q_index, twist_index=twist_index, trace_rows=trace_rows
    )
    root = Path(output_directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    stem = f"task40_v30_q{q_index}_twist{twist_index}"
    blocks, facts, pattern_seconds = _assemble_v17_row_tile_patterns(
        view,
        (q_map,),
        allocation_gate=allocation_gate,
        requested_blocks=((0, 0),),
        disk_backed_directory=root,
        disk_backed_stem=stem,
        support_routes_directory=root,
    )
    matrix = blocks.get((0, 0))
    block_facts = facts.get("pattern_facts_by_block", {}).get("00")
    if matrix is None or not isinstance(block_facts, Mapping) or matrix.shape != (
        q_map.shape[1], q_map.shape[1]
    ):
        raise RuntimeError("selected q V17 pattern builder omitted its diagonal CSR")
    if not matrix.has_canonical_format or not matrix.has_sorted_indices:
        raise RuntimeError("selected q V17 CSR pattern is not canonical and sorted")
    paths = block_facts.get("disk_backed_artifacts")
    if not isinstance(paths, Mapping) or set(paths) != {"indptr", "indices", "data"}:
        raise RuntimeError("selected q V17 pattern did not persist all three CSR arrays")
    artifacts = {}
    for name, raw_path in paths.items():
        artifact = Path(str(raw_path)).resolve()
        if not artifact.is_file():
            raise FileNotFoundError(f"selected q pattern array missing: {artifact.name}")
        artifacts[str(name)] = {
            "path": str(artifact),
            "bytes": int(artifact.stat().st_size),
            "sha256": _sha256_file(artifact),
        }
    route_path = facts.get("support_route_database_path")
    if not isinstance(route_path, str) or not Path(route_path).is_file():
        raise RuntimeError("selected q V17 support-route database is missing")
    pattern_record = {
        "pattern_algorithm": facts.get("pattern_algorithm"),
        "pattern_seconds": float(pattern_seconds),
        "block_facts": dict(block_facts),
        "support_route_database": {
            "path": str(Path(route_path).resolve()),
            "bytes": int(Path(route_path).stat().st_size),
            "sha256": _sha256_file(Path(route_path)),
        },
        "csr_artifacts": artifacts,
        "q_index": q_index,
        "twist_index": twist_index,
        "q_map_shape": list(q_map.shape),
        "q_map_sha256": _csr_sha256(q_map),
    }
    return matrix, view, pattern_record


def _csr_sha256(matrix: sparse.csr_matrix) -> str:
    from .task40_v30_qualified_q_csr import _csr_sha256 as qualified_csr_sha256

    return qualified_csr_sha256(matrix)


def _ordered_modes_sha256(modes: Sequence[Any]) -> str:
    rows = [
        [str(mode.side), int(mode.m), int(mode.n), str(mode.polarization)]
        for mode in modes
    ]
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def selected_q_operator_identity(
    *,
    scientific_input_sha256: str,
    profile_identity: Mapping[str, Any],
    ordered_modes: Sequence[Any],
    q_map: sparse.csr_matrix,
    original_h: np.ndarray,
) -> dict[str, str]:
    """Hash the actual profile, ordered modes, map, H, and current science input."""
    from .task40_v30_qualified_q_csr import _array_sha256, _require_sha

    _require_sha(scientific_input_sha256, "scientific_input_sha256")
    _checked_selected_map(q_map, local_rows=q_map.shape[0])
    profile_bytes = json.dumps(
        dict(profile_identity), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    h = np.ascontiguousarray(original_h, dtype=np.complex128)
    if h.ndim != 1 or not np.isfinite(h).all():
        raise ValueError("selected q original H must be a finite one-dimensional complex128 array")
    return {
        "scientific_input_sha256": scientific_input_sha256,
        "profile_identity_sha256": hashlib.sha256(profile_bytes).hexdigest(),
        "ordered_mode_sha256": _ordered_modes_sha256(ordered_modes),
        "q_map_sha256": _csr_sha256(q_map),
        "original_h_sha256": _array_sha256(h, np.dtype(np.complex128), "selected q original H"),
    }


def _flush_memmap(value: Any) -> None:
    flush = getattr(value, "flush", None)
    if callable(flush):
        flush()


def _array_memmap_path(value: Any) -> Path | None:
    current = value
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, np.memmap):
            filename = getattr(current, "filename", None)
            return Path(filename).resolve() if filename is not None else None
        current = getattr(current, "base", None)
    return None


def _smaps_resident_bytes(path: Path) -> tuple[int, int]:
    """Return one file mapping's resident bytes and the number of matching maps."""
    try:
        stat = path.stat()
        device = f"{os.major(stat.st_dev):02x}:{os.minor(stat.st_dev):02x}"
        inode = str(stat.st_ino)
        smaps = Path("/proc/self/smaps").read_text(encoding="ascii", errors="replace")
    except OSError:
        return 0, 0
    resident: list[int] = []
    current_match = False
    for line in smaps.splitlines():
        fields = line.split()
        if len(fields) >= 5 and "-" in fields[0] and fields[3] == device and fields[4] == inode:
            current_match = True
            continue
        if line.startswith("Rss:") and current_match:
            rss_fields = line.split()
            if len(rss_fields) >= 2:
                resident.append(int(rss_fields[1]) * 1024)
            current_match = False
    # A second mapping could alias or split the same inode. Fail conservatively
    # by requiring the whole unique file payload as future resident memory.
    if len(resident) != 1:
        return 0, len(resident)
    return min(int(path.stat().st_size), resident[0]), 1


def _selected_q_preclear_memory_facts(
    matrix: sparse.csr_matrix,
    q_map: sparse.csr_matrix,
    source: Any,
) -> dict[str, Any]:
    from .task40_v10_p6_yorbit import V16_Q_STAGING_BUDGET_BYTES

    array_rows = {
        "data": matrix.data,
        "indices": matrix.indices,
        "indptr": matrix.indptr,
    }
    unique_files: dict[tuple[int, int], dict[str, Any]] = {}
    array_facts = {}
    for name, value in array_rows.items():
        path = _array_memmap_path(value)
        if path is None:
            array_facts[name] = {
                "bytes": int(value.nbytes),
                "backing": "resident_array_owner",
            }
            continue
        stat = path.stat()
        key = (int(stat.st_dev), int(stat.st_ino))
        row = unique_files.get(key)
        if row is None:
            resident, mapping_count = _smaps_resident_bytes(path)
            row = {
                "path": str(path),
                "device": int(stat.st_dev),
                "inode": int(stat.st_ino),
                "file_bytes": int(stat.st_size),
                "resident_bytes": resident,
                "mapping_count": mapping_count,
                "unresident_bytes": max(0, int(stat.st_size) - resident),
                "array_names": [],
            }
            unique_files[key] = row
        row["array_names"].append(name)
        array_facts[name] = {
            "bytes": int(value.nbytes),
            "backing": "mmap_file",
            "device": int(stat.st_dev),
            "inode": int(stat.st_ino),
            "path": str(path),
        }
    unique_payload = sum(int(row["file_bytes"]) for row in unique_files.values())
    resident_backing = sum(int(row["resident_bytes"]) for row in unique_files.values())
    unresident_backing = sum(int(row["unresident_bytes"]) for row in unique_files.values())

    def owner_bytes(value: Any) -> int:
        array = np.asarray(value)
        if _array_memmap_path(array) is not None:
            return 0
        return int(array.nbytes)

    owner_facts = {
        "selected_q_map_bytes": int(q_map.data.nbytes + q_map.indices.nbytes + q_map.indptr.nbytes),
        "source_lookup_bytes": owner_bytes(getattr(source, "active_lookup", np.empty(0, dtype=np.int8))),
        "source_local_h_bytes": owner_bytes(getattr(source, "local_h", np.empty(0, dtype=np.int8))),
        "accounting": "already-live owners are included in the immediate process-tree/cgroup snapshot",
    }
    return {
        "additional_payload_bytes": int(unresident_backing),
        "workspace_bytes": int(V16_Q_STAGING_BUDGET_BYTES),
        "csr_payload_bytes": int(sum(int(value.nbytes) for value in array_rows.values())),
        "unique_backing_file_payload_bytes": int(unique_payload),
        "resident_backing_file_bytes": int(resident_backing),
        "unresident_backing_file_bytes": int(unresident_backing),
        "same_backing_pages_counted_once": True,
        "disk_backed_mmap_payload_bytes": int(unique_payload),
        "mmap_page_cache_counted_as_memory": bool(unique_files),
        "csr_arrays": array_facts,
        "unique_backing_files": list(unique_files.values()),
        "live_owner_facts": owner_facts,
        "preclear_admission": True,
        "projection_staging_reserve_bytes": int(V16_Q_STAGING_BUDGET_BYTES),
    }


def fill_saved_selected_q_values(
    source: Any,
    matrix: sparse.csr_matrix,
    q_map: sparse.csr_matrix,
    *,
    q_index: int,
    twist_index: int,
    trace_rows: int,
    allocation_gate: Callable[[str, Mapping[str, Any]], Any],
    direct_hhat: bool,
    direct_hhat_evidence: Mapping[str, Any] | None = None,
    resident_csr_admission: Callable[[str, Mapping[str, Any]], Any] | None = None,
    contribution_completed_observer: Callable[..., Any] | None = None,
) -> tuple[sparse.csr_matrix, dict[str, Any]]:
    """Fill a selected-q disk-backed CSR with V28 sparse-local arithmetic."""
    from .task40_v10_p6_yorbit import _accumulate_bounded_q_pattern_values

    view = SavedSelectedQContributionView(
        source, q_map, q_index=q_index, twist_index=twist_index, trace_rows=trace_rows
    )
    _checked_selected_map(q_map, local_rows=view.reduced_rows)
    if matrix.shape != (q_map.shape[1], q_map.shape[1]) or not matrix.has_canonical_format:
        raise ValueError("selected q numeric fill does not match its saved row-tile pattern")
    if direct_hhat:
        if direct_hhat_evidence is None:
            raise ValueError("selected direct-H path needs the recorded internal B/D gate")
        require_direct_hhat_evidence(direct_hhat_evidence)
    data_owner = matrix.data
    _flush_memmap(data_owner)
    preclear_facts = _selected_q_preclear_memory_facts(matrix, q_map, source)
    preclear_facts.update(
        {
            "clear_policy": "restart from exact zero; do not add onto partial values",
            "q_index": q_index,
            "twist_index": twist_index,
        }
    )
    gate = resident_csr_admission or allocation_gate
    admitted = gate(f"task40_v30_q{q_index}_preclear_csr_residency", preclear_facts)
    if isinstance(admitted, Mapping) and admitted.get("passed") is False:
        raise RuntimeError("selected-q full CSR/owner/staging admission failed before clearing its data")
    matrix.data[:] = 0.0
    _flush_memmap(matrix.data)
    blocks, audit = _accumulate_bounded_q_pattern_values(
        view,
        (q_map,),
        {(0, 0): matrix},
        allocation_gate=allocation_gate,
        assembly_strategy="ROW_TILE_BOUNDED_CSR_V17",
        pattern_algorithm="selected_q_v17_row_tile_pattern",
        patterns={"00": {"pattern_nnz": int(matrix.nnz)}},
        pattern_seconds=0.0,
        projection_method="sparse_local",
        direct_hhat=direct_hhat,
        direct_hhat_q_index=q_index,
        contribution_completed_observer=contribution_completed_observer,
    )
    filled = blocks[(0, 0)]
    _flush_memmap(filled.data)
    if (
        not np.shares_memory(data_owner, filled.data)
        or not filled.has_canonical_format
        or not filled.has_sorted_indices
    ):
        raise RuntimeError("selected q numeric pass detached or corrupted its disk-backed CSR")
    from .task40_v30_qualified_q_csr import _require_csr

    try:
        _require_csr(filled, "selected q numeric CSR")
    except ValueError as exc:
        raise RuntimeError(
            "selected q numeric pass detached or corrupted its disk-backed CSR"
        ) from exc
    return filled, {
        **dict(audit),
        "q_index": q_index,
        "twist_index": twist_index,
        "projection_method": "sparse_local",
        "direct_hhat_selected_q": bool(direct_hhat),
        "direct_hhat_evidence": (
            require_direct_hhat_evidence(direct_hhat_evidence)
            if direct_hhat
            else None
        ),
        "numeric_fill_complete": True,
        "preclear_memory_admission": preclear_facts,
    }


def _relative_error(actual: np.ndarray, expected: np.ndarray) -> float:
    left = np.asarray(actual, dtype=np.complex128).reshape(-1)
    right = np.asarray(expected, dtype=np.complex128).reshape(-1)
    if left.shape != right.shape or not np.isfinite(left).all() or not np.isfinite(right).all():
        raise ValueError("native/CSR comparison vectors differ in shape or finiteness")
    numerator_sq = 0.0
    denominator_sq = 0.0
    for start in range(0, len(left), 1 << 18):
        stop = min(start + (1 << 18), len(left))
        delta = left[start:stop] - right[start:stop]
        numerator_sq += float(np.vdot(delta, delta).real)
        denominator_sq += float(np.vdot(right[start:stop], right[start:stop]).real)
    numerator = float(np.sqrt(numerator_sq))
    denominator = max(float(np.sqrt(denominator_sq)), np.finfo(float).tiny)
    return numerator / denominator


def _l2(value: np.ndarray) -> float:
    array = np.asarray(value, dtype=np.complex128).reshape(-1)
    total = 0.0
    for start in range(0, len(array), 1 << 18):
        part = array[start : start + (1 << 18)]
        total += float(np.vdot(part, part).real)
    return float(np.sqrt(total))


def selected_q_csr_actions(
    matrix: sparse.csr_matrix,
    inputs: Mapping[str, np.ndarray],
    *,
    allocation_gate: Callable[[str, Mapping[str, Any]], Any],
    q_index: int,
) -> dict[str, np.ndarray]:
    """Run the required four full CSR actions for one q and retain their inputs."""
    required = ("case1_full", "case1_trace_only", "case1_port_only", "case2_full")
    if set(inputs) != set(required):
        raise ValueError("selected q native comparison requires the four named frozen vectors")
    lengths = {len(np.asarray(value)) for value in inputs.values()}
    if lengths != {matrix.shape[1]}:
        raise ValueError("selected q native comparison vectors do not match the CSR columns")
    payload = sum(np.asarray(value).nbytes for value in inputs.values())
    allocation_gate(
        f"task40_v30_q{q_index}_four_csr_actions",
        {
            "additional_payload_bytes": int(2 * matrix.shape[0] * 16),
            "workspace_bytes": int(matrix.shape[0] * 16),
            "retained_input_bytes": int(payload),
            "csr_action_count": 4,
            "q_index": q_index,
        },
    )
    outputs = {}
    for name in required:
        vector = np.asarray(inputs[name])
        if vector.dtype != np.dtype(np.complex128) or not np.isfinite(vector).all():
            raise ValueError(f"selected q {name} vector must be finite complex128")
        outputs[name] = np.asarray(matrix @ vector, dtype=np.complex128)
    return outputs


def qualify_selected_q_native(
    *,
    matrix: sparse.csr_matrix,
    inputs: Mapping[str, np.ndarray],
    csr_outputs: Mapping[str, np.ndarray],
    native_outputs: Mapping[str, np.ndarray],
    native_components_case1: Mapping[str, np.ndarray],
    paired_leakage: Mapping[str, Any],
    trace_rows: int,
) -> dict[str, Any]:
    """Independently check four complete CSR actions and paired-sector leakage."""
    required = ("case1_full", "case1_trace_only", "case1_port_only", "case2_full")
    if (
        set(inputs) != set(required)
        or set(csr_outputs) != set(required)
        or set(native_outputs) != set(required)
    ):
        raise ValueError("selected q native evidence omits one of its four complete actions")
    input_rows = [np.asarray(inputs[name]) for name in required if name.endswith("full")]
    if any(
        value.dtype != np.dtype(np.complex128)
        or value.shape != (matrix.shape[1],)
        or not np.isfinite(value).all()
        or np.any(value == 0)
        for value in input_rows
    ):
        raise ValueError("the two full selected-q inputs must be distinct, nonzero complex128 vectors")
    if np.array_equal(input_rows[0], input_rows[1]):
        raise ValueError("the two selected-q full native inputs must be distinct")
    if type(trace_rows) is not int or not 0 < trace_rows < matrix.shape[1]:
        raise ValueError("selected q native check requires the actual trace/port split")
    full1 = np.asarray(inputs["case1_full"])
    trace_only = np.asarray(inputs["case1_trace_only"])
    port_only = np.asarray(inputs["case1_port_only"])
    if (
        trace_only.dtype != np.dtype(np.complex128)
        or port_only.dtype != np.dtype(np.complex128)
        or not np.array_equal(trace_only[:trace_rows], full1[:trace_rows])
        or np.any(trace_only[trace_rows:] != 0.0)
        or np.any(port_only[:trace_rows] != 0.0)
        or not np.array_equal(port_only[trace_rows:], full1[trace_rows:])
    ):
        raise ValueError("trace-only and port-only inputs are not an exact partition of case1_full")
    components = dict(native_components_case1)
    if set(components) != {"volume", "minus_D", "C", "Hhat"}:
        raise ValueError("first selected-q native case must retain volume, -D, C, and Hhat")
    component_sum = sum(
        (np.asarray(components[key], dtype=np.complex128) for key in ("volume", "minus_D", "C", "Hhat")),
        np.zeros(matrix.shape[0], dtype=np.complex128),
    )
    if _relative_error(component_sum, np.asarray(native_outputs["case1_full"])) > _NATIVE_LIMIT:
        raise ValueError("native volume/-D/C/Hhat components do not reassemble to the full output")
    errors = {}
    for name in required:
        errors[name] = _relative_error(
            np.asarray(csr_outputs[name]), np.asarray(native_outputs[name])
        )
        if errors[name] > _NATIVE_LIMIT:
            raise ValueError(f"selected q {name} CSR/native error exceeded 1e-11")
    split_reassembly = _relative_error(
        np.asarray(native_outputs["case1_trace_only"])
        + np.asarray(native_outputs["case1_port_only"]),
        np.asarray(native_outputs["case1_full"]),
    )
    if split_reassembly > _NATIVE_LIMIT:
        raise ValueError("trace-only plus port-only native actions do not reassemble to case1_full")
    for key in ("q_to_peer", "peer_to_q"):
        row = paired_leakage.get(key)
        if not isinstance(row, Mapping) or not isinstance(row.get("relative"), (int, float)):
            raise ValueError("paired-sector native leakage evidence is incomplete")
        value = float(row["relative"])
        if not np.isfinite(value) or value > _NATIVE_LIMIT:
            raise ValueError("paired-sector native leakage exceeded the existing 1e-11 gate")
    return {
        "schema": V30_SELECTED_Q_NATIVE_SCHEMA,
        "status": "PASS",
        "four_complete_csr_actions_passed": True,
        "csr_action_count": 4,
        "first_input_component_reassembly_relative": _relative_error(
            component_sum, np.asarray(native_outputs["case1_full"])
        ),
        "first_input_trace_plus_port_reassembly_relative": split_reassembly,
        "maximum_relative_error": max(errors.values()),
        "relative_errors": errors,
        "paired_sector_leakage_passed": True,
        "paired_sector_leakage": dict(paired_leakage),
        "relative_error_limit": _NATIVE_LIMIT,
    }


def _nonzero_complex_vector(length: int, seed: int) -> np.ndarray:
    rng = np.random.Generator(np.random.PCG64(seed))
    value = np.empty(length, dtype=np.complex128)
    value.real = 2.0 + rng.random(length)
    value.imag = 1.0 + rng.random(length)
    if not np.isfinite(value).all() or np.any(value == 0.0):
        raise RuntimeError("frozen selected-q native input generation failed")
    return value


def _raw_vector_sha256(value: np.ndarray) -> str:
    array = np.asarray(value)
    if array.dtype != np.dtype(np.complex128) or array.ndim != 1 or not np.isfinite(array).all():
        raise ValueError("saved selected-q native witness arrays must be finite complex128 vectors")
    return hashlib.sha256(np.ascontiguousarray(array).view(np.uint8)).hexdigest()


def _checked_saved_native_vector(
    witness: Mapping[str, Any],
    name: str,
    *,
    expected_length: int,
    expected_operator_identity: Mapping[str, Any],
    expected_current_identity: Mapping[str, Any],
) -> np.ndarray:
    if (
        witness.get("schema") != "task40extra.review_v30_selected_q_saved_native_reuse.v1"
        or dict(witness.get("operator_identity", {})) != dict(expected_operator_identity)
        or not isinstance(expected_current_identity, Mapping)
    ):
        raise ValueError("saved selected-q native witness is not bound to the live operator identity")
    native_manifest = witness.get("native_manifest")
    replay_manifest = witness.get("saved_replay_manifest")
    donor_receipt = witness.get("donor_verifier_receipt")
    if (
        not isinstance(native_manifest, Mapping)
        or not isinstance(replay_manifest, Mapping)
        or not isinstance(donor_receipt, Mapping)
    ):
        raise ValueError("saved selected-q witness must include its verified V26 native and replay manifests")
    for key in ("native_manifest_sha256", "saved_replay_manifest_sha256", "producer_identity_sha256"):
        value = witness.get(key)
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise ValueError(f"saved selected-q native witness has invalid {key}")
    native_schema = native_manifest.get("schema")
    native_identity = native_manifest.get(
        "native_current_identity", native_manifest.get("current_identity")
    )
    donor_identity = witness.get("current_identity")
    recovery_identity = native_manifest.get("recovery_current_identity")
    current_keys = (
        "run_id",
        "physical_model_sha256",
        "campaign_window_sha256",
        "producer_identity_sha256",
        "mode_manifest_sha256",
        "ordered_mode_key_sha256",
    )
    if donor_receipt.get("schema") == "task40extra.review_v26_native_case_recovery_check.v1":
        receipt_path = Path(str(witness.get("donor_verifier_receipt_path", "")))
        receipt_sha = witness.get("donor_verifier_receipt_sha256")
        receipt_valid = (
            donor_receipt.get("status") == "PASS_READONLY_THREE_CASE_RECOVERY"
            and donor_receipt.get("checker_passed") is True
            and isinstance(donor_identity, Mapping)
            and donor_receipt.get("recovery_current_identity") == dict(donor_identity)
            and donor_receipt.get("producer_identity_sha256")
            == witness.get("producer_identity_sha256")
            and donor_receipt.get("saved_replay_manifest_sha256")
            == witness.get("saved_replay_manifest_sha256")
            and donor_receipt.get("original_native_current_identity")
            == native_manifest.get("native_current_identity")
            and native_manifest.get("recovery_checker_receipt_sha256") == receipt_sha
            and Path(str(native_manifest.get("recovery_checker_receipt_path", ""))).resolve()
            == receipt_path.resolve()
            and isinstance(receipt_sha, str)
            and receipt_path.is_file()
            and _sha256_file(receipt_path) == receipt_sha
        )
    else:
        receipt_valid = (
            donor_receipt.get("schema") == "task40extra.review_v26_native_donor_readback.v1"
            and donor_receipt.get("status") == "PASS"
            and donor_receipt.get("native_manifest_sha256")
            == witness.get("native_manifest_sha256")
            and donor_receipt.get("saved_replay_manifest_sha256")
            == witness.get("saved_replay_manifest_sha256")
            and donor_receipt.get("producer_identity_sha256")
            == witness.get("producer_identity_sha256")
            and donor_receipt.get("donor_current_identity")
            == (dict(donor_identity) if isinstance(donor_identity, Mapping) else {})
        )
    if (
        native_schema not in {
            "task40extra.review_v26_native_action.v1",
            "task40extra.review_v26_native_action_recovery.v1",
        }
        or native_manifest.get("status") not in {
            "PASS_COMPLETE_Q0_NATIVE_CONSUMER",
            "PASS_RECOVERED_THREE_NATIVE_CASES",
        }
        or native_manifest.get("manifest_sha256") != witness.get("native_manifest_sha256")
        or native_manifest.get("producer_identity_sha256") != witness.get("producer_identity_sha256")
        or native_manifest.get("saved_replay_manifest_sha256")
        != witness.get("saved_replay_manifest_sha256")
        or not isinstance(native_identity, Mapping)
        or not isinstance(donor_identity, Mapping)
        or not receipt_valid
        or (
            native_schema == "task40extra.review_v26_native_action.v1"
            and dict(native_identity) != dict(donor_identity)
        )
        or (
            native_schema == "task40extra.review_v26_native_action_recovery.v1"
            and (
                not isinstance(recovery_identity, Mapping)
                or dict(recovery_identity) != dict(donor_identity)
            )
        )
        or replay_manifest.get("schema") != "task40extra.review_v26_saved_q_replay.v1"
        or replay_manifest.get("status") != "PASS_SAVED_STREAM_REPLAY_NO_NATIVE"
        or replay_manifest.get("manifest_sha256") != witness.get("saved_replay_manifest_sha256")
        or replay_manifest.get("producer_identity_sha256") != witness.get("producer_identity_sha256")
        or any(
            native_identity.get(key) != replay_manifest.get("current_identity", {}).get(key)
            for key in current_keys
        )
    ):
        raise ValueError("saved selected-q native/replay manifests do not match the live Task40 identity")
    replay_arrays = (
        replay_manifest.get("artifacts", {}).get("inputs", {}).get("array_sha256", {})
        if isinstance(replay_manifest.get("artifacts"), Mapping)
        else {}
    )
    native_cases = native_manifest.get("cases", {})
    if not isinstance(native_cases, Mapping):
        raise ValueError("saved selected-q native manifest has no persisted case inventory")
    q4_hashes = native_cases.get("q4_pair", {}).get("array_sha256", {})
    q0_hashes = native_cases.get("q0_case_1", {}).get("array_sha256", {})
    artifact_hashes = {
        "case1_full_input": replay_arrays.get("q4_pair"),
        "case1_full_output": q4_hashes.get("native_q4_total"),
        "selected_to_peer_cross": q4_hashes.get("native_q0_from_q4"),
        "peer_case1_input": replay_arrays.get("q0_case_1"),
        "peer_case1_output": q0_hashes.get("native_q0_total"),
        "peer_to_selected_cross": q0_hashes.get("native_q4_from_q0"),
    }
    rows = witness.get("arrays")
    record = rows.get(name) if isinstance(rows, Mapping) else None
    if not isinstance(record, Mapping) or "value" not in record:
        raise ValueError(f"saved selected-q native witness omits {name}")
    value = np.asarray(record["value"])
    if value.shape != (expected_length,) or value.dtype != np.dtype(np.complex128) or not np.isfinite(value).all():
        raise ValueError(f"saved selected-q native witness {name} has invalid shape/dtype/values")
    digest = record.get("sha256")
    if (
        not isinstance(digest, str)
        or digest != artifact_hashes.get(name)
        or _raw_vector_sha256(value) != digest
    ):
        raise ValueError(f"saved selected-q native witness {name} failed its array hash")
    return value


def run_selected_q_native_actions(
    *,
    action: Any,
    volume_action: Any,
    comm: Any,
    q_maps: tuple[sparse.csr_matrix, sparse.csr_matrix],
    q_indices: tuple[int, int],
    trace_rows_by_q: Mapping[int, int],
    selected_q_index: int,
    twist_index: int,
    matrix: sparse.csr_matrix,
    allocation_gate: Callable[[str, Mapping[str, Any]], Any],
    peer_matrix: sparse.csr_matrix | None = None,
    saved_native_witness: Mapping[str, Any] | None = None,
    expected_operator_identity: Mapping[str, Any] | None = None,
    expected_current_identity: Mapping[str, Any] | None = None,
    native_stage_callback: Callable[
        [str, Mapping[str, np.ndarray], Mapping[str, Any]], Mapping[str, Any] | None
    ] | None = None,
    native_stage_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run four CSR actions, reusing identity-bound V26 witnesses when supplied."""
    from .task40_v25_selected_q0 import (
        _native_component_reduced_actions,
        _native_projected_action,
    )

    if (
        len(q_maps) != 2
        or len(q_indices) != 2
        or q_indices[0] == q_indices[1]
        or selected_q_index not in q_indices
        or set(trace_rows_by_q) != set(q_indices)
        or type(twist_index) is not int
        or twist_index < 0
    ):
        raise ValueError("native selected-q route requires the exact two-q sector inventory")
    branch = q_indices.index(selected_q_index)
    peer_branch = 1 - branch
    peer_q_index = q_indices[peer_branch]
    selected_map = q_maps[branch]
    peer_map = q_maps[peer_branch]
    if native_stage_callback is not None and not callable(native_stage_callback):
        raise TypeError("V30 native stage persistence callback must be callable")
    native_stage_records: dict[str, dict[str, Any]] = {}

    def persist_stage(
        name: str,
        arrays: Mapping[str, np.ndarray],
        metadata: Mapping[str, Any],
    ) -> None:
        if native_stage_callback is None:
            return
        saved = native_stage_callback(
            name,
            arrays,
            {**dict(native_stage_identity or {}), **dict(metadata)},
        )
        if isinstance(saved, Mapping):
            native_stage_records[name] = dict(saved)

    _checked_selected_map(selected_map, local_rows=int(action.reduced_size))
    _checked_selected_map(peer_map, local_rows=int(action.reduced_size))
    if matrix.shape != (selected_map.shape[1], selected_map.shape[1]):
        raise ValueError("selected q CSR and native map dimensions differ")
    selected_trace_rows = int(trace_rows_by_q[selected_q_index])
    peer_trace_rows = int(trace_rows_by_q[peer_q_index])
    if not 0 < selected_trace_rows < selected_map.shape[1] or not 0 < peer_trace_rows < peer_map.shape[1]:
        raise ValueError("selected sector trace/port split is outside its q map")
    reuse_saved_native = saved_native_witness is not None
    if reuse_saved_native:
        if (
            selected_q_index != 4
            or peer_q_index != 0
            or twist_index != 0
            or not isinstance(expected_operator_identity, Mapping)
            or not isinstance(expected_current_identity, Mapping)
        ):
            raise ValueError("only the identity-matched saved q4/q0 twist-0 native pair may be reused")

    full_rows = int(action.condensed.full_rows)
    reduced_rows = int(action.reduced_size)
    retained_input_bytes = 4 * int(selected_map.shape[1]) * np.dtype(np.complex128).itemsize
    retained_native_bytes = 4 * int(selected_map.shape[1]) * np.dtype(np.complex128).itemsize
    paired_workspace_bytes = (
        4 * full_rows * np.dtype(np.complex128).itemsize
        + 4 * reduced_rows * np.dtype(np.complex128).itemsize
        + 4 * (int(selected_map.shape[1]) + int(peer_map.shape[1]))
        * np.dtype(np.complex128).itemsize
    )
    allocation_gate(
        f"task40_v30_q{selected_q_index}_native_case_owners",
        {
            "additional_payload_bytes": retained_input_bytes + retained_native_bytes,
            "workspace_bytes": paired_workspace_bytes,
            "q_indices": list(q_indices),
            "selected_q_index": selected_q_index,
            "native_complete_action_count": 2 if reuse_saved_native else 3,
            "native_saved_witness_reused": reuse_saved_native,
            "native_case_names": [
                "case1_full",
                "case2_full",
                *([] if reuse_saved_native else ["paired_peer_full"]),
                "case1_trace_only_and_port_only_from_components",
            ],
        },
    )
    seed_offset = 1009 * twist_index
    if reuse_saved_native:
        if saved_native_witness is None:
            raise RuntimeError("selected q4 witness disappeared after its admission gate")
        inputs = {
            "case1_full": _checked_saved_native_vector(
                saved_native_witness,
                "case1_full_input",
                expected_length=int(selected_map.shape[1]),
                expected_operator_identity=expected_operator_identity or {},
                expected_current_identity=expected_current_identity or {},
            ),
            "case2_full": _nonzero_complex_vector(
                int(selected_map.shape[1]), 301101 + selected_q_index + seed_offset
            ),
        }
        reused_case1 = _checked_saved_native_vector(
            saved_native_witness,
            "case1_full_output",
            expected_length=int(selected_map.shape[1]),
            expected_operator_identity=expected_operator_identity or {},
            expected_current_identity=expected_current_identity or {},
        )
        reused_selected_cross = _checked_saved_native_vector(
            saved_native_witness,
            "selected_to_peer_cross",
            expected_length=int(peer_map.shape[1]),
            expected_operator_identity=expected_operator_identity or {},
            expected_current_identity=expected_current_identity or {},
        )
        reused_peer_input = _checked_saved_native_vector(
            saved_native_witness,
            "peer_case1_input",
            expected_length=int(peer_map.shape[1]),
            expected_operator_identity=expected_operator_identity or {},
            expected_current_identity=expected_current_identity or {},
        )
        reused_peer_diagonal = _checked_saved_native_vector(
            saved_native_witness,
            "peer_case1_output",
            expected_length=int(peer_map.shape[1]),
            expected_operator_identity=expected_operator_identity or {},
            expected_current_identity=expected_current_identity or {},
        )
        reused_peer_cross = _checked_saved_native_vector(
            saved_native_witness,
            "peer_to_selected_cross",
            expected_length=int(selected_map.shape[1]),
            expected_operator_identity=expected_operator_identity or {},
            expected_current_identity=expected_current_identity or {},
        )
        peer_input = reused_peer_input
    else:
        inputs = {
            "case1_full": _nonzero_complex_vector(
                int(selected_map.shape[1]), 301001 + selected_q_index + seed_offset
            ),
            "case2_full": _nonzero_complex_vector(
                int(selected_map.shape[1]), 301101 + selected_q_index + seed_offset
            ),
        }
        reused_case1 = reused_selected_cross = None
        reused_peer_input = reused_peer_diagonal = reused_peer_cross = None
        peer_input = _nonzero_complex_vector(
            int(peer_map.shape[1]), 301201 + peer_q_index + seed_offset
        )
    inputs["case1_trace_only"] = np.zeros_like(inputs["case1_full"])
    inputs["case1_trace_only"][:selected_trace_rows] = inputs["case1_full"][:selected_trace_rows]
    inputs["case1_port_only"] = np.zeros_like(inputs["case1_full"])
    inputs["case1_port_only"][selected_trace_rows:] = inputs["case1_full"][selected_trace_rows:]
    reused_array_references = (
        dict(saved_native_witness.get("array_references", {}))
        if reuse_saved_native and isinstance(saved_native_witness, Mapping)
        else {}
    )
    fresh_input_arrays = dict(inputs)
    if reuse_saved_native:
        # The old V26 full input stays in its original replay artifact.
        fresh_input_arrays.pop("case1_full", None)
    else:
        fresh_input_arrays["paired_peer_full"] = peer_input
    persist_stage(
        "inputs_ready",
        fresh_input_arrays,
        {
            "input_names": sorted(inputs),
            "paired_peer_input_present": True,
            "reused_artifacts": {
                key: reused_array_references[key]
                for key in ("case1_full_input", "peer_case1_input")
                if key in reused_array_references
            },
        },
    )

    native_outputs: dict[str, np.ndarray] = {}
    native_components_case1: dict[str, np.ndarray]
    peer_case2: np.ndarray
    if reuse_saved_native:
        allocation_gate(
            f"task40_v30_q{selected_q_index}_native_case1_missing_components",
            {
                "additional_payload_bytes": int(
                    4 * reduced_rows * np.dtype(np.complex128).itemsize
                    + 4 * (selected_map.shape[1] + peer_map.shape[1])
                    * np.dtype(np.complex128).itemsize
                ),
                "workspace_bytes": paired_workspace_bytes,
                "input_q": selected_q_index,
                "output_q": list(q_indices),
                "reused_case1_total_and_both_leakage_directions": True,
                "component_capture": True,
            },
        )
        reduced_components = _native_component_reduced_actions(
            action=action,
            volume_action=volume_action,
            comm=comm,
            q_map=selected_map,
            trace_rows=selected_trace_rows,
            trace_input=inputs["case1_full"][:selected_trace_rows],
            port_input=inputs["case1_full"][selected_trace_rows:],
        )
        native_components_case1 = {
            ("minus_D" if key == "-D" else key): np.asarray(
                selected_map.conjugate().T @ value, dtype=np.complex128
            ).reshape(-1)
            for key, value in reduced_components.items()
        }
        persist_stage(
            "case1_complete",
            {
                f"component_case1_{name}": value
                for name, value in native_components_case1.items()
            },
            {
                "native_total_and_paired_leakage_reused": True,
                "component_array_sha256": {
                    name: _raw_vector_sha256(value)
                    for name, value in native_components_case1.items()
                },
                "reused_artifacts": {
                    key: reused_array_references[key]
                    for key in (
                        "case1_full_input",
                        "case1_full_output",
                        "selected_to_peer_cross",
                    )
                    if key in reused_array_references
                },
            },
        )
        component_total = sum(
            (native_components_case1[key] for key in ("volume", "minus_D", "C", "Hhat")),
            np.zeros(matrix.shape[0], dtype=np.complex128),
        )
        if _relative_error(component_total, reused_case1) > _NATIVE_LIMIT:
            raise ValueError("fresh selected-q components do not reassemble to the saved case1 native output")
        native_outputs["case1_full"] = reused_case1
        peer_input = reused_peer_input
        peer_diagonal = reused_peer_diagonal
        peer_cross_to_selected = reused_peer_cross
        peer_cross_from_selected = reused_selected_cross
        persist_stage(
            "peer_case1_complete",
            {},
            {
                "native_peer_action_reused": True,
                "reused_artifacts": {
                    key: reused_array_references[key]
                    for key in (
                        "peer_case1_input",
                        "peer_case1_output",
                        "peer_to_selected_cross",
                    )
                    if key in reused_array_references
                },
            },
        )
    else:
        allocation_gate(
            f"task40_v30_q{selected_q_index}_native_case1_with_components",
            {
                "additional_payload_bytes": int(
                    (2 * selected_map.shape[1] + peer_map.shape[1])
                    * np.dtype(np.complex128).itemsize
                ),
                "workspace_bytes": paired_workspace_bytes,
                "input_q": selected_q_index,
                "output_q": list(q_indices),
                "component_capture": True,
            },
        )
        out0, out1, _reduced, components0, components1 = _native_projected_action(
            action=action,
            volume_action=volume_action,
            comm=comm,
            input_map=selected_map,
            output_maps=q_maps,
            source=inputs["case1_full"],
            trace_rows=selected_trace_rows,
            include_components=True,
        )
        selected_components = components0 if branch == 0 else components1
        native_components_case1 = {
            ("minus_D" if key == "-D" else key): value
            for key, value in selected_components.items()
        }
        native_outputs["case1_full"] = out0 if branch == 0 else out1
        peer_cross_from_selected = out1 if branch == 0 else out0
        persist_stage(
            "case1_complete",
            {
                "case1_full_output": native_outputs["case1_full"],
                "selected_to_peer_cross": peer_cross_from_selected,
                **{
                    f"component_case1_{name}": value
                    for name, value in native_components_case1.items()
                },
            },
            {
                "native_total_and_components_fresh": True,
                "selected_input_sha256": _raw_vector_sha256(inputs["case1_full"]),
            },
        )
        allocation_gate(
            f"task40_v30_q{selected_q_index}_native_peer_direction",
            {
                "additional_payload_bytes": int(
                    (2 * peer_map.shape[1] + selected_map.shape[1])
                    * np.dtype(np.complex128).itemsize
                ),
                "workspace_bytes": paired_workspace_bytes,
                "input_q": peer_q_index,
                "output_q": list(q_indices),
                "purpose": "independent opposite-direction paired-sector leakage",
            },
        )
        peer_result = _native_projected_action(
            action=action,
            volume_action=volume_action,
            comm=comm,
            input_map=peer_map,
            output_maps=q_maps,
            source=peer_input,
            trace_rows=peer_trace_rows,
            include_components=False,
        )
        peer_out0, peer_out1, _peer_reduced = peer_result
        peer_diagonal = peer_out0 if peer_branch == 0 else peer_out1
        peer_cross_to_selected = peer_out0 if branch == 0 else peer_out1
        persist_stage(
            "peer_case1_complete",
            {
                "peer_case1_diagonal": peer_diagonal,
                "peer_to_selected_cross": peer_cross_to_selected,
            },
            {
                "native_peer_action_fresh": True,
                "peer_input_sha256": _raw_vector_sha256(peer_input),
            },
        )

    trace_native = sum(
        (native_components_case1[key] for key in ("volume", "minus_D")),
        np.zeros(matrix.shape[0], dtype=np.complex128),
    )
    port_native = sum(
        (native_components_case1[key] for key in ("C", "Hhat")),
        np.zeros(matrix.shape[0], dtype=np.complex128),
    )
    native_outputs["case1_trace_only"] = trace_native
    native_outputs["case1_port_only"] = port_native
    allocation_gate(
        f"task40_v30_q{selected_q_index}_native_case2_full",
        {
            "additional_payload_bytes": int(
                (2 * selected_map.shape[1] + peer_map.shape[1])
                * np.dtype(np.complex128).itemsize
            ),
            "workspace_bytes": paired_workspace_bytes,
            "input_q": selected_q_index,
            "output_q": list(q_indices),
            "component_capture": False,
        },
    )
    case2_result = _native_projected_action(
        action=action,
        volume_action=volume_action,
        comm=comm,
        input_map=selected_map,
        output_maps=q_maps,
        source=inputs["case2_full"],
        trace_rows=selected_trace_rows,
        include_components=False,
    )
    case2_out0, case2_out1, _case2_reduced = case2_result
    native_outputs["case2_full"] = case2_out0 if branch == 0 else case2_out1
    peer_case2 = case2_out1 if branch == 0 else case2_out0
    persist_stage(
        "case2_complete",
        {
            "case2_full_output": native_outputs["case2_full"],
            "peer_case2_cross": peer_case2,
        },
        {
            "case2_input_sha256": _raw_vector_sha256(inputs["case2_full"]),
            "native_action_complete": True,
        },
    )
    peer_matrix_error = None
    if peer_matrix is not None:
        if peer_matrix.shape != (peer_map.shape[1], peer_map.shape[1]):
            raise ValueError("peer q CSR does not match the actual paired-sector map")
        peer_matrix_error = _relative_error(peer_matrix @ peer_input, peer_diagonal)
        if peer_matrix_error > _NATIVE_LIMIT:
            raise ValueError("peer q CSR/native action differs during the pair leakage check")
    leakage = {
        "q_to_peer": {
            "input_q": selected_q_index,
            "output_q": peer_q_index,
            "relative": _l2(peer_cross_from_selected)
            / max(_l2(native_outputs["case1_full"]), np.finfo(float).tiny),
            "scale": "selected q native diagonal action norm",
        },
        "peer_to_q": {
            "input_q": peer_q_index,
            "output_q": selected_q_index,
            "relative": _l2(peer_cross_to_selected)
            / max(_l2(peer_diagonal), np.finfo(float).tiny),
            "scale": "peer q native diagonal action norm",
            "peer_csr_native_relative": peer_matrix_error,
        },
    }
    paired_native_arrays = {
        "case1_full_output": native_outputs["case1_full"],
        "case1_trace_only_output": native_outputs["case1_trace_only"],
        "case1_port_only_output": native_outputs["case1_port_only"],
        "case2_full_output": native_outputs["case2_full"],
        "peer_case1_diagonal": peer_diagonal,
        "selected_to_peer_cross": peer_cross_from_selected,
        "peer_to_selected_cross": peer_cross_to_selected,
        "peer_case2_cross": peer_case2,
        **{
            f"component_case1_{name}": value
            for name, value in native_components_case1.items()
        },
    }
    persist_stage(
        "paired_witness_ready",
        {},
        {
            "paired_leakage": leakage,
            "native_array_sha256": {
                name: _raw_vector_sha256(value)
                for name, value in paired_native_arrays.items()
            },
            "stage_records": native_stage_records,
            "reused_artifacts": reused_array_references,
            "qualification_follows_this_record": True,
        },
    )
    csr_outputs = selected_q_csr_actions(
        matrix,
        inputs,
        allocation_gate=allocation_gate,
        q_index=selected_q_index,
    )
    receipt = qualify_selected_q_native(
        matrix=matrix,
        inputs=inputs,
        csr_outputs=csr_outputs,
        native_outputs=native_outputs,
        native_components_case1=native_components_case1,
        paired_leakage=leakage,
        trace_rows=selected_trace_rows,
    )
    return {
        **receipt,
        "q_index": selected_q_index,
        "peer_q_index": peer_q_index,
        "q_indices": list(q_indices),
        "native_input_seeds": {
            "case1_full": None if reuse_saved_native else 301001 + selected_q_index + seed_offset,
            "case2_full": 301101 + selected_q_index + seed_offset,
            "paired_peer_full": (
                "reused_v26_native_case1" if reuse_saved_native
                else 301201 + peer_q_index + seed_offset
            ),
        },
        "native_selected_case_count": 2 if reuse_saved_native else 3,
        "native_volume_apply_count": 4 if reuse_saved_native else 6,
        "saved_native_reused": reuse_saved_native,
        "twist_index": twist_index,
        "inputs": inputs,
        "csr_outputs": csr_outputs,
        "native_outputs": native_outputs,
        "native_components_case1": native_components_case1,
        "paired_peer_input": peer_input,
        "paired_peer_native_diagonal": peer_diagonal,
        "paired_peer_native_cross": peer_cross_to_selected,
        "paired_selected_native_cross": peer_cross_from_selected,
        "paired_peer_case2_cross": peer_case2,
        "native_stage_records": native_stage_records,
    }


def _save_array(path: Path, value: np.ndarray) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"refusing to replace selected-q native evidence: {path.name}")
    array = np.asarray(value)
    if array.dtype != np.dtype(np.complex128) or not np.isfinite(array).all():
        raise ValueError(f"selected-q native array {path.name} must be finite complex128")
    with path.open("xb") as stream:
        np.save(stream, array, allow_pickle=False)
        stream.flush()
        os.fsync(stream.fileno())
    return {
        "path": str(path.resolve()),
        "bytes": int(path.stat().st_size),
        "sha256": _sha256_file(path),
        "dtype": array.dtype.str,
        "shape": list(array.shape),
    }


def _persist_v30_native_stage(
    *,
    output_directory: str | Path,
    q_index: int,
    twist_index: int,
    stage: str,
    arrays: Mapping[str, np.ndarray],
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    """Atomically preserve one completed native stage and its original identities."""
    from .task40_v25_selected_q0 import _save_npz_atomic, _write_json

    if (
        type(q_index) is not int
        or q_index < 0
        or type(twist_index) is not int
        or twist_index < 0
        or not stage.replace("_", "").isalnum()
    ):
        raise ValueError("V30 native stage needs safe q, twist, and stage identities")
    root = Path(output_directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    stem = f"task40_v30_q{q_index}_twist{twist_index}_native_{stage}"
    array_path = root / f"{stem}.npz"
    sidecar_path = root / f"{stem}.json"
    if array_path.exists() or sidecar_path.exists():
        raise FileExistsError(f"refusing to replace V30 native stage evidence: {stem}")
    checked: dict[str, np.ndarray] = {}
    for name, raw in arrays.items():
        if not name.replace("_", "").isalnum():
            raise ValueError("V30 native stage has an unsafe array name")
        value = np.asarray(raw)
        if value.ndim != 1 or value.dtype != np.dtype(np.complex128) or not np.isfinite(value).all():
            raise ValueError(f"V30 native stage array {name} must be a finite complex128 vector")
        checked[name] = value
    if checked:
        _save_npz_atomic(array_path, **checked)
    payload = {
        "schema": "task40extra.review_v30_selected_q_native_stage.v1",
        "status": "STAGE_COMPLETE",
        "stage": stage,
        "q_index": q_index,
        "twist_index": twist_index,
        "metadata": dict(metadata),
        "array_artifact": (
            {
                "path": str(array_path),
                "bytes": int(array_path.stat().st_size),
                "sha256": _sha256_file(array_path),
            }
            if checked
            else None
        ),
        "array_names": sorted(checked),
        "array_shapes": {name: list(value.shape) for name, value in checked.items()},
        "array_sha256": {
            name: _raw_vector_sha256(value) for name, value in checked.items()
        },
    }
    _write_json(sidecar_path, payload)
    payload["sidecar_path"] = str(sidecar_path)
    payload["sidecar_sha256"] = _sha256_file(sidecar_path)
    return payload


def _persist_v30_numeric_pending(
    *,
    matrix: sparse.csr_matrix,
    pattern_record: Mapping[str, Any],
    numeric_facts: Mapping[str, Any],
    output_directory: str | Path,
    profile: str,
    q_index: int,
    twist_index: int,
    operator_identity: Mapping[str, Any],
    matrix_source_identity: Mapping[str, Any],
    execution_identity: Mapping[str, Any],
    producer_identity: Mapping[str, Any],
) -> dict[str, Any]:
    """Record the filled CSR independently before any native qualification."""
    from .task40_v25_selected_q0 import _write_json

    if numeric_facts.get("numeric_fill_complete") is not True:
        raise ValueError("V30 pending record requires a completed numeric fill")
    root = Path(output_directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"task40_v30_q{q_index}_twist{twist_index}_numeric_pending.json"
    if path.exists() or _integrity_sidecar_path(path).exists():
        raise FileExistsError("refusing to replace an existing V30 numeric-pending record")
    artifacts: dict[str, dict[str, Any]] = {}
    pattern_artifacts = dict(pattern_record.get("csr_artifacts", {}))
    if set(pattern_artifacts) != {"data", "indices", "indptr"}:
        raise ValueError("V30 numeric-pending record needs all three pattern CSR arrays")
    for name in ("data", "indices", "indptr"):
        row = pattern_artifacts[name]
        artifact = Path(str(row.get("path", ""))).resolve()
        if not artifact.is_file():
            raise FileNotFoundError(f"V30 numeric-pending CSR array is missing: {name}")
        digest = _sha256_file(artifact)
        if name != "data" and digest != row.get("sha256"):
            raise IOError(f"V30 numeric fill changed structural array {name}")
        live_path = _array_memmap_path(getattr(matrix, name))
        if live_path is None or live_path.resolve() != artifact:
            raise ValueError(f"V30 numeric-pending {name} is not the saved pattern backing array")
        artifacts[name] = {
            "path": str(artifact),
            "bytes": int(artifact.stat().st_size),
            "sha256": digest,
            "pattern_sha256": row.get("sha256"),
            "numeric_fill_changed_data": bool(
                name == "data" and digest != row.get("sha256")
            ),
        }
    payload = {
        "schema": "task40extra.review_v30_q_csr_numeric_pending.v1",
        "status": "NUMERIC_COMPLETE_NATIVE_PENDING",
        "profile": profile,
        "q_index": q_index,
        "twist_index": twist_index,
        "shape": list(matrix.shape),
        "stored_structural_slots": int(matrix.nnz),
        "operator_identity": dict(operator_identity),
        "matrix_source_identity": dict(matrix_source_identity),
        "execution_identity": dict(execution_identity),
        "producer_identity": dict(producer_identity),
        "pattern_record": dict(pattern_record),
        "numeric_fill_facts": dict(numeric_facts),
        "csr_artifacts": artifacts,
        "csr_content_sha256": _csr_sha256(matrix),
    }
    _atomic_json(path, payload)
    payload["record_path"] = str(path)
    payload["record_sha256"] = _sha256_file(path)
    _write_integrity_sidecar(path, payload["record_sha256"])
    return payload


def _integrity_sidecar_path(path: Path) -> Path:
    return path.with_name(path.name + ".sha256")


def _write_integrity_sidecar(path: Path, sha256: str) -> Path:
    sidecar = _integrity_sidecar_path(path)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="ascii", dir=sidecar.parent,
        prefix=f".{sidecar.name}.", suffix=".tmp", delete=False,
    ) as stream:
        temporary = Path(stream.name)
        stream.write(f"{sha256}  {path.name}\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, sidecar)
    return sidecar


def _read_integrity_bound_json(path: Path, *, label: str) -> tuple[dict[str, Any], str]:
    sidecar = _integrity_sidecar_path(path)
    if not path.is_file() or not sidecar.is_file():
        raise ValueError(f"{label} lacks its atomic content-hash sidecar")
    fields = sidecar.read_text(encoding="ascii").strip().split()
    if len(fields) != 2 or fields[1] != path.name:
        raise ValueError(f"{label} content-hash sidecar is malformed")
    actual = _sha256_file(path)
    if fields[0] != actual:
        raise ValueError(f"{label} content hash differs from its sidecar")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return payload, actual


def _require_run_identity(value: Mapping[str, Any], label: str) -> dict[str, str]:
    source_sha = value.get("source_sha")
    window_sha256 = value.get("window_sha256")
    if (
        not isinstance(source_sha, str)
        or len(source_sha) != 40
        or any(character not in "0123456789abcdef" for character in source_sha)
        or not isinstance(window_sha256, str)
        or len(window_sha256) != 64
        or any(character not in "0123456789abcdef" for character in window_sha256)
    ):
        raise ValueError(f"{label} must contain a full source SHA and campaign-window SHA-256")
    return {"source_sha": source_sha, "window_sha256": window_sha256}


def make_v31_pending_import_authorization(
    pending_record: Mapping[str, Any],
    *,
    pending_sha256: str,
    consumer_execution_identity: Mapping[str, Any],
) -> dict[str, Any]:
    """Describe one exact old numeric-pending import for a V31 execution contract."""
    artifacts = dict(pending_record.get("csr_artifacts", {}))
    if set(artifacts) != {"data", "indices", "indptr"}:
        raise ValueError("V31 pending import request needs the exact three saved CSR arrays")
    return {
        "schema": "task40extra.review_v31_q_numeric_pending_import_authorization.v1",
        "q_index": int(pending_record["q_index"]),
        "twist_index": int(pending_record["twist_index"]),
        "profile": str(pending_record["profile"]),
        "pending_record_sha256": pending_sha256,
        "producer_execution_identity": _require_run_identity(
            pending_record.get("execution_identity", {}), "pending producer execution identity"
        ),
        "consumer_execution_identity": _require_run_identity(
            consumer_execution_identity, "pending consumer execution identity"
        ),
        "operator_identity": dict(pending_record["operator_identity"]),
        "matrix_source_identity": dict(pending_record["matrix_source_identity"]),
        "producer_identity_sha256": hashlib.sha256(
            json.dumps(
                dict(pending_record["producer_identity"]),
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
        "csr_artifacts_sha256": hashlib.sha256(
            json.dumps(artifacts, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
    }


def _persist_v31_pending_consumer_receipt(
    *,
    pending_path: Path,
    pending: Mapping[str, Any],
    pending_sha256: str,
    consumer_execution_identity: Mapping[str, Any],
    authorization: Mapping[str, Any],
) -> dict[str, Any]:
    """Record cross-window consumption without rewriting the producer's pending evidence."""
    producer_execution = _require_run_identity(
        pending.get("execution_identity", {}), "pending producer execution identity"
    )
    consumer_execution = _require_run_identity(
        consumer_execution_identity, "pending consumer execution identity"
    )
    expected_authorization = make_v31_pending_import_authorization(
        pending,
        pending_sha256=pending_sha256,
        consumer_execution_identity=consumer_execution,
    )
    if dict(authorization) != expected_authorization:
        raise ValueError("cross-window pending import lacks its exact V31 contract authorization")
    identity_seed = json.dumps(
        {
            "pending_record_sha256": pending_sha256,
            "consumer_execution_identity": consumer_execution,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    receipt_id = hashlib.sha256(identity_seed).hexdigest()
    receipt_path = pending_path.with_name(
        f"task40_v31_q{int(pending['q_index'])}_twist{int(pending['twist_index'])}_consumer_{receipt_id}.json"
    )
    payload = {
        "schema": "task40extra.review_v31_q_numeric_pending_consumer.v1",
        "status": "CONSUMED_NUMERIC_COMPLETE_NATIVE_PENDING",
        "q_index": int(pending["q_index"]),
        "twist_index": int(pending["twist_index"]),
        "profile": str(pending["profile"]),
        "operator_identity": dict(pending["operator_identity"]),
        "matrix_source_identity": dict(pending["matrix_source_identity"]),
        "producer_identity": dict(pending["producer_identity"]),
        "producer_execution_identity": producer_execution,
        "consumer_execution_identity": consumer_execution,
        "pending_record": {"path": str(pending_path.resolve()), "sha256": pending_sha256},
        "csr_artifacts": dict(pending["csr_artifacts"]),
        "authorization": expected_authorization,
        "authorization_sha256": hashlib.sha256(
            json.dumps(expected_authorization, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "original_native_status": "NATIVE_PENDING",
        "original_record_rewritten": False,
    }
    if receipt_path.exists() or _integrity_sidecar_path(receipt_path).exists():
        saved, digest = _read_integrity_bound_json(
            receipt_path, label="V31 pending consumer receipt"
        )
        if saved != payload:
            raise ValueError("existing V31 consumer receipt differs from this exact consumer identity")
        return {
            "path": str(receipt_path),
            "sha256": digest,
            "payload": saved,
            "reopened": True,
        }
    _atomic_json(receipt_path, payload)
    digest = _sha256_file(receipt_path)
    _write_integrity_sidecar(receipt_path, digest)
    return {"path": str(receipt_path), "sha256": digest, "payload": payload, "reopened": False}


def _require_v31_pending_consumer_receipt(
    numeric_stage: Mapping[str, Any],
    *,
    consumer_execution_identity: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    pending = numeric_stage.get("numeric_pending")
    if not isinstance(pending, Mapping):
        raise ValueError("prebuilt q numeric stage omits its durable pending record")
    producer_execution = _require_run_identity(
        pending.get("execution_identity", {}), "pending producer execution identity"
    )
    consumer_execution = _require_run_identity(
        consumer_execution_identity, "pending consumer execution identity"
    )
    if producer_execution == consumer_execution:
        return None
    reference = numeric_stage.get("consumer_receipt")
    if not isinstance(reference, Mapping):
        raise ValueError("cross-window prebuilt q requires its V31 consumer receipt")
    receipt_path = Path(str(reference.get("path", ""))).resolve()
    payload, digest = _read_integrity_bound_json(
        receipt_path, label="V31 pending consumer receipt"
    )
    expected_fields = {
        "status": "CONSUMED_NUMERIC_COMPLETE_NATIVE_PENDING",
        "q_index": pending.get("q_index"),
        "twist_index": pending.get("twist_index"),
        "profile": pending.get("profile"),
        "operator_identity": pending.get("operator_identity"),
        "matrix_source_identity": pending.get("matrix_source_identity"),
        "producer_identity": pending.get("producer_identity"),
        "producer_execution_identity": producer_execution,
        "consumer_execution_identity": consumer_execution,
        "pending_record": {
            "path": str(Path(str(pending.get("record_path", ""))).resolve()),
            "sha256": pending.get("record_sha256"),
        },
        "csr_artifacts": pending.get("csr_artifacts"),
        "original_native_status": "NATIVE_PENDING",
        "original_record_rewritten": False,
    }
    expected_authorization = make_v31_pending_import_authorization(
        pending,
        pending_sha256=str(pending.get("record_sha256", "")),
        consumer_execution_identity=consumer_execution,
    )
    expected_fields.update(
        authorization=expected_authorization,
        authorization_sha256=hashlib.sha256(
            json.dumps(expected_authorization, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
    )
    if (
        reference.get("sha256") != digest
        or reference.get("payload") != payload
        or payload.get("schema") != "task40extra.review_v31_q_numeric_pending_consumer.v1"
        or any(payload.get(key) != value for key, value in expected_fields.items())
    ):
        raise ValueError("V31 pending consumer receipt is not bound to this exact q and consumer")
    return {"path": str(receipt_path), "sha256": digest, "payload": payload}


def _persist_v31_pattern_checkpoint(
    *,
    pattern_record: Mapping[str, Any],
    output_directory: Path,
    profile: str,
    q_index: int,
    twist_index: int,
    operator_identity: Mapping[str, Any],
    matrix_source_identity: Mapping[str, Any],
    execution_identity: Mapping[str, Any],
    producer_identity: Mapping[str, Any],
) -> dict[str, Any]:
    """Atomically certify a complete zero-data pattern before numeric fill."""
    path = output_directory / f"task40_v31_q{q_index}_twist{twist_index}_pattern.json"
    if path.exists() or _integrity_sidecar_path(path).exists():
        raise FileExistsError("refusing to replace a V31 selected-q pattern checkpoint")
    arrays = dict(pattern_record.get("csr_artifacts", {}))
    if set(arrays) != {"data", "indices", "indptr"}:
        raise ValueError("V31 pattern checkpoint requires all three CSR arrays")
    if not isinstance(arrays["data"].get("sha256"), str):
        raise ValueError("V31 pattern checkpoint lacks its initial data-array hash")
    payload = {
        "schema": "task40extra.review_v31_q_csr_pattern.v1",
        "status": "PATTERN_COMPLETE_NUMERIC_EMPTY",
        "profile": profile,
        "q_index": q_index,
        "twist_index": twist_index,
        "operator_identity": dict(operator_identity),
        "matrix_source_identity": dict(matrix_source_identity),
        "execution_identity": dict(execution_identity),
        "producer_identity": dict(producer_identity),
        "initial_data_sha256": arrays["data"]["sha256"],
        "numeric_restart_semantics": "fill_saved_selected_q_values clears data to exact zero after its allocation gate",
        "pattern_record": dict(pattern_record),
    }
    _atomic_json(path, payload)
    digest = _sha256_file(path)
    _write_integrity_sidecar(path, digest)
    payload["checkpoint_path"] = str(path)
    payload["checkpoint_sha256"] = digest
    return payload


def _load_v31_pattern_checkpoint(
    *,
    path: Path,
    profile: str,
    q_index: int,
    twist_index: int,
    operator_identity: Mapping[str, Any],
    matrix_source_identity: Mapping[str, Any],
    execution_identity: Mapping[str, Any],
    producer_identity: Mapping[str, Any],
    q_map: sparse.csr_matrix,
    allocation_gate: Callable[[str, Mapping[str, Any]], Any],
) -> tuple[sparse.csr_matrix, dict[str, Any]]:
    payload, digest = _read_integrity_bound_json(path, label="V31 pattern checkpoint")
    if (
        payload.get("schema") != "task40extra.review_v31_q_csr_pattern.v1"
        or payload.get("status") != "PATTERN_COMPLETE_NUMERIC_EMPTY"
        or payload.get("profile") != profile
        or payload.get("q_index") != q_index
        or payload.get("twist_index") != twist_index
        or dict(payload.get("operator_identity", {})) != dict(operator_identity)
        or dict(payload.get("matrix_source_identity", {})) != dict(matrix_source_identity)
        or dict(payload.get("execution_identity", {})) != dict(execution_identity)
        or dict(payload.get("producer_identity", {})) != dict(producer_identity)
    ):
        raise ValueError("V31 pattern checkpoint identity differs from the current saved-q request")
    pattern_record = payload.get("pattern_record")
    if not isinstance(pattern_record, Mapping):
        raise ValueError("V31 pattern checkpoint omits its row-tile facts")
    arrays = dict(pattern_record.get("csr_artifacts", {}))
    if set(arrays) != {"data", "indices", "indptr"}:
        raise ValueError("V31 pattern checkpoint omits a CSR backing array")
    payload_bytes = sum(int(row.get("bytes", -1)) for row in arrays.values())
    if payload_bytes <= 0:
        raise ValueError("V31 pattern checkpoint has invalid backing byte counts")
    allocation_gate(
        f"task40_v31_q{q_index}_pattern_reopen",
        {
            "additional_payload_bytes": payload_bytes,
            "workspace_bytes": 256 * 1024**2,
            "all_large_file_hashes_after_gate": True,
            "pattern_reopen": True,
        },
    )
    if pattern_record.get("q_map_sha256") != _csr_sha256(q_map):
        raise ValueError("V31 pattern checkpoint does not bind the current q map")
    opened = {}
    for name in ("data", "indices", "indptr"):
        row = arrays[name]
        artifact = Path(str(row.get("path", ""))).resolve()
        if (
            not artifact.is_relative_to(path.parent.resolve())
            or not artifact.is_file()
            or artifact.stat().st_size != row.get("bytes")
        ):
            raise ValueError(f"V31 pattern artifact {name} is missing or changed in size")
        if name != "data" and _sha256_file(artifact) != row.get("sha256"):
            raise ValueError(f"V31 pattern structural artifact {name} changed")
        opened[name] = np.load(artifact, mmap_mode="r+" if name == "data" else "r", allow_pickle=False)
    shape = tuple(map(int, pattern_record.get("block_facts", {}).get("shape", ())))
    if (
        len(shape) != 2
        or shape != (q_map.shape[1], q_map.shape[1])
        or opened["data"].dtype != np.dtype(np.complex128)
        or opened["indices"].dtype != np.dtype(np.int32)
        or opened["indptr"].dtype != np.dtype(np.int32)
        or opened["indices"].shape != opened["data"].shape
        or opened["indptr"].shape != (shape[0] + 1,)
    ):
        raise ValueError("V31 pattern arrays do not match the saved q map and CSR dtypes")
    matrix = sparse.csr_matrix(
        (opened["data"], opened["indices"], opened["indptr"]), shape=shape, copy=False
    )
    if not matrix.has_canonical_format or not matrix.has_sorted_indices:
        raise ValueError("V31 reopened pattern is not canonical and sorted")
    checkpoint = dict(payload)
    checkpoint["checkpoint_path"] = str(path)
    checkpoint["checkpoint_sha256"] = digest
    return matrix, checkpoint


def _load_v30_numeric_pending(
    *,
    path: Path,
    profile: str,
    q_index: int,
    twist_index: int,
    operator_identity: Mapping[str, Any],
    matrix_source_identity: Mapping[str, Any],
    execution_identity: Mapping[str, Any],
    producer_identity: Mapping[str, Any],
    allocation_gate: Callable[[str, Mapping[str, Any]], Any],
    consumer_import_authorization: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Strictly reopen a complete pending CSR; never repeat its numeric fill."""
    payload, digest = _read_integrity_bound_json(path, label="V30 numeric-pending record")
    if (
        payload.get("schema") != "task40extra.review_v30_q_csr_numeric_pending.v1"
        or payload.get("status") != "NUMERIC_COMPLETE_NATIVE_PENDING"
        or payload.get("profile") != profile
        or payload.get("q_index") != q_index
        or payload.get("twist_index") != twist_index
        or dict(payload.get("operator_identity", {})) != dict(operator_identity)
        or dict(payload.get("matrix_source_identity", {})) != dict(matrix_source_identity)
        or dict(payload.get("producer_identity", {})) != dict(producer_identity)
    ):
        raise ValueError("V30 numeric-pending identity differs from the current saved-q request")
    records = dict(payload.get("csr_artifacts", {}))
    if set(records) != {"data", "indices", "indptr"}:
        raise ValueError("V30 numeric-pending record omits a CSR array")
    paths = {name: Path(str(row.get("path", ""))).resolve() for name, row in records.items()}
    if any(not artifact.is_relative_to(path.parent.resolve()) or not artifact.is_file() for artifact in paths.values()):
        raise FileNotFoundError("V30 numeric-pending CSR backing array is missing")
    total_bytes = sum(int(row.get("bytes", -1)) for row in records.values())
    allocation_gate(
        f"task40_v31_q{q_index}_numeric_pending_reopen",
        {"additional_payload_bytes": total_bytes, "workspace_bytes": 16 * 1024**2,
         "all_large_file_hashes_after_gate": True},
    )
    for name, artifact in paths.items():
        row = records[name]
        if artifact.stat().st_size != row.get("bytes") or _sha256_file(artifact) != row.get("sha256"):
            raise ValueError(f"V30 numeric-pending CSR artifact {name} failed its size/hash check")
    arrays = {
        name: np.load(path, mmap_mode="r", allow_pickle=False)
        for name, path in paths.items()
    }
    shape = tuple(map(int, payload.get("shape", ())))
    slots = payload.get("stored_structural_slots")
    if (
        len(shape) != 2 or shape[0] != shape[1]
        or type(slots) is not int
        or arrays["data"].dtype != np.dtype(np.complex128)
        or arrays["indices"].dtype != np.dtype(np.int32)
        or arrays["indptr"].dtype != np.dtype(np.int32)
        or arrays["data"].shape != (slots,)
        or arrays["indices"].shape != (slots,)
        or arrays["indptr"].shape != (shape[0] + 1,)
        or int(arrays["indptr"][0]) != 0
        or int(arrays["indptr"][-1]) != slots
    ):
        raise ValueError("V30 numeric-pending CSR dimensions/dtypes differ from its record")
    matrix = sparse.csr_matrix(
        (arrays["data"], arrays["indices"], arrays["indptr"]), shape=shape, copy=False
    )
    from .task40_v30_qualified_q_csr import _require_csr

    _require_csr(matrix, f"q={q_index} numeric-pending CSR")
    if _csr_sha256(matrix) != payload.get("csr_content_sha256"):
        raise ValueError("V30 numeric-pending CSR content hash differs from its record")
    producer_execution = _require_run_identity(
        payload.get("execution_identity", {}), "V30 pending producer execution identity"
    )
    consumer_execution = _require_run_identity(
        execution_identity, "V31 pending consumer execution identity"
    )
    pending = dict(payload)
    pending["record_path"] = str(path)
    pending["record_sha256"] = digest
    consumer_receipt = None
    if producer_execution != consumer_execution:
        if not isinstance(consumer_import_authorization, Mapping):
            raise ValueError("cross-window numeric pending requires a V31 contract import authorization")
        consumer_receipt = _persist_v31_pending_consumer_receipt(
            pending_path=path,
            pending=pending,
            pending_sha256=digest,
            consumer_execution_identity=consumer_execution,
            authorization=consumer_import_authorization,
        )
    return {
        "status": payload["status"],
        "matrix": matrix,
        "pattern_record": dict(payload["pattern_record"]),
        "numeric_facts": dict(payload["numeric_fill_facts"]),
        "numeric_pending": pending,
        "output_directory": str(path.parent),
        "reopened": True,
        "consumer_receipt": consumer_receipt,
    }


def prepare_saved_selected_q_numeric_pending(
    *,
    source: Any,
    q_map: sparse.csr_matrix,
    q_index: int,
    twist_index: int,
    trace_rows: int,
    allocation_gate: Callable[[str, Mapping[str, Any]], Any],
    profile: str,
    operator_identity: Mapping[str, Any],
    matrix_source_identity: Mapping[str, Any],
    execution_identity: Mapping[str, Any],
    producer_identity: Mapping[str, Any],
    output_directory: str | Path,
    direct_hhat_evidence: Mapping[str, Any] | None = None,
    consumer_import_authorization: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build and persist one saved-data q CSR without constructing a native owner.

    This is the reusable saved-first boundary: callers can complete the numeric
    CSR while FE/native/factor construction is still deferred.  The returned
    matrix remains backed by the persisted V17 arrays for a later native pass.
    """
    if type(q_index) is not int or q_index < 0 or type(twist_index) is not int or twist_index < 0:
        raise ValueError("saved selected-q numeric preparation needs explicit q/twist indices")
    if not profile or not callable(allocation_gate):
        raise ValueError("saved selected-q numeric preparation needs profile and allocation gate")
    if not all(isinstance(value, Mapping) and value for value in (
        operator_identity, matrix_source_identity, execution_identity, producer_identity
    )):
        raise ValueError("saved selected-q pending needs nonempty bound identities")
    root = Path(output_directory).resolve()
    pending_path = root / f"task40_v30_q{q_index}_twist{twist_index}_numeric_pending.json"
    if pending_path.exists():
        return _load_v30_numeric_pending(
            path=pending_path,
            profile=profile,
            q_index=q_index,
            twist_index=twist_index,
            operator_identity=operator_identity,
            matrix_source_identity=matrix_source_identity,
            execution_identity=execution_identity,
            producer_identity=producer_identity,
            allocation_gate=allocation_gate,
            consumer_import_authorization=consumer_import_authorization,
        )
    if _integrity_sidecar_path(pending_path).exists():
        raise ValueError("orphan V30 numeric-pending hash sidecar; preserving attempt evidence")
    pattern_path = root / f"task40_v31_q{q_index}_twist{twist_index}_pattern.json"
    if pattern_path.exists():
        matrix, checkpoint = _load_v31_pattern_checkpoint(
            path=pattern_path,
            profile=profile,
            q_index=q_index,
            twist_index=twist_index,
            operator_identity=operator_identity,
            matrix_source_identity=matrix_source_identity,
            execution_identity=execution_identity,
            producer_identity=producer_identity,
            q_map=q_map,
            allocation_gate=allocation_gate,
        )
        pattern_record = dict(checkpoint["pattern_record"])
    else:
        if _integrity_sidecar_path(pattern_path).exists():
            raise ValueError("orphan V31 pattern hash sidecar; preserving attempt evidence")
        matrix, _view, pattern_record = build_saved_selected_q_pattern(
            source,
            q_map,
            q_index=q_index,
            twist_index=twist_index,
            trace_rows=trace_rows,
            output_directory=root,
            allocation_gate=allocation_gate,
        )
        _persist_v31_pattern_checkpoint(
            pattern_record=pattern_record,
            output_directory=root,
            profile=profile,
            q_index=q_index,
            twist_index=twist_index,
            operator_identity=operator_identity,
            matrix_source_identity=matrix_source_identity,
            execution_identity=execution_identity,
            producer_identity=producer_identity,
        )
    matrix, numeric_facts = fill_saved_selected_q_values(
        source,
        matrix,
        q_map,
        q_index=q_index,
        twist_index=twist_index,
        trace_rows=trace_rows,
        allocation_gate=allocation_gate,
        direct_hhat=direct_hhat_evidence is not None,
        direct_hhat_evidence=direct_hhat_evidence,
    )
    pending = _persist_v30_numeric_pending(
        matrix=matrix,
        pattern_record=pattern_record,
        numeric_facts=numeric_facts,
        output_directory=root,
        profile=profile,
        q_index=q_index,
        twist_index=twist_index,
        operator_identity=operator_identity,
        matrix_source_identity=matrix_source_identity,
        execution_identity=execution_identity,
        producer_identity=producer_identity,
    )
    return {
        "status": pending["status"],
        "matrix": matrix,
        "pattern_record": pattern_record,
        "numeric_facts": numeric_facts,
        "numeric_pending": pending,
        "output_directory": str(root),
    }


def finalize_selected_q_csr(
    *,
    matrix: sparse.csr_matrix,
    pattern_record: Mapping[str, Any],
    numeric_facts: Mapping[str, Any],
    native_result: Mapping[str, Any],
    output_directory: str | Path,
    profile: str,
    q_index: int,
    twist_index: int,
    q_map: sparse.csr_matrix,
    original_h: np.ndarray,
    profile_identity: Mapping[str, Any],
    ordered_modes: Sequence[Any],
    scientific_input_sha256: str,
    operator_identity: Mapping[str, Any],
    matrix_source_identity: Mapping[str, Any],
    execution_identity: Mapping[str, Any],
    producer_identity: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Freeze a COMPLETE selected-q CSR and its separate independent native PASS."""
    from .task40_v30_qualified_q_csr import (
        _require_csr,
        _require_sha,
        _require_source_sha,
    )

    root = Path(output_directory).resolve()
    if (
        not profile
        or type(q_index) is not int
        or q_index < 0
        or type(twist_index) is not int
        or twist_index < 0
        or not sparse.isspmatrix_csr(matrix)
        or matrix.dtype != np.dtype(np.complex128)
        or matrix.indices.dtype != np.dtype(np.int32)
        or matrix.indptr.dtype != np.dtype(np.int32)
        or not matrix.has_canonical_format
        or not matrix.has_sorted_indices
    ):
        raise ValueError("selected-q finalizer requires a finite canonical complex128/int32 CSR")
    try:
        _require_csr(matrix, "selected-q final CSR")
    except ValueError as exc:
        raise ValueError(
            "selected-q finalizer requires a finite canonical complex128/int32 CSR"
        ) from exc
    if (
        native_result.get("status") != "PASS"
        or native_result.get("four_complete_csr_actions_passed") is not True
        or native_result.get("paired_sector_leakage_passed") is not True
        or float(native_result.get("maximum_relative_error", float("inf"))) > _NATIVE_LIMIT
    ):
        raise ValueError("selected-q finalizer refuses missing or failed independent native evidence")
    if numeric_facts.get("numeric_fill_complete") is not True:
        raise ValueError("selected-q finalizer refuses a CSR without a completed numeric fill")
    operator = dict(operator_identity)
    source = dict(matrix_source_identity)
    execution = dict(execution_identity)
    for field in (
        "scientific_input_sha256",
        "profile_identity_sha256",
        "ordered_mode_sha256",
        "q_map_sha256",
        "original_h_sha256",
    ):
        _require_sha(operator.get(field), f"operator_identity.{field}")
    actual_operator = selected_q_operator_identity(
        scientific_input_sha256=scientific_input_sha256,
        profile_identity=profile_identity,
        ordered_modes=ordered_modes,
        q_map=q_map,
        original_h=original_h,
    )
    if operator != actual_operator:
        raise ValueError("selected q operator identity differs from actual profile/modes/map/H/input")
    _require_source_sha(source.get("source_sha"), "matrix_source_identity.source_sha")
    _require_sha(source.get("window_sha256"), "matrix_source_identity.window_sha256")
    _require_source_sha(execution.get("source_sha"), "execution_identity.source_sha")
    _require_sha(execution.get("window_sha256"), "execution_identity.window_sha256")
    manifest_path = root / f"task40_v30_q{q_index}_twist{twist_index}_csr_manifest.json"
    qualification_path = root / f"task40_v30_q{q_index}_twist{twist_index}_native_qualification.json"
    if manifest_path.exists() or qualification_path.exists():
        raise FileExistsError("refusing to replace selected-q COMPLETE or native evidence")
    csr_artifacts = {}
    pattern_artifacts = {}
    source_csr_artifacts = dict(pattern_record.get("csr_artifacts", {}))
    csr_backing_identity: dict[str, Any] = {}
    for key, row in dict(pattern_record.get("csr_artifacts", {})).items():
        artifact = Path(str(row.get("path", ""))).resolve()
        if not artifact.is_file():
            raise FileNotFoundError(f"selected-q CSR array missing: {artifact.name}")
        file_sha256 = _sha256_file(artifact)
        if row.get("bytes") != artifact.stat().st_size:
            raise IOError(f"selected-q CSR array size changed after V17 pattern construction: {artifact.name}")
        if key != "data" and row.get("sha256") != file_sha256:
            raise IOError(f"selected-q V17 structural array changed after pattern construction: {artifact.name}")
        matrix_array_path = _array_memmap_path(getattr(matrix, str(key)))
        if matrix_array_path is None:
            raise ValueError(f"selected-q live {key} array is not the disk-backed V17 array")
        matrix_stat = matrix_array_path.stat()
        artifact_stat = artifact.stat()
        if (matrix_stat.st_dev, matrix_stat.st_ino) != (artifact_stat.st_dev, artifact_stat.st_ino):
            raise ValueError(f"selected-q live {key} array is not backed by its V17 pattern artifact")
        csr_backing_identity[str(key)] = {
            "path": str(artifact),
            "device": int(artifact_stat.st_dev),
            "inode": int(artifact_stat.st_ino),
            "reused_in_place": True,
        }
        csr_artifacts[str(key)] = {
            "path": str(artifact),
            "bytes": int(artifact.stat().st_size),
            "sha256": file_sha256,
            "pattern_sha256": row.get("sha256"),
            "numeric_fill_changed_data": bool(key == "data" and row.get("sha256") != file_sha256),
        }
        pattern_artifacts[str(key)] = {
            "path": str(artifact),
            "bytes": int(row.get("bytes", 0)),
            "sha256": row.get("sha256"),
        }
    if set(csr_artifacts) != {"data", "indices", "indptr"}:
        raise ValueError("selected-q V17 pattern is missing a persisted CSR array")
    expected_arrays = {
        "data": (matrix.data.shape, np.dtype(np.complex128)),
        "indices": (matrix.indices.shape, np.dtype(np.int32)),
        "indptr": (matrix.indptr.shape, np.dtype(np.int32)),
    }
    for name, (shape, dtype) in expected_arrays.items():
        saved = np.load(csr_artifacts[name]["path"], mmap_mode="r", allow_pickle=False)
        if saved.shape != shape or saved.dtype != dtype:
            raise ValueError(f"selected-q persisted {name} array differs from the live CSR")
        if name in source_csr_artifacts and (
            Path(str(source_csr_artifacts[name].get("path", ""))).resolve()
            != Path(csr_artifacts[name]["path"]).resolve()
        ):
            raise ValueError(f"selected-q finalizer attempted to replace the V17 {name} backing array")
        del saved
    if matrix.shape[0] != matrix.shape[1] or matrix.nnz != len(matrix.indices):
        raise ValueError("selected-q disk-backed CSR payload and runtime matrix disagree")
    manifest = {
        "schema": V30_SELECTED_Q_MANIFEST_SCHEMA,
        "status": "COMPLETE_CSR",
        "profile": profile,
        "q_index": q_index,
        "twist_index": twist_index,
        "shape": list(matrix.shape),
        "stored_structural_slots": int(matrix.nnz),
        "csr_index_dtype": matrix.indices.dtype.str,
        "csr_data_dtype": matrix.data.dtype.str,
        "operator_identity": operator,
        "matrix_source_identity": source,
        "execution_identity": execution,
        "csr_artifacts": csr_artifacts,
        "pattern_csr_artifacts": pattern_artifacts,
        "numeric_csr_identity": {
            "csr_content_sha256": _csr_sha256(matrix),
            "array_sha256": {name: row["sha256"] for name, row in csr_artifacts.items()},
            "data_pattern_sha256": pattern_artifacts["data"]["sha256"],
            "data_numeric_sha256": csr_artifacts["data"]["sha256"],
            "numeric_fill_complete": True,
        },
        "csr_backing_identity": csr_backing_identity,
        "v17_csr_arrays_reused_without_copy": all(
            row.get("reused_in_place") is True for row in csr_backing_identity.values()
        ),
        "pattern_record": dict(pattern_record),
        "numeric_fill_facts": dict(numeric_facts),
        "producer_identity": dict(producer_identity),
        "csr_content_sha256": _csr_sha256(matrix),
    }
    _atomic_json(manifest_path, manifest)
    manifest_sha = _sha256_file(manifest_path)

    native_arrays = {}
    evidence_arrays = {
        **{f"input_{name}": value for name, value in dict(native_result.get("inputs", {})).items()},
        **{f"csr_{name}": value for name, value in dict(native_result.get("csr_outputs", {})).items()},
        **{f"native_{name}": value for name, value in dict(native_result.get("native_outputs", {})).items()},
        **{
            f"component_case1_{name}": value
            for name, value in dict(native_result.get("native_components_case1", {})).items()
        },
        "paired_peer_input": native_result.get("paired_peer_input"),
        "paired_peer_native_diagonal": native_result.get("paired_peer_native_diagonal"),
        "paired_peer_native_cross": native_result.get("paired_peer_native_cross"),
        "paired_selected_native_cross": native_result.get("paired_selected_native_cross"),
        "paired_peer_case2_cross": native_result.get("paired_peer_case2_cross"),
    }
    native_root = root / f"task40_v30_q{q_index}_twist{twist_index}_native_arrays"
    for name, value in evidence_arrays.items():
        if value is None:
            continue
        if not name.replace("_", "").isalnum():
            raise ValueError("selected-q native evidence has an unsafe array name")
        native_arrays[name] = _save_array(native_root / f"{name}.npy", np.asarray(value))
    qualification = {
        "schema": V30_SELECTED_Q_NATIVE_SCHEMA,
        "status": "PASS",
        "q_index": q_index,
        "twist_index": twist_index,
        "csr_manifest_sha256": manifest_sha,
        "operator_identity": operator,
        "matrix_source_identity": source,
        "execution_identity": execution,
        "four_complete_csr_actions_passed": True,
        "csr_action_count": 4,
        "paired_sector_leakage_passed": True,
        "paired_sector_leakage": dict(native_result["paired_sector_leakage"]),
        "maximum_relative_error": float(native_result["maximum_relative_error"]),
        "relative_errors": dict(native_result["relative_errors"]),
        "relative_error_limit": _NATIVE_LIMIT,
        "native_component_reassembly_relative": float(
            native_result["first_input_component_reassembly_relative"]
        ),
        "trace_plus_port_reassembly_relative": float(
            native_result["first_input_trace_plus_port_reassembly_relative"]
        ),
        "native_input_seeds": dict(native_result["native_input_seeds"]),
        "native_array_artifacts": native_arrays,
    }
    _atomic_json(qualification_path, qualification)
    selector_entry = {
        "q_index": q_index,
        "twist_index": twist_index,
        "shape": list(matrix.shape),
        "operator_identity": operator,
        "matrix_source_identity": source,
        "execution_identity": execution,
        "csr_manifest": {"path": str(manifest_path), "sha256": manifest_sha},
        "native_qualification": {
            "path": str(qualification_path),
            "sha256": _sha256_file(qualification_path),
            "status": "PASS",
        },
        "manifest_status": "COMPLETE_CSR",
        "qualification_status": "PASS",
        "manifest_sha256": manifest_sha,
        "native_qualification_sha256": _sha256_file(qualification_path),
    }
    return manifest, qualification, selector_entry


def prepare_selected_q_csr_sector(
    *,
    sources_by_q: Mapping[int, Any],
    q_maps_by_q: Mapping[int, sparse.csr_matrix],
    sector_q_indices: tuple[int, int],
    twist_index: int,
    trace_rows_by_q: Mapping[int, int],
    selected_q_indices: Sequence[int],
    action: Any,
    volume_action: Any,
    comm: Any,
    available_sector_matrices: Mapping[int, sparse.csr_matrix],
    allocation_gate: Callable[[str, Mapping[str, Any]], Any],
    profile: str,
    profile_identity: Mapping[str, Any],
    ordered_modes: Sequence[Any],
    original_h: np.ndarray,
    scientific_input_sha256: str,
    operator_identity_by_q: Mapping[int, Mapping[str, Any]],
    matrix_source_identity_by_q: Mapping[int, Mapping[str, Any]],
    execution_identity: Mapping[str, Any],
    producer_identity_by_q: Mapping[int, Mapping[str, Any]],
    output_directory: str | Path,
    saved_native_witness_by_q: Mapping[int, Mapping[str, Any]] | None = None,
    direct_hhat_evidence_by_q: Mapping[int, Mapping[str, Any]] | None = None,
    precomputed_numeric_by_q: Mapping[int, Mapping[str, Any]] | None = None,
) -> tuple[dict[int, sparse.csr_matrix], dict[str, Any]]:
    """Produce only missing q values and persist each with an independent native gate."""
    sector_qs = tuple(int(q) for q in sector_q_indices)
    selected = tuple(int(q) for q in selected_q_indices)
    if (
        len(sector_qs) != 2
        or sector_qs[0] == sector_qs[1]
        or type(twist_index) is not int
        or twist_index < 0
        or len(set(selected)) != len(selected)
        or not selected
        or not set(selected) <= set(sector_qs)
        or set(sources_by_q) != set(selected)
        or set(q_maps_by_q) != set(sector_qs)
        or set(trace_rows_by_q) != set(sector_qs)
        or set(operator_identity_by_q) != set(selected)
        or set(matrix_source_identity_by_q) != set(selected)
        or set(producer_identity_by_q) != set(selected)
        or not callable(allocation_gate)
    ):
        raise ValueError("V30 sector preparation must bind exactly its real missing q branches")
    saved_witnesses = {
        int(q): value for q, value in (saved_native_witness_by_q or {}).items()
    }
    direct_hhat_evidence = {
        int(q): value for q, value in (direct_hhat_evidence_by_q or {}).items()
    }
    precomputed_numeric = {
        int(q): value for q, value in (precomputed_numeric_by_q or {}).items()
    }
    if (
        not set(saved_witnesses) <= set(selected)
        or any(q != 4 for q in saved_witnesses)
        or (saved_witnesses and (sector_qs != (0, 4) or twist_index != 0))
        or not set(direct_hhat_evidence) <= set(selected)
        or any(q != 4 for q in direct_hhat_evidence)
        or not set(precomputed_numeric) <= set(selected)
    ):
        raise ValueError("V30 V26 witness/support reuse is restricted to the accepted q4/q0 twist-0 pair")
    matrices = {int(q): matrix for q, matrix in available_sector_matrices.items()}
    if (
        not set(matrices) <= set(sector_qs)
        or set(matrices).intersection(selected)
        or set(matrices).union(selected) != set(sector_qs)
    ):
        raise ValueError(
            "V30 sector preparation must pair every missing q with its real provider or newly selected peer"
        )
    output_root = Path(output_directory).resolve()
    q_maps = tuple(q_maps_by_q[q] for q in sector_qs)
    prepared: dict[int, sparse.csr_matrix] = {}
    pattern_records: dict[int, dict[str, Any]] = {}
    numeric_facts_by_q: dict[int, dict[str, Any]] = {}
    numeric_pending_by_q: dict[int, dict[str, Any]] = {}
    for q_index in selected:
        q_map = q_maps_by_q[q_index]
        q_directory = output_root / f"q{q_index}_twist{twist_index}"
        if q_index in precomputed_numeric:
            numeric_stage = dict(precomputed_numeric[q_index])
            numeric_pending = dict(numeric_stage.get("numeric_pending", {}))
            matrix = numeric_stage.get("matrix")
            pattern_record = numeric_stage.get("pattern_record")
            numeric_facts = numeric_stage.get("numeric_facts")
            _require_v31_pending_consumer_receipt(
                numeric_stage, consumer_execution_identity=execution_identity
            )
            if (
                numeric_stage.get("status") != "NUMERIC_COMPLETE_NATIVE_PENDING"
                or numeric_pending.get("status") != "NUMERIC_COMPLETE_NATIVE_PENDING"
                or numeric_pending.get("q_index") != q_index
                or numeric_pending.get("twist_index") != twist_index
                or dict(numeric_pending.get("operator_identity", {}))
                != dict(operator_identity_by_q[q_index])
                or not sparse.isspmatrix_csr(matrix)
                or not isinstance(pattern_record, Mapping)
                or not isinstance(numeric_facts, Mapping)
                or numeric_facts.get("numeric_fill_complete") is not True
            ):
                raise ValueError("prebuilt selected-q numeric pending differs from the live sector identity")
            q_directory = Path(str(numeric_stage.get("output_directory", q_directory))).resolve()
        else:
            numeric_stage = prepare_saved_selected_q_numeric_pending(
                source=sources_by_q[q_index],
                q_map=q_map,
                q_index=q_index,
                twist_index=twist_index,
                trace_rows=int(trace_rows_by_q[q_index]),
                allocation_gate=allocation_gate,
                profile=profile,
                operator_identity=operator_identity_by_q[q_index],
                matrix_source_identity=matrix_source_identity_by_q[q_index],
                execution_identity=execution_identity,
                producer_identity=producer_identity_by_q[q_index],
                output_directory=q_directory,
                direct_hhat_evidence=direct_hhat_evidence.get(q_index),
            )
            matrix = numeric_stage["matrix"]
            pattern_record = numeric_stage["pattern_record"]
            numeric_facts = numeric_stage["numeric_facts"]
            numeric_pending = numeric_stage["numeric_pending"]
        numeric_pending_by_q[q_index] = dict(numeric_pending)
        prepared[q_index] = matrix
        matrices[q_index] = matrix
        pattern_records[q_index] = pattern_record
        numeric_facts_by_q[q_index] = numeric_facts

    selector_entries = []
    native_facts = {}
    for q_index in selected:
        branch = sector_qs.index(q_index)
        peer_q_index = sector_qs[1 - branch]
        peer_matrix = matrices.get(peer_q_index)
        if peer_matrix is None:
            raise ValueError("V30 native qualification requires the actual paired-sector CSR")
        operator_identity = dict(operator_identity_by_q[q_index])
        actual_operator_identity = selected_q_operator_identity(
            scientific_input_sha256=scientific_input_sha256,
            profile_identity=profile_identity,
            ordered_modes=ordered_modes,
            q_map=q_maps_by_q[q_index],
            original_h=original_h,
        )
        if operator_identity != actual_operator_identity:
            raise ValueError("V30 prepared q operator identity differs from its actual sector map/H")
        native_stage_records: dict[str, dict[str, Any]] = {}

        def persist_native_stage(
            stage: str,
            arrays: Mapping[str, np.ndarray],
            metadata: Mapping[str, Any],
        ) -> Mapping[str, Any]:
            record = _persist_v30_native_stage(
                output_directory=q_directory,
                q_index=q_index,
                twist_index=twist_index,
                stage=stage,
                arrays=arrays,
                metadata={
                    "operator_identity": dict(operator_identity),
                    "matrix_source_identity": dict(matrix_source_identity_by_q[q_index]),
                    "execution_identity": dict(execution_identity),
                    "producer_identity": dict(producer_identity_by_q[q_index]),
                    "numeric_pending_record": numeric_pending_by_q[q_index],
                    **dict(metadata),
                },
            )
            native_stage_records[stage] = dict(record)
            return record

        try:
            native_result = run_selected_q_native_actions(
                action=action,
                volume_action=volume_action,
                comm=comm,
                q_maps=q_maps,
                q_indices=sector_qs,
                trace_rows_by_q=trace_rows_by_q,
                selected_q_index=q_index,
                twist_index=twist_index,
                matrix=prepared[q_index],
                allocation_gate=allocation_gate,
                peer_matrix=peer_matrix,
                saved_native_witness=saved_witnesses.get(q_index),
                expected_operator_identity=operator_identity,
                expected_current_identity=execution_identity,
                native_stage_callback=persist_native_stage,
                native_stage_identity={
                    "numeric_pending_path": numeric_pending_by_q[q_index].get("record_path"),
                    "numeric_pending_sha256": numeric_pending_by_q[q_index].get("record_sha256"),
                },
            )
        except Exception as exc:
            from .task40_v25_selected_q0 import _write_json

            failure_path = (
                q_directory
                / f"task40_v30_q{q_index}_twist{twist_index}_native_failure.json"
            )
            if failure_path.exists():
                raise FileExistsError(
                    f"refusing to overwrite existing V30 native failure evidence: {failure_path}"
                ) from exc
            _write_json(
                failure_path,
                {
                    "schema": "task40extra.review_v30_selected_q_native_failure.v1",
                    "status": "NATIVE_FAILED_AFTER_NUMERIC_COMPLETE",
                    "q_index": q_index,
                    "twist_index": twist_index,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "numeric_pending_record": numeric_pending_by_q[q_index],
                    "native_stage_records": native_stage_records,
                    "saved_native_array_references": dict(
                        saved_witnesses.get(q_index, {}).get("array_references", {})
                    ),
                },
            )
            raise
        _manifest, qualification, entry = finalize_selected_q_csr(
            matrix=prepared[q_index],
            pattern_record=pattern_records[q_index],
            numeric_facts=numeric_facts_by_q[q_index],
            native_result=native_result,
            output_directory=q_directory,
            profile=profile,
            q_index=q_index,
            twist_index=twist_index,
            q_map=q_maps_by_q[q_index],
            original_h=original_h,
            profile_identity=profile_identity,
            ordered_modes=ordered_modes,
            scientific_input_sha256=scientific_input_sha256,
            operator_identity=operator_identity,
            matrix_source_identity=matrix_source_identity_by_q[q_index],
            execution_identity=execution_identity,
            producer_identity=producer_identity_by_q[q_index],
        )
        if qualification.get("status") != "PASS" or entry.get("manifest_status") != "COMPLETE_CSR":
            raise RuntimeError("V30 selected q did not persist COMPLETE CSR and native PASS")
        selector_entries.append(entry)
        native_facts[str(q_index)] = {
            "status": qualification["status"],
            "four_complete_csr_actions_passed": qualification[
                "four_complete_csr_actions_passed"
            ],
            "paired_sector_leakage_passed": qualification["paired_sector_leakage_passed"],
            "maximum_relative_error": qualification["maximum_relative_error"],
            "csr_manifest_sha256": entry["manifest_sha256"],
            "native_qualification_sha256": entry["native_qualification_sha256"],
            "numeric_pending_path": numeric_pending_by_q[q_index]["record_path"],
            "numeric_pending_sha256": numeric_pending_by_q[q_index]["record_sha256"],
            "native_stage_records": native_stage_records,
        }
    return prepared, {
        "selected_q_indices": list(selected),
        "pattern_facts_by_q": pattern_records,
        "numeric_facts_by_q": numeric_facts_by_q,
        "numeric_pending_by_q": numeric_pending_by_q,
        "native_facts_by_q": native_facts,
        "selector_entries": selector_entries,
        "all_complete_native_pass": len(selector_entries) == len(selected)
        and all(row.get("qualification_status") == "PASS" for row in selector_entries),
    }


def make_v30_q_selector(
    *, profile: str, entries: Sequence[Mapping[str, Any]], q_count: int
) -> dict[str, Any]:
    """Create an all-q selector only after every q is independently complete."""
    rows = [dict(row) for row in entries]
    indices = [row.get("q_index") for row in rows]
    if (
        not profile
        or type(q_count) is not int
        or q_count <= 0
        or len(rows) != q_count
        or set(indices) != set(range(q_count))
        or len(set(indices)) != len(indices)
    ):
        raise ValueError("V30 selector publication requires one COMPLETE native PASS for every q")
    for row in rows:
        if (
            row.get("qualification_status") != "PASS"
            or row.get("manifest_status") != "COMPLETE_CSR"
            or not row.get("manifest_sha256")
            or not row.get("native_qualification_sha256")
        ):
            raise ValueError("V30 selector refuses a q without bound COMPLETE CSR and native PASS")
    return {
        "schema": V30_SELECTED_Q_SELECTOR_SCHEMA,
        "profile": profile,
        "q_csr_entries": sorted(rows, key=lambda row: int(row["q_index"])),
    }


def publish_v30_q_selector(
    path: str | Path,
    *,
    profile: str,
    entries: Sequence[Mapping[str, Any]],
    q_count: int,
) -> dict[str, Any]:
    """Atomically publish the final selector only after every q has COMPLETE evidence."""
    destination = Path(path).resolve()
    if destination.exists():
        raise FileExistsError("refusing to replace an existing V30 all-q selector")
    payload = make_v30_q_selector(profile=profile, entries=entries, q_count=q_count)
    _atomic_json(destination, payload)
    return {
        "path": str(destination),
        "bytes": int(destination.stat().st_size),
        "sha256": _sha256_file(destination),
        "q_count": int(q_count),
        "all_q_complete_native_pass": True,
    }
