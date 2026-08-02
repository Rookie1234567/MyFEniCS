from __future__ import annotations

import copy
import csv
from dataclasses import dataclass
import hashlib
import json
import time
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence

import numpy as np
import ufl
from mpi4py import MPI
from petsc4py import PETSc

import dolfinx_mpc
from dolfinx import fem
from dolfinx.fem import petsc as fem_petsc
from dolfinx.la.petsc import _ghost_update, create_vector

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
from .hcurl_cell_static_condensation import (
    build_explicit_cell_static_condensation,
    build_floquet_independent_trace_system,
    expand_floquet_independent_trace_solution,
    owned_hcurl_cell_interior_dofs,
    recover_full_solution,
)
from .hcurl_assembly_time_condensation import (
    AssemblyTimeCondensedSystem,
    build_unconstrained_assembly_time_condensation,
    cell_interior_schur_bilinear,
    condense_unconstrained_vector_to_active_trace,
    recover_owned_cell_interiors,
)
from .hcurl_variable_p_reduction import (
    VariablePAssemblyTimeReduction,
    VariablePRecoveredSolution,
    build_variable_p_assembly_time_reduction,
)
from .mpc_form_action import MpcFormActionContext
from .solve_vector_maxwell import _json_default


DTN_PORT_MODAL_POWER_SOURCE = "dtn_port_modal_amplitudes"
DTN_PORT_MODAL_REFERENCE = (
    "top=physical_z_max; bottom=physical_z_min; bottom lossy power uses boundary-plane phase attenuation"
)


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
            {
                key: _deep_readonly_copy(item)
                for key, item in value.items()
            }
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
    digest.update(
        np.asarray(array.shape, dtype=np.dtype("<i8")).tobytes()
    )
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
    if [int(row["rank"]) for row in rank_hashes] != list(
        range(communicator.size)
    ):
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
    removed_max = timing_details.get(
        "stage4_dtn_variable_p_removed_interior_max_abs"
    )
    removed_over_threshold_max = timing_details.get(
        "stage4_dtn_variable_p_removed_interior_over_threshold_max"
    )
    acceptance_threshold_max = timing_details.get(
        "stage4_dtn_variable_p_acceptance_threshold_max_abs"
    )
    trace_only = (
        timing_details.get(
            "stage4_dtn_variable_p_trace_only_gate_pass"
        )
        is True
    )
    auxiliary_columns = timing_details.get(
        "stage4_dtn_variable_p_auxiliary_interior_columns_allocated"
    )
    operator_sha256 = timing_details.get(
        "stage4_dtn_trace_only_external_operator_sha256"
    )
    rhs_sha256 = timing_details.get(
        "stage4_dtn_trace_only_external_rhs_sha256"
    )
    base_rhs_norm = timing_details.get(
        "stage4_dtn_trace_only_base_reduced_rhs_norm"
    )
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
        "external_operator_content_hash": valid_sha256(
            operator_sha256
        ),
        "external_rhs_content_hash": valid_sha256(rhs_sha256),
        "zero_volume_base_rhs": (
            isinstance(base_rhs_norm, (int, float))
            and np.isfinite(float(base_rhs_norm))
            and 0.0 <= float(base_rhs_norm) <= 5.0e-13
        ),
    }
    return {
        "schema_version": (
            "task035d.variable-p-trace-only-port-operator.v1"
        ),
        "pass": all(checks.values()),
        "checks": checks,
        "trace_functional_count": functional_count,
        "removed_active_interior_max_abs": removed_max,
        "removed_active_interior_over_threshold_max": (
            removed_over_threshold_max
        ),
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
                collective_preflight_errors
                + collective_cleanup_errors,
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
        observed_ksp_configuration = _ksp_configuration_signature(
            view.ksp
        )
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
            "left the callback: "
            + json.dumps(observer_errors, sort_keys=True)
        )


def _assembly_backend_summary_fields(
    audit: dict[str, object],
    qualification: dict[str, object],
) -> dict[str, object]:
    """Return the stable requested/actual backend provenance fields."""

    return {
        "stage4_full3d_assembly_backend_requested": audit["requested"],
        "stage4_full3d_assembly_backend_actual": audit["actual"],
        "stage4_full3d_assembly_backend_selection_source": audit[
            "selection_source"
        ],
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
        "matrix_column_ownership_range": list(
            map(int, column_ownership)
        ),
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
        None
        if independent_trace_rows is None
        else int(independent_trace_rows)
    )
    augmented = int(augmented_rows)
    auxiliary = int(auxiliary_rows)
    if min(active, storage, augmented, auxiliary) < 0:
        raise ValueError("DoF and row counts must be nonnegative.")
    if active > storage:
        raise ValueError(
            "Active exact-sequence FE DoFs exceed the storage carrier."
        )
    if independent is not None:
        if independent < 0 or independent > active:
            raise ValueError(
                "Independent trace rows must not exceed active FE DoFs."
            )
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
                "physical conforming exact-sequence FE space before static "
                "condensation"
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


def _as_ufl_vector(values: np.ndarray, phase):
    return ufl.as_vector(tuple(PETSc.ScalarType(value) * phase for value in values))


def _surface_vector_form(V, mesh_data, tag: int, vector: np.ndarray, phase):
    v = ufl.TestFunction(V)
    ds = ufl.Measure("ds", domain=mesh_data.mesh, subdomain_data=mesh_data.facet_tags)
    return ufl.inner(_as_ufl_vector(vector, phase), v) * ds(tag)


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


def _assemble_mpc_vector(linear_form, mpc, *, quadrature_degree: int | None = None) -> PETSc.Vec:
    form_options: dict[str, int] = {}
    if quadrature_degree is not None:
        form_options["quadrature_degree"] = int(quadrature_degree)
    return _assemble_mpc_form_vector(fem.form(linear_form, form_compiler_options=form_options), mpc)


def _assemble_unconstrained_vector(
    linear_form,
    *,
    quadrature_degree: int | None = None,
) -> PETSc.Vec:
    form_options: dict[str, int] = {}
    if quadrature_degree is not None:
        form_options["quadrature_degree"] = int(quadrature_degree)
    return _assemble_unconstrained_form_vector(
        fem.form(
            linear_form,
            form_compiler_options=form_options,
        )
    )


def _vec_nonzero_owned_entries(
    vec: PETSc.Vec,
    *,
    relative_tol: float = 1.0e-13,
) -> tuple[np.ndarray, np.ndarray]:
    """Return owned significant entries using one collective cutoff."""

    start, end = vec.getOwnershipRange()
    values = np.asarray(vec.getArray(readonly=True), dtype=np.complex128)
    local_maximum = float(np.max(np.abs(values), initial=0.0))
    global_maximum = float(
        vec.getComm().tompi4py().allreduce(
            local_maximum,
            op=MPI.MAX,
        )
    )
    cutoff = max(1.0e-30, relative_tol * global_maximum)
    nz = np.flatnonzero(np.abs(values) > cutoff)
    return (_idx(np.arange(start, end, dtype=np.int64)[nz]), values[nz].copy())


