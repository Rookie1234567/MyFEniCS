"""Task035d adapter from p6 Stage-4 forms to a true variable-p trace system."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import os
from time import perf_counter
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc
from scipy import sparse
from scipy.sparse import csgraph, linalg as sparse_linalg

from src.adaptivity.variable_p_degree_plan import (
    VariablePCellDegreePlan,
    load_variable_p_cell_degree_plan,
)
from src.adaptivity.variable_p_periodic_orbits import (
    build_variable_p_periodic_constraint_map,
)
from src.adaptivity.variable_p_transfer import (
    PETScSelectedRowLayout,
    VariablePGlobalTransfer,
    build_variable_p_global_transfer,
    project_p6_dual_to_active_full,
    recover_active_full_to_p6_field,
)
from src.adaptivity.stage4_local_h import (
    Stage4LocalHContext,
    build_stage4_local_h_reduction_authority,
)

from .hcurl_variable_p_assembly import (
    VariablePCondensedTraceSystem,
    _iteratively_refined_lu_solve,
    _lu_factor_matrix_action,
    audit_variable_p_active_full_adjoint_recovery,
    build_variable_p_condensed_trace_system_from_compiled_form,
    conform_variable_p_active_primal_trace_from_reduced,
    condense_variable_p_active_vector_to_trace,
    extract_variable_p_active_primal_to_reduced,
    recover_variable_p_active_full_adjoint_vector,
    recover_variable_p_active_full_vector,
    variable_p_cell_interior_schur_bilinear,
)


@dataclass
class VariablePRecoveredSolution:
    """Recovered p6 storage field and owned active-space PETSc vectors."""

    field: Any
    active_full_solution: PETSc.Vec | None
    active_full_rhs: PETSc.Vec | None
    active_auxiliary_interior_action: PETSc.Vec | None
    audit: dict[str, Any]
    _destroyed: bool = field(default=False, init=False, repr=False)

    def destroy(self) -> None:
        """Release the three owned active-space vectors exactly once."""

        if self._destroyed:
            return
        owned = (
            ("active_full_solution", self.active_full_solution),
            ("active_full_rhs", self.active_full_rhs),
            (
                "active_auxiliary_interior_action",
                self.active_auxiliary_interior_action,
            ),
        )
        self.active_full_solution = None
        self.active_full_rhs = None
        self.active_auxiliary_interior_action = None
        self._destroyed = True
        errors: list[str] = []
        for name, vector in owned:
            if vector is None:
                continue
            try:
                vector.destroy()
            except Exception as exc:
                errors.append(f"{name}: {type(exc).__name__}: {exc}")
        if errors:
            raise RuntimeError(
                "variable-p recovered-solution cleanup failed: "
                + "; ".join(errors)
            )

    def __enter__(self) -> VariablePRecoveredSolution:
        return self

    def __exit__(self, *_args: Any) -> None:
        self.destroy()


@dataclass
class VariablePRecoveredAdjoint:
    """Recovered active adjoint component with explicit PETSc lifecycle."""

    active_full_adjoint: PETSc.Vec | None
    active_full_goal: PETSc.Vec | None
    audit: dict[str, Any]
    _destroyed: bool = field(default=False, init=False, repr=False)

    def destroy(self) -> None:
        """Release the retained adjoint and copied goal vectors once."""

        if self._destroyed:
            return
        owned = (
            ("active_full_adjoint", self.active_full_adjoint),
            ("active_full_goal", self.active_full_goal),
        )
        self.active_full_adjoint = None
        self.active_full_goal = None
        self._destroyed = True
        errors: list[str] = []
        for name, vector in owned:
            if vector is None:
                continue
            try:
                vector.destroy()
            except Exception as exc:
                errors.append(f"{name}: {type(exc).__name__}: {exc}")
        if errors:
            raise RuntimeError(
                "variable-p recovered-adjoint cleanup failed: "
                + "; ".join(errors)
            )

    def __enter__(self) -> VariablePRecoveredAdjoint:
        return self

    def __exit__(self, *_args: Any) -> None:
        self.destroy()


@dataclass
class VariablePPrimalAffineComplement:
    """Off-manifold active-interior correction for one injected primal."""

    active_full_complement: PETSc.Vec | None
    audit: dict[str, Any]
    _destroyed: bool = field(default=False, init=False, repr=False)

    def destroy(self) -> None:
        """Release the owned active-space correction exactly once."""

        if self._destroyed:
            return
        vector = self.active_full_complement
        self.active_full_complement = None
        self._destroyed = True
        if vector is not None:
            vector.destroy()

    def __enter__(self) -> VariablePPrimalAffineComplement:
        return self

    def __exit__(self, *_args: Any) -> None:
        self.destroy()


def build_variable_p_primal_affine_complement(
    system: VariablePCondensedTraceSystem,
    active_full_primal: PETSc.Vec,
    active_full_rhs: PETSc.Vec,
    *,
    active_auxiliary_interior_action: PETSc.Vec | None = None,
) -> VariablePPrimalAffineComplement:
    """Return the exact eliminated-interior correction for an injected field.

    The injected current field has a conforming trace, but after transfer into
    an enriched shadow space its cell-interior coefficients need not lie on
    the shadow static-condensation affine manifold.  For every owned cell this
    routine evaluates

    ``c_i = -A_ii^-1 A_it x_t + A_ii^-1 (b_i + q_i) - x_i``

    using the retained local factors.  Only rows needed by locally owned cells
    are read through one reusable PETSc selected-row scatter; no complete
    active vector or p6 matrix is gathered or assembled.
    """

    active_rows = int(system.entity_map.active_rows)
    raw_trace_rows = int(system.entity_map.active_trace_rows)
    if not 0 <= raw_trace_rows <= active_rows:
        raise ValueError("variable-p active trace/full row counts are invalid")
    vectors = (
        ("active full primal", active_full_primal),
        ("active full RHS", active_full_rhs),
    )
    if active_auxiliary_interior_action is not None:
        vectors += (
            (
                "active auxiliary interior action",
                active_auxiliary_interior_action,
            ),
        )
    reference_layout = (
        int(active_full_primal.getSize()),
        int(active_full_primal.getLocalSize()),
        tuple(map(int, active_full_primal.getOwnershipRange())),
    )
    for label, vector in vectors:
        layout = (
            int(vector.getSize()),
            int(vector.getLocalSize()),
            tuple(map(int, vector.getOwnershipRange())),
        )
        if layout != reference_layout or layout[0] != active_rows:
            raise ValueError(f"{label} has the wrong active-space layout")

    requested_rows = np.concatenate(
        [
            np.concatenate(
                (recovery.cell.trace_rows, recovery.cell.interior_rows)
            )
            for recovery in system.cell_recovery
        ]
        or [np.empty(0, dtype=np.int64)]
    )
    complement = active_full_primal.duplicate()
    complement.set(PETSc.ScalarType(0.0))
    local_residual_sq = 0.0
    local_residual_max = 0.0
    local_closure_sq = 0.0
    local_closure_max = 0.0
    local_complement_sq = 0.0
    local_complement_max = 0.0
    selected_audit: dict[str, Any] | None = None
    try:
        with PETScSelectedRowLayout.create(
            active_full_primal,
            requested_rows,
        ) as selected:
            primal = selected.gather(active_full_primal)
            rhs = selected.gather(active_full_rhs)
            auxiliary = (
                np.zeros_like(rhs)
                if active_auxiliary_interior_action is None
                else selected.gather(active_auxiliary_interior_action)
            )
            selected_audit = dict(selected.audit)
            for recovery in system.cell_recovery:
                cell = recovery.cell
                trace_positions = selected.positions(cell.trace_rows)
                interior_positions = selected.positions(cell.interior_rows)
                local_trace = primal[trace_positions]
                local_interior = primal[interior_positions]
                effective_rhs = (
                    rhs[interior_positions]
                    + auxiliary[interior_positions]
                )
                homogeneous = (
                    system.interior_from_trace_by_class[
                        recovery.class_key
                    ]
                    @ local_trace
                )
                residual = effective_rhs - _lu_factor_matrix_action(
                    system.interior_lu_by_class[recovery.class_key],
                    local_interior - homogeneous,
                )
                correction = _iteratively_refined_lu_solve(
                    system.interior_lu_by_class[recovery.class_key],
                    residual,
                )
                closure = _lu_factor_matrix_action(
                    system.interior_lu_by_class[recovery.class_key],
                    correction,
                ) - residual
                if (
                    not np.all(np.isfinite(residual))
                    or not np.all(np.isfinite(correction))
                    or not np.all(np.isfinite(closure))
                ):
                    raise RuntimeError(
                        "variable-p affine complement contains non-finite "
                        "cell-interior values"
                    )
                complement.setValues(
                    np.asarray(cell.interior_rows, dtype=PETSc.IntType),
                    np.asarray(correction, dtype=PETSc.ScalarType),
                    addv=PETSc.InsertMode.INSERT_VALUES,
                )
                local_residual_sq += float(
                    np.vdot(residual, residual).real
                )
                local_residual_max = max(
                    local_residual_max,
                    float(np.max(np.abs(residual), initial=0.0)),
                )
                local_closure_sq += float(
                    np.vdot(closure, closure).real
                )
                local_closure_max = max(
                    local_closure_max,
                    float(np.max(np.abs(closure), initial=0.0)),
                )
                local_complement_sq += float(
                    np.vdot(correction, correction).real
                )
                local_complement_max = max(
                    local_complement_max,
                    float(np.max(np.abs(correction), initial=0.0)),
                )
        complement.assemble()
    except Exception:
        complement.destroy()
        raise

    comm = system.entity_map.mesh.comm
    residual_norm = float(
        np.sqrt(comm.allreduce(local_residual_sq, op=MPI.SUM))
    )
    residual_max = float(
        comm.allreduce(local_residual_max, op=MPI.MAX)
    )
    closure_norm = float(
        np.sqrt(comm.allreduce(local_closure_sq, op=MPI.SUM))
    )
    closure_max = float(
        comm.allreduce(local_closure_max, op=MPI.MAX)
    )
    complement_norm = float(
        np.sqrt(comm.allreduce(local_complement_sq, op=MPI.SUM))
    )
    complement_max = float(
        comm.allreduce(local_complement_max, op=MPI.MAX)
    )
    closure_tolerance = max(
        1.0e-12,
        5.0e-11 * max(residual_norm, 1.0),
    )
    if (
        not all(
            np.isfinite(value)
            for value in (
                residual_norm,
                residual_max,
                closure_norm,
                closure_max,
                complement_norm,
                complement_max,
            )
        )
        or closure_norm > closure_tolerance
    ):
        complement.destroy()
        raise RuntimeError(
            "variable-p affine-complement local solve did not close: "
            f"closure={closure_norm:.6e}, "
            f"tolerance={closure_tolerance:.6e}"
        )
    if selected_audit is None:
        complement.destroy()
        raise RuntimeError("affine-complement selected-row audit is absent")
    audit = {
        "schema_version": (
            "task035e.variable-p-primal-affine-complement.v1"
        ),
        "status": "active_interior_affine_complement_pass",
        "pass": True,
        "definition": (
            "c_i=-A_ii^-1*A_it*x_t+A_ii^-1*(b_i+q_i)-x_i"
        ),
        "active_full_rows": active_rows,
        "raw_active_trace_rows": raw_trace_rows,
        "active_interior_rows": active_rows - raw_trace_rows,
        "owned_cell_count_local": len(system.cell_recovery),
        "owned_cell_count_global": int(
            comm.allreduce(len(system.cell_recovery), op=MPI.SUM)
        ),
        "interior_residual_l2_norm": residual_norm,
        "interior_residual_max_abs": residual_max,
        "interior_local_solve_closure_l2_norm": closure_norm,
        "interior_local_solve_closure_max_abs": closure_max,
        "interior_local_solve_closure_tolerance": closure_tolerance,
        "active_full_complement_l2_norm": complement_norm,
        "active_full_complement_max_abs": complement_max,
        "auxiliary_interior_action_included": (
            active_auxiliary_interior_action is not None
        ),
        "selected_row_layout": {
            **selected_audit,
            "shared_layout_vector_count": (
                2
                if active_auxiliary_interior_action is None
                else 3
            ),
        },
        "trace_entries_constructed_as_exact_zero": True,
        "full_active_vector_python_gathered": False,
        "full_p6_global_matrix_allocated": False,
        "ordinary_default_changed": False,
    }
    return VariablePPrimalAffineComplement(
        active_full_complement=complement,
        audit=audit,
    )


@dataclass
class VariablePAssemblyTimeReduction:
    """One physically reduced variable-p Full3D operator."""

    system: VariablePCondensedTraceSystem
    transfer: VariablePGlobalTransfer
    degree_plan: VariablePCellDegreePlan
    build_audit: dict[str, Any]
    _trace_dual_factor_cache: dict[str, Any] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )

    def destroy(self) -> None:
        self._trace_dual_factor_cache.clear()
        self.system.destroy()

    def release_retained_local_schur(self) -> dict[str, Any]:
        """Close the optional callback-only Schur lease."""

        audit = self.system.release_retained_local_schur()
        self.build_audit["condensed_system"] = dict(
            self.system.build_audit
        )
        return audit

    def primal_affine_complement(
        self,
        active_full_primal: PETSc.Vec,
        active_full_rhs: PETSc.Vec,
        *,
        active_auxiliary_interior_action: PETSc.Vec | None = None,
    ) -> VariablePPrimalAffineComplement:
        """Build the injected primal's eliminated-interior DWR correction."""

        return build_variable_p_primal_affine_complement(
            self.system,
            active_full_primal,
            active_full_rhs,
            active_auxiliary_interior_action=(
                active_auxiliary_interior_action
            ),
        )

    def reduce_p6_vector(
        self,
        p6_vector: PETSc.Vec,
        *,
        side: str,
    ) -> PETSc.Vec:
        active = self.project_p6_vector(p6_vector)
        try:
            return self.reduce_active_vector(active, side=side)
        finally:
            active.destroy()

    def project_p6_vector(self, p6_vector: PETSc.Vec) -> PETSc.Vec:
        """Project one p6 dual vector into the true active full space."""

        return project_p6_dual_to_active_full(
            self.transfer,
            p6_vector,
        )

    def reduce_active_vector(
        self,
        active_full_vector: PETSc.Vec,
        *,
        side: str,
    ) -> PETSc.Vec:
        """Condense an already projected active vector."""

        return condense_variable_p_active_vector_to_trace(
            self.system,
            active_full_vector,
            side=side,
        )

    def extract_primal_to_reduced(
        self,
        active_full_primal: PETSc.Vec,
        *,
        auxiliary_reduced_values: np.ndarray,
        roundtrip_tolerance: float = 5.0e-10,
    ) -> tuple[PETSc.Vec, dict[str, Any]]:
        """Extract one conforming primal into independent trace coordinates."""

        return extract_variable_p_active_primal_to_reduced(
            self.system,
            active_full_primal,
            auxiliary_reduced_values=auxiliary_reduced_values,
            roundtrip_tolerance=roundtrip_tolerance,
        )

    def project_primal_trace_to_reduced(
        self,
        active_full_primal: PETSc.Vec,
        *,
        auxiliary_reduced_values: np.ndarray,
        roundtrip_tolerance: float = 5.0e-10,
    ) -> tuple[PETSc.Vec, PETSc.Vec, dict[str, Any]]:
        """Extract physical roots and return a constraint-conforming primal.

        This explicit opt-in is reserved for nested local-h carriers.  The
        strict extraction default remains unchanged.  Physical root
        coordinates are extracted from the input, all hanging/Floquet slave
        traces are reconstructed, active cell-interior coefficients are
        preserved bitwise, and a second strict extraction must close.
        """

        reduced = None
        conformed = None
        strict_reduced = None
        closure = None
        try:
            reduced, extraction = (
                extract_variable_p_active_primal_to_reduced(
                    self.system,
                    active_full_primal,
                    auxiliary_reduced_values=auxiliary_reduced_values,
                    roundtrip_tolerance=roundtrip_tolerance,
                    allow_physical_root_projection=True,
                )
            )
            conformed, projection = (
                conform_variable_p_active_primal_trace_from_reduced(
                    self.system,
                    active_full_primal,
                    reduced,
                )
            )
            strict_reduced, strict_extraction = (
                extract_variable_p_active_primal_to_reduced(
                    self.system,
                    conformed,
                    auxiliary_reduced_values=auxiliary_reduced_values,
                    roundtrip_tolerance=roundtrip_tolerance,
                )
            )
            closure = strict_reduced.copy()
            closure.axpy(PETSc.ScalarType(-1.0), reduced)
            closure_norm = float(closure.norm())
            closure_max = float(
                closure.norm(PETSc.NormType.NORM_INFINITY)
            )
            reference_norm = float(reduced.norm())
            reference_max = float(
                reduced.norm(PETSc.NormType.NORM_INFINITY)
            )
            relative_l2 = closure_norm / max(
                reference_norm,
                np.finfo(np.float64).tiny,
            )
            relative_linf = closure_max / max(
                reference_max,
                np.finfo(np.float64).tiny,
            )
            if (
                relative_l2 > float(roundtrip_tolerance)
                or relative_linf > float(roundtrip_tolerance)
            ):
                raise RuntimeError(
                    "physical-root projection strict re-extraction did not "
                    "close: "
                    f"relative_l2={relative_l2:.6e}, "
                    f"relative_linf={relative_linf:.6e}"
                )
        except Exception:
            if conformed is not None:
                conformed.destroy()
            if reduced is not None:
                reduced.destroy()
            raise
        finally:
            if closure is not None:
                closure.destroy()
            if strict_reduced is not None:
                strict_reduced.destroy()

        if reduced is None or conformed is None:
            raise RuntimeError(
                "physical-root projection lost an owned PETSc vector"
            )
        audit = {
            "schema_version": (
                "task035e.physical-root-primal-projection-pipeline.v1"
            ),
            "status": "physical_root_primal_projection_pipeline_pass",
            "pass": True,
            "input_extraction": extraction,
            "trace_projection": projection,
            "strict_reextraction": strict_extraction,
            "strict_reextraction_closure_l2_norm": closure_norm,
            "strict_reextraction_closure_linf_norm": closure_max,
            "strict_reextraction_reference_l2_norm": reference_norm,
            "strict_reextraction_reference_linf_norm": reference_max,
            "strict_reextraction_relative_l2": relative_l2,
            "strict_reextraction_relative_linf": relative_linf,
            "strict_reextraction_tolerance": float(
                roundtrip_tolerance
            ),
            "active_interior_rows_bitwise_unchanged": projection[
                "active_interior_rows_bitwise_unchanged"
            ],
            "input_receives_exact_nested_transfer_credit": False,
            "full_vector_allgather_used": False,
            "ordinary_default_changed": False,
        }
        return reduced, conformed, audit

    def enforce_trace_only_active_functional(
        self,
        active_full_vector: PETSc.Vec,
        *,
        role: str,
        relative_tolerance: float = 5.0e-12,
        absolute_tolerance: float = 1.0e-12,
    ) -> dict[str, Any]:
        """Validate and remove roundoff-only interior boundary entries.

        N1curl cell-interior functions have exactly zero tangential trace.
        A boundary functional must therefore have no active cell-interior
        entries.  FFCx quadrature may leave roundoff-sized values; accepting
        them into only part of the auxiliary Schur algebra would be
        inconsistent, so this gate validates and zeros them before any
        condensation, RHS accumulation, or recovery.
        """

        if active_full_vector.getSize() != self.system.entity_map.active_rows:
            raise ValueError("trace-only functional has the wrong size")
        row_start, row_end = map(
            int,
            active_full_vector.getOwnershipRange(),
        )
        values = active_full_vector.getArray()
        split = min(
            max(self.system.entity_map.active_trace_rows - row_start, 0),
            row_end - row_start,
        )
        local_trace_max = float(
            np.max(np.abs(values[:split]), initial=0.0)
        )
        local_interior_max = float(
            np.max(np.abs(values[split:]), initial=0.0)
        )
        local_interior_sq = float(
            np.vdot(values[split:], values[split:]).real
        )
        comm = self.system.entity_map.mesh.comm
        trace_max = float(
            comm.allreduce(local_trace_max, op=MPI.MAX)
        )
        interior_max = float(
            comm.allreduce(local_interior_max, op=MPI.MAX)
        )
        interior_norm = float(
            np.sqrt(comm.allreduce(local_interior_sq, op=MPI.SUM))
        )
        threshold = max(
            float(absolute_tolerance),
            float(relative_tolerance) * trace_max,
        )
        if interior_max > threshold:
            raise RuntimeError(
                f"{role} is not a trace-only N1curl functional: "
                f"interior_max={interior_max:.6e}, "
                f"threshold={threshold:.6e}"
            )
        values[split:] = PETSc.ScalarType(0.0)
        active_full_vector.assemble()
        return {
            "schema_version": (
                "task035d.variable-p-trace-only-functional.v1"
            ),
            "status": "trace_only_functional_roundoff_removed",
            "pass": True,
            "role": str(role),
            "active_trace_max_abs": trace_max,
            "removed_active_interior_max_abs": interior_max,
            "removed_active_interior_norm": interior_norm,
            "acceptance_threshold": threshold,
            "structural_reason": (
                "N1curl cell-interior basis has zero tangential trace"
            ),
            "auxiliary_dense_interior_schur_required": False,
            "ordinary_default_changed": False,
        }

    def interior_cross_bilinear(
        self,
        left_p6: PETSc.Vec,
        right_p6: PETSc.Vec,
    ) -> complex:
        left_active = self.project_p6_vector(left_p6)
        right_active = self.project_p6_vector(right_p6)
        try:
            return self.interior_cross_bilinear_active(
                left_active,
                right_active,
            )
        finally:
            left_active.destroy()
            right_active.destroy()

    def interior_cross_bilinear_active(
        self,
        left_active_full: PETSc.Vec,
        right_active_full: PETSc.Vec,
    ) -> complex:
        """Evaluate an interior Schur term from projected active vectors."""

        return variable_p_cell_interior_schur_bilinear(
            self.system,
            left_active_full,
            right_active_full,
        )

    def recover_adjoint(
        self,
        reduced_adjoint: PETSc.Vec,
        p6_full_goal: PETSc.Vec | None,
        *,
        active_full_goal_override: PETSc.Vec | None = None,
        appended_auxiliary_interior_coupling_absent: bool | None = None,
    ) -> VariablePRecoveredAdjoint:
        """Recover interior/constraint components of one reduced adjoint.

        This routine does not solve or audit the reduced adjoint equation.
        Callers must separately bind ``A_r^H z_r = g_r`` to a KSP residual.
        """

        if (
            self.system.appended_rows
            and appended_auxiliary_interior_coupling_absent is not True
        ):
            raise RuntimeError(
                "adjoint recovery with appended auxiliary rows requires "
                "an explicit trace-only interior-coupling qualification"
            )
        if active_full_goal_override is None:
            if p6_full_goal is None:
                raise ValueError(
                    "adjoint recovery requires a p6 or active full goal"
                )
            active_goal = project_p6_dual_to_active_full(
                self.transfer,
                p6_full_goal,
            )
            goal_source = "projected_p6_full_goal"
        else:
            if (
                active_full_goal_override.getSize()
                != self.system.entity_map.active_rows
            ):
                raise ValueError("active full goal override has the wrong size")
            active_goal = active_full_goal_override.copy()
            goal_source = "preprojected_active_full_goal"
        try:
            active_adjoint = (
                recover_variable_p_active_full_adjoint_vector(
                    self.system,
                    reduced_adjoint,
                    active_full_goal=active_goal,
                )
            )
        except Exception:
            active_goal.destroy()
            raise
        try:
            interior_audit = (
                audit_variable_p_active_full_adjoint_recovery(
                    self.system,
                    active_adjoint,
                    active_full_goal=active_goal,
                )
            )
            trace_audit = _trace_constraint_recovery_audit(
                self.system,
                reduced_adjoint,
                active_adjoint,
            )
        except Exception:
            active_adjoint.destroy()
            active_goal.destroy()
            raise
        return VariablePRecoveredAdjoint(
            active_full_adjoint=active_adjoint,
            active_full_goal=active_goal,
            audit={
                "schema_version": (
                    "task035d.variable-p-adjoint-recovery.v1"
                ),
                "status": (
                    "variable_p_adjoint_interior_constraint_recovery_pass"
                ),
                "pass": True,
                "active_full_rows": self.system.entity_map.active_rows,
                "active_trace_rows": self.system.active_trace_rows,
                "appended_auxiliary_rows": self.system.appended_rows,
                "appended_auxiliary_interior_coupling_absent": (
                    True
                    if not self.system.appended_rows
                    else bool(
                        appended_auxiliary_interior_coupling_absent
                    )
                ),
                "active_full_goal_source": goal_source,
                "interior_recovery": interior_audit,
                "trace_constraint_recovery": trace_audit,
                "adjoint_formula": (
                    "z_i=-A_ii^-H*A_ti^H*z_t+A_ii^-H*g_i"
                ),
                "primal_recovery_operator_reused_for_adjoint": False,
                "reduced_adjoint_equation_checked": False,
                "reduced_adjoint_ksp_residual_checked": False,
                "full_adjoint_solve_pass": False,
                "qualification_scope": (
                    "conditional_on_qualified_trace_constraint_map"
                ),
                "full_p6_global_matrix_allocated": False,
                "ordinary_default_changed": False,
            },
        )

    def recover(
        self,
        reduced_solution: PETSc.Vec,
        p6_full_rhs: PETSc.Vec | None,
        *,
        active_full_rhs_override: PETSc.Vec | None = None,
        auxiliary_interior_columns_local: np.ndarray | None = None,
        auxiliary_values: np.ndarray | None = None,
    ) -> VariablePRecoveredSolution:
        if active_full_rhs_override is None:
            if p6_full_rhs is None:
                raise ValueError(
                    "recovery requires a p6 or active full RHS"
                )
            active_rhs = project_p6_dual_to_active_full(
                self.transfer,
                p6_full_rhs,
            )
            rhs_source = "projected_p6_full_rhs"
        else:
            if (
                active_full_rhs_override.getSize()
                != self.system.entity_map.active_rows
            ):
                raise ValueError("active full RHS override has the wrong size")
            active_rhs = active_full_rhs_override.copy()
            rhs_source = "preprojected_active_full_rhs"
        auxiliary_action = _active_auxiliary_interior_action(
            self.system,
            active_rhs,
            columns_local=auxiliary_interior_columns_local,
            auxiliary_values=auxiliary_values,
        )
        effective_rhs = active_rhs
        if auxiliary_action is not None:
            effective_rhs = active_rhs.copy()
            effective_rhs.axpy(PETSc.ScalarType(1.0), auxiliary_action)
        try:
            active_solution = recover_variable_p_active_full_vector(
                self.system,
                reduced_solution,
                active_full_rhs=effective_rhs,
            )
        except Exception:
            if effective_rhs is not active_rhs:
                effective_rhs.destroy()
            active_rhs.destroy()
            if auxiliary_action is not None:
                auxiliary_action.destroy()
            raise
        if effective_rhs is not active_rhs:
            effective_rhs.destroy()
        try:
            trace_constraint_recovery = (
                _trace_constraint_recovery_audit(
                    self.system,
                    reduced_solution,
                    active_solution,
                )
            )
        except Exception:
            active_solution.destroy()
            active_rhs.destroy()
            if auxiliary_action is not None:
                auxiliary_action.destroy()
            raise
        try:
            field, field_audit = recover_active_full_to_p6_field(
                self.transfer,
                active_solution,
            )
        except Exception:
            active_solution.destroy()
            active_rhs.destroy()
            if auxiliary_action is not None:
                auxiliary_action.destroy()
            raise
        auxiliary_norm = (
            0.0
            if auxiliary_action is None
            else float(auxiliary_action.norm())
        )
        return VariablePRecoveredSolution(
            field=field,
            active_full_solution=active_solution,
            active_full_rhs=active_rhs,
            active_auxiliary_interior_action=auxiliary_action,
            audit={
                "schema_version": (
                    "task035d.variable-p-solution-recovery.v2"
                ),
                "status": "variable_p_full_field_recovery_pass",
                "pass": True,
                "active_full_rows": self.system.entity_map.active_rows,
                "active_trace_rows": self.system.active_trace_rows,
                "p6_storage_rows": self.transfer.audit["p6_global_rows"],
                "field_recovery": field_audit,
                "trace_constraint_recovery": (
                    trace_constraint_recovery
                ),
                "auxiliary_interior_action_included": (
                    auxiliary_action is not None
                ),
                "auxiliary_interior_action_norm": auxiliary_norm,
                "active_full_rhs_source": rhs_source,
                "interior_rhs_recovery_iterative_refinement_max_steps": (
                    self.system.build_audit[
                        "interior_rhs_recovery_iterative_refinement_max_steps"
                    ]
                ),
                "interior_trace_source": (
                    "assembled_global_active_trace"
                ),
                "trace_vector_assembled_before_interior_recovery": True,
                "full_p6_global_matrix_allocated": False,
                "ordinary_default_changed": False,
            },
        )

    def full_active_residual(
        self,
        reduced_matrix: PETSc.Mat,
        reduced_rhs: PETSc.Vec,
        reduced_solution: PETSc.Vec,
        recovered: VariablePRecoveredSolution,
    ) -> dict[str, Any]:
        """Audit reduced and every eliminated active-interior equation."""

        residual = reduced_matrix.createVecLeft()
        reduced_matrix.mult(reduced_solution, residual)
        residual.axpy(PETSc.ScalarType(-1.0), reduced_rhs)
        try:
            reduced_norms, reduced_norm_audit = (
                _reduced_trace_auxiliary_norms(
                    self.system,
                    (
                        ("residual", residual, "dual"),
                        ("rhs", reduced_rhs, "dual"),
                        ("solution", reduced_solution, "primal"),
                    ),
                    factor_cache=self._trace_dual_factor_cache,
                )
            )
        finally:
            residual.destroy()
        reduced_norm = reduced_norms["residual"]
        reduced_rhs_norm = reduced_norms["rhs"]
        reduced_solution_norm = reduced_norms["solution"]

        active_solution_vector = recovered.active_full_solution
        active_rhs_vector = recovered.active_full_rhs
        if active_solution_vector is None or active_rhs_vector is None:
            raise RuntimeError(
                "recovered active vectors were released before residual audit"
            )
        requested_active_rows = np.concatenate(
            [
                np.concatenate(
                    (recovery.cell.trace_rows, recovery.cell.interior_rows)
                )
                for recovery in self.system.cell_recovery
            ]
            or [np.empty(0, dtype=np.int64)]
        )
        with PETScSelectedRowLayout.create(
            active_solution_vector,
            requested_active_rows,
        ) as active_layout:
            active_solution = active_layout.gather(active_solution_vector)
            active_rhs = active_layout.gather(active_rhs_vector)
            auxiliary_action = (
                np.zeros_like(active_rhs)
                if recovered.active_auxiliary_interior_action is None
                else active_layout.gather(
                    recovered.active_auxiliary_interior_action
                )
            )
            active_selected_audit = dict(active_layout.audit)

        local_interior_sq = 0.0
        local_interior_max = 0.0
        local_interior_rhs_sq = 0.0
        local_interior_solution_sq = 0.0
        for recovery in self.system.cell_recovery:
            cell = recovery.cell
            trace_positions = np.searchsorted(
                active_layout.global_rows,
                cell.trace_rows,
            )
            interior_positions = np.searchsorted(
                active_layout.global_rows,
                cell.interior_rows,
            )
            local_trace = active_solution[trace_positions]
            local_interior = active_solution[interior_positions]
            homogeneous = (
                self.system.interior_from_trace_by_class[
                    recovery.class_key
                ]
                @ local_trace
            )
            delta = local_interior - homogeneous
            action = _lu_factor_matrix_action(
                self.system.interior_lu_by_class[recovery.class_key],
                delta,
            )
            action -= active_rhs[interior_positions]
            action -= auxiliary_action[interior_positions]
            local_interior_sq += float(np.vdot(action, action).real)
            local_rhs = active_rhs[interior_positions]
            local_interior_rhs_sq += float(
                np.vdot(local_rhs, local_rhs).real
            )
            local_interior_solution_sq += float(
                np.vdot(local_interior, local_interior).real
            )
            local_interior_max = max(
                local_interior_max,
                float(np.max(np.abs(action), initial=0.0)),
            )
        comm = self.system.entity_map.mesh.comm
        interior_norm = float(
            np.sqrt(comm.allreduce(local_interior_sq, op=MPI.SUM))
        )
        interior_max = float(
            comm.allreduce(local_interior_max, op=MPI.MAX)
        )
        full_norm = float(np.hypot(reduced_norm, interior_norm))
        interior_rhs_norm = float(
            np.sqrt(
                comm.allreduce(local_interior_rhs_sq, op=MPI.SUM)
            )
        )
        rhs_norm = float(
            np.hypot(reduced_rhs_norm, interior_rhs_norm)
        )
        interior_solution_norm = float(
            np.sqrt(
                comm.allreduce(
                    local_interior_solution_sq,
                    op=MPI.SUM,
                )
            )
        )
        solution_norm = float(
            np.hypot(reduced_solution_norm, interior_solution_norm)
        )
        return {
            "linear_system_rhs_norm": rhs_norm,
            "linear_system_solution_norm": solution_norm,
            "linear_system_residual_norm": full_norm,
            "linear_system_relative_residual": (
                full_norm / max(rhs_norm, 1.0e-30)
            ),
            "reduced_trace_dtn_rhs_norm": reduced_rhs_norm,
            "reduced_trace_dtn_relative_residual": (
                reduced_norm / max(reduced_rhs_norm, 1.0e-30)
            ),
            "reduced_trace_dtn_residual_norm": reduced_norm,
            "eliminated_cell_interior_rhs_norm": interior_rhs_norm,
            "eliminated_cell_interior_residual_norm": interior_norm,
            "eliminated_cell_interior_max_abs_residual": interior_max,
            "auxiliary_interior_action_included": (
                recovered.active_auxiliary_interior_action is not None
            ),
            "full_operator_residual_method": (
                "exact block-Gaussian transformed residual: explicit "
                "variable-p reduced trace+DtN Mat action plus "
                "LU-reconstructed action on every eliminated active "
                "cell-interior equation"
                + (
                    ", including the solved auxiliary DtN column action"
                    if recovered.active_auxiliary_interior_action
                    is not None
                    else (
                        "; the trace-only port gate makes auxiliary "
                        "cell-interior columns structurally zero"
                    )
                )
            ),
            "linear_system_norm_definition": (
                "constraint-induced norm of [reduced trace+DtN equations, "
                "eliminated active-interior equations]; dual trace uses "
                "(C^H C)^-1, primal trace uses C^H C, and the RHS uses "
                "the same block-Gaussian transformed coordinates"
            ),
            "residual_space": (
                "true exact-sequence active variable-p test space"
            ),
            "p6_complement_residual_is_error_estimator_not_solver_gate": True,
            "full_p6_global_matrix_allocated_for_residual": False,
            "active_selected_rows": {
                **active_selected_audit,
                "shared_layout_vector_count": 3,
                "selected_row_layout_reused_for_solution_rhs_auxiliary": True,
                "selected_values_peak_bytes_local": (
                    3
                    * int(
                        active_selected_audit[
                            "selected_value_bytes_local"
                        ]
                    )
                ),
            },
            "reduced_constraint_norm": reduced_norm_audit,
            "replicated_active_vector_bytes_per_rank": 0,
            "replicated_reduced_vector_bytes_per_rank": 0,
            "ordinary_default_changed": False,
        }


