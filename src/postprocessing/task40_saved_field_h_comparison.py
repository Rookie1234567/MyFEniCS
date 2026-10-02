"""Task40 G0/G1 saved-field comparison on exact common hexahedral subcells.

This module contains the FE restoration, direct-curl, volume-comparison, and
material-interface trace calculations. Artifact discovery and JSON reporting
belong to the benchmark entry point.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


AXIS_MATCH_TOL_NM = 1.0e-12
FIELD_H_GATE = 1.0e-2
COMMON_QUADRATURE_ORDER = 7
SUBCELL_BATCH = 16
TRACE_QUADRATURE_ORDER = 5


@dataclass
class P6TotalField:
    label: str
    cfg: Any
    levels: dict[str, Any]
    electric: Any
    curl: Any
    axes: tuple[np.ndarray, np.ndarray, np.ndarray]
    tags_by_cell: np.ndarray
    cell_grid: np.ndarray


def union_axis_points(first: np.ndarray, second: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    """Return the exact floating-point union without snapping or tolerance merging."""

    a = np.asarray(first, dtype=np.float64)
    b = np.asarray(second, dtype=np.float64)
    if a.ndim != 1 or b.ndim != 1 or a.size < 2 or b.size < 2:
        raise ValueError("mesh axes must be one-dimensional and contain at least two points")
    if not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError("mesh axes must be finite")
    if np.any(np.diff(a) <= 0.0) or np.any(np.diff(b) <= 0.0):
        raise ValueError("source mesh axes must be strictly increasing")
    if a[0] != b[0]:
        raise ValueError("source mesh axis minima differ")
    if a[-1] != b[-1]:
        raise ValueError("source mesh axis maxima differ")
    raw = np.concatenate((a, b))
    union = np.unique(raw)
    close_gaps = np.diff(union)
    facts = {
        "source_point_counts": [int(a.size), int(b.size)],
        "union_point_count": int(union.size),
        "exact_duplicate_count": int(raw.size - union.size),
        "near_distinct_gap_count_below_diagnostic_tolerance": int(
            np.count_nonzero((close_gaps > 0.0) & (close_gaps <= AXIS_MATCH_TOL_NM))
        ),
        "diagnostic_tolerance_nm_not_used_for_merging": AXIS_MATCH_TOL_NM,
        "bounds_nm": [float(union[0]), float(union[-1])],
        "minimum_union_interval_nm": float(np.min(close_gaps)),
    }
    return union, facts


def weighted_vector_squared_norm(values: np.ndarray, weights: np.ndarray) -> float:
    """Compute integral |v|^2 with one scalar weight per vector sample."""

    vectors = np.asarray(values)
    weights = np.asarray(weights, dtype=np.float64)
    if vectors.ndim != 2 or weights.shape != (vectors.shape[0],):
        raise ValueError("vector values must be (sample, component) with one weight per sample")
    if np.any(weights < 0.0) or not np.isfinite(weights).all():
        raise ValueError("quadrature weights must be finite and nonnegative")
    component_norms = np.sum(np.abs(vectors) ** 2, axis=1)
    return float(np.dot(component_norms, weights))


def structured_cell_grid(
    axes: tuple[np.ndarray, np.ndarray, np.ndarray], midpoints: np.ndarray
) -> np.ndarray:
    """Map structured (i,j,k) axis intervals to local mesh-cell indices."""

    midpoints = np.asarray(midpoints, dtype=np.float64).reshape((-1, 3))
    shape = tuple(len(axis) - 1 for axis in axes)
    if int(np.prod(shape)) != len(midpoints):
        raise ValueError("cell midpoint count does not equal the structured axis-cell product")
    grid = np.full(shape, -1, dtype=np.int32)
    indices = np.column_stack(
        [
            np.searchsorted(axes[axis], midpoints[:, axis], side="right") - 1
            for axis in range(3)
        ]
    )
    for cell, (i, j, k) in enumerate(indices):
        if not (0 <= i < shape[0] and 0 <= j < shape[1] and 0 <= k < shape[2]):
            raise ValueError("cell midpoint lies outside the exact source mesh axes")
        if grid[i, j, k] != -1:
            raise ValueError("duplicate source cell in structured (i,j,k) axis map")
        grid[i, j, k] = cell
    if np.any(grid < 0):
        raise ValueError("structured source mesh has an unassigned axis cell")
    return grid


def direct_curl_dg(field: Any, degree: int = 6) -> Any:
    """Evaluate the FE derivative curl(E) directly from UFL into DG."""

    from dolfinx import fem
    import ufl

    mesh = field.function_space.mesh
    space = fem.functionspace(mesh, ("DG", int(degree), (3,)))
    points = space.element.interpolation_points
    if callable(points):
        points = points()
    curl = fem.Function(space, name="curl_E_direct_from_ufl")
    curl.interpolate(fem.Expression(ufl.curl(field), points))
    curl.x.scatter_forward()
    return curl


def restore_p6_total_field(label: str, cfg: Any, saved_vector: np.ndarray) -> P6TotalField:
    """Rebuild only the saved p6 space, then restore the exact total FE field."""

    from dolfinx import fem, mesh as dmesh
    from mpi4py import MPI

    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels

    levels = _build_same_mesh_levels(
        cfg, MPI.COMM_SELF, (6,), include_positive_coefficients=False
    )
    space = levels["spaces"][6]
    mpc = levels["floquets"][6].mpc
    electric = fem.Function(space, name=f"{label}_saved_total_E")
    saved_vector = np.asarray(saved_vector, dtype=np.complex128).reshape((-1,))
    if electric.x.array.size != saved_vector.size:
        raise ValueError(
            f"{label}: rebuilt p6 vector has {electric.x.array.size} entries; "
            f"saved vector has {saved_vector.size}"
        )
    electric.x.array[:] = saved_vector
    electric.x.scatter_forward()
    mpc.homogenize(electric)
    electric.x.scatter_forward()
    mpc.backsubstitution(electric)
    electric.x.scatter_forward()
    curl = direct_curl_dg(electric, degree=6)

    mesh = levels["mesh"]
    coordinates = np.asarray(mesh.geometry.x, dtype=np.float64)
    axes = tuple(np.unique(coordinates[:, axis]) for axis in range(3))
    if any(axis.size < 2 or np.any(np.diff(axis) <= 0.0) for axis in axes):
        raise ValueError(f"{label}: rebuilt structured p6 mesh has invalid axes")
    cell_count = int(mesh.topology.index_map(3).size_local)
    tags_by_cell = np.full(cell_count, -1, dtype=np.int32)
    cell_tags = levels["mesh_data"].cell_tags
    tags_by_cell[np.asarray(cell_tags.indices, dtype=np.int64)] = np.asarray(
        cell_tags.values, dtype=np.int32
    )
    if np.any(tags_by_cell < 0):
        raise ValueError(f"{label}: rebuilt p6 mesh has cells without a material tag")
    midpoints = dmesh.compute_midpoints(
        mesh, 3, np.arange(cell_count, dtype=np.int32)
    )
    cell_grid = structured_cell_grid(axes, midpoints)
    return P6TotalField(
        label=label,
        cfg=cfg,
        levels=levels,
        electric=electric,
        curl=curl,
        axes=axes,
        tags_by_cell=tags_by_cell,
        cell_grid=cell_grid,
    )


def _locate_cells(field: P6TotalField, points: np.ndarray) -> np.ndarray:
    points = np.asarray(points, dtype=np.float64).reshape((-1, 3))
    indices = np.column_stack(
        [
            np.searchsorted(field.axes[axis], points[:, axis], side="right") - 1
            for axis in range(3)
        ]
    )
    bounds = np.asarray(field.cell_grid.shape, dtype=np.int64)
    valid = np.all((indices >= 0) & (indices < bounds[None, :]), axis=1)
    if not np.all(valid):
        point = points[int(np.flatnonzero(~valid)[0])]
        raise ValueError(f"{field.label}: point is outside source mesh axes: {point.tolist()}")
    cells = field.cell_grid[indices[:, 0], indices[:, 1], indices[:, 2]]
    if np.any(cells < 0):
        raise ValueError(f"{field.label}: exact axis-index map has an unassigned structured cell")
    return np.asarray(cells, dtype=np.int32)


def _eval(function: Any, points: np.ndarray, cells: np.ndarray) -> np.ndarray:
    values = np.asarray(
        function.eval(
            np.asarray(points, dtype=np.float64).reshape((-1, 3)),
            np.asarray(cells, dtype=np.int32).reshape((-1,)),
        ),
        dtype=np.complex128,
    )
    return values.reshape((len(points), -1))[:, :3]


def total_field_sample_witness(
    field: P6TotalField,
    samples: dict[str, np.ndarray],
    sample_metadata: dict[str, Any],
) -> dict[str, Any]:
    """Verify the production total-field semantics against its saved samples."""

    from src.postprocessing.full3d_reference import (
        _sample_distributed_function,
        reference_plane_sides,
    )

    x = np.asarray(samples["x_nm"], dtype=np.float64)
    y = np.asarray(samples["y_nm"], dtype=np.float64)
    z = np.asarray(samples["z_nm"], dtype=np.float64)
    e_reference = np.asarray(samples["E_V_per_m"], dtype=np.complex128)
    h_reference = np.asarray(samples["H_A_per_m"], dtype=np.complex128)
    expected_shape = tuple(sample_metadata["array_shape_z_y_x_component"])
    if e_reference.shape != expected_shape or h_reference.shape != expected_shape:
        raise ValueError(f"{field.label}: saved E/H samples differ from metadata shape")
    zz, yy, xx = np.meshgrid(z, y, x, indexing="ij")
    points = np.column_stack((xx.ravel(), yy.ravel(), zz.ravel()))
    sides = reference_plane_sides(len(z), len(x) * len(y))
    e_code = _sample_distributed_function(field.electric, points, sides)
    curl_code = _sample_distributed_function(field.curl, points, sides)
    h_code = curl_code / (1j * field.cfg.k0 * field.cfg.mu_r)
    e_actual = e_code * field.cfg.electric_field_scale_V_per_m
    h_actual = h_code * field.cfg.magnetic_field_scale_A_per_m
    e_expected = e_reference.reshape((-1, 3))
    h_expected = h_reference.reshape((-1, 3))

    def relative(actual: np.ndarray, expected: np.ndarray) -> float:
        return float(
            np.linalg.norm((actual - expected).ravel())
            / max(np.linalg.norm(expected.ravel()), np.finfo(np.float64).tiny)
        )

    e_relative = relative(e_actual, e_expected)
    h_relative = relative(h_actual, h_expected)
    return {
        "field_model": "total_field",
        "production_identity": {
            "function_name": "E_total",
            "recovery_facts_field_model": "total_field",
            "volume_absorption_consumes_field_directly_as_total": True,
            "diffraction_call_uses_E_scattered_argument": False,
        },
        "sample_trace_sides": sample_metadata.get("interface_trace_sides"),
        "sample_z_nm": z.tolist(),
        "sample_shape": list(e_reference.shape),
        "electric_relative_l2": e_relative,
        "magnetic_relative_l2_from_direct_fe_curl": h_relative,
        "limit_relative_l2": 1.0e-4,
        "pass": bool(e_relative <= 1.0e-4 and h_relative <= 1.0e-4),
        "curl_source": "direct UFL curl(E_FE), not archived H or analytic background",
    }


def _exact_axis_union(
    first: P6TotalField, second: P6TotalField
) -> tuple[tuple[np.ndarray, np.ndarray, np.ndarray], list[dict[str, Any]]]:
    axes: list[np.ndarray] = []
    facts: list[dict[str, Any]] = []
    for index, name in enumerate(("x", "y", "z")):
        union, item = union_axis_points(first.axes[index], second.axes[index])
        item["axis"] = name
        axes.append(union)
        facts.append(item)
    return tuple(axes), facts  # type: ignore[return-value]


def _cell_catalog(
    first: P6TotalField,
    second: P6TotalField,
    axes: tuple[np.ndarray, np.ndarray, np.ndarray],
) -> dict[str, Any]:
    intervals = [np.diff(axis) for axis in axes]
    mids = [0.5 * (axis[:-1] + axis[1:]) for axis in axes]
    mx, my, mz = np.meshgrid(*mids, indexing="ij")
    wx, wy, wz = np.meshgrid(*intervals, indexing="ij")
    centers = np.column_stack((mx.ravel(), my.ravel(), mz.ravel()))
    widths = np.column_stack((wx.ravel(), wy.ravel(), wz.ravel()))
    cells0 = _locate_cells(first, centers)
    cells1 = _locate_cells(second, centers)
    tags0 = first.tags_by_cell[cells0]
    tags1 = second.tags_by_cell[cells1]
    mismatches = np.flatnonzero(tags0 != tags1)
    if mismatches.size:
        i = int(mismatches[0])
        raise ValueError(
            "common subcell material tags differ at "
            f"{centers[i].tolist()}: {int(tags0[i])} vs {int(tags1[i])}"
        )

    cfg = first.cfg
    air = tags0 == int(cfg.tags.air)
    substrate = tags0 == int(cfg.tags.substrate)
    grating = tags0 == int(cfg.tags.grating)
    void = np.zeros(len(centers), dtype=bool)
    if cfg.air_void_box_nm is not None:
        x0, x1, y0, y1, z0, z1 = map(float, cfg.air_void_box_nm)
        void = (
            air
            & (centers[:, 0] > x0)
            & (centers[:, 0] < x1)
            & (centers[:, 1] > y0)
            & (centers[:, 1] < y1)
            & (centers[:, 2] > z0)
            & (centers[:, 2] < z1)
        )
    pml = (tags0 == int(cfg.tags.top_pml)) | (tags0 == int(cfg.tags.bottom_pml))
    return {
        "centers": centers,
        "widths": widths,
        "cells_g0": cells0,
        "cells_g1": cells1,
        "masks": {
            "physical_domain": ~pml,
            "air_all_including_void": air,
            "air_outside_void_box": air & ~void,
            "void_box_air": void,
            "substrate": substrate,
            "grating_silicon": grating,
        },
        "shape": [int(axis.size - 1) for axis in axes],
        "material_tag_mismatch_count": int(mismatches.size),
    }


def _quantities(field: P6TotalField, e: np.ndarray, curl: np.ndarray,
                background_e: np.ndarray, background_h: np.ndarray) -> dict[str, np.ndarray]:
    h = curl / (1j * field.cfg.k0 * field.cfg.mu_r)
    curl_background = 1j * field.cfg.k0 * field.cfg.mu_r * background_h
    curl_scattered = curl - curl_background
    return {
        "E_total": e,
        "E_scattered": e - background_e,
        "H_total": h,
        "H_scattered": h - background_h,
        "curl_E_total": curl,
        "curl_E_scattered": curl_scattered,
        "scaled_curl_E_total": curl / field.cfg.k0,
        "scaled_curl_E_scattered": curl_scattered / field.cfg.k0,
    }


_QUANTITIES = {
    "E_total": ("V/m", "electric_field_scale_V_per_m"),
    "E_scattered": ("V/m", "electric_field_scale_V_per_m"),
    "H_total": ("A/m", "magnetic_field_scale_A_per_m"),
    "H_scattered": ("A/m", "magnetic_field_scale_A_per_m"),
    "curl_E_total": ("V/m/nm", "electric_field_scale_V_per_m"),
    "curl_E_scattered": ("V/m/nm", "electric_field_scale_V_per_m"),
    "scaled_curl_E_total": ("V/m", "electric_field_scale_V_per_m"),
    "scaled_curl_E_scattered": ("V/m", "electric_field_scale_V_per_m"),
}


def _background_code_fields(
    cfg: Any, points: np.ndarray, background: str
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Evaluate a named background E, H and analytic curl(E) in code units."""

    from src.common.analytic_fields_3d import (
        electric_field_code_values,
        magnetic_field_code_values,
        pml_complex_z,
    )

    coordinates = np.asarray(points, dtype=np.float64).reshape((-1, 3))
    if background == "layered_fresnel":
        electric = electric_field_code_values(cfg, coordinates)
        magnetic = magnetic_field_code_values(cfg, coordinates)
    elif background == "incident_plane_wave":
        wavevector = np.asarray(cfg.wavevector, dtype=np.complex128)
        polarization = np.asarray(cfg.polarization_vector, dtype=np.complex128)
        zeta = pml_complex_z(cfg, coordinates[:, 2])
        phase = np.exp(
            1j
            * (
                wavevector[0] * coordinates[:, 0]
                + wavevector[1] * coordinates[:, 1]
                + wavevector[2] * zeta
            )
        )
        electric = complex(cfg.incident_amplitude) * phase[:, None] * polarization[None, :]
        h_amplitude = np.cross(wavevector, polarization) / (
            cfg.k0 * cfg.mu_r
        )
        magnetic = complex(cfg.incident_amplitude) * phase[:, None] * h_amplitude[None, :]
    else:
        raise ValueError(f"unknown saved-field background {background!r}")

    # The incident plane wave is extended through substrate only to reproduce
    # the legacy R5 metric.  Layered Fresnel is Maxwell-consistent regionwise.
    # Both analytic curls are independent of the FE curl evaluated below.
    curl = 1j * cfg.k0 * cfg.mu_r * magnetic
    return electric, magnetic, curl


