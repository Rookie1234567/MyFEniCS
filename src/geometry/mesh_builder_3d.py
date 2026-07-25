from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import ufl
from basix.ufl import element
from mpi4py import MPI

from dolfinx import default_real_type, graph, io, mesh

from ..common.config_3d import SimulationConfig3D


@dataclass
class AirBox3DMesh:
    mesh: mesh.Mesh
    cell_tags: mesh.MeshTags
    facet_tags: mesh.MeshTags
    boundary_facets: np.ndarray
    mesh_cell_type_resolved: str
    mesh_cells_resolved: tuple[int, int, int]
    z_alignment_warnings: list[str]
    mesh_spacing_mode_resolved: str
    mesh_axis_cell_stats: dict[str, dict[str, float | int]]
    material_plane_alignment: dict[str, object]
    local_refinement_regions: dict[str, list[list[float]]]


@dataclass(frozen=True)
class HexaAxisPlan:
    x_values: np.ndarray
    y_values: np.ndarray
    z_values: np.ndarray
    mesh_spacing_mode_resolved: str
    axis_cell_stats: dict[str, dict[str, float | int]]
    material_plane_alignment: dict[str, object]
    local_refinement_regions: dict[str, list[list[float]]]

    @property
    def mesh_cells_resolved(self) -> tuple[int, int, int]:
        return (len(self.x_values) - 1, len(self.y_values) - 1, len(self.z_values) - 1)


def _mark_boundary_facets(msh: mesh.Mesh, cfg: SimulationConfig3D) -> tuple[mesh.MeshTags, np.ndarray]:
    """Tag the six exterior box faces used by Dirichlet and Floquet logic."""
    fdim = msh.topology.dim - 1
    markers = (
        (cfg.tags.x_min, lambda x: np.isclose(x[0], cfg.x_min)),
        (cfg.tags.x_max, lambda x: np.isclose(x[0], cfg.x_max)),
        (cfg.tags.y_min, lambda x: np.isclose(x[1], cfg.y_min)),
        (cfg.tags.y_max, lambda x: np.isclose(x[1], cfg.y_max)),
        (cfg.tags.z_min, lambda x: np.isclose(x[2], cfg.domain_z_min)),
        (cfg.tags.z_max, lambda x: np.isclose(x[2], cfg.domain_z_max)),
    )
    facet_indices: list[np.ndarray] = []
    facet_values: list[np.ndarray] = []
    for tag, marker in markers:
        facets = mesh.locate_entities_boundary(msh, fdim, marker)
        facet_indices.append(facets)
        facet_values.append(np.full(len(facets), tag, dtype=np.int32))

    if facet_indices:
        indices = np.concatenate(facet_indices).astype(np.int32)
        values = np.concatenate(facet_values).astype(np.int32)
        order = np.argsort(indices)
        indices = indices[order]
        values = values[order]
    else:
        indices = np.asarray([], dtype=np.int32)
        values = np.asarray([], dtype=np.int32)

    return mesh.meshtags(msh, fdim, indices, values), np.unique(indices)


def _mark_cells(msh: mesh.Mesh, cfg: SimulationConfig3D) -> mesh.MeshTags:
    """Tag air, substrate, grating, top PML, and bottom PML cells by midpoint."""
    tdim = msh.topology.dim
    index_map = msh.topology.index_map(tdim)
    # MeshTags used in UFL measures must describe owned integration entities.
    # Including ghost cells can make material/PML terms depend on the MPI
    # partition, even when the geometric tags look correct in aggregate.
    num_cells = index_map.size_local
    cells = np.arange(num_cells, dtype=np.int32)
    midpoints = mesh.compute_midpoints(msh, tdim, cells)

    values = np.full(num_cells, cfg.tags.air, dtype=np.int32)
    z = midpoints[:, 2]
    tol = 1.0e-10 * max(abs(cfg.domain_z_max - cfg.domain_z_min), 1.0)

    if cfg.use_pml and cfg.pml_bottom_thickness > 0.0:
        values[z < cfg.physical_z_min - tol] = cfg.tags.bottom_pml
    if cfg.use_pml and cfg.pml_top_thickness > 0.0:
        values[z > cfg.physical_z_max + tol] = cfg.tags.top_pml
    if cfg.geometry_kind in {"fresnel_interface", "rectangular_block_grating"}:
        physical = (z >= cfg.physical_z_min - tol) & (z <= cfg.physical_z_max + tol)
        values[physical & (z < cfg.interface_z)] = cfg.tags.substrate
    if cfg.geometry_kind == "rectangular_block_grating" and cfg.has_grating_block:
        x = midpoints[:, 0]
        y = midpoints[:, 1]
        physical = (z >= cfg.physical_z_min - tol) & (z <= cfg.physical_z_max + tol)
        in_block = (
            physical
            & (x >= cfg.grating_x_min - tol)
            & (x <= cfg.grating_x_max + tol)
            & (y >= cfg.grating_y_min - tol)
            & (y <= cfg.grating_y_max + tol)
            & (z >= cfg.grating_z_min - tol)
            & (z <= cfg.grating_z_max + tol)
        )
        values[in_block] = cfg.tags.grating

    return mesh.meshtags(msh, tdim, cells, values)


def _axis_coordinates(start: float, stop: float, target_size: float, required: tuple[float, ...] = ()) -> np.ndarray:
    """Return sorted coordinates that include required material/PML planes."""
    length = stop - start
    num_cells = max(1, int(np.ceil(length / target_size)))
    base = np.linspace(start, stop, num_cells + 1)
    values = [float(value) for value in base]
    tol = 1.0e-10 * max(abs(length), 1.0)
    for value in required:
        if start + tol < value < stop - tol:
            values.append(float(value))
    values = sorted(values)
    unique = [values[0]]
    for value in values[1:]:
        if abs(value - unique[-1]) > tol:
            unique.append(value)
    return np.asarray(unique, dtype=np.float64)


