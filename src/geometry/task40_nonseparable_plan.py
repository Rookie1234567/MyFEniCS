from __future__ import annotations

import hashlib
import json
import math
from fractions import Fraction
from typing import Any, Mapping

TASK40_PROFILE = "task40extra_0p7nm_p6trace_p4_v1"
TASK40_COMPARISON_GROUP = "task40extra_0p7nm_nonseparable_n0_n6"
TASK40_GEOMETRY_IDENTITY = "task40extra_nonseparable_0p7nm_v1"
TASK40_RUNS = {
    "task40extra_0p7nm_nonseparable_g0_iterative_v1": "G0",
    "task40extra_0p7nm_nonseparable_g1_iterative_v1": "G1",
    "task40extra_0p7nm_nonseparable_g0_direct_reference_v1": "G0",
}
TASK40_SI_N = complex(0.9998851703688496, 4.3236152269189515e-6)
SCALE = Fraction(7, 135)


def _canonical_sha256(value: object) -> str:
    data = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _ceil_fraction(value: Fraction) -> int:
    return -(-value.numerator // value.denominator)


def _subdivide(
    points: list[Fraction], h: Fraction
) -> tuple[list[Fraction], list[int]]:
    coordinates = [points[0]]
    counts = []
    for low, high in zip(points, points[1:]):
        count = _ceil_fraction((high - low) / h)
        counts.append(count)
        coordinates.extend(
            low + (high - low) * Fraction(index, count)
            for index in range(1, count + 1)
        )
    return coordinates, counts


def _to_nm(values: list[Fraction], shift: Fraction = Fraction(0)) -> list[float]:
    return [float((value + shift) * SCALE) for value in values]


def task40_mesh_plan(mesh_id: str) -> dict[str, Any]:
    if mesh_id not in {"G0", "G1"}:
        raise ValueError(f"Unknown Task40 mesh id: {mesh_id}")
    h = Fraction(10) if mesh_id == "G0" else Fraction(15, 2)
    plane_points = {
        "x": [
            Fraction(0),
            Fraction(33, 2),
            Fraction(25),
            Fraction(67, 2),
            Fraction(50),
        ],
        "y": [Fraction(0), Fraction(25, 4), Fraction(75, 4), Fraction(25)],
        "z": [
            Fraction(-10),
            Fraction(0),
            Fraction(40),
            Fraction(80),
            Fraction(120),
            Fraction(130),
        ],
    }
    axes: dict[str, list[float]] = {}
    segment_counts: dict[str, list[int]] = {}
    for axis, points in plane_points.items():
        values, counts = _subdivide(points, h)
        axes[axis] = _to_nm(values)
        segment_counts[axis] = counts
    counts = {axis: sum(values) for axis, values in segment_counts.items()}
    payload = {
        "mesh_id": mesh_id,
        "target_h_nm": float(h * SCALE),
        "axis_segment_interval_counts": segment_counts,
        "axis_interval_counts": counts,
        "axis_coordinates_nm": axes,
        "expected_hexahedra": math.prod(counts.values()),
    }
    return {
        **payload,
        "mesh_plan_id": f"task40extra.{mesh_id.lower()}.exact_planes.v1",
        "mesh_plan_sha256": _canonical_sha256(payload),
    }


def _close(actual: Any, expected: float, *, atol: float = 1.0e-13) -> bool:
    try:
        value = float(actual)
    except (TypeError, ValueError):
        return False
    return math.isfinite(value) and math.isclose(
        value, expected, rel_tol=0.0, abs_tol=atol
    )


def validate_task40_input(config: Mapping[str, Any]) -> None:
    """Reject any Task40 run whose physical/mesh identity differs from N1."""

    run_id = str(config.get("run_id", ""))
    mesh_id = TASK40_RUNS.get(run_id)
    if mesh_id is None:
        raise ValueError("run_id is not in the explicit Task40 N3-N5 allowlist")
    if config.get("comparison_group") != TASK40_COMPARISON_GROUP:
        raise ValueError("comparison_group differs from the frozen Task40 identity")
    if config.get("dimension") != 3:
        raise ValueError("Task40 requires dimension=3")

    geometry = config.get("geometry", {})
    materials = config.get("materials", {})
    incidence = config.get("incidence", {})
    discretization = config.get("discretization", {})
    if geometry.get("geometry_kind") != "rectangular_block_grating":
        raise ValueError("Task40 requires rectangular_block_grating")
    if geometry.get("model_variant") != "original":
        raise ValueError("Task40 requires model_variant=original")
    if geometry.get("geometry_identity") != TASK40_GEOMETRY_IDENTITY:
        raise ValueError("Task40 geometry_identity differs from the frozen identity")

    s = float(SCALE)
    expected_geometry = {
        "period_x_nm": 50 * s,
        "period_y_nm": 25 * s,
        "z_min_nm": -10 * s,
        "z_max_nm": 130 * s,
        "interface_z_nm": 0.0,
        "air_height_nm": 130 * s,
        "substrate_thickness_nm": 10 * s,
        "grating_width_x_nm": 17 * s,
        "grating_width_y_nm": 25 * s,
        "grating_height_nm": 120 * s,
    }
    for key, expected in expected_geometry.items():
        if not _close(geometry.get(key), expected):
            raise ValueError(f"Task40 geometry.{key} differs from N1")
    expected_void = [
        25 * s,
        67 / 2 * s,
        25 / 4 * s,
        75 / 4 * s,
        40 * s,
        80 * s,
    ]
    actual_void = geometry.get("air_void_box_nm") or ()
    if len(actual_void) != 6 or any(
        not _close(actual, expected)
        for actual, expected in zip(actual_void, expected_void, strict=True)
    ):
        raise ValueError("Task40 air_void_box_nm differs from the exact 3D notch")

    if not _close(incidence.get("wavelength_nm"), 0.7):
        raise ValueError("Task40 wavelength must be exactly 0.7 nm")
    if not _close(incidence.get("grazing_angle_deg"), 1.0):
        raise ValueError("Task40 incidence must be 1 degree grazing")
    if not _close(incidence.get("azimuth_deg"), 0.0):
        raise ValueError("Task40 azimuth must be zero")
    if incidence.get("polarization") != "s":
        raise ValueError("Task40 incidence polarization must be s")

    def complex_pair(value: Any) -> complex | None:
        if not isinstance(value, (tuple, list)) or len(value) != 2:
            return None
        try:
            return complex(float(value[0]), float(value[1]))
        except (TypeError, ValueError):
            return None

    if complex_pair(materials.get("n_air")) != 1.0 + 0.0j:
        raise ValueError("Task40 external upper medium must be vacuum")
    for key in ("n_substrate", "n_grating"):
        value = complex_pair(materials.get(key))
        if value is None or abs(value - TASK40_SI_N) > 1.0e-14:
            raise ValueError(f"Task40 materials.{key} differs from the N1 Si record")
    if complex_pair(materials.get("mu_r")) != 1.0 + 0.0j:
        raise ValueError("Task40 requires the inherited nonmagnetic material model")

    plan = task40_mesh_plan(mesh_id)
    for key, expected in (
        ("mesh_target_nm", plan["target_h_nm"]),
        ("mesh_plan_id", plan["mesh_plan_id"]),
        ("mesh_plan_sha256", plan["mesh_plan_sha256"]),
    ):
        actual = discretization.get(key)
        if key.endswith("_nm"):
            if not _close(actual, float(expected)):
                raise ValueError(f"Task40 discretization.{key} differs from N1")
        elif actual != expected:
            raise ValueError(f"Task40 discretization.{key} differs from N1")
    if discretization.get("nedelec_degree") != 6:
        raise ValueError("Task40 requires p6")
    if tuple(discretization.get("mesh_axis_cell_counts", ())) != tuple(
        plan["axis_interval_counts"][axis] for axis in ("x", "y", "z")
    ):
        raise ValueError("Task40 tensor axis counts differ from the frozen mesh plan")
    for axis in ("x", "y", "z"):
        actual = discretization.get(f"mesh_axis_{axis}_values")
        expected = plan["axis_coordinates_nm"][axis]
        if not isinstance(actual, (tuple, list)) or len(actual) != len(expected):
            raise ValueError(f"Task40 mesh_axis_{axis}_values length differs from N1")
        if any(
            not _close(value, target, atol=1.0e-12)
            for value, target in zip(actual, expected, strict=True)
        ):
            raise ValueError(f"Task40 mesh_axis_{axis}_values differ from N1")
