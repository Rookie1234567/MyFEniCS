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
