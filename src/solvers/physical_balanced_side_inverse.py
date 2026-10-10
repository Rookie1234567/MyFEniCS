"""Minimal side-trace adapter for the reviewed BAL_H preconditioner.

The borrowed one-sided ``HybridLocalDtnActionSystem.A`` remains the Krylov
operator.  Its right preconditioner injects an active residual with ``J^H``,
applies the full-space BAL_H route, and extracts the active trace with ``J``.
The full p6 action, one p4 factor, p6/p4 owner transfer, and fixed H6 action
are all owned by one adapter instance; the side system and its mesh/MPC data
remain borrowed.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from time import perf_counter
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from .hybrid_local_dtn_action import HybridLocalDtnActionSystem
from .p4_cell_condensed_inverse import P4CellCondensedInverse
from .physical_balanced_coupling import (
    BalancedConstraintRejected,
    PhysicalBalancedCoupling,
)
from .physical_balanced_h6 import H6_DEGREE, FixedH6, build_balanced_h6
from .physical_balanced_physical_operator import (
    P4PhysicalResidualGateError,
    _full_action_inventory,
    _payload_array_inventory,
    _refinement_target_tolerance,
    build_fullspace_physical_dtn_action,
    build_p4_condensed_exact_factor,
    build_p4_exact_factor,
)
from .physical_balanced_same_mesh_transfer import (
    _TASK041_SCHUR_SPEED_V2_PROFILE,
    _TRANSFER_TIMING_NAMES,
    build_same_mesh_hcurl_owner_transfer,
)
from .physical_balanced_trace_bridge import (
    extract_full_p6_to_active_trace,
    inject_active_residual_to_full_p6,
)

__all__ = (
    "FIXED_PHYSICAL_BALH_MODAL_FEEDBACK_METHOD",
    "FixedH6ActiveTraceAction",
    "FixedPhysicalBalancedActiveTraceAction",
    "SideBalancedInverse",
    "build_side_balanced_inverse",
)


_MAX_DENSE_COLUMNS = 32
_ALLOWED_KSP = ((128, 1.0e-2), (256, 1.0e-4))
_DETAIL_TIMING_NAMES = (
    "q_ph_seconds",
    "q_ph_cell_adjoint_seconds",
    "q_ph_dual_reduce_seconds",
    "q_ph_route_sort_index_seconds",
    "q_ph_mpi_exchange_seconds",
    "q_ph_duplicate_row_check_seconds",
    "q_ph_ghost_mpc_prepare_seconds",
    "q_ph_ghost_mpc_check_seconds",
    "q_augmented_rhs_extract_seconds",
   "q_factor_solve_seconds",
    "q_p4_storage_rhs_reduction_seconds",
    "q_p4_solution_recovery_seconds",
   "q_a4_residual_refinement_seconds",
   "q_physical_action_matrix_mult_seconds",
    "q_p_seconds",
    "q_p_local_candidate_generation_seconds",
    "q_p_route_sort_index_seconds",
    "q_p_mpi_exchange_seconds",
    "q_p_duplicate_row_check_seconds",
    "q_p_ghost_mpc_prepare_seconds",
    "q_p_ghost_mpc_check_seconds",
    "balance_ph_seconds",
    "balance_ph_cell_adjoint_seconds",
    "balance_ph_dual_reduce_seconds",
    "balance_ph_route_sort_index_seconds",
    "balance_ph_mpi_exchange_seconds",
    "balance_ph_duplicate_row_check_seconds",
    "balance_ph_ghost_mpc_prepare_seconds",
    "balance_ph_ghost_mpc_check_seconds",
    "balance_a6_seconds",
    "balance_h6_seconds",
    "balance_jh_inject_allocate_seconds",
)
_DETAIL_TIMING_SEMANTICS = {
    "q_ph_seconds": "inclusive q PH transfer; q_ph_* intervals are nested",
    "q_p_seconds": "inclusive q P transfer; q_p_* intervals are nested",
    "balance_ph_seconds": (
        "inclusive BAL_H balance PH transfer; balance_ph_* intervals are nested"
    ),
    "*_route_sort_index_seconds": (
        "local owner routing, sorting, counts, displacements, and index ordering; "
        "excludes MPI calls"
    ),
    "*_mpi_exchange_seconds": (
        "only the transfer Alltoall/Alltoallv or PH ghostUpdate call; for PH "
        "this is nested in *_ghost_mpc_check_seconds, while prepare/check can "
        "include other communication and are not additive MPI totals"
    ),
    "*_duplicate_row_check_seconds": (
        "owner-row duplicate consistency check, including its existing scalar MAX"
    ),
    "*_ghost_mpc_prepare_seconds": "input copy, ghost update, and MPC preparation",
    "*_ghost_mpc_check_seconds": (
        "output ghost/MPC finalization, zero/check, other communication, and "
        "finite validation; PH mpi_exchange_seconds is nested here"
    ),
   "q_a4_residual_refinement_seconds": (
       "inclusive extraction, Vec allocation, physical action, norm, and audit work"
   ),
    "q_p4_storage_rhs_reduction_seconds": (
        "cell-condensed storage RHS reduction only; not factor or recovery"
    ),
    "q_p4_solution_recovery_seconds": (
        "cell-condensed active/interior/port recovery only; not factor"
    ),
    "q_physical_action_matrix_mult_seconds": (
        "physical_action.matrix.mult only; nested inside q_a4_residual_refinement_seconds"
    ),
    "balance_jh_inject_allocate_seconds": (
        "JH injection and its Vec allocation only; not all allocation/packing"
    ),
}
# Native PETSc names the task's DIVERGED_ITS budget result DIVERGED_MAX_IT.
_DIVERGED_ITS = int(PETSc.KSP.ConvergedReason.DIVERGED_MAX_IT)
_P4_INVERSE_BACKENDS = frozenset({"full", "cell_condensed"})
FIXED_PHYSICAL_BALH_MODAL_FEEDBACK_METHOD = "fixed_physical_balh_once"
_V12_RESTART64_SELECTION_RULE = (
    "same_rhs_eta64_at_most_0.9_eta32_and_max_rank_trial_wall_with_one_setup_not_higher"
    "_and_log_residual_reduction_per_wall_not_lower"
)


def _v12_restart64_selection_evidence(
    eta32: Any,
    eta64: Any,
    restart32_work_by_rank: Any,
    restart64_rank_records: Any,
    *,
    trial_elapsed_max_rank_seconds: Any,
    trial_setup_elapsed_max_rank_seconds: Any,
) -> dict[str, Any]:
    """Apply the fixed same-RHS residual and wall-cost rule to one trial."""

    evidence: dict[str, Any] = {
        "rule_id": _V12_RESTART64_SELECTION_RULE,
        "residual_improved_by_at_least_10_percent": False,
        "max_rank_trial_wall_with_one_setup_not_higher": False,
        "log_residual_reduction_per_wall_not_lower": False,
        "restart32_max_rank_side_wall_seconds": None,
        "restart64_max_rank_side_solve_wall_seconds": None,
        "restart64_max_rank_setup_wall_seconds": None,
        "restart64_max_rank_trial_wall_with_setup_seconds": None,
        "restart32_log_residual_reduction_per_wall": None,
        "restart64_log_residual_reduction_per_wall": None,
        "eligible_for_64": False,
        "reason": "missing_or_nonfinite_same_rhs_cost_or_residual_evidence",
    }

    def finite_number(value: Any, *, strictly_positive: bool = False) -> float | None:
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
        ):
            return None
        result = float(value)
        if result < 0.0 or (strictly_positive and result <= 0.0):
            return None
        return result

    eta32_value = finite_number(eta32, strictly_positive=True)
    eta64_value = finite_number(eta64, strictly_positive=True)
    if (
        eta32_value is None
        or eta64_value is None
        or eta32_value >= 1.0
        or eta64_value >= 1.0
        or not isinstance(restart32_work_by_rank, list)
        or not isinstance(restart64_rank_records, list)
        or not restart32_work_by_rank
        or len(restart32_work_by_rank) != len(restart64_rank_records)
    ):
        evidence["reason"] = "invalid_residual_or_rank_cost_evidence"
        return evidence

    restart32_local_walls: list[float] = []
    restart32_reported_maxes: list[float] = []
    restart64_local_walls: list[float] = []
    restart64_setup_local_walls: list[float] = []
    for rank, (baseline, trial) in enumerate(
        zip(restart32_work_by_rank, restart64_rank_records, strict=True)
    ):
        if (
            not isinstance(baseline, Mapping)
            or type(baseline.get("rank")) is not int
            or baseline.get("rank") != rank
            or not isinstance(trial, Mapping)
            or type(trial.get("rank")) is not int
            or trial.get("rank") != rank
        ):
            evidence["reason"] = "rank_cost_evidence_mismatch"
            return evidence
        baseline_local = finite_number(
            baseline.get("rank_local_elapsed_seconds"), strictly_positive=True
        )
        baseline_max = finite_number(
            baseline.get("max_rank_elapsed_seconds"), strictly_positive=True
        )
        trial_local = finite_number(
            trial.get("elapsed_local_seconds"), strictly_positive=True
        )
        setup_local = finite_number(
            trial.get("ksp_setup_elapsed_local_seconds")
        )
        if any(
            value is None
            for value in (baseline_local, baseline_max, trial_local, setup_local)
        ):
            evidence["reason"] = "missing_or_nonfinite_same_rhs_rank_timing"
            return evidence
        restart32_local_walls.append(float(baseline_local))
        restart32_reported_maxes.append(float(baseline_max))
        restart64_local_walls.append(float(trial_local))
        restart64_setup_local_walls.append(float(setup_local))

    restart32_max_rank = max(restart32_local_walls)
    restart64_max_rank = max(restart64_local_walls)
    restart64_setup_max_rank = max(restart64_setup_local_walls)
    restart64_trial_max_rank_with_setup = max(
        solve_wall + setup_wall
        for solve_wall, setup_wall in zip(
            restart64_local_walls, restart64_setup_local_walls, strict=True
        )
    )
    reported_trial_elapsed = finite_number(
        trial_elapsed_max_rank_seconds, strictly_positive=True
    )
    reported_trial_setup = finite_number(
        trial_setup_elapsed_max_rank_seconds
    )
    if (
        reported_trial_elapsed is None
        or reported_trial_setup is None
        or not all(
            math.isclose(value, restart32_max_rank, rel_tol=1.0e-12, abs_tol=1.0e-15)
            for value in restart32_reported_maxes
        )
        or not math.isclose(
            reported_trial_elapsed,
            restart64_max_rank,
            rel_tol=1.0e-12,
            abs_tol=1.0e-15,
        )
        or not math.isclose(
            reported_trial_setup,
            restart64_setup_max_rank,
            rel_tol=1.0e-12,
            abs_tol=1.0e-15,
        )
    ):
        evidence["reason"] = "reported_max_rank_cost_does_not_match_rank_records"
        return evidence

    try:
        restart32_log_rate = -math.log(eta32_value) / restart32_max_rank
        restart64_log_rate = (
            -math.log(eta64_value) / restart64_trial_max_rank_with_setup
        )
    except (OverflowError, ZeroDivisionError):
        evidence["reason"] = "nonfinite_log_residual_cost"
        return evidence
    if not math.isfinite(restart32_log_rate) or not math.isfinite(restart64_log_rate):
        evidence["reason"] = "nonfinite_log_residual_cost"
        return evidence

    residual_improved = eta64_value <= 0.9 * eta32_value
    wall_not_higher = restart64_trial_max_rank_with_setup <= restart32_max_rank
    log_rate_not_lower = restart64_log_rate >= restart32_log_rate
    eligible = bool(residual_improved and wall_not_higher and log_rate_not_lower)
    evidence.update(
        {
            "residual_improved_by_at_least_10_percent": residual_improved,
            "max_rank_trial_wall_with_one_setup_not_higher": wall_not_higher,
            "log_residual_reduction_per_wall_not_lower": log_rate_not_lower,
            "restart32_max_rank_side_wall_seconds": restart32_max_rank,
            "restart64_max_rank_side_solve_wall_seconds": restart64_max_rank,
            "restart64_max_rank_setup_wall_seconds": restart64_setup_max_rank,
            "restart64_max_rank_trial_wall_with_setup_seconds": (
                restart64_trial_max_rank_with_setup
            ),
            "restart32_log_residual_reduction_per_wall": restart32_log_rate,
            "restart64_log_residual_reduction_per_wall": restart64_log_rate,
            "eligible_for_64": eligible,
            "reason": (
                "residual_and_cost_improved"
                if eligible
                else "restart64_did_not_improve_residual_and_cost_together"
            ),
        }
    )
    return evidence


def _p4_solve_count(p4_factor: Any) -> int:
    """Read the solve counter shared by the two explicit p4 backends."""

    diagnostics = p4_factor.diagnostics
    research_factor = diagnostics.get("research_factor")
    if isinstance(research_factor, Mapping):
        return int(research_factor["solve_count"])
    return int(diagnostics["factor_solve_count"])


def _fixed_q_cell_solve_audit(
    p4_factor: Any,
    *,
    solve_count_before: int,
    solve_count_after: int,
) -> tuple[int, int]:
    """Validate both audited inverse calls that implement one fixed Q correction."""

    delta_total = int(solve_count_after) - int(solve_count_before)
    if delta_total < 0:
        raise RuntimeError("fixed-Q P4 solve counter moved backwards")
    inverse = getattr(p4_factor, "inverse", None)
    if not isinstance(inverse, P4CellCondensedInverse):
        raise TypeError("cell-condensed fixed-Q factor has no P4CellCondensedInverse")
    diagnostics = p4_factor.diagnostics
    last_solve = diagnostics.get("last_solve")
    if not isinstance(last_solve, Mapping):
        raise TypeError("fixed-Q P4 factor has no current solve audit")
    if (
        type(last_solve.get("mathematical_correction_steps")) is not int
        or last_solve["mathematical_correction_steps"] != 1
    ):
        raise RuntimeError("fixed-Q P4 audit lost its one mathematical correction")
    if (
        type(last_solve.get("factor_solve_count_start")) is not int
        or last_solve["factor_solve_count_start"] != int(solve_count_before)
    ):
        raise RuntimeError("fixed-Q P4 audit has a stale starting solve count")
    if (
        type(last_solve.get("factor_solve_count_after")) is not int
        or last_solve["factor_solve_count_after"] != int(solve_count_after)
    ):
        raise RuntimeError("fixed-Q P4 audit has a stale ending solve count")
    history = last_solve.get("inverse_apply_history")
    if not isinstance(history, (list, tuple)) or len(history) != 2:
        raise RuntimeError("fixed-Q P4 audit must contain initial and correction calls")
    if any(not isinstance(entry, Mapping) for entry in history):
        raise RuntimeError("fixed-Q P4 inverse-call audit is malformed")
    if tuple(entry.get("step") for entry in history) != (
        "initial",
        "correction_1",
    ):
        raise RuntimeError("fixed-Q P4 inverse-call order changed")
    identities = [entry.get("factor_identity_local") for entry in history]
    matrices = [entry.get("matrix_identity") for entry in history]
    if (
        any(type(identity) is not int for identity in identities)
        or any(identity != id(inverse.factor) for identity in identities)
        or any(matrix != matrices[0] for matrix in matrices[1:])
        or not isinstance(matrices[0], Mapping)
    ):
        raise RuntimeError("fixed-Q P4 calls did not retain one factor/matrix identity")

    expected_before = int(solve_count_before)
    deltas: list[int] = []
    for entry in history:
        raw = entry.get("inverse_audit")
        if not isinstance(raw, Mapping):
            raise TypeError("fixed-Q P4 inverse-call audit payload is missing")
        status = entry.get("status")
        delta = entry.get("factor_solve_delta")
        count_before = entry.get("factor_solve_count_before")
        count_after = entry.get("factor_solve_count_after")
        if (
            type(delta) is not int
            or delta not in (0, 1)
            or type(count_before) is not int
            or type(count_after) is not int
            or count_before != expected_before
            or count_after - count_before != delta
            or type(raw.get("factor_solve_call_delta")) is not int
            or raw.get("factor_solve_call_delta") != delta
            or type(raw.get("factor_solve_count")) is not int
            or raw.get("factor_solve_count") != count_after
            or raw.get("status") != status
        ):
            raise RuntimeError("fixed-Q per-call audit and counter chain disagree")
        global_zero = entry.get("global_rhs_exact_zero") is True
        port_zero = entry.get("port_rhs_exact_zero") is True
        rhs_norm = entry.get("global_rhs_norm")
        if (
            type(rhs_norm) is not float
            or not np.isfinite(rhs_norm)
            or rhs_norm < 0.0
            or (rhs_norm == 0.0) != global_zero
            or type(entry.get("global_rhs_exact_zero")) is not bool
            or type(entry.get("port_rhs_exact_zero")) is not bool
        ):
            raise RuntimeError("fixed-Q global exact-zero evidence is inconsistent")
        if status == "ZERO_RHS_DIRECT_ZERO":
            if (
                delta != 0
                or not global_zero
                or not port_zero
                or raw.get("slave_zero") is not True
                or raw.get("port_rhs_zero") is not True
            ):
                raise RuntimeError("fixed-Q zero solve lacks direct-zero evidence")
        elif status == "SOLVE_COMPLETED":
            if delta != 1 or (global_zero and port_zero):
                raise RuntimeError("fixed-Q nonzero solve has inconsistent zero evidence")
            if raw.get("matrix_identity") != entry.get("matrix_identity"):
                raise RuntimeError("fixed-Q solve audit changed source matrix identity")
        else:
            raise RuntimeError(f"fixed-Q call has unsupported status {status!r}")
        deltas.append(delta)
        expected_before = count_after

    if expected_before != int(solve_count_after) or sum(deltas) != delta_total:
        raise RuntimeError("fixed-Q per-call deltas do not sum to the live counter")
    if (
        type(last_solve.get("factor_solve_delta_sum")) is not int
        or last_solve["factor_solve_delta_sum"] != delta_total
    ):
        raise RuntimeError("fixed-Q P4 audit total solve delta is inconsistent")
    if (
        type(last_solve.get("backsolve_count")) is not int
        or last_solve["backsolve_count"] != delta_total
    ):
        raise RuntimeError("fixed-Q residual audit solve count is inconsistent")
    return deltas[0], deltas[1]

_GMRES_RESTART_LIBRARY: Any | None = None
_GMRES_RESTART_FUNCTION: Any | None = None
_GMRES_PREALLOCATE_FUNCTION: Any | None = None
_GMRES_SET_ORTHOGONALIZATION_FUNCTION: Any | None = None
_GMRES_GET_ORTHOGONALIZATION_FUNCTION: Any | None = None
_GMRES_MGS_FUNCTION: Any | None = None


def _live_gmres_restart(ksp: PETSc.KSP) -> int:
    """Read FGMRES restart from the loaded PETSc implementation.

    petsc4py 3.19 exposes ``setGMRESRestart`` but not its matching getter.
    The opt-in contract audit therefore calls the exact PETSc symbol through
    the already loaded petsc4py extension; ordinary solves never initialize
    this narrow audit-only path.
    """

    import ctypes

    global _GMRES_RESTART_FUNCTION, _GMRES_RESTART_LIBRARY
    if _GMRES_RESTART_FUNCTION is None:
        if np.dtype(PETSc.IntType) != np.dtype(np.int32):
            raise RuntimeError(
                "KSPGMRESGetRestart requires the qualified PetscInt=int32 ABI"
            )
        try:
            library = ctypes.CDLL(PETSc.__file__)
            function = library.KSPGMRESGetRestart
        except (AttributeError, OSError) as exc:
            raise RuntimeError(
                "loaded PETSc extension has no KSPGMRESGetRestart symbol"
            ) from exc
        function.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_int32),
        ]
        function.restype = ctypes.c_int
        _GMRES_RESTART_LIBRARY = library
        _GMRES_RESTART_FUNCTION = function

    restart = ctypes.c_int32()
    error_code = int(
        _GMRES_RESTART_FUNCTION(
            ctypes.c_void_p(int(ksp.handle)),
            ctypes.byref(restart),
        )
    )
    if error_code != 0:
        raise RuntimeError(
            f"KSPGMRESGetRestart failed with PetscErrorCode={error_code}"
        )
    return int(restart.value)


def _gmres_native_stage_functions() -> tuple[Any, Any, Any, Any]:
    """Load only public PETSc GMRES controls used by the explicit restart trial."""

    import ctypes

    global _GMRES_RESTART_LIBRARY
    global _GMRES_PREALLOCATE_FUNCTION
    global _GMRES_SET_ORTHOGONALIZATION_FUNCTION
    global _GMRES_GET_ORTHOGONALIZATION_FUNCTION
    global _GMRES_MGS_FUNCTION
    if _GMRES_PREALLOCATE_FUNCTION is None:
        try:
            library = ctypes.CDLL(PETSc.__file__)
            preallocate = library.KSPGMRESSetPreAllocateVectors
            set_orthogonalization = library.KSPGMRESSetOrthogonalization
            get_orthogonalization = library.KSPGMRESGetOrthogonalization
            mgs = library.KSPGMRESModifiedGramSchmidtOrthogonalization
        except (AttributeError, OSError) as exc:
            raise RuntimeError(
                "loaded PETSc lacks the public GMRES restart-trial controls"
            ) from exc
        preallocate.argtypes = [ctypes.c_void_p]
        preallocate.restype = ctypes.c_int
        set_orthogonalization.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        set_orthogonalization.restype = ctypes.c_int
        get_orthogonalization.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        get_orthogonalization.restype = ctypes.c_int
        mgs.restype = ctypes.c_void_p
        _GMRES_RESTART_LIBRARY = library
        _GMRES_PREALLOCATE_FUNCTION = preallocate
        _GMRES_SET_ORTHOGONALIZATION_FUNCTION = set_orthogonalization
        _GMRES_GET_ORTHOGONALIZATION_FUNCTION = get_orthogonalization
        _GMRES_MGS_FUNCTION = mgs
    return (
        _GMRES_PREALLOCATE_FUNCTION,
        _GMRES_SET_ORTHOGONALIZATION_FUNCTION,
        _GMRES_GET_ORTHOGONALIZATION_FUNCTION,
        _GMRES_MGS_FUNCTION,
    )


def _configure_gmres_restart_trial(ksp: PETSc.KSP) -> dict[str, Any]:
    """Freeze public FGMRES preallocation and MGS before candidate setup."""

    import ctypes

    preallocate, set_orthogonalization, get_orthogonalization, mgs = (
        _gmres_native_stage_functions()
    )
    handle = ctypes.c_void_p(int(ksp.handle))
    preallocate_error = int(preallocate(handle))
    mgs_address = int(ctypes.cast(mgs, ctypes.c_void_p).value or 0)
    set_error = int(
        set_orthogonalization(handle, ctypes.c_void_p(mgs_address))
    )
    observed = ctypes.c_void_p()
    get_error = int(get_orthogonalization(handle, ctypes.byref(observed)))
    if preallocate_error or set_error or get_error:
        raise RuntimeError(
            "PETSc FGMRES restart64 setup failed "
            f"(preallocate={preallocate_error}, set_mgs={set_error}, get={get_error})"
        )
    if int(observed.value or 0) != mgs_address:
        raise RuntimeError("PETSc FGMRES did not retain modified Gram-Schmidt")
    return {
        "preallocate_vectors": True,
        "orthogonalization": "modified_gram_schmidt",
        "set_from_public_petsc_api": True,
        "readback_matches": True,
    }


def _owner_transfer_primal_route_plan_snapshot(
    owner_transfer: Any,
) -> dict[str, Any]:
    """Return local byte/count facts without copying or communicating arrays."""

    comm = getattr(owner_transfer, "comm", None)
    rank = getattr(comm, "rank", None)
    comm_size = getattr(comm, "size", None)
    enabled = bool(getattr(owner_transfer, "_reuse_primal_route_plan", False))
    if not enabled:
        return {
            "status": "disabled",
            "enabled": False,
            "captured": False,
            "rank": None if rank is None else int(rank),
            "communicator_size": None if comm_size is None else int(comm_size),
            "N_r": None,
            "M_r": None,
            "array_nbytes_local": None,
            "persistent_index_payload_bytes_local": None,
            "payload_formula_bytes_local": None,
            "payload_formula": "16*N_r + 20*M_r + 16*P",
        }
    plan = getattr(owner_transfer, "_primal_route_plan", None)
    if plan is None:
        return {
            "status": "not_captured_yet",
            "enabled": True,
            "captured": False,
            "rank": None if rank is None else int(rank),
            "communicator_size": None if comm_size is None else int(comm_size),
            "N_r": None,
            "M_r": None,
            "array_nbytes_local": None,
            "persistent_index_payload_bytes_local": None,
            "payload_formula_bytes_local": None,
            "payload_formula": "16*N_r + 20*M_r + 16*P",
        }

    array_names = (
        "candidate_ids",
        "send_order",
        "recv_order",
        "recv_ids",
        "source_ranks",
        "send_counts",
        "send_displacements",
        "recv_counts",
        "recv_displacements",
    )
    array_nbytes: dict[str, int | None] = {}
    for name in array_names:
        value = getattr(plan, name, None)
        raw_nbytes = getattr(value, "nbytes", None)
        array_nbytes[name] = (
            int(raw_nbytes)
            if isinstance(raw_nbytes, (int, np.integer))
            and not isinstance(raw_nbytes, (bool, np.bool_))
            else None
        )
    send_order = getattr(plan, "send_order", None)
    recv_order = getattr(plan, "recv_order", None)
    N_r = getattr(send_order, "size", None)
    M_r = getattr(recv_order, "size", None)
    N_r = int(N_r) if isinstance(N_r, (int, np.integer)) else None
    M_r = int(M_r) if isinstance(M_r, (int, np.integer)) else None
    payload_bytes = (
        sum(int(value) for value in array_nbytes.values())
        if all(value is not None for value in array_nbytes.values())
        else None
    )
    formula_bytes = (
        16 * N_r + 20 * M_r + 16 * int(comm_size)
        if N_r is not None and M_r is not None and comm_size is not None
        else None
    )
    return {
        "status": "captured" if payload_bytes is not None else "captured_size_unknown",
        "enabled": True,
        "captured": True,
        "rank": None if rank is None else int(rank),
        "communicator_size": None if comm_size is None else int(comm_size),
        "N_r": N_r,
        "M_r": M_r,
        "array_nbytes_local": array_nbytes,
        "persistent_index_payload_bytes_local": payload_bytes,
        "payload_formula_bytes_local": formula_bytes,
        "payload_formula_matches": (
            None
            if payload_bytes is None or formula_bytes is None
            else payload_bytes == formula_bytes
        ),
        "payload_formula": "16*N_r + 20*M_r + 16*P",
    }


def _compact_owner_transfer_storage_payload(owner_transfer: Any) -> dict[str, Any]:
    owner_audit = owner_transfer.audit
    orientation_storage = owner_audit.get("orientation_storage")
    if not isinstance(orientation_storage, Mapping):
        raise TypeError("compact owner-transfer storage audit is missing")
    mesh = owner_transfer.mesh
    cell_map = mesh.topology.index_map(mesh.topology.dim)
    seed_key = orientation_storage.get("seed_key")
    if (
        orientation_storage.get("representation") != "compact_entity_blocks"
        or orientation_storage.get("key_order")
        != ["coarse_cell_info", "fine_cell_info"]
        or orientation_storage.get("seed_included_in_unique_key_count") is not True
        or not isinstance(seed_key, list)
        or len(seed_key) != 2
        or any(type(value) is not int for value in seed_key)
        or type(orientation_storage.get("seed_key_has_cell_record")) is not bool
    ):
        raise RuntimeError("compact owner-transfer storage audit is incomplete")

    scalar_fields = {
        "K_local": orientation_storage.get("unique_key_count_including_seed"),
        "record_unique_key_count_local": orientation_storage.get(
            "record_unique_key_count"
        ),
        "record_count_local": orientation_storage.get("record_count_local"),
        "canonical_R_bytes_local": orientation_storage.get(
            "canonical_R_bytes_local"
        ),
        "nonidentity_transform_block_bytes_local": orientation_storage.get(
            "nonidentity_transform_block_bytes_local"
        ),
        "entity_index_payload_bytes_local": orientation_storage.get(
            "entity_index_bytes_local"
        ),
        "unique_numeric_array_payload_bytes_local": orientation_storage.get(
            "unique_numeric_array_payload_bytes_local"
        ),
    }
    if any(
        type(value) is not int or value < 0
        for value in scalar_fields.values()
    ):
        raise RuntimeError("compact owner-transfer payload counts are invalid")
    if (
        scalar_fields["record_unique_key_count_local"]
        > scalar_fields["record_count_local"]
        or scalar_fields["K_local"]
        != scalar_fields["record_unique_key_count_local"]
        + int(not orientation_storage["seed_key_has_cell_record"])
        or scalar_fields["unique_numeric_array_payload_bytes_local"]
        != scalar_fields["canonical_R_bytes_local"]
        + scalar_fields["nonidentity_transform_block_bytes_local"]
        + scalar_fields["entity_index_payload_bytes_local"]
    ):
        raise RuntimeError("compact owner-transfer storage totals are inconsistent")

    return {
        **scalar_fields,
        "seed_key_coarse_fine": [int(value) for value in seed_key],
        "seed_has_cell_record": orientation_storage["seed_key_has_cell_record"],
        "owned_cell_count_local": int(cell_map.size_local),
        "owned_plus_ghost_cell_count_local": int(
            cell_map.size_local + cell_map.num_ghosts
        ),
    }


def _compact_owner_transfer_storage_local_record(
    owner_transfer: Any,
) -> dict[str, Any]:
    """Capture local scalar facts without communicating or leaving a rank."""

    rank = None
    try:
        rank = int(owner_transfer.comm.rank)
        payload = _compact_owner_transfer_storage_payload(owner_transfer)
    except Exception as exc:  # noqa: BLE001 - exchange rank-local schema errors
        return {
            "rank": rank,
            "error": f"{type(exc).__name__}: {str(exc)[:240]}",
            "payload": None,
        }
    return {"rank": rank, "error": None, "payload": payload}


def _aggregate_compact_owner_transfer_storage_records(
    gathered: Any,
    *,
    communicator_size: int,
) -> dict[str, Any]:
    """Validate one already-completed setup gather and compute rank sums."""

    if not isinstance(gathered, (tuple, list)) or len(gathered) != int(
        communicator_size
    ):
        raise RuntimeError("compact transfer inventory gather is incomplete")
    records = [dict(record) for record in gathered]
    local_errors = [
        {"rank": record["rank"], "error": record.get("error")}
        for record in records
        if record.get("error") is not None
    ]
    if local_errors:
        raise RuntimeError(
            "compact transfer inventory rejected collectively after setup "
            f"allgather: {local_errors}"
        )
    if [record.get("rank") for record in records] != list(
        range(int(communicator_size))
    ):
        raise RuntimeError("compact transfer inventory rank set is incomplete")
    if any(not isinstance(record.get("payload"), Mapping) for record in records):
        raise RuntimeError("compact transfer inventory payload is incomplete")
    rank_records = [
        {"rank": record["rank"], **dict(record["payload"])}
        for record in records
    ]

    summed_fields = (
        "K_local",
        "owned_cell_count_local",
        "owned_plus_ghost_cell_count_local",
        "canonical_R_bytes_local",
        "nonidentity_transform_block_bytes_local",
        "entity_index_payload_bytes_local",
        "unique_numeric_array_payload_bytes_local",
    )
    cross_rank_total = {
        f"rank_local_{field.removesuffix('_local')}_sum": sum(
            int(record[field]) for record in rank_records
        )
        for field in summed_fields
    }
    return {
        "schema": "task041.bal_h.compact_orientation_storage_inventory.v1",
        "aggregation": "one setup allgather of scalar rank records",
        "K_definition": (
            "per-rank unique (coarse_cell_info,fine_cell_info) keys; the local "
            "seed key is included even when that rank owns no cell record"
        ),
        "rank_records": rank_records,
        "cross_rank_total": {
            "semantics": (
                "sum of rank-local payloads; owned-plus-ghost cells can be "
                "counted on multiple ranks"
            ),
            **cross_rank_total,
        },
    }


def _owner_transfer_inventory(
    owner_transfer: Any,
    *,
    compact_orientation_inventory: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    owner_audit = owner_transfer.audit
    orientation_storage = owner_audit.get("orientation_storage")
    compact = isinstance(orientation_storage, Mapping)
    if compact != (compact_orientation_inventory is not None):
        raise RuntimeError(
            "compact transfer inventory argument does not match owner representation"
        )
    if compact and compact_orientation_inventory.get("schema") != (
        "task041.bal_h.compact_orientation_storage_inventory.v1"
    ):
        raise RuntimeError("compact transfer inventory has an unsupported schema")
    # Compact owners expose no dense matrix. Do not touch local_transfer.matrix
    # on that path; the scalar orientation audit is the storage authority.
    local_map = None if compact else owner_transfer.local_transfer.matrix
    if not compact and local_map is None:
        raise RuntimeError("dense owner transfer has no canonical local matrix")
    owned_objects = [
        _payload_array_inventory(
            owner_transfer._coarse_work.x.array,
            label="transfer.coarse_work_array",
            ownership="SameMeshHcurlOwnerTransfer until destroy",
        ),
        _payload_array_inventory(
            owner_transfer._fine_work.x.array,
            label="transfer.fine_work_array",
            ownership="SameMeshHcurlOwnerTransfer until destroy",
        ),
        _payload_array_inventory(
            owner_transfer._dual_reduction_work,
            label="transfer.dual_reduction_work",
            ownership="SameMeshHcurlOwnerTransfer until destroy",
        ),
    ]
    if not compact:
        owned_objects.append(
            _payload_array_inventory(
                local_map,
                label="transfer.canonical_reference_map",
                ownership="local transfer cache until destroy",
            )
        )
    inventory = {
        "stage_scope": "rank_local",
        "owned_objects": owned_objects,
        "borrowed_objects": [
            {
                "label": "transfer.fine_coarse_spaces_mpc",
                "ownership": "borrowed from side systems; not destroyed here",
                "payload_bytes_local": "unknown",
            }
        ],
        "row_inventory": {
            "fine_global_rows": int(owner_transfer.fine_space.dofmap.index_map.size_global),
            "coarse_global_rows": int(owner_transfer.coarse_space.dofmap.index_map.size_global),
            "fine_owned_rows": int(owner_transfer._fine_owned_size),
            "coarse_owned_rows": int(owner_transfer._coarse_owned_size),
        },
        "canonical_map_cache": (
            "only the canonical local map is listed; per-cell cache references "
            "are not expanded or summed"
        ),
        "native_workspace_bytes": "unknown",
    }
    if compact:
        inventory["stage_scope"] = "rank_local_with_setup_scalar_allgather"
        inventory["canonical_map_cache"] = (
            "compact adapter storage is listed once per unique orientation key; "
            "per-cell record references are not expanded or summed"
        )
        inventory["compact_orientation_storage"] = dict(
            compact_orientation_inventory
        )
    return inventory


def _side_adapter_inventory(inverse: SideBalancedInverse) -> dict[str, Any]:
    return {
        "stage_scope": "rank_local",
        "owned_objects": [
            {
                "label": "adapter.ksp",
                "kind": "PETSc.KSP",
                "ownership": "SideBalancedInverse until destroy",
                "payload_bytes_local": "unknown",
            },
            {
                "label": "adapter.full_action_p4_transfer_h6",
                "kind": "owned component set",
                "ownership": "SideBalancedInverse until destroy",
                "payload_bytes_local": "see component ready events; no resumming",
            },
        ],
        "borrowed_objects": [
            {
                "label": "adapter.side_system_operator_and_condensed_data",
                "ownership": "borrowed from side system; not destroyed here",
                "payload_bytes_local": "unknown",
            }
        ],
        "native_workspace_bytes": "unknown",
    }


def _dense_types(matrix: PETSc.Mat) -> bool:
    return str(matrix.getType()).lower() in {"seqdense", "dense", "mpidense"}


def _context_apply_count(matrix: PETSc.Mat) -> int | None:
    if str(matrix.getType()).lower() != "python":
        return None
    try:
        context = matrix.getPythonContext()
    except (AttributeError, PETSc.Error):
        return None
    value = getattr(context, "apply_count", None)
    return None if value is None else int(value)


def _same_handle(left: Any, right: Any) -> bool:
    if left is right:
        return True
    try:
        return int(left.handle) == int(right.handle)
    except (AttributeError, TypeError, ValueError):
        return False


def _local_complex_vec_sha256(vector: PETSc.Vec) -> str:
    """Hash an owned complex128 Vec view without materializing a byte copy."""

    values = np.asarray(vector.getArray(readonly=True))
    if values.dtype != np.dtype(np.complex128) or not values.flags.c_contiguous:
        raise TypeError("restart-trial Vec hashing requires a contiguous complex128 view")
    return hashlib.sha256(memoryview(values).cast("B")).hexdigest()


def _classify_ksp_result(
    reason: int,
    iterations: int,
    max_it: int,
) -> tuple[str, bool]:
    """Keep PETSc's raw reason while admitting only the fixed ITS budget."""

    reason = int(reason)
    iterations = int(iterations)
    max_it = int(max_it)
    if iterations < 0 or iterations > max_it:
        raise RuntimeError(
            "BAL_H side KSP returned iterations outside its fixed budget: "
            f"{iterations} not in [0,{max_it}]"
        )
    if reason > 0:
        return "KSP_CONVERGED", True
    if reason == _DIVERGED_ITS and iterations == max_it:
        return "INNER_APPROXIMATE_RETURN", False
    raise RuntimeError(
        "BAL_H side KSP failed with non-iterative reason "
        f"{reason} after {iterations} iterations"
    )