@dataclass
class P6BackgroundRepresentation:
    electric: Any
    curl: Any
    mpc_constraint_residual: float
    slave_interpolation_adjustment_relative: float
    slave_interpolation_adjustment_max: float


def interpolate_p6_background(
    field: P6TotalField, background: str
) -> P6BackgroundRepresentation:
    """Apply the actual p6 N1curl interpolation and finalized Floquet MPC map."""

    from dolfinx import fem

    from src.solvers.fullspace_same_mesh_hcurl_pmg_runtime import (
        _mpc_constraint_residual,
    )

    space = field.electric.function_space
    interpolated = fem.Function(space, name=f"{field.label}_{background}_IhE")
    interpolated.interpolate(
        lambda x: _background_code_fields(field.cfg, x.T, background)[0].T
    )
    interpolated.x.scatter_forward()

    mpc = field.levels["floquets"][6].mpc
    slave_dofs = np.asarray(mpc.slaves, dtype=np.int64)
    raw_slave_values = np.asarray(interpolated.x.array[slave_dofs]).copy()
    mpc.homogenize(interpolated)
    interpolated.x.scatter_forward()
    mpc.backsubstitution(interpolated)
    interpolated.x.scatter_forward()
    constrained_slave_values = np.asarray(interpolated.x.array[slave_dofs])
    adjustment = constrained_slave_values - raw_slave_values
    raw_norm = float(np.linalg.norm(raw_slave_values))
    adjustment_norm = float(np.linalg.norm(adjustment))
    adjustment_relative = adjustment_norm / max(raw_norm, np.finfo(float).tiny)
    adjustment_max = float(np.max(np.abs(adjustment), initial=0.0))
    residual = float(_mpc_constraint_residual(interpolated, field.levels["floquets"][6]))
    curl = direct_curl_dg(interpolated, degree=6)
    return P6BackgroundRepresentation(
        electric=interpolated,
        curl=curl,
        mpc_constraint_residual=residual,
        slave_interpolation_adjustment_relative=adjustment_relative,
        slave_interpolation_adjustment_max=adjustment_max,
    )