def _axis_tolerance(start: float, stop: float) -> float:
    return 1.0e-10 * max(abs(stop - start), 1.0)


def _deduplicate_sorted(values: list[float], tol: float) -> list[float]:
    if not values:
        return []
    ordered = sorted(float(value) for value in values)
    unique = [ordered[0]]
    for value in ordered[1:]:
        if abs(value - unique[-1]) > tol:
            unique.append(value)
    return unique


def _clip_interval(start: float, stop: float, low: float, high: float, tol: float) -> tuple[float, float] | None:
    clipped_low = max(start, low)
    clipped_high = min(stop, high)
    if clipped_high - clipped_low <= tol:
        return None
    return (float(clipped_low), float(clipped_high))


def _stage4_required_planes_by_axis(cfg: SimulationConfig3D) -> dict[str, list[tuple[str, float]]]:
    """Return material/interface planes that must become true hexa grid planes."""

    planes: dict[str, list[tuple[str, float]]] = {"x": [], "y": [], "z": _required_z_planes(cfg)}
    if cfg.geometry_kind == "rectangular_block_grating" and cfg.has_grating_block:
        planes["x"].extend(
            [("grating_x_min", cfg.grating_x_min), ("grating_x_max", cfg.grating_x_max)]
        )
        planes["y"].extend(
            [("grating_y_min", cfg.grating_y_min), ("grating_y_max", cfg.grating_y_max)]
        )
        planes["z"].append(("grating_z_min", cfg.grating_z_min))
    return planes


def _axis_stats(values: np.ndarray) -> dict[str, float | int]:
    widths = np.diff(values)
    if len(widths) == 0:
        return {"num_cells": 0, "min": 0.0, "max": 0.0, "median": 0.0}
    return {
        "num_cells": int(len(widths)),
        "min": float(np.min(widths)),
        "max": float(np.max(widths)),
        "median": float(np.median(widths)),
    }


def _axis_contains(values: np.ndarray, value: float, tol: float) -> bool:
    return bool(np.any(np.isclose(values, value, atol=tol, rtol=0.0)))


def _material_plane_alignment_report(
    cfg: SimulationConfig3D,
    axis_values: dict[str, np.ndarray],
) -> dict[str, object]:
    """Check that Stage-4 material planes are represented as mesh coordinate planes."""

    required = _stage4_required_planes_by_axis(cfg)
    missing: list[str] = []
    checked: dict[str, list[dict[str, object]]] = {"x": [], "y": [], "z": []}
    spans = {
        "x": (cfg.x_min, cfg.x_max),
        "y": (cfg.y_min, cfg.y_max),
        "z": (cfg.domain_z_min, cfg.domain_z_max),
    }
    for axis_name, planes in required.items():
        tol = _axis_tolerance(*spans[axis_name])
        values = axis_values[axis_name]
        for name, value in planes:
            aligned = _axis_contains(values, value, tol)
            checked[axis_name].append({"name": name, "value": float(value), "aligned": bool(aligned)})
            if not aligned:
                missing.append(f"{name}={value:g} nm is not on the generated {axis_name}-grid.")
    return {
        "all_aligned": len(missing) == 0,
        "missing": missing,
        "checked": checked,
    }


def _subdivide_piecewise_axis(
    start: float,
    stop: float,
    breakpoints: list[float],
    target_size_by_interval,
    min_cells: int = 1,
) -> np.ndarray:
    """Create a nonuniform axis from exact breakpoints and interval target sizes."""

    if target_size_by_interval is None:
        raise ValueError("target_size_by_interval must be callable.")
    if stop <= start:
        raise ValueError("Axis stop must be greater than start.")
    tol = _axis_tolerance(start, stop)
    points = _deduplicate_sorted([start, stop, *breakpoints], tol)
    if abs(points[0] - start) > tol or abs(points[-1] - stop) > tol:
        raise ValueError("Axis breakpoints must stay inside the domain bounds.")

    axis: list[float] = [float(start)]
    for low, high in zip(points[:-1], points[1:]):
        length = high - low
        if length <= tol:
            continue
        target = float(target_size_by_interval(0.5 * (low + high)))
        if target <= 0.0:
            raise ValueError("Mesh target sizes must be positive.")
        num = max(1, int(np.ceil(length / target)))
        segment = np.linspace(low, high, num + 1, dtype=np.float64)
        axis.extend(float(value) for value in segment[1:])

    while len(axis) - 1 < min_cells:
        widths = np.diff(np.asarray(axis, dtype=np.float64))
        split_index = int(np.argmax(widths))
        midpoint = 0.5 * (axis[split_index] + axis[split_index + 1])
        axis.insert(split_index + 1, float(midpoint))
    return np.asarray(axis, dtype=np.float64)


