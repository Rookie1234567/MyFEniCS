"""Reusable P6 topology, q-mode, and conservative CSR support bounds.

The module derives structured counts without building a target FE space, CSR
matrix, factor, or PDE solve. Native-map calibration can tighten a bound only
when its y-orbit coverage and target permutation coverage match; otherwise the
432-channel trace and 432*Nx boundary bounds remain in force.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any, Mapping, Sequence

import numpy as np


INT32_MAX = 2**31 - 1
P6_LOCAL_TRACE_WIDTH = 432
P6_EDGE_DOF_WIDTH = 6
P6_FACE_DOF_WIDTH = 60
P6_CELL_INTERIOR_WIDTH = 450


def p6_periodic_topology_counts(nx: int, ny: int, nz: int) -> dict[str, Any]:
    """Derive structured periodic P6 storage and q-trace row counts."""
    nx, ny, nz = int(nx), int(ny), int(nz)
    if min(nx, ny, nz) <= 0 or ny % 2:
        raise ValueError("positive structured axes and an even Ny are required")
    cells = nx * ny * nz
    full_edges = {
        "x": nx * (ny + 1) * (nz + 1),
        "y": (nx + 1) * ny * (nz + 1),
        "z": (nx + 1) * (ny + 1) * nz,
    }
    full_faces = {
        "normal_x": (nx + 1) * ny * nz,
        "normal_y": nx * (ny + 1) * nz,
        "normal_z": nx * ny * (nz + 1),
    }
    periodic_edges = {
        "x": nx * ny * (nz + 1),
        "y": nx * ny * (nz + 1),
        "z": nx * ny * nz,
    }
    periodic_faces = {
        "normal_x": nx * ny * nz,
        "normal_y": nx * ny * nz,
        "normal_z": nx * ny * (nz + 1),
    }
    full_storage_rows = (
        P6_EDGE_DOF_WIDTH * sum(full_edges.values())
        + P6_FACE_DOF_WIDTH * sum(full_faces.values())
        + P6_CELL_INTERIOR_WIDTH * cells
    )
    independent_rows = (
        P6_EDGE_DOF_WIDTH * sum(periodic_edges.values())
        + P6_FACE_DOF_WIDTH * sum(periodic_faces.values())
        + P6_CELL_INTERIOR_WIDTH * cells
    )
    interior_rows = P6_CELL_INTERIOR_WIDTH * cells
    trace_rows = independent_rows - interior_rows
    q_edges = {
        "x": nx * (nz + 1),
        "y": nx * (nz + 1),
        "z": nx * nz,
    }
    q_faces = {
        "normal_x": nx * nz,
        "normal_y": nx * nz,
        "normal_z": nx * (nz + 1),
    }
    q_edge_rows = {key: value * P6_EDGE_DOF_WIDTH for key, value in q_edges.items()}
    q_face_rows = {key: value * P6_FACE_DOF_WIDTH for key, value in q_faces.items()}
    q_trace_rows, trace_remainder = divmod(trace_rows, ny)
    q_spatial_rows, spatial_remainder = divmod(independent_rows, ny)
    q_interior_rows = P6_CELL_INTERIOR_WIDTH * nx * nz
    if trace_remainder or spatial_remainder:
        raise AssertionError("periodic P6 topology does not divide into Ny q blocks")
    if q_trace_rows != sum(q_edge_rows.values()) + sum(q_face_rows.values()):
        raise AssertionError("q trace topology formula does not close")
    if q_spatial_rows != q_trace_rows + q_interior_rows:
        raise AssertionError("q spatial row formula does not close")
    return {
        "classification": "derived_structured_periodic_p6_topology_formula",
        "cell_axes": [nx, ny, nz],
        "physical_cells": cells,
        "full_storage_rows": full_storage_rows,
        "periodic_independent_rows": independent_rows,
        "interior_rows": interior_rows,
        "trace_rows": trace_rows,
        "q_count": ny,
        "q_edge_entities": q_edges,
        "q_face_entities": q_faces,
        "q_edge_rows": q_edge_rows,
        "q_face_rows": q_face_rows,
        "q_trace_rows": q_trace_rows,
        "q_interior_rows": q_interior_rows,
        "q_spatial_rows": q_spatial_rows,
        "q_representative_cells": nx * nz,
    }


def support_bounds_from_native_calibration(
    target_cell_axes: Sequence[int],
    target_permutation_codes: Sequence[int],
    calibration: Mapping[str, Any],
) -> dict[str, Any]:
    """Select measured-calibration support or conservative 432-channel fallback.

    A small calibration can tighten the bound only if it covered the same Ny
    orbit count, every representative/layer, and exactly the target's cell
    permutation-code set. The Ny4 support value is never transferred to Ny8.
    """
    nx, ny, nz = map(int, target_cell_axes)
    if min(nx, ny, nz) <= 0 or ny % 2:
        raise ValueError("target structured axes must be positive with even Ny")
    native_scan = calibration.get(
        "native_q_cell_support_scan", calibration.get("native_scan", {})
    )
    calibration_axes = native_scan.get("mesh_cell_axes", ())
    calibration_ny = int(calibration_axes[1]) if len(calibration_axes) >= 2 else None
    target_codes = {int(value) for value in target_permutation_codes}
    calibration_codes_raw = calibration.get(
        "cell_permutation_codes",
        calibration.get("calibration_permutation_code_set", ()),
    )
    calibration_codes = {int(value) for value in calibration_codes_raw}
    permutation_coverage_matches = bool(
        target_codes and calibration_codes and target_codes == calibration_codes
    )
    native_map_coverage_complete = bool(
        native_scan.get("all_xz_representatives_covered")
        and native_scan.get("every_y_layer_covered_for_each_xz_representative")
        and native_scan.get("all_folded_cell_trace_supports_within_432_local_channels")
    )
    ny_matches = calibration_ny == ny
    reasons = []
    if not ny_matches:
        reasons.append("calibration_Ny_does_not_match_target")
    if not permutation_coverage_matches:
        reasons.append("target_and_calibration_permutation_code_sets_do_not_match")
    if not native_map_coverage_complete:
        reasons.append("native_map_coverage_is_incomplete_or_unavailable")

    use_calibrated_cell_support = (
        ny_matches and permutation_coverage_matches and native_map_coverage_complete
    )
    if use_calibrated_cell_support:
        cell_support = int(native_scan["maximum_folded_cell_trace_support_size"])
        if not 1 <= cell_support <= P6_LOCAL_TRACE_WIDTH:
            raise ValueError("native calibration support is outside the 432-channel trace")
    else:
        cell_support = P6_LOCAL_TRACE_WIDTH

    periodic_rule = native_scan.get("periodic_x_boundary_support_rule", {})
    periodic_rule_verified = bool(
        periodic_rule.get("all_periodic_x_faces_verified_from_native_entity_slots")
        and periodic_rule.get("observed_union_fits_conservative_formula_on_both_faces")
    )
    if not periodic_rule_verified:
        reasons.append("periodic_x_interface_coverage_is_unverified")
    target_periodic_rule_transferable = bool(
        use_calibrated_cell_support and periodic_rule_verified and nx >= 3
    )
    if periodic_rule_verified and not target_periodic_rule_transferable:
        reasons.append("periodic_x_boundary_rule_not_transferable_to_target")
    if target_periodic_rule_transferable:
        overlap_rows = int(
            periodic_rule["face_entity_dofs_per_face_for_reference"]
        )
        if not 0 <= overlap_rows <= cell_support:
            raise ValueError("verified periodic interface overlap exceeds cell support")
        boundary_support = nx * (cell_support - overlap_rows)
        boundary_is_refined = True
    else:
        overlap_rows = None
        boundary_support = nx * P6_LOCAL_TRACE_WIDTH
        boundary_is_refined = False
        if nx < 3:
            reasons.append("periodic_x_boundary_formula_requires_at_least_three_cells")

    return {
        "classification": "derived_support_upper_from_small_native_calibration_or_full_432_fallback",
        "target_cell_axes": [nx, ny, nz],
        "calibration_cell_axes": list(map(int, calibration_axes))
        if len(calibration_axes) == 3
        else None,
        "target_and_calibration_permutation_code_sets_match": permutation_coverage_matches,
        "native_map_coverage_complete": native_map_coverage_complete,
        "same_Ny_calibration": ny_matches,
        "folded_cell_trace_support_upper": cell_support,
        "cell_support_source": (
            "measured_small_native_calibration_maximum"
            if use_calibrated_cell_support
            else "conservative_full_432_local_trace_channels"
        ),
        "periodic_x_boundary_rule_verified_on_calibration": periodic_rule_verified,
        "periodic_x_boundary_rule_transferable_to_target": target_periodic_rule_transferable,
        "verified_shared_normal_x_face_rows_per_interface": overlap_rows,
        "boundary_trace_support_upper_per_face": boundary_support,
        "boundary_support_refined": boundary_is_refined,
        "fallback_reasons": reasons,
        "target_fe_space_or_csr_built": False,
        "target_factor_or_pde_built": False,
    }


def assign_ordered_modes_to_q(
    modes: Sequence[Any], cfg: Any, axes: Mapping[str, Sequence[float]]
) -> dict[str, Any]:
    """Use the production sector mapper and preserve every ordered mode once."""
    from src.solvers.task40_v10_p6_yorbit import build_task40_v10_sector_contexts

    ny = len(axes["y"]) - 1
    if ny <= 0 or ny % 2:
        raise ValueError("q mapper requires a positive even y-cell count")
    contexts = build_task40_v10_sector_contexts(tuple(modes), cfg, axes)
    q_for_mode = np.full(len(modes), -1, dtype=np.int64)
    q_counts = np.zeros(ny, dtype=np.int64)
    q_side_counts: list[Counter[str]] = [Counter() for _ in range(ny)]
    K = ny // 2
    for twist, context in enumerate(contexts):
        for mode_index, branch in zip(
            context.original_mode_indices, context.local_branch_indices, strict=True
        ):
            index = int(mode_index)
            branch = int(branch)
            q = int(twist + branch * K)
            side = str(getattr(modes[index], "side", ""))
            if side not in {"top", "bottom"}:
                raise ValueError(f"mode {index} has an unknown or missing side {side!r}")
            if not 0 <= q < ny or q_for_mode[index] != -1:
                raise AssertionError("production q mapper duplicated or misrouted a mode")
            q_for_mode[index] = q
            q_counts[q] += 1
            q_side_counts[q][side] += 1
    if np.any(q_for_mode < 0) or int(q_counts.sum()) != len(modes):
        raise AssertionError("production q mapper failed complete ordered-mode coverage")
    ordered_identity = [
        {
            "index": index,
            "mode_key": str(getattr(mode, "mode_key", index)),
            "q": int(q_for_mode[index]),
            "side": str(getattr(mode, "side", "")),
        }
        for index, mode in enumerate(modes)
    ]
    digest = hashlib.sha256(
        json.dumps(ordered_identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "classification": "measured_production_q_phase_assignment_from_ordered_mode_objects",
        "ny": ny,
        "K": K,
        "ordered_mode_count": len(modes),
        "q_counts": [int(value) for value in q_counts],
        "q_side_counts": [
            {"top": int(counts.get("top", 0)), "bottom": int(counts.get("bottom", 0))}
            for counts in q_side_counts
        ],
        "sector_counts": [int(len(ctx.original_mode_indices)) for ctx in contexts],
        "ordered_q_assignment_sha256": digest,
        "all_modes_assigned_once": True,
        "q_for_mode": q_for_mode,
    }


def derive_p6_q_csr_bounds(
    topology: Mapping[str, Any],
    q_side_counts: Sequence[Mapping[str, int]],
    *,
    folded_cell_trace_support_upper: int,
    boundary_trace_support_upper_per_face: int,
    evidence_classification: str,
) -> dict[str, Any]:
    """Derive conservative condensed-CSR shape, NNZ, payload, and index bounds."""
    nx, ny, nz = map(int, topology["cell_axes"])
    q_count = int(topology["q_count"])
    side_counts = list(q_side_counts)
    if q_count != ny or len(side_counts) != q_count:
        raise ValueError("q side-mode inventory must cover every global q")
    cell_support = int(folded_cell_trace_support_upper)
    boundary_support = int(boundary_trace_support_upper_per_face)
    if not 1 <= cell_support <= P6_LOCAL_TRACE_WIDTH:
        raise ValueError("folded support upper must be within the P6 432-row trace")
    if boundary_support < 0:
        raise ValueError("boundary support upper must be nonnegative")

    trace_rows_per_q = int(topology["q_trace_rows"])
    interior_rows_per_q = int(topology["q_interior_rows"])
    q_cell_count = nx * nz
    q_matrices = []
    for q, side_counts_for_q in enumerate(side_counts):
        if set(side_counts_for_q) != {"top", "bottom"}:
            raise ValueError(f"q={q} side inventory must contain only top and bottom")
        top = int(side_counts_for_q["top"])
        bottom = int(side_counts_for_q["bottom"])
        if min(top, bottom) < 0:
            raise ValueError(f"q={q} side-mode counts must be nonnegative")
        port_count = top + bottom
        rows = trace_rows_per_q + port_count
        local_dense = q_cell_count * cell_support**2
        trace_port = 2 * boundary_support * port_count
        port_port = port_count**2
        nnz_upper = local_dense + trace_port + port_port
        max_trace_row = 4 * cell_support + port_count
        max_port_row = boundary_support + port_count
        max_row = max(max_trace_row, max_port_row)
        payload = {
            "complex128_values": nnz_upper * 16,
            "int32_column_indices": nnz_upper * 4,
            "int32_indptr": (rows + 1) * 4,
            "total_int32_csr": nnz_upper * 20 + (rows + 1) * 4,
            "int64_indices_and_indptr": nnz_upper * 24 + (rows + 1) * 8,
        }
        safe = (
            rows <= INT32_MAX
            and nnz_upper <= INT32_MAX
            and max_row <= INT32_MAX
        )
        q_matrices.append(
            {
                "q": q,
                "spatial_trace_rows_columns": trace_rows_per_q,
                "interior_rows_eliminated_per_q": interior_rows_per_q,
                "port_rows_columns": port_count,
                "port_rows_by_face": {"top": top, "bottom": bottom},
                "augmented_rows_columns": rows,
                "structural_nnz_lower_bound": rows,
                "structural_nnz_upper_bound": nnz_upper,
                "upper_bound_components": {
                    "cell_local_dense_folded_trace_support": local_dense,
                    "top_bottom_trace_port_both_directions": trace_port,
                    "full_port_port_block": port_port,
                },
                "maximum_intermediate_csr_offset_upper": nnz_upper - 1,
                "maximum_column_index": rows - 1,
                "maximum_row_nnz_upper": max_row,
                "payload_upper_bytes": payload,
                "int32_safe_for_shape_nnz_offsets_and_row_support": safe,
            }
        )
    return {
        "classification": evidence_classification,
        "target_p6_csr_allocated": False,
        "target_factor_or_pde_built": False,
        "folded_cell_trace_support_upper_used": cell_support,
        "boundary_trace_support_rows_upper_per_face": boundary_support,
        "q_matrices": q_matrices,
        "all_q_structural_upper_bounds_fit_int32": all(
            row["int32_safe_for_shape_nnz_offsets_and_row_support"] for row in q_matrices
        ),
        "int32_index_limit": INT32_MAX,
        "q_count_distinct_payload_upper_bytes": sum(
            int(row["payload_upper_bytes"]["total_int32_csr"]) for row in q_matrices
        ),
        "q_payload_sum_is_simultaneous_memory_claim": False,
        "lower_bound_is_not_measured_numerical_nnz": True,
        "numerical_nonzero_pruning_is_unmeasured": True,
    }

