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

from .hybrid_local_dtn_woodbury import ResearchExactFactorInverse

__all__ = (
    "LayerBlockOperator",
    "LayerSweepAction",
    "audit_layer_block_action",
    "build_real_layer_labels",
    "build_layer_block_operator",
    "build_layer_sweep_action",
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
    matrix: PETSc.Mat | None
    local_nnz: int
    csr_bytes: int
    local_hash: str

    def destroy(self) -> None:
        if self.matrix is not None:
            self.matrix.destroy()
            self.matrix = None


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


class LayerSweepAction:
    """Fixed layer-triangular sweep with sequential factor-only ownership."""

    _METHODS = ("J1", "F1", "FB1", "FB2", "FB4")

    def __init__(
        self,
        *,
        method: str,
        factors: list[ResearchExactFactorInverse],
        lower: dict[int, PETSc.Mat],
        upper: dict[int, PETSc.Mat],
        workspaces: list[_LayerWorkspace],
        parent_template: PETSc.Vec,
        factor_records: list[dict[str, Any]],
        fine_action: Any,
        lifecycle_callback: Any,
    ) -> None:
        self._method = method
        self._factors = factors
        self._lower = lower
        self._upper = upper
        self._workspaces = workspaces
        self._parent_template = parent_template
        self._factor_records = factor_records
        self._current = parent_template.duplicate()
        self._residual = parent_template.duplicate()
        self._correction = parent_template.duplicate()
        self._fine_action = fine_action
        self._lifecycle_callback = lifecycle_callback
        self._destroyed = False
        self._apply_count = 0
        self._fb_sweep_count = 0
        self._fine_action_count = 0
        self._layer_solve_count = [0 for _ in factors]
        self._diagnostics = {
            "method": method,
            "layer_count": len(factors),
            "layer_factor_count": len(factors),
            "full_side_exact_factor_count": 0,
            "global_direct_factor_count": 0,
            "nested_ksp_count": 0,
            "fine_action_callback": fine_action is not None,
            "fine_action_is_explicit_matrix": isinstance(fine_action, PETSc.Mat),
            "factor_only_storage": True,
            "retained_explicit_diagonal_count": 0,
            "retained_lower_block_count": len(lower),
            "retained_upper_block_count": len(upper),
            "layer_factor_lifecycle": [
                {
                    "layer": layer,
                    "construction_marker": "completed",
                    "destroy_marker": "pending",
                }
                for layer in range(len(factors))
            ],
            "layer_factors": factor_records,
            "apply_count": 0,
            "fb_sweep_count": 0,
            "fine_action_count": 0,
            "layer_solve_count": [0 for _ in factors],
            "destroy_marker": "pending",
        }

    @classmethod
    def from_matrix(
        cls,
        matrix: PETSc.Mat,
        global_layer_labels: np.ndarray,
        *,
        layer_count: int,
        method: str,
        fine_action: Any = None,
        lifecycle_callback: Any = None,
    ) -> "LayerSweepAction":
        """Build one fixed sweep and release each explicit diagonal block."""

        if method not in cls._METHODS:
            raise ValueError(f"Unsupported fixed layer sweep method: {method}")
        if method in ("FB2", "FB4") and fine_action is None:
            raise ValueError(f"{method} requires a fine action callback")
        rows, cols = map(int, matrix.getSize())
        if rows != cols:
            raise ValueError("Layer sweep requires a square matrix")
        labels = np.asarray(global_layer_labels, dtype=np.int32)
        if (
            labels.shape != (rows,)
            or np.any(labels < 0)
            or np.any(labels >= layer_count)
        ):
            raise ValueError("Layer sweep labels do not match the matrix")
        comm = matrix.getComm()
        row_start, row_end = map(int, matrix.getOwnershipRange())
        local_labels = labels[row_start:row_end]
        row_ids = tuple(
            np.flatnonzero(local_labels == layer).astype(PETSc.IntType) + row_start
            for layer in range(layer_count)
        )
        layer_is = tuple(PETSc.IS().createGeneral(ids, comm=comm) for ids in row_ids)
        parent_template = matrix.createVecRight()
        factors: list[ResearchExactFactorInverse] = []
        factor_records: list[dict[str, Any]] = []
        lower: dict[int, PETSc.Mat] = {}
        upper: dict[int, PETSc.Mat] = {}
        workspaces: list[_LayerWorkspace] = []

        def cleanup_partial() -> None:
            for workspace in reversed(workspaces):
                workspace.destroy()
            workspaces.clear()
            for block in reversed(tuple(lower.values())):
                block.destroy()
            lower.clear()
            for block in reversed(tuple(upper.values())):
                block.destroy()
            upper.clear()
            for factor in reversed(factors):
                factor.destroy()
            factors.clear()
            for layer_is_item in layer_is:
                layer_is_item.destroy()
            parent_template.destroy()

        try:
            for layer in range(layer_count - 1):
                upper[layer] = matrix.createSubMatrix(
                    layer_is[layer], layer_is[layer + 1]
                )
                lower[layer + 1] = matrix.createSubMatrix(
                    layer_is[layer + 1], layer_is[layer]
                )
            for layer in range(layer_count):
                diagonal = matrix.createSubMatrix(layer_is[layer], layer_is[layer])
                factor = None
                try:
                    if lifecycle_callback is not None:
                        lifecycle_callback("layer_factor_setup_begin", {"layer": layer})
                    factor = ResearchExactFactorInverse(
                        diagonal,
                        factor_solver_type="mumps",
                        factor_only_storage=True,
                    )
                    factor.release_borrowed_matrix()
                    factors.append(factor)
                    factor_diagnostics = factor.diagnostics
                    local_rows, _ = map(int, diagonal.getLocalSize())
                    nnz_local = int(diagonal.getInfo()["nz_used"])
                    nnz_global = int(
                        matrix.getComm().tompi4py().allreduce(nnz_local, op=MPI.SUM)
                    )
                    factor_records.append(
                        {
                            "layer": layer,
                            "rows_owned_local": local_rows,
                            "rows_global": int(diagonal.getSize()[0]),
                            "nnz_local": nnz_local,
                            "nnz_global": nnz_global,
                            "factor_matrix_stats": factor_diagnostics[
                                "factor_matrix_stats"
                            ],
                            "factor_only_storage": bool(
                                factor_diagnostics["factor_only_storage"]
                            ),
                            "borrowed_matrix_released": bool(
                                factor_diagnostics["borrowed_matrix_released"]
                            ),
                            "factor_matrix_alive": bool(
                                factor_diagnostics["factor_matrix_alive"]
                            ),
                        }
                    )
                    if lifecycle_callback is not None:
                        lifecycle_callback(
                            "layer_factor_ready",
                            {"layer": layer, "factor_only_storage": True},
                        )
                except Exception:
                    if factor is not None:
                        factor.destroy()
                    raise
                finally:
                    diagonal.destroy()
            for layer, factor in enumerate(factors):
                factor_matrix = factor.operator
                if factor_matrix is None:
                    raise RuntimeError(f"Layer {layer} factor has no retained matrix")
                x = factor_matrix.createVecRight()
                y = factor_matrix.createVecLeft()
                temp = y.duplicate()
                first, last = map(int, x.getOwnershipRange())
                positions = PETSc.IS().createStride(
                    last - first, first=first, step=1, comm=comm
                )
                try:
                    scatter = PETSc.Scatter().create(
                        parent_template,
                        layer_is[layer],
                        x,
                        positions,
                    )
                except Exception:
                    temp.destroy()
                    y.destroy()
                    x.destroy()
                    raise
                finally:
                    positions.destroy()
                workspaces.append(
                    _LayerWorkspace(layer=layer, x=x, y=y, temp=temp, scatter=scatter)
                )
            action = cls(
                method=method,
                factors=factors,
                lower=lower,
                upper=upper,
                workspaces=workspaces,
                parent_template=parent_template,
                factor_records=factor_records,
                fine_action=fine_action,
                lifecycle_callback=lifecycle_callback,
            )
            for layer_is_item in layer_is:
                layer_is_item.destroy()
            layer_is = ()
            return action
        except Exception:
            cleanup_partial()
            raise

    @property
    def diagnostics(self) -> dict[str, Any]:
        diagnostics = dict(self._diagnostics)
        diagnostics["layer_factor_count"] = 0 if self._destroyed else len(self._factors)
        diagnostics["apply_count"] = self._apply_count
        diagnostics["fb_sweep_count"] = self._fb_sweep_count
        diagnostics["fine_action_count"] = self._fine_action_count
        diagnostics["layer_solve_count"] = list(self._layer_solve_count)
        diagnostics["layer_factors"] = [
            {**record, "solve_count": self._layer_solve_count[record["layer"]]}
            for record in self._factor_records
        ]
        diagnostics["destroyed"] = self._destroyed
        return diagnostics

    @property
    def destroyed(self) -> bool:
        return self._destroyed

    @property
    def factor_only_storage(self) -> bool:
        """The action retains layer factors, not explicit diagonal matrices."""

        return True

    def _gather(self, source: PETSc.Vec) -> None:
        for workspace in self._workspaces:
            workspace.scatter.scatter(
                source,
                workspace.x,
                addv=PETSc.InsertMode.INSERT_VALUES,
                mode=PETSc.ScatterMode.FORWARD,
            )

    def _forward(self) -> None:
        for layer, workspace in enumerate(self._workspaces):
            if layer:
                self._lower[layer].mult(self._workspaces[layer - 1].y, workspace.temp)
                workspace.x.axpy(PETSc.ScalarType(-1.0), workspace.temp)
            self._solve_layer(layer, workspace.x, workspace.y)

    def _backward(self) -> None:
        for layer in range(len(self._workspaces) - 1, -1, -1):
            workspace = self._workspaces[layer]
            if layer < len(self._workspaces) - 1:
                self._upper[layer].mult(self._workspaces[layer + 1].y, workspace.temp)
                workspace.x.axpy(PETSc.ScalarType(-1.0), workspace.temp)
            self._solve_layer(layer, workspace.x, workspace.y)

    def _solve_layer(self, layer: int, source: PETSc.Vec, target: PETSc.Vec) -> None:
        self._factors[layer].solve(source, target)
        self._layer_solve_count[layer] += 1

    def _scatter_solution(self, target: PETSc.Vec) -> None:
        target.set(0.0)
        for workspace in self._workspaces:
            workspace.scatter.scatter(
                workspace.y,
                target,
                addv=PETSc.InsertMode.ADD_VALUES,
                mode=PETSc.ScatterMode.REVERSE,
            )
        target.assemble()

    def _apply_fb1(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        self._gather(source)
        self._forward()
        self._backward()
        self._scatter_solution(target)
        self._fb_sweep_count += 1

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        self.apply_checkpoint(self._method, source, target)

    def solve(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        """Expose the fixed action through the base-inverse solve protocol."""

        self.apply(source, target)

    def apply_checkpoint(
        self, method: str, source: PETSc.Vec, target: PETSc.Vec
    ) -> None:
        if self._destroyed:
            raise RuntimeError("layer sweep action has been destroyed")
        if method not in self._METHODS:
            raise ValueError(f"Unsupported fixed layer sweep method: {method}")
        if method in ("FB2", "FB4") and self._fine_action is None:
            raise ValueError(f"{method} requires a fine action callback")
        expected_size = self._parent_template.getSize()
        if source.getSize() != expected_size or target.getSize() != expected_size:
            raise ValueError("layer sweep vector does not match matrix layout")
        self._apply_count += 1
        if method == "J1":
            self._gather(source)
            for layer, workspace in enumerate(self._workspaces):
                self._solve_layer(layer, workspace.x, workspace.y)
            self._scatter_solution(target)
            return
        if method == "F1":
            self._gather(source)
            self._forward()
            self._scatter_solution(target)
            return
        if method == "FB1":
            self._apply_fb1(source, target)
            return

        target.set(0.0)
        self._current.set(0.0)
        applications = 2 if method == "FB2" else 4
        for iteration in range(applications):
            if iteration == 0:
                source.copy(self._residual)
            else:
                self._fine_action(self._current, self._residual)
                self._fine_action_count += 1
                self._residual.scale(PETSc.ScalarType(-1.0))
                self._residual.axpy(PETSc.ScalarType(1.0), source)
            self._apply_fb1(self._residual, self._correction)
            self._current.axpy(PETSc.ScalarType(1.0), self._correction)
        self._current.copy(target)

    def destroy(self) -> None:
        if self._destroyed:
            return
        for vector in (self._correction, self._residual, self._current):
            vector.destroy()
        self._correction = None
        self._residual = None
        self._current = None
        for workspace in reversed(self._workspaces):
            workspace.destroy()
        self._workspaces.clear()
        for block in reversed(tuple(self._lower.values())):
            block.destroy()
        self._lower.clear()
        for block in reversed(tuple(self._upper.values())):
            block.destroy()
        self._upper.clear()
        for layer, factor in reversed(tuple(enumerate(self._factors))):
            factor.destroy()
            self._diagnostics["layer_factor_lifecycle"][layer]["destroy_marker"] = (
                "completed"
            )
        self._factors.clear()
        self._parent_template.destroy()
        self._parent_template = None
        self._diagnostics["layer_factor_count"] = 0
        self._diagnostics["destroy_marker"] = "completed"
        self._destroyed = True
        if self._lifecycle_callback is not None:
            self._lifecycle_callback("layer_sweep_destroyed", self.diagnostics)


def build_layer_sweep_action(
    matrix: PETSc.Mat,
    global_layer_labels: np.ndarray,
    *,
    layer_count: int,
    method: str,
    fine_action: Any = None,
    lifecycle_callback: Any = None,
) -> LayerSweepAction:
    """Build a fixed J1/F1/FB1/FB2/FB4 factor-only layer action."""

    return LayerSweepAction.from_matrix(
        matrix,
        global_layer_labels,
        layer_count=layer_count,
        method=method,
        fine_action=fine_action,
        lifecycle_callback=lifecycle_callback,
    )


def _relative_vec_error(actual: PETSc.Vec, expected: PETSc.Vec) -> float:
    difference = actual.duplicate()
    expected.copy(difference)
    difference.axpy(PETSc.ScalarType(-1.0), actual)
    error = float(difference.norm()) / max(float(expected.norm()), 1.0e-30)
    difference.destroy()
    return error


def _fill_audit_source(vector: PETSc.Vec, index: int) -> tuple[str, str]:
    first, last = map(int, vector.getOwnershipRange())
    rows = np.arange(first, last, dtype=np.float64)
    values = np.sin(0.013 * rows + 0.17 * index) + 1j * np.cos(
        0.009 * rows - 0.23 * index
    )
    vector.getArray()[:] = np.asarray(values, dtype=PETSc.ScalarType)
    vector.assemble()
    local_hash = hashlib.sha256(
        np.ascontiguousarray(vector.getArray(readonly=True)).view(np.uint8)
    ).hexdigest()
    comm = vector.getComm().tompi4py()
    partition_digest = hashlib.sha256(
        json.dumps(
            comm.allgather(
                {
                    "ownership_range": [first, last],
                    "local_hash": local_hash,
                }
            ),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    generator_digest = hashlib.sha256(
        f"global_row_sin_cos_v1:{index}:{vector.getSize()}:"
        f"{np.dtype(PETSc.ScalarType).str}".encode("ascii")
    ).hexdigest()
    return partition_digest, generator_digest


def audit_layer_block_action(
    matrix: PETSc.Mat, operator: LayerBlockOperator, *, vector_count: int = 8
) -> dict[str, Any]:
    """Compare a block action with ``matrix`` on fixed value-hashed vectors.

    The vectors are generated from global row numbers, so their values do not
    depend on the MPI partition.  Only local PETSc arrays are materialized.
    This is an audit helper, not a solver or a source of physical fields.
    """

    if vector_count != 8:
        raise ValueError("V8 layer action audit requires exactly eight vectors")
    retained_sources: list[PETSc.Vec] = []
    retained_actual: list[PETSc.Vec] = []
    reports: list[dict[str, Any]] = []
    try:
        for index in range(vector_count):
            source = matrix.createVecRight()
            f_result = matrix.createVecLeft()
            block_result = matrix.createVecLeft()
            try:
                source_hash, generator_hash = _fill_audit_source(source, index)
                matrix.mult(source, f_result)
                operator.apply(source, block_result)
                f_norm = float(f_result.norm())
                block_norm = float(block_result.norm())
                relative_error = _relative_vec_error(block_result, f_result)
                reports.append(
                    {
                        "index": index,
                        "source_value_hash": source_hash,
                        "generator_contract_sha256": generator_hash,
                        "hash_scheme": "rank_local_sha256_allgather_v1",
                        "rank_partition_bound": True,
                        "f_norm": f_norm,
                        "block_norm": block_norm,
                        "relative_error": relative_error,
                        "finite": bool(
                            np.isfinite(relative_error)
                            and np.isfinite(f_norm)
                            and np.isfinite(block_norm)
                        ),
                    }
                )
                if index < 2:
                    retained_sources.append(source)
                    retained_actual.append(block_result)
                    source = None
                    block_result = None
            finally:
                f_result.destroy()
                if source is not None:
                    source.destroy()
                if block_result is not None:
                    block_result.destroy()
        repeat = retained_actual[0].duplicate()
        operator.apply(retained_sources[0], repeat)
        repeat_error = _relative_vec_error(repeat, retained_actual[0])
        linear_expected = retained_actual[0].duplicate()
        retained_actual[0].copy(linear_expected)
        linear_expected.scale(PETSc.ScalarType(1.1 - 0.4j))
        linear_expected.axpy(PETSc.ScalarType(-0.7 + 0.2j), retained_actual[1])
        combination = retained_sources[0].duplicate()
        retained_sources[0].copy(combination)
        combination.scale(PETSc.ScalarType(1.1 - 0.4j))
        combination.axpy(PETSc.ScalarType(-0.7 + 0.2j), retained_sources[1])
        combination_actual = matrix.createVecLeft()
        operator.apply(combination, combination_actual)
        linearity_error = _relative_vec_error(combination_actual, linear_expected)
        repeat.destroy()
        linear_expected.destroy()
        combination.destroy()
        combination_actual.destroy()
        return {
            "vector_count": vector_count,
            "vectors": reports,
            "max_relative_error": max(
                float(report["relative_error"]) for report in reports
            ),
            "repeat_relative_error": repeat_error,
            "linearity_relative_error": linearity_error,
            "relative_error_limit": 1.0e-12,
            "repeat_limit": 1.0e-13,
            "linearity_limit": 1.0e-13,
            "value_hash_bound": True,
            "source_generator": "global_row_sin_cos_v1",
            "source_hash_rank_partition_bound": True,
        }
    finally:
        for vector in (*retained_actual, *retained_sources):
            vector.destroy()


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
