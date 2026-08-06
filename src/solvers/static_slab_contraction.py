"""Small research diagnostic for one global preconditioner application."""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from .physical_slab_two_level import (
    DistributedPhysicalSlabSmoother,
    OwnerLocalSlabPlan,
)
from .static_factor_free_slab_pc import FactorFreeLocalSlabKrylovPc

__all__ = (
    "measure_one_apply_contraction",
    "measure_owner_local_slab_contractions",
)


def measure_one_apply_contraction(
    operator: PETSc.Mat,
    residual: PETSc.Vec,
    apply_correction: Callable[[PETSc.Vec, PETSc.Vec], None],
) -> dict[str, float]:
    """Measure ``rho=||r-A M^-1 r||/||r||`` for one synchronous apply.

    ``residual`` is borrowed and remains unchanged.  The correction and post-
    action vectors are temporary objects owned by this function.
    """

    input_norm = float(residual.norm())
    if input_norm == 0.0:
        raise ValueError("one-apply contraction requires a nonzero residual")

    correction = operator.createVecRight()
    post = operator.createVecLeft()
    try:
        apply_correction(residual, correction)
        operator.mult(correction, post)
        post.scale(PETSc.ScalarType(-1.0))
        post.axpy(PETSc.ScalarType(1.0), residual)
        post_norm = float(post.norm())
        return {
            "input_norm": input_norm,
            "post_norm": post_norm,
            "rho": post_norm / input_norm,
            "correction_norm": float(correction.norm()),
        }
    finally:
        correction.destroy()
        post.destroy()