def _sample_l2(values: np.ndarray, weights: np.ndarray) -> float:
    return float(np.sqrt(weighted_vector_squared_norm(values, weights)))


def _incident_norm_for_quantity(
    quantity: str, incident_e_norm: float, incident_h_norm: float, k0: float
) -> float:
    if quantity.startswith("E_") or quantity.startswith("scaled_curl"):
        return incident_e_norm
    if quantity.startswith("H_"):
        return incident_h_norm
    return incident_e_norm * k0


def _attribution_terms(
    d: np.ndarray, d_b: np.ndarray, weights: np.ndarray
) -> dict[str, float]:
    inner = np.sum(np.conjugate(d) * d_b, axis=1)
    return {
        "d_sq": weighted_vector_squared_norm(d, weights),
        "d_b_sq": weighted_vector_squared_norm(d_b, weights),
        "remainder_sq": weighted_vector_squared_norm(d - d_b, weights),
        "inner_re": float(np.dot(np.real(inner), weights)),
        "inner_im": float(np.dot(np.imag(inner), weights)),
    }


def four_corner_differences(
    g00: np.ndarray, g10: np.ndarray, g01: np.ndarray, g11: np.ndarray
) -> dict[str, np.ndarray]:
    """Return x/z increments and the exact four-corner interaction vector."""

    return {
        "G00_to_G11": g11 - g00,
        "x_increment_G10_minus_G00": g10 - g00,
        "z_increment_G01_minus_G00": g01 - g00,
        "x_to_G11_error_G10_minus_G11": g10 - g11,
        "z_to_G11_error_G01_minus_G11": g01 - g11,
        "interaction_G11_minus_G10_minus_G01_plus_G00": g11 - g10 - g01 + g00,
    }


def _format_attribution(
    terms: dict[str, float],
    field_scale: float,
    unit: str,
    derivative_scale: float = 1.0,
    volume_integrated: bool = False,
) -> dict[str, Any]:
    factor = field_scale * derivative_scale
    d_norm = np.sqrt(terms["d_sq"]) * factor
    d_b_norm = np.sqrt(terms["d_b_sq"]) * factor
    remainder_norm = np.sqrt(terms["remainder_sq"]) * factor
    inner_re = terms["inner_re"] * factor**2
    inner_im = terms["inner_im"] * factor**2
    closure = (
        terms["remainder_sq"]
        - terms["d_sq"]
        - terms["d_b_sq"]
        + 2.0 * terms["inner_re"]
    ) * factor**2
    measure_suffix = "·nm^(3/2)" if volume_integrated else ""
    inner_suffix = "·nm^3" if volume_integrated else ""
    return {
        "field_unit": unit,
        "l2_norm_unit": f"{unit}{measure_suffix}",
        "inner_product_unit": f"{unit}^2{inner_suffix}",
        "d_l2_norm": float(d_norm),
        "d_b_l2_norm": float(d_b_norm),
        "d_minus_d_b_l2_norm": float(remainder_norm),
        "complex_inner_product": [float(inner_re), float(inner_im)],
        "two_real_inner_product": float(2.0 * inner_re),
        "squared_norm_identity_closure": float(closure),
        "squared_norm_identity_closure_relative": float(
            abs(closure)
            / max(remainder_norm**2, d_norm**2 + d_b_norm**2, np.finfo(float).tiny)
        ),
        "two_real_inner_product_definition": "2 Re <d,d_b>, <u,v>=integral(conj(u)·v)dV",
    }


def _sample_pair_metrics(
    first: P6TotalField,
    second: P6TotalField,
    sample_points: np.ndarray,
    sample_metadata: dict[str, Any],
    representations: dict[str, tuple[P6BackgroundRepresentation, P6BackgroundRepresentation]],
) -> dict[str, Any]:
    from src.postprocessing.full3d_reference import (
        _sample_distributed_function,
        reference_plane_sides,
    )

    points = np.asarray(sample_points, dtype=np.float64).reshape((-1, 3))
    z_count, y_count, x_count, _ = tuple(
        int(value) for value in sample_metadata["array_shape_z_y_x_component"]
    )
    sides = reference_plane_sides(z_count, x_count * y_count)
    if len(points) != z_count * y_count * x_count:
        raise ValueError("fixed sample point count differs from its archived array shape")
    e0 = _sample_distributed_function(first.electric, points, sides)
    c0 = _sample_distributed_function(first.curl, points, sides)
    e1 = _sample_distributed_function(second.electric, points, sides)
    c1 = _sample_distributed_function(second.curl, points, sides)
    weights = np.ones(len(points), dtype=np.float64)
    scale_e = float(first.cfg.electric_field_scale_V_per_m)
    scale_h = float(first.cfg.magnetic_field_scale_A_per_m)
    k0 = float(first.cfg.k0)
    incident_e, incident_h, _ = _background_code_fields(first.cfg, points, "incident_plane_wave")
    inc_e_norm = _sample_l2(incident_e, weights) * scale_e
    inc_h_norm = _sample_l2(incident_h, weights) * scale_h
    result: dict[str, Any] = {"sample_count": int(len(points)), "backgrounds": {}}
    for name, (rep0, rep1) in representations.items():
        bg_e, bg_h, bg_curl = _background_code_fields(first.cfg, points, name)
        q0 = _quantities(first, e0, c0, bg_e, bg_h)
        q1 = _quantities(second, e1, c1, bg_e, bg_h)
        metrics: dict[str, Any] = {}
        for quantity, (unit, factor_name) in _QUANTITIES.items():
            factor = float(getattr(first.cfg, factor_name))
            left, right = q0[quantity], q1[quantity]
            difference_norm = _sample_l2(left - right, weights) * factor
            denominator = _sample_l2(right, weights) * factor
            incident_norm = _incident_norm_for_quantity(
                quantity, inc_e_norm, inc_h_norm, k0
            )
            metrics[quantity] = {
                "unit": unit,
                "g0_l2_norm": _sample_l2(left, weights) * factor,
                "g1_l2_norm": denominator,
                "difference_l2_norm": difference_norm,
                "relative_to_g1": difference_norm / max(denominator, np.finfo(float).tiny),
                "incident_normalizer_l2": incident_norm,
                "difference_over_incident_l2": difference_norm
                / max(incident_norm, np.finfo(float).tiny),
            }

        sample_representation: dict[str, Any] = {}
        for label, actual, actual_curl, representation in (
            ("G0", e0, c0, rep0),
            ("G1", e1, c1, rep1),
        ):
            represented_e = _sample_distributed_function(
                representation.electric, points, sides
            )
            represented_curl = _sample_distributed_function(
                representation.curl, points, sides
            )
            sample_representation[label] = {
                "mpc_constraint_residual": representation.mpc_constraint_residual,
                "slave_interpolation_adjustment_relative": representation.slave_interpolation_adjustment_relative,
                "slave_interpolation_adjustment_max": representation.slave_interpolation_adjustment_max,
                "E_interp_error_l2_norm": _sample_l2(
                    represented_e - bg_e, weights
                )
                * scale_e,
                "E_background_l2_norm": _sample_l2(bg_e, weights) * scale_e,
                "curl_E_interp_error_l2_norm": _sample_l2(
                    represented_curl - bg_curl, weights
                )
                * scale_e,
                "curl_E_background_l2_norm": _sample_l2(bg_curl, weights) * scale_e,
                "actual_E_l2_norm": _sample_l2(actual, weights) * scale_e,
                "actual_curl_E_l2_norm": _sample_l2(actual_curl, weights) * scale_e,
            }

        attribution: dict[str, Any] = {}
        sampled_rep0_e = _sample_distributed_function(rep0.electric, points, sides)
        sampled_rep1_e = _sample_distributed_function(rep1.electric, points, sides)
        sampled_rep0_c = _sample_distributed_function(rep0.curl, points, sides)
        sampled_rep1_c = _sample_distributed_function(rep1.curl, points, sides)
        for label, actual_first, actual_second, represented_first, represented_second in (
            ("E", e0, e1, sampled_rep0_e, sampled_rep1_e),
            ("curl_E", c0, c1, sampled_rep0_c, sampled_rep1_c),
        ):
            d = actual_first - actual_second
            db = represented_first - represented_second
            attribution[label] = _format_attribution(
                _attribution_terms(d, db, weights),
                scale_e,
                "V/m" if label == "E" else "V/m/nm",
            )
            attribution[label]["two_real_inner_product_definition"] = (
                "2 Re <d,d_b>, <u,v>=sum(conj(u)*v)"
            )
        result["backgrounds"][name] = {
            "quantities": metrics,
            "representation": sample_representation,
            "attribution": attribution,
        }
    result["trace_sides"] = sample_metadata.get("interface_trace_sides")
    result["sample_z_nm"] = points[:: x_count * y_count, 2].tolist()
    result["reference_plane_sides"] = [
        "positive_z" if int(value) > 0 else "negative_z"
        for value in sides[:: x_count * y_count]
    ]
    return result


