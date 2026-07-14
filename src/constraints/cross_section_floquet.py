from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from dolfinx import fem, mesh
from mpi4py import MPI
from petsc4py import PETSc

from ..modes.cross_section_spaces import CrossSectionMesh, CrossSectionSpaces


@dataclass(frozen=True)
class CrossSectionFloquetConstraints:
    """Owned mixed-space slave rows with global mixed-space master columns."""

    slave_local: np.ndarray
    slave_global: np.ndarray
    master_global: np.ndarray
    master_owners: np.ndarray
    coefficients: np.ndarray
    offsets: np.ndarray
    phase_x: complex
    phase_y: complex
    transverse_constraint_count: int
    longitudinal_constraint_count: int
    max_pair_coordinate_error: float
    max_probe_residual: float
    communication_scope: str = "periodic_boundary_dofs_only"


@dataclass(frozen=True)
class DistributedConstraintTransform:
    matrix: PETSc.Mat
    full_global_size: int
    reduced_global_size: int
    full_local_size: int
    reduced_local_size: int
    global_slave_count: int
    ownership_note: str = "PETSc distributed rows; no rank-0 eigenvector gather"


def _global_info(space, dofs: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    dofs = np.asarray(dofs, dtype=np.int64)
    index_map = space.dofmap.index_map
    bs = int(space.dofmap.index_map_bs)
    blocks = dofs // bs
    components = dofs % bs
    global_blocks = index_map.local_to_global(blocks.astype(np.int32)).astype(np.int64)
    global_dofs = global_blocks * bs + components
    owned = blocks < index_map.size_local
    owners = np.empty(len(dofs), dtype=np.int32)
    owners[owned] = space.mesh.comm.rank
    if np.any(~owned):
        ghost_owners = np.asarray(index_map.owners, dtype=np.int32)
        owners[~owned] = ghost_owners[blocks[~owned] - index_map.size_local]
    return global_dofs, owners, owned


def _parent_info(
    spaces: CrossSectionSpaces,
    collapsed_to_mixed: np.ndarray,
    collapsed_dofs: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    parent_local = np.asarray(collapsed_to_mixed, dtype=np.int64)[collapsed_dofs]
    parent_global, parent_owners, parent_owned = _global_info(
        spaces.mixed, parent_local
    )
    return parent_local, parent_global, parent_owners, parent_owned


def _coordinate_key(value: float, tolerance: float) -> int:
    return int(round(float(value) / tolerance))


def _facet_probe_arrays(
    space,
    *,
    normal_axis: int,
    tangent_midpoint: float,
    tangent_scale: float,
    kx: float,
    ky: float,
    num_probes: int,
) -> list[np.ndarray]:
    """Interpolate a fixed number of collective-safe trace probes.

    ``Function.x.scatter_forward`` communicates with neighboring ranks.  Every
    rank must therefore execute the same number of scatters even when its
    partition owns a different number of exterior facets.
    """

    arrays: list[np.ndarray] = []
    tangent_axis = 1 - normal_axis
    tangent_component = tangent_axis
    for power in range(num_probes):
        probe = fem.Function(space, name=f"cross_section_probe_{normal_axis}_{power}")

        def field(x, power=power):
            result = np.zeros((2, x.shape[1]), dtype=np.complex128)
            eta = (x[tangent_axis] - tangent_midpoint) / tangent_scale
            result[tangent_component] = eta**power * np.exp(
                1j * (kx * x[0] + ky * x[1])
            )
            return result

        probe.interpolate(field)
        probe.x.scatter_forward()
        arrays.append(np.asarray(probe.x.array, dtype=np.complex128).copy())
    return arrays


def _local_facet_records(
    cross_section: CrossSectionMesh,
    spaces: CrossSectionSpaces,
    *,
    normal_axis: int,
    side: str,
    kx: float,
    ky: float,
    tolerance: float,
) -> list[dict[str, object]]:
    msh = cross_section.mesh
    fdim = msh.topology.dim - 1
    coordinate = (
        cross_section.x_values[0 if side == "min" else -1]
        if normal_axis == 0
        else cross_section.y_values[0 if side == "min" else -1]
    )
    facets = mesh.locate_entities_boundary(
        msh,
        fdim,
        lambda x: np.isclose(x[normal_axis], coordinate, atol=tolerance, rtol=0.0),
    )
    midpoints = mesh.compute_midpoints(msh, fdim, facets)
    facet_index_map = msh.topology.index_map(fdim)
    tangent_axis = 1 - normal_axis
    tangent_scale = max(
        float(
            (cross_section.y_values[-1] - cross_section.y_values[0])
            if tangent_axis == 1
            else (cross_section.x_values[-1] - cross_section.x_values[0])
        ),
        1.0e-12,
    )
    pending_records: list[dict[str, object]] = []
    for facet, midpoint in zip(facets, midpoints):
        dofs = np.asarray(
            fem.locate_dofs_topological(
                spaces.transverse,
                fdim,
                np.asarray([facet], dtype=np.int32),
                remote=False,
            ),
            dtype=np.int32,
        )
        if len(dofs) == 0:
            raise RuntimeError("No transverse H(curl) dofs were found on a periodic facet.")
        _, parent_global, parent_owners, _ = _parent_info(
            spaces, spaces.transverse_to_mixed, dofs
        )
        pending_records.append(
            {
                "key": _coordinate_key(float(midpoint[tangent_axis]), tolerance),
                "tangent": float(midpoint[tangent_axis]),
                "parent_global": parent_global.tolist(),
                "parent_owners": parent_owners.tolist(),
                "dofs": dofs,
                "facet_owned": bool(int(facet) < facet_index_map.size_local),
                "rank": msh.comm.rank,
            }
        )
    num_probes = max(2 * int(spaces.transverse_degree) + 2, 4)
    # The midpoint merely centers polynomial probes.  On a structured matching
    # pair, using one common center per side preserves the exact translated
    # trace relation and keeps the interpolation collective count fixed.
    common_midpoint = 0.5 * float(
        (cross_section.y_values[0] + cross_section.y_values[-1])
        if tangent_axis == 1
        else (cross_section.x_values[0] + cross_section.x_values[-1])
    )
    probe_arrays = _facet_probe_arrays(
        spaces.transverse,
        normal_axis=normal_axis,
        tangent_midpoint=common_midpoint,
        tangent_scale=tangent_scale,
        kx=kx,
        ky=ky,
        num_probes=num_probes,
    )
    records: list[dict[str, object]] = []
    for record in pending_records:
        dofs = np.asarray(record.pop("dofs"), dtype=np.int32)
        values = np.column_stack([array[dofs] for array in probe_arrays])
        record["probe_values"] = values.tolist()
        records.append(record)
    return records


def _merge_facet_records(
    records_by_rank: list[list[dict[str, object]]],
) -> dict[int, dict[str, object]]:
    merged: dict[int, dict[str, object]] = {}
    for records in records_by_rank:
        for record in records:
            key = int(record["key"])
            priority = (not bool(record["facet_owned"]), int(record["rank"]))
            old = merged.get(key)
            old_priority = (
                (not bool(old["facet_owned"]), int(old["rank"]))
                if old is not None
                else None
            )
            if old is None or priority < old_priority:
                merged[key] = record
    return merged


def _owned_parent_lookup(spaces: CrossSectionSpaces) -> dict[int, int]:
    index_map = spaces.mixed.dofmap.index_map
    bs = int(spaces.mixed.dofmap.index_map_bs)
    if bs != 1:
        raise NotImplementedError("Cross-section mixed-space block size must be one.")
    local = np.arange(index_map.size_local, dtype=np.int32)
    global_dofs = index_map.local_to_global(local).astype(np.int64)
    return {int(global_dof): int(local_dof) for local_dof, global_dof in zip(local, global_dofs)}


def _transverse_axis_constraints(
    cross_section: CrossSectionMesh,
    spaces: CrossSectionSpaces,
    *,
    normal_axis: int,
    kx: float,
    ky: float,
    phase: complex,
    tolerance: float,
) -> tuple[list[tuple[int, int, list[int], list[int], list[complex]]], float, float]:
    comm = cross_section.mesh.comm
    low = _merge_facet_records(
        comm.allgather(
            _local_facet_records(
                cross_section,
                spaces,
                normal_axis=normal_axis,
                side="min",
                kx=kx,
                ky=ky,
                tolerance=tolerance,
            )
        )
    )
    high = _merge_facet_records(
        comm.allgather(
            _local_facet_records(
                cross_section,
                spaces,
                normal_axis=normal_axis,
                side="max",
                kx=kx,
                ky=ky,
                tolerance=tolerance,
            )
        )
    )
    if set(low) != set(high):
        raise RuntimeError(
            f"Periodic facet keys differ on axis {normal_axis}: min={sorted(low)}, max={sorted(high)}"
        )

    owned_parent = _owned_parent_lookup(spaces)
    rows: list[tuple[int, int, list[int], list[int], list[complex]]] = []
    max_pair_error = 0.0
    max_probe_residual = 0.0
    for key in sorted(low):
        low_record = low[key]
        high_record = high[key]
        max_pair_error = max(
            max_pair_error,
            abs(float(low_record["tangent"]) - float(high_record["tangent"])),
        )
        low_values = np.asarray(low_record["probe_values"], dtype=np.complex128)
        high_values = np.asarray(high_record["probe_values"], dtype=np.complex128)
        rank = np.linalg.matrix_rank(low_values, tol=1.0e-11)
        if rank < low_values.shape[0]:
            raise RuntimeError(
                f"Periodic probe rank {rank} is smaller than {low_values.shape[0]} on axis {normal_axis}."
            )
        transform = (high_values / phase) @ np.linalg.pinv(low_values)
        residual = high_values - phase * transform @ low_values
        max_probe_residual = max(
            max_probe_residual,
            float(np.linalg.norm(residual) / max(np.linalg.norm(high_values), 1.0e-30)),
        )

        low_global = np.asarray(low_record["parent_global"], dtype=np.int64)
        low_owners = np.asarray(low_record["parent_owners"], dtype=np.int32)
        high_global = np.asarray(high_record["parent_global"], dtype=np.int64)
        high_owners = np.asarray(high_record["parent_owners"], dtype=np.int32)
        cutoff = max(1.0e-13, 1.0e-11 * float(np.max(np.abs(transform))))
        for row_index, (slave_global, slave_owner) in enumerate(
            zip(high_global, high_owners)
        ):
            if int(slave_owner) != comm.rank:
                continue
            slave_local = owned_parent.get(int(slave_global))
            if slave_local is None:
                raise RuntimeError("An owned transverse slave has no local mixed-space index.")
            row_coefficients = phase * transform[row_index]
            selected = np.flatnonzero(np.abs(row_coefficients) > cutoff)
            if len(selected) == 0:
                selected = np.asarray([int(np.argmax(np.abs(row_coefficients)))])
            rows.append(
                (
                    slave_local,
                    int(slave_global),
                    [int(value) for value in low_global[selected]],
                    [int(value) for value in low_owners[selected]],
                    [complex(value) for value in row_coefficients[selected]],
                )
            )
    return rows, max_pair_error, max_probe_residual


def _longitudinal_constraints(
    cross_section: CrossSectionMesh,
    spaces: CrossSectionSpaces,
    *,
    phase_x: complex,
    phase_y: complex,
    tolerance: float,
) -> list[tuple[int, int, list[int], list[int], list[complex]]]:
    Vz = spaces.longitudinal
    comm = cross_section.mesh.comm
    coordinates = np.asarray(Vz.tabulate_dof_coordinates(), dtype=np.float64)
    all_local = np.arange(len(coordinates), dtype=np.int32)
    _, parent_global, parent_owners, parent_owned = _parent_info(
        spaces, spaces.longitudinal_to_mixed, all_local
    )

    x_min, x_max = cross_section.x_values[[0, -1]]
    y_min, y_max = cross_section.y_values[[0, -1]]

    local_master_records: list[tuple[int, int, int, int]] = []
    for dof, coordinate in enumerate(coordinates):
        if not parent_owned[dof]:
            continue
        on_master_edge = np.isclose(coordinate[0], x_min, atol=tolerance, rtol=0.0) or np.isclose(
            coordinate[1], y_min, atol=tolerance, rtol=0.0
        )
        if on_master_edge:
            local_master_records.append(
                (
                    _coordinate_key(coordinate[0], tolerance),
                    _coordinate_key(coordinate[1], tolerance),
                    int(parent_global[dof]),
                    int(parent_owners[dof]),
                )
            )
    master_records = [
        record for records in comm.allgather(local_master_records) for record in records
    ]
    master_by_coordinate = {
        (record[0], record[1]): (record[2], record[3]) for record in master_records
    }

    rows: list[tuple[int, int, list[int], list[int], list[complex]]] = []
    owned_parent = _owned_parent_lookup(spaces)
    for dof, coordinate in enumerate(coordinates):
        if not parent_owned[dof]:
            continue
        on_right = np.isclose(coordinate[0], x_max, atol=tolerance, rtol=0.0)
        on_top = np.isclose(coordinate[1], y_max, atol=tolerance, rtol=0.0)
        if not (on_right or on_top):
            continue

        if on_right and on_top:
            master_coordinate = (x_min, y_min)
            coefficient = phase_x * phase_y
        elif on_right:
            master_coordinate = (x_min, coordinate[1])
            coefficient = phase_x
        else:
            master_coordinate = (coordinate[0], y_min)
            coefficient = phase_y
        key = (
            _coordinate_key(master_coordinate[0], tolerance),
            _coordinate_key(master_coordinate[1], tolerance),
        )
        if key not in master_by_coordinate:
            raise RuntimeError(f"No scalar periodic master was found at coordinate key {key}.")
        master_global, master_owner = master_by_coordinate[key]
        slave_global = int(parent_global[dof])
        slave_local = owned_parent.get(slave_global)
        if slave_local is None:
            raise RuntimeError("An owned longitudinal slave has no local mixed-space index.")
        rows.append(
            (
                slave_local,
                slave_global,
                [int(master_global)],
                [int(master_owner)],
                [complex(coefficient)],
            )
        )
    return rows


def build_cross_section_floquet_constraints(
    cross_section: CrossSectionMesh,
    spaces: CrossSectionSpaces,
    *,
    kx: float,
    ky: float,
) -> CrossSectionFloquetConstraints:
    """Build orientation-aware double-periodic constraints on the mixed space.

    Only periodic-boundary records are replicated.  Interior vectors and
    matrices stay distributed.
    """

    length_x = float(cross_section.x_values[-1] - cross_section.x_values[0])
    length_y = float(cross_section.y_values[-1] - cross_section.y_values[0])
    phase_x = complex(np.exp(1j * kx * length_x))
    phase_y = complex(np.exp(1j * ky * length_y))
    tolerance = 1.0e-11 * max(length_x, length_y, 1.0)

    transverse_x, pair_x, probe_x = _transverse_axis_constraints(
        cross_section,
        spaces,
        normal_axis=0,
        kx=kx,
        ky=ky,
        phase=phase_x,
        tolerance=tolerance,
    )
    transverse_y, pair_y, probe_y = _transverse_axis_constraints(
        cross_section,
        spaces,
        normal_axis=1,
        kx=kx,
        ky=ky,
        phase=phase_y,
        tolerance=tolerance,
    )
    longitudinal = _longitudinal_constraints(
        cross_section,
        spaces,
        phase_x=phase_x,
        phase_y=phase_y,
        tolerance=tolerance,
    )
    rows = transverse_x + transverse_y + longitudinal
    rows.sort(key=lambda row: row[1])

    slave_local: list[int] = []
    slave_global: list[int] = []
    master_global: list[int] = []
    master_owners: list[int] = []
    coefficients: list[complex] = []
    offsets = [0]
    for local, global_dof, masters, owners, row_coefficients in rows:
        slave_local.append(local)
        slave_global.append(global_dof)
        master_global.extend(masters)
        master_owners.extend(owners)
        coefficients.extend(row_coefficients)
        offsets.append(len(master_global))

    local_slaves = list(slave_global)
    slaves_by_rank = cross_section.mesh.comm.allgather(local_slaves)
    all_slaves = {
        int(value) for values in slaves_by_rank for value in values
    }
    if len(all_slaves) != sum(len(values) for values in slaves_by_rank):
        raise RuntimeError("A mixed-space periodic slave is owned by more than one rank.")
    if any(int(master) in all_slaves for master in master_global):
        raise RuntimeError("Periodic masters must not also be slave dofs.")

    return CrossSectionFloquetConstraints(
        slave_local=np.asarray(slave_local, dtype=np.int32),
        slave_global=np.asarray(slave_global, dtype=np.int64),
        master_global=np.asarray(master_global, dtype=np.int64),
        master_owners=np.asarray(master_owners, dtype=np.int32),
        coefficients=np.asarray(coefficients, dtype=np.complex128),
        offsets=np.asarray(offsets, dtype=np.int32),
        phase_x=phase_x,
        phase_y=phase_y,
        transverse_constraint_count=len(transverse_x) + len(transverse_y),
        longitudinal_constraint_count=len(longitudinal),
        max_pair_coordinate_error=max(pair_x, pair_y),
        max_probe_residual=max(probe_x, probe_y),
    )


def build_distributed_constraint_transform(
    spaces: CrossSectionSpaces,
    constraints: CrossSectionFloquetConstraints,
) -> DistributedConstraintTransform:
    """Create the distributed full-to-free map ``u = C q`` without root gather."""

    V = spaces.mixed
    comm = V.mesh.comm
    index_map = V.dofmap.index_map
    if int(V.dofmap.index_map_bs) != 1:
        raise NotImplementedError("The QEP constraint transform currently requires block size one.")
    full_local = int(index_map.size_local)
    full_global = int(index_map.size_global)
    ownership_start, ownership_end = map(int, index_map.local_range)

    global_slaves = np.asarray(
        sorted(
            int(value)
            for values in comm.allgather(constraints.slave_global.tolist())
            for value in values
        ),
        dtype=np.int64,
    )
    if len(np.unique(global_slaves)) != len(global_slaves):
        raise RuntimeError("Duplicate globally owned slave rows were detected.")
    slave_set = set(int(value) for value in global_slaves)
    if any(int(master) in slave_set for master in constraints.master_global):
        raise RuntimeError("Constraint transform cannot contain slave-to-slave chains.")

    reduced_global = full_global - len(global_slaves)
    local_slave_count = len(constraints.slave_global)
    reduced_local = full_local - local_slave_count

    def reduced_index(global_dof: int) -> int:
        return int(global_dof - np.searchsorted(global_slaves, global_dof, side="left"))

    C = PETSc.Mat().createAIJ(
        size=((full_local, full_global), (reduced_local, reduced_global)),
        nnz=max(1, int(max(np.diff(constraints.offsets), default=1))),
        comm=comm,
    )
    C.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR, False)
    local_constraint_rows = {
        int(slave): row for row, slave in enumerate(constraints.slave_global)
    }
    for global_row in range(ownership_start, ownership_end):
        constraint_row = local_constraint_rows.get(global_row)
        if constraint_row is None:
            C.setValue(global_row, reduced_index(global_row), 1.0)
            continue
        start = int(constraints.offsets[constraint_row])
        stop = int(constraints.offsets[constraint_row + 1])
        columns = [
            reduced_index(int(master))
            for master in constraints.master_global[start:stop]
        ]
        C.setValues(
            [global_row],
            columns,
            constraints.coefficients[start:stop][None, :],
        )
    C.assemble()
    return DistributedConstraintTransform(
        matrix=C,
        full_global_size=full_global,
        reduced_global_size=reduced_global,
        full_local_size=full_local,
        reduced_local_size=reduced_local,
        global_slave_count=len(global_slaves),
    )


def reduce_matrix_hermitian(
    matrix: PETSc.Mat,
    transform: PETSc.Mat,
    *,
    transform_h: PETSc.Mat | None = None,
) -> PETSc.Mat:
    """Return ``C^H A C`` using distributed PETSc sparse products."""

    product = matrix.matMult(transform)
    owns_transpose = transform_h is None
    if transform_h is None:
        transform_h = PETSc.Mat()
        transform.hermitianTranspose(transform_h)
    reduced = transform_h.matMult(product)
    product.destroy()
    if owns_transpose:
        transform_h.destroy()
    return reduced