def _subdivide_piecewise_axis_exact_count(
    start: float,
    stop: float,
    breakpoints: list[float],
    *,
    num_cells: int,
) -> np.ndarray:
    """Fit required planes while producing exactly ``num_cells`` intervals."""

    if stop <= start:
        raise ValueError("Axis stop must be greater than start.")
    if isinstance(num_cells, bool) or not isinstance(
        num_cells, (int, np.integer)
    ):
        raise ValueError("Exact axis cell count must be an integer.")
    num_cells = int(num_cells)
    tol = _axis_tolerance(start, stop)
    points = _deduplicate_sorted([start, stop, *breakpoints], tol)
    if abs(points[0] - start) > tol or abs(points[-1] - stop) > tol:
        raise ValueError("Axis breakpoints must stay inside the domain bounds.")
    interval_lengths = np.diff(np.asarray(points, dtype=np.float64))
    if np.any(interval_lengths <= tol):
        raise ValueError("Exact axis authority contains a degenerate interval.")
    if num_cells < len(interval_lengths):
        raise ValueError(
            "Exact axis cell count cannot place at least one cell in every "
            "material interval."
        )

    quotas = (
        float(num_cells)
        * interval_lengths
        / float(np.sum(interval_lengths))
    )
    allocations = np.maximum(
        1,
        np.floor(quotas).astype(np.int64),
    )
    while int(np.sum(allocations)) < num_cells:
        deficits = quotas - allocations
        index = int(np.argmax(deficits))
        allocations[index] += 1
    while int(np.sum(allocations)) > num_cells:
        removable = allocations > 1
        if not np.any(removable):
            raise RuntimeError(
                "Exact axis interval allocation cannot satisfy its count."
            )
        excess = allocations.astype(np.float64) - quotas
        excess[~removable] = -np.inf
        index = int(np.argmax(excess))
        allocations[index] -= 1

    axis: list[float] = [float(start)]
    for low, high, count in zip(
        points[:-1],
        points[1:],
        allocations,
        strict=True,
    ):
        segment = np.linspace(
            low,
            high,
            int(count) + 1,
            dtype=np.float64,
        )
        axis.extend(float(value) for value in segment[1:])
    values = np.asarray(axis, dtype=np.float64)
    if len(values) - 1 != num_cells:
        raise RuntimeError("Exact axis generator produced the wrong count.")
    return values


def _uniform_axis(start: float, stop: float, num_cells: int) -> np.ndarray:
    return np.linspace(start, stop, num_cells + 1, dtype=np.float64)


def _uniform_axes(cfg: SimulationConfig3D, mesh_cells_resolved: tuple[int, int, int]) -> dict[str, np.ndarray]:
    return {
        "x": _uniform_axis(cfg.x_min, cfg.x_max, mesh_cells_resolved[0]),
        "y": _uniform_axis(cfg.y_min, cfg.y_max, mesh_cells_resolved[1]),
        "z": _uniform_axis(cfg.domain_z_min, cfg.domain_z_max, mesh_cells_resolved[2]),
    }


def _refine_axes_until_enough_cells(
    axes: dict[str, np.ndarray],
    min_total_cells: int,
) -> dict[str, np.ndarray]:
    """Split the largest current interval until there are enough cells for MPI ranks."""

    refined = {axis_name: np.asarray(values, dtype=np.float64).copy() for axis_name, values in axes.items()}
    if min_total_cells <= 1:
        return refined

    def total_cells() -> int:
        return int(np.prod([len(values) - 1 for values in refined.values()]))

    while total_cells() < min_total_cells:
        candidates: list[tuple[float, str, int]] = []
        for axis_name, values in refined.items():
            widths = np.diff(values)
            if len(widths) == 0:
                continue
            split_index = int(np.argmax(widths))
            candidates.append((float(widths[split_index]), axis_name, split_index))
        if not candidates:
            raise RuntimeError("Cannot refine an empty hexa axis plan.")
        _, axis_name, split_index = max(candidates, key=lambda item: item[0])
        values = refined[axis_name]
        midpoint = 0.5 * (values[split_index] + values[split_index + 1])
        refined[axis_name] = np.insert(values, split_index + 1, midpoint)
    return refined


def _stage4_refinement_regions(cfg: SimulationConfig3D) -> dict[str, list[list[float]]]:
    """Return clipped geometry-driven refinement bands for Stage-4 local_refined mode."""

    radius = cfg.mesh_refinement_radius_resolved
    tol_x = _axis_tolerance(cfg.x_min, cfg.x_max)
    tol_y = _axis_tolerance(cfg.y_min, cfg.y_max)
    tol_z = _axis_tolerance(cfg.domain_z_min, cfg.domain_z_max)
    regions: dict[str, list[list[float]]] = {"x": [], "y": [], "z": []}

    if cfg.has_grating_block:
        x_band = _clip_interval(cfg.x_min, cfg.x_max, cfg.grating_x_min - radius, cfg.grating_x_max + radius, tol_x)
        y_band = _clip_interval(cfg.y_min, cfg.y_max, cfg.grating_y_min - radius, cfg.grating_y_max + radius, tol_y)
        z_band = _clip_interval(
            cfg.domain_z_min,
            cfg.domain_z_max,
            min(cfg.interface_z, cfg.grating_z_min) - radius,
            cfg.grating_z_max + radius,
            tol_z,
        )
        if x_band is not None:
            regions["x"].append([x_band[0], x_band[1]])
        if y_band is not None:
            regions["y"].append([y_band[0], y_band[1]])
        if z_band is not None:
            regions["z"].append([z_band[0], z_band[1]])
    else:
        z_band = _clip_interval(
            cfg.domain_z_min,
            cfg.domain_z_max,
            cfg.interface_z - radius,
            cfg.interface_z + radius,
            tol_z,
        )
        if z_band is not None:
            regions["z"].append([z_band[0], z_band[1]])
    return regions


def _interval_in_regions(midpoint: float, regions: list[list[float]]) -> bool:
    return any(low <= midpoint <= high for low, high in regions)