class FixedH6ActiveTraceAction:
    """Borrow a fixed positive H6 action through the existing trace maps.

    This adapter applies ``J H6 J^H`` on active rows.  In a modal Schur
    action it supplies the two feedback terms
    ``C - P_b J_b H6_b J_b^H T_b - P_t J_t H6_t J_t^H T_t``; ``T`` remains
    the existing modal coupling action.  H6 is a frozen positive surrogate,
    not the Maxwell side inverse, and adds no exact P4 or DtN feedback. The
    action is linear only while the borrowed H6 window, diagonal, runtime
    matrix, and condensed maps remain frozen for this adapter's lifetime.
    This adapter is not reentrant because its two work vectors are shared.
    The active operator, condensed layout, and H6 are borrowed. Only the two
    full-space work vectors allocated here are owned by this adapter.
    """

    operator_identity = "borrowed_fixed_h6_active_trace_J_H6_JH"
    method = "fixed_h6_active_trace"

    def __init__(self, operator: PETSc.Mat, condensed: Any, h6: FixedH6) -> None:
        self._operator: PETSc.Mat | None = operator
        self._condensed: Any | None = condensed
        self._h6: FixedH6 | None = h6
        self._comm = condensed.comm
        self._full_rhs: PETSc.Vec | None = None
        self._full_solution: PETSc.Vec | None = None
        self._destroyed = False
        self._apply_count = 0
        self._matrix_mult_count = 0

        local_error = None
        try:
            if not isinstance(operator, PETSc.Mat):
                raise TypeError("active H6 bridge requires a PETSc operator")
            if not isinstance(h6, FixedH6):
                raise TypeError("active H6 bridge requires a FixedH6 action")
            if not hasattr(self._comm, "allgather"):
                raise TypeError("condensed trace map has no MPI communicator")
            active_rows = int(condensed.active_rows)
            full_rows = int(condensed.full_rows)
            if operator.getSize() != (active_rows, active_rows):
                raise ValueError("active operator and trace rows differ")
            if h6.matrix.getSize() != (full_rows, full_rows):
                raise ValueError("FixedH6 and full p6 rows differ")
            trace = condensed.trace_constraints
            active_original = np.asarray(
                trace.owned_active_original_dofs, dtype=PETSc.IntType
            )
            if (
                active_original.ndim != 1
                or active_original.size != int(condensed.owned_active_rows)
                or np.unique(active_original).size != active_original.size
                or np.any(active_original < 0)
                or np.any(active_original >= full_rows)
            ):
                raise ValueError("owned active-to-full row map is inconsistent")
            for matrix in (operator, h6.matrix):
                relation = MPI.Comm.Compare(
                    self._comm, matrix.getComm().tompi4py()
                )
                if relation not in (MPI.IDENT, MPI.CONGRUENT):
                    raise ValueError("active and full H6 communicators differ")
        except Exception as exc:  # noqa: BLE001 - report rank-local metadata errors together
            local_error = f"{type(exc).__name__}: {exc}"
        self._raise_layout_errors(local_error, "metadata")

        active_rows = int(condensed.active_rows)
        full_rows = int(condensed.full_rows)
        local_error = None
        full_range = row_range = column_range = None
        try:
            self._full_rhs = self._h6.matrix.createVecRight()
            self._full_solution = self._h6.matrix.createVecLeft()
            full_range = tuple(map(int, self._full_rhs.getOwnershipRange()))
            if tuple(map(int, self._full_solution.getOwnershipRange())) != full_range:
                raise ValueError("FixedH6 full work-vector ownership differs")
            row_range = tuple(map(int, operator.getOwnershipRange()))
            column_range = tuple(map(int, operator.getOwnershipRangeColumn()))
            if (
                operator.getSize() != (active_rows, active_rows)
                or row_range[1] - row_range[0]
                != int(condensed.owned_active_rows)
                or column_range[1] - column_range[0]
                != int(condensed.owned_active_rows)
            ):
                raise ValueError("active operator ownership differs from trace map")
            active_original = np.asarray(
                condensed.trace_constraints.owned_active_original_dofs,
                dtype=PETSc.IntType,
            )
            if active_original.size and (
                int(active_original.min()) < full_range[0]
                or int(active_original.max()) >= full_range[1]
            ):
                raise ValueError("active full rows are not locally owned by H6")
        except Exception as exc:  # noqa: BLE001 - report rank-local layout errors together
            local_error = f"{type(exc).__name__}: {exc}"

        layout_records = self._comm.allgather(
            (
                local_error,
                full_range,
                row_range,
                column_range,
                int(condensed.owned_active_rows),
            )
        )
        failures = [
            f"rank {rank}: {record[0]}"
            for rank, record in enumerate(layout_records)
            if record[0] is not None
        ]
        if not failures:
            full_ranges = [record[1] for record in layout_records]
            active_ranges = [record[2] for record in layout_records]
            active_column_ranges = [record[3] for record in layout_records]
            active_counts = [record[4] for record in layout_records]
            full_valid = (
                full_ranges[0][0] == 0
                and full_ranges[-1][1] == full_rows
                and all(
                    full_ranges[rank - 1][1] == full_ranges[rank][0]
                    for rank in range(1, len(full_ranges))
                )
            )
            active_offsets = np.cumsum([0, *active_counts])
            active_valid = (
                int(active_offsets[-1]) == active_rows
                and all(
                    active_ranges[rank]
                    == (int(active_offsets[rank]), int(active_offsets[rank + 1]))
                    and active_column_ranges[rank] == active_ranges[rank]
                    for rank in range(len(active_ranges))
                )
            )
            if not full_valid:
                failures.append("full p6 ownership ranges do not cover rows")
            if not active_valid:
                failures.append("active ownership ranges do not match trace rows")
        if failures:
            self.destroy()
            raise ValueError(
                "FixedH6 active-trace vector layout validation failed; "
                + "; ".join(failures)
            )
        self._active_layout = row_range

    def _raise_layout_errors(self, local_error: str | None, stage: str) -> None:
        errors = self._comm.allgather(local_error)
        failures = [
            f"rank {rank}: {error}"
            for rank, error in enumerate(errors)
            if error is not None
        ]
        if failures:
            raise ValueError(
                f"FixedH6 active-trace {stage} validation failed; "
                + "; ".join(failures)
            )

    @property
    def operator(self) -> PETSc.Mat:
        if self._destroyed or self._operator is None:
            raise RuntimeError("FixedH6 active-trace adapter has been destroyed")
        return self._operator

    @property
    def audit(self) -> dict[str, Any]:
        return {
            "operator_identity": self.operator_identity,
            "action": "J H6 J^H",
            "linearity_condition": (
                "borrowed H6 window/diagonal/runtime matrix and condensed maps "
                "remain frozen for adapter lifetime"
            ),
            "reentrant": False,
            "h6_degree": H6_DEGREE,
            "h6_is_positive_surrogate": True,
            "exact_p4_or_dtn_feedback": False,
            "apply_count": self._apply_count,
            "matrix_mult_count": self._matrix_mult_count,
            "owned_work_vectors": 2,
            "borrowed_objects": ("operator", "condensed", "FixedH6"),
            "destroyed": self._destroyed,
        }

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        """Apply ``J H6 J^H`` without changing the borrowed source vector."""

        local_error = None
        try:
            if self._destroyed or self._condensed is None or self._h6 is None:
                raise RuntimeError("FixedH6 active-trace adapter has been destroyed")
            if _same_handle(source, target):
                raise ValueError("source and target PETSc vectors alias")
            active_rows = int(self._condensed.active_rows)
            if (
                source.getSize() != active_rows
                or target.getSize() != active_rows
                or tuple(map(int, source.getOwnershipRange()))
                != self._active_layout
                or tuple(map(int, target.getOwnershipRange()))
                != self._active_layout
            ):
                raise ValueError("active H6 bridge input/output layout differs")
        except Exception as exc:  # noqa: BLE001 - reject rank-local errors together
            local_error = f"{type(exc).__name__}: {exc}"
        self._raise_layout_errors(local_error, "apply arguments")

        condensed = self._condensed
        inject_active_residual_to_full_p6(condensed, source, self._full_rhs)
        facts = self._apply_full_action(self._full_rhs, self._full_solution)
        active_solution = extract_full_p6_to_active_trace(
            condensed, self._full_solution
        )
        try:
            active_solution.copy(target)
        finally:
            active_solution.destroy()
        self._apply_count += 1
        self._matrix_mult_count += int(facts["matrix_mult_count"])

    def _apply_full_action(
        self, source: PETSc.Vec, target: PETSc.Vec
    ) -> Mapping[str, Any]:
        if self._h6 is None:
            raise RuntimeError("FixedH6 active-trace adapter has been destroyed")
        return self._h6.apply_into(source, target)

    def destroy(self) -> None:
        """Release work vectors only; all three operator inputs are borrowed."""

        if self._destroyed:
            return
        self._destroyed = True
        for name in ("_full_rhs", "_full_solution"):
            vector = getattr(self, name)
            if vector is not None:
                vector.destroy()
                setattr(self, name, None)
        self._operator = None
        self._condensed = None
        self._h6 = None


