#!/usr/bin/env python3
"""Bounded Y2/Y3 FE port-projection diagnostic; no solve or volume operator."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

TARGET_KEYS = (
    ("top", -4, 0, "p"),
    ("top", 0, 0, "s"),
    ("top", 4, 0, "p"),
    ("bottom", -4, 0, "p"),
    ("bottom", 0, 0, "s"),
    ("bottom", 4, 0, "p"),
)
TARGET_PARENT_INDICES = (17, 152, 289, 323, 458, 595)
DIAGNOSTIC_MPC_RELATIVE_TOLERANCE = 1.0e-10


def mode_key(row: Mapping[str, Any]) -> tuple[str, int, int, str]:
    return (str(row["side"]), int(row["m"]), int(row["n"]), str(row["polarization"]))


def _require_target_mode_order(selected_rows: Sequence[Mapping[str, Any]]) -> None:
    """Require the exact frozen signed-key order, independent of row container type."""
    actual = tuple(mode_key(row) for row in selected_rows)
    if actual != TARGET_KEYS:
        raise ValueError("cutoff-stage capture mode order differs from the frozen signed keys")


def select_target_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Select only the six requested rows from the saved 612-row identity."""
    if len(rows) != 612:
        raise ValueError("saved parent mode manifest must contain exactly 612 rows")
    wanted = set(TARGET_KEYS)
    found: dict[tuple[str, int, int, str], dict[str, Any]] = {}
    for row in rows:
        key = mode_key(row)
        if key not in wanted:
            continue
        if key in found:
            raise ValueError(f"duplicate saved target mode key: {key}")
        found[key] = dict(row)
    if set(found) != wanted:
        raise ValueError(f"saved parent manifest lacks target keys: {sorted(wanted-set(found))}")
    return sorted(found.values(), key=lambda row: int(row["mode_index"]))


