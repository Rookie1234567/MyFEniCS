"""Typed, opt-in iterative profiles for the condensed Stage-4 trace system.

The ordinary solver remains direct MUMPS.  This module owns only explicit
research profiles so that a raw PETSc option cannot be relabelled as a
qualified factor-free result.

The Review-V2 physics-aware discriminator uses the actual block structure

    [ A_tt  B ] [trace] = [f_t]
    [ C     D ] [ dtn ]   [f_d]

of the assembly-time-condensed operator.  One low-storage coarse vector is
built for every DtN auxiliary mode:

    w_j = [-diag(A_tt)^(-1) B_j; e_j].

These vectors retain the physical port-mode identity while lifting it into
the trace space.  A fixed Jacobi smoother plus exact Galerkin correction on
their span is applied through a PETSc Python PC.  The fine operator has no
sparse direct factor.  The replicated dense coarse factor is deliberately
reported separately; it must not be hidden by the phrase ``factor free``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import time
from typing import Any

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc

from .physical_slab_two_level import (
    SparseCoarseVector,
    SparseGalerkinTwoLevelPc,
)


@dataclass(frozen=True)
class CondensedIterativeProfile:
    """Programmatic identity and qualification state of one research profile."""

    name: str
    ksp_type: str
    pc_strategy: str
    restart: int = 30
    maximum_iterations: int = 200
    relative_tolerance: float = 1.0e-8
    absolute_tolerance: float = 1.0e-12
    norm_type: str = "unpreconditioned"
    evidence_status: str = "not_run"


_PROFILES = {
    "gmres_jacobi": CondensedIterativeProfile(
        name="gmres_jacobi",
        ksp_type="gmres",
        pc_strategy="jacobi",
        evidence_status="closed_controlled_negative",
    ),
    "fgmres_asm_ilu": CondensedIterativeProfile(
        name="fgmres_asm_ilu",
        ksp_type="fgmres",
        pc_strategy="asm_restrict_overlap1_local_ilu0",
        evidence_status="closed_controlled_negative",
    ),
    "fgmres_dtn_trace_deflation": CondensedIterativeProfile(
        name="fgmres_dtn_trace_deflation",
        ksp_type="fgmres",
        pc_strategy=(
            "fixed_jacobi_plus_diagonal_lifted_dtn_trace_galerkin"
        ),
        relative_tolerance=1.0e-10,
        evidence_status="not_run_requires_formal_discriminator",
    ),
}

SUPPORTED_CONDENSED_ITERATIVE_PROFILES = tuple(_PROFILES)
PHYSICS_AWARE_PROFILE = "fgmres_dtn_trace_deflation"


def condensed_iterative_profile(
    name: str,
) -> CondensedIterativeProfile:
    """Return a typed profile or fail before a KSP is created."""

    try:
        return _PROFILES[str(name)]
    except KeyError as exc:
        raise ValueError(
            "unsupported condensed iterative profile "
            f"{name!r}; expected one of "
            f"{list(SUPPORTED_CONDENSED_ITERATIVE_PROFILES)}"
        ) from exc


def condensed_iterative_profile_contract(name: str) -> dict[str, Any]:
    """Return a JSON-safe provenance/qualification contract."""

    profile = condensed_iterative_profile(name)
    return {
        "schema_version": "task035b.condensed-iterative-profile-contract.v2",
        **asdict(profile),
        "configured_programmatically": True,
        "raw_petsc_options_accepted": False,
        "assembled_reduced_operator": True,
        "matrix_free": False,
        "formal_first_screen": {
            "minimum_unpreconditioned_residual_reduction_decades": 3.0,
            "terminal_explicit_reduced_relative_residual_max": 1.0e-3,
            "full_recovered_true_residual_required": True,
            "global_fine_sparse_direct_factor_nnz_required": 0,
            "swap_allowed": False,
        },
        "official_output_requires": {
            "positive_ksp_converged_reason": True,
            "full_explicit_true_residual_max": 1.0e-9,
        },
        "ordinary_default_changed": False,
    }


def configure_condensed_iterative_outer_ksp(
    ksp: PETSc.KSP,
    profile: CondensedIterativeProfile,
) -> None:
    """Configure the common outer contract without consulting PETSc options."""

    ksp.setType(profile.ksp_type)
    ksp.setGMRESRestart(profile.restart)
    ksp.setTolerances(
        rtol=profile.relative_tolerance,
        atol=profile.absolute_tolerance,
        divtol=1.0e8,
        max_it=profile.maximum_iterations,
    )
    ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
    ksp.setInitialGuessNonzero(False)
    ksp.setConvergenceHistory(
        length=profile.maximum_iterations + 1,
        reset=True,
    )


class _ComplexDiagonalSmoother:
    """Fixed linear complex Jacobi action with an explicit diagonal gate."""

    def __init__(
        self,
        operator: PETSc.Mat,
        *,
        relative_zero_tolerance: float = 1.0e-14,
    ) -> None:
        diagonal = operator.createVecLeft()
        operator.getDiagonal(diagonal)
        values = diagonal.getArray(readonly=True)
        comm = operator.getComm().tompi4py()
        local_maximum = float(np.max(np.abs(values), initial=0.0))
        global_maximum = float(
            comm.allreduce(local_maximum, op=MPI.MAX)
        )
        if not math.isfinite(global_maximum) or global_maximum <= 0.0:
            diagonal.destroy()
            raise RuntimeError(
                "DtN-trace deflation requires a finite nonzero operator "
                "diagonal"
            )
        threshold = relative_zero_tolerance * global_maximum
        local_minimum = float(np.min(np.abs(values), initial=global_maximum))
        global_minimum = float(
            comm.allreduce(local_minimum, op=MPI.MIN)
        )
        if global_minimum <= threshold:
            diagonal.destroy()
            raise RuntimeError(
                "DtN-trace deflation refuses a singular/near-zero Jacobi "
                f"diagonal: minimum={global_minimum:.6e}, "
                f"threshold={threshold:.6e}"
            )
        inverse = operator.createVecRight()
        inverse.getArray()[:] = PETSc.ScalarType(1.0) / values
        diagonal.destroy()
        self._inverse = inverse
        self.minimum_diagonal_magnitude = global_minimum
        self.maximum_diagonal_magnitude = global_maximum
        self.apply_count = 0
        self._destroyed = False

    def solve(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        target.pointwiseMult(self._inverse, source)
        self.apply_count += 1

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._inverse.destroy()
        self._destroyed = True


def build_diagonal_lifted_dtn_trace_basis(
    operator: PETSc.Mat,
    *,
    trace_rows: int,
    dtn_auxiliary_rows: int,
) -> tuple[tuple[SparseCoarseVector, ...], dict[str, Any]]:
    """Build normalized sparse ``[-diag(A_tt)^-1 B_j; e_j]`` vectors.

    Each returned :class:`SparseCoarseVector` stores only the part owned by the
    calling rank.  Global normalization is collective.  The unique auxiliary
    unit entry makes the port-mode identity explicit and prevents a zero basis
    vector even when one mode has a very small trace coupling.
    """

    rows, cols = operator.getSize()
    trace_rows = int(trace_rows)
    dtn_auxiliary_rows = int(dtn_auxiliary_rows)
    if rows != cols:
        raise ValueError("DtN-trace deflation requires a square operator")
    if trace_rows <= 0 or dtn_auxiliary_rows <= 0:
        raise ValueError(
            "DtN-trace deflation requires positive trace and auxiliary rows"
        )
    if trace_rows + dtn_auxiliary_rows != rows:
        raise ValueError(
            "trace_rows + dtn_auxiliary_rows must equal the operator size"
        )

    comm = operator.getComm().tompi4py()
    ownership_start, ownership_end = operator.getOwnershipRange()
    diagonal = operator.createVecLeft()
    operator.getDiagonal(diagonal)
    diagonal_values = np.asarray(
        diagonal.getArray(readonly=True),
        dtype=PETSc.ScalarType,
    )
    local_diagonal_maximum = float(
        np.max(np.abs(diagonal_values), initial=0.0)
    )
    diagonal_maximum = float(
        comm.allreduce(local_diagonal_maximum, op=MPI.MAX)
    )
    diagonal_threshold = max(
        np.finfo(float).tiny,
        diagonal_maximum * 1.0e-14,
    )

    indices_by_mode: list[list[int]] = [
        [] for _ in range(dtn_auxiliary_rows)
    ]
    values_by_mode: list[list[complex]] = [
        [] for _ in range(dtn_auxiliary_rows)
    ]
    local_trace_coupling_nnz = 0
    for global_row in range(ownership_start, ownership_end):
        local_row = global_row - ownership_start
        if global_row < trace_rows:
            columns, values = operator.getRow(global_row)
            auxiliary_mask = np.asarray(columns) >= trace_rows
            if np.any(auxiliary_mask):
                diagonal_value = complex(diagonal_values[local_row])
                if abs(diagonal_value) <= diagonal_threshold:
                    diagonal.destroy()
                    raise RuntimeError(
                        "a DtN-coupled trace row has a singular/near-zero "
                        f"diagonal: row={global_row}, "
                        f"|diag|={abs(diagonal_value):.6e}, "
                        f"threshold={diagonal_threshold:.6e}"
                    )
                for column, value in zip(
                    np.asarray(columns)[auxiliary_mask],
                    np.asarray(values)[auxiliary_mask],
                    strict=True,
                ):
                    if complex(value) == 0.0:
                        continue
                    mode = int(column) - trace_rows
                    indices_by_mode[mode].append(global_row)
                    values_by_mode[mode].append(
                        -complex(value) / diagonal_value
                    )
                    local_trace_coupling_nnz += 1
        else:
            mode = global_row - trace_rows
            indices_by_mode[mode].append(global_row)
            values_by_mode[mode].append(1.0 + 0.0j)
    diagonal.destroy()

    local_norm_squared = np.asarray(
        [
            float(np.vdot(values, values).real)
            for values in (
                np.asarray(mode_values, dtype=np.complex128)
                for mode_values in values_by_mode
            )
        ],
        dtype=np.float64,
    )
    global_norm_squared = np.empty_like(local_norm_squared)
    comm.Allreduce(
        local_norm_squared,
        global_norm_squared,
        op=MPI.SUM,
    )
    if (
        not np.all(np.isfinite(global_norm_squared))
        or np.any(global_norm_squared <= 0.0)
    ):
        raise RuntimeError(
            "DtN-trace coarse basis contains a non-finite or zero mode"
        )

    basis: list[SparseCoarseVector] = []
    local_normalized_norm_squared = np.zeros(
        dtn_auxiliary_rows,
        dtype=np.float64,
    )
    for mode, (indices, values) in enumerate(
        zip(indices_by_mode, values_by_mode, strict=True)
    ):
        scale = math.sqrt(float(global_norm_squared[mode]))
        normalized = np.asarray(values, dtype=PETSc.ScalarType) / scale
        local_normalized_norm_squared[mode] = float(
            np.vdot(normalized, normalized).real
        )
        basis.append(
            SparseCoarseVector(
                indices=np.asarray(indices, dtype=PETSc.IntType),
                values=normalized,
                slab=mode,
                eigenvalue=float("nan"),
                eigenpair_residual=0.0,
            )
        )
    normalized_norm_squared = np.empty_like(
        local_normalized_norm_squared
    )
    comm.Allreduce(
        local_normalized_norm_squared,
        normalized_norm_squared,
        op=MPI.SUM,
    )
    local_basis_nnz = sum(vector.indices.size for vector in basis)
    global_basis_nnz = int(
        comm.allreduce(local_basis_nnz, op=MPI.SUM)
    )
    trace_coupling_nnz = int(
        comm.allreduce(local_trace_coupling_nnz, op=MPI.SUM)
    )
    audit = {
        "schema_version": "task035b.dtn-trace-coarse-basis.v1",
        "basis_kind": (
            "diagonal_lifted_physical_dtn_auxiliary_trace_modes"
        ),
        "formula": "w_j=[-diag(A_tt)^(-1) B_j; e_j]",
        "trace_rows": trace_rows,
        "dtn_auxiliary_rows": dtn_auxiliary_rows,
        "basis_dimension": dtn_auxiliary_rows,
        "trace_coupling_nnz": trace_coupling_nnz,
        "basis_nnz": global_basis_nnz,
        "basis_dense_equivalent_entries": rows * dtn_auxiliary_rows,
        "basis_normalization_max_abs_error": float(
            np.max(np.abs(normalized_norm_squared - 1.0), initial=0.0)
        ),
        "inactive_or_unrelated_rows_added": False,
        "global_fine_sparse_factor_created": False,
        "ordinary_default_changed": False,
    }
    return tuple(basis), audit


class DtnTraceDeflationPc:
    """Fixed two-level PC for the Review-V2 minimal discriminator."""

    def __init__(
        self,
        operator: PETSc.Mat,
        *,
        trace_rows: int,
        dtn_auxiliary_rows: int,
    ) -> None:
        started = time.perf_counter()
        basis, basis_audit = build_diagonal_lifted_dtn_trace_basis(
            operator,
            trace_rows=trace_rows,
            dtn_auxiliary_rows=dtn_auxiliary_rows,
        )
        smoother = _ComplexDiagonalSmoother(operator)
        try:
            core = SparseGalerkinTwoLevelPc(
                operator,
                smoother,
                basis,
                post_smooth=True,
                post_smooth_weight=1.0,
                condition_limit=1.0e12,
            )
        except Exception:
            smoother.destroy()
            raise
        self._core = core
        self._smoother = smoother
        self._basis_audit = basis_audit
        self._setup_seconds = float(time.perf_counter() - started)
        self._destroyed = False

    def apply(
        self,
        pc: PETSc.PC,
        source: PETSc.Vec,
        target: PETSc.Vec,
    ) -> None:
        self._core.apply(pc, source, target)

    @property
    def diagnostics(self) -> dict[str, Any]:
        dimension = int(self._basis_audit["basis_dimension"])
        dense_entries = dimension * dimension
        return {
            "schema_version": "task035b.dtn-trace-deflation-pc.v1",
            "strategy": (
                "fixed_jacobi_pre_and_post_smoothing_plus_exact_"
                "dtn_trace_galerkin_correction"
            ),
            "basis": self._basis_audit,
            "setup_seconds": self._setup_seconds,
            "coarse_dimension": dimension,
            "coarse_rank": int(self._core.coarse_rank),
            "coarse_condition": float(self._core.coarse_condition),
            "coarse_smallest_singular_value": float(
                self._core.coarse_smallest_singular_value
            ),
            "coarse_largest_singular_value": float(
                self._core.coarse_largest_singular_value
            ),
            "coarse_dense_lu_active": True,
            "coarse_dense_matrix_entries": dense_entries,
            "coarse_dense_matrix_bytes": dense_entries * 16,
            "coarse_dense_lu_storage_semantics": (
                "small replicated SciPy complex LU; not a global fine sparse "
                "factor and not included in global_direct_factor_nnz"
            ),
            "basis_storage_bytes": int(self._core.basis_storage_bytes),
            "smoother": "fixed_complex_jacobi",
            "minimum_diagonal_magnitude": (
                self._smoother.minimum_diagonal_magnitude
            ),
            "maximum_diagonal_magnitude": (
                self._smoother.maximum_diagonal_magnitude
            ),
            "preconditioner_apply_count": int(self._core.apply_count),
            "preconditioner_apply_seconds": float(
                self._core.apply_elapsed_s
            ),
            "smoother_apply_count": int(self._smoother.apply_count),
            "smoother_apply_seconds": float(
                self._core.smoother_elapsed_s
            ),
            "coarse_apply_seconds": float(self._core.coarse_elapsed_s),
            "global_fine_sparse_factor_nnz": 0,
            "local_sparse_ilu_active": False,
            "mumps_symbolic_or_numeric_created": False,
            "fine_operator_factor_free": True,
            "strictly_factorless_preconditioner": False,
            "strictly_factorless_reason": (
                "an explicitly inventoried small dense Galerkin coarse LU is "
                "retained"
            ),
            "ordinary_default_changed": False,
        }

    def destroy(self, _pc: PETSc.PC | None = None) -> None:
        if self._destroyed:
            return
        self._core.destroy()
        self._smoother.destroy()
        self._destroyed = True


def configure_dtn_trace_deflation_pc(
    ksp: PETSc.KSP,
    operator: PETSc.Mat,
    *,
    trace_rows: int,
    dtn_auxiliary_rows: int,
) -> DtnTraceDeflationPc:
    """Attach the explicit physics-aware Python PC to an already typed KSP."""

    context = DtnTraceDeflationPc(
        operator,
        trace_rows=trace_rows,
        dtn_auxiliary_rows=dtn_auxiliary_rows,
    )
    pc = ksp.getPC()
    pc.setType(PETSc.PC.Type.PYTHON)
    pc.setPythonContext(context)
    return context


__all__ = [
    "CondensedIterativeProfile",
    "DtnTraceDeflationPc",
    "PHYSICS_AWARE_PROFILE",
    "SUPPORTED_CONDENSED_ITERATIVE_PROFILES",
    "build_diagonal_lifted_dtn_trace_basis",
    "condensed_iterative_profile",
    "condensed_iterative_profile_contract",
    "configure_condensed_iterative_outer_ksp",
    "configure_dtn_trace_deflation_pc",
]
