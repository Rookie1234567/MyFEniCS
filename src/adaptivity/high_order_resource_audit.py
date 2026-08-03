"""Task035b high-order H(curl) topology and direct-solver resource audits.

The routines in this module are read-only research diagnostics.  In
particular, the static-condensation row count is a topology-derived projection;
it is never reported as an assembled or solved matrix measurement.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

import numpy as np

from dolfinx import mesh

from ..constraints.high_order_floquet_trace import (
    high_order_trace_layout,
    tetrahedral_trace_layout,
)
from ..geometry.tetra_mesh_audit import (
    canonical_entity_key,
    mesh_coordinate_tolerance,
)


def _rows_sha256(rows: Iterable[tuple[int, ...]]) -> str:
    digest = hashlib.sha256()
    for row in sorted(rows):
        digest.update(
            json.dumps(row, separators=(",", ":"), ensure_ascii=True).encode(
                "ascii"
            )
        )
        digest.update(b"\n")
    return digest.hexdigest()


def _flatten_key(key: tuple[tuple[int, int, int], ...]) -> tuple[int, ...]:
    return tuple(component for point in key for component in point)


def _linear_cell_vertex_count(msh: mesh.Mesh) -> int:
    cell_name = str(msh.topology.cell_type).lower()
    if "tetrahedron" in cell_name:
        return 4
    if "hexahedron" in cell_name:
        return 8
    raise NotImplementedError(
        "Task035b mesh identity supports tetrahedra and hexahedra only."
    )


def partition_independent_linear_mesh_identity(mesh_data: Any) -> dict[str, Any]:
    """Hash actual affine cells and cell/facet tags independent of MPI partition."""

    msh = mesh_data.mesh
    comm = msh.comm
    tolerance = mesh_coordinate_tolerance(msh)
    tdim = msh.topology.dim
    cell_index_map = msh.topology.index_map(tdim)
    vertex_count = _linear_cell_vertex_count(msh)
    tag_by_cell = {
        int(index): int(value)
        for index, value in zip(
            mesh_data.cell_tags.indices,
            mesh_data.cell_tags.values,
            strict=True,
        )
    }

    local_cell_rows: list[tuple[int, ...]] = []
    local_cell_tag_rows: list[tuple[int, ...]] = []
    for local_cell in range(cell_index_map.size_local):
        geometry_indices = np.asarray(
            msh.geometry.dofmap[local_cell], dtype=np.int32
        )[:vertex_count]
        coordinates = np.asarray(
            msh.geometry.x[geometry_indices], dtype=np.float64
        )
        if coordinates.shape != (vertex_count, 3):
            raise RuntimeError(
                "Task035b mesh identity requires affine three-dimensional cells."
            )
        flattened = _flatten_key(canonical_entity_key(coordinates, tolerance))
        local_cell_rows.append(flattened)
        if local_cell not in tag_by_cell:
            raise RuntimeError("An owned Task035b cell is missing its material tag.")
        local_cell_tag_rows.append((tag_by_cell[local_cell], *flattened))

    cell_rows = [
        row for packet in comm.allgather(local_cell_rows) for row in packet
    ]
    cell_tag_rows = [
        row for packet in comm.allgather(local_cell_tag_rows) for row in packet
    ]
    if len(set(cell_rows)) != len(cell_rows):
        raise RuntimeError("Duplicate owned cell geometry keys detected.")
    if len(cell_rows) != int(cell_index_map.size_global):
        raise RuntimeError(
            "Partition-independent cell identity count does not match topology."
        )

    fdim = tdim - 1
    facet_indices = np.asarray(mesh_data.facet_tags.indices, dtype=np.int32)
    facet_geometry = mesh.entities_to_geometry(
        msh, fdim, facet_indices, False
    )
    local_facet_tag_rows = [
        (
            int(tag),
            *_flatten_key(
                canonical_entity_key(msh.geometry.x[indices], tolerance)
            ),
        )
        for tag, indices in zip(
            mesh_data.facet_tags.values,
            facet_geometry,
            strict=True,
        )
    ]
    facet_tag_rows = sorted(
        {
            row
            for packet in comm.allgather(local_facet_tag_rows)
            for row in packet
        }
    )
    return {
        "schema_version": "task035b.partition-independent-linear-mesh.v1",
        "mesh_cell_type": mesh_data.mesh_cell_type_resolved,
        "coordinate_tolerance": float(tolerance),
        "global_cell_count": len(cell_rows),
        "partition_independent_mesh_sha256": _rows_sha256(cell_rows),
        "cell_tag_sha256": _rows_sha256(cell_tag_rows),
        "facet_tag_sha256": _rows_sha256(facet_tag_rows),
        "mesh_cells_resolved": list(mesh_data.mesh_cells_resolved),
        "material_plane_alignment": mesh_data.material_plane_alignment,
    }


def _global_entity_counts(msh: mesh.Mesh) -> dict[str, int]:
    tdim = msh.topology.dim
    for entity_dim in range(1, tdim):
        msh.topology.create_entities(entity_dim)
    return {
        "vertices": int(msh.topology.index_map(0).size_global),
        "edges": int(msh.topology.index_map(1).size_global),
        "faces": int(msh.topology.index_map(2).size_global),
        "cells": int(msh.topology.index_map(tdim).size_global),
    }


def hcurl_entity_dof_inventory(
    V: Any,
    *,
    num_auxiliary_dofs: int,
    floquet_num_constraints: int | None,
    active_matrix_rows: int | None,
    cell_static_condensation: bool = False,
    floquet_slave_elimination: bool = False,
) -> dict[str, Any]:
    """Decompose the actual global N1curl dimension by mesh-entity ownership."""

    if floquet_slave_elimination and not cell_static_condensation:
        raise ValueError(
            "Floquet slave elimination audit requires cell static condensation"
        )
    msh = V.mesh
    degree = int(V.element.basix_element.degree)
    basix_element = V.element.basix_element
    cell_name = str(msh.basix_cell()).lower()
    if "tetrahedron" in cell_name:
        layout_builder = tetrahedral_trace_layout
        standard_layout = layout_builder(degree)
        standard_dimension = standard_layout.tetrahedron_dimension
    elif "hexahedron" in cell_name:
        layout_builder = high_order_trace_layout
        standard_layout = layout_builder(degree)
        standard_dimension = standard_layout.hexahedron_dimension
    else:
        raise NotImplementedError(
            "Task035b entity inventory supports tetrahedra and hexahedra."
        )
    entity_dofs = basix_element.entity_dofs

    def uniform_entity_dofs(dimension: int) -> int:
        values = {len(dofs) for dofs in entity_dofs[dimension]}
        if len(values) != 1:
            raise RuntimeError(
                "Task035b entity inventory requires uniform entity DoF "
                f"counts in topological dimension {dimension}"
            )
        return int(next(iter(values)))

    edge_per_entity = uniform_entity_dofs(1)
    face_per_entity = uniform_entity_dofs(2)
    cell_per_entity = uniform_entity_dofs(msh.topology.dim)
    element_dimension = int(basix_element.dim)
    trace_degree_candidates = [
        candidate
        for candidate in range(1, 7)
        if layout_builder(candidate).edge_dofs == edge_per_entity
        and layout_builder(candidate).face_interior_dofs == face_per_entity
    ]
    trace_degree = (
        int(trace_degree_candidates[0])
        if len(trace_degree_candidates) == 1
        else None
    )
    uniform_standard_layout = (
        edge_per_entity == standard_layout.edge_dofs
        and face_per_entity == standard_layout.face_interior_dofs
        and cell_per_entity == standard_layout.cell_interior_dofs
        and element_dimension == standard_dimension
    )
    counts = _global_entity_counts(msh)
    edge_dofs = counts["edges"] * edge_per_entity
    face_dofs = counts["faces"] * face_per_entity
    cell_interior_dofs = counts["cells"] * cell_per_entity
    decomposed_total = edge_dofs + face_dofs + cell_interior_dofs
    actual_total = int(
        V.dofmap.index_map.size_global * V.dofmap.index_map_bs
    )
    trace_total = edge_dofs + face_dofs
    auxiliary = int(num_auxiliary_dofs)
    projected_rows = trace_total + auxiliary
    current_expected_rows = actual_total + auxiliary
    periodic_independent_rows = projected_rows - int(
        0 if floquet_num_constraints is None else floquet_num_constraints
    )
    if floquet_slave_elimination and periodic_independent_rows <= 0:
        raise ValueError(
            "Floquet slave elimination removed all projected trace rows"
        )
    expected_active_rows = (
        periodic_independent_rows
        if floquet_slave_elimination
        else projected_rows
        if cell_static_condensation
        else current_expected_rows
    )
    active_rows_match = active_matrix_rows is None or (
        int(active_matrix_rows) == expected_active_rows
    )
    passed = decomposed_total == actual_total and active_rows_match
    return {
        "schema_version": "task035b.hcurl-entity-dof-inventory.v1",
        "status": "pass" if passed else "fail",
        "mesh_cell_type": (
            "tetrahedron" if "tetrahedron" in cell_name else "hexahedron"
        ),
        "degree": degree,
        "trace_degree_inferred": trace_degree,
        "uniform_standard_n1curl_layout": uniform_standard_layout,
        "basix_element_dimension": int(element_dimension),
        "global_entity_counts": counts,
        "entity_dofs_per_entity": {
            "edge": edge_per_entity,
            "face_interior": face_per_entity,
            "cell_interior": cell_per_entity,
        },
        "global_dof_contributions": {
            "edge": int(edge_dofs),
            "face_interior": int(face_dofs),
            "cell_interior": int(cell_interior_dofs),
        },
        "decomposed_nedelec_dofs": int(decomposed_total),
        "actual_nedelec_dofs": actual_total,
        "cell_interior_fraction": (
            0.0
            if actual_total == 0
            else float(cell_interior_dofs / actual_total)
        ),
        "floquet_constraint_rows": (
            None
            if floquet_num_constraints is None
            else int(floquet_num_constraints)
        ),
        "current_backend_row_semantics": (
            "exact cell-interior elimination; measured global matrix retains "
            "only edge/face trace and DtN auxiliary rows"
            if cell_static_condensation
            else "dolfinx_mpc retains the full FE row layout; constraints do "
            "not constitute static condensation"
        ),
        "num_auxiliary_dofs": auxiliary,
        "current_expected_augmented_rows": int(current_expected_rows),
        "active_matrix_rows_measured": (
            None if active_matrix_rows is None else int(active_matrix_rows)
        ),
        "theoretical_static_condensed_trace_dofs": int(trace_total),
        "theoretical_static_condensed_augmented_rows": int(projected_rows),
        "theoretical_static_condensed_periodic_independent_rows": int(
            periodic_independent_rows
        ),
        "theoretical_row_compression_factor": (
            None
            if projected_rows == 0
            else float(current_expected_rows / projected_rows)
        ),
        "static_condensation_projection_semantics": (
            "measured_active_rows; exact cell-interior and Floquet-slave "
            "elimination with independent edge/face trace and DtN auxiliary "
            "unknowns retained"
            if floquet_slave_elimination
            else "measured_active_rows; exact cell-interior elimination with "
            "all edge/face trace and DtN auxiliary unknowns retained"
            if cell_static_condensation
            else "derived_not_measured; assumes exact cell-interior "
            "elimination with all edge/face trace and DtN auxiliary unknowns "
            "retained"
        ),
        "cell_static_condensation_active": bool(cell_static_condensation),
        "floquet_slave_elimination_active": bool(
            floquet_slave_elimination
        ),
        "pass": passed,
    }


def matrix_factor_resource_audit(summary: dict[str, Any]) -> dict[str, Any]:
    """Normalize matrix/factor anatomy and direct-solve phase timings."""

    matrix_stats = summary.get("matrix_stats") or {}
    factor_inventory = summary.get("stage4_dtn_factor_inventory") or {}
    factor_stats = factor_inventory.get("matrix_stats") or {}
    matrix_nnz = matrix_stats.get("matrix_nnz_used")
    corrected_factor_nnz = factor_inventory.get("factor_nnz_corrected")
    factor_nnz = (
        corrected_factor_nnz
        if corrected_factor_nnz is not None
        else factor_stats.get("matrix_nnz_used")
    )
    factor_nnz_source = (
        factor_inventory.get("factor_nnz_corrected_source")
        if corrected_factor_nnz is not None
        else "petsc_factor_matrix_stats.matrix_nnz_used"
        if factor_nnz is not None
        else None
    )
    factor_rows = factor_stats.get("matrix_rows")
    factor_average_row_width = (
        float(corrected_factor_nnz) / float(factor_rows)
        if corrected_factor_nnz is not None
        and isinstance(factor_rows, (int, float))
        and float(factor_rows) > 0.0
        else factor_stats.get("matrix_average_nnz_per_row")
    )
    factor_average_row_width_source = (
        "corrected_factor_nnz_over_factor_rows"
        if corrected_factor_nnz is not None
        else "petsc_factor_matrix_stats.matrix_average_nnz_per_row"
    )
    fill_ratio = (
        None
        if matrix_nnz in (None, 0) or factor_nnz is None
        else float(factor_nnz) / float(matrix_nnz)
    )
    timing_keys = (
        "stage4_dtn_base_matrix_assembly_seconds",
        "stage4_dtn_base_rhs_assembly_seconds",
        "stage4_dtn_augmented_block_copy_seconds",
        "stage4_dtn_incident_source_vector_seconds",
        "stage4_dtn_modal_loop_seconds",
        "stage4_dtn_modal_vector_assembly_seconds",
        "stage4_dtn_modal_block_insert_seconds",
        "stage4_dtn_augmented_matrix_finalize_seconds",
        "stage4_dtn_cell_static_condensation_build_seconds",
        "stage4_dtn_cell_static_condensation_recovery_seconds",
        "stage4_dtn_floquet_slave_elimination_build_seconds",
        "stage4_dtn_ksp_setup_seconds",
        "stage4_dtn_ksp_solve_seconds",
        "stage4_dtn_linear_solve_seconds",
        "stage4_dtn_solution_backsubstitution_seconds",
        "elapsed_seconds",
    )
    return {
        "schema_version": "task035b.matrix-factor-resource-audit.v1",
        "active_rows": matrix_stats.get("matrix_rows"),
        "matrix_nnz": matrix_nnz,
        "matrix_average_row_width": matrix_stats.get(
            "matrix_average_nnz_per_row"
        ),
        "matrix_maximum_row_width": matrix_stats.get(
            "matrix_maximum_nnz_per_row"
        ),
        "factor_nnz": factor_nnz,
        "factor_nnz_source": factor_nnz_source,
        "factor_average_row_width": factor_average_row_width,
        "factor_average_row_width_source": (
            factor_average_row_width_source
        ),
        "factor_maximum_row_width": factor_stats.get(
            "matrix_maximum_nnz_per_row"
        ),
        "factor_fill_ratio": fill_ratio,
        "factor_solver_type": factor_inventory.get("factor_solver_type"),
        "factor_inventory_available": factor_inventory.get("available"),
        "timings_seconds": {key: summary.get(key) for key in timing_keys},
        "sum_rank_historical_peaks_mb_upper_bound": summary.get(
            "total_peak_rss_mb"
        ),
        "peak_memory_semantics": summary.get("total_peak_rss_semantics"),
    }


def build_high_order_resource_audit(
    field: Any,
    mesh_data: Any,
    summary: dict[str, Any],
) -> dict[str, Any]:
    """Build one complete high-order topology/resource record for a solve."""

    matrix_stats = summary.get("matrix_stats") or {}
    return {
        "schema_version": "task035b.high-order-resource-audit.v1",
        "mesh_identity": partition_independent_linear_mesh_identity(mesh_data),
        "entity_dof_inventory": hcurl_entity_dof_inventory(
            field.function_space,
            num_auxiliary_dofs=int(
                summary.get("stage4_dtn_num_auxiliary_dofs") or 0
            ),
            floquet_num_constraints=summary.get("floquet_num_constraints"),
            active_matrix_rows=matrix_stats.get("matrix_rows"),
            cell_static_condensation=bool(
                summary.get("stage4_cell_static_condensation")
            ),
            floquet_slave_elimination=bool(
                summary.get("stage4_floquet_slave_elimination")
            ),
        ),
        "matrix_factor_resource": matrix_factor_resource_audit(summary),
    }


__all__ = [
    "build_high_order_resource_audit",
    "hcurl_entity_dof_inventory",
    "matrix_factor_resource_audit",
    "partition_independent_linear_mesh_identity",
]
