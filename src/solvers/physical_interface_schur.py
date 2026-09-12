"""Physical p4 interface Schur core for the Task39extra V14 route.

The production path in this module owns the p4 internal elimination and the
sparse interface matrix, while the mesh, MPC, physical form and port carrier
remain owned by the caller.  It does not construct the historical macro
``Q/D/W`` objects or any p2/p1 level.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
import time
from typing import Any, Callable

import numpy as np


SCHUR_SCHEMA = "task039extra.physical-interface-schur.v14"
SCHUR_PROFILE = "physical_p4_schur_v14"
MAX_INTERNAL_ROWS = 2048
MAX_INTERFACE_ROWS = 512
MAX_INTERFACE_WORKSPACE_BYTES = 64 * 1024**2
SCHUR_BATCH_COLUMNS = 32
V11_MIN_BYTES = 32 * 1024**2
V11_PADDING_BYTES = 8 * 1024**2


def _sparse_payload_bytes(nnz: int, rows: int, petsc: Any) -> int:
    return int(rows + 1) * np.dtype(petsc.IntType).itemsize + int(nnz) * (
        np.dtype(petsc.IntType).itemsize + np.dtype(petsc.ScalarType).itemsize
    )


def v11_memory_request_mb(symbolic_raw: Mapping[str, Any]) -> dict[str, Any]:
    """Return the exact decimal-MB request prescribed by Review V14.

    MUMPS ``INFOG(16)`` is an integer estimate in megabytes.  The estimate is
    interpreted as a sizing input, not as a measured peak.
    """

    from .fullspace_bounded_mumps import symbolic_sized_local_mumps_request

    result = dict(symbolic_sized_local_mumps_request(symbolic_raw, mpi_size=1))
    result.update(
        {
            "formula": "ceil_MB(max(32 MiB, 2*symbolic_estimate_padded+8 MiB))",
            "symbolic_estimate_mb": int(result["infog16_mb"]),
            "symbolic_estimate_padded_bytes": int(result["estimate_bytes"]),
            "requested_memory_limit_mb": int(result["request_mb"]),
            "unit": "decimal_MB_for_MUMPS_ICNTL_23",
        }
    )
    return result


def _as_complex_array(value: Any) -> np.ndarray:
    if hasattr(value, "array"):
        return np.asarray(value.array)
    getter = getattr(value, "getArray", None)
    if callable(getter):
        try:
            return np.asarray(getter(readonly=True))
        except TypeError:
            return np.asarray(getter())
    return np.asarray(value)


def _destroy(value: Any) -> None:
    destroy = getattr(value, "destroy", None)
    if callable(destroy):
        destroy()


def _nonzero_rows(values: Any, *, tolerance: float = 0.0) -> np.ndarray:
    array = np.asarray(values)
    if array.ndim != 1:
        array = array.reshape(-1)
    return np.flatnonzero(np.abs(array) > tolerance).astype(np.int64)




@dataclass(frozen=True)
class SchurPartition:
    """Compact active-index partition and its auditable full-storage identity."""

    storage_size: int
    active_full_indices: np.ndarray
    slave_full_indices: np.ndarray
    gamma_full_indices: np.ndarray
    gamma_active_indices: np.ndarray
    internal_blocks_full: tuple[np.ndarray, ...]
    internal_blocks_active: tuple[np.ndarray, ...]
    seed_group_count: int
    port_support_full_indices: np.ndarray
    cross_owner_volume_pairs: int = 0

    @property
    def active_rows(self) -> int:
        return int(self.active_full_indices.size)

    @property
    def gamma_rows(self) -> int:
        return int(self.gamma_active_indices.size)

    @property
    def internal_rows(self) -> int:
        return int(sum(block.size for block in self.internal_blocks_active))

    def audit(self) -> dict[str, Any]:
        sizes = [int(block.size) for block in self.internal_blocks_active]
        return {
            "schema": SCHUR_SCHEMA,
            "storage_rows": self.storage_size,
            "active_rows": self.active_rows,
            "slave_rows": int(self.slave_full_indices.size),
            "gamma_rows": self.gamma_rows,
            "internal_rows": self.internal_rows,
            "internal_block_count": len(self.internal_blocks_active),
            "internal_block_sizes": sizes,
            "max_internal_block_rows": max(sizes, default=0),
            "seed_group_count": self.seed_group_count,
            "port_support_rows": int(self.port_support_full_indices.size),
            "cross_owner_volume_pairs": int(self.cross_owner_volume_pairs),
            "partition_complete": self.active_rows == self.gamma_rows + self.internal_rows,
        }


def _mpc_storage_map(
    space: Any,
    floquet: Any,
) -> tuple[np.ndarray, np.ndarray, dict[int, np.ndarray]]:
    """Expand cell dofs through MPC links without constructing a macro object."""

    from .condensed_fine_reference import native_map_arrays

    mapping = native_map_arrays(space, floquet)
    dofmap = np.asarray(mapping["dofmap"], dtype=np.int64)
    slaves = np.asarray(mapping["slaves"], dtype=np.int64)
    masters = np.asarray(mapping["masters"], dtype=np.int64)
    coefficients = np.asarray(mapping["coefficients"], dtype=np.complex128)
    offsets = np.asarray(mapping["offsets"], dtype=np.int64)
    independent = np.asarray(mapping["independent_indices"], dtype=np.int64)
    storage_size = offsets.size - 1
    if storage_size <= 0 or independent.size + slaves.size != storage_size:
        raise ValueError("native p4 map has inconsistent storage/active sizes")
    if (
        offsets[0] != 0
        or offsets[-1] != masters.size
        or masters.size != coefficients.size
        or np.any(np.diff(offsets) < 0)
        or np.any(slaves < 0)
        or np.any(slaves >= storage_size)
        or np.any(masters < 0)
        or np.any(masters >= storage_size)
        or np.unique(slaves).size != slaves.size
        or np.intersect1d(slaves, masters).size
        or not np.array_equal(
            np.sort(independent),
            np.setdiff1d(np.arange(storage_size), np.unique(slaves)),
        )
    ):
        raise ValueError("native p4 MPC map failed the active-index identity gate")
    links: dict[int, np.ndarray] = {}
    for slave in slaves:
        start, stop = int(offsets[slave]), int(offsets[slave + 1])
        links[int(slave)] = masters[start:stop].copy()
    return dofmap, slaves, links


def _cell_seed_groups(mesh: Any, cell_count: int) -> list[np.ndarray]:
    geometry_dofmap = np.asarray(mesh.geometry.dofmap, dtype=np.int64)
    coordinates = np.asarray(mesh.geometry.x)
    if geometry_dofmap.shape[0] != cell_count:
        raise ValueError("geometry and function-space cell counts differ")
    minima = np.asarray(
        [
            coordinates[geometry_dofmap[cell]].min(axis=0)
            for cell in range(cell_count)
        ]
    )
    axes = [np.unique(minima[:, axis]) for axis in range(3)]
    if cell_count != 252 or tuple(len(axis) for axis in axes) != (6, 3, 14):
        raise ValueError(
            "frozen p4 geometry must contain 252 cells with 6x3x14 starts"
        )
    axis_indices = [
        np.searchsorted(axes[axis], minima[:, axis]) for axis in range(3)
    ]
    groups: dict[tuple[int, int, int], list[int]] = {}
    for cell in range(cell_count):
        key = tuple(int(axis_indices[axis][cell]) // 2 for axis in range(3))
        groups.setdefault(key, []).append(cell)
    return [
        np.asarray(groups[key], dtype=np.int64)
        for key in sorted(groups)
    ]


def _carrier_support(
    carrier: Any,
    storage_size: int,
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    support: set[int] = set()
    port_data: list[dict[str, Any]] = []
    for port, entry in enumerate(carrier.entries):
        b_rows = np.asarray(entry.coupling_rows, dtype=np.int64).reshape(-1)
        b_values = np.asarray(entry.coupling_values, dtype=np.complex128).reshape(-1)
        d_rows = np.asarray(entry.projection_rows, dtype=np.int64).reshape(-1)
        d_values = np.asarray(entry.projection_values, dtype=np.complex128).reshape(-1)
        if b_rows.size != b_values.size or d_rows.size != d_values.size:
            raise ValueError(f"port {port} coupling/projection lengths differ")
        if (
            np.any(b_rows < 0)
            or np.any(b_rows >= storage_size)
            or np.any(d_rows < 0)
            or np.any(d_rows >= storage_size)
        ):
            raise ValueError(f"port {port} support is outside the p4 storage layout")
        b_keep = _nonzero_rows(b_values)
        d_keep = _nonzero_rows(d_values)
        support.update(b_rows[b_keep].tolist())
        support.update(d_rows[d_keep].tolist())
        port_data.append(
            {
                "port": port,
                "coupling_rows": b_rows,
                "coupling_values": b_values,
                "projection_rows": d_rows,
                "projection_values": d_values,
                "normalization_h": complex(entry.normalization_h),
            }
        )
    return np.asarray(sorted(support), dtype=np.int64), port_data


def build_interface_partition(
    space: Any,
    floquet: Any,
    carrier: Any,
    *,
    volume: Any | None = None,
) -> tuple[SchurPartition, list[dict[str, Any]]]:
    """Build the 42-cell p4 partition from geometry, MPC and port support.

    Only the reusable cell grouping and active-index rules are reproduced
    here.  No historical macro data structure is instantiated.
    """

    dofmap, slaves, links = _mpc_storage_map(space, floquet)
    storage_size = max(
        int(dofmap.max()) + 1,
        int(getattr(space.dofmap.index_map, "size_global", 0)),
    )
    slave_set = set(slaves.tolist())
    cell_active: list[np.ndarray] = []
    for cell in dofmap:
        expanded: list[int] = []
        for dof in cell:
            dof = int(dof)
            expanded.extend(
                links.get(dof, np.asarray([dof], dtype=np.int64)).tolist()
            )
        cell_active.append(
            np.asarray(sorted(set(expanded) - slave_set), dtype=np.int64)
        )
    groups = _cell_seed_groups(space.mesh, len(cell_active))
    block_rows: list[np.ndarray] = []
    owners: dict[int, set[int]] = {}
    for owner, cells in enumerate(groups):
        rows = np.asarray(
            sorted(
                set(
                    np.concatenate(
                        [cell_active[int(cell)] for cell in cells]
                    ).tolist()
                )
            ),
            dtype=np.int64,
        )
        block_rows.append(rows)
        for row in rows:
            owners.setdefault(int(row), set()).add(owner)
    active = np.asarray(
        [row for row in range(storage_size) if row not in slave_set],
        dtype=np.int64,
    )
    if set(np.concatenate(block_rows).tolist()) != set(active.tolist()):
        raise ValueError(
            "cell/MPC expansion does not cover exactly the legal active p4 rows"
        )
    support, port_data = _carrier_support(carrier, storage_size)
    if np.intersect1d(support, slaves).size:
        raise ValueError("port support contains an MPC slave row")
    gamma = set(support.tolist())
    gamma.update(
        row for row, row_owners in owners.items() if len(row_owners) > 1
    )
    cross_pairs = 0
    if volume is not None:
        owner_for_row = {
            row: next(iter(row_owners))
            for row, row_owners in owners.items()
            if len(row_owners) == 1 and row not in gamma
        }
        for row in active:
            row = int(row)
            if row not in owner_for_row:
                continue
            columns, _values = volume.getRow(row)
            for column in np.asarray(columns, dtype=np.int64):
                column = int(column)
                if column not in owner_for_row or column == row:
                    continue
                if owner_for_row[column] != owner_for_row[row]:
                    cross_pairs += 1
        if cross_pairs:
            raise ValueError(
                "nonzero volume coupling crosses two internal owners; "
                "Gamma must not be enlarged after the frozen partition gate"
            )
    gamma_full = np.asarray(sorted(gamma), dtype=np.int64)
    active_to_compact = -np.ones(storage_size, dtype=np.int64)
    active_to_compact[active] = np.arange(active.size, dtype=np.int64)
    gamma_active = active_to_compact[gamma_full]
    if np.any(gamma_active < 0):
        raise ValueError("Gamma contains an inactive row")
    gamma_active = np.sort(gamma_active)
    gamma_set = set(gamma_full.tolist())
    blocks_full = tuple(
        np.asarray(
            [row for row in rows if int(row) not in gamma_set],
            dtype=np.int64,
        )
        for rows in block_rows
    )
    blocks_active = tuple(active_to_compact[rows] for rows in blocks_full)
    if any(np.any(block < 0) for block in blocks_active):
        raise ValueError("internal block contains an inactive row")
    partition = SchurPartition(
        storage_size=storage_size,
        active_full_indices=active,
        slave_full_indices=np.sort(slaves),
        gamma_full_indices=gamma_full,
        gamma_active_indices=gamma_active,
        internal_blocks_full=blocks_full,
        internal_blocks_active=blocks_active,
        seed_group_count=len(groups),
        port_support_full_indices=support,
        cross_owner_volume_pairs=cross_pairs,
    )
    audit = partition.audit()
    if not audit["partition_complete"] or partition.seed_group_count != 42:
        raise ValueError(f"unexpected p4 interface partition: {audit}")
    if partition.storage_size == 53084 and (
        partition.active_rows != 48960
        or partition.gamma_rows != 13092
        or partition.internal_rows != 35868
    ):
        raise ValueError(
            "frozen p4 partition changed: expected active=48960, "
            "Gamma=13092, internal=35868"
        )
    if any(block.size == 0 or block.size > MAX_INTERNAL_ROWS for block in blocks_active):
        raise ValueError("frozen p4 internal blocks must be nonempty and <=2048 rows")
    return partition, port_data

 
 
@dataclass
class InternalFactor:
    block_index: int
    indices: np.ndarray
    matrix: Any
    factor: Any
    grows: np.ndarray
    gcols: np.ndarray
    A_gi: np.ndarray
    A_i_g: np.ndarray
    symbolic_raw: dict[str, Any]
    numeric_raw: dict[str, Any]
    memory_request: dict[str, Any]
    symbolic_seconds: float
    numeric_seconds: float
    solve_calls_at_build: int = 0
 
 
@dataclass
class PhysicalInterfaceSchur:
    """Owned sparse Schur matrices and live internal/interface factors."""
 
    volume: Any
    partition: SchurPartition
    S_V: Any
    V_GG: Any
    interface_matrix: Any
    internal: list[InternalFactor]
    interface_factor: Any
    port_data: list[dict[str, Any]]
    factor_facts: dict[str, Any] = field(default_factory=dict)
    owns_volume: bool = True
    destroyed: bool = False
 
    def _solve_factor(self, item: InternalFactor, values: np.ndarray) -> np.ndarray:
        rhs = item.matrix.createVecRight()
        solution = item.matrix.createVecRight()
        try:
            rhs.array[:] = values
            item.factor.solve_repeated(rhs, solution)
            return np.asarray(solution.array).copy()
        finally:
            rhs.destroy()
            solution.destroy()
 
    def _interface_solve(self, values: np.ndarray) -> np.ndarray:
        if self.interface_factor is None:
            raise RuntimeError("the global interface factor has not been built")
        rhs = self.interface_matrix.createVecRight()
        solution = self.interface_matrix.createVecRight()
        try:
            rhs.array[:] = values
            self.interface_factor.solve_repeated(rhs, solution)
            return np.asarray(solution.array).copy()
        finally:
            rhs.destroy()
            solution.destroy()

    def _reduce_rhs(
        self,
        rhs: Any,
        port_rhs: np.ndarray | None = None,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        input_array = _as_complex_array(rhs)
        if input_array.size != self.partition.storage_size:
            raise ValueError("Schur reduction expects full p4 storage RHS")
        active_rhs = np.asarray(
            input_array[self.partition.active_full_indices],
            dtype=np.complex128,
        )
        gamma = self.partition.gamma_active_indices
        reduced = active_rhs[gamma].copy()
        for item in self.internal:
            local_rhs = active_rhs[item.indices]
            if item.grows.size:
                reduced[item.grows] -= item.A_gi @ self._solve_factor(
                    item, local_rhs
                )
        ports = len(self.port_data)
        port_values = (
            np.zeros(ports, dtype=np.complex128)
            if port_rhs is None
            else np.asarray(port_rhs, dtype=np.complex128)
        )
        if port_values.shape != (ports,):
            raise ValueError("port RHS has the wrong shape")
        return active_rhs, reduced, port_values

    def reduce(
        self,
        rhs: Any,
        *,
        port_rhs: np.ndarray | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return the exact ``[g_G-A_GI A_II^-1 g_I; g_port]`` RHS."""

        _active_rhs, reduced, port_values = self._reduce_rhs(rhs, port_rhs)
        return reduced, port_values
 
    def solve(
        self,
        rhs: Any,
        *,
        port_rhs: np.ndarray | None = None,
        return_facts: bool = False,
    ) -> Any:
        """Eliminate all ``I_i``, solve one interface system, then recover."""
 
        active_rhs, reduced, port_values = self._reduce_rhs(rhs, port_rhs)
        gamma = self.partition.gamma_active_indices
        interface_solution = self._interface_solve(
            np.concatenate((reduced, port_values))
        )
        result, recovery_facts = self.recover(
            rhs,
            interface_solution[: gamma.size],
            return_facts=True,
        )
        output = _as_complex_array(result)
        facts = {
            **recovery_facts,
            "volume_rhs_norm": float(np.linalg.norm(active_rhs)),
            "interface_rhs_norm": float(
                np.linalg.norm(np.concatenate((reduced, port_values)))
            ),
            "internal_elimination_solves": len(self.internal),
            "interface_solves": 1,
            "interface_solution": interface_solution.copy(),
            "slave_solution_max": float(
                np.max(np.abs(output[self.partition.slave_full_indices]), initial=0.0)
            ),
        }
        return (result, facts) if return_facts else result

    def recover(
        self,
        rhs: Any,
        gamma_solution: Any,
        *,
        return_facts: bool = False,
    ) -> Any:
        """Recover internal p4 values from a supplied interface solution.

        This path only needs the retained local factors and ``V_GI`` blocks;
        it remains valid after the explicit ``S_V`` and global interface
        factor have been released.
        """

        input_array = _as_complex_array(rhs)
        if input_array.size != self.partition.storage_size:
            raise ValueError("Schur recovery expects full p4 storage RHS")
        gamma_solution = _as_complex_array(gamma_solution)
        if gamma_solution.size != self.partition.gamma_rows:
            raise ValueError("Gamma solution has the wrong size")
        active_rhs = np.asarray(
            input_array[self.partition.active_full_indices],
            dtype=np.complex128,
        )
        active_solution = np.zeros(self.partition.active_rows, dtype=np.complex128)
        active_solution[self.partition.gamma_active_indices] = gamma_solution
        for item in self.internal:
            rhs_local = active_rhs[item.indices].copy()
            if item.gcols.size:
                rhs_local -= item.A_i_g @ active_solution[
                    self.partition.gamma_active_indices[item.gcols]
                ]
            active_solution[item.indices] = self._solve_factor(item, rhs_local)
        output = np.zeros(self.partition.storage_size, dtype=np.complex128)
        output[self.partition.active_full_indices] = active_solution
        if hasattr(rhs, "duplicate"):
            result = rhs.duplicate()
            result.set(0)
            result.array[:] = output
        else:
            result = output
        facts = {
            "internal_recovery_solves": len(self.internal),
            "slave_solution_max": float(
                np.max(np.abs(output[self.partition.slave_full_indices]), initial=0.0)
            ),
        }
        return (result, facts) if return_facts else result
 
    def apply_volume_schur(self, vector: Any, output: Any | None = None) -> Any:
        """Apply ``S_V = V_GG - sum(V_GI V_II^-1 V_IG)`` matrix-free."""
 
        if hasattr(vector, "duplicate"):
            target = self.V_GG.createVecLeft() if output is None else output
            self.V_GG.mult(vector, target)
            for item in self.internal:
                if item.grows.size and item.gcols.size:
                    target.array[item.grows] -= item.A_gi @ self._solve_factor(
                        item,
                        item.A_i_g @ np.asarray(vector.array[item.gcols]),
                    )
            return target
        raise TypeError("the production Schur action requires a PETSc Vec")

    def apply_physical_schur(self, vector: Any, output: Any | None = None) -> Any:
        """Apply ``S = S_V + B H^-1 D`` without retaining a port matrix."""

        if not hasattr(vector, "array"):
            raise TypeError("the production physical Schur action requires a PETSc Vec")
        target = self.V_GG.createVecLeft() if output is None else output
        self.apply_volume_schur(vector, target)
        values = np.asarray(vector.array)
        for entry in self.port_data:
            h = entry["normalization_h"]
            if h == 0:
                raise ZeroDivisionError("port normalization H is zero")
            port_value = np.dot(
                entry["d_values"], values[entry["d_gamma"]]
            ) / h
            target.array[entry["b_gamma"]] += entry["b_values"] * port_value
        return target
 
    def apply_volume_schur_adjoint(self, vector: Any, output: Any | None = None) -> Any:
        """Apply the conjugate-transpose Schur operator using each same factor."""
 
        if not hasattr(vector, "array"):
            raise TypeError("the production adjoint Schur action requires a PETSc Vec")
        target = self.V_GG.createVecLeft() if output is None else output
        self.V_GG.multHermitian(vector, target)
        for item in self.internal:
            if not item.grows.size or not item.gcols.size:
                continue
            rhs = item.matrix.createVecRight()
            solution = item.matrix.createVecRight()
            try:
                rhs.array[:] = item.A_gi.conj().T @ np.asarray(vector.array[item.grows])
                solve_adjoint = getattr(item.factor, "solve_adjoint", None)
                if not callable(solve_adjoint):
                    raise RuntimeError("the live factor has no adjoint solve API")
                solve_adjoint(rhs, solution)
                target.array[item.gcols] -= item.A_i_g.conj().T @ np.asarray(
                    solution.array
                )
            finally:
                rhs.destroy()
                solution.destroy()
        return target

    def apply_physical_schur_adjoint(
        self,
        vector: Any,
        output: Any | None = None,
    ) -> Any:
        """Apply ``S.H = S_V.H + D.H H^{-H} B.H`` with the same factors."""

        if not hasattr(vector, "array"):
            raise TypeError(
                "the production physical adjoint action requires a PETSc Vec"
            )
        target = self.V_GG.createVecLeft() if output is None else output
        self.apply_volume_schur_adjoint(vector, target)
        values = np.asarray(vector.array)
        for entry in self.port_data:
            h = entry["normalization_h"]
            if h == 0:
                raise ZeroDivisionError("port normalization H is zero")
            port_value = np.dot(
                np.conj(entry["b_values"]), values[entry["b_gamma"]]
            ) / np.conj(h)
            target.array[entry["d_gamma"]] += np.conj(
                entry["d_values"]
            ) * port_value
        return target
 
    def apply_interface_matrix_free(self, vector: Any, output: Any | None = None) -> Any:
        """Apply the assembled augmented interface matrix by its blocks."""

        if not hasattr(vector, "array"):
            raise TypeError("the production interface action requires a PETSc Vec")
        values = np.asarray(vector.array)
        target = (
            self.interface_matrix.createVecLeft() if output is None else output
        )
        target.set(0)
        gamma_size = self.partition.gamma_rows
        volume_input = self.V_GG.createVecRight()
        volume_input.array[:] = values[:gamma_size]
        volume_output = self.V_GG.createVecLeft()
        try:
            self.apply_volume_schur(volume_input, volume_output)
            target.array[:gamma_size] = volume_output.array
        finally:
            volume_input.destroy()
            volume_output.destroy()
        for port, entry in enumerate(self.port_data):
            target.array[entry["b_gamma"]] += (
                entry["b_values"] * values[gamma_size + port]
            )
            target.array[gamma_size + port] -= np.dot(
                entry["d_values"], values[entry["d_gamma"]]
            )
            target.array[gamma_size + port] += (
                entry["normalization_h"] * values[gamma_size + port]
            )
        return target
 
    def destroy(self) -> None:
        if self.destroyed:
            return
        _destroy(self.interface_factor)
        self.interface_factor = None
        for item in self.internal:
            _destroy(item.factor)
            _destroy(item.matrix)
        self.internal.clear()
        for value in (self.interface_matrix, self.S_V, self.V_GG):
            _destroy(value)
        if self.owns_volume:
            _destroy(self.volume)
        self.interface_matrix = self.S_V = self.V_GG = None
        self.volume = None
        self.destroyed = True

    def release_explicit_schur(self) -> None:
        """Release global/interface matrices while preserving recovery state.

        The optional global interface factor, assembled ``S_V``, augmented
        interface matrix, and owned active volume are released.  The local
        internal factors, their coupling blocks, ``V_GG`` and port data stay
        live so the recovered physical action remains available for the
        controlled post-factor memory phase.
        """

        self.release_global_factor()
        _destroy(self.S_V)
        self.S_V = None
        _destroy(self.interface_matrix)
        self.interface_matrix = None
        if self.owns_volume:
            _destroy(self.volume)
            self.volume = None

    def release_global_factor(self) -> None:
        """Release the optional global interface numeric factor only."""

        _destroy(self.interface_factor)
        self.interface_factor = None
 
 