def _combine_owned_entries(
    component_entries: tuple[tuple[np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray]],
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
    local_maximum = float(
        np.max(np.abs(summed_values), initial=0.0)
    )
    global_maximum = float(
        comm.allreduce(local_maximum, op=MPI.MAX)
    )
    cutoff = max(1.0e-30, relative_tol * global_maximum)
    keep = np.abs(summed_values) > cutoff
    return _idx(unique_rows[keep]), summed_values[keep].copy()


def _active_trace_values_from_augmented(
    x_aug: PETSc.Vec,
    condensed: AssemblyTimeCondensedSystem,
) -> np.ndarray:
    """Collect the small independent trace vector on every rank."""

    comm = condensed.matrix.getComm().tompi4py()
    local_active = len(
        condensed.trace_constraints.owned_active_original_dofs
    )
    local_values = np.asarray(
        x_aug.getArray(readonly=True)[:local_active],
        dtype=np.complex128,
    ).copy()
    packets = comm.allgather(local_values)
    active = (
        np.concatenate(packets)
        if packets
        else np.empty(0, dtype=np.complex128)
    )
    if active.shape != (condensed.active_rows,):
        raise RuntimeError(
            "distributed active trace solution does not close globally"
        )
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
    owned_active = (
        condensed.trace_constraints.owned_active_original_dofs
    )
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
    return E_total, x_fe, {
        "schema_version": (
            "task035b.assembly-time-cell-condensation-recovery.v1"
        ),
        "status": "full_field_recovered_without_full_global_matrix",
        "recovered_interior_rows": int(
            comm.allreduce(local_recovered, op=MPI.SUM)
        ),
        "full_global_matrix_allocated": False,
        "full_trace_matrix_allocated": False,
        "total_recovery_seconds": float(
            comm.allreduce(
                time.perf_counter() - recovery_started,
                op=MPI.MAX,
            )
        ),
    }


def _assembly_time_full_operator_residual(
    bilinear_form,
    floquet_data: DoubleFloquet3DData,
    embedded_fe_solution: PETSc.Vec,
    reduced_matrix: PETSc.Mat,
    reduced_rhs: PETSc.Vec,
    reduced_solution: PETSc.Vec,
    condensed: AssemblyTimeCondensedSystem,
    full_rhs: PETSc.Vec,
) -> dict[str, Any]:
    """Audit all eliminated FE equations without allocating the full matrix."""

    reduced = _linear_residual(
        reduced_matrix,
        reduced_rhs,
        reduced_solution,
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
                condensed.interior_residual_projection_by_class[
                    cell.class_key
                ]
                @ values
            )
            local_interior_sq += float(np.vdot(values, values).real)
            local_interior_max = max(
                local_interior_max,
                float(np.max(np.abs(values), initial=0.0)),
            )
        comm = reduced_matrix.getComm().tompi4py()
        interior_norm = float(
            np.sqrt(comm.allreduce(local_interior_sq, op=MPI.SUM))
        )
        interior_max = float(
            comm.allreduce(local_interior_max, op=MPI.MAX)
        )
        reduced_norm = float(
            reduced["linear_system_residual_norm"] or 0.0
        )
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
            np.sqrt(
                full_rhs.norm() ** 2
                + comm.allreduce(local_aux_rhs_sq, op=MPI.SUM)
            )
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
        auxiliary_norm_sq = float(
            comm.allreduce(local_aux_sq, op=MPI.SUM)
        )
        full_solution_norm = float(
            np.sqrt(
                embedded_fe_solution.norm() ** 2
                + auxiliary_norm_sq
            )
        )
        return {
            "linear_system_rhs_norm": rhs_norm,
            "linear_system_solution_norm": full_solution_norm,
            "linear_system_residual_norm": full_norm,
            "linear_system_relative_residual": (
                full_norm / max(rhs_norm, 1.0e-30)
            ),
            "reduced_trace_dtn_residual_norm": reduced_norm,
            "eliminated_cell_interior_residual_norm": interior_norm,
            "eliminated_cell_interior_max_abs_residual": interior_max,
            "full_operator_residual_method": (
                "explicit reduced trace+DtN Mat action combined with "
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
    ):
        if component not in {0, 1}:
            raise ValueError("Stage-4 DtN port component assembly only supports x/y tangential components.")
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
        ds = ufl.Measure("ds", domain=mesh_data.mesh, subdomain_data=mesh_data.facet_tags)
        form_options: dict[str, int] = {}
        if quadrature_degree is not None:
            form_options["quadrature_degree"] = int(quadrature_degree)
        self.form = fem.form(
            ufl.inner(ufl.as_vector(tuple(vector)), v) * ds(tag),
            form_compiler_options=form_options,
        )

    def assemble_entries(self, mode: PortMode3D, mpc) -> tuple[np.ndarray, np.ndarray]:
        _set_scalar_constant(self.alpha, mode.alpha)
        _set_scalar_constant(self.gamma, mode.gamma)
        _set_scalar_constant(self.kz, mode.k_vector[2])
        vec = _assemble_mpc_form_vector(self.form, mpc)
        try:
            return _vec_nonzero_owned_entries(vec)
        finally:
            vec.destroy()

    def assemble_unconstrained_vector(self, mode: PortMode3D) -> PETSc.Vec:
        _set_scalar_constant(self.alpha, mode.alpha)
        _set_scalar_constant(self.gamma, mode.gamma)
        _set_scalar_constant(self.kz, mode.k_vector[2])
        return _assemble_unconstrained_form_vector(self.form)


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
    surface_assemblers: Mapping[
        tuple[str, int], _ReusableSurfaceComponentAssembler
    ],
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
        index for index, (mode, _rows, _values) in enumerate(traces)
        if int(mode.n) == 0
    ]
    alias_indices = [
        index for index, (mode, _rows, _values) in enumerate(traces)
        if int(mode.n) != 0
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
                abs(cross)
                / max(np.sqrt(target_norm_sq * alias_norm_sq), 1.0e-30)
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
        "dtn_auxiliary_average_coupling_nnz_per_mode": float(coupling_nnz / max(n_aux, 1)),
        "dtn_auxiliary_dense_block_equivalent_nnz": int(n_aux * max(n_fe, 1) * 2 + n_aux),
    }


def _augmented_vec_from_base(b_base: PETSc.Vec, n_aux: int, comm: MPI.Intracomm) -> PETSc.Vec:
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


def _mode_power_at_boundary(mode: PortMode3D, cfg: SimulationConfig3D, amplitude: complex) -> float:
    e_at_boundary = complex(amplitude) * _mode_boundary_phase(mode, cfg) * mode.e_vector
    return mode_power(mode.k_vector, e_at_boundary, cfg, _outward_normal(mode.side))


def _mode_carries_outward_power(mode: PortMode3D) -> bool:
    """Return whether the selected mode carries positive real power at its finite port."""

    return bool(mode.power_per_unit_amplitude > 0.0)


def _traction_vector(mode: PortMode3D, cfg: SimulationConfig3D) -> np.ndarray:
    del cfg
    curl_vector = 1j * np.cross(mode.k_vector, mode.e_vector)
    return np.cross(curl_vector, _outward_normal(mode.side))


def _incident_projection_onto_top_mode(mode: PortMode3D, cfg: SimulationConfig3D) -> complex:
    if mode.side != "top" or mode.m != 0 or mode.n != 0:
        return 0.0 + 0.0j
    denominator = _mode_projection_denominator(mode, cfg)
    incident_e = complex(cfg.incident_amplitude) * np.asarray(cfg.polarization_vector, dtype=np.complex128)
    tangential_overlap = np.vdot(mode.e_vector[:2], incident_e[:2])
    phase = np.exp(1j * (cfg.kz - mode.k_vector[2]) * cfg.physical_z_max)
    area = (cfg.x_max - cfg.x_min) * (cfg.y_max - cfg.y_min)
    return complex(area * tangential_overlap * phase / denominator)


def _incident_top_traction_form(V, mesh_data, cfg: SimulationConfig3D):
    x = ufl.SpatialCoordinate(mesh_data.mesh)
    k_inc = np.asarray(cfg.wavevector, dtype=np.complex128)
    e_inc = complex(cfg.incident_amplitude) * np.asarray(cfg.polarization_vector, dtype=np.complex128)
    traction = np.cross(1j * np.cross(k_inc, e_inc), np.asarray((0.0, 0.0, 1.0), dtype=np.float64))
    phase = ufl.exp(
        PETSc.ScalarType(1j * k_inc[0]) * x[0]
        + PETSc.ScalarType(1j * k_inc[1]) * x[1]
        + PETSc.ScalarType(1j * k_inc[2]) * x[2]
    )
    return _surface_vector_form(V, mesh_data, cfg.tags.z_max, traction, phase)


def _dtn_surface_quadrature_degree(cfg: SimulationConfig3D, modes: list[PortMode3D]) -> int:
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
        abs(complex(cfg.kx)) <= 1.0e-12 * transverse_scale and abs(complex(cfg.ky)) <= 1.0e-12 * transverse_scale
    )
    return cfg.stage4_dtn_order_policy.lower() == "zero_order" and normal_incidence


