"""Thin static-condensation adapter for one Hybrid local-FE block.

The numerical Schur construction, left/right vector reductions, cell-interior
bilinear, field recovery, and true-residual action remain owned by
``hcurl_assembly_time_condensation`` and ``dtn_port_3d``.  This module only
binds those qualified operations to the metadata needed by a Hybrid terminal
block.

Construction is explicit and fail-closed.  Importing this module changes no
default, and the binding accepts only the already-qualified
``assembly_time_static_condensed`` backend.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
from petsc4py import PETSc

from ..common.config_3d import (
    ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
)

from .dtn_port_3d import (
    _assembly_time_full_operator_residual,
    _assign_fe_solution_from_assembly_time_condensation,
)
from .hcurl_assembly_time_condensation import (
    AssemblyTimeCondensedSystem,
    cell_interior_schur_bilinear,
    condense_unconstrained_vector_to_active_trace,
    project_mpc_vector_to_active_trace,
)


HybridSurfaceVectorRole = Literal["load_column", "row_functional"]


@dataclass(frozen=True)
class HybridLocalReductionMetadata:
    """Stable row accounting for one physically reduced local-FE block."""

    assembly_backend_requested: str
    assembly_backend_actual: str
    full_fe_rows: int
    trace_rows_before_constraints: int
    active_trace_rows: int
    cell_interior_rows: int
    floquet_slave_rows: int
    external_auxiliary_rows: int
    local_algebra_rows: int
    full_global_matrix_allocated: bool
    full_trace_matrix_allocated: bool
    ordinary_default_changed: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-ready provenance without exposing PETSc objects."""

        return {
            "schema_version": (
                "myfenics.hybrid-local-static-condensation-metadata.v1"
            ),
            "status": "hybrid_local_static_condensation_bound",
            "assembly_backend_requested": self.assembly_backend_requested,
            "assembly_backend_actual": self.assembly_backend_actual,
            "full_fe_rows": self.full_fe_rows,
            "trace_rows_before_constraints": (
                self.trace_rows_before_constraints
            ),
            "active_trace_rows": self.active_trace_rows,
            "cell_interior_rows": self.cell_interior_rows,
            "floquet_slave_rows": self.floquet_slave_rows,
            "external_auxiliary_rows": self.external_auxiliary_rows,
            "local_algebra_rows": self.local_algebra_rows,
            "full_global_matrix_allocated": (
                self.full_global_matrix_allocated
            ),
            "full_trace_matrix_allocated": (
                self.full_trace_matrix_allocated
            ),
            "ordinary_default_changed": self.ordinary_default_changed,
        }


@dataclass(frozen=True)
class HybridLocalRecoveredField:
    """Recovered physical field and its mandatory residual evidence."""

    electric_field: Any
    recovery_audit: dict[str, Any]
    full_operator_residual: dict[str, Any]


