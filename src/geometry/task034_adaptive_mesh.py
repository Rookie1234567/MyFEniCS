from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Literal, Mapping, Sequence

import numpy as np
from mpi4py import MPI

from ..common.config_3d import SimulationConfig3D
from .hybrid_local_mesh import HybridLocalMesh, HybridLocalSide, _local_boundary_tags
from .mesh_builder_3d import (
    AirBox3DMesh,
    _axis_stats,
    _mark_cells,
    _structured_hexa_mesh,
)


Task034GradedProfile = Literal["mechanism", "conservative", "balanced", "aggressive"]

_PROFILE_PARAMETERS: dict[Task034GradedProfile, tuple[float, float]] = {
    "mechanism": (2.0, 2.0),
    "conservative": (1.5, 3.0),
    "balanced": (2.0, 2.0),
    "aggressive": (3.0, 1.0),
}


def _float_list(values: np.ndarray) -> list[float]:
    return [float(f"{value:.15g}") for value in np.asarray(values, dtype=np.float64)]


def _canonical_hash(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _unique_sorted(values: Sequence[float], *, tolerance: float) -> list[float]:
    ordered = sorted(float(value) for value in values)
    unique: list[float] = []
    for value in ordered:
        if not unique or abs(value - unique[-1]) > tolerance:
            unique.append(value)
    return unique


@dataclass(frozen=True)
class Task034Stage4Geometry:
    x_bounds_nm: tuple[float, float]
    y_bounds_nm: tuple[float, float]
    z_bounds_nm: tuple[float, float]
    material_planes_nm: dict[str, tuple[float, ...]]
    matching_planes_z_nm: tuple[float, float]

    @classmethod
    def from_config(
        cls,
        cfg: SimulationConfig3D,
        *,
        bottom_interface_z_nm: float = 10.0,
        top_interface_z_nm: float = 110.0,
    ) -> Task034Stage4Geometry:
        if (
            cfg.geometry_kind != "rectangular_block_grating"
            or not cfg.has_grating_block
        ):
            raise ValueError(
                "Task034 adaptive geometry requires the Stage-4 block grating."
            )
        if cfg.mesh_cell_type_resolved != "hexahedron":
            raise ValueError("Task034 adaptive geometry requires conforming hexahedra.")
        if not (
            cfg.domain_z_min
            < bottom_interface_z_nm
            < top_interface_z_nm
            < cfg.domain_z_max
        ):
            raise ValueError(
                "Task034 matching planes must lie strictly inside the z domain."
            )
        return cls(
            x_bounds_nm=(float(cfg.x_min), float(cfg.x_max)),
            y_bounds_nm=(float(cfg.y_min), float(cfg.y_max)),
            z_bounds_nm=(float(cfg.domain_z_min), float(cfg.domain_z_max)),
            material_planes_nm={
                "x": (float(cfg.grating_x_min), float(cfg.grating_x_max)),
                "y": (
                    *(
                        ()
                        if np.isclose(cfg.grating_y_min, cfg.y_min)
                        else (float(cfg.grating_y_min),)
                    ),
                    *(
                        ()
                        if np.isclose(cfg.grating_y_max, cfg.y_max)
                        else (float(cfg.grating_y_max),)
                    ),
                ),
                "z": (
                    float(cfg.interface_z),
                    float(cfg.grating_z_min),
                    float(cfg.grating_z_max),
                ),
            },
            matching_planes_z_nm=(
                float(bottom_interface_z_nm),
                float(top_interface_z_nm),
            ),
        )

    def to_record(self) -> dict[str, object]:
        return {
            "x_bounds_nm": list(self.x_bounds_nm),
            "y_bounds_nm": list(self.y_bounds_nm),
            "z_bounds_nm": list(self.z_bounds_nm),
            "material_planes_nm": {
                axis: list(values)
                for axis, values in sorted(self.material_planes_nm.items())
            },
            "matching_planes_z_nm": list(self.matching_planes_z_nm),
        }


@dataclass(frozen=True)
class Task034ConformingPlan:
    x_values: np.ndarray
    y_values: np.ndarray
    z_values: np.ndarray
    reference_h_nm: float
    profile: str
    coarse_factor: float
    transition_layers: float
    geometry: Task034Stage4Geometry
    plan_hash: str
    parent_plan_hash: str | None = None
    adaptive_iteration: int = 0
    marked_cell_count: int = 0

    @property
    def mesh_cells(self) -> tuple[int, int, int]:
        return (
            len(self.x_values) - 1,
            len(self.y_values) - 1,
            len(self.z_values) - 1,
        )

    @property
    def element_count(self) -> int:
        return int(np.prod(self.mesh_cells))

    def to_record(self) -> dict[str, object]:
        widths = {
            axis: np.diff(values)
            for axis, values in (
                ("x", self.x_values),
                ("y", self.y_values),
                ("z", self.z_values),
            )
        }
        minimum = min(float(np.min(value)) for value in widths.values())
        maximum = max(float(np.max(value)) for value in widths.values())
        return {
            "schema_version": "task034.conforming-plan.v1",
            "plan_hash": self.plan_hash,
            "parent_plan_hash": self.parent_plan_hash,
            "adaptive_iteration": self.adaptive_iteration,
            "marked_cell_count": self.marked_cell_count,
            "reference_h_nm": self.reference_h_nm,
            "profile": self.profile,
            "coarse_factor": self.coarse_factor,
            "transition_layers": self.transition_layers,
            "mesh_cells": list(self.mesh_cells),
            "element_count": self.element_count,
            "axes_nm": {
                "x": _float_list(self.x_values),
                "y": _float_list(self.y_values),
                "z": _float_list(self.z_values),
            },
            "axis_stats_nm": {
                axis: _axis_stats(values)
                for axis, values in (
                    ("x", self.x_values),
                    ("y", self.y_values),
                    ("z", self.z_values),
                )
            },
            "quality": {
                "minimum_axis_width_nm": minimum,
                "maximum_axis_width_nm": maximum,
                "axis_width_ratio": maximum / minimum,
                "positive_jacobian_proxy": minimum > 0.0,
                "hanging_nodes_present": False,
            },
            "periodic_pairing": {
                "x_trace_synchronized": True,
                "y_trace_synchronized": True,
                "periodic_mate_refinement_synchronized": True,
                "x_trace_signature": periodic_trace_signature(self, "x"),
                "y_trace_signature": periodic_trace_signature(self, "y"),
            },
            "material_planes_exact": material_planes_are_exact(self),
            "matching_planes_exact": matching_planes_are_exact(self),
            "ordinary_uniform_default_changed": False,
            "geometry": self.geometry.to_record(),
        }


def _axis_from_targets(
    bounds: tuple[float, float],
    *,
    exact_planes: Sequence[float],
    focus_planes: Sequence[float],
    reference_h_nm: float,
    coarse_factor: float,
    transition_layers: float,
    minimum_cells: int,
) -> np.ndarray:
    start, stop = bounds
    tolerance = 1.0e-12 * max(stop - start, 1.0)
    radius = transition_layers * reference_h_nm
    breakpoints: list[float] = [start, stop, *exact_planes]
    for plane in focus_planes:
        breakpoints.extend((max(start, plane - radius), min(stop, plane + radius)))
    points = _unique_sorted(breakpoints, tolerance=tolerance)
    axis = [points[0]]
    for low, high in zip(points[:-1], points[1:]):
        midpoint = 0.5 * (low + high)
        near_focus = any(
            abs(midpoint - plane) <= radius + tolerance for plane in focus_planes
        )
        target = reference_h_nm if near_focus else coarse_factor * reference_h_nm
        count = max(1, int(np.ceil((high - low) / target)))
        axis.extend(float(value) for value in np.linspace(low, high, count + 1)[1:])
    while len(axis) - 1 < minimum_cells:
        values = np.asarray(axis, dtype=np.float64)
        index = int(np.argmax(np.diff(values)))
        axis.insert(index + 1, 0.5 * (axis[index] + axis[index + 1]))
    return np.asarray(axis, dtype=np.float64)


def _refine_until_comm_safe(
    axes: dict[str, np.ndarray], comm_size: int
) -> dict[str, np.ndarray]:
    resolved = {
        name: np.asarray(values, dtype=np.float64) for name, values in axes.items()
    }
    while int(np.prod([len(values) - 1 for values in resolved.values()])) < comm_size:
        candidates = []
        for name, values in resolved.items():
            widths = np.diff(values)
            index = int(np.argmax(widths))
            candidates.append((float(widths[index]), name, index))
        _, name, index = max(candidates)
        values = resolved[name]
        resolved[name] = np.insert(
            values, index + 1, 0.5 * (values[index] + values[index + 1])
        )
    return resolved


def _plan_from_axes(
    *,
    axes: Mapping[str, np.ndarray],
    reference_h_nm: float,
    profile: str,
    coarse_factor: float,
    transition_layers: float,
    geometry: Task034Stage4Geometry,
    parent_plan_hash: str | None = None,
    adaptive_iteration: int = 0,
    marked_cell_count: int = 0,
) -> Task034ConformingPlan:
    canonical = {
        "schema_version": "task034.conforming-plan.v1",
        "reference_h_nm": float(reference_h_nm),
        "profile": profile,
        "coarse_factor": float(coarse_factor),
        "transition_layers": float(transition_layers),
        "geometry": geometry.to_record(),
        "axes_nm": {
            name: _float_list(np.asarray(axes[name])) for name in ("x", "y", "z")
        },
        "parent_plan_hash": parent_plan_hash,
        "adaptive_iteration": adaptive_iteration,
        "marked_cell_count": marked_cell_count,
    }
    plan = Task034ConformingPlan(
        x_values=np.asarray(axes["x"], dtype=np.float64),
        y_values=np.asarray(axes["y"], dtype=np.float64),
        z_values=np.asarray(axes["z"], dtype=np.float64),
        reference_h_nm=float(reference_h_nm),
        profile=profile,
        coarse_factor=float(coarse_factor),
        transition_layers=float(transition_layers),
        geometry=geometry,
        plan_hash=_canonical_hash(canonical),
        parent_plan_hash=parent_plan_hash,
        adaptive_iteration=adaptive_iteration,
        marked_cell_count=marked_cell_count,
    )
    validate_conforming_plan(plan)
    return plan


def build_task034_conforming_graded_plan(
    *,
    reference_h_nm: float,
    geometry: Task034Stage4Geometry,
    profile: Task034GradedProfile = "mechanism",
    coarse_factor: float | None = None,
    comm_size: int = 1,
) -> Task034ConformingPlan:
    if reference_h_nm <= 0.0:
        raise ValueError("reference_h_nm must be positive.")
    if comm_size <= 0:
        raise ValueError("comm_size must be positive.")
    default_factor, transition_layers = _PROFILE_PARAMETERS[profile]
    factor = default_factor if coarse_factor is None else float(coarse_factor)
    if factor <= 1.0:
        raise ValueError("coarse_factor must be greater than one.")
    axes = {
        "x": _axis_from_targets(
            geometry.x_bounds_nm,
            exact_planes=geometry.material_planes_nm["x"],
            focus_planes=geometry.material_planes_nm["x"],
            reference_h_nm=reference_h_nm,
            coarse_factor=factor,
            transition_layers=transition_layers,
            minimum_cells=2,
        ),
        "y": _axis_from_targets(
            geometry.y_bounds_nm,
            exact_planes=geometry.material_planes_nm["y"],
            focus_planes=geometry.material_planes_nm["y"],
            reference_h_nm=reference_h_nm,
            coarse_factor=factor,
            transition_layers=transition_layers,
            minimum_cells=2,
        ),
        "z": _axis_from_targets(
            geometry.z_bounds_nm,
            exact_planes=(
                *geometry.material_planes_nm["z"],
                *geometry.matching_planes_z_nm,
            ),
            focus_planes=geometry.material_planes_nm["z"],
            reference_h_nm=reference_h_nm,
            coarse_factor=factor,
            transition_layers=transition_layers,
            minimum_cells=1,
        ),
    }
    axes = _refine_until_comm_safe(axes, comm_size)
    return _plan_from_axes(
        axes=axes,
        reference_h_nm=reference_h_nm,
        profile=profile,
        coarse_factor=factor,
        transition_layers=transition_layers,
        geometry=geometry,
    )


def _contains(values: np.ndarray, target: float) -> bool:
    tolerance = 1.0e-10 * max(float(values[-1] - values[0]), 1.0)
    return bool(np.any(np.isclose(values, target, atol=tolerance, rtol=0.0)))


def material_planes_are_exact(plan: Task034ConformingPlan) -> bool:
    axes = {"x": plan.x_values, "y": plan.y_values, "z": plan.z_values}
    return all(
        _contains(axes[axis], plane)
        for axis, planes in plan.geometry.material_planes_nm.items()
        for plane in planes
    )


def matching_planes_are_exact(plan: Task034ConformingPlan) -> bool:
    return all(
        _contains(plan.z_values, plane) for plane in plan.geometry.matching_planes_z_nm
    )


def periodic_trace_signature(
    plan: Task034ConformingPlan, periodic_axis: Literal["x", "y"]
) -> str:
    trace_axes = (
        {"y": _float_list(plan.y_values), "z": _float_list(plan.z_values)}
        if periodic_axis == "x"
        else {"x": _float_list(plan.x_values), "z": _float_list(plan.z_values)}
    )
    return _canonical_hash(
        {"periodic_axis": periodic_axis, "trace_axes_nm": trace_axes}
    )


def assert_periodic_mate_trace(
    plan: Task034ConformingPlan,
    periodic_axis: Literal["x", "y"],
    *,
    mate_first_trace_axes: tuple[np.ndarray, np.ndarray],
    mate_second_trace_axes: tuple[np.ndarray, np.ndarray],
) -> None:
    del plan
    for first, second in zip(mate_first_trace_axes, mate_second_trace_axes):
        if first.shape != second.shape or not np.array_equal(first, second):
            raise ValueError(f"Broken {periodic_axis}-periodic mate trace topology.")


def validate_conforming_plan(plan: Task034ConformingPlan) -> None:
    for name, values, bounds in (
        ("x", plan.x_values, plan.geometry.x_bounds_nm),
        ("y", plan.y_values, plan.geometry.y_bounds_nm),
        ("z", plan.z_values, plan.geometry.z_bounds_nm),
    ):
        if values.ndim != 1 or len(values) < 2 or np.any(np.diff(values) <= 0.0):
            raise ValueError(f"Task034 {name} axis must be strictly increasing.")
        if not np.isclose(values[0], bounds[0]) or not np.isclose(
            values[-1], bounds[1]
        ):
            raise ValueError(f"Task034 {name} axis does not span the frozen domain.")
    if not material_planes_are_exact(plan):
        raise ValueError("Task034 conforming plan lost an exact material plane.")
    if not matching_planes_are_exact(plan):
        raise ValueError("Task034 conforming plan lost a matching trace plane.")


def global_indicator_scales(
    components: Mapping[str, np.ndarray],
    *,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
) -> dict[str, float]:
    scales: dict[str, float] = {}
    for name, values in sorted(components.items()):
        array = np.asarray(values)
        if array.ndim != 1 or not np.all(np.isfinite(array)):
            raise ValueError(f"Indicator component {name!r} must be a finite vector.")
        local_sum = float(np.sum(np.abs(array) ** 2))
        global_sum = float(comm.allreduce(local_sum, op=MPI.SUM))
        global_count = int(comm.allreduce(array.size, op=MPI.SUM))
        scales[name] = max(np.sqrt(global_sum / max(global_count, 1)), 1.0e-30)
    return scales


def combine_maxwell_indicator(
    components: Mapping[str, np.ndarray],
    *,
    scales: Mapping[str, float],
    weights: Mapping[str, float] | None = None,
) -> np.ndarray:
    required = {"volume_residual", "curl_jump", "material_interface"}
    if not required.issubset(components):
        raise ValueError(
            f"Missing Maxwell indicator components: {sorted(required - set(components))}"
        )
    lengths = {np.asarray(values).size for values in components.values()}
    if len(lengths) != 1:
        raise ValueError("Maxwell indicator components must have equal lengths.")
    total = np.zeros(next(iter(lengths)), dtype=np.float64)
    resolved_weights = {} if weights is None else dict(weights)
    for name, values in sorted(components.items()):
        array = np.asarray(values)
        if array.ndim != 1 or not np.all(np.isfinite(array)):
            raise ValueError(f"Indicator component {name!r} must be finite.")
        scale = float(scales.get(name, 0.0))
        weight = float(resolved_weights.get(name, 1.0))
        if (
            not np.isfinite(scale)
            or scale <= 0.0
            or not np.isfinite(weight)
            or weight < 0.0
        ):
            raise ValueError(
                "Indicator scales must be positive and weights nonnegative."
            )
        total += weight * (np.abs(array) / scale) ** 2
    result = np.sqrt(total)
    if not np.all(np.isfinite(result)) or np.any(result < 0.0):
        raise RuntimeError("Combined Maxwell indicator is not finite and nonnegative.")
    return result


def canonical_indicator_table(
    global_cell_ids: np.ndarray, indicator: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    ids = np.asarray(global_cell_ids, dtype=np.int64)
    values = np.asarray(indicator, dtype=np.float64)
    if ids.ndim != 1 or values.ndim != 1 or ids.shape != values.shape:
        raise ValueError("Indicator ids and values must be equal-length vectors.")
    if np.any(ids < 0) or not np.all(np.isfinite(values)) or np.any(values < 0.0):
        raise ValueError(
            "Indicator table requires nonnegative ids and finite nonnegative values."
        )
    order = np.argsort(ids, kind="stable")
    ids = ids[order]
    values = values[order]
    if len(ids) > 1 and np.any(np.diff(ids) == 0):
        raise ValueError("Indicator table contains duplicate global cell ids.")
    return ids, values


def indicator_digest(global_cell_ids: np.ndarray, indicator: np.ndarray) -> str:
    ids, values = canonical_indicator_table(global_cell_ids, indicator)
    return _canonical_hash(
        {"global_cell_ids": ids.tolist(), "indicator": _float_list(values)}
    )


def robust_common_indicator(
    parameter_indicators: Mapping[str, tuple[np.ndarray, np.ndarray]],
) -> tuple[np.ndarray, np.ndarray]:
    if not parameter_indicators:
        raise ValueError("At least one parameter indicator is required.")
    reference_ids: np.ndarray | None = None
    rows: list[np.ndarray] = []
    for name in sorted(parameter_indicators):
        ids, values = canonical_indicator_table(*parameter_indicators[name])
        if reference_ids is None:
            reference_ids = ids
        elif not np.array_equal(reference_ids, ids):
            raise ValueError(
                "Robust common-mesh indicators must share global cell ids."
            )
        rows.append(values)
    assert reference_ids is not None
    return reference_ids, np.max(np.vstack(rows), axis=0)


def dorfler_marked_cells(
    global_cell_ids: np.ndarray, indicator: np.ndarray, *, theta: float
) -> np.ndarray:
    if not 0.0 < theta <= 1.0:
        raise ValueError("Dorfler theta must lie in (0, 1].")
    ids, values = canonical_indicator_table(global_cell_ids, indicator)
    energy = values**2
    if not np.any(energy > 0.0):
        return np.empty(0, dtype=np.int64)
    order = np.lexsort((ids, -energy))
    count = (
        int(
            np.searchsorted(
                np.cumsum(energy[order]), theta * np.sum(energy), side="left"
            )
        )
        + 1
    )
    return np.sort(ids[order[:count]])


def refine_plan_from_indicator(
    plan: Task034ConformingPlan,
    global_cell_ids: np.ndarray,
    indicator: np.ndarray,
    *,
    theta: float,
) -> Task034ConformingPlan:
    marked = dorfler_marked_cells(global_cell_ids, indicator, theta=theta)
    if marked.size == 0:
        raise ValueError(
            "A zero indicator cannot drive a genuine adaptive refinement step."
        )
    nx, ny, nz = plan.mesh_cells
    if np.any(marked >= nx * ny * nz):
        raise ValueError("A marked global tensor cell id lies outside the plan.")
    x_indices: set[int] = set()
    y_indices: set[int] = set()
    z_indices: set[int] = set()
    for cell_id in marked:
        k, remainder = divmod(int(cell_id), nx * ny)
        j, i = divmod(remainder, nx)
        x_indices.add(i)
        y_indices.add(j)
        z_indices.add(k)
    if 0 in x_indices or nx - 1 in x_indices:
        x_indices.update((0, nx - 1))
    if 0 in y_indices or ny - 1 in y_indices:
        y_indices.update((0, ny - 1))

    def split(values: np.ndarray, indices: set[int]) -> np.ndarray:
        midpoints = [
            0.5 * (values[index] + values[index + 1]) for index in sorted(indices)
        ]
        return np.asarray(sorted([*values.tolist(), *midpoints]), dtype=np.float64)

    return _plan_from_axes(
        axes={
            "x": split(plan.x_values, x_indices),
            "y": split(plan.y_values, y_indices),
            "z": split(plan.z_values, z_indices),
        },
        reference_h_nm=plan.reference_h_nm,
        profile=f"adaptive_from_{plan.profile}",
        coarse_factor=plan.coarse_factor,
        transition_layers=plan.transition_layers,
        geometry=plan.geometry,
        parent_plan_hash=plan.plan_hash,
        adaptive_iteration=plan.adaptive_iteration + 1,
        marked_cell_count=int(marked.size),
    )


def _build_local_mesh(
    cfg: SimulationConfig3D,
    plan: Task034ConformingPlan,
    side: HybridLocalSide,
    *,
    comm: MPI.Intracomm,
) -> HybridLocalMesh:
    bottom_interface, top_interface = plan.geometry.matching_planes_z_nm
    interface_z = bottom_interface if side == "bottom" else top_interface
    tolerance = 1.0e-10 * max(cfg.period_x, cfg.period_y, 1.0)
    if side == "bottom":
        z_values = plan.z_values[plan.z_values <= interface_z + tolerance]
        external_z = float(cfg.domain_z_min)
        interface_tag, external_tag, local_normal_sign = (
            cfg.tags.z_max,
            cfg.tags.z_min,
            +1,
        )
    else:
        z_values = plan.z_values[plan.z_values >= interface_z - tolerance]
        external_z = float(cfg.domain_z_max)
        interface_tag, external_tag, local_normal_sign = (
            cfg.tags.z_min,
            cfg.tags.z_max,
            -1,
        )
    msh = _structured_hexa_mesh(comm, plan.x_values, plan.y_values, z_values)
    msh.name = f"{cfg.case_name}_{side}_task034_adaptive_local"
    msh.topology.create_connectivity(msh.topology.dim - 1, msh.topology.dim)
    cell_tags = _mark_cells(msh, cfg)
    facet_tags, boundary_facets = _local_boundary_tags(
        msh, cfg, z_min=float(z_values[0]), z_max=float(z_values[-1])
    )
    mesh_cells = (len(plan.x_values) - 1, len(plan.y_values) - 1, len(z_values) - 1)
    mesh_data = AirBox3DMesh(
        mesh=msh,
        cell_tags=cell_tags,
        facet_tags=facet_tags,
        boundary_facets=boundary_facets,
        mesh_cell_type_resolved="hexahedron",
        mesh_cells_resolved=mesh_cells,
        z_alignment_warnings=[],
        mesh_spacing_mode_resolved="task034_conforming_graded_opt_in",
        mesh_axis_cell_stats={
            "x": _axis_stats(plan.x_values),
            "y": _axis_stats(plan.y_values),
            "z": _axis_stats(z_values),
        },
        material_plane_alignment={
            "all_aligned": material_planes_are_exact(plan),
            "source": "task034_conforming_plan",
        },
        local_refinement_regions={"x": [], "y": [], "z": []},
    )
    fdim = msh.topology.dim - 1
    owned_facets = msh.topology.index_map(fdim).size_local
    global_interface = int(
        comm.allreduce(
            np.count_nonzero(facet_tags.find(interface_tag) < owned_facets), op=MPI.SUM
        )
    )
    global_external = int(
        comm.allreduce(
            np.count_nonzero(facet_tags.find(external_tag) < owned_facets), op=MPI.SUM
        )
    )
    expected = mesh_cells[0] * mesh_cells[1]
    if global_interface != expected or global_external != expected:
        raise RuntimeError(
            "Task034 local interface trace does not match the x/y tensor plan."
        )
    return HybridLocalMesh(
        side=side,
        mesh_data=mesh_data,
        z_values=np.asarray(z_values),
        interface_z_nm=float(interface_z),
        external_z_nm=external_z,
        interface_facet_tag=interface_tag,
        external_facet_tag=external_tag,
        local_interface_outward_normal_sign=local_normal_sign,
        modal_interface_outward_normal_sign=-local_normal_sign,
        global_interface_facet_count=global_interface,
        global_external_facet_count=global_external,
    )


def build_task034_graded_local_mesh_pair(
    cfg: SimulationConfig3D,
    plan: Task034ConformingPlan,
    *,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
) -> tuple[HybridLocalMesh, HybridLocalMesh]:
    validate_conforming_plan(plan)
    bottom = _build_local_mesh(cfg, plan, "bottom", comm=comm)
    top = _build_local_mesh(cfg, plan, "top", comm=comm)
    if bottom.mesh_cells[:2] != top.mesh_cells[:2]:
        raise RuntimeError("Task034 bottom/top local interface topology mismatch.")
    return bottom, top
