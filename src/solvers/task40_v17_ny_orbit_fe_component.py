"""Source-tracked adapter for the isolated real-Basix/DOLFINx Ny=8 witness.

This module composes the V17 orbit transport with the already-qualified p6
native entity collector. It does not alter the Ny=4 production solver, build a
global matrix, construct a numeric factor, or start a KSP.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from .task40_v17_ny_orbit import (
    MAPPING_LIMIT,
    TwoCellNyOrbitTransport,
    assign_ny_orbit_sectors,
)

OPERATOR_LIMIT = 1e-11


def _space(setup: Mapping[str, Any], role: str) -> tuple[Any, Any]:
    try:
        return setup["spaces"][6], setup["floquets"][6]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"{role} setup must contain actual p6 space and Floquet MPC") from exc


def _axes_values(axes: Mapping[str, Any], role: str) -> dict[str, np.ndarray]:
    result = {}
    for name in ("x", "y", "z"):
        try:
            values = np.asarray(axes[name], dtype=np.float64)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{role} axes must provide numeric {name} coordinates") from exc
        if values.ndim != 1 or values.size < 2 or not np.isfinite(values).all() or np.any(np.diff(values) <= 0):
            raise ValueError(f"{role} {name} coordinates must be finite and strictly increasing")
        result[name] = values
    return result


def _max_relative_metric_difference(actual: Any, expected: Any, *, role: str) -> float:
    actual_values = np.asarray(actual, dtype=np.float64)
    expected_values = np.asarray(expected, dtype=np.float64)
    if (
        actual_values.shape != expected_values.shape
        or actual_values.size == 0
        or not np.isfinite(actual_values).all()
        or not np.isfinite(expected_values).all()
        or np.any(expected_values == 0.0)
    ):
        raise ValueError(f"{role} metric vectors must be matching finite nonzero arrays")
    relative = np.abs(actual_values - expected_values) / np.abs(expected_values)
    return float(np.max(relative, initial=0.0))


def _coordinate_comparison(actual: Any, expected: Any, *, scale: float, role: str) -> dict[str, Any]:
    actual_values = np.asarray(actual, dtype=np.float64)
    expected_values = np.asarray(expected, dtype=np.float64)
    if (
        actual_values.shape != expected_values.shape
        or actual_values.size == 0
        or not np.isfinite(actual_values).all()
        or not np.isfinite(expected_values).all()
        or not np.isfinite(scale)
        or scale <= 0.0
    ):
        raise ValueError(f"{role} coordinates must be matching finite arrays with a positive metric scale")
    maximum_absolute_difference = float(
        np.max(np.abs(actual_values - expected_values), initial=0.0)
    )
    return {
        "bitwise_equal": bool(np.array_equal(actual_values, expected_values)),
        "maximum_absolute_difference": maximum_absolute_difference,
        "maximum_relative_metric_difference": maximum_absolute_difference / scale,
    }


@dataclass(frozen=True)
class NativeNy8Sector:
    """One actual two-cell local FE map and its V17 twist transport."""

    context: Any
    entities: Any
    transport: TwoCellNyOrbitTransport
    modes: tuple[Any, ...]
    geometry_audit: Mapping[str, Any]

    def audit(self) -> dict[str, Any]:
        return {
            **self.context.audit(),
            "actual_local_independent_rows": int(len(self.entities.independent)),
            "actual_local_storage_rows": int(self.entities.full_rows),
            "actual_local_dimension_counts": {
                str(key): int(value) for key, value in self.entities.dimension_counts.items()
            },
            "native_entity_transform_bank_shared": True,
            "geometry_audit": dict(self.geometry_audit),
            "transport": dict(self.transport.audit),
        }


@dataclass(frozen=True)
class NativeNy8OrbitComponent:
    """Actual global/local native maps read from the p6 FE spaces."""

    entities: Any
    sectors: tuple[NativeNy8Sector, ...]
    mode_count: int
    geometry_audit: Mapping[str, Any]

    def audit(self) -> dict[str, Any]:
        q_counts = [0] * 8
        for sector in self.sectors:
            for branch, q in enumerate(sector.context.global_q_indices):
                q_counts[int(q)] = int(sector.context.q_counts[branch])
        return {
            "schema": "task40extra.review_v17_native_ny8_fe_maps.v1",
            "global_y_cells_Ny": int(self.entities.ny),
            "local_y_cells_ell": 2,
            "translation_count_K": len(self.sectors),
            "actual_global_independent_rows": int(len(self.entities.independent)),
            "actual_global_storage_rows": int(self.entities.full_rows),
            "actual_global_dimension_counts": {
                str(key): int(value) for key, value in self.entities.dimension_counts.items()
            },
            "mode_count": int(self.mode_count),
            "global_q_counts": q_counts,
            "global_q_coverage": sorted(
                q for sector in self.sectors for q in sector.context.global_q_indices
            ),
            "all_global_q_nonempty": all(value > 0 for value in q_counts),
            "all_ordered_modes_covered_once": True,
            "mapping_limit": MAPPING_LIMIT,
            "native_entity_transform_bank_shared": True,
            "sectors": [sector.audit() for sector in self.sectors],
            "global_y_widths": np.asarray(self.entities.y_widths, dtype=np.float64).tolist(),
            "geometry_audit": dict(self.geometry_audit),
        }


def build_native_ny8_orbit_component(
    *,
    full_setup: Mapping[str, Any],
    local_cases: Sequence[Mapping[str, Any]],
    cfg: Any,
    full_axes: Mapping[str, Any],
    modes: Sequence[Any],
    transform_bank: Any,
) -> NativeNy8OrbitComponent:
    """Collect real p6 Basix/dofmap maps for Ny=8, ell=2, K=4.

    ``local_cases[b]`` contains the actual local ``setup``, its two-cell
    ``axes``, and the ordered global mode indices/mode objects supplied to its
    regular-reference action. The same qualified transform bank must own the
    global space and all four local spaces.
    """
    if transform_bank is None:
        raise ValueError("Ny8 FE collection requires the existing shared p6 transform bank")
    if len(local_cases) != 4:
        raise ValueError("Ny8 FE collection requires all four actual local twist spaces")
    if not modes:
        raise ValueError("Ny8 FE collection requires the complete frozen physical mode inventory")
    full_space, full_floquet = _space(full_setup, "global")
    global_axes = _axes_values(full_axes, "global")
    if len(global_axes["y"]) != 9:
        raise ValueError("Ny8 global FE axes must read back exactly eight y cells")
    global_dy = np.diff(global_axes["y"])
    global_width_reference = np.full(8, global_dy[0], dtype=np.float64)
    global_width_relative_difference = _max_relative_metric_difference(
        global_dy, global_width_reference, role="global y-width"
    )
    if global_width_relative_difference > MAPPING_LIMIT:
        raise ValueError("Ny8 global y widths must be uniform within the original mapping gate")
    global_widths_bitwise_equal = bool(np.array_equal(global_dy, global_width_reference))
    period_y = float(cfg.period_y)
    if not np.isfinite(period_y) or period_y <= 0.0:
        raise ValueError("Ny8 physical y period must be finite and positive")
    global_period = float(global_axes["y"][-1] - global_axes["y"][0])
    period_relative_difference = abs(global_period - period_y) / abs(period_y)
    if period_relative_difference > MAPPING_LIMIT:
        raise ValueError("Ny8 global y-axis must preserve the frozen physical period within the mapping gate")

    from .task40_v10_p6_yorbit import collect_y_orbit_entities

    full_entities = collect_y_orbit_entities(
        full_space, full_floquet, cfg, global_axes, transform_bank=transform_bank
    )
    if (
        int(full_entities.ny) != 8
        or any(int(full_entities.dimension_counts.get(dim, 0)) <= 0 for dim in (1, 2, 3))
        or getattr(full_entities, "_transform_bank", None) is not transform_bank
    ):
        raise ValueError("actual global p6 entity map is incomplete or did not borrow the shared bank")
    global_entity_metric_difference = _max_relative_metric_difference(
        full_entities.y_widths, global_dy, role="global entity y-width"
    )
    if global_entity_metric_difference > MAPPING_LIMIT:
        raise ValueError("global p6 entity-map widths do not preserve the actual global y-axis metric")

    sectors = assign_ny_orbit_sectors(
        modes,
        ky=complex(cfg.ky),
        period_y=float(cfg.period_y),
        cell_width_y=float(global_dy[0]),
        global_y_cells=int(full_entities.ny),
        local_y_cells=2,
        tolerance=MAPPING_LIMIT,
    )
    if len(sectors) != 4 or any(not count for sector in sectors for count in sector.q_counts):
        raise ValueError("actual 532-mode Ny8 inventory must populate all eight global q branches")
    local_width_reference = global_dy[:2]
    local_window_scale = float(global_axes["y"][2] - global_axes["y"][0])
    global_geometry_audit = {
        "mapping_limit": MAPPING_LIMIT,
        "global_y_widths_bitwise_equal_to_first_width": global_widths_bitwise_equal,
        "global_y_widths_max_relative_metric_difference": global_width_relative_difference,
        "global_y_entity_widths_max_relative_metric_difference": global_entity_metric_difference,
        "global_y_period_relative_difference": period_relative_difference,
        "global_y_coordinates": global_axes["y"].tolist(),
        "global_y_widths": global_dy.tolist(),
    }
    native_sectors = []
    for twist, (context, case) in enumerate(zip(sectors, local_cases, strict=True)):
        if int(context.twist_index) != twist:
            raise ValueError("actual local FE cases must be ordered by twist b=0,1,2,3")
        local_space, local_floquet = _space(case["setup"], f"twist {twist}")
        local_axes = _axes_values(case["axes"], f"twist {twist}")
        if len(local_axes["y"]) != 3:
            raise ValueError("each local FE mesh must contain exactly the first two global y cells")
        local_y_comparison = _coordinate_comparison(
            local_axes["y"], global_axes["y"][:3], scale=local_window_scale,
            role=f"twist {twist} first-window y",
        )
        local_widths = np.diff(local_axes["y"])
        local_width_relative_difference = _max_relative_metric_difference(
            local_widths, local_width_reference, role=f"twist {twist} y-width"
        )
        if (
            local_y_comparison["maximum_relative_metric_difference"] > MAPPING_LIMIT
            or local_width_relative_difference > MAPPING_LIMIT
            or not np.array_equal(local_axes["x"], global_axes["x"])
            or not np.array_equal(local_axes["z"], global_axes["z"])
        ):
            raise ValueError("each local FE mesh must map to the actual first two-cell x/z-preserving window")
        try:
            local_phase = complex(case["cfg"].floquet_phase_y)
        except (KeyError, AttributeError, TypeError, ValueError) as exc:
            raise ValueError(f"twist {twist} local config must provide its actual Floquet y phase") from exc
        if not np.isfinite(local_phase) or abs(local_phase - context.tau) > MAPPING_LIMIT:
            raise ValueError(f"twist {twist} local Floquet y phase does not equal its assigned tau")
        expected_indices = np.asarray(context.original_mode_indices, dtype=np.int64)
        supplied_indices = np.asarray(case["global_mode_indices"], dtype=np.int64)
        supplied_modes = tuple(case["modes"])
        expected_modes = tuple(modes[int(index)] for index in expected_indices)
        if (
            not np.array_equal(supplied_indices, expected_indices)
            or len(supplied_modes) != len(expected_modes)
            or any(actual is not expected for actual, expected in zip(supplied_modes, expected_modes, strict=True))
        ):
            raise ValueError("local regular-reference modes do not match the frozen ordered q-sector slice")
        local_entities = collect_y_orbit_entities(
            local_space, local_floquet, case["cfg"], local_axes,
            transform_bank=transform_bank,
        )
        if (
            int(local_entities.ny) != 2
            or any(int(local_entities.dimension_counts.get(dim, 0)) <= 0 for dim in (1, 2, 3))
            or getattr(local_entities, "_transform_bank", None) is not transform_bank
        ):
            raise ValueError(f"actual twist {twist} p6 entity map is incomplete or did not borrow the shared bank")
        local_entity_metric_difference = _max_relative_metric_difference(
            local_entities.y_widths, local_widths, role=f"twist {twist} entity y-width"
        )
        if local_entity_metric_difference > MAPPING_LIMIT:
            raise ValueError(f"twist {twist} p6 entity-map widths do not preserve its actual y-axis metric")
        transport = TwoCellNyOrbitTransport(
            full_entities, local_entities, twist_index=twist,
            eta=context.eta, cfg=cfg, local_y_cells=2,
        )
        native_sectors.append(
            NativeNy8Sector(
                context, local_entities, transport, supplied_modes,
                {
                    "first_window_y_coordinates": local_y_comparison,
                    "local_y_widths_bitwise_equal_to_global_first_window": bool(
                        np.array_equal(local_widths, local_width_reference)
                    ),
                    "local_y_widths_max_relative_metric_difference": local_width_relative_difference,
                    "local_y_entity_widths_max_relative_metric_difference": local_entity_metric_difference,
                    "local_floquet_phase_relative_difference": float(
                        abs(local_phase - context.tau) / max(abs(context.tau), np.finfo(float).tiny)
                    ),
                },
            )
        )

    covered = np.concatenate([sector.original_mode_indices for sector in sectors])
    if not np.array_equal(np.sort(covered), np.arange(len(modes), dtype=np.int64)):
        raise ValueError("actual FE twist maps do not cover every ordered physical mode exactly once")
    if len(np.unique(covered)) != len(modes):
        raise ValueError("actual FE twist maps assign a physical mode more than once")
    return NativeNy8OrbitComponent(
        full_entities, tuple(native_sectors), len(modes), global_geometry_audit
    )


def combine_native_regular_actions(
    component: NativeNy8OrbitComponent,
    *,
    full_action: Callable[[np.ndarray], Any],
    local_actions: Sequence[Callable[[np.ndarray], Any]],
    full_vectors: Sequence[Any],
    tolerance: float = OPERATOR_LIMIT,
) -> dict[str, Any]:
    """Compare actual full and four-sector matrix-free regular-reference actions.

    Callbacks receive/return complex128 vectors in each FE map's independent
    native rows. The combined action extracts each primal twist, applies that
    twist's actual local FE action, lifts its dual result, and sums all four
    contributions. This is a finite deterministic action witness, not a claim
    that every possible operator column was enumerated.
    """
    if not callable(full_action) or len(local_actions) != 4 or not all(map(callable, local_actions)):
        raise ValueError("native Ny8 action comparison requires one full and four local actions")
    if not full_vectors:
        raise ValueError("native Ny8 action comparison requires at least one fixed probe vector")
    if not np.isfinite(tolerance) or tolerance <= 0:
        raise ValueError("operator tolerance must be finite and positive")
    records = []
    full_results = []
    combined_results = []
    differences = []
    for probe_index, raw_vector in enumerate(full_vectors):
        vector = np.asarray(raw_vector)
        if (
            vector.dtype != np.dtype(np.complex128)
            or vector.shape != (len(component.entities.independent),)
            or not np.isfinite(vector).all()
        ):
            raise ValueError("each full regular-action probe must be a finite complex128 native vector")
        full_result = np.asarray(full_action(vector))
        if (
            full_result.dtype != np.dtype(np.complex128)
            or full_result.shape != vector.shape
            or not np.isfinite(full_result).all()
        ):
            raise ValueError("full FE action must return a finite complex128 independent-row dual vector")
        combined = np.zeros_like(full_result)
        for sector, action in zip(component.sectors, local_actions, strict=True):
            local_primal = sector.transport.extract_primal(vector)
            local_result = np.asarray(action(local_primal))
            if (
                local_result.dtype != np.dtype(np.complex128)
                or local_result.shape != (len(sector.entities.independent),)
                or not np.isfinite(local_result).all()
            ):
                raise ValueError("local FE action must return a finite complex128 independent-row dual vector")
            combined += sector.transport.lift_dual(local_result)
        difference = np.asarray(full_result - combined, dtype=np.complex128)
        error_norm = _norm(difference)
        full_action_norm = _norm(full_result)
        combined_action_norm = _norm(combined)
        relative = error_norm / full_action_norm if full_action_norm > 0.0 else None
        passed = (
            error_norm == 0.0
            if full_action_norm == 0.0
            else relative <= tolerance
        )
        records.append({
            "probe_index": probe_index,
            "full_action_norm": full_action_norm,
            "full_action_norm_is_zero_oracle": full_action_norm == 0.0,
            "combined_action_norm": combined_action_norm,
            "defect_norm": error_norm,
            "relative_defect": relative,
            "relative_defect_denominator": "full_action_norm",
            "maximum_absolute_defect": float(np.max(np.abs(difference), initial=0.0)),
            "passed": bool(passed),
        })
        full_results.append(full_result.copy())
        combined_results.append(combined.copy())
        differences.append(difference)
    return {
        "schema": "task40extra.review_v17_native_ny8_regular_action.v1",
        "status": "PASS" if all(row["passed"] for row in records) else "FAIL",
        "operator_limit": tolerance,
        "probe_count": len(records),
        "scope": "actual matrix-free regular-reference full action versus sum of four native local twist actions",
        "probe_records": records,
        "full_action_vectors": tuple(full_results),
        "combined_action_vectors": tuple(combined_results),
        "difference_vectors": tuple(differences),
    }


def _norm(values: np.ndarray) -> float:
    magnitude = np.abs(np.asarray(values))
    return float(np.sqrt(np.sum(magnitude * magnitude, dtype=np.longdouble)))
