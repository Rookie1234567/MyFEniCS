from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Mapping, Sequence

import numpy as np


MAIN_REFERENCE_LEVELS_NM = (5.0, 3.0)
MANDATORY_GATES = {
    "true_residual": 1.0e-9,
    "max_abs_rta_delta": 1.0e-5,
    "max_significant_order_amplitude_relative_delta": 1.0e-3,
    "sampled_interface_e_relative_error": 5.0e-3,
    "sampled_interface_h_relative_error": 1.0e-2,
}
STRONG_GATES = {
    "max_abs_rta_delta": 1.0e-6,
    "max_significant_order_amplitude_relative_delta": 1.0e-4,
}


class AdaptiveMeshContractError(ValueError):
    """Raised when an adaptive-mesh request violates the Task033 contract."""


class AdaptiveMeshBudgetError(RuntimeError):
    """Raised before mesh creation when a rebuild exceeds its cell budget."""


@dataclass(frozen=True)
class Task033Stage4Geometry:
    """Frozen geometry needed by the p2 graded-mesh feasibility path."""

    x_min_nm: float = 0.0
    x_max_nm: float = 50.0
    y_min_nm: float = 0.0
    y_max_nm: float = 25.0
    bottom_external_z_nm: float = -10.0
    bottom_interface_z_nm: float = 10.0
    top_interface_z_nm: float = 110.0
    top_external_z_nm: float = 130.0
    grating_x_min_nm: float = 16.5
    grating_x_max_nm: float = 33.5
    grating_z_min_nm: float = 0.0
    grating_z_max_nm: float = 120.0

    @classmethod
    def from_config(cls, cfg: object) -> Task033Stage4Geometry:
        return cls(
            x_min_nm=float(getattr(cfg, "x_min")),
            x_max_nm=float(getattr(cfg, "x_max")),
            y_min_nm=float(getattr(cfg, "y_min")),
            y_max_nm=float(getattr(cfg, "y_max")),
            bottom_external_z_nm=float(getattr(cfg, "domain_z_min")),
            bottom_interface_z_nm=10.0,
            top_interface_z_nm=110.0,
            top_external_z_nm=float(getattr(cfg, "domain_z_max")),
            grating_x_min_nm=float(getattr(cfg, "grating_x_min")),
            grating_x_max_nm=float(getattr(cfg, "grating_x_max")),
            grating_z_min_nm=float(getattr(cfg, "grating_z_min")),
            grating_z_max_nm=float(getattr(cfg, "grating_z_max")),
        )

    def validate(self) -> None:
        pairs = (
            (self.x_min_nm, self.x_max_nm, "x"),
            (self.y_min_nm, self.y_max_nm, "y"),
            (
                self.bottom_external_z_nm,
                self.bottom_interface_z_nm,
                "bottom z",
            ),
            (self.top_interface_z_nm, self.top_external_z_nm, "top z"),
        )
        for low, high, label in pairs:
            if not np.isfinite(low) or not np.isfinite(high) or high <= low:
                raise AdaptiveMeshContractError(f"Invalid {label} span {low:g}..{high:g}.")
        if not self.x_min_nm < self.grating_x_min_nm < self.grating_x_max_nm < self.x_max_nm:
            raise AdaptiveMeshContractError("Grating x planes must lie inside the period.")
        if not (
            self.bottom_external_z_nm
            < self.grating_z_min_nm
            < self.bottom_interface_z_nm
        ):
            raise AdaptiveMeshContractError("The lower material plane is outside the bottom block.")
        if not (
            self.top_interface_z_nm
            < self.grating_z_max_nm
            < self.top_external_z_nm
        ):
            raise AdaptiveMeshContractError("The upper material plane is outside the top block.")


def _validated_axis(values: Sequence[float], *, label: str) -> np.ndarray:
    axis = np.asarray(values, dtype=np.float64)
    if axis.ndim != 1 or len(axis) < 2:
        raise AdaptiveMeshContractError(f"{label} needs at least two coordinates.")
    if not np.all(np.isfinite(axis)) or np.any(np.diff(axis) <= 0.0):
        raise AdaptiveMeshContractError(f"{label} must be finite and strictly increasing.")
    return axis


def _deduplicate(values: Sequence[float], tolerance: float) -> list[float]:
    ordered = sorted(float(value) for value in values)
    unique: list[float] = []
    for value in ordered:
        if not unique or abs(value - unique[-1]) > tolerance:
            unique.append(value)
    return unique


def fitted_axis(
    start: float,
    stop: float,
    target_size_nm: float,
    *,
    required_planes_nm: Sequence[float] = (),
    min_cells: int = 1,
) -> np.ndarray:
    """Build a conforming one-dimensional grid containing every required plane."""

    if not np.isfinite(target_size_nm) or target_size_nm <= 0.0:
        raise AdaptiveMeshContractError("target_size_nm must be positive and finite.")
    if stop <= start:
        raise AdaptiveMeshContractError("Axis stop must be greater than start.")
    tolerance = 1.0e-12 * max(stop - start, 1.0)
    required = [float(value) for value in required_planes_nm]
    if any(value < start - tolerance or value > stop + tolerance for value in required):
        raise AdaptiveMeshContractError("A required plane lies outside the axis span.")
    breaks = _deduplicate([start, stop, *required], tolerance)
    coordinates = [float(start)]
    for low, high in zip(breaks[:-1], breaks[1:]):
        count = max(1, int(np.ceil((high - low) / target_size_nm)))
        coordinates.extend(np.linspace(low, high, count + 1, dtype=np.float64)[1:])
    axis = np.asarray(coordinates, dtype=np.float64)
    while len(axis) - 1 < int(min_cells):
        widths = np.diff(axis)
        split = int(np.argmax(widths))
        axis = np.insert(axis, split + 1, 0.5 * (axis[split] + axis[split + 1]))
    return _validated_axis(axis, label="fitted axis")