class FixedPhysicalBalancedActiveTraceAction(FixedH6ActiveTraceAction):
    """Apply one fixed physical BAL_H correction through active trace maps.

    The P4 factor, A6 action, H6 action, owner transfer, and condensed layout
    are borrowed from a live ``SideBalancedInverse``.  Each Q call requests
    exactly one same-factor P4 correction and deliberately suppresses that
    inverse's ordinary residual-target mode for this call only.  No solver
    tolerance or factor state is changed.
    """

    operator_identity = "borrowed_fixed_physical_balh_active_trace"
    method = FIXED_PHYSICAL_BALH_MODAL_FEEDBACK_METHOD

    def __init__(self, side_inverse: SideBalancedInverse) -> None:
        if not isinstance(side_inverse, SideBalancedInverse):
            raise TypeError("fixed physical BAL_H action requires a side inverse")
        if (
            side_inverse._destroyed
            or side_inverse._operator is None
            or side_inverse._condensed is None
            or side_inverse._h6 is None
            or side_inverse._p4_factor is None
            or side_inverse._full_action is None
            or side_inverse._owner_transfer is None
        ):
            raise RuntimeError(
                "Cannot create fixed physical BAL_H action from a destroyed side inverse"
            )
        if not isinstance(side_inverse._h6, FixedH6):
            raise TypeError("fixed physical BAL_H action requires FixedH6")
        if side_inverse._reuse_leading_ph_dual:
            raise ValueError(
                "fixed physical BAL_H feedback requires the registered ordinary PH path"
            )
        super().__init__(
            side_inverse._operator,
            side_inverse._condensed,
            side_inverse._h6,
        )
        self._side_inverse: SideBalancedInverse | None = side_inverse
        self._physical_balh: PhysicalBalancedCoupling | None = None
        self._last_q_factor_solve_deltas: tuple[int, ...] = ()
        self._last_q_factor_step_solve_deltas: tuple[tuple[int, int], ...] = ()
        self._last_q_solve_audits: tuple[dict[str, Any], ...] = ()
        self._a6_apply_count = 0
        self._h6_apply_count = 0
        self._h6_matrix_mult_count = 0
        try:
            self._physical_balh = PhysicalBalancedCoupling(
                self._apply_a6,
                self._apply_q_once,
                self._apply_h6,
                self._apply_ph,
                checkpoint=side_inverse._checkpoint,
                reuse_leading_ph=side_inverse._reuse_leading_ph_dual,
            )
        except BaseException:
            self.destroy()
            raise

    def _owner(self) -> SideBalancedInverse:
        owner = self._side_inverse
        if owner is None or owner._destroyed:
            raise RuntimeError("fixed physical BAL_H side inverse was destroyed")
        return owner

    def _apply_a6(self, source: PETSc.Vec) -> PETSc.Vec:
        result = self._owner()._apply_a6_callback(source)
        self._a6_apply_count += 1
        return result

    def _apply_q_once(
        self,
        source: PETSc.Vec,
        *,
        return_leading_dual: bool = False,
    ) -> PETSc.Vec | tuple[PETSc.Vec, PETSc.Vec]:
        owner = self._owner()
        factor = owner._p4_factor
        if factor is None:
            raise RuntimeError("fixed physical BAL_H P4 factor was destroyed")
        before = _p4_solve_count(factor)
        owner._last_fixed_q_solve_audit = None
        result = None
        try:
            result = owner._apply_q_callback(
                source,
                return_leading_dual=return_leading_dual,
                fixed_p4_correction_steps=1,
            )
            after = _p4_solve_count(factor)
            delta = after - before
            if delta < 0:
                raise RuntimeError("fixed physical BAL_H P4 solve counter moved backwards")
            if isinstance(getattr(factor, "inverse", None), P4CellCondensedInverse):
                q_audit = owner._last_fixed_q_solve_audit
                if not isinstance(q_audit, Mapping):
                    raise TypeError("fixed physical BAL_H lost per-call P4 audit")
                step_deltas = tuple(q_audit.get("factor_solve_deltas_by_step", ()))
                q_input_norm = q_audit.get("q_input_global_norm")
                if (
                    q_audit.get("factor_solve_count_before") != before
                    or q_audit.get("factor_solve_count_after") != after
                    or not isinstance(q_input_norm, (int, float))
                    or not np.isfinite(q_input_norm)
                    or q_input_norm < 0.0
                    or type(q_audit.get("q_input_global_exact_zero")) is not bool
                    or (q_input_norm == 0.0)
                    != q_audit.get("q_input_global_exact_zero")
                    or len(step_deltas) != 2
                    or any(type(value) is not int or value not in (0, 1) for value in step_deltas)
                    or sum(step_deltas) != delta
                ):
                    raise RuntimeError(
                        "fixed physical BAL_H per-call audit disagrees with factor count"
                    )
            else:
                # The full augmented backend has no direct-zero shortcut; each
                # of its two requested solves must therefore reach the factor.
                if delta != 2:
                    raise RuntimeError(
                        "fixed physical BAL_H full P4 backend did not execute both solves"
                    )
                step_deltas = (1, 1)
            q_audit = owner._last_fixed_q_solve_audit
            if not isinstance(q_audit, Mapping):
                raise TypeError("fixed physical BAL_H lost per-Q solve audit")
            if (
                type(q_audit.get("mathematical_correction_steps")) is not int
                or q_audit.get("mathematical_correction_steps") != 1
                or type(q_audit.get("factor_solve_call_delta")) is not int
                or q_audit.get("factor_solve_call_delta") != delta
                or tuple(q_audit.get("factor_solve_deltas_by_step", ()))
                != tuple(step_deltas)
            ):
                raise RuntimeError("fixed physical BAL_H per-Q audit is inconsistent")
        except BaseException:
            vectors = result if isinstance(result, tuple) else (result,)
            released: set[int] = set()
            for vector in vectors:
                if isinstance(vector, PETSc.Vec) and id(vector) not in released:
                    released.add(id(vector))
                    try:
                        vector.destroy()
                    except BaseException:  # noqa: BLE001, S110 - preserve solve-count failure
                        pass
            raise
        self._last_q_factor_solve_deltas = (
            *self._last_q_factor_solve_deltas,
            delta,
        )[-2:]
        self._last_q_factor_step_solve_deltas = (
            *self._last_q_factor_step_solve_deltas,
            step_deltas,
        )[-2:]
        self._last_q_solve_audits = (
            *self._last_q_solve_audits,
            dict(q_audit),
        )[-2:]
        return result

    def _apply_h6(self, source: PETSc.Vec) -> PETSc.Vec:
        result = self._owner()._apply_h6_callback(source)
        self._h6_apply_count += 1
        return result

    def _apply_ph(self, source: PETSc.Vec) -> PETSc.Vec:
        return self._owner()._apply_ph_callback(source)

    def _apply_full_action(
        self, source: PETSc.Vec, target: PETSc.Vec
    ) -> Mapping[str, Any]:
        owner = self._owner()
        coupling = self._physical_balh
        h6 = self._h6
        if coupling is None or h6 is None:
            raise RuntimeError("fixed physical BAL_H action has been destroyed")
        h6_mults_before = int(h6.matrix_mult_count)
        self._last_q_factor_solve_deltas = ()
        self._last_q_factor_step_solve_deltas = ()
        self._last_q_solve_audits = ()
        result = coupling.apply(source)
        try:
            result.copy(target)
        finally:
            result.destroy()
        facts = coupling.last_apply_facts
        self._h6_matrix_mult_count += int(h6.matrix_mult_count) - h6_mults_before
        counts = facts.get("counts")
        if not isinstance(counts, Mapping):
            raise TypeError("fixed physical BAL_H action lost operation counts")
        a6_calls = counts.get("A6")
        if type(a6_calls) is not int or a6_calls != 2:
            raise RuntimeError("fixed physical BAL_H action did not apply A6 twice")
        if counts.get("Q") != 2 or counts.get("H6") != 1:
            raise RuntimeError(
                "fixed physical BAL_H action changed its Q/H6 operation sequence"
            )
        if (
            len(self._last_q_factor_solve_deltas) != 2
            or len(self._last_q_factor_step_solve_deltas) != 2
            or len(self._last_q_solve_audits) != 2
            or any(
                len(step_deltas) != 2
                or any(
                    type(value) is not int or value not in (0, 1)
                    for value in step_deltas
                )
                or sum(step_deltas) != total_delta
                for step_deltas, total_delta in zip(
                    self._last_q_factor_step_solve_deltas,
                    self._last_q_factor_solve_deltas,
                    strict=True,
                )
            )
            or any(
                type(q_audit.get("mathematical_correction_steps")) is not int
                or q_audit.get("mathematical_correction_steps") != 1
                or type(q_audit.get("factor_solve_call_delta")) is not int
                or q_audit.get("factor_solve_call_delta") != total_delta
                or tuple(q_audit.get("factor_solve_deltas_by_step", ()))
                != step_deltas
                for q_audit, step_deltas, total_delta in zip(
                    self._last_q_solve_audits,
                    self._last_q_factor_step_solve_deltas,
                    self._last_q_factor_solve_deltas,
                    strict=True,
                )
            )
        ):
            raise RuntimeError(
                "fixed physical BAL_H action lost per-step same-factor P4 solve evidence"
            )
        if owner._p4_factor is None:
            raise RuntimeError("fixed physical BAL_H P4 factor was destroyed")
        return {
            "matrix_mult_count": a6_calls
            + int(h6.matrix_mult_count)
            - h6_mults_before
        }

    @property
    def audit(self) -> dict[str, Any]:
        result = super().audit
        owner = self._side_inverse
        coupling = self._physical_balh
        result.update(
            {
                "operator_identity": self.operator_identity,
                "method": FIXED_PHYSICAL_BALH_MODAL_FEEDBACK_METHOD,
                "action": "J[Q+(I-QA6)H6(I-A6Q)]J^H",
                "p4_q_correction_policy": "exactly_one_same_factor_correction_per_Q",
                "p4_refinement_target_tolerance_used": None,
                "ordinary_side_refinement_target_tolerance": (
                    None
                    if owner is None
                    else owner._p4_refinement_target_tolerance
                ),
                "physical_residual_gate": 1.0e-10,
                "augmented_residual_gate": 1.0e-10,
                "matrix_mult_count_scope": "explicit_A6_plus_H6_inner_mults; P4 work excluded",
                "borrowed_objects": (
                    "operator",
                    "condensed",
                    "FixedH6",
                    "SideBalancedInverse",
                    "P4 factor",
                    "A6 action",
                    "owner transfer",
                ),
                "exact_p4_or_dtn_feedback": True,
                "last_q_factor_solve_deltas": list(
                    self._last_q_factor_solve_deltas
                ),
                "last_q_factor_step_solve_deltas": [
                    list(values)
                    for values in self._last_q_factor_step_solve_deltas
                ],
                "last_q_solve_audits": [
                    {
                        **dict(q_audit),
                        "inverse_apply_history": (
                            None
                            if q_audit.get("inverse_apply_history") is None
                            else [
                                {
                                    **dict(inverse_audit),
                                    "inverse_audit": dict(
                                        inverse_audit["inverse_audit"]
                                    ),
                                }
                                for inverse_audit in q_audit[
                                    "inverse_apply_history"
                                ]
                            ]
                        ),
                    }
                    for q_audit in self._last_q_solve_audits
                ],
                "mathematical_p4_correction_steps_per_q": 1,
                "last_q_factor_solve_count_scope": (
                    "local side factor counter; each initial/correction inverse "
                    "call records its status and exact solve delta"
                ),
                "a6_apply_count": self._a6_apply_count,
                "h6_apply_count": self._h6_apply_count,
                "h6_matrix_mult_count": self._h6_matrix_mult_count,
                "last_balh_coupling": (
                    {}
                    if coupling is None
                    else dict(coupling.last_apply_facts)
                ),
                "destroyed": self._destroyed,
            }
        )
        return result

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._physical_balh = None
        self._side_inverse = None
        super().destroy()


class _SidePythonPcContext:
    """Borrow the side adapter from PETSc's Python right-PC context."""

    def __init__(self, owner: SideBalancedInverse) -> None:
        self.owner: SideBalancedInverse | None = owner

    def apply(
        self,
        _pc: PETSc.PC,
        source: PETSc.Vec,
        target: PETSc.Vec,
    ) -> None:
        owner = self.owner
        if owner is None:
            raise RuntimeError("BAL_H side Python PC has been destroyed")
        try:
            owner._apply_balanced_pc(source, target)
        except BaseException as exc:  # noqa: BLE001 - defer one callback failure to KSP
            owner._pending_pc_exception = exc
            _pc.setFailedReason(PETSc.PC.FailedReason.SUBPC_ERROR)
            target.set(PETSc.ScalarType(np.inf))

    def destroy(self, _pc: PETSc.PC | None = None) -> None:
        self.owner = None