def _stage4_axis_plan(cfg: SimulationConfig3D, comm_size: int) -> HexaAxisPlan:
    """Resolve the Stage-4 hexa spacing mode and build periodic-compatible axes."""

    _validate_stage4_hexa_geometry(cfg)
    explicit_counts = cfg.mesh_axis_cell_counts_requested
    explicit_z_values = cfg.mesh_axis_z_values_requested
    explicit_z_profile = cfg.mesh_axis_z_profile
    if (explicit_z_values is None) != (explicit_z_profile is None):
        raise ValueError(
            "mesh_axis_z_values and mesh_axis_z_profile must be supplied "
            "together."
        )
    if explicit_z_values is not None and explicit_counts is None:
        raise ValueError(
            "mesh_axis_z_values requires mesh_axis_cell_counts so the exact "
            "tensor topology is explicit."
        )
    if explicit_z_profile is not None and not str(explicit_z_profile).strip():
        raise ValueError("mesh_axis_z_profile must be a non-empty identity")
    if explicit_counts is not None:
        if cfg.mesh_cell_type_resolved != "hexahedron":
            raise ValueError(
                "mesh_axis_cell_counts is currently qualified only for "
                "Stage-4 hexahedra."
            )
        if cfg.geometry_kind != "rectangular_block_grating":
            raise ValueError(
                "mesh_axis_cell_counts is currently qualified only for the "
                "fixed rectangular block grating."
            )
        if cfg.mesh_spacing_mode_requested not in {
            "auto",
            "boundary_fitted",
        }:
            raise ValueError(
                "mesh_axis_cell_counts requires mesh_spacing_mode='auto' or "
                "'boundary_fitted'."
            )
        if cfg.use_floquet_xy and (
            explicit_counts[0] < 2 or explicit_counts[1] < 2
        ):
            raise ValueError(
                "Floquet exact-axis plans require at least two x and y cells."
            )
        if int(np.prod(explicit_counts)) < int(comm_size):
            raise ValueError(
                "Exact axis plan has fewer cells than MPI ranks; it will not "
                "be silently refined."
            )
        required = _stage4_required_planes_by_axis(cfg)
        spans = {
            "x": (cfg.x_min, cfg.x_max),
            "y": (cfg.y_min, cfg.y_max),
            "z": (cfg.domain_z_min, cfg.domain_z_max),
        }
        axes = {
            axis_name: _subdivide_piecewise_axis_exact_count(
                start,
                stop,
                [value for _, value in required[axis_name]],
                num_cells=explicit_counts[index],
            )
            for index, (axis_name, (start, stop)) in enumerate(
                spans.items()
            )
        }
        if explicit_z_values is not None:
            if len(explicit_z_values) != explicit_counts[2] + 1:
                raise ValueError(
                    "mesh_axis_z_values length must equal NZ + 1 from "
                    "mesh_axis_cell_counts."
                )
            if not (
                np.isclose(
                    explicit_z_values[0],
                    cfg.domain_z_min,
                    rtol=0.0,
                    atol=1.0e-12,
                )
                and np.isclose(
                    explicit_z_values[-1],
                    cfg.domain_z_max,
                    rtol=0.0,
                    atol=1.0e-12,
                )
            ):
                raise ValueError(
                    "mesh_axis_z_values endpoints must equal the Stage-4 "
                    "domain z bounds."
                )
            axes["z"] = np.asarray(explicit_z_values, dtype=np.float64)
            mode = "boundary_fitted_exact_counts_explicit_z"
        else:
            mode = "boundary_fitted_exact_counts"
        regions: dict[str, list[list[float]]] = {
            "x": [],
            "y": [],
            "z": [],
        }
    else:
        uniform_cells = _hexa_mesh_cells(cfg, comm_size)
        uniform_axes = _uniform_axes(cfg, uniform_cells)
        uniform_alignment = _material_plane_alignment_report(
            cfg,
            uniform_axes,
        )
        requested = cfg.mesh_spacing_mode_requested
        if requested == "auto":
            mode = (
                "uniform_strict"
                if uniform_alignment["all_aligned"]
                else "boundary_fitted"
            )
        else:
            mode = requested

        min_axis_cells = 2 if cfg.use_floquet_xy else 1
        required = _stage4_required_planes_by_axis(cfg)
        if mode == "uniform_strict":
            if not uniform_alignment["all_aligned"]:
                hint = (
                    "Stage-4 uniform_strict hexa meshes require every material boundary to be a grid plane. "
                    "Use mesh_spacing_mode='auto', 'boundary_fitted', or 'local_refined' to generate a fitted nonuniform hexa mesh."
                )
                raise ValueError(hint + " " + " ".join(str(message) for message in uniform_alignment["missing"]))
            axes = uniform_axes
            regions = {"x": [], "y": [], "z": []}
        else:
            spans = {
                "x": (cfg.x_min, cfg.x_max),
                "y": (cfg.y_min, cfg.y_max),
                "z": (cfg.domain_z_min, cfg.domain_z_max),
            }
            regions = _stage4_refinement_regions(cfg) if mode == "local_refined" else {"x": [], "y": [], "z": []}
            refined_size = cfg.mesh_refined_size_resolved
            axes = {}
            for axis_name, (start, stop) in spans.items():
                breakpoints = [value for _, value in required[axis_name]]
                for low, high in regions[axis_name]:
                    breakpoints.extend([low, high])

                def target_size(midpoint: float, *, axis: str = axis_name) -> float:
                    if mode == "local_refined" and _interval_in_regions(midpoint, regions[axis]):
                        return refined_size
                    return float(cfg.mesh_target_size)

                axes[axis_name] = _subdivide_piecewise_axis(
                    start,
                    stop,
                    breakpoints,
                    target_size,
                    min_cells=min_axis_cells,
                )
            axes = _refine_axes_until_enough_cells(axes, comm_size)

    alignment = _material_plane_alignment_report(cfg, axes)
    if not alignment["all_aligned"]:
        raise RuntimeError(
            "Internal Stage-4 hexa axis generation failed to align material planes. "
            + " ".join(str(message) for message in alignment["missing"])
        )
    stats = {axis_name: _axis_stats(values) for axis_name, values in axes.items()}
    return HexaAxisPlan(
        x_values=axes["x"],
        y_values=axes["y"],
        z_values=axes["z"],
        mesh_spacing_mode_resolved=mode,
        axis_cell_stats=stats,
        material_plane_alignment=alignment,
        local_refinement_regions=regions,
    )