def axis_neighbor_ratio(values: Sequence[float], *, periodic: bool) -> float:
    axis = _validated_axis(values, label="graded axis")
    widths = np.diff(axis)
    pairs = list(zip(widths[:-1], widths[1:]))
    if periodic and len(widths) > 1:
        pairs.append((widths[-1], widths[0]))
    if not pairs:
        return 1.0
    return float(max(max(left / right, right / left) for left, right in pairs))


def refine_marked_axis(
    values: Sequence[float],
    marked_intervals: Sequence[bool],
    *,
    periodic: bool,
    max_neighbor_ratio: float = 2.0,
    max_cells: int = 4096,
) -> np.ndarray:
    """Bisect marked intervals and grade neighbors without hanging nodes."""

    axis = _validated_axis(values, label="parent axis")
    marked = np.asarray(marked_intervals, dtype=bool)
    if marked.shape != (len(axis) - 1,):
        raise AdaptiveMeshContractError("Axis marks do not match the parent intervals.")
    if max_neighbor_ratio < 1.0:
        raise AdaptiveMeshContractError("max_neighbor_ratio must be at least one.")
    if int(max_cells) < 1:
        raise AdaptiveMeshContractError("max_cells must be positive.")
    coordinates = [float(axis[0])]
    for index, (low, high) in enumerate(zip(axis[:-1], axis[1:])):
        if marked[index]:
            coordinates.append(0.5 * float(low + high))
        coordinates.append(float(high))
    balanced = np.asarray(coordinates, dtype=np.float64)
    if len(balanced) - 1 > int(max_cells):
        raise AdaptiveMeshBudgetError(
            f"Marked refinement exceeded the {max_cells} cell safety cap."
        )
    while axis_neighbor_ratio(balanced, periodic=periodic) > max_neighbor_ratio * (1.0 + 1.0e-12):
        widths = np.diff(balanced)
        pairs = [(index, index + 1) for index in range(len(widths) - 1)]
        if periodic and len(widths) > 1:
            pairs.append((len(widths) - 1, 0))
        offending = max(
            pairs,
            key=lambda pair: max(
                widths[pair[0]] / widths[pair[1]],
                widths[pair[1]] / widths[pair[0]],
            ),
        )
        split = offending[0] if widths[offending[0]] > widths[offending[1]] else offending[1]
        midpoint = 0.5 * (balanced[split] + balanced[split + 1])
        balanced = np.insert(balanced, split + 1, midpoint)
        if len(balanced) - 1 > int(max_cells):
            raise AdaptiveMeshBudgetError(
                f"Axis balancing exceeded the {max_cells} cell safety cap."
            )
    return _validated_axis(balanced, label="balanced axis")


def mark_axis_intervals_near_planes(
    values: Sequence[float],
    planes_nm: Sequence[float],
    *,
    radius_nm: float,
) -> np.ndarray:
    axis = _validated_axis(values, label="marking axis")
    if radius_nm < 0.0 or not np.isfinite(radius_nm):
        raise AdaptiveMeshContractError("radius_nm must be finite and non-negative.")
    centers = 0.5 * (axis[:-1] + axis[1:])
    marks = np.zeros(len(centers), dtype=bool)
    for plane in planes_nm:
        marks |= np.abs(centers - float(plane)) <= radius_nm
        marks |= (axis[:-1] <= float(plane)) & (float(plane) <= axis[1:])
    return marks


def synchronize_periodic_cell_marks(cell_marks: np.ndarray) -> np.ndarray:
    """Union x/y opposite-boundary marks before a conforming tensor rebuild."""

    marks = np.asarray(cell_marks, dtype=bool).copy()
    if marks.ndim != 3 or any(length < 1 for length in marks.shape):
        raise AdaptiveMeshContractError("Cell marks must have shape (nx, ny, nz).")
    x_pair = marks[0, :, :] | marks[-1, :, :]
    marks[0, :, :] = x_pair
    marks[-1, :, :] = x_pair
    y_pair = marks[:, 0, :] | marks[:, -1, :]
    marks[:, 0, :] = y_pair
    marks[:, -1, :] = y_pair
    # The second x union propagates y-corner changes to all four periodic copies.
    x_pair = marks[0, :, :] | marks[-1, :, :]
    marks[0, :, :] = x_pair
    marks[-1, :, :] = x_pair
    return marks