def _petsc_is(PETSc: Any, indices: np.ndarray, comm: Any) -> Any:
    return PETSc.IS().createGeneral(
        np.asarray(indices, dtype=PETSc.IntType), comm=comm
    )
 
 
def _submatrix(matrix: Any, rows: np.ndarray) -> Any:
    from petsc4py import PETSc
 
    row_is = _petsc_is(PETSc, rows, matrix.getComm())
    col_is = _petsc_is(PETSc, rows, matrix.getComm())
    try:
        return matrix.createSubMatrix(row_is, col_is)
    finally:
        row_is.destroy()
        col_is.destroy()
 
 
def _csr_adjacency(matrix: Any) -> list[np.ndarray]:
    try:
        indptr, indices, _values = matrix.getValuesCSR()
        return [
            np.asarray(indices[indptr[row] : indptr[row + 1]])
            for row in range(len(indptr) - 1)
        ]
    except (AttributeError, RuntimeError, TypeError):
        rows: list[np.ndarray] = []
        for row in range(int(matrix.getSize()[0])):
            columns, _values = matrix.getRow(row)
            rows.append(np.asarray(columns).copy())
        return rows
 
 
def _prepare_factor(
    matrix: Any,
    factor_factory: Callable[[Any], Any],
    *,
    label: str,
    resource_sample: Callable[[], Mapping[str, Any]] | None = None,
    marker: Callable[[str, Mapping[str, Any]], None] | None = None,
    pre_numeric_gate: Callable[[Mapping[str, Any]], None] | None = None,
    post_numeric_gate: Callable[[Mapping[str, Any]], None] | None = None,
    inventory_components: Mapping[str, int]
    | Callable[[Mapping[str, Any]], Mapping[str, int]]
    | None = None,
) -> tuple[Any, dict[str, Any]]:
    def sample() -> dict[str, Any] | None:
        return dict(resource_sample()) if resource_sample is not None else None

    def emit(stage: str, facts: Mapping[str, Any]) -> None:
        if marker is not None:
            marker(stage, dict(facts))

    def inventory(facts: Mapping[str, Any]) -> dict[str, int]:
        if inventory_components is None:
            return {}
        values = (
            inventory_components(facts)
            if callable(inventory_components)
            else inventory_components
        )
        return {str(key): int(value) for key, value in values.items()}

    factor = factor_factory(matrix)
    matrix_facts = {
        "label": label,
        "rows": int(matrix.getSize()[0]),
        "matrix_info_before_factor": matrix.getInfo(),
        "pre_factor_resource": sample(),
    }
    emit("schur_factor_symbolic_started", matrix_facts)
    try:
        symbolic_started = time.perf_counter()
        factor.symbolic(matrix)
        symbolic_seconds = time.perf_counter() - symbolic_started
        symbolic_raw = factor.info((22, 29))
        memory_request = v11_memory_request_mb(symbolic_raw)
        set_memory_limit = getattr(factor, "set_memory_limit_mb", None)
        if not callable(set_memory_limit):
            raise RuntimeError("V11 factor does not expose ICNTL(23) memory setting")
        settings_getter = getattr(factor, "symbolic_memory_settings", None)
        settings = settings_getter() if callable(settings_getter) else None
        emit(
            "schur_factor_symbolic_complete",
            {
                **matrix_facts,
                "symbolic_raw": symbolic_raw,
                "symbolic_memory_settings": settings,
                "symbolic_resource": sample(),
            },
        )
        set_memory_limit(memory_request["requested_memory_limit_mb"])
        get_memory_limit = getattr(factor, "get_icntl", None)
        if not callable(get_memory_limit):
            raise RuntimeError("V11 factor does not expose ICNTL(23) readback")
        memory_readback = int(get_memory_limit(23))
        if memory_readback != int(memory_request["requested_memory_limit_mb"]):
            raise RuntimeError(
                "V11 ICNTL(23) readback differs from the requested memory package"
            )
        settings_after = settings_getter() if callable(settings_getter) else None
        if settings is not None and settings_after is not None:
            before_icntl = dict(settings.get("icntl", {}))
            after_icntl = dict(settings_after.get("icntl", {}))
            changed = {
                key: (before_icntl.get(key), after_icntl.get(key))
                for key in set(before_icntl) | set(after_icntl)
                if key != "23" and before_icntl.get(key) != after_icntl.get(key)
            }
            if changed:
                raise RuntimeError(f"V11 changed a non-memory MUMPS control: {changed}")
        symbolic_facts = {
            **matrix_facts,
            "symbolic_raw": symbolic_raw,
            "symbolic_memory_settings": settings,
            "symbolic_memory_settings_after_memory_limit": settings_after,
            "memory_request": memory_request,
            "icntl23_readback_mb": memory_readback,
            "symbolic_seconds": symbolic_seconds,
            "symbolic_resource": sample(),
        }
        symbolic_facts["inventory_components"] = inventory(symbolic_facts)
        if pre_numeric_gate is not None:
            pre_numeric_gate(symbolic_facts)
        emit(
            "schur_factor_numeric_started",
            symbolic_facts,
        )
        numeric_started = time.perf_counter()
        factor.numeric(matrix)
        numeric_seconds = time.perf_counter() - numeric_started
        numeric_raw = factor.info((22, 29))
        facts = {
            "label": label,
            "rows": int(matrix.getSize()[0]),
            "symbolic_raw": symbolic_raw,
            "symbolic_memory_settings": settings,
            "symbolic_memory_settings_after_memory_limit": settings_after,
            "memory_request": memory_request,
            "icntl23_readback_mb": memory_readback,
            "symbolic_seconds": symbolic_seconds,
            "numeric_seconds": numeric_seconds,
            "numeric_raw": numeric_raw,
            "matrix_info_after_factor": matrix.getInfo(),
            "numeric_resource": sample(),
        }
        facts["inventory_components"] = inventory(facts)
        facts["factor_solve_calls_at_factorization"] = int(
            getattr(factor, "solve_calls", 0)
        )
        if post_numeric_gate is not None:
            post_numeric_gate(facts)
        emit("schur_factor_numeric_complete", {"label": label, **facts})
        return factor, facts
    except BaseException:
        _destroy(factor)
        raise
 
 