def _trace_constraint_recovery_audit(
    system: VariablePCondensedTraceSystem,
    reduced_solution: PETSc.Vec,
    active_solution: PETSc.Vec,
) -> dict[str, Any]:
    """Verify every recovered raw trace row against its physical root map."""

    constraints = system.trace_constraints
    if constraints is None:
        return {
            "schema_version": (
                "task035d.trace-constraint-recovery-audit.v1"
            ),
            "status": "not_required",
            "pass": True,
            "constraint_kinds": [],
            "maximum_abs_error": 0.0,
            "relative_l2_error": 0.0,
            "replicated_reduced_vector_bytes_per_rank": 0,
            "replicated_active_vector_bytes_per_rank": 0,
            "selected_reduced_rows_local": 0,
            "selected_active_rows_local": 0,
            "ordinary_default_changed": False,
        }
    comm = system.entity_map.mesh.comm
    routed_blocks = getattr(
        constraints,
        "work_owned_entity_blocks",
        None,
    )
    active_start, active_stop = map(
        int,
        active_solution.getOwnershipRange(),
    )
    blocks = (
        tuple(routed_blocks)
        if routed_blocks is not None
        else tuple(
            block
            for block in constraints.entity_blocks.values()
            if active_start <= int(block.full_rows[0]) < active_stop
        )
    )
    requested_reduced_rows = np.concatenate(
        [block.independent_rows for block in blocks]
        or [np.empty(0, dtype=np.int64)]
    )
    requested_active_rows = np.concatenate(
        [block.full_rows for block in blocks]
        or [np.empty(0, dtype=np.int64)]
    )
    with PETScSelectedRowLayout.create(
        reduced_solution,
        requested_reduced_rows,
    ) as reduced_layout:
        trace = reduced_layout.gather(reduced_solution)
        reduced_selected_audit = dict(reduced_layout.audit)
    with PETScSelectedRowLayout.create(
        active_solution,
        requested_active_rows,
    ) as active_layout:
        active = active_layout.gather(active_solution)
        active_selected_audit = dict(active_layout.audit)
    local_error_sq = 0.0
    local_reference_sq = 0.0
    local_maximum = 0.0
    local_rows = 0
    for block in blocks:
        expected = (
            np.asarray(
                block.full_from_independent,
                dtype=np.complex128,
            )
            @ trace[
                np.searchsorted(
                    reduced_layout.global_rows,
                    np.asarray(block.independent_rows, dtype=np.int64),
                )
            ]
        )
        observed = active[
            np.searchsorted(
                active_layout.global_rows,
                np.asarray(block.full_rows, dtype=np.int64),
            )
        ]
        error = observed - expected
        local_error_sq += float(np.vdot(error, error).real)
        local_reference_sq += float(np.vdot(expected, expected).real)
        local_maximum = max(
            local_maximum,
            float(np.max(np.abs(error), initial=0.0)),
        )
        local_rows += len(block.full_rows)
    error_norm = float(
        np.sqrt(comm.allreduce(local_error_sq, op=MPI.SUM))
    )
    reference_norm = float(
        np.sqrt(comm.allreduce(local_reference_sq, op=MPI.SUM))
    )
    maximum = float(comm.allreduce(local_maximum, op=MPI.MAX))
    covered_rows = int(comm.allreduce(local_rows, op=MPI.SUM))
    relative = error_norm / max(reference_norm, 1.0)
    if (
        covered_rows != system.entity_map.active_trace_rows
        or maximum > 5.0e-11
        or relative > 5.0e-11
    ):
        raise RuntimeError(
            "physical trace recovery failed: "
            f"rows={covered_rows}/{system.entity_map.active_trace_rows}, "
            f"max={maximum:.6e}, relative={relative:.6e}"
        )
    return {
        "schema_version": "task035d.trace-constraint-recovery-audit.v1",
        "status": "physical_trace_recovery_pass",
        "pass": True,
        "constraint_kinds": sorted(
            map(str, constraints.audit.get("constraint_kinds", ()))
        ),
        "covered_raw_trace_rows": covered_rows,
        "expected_raw_trace_rows": system.entity_map.active_trace_rows,
        "maximum_abs_error": maximum,
        "relative_l2_error": relative,
        "reduced_selected_rows": reduced_selected_audit,
        "active_selected_rows": active_selected_audit,
        "replicated_reduced_vector_bytes_per_rank": 0,
        "replicated_active_vector_bytes_per_rank": 0,
        "selected_reduced_rows_local": len(
            reduced_layout.global_rows
        ),
        "selected_active_rows_local": len(active_layout.global_rows),
        "selected_row_scatter_cache_count": 2,
        "hanging_trace_recovery_explicitly_checked": (
            "hanging"
            in constraints.audit.get("constraint_kinds", ())
        ),
        "ordinary_default_changed": False,
    }