def _mode_projections_from_solution(
    E_total,
    modes: Sequence[PortMode3D],
    mesh_data,
    cfg: SimulationConfig3D,
    *,
    quadrature_degree: int | None,
) -> list[complex]:
    """Project modes while compiling at most one form for each port side.

    The projection contract is tangential: only ``(E_x, E_y, 0)`` and
    ``(e_x, e_y, 0)`` enter the numerator, so a P-mode normal component never
    contributes to this DtN row.
    """

    modes = list(modes)
    if not modes:
        return []
    grouped: dict[str, list[tuple[int, PortMode3D]]] = {"top": [], "bottom": []}
    for index, mode in enumerate(modes):
        grouped[mode.side].append((index, mode))
    results: list[complex | None] = [None] * len(modes)
    x = ufl.SpatialCoordinate(mesh_data.mesh)
    tangential_field = ufl.as_vector(
        (E_total[0], E_total[1], PETSc.ScalarType(0.0))
    )
    form_options: dict[str, int] = {}
    if quadrature_degree is not None:
        form_options["quadrature_degree"] = int(quadrature_degree)
    for side, side_modes in grouped.items():
        if not side_modes:
            continue
        tag = cfg.tags.z_max if side == "top" else cfg.tags.z_min
        alpha = fem.Constant(mesh_data.mesh, PETSc.ScalarType(0.0))
        gamma = fem.Constant(mesh_data.mesh, PETSc.ScalarType(0.0))
        kz = fem.Constant(mesh_data.mesh, PETSc.ScalarType(0.0))
        mode_x = fem.Constant(mesh_data.mesh, PETSc.ScalarType(0.0))
        mode_y = fem.Constant(mesh_data.mesh, PETSc.ScalarType(0.0))
        phase = ufl.exp(
            PETSc.ScalarType(1j) * alpha * x[0]
            + PETSc.ScalarType(1j) * gamma * x[1]
            + PETSc.ScalarType(1j) * kz * x[2]
        )
        reference = ufl.as_vector(
            (mode_x * phase, mode_y * phase, PETSc.ScalarType(0.0))
        )
        ds = ufl.Measure(
            "ds", domain=mesh_data.mesh, subdomain_data=mesh_data.facet_tags
        )
        form = fem.form(
            ufl.inner(tangential_field, reference) * ds(tag),
            form_compiler_options=form_options,
        )
        for index, mode in side_modes:
            _set_scalar_constant(alpha, mode.alpha)
            _set_scalar_constant(gamma, mode.gamma)
            _set_scalar_constant(kz, mode.k_vector[2])
            _set_scalar_constant(mode_x, mode.e_vector[0])
            _set_scalar_constant(mode_y, mode.e_vector[1])
            local = fem.assemble_scalar(form)
            total = mesh_data.mesh.comm.allreduce(local, op=MPI.SUM)
            results[index] = complex(
                total / _mode_projection_denominator(mode, cfg)
            )
    return [complex(value) for value in results]


