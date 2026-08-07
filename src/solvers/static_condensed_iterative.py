from __future__ import annotations

import hashlib
from time import perf_counter
from typing import Any, Callable, Literal

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from src.constraints.floquet_3d_high_order import floquet_geometry_tolerance

from .condensed_dtn import (
    combine_petsc_augmented_solution,
    condensed_rhs,
    create_matrix_free_condensed_operator,
    extract_petsc_condensed_blocks,
    full_augmented_relative_residual,
    recover_petsc_auxiliary,
    relative_action_error,
)
from .dtn_port_3d import (
    Stage4ExternalLinearSolverRequest,
    Stage4ExternalLinearSolverSnapshot,
    Stage4NeverMaterializedLinearSolverRequest,
)
from .physical_slab_two_level import (
    DistributedPhysicalSlabSmoother,
    SparseGalerkinTwoLevelPc,
    build_active_trace_floquet_basis,
    build_owner_local_slab_diagonal,
    build_owner_local_slab_plan,
    build_trace_aware_physical_slab_partition,
    collect_owner_local_fullspace_slab_cells,
    collect_owner_local_lor_transfer,
    extract_owner_local_slab_vector,
)
from .static_fullspace_slab_oracle import (
    apply_fullspace_slab_schur_action,
    measure_fullspace_slab_identity,
)
from .static_lor_hcurl_slab_oracle import build_physical_lor_hcurl_slab_oracle
from .static_local_schur_action import create_static_local_schur_action
from .static_p2_auxiliary_pc import build_p2_auxiliary_setup


__all__ = (
    "solve_assembled_static_condensed_fgmres",
    "solve_never_materialized_static_condensed_fgmres",
    "solve_never_materialized_overlap0125_partition_fgmres",
    "solve_never_materialized_p2_auxiliary_fgmres",
    "solve_never_materialized_p2_factor_free_slab_auxiliary_fgmres",
    "solve_never_materialized_p2_factor_free_slab_ras_auxiliary_fgmres",
)
_TINY = np.finfo(float).tiny


class _ShiftedFineAction:
    """MatPython action borrowing F and owning its diagonal shift."""

    def __init__(self, fine: PETSc.Mat, shift: PETSc.Vec) -> None:
        self.fine = fine
        self.shift = shift
        self.destroyed = False

    def mult(self, _matrix: PETSc.Mat, source: PETSc.Vec, target: PETSc.Vec) -> None:
        self.fine.mult(source, target)
        target.getArray()[:] += self.shift.getArray(readonly=True) * source.getArray(
            readonly=True
        )

    def destroy(self, _matrix: PETSc.Mat | None = None) -> None:
        if not self.destroyed:
            self.shift.destroy()
            self.destroyed = True


def _relative_residual(
    operator: PETSc.Mat,
    rhs: PETSc.Vec,
    solution: PETSc.Vec,
    work: PETSc.Vec,
    rhs_norm: float,
) -> float:
    operator.mult(solution, work)
    work.scale(PETSc.ScalarType(-1.0))
    work.axpy(PETSc.ScalarType(1.0), rhs)
    return float(work.norm()) / max(rhs_norm, _TINY)


_TASK037_G2_SLAB = 14
_TASK037_G2_IDENTITY_TOLERANCE = 1.0e-10
_TASK037_G2_LOR_TOLERANCE = 1.0e-11
_TASK037_G2_DETERMINISTIC_VECTOR_LABELS = (
    "canonical_affine_phase",
    "canonical_complex_affine_phase",
    "canonical_sinusoidal_phase",
)


def _task037_g2_deterministic_vectors(owner_rows: np.ndarray) -> tuple[np.ndarray, ...]:
    rows = np.asarray(owner_rows, dtype=np.float64)
    scale = max(float(rows.size), 1.0)
    phase = (rows + 1.0) / scale
    return (
        np.asarray(1.0 + 0.125j * phase, dtype=np.complex128),
        np.asarray(
            1.0 + 0.25 * phase + 1j * (0.5 - 0.125 * phase),
            dtype=np.complex128,
        ),
        np.asarray(
            np.sin(2.0 * np.pi * phase)
            + 1j * np.cos(2.0 * np.pi * phase),
            dtype=np.complex128,
        ),
    )


def _task037_g2_owner_vector_sha256(
    owner_rows: np.ndarray,
    values: np.ndarray,
    *,
    domain: str,
) -> str:
    rows = np.ascontiguousarray(owner_rows, dtype="<i8")
    vector = np.ascontiguousarray(values, dtype="<c16")
    digest = hashlib.sha256()
    digest.update(domain.encode("ascii"))
    digest.update(b"|owner_rows=<i8|values=<c16|order=C\0")
    digest.update(np.asarray([rows.size], dtype="<u8").tobytes())
    digest.update(rows.tobytes(order="C"))
    digest.update(vector.tobytes(order="C"))
    return digest.hexdigest()


def _task037_g2_lor_vector_sha256(values: np.ndarray, *, domain: str) -> str:
    vector = np.ascontiguousarray(values, dtype="<c16")
    digest = hashlib.sha256()
    digest.update(domain.encode("ascii"))
    digest.update(b"|values=<c16|order=C\0")
    digest.update(np.asarray([vector.size], dtype="<u8").tobytes())
    digest.update(vector.tobytes(order="C"))
    return digest.hexdigest()


def _task037_g2_local_schur_contraction(
    residual: np.ndarray,
    post_action: np.ndarray,
) -> dict[str, float | bool]:
    residual = np.asarray(residual, dtype=PETSc.ScalarType)
    post_action = np.asarray(post_action, dtype=PETSc.ScalarType)
    if residual.shape != post_action.shape:
        raise ValueError("local residual and Schur action shapes must match")
    input_norm = float(np.linalg.norm(residual))
    if input_norm == 0.0:
        raise ValueError("local Schur contraction requires a nonzero residual")
    post_norm = float(np.linalg.norm(post_action))
    return {
        "input_norm": input_norm,
        "post_norm": post_norm,
        "rho": post_norm / input_norm,
        "finite": bool(
            np.isfinite(residual).all()
            and np.isfinite(post_action).all()
            and np.isfinite(post_norm)
        ),
    }


def _task037_g2_factor_payload_route(
    trace_inventory: dict[str, Any],
    fullspace_inventory: dict[str, Any],
) -> dict[str, int | float | bool | str]:
    trace_bytes = int(trace_inventory["retained_payload_lower_bound_bytes"])
    fullspace_bytes = int(
        fullspace_inventory["retained_payload_lower_bound_bytes"]
    )
    if trace_bytes <= 0:
        raise ValueError("trace factor retained payload must be positive")
    reduction_fraction = (trace_bytes - fullspace_bytes) / trace_bytes
    gate_pass = bool(reduction_fraction >= 0.25)
    return {
        "trace_retained_payload_lower_bound_bytes": trace_bytes,
        "fullspace_retained_payload_lower_bound_bytes": fullspace_bytes,
        "reduction_fraction": float(reduction_fraction),
        "gate_pass": gate_pass,
        "status": (
            "retained_payload_gate_pass_route_not_closed"
            if gate_pass
            else "close_fullspace_ilu_only_route"
        ),
    }


def _task037_g2_factor_status(
    payload_route: dict[str, Any],
    iter20_measurement: dict[str, Any] | None,
) -> dict[str, Any]:
    if iter20_measurement is None:
        return {
            "status": "missing_iter20",
            "iter20_gate_pass": False,
            "missing_iterations": [20],
        }
    current_measurement = iter20_measurement["current_trace_ilu"]
    full_measurement = iter20_measurement["fullspace_ilu"]
    trace_rhs_measurement = iter20_measurement["trace_rhs"]
    iter20_gate_pass = bool(
        trace_rhs_measurement["finite"]
        and trace_rhs_measurement["trace_rhs_exact"]
        and current_measurement["finite"]
        and full_measurement["finite"]
        and full_measurement["correction_finite"]
        and full_measurement["deterministic"]
    )
    return {
        "status": (
            payload_route["status"]
            if iter20_gate_pass
            else "close_fullspace_ilu_only_route"
        ),
        "iter20_gate_pass": iter20_gate_pass,
        "missing_iterations": [],
    }