def compare_paired_background_attribution(
    first: P6TotalField,
    second: P6TotalField,
    sample_points: np.ndarray,
    sample_metadata: dict[str, Any],
    *,
    progress: bool = True,
) -> dict[str, Any]:
    """Compare both saved-field backgrounds and their true p6 MPC interpolants."""

    if not np.isclose(first.cfg.k0, second.cfg.k0, rtol=0.0, atol=1.0e-14):
        raise ValueError("paired attribution requires the same wavenumber")
    if not np.isclose(
        first.cfg.electric_field_scale_V_per_m,
        second.cfg.electric_field_scale_V_per_m,
        rtol=1.0e-13,
        atol=0.0,
    ):
        raise ValueError("paired attribution requires one electric field scale")
    if not np.isclose(first.cfg.mu_r, second.cfg.mu_r, rtol=0.0, atol=1.0e-14):
        raise ValueError("paired attribution requires the same relative permeability")

    names = ("incident_plane_wave", "layered_fresnel")
    representations = {
        name: (
            interpolate_p6_background(first, name),
            interpolate_p6_background(second, name),
        )
        for name in names
    }
    fixed_samples = _sample_pair_metrics(
        first, second, sample_points, sample_metadata, representations
    )

    axes, axis_facts = _exact_axis_union(first, second)
    catalog = _cell_catalog(first, second, axes)
    centers, widths, masks = catalog["centers"], catalog["widths"], catalog["masks"]
    legendre, one_d_weights = np.polynomial.legendre.leggauss(COMMON_QUADRATURE_ORDER)
    qx, qy, qz = np.meshgrid(legendre, legendre, legendre, indexing="ij")
    qref = np.column_stack((qx.ravel(), qy.ravel(), qz.ravel()))
    qw_x, qw_y, qw_z = np.meshgrid(one_d_weights, one_d_weights, one_d_weights, indexing="ij")
    qweights_ref = (qw_x * qw_y * qw_z).ravel()
    nq = len(qweights_ref)

    volume_results: dict[str, Any] = {}
    scale_e = float(first.cfg.electric_field_scale_V_per_m)
    scale_h = float(first.cfg.magnetic_field_scale_A_per_m)
    k0 = float(first.cfg.k0)

    def new_stats() -> dict[str, Any]:
        return {
            region: {
                "volume_nm3": 0.0,
                "quantities": {
                    key: {"g0_sq": 0.0, "g1_sq": 0.0, "difference_sq": 0.0}
                    for key in _QUANTITIES
                },
                "representation": {
                    grid: {
                        key: {"error_sq": 0.0, "background_sq": 0.0}
                        for key in ("E", "scaled_curl_E")
                    }
                    for grid in ("G0", "G1")
                },
                "attribution": {
                    key: {
                        "d_sq": 0.0,
                        "d_b_sq": 0.0,
                        "remainder_sq": 0.0,
                        "inner_re": 0.0,
                        "inner_im": 0.0,
                    }
                    for key in ("E", "scaled_curl_E")
                },
                "incident_E_sq": 0.0,
                "incident_H_sq": 0.0,
            }
            for region in masks
        }

    stats_by_background = {name: new_stats() for name in names}
    total = len(centers)
    last_tenth = -1
    for start in range(0, total, SUBCELL_BATCH):
        stop = min(start + SUBCELL_BATCH, total)
        half = 0.5 * widths[start:stop]
        points = (
            centers[start:stop, None, :]
            + half[:, None, :] * qref[None, :, :]
        ).reshape((-1, 3))
        weights = (np.prod(half, axis=1)[:, None] * qweights_ref[None, :]).reshape((-1,))
        cells0 = np.repeat(catalog["cells_g0"][start:stop], nq)
        cells1 = np.repeat(catalog["cells_g1"][start:stop], nq)
        # Evaluate each saved field/curl once; both background definitions use
        # this identical pair and the same quadrature coordinates.
        e0, c0 = _eval(first.electric, points, cells0), _eval(first.curl, points, cells0)
        e1, c1 = _eval(second.electric, points, cells1), _eval(second.curl, points, cells1)
        incident_e, incident_h, _ = _background_code_fields(
            first.cfg, points, "incident_plane_wave"
        )
        for name in names:
            rep0, rep1 = representations[name]
            ih_e0, ih_c0 = _eval(rep0.electric, points, cells0), _eval(rep0.curl, points, cells0)
            ih_e1, ih_c1 = _eval(rep1.electric, points, cells1), _eval(rep1.curl, points, cells1)
            bg_e, bg_h, bg_curl = _background_code_fields(first.cfg, points, name)
            q0 = _quantities(first, e0, c0, bg_e, bg_h)
            q1 = _quantities(second, e1, c1, bg_e, bg_h)
            representation = {
                "G0": {
                    "E": (ih_e0 - bg_e, bg_e),
                    "scaled_curl_E": ((ih_c0 - bg_curl) / k0, bg_curl / k0),
                },
                "G1": {
                    "E": (ih_e1 - bg_e, bg_e),
                    "scaled_curl_E": ((ih_c1 - bg_curl) / k0, bg_curl / k0),
                },
            }
            differences = {
                "E": (e0 - e1, ih_e0 - ih_e1),
                "scaled_curl_E": ((c0 - c1) / k0, (ih_c0 - ih_c1) / k0),
            }
            stats = stats_by_background[name]
            for region, mask in masks.items():
                selected = np.repeat(mask[start:stop], nq)
                if not np.any(selected):
                    continue
                w = weights[selected]
                state = stats[region]
                state["volume_nm3"] += float(np.sum(w))
                state["incident_E_sq"] += weighted_vector_squared_norm(incident_e[selected], w)
                state["incident_H_sq"] += weighted_vector_squared_norm(incident_h[selected], w)
                for quantity in _QUANTITIES:
                    left, right = q0[quantity][selected], q1[quantity][selected]
                    row = state["quantities"][quantity]
                    row["g0_sq"] += weighted_vector_squared_norm(left, w)
                    row["g1_sq"] += weighted_vector_squared_norm(right, w)
                    row["difference_sq"] += weighted_vector_squared_norm(left - right, w)
                for grid, data in representation.items():
                    for key, (error, background_values) in data.items():
                        row = state["representation"][grid][key]
                        row["error_sq"] += weighted_vector_squared_norm(error[selected], w)
                        row["background_sq"] += weighted_vector_squared_norm(background_values[selected], w)
                for key, (d, d_b) in differences.items():
                    d, d_b = d[selected], d_b[selected]
                    entry = state["attribution"][key]
                    for term, value in _attribution_terms(d, d_b, w).items():
                        entry[term] += value
        tenth = int(10 * stop / total)
        if progress and tenth > last_tenth:
            print(
                f"background attribution volume: {stop}/{total} common subcells "
                f"({100 * stop / total:.0f}%)",
                flush=True,
            )
            last_tenth = tenth

    for name in names:
        stats = stats_by_background[name]
        regions: dict[str, Any] = {}
        for region, state in stats.items():
            quantity_metrics: dict[str, Any] = {}
            incident_e_norm = np.sqrt(state["incident_E_sq"]) * scale_e
            incident_h_norm = np.sqrt(state["incident_H_sq"]) * scale_h
            for quantity, (unit, factor_name) in _QUANTITIES.items():
                factor = float(getattr(first.cfg, factor_name))
                row = state["quantities"][quantity]
                n0 = np.sqrt(row["g0_sq"]) * factor
                n1 = np.sqrt(row["g1_sq"]) * factor
                difference = np.sqrt(row["difference_sq"]) * factor
                incident_norm = _incident_norm_for_quantity(
                    quantity, incident_e_norm, incident_h_norm, k0
                )
                quantity_metrics[quantity] = {
                    "unit": unit,
                    "l2_norm_unit": f"{unit}·nm^(3/2)",
                    "g0_l2_norm": float(n0),
                    "g1_l2_norm": float(n1),
                    "difference_l2_norm": float(difference),
                    "relative_to_g1": float(difference / max(n1, np.finfo(float).tiny)),
                    "incident_normalizer_l2": float(incident_norm),
                    "difference_over_incident_l2": float(difference / max(incident_norm, np.finfo(float).tiny)),
                }
            representation_metrics: dict[str, Any] = {}
            for grid in ("G0", "G1"):
                representation_metrics[grid] = {}
                for key, row in state["representation"][grid].items():
                    error = np.sqrt(row["error_sq"]) * scale_e
                    background_norm = np.sqrt(row["background_sq"]) * scale_e
                    representation_metrics[grid][key] = {
                        "l2_norm_unit": "(V/m)·nm^(3/2)",
                        "field_unit": "V/m",
                        "interpolation_error_l2_norm": float(error),
                        "analytic_background_l2_norm": float(background_norm),
                        "relative_to_analytic_background": float(error / max(background_norm, np.finfo(float).tiny)),
                        "relative_to_incident_E": float(error / max(incident_e_norm, np.finfo(float).tiny)),
                    }
                curl_row = representation_metrics[grid]["scaled_curl_E"]
                curl_row["curl_E_l2_norm_unit"] = "(V/m/nm)·nm^(3/2)"
                curl_row["curl_E_interpolation_error_l2_norm"] = float(curl_row["interpolation_error_l2_norm"] * k0)
                curl_row["curl_E_analytic_background_l2_norm"] = float(curl_row["analytic_background_l2_norm"] * k0)
            attribution_metrics: dict[str, Any] = {}
            for key, row in state["attribution"].items():
                attribution_metrics[key] = _format_attribution(
                    row, scale_e, "V/m", volume_integrated=True
                )
                if key == "scaled_curl_E":
                    attribution_metrics["curl_E_raw"] = _format_attribution(
                        row,
                        scale_e,
                        "V/m/nm",
                        derivative_scale=k0,
                        volume_integrated=True,
                    )
            regions[region] = {
                "volume_nm3": float(state["volume_nm3"]),
                "quantities": quantity_metrics,
                "p6_interpolation_representation": representation_metrics,
                "cross_mesh_attribution": attribution_metrics,
            }
        volume_results[name] = {
            "common_subcell_shape": catalog["shape"],
            "common_subcell_count": int(len(centers)),
            "axis_union": axis_facts,
            "quadrature_order_per_axis": COMMON_QUADRATURE_ORDER,
            "curl_source": "direct UFL curl(E_FE) into DG6 for both saved field and I_h b",
            "regions": regions,
            "l2_measure": "volume in nm^3; each reported L2 norm therefore has its field unit multiplied by nm^(3/2)",
        }

    return {
        "method": {
            "backgrounds": {
                "incident_plane_wave": "legacy R5 incident plane wave extended through the substrate; its substrate values reproduce the metric but are not a substrate Maxwell solution",
                "layered_fresnel": "existing flat air/substrate Fresnel background used by P1/P4",
            },
            "coordinates": "input coordinates and structured-mesh code coordinates are nm; xyz order; exp(i k·r), exp(-i omega t)",
            "interpolant": "Basix N1curl p6 moment interpolation followed by the run's finalized double-Floquet MPC homogenize/backsubstitution; no fit or projection factor",
            "curl": "independent UFL curl(E_FE) into DG6; analytic curl is the direct derivative of the named plane-wave components",
            "attribution": "d=E_G0-E_G1; d_b=I_G0 b-I_G1 b; no fitted coefficient or phase",
        },
        "fixed_samples": fixed_samples,
        "volume": volume_results,
    }