def _sampled_tangential_projection(
    electric_samples: np.ndarray,
    mode_samples: np.ndarray,
    weights: np.ndarray | None = None,
) -> complex:
    """Return the sampled form of the tangential DtN projection contract."""

    electric = np.asarray(electric_samples, dtype=np.complex128)
    mode = np.asarray(mode_samples, dtype=np.complex128)
    if (
        electric.shape != mode.shape
        or electric.ndim != 2
        or electric.shape[1] != 3
    ):
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
    numerator = np.sum(
        measure
        * np.sum(electric[:, :2] * np.conj(mode[:, :2]), axis=1)
    )
    denominator = float(
        np.sum(measure * np.sum(np.abs(mode[:, :2]) ** 2, axis=1))
    )
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
    direct_values = _mode_projections_from_solution(
        E_total,
        modes,
        mesh_data,
        cfg,
        quadrature_degree=quadrature_degree,
    )
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
            complex(auxiliary),
            complex(incident),
            mode.side,
        )
        direct_outgoing = _outgoing_projection(
            complex(direct),
            complex(incident),
            mode.side,
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
        (
            float(row["absolute_outgoing_projection_difference"])
            for row in rows
        ),
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
    form_options: dict[str, int] = {}
    if quadrature_degree is not None:
        form_options["quadrature_degree"] = int(quadrature_degree)
    local = fem.assemble_scalar(fem.form(expression * ds(tag), form_compiler_options=form_options))
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
        energy = _surface_scalar(ufl.inner(e_t, e_t), mesh_data, tag, quadrature_degree=quadrature_degree)
        diagnostics[f"stage4_dtn_{side}_facet_count_owned_global"] = owned_count
        diagnostics[f"stage4_dtn_{side}_surface_area_nm2"] = float(np.real(area))
        diagnostics[f"stage4_dtn_{side}_Et_l2_integral"] = float(np.real(energy))
        diagnostics[f"stage4_dtn_{side}_Et_l2_mean"] = float(np.real(energy) / max(float(np.real(area)), 1.0e-30))
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
    q_bottom_u_t = ufl.as_vector((q_bottom * u[0], q_bottom * u[1], PETSc.ScalarType(0.0)))
    a_local = a + ufl.inner(q_top_u_t, v_t) * ds(cfg.tags.z_max) + ufl.inner(q_bottom_u_t, v_t) * ds(cfg.tags.z_min)

    k_inc = np.asarray(cfg.wavevector, dtype=np.complex128)
    incident_e = complex(cfg.incident_amplitude) * np.asarray(cfg.polarization_vector, dtype=np.complex128)
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
        raise RuntimeError(f"zero_order local DtN expects exactly four modes: top/bottom x/y. Got {len(modes)} modes.")
    dtn_quadrature_degree = _dtn_surface_quadrature_degree(cfg, modes)
    timing_details["stage4_dtn_surface_quadrature_degree"] = int(dtn_quadrature_degree)
    if log is not None:
        log("Stage-4 DtN using zero-order local Robin sanity branch")
        log(f"Stage-4 DtN surface quadrature degree = {dtn_quadrature_degree}")

    t0 = time.perf_counter()
    a_local, L_local = _zero_order_local_robin_forms(a, L, V, mesh_data, cfg)
    E_total = fem.Function(floquet_data.mpc.function_space, name="E_total")
    if cfg.matrix_diagnostics_assemble_only:
        A_diag = dolfinx_mpc.assemble_matrix(fem.form(a_local), floquet_data.mpc, bcs=[])
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
            "stage4_dtn_assembly_seconds": float(comm.allreduce(time.perf_counter() - stage_start, op=MPI.MAX)),
            "ksp_converged_reason": 0,
            "ksp_iterations": 0,
            "actual_ksp_type": ksp.getType(),
            "actual_pc_type": ksp.getPC().getType(),
            "actual_pc_factor_solver_type": None,
            **timing_details,
        }
        try:
            solver_info["actual_pc_factor_solver_type"] = ksp.getPC().getFactorSolverType()
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
        _mode_projections_from_solution(
            E_total,
            modes,
            mesh_data,
            cfg,
            quadrature_degree=dtn_quadrature_degree,
        ),
        dtype=np.complex128,
    )
    incident_projections = [_incident_projection_onto_top_mode(mode, cfg) for mode in modes]
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
    port_metrics["stage4_dtn_zero_order_modal_values"] = [complex(value) for value in modal_values]
    port_metrics["stage4_dtn_zero_order_incident_projections"] = [complex(value) for value in incident_projections]
    port_metrics.update(timing_details)
    port_metrics["dtn_port_power_metric_note"] = (
        "Stage-4 zero_order dtn_port R/T is computed from direct boundary projections "
        "after solving the local Robin/DtN total-field problem."
    )
    _write_port_outputs(out_dir, cfg, modes, modal_values, incident_projections, port_metrics, comm)

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
        "stage4_dtn_assembly_seconds": float(comm.allreduce(time.perf_counter() - stage_start, op=MPI.MAX)),
        "ksp_converged_reason": int(problem.solver.getConvergedReason()),
        "ksp_iterations": int(problem.solver.getIterationNumber()),
        "actual_ksp_type": problem.solver.getType(),
        "actual_pc_type": problem.solver.getPC().getType(),
        "actual_pc_factor_solver_type": None,
        **timing_details,
        **_linear_residual(problem.A, problem.b, problem.x),
    }
    try:
        solver_info["actual_pc_factor_solver_type"] = problem.solver.getPC().getFactorSolverType()
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
            extra={"stage_semantics": "external sampler labels samples while KSPSetUp is running"},
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
    setup_seconds = float(progress_comm.allreduce(time.perf_counter() - setup_started, op=MPI.MAX))
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
            extra={"stage_semantics": "external sampler labels samples while KSPSolve is running"},
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
    solve_seconds = float(progress_comm.allreduce(time.perf_counter() - solve_started, op=MPI.MAX))
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


def _gather_auxiliary_values(x_aug: PETSc.Vec, n_fe: int, n_aux: int, comm: MPI.Intracomm) -> np.ndarray:
    values = np.zeros(n_aux, dtype=np.complex128)
    owner_rank = comm.size - 1
    if comm.rank == owner_rank and n_aux:
        values[:] = x_aug.getValues(_idx(np.arange(n_fe, n_fe + n_aux, dtype=np.int64)))
    values = comm.bcast(values, root=owner_rank)
    return np.asarray(values, dtype=np.complex128)


