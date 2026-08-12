"""Research-only owner-local full-space p4/p6 transfer.

The carrier keeps one reference ``I46`` and compact cell/ownership metadata.
It never assembles a transfer matrix or gathers numeric finite-element values.
PETSc vectors and the optional DOLFINx-MPC objects are borrowed by ``apply``;
the NumPy metadata owned by this module is copied and read-only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from types import MappingProxyType
from typing import Any, Mapping

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from ..adaptivity.exact_sequence_variable_p import (
    HexaEntityDegreeMap,
    VariablePReferenceSpace,
    build_variable_p_reference_space,
)

__all__ = (
    "P4P6MPCCarrier",
    "OwnerLocalP4P6Transfer",
    "build_owner_local_p4_p6_transfer",
)


_P4_DIMENSION = 300
_P6_DIMENSION = 882
_COMPLEX_ITEMSIZE = np.dtype(np.complex128).itemsize


def _readonly_copy(values: Any, dtype: np.dtype[Any]) -> np.ndarray:
    array = np.array(values, dtype=dtype, copy=True, order="C")
    array.setflags(write=False)
    return array


def _array_sha256(array: np.ndarray) -> str:
    contiguous = np.ascontiguousarray(array)
    return hashlib.sha256(contiguous.tobytes(order="C")).hexdigest()


def _json_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _retained_numeric_payload_components(
    p4_reference: VariablePReferenceSpace,
    p6_reference: VariablePReferenceSpace,
    cells: tuple[_OwnerCellStencil, ...],
    carriers: tuple[P4P6MPCCarrier, P4P6MPCCarrier],
) -> dict[str, int]:
    """Count the long-lived numeric arrays without counting Python/C++ overhead."""

    components: dict[str, int] = {}
    seen: set[int] = set()

    def add(name: str, array: np.ndarray) -> None:
        identity = id(array)
        components[name] = 0 if identity in seen else int(array.nbytes)
        seen.add(identity)

    for prefix, reference in (("p4_reference", p4_reference), ("p6_reference", p6_reference)):
        add(f"{prefix}_hcurl_to_p6_bytes", reference.hcurl_to_p6)
        add(f"{prefix}_h1_to_q6_bytes", reference.h1_to_q6)
        add(f"{prefix}_discrete_gradient_bytes", reference.discrete_gradient)
        add(f"{prefix}_trace_dofs_bytes", reference.trace_dofs)
        add(f"{prefix}_interior_dofs_bytes", reference.interior_dofs)
    for index, cell in enumerate(cells):
        add(f"stencil_{index}_p4_local_dofs_bytes", cell.p4_local_dofs)
        add(f"stencil_{index}_p6_local_dofs_bytes", cell.p6_local_dofs)
        add(
            f"stencil_{index}_selected_p6_positions_bytes",
            cell.selected_p6_positions,
        )
    for prefix, carrier in zip(("p4_mpc", "p6_mpc"), carriers, strict=True):
        add(f"{prefix}_slave_indices_bytes", carrier.slave_indices)
        add(f"{prefix}_slave_offsets_bytes", carrier.slave_offsets)
        add(f"{prefix}_master_indices_bytes", carrier.master_indices)
        add(f"{prefix}_coefficients_bytes", carrier.coefficients)
    return components


def _space_index_layout(space: Any) -> tuple[int, int, int]:
    element = space.element.basix_element
    if "hexahedron" not in str(element.cell_type).lower():
        raise ValueError("M1 transfer requires hexahedral spaces")
    family = str(getattr(element.family, "name", element.family)).lower()
    if family not in {"n1curl", "n1e"}:
        raise ValueError("M1 transfer requires scalar N1curl spaces")
    if int(space.dofmap.index_map_bs) != 1:
        raise ValueError("M1 transfer requires scalar-blocked dofmaps")
    index_map = space.dofmap.index_map
    return (
        int(index_map.size_global),
        int(index_map.size_local),
        int(index_map.size_local + index_map.num_ghosts),
    )


def _original_local_prefix_preserved(
    original_space: Any,
    extended_space: Any,
) -> bool:
    """Check that finalized MPC storage keeps the original local row prefix."""

    original_map = original_space.dofmap.index_map
    extended_map = extended_space.dofmap.index_map
    original_local_rows = int(original_map.size_local + original_map.num_ghosts)
    extended_local_rows = int(extended_map.size_local + extended_map.num_ghosts)
    if extended_local_rows < original_local_rows:
        return False
    local_rows = np.arange(original_local_rows, dtype=np.int32)
    original_global = np.asarray(
        original_map.local_to_global(local_rows),
        dtype=np.int64,
    )
    extended_global = np.asarray(
        extended_map.local_to_global(local_rows),
        dtype=np.int64,
    )
    return original_global.shape == extended_global.shape and np.array_equal(
        original_global,
        extended_global,
    )


def _owned_global_start(index_map: Any) -> int:
    owned = int(index_map.size_local)
    if owned == 0:
        return 0
    local = np.arange(owned, dtype=np.int32)
    global_rows = np.asarray(index_map.local_to_global(local), dtype=np.int64)
    expected = np.arange(int(global_rows[0]), int(global_rows[0]) + owned)
    if not np.array_equal(global_rows, expected):
        raise RuntimeError("DOLFINx owned row range is not contiguous")
    return int(global_rows[0])


@dataclass(frozen=True)
class P4P6MPCCarrier:
    """Owned local rank-one MPC lift and its exact conjugate transpose.

    Rows and masters are local indices in the DOLFINx MPC vector layout.  The
    global row count is provenance only; it is not part of the reusable I46
    transform identity.  ``from_dolfinx_mpc`` consumes the already-built
    sparse Floquet relation once and does not gather vector values.
    """

    global_rows: int
    owned_rows: int
    local_rows: int
    slave_indices: np.ndarray
    slave_offsets: np.ndarray
    master_indices: np.ndarray
    coefficients: np.ndarray
    owned_global_start: int = 0
    audit: Mapping[str, Any] = field(init=False)

    def __post_init__(self) -> None:
        global_rows = int(self.global_rows)
        owned_rows = int(self.owned_rows)
        local_rows = int(self.local_rows)
        owned_global_start = int(self.owned_global_start)
        if not (
            0 <= owned_global_start <= owned_global_start + owned_rows <= global_rows
        ):
            raise ValueError("MPC ownership range is inconsistent")
        if not 0 <= owned_rows <= local_rows:
            raise ValueError("MPC row layout is inconsistent")
        slaves = _readonly_copy(self.slave_indices, np.dtype(np.int32))
        offsets = _readonly_copy(self.slave_offsets, np.dtype(np.int32))
        masters = _readonly_copy(self.master_indices, np.dtype(np.int32))
        coefficients = _readonly_copy(
            self.coefficients,
            np.dtype(np.complex128),
        )
        if offsets.shape != (local_rows + 1,):
            raise ValueError("MPC offsets do not cover local rows")
        if offsets[0] != 0 or np.any(np.diff(offsets) < 0):
            raise ValueError("MPC offsets are not monotone")
        if int(offsets[-1]) != len(masters) or len(masters) != len(coefficients):
            raise ValueError("MPC master/coefficient arrays do not close")
        if slaves.ndim != 1 or len(np.unique(slaves)) != len(slaves):
            raise ValueError("MPC slave rows are duplicated")
        if np.any(slaves < 0) or np.any(slaves >= local_rows):
            raise ValueError("MPC slave row is outside local storage")
        if np.any(masters < 0) or np.any(masters >= local_rows):
            raise ValueError("MPC master row is outside local storage")
        slave_set = set(map(int, slaves))
        for row in slaves:
            start = int(offsets[int(row)])
            stop = int(offsets[int(row) + 1])
            if any(int(master) in slave_set for master in masters[start:stop]):
                raise NotImplementedError("chained MPC rows are unsupported")
        if not np.isfinite(coefficients).all():
            raise ValueError("MPC coefficients are not finite")
        object.__setattr__(self, "global_rows", global_rows)
        object.__setattr__(self, "owned_rows", owned_rows)
        object.__setattr__(self, "local_rows", local_rows)
        object.__setattr__(self, "owned_global_start", owned_global_start)
        object.__setattr__(self, "slave_indices", slaves)
        object.__setattr__(self, "slave_offsets", offsets)
        object.__setattr__(self, "master_indices", masters)
        object.__setattr__(self, "coefficients", coefficients)
        pattern = {
            "schema": "task037.m1.local-mpc-carrier.v1",
            "global_rows": global_rows,
            "owned_rows": owned_rows,
            "local_rows": local_rows,
            "owned_global_start": owned_global_start,
            "slave_indices_sha256": _array_sha256(slaves),
            "slave_offsets_sha256": _array_sha256(offsets),
            "master_indices_sha256": _array_sha256(masters),
            "coefficients_sha256": _array_sha256(coefficients),
        }
        object.__setattr__(
            self,
            "audit",
            MappingProxyType(
                {
                    **pattern,
                    "constraint_pattern_sha256": _json_sha256(pattern),
                    "local_slave_count": int(len(slaves)),
                    "constraint_nnz": int(len(masters)),
                    "phase_coefficients_applied_once": True,
                    "global_constraint_matrix_materialized": False,
                    "numeric_allgather": False,
                }
            ),
        )

    @classmethod
    def identity(cls, space: Any) -> "P4P6MPCCarrier":
        global_rows, owned_rows, local_rows = _space_index_layout(space)
        index_map = space.dofmap.index_map
        owned_start = _owned_global_start(index_map)
        return cls(
            global_rows=global_rows,
            owned_rows=owned_rows,
            local_rows=local_rows,
            slave_indices=np.empty(0, dtype=np.int32),
            slave_offsets=np.zeros(local_rows + 1, dtype=np.int32),
            master_indices=np.empty(0, dtype=np.int32),
            coefficients=np.empty(0, dtype=np.complex128),
            owned_global_start=owned_start,
        )

    @classmethod
    def from_relations(
        cls,
        *,
        global_rows: int,
        owned_rows: int,
        local_rows: int,
        relations: Mapping[int, tuple[np.ndarray, np.ndarray]],
        owned_global_start: int = 0,
    ) -> "P4P6MPCCarrier":
        offsets = np.zeros(int(local_rows) + 1, dtype=np.int32)
        masters: list[int] = []
        coefficients: list[complex] = []
        for row in range(int(local_rows)):
            relation = relations.get(row)
            if relation is not None:
                row_masters, row_coefficients = relation
                row_masters = np.asarray(row_masters, dtype=np.int32)
                row_coefficients = np.asarray(
                    row_coefficients,
                    dtype=np.complex128,
                )
                if row_masters.ndim != 1 or row_coefficients.shape != row_masters.shape:
                    raise ValueError("one MPC relation has incompatible arrays")
                masters.extend(map(int, row_masters))
                coefficients.extend(map(complex, row_coefficients))
            offsets[row + 1] = len(masters)
        return cls(
            global_rows=global_rows,
            owned_rows=owned_rows,
            local_rows=local_rows,
            slave_indices=np.asarray(sorted(relations), dtype=np.int32),
            slave_offsets=offsets,
            master_indices=np.asarray(masters, dtype=np.int32),
            coefficients=np.asarray(coefficients, dtype=np.complex128),
            owned_global_start=owned_global_start,
        )

    @classmethod
    def from_dolfinx_mpc(cls, mpc: Any) -> "P4P6MPCCarrier":
        """Copy one existing DOLFINx-MPC relation into local immutable arrays."""

        index_map = mpc.function_space.dofmap.index_map
        local_rows = int(index_map.size_local + index_map.num_ghosts)
        owned_rows = int(index_map.size_local)
        coefficients, source_offsets = mpc.coefficients()
        coefficients = np.asarray(coefficients, dtype=np.complex128)
        source_offsets = np.asarray(source_offsets, dtype=np.int32)
        is_slave = np.asarray(mpc.is_slave, dtype=bool)
        if source_offsets.size < local_rows + 1 or is_slave.size < local_rows:
            raise ValueError("DOLFINx MPC metadata does not cover local rows")
        relations: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        for row in np.asarray(mpc.slaves, dtype=np.int32):
            row = int(row)
            start = int(source_offsets[row])
            stop = int(source_offsets[row + 1])
            masters = np.asarray(mpc.masters.links(row), dtype=np.int32)
            values = np.array(coefficients[start:stop], copy=True, order="C")
            if masters.size != values.size or not bool(is_slave[row]):
                raise ValueError("DOLFINx MPC row metadata is inconsistent")
            relations[row] = (masters, values)
        return cls.from_relations(
            global_rows=int(index_map.size_global),
            owned_rows=owned_rows,
            local_rows=local_rows,
            relations=relations,
            owned_global_start=_owned_global_start(index_map),
        )

    def lift_in_place(
        self,
        values: np.ndarray,
        *,
        owned_only: bool = False,
    ) -> None:
        if values.shape != (self.local_rows,):
            raise ValueError("MPC lift array has the wrong local size")
        for row in self.slave_indices:
            row = int(row)
            if owned_only and row >= self.owned_rows:
                continue
            start = int(self.slave_offsets[row])
            stop = int(self.slave_offsets[row + 1])
            values[row] = np.dot(
                self.coefficients[start:stop],
                values[self.master_indices[start:stop]],
            )

    def adjoint_in_place(
        self,
        values: np.ndarray,
        *,
        owned_only: bool = False,
    ) -> None:
        if values.shape != (self.local_rows,):
            raise ValueError("MPC adjoint array has the wrong local size")
        rows = np.asarray(
            self.slave_indices[self.slave_indices < self.owned_rows]
            if owned_only
            else self.slave_indices,
            dtype=np.int32,
        )
        original = np.array(values[rows], dtype=np.complex128, copy=True, order="C")
        for row, original_value in zip(rows, original, strict=True):
            row = int(row)
            start = int(self.slave_offsets[row])
            stop = int(self.slave_offsets[row + 1])
            values[self.master_indices[start:stop]] += (
                np.conjugate(self.coefficients[start:stop]) * original_value
            )
            values[row] = 0.0


@dataclass(frozen=True)
class _OwnerCellStencil:
    local_cell: int
    global_cell: int
    cell_info: int
    p4_local_dofs: np.ndarray
    p6_local_dofs: np.ndarray
    selected_p6_positions: np.ndarray


@dataclass
class OwnerLocalP4P6Transfer:
    """Owner-local full-space p4/p6 transfer with a borrowed Vec interface."""

    p4_space: Any
    p6_space: Any
    p4_constraints: P4P6MPCCarrier
    p6_constraints: P4P6MPCCarrier
    reference_space: VariablePReferenceSpace
    _cells: tuple[_OwnerCellStencil, ...]
    audit: Mapping[str, Any]
    _p6_adjoint_work: PETSc.Vec | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _destroyed: bool = field(default=False, init=False, repr=False)

    def _check_live(self) -> None:
        if self._destroyed:
            raise RuntimeError("M1 owner-local transfer has been destroyed")

    def _check_vector_layout(
        self,
        vector: PETSc.Vec,
        carrier: P4P6MPCCarrier,
    ) -> None:
        self._check_live()
        if int(vector.getSize()) != carrier.global_rows:
            raise ValueError("vector global size does not match transfer layout")
        with vector.localForm() as local:
            if np.asarray(local.array_r).shape != (carrier.local_rows,):
                raise ValueError(
                    "vector local owned/ghost layout does not match transfer"
                )

    def apply_reference(self, values: np.ndarray, *, cell_info: int) -> np.ndarray:
        """Apply production I46 plus the production DOLFINx orientation."""

        return self.reference_space.active_to_p6_oriented(
            np.asarray(values, dtype=np.complex128),
            cell_info=int(cell_info),
        )

    def apply_reference_adjoint(
        self,
        values: np.ndarray,
        *,
        cell_info: int,
    ) -> np.ndarray:
        return self.reference_space.project_p6_oriented_dual(
            np.asarray(values, dtype=np.complex128),
            cell_info=int(cell_info),
        )

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        """Apply p4→p6 using ghost-forward, lift, local I46, and owner writes."""

        self._check_vector_layout(source, self.p4_constraints)
        self._check_vector_layout(target, self.p6_constraints)
        source.ghostUpdate(
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )
        with source.localForm() as source_local:
            p4_values = np.array(
                source_local.array_r,
                dtype=np.complex128,
                copy=True,
                order="C",
            )
        self.p4_constraints.lift_in_place(p4_values)
        target.set(0.0)
        with target.localForm() as target_local:
            target_values = target_local.array_w
            for cell in self._cells:
                local_p6 = self.apply_reference(
                    p4_values[cell.p4_local_dofs],
                    cell_info=cell.cell_info,
                )
                positions = cell.selected_p6_positions
                target_values[cell.p6_local_dofs[positions]] = local_p6[positions]
        target.ghostUpdate(
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )
        with target.localForm() as target_local:
            self.p6_constraints.lift_in_place(
                target_local.array_w,
            )
        target.ghostUpdate(
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )

    def apply_adjoint(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        """Apply the exact conjugate transpose with reverse ghost accumulation."""

        self._check_vector_layout(source, self.p6_constraints)
        self._check_vector_layout(target, self.p4_constraints)
        source.ghostUpdate(
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )
        if self._p6_adjoint_work is None:
            self._p6_adjoint_work = source.duplicate()
        p6_work = self._p6_adjoint_work
        with source.localForm() as source_local, p6_work.localForm() as work_local:
            work_local.set(0.0)
            work_local.array_w[: self.p6_constraints.owned_rows] = (
                source_local.array_r[: self.p6_constraints.owned_rows]
            )
            self.p6_constraints.adjoint_in_place(
                work_local.array_w,
                owned_only=True,
            )
        p6_work.ghostUpdate(
            addv=PETSc.InsertMode.ADD_VALUES,
            mode=PETSc.ScatterMode.REVERSE,
        )
        target.set(0.0)
        with p6_work.localForm() as work_local, target.localForm() as target_local:
            p6_values = work_local.array_r
            target_values = target_local.array_w
            target_values[:] = 0.0
            local_dual = np.zeros(_P6_DIMENSION, dtype=np.complex128)
            for cell in self._cells:
                local_dual.fill(0.0)
                positions = cell.selected_p6_positions
                local_dual[positions] = p6_values[
                    cell.p6_local_dofs[positions]
                ]
                local_p4 = self.apply_reference_adjoint(
                    local_dual,
                    cell_info=cell.cell_info,
                )
                np.add.at(target_values, cell.p4_local_dofs, local_p4)
        target.ghostUpdate(
            addv=PETSc.InsertMode.ADD_VALUES,
            mode=PETSc.ScatterMode.REVERSE,
        )
        with target.localForm() as target_local:
            target_local.array_w[self.p4_constraints.owned_rows :] = 0.0
            self.p4_constraints.adjoint_in_place(
                target_local.array_w,
                owned_only=True,
            )
        target.ghostUpdate(
            addv=PETSc.InsertMode.ADD_VALUES,
            mode=PETSc.ScatterMode.REVERSE,
        )
        target.ghostUpdate(
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )

    def destroy(self) -> None:
        """Release only the owned work Vec; spaces and caller Vecs are borrowed."""

        if self._destroyed:
            return
        if self._p6_adjoint_work is not None:
            self._p6_adjoint_work.destroy()
            self._p6_adjoint_work = None
        self._destroyed = True


def _cell_stencils(
    p4_space: Any,
    p6_space: Any,
    p6_constraints: P4P6MPCCarrier,
    *,
    p4_original_local_rows: int,
    p6_original_local_rows: int,
) -> tuple[_OwnerCellStencil, ...]:
    topology = p6_space.mesh.topology
    cell_dim = int(topology.dim)
    cell_map = topology.index_map(cell_dim)
    cell_count = int(cell_map.size_local)
    topology.create_entity_permutations()
    cell_globals = np.asarray(
        cell_map.local_to_global(np.arange(cell_count, dtype=np.int32)),
        dtype=np.int64,
    )
    cell_info = np.asarray(topology.get_cell_permutation_info(), dtype=np.uint32)
    if cell_info.size < cell_count:
        raise RuntimeError("cell permutation metadata does not cover local cells")
    occurrences: list[tuple[np.ndarray, np.ndarray]] = []
    for cell in range(cell_count):
        p4_dofs = np.array(
            p4_space.dofmap.cell_dofs(cell),
            dtype=np.int32,
            copy=True,
            order="C",
        )
        p6_dofs = np.array(
            p6_space.dofmap.cell_dofs(cell),
            dtype=np.int32,
            copy=True,
            order="C",
        )
        if p4_dofs.shape != (_P4_DIMENSION,) or p6_dofs.shape != (_P6_DIMENSION,):
            raise ValueError("M1 transfer only supports p4/p6 300/882 cell layouts")
        if (
            np.any(p4_dofs < 0)
            or np.any(p4_dofs >= int(p4_original_local_rows))
            or np.any(p6_dofs < 0)
            or np.any(p6_dofs >= int(p6_original_local_rows))
        ):
            raise ValueError("cell dofs must use the original local-row prefix")
        p6_global = np.asarray(
            p6_space.dofmap.index_map.local_to_global(p6_dofs),
            dtype=np.int64,
        )
        occurrences.append(
            (
                p6_global,
                np.full(p6_global.size, int(cell_globals[cell]), dtype=np.int64),
            )
        )

    # Only row/cell/owner metadata is exchanged here.  Numeric Vec values
    # never enter this designation collective.
    packets = p6_space.mesh.comm.allgather(
        (
            int(p6_space.mesh.comm.rank),
            int(p6_constraints.owned_global_start),
            int(p6_constraints.owned_global_start + p6_constraints.owned_rows),
            tuple(occurrences),
        )
    )
    designated: dict[int, int] = {}
    ownership_ranges = [
        (int(rank), int(start), int(stop))
        for rank, start, stop, _occurrences in packets
    ]
    for rank, _start, _stop, packet_occurrences in packets:
        for rows, cells in packet_occurrences:
            for global_row, global_cell in zip(rows, cells, strict=True):
                global_row = int(global_row)
                global_cell = int(global_cell)
                owner = next(
                    owner_rank
                    for owner_rank, owner_start, owner_stop in ownership_ranges
                    if owner_start <= global_row < owner_stop
                )
                if int(rank) != int(owner):
                    continue
                previous = designated.get(global_row)
                if previous is None or global_cell < previous:
                    designated[global_row] = global_cell

    grouped: dict[int, list[int]] = {}
    for cell, (p6_global, _cell_ids) in enumerate(occurrences):
        selected = [
            int(position)
            for position, global_row in enumerate(p6_global)
            if designated[int(global_row)] == int(cell_globals[cell])
        ]
        if selected:
            grouped[cell] = selected

    p6_start = int(p6_constraints.owned_global_start)
    p6_stop = p6_start + int(p6_constraints.owned_rows)
    selected_owned = {
        int(occurrences[cell][0][position])
        for cell, positions in grouped.items()
        for position in positions
    }
    expected = set(range(p6_start, p6_stop))
    if selected_owned != expected:
        raise RuntimeError(
            "owner-local p6 designation does not cover owned rows: "
            f"missing={sorted(expected - selected_owned)[:8]}, "
            f"extra={sorted(selected_owned - expected)[:8]}"
        )

    cells: list[_OwnerCellStencil] = []
    for local_cell in sorted(grouped):
        p4_dofs = np.array(
            p4_space.dofmap.cell_dofs(local_cell),
            dtype=np.int32,
            copy=True,
            order="C",
        )
        p6_dofs = np.array(
            p6_space.dofmap.cell_dofs(local_cell),
            dtype=np.int32,
            copy=True,
            order="C",
        )
        selected = np.sort(np.asarray(grouped[local_cell], dtype=np.int32))
        selected_global = np.asarray(
            occurrences[local_cell][0][selected],
            dtype=np.int64,
        )
        if np.any(selected_global < p6_start) or np.any(selected_global >= p6_stop):
            raise RuntimeError("designated p6 cell rows are not locally owned")
        for array in (p4_dofs, p6_dofs, selected):
            array.setflags(write=False)
        cells.append(
            _OwnerCellStencil(
                local_cell=local_cell,
                global_cell=int(cell_globals[local_cell]),
                cell_info=int(cell_info[local_cell]),
                p4_local_dofs=p4_dofs,
                p6_local_dofs=p6_dofs,
                selected_p6_positions=selected,
            )
        )
    return tuple(cells)


def build_owner_local_p4_p6_transfer(
    p4_space: Any,
    p6_space: Any,
    *,
    p4_mpc: Any | None = None,
    p6_mpc: Any | None = None,
) -> OwnerLocalP4P6Transfer:
    """Build the bounded owner-local p4↔p6 full-space transfer.

    ``p4_space`` and ``p6_space`` are the original scalar-blocked DOLFINx
    spaces.  If Floquet MPCs are present, pass their already-built ``mpc``
    objects; only their local rank-one relation metadata is copied.
    """

    if p4_space.mesh is not p6_space.mesh:
        raise ValueError("p4 and p6 transfer spaces must share one mesh")
    p4_layout = _space_index_layout(p4_space)
    p6_layout = _space_index_layout(p6_space)
    if p4_layout[0] <= 0 or p6_layout[0] <= 0:
        raise ValueError("invalid p4/p6 global layouts")
    if int(p4_space.element.space_dimension) != _P4_DIMENSION:
        raise ValueError("M1 transfer requires p4 cell dimension 300")
    if int(p6_space.element.space_dimension) != _P6_DIMENSION:
        raise ValueError("M1 transfer requires p6 cell dimension 882")
    p4_constraints = (
        P4P6MPCCarrier.from_dolfinx_mpc(p4_mpc)
        if p4_mpc is not None
        else P4P6MPCCarrier.identity(p4_space)
    )
    p6_constraints = (
        P4P6MPCCarrier.from_dolfinx_mpc(p6_mpc)
        if p6_mpc is not None
        else P4P6MPCCarrier.identity(p6_space)
    )
    if p4_constraints.global_rows != p4_layout[0]:
        raise ValueError("p4 MPC layout does not match the p4 space")
    if p6_constraints.global_rows != p6_layout[0]:
        raise ValueError("p6 MPC layout does not match the p6 space")
    p4_prefix_preserved = _original_local_prefix_preserved(
        p4_space,
        p4_mpc.function_space if p4_mpc is not None else p4_space,
    )
    p6_prefix_preserved = _original_local_prefix_preserved(
        p6_space,
        p6_mpc.function_space if p6_mpc is not None else p6_space,
    )
    if not p4_prefix_preserved:
        raise ValueError("p4 MPC layout does not preserve the original local prefix")
    if not p6_prefix_preserved:
        raise ValueError("p6 MPC layout does not preserve the original local prefix")
    if (
        p4_constraints.owned_rows != p4_layout[1]
        or p4_constraints.local_rows < p4_layout[2]
    ):
        raise ValueError("p4 MPC layout does not preserve the original local prefix")
    if (
        p6_constraints.owned_rows != p6_layout[1]
        or p6_constraints.local_rows < p6_layout[2]
    ):
        raise ValueError("p6 MPC layout does not preserve the original local prefix")
    reference = build_variable_p_reference_space(
        HexaEntityDegreeMap.uniform(4)
    )
    p6_reference = build_variable_p_reference_space(
        HexaEntityDegreeMap.uniform(6)
    )
    if reference.hcurl_to_p6.shape != (_P6_DIMENSION, _P4_DIMENSION):
        raise RuntimeError("production p4/p6 reference expansion has wrong shape")
    cells = _cell_stencils(
        p4_space,
        p6_space,
        p6_constraints,
        p4_original_local_rows=p4_layout[2],
        p6_original_local_rows=p6_layout[2],
    )
    local_selected_global_rows = np.concatenate(
        [
            np.asarray(
                p6_space.dofmap.index_map.local_to_global(
                    cell.p6_local_dofs[cell.selected_p6_positions]
                ),
                dtype=np.int64,
            )
            for cell in cells
        ]
        if cells
        else [np.empty(0, dtype=np.int64)]
    )
    selected_packets = p4_space.mesh.comm.allgather(local_selected_global_rows)
    selected_global_rows = np.concatenate(selected_packets)
    expected_global_rows = np.arange(p6_layout[0], dtype=np.int64)
    if not np.array_equal(
        np.sort(selected_global_rows),
        expected_global_rows,
    ):
        raise RuntimeError("global p6 owner designation is not one-to-one")
    cell_identity = [
        {
            "cell_info": int(cell.cell_info),
            "selected_positions": tuple(map(int, cell.selected_p6_positions)),
        }
        for cell in cells
    ]
    reference_identity = {
        "schema": "task037.m1.p4-p6-reference-transform.v1",
        "p4_dimension": _P4_DIMENSION,
        "p6_dimension": _P6_DIMENSION,
        "hcurl_expansion_sha256": reference.audit["hcurl_expansion_sha256"],
        "orientation": "DOLFINx cell permutation + VariablePReferenceSpace",
        "global_row_ids_in_identity": False,
    }
    retained_numeric_components = _retained_numeric_payload_components(
        reference,
        p6_reference,
        cells,
        (p4_constraints, p6_constraints),
    )
    retained_numeric_payload_bytes = int(sum(retained_numeric_components.values()))
    lazy_p6_work_vec_bytes = int(
        p6_constraints.local_rows * _COMPLEX_ITEMSIZE
    )
    retained_transfer_numeric_payload_bytes = (
        retained_numeric_payload_bytes + lazy_p6_work_vec_bytes
    )
    forward_workspace = {
        "p4_local_lift_copy_bytes": int(
            p4_constraints.local_rows * _COMPLEX_ITEMSIZE
        ),
        "one_oriented_p6_result_bytes": int(
            _P6_DIMENSION * _COMPLEX_ITEMSIZE
        ),
        "p4_orientation_scratch_bytes": int(
            _P4_DIMENSION * _COMPLEX_ITEMSIZE
        ),
        "p6_orientation_scratch_bytes": int(
            2 * _P6_DIMENSION * _COMPLEX_ITEMSIZE
        ),
    }
    adjoint_workspace = {
        "p6_local_adjoint_vec_bytes": int(
            p6_constraints.local_rows * _COMPLEX_ITEMSIZE
        ),
        "one_local_p6_dual_bytes": int(
            _P6_DIMENSION * _COMPLEX_ITEMSIZE
        ),
        "one_oriented_p4_result_bytes": int(
            _P4_DIMENSION * _COMPLEX_ITEMSIZE
        ),
        "p4_orientation_scratch_bytes": int(
            _P4_DIMENSION * _COMPLEX_ITEMSIZE
        ),
        "p6_orientation_scratch_bytes": int(
            2 * _P6_DIMENSION * _COMPLEX_ITEMSIZE
        ),
        "p6_mpc_slave_snapshot_bytes": int(
            len(p6_constraints.slave_indices) * _COMPLEX_ITEMSIZE
        ),
        "p4_mpc_slave_snapshot_bytes": int(
            len(p4_constraints.slave_indices) * _COMPLEX_ITEMSIZE
        ),
    }
    forward_workspace_bytes = int(sum(forward_workspace.values()))
    adjoint_workspace_bytes = int(sum(adjoint_workspace.values()))
    workspace_bytes = max(forward_workspace_bytes, adjoint_workspace_bytes)
    cell_mapping = [
        {
            "global_cell": int(cell.global_cell),
            "local_cell": int(cell.local_cell),
            "selected_positions": tuple(map(int, cell.selected_p6_positions)),
        }
        for cell in cells
    ]
    global_cell_mappings = sorted(
        (
            mapping
            for packet in p4_space.mesh.comm.allgather(cell_mapping)
            for mapping in packet
        ),
        key=lambda mapping: (
            int(mapping["global_cell"]),
            int(mapping["local_cell"]),
            tuple(mapping["selected_positions"]),
        ),
    )
    global_ownership_sha = _json_sha256(
        {"cells": global_cell_mappings}
    )
    topology = p6_space.mesh.topology
    topology.create_entity_permutations()
    owned_cell_count = int(topology.index_map(3).size_local)
    local_cell_info = np.asarray(
        topology.get_cell_permutation_info(), dtype=np.uint32
    )[:owned_cell_count]
    orientation_nonzero_local = int(np.count_nonzero(local_cell_info))
    orientation_nonzero_global = int(
        p6_space.mesh.comm.allreduce(orientation_nonzero_local, op=MPI.SUM)
    )
    orientation_cell_count_global = int(
        p6_space.mesh.comm.allreduce(owned_cell_count, op=MPI.SUM)
    )
    p4_owned_constraint_count_local = int(
        np.count_nonzero(p4_constraints.slave_indices < p4_constraints.owned_rows)
    )
    p6_owned_constraint_count_local = int(
        np.count_nonzero(p6_constraints.slave_indices < p6_constraints.owned_rows)
    )
    p4_owned_constraint_count_global = int(
        p4_space.mesh.comm.allreduce(p4_owned_constraint_count_local, op=MPI.SUM)
    )
    p6_owned_constraint_count_global = int(
        p6_space.mesh.comm.allreduce(p6_owned_constraint_count_local, op=MPI.SUM)
    )
    p4_original_ghost_rows = int(p4_layout[2] - p4_layout[1])
    p6_original_ghost_rows = int(p6_layout[2] - p6_layout[1])
    p4_mpc_extended_ghost_rows = int(
        p4_constraints.local_rows - p4_constraints.owned_rows
    )
    p6_mpc_extended_ghost_rows = int(
        p6_constraints.local_rows - p6_constraints.owned_rows
    )
    p4_mpc_added_master_ghost_rows = int(
        np.unique(
            p4_constraints.master_indices[
                p4_constraints.master_indices >= p4_layout[2]
            ]
        ).size
    )
    p6_mpc_added_master_ghost_rows = int(
        np.unique(
            p6_constraints.master_indices[
                p6_constraints.master_indices >= p6_layout[2]
            ]
        ).size
    )
    audit = MappingProxyType(
        {
            "schema_version": "task037.m1.owner-local-p4-p6.v1",
            "status": "structural_build_pass",
            "structural_build_pass": True,
            "measurement_qualification": "not_run",
            "m1_gate_pass": False,
            "mpi_size": int(p4_space.mesh.comm.size),
            "p4_global_rows": int(p4_constraints.global_rows),
            "p4_owned_rows": int(p4_constraints.owned_rows),
            "p4_ghost_rows": p4_original_ghost_rows,
            "p4_original_local_rows": int(p4_layout[2]),
            "p4_original_ghost_rows": p4_original_ghost_rows,
            "p4_mpc_extended_local_rows": int(p4_constraints.local_rows),
            "p4_mpc_extended_ghost_rows": p4_mpc_extended_ghost_rows,
            "p4_mpc_added_master_ghost_rows": p4_mpc_added_master_ghost_rows,
            "p4_mpc_original_prefix_preserved": p4_prefix_preserved,
            "p6_global_rows": int(p6_constraints.global_rows),
            "p6_owned_rows": int(p6_constraints.owned_rows),
            "p6_ghost_rows": p6_original_ghost_rows,
            "p6_original_local_rows": int(p6_layout[2]),
            "p6_original_ghost_rows": p6_original_ghost_rows,
            "p6_mpc_extended_local_rows": int(p6_constraints.local_rows),
            "p6_mpc_extended_ghost_rows": p6_mpc_extended_ghost_rows,
            "p6_mpc_added_master_ghost_rows": p6_mpc_added_master_ghost_rows,
            "p6_mpc_original_prefix_preserved": p6_prefix_preserved,
            "p4_mpc_extended_local_work_bytes": int(
                p4_constraints.local_rows * _COMPLEX_ITEMSIZE
            ),
            "p6_mpc_extended_local_work_bytes": int(
                p6_constraints.local_rows * _COMPLEX_ITEMSIZE
            ),
            "owned_cell_count_local": int(
                p6_space.mesh.topology.index_map(3).size_local
            ),
            "designating_cell_count_local": int(len(cells)),
            "orientation_nonzero_cell_count_global": orientation_nonzero_global,
            "orientation_cell_count_global": orientation_cell_count_global,
            "p4_constraint_count": int(len(p4_constraints.slave_indices)),
            "p6_constraint_count": int(len(p6_constraints.slave_indices)),
            "p4_owned_constraint_count_local": p4_owned_constraint_count_local,
            "p6_owned_constraint_count_local": p6_owned_constraint_count_local,
            "p4_owned_constraint_count_global": p4_owned_constraint_count_global,
            "p6_owned_constraint_count_global": p6_owned_constraint_count_global,
            "missing_owned_p6_rows": 0,
            "extra_owned_p6_rows": 0,
            "duplicate_owned_p6_designations": 0,
            "reference_hcurl_expansion_sha256": reference.audit[
                "hcurl_expansion_sha256"
            ],
            "reference_transform_sha256": _json_sha256(reference_identity),
            "orientation_metadata_sha256": _json_sha256(
                {"cells": cell_identity}
            ),
            "ownership_binding_sha256": _json_sha256(
                {"cells": cell_mapping}
            ),
            "global_ownership_binding_sha256": global_ownership_sha,
            "global_owner_designation_complete": True,
            "global_owner_designation_duplicate_count": int(
                len(selected_global_rows) - len(np.unique(selected_global_rows))
            ),
            "metadata_row_designation_allgather": True,
            "retained_numeric_payload_components": retained_numeric_components,
            "retained_numeric_payload_bytes": retained_numeric_payload_bytes,
            "lazy_p6_work_vec_bytes": lazy_p6_work_vec_bytes,
            "lazy_p6_work_vec_allocated_at_build": False,
            "retained_transfer_numeric_payload_bytes": (
                retained_transfer_numeric_payload_bytes
            ),
            "retained_transfer_numeric_payload_gate": (
                retained_transfer_numeric_payload_bytes <= 128_000_000
            ),
            "construction_transient_numeric_payload_bytes": None,
            "construction_transient_measurement": "not_measured",
            "measured_process_tree_rss_bytes": None,
            "measured_process_tree_rss": "not_measured",
            "bounded_apply_workspace_bytes": int(workspace_bytes),
            "bounded_apply_workspace_gate": workspace_bytes <= 64_000_000,
            "bounded_apply_workspace_components": {
                "forward": forward_workspace,
                "adjoint": adjoint_workspace,
                "forward_total_bytes": forward_workspace_bytes,
                "adjoint_total_bytes": adjoint_workspace_bytes,
                "simultaneous_phase": "one_direction_at_a_time",
            },
            "owned_numpy_carrier_readonly": True,
            "global_transfer_matrix_materialized": False,
            "global_matrix_materialized": False,
            "global_constraint_matrix_materialized": False,
            "numeric_allgather": False,
            "replicated_global_numeric_vector": False,
            "condensed_path": False,
            "trace_only_path": False,
            "slab_factor_materialized": False,
            "ordinary_default_changed": False,
            "p4_mpc_phase_applied_once": bool(
                p4_constraints.audit["phase_coefficients_applied_once"]
            ),
            "p6_mpc_phase_applied_once": bool(
                p6_constraints.audit["phase_coefficients_applied_once"]
            ),
        }
    )
    return OwnerLocalP4P6Transfer(
        p4_space=p4_space,
        p6_space=p6_space,
        p4_constraints=p4_constraints,
        p6_constraints=p6_constraints,
        reference_space=reference,
        _cells=cells,
        audit=audit,
    )