@dataclass(frozen=True)
class _TraceNormComponent:
    rows: np.ndarray
    gram: np.ndarray | sparse.csr_matrix
    cache_key: str


def _trace_norm_components(
    system: VariablePCondensedTraceSystem,
    template: PETSc.Vec,
) -> tuple[_TraceNormComponent, ...]:
    """Return only Gram components assigned to this PETSc root-row owner."""

    constraints = system.trace_constraints
    if constraints is None:
        return ()
    gram = getattr(constraints, "component_gram", None)
    if gram is None:
        blocks_by_root: dict[tuple[int, int], list[Any]] = {}
        for block in constraints.entity_blocks.values():
            blocks_by_root.setdefault(
                (int(block.dimension), int(block.root_entity)),
                [],
            ).append(block)
        row_start, row_end = map(int, template.getOwnershipRange())
        components = []
        for blocks in blocks_by_root.values():
            rows = np.asarray(
                blocks[0].independent_rows,
                dtype=np.int64,
            )
            if not row_start <= int(rows[0]) < row_end:
                continue
            component_gram = np.zeros(
                (len(rows), len(rows)),
                dtype=np.complex128,
            )
            for block in blocks:
                if not np.array_equal(rows, block.independent_rows):
                    raise RuntimeError(
                        "one periodic orbit has inconsistent row identity"
                    )
                expansion = np.asarray(
                    block.full_from_independent,
                    dtype=np.complex128,
                )
                component_gram += expansion.conj().T @ expansion
            cache_key = hashlib.sha256(
                np.ascontiguousarray(rows).view(np.uint8)
            ).hexdigest()
            rows.setflags(write=False)
            components.append(
                _TraceNormComponent(
                    rows=rows,
                    gram=component_gram,
                    cache_key=cache_key,
                )
            )
        covered = int(
            system.entity_map.mesh.comm.allreduce(
                sum(len(component.rows) for component in components),
                op=MPI.SUM,
            )
        )
        if covered != system.active_trace_rows:
            raise RuntimeError(
                "work-owned periodic components do not cover every root row"
            )
        return tuple(components)
    expected_shape = (
        system.active_trace_rows,
        system.active_trace_rows,
    )
    if gram.shape != expected_shape:
        raise RuntimeError("physical trace component Gram has the wrong shape")
    structure = sparse.csr_matrix(gram)
    structure.data = np.ones_like(structure.data, dtype=np.int8)
    component_count, labels = csgraph.connected_components(
        structure,
        directed=False,
        return_labels=True,
    )
    row_start, row_end = map(int, template.getOwnershipRange())
    components: list[_TraceNormComponent] = []
    for component in range(int(component_count)):
        rows = np.flatnonzero(labels == component).astype(np.int64)
        if not len(rows):
            raise RuntimeError("trace Gram contains an empty component")
        work_owner_row = int(rows[0])
        if not row_start <= work_owner_row < row_end:
            continue
        if sparse.issparse(gram):
            block = sparse.csr_matrix(gram[rows][:, rows])
        else:
            block = np.ascontiguousarray(
                np.asarray(gram)[np.ix_(rows, rows)]
            )
        cache_key = hashlib.sha256(
            np.ascontiguousarray(rows).view(np.uint8)
        ).hexdigest()
        rows.setflags(write=False)
        components.append(
            _TraceNormComponent(
                rows=rows,
                gram=block,
                cache_key=cache_key,
            )
        )
    covered = int(
        system.entity_map.mesh.comm.allreduce(
            sum(len(component.rows) for component in components),
            op=MPI.SUM,
        )
    )
    if covered != system.active_trace_rows:
        raise RuntimeError(
            "work-owned trace Gram components do not cover every root row"
        )
    return tuple(components)