def _linear_residual(A: PETSc.Mat, b: PETSc.Vec, x: PETSc.Vec) -> dict[str, float | None]:
    residual = None
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
    finally:
        if residual is not None:
            residual.destroy()


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
    for idx, (mode, aux_value, inc_proj) in enumerate(zip(modes, aux_values, incident_projections)):
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
                "outgoing_amplitude_at_boundary": outgoing_amplitude * _mode_boundary_phase(mode, cfg),
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
        "R_plus_T_plus_A_volume_dtn_port_modal": metrics.get("R_plus_T_plus_A_volume_dtn_port_modal"),
        "energy_closure_error_dtn_port_modal_volume": metrics.get("energy_closure_error_dtn_port_modal_volume"),
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
        {key: _complex_text(value) if isinstance(value, complex) else value for key, value in row.items()}
        for row in rows
    ]
    with (out_dir / "dtn_port_diffraction_orders_3d.csv").open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=list(csv_rows[0].keys()) if csv_rows else ["side", "m", "n"])
        writer.writeheader()
        writer.writerows(csv_rows)
    with (out_dir / "port_power.csv").open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=list(csv_rows[0].keys()) if csv_rows else ["side", "m", "n"])
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
                R00_by_polarization[mode.polarization] = (
                    R00_by_polarization.get(mode.polarization, 0.0)
                    + float(power)
                )
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
        "dtn_port_propagating_mode_count": int(sum(1 for mode in modes if mode.propagating)),
        "dtn_port_rayleigh_warning_count": int(sum(1 for mode in modes if mode.rayleigh_warning)),
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
        "dtn_port_propagating_mode_count": int(sum(1 for mode in modes if mode.propagating)),
        "dtn_port_rayleigh_warning_count": int(sum(1 for mode in modes if mode.rayleigh_warning)),
    }


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
    variable_p_live_observer: (
        Callable[[Stage4VariablePLiveView], None] | None
    ) = None,
    variable_p_retain_local_schur_for_research: bool = False,
    _recovery_cleanup_sink: list[VariablePRecoveredSolution],
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
    assembly_backend_qualification = (
        qualify_stage4_full3d_assembly_backend(
            cfg,
            assembly_backend_audit,
        )
    )
    assembly_backend_fields = _assembly_backend_summary_fields(
        assembly_backend_audit,
        assembly_backend_qualification,
    )
    internal_backend_state = assembly_backend_audit[
        "legacy_internal_state"
    ]
    if not isinstance(internal_backend_state, dict):
        raise TypeError(
            "assembly backend audit must contain a mapping of internal state"
        )
    cell_static_condensation = bool(
        internal_backend_state["stage4_cell_static_condensation"]
    )
    assembly_time_cell_static_condensation = bool(
        internal_backend_state[
            "stage4_assembly_time_cell_static_condensation"
        ]
    )
    floquet_slave_elimination = bool(
        internal_backend_state["stage4_floquet_slave_elimination"]
    )
    variable_p_backend = (
        assembly_backend_audit["actual"]
        == ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND
    )
    if variable_p_live_observer is not None and not variable_p_backend:
        raise ValueError(
            "the variable-p live observer requires the exact-sequence "
            "assembly-time variable-p backend"
        )
    if variable_p_live_observer is not None and (
        cfg.matrix_diagnostics_assemble_only
        or cfg.matrix_diagnostics_factorization_only
    ):
        raise ValueError(
            "the variable-p live observer requires a complete solve"
        )
    if (
        variable_p_retain_local_schur_for_research
        and variable_p_live_observer is None
    ):
        raise ValueError(
            "research Schur retention requires a variable-p live observer"
        )
    log(
        "Stage-4 Full3D assembly backend "
        f"requested={assembly_backend_audit['requested']} "
        f"actual={assembly_backend_audit['actual']} "
        f"selection_source={assembly_backend_audit['selection_source']} "
        f"qualification={assembly_backend_qualification['status']}"
    )

    if cfg.stage4_dtn_assembly.lower() != "auxiliary":
        raise NotImplementedError("Stage-4 3D DtN v1 supports only stage4_dtn_assembly='auxiliary'.")
    if cfg.use_pml:
        raise ValueError("stage4_boundary_model='dtn_port' requires use_pml=False.")
    if floquet_data is None:
        raise ValueError("stage4_boundary_model='dtn_port' requires x/y Floquet constraints.")
    if cell_static_condensation and (
        cfg.matrix_diagnostics_assemble_only
        or cfg.matrix_diagnostics_factorization_only
    ):
        raise ValueError(
            "Task035b cell static condensation requires a complete solve; "
            "assemble-only/factorization-only diagnostics are unsupported."
        )
    if (
        floquet_slave_elimination
        and not cell_static_condensation
    ):
        raise ValueError(
            "Task035b Floquet slave elimination currently requires "
            "stage4_cell_static_condensation=True."
        )
    if assembly_time_cell_static_condensation and (
        not cell_static_condensation
        or not floquet_slave_elimination
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
    timing_details["stage4_dtn_surface_quadrature_degree"] = int(
        dtn_quadrature_degree
    )
    assembly_time_system: AssemblyTimeCondensedSystem | None = None
    variable_p_reduction: VariablePAssemblyTimeReduction | None = None
    local_h_context = getattr(mesh_data, "local_h_context", None)
    assembly_time_full_rhs: PETSc.Vec | None = None
    variable_p_active_full_rhs: PETSc.Vec | None = None
    variable_p_trace_functional_audits: list[dict[str, Any]] = []

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
        support_group_by_row = tuple(
            0 if mode.side == "top" else 1 for mode in modes
        )
        if variable_p_backend:
            if (
                cfg.stage4_variable_p_cell_degree_plan is None
                and local_h_context is None
            ):
                raise RuntimeError(
                    "qualified variable-p backend lost both of its plans"
                )
            variable_p_reduction = (
                build_variable_p_assembly_time_reduction(
                    fem.form(a),
                    V,
                    mesh_data.cell_tags,
                    degree_plan_path=cfg.stage4_variable_p_cell_degree_plan,
                    phase_x=floquet_data.phase_x,
                    phase_y=floquet_data.phase_y,
                    local_h_context=local_h_context,
                    appended_global_rows=n_aux,
                    appended_support_owned_cell_groups=(
                        support_cell_groups
                    ),
                    appended_support_group_by_row=(
                        support_group_by_row
                    ),
                    defer_final_assembly=True,
                    retain_local_schur_for_research=(
                        variable_p_retain_local_schur_for_research
                    ),
                )
            )
            reduction_system = variable_p_reduction.system
        else:
            assembly_time_system = (
                build_unconstrained_assembly_time_condensation(
                    fem.form(a),
                    V,
                    mesh_data.cell_tags,
                    mpc=floquet_data.mpc,
                    appended_global_rows=n_aux,
                    appended_support_owned_cell_groups=(
                        support_cell_groups
                    ),
                    appended_support_group_by_row=(
                        support_group_by_row
                    ),
                    defer_final_assembly=True,
                )
            )
            reduction_system = assembly_time_system
        A_base = None
        A_aug = reduction_system.matrix
        n_fe = int(
            reduction_system.active_trace_rows
            if variable_p_reduction is not None
            else reduction_system.active_rows
        )
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
        assembly_time_system is not None
        or variable_p_reduction is not None
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
            raise RuntimeError(
                "assembly-time vector reduction is not active"
            )
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
            raise RuntimeError(
                "assembly-time interior bilinear is not active"
            )
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
            variable_p_active_full_rhs = (
                variable_p_reduction.project_p6_vector(full_b_base)
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
                dofs=int(
                    V.dofmap.index_map.size_global
                    * V.dofmap.index_map_bs
                ),
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
                "assembly_time_final_augmented_matrix": True,
                "base_to_augmented_matrix_copy_performed": False,
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
    timing_details["stage4_dtn_augmented_block_copy_seconds"] = float(
        comm.allreduce(time.perf_counter() - t0, op=MPI.MAX)
    ) if not assembly_time_active else 0.0
    if (
        cfg.direct_release_base_after_augmentation
        and not assembly_time_active
    ):
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
            dofs=int(
                V.dofmap.index_map.size_global
                * V.dofmap.index_map_bs
            ),
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
        variable_p_live_observer is not None
        and variable_p_reduction is not None
    )
    external_operator_digest = (
        hashlib.sha256() if trace_only_content_identity_active else None
    )
    external_rhs_digest = (
        hashlib.sha256() if trace_only_content_identity_active else None
    )
    if (
        external_operator_digest is not None
        and external_rhs_digest is not None
    ):
        timing_details[
            "stage4_dtn_trace_only_base_reduced_rhs_norm"
        ] = float(b_aug.norm())
        external_operator_digest.update(
            b"task035d.trace-only-external-operator.local.v1\0"
        )
        external_rhs_digest.update(
            b"task035d.trace-only-external-rhs.local.v1\0"
        )
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

    t0 = time.perf_counter()
    if assembly_time_active:
        if assembly_time_full_rhs is None:
            raise RuntimeError("assembly-time full RHS was not initialized")
        incident_traction_vec = _assemble_unconstrained_vector(
            _incident_top_traction_form(V, mesh_data, cfg)
        )
        if variable_p_reduction is not None:
            if variable_p_active_full_rhs is None:
                raise RuntimeError(
                    "variable-p active full RHS was not initialized"
                )
            active_incident = variable_p_reduction.project_p6_vector(
                incident_traction_vec
            )
            variable_p_trace_functional_audits.append(
                variable_p_reduction
                .enforce_trace_only_active_functional(
                    active_incident,
                    role="incident_top_traction",
                )
            )
            reduced_incident = (
                variable_p_reduction.reduce_active_vector(
                    active_incident,
                    side="right",
                )
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
        inc_rows, inc_values = _vec_nonzero_owned_entries(
            reduced_incident
        )
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
        inc_rows, inc_values = _vec_nonzero_owned_entries(
            incident_traction_vec
        )
        incident_traction_vec.destroy()
    if external_rhs_digest is not None:
        _update_evidence_digest_sparse(
            external_rhs_digest,
            "incident-top-traction",
            inc_rows,
            inc_values,
        )
    if len(inc_rows):
        b_aug.setValues(inc_rows, inc_values, addv=PETSc.InsertMode.ADD_VALUES)
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
    matrix_row_start, matrix_row_end = A_aug.getOwnershipRange()
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
                    surface_assemblers[
                        (mode.side, 0)
                    ].assemble_unconstrained_vector(mode),
                    surface_assemblers[
                        (mode.side, 1)
                    ].assemble_unconstrained_vector(mode),
                )
                if variable_p_reduction is not None:
                    component_active_vectors = tuple(
                        variable_p_reduction.project_p6_vector(vector)
                        for vector in component_full_vectors
                    )
                    for component, vector in enumerate(
                        component_active_vectors
                    ):
                        variable_p_trace_functional_audits.append(
                            variable_p_reduction
                            .enforce_trace_only_active_functional(
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
                    _vec_nonzero_owned_entries(vector)
                    for vector in right_vectors
                )
                component_left_entries = tuple(
                    _vec_nonzero_owned_entries(vector)
                    for vector in left_vectors
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
                    surface_assemblers[
                        (mode.side, 0)
                    ].assemble_entries(mode, floquet_data.mpc),
                    surface_assemblers[
                        (mode.side, 1)
                    ].assemble_entries(mode, floquet_data.mpc),
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
        if (
            incident_projection != 0.0
            and (
                component_active_vectors is not None
                or component_full_vectors is not None
            )
        ):
            if variable_p_reduction is not None:
                if (
                    variable_p_active_full_rhs is None
                    or component_active_vectors is None
                ):
                    raise RuntimeError(
                        "variable-p modal RHS lifecycle is invalid"
                    )
                for coefficient, vector in zip(
                    traction_vector[:2],
                    component_active_vectors,
                    strict=True,
                ):
                    variable_p_active_full_rhs.axpy(
                        PETSc.ScalarType(
                            -incident_projection * coefficient
                        ),
                        vector,
                    )
            else:
                if (
                    assembly_time_full_rhs is None
                    or component_full_vectors is None
                ):
                    raise RuntimeError(
                        "assembly-time modal RHS lifecycle is invalid"
                    )
                for coefficient, vector in zip(
                    traction_vector[:2],
                    component_full_vectors,
                    strict=True,
                ):
                    assembly_time_full_rhs.axpy(
                        PETSc.ScalarType(
                            -incident_projection * coefficient
                        ),
                        vector,
                    )

        if len(ell_cols):
            ell_cols_total_local += int(len(ell_cols))
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
            A_aug.setValue(
                aux_global,
                aux_global,
                PETSc.ScalarType(auxiliary_diagonal),
                addv=matrix_insert_mode,
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

    if (
        external_operator_digest is not None
        and external_rhs_digest is not None
    ):
        timing_details[
            "stage4_dtn_trace_only_external_operator_sha256"
        ] = _partition_bound_evidence_sha256(
            comm,
            namespace=(
                "task035d.trace-only-external-operator.partition.v1"
            ),
            local_sha256=external_operator_digest.hexdigest(),
        )
        timing_details[
            "stage4_dtn_trace_only_external_rhs_sha256"
        ] = _partition_bound_evidence_sha256(
            comm,
            namespace="task035d.trace-only-external-rhs.partition.v1",
            local_sha256=external_rhs_digest.hexdigest(),
        )
        timing_details[
            "stage4_dtn_trace_only_content_identity_mpi_size"
        ] = int(comm.size)
        timing_details[
            "stage4_dtn_trace_only_content_identity_partition_bound"
        ] = True

    if variable_p_reduction is not None:
        timing_details[
            "stage4_dtn_variable_p_auxiliary_interior_columns_allocated"
        ] = False
        timing_details[
            "stage4_dtn_variable_p_auxiliary_interior_column_bytes_local_max"
        ] = 0
    if variable_p_trace_functional_audits:
        removed_over_threshold = [
            float(audit["removed_active_interior_max_abs"])
            / float(audit["acceptance_threshold"])
            for audit in variable_p_trace_functional_audits
        ]
        timing_details[
            "stage4_dtn_variable_p_trace_functional_count"
        ] = len(variable_p_trace_functional_audits)
        timing_details[
            "stage4_dtn_variable_p_removed_interior_max_abs"
        ] = max(
            float(audit["removed_active_interior_max_abs"])
            for audit in variable_p_trace_functional_audits
        )
        timing_details[
            "stage4_dtn_variable_p_acceptance_threshold_max_abs"
        ] = max(
            float(audit["acceptance_threshold"])
            for audit in variable_p_trace_functional_audits
        )
        timing_details[
            "stage4_dtn_variable_p_removed_interior_over_threshold_max"
        ] = max(removed_over_threshold)
        timing_details[
            "stage4_dtn_variable_p_trace_only_gate_pass"
        ] = True

    timing_details["stage4_dtn_modal_loop_seconds"] = float(
        comm.allreduce(time.perf_counter() - modal_loop_start, op=MPI.MAX)
    )
    timing_details["stage4_dtn_modal_vector_assembly_seconds"] = float(
        comm.allreduce(modal_vector_assembly_seconds_local, op=MPI.MAX)
    )
    timing_details["stage4_dtn_modal_block_insert_seconds"] = float(
        comm.allreduce(modal_block_insert_seconds_local, op=MPI.MAX)
    )
    timing_details["stage4_dtn_unique_surface_orders"] = int(comm.allreduce(unique_surface_orders, op=MPI.MAX))
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
    A_aug.assemble()
    b_aug.assemble()
    augmented_matrix_stats_after_finalize = _petsc_matrix_stats(A_aug)
    storage_carrier_fe_dofs = int(
        V.dofmap.index_map.size_global * V.dofmap.index_map_bs
    )
    active_exact_sequence_fe_dofs = (
        int(
            variable_p_reduction.build_audit[
                "actual_conforming_active_fe_dofs"
            ]
        )
        if variable_p_reduction is not None
        else storage_carrier_fe_dofs
    )
    assembled_dof_row_fields = _dof_row_semantics(
        active_exact_sequence_fe_dofs=active_exact_sequence_fe_dofs,
        storage_carrier_fe_dofs=storage_carrier_fe_dofs,
        independent_trace_rows=(
            int(n_fe) if assembly_time_active else None
        ),
        augmented_rows=int(A_aug.getSize()[0]),
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
        extra={"stage4_dtn_num_auxiliary_dofs": int(n_aux)},
    )

    if cfg.matrix_diagnostics_assemble_only:
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
        E_total = fem.Function(floquet_data.mpc.function_space, name="E_total")
        solver_info = {
            "solver_backend": "PETSc augmented auxiliary Fourier-DtN port with dolfinx_mpc Floquet constraints",
            "assemble_only": True,
            **assembly_backend_fields,
            "num_auxiliary_dofs": int(n_aux),
            "num_fem_dofs_after_mpc": int(n_fe),
            "num_total_augmented_dofs": int(n_fe + n_aux),
            **assembled_dof_row_fields,
            "stage4_dtn_assembly_seconds": float(comm.allreduce(time.perf_counter() - stage_start, op=MPI.MAX)),
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
    if (
        cell_static_condensation
        and not assembly_time_active
    ):
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
        timing_details["stage4_dtn_cell_static_condensation_build_seconds"] = (
            float(
                comm.allreduce(
                    time.perf_counter() - condensation_started,
                    op=MPI.MAX,
                )
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
                (local_slaves >= 0)
                & (local_slaves < int(dofmap.index_map.size_local))
            ]
            owned_slave_original_dofs = (
                owned_slaves + int(dofmap.index_map.local_range[0])
            ).astype(PETSc.IntType)
            independent_trace_system = (
                build_floquet_independent_trace_system(
                    condensed_system.matrix,
                    condensed_system.rhs,
                    owned_slave_original_dofs=owned_slave_original_dofs,
                    original_to_trace=condensed_system.original_to_trace,
                )
            )
            independent_trace_matrix_stats = _petsc_matrix_stats(
                independent_trace_system.matrix
            )
            timing_details[
                "stage4_dtn_floquet_slave_elimination_build_seconds"
            ] = float(
                comm.allreduce(
                    time.perf_counter() - independent_started,
                    op=MPI.MAX,
                )
            )
            solve_A = independent_trace_system.matrix
            solve_b = independent_trace_system.rhs
            solve_dofs = int(independent_trace_system.active_rows)
            solve_prefix = (
                f"stage4_3d_dtn_cell_condensed_floquet_independent_"
                f"{cfg.case_name}_"
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
                    "floquet_slave_elimination": (
                        independent_trace_system.build_audit
                    ),
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
    try:
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
                    None
                    if condensed_system is None
                    else condensed_system.build_audit
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
    setup_and_solve_seconds = float(
        comm.allreduce(time.perf_counter() - t0, op=MPI.MAX)
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
                "diffraction_total_power_source": (
                    "factorization_only_skipped_solve"
                ),
                **_port_mode_count_metrics(modes),
            },
        }
    timing_details["stage4_dtn_linear_solve_seconds"] = setup_and_solve_seconds

    assembly_time_field = None
    embedded_fe_solution = None
    variable_p_recovered: VariablePRecoveredSolution | None = None
    if variable_p_reduction is not None:
        if (
            assembly_time_full_rhs is None
            or variable_p_active_full_rhs is None
        ):
            raise RuntimeError(
                "variable-p recovery requires the active and p6 RHS"
            )
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
        timing_details[
            "stage4_dtn_cell_static_condensation_recovery_seconds"
        ] = float(
            comm.allreduce(
                time.perf_counter() - recovery_started,
                op=MPI.MAX,
            )
        )
    elif assembly_time_system is not None:
        if assembly_time_full_rhs is None:
            raise RuntimeError(
                "assembly-time recovery requires the full-space RHS"
            )
        recovery_started = time.perf_counter()
        (
            assembly_time_field,
            embedded_fe_solution,
            condensation_recovery,
        ) = (
            _assign_fe_solution_from_assembly_time_condensation(
                solve_x,
                assembly_time_system,
                floquet_data,
                assembly_time_full_rhs,
            )
        )
        x_aug = solve_x
        timing_details[
            "stage4_dtn_cell_static_condensation_recovery_seconds"
        ] = float(
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
        timing_details["stage4_dtn_cell_static_condensation_recovery_seconds"] = (
            float(
                comm.allreduce(
                    time.perf_counter() - recovery_started,
                    op=MPI.MAX,
                )
            )
        )
    else:
        x_aug = solve_x

    if (
        variable_p_reduction is not None
        and variable_p_recovered is not None
    ):
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
        timing_details[
            "stage4_dtn_matrix_free_full_residual_seconds"
        ] = float(
            comm.allreduce(
                time.perf_counter() - residual_started,
                op=MPI.MAX,
            )
        )
    elif (
        assembly_time_system is not None
        and embedded_fe_solution is not None
    ):
        residual_started = time.perf_counter()
        linear_residual = _assembly_time_full_operator_residual(
            a,
            floquet_data,
            embedded_fe_solution,
            A_aug,
            b_aug,
            x_aug,
            assembly_time_system,
            assembly_time_full_rhs,
        )
        embedded_fe_solution.destroy()
        embedded_fe_solution = None
        assembly_time_full_rhs.destroy()
        assembly_time_full_rhs = None
        timing_details[
            "stage4_dtn_matrix_free_full_residual_seconds"
        ] = float(
            comm.allreduce(
                time.perf_counter() - residual_started,
                op=MPI.MAX,
            )
        )
    else:
        linear_residual = _linear_residual(A_aug, b_aug, x_aug)
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
        extra={"linear_system_relative_residual": linear_residual.get("linear_system_relative_residual")},
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
    port_metrics = _port_power_metrics(cfg, modes, aux_values, incident_projections)
    if cfg.dtn_auxiliary_direct_projection_audit:
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
        timing_details[
            "stage4_dtn_auxiliary_direct_projection_audit_seconds"
        ] = float(
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
    _write_port_outputs(out_dir, cfg, modes, aux_values, incident_projections, port_metrics, comm)
    _write_progress_event(
        out_dir,
        comm,
        stage="after_official_rta",
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
            "floquet_independent_matrix_stats": (
                independent_trace_matrix_stats
            ),
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
        trace_constraints = (
            variable_p_reduction.system.trace_constraints
        )
        if trace_constraints is None:
            raise RuntimeError(
                "variable-p audit lost its physical trace constraints"
            )
        cell_static_condensation_audit = {
            **variable_p_reduction.build_audit,
            "condensed_matrix_stats": (
                augmented_matrix_stats_after_finalize
            ),
            "floquet_independent_matrix_stats": (
                augmented_matrix_stats_after_finalize
            ),
            "floquet_slave_elimination": (
                dict(trace_constraints.audit)
            ),
            "trace_constraint_elimination": (
                dict(trace_constraints.audit)
            ),
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
            "condensed_matrix_stats": (
                augmented_matrix_stats_after_finalize
            ),
            "floquet_independent_matrix_stats": (
                augmented_matrix_stats_after_finalize
            ),
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
            "ordinary_default_changed": False,
        }
    solver_info = {
        "solver_backend": (
            "PETSc exact-sequence inactive-row-free variable-p assembly-time "
            "trace Schur + Floquet-independent auxiliary Fourier-DtN port"
            if variable_p_reduction is not None
            else
            "PETSc assembly-time exact cell-interior trace Schur + direct "
            "Floquet-independent insertion + auxiliary Fourier-DtN port"
            if assembly_time_active
            else
            "PETSc exact cell-interior trace Schur + auxiliary Fourier-DtN "
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
        "num_active_trace_dofs": (
            None
            if not assembly_time_active
            else int(n_fe)
        ),
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
            condensed_system is not None
            or assembly_time_active
        ),
        "stage4_assembly_time_cell_static_condensation": bool(
            assembly_time_active
        ),
        "stage4_variable_p_active": bool(
            variable_p_reduction is not None
        ),
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
            else int(
                variable_p_reduction.build_audit[
                    "actual_conforming_active_fe_dofs"
                ]
            )
        ),
        "num_raw_broken_active_fe_dofs": (
            None
            if variable_p_reduction is None
            else int(
                variable_p_reduction.build_audit[
                    "raw_broken_active_fe_dofs"
                ]
            )
        ),
        "stage4_floquet_slave_elimination": bool(
            independent_trace_system is not None
            or assembly_time_active
        ),
        "cell_static_condensation": cell_static_condensation_audit,
        "stage4_dtn_assembly_seconds": float(comm.allreduce(time.perf_counter() - stage_start, op=MPI.MAX)),
        "ksp_converged_reason": int(ksp.getConvergedReason()),
        "ksp_iterations": int(ksp.getIterationNumber()),
        "primal_ksp_residual_norm": float(ksp.getResidualNorm()),
        "actual_ksp_type": ksp.getType(),
        "actual_pc_type": ksp.getPC().getType(),
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
        "dtn_trace_alias_preflight": trace_alias_preflight,
        "explicit_chac_constructed": False,
        "dtn_auxiliary_dense_block_constructed": False,
        **ksp_telemetry,
        **timing_details,
        **linear_residual,
    }
    try:
        solver_info["actual_pc_factor_solver_type"] = ksp.getPC().getFactorSolverType()
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
            if (
                variable_p_reduction is None
                or variable_p_recovered is None
            ):
                raise RuntimeError(
                    "requested variable-p live observer lost its recovered "
                    "state"
                )
            relative_residual = linear_residual.get(
                "linear_system_relative_residual"
            )
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
            port_operator_audit = _variable_p_port_operator_audit(
                timing_details
            )
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
                port_operator_audit=_deep_readonly_copy(
                    port_operator_audit
                ),
                full_active_residual=_deep_readonly_copy(
                    linear_residual
                ),
                primal_solver_telemetry=_deep_readonly_copy(
                    {
                        "converged_reason": solver_info[
                            "ksp_converged_reason"
                        ],
                        "iterations": solver_info["ksp_iterations"],
                        "residual_norm": solver_info[
                            "primal_ksp_residual_norm"
                        ],
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
                raise AssertionError(
                    "collective live-view preflight lost its view"
                )
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
                    dofs=int(
                        V.dofmap.index_map.size_global
                        * V.dofmap.index_map_bs
                    ),
                    constraints=floquet_data.num_constraints,
                    matrix_stats=(
                        augmented_matrix_stats_after_finalize
                    ),
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
            local_schur_release = (
                variable_p_reduction.release_retained_local_schur()
            )
        variable_p_recovered = None
        solver_info["variable_p_live_observer_invoked"] = True
        solver_info["variable_p_local_schur_release"] = (
            local_schur_release
        )

    return {
        "E_total": E_total,
        "A": returned_A,
        "b": returned_b,
        "x": returned_x,
        "ksp": ksp,
        "solver_info": solver_info,
        "port_metrics": port_metrics,
        "goal_context": goal_context,
    }


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
    variable_p_live_observer: (
        Callable[[Stage4VariablePLiveView], None] | None
    ) = None,
    variable_p_retain_local_schur_for_research: bool = False,
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
        )
    )
    if len(set(observer_flags)) != 1:
        raise ValueError(
            "the variable-p live observer must be enabled on every MPI rank "
            "and research Schur retention flags must match"
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
            variable_p_live_observer=variable_p_live_observer,
            variable_p_retain_local_schur_for_research=(
                variable_p_retain_local_schur_for_research
            ),
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
