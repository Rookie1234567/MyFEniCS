from __future__ import annotations

import copy
import csv
import hashlib
import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

import dolfinx_mpc
import numpy as np
import ufl
from dolfinx import fem
from dolfinx.fem import petsc as fem_petsc
from dolfinx.la.petsc import _ghost_update, create_vector
from mpi4py import MPI
from petsc4py import PETSc

from ..common.config_3d import (
    ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND,
    SimulationConfig3D,
    qualify_stage4_full3d_assembly_backend,
    resolve_stage4_full3d_assembly_backend,
)
from ..common.modes_3d import (
    PortMode3D,
    incident_power_3d,
    mode_power,
    outgoing_port_modes_3d,
)
from ..constraints.floquet_3d import DoubleFloquet3DData
from .common_3d_solve import (
    DirectSolveFailure,
    _petsc_factor_inventory,
    _petsc_matrix_stats,
)
from .common_3d_utils import _write_progress_event
from .condensed_dtn import (
    DtnBlockAssembler,
    MatrixFreeDtnProbe,
    PetscCondensedBlocks,
    combine_petsc_augmented_solution,
    create_matrix_free_augmented_operator,
)
from .condensed_reference_preflight import CondensedPreflightExit
from .fullspace_surface_legendre import (
    Q160SixLaneWeightedMomentWorkspace,
    SURFACE_COMPONENT_PAIR_BACKEND,
    SURFACE_WEIGHTED_MOMENT_CONTRACTION,
    SURFACE_WEIGHTED_MOMENT_CONTRACTION_SIX_LANE,
)
from .hcurl_assembly_time_condensation import (
    AssemblyTimeCondensedSystem,
    build_unconstrained_assembly_time_condensation,
    cell_interior_schur_bilinear,
    condense_unconstrained_vector_to_active_trace,
    owned_active_support_groups,
    recover_owned_cell_interiors,
)
from .hcurl_cell_static_condensation import (
    build_explicit_cell_static_condensation,
    build_floquet_independent_trace_system,
    expand_floquet_independent_trace_solution,
    owned_hcurl_cell_interior_dofs,
    recover_full_solution,
)
from .hcurl_variable_p_reduction import (
    VariablePAssemblyTimeReduction,
    VariablePRecoveredSolution,
    build_variable_p_assembly_time_reduction,
)
from .mpc_form_action import MpcFormActionContext
from .solve_vector_maxwell import _json_default
from .static_local_schur_action import create_static_local_schur_action

DTN_PORT_MODAL_POWER_SOURCE = "dtn_port_modal_amplitudes"
DTN_PORT_MODAL_REFERENCE = "top=physical_z_max; bottom=physical_z_min; bottom lossy power uses boundary-plane phase attenuation"


class Stage4VariablePLiveObserverError(RuntimeError):
    """Collective failure from a controlled live variable-p observer."""


@dataclass(frozen=True)
class Stage4VariablePLiveView:
    """Callback-only borrowed view of one solved variable-p Stage-4 system.

    A callback may perform matched collective transpose/backsolves through
    ``ksp``.  It must not change its operators/options, destroy or retain any
    borrowed PETSc object, or modify ``A``, ``b``, ``x``, ``field``, geometry,
    constraints, or the read-only evidence mappings.  All ranks must execute
    the same collective phases; arbitrary rank-divergent callback failures
    cannot be recovered once another rank has entered a PETSc collective.
    """

    field: Any
    mesh_data: Any
    config: SimulationConfig3D
    floquet_data: DoubleFloquet3DData
    A: PETSc.Mat
    b: PETSc.Vec
    x: PETSc.Vec
    ksp: PETSc.KSP
    reduction: VariablePAssemblyTimeReduction
    recovered: VariablePRecoveredSolution
    goal_context: Mapping[str, Any]
    port_metrics: Mapping[str, Any]
    port_operator_audit: Mapping[str, Any]
    full_active_residual: Mapping[str, Any]
    primal_solver_telemetry: Mapping[str, Any]


@dataclass(frozen=True)
class Stage4ExternalLinearSolverRequest:
    """Borrowed system; only the owner callback may release its assembled A."""

    A: PETSc.Mat
    b: PETSc.Vec
    n_fe: int
    n_aux: int
    static_condensed_system: AssemblyTimeCondensedSystem
    function_space: Any
    config: SimulationConfig3D
    floquet_data: DoubleFloquet3DData
    release_assembled_matrix: Callable[[], None] | None = None
    mesh_data: Any = None
    full_rhs: PETSc.Vec | None = None
    incident_traction_quadrature_degree: int | None = None


@dataclass(frozen=True)
class Stage4ExternalLinearSolverSnapshot:
    """Transferred solution and fixed scalar evidence from an external port."""

    x: PETSc.Vec
    converged_reason: int
    iterations: int
    reported_relative_residual: float | None
    condensed_true_residual: float | None
    full_augmented_true_residual: float | None
    ksp_type: str
    pc_type: str
    residual_limit: float
    no_global_factor: bool
    solver_profile: str = "assembled"
    assembled_matrix_released_before_solve: bool = False
    reduced_residual_norm: float | None = None


@dataclass(frozen=True)
class Stage4NeverMaterializedLinearSolverRequest:
    """Borrowed action-only DtN system for one explicit solver callback."""

    operator: PETSc.Mat
    b: PETSc.Vec
    n_fe: int
    n_aux: int
    static_condensed_system: AssemblyTimeCondensedSystem
    fine_operator: PETSc.Mat
    blocks: PetscCondensedBlocks
    function_space: Any
    config: SimulationConfig3D
    floquet_data: DoubleFloquet3DData


@dataclass(frozen=True)
class Stage4NeverMaterializedLinearSolverPort:
    """Typed opt-in tag for a callback that consumes the action-only system."""

    callback: Callable[
        [Stage4NeverMaterializedLinearSolverRequest],
        Stage4ExternalLinearSolverSnapshot,
    ]

    def __call__(
        self,
        request: Stage4NeverMaterializedLinearSolverRequest,
    ) -> Stage4ExternalLinearSolverSnapshot:
        return self.callback(request)


def _external_snapshot_allows_official_rta(
    snapshot: Stage4ExternalLinearSolverSnapshot,
    full_fe_relative_residual: float | None,
) -> bool:
    residuals = (
        snapshot.reported_relative_residual,
        snapshot.condensed_true_residual,
        snapshot.full_augmented_true_residual,
        full_fe_relative_residual,
    )
    return (
        snapshot.converged_reason > 0
        and snapshot.no_global_factor
        and all(
            value is not None
            and np.isfinite(float(value))
            and float(value) <= snapshot.residual_limit
            for value in residuals
        )
    )


def _dispatch_external_linear_solver(
    A_aug: PETSc.Mat,
    b_aug: PETSc.Vec,
    *,
    n_fe: int,
    n_aux: int,
    static_condensed_system: AssemblyTimeCondensedSystem,
    function_space: Any,
    config: SimulationConfig3D,
    floquet_data: DoubleFloquet3DData,
    release_assembled_matrix: Callable[[], None] | None = None,
    mesh_data: Any = None,
    full_rhs: PETSc.Vec | None = None,
    incident_traction_quadrature_degree: int | None = None,
    port: Callable[
        [Stage4ExternalLinearSolverRequest], Stage4ExternalLinearSolverSnapshot
    ],
) -> Stage4ExternalLinearSolverSnapshot:
    augmented_size = int(A_aug.getSize()[0])
    augmented_ownership = A_aug.getOwnershipRange()
    snapshot = port(
        Stage4ExternalLinearSolverRequest(
            A=A_aug,
            b=b_aug,
            n_fe=int(n_fe),
            n_aux=int(n_aux),
            static_condensed_system=static_condensed_system,
            function_space=function_space,
            config=config,
            floquet_data=floquet_data,
            release_assembled_matrix=release_assembled_matrix,
            mesh_data=mesh_data,
            full_rhs=full_rhs,
            incident_traction_quadrature_degree=incident_traction_quadrature_degree,
        )
    )
    if not isinstance(snapshot, Stage4ExternalLinearSolverSnapshot):
        raise TypeError("external linear-solver port must return its snapshot type")
    if not snapshot.no_global_factor:
        raise ValueError(
            "external linear-solver snapshot must certify no_global_factor"
        )
    if (
        snapshot.x.getSize() != augmented_size
        or snapshot.x.getOwnershipRange() != augmented_ownership
    ):
        raise ValueError("external solver x must match finalized augmented ownership")
    return snapshot


def _readonly_goal_context(
    goal_context: Mapping[str, Any],
) -> Mapping[str, Any]:
    copied = dict(goal_context)
    modes = copy.deepcopy(tuple(copied["modes"]))
    for mode in modes:
        for attribute in ("e_vector", "k_vector", "h_vector"):
            getattr(mode, attribute).setflags(write=False)
    copied["modes"] = modes
    for key in (
        "auxiliary_values",
        "incident_projections",
        "auxiliary_coordinate_scales",
    ):
        if key not in copied:
            continue
        values = np.asarray(copied[key], dtype=np.complex128).copy()
        values.setflags(write=False)
        copied[key] = values
    return MappingProxyType(copied)


def _deep_readonly_copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _deep_readonly_copy(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_deep_readonly_copy(item) for item in value)
    if isinstance(value, np.ndarray):
        copied = np.asarray(value).copy()
        copied.setflags(write=False)
        return copied
    return copy.deepcopy(value)


def _update_evidence_digest_array(
    digest: Any,
    name: str,
    values: Any,
    *,
    dtype: np.dtype[Any],
) -> None:
    array = np.ascontiguousarray(np.asarray(values), dtype=dtype)
    digest.update(name.encode("ascii"))
    digest.update(b"\0")
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(b"\0")
    digest.update(np.asarray(array.shape, dtype=np.dtype("<i8")).tobytes())
    digest.update(array.tobytes(order="C"))


def _update_evidence_digest_sparse(
    digest: Any,
    name: str,
    rows: Any,
    values: Any,
) -> None:
    canonical_rows = np.asarray(rows, dtype=np.int64)
    canonical_values = np.asarray(values, dtype=np.complex128)
    if canonical_rows.shape != canonical_values.shape:
        raise ValueError("sparse evidence rows and values are misaligned")
    order = np.argsort(canonical_rows, kind="stable")
    _update_evidence_digest_array(
        digest,
        f"{name}.rows",
        canonical_rows[order],
        dtype=np.dtype("<i8"),
    )
    _update_evidence_digest_array(
        digest,
        f"{name}.values",
        canonical_values[order],
        dtype=np.dtype("<c16"),
    )


