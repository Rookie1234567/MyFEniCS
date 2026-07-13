from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from mpi4py import MPI
from scipy import sparse
from scipy.sparse import linalg as spla

from dolfinx import fem, mesh

from ..common.config import SimulationConfig


@dataclass
class FloquetConstraintData:
    slave_dofs: np.ndarray
    master_dofs: np.ndarray
    coefficients: np.ndarray
    offsets: np.ndarray
    phase: complex
    orientation_factors: np.ndarray
    max_pair_y_error: float
    max_probe_error: float
    master_owners: np.ndarray | None = None
    master_dofs_are_global: bool = False


def _facet_dofs(V, facet_dim: int, facet: int) -> np.ndarray:
    dofs = fem.locate_dofs_topological(
        V, facet_dim, np.asarray([facet], dtype=np.int32)
    )
    if len(dofs) < 1:
        raise RuntimeError(f"No H(curl) dofs were found on Floquet facet {facet}.")
    return np.asarray(dofs, dtype=np.int32)


def _local_dof_global_info(
    V, dofs: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    index_map = V.dofmap.index_map
    bs = V.dofmap.index_map_bs
    comm = V.mesh.comm

    dofs = np.asarray(dofs, dtype=np.int64)
    blocks = dofs // bs
    components = dofs % bs
    global_blocks = index_map.local_to_global(blocks.astype(np.int32)).astype(np.int64)
    global_dofs = global_blocks * bs + components

    owned = blocks < index_map.size_local
    owners = np.empty(len(dofs), dtype=np.int32)
    owners[owned] = comm.rank
    if np.any(~owned):
        ghost_owners = np.asarray(index_map.owners, dtype=np.int32)
        owners[~owned] = ghost_owners[blocks[~owned] - index_map.size_local]
    return global_dofs.astype(np.int64), owners, owned


def _facet_probe_values(
    V,
    cfg: SimulationConfig,
    dofs: np.ndarray,
    y_mid: float,
    num_probes: int,
) -> np.ndarray:
    values = np.empty((len(dofs), num_probes), dtype=np.complex128)
    y_scale = max(cfg.mesh_target_size, 1e-12)

    for power in range(num_probes):
        probe = fem.Function(V, name=f"floquet_probe_{power}")

        def vertical_probe(x, power=power):
            field = np.zeros((2, x.shape[1]), dtype=np.complex128)
            eta = (x[1] - y_mid) / y_scale
            field[1] = eta**power * np.exp(1j * cfg.kx * x[0])
            return field

        probe.interpolate(vertical_probe)
        values[:, power] = probe.x.array[dofs]
    return values


def _facet_constraint_matrix(
    V,
    cfg: SimulationConfig,
    left_dofs: np.ndarray,
    right_dofs: np.ndarray,
    y_mid: float,
) -> tuple[np.ndarray, float]:
    num_left = len(left_dofs)
    num_right = len(right_dofs)
    num_probes = max(2 * max(num_left, num_right) + 2, 4)
    left_values = _facet_probe_values(V, cfg, left_dofs, y_mid, num_probes)
    right_values = _facet_probe_values(V, cfg, right_dofs, y_mid, num_probes)
    return _transform_from_probe_values(cfg, left_values, right_values)


def _transform_from_probe_values(
    cfg: SimulationConfig, left_values: np.ndarray, right_values: np.ndarray
) -> tuple[np.ndarray, float]:
    rank = np.linalg.matrix_rank(left_values, tol=1e-11)
    if rank < left_values.shape[0]:
        raise RuntimeError(
            f"Floquet probe fields span only rank {rank} for {left_values.shape[0]} left facet dofs. "
            "Try lowering nedelec_degree or refining the boundary mesh."
        )

    transform = (right_values / cfg.floquet_phase) @ np.linalg.pinv(left_values)
    residual = right_values - cfg.floquet_phase * transform @ left_values
    denom = max(np.linalg.norm(right_values), 1e-30)
    return transform, float(np.linalg.norm(residual) / denom)


def _build_floquet_constraints_serial(
    V, mesh_data, cfg: SimulationConfig
) -> FloquetConstraintData:
    msh = mesh_data.mesh
    facet_dim = msh.topology.dim - 1
    left_facets = np.asarray(mesh_data.facet_tags.find(cfg.tags.left), dtype=np.int32)
    right_facets = np.asarray(mesh_data.facet_tags.find(cfg.tags.right), dtype=np.int32)
    if len(left_facets) != len(right_facets):
        raise RuntimeError(
            f"Left/right Floquet facet counts differ: left={len(left_facets)}, right={len(right_facets)}"
        )

    left_mid = mesh.compute_midpoints(msh, facet_dim, left_facets)
    right_mid = mesh.compute_midpoints(msh, facet_dim, right_facets)
    left_order = np.argsort(left_mid[:, 1])
    right_order = np.argsort(right_mid[:, 1])
    left_facets = left_facets[left_order]
    right_facets = right_facets[right_order]
    left_y = left_mid[left_order, 1]
    right_y = right_mid[right_order, 1]
    max_pair_y_error = float(np.max(np.abs(left_y - right_y))) if len(left_y) else 0.0
    if max_pair_y_error > 1e-10:
        raise RuntimeError(
            f"Left/right Floquet facets cannot be paired by y coordinate; max error={max_pair_y_error:g}"
        )

    slave_dofs: list[int] = []
    master_dofs: list[int] = []
    master_owners: list[int] = []
    coefficients: list[complex] = []
    offsets: list[int] = [0]
    orientation_factors: list[complex] = []
    probe_errors: list[float] = []

    for left_facet, right_facet, left_mid_y, right_mid_y in zip(
        left_facets, right_facets, left_y, right_y
    ):
        left_dofs = _facet_dofs(V, facet_dim, int(left_facet))
        right_dofs = _facet_dofs(V, facet_dim, int(right_facet))
        if len(left_dofs) != len(right_dofs):
            raise RuntimeError(
                f"Floquet facet dof counts differ: left facet {left_facet} has {len(left_dofs)}, "
                f"right facet {right_facet} has {len(right_dofs)}."
            )

        transform, probe_error = _facet_constraint_matrix(
            V,
            cfg,
            left_dofs,
            right_dofs,
            y_mid=0.5 * (float(left_mid_y) + float(right_mid_y)),
        )
        probe_errors.append(probe_error)
        global_left, owners_left, _ = _local_dof_global_info(V, left_dofs)

        cutoff = max(1e-12, 1e-10 * float(np.max(np.abs(transform))))
        for row, slave in enumerate(right_dofs):
            slave_dofs.append(int(slave))
            row_coefficients = cfg.floquet_phase * transform[row]
            used = False
            for master, owner, coefficient in zip(
                global_left, owners_left, row_coefficients
            ):
                if abs(coefficient) <= cutoff:
                    continue
                master_dofs.append(int(master))
                master_owners.append(int(owner))
                coefficients.append(complex(coefficient))
                orientation_factors.append(complex(coefficient / cfg.floquet_phase))
                used = True
            if not used:
                best = int(np.argmax(np.abs(row_coefficients)))
                master_dofs.append(int(global_left[best]))
                master_owners.append(int(owners_left[best]))
                coefficient = complex(row_coefficients[best])
                coefficients.append(coefficient)
                orientation_factors.append(complex(coefficient / cfg.floquet_phase))
            offsets.append(len(master_dofs))

    return FloquetConstraintData(
        slave_dofs=np.asarray(slave_dofs, dtype=np.int32),
        master_dofs=np.asarray(master_dofs, dtype=np.int64),
        coefficients=np.asarray(coefficients, dtype=np.complex128),
        offsets=np.asarray(offsets, dtype=np.int32),
        phase=cfg.floquet_phase,
        orientation_factors=np.asarray(orientation_factors, dtype=np.complex128),
        max_pair_y_error=max_pair_y_error,
        max_probe_error=max(probe_errors, default=0.0),
        master_owners=np.asarray(master_owners, dtype=np.int32),
        master_dofs_are_global=False,
    )


def _y_key(value: float) -> int:
    return int(round(float(value) / 1e-12))


def _local_facet_records(V, mesh_data, tag: int) -> list[dict[str, object]]:
    msh = mesh_data.mesh
    facet_dim = msh.topology.dim - 1
    facets = np.asarray(mesh_data.facet_tags.find(tag), dtype=np.int32)
    if len(facets) == 0:
        return []
    midpoints = mesh.compute_midpoints(msh, facet_dim, facets)
    records: list[dict[str, object]] = []
    for facet, midpoint in zip(facets, midpoints):
        dofs = _facet_dofs(V, facet_dim, int(facet))
        y_mid = float(midpoint[1])
        global_dofs, owners, _ = _local_dof_global_info(V, dofs)
        records.append(
            {
                "y": y_mid,
                "key": _y_key(y_mid),
                "local_facet": int(facet),
                "local_dofs": dofs,
                "global_dofs": global_dofs,
                "owners": owners,
                "rank": msh.comm.rank,
            }
        )
    return records


def _merge_records(
    records_by_rank: list[list[dict[str, object]]],
) -> dict[int, dict[str, object]]:
    merged: dict[int, dict[str, object]] = {}
    for records in records_by_rank:
        for record in records:
            key = int(record["key"])
            if key not in merged or int(record["rank"]) < int(merged[key]["rank"]):
                merged[key] = record
    return merged


def _local_facet_map(mesh_data, tag: int) -> dict[int, dict[str, object]]:
    msh = mesh_data.mesh
    facet_dim = msh.topology.dim - 1
    facets = np.asarray(mesh_data.facet_tags.find(tag), dtype=np.int32)
    if len(facets) == 0:
        return {}
    midpoints = mesh.compute_midpoints(msh, facet_dim, facets)
    records: dict[int, dict[str, object]] = {}
    for facet, midpoint in zip(facets, midpoints):
        y_mid = float(midpoint[1])
        key = _y_key(y_mid)
        records[key] = {"y": y_mid, "local_facet": int(facet), "rank": msh.comm.rank}
    return records


def _collective_dof_record_for_key(
    V,
    mesh_data,
    local_facets: dict[int, dict[str, object]],
    key: int,
) -> dict[str, object] | None:
    facet_dim = mesh_data.mesh.topology.dim - 1
    facet_record = local_facets.get(key)
    if facet_record is None:
        facets = np.asarray([], dtype=np.int32)
    else:
        facets = np.asarray([int(facet_record["local_facet"])], dtype=np.int32)
    dofs = fem.locate_dofs_topological(V, facet_dim, facets)
    if facet_record is None:
        return None
    dofs = np.asarray(dofs, dtype=np.int32)
    global_dofs, owners, _ = _local_dof_global_info(V, dofs)
    return {
        "y": float(facet_record["y"]),
        "key": key,
        "local_facet": int(facet_record["local_facet"]),
        "local_dofs": dofs,
        "global_dofs": global_dofs,
        "owners": owners,
        "rank": mesh_data.mesh.comm.rank,
    }


def _collective_probe_values_for_key(
    V,
    cfg: SimulationConfig,
    key: int,
    y_mid: float,
    num_probes: int,
    local_records: dict[int, dict[str, object]],
) -> np.ndarray | None:
    record = local_records.get(key)
    dofs = (
        np.asarray(record["local_dofs"], dtype=np.int32)
        if record is not None
        else np.asarray([], dtype=np.int32)
    )
    values = np.empty((len(dofs), num_probes), dtype=np.complex128)
    y_scale = max(cfg.mesh_target_size, 1e-12)

    for power in range(num_probes):
        probe = fem.Function(V, name=f"floquet_probe_{key}_{power}")

        def vertical_probe(x, power=power, y_mid=y_mid):
            field = np.zeros((2, x.shape[1]), dtype=np.complex128)
            eta = (x[1] - y_mid) / y_scale
            field[1] = eta**power * np.exp(1j * cfg.kx * x[0])
            return field

        probe.interpolate(vertical_probe)
        if len(dofs):
            values[:, power] = probe.x.array[dofs]
    return values if record is not None else None


def _build_floquet_constraints_parallel(
    V, mesh_data, cfg: SimulationConfig
) -> FloquetConstraintData:
    comm = mesh_data.mesh.comm
    local_left_facets = _local_facet_map(mesh_data, cfg.tags.left)
    local_right_facets = _local_facet_map(mesh_data, cfg.tags.right)
    left_keys = sorted(
        {key for keys in comm.allgather(list(local_left_facets)) for key in keys}
    )
    right_keys = sorted(
        {key for keys in comm.allgather(list(local_right_facets)) for key in keys}
    )
    if not left_keys:
        raise RuntimeError("No left Floquet facets were found across MPI ranks.")
    if not right_keys:
        raise RuntimeError("No right Floquet facets were found across MPI ranks.")
    all_keys = sorted(set(left_keys) | set(right_keys))

    slave_dofs: list[int] = []
    master_dofs: list[int] = []
    master_owners: list[int] = []
    coefficients: list[complex] = []
    offsets: list[int] = [0]
    orientation_factors: list[complex] = []
    probe_errors: list[float] = []
    pair_errors: list[float] = []

    for key in all_keys:
        left_key = key
        if left_key not in left_keys:
            nearest_key = min(left_keys, key=lambda candidate: abs(candidate - key))
            if abs(nearest_key - key) > 100:
                raise RuntimeError(
                    f"No matching left Floquet facet was found for right facet key={key}."
                )
            left_key = nearest_key

        local_left_record = _collective_dof_record_for_key(
            V, mesh_data, local_left_facets, left_key
        )
        gathered_left_records = comm.allgather(local_left_record)
        left_record = next(
            (record for record in gathered_left_records if record is not None), None
        )
        if left_record is None:
            raise RuntimeError(
                f"No rank produced left dofs for Floquet key {left_key}."
            )

        local_right_record = _collective_dof_record_for_key(
            V, mesh_data, local_right_facets, key
        )
        gathered_right_records = comm.allgather(local_right_record)
        right_record_global = next(
            (record for record in gathered_right_records if record is not None), None
        )
        if key not in right_keys or right_record_global is None:
            continue

        right_y = float(right_record_global["y"])
        left_y = float(left_record["y"])
        pair_errors.append(abs(left_y - right_y))

        num_left = len(left_record["global_dofs"])
        num_right = len(right_record_global["global_dofs"])
        if num_left != num_right:
            raise RuntimeError(
                f"Floquet facet dof counts differ on rank {comm.rank}: "
                f"left has {num_left}, right has {num_right}."
            )

        num_probes = max(2 * max(num_left, num_right) + 2, 4)
        local_left = (
            {left_key: local_left_record} if local_left_record is not None else {}
        )
        local_right = (
            {key: local_right_record} if local_right_record is not None else {}
        )
        local_left_values = _collective_probe_values_for_key(
            V, cfg, left_key, left_y, num_probes, local_left
        )
        gathered_left_values = comm.allgather(local_left_values)
        left_values = next(
            (values for values in gathered_left_values if values is not None), None
        )
        if left_values is None:
            raise RuntimeError(
                f"No rank produced left probe values for Floquet key {left_key}."
            )

        local_right_values = _collective_probe_values_for_key(
            V, cfg, key, right_y, num_probes, local_right
        )
        if local_right_record is None:
            continue
        right_dofs = np.asarray(local_right_record["local_dofs"], dtype=np.int32)
        right_global, _, right_owned = _local_dof_global_info(V, right_dofs)
        right_values = np.asarray(local_right_values)
        transform, probe_error = _transform_from_probe_values(
            cfg, np.asarray(left_values), right_values
        )
        probe_errors.append(probe_error)

        cutoff = max(1e-12, 1e-10 * float(np.max(np.abs(transform))))
        left_global = np.asarray(left_record["global_dofs"], dtype=np.int64)
        left_owners = np.asarray(left_record["owners"], dtype=np.int32)
        for row, (slave, owned) in enumerate(zip(right_dofs, right_owned)):
            if not owned:
                continue
            slave_dofs.append(int(slave))
            row_coefficients = cfg.floquet_phase * transform[row]
            used = False
            for master, owner, coefficient in zip(
                left_global, left_owners, row_coefficients
            ):
                if int(master) == int(right_global[row]):
                    continue
                if abs(coefficient) <= cutoff:
                    continue
                master_dofs.append(int(master))
                master_owners.append(int(owner))
                coefficients.append(complex(coefficient))
                orientation_factors.append(complex(coefficient / cfg.floquet_phase))
                used = True
            if not used:
                best = int(np.argmax(np.abs(row_coefficients)))
                master_dofs.append(int(left_global[best]))
                master_owners.append(int(left_owners[best]))
                coefficient = complex(row_coefficients[best])
                coefficients.append(coefficient)
                orientation_factors.append(complex(coefficient / cfg.floquet_phase))
            offsets.append(len(master_dofs))

    local_pair_error = max(pair_errors, default=0.0)
    local_probe_error = max(probe_errors, default=0.0)
    max_pair_y_error = comm.allreduce(local_pair_error, op=MPI.MAX)
    max_probe_error = comm.allreduce(local_probe_error, op=MPI.MAX)

    return FloquetConstraintData(
        slave_dofs=np.asarray(slave_dofs, dtype=np.int32),
        master_dofs=np.asarray(master_dofs, dtype=np.int64),
        coefficients=np.asarray(coefficients, dtype=np.complex128),
        offsets=np.asarray(offsets, dtype=np.int32),
        phase=cfg.floquet_phase,
        orientation_factors=np.asarray(orientation_factors, dtype=np.complex128),
        max_pair_y_error=float(max_pair_y_error),
        max_probe_error=float(max_probe_error),
        master_owners=np.asarray(master_owners, dtype=np.int32),
        master_dofs_are_global=True,
    )


def build_floquet_constraints(
    V, mesh_data, cfg: SimulationConfig
) -> FloquetConstraintData:
    """Constrain right boundary H(curl) edge dofs to left boundary dofs."""
    if mesh_data.mesh.comm.size == 1:
        return _build_floquet_constraints_serial(V, mesh_data, cfg)
    return _build_floquet_constraints_parallel(V, mesh_data, cfg)


def solve_with_constraints_with_stats(A_csr, b, constraints: FloquetConstraintData):
    """Solve the reduced system and also return its structural diagnostics."""

    if MPI.COMM_WORLD.size != 1:
        raise RuntimeError(
            "Manual C^H A C elimination is a serial verification backend and cannot run with MPI."
        )
    n = A_csr.shape[0]
    slave = constraints.slave_dofs
    master = constraints.master_dofs
    coefficients = constraints.coefficients
    offsets = constraints.offsets

    is_slave = np.zeros(n, dtype=bool)
    is_slave[slave] = True
    free = np.flatnonzero(~is_slave)
    reduced_index = -np.ones(n, dtype=np.int64)
    reduced_index[free] = np.arange(len(free), dtype=np.int64)

    if np.any(reduced_index[master] < 0):
        raise RuntimeError("Floquet master dofs cannot also be slave dofs.")

    slave_rows = np.repeat(slave, np.diff(offsets))
    rows = np.concatenate([free, slave_rows])
    cols = np.concatenate([reduced_index[free], reduced_index[master]])
    data = np.concatenate([np.ones(len(free), dtype=np.complex128), coefficients])
    C = sparse.coo_matrix(
        (data, (rows, cols)), shape=(n, len(free)), dtype=np.complex128
    ).tocsr()

    A_reduced = (C.conjugate().transpose() @ A_csr @ C).tocsc()
    b_reduced = C.conjugate().transpose() @ b
    x_reduced = spla.spsolve(A_reduced, b_reduced)
    reduced_residual = np.linalg.norm(A_reduced @ x_reduced - b_reduced) / max(
        np.linalg.norm(b_reduced), 1e-30
    )
    x_full = C @ x_reduced
    return (
        np.asarray(x_full, dtype=np.complex128),
        float(reduced_residual),
        int(A_reduced.shape[0]),
        int(A_reduced.nnz),
    )


def solve_with_constraints(A_csr, b, constraints: FloquetConstraintData):
    """Solve C^H A C q = C^H b, then reconstruct the full vector u=Cq."""

    solution, residual, rows, _nnz = solve_with_constraints_with_stats(
        A_csr, b, constraints
    )
    return solution, residual, rows


def dof_trace_mismatch(values: np.ndarray, constraints: FloquetConstraintData) -> float:
    if constraints.master_dofs_are_global:
        return float("nan")
    right = values[constraints.slave_dofs]
    predicted = np.empty(len(constraints.slave_dofs), dtype=np.complex128)
    for i in range(len(constraints.slave_dofs)):
        start = constraints.offsets[i]
        end = constraints.offsets[i + 1]
        predicted[i] = np.dot(
            constraints.coefficients[start:end],
            values[constraints.master_dofs[start:end]],
        )
    diff = right - predicted
    denom = max(np.linalg.norm(right), np.linalg.norm(predicted), 1e-30)
    return float(np.linalg.norm(diff) / denom)