def _solve_static_condensed_fgmres_core(
    request: Stage4ExternalLinearSolverRequest
    | Stage4NeverMaterializedLinearSolverRequest,
    *,
    screen_iterations: int,
    local_krylov_steps: Literal[2, 4] = 2,
    residual_observer: Callable[[int, float, float], None] | None = None,
    residual_snapshot_observer: Callable[[int, PETSc.Vec, float, float], None]
    | None = None,
    task037_extra_g0_diagnostics: bool = False,
    task037_extra_g2_slab14_identity: bool = False,
    task037_extra_g2_slab14_factor_inventory: bool = False,
    task037_extra_g2_slab14_lor_transfer: bool = False,
    task037_extra_g2_slab14_lor_hx_oracle: bool = False,
    solver_profile: Literal[
        "assembled",
        "assembled_setup_then_static_local_schur_matrix_free_solve",
        "never_materialized_owner_local",
        "never_materialized_owner_local_overlap0125_partition",
        "never_materialized_p2_auxiliary",
        "never_materialized_p2_factor_free_slab_auxiliary",
        "never_materialized_p2_factor_free_slab_ras_auxiliary",
    ] = "assembled",
    release_assembled_matrix: Callable[[], None] | None = None,
    lifecycle_observer: Callable[[str, dict[str, Any]], None] | None = None,
) -> tuple[Stage4ExternalLinearSolverSnapshot, dict[str, Any]]:
    action_only = isinstance(request, Stage4NeverMaterializedLinearSolverRequest)
    if solver_profile not in (
        "assembled",
        "assembled_setup_then_static_local_schur_matrix_free_solve",
        "never_materialized_owner_local",
        "never_materialized_owner_local_overlap0125_partition",
        "never_materialized_p2_auxiliary",
        "never_materialized_p2_factor_free_slab_auxiliary",
        "never_materialized_p2_factor_free_slab_ras_auxiliary",
    ):
        raise ValueError("unsupported static-condensed FGMRES solver profile")
    exact_profile = (
        solver_profile == "assembled_setup_then_static_local_schur_matrix_free_solve"
    )
    action_only_profile = solver_profile in {
        "never_materialized_owner_local",
        "never_materialized_owner_local_overlap0125_partition",
        "never_materialized_p2_auxiliary",
        "never_materialized_p2_factor_free_slab_auxiliary",
        "never_materialized_p2_factor_free_slab_ras_auxiliary",
    }
    m3a_profile = (
        solver_profile == "never_materialized_owner_local_overlap0125_partition"
    )
    if task037_extra_g0_diagnostics and not m3a_profile:
        raise ValueError("Task037-extra G0 diagnostics require the M3a profile")
    if task037_extra_g2_slab14_identity and (
        not action_only or not m3a_profile
    ):
        raise ValueError(
            "Task037-extra G2 slab14 identity requires the M3a action-only profile"
        )
    if task037_extra_g2_slab14_factor_inventory and not (
        task037_extra_g2_slab14_identity
    ):
        raise ValueError(
            "Task037-extra G2 slab14 factor inventory requires slab14 identity"
        )
    if task037_extra_g2_slab14_factor_inventory and (
        not action_only or not m3a_profile
    ):
        raise ValueError(
            "Task037-extra G2 slab14 factor inventory requires the M3a action-only profile"
        )
    if task037_extra_g2_slab14_lor_transfer and not (
        task037_extra_g2_slab14_identity
    ):
        raise ValueError(
            "Task037-extra G2 slab14 LOR transfer requires slab14 identity"
        )
    if task037_extra_g2_slab14_lor_hx_oracle and not (
        task037_extra_g2_slab14_identity
        and task037_extra_g2_slab14_lor_transfer
    ):
        raise ValueError(
            "Task037-extra G2 slab14 LOR-HX oracle requires identity and LOR transfer"
        )
    if task037_extra_g2_slab14_lor_hx_oracle and (
        task037_extra_g2_slab14_factor_inventory
        or task037_extra_g0_diagnostics
    ):
        raise ValueError(
            "Task037-extra G2 slab14 LOR-HX oracle conflicts with factor inventory and G0"
        )
    if task037_extra_g2_slab14_lor_hx_oracle and (
        not action_only or not m3a_profile
    ):
        raise ValueError(
            "Task037-extra G2 slab14 LOR-HX oracle requires the M3a action-only profile"
        )
    if task037_extra_g2_slab14_identity and task037_extra_g0_diagnostics:
        raise ValueError(
            "Task037-extra G2 slab14 identity conflicts with G0 diagnostics"
        )
    p2_auxiliary_profile = solver_profile in {
        "never_materialized_p2_auxiliary",
        "never_materialized_p2_factor_free_slab_auxiliary",
        "never_materialized_p2_factor_free_slab_ras_auxiliary",
    }
    factor_free_p2_profile = solver_profile in {
        "never_materialized_p2_factor_free_slab_auxiliary",
        "never_materialized_p2_factor_free_slab_ras_auxiliary",
    }
    factor_free_p2_ras_profile = (
        solver_profile == "never_materialized_p2_factor_free_slab_ras_auxiliary"
    )
    if factor_free_p2_ras_profile and local_krylov_steps != 4:
        raise ValueError("RAS factor-free p2 profile requires four local steps")
    if action_only != action_only_profile:
        raise ValueError("solver profile does not match the request type")
    if exact_profile and not action_only and release_assembled_matrix is None:
        raise ValueError(
            "exact F5b profile requires an assembled-matrix release callback"
        )
    if action_only and release_assembled_matrix is not None:
        raise ValueError(
            "never-materialized request cannot release an assembled matrix"
        )
    started = perf_counter()
    request_operator = request.operator if action_only else request.A
    request_rhs = request.b
    request_operator_size = tuple(map(int, request_operator.getSize()))
    request_operator_columns = tuple(
        map(int, request_operator.getOwnershipRangeColumn())
    )
    comm = request_operator.getComm().tompi4py()
    returned_solution_transferred = False
    live_state: dict[str, bool | int] = {
        "borrowed_augmented_A": not action_only,
        "active_F": False,
        "C": False,
        "D": False,
        "H": False,
        "borrowed_augmented_rhs": True,
        "extracted_active_rhs": False,
        "extracted_aux_rhs": False,
        "condensed_active_rhs": False,
        "borrowed_retained_local_schur": False,
        "fine_action": False,
        "matrix_free_operator": False,
        "basis": False,
        "shifted_action": False,
        "shift": False,
        "slab_submatrices": 0,
        "slab_factors": 0,
        "coarse": False,
        "solution": False,
        "monitor_solution": False,
        "residual_work": False,
        "outer_ksp": False,
        "outer_pc": False,
        "recovered_auxiliary": False,
        "augmented_solution": False,
        "returned_augmented_solution": False,
    }
    if lifecycle_observer is not None:
        live_state["borrowed_retained_local_schur"] = (
            request.static_condensed_system.retained_local_schur_by_class is not None
        )

    def emit_lifecycle(event: str, **payload: Any) -> None:
        if lifecycle_observer is not None:
            payload["rank_local_live_objects"] = dict(live_state)
            lifecycle_observer(
                event,
                {
                    "rank_local_rank": int(comm.rank),
                    "rank_count": int(comm.size),
                    **payload,
                },
            )

    def smoother_setup_observer(event: str, payload: dict[str, Any]) -> None:
        if event == "first_owned_slab_submatrix_allocated":
            live_state["slab_submatrices"] = int(
                bool(payload["rank_local_has_first_submatrix"])
            )
        elif event == "first_owned_slab_factor_ready":
            live_state["slab_submatrices"] = 0
            live_state["slab_factors"] = int(
                bool(payload["rank_local_has_first_factor"])
            )
        elif event == "all_slab_factors_ready":
            live_state["slab_submatrices"] = 0
            live_state["slab_factors"] = int(payload["rank_local_factor_count"])
        emit_lifecycle(event, **payload)

    owned: list[Any] = []
    g0_residual_snapshots: dict[int, PETSc.Vec] = {}
    g2_identity_state: dict[str, Any] | None = None
    g2_factor_state: dict[str, Any] | None = None
    g2_lor_transfer_audit: dict[str, Any] | None = None
    g2_lor_hx_audit: dict[str, Any] | None = None
    lor_hx_oracle = None
    try:
        if action_only:
            blocks = request.blocks
            if blocks.F is not None:
                raise ValueError(
                    "never-materialized request must provide blocks.F=None"
                )
            fine = request.fine_operator
            matrix_blocks = {"C": blocks.C, "D": blocks.D, "H": blocks.H}
        else:
            blocks = extract_petsc_condensed_blocks(
                request.A, request.b, n_fe=request.n_fe, n_aux=request.n_aux
            )
            owned.append(blocks)
            fine = blocks.require_f()
            matrix_blocks = {
                "F": fine,
                "C": blocks.C,
                "D": blocks.D,
                "H": blocks.H,
            }
        live_state.update(
            active_F=not action_only,
            C=True,
            D=True,
            H=True,
            extracted_active_rhs=not action_only,
            extracted_aux_rhs=not action_only,
        )
        emit_lifecycle(
            "F_C_D_H_extracted",
            blocks_source=("borrowed_action_only" if action_only else "extracted"),
            borrowed_A_already_finalized_at_port_entry=not action_only,
            global_active_rows=int(blocks.n_fe),
            global_aux_rows=int(blocks.n_aux),
            global_augmented_rows=request_operator_size[0],
            global_A_materialized=not action_only,
            global_F_materialized=not action_only,
            global_matrix_shapes={
                name: [int(matrix.getSize()[0]), int(matrix.getSize()[1])]
                for name, matrix in matrix_blocks.items()
            },
            rank_local_matrix_nnz_used={
                name: int(matrix.getInfo(PETSc.Mat.InfoType.LOCAL)["nz_used"])
                for name, matrix in matrix_blocks.items()
            },
        )
        rhs = condensed_rhs(blocks)
        owned.append(rhs)
        live_state["condensed_active_rhs"] = True
        emit_lifecycle(
            "condensed_active_rhs_ready",
            global_condensed_rhs_size=int(rhs.getSize()),
        )
        fine_action = fine
        fine_action_error = None
        if exact_profile and not action_only:
            fine_action, _ = create_static_local_schur_action(
                request.static_condensed_system, fine
            )
            owned.append(fine_action)
            probe = fine.createVecRight()
            owned.append(probe)
            start, end = map(int, fine.getOwnershipRange())
            probe.getArray()[:] = np.asarray(
                [1.0 + 0.1 * row + 0.2j * (row + 1) for row in range(start, end)],
                dtype=PETSc.ScalarType,
            )
            fine_action_error = relative_action_error(fine, fine_action, probe)
            probe.destroy()
            owned.remove(probe)
            if fine_action_error > 1.0e-11:
                raise ValueError(
                    "retained local Schur action failed the fine-action gate"
                )
        retained_schur_class_count = 0
        retained_schur_bytes = 0
        if lifecycle_observer is not None:
            retained_schurs = (
                request.static_condensed_system.retained_local_schur_by_class
            )
            if retained_schurs is None:
                retained_schur_class_count = 0
                retained_schur_bytes = 0
            else:
                retained_schur_class_count = len(retained_schurs)
                retained_schur_bytes = sum(
                    int(np.asarray(value).nbytes) for value in retained_schurs.values()
                )
            summed_rank_local_retained_schur_class_count = int(
                comm.allreduce(retained_schur_class_count, op=MPI.SUM)
            )
            summed_rank_local_retained_schur_bytes = int(
                comm.allreduce(retained_schur_bytes, op=MPI.SUM)
            )
        else:
            summed_rank_local_retained_schur_class_count = None
            summed_rank_local_retained_schur_bytes = None
        live_state.update(
            fine_action=True,
        )
        emit_lifecycle(
            "local_schur_action_ready",
            fine_action_relative_error=fine_action_error,
            rank_local_retained_schur_class_count=retained_schur_class_count,
            rank_local_retained_schur_bytes=retained_schur_bytes,
            summed_rank_local_retained_schur_class_count=(
                summed_rank_local_retained_schur_class_count
            ),
            summed_rank_local_retained_schur_bytes=summed_rank_local_retained_schur_bytes,
        )
        operator, operator_context = create_matrix_free_condensed_operator(
            blocks, fine_operator=fine_action
        )
        owned.append(operator)
        live_state["matrix_free_operator"] = True
        basis = build_active_trace_floquet_basis(
            request.static_condensed_system,
            request.function_space,
            request.config,
            request.floquet_data,
            fine_action,
        )
        live_state["basis"] = True
        emit_lifecycle(
            "basis_ready",
            global_basis_dimension=len(basis),
        )
        p2_auxiliary_audit = None
        if p2_auxiliary_profile:
            if request.mesh_data is None:
                raise ValueError("p2 auxiliary profile requires borrowed mesh_data")
            p2_smoother, p2_transfer, p2_diagonal, p2_auxiliary_audit = (
                build_p2_auxiliary_setup(
                    fine_space=request.function_space,
                    fine_condensed=request.static_condensed_system,
                    fine_operator=operator,
                    fine_blocks=blocks,
                    mesh_data=request.mesh_data,
                    config=request.config,
                    fine_schur_action=(fine_action if factor_free_p2_profile else None),
                    local_krylov_steps=local_krylov_steps,
                    optimized_schwarz=factor_free_p2_ras_profile,
                )
            )
            owned.extend((p2_transfer, p2_diagonal, p2_smoother))
            smoother = p2_smoother
            if factor_free_p2_profile:
                patch_audit = p2_auxiliary_audit["factor_free_slab_patch"]
                partition_audit = {
                    "p6_slab_matrix_materialized": patch_audit[
                        "p6_slab_matrix_materialized"
                    ],
                    "p6_slab_matrix_count": patch_audit["p6_slab_matrix_count"],
                    "p6_factor_count": patch_audit["p6_factor_count"],
                    "local_krylov_steps": patch_audit["local_krylov_steps"],
                    "local_inner_preconditioner": patch_audit[
                        "local_inner_preconditioner"
                    ],
                    "outer_requires_fgmres": patch_audit["outer_requires_fgmres"],
                    "p6_factor_nnz": patch_audit["p6_factor_nnz"],
                    "global_A_materialized_by_pc": patch_audit[
                        "global_A_materialized_by_pc"
                    ],
                    "num_slabs": patch_audit["num_slabs"],
                    "overlap_fraction": patch_audit["overlap_fraction"],
                    "interpolation": patch_audit["interpolation"],
                    "partition_weight_sum_error": patch_audit[
                        "partition_weight_sum_error"
                    ],
                    "partition_weight_min": patch_audit["partition_weight_min"],
                    "partition_weight_max": patch_audit["partition_weight_max"],
                }
                if factor_free_p2_ras_profile:
                    partition_audit.update(
                        {
                            "variant": patch_audit["variant"],
                            "correction_partition": patch_audit["correction_partition"],
                            "ras_core_sum_error": patch_audit["ras_core_sum_error"],
                            "interface_row_count": patch_audit["interface_row_count"],
                            "interface_shift_mode": patch_audit["interface_shift_mode"],
                            "interface_shift_nonzero_rows": patch_audit[
                                "interface_shift_nonzero_rows"
                            ],
                            "noninterface_shift_nonzero_rows": patch_audit[
                                "noninterface_shift_nonzero_rows"
                            ],
                        }
                    )
            else:
                partition_audit = {
                    "p6_slab_matrix_materialized": False,
                    "p6_slab_matrix_count": 0,
                    "p6_factor_count": 0,
                }
        elif action_only:
            owner_plan = build_owner_local_slab_plan(
                request.static_condensed_system,
                request.function_space.mesh,
                domain_z=(request.config.domain_z_min, request.config.domain_z_max),
                num_slabs=16,
                overlap_fraction=0.125 if m3a_profile else 0.25,
            )
            partition_audit = {
                "matrix_materialized": False,
                "coverage_pass": True,
                "num_slabs": len(owner_plan.slab_owners),
                "slab_row_counts": list(owner_plan.slab_row_counts),
                "subdomain_owners": list(owner_plan.slab_owners),
            }
            if m3a_profile:
                partition_audit.update(
                    {
                        "overlap_fraction": 0.125,
                        "interpolation": "partition",
                    }
                )
            diagonal, diagonal_audit = build_owner_local_slab_diagonal(
                request.static_condensed_system
            )
            owned.append(diagonal)
            global_scale = float(diagonal_audit["global_diagonal_max_abs"])
            shift = diagonal
            absolute = np.abs(shift.getArray(readonly=True))
            shift.getArray()[:] = (
                -1j * 0.1 * np.maximum(absolute, 1.0e-12 * global_scale)
            )
        else:
            subdomains, partition_audit = build_trace_aware_physical_slab_partition(
                request.static_condensed_system,
                request.function_space.mesh,
                domain_z=(request.config.domain_z_min, request.config.domain_z_max),
                num_slabs=16,
                overlap_fraction=0.25,
            )
            diagonal = fine.createVecLeft()
            owned.append(diagonal)
            fine.getDiagonal(diagonal)
            absolute = np.abs(diagonal.getArray(readonly=True))
            comm = fine.getComm().tompi4py()
            global_scale = float(
                comm.allreduce(float(absolute.max(initial=0.0)), op=MPI.MAX)
            )
            shift = diagonal.duplicate()
            owned.append(shift)
            shift.getArray()[:] = (
                -1j * 0.1 * np.maximum(absolute, 1.0e-12 * global_scale)
            )
            diagonal.destroy()
            owned.remove(diagonal)
        if task037_extra_g2_slab14_identity:
            slab = _TASK037_G2_SLAB
            g2_cells, collector_audit = collect_owner_local_fullspace_slab_cells(
                request.static_condensed_system,
                owner_plan,
                request.function_space.mesh,
                slab,
            )
            slab_owner = int(owner_plan.slab_owners[slab])
            owner_rows = np.asarray(
                owner_plan.owner_rows[slab],
                dtype=PETSc.IntType,
            )
            local_shift, shift_route_audit = extract_owner_local_slab_vector(
                shift,
                owner_plan,
                slab,
            )
            deterministic_measurement = None
            shift_identity = None
            if comm.rank == slab_owner:
                assert local_shift is not None
                deterministic_vectors = _task037_g2_deterministic_vectors(owner_rows)
                deterministic_measurement = measure_fullspace_slab_identity(
                    g2_cells,
                    deterministic_vectors,
                    active_size=int(owner_rows.size),
                    trace_shift=local_shift,
                )
                shift_identity = {
                    "count": int(local_shift.size),
                    "owner_row_count": int(owner_rows.size),
                    "local_shift_norm2": float(np.linalg.norm(local_shift)),
                    "nonzero_count": int(np.count_nonzero(local_shift)),
                    "finite": bool(np.isfinite(local_shift).all()),
                    "sha256": _task037_g2_owner_vector_sha256(
                        owner_rows,
                        local_shift,
                        domain="task037.g2.current-local-shift.v1",
                    ),
                    "route": shift_route_audit,
                }
            deterministic_measurement = comm.bcast(
                deterministic_measurement,
                root=slab_owner,
            )
            shift_identity = comm.bcast(shift_identity, root=slab_owner)
            g2_setup_audit = {
                "primary_selection_basis": {
                    "primary_slab": slab,
                    "control_slab": 5,
                    "ablation_comparator_slab": 13,
                    "basis": (
                        "G0 frozen primary: largest iter20 local residual; "
                        "slab5 is lower-median control; slab13 is the "
                        "largest-positive-ablation comparator"
                    ),
                },
                "materialization": {
                    "condensed_trace_matrix_materialized": bool(
                        request.static_condensed_system.matrix is not None
                    ),
                    "action_only_request": bool(action_only),
                    "blocks_F_present": bool(blocks.F is not None),
                },
                "collector": dict(collector_audit),
                "current_local_shift": shift_identity,
                "deterministic_vectors": {
                    "labels": list(_TASK037_G2_DETERMINISTIC_VECTOR_LABELS),
                    "count": 3,
                    "measurement": deterministic_measurement,
                    "gate_pass": bool(
                        deterministic_measurement["finite"]
                        and deterministic_measurement["deterministic"]
                        and deterministic_measurement["max_relative_error"]
                        <= _TASK037_G2_IDENTITY_TOLERANCE
                    ),
                },
                "iter20_real_residual": None,
                "relative_error_tolerance": _TASK037_G2_IDENTITY_TOLERANCE,
                "missing_iterations": [20],
                "gate_pass": False,
                "status": "pending_iter20",
            }
            g2_identity_state = {
                "cells": g2_cells,
                "owner": slab_owner,
                "owner_rows": owner_rows,
                "owner_rows_size": int(owner_rows.size),
                "shift": local_shift,
                "audit": g2_setup_audit,
            }
        if task037_extra_g2_slab14_lor_transfer:
            assert g2_identity_state is not None
            if request.mesh_data is None:
                raise RuntimeError(
                    "Task037-extra G2 slab14 LOR transfer requires mesh data"
                )
            floquet_topology = request.floquet_data.phase_independent_topology
            if floquet_topology is None:
                raise RuntimeError(
                    "Task037-extra G2 slab14 LOR transfer requires "
                    "phase-independent Floquet topology"
                )
            slab = _TASK037_G2_SLAB
            slab_owner = int(g2_identity_state["owner"])
            emit_lifecycle(
                "g2_lor_transfer_build_started",
                slab=slab,
                owner_rank=slab_owner,
            )
            lor_started = perf_counter()
            lor_transfer, lor_topologies, lor_audit = collect_owner_local_lor_transfer(
                request.static_condensed_system,
                owner_plan,
                request.function_space.mesh,
                request.mesh_data.cell_tags,
                slab,
                degree=int(request.config.nedelec_trace_degree_resolved),
                floquet_topology=floquet_topology,
                phase_x=request.floquet_data.phase_x,
                phase_y=request.floquet_data.phase_y,
                coordinate_tolerance=floquet_geometry_tolerance(
                    request.config
                ),
                retain_parent_topologies=task037_extra_g2_slab14_lor_hx_oracle,
            )
            lor_build_seconds = comm.allreduce(
                float(perf_counter() - lor_started),
                op=MPI.MAX,
            )
            lor_measurement = None
            if comm.rank == slab_owner:
                assert lor_transfer is not None
                active_count = int(lor_audit["active_edge_count"])
                active_indices = np.arange(active_count, dtype=np.float64)
                deterministic_vectors = _task037_g2_deterministic_vectors(
                    active_indices
                )
                output_hashes = []
                deterministic = True
                finite = True
                apply_count = 0
                for vector in deterministic_vectors:
                    first = lor_transfer.apply(vector)
                    second = lor_transfer.apply(vector)
                    apply_count += 2
                    deterministic = deterministic and bool(
                        np.array_equal(first, second)
                    )
                    finite = finite and bool(
                        np.isfinite(first).all() and np.isfinite(second).all()
                    )
                    output_hashes.append(
                        _task037_g2_lor_vector_sha256(
                            first,
                            domain="task037.g2.lor-transfer.full-output.v1",
                        )
                    )
                full_probe = np.asarray(
                    1.0 + 0.125j * np.arange(
                        int(lor_audit["full_rows"]),
                        dtype=np.float64,
                    ),
                    dtype=np.complex128,
                )
                active_probe = deterministic_vectors[0]
                full_output = lor_transfer.apply(active_probe)
                adjoint_output = lor_transfer.apply_adjoint(full_probe)
                left = np.vdot(full_output, full_probe)
                right = np.vdot(active_probe, adjoint_output)
                adjoint_error = float(
                    abs(left - right) / max(abs(left), abs(right), 1.0)
                )
                lor_measurement = {
                    "vector_count": len(deterministic_vectors),
                    "forward_apply_count": apply_count + 1,
                    "adjoint_apply_count": 1,
                    "deterministic": bool(deterministic),
                    "finite": bool(
                        finite
                        and np.isfinite(full_probe).all()
                        and np.isfinite(adjoint_output).all()
                        and np.isfinite(adjoint_error)
                    ),
                    "output_sha256": output_hashes,
                    "adjoint_relative_error": adjoint_error,
                }
            lor_measurement = comm.bcast(lor_measurement, root=slab_owner)
            g2_lor_transfer_audit = dict(lor_audit)
            g2_lor_transfer_audit.update(
                {
                    "primary_slab": slab,
                    "build_seconds": float(lor_build_seconds),
                    "measurement": lor_measurement,
                    "gate_pass": bool(
                        lor_measurement["finite"]
                        and lor_measurement["deterministic"]
                        and lor_measurement["adjoint_relative_error"]
                        <= _TASK037_G2_LOR_TOLERANCE
                        and lor_audit["missing_writer_count"] == 0
                        and lor_audit["shared_trace_max_relative_error"]
                        <= _TASK037_G2_LOR_TOLERANCE
                        and lor_audit[
                            "complete_trace_reconstruction_max_relative_error"
                        ]
                        <= _TASK037_G2_LOR_TOLERANCE
                        and lor_audit["global_dense_T_retained"] is False
                        and lor_audit["matched_identity_block_count"] > 0
                        and lor_audit["periodic_slave_edge_count"] > 0
                        and lor_audit["active_edge_count"]
                        + lor_audit["periodic_slave_edge_count"]
                        == lor_audit["physical_edge_count"]
                        and lor_audit["periodic_relation_count"]
                        == lor_audit["periodic_slave_edge_count"]
                    ),
                }
            )
            g2_lor_transfer_audit["status"] = (
                "pass"
                if g2_lor_transfer_audit["gate_pass"]
                else "lor_transfer_gate_failed"
            )
            emit_lifecycle(
                "g2_lor_transfer_build_ready",
                slab=slab,
                owner_rank=slab_owner,
                parent_count=int(g2_lor_transfer_audit["parent_count"]),
                full_rows=int(g2_lor_transfer_audit["full_rows"]),
                retained_numeric_payload_lower_bound_bytes=int(
                    g2_lor_transfer_audit[
                        "retained_numeric_payload_lower_bound_bytes"
                    ]
                ),
                build_seconds=float(lor_build_seconds),
            )
            if task037_extra_g2_slab14_lor_hx_oracle:
                if g2_lor_transfer_audit["gate_pass"] is not True:
                    raise RuntimeError(
                        "LOR-HX oracle requires a passing LOR transfer audit"
                    )
                owner_prerequisite_error = None
                if comm.rank == slab_owner:
                    if lor_transfer is None or lor_topologies is None:
                        owner_prerequisite_error = (
                            "LOR-HX oracle requires owner transfer and parent topologies"
                        )
                owner_prerequisite_error = comm.bcast(
                    owner_prerequisite_error,
                    root=slab_owner,
                )
                if owner_prerequisite_error is not None:
                    raise RuntimeError(owner_prerequisite_error)
                emit_lifecycle(
                    "g2_lor_hx_build_started",
                    slab=slab,
                    owner_rank=slab_owner,
                )
                hx_started = perf_counter()
                builder_error = None
                if comm.rank == slab_owner:
                    try:
                        lor_hx_oracle = build_physical_lor_hcurl_slab_oracle(
                            lor_transfer,
                            lor_topologies,
                            request.config,
                        )
                        local_hx_audit = dict(lor_hx_oracle.audit)
                    except (
                        ValueError,
                        NotImplementedError,
                        RuntimeError,
                    ) as error:
                        builder_error = f"{type(error).__name__}: {error}"
                else:
                    local_hx_audit = None
                builder_error = comm.bcast(builder_error, root=slab_owner)
                if builder_error is not None:
                    raise RuntimeError(builder_error)
                hx_build_seconds = comm.allreduce(
                    float(perf_counter() - hx_started),
                    op=MPI.MAX,
                )
                hx_audit = comm.bcast(local_hx_audit, root=slab_owner)
                transfer_payload = int(
                    g2_lor_transfer_audit[
                        "retained_numeric_payload_lower_bound_bytes"
                    ]
                )
                d2c_payload = int(
                    hx_audit[
                        "d2c_retained_numeric_payload_lower_bound_bytes"
                    ]
                )
                total_payload = int(
                    hx_audit["retained_numeric_payload_lower_bound_bytes"]
                )
                allowed_tags = {
                    int(request.config.tags.air),
                    int(request.config.tags.substrate),
                    int(request.config.tags.grating),
                }
                present_tags = hx_audit.get("present_material_tags", ())
                mass_coefficients = hx_audit.get(
                    "mass_coefficient_by_tag", {}
                )
                coefficient_gate = (
                    isinstance(present_tags, list)
                    and bool(present_tags)
                    and all(int(tag) in allowed_tags for tag in present_tags)
                    and isinstance(mass_coefficients, dict)
                    and set(mass_coefficients) == {
                        str(int(tag)) for tag in present_tags
                    }
                    and isinstance(hx_audit.get("curl_coefficient"), list)
                    and len(hx_audit["curl_coefficient"]) == 2
                    and all(
                        np.isfinite(float(value))
                        for value in hx_audit["curl_coefficient"]
                    )
                    and all(
                        isinstance(value, list)
                        and len(value) == 2
                        and all(np.isfinite(float(item)) for item in value)
                        for value in mass_coefficients.values()
                    )
                )
                row_gate = (
                    hx_audit.get("full_rows")
                    == hx_audit.get("interior_rows")
                    + hx_audit.get("trace_rows")
                    and hx_audit.get("trace_rows")
                    == g2_lor_transfer_audit.get("trace_rows")
                    == g2_lor_transfer_audit.get("owner_active_row_count")
                    and hx_audit.get("active_lor_rows")
                    == g2_lor_transfer_audit.get("active_edge_count")
                )
                storage_gate = (
                    hx_audit.get("volume_proxy_only") is True
                    and hx_audit.get("dtn_surface_in_proxy") is False
                    and hx_audit.get("literal_p6_shift_galerkin") is False
                    and total_payload
                    == transfer_payload + d2c_payload
                    and total_payload > 0
                    and hx_audit.get("factor_count") == 2
                    and hx_audit.get("coarsest_factor_count") == 2
                    and hx_audit.get("fine_p6_trace_factor_count") == 0
                    and hx_audit.get("fine_p6_full_factor_count") == 0
                    and hx_audit.get("large_lor_factor_count") == 0
                    and hx_audit.get("fine_intermediate_factor_count") == 0
                    and hx_audit.get("coarsest_only") is True
                    and hx_audit.get("parent_topologies_retained") is False
                    and hx_audit.get("persistent_full_rhs") is False
                    and hx_audit.get("persistent_lor_rhs") is False
                    and hx_audit.get("global_dense") is False
                    and hx_audit.get("exact_outer_changed") is False
                    and hx_audit.get("contraction_not_evaluated") is True
                )
                g2_lor_hx_audit = {
                    **hx_audit,
                    "primary_slab": slab,
                    "owner": slab_owner,
                    "build_seconds": float(hx_build_seconds),
                    "transfer_identity": {
                        "parent_id_hash": g2_lor_transfer_audit[
                            "parent_id_hash"
                        ],
                        "physical_edge_keys_sha256": g2_lor_transfer_audit[
                            "physical_edge_keys_sha256"
                        ],
                        "active_edge_keys_sha256": g2_lor_transfer_audit[
                            "active_edge_keys_sha256"
                        ],
                        "parent_count": g2_lor_transfer_audit[
                            "parent_count"
                        ],
                        "active_edge_count": g2_lor_transfer_audit[
                            "active_edge_count"
                        ],
                    },
                    "transfer_retained_numeric_payload_lower_bound_bytes": (
                        transfer_payload
                    ),
                    "d2c_retained_numeric_payload_lower_bound_bytes": (
                        d2c_payload
                    ),
                    "retained_numeric_payload_lower_bound_bytes": total_payload,
                    "gate_checks": {
                        "rows": bool(row_gate),
                        "coefficients": bool(coefficient_gate),
                        "storage": bool(storage_gate),
                    },
                }
                g2_lor_hx_audit["gate_pass"] = bool(
                    row_gate and coefficient_gate and storage_gate
                )
                g2_lor_hx_audit["status"] = (
                    "pass_build_only"
                    if g2_lor_hx_audit["gate_pass"]
                    else "build_gate_failed"
                )
                emit_lifecycle(
                    "g2_lor_hx_build_ready",
                    slab=slab,
                    owner_rank=slab_owner,
                    full_rows=int(hx_audit["full_rows"]),
                    retained_numeric_payload_lower_bound_bytes=total_payload,
                    factor_count=int(hx_audit["factor_count"]),
                    build_seconds=float(hx_build_seconds),
                )
                del lor_topologies
        if not p2_auxiliary_profile:
            live_state["shift"] = True
            shifted_context = _ShiftedFineAction(fine_action, shift)
            shifted_fine = PETSc.Mat().createPython(
                fine_action.getSizes(),
                context=shifted_context,
                comm=fine_action.getComm(),
            )
            owned.append(shifted_fine)
            owned.remove(shift)
            shifted_fine.setUp()
            live_state["shifted_action"] = True
            if action_only:
                smoother = DistributedPhysicalSlabSmoother.from_owner_local_plan(
                    request.static_condensed_system,
                    owner_plan,
                    ilu_levels=0,
                    interpolation=("partition" if m3a_profile else "basic"),
                    precomputed_diagonal_shift=shift,
                    two_step_action_operator=shifted_fine,
                    progress=None,
                    setup_observer=(
                        smoother_setup_observer
                        if lifecycle_observer is not None
                        else None
                    ),
                )
            else:
                smoother = DistributedPhysicalSlabSmoother(
                    fine,
                    subdomains,
                    ilu_levels=0,
                    local_ksp_iterations=1,
                    local_ksp_type="gmres",
                    smoother_iterations=2,
                    smoother_ksp_type="gmres",
                    action_operator=shifted_fine,
                    diagonal_shift=shift,
                    factor_only_storage=True,
                    interpolation="basic",
                    assembly_order="two_color",
                    setup_observer=(
                        smoother_setup_observer
                        if lifecycle_observer is not None
                        else None
                    ),
                )
            owned.append(smoother)
            if m3a_profile:
                smoother_setup = smoother.diagnostics
                partition_audit.update(
                    {
                        "partition_weight_sum_error": smoother_setup[
                            "partition_weight_sum_error"
                        ],
                        "partition_weight_min": smoother_setup["partition_weight_min"],
                        "partition_weight_max": smoother_setup["partition_weight_max"],
                    }
                )
        if task037_extra_g2_slab14_factor_inventory:
            from .static_fullspace_slab_factor_oracle import (
                FullSpaceSlabFactorOracle,
                assemble_fullspace_slab_matrix,
            )

            assert g2_identity_state is not None
            slab = _TASK037_G2_SLAB
            slab_owner = int(g2_identity_state["owner"])
            emit_lifecycle(
                "g2_fullspace_matrix_assembly_started",
                slab=slab,
                owner_rank=slab_owner,
            )
            fullspace_matrix = None
            matrix_audit = None
            if comm.rank == slab_owner:
                matrix_started = perf_counter()
                fullspace_matrix, matrix_audit = assemble_fullspace_slab_matrix(
                    g2_identity_state["cells"],
                    active_size=int(g2_identity_state["owner_rows_size"]),
                    trace_shift=g2_identity_state["shift"],
                )
                matrix_audit["matrix_assembly_seconds"] = float(
                    perf_counter() - matrix_started
                )
            matrix_audit = comm.bcast(matrix_audit, root=slab_owner)
            emit_lifecycle(
                "g2_fullspace_matrix_assembly_ready",
                slab=slab,
                owner_rank=slab_owner,
                full_rows=int(matrix_audit["full_rows"]),
                matrix_nnz=int(matrix_audit["matrix_nnz"]),
            )
            emit_lifecycle(
                "g2_fullspace_factor_setup_started",
                slab=slab,
                owner_rank=slab_owner,
            )
            factor_oracle = None
            setup_inventory = None
            if comm.rank == slab_owner:
                assert fullspace_matrix is not None
                factor_oracle = FullSpaceSlabFactorOracle(
                    fullspace_matrix,
                    matrix_audit,
                    solver="ilu",
                )
                owned.append(factor_oracle)
                setup_inventory = factor_oracle.inventory
            setup_inventory = comm.bcast(setup_inventory, root=slab_owner)
            emit_lifecycle(
                "g2_fullspace_factor_setup_ready",
                slab=slab,
                owner_rank=slab_owner,
                full_rows=int(setup_inventory["full_rows"]),
                factor_nnz=int(setup_inventory["factor_nnz"]),
                retained_payload_lower_bound_bytes=int(
                    setup_inventory["retained_payload_lower_bound_bytes"]
                ),
            )
            g2_factor_state = {
                "oracle": factor_oracle,
                "owner": slab_owner,
                "setup_inventory": setup_inventory,
                "matrix_audit": matrix_audit,
                "iter20": None,
            }
        live_state["slab_factors"] = (
            0 if p2_auxiliary_profile else len(smoother.local_subdomains)
        )
        coarse = SparseGalerkinTwoLevelPc(
            operator,
            smoother,
            basis,
            post_smooth=not p2_auxiliary_profile,
        )
        owned.append(coarse)
        live_state["coarse"] = True
        emit_lifecycle(
            "coarse_operator_ready",
            global_coarse_dimension=len(basis),
        )
        assembled_matrix_released = False
        if exact_profile and not action_only:
            blocks.release_f()
            live_state["active_F"] = False
            emit_lifecycle(
                "F_released",
            )
            release_assembled_matrix()
            assembled_matrix_released = True
            live_state["borrowed_augmented_A"] = False
            emit_lifecycle(
                "A_released",
            )
        solution = operator.createVecRight()
        monitor_solution = operator.createVecRight()
        residual_work = operator.createVecLeft()
        owned.extend((solution, monitor_solution, residual_work))
        live_state.update(solution=True, monitor_solution=True, residual_work=True)
        solution.set(0.0)
        rhs_norm = float(rhs.norm())
        reported_history: list[tuple[int, float]] = []
        condensed_samples: list[tuple[int, float]] = []
        sampled_iterations = {0}
        initial_condensed = _relative_residual(
            operator, rhs, solution, residual_work, rhs_norm
        )
        reported_history.append((0, 1.0))
        condensed_samples.append((0, initial_condensed))
        if residual_observer is not None:
            residual_observer(0, 1.0, initial_condensed)

        def emit_residual_snapshot(
            iteration: int,
            reported_value: float,
            true_value: float,
        ) -> None:
            if (
                task037_extra_g0_diagnostics
                and iteration in (0, 20)
                and iteration not in g0_residual_snapshots
            ):
                g0_residual_snapshots[int(iteration)] = residual_work.copy()
                owned.append(g0_residual_snapshots[int(iteration)])
            if (
                g2_identity_state is not None
                and int(iteration) == 20
                and g2_identity_state["audit"]["iter20_real_residual"] is None
            ):
                owner = int(g2_identity_state["owner"])
                residual_local, residual_route_audit = (
                    extract_owner_local_slab_vector(
                        residual_work,
                        owner_plan,
                        _TASK037_G2_SLAB,
                    )
                )
                trace_rhs = None
                current_trace_correction = None
                if task037_extra_g2_slab14_factor_inventory:
                    trace_rhs, current_trace_correction = (
                        smoother._diagnostic_owner_local_ilu(
                            residual_work,
                            _TASK037_G2_SLAB,
                        )
                    )
                residual_measurement = None
                residual_identity = None
                factor_measurement = None
                if comm.rank == owner:
                    assert residual_local is not None
                    residual_measurement = measure_fullspace_slab_identity(
                        g2_identity_state["cells"],
                        (residual_local,),
                        active_size=int(g2_identity_state["owner_rows_size"]),
                        trace_shift=g2_identity_state["shift"],
                    )
                    residual_identity = {
                        "owner_row_count": int(residual_local.size),
                        "local_residual_norm2": float(
                            np.linalg.norm(residual_local)
                        ),
                        "sha256": _task037_g2_owner_vector_sha256(
                            g2_identity_state["owner_rows"],
                            residual_local,
                            domain="task037.g2.iter20-real-residual.v1",
                        ),
                    }
                    if task037_extra_g2_slab14_factor_inventory:
                        assert g2_factor_state is not None
                        assert trace_rhs is not None
                        assert current_trace_correction is not None
                        factor_oracle = g2_factor_state["oracle"]
                        assert factor_oracle is not None
                        trace_rhs_difference = trace_rhs - residual_local
                        trace_rhs_relative_error = float(
                            np.linalg.norm(trace_rhs_difference)
                            / np.linalg.norm(residual_local)
                        )
                        current_action = apply_fullspace_slab_schur_action(
                            g2_identity_state["cells"],
                            current_trace_correction,
                            active_size=int(g2_identity_state["owner_rows_size"]),
                            trace_shift=g2_identity_state["shift"],
                        )
                        full_first = factor_oracle.apply_trace_rhs(residual_local)
                        full_second = factor_oracle.apply_trace_rhs(residual_local)
                        full_action = apply_fullspace_slab_schur_action(
                            g2_identity_state["cells"],
                            full_first,
                            active_size=int(g2_identity_state["owner_rows_size"]),
                            trace_shift=g2_identity_state["shift"],
                        )
                        current_contraction = _task037_g2_local_schur_contraction(
                            residual_local,
                            residual_local - current_action,
                        )
                        full_contraction = _task037_g2_local_schur_contraction(
                            residual_local,
                            residual_local - full_action,
                        )
                        factor_measurement = {
                            "trace_rhs": {
                                "owner_row_count": int(trace_rhs.size),
                                "norm2": float(np.linalg.norm(trace_rhs)),
                                "finite": bool(np.isfinite(trace_rhs).all()),
                                "sha256": _task037_g2_owner_vector_sha256(
                                    g2_identity_state["owner_rows"],
                                    trace_rhs,
                                    domain="task037.g2.iter20-factor-trace-rhs.v1",
                                ),
                                "trace_rhs_vs_extracted_relative_error": (
                                    trace_rhs_relative_error
                                ),
                                "trace_rhs_exact": bool(
                                    np.array_equal(trace_rhs, residual_local)
                                ),
                            },
                            "current_trace_ilu": {
                                **current_contraction,
                                "correction_norm2": float(
                                    np.linalg.norm(current_trace_correction)
                                ),
                                "correction_sha256": _task037_g2_owner_vector_sha256(
                                    g2_identity_state["owner_rows"],
                                    current_trace_correction,
                                    domain="task037.g2.iter20-current-trace-ilu-correction.v1",
                                ),
                            },
                            "fullspace_ilu": {
                                **full_contraction,
                                "correction_norm2": float(np.linalg.norm(full_first)),
                                "correction_sha256": _task037_g2_owner_vector_sha256(
                                    g2_identity_state["owner_rows"],
                                    full_first,
                                    domain="task037.g2.iter20-fullspace-ilu-correction.v1",
                                ),
                                "deterministic": bool(
                                    np.array_equal(full_first, full_second)
                                ),
                                "correction_finite": bool(
                                    np.isfinite(full_first).all()
                                    and np.isfinite(full_second).all()
                                ),
                                "apply_count": 2,
                                "apply_seconds": float(
                                    factor_oracle.inventory["apply_seconds"]
                                ),
                            },
                            "contraction_comparison": {
                                "full_minus_trace_rho": float(
                                    full_contraction["rho"]
                                    - current_contraction["rho"]
                                ),
                                "full_to_trace_rho_ratio": float(
                                    full_contraction["rho"]
                                    / current_contraction["rho"]
                                ),
                            },
                        }
                residual_measurement = comm.bcast(
                    residual_measurement,
                    root=owner,
                )
                residual_identity = comm.bcast(residual_identity, root=owner)
                if task037_extra_g2_slab14_factor_inventory:
                    factor_measurement = comm.bcast(
                        factor_measurement,
                        root=owner,
                    )
                    assert g2_factor_state is not None
                    g2_factor_state["iter20"] = factor_measurement
                residual_audit = {
                    "iteration": 20,
                    "true_relative_residual": float(true_value),
                    "source": "core_residual_work_b_minus_Ax",
                    "route": residual_route_audit,
                    **residual_identity,
                    "measurement": residual_measurement,
                    "finite": bool(residual_measurement["finite"]),
                    "deterministic": bool(
                        residual_measurement["deterministic"]
                    ),
                    "max_relative_error": float(
                        residual_measurement["max_relative_error"]
                    ),
                    "gate_pass": bool(
                        residual_measurement["finite"]
                        and residual_measurement["deterministic"]
                        and residual_measurement["max_relative_error"]
                        <= _TASK037_G2_IDENTITY_TOLERANCE
                    ),
                }
                if task037_extra_g2_slab14_factor_inventory:
                    residual_audit["factor_measurement"] = factor_measurement
                g2_identity_state["audit"]["iter20_real_residual"] = (
                    residual_audit
                )
                g2_identity_state["audit"]["missing_iterations"] = []
                g2_identity_state["audit"]["gate_pass"] = bool(
                    g2_identity_state["audit"]["deterministic_vectors"][
                        "gate_pass"
                    ]
                    and residual_audit["gate_pass"]
                )
                g2_identity_state["audit"]["status"] = (
                    "pass"
                    if g2_identity_state["audit"]["gate_pass"]
                    else "identity_gate_failed"
                )
            if residual_snapshot_observer is None:
                return
            residual_snapshot_observer(
                int(iteration),
                residual_work,
                float(reported_value),
                float(true_value),
            )

        emit_residual_snapshot(0, 1.0, initial_condensed)
        ksp = PETSc.KSP().create(comm)
        owned.append(ksp)
        live_state["outer_ksp"] = True
        ksp.setOperators(operator)
        ksp.setType("fgmres")
        ksp.setGMRESRestart(90)
        ksp.setPCSide(PETSc.PC.Side.RIGHT)
        ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
        ksp.setTolerances(rtol=1.0e-6, atol=0.0, max_it=int(screen_iterations))
        pc = ksp.getPC()
        pc.setType(PETSc.PC.Type.PYTHON)
        pc.setPythonContext(coarse)
        live_state["outer_pc"] = True
        ksp.setUp()
        emit_lifecycle(
            "outer_ksp_setup",
            ksp_type=str(ksp.getType()),
        )
        setup_seconds = perf_counter() - started

        def monitor(current: PETSc.KSP, iteration: int, residual_norm: float) -> None:
            reported = float(residual_norm) / max(rhs_norm, _TINY)
            if not reported_history or reported_history[-1][0] != iteration:
                reported_history.append((int(iteration), reported))
            if (
                iteration in (10, 20)
                or (screen_iterations > 3000 and iteration % 100 == 0)
                or (
                    residual_snapshot_observer is not None
                    and iteration == 100
                )
            ) and iteration not in sampled_iterations:
                current_solution = current.buildSolution(monitor_solution)
                condensed = _relative_residual(
                    operator, rhs, current_solution, residual_work, rhs_norm
                )
                condensed_samples.append((int(iteration), condensed))
                sampled_iterations.add(iteration)
                if residual_observer is not None:
                    residual_observer(int(iteration), reported, condensed)
                emit_residual_snapshot(
                    int(iteration),
                    reported,
                    condensed,
                )

        ksp.setMonitor(monitor)
        solve_started = perf_counter()
        ksp.solve(rhs, solution)
        solve_seconds = perf_counter() - solve_started
        reason = int(ksp.getConvergedReason())
        iterations = int(ksp.getIterationNumber())
        reported = float(ksp.getResidualNorm()) / max(rhs_norm, _TINY)
        condensed = _relative_residual(operator, rhs, solution, residual_work, rhs_norm)
        if iterations not in sampled_iterations:
            condensed_samples.append((iterations, condensed))
            if residual_observer is not None:
                residual_observer(iterations, reported, condensed)
            emit_residual_snapshot(iterations, reported, condensed)
        emit_lifecycle(
            "outer_ksp_solved",
            converged_reason=reason,
            iterations=iterations,
            reported_relative_residual=reported,
        )

        recovery_started = perf_counter()
        auxiliary = recover_petsc_auxiliary(blocks, solution)
        owned.append(auxiliary)
        live_state["recovered_auxiliary"] = True
        augmented = (
            request_rhs.duplicate()
            if action_only or exact_profile
            else request_operator.createVecRight()
        )
        owned.append(augmented)
        live_state["augmented_solution"] = True
        combine_petsc_augmented_solution(blocks, solution, auxiliary, augmented)
        if (
            augmented.getSize() != request_rhs.getSize()
            or augmented.getSize() != request_operator_size[1]
            or augmented.getOwnershipRange() != request_rhs.getOwnershipRange()
            or augmented.getOwnershipRange() != request_operator_columns
        ):
            raise ValueError(
                "returned augmented solution layout does not match the borrowed "
                "RHS and operator columns"
            )
        emit_lifecycle(
            "augmented_solution_recovered",
        )
        full_augmented = full_augmented_relative_residual(
            blocks, solution, auxiliary, fine_operator=fine_action
        )
        emit_lifecycle(
            "full_augmented_residual_complete",
            full_augmented_true_residual=float(full_augmented),
        )
        recovery_seconds = perf_counter() - recovery_started
        smoother_audit = smoother.diagnostics
        formal_operator_apply_count = int(operator_context.apply_count)
        formal_coarse_audit = {
            "apply_count": int(coarse.apply_count),
            "apply_elapsed_s": float(coarse.apply_elapsed_s),
            "smoother_elapsed_s": float(coarse.smoother_elapsed_s),
            "coarse_elapsed_s": float(coarse.coarse_elapsed_s),
        }
        if p2_auxiliary_profile:
            factor_nnz = int(smoother_audit["p2_factor_nnz_used"])
            factor_rows = int(smoother_audit["p2_rows"])
            factor_csr_payload_estimate_bytes = int(
                smoother_audit["p2_factor_payload_lower_bound_bytes"]
            )
        else:
            factor_nnz = int(smoother_audit["global_stored_factor_nnz"])
            factor_rows = int(smoother_audit["global_factor_rows"])
            scalar_bytes = np.dtype(PETSc.ScalarType).itemsize
            integer_bytes = np.dtype(PETSc.IntType).itemsize
            factor_csr_payload_estimate_bytes = int(
                factor_nnz * (scalar_bytes + integer_bytes)
                + (factor_rows + 16) * integer_bytes
            )
        if p2_auxiliary_profile:
            factor_inventory = {
                "full_p6_global_direct_factor_count": 0,
                "global_schur_matrix_materialized": False,
                "global_A_materialized": False,
                "global_F_materialized": False,
                "p6_factor_count": 0,
                "p6_slab_matrix_count": 0,
                "p2_distributed_mumps_factor_count": 1,
                "wave_coarse_dense_lu_count": 1,
                "n_aux": int(request.n_aux),
                "coarse_dimension": len(basis),
                "allowed_factor_scope": [
                    "SmallDenseInverse(H)",
                    "dense coarse LU",
                    "p2 distributed MUMPS factor",
                ],
            }
            if factor_free_p2_profile:
                patch_runtime = smoother_audit["factor_free_slab_patch"]
                factor_inventory.update(
                    {
                        "p6_factor_count": patch_runtime["p6_factor_count"],
                        "p6_factor_nnz": patch_runtime["p6_factor_nnz"],
                        "p6_slab_matrix_count": patch_runtime["p6_slab_matrix_count"],
                    }
                )
        else:
            factor_inventory = {
                "global_direct_factor_count": 0,
                "global_schur_matrix_materialized": False,
                "global_A_materialized": not action_only,
                "global_F_materialized": not action_only and not exact_profile,
                "n_aux": int(request.n_aux),
                "coarse_dimension": len(basis),
                "allowed_factor_scope": [
                    "SmallDenseInverse(H)",
                    "dense coarse LU",
                    "COMM_SELF factor_only ILU(0)",
                ],
            }
        g2_factor_audit = None
        if task037_extra_g2_slab14_factor_inventory:
            assert g2_factor_state is not None
            slab_owner = int(g2_factor_state["owner"])
            fullspace_inventory = comm.bcast(
                (
                    g2_factor_state["oracle"].inventory
                    if comm.rank == slab_owner
                    else None
                ),
                root=slab_owner,
            )
            trace_inventory = comm.bcast(
                (
                    smoother._diagnostic_owner_local_factor_inventory(
                        _TASK037_G2_SLAB
                    )
                    if comm.rank == slab_owner
                    else None
                ),
                root=slab_owner,
            )
            payload_route = _task037_g2_factor_payload_route(
                trace_inventory,
                fullspace_inventory,
            )
            iter20_factor_measurement = g2_factor_state["iter20"]
            factor_status = _task037_g2_factor_status(
                payload_route,
                iter20_factor_measurement,
            )
            g2_factor_audit = {
                "primary_slab": _TASK037_G2_SLAB,
                "global_A_materialized": False,
                "global_F_materialized": False,
                "official_result_unaffected": True,
                "inventory_only": True,
                "used_in_outer_preconditioner": False,
                "matrix_audit": dict(g2_factor_state["matrix_audit"]),
                "fullspace_factor_inventory": fullspace_inventory,
                "current_trace_factor_inventory": trace_inventory,
                "retained_payload_route": payload_route,
                "iter20": iter20_factor_measurement,
                **factor_status,
            }
        candidate = {
            "outer_ksp": str(ksp.getType()),
            "pc_side": "right",
            "norm_type": "unpreconditioned",
            "restart": 90,
            "rtol": 1.0e-6,
            "atol": 0.0,
            "max_it": int(screen_iterations),
            **(
                {
                    "num_slabs": 16,
                    "overlap_fraction": 0.125,
                    "interpolation": "partition",
                    "local_krylov_steps": local_krylov_steps,
                    "local_inner_preconditioner": "none",
                    "outer_requires_fgmres": True,
                    "p2_auxiliary_correction": True,
                    "fine_operator_kind": "borrowed_p6_condensed_dtn_action",
                    "fine_schur_action_kind": "borrowed_p6_static_local_schur_action",
                    "wave_coarse_post_smooth": False,
                }
                if factor_free_p2_profile
                else {
                    "p6_smoothing": "not_used",
                    "p2_auxiliary_correction": True,
                    "p2_absorption_shift": 0.1,
                    "p2_diagonal_patch_omega": 0.6,
                    "wave_coarse_post_smooth": False,
                }
                if p2_auxiliary_profile
                else {
                    "num_slabs": 16,
                    "overlap_fraction": 0.125,
                    "interpolation": "partition",
                    "absorption_shift": 0.1,
                }
                if m3a_profile
                else {
                    "num_slabs": 16,
                    "overlap_fraction": 0.25,
                    "absorption_shift": 0.1,
                }
            ),
        }
        if factor_free_p2_ras_profile:
            candidate.update(
                {
                    "variant": "ras",
                    "correction_partition": "one_hot_ras",
                    "interface_shift_mode": "shared_rows_only",
                }
            )
        audit = {
            "matrix_type": "python_action_only" if action_only else "assembled",
            "global_A_materialized": not action_only,
            "global_F_materialized": not action_only and not exact_profile,
            "candidate": candidate,
            "solver_profile": solver_profile,
            "assembled_matrix_released_before_solve": assembled_matrix_released,
            "fine_action_relative_error": fine_action_error,
            "reported_history": reported_history,
            "condensed_true_samples": condensed_samples,
            "final": {
                "converged_reason": reason,
                "iterations": iterations,
                "reported_relative_residual": reported,
                "condensed_true_residual": condensed,
                "full_augmented_true_residual": full_augmented,
            },
            "timings_seconds": {
                "setup": float(setup_seconds),
                "solve": float(solve_seconds),
                "recovery": float(recovery_seconds),
                "total": float(perf_counter() - started),
            },
            "operator_apply_count": formal_operator_apply_count,
            "coarse": {
                "dimension": len(basis),
                "rank": int(coarse.coarse_rank),
                "condition": float(coarse.coarse_condition),
                "basis_storage_bytes": int(coarse.basis_storage_bytes),
                "apply_count": formal_coarse_audit["apply_count"],
            },
            "partition_audit": partition_audit,
            "smoother_diagnostics": smoother_audit,
            "factor_csr_payload_estimate_bytes": factor_csr_payload_estimate_bytes,
            "no_global_factor_inventory": factor_inventory,
        }
        if g2_identity_state is not None:
            if g2_identity_state["audit"]["iter20_real_residual"] is None:
                g2_identity_state["audit"]["status"] = "missing_iter20"
                g2_identity_state["audit"]["gate_pass"] = False
                g2_identity_state["audit"]["missing_iterations"] = [20]
            audit["task037_extra_g2_slab14_identity"] = dict(
                g2_identity_state["audit"]
            )
        if g2_factor_audit is not None:
            audit["task037_extra_g2_slab14_factor_inventory"] = g2_factor_audit
        if g2_lor_transfer_audit is not None:
            audit["task037_extra_g2_slab14_lor_transfer"] = (
                g2_lor_transfer_audit
            )
        if g2_lor_hx_audit is not None:
            audit["task037_extra_g2_slab14_lor_hx_oracle"] = g2_lor_hx_audit
        if p2_auxiliary_profile:
            audit["p2_auxiliary_audit"] = p2_auxiliary_audit
        if task037_extra_g0_diagnostics:
            from .static_factor_free_slab_pc import FactorFreeLocalSlabKrylovPc
            from .static_slab_contraction import (
                measure_owner_local_slab_contractions,
            )

            diagnostic_started = perf_counter()
            diagnostics_by_iteration: dict[str, Any] = {}
            b4 = FactorFreeLocalSlabKrylovPc(
                fine_action,
                owner_plan,
                shift,
                local_krylov_steps=4,
                variant="partition",
            )
            try:
                for iteration in (0, 20):
                    residual_snapshot = g0_residual_snapshots.get(iteration)
                    if residual_snapshot is None:
                        continue
                    diagnostics_by_iteration[str(iteration)] = (
                        measure_owner_local_slab_contractions(
                            global_operator=operator,
                            shifted_local_operator=shifted_fine,
                            residual=residual_snapshot,
                            plan=owner_plan,
                            smoother=smoother,
                            b4=b4,
                            fixed_two_step_apply=smoother.solve,
                            m3a_two_level_apply=(
                                lambda source, target: coarse.apply(
                                    None, source, target
                                )
                            ),
                        )
                    )
            finally:
                b4.destroy()
            audit["task037_extra_g0_diagnostics"] = {
                "enabled": True,
                "retained_iterations": sorted(g0_residual_snapshots),
                "missing_iterations": [
                    iteration
                    for iteration in (0, 20)
                    if iteration not in g0_residual_snapshots
                ],
                "formal_audit_frozen_before_diagnostic": {
                    "operator_apply_count": formal_operator_apply_count,
                    "coarse": formal_coarse_audit,
                    "smoother_apply_count": int(
                        smoother_audit.get(
                            "one_level_apply_count",
                            smoother_audit.get("apply_count", 0),
                        )
                    ),
                    "global_factor_rows": int(
                        smoother_audit.get("global_factor_rows", 0)
                    ),
                    "global_stored_factor_nnz": int(
                        smoother_audit.get("global_stored_factor_nnz", 0)
                    ),
                },
                "diagnostic_wall_seconds": float(
                    perf_counter() - diagnostic_started
                ),
                "by_iteration": diagnostics_by_iteration,
            }
        snapshot = Stage4ExternalLinearSolverSnapshot(
            x=augmented,
            converged_reason=reason,
            iterations=iterations,
            reported_relative_residual=reported,
            condensed_true_residual=condensed,
            full_augmented_true_residual=full_augmented,
            ksp_type=str(ksp.getType()),
            pc_type=str(pc.getType()),
            residual_limit=1.0e-6,
            no_global_factor=True,
            solver_profile=solver_profile,
            assembled_matrix_released_before_solve=assembled_matrix_released,
            reduced_residual_norm=condensed * rhs_norm,
        )
        owned.remove(augmented)
        returned_solution_transferred = True
        live_state["returned_augmented_solution"] = True
        return snapshot, audit
    finally:
        for item in reversed(owned):
            item.destroy()
        for name in (
            "active_F",
            "C",
            "D",
            "H",
            "extracted_active_rhs",
            "extracted_aux_rhs",
            "condensed_active_rhs",
            "fine_action",
            "matrix_free_operator",
            "basis",
            "shifted_action",
            "shift",
            "coarse",
            "solution",
            "monitor_solution",
            "residual_work",
            "outer_ksp",
            "outer_pc",
            "recovered_auxiliary",
            "augmented_solution",
        ):
            live_state[name] = False
        live_state["slab_factors"] = 0
        emit_lifecycle(
            "solver_owned_objects_released",
            normal_completion=returned_solution_transferred,
            returned_solution_transferred=returned_solution_transferred,
        )