def dorfler_mark(indicator: np.ndarray, *, theta: float = 0.5) -> np.ndarray:
    """Return the minimal deterministic bulk set reaching ``theta`` of the sum."""

    values = np.asarray(indicator, dtype=np.float64)
    if values.ndim != 3 or not np.all(np.isfinite(values)) or np.any(values < 0.0):
        raise AdaptiveMeshContractError(
            "Indicator values must be a finite non-negative three-dimensional array."
        )
    if not 0.0 < theta <= 1.0:
        raise AdaptiveMeshContractError("Dorfler theta must lie in (0, 1].")
    flat = values.ravel()
    marks = np.zeros(flat.shape, dtype=bool)
    total = float(np.sum(flat))
    if total == 0.0:
        return marks.reshape(values.shape)
    # Stable sorting gives a deterministic index tie-break.
    order = np.argsort(-flat, kind="stable")
    cumulative = np.cumsum(flat[order])
    count = int(np.searchsorted(cumulative, theta * total, side="left")) + 1
    marks[order[:count]] = True
    return marks.reshape(values.shape)


def combined_indicator(
    element_residual: np.ndarray,
    tangential_curl_jump: np.ndarray,
    *,
    jump_weight: float = 1.0,
) -> np.ndarray:
    residual = np.asarray(element_residual, dtype=np.float64)
    jump = np.asarray(tangential_curl_jump, dtype=np.float64)
    if residual.shape != jump.shape:
        raise AdaptiveMeshContractError("Residual and jump indicators need the same shape.")
    if jump_weight < 0.0 or not np.isfinite(jump_weight):
        raise AdaptiveMeshContractError("jump_weight must be finite and non-negative.")
    return np.hypot(residual, jump_weight * jump)


def _axis_hash(values: np.ndarray) -> str:
    little_endian = np.asarray(values, dtype="<f8")
    return sha256(little_endian.tobytes()).hexdigest()


@dataclass(frozen=True)
class PeriodicGradedHybridPlan:
    geometry: Task033Stage4Geometry
    reference_h_nm: float
    cycle: int
    x_values: np.ndarray
    y_values: np.ndarray
    bottom_z_values: np.ndarray
    top_z_values: np.ndarray
    policy: str
    parent_plan_hash: str | None = None
    explicit_y_feature_planes_present: bool = False
    max_neighbor_ratio: float = 2.0

    def __post_init__(self) -> None:
        self.geometry.validate()
        if not any(
            np.isclose(float(self.reference_h_nm), allowed)
            for allowed in MAIN_REFERENCE_LEVELS_NM
        ):
            raise AdaptiveMeshContractError("A graded plan must target the h5 or h3 reference.")
        if int(self.cycle) < 0:
            raise AdaptiveMeshContractError("Adaptive cycle must be non-negative.")
        if self.max_neighbor_ratio < 1.0:
            raise AdaptiveMeshContractError("max_neighbor_ratio must be at least one.")
        for field_name, label in (
            ("x_values", "x"),
            ("y_values", "y"),
            ("bottom_z_values", "bottom z"),
            ("top_z_values", "top z"),
        ):
            axis = _validated_axis(getattr(self, field_name), label=label).copy()
            axis.flags.writeable = False
            object.__setattr__(self, field_name, axis)

    @property
    def mesh_cells(self) -> dict[str, int]:
        nx = len(self.x_values) - 1
        ny = len(self.y_values) - 1
        bottom = nx * ny * (len(self.bottom_z_values) - 1)
        top = nx * ny * (len(self.top_z_values) - 1)
        return {"bottom": int(bottom), "top": int(top), "total": int(bottom + top)}

    @property
    def plan_hash(self) -> str:
        digest = sha256()
        for axis in (
            self.x_values,
            self.y_values,
            self.bottom_z_values,
            self.top_z_values,
        ):
            digest.update(np.asarray(axis, dtype="<f8").tobytes())
        for field_name in self.geometry.__dataclass_fields__:
            digest.update(f"{field_name}:{getattr(self.geometry, field_name):.17g}".encode())
        digest.update(f"p2:{self.reference_h_nm:g}:{self.cycle}:{self.policy}".encode())
        digest.update(str(self.explicit_y_feature_planes_present).encode())
        digest.update(f"{self.max_neighbor_ratio:.17g}".encode())
        return digest.hexdigest()

    def certificate(self) -> dict[str, Any]:
        geometry = self.geometry
        axes = {
            "x": _validated_axis(self.x_values, label="x"),
            "y": _validated_axis(self.y_values, label="y"),
            "bottom_z": _validated_axis(self.bottom_z_values, label="bottom z"),
            "top_z": _validated_axis(self.top_z_values, label="top z"),
        }
        tolerance = 1.0e-11

        def contains(axis: np.ndarray, value: float) -> bool:
            return bool(np.any(np.isclose(axis, value, atol=tolerance, rtol=0.0)))

        checks = {
            "degree_is_fixed_p2": True,
            "conforming_tensor_product": True,
            "custom_hanging_node_constraints_used": False,
            "x_opposite_faces_share_yz_coordinates": True,
            "y_opposite_faces_share_xz_coordinates": True,
            "bottom_top_modal_trace_xy_exact_match": True,
            "material_x_planes_present": all(
                contains(axes["x"], value)
                for value in (geometry.grating_x_min_nm, geometry.grating_x_max_nm)
            ),
            "bottom_material_and_interface_planes_present": all(
                contains(axes["bottom_z"], value)
                for value in (geometry.grating_z_min_nm, geometry.bottom_interface_z_nm)
            ),
            "top_material_and_interface_planes_present": all(
                contains(axes["top_z"], value)
                for value in (geometry.top_interface_z_nm, geometry.grating_z_max_nm)
            ),
            "periodic_cell_mark_sync_required": True,
            "ordinary_default_changed": False,
        }
        ratios = {
            "x_periodic": axis_neighbor_ratio(axes["x"], periodic=True),
            "y_periodic": axis_neighbor_ratio(axes["y"], periodic=True),
            "bottom_z": axis_neighbor_ratio(axes["bottom_z"], periodic=False),
            "top_z": axis_neighbor_ratio(axes["top_z"], periodic=False),
        }
        checks["neighbor_ratio_gate_pass"] = all(
            value <= self.max_neighbor_ratio * (1.0 + 1.0e-12)
            for value in ratios.values()
        )
        eligible = (
            checks["degree_is_fixed_p2"]
            and checks["conforming_tensor_product"]
            and not checks["custom_hanging_node_constraints_used"]
            and checks["x_opposite_faces_share_yz_coordinates"]
            and checks["y_opposite_faces_share_xz_coordinates"]
            and checks["bottom_top_modal_trace_xy_exact_match"]
            and checks["material_x_planes_present"]
            and checks["bottom_material_and_interface_planes_present"]
            and checks["top_material_and_interface_planes_present"]
            and checks["periodic_cell_mark_sync_required"]
            and not checks["ordinary_default_changed"]
            and checks["neighbor_ratio_gate_pass"]
        )
        return {
            "eligible_for_mesh_smoke": eligible,
            "checks": checks,
            "neighbor_width_ratios": ratios,
            "axis_hashes": {name: _axis_hash(axis) for name, axis in axes.items()},
            "full_mesh_or_field_gathered": False,
            "explicit_y_feature_planes_present": self.explicit_y_feature_planes_present,
        }

    def to_record(self) -> dict[str, Any]:
        return {
            "reference_h_nm": float(self.reference_h_nm),
            "degree": 2,
            "cycle": int(self.cycle),
            "policy": self.policy,
            "plan_hash": self.plan_hash,
            "parent_plan_hash": self.parent_plan_hash,
            "axis_coordinates_nm": {
                "x": self.x_values.tolist(),
                "y": self.y_values.tolist(),
                "bottom_z": self.bottom_z_values.tolist(),
                "top_z": self.top_z_values.tolist(),
            },
            "axis_cells": {
                "x": len(self.x_values) - 1,
                "y": len(self.y_values) - 1,
                "bottom_z": len(self.bottom_z_values) - 1,
                "top_z": len(self.top_z_values) - 1,
            },
            "mesh_cells": self.mesh_cells,
            "certificate": self.certificate(),
        }