def measure_owner_local_slab_contractions(
    global_operator: PETSc.Mat,
    shifted_local_operator: PETSc.Mat,
    residual: PETSc.Vec,
    plan: OwnerLocalSlabPlan,
    smoother: DistributedPhysicalSlabSmoother,
    b4: FactorFreeLocalSlabKrylovPc,
    *,
    fixed_two_step_apply: Callable[[PETSc.Vec, PETSc.Vec], None] | None = None,
    m3a_two_level_apply: Callable[[PETSc.Vec, PETSc.Vec], None] | None = None,
) -> dict[str, Any]:
    """Collect raw per-slab and global contraction diagnostics.

    ``global_operator`` is the exact condensed active-trace operator ``A_t``
    used for every global ratio.  ``shifted_local_operator`` is the local
    Schur action plus frozen diagonal shift used for the unweighted ILU local
    ratio; ``b4.restricted_action`` supplies that same local action for B4.
    Only the global B4 application uses the partition weights already owned by
    ``b4``.  The two optional actions are explicit fixture/core inputs: the
    latter must be the complete M3a two-step + wave-coarse + post-smooth
    action, not coarse-only.
    """

    comm = plan.comm
    num_slabs = len(plan.slab_owners)
    owner_row_packets = comm.allgather(
        tuple(
            np.asarray(rows, dtype=PETSc.IntType).copy()
            for rows in plan.owner_rows
        )
    )
    global_slab_rows = tuple(
        next(packet[slab] for packet in owner_row_packets if packet[slab].size)
        for slab in range(num_slabs)
    )
    residual_start, residual_end = map(int, residual.getOwnershipRange())
    residual_values = np.asarray(
        residual.getArray(readonly=True), dtype=PETSc.ScalarType
    )
    embedded_correction = shifted_local_operator.createVecRight()
    local_action = shifted_local_operator.createVecLeft()
    local_metrics: list[dict[str, float | int | None]] = []
    try:
        for slab, owner in enumerate(plan.slab_owners):
            rows = global_slab_rows[slab]
            local_positions = rows[
                (rows >= residual_start) & (rows < residual_end)
            ] - residual_start
            local_residual = residual_values[local_positions]
            local_residual_sq = float(np.vdot(local_residual, local_residual).real)
            residual_norm = float(
                np.sqrt(comm.allreduce(local_residual_sq, op=MPI.SUM))
            )

            ilu_rhs, ilu_correction = smoother._diagnostic_owner_local_ilu(
                residual, slab
            )
            embedded_correction.set(0.0)
            if comm.rank == int(owner):
                rows_for_owner = np.asarray(rows, dtype=PETSc.IntType)
                embedded_correction.setValues(rows_for_owner, ilu_correction)
            embedded_correction.assemble()
            shifted_local_operator.mult(embedded_correction, local_action)
            local_action_values = np.asarray(
                local_action.getArray(readonly=True), dtype=PETSc.ScalarType
            )
            local_post = residual_values[local_positions] - local_action_values[
                local_positions
            ]
            local_post_sq = float(np.vdot(local_post, local_post).real)
            ilu_post_norm = float(
                np.sqrt(comm.allreduce(local_post_sq, op=MPI.SUM))
            )

            b4_rhs = (
                ilu_rhs
                if comm.rank == int(owner)
                else np.empty(0, dtype=PETSc.ScalarType)
            )
            b4_correction, _happy_breakdown = b4._fixed_step_gmres(slab, b4_rhs)
            b4_local_action = b4.restricted_action(
                slab,
                b4_correction
                if comm.rank == int(owner)
                else np.empty(0, dtype=PETSc.ScalarType),
            )
            b4_local_post = (
                b4_rhs - b4_local_action
                if comm.rank == int(owner)
                else np.empty(0, dtype=PETSc.ScalarType)
            )
            b4_post_sq = float(np.vdot(b4_local_post, b4_local_post).real)
            b4_post_norm = float(
                np.sqrt(comm.allreduce(b4_post_sq, op=MPI.SUM))
            )
            ilu_rho = (
                None
                if residual_norm == 0.0
                else ilu_post_norm / residual_norm
            )
            b4_rho = (
                None
                if residual_norm == 0.0
                else b4_post_norm / residual_norm
            )
            local_metrics.append(
                {
                    "slab": int(slab),
                    "local_residual_norm": residual_norm,
                    "current_trace_ilu_unweighted_local_one_solve_rho": ilu_rho,
                    "b4_fixed_gmres4_unweighted_local_one_solve_rho": b4_rho,
                }
            )
    finally:
        local_action.destroy()
        embedded_correction.destroy()

    current_ilu = measure_one_apply_contraction(
        global_operator,
        residual,
        smoother._diagnostic_one_level_apply,
    )
    b4_global = measure_one_apply_contraction(
        global_operator,
        residual,
        b4.apply,
    )
    ablation: list[dict[str, float | int]] = []
    for excluded_subdomain in range(num_slabs):
        excluded = measure_one_apply_contraction(
            global_operator,
            residual,
            lambda source, target, excluded_subdomain=excluded_subdomain: (
                smoother._diagnostic_one_level_apply(
                    source,
                    target,
                    excluded_subdomain=excluded_subdomain,
                )
            ),
        )
        ablation.append(
            {
                "excluded_subdomain": int(excluded_subdomain),
                "rho": excluded["rho"],
                "ablation_damage": excluded["rho"] - current_ilu["rho"],
            }
        )

    def optional_global_apply(
        apply_correction: Callable[[PETSc.Vec, PETSc.Vec], None] | None,
    ) -> dict[str, float] | None:
        if apply_correction is None:
            return None
        return measure_one_apply_contraction(
            global_operator,
            residual,
            apply_correction,
        )

    return {
        "local_slab_contractions": local_metrics,
        "global_current_trace_ilu_one_additive_apply": current_ilu,
        "global_b4_partition_weighted_one_apply": b4_global,
        "global_current_trace_ilu_ablation": ablation,
        "global_fixed_two_step_smoother": optional_global_apply(
            fixed_two_step_apply
        ),
        "global_m3a_two_step_wave_coarse_post_smooth": optional_global_apply(
            m3a_two_level_apply
        ),
    }