def _matrix_values(
    matrix: Any,
    rows: np.ndarray,
    columns: np.ndarray,
) -> np.ndarray:
    if not rows.size or not columns.size:
        return np.empty((rows.size, columns.size), dtype=np.complex128)
    return np.asarray(
        matrix.getValues(rows.tolist(), columns.tolist()),
        dtype=np.complex128,
    )
 
 
def build_physical_interface_schur(
    volume: Any,
    partition: SchurPartition,
    carrier: Any,
    *,
    port_data: list[dict[str, Any]] | None = None,
    factor_factory: Callable[[Any], Any] | None = None,
    batch_columns: int = SCHUR_BATCH_COLUMNS,
    resource_sample: Callable[[], Mapping[str, Any]] | None = None,
    marker: Callable[[str, Mapping[str, Any]], None] | None = None,
    pre_numeric_gate: Callable[[Mapping[str, Any]], None] | None = None,
    post_numeric_gate: Callable[[Mapping[str, Any]], None] | None = None,
    allocation_gate: Callable[[str, Mapping[str, Any]], None] | None = None,
    owns_volume: bool = True,
) -> PhysicalInterfaceSchur:
    """Assemble sparse ``S_V`` and ``[S_V B; -D H]`` from an active V matrix."""
 
    from petsc4py import PETSc
    from .fullspace_v17_p3_oracle import _MumpsFactor
 
    if volume.getComm().getSize() != 1:
        raise ValueError("V14 Schur assembly is fixed to MPI1")
    if int(volume.getSize()[0]) != partition.active_rows:
        raise ValueError("active volume matrix does not match the partition")
    batch_columns = int(batch_columns)
    if batch_columns <= 0 or batch_columns > SCHUR_BATCH_COLUMNS:
        raise ValueError("Schur assembly batches must be at most 32 columns")
    factor_factory = _MumpsFactor if factor_factory is None else factor_factory
    if port_data is None:
        _support, port_data = _carrier_support(carrier, partition.storage_size)
    full_to_active = -np.ones(partition.storage_size, dtype=np.int64)
    full_to_active[partition.active_full_indices] = np.arange(
        partition.active_rows,
        dtype=np.int64,
    )
    gamma = partition.gamma_active_indices
    gamma_position = {int(value): index for index, value in enumerate(gamma)}
    adjacency = _csr_adjacency(volume)
    internal: list[InternalFactor] = []
    S_V = V_GG = interface_matrix = None
    try:
        # V_GG is a separate live sparse object.  Let the caller account for
        # its bounded CSR payload before PETSc allocates it.
        if allocation_gate is not None:
            vgg_nnz = sum(
                max(
                    1,
                    sum(
                        1
                        for column in adjacency[int(row)]
                        if int(column) in gamma_position
                    ),
                )
                for row in gamma
            )
            allocation_gate(
                "V_GG",
                {
                    "rows": partition.gamma_rows,
                    "nnz": int(vgg_nnz),
                    "matrix_payload_bytes": int(
                        _sparse_payload_bytes(vgg_nnz, partition.gamma_rows, PETSc)
                    ),
                    "workspace_bytes": 0,
                },
            )
        V_GG = _submatrix(volume, gamma)
        for block_index, indices in enumerate(partition.internal_blocks_active):
            if indices.size > MAX_INTERNAL_ROWS:
                raise ValueError(f"internal block {block_index} exceeds 2048 rows")
            block_set = set(indices.tolist())
            grows = np.asarray(
                [
                    row_index
                    for row_index, row in enumerate(gamma)
                    if block_set.intersection(adjacency[int(row)])
                ],
                dtype=np.int64,
            )
            gcols = np.asarray(
                sorted(
                    {
                        gamma_position[column]
                        for row in indices
                        for column in adjacency[int(row)]
                        if column in gamma_position
                    }
                ),
                dtype=np.int64,
            )
            if allocation_gate is not None:
                coupling_bytes = int(
                    (grows.size * indices.size + indices.size * gcols.size)
                    * np.dtype(PETSc.ScalarType).itemsize
                )
                allocation_gate(
                    f"internal_coupling_{block_index}",
                    {
                        "block_index": block_index,
                        "rows": int(indices.size),
                        "grows": int(grows.size),
                        "gcols": int(gcols.size),
                        "coupling_bytes": coupling_bytes,
                        "index_bytes": int(
                            indices.nbytes + grows.nbytes + gcols.nbytes
                        ),
                        "workspace_bytes": int(
                            (grows.size + gcols.size)
                            * np.dtype(PETSc.ScalarType).itemsize
                        ),
                    },
                )
            A_gi = _matrix_values(volume, gamma[grows], indices)
            A_i_g = _matrix_values(volume, indices, gamma[gcols])
            Aii = _submatrix(volume, indices)
            try:
                factor, factor_facts = _prepare_factor(
                    Aii,
                    factor_factory,
                    label=f"internal_{block_index}",
                    resource_sample=resource_sample,
                    marker=marker,
                    pre_numeric_gate=pre_numeric_gate,
                    post_numeric_gate=post_numeric_gate,
                    inventory_components=lambda _facts, A_gi=A_gi, A_i_g=A_i_g, indices=indices, grows=grows, gcols=gcols: {
                        "coupling_bytes": int(A_gi.nbytes + A_i_g.nbytes),
                        "index_bytes": int(indices.nbytes + grows.nbytes + gcols.nbytes),
                        "workspace_bytes": int(2 * indices.size * np.dtype(np.complex128).itemsize),
                    },
                )
            except BaseException:
                _destroy(Aii)
                raise
            item = InternalFactor(
                block_index=block_index,
                indices=indices.copy(),
                matrix=Aii,
                factor=factor,
                grows=grows,
                gcols=gcols,
                A_gi=A_gi,
                A_i_g=A_i_g,
                symbolic_raw=factor_facts["symbolic_raw"],
                numeric_raw=factor_facts["numeric_raw"],
                memory_request=factor_facts["memory_request"],
                symbolic_seconds=float(factor_facts["symbolic_seconds"]),
                numeric_seconds=float(factor_facts["numeric_seconds"]),
            )
            internal.append(item)

        # Generate a bounded Gamma-row union on demand.  Only the current row
        # is materialized; ``row_nnz`` is the small preallocation ledger used
        # for both the volume Schur and the augmented interface matrix.
        internal_columns_by_grow: dict[int, list[np.ndarray]] = {}
        for item in internal:
            for grow in item.grows:
                internal_columns_by_grow.setdefault(int(grow), []).append(item.gcols)

        def gamma_row_columns(row_index: int) -> np.ndarray:
            row = int(gamma[row_index])
            pieces: list[np.ndarray] = []
            direct = np.asarray(
                [
                    gamma_position[int(column)]
                    for column in adjacency[row]
                    if int(column) in gamma_position
                ],
                dtype=np.int64,
            )
            if direct.size:
                pieces.append(direct)
            pieces.extend(internal_columns_by_grow.get(row_index, ()))
            pieces.append(np.asarray([row_index], dtype=np.int64))
            return np.unique(np.concatenate(pieces)).astype(PETSc.IntType, copy=False)

        row_nnz = np.empty(partition.gamma_rows, dtype=PETSc.IntType)
        for row_index in range(partition.gamma_rows):
            columns = gamma_row_columns(row_index)
            row_nnz[row_index] = max(1, int(columns.size))
            del columns
        if allocation_gate is not None:
            allocation_gate(
                "S_V",
                {
                    "rows": partition.gamma_rows,
                    "nnz": int(np.sum(row_nnz, dtype=np.int64)),
                    "matrix_payload_bytes": int(
                        _sparse_payload_bytes(
                            int(np.sum(row_nnz, dtype=np.int64)),
                            partition.gamma_rows,
                            PETSc,
                        )
                    ),
                    "workspace_bytes": int(
                        max(
                            1,
                            max(
                                (
                                    (
                                        2 * item.indices.size + item.grows.size
                                    )
                                    * min(batch_columns, item.gcols.size)
                                    * np.dtype(PETSc.ScalarType).itemsize
                                    + 1 * 1024**2
                                    for item in internal
                                ),
                                default=0,
                            ),
                        )
                    ),
                },
            )
        S_V = PETSc.Mat().createAIJ(
            [partition.gamma_rows, partition.gamma_rows],
            nnz=row_nnz,
            comm=volume.getComm(),
        )
        S_V.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR, True)
        for row_index, row in enumerate(gamma):
            base_columns = gamma_row_columns(row_index)
            if base_columns.size:
                values = _matrix_values(
                    volume,
                    np.asarray([row], dtype=PETSc.IntType),
                    gamma[base_columns],
                )[0]
                S_V.setValues(
                    [row_index],
                    base_columns.tolist(),
                    values,
                    addv=PETSc.InsertMode.ADD_VALUES,
                )
            elif partition.gamma_rows:
                S_V.setValue(
                    row_index,
                    row_index,
                    0.0,
                    addv=PETSc.InsertMode.ADD_VALUES,
                )
            del base_columns
        for item in internal:
            if not item.grows.size or not item.gcols.size:
                continue
            for start in range(0, item.gcols.size, batch_columns):
                stop = min(start + batch_columns, item.gcols.size)
                rhs_values = item.A_i_g[:, start:stop]
                solutions = np.column_stack(
                    [
                        _solve_array_with_factor(item, rhs_values[:, column])
                        for column in range(rhs_values.shape[1])
                    ]
                )
                contribution = item.A_gi @ solutions
                S_V.setValues(
                    item.grows.tolist(),
                    item.gcols[start:stop].tolist(),
                    -contribution,
                    addv=PETSc.InsertMode.ADD_VALUES,
                )
        S_V.assemble()
        for item in internal:
            item.solve_calls_at_build = int(getattr(item.factor, "solve_calls", 0))
        port_maps = _compact_port_data(
            port_data,
            full_to_active,
            gamma_position,
        )
        # ``row_nnz`` is the exact preallocation ledger for S_V and can be
        # reused for the augmented volume rows without a full CSR copy.
        b_port_columns: dict[int, set[int]] = {}
        for port, entry in enumerate(port_maps):
            interface_column = partition.gamma_rows + port
            for row in entry["b_gamma"]:
                b_port_columns.setdefault(int(row), set()).add(interface_column)
        interface_nnz = np.empty(
            partition.gamma_rows + len(port_maps), dtype=PETSc.IntType
        )
        for row in range(partition.gamma_rows):
            interface_nnz[row] = max(
                1, int(row_nnz[row]) + len(b_port_columns.get(row, ()))
            )
        for port, entry in enumerate(port_maps):
            d_columns = np.unique(entry["d_gamma"])
            interface_nnz[partition.gamma_rows + port] = max(
                1, int(d_columns.size) + 1
            )
        if allocation_gate is not None:
            allocation_gate(
                "interface_matrix",
                {
                    "rows": int(interface_nnz.size),
                    "nnz": int(np.sum(interface_nnz, dtype=np.int64)),
                    "matrix_payload_bytes": int(
                        _sparse_payload_bytes(
                            int(np.sum(interface_nnz, dtype=np.int64)),
                            int(interface_nnz.size),
                            PETSc,
                        )
                    ),
                    "workspace_bytes": int(interface_nnz.size * np.dtype(PETSc.ScalarType).itemsize),
                },
            )
        del row_nnz, b_port_columns
        # Keep the row helper's closure valid while releasing its large graph
        # backing objects before the augmented matrix is populated.
        internal_columns_by_grow.clear()
        adjacency.clear()
        interface_matrix = PETSc.Mat().createAIJ(
            [partition.gamma_rows + len(port_maps)] * 2,
            nnz=interface_nnz,
            comm=volume.getComm(),
        )
        interface_matrix.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR, True)
        for row in range(partition.gamma_rows):
            columns, values = S_V.getRow(row)
            if len(columns):
                interface_matrix.setValues(
                    [row],
                    np.asarray(columns).tolist(),
                    values,
                )
        for port, entry in enumerate(port_maps):
            interface_row = partition.gamma_rows + port
            if entry["b_gamma"].size:
                interface_matrix.setValues(
                    entry["b_gamma"].tolist(),
                    [interface_row],
                    entry["b_values"][:, None],
                )
            if entry["d_gamma"].size:
                interface_matrix.setValues(
                    [interface_row],
                    entry["d_gamma"].tolist(),
                    -entry["d_values"][None, :],
                )
            interface_matrix.setValue(
                interface_row,
                interface_row,
                entry["normalization_h"],
            )
        interface_matrix.assemble()
        factor_facts = {
            "internal": [
                {
                    "block_index": item.block_index,
                    "rows": int(item.indices.size),
                    "grows": int(item.grows.size),
                    "gcols": int(item.gcols.size),
                    "symbolic_raw": item.symbolic_raw,
                    "numeric_raw": item.numeric_raw,
                    "memory_request": item.memory_request,
                    "symbolic_seconds": item.symbolic_seconds,
                    "numeric_seconds": item.numeric_seconds,
                    "matrix_info": item.matrix.getInfo(),
                    "solve_calls_at_build": item.solve_calls_at_build,
                    "coupling_bytes": int(item.A_gi.nbytes + item.A_i_g.nbytes),
                    "index_bytes": int(
                        item.indices.nbytes + item.grows.nbytes + item.gcols.nbytes
                    ),
                }
                for item in internal
            ],
            "S_V": S_V.getInfo(),
            "interface": {
                "rows": int(interface_matrix.getSize()[0]),
                "matrix_info": interface_matrix.getInfo(),
                "factor": None,
                "factor_status": "NOT_BUILT_BY_CORE",
            },
            "batch_columns": batch_columns,
        }
        return PhysicalInterfaceSchur(
            volume=volume,
            partition=partition,
            S_V=S_V,
            V_GG=V_GG,
            interface_matrix=interface_matrix,
            internal=internal,
            interface_factor=None,
            port_data=port_maps,
            factor_facts=factor_facts,
            owns_volume=bool(owns_volume),
        )
    except BaseException:
        for item in internal:
            _destroy(item.factor)
            _destroy(item.matrix)
        for value in (interface_matrix, S_V, V_GG):
            _destroy(value)
        raise