def _solve_trace_component(
    component: _TraceNormComponent,
    values: np.ndarray,
    factor_cache: dict[str, Any],
) -> tuple[np.ndarray, bool]:
    """Solve one small SPD component, caching exactly one local factor."""

    factor = factor_cache.get(component.cache_key)
    created = factor is None
    if factor is None:
        if sparse.issparse(component.gram):
            factor = (
                "sparse_lu",
                sparse_linalg.splu(
                    sparse.csc_matrix(component.gram)
                ),
            )
        else:
            factor = (
                "dense_cholesky",
                np.linalg.cholesky(
                    np.asarray(component.gram, dtype=np.complex128)
                ),
            )
        factor_cache[component.cache_key] = factor
    kind, payload = factor
    if kind == "sparse_lu":
        result = payload.solve(values)
    elif kind == "dense_cholesky":
        intermediate = np.linalg.solve(payload, values)
        result = np.linalg.solve(payload.conj().T, intermediate)
    else:
        raise RuntimeError("trace component factor cache is invalid")
    return np.asarray(result, dtype=np.complex128), created


def _reduced_trace_auxiliary_norms(
    system: VariablePCondensedTraceSystem,
    vectors: tuple[tuple[str, PETSc.Vec, str], ...],
    *,
    factor_cache: dict[str, Any] | None = None,
) -> tuple[dict[str, float], dict[str, Any]]:
    """Compute several invariant norms from one selected-row layout."""

    if not vectors or len({name for name, _, _ in vectors}) != len(vectors):
        raise ValueError("reduced norm vectors require unique names")
    if any(kind not in {"dual", "primal"} for _, _, kind in vectors):
        raise ValueError("reduced trace norm must be primal or dual")
    expected = system.active_trace_rows + system.appended_rows
    if any(int(vector.getSize()) != expected for _, vector, _ in vectors):
        raise ValueError("reduced norm vector has the wrong global size")
    constraints = system.trace_constraints
    if constraints is None:
        values = {
            name: float(vector.norm(PETSc.NormType.NORM_2))
            for name, vector, _ in vectors
        }
        return values, {
            "schema_version": "task035e.work-owned-trace-norm.v1",
            "status": "unconstrained_distributed_petsc_norm",
            "pass": True,
            "work_owned_component_count_local": 0,
            "selected_trace_rows_local": 0,
            "replicated_reduced_vector_bytes_per_rank": 0,
            "global_component_gram_factorizations": 0,
            "read_only_component_gram_authority_bytes_per_rank": 0,
            "additional_replicated_global_gram_numeric_copy_bytes_per_rank": 0,
            "selected_row_layout_reused_vector_count": 0,
            "full_vector_allgather_used": False,
        }

    components = _trace_norm_components(system, vectors[0][1])
    authority_gram = getattr(constraints, "component_gram", None)
    if authority_gram is None:
        authority_gram_bytes = 0
    elif sparse.issparse(authority_gram):
        authority_gram_bytes = int(
            authority_gram.data.nbytes
            + authority_gram.indices.nbytes
            + authority_gram.indptr.nbytes
        )
    else:
        authority_gram_bytes = int(
            np.asarray(authority_gram).nbytes
        )
    requested_rows = np.concatenate(
        [component.rows for component in components]
        or [np.empty(0, dtype=np.int64)]
    )
    local_factor_cache = {} if factor_cache is None else factor_cache
    factor_count_before = len(local_factor_cache)
    factor_creations = 0
    factor_hits = 0
    maximum_dual_solve_relative_residual = 0.0
    local_component_bytes = int(
        sum(
            (
                component.gram.data.nbytes
                + component.gram.indices.nbytes
                + component.gram.indptr.nbytes
            )
            if sparse.issparse(component.gram)
            else component.gram.nbytes
            for component in components
        )
    )
    local_results: dict[str, float] = {}
    with PETScSelectedRowLayout.create(
        vectors[0][1],
        requested_rows,
    ) as layout:
        layout_audit = dict(layout.audit)
        for name, vector, trace_kind in vectors:
            selected = layout.gather(vector)
            trace_sq = 0.0
            for component in components:
                positions = layout.positions(component.rows)
                block_values = selected[positions]
                if trace_kind == "primal":
                    gram_action = component.gram @ block_values
                else:
                    gram_action, created = _solve_trace_component(
                        component,
                        block_values,
                        local_factor_cache,
                    )
                    factor_creations += int(created)
                    factor_hits += int(not created)
                    residual = (
                        component.gram @ gram_action - block_values
                    )
                    maximum_dual_solve_relative_residual = max(
                        maximum_dual_solve_relative_residual,
                        float(
                            np.linalg.norm(residual)
                            / max(np.linalg.norm(block_values), 1.0)
                        ),
                    )
                contribution = np.vdot(block_values, gram_action)
                if (
                    abs(float(contribution.imag))
                    > 5.0e-11
                    * max(abs(float(contribution.real)), 1.0)
                    or float(contribution.real) < -5.0e-11
                ):
                    raise RuntimeError(
                        "physical trace component norm is not positive real"
                    )
                trace_sq += max(float(contribution.real), 0.0)
            row_start, row_end = map(int, vector.getOwnershipRange())
            auxiliary_start = max(
                system.active_trace_rows,
                row_start,
            )
            local = np.asarray(
                vector.getArray(readonly=True),
                dtype=np.complex128,
            )
            offset = auxiliary_start - row_start
            auxiliary = (
                local[offset:]
                if row_end > auxiliary_start
                else np.empty(0, dtype=np.complex128)
            )
            auxiliary_sq = float(np.vdot(auxiliary, auxiliary).real)
            global_sq = float(
                system.entity_map.mesh.comm.allreduce(
                    trace_sq + auxiliary_sq,
                    op=MPI.SUM,
                )
            )
            local_results[name] = float(np.sqrt(max(global_sq, 0.0)))
    maximum_dual_solve_relative_residual = float(
        system.entity_map.mesh.comm.allreduce(
            maximum_dual_solve_relative_residual,
            op=MPI.MAX,
        )
    )
    if maximum_dual_solve_relative_residual > 5.0e-11:
        raise RuntimeError(
            "physical trace component Gram solve failed: "
            f"{maximum_dual_solve_relative_residual:.6e}"
        )
    return local_results, {
        "schema_version": "task035e.work-owned-trace-norm.v1",
        "status": "work_owned_component_norm_pass",
        "pass": True,
        "work_owned_component_count_local": len(components),
        "work_owned_component_rows_local": sum(
            len(component.rows) for component in components
        ),
        "work_owned_component_gram_bytes_local": local_component_bytes,
        "selected_trace_rows_local": len(layout.global_rows),
        "selected_rows": layout_audit,
        "replicated_reduced_vector_bytes_per_rank": 0,
        "global_component_gram_factorizations": 0,
        "read_only_component_gram_authority_bytes_per_rank": (
            authority_gram_bytes
        ),
        "additional_replicated_global_gram_numeric_copy_bytes_per_rank": 0,
        "local_component_factor_cache_size_before": factor_count_before,
        "local_component_factor_cache_size_after": len(
            local_factor_cache
        ),
        "local_component_factorizations_new": factor_creations,
        "local_component_factor_cache_hits": factor_hits,
        "maximum_dual_solve_relative_residual": (
            maximum_dual_solve_relative_residual
        ),
        "selected_row_layout_reused_vector_count": len(vectors),
        "full_vector_allgather_used": False,
    }