def solve_assembled_static_condensed_fgmres(
    request: Stage4ExternalLinearSolverRequest,
    *,
    screen_iterations: Literal[20],
    residual_observer: Callable[[int, float, float], None] | None = None,
    residual_snapshot_observer: Callable[[int, PETSc.Vec, float, float], None]
    | None = None,
    solver_profile: Literal[
        "assembled", "assembled_setup_then_static_local_schur_matrix_free_solve"
    ] = "assembled",
    release_assembled_matrix: Callable[[], None] | None = None,
    lifecycle_observer: Callable[[str, dict[str, Any]], None] | None = None,
) -> tuple[Stage4ExternalLinearSolverSnapshot, dict[str, Any]]:
    """Preserve the ordinary/F5b entry while sharing the M2c solve core."""

    return _solve_static_condensed_fgmres_core(
        request,
        screen_iterations=screen_iterations,
        residual_observer=residual_observer,
        residual_snapshot_observer=residual_snapshot_observer,
        solver_profile=solver_profile,
        release_assembled_matrix=release_assembled_matrix,
        lifecycle_observer=lifecycle_observer,
    )


def solve_never_materialized_static_condensed_fgmres(
    request: Stage4NeverMaterializedLinearSolverRequest,
    *,
    screen_iterations: Literal[20] = 20,
    residual_observer: Callable[[int, float, float], None] | None = None,
    residual_snapshot_observer: Callable[[int, PETSc.Vec, float, float], None]
    | None = None,
    lifecycle_observer: Callable[[str, dict[str, Any]], None] | None = None,
) -> tuple[Stage4ExternalLinearSolverSnapshot, dict[str, Any]]:
    """Run the shared 20-step core against borrowed action-only objects."""

    return _solve_static_condensed_fgmres_core(
        request,
        screen_iterations=screen_iterations,
        residual_observer=residual_observer,
        residual_snapshot_observer=residual_snapshot_observer,
        solver_profile="never_materialized_owner_local",
        lifecycle_observer=lifecycle_observer,
    )