def stage4_axis_plan(cfg: SimulationConfig3D, comm_size: int) -> HexaAxisPlan:
    """Return the reviewed Stage-4 tensor axes for matching lower-dimensional meshes.

    The hybrid FEM-modal path must use cross-section cells that are the exact
    x-y faces of the full 3D hexahedral mesh.  This small public wrapper avoids
    duplicating the material-plane fitting policy in the modal package.
    """

    return _stage4_axis_plan(cfg, comm_size)


def _structured_hexa_mesh(
    msh_comm: MPI.Intracomm,
    x_values: np.ndarray,
    y_values: np.ndarray,
    z_values: np.ndarray,
    *,
    preserve_input_partition: bool = False,
) -> mesh.Mesh:
    """Create a tensor-product hexa mesh from explicit nonuniform coordinate axes."""

    nx = len(x_values) - 1
    ny = len(y_values) - 1
    nz = len(z_values) - 1
    points = np.asarray(
        [(x, y, z) for z in z_values for y in y_values for x in x_values],
        dtype=default_real_type,
    )

    def node(i: int, j: int, k: int) -> int:
        return k * len(y_values) * len(x_values) + j * len(x_values) + i

    cell_ids = _rank_cell_ids(nx * ny * nz, msh_comm.rank, msh_comm.size)
    cells = [
        _structured_hexa_cell_vertices(int(cell_id), nx, ny, node)
        for cell_id in cell_ids
    ]
    coordinate_element = element("Lagrange", "hexahedron", 1, shape=(3,), dtype=default_real_type)
    domain = ufl.Mesh(coordinate_element)
    if preserve_input_partition:

        def keep_input_cell_owners(
            _comm,
            num_partitions: int,
            adjacency,
            _ghost_mode: bool,
        ):
            if int(num_partitions) != int(msh_comm.size):
                raise RuntimeError(
                    "input-preserving partitioner received an unexpected "
                    "partition count"
                )
            destinations = np.full(
                (int(adjacency.num_nodes), 1),
                int(msh_comm.rank),
                dtype=np.int32,
            )
            return graph.adjacencylist(destinations)._cpp_object

        partitioner = mesh.create_cell_partitioner(
            keep_input_cell_owners,
            mesh.GhostMode.shared_facet,
        )
    else:
        partitioner = mesh.create_cell_partitioner(
            mesh.GhostMode.shared_facet
        )
    return mesh.create_mesh(msh_comm, np.asarray(cells, dtype=np.int64), domain, points, partitioner=partitioner)


def _rank_cell_ids(total_cells: int, rank: int, size: int) -> range:
    """Return the global tensor-cell ids provided by one MPI rank to create_mesh."""

    if total_cells < 0:
        raise ValueError("total_cells must be non-negative.")
    if size <= 0:
        raise ValueError("MPI size must be positive.")
    start = (total_cells * rank) // size
    stop = (total_cells * (rank + 1)) // size
    return range(start, stop)


def _structured_hexa_cell_vertices(cell_id: int, nx: int, ny: int, node) -> list[int]:
    """Convert a tensor-product cell id into DOLFINx hexa vertex connectivity."""

    cells_per_layer = nx * ny
    k = cell_id // cells_per_layer
    layer_cell = cell_id - k * cells_per_layer
    j = layer_cell // nx
    i = layer_cell - j * nx
    return [
        node(i, j, k),
        node(i + 1, j, k),
        node(i, j + 1, k),
        node(i + 1, j + 1, k),
        node(i, j, k + 1),
        node(i + 1, j, k + 1),
        node(i, j + 1, k + 1),
        node(i + 1, j + 1, k + 1),
    ]


def _structured_tet_mesh_from_axes(
    msh_comm: MPI.Intracomm,
    x_values: np.ndarray,
    y_values: np.ndarray,
    z_values: np.ndarray,
) -> mesh.Mesh:
    """Split matching tensor boxes into periodic-compatible tetrahedra."""

    nx = len(x_values) - 1
    ny = len(y_values) - 1
    nz = len(z_values) - 1
    points = np.asarray(
        [(x, y, z) for z in z_values for y in y_values for x in x_values],
        dtype=default_real_type,
    )

    def node(i: int, j: int, k: int) -> int:
        return k * len(y_values) * len(x_values) + j * len(x_values) + i

    cells: list[list[int]] = []
    cells_per_layer = nx * ny
    for cell_id in _rank_cell_ids(nx * ny * nz, msh_comm.rank, msh_comm.size):
        k = int(cell_id) // cells_per_layer
        layer_cell = int(cell_id) - k * cells_per_layer
        j = layer_cell // nx
        i = layer_cell - j * nx
        v000 = node(i, j, k)
        v100 = node(i + 1, j, k)
        v010 = node(i, j + 1, k)
        v110 = node(i + 1, j + 1, k)
        v001 = node(i, j, k + 1)
        v101 = node(i + 1, j, k + 1)
        v011 = node(i, j + 1, k + 1)
        v111 = node(i + 1, j + 1, k + 1)
        cells.extend(
            [
                [v000, v100, v110, v111],
                [v000, v110, v010, v111],
                [v000, v010, v011, v111],
                [v000, v011, v001, v111],
                [v000, v001, v101, v111],
                [v000, v101, v100, v111],
            ]
        )
    coordinate_element = element(
        "Lagrange",
        "tetrahedron",
        1,
        shape=(3,),
        dtype=default_real_type,
    )
    domain = ufl.Mesh(coordinate_element)
    partitioner = mesh.create_cell_partitioner(mesh.GhostMode.shared_facet)
    return mesh.create_mesh(
        msh_comm,
        np.asarray(cells, dtype=np.int64),
        domain,
        points,
        partitioner=partitioner,
    )