def _validate_reference_h(reference_h_nm: float) -> float:
    value = float(reference_h_nm)
    if not any(np.isclose(value, allowed) for allowed in MAIN_REFERENCE_LEVELS_NM):
        raise AdaptiveMeshContractError(
            "The Task033 graded feasibility runner accepts only the h5 and h3 main references."
        )
    return value


def build_physics_informed_graded_plan(
    *,
    reference_h_nm: float,
    geometry: Task033Stage4Geometry | None = None,
    coarse_factor: float = 2.0,
    max_neighbor_ratio: float = 2.0,
    feature_planes_y_nm: Sequence[float] = (),
) -> PeriodicGradedHybridPlan:
    """Build the explicit-opt-in cycle-0 p2 graded plan for h5 or h3."""

    reference_h = _validate_reference_h(reference_h_nm)
    if coarse_factor <= 1.0 or not np.isfinite(coarse_factor):
        raise AdaptiveMeshContractError("coarse_factor must be finite and greater than one.")
    geometry = geometry or Task033Stage4Geometry()
    geometry.validate()
    coarse_h = coarse_factor * reference_h
    x_parent = fitted_axis(
        geometry.x_min_nm,
        geometry.x_max_nm,
        coarse_h,
        required_planes_nm=(geometry.grating_x_min_nm, geometry.grating_x_max_nm),
        min_cells=2,
    )
    y_parent = fitted_axis(
        geometry.y_min_nm,
        geometry.y_max_nm,
        coarse_h,
        required_planes_nm=feature_planes_y_nm,
        min_cells=2,
    )
    bottom_parent = fitted_axis(
        geometry.bottom_external_z_nm,
        geometry.bottom_interface_z_nm,
        coarse_h,
        required_planes_nm=(geometry.grating_z_min_nm,),
    )
    top_parent = fitted_axis(
        geometry.top_interface_z_nm,
        geometry.top_external_z_nm,
        coarse_h,
        required_planes_nm=(geometry.grating_z_max_nm,),
    )
    x_marks = mark_axis_intervals_near_planes(
        x_parent,
        (geometry.grating_x_min_nm, geometry.grating_x_max_nm),
        radius_nm=reference_h,
    )
    y_marks = mark_axis_intervals_near_planes(
        y_parent,
        feature_planes_y_nm,
        radius_nm=reference_h,
    )
    bottom_marks = mark_axis_intervals_near_planes(
        bottom_parent,
        (
            geometry.bottom_external_z_nm,
            geometry.grating_z_min_nm,
            geometry.bottom_interface_z_nm,
        ),
        radius_nm=reference_h,
    )
    top_marks = mark_axis_intervals_near_planes(
        top_parent,
        (
            geometry.top_interface_z_nm,
            geometry.grating_z_max_nm,
            geometry.top_external_z_nm,
        ),
        radius_nm=reference_h,
    )
    plan = PeriodicGradedHybridPlan(
        geometry=geometry,
        reference_h_nm=reference_h,
        cycle=0,
        x_values=refine_marked_axis(
            x_parent,
            x_marks,
            periodic=True,
            max_neighbor_ratio=max_neighbor_ratio,
        ),
        y_values=refine_marked_axis(
            y_parent,
            y_marks,
            periodic=True,
            max_neighbor_ratio=max_neighbor_ratio,
        ),
        bottom_z_values=refine_marked_axis(
            bottom_parent,
            bottom_marks,
            periodic=False,
            max_neighbor_ratio=max_neighbor_ratio,
        ),
        top_z_values=refine_marked_axis(
            top_parent,
            top_marks,
            periodic=False,
            max_neighbor_ratio=max_neighbor_ratio,
        ),
        policy="physics_informed_conforming_tensor_rebuild",
        explicit_y_feature_planes_present=bool(feature_planes_y_nm),
        max_neighbor_ratio=float(max_neighbor_ratio),
    )
    if not plan.certificate()["eligible_for_mesh_smoke"]:
        raise AdaptiveMeshContractError("The generated plan failed its mesh certificate.")
    return plan