def _reduced_trace_auxiliary_norm(
    system: VariablePCondensedTraceSystem,
    vector: PETSc.Vec,
    *,
    trace_kind: str,
) -> float:
    """Return one invariant norm through owner-local selected components."""

    values, _audit = _reduced_trace_auxiliary_norms(
        system,
        (("value", vector, trace_kind),),
    )
    return values["value"]


def _active_auxiliary_interior_action(
    system: VariablePCondensedTraceSystem,
    template: PETSc.Vec,
    *,
    columns_local: np.ndarray | None,
    auxiliary_values: np.ndarray | None,
) -> PETSc.Vec | None:
    """Build ``sum_j t_i,j a_j`` without global auxiliary-column storage."""

    if columns_local is None and auxiliary_values is None:
        return None
    if columns_local is None or auxiliary_values is None:
        raise ValueError(
            "auxiliary interior columns and values must be supplied together"
        )
    columns = np.asarray(columns_local, dtype=np.complex128)
    values = np.asarray(auxiliary_values, dtype=np.complex128)
    if columns.ndim != 2 or values.ndim != 1:
        raise ValueError("auxiliary interior data has the wrong rank")
    row_start, row_end = map(int, template.getOwnershipRange())
    interior_start = max(row_start, system.entity_map.active_trace_rows)
    local_interior_rows = max(0, row_end - interior_start)
    if columns.shape != (local_interior_rows, len(values)):
        raise ValueError(
            "local auxiliary interior columns have the wrong shape"
        )
    if not np.all(np.isfinite(columns)) or not np.all(np.isfinite(values)):
        raise ValueError("auxiliary interior data contains non-finite values")
    action = template.duplicate()
    action.set(PETSc.ScalarType(0.0))
    if local_interior_rows:
        local = action.getArray()
        offset = interior_start - row_start
        local[offset:] = columns @ values
    action.assemble()
    return action