@dataclass(frozen=True)
class HybridLocalStaticCondensation:
    """Validated adapter around one assembly-time condensed local system.

    ``bilinear_form`` is the original full-space variational form and
    ``floquet_data`` owns its qualified MPC.  The adapter borrows every PETSc
    and DOLFINx object; lifecycle ownership stays with the caller.
    """

    condensed: AssemblyTimeCondensedSystem
    bilinear_form: Any
    floquet_data: Any
    metadata: HybridLocalReductionMetadata

    def __post_init__(self) -> None:
        _validate_binding(
            self.condensed,
            self.bilinear_form,
            self.floquet_data,
            self.metadata,
        )

    def reduce_surface_vector(
        self,
        full_vector: PETSc.Vec,
        *,
        role: HybridSurfaceVectorRole,
    ) -> PETSc.Vec:
        """Reduce one unconstrained surface vector with explicit semantics.

        ``load_column`` applies the right Schur reduction used by a traction
        column. ``row_functional`` applies the left reduction whose conjugate
        transpose is inserted as a modal projection row.
        """

        reduction_side = {
            "load_column": "right",
            "row_functional": "left",
        }.get(role)
        if reduction_side is None:
            raise ValueError(
                "Hybrid surface vector role must be 'load_column' or "
                "'row_functional'"
            )
        _require_vector_size(
            full_vector,
            self.metadata.full_fe_rows,
            label="unconstrained surface vector",
        )
        reduced = condense_unconstrained_vector_to_active_trace(
            self.condensed,
            full_vector,
            side=reduction_side,
        )
        expected = self.metadata.local_algebra_rows
        if reduced.getSize() != expected:
            reduced.destroy()
            raise RuntimeError(
                "Hybrid surface-vector reduction returned "
                f"{reduced.getSize()} rows; expected {expected}"
            )
        return reduced

    def interior_cross_bilinear(
        self,
        left_full_vector: PETSc.Vec,
        right_full_vector: PETSc.Vec,
    ) -> complex:
        """Return the eliminated ``left_i^H A_ii^-1 right_i`` term."""

        _require_vector_size(
            left_full_vector,
            self.metadata.full_fe_rows,
            label="left full-space surface vector",
        )
        _require_vector_size(
            right_full_vector,
            self.metadata.full_fe_rows,
            label="right full-space surface vector",
        )
        return cell_interior_schur_bilinear(
            self.condensed,
            left_full_vector,
            right_full_vector,
        )

    def interior_cross_block(
        self,
        left_full_vectors: tuple[PETSc.Vec, ...],
        right_full_vectors: tuple[PETSc.Vec, ...],
    ) -> np.ndarray:
        """Return all eliminated cross terms without changing their signs."""

        if not left_full_vectors or not right_full_vectors:
            raise ValueError(
                "Hybrid interior cross block requires non-empty vector sets"
            )
        return np.asarray(
            [
                [
                    self.interior_cross_bilinear(left, right)
                    for right in right_full_vectors
                ]
                for left in left_full_vectors
            ],
            dtype=np.complex128,
        )

    def reduce_tangential_surface_mpc_vector(
        self,
        full_mpc_vector: PETSc.Vec,
        *,
        eliminated_tolerance: float = 1.0e-12,
    ) -> PETSc.Vec:
        """Project a verified trace-only tangential surface vector.

        Hybrid interface projection and modal traction are pure tangential
        ``ds`` forms.  Cell-interior H(curl) basis functions have zero
        tangential trace, so their entries must vanish.  The input has already
        been assembled through the qualified Floquet MPC and therefore
        contains ``C^H``.  The helper verifies every eliminated interior/slave
        entry before dropping it; any nonzero volume-lifting contribution
        fails closed instead of silently taking this fast path.
        """

        _require_vector_size(
            full_mpc_vector,
            self.metadata.full_fe_rows,
            label="MPC tangential surface vector",
        )
        return project_mpc_vector_to_active_trace(
            self.condensed,
            full_mpc_vector,
            eliminated_tolerance=eliminated_tolerance,
        )

    def recover_and_audit(
        self,
        reduced_solution: PETSc.Vec,
        reduced_effective_rhs: PETSc.Vec,
        full_effective_rhs: PETSc.Vec,
    ) -> HybridLocalRecoveredField:
        """Recover cell interiors and audit every retained/eliminated equation.

        The effective RHS arguments are mandatory.  In a coupled Hybrid solve
        they must already include the solved external-DtN and internal-modal
        traction contributions; silently substituting the uncoupled base RHS
        would make interior recovery algebraically incomplete.
        """

        algebra_rows = self.metadata.local_algebra_rows
        _require_vector_size(
            reduced_solution,
            algebra_rows,
            label="reduced Hybrid local solution",
        )
        _require_vector_size(
            reduced_effective_rhs,
            algebra_rows,
            label="reduced effective Hybrid RHS",
        )
        _require_vector_size(
            full_effective_rhs,
            self.metadata.full_fe_rows,
            label="full effective Hybrid RHS",
        )
        electric_field, embedded_fe_solution, recovery = (
            _assign_fe_solution_from_assembly_time_condensation(
                reduced_solution,
                self.condensed,
                self.floquet_data,
                full_effective_rhs,
            )
        )
        try:
            residual = _assembly_time_full_operator_residual(
                self.bilinear_form,
                self.floquet_data,
                embedded_fe_solution,
                self.condensed.matrix,
                reduced_effective_rhs,
                reduced_solution,
                self.condensed,
                full_effective_rhs,
            )
        except Exception:
            # The fem.Function returned above owns its own data.  The
            # temporary full-space PETSc vector is independent and must not
            # leak when residual evaluation fails.
            embedded_fe_solution.destroy()
            raise
        embedded_fe_solution.destroy()
        recovery_audit = {
            **recovery,
            "assembly_backend_actual": (
                self.metadata.assembly_backend_actual
            ),
            "effective_rhs_includes_coupled_surface_actions_required": True,
            "ordinary_default_changed": False,
        }
        residual_audit = {
            **residual,
            "assembly_backend_actual": (
                self.metadata.assembly_backend_actual
            ),
            "effective_rhs_includes_coupled_surface_actions_required": True,
            "ordinary_default_changed": False,
        }
        return HybridLocalRecoveredField(
            electric_field=electric_field,
            recovery_audit=recovery_audit,
            full_operator_residual=residual_audit,
        )