def solve_never_materialized_overlap0125_partition_fgmres(
    request: Stage4NeverMaterializedLinearSolverRequest,
    *,
    screen_iterations: Literal[20, 100, 200] = 20,
    residual_observer: Callable[[int, float, float], None] | None = None,
    residual_snapshot_observer: Callable[[int, PETSc.Vec, float, float], None]
    | None = None,
    task037_extra_g0_diagnostics: bool = False,
    task037_extra_g2_slab14_identity: bool = False,
    task037_extra_g2_slab14_factor_inventory: bool = False,
    task037_extra_g2_slab14_lor_transfer: bool = False,
    task037_extra_g2_slab14_lor_hx_oracle: bool = False,
    lifecycle_observer: Callable[[str, dict[str, Any]], None] | None = None,
) -> tuple[Stage4ExternalLinearSolverSnapshot, dict[str, Any]]:
    """Run the opt-in overlap-0.125 partition-weighted slab profile."""

    return _solve_static_condensed_fgmres_core(
        request,
        screen_iterations=screen_iterations,
        residual_observer=residual_observer,
        residual_snapshot_observer=residual_snapshot_observer,
        task037_extra_g0_diagnostics=task037_extra_g0_diagnostics,
        task037_extra_g2_slab14_identity=task037_extra_g2_slab14_identity,
        task037_extra_g2_slab14_factor_inventory=(
            task037_extra_g2_slab14_factor_inventory
        ),
        task037_extra_g2_slab14_lor_transfer=(
            task037_extra_g2_slab14_lor_transfer
        ),
        task037_extra_g2_slab14_lor_hx_oracle=(
            task037_extra_g2_slab14_lor_hx_oracle
        ),
        solver_profile="never_materialized_owner_local_overlap0125_partition",
        lifecycle_observer=lifecycle_observer,
    )


