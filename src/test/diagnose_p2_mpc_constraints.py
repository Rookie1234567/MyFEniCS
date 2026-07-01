from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from mpi4py import MPI

from dolfinx import fem

from src.common.config_3d import SimulationConfig3D
from src.constraints import floquet_3d
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.runners.run_3d_cases import _stage_defaults
from src.solvers.common_3d_solve import _create_nedelec_space


def _make_cfg() -> SimulationConfig3D:
    values = _stage_defaults("stage4_flat_layer_sanity")
    values.update(
        {
            "lambda0": 633.0,
            "n_substrate": 1.0 + 0.0j,
            "mesh_target_size": 20.0,
            "nedelec_degree": 2,
            "visualization_degree": 1,
            "floquet_constraint_mode": "auto",
        }
    )
    return SimulationConfig3D(**values)


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose p=2 3D Floquet MPC coefficient residuals.")
    parser.add_argument("--verbose", action="store_true", help="Print worst face block and permutation details.")
    args = parser.parse_args()
    comm = MPI.COMM_WORLD
    cfg = _make_cfg()
    mesh_data = build_airbox_mesh_3d(cfg, Path("/tmp/p2_constraint_resid"))
    V = _create_nedelec_space(mesh_data.mesh, cfg)
    context = floquet_3d._build_topological_trace_context_p2(V, mesh_data, cfg)
    x_edge_data = floquet_3d._build_p2_edge_constraints_for_kind(context, cfg, "x", comm)
    x_face_data = floquet_3d._build_p2_face_constraints_for_kind(context, cfg, "x", comm)
    y_edge_data = floquet_3d._build_p2_edge_constraints_for_kind(context, cfg, "y", comm)
    y_face_data = floquet_3d._build_p2_face_constraints_for_kind(context, cfg, "y", comm)
    corner_data = floquet_3d._build_p2_edge_constraints_for_kind(context, cfg, "corner", comm)

    field = fem.Function(V)
    field.interpolate(lambda x: np.vstack((0.0 * x[0], np.exp(1j * cfg.kz * x[2]), 0.0 * x[0])))
    field.x.scatter_forward()

    local_values = np.asarray(field.x.array, dtype=np.complex128)
    imap = V.dofmap.index_map
    bs = V.dofmap.index_map_bs
    owned_size = imap.size_local * bs
    local_to_global = np.empty(imap.size_local + imap.num_ghosts, dtype=np.int64)
    local_to_global[: imap.size_local] = np.arange(imap.local_range[0], imap.local_range[1], dtype=np.int64)
    if imap.num_ghosts:
        local_to_global[imap.size_local :] = imap.ghosts
    dof_local_to_global = local_to_global

    global_owned_values = {
        int(dof_local_to_global[i]): complex(local_values[i]) for i in range(min(owned_size, len(local_values)))
    }
    gathered = comm.allgather(global_owned_values)
    value_by_global: dict[int, complex] = {}
    for packet in gathered:
        value_by_global.update(packet)

    def block_stats(label: str, data: dict[str, object]) -> dict[str, object]:
        local_max = 0.0
        local_count = 0
        local_bad = 0
        local_bad_owned = 0
        local_bad_ghost = 0
        worst: tuple[float, int, int, list[int], list[complex]] = (0.0, -1, -1, [], [])
        for slave_local, local_terms in data["local_maps"].items():
            slave_global, masters, _owners, coeffs = local_terms
            predicted = 0.0 + 0.0j
            master_list = [int(master) for master in np.asarray(masters, dtype=np.int64)]
            coeff_list = [complex(coeff) for coeff in np.asarray(coeffs, dtype=np.complex128)]
            for master, coeff in zip(master_list, coeff_list):
                predicted += coeff * value_by_global[master]
            actual = complex(local_values[int(slave_local)])
            err = abs(actual - predicted)
            local_max = max(local_max, float(err))
            local_count += 1
            if err > 1.0e-10:
                local_bad += 1
                if int(slave_local) < owned_size:
                    local_bad_owned += 1
                else:
                    local_bad_ghost += 1
            if err > worst[0]:
                worst = (float(err), int(slave_local), int(slave_global), master_list, coeff_list)
        gathered_worst = comm.gather(worst, root=0)
        global_worst = None
        if comm.rank == 0 and gathered_worst:
            global_worst = max(gathered_worst, key=lambda item: item[0])
        return {
            "label": label,
            "count": int(comm.allreduce(local_count, op=MPI.SUM)),
            "bad": int(comm.allreduce(local_bad, op=MPI.SUM)),
            "bad_owned": int(comm.allreduce(local_bad_owned, op=MPI.SUM)),
            "bad_ghost": int(comm.allreduce(local_bad_ghost, op=MPI.SUM)),
            "max_error": float(comm.allreduce(local_max, op=MPI.MAX)),
            "worst": global_worst,
        }

    stats = [
        block_stats("x_edge", x_edge_data),
        block_stats("x_face", x_face_data),
        block_stats("y_edge", y_edge_data),
        block_stats("y_face", y_face_data),
        block_stats("corner", corner_data),
    ]
    debug_local: tuple[float, dict[str, object] | None] = (0.0, None)
    permutation_stats: dict[tuple[object, ...], list[int | float]] = {}
    tol = float(context["tol"])
    for record in context["face_records"]:
        if not floquet_3d._record_is_face_slave_kind(record, cfg, tol, "x"):
            continue
        target, phase = floquet_3d._target_for_kind(record, cfg, "x")
        target_key = floquet_3d._face_match_key(target, int(record["normal_axis"]), tol)
        master = context["face_global_by_key"][target_key]
        transform = floquet_3d._face_transform_p2(context, record, master, cfg, "x", tol)
        shifted = np.asarray(record["geometry_coords"], dtype=np.float64).copy()
        shifted[:, 0] -= cfg.x_max - cfg.x_min
        permutation = floquet_3d._face_vertex_permutation(
            shifted,
            np.asarray(master["geometry_coords"], dtype=np.float64),
            tol,
        )
        stat_key = (
            permutation,
            int(record["local_entity"]),
            int(master["local_entity"]),
            tuple(np.sign(np.round(np.asarray(record["normal"], dtype=float), 12)).astype(int).tolist()),
            tuple(np.sign(np.round(np.asarray(master["normal"], dtype=float), 12)).astype(int).tolist()),
        )
        permutation_stats.setdefault(stat_key, [0, 0, 0.0])
        for row, slave_local in enumerate(np.asarray(record["local_dofs"], dtype=np.int32)):
            predicted = 0.0 + 0.0j
            for master_global, coeff in zip(np.asarray(master["global_dofs"], dtype=np.int64), phase * transform[row, :]):
                predicted += complex(coeff) * value_by_global[int(master_global)]
            actual = complex(local_values[int(slave_local)])
            err = abs(actual - predicted)
            permutation_stats[stat_key][0] += 1
            if err > 1.0e-10:
                permutation_stats[stat_key][1] += 1
            permutation_stats[stat_key][2] = max(float(permutation_stats[stat_key][2]), float(err))
            if err > debug_local[0]:
                debug_local = (
                    float(err),
                    {
                        "rank": comm.rank,
                        "slave_face": int(record["face"]),
                        "master_face": int(master["face"]),
                        "slave_local_dofs": np.asarray(record["local_dofs"], dtype=np.int32).tolist(),
                        "slave_global_dofs": np.asarray(record["global_dofs"], dtype=np.int64).tolist(),
                        "master_global_dofs": np.asarray(master["global_dofs"], dtype=np.int64).tolist(),
                        "transform": np.asarray(transform).tolist(),
                        "slave_values": [
                            complex(local_values[int(local_dof)])
                            for local_dof in np.asarray(record["local_dofs"], dtype=np.int32)
                        ],
                        "master_values": [
                            value_by_global[int(global_dof)]
                            for global_dof in np.asarray(master["global_dofs"], dtype=np.int64)
                        ],
                        "slave_geometry_coords": np.asarray(record["geometry_coords"], dtype=float).tolist(),
                        "master_geometry_coords": np.asarray(master["geometry_coords"], dtype=float).tolist(),
                    },
                )
    debug_packets = comm.gather(debug_local, root=0)
    permutation_packets = comm.gather(permutation_stats, root=0)
    if comm.rank == 0:
        for item in stats:
            print(
                {
                    "label": item["label"],
                    "count": item["count"],
                    "bad": item["bad"],
                    "bad_owned": item["bad_owned"],
                    "bad_ghost": item["bad_ghost"],
                    "max_error": item["max_error"],
                }
            )
        if args.verbose and debug_packets:
            print({"x_face_worst_block": max(debug_packets, key=lambda item: item[0])})
        merged_permutations: dict[tuple[int, int, int, int], list[int | float]] = {}
        for packet in permutation_packets or []:
            for key, values in packet.items():
                merged = merged_permutations.setdefault(key, [0, 0, 0.0])
                merged[0] += int(values[0])
                merged[1] += int(values[1])
                merged[2] = max(float(merged[2]), float(values[2]))
        if args.verbose:
            print({"x_face_permutation_stats": {str(key): value for key, value in merged_permutations.items()}})


if __name__ == "__main__":
    main()