def _structured_tet_mesh(msh_comm: MPI.Intracomm, cfg: SimulationConfig3D) -> mesh.Mesh:
    """Create a structured tet mesh with z breaks at Stage-2 material planes.

    ``mesh.create_box`` only creates uniform axis spacing.  For Fresnel and PML
    validation, the interface and PML entrances must be real cell faces even on
    coarse smoke meshes; otherwise midpoint-based tags smear the manufactured
    reference problem.
    """
    required_z = [cfg.physical_z_min, cfg.physical_z_max]
    if cfg.geometry_kind == "fresnel_interface":
        required_z.append(cfg.interface_z)
    x_values = _axis_coordinates(cfg.x_min, cfg.x_max, cfg.mesh_target_size)
    y_values = _axis_coordinates(cfg.y_min, cfg.y_max, cfg.mesh_target_size)
    z_values = _axis_coordinates(cfg.domain_z_min, cfg.domain_z_max, cfg.mesh_target_size, tuple(required_z))

    nx = len(x_values) - 1
    ny = len(y_values) - 1
    nz = len(z_values) - 1
    points = np.asarray(
        [(x, y, z) for z in z_values for y in y_values for x in x_values],
        dtype=default_real_type,
    )

    def node(i: int, j: int, k: int) -> int:
        return k * len(y_values) * len(x_values) + j * len(x_values) + i

    cells: list[list[int]] = []
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                v000 = node(i, j, k)
                v100 = node(i + 1, j, k)
                v010 = node(i, j + 1, k)
                v110 = node(i + 1, j + 1, k)
                v001 = node(i, j, k + 1)
                v101 = node(i + 1, j, k + 1)
                v011 = node(i, j + 1, k + 1)
                v111 = node(i + 1, j + 1, k + 1)
                cells.extend(
                    [
                        [v000, v100, v110, v111],
                        [v000, v110, v010, v111],
                        [v000, v010, v011, v111],
                        [v000, v011, v001, v111],
                        [v000, v001, v101, v111],
                        [v000, v101, v100, v111],
                    ]
                )
    coordinate_element = element("Lagrange", "tetrahedron", 1, shape=(3,), dtype=default_real_type)
    domain = ufl.Mesh(coordinate_element)
    partitioner = mesh.create_cell_partitioner(mesh.GhostMode.shared_facet)
    return mesh.create_mesh(msh_comm, np.asarray(cells, dtype=np.int64), domain, points, partitioner=partitioner)


def _required_z_planes(cfg: SimulationConfig3D) -> list[tuple[str, float]]:
    planes: list[tuple[str, float]] = []
    if cfg.use_pml:
        planes.append(("physical_z_min", cfg.physical_z_min))
        planes.append(("physical_z_max", cfg.physical_z_max))
    if cfg.geometry_kind in {"fresnel_interface", "rectangular_block_grating"}:
        planes.append(("interface_z", cfg.interface_z))
    if cfg.geometry_kind == "rectangular_block_grating" and cfg.has_grating_block:
        planes.append(("grating_z_max", cfg.grating_z_max))
    return planes


def _hexa_mesh_cells(cfg: SimulationConfig3D, comm_size: int) -> tuple[int, int, int]:
    """Keep periodic hexa smoke meshes from creating empty MPI ranks."""
    cells = [int(value) for value in cfg.mesh_cells]
    if cfg.use_floquet_xy:
        cells[0] = max(cells[0], 2)
        cells[1] = max(cells[1], 2)
        cells[2] = max(cells[2], 2)
    axis = 2
    while cells[0] * cells[1] * cells[2] < comm_size:
        cells[axis] += 1
        axis = (axis + 2) % 3
    return tuple(cells)


def _z_alignment_warnings(cfg: SimulationConfig3D, mesh_cells_resolved: tuple[int, int, int]) -> list[str]:
    """Report when uniform hexahedral z planes do not contain material breaks."""
    if cfg.mesh_cell_type_resolved != "hexahedron":
        return []
    required = _required_z_planes(cfg)
    if not required:
        return []
    z_grid = np.linspace(cfg.domain_z_min, cfg.domain_z_max, mesh_cells_resolved[2] + 1)
    tol = 1.0e-10 * max(abs(cfg.domain_z_max - cfg.domain_z_min), 1.0)
    warnings: list[str] = []
    for name, value in required:
        if not np.any(np.isclose(z_grid, value, atol=tol, rtol=0.0)):
            warnings.append(
                f"{name}={value:g} nm is not on a hexahedral z grid plane for "
                f"mesh_target_size={cfg.mesh_target_size:g} nm; cell tags use midpoint classification."
            )
    return warnings


def _grid_contains(grid: np.ndarray, value: float, tol: float) -> bool:
    return bool(np.any(np.isclose(grid, value, atol=tol, rtol=0.0)))


