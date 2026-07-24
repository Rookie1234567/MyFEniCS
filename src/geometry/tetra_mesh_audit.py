"""Partition-independent geometry audits for Task035 research meshes."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from typing import Any, Iterable

import numpy as np
from mpi4py import MPI

from dolfinx import mesh


@dataclass(frozen=True)
class OwnedCellGeometry:
    """Canonical geometry and ownership identity for one owned affine cell."""

    local_index: int
    global_index: int
    key: tuple[tuple[int, int, int], ...]
    coordinates: np.ndarray


@dataclass(frozen=True)
class OwnedTetraCellGeometry:
    """Canonical geometry and ownership identity for one owned tetrahedron."""

    local_index: int
    global_index: int
    key: tuple[tuple[int, int, int], ...]
    coordinates: np.ndarray


def mesh_coordinate_tolerance(msh: mesh.Mesh) -> float:
    """Return a deterministic tolerance for coordinate hashing and matching."""

    coordinates = np.asarray(msh.geometry.x, dtype=np.float64)
    if len(coordinates):
        local_minimum = np.min(coordinates, axis=0)
        local_maximum = np.max(coordinates, axis=0)
    else:
        local_minimum = np.full(3, math.inf)
        local_maximum = np.full(3, -math.inf)
    minimum = np.empty(3, dtype=np.float64)
    maximum = np.empty(3, dtype=np.float64)
    msh.comm.Allreduce(local_minimum, minimum, op=MPI.MIN)
    msh.comm.Allreduce(local_maximum, maximum, op=MPI.MAX)
    return 1.0e-10 * max(float(np.max(maximum - minimum)), 1.0)


def canonical_point_key(point: np.ndarray, tolerance: float) -> tuple[int, int, int]:
    """Quantize one three-dimensional point for stable exact-key comparisons."""

    if tolerance <= 0.0:
        raise ValueError("coordinate tolerance must be positive")
    quantized = np.rint(np.asarray(point, dtype=np.float64) / tolerance).astype(
        np.int64
    )
    return tuple(int(value) for value in quantized)


def canonical_entity_key(
    coordinates: np.ndarray,
    tolerance: float,
) -> tuple[tuple[int, int, int], ...]:
    """Return an orientation-independent coordinate key for one mesh entity."""

    return tuple(
        sorted(canonical_point_key(point, tolerance) for point in coordinates)
    )


def owned_tetra_cell_geometry(
    msh: mesh.Mesh,
    *,
    tolerance: float | None = None,
) -> list[OwnedTetraCellGeometry]:
    """Describe all owned cells without relying on partition-local numbering."""

    if msh.topology.cell_type != mesh.CellType.tetrahedron:
        raise ValueError("tetra geometry audit requires a tetrahedron mesh")
    resolved_tolerance = (
        mesh_coordinate_tolerance(msh) if tolerance is None else float(tolerance)
    )
    tdim = msh.topology.dim
    index_map = msh.topology.index_map(tdim)
    local_indices = np.arange(index_map.size_local, dtype=np.int32)
    global_indices = index_map.local_to_global(local_indices)
    records: list[OwnedTetraCellGeometry] = []
    for local_index, global_index in zip(
        local_indices, global_indices, strict=True
    ):
        geometry_indices = msh.geometry.dofmap[int(local_index)]
        coordinates = np.asarray(
            msh.geometry.x[geometry_indices][:4], dtype=np.float64
        ).copy()
        if coordinates.shape != (4, 3):
            raise RuntimeError("tetrahedron must have four affine geometry vertices")
        records.append(
            OwnedTetraCellGeometry(
                local_index=int(local_index),
                global_index=int(global_index),
                key=canonical_entity_key(coordinates, resolved_tolerance),
                coordinates=coordinates,
            )
        )
    return records


def owned_cell_geometry(
    msh: mesh.Mesh,
    *,
    tolerance: float | None = None,
) -> list[OwnedCellGeometry]:
    """Describe owned tetrahedra or hexahedra by canonical vertex geometry."""

    vertex_count_by_type = {
        mesh.CellType.tetrahedron: 4,
        mesh.CellType.hexahedron: 8,
    }
    vertex_count = vertex_count_by_type.get(msh.topology.cell_type)
    if vertex_count is None:
        raise ValueError(
            "generic cell geometry audit supports tetrahedron and hexahedron meshes"
        )
    resolved_tolerance = (
        mesh_coordinate_tolerance(msh) if tolerance is None else float(tolerance)
    )
    tdim = msh.topology.dim
    index_map = msh.topology.index_map(tdim)
    local_indices = np.arange(index_map.size_local, dtype=np.int32)
    global_indices = index_map.local_to_global(local_indices)
    records: list[OwnedCellGeometry] = []
    for local_index, global_index in zip(
        local_indices, global_indices, strict=True
    ):
        geometry_indices = msh.geometry.dofmap[int(local_index)]
        coordinates = np.asarray(
            msh.geometry.x[geometry_indices][:vertex_count],
            dtype=np.float64,
        ).copy()
        if coordinates.shape != (vertex_count, 3):
            raise RuntimeError(
                f"{msh.topology.cell_type.name} must expose {vertex_count} "
                "three-dimensional geometry vertices"
            )
        records.append(
            OwnedCellGeometry(
                local_index=int(local_index),
                global_index=int(global_index),
                key=canonical_entity_key(coordinates, resolved_tolerance),
                coordinates=coordinates,
            )
        )
    return records


def canonical_owned_cell_ids(
    msh: mesh.Mesh,
    *,
    tolerance: float | None = None,
) -> tuple[np.ndarray, list[OwnedCellGeometry], list[tuple[tuple[int, int, int], ...]]]:
    """Return partition-independent IDs aligned with locally owned cells."""

    records = owned_cell_geometry(msh, tolerance=tolerance)
    local_keys = [record.key for record in records]
    ordered_keys = sorted(
        key for packet in msh.comm.allgather(local_keys) for key in packet
    )
    if len(set(ordered_keys)) != len(ordered_keys):
        raise RuntimeError("canonical cell geometry is not globally unique")
    canonical_id_by_key = {
        key: index for index, key in enumerate(ordered_keys)
    }
    canonical_ids = np.asarray(
        [canonical_id_by_key[key] for key in local_keys],
        dtype=np.int64,
    )
    return canonical_ids, records, ordered_keys


def geometry_key_sha256(
    keys: Iterable[tuple[tuple[int, int, int], ...]],
) -> str:
    """Hash fixed-size canonical entity keys in lexicographic order."""

    ordered = sorted(keys)
    digest = hashlib.sha256()
    for key in ordered:
        digest.update(np.asarray(key, dtype="<i8").tobytes())
    return digest.hexdigest()


def _tagged_rows_sha256(rows: Iterable[tuple[int, ...]]) -> str:
    digest = hashlib.sha256()
    for row in sorted(rows):
        digest.update(np.asarray(row, dtype="<i8").tobytes())
    return digest.hexdigest()


def _quality(coordinates: np.ndarray, determinant: float) -> float:
    lengths = [
        float(np.linalg.norm(coordinates[j] - coordinates[i]))
        for i in range(4)
        for j in range(i + 1, 4)
    ]
    longest = max(lengths)
    if longest <= 0.0:
        return 0.0
    volume = abs(determinant) / 6.0
    return float(6.0 * math.sqrt(2.0) * volume / longest**3)


def _flatten_key(key: tuple[tuple[int, int, int], ...]) -> tuple[int, ...]:
    return tuple(component for point in key for component in point)


def _collect_unique(
    comm: MPI.Intracomm,
    local_rows: list[tuple[int, ...]],
    *,
    label: str,
) -> list[tuple[int, ...]]:
    packets = comm.gather(local_rows, root=0)
    result: list[tuple[int, ...]] | None = None
    error: str | None = None
    if comm.rank == 0:
        assert packets is not None
        combined = [row for packet in packets for row in packet]
        result = sorted(set(combined))
        if len(result) != len(combined):
            error = f"duplicate owned {label} geometry keys detected"
    error = comm.bcast(error, root=0)
    if error is not None:
        raise RuntimeError(error)
    return comm.bcast(result, root=0)


def _global_quantiles(
    comm: MPI.Intracomm,
    local_values: list[float],
) -> dict[str, float]:
    packets = comm.gather(local_values, root=0)
    result: dict[str, float] | None = None
    if comm.rank == 0:
        assert packets is not None
        values = np.asarray(
            [value for packet in packets for value in packet], dtype=np.float64
        )
        if not len(values):
            result = {name: math.nan for name in ("minimum", "q05", "median", "q95", "maximum")}
        else:
            result = {
                "minimum": float(np.min(values)),
                "q05": float(np.quantile(values, 0.05)),
                "median": float(np.median(values)),
                "q95": float(np.quantile(values, 0.95)),
                "maximum": float(np.max(values)),
            }
    return comm.bcast(result, root=0)


def _owned_cell_tag_rows(
    msh: mesh.Mesh,
    cell_tags: mesh.MeshTags,
    records: list[OwnedTetraCellGeometry],
) -> tuple[list[tuple[int, ...]], dict[int, int]]:
    tag_by_cell = {
        int(index): int(value)
        for index, value in zip(cell_tags.indices, cell_tags.values, strict=True)
    }
    rows: list[tuple[int, ...]] = []
    counts: dict[int, int] = {}
    for record in records:
        if record.local_index not in tag_by_cell:
            raise RuntimeError("owned tetra cell is missing its material tag")
        value = tag_by_cell[record.local_index]
        rows.append((value, *_flatten_key(record.key)))
        counts[value] = counts.get(value, 0) + 1
    return rows, counts


def _facet_tag_rows(
    msh: mesh.Mesh,
    facet_tags: mesh.MeshTags,
    tolerance: float,
) -> list[tuple[int, ...]]:
    fdim = msh.topology.dim - 1
    facet_indices = np.asarray(facet_tags.indices, dtype=np.int32)
    geometry = mesh.entities_to_geometry(msh, fdim, facet_indices, False)
    rows: list[tuple[int, ...]] = []
    for value, indices in zip(facet_tags.values, geometry, strict=True):
        key = canonical_entity_key(msh.geometry.x[indices], tolerance)
        rows.append((int(value), *_flatten_key(key)))
    return rows


def _periodic_face_report(
    facet_rows: list[tuple[int, ...]],
    *,
    minimum_tag: int,
    maximum_tag: int,
    axis: int,
    period_quantized: int,
) -> dict[str, Any]:
    def normalized(tag: int) -> set[tuple[int, ...]]:
        result: set[tuple[int, ...]] = set()
        for row in facet_rows:
            if row[0] != tag:
                continue
            points = np.asarray(row[1:], dtype=np.int64).reshape(-1, 3)
            if tag == maximum_tag:
                points[:, axis] -= period_quantized
            result.add(_flatten_key(tuple(tuple(int(v) for v in p) for p in points)))
        return result

    minimum = normalized(minimum_tag)
    maximum = normalized(maximum_tag)
    missing_at_maximum = sorted(minimum - maximum)
    missing_at_minimum = sorted(maximum - minimum)
    return {
        "minimum_face_count": len(minimum),
        "maximum_face_count": len(maximum),
        "missing_at_maximum_count": len(missing_at_maximum),
        "missing_at_minimum_count": len(missing_at_minimum),
        "normalized_face_set_sha256": _tagged_rows_sha256(minimum),
        "pass": not missing_at_maximum and not missing_at_minimum,
    }


def audit_periodic_tetra_mesh(
    msh: mesh.Mesh,
    cell_tags: mesh.MeshTags,
    facet_tags: mesh.MeshTags,
    cfg: Any,
) -> dict[str, Any]:
    """Audit orientation, shape, tags, hashes, and periodic boundary closure."""

    comm = msh.comm
    tolerance = mesh_coordinate_tolerance(msh)
    records = owned_tetra_cell_geometry(msh, tolerance=tolerance)
    determinants: list[float] = []
    qualities: list[float] = []
    volumes: list[float] = []
    nonpositive_local = 0
    for record in records:
        coordinates = record.coordinates
        determinant = float(
            np.linalg.det(
                np.column_stack(
                    (
                        coordinates[1] - coordinates[0],
                        coordinates[2] - coordinates[0],
                        coordinates[3] - coordinates[0],
                    )
                )
            )
        )
        determinants.append(determinant)
        volumes.append(determinant / 6.0)
        qualities.append(_quality(coordinates, determinant))
        nonpositive_local += determinant <= 0.0

    cell_keys = _collect_unique(
        comm,
        [_flatten_key(record.key) for record in records],
        label="cell",
    )
    local_cell_tag_rows, local_cell_tag_counts = _owned_cell_tag_rows(
        msh, cell_tags, records
    )
    cell_tag_packets = comm.gather(local_cell_tag_rows, root=0)
    cell_tag_rows: list[tuple[int, ...]] | None = None
    if comm.rank == 0:
        assert cell_tag_packets is not None
        cell_tag_rows = [row for packet in cell_tag_packets for row in packet]
    cell_tag_rows = comm.bcast(cell_tag_rows, root=0)

    facet_rows = _facet_tag_rows(msh, facet_tags, tolerance)
    facet_packets = comm.gather(facet_rows, root=0)
    global_facet_rows: list[tuple[int, ...]] | None = None
    if comm.rank == 0:
        assert facet_packets is not None
        global_facet_rows = sorted(
            set(row for packet in facet_packets for row in packet)
        )
    global_facet_rows = comm.bcast(global_facet_rows, root=0)

    count_packets = comm.allgather(local_cell_tag_counts)
    cell_tag_counts: dict[str, int] = {}
    for packet in count_packets:
        for tag, count in packet.items():
            name = str(tag)
            cell_tag_counts[name] = cell_tag_counts.get(name, 0) + count
    facet_tag_counts: dict[str, int] = {}
    for row in global_facet_rows:
        name = str(row[0])
        facet_tag_counts[name] = facet_tag_counts.get(name, 0) + 1

    period_x_quantized = int(round((cfg.x_max - cfg.x_min) / tolerance))
    period_y_quantized = int(round((cfg.y_max - cfg.y_min) / tolerance))
    periodic_x = _periodic_face_report(
        global_facet_rows,
        minimum_tag=int(cfg.tags.x_min),
        maximum_tag=int(cfg.tags.x_max),
        axis=0,
        period_quantized=period_x_quantized,
    )
    periodic_y = _periodic_face_report(
        global_facet_rows,
        minimum_tag=int(cfg.tags.y_min),
        maximum_tag=int(cfg.tags.y_max),
        axis=1,
        period_quantized=period_y_quantized,
    )
    nonpositive = int(comm.allreduce(nonpositive_local, op=MPI.SUM))
    orientation_quantiles = _global_quantiles(comm, determinants)
    quality_quantiles = _global_quantiles(comm, qualities)
    volume_quantiles = _global_quantiles(comm, volumes)
    finite = all(
        math.isfinite(value)
        for group in (orientation_quantiles, quality_quantiles, volume_quantiles)
        for value in group.values()
    )
    passed = (
        finite
        and nonpositive == 0
        and orientation_quantiles["minimum"] > 0.0
        and quality_quantiles["minimum"] > 0.0
        and periodic_x["pass"]
        and periodic_y["pass"]
    )
    return {
        "schema_version": "task035.periodic-tetra-mesh-audit.v1",
        "status": "pass" if passed else "fail",
        "mpi_size": comm.size,
        "coordinate_tolerance": tolerance,
        "global_cell_count": len(cell_keys),
        "partition_independent_mesh_sha256": _tagged_rows_sha256(cell_keys),
        "cell_tag_sha256": _tagged_rows_sha256(cell_tag_rows),
        "facet_tag_sha256": _tagged_rows_sha256(global_facet_rows),
        "cell_tag_counts": cell_tag_counts,
        "facet_tag_counts": facet_tag_counts,
        "orientation": {
            "nonpositive_count": nonpositive,
            "determinant_quantiles": orientation_quantiles,
            "signed_volume_quantiles": volume_quantiles,
        },
        "shape_quality": {
            "definition": "6*sqrt(2)*abs(volume)/maximum_edge_length^3",
            "quantiles": quality_quantiles,
        },
        "periodic_x": periodic_x,
        "periodic_y": periodic_y,
        "pass": passed,
    }


__all__ = [
    "OwnedCellGeometry",
    "OwnedTetraCellGeometry",
    "audit_periodic_tetra_mesh",
    "canonical_owned_cell_ids",
    "canonical_entity_key",
    "canonical_point_key",
    "geometry_key_sha256",
    "mesh_coordinate_tolerance",
    "owned_cell_geometry",
    "owned_tetra_cell_geometry",
]
