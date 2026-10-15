"""Focused Task041 H1c tests for the real physical-side operators."""

from __future__ import annotations

import copy
import hashlib
import json
from types import SimpleNamespace

import numpy as np
import pytest
from dolfinx import fem
from mpi4py import MPI
from petsc4py import PETSc

from src.common.config_3d import (
    ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
    SimulationConfig3D,
)
from src.coupling.hybrid_internal_modes import build_hybrid_internal_mode_coupling
from src.geometry.hybrid_local_mesh import build_hybrid_local_mesh
from src.modes.cross_section_spaces import (
    build_cross_section_spaces,
    build_matching_cross_section,
)
from src.solvers.dtn_port_3d import _augmented_vec_from_base
from src.solvers.hcurl_assembly_time_condensation import (
    recover_owned_cell_interiors,
)
from src.solvers.hybrid_fem_modal_block_ldu import (
    TASK041_V13_CONSISTENT_MODAL_POLICY_ID,
    HybridAugmentedLayout,
    create_side_balh_block_ldu_preconditioner,
    resolve_task041_modal_solver_policy,
)
from src.solvers.hybrid_fem_modal_iterative import (
    create_hybrid_assembled_block_action,
)
from src.solvers.hybrid_local_dtn import assemble_hybrid_local_dtn_system
from src.solvers.hybrid_local_dtn_action import (
    assemble_hybrid_local_dtn_action_system,
)
from src.solvers.hybrid_local_dtn_woodbury import ResearchExactFactorInverse
from src.solvers.physical_balanced_fused_volume import (
    build_task041_fused_physical_volume_context,
)
from src.solvers.physical_balanced_physical_operator import (
    FullSpacePhysicalDtnActionSystem,
    P4CondensedExactFactor,
    P4ExactFactor,
    _assemble_augmented_matrix,
    _build_matching_p4_action,
    build_fullspace_physical_dtn_action,
    build_p4_condensed_exact_factor_from_action,
    build_p4_exact_factor,
)
from src.solvers.physical_balanced_same_mesh_transfer import (
    build_same_mesh_hcurl_owner_transfer,
)
from src.solvers.physical_balanced_side_inverse import (
    build_side_balanced_inverse,
)
from src.solvers.physical_balanced_trace_bridge import (
    extract_full_p6_to_active_trace,
    inject_active_residual_to_full_p6,
)

pytestmark = pytest.mark.skipif(
    MPI.COMM_WORLD.size not in (1, 2),
    reason="Task041 H1c focused physical tests are serial/MPI2 only",
)

# Review §6 accepts the p6 full/condensed reference and original physical
# residuals at 5e-9.  Mapping, p4, and global action checks retain 1e-10/1e-12.
_P6_TOLERANCE = 5.0e-9
_STRICT_TOLERANCE = 1.0e-10


def _task041_v16_rank_ksp_fields(record: object) -> dict[str, int] | None:
    """Read required solver outcomes from the sealed nested KSP record."""
    if not isinstance(record, dict):
        return None
    ksp = record.get("ksp")
    if not isinstance(ksp, dict):
        return None
    fields = {
        "converged_reason": ksp.get("converged_reason"),
        "iterations": ksp.get("iterations"),
        "max_iterations": ksp.get("max_iterations"),
    }
    if any(
        not isinstance(value, int) or isinstance(value, bool)
        for value in fields.values()
    ):
        return None
    if fields["iterations"] < 0 or fields["max_iterations"] < 1:
        return None
    return {
        "converged_reason": int(fields["converged_reason"]),
        "iterations": int(fields["iterations"]),
        "max_iterations": int(fields["max_iterations"]),
    }


def _task041_v16_iteration_limit_candidate(
    record: object,
    iteration_limit_reasons: set[int],
    *,
    clean_pc_capture_evidence: bool,
    residual_tolerance: float = _P6_TOLERANCE,
) -> bool:
    """Apply the per-rank R60 precondition without trusting summary fields."""
    fields = _task041_v16_rank_ksp_fields(record)
    if fields is None or not isinstance(record, dict):
        return False
    relative = record.get("ax_minus_f_relative")
    return bool(
        fields["converged_reason"] in iteration_limit_reasons
        and fields["iterations"] == 600
        and fields["max_iterations"] == 600
        and isinstance(relative, (int, float))
        and np.isfinite(float(relative))
        and float(relative) > residual_tolerance
        and record.get("rhs_unchanged") is True
        and clean_pc_capture_evidence is True
    )


def _task041_v16_numeric_record_qualified(
    record: object,
    *,
    clean_pc_capture_evidence: bool,
    residual_tolerance: float = _P6_TOLERANCE,
) -> bool:
    """Check the per-rank KSP/result portion of tiny qualification."""
    fields = _task041_v16_rank_ksp_fields(record)
    if fields is None or not isinstance(record, dict):
        return False
    checks = record.get("checks")
    relative = record.get("ax_minus_f_relative")
    return bool(
        fields["converged_reason"] > 0
        and fields["iterations"] >= 2
        and isinstance(relative, (int, float))
        and np.isfinite(float(relative))
        and float(relative) <= residual_tolerance
        and isinstance(checks, dict)
        and checks.get("successful_pc_applies_cover_iterations") is True
        and checks.get("finite_ax_minus_f_relative") is True
        and checks.get("ax_minus_f_within_tolerance") is True
        and record.get("rhs_unchanged") is True
        and clean_pc_capture_evidence is True
    )


def _task041_v16_validate_snapshot_arrays(
    arrays: object,
) -> dict[str, object]:
    """Validate frozen row arrays with only the two defined log-zero cases."""
    if not isinstance(arrays, dict) or not arrays:
        return {"status": "failed", "reason": "arrays_missing_or_not_mapping"}
    if any(not isinstance(value, np.ndarray) for value in arrays.values()):
        return {"status": "failed", "reason": "array_value_has_wrong_type"}

    log_pairs = {
        "row_relative_log_error": ("row_relative_error", "d"),
        "decomposition_row_relative_log_error": (
            "decomposition_row_relative_error",
            "decomposition_error",
        ),
    }
    permitted_log_fields = set(log_pairs)
    for name, value in arrays.items():
        if value.dtype.kind not in "biufc":
            return {
                "status": "failed",
                "reason": f"nonnumeric_array:{name}",
            }
        if name not in permitted_log_fields and not np.isfinite(value).all():
            return {
                "status": "failed",
                "reason": f"nonfinite_physical_or_unrecognized_array:{name}",
            }

    permitted_negative_infinity: dict[str, list[int]] = {}
    for log_name, (linear_name, actual_error_name) in log_pairs.items():
        if log_name not in arrays:
            continue
        if linear_name not in arrays or actual_error_name not in arrays:
            return {
                "status": "failed",
                "reason": f"log_pair_missing:{log_name}",
            }
        log_values = arrays[log_name]
        linear_values = arrays[linear_name]
        actual_error = arrays[actual_error_name]
        if (
            log_values.dtype.kind != "f"
            or linear_values.dtype.kind != "f"
            or log_values.shape != linear_values.shape
            or log_values.shape != actual_error.shape
            or log_values.ndim != 1
        ):
            return {
                "status": "failed",
                "reason": f"log_pair_shape_or_type_mismatch:{log_name}",
            }
        negative_infinity = np.isneginf(log_values)
        if not np.isfinite(linear_values).all() or np.any(linear_values < 0.0):
            return {
                "status": "failed",
                "reason": f"linear_error_invalid:{linear_name}",
            }
        if not np.all(np.isfinite(log_values) | negative_infinity):
            return {
                "status": "failed",
                "reason": f"log_error_nan_or_positive_infinity:{log_name}",
            }
        if np.any(negative_infinity):
            exact_zero = (linear_values == 0.0) & (actual_error == 0.0)
            if not np.all(exact_zero[negative_infinity]):
                return {
                    "status": "failed",
                    "reason": f"negative_infinity_without_exact_zero:{log_name}",
                }
            permitted_negative_infinity[log_name] = np.flatnonzero(
                negative_infinity
            ).astype(int).tolist()

    if "row_relative_log_error" in arrays:
        required = ("w_modal", "r_modal", "d")
        if any(name not in arrays for name in required):
            return {
                "status": "failed",
                "reason": "row_residual_reconstruction_fields_missing",
            }
        w_modal, r_modal, residual = (arrays[name] for name in required)
        if (
            w_modal.shape != r_modal.shape
            or w_modal.shape != residual.shape
            or not np.array_equal(residual, w_modal - r_modal)
        ):
            return {
                "status": "failed",
                "reason": "row_residual_does_not_match_w_minus_r",
            }

    if "decomposition_row_relative_log_error" in arrays:
        required = (
            "w_modal",
            "t_constraint",
            "t_bottom",
            "t_top",
            "decomposition_error",
        )
        if any(name not in arrays for name in required):
            return {
                "status": "failed",
                "reason": "decomposition_reconstruction_fields_missing",
            }
        w_modal = arrays["w_modal"]
        decomposition = arrays["t_constraint"].copy()
        if any(
            arrays[name].shape != w_modal.shape
            for name in ("t_constraint", "t_bottom", "t_top", "decomposition_error")
        ):
            return {
                "status": "failed",
                "reason": "decomposition_shape_mismatch",
            }
        decomposition += arrays["t_bottom"]
        decomposition += arrays["t_top"]
        reconstructed_difference = w_modal - decomposition
        if not np.array_equal(
            arrays["decomposition_error"], reconstructed_difference
        ):
            return {
                "status": "failed",
                "reason": "decomposition_error_does_not_match_components",
            }

    return {
        "status": "passed",
        "array_count": len(arrays),
        "permitted_negative_infinity_indices": permitted_negative_infinity,
    }


def _fixture_config(degree: int, *, condensed: bool) -> SimulationConfig3D:
    return SimulationConfig3D(
        stage_case="stage4_block_grating",
        geometry_kind="rectangular_block_grating",
        lambda0=3.7,
        period_x=1.0,
        period_y=1.0,
        z_min=0.0,
        z_max=1.0,
        interface_z=0.5,
        n_substrate=1.4 + 0.02j,
        n_grating=1.7 + 0.01j,
        grating_width_x=1.0,
        grating_width_y=1.0,
        grating_height=0.5,
        incident_theta_deg=17.0,
        incident_phi_deg=23.0,
        polarization_kind="s",
        nedelec_degree=degree,
        mesh_cell_type="hexahedron",
        mesh_target_size=1.0,
        mesh_axis_cell_counts=(2, 2, 2),
        use_floquet_xy=True,
        floquet_constraint_mode=f"topological_trace_p{degree}",
        stage4_dtn_order_policy="manual",
        diffraction_zero_order_only=False,
        diffraction_order_max_m=1,
        diffraction_order_max_n=0,
        stage4_full3d_assembly_backend=(
            ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND
            if condensed
            else "standard_full"
        ),
    )


def _fill_algebraic(vector: PETSc.Vec, slaves: np.ndarray, seed: float) -> None:
    first, last = (int(value) for value in vector.getOwnershipRange())
    global_rows = np.arange(first, last, dtype=np.float64)
    vector.getArray()[:] = (
        seed
        + 0.01 * global_rows
        + 1.0
        + 1j * (0.2 * seed + 0.007 * global_rows + 0.3)
    ).astype(PETSc.ScalarType)
    local_slaves = np.asarray(slaves, dtype=np.int64)
    if len(local_slaves):
        vector.getArray()[local_slaves] = 0.0
    vector.assemble()


def _fill_active(vector: PETSc.Vec, seed: float) -> None:
    first, last = (int(value) for value in vector.getOwnershipRange())
    rows = np.arange(first, last, dtype=np.float64)
    vector.getArray()[:] = (
        seed + 0.013 * rows + 1j * (0.4 + 0.009 * rows)
    ).astype(PETSc.ScalarType)
    vector.assemble()


def _extract_fe_segment(augmented: PETSc.Vec, n_fe: int) -> PETSc.Vec:
    start, end = (int(value) for value in augmented.getOwnershipRange())
    local_fe = max(0, min(end, int(n_fe)) - start)
    result = PETSc.Vec().createMPI(
        (local_fe, int(n_fe)),
        comm=augmented.getComm(),
    )
    result_start, result_end = (int(value) for value in result.getOwnershipRange())
    if result_end > result_start:
        result.getArray()[:] = augmented.getValues(
            np.arange(result_start, result_end, dtype=PETSc.IntType)
        )
    result.assemble()
    return result


def _raw_residual_gate(
    residual: PETSc.Vec,
    rhs: PETSc.Vec,
    *,
    tolerance: float = _STRICT_TOLERANCE,
) -> dict[str, object]:
    comm = residual.getComm().tompi4py()
    finite_local = bool(
        np.isfinite(np.asarray(residual.getArray(readonly=True))).all()
    )
    finite = bool(comm.allreduce(finite_local, op=MPI.LAND))
    residual_norm = float(residual.norm())
    rhs_norm = float(rhs.norm())
    if rhs_norm == 0.0:
        relative = None
        passed = bool(finite and np.isfinite(residual_norm)
                      and residual_norm <= float(tolerance))
    else:
        relative = residual_norm / rhs_norm
        passed = bool(finite and np.isfinite(relative)
                      and relative <= float(tolerance))
    return {
        "tolerance": float(tolerance),
        "residual_norm": residual_norm,
        "rhs_norm": rhs_norm,
        "relative_residual": relative,
        "finite": finite and np.isfinite(residual_norm) and np.isfinite(rhs_norm),
        "passed": passed,
    }


def _raw_augmented_residual_metrics(
    matrix: PETSc.Mat,
    residual: PETSc.Vec,
    rhs: PETSc.Vec,
    solution: PETSc.Vec,
    fe_rows: int,
    *,
    tolerance: float,
) -> dict[str, object]:
    """Measure one oracle residual without making the oracle gate abort early."""

    comm = residual.getComm().tompi4py()
    start, end = (int(value) for value in residual.getOwnershipRange())
    values = np.asarray(residual.getArray(readonly=True), dtype=np.complex128)
    global_rows = np.arange(start, end, dtype=np.int64)
    fe_mask = global_rows < int(fe_rows)
    aux_mask = ~fe_mask
    local_fe_sq = float(np.vdot(values[fe_mask], values[fe_mask]).real)
    local_aux_sq = float(np.vdot(values[aux_mask], values[aux_mask]).real)
    fe_norm = float(np.sqrt(comm.allreduce(local_fe_sq, op=MPI.SUM)))
    aux_norm = float(np.sqrt(comm.allreduce(local_aux_sq, op=MPI.SUM)))
    residual_norm = float(residual.norm())
    rhs_norm = float(rhs.norm())
    solution_norm = float(solution.norm())
    matrix_norm = float(matrix.norm(PETSc.NormType.FROBENIUS))
    denominator = matrix_norm * solution_norm + rhs_norm
    if rhs_norm > 0.0:
        relative = residual_norm / rhs_norm
        gate_passed = bool(
            np.isfinite(relative) and relative <= float(tolerance)
        )
    else:
        relative = None
        gate_passed = bool(
            np.isfinite(residual_norm) and residual_norm <= float(tolerance)
        )
    backward_error = (
        residual_norm / denominator if denominator > 0.0 else residual_norm
    )
    return {
        "residual_norm": residual_norm,
        "relative_residual": relative,
        "fe_residual_norm": fe_norm,
        "aux_residual_norm": aux_norm,
        "rhs_norm": rhs_norm,
        "solution_norm": solution_norm,
        "matrix_frobenius_norm": matrix_norm,
        "consistent_norm_denominator": denominator,
        "consistent_backward_error": float(backward_error),
        "finite": bool(
            np.isfinite(values).all()
            and np.isfinite(
                [
                    residual_norm,
                    rhs_norm,
                    solution_norm,
                    matrix_norm,
                    denominator,
                    backward_error,
                ]
            ).all()
        ),
        "gate_passed": gate_passed,
    }


def _explicit_factor_solve(
    factor: ResearchExactFactorInverse,
    matrix: PETSc.Mat,
    rhs: PETSc.Vec,
    fe_rows: int,
    *,
    label: str,
    tolerance: float = _P6_TOLERANCE,
) -> tuple[PETSc.Vec, dict[str, object]]:
    solution = matrix.createVecRight()
    residual = rhs.duplicate()
    correction = None
    history: list[dict[str, object]] = []
    try:
        for iteration in range(3):
            if iteration == 0:
                factor.solve(rhs, solution)
            else:
                correction = matrix.createVecRight()
                try:
                    factor.solve(residual, correction)
                    solution.axpy(PETSc.ScalarType(-1.0), correction)
                finally:
                    correction.destroy()
                    correction = None
            matrix.mult(solution, residual)
            residual.axpy(PETSc.ScalarType(-1.0), rhs)
            metrics = _raw_augmented_residual_metrics(
                matrix,
                residual,
                rhs,
                solution,
                fe_rows,
                tolerance=tolerance,
            )
            metrics["iteration"] = int(iteration)
            history.append(metrics)
        final = history[-1]
        audit: dict[str, object] = {
            "label": label,
            "tolerance": float(tolerance),
            "raw_relative_residuals": tuple(
                item["relative_residual"] for item in history
            ),
            "history": tuple(history),
            "final_fe_residual_norm": final["fe_residual_norm"],
            "final_aux_residual_norm": final["aux_residual_norm"],
            "rhs_norm": final["rhs_norm"],
            "solution_norm": final["solution_norm"],
            "consistent_backward_error": final["consistent_backward_error"],
            "gate_passed": bool(final["finite"] and final["gate_passed"]),
        }
        if matrix.getComm().tompi4py().rank == 0:
            print(
                "H1c oracle "
                f"{label}: raw_relative={audit['raw_relative_residuals']}, "
                f"final_fe_abs={audit['final_fe_residual_norm']:.16e}, "
                f"final_aux_abs={audit['final_aux_residual_norm']:.16e}, "
                f"rhs_norm={audit['rhs_norm']:.16e}, "
                f"solution_norm={audit['solution_norm']:.16e}, "
                "Frobenius/2-norm backward_error="
                f"{audit['consistent_backward_error']:.16e}, "
                f"gate_tolerance={audit['tolerance']:.1e}, "
                f"gate={audit['gate_passed']}",
                flush=True,
            )
        return solution, audit
    except Exception:
        solution.destroy()
        raise
    finally:
        residual.destroy()
        if correction is not None:
            correction.destroy()


@pytest.fixture(scope="module")
def h1c_fixture():
    comm = MPI.COMM_WORLD
    cfg6 = _fixture_config(6, condensed=False)
    cfg_action = _fixture_config(6, condensed=True)
    meshes = {
        side: build_hybrid_local_mesh(
            cfg6,
            side,
            bottom_interface_z_nm=0.5,
            top_interface_z_nm=0.5,
            comm=comm,
        )
        for side in ("bottom", "top")
    }
    action_systems = {}
    p6: dict[str, FullSpacePhysicalDtnActionSystem] = {}
    p4: dict[str, P4ExactFactor] = {}
    full_oracle = {}
    condensed_oracle = {}
    full_factors = {}
    condensed_factors = {}
    owners = {}
    try:
        for side in ("bottom", "top"):
            action_systems[side] = assemble_hybrid_local_dtn_action_system(
                cfg_action,
                side,
                local_mesh_override=meshes[side],
                comm=comm,
            )
            p6[side] = build_fullspace_physical_dtn_action(
                action_systems[side]
            )
            p4[side] = build_p4_exact_factor(action_systems[side])
            full_oracle[side] = assemble_hybrid_local_dtn_system(
                cfg6,
                side,
                local_mesh_override=meshes[side],
                comm=comm,
            )
            condensed_oracle[side] = assemble_hybrid_local_dtn_system(
                cfg_action,
                side,
                local_mesh_override=meshes[side],
                comm=comm,
            )
            full_factors[side] = ResearchExactFactorInverse(
                full_oracle[side].A,
                factor_solver_type="mumps",
                factor_only_storage=True,
            )
            condensed_factors[side] = ResearchExactFactorInverse(
                condensed_oracle[side].A,
                factor_solver_type="mumps",
                factor_only_storage=True,
            )
            owners[side] = build_same_mesh_hcurl_owner_transfer(
                p6[side].V,
                p6[side].floquet_data,
                p4[side].physical_action.V,
                p4[side].physical_action.floquet_data,
            )
        yield {
            "cfg6": cfg6,
            "action_systems": action_systems,
            "p6": p6,
            "p4": p4,
            "condensed": action_systems,
            "full_oracle": full_oracle,
            "condensed_oracle": condensed_oracle,
            "full_factors": full_factors,
            "condensed_factors": condensed_factors,
            "owners": owners,
        }
    finally:
        for factor in full_factors.values():
            factor.destroy()
        for factor in condensed_factors.values():
            factor.destroy()
        for system in full_oracle.values():
            system.destroy()
        for system in condensed_oracle.values():
            system.destroy()
        for owner in owners.values():
            owner.destroy()
        for factor in p4.values():
            factor.destroy()
        for system in p6.values():
            system.destroy()
        for system in action_systems.values():
            system.destroy()


