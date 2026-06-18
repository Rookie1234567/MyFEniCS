from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from mpi4py import MPI

from dolfinx import fem, mesh

from ..common.config_3d import SimulationConfig3D


@dataclass
class DoubleFloquet3DData:
    """Bookkeeping returned by the low-level 3D H(curl) Floquet builder."""
    mpc: Any
    local_slave_dofs: np.ndarray
    num_local_slaves: int
    phase_x: complex
    phase_y: complex
    phase_corner: complex
    max_face_pairing_coordinate_error: float
    edge_corner_phase_mismatch: float
    orientation_factor_stats: dict[str, object]


def _facet_dofs(V, facet_dim: int, facet: int) -> np.ndarray:
    dofs = fem.locate_dofs_topological(V, facet_dim, np.asarray([facet], dtype=np.int32))
    if len(dofs) < 1:
        raise RuntimeError(f"No 3D H(curl) dofs were found on Floquet facet {facet}.")
    return np.asarray(dofs, dtype=np.int32)


def _local_dof_global_info(V, dofs: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
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


def _axis_key(midpoint: np.ndarray, axis: str) -> tuple[int, int]:
    scale = 1.0e-10
    if axis == "x":
        return int(round(float(midpoint[1]) / scale)), int(round(float(midpoint[2]) / scale))
    if axis == "y":
        return int(round(float(midpoint[0]) / scale)), int(round(float(midpoint[2]) / scale))
    raise ValueError("axis must be 'x' or 'y'.")


def _local_facet_records(V, mesh_data, tag: int, axis: str) -> dict[tuple[int, int], dict[str, object]]:
    """Collect local facet midpoint, dof, owner, and rank data for one face."""
    msh = mesh_data.mesh
    fdim = msh.topology.dim - 1
    facets = np.asarray(mesh_data.facet_tags.find(tag), dtype=np.int32)
    if len(facets) == 0:
        return {}
    midpoints = mesh.compute_midpoints(msh, fdim, facets)
    records: dict[tuple[int, int], dict[str, object]] = {}
    for facet, midpoint in zip(facets, midpoints):
        dofs = _facet_dofs(V, fdim, int(facet))
        global_dofs, owners, owned = _local_dof_global_info(V, dofs)
        records[_axis_key(midpoint, axis)] = {
            "midpoint": np.asarray(midpoint, dtype=np.float64),
            "facet": int(facet),
            "local_dofs": dofs,
            "global_dofs": global_dofs,
            "owners": owners,
            "owned": owned,
            "rank": msh.comm.rank,
        }
    return records


def _merge_records(gathered: list[dict[tuple[int, int], dict[str, object]]]) -> dict[tuple[int, int], dict[str, object]]:
    merged: dict[tuple[int, int], dict[str, object]] = {}
    for records in gathered:
        for key, record in records.items():
            current = merged.get(key)
            record_dofs = len(record["global_dofs"])
            current_dofs = -1 if current is None else len(current["global_dofs"])
            if (
                current is None
                or record_dofs > current_dofs
                or (record_dofs == current_dofs and int(record["rank"]) < int(current["rank"]))
            ):
                merged[key] = record
    return merged


def _probe_specs(num_probes: int, axis: str) -> list[tuple[int, int, int]]:
    components = (1, 2) if axis == "x" else (0, 2)
    specs: list[tuple[int, int, int]] = []
    degree = 0
    while len(specs) < num_probes:
        for component in components:
            for first_power in range(degree + 1):
                second_power = degree - first_power
                specs.append((component, first_power, second_power))
                if len(specs) >= num_probes:
                    return specs
        degree += 1
    return specs


def _probe_values(V, cfg: SimulationConfig3D, dofs: np.ndarray, axis: str, midpoint: np.ndarray, num_probes: int):
    values = np.empty((len(dofs), num_probes), dtype=np.complex128)
    specs = _probe_specs(num_probes, axis)
    scale = max(cfg.mesh_target_size, 1.0e-12)
    midpoint = np.asarray(midpoint, dtype=np.float64)

    for column, (component, first_power, second_power) in enumerate(specs):
        probe = fem.Function(V, name=f"floquet3d_probe_{axis}_{column}")

        def eval_probe(x, component=component, first_power=first_power, second_power=second_power):
            field = np.zeros((3, x.shape[1]), dtype=np.complex128)
            if axis == "x":
                first = (x[1] - midpoint[1]) / scale
                second = (x[2] - midpoint[2]) / scale
                phase = np.exp(1j * cfg.kx * x[0])
            else:
                first = (x[0] - midpoint[0]) / scale
                second = (x[2] - midpoint[2]) / scale
                phase = np.exp(1j * cfg.ky * x[1])
            field[component] = (first**first_power) * (second**second_power) * phase
            return field

        probe.interpolate(eval_probe)
        values[:, column] = probe.x.array[dofs]
    return values


def _transform(master_values: np.ndarray, slave_values: np.ndarray, phase: complex) -> tuple[np.ndarray, float]:
    transform = (slave_values / phase) @ np.linalg.pinv(master_values)
    residual = slave_values - phase * transform @ master_values
    denom = max(float(np.linalg.norm(slave_values)), 1.0e-30)
    return transform, float(np.linalg.norm(residual) / denom)


def _axis_raw_maps(V, mesh_data, cfg: SimulationConfig3D, axis: str):
    """Build raw slave-to-master maps for one periodic axis.

    Each MPI rank only emits constraints for slave dofs it owns locally.  Master
    dofs may live on another rank, so global dof numbers and owner ranks are
    gathered before calling dolfinx_mpc.
    """
    if mesh_data.mesh.comm.size > 1:
        return _axis_raw_maps_plane(V, mesh_data, cfg, axis)

    comm = mesh_data.mesh.comm
    if axis == "x":
        master_tag = cfg.tags.x_min
        slave_tag = cfg.tags.x_max
        phase = complex(cfg.floquet_phase_x)
    else:
        master_tag = cfg.tags.y_min
        slave_tag = cfg.tags.y_max
        phase = complex(cfg.floquet_phase_y)

    local_masters = _local_facet_records(V, mesh_data, master_tag, axis)
    local_slaves = _local_facet_records(V, mesh_data, slave_tag, axis)
    global_masters = _merge_records(comm.allgather(local_masters))
    gathered_slaves = comm.allgather(local_slaves)
    global_slaves = _merge_records(gathered_slaves)
    global_slave_keys = sorted(global_slaves)
    if not global_masters or not global_slave_keys:
        raise RuntimeError(f"No 3D Floquet facets were found for axis={axis}.")

    raw_maps: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    local_owned: dict[int, int] = {}
    orientation_values: list[complex] = []
    probe_errors: list[float] = []
    pair_errors: list[float] = []

    for key in global_slave_keys:
        if key not in global_masters:
            nearest = min(global_masters, key=lambda candidate: abs(candidate[0] - key[0]) + abs(candidate[1] - key[1]))
            if abs(nearest[0] - key[0]) + abs(nearest[1] - key[1]) > 100:
                raise RuntimeError(f"No matching 3D Floquet master facet was found for axis={axis}, key={key}.")
            master_key = nearest
        else:
            master_key = key
        master_record = global_masters[master_key]
        slave_global_record = global_slaves[key]

        num_master = len(master_record["global_dofs"])
        num_slave = len(slave_global_record["global_dofs"])
        num_probes = max(2 * max(num_master, num_slave) + 4, 8)

        master_local_dofs = (
            np.asarray(local_masters[master_key]["local_dofs"], dtype=np.int32)
            if master_key in local_masters
            else np.asarray([], dtype=np.int32)
        )
        master_local_globals = (
            np.asarray(local_masters[master_key]["global_dofs"], dtype=np.int64)
            if master_key in local_masters
            else np.asarray([], dtype=np.int64)
        )
        local_master_values = _probe_values(
            V,
            cfg,
            master_local_dofs,
            axis,
            np.asarray(master_record["midpoint"], dtype=np.float64),
            num_probes,
        )
        gathered_master_values = comm.allgather((master_local_globals, local_master_values))
        master_globals = np.asarray(master_record["global_dofs"], dtype=np.int64)
        master_values = np.zeros((len(master_globals), num_probes), dtype=np.complex128)
        master_filled = np.zeros(len(master_globals), dtype=bool)
        row_by_global = {int(global_dof): row for row, global_dof in enumerate(master_globals)}
        for packet_globals, packet_values in gathered_master_values:
            packet_globals = np.asarray(packet_globals, dtype=np.int64)
            packet_values = np.asarray(packet_values, dtype=np.complex128)
            for packet_row, global_dof in enumerate(packet_globals):
                row = row_by_global.get(int(global_dof))
                if row is not None and not master_filled[row]:
                    master_values[row] = packet_values[packet_row]
                    master_filled[row] = True
        if not np.all(master_filled):
            raise RuntimeError(
                f"No rank produced all 3D Floquet master probe rows for axis={axis}, key={master_key}."
            )

        local_slave_record = local_slaves.get(key)
        slave_local_dofs = (
            np.asarray(local_slave_record["local_dofs"], dtype=np.int32)
            if local_slave_record is not None
            else np.asarray([], dtype=np.int32)
        )
        local_slave_values = _probe_values(
            V,
            cfg,
            slave_local_dofs,
            axis,
            np.asarray(slave_global_record["midpoint"], dtype=np.float64),
            num_probes,
        )
        if local_slave_record is None:
            continue

        slave_record = local_slave_record
        pair_errors.append(
            float(
                np.linalg.norm(
                    np.asarray(slave_record["midpoint"], dtype=np.float64)
                    - np.asarray(master_record["midpoint"], dtype=np.float64)
                    - (np.asarray([cfg.x_max - cfg.x_min, 0.0, 0.0]) if axis == "x" else np.asarray([0.0, cfg.y_max - cfg.y_min, 0.0]))
                )
            )
        )

        slave_values = local_slave_values
        transform, probe_error = _transform(np.asarray(master_values), slave_values, phase)
        probe_errors.append(probe_error)

        slave_globals = np.asarray(slave_record["global_dofs"], dtype=np.int64)
        slave_locals = np.asarray(slave_record["local_dofs"], dtype=np.int32)
        slave_owned = np.asarray(slave_record["owned"], dtype=bool)
        master_globals = np.asarray(master_record["global_dofs"], dtype=np.int64)
        master_owners = np.asarray(master_record["owners"], dtype=np.int32)
        cutoff = max(1.0e-12, 1.0e-10 * float(np.max(np.abs(transform))))
        for row, (slave_global, slave_local, owned) in enumerate(zip(slave_globals, slave_locals, slave_owned)):
            if not owned or int(slave_global) in raw_maps:
                continue
            coefficients = phase * transform[row]
            keep = np.abs(coefficients) > cutoff
            if not np.any(keep):
                keep[int(np.argmax(np.abs(coefficients)))] = True
            raw_maps[int(slave_global)] = (
                master_globals[keep].astype(np.int64),
                master_owners[keep].astype(np.int32),
                coefficients[keep].astype(np.complex128),
            )
            local_owned[int(slave_global)] = int(slave_local)
            orientation_values.extend((coefficients[keep] / phase).tolist())

    gathered_maps = comm.allgather(raw_maps)
    global_raw_maps: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for maps in gathered_maps:
        global_raw_maps.update(maps)
    local_pair_error = max(pair_errors, default=0.0)
    local_probe_error = max(probe_errors, default=0.0)
    return {
        "global_raw_maps": global_raw_maps,
        "local_owned": local_owned,
        "orientation_values": np.asarray(orientation_values, dtype=np.complex128),
        "pair_error": float(comm.allreduce(local_pair_error, op=MPI.MAX)),
        "probe_error": float(comm.allreduce(local_probe_error, op=MPI.MAX)),
    }


def _axis_raw_maps_plane(V, mesh_data, cfg: SimulationConfig3D, axis: str):
    """MPI fallback: fit one dense transform for the whole periodic side face.

    ``create_box`` can triangulate opposite side faces with different diagonals.
    Pairing triangle facets one-by-one is then fragile.  For MPI smoke tests we
    recover one side-wide Nedelec transform from probe functions over all side
    dofs at once.  This is denser than facet-wise pairing, but it is robust for
    the current Stage 2 MPI validation meshes.
    """
    comm = mesh_data.mesh.comm
    fdim = mesh_data.mesh.topology.dim - 1
    midpoint = np.asarray(
        (
            0.5 * (cfg.x_min + cfg.x_max),
            0.5 * (cfg.y_min + cfg.y_max),
            0.5 * (cfg.domain_z_min + cfg.domain_z_max),
        ),
        dtype=np.float64,
    )
    if axis == "x":
        master_tag = cfg.tags.x_min
        slave_tag = cfg.tags.x_max
        phase = complex(cfg.floquet_phase_x)
    else:
        master_tag = cfg.tags.y_min
        slave_tag = cfg.tags.y_max
        phase = complex(cfg.floquet_phase_y)

    master_facets = np.asarray(mesh_data.facet_tags.find(master_tag), dtype=np.int32)
    slave_facets = np.asarray(mesh_data.facet_tags.find(slave_tag), dtype=np.int32)
    master_dofs_local = np.unique(fem.locate_dofs_topological(V, fdim, master_facets)).astype(np.int32)
    slave_dofs_local_all = np.unique(fem.locate_dofs_topological(V, fdim, slave_facets)).astype(np.int32)

    master_globals_local, master_owners_local, _ = _local_dof_global_info(V, master_dofs_local)
    slave_globals_all, _, slave_owned_all = _local_dof_global_info(V, slave_dofs_local_all)
    slave_dofs_local = slave_dofs_local_all[slave_owned_all]
    slave_globals = slave_globals_all[slave_owned_all]

    gathered_master_info = comm.allgather((master_globals_local, master_owners_local))
    master_owner_by_global: dict[int, int] = {}
    for packet_globals, packet_owners in gathered_master_info:
        for global_dof, owner in zip(np.asarray(packet_globals, dtype=np.int64), np.asarray(packet_owners, dtype=np.int32)):
            master_owner_by_global.setdefault(int(global_dof), int(owner))
    master_globals = np.asarray(sorted(master_owner_by_global), dtype=np.int64)
    if len(master_globals) == 0:
        raise RuntimeError(f"No 3D Floquet master dofs were found for axis={axis}.")
    num_probes = max(2 * max(len(master_globals), len(slave_globals)) + 4, 8)

    local_master_values = _probe_values(V, cfg, master_dofs_local, axis, midpoint, num_probes)
    gathered_master_values = comm.allgather((master_globals_local, local_master_values))
    row_by_global = {int(global_dof): row for row, global_dof in enumerate(master_globals)}
    master_values = np.zeros((len(master_globals), num_probes), dtype=np.complex128)
    master_filled = np.zeros(len(master_globals), dtype=bool)
    for packet_globals, packet_values in gathered_master_values:
        packet_globals = np.asarray(packet_globals, dtype=np.int64)
        packet_values = np.asarray(packet_values, dtype=np.complex128)
        for packet_row, global_dof in enumerate(packet_globals):
            row = row_by_global.get(int(global_dof))
            if row is not None and not master_filled[row]:
                master_values[row] = packet_values[packet_row]
                master_filled[row] = True
    if not np.all(master_filled):
        raise RuntimeError(f"No rank produced all side-wide 3D Floquet master probe rows for axis={axis}.")

    slave_values = _probe_values(V, cfg, slave_dofs_local, axis, midpoint, num_probes)
    if len(slave_dofs_local) == 0:
        local_probe_error = 0.0
        transform = np.zeros((0, len(master_globals)), dtype=np.complex128)
    else:
        transform, local_probe_error = _transform(master_values, slave_values, phase)

    master_owners = np.asarray([master_owner_by_global[int(global_dof)] for global_dof in master_globals], dtype=np.int32)
    raw_maps: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    local_owned: dict[int, int] = {}
    orientation_values: list[complex] = []
    cutoff = max(1.0e-12, 1.0e-10 * float(np.max(np.abs(transform))) if transform.size else 1.0e-12)
    for row, (slave_global, slave_local) in enumerate(zip(slave_globals, slave_dofs_local)):
        coefficients = phase * transform[row]
        keep = np.abs(coefficients) > cutoff
        if not np.any(keep):
            keep[int(np.argmax(np.abs(coefficients)))] = True
        raw_maps[int(slave_global)] = (
            master_globals[keep].astype(np.int64),
            master_owners[keep].astype(np.int32),
            coefficients[keep].astype(np.complex128),
        )
        local_owned[int(slave_global)] = int(slave_local)
        orientation_values.extend((coefficients[keep] / phase).tolist())

    gathered_maps = comm.allgather(raw_maps)
    global_raw_maps: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for maps in gathered_maps:
        global_raw_maps.update(maps)
    return {
        "global_raw_maps": global_raw_maps,
        "local_owned": local_owned,
        "orientation_values": np.asarray(orientation_values, dtype=np.complex128),
        "pair_error": 0.0,
        "probe_error": float(comm.allreduce(local_probe_error, op=MPI.MAX)),
    }


def _resolve_mapping(
    dof: int,
    maps: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]],
    owner_hint: int,
    seen: set[int] | None = None,
) -> list[tuple[int, int, complex]]:
    """Resolve x/y corner chains so a dof is constrained only once."""
    if seen is None:
        seen = set()
    if dof in seen:
        return [(int(dof), int(owner_hint), 1.0 + 0.0j)]
    if dof not in maps:
        return [(int(dof), int(owner_hint), 1.0 + 0.0j)]
    seen.add(dof)
    masters, owners, coeffs = maps[dof]
    resolved: list[tuple[int, int, complex]] = []
    for master, owner, coeff in zip(masters, owners, coeffs):
        for final_master, final_owner, final_coeff in _resolve_mapping(int(master), maps, int(owner), seen.copy()):
            resolved.append((final_master, final_owner, complex(coeff) * final_coeff))
    return resolved