def _indicator_shapes(plan: PeriodicGradedHybridPlan) -> tuple[tuple[int, ...], tuple[int, ...]]:
    nx = len(plan.x_values) - 1
    ny = len(plan.y_values) - 1
    return (
        (nx, ny, len(plan.bottom_z_values) - 1),
        (nx, ny, len(plan.top_z_values) - 1),
    )


def rebuild_from_cell_indicators(
    plan: PeriodicGradedHybridPlan,
    *,
    bottom_indicator: np.ndarray,
    top_indicator: np.ndarray,
    theta: float = 0.5,
    max_total_cells: int = 2_000_000,
) -> PeriodicGradedHybridPlan:
    """Perform one solve-indicator-rebuild step on the conforming tensor grid."""

    bottom_shape, top_shape = _indicator_shapes(plan)
    bottom_values = np.asarray(bottom_indicator, dtype=np.float64)
    top_values = np.asarray(top_indicator, dtype=np.float64)
    if bottom_values.shape != bottom_shape or top_values.shape != top_shape:
        raise AdaptiveMeshContractError(
            f"Indicator shapes must be {bottom_shape} and {top_shape}."
        )
    if float(np.sum(bottom_values)) + float(np.sum(top_values)) <= 0.0:
        raise AdaptiveMeshContractError("At least one positive indicator is required to rebuild.")
    bottom_marks = synchronize_periodic_cell_marks(
        dorfler_mark(bottom_values, theta=theta)
    )
    top_marks = synchronize_periodic_cell_marks(dorfler_mark(top_values, theta=theta))
    x_marks = np.any(bottom_marks, axis=(1, 2)) | np.any(top_marks, axis=(1, 2))
    y_marks = np.any(bottom_marks, axis=(0, 2)) | np.any(top_marks, axis=(0, 2))
    bottom_z_marks = np.any(bottom_marks, axis=(0, 1))
    top_z_marks = np.any(top_marks, axis=(0, 1))
    candidate = PeriodicGradedHybridPlan(
        geometry=plan.geometry,
        reference_h_nm=plan.reference_h_nm,
        cycle=plan.cycle + 1,
        x_values=refine_marked_axis(
            plan.x_values,
            x_marks,
            periodic=True,
            max_neighbor_ratio=plan.max_neighbor_ratio,
        ),
        y_values=refine_marked_axis(
            plan.y_values,
            y_marks,
            periodic=True,
            max_neighbor_ratio=plan.max_neighbor_ratio,
        ),
        bottom_z_values=refine_marked_axis(
            plan.bottom_z_values,
            bottom_z_marks,
            periodic=False,
            max_neighbor_ratio=plan.max_neighbor_ratio,
        ),
        top_z_values=refine_marked_axis(
            plan.top_z_values,
            top_z_marks,
            periodic=False,
            max_neighbor_ratio=plan.max_neighbor_ratio,
        ),
        policy="residual_jump_conforming_tensor_rebuild",
        parent_plan_hash=plan.plan_hash,
        explicit_y_feature_planes_present=plan.explicit_y_feature_planes_present,
        max_neighbor_ratio=plan.max_neighbor_ratio,
    )
    if candidate.mesh_cells["total"] > int(max_total_cells):
        raise AdaptiveMeshBudgetError(
            f"Rebuild predicts {candidate.mesh_cells['total']} cells, above the "
            f"{max_total_cells} fail-closed cap."
        )
    if not candidate.certificate()["eligible_for_mesh_smoke"]:
        raise AdaptiveMeshContractError("The rebuilt plan failed its mesh certificate.")
    return candidate