def _solve_array_with_factor(
    item: InternalFactor,
    values: np.ndarray,
) -> np.ndarray:
    rhs = item.matrix.createVecRight()
    solution = item.matrix.createVecRight()
    try:
        rhs.array[:] = values
        item.factor.solve_repeated(rhs, solution)
        return np.asarray(solution.array).copy()
    finally:
        rhs.destroy()
        solution.destroy()


def factorize_interface_schur(
    core: PhysicalInterfaceSchur,
    *,
    factor_factory: Callable[[Any], Any] | None = None,
    resource_sample: Callable[[], Mapping[str, Any]] | None = None,
    marker: Callable[[str, Mapping[str, Any]], None] | None = None,
    pre_numeric_gate: Callable[[Mapping[str, Any]], None] | None = None,
    post_numeric_gate: Callable[[Mapping[str, Any]], None] | None = None,
    inventory_components: Mapping[str, int]
    | Callable[[Mapping[str, Any]], Mapping[str, int]]
    | None = None,
) -> dict[str, Any]:
    """Optionally attach the global interface factor to an assembled core.

    Keeping this operation separate is intentional: a resource-controlled
    global numeric phase must not invalidate the already checked local
    elimination, sparse Schur action, adjoint and recovery paths.
    """

    if core.destroyed:
        raise RuntimeError("cannot factorize a destroyed Schur core")
    if core.interface_factor is not None:
        raise RuntimeError("the global interface factor is already attached")
    from .fullspace_v17_p3_oracle import _MumpsFactor

    factor_factory = _MumpsFactor if factor_factory is None else factor_factory
    factor, facts = _prepare_factor(
        core.interface_matrix,
        factor_factory,
        label="interface",
        resource_sample=resource_sample,
        marker=marker,
        pre_numeric_gate=pre_numeric_gate,
        post_numeric_gate=post_numeric_gate,
        inventory_components=inventory_components,
    )
    core.interface_factor = factor
    core.factor_facts["interface"]["factor"] = facts
    core.factor_facts["interface"]["factor_status"] = "NUMERIC_READY"
    return facts


