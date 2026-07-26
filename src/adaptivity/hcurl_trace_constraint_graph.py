"""Partition-independent algebra for flattened H(curl) trace constraints.

Local-h combines two kinds of relations:

* a hanging fine trace depends on a coarse trace through a rectangular map;
* a Floquet slave depends on a periodic master through a square complex map.

Applying those relations sequentially can leave chained slaves in the global
matrix.  This module instead substitutes every primary relation to physical
root rows before PETSc numbering.  Secondary equations are retained as
mandatory compatibility checks (for example, the periodic image of a hanging
relation).

The graph is deliberately independent of DOLFINx global entity numbering.
Rows are named by immutable physical geometry keys.  It is a component
authority only; a later adapter must bind actual broken-hexa edge/face rows and
cell expansions before a PDE can receive accuracy credit.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import numpy as np
from scipy import sparse


@dataclass(frozen=True, order=True)
class PhysicalTraceRowKey:
    """Canonical identity of one trace coefficient."""

    entity_dimension: int
    entity_geometry_key: tuple[int, ...]
    degree: int
    mode: int

    def __post_init__(self) -> None:
        dimension = int(self.entity_dimension)
        geometry = tuple(map(int, self.entity_geometry_key))
        degree = int(self.degree)
        mode = int(self.mode)
        if dimension not in {1, 2}:
            raise ValueError("H(curl) trace rows must belong to edges or faces")
        if not geometry:
            raise ValueError("physical trace geometry key cannot be empty")
        if degree not in {4, 5, 6}:
            raise ValueError("Task035d trace graph qualifies p4/p5/p6 only")
        if mode < 0:
            raise ValueError("trace mode must be non-negative")
        object.__setattr__(self, "entity_dimension", dimension)
        object.__setattr__(self, "entity_geometry_key", geometry)
        object.__setattr__(self, "degree", degree)
        object.__setattr__(self, "mode", mode)

    def to_tuple(self) -> tuple[Any, ...]:
        return (
            self.entity_dimension,
            self.entity_geometry_key,
            self.degree,
            self.mode,
        )


@dataclass(frozen=True)
class LinearTraceRelation:
    """One block equation ``slave = transform @ master``."""

    kind: str
    slave_rows: tuple[PhysicalTraceRowKey, ...]
    master_rows: tuple[PhysicalTraceRowKey, ...]
    slave_from_master: np.ndarray
    primary: bool = True
    provenance: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        kind = str(self.kind)
        slaves = tuple(self.slave_rows)
        masters = tuple(self.master_rows)
        transform = np.asarray(
            self.slave_from_master,
            dtype=np.complex128,
        )
        if not kind:
            raise ValueError("trace relation kind cannot be empty")
        if not slaves or not masters:
            raise ValueError("trace relation requires slave and master rows")
        if len(set(slaves)) != len(slaves):
            raise ValueError("trace relation contains duplicate slave rows")
        if len(set(masters)) != len(masters):
            raise ValueError("trace relation contains duplicate master rows")
        if transform.shape != (len(slaves), len(masters)):
            raise ValueError("trace relation matrix shape does not match rows")
        if not np.all(np.isfinite(transform)):
            raise ValueError("trace relation contains non-finite coefficients")
        if np.any(
            np.max(np.abs(transform), axis=1)
            <= np.finfo(np.float64).tiny
        ):
            raise ValueError("trace relation contains a zero slave row")
        transform = np.ascontiguousarray(transform)
        transform.setflags(write=False)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "slave_rows", slaves)
        object.__setattr__(self, "master_rows", masters)
        object.__setattr__(self, "slave_from_master", transform)
        object.__setattr__(
            self,
            "provenance",
            MappingProxyType(dict(self.provenance)),
        )


@dataclass(frozen=True)
class RawCellTraceRows:
    """Physical raw trace-row order for one cell or trace patch."""

    physical_cell_key: tuple[int, ...]
    raw_rows: tuple[PhysicalTraceRowKey, ...]

    def __post_init__(self) -> None:
        cell_key = tuple(map(int, self.physical_cell_key))
        rows = tuple(self.raw_rows)
        if not cell_key or not rows:
            raise ValueError("cell trace map requires identity and rows")
        if len(set(rows)) != len(rows):
            raise ValueError("one cell trace contains duplicate raw rows")
        object.__setattr__(self, "physical_cell_key", cell_key)
        object.__setattr__(self, "raw_rows", rows)


@dataclass(frozen=True)
class ConstrainedCellTraceMap:
    """Cell-local expansion from final independent roots to raw trace rows."""

    physical_cell_key: tuple[int, ...]
    raw_rows: tuple[PhysicalTraceRowKey, ...]
    independent_rows: np.ndarray
    full_trace_from_independent: np.ndarray


@dataclass(frozen=True)
class FlattenedTraceConstraintMap:
    """One fully substituted trace graph with no numbered slave rows."""

    raw_rows: tuple[PhysicalTraceRowKey, ...]
    root_rows: tuple[PhysicalTraceRowKey, ...]
    raw_from_independent: np.ndarray | sparse.csr_matrix
    component_gram: np.ndarray | sparse.csr_matrix
    cells: tuple[ConstrainedCellTraceMap, ...]
    audit: Mapping[str, Any]


def _matrix_sha256(
    matrix: np.ndarray | sparse.spmatrix,
) -> str:
    if sparse.issparse(matrix):
        values = sparse.csr_matrix(matrix)
        digest = hashlib.sha256()
        digest.update(
            np.asarray(values.shape, dtype=np.int64).tobytes()
        )
        digest.update(np.ascontiguousarray(values.indptr).view(np.uint8))
        digest.update(np.ascontiguousarray(values.indices).view(np.uint8))
        digest.update(np.ascontiguousarray(values.data).view(np.uint8))
        return digest.hexdigest()
    return hashlib.sha256(
        np.ascontiguousarray(matrix).view(np.uint8)
    ).hexdigest()


def _relation_payload(relation: LinearTraceRelation) -> dict[str, Any]:
    return {
        "kind": relation.kind,
        "primary": bool(relation.primary),
        "slave_rows": [row.to_tuple() for row in relation.slave_rows],
        "master_rows": [row.to_tuple() for row in relation.master_rows],
        "matrix_sha256": _matrix_sha256(relation.slave_from_master),
        "provenance": dict(relation.provenance),
    }


def compose_and_flatten_trace_constraints(
    raw_rows: Sequence[PhysicalTraceRowKey],
    relations: Sequence[LinearTraceRelation],
    *,
    cells: Sequence[RawCellTraceRows] = (),
    compatibility_tolerance: float = 5.0e-11,
) -> FlattenedTraceConstraintMap:
    """Flatten hanging/Floquet relations to physical independent roots."""

    ordered_rows = tuple(sorted(raw_rows))
    if not ordered_rows or len(set(ordered_rows)) != len(ordered_rows):
        raise ValueError("raw physical trace rows must be nonempty and unique")
    row_set = set(ordered_rows)
    relation_rows = tuple(relations)
    tolerance = float(compatibility_tolerance)
    if not np.isfinite(tolerance) or tolerance <= 0.0:
        raise ValueError("constraint compatibility tolerance must be positive")
    producers: dict[
        PhysicalTraceRowKey,
        tuple[tuple[PhysicalTraceRowKey, ...], np.ndarray, str],
    ] = {}
    duplicate_primary_rows = 0
    for relation in relation_rows:
        unknown = (
            set(relation.slave_rows) | set(relation.master_rows)
        ) - row_set
        if unknown:
            raise ValueError(
                "trace relation references rows outside raw universe: "
                f"{sorted(unknown)[:4]}"
            )
        if not relation.primary:
            continue
        for local_row, slave in enumerate(relation.slave_rows):
            coefficients = np.ascontiguousarray(
                relation.slave_from_master[local_row]
            )
            if slave in relation.master_rows:
                self_column = relation.master_rows.index(slave)
                if abs(coefficients[self_column]) > tolerance:
                    raise RuntimeError(
                        f"trace constraint has self dependency: {slave}"
                    )
            existing = producers.get(slave)
            candidate = (
                relation.master_rows,
                coefficients,
                relation.kind,
            )
            if existing is None:
                producers[slave] = candidate
                continue
            same_masters = existing[0] == candidate[0]
            same_values = (
                same_masters
                and np.max(
                    np.abs(existing[1] - candidate[1]),
                    initial=0.0,
                )
                <= tolerance
            )
            if not same_values:
                raise RuntimeError(
                    "trace row has conflicting primary producers: "
                    f"{slave}, {existing[2]} vs {candidate[2]}"
                )
            duplicate_primary_rows += 1

    state: dict[PhysicalTraceRowKey, int] = {}
    cache: dict[
        PhysicalTraceRowKey,
        dict[PhysicalTraceRowKey, complex],
    ] = {}
    depth: dict[PhysicalTraceRowKey, int] = {}
    stack: list[PhysicalTraceRowKey] = []

    def expand(
        row: PhysicalTraceRowKey,
    ) -> dict[PhysicalTraceRowKey, complex]:
        status = state.get(row, 0)
        if status == 2:
            return cache[row]
        if status == 1:
            start = stack.index(row)
            cycle = stack[start:] + [row]
            raise RuntimeError(
                "trace constraint cycle detected: "
                + " -> ".join(map(str, cycle))
            )
        state[row] = 1
        stack.append(row)
        producer = producers.get(row)
        if producer is None:
            values = {row: 1.0 + 0.0j}
            row_depth = 0
        else:
            masters, coefficients, _kind = producer
            values: dict[PhysicalTraceRowKey, complex] = {}
            row_depth = 0
            for master, coefficient in zip(
                masters,
                coefficients,
                strict=True,
            ):
                if abs(coefficient) <= np.finfo(np.float64).tiny:
                    continue
                master_values = expand(master)
                row_depth = max(row_depth, depth[master] + 1)
                for root, root_coefficient in master_values.items():
                    values[root] = (
                        values.get(root, 0.0 + 0.0j)
                        + coefficient * root_coefficient
                    )
            values = {
                root: coefficient
                for root, coefficient in values.items()
                if abs(coefficient) > np.finfo(np.float64).tiny
            }
            if not values:
                raise RuntimeError(
                    f"trace constraint flattened to a zero row: {row}"
                )
        stack.pop()
        state[row] = 2
        cache[row] = values
        depth[row] = row_depth
        return values

    for row in ordered_rows:
        expand(row)
    root_rows = tuple(sorted(row for row in ordered_rows if row not in producers))
    roots_seen = {root for values in cache.values() for root in values}
    if set(root_rows) != roots_seen:
        raise RuntimeError("flattened trace roots do not close")
    root_index = {row: index for index, row in enumerate(root_rows)}
    row_index = {row: index for index, row in enumerate(ordered_rows)}
    coordinate_rows: list[int] = []
    coordinate_columns: list[int] = []
    coordinate_values: list[complex] = []
    for row, values in cache.items():
        for root, coefficient in values.items():
            coordinate_rows.append(row_index[row])
            coordinate_columns.append(root_index[root])
            coordinate_values.append(coefficient)
    sparse_expansion = sparse.coo_matrix(
        (
            np.asarray(coordinate_values, dtype=np.complex128),
            (
                np.asarray(coordinate_rows, dtype=np.int64),
                np.asarray(coordinate_columns, dtype=np.int64),
            ),
        ),
        shape=(len(ordered_rows), len(root_rows)),
    ).tocsr()
    raw_from_independent: np.ndarray | sparse.csr_matrix
    if max(sparse_expansion.shape, default=0) <= 512:
        raw_from_independent = np.ascontiguousarray(
            sparse_expansion.toarray()
        )
    else:
        raw_from_independent = sparse_expansion

    maximum_relation_residual = 0.0
    secondary_relation_count = 0
    relation_residuals: list[dict[str, Any]] = []
    for relation in relation_rows:
        slave_indices = [row_index[row] for row in relation.slave_rows]
        master_indices = [row_index[row] for row in relation.master_rows]
        slave_expansion = raw_from_independent[slave_indices]
        master_expansion = raw_from_independent[master_indices]
        if sparse.issparse(slave_expansion):
            slave_expansion = slave_expansion.toarray()
        if sparse.issparse(master_expansion):
            master_expansion = master_expansion.toarray()
        residual = slave_expansion - (
            relation.slave_from_master @ master_expansion
        )
        error = float(np.max(np.abs(residual), initial=0.0))
        maximum_relation_residual = max(maximum_relation_residual, error)
        secondary_relation_count += not relation.primary
        relation_residuals.append(
            {
                "kind": relation.kind,
                "primary": bool(relation.primary),
                "maximum_residual": error,
            }
        )
        if error > tolerance:
            raise RuntimeError(
                "flattened trace relation is incompatible: "
                f"kind={relation.kind}, residual={error:.6e}"
            )

    constrained_cells: list[ConstrainedCellTraceMap] = []
    cell_hash_rows: list[tuple[Any, ...]] = []
    for cell in sorted(cells, key=lambda row: row.physical_cell_key):
        unknown = set(cell.raw_rows) - row_set
        if unknown:
            raise ValueError(
                "cell trace references rows outside raw universe: "
                f"{sorted(unknown)[:4]}"
            )
        local = raw_from_independent[
            [row_index[row] for row in cell.raw_rows]
        ]
        if sparse.issparse(local):
            local = local.toarray()
        active_columns = np.flatnonzero(
            np.max(np.abs(local), axis=0)
            > np.finfo(np.float64).tiny
        ).astype(np.int64)
        expansion = np.ascontiguousarray(local[:, active_columns])
        if int(np.linalg.matrix_rank(expansion)) != len(active_columns):
            raise RuntimeError(
                "one flattened cell trace expansion is rank deficient"
            )
        active_columns.setflags(write=False)
        expansion.setflags(write=False)
        constrained_cells.append(
            ConstrainedCellTraceMap(
                physical_cell_key=cell.physical_cell_key,
                raw_rows=cell.raw_rows,
                independent_rows=active_columns,
                full_trace_from_independent=expansion,
            )
        )
        cell_hash_rows.append(
            (
                cell.physical_cell_key,
                tuple(map(int, active_columns)),
                _matrix_sha256(expansion),
            )
        )

    gram_product = (
        raw_from_independent.conj().T @ raw_from_independent
    )
    gram: np.ndarray | sparse.csr_matrix
    if sparse.issparse(gram_product):
        gram = sparse.csr_matrix(gram_product)
    else:
        gram = np.ascontiguousarray(gram_product)
    root_indices = [row_index[row] for row in root_rows]
    root_identity = raw_from_independent[root_indices]
    if sparse.issparse(root_identity):
        root_identity = root_identity.toarray()
    root_identity_error = float(
        np.max(
            np.abs(root_identity - np.eye(len(root_rows))),
            initial=0.0,
        )
    )
    gram_rank = len(root_rows) if root_identity_error <= tolerance else 0
    if gram_rank != len(root_rows):
        raise RuntimeError("flattened root rows do not contain an identity block")
    if sparse.issparse(raw_from_independent):
        maximum_row_width = int(
            np.max(
                np.diff(raw_from_independent.indptr),
                initial=0,
            )
        )
    else:
        maximum_row_width = int(
            max(
                (
                    np.count_nonzero(
                        np.abs(raw_from_independent[row]) > tolerance
                    )
                    for row in range(len(ordered_rows))
                ),
                default=0,
            )
        )
    relation_payload = [_relation_payload(row) for row in relation_rows]
    graph_payload = {
        "raw_rows": [row.to_tuple() for row in ordered_rows],
        "root_rows": [row.to_tuple() for row in root_rows],
        "relations": relation_payload,
        "raw_from_independent_sha256": _matrix_sha256(
            raw_from_independent
        ),
        "cells": cell_hash_rows,
    }
    graph_sha256 = hashlib.sha256(
        json.dumps(
            graph_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()
    relation_kind_counts = {
        kind: sum(row.kind == kind for row in relation_rows)
        for kind in sorted({row.kind for row in relation_rows})
    }
    checks = {
        "all_rows_flattened_to_roots": set(root_rows) == roots_seen,
        "no_slave_row_globally_numbered": not set(producers).intersection(
            root_rows
        ),
        "all_relations_compatible": maximum_relation_residual <= tolerance,
        "component_gram_full_rank": gram_rank == len(root_rows),
        "all_cell_expansions_full_rank": True,
    }
    audit = MappingProxyType(
        {
            "schema_version": "task035d.flattened-trace-constraint-map.v1",
            "status": "flattened_trace_constraint_component_pass",
            "pass": True,
            "raw_trace_rows": len(ordered_rows),
            "independent_trace_rows": len(root_rows),
            "primary_slave_rows": len(producers),
            "primary_relation_count": sum(
                relation.primary for relation in relation_rows
            ),
            "secondary_relation_count": secondary_relation_count,
            "duplicate_primary_rows_deduplicated": duplicate_primary_rows,
            "relation_kind_counts": relation_kind_counts,
            "maximum_chain_depth": max(depth.values(), default=0),
            "maximum_flattened_row_width": maximum_row_width,
            "maximum_relation_residual": maximum_relation_residual,
            "relation_residuals": relation_residuals,
            "component_gram_rank": gram_rank,
            "root_identity_error": root_identity_error,
            "expansion_storage": (
                "csr" if sparse.issparse(raw_from_independent) else "dense"
            ),
            "cell_map_count": len(constrained_cells),
            "graph_sha256": graph_sha256,
            "raw_from_independent_sha256": _matrix_sha256(
                raw_from_independent
            ),
            "component_gram_sha256": _matrix_sha256(gram),
            "checks": checks,
            "failures": [],
            "physical_key_numbering": True,
            "chained_slave_rows_globally_numbered": False,
            "hanging_or_periodic_slave_rows_globally_numbered": False,
            "pde_accuracy_credit": False,
            "ordinary_default_changed": False,
        }
    )
    if sparse.issparse(raw_from_independent):
        for values in (
            raw_from_independent.data,
            raw_from_independent.indices,
            raw_from_independent.indptr,
        ):
            values.setflags(write=False)
    else:
        raw_from_independent.setflags(write=False)
    if sparse.issparse(gram):
        for values in (gram.data, gram.indices, gram.indptr):
            values.setflags(write=False)
    else:
        gram.setflags(write=False)
    return FlattenedTraceConstraintMap(
        raw_rows=ordered_rows,
        root_rows=root_rows,
        raw_from_independent=raw_from_independent,
        component_gram=gram,
        cells=tuple(constrained_cells),
        audit=audit,
    )


__all__ = [
    "ConstrainedCellTraceMap",
    "FlattenedTraceConstraintMap",
    "LinearTraceRelation",
    "PhysicalTraceRowKey",
    "RawCellTraceRows",
    "compose_and_flatten_trace_constraints",
]