def _partition_bound_evidence_sha256(
    communicator: MPI.Intracomm,
    *,
    namespace: str,
    local_sha256: str,
) -> str:
    rank_hashes = communicator.allgather(
        {
            "rank": int(communicator.rank),
            "sha256": str(local_sha256),
        }
    )
    rank_hashes.sort(key=lambda row: int(row["rank"]))
    if [int(row["rank"]) for row in rank_hashes] != list(range(communicator.size)):
        raise RuntimeError("partition evidence does not cover MPI ranks")
    digest = hashlib.sha256()
    digest.update(namespace.encode("ascii"))
    digest.update(b"\0")
    digest.update(
        json.dumps(
            rank_hashes,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    )
    return digest.hexdigest()


def _variable_p_port_operator_audit(
    timing_details: Mapping[str, Any],
) -> dict[str, Any]:
    """Freeze the trace-only DtN invariance required by nested-p DWR."""

    def valid_sha256(value: Any) -> bool:
        return bool(
            isinstance(value, str)
            and len(value) == 64
            and all(character in "0123456789abcdef" for character in value)
        )

    functional_count = timing_details.get(
        "stage4_dtn_variable_p_trace_functional_count"
    )
    removed_max = timing_details.get("stage4_dtn_variable_p_removed_interior_max_abs")
    removed_over_threshold_max = timing_details.get(
        "stage4_dtn_variable_p_removed_interior_over_threshold_max"
    )
    acceptance_threshold_max = timing_details.get(
        "stage4_dtn_variable_p_acceptance_threshold_max_abs"
    )
    trace_only = (
        timing_details.get("stage4_dtn_variable_p_trace_only_gate_pass") is True
    )
    auxiliary_columns = timing_details.get(
        "stage4_dtn_variable_p_auxiliary_interior_columns_allocated"
    )
    operator_sha256 = timing_details.get(
        "stage4_dtn_trace_only_external_operator_sha256"
    )
    rhs_sha256 = timing_details.get("stage4_dtn_trace_only_external_rhs_sha256")
    base_rhs_norm = timing_details.get("stage4_dtn_trace_only_base_reduced_rhs_norm")
    checks = {
        "trace_functionals_present": (
            isinstance(functional_count, int) and functional_count > 0
        ),
        "trace_only_gate": trace_only,
        "removed_interior_is_qualified_roundoff": (
            isinstance(removed_max, (int, float))
            and np.isfinite(float(removed_max))
            and 0.0 <= float(removed_max)
            and isinstance(
                removed_over_threshold_max,
                (int, float),
            )
            and np.isfinite(float(removed_over_threshold_max))
            and 0.0 <= float(removed_over_threshold_max) <= 1.0
            and isinstance(
                acceptance_threshold_max,
                (int, float),
            )
            and np.isfinite(float(acceptance_threshold_max))
            and 0.0 < float(acceptance_threshold_max)
        ),
        "no_auxiliary_interior_columns": auxiliary_columns is False,
        "external_operator_content_hash": valid_sha256(operator_sha256),
        "external_rhs_content_hash": valid_sha256(rhs_sha256),
        "zero_volume_base_rhs": (
            isinstance(base_rhs_norm, (int, float))
            and np.isfinite(float(base_rhs_norm))
            and 0.0 <= float(base_rhs_norm) <= 5.0e-13
        ),
    }
    return {
        "schema_version": ("task035d.variable-p-trace-only-port-operator.v1"),
        "pass": all(checks.values()),
        "checks": checks,
        "trace_functional_count": functional_count,
        "removed_active_interior_max_abs": removed_max,
        "removed_active_interior_over_threshold_max": (removed_over_threshold_max),
        "acceptance_threshold_max_abs": acceptance_threshold_max,
        "roundoff_gate_semantics": (
            "each functional is checked against max(1e-12, "
            "5e-12 * active_trace_max_abs) before its interior entries "
            "are zeroed; the reported ratio is the maximum of "
            "removed_max/acceptance_threshold over all functionals"
        ),
        "auxiliary_interior_columns_allocated": auxiliary_columns,
        "external_operator_content_sha256": operator_sha256,
        "external_rhs_content_sha256": rhs_sha256,
        "base_reduced_rhs_l2_norm": base_rhs_norm,
        "content_identity_is_partition_bound": True,
        "content_identity_requires_same_mpi_ownership": True,
        "invariance_contract": (
            "for one clean source SHA, identical geometry, trace "
            "constraints, modes, Floquet phases, incident projections, "
            "and auxiliary coordinates imply identical DtN/port/aux "
            "operator and exterior-RHS actions when every surface "
            "functional is trace-only and auxiliary-to-interior columns "
            "are absent"
        ),
        "interior_degree_may_affect_port_operator": False,
    }


def _ksp_configuration_signature(ksp: PETSc.KSP) -> tuple[Any, ...]:
    operator, preconditioning_operator = ksp.getOperators()
    pc = ksp.getPC()
    try:
        factor_solver_type = pc.getFactorSolverType()
    except Exception:
        factor_solver_type = None
    return (
        ksp.getType(),
        pc.getType(),
        factor_solver_type,
        ksp.getOptionsPrefix(),
        tuple(ksp.getTolerances()),
        int(operator.handle),
        int(preconditioning_operator.handle),
    )


def _invoke_collective_variable_p_live_observer(
    observer: Callable[[Stage4VariablePLiveView], None],
    view: Stage4VariablePLiveView,
    communicator: MPI.Intracomm,
) -> None:
    """Invoke one controlled callback and close its recovered vectors."""

    protected_objects: dict[str, Any] = {}
    protected_states: dict[str, int] = {}
    ksp_configuration: tuple[Any, ...] | None = None
    preflight_errors: list[dict[str, Any]] = []
    try:
        protected_objects = {
            "matrix": view.A,
            "rhs": view.b,
            "solution": view.x,
            "field": view.field.x.petsc_vec,
        }
        protected_states = {
            name: int(petsc_object.stateGet())
            for name, petsc_object in protected_objects.items()
        }
        ksp_configuration = _ksp_configuration_signature(view.ksp)
    except Exception as exc:
        preflight_errors.append(
            {
                "rank": int(communicator.rank),
                "phase": "callback_preflight",
                "exception_type": type(exc).__name__,
                "message": str(exc),
            }
        )
    collective_preflight_errors = [
        error
        for rank_errors in communicator.allgather(preflight_errors)
        for error in rank_errors
    ]
    if collective_preflight_errors:
        cleanup_errors: list[dict[str, Any]] = []
        try:
            view.recovered.destroy()
        except Exception as exc:
            cleanup_errors.append(
                {
                    "rank": int(communicator.rank),
                    "phase": "preflight_recovered_vector_cleanup",
                    "exception_type": type(exc).__name__,
                    "message": str(exc),
                }
            )
        collective_cleanup_errors = [
            error
            for rank_errors in communicator.allgather(cleanup_errors)
            for error in rank_errors
        ]
        raise Stage4VariablePLiveObserverError(
            "variable-p live observer preflight failed collectively: "
            + json.dumps(
                collective_preflight_errors + collective_cleanup_errors,
                sort_keys=True,
            )
        )
    if ksp_configuration is None:
        raise AssertionError("collective callback preflight lost KSP identity")
    local_errors: list[dict[str, Any]] = []
    try:
        observer(view)
    except Exception as exc:
        local_errors.append(
            {
                "rank": int(communicator.rank),
                "phase": "callback",
                "exception_type": type(exc).__name__,
                "message": str(exc),
            }
        )
    for name, petsc_object in protected_objects.items():
        try:
            observed_state = int(petsc_object.stateGet())
        except Exception as exc:
            local_errors.append(
                {
                    "rank": int(communicator.rank),
                    "phase": f"borrowed_{name}_state_audit",
                    "exception_type": type(exc).__name__,
                    "message": str(exc),
                }
            )
            continue
        if observed_state != protected_states[name]:
            local_errors.append(
                {
                    "rank": int(communicator.rank),
                    "phase": f"borrowed_{name}_state_audit",
                    "exception_type": "BorrowedObjectMutation",
                    "message": (
                        f"PETSc state changed from "
                        f"{protected_states[name]} to {observed_state}"
                    ),
                }
            )
    try:
        observed_ksp_configuration = _ksp_configuration_signature(view.ksp)
    except Exception as exc:
        local_errors.append(
            {
                "rank": int(communicator.rank),
                "phase": "borrowed_ksp_configuration_audit",
                "exception_type": type(exc).__name__,
                "message": str(exc),
            }
        )
    else:
        if observed_ksp_configuration != ksp_configuration:
            local_errors.append(
                {
                    "rank": int(communicator.rank),
                    "phase": "borrowed_ksp_configuration_audit",
                    "exception_type": "BorrowedObjectMutation",
                    "message": "KSP operator/options configuration changed",
                }
            )
    try:
        view.recovered.destroy()
    except Exception as exc:
        local_errors.append(
            {
                "rank": int(communicator.rank),
                "phase": "recovered_vector_cleanup",
                "exception_type": type(exc).__name__,
                "message": str(exc),
            }
        )
    observer_errors = [
        error
        for rank_errors in communicator.allgather(local_errors)
        for error in rank_errors
    ]
    if observer_errors:
        raise Stage4VariablePLiveObserverError(
            "variable-p live observer failed collectively after all ranks "
            "left the callback: " + json.dumps(observer_errors, sort_keys=True)
        )


def _assembly_backend_summary_fields(
    audit: dict[str, object],
    qualification: dict[str, object],
) -> dict[str, object]:
    """Return the stable requested/actual backend provenance fields."""

    return {
        "stage4_full3d_assembly_backend_requested": audit["requested"],
        "stage4_full3d_assembly_backend_actual": audit["actual"],
        "stage4_full3d_assembly_backend_selection_source": audit["selection_source"],
        "stage4_full3d_assembly_backend_qualification": qualification,
        "stage4_full3d_assembly_backend_audit": audit,
    }


def _complex_text(value: complex) -> str:
    number = complex(value)
    return f"{number.real:.16e}{number.imag:+.16e}j"


def _idx(values) -> np.ndarray:
    """PETSc index arrays must match the PETSc build's integer width."""

    if isinstance(values, np.ndarray):
        return np.asarray(values, dtype=PETSc.IntType)
    return np.fromiter(values, dtype=PETSc.IntType)


def _deferred_preallocation_matrix_stats(
    matrix,
    preallocation: dict[str, Any],
) -> dict[str, Any]:
    """Describe planned preallocation before the sole final assembly."""

    rows, cols = matrix.getSize()
    local_rows, local_cols = matrix.getLocalSize()
    row_ownership = matrix.getOwnershipRange()
    column_ownership = matrix.getOwnershipRangeColumn()
    allocated = int(preallocation["preallocated_structural_nnz"])
    return {
        "matrix_rows": int(rows),
        "matrix_cols": int(cols),
        "matrix_nnz_used": None,
        "matrix_nnz_allocated": None,
        "matrix_nnz_unneeded": None,
        "matrix_mallocs": None,
        "matrix_type": matrix.getType(),
        "matrix_local_rows": int(local_rows),
        "matrix_local_cols": int(local_cols),
        "matrix_row_ownership_range": list(map(int, row_ownership)),
        "matrix_column_ownership_range": list(map(int, column_ownership)),
        "matrix_average_nnz_per_row": None,
        "matrix_maximum_nnz_per_row": None,
        "matrix_average_allocated_nnz_per_row": None,
        "matrix_memory_bytes": None,
        "matrix_memory_mb": None,
        "matrix_memory_estimate_bytes": None,
        "matrix_memory_estimate_mb": None,
        "matrix_norm_frobenius": None,
        "matrix_norm_infinity": None,
        "matrix_preallocated_structural_nnz_planned": float(allocated),
        "matrix_average_preallocated_nnz_per_row_planned": (
            float(allocated) / float(rows) if rows else 0.0
        ),
        "matrix_stats_measurement_status": "derived_pre_final_assembly",
        "matrix_stats_semantics": (
            "exact base constrained-cell graph plus a support-safe DtN "
            "upper bound; measured allocation and numerical NNZ are "
            "deferred until the sole augmented-matrix final assembly"
        ),
    }


def _dof_row_semantics(
    *,
    active_exact_sequence_fe_dofs: int,
    storage_carrier_fe_dofs: int,
    independent_trace_rows: int | None,
    augmented_rows: int,
    auxiliary_rows: int,
) -> dict[str, Any]:
    """Name physical FE spaces and actual linear-system rows unambiguously."""

    active = int(active_exact_sequence_fe_dofs)
    storage = int(storage_carrier_fe_dofs)
    independent = (
        None if independent_trace_rows is None else int(independent_trace_rows)
    )
    augmented = int(augmented_rows)
    auxiliary = int(auxiliary_rows)
    if min(active, storage, augmented, auxiliary) < 0:
        raise ValueError("DoF and row counts must be nonnegative.")
    if active > storage:
        raise ValueError("Active exact-sequence FE DoFs exceed the storage carrier.")
    if independent is not None:
        if independent < 0 or independent > active:
            raise ValueError("Independent trace rows must not exceed active FE DoFs.")
        if augmented != independent + auxiliary:
            raise ValueError(
                "Augmented rows must equal independent trace plus auxiliary "
                "rows when independent trace elimination is active."
            )
    return {
        "num_active_exact_sequence_fe_dofs": active,
        "num_storage_carrier_fe_dofs": storage,
        "num_independent_trace_rows": independent,
        "num_augmented_rows": augmented,
        "dof_row_semantics": {
            "num_active_exact_sequence_fe_dofs": (
                "physical conforming exact-sequence FE space before static condensation"
            ),
            "num_storage_carrier_fe_dofs": (
                "DOLFINx carrier function-space DoFs; inactive high-order "
                "rows are storage only in variable-p runs"
            ),
            "num_independent_trace_rows": (
                "FE trace rows after cell-interior and Floquet-slave "
                "elimination; null when that reduction is not active"
            ),
            "num_augmented_rows": (
                "actual solved matrix rows including DtN auxiliary rows"
            ),
            "auxiliary_rows": auxiliary,
        },
    }


def _variable_p_active_fe_dofs(build_audit: Mapping[str, Any]) -> int:
    """Read the current variable-p DoF field with its legacy alias."""

    value = build_audit.get("actual_conforming_active_fe_dofs")
    if value is None:
        value = build_audit.get("actual_full3d_equivalent_active_fe_dofs")
    if value is None:
        raise KeyError("variable-p audit has no conforming active FE DoF count")
    return int(value)


def _as_ufl_vector(values: np.ndarray, phase):
    return ufl.as_vector(tuple(PETSc.ScalarType(value) * phase for value in values))


def _surface_vector_form(V, mesh_data, tag: int, vector: np.ndarray, phase):
    v = ufl.TestFunction(V)
    ds = ufl.Measure("ds", domain=mesh_data.mesh, subdomain_data=mesh_data.facet_tags)
    return ufl.inner(_as_ufl_vector(vector, phase), v) * ds(tag)


def _with_quadrature_degree(form, quadrature_degree):
    if quadrature_degree is None:
        return form
    degree = int(quadrature_degree)
    integrals = tuple(
        integral.reconstruct(
            metadata={
                **integral.metadata(),
                "quadrature_degree": degree,
            }
        )
        for integral in form.integrals()
    )
    return ufl.Form(integrals)


def _assemble_mpc_form_vector(linear_form, mpc) -> PETSc.Vec:
    vec = dolfinx_mpc.assemble_vector(linear_form, mpc)
    vec.ghostUpdate(addv=PETSc.InsertMode.ADD_VALUES, mode=PETSc.ScatterMode.REVERSE)
    vec.ghostUpdate(addv=PETSc.InsertMode.INSERT_VALUES, mode=PETSc.ScatterMode.FORWARD)
    return vec


def _assemble_unconstrained_form_vector(linear_form) -> PETSc.Vec:
    vec = fem_petsc.assemble_vector(linear_form)
    vec.ghostUpdate(
        addv=PETSc.InsertMode.ADD_VALUES,
        mode=PETSc.ScatterMode.REVERSE,
    )
    vec.ghostUpdate(
        addv=PETSc.InsertMode.INSERT_VALUES,
        mode=PETSc.ScatterMode.FORWARD,
    )
    return vec


def _assemble_mpc_vector(
    linear_form,
    mpc,
    *,
    quadrature_degree: int | None = None,
    jit_options: Mapping[str, Any] | None = None,
) -> PETSc.Vec:
    jit_kwargs: dict[str, Any] = {}
    if jit_options is not None:
        jit_kwargs["jit_options"] = dict(jit_options)
    return _assemble_mpc_form_vector(
        fem.form(
            _with_quadrature_degree(linear_form, quadrature_degree),
            **jit_kwargs,
        ),
        mpc,
    )


def _assemble_unconstrained_vector(
    linear_form,
    *,
    quadrature_degree: int | None = None,
) -> PETSc.Vec:
    return _assemble_unconstrained_form_vector(
        fem.form(
            _with_quadrature_degree(linear_form, quadrature_degree),
        )
    )


def _vec_nonzero_owned_entries(
    vec: PETSc.Vec,
    *,
    relative_tol: float = 1.0e-13,
    support: np.ndarray | None = None,
    timing_totals: dict[str, float] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Return owned significant entries using one collective cutoff."""

    start, end = vec.getOwnershipRange()
    values = np.asarray(vec.getArray(readonly=True), dtype=np.complex128)
    if support is not None:
        started = time.perf_counter() if timing_totals is not None else None
        local_support = np.asarray(support, dtype=np.int64).reshape(-1)
        if local_support.size and (
            int(local_support.min()) < 0 or int(local_support.max()) >= values.size
        ):
            raise ValueError("surface support contains a non-owned vector entry")
        supported_values = values[local_support]
        if not np.isfinite(supported_values).all():
            raise ValueError("surface support vector contains non-finite entries")
        magnitudes = np.abs(supported_values)
        local_maximum = float(np.max(magnitudes, initial=0.0))
        global_maximum = float(
            vec.getComm()
            .tompi4py()
            .allreduce(
                local_maximum,
                op=MPI.MAX,
            )
        )
        cutoff = max(1.0e-30, relative_tol * global_maximum)
        nz = np.flatnonzero(magnitudes > cutoff)
        rows = _idx(np.asarray(start + local_support[nz], dtype=np.int64))
        result = rows, supported_values[nz].copy()
        if started is not None:
            timing_totals["owned_support_extract_seconds"] = (
                timing_totals.get("owned_support_extract_seconds", 0.0)
                + time.perf_counter() - started
            )
        return result

    if not np.isfinite(values).all():
        raise ValueError("surface vector contains non-finite owned entries")
    local_maximum = float(np.max(np.abs(values), initial=0.0))
    global_maximum = float(
        vec.getComm()
        .tompi4py()
        .allreduce(
            local_maximum,
            op=MPI.MAX,
        )
    )
    cutoff = max(1.0e-30, relative_tol * global_maximum)
    nz = np.flatnonzero(np.abs(values) > cutoff)
    return (_idx(np.arange(start, end, dtype=np.int64)[nz]), values[nz].copy())


def _surface_mpc_local_support(
    function_space: Any,
    mpc: Any,
    cells: Sequence[int],
    local_storage_size: int,
) -> np.ndarray:
    """Build the structural local write set for MPC exterior-facet assembly."""

    if int(function_space.dofmap.index_map_bs) != 1:
        raise ValueError("surface support opt-in requires block size one")
    cell_to_slaves = mpc.cell_to_slaves
    masters = mpc.masters
    support: set[int] = set()
    for cell_value in cells:
        cell = int(cell_value)
        cell_dofs = np.asarray(function_space.dofmap.cell_dofs(cell), dtype=np.int64)
        if cell_dofs.size and (
            int(cell_dofs.min()) < 0 or int(cell_dofs.max()) >= local_storage_size
        ):
            raise ValueError("surface cell DOF exceeds the MPC vector local storage")
        cell_dof_set = {int(dof) for dof in cell_dofs}
        support.update(cell_dof_set)
        for slave_value in cell_to_slaves.links(cell):
            slave = int(slave_value)
            if slave not in cell_dof_set:
                raise ValueError("MPC cell slave is absent from the form cell DOF map")
            for master_value in masters.links(slave):
                master = int(master_value)
                if master < 0 or master >= local_storage_size:
                    raise ValueError("MPC master exceeds the vector local/ghost storage")
                support.add(master)
    return np.asarray(sorted(support), dtype=np.int32)


def _surface_array_sha256(array: np.ndarray) -> str:
    """Hash an existing contiguous numeric array without making a byte copy."""

    value = np.asarray(array)
    if not value.flags.c_contiguous:
        raise ValueError("surface identity arrays must be C-contiguous")
    digest = hashlib.sha256()
    digest.update(memoryview(value).cast("B"))
    return digest.hexdigest()


def _require_surface_support_superset(
    required_support: Sequence[int], proposed_support: Sequence[int]
) -> None:
    """Reject a support mask that omits any structurally writable local row."""

    required = {int(value) for value in required_support}
    proposed = {int(value) for value in proposed_support}
    missing = sorted(required.difference(proposed))
    if missing:
        raise ValueError(
            "surface support omits structurally writable local rows: "
            f"{missing[:8]}"
        )


def _combine_owned_entries(
    component_entries: tuple[
        tuple[np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray]
    ],
    coefficients: tuple[complex, complex],
    *,
    comm: MPI.Intracomm,
    relative_tol: float = 1.0e-13,
) -> tuple[np.ndarray, np.ndarray]:
    row_blocks: list[np.ndarray] = []
    value_blocks: list[np.ndarray] = []
    for (rows, values), coefficient in zip(component_entries, coefficients):
        coefficient = complex(coefficient)
        if len(rows) == 0 or abs(coefficient) <= 0.0:
            continue
        row_blocks.append(rows)
        value_blocks.append(PETSc.ScalarType(coefficient) * values)
    if row_blocks:
        rows_all = np.concatenate(row_blocks).astype(
            PETSc.IntType,
            copy=False,
        )
        values_all = np.concatenate(value_blocks).astype(
            np.complex128,
            copy=False,
        )
        order = np.argsort(rows_all, kind="mergesort")
        rows_sorted = rows_all[order]
        values_sorted = values_all[order]
        unique_rows, first = np.unique(rows_sorted, return_index=True)
        summed_values = np.add.reduceat(values_sorted, first)
    else:
        unique_rows = _idx([])
        summed_values = np.asarray([], dtype=np.complex128)
    local_maximum = float(np.max(np.abs(summed_values), initial=0.0))
    global_maximum = float(comm.allreduce(local_maximum, op=MPI.MAX))
    cutoff = max(1.0e-30, relative_tol * global_maximum)
    keep = np.abs(summed_values) > cutoff
    return _idx(unique_rows[keep]), summed_values[keep].copy()


def _active_trace_values_from_augmented(
    x_aug: PETSc.Vec,
    condensed: AssemblyTimeCondensedSystem,
) -> np.ndarray:
    """Collect the small independent trace vector on every rank."""

    comm = x_aug.getComm().tompi4py()
    local_active = len(condensed.trace_constraints.owned_active_original_dofs)
    local_values = np.asarray(
        x_aug.getArray(readonly=True)[:local_active],
        dtype=np.complex128,
    ).copy()
    packets = comm.allgather(local_values)
    active = np.concatenate(packets) if packets else np.empty(0, dtype=np.complex128)
    if active.shape != (condensed.active_rows,):
        raise RuntimeError("distributed active trace solution does not close globally")
    return active


def _assign_fe_solution_from_assembly_time_condensation(
    x_aug: PETSc.Vec,
    condensed: AssemblyTimeCondensedSystem,
    floquet_data: DoubleFloquet3DData,
    full_rhs: PETSc.Vec,
) -> tuple[Any, PETSc.Vec, dict[str, Any]]:
    """Recover cell interiors without allocating the full global matrix."""

    recovery_started = time.perf_counter()
    active = _active_trace_values_from_augmented(x_aug, condensed)
    recovered = recover_owned_cell_interiors(
        condensed,
        active,
        full_rhs=full_rhs,
    )
    mpc = floquet_data.mpc
    E_total = fem.Function(mpc.function_space, name="E_total")
    index_map = E_total.function_space.dofmap.index_map
    block_size = E_total.function_space.dofmap.index_map_bs
    x_fe = create_vector([(index_map, block_size)])
    x_fe.set(PETSc.ScalarType(0.0))
    owned_active = condensed.trace_constraints.owned_active_original_dofs
    if len(owned_active):
        active_ids = _idx(
            condensed.trace_constraints.original_to_active[int(original)]
            for original in owned_active
        )
        x_fe.setValues(
            owned_active,
            active[active_ids],
            addv=PETSc.InsertMode.INSERT_VALUES,
        )
    local_recovered = 0
    for original_rows, values in recovered:
        x_fe.setValues(
            original_rows,
            np.asarray(values, dtype=PETSc.ScalarType),
            addv=PETSc.InsertMode.INSERT_VALUES,
        )
        local_recovered += len(original_rows)
    x_fe.assemble()
    _ghost_update(
        x_fe,
        PETSc.InsertMode.INSERT,
        PETSc.ScatterMode.FORWARD,
    )  # type: ignore[arg-type]
    fem_petsc.assign(x_fe, E_total)
    mpc.homogenize(E_total)
    mpc.backsubstitution(E_total)
    E_total.x.scatter_forward()
    comm = E_total.function_space.mesh.comm
    return (
        E_total,
        x_fe,
        {
            "schema_version": ("task035b.assembly-time-cell-condensation-recovery.v1"),
            "status": "full_field_recovered_without_full_global_matrix",
            "recovered_interior_rows": int(comm.allreduce(local_recovered, op=MPI.SUM)),
            "full_global_matrix_allocated": False,
            "full_trace_matrix_allocated": False,
            "total_recovery_seconds": float(
                comm.allreduce(
                    time.perf_counter() - recovery_started,
                    op=MPI.MAX,
                )
            ),
        },
    )


def _assembly_time_full_operator_residual(
    bilinear_form,
    floquet_data: DoubleFloquet3DData,
    embedded_fe_solution: PETSc.Vec,
    reduced_matrix: PETSc.Mat | None,
    reduced_rhs: PETSc.Vec,
    reduced_solution: PETSc.Vec,
    condensed: AssemblyTimeCondensedSystem,
    full_rhs: PETSc.Vec,
    reduced_residual_norm: float | None = None,
) -> dict[str, Any]:
    """Audit all eliminated FE equations without allocating the full matrix."""

    reduced = (
        {"linear_system_residual_norm": float(reduced_residual_norm)}
        if reduced_residual_norm is not None
        else _linear_residual(reduced_matrix, reduced_rhs, reduced_solution)
    )
    context = MpcFormActionContext(
        bilinear_form,
        floquet_data.mpc,
        reference=None,
    )
    action = embedded_fe_solution.duplicate()
    action.set(PETSc.ScalarType(0.0))
    try:
        context.mult(
            None,  # type: ignore[arg-type]
            embedded_fe_solution,
            action,
        )
        local_interior_sq = 0.0
        local_interior_max = 0.0
        for cell in condensed.cell_recovery_maps:
            values = np.asarray(
                action.getValues(cell.interior_original_dofs),
                dtype=np.complex128,
            )
            values -= np.asarray(
                full_rhs.getValues(cell.interior_original_dofs),
                dtype=np.complex128,
            )
            values = (
                condensed.interior_residual_projection_by_class[cell.class_key] @ values
            )
            local_interior_sq += float(np.vdot(values, values).real)
            local_interior_max = max(
                local_interior_max,
                float(np.max(np.abs(values), initial=0.0)),
            )
        comm = reduced_solution.getComm().tompi4py()
        interior_norm = float(np.sqrt(comm.allreduce(local_interior_sq, op=MPI.SUM)))
        interior_max = float(comm.allreduce(local_interior_max, op=MPI.MAX))
        reduced_norm = float(reduced["linear_system_residual_norm"] or 0.0)
        full_norm = float(np.hypot(reduced_norm, interior_norm))
        local_aux_rhs_sq = 0.0
        if comm.rank == comm.size - 1 and condensed.appended_rows:
            aux_start = condensed.active_rows
            aux_rhs = np.asarray(
                reduced_rhs.getValues(
                    _idx(
                        range(
                            aux_start,
                            aux_start + condensed.appended_rows,
                        )
                    )
                ),
                dtype=np.complex128,
            )
            local_aux_rhs_sq = float(np.vdot(aux_rhs, aux_rhs).real)
        rhs_norm = float(
            np.sqrt(full_rhs.norm() ** 2 + comm.allreduce(local_aux_rhs_sq, op=MPI.SUM))
        )

        local_aux_sq = 0.0
        if comm.rank == comm.size - 1 and condensed.appended_rows:
            aux_start = condensed.active_rows
            aux_values = np.asarray(
                reduced_solution.getValues(
                    _idx(
                        range(
                            aux_start,
                            aux_start + condensed.appended_rows,
                        )
                    )
                ),
                dtype=np.complex128,
            )
            local_aux_sq = float(np.vdot(aux_values, aux_values).real)
        auxiliary_norm_sq = float(comm.allreduce(local_aux_sq, op=MPI.SUM))
        full_solution_norm = float(
            np.sqrt(embedded_fe_solution.norm() ** 2 + auxiliary_norm_sq)
        )
        return {
            "linear_system_rhs_norm": rhs_norm,
            "linear_system_solution_norm": full_solution_norm,
            "linear_system_residual_norm": full_norm,
            "linear_system_relative_residual": (full_norm / max(rhs_norm, 1.0e-30)),
            "reduced_trace_dtn_residual_norm": reduced_norm,
            "eliminated_cell_interior_residual_norm": interior_norm,
            "eliminated_cell_interior_max_abs_residual": interior_max,
            "full_operator_residual_method": (
                "external snapshot reduced residual plus matrix-free "
                "dolfinx_mpc UFL action"
                if reduced_residual_norm is not None
                else "explicit reduced trace+DtN Mat action combined with "
                "matrix-free dolfinx_mpc UFL action projected onto every "
                "active eliminated cell-interior test space, including "
                "condensed full-space RHS"
            ),
            "full_global_matrix_allocated_for_residual": False,
            "full_trace_matrix_allocated_for_residual": False,
        }
    finally:
        action.destroy()
        context.destroy()


def _set_scalar_constant(constant: fem.Constant, value: complex) -> None:
    scalar = PETSc.ScalarType(value)
    try:
        constant.value[...] = scalar
    except Exception:
        constant.value = scalar


class _ReusableSurfaceComponentAssembler:
    """Cache one port surface form and update only the Fourier phase constants."""

    def __init__(
        self,
        V,
        mesh_data,
        tag: int,
        component: int,
        *,
        quadrature_degree: int | None = None,
        jit_options: Mapping[str, Any] | None = None,
    ):
        if component not in {0, 1}:
            raise ValueError(
                "Stage-4 DtN port component assembly only supports x/y tangential components."
            )
        self.function_space = V
        self.tag = int(tag)
        self.mesh_data = mesh_data
        self.component = int(component)
        self.comm = mesh_data.mesh.comm
        self.alpha = fem.Constant(mesh_data.mesh, PETSc.ScalarType(0.0))
        self.gamma = fem.Constant(mesh_data.mesh, PETSc.ScalarType(0.0))
        self.kz = fem.Constant(mesh_data.mesh, PETSc.ScalarType(0.0))
        x = ufl.SpatialCoordinate(mesh_data.mesh)
        phase = ufl.exp(
            PETSc.ScalarType(1j) * self.alpha * x[0]
            + PETSc.ScalarType(1j) * self.gamma * x[1]
            + PETSc.ScalarType(1j) * self.kz * x[2]
        )
        vector = [PETSc.ScalarType(0.0), PETSc.ScalarType(0.0), PETSc.ScalarType(0.0)]
        vector[component] = phase
        v = ufl.TestFunction(V)
        ds = ufl.Measure(
            "ds", domain=mesh_data.mesh, subdomain_data=mesh_data.facet_tags
        )
        jit_kwargs: dict[str, Any] = {}
        if jit_options is not None:
            jit_kwargs["jit_options"] = dict(jit_options)
        form = ufl.inner(ufl.as_vector(tuple(vector)), v) * ds(tag)
        self.form = fem.form(
            _with_quadrature_degree(form, quadrature_degree),
            **jit_kwargs,
        )

    def assemble_entries(
        self,
        mode: PortMode3D,
        mpc,
        *,
        workspace: Any | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        _set_scalar_constant(self.alpha, mode.alpha)
        _set_scalar_constant(self.gamma, mode.gamma)
        _set_scalar_constant(self.kz, mode.k_vector[2])
        vec = (
            _assemble_mpc_form_vector(self.form, mpc)
            if workspace is None
            else workspace.assemble(self.form, mpc)
        )
        try:
            if workspace is None:
                return _vec_nonzero_owned_entries(vec)
            return _vec_nonzero_owned_entries(
                vec,
                support=workspace.owned_support,
                timing_totals=workspace.timing_totals,
            )
        finally:
            if workspace is None:
                vec.destroy()

    def assemble_unconstrained_vector(self, mode: PortMode3D) -> PETSc.Vec:
        _set_scalar_constant(self.alpha, mode.alpha)
        _set_scalar_constant(self.gamma, mode.gamma)
        _set_scalar_constant(self.kz, mode.k_vector[2])
        return _assemble_unconstrained_form_vector(self.form)


class _SurfaceMpcVectorWorkspace:
    """One opt-in reusable Vec for the four same-space exterior port forms."""

    EXPECTED_ASSEMBLERS = frozenset(
        {("top", 0), ("top", 1), ("bottom", 0), ("bottom", 1)}
    )

    def __init__(
        self,
        function_space: Any,
        mesh_data: Any,
        mpc: Any,
        surface_assemblers: Mapping[tuple[str, int], Any],
        *,
        collect_timings: bool = False,
    ) -> None:
        if int(mesh_data.mesh.comm.size) != 1:
            raise ValueError("reused surface-vector assembly is restricted to MPI1")
        if set(surface_assemblers) != self.EXPECTED_ASSEMBLERS:
            raise ValueError("reused surface-vector assembly requires top/bottom x/y forms")
        if int(function_space.dofmap.index_map_bs) != 1:
            raise ValueError("reused surface-vector assembly requires block size one")
        mpc_space = mpc.function_space
        if int(mpc_space.dofmap.index_map_bs) != 1:
            raise ValueError("reused MPC vector requires block size one")
        if function_space.mesh is not mpc_space.mesh:
            raise ValueError("surface form and MPC use different mesh objects")
        form_index_map = function_space.dofmap.index_map
        mpc_index_map = mpc_space.dofmap.index_map
        if (
            int(form_index_map.size_local) != int(mpc_index_map.size_local)
            or int(form_index_map.size_global) != int(mpc_index_map.size_global)
            or int(form_index_map.num_ghosts) != int(mpc_index_map.num_ghosts)
            or tuple(form_index_map.local_range) != tuple(mpc_index_map.local_range)
        ):
            raise ValueError("surface form and MPC dofmap owned/global layouts differ")
        for assembler in surface_assemblers.values():
            if assembler.function_space is not function_space:
                raise ValueError("surface assemblers do not share one function space")
            if assembler.mesh_data.mesh is not mesh_data.mesh:
                raise ValueError("surface assemblers do not share one mesh")
        self._vector: PETSc.Vec | None = None
        self._destroyed = False
        self._mpc = mpc
        self._function_space = function_space
        self._mesh_data = mesh_data
        self._allowed_assembler_ids = {id(assembler) for assembler in surface_assemblers.values()}
        self._allowed_form_ids = {
            id(assembler.form)
            for assembler in surface_assemblers.values()
            if hasattr(assembler, "form")
        }
        self.timing_totals: dict[str, float] | None = (
            {
                "scratch_initial_full_clear_seconds": 0.0,
                "scratch_support_clear_seconds": 0.0,
                "cpp_assembly_mpc_seconds": 0.0,
                "ghost_update_seconds": 0.0,
                "owned_support_extract_seconds": 0.0,
                "carrier_combine_seconds": 0.0,
                "carrier_normalize_validate_seconds": 0.0,
                "legendre_moment_local_seconds": 0.0,
            }
            if collect_timings
            else None
        )

        index_map = mpc_space.dofmap.index_map
        self._owned_size = int(index_map.size_local)
        local_storage_size = int(index_map.size_local + index_map.num_ghosts)
        self._vector = create_vector(
            [(index_map, int(mpc_space.dofmap.index_map_bs))]
        )
        try:
            started = time.perf_counter() if self.timing_totals is not None else None
            with self._vector.localForm() as local_form:
                local_values = local_form.array_w
                if int(local_values.size) != local_storage_size:
                    raise ValueError(
                        "MPC Vec local storage differs from its index-map owned+ghost size"
                    )
                # PETSc Vec storage is uninitialized; this is the sole full clear.
                local_form.set(0.0)
            if started is not None:
                self.timing_totals["scratch_initial_full_clear_seconds"] += (
                    time.perf_counter() - started
                )

            mesh = mesh_data.mesh
            topology = mesh.topology
            tdim = int(topology.dim)
            fdim = tdim - 1
            topology.create_connectivity(fdim, tdim)
            facet_to_cell = topology.connectivity(fdim, tdim)
            active_cells: set[int] = set()
            tags = {int(assembler.tag) for assembler in surface_assemblers.values()}
            for tag in tags:
                facets = np.asarray(mesh_data.facet_tags.find(tag), dtype=np.int32)
                if facets.size == 0:
                    raise ValueError(f"surface tag {tag} has no local facets")
                for facet_value in facets:
                    adjacent = np.asarray(
                        facet_to_cell.links(int(facet_value)), dtype=np.int32
                    )
                    if adjacent.size != 1:
                        raise ValueError(
                            "surface-vector opt-in accepts exterior facets only"
                        )
                    active_cells.add(int(adjacent[0]))
            if not active_cells:
                raise ValueError("surface-vector support contains no adjacent cells")
            cell_index_map = topology.index_map(tdim)
            if any(
                cell < 0
                or cell >= int(cell_index_map.size_local + cell_index_map.num_ghosts)
                for cell in active_cells
            ):
                raise ValueError("surface facet references a cell outside local topology storage")
            for cell in active_cells:
                form_dofs = np.asarray(
                    function_space.dofmap.cell_dofs(cell), dtype=np.int64
                )
                mpc_dofs = np.asarray(mpc_space.dofmap.cell_dofs(cell), dtype=np.int64)
                if not np.array_equal(form_dofs, mpc_dofs):
                    raise ValueError(
                        "surface form and MPC cell DOF maps are incompatible"
                    )
            self.local_support = _surface_mpc_local_support(
                function_space,
                mpc,
                sorted(active_cells),
                local_storage_size,
            )
            form_global_rows = form_index_map.local_to_global(self.local_support)
            mpc_global_rows = mpc_index_map.local_to_global(self.local_support)
            if not np.array_equal(form_global_rows, mpc_global_rows):
                raise ValueError("surface form and MPC local-to-global row maps differ")
            self.local_support.flags.writeable = False
            self.owned_support = np.ascontiguousarray(
                self.local_support[self.local_support < self._owned_size],
                dtype=np.int32,
            )
            self.owned_support.flags.writeable = False
            start, end = self._vector.getOwnershipRange()
            if int(end - start) != self._owned_size:
                raise ValueError("MPC Vec ownership differs from its local index map")
            self.facts = {
                "support_local_rows": int(self.local_support.size),
                "support_owned_rows": int(self.owned_support.size),
                "support_ghost_rows": int(
                    self.local_support.size - self.owned_support.size
                ),
                "support_index_bytes": int(self.local_support.nbytes),
                "vector_owned_rows": int(self._owned_size),
                "vector_local_storage_rows": int(local_storage_size),
                "scratch_vector_count": 1,
            }
        except BaseException:
            self.destroy()
            raise

    @property
    def vector(self) -> PETSc.Vec:
        if self._vector is None or self._destroyed:
            raise RuntimeError("surface MPC Vec workspace is destroyed")
        return self._vector

    def assemble(self, linear_form: Any, mpc: Any) -> PETSc.Vec:
        vector = self.vector
        if mpc is not self._mpc:
            raise ValueError("surface workspace was used with a different MPC")
        if id(linear_form) not in self._allowed_form_ids:
            raise ValueError("surface workspace was used with an unregistered form")
        started = time.perf_counter() if self.timing_totals is not None else None
        with vector.localForm() as local_form:
            local_values = local_form.array_w
            local_values[self.local_support] = 0.0
            if started is not None:
                self.timing_totals["scratch_support_clear_seconds"] += (
                    time.perf_counter() - started
                )
            started = time.perf_counter() if self.timing_totals is not None else None
            # Use the same qualified nanobind C++ function as the Python wrapper,
            # bypassing only its unconditional full-vector b_local.set(0.0).
            dolfinx_mpc.cpp.mpc.assemble_vector(
                local_values, linear_form._cpp_object, mpc._cpp_object
            )
        if started is not None:
            self.timing_totals["cpp_assembly_mpc_seconds"] += (
                time.perf_counter() - started
            )
        started = time.perf_counter() if self.timing_totals is not None else None
        vector.ghostUpdate(
            addv=PETSc.InsertMode.ADD_VALUES, mode=PETSc.ScatterMode.REVERSE
        )
        vector.ghostUpdate(
            addv=PETSc.InsertMode.INSERT_VALUES, mode=PETSc.ScatterMode.FORWARD
        )
        if started is not None:
            self.timing_totals["ghost_update_seconds"] += (
                time.perf_counter() - started
            )
        return vector

    def assemble_custom(
        self,
        assembler: Any,
        mpc: Any,
        assemble_into: Callable[[PETSc.Vec], None],
    ) -> PETSc.Vec:
        """Clear the exact shared support and run a registered local backend."""

        vector = self.vector
        if mpc is not self._mpc:
            raise ValueError("surface workspace was used with a different MPC")
        if id(assembler) not in self._allowed_assembler_ids:
            raise ValueError("surface workspace was used with an unregistered assembler")
        if (
            assembler.function_space is not self._function_space
            or assembler.mesh_data is not self._mesh_data
        ):
            raise ValueError("custom surface assembler does not match workspace identity")
        started = time.perf_counter() if self.timing_totals is not None else None
        with vector.localForm() as local_form:
            local_form.array_w[self.local_support] = 0.0
        if started is not None:
            self.timing_totals["scratch_support_clear_seconds"] += (
                time.perf_counter() - started
            )
        started = time.perf_counter() if self.timing_totals is not None else None
        assemble_into(vector)
        if started is not None:
            self.timing_totals["legendre_moment_local_seconds"] += (
                time.perf_counter() - started
            )
        started = time.perf_counter() if self.timing_totals is not None else None
        vector.ghostUpdate(
            addv=PETSc.InsertMode.ADD_VALUES, mode=PETSc.ScatterMode.REVERSE
        )
        vector.ghostUpdate(
            addv=PETSc.InsertMode.INSERT_VALUES, mode=PETSc.ScatterMode.FORWARD
        )
        if started is not None:
            self.timing_totals["ghost_update_seconds"] += (
                time.perf_counter() - started
            )
        return vector

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        vector, self._vector = self._vector, None
        if vector is not None:
            vector.destroy()


@dataclass(frozen=True)
class _SurfaceCellMpcPlan:
    cell_dofs: np.ndarray
    slave_positions: np.ndarray
    master_rows: tuple[np.ndarray, ...]
    coefficient_rows: tuple[np.ndarray, ...]


@dataclass(frozen=True)
class _SurfaceFacetRecord:
    cell: int
    geometry_dofs: np.ndarray | None
    local_facet: int
    zeta_face: float
    x0: float
    y0: float
    hx: float
    hy: float
    z_face: float
    cell_plan: _SurfaceCellMpcPlan


class _SurfacePointwiseGeometryCache:
    """One-carrier cache of exact pointwise geometry for the p6 paired path."""

    def __init__(self, context: Any, *, max_bytes: int) -> None:
        from .fullspace_surface_legendre import (
            SURFACE_COMPONENT_PAIR_BACKEND,
            SURFACE_GEOMETRY_CACHE_MAX_BYTES,
            surface_geometry_cache_payload_bytes,
        )

        if (
            context.backend != SURFACE_COMPONENT_PAIR_BACKEND
            or int(context.degree) != 6
            or int(context.quadrature_degree) != 160
        ):
            raise ValueError("geometry caching requires the p6 paired q160 context")
        if not context._geometry_cache_enabled:
            raise ValueError("geometry cache was not enabled by the explicit profile")
        limit = int(max_bytes)
        if limit <= 0 or limit > SURFACE_GEOMETRY_CACHE_MAX_BYTES:
            raise ValueError("geometry cache limit exceeds the fixed 4 GiB cap")
        records_by_side = context._records_by_side
        if set(records_by_side) != {"bottom", "top"}:
            raise ValueError("geometry cache requires the two validated exterior sides")
        ordered_records = []
        seen: set[int] = set()
        for side in ("bottom", "top"):
            records = records_by_side[side]
            if not isinstance(records, tuple):
                raise ValueError("geometry cache records must be immutable ordered tuples")
            for position, record in enumerate(records):
                record_id = id(record)
                if record_id in seen:
                    raise ValueError("a geometry facet record occurs more than once")
                seen.add(record_id)
                if (
                    record.zeta_face != (0.0 if side == "bottom" else 1.0)
                    or record.local_facet
                    != context._geometry_face_local_facets[side]
                ):
                    raise ValueError("geometry cache side/facet metadata is inconsistent")
                ordered_records.append((side, position, record))
        point_count = int(context.quadrilateral_weights.size)
        predicted_bytes = surface_geometry_cache_payload_bytes(
            point_count=point_count, facet_count=len(ordered_records)
        )
        # This guard is before any per-facet geometry mapping or cache-array
        # allocation. It is a numeric-array cap, not an RSS estimate.
        if predicted_bytes > limit:
            raise MemoryError(
                f"surface geometry cache needs {predicted_bytes} bytes, over {limit}"
            )

        self._context = context
        self._mesh = context.mesh_data.mesh
        self._geometry_coordinates = context._geometry_coordinates
        self._records_by_side = records_by_side
        self._record_sequences = dict(records_by_side)
        self._quadrilateral_points = context.quadrilateral_points
        self._quadrilateral_weights = context.quadrilateral_weights
        self._polynomial_x = context._polynomial_x
        self._polynomial_y = context._polynomial_y
        self._weighted_moment_contraction = (
            context._weighted_moment_contraction
        )
        self._polynomial_values = (
            context.polynomial_values
            if self._weighted_moment_contraction is not None
            else None
        )
        self._geometry_face_tables = {
            side: context._geometry_face_tables[side]
            for side in ("bottom", "top")
        }
        self._geometry_face_table_mapping = context._geometry_face_tables
        self._geometry_face_local_facets = context._geometry_face_local_facets
        self._geometry_face_local_facet_values = dict(
            context._geometry_face_local_facets
        )
        self._facet_jacobians = dict(context._facet_jacobians_by_side)
        self._facet_jacobian_mapping = context._facet_jacobians_by_side
        self._geometry_dofmap = context._geometry_dofmap
        self._coordinate_element_identity = dict(context._coordinate_element_identity)
        self._formatter_identity = dict(context._ffcx_coordinate_table_options)
        self._quadrature_identity = dict(context.facts["quadrature_array_hashes"])
        self._degree = int(context.degree)
        self._quadrature_degree = int(context.quadrature_degree)
        self._entries: dict[int, tuple[Any, ...]] | None = {}
        self._expected_record_count = len(ordered_records)
        self._predicted_numeric_payload_bytes = predicted_bytes
        self._numeric_payload_bytes = 0
        self._coordinate_snapshot_bytes = 0
        self._geometry_build_count = 0
        self._lookup_count = 0
        self._released = False
        self._numeric_payload_peak_bytes = 0
        self._coordinate_snapshot_peak_bytes = 0
        try:
            for side, position, record in ordered_records:
                if record.geometry_dofs is None:
                    raise ValueError("geometry cache record has no coordinate DOFs")
                geometry_dofs = np.asarray(record.geometry_dofs)
                if (
                    geometry_dofs.shape != (8,)
                    or not np.issubdtype(geometry_dofs.dtype, np.integer)
                    or np.unique(geometry_dofs).size != geometry_dofs.size
                    or not np.array_equal(
                        geometry_dofs,
                        np.asarray(context._geometry_dofmap[record.cell]),
                    )
                ):
                    raise ValueError("geometry cache coordinate DOF identity is malformed")
                coordinate_snapshot, physical, determinant, cofactors, measure = (
                    context._build_pointwise_geometry_entry(side, record)
                )
                arrays = (physical, determinant, cofactors, measure)
                expected_shapes = (
                    (point_count, 3),
                    (point_count,),
                    (point_count, 3, 3),
                    (point_count,),
                )
                if any(
                    array.dtype != np.dtype(np.float64)
                    or array.shape != shape
                    or not array.flags.c_contiguous
                    or not np.isfinite(array).all()
                    for array, shape in zip(arrays, expected_shapes, strict=True)
                ):
                    raise ValueError("mapped geometry cache arrays are malformed")
                if (
                    coordinate_snapshot.dtype != np.dtype(np.float64)
                    or coordinate_snapshot.shape != (8, 3)
                    or not np.isfinite(coordinate_snapshot).all()
                    or not np.array_equal(
                        coordinate_snapshot,
                        self._geometry_coordinates[geometry_dofs],
                    )
                ):
                    raise ValueError("raw geometry snapshot differs from the live mesh")
                coordinate_snapshot.flags.writeable = False
                for array in arrays:
                    array.flags.writeable = False
                self._entries[id(record)] = (
                    side,
                    position,
                    record,
                    tuple(int(value) for value in geometry_dofs),
                    coordinate_snapshot,
                    *arrays,
                )
                self._numeric_payload_bytes += sum(int(array.nbytes) for array in arrays)
                self._coordinate_snapshot_bytes += int(coordinate_snapshot.nbytes)
                self._numeric_payload_peak_bytes = max(
                    self._numeric_payload_peak_bytes, self._numeric_payload_bytes
                )
                self._coordinate_snapshot_peak_bytes = max(
                    self._coordinate_snapshot_peak_bytes,
                    self._coordinate_snapshot_bytes,
                )
                self._geometry_build_count += 1
                if self._numeric_payload_bytes > limit:
                    raise MemoryError("actual geometry cache arrays exceed the 4 GiB cap")
            if self._numeric_payload_bytes != predicted_bytes:
                raise ValueError("actual geometry cache payload differs from preflight")
        except Exception:
            self.release()
            raise

    def _assert_context_binding(self, context: Any) -> None:
        if (
            context is not self._context
            or context.mesh_data.mesh is not self._mesh
            or context._geometry_coordinates is not self._geometry_coordinates
            or context._records_by_side is not self._records_by_side
            or context.quadrilateral_points is not self._quadrilateral_points
            or context.quadrilateral_weights is not self._quadrilateral_weights
            or context._polynomial_x is not self._polynomial_x
            or context._polynomial_y is not self._polynomial_y
            or context._weighted_moment_contraction
            != self._weighted_moment_contraction
            or (
                self._weighted_moment_contraction is not None
                and (
                    context.polynomial_values is not self._polynomial_values
                    or context.polynomial_values.flags.writeable
                )
            )
            or context._geometry_dofmap is not self._geometry_dofmap
            or context._geometry_face_tables is not self._geometry_face_table_mapping
            or context._geometry_face_local_facets
            is not self._geometry_face_local_facets
            or dict(context._geometry_face_local_facets)
            != self._geometry_face_local_facet_values
            or context._facet_jacobians_by_side is not self._facet_jacobian_mapping
            or context.degree != self._degree
            or context.quadrature_degree != self._quadrature_degree
            or dict(context._coordinate_element_identity) != self._coordinate_element_identity
            or dict(context._ffcx_coordinate_table_options) != self._formatter_identity
            or dict(context.facts["quadrature_array_hashes"])
            != self._quadrature_identity
        ):
            raise ValueError("surface geometry cache context or quadrature identity changed")
        if self._entries is None or self._released:
            raise RuntimeError("surface geometry cache is no longer active")

    def get(
        self,
        context: Any,
        side: str,
        position: int,
        record: _SurfaceFacetRecord,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        self._assert_context_binding(context)
        side = str(side)
        position = int(position)
        sequence = self._record_sequences.get(side)
        if (
            sequence is None
            or context._records_by_side.get(side) is not sequence
            or position < 0
            or position >= len(sequence)
            or sequence[position] is not record
        ):
            raise ValueError("surface geometry cache side/facet/order binding changed")
        entry = self._entries.get(id(record))
        if entry is None or entry[0] != side or entry[1] != position or entry[2] is not record:
            raise ValueError("surface geometry cache record identity is not present")
        dof_values = tuple(int(value) for value in np.asarray(record.geometry_dofs))
        if (
            dof_values != entry[3]
            or not np.array_equal(
                record.geometry_dofs,
                np.asarray(context._geometry_dofmap[record.cell]),
            )
            or not np.array_equal(
            context._geometry_coordinates[record.geometry_dofs],
            entry[4],
            )
        ):
            raise ValueError("surface geometry cache raw coordinates or DOFs changed")
        coordinate_values, coordinate_derivatives = context._geometry_face_tables[side]
        bound_values, bound_derivatives = self._geometry_face_tables[side]
        if (
            coordinate_values is not bound_values
            or coordinate_derivatives is not bound_derivatives
            or context._facet_jacobians_by_side[side] is not self._facet_jacobians[side]
            or record.zeta_face != (0.0 if side == "bottom" else 1.0)
            or record.local_facet != context._geometry_face_local_facets[side]
            or self._quadrilateral_points.flags.writeable
            or self._quadrilateral_weights.flags.writeable
            or self._polynomial_x.flags.writeable
            or self._polynomial_y.flags.writeable
            or coordinate_values.flags.writeable
            or coordinate_derivatives.flags.writeable
            or self._facet_jacobians[side].flags.writeable
        ):
            raise ValueError("surface geometry cache face identity changed")
        self._lookup_count += 1
        return entry[5], entry[6], entry[7], entry[8]

    def facts(self) -> dict[str, int | str | bool]:
        return {
            "enabled": True,
            "eligible_facet_count": self._expected_record_count,
            "geometry_build_count": self._geometry_build_count,
            "geometry_lookup_count": self._lookup_count,
            "predicted_numeric_array_payload_bytes": self._predicted_numeric_payload_bytes,
            "actual_numeric_array_payload_bytes": self._numeric_payload_bytes,
            "peak_numeric_array_payload_bytes": self._numeric_payload_peak_bytes,
            "numeric_payload_limit_bytes": 4 * 1024**3,
            "raw_coordinate_identity_snapshot_peak_bytes": self._coordinate_snapshot_peak_bytes,
            "python_metadata_and_allocator_bytes": "not counted in numeric payload",
            "jacobians_retained": False,
            "readonly_arrays": True,
            "release_count": int(self._released),
            "payload_after_release_bytes": 0 if self._released else self._numeric_payload_bytes,
            "payload_is_rss": False,
        }

    def release(self) -> dict[str, int | str | bool]:
        if not self._released:
            self._released = True
            if self._entries is not None:
                self._entries.clear()
                self._entries = None
            self._numeric_payload_bytes = 0
            self._coordinate_snapshot_bytes = 0
        return self.facts()


class _SurfaceLegendreMomentContext:
    """Bounded reference-cell data shared by one degree's four face forms."""

    def __init__(
        self,
        function_space: Any,
        mesh_data: Any,
        mpc: Any,
        cfg: Any,
        quadrature_degree: int,
        *,
        backend: str,
        reuse_geometry_cache: bool = False,
        geometry_cache_limit_bytes: int = 0,
        weighted_moment_contraction: str | None = None,
        prepare_trace_contraction: bool = False,
    ) -> None:
        import basix
        from basix import polynomials
        from ffcx.element_interface import map_facet_points
        from ffcx.options import get_options as get_ffcx_options

        from .fullspace_surface_legendre import (
            SURFACE_COMPONENT_PAIR_BACKEND,
            SURFACE_GEOMETRY_CACHE_MAX_BYTES,
            SURFACE_LEGENDRE_BACKEND,
            SURFACE_MOMENT_CACHE_LIMIT,
            SURFACE_POINTWISE_WEIGHTED_BACKEND,
            borrow_readonly_array_view,
            clamp_ffcx_coordinate_table,
            face_trace_reference_tensor,
            face_trace_table,
            ffcx_float64_formatter_facts,
            roundtrip_ffcx_float64_array,
            scalar_hex_coordinate_basix_element,
            validate_component_pair_degree,
            validate_prepared_trace_contraction,
            validate_q160_expanded_interval_tables,
            validate_weighted_moment_contraction,
        )

        if int(mesh_data.mesh.comm.size) != 1:
            raise NotImplementedError("Legendre surface backend is qualified for MPI1 only")
        if int(quadrature_degree) != 160:
            raise NotImplementedError("Legendre surface backend is fixed to quadrature degree 160")
        if backend not in {
            SURFACE_LEGENDRE_BACKEND,
            SURFACE_POINTWISE_WEIGHTED_BACKEND,
            SURFACE_COMPONENT_PAIR_BACKEND,
        }:
            raise ValueError(f"unsupported explicit Legendre backend: {backend}")
        if mpc is None or mpc.function_space.mesh is not mesh_data.mesh:
            raise ValueError("Legendre surface backend requires the finalized same-mesh MPC")
        element = function_space.element.basix_element
        if (
            element.family != basix.ElementFamily.N1E
            or element.cell_type != basix.CellType.hexahedron
            or element.map_type != basix.MapType.covariantPiola
            or element.polyset_type != basix.PolysetType.standard
            or int(element.value_size) != 3
        ):
            raise NotImplementedError("Legendre surface backend requires actual standard N1E hex")
        variant = getattr(element, "lagrange_variant", None)
        variant_name = getattr(variant, "name", "unknown").lower()
        if variant_name != "legendre":
            raise NotImplementedError(
                f"Legendre surface backend rejects element variant {variant_name!r}"
            )
        degree = int(element.degree)
        if degree not in (3, 6) or int(element.embedded_superdegree) != degree:
            raise NotImplementedError("Legendre surface backend supports only actual p3/p6 elements")
        validate_component_pair_degree(backend, degree)
        validate_weighted_moment_contraction(
            weighted_moment_contraction,
            backend=backend,
            degree=degree,
            quadrature_degree=int(quadrature_degree),
            reuse_geometry_cache=bool(reuse_geometry_cache),
        )
        validate_prepared_trace_contraction(
            bool(prepare_trace_contraction),
            backend=backend,
            degree=degree,
            quadrature_degree=int(quadrature_degree),
            reuse_geometry_cache=bool(reuse_geometry_cache),
            weighted_moment_contraction=weighted_moment_contraction,
        )
        if reuse_geometry_cache and (
            backend != SURFACE_COMPONENT_PAIR_BACKEND
            or degree != 6
            or int(geometry_cache_limit_bytes) != SURFACE_GEOMETRY_CACHE_MAX_BYTES
        ):
            raise ValueError("surface geometry caching is restricted to the explicit p6 pair")
        if not reuse_geometry_cache and int(geometry_cache_limit_bytes) != 0:
            raise ValueError("surface geometry cache limit requires its explicit opt-in")
        width = degree + 1
        raw_coefficient_matrix = element.coefficient_matrix
        coefficient_matrix = np.asarray(raw_coefficient_matrix)
        expected_rows = int(function_space.dofmap.cell_dofs(0).size)
        if (
            coefficient_matrix.dtype != np.dtype(np.float64)
            or not coefficient_matrix.flags.c_contiguous
            or coefficient_matrix.shape != (expected_rows, 3 * width**3)
            or int(element.dim) != expected_rows
        ):
            raise NotImplementedError("live Basix C matrix has an unsupported N1E tensor layout")
        if not np.isfinite(coefficient_matrix).all():
            raise ValueError("live Basix C matrix contains non-finite values")
        coefficient_matrix_sha256 = _surface_array_sha256(coefficient_matrix)
        coefficient_matrix_shape = tuple(int(item) for item in coefficient_matrix.shape)
        coefficient_matrix_dtype = coefficient_matrix.dtype.str

        interval_points, interval_weights = basix.make_quadrature(
            basix.CellType.interval,
            int(quadrature_degree),
            rule=basix.QuadratureType.default,
        )
        quadrilateral_points, quadrilateral_weights = basix.make_quadrature(
            basix.CellType.quadrilateral,
            int(quadrature_degree),
            rule=basix.QuadratureType.default,
        )
        interval_points = np.asarray(interval_points, dtype=np.float64).reshape(-1, 1)
        interval_weights = np.asarray(interval_weights, dtype=np.float64).reshape(-1)
        quadrilateral_points = np.asarray(quadrilateral_points, dtype=np.float64)
        quadrilateral_weights = np.asarray(quadrilateral_weights, dtype=np.float64)
        if interval_points.shape != (81, 1) or interval_weights.shape != (81,):
            raise NotImplementedError("q160 interval rule is not the qualified 81-point rule")
        expected_points = np.asarray(
            [(float(x[0]), float(y[0])) for x in interval_points for y in interval_points],
            dtype=np.float64,
        )
        expected_weights = np.asarray(
            [float(wx * wy) for wx in interval_weights for wy in interval_weights],
            dtype=np.float64,
        )
        if (
            quadrilateral_points.shape != expected_points.shape
            or quadrilateral_weights.shape != expected_weights.shape
            or not np.array_equal(quadrilateral_points, expected_points)
            or not np.array_equal(quadrilateral_weights, expected_weights)
        ):
            raise NotImplementedError("Basix q160 quad rule ordering/product is unsupported")
        basix_quadrilateral_weights_sha256 = _surface_array_sha256(
            quadrilateral_weights
        )
        pointwise_formatter_facts = None
        if backend in {
            SURFACE_POINTWISE_WEIGHTED_BACKEND,
            SURFACE_COMPONENT_PAIR_BACKEND,
        }:
            quadrilateral_weights = roundtrip_ffcx_float64_array(
                quadrilateral_weights,
                name="Basix quadrilateral weights",
            )
            pointwise_formatter_facts = ffcx_float64_formatter_facts()
        interval_points_sha256 = _surface_array_sha256(interval_points)
        interval_weights_sha256 = _surface_array_sha256(interval_weights)
        quadrilateral_points_sha256 = _surface_array_sha256(quadrilateral_points)
        quadrilateral_weights_sha256 = _surface_array_sha256(quadrilateral_weights)
        point_table = np.asarray(
            polynomials.tabulate_polynomials(
                basix.PolynomialType.legendre,
                basix.CellType.interval,
                degree,
                interval_points,
            ),
            dtype=np.float64,
        )
        endpoint_table = np.asarray(
            polynomials.tabulate_polynomials(
                basix.PolynomialType.legendre,
                basix.CellType.interval,
                degree,
                np.asarray([[0.0], [1.0]], dtype=np.float64),
            ),
            dtype=np.float64,
        )
        if point_table.shape != (width, 81) or endpoint_table.shape != (width, 2):
            raise NotImplementedError("Basix Legendre table ordering is unsupported")
        self.polynomial_values = np.ascontiguousarray(point_table.T)
        self.interval_points = np.ascontiguousarray(interval_points[:, 0])
        self.interval_weights = np.ascontiguousarray(interval_weights)
        self.degree = degree
        self.quadrature_degree = int(quadrature_degree)
        self.backend = str(backend)
        self._geometry_cache_enabled = bool(reuse_geometry_cache)
        self._geometry_cache_limit_bytes = int(geometry_cache_limit_bytes)
        self._geometry_cache: _SurfacePointwiseGeometryCache | None = None
        self._geometry_cache_last_facts: dict[str, Any] | None = None
        self._weighted_moment_contraction = weighted_moment_contraction
        self._six_lane_moment_workspace: Q160SixLaneWeightedMomentWorkspace | None = None
        self._prepare_trace_contraction = bool(prepare_trace_contraction)
        self._prepared_trace_contractions: dict[str, Any] = {}
        self._prepared_trace_release_count = 0
        self._weighted_moment_basis_validation: dict[str, Any] | None = None
        self.function_space = function_space
        self.mesh_data = mesh_data
        self.mpc = mpc
        self.quadrilateral_points = np.ascontiguousarray(quadrilateral_points)
        self.quadrilateral_weights = np.ascontiguousarray(quadrilateral_weights)
        coefficient_source, offset_source = mpc.coefficients()
        self._mpc_coefficients = borrow_readonly_array_view(
            coefficient_source, name="MPC coefficients"
        )
        self._mpc_offsets = borrow_readonly_array_view(
            offset_source, name="MPC offsets"
        )
        # These are borrowed views into the finalized MPC. Do not cast/diff the
        # global adjacency offsets: for the 0.7 nm p6 space that can create a
        # multi-GB int64 copy and scan. Only rows reached from boundary cells
        # are validated below and copied into immutable per-cell plans.
        is_slave_source = mpc.is_slave
        self._mpc_is_slave = borrow_readonly_array_view(
            is_slave_source, name="MPC slave flags"
        )
        self._mpc_array_view_identity = {
            "coefficients_shares_source": bool(
                isinstance(coefficient_source, np.ndarray)
                and np.shares_memory(self._mpc_coefficients, coefficient_source)
            ),
            "offsets_shares_source": bool(
                isinstance(offset_source, np.ndarray)
                and np.shares_memory(self._mpc_offsets, offset_source)
            ),
            "is_slave_shares_source": bool(
                isinstance(is_slave_source, np.ndarray)
                and np.shares_memory(self._mpc_is_slave, is_slave_source)
            ),
        }
        if (
            self._mpc_coefficients.ndim != 1
            or not np.issubdtype(self._mpc_coefficients.dtype, np.complexfloating)
            or self._mpc_offsets.ndim != 1
            or not np.issubdtype(self._mpc_offsets.dtype, np.integer)
            or self._mpc_is_slave.ndim != 1
            or not np.issubdtype(self._mpc_is_slave.dtype, np.integer)
        ):
            raise ValueError("finalized MPC coefficient/offset views are malformed")
        self._cell_to_slaves = mpc.cell_to_slaves
        self._masters = mpc.masters
        self._cell_plans: dict[int, _SurfaceCellMpcPlan] = {}
        self._trace_tables: dict[tuple[str, int], np.ndarray] = {}
        self._geometry_face_tables: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        self._geometry_face_local_facets: dict[str, int] = {}
        self._facet_jacobians_by_side: dict[str, np.ndarray] = {}
        self._geometry_dofmap = mesh_data.mesh.geometry.dofmap
        self._geometry_coordinates = np.asarray(
            mesh_data.mesh.geometry.x, dtype=np.float64
        )
        self._polynomial_x = np.empty((0, width), dtype=np.float64)
        self._polynomial_y = np.empty((0, width), dtype=np.float64)
        if backend in {
            SURFACE_POINTWISE_WEIGHTED_BACKEND,
            SURFACE_COMPONENT_PAIR_BACKEND,
        }:
            self._polynomial_x = np.ascontiguousarray(
                np.repeat(self.polynomial_values, 81, axis=0)
            )
            self._polynomial_y = np.ascontiguousarray(
                np.tile(self.polynomial_values, (81, 1))
            )
            coordinate_element, coordinate_identity = (
                scalar_hex_coordinate_basix_element(
                    mesh_data.mesh,
                    hexahedron_cell_type=basix.CellType.hexahedron,
                )
            )
            ffcx_options = get_ffcx_options()
            table_rtol = float(ffcx_options["table_rtol"])
            table_atol = float(ffcx_options["table_atol"])
            reference_vertices = np.asarray(
                basix.cell.geometry(basix.CellType.hexahedron), dtype=np.float64
            )
            facet_topology = basix.cell.topology(basix.CellType.hexahedron)[2]
            facet_jacobians = np.asarray(
                basix.cell.facet_jacobians(basix.CellType.hexahedron),
                dtype=np.float64,
            )
            if facet_jacobians.shape != (6, 3, 2) or len(facet_topology) != 6:
                raise NotImplementedError(
                    "live Basix hex facet Jacobian layout is unsupported"
                )
            derivative_indices = (
                basix.index(1, 0, 0),
                basix.index(0, 1, 0),
                basix.index(0, 0, 1),
            )
            self._geometry_tabulation_bytes_by_side: dict[str, int] = {}
            for side, endpoint_index in (("bottom", 0), ("top", 1)):
                facet_candidates = [
                    facet_index
                    for facet_index, vertices in enumerate(facet_topology)
                    if np.all(
                        reference_vertices[np.asarray(vertices, dtype=np.int64), 2]
                        == float(endpoint_index)
                    )
                ]
                if len(facet_candidates) != 1:
                    raise NotImplementedError(
                        f"hex has no unique canonical z={endpoint_index} face"
                    )
                face_index = int(facet_candidates[0])
                reference_points = np.asarray(
                    map_facet_points(
                        quadrilateral_points,
                        face_index,
                        "hexahedron",
                    ),
                    dtype=np.float64,
                )
                if reference_points.shape != (len(quadrilateral_points), 3):
                    raise NotImplementedError(
                        "FFCx reference-facet quadrature mapping has an unsupported shape"
                    )
                tabulation = np.asarray(
                    coordinate_element.tabulate(1, reference_points),
                    dtype=np.float64,
                )
                expected_shape = (
                    4,
                    len(quadrilateral_points),
                    int(coordinate_element.dim),
                    1,
                )
                if tabulation.shape != expected_shape or int(coordinate_element.dim) != 8:
                    raise NotImplementedError(
                        "live coordinate Basix tabulation has an unsupported shape"
                    )
                tabulation = clamp_ffcx_coordinate_table(
                    tabulation,
                    rtol=table_rtol,
                    atol=table_atol,
                )
                tabulation = roundtrip_ffcx_float64_array(
                    tabulation,
                    name=f"{side} FFCx coordinate table",
                )
                coordinate_values = np.ascontiguousarray(
                    tabulation[0, :, :, 0]
                )
                coordinate_derivatives = np.ascontiguousarray(
                    np.stack(
                        [tabulation[index, :, :, 0] for index in derivative_indices],
                        axis=2,
                    )
                )
                coordinate_values.flags.writeable = False
                coordinate_derivatives.flags.writeable = False
                self._geometry_face_tables[side] = (
                    coordinate_values,
                    coordinate_derivatives,
                )
                face_jacobian = np.array(
                    facet_jacobians[face_index], dtype=np.float64, copy=True
                )
                face_jacobian.flags.writeable = False
                self._geometry_face_local_facets[side] = face_index
                self._facet_jacobians_by_side[side] = face_jacobian
                self._geometry_tabulation_bytes_by_side[side] = int(
                    tabulation.nbytes
                )
                del tabulation, reference_points
            self._coordinate_element_identity = coordinate_identity
            self._ffcx_coordinate_table_options = {
                "table_rtol": table_rtol,
                "table_atol": table_atol,
                "clamp_function": "ffcx.ir.elementtables.clamp_table_small_numbers",
                "clamp_targets_in_order": [-1.0, 0.0, 1.0],
                "float_roundtrip": "ffcx.codegeneration.C.c_implementation.CFormatter(np.float64)._format_number",
                "formatter_identity": pointwise_formatter_facts,
            }
            self._facet_jacobians_sha256 = _surface_array_sha256(
                np.ascontiguousarray(facet_jacobians)
            )
        if self._geometry_cache_enabled:
            for array in (
                self.interval_points,
                self.interval_weights,
                self.quadrilateral_points,
                self.quadrilateral_weights,
                self._polynomial_x,
                self._polynomial_y,
            ):
                array.flags.writeable = False
        if self._weighted_moment_contraction is not None:
            self.polynomial_values.flags.writeable = False
            self._weighted_moment_basis_validation = (
                validate_q160_expanded_interval_tables(
                    self.polynomial_values,
                    self._polynomial_x,
                    self._polynomial_y,
                )
            )
        for side, endpoint_index in (("bottom", 0), ("top", 1)):
            if backend in {
                SURFACE_POINTWISE_WEIGHTED_BACKEND,
                SURFACE_COMPONENT_PAIR_BACKEND,
            }:
                table = face_trace_reference_tensor(
                    coefficient_matrix,
                    degree,
                    float(endpoint_index),
                    endpoint_values=endpoint_table[:, endpoint_index],
                )
                table.flags.writeable = False
                self._trace_tables[(side, 0)] = table
                self._trace_tables[(side, 1)] = table
            else:
                for component in (0, 1):
                    table = face_trace_table(
                        coefficient_matrix,
                        degree,
                        component,
                        float(endpoint_index),
                        endpoint_values=endpoint_table[:, endpoint_index],
                    )
                    table.flags.writeable = False
                    self._trace_tables[(side, component)] = table
        if self._prepare_trace_contraction:
            from .fullspace_surface_legendre import prepare_face_trace_contraction

            for side in ("bottom", "top"):
                self._prepared_trace_contractions[side] = (
                    prepare_face_trace_contraction(self._trace_tables[(side, 0)])
                )
        coefficient_matrix_bytes = int(coefficient_matrix.nbytes)
        coefficient_property_owns_array = bool(coefficient_matrix.flags.owndata)
        coefficient_property_aliases_basix_return = bool(
            isinstance(raw_coefficient_matrix, np.ndarray)
            and np.shares_memory(coefficient_matrix, raw_coefficient_matrix)
        )
        del coefficient_matrix, raw_coefficient_matrix

        self._records_by_side = self._build_facet_records(basix, cfg)
        boundary_plan_payload_bytes = int(
            sum(
                plan.cell_dofs.nbytes
                + plan.slave_positions.nbytes
                + sum(row.nbytes for row in plan.master_rows)
                + sum(row.nbytes for row in plan.coefficient_rows)
                for plan in self._cell_plans.values()
            )
        )
        boundary_slave_rows = int(
            sum(plan.slave_positions.size for plan in self._cell_plans.values())
        )
        self._moment_cache: dict[
            tuple[tuple[Any, ...], float, float], tuple[np.ndarray, np.ndarray]
        ] = {}
        self._moment_cache_limit = (
            SURFACE_MOMENT_CACHE_LIMIT
            if backend == SURFACE_LEGENDRE_BACKEND
            else 0
        )
        self._component_pair_stats = {
            "backend": backend,
            "degree": int(degree),
            "pair_call_count": 0,
            "paired_facet_count": 0,
            "max_staging_bytes": 0,
            "max_staging_facets": 0,
            "staging_release_count": 0,
            "staging_buffer_count_max": 0,
            "max_explicit_numpy_payload_upper_bytes": 0,
            "staging_max_bytes_limit": 64 * 1024 * 1024,
            "staging_max_facet_limit": 4096,
        }
        self.facts = {
            "backend": backend,
            "degree": degree,
            "element_family": "N1E",
            "element_variant": variant_name,
            "map_type": "covariantPiola",
            "polyset_type": "standard",
            "quadrature_degree": self.quadrature_degree,
            "quadrature_shape": [81, 81],
            "quadrature_order": "x-major/y-minor; exact Basix interval outer product",
                "quadrature_array_hashes": {
                    "interval_points_sha256": interval_points_sha256,
                    "interval_weights_sha256": interval_weights_sha256,
                    "quadrilateral_points_sha256": quadrilateral_points_sha256,
                    "quadrilateral_weights_sha256": quadrilateral_weights_sha256,
                    "hash_basis": "canonical float64 arrays consumed by this backend",
                },
            "quadrature_array_layout": {
                "interval_points_shape": list(self.interval_points.shape),
                "interval_weights_shape": list(self.interval_weights.shape),
                "polynomial_values_shape": list(self.polynomial_values.shape),
                "quadrilateral_points_shape": list(quadrilateral_points.shape),
                "quadrilateral_weights_shape": list(quadrilateral_weights.shape),
                "dtype": "float64",
            },
            "coefficient_matrix_shape": [expected_rows, 3 * width**3],
            "coefficient_matrix_bytes": coefficient_matrix_bytes,
            "coefficient_matrix_sha256": coefficient_matrix_sha256,
            "coefficient_array_owns_data": coefficient_property_owns_array,
            "coefficient_array_aliases_property_return": coefficient_property_aliases_basix_return,
            "coefficient_extra_copy_after_property": False,
            "mpc_global_arrays": {
                "storage_policy": "borrowed original-dtype ndarray views; no int64 cast, full diff, or full finite scan",
                "coefficients_dtype": self._mpc_coefficients.dtype.str,
                "coefficients_bytes_borrowed": int(self._mpc_coefficients.nbytes),
                "offsets_dtype": self._mpc_offsets.dtype.str,
                "offsets_bytes_borrowed": int(self._mpc_offsets.nbytes),
                "is_slave_dtype": self._mpc_is_slave.dtype.str,
                "is_slave_bytes_borrowed": int(self._mpc_is_slave.nbytes),
                "views_share_property_sources": dict(self._mpc_array_view_identity),
                "views_are_read_only": all(
                    not array.flags.writeable
                    for array in (
                        self._mpc_coefficients,
                        self._mpc_offsets,
                        self._mpc_is_slave,
                    )
                ),
                "boundary_context_fetches_global_slaves_array": False,
                "carrier_slave_inventory": "existing downstream carrier path, separate from this boundary plan",
                "validation_scope": "only boundary cell_to_slaves rows, corresponding offset pairs, masters, and coefficients",
            },
            "boundary_mpc_metadata": {
                "validated_cell_plan_count": int(len(self._cell_plans)),
                "validated_boundary_slave_rows": boundary_slave_rows,
                "newly_owned_array_payload_bytes": boundary_plan_payload_bytes,
                "cell_dofs_cached_once_per_boundary_cell": True,
                "master_and_coefficient_rows_cached_once": True,
                "offset_pairs_checked_individually": True,
                "empty_master_rows_rejected": True,
                "nonboundary_offset_rows_scanned": False,
            },
            "trace_table_bytes": int(
                sum(
                    value.nbytes
                    for value in {
                        id(array): array for array in self._trace_tables.values()
                    }.values()
                )
            ),
            "trace_table_entry_count": int(len(self._trace_tables)),
            "trace_table_unique_array_count": int(
                len({id(array) for array in self._trace_tables.values()})
            ),
            "moment_cache_entries_cap": self._moment_cache_limit,
            "moment_cache_numeric_array_payload_bytes_cap": int(
                self._moment_cache_limit
                * 2
                * width
                * np.dtype(np.complex128).itemsize
            ),
            "moment_cache_metadata_bytes": "python key/dict overhead not included",
            "candidate_memory_accounting": {
                "trace_tables_are_partial_not_total": True,
                "new_boundary_mpc_metadata_array_bytes": boundary_plan_payload_bytes,
                "borrowed_global_mpc_payload_bytes": int(
                    self._mpc_coefficients.nbytes
                    + self._mpc_offsets.nbytes
                    + self._mpc_is_slave.nbytes
                ),
                "c_property_array_bytes_during_table_build": coefficient_matrix_bytes,
                "c_property_array_released_after_table_build": True,
                "interval_and_legendre_arrays_owned_by_context_bytes": int(
                    self.interval_points.nbytes
                    + self.interval_weights.nbytes
                    + self.polynomial_values.nbytes
                ),
            },
            "face_facet_counts": {
                side: int(len(records)) for side, records in self._records_by_side.items()
            },
            "geometry_policy": "raw exact axis-aligned affine hex; unsupported maps reject",
            "standard_transform": "live element T_apply on real/imag lanes once per facet",
            "mpc_scatter": "qualified complex conjugate coefficient scatter; ghost reverse-add/forward-insert",
            "c_acquisition": "one live Basix C property read per degree; release local reference after trace tables",
            "construction_peak_arrays": {
                "persistent_C_if_property_allocates": coefficient_property_owns_array,
                "C_property_temporary_bytes": coefficient_matrix_bytes,
                "persistent_trace_tables_bytes": int(
                    sum(
                        array.nbytes
                        for array in {
                            id(value): value
                            for value in self._trace_tables.values()
                        }.values()
                    )
                ),
                "largest_single_local_complex_vector_bytes": int(expected_rows * 16),
                "local_MPC_scratch_vector_bytes": int(expected_rows * 16),
                "cell_mpc_plan_count": int(len(self._cell_plans)),
                "cell_mpc_plan_new_array_bytes": boundary_plan_payload_bytes,
            },
        }
        if self._weighted_moment_contraction is not None:
            self.facts["weighted_moment_contraction"] = {
                "algorithm": self._weighted_moment_contraction,
                "enabled_only_for_explicit_p6_q160_geometry_cache": True,
                "reduction_order": "T[a,j]=sum_i Px[i,a]*W[i,j]; M[a,b]=sum_j T[a,j]*Py[j,b]",
                "pointwise_weight_order": "(cofactor/determinant)*phase, then surface_measure, then full product weight once",
                "expanded_basis_validation": dict(
                    self._weighted_moment_basis_validation or {}
                ),
                "basis_hashes": {
                    "interval_values_sha256": _surface_array_sha256(
                        self.polynomial_values
                    ),
                    "expanded_x_sha256": _surface_array_sha256(
                        self._polynomial_x
                    ),
                    "expanded_y_sha256": _surface_array_sha256(
                        self._polynomial_y
                    ),
                    "quadrilateral_weights_sha256": self.facts[
                        "quadrature_array_hashes"
                    ]["quadrilateral_weights_sha256"],
                },
                "existing_single_lane_weighted_route_preserved": True,
                "ordinary_default_and_p3_routes_changed": False,
                "existing_numerical_gates_changed": False,
            }
            if (
                self._weighted_moment_contraction
                == SURFACE_WEIGHTED_MOMENT_CONTRACTION
            ):
                self.facts["weighted_moment_contraction"][
                    "named_array_payload_bytes"
                ] = {
                    "inverse_piola_values": 81 * 81 * 8,
                    "weighted_q_values": 81 * 81 * 16,
                    "x_contraction": 7 * 81 * 16,
                    "phase": 81 * 81 * 16,
                    "pair_output": 2 * 3 * 7 * 7 * 16,
                    "named_total": 276_216,
                    "scope": "named arrays only; finite-check masks, other temporaries, and BLAS workspace are not included; not RSS",
                }
            elif (
                self._weighted_moment_contraction
                == SURFACE_WEIGHTED_MOMENT_CONTRACTION_SIX_LANE
            ):
                self.facts["weighted_moment_contraction"][
                    "known_array_payload_per_active_call"
                ] = {
                    "W_shape": [2, 3, 81, 81],
                    "W_bytes": 2 * 3 * 81 * 81 * 16,
                    "T_shape": [2, 3, 7, 81],
                    "T_bytes": 2 * 3 * 7 * 81 * 16,
                    "W_plus_T_reused_workspace_bytes": 2 * 3 * 81 * 81 * 16
                    + 2 * 3 * 7 * 81 * 16,
                    "phase_inverse_and_owned_output_bytes": 6561 * 16
                    + 6561 * 8
                    + 2 * 3 * 7 * 7 * 16,
                    "all_known_numeric_arrays_bytes": 846456,
                    "qualification": "typed-array payload only; NumPy/BLAS temporaries and process RSS are not included",
                }
        if self._prepare_trace_contraction:
            self.facts["prepared_trace_contraction"] = {
                "explicit_profile_opt_in": True,
                "enabled_only_for_cached_p6_weighted_q160": True,
                "prepared_side_count": len(self._prepared_trace_contractions),
                "trace_array_payload_is_borrowed": True,
                "additional_trace_numeric_payload_bytes": 0,
                "per_call_trace_finite_scan": False,
                "per_call_moment_and_output_finite_checks": True,
                "expression": "ikab,kab->i; operand order unchanged",
                "ordinary_default_and_p3_routes_changed": False,
            }
        if self._geometry_cache_enabled:
            from .fullspace_surface_legendre import (
                SURFACE_GEOMETRY_CACHE_MAX_BYTES,
                surface_geometry_cache_payload_bytes,
            )

            cache_facet_count = sum(
                len(records) for records in self._records_by_side.values()
            )
            self.facts["pointwise_geometry_cache"] = {
                "explicit_profile_opt_in": True,
                "lifecycle": "one p6 carrier call; shared by all four side/component assemblers; finally released",
                "eligible_facet_count": cache_facet_count,
                "numeric_array_payload_bytes_preflight": surface_geometry_cache_payload_bytes(
                    point_count=int(self.quadrilateral_weights.size),
                    facet_count=cache_facet_count,
                ),
                "numeric_payload_limit_bytes": SURFACE_GEOMETRY_CACHE_MAX_BYTES,
                "payload_scope": "physical_coordinates+determinant+cofactors+surface_measure; excludes identity metadata and is not RSS",
                "jacobians_retained": False,
                "ordinary_and_p3_routes_changed": False,
            }
        if backend in {
            SURFACE_POINTWISE_WEIGHTED_BACKEND,
            SURFACE_COMPONENT_PAIR_BACKEND,
        }:
            geometry_dof_payload_bytes = int(
                sum(
                    record.geometry_dofs.nbytes
                    for records in self._records_by_side.values()
                    for record in records
                    if record.geometry_dofs is not None
                )
            )
            geometry_face_table_bytes = int(
                sum(
                    values.nbytes + derivatives.nbytes
                    for values, derivatives in self._geometry_face_tables.values()
                )
            )
            self.facts["quadrature_array_hashes"].update(
                {
                    "basix_quadrilateral_weights_source_sha256": basix_quadrilateral_weights_sha256,
                    "ffcx_cformatter_consumed_quadrilateral_weights_sha256": quadrilateral_weights_sha256,
                }
            )
            self.facts.update(
                pointwise_weight_formula=(
                    "sum_q quad_weight*cofactor_surface_measure*phase_at_live_"
                    "physical_point*inverseJ[reference_component,physical_component]"
                    "*Lx*Ly; q weight exactly once"
                ),
                pointwise_phase=(
                    "exp(i*(alpha*x(q)+gamma*y(q)+kz*z(q))); no origin phase"
                ),
                pointwise_piola_and_measure=(
                    "generated-kernel cofactor inverse of live coordinate-element "
                    "J(q); measure is the generated reference-facet-Jacobian "
                    "tangent cross-product norm; no extra width scale"
                ),
                reference_components_in_trace=(0, 1, 2),
                live_coordinate_element={
                    **self._coordinate_element_identity,
                    "tabulation_points": "FFCx map_facet_points for canonical z face",
                    "tabulation_clamp": dict(self._ffcx_coordinate_table_options),
                    "facet_jacobians_sha256": self._facet_jacobians_sha256,
                    "facet_jacobian_by_side": {
                        side: self._facet_jacobians_by_side[side].tolist()
                        for side in ("bottom", "top")
                    },
                },
                fixed_face_workspace_bytes={
                    "geometry_basis_values_and_derivatives": geometry_face_table_bytes,
                    "expanded_interval_polynomial_values": int(
                        self._polynomial_x.nbytes + self._polynomial_y.nbytes
                    ),
                    "owned_geometry_dof_indices_per_surface_facet": geometry_dof_payload_bytes,
                    "temporary_coordinate_tabulation_bytes_per_face": int(
                        max(self._geometry_tabulation_bytes_by_side.values(), default=0)
                    ),
                    "cached_pointwise_moments": False,
                    "moment_array_per_call_bytes": int(
                        3 * width * width * np.dtype(np.complex128).itemsize
                    ),
                    "moment_metadata_bytes": "NumPy/BLAS allocator overhead not included",
                },
                pointwise_selected_temporary_array_shapes={
                    "physical_coordinates": [6561, 3],
                    "jacobians": [6561, 3, 3],
                    "cofactor_jacobians": [6561, 3, 3],
                    "selected_inverse_column": [6561, 3],
                    "surface_measure": [6561],
                    "phase": [6561],
                    "weighted_basis": [width, 6561],
                    "moments": (
                        [2, 3, width, width]
                        if backend == SURFACE_COMPONENT_PAIR_BACKEND
                        else [3, width, width]
                    ),
                },
                pointwise_selected_temporary_numeric_payload_bytes={
                    "physical_coordinates": int(6561 * 3 * 8),
                    "jacobians": int(6561 * 9 * 8),
                    "cofactor_jacobians": int(6561 * 9 * 8),
                    "selected_inverse_column": int(6561 * 3 * 8),
                    "surface_measure": int(6561 * 8),
                    "phase": int(6561 * 16),
                    "quadrature_phase_weight": int(6561 * 16),
                    "weighted_basis": int(width * 6561 * 16),
                    "moments": int(
                        (6 if backend == SURFACE_COMPONENT_PAIR_BACKEND else 3)
                        * width
                        * width
                        * 16
                    ),
                    "payload_scope": (
                        "selected arrays only; determinant, adjugate, tangent, cross-product, "
                        "phase intermediates and other temporary arrays are not included"
                    ),
                    "other_temporary_array_payload_bytes": "unknown",
                },
                component_pair_staging_policy=(
                    {
                        "one_complex128_array_per_unique_phase_and_side": True,
                        "staging_bytes_formula": (
                            "actual_side_facet_count*local_cell_dof_count*16"
                        ),
                        "maximum_supported_staging_bytes": (
                            _SURFACE_COMPONENT_PAIR_STAGING_MAX_BYTES
                        ),
                        "maximum_supported_side_facets": (
                            _SURFACE_COMPONENT_PAIR_STAGING_MAX_FACETS
                        ),
                        "allocation_guard_precedes_numpy_allocation": True,
                        "record_key": "ordered_side_record_position_not_cell_id",
                        "release": "finally after component-one extraction or any exception",
                        "payload_scope": (
                            "staging value and bool flags only; does not represent RSS"
                        ),
                    }
                    if backend == SURFACE_COMPONENT_PAIR_BACKEND
                    else "not_applicable"
                ),
            )

        if backend == SURFACE_COMPONENT_PAIR_BACKEND:
            self._functional_store_identity_seed = {
                "element": element,
                "coefficient_matrix_shape": coefficient_matrix_shape,
                "coefficient_matrix_dtype": coefficient_matrix_dtype,
                "coefficient_matrix_sha256": coefficient_matrix_sha256,
                "endpoint_polynomial_table_sha256": _surface_array_sha256(
                    endpoint_table
                ),
            }

    def _initialize_functional_store_identity(
        self,
        *,
        element: Any,
        coefficient_matrix_shape: tuple[int, ...],
        coefficient_matrix_dtype: str,
        coefficient_matrix_sha256: str,
        endpoint_polynomial_table_sha256: str,
    ) -> None:
        """Snapshot the bounded immutable p6 numerical context once.

        The store identity deliberately excludes the mutable ``facts`` tree,
        paths, timers, cache counters, and Python object IDs.  Arrays remain
        owned by this live context and are checked by reference/read-only state
        when a store is opened; their content digests are computed only here,
        never in the per-mode carrier loop.
        """

        import copy

        from .fullspace_surface_legendre import (
            SURFACE_COMPONENT_PAIR_BACKEND,
            SURFACE_WEIGHTED_MOMENT_CONTRACTIONS,
        )

        if (
            self.backend != SURFACE_COMPONENT_PAIR_BACKEND
            or self.degree != 6
            or self.quadrature_degree != 160
            or not self._geometry_cache_enabled
            or self._weighted_moment_contraction
            not in SURFACE_WEIGHTED_MOMENT_CONTRACTIONS
            or not self._prepare_trace_contraction
            or set(self._geometry_face_tables) != {"bottom", "top"}
            or set(self._facet_jacobians_by_side) != {"bottom", "top"}
        ):
            raise ValueError(
                "p6 functional-store identity requires the prepared cached q160 context"
            )

        arrays: dict[str, np.ndarray] = {
            "interval_points": self.interval_points,
            "interval_weights": self.interval_weights,
            "quadrilateral_points": self.quadrilateral_points,
            "quadrilateral_weights": self.quadrilateral_weights,
            "polynomial_values": self.polynomial_values,
            "expanded_polynomial_x": self._polynomial_x,
            "expanded_polynomial_y": self._polynomial_y,
        }
        for side in ("bottom", "top"):
            values, derivatives = self._geometry_face_tables[side]
            arrays[f"coordinate_values_{side}"] = values
            arrays[f"coordinate_derivatives_{side}"] = derivatives
            arrays[f"facet_jacobian_{side}"] = self._facet_jacobians_by_side[side]
            for component in (0, 1):
                arrays[f"trace_{side}_{component}"] = self._trace_tables[
                    (side, component)
                ]

        descriptors: dict[str, dict[str, Any]] = {}
        for name, array in arrays.items():
            value = np.asarray(array)
            if (
                not isinstance(array, np.ndarray)
                or value is not array
                or value.dtype.hasobject
                or not value.flags.c_contiguous
                or value.flags.writeable
            ):
                raise ValueError(
                    f"p6 functional-store context array {name} is not immutable contiguous data"
                )
            descriptors[name] = {
                "dtype": value.dtype.str,
                "shape": [int(item) for item in value.shape],
                "nbytes": int(value.nbytes),
                "sha256": _surface_array_sha256(value),
            }

        coordinate_options = dict(self._ffcx_coordinate_table_options)
        formatter_identity = dict(coordinate_options.pop("formatter_identity", {}))
        formatter_identity.pop("module_path", None)
        if not formatter_identity.get("module_sha256"):
            raise ValueError("p6 functional-store FFCx formatter identity is missing")
        coordinate_options["formatter_identity"] = formatter_identity

        prepared_trace: dict[str, Any] = {}
        for side in ("bottom", "top"):
            trace = self._trace_tables[(side, 0)]
            if self._trace_tables[(side, 1)] is not trace:
                raise ValueError("p6 paired components do not share the live trace table")
            plan = self._prepared_trace_contractions.get(side)
            if plan is None or plan.trace_tensor is not trace:
                raise ValueError("p6 prepared trace plan does not bind its live trace table")
            prepared_trace[side] = {
                "expression": "ikab,kab->i",
                "einsum_path": copy.deepcopy(plan.einsum_path),
                "trace_sha256": descriptors[f"trace_{side}_0"]["sha256"],
            }

        basix_hash = getattr(element, "hash", None)
        if not callable(basix_hash):
            raise ValueError("p6 functional-store Basix element hash is unavailable")
        self._functional_store_identity_descriptor = {
            "schema": "task39extra.p6-paired-surface-context-numerical-provider.v1",
            "backend": self.backend,
            "degree": int(self.degree),
            "quadrature_degree": int(self.quadrature_degree),
            "weighted_moment_contraction": str(self._weighted_moment_contraction),
            "prepared_trace_contraction": {
                "enabled": True,
                "expression": "ikab,kab->i",
                "side_plans": prepared_trace,
            },
            "element": {
                "basix_hash": int(basix_hash()),
                "family": str(element.family),
                "degree": int(element.degree),
                "cell_type": str(element.cell_type),
                "value_size": int(element.value_size),
                "map_type": str(element.map_type),
                "polyset_type": str(element.polyset_type),
                "lagrange_variant": str(
                    getattr(getattr(element, "lagrange_variant", None), "name", "unknown")
                ).lower(),
                "coefficient_matrix": {
                    "dtype": str(coefficient_matrix_dtype),
                    "shape": [int(item) for item in coefficient_matrix_shape],
                    "sha256": str(coefficient_matrix_sha256),
                },
                "endpoint_polynomial_table_sha256": str(
                    endpoint_polynomial_table_sha256
                ),
            },
            "quadrature_and_basis_arrays": {
                name: descriptors[name]
                for name in (
                    "interval_points",
                    "interval_weights",
                    "quadrilateral_points",
                    "quadrilateral_weights",
                    "polynomial_values",
                    "expanded_polynomial_x",
                    "expanded_polynomial_y",
                )
            },
            "coordinate_element": {
                **copy.deepcopy(self._coordinate_element_identity),
                "ffcx_table_options": coordinate_options,
                "consumed_tables_by_side": {
                    side: {
                        "values": descriptors[f"coordinate_values_{side}"],
                        "derivatives": descriptors[
                            f"coordinate_derivatives_{side}"
                        ],
                        "facet_jacobian": descriptors[f"facet_jacobian_{side}"],
                        "local_facet": int(self._geometry_face_local_facets[side]),
                    }
                    for side in ("bottom", "top")
                },
            },
            "trace_reference_tensors": {
                side: descriptors[f"trace_{side}_0"]
                for side in ("bottom", "top")
                },
            }
        self._functional_store_identity_array_refs = arrays

    def functional_store_identity_descriptor(self) -> dict[str, Any]:
        """Return the p6 numerical context descriptor after cheap lineage checks."""

        import copy

        descriptor = getattr(self, "_functional_store_identity_descriptor", None)
        references = getattr(self, "_functional_store_identity_array_refs", None)
        if descriptor is None or references is None:
            seed = getattr(self, "_functional_store_identity_seed", None)
            if not isinstance(seed, dict):
                raise ValueError("p6 functional-store numerical identity is unavailable")
            self._initialize_functional_store_identity(**seed)
            descriptor = getattr(self, "_functional_store_identity_descriptor", None)
            references = getattr(self, "_functional_store_identity_array_refs", None)
        if not isinstance(descriptor, dict) or not isinstance(references, dict):
            raise ValueError("p6 functional-store numerical identity is unavailable")
        current: dict[str, np.ndarray] = {
            "interval_points": self.interval_points,
            "interval_weights": self.interval_weights,
            "quadrilateral_points": self.quadrilateral_points,
            "quadrilateral_weights": self.quadrilateral_weights,
            "polynomial_values": self.polynomial_values,
            "expanded_polynomial_x": self._polynomial_x,
            "expanded_polynomial_y": self._polynomial_y,
        }
        for side in ("bottom", "top"):
            values, derivatives = self._geometry_face_tables[side]
            current[f"coordinate_values_{side}"] = values
            current[f"coordinate_derivatives_{side}"] = derivatives
            current[f"facet_jacobian_{side}"] = self._facet_jacobians_by_side[side]
            for component in (0, 1):
                current[f"trace_{side}_{component}"] = self._trace_tables[
                    (side, component)
                ]
        if set(current) != set(references):
            raise ValueError("p6 functional-store numerical context layout changed")
        for name, expected in references.items():
            actual = current[name]
            if actual is not expected or actual.flags.writeable:
                raise ValueError(
                    f"p6 functional-store immutable context lineage changed: {name}"
                )
        return copy.deepcopy(descriptor)

    def _cell_mpc_plan(self, cell: int) -> _SurfaceCellMpcPlan:
        from .fullspace_surface_legendre import validate_boundary_mpc_row

        cell = int(cell)
        cached = self._cell_plans.get(cell)
        if cached is not None:
            return cached
        form_dofs = np.asarray(self.function_space.dofmap.cell_dofs(cell))
        mpc_dofs = np.asarray(self.mpc.function_space.dofmap.cell_dofs(cell))
        if (
            form_dofs.ndim != 1
            or mpc_dofs.ndim != 1
            or not np.issubdtype(form_dofs.dtype, np.integer)
            or not np.issubdtype(mpc_dofs.dtype, np.integer)
        ):
            raise ValueError("surface/MPC cell DOF arrays are malformed")
        cell_dofs = np.array(form_dofs, dtype=np.int32, copy=True)
        index_map = self.mpc.function_space.dofmap.index_map
        local_storage_size = int(index_map.size_local + index_map.num_ghosts)
        if (
            not np.array_equal(cell_dofs, mpc_dofs)
            or np.unique(cell_dofs).size != cell_dofs.size
            or (
                cell_dofs.size
                and (cell_dofs.min() < 0 or cell_dofs.max() >= local_storage_size)
            )
        ):
            raise ValueError("surface/MPC cell DOF maps are incompatible")
        local_positions = {int(dof): position for position, dof in enumerate(cell_dofs)}
        slaves = np.asarray(self._cell_to_slaves.links(cell))
        if slaves.ndim != 1 or not np.issubdtype(slaves.dtype, np.integer):
            raise ValueError("surface cell_to_slaves row is malformed")
        positions: list[int] = []
        master_rows: list[np.ndarray] = []
        coefficient_rows: list[np.ndarray] = []
        seen_slaves: set[int] = set()
        for slave_value in slaves:
            slave = int(slave_value)
            if (
                slave < 0
                or slave in seen_slaves
                or slave not in local_positions
            ):
                raise ValueError("surface cell_to_slaves metadata is inconsistent")
            seen_slaves.add(slave)
            masters_source = np.asarray(self._masters.links(slave))
            try:
                masters, coefficients = validate_boundary_mpc_row(
                    slave,
                    self._mpc_offsets,
                    self._mpc_coefficients,
                    self._mpc_is_slave,
                    masters_source,
                    local_storage_size,
                )
            except ValueError as exc:
                raise NotImplementedError(str(exc)) from exc
            positions.append(local_positions[slave])
            master_rows.append(masters)
            coefficient_rows.append(coefficients)
        cell_dofs.flags.writeable = False
        slave_positions = np.asarray(positions, dtype=np.int32)
        slave_positions.flags.writeable = False
        plan = _SurfaceCellMpcPlan(
            cell_dofs=cell_dofs,
            slave_positions=slave_positions,
            master_rows=tuple(master_rows),
            coefficient_rows=tuple(coefficient_rows),
        )
        self._cell_plans[cell] = plan
        return plan

    def _build_facet_records(self, basix: Any, cfg: Any) -> dict[str, tuple[_SurfaceFacetRecord, ...]]:
        from .fullspace_surface_legendre import (
            SURFACE_COMPONENT_PAIR_BACKEND,
            SURFACE_POINTWISE_WEIGHTED_BACKEND,
        )

        mesh = self.mesh_data.mesh
        topology = mesh.topology
        tdim = int(topology.dim)
        if tdim != 3:
            raise NotImplementedError("Legendre surface backend requires a 3D mesh")
        fdim = tdim - 1
        topology.create_connectivity(fdim, tdim)
        topology.create_connectivity(tdim, fdim)
        topology.create_entity_permutations()
        self._cell_permutations = np.asarray(
            topology.get_cell_permutation_info(), dtype=np.uint32
        )
        facet_to_cell = topology.connectivity(fdim, tdim)
        cell_to_facet = topology.connectivity(tdim, fdim)
        reference_vertices = np.asarray(
            basix.cell.geometry(basix.CellType.hexahedron), dtype=np.float64
        )
        facet_topology = basix.cell.topology(basix.CellType.hexahedron)[fdim]
        if reference_vertices.shape != (8, 3) or len(facet_topology) != 6:
            raise NotImplementedError("Basix hexahedron reference topology is unsupported")
        geometry_dofmap = mesh.geometry.dofmap
        geometry_coordinates = np.asarray(mesh.geometry.x, dtype=np.float64)
        local_cell_count = int(topology.index_map(tdim).size_local)
        records_by_side: dict[str, tuple[_SurfaceFacetRecord, ...]] = {}
        for side, tag, endpoint in (
            ("bottom", int(cfg.tags.z_min), 0.0),
            ("top", int(cfg.tags.z_max), 1.0),
        ):
            facets = np.asarray(self.mesh_data.facet_tags.find(tag), dtype=np.int32)
            if not facets.size:
                raise ValueError(f"Legendre surface tag {tag} has no local facets")
            records: list[_SurfaceFacetRecord] = []
            seen_facets: set[int] = set()
            for facet_value in facets:
                facet = int(facet_value)
                if facet in seen_facets:
                    raise ValueError("surface facet tag contains duplicate facets")
                seen_facets.add(facet)
                adjacent = np.asarray(facet_to_cell.links(facet), dtype=np.int32)
                if adjacent.size != 1:
                    raise NotImplementedError("Legendre surface backend accepts exterior facets only")
                cell = int(adjacent[0])
                if cell < 0 or cell >= local_cell_count:
                    raise NotImplementedError("Legendre surface backend requires owned exterior cells")
                cell_facets = np.asarray(cell_to_facet.links(cell), dtype=np.int32)
                local_matches = np.flatnonzero(cell_facets == facet)
                if local_matches.size != 1:
                    raise ValueError("surface facet has no unique local hex facet index")
                local_facet = int(local_matches[0])
                if (
                    self.backend
                    in {
                        SURFACE_POINTWISE_WEIGHTED_BACKEND,
                        SURFACE_COMPONENT_PAIR_BACKEND,
                    }
                    and local_facet != self._geometry_face_local_facets[side]
                ):
                    raise NotImplementedError(
                        "tagged surface facet does not use the validated FFCx z-face map"
                    )
                geometry_dofs = np.asarray(geometry_dofmap[cell], dtype=np.int64)
                if geometry_dofs.shape != (8,):
                    raise NotImplementedError("Legendre surface backend requires linear hex geometry")
                raw_vertices = geometry_coordinates[geometry_dofs]
                if raw_vertices.shape != reference_vertices.shape or not np.isfinite(raw_vertices).all():
                    raise ValueError("raw affine hex coordinates are malformed")
                low = np.min(raw_vertices, axis=0)
                high = np.max(raw_vertices, axis=0)
                if np.any(high <= low):
                    raise NotImplementedError("Legendre surface backend rejects degenerate hex cells")
                for axis in range(3):
                    expected_axis = np.where(reference_vertices[:, axis] == 0.0, low[axis], high[axis])
                    if not np.array_equal(raw_vertices[:, axis], expected_axis):
                        raise NotImplementedError(
                            "Legendre surface backend rejects noncanonical/skew raw hex geometry"
                        )
                ref_face_vertices = np.asarray(facet_topology[local_facet], dtype=np.int64)
                ref_face_z = reference_vertices[ref_face_vertices, 2]
                if ref_face_z.size != 4 or not np.all(ref_face_z == endpoint):
                    raise NotImplementedError(
                        f"{side} tagged facet is not the canonical reference z={endpoint:g} face"
                    )
                z_face = float(low[2] if endpoint == 0.0 else high[2])
                physical_face_z = raw_vertices[ref_face_vertices, 2]
                if not np.all(physical_face_z == z_face):
                    raise NotImplementedError("raw tagged face does not map to one physical z plane")
                record_geometry_dofs = None
                if self.backend in {
                    SURFACE_POINTWISE_WEIGHTED_BACKEND,
                    SURFACE_COMPONENT_PAIR_BACKEND,
                }:
                    record_geometry_dofs = np.asarray(
                        geometry_dofs, dtype=np.int32
                    ).copy()
                    record_geometry_dofs.flags.writeable = False
                records.append(
                    _SurfaceFacetRecord(
                        cell=cell,
                        geometry_dofs=record_geometry_dofs,
                        local_facet=local_facet,
                        zeta_face=endpoint,
                        x0=float(low[0]),
                        y0=float(low[1]),
                        hx=float(high[0] - low[0]),
                        hy=float(high[1] - low[1]),
                        z_face=z_face,
                        cell_plan=self._cell_mpc_plan(cell),
                    )
                )
            records_by_side[side] = tuple(records)
        return records_by_side

    def trace_table(self, side: str, component: int) -> np.ndarray:
        try:
            return self._trace_tables[(str(side), int(component))]
        except KeyError as exc:
            raise ValueError("unsupported Legendre surface side/component") from exc

    def prepared_trace_contraction(self, side: str) -> Any:
        if not self._prepare_trace_contraction:
            raise RuntimeError("prepared trace contraction is not enabled")
        try:
            return self._prepared_trace_contractions[str(side)]
        except KeyError as exc:
            raise ValueError("unsupported prepared trace side") from exc

    def release_prepared_trace_contractions(self) -> None:
        if self._prepared_trace_contractions:
            self._prepared_trace_contractions.clear()
            self._prepared_trace_release_count += 1

    def records(self, side: str) -> tuple[_SurfaceFacetRecord, ...]:
        return self._records_by_side[str(side)]

    def begin_geometry_cache(self, *, max_bytes: int | None = None) -> None:
        if not self._geometry_cache_enabled:
            raise ValueError("surface geometry cache is not enabled for this context")
        if self._geometry_cache is not None:
            raise RuntimeError("surface geometry cache is already active")
        self._geometry_cache_last_facts = None
        limit = (
            self._geometry_cache_limit_bytes
            if max_bytes is None
            else int(max_bytes)
        )
        self._geometry_cache = _SurfacePointwiseGeometryCache(
            self, max_bytes=limit
        )
        if (
            self._weighted_moment_contraction
            == SURFACE_WEIGHTED_MOMENT_CONTRACTION_SIX_LANE
        ):
            try:
                from .fullspace_surface_legendre import (
                    Q160SixLaneWeightedMomentWorkspace,
                )

                self._six_lane_moment_workspace = (
                    Q160SixLaneWeightedMomentWorkspace()
                )
            except BaseException:
                self.end_geometry_cache()
                raise

    def end_geometry_cache(self) -> None:
        cache = self._geometry_cache
        try:
            if cache is not None:
                self._geometry_cache_last_facts = cache.release()
        finally:
            self._geometry_cache = None
            try:
                self.release_prepared_trace_contractions()
            finally:
                workspace, self._six_lane_moment_workspace = (
                    self._six_lane_moment_workspace,
                    None,
                )
                if workspace is not None:
                    workspace.release()

    def geometry_cache_facts(self) -> dict[str, Any] | str:
        if self._geometry_cache is not None:
            return self._geometry_cache.facts()
        if self._geometry_cache_last_facts is not None:
            return dict(self._geometry_cache_last_facts)
        return "not_started"

    def _build_pointwise_geometry_entry(
        self, side: str, record: _SurfaceFacetRecord
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        from .fullspace_surface_legendre import (
            _pointwise_surface_geometry_terms,
            map_coordinate_quadrature,
        )

        if side not in {"bottom", "top"} or record.geometry_dofs is None:
            raise ValueError("surface geometry cache received an unsupported facet")
        if record.local_facet != self._geometry_face_local_facets[side]:
            raise ValueError("surface geometry cache facet differs from its bound side")
        coordinate_values, coordinate_derivatives = self._geometry_face_tables[side]
        coordinate_snapshot = np.array(
            self._geometry_coordinates[record.geometry_dofs],
            dtype=np.float64,
            copy=True,
            order="C",
        )
        physical_coordinates, jacobians = map_coordinate_quadrature(
            coordinate_snapshot, coordinate_values, coordinate_derivatives
        )
        determinant, cofactors, surface_measure = _pointwise_surface_geometry_terms(
            jacobians, self._facet_jacobians_by_side[side]
        )
        return (
            coordinate_snapshot,
            physical_coordinates,
            determinant,
            cofactors,
            surface_measure,
        )

    def moments(self, mode: PortMode3D, record: _SurfaceFacetRecord) -> tuple[np.ndarray, np.ndarray]:
        from .fullspace_surface_legendre import fourier_legendre_moment

        phase_key = (
            str(mode.side),
            int(mode.m),
            int(mode.n),
            complex(mode.alpha),
            complex(mode.gamma),
            complex(mode.k_vector[2]),
        )
        key = (phase_key, float(record.hx), float(record.hy))
        cached = self._moment_cache.get(key)
        if cached is not None:
            return cached
        if len(self._moment_cache) >= self._moment_cache_limit:
            self._moment_cache.pop(next(iter(self._moment_cache)))
        x_moment = fourier_legendre_moment(
            self.interval_points,
            self.interval_weights,
            self.degree,
            complex(mode.alpha),
            record.hx,
            polynomial_values=self.polynomial_values,
        )
        y_moment = fourier_legendre_moment(
            self.interval_points,
            self.interval_weights,
            self.degree,
            complex(mode.gamma),
            record.hy,
            polynomial_values=self.polynomial_values,
        )
        cached = (x_moment, y_moment)
        self._moment_cache[key] = cached
        return cached

    def pointwise_moments(
        self, mode: PortMode3D, record: _SurfaceFacetRecord, physical_component: int
    ) -> np.ndarray:
        from .fullspace_surface_legendre import SURFACE_POINTWISE_WEIGHTED_BACKEND

        if self.backend != SURFACE_POINTWISE_WEIGHTED_BACKEND:
            raise ValueError("pointwise moments are unavailable for the old backend")
        from .fullspace_surface_legendre import (
            map_coordinate_quadrature,
            pointwise_weighted_legendre_moments,
        )

        side = "bottom" if record.zeta_face == 0.0 else "top"
        if record.local_facet != self._geometry_face_local_facets[side]:
            raise NotImplementedError(
                "surface record differs from the validated FFCx local face"
            )
        coordinate_values, coordinate_derivatives = self._geometry_face_tables[side]
        if record.geometry_dofs is None:
            raise RuntimeError("pointwise surface record has no geometry DOF map")
        coordinate_dofs = self._geometry_coordinates[record.geometry_dofs]
        physical_coordinates, jacobians = map_coordinate_quadrature(
            coordinate_dofs,
            coordinate_values,
            coordinate_derivatives,
        )
        return pointwise_weighted_legendre_moments(
            physical_coordinates,
            jacobians,
            self.quadrilateral_weights,
            self._polynomial_x,
            self._polynomial_y,
            facet_jacobian=self._facet_jacobians_by_side[side],
            alpha=complex(mode.alpha),
            gamma=complex(mode.gamma),
            kz=complex(mode.k_vector[2]),
            physical_component=int(physical_component),
        )

    def pointwise_moments_pair(
        self,
        mode: PortMode3D,
        record: _SurfaceFacetRecord,
        *,
        record_position: int | None = None,
    ) -> np.ndarray:
        from .fullspace_surface_legendre import (
            SURFACE_COMPONENT_PAIR_BACKEND,
            map_coordinate_quadrature,
            pointwise_weighted_legendre_moments_pair,
            pointwise_weighted_legendre_moments_pair_from_geometry,
            pointwise_weighted_legendre_moments_pair_from_geometry_x_then_y,
            pointwise_weighted_legendre_moments_pair_from_geometry_six_lane_x_then_y,
        )

        if self.backend != SURFACE_COMPONENT_PAIR_BACKEND:
            raise ValueError("paired moments require the component-pair backend")
        side = "bottom" if record.zeta_face == 0.0 else "top"
        if str(mode.side) != side:
            raise ValueError("paired surface mode side differs from its facet record")
        if record.local_facet != self._geometry_face_local_facets[side]:
            raise NotImplementedError(
                "surface record differs from the validated FFCx local face"
            )
        if record.geometry_dofs is None:
            raise RuntimeError("pointwise surface record has no geometry DOF map")
        if (
            self._weighted_moment_contraction
            == SURFACE_WEIGHTED_MOMENT_CONTRACTION_SIX_LANE
            and self._geometry_cache is None
        ):
            raise RuntimeError(
                "six-lane weighted moments require their active cached workspace"
            )
        if self._geometry_cache is not None:
            if record_position is None:
                raise ValueError("cached geometry access requires the ordered record position")
            physical, determinant, cofactors, surface_measure = self._geometry_cache.get(
                self, side, record_position, record
            )
            if self._weighted_moment_contraction == SURFACE_WEIGHTED_MOMENT_CONTRACTION:
                return pointwise_weighted_legendre_moments_pair_from_geometry_x_then_y(
                    physical,
                    self.quadrilateral_weights,
                    self.polynomial_values,
                    determinant,
                    cofactors,
                    surface_measure,
                    alpha=complex(mode.alpha),
                    gamma=complex(mode.gamma),
                    kz=complex(mode.k_vector[2]),
                )
            if (
                self._weighted_moment_contraction
                == SURFACE_WEIGHTED_MOMENT_CONTRACTION_SIX_LANE
            ):
                workspace = self._six_lane_moment_workspace
                if workspace is None:
                    raise RuntimeError("six-lane weighted-moment workspace is not active")
                return pointwise_weighted_legendre_moments_pair_from_geometry_six_lane_x_then_y(
                    physical,
                    self.quadrilateral_weights,
                    self.polynomial_values,
                    determinant,
                    cofactors,
                    surface_measure,
                    alpha=complex(mode.alpha),
                    gamma=complex(mode.gamma),
                    kz=complex(mode.k_vector[2]),
                    workspace=workspace,
                )
            if self._weighted_moment_contraction is not None:
                raise RuntimeError("bound weighted-moment contraction identity changed")
            return pointwise_weighted_legendre_moments_pair_from_geometry(
                physical,
                self.quadrilateral_weights,
                self._polynomial_x,
                self._polynomial_y,
                determinant,
                cofactors,
                surface_measure,
                alpha=complex(mode.alpha),
                gamma=complex(mode.gamma),
                kz=complex(mode.k_vector[2]),
            )
        coordinate_values, coordinate_derivatives = self._geometry_face_tables[side]
        coordinate_dofs = self._geometry_coordinates[record.geometry_dofs]
        physical_coordinates, jacobians = map_coordinate_quadrature(
            coordinate_dofs, coordinate_values, coordinate_derivatives
        )
        return pointwise_weighted_legendre_moments_pair(
            physical_coordinates,
            jacobians,
            self.quadrilateral_weights,
            self._polynomial_x,
            self._polynomial_y,
            facet_jacobian=self._facet_jacobians_by_side[side],
            alpha=complex(mode.alpha),
            gamma=complex(mode.gamma),
            kz=complex(mode.k_vector[2]),
        )

    def component_pair_stats_facts(self) -> dict[str, Any]:
        facts = dict(self._component_pair_stats)
        if self._geometry_cache_enabled:
            facts["geometry_cache"] = self.geometry_cache_facts()
        return facts

    def release_mode(self, mode: PortMode3D) -> None:
        phase_key = (
            str(mode.side),
            int(mode.m),
            int(mode.n),
            complex(mode.alpha),
            complex(mode.gamma),
            complex(mode.k_vector[2]),
        )
        for key in tuple(self._moment_cache):
            if key[0] == phase_key:
                del self._moment_cache[key]


_SURFACE_COMPONENT_PAIR_STAGING_MAX_BYTES = 64 * 1024 * 1024
_SURFACE_COMPONENT_PAIR_STAGING_MAX_FACETS = 4096


def _surface_pair_phase_key(mode: PortMode3D) -> tuple[Any, ...]:
    return (
        str(mode.side),
        int(mode.m),
        int(mode.n),
        complex(mode.alpha),
        complex(mode.gamma),
        complex(mode.k_vector[2]),
    )


class _SurfaceComponentPairStaging:
    """Record-position staging for the already transformed second component."""

    def __init__(
        self,
        records: Sequence[_SurfaceFacetRecord],
        *,
        primary: Any,
        companion: Any,
        mode: PortMode3D,
        mpc: Any,
        workspace: Any,
    ) -> None:
        self.records = tuple(records)
        if (
            primary is companion
            or primary.context is not companion.context
            or primary.context.backend != SURFACE_COMPONENT_PAIR_BACKEND
            or str(primary.side) != str(companion.side)
            or str(mode.side) != str(primary.side)
            or int(primary.component) != 0
            or int(companion.component) != 1
            or primary.function_space is not companion.function_space
            or primary.mesh_data is not companion.mesh_data
            or getattr(primary.context, "mpc", None) is not mpc
            or getattr(workspace, "_mpc", None) is not mpc
            or getattr(workspace, "_function_space", None)
            is not primary.function_space
            or getattr(workspace, "_mesh_data", None) is not primary.mesh_data
            or int(primary.tag) != int(companion.tag)
            or id(primary) not in getattr(workspace, "_allowed_assembler_ids", set())
            or id(companion) not in getattr(workspace, "_allowed_assembler_ids", set())
        ):
            raise ValueError("component-pair assembler or workspace identity differs")
        if not self.records:
            raise ValueError("component-pair staging requires at least one facet")
        if len(self.records) > _SURFACE_COMPONENT_PAIR_STAGING_MAX_FACETS:
            raise ValueError("component-pair facet count exceeds the supported bound")
        dimensions = tuple(
            int(np.asarray(record.cell_plan.cell_dofs).size)
            for record in self.records
        )
        if not dimensions or min(dimensions) <= 0 or len(set(dimensions)) != 1:
            raise ValueError("component-pair cells must have one positive local dimension")
        self.local_dimension = dimensions[0]
        self.staging_bytes = (
            len(self.records)
            * self.local_dimension
            * int(np.dtype(np.complex128).itemsize)
        )
        if self.staging_bytes > _SURFACE_COMPONENT_PAIR_STAGING_MAX_BYTES:
            raise ValueError("component-pair staging bytes exceed the supported bound")
        if tuple(map(id, self.records)) != tuple(
            map(id, primary.context.records(primary.side))
        ):
            raise ValueError("component-pair records differ from the bound side order")
        self.record_ids = tuple(id(record) for record in self.records)
        self.primary_assembler_id = id(primary)
        self.companion_assembler_id = id(companion)
        self.context_id = id(primary.context)
        self.side = str(primary.side)
        self.phase_key = _surface_pair_phase_key(mode)
        self.mpc_id = id(mpc)
        self.workspace_id = id(workspace)
        self.workspace = workspace
        self.degree = int(primary.context.degree)
        self.component_ids = (int(primary.component), int(companion.component))
        self.values: np.ndarray | None = np.empty(
            (len(self.records), self.local_dimension), dtype=np.complex128
        )
        self._filled: np.ndarray | None = np.zeros(len(self.records), dtype=np.bool_)

    def assert_binding(
        self,
        *,
        primary: Any,
        companion: Any,
        mode: PortMode3D,
        mpc: Any,
        workspace: Any,
        records: Sequence[_SurfaceFacetRecord],
    ) -> None:
        actual_records = tuple(records)
        if (
            primary.context is not companion.context
            or id(primary) != self.primary_assembler_id
            or id(companion) != self.companion_assembler_id
            or id(primary.context) != self.context_id
            or primary.context.backend != SURFACE_COMPONENT_PAIR_BACKEND
            or getattr(primary.context, "mpc", None) is not mpc
            or str(primary.side) != self.side
            or str(companion.side) != self.side
            or str(mode.side) != self.side
            or int(primary.component) != 0
            or int(companion.component) != 1
            or self.component_ids != (0, 1)
            or id(mpc) != self.mpc_id
            or id(workspace) != self.workspace_id
            or getattr(workspace, "_function_space", None)
            is not primary.function_space
            or getattr(workspace, "_mesh_data", None) is not primary.mesh_data
            or int(primary.tag) != int(companion.tag)
            or int(primary.context.degree) != self.degree
            or int(companion.context.degree) != self.degree
            or _surface_pair_phase_key(mode) != self.phase_key
            or tuple(id(record) for record in actual_records) != self.record_ids
        ):
            raise ValueError("component-pair staging identity, phase or record order differs")
        if self.values is None or self._filled is None:
            raise RuntimeError("component-pair staging was already released")

    def store(
        self, record_position: int, record: _SurfaceFacetRecord, values: np.ndarray
    ) -> None:
        position = int(record_position)
        if position < 0 or position >= len(self.record_ids):
            raise IndexError("component-pair record position is out of range")
        if id(record) != self.record_ids[position]:
            raise ValueError("component-pair staging record position differs")
        array = np.asarray(values, dtype=np.complex128)
        if array.shape != (self.local_dimension,) or not np.isfinite(array).all():
            raise ValueError("component-pair local vector is invalid")
        if self.values is None or self._filled is None:
            raise RuntimeError("component-pair staging was already released")
        self.values[position] = array
        self._filled[position] = True

    def assert_complete(self) -> None:
        if self._filled is None or not bool(np.all(self._filled)):
            raise RuntimeError("component-pair staging has missing record positions")

    def get(self, record_position: int, record: _SurfaceFacetRecord) -> np.ndarray:
        position = int(record_position)
        if position < 0 or position >= len(self.record_ids):
            raise IndexError("component-pair record position is out of range")
        if id(record) != self.record_ids[position]:
            raise ValueError("component-pair replay record order differs")
        if (
            self.values is None
            or self._filled is None
            or not bool(self._filled[position])
        ):
            raise RuntimeError("component-pair record was not staged")
        return self.values[position]

    def release(self) -> None:
        self.values = None
        self._filled = None
        self.record_ids = ()
        self.records = ()
        self.workspace = None


class _SurfaceLegendreMomentAssembler:
    """Opt-in q160 Legendre face functional for one side/component."""

    surface_backend = "q160_affine_hex_fourier_legendre_v1"

    def __init__(
        self,
        context: _SurfaceLegendreMomentContext,
        side: str,
        tag: int,
        component: int,
    ) -> None:
        if side not in {"top", "bottom"} or component not in {0, 1}:
            raise ValueError("Legendre surface assembler supports top/bottom x/y only")
        self.context = context
        self.function_space = context.function_space
        self.mesh_data = context.mesh_data
        self.comm = context.mesh_data.mesh.comm
        self.side = str(side)
        self.tag = int(tag)
        self.component = int(component)
        self.surface_backend = context.backend
        self.call_count = 0
        self.facet_count = 0

    def _assemble_to_vector(self, mode: PortMode3D, mpc: Any, vector: PETSc.Vec) -> None:
        from .fullspace_surface_legendre import (
            SURFACE_POINTWISE_WEIGHTED_BACKEND,
            add_prevalidated_complex_mpc_cell_contribution,
            apply_standard_dof_transform,
            assemble_face_from_prevalidated_moments,
            assemble_face_from_weighted_moments,
        )

        if self.surface_backend == SURFACE_COMPONENT_PAIR_BACKEND:
            raise RuntimeError(
                "paired pointwise backend must enter through assemble_pair_entries"
            )
        if mpc is not self.context.mpc:
            raise ValueError("Legendre assembler was used with a different MPC")
        element = self.function_space.element
        cell_info = self.context._cell_permutations
        table = self.context.trace_table(self.side, self.component)
        with vector.localForm() as local_form:
            local_values = local_form.array_w
            for record in self.context.records(self.side):
                plan = record.cell_plan
                if self.surface_backend == SURFACE_POINTWISE_WEIGHTED_BACKEND:
                    moments = self.context.pointwise_moments(
                        mode, record, self.component
                    )
                    local_vector = assemble_face_from_weighted_moments(
                        table, moments
                    )
                else:
                    x_moment, y_moment = self.context.moments(mode, record)
                    h_component = record.hx if self.component == 0 else record.hy
                    phase_origin = np.exp(
                        1j
                        * (
                            complex(mode.alpha) * record.x0
                            + complex(mode.gamma) * record.y0
                            + complex(mode.k_vector[2]) * record.z_face
                        )
                    )
                    local_vector = assemble_face_from_prevalidated_moments(
                        table,
                        x_moment,
                        y_moment,
                        hx=record.hx,
                        hy=record.hy,
                        h_component=h_component,
                        phase_origin=phase_origin,
                    )
                if local_vector.shape != plan.cell_dofs.shape:
                    raise ValueError("surface trace vector and cell DOF count differ")
                local_vector = apply_standard_dof_transform(
                    element,
                    local_vector,
                    int(cell_info[record.cell]),
                    check_finite=False,
                )
                add_prevalidated_complex_mpc_cell_contribution(
                    local_vector,
                    local_values,
                    plan.cell_dofs,
                    plan.slave_positions,
                    plan.master_rows,
                    plan.coefficient_rows,
                )
        self.call_count += 1
        self.facet_count += len(self.context.records(self.side))

    def assemble_entries(
        self,
        mode: PortMode3D,
        mpc: Any,
        *,
        workspace: Any | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        if self.surface_backend == SURFACE_COMPONENT_PAIR_BACKEND:
            raise RuntimeError(
                "paired pointwise backend cannot silently use the unpaired assembler"
            )
        if mpc is not self.context.mpc:
            raise ValueError("Legendre assembler was used with a different MPC")
        if workspace is not None:
            vector = workspace.assemble_custom(
                self,
                mpc,
                lambda output: self._assemble_to_vector(mode, mpc, output),
            )
            return _vec_nonzero_owned_entries(
                vector,
                support=workspace.owned_support,
                timing_totals=workspace.timing_totals,
            )
        index_map = mpc.function_space.dofmap.index_map
        vector = create_vector(
            [(index_map, int(mpc.function_space.dofmap.index_map_bs))]
        )
        try:
            with vector.localForm() as local_form:
                local_form.set(0.0)
            self._assemble_to_vector(mode, mpc, vector)
            vector.ghostUpdate(
                addv=PETSc.InsertMode.ADD_VALUES,
                mode=PETSc.ScatterMode.REVERSE,
            )
            vector.ghostUpdate(
                addv=PETSc.InsertMode.INSERT_VALUES,
                mode=PETSc.ScatterMode.FORWARD,
            )
            return _vec_nonzero_owned_entries(vector)
        finally:
            vector.destroy()

    def _assemble_pair_to_vector(
        self,
        companion: _SurfaceLegendreMomentAssembler,
        mode: PortMode3D,
        mpc: Any,
        vector: PETSc.Vec,
        staging: _SurfaceComponentPairStaging,
    ) -> None:
        from .fullspace_surface_legendre import (
            add_prevalidated_complex_mpc_cell_contribution,
            apply_standard_dof_transform,
            assemble_face_from_weighted_moments,
        )

        if self.component != 0 or companion.component != 1:
            raise ValueError("paired surface assembly requires component order x then y")
        if (
            self.surface_backend != SURFACE_COMPONENT_PAIR_BACKEND
            or companion.surface_backend != SURFACE_COMPONENT_PAIR_BACKEND
            or self.context is not companion.context
            or mpc is not self.context.mpc
        ):
            raise ValueError("paired surface assembly identities differ")
        records = self.context.records(self.side)
        staging.assert_binding(
            primary=self,
            companion=companion,
            mode=mode,
            mpc=mpc,
            workspace=staging.workspace,
            records=records,
        )
        element = self.function_space.element
        cell_info = self.context._cell_permutations
        trace_table = self.context.trace_table(self.side, 0)
        prepared_trace = (
            self.context.prepared_trace_contraction(self.side)
            if self.context._prepare_trace_contraction
            else None
        )
        with vector.localForm() as local_form:
            local_values = local_form.array_w
            for position, record in enumerate(records):
                plan = record.cell_plan
                pair_moments = self.context.pointwise_moments_pair(
                    mode, record, record_position=position
                )
                if prepared_trace is None:
                    local_primary = assemble_face_from_weighted_moments(
                        trace_table, pair_moments[0]
                    )
                    local_companion = assemble_face_from_weighted_moments(
                        trace_table, pair_moments[1]
                    )
                else:
                    local_primary = prepared_trace.apply(pair_moments[0])
                    local_companion = prepared_trace.apply(pair_moments[1])
                if (
                    local_primary.shape != plan.cell_dofs.shape
                    or local_companion.shape != plan.cell_dofs.shape
                ):
                    raise ValueError("paired surface trace and cell DOF counts differ")
                cell_permutation = int(cell_info[record.cell])
                local_primary = apply_standard_dof_transform(
                    element, local_primary, cell_permutation, check_finite=False
                )
                local_companion = apply_standard_dof_transform(
                    element, local_companion, cell_permutation, check_finite=False
                )
                staging.store(position, record, local_companion)
                add_prevalidated_complex_mpc_cell_contribution(
                    local_primary,
                    local_values,
                    plan.cell_dofs,
                    plan.slave_positions,
                    plan.master_rows,
                    plan.coefficient_rows,
                )
        staging.assert_complete()

    def _replay_staged_component_to_vector(
        self,
        primary: _SurfaceLegendreMomentAssembler,
        mode: PortMode3D,
        mpc: Any,
        vector: PETSc.Vec,
        staging: _SurfaceComponentPairStaging,
        workspace: Any,
    ) -> None:
        from .fullspace_surface_legendre import (
            add_prevalidated_complex_mpc_cell_contribution,
        )

        if (
            self.component != 1
            or self.surface_backend != SURFACE_COMPONENT_PAIR_BACKEND
            or mpc is not self.context.mpc
        ):
            raise ValueError("staged replay requires the bound paired y-component")
        records = self.context.records(self.side)
        staging.assert_binding(
            primary=primary,
            companion=self,
            mode=mode,
            mpc=mpc,
            workspace=workspace,
            records=records,
        )
        with vector.localForm() as local_form:
            local_values = local_form.array_w
            for position, record in enumerate(records):
                plan = record.cell_plan
                local_vector = staging.get(position, record)
                add_prevalidated_complex_mpc_cell_contribution(
                    local_vector,
                    local_values,
                    plan.cell_dofs,
                    plan.slave_positions,
                    plan.master_rows,
                    plan.coefficient_rows,
                )

    def assemble_pair_entries(
        self,
        companion: _SurfaceLegendreMomentAssembler,
        mode: PortMode3D,
        mpc: Any,
        *,
        workspace: Any,
    ) -> tuple[tuple[np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray]]:
        if workspace is None:
            raise ValueError("paired surface backend requires the one-Vec workspace")
        records = self.context.records(self.side)
        staging = _SurfaceComponentPairStaging(
            records,
            primary=self,
            companion=companion,
            mode=mode,
            mpc=mpc,
            workspace=workspace,
        )
        stats = self.context._component_pair_stats
        try:
            stats["pair_call_count"] += 1
            stats["max_staging_bytes"] = max(
                int(stats["max_staging_bytes"]), staging.staging_bytes
            )
            stats["max_staging_facets"] = max(
                int(stats["max_staging_facets"]), len(records)
            )
            stats["staging_buffer_count_max"] = max(
                int(stats["staging_buffer_count_max"]), 1
            )
            from .fullspace_surface_legendre import (
                component_pair_explicit_array_payload_bounds,
            )

            payload_bounds = component_pair_explicit_array_payload_bounds(
                point_count=int(self.context.quadrilateral_weights.size),
                polynomial_width=int(self.context.degree + 1),
                local_dof_count=staging.local_dimension,
                facet_count=len(records),
                owned_support_rows=int(workspace.owned_support.size),
                row_index_bytes=int(np.dtype(PETSc.IntType).itemsize),
            )
            stats["max_explicit_numpy_payload_upper_bytes"] = max(
                int(stats.get("max_explicit_numpy_payload_upper_bytes", 0)),
                int(payload_bounds["explicit_numpy_payload_upper_bytes"]),
            )
            stats["last_payload_bounds"] = payload_bounds
            primary_vector = workspace.assemble_custom(
                self,
                mpc,
                lambda output: self._assemble_pair_to_vector(
                    companion, mode, mpc, output, staging
                ),
            )
            staging.assert_complete()
            primary_entries = _vec_nonzero_owned_entries(
                primary_vector,
                support=workspace.owned_support,
                timing_totals=workspace.timing_totals,
            )
            # _vec_nonzero_owned_entries returns an owned sparse value copy
            # before the shared Vec is cleared for component one.
            companion_vector = workspace.assemble_custom(
                companion,
                mpc,
                lambda output: companion._replay_staged_component_to_vector(
                    self, mode, mpc, output, staging, workspace
                ),
            )
            companion_entries = _vec_nonzero_owned_entries(
                companion_vector,
                support=workspace.owned_support,
                timing_totals=workspace.timing_totals,
            )
            self.call_count += 1
            companion.call_count += 1
            self.facet_count += len(records)
            companion.facet_count += len(records)
            stats["paired_facet_count"] += len(records)
            return primary_entries, companion_entries
        finally:
            staging.release()
            stats["staging_release_count"] += 1


class DtnTraceAliasError(RuntimeError):
    """Raised before matrix insertion when the declared n=0 trace aliases."""

    def __init__(self, audit: dict[str, Any]) -> None:
        self.audit = dict(audit)
        super().__init__(
            "DTN y-invariant n=0 trace alias preflight failed: "
            f"status={audit['status']}, "
            f"overlap={audit['maximum_normalized_overlap']:.6e}, "
            f"limit={audit['overlap_tolerance']:.6e}, "
            f"target={audit['worst_target_mode']}, "
            f"alias={audit['worst_non_target_mode']}. "
            "Refine the y-axis topology before solving."
        )


def _dtn_n0_trace_alias_preflight(
    modes: list[PortMode3D],
    surface_assemblers: Mapping[tuple[str, int], _ReusableSurfaceComponentAssembler],
    mpc,
    *,
    enabled: bool,
    overlap_tolerance: float,
) -> dict[str, Any]:
    """Audit actual MPC-reduced n=0/nonzero-n tangential trace functionals."""

    if not np.isfinite(overlap_tolerance) or overlap_tolerance < 0.0:
        raise ValueError(
            "DTN trace alias overlap tolerance must be finite and nonnegative."
        )
    if not enabled:
        return {
            "status": "not_requested",
            "enabled": False,
            "pass": True,
            "overlap_tolerance": float(overlap_tolerance),
        }
    if not modes:
        raise ValueError("DTN trace alias preflight requires at least one mode.")
    comm = next(iter(surface_assemblers.values())).comm
    traces: list[tuple[PortMode3D, np.ndarray, np.ndarray]] = []
    component_cache: dict[
        tuple[str, int, int, complex],
        tuple[
            tuple[np.ndarray, np.ndarray],
            tuple[np.ndarray, np.ndarray],
        ],
    ] = {}
    for mode in modes:
        key = (
            mode.side,
            int(mode.m),
            int(mode.n),
            complex(mode.k_vector[2]),
        )
        entries = component_cache.get(key)
        if entries is None:
            entries = (
                surface_assemblers[(mode.side, 0)].assemble_entries(mode, mpc),
                surface_assemblers[(mode.side, 1)].assemble_entries(mode, mpc),
            )
            component_cache[key] = entries
        rows, values = _combine_owned_entries(
            entries,
            (mode.e_vector[0], mode.e_vector[1]),
            comm=comm,
        )
        traces.append((mode, rows, values))

    target_indices = [
        index for index, (mode, _rows, _values) in enumerate(traces) if int(mode.n) == 0
    ]
    alias_indices = [
        index for index, (mode, _rows, _values) in enumerate(traces) if int(mode.n) != 0
    ]
    maximum = 0.0
    worst_target = None
    worst_alias = None
    comparisons = 0
    zero_norm_modes: list[dict[str, Any]] = []
    nonfinite_entries: list[dict[str, Any]] = []
    for target_index in target_indices:
        target_mode, target_rows, target_values = traces[target_index]
        target_norm_sq = float(
            comm.allreduce(
                float(np.vdot(target_values, target_values).real),
                op=MPI.SUM,
            )
        )
        if not np.isfinite(target_norm_sq):
            nonfinite_entries.append(
                {
                    "role": "target_n0_norm",
                    "side": target_mode.side,
                    "m": int(target_mode.m),
                    "n": int(target_mode.n),
                    "polarization": target_mode.polarization,
                }
            )
            continue
        if target_norm_sq <= 1.0e-30:
            zero_norm_modes.append(
                {
                    "role": "target_n0",
                    "side": target_mode.side,
                    "m": int(target_mode.m),
                    "n": int(target_mode.n),
                    "polarization": target_mode.polarization,
                }
            )
            continue
        for alias_index in alias_indices:
            alias_mode, alias_rows, alias_values = traces[alias_index]
            if alias_mode.side != target_mode.side:
                continue
            alias_norm_sq = float(
                comm.allreduce(
                    float(np.vdot(alias_values, alias_values).real),
                    op=MPI.SUM,
                )
            )
            if not np.isfinite(alias_norm_sq):
                nonfinite_entries.append(
                    {
                        "role": "non_target_n_norm",
                        "side": alias_mode.side,
                        "m": int(alias_mode.m),
                        "n": int(alias_mode.n),
                        "polarization": alias_mode.polarization,
                    }
                )
                continue
            if alias_norm_sq <= 1.0e-30:
                identity = {
                    "role": "non_target_n",
                    "side": alias_mode.side,
                    "m": int(alias_mode.m),
                    "n": int(alias_mode.n),
                    "polarization": alias_mode.polarization,
                }
                if identity not in zero_norm_modes:
                    zero_norm_modes.append(identity)
                continue
            shared, target_positions, alias_positions = np.intersect1d(
                target_rows,
                alias_rows,
                assume_unique=True,
                return_indices=True,
            )
            local_cross = (
                complex(
                    np.vdot(
                        target_values[target_positions],
                        alias_values[alias_positions],
                    )
                )
                if len(shared)
                else 0.0 + 0.0j
            )
            cross = complex(comm.allreduce(local_cross, op=MPI.SUM))
            if not np.isfinite(cross.real) or not np.isfinite(cross.imag):
                nonfinite_entries.append(
                    {
                        "role": "cross_overlap",
                        "target": {
                            "side": target_mode.side,
                            "m": int(target_mode.m),
                            "n": int(target_mode.n),
                            "polarization": target_mode.polarization,
                        },
                        "non_target": {
                            "side": alias_mode.side,
                            "m": int(alias_mode.m),
                            "n": int(alias_mode.n),
                            "polarization": alias_mode.polarization,
                        },
                    }
                )
                continue
            overlap = float(
                abs(cross) / max(np.sqrt(target_norm_sq * alias_norm_sq), 1.0e-30)
            )
            if not np.isfinite(overlap):
                nonfinite_entries.append(
                    {
                        "role": "normalized_overlap",
                        "target": {
                            "side": target_mode.side,
                            "m": int(target_mode.m),
                            "n": int(target_mode.n),
                            "polarization": target_mode.polarization,
                        },
                        "non_target": {
                            "side": alias_mode.side,
                            "m": int(alias_mode.m),
                            "n": int(alias_mode.n),
                            "polarization": alias_mode.polarization,
                        },
                    }
                )
                continue
            comparisons += 1
            if overlap > maximum:
                maximum = overlap
                worst_target = {
                    "side": target_mode.side,
                    "m": int(target_mode.m),
                    "n": int(target_mode.n),
                    "polarization": target_mode.polarization,
                }
                worst_alias = {
                    "side": alias_mode.side,
                    "m": int(alias_mode.m),
                    "n": int(alias_mode.n),
                    "polarization": alias_mode.polarization,
                }
    exercised = bool(target_indices and alias_indices and comparisons)
    if not target_indices:
        status = "not_exercised_missing_n0_target"
        passed = False
    elif not alias_indices:
        status = "not_exercised_missing_nonzero_n_control"
        passed = False
    elif nonfinite_entries:
        status = "invalid_nonfinite_trace_functional"
        passed = False
    elif zero_norm_modes:
        status = "invalid_zero_norm_trace_functional"
        passed = False
    elif not exercised:
        status = "not_exercised_no_same_side_comparisons"
        passed = False
    elif maximum > overlap_tolerance:
        status = "dtn_y_trace_alias_detected"
        passed = False
    else:
        status = "pass"
        passed = True
    audit = {
        "status": status,
        "enabled": True,
        "pass": passed,
        "method": (
            "normalized_actual_mpc_reduced_tangential_surface_functional_overlap"
        ),
        "target_n": 0,
        "target_mode_count": len(target_indices),
        "non_target_mode_count": len(alias_indices),
        "comparison_count": comparisons,
        "overlap_tolerance": float(overlap_tolerance),
        "maximum_normalized_overlap": maximum,
        "worst_target_mode": worst_target,
        "worst_non_target_mode": worst_alias,
        "zero_norm_modes": zero_norm_modes,
        "nonfinite_entries": nonfinite_entries,
    }
    if not passed:
        raise DtnTraceAliasError(audit)
    return audit


def _copy_base_matrix_to_augmented(
    A_base: PETSc.Mat,
    n_aux: int,
    comm: MPI.Intracomm,
    *,
    on_allocated: Callable[[], None] | None = None,
) -> PETSc.Mat:
    n_fe = A_base.getSize()[0]
    local_fe_rows = A_base.getOwnershipRange()[1] - A_base.getOwnershipRange()[0]
    local_aug_rows = local_fe_rows + (n_aux if comm.rank == comm.size - 1 else 0)
    A_aug = PETSc.Mat().createAIJ(
        size=((local_aug_rows, n_fe + n_aux), (local_aug_rows, n_fe + n_aux)),
        comm=comm,
    )
    A_aug.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR, False)
    if on_allocated is not None:
        on_allocated()
    row_start, row_end = A_base.getOwnershipRange()
    for row in range(row_start, row_end):
        cols, values = A_base.getRow(row)
        if len(cols):
            A_aug.setValues(_idx([row]), _idx(cols), values)
    return A_aug


def _local_augmented_dtn_coupling_stats(
    *,
    n_fe: int,
    n_aux: int,
    traction_rows_total: int,
    ell_cols_total: int,
) -> dict[str, Any]:
    """Summarize the sparse auxiliary DtN block shape.

    The auxiliary formulation should add one sparse column and one sparse row
    per mode, not a dense all-to-all FEM trace block.
    """

    coupling_nnz = int(traction_rows_total + ell_cols_total + n_aux)
    return {
        "dtn_auxiliary_block_is_dense": False,
        "dtn_auxiliary_dof_count": int(n_aux),
        "dtn_auxiliary_fem_dof_count": int(n_fe),
        "dtn_auxiliary_coupling_nnz_estimate": coupling_nnz,
        "dtn_auxiliary_average_coupling_nnz_per_mode": float(
            coupling_nnz / max(n_aux, 1)
        ),
        "dtn_auxiliary_dense_block_equivalent_nnz": int(
            n_aux * max(n_fe, 1) * 2 + n_aux
        ),
    }


def _augmented_vec_from_base(
    b_base: PETSc.Vec, n_aux: int, comm: MPI.Intracomm
) -> PETSc.Vec:
    n_fe = b_base.getSize()
    local_fe_rows = b_base.getOwnershipRange()[1] - b_base.getOwnershipRange()[0]
    local_aug_rows = local_fe_rows + (n_aux if comm.rank == comm.size - 1 else 0)
    b_aug = PETSc.Vec().createMPI((local_aug_rows, n_fe + n_aux), comm=comm)
    row_start, row_end = b_base.getOwnershipRange()
    values = np.asarray(b_base.getArray(readonly=True), dtype=np.complex128)
    if values.size:
        b_aug.setValues(
            _idx(np.arange(row_start, row_end, dtype=np.int64)),
            values,
            addv=PETSc.InsertMode.ADD_VALUES,
        )
    return b_aug


def _outward_normal(side: str) -> np.ndarray:
    if side == "top":
        return np.asarray((0.0, 0.0, 1.0), dtype=np.float64)
    if side == "bottom":
        return np.asarray((0.0, 0.0, -1.0), dtype=np.float64)
    raise ValueError("side must be 'top' or 'bottom'.")


def _mode_boundary_z(mode: PortMode3D, cfg: SimulationConfig3D) -> float:
    return float(cfg.physical_z_max if mode.side == "top" else cfg.physical_z_min)


def _mode_boundary_phase(mode: PortMode3D, cfg: SimulationConfig3D) -> complex:
    return complex(np.exp(1j * complex(mode.k_vector[2]) * _mode_boundary_z(mode, cfg)))


def _mode_projection_denominator(mode: PortMode3D, cfg: SimulationConfig3D) -> float:
    area = (cfg.x_max - cfg.x_min) * (cfg.y_max - cfg.y_min)
    phase = _mode_boundary_phase(mode, cfg)
    return float(area * mode.electric_tangential_norm_sq * abs(phase) ** 2)


def _mode_power_at_boundary(
    mode: PortMode3D, cfg: SimulationConfig3D, amplitude: complex
) -> float:
    e_at_boundary = complex(amplitude) * _mode_boundary_phase(mode, cfg) * mode.e_vector
    return mode_power(mode.k_vector, e_at_boundary, cfg, _outward_normal(mode.side))


def _mode_carries_outward_power(mode: PortMode3D) -> bool:
    """Return whether the selected mode carries positive real power at its finite port."""

    return bool(mode.power_per_unit_amplitude > 0.0)


def _traction_vector(mode: PortMode3D, cfg: SimulationConfig3D) -> np.ndarray:
    del cfg
    curl_vector = 1j * np.cross(mode.k_vector, mode.e_vector)
    return np.cross(curl_vector, _outward_normal(mode.side))


def _incident_projection_onto_top_mode(
    mode: PortMode3D, cfg: SimulationConfig3D
) -> complex:
    if mode.side != "top" or mode.m != 0 or mode.n != 0:
        return 0.0 + 0.0j
    denominator = _mode_projection_denominator(mode, cfg)
    incident_e = complex(cfg.incident_amplitude) * np.asarray(
        cfg.polarization_vector, dtype=np.complex128
    )
    tangential_overlap = np.vdot(mode.e_vector[:2], incident_e[:2])
    phase = np.exp(1j * (cfg.kz - mode.k_vector[2]) * cfg.physical_z_max)
    area = (cfg.x_max - cfg.x_min) * (cfg.y_max - cfg.y_min)
    return complex(area * tangential_overlap * phase / denominator)


def _incident_top_traction_form(V, mesh_data, cfg: SimulationConfig3D):
    x = ufl.SpatialCoordinate(mesh_data.mesh)
    k_inc = np.asarray(cfg.wavevector, dtype=np.complex128)
    e_inc = complex(cfg.incident_amplitude) * np.asarray(
        cfg.polarization_vector, dtype=np.complex128
    )
    traction = np.cross(
        1j * np.cross(k_inc, e_inc), np.asarray((0.0, 0.0, 1.0), dtype=np.float64)
    )
    phase = ufl.exp(
        PETSc.ScalarType(1j * k_inc[0]) * x[0]
        + PETSc.ScalarType(1j * k_inc[1]) * x[1]
        + PETSc.ScalarType(1j * k_inc[2]) * x[2]
    )
    return _surface_vector_form(V, mesh_data, cfg.tags.z_max, traction, phase)


def _dtn_surface_quadrature_degree(
    cfg: SimulationConfig3D, modes: list[PortMode3D]
) -> int:
    """Choose a quadrature degree for oscillatory DtN surface projections.

    The port forms contain Fourier factors exp(i alpha x + i gamma y), not just
    polynomials.  Default UFL quadrature is too low for p=2 EUV cases where the
    automatically selected propagating orders can change phase rapidly within a
    single surface cell.  A deterministic moderately high rule keeps the
    auxiliary DtN block from losing rank in MPI while avoiding a user-facing
    option explosion at this stage.
    """

    configured = getattr(cfg, "stage4_dtn_quadrature_degree", None)
    if configured is not None:
        return max(1, int(configured))
    max_order = max((max(abs(mode.m), abs(mode.n)) for mode in modes), default=0)
    return int(max(10, 2 * int(cfg.nedelec_degree) + max_order + 6))


def _use_zero_order_local_robin_dtn(cfg: SimulationConfig3D) -> bool:
    """Use the 2D-like local DtN sanity branch for normal-incidence order 0."""

    transverse_scale = max(abs(cfg.k0 * complex(cfg.n_air)), 1.0)
    normal_incidence = (
        abs(complex(cfg.kx)) <= 1.0e-12 * transverse_scale
        and abs(complex(cfg.ky)) <= 1.0e-12 * transverse_scale
    )
    return cfg.stage4_dtn_order_policy.lower() == "zero_order" and normal_incidence


def _mode_projection_from_solution(
    E_total,
    mode: PortMode3D,
    mesh_data,
    cfg: SimulationConfig3D,
    *,
    quadrature_degree: int | None,
) -> complex:
    """Project the solved tangential E trace onto one tangential port mode."""

    tag = cfg.tags.z_max if mode.side == "top" else cfg.tags.z_min
    x = ufl.SpatialCoordinate(mesh_data.mesh)
    phase = ufl.exp(
        PETSc.ScalarType(1j * mode.alpha) * x[0]
        + PETSc.ScalarType(1j * mode.gamma) * x[1]
        + PETSc.ScalarType(1j * mode.k_vector[2]) * x[2]
    )
    tangential_field = ufl.as_vector((E_total[0], E_total[1], PETSc.ScalarType(0.0)))
    tangential_mode = np.asarray(
        (mode.e_vector[0], mode.e_vector[1], 0.0),
        dtype=np.complex128,
    )
    reference = _as_ufl_vector(tangential_mode, phase)
    ds = ufl.Measure("ds", domain=mesh_data.mesh, subdomain_data=mesh_data.facet_tags)
    local = fem.assemble_scalar(
        fem.form(
            _with_quadrature_degree(
                ufl.inner(tangential_field, reference) * ds(tag),
                quadrature_degree,
            ),
        )
    )
    total = mesh_data.mesh.comm.allreduce(local, op=MPI.SUM)
    denominator = _mode_projection_denominator(mode, cfg)
    return complex(total / denominator)


def _sampled_tangential_projection(
    electric_samples: np.ndarray,
    mode_samples: np.ndarray,
    weights: np.ndarray | None = None,
) -> complex:
    """Return the sampled form of the tangential DtN projection contract."""

    electric = np.asarray(electric_samples, dtype=np.complex128)
    mode = np.asarray(mode_samples, dtype=np.complex128)
    if electric.shape != mode.shape or electric.ndim != 2 or electric.shape[1] != 3:
        raise ValueError(
            "sampled tangential projection requires matching (N, 3) arrays"
        )
    measure = (
        np.ones(electric.shape[0], dtype=np.float64)
        if weights is None
        else np.asarray(weights, dtype=np.float64)
    )
    if measure.shape != (electric.shape[0],) or np.any(measure < 0.0):
        raise ValueError("sampled tangential projection weights are invalid")
    numerator = np.sum(measure * np.sum(electric[:, :2] * np.conj(mode[:, :2]), axis=1))
    denominator = float(np.sum(measure * np.sum(np.abs(mode[:, :2]) ** 2, axis=1)))
    if denominator <= 0.0:
        raise ValueError("sampled tangential mode has zero tangential norm")
    return complex(numerator / denominator)


def _outgoing_projection(
    total_projection: complex,
    incident_projection: complex,
    side: str,
) -> complex:
    """Convert a total port coefficient to the outgoing convention."""

    if side == "top":
        return complex(total_projection - incident_projection)
    if side == "bottom":
        return complex(total_projection)
    raise ValueError("side must be top or bottom")


def _auxiliary_direct_tangential_projection_audit(
    E_total,
    modes: list[PortMode3D],
    auxiliary_values: np.ndarray,
    incident_projections: list[complex],
    mesh_data,
    cfg: SimulationConfig3D,
    *,
    quadrature_degree: int | None,
) -> dict[str, Any]:
    """Compare official auxiliary amplitudes with an independent FE projection."""

    mode_count = len(modes)
    if mode_count == 0:
        raise ValueError(
            "DTN auxiliary/direct projection audit requires at least one mode."
        )
    if len(auxiliary_values) != mode_count or len(incident_projections) != mode_count:
        raise ValueError(
            "DTN auxiliary/direct projection audit input lengths must match: "
            f"modes={mode_count}, auxiliary={len(auxiliary_values)}, "
            f"incident={len(incident_projections)}."
        )
    direct_values = [
        _mode_projection_from_solution(
            E_total,
            mode,
            mesh_data,
            cfg,
            quadrature_degree=quadrature_degree,
        )
        for mode in modes
    ]
    rows: list[dict[str, Any]] = []
    for mode, auxiliary, direct, incident in zip(
        modes,
        auxiliary_values,
        direct_values,
        incident_projections,
    ):
        complex_values = tuple(
            complex(value) for value in (auxiliary, direct, incident)
        )
        if not all(
            np.isfinite(value.real) and np.isfinite(value.imag)
            for value in complex_values
        ):
            raise ValueError(
                "DTN auxiliary/direct projection audit encountered a non-finite "
                f"projection for {mode.side} ({mode.m}, {mode.n}) "
                f"{mode.polarization}."
            )
        auxiliary_outgoing = _outgoing_projection(
            complex(auxiliary), complex(incident), mode.side
        )
        direct_outgoing = _outgoing_projection(
            complex(direct), complex(incident), mode.side
        )
        rows.append(
            {
                "side": mode.side,
                "m": int(mode.m),
                "n": int(mode.n),
                "polarization": mode.polarization,
                "auxiliary_total_projection": complex(auxiliary),
                "direct_tangential_total_projection": complex(direct),
                "incident_projection": complex(incident),
                "auxiliary_outgoing_projection": auxiliary_outgoing,
                "direct_tangential_outgoing_projection": direct_outgoing,
                "absolute_total_projection_difference": float(
                    abs(complex(auxiliary) - complex(direct))
                ),
                "absolute_outgoing_projection_difference": float(
                    abs(auxiliary_outgoing - direct_outgoing)
                ),
            }
        )
        if not all(
            np.isfinite(float(rows[-1][key]))
            for key in (
                "absolute_total_projection_difference",
                "absolute_outgoing_projection_difference",
            )
        ):
            raise ValueError(
                "DTN auxiliary/direct projection audit produced a non-finite "
                f"difference for {mode.side} ({mode.m}, {mode.n}) "
                f"{mode.polarization}."
            )
    max_difference = max(
        (float(row["absolute_outgoing_projection_difference"]) for row in rows),
        default=0.0,
    )
    tolerance = float(cfg.dtn_auxiliary_direct_projection_tolerance)
    return {
        "requested": True,
        "method": (
            "independent recovered-FE tangential trace projection; official "
            "auxiliary amplitudes are unchanged"
        ),
        "quadrature_degree": quadrature_degree,
        "absolute_error_only_for_near_zero_channels": True,
        "tolerance": tolerance,
        "max_absolute_outgoing_projection_difference": max_difference,
        "pass": bool(max_difference <= tolerance),
        "orders": rows,
    }


def _surface_scalar(
    expression,
    mesh_data,
    tag: int,
    *,
    quadrature_degree: int | None,
) -> complex:
    ds = ufl.Measure("ds", domain=mesh_data.mesh, subdomain_data=mesh_data.facet_tags)
    local = fem.assemble_scalar(
        fem.form(
            _with_quadrature_degree(expression * ds(tag), quadrature_degree)
        )
    )
    return complex(mesh_data.mesh.comm.allreduce(local, op=MPI.SUM))


def _surface_diagnostics(
    E_total,
    mesh_data,
    cfg: SimulationConfig3D,
    *,
    quadrature_degree: int | None,
) -> dict[str, Any]:
    """Return direct z-port measure diagnostics for the zero-order sanity branch."""

    fdim = mesh_data.mesh.topology.dim - 1
    facet_index_map = mesh_data.mesh.topology.index_map(fdim)
    owned_facet_limit = facet_index_map.size_local
    diagnostics: dict[str, Any] = {}
    one = fem.Constant(mesh_data.mesh, PETSc.ScalarType(1.0))
    e_t = ufl.as_vector((E_total[0], E_total[1], PETSc.ScalarType(0.0)))
    for side, tag in (("top", cfg.tags.z_max), ("bottom", cfg.tags.z_min)):
        tagged_facets = np.asarray(mesh_data.facet_tags.find(tag), dtype=np.int32)
        owned_count_local = int(np.count_nonzero(tagged_facets < owned_facet_limit))
        owned_count = int(mesh_data.mesh.comm.allreduce(owned_count_local, op=MPI.SUM))
        area = _surface_scalar(one, mesh_data, tag, quadrature_degree=quadrature_degree)
        energy = _surface_scalar(
            ufl.inner(e_t, e_t), mesh_data, tag, quadrature_degree=quadrature_degree
        )
        diagnostics[f"stage4_dtn_{side}_facet_count_owned_global"] = owned_count
        diagnostics[f"stage4_dtn_{side}_surface_area_nm2"] = float(np.real(area))
        diagnostics[f"stage4_dtn_{side}_Et_l2_integral"] = float(np.real(energy))
        diagnostics[f"stage4_dtn_{side}_Et_l2_mean"] = float(
            np.real(energy) / max(float(np.real(area)), 1.0e-30)
        )
    return diagnostics


def _owned_cells_adjacent_to_facet_tag(mesh_data, tag: int) -> np.ndarray:
    """Return locally owned cells touching a tagged exterior facet."""

    msh = mesh_data.mesh
    tdim = msh.topology.dim
    fdim = tdim - 1
    msh.topology.create_connectivity(fdim, tdim)
    facet_to_cell = msh.topology.connectivity(fdim, tdim)
    if facet_to_cell is None:
        raise RuntimeError("facet-to-cell connectivity is unavailable")
    owned_cells = int(msh.topology.index_map(tdim).size_local)
    tagged_facets = np.asarray(
        mesh_data.facet_tags.find(int(tag)),
        dtype=np.int32,
    )
    cells = [
        int(cell)
        for facet in tagged_facets
        for cell in facet_to_cell.links(int(facet))
        if 0 <= int(cell) < owned_cells
    ]
    return np.asarray(sorted(set(cells)), dtype=np.int32)


def _zero_order_local_robin_forms(a, L, V, mesh_data, cfg: SimulationConfig3D):
    """Build the normal-incidence order-0 DtN form used as a hard sanity path.

    The H(curl) integration-by-parts identity contributes
    ``+ int_boundary (n x curl(E)) . v``.  For a top incident downward wave and
    outgoing top/bottom zero-order modes, this gives the same sign convention
    as the validated 2D port sanity path: ``q=-i beta`` and top source
    ``-2 i beta E_inc,t``.
    """

    u = ufl.TrialFunction(V)
    v = ufl.TestFunction(V)
    x = ufl.SpatialCoordinate(mesh_data.mesh)
    ds = ufl.Measure("ds", domain=mesh_data.mesh, subdomain_data=mesh_data.facet_tags)

    beta_top = cfg.k0 * complex(cfg.n_air)
    beta_bottom = cfg.k0 * complex(cfg.substrate_index)
    q_top = PETSc.ScalarType(-1j * beta_top)
    q_bottom = PETSc.ScalarType(-1j * beta_bottom)
    v_t = ufl.as_vector((v[0], v[1], PETSc.ScalarType(0.0)))
    q_top_u_t = ufl.as_vector((q_top * u[0], q_top * u[1], PETSc.ScalarType(0.0)))
    q_bottom_u_t = ufl.as_vector(
        (q_bottom * u[0], q_bottom * u[1], PETSc.ScalarType(0.0))
    )
    a_local = (
        a
        + ufl.inner(q_top_u_t, v_t) * ds(cfg.tags.z_max)
        + ufl.inner(q_bottom_u_t, v_t) * ds(cfg.tags.z_min)
    )

    k_inc = np.asarray(cfg.wavevector, dtype=np.complex128)
    incident_e = complex(cfg.incident_amplitude) * np.asarray(
        cfg.polarization_vector, dtype=np.complex128
    )
    source_vec = np.asarray(
        (
            -2j * beta_top * incident_e[0],
            -2j * beta_top * incident_e[1],
            0.0 + 0.0j,
        ),
        dtype=np.complex128,
    )
    phase = ufl.exp(
        PETSc.ScalarType(1j * k_inc[0]) * x[0]
        + PETSc.ScalarType(1j * k_inc[1]) * x[1]
        + PETSc.ScalarType(1j * k_inc[2]) * x[2]
    )
    L_local = L + ufl.inner(_as_ufl_vector(source_vec, phase), v) * ds(cfg.tags.z_max)
    return a_local, L_local


def _solve_zero_order_local_robin_dtn(
    *,
    a,
    L,
    V,
    mesh_data,
    cfg: SimulationConfig3D,
    floquet_data: DoubleFloquet3DData,
    petsc_options: dict[str, Any],
    out_dir: Path,
    log,
    started: float | None = None,
) -> dict[str, Any]:
    """Solve the normal-incidence zero-order DtN port as a local Robin problem."""

    comm = mesh_data.mesh.comm
    stage_start = time.perf_counter()
    timing_details: dict[str, float | int | bool | str] = {
        "stage4_dtn_zero_order_local_robin": True,
    }
    modes = outgoing_port_modes_3d(cfg)
    if len(modes) != 4:
        raise RuntimeError(
            f"zero_order local DtN expects exactly four modes: top/bottom x/y. Got {len(modes)} modes."
        )
    dtn_quadrature_degree = _dtn_surface_quadrature_degree(cfg, modes)
    timing_details["stage4_dtn_surface_quadrature_degree"] = int(dtn_quadrature_degree)
    if log is not None:
        log("Stage-4 DtN using zero-order local Robin sanity branch")
        log(f"Stage-4 DtN surface quadrature degree = {dtn_quadrature_degree}")

    t0 = time.perf_counter()
    a_local, L_local = _zero_order_local_robin_forms(a, L, V, mesh_data, cfg)
    E_total = fem.Function(floquet_data.mpc.function_space, name="E_total")
    if cfg.matrix_diagnostics_assemble_only:
        A_diag = dolfinx_mpc.assemble_matrix(
            fem.form(a_local), floquet_data.mpc, bcs=[]
        )
        A_diag.assemble()
        b_diag = _assemble_mpc_vector(L_local, floquet_data.mpc)
        x_diag = b_diag.duplicate()
        x_diag.set(PETSc.ScalarType(0.0))
        ksp = PETSc.KSP().create(comm)
        ksp.setOptionsPrefix(f"stage4_3d_zero_order_dtn_{cfg.case_name}_")
        ksp.setOperators(A_diag)
        opts = PETSc.Options()
        opts.prefixPush(f"stage4_3d_zero_order_dtn_{cfg.case_name}_")
        for key, value in petsc_options.items():
            opts[key] = value
        ksp.setFromOptions()
        for key in petsc_options.keys():
            del opts[key]
        opts.prefixPop()
        matrix_stats_after_setup = _petsc_matrix_stats(A_diag)
        _write_progress_event(
            out_dir,
            comm,
            stage="stage4_dtn_zero_order_matrix_assembled",
            status="end",
            started=started,
            dofs=int(V.dofmap.index_map.size_global * V.dofmap.index_map_bs),
            constraints=floquet_data.num_constraints,
            matrix_stats=matrix_stats_after_setup,
            petsc_options=petsc_options,
        )
        timing_details["stage4_dtn_zero_order_linear_problem_setup_seconds"] = float(
            comm.allreduce(time.perf_counter() - t0, op=MPI.MAX)
        )
        solver_info = {
            "solver_backend": "dolfinx_mpc assembled zero-order local 3D DtN/Robin ports",
            "assemble_only": True,
            "num_auxiliary_dofs": 0,
            "num_fem_dofs_after_mpc": int(A_diag.getSize()[0]),
            "num_total_augmented_dofs": int(A_diag.getSize()[0]),
            "explicit_chac_constructed": False,
            "dtn_auxiliary_dense_block_constructed": False,
            "dtn_base_matrix_stats": None,
            "dtn_augmented_matrix_stats_after_finalize": None,
            "dtn_auxiliary_block_stats": {
                "dtn_auxiliary_block_is_dense": False,
                "dtn_auxiliary_dof_count": 0,
                "dtn_auxiliary_coupling_nnz_estimate": 0,
            },
            "stage4_dtn_assembly_seconds": float(
                comm.allreduce(time.perf_counter() - stage_start, op=MPI.MAX)
            ),
            "ksp_converged_reason": 0,
            "ksp_iterations": 0,
            "actual_ksp_type": ksp.getType(),
            "actual_pc_type": ksp.getPC().getType(),
            "actual_pc_factor_solver_type": None,
            **timing_details,
        }
        try:
            solver_info["actual_pc_factor_solver_type"] = (
                ksp.getPC().getFactorSolverType()
            )
        except Exception:
            solver_info["actual_pc_factor_solver_type"] = None
        return {
            "E_total": E_total,
            "solver_info": solver_info,
            "port_metrics": {
                "R_total": None,
                "T_total": None,
                "R_plus_T": None,
                "A_balance": None,
                "diffraction_total_power_source": "assemble_only_skipped",
                **_port_mode_count_metrics(modes),
            },
            "A": A_diag,
            "b": b_diag,
            "x": x_diag,
            "ksp": ksp,
            "problem": None,
        }

    problem = dolfinx_mpc.LinearProblem(
        a_local,
        L_local,
        floquet_data.mpc,
        bcs=[],
        u=E_total,
        petsc_options_prefix=f"stage4_3d_zero_order_dtn_{cfg.case_name}_",
        petsc_options=petsc_options,
    )
    timing_details["stage4_dtn_zero_order_linear_problem_setup_seconds"] = float(
        comm.allreduce(time.perf_counter() - t0, op=MPI.MAX)
    )

    t0 = time.perf_counter()
    _write_progress_event(
        out_dir,
        comm,
        stage="stage4_dtn_zero_order_solve",
        status="begin",
        started=started,
        dofs=int(V.dofmap.index_map.size_global * V.dofmap.index_map_bs),
        constraints=floquet_data.num_constraints,
        petsc_options=petsc_options,
    )
    try:
        E_total = problem.solve()
    except PETSc.Error as exc:
        raise DirectSolveFailure(
            "PETSc direct LU failed during Stage-4 zero-order DtN KSPSolve.",
            failure_stage="stage4_dtn_zero_order_solve",
            petsc_error=exc,
            A=problem.A,
            b=problem.b,
            x=problem.x,
            ksp=problem.solver,
            solver_backend="dolfinx_mpc.LinearProblem with zero-order local 3D DtN/Robin ports",
            timing_details=timing_details,
            extra_summary={
                "solver_info": {
                    "num_auxiliary_dofs": 0,
                    "dtn_base_matrix_stats": None,
                    "dtn_augmented_matrix_stats_after_finalize": None,
                    "dtn_auxiliary_block_stats": {
                        "dtn_auxiliary_block_is_dense": False,
                        "dtn_auxiliary_dof_count": 0,
                        "dtn_auxiliary_coupling_nnz_estimate": 0,
                    },
                }
            },
        ) from exc
    E_total.x.scatter_forward()
    timing_details["stage4_dtn_zero_order_linear_solve_seconds"] = float(
        comm.allreduce(time.perf_counter() - t0, op=MPI.MAX)
    )
    _write_progress_event(
        out_dir,
        comm,
        stage="stage4_dtn_zero_order_solve",
        status="end",
        started=started,
        dofs=int(V.dofmap.index_map.size_global * V.dofmap.index_map_bs),
        constraints=floquet_data.num_constraints,
        matrix_stats=_petsc_matrix_stats(problem.A),
        petsc_options=petsc_options,
    )

    t0 = time.perf_counter()
    modal_values = np.asarray(
        [
            _mode_projection_from_solution(
                E_total,
                mode,
                mesh_data,
                cfg,
                quadrature_degree=dtn_quadrature_degree,
            )
            for mode in modes
        ],
        dtype=np.complex128,
    )
    incident_projections = [
        _incident_projection_onto_top_mode(mode, cfg) for mode in modes
    ]
    timing_details["stage4_dtn_zero_order_projection_seconds"] = float(
        comm.allreduce(time.perf_counter() - t0, op=MPI.MAX)
    )
    port_metrics = _port_power_metrics(cfg, modes, modal_values, incident_projections)
    port_metrics.update(
        _surface_diagnostics(
            E_total,
            mesh_data,
            cfg,
            quadrature_degree=dtn_quadrature_degree,
        )
    )
    port_metrics["stage4_dtn_zero_order_modal_values"] = [
        complex(value) for value in modal_values
    ]
    port_metrics["stage4_dtn_zero_order_incident_projections"] = [
        complex(value) for value in incident_projections
    ]
    port_metrics.update(timing_details)
    port_metrics["dtn_port_power_metric_note"] = (
        "Stage-4 zero_order dtn_port R/T is computed from direct boundary projections "
        "after solving the local Robin/DtN total-field problem."
    )
    _write_port_outputs(
        out_dir, cfg, modes, modal_values, incident_projections, port_metrics, comm
    )

    solver_info = {
        "solver_backend": "dolfinx_mpc.LinearProblem with zero-order local 3D DtN/Robin ports",
        "num_auxiliary_dofs": 0,
        "num_fem_dofs_after_mpc": int(problem.A.getSize()[0]),
        "num_total_augmented_dofs": int(problem.A.getSize()[0]),
        "explicit_chac_constructed": False,
        "dtn_auxiliary_dense_block_constructed": False,
        "dtn_base_matrix_stats": None,
        "dtn_augmented_matrix_stats_after_finalize": None,
        "dtn_auxiliary_block_stats": {
            "dtn_auxiliary_block_is_dense": False,
            "dtn_auxiliary_dof_count": 0,
            "dtn_auxiliary_coupling_nnz_estimate": 0,
        },
        "stage4_dtn_assembly_seconds": float(
            comm.allreduce(time.perf_counter() - stage_start, op=MPI.MAX)
        ),
        "ksp_converged_reason": int(problem.solver.getConvergedReason()),
        "ksp_iterations": int(problem.solver.getIterationNumber()),
        "actual_ksp_type": problem.solver.getType(),
        "actual_pc_type": problem.solver.getPC().getType(),
        "actual_pc_factor_solver_type": None,
        **timing_details,
        **_linear_residual(problem.A, problem.b, problem.x),
    }
    try:
        solver_info["actual_pc_factor_solver_type"] = (
            problem.solver.getPC().getFactorSolverType()
        )
    except Exception:
        solver_info["actual_pc_factor_solver_type"] = None
    return {
        "E_total": E_total,
        "solver_info": solver_info,
        "port_metrics": port_metrics,
        "A": problem.A,
        "b": problem.b,
        "x": problem.x,
        "ksp": problem.solver,
        "problem": problem,
    }


def _solve_augmented_system(
    A_aug: PETSc.Mat,
    b_aug: PETSc.Vec,
    petsc_options: dict[str, Any],
    prefix: str,
    *,
    out_dir: Path | None = None,
    comm: MPI.Intracomm | None = None,
    started: float | None = None,
    dofs: int | None = None,
    constraints: int | None = None,
    matrix_stats: dict[str, Any] | None = None,
    factorization_only: bool = False,
) -> tuple[PETSc.Vec, PETSc.KSP, dict[str, Any]]:
    progress_comm = comm if comm is not None else A_aug.getComm()
    if out_dir is not None:
        _write_progress_event(
            out_dir,
            progress_comm,
            stage="before_ksp_create",
            status="begin",
            started=started,
            dofs=dofs,
            constraints=constraints,
            matrix_stats=matrix_stats,
            petsc_options=petsc_options,
        )
    ksp = PETSc.KSP().create(A_aug.getComm())
    ksp.setOptionsPrefix(prefix)
    ksp.setOperators(A_aug)
    opts = PETSc.Options()
    opts.prefixPush(prefix)
    for key, value in petsc_options.items():
        opts[key] = value
    ksp.setFromOptions()
    for key in petsc_options.keys():
        del opts[key]
    opts.prefixPop()
    x_aug = b_aug.duplicate()
    if out_dir is not None:
        _write_progress_event(
            out_dir,
            progress_comm,
            stage="stage4_dtn_augmented_ksp_setup",
            status="begin",
            started=started,
            dofs=dofs,
            constraints=constraints,
            matrix_stats=matrix_stats,
            petsc_options=petsc_options,
        )
        _write_progress_event(
            out_dir,
            progress_comm,
            stage="before_ksp_setup",
            status="begin",
            started=started,
            dofs=dofs,
            constraints=constraints,
            matrix_stats=matrix_stats,
            petsc_options=petsc_options,
        )
        _write_progress_event(
            out_dir,
            progress_comm,
            stage="during_ksp_setup_peak",
            status="active",
            started=started,
            dofs=dofs,
            constraints=constraints,
            matrix_stats=matrix_stats,
            petsc_options=petsc_options,
            extra={
                "stage_semantics": "external sampler labels samples while KSPSetUp is running"
            },
        )
    setup_started = time.perf_counter()
    try:
        ksp.setUp()
    except PETSc.Error as exc:
        raise DirectSolveFailure(
            "PETSc direct LU failed during Stage-4 augmented DtN KSPSetUp/LU factorization.",
            failure_stage="stage4_dtn_augmented_ksp_setup",
            petsc_error=exc,
            A=A_aug,
            b=b_aug,
            x=x_aug,
            ksp=ksp,
            solver_backend="PETSc augmented auxiliary Fourier-DtN port with dolfinx_mpc Floquet constraints",
        ) from exc
    setup_seconds = float(
        progress_comm.allreduce(time.perf_counter() - setup_started, op=MPI.MAX)
    )
    factor_inventory = _petsc_factor_inventory(ksp)
    if out_dir is not None:
        _write_progress_event(
            out_dir,
            progress_comm,
            stage="stage4_dtn_augmented_ksp_setup",
            status="end",
            started=started,
            dofs=dofs,
            constraints=constraints,
            matrix_stats=matrix_stats,
            petsc_options=petsc_options,
        )
        _write_progress_event(
            out_dir,
            progress_comm,
            stage="after_ksp_setup_factorized",
            status="end",
            started=started,
            dofs=dofs,
            constraints=constraints,
            matrix_stats=matrix_stats,
            petsc_options=petsc_options,
            extra={
                "ksp_setup_seconds": setup_seconds,
                "factor_inventory": factor_inventory,
            },
        )
    if factorization_only:
        x_aug.set(PETSc.ScalarType(0.0))
        return (
            x_aug,
            ksp,
            {
                "ksp_setup_seconds": setup_seconds,
                "ksp_solve_seconds": None,
                "factor_inventory": factor_inventory,
                "factorization_only": True,
            },
        )
    if out_dir is not None:
        _write_progress_event(
            out_dir,
            progress_comm,
            stage="stage4_dtn_augmented_solve",
            status="begin",
            started=started,
            dofs=dofs,
            constraints=constraints,
            matrix_stats=matrix_stats,
            petsc_options=petsc_options,
        )
        _write_progress_event(
            out_dir,
            progress_comm,
            stage="before_ksp_solve",
            status="begin",
            started=started,
            dofs=dofs,
            constraints=constraints,
            matrix_stats=matrix_stats,
            petsc_options=petsc_options,
        )
        _write_progress_event(
            out_dir,
            progress_comm,
            stage="during_ksp_solve_peak",
            status="active",
            started=started,
            dofs=dofs,
            constraints=constraints,
            matrix_stats=matrix_stats,
            petsc_options=petsc_options,
            extra={
                "stage_semantics": "external sampler labels samples while KSPSolve is running"
            },
        )
    solve_started = time.perf_counter()
    try:
        ksp.solve(b_aug, x_aug)
    except PETSc.Error as exc:
        raise DirectSolveFailure(
            "PETSc direct LU failed during Stage-4 augmented DtN KSPSolve.",
            failure_stage="stage4_dtn_augmented_solve",
            petsc_error=exc,
            A=A_aug,
            b=b_aug,
            x=x_aug,
            ksp=ksp,
            solver_backend="PETSc augmented auxiliary Fourier-DtN port with dolfinx_mpc Floquet constraints",
        ) from exc
    solve_seconds = float(
        progress_comm.allreduce(time.perf_counter() - solve_started, op=MPI.MAX)
    )
    if out_dir is not None:
        _write_progress_event(
            out_dir,
            progress_comm,
            stage="stage4_dtn_augmented_solve",
            status="end",
            started=started,
            dofs=dofs,
            constraints=constraints,
            matrix_stats=matrix_stats,
            petsc_options=petsc_options,
        )
        _write_progress_event(
            out_dir,
            progress_comm,
            stage="after_ksp_solve",
            status="end",
            started=started,
            dofs=dofs,
            constraints=constraints,
            matrix_stats=matrix_stats,
            petsc_options=petsc_options,
            extra={"ksp_solve_seconds": solve_seconds},
        )
    return (
        x_aug,
        ksp,
        {
            "ksp_setup_seconds": setup_seconds,
            "ksp_solve_seconds": solve_seconds,
            "factor_inventory": factor_inventory,
        },
    )


def _assign_fe_solution_from_augmented(
    x_aug: PETSc.Vec,
    floquet_data: DoubleFloquet3DData,
    n_aux: int,
):
    mpc = floquet_data.mpc
    E_total = fem.Function(mpc.function_space, name="E_total")
    index_map = E_total.function_space.dofmap.index_map
    block_size = E_total.function_space.dofmap.index_map_bs

    # Mirror dolfinx_mpc.LinearProblem.solve(): use a PETSc vector with the
    # original MPC function-space layout, ghost-update it, then let
    # fem.petsc.assign populate the Function.  Hand-copying into
    # E_total.x.array is fragile in MPI once the augmented DtN system appends
    # auxiliary rows on the final rank.
    x_fe = create_vector([(index_map, block_size)])
    row_start, row_end = x_fe.getOwnershipRange()
    if row_end > row_start:
        rows = _idx(np.arange(row_start, row_end, dtype=np.int64))
        x_fe.setValues(rows, x_aug.getValues(rows), addv=PETSc.InsertMode.INSERT_VALUES)
    x_fe.assemble()
    _ghost_update(x_fe, PETSc.InsertMode.INSERT, PETSc.ScatterMode.FORWARD)  # type: ignore[arg-type]
    fem_petsc.assign(x_fe, E_total)
    mpc.homogenize(E_total)
    mpc.backsubstitution(E_total)
    E_total.x.scatter_forward()
    x_fe.destroy()
    if n_aux == 0:
        return E_total
    return E_total


def _gather_auxiliary_values(
    x_aug: PETSc.Vec, n_fe: int, n_aux: int, comm: MPI.Intracomm
) -> np.ndarray:
    values = np.zeros(n_aux, dtype=np.complex128)
    owner_rank = comm.size - 1
    if comm.rank == owner_rank and n_aux:
        values[:] = x_aug.getValues(_idx(np.arange(n_fe, n_fe + n_aux, dtype=np.int64)))
    values = comm.bcast(values, root=owner_rank)
    return np.asarray(values, dtype=np.complex128)


def _linear_residual(
    A: PETSc.Mat, b: PETSc.Vec, x: PETSc.Vec
) -> dict[str, float | None]:
    try:
        residual = b.duplicate()
        A.mult(x, residual)
        residual.axpy(PETSc.ScalarType(-1.0), b)
        rhs_norm = float(b.norm())
        residual_norm = float(residual.norm())
        return {
            "linear_system_rhs_norm": rhs_norm,
            "linear_system_solution_norm": float(x.norm()),
            "linear_system_residual_norm": residual_norm,
            "linear_system_relative_residual": residual_norm / max(rhs_norm, 1.0e-30),
        }
    except Exception:
        return {
            "linear_system_rhs_norm": None,
            "linear_system_solution_norm": None,
            "linear_system_residual_norm": None,
            "linear_system_relative_residual": None,
        }


def _write_port_outputs(
    out_dir: Path,
    cfg: SimulationConfig3D,
    modes: list[PortMode3D],
    aux_values: np.ndarray,
    incident_projections: list[complex],
    metrics: dict[str, Any],
    comm: MPI.Intracomm,
) -> None:
    rows: list[dict[str, Any]] = []
    for idx, (mode, aux_value, inc_proj) in enumerate(
        zip(modes, aux_values, incident_projections)
    ):
        outgoing_amplitude = _outgoing_projection(
            complex(aux_value),
            complex(inc_proj),
            mode.side,
        )
        power_carrying = _mode_carries_outward_power(mode)
        modal_power = _mode_power_at_boundary(mode, cfg, outgoing_amplitude)
        power = modal_power / metrics["incident_power_code_units"]
        direction = "outgoing_up" if mode.side == "top" else "outgoing_down"
        medium = "air" if mode.side == "top" else "substrate"
        rows.append(
            {
                "auxiliary_index": idx,
                "side": mode.side,
                "direction": direction,
                "medium": medium,
                "m": mode.m,
                "n": mode.n,
                "order_m": mode.m,
                "order_n": mode.n,
                "polarization": mode.polarization,
                "alpha": mode.alpha,
                "gamma": mode.gamma,
                "beta": mode.beta,
                "kz": mode.vertical_sign * mode.beta,
                "vertical_sign": mode.vertical_sign,
                "propagating": mode.propagating,
                "power_carrying": power_carrying,
                "rayleigh_warning": mode.rayleigh_warning,
                "refractive_index": mode.refractive_index,
                "auxiliary_amplitude_total_projection": complex(aux_value),
                "incident_projection": complex(inc_proj),
                "outgoing_amplitude": outgoing_amplitude,
                "boundary_phase": _mode_boundary_phase(mode, cfg),
                "outgoing_amplitude_at_boundary": outgoing_amplitude
                * _mode_boundary_phase(mode, cfg),
                "modal_power_code_units": float(modal_power),
                "power_ratio": float(power),
                "power_source": DTN_PORT_MODAL_POWER_SOURCE,
                "R": float(power) if mode.side == "top" and power_carrying else 0.0,
                "T": float(power) if mode.side == "bottom" and power_carrying else 0.0,
            }
        )
    if comm.rank != 0:
        return
    payload = {"metrics": metrics, "orders": rows}
    port_payload = {
        "method": "port",
        "role": "primary",
        "status": "ok",
        "power_source": DTN_PORT_MODAL_POWER_SOURCE,
        "reference": DTN_PORT_MODAL_REFERENCE,
        "reference_planes": {
            "top_z": float(cfg.physical_z_max),
            "bottom_z": float(cfg.physical_z_min),
            "top_reference": "physical_z_max",
            "bottom_reference": "physical_z_min",
        },
        "R_total": metrics["R_total"],
        "R00_total": metrics["R00_total"],
        "R00_s": metrics["R00_s"],
        "R00_p": metrics["R00_p"],
        "T_total": metrics["T_total"],
        "A_balance": metrics["A_balance"],
        "R_plus_T": metrics["R_plus_T"],
        "R_total_dtn_port_modal": metrics["R_total_dtn_port_modal"],
        "T_total_dtn_port_modal": metrics["T_total_dtn_port_modal"],
        "A_balance_dtn_port_modal": metrics["A_balance_dtn_port_modal"],
        "R_plus_T_dtn_port_modal": metrics["R_plus_T_dtn_port_modal"],
        "R_plus_T_plus_A_volume_dtn_port_modal": metrics.get(
            "R_plus_T_plus_A_volume_dtn_port_modal"
        ),
        "energy_closure_error_dtn_port_modal_volume": metrics.get(
            "energy_closure_error_dtn_port_modal_volume"
        ),
        "incident_power_code_units": metrics["incident_power_code_units"],
        "stage4_dtn_order_policy": cfg.stage4_dtn_order_policy,
        "stage4_dtn_assembly": cfg.stage4_dtn_assembly,
        "modal_amplitude_convention": metrics["dtn_port_modal_amplitude_convention"],
        "orders": rows,
        "note": metrics.get("dtn_port_power_metric_note"),
    }
    (out_dir / "port_power.json").write_text(
        json.dumps(port_payload, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    (out_dir / "dtn_port_power_metrics_3d.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    (out_dir / "dtn_port_diffraction_orders_3d.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    csv_rows = [
        {
            key: _complex_text(value) if isinstance(value, complex) else value
            for key, value in row.items()
        }
        for row in rows
    ]
    with (out_dir / "dtn_port_diffraction_orders_3d.csv").open(
        "w", newline="", encoding="utf-8"
    ) as fp:
        writer = csv.DictWriter(
            fp, fieldnames=list(csv_rows[0].keys()) if csv_rows else ["side", "m", "n"]
        )
        writer.writeheader()
        writer.writerows(csv_rows)
    with (out_dir / "port_power.csv").open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(
            fp, fieldnames=list(csv_rows[0].keys()) if csv_rows else ["side", "m", "n"]
        )
        writer.writeheader()
        writer.writerows(csv_rows)
    amplitudes = [
        {
            "auxiliary_index": idx,
            "side": mode.side,
            "direction": "outgoing_up" if mode.side == "top" else "outgoing_down",
            "medium": "air" if mode.side == "top" else "substrate",
            "m": mode.m,
            "n": mode.n,
            "order_m": mode.m,
            "order_n": mode.n,
            "polarization": mode.polarization,
            "beta": mode.beta,
            "kz": mode.vertical_sign * mode.beta,
            "propagating": mode.propagating,
            "auxiliary_amplitude_total_projection": complex(aux_values[idx]),
            "incident_projection": complex(incident_projections[idx]),
            "outgoing_amplitude": _outgoing_projection(
                complex(aux_values[idx]),
                complex(incident_projections[idx]),
                mode.side,
            ),
            "boundary_phase": _mode_boundary_phase(mode, cfg),
            "outgoing_amplitude_at_boundary": (
                _outgoing_projection(
                    complex(aux_values[idx]),
                    complex(incident_projections[idx]),
                    mode.side,
                )
            )
            * _mode_boundary_phase(mode, cfg),
        }
        for idx, mode in enumerate(modes)
    ]
    (out_dir / "dtn_auxiliary_amplitudes_3d.json").write_text(
        json.dumps(amplitudes, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )


def _port_power_metrics(
    cfg: SimulationConfig3D,
    modes: list[PortMode3D],
    aux_values: np.ndarray,
    incident_projections: list[complex],
) -> dict[str, Any]:
    incident_power = incident_power_3d(cfg)
    rows_by_side = {"top": 0, "bottom": 0}
    R_total = 0.0
    T_total = 0.0
    R00_by_polarization: dict[str, float] = {}
    for mode, aux_value, inc_proj in zip(modes, aux_values, incident_projections):
        rows_by_side[mode.side] += 1
        outgoing_amplitude = _outgoing_projection(
            complex(aux_value),
            complex(inc_proj),
            mode.side,
        )
        if not _mode_carries_outward_power(mode):
            continue
        power = _mode_power_at_boundary(mode, cfg, outgoing_amplitude) / incident_power
        if mode.side == "top":
            R_total += float(power)
            if mode.m == 0 and mode.n == 0:
                R00_by_polarization[mode.polarization] = R00_by_polarization.get(
                    mode.polarization, 0.0
                ) + float(power)
        else:
            T_total += float(power)
    R00_total = float(sum(R00_by_polarization.values()))
    return {
        "R_total": float(R_total),
        "R00_total": R00_total,
        "R00_s": float(R00_by_polarization.get("s", 0.0)),
        "R00_p": float(R00_by_polarization.get("p", 0.0)),
        "R00_by_polarization": R00_by_polarization,
        "T_total": float(T_total),
        "R_plus_T": float(R_total + T_total),
        "A_balance": float(1.0 - R_total - T_total),
        "R_total_dtn_port_modal": float(R_total),
        "T_total_dtn_port_modal": float(T_total),
        "R_plus_T_dtn_port_modal": float(R_total + T_total),
        "A_balance_dtn_port_modal": float(1.0 - R_total - T_total),
        "R_plus_T_plus_A_volume": None,
        "R_plus_T_plus_A_volume_dtn_port_modal": None,
        "energy_closure_error_dtn_port_modal_volume": None,
        "power_source": DTN_PORT_MODAL_POWER_SOURCE,
        "diffraction_total_power_source": DTN_PORT_MODAL_POWER_SOURCE,
        "dtn_port_modal_reference": DTN_PORT_MODAL_REFERENCE,
        "dtn_port_top_reference_z": float(cfg.physical_z_max),
        "dtn_port_bottom_reference_z": float(cfg.physical_z_min),
        "dtn_port_modal_amplitude_convention": (
            "auxiliary unknown a_j is the total-field port projection. "
            "top outgoing amplitude = a_j - incident_projection_j; "
            "bottom outgoing amplitude = a_j. Power uses boundary-plane "
            "outgoing amplitude after applying boundary_phase."
        ),
        "dtn_port_power_metric_note": (
            "Stage-4 dtn_port R/T is computed directly from auxiliary outgoing modal amplitudes "
            "on the finite top and bottom port faces. Selected modes with positive outward real-Poynting "
            "flux contribute even when a below-critical lossy mode retains propagating=false; lossless "
            "evanescent modes carry zero modal power."
        ),
        "incident_power_code_units": float(incident_power),
        "stage4_dtn_order_policy": cfg.stage4_dtn_order_policy,
        "stage4_dtn_assembly": cfg.stage4_dtn_assembly,
        "dtn_port_mode_count": int(len(modes)),
        "dtn_port_top_mode_count": int(rows_by_side["top"]),
        "dtn_port_bottom_mode_count": int(rows_by_side["bottom"]),
        "dtn_port_propagating_mode_count": int(
            sum(1 for mode in modes if mode.propagating)
        ),
        "dtn_port_rayleigh_warning_count": int(
            sum(1 for mode in modes if mode.rayleigh_warning)
        ),
        "port_power_file": "port_power.json",
        "dtn_port_power_metrics_file": "dtn_port_power_metrics_3d.json",
        "dtn_port_orders_json": "dtn_port_diffraction_orders_3d.json",
        "dtn_port_orders_csv": "dtn_port_diffraction_orders_3d.csv",
        "port_power_csv": "port_power.csv",
        "dtn_auxiliary_amplitudes_file": "dtn_auxiliary_amplitudes_3d.json",
    }


def _port_mode_count_metrics(modes: list[PortMode3D]) -> dict[str, int]:
    rows_by_side = {"top": 0, "bottom": 0}
    for mode in modes:
        rows_by_side[mode.side] += 1
    return {
        "dtn_port_mode_count": int(len(modes)),
        "dtn_port_top_mode_count": int(rows_by_side["top"]),
        "dtn_port_bottom_mode_count": int(rows_by_side["bottom"]),
        "dtn_port_propagating_mode_count": int(
            sum(1 for mode in modes if mode.propagating)
        ),
        "dtn_port_rayleigh_warning_count": int(
            sum(1 for mode in modes if mode.rayleigh_warning)
        ),
    }


def _assemble_assembly_time_incident_traction(V, mesh_data, cfg, *,
        dtn_quadrature_degree, diagnostic_reference_incident_quadrature=False):
    """Default keeps historical integration; diagnostic reference matches native RHS."""
    form = _incident_top_traction_form(V, mesh_data, cfg)
    options = ({'quadrature_degree': dtn_quadrature_degree}
               if diagnostic_reference_incident_quadrature else {})
    return _assemble_unconstrained_vector(form, **options)


def _solve_stage4_dtn_port_total_field_impl(
    *,
    a,
    L,
    V,
    mesh_data,
    cfg: SimulationConfig3D,
    floquet_data: DoubleFloquet3DData,
    petsc_options: dict[str, Any],
    out_dir: Path,
    log,
    started: float | None = None,
    linear_solver_port: (
        Callable[
            [Stage4ExternalLinearSolverRequest],
            Stage4ExternalLinearSolverSnapshot,
        ]
        | None
    ) = None,
    variable_p_live_observer: (Callable[[Stage4VariablePLiveView], None] | None) = None,
    variable_p_retain_local_schur_for_research: bool = False,
    static_retain_local_schur_for_matrix_free: bool = False,
    matrix_free_dtn: bool = False,
    matrix_free_dtn_probe: bool = False,
    canonical_vector_export: bool = False,
    _recovery_cleanup_sink: list[VariablePRecoveredSolution],
    diagnostic_reference_incident_quadrature: bool = False,
) -> dict[str, Any]:
    """Solve the Stage-4 total-field problem with 3D Fourier-DtN ports.

    ``variable_p_live_observer`` is a default-off controlled research hook.
    It runs after primal telemetry and residuals are frozen but before the
    matrix, factor, and recovered active vectors leave this solver.
    Local Schur matrices are retained only under the separate explicit
    ``variable_p_retain_local_schur_for_research`` opt-in.
    """

    assembly_backend_audit = resolve_stage4_full3d_assembly_backend(
        cfg,
        apply=True,
    )
    assembly_backend_qualification = qualify_stage4_full3d_assembly_backend(
        cfg,
        assembly_backend_audit,
    )
    assembly_backend_fields = _assembly_backend_summary_fields(
        assembly_backend_audit,
        assembly_backend_qualification,
    )
    internal_backend_state = assembly_backend_audit["legacy_internal_state"]
    if not isinstance(internal_backend_state, dict):
        raise TypeError(
            "assembly backend audit must contain a mapping of internal state"
        )
    cell_static_condensation = bool(
        internal_backend_state["stage4_cell_static_condensation"]
    )
    assembly_time_cell_static_condensation = bool(
        internal_backend_state["stage4_assembly_time_cell_static_condensation"]
    )
    floquet_slave_elimination = bool(
        internal_backend_state["stage4_floquet_slave_elimination"]
    )
    variable_p_backend = (
        assembly_backend_audit["actual"] == ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND
    )
    never_materialized_port = isinstance(
        linear_solver_port,
        Stage4NeverMaterializedLinearSolverPort,
    )
    if diagnostic_reference_incident_quadrature and (
        linear_solver_port is None or not assembly_time_cell_static_condensation
        or variable_p_backend or never_materialized_port
    ):
        raise ValueError('diagnostic incident quadrature requires fixed-p assembled external reference')
    if matrix_free_dtn and not never_materialized_port:
        raise ValueError("matrix-free DtN requires the action-only solver port")
    if matrix_free_dtn_probe and (not matrix_free_dtn or not never_materialized_port):
        raise ValueError(
            "matrix-free DtN probe requires the matrix-free action-only port"
        )
    if never_materialized_port and (
        not assembly_time_cell_static_condensation
        or variable_p_backend
        or cfg.matrix_diagnostics_assemble_only
        or cfg.matrix_diagnostics_factorization_only
    ):
        raise ValueError(
            "the never-materialized port requires complete fixed-p "
            "assembly-time condensation"
        )
    if variable_p_live_observer is not None and not variable_p_backend:
        raise ValueError(
            "the variable-p live observer requires the exact-sequence "
            "assembly-time variable-p backend"
        )
    if canonical_vector_export and (
        not assembly_time_cell_static_condensation or variable_p_backend
    ):
        raise ValueError(
            "canonical vector export requires the fixed assembly-time "
            "static-condensed backend"
        )
    if variable_p_live_observer is not None and (
        cfg.matrix_diagnostics_assemble_only
        or cfg.matrix_diagnostics_factorization_only
    ):
        raise ValueError("the variable-p live observer requires a complete solve")
    if variable_p_retain_local_schur_for_research and variable_p_live_observer is None:
        raise ValueError("research Schur retention requires a variable-p live observer")
    log(
        "Stage-4 Full3D assembly backend "
        f"requested={assembly_backend_audit['requested']} "
        f"actual={assembly_backend_audit['actual']} "
        f"selection_source={assembly_backend_audit['selection_source']} "
        f"qualification={assembly_backend_qualification['status']}"
    )

    if cfg.stage4_dtn_assembly.lower() != "auxiliary":
        raise NotImplementedError(
            "Stage-4 3D DtN v1 supports only stage4_dtn_assembly='auxiliary'."
        )
    if cfg.use_pml:
        raise ValueError("stage4_boundary_model='dtn_port' requires use_pml=False.")
    if floquet_data is None:
        raise ValueError(
            "stage4_boundary_model='dtn_port' requires x/y Floquet constraints."
        )
    if cell_static_condensation and (
        cfg.matrix_diagnostics_assemble_only
        or cfg.matrix_diagnostics_factorization_only
    ):
        raise ValueError(
            "Task035b cell static condensation requires a complete solve; "
            "assemble-only/factorization-only diagnostics are unsupported."
        )
    if floquet_slave_elimination and not cell_static_condensation:
        raise ValueError(
            "Task035b Floquet slave elimination currently requires "
            "stage4_cell_static_condensation=True."
        )
    if assembly_time_cell_static_condensation and (
        not cell_static_condensation or not floquet_slave_elimination
    ):
        raise ValueError(
            "assembly-time cell condensation directly builds the Floquet-"
            "independent trace system and requires both Task035b flags"
        )
    comm = mesh_data.mesh.comm
    _write_progress_event(
        out_dir,
        comm,
        stage="stage4_full3d_assembly_backend",
        status="end",
        started=started,
        petsc_options=petsc_options,
        extra=assembly_backend_fields,
    )
    if _use_zero_order_local_robin_dtn(cfg):
        if cell_static_condensation:
            raise ValueError(
                "cell static condensation is unavailable for the zero-order "
                "local Robin sanity branch; use the standard full backend"
            )
        try:
            zero_order_result = _solve_zero_order_local_robin_dtn(
                a=a,
                L=L,
                V=V,
                mesh_data=mesh_data,
                cfg=cfg,
                floquet_data=floquet_data,
                petsc_options=petsc_options,
                out_dir=out_dir,
                log=log,
                started=started,
            )
        except DirectSolveFailure as exc:
            exc.extra_summary.setdefault("solver_info", {}).update(
                assembly_backend_fields
            )
            raise
        zero_order_result["solver_info"].update(assembly_backend_fields)
        return zero_order_result

    stage_start = time.perf_counter()
    timing_details: dict[str, float | int] = {}
    modes = outgoing_port_modes_3d(cfg)
    n_aux = len(modes)
    if n_aux == 0:
        raise RuntimeError("Stage-4 DtN selected zero port modes.")
    dtn_quadrature_degree = _dtn_surface_quadrature_degree(cfg, modes)
    timing_details["stage4_dtn_surface_quadrature_degree"] = int(dtn_quadrature_degree)
    assembly_time_system: AssemblyTimeCondensedSystem | None = None
    variable_p_reduction: VariablePAssemblyTimeReduction | None = None
    local_h_context = getattr(mesh_data, "local_h_context", None)
    assembly_time_full_rhs: PETSc.Vec | None = None
    variable_p_active_full_rhs: PETSc.Vec | None = None
    variable_p_trace_functional_audits: list[dict[str, Any]] = []
    dtn_action_assembler: DtnBlockAssembler | None = None
    dtn_action_blocks = None
    dtn_fine_action = None
    dtn_action_preallocation_audit = None
    dtn_action_probe = None
    dtn_action_probe_audit = None

    t0 = time.perf_counter()
    if assembly_time_cell_static_condensation:
        support_cell_groups = (
            _owned_cells_adjacent_to_facet_tag(
                mesh_data,
                cfg.tags.z_max,
            ),
            _owned_cells_adjacent_to_facet_tag(
                mesh_data,
                cfg.tags.z_min,
            ),
        )
        support_group_by_row = tuple(0 if mode.side == "top" else 1 for mode in modes)
        if variable_p_backend:
            if (
                cfg.stage4_variable_p_cell_degree_plan is None
                and local_h_context is None
            ):
                raise RuntimeError(
                    "qualified variable-p backend lost both of its plans"
                )
            variable_p_reduction = build_variable_p_assembly_time_reduction(
                fem.form(a),
                V,
                mesh_data.cell_tags,
                degree_plan_path=cfg.stage4_variable_p_cell_degree_plan,
                phase_x=floquet_data.phase_x,
                phase_y=floquet_data.phase_y,
                local_h_context=local_h_context,
                appended_global_rows=n_aux,
                appended_support_owned_cell_groups=(support_cell_groups),
                appended_support_group_by_row=(support_group_by_row),
                defer_final_assembly=True,
                retain_local_schur_for_research=(
                    variable_p_retain_local_schur_for_research
                ),
            )
            reduction_system = variable_p_reduction.system
        else:
            assembly_time_system = build_unconstrained_assembly_time_condensation(
                fem.form(a),
                V,
                mesh_data.cell_tags,
                mpc=floquet_data.mpc,
                appended_global_rows=n_aux,
                appended_support_owned_cell_groups=(support_cell_groups),
                appended_support_group_by_row=(support_group_by_row),
                defer_final_assembly=True,
                retain_local_schur_for_matrix_free=(
                    static_retain_local_schur_for_matrix_free or never_materialized_port
                ),
                materialize_global_matrix=not never_materialized_port,
            )
            reduction_system = assembly_time_system
        A_base = None
        A_aug = reduction_system.matrix
        n_fe = int(
            reduction_system.active_trace_rows
            if variable_p_reduction is not None
            else reduction_system.active_rows
        )
        if never_materialized_port:
            base_matrix_stats = {
                "matrix_type": "not_materialized_action_only",
                "matrix_rows": int(n_fe + n_aux),
                "matrix_cols": int(n_fe + n_aux),
                "matrix_nnz_used": None,
                "matrix_nnz_allocated": None,
                "matrix_average_nnz_per_row": None,
                "matrix_average_allocated_nnz_per_row": None,
                "matrix_memory_bytes": None,
                "matrix_memory_mb": None,
                "matrix_memory_estimate_bytes": None,
                "matrix_memory_estimate_mb": None,
                "matrix_norm_frobenius": None,
                "matrix_norm_infinity": None,
                "global_A_materialized": False,
                "global_F_materialized": False,
                "matrix_stats_measurement_status": "not_run_action_only",
            }
            base_matrix_lifecycle = "not_materialized_action_only"
        else:
            base_matrix_stats = _deferred_preallocation_matrix_stats(
                A_aug,
                reduction_system.build_audit["trace_preallocation"],
            )
            base_matrix_lifecycle = (
                "preallocated_values_pending_augmented_final_assembly"
            )
        timing_details.update(
            {
                f"stage4_dtn_assembly_time_{key}": value
                for key, value in reduction_system.build_audit.items()
                if key.endswith("_seconds")
            }
        )
    else:
        A_base = dolfinx_mpc.assemble_matrix(
            fem.form(a),
            floquet_data.mpc,
            bcs=None,
        )
        A_base.assemble()
        A_aug = None
        n_fe = A_base.getSize()[0]
        base_matrix_stats = _petsc_matrix_stats(A_base)
        base_matrix_lifecycle = "assembled"
    assembly_time_active = (
        assembly_time_system is not None or variable_p_reduction is not None
    )

    def reduce_assembly_time_vector(
        vector: PETSc.Vec,
        *,
        side: str,
    ) -> PETSc.Vec:
        if variable_p_reduction is not None:
            return variable_p_reduction.reduce_p6_vector(
                vector,
                side=side,
            )
        if assembly_time_system is None:
            raise RuntimeError("assembly-time vector reduction is not active")
        return condense_unconstrained_vector_to_active_trace(
            assembly_time_system,
            vector,
            side=side,
        )

    def assembly_time_interior_bilinear(
        left: PETSc.Vec,
        right: PETSc.Vec,
    ) -> complex:
        if variable_p_reduction is not None:
            return variable_p_reduction.interior_cross_bilinear(
                left,
                right,
            )
        if assembly_time_system is None:
            raise RuntimeError("assembly-time interior bilinear is not active")
        return cell_interior_schur_bilinear(
            assembly_time_system,
            left,
            right,
        )

    _write_progress_event(
        out_dir,
        comm,
        stage="stage4_dtn_base_matrix_assembled",
        status="end",
        started=started,
        dofs=int(V.dofmap.index_map.size_global * V.dofmap.index_map_bs),
        constraints=floquet_data.num_constraints,
        matrix_stats=base_matrix_stats,
        petsc_options=petsc_options,
        extra={
            "stage4_dtn_base_matrix_lifecycle": base_matrix_lifecycle,
        },
    )
    _write_progress_event(
        out_dir,
        comm,
        stage="after_base_matrix_assembly",
        status="end",
        started=started,
        dofs=int(V.dofmap.index_map.size_global * V.dofmap.index_map_bs),
        constraints=floquet_data.num_constraints,
        matrix_stats=base_matrix_stats,
        petsc_options=petsc_options,
        extra={
            "stage4_dtn_base_matrix_lifecycle": base_matrix_lifecycle,
        },
    )
    timing_details["stage4_dtn_base_matrix_assembly_seconds"] = float(
        comm.allreduce(time.perf_counter() - t0, op=MPI.MAX)
    )

    t0 = time.perf_counter()
    if assembly_time_active:
        full_b_base = _assemble_unconstrained_vector(L)
        assembly_time_full_rhs = full_b_base
        if variable_p_reduction is not None:
            variable_p_active_full_rhs = variable_p_reduction.project_p6_vector(
                full_b_base
            )
            b_aug = variable_p_reduction.reduce_active_vector(
                variable_p_active_full_rhs,
                side="right",
            )
        else:
            b_aug = reduce_assembly_time_vector(
                full_b_base,
                side="right",
            )
        b_base = None
    else:
        full_b_base = _assemble_mpc_vector(L, floquet_data.mpc)
        b_base = full_b_base
        b_aug = None
    timing_details["stage4_dtn_base_rhs_assembly_seconds"] = float(
        comm.allreduce(time.perf_counter() - t0, op=MPI.MAX)
    )

    _write_progress_event(
        out_dir,
        comm,
        stage="after_dtn_mode_enumeration",
        status="end",
        started=started,
        dofs=int(V.dofmap.index_map.size_global * V.dofmap.index_map_bs),
        constraints=floquet_data.num_constraints,
        petsc_options=petsc_options,
        extra={"stage4_dtn_num_auxiliary_dofs": int(n_aux)},
    )
    if log is not None:
        log(f"Stage-4 DtN selected auxiliary port modes = {n_aux}")
        log(
            f"Stage-4 DtN top/bottom mode count = {sum(m.side == 'top' for m in modes)} / {sum(m.side == 'bottom' for m in modes)}"
        )
        log(f"Stage-4 DtN matrix base rows = {n_fe}")
        log(f"Stage-4 DtN surface quadrature degree = {dtn_quadrature_degree}")

    t0 = time.perf_counter()
    if not assembly_time_active:
        if A_base is None or b_base is None:
            raise RuntimeError("ordinary DtN base matrix lifecycle is invalid")
        A_aug = _copy_base_matrix_to_augmented(
            A_base,
            n_aux,
            comm,
            on_allocated=lambda: _write_progress_event(
                out_dir,
                comm,
                stage="after_augmented_matrix_allocation",
                status="end",
                started=started,
                dofs=int(V.dofmap.index_map.size_global * V.dofmap.index_map_bs),
                constraints=floquet_data.num_constraints,
                petsc_options=petsc_options,
                extra={"stage4_dtn_num_auxiliary_dofs": int(n_aux)},
            ),
        )
        b_aug = _augmented_vec_from_base(b_base, n_aux, comm)
    else:
        _write_progress_event(
            out_dir,
            comm,
            stage="after_augmented_matrix_allocation",
            status="end",
            started=started,
            dofs=int(V.dofmap.index_map.size_global * V.dofmap.index_map_bs),
            constraints=floquet_data.num_constraints,
            petsc_options=petsc_options,
            extra={
                "stage4_dtn_num_auxiliary_dofs": int(n_aux),
                "assembly_time_final_augmented_matrix": not never_materialized_port,
                "base_to_augmented_matrix_copy_performed": False,
                "global_A_materialized": not never_materialized_port,
                "global_F_materialized": not never_materialized_port,
            },
        )
    _write_progress_event(
        out_dir,
        comm,
        stage="after_base_matrix_copy",
        status="end",
        started=started,
        dofs=int(V.dofmap.index_map.size_global * V.dofmap.index_map_bs),
        constraints=floquet_data.num_constraints,
        petsc_options=petsc_options,
        extra={"stage4_dtn_num_auxiliary_dofs": int(n_aux)},
    )
    timing_details["stage4_dtn_augmented_block_copy_seconds"] = (
        float(comm.allreduce(time.perf_counter() - t0, op=MPI.MAX))
        if not assembly_time_active
        else 0.0
    )
    if cfg.direct_release_base_after_augmentation and not assembly_time_active:
        if A_base is None or b_base is None:
            raise RuntimeError("ordinary DtN base release state is invalid")
        A_base.destroy()
        b_base.destroy()
        A_base = None
        b_base = None
        _write_progress_event(
            out_dir,
            comm,
            stage="after_base_matrix_release",
            status="end",
            started=started,
            dofs=int(V.dofmap.index_map.size_global * V.dofmap.index_map_bs),
            constraints=floquet_data.num_constraints,
            petsc_options=petsc_options,
            extra={
                "direct_release_base_after_augmentation": True,
                "released_objects": ["A_base", "b_base"],
            },
        )
    elif assembly_time_active:
        _write_progress_event(
            out_dir,
            comm,
            stage="after_base_matrix_release",
            status="end",
            started=started,
            dofs=int(V.dofmap.index_map.size_global * V.dofmap.index_map_bs),
            constraints=floquet_data.num_constraints,
            petsc_options=petsc_options,
            extra={
                "direct_release_base_after_augmentation": True,
                "released_objects": [],
                "base_matrix_was_never_allocated": True,
                "base_to_augmented_matrix_copy_performed": False,
            },
        )

    trace_only_content_identity_active = bool(
        variable_p_live_observer is not None and variable_p_reduction is not None
    )
    external_operator_digest = (
        hashlib.sha256() if trace_only_content_identity_active else None
    )
    external_rhs_digest = (
        hashlib.sha256() if trace_only_content_identity_active else None
    )
    if external_operator_digest is not None and external_rhs_digest is not None:
        timing_details["stage4_dtn_trace_only_base_reduced_rhs_norm"] = float(
            b_aug.norm()
        )
        external_operator_digest.update(
            b"task035d.trace-only-external-operator.local.v1\0"
        )
        external_rhs_digest.update(b"task035d.trace-only-external-rhs.local.v1\0")
        dimensions = np.asarray(
            [
                int(n_fe),
                int(n_aux),
                int(comm.rank),
                int(comm.size),
                *map(int, A_aug.getOwnershipRange()),
                *map(int, b_aug.getOwnershipRange()),
            ],
            dtype=np.int64,
        )
        _update_evidence_digest_array(
            external_operator_digest,
            "dimensions",
            dimensions,
            dtype=np.dtype("<i8"),
        )
        _update_evidence_digest_array(
            external_rhs_digest,
            "dimensions",
            dimensions,
            dtype=np.dtype("<i8"),
        )
        _update_evidence_digest_array(
            external_rhs_digest,
            "base-reduced-rhs-owned",
            b_aug.getArray(readonly=True),
            dtype=np.dtype("<c16"),
        )

    if never_materialized_port:
        if assembly_time_system is None:
            raise RuntimeError("action-only port lost its assembly-time system")
        support_groups = owned_active_support_groups(
            assembly_time_system,
            support_cell_groups,
        )
        base_active_rhs = assembly_time_system.create_active_vector()
        local_active_rows = base_active_rhs.getLocalSize()
        base_active_rhs.getArray()[:] = b_aug.getArray(readonly=True)[
            :local_active_rows
        ]
        base_active_rhs.assemble()
        support_rows = tuple(support_groups[group] for group in support_group_by_row)
        if matrix_free_dtn_probe:
            mode_identities = tuple(
                {
                    "mode_key": [
                        str(mode.side),
                        int(mode.m),
                        int(mode.n),
                        str(mode.polarization),
                    ],
                    "beta": [
                        float(complex(mode.beta).real),
                        float(complex(mode.beta).imag),
                    ],
                    "polarization": str(mode.polarization),
                    "power_normalization": float(mode.power_per_unit_amplitude),
                    "rayleigh_warning": bool(mode.rayleigh_warning),
                }
                for mode in modes
            )
            dtn_action_probe = MatrixFreeDtnProbe(
                base_active_rhs,
                n_aux,
                traction_supports=support_rows,
                ell_supports=support_rows,
                mode_identities=mode_identities,
                expected_mode_count=80,
            )
            dtn_action_assembler = dtn_action_probe.primary_assembler
        else:
            dtn_action_assembler = DtnBlockAssembler(
                base_active_rhs,
                n_aux,
                traction_supports=support_rows,
                ell_supports=support_rows,
                matrix_free_dtn=matrix_free_dtn,
            )
        base_active_rhs.destroy()

    t0 = time.perf_counter()
    if assembly_time_active:
        if assembly_time_full_rhs is None:
            raise RuntimeError("assembly-time full RHS was not initialized")
        incident_traction_vec = _assemble_assembly_time_incident_traction(
            V, mesh_data, cfg, dtn_quadrature_degree=dtn_quadrature_degree,
            diagnostic_reference_incident_quadrature=diagnostic_reference_incident_quadrature,
        )
        if variable_p_reduction is not None:
            if variable_p_active_full_rhs is None:
                raise RuntimeError("variable-p active full RHS was not initialized")
            active_incident = variable_p_reduction.project_p6_vector(
                incident_traction_vec
            )
            variable_p_trace_functional_audits.append(
                variable_p_reduction.enforce_trace_only_active_functional(
                    active_incident,
                    role="incident_top_traction",
                )
            )
            reduced_incident = variable_p_reduction.reduce_active_vector(
                active_incident,
                side="right",
            )
            variable_p_active_full_rhs.axpy(
                PETSc.ScalarType(1.0),
                active_incident,
            )
            active_incident.destroy()
        else:
            reduced_incident = reduce_assembly_time_vector(
                incident_traction_vec,
                side="right",
            )
        inc_rows, inc_values = _vec_nonzero_owned_entries(reduced_incident)
        if variable_p_reduction is None:
            assembly_time_full_rhs.axpy(
                PETSc.ScalarType(1.0),
                incident_traction_vec,
            )
        reduced_incident.destroy()
        incident_traction_vec.destroy()
    else:
        incident_traction_vec = _assemble_mpc_vector(
            _incident_top_traction_form(V, mesh_data, cfg),
            floquet_data.mpc,
        )
        inc_rows, inc_values = _vec_nonzero_owned_entries(incident_traction_vec)
        incident_traction_vec.destroy()
    if external_rhs_digest is not None:
        _update_evidence_digest_sparse(
            external_rhs_digest,
            "incident-top-traction",
            inc_rows,
            inc_values,
        )
    if len(inc_rows):
        if never_materialized_port:
            if dtn_action_probe is not None:
                dtn_action_probe.add_active_rhs(inc_rows, inc_values)
            else:
                if dtn_action_assembler is None:
                    raise RuntimeError("action-only RHS sink is unavailable")
                dtn_action_assembler.b_fe.setValues(
                    inc_rows,
                    inc_values,
                    addv=PETSc.InsertMode.ADD_VALUES,
                )
        else:
            b_aug.setValues(
                inc_rows,
                inc_values,
                addv=PETSc.InsertMode.ADD_VALUES,
            )
    timing_details["stage4_dtn_incident_source_vector_seconds"] = float(
        comm.allreduce(time.perf_counter() - t0, op=MPI.MAX)
    )

    incident_projections: list[complex] = []
    surface_assemblers = {
        ("top", 0): _ReusableSurfaceComponentAssembler(
            V, mesh_data, cfg.tags.z_max, 0, quadrature_degree=dtn_quadrature_degree
        ),
        ("top", 1): _ReusableSurfaceComponentAssembler(
            V, mesh_data, cfg.tags.z_max, 1, quadrature_degree=dtn_quadrature_degree
        ),
        ("bottom", 0): _ReusableSurfaceComponentAssembler(
            V, mesh_data, cfg.tags.z_min, 0, quadrature_degree=dtn_quadrature_degree
        ),
        ("bottom", 1): _ReusableSurfaceComponentAssembler(
            V, mesh_data, cfg.tags.z_min, 1, quadrature_degree=dtn_quadrature_degree
        ),
    }
    try:
        trace_alias_preflight = _dtn_n0_trace_alias_preflight(
            modes,
            surface_assemblers,
            floquet_data.mpc,
            enabled=bool(cfg.dtn_y_invariant_n0_alias_preflight),
            overlap_tolerance=float(cfg.dtn_trace_alias_overlap_tolerance),
        )
    except DtnTraceAliasError as exc:
        if comm.rank == 0:
            (out_dir / "dtn_trace_alias_preflight.json").write_text(
                json.dumps(
                    exc.audit,
                    ensure_ascii=False,
                    indent=2,
                    default=_json_default,
                ),
                encoding="utf-8",
            )
        raise
    component_key: tuple[str, int, int, complex] | None = None
    component_right_entries: (
        tuple[
            tuple[np.ndarray, np.ndarray],
            tuple[np.ndarray, np.ndarray],
        ]
        | None
    ) = None
    component_left_entries: (
        tuple[
            tuple[np.ndarray, np.ndarray],
            tuple[np.ndarray, np.ndarray],
        ]
        | None
    ) = None
    component_full_vectors: tuple[PETSc.Vec, PETSc.Vec] | None = None
    component_active_vectors: tuple[PETSc.Vec, PETSc.Vec] | None = None
    component_interior_bilinear: np.ndarray | None = None
    unique_surface_orders = 0
    component_vector_assemblies = 0
    component_vector_cache_hits = 0
    modal_vector_assembly_seconds_local = 0.0
    modal_block_insert_seconds_local = 0.0
    traction_rows_total_local = 0
    ell_cols_total_local = 0
    matrix_insert_mode = (
        PETSc.InsertMode.ADD_VALUES
        if assembly_time_active
        else PETSc.InsertMode.INSERT_VALUES
    )
    matrix_row_start, matrix_row_end = (
        b_aug.getOwnershipRange()
        if never_materialized_port
        else A_aug.getOwnershipRange()
    )
    modal_loop_start = time.perf_counter()
    for aux_index, mode in enumerate(modes):
        mode_key = (mode.side, int(mode.m), int(mode.n), complex(mode.k_vector[2]))
        if mode_key != component_key or component_right_entries is None:
            t_component = time.perf_counter()
            if assembly_time_active:
                if component_full_vectors is not None:
                    for vector in component_full_vectors:
                        vector.destroy()
                if component_active_vectors is not None:
                    for vector in component_active_vectors:
                        vector.destroy()
                    component_active_vectors = None
                component_full_vectors = (
                    surface_assemblers[(mode.side, 0)].assemble_unconstrained_vector(
                        mode
                    ),
                    surface_assemblers[(mode.side, 1)].assemble_unconstrained_vector(
                        mode
                    ),
                )
                if variable_p_reduction is not None:
                    component_active_vectors = tuple(
                        variable_p_reduction.project_p6_vector(vector)
                        for vector in component_full_vectors
                    )
                    for component, vector in enumerate(component_active_vectors):
                        variable_p_trace_functional_audits.append(
                            variable_p_reduction.enforce_trace_only_active_functional(
                                vector,
                                role=(
                                    f"{mode.side}_surface_component_"
                                    f"{component}_m{mode.m}_n{mode.n}"
                                ),
                            )
                        )
                    right_vectors = tuple(
                        variable_p_reduction.reduce_active_vector(
                            vector,
                            side="right",
                        )
                        for vector in component_active_vectors
                    )
                    left_vectors = tuple(
                        variable_p_reduction.reduce_active_vector(
                            vector,
                            side="left",
                        )
                        for vector in component_active_vectors
                    )
                else:
                    right_vectors = tuple(
                        reduce_assembly_time_vector(
                            vector,
                            side="right",
                        )
                        for vector in component_full_vectors
                    )
                    left_vectors = tuple(
                        reduce_assembly_time_vector(
                            vector,
                            side="left",
                        )
                        for vector in component_full_vectors
                    )
                component_right_entries = tuple(
                    _vec_nonzero_owned_entries(vector) for vector in right_vectors
                )
                component_left_entries = tuple(
                    _vec_nonzero_owned_entries(vector) for vector in left_vectors
                )
                for vector in (*right_vectors, *left_vectors):
                    vector.destroy()
                if (
                    variable_p_reduction is not None
                    and component_active_vectors is not None
                ):
                    component_interior_bilinear = np.zeros(
                        (2, 2),
                        dtype=np.complex128,
                    )
                else:
                    component_interior_bilinear = np.asarray(
                        [
                            [
                                assembly_time_interior_bilinear(
                                    left,
                                    right,
                                )
                                for right in component_full_vectors
                            ]
                            for left in component_full_vectors
                        ],
                        dtype=np.complex128,
                    )
            else:
                component_right_entries = (
                    surface_assemblers[(mode.side, 0)].assemble_entries(
                        mode, floquet_data.mpc
                    ),
                    surface_assemblers[(mode.side, 1)].assemble_entries(
                        mode, floquet_data.mpc
                    ),
                )
                component_left_entries = component_right_entries
                component_interior_bilinear = None
            modal_vector_assembly_seconds_local += time.perf_counter() - t_component
            component_key = mode_key
            unique_surface_orders += 1
            component_vector_assemblies += 2
        else:
            component_vector_cache_hits += 1

        if component_left_entries is None:
            raise RuntimeError("DtN left component cache is unavailable")
        traction_vector = _traction_vector(mode, cfg)
        ell_cols, ell_values = _combine_owned_entries(
            component_left_entries,
            (mode.e_vector[0], mode.e_vector[1]),
            comm=comm,
        )
        traction_rows, traction_values = _combine_owned_entries(
            component_right_entries,
            (traction_vector[0], traction_vector[1]),
            comm=comm,
        )
        aux_global = n_fe + aux_index
        denominator = _mode_projection_denominator(mode, cfg)
        incident_projection = _incident_projection_onto_top_mode(mode, cfg)
        incident_projections.append(incident_projection)
        if external_rhs_digest is not None:
            external_rhs_digest.update(
                (
                    f"mode-rhs:{aux_index}:{mode.side}:"
                    f"{mode.m}:{mode.n}:{mode.polarization}"
                ).encode("ascii")
            )
            external_rhs_digest.update(b"\0")
            _update_evidence_digest_sparse(
                external_rhs_digest,
                f"mode-{aux_index}-incident-projection",
                traction_rows,
                -traction_values * incident_projection,
            )

        t_insert = time.perf_counter()
        if len(traction_rows):
            traction_rows_total_local += int(len(traction_rows))
            if not never_materialized_port:
                A_aug.setValues(
                    traction_rows,
                    _idx([aux_global]),
                    (-traction_values).reshape((len(traction_rows), 1)),
                    addv=matrix_insert_mode,
                )
                if incident_projection != 0.0:
                    b_aug.setValues(
                        traction_rows,
                        -traction_values * incident_projection,
                        addv=PETSc.InsertMode.ADD_VALUES,
                    )
        if incident_projection != 0.0 and (
            component_active_vectors is not None or component_full_vectors is not None
        ):
            if variable_p_reduction is not None:
                if (
                    variable_p_active_full_rhs is None
                    or component_active_vectors is None
                ):
                    raise RuntimeError("variable-p modal RHS lifecycle is invalid")
                for coefficient, vector in zip(
                    traction_vector[:2],
                    component_active_vectors,
                    strict=True,
                ):
                    variable_p_active_full_rhs.axpy(
                        PETSc.ScalarType(-incident_projection * coefficient),
                        vector,
                    )
            else:
                if assembly_time_full_rhs is None or component_full_vectors is None:
                    raise RuntimeError("assembly-time modal RHS lifecycle is invalid")
                for coefficient, vector in zip(
                    traction_vector[:2],
                    component_full_vectors,
                    strict=True,
                ):
                    assembly_time_full_rhs.axpy(
                        PETSc.ScalarType(-incident_projection * coefficient),
                        vector,
                    )

        if len(ell_cols):
            ell_cols_total_local += int(len(ell_cols))
            if not never_materialized_port:
                A_aug.setValues(
                    _idx([aux_global]),
                    ell_cols,
                    (-np.conj(ell_values) / denominator).reshape((1, len(ell_cols))),
                    addv=matrix_insert_mode,
                )
        auxiliary_diagonal = 1.0 + 0.0j
        if component_interior_bilinear is not None:
            electric = np.asarray(
                mode.e_vector[:2],
                dtype=np.complex128,
            )
            traction = np.asarray(
                traction_vector[:2],
                dtype=np.complex128,
            )
            auxiliary_diagonal -= complex(
                np.vdot(
                    electric,
                    component_interior_bilinear @ traction,
                )
                / denominator
            )
        if external_operator_digest is not None:
            external_operator_digest.update(
                (
                    f"mode-operator:{aux_index}:{mode.side}:"
                    f"{mode.m}:{mode.n}:{mode.polarization}"
                ).encode("ascii")
            )
            external_operator_digest.update(b"\0")
            _update_evidence_digest_sparse(
                external_operator_digest,
                f"mode-{aux_index}-upper-right",
                traction_rows,
                -traction_values,
            )
            _update_evidence_digest_sparse(
                external_operator_digest,
                f"mode-{aux_index}-lower-left",
                ell_cols,
                -np.conj(ell_values) / denominator,
            )
            _update_evidence_digest_array(
                external_operator_digest,
                f"mode-{aux_index}-auxiliary-diagonal",
                np.asarray([auxiliary_diagonal]),
                dtype=np.dtype("<c16"),
            )
        if matrix_row_start <= aux_global < matrix_row_end:
            if not never_materialized_port:
                A_aug.setValue(
                    aux_global,
                    aux_global,
                    PETSc.ScalarType(auxiliary_diagonal),
                    addv=matrix_insert_mode,
                )
        if never_materialized_port:
            if dtn_action_assembler is None:
                raise RuntimeError("action-only modal sink is unavailable")
            dtn_action_sink = (
                dtn_action_probe
                if dtn_action_probe is not None
                else dtn_action_assembler
            )
            dtn_action_sink.add_mode(
                aux_index,
                traction_rows=traction_rows,
                traction_values=-traction_values,
                ell_cols=ell_cols,
                ell_values=-np.conj(ell_values) / denominator,
                auxiliary_diagonal=auxiliary_diagonal,
                b_fe_rows=traction_rows if incident_projection != 0.0 else None,
                b_fe_values=(
                    -traction_values * incident_projection
                    if incident_projection != 0.0
                    else None
                ),
            )
        modal_block_insert_seconds_local += time.perf_counter() - t_insert

        if log is not None and (aux_index + 1) % 50 == 0:
            elapsed = comm.allreduce(time.perf_counter() - stage_start, op=MPI.MAX)
            log(
                f"Stage-4 DtN prepared {aux_index + 1}/{n_aux} auxiliary modes "
                f"in {elapsed:.3f} seconds; unique surface orders = {unique_surface_orders}"
            )

    if component_full_vectors is not None:
        for vector in component_full_vectors:
            vector.destroy()
    if component_active_vectors is not None:
        for vector in component_active_vectors:
            vector.destroy()

    if external_operator_digest is not None and external_rhs_digest is not None:
        timing_details["stage4_dtn_trace_only_external_operator_sha256"] = (
            _partition_bound_evidence_sha256(
                comm,
                namespace=("task035d.trace-only-external-operator.partition.v1"),
                local_sha256=external_operator_digest.hexdigest(),
            )
        )
        timing_details["stage4_dtn_trace_only_external_rhs_sha256"] = (
            _partition_bound_evidence_sha256(
                comm,
                namespace="task035d.trace-only-external-rhs.partition.v1",
                local_sha256=external_rhs_digest.hexdigest(),
            )
        )
        timing_details["stage4_dtn_trace_only_content_identity_mpi_size"] = int(
            comm.size
        )
        timing_details["stage4_dtn_trace_only_content_identity_partition_bound"] = True

    if variable_p_reduction is not None:
        timing_details["stage4_dtn_variable_p_auxiliary_interior_columns_allocated"] = (
            False
        )
        timing_details[
            "stage4_dtn_variable_p_auxiliary_interior_column_bytes_local_max"
        ] = 0
    if variable_p_trace_functional_audits:
        removed_over_threshold = [
            float(audit["removed_active_interior_max_abs"])
            / float(audit["acceptance_threshold"])
            for audit in variable_p_trace_functional_audits
        ]
        timing_details["stage4_dtn_variable_p_trace_functional_count"] = len(
            variable_p_trace_functional_audits
        )
        timing_details["stage4_dtn_variable_p_removed_interior_max_abs"] = max(
            float(audit["removed_active_interior_max_abs"])
            for audit in variable_p_trace_functional_audits
        )
        timing_details["stage4_dtn_variable_p_acceptance_threshold_max_abs"] = max(
            float(audit["acceptance_threshold"])
            for audit in variable_p_trace_functional_audits
        )
        timing_details["stage4_dtn_variable_p_removed_interior_over_threshold_max"] = (
            max(removed_over_threshold)
        )
        timing_details["stage4_dtn_variable_p_trace_only_gate_pass"] = True

    timing_details["stage4_dtn_modal_loop_seconds"] = float(
        comm.allreduce(time.perf_counter() - modal_loop_start, op=MPI.MAX)
    )
    timing_details["stage4_dtn_modal_vector_assembly_seconds"] = float(
        comm.allreduce(modal_vector_assembly_seconds_local, op=MPI.MAX)
    )
    timing_details["stage4_dtn_modal_block_insert_seconds"] = float(
        comm.allreduce(modal_block_insert_seconds_local, op=MPI.MAX)
    )
    timing_details["stage4_dtn_unique_surface_orders"] = int(
        comm.allreduce(unique_surface_orders, op=MPI.MAX)
    )
    timing_details["stage4_dtn_component_vector_assemblies"] = int(
        comm.allreduce(component_vector_assemblies, op=MPI.MAX)
    )
    timing_details["stage4_dtn_component_vector_cache_hits"] = int(
        comm.allreduce(component_vector_cache_hits, op=MPI.MAX)
    )
    traction_rows_total = int(comm.allreduce(traction_rows_total_local, op=MPI.SUM))
    ell_cols_total = int(comm.allreduce(ell_cols_total_local, op=MPI.SUM))
    dtn_auxiliary_block_stats = _local_augmented_dtn_coupling_stats(
        n_fe=n_fe,
        n_aux=n_aux,
        traction_rows_total=traction_rows_total,
        ell_cols_total=ell_cols_total,
    )
    if log is not None:
        log(
            "Stage-4 DtN modal cache summary: "
            f"unique surface orders = {timing_details['stage4_dtn_unique_surface_orders']}, "
            f"x/y component vector assemblies = {timing_details['stage4_dtn_component_vector_assemblies']}, "
            f"polarization cache hits = {timing_details['stage4_dtn_component_vector_cache_hits']}"
        )
        log(f"Stage-4 DtN base matrix nnz = {base_matrix_stats.get('matrix_nnz_used')}")
        log(
            f"Stage-4 DtN auxiliary coupling nnz estimate = {dtn_auxiliary_block_stats['dtn_auxiliary_coupling_nnz_estimate']}"
        )

    _write_progress_event(
        out_dir,
        comm,
        stage="after_dtn_coupling_insert",
        status="end",
        started=started,
        dofs=int(V.dofmap.index_map.size_global * V.dofmap.index_map_bs),
        constraints=floquet_data.num_constraints,
        petsc_options=petsc_options,
        extra={
            "stage4_dtn_num_auxiliary_dofs": int(n_aux),
            "dtn_auxiliary_block_stats": dtn_auxiliary_block_stats,
            "dtn_trace_alias_preflight": trace_alias_preflight,
        },
    )

    t0 = time.perf_counter()
    if never_materialized_port:
        if dtn_action_assembler is None or assembly_time_system is None:
            raise RuntimeError("action-only modal sink was not initialized")
        dtn_action_preallocation_audit = dict(dtn_action_assembler.preallocation_audit)
        if dtn_action_probe is not None:
            dtn_action_blocks = dtn_action_probe.finish()
            dtn_action_probe_audit = dtn_action_probe.audit()
            if not dtn_action_probe_audit["gate_pass"]:
                dtn_action_probe.destroy()
                raise RuntimeError("MATRIX_FREE_DTN_FORMAL_80MODE_GATE_FAILED")
        else:
            dtn_action_blocks = dtn_action_assembler.finish()
        dtn_fine_action, _ = create_static_local_schur_action(assembly_time_system)
        A_aug, _ = create_matrix_free_augmented_operator(
            dtn_action_blocks,
            dtn_fine_action,
        )
        old_b_aug = b_aug
        b_aug = assembly_time_system.create_augmented_vector()
        combine_petsc_augmented_solution(
            dtn_action_blocks,
            dtn_action_blocks.b_fe,
            dtn_action_blocks.b_aux,
            b_aug,
        )
        old_b_aug.destroy()
        augmented_matrix_stats_after_finalize = {
            **_petsc_matrix_stats(A_aug, assemble=False),
            "global_A_materialized": False,
            "global_F_materialized": False,
        }
    else:
        A_aug.assemble()
        b_aug.assemble()
        augmented_matrix_stats_after_finalize = _petsc_matrix_stats(A_aug)
    storage_carrier_fe_dofs = int(
        V.dofmap.index_map.size_global * V.dofmap.index_map_bs
    )
    active_exact_sequence_fe_dofs = (
        _variable_p_active_fe_dofs(variable_p_reduction.build_audit)
        if variable_p_reduction is not None
        else storage_carrier_fe_dofs
    )
    assembled_dof_row_fields = _dof_row_semantics(
        active_exact_sequence_fe_dofs=active_exact_sequence_fe_dofs,
        storage_carrier_fe_dofs=storage_carrier_fe_dofs,
        independent_trace_rows=int(n_fe) if assembly_time_active else None,
        augmented_rows=int(n_fe + n_aux),
        auxiliary_rows=int(n_aux),
    )
    timing_details["stage4_dtn_augmented_matrix_finalize_seconds"] = float(
        comm.allreduce(time.perf_counter() - t0, op=MPI.MAX)
    )
    _write_progress_event(
        out_dir,
        comm,
        stage="stage4_dtn_augmented_matrix_finalized",
        status="end",
        started=started,
        dofs=int(V.dofmap.index_map.size_global * V.dofmap.index_map_bs),
        constraints=floquet_data.num_constraints,
        matrix_stats=augmented_matrix_stats_after_finalize,
        petsc_options=petsc_options,
        extra={
            "stage4_dtn_num_auxiliary_dofs": int(n_aux),
            "global_A_materialized": not never_materialized_port,
            "global_F_materialized": not never_materialized_port,
            "dtn_action_preallocation_audit": dtn_action_preallocation_audit,
        },
    )

    if cfg.matrix_diagnostics_assemble_only or matrix_free_dtn_probe:
        component_only = bool(matrix_free_dtn_probe)
        x_aug = b_aug.duplicate()
        ksp = PETSc.KSP().create(A_aug.getComm())
        ksp.setOptionsPrefix(f"stage4_3d_dtn_{cfg.case_name}_")
        ksp.setOperators(A_aug)
        opts = PETSc.Options()
        opts.prefixPush(f"stage4_3d_dtn_{cfg.case_name}_")
        for key, value in petsc_options.items():
            opts[key] = value
        ksp.setFromOptions()
        for key in petsc_options.keys():
            del opts[key]
        opts.prefixPop()
        E_total = (
            None
            if component_only
            else fem.Function(floquet_data.mpc.function_space, name="E_total")
        )
        solver_info = {
            "solver_backend": "PETSc augmented auxiliary Fourier-DtN port with dolfinx_mpc Floquet constraints",
            "assemble_only": True,
            "matrix_free_dtn_component_only": component_only,
            "matrix_free_dtn_probe": bool(matrix_free_dtn_probe),
            "matrix_free_dtn_probe_audit": dtn_action_probe_audit,
            "global_A_materialized": False
            if component_only
            else not never_materialized_port,
            "global_F_materialized": False
            if component_only
            else not never_materialized_port,
            "ordinary_default_changed": False,
            **assembly_backend_fields,
            "num_auxiliary_dofs": int(n_aux),
            "num_fem_dofs_after_mpc": int(n_fe),
            "num_total_augmented_dofs": int(n_fe + n_aux),
            **assembled_dof_row_fields,
            "stage4_dtn_assembly_seconds": float(
                comm.allreduce(time.perf_counter() - stage_start, op=MPI.MAX)
            ),
            "ksp_converged_reason": 0,
            "ksp_iterations": 0,
            "actual_ksp_type": ksp.getType(),
            "actual_pc_type": ksp.getPC().getType(),
            "actual_pc_factor_solver_type": None,
            "dtn_base_matrix_stats": base_matrix_stats,
            "dtn_augmented_matrix_stats_after_finalize": augmented_matrix_stats_after_finalize,
            "dtn_auxiliary_block_stats": dtn_auxiliary_block_stats,
            "dtn_trace_alias_preflight": trace_alias_preflight,
            "explicit_chac_constructed": False,
            "dtn_auxiliary_dense_block_constructed": False,
            **timing_details,
        }
        return {
            "E_total": E_total,
            "A": A_aug,
            "b": b_aug,
            "x": x_aug,
            "ksp": ksp,
            "solver_info": solver_info,
            "port_metrics": {
                "R_total": None,
                "T_total": None,
                "R_plus_T": None,
                "A_balance": None,
                "diffraction_total_power_source": "assemble_only_skipped",
                **_port_mode_count_metrics(modes),
            },
        }

    condensed_system = None
    condensed_matrix_stats = None
    independent_trace_system = None
    independent_trace_matrix_stats = None
    condensation_recovery = None
    solve_A = A_aug
    solve_b = b_aug
    solve_dofs = (
        int(n_fe + n_aux)
        if assembly_time_active
        else int(V.dofmap.index_map.size_global * V.dofmap.index_map_bs)
    )
    solve_prefix = (
        f"stage4_3d_dtn_variable_p_condensed_{cfg.case_name}_"
        if variable_p_reduction is not None
        else f"stage4_3d_dtn_assembly_time_condensed_{cfg.case_name}_"
        if assembly_time_active
        else f"stage4_3d_dtn_{cfg.case_name}_"
    )
    if cell_static_condensation and not assembly_time_active:
        condensation_started = time.perf_counter()
        _write_progress_event(
            out_dir,
            comm,
            stage="stage4_dtn_cell_static_condensation",
            status="begin",
            started=started,
            dofs=solve_dofs,
            constraints=floquet_data.num_constraints,
            matrix_stats=augmented_matrix_stats_after_finalize,
            petsc_options=petsc_options,
        )
        condensed_system = build_explicit_cell_static_condensation(
            A_aug,
            b_aug,
            owned_hcurl_cell_interior_dofs(V),
        )
        condensed_matrix_stats = _petsc_matrix_stats(condensed_system.matrix)
        timing_details["stage4_dtn_cell_static_condensation_build_seconds"] = float(
            comm.allreduce(
                time.perf_counter() - condensation_started,
                op=MPI.MAX,
            )
        )
        solve_A = condensed_system.matrix
        solve_b = condensed_system.rhs
        solve_dofs = int(condensed_system.trace_rows)
        solve_prefix = f"stage4_3d_dtn_cell_condensed_{cfg.case_name}_"
        _write_progress_event(
            out_dir,
            comm,
            stage="stage4_dtn_cell_static_condensation",
            status="end",
            started=started,
            dofs=solve_dofs,
            constraints=floquet_data.num_constraints,
            matrix_stats=condensed_matrix_stats,
            petsc_options=petsc_options,
            extra={
                "cell_static_condensation": condensed_system.build_audit,
            },
        )
        if floquet_slave_elimination:
            independent_started = time.perf_counter()
            dofmap = V.dofmap
            if int(dofmap.index_map_bs) != 1:
                raise NotImplementedError(
                    "Floquet slave elimination requires scalar-blocked H(curl)"
                )
            local_slaves = np.unique(
                np.asarray(
                    floquet_data.local_slave_dofs,
                    dtype=np.int64,
                )
            )
            owned_slaves = local_slaves[
                (local_slaves >= 0) & (local_slaves < int(dofmap.index_map.size_local))
            ]
            owned_slave_original_dofs = (
                owned_slaves + int(dofmap.index_map.local_range[0])
            ).astype(PETSc.IntType)
            independent_trace_system = build_floquet_independent_trace_system(
                condensed_system.matrix,
                condensed_system.rhs,
                owned_slave_original_dofs=owned_slave_original_dofs,
                original_to_trace=condensed_system.original_to_trace,
            )
            independent_trace_matrix_stats = _petsc_matrix_stats(
                independent_trace_system.matrix
            )
            timing_details["stage4_dtn_floquet_slave_elimination_build_seconds"] = (
                float(
                    comm.allreduce(
                        time.perf_counter() - independent_started,
                        op=MPI.MAX,
                    )
                )
            )
            solve_A = independent_trace_system.matrix
            solve_b = independent_trace_system.rhs
            solve_dofs = int(independent_trace_system.active_rows)
            solve_prefix = (
                f"stage4_3d_dtn_cell_condensed_floquet_independent_{cfg.case_name}_"
            )
            _write_progress_event(
                out_dir,
                comm,
                stage="stage4_dtn_floquet_slave_elimination",
                status="end",
                started=started,
                dofs=solve_dofs,
                constraints=floquet_data.num_constraints,
                matrix_stats=independent_trace_matrix_stats,
                petsc_options=petsc_options,
                extra={
                    "floquet_slave_elimination": (independent_trace_system.build_audit),
                },
            )

    independent_trace_rows = (
        int(n_fe)
        if assembly_time_active
        else (
            int(independent_trace_system.active_rows) - int(n_aux)
            if independent_trace_system is not None
            else None
        )
    )
    solved_dof_row_fields = _dof_row_semantics(
        active_exact_sequence_fe_dofs=active_exact_sequence_fe_dofs,
        storage_carrier_fe_dofs=storage_carrier_fe_dofs,
        independent_trace_rows=independent_trace_rows,
        augmented_rows=int(solve_A.getSize()[0]),
        auxiliary_rows=int(n_aux),
    )

    t0 = time.perf_counter()
    external_snapshot: Stage4ExternalLinearSolverSnapshot | None = None
    try:
        if linear_solver_port is None:
            solve_x, ksp, ksp_telemetry = _solve_augmented_system(
                solve_A,
                solve_b,
                petsc_options,
                solve_prefix,
                out_dir=out_dir,
                comm=comm,
                started=started,
                dofs=solve_dofs,
                constraints=floquet_data.num_constraints,
                matrix_stats=(
                    independent_trace_matrix_stats
                    if independent_trace_matrix_stats is not None
                    else condensed_matrix_stats
                    if condensed_matrix_stats is not None
                    else augmented_matrix_stats_after_finalize
                ),
                factorization_only=cfg.matrix_diagnostics_factorization_only,
            )
        else:
            if never_materialized_port:
                if (
                    assembly_time_system is None
                    or dtn_fine_action is None
                    or dtn_action_blocks is None
                ):
                    raise RuntimeError(
                        "action-only solver request lost its borrowed objects"
                    )
                external_snapshot = linear_solver_port(
                    Stage4NeverMaterializedLinearSolverRequest(
                        operator=solve_A,
                        b=solve_b,
                        n_fe=int(n_fe),
                        n_aux=int(n_aux),
                        static_condensed_system=assembly_time_system,
                        fine_operator=dtn_fine_action,
                        blocks=dtn_action_blocks,
                        function_space=V,
                        config=cfg,
                        floquet_data=floquet_data,
                    )
                )
                if not isinstance(
                    external_snapshot,
                    Stage4ExternalLinearSolverSnapshot,
                ):
                    raise TypeError(
                        "never-materialized linear-solver port must return "
                        "its snapshot type"
                    )
                if not external_snapshot.no_global_factor:
                    raise ValueError(
                        "never-materialized snapshot must certify no_global_factor"
                    )
                if external_snapshot.assembled_matrix_released_before_solve:
                    raise ValueError(
                        "never-materialized snapshot cannot release an assembled matrix"
                    )
                if (
                    external_snapshot.x.getSize() != solve_A.getSize()[0]
                    or external_snapshot.x.getOwnershipRange()
                    != solve_A.getOwnershipRange()
                ):
                    raise ValueError(
                        "never-materialized solver x must match action-only ownership"
                    )
            else:
                external_snapshot = _dispatch_external_linear_solver(
                    solve_A,
                    solve_b,
                    n_fe=n_fe,
                    n_aux=n_aux,
                    static_condensed_system=assembly_time_system,
                    function_space=V,
                    config=cfg,
                    floquet_data=floquet_data,
                    release_assembled_matrix=(
                        assembly_time_system.destroy
                        if assembly_time_system is not None
                        else None
                    ),
                    port=linear_solver_port,
                    mesh_data=mesh_data,
                    full_rhs=assembly_time_full_rhs,
                    incident_traction_quadrature_degree=(dtn_quadrature_degree
                        if diagnostic_reference_incident_quadrature else None),
                )
            solve_x = external_snapshot.x
            ksp = None
            ksp_telemetry = {}
    except DirectSolveFailure as exc:
        exc.timing_details.update(timing_details)
        exc.extra_summary.setdefault("solver_info", {})
        exc.extra_summary["solver_info"].update(
            {
                **assembly_backend_fields,
                "num_auxiliary_dofs": int(n_aux),
                **solved_dof_row_fields,
                "dtn_base_matrix_stats": base_matrix_stats,
                "dtn_augmented_matrix_stats_after_finalize": augmented_matrix_stats_after_finalize,
                "dtn_auxiliary_block_stats": dtn_auxiliary_block_stats,
                "dtn_trace_alias_preflight": trace_alias_preflight,
                "cell_static_condensation": (
                    None if condensed_system is None else condensed_system.build_audit
                ),
                "dtn_condensed_matrix_stats": condensed_matrix_stats,
                "dtn_floquet_independent_matrix_stats": (
                    independent_trace_matrix_stats
                ),
                "floquet_slave_elimination": (
                    None
                    if independent_trace_system is None
                    else independent_trace_system.build_audit
                ),
                "assembly_time_cell_static_condensation": (
                    None
                    if not assembly_time_active
                    else (
                        variable_p_reduction.build_audit
                        if variable_p_reduction is not None
                        else assembly_time_system.build_audit
                    )
                ),
            }
        )
        raise
    except CondensedPreflightExit as stop:
        # A reference observer deliberately does not return a solver snapshot.
        # Release owner-held objects before the outer worker writes its terminal.
        stop.release((solve_A, solve_b, assembly_time_full_rhs))
        raise
    setup_and_solve_seconds = float(
        comm.allreduce(time.perf_counter() - t0, op=MPI.MAX)
    )
    released_external = bool(
        external_snapshot is not None
        and external_snapshot.assembled_matrix_released_before_solve
    )
    if cfg.matrix_diagnostics_factorization_only:
        timing_details["stage4_dtn_factorization_seconds"] = setup_and_solve_seconds
        E_total = fem.Function(floquet_data.mpc.function_space, name="E_total")
        solver_info = {
            "solver_backend": "PETSc augmented auxiliary Fourier-DtN port with dolfinx_mpc Floquet constraints",
            "assemble_only": False,
            "factorization_only": True,
            **assembly_backend_fields,
            "num_auxiliary_dofs": int(n_aux),
            "num_fem_dofs_after_mpc": int(n_fe),
            "num_total_augmented_dofs": int(n_fe + n_aux),
            **solved_dof_row_fields,
            "stage4_dtn_assembly_seconds": float(
                comm.allreduce(time.perf_counter() - stage_start, op=MPI.MAX)
            ),
            "ksp_converged_reason": 0,
            "ksp_iterations": 0,
            "actual_ksp_type": ksp.getType(),
            "actual_pc_type": ksp.getPC().getType(),
            "actual_pc_factor_solver_type": None,
            "dtn_base_matrix_stats": base_matrix_stats,
            "dtn_augmented_matrix_stats_after_finalize": augmented_matrix_stats_after_finalize,
            "dtn_auxiliary_block_stats": dtn_auxiliary_block_stats,
            "dtn_trace_alias_preflight": trace_alias_preflight,
            "explicit_chac_constructed": False,
            "dtn_auxiliary_dense_block_constructed": False,
            **ksp_telemetry,
            **timing_details,
        }
        try:
            solver_info["actual_pc_factor_solver_type"] = (
                ksp.getPC().getFactorSolverType()
            )
        except Exception:
            solver_info["actual_pc_factor_solver_type"] = None
        return {
            "E_total": E_total,
            "A": A_aug,
            "b": b_aug,
            "x": solve_x,
            "ksp": ksp,
            "solver_info": solver_info,
            "port_metrics": {
                "R_total": None,
                "T_total": None,
                "R_plus_T": None,
                "A_balance": None,
                "diffraction_total_power_source": ("factorization_only_skipped_solve"),
                **_port_mode_count_metrics(modes),
            },
        }
    timing_details["stage4_dtn_linear_solve_seconds"] = setup_and_solve_seconds

    assembly_time_field = None
    embedded_fe_solution = None
    variable_p_recovered: VariablePRecoveredSolution | None = None
    if variable_p_reduction is not None:
        if assembly_time_full_rhs is None or variable_p_active_full_rhs is None:
            raise RuntimeError("variable-p recovery requires the active and p6 RHS")
        recovery_started = time.perf_counter()
        variable_p_recovered = variable_p_reduction.recover(
            solve_x,
            assembly_time_full_rhs,
            active_full_rhs_override=variable_p_active_full_rhs,
        )
        _recovery_cleanup_sink.append(variable_p_recovered)
        assembly_time_field = variable_p_recovered.field
        condensation_recovery = variable_p_recovered.audit
        x_aug = solve_x
        timing_details["stage4_dtn_cell_static_condensation_recovery_seconds"] = float(
            comm.allreduce(
                time.perf_counter() - recovery_started,
                op=MPI.MAX,
            )
        )
    elif assembly_time_system is not None:
        if assembly_time_full_rhs is None:
            raise RuntimeError("assembly-time recovery requires the full-space RHS")
        recovery_started = time.perf_counter()
        (
            assembly_time_field,
            embedded_fe_solution,
            condensation_recovery,
        ) = _assign_fe_solution_from_assembly_time_condensation(
            solve_x,
            assembly_time_system,
            floquet_data,
            assembly_time_full_rhs,
        )
        x_aug = solve_x
        timing_details["stage4_dtn_cell_static_condensation_recovery_seconds"] = float(
            comm.allreduce(
                time.perf_counter() - recovery_started,
                op=MPI.MAX,
            )
        )
    elif condensed_system is not None:
        recovery_started = time.perf_counter()
        expanded_trace_solution = (
            expand_floquet_independent_trace_solution(
                condensed_system.rhs,
                independent_trace_system,
                solve_x,
            )
            if independent_trace_system is not None
            else None
        )
        x_aug, condensation_recovery = recover_full_solution(
            A_aug,
            b_aug,
            condensed_system,
            (
                expanded_trace_solution
                if expanded_trace_solution is not None
                else solve_x
            ),
        )
        if expanded_trace_solution is not None:
            expanded_trace_solution.destroy()
        timing_details["stage4_dtn_cell_static_condensation_recovery_seconds"] = float(
            comm.allreduce(
                time.perf_counter() - recovery_started,
                op=MPI.MAX,
            )
        )
    else:
        x_aug = solve_x

    if variable_p_reduction is not None and variable_p_recovered is not None:
        residual_started = time.perf_counter()
        linear_residual = variable_p_reduction.full_active_residual(
            A_aug,
            b_aug,
            x_aug,
            variable_p_recovered,
        )
        if assembly_time_full_rhs is None:
            raise RuntimeError("variable-p full RHS lifecycle is invalid")
        assembly_time_full_rhs.destroy()
        assembly_time_full_rhs = None
        if variable_p_active_full_rhs is None:
            raise RuntimeError("variable-p active RHS lifecycle is invalid")
        variable_p_active_full_rhs.destroy()
        variable_p_active_full_rhs = None
        if variable_p_live_observer is None:
            variable_p_recovered.destroy()
            variable_p_recovered = None
        timing_details["stage4_dtn_matrix_free_full_residual_seconds"] = float(
            comm.allreduce(
                time.perf_counter() - residual_started,
                op=MPI.MAX,
            )
        )
    elif assembly_time_system is not None and embedded_fe_solution is not None:
        residual_started = time.perf_counter()
        linear_residual = _assembly_time_full_operator_residual(
            a,
            floquet_data,
            embedded_fe_solution,
            None if released_external else A_aug,
            b_aug,
            x_aug,
            assembly_time_system,
            assembly_time_full_rhs,
            reduced_residual_norm=(
                external_snapshot.reduced_residual_norm if released_external else None
            ),
        )
        embedded_fe_solution.destroy()
        embedded_fe_solution = None
        assembly_time_full_rhs.destroy()
        assembly_time_full_rhs = None
        timing_details["stage4_dtn_matrix_free_full_residual_seconds"] = float(
            comm.allreduce(
                time.perf_counter() - residual_started,
                op=MPI.MAX,
            )
        )
    else:
        linear_residual = _linear_residual(A_aug, b_aug, x_aug)
    external_rta_gate_pass = (
        None
        if external_snapshot is None
        else _external_snapshot_allows_official_rta(
            external_snapshot,
            linear_residual.get("linear_system_relative_residual"),
        )
    )
    _write_progress_event(
        out_dir,
        comm,
        stage="after_true_residual",
        status="end",
        started=started,
        dofs=int(V.dofmap.index_map.size_global * V.dofmap.index_map_bs),
        constraints=floquet_data.num_constraints,
        matrix_stats=augmented_matrix_stats_after_finalize,
        petsc_options=petsc_options,
        extra={
            "linear_system_relative_residual": linear_residual.get(
                "linear_system_relative_residual"
            )
        },
    )

    t0 = time.perf_counter()
    E_total = (
        assembly_time_field
        if assembly_time_field is not None
        else _assign_fe_solution_from_augmented(
            x_aug,
            floquet_data,
            n_aux,
        )
    )
    timing_details["stage4_dtn_solution_backsubstitution_seconds"] = float(
        comm.allreduce(time.perf_counter() - t0, op=MPI.MAX)
    )
    _write_progress_event(
        out_dir,
        comm,
        stage="after_fe_field_reconstruction",
        status="end",
        started=started,
        dofs=int(V.dofmap.index_map.size_global * V.dofmap.index_map_bs),
        constraints=floquet_data.num_constraints,
        petsc_options=petsc_options,
    )
    _write_progress_event(
        out_dir,
        comm,
        stage="after_augmented_matrix_finalize",
        status="end",
        started=started,
        dofs=int(V.dofmap.index_map.size_global * V.dofmap.index_map_bs),
        constraints=floquet_data.num_constraints,
        matrix_stats=augmented_matrix_stats_after_finalize,
        petsc_options=petsc_options,
    )
    aux_values = _gather_auxiliary_values(x_aug, n_fe, n_aux, comm)
    port_metrics = (
        {}
        if external_rta_gate_pass is False
        else _port_power_metrics(cfg, modes, aux_values, incident_projections)
    )
    if (
        cfg.dtn_auxiliary_direct_projection_audit
        and external_rta_gate_pass is not False
    ):
        _write_progress_event(
            out_dir,
            comm,
            stage="before_dtn_auxiliary_direct_projection_audit",
            status="start",
            started=started,
            dofs=int(V.dofmap.index_map.size_global * V.dofmap.index_map_bs),
            constraints=floquet_data.num_constraints,
            petsc_options=petsc_options,
        )
        projection_started = time.perf_counter()
        port_metrics["auxiliary_direct_tangential_projection_audit"] = (
            _auxiliary_direct_tangential_projection_audit(
                E_total,
                modes,
                aux_values,
                incident_projections,
                mesh_data,
                cfg,
                quadrature_degree=dtn_quadrature_degree,
            )
        )
        timing_details["stage4_dtn_auxiliary_direct_projection_audit_seconds"] = float(
            comm.allreduce(
                time.perf_counter() - projection_started,
                op=MPI.MAX,
            )
        )
        _write_progress_event(
            out_dir,
            comm,
            stage="after_dtn_auxiliary_direct_projection_audit",
            status="end",
            started=started,
            dofs=int(V.dofmap.index_map.size_global * V.dofmap.index_map_bs),
            constraints=floquet_data.num_constraints,
            petsc_options=petsc_options,
            extra={
                "maximum_absolute_outgoing_projection_difference": port_metrics[
                    "auxiliary_direct_tangential_projection_audit"
                ]["max_absolute_outgoing_projection_difference"],
            },
        )
    else:
        port_metrics["auxiliary_direct_tangential_projection_audit"] = {
            "requested": False,
            "status": "not_requested",
            "pass": None,
            "ordinary_default_changed": False,
        }
    port_metrics.update(timing_details)
    if external_rta_gate_pass is not False:
        _write_port_outputs(
            out_dir,
            cfg,
            modes,
            aux_values,
            incident_projections,
            port_metrics,
            comm,
        )
    _write_progress_event(
        out_dir,
        comm,
        stage=(
            "after_official_rta"
            if external_rta_gate_pass is not False
            else "external_rta_not_run"
        ),
        status="end",
        started=started,
        dofs=int(V.dofmap.index_map.size_global * V.dofmap.index_map_bs),
        constraints=floquet_data.num_constraints,
        petsc_options=petsc_options,
        extra={
            "R_total": port_metrics.get("R_total"),
            "T_total": port_metrics.get("T_total"),
        },
    )

    cell_static_condensation_audit = None
    if condensed_system is not None:
        cell_static_condensation_audit = {
            **condensed_system.build_audit,
            "condensed_matrix_stats": condensed_matrix_stats,
            "floquet_independent_matrix_stats": (independent_trace_matrix_stats),
            "floquet_slave_elimination": (
                None
                if independent_trace_system is None
                else independent_trace_system.build_audit
            ),
            "recovery": condensation_recovery,
            "full_explicit_true_residual": linear_residual,
            "same_full_operator_used_for_recovery_and_residual": True,
            "ordinary_default_changed": False,
        }
    elif variable_p_reduction is not None:
        trace_constraints = variable_p_reduction.system.trace_constraints
        if trace_constraints is None:
            raise RuntimeError("variable-p audit lost its physical trace constraints")
        cell_static_condensation_audit = {
            **variable_p_reduction.build_audit,
            "condensed_matrix_stats": (augmented_matrix_stats_after_finalize),
            "floquet_independent_matrix_stats": (augmented_matrix_stats_after_finalize),
            "floquet_slave_elimination": (dict(trace_constraints.audit)),
            "trace_constraint_elimination": (dict(trace_constraints.audit)),
            "recovery": condensation_recovery,
            "full_operator_true_residual": linear_residual,
            "full_explicit_true_residual": linear_residual,
            "true_residual_semantics": (
                "exact active variable-p C_t^H Schur C_t plus DtN "
                "operator and explicit eliminated active-interior residual"
            ),
            "same_full_operator_used_for_recovery_and_residual": True,
            "ordinary_default_changed": False,
        }
    elif assembly_time_system is not None:
        cell_static_condensation_audit = {
            **assembly_time_system.build_audit,
            "condensed_matrix_stats": (augmented_matrix_stats_after_finalize),
            "floquet_independent_matrix_stats": (augmented_matrix_stats_after_finalize),
            "floquet_slave_elimination": (
                assembly_time_system.trace_constraints.build_audit
            ),
            "recovery": condensation_recovery,
            "full_operator_true_residual": linear_residual,
            "full_explicit_true_residual": linear_residual,
            "true_residual_semantics": (
                "exact physically reduced C_t^H Schur C_t plus DtN "
                "operator residual; full FE matrix deliberately not allocated"
            ),
            "same_full_operator_used_for_recovery_and_residual": False,
            "action_only_setup": bool(never_materialized_port),
            "global_A_materialized": not never_materialized_port,
            "global_F_materialized": not never_materialized_port,
            "dtn_action_preallocation_audit": dtn_action_preallocation_audit,
            "ordinary_default_changed": False,
        }
    if external_snapshot is None:
        solver_converged_reason = int(ksp.getConvergedReason())
        solver_iterations = int(ksp.getIterationNumber())
        solver_residual_norm = float(ksp.getResidualNorm())
        solver_ksp_type = ksp.getType()
        solver_pc_type = ksp.getPC().getType()
    else:
        solver_converged_reason = int(external_snapshot.converged_reason)
        solver_iterations = int(external_snapshot.iterations)
        solver_residual_norm = None
        solver_ksp_type = external_snapshot.ksp_type
        solver_pc_type = external_snapshot.pc_type
    solver_info = {
        "solver_backend": (
            "external static-condensed linear-solver port"
            if external_snapshot is not None
            else "PETSc exact-sequence inactive-row-free variable-p assembly-time "
            "trace Schur + Floquet-independent auxiliary Fourier-DtN port"
            if variable_p_reduction is not None
            else "PETSc assembly-time exact cell-interior trace Schur + direct "
            "Floquet-independent insertion + auxiliary Fourier-DtN port"
            if assembly_time_active
            else "PETSc exact cell-interior trace Schur + auxiliary Fourier-DtN "
            "port with dolfinx_mpc Floquet constraints"
            if condensed_system is not None
            else "PETSc augmented auxiliary Fourier-DtN port with "
            "dolfinx_mpc Floquet constraints"
        ),
        **assembly_backend_fields,
        "num_auxiliary_dofs": int(n_aux),
        "num_original_fem_dofs": int(
            V.dofmap.index_map.size_global * V.dofmap.index_map_bs
        ),
        "num_fem_dofs_after_mpc": int(
            V.dofmap.index_map.size_global * V.dofmap.index_map_bs
        ),
        "num_active_trace_dofs": (None if not assembly_time_active else int(n_fe)),
        "num_total_augmented_dofs": int(n_fe + n_aux),
        "num_active_condensed_dofs": (
            int(n_fe + n_aux)
            if assembly_time_active
            else None
            if condensed_system is None
            else int(condensed_system.trace_rows)
        ),
        **solved_dof_row_fields,
        "stage4_cell_static_condensation": bool(
            condensed_system is not None or assembly_time_active
        ),
        "stage4_assembly_time_cell_static_condensation": bool(assembly_time_active),
        "stage4_variable_p_active": bool(variable_p_reduction is not None),
        "stage4_local_h_active": bool(
            variable_p_reduction is not None
            and variable_p_reduction.build_audit.get("local_h") is not None
        ),
        "stage4_local_h_constraint_audit": (
            None
            if variable_p_reduction is None
            else variable_p_reduction.build_audit.get("local_h")
        ),
        "num_actual_conforming_active_fe_dofs": (
            None
            if variable_p_reduction is None
            else _variable_p_active_fe_dofs(variable_p_reduction.build_audit)
        ),
        "num_raw_broken_active_fe_dofs": (
            None
            if variable_p_reduction is None
            else int(variable_p_reduction.build_audit["raw_broken_active_fe_dofs"])
        ),
        "stage4_floquet_slave_elimination": bool(
            independent_trace_system is not None or assembly_time_active
        ),
        "cell_static_condensation": cell_static_condensation_audit,
        "stage4_dtn_assembly_seconds": float(
            comm.allreduce(time.perf_counter() - stage_start, op=MPI.MAX)
        ),
        "ksp_converged_reason": solver_converged_reason,
        "ksp_iterations": solver_iterations,
        "primal_ksp_residual_norm": solver_residual_norm,
        "actual_ksp_type": solver_ksp_type,
        "actual_pc_type": solver_pc_type,
        "actual_pc_factor_solver_type": None,
        "variable_p_live_observer_requested": bool(
            variable_p_live_observer is not None
        ),
        "variable_p_live_observer_invoked": False,
        "dtn_base_matrix_stats": base_matrix_stats,
        "dtn_augmented_matrix_stats_after_finalize": augmented_matrix_stats_after_finalize,
        "dtn_condensed_matrix_stats": (
            augmented_matrix_stats_after_finalize
            if assembly_time_active
            else condensed_matrix_stats
        ),
        "dtn_floquet_independent_matrix_stats": (
            augmented_matrix_stats_after_finalize
            if assembly_time_active
            else independent_trace_matrix_stats
        ),
        "dtn_auxiliary_block_stats": dtn_auxiliary_block_stats,
        "action_only_setup": bool(never_materialized_port),
        "matrix_free_dtn_profile": bool(matrix_free_dtn),
        "global_A_materialized": not never_materialized_port,
        "global_F_materialized": not never_materialized_port,
        "dtn_action_preallocation_audit": dtn_action_preallocation_audit,
        "dtn_trace_alias_preflight": trace_alias_preflight,
        "explicit_chac_constructed": False,
        "dtn_auxiliary_dense_block_constructed": False,
        **ksp_telemetry,
        **timing_details,
        **linear_residual,
    }
    if external_snapshot is not None:
        solver_info.update(
            {
                "external_linear_solver_port": True,
                "external_rta_gate_pass": external_rta_gate_pass,
                "reported_relative_residual": (
                    external_snapshot.reported_relative_residual
                ),
                "condensed_true_residual": (external_snapshot.condensed_true_residual),
                "full_augmented_true_residual": (
                    external_snapshot.full_augmented_true_residual
                ),
                "residual_limit": external_snapshot.residual_limit,
                "no_global_factor": external_snapshot.no_global_factor,
                "solver_profile": external_snapshot.solver_profile,
                "assembled_matrix_released_before_solve": (
                    external_snapshot.assembled_matrix_released_before_solve
                ),
                "reduced_residual_norm": external_snapshot.reduced_residual_norm,
            }
        )
    if external_snapshot is None:
        try:
            solver_info["actual_pc_factor_solver_type"] = (
                ksp.getPC().getFactorSolverType()
            )
        except Exception:
            solver_info["actual_pc_factor_solver_type"] = None

    if condensed_system is not None:
        if independent_trace_system is not None:
            returned_A = independent_trace_system.matrix
            returned_b = independent_trace_system.rhs
            condensed_system.destroy()
        else:
            returned_A = condensed_system.matrix
            returned_b = condensed_system.rhs
        returned_x = solve_x
        A_aug.destroy()
        b_aug.destroy()
        x_aug.destroy()
    elif released_external:
        returned_A = None
        returned_b = b_aug
        returned_x = x_aug
    else:
        returned_A = A_aug
        returned_b = b_aug
        returned_x = x_aug

    goal_context = {
        "num_fem_dofs_after_mpc": int(n_fe),
        "modes": modes,
        "auxiliary_values": aux_values,
        "incident_projections": incident_projections,
        "normalization": "finite-port outgoing modal power / incident power",
    }
    if variable_p_live_observer is not None:
        live_view = None
        local_view_errors: list[dict[str, Any]] = []
        try:
            if variable_p_reduction is None or variable_p_recovered is None:
                raise RuntimeError(
                    "requested variable-p live observer lost its recovered state"
                )
            relative_residual = linear_residual.get("linear_system_relative_residual")
            callback_gate_pass = bool(
                solver_info["ksp_converged_reason"] > 0
                and relative_residual is not None
                and np.isfinite(float(relative_residual))
                and float(relative_residual) <= 1.0e-9
            )
            if not callback_gate_pass:
                raise RuntimeError(
                    "variable-p live observer requires a converged primal "
                    "solve and full active true residual <= 1e-9"
                )
            port_operator_audit = _variable_p_port_operator_audit(timing_details)
            if not port_operator_audit["pass"]:
                raise RuntimeError(
                    "variable-p live observer requires a qualified "
                    "trace-only DtN/port operator: "
                    f"{port_operator_audit}"
                )
            live_view = Stage4VariablePLiveView(
                field=E_total,
                mesh_data=mesh_data,
                config=cfg,
                floquet_data=floquet_data,
                A=returned_A,
                b=returned_b,
                x=returned_x,
                ksp=ksp,
                reduction=variable_p_reduction,
                recovered=variable_p_recovered,
                goal_context=_readonly_goal_context(goal_context),
                port_metrics=_deep_readonly_copy(port_metrics),
                port_operator_audit=_deep_readonly_copy(port_operator_audit),
                full_active_residual=_deep_readonly_copy(linear_residual),
                primal_solver_telemetry=_deep_readonly_copy(
                    {
                        "converged_reason": solver_info["ksp_converged_reason"],
                        "iterations": solver_info["ksp_iterations"],
                        "residual_norm": solver_info["primal_ksp_residual_norm"],
                        "ksp_type": solver_info["actual_ksp_type"],
                        "pc_type": solver_info["actual_pc_type"],
                        "pc_factor_solver_type": solver_info[
                            "actual_pc_factor_solver_type"
                        ],
                        **dict(linear_residual),
                    }
                ),
            )
        except Exception as exc:
            local_view_errors.append(
                {
                    "rank": int(comm.rank),
                    "phase": "live_view_preflight",
                    "exception_type": type(exc).__name__,
                    "message": str(exc),
                }
            )
        collective_view_errors = [
            error
            for rank_errors in comm.allgather(local_view_errors)
            for error in rank_errors
        ]
        local_schur_release: dict[str, Any] | None = None
        try:
            if collective_view_errors:
                raise Stage4VariablePLiveObserverError(
                    "variable-p live-view preflight failed collectively: "
                    + json.dumps(
                        collective_view_errors,
                        sort_keys=True,
                    )
                )
            if live_view is None:
                raise AssertionError("collective live-view preflight lost its view")
            _invoke_collective_variable_p_live_observer(
                variable_p_live_observer,
                live_view,
                comm,
            )
        except Exception as exc:
            try:
                _write_progress_event(
                    out_dir,
                    comm,
                    stage="variable_p_live_observer",
                    status="failed",
                    started=started,
                    dofs=int(V.dofmap.index_map.size_global * V.dofmap.index_map_bs),
                    constraints=floquet_data.num_constraints,
                    matrix_stats=(augmented_matrix_stats_after_finalize),
                    petsc_options=petsc_options,
                    extra={
                        "exception_type": type(exc).__name__,
                        "message": str(exc),
                        "official_port_outputs_written_before_failure": True,
                        "completed_summary_written": False,
                    },
                )
            except Exception:
                # Preserve the collective observer failure if a best-effort
                # progress marker cannot be written.
                pass
            for petsc_object in (
                ksp,
                returned_x,
                returned_b,
                returned_A,
            ):
                try:
                    petsc_object.destroy()
                except Exception:
                    pass
            raise
        finally:
            live_view = None
            local_schur_release = variable_p_reduction.release_retained_local_schur()
        variable_p_recovered = None
        solver_info["variable_p_live_observer_invoked"] = True
        solver_info["variable_p_local_schur_release"] = local_schur_release

    result = {
        "E_total": E_total,
        "A": returned_A,
        "b": returned_b,
        "x": returned_x,
        "ksp": ksp,
        "solver_info": solver_info,
        "port_metrics": port_metrics,
        "goal_context": goal_context,
    }
    if canonical_vector_export:
        if assembly_time_system is None:
            raise RuntimeError("canonical vector export lost its assembly-time system")
        result["canonical_vector_context"] = {
            "assembly_time_system": assembly_time_system,
        }
    return result


def solve_stage4_dtn_port_total_field(
    *,
    a,
    L,
    V,
    mesh_data,
    cfg: SimulationConfig3D,
    floquet_data: DoubleFloquet3DData,
    petsc_options: dict[str, Any],
    out_dir: Path,
    log,
    started: float | None = None,
    linear_solver_port=None,
    diagnostic_reference_incident_quadrature: bool = False,
    variable_p_live_observer: (Callable[[Stage4VariablePLiveView], None] | None) = None,
    variable_p_retain_local_schur_for_research: bool = False,
    static_retain_local_schur_for_matrix_free: bool = False,
    matrix_free_dtn: bool = False,
    matrix_free_dtn_probe: bool = False,
    canonical_vector_export: bool = False,
) -> dict[str, Any]:
    """Run the DtN solver with exception-safe recovered-vector ownership."""

    comm = (
        mesh_data.mesh.comm
        if mesh_data is not None
        else V.mesh.comm
        if V is not None
        else MPI.COMM_WORLD
    )
    observer_flags = comm.allgather(
        (
            variable_p_live_observer is not None,
            bool(variable_p_retain_local_schur_for_research),
            bool(static_retain_local_schur_for_matrix_free),
            bool(matrix_free_dtn),
            bool(matrix_free_dtn_probe),
            bool(canonical_vector_export),
            bool(diagnostic_reference_incident_quadrature),
        )
    )
    if len(set(observer_flags)) != 1:
        raise ValueError(
            "the variable-p live observer must be enabled on every MPI rank "
            "and research flags must match"
        )
    recovered_cleanup: list[VariablePRecoveredSolution] = []
    implementation_failed = False
    try:
        return _solve_stage4_dtn_port_total_field_impl(
            a=a,
            L=L,
            V=V,
            mesh_data=mesh_data,
            cfg=cfg,
            floquet_data=floquet_data,
            petsc_options=petsc_options,
            out_dir=out_dir,
            log=log,
            started=started,
            linear_solver_port=linear_solver_port,
            diagnostic_reference_incident_quadrature=diagnostic_reference_incident_quadrature,
            variable_p_live_observer=variable_p_live_observer,
            variable_p_retain_local_schur_for_research=(
                variable_p_retain_local_schur_for_research
            ),
            static_retain_local_schur_for_matrix_free=(
                static_retain_local_schur_for_matrix_free
            ),
            matrix_free_dtn=matrix_free_dtn,
            matrix_free_dtn_probe=matrix_free_dtn_probe,
            canonical_vector_export=canonical_vector_export,
            _recovery_cleanup_sink=recovered_cleanup,
        )
    except BaseException:
        implementation_failed = True
        raise
    finally:
        cleanup_errors: list[str] = []
        for recovered in reversed(recovered_cleanup):
            try:
                recovered.destroy()
            except Exception as exc:
                cleanup_errors.append(f"{type(exc).__name__}: {exc}")
        if cleanup_errors and not implementation_failed:
            raise RuntimeError(
                "variable-p recovered-state final cleanup failed: "
                + "; ".join(cleanup_errors)
            )