def build_variable_p_assembly_time_reduction(
    compiled_p6_form: Any,
    p6_space: Any,
    cell_tags: Any,
    *,
    degree_plan_path: str | None,
    phase_x: complex,
    phase_y: complex,
    local_h_context: Stage4LocalHContext | None = None,
    appended_global_rows: int = 0,
    appended_support_owned_cell_groups: tuple[np.ndarray, ...] = (),
    appended_support_group_by_row: tuple[int, ...] = (),
    defer_final_assembly: bool = False,
    retain_local_schur_for_research: bool = False,
    persistent_raw_tensor_cache_directory: (
        str | os.PathLike[str] | None
    ) = None,
    persistent_raw_tensor_cache_namespace: str | None = None,
) -> VariablePAssemblyTimeReduction:
    """Build one hash-bound Task035d p4/p5/p6 reduction."""

    if local_h_context is None:
        if degree_plan_path is None:
            raise ValueError(
                "variable-p reduction requires a cell-degree or local-h plan"
            )
        degree_plan = load_variable_p_cell_degree_plan(
            p6_space.mesh,
            degree_plan_path,
        )
        trace_constraints = None
        periodic = build_variable_p_periodic_constraint_map(
            degree_plan.entity_map,
            axes=("x", "y"),
            phase_x=complex(phase_x),
            phase_y=complex(phase_y),
        )
        physical_active_fe_dofs = degree_plan.entity_map.active_rows
        local_h_audit = None
    else:
        if degree_plan_path is not None:
            raise ValueError(
                "local-h and conforming cell-degree plans are mutually exclusive"
            )
        if p6_space.mesh is not local_h_context.carrier.mesh:
            raise ValueError(
                "local-h context and p6 storage space use different meshes"
            )
        local_h = build_stage4_local_h_reduction_authority(
            local_h_context,
            phase_x=complex(phase_x),
            phase_y=complex(phase_y),
        )
        degree_plan = local_h.degree_plan
        trace_constraints = local_h.trace_constraints
        periodic = None
        physical_active_fe_dofs = int(
            local_h.audit[
                "actual_full3d_equivalent_active_fe_dofs"
            ]
        )
        local_h_audit = dict(local_h.audit)
    task035e_scope = bool(
        local_h_audit is not None
        and local_h_audit.get("mesh", {}).get("schema_version")
        == "task035e.stage4-multilevel-local-h-mesh.v1"
    )
    advisory_dof_target = 90_000
    if (
        not task035e_scope
        and physical_active_fe_dofs > advisory_dof_target
    ):
        raise RuntimeError(
            "Task035d variable-p candidate exceeds the fail-closed "
            "90,000 active FE DoF gate; use the standard/static backend "
            "for a global-p control"
        )
    global_transfer_started = perf_counter()
    transfer = build_variable_p_global_transfer(
        degree_plan.entity_map,
        p6_space,
    )
    global_transfer_seconds_local = float(
        perf_counter() - global_transfer_started
    )
    timing_comm = degree_plan.entity_map.mesh.comm
    global_transfer_seconds_buffer = np.empty(
        timing_comm.size,
        dtype=np.float64,
    )
    timing_comm.Allgather(
        np.asarray(
            [global_transfer_seconds_local],
            dtype=np.float64,
        ),
        global_transfer_seconds_buffer,
    )
    global_transfer_seconds_by_rank = tuple(
        float(value) for value in global_transfer_seconds_buffer
    )
    global_transfer_setup_timing = {
        "semantics": (
            "perf_counter wall seconds; the rank-local build is measured "
            "without an added barrier and seconds_max is the collective "
            "critical-path envelope"
        ),
        "seconds_by_rank": global_transfer_seconds_by_rank,
        "seconds_max": max(global_transfer_seconds_by_rank, default=0.0),
    }
    system = (
        build_variable_p_condensed_trace_system_from_compiled_form(
            compiled_p6_form,
            p6_space,
            cell_tags,
            degree_plan.entity_map,
            periodic_constraints=periodic,
            trace_constraints=trace_constraints,
            appended_global_rows=appended_global_rows,
            appended_support_owned_cell_groups=(
                appended_support_owned_cell_groups
            ),
            appended_support_group_by_row=(
                appended_support_group_by_row
            ),
            defer_final_assembly=defer_final_assembly,
            retain_local_schur_for_research=(
                retain_local_schur_for_research
            ),
            persistent_raw_tensor_cache_directory=(
                persistent_raw_tensor_cache_directory
            ),
            persistent_raw_tensor_cache_namespace=(
                persistent_raw_tensor_cache_namespace
            ),
        )
    )
    audit = {
        "schema_version": "task035d.variable-p-assembly-reduction.v1",
        "status": "variable_p_assembly_time_reduction_built",
        "pass": True,
        "degree_plan": dict(degree_plan.audit),
        "periodic_constraints": (
            None if periodic is None else dict(periodic.audit)
        ),
        "trace_constraints": (
            None
            if trace_constraints is None
            else dict(trace_constraints.audit)
        ),
        "local_h": local_h_audit,
        "global_transfer": dict(transfer.audit),
        "condensed_system": dict(system.build_audit),
        "setup_anatomy": {
            "schema_version": "task035e.variable-p-setup-anatomy.v1",
            "global_transfer": global_transfer_setup_timing,
            "local_h_phase_timing_audit_field": (
                None
                if local_h_audit is None
                else "local_h.phase_timings_seconds_by_rank"
            ),
            "trace_constraint_phase_timing_audit_field": (
                None
                if local_h_audit is None
                else "local_h.trace_constraint_setup_timing"
            ),
            "condensed_system_phase_timing_audit_field": (
                "condensed_system.phase_timings_seconds_by_rank"
            ),
            "compiled_builder_phase_timing_audit_field": (
                "condensed_system."
                "compiled_builder_phase_timings_seconds_by_rank"
            ),
            "timing_fields_are_diagnostic_only": True,
            "ordinary_default_changed": False,
        },
        "actual_conforming_active_fe_dofs": (
            physical_active_fe_dofs
        ),
        "actual_full3d_equivalent_active_fe_dofs": (
            physical_active_fe_dofs
        ),
        "raw_broken_active_fe_dofs": (
            degree_plan.entity_map.active_rows
        ),
        "active_fe_dof_hard_gate_active": not task035e_scope,
        "active_fe_dof_gate_limit": (
            None if task035e_scope else advisory_dof_target
        ),
        "active_fe_dof_gate_pass": (
            True
            if task035e_scope
            else physical_active_fe_dofs <= advisory_dof_target
        ),
        "active_fe_dof_advisory_target": advisory_dof_target,
        "active_fe_dof_advisory_target_met": (
            physical_active_fe_dofs <= advisory_dof_target
        ),
        "full_p6_global_matrix_allocated": False,
        "inactive_p6_rows_globally_numbered": False,
        "ordinary_default_changed": False,
    }
    system.build_audit["variable_p_reduction"] = audit
    return VariablePAssemblyTimeReduction(
        system=system,
        transfer=transfer,
        degree_plan=degree_plan,
        build_audit=audit,
    )


__all__ = [
    "VariablePAssemblyTimeReduction",
    "VariablePPrimalAffineComplement",
    "VariablePRecoveredAdjoint",
    "VariablePRecoveredSolution",
    "build_variable_p_primal_affine_complement",
    "build_variable_p_assembly_time_reduction",
]