def bind_hybrid_local_static_condensation(
    *,
    condensed: AssemblyTimeCondensedSystem,
    bilinear_form: Any,
    floquet_data: Any,
    assembly_backend_requested: str,
    assembly_backend_actual: str,
    external_auxiliary_rows: int,
) -> HybridLocalStaticCondensation:
    """Bind a previously built condensed system to one Hybrid local block."""

    requested = str(assembly_backend_requested).strip().lower()
    actual = str(assembly_backend_actual).strip().lower()
    if actual != ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND:
        raise ValueError(
            "Hybrid local static-condensation binding requires actual backend "
            f"{ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND!r}; got {actual!r}"
        )
    if requested != ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND:
        raise ValueError(
            "Hybrid local static condensation must be explicitly requested; "
            f"got {requested!r}"
        )
    external_auxiliary_rows = int(external_auxiliary_rows)
    if external_auxiliary_rows < 0:
        raise ValueError("external auxiliary row count must be non-negative")
    if external_auxiliary_rows != int(condensed.appended_rows):
        raise ValueError(
            "Hybrid external auxiliary rows differ from the condensed "
            "appended-row contract"
        )
    metadata = HybridLocalReductionMetadata(
        assembly_backend_requested=requested,
        assembly_backend_actual=actual,
        full_fe_rows=int(condensed.full_rows),
        trace_rows_before_constraints=int(condensed.trace_rows),
        active_trace_rows=int(condensed.active_rows),
        cell_interior_rows=int(condensed.interior_rows),
        floquet_slave_rows=int(condensed.trace_constraints.slave_rows),
        external_auxiliary_rows=external_auxiliary_rows,
        local_algebra_rows=int(
            condensed.active_rows + external_auxiliary_rows
        ),
        full_global_matrix_allocated=False,
        full_trace_matrix_allocated=False,
        ordinary_default_changed=False,
    )
    return HybridLocalStaticCondensation(
        condensed=condensed,
        bilinear_form=bilinear_form,
        floquet_data=floquet_data,
        metadata=metadata,
    )


def _require_vector_size(
    vector: PETSc.Vec,
    expected: int,
    *,
    label: str,
) -> None:
    observed = int(vector.getSize())
    if observed != int(expected):
        raise ValueError(
            f"{label} has {observed} rows; expected {int(expected)}"
        )


