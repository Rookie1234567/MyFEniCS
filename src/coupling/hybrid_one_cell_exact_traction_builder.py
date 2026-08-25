"""Build the research-only exact one-cell traction blocks for Hybrid direct."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
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
    TraceIdentityGateError,
    require_congruent_trace_identity,
    split_exact_local_amplitude_blocks,
    transfer_congruent_endpoint_columns,
    transfer_congruent_endpoint_dual_columns,
)


def _selected_mode_source_factor_event(
    stage_callback: Callable[[str, Mapping[str, Any]], None] | None,
    stage: str,
    detail: Mapping[str, Any],
) -> None:
    if stage_callback is not None:
        stage_callback(stage, detail)


class ExactOneCellSourceIdentityError(RuntimeError):
    """A primal/dual current-layout identity gate rejected one-cell sources."""


def _collective_source_identity_gate(
    comm,
    local_error: ExactOneCellSourceIdentityError | None,
) -> None:
    """Make an explicit source identity failure a rank-symmetric decision."""

    payload = None
    if local_error is not None:
        payload = {
            "message": str(local_error),
            "stage": getattr(local_error, "stage", "source_identity"),
        }
    gathered = comm.allgather(payload)
    first = next((item for item in gathered if item is not None), None)
    if first is not None:
        error = ExactOneCellSourceIdentityError(str(first["message"]))
        error.stage = str(first["stage"])
        error.local_errors = gathered
        raise error


def select_negative_bottom_backward_column(
    forward_flux: Any,
    backward_flux: Any,
    *,
    left_rows: int,
    right_rows: int,
    forward_factor: complex,
    backward_factor: complex,
) -> np.ndarray:
    """Select the frozen negative column after the exact ``/mu`` split.

    The exact one-cell splitter expects isolated forward/backward blocks.  The
    negative branch is therefore represented by ``(1, mu)`` and read from
    ``bottom_backward[:, 1]``; this helper keeps that source-definition wiring
    explicit and directly testable.
    """

    forward = np.asarray(forward_flux, dtype=np.complex128).reshape(-1)
    backward = np.asarray(backward_flux, dtype=np.complex128).reshape(-1)
    if forward.shape != backward.shape:
        raise ValueError("negative exact flux columns must have matching shapes")
    zero = np.zeros_like(forward)
    split = split_exact_local_amplitude_blocks(
        np.column_stack((zero, forward)),
        np.column_stack((zero, backward)),
        left_rows=int(left_rows),
        right_rows=int(right_rows),
        forward_factors=(1.0 + 0.0j, complex(forward_factor)),
        backward_factors=(1.0 + 0.0j, complex(backward_factor)),
    )
    return np.asarray(split["bottom_backward"][:, 1], dtype=np.complex128).copy()


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


def build_exact_one_cell_selected_traction_columns(
    cfg,
    selected_traces: Mapping[str, Any],
    *,
    positive_beta: complex,
    negative_beta: complex,
    positive_passive_branch_valid: bool,
    negative_passive_branch_valid: bool,
    bottom_system,
    work_dir: Path,
    stage_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> tuple[np.ndarray, dict[str, dict[str, np.ndarray]], dict[str, Any]]:
    """Build positive/negative frozen columns with one one-cell factor.

    The first and second ``apply_columns`` calls are independent source
    regenerations for the two selected traces.  Both branches share one
    current-layout one-cell action and its one interior MUMPS factor; the
    action is destroyed before this function returns.
    """

    required = {"positive", "negative"}
    if set(selected_traces) != required:
        raise ValueError("Selected exact one-cell traces must contain both branches.")
    if bottom_system.side != "bottom":
        raise ValueError("Selected exact one-cell source requires the bottom system.")
    if bottom_system.static_condensation is None:
        raise ValueError("Selected exact one-cell source requires condensation.")
    if not all(np.isfinite(complex(value)) for value in (positive_beta, negative_beta)):
        raise ValueError("Selected exact one-cell betas must be finite.")
    if not positive_passive_branch_valid or not negative_passive_branch_valid:
        raise ValueError("Selected exact one-cell branches are not passive-certified.")

    from ..solvers.one_cell_trace_schur import (
        EndpointModeLifter,
        _active_values_for_port,
        build_one_cell_two_port_schur_action,
        identify_endpoint_active_rows,
    )
    from ..modes.stable_propagation import build_two_sided_propagation

    comm = bottom_system.local_mesh.mesh.comm
    work_dir = Path(work_dir)
    if comm.rank == 0:
        work_dir.mkdir(parents=True, exist_ok=True)
    comm.Barrier()
    one_cfg = _one_cell_config(cfg, comm.size)
    mesh_data = V = floquet = condensed = action = None
    lifecycle: dict[str, Any] = {
        "factor_count_before": 0,
        "factor_count_ready": None,
        "factor_count_after": None,
        "factor_destroyed_before_return": None,
        "factor_matrix_alive_after_return": None,
        "mat_solve_call_count": 0,
        "rhs_columns_solved": 0,
        "apply_count": 0,
        "factor_construction_count": 0,
        "peak_simultaneous_factor_count": 0,
        "full_side_factor_overlap": False,
    }
    audit: dict[str, Any] = {
        "modal_traction_model": "full3d_one_cell_exact_schur",
        "propagation_model": "full3d_uniform_cg",
        "propagation_axial_fem_degree": int(one_cfg.nedelec_degree),
        "propagation_axial_h_nm": 10.0,
        "selected_columns": {"positive": 281, "negative": 283},
        "qep_calls": 0,
        "top_system_constructed": False,
        "full_coupling_constructed": False,
        "three_group_factor_count": 0,
        "one_cell_factor_lifecycle": lifecycle,
        "primal_endpoint_identity": None,
        "dual_endpoint_transfer": None,
        "raw_global_row_remap": False,
    }
    try:
        mesh_data = build_airbox_mesh_3d(one_cfg, work_dir / "mesh")
        V = _create_nedelec_space(mesh_data.mesh, one_cfg)
        bilinear, _ = _build_variational_forms(
            mesh_data.mesh,
            mesh_data,
            one_cfg,
            V,
        )
        floquet = build_double_floquet_mpc(V, mesh_data, one_cfg)
        condensed = build_unconstrained_assembly_time_condensation(
            fem.form(bilinear),
            V,
            mesh_data.cell_tags,
            mpc=floquet.mpc,
            materialize_global_matrix=True,
        )
        if condensed.matrix is None:
            raise RuntimeError("Selected exact one-cell source needs a sparse matrix.")
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
        lifecycle["factor_count_ready"] = 1
        lifecycle["factor_construction_count"] = 1
        lifecycle["peak_simultaneous_factor_count"] = 1
        _selected_mode_source_factor_event(
            stage_callback,
            "v5_one_cell_source_factor_ready",
            {
                "factor_count": 1,
                "factor_construction_count": 1,
                "active": 1,
                "peak_simultaneous_factor_count": 1,
                "factor_kind": "one_cell_interior_schur_mumps",
                "selected_columns": [281, 283],
                "top_system_constructed": False,
                "full_coupling_constructed": False,
                "full_side_factor_active": 0,
            },
        )

        propagation_modes = (
            SimpleNamespace(
                beta=complex(positive_beta),
                direction="forward",
                passive_branch_valid=bool(positive_passive_branch_valid),
            ),
            SimpleNamespace(
                beta=complex(negative_beta),
                direction="backward",
                passive_branch_valid=bool(negative_passive_branch_valid),
            ),
        )
        propagation = build_two_sided_propagation(
            propagation_modes,
            10.0,
            propagation_model="full3d_uniform_cg",
            axial_fem_degree=int(one_cfg.nedelec_degree),
            axial_h_nm=10.0,
        )
        lifter = EndpointModeLifter(
            V,
            max(float(one_cfg.period_x), float(one_cfg.period_y)),
        )

        def endpoint_values(trace) -> tuple[np.ndarray, np.ndarray]:
            field = lifter.lift(trace)
            floquet.mpc.homogenize(field)
            field.x.scatter_forward()
            return (
                _active_values_for_port(field, condensed, one_rows.left_active),
                _active_values_for_port(field, condensed, one_rows.right_active),
            )

        positive_left, positive_right = endpoint_values(selected_traces["positive"])
        negative_left, negative_right = endpoint_values(selected_traces["negative"])
        left_columns = np.column_stack((positive_left, negative_left))
        bottom_rows = _local_interface_active_rows(bottom_system)
        bottom_direct = _lift_port_columns(
            bottom_system.V,
            bottom_system.floquet_data.mpc,
            bottom_system.static_condensation.condensed,
            bottom_rows,
            (selected_traces["positive"], selected_traces["negative"]),
            max(float(cfg.period_x), float(cfg.period_y)),
        )
        primal_transferred, primal_audit = transfer_congruent_endpoint_columns(
            left_columns,
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
        primal_identity = None
        primal_error = None
        try:
            primal_identity = require_congruent_trace_identity(
                primal_transferred,
                bottom_direct,
                side="bottom",
            )
        except TraceIdentityGateError as exc:
            primal_error = ExactOneCellSourceIdentityError(
                "selected modal primal endpoint/current-interface identity failed"
            )
            primal_error.stage = "primal_endpoint_identity"
            primal_error.identity_gate_cause = str(exc)
        _collective_source_identity_gate(comm, primal_error)
        if primal_identity is None:
            raise AssertionError("collective primal identity returned no audit")
        primal_identity["entity_transfer"] = primal_audit
        audit["primal_endpoint_identity"] = primal_identity

        positive_directional = np.vstack(
            (
                positive_left[:, None],
                positive_right[:, None] * propagation.forward.factors[0],
            )
        )
        positive_left_repeat, positive_right_repeat = endpoint_values(
            selected_traces["positive"]
        )
        negative_left_repeat, negative_right_repeat = endpoint_values(
            selected_traces["negative"]
        )
        negative_directional = np.vstack(
            (
                negative_left[:, None] * propagation.backward.factors[0],
                negative_right[:, None],
            )
        )
        directional = np.column_stack((positive_directional, negative_directional))
        repeat_directional = np.column_stack(
            (
                np.vstack(
                    (
                        positive_left_repeat[:, None],
                        positive_right_repeat[:, None] * propagation.forward.factors[0],
                    )
                ),
                np.vstack(
                    (
                        negative_left_repeat[:, None] * propagation.backward.factors[0],
                        negative_right_repeat[:, None],
                    )
                ),
            )
        )
        first_flux = action.apply_columns(directional)
        lifecycle["apply_count"] = 1
        lifecycle["mat_solve_call_count"] = 1
        lifecycle["rhs_columns_solved"] = 2
        _selected_mode_source_factor_event(
            stage_callback,
            "v5_one_cell_source_factor_apply",
            {
                "factor_count": 1,
                "active": 1,
                "apply_count": 1,
                "mat_solve_call_count": 1,
                "rhs_columns_solved": 2,
            },
        )
        repeat_flux = action.apply_columns(repeat_directional)
        lifecycle["apply_count"] = 2
        lifecycle["mat_solve_call_count"] = 2
        lifecycle["rhs_columns_solved"] = 4
        _selected_mode_source_factor_event(
            stage_callback,
            "v5_one_cell_source_factor_apply",
            {
                "factor_count": 1,
                "active": 1,
                "apply_count": 2,
                "mat_solve_call_count": 2,
                "rhs_columns_solved": 4,
            },
        )
        left_count = len(one_rows.left_active)
        first_split = split_exact_local_amplitude_blocks(
            np.column_stack((first_flux[:, 0], np.zeros_like(first_flux[:, 0]))),
            np.column_stack((np.zeros_like(first_flux[:, 1]), first_flux[:, 1])),
            left_rows=left_count,
            right_rows=len(one_rows.right_active),
            forward_factors=(propagation.forward.factors[0], 1.0 + 0.0j),
            backward_factors=(1.0 + 0.0j, propagation.backward.factors[0]),
        )
        repeat_split = split_exact_local_amplitude_blocks(
            np.column_stack((repeat_flux[:, 0], np.zeros_like(repeat_flux[:, 0]))),
            np.column_stack((np.zeros_like(repeat_flux[:, 1]), repeat_flux[:, 1])),
            left_rows=left_count,
            right_rows=len(one_rows.right_active),
            forward_factors=(propagation.forward.factors[0], 1.0 + 0.0j),
            backward_factors=(1.0 + 0.0j, propagation.backward.factors[0]),
        )
        negative_first = select_negative_bottom_backward_column(
            first_flux[:, 0],
            first_flux[:, 1],
            left_rows=left_count,
            right_rows=len(one_rows.right_active),
            forward_factor=1.0 + 0.0j,
            backward_factor=propagation.backward.factors[0],
        )
        bottom_flux = np.column_stack(
            (first_split["bottom_forward"][:, 0], negative_first)
        )
        negative_repeat = select_negative_bottom_backward_column(
            repeat_flux[:, 0],
            repeat_flux[:, 1],
            left_rows=left_count,
            right_rows=len(one_rows.right_active),
            forward_factor=1.0 + 0.0j,
            backward_factor=propagation.backward.factors[0],
        )
        repeat_bottom_flux = np.column_stack(
            (repeat_split["bottom_forward"][:, 0], negative_repeat)
        )
        dual_transferred, dual_audit = transfer_congruent_endpoint_dual_columns(
            bottom_flux,
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
        repeat_transferred, repeat_dual_audit = (
            transfer_congruent_endpoint_dual_columns(
                repeat_bottom_flux,
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
        dual_error = None
        if (
            not np.isfinite(dual_transferred).all()
            or not np.isfinite(repeat_transferred).all()
        ):
            dual_error = ExactOneCellSourceIdentityError(
                "selected modal dual transfer is non-finite"
            )
            dual_error.stage = "dual_endpoint_identity"
        for repeat_name, dual_audit_item in (
            ("first", dual_audit),
            ("repeat", repeat_dual_audit),
        ):
            reconstruction_error = float(
                dual_audit_item["dual_inverse_map_reconstruction_error"]
            )
            if not np.isfinite(reconstruction_error):
                dual_error = ExactOneCellSourceIdentityError(
                    f"selected modal {repeat_name} dual transfer is non-finite"
                )
                dual_error.stage = "dual_endpoint_identity"
            elif reconstruction_error > 1.0e-12:
                dual_error = ExactOneCellSourceIdentityError(
                    f"selected modal {repeat_name} dual inverse-map identity "
                    f"failed: {reconstruction_error:.6e} > 1e-12"
                )
                dual_error.stage = "dual_endpoint_identity"
        _collective_source_identity_gate(comm, dual_error)
        audit["dual_endpoint_transfer"] = {
            "first": dual_audit,
            "repeat": repeat_dual_audit,
        }
        return (
            bottom_rows.copy(),
            {
                "positive": {
                    "values": dual_transferred[:, 0].copy(),
                    "repeat_values": repeat_transferred[:, 0].copy(),
                },
                "negative": {
                    "values": dual_transferred[:, 1].copy(),
                    "repeat_values": repeat_transferred[:, 1].copy(),
                },
            },
            audit,
        )
    finally:
        if action is not None:
            action.destroy()
            lifecycle["factor_count_after"] = 0 if action._destroyed else None
            lifecycle["factor_destroyed_before_return"] = bool(action._destroyed)
            lifecycle["factor_matrix_alive_after_return"] = not bool(action._destroyed)
            _selected_mode_source_factor_event(
                stage_callback,
                "v5_one_cell_source_factor_destroyed",
                {
                    "factor_count": lifecycle["factor_count_after"],
                    "factor_destroyed": lifecycle["factor_destroyed_before_return"],
                    "factor_matrix_alive": lifecycle[
                        "factor_matrix_alive_after_return"
                    ],
                    "factor_construction_count": lifecycle["factor_construction_count"],
                    "mat_solve_call_count": lifecycle["mat_solve_call_count"],
                    "rhs_columns_solved": lifecycle["rhs_columns_solved"],
                    "apply_count": lifecycle["apply_count"],
                    "active": 0,
                    "full_side_factor_active": 0,
                },
            )
        if condensed is not None:
            condensed.destroy()
        if floquet is not None and getattr(floquet, "mpc", None) is not None:
            floquet.mpc.destroy()


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
            array_scope="replicated_lift_output_combined_left_right",
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


__all__ = [
    "ExactOneCellMatrixBuild",
    "ExactOneCellSourceIdentityError",
    "build_exact_one_cell_selected_traction_columns",
    "build_exact_one_cell_traction_matrices",
    "select_negative_bottom_backward_column",
]