class SideBalancedInverse:
    """Right FGMRES inverse of one borrowed condensed side operator.

    ``apply`` returns through the caller-provided target Vec.  The internal
    callbacks used by BAL_H always return fresh owned Vec objects, so the
    coupling can release every temporary independently of the side input.
    ``reuse_leading_ph_dual`` is a default-off single-apply optimization and is
    rejected for vector diagnostics that could alter the reused RHS.  Its
    caller must keep the borrowed transfer layout/MPC fixed; the P4 factors
    used here consume, but do not modify, the PH-produced RHS.
    """

    operator_identity = "borrowed_side_A_right_fgmres_J_BAL_H_JH"

    def __init__(
        self,
        side_system: HybridLocalDtnActionSystem,
        full_action: Any,
        p4_factor: Any,
        owner_transfer: Any,
        h6: Any,
        *,
        max_it: int = 128,
        rtol: float = 1.0e-2,
        checkpoint_callback: Callable[[], None] | None = None,
        audit_callback: Callable[[dict[str, Any]], None] | None = None,
        detailed_timing: bool = False,
        record_iteration_history: bool = False,
        diagnostic_callback: Callable[[Mapping[str, Any]], Any] | None = None,
        p4_inverse_backend: str = "full",
        physical_action_backend: str | None = None,
        reuse_leading_ph_dual: bool = False,
        side_restart64_trial_state: dict[str, Any] | None = None,
        side_restart64_memory_gate: Callable[[Mapping[str, Any]], Mapping[str, Any]]
        | None = None,
    ) -> None:
        _validate_ksp_pair(max_it, rtol)
        if not isinstance(reuse_leading_ph_dual, bool):
            raise TypeError("reuse_leading_ph_dual must be a boolean")
        if reuse_leading_ph_dual and diagnostic_callback is not None:
            raise ValueError(
                "leading PH reuse is incompatible with mutable vector diagnostics"
            )
        if p4_inverse_backend not in _P4_INVERSE_BACKENDS:
            raise ValueError(
                "p4_inverse_backend must be 'full' or 'cell_condensed'"
            )
        if (side_restart64_trial_state is None) != (
            side_restart64_memory_gate is None
        ):
            raise ValueError(
                "the V12 side restart trial state and fresh memory gate must be supplied together"
            )
        if side_restart64_trial_state is not None and (
                not isinstance(side_restart64_trial_state, dict)
                or side_restart64_trial_state.get("schema")
                != "task041.v12.side_restart64_trial_state.v1"
                or side_restart64_trial_state.get("policy_id")
                != "task041_v12_bounded_inexact_modal_once_backup"
                or side_system.side not in {"bottom", "top"}
                or not callable(side_restart64_memory_gate)
                or max_it != 128
                or float(rtol) != 1.0e-2
                or p4_inverse_backend != "cell_condensed"
        ):
            raise ValueError(
                "the side restart64 trial is limited to registered V12 staged cell-condensed W0.7 sides"
            )
        operator = side_system.A
        condensed = side_system.static_condensation.condensed
        if not isinstance(operator, PETSc.Mat):
            raise TypeError("BAL_H side inverse requires a PETSc side operator")
        if int(side_system.cfg.nedelec_degree) != 6:
            raise ValueError("BAL_H side inverse requires the p6 side system")
        if int(operator.getSize()[0]) != int(condensed.active_rows):
            raise ValueError("side operator and condensed active rows do not match")
        if int(full_action.full_rows) != int(condensed.full_rows):
            raise ValueError("full p6 action and condensed FE rows do not match")

        self._side_system: HybridLocalDtnActionSystem | None = side_system
        self._condensed: Any | None = condensed
        self._operator: PETSc.Mat | None = operator
        self._full_action: Any | None = full_action
        self._p4_factor: Any | None = p4_factor
        self._p4_inverse_backend = p4_inverse_backend
        self._physical_action_backend = physical_action_backend
        self._reuse_leading_ph_dual = reuse_leading_ph_dual
        self._owner_transfer: Any | None = owner_transfer
        self._reuse_primal_route_plan_enabled = bool(
            getattr(owner_transfer, "_reuse_primal_route_plan", False)
        )
        self._h6: Any | None = h6
        self._checkpoint_callback = checkpoint_callback or (lambda: None)
        self._audit_callback = audit_callback
        self._comm = operator.getComm().tompi4py()
        self._max_it = int(max_it)
        self._rtol = float(rtol)
        self._detailed_timing = bool(detailed_timing)
        self._destroyed = False
        self._variant_context_active = False
        self._active_variant: str | None = None
        self._apply_in_progress = False
        self._record_iteration_history = bool(record_iteration_history)
        self._diagnostic_callback = diagnostic_callback
        self._diagnostic_p4_correction_steps = 0
        self._diagnostic_p4_correction_callback: Callable[
            [Mapping[str, Any], Mapping[str, Any]], None
        ] | None = None
        self._p4_refinement_target_tolerance: float | None = None
        self._active_apply_pc_count = 0
        self._active_pc_index: int | None = None
        self._active_pc_q_count = 0
        self._active_ksp_iteration: int | None = None
        self._active_rhs_source: PETSc.Vec | None = None
        self._active_rhs_norm: float | None = None
        self._active_p4_call_records: list[dict[str, Any]] | None = None
        self._active_true_residual_samples: list[dict[str, Any]] | None = None
        self._direct_p4_call_records: list[dict[str, Any]] = []
        self._last_fixed_q_solve_audit: dict[str, Any] | None = None
        self._iteration_history: list[dict[str, Any]] | None = (
            [] if self._record_iteration_history else None
        )
        self._side_restart64_trial_state = side_restart64_trial_state
        self._side_restart64_memory_gate = side_restart64_memory_gate
        self._gmres_restart = 32
        self._nested_ksp_created_count = 1
        self._nested_ksp_destroy_count = 0
        self._restart_transition_ksp_setup_seconds = 0.0
        self._active_restart64_ksp: PETSc.KSP | None = None
        self._active_restart32_samples: list[dict[str, Any]] | None = None
        self._side_restart64_candidate_rhs: PETSc.Vec | None = None
        self._side_restart64_trial_record: dict[str, Any] | None = None
        self._side_restart64_trial_running = False
        self._p4_factor_created_count = 1
        self._p4_factor_destroy_count = 0
        self._checkpoint_count = 0
        self._pc_apply_count = 0
        self._q_count = 0
        self._h6_count = 0
        self._a6_count = 0
        self._j_count = 0
        self._jh_count = 0
        self._ph_audit_count = 0
        self._ph_leading_reused_count = 0
        self._ph_total_count = 0
        self._p_count = 0

        self._p4_backsolve_count = 0
        self._p4_refinement_count = 0
        self._apply_count = 0
        self._total_iterations = 0
        self._total_apply_seconds = 0.0
        self._last_apply: dict[str, Any] = {}
        self._last_coupling_failure: dict[str, Any] | None = None
        self._pending_pc_exception: BaseException | None = None
        self._rhs_operation_seconds = {name: 0.0 for name in ("Q", "H6", "A6")}
        self._rhs_detail_seconds = {
            name: 0.0 for name in _DETAIL_TIMING_NAMES
        }
        self._rhs_detail_seen = {
            name: False for name in _DETAIL_TIMING_NAMES
        }
        self._cumulative_counts: dict[str, int | None] = {
            "side_A": _context_apply_count(operator),
            "pc": 0,
            "Q": 0,
            "p4_backsolve": 0,
            "p4_refinement": 0,
            "H6": 0,
            "A6": 0,
            "J": 0,
            "JH": 0,
            "P": 0,
            "PH_audit": 0,
            "PH_total": 0,
        }
        if self._reuse_leading_ph_dual:
            self._cumulative_counts["PH_audit_leading_reused"] = 0
            self._cumulative_counts["PH_audit_logical"] = 0
        self._pre_destroy_component_diagnostics: dict[str, Any] | None = None

        self._coupling = PhysicalBalancedCoupling(
            self._apply_a6_callback,
            self._apply_q_callback,
            self._apply_h6_callback,
            self._apply_ph_callback,
            checkpoint=self._checkpoint,
            reuse_leading_ph=self._reuse_leading_ph_dual,
        )
        self._pc_context = _SidePythonPcContext(self)
        self._ksp: PETSc.KSP | None = PETSc.KSP().create(operator.getComm())
        try:
            self._ksp.setOperators(operator)
            self._ksp.setType("fgmres")
            self._ksp.setPCSide(PETSc.PC.Side.RIGHT)
            self._ksp.setGMRESRestart(32)
            self._ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
            self._ksp.setInitialGuessNonzero(False)
            self._ksp.setTolerances(
                rtol=self._rtol,
                atol=0.0,
                max_it=self._max_it,
            )
            pc = self._ksp.getPC()
            pc.setType("python")
            pc.setPythonContext(self._pc_context)
            self._ksp.setMonitor(self._monitor)
            self._ksp.setUp()
        except BaseException:
            self._pc_context.owner = None
            self._ksp.destroy()
            self._ksp = None
            raise

    def configure_diagnostic_p4_corrections(
        self,
        steps: int,
        callback: Callable[[Mapping[str, Any], Mapping[str, Any]], None] | None,
        *,
        refinement_target_tolerance: float | None = None,
    ) -> None:
        """Set fixed-step auditing or the single opt-in residual target."""

        if isinstance(steps, bool) or int(steps) not in (0, 1, 2):
            raise ValueError("diagnostic P4 corrections must be 0, 1, or 2")
        target = _refinement_target_tolerance(refinement_target_tolerance)
        if target is not None and (int(steps) != 0 or callback is not None):
            raise ValueError(
                "refinement target and fixed-step P4 diagnostics are mutually exclusive"
            )
        if self._reuse_leading_ph_dual and callback is not None:
            raise ValueError(
                "leading PH reuse is incompatible with mutable P4 diagnostics"
            )
        self._diagnostic_p4_correction_steps = int(steps)
        self._diagnostic_p4_correction_callback = callback
        self._p4_refinement_target_tolerance = target

    @property
    def operator(self) -> PETSc.Mat:
        if self._destroyed or self._operator is None:
            raise RuntimeError("BAL_H side inverse has been destroyed")
        return self._operator

    def create_fixed_h6_active_trace_action(self) -> FixedH6ActiveTraceAction:
        """Create a borrowed fixed-H6 modal surrogate for this live side.

        The returned adapter owns only its work vectors.  This inverse retains
        ownership of the H6 action and condensed map and must outlive it.
        """

        if (
            self._destroyed
            or self._operator is None
            or self._condensed is None
            or self._h6 is None
        ):
            raise RuntimeError(
                "Cannot create a fixed-H6 trace action from a destroyed side inverse"
            )
        if not isinstance(self._h6, FixedH6):
            raise TypeError("Fixed-H6 modal research requires a FixedH6 side action")
        return FixedH6ActiveTraceAction(
            self._operator,
            self._condensed,
            self._h6,
        )

    def create_fixed_physical_balh_active_trace_action(
        self,
    ) -> FixedPhysicalBalancedActiveTraceAction:
        """Borrow this live side's factors/actions for one fixed BAL_H Q policy."""

        return FixedPhysicalBalancedActiveTraceAction(self)

    @contextmanager
    def variant_context(self, variant: str):
        """Temporarily select a transfer variant for one complete side apply."""

        if self._destroyed or self._owner_transfer is None:
            raise RuntimeError("BAL_H side inverse has been destroyed")
        if self._apply_in_progress:
            raise RuntimeError("BAL_H execution variant cannot change during apply")
        if self._variant_context_active:
            raise RuntimeError("BAL_H execution variant cannot change while active")
        previous = self._active_variant
        self._active_variant = variant
        self._variant_context_active = True
        try:
            with self._owner_transfer.variant_context(variant):
                yield self
        finally:
            self._active_variant = previous
            self._variant_context_active = False

    def _ksp_contract_audit(self) -> dict[str, Any]:
        """Read the live PETSc KSP settings used by an opt-in comparison."""

        ksp = self._ksp
        if ksp is None:
            raise RuntimeError("BAL_H side KSP is not live")
        pc = ksp.getPC()
        rtol, atol, divtol, max_it = ksp.getTolerances()
        restart = _live_gmres_restart(ksp)
        pc_side = ksp.getPCSide()
        norm_type = ksp.getNormType()
        actual = {
            "type": str(ksp.getType()),
            "pc_type": str(pc.getType()),
            "pc_side": int(pc_side),
            "pc_side_label": (
                "RIGHT" if pc_side == PETSc.PC.Side.RIGHT else str(pc_side)
            ),
            "norm_type": int(norm_type),
            "norm_type_label": (
                "UNPRECONDITIONED"
                if norm_type == PETSc.KSP.NormType.UNPRECONDITIONED
                else str(norm_type)
            ),
            "restart": int(restart),
            "rtol": float(rtol),
            "atol": float(atol),
            "divtol": float(divtol),
            "max_it": int(max_it),
            "initial_guess_nonzero": bool(ksp.getInitialGuessNonzero()),
        }
        expected = {
            "type": "fgmres",
            "pc_type": "python",
            "pc_side": int(PETSc.PC.Side.RIGHT),
            "pc_side_label": "RIGHT",
            "norm_type": int(PETSc.KSP.NormType.UNPRECONDITIONED),
            "norm_type_label": "UNPRECONDITIONED",
            "restart": int(self._gmres_restart),
            "rtol": self._rtol,
            "atol": 0.0,
            "max_it": self._max_it,
            "initial_guess_nonzero": False,
        }
        checks = {
            "type": actual["type"].lower() == expected["type"],
            "pc_type": actual["pc_type"].lower() == expected["pc_type"],
            "pc_side": pc_side == PETSc.PC.Side.RIGHT,
            "norm_type": norm_type == PETSc.KSP.NormType.UNPRECONDITIONED,
            "restart": actual["restart"] == expected["restart"],
            "rtol": actual["rtol"] == expected["rtol"],
            "atol": actual["atol"] == expected["atol"],
            "max_it": actual["max_it"] == expected["max_it"],
            "initial_guess_nonzero": (
                actual["initial_guess_nonzero"]
                == expected["initial_guess_nonzero"]
            ),
        }
        return {
            "source": "live_petsc_getters_before_opt_in_apply",
            "actual": actual,
            "expected": expected,
            "checks": checks,
            "pass": all(checks.values()),
        }

    def _monitor(
        self,
        _ksp: PETSc.KSP,
        _iteration: int,
        _reported_residual: float,
    ) -> None:
        self._active_ksp_iteration = int(_iteration)
        if (
            self._iteration_history is not None
            and len(self._iteration_history) < self._max_it + 1
        ):
            residual = float(_reported_residual)
            if np.isnan(residual):
                recorded_residual: float | str = "nan"
            elif np.isposinf(residual):
                recorded_residual = "inf"
            elif np.isneginf(residual):
                recorded_residual = "-inf"
            else:
                recorded_residual = residual
            self._iteration_history.append(
                {
                    "iteration": int(_iteration),
                    "reported_residual": recorded_residual,
                }
            )
        self._emit_diagnostic(
            "ksp_monitor",
            iteration=int(_iteration),
            reported_residual=float(_reported_residual),
        )
        capture_every_step = self._side_restart64_capture_is_armed()
        sample_iteration = int(_iteration)
        if self._active_restart32_samples is not None and (
            capture_every_step
            or sample_iteration in {1, 4, 8}
            or sample_iteration > 0 and sample_iteration % 32 == 0
        ):
            sample = self._restart32_true_residual_sample(
                _ksp,
                iteration=sample_iteration,
                reported_residual=float(_reported_residual),
            )
            if not self._active_restart32_samples or self._active_restart32_samples[-1][
                "iteration"
            ] != sample_iteration:
                self._active_restart32_samples.append(sample)
        if self._diagnostic_callback is not None and (
            int(_iteration) == 1
            or (int(_iteration) > 0 and int(_iteration) % 32 == 0)
        ):
            self._emit_ksp_true_residual_sample(
                _ksp,
                iteration=int(_iteration),
                sample_label=(
                    "first_iteration"
                    if int(_iteration) == 1
                    else "restart_boundary"
                ),
            )
        self._checkpoint()

    def _restart32_true_residual_sample(
        self,
        ksp: PETSc.KSP,
        *,
        iteration: int,
        reported_residual: float | None,
        final_solution: PETSc.Vec | None = None,
    ) -> dict[str, Any]:
        """Measure a bounded original-D residual sample for the V12 side trial."""

        if self._operator is None or self._active_rhs_source is None:
            raise RuntimeError("restart32 trajectory lost its original D/RHS")
        solution = final_solution
        owns_solution = solution is None
        residual = self._operator.createVecLeft()
        if solution is None:
            solution = self._operator.createVecRight()
        try:
            if owns_solution:
                ksp.buildSolution(solution)
            self._operator.mult(solution, residual)
            residual.scale(PETSc.ScalarType(-1.0))
            residual.axpy(PETSc.ScalarType(1.0), self._active_rhs_source)
            local_finite = bool(
                np.isfinite(solution.getArray(readonly=True)).all()
                and np.isfinite(residual.getArray(readonly=True)).all()
            )
            finite = bool(self._comm.allreduce(local_finite, op=MPI.LAND))
            residual_norm = float(residual.norm())
            rhs_norm = self._active_rhs_norm
            relative = (
                residual_norm / rhs_norm
                if rhs_norm is not None and rhs_norm > 0.0
                else 0.0
                if rhs_norm == 0.0 and residual_norm == 0.0
                else None
            )
            finite = bool(
                finite
                and np.isfinite(residual_norm)
                and relative is not None
                and np.isfinite(relative)
            )
            return {
                "iteration": int(iteration),
                "reported_residual": reported_residual,
                "original_D_true_residual_norm": residual_norm,
                "original_D_rhs_norm": rhs_norm,
                "original_D_true_relative_residual": relative,
                "finite": finite,
                "scope": "global_norm_from_distributed_owned_rows",
            }
        finally:
            residual.destroy()
            if owns_solution:
                solution.destroy()

    def _side_restart64_capture_is_armed(self) -> bool:
        state = self._side_restart64_trial_state
        return bool(
            isinstance(state, Mapping)
            and state.get("schema") == "task041.v12.side_restart64_trial_state.v1"
            and state.get("backup_method_active") is True
            and state.get("backup_commit_count") == 1
            and state.get("outer_stagnation_confirmed") is True
            and state.get("capture_armed") is True
            and state.get("status") == "capture_armed"
            and state.get("trial_count") == 0
            and self._gmres_restart == 32
            and self._max_it == 128
        )

    def _mark_post_backup_side_solve_seen(self) -> None:
        state = self._side_restart64_trial_state
        if not isinstance(state, dict) or state.get("backup_method_active") is not True:
            return
        if state.get("status") not in {"armed", "capture_armed"}:
            return
        seen = state.get("post_backup_side_solve_seen")
        if isinstance(seen, dict) and self._side_system is not None:
            seen[str(self._side_system.side)] = True

    def _consider_restart32_candidate(
        self,
        source: PETSc.Vec,
        *,
        reason: int | None,
        iterations: int,
        residual_audit: Mapping[str, Any],
        samples: Sequence[Mapping[str, Any]],
        solve_record: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        """Capture at most one true-residual-stagnant owned RHS after outer stagnation."""

        self._mark_post_backup_side_solve_seen()
        if not self._side_restart64_capture_is_armed():
            return None
        local_samples = {
            int(row["iteration"]): dict(row)
            for row in samples
            if type(row.get("iteration")) is int
        }
        required_iterations = tuple(range(64, 129))
        local_error = None
        candidate_evidence: dict[str, Any] = {}
        try:
            eta = residual_audit.get("relative_residual")
            sample_rows = [local_samples.get(value) for value in required_iterations]
            if (
                self._side_system is None
                or reason != _DIVERGED_ITS
                or iterations != 128
                or solve_record.get("reason") != reason
                or solve_record.get("iterations") != iterations
                or not isinstance(eta, (int, float))
                or isinstance(eta, bool)
                or not np.isfinite(float(eta))
                or float(eta) <= self._rtol
                or any(not isinstance(row, Mapping) for row in sample_rows)
                or any(row.get("finite") is not True for row in sample_rows)
            ):
                candidate_evidence = {
                    "eligible": False,
                    "reason": "not_a_finite_128_step_non_target_return",
                }
            else:
                eta_by_iteration = {
                    int(row["iteration"]): float(
                        row["original_D_true_relative_residual"]
                    )
                    for row in sample_rows
                }
                eta64 = eta_by_iteration[64]
                first_best = min(
                    eta_by_iteration[iteration] for iteration in range(64, 97)
                )
                first_improvement = (
                    (eta64 - first_best) / eta64 if eta64 > 0.0 else None
                )
                second_best = min(
                    eta_by_iteration[iteration] for iteration in range(96, 129)
                )
                second_improvement = (
                    (first_best - second_best) / first_best
                    if first_best > 0.0
                    else None
                )
                eligible = bool(
                    first_improvement is not None
                    and second_improvement is not None
                    and np.isfinite(first_improvement)
                    and np.isfinite(second_improvement)
                    and first_improvement < 0.10
                    and second_improvement < 0.10
                )
                candidate_evidence = {
                    "eligible": eligible,
                    "reason": (
                        "two_restart32_true_residual_windows_stalled"
                        if eligible
                        else "restart32_true_residual_windows_still_improving"
                    ),
                    "sampling_scope": (
                        "original_D_true_residual_each_iteration_after_outer_stagnation"
                    ),
                    "window_end_iterations": [[64, 96], [96, 128]],
                    "window_best_relative_residuals": [first_best, second_best],
                    "window_improvement_fractions": [
                        first_improvement,
                        second_improvement,
                    ],
                    "required_improvement": "both strictly below 0.10",
                    "final_original_D_relative_residual": float(eta),
                    "target_rtol": self._rtol,
                    "samples": [dict(row) for row in sample_rows],
                }
        except Exception as exc:  # noqa: BLE001 - rank errors are agreed before gate
            local_error = f"{type(exc).__name__}: {exc}"
        evidence_signature = hashlib.sha256(
            json.dumps(
                candidate_evidence,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        rank_evidence = self._comm.allgather(
            {
                "rank": int(self._comm.rank),
                "error": local_error,
                "evidence_sha256": evidence_signature,
                "eligible": candidate_evidence.get("eligible"),
                "reason": candidate_evidence.get("reason"),
                "runtime_reason": reason,
                "iterations": int(iterations),
                "restart32_work": self._restart32_reference_work(solve_record),
            }
        )
        errors = [row for row in rank_evidence if row.get("error") is not None]
        if errors:
            raise RuntimeError(
                "side restart32 candidate evidence failed collectively: "
                + "; ".join(
                    f"rank {row['rank']}: {row['error']}" for row in errors
                )
            )
        signatures = [
            (
                row.get("evidence_sha256"),
                row.get("eligible"),
                row.get("reason"),
                row.get("runtime_reason"),
                row.get("iterations"),
            )
            for row in rank_evidence
        ]
        if any(value != signatures[0] for value in signatures[1:]):
            raise RuntimeError("side restart32 candidate evidence differs across ranks")
        evidence = dict(candidate_evidence)
        evidence["restart32_reference_work_by_rank"] = [
            dict(row["restart32_work"]) for row in rank_evidence
        ]
        state = self._side_restart64_trial_state
        if not evidence.get("eligible") or not isinstance(state, dict):
            return None
        if state.get("status") != "capture_armed" or state.get("trial_count") != 0:
            raise RuntimeError("side restart64 candidate was already consumed or disarmed")
        if self._side_restart64_memory_gate is None:
            raise RuntimeError("side restart64 candidate has no fresh memory gate")
        if self._operator is None:
            raise RuntimeError("side restart64 candidate lost its operator layout")
        local_operator_rows, local_operator_columns = (
            int(value) for value in self._operator.getLocalSize()
        )
        local_sha = _local_complex_vec_sha256(source)
        gate = self._side_restart64_memory_gate(
            {
                "phase": "capture_restart32_rhs",
                "side": str(self._side_system.side),
                "restart": 32,
                "workspace_lifecycle": (
                    "restart32_ksp_live_plus_source_rhs_before_candidate_copy"
                ),
                "existing_restart32_ksp_live": True,
                "restart64_trial_ksp_live": False,
                "candidate_rhs_live": False,
                "existing_restart32_restart": 32,
                "local_vector_size": int(source.getLocalSize()),
                "operator_local_rows": local_operator_rows,
                "operator_local_columns": local_operator_columns,
                "rhs_local_sha256": local_sha,
                "rhs_global_size": int(source.getSize()),
                "rhs_ownership_range": list(map(int, source.getOwnershipRange())),
                "original_D_rhs_norm": float(source.norm()),
            }
        )
        if not isinstance(gate, Mapping) or type(gate.get("pass")) is not bool:
            raise RuntimeError("side restart64 capture gate returned no explicit decision")
        if gate.get("pass") is not True:
            state.update(
                {
                    "status": "capacity_gate_refused",
                    "pending": True,
                    "capture_armed": False,
                    "capture_gate": dict(gate),
                    "result": {
                        "status": "capacity_gate_refused",
                        "stage": "capture_restart32_rhs",
                        "refused_object": "captured_restart32_rhs_vector",
                        "side": str(self._side_system.side),
                        "candidate": evidence,
                        "gate": dict(gate),
                    },
                }
            )
            return {"status": "capacity_gate_refused", "gate": dict(gate)}
        captured = None
        allocation_error = None
        try:
            captured = source.duplicate()
            source.copy(captured)
        except Exception as exc:  # noqa: BLE001 - allocation is not a budget refusal
            allocation_error = f"{type(exc).__name__}: {exc}"
        allocation_errors = self._comm.allgather(allocation_error)
        if any(value is not None for value in allocation_errors):
            if captured is not None:
                captured.destroy()
            raise RuntimeError(
                "side restart64 RHS capture failed after its memory gate: "
                + "; ".join(
                    f"rank {rank}: {error}"
                    for rank, error in enumerate(allocation_errors)
                    if error is not None
                )
            )
        if captured is None:
            raise RuntimeError("side restart64 RHS capture produced no owned Vec")
        self._side_restart64_candidate_rhs = captured
        state.update(
            {
                "status": "candidate_captured",
                "pending": True,
                "capture_armed": False,
                "candidate_side": str(self._side_system.side),
                "candidate": {
                    "side": str(self._side_system.side),
                    "original_D_rhs_norm": float(source.norm()),
                    "original_D_relative_residual": float(
                        residual_audit["relative_residual"]
                    ),
                    "global_size": int(source.getSize()),
                    "capture_gate": dict(gate),
                    "restart32_evidence": evidence,
                    "captured_owner_sharded": True,
                },
            }
        )
        return {"status": "candidate_captured", "candidate": dict(state["candidate"])}

    @staticmethod
    def _p4_timing_costs(calls: Any) -> dict[str, Any] | None:
        """Summarize existing scalar P4 timers without retaining call records."""

        p4_timing_fields = (
            "factor_solve_seconds",
            "factor_backsolve_seconds",
            "solution_recovery_seconds",
        )
        if not isinstance(calls, list):
            return None
        p4_costs: dict[str, Any] = {"call_count": len(calls), "timings": {}}
        for name in p4_timing_fields:
            values = [
                float(call[name])
                for call in calls
                if isinstance(call, Mapping)
                and isinstance(call.get(name), (int, float))
                and not isinstance(call.get(name), bool)
                and np.isfinite(float(call[name]))
                and float(call[name]) >= 0.0
            ]
            p4_costs["timings"][name] = {
                "sum_of_recorded_rank_local_seconds": float(sum(values)),
                "recorded_call_count": len(values),
                "missing_or_nonfinite_call_count": len(calls) - len(values),
            }
        return p4_costs

    @classmethod
    def _restart32_reference_work(
        cls, solve_record: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Keep bounded scalar cost evidence for the same-RHS restart32 solve."""

        counts = solve_record.get("counts")
        count_delta = counts.get("delta") if isinstance(counts, Mapping) else None
        operations = solve_record.get("operation_seconds")
        local_operations = (
            operations.get("per_rank_accumulated_seconds")
            if isinstance(operations, Mapping)
            else None
        )
        elapsed = solve_record.get("elapsed_seconds")
        if (
            not isinstance(elapsed, (int, float))
            or isinstance(elapsed, bool)
            or not np.isfinite(float(elapsed))
            or float(elapsed) < 0.0
        ):
            elapsed = None
        return {
            "rank": int(solve_record.get("rank", -1)),
            "iterations": int(solve_record.get("iterations", 0)),
            "reason": solve_record.get("reason"),
            "rank_local_elapsed_seconds": solve_record.get(
                "elapsed_local_seconds"
            ),
            "max_rank_elapsed_seconds": elapsed,
            "rank_local_operation_seconds": (
                dict(local_operations)
                if isinstance(local_operations, Mapping)
                else None
            ),
            "rank_local_count_delta": (
                dict(count_delta) if isinstance(count_delta, Mapping) else None
            ),
            "p4_costs": cls._p4_timing_costs(
                solve_record.get("p4_call_history")
            ),
        }

    def _destroy_nested_ksp_for_restart(self) -> None:
        ksp, self._ksp = self._ksp, None
        context, self._pc_context = self._pc_context, None
        if context is not None:
            context.owner = None
        if ksp is not None:
            ksp.destroy()
            self._nested_ksp_destroy_count += 1

    def _create_nested_ksp_for_restart(
        self,
        restart: int,
        *,
        trial_monitor: bool,
        install: bool = False,
    ) -> tuple[Mapping[str, Any], PETSc.KSP, _SidePythonPcContext]:
        if self._operator is None:
            raise RuntimeError("cannot recreate side KSP after operator release")
        if install and self._ksp is not None:
            raise RuntimeError("cannot replace a live side KSP without releasing it")
        ksp = PETSc.KSP().create(self._operator.getComm())
        context = _SidePythonPcContext(self)
        local_error = None
        setup_facts: Mapping[str, Any] = {}
        try:
            ksp.setOperators(self._operator)
            ksp.setType("fgmres")
            ksp.setPCSide(PETSc.PC.Side.RIGHT)
            ksp.setGMRESRestart(int(restart))
            ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
            ksp.setInitialGuessNonzero(False)
            ksp.setTolerances(rtol=self._rtol, atol=0.0, max_it=self._max_it)
            pc = ksp.getPC()
            pc.setType("python")
            pc.setPythonContext(context)
            if trial_monitor:
                ksp.setMonitor(self._trial_monitor)
            else:
                ksp.setMonitor(self._monitor)
            if restart == 64:
                setup_facts = _configure_gmres_restart_trial(ksp)
            ksp.setUp()
        except Exception as exc:  # noqa: BLE001 - setup status is agreed before solve
            local_error = f"{type(exc).__name__}: {exc}"
        records = self._comm.allgather(
            {"error": local_error, "setup_facts": dict(setup_facts)}
        )
        failures = [
            f"rank {rank}: {record['error']}"
            for rank, record in enumerate(records)
            if record.get("error") is not None
        ]
        setup_signatures = [
            json.dumps(
                record.get("setup_facts"),
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            for record in records
        ]
        if setup_signatures and any(
            signature != setup_signatures[0]
            for signature in setup_signatures[1:]
        ):
            failures.append("restart KSP setup facts differ across ranks")
        if failures:
            context.owner = None
            ksp.destroy()
            raise RuntimeError(
                "side restart KSP setup failed collectively; " + "; ".join(failures)
            )
        self._nested_ksp_created_count += 1
        common_setup = records[0].get("setup_facts") if records else {}
        if install:
            self._ksp = ksp
            self._pc_context = context
            self._gmres_restart = int(restart)
        return dict(common_setup or {}), ksp, context

    def _trial_monitor(
        self, _ksp: PETSc.KSP, _iteration: int, _reported_residual: float
    ) -> None:
        self._checkpoint()

    def run_side_restart64_trial(self) -> dict[str, Any]:
        """Compare one captured RHS with restart64 using non-overlapping KSP workspaces."""

        state = self._side_restart64_trial_state
        candidate = self._side_restart64_candidate_rhs
        if (
            not isinstance(state, dict)
            or state.get("status") != "candidate_captured"
            or state.get("trial_count") != 0
            or candidate is None
            or self._destroyed
            or self._apply_in_progress
            or self._active_p4_call_records is not None
            or self._operator is None
            or self._p4_factor is None
            or self._memory_gate_missing()
            or self._ksp is None
            or self._gmres_restart != 32
        ):
            raise RuntimeError("side restart64 trial is not at its sealed safe boundary")
        factor_handle = self._p4_factor
        if self._p4_factor is not factor_handle:
            raise RuntimeError("side restart trial lost its borrowed P4 factor")
        source_norm = float(candidate.norm())
        if not np.isfinite(source_norm) or source_norm <= 0.0:
            raise RuntimeError("captured side restart64 RHS is not finite and nonzero")
        local_operator_rows, local_operator_columns = (
            int(value) for value in self._operator.getLocalSize()
        )
        rhs_binding = {
            "global_size": int(candidate.getSize()),
            "local_size": int(candidate.getLocalSize()),
            "ownership_range": list(map(int, candidate.getOwnershipRange())),
            "local_sha256": _local_complex_vec_sha256(candidate),
            "original_D_rhs_norm": source_norm,
        }
        side = str(self._side_system.side)

        def gate(phase: str, restart: int) -> Mapping[str, Any]:
            if self._side_restart64_memory_gate is None:
                raise RuntimeError("side restart64 live memory callback was released")
            lifecycle = {
                "capture_restart32_rhs": (
                    "restart32_ksp_live_plus_source_rhs_before_candidate_copy"
                ),
                "allocate_restart64": (
                    "restart32_ksp_destroyed_plus_candidate_rhs_live_plus_full_new_restart64_workspace"
                ),
                "restore_restart32": (
                    "restart64_ksp_and_candidate_rhs_destroyed_plus_full_new_restart32_workspace"
                ),
            }.get(phase)
            if lifecycle is None:
                raise ValueError("side restart trial requested an unknown gate phase")
            return self._side_restart64_memory_gate(
                {
                    "phase": phase,
                    "side": side,
                    "restart": int(restart),
                    "workspace_lifecycle": lifecycle,
                    "existing_restart32_ksp_live": phase
                    == "capture_restart32_rhs",
                    "restart64_trial_ksp_live": False,
                    "candidate_rhs_live": phase == "allocate_restart64",
                    "existing_restart32_restart": 32,
                    "local_vector_size": rhs_binding["local_size"],
                    "operator_local_rows": local_operator_rows,
                    "operator_local_columns": local_operator_columns,
                    "rhs_local_sha256": rhs_binding["local_sha256"],
                    "rhs_global_size": rhs_binding["global_size"],
                    "rhs_ownership_range": rhs_binding["ownership_range"],
                    "original_D_rhs_norm": source_norm,
                }
            )

        def release_candidate() -> None:
            nonlocal candidate
            if candidate is not None:
                if self._side_restart64_candidate_rhs is candidate:
                    self._side_restart64_candidate_rhs = None
                candidate.destroy()
                candidate = None

        def update_trial_state(record: dict[str, Any]) -> None:
            state.update(
                {
                    "status": record["status"],
                    "pending": True,
                    "trial_count": 1,
                    "resolved": False,
                    "result": record,
                }
            )
            self._side_restart64_trial_record = dict(record)

        def restore_restart32() -> tuple[Mapping[str, Any], dict[str, Any] | None]:
            if candidate is not None:
                raise RuntimeError("restart32 restore gate ran while candidate RHS was live")
            if self._ksp is not None or self._pc_context is not None:
                raise RuntimeError("restart32 restore gate ran with another KSP live")
            restore_gate = gate("restore_restart32", 32)
            if not isinstance(restore_gate, Mapping) or type(
                restore_gate.get("pass")
            ) is not bool:
                raise RuntimeError("restart32 restore gate returned no explicit decision")
            setup_record: dict[str, Any] | None = None
            if restore_gate.get("pass") is True:
                setup_started = perf_counter()
                setup_facts, _restored_ksp, _restored_context = (
                    self._create_nested_ksp_for_restart(
                        32,
                        trial_monitor=False,
                        install=True,
                    )
                )
                setup_local = float(perf_counter() - setup_started)
                setup_max = float(self._comm.allreduce(setup_local, op=MPI.MAX))
                self._restart_transition_ksp_setup_seconds += setup_max
                setup_rows = self._comm.allgather(
                    {
                        "rank": int(self._comm.rank),
                        "elapsed_local_seconds": setup_local,
                    }
                )
                setup_record = {
                    "setup_facts": dict(setup_facts),
                    "elapsed_seconds_by_rank": setup_rows,
                    "elapsed_max_rank_seconds": setup_max,
                    "restart": 32,
                    "same_p4_factor_handle": self._p4_factor is factor_handle,
                }
            return restore_gate, setup_record

        # Destroy the old nested KSP before taking the full restart64 B sample.
        # Its basis is not retained alongside the trial workspace.
        self._destroy_nested_ksp_for_restart()
        if self._ksp is not None or self._pc_context is not None:
            release_candidate()
            raise RuntimeError("restart32 KSP was not released before restart64 gate")

        trial_ksp: PETSc.KSP | None = None
        trial_context: _SidePythonPcContext | None = None
        solution: PETSc.Vec | None = None
        installed_trial = False
        previous_instrumentation: dict[str, Any] | None = None
        record: dict[str, Any] | None = None
        restore_after_trial = False
        gate64: Mapping[str, Any] | None = None
        choose64 = False
        try:
            gate64 = gate("allocate_restart64", 64)
            if not isinstance(gate64, Mapping) or type(gate64.get("pass")) is not bool:
                raise RuntimeError("restart64 allocation gate returned no explicit decision")
            if gate64.get("pass") is not True:
                restore_after_trial = True
                record = {
                    "status": "capacity_gate_refused",
                    "stage": "allocate_restart64",
                    "refused_object": "one_complete_restart64_FGMRES_KSP_workspace",
                    "side": side,
                    "gate": dict(gate64),
                    "restart64_gate": dict(gate64),
                    "restart32_original_handle_destroyed": True,
                    "restart32_handle_retained": False,
                    "restart32_restore_required": True,
                    "restart32_restored": False,
                    "factor_handle_retained": self._p4_factor is factor_handle,
                    "restart64_trial_selected_restart": None,
                    "candidate_rhs_binding": {
                        **rhs_binding,
                        "rank_layout": gate64.get("rank_layout"),
                        "restart32_reference_work_by_rank": (
                            state["candidate"]["restart32_evidence"].get(
                                "restart32_reference_work_by_rank"
                            )
                        ),
                    },
                    "original_D_rhs_norm": source_norm,
                }
            else:
                trial_setup_started = perf_counter()
                setup_facts, trial_ksp, trial_context = (
                    self._create_nested_ksp_for_restart(
                        64,
                        trial_monitor=True,
                        install=False,
                    )
                )
                trial_setup_elapsed_local = float(perf_counter() - trial_setup_started)
                trial_setup_elapsed_max = float(
                    self._comm.allreduce(trial_setup_elapsed_local, op=MPI.MAX)
                )
                self._restart_transition_ksp_setup_seconds += trial_setup_elapsed_max
                solution_error = None
                try:
                    solution = self._operator.createVecRight()
                    solution.set(0.0)
                except Exception as exc:  # noqa: BLE001 - agree before trial solve
                    solution_error = f"{type(exc).__name__}: {exc}"
                solution_errors = self._comm.allgather(solution_error)
                failures = [
                    f"rank {rank}: {error}"
                    for rank, error in enumerate(solution_errors)
                    if error is not None
                ]
                if failures:
                    raise RuntimeError(
                        "restart64 solution Vec allocation failed collectively; "
                        + "; ".join(failures)
                    )
                assert trial_ksp is not None and trial_context is not None and solution is not None
                previous_instrumentation = {
                    "rhs_operation_seconds": self._rhs_operation_seconds,
                    "rhs_detail_seconds": self._rhs_detail_seconds,
                    "rhs_detail_seen": self._rhs_detail_seen,
                    "active_p4_call_records": self._active_p4_call_records,
                    "active_true_residual_samples": self._active_true_residual_samples,
                    "active_restart32_samples": self._active_restart32_samples,
                }
                trial_p4_call_records: list[dict[str, Any]] = []
                self._rhs_operation_seconds = {
                    name: 0.0 for name in ("Q", "H6", "A6")
                }
                self._rhs_detail_seconds = {
                    name: 0.0 for name in _DETAIL_TIMING_NAMES
                }
                self._rhs_detail_seen = {
                    name: False for name in _DETAIL_TIMING_NAMES
                }
                # This bounded trial has its own short P4 record list.
                self._active_p4_call_records = trial_p4_call_records
                self._active_true_residual_samples = (
                    [] if self._diagnostic_callback is not None else None
                )
                self._active_restart32_samples = None
                before = self._count_snapshot()
                started = perf_counter()
                self._side_restart64_trial_running = True
                self._apply_in_progress = True
                self._active_apply_pc_count = 0
                self._active_pc_index = None
                self._active_pc_q_count = 0
                self._active_rhs_source = candidate
                self._active_rhs_norm = source_norm
                self._pending_pc_exception = None
                self._active_restart64_ksp = trial_ksp
                try:
                    trial_ksp.solve(candidate, solution)
                    pending_pc_exception = self._pending_pc_exception
                    if pending_pc_exception is not None:
                        raise pending_pc_exception
                    reason = int(trial_ksp.getConvergedReason())
                    iterations = int(trial_ksp.getIterationNumber())
                    residual = self._explicit_residual(candidate, solution)
                    candidate_after_sha = _local_complex_vec_sha256(candidate)
                    local_finite = bool(
                        np.isfinite(solution.getArray(readonly=True)).all()
                        and np.isfinite(float(residual["relative_residual"]))
                    )
                    finite = bool(self._comm.allreduce(local_finite, op=MPI.LAND))
                    reason64 = _DIVERGED_ITS
                    if (
                        not finite
                        or candidate_after_sha != rhs_binding["local_sha256"]
                        or iterations < 0
                        or iterations > 128
                        or not (reason > 0 or reason == reason64)
                    ):
                        raise RuntimeError(
                            "restart64 trial changed its RHS or returned a breakdown, "
                            "non-finite state, or unsupported KSP reason"
                        )
                    local_elapsed = float(perf_counter() - started)
                    elapsed = float(self._comm.allreduce(local_elapsed, op=MPI.MAX))
                    operation_timing = self._rhs_operation_timing(
                        local_elapsed, reduce=True
                    )
                    p4_costs = self._p4_timing_costs(trial_p4_call_records)
                    self._total_iterations += iterations
                    self._total_apply_seconds += elapsed
                    after = self._count_snapshot()
                    local_record = {
                        "rank": int(self._comm.rank),
                        "ksp_reason": reason,
                        "iterations": iterations,
                        "original_D_residual": dict(residual),
                        "rank_local_count_delta": self._count_delta(before, after),
                        "elapsed_local_seconds": local_elapsed,
                        "ksp_setup_elapsed_local_seconds": trial_setup_elapsed_local,
                        "operation_seconds": operation_timing,
                        "p4_costs": p4_costs,
                        "same_p4_factor_handle_local": self._p4_factor is factor_handle,
                        "candidate_rhs_unchanged_local": (
                            candidate_after_sha == rhs_binding["local_sha256"]
                        ),
                    }
                    rank_records = self._comm.allgather(local_record)
                    if any(
                        row.get("same_p4_factor_handle_local") is not True
                        for row in rank_records
                    ):
                        raise RuntimeError(
                            "restart64 trial replaced or released the borrowed P4 handle"
                        )
                    if any(
                        row.get("candidate_rhs_unchanged_local") is not True
                        for row in rank_records
                    ):
                        raise RuntimeError(
                            "restart64 trial changed its captured original-D RHS"
                        )
                    if any(
                        row.get("ksp_reason") != reason
                        or row.get("iterations") != iterations
                        or row.get("original_D_residual") != dict(residual)
                        for row in rank_records
                    ):
                        raise RuntimeError(
                            "restart64 trial solve evidence differs across ranks"
                        )
                    eta32 = float(
                        state["candidate"]["original_D_relative_residual"]
                    )
                    eta64 = float(residual["relative_residual"])
                    restart32_work_by_rank = state["candidate"][
                        "restart32_evidence"
                    ].get("restart32_reference_work_by_rank")
                    selection_evidence = _v12_restart64_selection_evidence(
                        eta32,
                        eta64,
                        restart32_work_by_rank,
                        rank_records,
                        trial_elapsed_max_rank_seconds=elapsed,
                        trial_setup_elapsed_max_rank_seconds=(
                            trial_setup_elapsed_max
                        ),
                    )
                    choose64 = selection_evidence["eligible_for_64"] is True
                    restore_after_trial = not choose64
                    if choose64:
                        trial_ksp.setMonitor(self._monitor)
                        self._ksp = trial_ksp
                        self._pc_context = trial_context
                        self._gmres_restart = 64
                        installed_trial = True
                    record = {
                        "status": (
                            "trial_completed_selected_64"
                            if choose64
                            else "trial_completed_retained_32"
                        ),
                        "side": side,
                        "restart32_relative_residual": eta32,
                        "restart64_relative_residual": eta64,
                        "restart64_reason": reason,
                        "restart64_iterations": iterations,
                        "restart64_original_D_residual": dict(residual),
                        "restart64_rank_records": rank_records,
                        "restart64_gate": dict(gate64),
                        "restart32_original_handle_destroyed": True,
                        "restart32_handle_retained": False,
                        "restart32_restore_required": not choose64,
                        "restart32_restored": False,
                        "restart64_handle_retained": choose64,
                        "restart64_mgs_setup": dict(setup_facts),
                        "candidate_rhs_binding": {
                            **rhs_binding,
                            "rank_layout": gate64.get("rank_layout"),
                            "restart32_reference_work_by_rank": (
                                state["candidate"]["restart32_evidence"].get(
                                    "restart32_reference_work_by_rank"
                                )
                            ),
                        },
                        "restart64_cost_scope": (
                            "per-rank side wall, nested KSP setup, Q/H6/A6 timing, P4 scalar timer sums, and PC/P4 action-count deltas; see rank records"
                        ),
                        "trial_elapsed_seconds_max_rank": elapsed,
                        "trial_ksp_setup_elapsed_max_rank_seconds": (
                            trial_setup_elapsed_max
                        ),
                        "trial_transition_wall_including_one_setup_max_rank_seconds": (
                            selection_evidence[
                                "restart64_max_rank_trial_wall_with_setup_seconds"
                            ]
                        ),
                        "same_p4_factor_handle_all_ranks": True,
                        "selected_restart": 64 if choose64 else 32,
                        "selection_rule": _V12_RESTART64_SELECTION_RULE,
                        "selection_evidence": selection_evidence,
                        "cumulative_side_iterations": int(self._total_iterations),
                        "cumulative_side_apply_seconds": float(
                            self._total_apply_seconds
                        ),
                        "cumulative_restart_transition_ksp_setup_seconds": float(
                            self._restart_transition_ksp_setup_seconds
                        ),
                        "cumulative_side_wall_seconds_including_transition_setup": float(
                            self._total_apply_seconds
                            + self._restart_transition_ksp_setup_seconds
                        ),
                    }
                finally:
                    self._active_rhs_source = None
                    self._active_rhs_norm = None
                    self._active_pc_index = None
                    self._active_pc_q_count = 0
                    self._apply_in_progress = False
                    self._active_restart64_ksp = None
                    self._side_restart64_trial_running = False
                    self._pending_pc_exception = None
        finally:
            if solution is not None:
                solution.destroy()
            release_candidate()
            if previous_instrumentation is not None:
                self._rhs_operation_seconds = previous_instrumentation[
                    "rhs_operation_seconds"
                ]
                self._rhs_detail_seconds = previous_instrumentation[
                    "rhs_detail_seconds"
                ]
                self._rhs_detail_seen = previous_instrumentation[
                    "rhs_detail_seen"
                ]
                self._active_p4_call_records = previous_instrumentation[
                    "active_p4_call_records"
                ]
                self._active_true_residual_samples = previous_instrumentation[
                    "active_true_residual_samples"
                ]
                self._active_restart32_samples = previous_instrumentation[
                    "active_restart32_samples"
                ]
            if not installed_trial and trial_ksp is not None:
                if trial_context is not None:
                    trial_context.owner = None
                trial_ksp.destroy()
                self._nested_ksp_destroy_count += 1

        if restore_after_trial:
            if record is None:
                raise RuntimeError("restart32 restore has no terminal trial record")
            restore_gate, restore_setup = restore_restart32()
            record["restart64_trial_selected_restart"] = record.get(
                "selected_restart"
            )
            record["restart32_restore_gate"] = dict(restore_gate)
            record["restart32_restore_setup"] = restore_setup
            if restore_gate.get("pass") is True:
                record["status"] = (
                    "capacity_gate_refused"
                    if record.get("stage") == "allocate_restart64"
                    else "trial_completed_retained_32"
                )
                record["stage"] = record.get("stage", "trial_completed_retained_32")
                record["restart32_restore_required"] = False
                record["restart32_restored"] = True
                record["restart32_handle_retained"] = False
                record["restart32_restored_handle_live"] = self._ksp is not None
                record["selected_restart"] = 32
            else:
                record["status"] = "capacity_gate_refused_restart32_restore"
                record["stage"] = "restore_restart32"
                record["gate"] = dict(restore_gate)
                record["refused_object"] = (
                    "one_complete_restart32_FGMRES_KSP_workspace_for_future_side_apply"
                )
                record["restart32_restore_required"] = True
                record["restart32_restored"] = False
                record["restart32_restored_handle_live"] = False
                record["selected_restart"] = None
                record["restore_capacity_stop_required"] = True
            record["factor_handle_retained"] = self._p4_factor is factor_handle
            record["same_p4_factor_handle_all_ranks"] = bool(
                self._p4_factor is factor_handle
            )
            record["cumulative_side_iterations"] = int(self._total_iterations)
            record["cumulative_side_apply_seconds"] = float(
                self._total_apply_seconds
            )
            record["cumulative_restart_transition_ksp_setup_seconds"] = float(
                self._restart_transition_ksp_setup_seconds
            )
            record[
                "cumulative_side_wall_seconds_including_transition_setup"
            ] = float(
                self._total_apply_seconds
                + self._restart_transition_ksp_setup_seconds
            )
        elif record is not None:
            record["restart32_restore_required"] = False
            record["restart32_restored"] = False
            record["restart32_restored_handle_live"] = False
            record["selected_restart"] = 64
            record["factor_handle_retained"] = self._p4_factor is factor_handle
            record["same_p4_factor_handle_all_ranks"] = bool(
                self._p4_factor is factor_handle
            )
            record[
                "cumulative_side_wall_seconds_including_transition_setup"
            ] = float(
                self._total_apply_seconds
                + self._restart_transition_ksp_setup_seconds
            )

        if record is None:
            raise RuntimeError("side restart trial ended without a terminal record")
        update_trial_state(record)
        return record

    def _memory_gate_missing(self) -> bool:
        return self._side_restart64_memory_gate is None

    def _emit_ksp_true_residual_sample(
        self,
        ksp: PETSc.KSP,
        *,
        iteration: int,
        sample_label: str,
        final_solution: PETSc.Vec | None = None,
        reported_residual: float | None = None,
    ) -> None:
        source = self._active_rhs_source
        if self._diagnostic_callback is None or source is None or self._operator is None:
            return
        solution = final_solution
        owns_solution = solution is None
        if solution is None:
            solution = self._operator.createVecRight()
        residual = self._operator.createVecLeft()
        try:
            if owns_solution:
                # Supplying our own Vec keeps ownership explicit; buildSolution
                # is the public KSP API for the current Krylov approximation.
                ksp.buildSolution(solution)
            self._operator.mult(solution, residual)
            residual.scale(PETSc.ScalarType(-1.0))
            residual.axpy(PETSc.ScalarType(1.0), source)
            local_finite = bool(
                np.isfinite(solution.getArray(readonly=True)).all()
                and np.isfinite(residual.getArray(readonly=True)).all()
            )
            finite = bool(self._comm.allreduce(local_finite, op=MPI.LAND))
            residual_norm = float(residual.norm())
            rhs_norm = self._active_rhs_norm
            relative = (
                residual_norm / rhs_norm
                if rhs_norm is not None and rhs_norm > 0.0
                else 0.0
                if rhs_norm == 0.0 and residual_norm == 0.0
                else None
            )
            finite = bool(
                finite
                and np.isfinite(residual_norm)
                and relative is not None
                and np.isfinite(relative)
            )
            sample = {
                "iteration": int(iteration),
                "sample_label": str(sample_label),
                "reported_residual": (
                    None
                    if reported_residual is None
                    else float(reported_residual)
                ),
                "true_residual_norm": residual_norm,
                "rhs_norm": rhs_norm,
                "true_relative_residual": relative,
                "finite": finite,
            }
            if self._active_true_residual_samples is not None:
                self._active_true_residual_samples.append(dict(sample))
            self._emit_diagnostic(
                "ksp_true_residual_sample",
                vectors={
                    "solution": solution,
                    "rhs": source,
                    "true_residual": residual,
                },
                **sample,
            )
        finally:
            residual.destroy()
            if owns_solution:
                solution.destroy()

    def _emit_diagnostic(
        self,
        event: str,
        *,
        vectors: Mapping[str, PETSc.Vec] | None = None,
        **facts: Any,
    ) -> Any:
        """Synchronously expose borrowed vectors to an opt-in diagnostic."""

        if self._diagnostic_callback is None:
            return None
        record: dict[str, Any] = {
            "event": str(event),
            "p4_backend": self._p4_inverse_backend,
            **facts,
        }
        if self._active_pc_index is not None:
            record["scope"] = (
                "side_apply" if self._apply_in_progress else "direct_pc_apply"
            )
            record["pc_apply_index"] = int(self._active_pc_index)
            if self._active_ksp_iteration is not None:
                record["ksp_iteration"] = int(self._active_ksp_iteration)
        elif self._apply_in_progress:
            record["scope"] = "side_apply"
            if self._active_ksp_iteration is not None:
                record["ksp_iteration"] = int(self._active_ksp_iteration)
        else:
            record["scope"] = "independent_replay"
        if vectors:
            # These PETSc Vecs are borrowed and valid only during this callback.
            record["borrowed_vectors"] = dict(vectors)
        return self._diagnostic_callback(record)

    @staticmethod
    def _p4_call_summary(calls: list[dict[str, Any]]) -> dict[str, Any]:
        fields = (
            "physical_relative_residual",
            "augmented_relative_residual",
            "factor_solve_seconds",
            "factor_backsolve_seconds",
            "solution_recovery_seconds",
        )
        maxima: dict[str, Any] = {}
        for field in fields:
            candidates: list[tuple[float, int]] = []
            missing: list[int] = []
            nonfinite: list[int] = []
            for position, call in enumerate(calls):
                call_index = int(call.get("p4_call_index", position + 1))
                value = call.get(field)
                if value is None or isinstance(value, bool) or not isinstance(
                    value, (int, float)
                ):
                    missing.append(call_index)
                    continue
                if not np.isfinite(float(value)):
                    nonfinite.append(call_index)
                    continue
                else:
                    candidates.append((float(value), call_index))
            maximum = max(candidates, key=lambda candidate: candidate[0]) if candidates else None
            maxima[field] = {
                "maximum": (
                    {"value": maximum[0], "p4_call_index": maximum[1]}
                    if maximum is not None else None
                ),
                "missing_call_indices": missing,
                "nonfinite_call_indices": nonfinite,
            }
        failed = [
            int(call.get("p4_call_index", position + 1))
            for position, call in enumerate(calls)
            if call.get("status") not in {"passed", "ZERO_RHS_DIRECT_ZERO"}
        ]
        augmented_unqualified = [
            int(call.get("p4_call_index", position + 1))
            for position, call in enumerate(calls)
            if call.get("augmented_gate_passed") is not True
        ]
        return {
            "call_count": len(calls),
            "call_index_field": "p4_call_index",
            "call_index_base": "one_based",
            "failed_or_unqualified_call_indices": failed,
            "augmented_residual_unqualified_call_indices": augmented_unqualified,
            "maxima_and_argmax": maxima,
        }

    def _checkpoint(self) -> None:
        self._checkpoint_count += 1
        self._checkpoint_callback()

    def _add_rhs_detail_seconds(self, name: str, elapsed: float) -> None:
        if self._detailed_timing:
            self._rhs_detail_seen[name] = True
            self._rhs_detail_seconds[name] += max(0.0, float(elapsed))

    def _merge_transfer_timing(
        self,
        timing: Mapping[str, float],
        prefix: str,
    ) -> None:
        if not self._detailed_timing:
            return
        for name in _TRANSFER_TIMING_NAMES:
            value = timing.get(name)
            if isinstance(value, (int, float)) and np.isfinite(value):
                self._add_rhs_detail_seconds(
                    f"{prefix}_{name}",
                    float(value),
                )

    def admission_audit(
        self,
        *,
        identity: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Audit the owned BAL_H maps against the live side objects.

        This is a bounded admission check for one side.  It exercises the
        existing owner-routed ``P/P^H`` and ``J/J^H`` adapters, the matching
        p4/p6 actions, and the borrowed ``F/C/D/H`` view.  It records scalar
        distributed norms only; no FE-sized gather or new p6/p4 factor is built.
        """

        if (
            self._destroyed
            or self._side_system is None
            or self._condensed is None
            or self._operator is None
            or self._full_action is None
            or self._p4_factor is None
            or self._owner_transfer is None
        ):
            raise RuntimeError("BAL_H admission audit requires live side components")

        side_system = self._side_system
        condensed = self._condensed
        operator = self._operator
        full_matrix = self._full_action.matrix
        p4_matrix = self._p4_factor.physical_action.matrix
        owner = self._owner_transfer
        comm = self._comm
        vectors: list[PETSc.Vec] = []

        def keep(vector: PETSc.Vec) -> PETSc.Vec:
            vectors.append(vector)
            return vector

        def copy_vector(vector: PETSc.Vec) -> PETSc.Vec:
            result = keep(vector.duplicate())
            vector.copy(result)
            return result

        def fill_bounded(
            vector: PETSc.Vec,
            seed: float,
            slaves: np.ndarray | None = None,
        ) -> None:
            first, last = (int(value) for value in vector.getOwnershipRange())
            global_ids = np.arange(first, last, dtype=np.int64)
            values = vector.getArray()
            values[:] = (
                seed
                + 0.0078125 * (global_ids % 11)
                + 1j * (0.125 * seed + 0.00390625 * (global_ids % 13))
            ).astype(PETSc.ScalarType)
            if slaves is not None and len(slaves):
                values[np.asarray(slaves, dtype=np.int64)] = 0.0
            vector.assemble()

        def norm(vector: PETSc.Vec) -> float:
            return float(vector.norm())

        def relative(numerator: float, denominator: float) -> float:
            return numerator / max(denominator, 1.0e-30)

        def difference_norm(left: PETSc.Vec, right: PETSc.Vec) -> float:
            difference = left.duplicate()
            try:
                left.copy(difference)
                difference.axpy(PETSc.ScalarType(-1.0), right)
                return norm(difference)
            finally:
                difference.destroy()

        def all_finite(*items: PETSc.Vec) -> bool:
            local = all(
                bool(np.isfinite(vector.getArray(readonly=True)).all())
                for vector in items
            )
            return bool(comm.allreduce(local, op=MPI.LAND))

        def max_selected(vector: PETSc.Vec, indices: np.ndarray) -> float:
            values = np.asarray(vector.getArray(readonly=True))
            local = (
                float(np.max(np.abs(values[indices])))
                if len(indices)
                else 0.0
            )
            return float(comm.allreduce(local, op=MPI.MAX))

        def complex_scalar(value: Any) -> dict[str, float]:
            number = complex(value)
            return {
                "real": float(number.real),
                "imag": float(number.imag),
                "abs": float(abs(number)),
            }

        thresholds = {
            "transfer_dot_relative": 1.0e-10,
            "trace_dot_relative": 1.0e-10,
            "galerkin_relative": 1.0e-10,
            "condensed_action_relative": 1.0e-10,
        }
        try:
            coarse_slaves = np.asarray(owner._coarse_slaves, dtype=np.int64)
            fine_slaves = np.asarray(owner._fine_slaves, dtype=np.int64)

            q1 = keep(p4_matrix.createVecRight())
            q2 = keep(q1.duplicate())
            fill_bounded(q1, 0.125, coarse_slaves)
            fill_bounded(q2, -0.375, coarse_slaves)
            q1_before = copy_vector(q1)
            q2_before = copy_vector(q2)
            p_q1 = keep(owner.apply_primal(q1))
            p_q2 = keep(owner.apply_primal(q2))
            p_q1_repeat = keep(owner.apply_primal(q1))
            fine_probe = keep(full_matrix.createVecRight())
            fill_bounded(fine_probe, 0.625, fine_slaves)
            fine_probe_before = copy_vector(fine_probe)
            ph_probe = keep(owner.apply_adjoint(fine_probe))

            transfer_lhs = p_q1.dot(fine_probe)
            transfer_rhs = q1.dot(ph_probe)
            transfer_dot_abs = float(abs(transfer_lhs - transfer_rhs))
            transfer_dot_rel = relative(
                transfer_dot_abs,
                max(abs(transfer_lhs), abs(transfer_rhs)),
            )
            p_alternation_abs = difference_norm(p_q1, p_q1_repeat)
            p_alternation_rel = relative(
                p_alternation_abs,
                max(norm(p_q1), norm(p_q1_repeat)),
            )
            from dolfinx import fem

            coarse_field = fem.Function(owner.coarse_floquet.mpc.function_space)
            fine_oracle = fem.Function(owner.fine_floquet.mpc.function_space)
            try:
                q1.copy(coarse_field.x.petsc_vec)
                coarse_field.x.scatter_forward()
                owner.coarse_floquet.mpc.homogenize(coarse_field)
                coarse_field.x.scatter_forward()
                owner.coarse_floquet.mpc.backsubstitution(coarse_field)
                coarse_field.x.scatter_forward()
                fine_oracle.interpolate(coarse_field)
                fine_oracle.x.scatter_forward()
                owner.fine_floquet.mpc.homogenize(fine_oracle)
                fine_oracle.x.scatter_forward()
                oracle_absolute = difference_norm(
                    p_q1, fine_oracle.x.petsc_vec
                )
                oracle_norm = norm(fine_oracle.x.petsc_vec)
            finally:
                del coarse_field, fine_oracle
            oracle_relative = relative(oracle_absolute, norm(p_q1))
            transfer = {
                "dot_lhs_Pq_f": complex_scalar(transfer_lhs),
                "dot_rhs_q_PHf": complex_scalar(transfer_rhs),
                "dot_absolute": transfer_dot_abs,
                "dot_relative": transfer_dot_rel,
                "q1_input_unchanged_norm": difference_norm(q1_before, q1),
                "q2_input_unchanged_norm": difference_norm(q2_before, q2),
                "fine_probe_input_unchanged_norm": difference_norm(
                    fine_probe_before, fine_probe
                ),
                "fine_owned_slave_max": max_selected(p_q1, fine_slaves),
                "coarse_owned_slave_max": max_selected(ph_probe, coarse_slaves),
                "alternating_q1_repeat_absolute": p_alternation_abs,
                "alternating_q1_repeat_relative": p_alternation_rel,
                "independent_fe_oracle_absolute": oracle_absolute,
                "independent_fe_oracle_relative": oracle_relative,
                "independent_fe_oracle_norm": oracle_norm,
                "q1_norm": norm(q1),
                "q2_norm": norm(q2),
                "fine_probe_norm": norm(fine_probe),
                "finite": all_finite(q1, q2, p_q1, p_q2, p_q1_repeat, fine_probe, ph_probe),
            }
            transfer_checks = {
                "finite": transfer["finite"],
                "dot": bool(transfer_dot_rel <= thresholds["transfer_dot_relative"]),
                "fine_owned_slaves_zero": transfer["fine_owned_slave_max"] == 0.0,
                "coarse_owned_slaves_zero": transfer["coarse_owned_slave_max"] == 0.0,
                "inputs_unchanged": bool(
                    transfer["q1_input_unchanged_norm"] == 0.0
                    and transfer["q2_input_unchanged_norm"] == 0.0
                    and transfer["fine_probe_input_unchanged_norm"] == 0.0
                ),
                "alternating": bool(
                    p_alternation_rel <= thresholds["transfer_dot_relative"]
                ),
                "independent_fe_oracle": bool(
                    oracle_relative <= thresholds["transfer_dot_relative"]
                ),
                "nonzero_inputs": bool(
                    transfer["q1_norm"] > 0.0
                    and transfer["q2_norm"] > 0.0
                    and transfer["fine_probe_norm"] > 0.0
                ),
            }
            transfer["checks"] = transfer_checks
            transfer["pass"] = all(transfer_checks.values())

            full_probe = keep(full_matrix.createVecRight())
            fill_bounded(full_probe, -0.25)
            full_probe_before = copy_vector(full_probe)
            active_probe = keep(operator.createVecRight())
            fill_bounded(active_probe, 0.875)
            active_probe_before = copy_vector(active_probe)
            active_j = keep(extract_full_p6_to_active_trace(condensed, full_probe))
            full_jh = keep(full_matrix.createVecRight())
            inject_active_residual_to_full_p6(condensed, active_probe, full_jh)
            active_original = np.asarray(
                condensed.trace_constraints.owned_active_original_dofs,
                dtype=PETSc.IntType,
            )
            full_first = int(full_jh.getOwnershipRange()[0])
            local_active = active_original.astype(np.int64) - full_first
            local_interior = np.ones(full_jh.getLocalSize(), dtype=bool)
            local_interior[local_active] = False
            interior_max_local = (
                float(
                    np.max(
                        np.abs(
                            np.asarray(full_jh.getArray(readonly=True))[local_interior]
                        )
                    )
                )
                if np.any(local_interior)
                else 0.0
            )
            interior_max = float(comm.allreduce(interior_max_local, op=MPI.MAX))
            trace_lhs = active_j.dot(active_probe)
            trace_rhs = full_probe.dot(full_jh)
            trace_dot_abs = float(abs(trace_lhs - trace_rhs))
            trace_dot_rel = relative(
                trace_dot_abs,
                max(abs(trace_lhs), abs(trace_rhs)),
            )
            trace = {
                "dot_lhs_Jfull_y": complex_scalar(trace_lhs),
                "dot_rhs_full_JHy": complex_scalar(trace_rhs),
                "dot_absolute": trace_dot_abs,
                "dot_relative": trace_dot_rel,
                "full_input_unchanged_norm": difference_norm(
                    full_probe_before, full_probe
                ),
                "active_input_unchanged_norm": difference_norm(
                    active_probe_before, active_probe
                ),
                "injected_interior_max": interior_max,
                "active_rows_local": int(active_original.size),
                "finite": all_finite(full_probe, active_probe, active_j, full_jh),
            }
            trace_checks = {
                "finite": trace["finite"],
                "dot": bool(trace_dot_rel <= thresholds["trace_dot_relative"]),
                "interior_zero": trace["injected_interior_max"] == 0.0,
                "inputs_unchanged": bool(
                    trace["full_input_unchanged_norm"] == 0.0
                    and trace["active_input_unchanged_norm"] == 0.0
                ),
                "nonzero_inputs": bool(
                    norm(full_probe) > 0.0 and norm(active_probe) > 0.0
                ),
            }
            trace["checks"] = trace_checks
            trace["pass"] = all(trace_checks.values())

            a6_pq = keep(full_matrix.createVecLeft())
            full_matrix.mult(p_q1, a6_pq)
            ph_a6_p = keep(owner.apply_adjoint(a6_pq))
            a4_q = keep(p4_matrix.createVecLeft())
            p4_matrix.mult(q1, a4_q)
            galerkin_absolute = difference_norm(ph_a6_p, a4_q)
            galerkin_relative = relative(galerkin_absolute, norm(a4_q))
            galerkin = {
                "absolute": galerkin_absolute,
                "relative": galerkin_relative,
                "p4_output_norm": norm(a4_q),
                "finite": all_finite(p_q1, a6_pq, ph_a6_p, a4_q),
            }
            galerkin_checks = {
                "finite": galerkin["finite"],
                "relative": bool(
                    galerkin_relative <= thresholds["galerkin_relative"]
                ),
                "nonzero_input": bool(norm(q1) > 0.0),
            }
            galerkin["checks"] = galerkin_checks
            galerkin["pass"] = all(galerkin_checks.values())

            from .hybrid_local_dtn_action import (
                create_hybrid_local_dtn_action_components,
            )

            action_source = keep(operator.createVecRight())
            fill_bounded(action_source, 0.4375)
            action_source_before = copy_vector(action_source)
            action_before = keep(operator.createVecLeft())
            operator.mult(action_source, action_before)
            components = create_hybrid_local_dtn_action_components(side_system)
            components_destroyed = False
            try:
                component_action = keep(operator.createVecLeft())
                components.mult(action_source, component_action)
                component_difference = difference_norm(action_before, component_action)
                small_h_condition_number = float(components.h_condition_number)
            finally:
                components.destroy()
                components_destroyed = True
            action_relative = relative(component_difference, norm(action_before))
            condensed_action = {
                "F_C_H_D_action_absolute": component_difference,
                "F_C_H_D_action_relative": action_relative,
                "source_unchanged_norm": difference_norm(
                    action_source_before, action_source
                ),
                "small_h_audit_factor": {
                    "created": True,
                    "creation_count": 1,
                    "destroyed": components_destroyed,
                    "destroy_count": int(components_destroyed),
                    "source": "borrowed side_system.blocks.H",
                    "condition_number": small_h_condition_number,
                    "new_p6_p4_factor": False,
                },
                "finite": all_finite(
                    action_source,
                    action_before,
                    component_action,
                ),
            }
            condensed_checks = {
                "finite": condensed_action["finite"],
                "F_C_H_D_identity": bool(
                    action_relative <= thresholds["condensed_action_relative"]
                ),
                "source_unchanged": bool(
                    condensed_action["source_unchanged_norm"] == 0.0
                ),
                "nonzero_input": bool(norm(action_source) > 0.0),
            }
            condensed_action["checks"] = condensed_checks
            condensed_action["pass"] = all(condensed_checks.values())

            checks = {
                "P_PH": bool(transfer["pass"]),
                "J_JH": bool(trace["pass"]),
                "Galerkin": bool(galerkin["pass"]),
                "condensed_action": bool(condensed_action["pass"]),
            }
            return {
                "schema": "task041.h1g2b2b.side_admission.v1",
                "side": str(side_system.side),
                "identity": dict(identity) if identity is not None else {},
                "thresholds": thresholds,
                "P_PH": transfer,
                "J_JH": trace,
                "Galerkin": galerkin,
                "condensed_action": condensed_action,
                "checks": checks,
                "pass": all(checks.values()),
            }
        finally:
            for vector in reversed(vectors):
                vector.destroy()

    def _apply_a6_callback(self, source: PETSc.Vec) -> PETSc.Vec:
        if self._full_action is None:
            raise RuntimeError("BAL_H full p6 action has been destroyed")
        target = self._full_action.matrix.createVecLeft()
        started = perf_counter()
        try:
            self._full_action.matrix.mult(source, target)
            self._a6_count += 1
            return target
        except BaseException:
            target.destroy()
            raise
        finally:
            self._add_rhs_detail_seconds(
                "balance_a6_seconds", perf_counter() - started
            )

    def _apply_ph_callback(self, source: PETSc.Vec) -> PETSc.Vec:
        if self._owner_transfer is None:
            raise RuntimeError("BAL_H owner transfer has been destroyed")
        self._ph_audit_count += 1
        self._ph_total_count += 1
        started = perf_counter()
        transfer_timing: dict[str, float] = {}
        result = None
        try:
            self._emit_diagnostic("PH_input", vectors={"source": source})
            kwargs = {"timing": transfer_timing} if self._detailed_timing else {}
            result = self._owner_transfer.apply_adjoint(source, **kwargs)
            try:
                self._emit_diagnostic("PH_output", vectors={"result": result})
            except BaseException:
                try:
                    result.destroy()
                except BaseException:  # noqa: BLE001, S110 - preserve callback error
                    pass
                result = None
                raise
            return result
        finally:
            self._add_rhs_detail_seconds(
                "balance_ph_seconds", perf_counter() - started
            )
            self._merge_transfer_timing(transfer_timing, "balance_ph")

    def _apply_h6_callback(self, source: PETSc.Vec) -> PETSc.Vec:
        if self._h6 is None:
            raise RuntimeError("BAL_H H6 action has been destroyed")
        self._h6_count += 1
        started = perf_counter()
        try:
            return self._h6.apply(source)
        finally:
            self._add_rhs_detail_seconds(
                "balance_h6_seconds", perf_counter() - started
            )

    def _apply_q_callback(
        self,
        source: PETSc.Vec,
        *,
        return_leading_dual: bool = False,
        fixed_p4_correction_steps: int | None = None,
    ) -> PETSc.Vec | tuple[PETSc.Vec, PETSc.Vec]:
        if not isinstance(return_leading_dual, bool):
            raise TypeError("return_leading_dual must be a boolean")
        if fixed_p4_correction_steps is not None and (
            isinstance(fixed_p4_correction_steps, bool)
            or not isinstance(fixed_p4_correction_steps, int)
            or fixed_p4_correction_steps != 1
        ):
            raise ValueError(
                "the fixed physical BAL_H Q policy supports exactly one P4 correction"
            )
        if not return_leading_dual:
            return self._apply_q_callback_impl(
                source,
                fixed_p4_correction_steps=fixed_p4_correction_steps,
            )
        if not self._reuse_leading_ph_dual:
            raise RuntimeError("leading PH handoff was not enabled for this side")

        handoff: dict[str, PETSc.Vec | None] = {}
        try:
            result = self._apply_q_callback_impl(
                source,
                handoff_state=handoff,
                fixed_p4_correction_steps=fixed_p4_correction_steps,
            )
            leading_dual = handoff.get("leading_dual")
            if (
                result is None
                or result is not handoff.get("coarse_output")
                or leading_dual is None
            ):
                raise RuntimeError("leading PH handoff completed without both Vecs")
        except BaseException:
            released: set[int] = set()
            for vector in handoff.values():
                if vector is not None and id(vector) not in released:
                    released.add(id(vector))
                    try:
                        vector.destroy()
                    except BaseException:  # noqa: BLE001, S110 - preserve Q callback error
                        pass
            raise
        handoff.clear()
        return result, leading_dual

    def _apply_q_callback_impl(
        self,
        source: PETSc.Vec,
        *,
        handoff_state: dict[str, PETSc.Vec | None] | None = None,
        fixed_p4_correction_steps: int | None = None,
    ) -> PETSc.Vec:
        if self._owner_transfer is None or self._p4_factor is None:
            raise RuntimeError("BAL_H coarse components have been destroyed")
        if fixed_p4_correction_steps is not None and (
            type(fixed_p4_correction_steps) is not int
            or fixed_p4_correction_steps != 1
        ):
            raise ValueError("fixed physical BAL_H requests exactly one correction")
        self._last_fixed_q_solve_audit = None
        fixed_q_input_global_norm = (
            float(source.norm())
            if fixed_p4_correction_steps is not None
            else None
        )
        if fixed_p4_correction_steps is not None and (
            not np.isfinite(fixed_q_input_global_norm)
            or fixed_q_input_global_norm < 0.0
        ):
            raise FloatingPointError("fixed-Q input norm is non-finite or negative")
        call_history = (
            self._active_p4_call_records
            if self._apply_in_progress
            else self._direct_p4_call_records
        )
        if (
            fixed_p4_correction_steps is None
            and self._diagnostic_callback is not None
            and call_history is not None
            and len(call_history) >= 2 * (self._max_it + 1)
        ):
            raise RuntimeError(
                "BAL_H p4 diagnostic call history exceeded its KSP bound"
            )
        self._q_count += 1
        if self._active_pc_index is not None:
            self._active_pc_q_count += 1
            q_call_index = self._active_pc_q_count
        elif fixed_p4_correction_steps is not None:
            q_call_index = int(self._q_count)
        else:
            q_call_index = len(self._direct_p4_call_records) + 1
        correction_steps = (
            int(self._diagnostic_p4_correction_steps)
            if fixed_p4_correction_steps is None
            else fixed_p4_correction_steps
        )
        record_restart_trial_costs = bool(
            self._side_restart64_trial_running
            or self._side_restart64_capture_is_armed()
        )
        record_p4_timing = bool(self._detailed_timing or record_restart_trial_costs)

        def observe_p4_correction(
            audit: Mapping[str, Any], vectors: Mapping[str, Any]
        ) -> None:
            callback = self._diagnostic_p4_correction_callback
            if callback is None:
                raise RuntimeError("P4 correction observer disappeared during replay")
            fe_solution = None
            fe_correction = None
            p_output = None
            local_error = None
            try:
                if self._p4_inverse_backend == "full":
                    fe_solution = self._p4_factor.extract_fe_solution(
                        vectors["solution"]
                    )
                    if vectors.get("correction") is not None:
                        fe_correction = self._p4_factor.extract_fe_solution(
                            vectors["correction"]
                        )
                else:
                    fe_solution = vectors["solution"]
                    fe_correction = vectors.get("correction")
                if not isinstance(fe_solution, PETSc.Vec):
                    raise TypeError("P4 correction observer has no FE solution")
            except BaseException as exc:  # noqa: BLE001 - synchronize before P
                local_error = f"{type(exc).__name__}: {exc}"
            errors = self._comm.allgather(local_error)
            if any(value is not None for value in errors):
                if self._p4_inverse_backend == "full":
                    if fe_correction is not None:
                        fe_correction.destroy()
                    if fe_solution is not None:
                        fe_solution.destroy()
                raise RuntimeError(f"P4 correction state extraction failed: {errors}")
            try:
                p_output = self._owner_transfer.apply_primal(fe_solution)
                port_state = {
                    key: (
                        None
                        if vectors.get(key) is None
                        else [
                            [float(value.real), float(value.imag)]
                            for value in np.asarray(vectors[key]).reshape(-1)
                        ]
                    )
                    for key in (
                        "port_solution",
                        "port_rhs",
                        "port_residual",
                        "port_correction",
                    )
                }
                callback(
                    {
                        "backend": self._p4_inverse_backend,
                        "q_call_index": int(q_call_index),
                        "p4_audit": dict(audit),
                        "port_state": port_state,
                    },
                    {
                        "solution": fe_solution,
                        "coarse_rhs": coarse_rhs,
                        "fe_residual": vectors["fe_residual"],
                        "correction": fe_correction,
                        "p_output": p_output,
                        "q_input": source,
                    },
                )
            finally:
                if p_output is not None:
                    p_output.destroy()
                if self._p4_inverse_backend == "full":
                    if fe_correction is not None:
                        fe_correction.destroy()
                    if fe_solution is not None:
                        fe_solution.destroy()
        self._ph_total_count += 1
        self._emit_diagnostic(
            "Q_input",
            vectors={"source": source},
            q_call_index=int(q_call_index),
        )
        ph_started = perf_counter()
        ph_transfer_timing: dict[str, float] = {}
        coarse_rhs = None
        try:
            kwargs = (
                {"timing": ph_transfer_timing} if self._detailed_timing else {}
            )
            coarse_rhs = self._owner_transfer.apply_adjoint(source, **kwargs)
            if handoff_state is not None:
                handoff_state["leading_dual"] = coarse_rhs
        finally:
            self._add_rhs_detail_seconds(
                "q_ph_seconds", perf_counter() - ph_started
            )
            self._merge_transfer_timing(ph_transfer_timing, "q_ph")
        augmented_rhs = None
        augmented_solution = None
        coarse_solution = None
        solution_norm: float | None = None
        solution_norm_status = "not_measured_no_solution"
        capture_port_values = False
        p4_timing: dict[str, float] = {}
        factor_solve_before = _p4_solve_count(self._p4_factor)
        refinement_target_tolerance = (
            None
            if fixed_p4_correction_steps is not None
            else self._p4_refinement_target_tolerance
        )
        record_p4_refinement = bool(
            fixed_p4_correction_steps is None
            and (
                self._diagnostic_callback is not None
                or refinement_target_tolerance is not None
            )
        )
        try:
            self._emit_diagnostic(
                "PH_Q_output",
                vectors={"result": coarse_rhs},
                q_call_index=int(q_call_index),
            )
            if self._p4_inverse_backend == "cell_condensed":
                capture_port_values = self._emit_diagnostic(
                    "p4_rhs",
                    vectors={"rhs": coarse_rhs},
                    q_call_index=int(q_call_index),
                    rhs_global_size=int(coarse_rhs.getSize()),
                ) is True
                apply_kwargs: dict[str, Any] = {
                    "timing": p4_timing if record_p4_timing else None
                }
                if correction_steps:
                    apply_kwargs["diagnostic_correction_steps"] = correction_steps
                    if self._diagnostic_p4_correction_callback is not None:
                        apply_kwargs["diagnostic_callback"] = observe_p4_correction
                if refinement_target_tolerance is not None:
                    apply_kwargs["refinement_target_tolerance"] = (
                        refinement_target_tolerance
                    )
                if capture_port_values:
                    apply_kwargs["capture_port_values"] = True
                coarse_solution = self._p4_factor.apply(coarse_rhs, **apply_kwargs)
            else:
                allocation_started = perf_counter()
                try:
                    augmented_rhs = self._p4_factor.create_rhs(coarse_rhs)
                    augmented_solution = augmented_rhs.duplicate()
                    augmented_solution.set(0.0)
                finally:
                    self._add_rhs_detail_seconds(
                        "q_augmented_rhs_extract_seconds",
                        perf_counter() - allocation_started,
                    )
            if self._p4_inverse_backend == "full":
                capture_port_values = self._emit_diagnostic(
                    "p4_rhs",
                    vectors={"rhs": augmented_rhs},
                    q_call_index=int(q_call_index),
                    rhs_global_size=int(augmented_rhs.getSize()),
                ) is True
                solve_kwargs: dict[str, Any] = {
                    "residual_tolerance": 1.0e-10
                }
                if record_p4_timing:
                    solve_kwargs["timing"] = p4_timing
                if self._diagnostic_callback is not None:
                    solve_kwargs["diagnostic_audit"] = True
                if correction_steps:
                    solve_kwargs["diagnostic_correction_steps"] = correction_steps
                    if self._diagnostic_p4_correction_callback is not None:
                        solve_kwargs["diagnostic_callback"] = observe_p4_correction
                if refinement_target_tolerance is not None:
                    solve_kwargs["refinement_target_tolerance"] = (
                        refinement_target_tolerance
                    )
                if capture_port_values:
                    solve_kwargs["capture_port_values"] = True
                self._p4_factor.solve_with_refinement(
                    augmented_rhs,
                    augmented_solution,
                    **solve_kwargs,
                )
                extract_started = perf_counter()
                try:
                    coarse_solution = self._p4_factor.extract_fe_solution(
                        augmented_solution
                    )
                finally:
                    self._add_rhs_detail_seconds(
                        "q_augmented_rhs_extract_seconds",
                        perf_counter() - extract_started,
                    )
            if fixed_p4_correction_steps is not None:
                factor_solve_after = _p4_solve_count(self._p4_factor)
                actual_q_backsolves = factor_solve_after - factor_solve_before
                if actual_q_backsolves < 0:
                    raise RuntimeError("fixed physical BAL_H P4 solve counter moved backwards")
                if (
                    self._p4_inverse_backend == "cell_condensed"
                    and isinstance(
                        getattr(self._p4_factor, "inverse", None),
                        P4CellCondensedInverse,
                    )
                ):
                    step_deltas = _fixed_q_cell_solve_audit(
                        self._p4_factor,
                        solve_count_before=factor_solve_before,
                        solve_count_after=factor_solve_after,
                    )
                    last_solve = self._p4_factor.diagnostics["last_solve"]
                    inverse_history = tuple(
                        dict(entry)
                        for entry in last_solve["inverse_apply_history"]
                    )
                    audit_source = "P4CellCondensedInverse.last_audit_per_apply"
                else:
                    # The full augmented backend and legacy dense test doubles
                    # have no direct-zero inverse path; both calls must solve.
                    if actual_q_backsolves != 2:
                        raise RuntimeError(
                            "fixed physical BAL_H non-shortcut P4 backend did not "
                            "execute both inverse calls"
                        )
                    step_deltas = (1, 1)
                    inverse_history = None
                    audit_source = "backend_counter_no_direct_zero_path"
                self._last_fixed_q_solve_audit = {
                    "mathematical_correction_steps": 1,
                    "q_input_global_norm": float(fixed_q_input_global_norm),
                    "q_input_global_exact_zero": (
                        float(fixed_q_input_global_norm) == 0.0
                    ),
                    "factor_solve_count_before": factor_solve_before,
                    "factor_solve_count_after": factor_solve_after,
                    "factor_solve_call_delta": actual_q_backsolves,
                    "factor_solve_deltas_by_step": tuple(step_deltas),
                    "inverse_apply_history": inverse_history,
                    "audit_source": audit_source,
                }
            if self._diagnostic_callback is not None and coarse_solution is not None:
                solution_norm = float(coarse_solution.norm())
                solution_norm_status = "measured"
            if capture_port_values:
                last_solve = self._p4_factor.diagnostics.get("last_solve", {})
                self._emit_diagnostic(
                    "p4_port_solution",
                    q_call_index=int(q_call_index),
                    port_solution_complex=last_solve.get(
                        "port_solution_complex"
                    ),
                    port_rhs_complex=last_solve.get("port_rhs_complex"),
                    port_projection_complex=last_solve.get(
                        "port_projection_complex"
                    ),
                    port_values_available=(
                        isinstance(last_solve.get("port_solution_complex"), list)
                    ),
                )
            self._emit_diagnostic(
                "p4_recovered_solution",
                vectors={"solution": coarse_solution},
                q_call_index=int(q_call_index),
                solution_global_size=int(coarse_solution.getSize()),
            )
            p_started = perf_counter()
            p_transfer_timing: dict[str, float] = {}
            result = None
            try:
                kwargs = (
                    {"timing": p_transfer_timing} if self._detailed_timing else {}
                )
                result = self._owner_transfer.apply_primal(
                    coarse_solution,
                    **kwargs,
                )
                if handoff_state is not None:
                    handoff_state["coarse_output"] = result
                try:
                    self._emit_diagnostic(
                        "P_output",
                        vectors={"result": result},
                        q_call_index=int(q_call_index),
                    )
                except BaseException:
                    try:
                        result.destroy()
                    except BaseException:  # noqa: BLE001, S110 - preserve callback error
                        pass
                    result = None
                    if handoff_state is not None:
                        handoff_state["coarse_output"] = None
                    raise
            finally:
                self._add_rhs_detail_seconds(
                    "q_p_seconds", perf_counter() - p_started
                )
                self._merge_transfer_timing(p_transfer_timing, "q_p")
            self._p_count += 1
            return result
        finally:
            # Release every Vec before reading or appending optional audit data;
            # diagnostic failures must never strand factor-work vectors.
            active_error = sys.exc_info()[1]
            cleanup_error: BaseException | None = None
            for vector in (
                (
                    None
                    if handoff_state is not None
                    and coarse_rhs is handoff_state.get("leading_dual")
                    else coarse_rhs
                ),
                augmented_rhs,
                augmented_solution,
                coarse_solution,
            ):
                if vector is not None:
                    try:
                        vector.destroy()
                    except BaseException as error:  # noqa: BLE001
                        if cleanup_error is None:
                            cleanup_error = error
            if cleanup_error is not None and active_error is None:
                raise cleanup_error
            if self._detailed_timing:
                if "factor_solve_seconds" in p4_timing:
                    self._add_rhs_detail_seconds(
                        "q_factor_solve_seconds",
                        p4_timing["factor_solve_seconds"],
                    )
                if "factor_backsolve_seconds" in p4_timing:
                    self._add_rhs_detail_seconds(
                        "q_factor_solve_seconds",
                        p4_timing["factor_backsolve_seconds"],
                    )
                if "A4_residual_refinement_seconds" in p4_timing:
                    self._add_rhs_detail_seconds(
                        "q_a4_residual_refinement_seconds",
                        p4_timing["A4_residual_refinement_seconds"],
                    )
                if "native_action_and_residual_seconds" in p4_timing:
                    self._add_rhs_detail_seconds(
                        "q_a4_residual_refinement_seconds",
                        p4_timing["native_action_and_residual_seconds"],
                    )
                if "physical_action_matrix_mult_seconds" in p4_timing:
                    self._add_rhs_detail_seconds(
                        "q_physical_action_matrix_mult_seconds",
                        p4_timing["physical_action_matrix_mult_seconds"],
                    )
                if "native_action_matrix_mult_seconds" in p4_timing:
                    self._add_rhs_detail_seconds(
                        "q_physical_action_matrix_mult_seconds",
                        p4_timing["native_action_matrix_mult_seconds"],
                    )
                if "storage_rhs_reduction_seconds" in p4_timing:
                    self._add_rhs_detail_seconds(
                        "q_p4_storage_rhs_reduction_seconds",
                        p4_timing["storage_rhs_reduction_seconds"],
                    )
                if "solution_recovery_seconds" in p4_timing:
                    self._add_rhs_detail_seconds(
                        "q_p4_solution_recovery_seconds",
                        p4_timing["solution_recovery_seconds"],
                    )
            factor_solve_after = _p4_solve_count(self._p4_factor)
            actual_backsolves = factor_solve_after - factor_solve_before
            if actual_backsolves < 0:
                raise RuntimeError("BAL_H P4 solve counter moved backwards")
            self._p4_backsolve_count += actual_backsolves
            self._p4_refinement_count += max(actual_backsolves - 1, 0)
            if record_p4_refinement:
                try:
                    factor_diagnostics = self._p4_factor.diagnostics
                    last_solve = factor_diagnostics.get("last_solve", {})
                except BaseException as diagnostic_error:  # noqa: BLE001
                    last_solve = {
                        "diagnostic_read_error": {
                            "type": type(diagnostic_error).__name__,
                            "message": str(diagnostic_error),
                        }
                    }
                physical_rhs_norm = (
                    last_solve.get(
                        "physical_rhs_norm",
                        last_solve.get("rhs_norm"),
                    )
                    if isinstance(last_solve, Mapping)
                    else None
                )
                scalar_summary = {
                    key: last_solve[key]
                    for key in (
                        "status",
                        "rhs_norm",
                        "physical_rhs_norm",
                        "residual_norm",
                        "relative_residual",
                        "physical_relative_residual",
                        "augmented_relative_residual",
                        "augmented_gate_passed",
                        "augmented_rhs_norm",
                        "port_residual_norm",
                        "backsolve_count",
                        "refinement_count",
                        "actual_correction_count",
                        "refinement_target_tolerance",
                        "target_reached",
                        "stop_reason",
                    )
                    if isinstance(last_solve, Mapping)
                    and isinstance(
                        last_solve.get(key),
                        (int, float, bool, str),
                    )
                }
                scalar_summary.update(
                    {
                        "physical_rhs_norm": physical_rhs_norm,
                        "solution_norm": solution_norm,
                        "solution_norm_status": solution_norm_status,
                        "fixed_p4_correction_steps": (
                            fixed_p4_correction_steps
                        ),
                        "configured_refinement_target_tolerance": (
                            self._p4_refinement_target_tolerance
                        ),
                        "effective_refinement_target_tolerance": (
                            refinement_target_tolerance
                        ),
                    }
                )
                if correction_steps or refinement_target_tolerance is not None:
                    correction_history = (
                        last_solve.get("diagnostic_correction_history", [])
                        if isinstance(last_solve, Mapping)
                        else []
                    )
                    scalar_summary["diagnostic_correction_history"] = [
                        {
                            key: value
                            for key, value in step.items()
                            if isinstance(
                                value,
                                (bool, int, float, str, type(None)),
                            )
                        }
                        for step in correction_history
                        if isinstance(step, Mapping)
                    ] if isinstance(correction_history, (list, tuple)) else []
                call_record = {
                    "p4_call_index": (
                        len(self._active_p4_call_records or []) + 1
                        if self._apply_in_progress
                        else len(self._direct_p4_call_records) + 1
                    ),
                    "scope": (
                        "side_apply"
                        if self._apply_in_progress
                        else "independent_q_replay"
                    ),
                    "pc_apply_index": (
                        self._active_pc_index
                        if self._apply_in_progress
                        else None
                    ),
                    "q_call_index": int(q_call_index),
                    "ksp_iteration": (
                        int(self._active_ksp_iteration)
                        if self._apply_in_progress
                        and self._active_ksp_iteration is not None
                        else None
                    ),
                    "backend": self._p4_inverse_backend,
                    "factor_solve_count_delta": int(actual_backsolves),
                    "last_solve_scalar_summary": scalar_summary,
                    "factor_solve_seconds": p4_timing.get(
                        "factor_solve_seconds"
                    ),
                    "factor_backsolve_seconds": p4_timing.get(
                        "factor_backsolve_seconds"
                    ),
                    "solution_recovery_seconds": p4_timing.get(
                        "solution_recovery_seconds"
                    ),
                    "physical_relative_residual": (
                        last_solve.get("physical_relative_residual")
                        if isinstance(last_solve, Mapping)
                        else None
                    ),
                    "physical_rhs_norm": physical_rhs_norm,
                    "solution_norm": solution_norm,
                    "solution_norm_status": solution_norm_status,
                    "augmented_relative_residual": (
                        last_solve.get(
                            "augmented_relative_residual",
                            last_solve.get("relative_residual"),
                        )
                        if isinstance(last_solve, Mapping)
                        else None
                    ),
                    "status": (
                        last_solve.get("status")
                        if isinstance(last_solve, Mapping)
                        else None
                    ),
                    "augmented_gate_passed": (
                        last_solve.get("augmented_gate_passed")
                        if isinstance(last_solve, Mapping)
                        else None
                    ),
                    "port_residual_norm": (
                        last_solve.get("port_residual_norm")
                        if isinstance(last_solve, Mapping)
                        else None
                    ),
                }
                if fixed_p4_correction_steps is not None:
                    q_solve_audit = self._last_fixed_q_solve_audit
                    if isinstance(q_solve_audit, Mapping):
                        scalar_summary.update(
                            {
                                "mathematical_correction_steps": 1,
                                "factor_solve_delta_sum": int(actual_backsolves),
                                "factor_solve_deltas_by_step": list(
                                    q_solve_audit["factor_solve_deltas_by_step"]
                                ),
                            }
                        )
                        call_record["fixed_q_solve_audit"] = dict(q_solve_audit)
                    elif active_error is None:
                        raise RuntimeError("fixed-Q P4 solve audit was not retained")
                if refinement_target_tolerance is not None:
                    call_record.update(
                        {
                            "refinement_target_tolerance": (
                                refinement_target_tolerance
                            ),
                            "target_reached": last_solve.get("target_reached"),
                            "stop_reason": last_solve.get("stop_reason"),
                            "actual_correction_count": last_solve.get(
                                "actual_correction_count"
                            ),
                        }
                    )
                if self._active_p4_call_records is not None:
                    self._active_p4_call_records.append(call_record)
                else:
                    self._direct_p4_call_records.append(call_record)

    def _apply_balanced_pc(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self._destroyed or self._full_action is None or self._condensed is None:
            raise RuntimeError("BAL_H side inverse has been destroyed")
        if source.getSize() != self.operator.getSize()[1]:
            raise ValueError("BAL_H side PC source has the wrong active size")
        if target.getSize() != self.operator.getSize()[0]:
            raise ValueError("BAL_H side PC target has the wrong active size")
        self._pc_apply_count += 1
        self._active_apply_pc_count += 1
        self._active_pc_index = self._active_apply_pc_count
        self._active_pc_q_count = 0
        if (
            self._apply_in_progress
            and self._diagnostic_callback is not None
            and (self._active_restart64_ksp is not None or self._ksp is not None)
        ):
            active_ksp = (
                self._active_restart64_ksp
                if self._active_restart64_ksp is not None
                else self._ksp
            )
            self._active_ksp_iteration = int(active_ksp.getIterationNumber())
        else:
            self._active_ksp_iteration = None
        self._emit_diagnostic("PC_input", vectors={"source": source})
        full_source = None
        full_output = None
        active_output = None
        coupling_applied = False
        try:
            packing_started = perf_counter()
            try:
                full_source = self._full_action.matrix.createVecRight()
                self._jh_count += 1
                inject_active_residual_to_full_p6(
                    self._condensed,
                    source,
                    full_source,
                )
            finally:
                self._add_rhs_detail_seconds(
                    "balance_jh_inject_allocate_seconds",
                    perf_counter() - packing_started,
                )
            if self._coupling is None:
                raise RuntimeError("BAL_H coupling has been destroyed")
            try:
                coupling_applied = True
                full_output = self._coupling.apply(full_source)
            except BaseException as exc:
                failure: dict[str, Any] = {
                    "exception_type": type(exc).__name__,
                    "exception": str(exc),
                }
                if isinstance(exc, P4PhysicalResidualGateError):
                    failure.update(
                        {
                            "failure_classification": "P4_PHYSICAL_RESIDUAL_GATE",
                            "p4_solve_audit": dict(exc.audit),
                        }
                    )
                elif isinstance(exc, BalancedConstraintRejected):
                    failure.update(
                        {
                            "failure_classification": "BALANCED_CONSTRAINT_REJECTED",
                            "balance_audit": dict(exc.facts),
                        }
                    )
                self._last_coupling_failure = failure
                raise
            finally:
                operation_seconds = self._coupling.last_apply_facts.get(
                    "operation_seconds", {}
                )
                if isinstance(operation_seconds, Mapping):
                    for name in self._rhs_operation_seconds:
                        value = operation_seconds.get(name)
                        if isinstance(value, (int, float)) and np.isfinite(value):
                            self._rhs_operation_seconds[name] += float(value)
                if self._reuse_leading_ph_dual and coupling_applied:
                    counts = self._coupling.last_apply_facts.get("counts", {})
                    reused = (
                        counts.get("PH_audit_leading_reused", 0)
                        if isinstance(counts, Mapping)
                        else 0
                    )
                    if isinstance(reused, int) and not isinstance(reused, bool):
                        self._ph_leading_reused_count += reused
            self._j_count += 1
            active_output = extract_full_p6_to_active_trace(
                self._condensed,
                full_output,
            )
            active_output.copy(target)
            self._emit_diagnostic("PC_output", vectors={"target": target})
        finally:
            if full_source is not None:
                full_source.destroy()
            if full_output is not None:
                full_output.destroy()
            if active_output is not None:
                active_output.destroy()
            self._active_pc_index = None
            self._active_pc_q_count = 0
            if not self._apply_in_progress:
                self._active_ksp_iteration = None

    def _explicit_residual(self, source: PETSc.Vec, target: PETSc.Vec) -> dict[str, Any]:
        if self._operator is None:
            raise RuntimeError("BAL_H side operator has been destroyed")
        operator_output = self._operator.createVecLeft()
        residual = source.duplicate()
        try:
            self._operator.mult(target, operator_output)
            source.copy(residual)
            residual.axpy(PETSc.ScalarType(-1.0), operator_output)
            rhs_norm = float(source.norm())
            residual_norm = float(residual.norm())
            solution_norm = float(target.norm())
            if not all(
                np.isfinite(value)
                for value in (rhs_norm, residual_norm, solution_norm)
            ):
                raise RuntimeError("BAL_H side true residual is non-finite")
            relative = (
                residual_norm / rhs_norm if rhs_norm > 0.0 else residual_norm
            )
            if not np.isfinite(relative):
                raise RuntimeError("BAL_H side true residual ratio is non-finite")
            return {
                "rhs_norm": rhs_norm,
                "solution_norm": solution_norm,
                "residual_norm": residual_norm,
                "relative_residual": relative,
            }
        finally:
            operator_output.destroy()
            residual.destroy()

    def _rhs_operation_timing(
        self, local_elapsed: float, *, reduce: bool
    ) -> dict[str, Any]:
        local = {
            name: float(value) for name, value in self._rhs_operation_seconds.items()
        }
        local_detail = {
            name: (
                float(value) if self._rhs_detail_seen[name] else None
            )
            for name, value in self._rhs_detail_seconds.items()
        }
        local_uncovered = max(0.0, float(local_elapsed) - sum(local.values()))
        if not reduce:
            result = {
                "status": "local_only_after_exception",
                "per_rank_accumulated_seconds": local,
                "per_rank_uncovered_seconds": local_uncovered,
                "max_rank_accumulated_seconds": None,
                "max_rank_uncovered_seconds": None,
                "remaining_diagnostics_seconds": None,
            }
            if self._detailed_timing:
                result["detailed"] = {
                    "logging_rank": int(self._comm.Get_rank()),
                    "local_scope": "logging_rank_only",
                    "per_rank_seconds": local_detail,
                    "max_rank_seconds": None,
                    "interval_semantics": dict(_DETAIL_TIMING_SEMANTICS),
                    "measurement_status": {
                        name: (
                            "measured" if value is not None else "not_called"
                        )
                        for name, value in local_detail.items()
                    },
                    "semantics": (
                        "inclusive local timing regions; q_ph_seconds and q_p_seconds "
                        "contain their prefixed transfer subregions; q_a4_residual_"
                        "refinement_seconds includes extraction, allocation, physical "
                        "action, norm, and audit work, with q_physical_action_matrix_"
                        "mult_seconds nested inside it; balance_jh_inject_allocate_"
                        "seconds covers only JH injection and its Vec allocation"
                    ),
                }
            return result
        names = ("Q", "H6", "A6")
        detail_values = (
            [
                float(self._rhs_detail_seconds[name])
                for name in _DETAIL_TIMING_NAMES
            ]
            if self._detailed_timing
            else []
        )
        detail_seen = (
            [
                float(self._rhs_detail_seen[name])
                for name in _DETAIL_TIMING_NAMES
            ]
            if self._detailed_timing
            else []
        )
        local_values = np.asarray(
            [local[name] for name in names]
            + [local_uncovered]
            + detail_values
            + detail_seen,
            dtype=np.float64,
        )
        max_values = np.empty_like(local_values)
        self._comm.Allreduce(local_values, max_values, op=MPI.MAX)
        max_rank = {
            name: float(value)
            for name, value in zip(names, max_values[:3])
        }
        result = {
            "status": "measured_rank_max",
            "per_rank_accumulated_seconds": local,
            "per_rank_uncovered_seconds": local_uncovered,
            "max_rank_accumulated_seconds": max_rank,
            "max_rank_uncovered_seconds": float(max_values[3]),
            "remaining_diagnostics_seconds": float(max_values[3]),
            "semantics": (
                "all PC applies in this RHS are accumulated per rank, then one "
                "MPI.MAX buffer reduction is used; component maxima are not summed "
                "as wall and uncovered time is reduced independently; detailed "
                "transfer fields are local intervals, while the q_ph/q_p and "
                "balance_ph fields are inclusive wrappers"
            ),
        }
        if self._detailed_timing:
            detail_start = 4
            detail_stop = detail_start + len(_DETAIL_TIMING_NAMES)
            result["detailed"] = {
                "logging_rank": int(self._comm.Get_rank()),
                "local_scope": "logging_rank_only",
                "per_rank_seconds": local_detail,
                "interval_semantics": dict(_DETAIL_TIMING_SEMANTICS),
                "max_rank_seconds": {
                    name: (
                        float(value)
                        if bool(
                            max_values[
                                detail_start + index + len(_DETAIL_TIMING_NAMES)
                            ]
                        )
                        else None
                    )
                    for index, (name, value) in enumerate(
                        zip(
                            _DETAIL_TIMING_NAMES,
                            max_values[detail_start:detail_stop],
                        )
                    )
                },
                "measurement_status": {
                    name: (
                        "measured"
                        if bool(
                            max_values[
                                detail_start
                                + len(_DETAIL_TIMING_NAMES)
                                + index
                            ]
                        )
                        else "not_called"
                    )
                    for index, name in enumerate(_DETAIL_TIMING_NAMES)
                },
                "semantics": (
                    "inclusive local timing regions reduced with the same single "
                    "MPI.MAX buffer; component maxima are not summed as wall; "
                    "q_a4_residual_refinement_seconds includes extraction, "
                    "allocation, physical action, norm, and audit work, and "
                    "q_physical_action_matrix_mult_seconds is its nested matrix "
                    "mult interval; balance_jh_inject_allocate_seconds is only "
                    "the JH injection/Vec allocation interval"
                ),
            }
        return result

    def _count_snapshot(self) -> dict[str, int | None]:
        if self._operator is None:
            return dict(self._cumulative_counts)
        snapshot = {
            "side_A": _context_apply_count(self.operator),
            "pc": int(self._pc_apply_count),
            "Q": int(self._q_count),
            "p4_backsolve": int(self._p4_backsolve_count),
            "p4_refinement": int(self._p4_refinement_count),
            "H6": int(self._h6_count),
            "A6": int(self._a6_count),
            "J": int(self._j_count),
            "JH": int(self._jh_count),
            "P": int(self._p_count),
            "PH_audit": int(self._ph_audit_count),
            "PH_total": int(self._ph_total_count),
            "checkpoint": int(self._checkpoint_count),
        }
        if self._reuse_leading_ph_dual:
            snapshot["PH_audit_leading_reused"] = int(
                self._ph_leading_reused_count
            )
            snapshot["PH_audit_logical"] = int(
                self._ph_audit_count + self._ph_leading_reused_count
            )
        self._cumulative_counts = dict(snapshot)
        return snapshot

    @staticmethod
    def _count_delta(
        before: dict[str, int | None],
        after: dict[str, int | None],
    ) -> dict[str, int | None]:
        result: dict[str, int | None] = {}
        for name, value in after.items():
            old = before[name]
            result[name] = None if value is None or old is None else value - old
        return result

    def complete_staged_p4_numeric(self) -> Mapping[str, Any]:
        """Complete the registered W0.7 P4 factor on this side's same handle."""

        if self._destroyed or self._p4_factor is None:
            raise RuntimeError("BAL_H side inverse is destroyed")
        if self._apply_in_progress:
            raise RuntimeError("cannot complete P4 numeric during side apply")
        if self._p4_inverse_backend != "cell_condensed":
            raise RuntimeError("staged P4 numeric requires the cell-condensed backend")
        if not callable(getattr(self._p4_factor, "complete_numeric", None)):
            raise TypeError("BAL_H P4 factor lacks staged numeric completion")
        return self._p4_factor.complete_numeric()

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self._apply_in_progress:
            raise RuntimeError("BAL_H side inverse apply is already in progress")
        if self._p4_factor is not None and self._p4_factor.diagnostics.get(
            "factor_state"
        ) == "symbolic_live_pending_numeric":
            raise RuntimeError(
                "BAL_H side P4 factor is symbolic only; complete staged numeric before apply"
            )
        self._apply_in_progress = True
        self._active_ksp_iteration = None
        try:
            self._apply_impl(source, target)
        finally:
            self._apply_in_progress = False
            self._active_ksp_iteration = None

    def _apply_impl(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        """Apply the side inverse into ``target`` and record one RHS audit."""

        if (
            self._destroyed
            or self._operator is None
            or self._ksp is None
            or self._owner_transfer is None
        ):
            raise RuntimeError("BAL_H side inverse has been destroyed")
        if _same_handle(source, target):
            raise ValueError("BAL_H side inverse does not allow source/target aliasing")
        if source.getSize() != self._operator.getSize()[1]:
            raise ValueError("BAL_H side inverse source has the wrong size")
        if target.getSize() != self._operator.getSize()[0]:
            raise ValueError("BAL_H side inverse target has the wrong size")
        target.set(0.0)
        self._apply_count += 1
        self._active_apply_pc_count = 0
        self._active_pc_index = None
        self._active_pc_q_count = 0
        self._active_ksp_iteration = None
        self._active_rhs_norm = None
        capture_restart32 = self._side_restart64_capture_is_armed()
        self._active_p4_call_records = (
            []
            if (
                self._diagnostic_callback is not None
                or self._p4_refinement_target_tolerance is not None
                or capture_restart32
            )
            else None
        )
        self._active_true_residual_samples = (
            [] if self._diagnostic_callback is not None else None
        )
        self._active_restart32_samples = [] if capture_restart32 else None
        if self._iteration_history is not None:
            self._iteration_history.clear()
        before = self._count_snapshot()
        started = perf_counter()
        self._rhs_operation_seconds = {
            name: 0.0 for name in ("Q", "H6", "A6")
        }
        self._rhs_detail_seconds = {
            name: 0.0 for name in _DETAIL_TIMING_NAMES
        }
        self._rhs_detail_seen = {
            name: False for name in _DETAIL_TIMING_NAMES
        }
        self._last_coupling_failure = None
        self._pending_pc_exception = None
        self._ksp.getPC().setFailedReason(PETSc.PC.FailedReason.NOERROR)
        rhs_norm: Any = "not_measured"
        reason: int | None = None
        iterations = 0
        solve_started = False
        ksp_positive = False
        zero_rhs = False
        operation_timing: dict[str, Any] = {"status": "not_measured"}
        residual_audit: dict[str, Any] = {
            "rhs_norm": "not_measured",
            "solution_norm": "not_measured",
            "residual_norm": "not_measured",
            "relative_residual": "not_measured",
        }
        ksp_contract: dict[str, Any] | None = None
        execution_variant = self._active_variant
        if execution_variant is None:
            execution_variant = self._owner_transfer.execution_variant
        try:
            if self._record_iteration_history:
                try:
                    ksp_contract = self._ksp_contract_audit()
                except Exception as contract_error:  # noqa: BLE001 - turn getter failure into collective audit
                    ksp_contract = {
                        "source": "live_petsc_getters_before_opt_in_apply",
                        "pass": False,
                        "error": {
                            "type": type(contract_error).__name__,
                            "message": str(contract_error),
                        },
                    }
                collective_contract_pass = bool(
                    self._comm.allreduce(
                        ksp_contract.get("pass") is True,
                        op=MPI.LAND,
                    )
                )
                if not collective_contract_pass:
                    ksp_contract["collective_pass"] = False
                    ksp_contract["rank_summaries"] = self._comm.allgather(
                        {
                            "rank": int(self._comm.Get_rank()),
                            "contract": ksp_contract,
                        }
                    )
                    raise RuntimeError(
                        "BAL_H live KSP contract does not match on every rank"
                    )
                ksp_contract["collective_pass"] = True
            rhs_norm = float(source.norm())
            if not np.isfinite(rhs_norm):
                raise RuntimeError("BAL_H side RHS norm is non-finite")
            self._active_rhs_source = source
            self._active_rhs_norm = rhs_norm
            residual_audit["rhs_norm"] = rhs_norm
            zero_rhs = rhs_norm == 0.0
            if self._active_restart32_samples is not None:
                local_finite = bool(
                    np.isfinite(source.getArray(readonly=True)).all()
                )
                finite = bool(self._comm.allreduce(local_finite, op=MPI.LAND))
                self._active_restart32_samples.append(
                    {
                        "iteration": 0,
                        "reported_residual": None,
                        "original_D_true_residual_norm": rhs_norm,
                        "original_D_rhs_norm": rhs_norm,
                        "original_D_true_relative_residual": (
                            1.0 if rhs_norm > 0.0 else 0.0
                        ),
                        "finite": finite,
                        "scope": "zero_initial_guess_exact_rhs_residual",
                    }
                )
            if not zero_rhs:
                solve_started = True
                self._ksp.solve(source, target)
                pending_pc_exception = self._pending_pc_exception
                if pending_pc_exception is not None:
                    raise pending_pc_exception
                reason = int(self._ksp.getConvergedReason())
                iterations = int(self._ksp.getIterationNumber())
                if self._diagnostic_callback is not None:
                    self._emit_ksp_true_residual_sample(
                        self._ksp,
                        iteration=iterations,
                        sample_label="final_iteration",
                        final_solution=target,
                        reported_residual=(
                            float(self._iteration_history[-1]["reported_residual"])
                            if self._iteration_history
                            and isinstance(
                                self._iteration_history[-1].get(
                                    "reported_residual"
                                ),
                                (int, float),
                            )
                            else None
                        ),
                    )
                status, ksp_positive = _classify_ksp_result(
                    reason,
                    iterations,
                    self._max_it,
                )
                if (
                    self._active_restart32_samples is not None
                    and not any(
                        row.get("iteration") == iterations
                        for row in self._active_restart32_samples
                    )
                ):
                    self._active_restart32_samples.append(
                        self._restart32_true_residual_sample(
                            self._ksp,
                            iteration=iterations,
                            reported_residual=None,
                            final_solution=target,
                        )
                    )
            else:
                status = "ZERO_RHS_EXACT"

            residual_audit = self._explicit_residual(source, target)
            true_target_reached = bool(
                residual_audit["relative_residual"] <= self._rtol
                if not zero_rhs
                else residual_audit["residual_norm"] == 0.0
            )
            local_elapsed = float(perf_counter() - started)
            elapsed = float(self._comm.allreduce(local_elapsed, op=MPI.MAX))
            operation_timing = self._rhs_operation_timing(local_elapsed, reduce=True)
            after = self._count_snapshot()
            record = {
                "rank": int(self._comm.Get_rank()),
                "status": status,
                "reason": reason,
                "iterations": int(iterations),
                "ksp_positive": bool(ksp_positive),
                "explicit_true_target_reached": true_target_reached,
                "ksp_rtol": self._rtol,
                "ksp_max_it": self._max_it,
                "elapsed_seconds": elapsed,
                "elapsed_local_seconds": float(local_elapsed),
                "execution_variant": execution_variant,
                "operation_seconds": operation_timing,
                "counts": {
                    "delta": self._count_delta(before, after),
                    "cumulative": after,
                },
                **residual_audit,
                **(
                    {"ksp_contract": ksp_contract}
                    if ksp_contract is not None
                    else {}
                ),
                **(
                    {"iteration_history": list(self._iteration_history)}
                    if self._iteration_history is not None
                    else {}
                ),
                **(
                    {
                        "p4_call_history": list(self._active_p4_call_records),
                        "p4_call_summary": self._p4_call_summary(
                            self._active_p4_call_records
                        ),
                    }
                    if self._active_p4_call_records is not None
                    else {}
                ),
                **(
                    {
                        "true_residual_samples": list(
                            self._active_true_residual_samples
                        )
                    }
                    if self._active_true_residual_samples is not None
                    else {}
                ),
            }
            restart32_capture = self._consider_restart32_candidate(
                source,
                reason=reason,
                iterations=iterations,
                residual_audit=residual_audit,
                samples=tuple(self._active_restart32_samples or ()),
                solve_record=record,
            )
            if restart32_capture is not None:
                record["side_restart64_capture"] = dict(restart32_capture)
        except BaseException as exc:
            if solve_started and self._ksp is not None:
                try:
                    reason = int(self._ksp.getConvergedReason())
                    iterations = int(self._ksp.getIterationNumber())
                except (AttributeError, PETSc.Error):
                    pass
            self._total_iterations += int(iterations)
            elapsed = float(perf_counter() - started)
            self._total_apply_seconds += elapsed
            operation_timing = self._rhs_operation_timing(elapsed, reduce=False)
            after = self._count_snapshot()
            record = {
                "rank": int(self._comm.Get_rank()),
                "status": "FAILED",
                "reason": reason,
                "iterations": int(iterations),
                "ksp_positive": bool(ksp_positive),
                "explicit_true_target_reached": "not_measured",
                "ksp_rtol": self._rtol,
                "ksp_max_it": self._max_it,
                "elapsed_seconds": elapsed,
                "execution_variant": execution_variant,
                "operation_seconds": operation_timing,
                "exception_type": type(exc).__name__,
                "exception": str(exc),
                "counts": {
                    "delta": self._count_delta(before, after),
                    "cumulative": after,
                },
                **residual_audit,
                **(
                    {"ksp_contract": ksp_contract}
                    if ksp_contract is not None
                    else {}
                ),
                **(
                    {"iteration_history": list(self._iteration_history)}
                    if self._iteration_history is not None
                    else {}
                ),
                **(
                    {
                        "p4_call_history": list(self._active_p4_call_records),
                        "p4_call_summary": self._p4_call_summary(
                            self._active_p4_call_records
                        ),
                    }
                    if self._active_p4_call_records is not None
                    else {}
                ),
                **(
                    {
                        "true_residual_samples": list(
                            self._active_true_residual_samples
                        )
                    }
                    if self._active_true_residual_samples is not None
                    else {}
                ),
            }
            if self._last_coupling_failure is not None:
                record.update(dict(self._last_coupling_failure))
            elif isinstance(exc, P4PhysicalResidualGateError):
                record.update(
                    {
                        "failure_classification": "P4_PHYSICAL_RESIDUAL_GATE",
                        "p4_solve_audit": dict(exc.audit),
                    }
                )
            elif isinstance(exc, BalancedConstraintRejected):
                record.update(
                    {
                        "failure_classification": "BALANCED_CONSTRAINT_REJECTED",
                        "balance_audit": dict(exc.facts),
                    }
                )
            self._last_apply = dict(record)
            if self._audit_callback is not None:
                self._audit_callback(dict(record))
            raise
        finally:
            self._pending_pc_exception = None
            self._active_pc_index = None
            self._active_pc_q_count = 0
            self._active_ksp_iteration = None
            self._active_p4_call_records = None
            self._active_true_residual_samples = None
            self._active_restart32_samples = None
            self._active_rhs_source = None
            self._active_rhs_norm = None

        self._total_iterations += int(iterations)
        self._total_apply_seconds += elapsed
        self._last_apply = dict(record)
        if self._audit_callback is not None:
            self._audit_callback(dict(record))

    def apply_many(self, sources: PETSc.Mat, targets: PETSc.Mat) -> None:
        """Apply columns one at a time with the fixed 32-column bound."""

        if self._destroyed or self._operator is None:
            raise RuntimeError("BAL_H side inverse has been destroyed")
        if not isinstance(sources, PETSc.Mat) or not isinstance(targets, PETSc.Mat):
            raise TypeError("BAL_H side inverse batches require PETSc dense matrices")
        if _same_handle(sources, targets):
            raise ValueError("BAL_H side inverse does not allow batch aliasing")
        if not _dense_types(sources) or not _dense_types(targets):
            raise TypeError("BAL_H side inverse batches require dense matrices")
        source_size = tuple(map(int, sources.getSize()))
        target_size = tuple(map(int, targets.getSize()))
        width = source_size[1]
        if source_size[0] != self._operator.getSize()[1]:
            raise ValueError("BAL_H source batch has the wrong row count")
        if target_size != (self._operator.getSize()[0], width):
            raise ValueError("BAL_H target batch has the wrong shape")
        if width <= 0 or width > _MAX_DENSE_COLUMNS:
            raise ValueError("BAL_H batches require one to 32 columns")
        ownership = tuple(map(int, self._operator.getOwnershipRange()))
        if tuple(map(int, sources.getOwnershipRange())) != ownership:
            raise ValueError("BAL_H source batch ownership does not match side A")
        if tuple(map(int, targets.getOwnershipRange())) != ownership:
            raise ValueError("BAL_H target batch ownership does not match side A")

        source = self._operator.createVecRight()
        target = self._operator.createVecLeft()
        try:
            source_array = sources.getDenseArray()
            target_array = targets.getDenseArray()
            for column in range(width):
                source.getArray()[:] = source_array[:, column]
                source.assemble()
                self.apply(source, target)
                target_array[:, column] = target.getArray(readonly=True)
            targets.assemble()
        finally:
            source.destroy()
            target.destroy()

    @property
    def diagnostics(self) -> dict[str, Any]:
        if self._p4_factor is None:
            p4_diagnostics = dict(
                (self._pre_destroy_component_diagnostics or {}).get(
                    "p4_factor", {}
                )
            )
        else:
            p4_diagnostics = dict(self._p4_factor.diagnostics)
        p4_live = int(self._p4_factor is not None)
        nested_ksp_live = int(self._ksp is not None)
        return {
            "schema": "task041.h1e.side_balanced_inverse.v1",
            "operator_identity": self.operator_identity,
            "research_only": True,
            "ksp_type": "fgmres",
            "pc_side": "right",
            "restart": int(self._gmres_restart),
            "norm_type": "unpreconditioned",
            "zero_initial_guess": True,
            "ksp_rtol": self._rtol,
            "ksp_max_it": self._max_it,
            "detailed_timing": self._detailed_timing,
            "iteration_history_enabled": self._record_iteration_history,
            "preconditioner": "J BAL_H JH",
            "p4_inverse_backend": self._p4_inverse_backend,
            **(
                {"physical_action_backend": self._physical_action_backend}
                if self._physical_action_backend is not None
                else {}
            ),
            **(
                {
                    "p4_refinement_target_tolerance": (
                        self._p4_refinement_target_tolerance
                    )
                }
                if self._p4_refinement_target_tolerance is not None
                else {}
            ),
            "apply_count": int(self._apply_count),
            "total_iterations": int(self._total_iterations),
            "total_apply_seconds": float(self._total_apply_seconds),
            "restart_transition_ksp_setup_seconds": float(
                self._restart_transition_ksp_setup_seconds
            ),
            "total_side_wall_seconds_including_restart_transition_setup": float(
                self._total_apply_seconds
                + self._restart_transition_ksp_setup_seconds
            ),
            "direct_factor_count": p4_live,
            "local_direct_factor_count": p4_live,
            "local_direct_factor_count_owned": p4_live,
            "p4_factor_count": p4_live,
            "p4_factor_live": p4_live,
            "p4_factor_created_count": int(self._p4_factor_created_count),
            "p4_factor_destroy_count": int(self._p4_factor_destroy_count),
            "p6_factor_count": 0,
            "global_direct_factor_count": 0,
            "global_hybrid_direct_factor_count": 0,
            "factor_free_qualification": False,
            "exact_side_qualification": False,
            "nested_iterative_ksp_count": int(nested_ksp_live),
            "nested_ksp_created_count": int(self._nested_ksp_created_count),
            "nested_ksp_destroy_count": int(self._nested_ksp_destroy_count),
            "nested_ksp_current_live": bool(nested_ksp_live),
            "approximate_nonlinear_inverse": True,
            "counts": self._count_snapshot(),
            "last_apply": dict(self._last_apply),
            "side_restart64_trial": (
                None
                if self._side_restart64_trial_state is None
                else {
                    key: value
                    for key, value in self._side_restart64_trial_state.items()
                    if not key.startswith("_")
                }
            ),
            "side_restart64_trial_record": (
                None
                if self._side_restart64_trial_record is None
                else dict(self._side_restart64_trial_record)
            ),
            **(
                {
                    "independent_p4_call_history": list(
                        self._direct_p4_call_records
                    ),
                    "independent_p4_call_summary": self._p4_call_summary(
                        self._direct_p4_call_records
                    ),
                }
                if (
                    self._diagnostic_callback is not None
                    or self._p4_refinement_target_tolerance is not None
                )
                else {}
            ),
            "p4_factor": p4_diagnostics,
            "p4_factor_state": p4_diagnostics.get("factor_state"),
            "p4_numeric_factor_ready": p4_diagnostics.get(
                "numeric_factor_ready"
            ),
            "destroyed": bool(self._destroyed),
            "ksp_destroyed": not bool(nested_ksp_live),
        }

    def primal_route_plan_snapshot(self) -> dict[str, Any]:
        """Report only this rank's persistent route-index payload, if live."""

        if self._destroyed or self._owner_transfer is None:
            return {
                "status": "destroyed",
                "enabled": self._reuse_primal_route_plan_enabled,
                "captured": None,
                "rank": int(self._comm.rank),
                "communicator_size": int(self._comm.size),
                "N_r": None,
                "M_r": None,
                "array_nbytes_local": None,
                "persistent_index_payload_bytes_local": None,
                "payload_formula_bytes_local": None,
                "payload_formula": "16*N_r + 20*M_r + 16*P",
            }
        return _owner_transfer_primal_route_plan_snapshot(self._owner_transfer)

    def destroy(self) -> None:
        if self._destroyed:
            return
        if self._side_restart64_trial_running:
            raise RuntimeError("cannot destroy a side inverse during its restart64 trial")
        self._destroyed = True
        candidate_rhs, self._side_restart64_candidate_rhs = (
            self._side_restart64_candidate_rhs,
            None,
        )
        if candidate_rhs is not None:
            candidate_rhs.destroy()
        ksp = self._ksp
        self._ksp = None
        try:
            if ksp is not None:
                ksp.destroy()
                self._nested_ksp_destroy_count += 1
        finally:
            self._pending_pc_exception = None
            if self._pc_context is not None:
                self._pc_context.owner = None
            self._pc_context = None
            self._coupling = None
            p4_component = self._p4_factor
            owned = (
                ("h6", self._h6),
                ("owner_transfer", self._owner_transfer),
                ("p4_factor", p4_component),
                ("full_action", self._full_action),
            )
            p4_diagnostics: dict[str, Any] | None = None
            for _name, component in owned:
                if component is not None:
                    component.destroy()
                if _name == "p4_factor" and component is not None:
                    p4_diagnostics = dict(component.diagnostics)
            self._p4_factor_destroy_count = 1
            if p4_diagnostics is None:
                p4_diagnostics = {}
            p4_diagnostics["factor_destroy_count"] = 1
            p4_diagnostics["destroyed"] = True
            self._pre_destroy_component_diagnostics = {
                "p4_factor": p4_diagnostics,
            }
            self._h6 = None
            self._owner_transfer = None
            self._p4_factor = None
            self._full_action = None
            self._operator = None
            self._condensed = None
            self._side_system = None


def _validate_ksp_pair(max_it: int, rtol: float) -> None:
    pair = (int(max_it), float(rtol))
    if pair not in _ALLOWED_KSP:
        raise ValueError(
            "BAL_H side inverse accepts only (max_it, rtol)=(128,1e-2) "
            "or (256,1e-4)"
        )


def build_side_balanced_inverse(
    side_system: HybridLocalDtnActionSystem,
    *,
    max_it: int = 128,
    rtol: float = 1.0e-2,
    checkpoint_callback: Callable[[], None] | None = None,
    audit_callback: Callable[[dict[str, Any]], None] | None = None,
    detailed_timing: bool = False,
    record_iteration_history: bool = False,
    diagnostic_callback: Callable[[Mapping[str, Any]], None] | None = None,
    lifecycle_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
    performance_profile: str | None = None,
    p4_inverse_backend: str = "full",
    factor_stage_factory: Callable[..., Any] | None = None,
    defer_p4_numeric: bool = False,
    support_policy: str = "legacy",
    volume_action_context_factory: Callable[..., Any] | None = None,
    reuse_primal_route_plan: bool = False,
    reuse_leading_ph_dual: bool = False,
    compact_orientation: bool = False,
    side_restart64_trial_state: dict[str, Any] | None = None,
    side_restart64_memory_gate: Callable[[Mapping[str, Any]], Mapping[str, Any]]
    | None = None,
) -> SideBalancedInverse:
    """Build one side adapter and release all partial owned state on failure."""

    if not isinstance(reuse_primal_route_plan, bool):
        raise TypeError("reuse_primal_route_plan must be a boolean")
    if not isinstance(reuse_leading_ph_dual, bool):
        raise TypeError("reuse_leading_ph_dual must be a boolean")
    if type(defer_p4_numeric) is not bool:
        raise TypeError("defer_p4_numeric must be an exact bool")
    if not isinstance(compact_orientation, bool):
        raise TypeError("compact_orientation must be a boolean")
    if (side_restart64_trial_state is None) != (
        side_restart64_memory_gate is None
    ):
        raise ValueError(
            "V12 side restart state and live memory gate must be supplied together"
        )
    if side_restart64_trial_state is not None and (
        not isinstance(side_restart64_trial_state, dict)
        or side_restart64_trial_state.get("schema")
        != "task041.v12.side_restart64_trial_state.v1"
        or side_restart64_trial_state.get("policy_id")
        != "task041_v12_bounded_inexact_modal_once_backup"
        or not callable(side_restart64_memory_gate)
        or max_it != 128
        or float(rtol) != 1.0e-2
        or side_system.side not in {"bottom", "top"}
        or p4_inverse_backend != "cell_condensed"
        or factor_stage_factory is None
        or defer_p4_numeric is not True
    ):
        raise ValueError(
            "V12 side restart is limited to staged deferred cell-condensed W0.7 sides"
        )
    if reuse_leading_ph_dual and diagnostic_callback is not None:
        raise ValueError(
            "leading PH reuse is incompatible with mutable vector diagnostics"
        )
    _validate_ksp_pair(max_it, rtol)
    if p4_inverse_backend not in _P4_INVERSE_BACKENDS:
        raise ValueError(
            "p4_inverse_backend must be 'full' or 'cell_condensed'"
        )
    if factor_stage_factory is not None and (
        not callable(factor_stage_factory)
        or p4_inverse_backend != "cell_condensed"
        or side_system.side not in {"bottom", "top"}
    ):
        raise ValueError(
            "staged factors are limited to registered cell-condensed BAL_H sides"
        )
    if defer_p4_numeric and (
        factor_stage_factory is None
        or p4_inverse_backend != "cell_condensed"
        or side_system.side not in {"bottom", "top"}
    ):
        raise ValueError(
            "pending P4 numeric is limited to explicitly staged cell-condensed bottom/top sides"
        )
    if compact_orientation and (
        factor_stage_factory is None
        or not defer_p4_numeric
        or p4_inverse_backend != "cell_condensed"
        or side_system.side not in {"bottom", "top"}
        or lifecycle_callback is None
    ):
        raise ValueError(
            "compact orientation is limited to staged deferred cell-condensed "
            "BAL_H sides with a setup lifecycle inventory"
        )
    if performance_profile not in {None, _TASK041_SCHUR_SPEED_V2_PROFILE}:
        raise ValueError("unsupported Task041 performance profile")
    if not isinstance(side_system, HybridLocalDtnActionSystem):
        raise TypeError("BAL_H side inverse requires a HybridLocalDtnActionSystem")
    if volume_action_context_factory is not None:
        from .physical_balanced_fused_volume import (
            build_task041_fused_physical_volume_context,
        )

        if volume_action_context_factory is not build_task041_fused_physical_volume_context:
            raise ValueError("unsupported Task041 physical volume context factory")
    full_action = None
    p4_factor = None
    owner_transfer = None
    h6 = None
    inverse = None

    def emit(event: str, detail: Mapping[str, Any] | None = None) -> None:
        if lifecycle_callback is not None:
            lifecycle_callback(
                event,
                {
                    "scope": "side_local",
                    **({} if detail is None else dict(detail)),
                },
            )

    nested_lifecycle_callback = (
        emit if lifecycle_callback is not None else None
    )

    try:
        emit("full_action_begin")
        if volume_action_context_factory is None:
            full_action = build_fullspace_physical_dtn_action(side_system)
            physical_action_backend = "MpcFormActionContext"
        else:
            full_action = build_fullspace_physical_dtn_action(
                side_system,
                volume_action_context_factory=volume_action_context_factory,
            )
            action_context = getattr(
                getattr(full_action, "action", None), "context", None
            )
            action_audit = getattr(action_context, "audit", None)
            local_kernel = (
                action_audit.get("local_kernel")
                if isinstance(action_audit, Mapping)
                else None
            )
            if (
                not isinstance(local_kernel, Mapping)
                or local_kernel.get("backend")
                != "task041_opt_in_sum_factorized_physical_volume"
            ):
                raise RuntimeError(
                    "the requested Task041 physical volume kernel was not built"
                )
            physical_action_backend = str(local_kernel["backend"])
        if lifecycle_callback is None:
            emit("full_action_ready")
        else:
            object_inventory = _full_action_inventory(
                full_action,
                owner="side.full_action",
            )
            condensed = getattr(
                getattr(side_system, "static_condensation", None),
                "condensed",
                None,
            )
            condensed_build_audit = getattr(
                condensed,
                "build_audit",
                None,
            )
            if isinstance(condensed_build_audit, Mapping):
                object_inventory[
                    "p6_assembly_time_condensation_build_audit"
                ] = dict(condensed_build_audit)
                object_inventory[
                    "p6_assembly_time_condensation_payload_semantics"
                ] = "array payload only; not RSS"
            emit(
                "full_action_ready",
                {
                    "object_inventory": object_inventory,
                },
            )
        if p4_inverse_backend == "cell_condensed":
            p4_factor = build_p4_condensed_exact_factor(
                side_system,
                lifecycle_callback=nested_lifecycle_callback,
                stage_factory=factor_stage_factory,
                stage_identity=(
                    f"task041.w0p7.p4.{side_system.side}"
                    if factor_stage_factory is not None
                    else None
                ),
                defer_numeric=defer_p4_numeric,
            )
        else:
            p4_factor = build_p4_exact_factor(
                side_system,
                lifecycle_callback=nested_lifecycle_callback,
            )
        emit("transfer_begin")
        owner_transfer = build_same_mesh_hcurl_owner_transfer(
            full_action.V,
            full_action.floquet_data,
            p4_factor.physical_action.V,
            p4_factor.physical_action.floquet_data,
            optimization_profile=performance_profile,
            support_policy=support_policy,
            reuse_primal_route_plan=reuse_primal_route_plan,
            compact_orientation=compact_orientation,
        )
        compact_orientation_inventory = None
        if compact_orientation:
            transfer_comm = owner_transfer.comm
            local_storage_record = _compact_owner_transfer_storage_local_record(
                owner_transfer
            )
            gathered_storage_records = transfer_comm.allgather(
                local_storage_record
            )
            compact_orientation_inventory = (
                _aggregate_compact_owner_transfer_storage_records(
                    gathered_storage_records,
                    communicator_size=int(transfer_comm.size),
                )
            )
        if lifecycle_callback is None:
            emit("transfer_ready")
        else:
            transfer_inventory = (
                _owner_transfer_inventory(
                    owner_transfer,
                    compact_orientation_inventory=(
                        compact_orientation_inventory
                    ),
                )
                if compact_orientation
                else _owner_transfer_inventory(owner_transfer)
            )
            emit(
                "transfer_ready",
                {"object_inventory": transfer_inventory},
            )
        h6 = build_balanced_h6(
            side_system,
            lifecycle_callback=nested_lifecycle_callback,
        )
        emit("adapter_ksp_begin")
        inverse = SideBalancedInverse(
            side_system,
            full_action,
            p4_factor,
            owner_transfer,
            h6,
            max_it=max_it,
            rtol=rtol,
            checkpoint_callback=checkpoint_callback,
            audit_callback=audit_callback,
            detailed_timing=detailed_timing,
            record_iteration_history=record_iteration_history,
            diagnostic_callback=diagnostic_callback,
            p4_inverse_backend=p4_inverse_backend,
            physical_action_backend=physical_action_backend,
            reuse_leading_ph_dual=reuse_leading_ph_dual,
            side_restart64_trial_state=side_restart64_trial_state,
            side_restart64_memory_gate=side_restart64_memory_gate,
        )
        full_action = None
        p4_factor = None
        owner_transfer = None
        h6 = None
        if lifecycle_callback is None:
            emit("adapter_ksp_ready")
        else:
            emit(
                "adapter_ksp_ready",
                {"object_inventory": _side_adapter_inventory(inverse)},
            )
        return inverse
    except BaseException:
        if inverse is not None:
            inverse.destroy()
        if h6 is not None:
            h6.destroy()
        if owner_transfer is not None:
            owner_transfer.destroy()
        if p4_factor is not None:
            p4_factor.destroy()
        if full_action is not None:
            full_action.destroy()
        raise