def compare_four_corner_directional(
    fields: dict[str, P6TotalField], *, progress: bool = True
) -> dict[str, Any]:
    """Measure the preregistered G00/G10/G01/G11 x/z mesh contrast."""

    labels = ("G00", "G10", "G01", "G11")
    if set(fields) != set(labels):
        raise ValueError(f"four-corner fields must be exactly {labels}")
    first, last = fields["G00"], fields["G11"]
    for label in labels[1:]:
        cfg = fields[label].cfg
        if not np.isclose(cfg.k0, first.cfg.k0, rtol=0.0, atol=1.0e-14):
            raise ValueError("four-corner fields have different wavenumbers")
        if not np.isclose(cfg.mu_r, first.cfg.mu_r, rtol=0.0, atol=1.0e-14):
            raise ValueError("four-corner fields have different relative permeability")
        for scale_name in (
            "electric_field_scale_V_per_m",
            "magnetic_field_scale_A_per_m",
        ):
            if not np.isclose(
                getattr(cfg, scale_name),
                getattr(first.cfg, scale_name),
                rtol=1.0e-13,
                atol=0.0,
            ):
                raise ValueError(f"four-corner fields differ in {scale_name}")

    axes, axis_facts = _exact_axis_union(first, last)
    for axis_index, axis_name in enumerate(("x", "y", "z")):
        for label in labels[1:-1]:
            candidate = np.unique(
                np.concatenate((axes[axis_index], fields[label].axes[axis_index]))
            )
            if not np.array_equal(candidate, axes[axis_index]):
                raise ValueError(
                    f"{label} {axis_name} axis is not a subset of the common four-grid union"
                )
    catalog = _cell_catalog(first, last, axes)
    centers, widths, masks = catalog["centers"], catalog["widths"], catalog["masks"]
    cell_maps = {
        label: _locate_cells(fields[label], centers) for label in labels
    }
    reference_tags = first.tags_by_cell[catalog["cells_g0"]]
    for label in labels[1:]:
        tags = fields[label].tags_by_cell[cell_maps[label]]
        if not np.array_equal(tags, reference_tags):
            index = int(np.flatnonzero(tags != reference_tags)[0])
            raise ValueError(
                f"{label}: material tag differs at common cell center "
                f"{centers[index].tolist()}"
            )

    legendre, one_d_weights = np.polynomial.legendre.leggauss(COMMON_QUADRATURE_ORDER)
    qx, qy, qz = np.meshgrid(legendre, legendre, legendre, indexing="ij")
    qref = np.column_stack((qx.ravel(), qy.ravel(), qz.ravel()))
    qw_x, qw_y, qw_z = np.meshgrid(
        one_d_weights, one_d_weights, one_d_weights, indexing="ij"
    )
    qweights_ref = (qw_x * qw_y * qw_z).ravel()
    nq = len(qweights_ref)
    direction_keys = (
        "G00_to_G11",
        "x_increment_G10_minus_G00",
        "z_increment_G01_minus_G00",
        "x_to_G11_error_G10_minus_G11",
        "z_to_G11_error_G01_minus_G11",
        "interaction_G11_minus_G10_minus_G01_plus_G00",
    )

    def new_region() -> dict[str, Any]:
        return {
            "volume_nm3": 0.0,
            "corner_sq": {
                label: {quantity: 0.0 for quantity in _QUANTITIES}
                for label in labels
            },
            "direction_sq": {
                quantity: {key: 0.0 for key in direction_keys}
                for quantity in _QUANTITIES
            },
            "incident_E_sq": 0.0,
            "incident_H_sq": 0.0,
        }

    stats = {region: new_region() for region in masks}
    scale_e = float(first.cfg.electric_field_scale_V_per_m)
    scale_h = float(first.cfg.magnetic_field_scale_A_per_m)
    k0 = float(first.cfg.k0)
    total = len(centers)
    last_tenth = -1
    for start in range(0, total, SUBCELL_BATCH):
        stop = min(start + SUBCELL_BATCH, total)
        half = 0.5 * widths[start:stop]
        points = (
            centers[start:stop, None, :]
            + half[:, None, :] * qref[None, :, :]
        ).reshape((-1, 3))
        weights = (np.prod(half, axis=1)[:, None] * qweights_ref[None, :]).reshape(
            (-1,)
        )
        incident_e, incident_h, _ = _background_code_fields(
            first.cfg, points, "incident_plane_wave"
        )
        bg_e, bg_h, _ = _background_code_fields(
            first.cfg, points, "layered_fresnel"
        )
        corner_values: dict[str, dict[str, np.ndarray]] = {}
        for label in labels:
            field = fields[label]
            cells = np.repeat(cell_maps[label][start:stop], nq)
            electric = _eval(field.electric, points, cells)
            curl = _eval(field.curl, points, cells)
            corner_values[label] = _quantities(field, electric, curl, bg_e, bg_h)

        for region, mask in masks.items():
            selected = np.repeat(mask[start:stop], nq)
            if not np.any(selected):
                continue
            w = weights[selected]
            state = stats[region]
            state["volume_nm3"] += float(np.sum(w))
            state["incident_E_sq"] += weighted_vector_squared_norm(incident_e[selected], w)
            state["incident_H_sq"] += weighted_vector_squared_norm(incident_h[selected], w)
            for quantity in _QUANTITIES:
                for label in labels:
                    state["corner_sq"][label][quantity] += weighted_vector_squared_norm(
                        corner_values[label][quantity][selected], w
                    )
                directional = four_corner_differences(
                    corner_values["G00"][quantity][selected],
                    corner_values["G10"][quantity][selected],
                    corner_values["G01"][quantity][selected],
                    corner_values["G11"][quantity][selected],
                )
                for key, vector in directional.items():
                    state["direction_sq"][quantity][key] += weighted_vector_squared_norm(
                        vector, w
                    )
        tenth = int(10 * stop / total)
        if progress and tenth > last_tenth:
            print(
                f"four-corner volume: {stop}/{total} common subcells "
                f"({100 * stop / total:.0f}%)",
                flush=True,
            )
            last_tenth = tenth

    regions: dict[str, Any] = {}
    for region, state in stats.items():
        incident_e_norm = np.sqrt(state["incident_E_sq"]) * scale_e
        incident_h_norm = np.sqrt(state["incident_H_sq"]) * scale_h
        quantities: dict[str, Any] = {}
        for quantity, (unit, factor_name) in _QUANTITIES.items():
            factor = float(getattr(first.cfg, factor_name))
            corner_norms = {
                label: float(np.sqrt(state["corner_sq"][label][quantity]) * factor)
                for label in labels
            }
            direction_norms = {
                key: float(np.sqrt(value) * factor)
                for key, value in state["direction_sq"][quantity].items()
            }
            g1_norm = corner_norms["G11"]
            incident_norm = _incident_norm_for_quantity(quantity, incident_e_norm, incident_h_norm, k0)
            quantities[quantity] = {
                "unit": unit,
                "l2_norm_unit": f"{unit}·nm^(3/2)",
                "corner_l2_norms": corner_norms,
                "Gx_to_G1_difference_l2_norm": direction_norms[
                    "x_to_G11_error_G10_minus_G11"
                ],
                "Gx_relative_to_G1": direction_norms[
                    "x_to_G11_error_G10_minus_G11"
                ] / max(g1_norm, np.finfo(float).tiny),
                "Gz_to_G1_difference_l2_norm": direction_norms[
                    "z_to_G11_error_G01_minus_G11"
                ],
                "Gz_relative_to_G1": direction_norms[
                    "z_to_G11_error_G01_minus_G11"
                ] / max(g1_norm, np.finfo(float).tiny),
                "G0_to_G1_difference_l2_norm": direction_norms["G00_to_G11"],
                "G0_relative_to_G1": direction_norms["G00_to_G11"]
                / max(g1_norm, np.finfo(float).tiny),
                "x_increment_l2_norm": direction_norms[
                    "x_increment_G10_minus_G00"
                ],
                "x_increment_relative_to_G1": direction_norms[
                    "x_increment_G10_minus_G00"
                ] / max(g1_norm, np.finfo(float).tiny),
                "x_increment_over_incident_l2": direction_norms[
                    "x_increment_G10_minus_G00"
                ] / max(incident_norm, np.finfo(float).tiny),
                "z_increment_l2_norm": direction_norms[
                    "z_increment_G01_minus_G00"
                ],
                "z_increment_relative_to_G1": direction_norms[
                    "z_increment_G01_minus_G00"
                ] / max(g1_norm, np.finfo(float).tiny),
                "z_increment_over_incident_l2": direction_norms[
                    "z_increment_G01_minus_G00"
                ] / max(incident_norm, np.finfo(float).tiny),
                "interaction_l2_norm": direction_norms[
                    "interaction_G11_minus_G10_minus_G01_plus_G00"
                ],
                "interaction_relative_to_G1": direction_norms[
                    "interaction_G11_minus_G10_minus_G01_plus_G00"
                ] / max(g1_norm, np.finfo(float).tiny),
                "interaction_over_incident_l2": direction_norms[
                    "interaction_G11_minus_G10_minus_G01_plus_G00"
                ] / max(incident_norm, np.finfo(float).tiny),
                "incident_normalizer_l2": float(incident_norm),
                "Gx_to_G1_difference_over_incident_l2": direction_norms[
                    "x_to_G11_error_G10_minus_G11"
                ] / max(incident_norm, np.finfo(float).tiny),
                "Gz_to_G1_difference_over_incident_l2": direction_norms[
                    "z_to_G11_error_G01_minus_G11"
                ] / max(incident_norm, np.finfo(float).tiny),
            }
        regions[region] = {
            "volume_nm3": float(state["volume_nm3"]),
            "quantities": quantities,
        }
    return {
        "background": "layered_fresnel (official P1/P4 definition)",
        "common_subcell_shape": catalog["shape"],
        "common_subcell_count": int(total),
        "axis_union": axis_facts,
        "quadrature_order_per_axis": COMMON_QUADRATURE_ORDER,
        "material_tag_mismatch_count": 0,
        "curl_source": "direct UFL curl(E_FE) into DG6 for all four saved fields",
        "directions": {
            "x": "G10-G00",
            "z": "G01-G00",
            "interaction": "G11-G10-G01+G00",
            "Gx_to_G1": "G10-G11",
            "Gz_to_G1": "G01-G11",
        },
        "normalization": {
            "Gx_and_Gz_error_denominator": "fixed G11/G1 L2 norm for the same quantity and region",
            "incident_diagnostic_denominator": "same-region incident E, H, or k0-scaled E L2 norm according to quantity units",
            "x_z_interaction": "G11-G10-G01+G00; reported as absolute, G1-relative, and incident-relative L2 norms",
        },
        "regions": regions,
        "l2_measure": "volume in nm^3; each reported L2 norm has its field unit multiplied by nm^(3/2)",
    }