def _validate_binding(
    condensed: AssemblyTimeCondensedSystem,
    bilinear_form: Any,
    floquet_data: Any,
    metadata: HybridLocalReductionMetadata,
) -> None:
    if bilinear_form is None:
        raise ValueError(
            "Hybrid local static condensation requires the full bilinear form"
        )
    if floquet_data is None or getattr(floquet_data, "mpc", None) is None:
        raise ValueError(
            "Hybrid local static condensation requires qualified Floquet MPC"
        )
    if (
        metadata.assembly_backend_requested
        != ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND
        or metadata.assembly_backend_actual
        != ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND
    ):
        raise ValueError(
            "Hybrid local reduction metadata does not describe an explicit "
            "assembly-time static-condensation request"
        )
    if metadata.ordinary_default_changed:
        raise ValueError(
            "Hybrid local static condensation cannot change the ordinary "
            "assembly default"
        )
    if condensed.full_rows != (
        condensed.trace_rows + condensed.interior_rows
    ):
        raise RuntimeError("Hybrid local FE row partition does not close")
    if condensed.active_rows != condensed.trace_constraints.active_rows:
        raise RuntimeError(
            "Hybrid local active trace rows disagree with Floquet constraints"
        )
    if condensed.trace_rows != (
        condensed.active_rows + condensed.trace_constraints.slave_rows
    ):
        raise RuntimeError(
            "Hybrid local trace/Floquet row partition does not close"
        )
    expected_metadata = {
        "full_fe_rows": int(condensed.full_rows),
        "trace_rows_before_constraints": int(condensed.trace_rows),
        "active_trace_rows": int(condensed.active_rows),
        "cell_interior_rows": int(condensed.interior_rows),
        "floquet_slave_rows": int(
            condensed.trace_constraints.slave_rows
        ),
        "external_auxiliary_rows": int(condensed.appended_rows),
    }
    mismatches = [
        f"{name}={getattr(metadata, name)} expected={expected}"
        for name, expected in expected_metadata.items()
        if int(getattr(metadata, name)) != expected
    ]
    if mismatches:
        raise RuntimeError(
            "Hybrid local reduction metadata differs from the condensed "
            "system: " + "; ".join(mismatches)
        )
    expected_rows = condensed.active_rows + condensed.appended_rows
    if condensed.matrix.getSize() != (expected_rows, expected_rows):
        raise RuntimeError(
            "Hybrid local condensed matrix does not contain exactly active "
            "trace plus appended auxiliary rows"
        )
    if metadata.local_algebra_rows != expected_rows:
        raise RuntimeError(
            "Hybrid local reduction metadata has inconsistent algebra rows"
        )
    audit = condensed.build_audit
    required_false = (
        "full_global_matrix_allocated",
        "full_trace_matrix_allocated",
        "inactive_max_p_rows_retained_in_matrix",
    )
    failed_false = [
        name for name in required_false if audit.get(name) is not False
    ]
    if failed_false:
        raise ValueError(
            "Hybrid local condensed system lacks physical-reduction evidence: "
            + ", ".join(failed_false)
        )
    if audit.get("axis_aligned_affine_geometry_verified") is not True:
        raise ValueError(
            "Hybrid local static condensation requires verified axis-aligned "
            "affine hexahedra"
        )
    mpc_space = floquet_data.mpc.function_space
    dofmap = mpc_space.dofmap
    mpc_full_rows = int(
        dofmap.index_map.size_global * dofmap.index_map_bs
    )
    if mpc_full_rows != condensed.full_rows:
        raise ValueError(
            "Hybrid local Floquet MPC and condensed FE spaces have different "
            "global row counts"
        )
    if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
        raise TypeError(
            "Hybrid local static condensation requires PETSc complex128"
        )


__all__ = [
    "HybridLocalRecoveredField",
    "HybridLocalReductionMetadata",
    "HybridLocalStaticCondensation",
    "HybridSurfaceVectorRole",
    "bind_hybrid_local_static_condensation",
]