def _validate_stage4_hexa_geometry(cfg: SimulationConfig3D) -> None:
    """Validate Stage-4 assumptions before building fitted tensor axes."""
    if cfg.geometry_kind != "rectangular_block_grating":
        return
    if cfg.mesh_cell_type_resolved not in {"hexahedron", "tetrahedron"}:
        raise ValueError(
            "stage4_block_grating requires a tetrahedron or hexahedron mesh."
        )
    degree = int(cfg.nedelec_degree)
    task035_fixed_target_high_order = (
        cfg.stage_case == "stage4_block_grating" and degree in {5, 6}
    )
    if degree not in {1, 2, 3, 4} and not task035_fixed_target_high_order:
        raise NotImplementedError(
            "Stage-4 Floquet supports N1curl degree 1 through 4 generally and "
            "Task035/Task035b research degrees 5 through 6 on the fixed target; "
            f"requested degree={degree}, cell_type={cfg.mesh_cell_type_resolved}."
        )
    if cfg.scattering_background.lower() != "layered":
        raise ValueError("stage4_block_grating currently requires scattering_background='layered'.")
    if cfg.grating_width_x < 0.0 or cfg.grating_width_y < 0.0 or cfg.grating_height < 0.0:
        raise ValueError("Stage-4 grating dimensions must be non-negative.")
    if cfg.has_grating_block:
        if not (cfg.x_min <= cfg.grating_x_min < cfg.grating_x_max <= cfg.x_max):
            raise ValueError("Stage-4 grating x bounds must lie inside one periodic cell.")
        if not (cfg.y_min <= cfg.grating_y_min < cfg.grating_y_max <= cfg.y_max):
            raise ValueError("Stage-4 grating y bounds must lie inside one periodic cell.")
        if not (cfg.physical_z_min <= cfg.grating_z_min < cfg.grating_z_max <= cfg.physical_z_max):
            raise ValueError("Stage-4 grating z bounds must lie inside the physical z domain.")