def compare_common_subcell_volume(
    first: P6TotalField,
    second: P6TotalField,
    *,
    progress: bool = True,
) -> dict[str, Any]:
    """Stream field and independently differentiated curl norms on exact union cells."""

    from src.common.analytic_fields_3d import electric_field_code_values, magnetic_field_code_values

    axes, axis_facts = _exact_axis_union(first, second)
    catalog = _cell_catalog(first, second, axes)
    centers = catalog["centers"]
    widths = catalog["widths"]
    masks = catalog["masks"]
    legendre, one_d_weights = np.polynomial.legendre.leggauss(COMMON_QUADRATURE_ORDER)
    qx, qy, qz = np.meshgrid(legendre, legendre, legendre, indexing="ij")
    qref = np.column_stack((qx.ravel(), qy.ravel(), qz.ravel()))
    qw_x, qw_y, qw_z = np.meshgrid(one_d_weights, one_d_weights, one_d_weights, indexing="ij")
    qweights_ref = (qw_x * qw_y * qw_z).ravel()
    nq = len(qweights_ref)
    stats = {
        region: {
            "volume_nm3": 0.0,
            **{
                name: {"g0_sq": 0.0, "g1_sq": 0.0, "difference_sq": 0.0}
                for name in _QUANTITIES
            },
        }
        for region in masks
    }
    total = len(centers)
    last_tenth = -1
    for start in range(0, total, SUBCELL_BATCH):
        stop = min(start + SUBCELL_BATCH, total)
        cell_centers = centers[start:stop]
        half = 0.5 * widths[start:stop]
        points = (cell_centers[:, None, :] + half[:, None, :] * qref[None, :, :]).reshape((-1, 3))
        weights = (np.prod(half, axis=1)[:, None] * qweights_ref[None, :]).reshape((-1,))
        cells0 = np.repeat(catalog["cells_g0"][start:stop], nq)
        cells1 = np.repeat(catalog["cells_g1"][start:stop], nq)
        e0, c0 = _eval(first.electric, points, cells0), _eval(first.curl, points, cells0)
        e1, c1 = _eval(second.electric, points, cells1), _eval(second.curl, points, cells1)
        bg_e = electric_field_code_values(first.cfg, points)
        bg_h = magnetic_field_code_values(first.cfg, points)
        q0 = _quantities(first, e0, c0, bg_e, bg_h)
        q1 = _quantities(second, e1, c1, bg_e, bg_h)
        for region, mask in masks.items():
            selected = np.repeat(mask[start:stop], nq)
            if not np.any(selected):
                continue
            selected_weights = weights[selected]
            stats[region]["volume_nm3"] += float(np.sum(selected_weights))
            for name in _QUANTITIES:
                left, right = q0[name][selected], q1[name][selected]
                stats[region][name]["g0_sq"] += weighted_vector_squared_norm(left, selected_weights)
                stats[region][name]["g1_sq"] += weighted_vector_squared_norm(right, selected_weights)
                stats[region][name]["difference_sq"] += weighted_vector_squared_norm(left - right, selected_weights)
        tenth = int(10 * stop / total)
        if progress and tenth > last_tenth:
            print(f"P1 volume: {stop}/{total} common subcells ({100*stop/total:.0f}%)", flush=True)
            last_tenth = tenth

    metrics: dict[str, Any] = {}
    for region, values in stats.items():
        row = {"volume_nm3": values["volume_nm3"], "quantities": {}}
        for name, (unit, factor_name) in _QUANTITIES.items():
            factor0 = float(getattr(first.cfg, factor_name))
            factor1 = float(getattr(second.cfg, factor_name))
            n0 = np.sqrt(values[name]["g0_sq"]) * factor0
            n1 = np.sqrt(values[name]["g1_sq"]) * factor1
            error = np.sqrt(values[name]["difference_sq"]) * 0.5 * (factor0 + factor1)
            row["quantities"][name] = {
                "unit": unit,
                "g0_l2_norm": float(n0),
                "g1_l2_norm": float(n1),
                "difference_l2_norm": float(error),
                "relative_to_g1": float(error / max(n1, np.finfo(float).tiny)),
            }
        metrics[region] = row

    gate_fields = (
        "E_total", "E_scattered", "H_total", "H_scattered",
        "scaled_curl_E_total", "scaled_curl_E_scattered",
    )
    global_values = metrics["physical_domain"]["quantities"]
    relative_values = [global_values[name]["relative_to_g1"] for name in gate_fields]
    return {
        "axis_union": axis_facts,
        "common_subcell_shape": catalog["shape"],
        "common_subcell_count": int(len(centers)),
        "material_tag_mismatch_count": catalog["material_tag_mismatch_count"],
        "region_semantics": {
            "physical_domain": "all tagged physical cells, excluding top/bottom PML tags",
            "air_all_including_void": "air-tagged cells, including the explicit rectangular air void",
            "air_outside_void_box": "air-tagged cells outside air_void_box_nm",
            "void_box_air": "air-tagged subcells strictly inside air_void_box_nm",
            "substrate": "substrate-tagged cells",
            "grating_silicon": "grating-tagged cells",
        },
        "streaming": {
            "subcell_batch": SUBCELL_BATCH,
            "quadrature_order_per_axis": COMMON_QUADRATURE_ORDER,
            "max_quadrature_points_per_batch": SUBCELL_BATCH * nq,
            "curl_source": "direct UFL curl(E_FE) into DG6; H derived afterward from curl",
        },
        "metrics": metrics,
        "field_scaled_curl_h_gate": {
            "metric_scope": "global physical-domain L2 norms on exact common subcells",
            "quantities": list(gate_fields),
            "limit_relative_l2": FIELD_H_GATE,
            "max_relative_l2": float(max(relative_values, default=0.0)),
            "pass": bool(all(value <= FIELD_H_GATE for value in relative_values)),
            "classification": "engineering h comparison only; not continuum convergence",
        },
    }


