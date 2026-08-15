"""Build the research-only exact one-cell traction blocks for Hybrid direct."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np
from dolfinx import fem, mesh
from petsc4py import PETSc

from ..common.config_3d import ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND
from ..constraints.floquet_3d import build_double_floquet_mpc
from ..geometry.mesh_builder_3d import build_airbox_mesh_3d, stage4_axis_plan
from ..solvers.common_3d_forms import _build_variational_forms
from ..solvers.common_3d_solve import _create_nedelec_space
from ..solvers.hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
)
from .hybrid_one_cell_exact_traction import (
    ExactOneCellCoupling,
    require_congruent_trace_identity,
    split_exact_local_amplitude_blocks,
    transfer_congruent_endpoint_columns,
    transfer_congruent_endpoint_dual_columns,
)


@dataclass(frozen=True)
class ExactOneCellMatrixBuild:
    """Exact traction matrices and immutable numerical audit."""

    matrices: dict[str, tuple[PETSc.Mat, PETSc.Mat]]
    audit: dict[str, Any]


def _replicated_array_marker_detail(
    rows: int,
    nrhs: int,
    mpi_size: int,
    *,
    array_scope: str,
) -> dict[str, Any]:
    """Describe a replicated NumPy lift/projection array, without PETSc payload."""

    per_rank = int(rows) * int(nrhs) * 16
    return {
        "rows": int(rows),
        "nrhs": int(nrhs),
        "column_blocks": 1,
        "replicated_numpy_array_bytes_per_rank": per_rank,
        "replicated_numpy_array_bytes_process_tree": per_rank * int(mpi_size),
        "replicated_array_formula": (
            "rows*nrhs*16 bytes per rank; process-tree value multiplies by MPI size"
        ),
        "array_scope": array_scope,
        "classification": "derived_complex128_dense_buffer",
    }


def _apply_columns_marker_detail(
    port_rows: int,
    interior_rows: int,
    nrhs: int,
    mpi_size: int,
    *,
    direction: str,
) -> dict[str, Any]:
    """Describe the five PETSc dense payloads and separate NumPy I/O arrays."""

    input_per_rank = int(port_rows) * int(nrhs) * 16
    output_per_rank = input_per_rank
    return {
        "rows": int(port_rows),
        "port_rows": int(port_rows),
        "interior_rows": int(interior_rows),
        "nrhs": int(nrhs),
        "column_blocks": 1,
        "direction": direction,
        "distributed_petsc_5mat_payload_lower_bound_bytes": int(
            (3 * int(port_rows) + 2 * int(interior_rows)) * int(nrhs) * 16
        ),
        "replicated_input_numpy_bytes_per_rank": input_per_rank,
        "replicated_input_numpy_bytes_process_tree": input_per_rank * int(mpi_size),
        "replicated_output_numpy_bytes_per_rank": output_per_rank,
        "replicated_output_numpy_bytes_process_tree": output_per_rank * int(mpi_size),
        "dense_buffer_formula": (
            "five PETSc dense payloads use (3*port_rows + 2*interior_rows)*nrhs*16; "
            "input and output each use port_rows*nrhs*16 per rank and multiply by "
            "MPI size for process-tree estimates"
        ),
        "classification": "derived_complex128_dense_buffer",
    }


def _one_cell_config(cfg, comm_size: int):
    source_plan = stage4_axis_plan(cfg, int(comm_size))
    source_x_cells, source_y_cells, _ = source_plan.mesh_cells_resolved
    return replace(
        cfg,
        case_name=f"{cfg.case_name}_exact_one_cell",
        z_min=0.0,
        z_max=10.0,
        air_height=10.0,
        substrate_thickness=0.0,
        interface_z=0.0,
        grating_height=10.0,
        mesh_axis_cell_counts=(source_x_cells, source_y_cells, 1),
        mesh_axis_z_values=(0.0, 10.0),
        mesh_axis_z_profile="task037c_x3_uniform_10nm_one_cell",
        mesh_cell_type="hexahedron",
        mesh_spacing_mode="boundary_fitted",
        stage4_full3d_assembly_backend=ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
    )


def _local_interface_active_rows(system) -> np.ndarray:
    from ..solvers.one_cell_trace_schur import _owned_original_rows_on_facets

    if system.static_condensation is None:
        raise ValueError("Exact one-cell traction requires local condensation.")
    condensed = system.static_condensation.condensed
    facets = system.local_mesh.mesh_data.facet_tags.find(
        system.local_mesh.interface_facet_tag
    )
    original = _owned_original_rows_on_facets(system.V, facets)
    active: set[int] = set()
    for row in original:
        expansion = condensed.trace_constraints.expansion_by_original.get(int(row))
        if expansion is None:
            raise RuntimeError(
                f"Local interface original row {int(row)} is not condensed."
            )
        active.update(int(value) for value in expansion[0])
    result = np.asarray(sorted(active), dtype=PETSc.IntType)
    if not len(result) or np.any(result >= int(condensed.active_rows)):
        raise RuntimeError("Local exact interface active rows are invalid.")
    return result


def _owned_interface_matrix(system, rows: np.ndarray, columns: np.ndarray) -> PETSc.Mat:
    """Insert only owned FE interface rows into the production-shaped matrix."""

    from .hybrid_internal_modes import _create_rectangular_aij

    values = np.asarray(columns, dtype=np.complex128)
    if values.ndim != 2 or values.shape[0] != len(rows):
        raise ValueError("Exact interface columns and row count differ.")
    if not np.all(np.isfinite(values)):
        raise ValueError("Exact interface columns must be finite.")
    comm = system.local_mesh.mesh.comm
    matrix = _create_rectangular_aij(
        comm,
        global_rows=system.global_size,
        local_rows=system.A.getLocalSize()[0],
        global_cols=values.shape[1],
        local_cols=values.shape[1] if comm.rank == comm.size - 1 else 0,
    )
    if matrix.getOwnershipRange() != system.A.getOwnershipRange():
        matrix.destroy()
        raise RuntimeError("Exact traction matrix ownership differs from local A.")
    first, last = system.A.getOwnershipRange()
    owned = (rows >= first) & (rows < last)
    if np.any(owned):
        matrix.setValues(
            rows[owned],
            np.arange(values.shape[1], dtype=PETSc.IntType),
            values[owned, :],
            addv=PETSc.InsertMode.INSERT_VALUES,
        )
    matrix.assemble()
    return matrix


def _lift_port_columns(
    V,
    mpc,
    condensed,
    rows: Sequence[int],
    sources,
    axis_scale_nm: float,
) -> np.ndarray:
    from ..solvers.one_cell_trace_schur import EndpointModeLifter
    from ..solvers.one_cell_trace_schur import _active_values_for_port

    lifter = EndpointModeLifter(V, axis_scale_nm)
    columns = []
    for source in sources:
        field = lifter.lift(source)
        mpc.homogenize(field)
        field.x.scatter_forward()
        columns.append(_active_values_for_port(field, condensed, rows))
    return np.column_stack(columns)


def build_exact_one_cell_traction_matrices(
    cfg,
    positive_basis,
    raw_negative_traces,
    projection,
    cell_propagation,
    bottom_system,
    top_system,
    *,
    work_dir: Path,
    coupling_propagation_length_nm: float,
    log=None,
    stage_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
    post_destroy_cleanup: Callable[[], Mapping[str, Any]] | None = None,
) -> ExactOneCellMatrixBuild:
    """Construct exact one-cell blocks from live modes and local systems."""

    from ..solvers.one_cell_trace_schur import (
        EndpointModeLifter,
        build_one_cell_two_port_schur_action,
        identify_endpoint_active_rows,
        lifted_endpoint_columns,
    )

    if abs(float(cell_propagation.length_nm) - 10.0) > 1.0e-12:
        raise ValueError("Exact one-cell propagation must have length 10 nm.")
    if abs(float(coupling_propagation_length_nm) - 100.0) > 1.0e-12:
        raise ValueError("Exact Hybrid coupling propagation must have length 100 nm.")
    if cell_propagation.propagation_model != "full3d_uniform_cg":
        raise ValueError("Exact one-cell traction requires full3d_uniform_cg.")
    mode_count = len(positive_basis.modes)
    if mode_count == 0 or len(raw_negative_traces) != mode_count:
        raise ValueError("Exact one-cell sources must match the positive mode count.")
    if (
        len(projection.right_traces) != mode_count
        or len(projection.left_traces) != mode_count
    ):
        raise ValueError("Exact one-cell projection dimensions do not match modes.")

    work_dir = Path(work_dir)
    comm = bottom_system.local_mesh.mesh.comm
    if comm.rank == 0:
        work_dir.mkdir(parents=True, exist_ok=True)
    comm.Barrier()
    mesh_data = V = floquet = condensed = action = None
    matrices: dict[str, tuple[PETSc.Mat, PETSc.Mat]] = {}
    try:
        one_cfg = _one_cell_config(cfg, comm.size)
        mesh_data = build_airbox_mesh_3d(one_cfg, work_dir / "mesh")
        V = _create_nedelec_space(mesh_data.mesh, one_cfg)
        bilinear, _ = _build_variational_forms(mesh_data.mesh, mesh_data, one_cfg, V)
        floquet = build_double_floquet_mpc(V, mesh_data, one_cfg)
        condensed = build_unconstrained_assembly_time_condensation(
            fem.form(bilinear),
            V,
            mesh_data.cell_tags,
            mpc=floquet.mpc,
            materialize_global_matrix=True,
        )
        if condensed.matrix is None:
            raise RuntimeError("Exact one-cell builder requires a sparse matrix.")
        tdim = mesh_data.mesh.topology.dim
        left_facets = mesh.locate_entities_boundary(
            mesh_data.mesh,
            tdim - 1,
            lambda x: np.isclose(x[2], one_cfg.domain_z_min),
        )
        right_facets = mesh.locate_entities_boundary(
            mesh_data.mesh,
            tdim - 1,
            lambda x: np.isclose(x[2], one_cfg.domain_z_max),
        )
        one_rows = identify_endpoint_active_rows(
            V,
            condensed,
            left_facets=left_facets,
            right_facets=right_facets,
        )
        action = build_one_cell_two_port_schur_action(condensed.matrix, one_rows)
        if stage_callback is not None:
            stage_callback(
                "one_cell_factor_ready",
                {
                    "rows": int(action.port_rows),
                    "port_rows": int(action.port_rows),
                    "interior_rows": int(action.interior_rows),
                    "nrhs": 0,
                    "column_blocks": 0,
                    "factor_count": 1,
                    "classification": "measured_from_worker_record",
                },
            )
        sources = (*projection.right_traces, *raw_negative_traces)
        lift_detail = _replicated_array_marker_detail(
            action.port_rows,
            2 * mode_count,
            comm.size,
            array_scope="replicated_lift_input_output",
        )
        if stage_callback is not None:
            stage_callback("one_cell_lift_columns_begin", lift_detail)
        one_left, one_right = lifted_endpoint_columns(
            sources,
            EndpointModeLifter(V, max(one_cfg.period_x, one_cfg.period_y)),
            condensed,
            one_rows,
            mpc=floquet.mpc,
        )
        if stage_callback is not None:
            stage_callback("one_cell_lift_columns_end", lift_detail)
        pos_left = one_left[:, :mode_count]
        pos_right = one_right[:, :mode_count]
        neg_left = one_left[:, mode_count:]
        neg_right = one_right[:, mode_count:]
        lam = np.asarray(cell_propagation.forward.factors, dtype=np.complex128)
        mu = np.asarray(cell_propagation.backward.factors, dtype=np.complex128)
        if lam.shape != (mode_count,) or mu.shape != (mode_count,):
            raise RuntimeError("Cell propagation factors do not match the modes.")
        if stage_callback is not None:
            stage_callback(
                "one_cell_apply_columns_begin",
                _apply_columns_marker_detail(
                    action.port_rows,
                    action.interior_rows,
                    mode_count,
                    comm.size,
                    direction="forward",
                ),
            )
        exact_forward = action.apply_columns(
            np.vstack((pos_left, pos_right * lam[None, :]))
        )
        if stage_callback is not None:
            stage_callback(
                "one_cell_apply_columns_end",
                _apply_columns_marker_detail(
                    action.port_rows,
                    action.interior_rows,
                    mode_count,
                    comm.size,
                    direction="forward",
                ),
            )
            stage_callback(
                "one_cell_apply_columns_begin",
                _apply_columns_marker_detail(
                    action.port_rows,
                    action.interior_rows,
                    mode_count,
                    comm.size,
                    direction="backward",
                ),
            )
        exact_backward = action.apply_columns(
            np.vstack((neg_left * mu[None, :], neg_right))
        )
        if stage_callback is not None:
            stage_callback(
                "one_cell_apply_columns_end",
                _apply_columns_marker_detail(
                    action.port_rows,
                    action.interior_rows,
                    mode_count,
                    comm.size,
                    direction="backward",
                ),
            )
        exact_blocks = split_exact_local_amplitude_blocks(
            exact_forward,
            exact_backward,
            left_rows=len(one_rows.left_active),
            right_rows=len(one_rows.right_active),
            forward_factors=lam,
            backward_factors=mu,
        )
        bottom_rows = _local_interface_active_rows(bottom_system)
        top_rows = _local_interface_active_rows(top_system)
        bottom_projection_detail = _replicated_array_marker_detail(
            len(bottom_rows),
            2 * mode_count,
            comm.size,
            array_scope="replicated_bottom_projection_array",
        )
        if stage_callback is not None:
            stage_callback("bottom_projection_columns_begin", bottom_projection_detail)
        bottom_pos = _lift_port_columns(
            bottom_system.V,
            bottom_system.floquet_data.mpc,
            bottom_system.static_condensation.condensed,
            bottom_rows,
            sources,
            max(cfg.period_x, cfg.period_y),
        )
        if stage_callback is not None:
            stage_callback("bottom_projection_columns_end", bottom_projection_detail)
        top_projection_detail = _replicated_array_marker_detail(
            len(top_rows),
            2 * mode_count,
            comm.size,
            array_scope="replicated_top_projection_array",
        )
        if stage_callback is not None:
            stage_callback("top_projection_columns_begin", top_projection_detail)
        top_pos = _lift_port_columns(
            top_system.V,
            top_system.floquet_data.mpc,
            top_system.static_condensation.condensed,
            top_rows,
            sources,
            max(cfg.period_x, cfg.period_y),
        )
        if stage_callback is not None:
            stage_callback("top_projection_columns_end", top_projection_detail)
        bottom_pos_transferred_all, bottom_positive_transfer_audit = (
            transfer_congruent_endpoint_columns(
                one_left,
                V,
                condensed,
                floquet,
                one_rows.left_active,
                bottom_system.V,
                bottom_system.static_condensation.condensed,
                bottom_system.floquet_data,
                bottom_rows,
                source_endpoint="left",
                target_endpoint="right",
            )
        )
        top_pos_transferred_all, top_positive_transfer_audit = (
            transfer_congruent_endpoint_columns(
                one_right,
                V,
                condensed,
                floquet,
                one_rows.right_active,
                top_system.V,
                top_system.static_condensation.condensed,
                top_system.floquet_data,
                top_rows,
                source_endpoint="right",
                target_endpoint="left",
            )
        )
        bottom_pos_transferred = bottom_pos_transferred_all[:, :mode_count]
        bottom_negative_transferred = bottom_pos_transferred_all[:, mode_count:]
        top_pos_transferred = top_pos_transferred_all[:, :mode_count]
        top_negative_transferred = top_pos_transferred_all[:, mode_count:]
        bottom_positive_identity = require_congruent_trace_identity(
            bottom_pos_transferred,
            bottom_pos[:, :mode_count],
            side="bottom",
        )
        bottom_positive_identity["entity_transfer"] = bottom_positive_transfer_audit
        top_positive_identity = require_congruent_trace_identity(
            top_pos_transferred,
            top_pos[:, :mode_count],
            side="top",
        )
        top_positive_identity["entity_transfer"] = top_positive_transfer_audit
        bottom_negative_identity = require_congruent_trace_identity(
            bottom_negative_transferred,
            bottom_pos[:, mode_count:],
            side="bottom",
        )
        bottom_negative_identity["entity_transfer"] = bottom_positive_transfer_audit
        top_negative_identity = require_congruent_trace_identity(
            top_negative_transferred,
            top_pos[:, mode_count:],
            side="top",
        )
        top_negative_identity["entity_transfer"] = top_positive_transfer_audit
        row_identity = {
            "bottom": {
                "positive": bottom_positive_identity,
                "raw_negative": bottom_negative_identity,
            },
            "top": {
                "positive": top_positive_identity,
                "raw_negative": top_negative_identity,
            },
        }
        if not all(
            item["pass"] is True
            for side in row_identity.values()
            for item in side.values()
        ):
            raise RuntimeError("Exact one-cell/local interface row identity failed.")
        bottom_dual_source = np.column_stack(
            (exact_blocks["bottom_forward"], exact_blocks["bottom_backward"])
        )
        top_dual_source = np.column_stack(
            (exact_blocks["top_forward"], exact_blocks["top_backward"])
        )
        bottom_dual_transferred, bottom_dual_transfer_audit = (
            transfer_congruent_endpoint_dual_columns(
                bottom_dual_source,
                V,
                condensed,
                floquet,
                one_rows.left_active,
                bottom_system.V,
                bottom_system.static_condensation.condensed,
                bottom_system.floquet_data,
                bottom_rows,
                source_endpoint="left",
                target_endpoint="right",
            )
        )
        top_dual_transferred, top_dual_transfer_audit = (
            transfer_congruent_endpoint_dual_columns(
                top_dual_source,
                V,
                condensed,
                floquet,
                one_rows.right_active,
                top_system.V,
                top_system.static_condensation.condensed,
                top_system.floquet_data,
                top_rows,
                source_endpoint="right",
                target_endpoint="left",
            )
        )
        dual_audits = (bottom_dual_transfer_audit, top_dual_transfer_audit)
        if any(
            not np.isfinite(audit["dual_inverse_map_reconstruction_error"])
            or audit["dual_inverse_map_reconstruction_error"] > 1.0e-12
            for audit in dual_audits
        ):
            raise RuntimeError("Exact endpoint dual transfer reconstruction failed.")
        exact_blocks = {
            "bottom_forward": bottom_dual_transferred[:, :mode_count],
            "bottom_backward": bottom_dual_transferred[:, mode_count:],
            "top_forward": top_dual_transferred[:, :mode_count],
            "top_backward": top_dual_transferred[:, mode_count:],
        }
        carrier = ExactOneCellCoupling(
            blocks=exact_blocks,
            bottom_rows=bottom_rows,
            top_rows=top_rows,
            row_identity=row_identity,
            action_audit={
                "port_rows": int(action.port_rows),
                "interior_rows": int(action.interior_rows),
                "interior_matrix_nnz": int(action.interior_matrix_nnz),
            },
            dense_endpoint_square_formed=bool(action.dense_interface_square_formed),
        )
        bottom_forward = _owned_interface_matrix(
            bottom_system, bottom_rows, carrier.blocks["bottom_forward"]
        )
        try:
            bottom_backward = _owned_interface_matrix(
                bottom_system, bottom_rows, carrier.blocks["bottom_backward"]
            )
        except Exception:
            bottom_forward.destroy()
            raise
        matrices["bottom"] = (bottom_forward, bottom_backward)
        top_forward = _owned_interface_matrix(
            top_system, top_rows, carrier.blocks["top_forward"]
        )
        try:
            top_backward = _owned_interface_matrix(
                top_system, top_rows, carrier.blocks["top_backward"]
            )
        except Exception:
            top_forward.destroy()
            raise
        matrices["top"] = (top_forward, top_backward)
        if log is not None:
            log(
                "Task37c exact one-cell traction columns inserted on owned interface rows"
            )
        audit = carrier.audit()
        audit.update(
            {
                "research_only": True,
                "production_qualified": False,
                "cell_length_nm": float(cell_propagation.length_nm),
                "coupling_propagation_length_nm": float(coupling_propagation_length_nm),
                "cell_propagation_factors": {
                    "forward": [
                        [float(value.real), float(value.imag)] for value in lam
                    ],
                    "backward": [
                        [float(value.real), float(value.imag)] for value in mu
                    ],
                },
                "operator_shapes": {
                    "bottom_positive": list(matrices["bottom"][0].getSize()),
                    "bottom_negative": list(matrices["bottom"][1].getSize()),
                    "top_positive": list(matrices["top"][0].getSize()),
                    "top_negative": list(matrices["top"][1].getSize()),
                },
                "entity_transfer": {
                    "bottom": bottom_dual_transfer_audit,
                    "top": top_dual_transfer_audit,
                },
            }
        )
        return ExactOneCellMatrixBuild(matrices=matrices, audit=audit)
    except Exception:
        for pair in matrices.values():
            for matrix in pair:
                matrix.destroy()
        raise
    finally:
        cleanup_detail = None
        if action is not None:
            cleanup_detail = {
                "rows": int(action.port_rows),
                "port_rows": int(action.port_rows),
                "interior_rows": int(action.interior_rows),
                "nrhs": int(2 * mode_count),
                "column_blocks": 1,
                "classification": "measured_from_worker_record",
            }
        if action is not None:
            action.destroy()
        if condensed is not None:
            condensed.destroy()
        cleanup_result = (
            post_destroy_cleanup() if post_destroy_cleanup is not None else None
        )
        if stage_callback is not None:
            cleanup_attempted = post_destroy_cleanup is not None
            cleanup_completed = bool(
                isinstance(cleanup_result, Mapping)
                and cleanup_result.get("collective_call_completed") is True
            )
            cleanup_status = (
                "completed"
                if cleanup_completed
                else "attempted_incomplete"
                if cleanup_attempted
                else "not_run"
            )
            stage_callback(
                "one_cell_factor_destroyed",
                {
                    **(cleanup_detail or {}),
                    "cleanup_attempted": cleanup_attempted,
                    "cleanup_completed": cleanup_completed,
                    "cleanup_status": cleanup_status,
                    "cleanup_result": cleanup_result,
                },
            )


__all__ = ["ExactOneCellMatrixBuild", "build_exact_one_cell_traction_matrices"]