def test_task041_fused_physical_volume_matches_original_action() -> None:
    """Compare the explicit sum-factorized slice with UFL on the same p6 MPC."""

    comm = MPI.COMM_WORLD
    cfg6 = _fixture_config(6, condensed=False)
    cfg_action = _fixture_config(6, condensed=True)
    all_material_ids: set[int] = set()
    has_nonzero_bloch_coefficient = False
    action_comparisons: list[dict[str, object]] = []
    for side in ("bottom", "top"):
        local_mesh = build_hybrid_local_mesh(
            cfg6,
            side,
            bottom_interface_z_nm=0.5,
            top_interface_z_nm=0.5,
            comm=comm,
        )
        side_system = None
        reference = None
        candidate = None
        source = None
        reference_volume = None
        candidate_volume = None
        reference_full = None
        candidate_full = None
        difference = None
        first_candidate = None
        first_candidate_volume = None
        try:
            side_system = assemble_hybrid_local_dtn_action_system(
                cfg_action,
                side,
                local_mesh_override=local_mesh,
                comm=comm,
            )
            reference = build_fullspace_physical_dtn_action(side_system)
            candidate = build_fullspace_physical_dtn_action(
                side_system,
                volume_action_context_factory=(
                    build_task041_fused_physical_volume_context
                ),
            )
            source = reference.matrix.createVecRight()
            reference_volume = source.duplicate()
            candidate_volume = source.duplicate()
            reference_full = source.duplicate()
            candidate_full = source.duplicate()
            difference = source.duplicate()

            def assert_action_close(
                left,
                right,
                label: str,
                scratch=difference,
                action_side=side,
            ) -> float:
                left.copy(scratch)
                scratch.axpy(PETSc.ScalarType(-1.0), right)
                scale = float(left.norm())
                error = float(scratch.norm())
                relative = error / scale if scale != 0.0 else None
                action_comparisons.append(
                    {
                        "side": action_side,
                        "label": label,
                        "scale": scale if np.isfinite(scale) else str(scale),
                        "error": error if np.isfinite(error) else str(error),
                        "relative": (
                            relative
                            if relative is None or np.isfinite(relative)
                            else str(relative)
                        ),
                    }
                )
                assert np.isfinite(error), f"{action_side} {label} is non-finite"
                if scale == 0.0:
                    assert error <= _STRICT_TOLERANCE, (
                        f"{action_side} zero {label} error={error:.3e}"
                    )
                else:
                    assert relative <= _STRICT_TOLERANCE, (
                        f"{action_side} {label} relative error={relative:.3e}"
                    )
                return error

            cell_tags = side_system.local_mesh.mesh_data.cell_tags
            all_material_ids.update(int(value) for value in cell_tags.values)
            mpc_coefficients, _mpc_offsets = (
                side_system.floquet_data.mpc.coefficients()
            )
            has_nonzero_bloch_coefficient |= bool(
                np.any(np.asarray(mpc_coefficients).imag != 0.0)
            )

            for input_index, seed in enumerate((0.7, 3.1, 0.7)):
                input_label = ("A", "B", "A")[input_index]
                _fill_algebraic(
                    source,
                    reference.action.context.owned_slaves,
                    seed,
                )
                source_before = np.asarray(
                    source.getArray(readonly=True), dtype=np.complex128
                ).copy()

                reference.action.context.mult(None, source, reference_volume)
                candidate.action.context.mult(None, source, candidate_volume)
                local_input_unchanged = np.array_equal(
                    np.asarray(source.getArray(readonly=True)), source_before
                )
                assert comm.allreduce(
                    local_input_unchanged, op=MPI.LAND
                ), f"{side} volume action changed its input"

                assert_action_close(
                    reference_volume,
                    candidate_volume,
                    f"{input_label} volume action",
                )

                reference.matrix.mult(source, reference_full)
                candidate.matrix.mult(source, candidate_full)
                assert_action_close(
                    reference_full,
                    candidate_full,
                    f"{input_label} full DtN action",
                )
                local_input_unchanged = np.array_equal(
                    np.asarray(source.getArray(readonly=True)), source_before
                )
                assert comm.allreduce(local_input_unchanged, op=MPI.LAND), (
                    f"{side} full action changed its input"
                )
                if input_index == 0:
                    first_candidate_volume = candidate_volume.duplicate()
                    candidate_volume.copy(first_candidate_volume)
                    first_candidate = candidate_full.duplicate()
                    candidate_full.copy(first_candidate)
                elif input_index == 2:
                    assert_action_close(
                        first_candidate_volume,
                        candidate_volume,
                        "A-B-A repeated volume action",
                    )
                    assert_action_close(
                        first_candidate, candidate_full, "A-B-A repeated action"
                    )

            source.set(0.0)
            source.assemble()
            reference.action.context.mult(None, source, reference_volume)
            candidate.action.context.mult(None, source, candidate_volume)
            assert_action_close(
                reference_volume, candidate_volume, "zero volume action"
            )
            reference.matrix.mult(source, reference_full)
            candidate.matrix.mult(source, candidate_full)
            assert_action_close(reference_full, candidate_full, "zero full DtN action")
        finally:
            if candidate is not None and comm.rank == 0:
                kernel = candidate.action.context.audit["local_kernel"]
                print(
                    "TASK041_FUSED_PHYSICAL_VOLUME_ORACLE "
                    + json.dumps(
                        {
                            "side": side,
                            "comparisons": [
                                item
                                for item in action_comparisons
                                if item["side"] == side
                            ],
                            "kernel_payload_rank0": {
                                "owned_cells": int(kernel["owned_cells"]),
                                "batch_size": int(kernel["batch_size"]),
                                "batch_workspace_bytes": int(
                                    kernel["batch_workspace_bytes"]
                                ),
                                "cell_metadata_bytes": int(
                                    kernel["cell_metadata_bytes"]
                                ),
                                "reference_bytes": int(kernel["reference_bytes"]),
                                "scope": "rank-0 kernel buffers; not process RSS",
                            },
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                        allow_nan=False,
                    ),
                    flush=True,
                )
            if first_candidate is not None:
                first_candidate.destroy()
            if first_candidate_volume is not None:
                first_candidate_volume.destroy()
            for vector in (
                difference,
                candidate_full,
                reference_full,
                candidate_volume,
                reference_volume,
                source,
            ):
                if vector is not None:
                    vector.destroy()
            if candidate is not None:
                candidate.destroy()
            if reference is not None:
                reference.destroy()
            if side_system is not None:
                side_system.destroy()
            candidate = None
            reference = None
            side_system = None
            local_mesh = None
            source_before = None

    material_ids_by_rank = comm.allgather(sorted(all_material_ids))
    all_material_ids = {
        tag for rank_tags in material_ids_by_rank for tag in rank_tags
    }
    assert len(all_material_ids) >= 2
    assert comm.allreduce(has_nonzero_bloch_coefficient, op=MPI.LOR)
    assert float(cfg6.incident_theta_deg) != 0.0
    assert float(cfg6.incident_phi_deg) != 0.0


def test_task041_h1c_physical_galerkin_factor_and_alternation(h1c_fixture) -> None:
    data = h1c_fixture
    for side in ("bottom", "top"):
        p6 = data["p6"][side]
        p4 = data["p4"][side]
        owner = data["owners"][side]
        coarse_slaves = np.asarray(owner._coarse_slaves, dtype=np.int64)
        keys = {(int(mode.m), int(mode.n)) for mode in p6.modes}
        assert len(keys) >= 2
        assert any(m != 0 for m, _n in keys)
        q1 = p4.physical_action.action.context.input_vector.duplicate()
        q2 = q1.duplicate()
        p_q1 = None
        p_q2 = None
        p_q1_repeat = None
        fine_action = None
        coarse_from_adjoint = None
        coarse_action = None
        coarse_difference = None
        zero_q = None
        zero_rhs = None
        zero_solution = None
        try:
            _fill_algebraic(q1, coarse_slaves, 1.0)
            _fill_algebraic(q2, coarse_slaves, 4.0)
            q1_before = np.asarray(q1.getArray(readonly=True)).copy()
            p_q1 = owner.apply_primal(q1)
            p_q2 = owner.apply_primal(q2)
            p_q1_repeat = owner.apply_primal(q1)
            np.testing.assert_array_equal(q1.getArray(readonly=True), q1_before)
            np.testing.assert_allclose(
                p_q1.getArray(readonly=True),
                p_q1_repeat.getArray(readonly=True),
                atol=1.0e-12,
                rtol=1.0e-12,
            )
            assert not np.allclose(
                p_q1.getArray(readonly=True), p_q2.getArray(readonly=True)
            )

            fine_action = p_q1.duplicate()
            p6.action.mult(None, p_q1, fine_action)
            coarse_from_adjoint = owner.apply_adjoint(fine_action)
            coarse_action = p4.physical_action.matrix.createVecRight()
            p4.physical_action.matrix.mult(q1, coarse_action)
            coarse_difference = coarse_action.duplicate()
            coarse_action.copy(coarse_difference)
            coarse_difference.axpy(
                PETSc.ScalarType(-1.0),
                coarse_from_adjoint,
            )
            assert (
                coarse_difference.norm() / max(coarse_action.norm(), 1.0e-30)
                <= _STRICT_TOLERANCE
            )

            solution_snapshots = []
            for q in (q1, q2, q1):
                rhs = p4.create_rhs(q)
                solution = p4.matrix.createVecRight()
                try:
                    solve_audit = p4.solve_with_refinement(rhs, solution)
                    assert np.isfinite(solve_audit["relative_residual"])
                    assert solve_audit["relative_residual"] <= _STRICT_TOLERANCE
                    assert solve_audit["backsolve_count"] <= 3
                    assert solve_audit["refinement_count"] <= 2
                    assert solve_audit["same_factor_refinement"] == (
                        solve_audit["backsolve_count"] > 1
                    )
                    snapshot = np.asarray(
                        solution.getArray(readonly=True),
                        dtype=np.complex128,
                    ).copy()
                    if len(solution_snapshots) == 2:
                        np.testing.assert_allclose(
                            snapshot,
                            solution_snapshots[0],
                            atol=_STRICT_TOLERANCE,
                            rtol=_STRICT_TOLERANCE,
                        )
                    solution_snapshots.append(snapshot)
                finally:
                    solution.destroy()
                    rhs.destroy()

            zero_q = q1.duplicate()
            zero_q.set(0.0)
            zero_before = np.asarray(zero_q.getArray(readonly=True)).copy()
            zero_rhs = p4.create_rhs(zero_q)
            zero_solution = p4.matrix.createVecRight()
            zero_audit = p4.solve_with_refinement(zero_rhs, zero_solution)
            assert zero_audit["rhs_norm"] == 0.0
            assert zero_audit["residual_norm"] <= _STRICT_TOLERANCE
            assert zero_audit["relative_residual"] <= _STRICT_TOLERANCE
            np.testing.assert_array_equal(
                zero_q.getArray(readonly=True),
                zero_before,
            )
        finally:
            for vector in (p_q1, p_q2, p_q1_repeat):
                if vector is not None:
                    vector.destroy()
            if fine_action is not None:
                fine_action.destroy()
            if coarse_from_adjoint is not None:
                coarse_from_adjoint.destroy()
            if coarse_action is not None:
                coarse_action.destroy()
            if coarse_difference is not None:
                coarse_difference.destroy()
            if zero_q is not None:
                zero_q.destroy()
            if zero_rhs is not None:
                zero_rhs.destroy()
            if zero_solution is not None:
                zero_solution.destroy()
            q1.destroy()
            q2.destroy()

        diagnostics = p4.diagnostics
        assert diagnostics["factor_creation_count"] == 1
        assert diagnostics["research_factor"]["direct_factor_count"] == 1
        assert diagnostics["research_factor"]["solve_count"] >= 4


@pytest.fixture(scope="module")
def h1e_real_side_systems():
    """Build only the borrowed tiny-FE side systems for ownership coverage."""

    comm = MPI.COMM_WORLD
    cfg = _fixture_config(6, condensed=True)
    meshes = {}
    systems = {}
    try:
        for side in ("bottom", "top"):
            meshes[side] = build_hybrid_local_mesh(
                cfg,
                side,
                bottom_interface_z_nm=0.5,
                top_interface_z_nm=0.5,
                comm=comm,
            )
            systems[side] = assemble_hybrid_local_dtn_action_system(
                cfg,
                side,
                local_mesh_override=meshes[side],
                comm=comm,
            )
        yield systems
    finally:
        for system in systems.values():
            system.destroy()


def test_task041_v13_real_fe_condensed_sides_build_same_fixed_b_ldu(
    h1e_real_side_systems, tmp_path
) -> None:
    """Exercise V13 on real condensed P6 sides with analytic, non-QEP modes.

    The twelve fixture modes are assembled as complex FEM fields on the
    matched cross-section. They are deliberately small analytic test modes,
    not QEP modes and not evidence for the M400 pilot. The fresh-authority
    callback below only lets this unit fixture traverse the builder contract;
    its synthetic receipt is explicitly not a host/resource qualification.
    MPI2 ownership is exercised here when selected; the separate test349
    fixture remains the empty-owner branch evidence.
    """
    comm = MPI.COMM_WORLD
    import os
    import sys
    import time
    from pathlib import Path

    from benchmarks import task041_exact_side_workflow as exact_side

    test_body_started = time.perf_counter()

    evidence_root_text = (
        str(Path(tmp_path) / "v15-modal-evidence")
        if comm.rank == 0
        else None
    )
    evidence_root = Path(comm.bcast(evidence_root_text, root=0))
    test_source_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    fixture_binding = {
        "selector": (
            "test_task041_v13_real_fe_condensed_sides_build_same_fixed_b_ldu"
        ),
        "fixture": "registered tiny real condensed FE sides; synthetic analytic modes",
        "degree": 6,
        "mesh_cell_counts": [2, 2, 2],
        "mode_count_per_direction": 6,
        "authority_scope": "fixture_control_only_not_a_resource_qualification",
    }
    packet_manifest_sha256 = hashlib.sha256(
        json.dumps(fixture_binding, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    def modal_snapshot_callback(payload):
        kind = payload.get("snapshot_kind")
        if kind == "v15_capture_failure_rank":
            return exact_side._write_task041_v13_capture_failure_rank(
                evidence_root, payload, rank=int(comm.rank)
            )
        if kind == "v15_terminal_rank_vectors":
            return exact_side._write_task041_v13_terminal_rank_vectors(
                evidence_root, payload, rank=int(comm.rank)
            )
        return exact_side._write_task041_v13_modal_evidence_snapshot(
            evidence_root,
            payload,
            source_sha=test_source_sha,
            identity={**fixture_binding, "source_file_sha256": test_source_sha},
            packet_manifest_sha256=packet_manifest_sha256,
            consumer_binding=fixture_binding,
        )

    capture_opt_in = os.environ.get("TASK041_V13_CAPTURE_FIRST_TOP_Q_ROW", "")
    if capture_opt_in not in {"", "1"}:
        raise RuntimeError("first-top-Q capture opt-in must be unset or exactly 1")
    diagnostic_enabled = capture_opt_in == "1"
    capture_dir = os.environ.get("TASK041_V13_CAPTURE_DIR", "")
    if diagnostic_enabled and int(comm.size) != 1:
        raise RuntimeError("first-top-Q row capture is serial-only")
    if diagnostic_enabled and not capture_dir:
        raise RuntimeError("TASK041_V13_CAPTURE_DIR is required for capture")
    capture_output_dir = None
    if diagnostic_enabled:
        results_root = (Path(__file__).resolve().parents[2] / "results").resolve()
        capture_output_dir = Path(capture_dir).resolve()
        if not capture_output_dir.is_relative_to(results_root) or capture_output_dir.exists():
            raise RuntimeError("capture directory must be fresh under ignored results/")
    systems = h1e_real_side_systems
    cfg = systems["bottom"].cfg
    cross_section = build_matching_cross_section(cfg, "stage4_xy", comm=comm)
    spaces = build_cross_section_spaces(
        cross_section, transverse_degree=int(cfg.nedelec_degree)
    )
    mode_vectors: list[PETSc.Vec] = []
    inverses: dict[str, object] = {}
    p4_gate_records: dict[str, list[dict[str, object]]] = {
        "bottom": [],
        "top": [],
    }
    p4_apply_originals: dict[str, tuple[object, object]] = {}
    coupling = None
    original_operator = None
    original_action_context = None
    ldu = None
    inputs: list[PETSc.Vec] = []
    outputs: dict[str, PETSc.Vec] = {}
    authority_calls: list[dict[str, object]] = []

    beta = complex(
        np.sqrt(
            (cfg.k0 * complex(cfg.n_air)) ** 2
            - cfg.kx**2
            - cfg.ky**2
            + 0.0j
        )
    )
    positive_basis = None
    negative_basis = None

    def analytic_basis(direction: str) -> SimpleNamespace:
        modes = []
        for index in range(6):
            component = index // 3
            power = index % 3
            trace = fem.Function(spaces.transverse)

            def field(x, *, selected_component=component, selected_power=power):
                values = np.zeros((2, x.shape[1]), dtype=PETSc.ScalarType)
                phase = np.exp(1j * (cfg.kx * x[0] + cfg.ky * x[1]))
                axis = selected_component
                coordinate = np.asarray(x[axis], dtype=np.float64)
                period = (
                    cfg.period_x if selected_component == 0 else cfg.period_y
                )
                periodic_harmonic = np.exp(
                    2j * np.pi * selected_power * coordinate / period
                )
                values[selected_component, :] = (
                    (1.0 + 0.07j * (selected_power + 1))
                    * phase
                    * periodic_harmonic
                )
                return values

            trace.interpolate(field)
            trace.x.scatter_forward()
            mixed = fem.Function(spaces.mixed)
            mixed.x.array[:] = 0.0
            mixed.x.array[spaces.transverse_to_mixed] = trace.x.array
            mixed.x.scatter_forward()
            vector = mixed.x.petsc_vec.duplicate()
            mixed.x.petsc_vec.copy(vector)
            mode_vectors.append(vector)
            modes.append(
                SimpleNamespace(
                    beta=beta if direction == "forward" else -beta,
                    right=SimpleNamespace(right_full=vector),
                    left_full=vector,
                    direction=direction,
                    passive_branch_valid=True,
                )
            )
        return SimpleNamespace(modes=modes, groups=())

    try:
        positive_basis = analytic_basis("forward")
        negative_basis = analytic_basis("backward")
        coupling = build_hybrid_internal_mode_coupling(
            cfg,
            spaces,
            positive_basis,
            negative_basis,
            systems["bottom"],
            systems["top"],
            length_nm=1.0,
        )
        assert coupling.mode_count_per_direction == 6
        assert coupling.internal_equation_count == 12
        assert coupling.positive_projection_identity_error <= 1.0e-9
        assert np.linalg.matrix_rank(coupling.negative_trace_to_positive) == 6
        for side in ("bottom", "top"):
            inverses[side] = build_side_balanced_inverse(
                systems[side],
                detailed_timing=True,
                p4_inverse_backend="cell_condensed",
                support_policy="entity_closure",
            )
            assert inverses[side].diagnostics["p4_inverse_backend"] == (
                "cell_condensed"
            )
            assert (
                inverses[side]._owner_transfer.audit["support_policy"]
                == "entity_closure"
            )
            assert inverses[side].diagnostics["p4_factor_created_count"] == 1
            p4_factor = inverses[side]._p4_factor
            original_apply = p4_factor.apply
            p4_apply_originals[side] = (p4_factor, original_apply)

            def capture_real_p4_apply(
                *args,
                side_name=side,
                factor=p4_factor,
                apply=original_apply,
                **kwargs,
            ):
                result = apply(*args, **kwargs)
                p4_gate_records[side_name].append(
                    dict(factor.diagnostics["last_solve"])
                )
                return result

            p4_factor.apply = capture_real_p4_apply

        columns = [0, 1, 3, 5, 6, 7, 9, 11]
        roles = {
            str(column): [
                "head" if index in (0, 4) else "interior",
                (
                    "bottom_positive_unattenuated"
                    if column < 6
                    else "top_negative_unattenuated"
                ),
            ]
            for index, column in enumerate(columns)
        }
        contract = {
            "columns": columns,
            "mode_count_per_direction": 6,
            "roles": roles,
        }
        contract_sha256 = hashlib.sha256(
            json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

        def fixture_control_only_not_resource_qualification(
            phase: str, report: dict[str, object]
        ) -> dict[str, object]:
            projection = report["phase_memory_projection"]
            selected_phase = projection["selected_phase"]
            selected = projection["phase_reports"][selected_phase]
            known = list(selected["known_additional_bytes_by_rank"])
            temporary = list(selected["additional_temporary_bytes_by_rank"])
            replicated = list(selected["additional_replicated_bytes_by_rank"])
            additional = [
                known[rank] + temporary[rank] + replicated[rank]
                for rank in range(comm.size)
            ]
            request_sha256 = hashlib.sha256(
                json.dumps(
                    report,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode()
            ).hexdigest()
            # These values are only a deterministic test-control response.
            # They do not represent measured memory, an external gate, or a
            # production resource-admission result.
            payload = {
                "phase": phase,
                "request_sha256": request_sha256,
                "fixture_only": "not_a_resource_qualification",
            }
            receipt_sha256 = hashlib.sha256(
                json.dumps(
                    payload,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode()
            ).hexdigest()
            response = {
                "schema": "task041.v13.modal_builder_admission.v1",
                "phase": phase,
                "status": "pass",
                "decision": "continue",
                "request_sha256": request_sha256,
                "authority_receipt_payload": payload,
                "authority_receipt_sha256": receipt_sha256,
                "fresh_job_authority_bytes": 0,
                "cap_bytes": 1_000_000_000_000_000,
                "W_policy_reserve_bytes": 0,
                "additional_bytes_by_rank": additional,
                "additional_temporary_bytes_by_rank": temporary,
                "additional_replicated_bytes_by_rank": replicated,
                "selected_memory_phase": selected_phase,
                "selected_memory_phase_payload_bytes": sum(additional),
                "projected_B_plus_delta_plus_W_bytes": sum(additional),
                "external_resource_gates": {
                    "fixture_only_not_a_resource_qualification": True
                },
                "cost_assessment": {
                    "scope": "fixture_control_only",
                    "status": "not_a_resource_qualification",
                    "target_is_elapsed_stop": False,
                },
            }
            authority_calls.append(
                {
                    "phase": phase,
                    "response_scope": "fixture_only_not_a_resource_qualification",
                }
            )
            return response

        layout = HybridAugmentedLayout.build(
            systems["bottom"], systems["top"], coupling.internal_equation_count
        )
        original_action_started = time.perf_counter()
        original_operator, original_action_context = (
            create_hybrid_assembled_block_action(
                systems["bottom"], systems["top"], coupling
            )
        )
        original_action_setup_wall_seconds = (
            time.perf_counter() - original_action_started
        )
        pre_builder_side = {
            side: {
                "apply_count": int(inverse.diagnostics["apply_count"]),
                "total_iterations": int(
                    inverse.diagnostics["total_iterations"]
                ),
                "factor_solve_count": int(
                    inverse._p4_factor.inverse.solve_count
                ),
                "p4_gate_record_count": len(p4_gate_records[side]),
            }
            for side, inverse in inverses.items()
        }
        ldu_setup_started = time.perf_counter()
        ldu = create_side_balh_block_ldu_preconditioner(
            layout,
            systems["bottom"],
            systems["top"],
            coupling,
            inverses["bottom"],
            inverses["top"],
            sampled_columns=columns,
            sampled_column_roles=roles,
            sampled_column_contract_sha256=contract_sha256,
            fixed_h6_modal_gmres_research=True,
            modal_solver_policy=resolve_task041_modal_solver_policy(
                TASK041_V13_CONSISTENT_MODAL_POLICY_ID
            ),
            v13_fresh_authority_callback=(
                fixture_control_only_not_resource_qualification
            ),
            modal_snapshot_callback=modal_snapshot_callback,
        )
        fixed_b_s_b_setup_wall_seconds = time.perf_counter() - ldu_setup_started
        post_builder_side = {
            side: {
                "apply_count": int(inverse.diagnostics["apply_count"]),
                "total_iterations": int(
                    inverse.diagnostics["total_iterations"]
                ),
                "factor_solve_count": int(
                    inverse._p4_factor.inverse.solve_count
                ),
                "p4_gate_record_count": len(p4_gate_records[side]),
            }
            for side, inverse in inverses.items()
        }
        builder_p4_gates = {
            side: p4_gate_records[side][
                pre_builder_side[side]["p4_gate_record_count"] :
            ]
            for side in ("bottom", "top")
        }
        builder_action_work = {
            side: copy.deepcopy(
                (ldu.bottom_action if side == "bottom" else ldu.top_action)
                .audit["fixed_q_actual_work_cumulative"]
            )
            for side in ("bottom", "top")
        }
        builder_action_apply_count = {
            side: int(
                (ldu.bottom_action if side == "bottom" else ldu.top_action)
                .audit["apply_count"]
            )
            for side in ("bottom", "top")
        }
        ldu.bind_v13_original_global_operator(original_operator)
        assert ldu.bottom_action is ldu.action_modal_schur_system.bottom_action
        assert ldu.top_action is ldu.action_modal_schur_system.top_action
        assert ldu.bottom_action._side_inverse is inverses["bottom"]
        assert ldu.top_action._side_inverse is inverses["top"]
        modal_system = ldu.action_modal_schur_system
        modal_audit = modal_system.diagnostics
        assert modal_audit["modal_schur_column_count"] == 12
        assert modal_audit["modal_ksp_handle_count"] == 0
        assert modal_audit["modal_ksp_solve_count"] == 0
        assert modal_system.build_audit[
            "sample_columns_written_directly_to_final_matrix"
        ] == columns
        assert modal_system.build_audit["remaining_columns_applied_once"] == [
            2,
            4,
            8,
            10,
        ]
        assert [row["phase"] for row in authority_calls] == [
            "before_dense_allocation",
            "after_eight_columns",
        ]
        assert all(
            row["response_scope"] == "fixture_only_not_a_resource_qualification"
            for row in authority_calls
        )

        def make_input(seed: float) -> PETSc.Vec:
            vector = layout.create_vector()
            first, last = (int(value) for value in vector.getOwnershipRange())
            rows = np.arange(first, last, dtype=np.float64)
            vector.getArray()[:] = np.asarray(
                seed + 0.017 * rows + 1j * (0.23 - 0.011 * rows),
                dtype=PETSc.ScalarType,
            )
            vector.assemble()
            inputs.append(vector)
            return vector

        x = make_input(0.2)
        y = make_input(-0.35)
        x_values = np.asarray(x.getArray(readonly=True)).copy()
        y_values = np.asarray(y.getArray(readonly=True)).copy()
        alpha = 0.3 - 0.4j
        combined = x.duplicate()
        x.copy(combined)
        combined.axpy(PETSc.ScalarType(1.0), y)
        scaled = x.duplicate()
        x.copy(scaled)
        scaled.scale(PETSc.ScalarType(alpha))
        repeated_x = x.copy()
        zero = layout.create_vector()
        zero.set(0.0)
        zero.assemble()
        near_zero = x.copy()
        near_zero.scale(PETSc.ScalarType(1.0e-12))
        inputs.extend((combined, scaled, repeated_x, zero, near_zero))

        v15_row_contract_id = "task041.v15.original_modal_row.terms_backward.v1"

        def assert_v15_row_gate_passed(row_gate: dict[str, object]) -> None:
            metrics = row_gate["metrics"]
            assert row_gate["status"] == "passed"
            assert row_gate["schema"] == v15_row_contract_id
            assert row_gate["contract_id"] == v15_row_contract_id
            assert metrics["contract_id"] == v15_row_contract_id
            assert metrics["tolerance"] == 1.0e-10
            assert metrics["status"] == "passed"
            eta_terms_inf = metrics["eta_terms_inf"]
            assert isinstance(eta_terms_inf, (int, float))
            assert np.isfinite(float(eta_terms_inf))
            assert float(eta_terms_inf) <= 1.0e-10

        def apply_full_pc(name: str, source: PETSc.Vec) -> PETSc.Vec:
            before = np.asarray(source.getArray(readonly=True)).copy()
            target = layout.create_vector()
            if diagnostic_enabled:
                try:
                    ldu.apply(None, source, target)
                    np.testing.assert_array_equal(
                        np.asarray(source.getArray(readonly=True)), before
                    )
                    row_gate = ldu.action_modal_schur_system.diagnostics[
                        "last_original_modal_row"
                    ]
                    assert_v15_row_gate_passed(row_gate)
                except BaseException as error:
                    try:
                        capture_state["source_unchanged_on_failure"] = bool(
                            np.array_equal(
                                np.asarray(source.getArray(readonly=True)), before
                            )
                        )
                    except BaseException as source_check_error:  # noqa: BLE001
                        capture_state["source_unchanged_check_error"] = type(
                            source_check_error
                        ).__name__
                        capture_state["source_unchanged_check_error_message"] = (
                            bounded_error_message(source_check_error)
                        )
                    try:
                        target.destroy()
                    except BaseException as cleanup_error:  # noqa: BLE001
                        capture_state["target_cleanup_error"] = type(cleanup_error).__name__
                        capture_state["target_cleanup_error_message"] = (
                            bounded_error_message(cleanup_error)
                        )
                    capture_state["full_pc_exception"] = exception_record(error)
                    raise
            else:
                ldu.apply(None, source, target)
                np.testing.assert_array_equal(
                    np.asarray(source.getArray(readonly=True)), before
                )
                row_gate = ldu.action_modal_schur_system.diagnostics[
                    "last_original_modal_row"
                ]
                assert_v15_row_gate_passed(row_gate)
            outputs[name] = target
            return target

        capture_state: dict[str, object] = {
            "schema": "task041.v13.first_top_q_row_capture.v1",
            "status": "not_reached",
            "enabled": diagnostic_enabled,
            "capture_byte_limit": 1 << 20,
            "capture_byte_limit_scope": (
                "logical captured array bytes plus serialized row artifact bytes; "
                "the final manifest uses a 4096-byte reserve; excludes Python "
                "object overhead and transient serialization memory"
            ),
        }

        def exception_record(error: BaseException) -> dict[str, str]:
            return {
                "type": type(error).__name__,
                "message": bounded_error_message(error),
            }

        def bounded_error_message(error: BaseException, limit: int = 256) -> str:
            try:
                message = str(error)
            except BaseException as message_error:  # noqa: BLE001
                message = f"<message unavailable: {type(message_error).__name__}>"
            return message[:limit]

        def vector_binding(vector: PETSc.Vec) -> dict[str, object]:
            values = np.ascontiguousarray(vector.getArray(readonly=True))
            return {
                "global_size": int(vector.getSize()),
                "local_size": int(vector.getLocalSize()),
                "ownership_range": [int(v) for v in vector.getOwnershipRange()],
                "dtype": str(values.dtype),
                "nbytes": int(values.nbytes),
                "sha256": hashlib.sha256(values.view(np.uint8)).hexdigest(),
            }

        def complex_pairs(values: np.ndarray) -> list[list[float]]:
            return [
                [float(v.real), float(v.imag)]
                for v in np.asarray(values, dtype=np.complex128).reshape(-1)
            ]

        def capture_worst_row(**packet: object) -> dict[str, object]:
            """Capture one complete serial row group; never raise into the hook."""
            try:
                ids = np.asarray(packet["ids"])
                values = np.asarray(packet["values"])
                ranks = np.asarray(packet["source_ranks"])
                owner = int(packet["owner_rank"])
                if (
                    int(comm.size) != 1
                    or ids.dtype != np.dtype(np.uint64)
                    or values.dtype != np.dtype(np.complex128)
                    or ranks.dtype != np.dtype(np.int32)
                    or ids.ndim != 1
                    or values.shape != ids.shape
                    or ranks.shape != ids.shape
                ):
                    raise ValueError("serial owner packet shape or dtype is unsupported")

                worst = None
                start = 0
                while start < ids.size:
                    stop = start + 1
                    while stop < ids.size and ids[stop] == ids[start]:
                        stop += 1
                    reference = next(
                        (i for i in range(start, stop) if int(ranks[i]) == owner),
                        None,
                    )
                    if reference is None:
                        raise ValueError("row has no canonical owner candidate")
                    reference_value = complex(values[reference])
                    row_differences = np.abs(values[start:stop] - reference_value)
                    if not np.isfinite(row_differences).all():
                        raise ValueError("row candidate defect is non-finite")
                    row_max = float(np.max(row_differences))
                    row_arg = start + int(np.argmax(row_differences))
                    candidate = (row_max, int(ids[start]), start, stop, reference, row_arg)
                    if worst is None or (
                        -candidate[0], candidate[1], candidate[5]
                    ) < (-worst[0], worst[1], worst[5]):
                        worst = candidate
                    start = stop
                if worst is None:
                    raise ValueError("owner packet is empty")
                defect, row_id, first, last, reference, worst_arg = worst
                count = int(last - first)
                row_summary = {
                    "row_id": row_id,
                    "candidate_count": count,
                    "reference_position": reference - first,
                    "reference_value": [
                        float(values[reference].real), float(values[reference].imag)
                    ],
                    "worst_candidate_position": worst_arg - first,
                    "measured_absolute_defect": defect,
                    "matches_previous_scalar": defect == 1.3520610761878294e-11,
                    "limit": 1.0e-11,
                }
                capture_state["selected_row_summary"] = row_summary

                candidate_array_bytes = count * 28  # uint64 IDs, complex128 values, int32 ranks
                preliminary = candidate_array_bytes + 65536 + count * 2400
                if preliminary > (1 << 20):
                    capture_state.update(
                        status="capture_incomplete",
                        reason="candidate_group_exceeds_1MiB_bound",
                        candidate_array_nbytes=candidate_array_bytes,
                        total_capture_upper_bound=preliminary,
                    )
                    return {"status": "capture_incomplete"}

                emitted_ids = np.asarray(packet["emitted_ids"])
                emitted_values = np.asarray(packet["emitted_values"])
                emitted_positions = [
                    i for i, value in enumerate(emitted_ids) if int(value) == row_id
                ]
                if len(emitted_positions) != count:
                    raise ValueError("selected row does not map to all emissions")

                transfer = packet["transfer"]
                origin_specs = []
                origin_array_bytes = 0
                origin_scalars = 0
                offset = 0
                for record_index, record in enumerate(transfer._records):
                    for local_position, value in enumerate(record["fine_global"]):
                        if int(value) != row_id:
                            continue
                        packet_position = offset + local_position
                        if packet_position != emitted_positions[len(origin_specs)]:
                            raise ValueError("record and packet order do not agree")
                        if "compact_transfer" in record:
                            raise ValueError("compact transfer row cannot be captured exactly")
                        coarse_local = np.asarray(record["coarse_local"])
                        coarse_global = np.asarray(record["coarse_global"])
                        matrix_row = np.asarray(record["matrix"][local_position])
                        work_values = np.asarray(
                            transfer._coarse_work.x.array[coarse_local]
                        )
                        origin_array_bytes += sum(
                            array.nbytes
                            for array in (coarse_local, coarse_global, matrix_row, work_values)
                        )
                        origin_scalars += 3 + 6 * int(coarse_local.size)
                        origin_specs.append(
                            (record_index, local_position, packet_position)
                        )
                    offset += len(record["fine_global"])
                if len(origin_specs) != count:
                    raise ValueError("candidate origin count is incomplete")

                arrays_nbytes = candidate_array_bytes + origin_array_bytes
                json_upper = 65536 + count * 2048 + (5 * count + origin_scalars) * 64
                if arrays_nbytes + json_upper + 4096 > (1 << 20):
                    capture_state.update(
                        status="capture_incomplete",
                        reason="row_with_origins_exceeds_1MiB_bound",
                        candidate_count=count,
                        array_nbytes=arrays_nbytes,
                        total_capture_upper_bound=arrays_nbytes + json_upper + 4096,
                    )
                    return {"status": "capture_incomplete"}

                group_values = values[first:last].copy()
                if not np.array_equal(group_values, emitted_values[emitted_positions]):
                    raise ValueError("emitted values do not preserve packet order")
                origins = []
                for record_index, local_position, packet_position in origin_specs:
                    record = transfer._records[record_index]
                    coarse_local = np.asarray(record["coarse_local"])
                    coarse_global = np.asarray(record["coarse_global"])
                    origins.append(
                        {
                            "record": record_index,
                            "local_position": local_position,
                            "packet_position": packet_position,
                            "fine_local": int(record["fine_local"][local_position]),
                            "fine_global": row_id,
                            "authority": bool(record["authority"][local_position]),
                            "coarse_local": coarse_local.tolist(),
                            "coarse_global": coarse_global.tolist(),
                            "matrix_row": complex_pairs(record["matrix"][local_position]),
                            "coarse_work_input": complex_pairs(
                                transfer._coarse_work.x.array[coarse_local]
                            ),
                        }
                    )
                attempts = {
                    name: (
                        {
                            "status": "exception",
                            "type": str(attempt["exception_type"])[:128],
                            "message": bounded_error_message(
                                attempt["exception_message"]
                            ),
                        }
                        if "exception_type" in attempt
                        else {
                            "status": "returned",
                            "global_defect": float(attempt["result"][2]),
                            "packet_rows": int(attempt["result"][3]),
                        }
                    )
                    for name, attempt in packet["attempts"].items()
                }
                source = packet["source"]
                payload = {
                    "rank": 0,
                    "size": 1,
                    "selected_variant": transfer.execution_variant,
                    "support_policy": transfer.audit["support_policy"],
                    "local_transfer": {
                        key: transfer.local_transfer.audit[key]
                        for key in (
                            "pair_fine_to_coarse",
                            "shape",
                            "fine_lagrange_variant",
                            "coarse_lagrange_variant",
                            "support_policy",
                        )
                    },
                    "fine_ranges": [list(map(int, r)) for r in transfer.fine_ranges],
                    "coarse_ranges": [list(map(int, r)) for r in transfer.coarse_ranges],
                    "source_layout_sha256": vector_binding(source),
                    "outer_x_layout_sha256": capture_state["outer_x"],
                    "row_summary": row_summary,
                    "packet_group_range": [first, last],
                    "packet_order": "row ID, source rank, stable local record order",
                    "candidate_ids_uint64": ids[first:last].tolist(),
                    "candidate_values_complex128_pairs": complex_pairs(group_values),
                    "candidate_source_ranks_int32": ranks[first:last].tolist(),
                    "candidate_origins": origins,
                    "resolver_attempts": attempts,
                    "hook_row_hints": {
                        "max_local_rows": int(transfer._diagnostic_context["max_local_rows"]),
                        "max_global_rows": int(transfer._diagnostic_context["max_global_rows"]),
                        "enforced": False,
                    },
                    "extra_hook_work": (
                        "packet precheck; ordinary selected resolver once; diagnostic "
                        "alternate resolver once (one extra resolver pass); callback "
                        "agreement collective; one owner-packet scan"
                    ),
                    "array_nbytes": arrays_nbytes,
                    "capture_byte_limit": 1 << 20,
                    "capture_byte_limit_scope": capture_state[
                        "capture_byte_limit_scope"
                    ],
                }
                encoded = json.dumps(
                    payload, sort_keys=True, separators=(",", ":"), allow_nan=False
                ).encode()
                if arrays_nbytes + len(encoded) + 4096 > (1 << 20):
                    capture_state.update(
                        status="capture_incomplete",
                        reason="serialized_row_exceeds_1MiB_bound",
                        candidate_count=count,
                        array_nbytes=arrays_nbytes,
                        total_capture_bytes=arrays_nbytes + len(encoded) + 4096,
                    )
                    return {"status": "capture_incomplete"}
                capture_state.update(
                    status="capture_complete",
                    candidate_count=count,
                    array_nbytes=arrays_nbytes,
                    serialized_payload_bytes=len(encoded),
                    total_capture_upper_bound=arrays_nbytes + len(encoded) + 4096,
                    payload=payload,
                )
                return {"status": "capture_complete"}
            except BaseException as error:  # noqa: BLE001
                capture_state.update(
                    status="capture_incomplete",
                    reason="capture_callback_error",
                    capture_error_type=type(error).__name__,
                    capture_error_message=bounded_error_message(error),
                )
                return {"status": "capture_incomplete"}

        def persist_capture(outcome: str, error: BaseException | None = None) -> None:
            if capture_state["status"] == "not_reached":
                capture_state["status"] = "capture_not_reached"
            if error is not None:
                capture_state["original_exception"] = exception_record(error)
            capture_state["outcome"] = outcome
            capture_state["transfer_diagnostic"] = (
                inverses["top"]._owner_transfer.last_diagnostic
            )
            row = json.dumps(
                capture_state, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
            logical_arrays = int(capture_state.get("array_nbytes", 0))
            if (
                (logical_arrays if capture_state.get("payload") is not None else 0)
                + len(row)
                + 4096
                > (1 << 20)
            ):
                capture_state.update(
                    status="capture_incomplete",
                    reason="final_envelope_exceeds_1MiB_bound",
                    payload=None,
                    discarded_payload_array_nbytes=logical_arrays,
                    array_nbytes=0,
                    serialized_payload_bytes=0,
                )
                logical_arrays = 0
                row = json.dumps(
                    capture_state, sort_keys=True, separators=(",", ":"), allow_nan=False
                ).encode()
            if len(row) + 4096 > (1 << 20) or capture_output_dir is None:
                raise ValueError("capture summary cannot be safely persisted")
            capture_output_dir.mkdir(parents=True, exist_ok=False)
            row_path = capture_output_dir / "rank0_transfer_row_capture.json"
            with row_path.open("xb") as stream:
                stream.write(row)
            manifest = json.dumps(
                {
                    "path": row_path.name,
                    "bytes": len(row),
                    "sha256": hashlib.sha256(row).hexdigest(),
                    "status": capture_state["status"],
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
            if logical_arrays + len(row) + len(manifest) > (1 << 20):
                raise ValueError("capture files exceed 1 MiB")
            with (capture_output_dir / "manifest.json").open("xb") as stream:
                stream.write(manifest)

        if diagnostic_enabled:
            capture_state["outer_x"] = vector_binding(x)
            top_transfer = inverses["top"]._owner_transfer
            if top_transfer.execution_variant != "legacy":
                raise RuntimeError("diagnostic requires the existing legacy resolver")
            original_apply = top_transfer.apply_primal
            armed = True

            def capture_first_top_q(source: PETSc.Vec, *, timing=None):
                nonlocal armed
                if not armed:
                    return original_apply(source, timing=timing)
                armed = False
                capture_state["first_top_transfer_entered"] = True
                with top_transfer.diagnostic_context(capture_worst_row):
                    return original_apply(source, timing=timing)

            top_transfer.apply_primal = capture_first_top_q
            try:
                fx = apply_full_pc("x", x)
            except BaseException as error:
                try:
                    persist_capture("first_full_pc_failed", error)
                except BaseException as write_error:  # noqa: BLE001
                    try:
                        error.add_note(
                            "capture persistence failed without replacing original: "
                            f"{type(write_error).__name__}: "
                            f"{bounded_error_message(write_error)}"
                        )
                    except BaseException as note_error:  # noqa: BLE001
                        capture_state["write_error_note_failure"] = type(note_error).__name__
                raise
            else:
                try:
                    persist_capture("first_full_pc_returned")
                except Exception as error:  # noqa: BLE001
                    pytest.fail(f"capture persistence failed: {type(error).__name__}: {error}")
                pytest.skip("diagnostic stops after the first full-PC action")
            finally:
                top_transfer.apply_primal = original_apply
        else:
            fx = apply_full_pc("x", x)
        fy = apply_full_pc("y", y)
        fxy = apply_full_pc("x_plus_y", combined)
        falpha = apply_full_pc("alpha_x", scaled)
        frepeat = apply_full_pc("repeat_x", repeated_x)
        fzero = apply_full_pc("zero", zero)
        fnear = apply_full_pc("near_zero", near_zero)

        def assert_linear_relation(
            name: str,
            actual: PETSc.Vec,
            terms: tuple[tuple[complex, PETSc.Vec], ...],
            *,
            tolerance: float = 1.0e-10,
        ) -> dict[str, float]:
            expected = actual.duplicate()
            expected.set(0.0)
            for coefficient, vector in terms:
                expected.axpy(PETSc.ScalarType(coefficient), vector)
            difference = actual.duplicate()
            actual.copy(difference)
            difference.axpy(PETSc.ScalarType(-1.0), expected)
            try:
                absolute_error = float(difference.norm())
                scale = float(expected.norm())
                scaled_error = (
                    absolute_error / scale
                    if scale > 0.0
                    else (0.0 if absolute_error == 0.0 else float("inf"))
                )
                error_record = {
                    "absolute_error": absolute_error,
                    "reference_scale": scale,
                    "scaled_error": scaled_error,
                    "scaled_error_limit": tolerance,
                    "absolute_error_limit": tolerance * scale,
                }
                linearity_records[name] = error_record
                assert (
                    np.isfinite(absolute_error)
                    and np.isfinite(scaled_error)
                    and absolute_error <= tolerance * scale
                    and scaled_error <= tolerance
                )
                return error_record
            finally:
                difference.destroy()
                expected.destroy()

        linearity_records: dict[str, dict[str, float]] = {}
        assert_linear_relation("x_plus_y", fxy, ((1.0, fx), (1.0, fy)))
        assert_linear_relation("alpha_x", falpha, ((alpha, fx),))
        assert_linear_relation("repeat_x", frepeat, ((1.0, fx),))
        assert float(fzero.norm()) == 0.0
        near_zero_record = assert_linear_relation(
            "near_zero", fnear, ((1.0e-12, fx),)
        )
        assert near_zero_record["reference_scale"] > 0.0
        assert near_zero_record["absolute_error"] <= near_zero_record[
            "absolute_error_limit"
        ]
        assert near_zero_record["scaled_error"] <= 1.0e-10
        np.testing.assert_array_equal(
            np.asarray(x.getArray(readonly=True)), x_values
        )
        np.testing.assert_array_equal(
            np.asarray(y.getArray(readonly=True)), y_values
        )

        for side, inverse in inverses.items():
            action = ldu.bottom_action if side == "bottom" else ldu.top_action
            work = action.audit["fixed_q_actual_work_cumulative"]
            p4_solve_count = int(inverse._p4_factor.inverse.solve_count)
            built_work = builder_action_work[side]
            builder_solve_delta = (
                post_builder_side[side]["factor_solve_count"]
                - pre_builder_side[side]["factor_solve_count"]
            )
            outer_solve_delta = (
                p4_solve_count - post_builder_side[side]["factor_solve_count"]
            )
            cumulative_solve_delta = (
                p4_solve_count - pre_builder_side[side]["factor_solve_count"]
            )
            outer_apply_delta = (
                int(action.audit["apply_count"])
                - builder_action_apply_count[side]
            )
            builder_apply_count = builder_action_apply_count[side]
            assert builder_solve_delta >= 0
            assert outer_solve_delta >= 0
            assert outer_apply_delta >= 0
            assert cumulative_solve_delta == builder_solve_delta + outer_solve_delta
            assert built_work["successful_factor_solve_delta_total"] == (
                builder_solve_delta
            )
            assert built_work["mathematical_correction_steps_requested"] == (
                2 * builder_apply_count
            )
            assert work["successful_factor_solve_delta_total"] == (
                cumulative_solve_delta
            )
            assert (
                work["successful_factor_solve_delta_total"]
                - built_work["successful_factor_solve_delta_total"]
                == outer_solve_delta
            )
            assert (
                work["mathematical_correction_steps_requested"]
                - built_work["mathematical_correction_steps_requested"]
                == 2 * outer_apply_delta
            )
            assert work["mathematical_correction_steps_requested"] == (
                2 * int(action.audit["apply_count"])
            )
            assert (
                work["successful_q_audit_count"]
                - built_work["successful_q_audit_count"]
                == 2 * outer_apply_delta
            )
            assert (
                work["mathematical_correction_steps_completed_with_valid_q_audit"]
                - built_work[
                    "mathematical_correction_steps_completed_with_valid_q_audit"
                ]
                == 2 * outer_apply_delta
            )
            assert work["q_attempts_missing_complete_audit"] == built_work[
                "q_attempts_missing_complete_audit"
            ] == 0
            assert work[
                "mathematical_correction_steps_completed_with_valid_q_audit"
            ] == work["successful_q_audit_count"]
            assert work["mathematical_correction_steps_requested"] == work[
                "successful_q_audit_count"
            ]
            assert work["q_attempts_missing_complete_audit"] == 0
            assert work["failed_q_attempt_count"] == 0
            assert sum(
                int(gate["backsolve_count"]) for gate in builder_p4_gates[side]
            ) == builder_solve_delta
            post_builder_p4_gates = p4_gate_records[side][
                post_builder_side[side]["p4_gate_record_count"] :
            ]
            assert sum(
                int(gate["backsolve_count"]) for gate in post_builder_p4_gates
            ) == outer_solve_delta
            for p4_gate in p4_gate_records[side]:
                assert p4_gate["physical_gate_passed"] is True
                assert p4_gate["augmented_gate_passed"] is True
                assert p4_gate["residual_tolerance"] == 1.0e-10
                assert p4_gate["physical_relative_residual"] <= 1.0e-10
                assert p4_gate["relative_residual"] <= 1.0e-10
            for step_name in ("initial", "correction"):
                step = work["factor_solve_deltas_by_step"][step_name]
                built_step = built_work["factor_solve_deltas_by_step"][step_name]
                assert step["audited_q_count"] == work["successful_q_audit_count"]
                assert (
                    step["audited_q_count"] - built_step["audited_q_count"]
                    == 2 * outer_apply_delta
                )
                assert (
                    step["factor_solve_delta_total"]
                    - built_step["factor_solve_delta_total"]
                    >= 0
                )
                assert step["direct_zero_status_audited_q_count"] + step[
                    "direct_zero_status_missing_q_count"
                ] == step["audited_q_count"]
                assert step["direct_zero_status_missing_q_count"] == 0
                assert (
                    step["direct_zero_status_audited_q_count"]
                    - built_step["direct_zero_status_audited_q_count"]
                    == 2 * outer_apply_delta
                )
                assert (
                    step["direct_zero_status_missing_q_count"]
                    - built_step["direct_zero_status_missing_q_count"]
                    == 0
                )
                assert 0 <= step["direct_zero_count"] <= step[
                    "direct_zero_status_audited_q_count"
                ]
            assert sum(
                work["factor_solve_deltas_by_step"][name][
                    "factor_solve_delta_total"
                ]
                - built_work["factor_solve_deltas_by_step"][name][
                    "factor_solve_delta_total"
                ]
                for name in ("initial", "correction")
            ) == outer_solve_delta
            p4_last_solve = inverse._p4_factor.diagnostics["last_solve"]
            assert p4_last_solve["physical_gate_passed"] is True
            assert p4_last_solve["augmented_gate_passed"] is True
            assert p4_last_solve["residual_tolerance"] == 1.0e-10
            current = inverse.diagnostics
            assert current["apply_count"] == pre_builder_side[side]["apply_count"] == 0
            assert current["total_iterations"] == pre_builder_side[side]["total_iterations"] == 0
            assert post_builder_side[side]["apply_count"] == pre_builder_side[side]["apply_count"]
            assert post_builder_side[side]["total_iterations"] == pre_builder_side[side]["total_iterations"]
            assert current["p4_factor_live"] == 1
            assert current["nested_iterative_ksp_count"] == 1
        final_modal_audit = ldu.action_modal_schur_system.diagnostics
        assert final_modal_audit["modal_ksp_handle_count"] == 0
        assert final_modal_audit["modal_ksp_solve_count"] == 0

        # Exercise the real original MatPython A and the real V13 LDU as a
        # right-preconditioned FGMRES solve.  This is a tiny registered FE
        # fixture, not the M400 warm route or a host resource qualification.
        exact_solution = layout.create_vector()
        rhs = layout.create_vector()
        solution = layout.create_vector()
        true_residual = layout.create_vector()
        monitor_solution_scratch = original_operator.createVecRight()
        monitor_residual_scratch = original_operator.createVecLeft()
        inputs.extend((exact_solution, rhs))
        outputs["tiny_fgmres_solution"] = solution
        outputs["tiny_fgmres_true_residual"] = true_residual
        outputs["tiny_fgmres_monitor_solution_scratch"] = (
            monitor_solution_scratch
        )
        outputs["tiny_fgmres_monitor_residual_scratch"] = (
            monitor_residual_scratch
        )
        first, last = (int(value) for value in exact_solution.getOwnershipRange())
        global_rows = np.arange(first, last, dtype=np.float64)
        exact_solution.getArray()[:] = np.asarray(
            0.8
            + 0.003 * global_rows
            + 1j * (0.2 - 0.007 * global_rows),
            dtype=PETSc.ScalarType,
        )
        exact_solution.assemble()
        original_operator.mult(exact_solution, rhs)
        ksp = PETSc.KSP().create(comm)
        missing_instance_apply = object()
        prior_instance_apply = vars(ldu).get("apply", missing_instance_apply)
        ldu_apply_wrapper_installed = False
        apply_restore_error: dict[str, str] | None = None
        ksp_destroy_error: dict[str, str] | None = None
        ksp_destroy_primary: BaseException | None = None

        def exception_message(error: BaseException) -> str:
            try:
                return str(error)[:320]
            except BaseException as render_error:  # noqa: BLE001 - evidence is secondary
                return f"<message unavailable: {type(render_error).__name__}>"

        try:
            ksp.setOperators(original_operator)
            ksp.setType(PETSc.KSP.Type.FGMRES)
            ksp.setPCSide(PETSc.PC.Side.RIGHT)
            pc = ksp.getPC()
            pc.setType(PETSc.PC.Type.PYTHON)
            pc.setPythonContext(ldu)
            max_iterations = min(600, max(4, int(layout.global_size)))
            ksp.setTolerances(rtol=5.0e-9, atol=0.0, max_it=max_iterations)
            restart = 30
            ksp.setGMRESRestart(restart)
            ksp.setInitialGuessNonzero(False)

            def finite_json_number(value: float) -> float | dict[str, object]:
                number = float(value)
                if np.isfinite(number):
                    return number
                label = "NaN" if np.isnan(number) else ("+Inf" if number > 0 else "-Inf")
                return {"value": None, "nonfinite": label}

            def json_safe(value: object) -> object:
                if isinstance(value, np.generic):
                    value = value.item()
                if value is None or isinstance(value, (str, bool, int)):
                    return value
                if isinstance(value, float):
                    return finite_json_number(value)
                if isinstance(value, (tuple, list)):
                    return [json_safe(item) for item in value]
                if isinstance(value, dict):
                    return {
                        str(key): json_safe(item)
                        for key, item in value.items()
                    }
                return {
                    "status": "unsupported",
                    "python_type": type(value).__name__,
                }

            def read_ksp_value(owner, getter_name: str) -> dict[str, object]:
                getter = getattr(owner, getter_name, None)
                if not callable(getter):
                    return {"status": "unsupported", "getter": getter_name}
                try:
                    value = getter()
                except Exception as getter_error:  # noqa: BLE001 - diagnostic read only
                    return {
                        "status": "read_failed",
                        "getter": getter_name,
                        "error_type": type(getter_error).__name__,
                        "error_message": str(getter_error)[:240],
                    }
                serialized_value = json_safe(value)
                result = {"status": "read", "value": serialized_value}
                if (
                    isinstance(serialized_value, dict)
                    and serialized_value.get("status") == "unsupported"
                ):
                    result["value_display"] = str(value)
                return result

            tolerances = read_ksp_value(ksp, "getTolerances")
            if tolerances.get("status") == "read":
                tolerance_values = tolerances.get("value")
                if isinstance(tolerance_values, list) and len(tolerance_values) == 4:
                    tolerances["named_values"] = dict(
                        zip(
                            ("rtol", "atol", "divtol", "max_it"),
                            tolerance_values,
                            strict=True,
                        )
                    )
                else:
                    tolerances["status"] = "unsupported_shape"
            convergence_getter = getattr(ksp, "getConvergenceTest", None)
            if not callable(convergence_getter):
                convergence_test = {
                    "status": "unsupported",
                    "reason": "petsc4py exposes no read-only convergence-test getter",
                }
            else:
                try:
                    convergence_value = convergence_getter()
                    if isinstance(convergence_value, tuple):
                        convergence_value = convergence_value[0]
                    if callable(convergence_value):
                        convergence_test = {
                            "status": "read",
                            "callable_module": getattr(
                                convergence_value, "__module__", None
                            ),
                            "callable_name": getattr(
                                convergence_value,
                                "__qualname__",
                                getattr(convergence_value, "__name__", None),
                            ),
                            "source": "petsc4py KSP.getConvergenceTest",
                        }
                    else:
                        convergence_test = {
                            "status": "unsupported",
                            "returned_type": type(convergence_value).__name__,
                        }
                except Exception as getter_error:  # noqa: BLE001 - diagnostic read only
                    convergence_test = {
                        "status": "read_failed",
                        "error_type": type(getter_error).__name__,
                        "error_message": str(getter_error)[:240],
                    }
            relevant_option_names = (
                "ksp_type",
                "ksp_pc_side",
                "ksp_rtol",
                "ksp_atol",
                "ksp_divtol",
                "ksp_max_it",
                "ksp_gmres_restart",
                "ksp_initial_guess_nonzero",
                "ksp_norm_type",
            )
            try:
                options_getter = getattr(PETSc.Options(), "getAll", None)
                if not callable(options_getter):
                    relevant_options: dict[str, object] = {
                        "status": "unsupported"
                    }
                else:
                    all_options = options_getter()
                    relevant_options = {
                        "status": "read",
                        "keys": {
                            name: json_safe(all_options[name])
                            if name in all_options
                            else {"status": "not_set_in_options_db"}
                            for name in relevant_option_names
                        },
                    }
            except Exception as options_error:  # noqa: BLE001 - diagnostic read only
                relevant_options = {
                    "status": "read_failed",
                    "error_type": type(options_error).__name__,
                    "error_message": str(options_error)[:240],
                }
            thread_environment = {
                name: os.environ.get(name, "not_set")
                for name in (
                    "OMP_NUM_THREADS",
                    "OPENBLAS_NUM_THREADS",
                    "MKL_NUM_THREADS",
                    "BLIS_NUM_THREADS",
                    "NUMEXPR_NUM_THREADS",
                    "VECLIB_MAXIMUM_THREADS",
                )
            }
            thread_environment["PETSC_OPTIONS"] = (
                "present_not_exported"
                if os.environ.get("PETSC_OPTIONS")
                else "not_set"
            )
            ksp_configuration = {
                "requested": {
                    "type": "fgmres",
                    "pc_side": "right",
                    "rtol": 5.0e-9,
                    "atol": 0.0,
                    "max_it": max_iterations,
                    "restart": restart,
                    "initial_guess_nonzero": False,
                    "norm_type": "existing_default_unchanged",
                },
                "readback": {
                    "type": read_ksp_value(ksp, "getType"),
                    "pc_side": read_ksp_value(ksp, "getPCSide"),
                    "pc_type": read_ksp_value(pc, "getType"),
                    "pc_context": {
                        "python_type": type(pc.getPythonContext()).__name__,
                        "same_ldu_object": pc.getPythonContext() is ldu,
                    },
                    "tolerances": tolerances,
                    "restart": read_ksp_value(ksp, "getGMRESRestart"),
                    "initial_guess_nonzero": read_ksp_value(
                        ksp, "getInitialGuessNonzero"
                    ),
                    "norm_type": read_ksp_value(ksp, "getNormType"),
                    "convergence_test": convergence_test,
                },
                "relevant_petsc_options": relevant_options,
                "limited_environment": thread_environment,
            }

            ksp_monitor_samples: list[dict[str, object]] = []
            ksp_monitor_errors: list[dict[str, object]] = []
            solve_started_monotonic = time.monotonic()
            active_run_id = "R30"
            active_restart = 30
            active_run_observations: list[dict[str, object]] = []
            active_run_observation_wall_seconds = 0.0

            def persist_observation_exception(
                error: BaseException,
                *,
                run_id: str,
                iteration: int | None,
                stage: str,
                details: dict[str, object],
            ) -> None:
                payload = {
                    "schema": "task041.v16.local_collective_observation_error.v1",
                    "classification": "local_secondary_receipt_original_exception_reraised",
                    "run_id": run_id,
                    "rank": int(comm.rank),
                    "iteration": iteration,
                    "stage": stage,
                    "error_type": type(error).__name__,
                    "error_message": exception_message(error),
                    "details": details,
                    "other_rank_cleanup_status": "not_claimed_after_collective_exception",
                }
                receipt = write_rank_json(
                    evidence_root
                    / f"tiny_fgmres_{run_id}_{stage}_rank-{comm.rank}.json",
                    payload,
                )
                try:
                    error.add_note(
                        "secondary Task041 observation receipt: "
                        + json.dumps(receipt, sort_keys=True)
                    )
                except Exception as note_error:  # noqa: BLE001 - preserve original failure
                    receipt["add_note_error"] = {
                        "type": type(note_error).__name__,
                        "message": exception_message(note_error),
                    }

            def fail_at_observation_safe_point(
                stage: str,
                iteration_number: int,
                rows: list[dict[str, object]],
                message: str,
            ) -> None:
                error = AssertionError(message + ": " + json.dumps(rows, sort_keys=True))
                persist_observation_exception(
                    error,
                    run_id=active_run_id,
                    iteration=int(iteration_number),
                    stage=stage,
                    details={"rank_rows": rows},
                )
                raise error

            def capture_intermediate_true_residual(
                current_ksp, iteration_number: int
            ) -> dict[str, object]:
                nonlocal active_run_observation_wall_seconds
                started = time.perf_counter()
                result: dict[str, object] = {
                    "run_id": active_run_id,
                    "iteration": int(iteration_number),
                    "restart_window_index": (iteration_number - 1) // active_restart,
                    "reported_norm_is_not_true_residual": True,
                }

                try:
                    build_solution = getattr(current_ksp, "buildSolution", None)
                    capability = {
                        "rank": int(comm.rank),
                        "callable": callable(build_solution),
                        "lookup_error": None,
                    }
                except Exception as lookup_error:  # noqa: BLE001 - method lookup precedes buildSolution
                    build_solution = None
                    capability = {
                        "rank": int(comm.rank),
                        "callable": False,
                        "lookup_error": {
                            "type": type(lookup_error).__name__,
                            "message": exception_message(lookup_error),
                        },
                    }
                capabilities = comm.allgather(capability)
                available = [bool(row["callable"]) for row in capabilities]
                if any(row["lookup_error"] for row in capabilities) or len(
                    set(available)
                ) != 1:
                    fail_at_observation_safe_point(
                        "buildSolution_capability_preflight",
                        iteration_number,
                        capabilities,
                        "buildSolution availability is inconsistent before invocation",
                    )
                if not available[0]:
                    result.update(
                        status="buildSolution_unavailable",
                        rank_build_solution_probe=[
                            {
                                "rank": int(row["rank"]),
                                "status": "unavailable",
                                "call_attempted": False,
                                "reason": "no_callable_buildSolution_before_call",
                                "unsupported_invariants_unchanged": True,
                            }
                            for row in capabilities
                        ],
                    )
                    result["observation_wall_seconds"] = finite_json_number(
                        time.perf_counter() - started
                    )
                    active_run_observation_wall_seconds += float(
                        result["observation_wall_seconds"]
                    )
                    active_run_observations.append(result)
                    return result

                context = original_operator.getPythonContext()
                matmult_before = int(context._matmult_call_count)
                pc_attempt_before = int(ldu._pc_apply_attempt_count)
                pc_success_before = int(ldu._pc_apply_count)
                capture_request_before = getattr(
                    context, "_v13_modal_row_capture_request", None
                )
                capture_result_before = getattr(
                    context, "_v13_modal_row_capture_result", None
                )
                scratch_handle = int(monitor_solution_scratch.handle)
                monitor_solution_scratch.set(
                    PETSc.ScalarType(12345.0 + 6789.0j)
                )
                preparation_error = None
                try:
                    scratch_before = np.asarray(
                        monitor_solution_scratch.getArray(readonly=True)
                    ).copy()
                    rhs_before = np.asarray(rhs.getArray(readonly=True)).copy()
                    solution_before = np.asarray(
                        solution.getArray(readonly=True)
                    ).copy()
                except Exception as local_error:  # noqa: BLE001 - noncollective local reads
                    preparation_error = {
                        "type": type(local_error).__name__,
                        "message": exception_message(local_error),
                    }
                    scratch_before = rhs_before = solution_before = np.empty(
                        0, dtype=np.complex128
                    )
                preparation_rows = comm.allgather(
                    {
                        "rank": int(comm.rank),
                        "status": "ready" if preparation_error is None else "error",
                        "error": preparation_error,
                    }
                )
                if any(row["status"] != "ready" for row in preparation_rows):
                    fail_at_observation_safe_point(
                        "buildSolution_local_preparation",
                        iteration_number,
                        preparation_rows,
                        "local buildSolution preparation failed",
                    )

                try:
                    returned = build_solution(monitor_solution_scratch)
                except BaseException as build_error:  # preserve possibly collective PETSc failure
                    persist_observation_exception(
                        build_error,
                        run_id=active_run_id,
                        iteration=int(iteration_number),
                        stage="buildSolution",
                        details={
                            "scratch_handle": scratch_handle,
                            "original_A_matmult_delta_so_far": int(
                                context._matmult_call_count
                            ) - matmult_before,
                            "pc_attempt_delta_so_far": int(
                                ldu._pc_apply_attempt_count
                            ) - pc_attempt_before,
                            "pc_success_delta_so_far": int(
                                ldu._pc_apply_count
                            ) - pc_success_before,
                        },
                    )
                    raise

                try:
                    scratch_after = np.asarray(
                        monitor_solution_scratch.getArray(readonly=True)
                    ).copy()
                    returned_handle = getattr(returned, "handle", None)
                    build_row: dict[str, object] = {
                        "rank": int(comm.rank),
                        "returned_uses_scratch": (
                            returned is None
                            or returned is monitor_solution_scratch
                            or (
                                returned_handle is not None
                                and int(returned_handle) == scratch_handle
                            )
                        ),
                        "scratch_written": not np.array_equal(
                            scratch_after, scratch_before
                        ),
                        "scratch_finite": bool(np.isfinite(scratch_after).all()),
                        "scratch_aliases_solution": (
                            scratch_handle == int(solution.handle)
                        ),
                        "scratch_aliases_rhs": scratch_handle == int(rhs.handle),
                        "rhs_unchanged": np.array_equal(
                            np.asarray(rhs.getArray(readonly=True)), rhs_before
                        ),
                        "ksp_solution_unchanged": np.array_equal(
                            np.asarray(solution.getArray(readonly=True)),
                            solution_before,
                        ),
                        "pc_attempt_delta": int(
                            ldu._pc_apply_attempt_count
                        ) - pc_attempt_before,
                        "pc_success_delta": int(
                            ldu._pc_apply_count
                        ) - pc_success_before,
                        "original_A_matmult_delta": int(
                            context._matmult_call_count
                        ) - matmult_before,
                        "capture_request_clear_before": (
                            capture_request_before is None
                        ),
                        "capture_request_clear_after": (
                            getattr(context, "_v13_modal_row_capture_request", None)
                            is None
                        ),
                        "capture_result_clear_before": (
                            capture_result_before is None
                        ),
                        "capture_result_clear_after": (
                            getattr(context, "_v13_modal_row_capture_result", None)
                            is None
                        ),
                    }
                    build_checks = {
                        "returned_uses_scratch": True,
                        "scratch_written": True,
                        "scratch_finite": True,
                        "scratch_aliases_solution": False,
                        "scratch_aliases_rhs": False,
                        "rhs_unchanged": True,
                        "ksp_solution_unchanged": True,
                        "pc_attempt_delta": 0,
                        "pc_success_delta": 0,
                        "original_A_matmult_delta": 0,
                        "capture_request_clear_before": True,
                        "capture_request_clear_after": True,
                        "capture_result_clear_before": True,
                        "capture_result_clear_after": True,
                    }
                    build_row["status"] = (
                        "supported"
                        if all(
                            build_row.get(key) == expected
                            for key, expected in build_checks.items()
                        )
                        else "invariant_failed"
                    )
                except Exception as local_error:  # noqa: BLE001 - buildSolution returned before local inspection
                    build_row = {
                        "rank": int(comm.rank),
                        "status": "local_inspection_error",
                        "error_type": type(local_error).__name__,
                        "error_message": exception_message(local_error),
                    }
                build_rows = comm.allgather(build_row)
                result["rank_build_solution_probe"] = build_rows
                if any(row.get("status") != "supported" for row in build_rows):
                    result.update(status="buildSolution_invariant_failed", finite=False)
                    active_run_observations.append(result)
                    fail_at_observation_safe_point(
                        "buildSolution_invariant",
                        iteration_number,
                        build_rows,
                        "buildSolution scratch/input/PC/A invariant failed",
                    )

                matmult_before_A = int(context._matmult_call_count)
                pc_attempt_before_A = int(ldu._pc_apply_attempt_count)
                pc_success_before_A = int(ldu._pc_apply_count)
                rhs_before_A = np.asarray(rhs.getArray(readonly=True)).copy()
                solution_before_A = np.asarray(
                    solution.getArray(readonly=True)
                ).copy()
                scratch_before_A = np.asarray(
                    monitor_solution_scratch.getArray(readonly=True)
                ).copy()
                capture_request_clear_before_A = (
                    getattr(context, "_v13_modal_row_capture_request", None)
                    is None
                )
                capture_result_clear_before_A = (
                    getattr(context, "_v13_modal_row_capture_result", None)
                    is None
                )
                try:
                    original_operator.mult(
                        monitor_solution_scratch, monitor_residual_scratch
                    )
                    monitor_residual_scratch.axpy(PETSc.ScalarType(-1.0), rhs)
                    rhs_norm = float(rhs.norm())
                    residual_norm = float(monitor_residual_scratch.norm())
                except BaseException as action_error:  # preserve A/norm failure; no recovery collective
                    persist_observation_exception(
                        action_error,
                        run_id=active_run_id,
                        iteration=int(iteration_number),
                        stage="original_A_mult_or_norm",
                        details={
                            "original_A_matmult_delta_so_far": int(
                                context._matmult_call_count
                            ) - matmult_before_A,
                            "pc_attempt_delta_so_far": int(
                                ldu._pc_apply_attempt_count
                            ) - pc_attempt_before_A,
                            "pc_success_delta_so_far": int(
                                ldu._pc_apply_count
                            ) - pc_success_before_A,
                        },
                    )
                    raise

                relative = (
                    residual_norm / rhs_norm if rhs_norm > 0.0 else float("inf")
                )
                try:
                    action_row: dict[str, object] = {
                        "rank": int(comm.rank),
                        "scratch_unchanged": np.array_equal(
                            np.asarray(
                                monitor_solution_scratch.getArray(readonly=True)
                            ),
                            scratch_before_A,
                        ),
                        "rhs_unchanged": np.array_equal(
                            np.asarray(rhs.getArray(readonly=True)), rhs_before_A
                        ),
                        "ksp_solution_unchanged": np.array_equal(
                            np.asarray(solution.getArray(readonly=True)),
                            solution_before_A,
                        ),
                        "capture_request_clear_before": (
                            capture_request_clear_before_A
                        ),
                        "capture_result_clear_before": (
                            capture_result_clear_before_A
                        ),
                        "original_A_matmult_delta": int(
                            context._matmult_call_count
                        ) - matmult_before_A,
                        "pc_attempt_delta": int(
                            ldu._pc_apply_attempt_count
                        ) - pc_attempt_before_A,
                        "pc_success_delta": int(
                            ldu._pc_apply_count
                        ) - pc_success_before_A,
                        "residual_scratch_finite": bool(
                            np.isfinite(
                                np.asarray(
                                    monitor_residual_scratch.getArray(
                                        readonly=True
                                    )
                                )
                            ).all()
                        ),
                        "rhs_norm": finite_json_number(rhs_norm),
                        "ax_minus_f_numerator_norm": finite_json_number(
                            residual_norm
                        ),
                        "ax_minus_f_relative": finite_json_number(relative),
                        "finite": bool(
                            np.isfinite(rhs_norm)
                            and np.isfinite(residual_norm)
                            and np.isfinite(relative)
                        ),
                        "capture_request_clear_after": (
                            getattr(context, "_v13_modal_row_capture_request", None)
                            is None
                        ),
                        "capture_result_clear_after": (
                            getattr(context, "_v13_modal_row_capture_result", None)
                            is None
                        ),
                    }
                    action_checks = {
                        "scratch_unchanged": True,
                        "rhs_unchanged": True,
                        "ksp_solution_unchanged": True,
                        "capture_request_clear_before": True,
                        "capture_result_clear_before": True,
                        "original_A_matmult_delta": 1,
                        "pc_attempt_delta": 0,
                        "pc_success_delta": 0,
                        "residual_scratch_finite": True,
                        "finite": True,
                        "capture_request_clear_after": True,
                        "capture_result_clear_after": True,
                    }
                    action_row["status"] = (
                        "ready"
                        if all(
                            action_row.get(key) == expected
                            for key, expected in action_checks.items()
                        )
                        else "invariant_failed"
                    )
                except Exception as local_error:  # noqa: BLE001 - A/norm returned before local inspection
                    action_row = {
                        "rank": int(comm.rank),
                        "status": "local_inspection_error",
                        "error_type": type(local_error).__name__,
                        "error_message": exception_message(local_error),
                    }
                action_rows = comm.allgather(action_row)
                status = (
                    "captured"
                    if all(row.get("status") == "ready" for row in action_rows)
                    else "original_A_observation_invariant_failed"
                )
                result.update(
                    status=status,
                    independent_A_action_by_rank=action_rows,
                    original_A_matmult_delta=int(
                        context._matmult_call_count - matmult_before
                    ),
                    rhs_norm=finite_json_number(rhs_norm),
                    ax_minus_f_numerator_norm=finite_json_number(residual_norm),
                    ax_minus_f_relative=finite_json_number(relative),
                    finite=bool(
                        np.isfinite(rhs_norm)
                        and np.isfinite(residual_norm)
                        and np.isfinite(relative)
                    ),
                )
                result["observation_wall_seconds"] = finite_json_number(
                    time.perf_counter() - started
                )
                active_run_observation_wall_seconds += float(
                    result["observation_wall_seconds"]
                )
                active_run_observations.append(result)
                if status != "captured":
                    fail_at_observation_safe_point(
                        "original_A_observation_invariant",
                        iteration_number,
                        action_rows,
                        "original A observation input/PC/count invariant failed",
                    )
                return result

            def capture_ksp_monitor(
                _current_ksp, iteration: int, reported_rnorm: float
            ) -> None:
                iteration_number = int(iteration)
                ksp_monitor_samples.append(
                    {
                        "iteration": iteration_number,
                        "petsc_reported_rnorm": finite_json_number(
                            float(reported_rnorm)
                        ),
                        "seconds_since_solve_start": finite_json_number(
                            time.monotonic() - solve_started_monotonic
                        ),
                        "restart_window_index": (
                            None
                            if iteration_number == 0
                            else (iteration_number - 1) // active_restart
                        ),
                        "run_id": active_run_id,
                        "window": (
                            "initial"
                            if iteration_number == 0
                            else "first_60"
                            if iteration_number <= 60
                            else "after_60"
                        ),
                        "run_scope": "this_tiny_attempt_only",
                        "norm_semantics": "PETSc KSP reported norm; not an independent true residual",
                    }
                )
                if iteration_number > 0 and iteration_number % 30 == 0:
                    capture_intermediate_true_residual(
                        _current_ksp, iteration_number
                    )

            ksp.setMonitor(capture_ksp_monitor)
            pc_apply_history: list[dict[str, object]] = []
            original_ldu_apply = ldu.apply

            def encode_complex_array(value: np.ndarray) -> dict[str, object]:
                array = np.asarray(value, dtype=np.complex128)
                return {
                    "dtype": "complex128",
                    "shape": list(array.shape),
                    "values_re_im": [
                        [
                            finite_json_number(float(item.real)),
                            finite_json_number(float(item.imag)),
                        ]
                        for item in array.reshape(-1)
                    ],
                }

            def capture_pc_apply_result(
                attempt_ordinal: int,
                attempt_before: int,
                successful_before: int,
                status: str,
                primary_error: BaseException | None = None,
            ) -> None:
                row: dict[str, object] = {
                    "run_id": active_run_id,
                    "instrumentation_apply_ordinal": attempt_ordinal,
                    "production_attempt_count_before": attempt_before,
                    "production_success_count_before": successful_before,
                    "delegate_status": status,
                    "row_capture_status": "not_available",
                }
                if primary_error is not None:
                    row["primary_apply_error"] = {
                        "type": type(primary_error).__name__,
                        "message": exception_message(primary_error),
                    }
                try:
                    system = ldu.action_modal_schur_system
                    production_attempt_after = int(ldu._pc_apply_attempt_count)
                    production_success_after = int(ldu._pc_apply_count)
                    expected_attempt = attempt_before + 1
                    row["production_attempt_count_after"] = production_attempt_after
                    row["production_success_count_after"] = production_success_after
                    row["expected_attempt_index"] = expected_attempt
                    row["attempt_count_matches_one_apply"] = (
                        production_attempt_after == expected_attempt
                    )
                    row["successful_count_delta"] = (
                        production_success_after - successful_before
                    )
                    frozen = system.frozen_original_modal_row()
                    frozen_record = (
                        None
                        if not isinstance(frozen, dict)
                        else frozen.get("record")
                    )
                    if not isinstance(frozen_record, dict):
                        row["row_capture_status"] = "no_frozen_row"
                        row["latest_attempt_record"] = json_safe(
                            getattr(system, "_last_pc_apply_attempt", None)
                        )
                        row["latest_success_record"] = json_safe(
                            getattr(system, "_last_pc_apply_success", None)
                        )
                    else:
                        current_index = frozen_record.get("attempt_index")
                        row["row_record_attempt_index"] = current_index
                        if current_index != expected_attempt:
                            row["row_capture_status"] = "stale_or_mismatched_attempt"
                            row["latest_attempt_record"] = json_safe(
                                getattr(system, "_last_pc_apply_attempt", None)
                            )
                            row["latest_success_record"] = json_safe(
                                getattr(system, "_last_pc_apply_success", None)
                            )
                        else:
                            row["row_capture_status"] = "captured_current_attempt"
                            row["row_gate"] = {
                                key: json_safe(frozen_record.get(key))
                                for key in (
                                    "schema",
                                    "contract_id",
                                    "status",
                                    "classification",
                                    "attempt_index",
                                    "outer_iteration",
                                    "modal_layout_keys",
                                    "operator_identity",
                                    "same_attempt_owner_solve",
                                    "owner_lu_solve_record",
                                    "owner_lu_solve_count_before",
                                    "owner_lu_solve_count_after",
                                    "solve_count_before",
                                    "solve_count_after",
                                    "B_P4_counters_before",
                                    "B_P4_counters_after_by_rank",
                                    "B_P4_counter_delta_by_rank",
                                    "metrics",
                                    "capture_identity",
                                    "attempt_binding_by_rank",
                                    "snapshot_receipts_by_slot",
                                    "writer_errors",
                                )
                            }
                            row["snapshot_receipt"] = json_safe(
                                frozen.get("snapshot_receipt")
                            )
                            arrays = frozen.get("arrays")
                            if not isinstance(arrays, dict):
                                row["row_capture_status"] = "current_row_arrays_missing"
                            else:
                                row["modal_components"] = {
                                    name: encode_complex_array(arrays[name])
                                    for name in (
                                        "r_modal",
                                        "w_modal",
                                        "t_bottom",
                                        "t_top",
                                        "t_constraint",
                                        "d",
                                    )
                                    if name in arrays
                                }
                                required_arrays = {
                                    "r_modal",
                                    "w_modal",
                                    "t_bottom",
                                    "t_top",
                                    "t_constraint",
                                    "d",
                                }
                                if not required_arrays.issubset(arrays):
                                    row["row_capture_status"] = "current_row_components_incomplete"
                    if not row["attempt_count_matches_one_apply"]:
                        row["row_capture_status"] = "production_attempt_count_mismatch"
                except BaseException as capture_error:  # noqa: BLE001 - capture is secondary to the actual apply
                    row["row_capture_status"] = "capture_error"
                    row["capture_error"] = {
                        "type": type(capture_error).__name__,
                        "message": exception_message(capture_error),
                    }
                    if primary_error is not None:
                        try:
                            primary_error.add_note(
                                "secondary tiny PC-apply capture error: "
                                + exception_message(capture_error)[:240]
                            )
                        except BaseException:  # noqa: BLE001, S110
                            pass
                pc_apply_history.append(row)

            def capture_ldu_apply(_pc, source, target) -> None:
                attempt_ordinal = (
                    sum(
                        row.get("run_id") == active_run_id
                        for row in pc_apply_history
                    )
                    + 1
                )
                attempt_before = int(ldu._pc_apply_attempt_count)
                successful_before = int(ldu._pc_apply_count)
                try:
                    original_ldu_apply(_pc, source, target)
                except BaseException as apply_error:
                    capture_pc_apply_result(
                        attempt_ordinal,
                        attempt_before,
                        successful_before,
                        "raised",
                        apply_error,
                    )
                    raise
                else:
                    capture_pc_apply_result(
                        attempt_ordinal,
                        attempt_before,
                        successful_before,
                        "returned",
                    )

            ldu.apply = capture_ldu_apply
            ldu_apply_wrapper_installed = True
            completion_owner = int(ldu.action_modal_schur_system.modal_owner)
            max_iterations = min(600, max(4, int(layout.global_size)))
            iteration_limit_reasons = set()
            for reason_name in ("DIVERGED_ITS", "DIVERGED_MAX_IT"):
                reason_value = getattr(
                    PETSc.KSP.ConvergedReason, reason_name, None
                )
                if reason_value is not None:
                    iteration_limit_reasons.add(int(reason_value))

            def current_factor_binding() -> dict[str, object]:
                modal_system = ldu.action_modal_schur_system
                pc_now = ksp.getPC()
                pc_context = pc_now.getPythonContext()
                return {
                    "ksp_handle": int(ksp.handle),
                    "pc_handle": int(pc_now.handle),
                    "layout_identity": id(layout),
                    "layout_global_size": int(layout.global_size),
                    "pc_context_is_same_ldu": pc_context is ldu,
                    "ldu_identity": id(ldu),
                    "modal_system_identity": id(modal_system),
                    "original_A_handle": int(original_operator.handle),
                    "original_A_context_identity": id(
                        original_operator.getPythonContext()
                    ),
                    "bottom_action_identity": id(ldu.bottom_action),
                    "top_action_identity": id(ldu.top_action),
                    "modal_C_identity": id(modal_system.modal_constraint),
                    "owner_S_B_identity": id(modal_system.modal_schur),
                    "bottom_p4_factor_identity": id(
                        inverses["bottom"]._p4_factor
                    ),
                    "top_p4_factor_identity": id(
                        inverses["top"]._p4_factor
                    ),
                    "rhs_vector_handle": int(rhs.handle),
                    "exact_solution_vector_handle": int(exact_solution.handle),
                    "solution_vector_handle": int(solution.handle),
                    "true_residual_vector_handle": int(true_residual.handle),
                    "rhs_ownership_range": [
                        int(value) for value in rhs.getOwnershipRange()
                    ],
                    "exact_solution_ownership_range": [
                        int(value)
                        for value in exact_solution.getOwnershipRange()
                    ],
                    "solution_ownership_range": [
                        int(value) for value in solution.getOwnershipRange()
                    ],
                }

            def write_owner_json(
                target_path: Path, payload: dict[str, object]
            ) -> dict[str, object]:
                write_status = None
                if comm.rank == completion_owner:
                    try:
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        temporary_path = target_path.with_name(
                            f".{target_path.name}.{os.getpid()}.tmp"
                        )
                        if target_path.exists() or temporary_path.exists():
                            raise FileExistsError(str(target_path))
                        with temporary_path.open("x", encoding="utf-8") as stream:
                            stream.write(
                                json.dumps(
                                    payload,
                                    sort_keys=True,
                                    indent=2,
                                    allow_nan=False,
                                )
                                + "\n"
                            )
                            stream.flush()
                            os.fsync(stream.fileno())
                        os.replace(temporary_path, target_path)
                        write_status = {
                            "status": "written",
                            "path": str(target_path),
                            "sha256": hashlib.sha256(
                                target_path.read_bytes()
                            ).hexdigest(),
                        }
                    except BaseException as write_error:  # noqa: BLE001 - keep as secondary evidence
                        write_status = {
                            "status": "failed",
                            "error_type": type(write_error).__name__,
                            "error_message": exception_message(write_error),
                        }
                return comm.bcast(write_status, root=completion_owner)

            def write_rank_json(
                target_path: Path, payload: dict[str, object]
            ) -> dict[str, object]:
                try:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    temporary_path = target_path.with_name(
                        f".{target_path.name}.{os.getpid()}.tmp"
                    )
                    if target_path.exists() or temporary_path.exists():
                        raise FileExistsError(str(target_path))
                    with temporary_path.open("x", encoding="utf-8") as stream:
                        stream.write(
                            json.dumps(
                                payload,
                                sort_keys=True,
                                indent=2,
                                allow_nan=False,
                            )
                            + "\n"
                        )
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(temporary_path, target_path)
                    return {
                        "status": "written",
                        "path": str(target_path),
                        "sha256": hashlib.sha256(
                            target_path.read_bytes()
                        ).hexdigest(),
                    }
                except BaseException as write_error:  # noqa: BLE001 - local evidence is secondary
                    return {
                        "status": "failed",
                        "error_type": type(write_error).__name__,
                        "error_message": exception_message(write_error),
                    }

            def freeze_rank_vectors(run_id: str) -> dict[str, object]:
                arrays = {
                    "x_star": np.asarray(
                        exact_solution.getArray(readonly=True)
                    ).copy(),
                    "f": np.asarray(rhs.getArray(readonly=True)).copy(),
                    "x": np.asarray(solution.getArray(readonly=True)).copy(),
                }
                target_path = evidence_root / (
                    f"tiny_fgmres_{run_id}_state_rank-{comm.rank}.npz"
                )
                temporary_path = target_path.with_name(
                    f".{target_path.name}.{os.getpid()}.tmp"
                )
                try:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    if target_path.exists() or temporary_path.exists():
                        raise FileExistsError(str(target_path))
                    with temporary_path.open("xb") as stream:
                        np.savez(stream, **arrays)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(temporary_path, target_path)
                    return {
                        "status": "written",
                        "path": str(target_path),
                        "sha256": hashlib.sha256(
                            target_path.read_bytes()
                        ).hexdigest(),
                        "local_array_sha256": {
                            name: hashlib.sha256(
                                np.ascontiguousarray(value).view(np.uint8)
                            ).hexdigest()
                            for name, value in arrays.items()
                        },
                        "ownership": {
                            "x_star": [
                                int(value)
                                for value in exact_solution.getOwnershipRange()
                            ],
                            "f": [
                                int(value) for value in rhs.getOwnershipRange()
                            ],
                            "x": [
                                int(value)
                                for value in solution.getOwnershipRange()
                            ],
                        },
                        "local_shapes": {
                            name: list(value.shape)
                            for name, value in arrays.items()
                        },
                        "dtype": {
                            name: str(value.dtype)
                            for name, value in arrays.items()
                        },
                    }
                except BaseException as vector_write_error:  # noqa: BLE001 - preserve solve result
                    return {
                        "status": "failed",
                        "error_type": type(vector_write_error).__name__,
                        "error_message": exception_message(vector_write_error),
                    }

            def freeze_terminal_residual(
                run_id: str, *, status: str
            ) -> dict[str, object]:
                target_path = evidence_root / (
                    f"tiny_fgmres_{run_id}_terminal_ax_minus_f_rank-"
                    f"{comm.rank}.npz"
                )
                temporary_path = target_path.with_name(
                    f".{target_path.name}.{os.getpid()}.tmp"
                )
                try:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    if target_path.exists() or temporary_path.exists():
                        raise FileExistsError(str(target_path))
                    residual_values = np.asarray(
                        true_residual.getArray(readonly=True)
                    ).copy()
                    with temporary_path.open("xb") as stream:
                        np.savez(stream, ax_minus_f=residual_values)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(temporary_path, target_path)
                    return {
                        "status": "written",
                        "measurement_status": status,
                        "path": str(target_path),
                        "sha256": hashlib.sha256(
                            target_path.read_bytes()
                        ).hexdigest(),
                        "ownership": [
                            int(value)
                            for value in true_residual.getOwnershipRange()
                        ],
                        "local_shape": list(residual_values.shape),
                        "dtype": str(residual_values.dtype),
                        "raw_nonfinite_values_preserved": True,
                    }
                except BaseException as vector_write_error:  # noqa: BLE001 - retain primary solve/measurement result
                    return {
                        "status": "failed",
                        "measurement_status": status,
                        "error_type": type(vector_write_error).__name__,
                        "error_message": exception_message(vector_write_error),
                    }

            def make_run_configuration(
                run_id: str, selected_restart: int
            ) -> dict[str, object]:
                configuration = copy.deepcopy(ksp_configuration)
                requested = configuration["requested"]
                requested.update(
                    {
                        "run_id": run_id,
                        "max_it": max_iterations,
                        "restart": selected_restart,
                        "initial_guess_nonzero": False,
                        "rtol": 5.0e-9,
                        "atol": 0.0,
                    }
                )
                readback = configuration["readback"]
                readback["restart"] = read_ksp_value(
                    ksp, "getGMRESRestart"
                )
                readback["initial_guess_nonzero"] = read_ksp_value(
                    ksp, "getInitialGuessNonzero"
                )
                readback["tolerances"] = read_ksp_value(ksp, "getTolerances")
                return configuration

            def run_ksp_once(
                run_id: str,
                selected_restart: int,
                *,
                setup_body_seconds: float | None,
                expected_factor_binding: dict[str, object] | None = None,
            ) -> dict[str, object]:
                nonlocal active_run_id
                nonlocal active_restart
                nonlocal active_run_observations
                nonlocal active_run_observation_wall_seconds
                nonlocal solve_started_monotonic

                active_run_id = run_id
                active_restart = selected_restart
                active_run_observations = []
                active_run_observation_wall_seconds = 0.0
                solution.set(PETSc.ScalarType(0.0))
                ksp.setInitialGuessNonzero(False)
                initial_solution_zero = bool(
                    np.equal(
                        np.asarray(solution.getArray(readonly=True)),
                        PETSc.ScalarType(0.0),
                    ).all()
                )
                rhs_before_run = np.asarray(
                    rhs.getArray(readonly=True)
                ).copy()
                exact_solution_before_run = np.asarray(
                    exact_solution.getArray(readonly=True)
                ).copy()
                ksp.setGMRESRestart(selected_restart)
                ksp.setTolerances(
                    rtol=5.0e-9,
                    atol=0.0,
                    max_it=max_iterations,
                )
                binding_before = current_factor_binding()
                same_factor_binding_as_r30 = (
                    None
                    if expected_factor_binding is None
                    else binding_before == expected_factor_binding
                )
                run_configuration = make_run_configuration(
                    run_id, selected_restart
                )
                pc_attempts_before_run = int(ldu._pc_apply_attempt_count)
                pc_successes_before_run = int(ldu._pc_apply_count)
                apply_history_start = len(pc_apply_history)
                monitor_start = len(ksp_monitor_samples)
                monitor_error_start = len(ksp_monitor_errors)
                original_context = original_operator.getPythonContext()
                original_matmult_before = int(
                    original_context._matmult_call_count
                )
                solve_started_monotonic = time.monotonic()
                solve_started_perf = time.perf_counter()
                ksp.solve(rhs, solution)
                solve_wall_seconds = time.perf_counter() - solve_started_perf

                converged_reason = int(ksp.getConvergedReason())
                iteration_count = int(ksp.getIterationNumber())
                pc_attempts_before_terminal_A = int(
                    ldu._pc_apply_attempt_count
                )
                pc_successes_before_terminal_A = int(ldu._pc_apply_count)
                # Persist this solve's owned x*, f and x before the terminal
                # independent A action. A later A/norm failure must not erase
                # the normally returned KSP state.
                vector_freeze_started = time.perf_counter()
                vector_archive = freeze_rank_vectors(run_id)
                vector_freeze_wall_seconds = (
                    time.perf_counter() - vector_freeze_started
                )
                state_arrays = {
                    "rhs": np.asarray(rhs.getArray(readonly=True)),
                    "exact_solution": np.asarray(
                        exact_solution.getArray(readonly=True)
                    ),
                    "solution": np.asarray(
                        solution.getArray(readonly=True)
                    ),
                }
                preterminal_payload = {
                    "schema": "task041.v16.tiny_fe_postsolve_state.v1",
                    "classification": "pre_terminal_A_action_not_solver_pass",
                    "run_id": run_id,
                    "rank": int(comm.rank),
                    "mpi_size": int(comm.size),
                    "converged_reason": converged_reason,
                    "iterations": iteration_count,
                    "max_iterations": max_iterations,
                    "restart": selected_restart,
                    "rhs_handle": int(rhs.handle),
                    "solution_handle": int(solution.handle),
                    "exact_solution_handle": int(exact_solution.handle),
                    "ownership": {
                        "rhs": [int(value) for value in rhs.getOwnershipRange()],
                        "solution": [
                            int(value)
                            for value in solution.getOwnershipRange()
                        ],
                        "exact_solution": [
                            int(value)
                            for value in exact_solution.getOwnershipRange()
                        ],
                    },
                    "pc_attempted_during_solve": (
                        int(ldu._pc_apply_attempt_count)
                        - pc_attempts_before_run
                    ),
                    "pc_successful_during_solve": (
                        int(ldu._pc_apply_count) - pc_successes_before_run
                    ),
                    "state_vector_archive": vector_archive,
                    "local_array_sha256": {
                        name: hashlib.sha256(
                            np.ascontiguousarray(value).view(np.uint8)
                        ).hexdigest()
                        for name, value in state_arrays.items()
                    },
                }
                preterminal_path = evidence_root / (
                    f"tiny_fgmres_{run_id}_postsolve_rank-{comm.rank}.json"
                )
                preterminal_status = write_rank_json(
                    preterminal_path, preterminal_payload
                )
                preterminal_status_by_rank = comm.allgather(
                    {
                        "rank": int(comm.rank),
                        "status": preterminal_status,
                    }
                )

                terminal_observation_started = time.perf_counter()
                original_matmult_before_terminal = int(
                    original_context._matmult_call_count
                )
                terminal_measurement_status = "measured"
                terminal_measurement_errors: list[dict[str, object]] = []
                try:
                    original_operator.mult(solution, true_residual)
                    true_residual.axpy(PETSc.ScalarType(-1.0), rhs)
                    rhs_norm = float(rhs.norm())
                    true_residual_norm = float(true_residual.norm())
                    true_relative_residual = (
                        true_residual_norm / rhs_norm
                        if rhs_norm != 0.0
                        else float("inf")
                    )
                except BaseException as terminal_error:  # preserve possibly collective PETSc failure
                    terminal_measurement_status = "collective_action_or_norm_raised"
                    persist_observation_exception(
                        terminal_error,
                        run_id=run_id,
                        iteration=None,
                        stage="terminal_original_A_or_norm",
                        details={
                            "reason": converged_reason,
                            "iterations": iteration_count,
                            "max_iterations": max_iterations,
                            "original_A_matmult_delta_so_far": (
                                int(original_context._matmult_call_count)
                                - original_matmult_before_terminal
                            ),
                        },
                    )
                    raise
                if not (
                    np.isfinite(rhs_norm)
                    and np.isfinite(true_residual_norm)
                    and np.isfinite(true_relative_residual)
                ):
                    terminal_measurement_status = "nonfinite_terminal_measurement"
                terminal_residual_archive = freeze_terminal_residual(
                    run_id, status=terminal_measurement_status
                )
                terminal_observation_wall_seconds = (
                    time.perf_counter() - terminal_observation_started
                )
                rhs_local_after = np.asarray(
                    rhs.getArray(readonly=True)
                ).copy()
                rhs_unchanged = np.array_equal(
                    rhs_local_after, rhs_before_run
                )
                exact_solution_unchanged = np.array_equal(
                    np.asarray(exact_solution.getArray(readonly=True)),
                    exact_solution_before_run,
                )
                pc_attempts_after_run = int(ldu._pc_apply_attempt_count)
                pc_successes_after_run = int(ldu._pc_apply_count)
                run_apply_history = pc_apply_history[apply_history_start:]
                run_monitor_samples = ksp_monitor_samples[monitor_start:]
                run_monitor_errors = ksp_monitor_errors[monitor_error_start:]
                original_matmult_after = int(
                    original_context._matmult_call_count
                )
                binding_after = current_factor_binding()
                capture_status = "captured"
                capture_error = None
                try:
                    proc_fields = Path("/proc/self/stat").read_text().rsplit(
                        ")", 1
                    )[1].split()
                    actual_cpu = int(proc_fields[36])
                    allowed_cpus = sorted(
                        int(cpu) for cpu in os.sched_getaffinity(0)
                    )
                except BaseException as identity_error:  # noqa: BLE001 - record identity gap
                    actual_cpu = None
                    allowed_cpus = []
                    capture_status = "failed"
                    capture_error = {
                        "type": type(identity_error).__name__,
                        "message": exception_message(identity_error),
                    }
                local_record: dict[str, object] = {
                    "run_id": run_id,
                    "capture_status": capture_status,
                    "capture_error": capture_error,
                    "rank": int(comm.rank),
                    "mpi_size": int(comm.size),
                    "actual_cpu": actual_cpu,
                    "allowed_cpus": allowed_cpus,
                    "fixture_binding": fixture_binding,
                    "test_source_sha256": test_source_sha,
                    "run_vector_binding": {
                        "rhs_handle": int(rhs.handle),
                        "exact_solution_handle": int(exact_solution.handle),
                        "solution_handle": int(solution.handle),
                        "true_residual_handle": int(true_residual.handle),
                        "initial_guess_nonzero_requested": False,
                        "solution_zero_before_solve": initial_solution_zero,
                        "exact_solution_unchanged": bool(
                            exact_solution_unchanged
                        ),
                        "rhs_unchanged": bool(rhs_unchanged),
                    },
                    "pre_terminal_state_receipt_by_rank": (
                        preterminal_status_by_rank
                    ),
                    "original_A": {
                        "petsc_mat_type": type(original_operator).__name__,
                        "petsc_mat_handle": int(original_operator.handle),
                        "python_context_type": type(original_context).__name__,
                        "python_context_id": id(original_context),
                        "python_context_matmult_call_count_before": (
                            original_matmult_before
                        ),
                        "python_context_matmult_call_count_after": (
                            original_matmult_after
                        ),
                        "python_context_matmult_delta": (
                            original_matmult_after - original_matmult_before
                        ),
                        "terminal_A_mult_pc_attempt_delta": (
                            int(ldu._pc_apply_attempt_count)
                            - pc_attempts_before_terminal_A
                        ),
                        "terminal_A_mult_pc_success_delta": (
                            int(ldu._pc_apply_count)
                            - pc_successes_before_terminal_A
                        ),
                        "terminal_A_mult_delta": (
                            int(original_matmult_after)
                            - original_matmult_before_terminal
                        ),
                        "terminal_measurement_status": (
                            terminal_measurement_status
                        ),
                        "terminal_measurement_errors": (
                            terminal_measurement_errors
                        ),
                        "global_shape": [
                            int(value)
                            for value in original_operator.getSize()
                        ],
                        "ldu_bound_operator_identity": (
                            ldu._v13_original_operator_identity
                        ),
                    },
                    "factor_binding": binding_after,
                    "factor_binding_before_run": binding_before,
                    "same_factor_binding_as_r30": (
                        same_factor_binding_as_r30
                    ),
                    "timings": {
                        "test_body_setup_before_R30_solve_seconds": (
                            setup_body_seconds
                        ),
                        "setup_components_are_not_additive_to_test_body_setup": True,
                        "original_A_action_setup_seconds": (
                            original_action_setup_wall_seconds
                        ),
                        "fixed_B_S_B_LDU_builder_setup_seconds": (
                            fixed_b_s_b_setup_wall_seconds
                        ),
                        "solve_wall_including_lazy_KSP_setup_and_monitors_seconds": (
                            solve_wall_seconds
                        ),
                        "periodic_observations_are_subset_of_solve_wall": True,
                        "timings_must_not_be_summed_as_disjoint": True,
                        "periodic_true_residual_observation_seconds": (
                            active_run_observation_wall_seconds
                        ),
                        "terminal_independent_Ax_minus_f_seconds": (
                            terminal_observation_wall_seconds
                        ),
                        "rank_vector_freeze_seconds": (
                            vector_freeze_wall_seconds
                        ),
                    },
                    "ksp": {
                        "configuration": run_configuration,
                        "iteration_budget": {
                            "max_it_expression": (
                                "min(600, max(4, global_size))"
                            ),
                            "max_iterations": max_iterations,
                            "restart": selected_restart,
                            "early_convergence_stops_normally": True,
                            "R60_policy": (
                                "only_after_clean_R30_iteration_limit_and_"
                                "original_Ax_minus_f_miss"
                            ),
                        },
                        "converged_reason": converged_reason,
                        "iterations": iteration_count,
                        "max_iterations": max_iterations,
                        "restart": selected_restart,
                        "monitor_norm_semantics": (
                            "PETSc reported rnorm; not an independent true residual"
                        ),
                        "reported_monitor_samples": run_monitor_samples,
                        "independent_Ax_minus_f_samples": (
                            list(active_run_observations)
                        ),
                        "monitor_capture_errors": run_monitor_errors,
                        "historical_60_step_run_curve": (
                            "not_reconstructed_or_reused"
                        ),
                    },
                    "pc_apply_timeline": {
                        "rank": int(comm.rank),
                        "run_id": run_id,
                        "instrumentation_ordinal_is_independent_of_ksp_iteration": True,
                        "no_one_to_one_iteration_mapping_claimed": True,
                        "attempted_before": pc_attempts_before_run,
                        "attempted_after": pc_attempts_after_run,
                        "successful_before": pc_successes_before_run,
                        "successful_after": pc_successes_after_run,
                        "records": run_apply_history,
                    },
                    "pc_apply_counts": {
                        "attempted_before": pc_attempts_before_run,
                        "attempted_after": pc_attempts_after_run,
                        "attempted_during_solve": (
                            pc_attempts_after_run - pc_attempts_before_run
                        ),
                        "successful_before": pc_successes_before_run,
                        "successful_after": pc_successes_after_run,
                        "successful_during_solve": (
                            pc_successes_after_run - pc_successes_before_run
                        ),
                    },
                    "rhs_norm": finite_json_number(rhs_norm),
                    "ax_minus_f_numerator_norm": finite_json_number(
                        true_residual_norm
                    ),
                    "ax_minus_f_relative": finite_json_number(
                        true_relative_residual
                    ),
                    "ax_minus_f_tolerance": 5.0e-9,
                    "rhs_unchanged": bool(rhs_unchanged),
                    "exact_solution_unchanged": bool(
                        exact_solution_unchanged
                    ),
                    "vector_archive": vector_archive,
                    "terminal_residual_archive": terminal_residual_archive,
                    "checks": {
                        "positive_ksp_reason": converged_reason > 0,
                        "at_least_two_iterations": iteration_count >= 2,
                        "successful_pc_applies_cover_iterations": (
                            pc_successes_after_run - pc_successes_before_run
                            >= iteration_count
                        ),
                        "finite_ax_minus_f_relative": bool(
                            np.isfinite(true_relative_residual)
                        ),
                        "ax_minus_f_within_tolerance": bool(
                            np.isfinite(true_relative_residual)
                            and true_relative_residual <= 5.0e-9
                        ),
                        "rhs_unchanged": bool(rhs_unchanged),
                        "terminal_measurement_passed": (
                            terminal_measurement_status == "measured"
                            and (
                                int(original_context._matmult_call_count)
                                - original_matmult_before_terminal
                            )
                            == 1
                            and np.isfinite(rhs_norm)
                            and np.isfinite(true_residual_norm)
                            and np.isfinite(true_relative_residual)
                            and terminal_residual_archive.get("status")
                            == "written"
                            and terminal_residual_archive.get(
                                "measurement_status"
                            )
                            == "measured"
                        ),
                        "pre_terminal_state_written_on_all_ranks": all(
                            row.get("status", {}).get("status") == "written"
                            for row in preterminal_status_by_rank
                        ),
                        "terminal_solution_matches_frozen_state": (
                            hashlib.sha256(
                                np.ascontiguousarray(
                                    np.asarray(
                                        solution.getArray(readonly=True)
                                    )
                                ).view(np.uint8)
                            ).hexdigest()
                            == vector_archive.get(
                                "local_array_sha256", {}
                            ).get("x")
                        ),
                        "all_terminal_A_mult_calls_avoided_PC_apply": (
                            int(ldu._pc_apply_attempt_count)
                            == pc_attempts_before_terminal_A
                            and int(ldu._pc_apply_count)
                            == pc_successes_before_terminal_A
                        ),
                    },
                }
                if run_id == "R30":
                    local_record["same_factor_binding_as_r30"] = True
                return {
                    "run_id": run_id,
                    "rank_records": comm.allgather(local_record),
                }

            def _inspect_run_rows_for_clean_pc_evidence(
                rank_records: list[dict[str, object]],
            ) -> bool:
                for record in rank_records:
                    ksp_fields = _task041_v16_rank_ksp_fields(record)
                    if ksp_fields is None:
                        return False
                    if record.get("capture_status") != "captured":
                        return False
                    if record.get("same_factor_binding_as_r30") is not True:
                        return False
                    factor_before = record.get(
                        "factor_binding_before_run"
                    )
                    factor_after = record.get("factor_binding")
                    if (
                        not isinstance(factor_before, dict)
                        or not isinstance(factor_after, dict)
                        or factor_before != factor_after
                    ):
                        return False
                    if record.get("vector_archive", {}).get("status") != "written":
                        return False
                    if record.get("rhs_unchanged") is not True:
                        return False
                    if record.get("checks", {}).get(
                        "terminal_measurement_passed"
                    ) is not True:
                        return False
                    if record.get("checks", {}).get(
                        "pre_terminal_state_written_on_all_ranks"
                    ) is not True or record.get("checks", {}).get(
                        "terminal_solution_matches_frozen_state"
                    ) is not True:
                        return False
                    terminal_archive = record.get(
                        "terminal_residual_archive", {}
                    )
                    if (
                        terminal_archive.get("status") != "written"
                        or terminal_archive.get("measurement_status")
                        != "measured"
                    ):
                        return False
                    original_A_record = record.get("original_A", {})
                    if (
                        original_A_record.get("terminal_A_mult_delta") != 1
                        or original_A_record.get(
                            "terminal_measurement_status"
                        )
                        != "measured"
                        or original_A_record.get(
                            "terminal_measurement_errors"
                        )
                    ):
                        return False
                    preterminal_receipts = record.get(
                        "pre_terminal_state_receipt_by_rank", []
                    )
                    if (
                        len(preterminal_receipts)
                        != int(record.get("mpi_size", 0))
                        or any(
                            row.get("rank") != index
                            or not isinstance(row.get("status"), dict)
                            or row["status"].get("status") != "written"
                            for index, row in enumerate(preterminal_receipts)
                        )
                    ):
                        return False
                    vector_binding = record.get("run_vector_binding", {})
                    if (
                        not isinstance(vector_binding, dict)
                        or vector_binding.get("initial_guess_nonzero_requested")
                        is not False
                        or vector_binding.get("solution_zero_before_solve")
                        is not True
                        or vector_binding.get("rhs_unchanged") is not True
                        or vector_binding.get("exact_solution_unchanged")
                        is not True
                    ):
                        return False
                    if record.get("checks", {}).get(
                        "all_terminal_A_mult_calls_avoided_PC_apply"
                    ) is not True:
                        return False
                    monitor_errors = record.get("ksp", {}).get(
                        "monitor_capture_errors", []
                    )
                    if monitor_errors:
                        return False
                    monitor_samples = record.get("ksp", {}).get(
                        "reported_monitor_samples", []
                    )
                    if not monitor_samples or any(
                        not isinstance(
                            sample.get("petsc_reported_rnorm"),
                            (int, float),
                        )
                        or not np.isfinite(
                            float(sample["petsc_reported_rnorm"])
                        )
                        for sample in monitor_samples
                    ):
                        return False
                    counts = record.get("pc_apply_counts", {})
                    apply_records = record.get("pc_apply_timeline", {}).get(
                        "records", []
                    )
                    if (
                        counts.get("attempted_during_solve")
                        != len(apply_records)
                        or counts.get("successful_during_solve", 0)
                        != len(apply_records)
                        or counts.get("successful_during_solve", 0)
                        < ksp_fields["iterations"]
                    ):
                        return False
                    if not apply_records:
                        return False
                    for apply_row in apply_records:
                        row_gate = apply_row.get("row_gate", {})
                        owner_solve = row_gate.get(
                            "owner_lu_solve_record", {}
                        )
                        metrics = row_gate.get("metrics", {})
                        p4_deltas = row_gate.get(
                            "B_P4_counter_delta_by_rank"
                        )
                        if (
                            apply_row.get("delegate_status") != "returned"
                            or apply_row.get("row_capture_status")
                            != "captured_current_attempt"
                            or row_gate.get("status") != "passed"
                            or row_gate.get("same_attempt_owner_solve")
                            is not True
                            or owner_solve.get("status") != "passed"
                            or owner_solve.get("input_unchanged") is not True
                            or row_gate.get("identity_or_evidence_errors")
                            or row_gate.get("capture_array_errors")
                            or row_gate.get("writer_errors")
                            or metrics.get("decomposition_passed") is not True
                            or not isinstance(metrics.get("eta_terms_inf"), (int, float))
                            or not np.isfinite(float(metrics["eta_terms_inf"]))
                            or float(metrics["eta_terms_inf"]) > 1.0e-10
                            or not isinstance(
                                metrics.get("decomposition_eta_terms_inf"),
                                (int, float),
                            )
                            or not np.isfinite(
                                float(metrics["decomposition_eta_terms_inf"])
                            )
                            or float(metrics["decomposition_eta_terms_inf"])
                            > 1.0e-10
                            or not isinstance(p4_deltas, list)
                            or len(p4_deltas) != int(record.get("mpi_size", 0))
                        ):
                            return False
                        for rank_delta in p4_deltas:
                            side_deltas = rank_delta.get("p4_and_B_by_side")
                            if not isinstance(side_deltas, dict) or any(
                                not isinstance(side_deltas.get(side), dict)
                                or side_deltas[side].get("action_apply_count")
                                != 2
                                or side_deltas[side].get("p4_factor_count")
                                != 0
                                for side in ("bottom", "top")
                            ):
                                return False
                    observations = record.get("ksp", {}).get(
                        "independent_Ax_minus_f_samples", []
                    )
                    expected_checkpoints = list(
                        range(30, ksp_fields["iterations"] + 1, 30)
                    )
                    if [
                        int(sample.get("iteration", -1))
                        for sample in observations
                    ] != expected_checkpoints:
                        return False
                    if any(
                        sample.get("status")
                        not in {"captured", "buildSolution_unavailable"}
                        for sample in observations
                    ):
                        return False
                    if any(
                        sample.get("status") == "captured"
                        and sample.get("finite") is not True
                        for sample in observations
                    ):
                        return False
                    for sample in observations:
                        probe_rows = sample.get(
                            "rank_build_solution_probe", []
                        )
                        if len(probe_rows) != int(
                            record.get("mpi_size", 0)
                        ):
                            return False
                        if sample.get("status") == "buildSolution_unavailable":
                            if any(
                                row.get("status") != "unavailable"
                                or row.get(
                                    "unsupported_invariants_unchanged"
                                )
                                is not True
                                for row in probe_rows
                            ):
                                return False
                        elif sample.get("status") == "captured" and any(
                                row.get("status") != "supported"
                                or row.get("returned_uses_scratch") is not True
                                or row.get("scratch_written") is not True
                                or row.get("scratch_finite") is not True
                                or row.get("scratch_aliases_solution") is not False
                                or row.get("scratch_aliases_rhs") is not False
                                or row.get("rhs_unchanged") is not True
                                or row.get("ksp_solution_unchanged") is not True
                                or row.get("pc_attempt_delta") != 0
                                or row.get("pc_success_delta") != 0
                                or row.get("original_A_matmult_delta") != 0
                                or row.get("capture_request_clear_before")
                                is not True
                                or row.get("capture_request_clear_after")
                                is not True
                                or row.get("capture_result_clear_before")
                                is not True
                                or row.get("capture_result_clear_after")
                                is not True
                                for row in probe_rows
                            ):
                            return False
                    if any(
                        sample.get("status") == "captured"
                        and any(
                            row.get("original_A_matmult_delta") != 1
                            or row.get("scratch_unchanged") is not True
                            or row.get("rhs_unchanged") is not True
                            or row.get("ksp_solution_unchanged") is not True
                            or row.get("pc_attempt_delta") != 0
                            or row.get("pc_success_delta") != 0
                            or row.get("residual_scratch_finite") is not True
                            or row.get("capture_request_clear_before") is not True
                            or row.get("capture_request_clear_after") is not True
                            or row.get("capture_result_clear_before") is not True
                            or row.get("capture_result_clear_after") is not True
                            for row in sample.get(
                                "independent_A_action_by_rank", []
                            )
                        )
                        for sample in observations
                    ):
                        return False
                return True

            def run_rows_have_clean_pc_and_capture_evidence(
                rank_records: list[dict[str, object]],
            ) -> bool:
                try:
                    return _inspect_run_rows_for_clean_pc_evidence(
                        rank_records
                    )
                except Exception:  # noqa: BLE001 - malformed evidence blocks R60/pass
                    return False

            def write_run_completion(
                run_result: dict[str, object]
            ) -> dict[str, object]:
                run_id = str(run_result["run_id"])
                run_path = evidence_root / (
                    f"tiny_fgmres_{run_id}_completion.json"
                )
                payload = {
                    "schema": "task041.v16.tiny_fe_fgmres_run_completion.v1",
                    "classification": (
                        "captured_before_final_assertions_not_a_solver_pass"
                    ),
                    "run_id": run_id,
                    "selector": fixture_binding["selector"],
                    "fixture_binding": fixture_binding,
                    "test_source_sha256": test_source_sha,
                    "mpi_size": int(comm.size),
                    "modal_owner": completion_owner,
                    "rank_records": run_result["rank_records"],
                }
                status = write_owner_json(run_path, payload)
                run_result["completion_file"] = status
                return status

            def make_iteration_limit_decision(
                rank_records: list[dict[str, object]],
                completion_file: dict[str, object],
            ) -> tuple[bool, str]:
                if completion_file.get("status") != "written":
                    return False, "R30_completion_write_failed"
                if not rank_records:
                    return False, "R30_rank_records_missing"
                for record in rank_records:
                    if not (
                        _task041_v16_iteration_limit_candidate(
                            record,
                            iteration_limit_reasons,
                            clean_pc_capture_evidence=(
                                run_rows_have_clean_pc_and_capture_evidence(
                                    [record]
                                )
                            ),
                        )
                    ):
                        return False, (
                            "R30_not_clean_full_iteration_limit_with_original_"
                            "Ax_minus_f_miss"
                        )
                return True, "R30_clean_600_iteration_limit_original_residual_miss"

            def run_is_numerically_qualified(
                rank_records: list[dict[str, object]],
            ) -> bool:
                return bool(rank_records) and all(
                    _task041_v16_numeric_record_qualified(
                        record,
                        clean_pc_capture_evidence=(
                            run_rows_have_clean_pc_and_capture_evidence(
                                [record]
                            )
                        ),
                    )
                    for record in rank_records
                )

            setup_before_r30_solve_seconds = (
                time.perf_counter() - test_body_started
            )
            r30_result = run_ksp_once(
                "R30",
                30,
                setup_body_seconds=setup_before_r30_solve_seconds,
            )
            r30_completion_status = write_run_completion(r30_result)
            run_results: list[dict[str, object]] = [r30_result]
            r30_eligible, r60_decision = make_iteration_limit_decision(
                r30_result["rank_records"], r30_completion_status
            )
            r60_result: dict[str, object] | None = None
            r60_execution_authorized = int(comm.size) == 1
            if r60_execution_authorized:
                r60_authorization_reason = (
                    "single_rank_only_conditional_R60_authorization"
                )
            elif int(comm.size) == 2:
                r60_authorization_reason = (
                    "mpi2_R30_qualification_only_no_R60_authorization"
                )
            else:
                r60_authorization_reason = (
                    "multi_rank_R60_not_authorized"
                )
            r60_authorization = {
                "authorized": r60_execution_authorized,
                "reason": r60_authorization_reason,
                "mpi_size": int(comm.size),
            }
            r60_not_run_reason = r60_decision
            if not r60_execution_authorized:
                r60_not_run_reason = r60_authorization_reason
                r60_completion_status = {
                    "status": "not_run",
                    "reason": r60_not_run_reason,
                }
            elif r30_eligible:
                local_factor_binding = current_factor_binding()
                r30_local_binding = r30_result["rank_records"][comm.rank].get(
                    "factor_binding"
                )
                local_reuse_identity = (
                    isinstance(r30_local_binding, dict)
                    and local_factor_binding == r30_local_binding
                    and int(ksp.handle)
                    == int(r30_local_binding.get("ksp_handle", -1))
                    and int(ksp.getPC().handle)
                    == int(r30_local_binding.get("pc_handle", -1))
                    and ksp.getPC().getPythonContext() is ldu
                    and ldu.action_modal_schur_system._destroyed is False
                )
                reuse_identity_by_rank = comm.allgather(
                    bool(local_reuse_identity)
                )
                if all(reuse_identity_by_rank):
                    r60_result = run_ksp_once(
                        "R60",
                        60,
                        setup_body_seconds=None,
                        expected_factor_binding=local_factor_binding,
                    )
                    run_results.append(r60_result)
                    r60_completion_status = write_run_completion(r60_result)
                    r60_not_run_reason = None
                else:
                    r60_not_run_reason = (
                        "same_live_KSP_PC_LDU_B_S_B_factor_identity_not_proven"
                    )
                    r60_completion_status = {
                        "status": "not_run",
                        "reason": r60_not_run_reason,
                    }
            else:
                r60_completion_status = {
                    "status": "not_run",
                    "reason": r60_not_run_reason,
                }

            completion_payload = {
                "schema": "task041.v16.tiny_fe_fgmres_completion.v1",
                "classification": (
                    "captured_before_final_assertions_not_a_solver_pass"
                ),
                "selector": fixture_binding["selector"],
                "fixture_binding": fixture_binding,
                "test_source_sha256": test_source_sha,
                "mpi_size": int(comm.size),
                "modal_owner": completion_owner,
                "historical_prior_attempt": "sealed_prior_raw_preserved_not_reused",
                "primary_run": "R30",
                "r30": {
                    "completion_file": r30_completion_status,
                    "iteration_limit_decision": r60_decision,
                    "rank_summary": [
                        {
                            "rank": record.get("rank"),
                            "reason": (
                                _task041_v16_rank_ksp_fields(record) or {}
                            ).get("converged_reason"),
                            "iterations": (
                                _task041_v16_rank_ksp_fields(record) or {}
                            ).get("iterations"),
                            "max_iterations": (
                                _task041_v16_rank_ksp_fields(record) or {}
                            ).get("max_iterations"),
                            "restart": record.get("restart"),
                            "ax_minus_f_relative": record.get(
                                "ax_minus_f_relative"
                            ),
                            "rhs_unchanged": record.get("rhs_unchanged"),
                            "vector_archive": record.get("vector_archive"),
                            "factor_binding": record.get("factor_binding"),
                        }
                        for record in r30_result["rank_records"]
                    ],
                    "numerically_eligible_for_R60": bool(r30_eligible),
                    "R60_eligibility_reason": r60_decision,
                    "R60_authorization": r60_authorization,
                },
                "r60": (
                    {
                        "status": "run",
                        "authorization": r60_authorization,
                        "completion_file": r60_completion_status,
                        "rank_summary": [
                            {
                                "rank": record.get("rank"),
                                "reason": (
                                    _task041_v16_rank_ksp_fields(record) or {}
                                ).get("converged_reason"),
                                "iterations": (
                                    _task041_v16_rank_ksp_fields(record) or {}
                                ).get("iterations"),
                                "max_iterations": (
                                    _task041_v16_rank_ksp_fields(record) or {}
                                ).get("max_iterations"),
                                "restart": record.get("restart"),
                                "ax_minus_f_relative": record.get(
                                    "ax_minus_f_relative"
                                ),
                                "rhs_unchanged": record.get("rhs_unchanged"),
                                "vector_archive": record.get("vector_archive"),
                                "factor_binding": record.get("factor_binding"),
                                "same_factor_binding_as_r30": record.get(
                                    "same_factor_binding_as_r30"
                                ),
                            }
                            for record in r60_result["rank_records"]
                        ],
                    }
                    if r60_result is not None
                    else {
                        "status": "not_run",
                        "reason": r60_not_run_reason,
                    "R30_numerically_eligible_for_R60": bool(r30_eligible),
                    "R30_R60_eligibility_reason": r60_decision,
                    "authorization": r60_authorization,
                    }
                ),
            }
            completion_status = write_owner_json(
                evidence_root / "tiny_fgmres_completion.json",
                completion_payload,
            )
        except BaseException as solve_or_assertion_error:
            ksp_destroy_primary = solve_or_assertion_error
            raise
        else:
            ksp_destroy_primary = None
        finally:
            ksp_cleanup_started = time.perf_counter()
            if ldu_apply_wrapper_installed:
                try:
                    if prior_instance_apply is missing_instance_apply:
                        delattr(ldu, "apply")
                    else:
                        ldu.apply = prior_instance_apply
                except BaseException as restore_error:  # noqa: BLE001 - cleanup is secondary
                    apply_restore_error = {
                        "type": type(restore_error).__name__,
                        "message": exception_message(restore_error),
                    }
                    if ksp_destroy_primary is not None:
                        try:
                            ksp_destroy_primary.add_note(
                                "secondary LDU apply restore error: "
                                + exception_message(restore_error)
                            )
                        except BaseException:  # noqa: BLE001, S110
                            pass
            try:
                ksp.destroy()
            except BaseException as destroy_error:  # noqa: BLE001 - record and continue frozen checks
                ksp_destroy_error = {
                    "type": type(destroy_error).__name__,
                    "message": exception_message(destroy_error),
                }
                if ksp_destroy_primary is not None:
                    try:
                        ksp_destroy_primary.add_note(
                            "secondary KSP destroy error: "
                            + exception_message(destroy_error)
                        )
                    except BaseException:  # noqa: BLE001, S110
                        pass
                else:
                    ksp_destroy_primary = destroy_error
                    write_rank_json(
                        evidence_root
                        / f"tiny_fgmres_ksp_destroy_error_rank-{comm.rank}.json",
                        {
                            "schema": "task041.v16.local_cleanup_error.v1",
                            "rank": int(comm.rank),
                            "stage": "KSP.destroy",
                            "error": ksp_destroy_error,
                            "post_destroy_lifecycle_collectives": "not_run",
                        },
                    )
            finally:
                ksp_cleanup_wall_seconds = (
                    time.perf_counter() - ksp_cleanup_started
                )

        if ksp_destroy_error is not None:
            raise ksp_destroy_primary

        frozen_lifecycle_cleanup_started = time.perf_counter()
        modal_system_after_solve = ldu.action_modal_schur_system
        ldu_destroy_error: dict[str, str] | None = None
        try:
            ldu.destroy()
        except BaseException as destroy_error:  # preserve possible collective cleanup failure
            ldu_destroy_error = {
                "type": type(destroy_error).__name__,
                "message": exception_message(destroy_error),
            }
            write_rank_json(
                evidence_root
                / f"tiny_fgmres_ldu_destroy_error_rank-{comm.rank}.json",
                {
                    "schema": "task041.v16.local_cleanup_error.v1",
                    "rank": int(comm.rank),
                    "stage": "LDU.destroy",
                    "error": ldu_destroy_error,
                    "post_destroy_lifecycle_collectives": "not_run",
                },
            )
            raise

        local_lifecycle: dict[str, object] = {
            "rank": int(comm.rank),
            "ldu_destroyed": modal_system_after_solve._destroyed is True,
            "frozen_row_status": "unavailable",
            "frozen_row_classification": None,
            "frozen_arrays_readable": False,
            "frozen_d_finite": False,
        }
        try:
            frozen_row = modal_system_after_solve.frozen_original_modal_row()
            if isinstance(frozen_row, dict):
                frozen_record = frozen_row.get("record")
                arrays = frozen_row.get("arrays")
                local_lifecycle["frozen_row_status"] = (
                    frozen_record.get("status")
                    if isinstance(frozen_record, dict)
                    else None
                )
                local_lifecycle["frozen_row_classification"] = (
                    frozen_record.get("classification")
                    if isinstance(frozen_record, dict)
                    else None
                )
                local_lifecycle["frozen_arrays_readable"] = isinstance(
                    arrays, dict
                )
                local_lifecycle["frozen_d_finite"] = bool(
                    isinstance(arrays, dict)
                    and isinstance(arrays.get("d"), np.ndarray)
                    and np.isfinite(arrays["d"]).all()
                )
            else:
                local_lifecycle["error"] = (
                    "frozen_original_modal_row returned no mapping"
                )
        except BaseException as frozen_error:  # noqa: BLE001 - retain lifecycle failure
            local_lifecycle["error"] = exception_message(frozen_error)
        lifecycle_rank_rows = comm.allgather(local_lifecycle)

        snapshot_validation = None
        if comm.rank == modal_system_after_solve.modal_owner:
            try:
                if not all(
                    row.get("ldu_destroyed") is True
                    and row.get("frozen_row_status") == "passed"
                    and row.get("frozen_row_classification")
                    == "numeric_gate_pass"
                    and row.get("frozen_arrays_readable") is True
                    and row.get("frozen_d_finite") is True
                    for row in lifecycle_rank_rows
                ):
                    raise AssertionError(
                        "post-destroy frozen row checks failed by rank"
                    )
                evidence_index_path = (
                    evidence_root
                    / "numerical_output"
                    / "v13_modal_row_evidence"
                    / "index.json"
                )
                evidence_index = json.loads(
                    evidence_index_path.read_text(encoding="utf-8")
                )
                required_slots = {
                    "v15_s_b_ready",
                    "v15_first_success_control",
                }
                if not required_slots.issubset(
                    evidence_index.get("records", {})
                ):
                    raise AssertionError(
                        "required post-destroy evidence slots are absent"
                    )
                snapshot_array_validations: dict[str, dict[str, object]] = {}
                for slot in required_slots:
                    record = evidence_index["records"][slot]
                    artifact_path = evidence_root / record["path"]
                    if hashlib.sha256(artifact_path.read_bytes()).hexdigest() != (
                        record["sha256"]
                    ):
                        raise AssertionError(
                            f"post-destroy snapshot hash mismatch: {slot}"
                        )
                    with np.load(artifact_path, allow_pickle=False) as artifact:
                        snapshot_arrays = {
                            name: artifact[name] for name in artifact.files
                        }
                        array_validation = (
                            _task041_v16_validate_snapshot_arrays(
                                snapshot_arrays
                            )
                        )
                        if array_validation.get("status") != "passed":
                            raise AssertionError(
                                "post-destroy snapshot is invalid: "
                                f"{slot}: {array_validation}"
                            )
                        snapshot_array_validations[slot] = array_validation
                snapshot_validation = {
                    "status": "passed",
                    "required_slots": sorted(required_slots),
                    "array_validation": {
                        slot: snapshot_array_validations[slot]
                        for slot in sorted(snapshot_array_validations)
                    },
                }
            except BaseException as snapshot_error:  # noqa: BLE001 - broadcast before final assertion
                snapshot_validation = {
                    "status": "failed",
                    "error": exception_message(snapshot_error),
                    "rank_rows": lifecycle_rank_rows,
                }
        snapshot_validation = comm.bcast(
            snapshot_validation, root=modal_system_after_solve.modal_owner
        )
        frozen_lifecycle_cleanup_wall_seconds = (
            time.perf_counter() - frozen_lifecycle_cleanup_started
        )
        lifecycle_payload = {
            "schema": "task041.v16.tiny_fe_post_destroy_lifecycle.v1",
            "classification": "lifecycle_result_separate_from_solver_result",
            "selector": fixture_binding["selector"],
            "test_source_sha256": test_source_sha,
            "mpi_size": int(comm.size),
            "modal_owner": int(modal_system_after_solve.modal_owner),
            "rank_rows": lifecycle_rank_rows,
            "ksp_destroy_error": ksp_destroy_error,
            "ldu_apply_restore_error": apply_restore_error,
            "ldu_destroy_error": ldu_destroy_error,
            "snapshot_validation": snapshot_validation,
            "timings": {
                "ksp_destroy_seconds": ksp_cleanup_wall_seconds,
                "ldu_destroy_and_frozen_snapshot_check_seconds": (
                    frozen_lifecycle_cleanup_wall_seconds
                ),
                "combined_cleanup_seconds": (
                    ksp_cleanup_wall_seconds
                    + frozen_lifecycle_cleanup_wall_seconds
                ),
            },
        }
        lifecycle_write_status = write_owner_json(
            evidence_root / "tiny_fgmres_post_destroy_lifecycle.json",
            lifecycle_payload,
        )

        selected_result = r60_result if r60_result is not None else r30_result
        selected_run_passed = run_is_numerically_qualified(
            selected_result["rank_records"]
        )
        all_run_completion_files_written = (
            r30_completion_status.get("status") == "written"
            and (
                r60_result is None
                or r60_completion_status.get("status") == "written"
            )
            and completion_status.get("status") == "written"
        )
        lifecycle_passed = (
            snapshot_validation.get("status") == "passed"
            and lifecycle_write_status.get("status") == "written"
            and apply_restore_error is None
            and ksp_destroy_error is None
            and ldu_destroy_error is None
        )
        final_validation = {
            "classification": (
                "tiny_solve_and_lifecycle_pass"
                if selected_run_passed
                and all_run_completion_files_written
                and lifecycle_passed
                else "tiny_solve_or_evidence_or_lifecycle_failure"
            ),
            "selected_run": selected_result["run_id"],
            "selected_run_numerically_qualified": selected_run_passed,
            "R30_reason": [
                (_task041_v16_rank_ksp_fields(row) or {}).get(
                    "converged_reason"
                )
                for row in r30_result["rank_records"]
            ],
            "R30_iterations": [
                (_task041_v16_rank_ksp_fields(row) or {}).get("iterations")
                for row in r30_result["rank_records"]
            ],
            "R30_ax_minus_f_relative": [
                row.get("ax_minus_f_relative")
                for row in r30_result["rank_records"]
            ],
            "R60_status": (
                "run" if r60_result is not None else "not_run"
            ),
            "R60_not_run_reason": r60_not_run_reason,
            "R30_numerically_eligible_for_R60": bool(r30_eligible),
            "R30_R60_eligibility_reason": r60_decision,
            "R60_execution_authorized": r60_execution_authorized,
            "R60_authorization_reason": r60_authorization_reason,
            "run_completion_files_written": (
                all_run_completion_files_written
            ),
            "post_destroy_snapshot_validation": snapshot_validation,
            "lifecycle_record_write": lifecycle_write_status,
            "ksp_destroy_error": ksp_destroy_error,
            "ldu_apply_restore_error": apply_restore_error,
            "ldu_destroy_error": ldu_destroy_error,
            "lifecycle_passed": lifecycle_passed,
        }
        assert (
            selected_run_passed
            and all_run_completion_files_written
            and lifecycle_passed
        ), final_validation
    finally:
        primary_error = sys.exc_info()[1]
        cleanup_errors: list[BaseException] = []

        def cleanup_step(label: str, action) -> None:
            try:
                action()
            except BaseException as cleanup_error:  # noqa: BLE001 - preserve the first failure
                try:
                    cleanup_message = str(cleanup_error)[:320]
                except BaseException as render_error:  # noqa: BLE001 - cleanup reporting is secondary
                    cleanup_message = (
                        f"<message unavailable: {type(render_error).__name__}>"
                    )
                note = f"secondary tiny-FE cleanup error at {label}: " + (
                    f"{type(cleanup_error).__name__}: {cleanup_message}"
                )
                if primary_error is not None:
                    try:
                        primary_error.add_note(note)
                    except BaseException:  # noqa: BLE001, S110
                        pass
                elif cleanup_errors:
                    try:
                        cleanup_errors[0].add_note(note)
                    except BaseException:  # noqa: BLE001, S110
                        pass
                else:
                    cleanup_errors.append(cleanup_error)

        def assert_factor_lifecycle(inverse) -> None:
            diagnostics = inverse.diagnostics
            assert diagnostics["p4_factor_live"] == 1
            assert diagnostics["nested_iterative_ksp_count"] == 1

        def restore_side_factor_apply(side: str, inverse) -> None:
            factor = inverse._p4_factor
            original = p4_apply_originals.get(side)
            if factor is not None and original is not None:
                original_factor, original_apply = original
                assert factor is original_factor
                factor.apply = original_apply

        if ldu is not None:
            cleanup_step("LDU destroy", ldu.destroy)
        if original_operator is not None:
            cleanup_step("original operator destroy", original_operator.destroy)
        if original_action_context is not None:
            cleanup_step("original action context destroy", original_action_context.destroy)
        if ldu is not None:
            # Destruction of the LDU/action wrappers must not own the factors.
            for inverse in inverses.values():
                cleanup_step(
                    "side factor lifecycle assertion",
                    lambda inverse=inverse: assert_factor_lifecycle(inverse),
                )
        if coupling is not None:
            cleanup_step("coupling destroy", coupling.destroy)
        for side, inverse in inverses.items():
            cleanup_step(
                f"{side} P4 apply restore",
                lambda side=side, inverse=inverse: restore_side_factor_apply(
                    side, inverse
                ),
            )
            cleanup_step(f"{side} inverse destroy", inverse.destroy)
        for index, vector in enumerate(outputs.values()):
            cleanup_step(f"output vector {index} destroy", vector.destroy)
        for index, vector in enumerate(inputs):
            cleanup_step(f"input vector {index} destroy", vector.destroy)
        for index, vector in enumerate(mode_vectors):
            cleanup_step(f"mode vector {index} destroy", vector.destroy)
        if primary_error is None and cleanup_errors:
            raise cleanup_errors[0]


def test_task041_h1e_real_fe_side_inverse_is_sequential_and_owned(
    h1e_real_side_systems,
) -> None:
    """Check real tiny-FE ownership without constructing the old oracle factors."""

    baseline: dict[str, dict[str, object]] = {}
    live_inverse_count = 0
    try:
        # Capture both borrowed operators before either adapter is constructed.
        for side_index, side in enumerate(("bottom", "top")):
            operator = h1e_real_side_systems[side].A
            original_b = h1e_real_side_systems[side].b
            source = operator.createVecRight()
            rhs = operator.createVecLeft()
            _fill_active(source, 1.0 + float(side_index))
            operator.mult(source, rhs)
            assert source.norm() > 0.0
            assert rhs.norm() > 0.0
            baseline[side] = {
                "operator": operator,
                "b": original_b,
                "source": source,
                "rhs": rhs,
                "b_values": np.asarray(
                    original_b.getArray(readonly=True)
                ).copy(),
                "source_values": np.asarray(
                    source.getArray(readonly=True)
                ).copy(),
                "rhs_values": np.asarray(rhs.getArray(readonly=True)).copy(),
            }

        def assert_borrowed_objects_unchanged() -> None:
            for record in baseline.values():
                operator = record["operator"]
                original_b = record["b"]
                source = record["source"]
                rhs = record["rhs"]
                probe = operator.createVecLeft()
                try:
                    operator.mult(source, probe)
                    np.testing.assert_array_equal(
                        original_b.getArray(readonly=True), record["b_values"]
                    )
                    np.testing.assert_array_equal(
                        source.getArray(readonly=True), record["source_values"]
                    )
                    np.testing.assert_array_equal(
                        rhs.getArray(readonly=True), record["rhs_values"]
                    )
                    np.testing.assert_allclose(
                        probe.getArray(readonly=True), record["rhs_values"],
                        atol=1.0e-12,
                        rtol=1.0e-12,
                    )
                finally:
                    probe.destroy()

        assert_borrowed_objects_unchanged()

        for side in ("bottom", "top"):
            side_system = h1e_real_side_systems[side]
            operator = baseline[side]["operator"]
            rhs = baseline[side]["rhs"]
            zero_rhs = operator.createVecRight()
            zero_output = operator.createVecLeft()
            nonzero_output = operator.createVecLeft()
            inverse = None
            events = []

            def record_lifecycle(event, detail, event_log=events):
                event_log.append((event, dict(detail)))

            try:
                zero_rhs.set(0.0)
                zero_rhs.assemble()
                inverse = build_side_balanced_inverse(
                    side_system,
                    lifecycle_callback=record_lifecycle,
                )
                # This counter is test bookkeeping only; diagnostics are the
                # ownership authority below.
                live_inverse_count += 1
                assert live_inverse_count == 1
                diagnostics = inverse.diagnostics
                assert diagnostics["p4_factor_live"] == 1
                assert diagnostics["nested_iterative_ksp_count"] == 1
                assert diagnostics["p4_factor_created_count"] == 1
                assert diagnostics["nested_ksp_created_count"] == 1

                inverse.apply(zero_rhs, zero_output)
                assert inverse.diagnostics["last_apply"]["status"] == (
                    "ZERO_RHS_EXACT"
                )
                assert zero_output.norm() == 0.0

                inverse.apply(rhs, nonzero_output)
                nonzero_audit = inverse.diagnostics["last_apply"]
                assert nonzero_audit["status"] == "KSP_CONVERGED"
                assert nonzero_audit["reason"] > 0
                assert nonzero_audit["explicit_true_target_reached"] is True
                assert np.isfinite(nonzero_audit["residual_norm"])
                assert np.isfinite(nonzero_audit["relative_residual"])
                assert nonzero_audit["relative_residual"] <= 1.0e-2
                event_names = [event for event, _detail in events]
                for expected in (
                    "full_action_begin",
                    "full_action_ready",
                    "p4_form_assembly_begin",
                    "p4_factor_ready",
                    "transfer_ready",
                    "h6_diagonal_ready",
                    "h6_window_ready",
                    "h6_runtime_ready",
                    "adapter_ksp_ready",
                ):
                    assert expected in event_names
                assert all(
                    detail["scope"] == "side_local"
                    for _event, detail in events
                )
            finally:
                if inverse is not None:
                    inverse.destroy()
                    live_inverse_count -= 1
                    assert live_inverse_count == 0
                    released = inverse.diagnostics
                    assert released["destroyed"] is True
                    assert released["p4_factor_live"] == 0
                    assert released["nested_iterative_ksp_count"] == 0
                    assert released["p4_factor_destroy_count"] == 1
                    assert released["nested_ksp_destroy_count"] == 1
                zero_output.destroy()
                nonzero_output.destroy()
                zero_rhs.destroy()

            # This is deliberately before the top adapter is built, so a
            # bottom cleanup that damages the borrowed top system is visible.
            if side == "bottom":
                assert_borrowed_objects_unchanged()

        assert_borrowed_objects_unchanged()
    finally:
        for record in baseline.values():
            record["rhs"].destroy()
            record["source"].destroy()


@pytest.fixture(scope="module")
def h1e_one_side_real_system():
    """Build one borrowed side so the p4 layout is reused exactly once."""

    comm = MPI.COMM_WORLD
    cfg = _fixture_config(6, condensed=True)
    mesh = build_hybrid_local_mesh(
        cfg,
        "bottom",
        bottom_interface_z_nm=0.5,
        top_interface_z_nm=0.5,
        comm=comm,
    )
    system = assemble_hybrid_local_dtn_action_system(
        cfg,
        "bottom",
        local_mesh_override=mesh,
        comm=comm,
    )
    try:
        yield system
    finally:
        system.destroy()


def test_task041_h1e_condensed_p4_matches_full_gp_response(
    h1e_one_side_real_system,
) -> None:
    """Compare one physical layout through full and condensed p4 factors."""

    comm = MPI.COMM_WORLD
    side_system = h1e_one_side_real_system
    physical = None
    full_matrix = None
    full_factor = None
    condensed: P4CondensedExactFactor | None = None
    fe_rhs = None
    augmented_rhs = None
    full_solution = None
    full_residual = None
    full_reference = None
    condensed_solution = None
    condensed_augmented = None
    condensed_residual = None
    rhs_b = None
    solution_b = None
    solution_a_repeat = None
    near_rhs = None
    near_solution = None
    zero_rhs = None
    zero_solution = None
    combo_rhs = None
    combo_solution = None
    expected_combo = None
    comparison = None
    repeat = None
    linearity = None
    oracle_rhs = None
    try:
        physical = _build_matching_p4_action(side_system)
        full_matrix = _assemble_augmented_matrix(physical)
        full_factor = ResearchExactFactorInverse(
            full_matrix,
            factor_solver_type="mumps",
            factor_only_storage=True,
        )
        fe_rhs = physical.action.context.input_vector.duplicate()
        fe_rhs.set(PETSc.ScalarType(0.0))
        _fill_algebraic(
            fe_rhs,
            physical.action.context.owned_slaves,
            1.7,
        )
        fe_before = np.asarray(fe_rhs.getArray(readonly=True)).copy()
        port_rhs = np.asarray(
            [
                (0.25 + 0.13j) * (index + 1)
                for index in range(len(physical.action.modes))
            ],
            dtype=np.complex128,
        )
        augmented_rhs = _augmented_vec_from_base(
            fe_rhs,
            len(port_rhs),
            comm,
        )
        if comm.rank == comm.size - 1:
            start, end = map(int, augmented_rhs.getOwnershipRange())
            port_start = physical.full_rows
            local_ports = np.arange(
                port_start,
                port_start + len(port_rhs),
                dtype=PETSc.IntType,
            )
            assert start <= port_start and end >= port_start + len(port_rhs)
            augmented_rhs.setValues(
                local_ports,
                port_rhs,
                addv=PETSc.InsertMode.ADD_VALUES,
            )
        augmented_rhs.assemble()
        full_solution = full_matrix.createVecRight()
        full_factor.solve(augmented_rhs, full_solution)
        full_residual = augmented_rhs.duplicate()
        full_matrix.mult(full_solution, full_residual)
        full_residual.axpy(PETSc.ScalarType(-1.0), augmented_rhs)
        full_relative = full_residual.norm() / augmented_rhs.norm()
        assert np.isfinite(full_relative)
        assert full_relative <= _STRICT_TOLERANCE
        full_reference = _extract_fe_segment(full_solution, physical.full_rows)
        if comm.rank == comm.size - 1:
            start, end = map(int, full_solution.getOwnershipRange())
            offset = physical.full_rows - start
            assert 0 <= offset <= end - start
            port_reference = np.asarray(
                full_solution.getArray(readonly=True)[
                    offset : offset + len(port_rhs)
                ],
                dtype=np.complex128,
            ).copy()
            assert len(port_reference) == len(port_rhs)
        else:
            port_reference = None
        port_reference = np.asarray(
            comm.bcast(port_reference, root=comm.size - 1),
            dtype=np.complex128,
        )
        full_factor.destroy()
        full_factor = None
        augmented_rhs.destroy()
        augmented_rhs = None
        full_solution.destroy()
        full_solution = None

        condensed = build_p4_condensed_exact_factor_from_action(
            physical,
            owns_physical_action=False,
        )
        same_physical_v_mpc_local = (
            condensed.physical_action is physical
            and condensed.physical_action.V is physical.V
            and condensed.physical_action.floquet_data.mpc
            is physical.floquet_data.mpc
        )
        same_physical_v_mpc = bool(
            all(comm.allgather(same_physical_v_mpc_local))
        )
        assert same_physical_v_mpc
        condensed_solution, port_solution = condensed.solve(
            fe_rhs,
            port_rhs=port_rhs,
        )
        comparison = condensed_solution.duplicate()
        condensed_solution.copy(comparison)
        comparison.axpy(PETSc.ScalarType(-1.0), full_reference)
        comparison_relative = comparison.norm() / full_reference.norm()
        assert np.isfinite(comparison_relative)
        assert comparison_relative <= 1.0e-11
        port_difference = np.linalg.norm(port_solution - port_reference)
        port_relative = port_difference / np.linalg.norm(port_reference)
        assert np.isfinite(port_relative)
        assert port_relative <= 1.0e-11
        condensed_augmented = _augmented_vec_from_base(
            condensed_solution,
            len(port_solution),
            comm,
        )
        if comm.rank == comm.size - 1:
            start, end = map(int, condensed_augmented.getOwnershipRange())
            offset = physical.full_rows - start
            condensed_augmented.setValues(
                np.arange(
                    physical.full_rows,
                    physical.full_rows + len(port_solution),
                    dtype=PETSc.IntType,
                ),
                port_solution,
                addv=PETSc.InsertMode.ADD_VALUES,
            )
            assert offset >= 0 and end >= physical.full_rows + len(port_solution)
        condensed_augmented.assemble()
        condensed_residual = condensed_augmented.duplicate()
        full_matrix.mult(condensed_augmented, condensed_residual)
        oracle_rhs = _augmented_vec_from_base(fe_rhs, len(port_rhs), comm)
        if comm.rank == comm.size - 1:
            oracle_rhs.setValues(
                np.arange(
                    physical.full_rows,
                    physical.full_rows + len(port_rhs),
                    dtype=PETSc.IntType,
                ),
                port_rhs,
                addv=PETSc.InsertMode.ADD_VALUES,
            )
        oracle_rhs.assemble()
        condensed_residual.axpy(PETSc.ScalarType(-1.0), oracle_rhs)
        condensed_residual_norm = condensed_residual.norm()
        oracle_rhs_norm = float(oracle_rhs.norm())
        condensed_residual_relative = condensed_residual_norm / oracle_rhs_norm
        assert condensed_residual_relative <= 1.0e-11
        audit = dict(condensed.diagnostics["last_solve"])
        assert audit["status"] == "passed"
        assert audit["relative_residual"] <= _STRICT_TOLERANCE
        assert audit["physical_relative_residual"] <= _STRICT_TOLERANCE
        assert audit["backsolve_count"] <= 3
        assert audit["refinement_count"] <= 2
        case_audits = {"normal": audit}
        np.testing.assert_array_equal(
            fe_rhs.getArray(readonly=True),
            fe_before,
        )

        zero_rhs = fe_rhs.duplicate()
        zero_rhs.set(PETSc.ScalarType(0.0))
        zero_rhs.assemble()
        zero_count_before = condensed.inverse.solve_count
        zero_solution, zero_ports = condensed.solve(
            zero_rhs,
            port_rhs=np.zeros_like(port_rhs),
        )
        zero_count_after = condensed.inverse.solve_count
        assert zero_solution.norm() == 0.0
        assert np.array_equal(zero_ports, np.zeros_like(port_rhs))
        assert zero_count_after == zero_count_before
        zero_audit = dict(condensed.diagnostics["last_solve"])
        assert zero_audit["physical_relative_residual"] == 0.0
        case_audits["zero"] = zero_audit

        near_rhs = fe_rhs.duplicate()
        fe_rhs.copy(near_rhs)
        near_rhs.scale(PETSc.ScalarType(1.0e-14))
        near_rhs.assemble()
        near_solution, near_ports = condensed.solve(
            near_rhs,
            port_rhs=port_rhs * 1.0e-14,
        )
        near_rhs_norm = float(near_rhs.norm())
        assert near_solution.norm() > 0.0
        near_audit = dict(condensed.diagnostics["last_solve"])
        assert near_audit["status"] == "passed"
        assert near_audit["backsolve_count"] <= 3
        assert near_audit["refinement_count"] <= 2
        assert np.linalg.norm(near_ports) > 0.0
        case_audits["nearzero"] = near_audit

        rhs_b = fe_rhs.duplicate()
        _fill_algebraic(
            rhs_b,
            physical.action.context.owned_slaves,
            2.3,
        )
        gp_b = port_rhs * (-0.17 + 0.21j)
        solution_b, ports_b = condensed.solve(rhs_b, port_rhs=gp_b)
        b_audit = dict(condensed.diagnostics["last_solve"])
        assert b_audit["backsolve_count"] <= 3
        assert b_audit["refinement_count"] <= 2
        case_audits["B"] = b_audit
        solution_a_repeat, ports_a_repeat = condensed.solve(
            fe_rhs,
            port_rhs=port_rhs,
        )
        repeat_audit = dict(condensed.diagnostics["last_solve"])
        assert repeat_audit["backsolve_count"] <= 3
        assert repeat_audit["refinement_count"] <= 2
        case_audits["A_repeat"] = repeat_audit
        repeat = solution_a_repeat.duplicate()
        solution_a_repeat.copy(repeat)
        repeat.axpy(PETSc.ScalarType(-1.0), condensed_solution)
        repeat_norm = float(repeat.norm())
        condensed_solution_norm = float(condensed_solution.norm())
        repeat_relative = repeat_norm / condensed_solution_norm
        assert repeat_relative <= 1.0e-11
        assert (
            np.linalg.norm(ports_a_repeat - port_solution)
            / np.linalg.norm(port_solution)
            <= 1.0e-11
        )

        alpha = 0.37 + 0.19j
        beta = -0.23 + 0.11j
        combo_rhs = fe_rhs.duplicate()
        fe_rhs.copy(combo_rhs)
        combo_rhs.scale(PETSc.ScalarType(alpha))
        combo_rhs.axpy(PETSc.ScalarType(beta), rhs_b)
        combo_rhs.assemble()
        combo_solution, combo_ports = condensed.solve(
            combo_rhs,
            port_rhs=alpha * port_rhs + beta * gp_b,
        )
        linearity_audit = dict(condensed.diagnostics["last_solve"])
        assert linearity_audit["backsolve_count"] <= 3
        assert linearity_audit["refinement_count"] <= 2
        case_audits["alpha_A_plus_beta_B"] = linearity_audit
        expected_combo = condensed_solution.duplicate()
        condensed_solution.copy(expected_combo)
        expected_combo.scale(PETSc.ScalarType(alpha))
        expected_combo.axpy(PETSc.ScalarType(beta), solution_b)
        linearity = combo_solution.duplicate()
        combo_solution.copy(linearity)
        linearity.axpy(PETSc.ScalarType(-1.0), expected_combo)
        linearity_norm = float(linearity.norm())
        expected_combo_norm = float(expected_combo.norm())
        linearity_relative = linearity_norm / expected_combo_norm
        assert linearity_relative <= 1.0e-11
        expected_ports = alpha * port_solution + beta * ports_b
        assert (
            linearity_relative
            <= 1.0e-11
        )
        port_linearity_relative = (
            np.linalg.norm(combo_ports - expected_ports)
            / np.linalg.norm(expected_ports)
        )
        assert port_linearity_relative <= 1.0e-11
        assert condensed.inverse.solve_count >= 5
        if comm.rank == 0:
            print(
                json.dumps(
                    {
                        "schema": "task041.h1e.p4_condensed_real_fixture.v1",
                        "mpi_size": comm.size,
                        "full_rows": physical.full_rows,
                        "active_trace_rows": condensed.condensed.active_rows,
                        "interior_rows": condensed.condensed.interior_rows,
                        "port_rows": condensed.condensed.appended_rows,
                        "same_physical_v_mpc": same_physical_v_mpc,
                        "factor_order": "old_full_released_before_new_condensed",
                        "fe_response_relative": float(comparison_relative),
                        "port_response_relative": float(port_relative),
                        "independent_full_residual_relative": float(full_relative),
                        "independent_condensed_residual_relative": float(
                            condensed_residual_relative
                        ),
                        "native_a4_relative": float(
                            audit["physical_relative_residual"]
                        ),
                        "native_a4_tolerance": 1.0e-10,
                        "repeat_relative": float(repeat_relative),
                        "complex_linearity_relative": float(linearity_relative),
                        "complex_port_linearity_relative": float(
                            port_linearity_relative
                        ),
                        "nearzero_rhs_norm": near_rhs_norm,
                        "zero_factor_solve_delta": int(
                            zero_count_after - zero_count_before
                        ),
                        "case_audits": {
                            name: {
                                "status": str(case["status"]),
                                "rhs_norm": float(case["physical_rhs_norm"]),
                                "physical_relative": float(
                                    case["physical_relative_residual"]
                                ),
                                "augmented_relative": float(
                                    case["relative_residual"]
                                ),
                                "backsolve_count": int(case["backsolve_count"]),
                                "refinement_count": int(case["refinement_count"]),
                            }
                            for name, case in case_audits.items()
                        },
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
    finally:
        if condensed is not None:
            condensed.destroy()
        if physical is not None:
            physical.destroy()
        if full_factor is not None:
            full_factor.destroy()
        if full_matrix is not None:
            full_matrix.destroy()
        if full_reference is not None:
            full_reference.destroy()
        if condensed_solution is not None:
            condensed_solution.destroy()
        if full_residual is not None:
            full_residual.destroy()
        if full_solution is not None:
            full_solution.destroy()
        if augmented_rhs is not None:
            augmented_rhs.destroy()
        if fe_rhs is not None:
            fe_rhs.destroy()
        for vector in (
            condensed_augmented,
            condensed_residual,
            rhs_b,
            solution_b,
            solution_a_repeat,
            near_rhs,
            near_solution,
            zero_rhs,
            zero_solution,
            combo_rhs,
            combo_solution,
            expected_combo,
            comparison,
            repeat,
            linearity,
            oracle_rhs,
        ):
            if vector is not None:
                vector.destroy()


def test_task041_h1e_side_inverse_old_new_q_pc_same_side(
    h1e_one_side_real_system,
) -> None:
    """Compare full and cell-condensed BAL_H Q/PC on one borrowed p6 side."""

    side_system = h1e_one_side_real_system
    operator = side_system.A
    source = operator.createVecRight()
    full_source = None
    old_inverse = None
    new_inverse = None
    old_q = None
    old_pc = None
    new_q = None
    new_pc = None
    side_a_before = operator.createVecLeft()
    side_b_before = np.asarray(
        side_system.b.getArray(readonly=True),
        dtype=np.complex128,
    ).copy()
    active_before = None
    full_before = None
    old_p4_audit = None
    old_pc_p4_audit = None
    new_p4_audit = None
    new_pc_p4_audit = None

    def relative_difference(left: PETSc.Vec, right: PETSc.Vec) -> float:
        difference = left.duplicate()
        try:
            left.copy(difference)
            difference.axpy(PETSc.ScalarType(-1.0), right)
            denominator = float(right.norm())
            numerator = float(difference.norm())
            return numerator / denominator if denominator else numerator
        finally:
            difference.destroy()

    def assert_borrowed_side_unchanged() -> None:
        np.testing.assert_array_equal(
            source.getArray(readonly=True),
            active_before,
        )
        np.testing.assert_array_equal(
            full_source.getArray(readonly=True),
            full_before,
        )
        np.testing.assert_array_equal(
            side_system.b.getArray(readonly=True),
            side_b_before,
        )
        side_a_probe = operator.createVecLeft()
        try:
            operator.mult(source, side_a_probe)
            np.testing.assert_array_equal(
                side_a_probe.getArray(readonly=True),
                side_a_before.getArray(readonly=True),
            )
        finally:
            side_a_probe.destroy()

    def p4_audit_values(adapter) -> dict[str, float]:
        last_solve = adapter.diagnostics["p4_factor"]["last_solve"]
        a4_relative = float(last_solve["physical_relative_residual"])
        backsolves = int(last_solve["backsolve_count"])
        assert np.isfinite(a4_relative)
        assert a4_relative <= 1.0e-10
        assert 1 <= backsolves <= 3
        return {
            "a4_relative": a4_relative,
            "backsolve_count": float(backsolves),
        }

    try:
        _fill_active(source, 1.25)
        active_before = np.asarray(
            source.getArray(readonly=True),
            dtype=np.complex128,
        ).copy()
        operator.mult(source, side_a_before)
        old_inverse = build_side_balanced_inverse(
            side_system,
            detailed_timing=True,
        )
        assert old_inverse._side_system is side_system
        full_source = old_inverse._full_action.matrix.createVecRight()
        assert full_source.getSize() == old_inverse._full_action.matrix.getSize()[1]
        inject_active_residual_to_full_p6(
            side_system.static_condensation.condensed,
            source,
            full_source,
        )
        full_before = np.asarray(
            full_source.getArray(readonly=True),
            dtype=np.complex128,
        ).copy()
        old_q = old_inverse._apply_q_callback(full_source)
        old_p4_audit = p4_audit_values(old_inverse)
        old_pc = operator.createVecLeft()
        old_inverse._apply_balanced_pc(source, old_pc)
        old_pc_p4_audit = p4_audit_values(old_inverse)
        assert_borrowed_side_unchanged()
        old_inverse.destroy()
        released = old_inverse.diagnostics
        assert released["destroyed"] is True
        assert released["p4_factor_live"] == 0
        assert released["nested_iterative_ksp_count"] == 0
        assert_borrowed_side_unchanged()
        old_inverse = None

        new_inverse = build_side_balanced_inverse(
            side_system,
            detailed_timing=True,
            p4_inverse_backend="cell_condensed",
        )
        assert new_inverse._side_system is side_system
        assert new_inverse.diagnostics["p4_inverse_backend"] == (
            "cell_condensed"
        )
        new_full_matrix = new_inverse._full_action.matrix
        assert new_full_matrix.getSize()[1] == full_source.getSize()
        assert tuple(new_full_matrix.getOwnershipRange()) == tuple(
            full_source.getOwnershipRange()
        )
        new_q = new_inverse._apply_q_callback(full_source)
        new_p4_audit = p4_audit_values(new_inverse)
        new_pc = operator.createVecLeft()
        new_inverse._apply_balanced_pc(source, new_pc)
        new_pc_p4_audit = p4_audit_values(new_inverse)
        assert_borrowed_side_unchanged()
        new_inverse.destroy()
        released = new_inverse.diagnostics
        assert released["destroyed"] is True
        assert released["p4_factor_live"] == 0
        assert released["nested_iterative_ksp_count"] == 0
        assert_borrowed_side_unchanged()
        new_inverse = None

        q_difference = relative_difference(new_q, old_q)
        pc_difference = relative_difference(new_pc, old_pc)
        assert np.isfinite(q_difference)
        assert np.isfinite(pc_difference)
        assert q_difference <= 1.0e-11
        assert pc_difference <= 1.0e-8
        if MPI.COMM_WORLD.rank == 0:
            print(
                json.dumps(
                    {
                        "schema": "task041.h1e.side_inverse_backend_compare.v1",
                        "mpi_size": MPI.COMM_WORLD.size,
                        "same_p6_side": True,
                        "old_backend": "full",
                        "new_backend": "cell_condensed",
                        "q_relative": float(q_difference),
                        "pc_relative": float(pc_difference),
                        "old_p4_a4_relative": old_p4_audit["a4_relative"],
                        "old_p4_backsolve_count": int(
                            old_p4_audit["backsolve_count"]
                        ),
                        "old_pc_p4_a4_relative": old_pc_p4_audit["a4_relative"],
                        "old_pc_p4_backsolve_count": int(
                            old_pc_p4_audit["backsolve_count"]
                        ),
                        "new_p4_a4_relative": new_p4_audit["a4_relative"],
                        "new_p4_backsolve_count": int(
                            new_p4_audit["backsolve_count"]
                        ),
                        "new_pc_p4_a4_relative": new_pc_p4_audit["a4_relative"],
                        "new_pc_p4_backsolve_count": int(
                            new_pc_p4_audit["backsolve_count"]
                        ),
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
    finally:
        for vector in (new_q, new_pc, old_q, old_pc, source):
            if vector is not None:
                vector.destroy()
        if full_source is not None:
            full_source.destroy()
        side_a_before.destroy()
        if new_inverse is not None:
            new_inverse.destroy()
        if old_inverse is not None:
            old_inverse.destroy()


def test_task041_h1c_j_jh_inverse_and_nonzero_particular(h1c_fixture) -> None:
    data = h1c_fixture
    oracle_audits: list[dict[str, object]] = []
    side_audits: list[dict[str, object]] = []
    for side in ("bottom", "top"):
        p6 = data["p6"][side]
        original = data["condensed"][side]
        condensed = original.static_condensation.condensed
        full_oracle = data["full_oracle"][side]
        condensed_oracle = data["condensed_oracle"][side]
        full_factor = data["full_factors"][side]
        condensed_factor = data["condensed_factors"][side]
        active_rhs = condensed.create_active_vector()
        full_rhs = p6.action.context.input_vector.duplicate()
        source = None
        active_from_full = None
        probe = None
        j_probe = None
        full_aug_rhs = None
        full_aug_solution = None
        full_solution = None
        full_residual = None
        condensed_aug_rhs = None
        condensed_aug_solution = None
        active_solution = None
        condensed_residual = None
        difference = None
        projected = None
        particular_rhs = None
        reconstructed = None
        particular_output = None
        try:
            _fill_active(active_rhs, 2.0)
            assert active_rhs.norm() > 0.0
            source = active_rhs.duplicate()
            active_rhs.copy(source)
            active_before = np.asarray(source.getArray(readonly=True)).copy()
            inject_active_residual_to_full_p6(condensed, active_rhs, full_rhs)
            active_from_full = extract_full_p6_to_active_trace(condensed, full_rhs)
            np.testing.assert_array_equal(
                active_rhs.getArray(readonly=True),
                active_before,
            )
            np.testing.assert_allclose(
                active_from_full.getArray(readonly=True),
                active_rhs.getArray(readonly=True),
                atol=0.0,
                rtol=0.0,
            )

            probe = p6.action.context.input_vector.duplicate()
            _fill_algebraic(probe, p6.action.context.owned_slaves, 3.0)
            j_probe = extract_full_p6_to_active_trace(condensed, probe)
            lhs = j_probe.dot(active_rhs)
            rhs_dot = probe.dot(full_rhs)
            assert (
                abs(lhs - rhs_dot) / max(abs(lhs), abs(rhs_dot), 1.0e-30)
                <= _STRICT_TOLERANCE
            )

            full_aug_rhs = _augmented_vec_from_base(
                full_rhs,
                len(full_oracle.external_modes),
                condensed.comm,
            )
            full_aug_rhs.assemble()
            full_aug_solution, full_oracle_audit = _explicit_factor_solve(
                full_factor,
                full_oracle.A,
                full_aug_rhs,
                full_oracle.n_fe,
                label=f"{side}.full_augmented",
            )
            oracle_audits.append(full_oracle_audit)
            full_solution = _extract_fe_segment(full_aug_solution, full_oracle.n_fe)
            full_residual = p6.matrix.createVecLeft()
            p6.matrix.mult(full_solution, full_residual)
            full_residual.axpy(PETSc.ScalarType(-1.0), full_rhs)
            full_physical_gate = _raw_residual_gate(
                full_residual,
                full_rhs,
                tolerance=_P6_TOLERANCE,
            )
            full_physical_relative = full_physical_gate["relative_residual"]
            projected = extract_full_p6_to_active_trace(condensed, full_solution)

            condensed_aug_rhs = _augmented_vec_from_base(
                active_rhs,
                len(condensed_oracle.external_modes),
                condensed.comm,
            )
            condensed_aug_rhs.assemble()
            condensed_aug_solution, condensed_oracle_audit = _explicit_factor_solve(
                condensed_factor,
                condensed_oracle.A,
                condensed_aug_rhs,
                condensed_oracle.n_fe,
                label=f"{side}.condensed_augmented",
            )
            oracle_audits.append(condensed_oracle_audit)
            active_solution = _extract_fe_segment(
                condensed_aug_solution,
                condensed_oracle.n_fe,
            )
            condensed_residual = original.A.createVecLeft()
            original.A.mult(active_solution, condensed_residual)
            condensed_residual.axpy(PETSc.ScalarType(-1.0), active_rhs)
            condensed_physical_gate = _raw_residual_gate(
                condensed_residual,
                active_rhs,
                tolerance=_P6_TOLERANCE,
            )
            condensed_physical_relative = condensed_physical_gate["relative_residual"]
            difference = projected.duplicate()
            projected.copy(difference)
            difference.axpy(PETSc.ScalarType(-1.0), active_solution)
            bridge_norm = float(difference.norm())
            bridge_solution_norm = float(active_solution.norm())
            bridge_relative = bridge_norm / max(bridge_solution_norm, 1.0e-30)
            bridge_finite = bool(
                np.isfinite(bridge_norm) and np.isfinite(bridge_solution_norm)
                and np.isfinite(bridge_relative)
            )
            bridge_passed = bool(
                bridge_finite and bridge_relative <= _STRICT_TOLERANCE
            )
            if MPI.COMM_WORLD.rank == 0:
                print(
                "H1c bridge pre-particular "
                f"{side}: full_relative={full_physical_relative}, "
                f"condensed_relative={condensed_physical_relative}, "
                f"bridge_relative={bridge_relative:.16e}, "
                f"full_gate={_P6_TOLERANCE:.1e}, "
                f"condensed_gate={_P6_TOLERANCE:.1e}, "
                f"bridge_gate={_STRICT_TOLERANCE:.1e}",
                    flush=True,
                )

            particular_rhs = full_rhs.duplicate()
            particular_rhs.set(0.0)
            first, _last = (int(value) for value in particular_rhs.getOwnershipRange())
            local = particular_rhs.getArray()
            for cell in condensed.cell_recovery_maps:
                rows = np.asarray(cell.interior_original_dofs, dtype=np.int64)
                if len(rows):
                    local[rows - first] = 1.0 + 0.25j
            particular_rhs.assemble()
            recovered = recover_owned_cell_interiors(
                condensed,
                np.zeros(condensed.active_rows, dtype=np.complex128),
                full_rhs=particular_rhs,
            )
            reconstructed = full_rhs.duplicate()
            reconstructed.set(0.0)
            for rows, values in recovered:
                petsc_rows = np.asarray(rows, dtype=PETSc.IntType)
                reconstructed.setValues(
                    petsc_rows,
                    np.asarray(values, dtype=PETSc.ScalarType),
                    addv=PETSc.InsertMode.INSERT_VALUES,
                )
            reconstructed.assemble()
            particular_output = p6.matrix.createVecLeft()
            p6.matrix.mult(reconstructed, particular_output)
            local_sq = 0.0
            for cell in condensed.cell_recovery_maps:
                rows = np.asarray(cell.interior_original_dofs, dtype=np.int64)
                if len(rows):
                    petsc_rows = np.asarray(rows, dtype=PETSc.IntType)
                    error = np.asarray(
                        particular_output.getValues(petsc_rows)
                        - particular_rhs.getValues(petsc_rows),
                        dtype=np.complex128,
                    )
                    local_sq += float(np.vdot(error, error).real)
            residual_norm = float(
                np.sqrt(condensed.comm.allreduce(local_sq, op=MPI.SUM))
            )
            rhs_norm = float(particular_rhs.norm())
            particular_relative = (
                residual_norm / rhs_norm if rhs_norm > 0.0 else None
            )
            particular_finite = bool(
                np.isfinite(residual_norm) and np.isfinite(rhs_norm)
                and (particular_relative is None or np.isfinite(particular_relative))
            )
            particular_passed = bool(
                particular_finite and rhs_norm > 0.0
                and particular_relative <= _STRICT_TOLERANCE
            )
            np.testing.assert_array_equal(
                active_rhs.getArray(readonly=True),
                active_before,
            )
            side_audits.append(
                {
                    "side": side,
                    "full_physical_relative": full_physical_relative,
                    "full_physical_tolerance": full_physical_gate["tolerance"],
                    "full_physical_finite": full_physical_gate["finite"],
                    "full_physical_passed": full_physical_gate["passed"],
                    "condensed_physical_relative": condensed_physical_relative,
                    "condensed_physical_tolerance": condensed_physical_gate[
                        "tolerance"
                    ],
                    "condensed_physical_finite": condensed_physical_gate["finite"],
                    "condensed_physical_passed": condensed_physical_gate["passed"],
                    "bridge_solution_relative": float(bridge_relative),
                    "bridge_solution_tolerance": _STRICT_TOLERANCE,
                    "bridge_solution_finite": bridge_finite,
                    "bridge_solution_passed": bridge_passed,
                    "particular_interior_relative": particular_relative,
                    "particular_interior_tolerance": _STRICT_TOLERANCE,
                    "particular_interior_finite": particular_finite,
                    "particular_interior_passed": particular_passed,
                    "particular_rhs_norm": rhs_norm,
                }
            )
        finally:
            if active_from_full is not None:
                active_from_full.destroy()
            if source is not None:
                source.destroy()
            if probe is not None:
                probe.destroy()
            if j_probe is not None:
                j_probe.destroy()
            if full_aug_rhs is not None:
                full_aug_rhs.destroy()
            if full_aug_solution is not None:
                full_aug_solution.destroy()
            if active_solution is not None:
                active_solution.destroy()
            if full_solution is not None:
                full_solution.destroy()
            if full_residual is not None:
                full_residual.destroy()
            if condensed_aug_rhs is not None:
                condensed_aug_rhs.destroy()
            if condensed_aug_solution is not None:
                condensed_aug_solution.destroy()
            if condensed_residual is not None:
                condensed_residual.destroy()
            if difference is not None:
                difference.destroy()
            if projected is not None:
                projected.destroy()
            if particular_rhs is not None:
                particular_rhs.destroy()
            if reconstructed is not None:
                reconstructed.destroy()
            if particular_output is not None:
                particular_output.destroy()
            active_rhs.destroy()
            full_rhs.destroy()

    if MPI.COMM_WORLD.rank == 0:
        for audit in side_audits:
            print(
                "H1c physical "
                f"{audit['side']}: full_relative={audit['full_physical_relative']}, "
                f"full_gate={audit['full_physical_tolerance']:.1e}, "
                f"full_finite={audit['full_physical_finite']}, "
                f"full_pass={audit['full_physical_passed']}, "
                f"condensed_relative={audit['condensed_physical_relative']}, "
                f"condensed_gate={audit['condensed_physical_tolerance']:.1e}, "
                f"condensed_finite={audit['condensed_physical_finite']}, "
                f"condensed_pass={audit['condensed_physical_passed']}, "
                f"bridge_relative={audit['bridge_solution_relative']:.16e}, "
                f"bridge_gate={audit['bridge_solution_tolerance']:.1e}, "
                f"bridge_finite={audit['bridge_solution_finite']}, "
                f"bridge_pass={audit['bridge_solution_passed']}, "
                f"particular_relative={audit['particular_interior_relative']}, "
                f"particular_gate={audit['particular_interior_tolerance']:.1e}, "
                f"particular_finite={audit['particular_interior_finite']}, "
                f"particular_pass={audit['particular_interior_passed']}, "
                f"particular_rhs_norm={audit['particular_rhs_norm']:.16e}",
                flush=True,
            )
    failed_gates = [
        f"{audit['label']}.{audit['tolerance']:.1e}"
        for audit in oracle_audits
        if not bool(audit["gate_passed"])
    ]
    for audit in side_audits:
            for name in (
            "full_physical",
            "condensed_physical",
            "bridge_solution",
            "particular_interior",
            ):
                if not bool(audit[f"{name}_finite"]):
                    failed_gates.append(f"{audit['side']}.{name}.finite")
                if not bool(audit[f"{name}_passed"]):
                    tolerance = audit[f"{name}_tolerance"]
                    failed_gates.append(
                        f"{audit['side']}.{name}.{float(tolerance):.1e}"
                    )
    assert not failed_gates, (
        "H1c residual/bridge gate failed: " + ", ".join(failed_gates)
    )
