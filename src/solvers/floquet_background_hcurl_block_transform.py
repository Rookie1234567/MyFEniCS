"""Distributed active-trace Bloch transforms for the narrow S2b Gate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from petsc4py import PETSc

from ..geometry.tetra_mesh_audit import canonical_entity_key, mesh_coordinate_tolerance
from .hcurl_canonical_vector_dolfinx import (
    _entity_coordinates,
    _physical_entity_transform,
)

__all__ = (
    "ActiveTraceBlochLayout",
    "ActiveTraceBlochTransforms",
    "build_active_trace_bloch_layout",
    "create_active_trace_bloch_transforms",
)


@dataclass(frozen=True)
class _EntityBlock:
    key: tuple[int, tuple[tuple[int, int, int], ...]]
    orbit: tuple[int, int]
    base: tuple[Any, ...]
    active_ids: tuple[int, ...]
    coordinates: tuple[tuple[float, float, float], ...]


@dataclass(frozen=True)
class ActiveTraceBlochLayout:
    comm: Any
    active_rows: int
    auxiliary_rows: int
    augmented_rows: int
    nx: int
    ny: int
    nz: int
    rows_per_harmonic: int
    ownership: tuple[int, int]
    axis_values: tuple[tuple[float, ...], ...]
    phase_x: complex
    phase_y: complex
    k_b: tuple[float, float]
    lengths: tuple[float, float]
    blocks: tuple[_EntityBlock, ...]
    block_by_orbit_base: dict[tuple[tuple[int, int], tuple[Any, ...]], _EntityBlock]
    slot_by_base: dict[tuple[Any, ...], int]
    orbit_rows: dict[tuple[int, int], int]


@dataclass
class ActiveTraceBlochTransforms:
    """Paired sparse transforms with borrowed layout metadata."""

    layout: ActiveTraceBlochLayout
    q: PETSc.Mat
    t: PETSc.Mat
    _destroyed: bool = False

    def destroy(self) -> None:
        if self._destroyed:
            return
        self.q.destroy()
        self.t.destroy()
        self._destroyed = True


def _unique_axis(values: list[float]) -> np.ndarray:
    result: list[float] = []
    for value in sorted(values):
        if not result or not np.isclose(value, result[-1], rtol=0.0, atol=1.0e-9):
            result.append(float(value))
    return np.asarray(result, dtype=np.float64)


def _mesh_cells(function_space) -> tuple[dict[int, tuple[int, int, int]], tuple[np.ndarray, ...]]:
    mesh = function_space.mesh
    comm = mesh.comm
    tdim = mesh.topology.dim
    cell_map = mesh.topology.index_map(tdim)
    local_cells: list[tuple[tuple[float, ...], tuple[float, ...]]] = []
    for cell in range(int(cell_map.size_local)):
        points = np.asarray(
            mesh.geometry.x[np.asarray(mesh.geometry.dofmap[cell], dtype=np.int32)],
            dtype=np.float64,
        )
        local_cells.append((tuple(points.min(axis=0)), tuple(points.max(axis=0))))
    packets = comm.allgather(tuple(local_cells))
    lowers = [point for packet in packets for lower, _upper in packet for point in [lower]]
    uppers = [point for packet in packets for _lower, upper in packet for point in [upper]]
    axes = tuple(
        _unique_axis(
            [float(point[axis]) for point in (*lowers, *uppers)]
        )
        for axis in range(3)
    )
    if any(len(axis) < 2 for axis in axes):
        raise RuntimeError("S2b requires a three-axis hexahedral mesh")
    widths = tuple(np.diff(axis) for axis in axes)
    for width in widths[:2]:
        if not np.allclose(width, width[0], rtol=0.0, atol=1.0e-10):
            raise RuntimeError("S2b requires equally spaced transverse axes")
    cell_indices: dict[int, tuple[int, int, int]] = {}
    for cell, (lower, _upper) in enumerate(local_cells):
        indices = []
        for axis, value in zip(axes, lower, strict=True):
            matches = np.flatnonzero(np.isclose(axis[:-1], value, rtol=0.0, atol=1.0e-9))
            if len(matches) != 1:
                raise RuntimeError("owned cell lower corner has no canonical axis index")
            indices.append(int(matches[0]))
        cell_indices[cell] = tuple(indices)
    return cell_indices, axes


def _candidate_blocks(function_space, condensed, axes):
    topology = function_space.mesh.topology
    tdim = topology.dim
    for dimension in (1, 2):
        topology.create_connectivity(tdim, dimension)
        topology.create_connectivity(dimension, tdim)
    topology.create_entity_permutations()
    cell_indices, _axes = _mesh_cells(function_space)
    tolerance = mesh_coordinate_tolerance(function_space.mesh)
    dx, dy = (float(np.diff(axes[axis])[0]) for axis in (0, 1))
    nx, ny = len(axes[0]) - 1, len(axes[1]) - 1
    dofmap = function_space.dofmap
    index_map = dofmap.index_map
    original_to_active = condensed.trace_constraints.original_to_active
    layout = dofmap.dof_layout
    candidates = []
    seen_entities: set[tuple[int, int]] = set()
    cells = sorted(cell_indices, key=lambda cell: cell_indices[cell])
    for cell in cells:
        cell_dofs = np.asarray(dofmap.cell_dofs(cell), dtype=np.int32)
        for dimension in (1, 2):
            for entity in topology.connectivity(tdim, dimension).links(cell):
                entity_id = int(entity)
                identity = (dimension, entity_id)
                if identity in seen_entities:
                    continue
                seen_entities.add(identity)
                matches = np.flatnonzero(
                    np.asarray(topology.connectivity(tdim, dimension).links(cell))
                    == entity_id
                )
                if len(matches) != 1:
                    raise RuntimeError("cell/entity incidence is not unique")
                positions = np.asarray(
                    layout.entity_dofs(dimension, int(matches[0])), dtype=np.int32
                )
                raw_local = cell_dofs[positions]
                raw_global = np.asarray(index_map.local_to_global(raw_local), dtype=np.int64)
                active = [original_to_active.get(int(value)) for value in raw_global]
                if any(value is None for value in active):
                    continue
                active_ids = tuple(int(value) for value in active)
                if len(set(active_ids)) != len(active_ids):
                    raise RuntimeError("entity block maps duplicate active trace rows")
                coordinates = np.asarray(_entity_coordinates(function_space, dimension, entity_id))
                minimum = coordinates.min(axis=0)
                raw_ix = int(np.rint((minimum[0] - axes[0][0]) / dx))
                raw_iy = int(np.rint((minimum[1] - axes[1][0]) / dy))
                if not 0 <= raw_ix <= nx or not 0 <= raw_iy <= ny:
                    raise RuntimeError("active entity lies outside transverse axes")
                if not np.isclose(
                    minimum[0], axes[0][0] + raw_ix * dx, rtol=0.0, atol=10.0 * tolerance
                ) or not np.isclose(
                    minimum[1], axes[1][0] + raw_iy * dy, rtol=0.0, atol=10.0 * tolerance
                ):
                    raise RuntimeError("active entity minimum is off the transverse axis")
                orbit = (raw_ix % nx, raw_iy % ny)
                shifted = coordinates - np.asarray((orbit[0] * dx, orbit[1] * dy, 0.0))
                physical_key = canonical_entity_key(
                    coordinates, tolerance
                )
                base = (int(dimension), canonical_entity_key(shifted, tolerance))
                candidates.append(
                    (
                        (int(dimension), physical_key),
                        orbit,
                        base,
                        active_ids,
                        tuple(tuple(float(value) for value in point) for point in coordinates),
                    )
                )
    return candidates


def build_active_trace_bloch_layout(request) -> ActiveTraceBlochLayout:
    """Build canonical active-trace metadata without collecting vector values."""

    function_space = request.function_space
    condensed = request.static_condensed_system
    comm = function_space.mesh.comm
    if condensed is None or request.floquet_data is None:
        raise RuntimeError("S2b requires static condensation and Floquet metadata")
    active_rows = int(condensed.active_rows)
    auxiliary_rows = int(request.n_aux)
    augmented_rows = active_rows + auxiliary_rows
    if int(request.A.getSize()[0]) != augmented_rows:
        raise RuntimeError("S2b request matrix size disagrees with condensed metadata")
    _cell_indices, axes = _mesh_cells(function_space)
    nx, ny, nz = (len(axis) - 1 for axis in axes)
    if (nx, ny, nz) != (3, 2, 4):
        raise RuntimeError(f"S2b actual mesh counts are {(nx, ny, nz)}, not (3, 2, 4)")
    phase_x = complex(request.floquet_data.phase_x)
    phase_y = complex(request.floquet_data.phase_y)
    if not np.isclose(abs(phase_x), 1.0, rtol=0.0, atol=1.0e-12):
        raise RuntimeError("S2b x Floquet phase is not unit modulus")
    if not np.isclose(abs(phase_y), 1.0, rtol=0.0, atol=1.0e-12):
        raise RuntimeError("S2b y Floquet phase is not unit modulus")
    lengths = (float(axes[0][-1] - axes[0][0]), float(axes[1][-1] - axes[1][0]))
    configured_k = (complex(request.config.kx), complex(request.config.ky))
    if any(abs(value.imag) > 1.0e-12 for value in configured_k):
        raise RuntimeError("S2b requires real configured transverse wave numbers")
    k_b = (float(configured_k[0].real), float(configured_k[1].real))
    if not np.isclose(
        np.exp(1j * k_b[0] * lengths[0]), phase_x, rtol=0.0, atol=1.0e-12
    ):
        raise RuntimeError("x Bloch phase authority does not close")
    if not np.isclose(
        np.exp(1j * k_b[1] * lengths[1]), phase_y, rtol=0.0, atol=1.0e-12
    ):
        raise RuntimeError("y Bloch phase authority does not close")
    if request.floquet_data.phase_independent_topology is None:
        raise RuntimeError("S2b requires phase-independent Floquet topology authority")
    local_candidates = _candidate_blocks(function_space, condensed, axes)
    packets = comm.allgather(tuple(local_candidates))
    by_key: dict[tuple[int, tuple[tuple[int, int, int], ...]], list[tuple[Any, ...]]] = {}
    for packet in packets:
        for candidate in packet:
            by_key.setdefault(candidate[0], []).append(candidate)
    selected: list[_EntityBlock] = []
    for key in sorted(by_key, key=repr):
        candidates = by_key[key]
        candidate = min(candidates, key=lambda value: (value[1], value[3]))
        if any(
            other[2:] != candidate[2:] for other in candidates
        ):
            raise RuntimeError("canonical entity block metadata differs across owners")
        selected.append(
            _EntityBlock(
                key=key,
                orbit=(int(candidate[1][0]), int(candidate[1][1])),
                base=candidate[2],
                active_ids=candidate[3],
                coordinates=candidate[4],
            )
        )
    active_to_block: dict[int, _EntityBlock] = {}
    for block in selected:
        for active_id in block.active_ids:
            if active_id in active_to_block:
                raise RuntimeError("active trace row has duplicate canonical entity ownership")
            active_to_block[active_id] = block
    if set(active_to_block) != set(range(active_rows)):
        raise RuntimeError("canonical entity blocks do not cover every active trace row")
    block_by_orbit_base = {(block.orbit, block.base): block for block in selected}
    if len(block_by_orbit_base) != len(selected):
        raise RuntimeError("physical orbit selection produced duplicate blocks")
    orbits = {(ix, iy) for ix in range(nx) for iy in range(ny)}
    if {block.orbit for block in selected} != orbits:
        raise RuntimeError("active trace blocks do not cover all transverse orbits")
    bases = {block.base for block in selected}
    base_orbits = {
        base: {orbit for orbit, candidate_base in block_by_orbit_base if candidate_base == base}
        for base in bases
    }
    if any(orbit_set != orbits for orbit_set in base_orbits.values()):
        raise RuntimeError("canonical trace base is missing or duplicated in an orbit")
    orbit_bases = {
        orbit: {base for candidate_orbit, base in block_by_orbit_base if candidate_orbit == orbit}
        for orbit in orbits
    }
    if any(base_set != bases for base_set in orbit_bases.values()):
        raise RuntimeError("transverse orbit is missing or duplicating a trace base")
    sizes = {base: len(block_by_orbit_base[((0, 0), base)].active_ids) for base in bases}
    if any(
        len(block_by_orbit_base[(orbit, base)].active_ids) != sizes[base]
        for orbit in orbits
        for base in bases
    ):
        raise RuntimeError("canonical trace channel sizes differ between orbits")
    ordered_bases = sorted(bases, key=repr)
    slot_by_base: dict[tuple[Any, ...], int] = {}
    offset = 0
    for base in ordered_bases:
        slot_by_base[base] = offset
        offset += sizes[base]
    orbit_rows = {
        orbit: sum(
            len(block.active_ids)
            for (candidate_orbit, _base), block in block_by_orbit_base.items()
            if candidate_orbit == orbit
        )
        for orbit in sorted(orbits)
    }
    if any(count != offset for count in orbit_rows.values()):
        raise RuntimeError("physical orbit coverage has unequal active-row counts")
    if active_rows != 480 or auxiliary_rows != 4 or offset != 80:
        raise RuntimeError(
            "S2b active metadata is not 480 FE rows = 6 * 80 with four auxiliary rows"
        )
    probe = condensed.create_augmented_vector()
    ownership = tuple(map(int, request.A.getOwnershipRange()))
    if request.A.getOwnershipRange() != probe.getOwnershipRange():
        probe.destroy()
        raise RuntimeError("S2b A and augmented-vector ownership differ")
    probe.destroy()
    return ActiveTraceBlochLayout(
        comm=comm,
        active_rows=active_rows,
        auxiliary_rows=auxiliary_rows,
        augmented_rows=augmented_rows,
        nx=nx,
        ny=ny,
        nz=nz,
        rows_per_harmonic=offset,
        ownership=ownership,
        axis_values=tuple(tuple(float(value) for value in axis) for axis in axes),
        phase_x=phase_x,
        phase_y=phase_y,
        k_b=k_b,
        lengths=lengths,
        blocks=tuple(selected),
        block_by_orbit_base=block_by_orbit_base,
        slot_by_base=slot_by_base,
        orbit_rows=orbit_rows,
    )


def _orientation(block: _EntityBlock) -> np.ndarray:
    transform, _state = _physical_entity_transform(
        np.asarray(block.coordinates, dtype=np.float64),
        block.key[0],
        2,
        1.0e-10 * max(np.ptp(np.asarray(block.coordinates), axis=0).max(), 1.0),
    )
    return np.asarray(transform, dtype=np.complex128)


def _phase(layout: ActiveTraceBlochLayout, orbit: tuple[int, int], mode: tuple[int, int], sign: int) -> complex:
    mx, my = mode
    rx = layout.lengths[0] * orbit[0] / layout.nx
    ry = layout.lengths[1] * orbit[1] / layout.ny
    gx = 2.0 * np.pi * mx / layout.lengths[0]
    gy = 2.0 * np.pi * my / layout.lengths[1]
    return complex(np.exp(1j * sign * ((layout.k_b[0] + gx) * rx + (layout.k_b[1] + gy) * ry)))


def _matrix_from_rows(layout: ActiveTraceBlochLayout, rows: dict[int, dict[int, complex]]) -> PETSc.Mat:
    comm = layout.comm
    start, stop = layout.ownership
    diagonal = np.zeros(stop - start, dtype=PETSc.IntType)
    off_diagonal = np.zeros(stop - start, dtype=PETSc.IntType)
    for row in range(start, stop):
        columns = tuple(rows.get(row, {}))
        diagonal[row - start] = sum(start <= column < stop for column in columns)
        off_diagonal[row - start] = len(columns) - int(diagonal[row - start])
    nnz = diagonal if comm.size == 1 else (diagonal, off_diagonal)
    matrix = PETSc.Mat().createAIJ(
        size=((stop - start, layout.augmented_rows), (stop - start, layout.augmented_rows)),
        nnz=nnz,
        comm=comm,
    )
    matrix.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR, True)
    for row in range(start, stop):
        entries = rows.get(row, {})
        if entries:
            columns = np.asarray(tuple(entries), dtype=PETSc.IntType)
            values = np.asarray(tuple(entries[column] for column in columns), dtype=PETSc.ScalarType)
            matrix.setValues(row, columns, values)
    matrix.assemble()
    return matrix


def _owned_entity_blocks(layout: ActiveTraceBlochLayout) -> tuple[_EntityBlock, ...]:
    start, stop = layout.ownership
    expected = set(range(start, min(stop, layout.active_rows)))
    owned = []
    covered: set[int] = set()
    for block in layout.blocks:
        local = {row for row in block.active_ids if start <= row < stop}
        if not local:
            continue
        if local != set(block.active_ids):
            raise RuntimeError("a physical entity block crosses PETSc row ownership")
        owned.append(block)
        covered.update(local)
    if covered != expected:
        raise RuntimeError("physical-row owners do not cover their entity blocks")
    return tuple(owned)


def create_active_trace_bloch_transforms(layout: ActiveTraceBlochLayout) -> ActiveTraceBlochTransforms:
    """Create sparse ``Q`` and ``T`` with physical=Q modal and modal=T physical."""

    if layout.auxiliary_rows != 4:
        raise RuntimeError("S2b requires four auxiliary envelope rows")
    local_blocks = _owned_entity_blocks(layout)
    q_rows: dict[int, dict[int, complex]] = {}
    t_h_rows: dict[int, dict[int, complex]] = {}
    normalization = np.sqrt(layout.nx * layout.ny)
    modes = tuple((mx, my) for my in range(layout.ny) for mx in range(layout.nx))
    for block in local_blocks:
        transform = _orientation(block)
        inverse = np.linalg.solve(transform, np.eye(len(block.active_ids)))
        for alpha, active_id in enumerate(block.active_ids):
            q_entries = q_rows.setdefault(active_id, {})
            s_entries = t_h_rows.setdefault(active_id, {})
            for mode_index, mode in enumerate(modes):
                q_factor = _phase(layout, block.orbit, mode, 1) / normalization
                for beta, value in enumerate(transform[alpha]):
                    if abs(value) > 1.0e-14:
                        column = (
                            mode_index * layout.rows_per_harmonic
                            + layout.slot_by_base[block.base]
                            + beta
                        )
                        q_entries[column] = complex(q_factor * value)
            for mode_index, mode in enumerate(modes):
                t_factor = _phase(layout, block.orbit, mode, -1) / normalization
                for beta, value in enumerate(inverse[:, alpha]):
                    if abs(value) > 1.0e-14:
                        column = (
                            mode_index * layout.rows_per_harmonic
                            + layout.slot_by_base[block.base]
                            + beta
                        )
                        s_entries[column] = complex(np.conj(t_factor * value))
    envelope_aux_start = layout.active_rows
    for row in range(layout.ownership[0], layout.ownership[1]):
        if envelope_aux_start <= row < layout.augmented_rows:
            q_rows.setdefault(row, {})[row] = 1.0
            t_h_rows.setdefault(row, {})[row] = 1.0
    q = _matrix_from_rows(layout, q_rows)
    t_h = _matrix_from_rows(layout, t_h_rows)
    t = PETSc.Mat()
    t_h.hermitianTranspose(t)
    t_h.destroy()
    if q.getSize() != (layout.augmented_rows, layout.augmented_rows):
        q.destroy()
        t.destroy()
        raise RuntimeError("S2b Q has the wrong global size")
    if t.getSize() != (layout.augmented_rows, layout.augmented_rows):
        q.destroy()
        t.destroy()
        raise RuntimeError("S2b T has the wrong global size")
    return ActiveTraceBlochTransforms(layout=layout, q=q, t=t)
