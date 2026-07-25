"""Strict structural partitions for the opt-in trace-harmonic prototype.

The exact trace-harmonic block LDU in
:mod:`src.solvers.condensed_trace_harmonic_pc` is useful only when its local
blocks are separated by a *structural* interface.  This module builds that
partition from the actual assembly-time-condensed cell support:

* every owned cell trace is pulled through the complete periodic/Floquet
  ``TraceConstraintMap``;
* the resulting active-row hyperedge is assigned to the cell's physical
  z-region;
* an active row incident to more than one region becomes interface;
* every appended/DtN row is interface;
* the assembled PETSc graph is scanned independently and must contain no
  entry between different local blocks.

The builder is collective and fail closed.  It does not enable a solver
profile or change an ordinary default.  Canonical content hashes are retained
so a future formal record can bind the exact expansion, hypergraph, partition,
and assembled matrix pattern without relying on MPI ownership.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc

from .condensed_trace_harmonic_pc import TraceHarmonicPartition
from .hcurl_assembly_time_condensation import AssemblyTimeCondensedSystem


_H15_ACTIVE_TRACE_ROWS = 16_800
_H15_APPENDED_DTN_ROWS = 80


def _canonical_json_sha256(namespace: str, value: Any) -> str:
    digest = hashlib.sha256()
    digest.update(namespace.encode("ascii"))
    digest.update(b"\0")
    digest.update(
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )
    return digest.hexdigest()


def _canonical_index_list(values: np.ndarray) -> list[int]:
    return [
        int(value)
        for value in np.asarray(values, dtype=np.int64).tolist()
    ]


def _collective_input_error(
    comm: MPI.Comm,
    local_error: str | None,
    *,
    context: str,
) -> None:
    errors = comm.allgather(local_error)
    if not any(error is not None for error in errors):
        return
    error_class = (
        TypeError
        if all(
            error is None or error.startswith("TypeError:")
            for error in errors
        )
        else ValueError
        if all(
            error is None or error.startswith("ValueError:")
            for error in errors
        )
        else RuntimeError
    )
    raise error_class(
        f"{context}: "
        + "; ".join(
            f"rank {rank}: {error}"
            for rank, error in enumerate(errors)
            if error is not None
        )
    )


def _normalize_region_edges(
    region_z_edges: Sequence[float] | np.ndarray,
) -> np.ndarray:
    edges = np.asarray(region_z_edges, dtype=np.float64)
    if edges.ndim != 1 or edges.size < 3:
        raise ValueError(
            "trace-harmonic z partition requires at least two regions"
        )
    if not np.all(np.isfinite(edges)):
        raise ValueError("trace-harmonic z-region edges must be finite")
    if np.any(np.diff(edges) <= 0.0):
        raise ValueError(
            "trace-harmonic z-region edges must be strictly increasing"
        )
    result = edges.copy()
    result.setflags(write=False)
    return result


def _region_for_midpoint(
    midpoint_z: float,
    edges: np.ndarray,
    *,
    tolerance: float,
) -> int:
    if midpoint_z < float(edges[0]) - tolerance or midpoint_z > (
        float(edges[-1]) + tolerance
    ):
        raise ValueError(
            "owned cell midpoint lies outside the declared z-region domain"
        )
    clipped = min(max(float(midpoint_z), float(edges[0])), float(edges[-1]))
    if clipped == float(edges[-1]):
        return int(edges.size - 2)
    return int(np.searchsorted(edges[1:-1], clipped, side="right"))


def _normalize_expansion_row(
    expansion: tuple[np.ndarray, np.ndarray],
    *,
    original_row: int,
    active_rows: int,
) -> tuple[np.ndarray, np.ndarray]:
    if not isinstance(expansion, tuple) or len(expansion) != 2:
        raise TypeError(
            "trace expansion rows must be (active_ids, coefficients) tuples"
        )
    raw_ids, raw_coefficients = expansion
    ids_array = np.asarray(raw_ids)
    coefficients = np.asarray(raw_coefficients, dtype=np.complex128)
    if ids_array.ndim != 1 or coefficients.ndim != 1:
        raise ValueError(
            f"trace expansion for original row {original_row} must be 1D"
        )
    if not np.issubdtype(ids_array.dtype, np.integer):
        raise TypeError(
            f"trace expansion IDs for original row {original_row} "
            "must be integers"
        )
    ids = np.asarray(ids_array, dtype=PETSc.IntType)
    if ids.size == 0 or ids.size != coefficients.size:
        raise ValueError(
            f"trace expansion for original row {original_row} is empty "
            "or has mismatched IDs and coefficients"
        )
    if len(np.unique(ids)) != len(ids):
        raise ValueError(
            f"trace expansion for original row {original_row} has "
            "duplicate active IDs"
        )
    if int(ids.min()) < 0 or int(ids.max()) >= active_rows:
        raise ValueError(
            f"trace expansion for original row {original_row} references "
            "an out-of-range active row"
        )
    if not np.all(
        np.isfinite(coefficients.real) & np.isfinite(coefficients.imag)
    ):
        raise ValueError(
            f"trace expansion for original row {original_row} is non-finite"
        )
    if np.any(coefficients == 0.0):
        raise ValueError(
            f"trace expansion for original row {original_row} contains "
            "an explicit zero coefficient"
        )
    order = np.argsort(ids, kind="stable")
    normalized_ids = np.asarray(ids[order], dtype=PETSc.IntType).copy()
    normalized_coefficients = np.asarray(
        coefficients[order],
        dtype=np.complex128,
    ).copy()
    normalized_ids.setflags(write=False)
    normalized_coefficients.setflags(write=False)
    return normalized_ids, normalized_coefficients


def _expansion_content(
    expansion_by_original: Mapping[
        int,
        tuple[np.ndarray, np.ndarray],
    ],
    *,
    active_rows: int,
) -> tuple[
    dict[int, tuple[np.ndarray, np.ndarray]],
    str,
]:
    normalized: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    payload: list[dict[str, Any]] = []
    raw_keys = list(expansion_by_original)
    for raw_original in raw_keys:
        if isinstance(raw_original, bool) or not isinstance(
            raw_original,
            (int, np.integer),
        ):
            raise TypeError("trace expansion original-row keys must be integers")
    for raw_original in sorted(raw_keys, key=int):
        original = int(raw_original)
        if original < 0:
            raise ValueError("trace expansion original-row keys must be nonnegative")
        ids, coefficients = _normalize_expansion_row(
            expansion_by_original[raw_original],
            original_row=original,
            active_rows=active_rows,
        )
        normalized[original] = (ids, coefficients)
        payload.append(
            {
                "original_row": original,
                "active_rows": _canonical_index_list(ids),
                "coefficients_real_imag": [
                    [float(value.real), float(value.imag)]
                    for value in coefficients
                ],
            }
        )
    if not normalized:
        raise ValueError("trace expansion map must not be empty")
    return normalized, _canonical_json_sha256(
        "task035b.trace-harmonic-expansion.v1",
        payload,
    )


def _matrix_pattern_audit(
    matrix: PETSc.Mat,
    *,
    local_block_by_row: np.ndarray,
    active_rows: int,
    appended_rows: int,
) -> tuple[dict[str, Any], str]:
    comm = matrix.getComm().tompi4py()
    start, end = map(int, matrix.getOwnershipRange())
    local_patterns: list[tuple[int, list[int]]] = []
    local_cross: list[tuple[int, int, int, int]] = []
    local_empty: list[int] = []
    local_appended_active_incidence: set[int] = set()
    local_error: str | None = None
    try:
        for row in range(start, end):
            columns, _values = matrix.getRow(row)
            normalized_columns = np.unique(
                np.asarray(columns, dtype=PETSc.IntType)
            )
            if normalized_columns.size and (
                int(normalized_columns[0]) < 0
                or int(normalized_columns[-1]) >= matrix.getSize()[1]
            ):
                raise RuntimeError(
                    "assembled matrix row contains an out-of-range column"
                )
            if normalized_columns.size == 0:
                local_empty.append(row)
            row_block = (
                int(local_block_by_row[row])
                if row < active_rows
                else -1
            )
            for column in normalized_columns:
                column_int = int(column)
                column_block = (
                    int(local_block_by_row[column_int])
                    if column_int < active_rows
                    else -1
                )
                if (
                    row_block >= 0
                    and column_block >= 0
                    and row_block != column_block
                ):
                    local_cross.append(
                        (row, column_int, row_block, column_block)
                    )
                if row >= active_rows and column_int < active_rows:
                    local_appended_active_incidence.add(row - active_rows)
                elif row < active_rows and column_int >= active_rows:
                    local_appended_active_incidence.add(
                        column_int - active_rows
                    )
            local_patterns.append(
                (row, _canonical_index_list(normalized_columns))
            )
    except Exception as error:
        local_error = f"{type(error).__name__}: {error}"
    _collective_input_error(
        comm,
        local_error,
        context="trace-harmonic assembled-pattern scan failed",
    )

    pattern_packets = comm.allgather(local_patterns)
    patterns = sorted(
        (entry for packet in pattern_packets for entry in packet),
        key=lambda entry: entry[0],
    )
    expected_rows = list(range(matrix.getSize()[0]))
    if [row for row, _columns in patterns] != expected_rows:
        raise RuntimeError(
            "assembled matrix pattern packets do not cover every row exactly once"
        )
    cross_entries = [
        entry
        for packet in comm.allgather(local_cross)
        for entry in packet
    ]
    empty_rows = sorted(
        row for packet in comm.allgather(local_empty) for row in packet
    )
    appended_incidence = {
        int(row)
        for packet in comm.allgather(
            sorted(local_appended_active_incidence)
        )
        for row in packet
    }
    orphan_appended = sorted(set(range(appended_rows)) - appended_incidence)
    if empty_rows:
        raise RuntimeError(
            "assembled condensed matrix has structurally empty rows: "
            f"{empty_rows[:8]}"
        )
    if orphan_appended:
        raise RuntimeError(
            "appended/DtN rows have no active-trace structural support: "
            f"{orphan_appended[:8]}"
        )
    if cross_entries:
        raise RuntimeError(
            "assembled condensed matrix contains a forbidden structural "
            "entry between different trace-harmonic local blocks: "
            f"{cross_entries[:4]}"
        )
    pattern_sha256 = _canonical_json_sha256(
        "task035b.trace-harmonic-assembled-pattern.v1",
        patterns,
    )
    structural_nnz = int(sum(len(columns) for _row, columns in patterns))
    return (
        {
            "schema_version": (
                "task035b.trace-harmonic-assembled-pattern-audit.v1"
            ),
            "matrix_rows": int(matrix.getSize()[0]),
            "structural_nnz": structural_nnz,
            "empty_row_count": 0,
            "appended_rows_with_active_support": len(appended_incidence),
            "orphan_appended_rows": [],
            "cross_local_block_structural_entry_count": 0,
            "cross_local_block_structural_zero_proven": True,
            "scan_semantics": (
                "petsc_stored_column_pattern_independent_of_value_magnitude"
            ),
            "matrix_pattern_sha256": pattern_sha256,
        },
        pattern_sha256,
    )


@dataclass(frozen=True)
class ProductionTraceHarmonicPartition:
    """A hash-bound structural foundation; not a production solver enable."""

    partition: TraceHarmonicPartition
    cell_active_hyperedges: tuple[np.ndarray, ...]
    cell_original_trace_supports: tuple[np.ndarray, ...]
    cell_region_ids: tuple[int, ...]
    cell_midpoint_z: tuple[float, ...]
    region_z_edges: np.ndarray
    active_rows: int
    appended_rows: int
    audit: Mapping[str, Any]

    def __post_init__(self) -> None:
        active_rows = int(self.active_rows)
        appended_rows = int(self.appended_rows)
        if active_rows <= 0 or appended_rows <= 0:
            raise ValueError(
                "production trace-harmonic foundation requires positive "
                "active and appended row counts"
            )
        self.partition.validate_cover(active_rows + appended_rows)
        expected_appended = np.arange(
            active_rows,
            active_rows + appended_rows,
            dtype=PETSc.IntType,
        )
        if not np.all(
            np.isin(expected_appended, self.partition.interface_rows)
        ):
            raise ValueError(
                "every appended/DtN row must belong to the interface"
            )
        if not (
            len(self.cell_active_hyperedges)
            == len(self.cell_original_trace_supports)
            == len(self.cell_region_ids)
            == len(self.cell_midpoint_z)
        ):
            raise ValueError(
                "cell hyperedges, region IDs, and midpoint metadata "
                "must be aligned"
            )
        normalized_edges = _normalize_region_edges(self.region_z_edges)
        normalized_hyperedges: list[np.ndarray] = []
        normalized_original_supports: list[np.ndarray] = []
        for number, raw_edge in enumerate(self.cell_active_hyperedges):
            edge = np.unique(
                np.asarray(raw_edge, dtype=PETSc.IntType)
            )
            if edge.size == 0:
                raise ValueError(f"cell hyperedge {number} is empty")
            if int(edge[0]) < 0 or int(edge[-1]) >= active_rows:
                raise ValueError(
                    f"cell hyperedge {number} contains an out-of-range row"
                )
            edge.setflags(write=False)
            normalized_hyperedges.append(edge)
            original_support = np.unique(
                np.asarray(
                    self.cell_original_trace_supports[number],
                    dtype=PETSc.IntType,
                )
            )
            if original_support.size == 0 or int(original_support[0]) < 0:
                raise ValueError(
                    f"cell original trace support {number} is empty or invalid"
                )
            original_support.setflags(write=False)
            normalized_original_supports.append(original_support)
        region_ids = tuple(int(value) for value in self.cell_region_ids)
        midpoints = tuple(float(value) for value in self.cell_midpoint_z)
        if any(
            region < 0 or region >= normalized_edges.size - 1
            for region in region_ids
        ):
            raise ValueError("cell region ID lies outside the z partition")
        if not np.all(np.isfinite(np.asarray(midpoints, dtype=np.float64))):
            raise ValueError("cell midpoint metadata must be finite")
        audit = dict(self.audit)
        required_true = (
            "foundation_pass",
            "periodic_closed_hyperedges",
            "cross_local_block_structural_zero_proven",
            "all_appended_rows_are_interface",
        )
        if any(audit.get(key) is not True for key in required_true):
            raise ValueError(
                "production trace-harmonic foundation audit is not affirmative"
            )
        if audit.get("production_execution_enabled") is not False:
            raise ValueError(
                "structural foundation may not enable production execution"
            )
        canonical_hashes = audit.get("canonical_hashes")
        if not isinstance(canonical_hashes, Mapping):
            raise ValueError(
                "structural foundation audit requires canonical hashes"
            )
        required_hashes = (
            "trace_expansion_sha256",
            "cell_hypergraph_sha256",
            "partition_sha256",
            "matrix_pattern_sha256",
            "foundation_bundle_sha256",
        )
        for name in required_hashes:
            value = canonical_hashes.get(name)
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
            ):
                raise ValueError(
                    f"structural foundation canonical hash {name} is invalid"
                )
        records = [
            {
                "midpoint_z": midpoint,
                "region": region,
                "active_rows": _canonical_index_list(edge),
                "original_trace_rows": _canonical_index_list(original),
            }
            for edge, original, region, midpoint in zip(
                normalized_hyperedges,
                normalized_original_supports,
                region_ids,
                midpoints,
                strict=True,
            )
        ]
        expected_hypergraph_sha256 = _canonical_json_sha256(
            "task035b.periodic-closed-active-row-hypergraph.v1",
            records,
        )
        partition_payload = {
            "active_rows": active_rows,
            "appended_rows": appended_rows,
            "region_z_edges": [
                float(value) for value in normalized_edges
            ],
            "local_blocks": [
                _canonical_index_list(block)
                for block in self.partition.local_blocks
            ],
            "interface_rows": _canonical_index_list(
                self.partition.interface_rows
            ),
        }
        expected_partition_sha256 = _canonical_json_sha256(
            "task035b.production-trace-harmonic-partition.v1",
            partition_payload,
        )
        if (
            canonical_hashes["cell_hypergraph_sha256"]
            != expected_hypergraph_sha256
            or canonical_hashes["partition_sha256"]
            != expected_partition_sha256
        ):
            raise ValueError(
                "structural foundation canonical hashes do not match its "
                "hypergraph or partition"
            )
        expected_bundle_sha256 = _canonical_json_sha256(
            "task035b.production-trace-harmonic-foundation.v1",
            {
                "trace_expansion_sha256": canonical_hashes[
                    "trace_expansion_sha256"
                ],
                "cell_hypergraph_sha256": expected_hypergraph_sha256,
                "partition_sha256": expected_partition_sha256,
                "matrix_pattern_sha256": canonical_hashes[
                    "matrix_pattern_sha256"
                ],
            },
        )
        if (
            canonical_hashes["foundation_bundle_sha256"]
            != expected_bundle_sha256
        ):
            raise ValueError(
                "structural foundation bundle hash does not match its "
                "component hashes"
            )
        matrix_audit = audit.get("assembled_matrix_pattern_audit")
        if (
            not isinstance(matrix_audit, Mapping)
            or matrix_audit.get("matrix_pattern_sha256")
            != canonical_hashes["matrix_pattern_sha256"]
        ):
            raise ValueError(
                "assembled matrix-pattern audit hash is missing or inconsistent"
            )
        object.__setattr__(
            self,
            "cell_active_hyperedges",
            tuple(normalized_hyperedges),
        )
        object.__setattr__(
            self,
            "cell_original_trace_supports",
            tuple(normalized_original_supports),
        )
        object.__setattr__(self, "cell_region_ids", region_ids)
        object.__setattr__(self, "cell_midpoint_z", midpoints)
        object.__setattr__(self, "region_z_edges", normalized_edges)
        object.__setattr__(self, "active_rows", active_rows)
        object.__setattr__(self, "appended_rows", appended_rows)
        object.__setattr__(self, "audit", MappingProxyType(audit))


def build_production_trace_harmonic_partition(
    condensed: AssemblyTimeCondensedSystem,
    *,
    owned_cell_midpoint_z: Sequence[float] | np.ndarray,
    region_z_edges: Sequence[float] | np.ndarray,
    z_tolerance: float = 1.0e-12,
) -> ProductionTraceHarmonicPartition:
    """Build a periodic-closed partition from actual condensed cell support."""

    if not isinstance(condensed, AssemblyTimeCondensedSystem):
        raise TypeError(
            "trace-harmonic partition requires AssemblyTimeCondensedSystem"
        )
    matrix = condensed.matrix
    comm = matrix.getComm().tompi4py()
    local_error: str | None = None
    local_records: list[dict[str, Any]] = []
    expansion_sha256 = ""
    edges = np.empty(0, dtype=np.float64)
    active_rows = 0
    appended_rows = 0
    normalized_expansion: dict[
        int,
        tuple[np.ndarray, np.ndarray],
    ] = {}
    try:
        if not matrix.isAssembled():
            raise ValueError(
                "trace-harmonic partition requires an assembled reduced matrix"
            )
        matrix_rows, matrix_columns = map(int, matrix.getSize())
        if matrix_rows != matrix_columns:
            raise ValueError("condensed trace-harmonic matrix must be square")
        active_rows = int(condensed.active_rows)
        appended_rows = int(condensed.appended_rows)
        if active_rows <= 0 or appended_rows <= 0:
            raise ValueError(
                "trace-harmonic partition requires positive active and "
                "appended/DtN rows"
            )
        if matrix_rows != active_rows + appended_rows:
            raise ValueError(
                "condensed matrix rows differ from active plus appended rows"
            )
        if (
            int(condensed.trace_constraints.active_rows) != active_rows
            or int(condensed.trace_constraints.full_trace_rows)
            != int(condensed.trace_rows)
        ):
            raise ValueError(
                "condensed system and trace-constraint dimensions disagree"
            )
        if not np.isfinite(z_tolerance) or z_tolerance < 0.0:
            raise ValueError("trace-harmonic z tolerance must be nonnegative")
        edges = _normalize_region_edges(region_z_edges)
        midpoint_z = np.asarray(
            owned_cell_midpoint_z,
            dtype=np.float64,
        )
        if midpoint_z.ndim != 1 or len(midpoint_z) != len(
            condensed.cell_recovery_maps
        ):
            raise ValueError(
                "owned cell midpoint z metadata must be a 1D array aligned "
                "with cell recovery maps"
            )
        if not np.all(np.isfinite(midpoint_z)):
            raise ValueError("owned cell midpoint z metadata must be finite")
        normalized_expansion, expansion_sha256 = _expansion_content(
            condensed.trace_constraints.expansion_by_original,
            active_rows=active_rows,
        )
        for local_cell, (recovery, midpoint) in enumerate(
            zip(
                condensed.cell_recovery_maps,
                midpoint_z,
                strict=True,
            )
        ):
            original_rows = np.asarray(recovery.trace_original_dofs)
            if original_rows.ndim != 1 or not np.issubdtype(
                original_rows.dtype,
                np.integer,
            ):
                raise TypeError(
                    "cell recovery trace original DoFs must be 1D integers"
                )
            originals = np.asarray(
                original_rows,
                dtype=PETSc.IntType,
            )
            if originals.size == 0 or len(np.unique(originals)) != len(
                originals
            ):
                raise ValueError(
                    "cell recovery trace support must be nonempty and unique"
                )
            missing = [
                int(original)
                for original in originals
                if int(original) not in normalized_expansion
            ]
            if missing:
                raise ValueError(
                    "cell recovery trace support is absent from the complete "
                    f"periodic expansion: {missing[:8]}"
                )
            active = np.unique(
                np.concatenate(
                    [
                        normalized_expansion[int(original)][0]
                        for original in originals
                    ]
                )
            ).astype(PETSc.IntType, copy=False)
            if active.size == 0:
                raise ValueError(
                    f"owned cell {local_cell} has an empty active hyperedge"
                )
            region = _region_for_midpoint(
                float(midpoint),
                edges,
                tolerance=float(z_tolerance),
            )
            local_records.append(
                {
                    "midpoint_z": float(midpoint),
                    "region": region,
                    "active_rows": _canonical_index_list(active),
                    "original_trace_rows": _canonical_index_list(
                        np.sort(originals)
                    ),
                }
            )
        expected_cells = condensed.build_audit.get(
            "owned_cell_count_global"
        )
        if expected_cells is not None and (
            isinstance(expected_cells, bool)
            or not isinstance(expected_cells, (int, np.integer))
            or int(expected_cells) <= 0
        ):
            raise ValueError(
                "condensed owned_cell_count_global audit is invalid"
            )
    except Exception as error:
        local_error = f"{type(error).__name__}: {error}"
    _collective_input_error(
        comm,
        local_error,
        context="trace-harmonic partition input validation failed",
    )

    contract_packets = comm.allgather(
        (
            active_rows,
            appended_rows,
            int(condensed.trace_rows),
            edges.tolist(),
            float(z_tolerance),
            expansion_sha256,
            (
                None
                if expected_cells is None
                else int(expected_cells)
            ),
        )
    )
    if any(packet != contract_packets[0] for packet in contract_packets[1:]):
        raise RuntimeError(
            "trace-harmonic partition contract differs across MPI ranks"
        )
    records = [
        record
        for packet in comm.allgather(local_records)
        for record in packet
    ]
    expected_cells = condensed.build_audit.get("owned_cell_count_global")
    if expected_cells is not None and len(records) != int(expected_cells):
        raise RuntimeError(
            "owned cell recovery count differs from the condensed build audit"
        )
    if not records:
        raise ValueError(
            "trace-harmonic partition requires at least one owned cell globally"
        )
    records.sort(
        key=lambda record: (
            record["region"],
            record["midpoint_z"],
            record["active_rows"],
            record["original_trace_rows"],
        )
    )
    globally_supported_originals = {
        int(original)
        for record in records
        for original in record["original_trace_rows"]
    }
    expansion_originals = set(normalized_expansion)
    if globally_supported_originals != expansion_originals:
        missing_cell_support = sorted(
            expansion_originals - globally_supported_originals
        )
        unknown_cell_support = sorted(
            globally_supported_originals - expansion_originals
        )
        raise ValueError(
            "cell support and the complete trace expansion original-row "
            "domains differ: "
            f"without_cell_support={missing_cell_support[:8]}, "
            f"without_expansion={unknown_cell_support[:8]}"
        )
    region_count = int(edges.size - 1)
    cells_per_region = [0] * region_count
    incident_regions: list[set[int]] = [
        set() for _row in range(active_rows)
    ]
    for record in records:
        region = int(record["region"])
        cells_per_region[region] += 1
        for row in record["active_rows"]:
            incident_regions[int(row)].add(region)
    empty_regions = [
        region
        for region, count in enumerate(cells_per_region)
        if count == 0
    ]
    if empty_regions:
        raise ValueError(
            "trace-harmonic z partition has regions with no owned-cell "
            f"support: {empty_regions}"
        )
    orphan_active = [
        row
        for row, regions in enumerate(incident_regions)
        if not regions
    ]
    if orphan_active:
        raise ValueError(
            "periodic-closed cell hypergraph does not cover every active row; "
            f"orphan rows {orphan_active[:8]}"
        )

    local_blocks: list[np.ndarray] = []
    local_block_by_row = np.full(active_rows, -1, dtype=np.int64)
    interface_active: list[int] = []
    for row, regions in enumerate(incident_regions):
        if len(regions) > 1:
            interface_active.append(row)
        else:
            region = next(iter(regions))
            local_block_by_row[row] = region
    for region in range(region_count):
        block = np.flatnonzero(local_block_by_row == region).astype(
            PETSc.IntType,
            copy=False,
        )
        if block.size == 0:
            raise ValueError(
                "trace-harmonic z region has no strictly local active rows; "
                f"region {region} cannot define a dense local block"
            )
        local_blocks.append(block)
    interface_rows = np.concatenate(
        (
            np.asarray(interface_active, dtype=PETSc.IntType),
            np.arange(
                active_rows,
                active_rows + appended_rows,
                dtype=PETSc.IntType,
            ),
        )
    )
    if interface_rows.size == 0:
        raise ValueError("trace-harmonic interface must not be empty")
    partition = TraceHarmonicPartition(
        local_blocks=tuple(local_blocks),
        interface_rows=interface_rows,
    )
    partition.validate_cover(active_rows + appended_rows)

    hyperedge_crossings: list[dict[str, Any]] = []
    for cell, record in enumerate(records):
        block_ids = sorted(
            {
                int(local_block_by_row[row])
                for row in record["active_rows"]
                if int(local_block_by_row[row]) >= 0
            }
        )
        if len(block_ids) > 1:
            hyperedge_crossings.append(
                {"cell": cell, "local_blocks": block_ids}
            )
    if hyperedge_crossings:
        raise RuntimeError(
            "periodic-closed cell hyperedge spans different local blocks: "
            f"{hyperedge_crossings[:4]}"
        )

    matrix_audit, matrix_pattern_sha256 = _matrix_pattern_audit(
        matrix,
        local_block_by_row=local_block_by_row,
        active_rows=active_rows,
        appended_rows=appended_rows,
    )
    hypergraph_sha256 = _canonical_json_sha256(
        "task035b.periodic-closed-active-row-hypergraph.v1",
        records,
    )
    partition_payload = {
        "active_rows": active_rows,
        "appended_rows": appended_rows,
        "region_z_edges": [float(value) for value in edges],
        "local_blocks": [
            _canonical_index_list(block) for block in local_blocks
        ],
        "interface_rows": _canonical_index_list(interface_rows),
    }
    partition_sha256 = _canonical_json_sha256(
        "task035b.production-trace-harmonic-partition.v1",
        partition_payload,
    )
    bundle_sha256 = _canonical_json_sha256(
        "task035b.production-trace-harmonic-foundation.v1",
        {
            "trace_expansion_sha256": expansion_sha256,
            "cell_hypergraph_sha256": hypergraph_sha256,
            "partition_sha256": partition_sha256,
            "matrix_pattern_sha256": matrix_pattern_sha256,
        },
    )
    audit: dict[str, Any] = {
        "schema_version": (
            "task035b.production-trace-harmonic-partition-builder.v1"
        ),
        "status": "structural_foundation_qualified_execution_disabled",
        "foundation_pass": True,
        "row_space": "active_condensed_trace_plus_appended_dtn",
        "active_rows": active_rows,
        "appended_rows": appended_rows,
        "matrix_rows": active_rows + appended_rows,
        "owned_cell_count_global": len(records),
        "region_count": region_count,
        "region_z_edges": [float(value) for value in edges],
        "cells_per_region": cells_per_region,
        "local_block_dimensions": [
            int(block.size) for block in local_blocks
        ],
        "active_interface_dimension": len(interface_active),
        "interface_dimension": int(interface_rows.size),
        "periodic_closed_hyperedges": True,
        "hyperedge_mapping": (
            "owned_cell_original_trace_support_through_complete_"
            "trace_constraint_expansion"
        ),
        "all_active_rows_have_cell_support": True,
        "all_expansion_original_rows_have_cell_support": True,
        "orphan_active_rows": [],
        "all_appended_rows_are_interface": True,
        "hyperedge_cross_local_block_count": 0,
        "cross_local_block_structural_zero_proven": True,
        "assembled_matrix_pattern_audit": matrix_audit,
        "canonical_hashes": {
            "trace_expansion_sha256": expansion_sha256,
            "cell_hypergraph_sha256": hypergraph_sha256,
            "partition_sha256": partition_sha256,
            "matrix_pattern_sha256": matrix_pattern_sha256,
            "foundation_bundle_sha256": bundle_sha256,
        },
        "hashes_are_mpi_ownership_independent": True,
        "production_execution_enabled": False,
        "candidate_promotion": False,
        "ordinary_default_changed": False,
    }
    return ProductionTraceHarmonicPartition(
        partition=partition,
        cell_active_hyperedges=tuple(
            np.asarray(record["active_rows"], dtype=PETSc.IntType)
            for record in records
        ),
        cell_original_trace_supports=tuple(
            np.asarray(
                record["original_trace_rows"],
                dtype=PETSc.IntType,
            )
            for record in records
        ),
        cell_region_ids=tuple(int(record["region"]) for record in records),
        cell_midpoint_z=tuple(
            float(record["midpoint_z"]) for record in records
        ),
        region_z_edges=edges,
        active_rows=active_rows,
        appended_rows=appended_rows,
        audit=audit,
    )


def estimate_h15_exact_dense_trace_harmonic_storage(
    partition: TraceHarmonicPartition,
    *,
    mpi_size: int = 8,
    active_rows: int = _H15_ACTIVE_TRACE_ROWS,
    appended_rows: int = _H15_APPENDED_DTN_ROWS,
    scalar_bytes: int = 16,
    pivot_bytes: int = 4,
) -> Mapping[str, Any]:
    """Derive the retained storage of the current exact dense block LDU.

    The h15 row authority is fixed at 16,800 active trace rows plus 80
    appended DtN rows.  The estimate is a dimension-derived storage ledger,
    not process RSS and not a measured peak.  The current exact implementation
    retains each local dense LU, both ``H=-A_ii^-1 A_iΓ`` and ``A_Γi``, and a
    dense interface matrix plus dense interface LU on every rank.
    """

    mpi_size = int(mpi_size)
    active_rows = int(active_rows)
    appended_rows = int(appended_rows)
    scalar_bytes = int(scalar_bytes)
    pivot_bytes = int(pivot_bytes)
    if mpi_size <= 0 or scalar_bytes <= 0 or pivot_bytes <= 0:
        raise ValueError(
            "MPI size and scalar/pivot storage widths must be positive"
        )
    if (
        active_rows != _H15_ACTIVE_TRACE_ROWS
        or appended_rows != _H15_APPENDED_DTN_ROWS
    ):
        raise ValueError(
            "h15 trace-harmonic estimator requires the qualified "
            "16800 active plus 80 appended row authority"
        )
    matrix_rows = active_rows + appended_rows
    partition.validate_cover(matrix_rows)
    appended = np.arange(
        active_rows,
        matrix_rows,
        dtype=PETSc.IntType,
    )
    if not np.all(np.isin(appended, partition.interface_rows)):
        raise ValueError(
            "h15 estimator requires every appended row in the interface"
        )
    dimensions = [int(block.size) for block in partition.local_blocks]
    interface_dimension = int(partition.interface_rows.size)
    local_total_dimension = int(sum(dimensions))
    if local_total_dimension + interface_dimension != matrix_rows:
        raise RuntimeError("h15 partition dimensions do not close")

    owners = partition.owners_for_size(mpi_size)
    local_lu_values = int(sum(n * n * scalar_bytes for n in dimensions))
    local_lu_pivots = int(sum(n * pivot_bytes for n in dimensions))
    stored_harmonic = int(
        local_total_dimension * interface_dimension * scalar_bytes
    )
    stored_lower = stored_harmonic
    rank_local_bytes = [0] * mpi_size
    for dimension, owner in zip(dimensions, owners, strict=True):
        rank_local_bytes[owner] += int(
            dimension * dimension * scalar_bytes
            + dimension * pivot_bytes
            + 2 * dimension * interface_dimension * scalar_bytes
        )

    coarse_matrix_per_rank = int(
        interface_dimension * interface_dimension * scalar_bytes
    )
    coarse_lu_per_rank = int(
        interface_dimension * interface_dimension * scalar_bytes
        + interface_dimension * pivot_bytes
    )
    interface_vector_per_rank = int(interface_dimension * scalar_bytes)
    replicated_per_rank = int(
        coarse_matrix_per_rank
        + coarse_lu_per_rank
        + interface_vector_per_rank
    )
    retained_total = int(
        local_lu_values
        + local_lu_pivots
        + stored_harmonic
        + stored_lower
        + mpi_size * replicated_per_rank
    )
    rank_retained = [
        int(local_bytes + replicated_per_rank)
        for local_bytes in rank_local_bytes
    ]
    local_lu_factor_flops = float(
        sum((2.0 / 3.0) * dimension**3 for dimension in dimensions)
    )
    replicated_interface_lu_flops = float(
        mpi_size * (2.0 / 3.0) * interface_dimension**3
    )
    audit = {
        "schema_version": (
            "task035b.h15-exact-dense-trace-harmonic-storage-estimate.v1"
        ),
        "status": "controlled_negative_exact_dense_retained_storage",
        "classification": "controlled_negative",
        "estimate_class": "derived_from_partition_dimensions_not_measured_rss",
        "h15_authority": {
            "active_trace_rows": active_rows,
            "appended_dtn_rows": appended_rows,
            "matrix_rows": matrix_rows,
        },
        "mpi_size": mpi_size,
        "local_block_dimensions": dimensions,
        "interface_dimension": interface_dimension,
        "resolved_block_owners": list(owners),
        "storage_widths": {
            "complex_scalar_bytes": scalar_bytes,
            "pivot_index_bytes": pivot_bytes,
        },
        "retained_storage_bytes": {
            "local_dense_lu_values_total": local_lu_values,
            "local_dense_lu_pivots_total": local_lu_pivots,
            "stored_harmonic_extensions_total": stored_harmonic,
            "stored_lower_couplings_total": stored_lower,
            "replicated_interface_matrix_per_rank": (
                coarse_matrix_per_rank
            ),
            "replicated_interface_lu_per_rank": coarse_lu_per_rank,
            "replicated_interface_vector_per_rank": (
                interface_vector_per_rank
            ),
            "replicated_interface_storage_rank_sum": int(
                mpi_size * replicated_per_rank
            ),
            "rank_retained_by_owner": rank_retained,
            "maximum_rank_retained": int(max(rank_retained)),
            "retained_rank_sum_total": retained_total,
        },
        "retained_storage_gib": {
            "maximum_rank_retained": float(
                max(rank_retained) / 1024**3
            ),
            "retained_rank_sum_total": float(retained_total / 1024**3),
        },
        "dense_factorization_work_estimate": {
            "local_lu_flops_sum": local_lu_factor_flops,
            "replicated_interface_lu_flops_sum": (
                replicated_interface_lu_flops
            ),
        },
        "retained_factor_semantics": [
            "exact_dense_local_block_lu",
            "stored_dense_harmonic_extension_H",
            "stored_dense_interface_to_local_lower_coupling",
            "replicated_dense_interface_matrix",
            "replicated_dense_interface_lu",
        ],
        "global_sparse_direct_factor_nnz": 0,
        "strictly_factorless": False,
        "production_execution_enabled": False,
        "candidate_promotion": False,
        "controlled_negative_reasons": [
            "exact dense local LU has cubic setup work",
            "stored H and lower couplings scale as local_rows_times_interface",
            "dense interface matrix and LU scale quadratically and are "
            "replicated on every MPI rank",
            "the profile is not factor-free and does not establish the "
            "future 0.7 nm memory envelope",
        ],
        "formal_partition_hash_required_for_resource_claim": True,
        "measured_process_memory": False,
        "ordinary_default_changed": False,
    }
    return MappingProxyType(audit)


__all__ = [
    "ProductionTraceHarmonicPartition",
    "build_production_trace_harmonic_partition",
    "estimate_h15_exact_dense_trace_harmonic_storage",
]