def _compact_port_data(
    port_data: Iterable[Mapping[str, Any]],
    full_to_active: np.ndarray,
    gamma_position: Mapping[int, int],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for entry in port_data:
        b_rows = np.asarray(entry["coupling_rows"], dtype=np.int64)
        b_values = np.asarray(entry["coupling_values"], dtype=np.complex128)
        d_rows = np.asarray(entry["projection_rows"], dtype=np.int64)
        d_values = np.asarray(entry["projection_values"], dtype=np.complex128)
        b_keep = _nonzero_rows(b_values)
        d_keep = _nonzero_rows(d_values)
        b_active = full_to_active[b_rows[b_keep]]
        d_active = full_to_active[d_rows[d_keep]]
        if np.any(b_active < 0) or np.any(d_active < 0):
            raise ValueError("port support contains an inactive row")
        b_gamma = np.asarray(
            [gamma_position[int(value)] for value in b_active],
            dtype=np.int64,
        )
        d_gamma = np.asarray(
            [gamma_position[int(value)] for value in d_active],
            dtype=np.int64,
        )
        result.append(
            {
                "port": int(entry["port"]),
                "b_gamma": b_gamma,
                "b_values": b_values[b_keep],
                "b_full": b_rows[b_keep],
                "d_gamma": d_gamma,
                "d_values": d_values[d_keep],
                "d_full": d_rows[d_keep],
                "normalization_h": complex(entry["normalization_h"]),
            }
        )
    return result


__all__ = [
    "InternalFactor",
    "MAX_INTERFACE_ROWS",
    "MAX_INTERFACE_WORKSPACE_BYTES",
    "MAX_INTERNAL_ROWS",
    "PhysicalInterfaceSchur",
    "SCHUR_PROFILE",
    "SCHUR_SCHEMA",
    "SchurPartition",
    "build_interface_partition",
    "build_physical_interface_schur",
    "factorize_interface_schur",
    "v11_memory_request_mb",
]

 
 
 
 
