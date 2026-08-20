"""Layer-aware sparse block action for the Task39 V8 graph audit.

The operator keeps the original distributed matrix layout.  Each local block
owns only the rows owned by that MPI rank and the selected layer columns. Six
distributed layer workspaces are shared by the sixteen D/L/U blocks; a
``VecScatter`` gathers each layer once and scatters each layer result back with
additive insertion. The source matrix and the system that produced it are
borrowed.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

__all__ = (
    "LayerBlockOperator",
    "build_real_layer_labels",
    "build_layer_block_operator",
    "minimum_layer_labels",
)


def minimum_layer_labels(
    local_labels: np.ndarray, global_rows: int, comm: MPI.Intracomm
) -> np.ndarray:
    sentinel = np.iinfo(np.int32).max
    local = np.asarray(local_labels, dtype=np.int32)
    if local.shape != (int(global_rows),) or not local.flags.c_contiguous:
        raise ValueError("V6 layer label buffer shape is invalid")
    if np.any((local < 0) & (local != sentinel)):
        raise ValueError("V6 layer label is outside the global row space")
    labels = np.full(int(global_rows), sentinel, dtype=np.int32)
    comm.Allreduce(local, labels, op=MPI.MIN)
    if np.any(labels == sentinel):
        raise ValueError("V6 layer graph does not cover every active F row")
    return labels


def build_real_layer_labels(
    matrix: PETSc.Mat, system: Any
) -> tuple[np.ndarray, dict[str, Any]]:
    """Build the deterministic assembly-time trace-row layer mapping.

    Cell geometry and the retained cell recovery/constraint maps are the
    authority.  A trace row shared by cells is assigned the minimum incident
    z-layer.  Only the compact int32 label array is reduced across MPI.
    """

    condensed = system.static_condensation.condensed
    constraints = condensed.trace_constraints
    z_values = np.asarray(system.local_mesh.z_values, dtype=np.float64)
    if z_values.ndim != 1 or len(z_values) < 2 or np.any(np.diff(z_values) <= 0):
        raise ValueError("layer mapping requires a strictly ordered z axis")
    global_rows = int(matrix.getSize()[0])
    sentinel = np.iinfo(np.int32).max
    partial = np.full(global_rows, sentinel, dtype=np.int32)
    geometry = system.local_mesh.mesh.geometry
    for cell, recovery in enumerate(condensed.cell_recovery_maps):
        geometry_indices = np.asarray(geometry.dofmap[cell], dtype=np.int64)
        centroid_z = float(np.mean(geometry.x[geometry_indices, 2]))
        layer = int(np.searchsorted(z_values, centroid_z, side="right") - 1)
        if layer < 0 or layer >= len(z_values) - 1:
            raise ValueError("cell centroid is outside the real z-layer axis")
        for original in recovery.trace_original_dofs:
            expansion = constraints.expansion_by_original.get(int(original))
            if expansion is None:
                raise ValueError("trace row has no assembly-time expansion")
            active_ids = np.asarray(expansion[0], dtype=np.int64)
            for active_id in active_ids:
                active = int(active_id)
                if active < 0 or active >= global_rows:
                    raise ValueError("active trace row is outside F")
                partial[active] = min(partial[active], layer)
    comm = matrix.getComm().tompi4py()
    labels = minimum_layer_labels(partial, global_rows, comm)
    metadata = {
        "z_layer_boundaries": [float(value) for value in z_values],
        "mapping_source": (
            "owned_cell_recovery_maps + trace_constraints.expansion_by_original "
            "+ local_mesh.geometry.z_values"
        ),
        "shared_trace_row_rule": "minimum_incident_owned_cell_layer",
    }
    del partial
    return labels, metadata


def _hash_array(hasher: Any, values: np.ndarray) -> None:
    raw = np.asarray(values)
    hasher.update(str(raw.dtype).encode("ascii"))
    hasher.update(np.asarray(raw.shape, dtype=np.int64).tobytes())
    view = np.ascontiguousarray(raw).view(np.uint8)
    for start in range(0, view.size, 1 << 20):
        hasher.update(view[start : start + (1 << 20)])


def _csr_hash(
    row_ptr: np.ndarray, columns: np.ndarray, values: np.ndarray
) -> tuple[str, int]:
    hasher = hashlib.sha256()
    _hash_array(hasher, row_ptr)
    _hash_array(hasher, columns)
    _hash_array(hasher, values)
    return hasher.hexdigest(), int(row_ptr.nbytes + columns.nbytes + values.nbytes)


@dataclass
class _LayerBlock:
    name: str
    row_layer: int
    column_layer: int
    rows_owned_local: int
    columns_owned_local: int
    matrix: PETSc.Mat
    local_nnz: int
    csr_bytes: int
    local_hash: str

    def destroy(self) -> None:
        self.matrix.destroy()


@dataclass
class _LayerWorkspace:
    layer: int
    x: PETSc.Vec
    y: PETSc.Vec
    temp: PETSc.Vec
    scatter: PETSc.Scatter

    def destroy(self) -> None:
        self.scatter.destroy()
        self.temp.destroy()
        self.y.destroy()
        self.x.destroy()


class LayerBlockOperator:
    """Distributed sparse ``D_i/L_i/U_i`` action over the original F layout."""

    def __init__(
        self,
        matrix: PETSc.Mat,
        global_layer_labels: np.ndarray,
        *,
        layer_count: int,
        mapping_metadata: dict[str, Any] | None = None,
    ) -> None:
        self._matrix = matrix
        self._comm = matrix.getComm().tompi4py()
        self._destroyed = False
        global_rows, global_cols = map(int, matrix.getSize())
        if global_rows != global_cols:
            raise ValueError("layer block operator requires a square F")
        labels = np.asarray(global_layer_labels, dtype=np.int32)
        if labels.shape != (global_rows,) or np.any(labels < 0):
            raise ValueError("global layer labels do not match F")
        if np.any(labels >= int(layer_count)):
            raise ValueError("global layer label exceeds layer count")
        self._labels = np.array(labels, dtype=np.int32, copy=True)
        self._layer_count = int(layer_count)
        self._permutation = np.argsort(self._labels, kind="stable").astype(
            PETSc.IntType, copy=False
        )
        self._inverse_permutation = np.empty_like(self._permutation)
        self._inverse_permutation[self._permutation] = np.arange(
            global_rows, dtype=PETSc.IntType
        )
        row_start, row_end = map(int, matrix.getOwnershipRange())
        local_labels = self._labels[row_start:row_end]
        self._row_ids_by_layer = tuple(
            np.flatnonzero(local_labels == layer).astype(PETSc.IntType) + row_start
            for layer in range(self._layer_count)
        )
        self._column_ids_by_layer = self._row_ids_by_layer
        self._parent_template = matrix.createVecRight()
        self._layer_is: tuple[PETSc.IS, ...] = tuple(
            PETSc.IS().createGeneral(ids, comm=matrix.getComm())
            for ids in self._column_ids_by_layer
        )
        self._blocks: list[_LayerBlock] = []
        self._workspaces: list[_LayerWorkspace] = []
        self._diagnostics = {
            "status": "construction_failed",
            "construction_marker": "started",
            "destroy_marker": "pending",
        }
        try:
            row_ptr, columns, values = matrix.getValuesCSR()
            self._graph = self._graph_stats(row_ptr, columns)
            self._original_nnz_local = int(len(columns))
            self._original_nnz_global = int(
                self._comm.allreduce(self._original_nnz_local, op=MPI.SUM)
            )
            for row_layer, column_layer, name in self._block_specs():
                self._blocks.append(self._build_block(row_layer, column_layer, name))
            self._workspaces = [
                self._build_workspace(layer) for layer in range(self._layer_count)
            ]
            self._diagnostics = self._make_diagnostics(
                mapping_metadata=mapping_metadata or {},
            )
        except Exception:
            self.destroy()
            raise

    def _block_specs(self):
        for layer in range(self._layer_count):
            yield layer, layer, f"D_{layer}"
        for layer in range(self._layer_count - 1):
            yield layer + 1, layer, f"L_{layer + 1}"
        for layer in range(self._layer_count - 1):
            yield layer, layer + 1, f"U_{layer}"

    def _build_block(self, row_layer: int, column_layer: int, name: str) -> _LayerBlock:
        row_ids = self._row_ids_by_layer[row_layer]
        column_ids = self._column_ids_by_layer[column_layer]
        submatrix = self._matrix.createSubMatrix(
            self._layer_is[row_layer], self._layer_is[column_layer]
        )
        row_ptr, columns, values = submatrix.getValuesCSR()
        local_hash, csr_bytes = _csr_hash(row_ptr, columns, values)
        return _LayerBlock(
            name=name,
            row_layer=row_layer,
            column_layer=column_layer,
            rows_owned_local=len(row_ids),
            columns_owned_local=len(column_ids),
            matrix=submatrix,
            local_nnz=int(len(columns)),
            csr_bytes=csr_bytes,
            local_hash=local_hash,
        )

    def _build_workspace(self, layer: int) -> _LayerWorkspace:
        diagonal = self._blocks[layer].matrix
        x = diagonal.createVecRight()
        y = diagonal.createVecLeft()
        temp = y.duplicate()
        local_start, local_end = map(int, x.getOwnershipRange())
        layer_positions = PETSc.IS().createStride(
            local_end - local_start,
            first=local_start,
            step=1,
            comm=self._matrix.getComm(),
        )
        try:
            scatter = PETSc.Scatter().create(
                self._parent_template,
                self._layer_is[layer],
                x,
                layer_positions,
            )
        except Exception:
            temp.destroy()
            y.destroy()
            x.destroy()
            raise
        finally:
            layer_positions.destroy()
        return _LayerWorkspace(layer=layer, x=x, y=y, temp=temp, scatter=scatter)

    def _graph_stats(self, row_ptr: np.ndarray, columns: np.ndarray) -> dict[str, Any]:
        local_labels = self._labels[
            self._matrix.getOwnershipRange()[0] : self._matrix.getOwnershipRange()[1]
        ]
        pair = np.zeros((self._layer_count, self._layer_count), dtype=np.int64)
        rows = np.bincount(local_labels, minlength=self._layer_count).astype(np.int64)
        same = adjacent = long_range = bandwidth = 0
        for local_row, row_layer in enumerate(local_labels):
            cols = columns[row_ptr[local_row] : row_ptr[local_row + 1]]
            col_layers = self._labels[cols]
            deltas = np.abs(col_layers - int(row_layer))
            np.add.at(pair[int(row_layer)], col_layers, 1)
            same += int(np.count_nonzero(deltas == 0))
            adjacent += int(np.count_nonzero(deltas == 1))
            long_range += int(np.count_nonzero(deltas > 1))
            if len(deltas):
                bandwidth = max(bandwidth, int(np.max(deltas)))
        pair = np.asarray(self._comm.allreduce(pair, op=MPI.SUM))
        rows = np.asarray(self._comm.allreduce(rows, op=MPI.SUM))
        classes = np.asarray(
            self._comm.allreduce(
                np.asarray([same, adjacent, long_range], dtype=np.int64),
                op=MPI.SUM,
            )
        )
        bandwidth = int(self._comm.allreduce(bandwidth, op=MPI.MAX))
        total = int(np.sum(pair))
        return {
            "rows_global": int(np.sum(rows)),
            "rows_by_layer": [int(value) for value in rows],
            "layer_pair_nnz": pair.tolist(),
            "nnz_total": total,
            "same_layer_nnz": int(classes[0]),
            "adjacent_layer_nnz": int(classes[1]),
            "long_range_nnz": int(classes[2]),
            "block_half_bandwidth": bandwidth,
        }

    def _make_diagnostics(self, *, mapping_metadata: dict[str, Any]) -> dict[str, Any]:
        local_rows = [len(ids) for ids in self._row_ids_by_layer]
        ownership = self._comm.allgather(local_rows)
        block_records: dict[str, Any] = {}
        for block in self._blocks:
            global_nnz = int(self._comm.allreduce(block.local_nnz, op=MPI.SUM))
            global_csr_bytes = int(self._comm.allreduce(block.csr_bytes, op=MPI.SUM))
            hashes = self._comm.allgather(block.local_hash)
            rank_inventory = self._comm.allgather(
                {
                    "rank": self._comm.rank,
                    "rows_owned_local": block.rows_owned_local,
                    "columns_owned_local": block.columns_owned_local,
                    "nnz_local": block.local_nnz,
                    "csr_bytes_local": block.csr_bytes,
                    "hash": block.local_hash,
                }
            )
            hash_bytes = json.dumps(hashes, separators=(",", ":")).encode()
            block_records[block.name] = {
                "row_layer": block.row_layer,
                "column_layer": block.column_layer,
                "rows_owned_local": block.rows_owned_local,
                "columns_owned_local": block.columns_owned_local,
                "rows_global": self._graph["rows_by_layer"][block.row_layer],
                "nnz_local": block.local_nnz,
                "nnz_global": global_nnz,
                "csr_bytes_local": block.csr_bytes,
                "csr_bytes_global": global_csr_bytes,
                "per_rank": rank_inventory,
                "hash": hashlib.sha256(hash_bytes).hexdigest(),
            }
        block_nnz = sum(record["nnz_global"] for record in block_records.values())
        return {
            "status": "measured",
            "layer_count": self._layer_count,
            "row_coverage_exact": bool(
                sum(self._graph["rows_by_layer"]) == self._graph["rows_global"]
                and all(value >= 0 for value in self._graph["rows_by_layer"])
            ),
            "per_layer_ownership": ownership,
            "layer_workspace_count": len(self._workspaces),
            "layer_workspace_layouts": [
                {
                    "layer": workspace.layer,
                    "global_size": workspace.x.getSize(),
                    "local_size": workspace.x.getLocalSize(),
                    "ownership_range": list(map(int, workspace.x.getOwnershipRange())),
                }
                for workspace in self._workspaces
            ],
            "permutation_hash": hashlib.sha256(self._permutation.tobytes()).hexdigest(),
            "inverse_permutation_hash": hashlib.sha256(
                self._inverse_permutation.tobytes()
            ).hexdigest(),
            "blocks": block_records,
            "nnz_partition": {
                "original_f_global": self._original_nnz_global,
                "diagonal_and_adjacent_blocks_global": block_nnz,
                "partition_exact": block_nnz == self._original_nnz_global,
            },
            "graph": self._graph,
            "long_range_nnz": self._graph["long_range_nnz"],
            "block_half_bandwidth": self._graph["block_half_bandwidth"],
            "construction_marker": "completed",
            "destroy_marker": "pending",
            "borrowed_f_matrix": True,
            "factor_count": 0,
            "qep_count": 0,
            "outer_ksp_count": 0,
            **mapping_metadata,
        }

    @property
    def diagnostics(self) -> dict[str, Any]:
        return self._diagnostics

    @property
    def destroyed(self) -> bool:
        return self._destroyed

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self._destroyed:
            raise RuntimeError("layer block operator has been destroyed")
        if source.getSize() != self._matrix.getSize()[1]:
            raise ValueError("source vector does not match F layout")
        if target.getSize() != self._matrix.getSize()[0]:
            raise ValueError("target vector does not match F layout")
        target.set(0.0)
        for workspace in self._workspaces:
            workspace.scatter.scatter(
                source,
                workspace.x,
                addv=PETSc.InsertMode.INSERT_VALUES,
                mode=PETSc.ScatterMode.FORWARD,
            )
            workspace.y.set(0.0)
        for block in self._blocks:
            block.matrix.mult(
                self._workspaces[block.column_layer].x,
                self._workspaces[block.row_layer].temp,
            )
            self._workspaces[block.row_layer].y.axpy(
                PETSc.ScalarType(1.0), self._workspaces[block.row_layer].temp
            )
        for workspace in self._workspaces:
            workspace.scatter.scatter(
                workspace.y,
                target,
                addv=PETSc.InsertMode.ADD_VALUES,
                mode=PETSc.ScatterMode.REVERSE,
            )
        target.assemble()

    def destroy(self) -> None:
        if self._destroyed:
            return
        for block in self._blocks:
            block.destroy()
        self._blocks.clear()
        for workspace in self._workspaces:
            workspace.destroy()
        self._workspaces.clear()
        for layer_is in getattr(self, "_layer_is", ()):
            layer_is.destroy()
        self._layer_is = ()
        self._parent_template.destroy()
        self._labels = None
        self._permutation = None
        self._inverse_permutation = None
        self._diagnostics["destroy_marker"] = "completed"
        self._diagnostics["factor_count"] = 0
        self._diagnostics["qep_count"] = 0
        self._diagnostics["outer_ksp_count"] = 0
        self._destroyed = True


def build_layer_block_operator(
    matrix: PETSc.Mat,
    global_layer_labels: np.ndarray,
    *,
    layer_count: int,
    mapping_metadata: dict[str, Any] | None = None,
) -> LayerBlockOperator:
    """Construct the V8 layer block action without taking ownership of ``matrix``."""

    return LayerBlockOperator(
        matrix,
        global_layer_labels,
        layer_count=layer_count,
        mapping_metadata=mapping_metadata,
    )
