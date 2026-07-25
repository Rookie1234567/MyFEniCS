from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from dolfinx import geometry, mesh as dmesh

from ..common.config_3d import SimulationConfig3D


REFERENCE_SCHEMA_VERSION = 1
MAX_REPLICATED_SAMPLE_BYTES = 64 * 1024 * 1024


def periodic_plane_sample_grid(
    cfg: SimulationConfig3D,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return an interior periodic x/y grid and flattened points on requested z planes.

    Half-cell offsets avoid sampling both copies of a periodic boundary.  Point
    ordering is ``(z, y, x, xyz)`` so archives can be reshaped deterministically.
    """

    nx = int(cfg.full3d_reference_sample_count_x)
    ny = int(cfg.full3d_reference_sample_count_y)
    plane_z = np.asarray(cfg.full3d_reference_plane_z, dtype=np.float64)
    if nx < 2 or ny < 2:
        raise ValueError("Full-3D reference sample counts must both be at least 2.")
    if plane_z.size == 0:
        raise ValueError("Full-3D reference export requires at least one z plane.")
    if np.unique(plane_z).size != plane_z.size:
        raise ValueError("Full-3D reference z planes must be unique.")
    if plane_z.size > 1 and np.any(np.diff(plane_z) <= 0.0):
        raise ValueError("Full-3D reference z planes must be strictly increasing.")
    if np.any(plane_z < cfg.physical_z_min) or np.any(plane_z > cfg.physical_z_max):
        raise ValueError(
            "Full-3D reference z planes must lie inside the physical domain "
            f"[{cfg.physical_z_min}, {cfg.physical_z_max}] nm."
        )

    x_nm = cfg.x_min + (np.arange(nx, dtype=np.float64) + 0.5) * cfg.period_x / nx
    y_nm = cfg.y_min + (np.arange(ny, dtype=np.float64) + 0.5) * cfg.period_y / ny
    zz, yy, xx = np.meshgrid(plane_z, y_nm, x_nm, indexing="ij")
    points_nm = np.column_stack((xx.ravel(), yy.ravel(), zz.ravel()))
    return x_nm, y_nm, plane_z, points_nm


def reference_plane_sides(plane_count: int, points_per_plane: int) -> np.ndarray:
    """Return deterministic one-sided z-trace selectors for ordered planes.

    The first interface is evaluated from its +z cell and the last interface
    from its -z cell, i.e. both traces are taken from inside the middle modal
    region.  Interior planes use the +z cell when they coincide with a mesh
    facet.  Values are repeated in the archive point ordering.
    """

    if plane_count < 2 or points_per_plane < 1:
        raise ValueError("Reference sampling requires at least two planes and one point per plane.")
    plane_sides = np.ones(plane_count, dtype=np.int8)
    plane_sides[-1] = -1
    return np.repeat(plane_sides, points_per_plane)


def _sample_distributed_function(
    function,
    points_nm: np.ndarray,
    z_sides: np.ndarray,
) -> np.ndarray:
    """Evaluate a distributed DOLFINx function with deterministic z traces."""

    mesh = function.function_space.mesh
    comm = mesh.comm
    points_nm = np.asarray(points_nm, dtype=np.float64).reshape((-1, 3))
    z_sides = np.asarray(z_sides, dtype=np.int8).reshape((-1,))
    if len(z_sides) != len(points_nm) or np.any(np.abs(z_sides) != 1):
        raise ValueError("Each reference point requires a +1 or -1 z-side selector.")
    tree = geometry.bb_tree(mesh, mesh.topology.dim)
    candidates = geometry.compute_collisions_points(tree, points_nm)
    collisions = geometry.compute_colliding_cells(mesh, candidates, points_nm)

    cell_map = mesh.topology.index_map(mesh.topology.dim)
    local_cells_with_ghosts = cell_map.size_local + cell_map.num_ghosts
    cell_midpoints = dmesh.compute_midpoints(
        mesh,
        mesh.topology.dim,
        np.arange(local_cells_with_ghosts, dtype=np.int32),
    )

    local_indices: list[int] = []
    local_cells: list[int] = []
    local_scores: list[float] = []
    for point_index in range(len(points_nm)):
        links = collisions.links(point_index)
        if len(links):
            offsets = cell_midpoints[links, 2] - points_nm[point_index, 2]
            scores = z_sides[point_index] * offsets
            selected = int(np.argmax(scores))
            local_indices.append(point_index)
            local_cells.append(int(links[selected]))
            local_scores.append(float(scores[selected]))

    if local_indices:
        local_points = points_nm[np.asarray(local_indices, dtype=np.int32)]
        local_values = np.asarray(
            function.eval(local_points, np.asarray(local_cells, dtype=np.int32)),
            dtype=np.complex128,
        )
        if local_values.ndim == 1:
            local_values = local_values.reshape((len(local_points), -1))
    else:
        local_values = np.zeros((0, 0), dtype=np.complex128)

    packets = comm.allgather((local_indices, local_scores, local_values))
    width = next((int(values.shape[1]) for _, _, values in packets if values.size), 0)
    if width < 3:
        raise RuntimeError("No rank returned a three-component value for the reference samples.")

    values = np.zeros((len(points_nm), width), dtype=np.complex128)
    filled = np.zeros(len(points_nm), dtype=bool)
    best_scores = np.full(len(points_nm), -np.inf, dtype=np.float64)
    for indices, scores, packet_values in packets:
        for row, point_index in enumerate(indices):
            if not filled[point_index] or scores[row] > best_scores[point_index]:
                values[point_index] = packet_values[row]
                filled[point_index] = True
                best_scores[point_index] = scores[row]
    if not np.all(filled):
        missing = np.flatnonzero(~filled)
        raise RuntimeError(
            f"No mesh cell found for {len(missing)} full-3D reference sample points; "
            f"first missing point={points_nm[int(missing[0])].tolist()}."
        )
    return values[:, :3]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export_full3d_reference_samples(
    cfg: SimulationConfig3D,
    electric_field,
    magnetic_field_A_per_m,
    out_dir: Path,
) -> dict[str, object]:
    """Write small structured complex E/H samples for Hybrid validation.

    The sampled arrays are intentionally bounded and are not a replacement for
    the distributed VTU volume field.  Every rank reconstructs the same small
    sample array; only rank 0 writes the archive and lightweight metadata.
    """

    x_nm, y_nm, plane_z_nm, points_nm = periodic_plane_sample_grid(cfg)
    points_per_plane = len(x_nm) * len(y_nm)
    z_sides = reference_plane_sides(len(plane_z_nm), points_per_plane)
    shape = (len(plane_z_nm), len(y_nm), len(x_nm), 3)
    replicated_bytes = int(np.prod(shape)) * np.dtype(np.complex128).itemsize * 2
    if replicated_bytes > MAX_REPLICATED_SAMPLE_BYTES:
        raise ValueError(
            "Full-3D reference sample request exceeds the 64 MiB replicated-data guard: "
            f"requested {replicated_bytes} bytes."
        )

    electric = _sample_distributed_function(electric_field, points_nm, z_sides).reshape(shape)
    electric *= cfg.electric_field_scale_V_per_m
    magnetic = _sample_distributed_function(
        magnetic_field_A_per_m,
        points_nm,
        z_sides,
    ).reshape(shape)

    comm = electric_field.function_space.mesh.comm
    npz_path = out_dir / "full3d_reference_samples.npz"
    json_path = out_dir / "full3d_reference_samples.json"
    metadata: dict[str, object] | None = None
    if comm.rank == 0:
        np.savez_compressed(
            npz_path,
            x_nm=x_nm,
            y_nm=y_nm,
            z_nm=plane_z_nm,
            E_V_per_m=electric,
            H_A_per_m=magnetic,
            interface_z_nm=plane_z_nm[[0, -1]],
            E_t_interface_V_per_m=electric[[0, -1], ..., :2],
            H_t_interface_A_per_m=magnetic[[0, -1], ..., :2],
        )
        plane_metrics = []
        for plane_index, z_nm in enumerate(plane_z_nm):
            e_plane = electric[plane_index]
            h_plane = magnetic[plane_index]
            plane_metrics.append(
                {
                    "z_nm": float(z_nm),
                    "max_abs_E_V_per_m": float(np.max(np.linalg.norm(e_plane, axis=-1))),
                    "max_abs_H_A_per_m": float(np.max(np.linalg.norm(h_plane, axis=-1))),
                    "max_abs_E_t_V_per_m": float(np.max(np.linalg.norm(e_plane[..., :2], axis=-1))),
                    "max_abs_H_t_A_per_m": float(np.max(np.linalg.norm(h_plane[..., :2], axis=-1))),
                }
            )
        metadata = {
            "schema_version": REFERENCE_SCHEMA_VERSION,
            "archive": npz_path.name,
            "archive_sha256": _sha256(npz_path),
            "archive_bytes": npz_path.stat().st_size,
            "array_shape_z_y_x_component": list(shape),
            "point_count": len(points_nm),
            "replicated_payload_bytes_uncompressed": replicated_bytes,
            "grid_convention": "periodic-cell-centered-x-y; exact-requested-z",
            "interface_plane_indices": [0, len(plane_z_nm) - 1],
            "interface_trace_sides": ["positive_z", "negative_z"],
            "interface_trace_region": "inside_middle_modal_region",
            "middle_plane_indices": list(range(1, len(plane_z_nm) - 1)),
            "components": ["x", "y", "z"],
            "tangential_components": ["x", "y"],
            "electric_field_unit": "V/m",
            "magnetic_field_unit": "A/m",
            "plane_metrics": plane_metrics,
        }
        json_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    metadata = comm.bcast(metadata, root=0)
    assert metadata is not None
    return {
        "full3d_reference_exported": True,
        "full3d_reference_archive": str(npz_path),
        "full3d_reference_metadata": str(json_path),
        "full3d_reference_archive_sha256": metadata["archive_sha256"],
        "full3d_reference_archive_bytes": metadata["archive_bytes"],
        "full3d_reference_array_shape": metadata["array_shape_z_y_x_component"],
        "full3d_reference_plane_z_nm": plane_z_nm.tolist(),
        "full3d_reference_point_count": metadata["point_count"],
        "full3d_reference_replicated_payload_bytes": replicated_bytes,
    }