def _material_surfaces(cfg: Any) -> list[dict[str, Any]]:
    candidates: list[tuple[int, float, str]] = []
    candidates.extend(
        [
            (0, float(cfg.grating_x_min), "grating_x_min"),
            (0, float(cfg.grating_x_max), "grating_x_max"),
            (1, float(cfg.grating_y_min), "grating_y_min"),
            (1, float(cfg.grating_y_max), "grating_y_max"),
            (2, float(cfg.interface_z), "substrate_top_grating_base"),
            (2, float(cfg.grating_z_min), "grating_z_min"),
            (2, float(cfg.grating_z_max), "grating_z_max"),
        ]
    )
    if cfg.air_void_box_nm is not None:
        x0, x1, y0, y1, z0, z1 = map(float, cfg.air_void_box_nm)
        candidates.extend(
            [
                (0, x0, "void_x_min"), (0, x1, "void_x_max"),
                (1, y0, "void_y_min"), (1, y1, "void_y_max"),
                (2, z0, "void_z_min"), (2, z1, "void_z_max"),
            ]
        )
    grouped: list[dict[str, Any]] = []
    for axis, coordinate, name in candidates:
        previous = next(
            (
                item for item in grouped
                if item["axis_index"] == axis
                and item["coordinate_nm"] == coordinate
            ),
            None,
        )
        if previous is None:
            grouped.append(
                {"axis_index": axis, "coordinate_nm": coordinate, "names": [name]}
            )
        else:
            previous["names"].append(name)
    return grouped