def solve_never_materialized_p2_auxiliary_fgmres(
    request: Stage4NeverMaterializedLinearSolverRequest,
    *,
    screen_iterations: Literal[20, 100, 200] = 20,
    residual_observer: Callable[[int, float, float], None] | None = None,
    residual_snapshot_observer: Callable[[int, PETSc.Vec, float, float], None]
    | None = None,
    lifecycle_observer: Callable[[str, dict[str, Any]], None] | None = None,
) -> tuple[Stage4ExternalLinearSolverSnapshot, dict[str, Any]]:
    """Run the shared core with the opt-in true p2 auxiliary PC profile."""

    return _solve_static_condensed_fgmres_core(
        request,
        screen_iterations=screen_iterations,
        residual_observer=residual_observer,
        residual_snapshot_observer=residual_snapshot_observer,
        solver_profile="never_materialized_p2_auxiliary",
        lifecycle_observer=lifecycle_observer,
    )


def solve_never_materialized_p2_factor_free_slab_auxiliary_fgmres(
    request: Stage4NeverMaterializedLinearSolverRequest,
    *,
    screen_iterations: int = 20,
    local_krylov_steps: Literal[2, 4] = 2,
    residual_observer: Callable[[int, float, float], None] | None = None,
    residual_snapshot_observer: Callable[[int, PETSc.Vec, float, float], None]
    | None = None,
    lifecycle_observer: Callable[[str, dict[str, Any]], None] | None = None,
) -> tuple[Stage4ExternalLinearSolverSnapshot, dict[str, Any]]:
    """Run the factor-free slab plus true p2 auxiliary profile."""

    return _solve_static_condensed_fgmres_core(
        request,
        screen_iterations=screen_iterations,
        local_krylov_steps=local_krylov_steps,
        residual_observer=residual_observer,
        residual_snapshot_observer=residual_snapshot_observer,
        solver_profile="never_materialized_p2_factor_free_slab_auxiliary",
        lifecycle_observer=lifecycle_observer,
    )


def solve_never_materialized_p2_factor_free_slab_ras_auxiliary_fgmres(
    request: Stage4NeverMaterializedLinearSolverRequest,
    *,
    screen_iterations: Literal[20, 100, 200] = 20,
    residual_observer: Callable[[int, float, float], None] | None = None,
    residual_snapshot_observer: Callable[[int, PETSc.Vec, float, float], None]
    | None = None,
    lifecycle_observer: Callable[[str, dict[str, Any]], None] | None = None,
) -> tuple[Stage4ExternalLinearSolverSnapshot, dict[str, Any]]:
    """Run the fixed-four-step RAS factor-free p2 auxiliary profile."""

    return _solve_static_condensed_fgmres_core(
        request,
        screen_iterations=screen_iterations,
        local_krylov_steps=4,
        residual_observer=residual_observer,
        residual_snapshot_observer=residual_snapshot_observer,
        solver_profile="never_materialized_p2_factor_free_slab_ras_auxiliary",
        lifecycle_observer=lifecycle_observer,
    )