def bind_exact_signed_mode_rows(
    parent_rows: Sequence[Mapping[str, Any]], auxiliary_rows: Sequence[Mapping[str, Any]]
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Pair only the six exact signed keys and prove their frozen parent indices."""
    selected = select_target_rows(parent_rows)
    expected = dict(zip(TARGET_KEYS, TARGET_PARENT_INDICES, strict=True))
    parent_by_key = {mode_key(row): row for row in selected}
    if len(parent_by_key) != len(selected):
        raise ValueError("parent target rows do not have unique signed mode keys")
    for key, expected_index in expected.items():
        if int(parent_by_key[key].get("mode_index", -1)) != expected_index:
            raise ValueError(f"parent signed mode key {key} is not at its frozen parent index")

    auxiliary_by_key: dict[tuple[str, int, int, str], dict[str, Any]] = {}
    for row in auxiliary_rows:
        try:
            key = mode_key(row)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("auxiliary row lacks an exact signed (side,m,n,pol) key") from exc
        if key in auxiliary_by_key:
            raise ValueError(f"duplicate auxiliary signed mode key: {key}")
        auxiliary_by_key[key] = dict(row)
    if not set(TARGET_KEYS).issubset(auxiliary_by_key):
        raise ValueError("auxiliary rows lack one or more exact signed target keys")

    pairs = []
    for parent in selected:
        key = mode_key(parent)
        auxiliary = auxiliary_by_key[key]
        if int(auxiliary.get("auxiliary_index", -1)) != int(parent["mode_index"]):
            raise ValueError(f"auxiliary signed mode key {key} has a mismatched parent index")
        pairs.append((dict(parent), auxiliary))
    return pairs


def preserve_no_carrier_diagnostic(
    case_result: dict[str, Any], gate: Mapping[str, Any], capture: Any
) -> dict[str, Any]:
    """Attach a diagnostic-only result without changing the frozen carrier gate."""
    gate_failed = gate.get("passed") is False
    try:
        facts = capture()
    except Exception as exc:  # noqa: BLE001 - preserve the original gate if optional capture fails
        facts = {"status": "CAPTURE_FAILED", "error": f"{type(exc).__name__}: {exc}"}
    case_result["diagnostic_only_signed_key_projection_capture"] = facts
    case_result["qualification"] = "DIAGNOSTIC_ONLY_NOT_CARRIER_OR_FIELD_QUALIFICATION"
    case_result["assembled_carrier_mode_count"] = 0
    case_result["projection_comparisons"] = []
    case_result["status"] = (
        "NO_CARRIER_COMPARISON" if gate_failed
        else "CARRIER_GATE_PASSED_BUT_CARRIER_NOT_BUILT_DIAGNOSTIC_ONLY"
    )
    return case_result


def decode_complex(value: Any) -> complex:
    if isinstance(value, Mapping) and set(value) >= {"real", "imag"}:
        return complex(float(value["real"]), float(value["imag"]))
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return complex(float(value[0]), float(value[1]))
    if isinstance(value, (int, float, np.number)):
        return complex(value)
    raise ValueError(f"unsupported serialized complex value: {type(value).__name__}")


def _jsonable(value: Any) -> Any:
    if isinstance(value, complex):
        return {"real": float(value.real), "imag": float(value.imag)}
    if isinstance(value, np.ndarray):
        return [_jsonable(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, bool, int, float)) or value is None:
        return value
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def match_cell_points(vtu_coordinates: np.ndarray, dof_coordinates: np.ndarray, tolerance: float) -> tuple[np.ndarray, float]:
    """Return a unique local VTU point for each DG DOF coordinate."""
    from scipy.spatial import cKDTree

    vtu = np.asarray(vtu_coordinates, dtype=np.float64)
    dofs = np.asarray(dof_coordinates, dtype=np.float64)
    if vtu.ndim != 2 or dofs.ndim != 2 or vtu.shape[1:] != (3,) or dofs.shape[1:] != (3,):
        raise ValueError("cell node coordinates must have shape (N,3)")
    if vtu.shape[0] != dofs.shape[0]:
        raise ValueError("VTU and DG6 cell node counts differ")
    distances, indices = cKDTree(vtu).query(dofs, k=1)
    indices = np.asarray(indices, dtype=np.int64)
    maximum = float(np.max(distances, initial=0.0))
    if not np.isfinite(maximum) or maximum > float(tolerance):
        raise ValueError(f"DG6/VTU cell node mismatch: maximum coordinate error {maximum}")
    if np.unique(indices).size != indices.size:
        raise ValueError("DG6 coordinate map is not one-to-one within a cell")
    return indices, maximum


def zero_slave_storage(full_values: np.ndarray, slave_indices: Sequence[int]) -> np.ndarray:
    """Copy full coefficients and zero only the declared local MPC slave slots."""
    values = np.asarray(full_values, dtype=np.complex128)
    slaves = np.asarray(slave_indices, dtype=np.int64).reshape(-1)
    if values.ndim != 1 or not np.all(np.isfinite(values)):
        raise ValueError("full FE storage must be a finite complex vector")
    if slaves.size and (int(slaves.min()) < 0 or int(slaves.max()) >= values.size):
        raise ValueError("MPC slave index is outside the FE storage vector")
    if np.unique(slaves).size != slaves.size:
        raise ValueError("MPC slave indices must be unique")
    result = values.copy()
    result[slaves] = 0.0
    return result


def relative_difference(reference: np.ndarray | complex, candidate: np.ndarray | complex) -> float:
    a = np.asarray(reference, dtype=np.complex128)
    b = np.asarray(candidate, dtype=np.complex128)
    denominator = max(float(np.linalg.norm(a)), float(np.linalg.norm(b)), np.finfo(float).tiny)
    return float(np.linalg.norm(a - b) / denominator)


def carrier_comparison_gate(
    *,
    data_finite: bool,
    global_roundtrip_relative: float | None,
    maximum_cell_roundtrip_relative: float | None,
    shared_trace_relative: float | None,
    maximum_facet_trace_relative: float | None,
    mpc_backsubstitution_relative: float | None,
    tolerance: float = DIAGNOSTIC_MPC_RELATIVE_TOLERANCE,
) -> dict[str, Any]:
    """Fail closed unless every reconstruction/trace/MPC witness is finite and small."""
    metrics = {
        "global_DG6_roundtrip_relative": global_roundtrip_relative,
        "maximum_cell_DG6_roundtrip_relative": maximum_cell_roundtrip_relative,
        "global_unaveraged_shared_tangential_trace_relative": shared_trace_relative,
        "maximum_facet_unaveraged_tangential_trace_relative": maximum_facet_trace_relative,
        "MPC_zero_slave_backsubstitution_relative": mpc_backsubstitution_relative,
    }
    checks = {}
    for name, value in metrics.items():
        finite = value is not None and bool(np.isfinite(float(value)))
        checks[name] = {
            "value": None if value is None else float(value),
            "finite": finite,
            "threshold": float(tolerance),
            "passed": bool(finite and float(value) <= tolerance),
        }
    failed = [name for name, check in checks.items() if not check["passed"]]
    if not data_finite:
        failed.insert(0, "input_or_reconstruction_nonfinite")
    return {
        "diagnostic_only_threshold": float(tolerance),
        "data_finite": bool(data_finite),
        "passed": bool(data_finite and not failed),
        "checks": checks,
        "failed_checks": failed,
        "interpretation": "all five relative witnesses and finite field data are required before carrier construction",
    }


def build_carrier_if_compatible(gate: Mapping[str, Any], builder: Any) -> Any | None:
    """The production caller uses this guard so failed witnesses cannot build a carrier."""
    if gate.get("passed") is not True:
        return None
    return builder()


def mode_selection_scope_facts() -> dict[str, Any]:
    return {
        "saved_parent_modes": 612,
        "explicitly_assembled_target_modes": 6,
        "other_parent_modes_not_evaluated_by_this_diagnostic": 606,
        "target_policy": "top/bottom m=-4,+4 n=0 p plus top/bottom m=n=0 s controls",
        "sparse_row_cutoff_before_after_evidence": "NOT_MEASURED",
    }


def _require_complex_scalar_type(scalar_type: Any) -> Any:
    if not np.issubdtype(np.dtype(scalar_type), np.complexfloating):
        raise TypeError("saved-field reconstruction requires complex DOLFINx scalar storage")
    return scalar_type


def _dg6_dtype_pair(geometry_dtype: Any, field_scalar_type: Any) -> tuple[np.dtype[Any], Any]:
    """Separate real Basix basis metadata from complex DOLFINx field storage."""
    basis_dtype = np.dtype(geometry_dtype)
    if not np.issubdtype(basis_dtype, np.floating):
        raise TypeError("DG6 Basix basis dtype must match real mesh geometry storage")
    field_dtype = _require_complex_scalar_type(field_scalar_type)
    return basis_dtype, field_dtype


def _build_complex_dg6_field(mesh: Any, fem: Any, element_factory: Any, field_scalar_type: Any) -> tuple[Any, Any, np.dtype[Any], Any]:
    basis_dtype, function_dtype = _dg6_dtype_pair(mesh.geometry.x.dtype, field_scalar_type)
    dg_element = element_factory("DG", mesh.basix_cell(), 6, shape=(3,), dtype=basis_dtype)
    dg_space = fem.functionspace(mesh, dg_element)
    dg_field = fem.Function(dg_space, name="E_total_reconstructed_DG6", dtype=function_dtype)
    return dg_space, dg_field, basis_dtype, function_dtype


def _facet_tangential_metrics(jump: np.ndarray, left: np.ndarray, right: np.ndarray) -> dict[str, Any]:
    jump_values = np.asarray(jump, dtype=np.complex128)
    left_values = np.asarray(left, dtype=np.complex128)
    right_values = np.asarray(right, dtype=np.complex128)
    finite = bool(
        np.all(np.isfinite(jump_values))
        and np.all(np.isfinite(left_values))
        and np.all(np.isfinite(right_values))
    )
    if not finite:
        return {
            "finite": False, "jump_l2": None, "scale_l2": None,
            "relative_l2": None, "maximum_absolute_component_error": None,
        }
    jump_l2 = float(np.linalg.norm(jump_values))
    scale_l2 = max(float(np.linalg.norm(left_values)), float(np.linalg.norm(right_values)))
    denominator = max(scale_l2, np.finfo(float).tiny)
    return {
        "finite": True,
        "jump_l2": jump_l2,
        "scale_l2": scale_l2,
        "relative_l2": jump_l2 / denominator,
        "maximum_absolute_component_error": float(np.max(np.abs(jump_values), initial=0.0)),
        "relative_denominator": denominator,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(_jsonable(payload), indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    os.replace(temporary, path)


def _axis_sha(values: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(values, dtype="<f8").tobytes()).hexdigest()


def _bbox_key(coordinates: np.ndarray) -> tuple[float, ...]:
    points = np.asarray(coordinates, dtype=np.float64)
    return tuple(float(value) for value in np.round(np.r_[points.min(axis=0), points.max(axis=0)], 10))


def _read_vtu_e(grid: Any, field_scale: float) -> tuple[np.ndarray, dict[str, Any]]:
    names = set(grid.point_data.keys())
    real_name, imag_name = "E_tot_V_per_m_real", "E_tot_V_per_m_imag"
    if real_name not in names or imag_name not in names:
        raise ValueError(f"VTU lacks {real_name}/{imag_name}; fields={sorted(names)}")
    real = np.asarray(grid.point_data[real_name], dtype=np.float64)
    imag = np.asarray(grid.point_data[imag_name], dtype=np.float64)
    if real.shape != imag.shape or real.shape != (int(grid.n_points), 3):
        raise ValueError("VTU E arrays must be matching (point_count,3) vectors")
    field = (real + 1j * imag) / float(field_scale)
    incident = np.asarray(grid.field_data.get("incident_e0_V_per_m", []), dtype=np.float64).reshape(-1)
    return field, {
        "point_count": int(grid.n_points),
        "incident_e0_V_per_m": incident.tolist(),
        "finite_complex_E_values": bool(np.all(np.isfinite(field))),
        "maximum_absolute_E_component": (
            float(np.max(np.abs(field), initial=0.0)) if np.all(np.isfinite(field)) else None
        ),
    }


def _basix_element_identity(function_space: Any) -> dict[str, Any]:
    element = function_space.element.basix_element
    matrix = np.asarray(element.interpolation_matrix)
    points = np.asarray(element.points)
    return {
        "family": str(element.family),
        "degree": int(element.degree),
        "dimension": int(element.dim),
        "value_size": int(element.value_size),
        "value_shape": list(element.value_shape),
        "mapping": str(element.map_type),
        "lagrange_variant": str(getattr(element, "lagrange_variant", "unknown")),
        "dof_transformations_are_identity": bool(element.dof_transformations_are_identity),
        "dof_transformations_are_permutations": bool(element.dof_transformations_are_permutations),
        "interpolation_point_count": int(points.shape[0]),
        "interpolation_matrix_shape": list(matrix.shape),
        "coefficient_reconstruction_api": "dolfinx.fem.Function.interpolate(DG6 Function into the production N1E6 space)",
    }


def _per_cell_roundtrip(dg_space: Any, original: Any, reconstructed: Any, cell_dofs: Sequence[np.ndarray]) -> dict[str, Any]:
    original_values = np.asarray(original.x.array, dtype=np.complex128).reshape(-1, 3)
    reconstructed_values = np.asarray(reconstructed.x.array, dtype=np.complex128).reshape(-1, 3)
    if not np.all(np.isfinite(original_values)) or not np.all(np.isfinite(reconstructed_values)):
        return {
            "cell_count": len(cell_dofs), "finite": False,
            "maximum_cell_relative_L2_error": None,
            "maximum_cell_relative_error_cell": None,
            "maximum_cell_absolute_error": None,
            "maximum_cell_absolute_error_cell": None,
            "maximum_cell_absolute_error_scale": None,
            "maximum_cell_relative_error_absolute_L2": None,
            "maximum_cell_relative_error_reference_scale_L2": None,
            "maximum_cell_relative_error_denominator": None,
        }
    error = reconstructed_values - original_values
    rows = []
    for cell, dofs in enumerate(cell_dofs):
        local_dofs = np.asarray(dofs, dtype=np.int64)
        local_error = error[local_dofs]
        local_reference = original_values[local_dofs]
        relative = float(np.linalg.norm(local_error) / max(float(np.linalg.norm(local_reference)), np.finfo(float).tiny))
        maximum = float(np.max(np.abs(local_error), initial=0.0))
        scale = float(np.linalg.norm(local_reference))
        error_l2 = float(np.linalg.norm(local_error))
        rows.append((relative, maximum, int(cell), scale, error_l2))
    default_row = (0.0, 0.0, -1, 0.0, 0.0)
    maximum_relative_row = max(rows, key=lambda row: row[0], default=default_row)
    maximum_absolute_row = max(rows, key=lambda row: row[1], default=default_row)
    return {
        "cell_count": len(rows),
        "finite": True,
        "maximum_cell_relative_L2_error": float(maximum_relative_row[0]),
        "maximum_cell_relative_error_cell": int(maximum_relative_row[2]),
        "maximum_cell_relative_error_absolute_L2": float(maximum_relative_row[4]),
        "maximum_cell_relative_error_reference_scale_L2": float(maximum_relative_row[3]),
        "maximum_cell_relative_error_denominator": max(float(maximum_relative_row[3]), np.finfo(float).tiny),
        "maximum_cell_absolute_error": float(maximum_absolute_row[1]),
        "maximum_cell_absolute_error_cell": int(maximum_absolute_row[2]),
        "maximum_cell_absolute_error_scale": float(maximum_absolute_row[3]),
        "denominator_policy": "cell DG6 coefficient L2 norm, with tiny absolute fallback for relative error",
    }


def _map_vtu_to_dg6(mesh: Any, dg_space: Any, dg_function: Any, grid: Any, vtu_field: np.ndarray) -> tuple[dict[str, Any], list[np.ndarray]]:
    from dolfinx.mesh import entities_to_geometry

    if int(mesh.comm.size) != 1:
        raise ValueError("bounded reconstruction is fixed to MPI1")
    tdim = int(mesh.topology.dim)
    cell_map = mesh.topology.index_map(tdim)
    cell_count = int(cell_map.size_local)
    if cell_count != int(grid.n_cells):
        raise ValueError("VTU/DOLFINx cell counts differ")
    if np.asarray(grid.celltypes).shape != (cell_count,) or not np.all(np.asarray(grid.celltypes) == 72):
        raise ValueError("VTU cells are not all VTK_LAGRANGE_HEXAHEDRON")
    geometry_cells = entities_to_geometry(mesh, tdim, np.arange(cell_count, dtype=np.int32), False)
    geometry_coordinates = np.asarray(mesh.geometry.x, dtype=np.float64)
    cell_by_bbox: dict[tuple[float, ...], int] = {}
    for cell in range(cell_count):
        key = _bbox_key(geometry_coordinates[np.asarray(geometry_cells[cell], dtype=np.int64)])
        if key in cell_by_bbox:
            raise ValueError("physical cell bounding boxes are not unique")
        cell_by_bbox[key] = cell
    vtu_points = np.asarray(grid.points, dtype=np.float64)
    vtu_cell_for_mesh_cell = np.full(cell_count, -1, dtype=np.int64)
    vtu_cells: list[np.ndarray] = []
    for vtu_cell in range(cell_count):
        cell = grid.get_cell(vtu_cell)
        point_ids = np.asarray(cell.point_ids, dtype=np.int64)
        if point_ids.size != 343:
            raise ValueError("each VTU DG6 hex must carry exactly 343 cell points")
        key = _bbox_key(vtu_points[point_ids])
        mesh_cell = cell_by_bbox.get(key)
        if mesh_cell is None or vtu_cell_for_mesh_cell[mesh_cell] >= 0:
            raise ValueError("VTU cells do not map one-to-one to actual mesh cells")
        vtu_cell_for_mesh_cell[mesh_cell] = vtu_cell
        vtu_cells.append(point_ids)
    if np.any(vtu_cell_for_mesh_cell < 0):
        raise ValueError("one or more actual mesh cells have no VTU cell")

    block_size = int(dg_space.dofmap.bs)
    if block_size != 3:
        raise ValueError(f"expected blocked vector DG6 dofmap with block size 3, got {block_size}")
    dof_coordinates = np.asarray(dg_space.tabulate_dof_coordinates(), dtype=np.float64).reshape(-1, 3)
    dof_values = dg_function.x.array.reshape(-1, 3)
    if not np.issubdtype(dof_values.dtype, np.complexfloating):
        raise TypeError("DG6 VTU target storage must preserve the complex field")
    if dof_values.shape[0] != dof_coordinates.shape[0]:
        raise ValueError("DG6 coordinate/value block counts differ")
    dof_to_vtu = np.full(dof_coordinates.shape[0], -1, dtype=np.int64)
    maximum_node_error = 0.0
    tolerance = 2.0e-10 * max(float(np.ptp(np.asarray(grid.points), axis=0).max()), 1.0)
    for mesh_cell in range(cell_count):
        dofs = np.asarray(dg_space.dofmap.cell_dofs(mesh_cell), dtype=np.int64)
        if dofs.size != 343:
            raise ValueError("each vector DG6 cell must expose 343 blocked scalar nodes")
        point_ids = vtu_cells[int(vtu_cell_for_mesh_cell[mesh_cell])]
        local_point_index, local_error = match_cell_points(
            vtu_points[point_ids], dof_coordinates[dofs], tolerance
        )
        maximum_node_error = max(maximum_node_error, local_error)
        if np.any(dof_to_vtu[dofs] >= 0):
            raise ValueError("DG6 discontinuous cell dofs unexpectedly overlap")
        point_map = point_ids[local_point_index]
        dof_to_vtu[dofs] = point_map
        dof_values[dofs] = vtu_field[point_map]
    dg_function.x.scatter_forward()
    if np.any(dof_to_vtu < 0):
        raise ValueError("not every DG6 storage node was bound to one VTU point")
    return {
        "mesh_cells": cell_count,
        "VTU_cells": int(grid.n_cells),
        "VTU_points": int(grid.n_points),
        "VTU_cell_type": 72,
        "points_per_cell": 343,
        "one_to_one_cell_map": True,
        "one_to_one_cell_local_node_map": True,
        "maximum_cell_local_coordinate_error_nm": maximum_node_error,
        "coordinate_match_tolerance_nm": tolerance,
    }, [np.asarray(dg_space.dofmap.cell_dofs(c), dtype=np.int64) for c in range(cell_count)]


def _shared_tangential_trace(mesh: Any, mesh_data: Any, dg_space: Any, dg_function: Any, cell_dofs: list[np.ndarray]) -> dict[str, Any]:
    """Compare unaveraged DG6 vectors at common internal-face coordinates."""
    from dolfinx.mesh import entities_to_geometry
    from scipy.spatial import cKDTree

    tdim = int(mesh.topology.dim)
    fdim = tdim - 1
    mesh.topology.create_connectivity(fdim, tdim)
    f2c = mesh.topology.connectivity(fdim, tdim)
    mesh.topology.create_connectivity(tdim, fdim)
    _cell_to_facets = mesh.topology.connectivity(tdim, fdim)
    facet_count = int(mesh.topology.index_map(fdim).size_local)
    domain_scale = max(float(np.ptp(mesh.geometry.x, axis=0).max()), 1.0)
    face_tolerance = 2.0e-10 * domain_scale
    dof_coords = np.asarray(dg_space.tabulate_dof_coordinates(), dtype=np.float64).reshape(-1, 3)
    values = dg_function.x.array.reshape(-1, 3)
    if not np.all(np.isfinite(dof_coords)) or not np.all(np.isfinite(values)):
        return {
            "finite": False, "faces": 0, "nodes": 0,
            "relative_l2_tangential_jump": None,
            "maximum_facet_relative_l2_tangential_jump": None,
            "worst_absolute_facet": None,
            "worst_relative_facet": None,
            "denominator_policy": "max of the two unaveraged face trace L2 norms, tiny absolute fallback",
        }
    cell_tags = np.full(int(mesh.topology.index_map(tdim).size_local), int(mesh_data.cell_tags.values[0]), dtype=np.int32)
    cell_tags[np.asarray(mesh_data.cell_tags.indices, dtype=np.int64)] = np.asarray(mesh_data.cell_tags.values, dtype=np.int32)
    totals = {
        "finite": True, "faces": 0, "nodes": 0, "sum_jump_sq": 0.0,
        "sum_trace_sq": 0.0, "max_abs_jump": 0.0, "max_face": None,
        "max_facet_relative": 0.0, "worst_absolute_facet": None,
        "worst_relative_facet": None, "x25_worst_relative_facet_two_side_Ey_Ez": None,
        "x25_max_relative": -1.0, "by_material_pair": {},
    }
    for facet in range(facet_count):
        adjacent = np.asarray(f2c.links(facet), dtype=np.int64)
        if adjacent.size != 2:
            continue
        geom = entities_to_geometry(mesh, fdim, np.asarray([facet], dtype=np.int32), False)[0]
        face_xyz = np.asarray(mesh.geometry.x, dtype=np.float64)[np.asarray(geom, dtype=np.int64)]
        extent = np.ptp(face_xyz, axis=0)
        axis = int(np.argmin(extent))
        plane = float(np.mean(face_xyz[:, axis]))
        face_payload = []
        for cell in adjacent:
            dofs = cell_dofs[int(cell)]
            coords = dof_coords[dofs]
            tol = face_tolerance
            mask = np.abs(coords[:, axis] - plane) <= tol
            face_coords = coords[mask]
            face_values = values[dofs][mask]
            if face_coords.shape[0] != 49:
                raise ValueError(f"expected 49 DG6 face nodes, got {face_coords.shape[0]}")
            face_payload.append((face_coords, face_values))
        left_xyz, left_values = face_payload[0]
        right_xyz, right_values = face_payload[1]
        distances, permutation = cKDTree(right_xyz).query(left_xyz, k=1)
        if np.unique(permutation).size != 49 or float(np.max(distances)) > tol:
            raise ValueError("adjacent cell DG6 face nodes do not match uniquely")
        tangent_components = [component for component in range(3) if component != axis]
        jump = left_values[:, tangent_components] - right_values[permutation][:, tangent_components]
        left_tangent = left_values[:, tangent_components]
        right_tangent = right_values[permutation][:, tangent_components]
        face_metrics = _facet_tangential_metrics(jump, left_tangent, right_tangent)
        if not face_metrics["finite"]:
            totals["finite"] = False
            continue
        face_jump_l2 = float(face_metrics["jump_l2"])
        face_scale = float(face_metrics["scale_l2"])
        face_relative = float(face_metrics["relative_l2"])
        face_max = float(face_metrics["maximum_absolute_component_error"])
        jump_sq = face_jump_l2**2
        trace_sq = float(np.vdot(left_tangent, left_tangent).real + np.vdot(right_tangent, right_tangent).real)
        pair = "-".join(str(int(value)) for value in sorted((cell_tags[int(adjacent[0])], cell_tags[int(adjacent[1])])))
        face_identity = {
            "facet": int(facet), "cells": adjacent.tolist(),
            "axis_normal": ["x", "y", "z"][axis], "plane_nm": plane,
            "material_tags": [int(cell_tags[int(x)]) for x in adjacent],
            "tangential_jump_l2": face_jump_l2,
            "tangential_trace_scale_l2": face_scale,
            "relative_denominator": face_metrics["relative_denominator"],
            "relative_tangential_jump_l2": face_relative,
            "maximum_absolute_tangential_component_error": face_max,
        }
        if axis == 0 and abs(plane - 25.0) <= face_tolerance and face_relative > float(totals["x25_max_relative"]):
            centers = {}
            for cell in adjacent:
                cell_geom = entities_to_geometry(
                    mesh, tdim, np.asarray([int(cell)], dtype=np.int32), False
                )[0]
                cell_xyz = np.asarray(mesh.geometry.x, dtype=np.float64)[
                    np.asarray(cell_geom, dtype=np.int64)
                ]
                centers[int(cell)] = float(np.mean(cell_xyz[:, 0]))
            first_cell, second_cell = (int(adjacent[0]), int(adjacent[1]))
            if centers[first_cell] <= centers[second_cell]:
                left_cell, right_cell = first_cell, second_cell
                left_xyz_saved = left_xyz
                left_tangent_saved = left_tangent
                right_tangent_saved = right_tangent
            else:
                left_cell, right_cell = second_cell, first_cell
                left_xyz_saved = left_xyz
                left_tangent_saved = right_values[permutation][:, tangent_components]
                right_tangent_saved = left_values[:, tangent_components]
            totals["x25_max_relative"] = face_relative
            totals["x25_worst_relative_facet_two_side_Ey_Ez"] = {
                **face_identity,
                "left_cell_id": left_cell,
                "right_cell_id": right_cell,
                "left_to_right_normal": [1.0, 0.0, 0.0],
                "left_cell_centroid_x_nm": centers[left_cell],
                "right_cell_centroid_x_nm": centers[right_cell],
                "face_coordinates_xyz_nm": left_xyz_saved,
                "tangential_component_names": ["Ey", "Ez"],
                "left_Ey_Ez_complex": left_tangent_saved,
                "right_Ey_Ez_complex": right_tangent_saved,
                "left_minus_right_Ey_Ez_complex": left_tangent_saved - right_tangent_saved,
                "parity_analysis": "NOT_COMPUTED; no vector mirror parity assumption is applied",
            }
        group = totals["by_material_pair"].setdefault(pair, {"faces": 0, "sum_jump_sq": 0.0, "sum_trace_sq": 0.0, "max_abs_jump": 0.0, "max_relative_jump": 0.0, "worst_relative_facet": None})
        group["faces"] += 1
        group["sum_jump_sq"] += jump_sq
        group["sum_trace_sq"] += trace_sq
        group["max_abs_jump"] = max(float(group["max_abs_jump"]), face_max)
        if face_relative > float(group["max_relative_jump"]):
            group["max_relative_jump"] = face_relative
            group["worst_relative_facet"] = face_identity
        totals["faces"] += 1
        totals["nodes"] += 49
        totals["sum_jump_sq"] += jump_sq
        totals["sum_trace_sq"] += trace_sq
        if face_max > float(totals["max_abs_jump"]):
            totals["max_abs_jump"] = face_max
            totals["max_face"] = {"facet": int(facet), "cells": adjacent.tolist(), "axis_normal": ["x", "y", "z"][axis], "plane_nm": plane, "material_tags": [int(cell_tags[int(x)]) for x in adjacent]}
        if face_max > (totals["worst_absolute_facet"] or {}).get("maximum_absolute_tangential_component_error", -1.0):
            totals["worst_absolute_facet"] = face_identity
        if face_relative > totals["max_facet_relative"]:
            totals["max_facet_relative"] = face_relative
            totals["worst_relative_facet"] = face_identity
    totals["relative_l2_tangential_jump"] = float(np.sqrt(totals["sum_jump_sq"]) / max(np.sqrt(totals["sum_trace_sq"]), np.finfo(float).tiny))
    totals["maximum_facet_relative_l2_tangential_jump"] = float(totals["max_facet_relative"])
    totals["worst_facet_absolute_error_and_scale"] = totals["worst_absolute_facet"]
    totals["worst_facet_relative_error_and_scale"] = totals["worst_relative_facet"]
    totals.pop("x25_max_relative", None)
    for pair, group in totals["by_material_pair"].items():
        group["relative_l2_tangential_jump"] = float(np.sqrt(group["sum_jump_sq"]) / max(np.sqrt(group["sum_trace_sq"]), np.finfo(float).tiny))
        group["maximum_facet_relative_l2_tangential_jump"] = float(group["max_relative_jump"])
    totals["interpretation"] = "cellwise DG6 coordinate trace comparison; no averaging, projection repair, or canonical H(curl) trace certificate"
    totals["denominator_policy"] = "each facet relative error uses jump L2 divided by the larger adjacent unaveraged tangential-trace L2 norm; tiny absolute fallback"
    return totals


def _signed_key_surface_projection_capture(
    *,
    case: Mapping[str, Any],
    cfg: Any,
    mesh: Any,
    mesh_data: Any,
    modes: Sequence[Any],
    selected_rows: Sequence[Mapping[str, Any]],
    live_mode_rows: Sequence[Mapping[str, Any]],
    selected_subset_sha256: str,
    saved_aux_by_key: Mapping[tuple[str, int, int, str], Mapping[str, Any]],
    dg_field: Any,
    reconstructed_n1e_field: Any,
    fem: Any,
    mpi: Any,
    jit_options: Mapping[str, Any],
) -> dict[str, Any]:
    """Compute six exact-key DG6/N1E6 q28 scalar projections without a carrier."""
    import ufl
    from petsc4py import PETSc

    from src.solvers.dtn_port_3d import (
        _dtn_surface_quadrature_degree,
        _mode_boundary_phase,
        _mode_projection_denominator,
        _set_scalar_constant,
        _with_quadrature_degree,
    )

    if len(modes) != 6 or len(selected_rows) != 6 or len(live_mode_rows) != 6:
        raise ValueError("signed-key projection capture requires exactly six modes")
    if [mode_key(row) for row in selected_rows] != [mode_key(row) for row in live_mode_rows]:
        raise ValueError("live mode rows do not preserve the exact signed parent-key order")
    if tuple(int(row["mode_index"]) for row in selected_rows) != TARGET_PARENT_INDICES:
        raise ValueError("signed target parent indices differ from the frozen six indices")
    if int(_dtn_surface_quadrature_degree(cfg, modes)) != 28:
        raise ValueError("diagnostic projection must retain the saved q28 surface rule")

    x = ufl.SpatialCoordinate(mesh)
    ds = ufl.Measure("ds", domain=mesh, subdomain_data=mesh_data.facet_tags)
    alpha_c = fem.Constant(mesh, PETSc.ScalarType(0.0))
    gamma_c = fem.Constant(mesh, PETSc.ScalarType(0.0))
    kz_c = fem.Constant(mesh, PETSc.ScalarType(0.0))
    ex_c = fem.Constant(mesh, PETSc.ScalarType(0.0))
    ey_c = fem.Constant(mesh, PETSc.ScalarType(0.0))
    phase = ufl.exp(1j * alpha_c * x[0] + 1j * gamma_c * x[1] + 1j * kz_c * x[2])
    reference = ufl.as_vector((ex_c * phase, ey_c * phase, PETSc.ScalarType(0.0)))
    forms: dict[tuple[str, str], Any] = {}
    for side, tag in (("top", cfg.tags.z_max), ("bottom", cfg.tags.z_min)):
        for field_name, field in (
            ("saved_DG6_from_VTU", dg_field),
            ("reconstructed_N1E6_from_DG6", reconstructed_n1e_field),
        ):
            tangent_field = ufl.as_vector((field[0], field[1], PETSc.ScalarType(0.0)))
            expression = ufl.inner(tangent_field, reference) * ds(tag)
            forms[(side, field_name)] = fem.form(
                _with_quadrature_degree(expression, 28), jit_options=dict(jit_options)
            )

    live_by_key = {mode_key(row): row for row in live_mode_rows}
    results = []
    for row, mode in zip(selected_rows, modes, strict=True):
        key = mode_key(row)
        live_row = live_by_key[key]
        auxiliary = dict(saved_aux_by_key[key])
        if int(auxiliary.get("auxiliary_index", -1)) != int(row["mode_index"]):
            raise ValueError(f"saved auxiliary index does not bind exact signed key {key}")
        _set_scalar_constant(alpha_c, mode.alpha)
        _set_scalar_constant(gamma_c, mode.gamma)
        _set_scalar_constant(kz_c, mode.k_vector[2])
        _set_scalar_constant(ex_c, mode.e_vector[0])
        _set_scalar_constant(ey_c, mode.e_vector[1])
        numerator_by_field = {}
        for field_name in ("saved_DG6_from_VTU", "reconstructed_N1E6_from_DG6"):
            local = fem.assemble_scalar(forms[(str(mode.side), field_name)])
            numerator = complex(mesh.comm.allreduce(local, op=mpi.SUM))
            if not np.isfinite(numerator):
                raise FloatingPointError(f"non-finite q28 numerator for {key}/{field_name}")
            numerator_by_field[field_name] = numerator
        H = float(_mode_projection_denominator(mode, cfg))
        P = complex(_mode_boundary_phase(mode, cfg))
        if not np.isfinite(H) or H <= 0.0 or not np.isfinite(P):
            raise FloatingPointError(f"non-finite q28 H or boundary phase for {key}")
        amplitudes = {
            name: {
                "N_complex": numerator,
                "H": H,
                "a_N_over_H_complex": numerator / H,
                "P_boundary_phase_complex": P,
                "aP_boundary_amplitude_complex": numerator / H * P,
            }
            for name, numerator in numerator_by_field.items()
        }
        saved_phase = decode_complex(auxiliary["boundary_phase"])
        saved_aux = decode_complex(auxiliary["auxiliary_amplitude_total_projection"])
        saved_boundary = decode_complex(auxiliary["outgoing_amplitude_at_boundary"])
        results.append(
            {
                "exact_signed_mode_key": list(key),
                "parent_mode_index": int(row["mode_index"]),
                "parent_mode_manifest_sha256": str(case["sha256"]["parent_modes"]),
                "parent_ordered_mode_manifest_sha256": str(case["mode_sha256"]),
                "six_mode_subset_sha256": selected_subset_sha256,
                "live_mode_identity": _jsonable(live_row),
                "beta_complex": complex(mode.beta),
                "k_vector_complex_xyz": tuple(complex(value) for value in mode.k_vector),
                "eigenvector_e_complex_xyz": tuple(complex(value) for value in mode.e_vector),
                "actual_alpha_gamma_kz_complex": (
                    complex(mode.alpha), complex(mode.gamma), complex(mode.k_vector[2])
                ),
                "kx_over_k0_complex": complex(mode.alpha) / complex(cfg.k0),
                "boundary_reference_phase_P_complex": P,
                "saved_exact_key_auxiliary_row": _jsonable(auxiliary),
                "saved_exact_key_auxiliary_amplitude_complex": saved_aux,
                "saved_exact_key_boundary_phase_complex": saved_phase,
                "saved_exact_key_outgoing_boundary_amplitude_complex": saved_boundary,
                "saved_auxiliary_phase_difference_complex": saved_phase - P,
                "saved_vs_reconstructed_projection": amplitudes,
                "reconstructed_N1E6_minus_saved_DG6_N_complex": (
                    numerator_by_field["reconstructed_N1E6_from_DG6"]
                    - numerator_by_field["saved_DG6_from_VTU"]
                ),
                "complex_inner_conjugates_second_argument": True,
                "surface_quadrature_degree": 28,
                "field_scope": "saved VTU -> DG6 -> N1E6 reconstruction; not original FE coefficients or a carrier qualification",
            }
        )
    return {
        "status": "SIX_SIGNED_KEY_Q28_PROJECTIONS_CAPTURED_DIAGNOSTIC_ONLY",
        "carrier_qualification": "NOT_GRANTED; original V4 joint gate remains failed",
        "full_612_mode_carrier_built": False,
        "production_carrier_or_matrix_or_factor_or_solve_built": False,
        "zero_slave_Du": "NOT_RUN_GATE_BLOCKED",
        "mirror_parity": "NOT_COMPUTED; no component parity or kx zeroing applied",
        "six_exact_signed_key_results": results,
    }


def _hash_array_view(array: np.ndarray) -> str:
    values = np.asarray(array)
    if not values.flags.c_contiguous:
        raise ValueError("diagnostic field identity requires a contiguous view")
    digest = hashlib.sha256()
    digest.update(memoryview(values).cast("B"))
    return digest.hexdigest()


def _complex_sample(rows: np.ndarray, values: np.ndarray, count: int = 8) -> list[dict[str, Any]]:
    if rows.size == 0:
        return []
    order = np.argsort(np.abs(values), kind="stable")[-min(count, rows.size) :][::-1]
    return [
        {
            "global_row": int(rows[index]),
            "value": complex(values[index]),
            "absolute_value": float(abs(values[index])),
        }
        for index in order
    ]


def _snapshot_surface_component(vector: Any, workspace: Any, index_map: Any) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Copy only the owned structural support before the one-Vec workspace is reused."""
    start, end = map(int, vector.getOwnershipRange())
    owned_count = end - start
    support = np.asarray(workspace.owned_support, dtype=np.int64)
    if support.size and (int(support.min()) < 0 or int(support.max()) >= owned_count):
        raise ValueError("workspace support is outside the PETSc owned row interval")
    with vector.localForm() as local_form:
        local_values = np.asarray(local_form.array_r, dtype=np.complex128)
        expected_local_size = int(workspace.facts["vector_local_storage_rows"])
        if local_values.size != expected_local_size or local_values.size < owned_count:
            raise ValueError("surface Vec owned+ghost storage differs from the workspace contract")
        owned_values = local_values[:owned_count]
        raw_values = owned_values[support].copy()
        outside = np.ones(owned_count, dtype=bool)
        outside[support] = False
        outside_values = owned_values[outside]
        ghost_values = local_values[owned_count:]
        ghost_rows = np.asarray(index_map.ghosts, dtype=np.int64).reshape(-1)
        if ghost_values.size != ghost_rows.size:
            raise ValueError("surface Vec ghost values differ from the function-space ghost map")
        comparable = (ghost_rows >= start) & (ghost_rows < end)
        if np.any(comparable):
            expected_ghost_values = owned_values[ghost_rows[comparable] - start]
            observed_ghost_values = ghost_values[comparable]
            ghost_values_match_owned = bool(np.array_equal(expected_ghost_values, observed_ghost_values))
        else:
            ghost_values_match_owned = None
        facts = {
            "owned_global_range": [start, end],
            "owned_row_count": owned_count,
            "support_owned_row_count": int(support.size),
            "support_ghost_row_count": int(workspace.facts["support_ghost_rows"]),
            "local_ghost_row_count": int(ghost_values.size),
            "local_ghost_nonzero_count_after_forward_update": int(np.count_nonzero(ghost_values)),
            "local_ghost_maximum_abs_after_forward_update": float(np.max(np.abs(ghost_values), initial=0.0)),
            "ghosts_with_same_rank_owner_checked": int(np.count_nonzero(comparable)),
            "ghost_values_match_same_rank_owned_values": ghost_values_match_owned,
            "owned_nonzero_entries_outside_structural_support": int(np.count_nonzero(outside_values)),
            "owned_maximum_abs_outside_structural_support": float(np.max(np.abs(outside_values), initial=0.0)),
            "raw_support_values_copied_before_workspace_reuse": True,
            "production_field_vector_written_or_cleared": False,
        }
    rows = start + support
    return rows.astype(np.int64, copy=False), raw_values, facts


def _cutoff_stage_capture(
    *,
    case: Mapping[str, Any],
    mpc_backsubstitution_facts: Mapping[str, Any],
    cfg: Any,
    mesh: Any,
    mesh_data: Any,
    function_space: Any,
    mpc: Any,
    modes: Sequence[Any],
    selected_rows: Sequence[Mapping[str, Any]],
    saved_aux_by_key: Mapping[tuple[str, int, int, str], Mapping[str, Any]],
    dg_field: Any,
    reconstructed_n1e_field: Any,
    reconstruction_facts: Mapping[str, Any],
    zero_slave_storage_field_values: np.ndarray,
    mpc_backsubstituted_field: Any,
    fem: Any,
    mpi: Any,
    jit_options: Mapping[str, Any],
    on_progress: Any,
) -> dict[str, Any]:
    """Measure production component/merge cutoffs on one saved-field storage vector."""
    import ufl
    from d13_cutoff_stage_accounting import (
        ABSOLUTE_FLOOR,
        RELATIVE_TOLERANCE,
        arrays_match,
        cutoff_facts,
        expected_component_filter,
        expected_merged_filter,
        route_cutoff_accounting,
    )
    from petsc4py import PETSc

    from src.solvers.dtn_port_3d import (
        _combine_owned_entries,
        _dtn_surface_quadrature_degree,
        _mode_boundary_phase,
        _mode_projection_denominator,
        _set_scalar_constant,
        _SurfaceMpcVectorWorkspace,
        _traction_vector,
        _vec_nonzero_owned_entries,
        _with_quadrature_degree,
    )
    from src.solvers.fullspace_dtn_action import _dtn_component_phase_key
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import _surface_assemblers

    if len(modes) != 6 or len(selected_rows) != 6:
        raise ValueError("cutoff-stage capture requires exactly six signed modes")
    _require_target_mode_order(selected_rows)
    if int(_dtn_surface_quadrature_degree(cfg, modes)) != 28:
        raise ValueError("cutoff-stage capture must preserve q28")
    storage = np.asarray(zero_slave_storage_field_values, dtype=np.complex128).reshape(-1)
    if not np.isfinite(storage).all():
        raise FloatingPointError("zero-slave storage is not finite")
    storage_sha = _hash_array_view(storage)
    dg_before_sha = _hash_array_view(np.asarray(dg_field.x.array))
    n1_before_sha = _hash_array_view(np.asarray(reconstructed_n1e_field.x.array))
    expanded_before_sha = _hash_array_view(np.asarray(mpc_backsubstituted_field.x.array))

    zero_slave_field = fem.Function(
        function_space,
        name="diagnostic_zero_slave_storage_only",
        dtype=np.asarray(zero_slave_storage_field_values).dtype,
    )
    if zero_slave_field.x.array.shape != storage.shape:
        raise ValueError("zero-slave storage shape differs from the diagnostic function")
    zero_slave_field.x.array[:] = storage
    zero_slave_field.x.scatter_forward()
    zero_slave_field_sha = _hash_array_view(np.asarray(zero_slave_field.x.array))
    expanded_storage_sha = _hash_array_view(np.asarray(mpc_backsubstituted_field.x.array))
    if expanded_storage_sha != expanded_before_sha:
        raise RuntimeError("MPC-expanded field changed while creating the zero-slave reference")

    assemblers = _surface_assemblers(
        function_space,
        mesh_data,
        cfg,
        28,
        mpc=mpc,
        jit_options=dict(jit_options),
    )
    workspace = _SurfaceMpcVectorWorkspace(
        function_space, mesh_data, mpc, assemblers, collect_timings=True
    )
    component_cache: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    cache_hits = 0
    cache_misses = 0
    component_assemblies = 0
    all_mode_results: list[dict[str, Any]] = []
    integrity_failures: list[str] = []

    x = ufl.SpatialCoordinate(mesh)
    ds = ufl.Measure("ds", domain=mesh, subdomain_data=mesh_data.facet_tags)
    alpha_c = fem.Constant(mesh, PETSc.ScalarType(0.0))
    gamma_c = fem.Constant(mesh, PETSc.ScalarType(0.0))
    kz_c = fem.Constant(mesh, PETSc.ScalarType(0.0))
    ex_c = fem.Constant(mesh, PETSc.ScalarType(0.0))
    ey_c = fem.Constant(mesh, PETSc.ScalarType(0.0))
    reference = ufl.as_vector(
        (
            ex_c * ufl.exp(1j * alpha_c * x[0] + 1j * gamma_c * x[1] + 1j * kz_c * x[2]),
            ey_c * ufl.exp(1j * alpha_c * x[0] + 1j * gamma_c * x[1] + 1j * kz_c * x[2]),
            PETSc.ScalarType(0.0),
        )
    )
    field_views = {
        "saved_DG6_reference": dg_field,
        "reconstructed_N1E6_reference": reconstructed_n1e_field,
        "zero_slave_storage_only_not_full_primal": zero_slave_field,
        "MPC_backsubstituted_full_primal_from_same_storage": mpc_backsubstituted_field,
    }
    direct_forms: dict[tuple[str, str], Any] = {}
    for side, tag in (("top", cfg.tags.z_max), ("bottom", cfg.tags.z_min)):
        for field_name, field in field_views.items():
            tangent = ufl.as_vector((field[0], field[1], PETSc.ScalarType(0.0)))
            form = ufl.inner(tangent, reference) * ds(tag)
            direct_forms[(side, field_name)] = fem.form(
                _with_quadrature_degree(form, 28), jit_options=dict(jit_options)
            )

    workspace_facts = dict(workspace.facts)
    workspace_facts.update(
        {
            "mpi_size": int(mesh.comm.size),
            "vector_owned_range": list(map(int, workspace.vector.getOwnershipRange())),
            "ghost_update_sequence": "production workspace reverse-add then forward-insert before snapshot",
        }
    )

    try:
        for row, mode in zip(selected_rows, modes, strict=True):
            key = mode_key(row)
            phase_key = _dtn_component_phase_key(mode)
            cache_facts = {"production_phase_key": phase_key, "cache_hit": phase_key in component_cache}
            if phase_key in component_cache:
                cache_hits += 1
                component_facts = component_cache[phase_key]
            else:
                cache_misses += 1
                component_facts = []
                for component, component_name in ((0, "x"), (1, "y")):
                    assembler = assemblers[(str(mode.side), component)]
                    _set_scalar_constant(assembler.alpha, mode.alpha)
                    _set_scalar_constant(assembler.gamma, mode.gamma)
                    _set_scalar_constant(assembler.kz, mode.k_vector[2])
                    vector = workspace.assemble(assembler.form, mpc)
                    raw_rows, raw_values, vector_facts = _snapshot_surface_component(
                        vector, workspace, function_space.dofmap.index_map
                    )
                    # Capture the raw component before any next workspace assembly.
                    component_assemblies += 1
                    actual_rows, actual_values = _vec_nonzero_owned_entries(
                        vector, support=workspace.owned_support, relative_tol=RELATIVE_TOLERANCE
                    )
                    expected_rows, expected_values, cutoff = expected_component_filter(
                        raw_rows, raw_values, relative_tolerance=RELATIVE_TOLERANCE
                    )
                    matches = arrays_match(
                        expected_rows, expected_values, actual_rows, actual_values
                    )
                    component_integrity = (
                        matches
                        and vector_facts["owned_nonzero_entries_outside_structural_support"] == 0
                        and vector_facts["ghost_values_match_same_rank_owned_values"] is not False
                    )
                    if not component_integrity:
                        integrity_failures.append(f"{key}/{component_name}/production_component_cutoff_or_support")
                    raw_digest = hashlib.sha256(
                        np.asarray(raw_rows, dtype="<i8").tobytes()
                        + np.asarray(raw_values, dtype="<c16").tobytes()
                    ).hexdigest()
                    actual_digest = hashlib.sha256(
                        np.asarray(actual_rows, dtype="<i8").tobytes()
                        + np.asarray(actual_values, dtype="<c16").tobytes()
                    ).hexdigest()
                    component_facts.append(
                        {
                            "component": component_name,
                            "support_row_count": int(raw_rows.size),
                            "raw_exact_nonzero_count": int(np.count_nonzero(raw_values)),
                            "raw_maximum_abs": float(np.max(np.abs(raw_values), initial=0.0)),
                            "raw_l2_norm": float(np.linalg.norm(raw_values)),
                            "raw_rows_values_sha256": raw_digest,
                            "raw_largest_entries_bounded_sample": _complex_sample(raw_rows, raw_values),
                            "stage1_cutoff": cutoff,
                            "production_rows_values_sha256": actual_digest,
                            "production_matches_independent_stage1_mask_elementwise": bool(matches),
                            "component_stage_integrity_passed": bool(component_integrity),
                            "production_entry_count": int(actual_rows.size),
                            "production_nonzero_count": int(np.count_nonzero(actual_values)),
                            "production_largest_entries_bounded_sample": _complex_sample(actual_rows, actual_values),
                            "vector_layout_and_ghost_facts": vector_facts,
                            "relative_cutoff": RELATIVE_TOLERANCE,
                            "absolute_floor": ABSOLUTE_FLOOR,
                            # Arrays are retained only in this in-memory phase cache and are never written.
                            "_raw_entries": (raw_rows, raw_values),
                            "_filtered_entries": (actual_rows, actual_values),
                        }
                    )
                component_cache[phase_key] = component_facts

            raw_entries = [item["_raw_entries"] for item in component_facts]
            filtered_entries = [item["_filtered_entries"] for item in component_facts]
            projection_coefficients = (complex(mode.e_vector[0]), complex(mode.e_vector[1]))
            traction = _traction_vector(mode, cfg)
            coupling_coefficients = (-complex(traction[0]), -complex(traction[1]))
            mode_integrity = all(item["component_stage_integrity_passed"] for item in component_facts)
            route_results: dict[str, Any] = {}
            for route_name, coefficients, conjugate in (
                ("projection", projection_coefficients, True),
                ("coupling", coupling_coefficients, False),
            ):
                expected_rows, expected_values, merged_rows, merged_values, merge_cutoff = expected_merged_filter(
                    filtered_entries, coefficients, relative_tolerance=RELATIVE_TOLERANCE
                )
                actual_merged_rows, actual_merged_values = _combine_owned_entries(
                    (filtered_entries[0], filtered_entries[1]),
                    coefficients,
                    comm=mesh.comm,
                    relative_tol=RELATIVE_TOLERANCE,
                )
                merged_matches = arrays_match(
                    merged_rows, merged_values, actual_merged_rows, actual_merged_values
                )
                if not merged_matches:
                    integrity_failures.append(f"{key}/{route_name}/production_merged_cutoff")
                accounting = route_cutoff_accounting(
                    raw_entries,
                    filtered_entries,
                    coefficients,
                    actual_merged_rows,
                    actual_merged_values,
                    storage,
                    conjugate_combined_values=conjugate,
                )
                if not accounting["closure_passed"]:
                    integrity_failures.append(f"{key}/{route_name}/deleted_dot_closure")
                mode_integrity = mode_integrity and merged_matches and bool(accounting["closure_passed"])
                before_stage2_rows, before_stage2_values = expected_rows, expected_values
                after_stage2_stats = cutoff_facts(
                    before_stage2_values, relative_tolerance=RELATIVE_TOLERANCE
                )
                route_results[route_name] = {
                    "coefficients": coefficients,
                    "relative_cutoff": RELATIVE_TOLERANCE,
                    "absolute_floor": ABSOLUTE_FLOOR,
                    "stage2_cutoff": merge_cutoff,
                    "stage2_rows_values_match_production_elementwise": bool(merged_matches),
                    "stage2_actual_row_count": int(actual_merged_rows.size),
                    "stage2_actual_rows_values_sha256": hashlib.sha256(
                        np.asarray(actual_merged_rows, dtype="<i8").tobytes()
                        + np.asarray(actual_merged_values, dtype="<c16").tobytes()
                    ).hexdigest(),
                    "stage1_to_stage2_input_maximum_abs": after_stage2_stats["maximum_abs_value"],
                    "stage1_to_stage2_input_l2_norm": float(np.linalg.norm(before_stage2_values)),
                    "stage1_to_stage2_input_entry_count": int(before_stage2_rows.size),
                    **accounting,
                }

            H = float(_mode_projection_denominator(mode, cfg))
            P = complex(_mode_boundary_phase(mode, cfg))
            if not np.isfinite(H) or H <= 0.0 or not np.isfinite(P):
                raise FloatingPointError(f"invalid H or boundary phase for {key}")
            projection = route_results["projection"]
            N = complex(projection["after_production_merged_cutoff_dot_complex"])
            saved = dict(saved_aux_by_key[key])
            if int(saved.get("auxiliary_index", -1)) != int(row["mode_index"]):
                raise ValueError(f"saved auxiliary row index differs for exact key {key}")
            saved_total = decode_complex(saved["auxiliary_amplitude_total_projection"])
            saved_incident = decode_complex(saved["incident_projection"])
            saved_outgoing = decode_complex(saved["outgoing_amplitude_at_boundary"])
            direct_numerators: dict[str, complex] = {}
            for field_name in field_views:
                _set_scalar_constant(alpha_c, mode.alpha)
                _set_scalar_constant(gamma_c, mode.gamma)
                _set_scalar_constant(kz_c, mode.k_vector[2])
                _set_scalar_constant(ex_c, mode.e_vector[0])
                _set_scalar_constant(ey_c, mode.e_vector[1])
                local = fem.assemble_scalar(direct_forms[(str(mode.side), field_name)])
                direct_numerators[field_name] = complex(mesh.comm.allreduce(local, op=mpi.SUM))
                if not np.isfinite(direct_numerators[field_name]):
                    raise FloatingPointError(f"non-finite independent q28 projection for {key}/{field_name}")
            direct_amplitudes = {name: value / H for name, value in direct_numerators.items()}
            direct_boundary = {name: value * P for name, value in direct_amplitudes.items()}
            key_result = {
                "exact_signed_mode_key": list(key),
                "parent_mode_index": int(row["mode_index"]),
                "parent_mode_manifest_sha256": str(case["sha256"]["parent_modes"]),
                "ordered_mode_manifest_sha256": str(case["mode_sha256"]),
                "production_phase_cache_key": phase_key,
                "diagnostic_component_phase_cache": {
                    "hit": bool(cache_facts["cache_hit"]),
                    "unique_phase_misses_so_far": int(cache_misses),
                    "hits_so_far": int(cache_hits),
                    "component_assembly_calls_so_far": int(component_assemblies),
                    "historical_612_mode_phase_cache_counts": "NOT_RECORDED",
                },
                "component_stage_records": [
                    {key_name: value for key_name, value in item.items() if not key_name.startswith("_")}
                    for item in component_facts
                ],
                "production_stage_two_routes": route_results,
                "projection": {
                    "complex_conjugation": "combined production projection vector values are conjugated before np.dot(values, same zero-slave storage)",
                    "raw_untruncated_N_complex": projection["raw_untruncated_dot_complex"],
                    "after_component_cutoff_N_complex": projection["after_component_cutoff_before_merge_dot_complex"],
                    "after_merged_cutoff_N_complex": N,
                    "H": H,
                    "boundary_phase_P": P,
                    "raw_N_over_H_complex": projection["raw_untruncated_dot_complex"] / H,
                    "component_cut_N_over_H_complex": projection["after_component_cutoff_before_merge_dot_complex"] / H,
                    "merged_cut_N_over_H_complex": N / H,
                    "merged_cut_boundary_total_amplitude_complex": N / H * P,
                    "saved_total_auxiliary_projection_complex": saved_total,
                    "saved_incident_projection_complex_separate": saved_incident,
                    "saved_outgoing_boundary_amplitude_complex_separate": saved_outgoing,
                    "merged_cut_boundary_vs_saved_total_aux_abs": float(abs(N / H * P - saved_total)),
                    "merged_cut_boundary_vs_saved_total_aux_relative": float(
                        abs(N / H * P - saved_total)
                        / max(abs(N / H * P), abs(saved_total), np.finfo(float).tiny)
                    ),
                    "top00_control_uses_saved_total_not_outgoing_only": key == ("top", 0, 0, "s"),
                    "outgoing_only_difference_is_not_substituted_for_total": (
                        complex(N / H * P - saved_outgoing)
                    ),
                },
                "independent_q28_surface_integrals": {
                    "saved_DG6_field": {
                        "N_complex": direct_numerators["saved_DG6_reference"],
                        "N_over_H_complex": direct_amplitudes["saved_DG6_reference"],
                        "boundary_amplitude_complex": direct_boundary["saved_DG6_reference"],
                    },
                    "reconstructed_N1E6_before_MPC_backsubstitution": {
                        "N_complex": direct_numerators["reconstructed_N1E6_reference"],
                        "N_over_H_complex": direct_amplitudes["reconstructed_N1E6_reference"],
                        "boundary_amplitude_complex": direct_boundary["reconstructed_N1E6_reference"],
                    },
                    "zero_slave_storage_only_not_full_primal": {
                        "N_complex": direct_numerators["zero_slave_storage_only_not_full_primal"],
                        "N_over_H_complex": direct_amplitudes["zero_slave_storage_only_not_full_primal"],
                        "boundary_amplitude_complex": direct_boundary["zero_slave_storage_only_not_full_primal"],
                    },
                    "MPC_backsubstituted_full_primal_from_same_storage": {
                        "N_complex": direct_numerators["MPC_backsubstituted_full_primal_from_same_storage"],
                        "N_over_H_complex": direct_amplitudes["MPC_backsubstituted_full_primal_from_same_storage"],
                        "boundary_amplitude_complex": direct_boundary["MPC_backsubstituted_full_primal_from_same_storage"],
                        "zero_slave_storage_sha256": storage_sha,
                        "expansion_method": "restore_p0_full_field on this same zero-slave storage with scatter/homogenize/backsubstitution/scatter",
                        "expansion_relative_difference_from_reconstructed_N1E6": mpc_backsubstitution_facts.get("expanded_field_relative_difference"),
                    },
                    "surface_quadrature_degree": 28,
                    "full_primal_uses_MPC_backsubstitution_expansion": True,
                },
                "component_cutoff_integrity_passed": bool(mode_integrity),
                "diagnostic_status": "CUTOFF_STAGE_ACCOUNTING_COMPLETE_NOT_QUALIFICATION" if mode_integrity else "DIAGNOSTIC_IMPLEMENTATION_FAILURE",
            }
            all_mode_results.append(key_result)
            on_progress(
                {
                    "status": "RUNNING",
                    "completed_signed_keys": len(all_mode_results),
                    "phase_cache_hits": cache_hits,
                    "phase_cache_misses": cache_misses,
                    "workspace_component_assembly_calls": component_assemblies,
                    "mode_results": all_mode_results,
                    "integrity_failures": list(integrity_failures),
                }
            )
            if not mode_integrity:
                break
    finally:
        workspace.destroy()

    after_hashes = {
        "zero_slave_storage_sha256": _hash_array_view(storage),
        "saved_DG6_field_sha256": _hash_array_view(np.asarray(dg_field.x.array)),
        "reconstructed_N1E6_field_sha256": _hash_array_view(np.asarray(reconstructed_n1e_field.x.array)),
        "MPC_backsubstituted_field_sha256": _hash_array_view(np.asarray(mpc_backsubstituted_field.x.array)),
        "diagnostic_zero_slave_function_sha256": _hash_array_view(np.asarray(zero_slave_field.x.array)),
    }
    if after_hashes["zero_slave_storage_sha256"] != storage_sha:
        integrity_failures.append("production_zero_slave_storage_mutated")
    if after_hashes["saved_DG6_field_sha256"] != dg_before_sha:
        integrity_failures.append("saved_DG6_input_field_mutated")
    if after_hashes["reconstructed_N1E6_field_sha256"] != n1_before_sha:
        integrity_failures.append("reconstructed_N1E6_input_field_mutated")
    if after_hashes["MPC_backsubstituted_field_sha256"] != expanded_before_sha:
        integrity_failures.append("MPC_backsubstituted_input_field_mutated")
    return {
        "schema": "task40.d13.cutoff-stage-signed-key-diagnostic.v1",
        "status": "DIAGNOSTIC_IMPLEMENTATION_FAILURE" if integrity_failures else "SIX_SIGNED_KEY_CUTOFF_STAGES_CAPTURED",
        "qualification": "NO_CARRIER_COMPARISON; V4/V5 failure remains unchanged; no qualification is granted",
        "production_carrier_or_action_or_global_matrix_or_factor_or_solve_built": False,
        "volume_forms_built": False,
        "surface_quadrature_degree": 28,
        "unchanged_production_cutoff": {
            "relative_tolerance": RELATIVE_TOLERANCE,
            "absolute_floor": ABSOLUTE_FLOOR,
            "strict_keep_rule": "abs(value) > max(1e-30, 1e-13*global_max)",
        },
        "field_and_mpc_scope": {
            "zero_slave_storage_sha256": storage_sha,
            "zero_slave_storage_shape": list(storage.shape),
            "diagnostic_zero_slave_function_sha256_before_surface_forms": zero_slave_field_sha,
            "zero_slave_slave_slots_maximum_abs": float(
                np.max(np.abs(storage[np.asarray(mpc.slaves, dtype=np.int64)]), initial=0.0)
            ) if len(mpc.slaves) else 0.0,
            "MPC_full_primal_is_backsubstitution_expansion_of_same_storage": True,
            "original_DG6_and_reconstructed_N1E6_kept_as_independent_references": True,
            "MPC_backsubstitution_error_facts": dict(mpc_backsubstitution_facts),
            "DG6_to_reconstructed_N1E6_roundtrip_facts": dict(reconstruction_facts),
            "field_hashes_after_capture": after_hashes,
            "field_vectors_written_or_cleared_by_diagnostic": False,
        },
        "workspace": workspace_facts,
        "component_phase_cache_observation": {
            "key_function": "production _dtn_component_phase_key",
            "diagnostic_hits": cache_hits,
            "diagnostic_misses": cache_misses,
            "component_assembly_calls": component_assemblies,
            "historical_production_cache_hit_counts": "NOT_RECORDED",
        },
        "integrity_failures": integrity_failures,
        "six_exact_signed_key_results": all_mode_results,
        "interpretation": "Cutoff accounting only. No attribution is made unless component rows/values, merged rows/values, field immutability, ghost ownership, and both deleted-dot closures pass.",
    }


def _run_one(case: Mapping[str, Any], output: dict[str, Any], write_report: Any) -> dict[str, Any]:
    import pyvista as pv
    from basix.ufl import element
    from dolfinx import default_scalar_type, fem
    from mpi4py import MPI
    from petsc4py import PETSc

    from src.common.modes_3d import outgoing_port_modes_3d
    from src.geometry.mesh_builder_3d import _stage4_axis_plan
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.solvers.dtn_port_3d import (
        _dtn_surface_quadrature_degree,
        _mode_boundary_phase,
        _mode_projection_denominator,
        _outward_normal,
        _set_scalar_constant,
    )
    from src.solvers.fullspace_dtn_action import build_ordered_mode_manifest
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        _surface_assemblers,
        restore_p0_full_field,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS

    if MPI.COMM_WORLD.size != 1 or PETSc.ScalarType is not np.complex128 or np.dtype(PETSc.IntType) != np.dtype(np.int64):
        raise RuntimeError("action-only diagnostic requires qualified complex128/int64 MPI1")
    def mark(stage: str) -> None:
        output["execution"]["current_case"] = case["case"]
        output["execution"]["current_stage"] = stage
        output["execution"]["stage_monotonic"] = time.monotonic()
        write_report()

    mark("verify_bound_artifacts")
    paths = {name: Path(case["files"][name]).resolve() for name in case["files"]}
    for name, path in paths.items():
        if not path.is_file():
            raise FileNotFoundError(path)
        observed = _sha256(path)
        if observed != case["sha256"][name]:
            raise ValueError(f"bound artifact hash mismatch for {name}: {observed}")

    mark("load_small_identities_and_vtu_hashes_verified")
    manifest = json.loads(paths["run_manifest"].read_text())
    resolved = json.loads(paths["resolved"].read_text())
    summary = json.loads(paths["summary"].read_text())
    parent_modes = json.loads(paths["parent_modes"].read_text())
    if paths["run_manifest"].parent.name != case["run_directory_id"]:
        raise ValueError("run manifest directory differs from the bound historical run directory")
    if manifest.get("run_id") != case["run_id"]:
        raise ValueError("run manifest id differs from the bound historical run")
    if summary.get("run_id") != case["run_id"]:
        raise ValueError("direct summary id differs from the bound historical run")
    for field in ("source_sha", "input_sha256", "physical_model_sha256", "resolved_config_sha256"):
        expected_value = case["resolved_config_sha256"] if field == "resolved_config_sha256" else case[field]
        if manifest.get(field) != expected_value:
            raise ValueError(f"run manifest {field} differs from its bound identity")
    if case["sha256"].get("input") != case["input_sha256"]:
        raise ValueError("original input file does not match its run-manifest input SHA")
    if paths["source_identity"].read_text().strip() != case["source_sha"]:
        raise ValueError("source_sha.txt differs from its bound historical source")
    if paths["input_identity"].read_text().strip() != case["input_sha256"]:
        raise ValueError("input_sha256.txt differs from its bound input identity")
    if paths["physical_identity"].read_text().strip() != case["physical_model_sha256"]:
        raise ValueError("physical_model_sha256.txt differs from its bound physical identity")
    saved_aux = json.loads(paths["auxiliary"].read_text())
    if summary["operator_identity"]["active_mode_count"] != 612 or summary["operator_identity"]["active_mode_sha256"] != case["mode_sha256"]:
        raise ValueError("saved direct summary mode identity differs from the frozen 612-mode parent")
    if int(summary["operator_identity"]["parent_quadrature_degree"]) != 28:
        raise ValueError("saved direct summary surface q is not q28")
    if int(parent_modes["mode_count"]) != 612 or len(parent_modes["modes"]) != 612:
        raise ValueError("saved original mode manifest is not the 612-row parent")
    exact_pairs = bind_exact_signed_mode_rows(parent_modes["modes"], saved_aux)
    selected_rows = [parent for parent, _aux in exact_pairs]
    saved_aux_map = {mode_key(parent): auxiliary for parent, auxiliary in exact_pairs}

    mark("six_parent_mode_keys_bound")
    cfg = simulation_config_3d_from_normalized(resolved)
    cfg.stage4_dtn_order_policy = "explicit_rectangle"
    cfg.task40_dtn_rectangle_max_m = 4
    cfg.task40_dtn_rectangle_max_n = 0
    cfg.stage4_dtn_quadrature_degree = 28
    candidates = outgoing_port_modes_3d(cfg)
    candidate_map = {mode_key({"side": m.side, "m": m.m, "n": m.n, "polarization": m.polarization}): m for m in candidates}
    if len(candidate_map) != len(candidates):
        raise ValueError("target rectangle generated duplicate mode keys")
    if any(mode_key(row) not in candidate_map for row in selected_rows):
        raise ValueError("live branch builder lacks a selected saved mode")
    modes = [candidate_map[mode_key(row)] for row in selected_rows]
    actual_rows, _encoded, selected_hash = build_ordered_mode_manifest(modes, cfg)
    for expected, actual in zip(selected_rows, actual_rows, strict=True):
        expected_cmp = dict(expected)
        actual_cmp = dict(_jsonable(actual))
        expected_cmp.pop("mode_index", None)
        actual_cmp.pop("mode_index", None)
        if expected_cmp != actual_cmp:
            raise ValueError(f"live mode branch/normalization differs from saved mode key {mode_key(expected)}")

    mesh_summary = summary["mesh_evidence"]
    plan = _stage4_axis_plan(cfg, MPI.COMM_WORLD.size)
    actual_axes = {axis: getattr(plan, f"{axis}_values") for axis in ("x", "y", "z")}
    axis_hashes = {axis: _axis_sha(actual_axes[axis]) for axis in actual_axes}
    if axis_hashes != mesh_summary["axis_sha256_le_f64"]:
        raise ValueError("live axis planner differs from the saved actual mesh evidence")
    expected_cells = int(case["expected_cells"])
    if int(np.prod(plan.mesh_cells_resolved)) != expected_cells or int(mesh_summary["actual_global_cell_count"]) != expected_cells:
        raise ValueError("live axis plan is not the bound Y2/Y3 mesh")
    mark("before_y_mesh_space_and_mpc_setup")
    levels = _build_same_mesh_levels(cfg, MPI.COMM_WORLD, (6,), include_positive_coefficients=False)
    mark("y_mesh_space_and_mpc_setup_complete")
    mesh_data = levels["mesh_data"]
    mesh = levels["mesh"]
    floquet = levels["floquets"][6]
    V = levels["spaces"][6]
    mesh.topology.create_connectivity(mesh.topology.dim - 1, mesh.topology.dim)
    cell_tags = mesh_data.cell_tags
    actual_tags = {str(int(tag)): int(np.count_nonzero(np.asarray(cell_tags.values) == int(tag))) for tag in np.unique(cell_tags.values)}
    expected_tags = {str(key): int(value) for key, value in mesh_summary["material_tag_counts"].items()}
    if actual_tags != expected_tags:
        raise ValueError("live mesh material tag counts differ from saved run")

    mark("before_saved_vtu_load")
    grid = pv.read(str(paths["vtu"]))
    vtu_field, field_facts = _read_vtu_e(grid, float(cfg.electric_field_scale_V_per_m))
    mark("saved_vtu_loaded_and_e_field_decoded")
    if field_facts["incident_e0_V_per_m"] and not np.allclose(field_facts["incident_e0_V_per_m"], [float(cfg.electric_field_scale_V_per_m)], rtol=0.0, atol=1.0e-14):
        raise ValueError("VTU incident E scale differs from bound config")
    dg_space, dg_field, dg_element_dtype, dg_scalar_type = _build_complex_dg6_field(
        mesh, fem, element, default_scalar_type
    )
    mark("dg6_element_and_complex_function_created")
    mapping_facts, cell_dofs = _map_vtu_to_dg6(mesh, dg_space, dg_field, grid, vtu_field)
    mark("vtu_to_dg6_cell_and_node_mapping_complete")
    del grid, vtu_field
    dg_roundtrip = fem.Function(dg_space, name="DG6_roundtrip_from_N1E6", dtype=dg_scalar_type)
    E_n1 = fem.Function(V, name="E_N1E6_reconstructed_from_saved_DG6", dtype=dg_scalar_type)
    E_n1.interpolate(dg_field)
    E_n1.x.scatter_forward()
    dg_roundtrip.interpolate(E_n1)
    dg_roundtrip.x.scatter_forward()
    cell_roundtrip = _per_cell_roundtrip(dg_space, dg_field, dg_roundtrip, cell_dofs)
    n1e_identity = _basix_element_identity(V)
    dg_values = np.asarray(dg_field.x.array, dtype=np.complex128)
    n1_values = np.asarray(E_n1.x.array, dtype=np.complex128)
    roundtrip_values = np.asarray(dg_roundtrip.x.array, dtype=np.complex128)
    data_finite = bool(
        field_facts["finite_complex_E_values"]
        and np.all(np.isfinite(dg_values))
        and np.all(np.isfinite(n1_values))
        and np.all(np.isfinite(roundtrip_values))
    )
    if data_finite:
        dg_error = roundtrip_values - dg_values
        dg_error_norm = float(np.linalg.norm(dg_error))
        dg_scale = float(np.linalg.norm(dg_values))
        dg_relative = dg_error_norm / max(dg_scale, np.finfo(float).tiny)
        dg_max = float(np.max(np.abs(dg_error), initial=0.0))
    else:
        dg_error_norm = dg_scale = dg_relative = dg_max = None
    trace_facts = _shared_tangential_trace(mesh, mesh_data, dg_space, dg_field, cell_dofs)
    mark("dg6_n1e_reconstruction_and_shared_tangent_check_complete")

    slave_indices = np.asarray(floquet.mpc.slaves, dtype=np.int64).reshape(-1)
    storage = None
    E_mpc = None
    if data_finite:
        try:
            storage = zero_slave_storage(n1_values, slave_indices)
            E_mpc = restore_p0_full_field(floquet, storage)
            mpc_values = np.asarray(E_mpc.x.array, dtype=np.complex128)
            mpc_difference = mpc_values - n1_values
            mpc_data_finite = bool(np.all(np.isfinite(mpc_values)) and np.all(np.isfinite(mpc_difference)))
            if mpc_data_finite:
                mpc_error_norm = float(np.linalg.norm(mpc_difference))
                mpc_scale = float(np.linalg.norm(n1_values))
                mpc_relative = mpc_error_norm / max(mpc_scale, np.finfo(float).tiny)
                slave_error = float(np.max(np.abs(mpc_difference[slave_indices]), initial=0.0)) if slave_indices.size else 0.0
            else:
                mpc_error_norm = mpc_scale = mpc_relative = slave_error = None
            mpc_facts = {
                "finite": mpc_data_finite,
                "slave_dof_count": int(slave_indices.size),
                "zero_slave_copy_non_mutating": True,
                "expanded_field_absolute_error_l2": mpc_error_norm,
                "expanded_field_reference_scale_l2": mpc_scale,
                "expanded_field_relative_difference": mpc_relative,
                "maximum_slave_difference": slave_error,
                "diagnostic_tolerance_not_a_solver_gate": DIAGNOSTIC_MPC_RELATIVE_TOLERANCE,
                "compatible_within_diagnostic_tolerance": bool(mpc_data_finite and mpc_relative <= DIAGNOSTIC_MPC_RELATIVE_TOLERANCE),
            }
        except (ValueError, RuntimeError, FloatingPointError, TypeError) as exc:
            mpc_facts = {
                "finite": False, "slave_dof_count": int(slave_indices.size),
                "zero_slave_copy_non_mutating": True,
                "expanded_field_absolute_error_l2": None,
                "expanded_field_reference_scale_l2": None,
                "expanded_field_relative_difference": None,
                "maximum_slave_difference": None,
                "diagnostic_tolerance_not_a_solver_gate": DIAGNOSTIC_MPC_RELATIVE_TOLERANCE,
                "compatible_within_diagnostic_tolerance": False,
                "backsubstitution_error": f"{type(exc).__name__}: {exc}",
            }
    else:
        mpc_facts = {
            "finite": False, "slave_dof_count": int(slave_indices.size),
            "zero_slave_copy_non_mutating": True,
            "expanded_field_absolute_error_l2": None,
            "expanded_field_reference_scale_l2": None,
            "expanded_field_relative_difference": None,
            "maximum_slave_difference": None,
            "diagnostic_tolerance_not_a_solver_gate": DIAGNOSTIC_MPC_RELATIVE_TOLERANCE,
            "compatible_within_diagnostic_tolerance": False,
        }

    compatibility_gate = carrier_comparison_gate(
        data_finite=data_finite and bool(cell_roundtrip.get("finite")) and bool(trace_facts.get("finite")) and bool(mpc_facts.get("finite")),
        global_roundtrip_relative=dg_relative,
        maximum_cell_roundtrip_relative=cell_roundtrip.get("maximum_cell_relative_L2_error"),
        shared_trace_relative=trace_facts.get("relative_l2_tangential_jump"),
        maximum_facet_trace_relative=trace_facts.get("maximum_facet_relative_l2_tangential_jump"),
        mpc_backsubstitution_relative=mpc_facts.get("expanded_field_relative_difference"),
    )

    mark("periodic_mpc_compatibility_check_complete")
    case_result = {
        "case": case["case"], "run_id": case["run_id"], "run_directory_id": case["run_directory_id"], "source_sha": case["source_sha"],
        "input_sha256": case["input_sha256"], "physical_model_sha256": case["physical_model_sha256"],
        "resolved_config_file_sha256": case["sha256"]["resolved"], "vtu_sha256": case["sha256"]["vtu"],
        "mode_manifest_file_sha256": case["sha256"]["parent_modes"], "auxiliary_file_sha256": case["sha256"]["auxiliary"],
        "parent_mode_count": 612, "parent_mode_sha256": case["mode_sha256"],
        "assembled_carrier_mode_count": 0, "assembled_mode_keys": [list(mode_key(row)) for row in selected_rows],
        "selected_parent_mode_indices": [int(row["mode_index"]) for row in selected_rows],
        "selected_subset_sha256": selected_hash, "surface_quadrature_degree": 28,
        "volume_forms_built": False, "global_matrix_or_factor_or_solve": False,
        "actual_axes_sha256_le_f64": axis_hashes, "axis_cell_counts": list(plan.mesh_cells_resolved),
        "actual_global_cell_count": int(mesh.topology.index_map(mesh.topology.dim).size_global),
        "DG6_Basix_element_dtype": str(dg_element_dtype),
        "DG6_function_scalar_dtype": str(np.dtype(dg_scalar_type)),
        "reconstructed_E_function_scalar_dtype": str(np.dtype(E_n1.x.array.dtype)),
        "roundtrip_function_scalar_dtype": str(np.dtype(dg_roundtrip.x.array.dtype)),
        "material_tag_counts": actual_tags, "vtu_field_scale_facts": field_facts,
        "vtu_to_DG6_mapping": mapping_facts,
        "production_N1E6_functional_orientation_Piola_identity": n1e_identity,
        "DG6_to_N1E6_to_DG6_relative_roundtrip_error": dg_relative,
        "DG6_to_N1E6_to_DG6_absolute_error_l2": dg_error_norm,
        "DG6_to_N1E6_to_DG6_reference_scale_l2": dg_scale,
        "DG6_to_N1E6_to_DG6_maximum_absolute_error": dg_max,
        "DG6_to_N1E6_to_DG6_cellwise_roundtrip": cell_roundtrip,
        "unaveraged_shared_tangential_trace": trace_facts,
        "periodic_MPC_compatibility": mpc_facts,
        "carrier_comparison_gate": compatibility_gate,
        "projection_comparisons": [],
        "status": "RECONSTRUCTION_CHECKS_COMPLETE",
    }
    output["cases"].append(case_result)
    write_report()

    if case.get("diagnostic_only_cutoff_stage_capture") is True:
        if not compatibility_gate["passed"]:
            case_result["carrier_comparison_skipped_reason"] = compatibility_gate["failed_checks"]
        case_result["assembled_carrier_mode_count"] = 0
        case_result["projection_comparisons"] = []
        case_result["qualification"] = "NO_CARRIER_COMPARISON; DIAGNOSTIC_ONLY_NOT_CARRIER_OR_FIELD_QUALIFICATION"
        case_result["status"] = "NO_CARRIER_COMPARISON"
        partial: dict[str, Any] = {
            "status": "RUNNING",
            "mode_results": [],
            "qualification": "DIAGNOSTIC_ONLY; V4/V5 failure remains unchanged",
        }
        case_result["diagnostic_only_cutoff_stage_capture"] = partial
        write_report()

        def record_progress(value: dict[str, Any]) -> None:
            case_result["diagnostic_only_cutoff_stage_capture"] = value
            mark("cutoff_stage_mode_progress")

        mark("before_diagnostic_only_six_signed_key_cutoff_stage_capture")
        try:
            if storage is None or E_mpc is None:
                raise RuntimeError("same-storage MPC backsubstituted field is unavailable")
            capture = _cutoff_stage_capture(
                case=case,
                mpc_backsubstitution_facts=mpc_facts,
                cfg=cfg,
                mesh=mesh,
                mesh_data=mesh_data,
                function_space=V,
                mpc=floquet.mpc,
                modes=modes,
                selected_rows=selected_rows,
                saved_aux_by_key=saved_aux_map,
                dg_field=dg_field,
                reconstructed_n1e_field=E_n1,
                reconstruction_facts={
                    "DG6_to_N1E6_to_DG6_relative_error": dg_relative,
                    "DG6_to_N1E6_to_DG6_absolute_error_l2": dg_error_norm,
                    "DG6_to_N1E6_to_DG6_reference_scale_l2": dg_scale,
                    "DG6_to_N1E6_to_DG6_maximum_absolute_error": dg_max,
                    "per_cell_roundtrip": cell_roundtrip,
                    "unaveraged_shared_tangential_trace": trace_facts,
                },
                zero_slave_storage_field_values=storage,
                mpc_backsubstituted_field=E_mpc,
                fem=fem,
                mpi=MPI,
                jit_options=SAME_MESH_JIT_OPTIONS,
                on_progress=record_progress,
            )
        except Exception as exc:  # noqa: BLE001 - preserve a bounded diagnostic failure in the report
            capture = {
                "schema": "task40.d13.cutoff-stage-signed-key-diagnostic.v1",
                "status": "DIAGNOSTIC_CAPTURE_FAILURE",
                "qualification": "NO_CARRIER_COMPARISON; V4/V5 failure remains unchanged",
                "error": f"{type(exc).__name__}: {exc}",
                "completed_signed_key_results": len(partial.get("mode_results", [])),
                "partial_mode_results": partial.get("mode_results", []),
                "production_carrier_or_action_or_global_matrix_or_factor_or_solve_built": False,
            }
        case_result["diagnostic_only_cutoff_stage_capture"] = capture
        case_result["status"] = "NO_CARRIER_COMPARISON"
        case_result["assembled_carrier_mode_count"] = 0
        case_result["projection_comparisons"] = []
        write_report()
        mark("diagnostic_only_six_signed_key_cutoff_stage_capture_complete")
        return case_result

    if not compatibility_gate["passed"]:
        case_result["carrier_comparison_skipped_reason"] = compatibility_gate["failed_checks"]
        write_report()
        case_result["status"] = "NO_CARRIER_COMPARISON"
        case_result["qualification"] = "DIAGNOSTIC_ONLY_NOT_CARRIER_OR_FIELD_QUALIFICATION"
        case_result["assembled_carrier_mode_count"] = 0
        write_report()
        return case_result

    # Assemble only the six requested carrier rows, not the 612-mode carrier and not a volume operator.
    from src.solvers.dtn_port_3d import _with_quadrature_degree
    from src.solvers.fullspace_dtn_action import (
        build_fullspace_dtn_action,
        build_fullspace_dtn_carrier_from_surface,
    )
    surface_q = _dtn_surface_quadrature_degree(cfg, modes)
    if surface_q != 28:
        raise ValueError(f"live six-mode q selection changed: {surface_q}")
    case_result["status"] = "SIX_MODE_Q28_CARRIER_COMPARISON_RUNNING"
    write_report()
    mark("before_six_mode_q28_carrier_assembly")
    assemblers = _surface_assemblers(V, mesh_data, cfg, 28, jit_options=SAME_MESH_JIT_OPTIONS)
    carrier = build_carrier_if_compatible(
        compatibility_gate,
        lambda surface_assemblers=assemblers: build_fullspace_dtn_carrier_from_surface(
            modes, surface_assemblers, floquet.mpc, cfg, degree=6,
            progress_interval=6, quadrature_degree=28,
        ),
    )
    if carrier is None:
        raise RuntimeError("carrier gate rejected after a passing compatibility decision")
    if len(carrier.entries) != 6:
        raise ValueError("action-only carrier unexpectedly materialized more than six entries")
    mark("six_mode_q28_carrier_complete")
    action = build_fullspace_dtn_action(carrier, comm=MPI.COMM_WORLD)
    output["execution"]["matrix_free_action_handle_created"] = True
    write_report()
    storage_function = fem.Function(V, name="zero_slave_storage_for_six_mode_carrier", dtype=dg_scalar_type)
    storage_function.x.array[:] = storage
    storage_function.x.scatter_forward()
    recovered = action.recover_auxiliary(storage_function.x.petsc_vec)
    raw_du = []
    for entry in carrier.entries:
        row = np.asarray(entry.projection_rows, dtype=np.int64)
        if row.size and int(row.max()) >= storage.size:
            raise ValueError("carrier projection rows exceed MPI1 zero-slave storage")
        raw_du.append(np.dot(entry.projection_values, storage[row]))
    h_values = [float(entry.normalization_h) for entry in carrier.entries]
    if any(h != _mode_projection_denominator(mode, cfg) for h, mode in zip(h_values, modes, strict=True)):
        raise ValueError("carrier H differs from production port projection denominator")

    import ufl
    from petsc4py import PETSc
    x = ufl.SpatialCoordinate(mesh)
    ds = ufl.Measure("ds", domain=mesh, subdomain_data=mesh_data.facet_tags)
    alpha_c = fem.Constant(mesh, PETSc.ScalarType(0.0))
    gamma_c = fem.Constant(mesh, PETSc.ScalarType(0.0))
    kz_c = fem.Constant(mesh, PETSc.ScalarType(0.0))
    ex_c = fem.Constant(mesh, PETSc.ScalarType(0.0))
    ey_c = fem.Constant(mesh, PETSc.ScalarType(0.0))
    phase = ufl.exp(1j * alpha_c * x[0] + 1j * gamma_c * x[1] + 1j * kz_c * x[2])
    reference = ufl.as_vector((ex_c * phase, ey_c * phase, PETSc.ScalarType(0.0)))
    zero = PETSc.ScalarType(0.0)
    projection_forms: dict[tuple[str, str, int], Any] = {}
    for side, tag in (("top", cfg.tags.z_max), ("bottom", cfg.tags.z_min)):
        for field_name, field in (("full_primal_N1E6", E_n1), ("direct_DG6", dg_field)):
            for component in (0, 1):
                components = (field[0], zero, zero) if component == 0 else (zero, field[1], zero)
                expression = ufl.inner(ufl.as_vector(components), reference) * ds(tag)
                projection_forms[(side, field_name, component)] = fem.form(_with_quadrature_degree(expression, 28), jit_options=dict(SAME_MESH_JIT_OPTIONS))

    mark("direct_q28_forms_compiled_and_storage_dual_ready")
    mode_results = []
    for index, (row, mode, entry) in enumerate(zip(selected_rows, modes, carrier.entries, strict=True)):
        _set_scalar_constant(alpha_c, mode.alpha)
        _set_scalar_constant(gamma_c, mode.gamma)
        _set_scalar_constant(kz_c, mode.k_vector[2])
        _set_scalar_constant(ex_c, mode.e_vector[0])
        _set_scalar_constant(ey_c, mode.e_vector[1])
        side = str(mode.side)
        components: dict[str, dict[str, complex]] = {}
        for field_name in ("full_primal_N1E6", "direct_DG6"):
            values = []
            for component in (0, 1):
                local = fem.assemble_scalar(projection_forms[(side, field_name, component)])
                value = complex(mesh.comm.allreduce(local, op=MPI.SUM))
                values.append(value)
            components[field_name] = {"x_numerator": values[0], "y_numerator": values[1], "total_numerator": values[0] + values[1], "x_amplitude": values[0] / h_values[index], "y_amplitude": values[1] / h_values[index]}
        direct_num = components["full_primal_N1E6"]["total_numerator"]
        dg_num = components["direct_DG6"]["total_numerator"]
        direct_amplitude = direct_num / h_values[index]
        dg_amplitude = dg_num / h_values[index]
        carrier_amplitude = complex(recovered[index])
        du_value = complex(raw_du[index])
        phase_value = _mode_boundary_phase(mode, cfg)
        saved = saved_aux_map[mode_key(row)]
        saved_aux_value = decode_complex(saved["auxiliary_amplitude_total_projection"])
        saved_phase = decode_complex(saved["boundary_phase"])
        saved_outgoing_boundary = decode_complex(saved["outgoing_amplitude_at_boundary"])
        normal = _outward_normal(mode.side)
        phase_abs_difference = abs(saved_phase - phase_value)
        phase_relative_difference = phase_abs_difference / max(
            abs(saved_phase), abs(phase_value), np.finfo(float).tiny
        )
        saved_incident = decode_complex(saved["incident_projection"])
        saved_outgoing_reconstructed = (
            saved_aux_value - saved_incident if mode.side == "top" else saved_aux_value
        ) * phase_value
        saved_outgoing_abs_difference = abs(
            saved_outgoing_boundary - saved_outgoing_reconstructed
        )
        saved_outgoing_relative_difference = saved_outgoing_abs_difference / max(
            abs(saved_outgoing_boundary), abs(saved_outgoing_reconstructed), np.finfo(float).tiny
        )
        direct_outgoing = direct_amplitude - saved_incident if mode.side == "top" else direct_amplitude
        carrier_outgoing = carrier_amplitude - saved_incident if mode.side == "top" else carrier_amplitude
        dg_outgoing = dg_amplitude - saved_incident if mode.side == "top" else dg_amplitude
        mode_result = {
            "parent_mode_index": int(row["mode_index"]), "key": list(mode_key(row)),
            "outward_normal": normal, "vertical_sign": int(mode.vertical_sign),
            "e_t": mode.e_vector[:2], "complex_inner_conjugates_second_argument": True,
            "alpha_gamma_kz": [mode.alpha, mode.gamma, mode.k_vector[2]],
            "boundary_z_nm": float(cfg.physical_z_max if mode.side == "top" else cfg.physical_z_min),
            "boundary_phase": phase_value, "saved_boundary_phase": saved_phase,
            "saved_vs_rebuilt_boundary_phase_absolute_difference": phase_abs_difference,
            "saved_vs_rebuilt_boundary_phase_relative_difference": phase_relative_difference,
            "projection_denominator_H": h_values[index],
            "carrier_H_exactly_matches_manifest_denominator": True,
            "carrier_Du": du_value, "carrier_Du_over_H": carrier_amplitude,
            "carrier_action_recover_auxiliary": carrier_amplitude,
            "full_primal_N1E6_total_projection": direct_amplitude,
            "direct_DG6_total_projection": dg_amplitude,
            "saved_auxiliary_total_projection": saved_aux_value,
            "full_primal_vs_DG6_relative": relative_difference(direct_amplitude, dg_amplitude),
            "carrier_vs_full_primal_relative": relative_difference(direct_amplitude, carrier_amplitude),
            "carrier_vs_saved_auxiliary_relative": relative_difference(saved_aux_value, carrier_amplitude),
            "full_primal_boundary_total_amplitude": direct_amplitude * phase_value,
            "DG6_boundary_total_amplitude": dg_amplitude * phase_value,
            "carrier_boundary_total_amplitude": carrier_amplitude * phase_value,
            "full_primal_outgoing_boundary_amplitude": direct_outgoing * phase_value,
            "DG6_outgoing_boundary_amplitude": dg_outgoing * phase_value,
            "carrier_outgoing_boundary_amplitude": carrier_outgoing * phase_value,
            "saved_outgoing_boundary_amplitude": saved_outgoing_boundary,
            "saved_outgoing_boundary_reconstruction_absolute_difference": saved_outgoing_abs_difference,
            "saved_outgoing_boundary_reconstruction_relative_difference": saved_outgoing_relative_difference,
            "component_contributions": components,
            "incident_projection": saved_incident,
            "projection_contract": {
                "field_components": "E_x and E_y separately; E_z excluded",
                "complex_inner_conjugates_second_argument": True,
                "phase_expression_before_UFL_inner": "exp(+i*alpha*x + i*gamma*y + i*kz*z)",
                "effective_numerator": "integral(E_t dot conjugate(e_t*phase)) dS",
                "normal_convention": "top +z; bottom -z",
                "denominator": "area*electric_tangential_norm_sq*abs(boundary_phase)^2",
            },
        }
        mode_results.append(mode_result)
    case_result["projection_comparisons"] = mode_results
    case_result["assembled_carrier_mode_count"] = len(carrier.entries)
    case_result["mode_selection_scope"] = mode_selection_scope_facts()
    case_result["status"] = "ACTION_ONLY_PROJECTIONS_COMPLETE_NOT_SOLVER_ORIGINAL_COEFFICIENT_CERTIFICATE"
    mark("six_mode_q28_projection_comparison_complete")
    action.destroy()
    del action, carrier, assemblers
    write_report()
    return case_result


def _load_contract(path: Path) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema") != "task40.d13.cutoff-stage-signed-key-contract.v2":
        raise ValueError("unsupported cutoff-stage diagnostic contract")
    if contract.get("scope") != "Y2_Y3_six_signed_key_cutoff_stage_accounting_no_carrier_no_solve":
        raise ValueError("contract scope differs from the approved cutoff-stage boundary")
    if contract.get("diagnostic_only_no_carrier_or_action") is not True:
        raise ValueError("cutoff-stage contract must explicitly forbid carrier/action construction")
    cases = contract.get("cases")
    if not isinstance(cases, list) or [case.get("case") for case in cases] != ["Y2-primary", "Y3-control"]:
        raise ValueError("contract must bind exactly the Y2 primary and Y3 same-key control")
    for case in cases:
        if not case.get("run_id") or not case.get("run_directory_id"):
            raise ValueError("contract must bind both run manifest id and run directory id")
        if int(case.get("parent_mode_count", -1)) != 612:
            raise ValueError("contract parent mode count must remain 612")
        if case.get("mode_sha256") != contract.get("expected_parent_mode_sha256"):
            raise ValueError("contract cases must share the frozen parent mode identity")
        if int(case.get("surface_quadrature_degree", -1)) != 28:
            raise ValueError("contract surface quadrature must remain q28")
        if case.get("selected_keys") != [list(key) for key in TARGET_KEYS]:
            raise ValueError("contract selected port keys differ from the fixed six-key scope")
        if case.get("selected_parent_indices") != list(TARGET_PARENT_INDICES):
            raise ValueError("contract parent indices differ from the fixed six-key selection")
        if case.get("diagnostic_only_cutoff_stage_capture") is not True:
            raise ValueError("each case must explicitly opt into the cutoff-stage capture")
    return contract


def _verify_analysis_source(contract: Mapping[str, Any]) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[3]
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, check=True,
        capture_output=True, text=True,
    )
    observed_head = completed.stdout.strip()
    if observed_head != contract.get("analysis_source_head"):
        raise ValueError("Task40 analysis source HEAD differs from the frozen contract")
    worker_hash = _sha256(Path(__file__).resolve())
    if worker_hash != contract.get("worker_script_sha256"):
        raise ValueError("action-only worker script SHA differs from the frozen contract")
    source_hashes = contract.get("analysis_source_file_sha256")
    if not isinstance(source_hashes, Mapping) or not source_hashes:
        raise ValueError("contract lacks the source-file identity set")
    observed_files: dict[str, str] = {}
    for relative, expected_hash in source_hashes.items():
        path = (repo_root / str(relative)).resolve()
        if repo_root not in path.parents or not path.is_file():
            raise ValueError(f"bound source file is outside the Task40 checkout or missing: {relative}")
        actual_hash = _sha256(path)
        if actual_hash != expected_hash:
            raise ValueError(f"Task40 analysis source file hash changed: {relative}")
        observed_files[str(relative)] = actual_hash
    spec = importlib.util.find_spec("src")
    if spec is None or spec.origin is None or Path(spec.origin).resolve() != repo_root / "src/__init__.py":
        raise ValueError("Python src package is not imported from the Task40 worktree")
    supervisor_path = Path(__file__).with_name("d13_saved_field_cutoff_stage_supervisor.py")
    observed_supervisor_hash = _sha256(supervisor_path)
    if observed_supervisor_hash != contract.get("supervisor_script_sha256"):
        raise ValueError("Task40 action-only supervisor script SHA differs from the frozen contract")
    return {
        "analysis_source_head": observed_head,
        "worker_script_sha256": worker_hash,
        "supervisor_script_sha256": observed_supervisor_hash,
        "analysis_source_file_sha256": observed_files,
        "src_package_path": str(Path(spec.origin).resolve()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    contract = _load_contract(args.contract.resolve())
    started = time.monotonic()
    report: dict[str, Any] = {
        "schema": "task40.d13.saved-field-cutoff-stage-report.v1",
        "status": "RUNNING", "contract_sha256": _sha256(args.contract.resolve()),
        "scope": contract["scope"], "cases": [], "execution": {
            "pid": os.getpid(), "started_monotonic": started,
            "matrix_built": False, "volume_form_built": False,
            "factor_or_solve": False, "PDE_solve": False,
            "full_612_carrier_built": False, "cache_warm_start": False,
        }
    }
    def write() -> None:
        report["execution"]["elapsed_seconds"] = time.monotonic() - started
        _atomic_json(args.output.resolve(), report)
    write()
    try:
        report["execution"]["analysis_source_identity"] = _verify_analysis_source(contract)
        report["execution"]["materialized_global_matrix_built"] = False
        report["execution"]["matrix_free_action_handle_created"] = False
        from mpi4py import MPI
        from petsc4py import PETSc
        report["execution"].update({"mpi_size": int(MPI.COMM_WORLD.size), "petsc_scalar_type": str(PETSc.ScalarType), "petsc_int_dtype": str(np.dtype(PETSc.IntType))})
        for case in contract["cases"]:
            completed_case = _run_one(case, report, write)
            cutoff = completed_case.get("diagnostic_only_cutoff_stage_capture", {})
            if cutoff.get("status") in {"DIAGNOSTIC_IMPLEMENTATION_FAILURE", "DIAGNOSTIC_CAPTURE_FAILURE"}:
                report["status"] = cutoff["status"]
                report["halted_after_case"] = case["case"]
                break
        else:
            report["status"] = "COMPLETE_CUTOFF_STAGE_DIAGNOSTIC_NO_QUALIFICATION"
    except Exception as exc:
        report["status"] = "ACTION_ONLY_DIAGNOSTIC_FAILED"
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        write()
    return 4 if report["status"] in {"DIAGNOSTIC_IMPLEMENTATION_FAILURE", "DIAGNOSTIC_CAPTURE_FAILURE"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