def _partition_mesh_exterior_surfaces(
    surfaces: list[dict[str, Any]],
    first_axes: tuple[np.ndarray, np.ndarray, np.ndarray],
    second_axes: tuple[np.ndarray, np.ndarray, np.ndarray],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Separate two-sided interior faces from configured planes on the domain boundary."""

    interior: list[dict[str, Any]] = []
    exterior: list[dict[str, Any]] = []
    for surface in surfaces:
        axis_index = int(surface["axis_index"])
        coordinate = float(surface["coordinate_nm"])
        at_exterior = []
        for label, axes in (("G0", first_axes), ("G1", second_axes)):
            axis = axes[axis_index]
            if coordinate == float(axis[0]) or coordinate == float(axis[-1]):
                at_exterior.append(label)
        if at_exterior and len(at_exterior) != 2:
            raise ValueError(
                f"G0/G1 domain boundaries disagree at configured face {coordinate} nm"
            )
        if at_exterior:
            exterior.append(
                {
                    "plane_names": list(surface["names"]),
                    "axis": ("x", "y", "z")[axis_index],
                    "coordinate_nm": coordinate,
                    "reason": "mesh exterior has no two-sided in-domain material trace",
                }
            )
        else:
            interior.append(surface)
    return interior, exterior


def _face_patch_points(
    axes: tuple[np.ndarray, np.ndarray, np.ndarray], axis_index: int, coordinate: float
) -> tuple[np.ndarray, np.ndarray, tuple[int, int]]:
    other = tuple(index for index in range(3) if index != axis_index)
    u_axis, v_axis = axes[other[0]], axes[other[1]]
    u_mid, v_mid = 0.5 * (u_axis[:-1] + u_axis[1:]), 0.5 * (v_axis[:-1] + v_axis[1:])
    uu, vv = np.meshgrid(u_mid, v_mid, indexing="ij")
    centers = np.column_stack((uu.ravel(), vv.ravel()))
    half = np.asarray(
        [
            (0.5 * (u_axis[i + 1] - u_axis[i]), 0.5 * (v_axis[j + 1] - v_axis[j]))
            for i in range(len(u_axis) - 1)
            for j in range(len(v_axis) - 1)
        ],
        dtype=np.float64,
    )
    q, qw = np.polynomial.legendre.leggauss(TRACE_QUADRATURE_ORDER)
    qu, qv = np.meshgrid(q, q, indexing="ij")
    qref = np.column_stack((qu.ravel(), qv.ravel()))
    wu, wv = np.meshgrid(qw, qw, indexing="ij")
    qweights = (wu * wv).ravel()
    uv = centers[:, None, :] + half[:, None, :] * qref[None, :, :]
    points = np.empty((len(centers), len(qref), 3), dtype=np.float64)
    points[:, :, axis_index] = coordinate
    points[:, :, other[0]] = uv[:, :, 0]
    points[:, :, other[1]] = uv[:, :, 1]
    weights = (np.prod(half, axis=1)[:, None] * qweights[None, :]).reshape((-1,))
    return points, weights, other


def _side_cells(
    field: P6TotalField,
    axis_index: int,
    coordinate: float,
    centers_on_face: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, float]:
    axis = field.axes[axis_index]
    nearest = int(np.argmin(np.abs(axis - coordinate)))
    difference = abs(float(axis[nearest]) - coordinate)
    if difference > AXIS_MATCH_TOL_NM:
        raise ValueError(
            f"{field.label}: material face {coordinate} is not a reconstructed mesh split "
            f"(nearest offset {difference} nm)"
        )
    if nearest == 0 or nearest == len(axis) - 1:
        raise ValueError(f"material interface {coordinate} is on the mesh exterior")
    minus_probe = 0.5 * (float(axis[nearest - 1]) + coordinate)
    plus_probe = 0.5 * (coordinate + float(axis[nearest + 1]))
    minus_points = centers_on_face.copy()
    plus_points = centers_on_face.copy()
    minus_points[:, axis_index] = minus_probe
    plus_points[:, axis_index] = plus_probe
    minus_cells = _locate_cells(field, minus_points)
    plus_cells = _locate_cells(field, plus_points)
    return minus_cells, plus_cells, difference


def _trace_quantities(field: P6TotalField, e: np.ndarray, curl: np.ndarray,
                      background_e: np.ndarray, background_h: np.ndarray) -> dict[str, np.ndarray]:
    return _quantities(field, e, curl, background_e, background_h)


def compare_material_interface_traces(
    first: P6TotalField,
    second: P6TotalField,
    axes: tuple[np.ndarray, np.ndarray, np.ndarray],
) -> dict[str, Any]:
    """Compare G0/G1 traces on both sides of configured rectangular material faces."""

    from src.common.analytic_fields_3d import electric_field_code_values, magnetic_field_code_values

    surfaces, exterior_surfaces = _partition_mesh_exterior_surfaces(
        _material_surfaces(first.cfg), first.axes, second.axes
    )
    transitions: list[dict[str, Any]] = []
    total_face_tiles = 0
    total_material_tiles = 0
    maximum_source_face_offset = 0.0
    for surface in surfaces:
        axis_index = int(surface["axis_index"])
        coordinate = float(surface["coordinate_nm"])
        face_points, weights, other = _face_patch_points(axes, axis_index, coordinate)
        patch_count, nq = face_points.shape[:2]
        centers = np.mean(face_points, axis=1)
        cells0_minus, cells0_plus, offset0 = _side_cells(
            first, axis_index, coordinate, centers.copy()
        )
        cells1_minus, cells1_plus, offset1 = _side_cells(
            second, axis_index, coordinate, centers.copy()
        )
        maximum_source_face_offset = max(maximum_source_face_offset, offset0, offset1)
        tags0_minus, tags0_plus = first.tags_by_cell[cells0_minus], first.tags_by_cell[cells0_plus]
        tags1_minus, tags1_plus = second.tags_by_cell[cells1_minus], second.tags_by_cell[cells1_plus]
        mismatch = (tags0_minus != tags1_minus) | (tags0_plus != tags1_plus)
        if np.any(mismatch):
            i = int(np.flatnonzero(mismatch)[0])
            raise ValueError(
                f"G0/G1 face material tags differ at {centers[i].tolist()} on {surface['names']}"
            )
        material_face = tags0_minus != tags0_plus
        total_face_tiles += int(patch_count)
        total_material_tiles += int(np.count_nonzero(material_face))
        if not np.any(material_face):
            continue
        records = []
        for minus_tag, plus_tag in sorted(
            set(zip(tags0_minus[material_face].tolist(), tags0_plus[material_face].tolist()))
        ):
            selected_patches = material_face & (tags0_minus == minus_tag) & (tags0_plus == plus_tag)
            indices = np.flatnonzero(selected_patches)
            points = face_points[indices].reshape((-1, 3))
            qw = weights.reshape((patch_count, nq))[indices].reshape((-1,))
            cm0 = np.repeat(cells0_minus[indices], nq)
            cp0 = np.repeat(cells0_plus[indices], nq)
            cm1 = np.repeat(cells1_minus[indices], nq)
            cp1 = np.repeat(cells1_plus[indices], nq)
            e0m, c0m = _eval(first.electric, points, cm0), _eval(first.curl, points, cm0)
            e0p, c0p = _eval(first.electric, points, cp0), _eval(first.curl, points, cp0)
            e1m, c1m = _eval(second.electric, points, cm1), _eval(second.curl, points, cm1)
            e1p, c1p = _eval(second.electric, points, cp1), _eval(second.curl, points, cp1)
            bg_points_minus, bg_points_plus = points.copy(), points.copy()
            bg_points_minus[:, axis_index] = np.nextafter(coordinate, -np.inf)
            bg_points_plus[:, axis_index] = np.nextafter(coordinate, np.inf)
            bg_em = electric_field_code_values(first.cfg, bg_points_minus)
            bg_ep = electric_field_code_values(first.cfg, bg_points_plus)
            bg_hm = magnetic_field_code_values(first.cfg, bg_points_minus)
            bg_hp = magnetic_field_code_values(first.cfg, bg_points_plus)
            q0m, q0p = _trace_quantities(first, e0m, c0m, bg_em, bg_hm), _trace_quantities(first, e0p, c0p, bg_ep, bg_hp)
            q1m, q1p = _trace_quantities(second, e1m, c1m, bg_em, bg_hm), _trace_quantities(second, e1p, c1p, bg_ep, bg_hp)
            side_records = []
            for side_name, left, right in (("minus", q0m, q1m), ("plus", q0p, q1p)):
                fields = {}
                for name, (unit, factor_name) in _QUANTITIES.items():
                    factor = float(getattr(first.cfg, factor_name))
                    v0, v1 = left[name], right[name]
                    full0 = weighted_vector_squared_norm(v0, qw) ** 0.5 * factor
                    full1 = weighted_vector_squared_norm(v1, qw) ** 0.5 * factor
                    err = weighted_vector_squared_norm(v0 - v1, qw) ** 0.5 * factor
                    fields[name] = {
                        "unit": unit,
                        "g0_l2_norm": float(full0),
                        "g1_l2_norm": float(full1),
                        "difference_l2_norm": float(err),
                        "relative_to_g1": float(err / max(full1, np.finfo(float).tiny)),
                    }
                # Tangential and normal trace differences are reported for total E and H.
                tangential_components = list(other)
                normal_component = [axis_index]
                for name, component_indices in (
                    ("E_total_tangential", tangential_components),
                    ("E_total_normal", normal_component),
                    ("H_total_tangential", tangential_components),
                    ("H_total_normal", normal_component),
                ):
                    base = "E_total" if name.startswith("E_") else "H_total"
                    factor_name = (
                        "electric_field_scale_V_per_m"
                        if base.startswith("E_")
                        else "magnetic_field_scale_A_per_m"
                    )
                    factor = float(getattr(first.cfg, factor_name))
                    v0, v1 = left[base][:, component_indices], right[base][:, component_indices]
                    norm0 = weighted_vector_squared_norm(v0, qw) ** 0.5 * factor
                    norm1 = weighted_vector_squared_norm(v1, qw) ** 0.5 * factor
                    err = weighted_vector_squared_norm(v0 - v1, qw) ** 0.5 * factor
                    fields[name] = {
                        "unit": "V/m" if base.startswith("E_") else "A/m",
                        "g0_l2_norm": float(norm0),
                        "g1_l2_norm": float(norm1),
                        "difference_l2_norm": float(err),
                        "relative_to_g1": float(err / max(norm1, np.finfo(float).tiny)),
                    }
                side_records.append({"side": side_name, "fields": fields})
            records.append(
                {
                    "material_transition_minus_to_plus": [int(minus_tag), int(plus_tag)],
                    "face_tile_count": int(len(indices)),
                    "area_nm2": float(np.sum(qw)),
                    "same_side_cross_grid_traces": side_records,
                }
            )
        normal = [0.0, 0.0, 0.0]
        normal[axis_index] = 1.0
        transitions.append(
            {
                "plane_names": surface["names"],
                "axis": ("x", "y", "z")[axis_index],
                "coordinate_nm": coordinate,
                "normal_from_minus_to_plus": normal,
                "face_tile_count": patch_count,
                "material_interface_tile_count": int(np.count_nonzero(material_face)),
                "material_tag_transition_groups": records,
            }
        )
    return {
        "method": "same-side G0/G1 FE trace difference at exact configured rectangular faces",
        "surfaces_checked": [surface["names"] for surface in surfaces],
        "coverage": {
            "configured_axis_aligned_grating_and_void_faces": True,
            "includes_void_gap_x_y_sidewalls": True,
            "candidate_face_tile_count": total_face_tiles,
            "material_interface_face_tile_count": total_material_tiles,
            "maximum_source_mesh_face_coordinate_offset_nm": maximum_source_face_offset,
            "axis_aligned_faces_only": True,
            "surfaces_skipped_at_mesh_exterior": exterior_surfaces,
        },
        "traces": transitions,
        "use": "interface-local h evidence; not included in the global field h gate",
    }