def build_airbox_mesh_3d(cfg: SimulationConfig3D, out_dir: Path) -> AirBox3DMesh:
    """Build a structured 3D box mesh for staged verification.

    Stage 4 uses a tensor-product hexa path so rectangular material planes can
    be exact grid planes without requiring one global uniform cell size.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    comm = MPI.COMM_WORLD
    mesh_cell_type_resolved = cfg.mesh_cell_type_resolved
    hexa_axis_plan: HexaAxisPlan | None = None
    if cfg.geometry_kind == "rectangular_block_grating" and (
        mesh_cell_type_resolved in {"hexahedron", "tetrahedron"}
    ):
        hexa_axis_plan = _stage4_axis_plan(cfg, comm.size)
        mesh_cells_resolved = hexa_axis_plan.mesh_cells_resolved
        z_alignment_warnings = []
    elif mesh_cell_type_resolved == "hexahedron":
        if cfg.geometry_kind == "rectangular_block_grating":
            hexa_axis_plan = _stage4_axis_plan(cfg, comm.size)
            mesh_cells_resolved = hexa_axis_plan.mesh_cells_resolved
            z_alignment_warnings: list[str] = []
        else:
            mesh_cells_resolved = _hexa_mesh_cells(cfg, comm.size)
            uniform_axes = _uniform_axes(cfg, mesh_cells_resolved)
            hexa_axis_plan = HexaAxisPlan(
                x_values=uniform_axes["x"],
                y_values=uniform_axes["y"],
                z_values=uniform_axes["z"],
                mesh_spacing_mode_resolved="uniform_strict",
                axis_cell_stats={axis_name: _axis_stats(values) for axis_name, values in uniform_axes.items()},
                material_plane_alignment=_material_plane_alignment_report(cfg, uniform_axes),
                local_refinement_regions={"x": [], "y": [], "z": []},
            )
            z_alignment_warnings = _z_alignment_warnings(cfg, mesh_cells_resolved)
    else:
        mesh_cells_resolved = cfg.mesh_cells
        z_alignment_warnings = _z_alignment_warnings(cfg, mesh_cells_resolved)

    if mesh_cell_type_resolved == "hexahedron":
        assert hexa_axis_plan is not None
        if hexa_axis_plan.mesh_spacing_mode_resolved == "uniform_strict":
            points = [
                np.asarray((cfg.x_min, cfg.y_min, cfg.domain_z_min), dtype=np.float64),
                np.asarray((cfg.x_max, cfg.y_max, cfg.domain_z_max), dtype=np.float64),
            ]
            msh = mesh.create_box(
                comm,
                points,
                mesh_cells_resolved,
                cell_type=mesh.CellType.hexahedron,
                ghost_mode=mesh.GhostMode.shared_facet,
            )
            mesh_note = "Using dolfinx.mesh.create_box with uniform hexahedron cells."
        else:
            msh = _structured_hexa_mesh(
                comm,
                hexa_axis_plan.x_values,
                hexa_axis_plan.y_values,
                hexa_axis_plan.z_values,
                preserve_input_partition=(
                    cfg.stage4_preserve_structured_input_partition
                ),
            )
            mesh_note = (
                "Using custom tensor-product hexahedron cells with nonuniform axis spacing. "
                "Opposite periodic faces share the same axis coordinates, so explicit edge Floquet pairing remains one-to-one."
            )
        if comm.rank == 0:
            note_lines = [
                mesh_note,
                "This is the default low-memory 3D Floquet mesh because opposite periodic faces are structured.",
                f"mesh_spacing_mode_resolved = {hexa_axis_plan.mesh_spacing_mode_resolved}",
                f"mesh_cells_resolved = {mesh_cells_resolved}",
                "stage4_preserve_structured_input_partition = "
                f"{cfg.stage4_preserve_structured_input_partition}",
                f"axis_cell_stats = {hexa_axis_plan.axis_cell_stats}",
            ]
            if cfg.geometry_kind == "rectangular_block_grating":
                note_lines.append(
                    "Stage-4 rectangular block material planes are aligned to hexahedral grid planes; no midpoint material-boundary fallback is used."
                )
                note_lines.append(f"material_plane_alignment = {hexa_axis_plan.material_plane_alignment}")
                note_lines.append(f"local_refinement_regions = {hexa_axis_plan.local_refinement_regions}")
            note_lines.extend(f"WARNING: {message}" for message in z_alignment_warnings)
            (out_dir / "mesh_3d_partition_note.txt").write_text("\n".join(note_lines) + "\n", encoding="utf-8")
    elif (
        mesh_cell_type_resolved == "tetrahedron"
        and cfg.geometry_kind == "rectangular_block_grating"
    ):
        assert hexa_axis_plan is not None
        msh = _structured_tet_mesh_from_axes(
            comm,
            hexa_axis_plan.x_values,
            hexa_axis_plan.y_values,
            hexa_axis_plan.z_values,
        )
        if comm.rank == 0:
            (out_dir / "mesh_3d_partition_note.txt").write_text(
                "Using matching tensor axes split into six conforming tetrahedra per box.\n"
                "Opposite x/y faces use translated-identical triangle patterns.\n"
                "Stage-4 material planes are exact mesh facets.\n"
                f"mesh_spacing_mode_resolved = {hexa_axis_plan.mesh_spacing_mode_resolved}\n"
                f"mesh_cells_resolved = {mesh_cells_resolved}\n"
                f"axis_cell_stats = {hexa_axis_plan.axis_cell_stats}\n"
                f"material_plane_alignment = {hexa_axis_plan.material_plane_alignment}\n",
                encoding="utf-8",
            )
    elif comm.size > 1:
        points = [
            np.asarray((cfg.x_min, cfg.y_min, cfg.domain_z_min), dtype=np.float64),
            np.asarray((cfg.x_max, cfg.y_max, cfg.domain_z_max), dtype=np.float64),
        ]
        msh = mesh.create_box(
            comm,
            points,
            mesh_cells_resolved,
            cell_type=mesh.CellType.tetrahedron,
            ghost_mode=mesh.GhostMode.shared_facet,
        )
        if comm.rank == 0:
            (out_dir / "mesh_3d_partition_note.txt").write_text(
                "MPI run: using dolfinx.mesh.create_box fallback. "
                "Serial Stage-2 Fresnel/PML validation uses a custom z-aligned mesh; "
                "distributed custom z-aligned mesh is deferred because it currently "
                "segfaults in this Docker/DOLFINx stack.",
                encoding="utf-8",
            )
    else:
        msh = _structured_tet_mesh(comm, cfg)
    msh.name = cfg.case_name
    msh.topology.create_connectivity(msh.topology.dim - 1, msh.topology.dim)
    cell_tags = _mark_cells(msh, cfg)
    facet_tags, boundary_facets = _mark_boundary_facets(msh, cfg)

    if comm.size == 1:
        try:
            with io.XDMFFile(comm, out_dir / "mesh_3d.xdmf", "w") as xdmf:
                xdmf.write_mesh(msh)
        except Exception as exc:  # pragma: no cover - best-effort artifact
            if comm.rank == 0:
                (out_dir / "mesh_3d_xdmf_warning.txt").write_text(str(exc), encoding="utf-8")
    elif comm.rank == 0:
        (out_dir / "mesh_3d_xdmf_warning.txt").write_text(
            "MPI run: mesh_3d.xdmf is skipped for the custom Stage-2 mesh; "
            "open fields_3d_for_paraview_parallel.pvd after postprocess.",
            encoding="utf-8",
        )

    return AirBox3DMesh(
        mesh=msh,
        cell_tags=cell_tags,
        facet_tags=facet_tags,
        boundary_facets=boundary_facets,
        mesh_cell_type_resolved=mesh_cell_type_resolved,
        mesh_cells_resolved=mesh_cells_resolved,
        z_alignment_warnings=z_alignment_warnings,
        mesh_spacing_mode_resolved=hexa_axis_plan.mesh_spacing_mode_resolved if hexa_axis_plan is not None else "n/a",
        mesh_axis_cell_stats=hexa_axis_plan.axis_cell_stats if hexa_axis_plan is not None else {},
        material_plane_alignment=hexa_axis_plan.material_plane_alignment
        if hexa_axis_plan is not None
        else {"all_aligned": None, "missing": [], "checked": {"x": [], "y": [], "z": []}},
        local_refinement_regions=hexa_axis_plan.local_refinement_regions if hexa_axis_plan is not None else {},
    )


def rebuild_airbox_mesh_data_3d(
    refined_mesh: mesh.Mesh,
    cfg: SimulationConfig3D,
    template: AirBox3DMesh,
) -> AirBox3DMesh:
    """Rebuild material and boundary tags after conforming tetra refinement."""

    if refined_mesh.topology.cell_type != mesh.CellType.tetrahedron:
        raise ValueError("Task035 marked refinement requires a tetrahedron mesh.")
    refined_mesh.name = cfg.case_name
    refined_mesh.topology.create_connectivity(
        refined_mesh.topology.dim - 1, refined_mesh.topology.dim
    )
    cell_tags = _mark_cells(refined_mesh, cfg)
    facet_tags, boundary_facets = _mark_boundary_facets(refined_mesh, cfg)
    return AirBox3DMesh(
        mesh=refined_mesh,
        cell_tags=cell_tags,
        facet_tags=facet_tags,
        boundary_facets=boundary_facets,
        mesh_cell_type_resolved="tetrahedron",
        mesh_cells_resolved=template.mesh_cells_resolved,
        z_alignment_warnings=list(template.z_alignment_warnings),
        mesh_spacing_mode_resolved="estimator_marked_tetra_refinement",
        mesh_axis_cell_stats=dict(template.mesh_axis_cell_stats),
        material_plane_alignment=dict(template.material_plane_alignment),
        local_refinement_regions=dict(template.local_refinement_regions),
    )