def uniform_reference_mesh_cells(
    reference_h_nm: float,
    *,
    geometry: Task033Stage4Geometry | None = None,
) -> int:
    reference_h = _validate_reference_h(reference_h_nm)
    geometry = geometry or Task033Stage4Geometry()
    geometry.validate()
    x_axis = fitted_axis(
        geometry.x_min_nm,
        geometry.x_max_nm,
        reference_h,
        required_planes_nm=(geometry.grating_x_min_nm, geometry.grating_x_max_nm),
        min_cells=2,
    )
    y_axis = fitted_axis(
        geometry.y_min_nm,
        geometry.y_max_nm,
        reference_h,
        min_cells=2,
    )
    bottom_axis = fitted_axis(
        geometry.bottom_external_z_nm,
        geometry.bottom_interface_z_nm,
        reference_h,
        required_planes_nm=(geometry.grating_z_min_nm,),
    )
    top_axis = fitted_axis(
        geometry.top_interface_z_nm,
        geometry.top_external_z_nm,
        reference_h,
        required_planes_nm=(geometry.grating_z_max_nm,),
    )
    return int(
        (len(x_axis) - 1)
        * (len(y_axis) - 1)
        * ((len(bottom_axis) - 1) + (len(top_axis) - 1))
    )


def compression_classification(compression: float) -> str:
    if compression >= 5.0:
        return "strong_preferred_target"
    if compression >= 3.0:
        return "combined_engineering_target"
    if compression >= 2.0:
        return "clear_success"
    if compression >= 1.3:
        return "useful_engineering_positive"
    return "weak_signal"


def _required(mapping: Mapping[str, Any], key: str) -> Any:
    if key not in mapping or mapping[key] is None:
        raise AdaptiveMeshContractError(f"Missing required evidence field: {key}")
    return mapping[key]


def _is_full_git_sha(value: str) -> bool:
    return len(value) == 40 and all(character in "0123456789abcdef" for character in value.lower())