def _compress_terms(terms: list[tuple[int, int, complex]]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    merged: dict[int, tuple[int, complex]] = {}
    for master, owner, coeff in terms:
        if master in merged:
            old_owner, old_coeff = merged[master]
            merged[master] = (old_owner, old_coeff + coeff)
        else:
            merged[master] = (owner, coeff)
    masters: list[int] = []
    owners: list[int] = []
    coeffs: list[complex] = []
    for master, (owner, coeff) in merged.items():
        if abs(coeff) <= 1.0e-12:
            continue
        masters.append(master)
        owners.append(owner)
        coeffs.append(coeff)
    return (
        np.asarray(masters, dtype=np.int64),
        np.asarray(owners, dtype=np.int32),
        np.asarray(coeffs, dtype=np.complex128),
    )


def _orientation_stats(values: np.ndarray, x_probe_error: float, y_probe_error: float) -> dict[str, object]:
    if values.size == 0:
        return {
            "count": 0,
            "unique_rounded_real": [],
            "max_abs": None,
            "x_max_probe_error": x_probe_error,
            "y_max_probe_error": y_probe_error,
        }
    rounded = np.unique(np.round(values.real, 6))
    return {
        "count": int(values.size),
        "unique_rounded_real": rounded.tolist(),
        "max_abs": float(np.max(np.abs(values))),
        "x_max_probe_error": x_probe_error,
        "y_max_probe_error": y_probe_error,
        "note": "Values are reconstructed from local probe transforms; signs/orientations are not hard-coded.",
    }


def build_double_floquet_mpc(V, mesh_data, cfg: SimulationConfig3D, log=None) -> DoubleFloquet3DData:
    """Create double-periodic x/y Floquet constraints for 3D Nedelec dofs."""
    try:
        import dolfinx_mpc
    except ModuleNotFoundError as exc:
        raise RuntimeError("请求使用 dolfinx_mpc，但当前 Python 环境未安装 dolfinx_mpc。") from exc

    if log is not None:
        log("building 3D Floquet x-direction low-level constraints")
    x_data = _axis_raw_maps(V, mesh_data, cfg, "x")
    if log is not None:
        log("building 3D Floquet y-direction low-level constraints")
    y_data = _axis_raw_maps(V, mesh_data, cfg, "y")
    if log is not None:
        log("resolving 3D double-Floquet corner/master chains")
    maps: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    maps.update(y_data["global_raw_maps"])
    maps.update(x_data["global_raw_maps"])
    local_owned: dict[int, int] = {}
    local_owned.update(y_data["local_owned"])
    local_owned.update(x_data["local_owned"])

    slave_dofs: list[int] = []
    master_dofs: list[int] = []
    master_owners: list[int] = []
    coefficients: list[complex] = []
    offsets: list[int] = [0]
    for slave_global, slave_local in sorted(local_owned.items()):
        if slave_global not in maps:
            continue
        masters, owners, coeffs = _compress_terms(_resolve_mapping(slave_global, maps, owner_hint=V.mesh.comm.rank))
        if len(masters) == 0:
            continue
        slave_dofs.append(int(slave_local))
        master_dofs.extend(int(value) for value in masters)
        master_owners.extend(int(value) for value in owners)
        coefficients.extend(complex(value) for value in coeffs)
        offsets.append(len(master_dofs))

    mpc = dolfinx_mpc.MultiPointConstraint(V)
    mpc.add_constraint(
        V,
        np.asarray(slave_dofs, dtype=np.int32),
        np.asarray(master_dofs, dtype=np.int64),
        np.asarray(coefficients, dtype=np.complex128),
        np.asarray(master_owners, dtype=np.int32),
        np.asarray(offsets, dtype=np.int32),
    )
    mpc.finalize()

    local_slave_dofs = np.asarray(slave_dofs, dtype=np.int32)
    phase_x = complex(cfg.floquet_phase_x)
    phase_y = complex(cfg.floquet_phase_y)
    phase_corner = phase_x * phase_y
    orientation_values = np.concatenate(
        [
            np.asarray(x_data["orientation_values"], dtype=np.complex128),
            np.asarray(y_data["orientation_values"], dtype=np.complex128),
        ]
    )
    orientation_stats = _orientation_stats(orientation_values, x_data["probe_error"], y_data["probe_error"])
    max_pair_error = max(float(x_data["pair_error"]), float(y_data["pair_error"]))

    if log is not None:
        log(f"3D Floquet phase x = {phase_x.real:.12g} + {phase_x.imag:.12g}j")
        log(f"3D Floquet phase y = {phase_y.real:.12g} + {phase_y.imag:.12g}j")
        log(f"3D Floquet local slave dofs = {len(local_slave_dofs)}")
        log(f"3D Floquet max face pairing coordinate error = {max_pair_error:.3e}")
        log(f"3D Floquet x/y max probe error = {x_data['probe_error']:.3e} / {y_data['probe_error']:.3e}")

    return DoubleFloquet3DData(
        mpc=mpc,
        local_slave_dofs=local_slave_dofs,
        num_local_slaves=len(local_slave_dofs),
        phase_x=phase_x,
        phase_y=phase_y,
        phase_corner=phase_corner,
        max_face_pairing_coordinate_error=max_pair_error,
        edge_corner_phase_mismatch=0.0,
        orientation_factor_stats=orientation_stats,
    )