def qualify_same_accuracy_candidate(
    *,
    plan: PeriodicGradedHybridPlan,
    reference: Mapping[str, Any] | None,
    candidate: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Apply the Task033 h5/h3 accuracy gates and fail closed on missing evidence."""

    reasons: list[str] = []
    if reference is None or candidate is None:
        return {
            "status": "not_qualified_missing_evidence",
            "data_identity": "not_run",
            "mandatory_gate_pass": False,
            "strong_gate_pass": False,
            "compression": None,
            "compression_unit": "dimensionless_local_fe_row_ratio",
            "compression_baseline": f"uniform_p2_h{plan.reference_h_nm:g}",
            "compression_denominator": "candidate_local_fe_rows",
            "compression_classification": None,
            "reasons": ["reference_and_candidate_measured_records_are_required"],
        }
    try:
        reference_identity = str(_required(reference, "data_identity"))
        candidate_identity = str(_required(candidate, "data_identity"))
        reference_clean = bool(_required(reference, "source_clean"))
        candidate_clean = bool(_required(candidate, "source_clean"))
        reference_degree = int(_required(reference, "degree"))
        candidate_degree = int(_required(candidate, "degree"))
        reference_h = float(_required(reference, "h_nm"))
        reference_rows = int(_required(reference, "local_fe_rows"))
        candidate_rows = int(_required(candidate, "local_fe_rows"))
        full_field_available = bool(_required(reference, "full_field_available"))
        modal_gate = bool(_required(candidate, "modal_truncation_gate_pass"))
        reference_commit = str(_required(reference, "source_commit"))
        candidate_commit = str(_required(candidate, "source_commit"))
        reference_physics = str(_required(reference, "physics_signature"))
        candidate_physics = str(_required(candidate, "physics_signature"))
        candidate_plan_hash = str(_required(candidate, "mesh_plan_hash"))
        metrics = {key: float(_required(candidate, key)) for key in MANDATORY_GATES}
    except (AdaptiveMeshContractError, TypeError, ValueError) as exc:
        return {
            "status": "not_qualified_invalid_evidence",
            "data_identity": "not_qualified",
            "mandatory_gate_pass": False,
            "strong_gate_pass": False,
            "compression": None,
            "compression_unit": "dimensionless_local_fe_row_ratio",
            "compression_baseline": f"uniform_p2_h{plan.reference_h_nm:g}",
            "compression_denominator": "candidate_local_fe_rows",
            "compression_classification": None,
            "reasons": [str(exc)],
        }
    if reference_identity != "measured" or candidate_identity != "measured":
        reasons.append("both_records_must_be_measured")
    if not reference_clean or not candidate_clean:
        reasons.append("both_records_must_come_from_tracked_source_clean_commits")
    if not _is_full_git_sha(reference_commit) or not _is_full_git_sha(candidate_commit):
        reasons.append("both_records_require_full_git_source_commits")
    if not reference_physics or not candidate_physics or reference_physics != candidate_physics:
        reasons.append("reference_and_candidate_physics_signatures_differ")
    if candidate_plan_hash != plan.plan_hash:
        reasons.append("candidate_record_is_not_bound_to_this_mesh_plan")
    if reference_degree != 2 or candidate_degree != 2:
        reasons.append("task033_h_adaptive_path_is_fixed_p2")
    if not np.isclose(reference_h, plan.reference_h_nm):
        reasons.append("reference_h_does_not_match_mesh_plan")
    if reference_rows <= 0 or candidate_rows <= 0:
        reasons.append("local_fe_rows_must_be_positive")
    if not full_field_available:
        reasons.append("h5_h3_reference_requires_full_field_evidence")
    if not modal_gate:
        reasons.append("modal_truncation_gate_failed_or_missing")
    certificate = plan.certificate()
    if not certificate["eligible_for_mesh_smoke"]:
        reasons.append("mesh_certificate_failed")
    for metric, limit in MANDATORY_GATES.items():
        value = metrics[metric]
        if not np.isfinite(value) or value < 0.0 or value > limit:
            reasons.append(f"{metric}_exceeds_{limit:.12g}")
    compression = (
        float(reference_rows / candidate_rows)
        if reference_rows > 0 and candidate_rows > 0
        else None
    )
    mandatory_pass = not reasons
    strong_pass = mandatory_pass and all(
        metrics[metric] <= limit for metric, limit in STRONG_GATES.items()
    )
    status = (
        "same_accuracy_strong_gate_pass"
        if strong_pass
        else "same_accuracy_mandatory_gate_pass"
        if mandatory_pass
        else "not_qualified_gate_failure"
    )
    return {
        "status": status,
        "data_identity": (
            "derived_from_clean_measured_reference_and_candidate"
            if mandatory_pass
            else "not_qualified"
        ),
        "mandatory_gate_pass": mandatory_pass,
        "strong_gate_pass": strong_pass,
        "compression": compression,
        "compression_unit": "dimensionless_local_fe_row_ratio",
        "compression_baseline": f"uniform_p2_h{plan.reference_h_nm:g}",
        "compression_denominator": "candidate_local_fe_rows",
        "compression_classification": (
            compression_classification(compression) if compression is not None else None
        ),
        "reference_local_fe_rows": reference_rows,
        "candidate_local_fe_rows": candidate_rows,
        "metrics": metrics,
        "limits": {"mandatory": MANDATORY_GATES, "strong": STRONG_GATES},
        "reasons": reasons,
    }


def build_adaptive_planning_record(
    plan: PeriodicGradedHybridPlan,
    *,
    reference_evidence: Mapping[str, Any] | None = None,
    candidate_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    uniform_cells = uniform_reference_mesh_cells(
        plan.reference_h_nm,
        geometry=plan.geometry,
    )
    planned_cells = plan.mesh_cells["total"]
    qualification = qualify_same_accuracy_candidate(
        plan=plan,
        reference=reference_evidence,
        candidate=candidate_evidence,
    )
    accuracy_measured = bool(qualification["mandatory_gate_pass"])
    return {
        "schema_version": 1,
        "task_id": "Task033",
        "case_id": "091_hybrid_hp_adaptivity_feasibility",
        "record_type": "p2_periodic_graded_mesh_plan",
        "status": (
            "measured_same_accuracy_qualification_attached"
            if accuracy_measured
            else "plan_only_no_pde_run"
        ),
        "identity": {
            "deterministic": True,
            "is_pde_run": False,
            "is_solver_pass": False,
            "is_adaptive_compression_measurement": accuracy_measured,
            "ordinary_default_changed": False,
            "explicit_opt_in": True,
            "proves_0p7nm_feasible": False,
        },
        "plan": plan.to_record(),
        "derived_mesh_cell_comparison": {
            "data_identity": "derived_from_axis_coordinate_counts",
            "unit": "hexahedral_cells",
            "baseline": f"uniform_fitted_p2_h{plan.reference_h_nm:g}",
            "denominator": "graded_plan_cells",
            "evidence_record": plan.plan_hash,
            "uniform_reference_cells": uniform_cells,
            "graded_plan_cells": planned_cells,
            "mesh_cell_compression_only": float(uniform_cells / planned_cells),
            "accuracy_qualified": False,
            "warning": "Mesh-cell compression is not local-DoF same-accuracy compression.",
        },
        "same_accuracy_qualification": qualification,
        "algorithm_boundaries": {
            "mesh_family": "nonuniform_graded_conforming_hexahedral_tensor_product",
            "periodic_policy": "opposite_cell_marks_union_then_common_axis_rebuild",
            "interface_policy": "bottom_and_top_share_exact_x_y_axis_arrays",
            "hanging_nodes": "not_used",
            "cellwise_variable_p": "not_used",
            "indicator_ladder": [
                "physics_informed_geometry_planes",
                "element_residual_plus_tangential_curl_jump",
            ],
            "dwr": "not_implemented_in_this_minimal_path",
            "generic_y_material": (
                "explicit_feature_planes_supported_but_generic_material_not_qualified"
                if plan.explicit_y_feature_planes_present
                else "not_qualified_fail_closed"
            ),
        },
    }


def build_task033_graded_local_mesh_pair(
    cfg: object,
    plan: PeriodicGradedHybridPlan,
    *,
    comm: object | None = None,
) -> tuple[object, object]:
    """Materialize the certified plan in DOLFINx; imports stay runtime-local."""

    if int(getattr(cfg, "nedelec_degree")) != 2:
        raise AdaptiveMeshContractError("This Task033 adaptive path is fixed to p=2.")
    if str(getattr(cfg, "geometry_kind")) != "rectangular_block_grating":
        raise AdaptiveMeshContractError("The graded local mesh requires Stage-4 block geometry.")
    if not bool(getattr(cfg, "use_floquet_xy")):
        raise AdaptiveMeshContractError("Double Floquet boundaries must be enabled.")
    if str(getattr(cfg, "mesh_cell_type_resolved")) != "hexahedron":
        raise AdaptiveMeshContractError("The graded path requires conforming hexahedra.")
    expected_geometry = Task033Stage4Geometry.from_config(cfg)
    for field_name in expected_geometry.__dataclass_fields__:
        expected = float(getattr(expected_geometry, field_name))
        actual = float(getattr(plan.geometry, field_name))
        if not np.isclose(expected, actual, atol=1.0e-10, rtol=0.0):
            raise AdaptiveMeshContractError(
                f"Plan/config geometry mismatch for {field_name}: {actual:g} != {expected:g}."
            )
    certificate = plan.certificate()
    if not certificate["eligible_for_mesh_smoke"]:
        raise AdaptiveMeshContractError("Refusing to build an uncertified graded mesh.")

    from mpi4py import MPI

    from .hybrid_local_mesh import HybridLocalMesh, _local_boundary_tags
    from .mesh_builder_3d import AirBox3DMesh, _axis_stats, _mark_cells, _structured_hexa_mesh

    mesh_comm = MPI.COMM_WORLD if comm is None else comm

    def build_side(side: str, z_values: np.ndarray) -> object:
        msh = _structured_hexa_mesh(
            mesh_comm,
            plan.x_values,
            plan.y_values,
            z_values,
        )
        msh.name = f"{getattr(cfg, 'case_name')}_{side}_task033_graded"
        msh.topology.create_connectivity(msh.topology.dim - 1, msh.topology.dim)
        cell_tags = _mark_cells(msh, cfg)
        facet_tags, boundary_facets = _local_boundary_tags(
            msh,
            cfg,
            z_min=float(z_values[0]),
            z_max=float(z_values[-1]),
        )
        if side == "bottom":
            interface_z = plan.geometry.bottom_interface_z_nm
            external_z = plan.geometry.bottom_external_z_nm
            interface_tag = getattr(cfg, "tags").z_max
            external_tag = getattr(cfg, "tags").z_min
            local_normal_sign = +1
        else:
            interface_z = plan.geometry.top_interface_z_nm
            external_z = plan.geometry.top_external_z_nm
            interface_tag = getattr(cfg, "tags").z_min
            external_tag = getattr(cfg, "tags").z_max
            local_normal_sign = -1
        nx = len(plan.x_values) - 1
        ny = len(plan.y_values) - 1
        mesh_cells = (nx, ny, len(z_values) - 1)
        mesh_data = AirBox3DMesh(
            mesh=msh,
            cell_tags=cell_tags,
            facet_tags=facet_tags,
            boundary_facets=boundary_facets,
            mesh_cell_type_resolved="hexahedron",
            mesh_cells_resolved=mesh_cells,
            z_alignment_warnings=[],
            mesh_spacing_mode_resolved="task033_periodic_graded_rebuild",
            mesh_axis_cell_stats={
                "x": _axis_stats(plan.x_values),
                "y": _axis_stats(plan.y_values),
                "z": _axis_stats(z_values),
            },
            material_plane_alignment={
                "all_aligned": True,
                "source": "Task033 graded-plan certificate",
            },
            local_refinement_regions={"x": [], "y": [], "z": []},
        )
        fdim = msh.topology.dim - 1
        owned_facets = msh.topology.index_map(fdim).size_local
        interface_owned = facet_tags.find(interface_tag)
        interface_owned = interface_owned[interface_owned < owned_facets]
        external_owned = facet_tags.find(external_tag)
        external_owned = external_owned[external_owned < owned_facets]
        global_interface = int(mesh_comm.allreduce(len(interface_owned), op=MPI.SUM))
        global_external = int(mesh_comm.allreduce(len(external_owned), op=MPI.SUM))
        expected_facets = nx * ny
        if global_interface != expected_facets or global_external != expected_facets:
            raise RuntimeError(
                f"{side} interface/external facets {global_interface}/{global_external} "
                f"do not match {expected_facets}."
            )
        return HybridLocalMesh(
            side=side,
            mesh_data=mesh_data,
            z_values=z_values,
            interface_z_nm=interface_z,
            external_z_nm=external_z,
            interface_facet_tag=interface_tag,
            external_facet_tag=external_tag,
            local_interface_outward_normal_sign=local_normal_sign,
            modal_interface_outward_normal_sign=-local_normal_sign,
            global_interface_facet_count=global_interface,
            global_external_facet_count=global_external,
        )

    return (
        build_side("bottom", plan.bottom_z_values),
        build_side("top", plan.top_z_values),
    )
