"""Streaming physical missing-p6 complement actions for Task035b.

The retained state is the fixed p5-trace/p6-interior augmented DtN system
(``L``).  The complement consists of the physical p6 trace modes that are
missing from that retained space (``H``).  This module supplies the action-only
pieces needed by
:mod:`src.adaptivity.complement_schur_channel_dwr`:

``A_HH``, ``A_HL``, ``A_LH``, ``A_LL^{-1}``, and their Hermitian actions.

No global p6 trace matrix is formed.  A full-p6 *local* cell Schur tensor is
retained once per oriented material/tensor class and streamed through the
qualified Riesz/Piola/Floquet expansion.  DtN coupling is represented by its
two projected modal component vectors and one existing auxiliary row per
mode.  The inactive missing modes therefore never become PETSc rows.

The module is deliberately fail closed about old h14 evidence.  At present it
is an analytic action-kernel capability only: the ``actual_pde`` evidence
class is disabled until the full-p6 storage operator, same-mesh discrete
gradient, complete enriched right-hand side, full DtN mode inventory, and
generalized caller-expansion recovery are wired with content-bound live
capture provenance.  Old records cannot reconstruct those transient data.
"""

from __future__ import annotations

from dataclasses import dataclass
from inspect import signature
from numbers import Integral
from types import MappingProxyType
from typing import Any, Callable, Hashable, Literal, Mapping, Sequence

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc
from scipy.sparse.linalg import LinearOperator, gmres

from src.adaptivity.complement_schur_channel_dwr import (
    ChannelGoal,
    ComplementSchurOperator,
    GoalComponent,
)
from src.adaptivity.physical_channel_dwr_trace_selection import (
    PhysicalMissingTraceDWRLayout,
)
from src.constraints.selective_p6_trace_expansion import (
    ActualSelectiveP6TraceExpansion,
)


EvidenceClass = Literal["actual_pde", "analytic_fixture"]
VectorAction = Callable[[np.ndarray], np.ndarray]

_TINY = np.finfo(np.float64).tiny
_FOCUS_SPECS: tuple[tuple[str, GoalComponent, str], ...] = (
    ("T_m-4_n0_s_power", "real_power", "power"),
    (
        "T_m-4_n0_s_amplitude_real",
        "complex_amplitude_real",
        "amplitude_real",
    ),
    (
        "T_m-4_n0_s_amplitude_imag",
        "complex_amplitude_imag",
        "amplitude_imag",
    ),
    ("R_m-4_n0_s_power", "real_power", "power"),
    (
        "R_m-4_n0_s_amplitude_real",
        "complex_amplitude_real",
        "amplitude_real",
    ),
    (
        "R_m-4_n0_s_amplitude_imag",
        "complex_amplitude_imag",
        "amplitude_imag",
    ),
    ("R_m-5_n0_s_power", "real_power", "power"),
    (
        "R_m-5_n0_s_amplitude_real",
        "complex_amplitude_real",
        "amplitude_real",
    ),
    (
        "R_m-5_n0_s_amplitude_imag",
        "complex_amplitude_imag",
        "amplitude_imag",
    ),
)


def _validate_evidence_class(evidence_class: EvidenceClass) -> None:
    if evidence_class not in {"actual_pde", "analytic_fixture"}:
        raise ValueError("unsupported action evidence class")
    if evidence_class == "actual_pde":
        raise RuntimeError(
            "actual PDE evidence is disabled until the full-p6 live-capture "
            "and exact-sequence authority are wired"
        )


def _readonly_vector(
    values: Any,
    *,
    dimension: int,
    label: str,
) -> np.ndarray:
    vector = np.array(values, dtype=np.complex128, order="C", copy=True)
    if vector.shape != (int(dimension),):
        raise ValueError(
            f"{label} has shape {vector.shape}, expected {(dimension,)}"
        )
    if not np.all(np.isfinite(vector)):
        raise FloatingPointError(f"{label} contains NaN or Inf")
    vector.setflags(write=False)
    return vector


def _readonly_matrix(
    values: Any,
    *,
    shape: tuple[int, int],
    label: str,
) -> np.ndarray:
    matrix = np.array(values, dtype=np.complex128, order="C", copy=True)
    if matrix.shape != shape:
        raise ValueError(f"{label} has shape {matrix.shape}, expected {shape}")
    if not np.all(np.isfinite(matrix)):
        raise FloatingPointError(f"{label} contains NaN or Inf")
    matrix.setflags(write=False)
    return matrix


def _readonly_indices(
    values: Any,
    *,
    upper_bound: int,
    label: str,
) -> np.ndarray:
    raw = np.asarray(values)
    if raw.ndim != 1 or not np.issubdtype(raw.dtype, np.integer):
        raise TypeError(f"{label} must be a one-dimensional integer vector")
    result = np.asarray(raw, dtype=np.int64).copy()
    if len(np.unique(result)) != len(result):
        raise ValueError(f"{label} contains duplicates")
    if len(result) and (
        int(result.min()) < 0 or int(result.max()) >= int(upper_bound)
    ):
        raise ValueError(f"{label} contains an out-of-range coordinate")
    result.setflags(write=False)
    return result


def _allreduce_complex(
    communicator: MPI.Intracomm,
    local: np.ndarray,
) -> np.ndarray:
    global_values = np.empty_like(local)
    communicator.Allreduce(local, global_values, op=MPI.SUM)
    global_values.setflags(write=False)
    return global_values


@dataclass(frozen=True)
class PhysicalCellComplementActionLayout:
    """One owned cell's storage-to-retained/complement expansion."""

    local_cell: int
    storage_original_dofs: np.ndarray
    low_rows: np.ndarray
    high_rows: np.ndarray
    low_coefficients: np.ndarray
    high_coefficients: np.ndarray

    def __post_init__(self) -> None:
        local_cell = int(self.local_cell)
        if local_cell < 0:
            raise ValueError("local cell index must be nonnegative")
        storage = np.asarray(self.storage_original_dofs, dtype=np.int64).copy()
        if storage.ndim != 1 or len(np.unique(storage)) != len(storage):
            raise ValueError("cell storage trace rows must be unique")
        storage.setflags(write=False)
        low = np.asarray(self.low_rows, dtype=np.int64).copy()
        high = np.asarray(self.high_rows, dtype=np.int64).copy()
        for indices, label in ((low, "low"), (high, "high")):
            if indices.ndim != 1 or len(np.unique(indices)) != len(indices):
                raise ValueError(f"cell {label} coordinates must be unique")
            if len(indices) and int(indices.min()) < 0:
                raise ValueError(f"cell {label} coordinates must be nonnegative")
            indices.setflags(write=False)
        low_coefficients = _readonly_matrix(
            self.low_coefficients,
            shape=(len(storage), len(low)),
            label="cell retained-trace coefficients",
        )
        high_coefficients = _readonly_matrix(
            self.high_coefficients,
            shape=(len(storage), len(high)),
            label="cell missing-p6 coefficients",
        )
        object.__setattr__(self, "local_cell", local_cell)
        object.__setattr__(self, "storage_original_dofs", storage)
        object.__setattr__(self, "low_rows", low)
        object.__setattr__(self, "high_rows", high)
        object.__setattr__(self, "low_coefficients", low_coefficients)
        object.__setattr__(self, "high_coefficients", high_coefficients)


@dataclass(frozen=True)
class PhysicalStorageTraceDualProjection:
    """Sparse ``C_L^H``/``C_H^H`` data for one global storage trace row."""

    storage_original_dof: int
    low_rows: np.ndarray
    low_coefficients: np.ndarray
    high_rows: np.ndarray
    high_coefficients: np.ndarray

    def __post_init__(self) -> None:
        original = int(self.storage_original_dof)
        if original < 0:
            raise ValueError("storage original DoF must be nonnegative")
        low = np.asarray(self.low_rows, dtype=np.int64).copy()
        high = np.asarray(self.high_rows, dtype=np.int64).copy()
        low_coefficients = _readonly_vector(
            self.low_coefficients,
            dimension=len(low),
            label="storage retained coefficients",
        )
        high_coefficients = _readonly_vector(
            self.high_coefficients,
            dimension=len(high),
            label="storage complement coefficients",
        )
        low.setflags(write=False)
        high.setflags(write=False)
        object.__setattr__(self, "storage_original_dof", original)
        object.__setattr__(self, "low_rows", low)
        object.__setattr__(self, "high_rows", high)
        object.__setattr__(self, "low_coefficients", low_coefficients)
        object.__setattr__(self, "high_coefficients", high_coefficients)


@dataclass(frozen=True)
class PhysicalMissingP6ActionLayout:
    """Hash-bound coordinate bridge used by every streaming action."""

    owned_cells: tuple[PhysicalCellComplementActionLayout, ...]
    storage_dual_projections: Mapping[
        int, PhysicalStorageTraceDualProjection
    ]
    retained_trace_rows: int
    low_dimension: int
    high_dimension: int
    storage_trace_rows_per_cell: int
    catalog_sha256: str
    trace_geometry_sha256: str
    ordered_trace_basis_sha256: str
    qualification_sha256: str
    complement_layout_sha256: str
    audit: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.audit.get("pass") is not True:
            raise ValueError("physical action layout is unqualified")
        projections = {
            int(original): projection
            for original, projection in self.storage_dual_projections.items()
        }
        if set(projections) != {
            projection.storage_original_dof
            for projection in projections.values()
        }:
            raise ValueError("storage dual projection keys are inconsistent")
        object.__setattr__(
            self,
            "storage_dual_projections",
            MappingProxyType(projections),
        )


def _split_active_columns(
    active_rows: np.ndarray,
    coefficients: np.ndarray,
    *,
    base_diagnostic_row_to_live_row: Mapping[int, int],
    missing_diagnostic_row_to_high_row: Mapping[int, int],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    low_columns: list[int] = []
    low_rows: list[int] = []
    high_columns: list[int] = []
    high_rows: list[int] = []
    for column, raw_row in enumerate(active_rows):
        row = int(raw_row)
        if row in base_diagnostic_row_to_live_row:
            low_columns.append(column)
            low_rows.append(base_diagnostic_row_to_live_row[row])
        elif row in missing_diagnostic_row_to_high_row:
            high_columns.append(column)
            high_rows.append(missing_diagnostic_row_to_high_row[row])
        else:
            raise RuntimeError(
                "diagnostic expansion references an unknown active row"
            )
    low_order = np.argsort(low_rows)
    high_order = np.argsort(high_rows)
    low_rows_array = np.asarray(low_rows, dtype=np.int64)[low_order]
    high_rows_array = np.asarray(high_rows, dtype=np.int64)[high_order]
    low_matrix = np.asarray(
        coefficients[:, np.asarray(low_columns, dtype=np.int64)][:, low_order],
        dtype=np.complex128,
    )
    high_matrix = np.asarray(
        coefficients[:, np.asarray(high_columns, dtype=np.int64)][
            :, high_order
        ],
        dtype=np.complex128,
    )
    return low_rows_array, low_matrix, high_rows_array, high_matrix


def build_physical_missing_p6_action_layout(
    *,
    diagnostic_expansion: ActualSelectiveP6TraceExpansion,
    physical_layout: PhysicalMissingTraceDWRLayout,
    retained_active_row_by_logical_mode: Mapping[tuple[int, int], int],
    retained_system_rows: int,
    communicator: MPI.Intracomm,
    expected_storage_trace_rows_per_cell: int = 432,
) -> PhysicalMissingP6ActionLayout:
    """Split an all-missing diagnostic expansion without allocating rows.

    ``diagnostic_expansion`` is only a coordinate authority.  It must select
    every missing physical orbit, and it must never have been passed to PETSc.
    Its selected row numbers are translated directly to the canonical
    complement indices in ``physical_layout``.  The retained p5 logical modes
    are translated separately to the row numbering of the already-solved
    fixed-trace candidate.
    """

    audit = diagnostic_expansion.audit
    caller_audit = (
        diagnostic_expansion.caller_trace_expansion.qualification_audit
    )
    if audit.get("pass") is not True:
        raise RuntimeError("diagnostic full-p6 expansion is not qualified")
    if audit.get("matrix_constructed") is not False:
        raise RuntimeError(
            "diagnostic full-p6 expansion must not be inserted into a matrix"
        )
    if caller_audit.get("full_trace_matrix_constructed") is not False:
        raise RuntimeError("full-p6 trace matrix materialization is forbidden")
    if audit.get("inactive_missing_petsc_rows") != 0:
        raise RuntimeError("inactive missing-p6 modes received PETSc rows")
    if physical_layout.audit.get("pass") is not True:
        raise RuntimeError("physical Riesz/Piola/Floquet layout is unqualified")

    base_logical = dict(diagnostic_expansion.base_logical_rows)
    missing_logical = dict(
        diagnostic_expansion.selected_missing_logical_rows
    )
    canonical_missing = dict(physical_layout.logical_mode_to_index)
    if set(missing_logical) != set(canonical_missing):
        raise RuntimeError(
            "diagnostic expansion must select every physical missing-p6 mode"
        )
    if (
        diagnostic_expansion.selected_missing_rows
        != physical_layout.high_dimension
    ):
        raise RuntimeError("diagnostic missing dimension differs from layout")

    live_map = {
        (int(key[0]), int(key[1])): int(row)
        for key, row in retained_active_row_by_logical_mode.items()
    }
    if set(live_map) != set(base_logical):
        raise RuntimeError(
            "retained candidate row map must cover every p5 logical mode"
        )
    retained_trace_rows = len(live_map)
    if set(live_map.values()) != set(range(retained_trace_rows)):
        raise RuntimeError(
            "retained candidate trace rows must be a contiguous bijection"
        )
    low_dimension = int(retained_system_rows)
    if low_dimension <= retained_trace_rows:
        raise ValueError(
            "retained system must include its existing DtN auxiliary rows"
        )

    base_row_to_live = {
        int(diagnostic_row): live_map[logical]
        for logical, diagnostic_row in base_logical.items()
    }
    missing_row_to_high = {
        int(diagnostic_row): canonical_missing[logical]
        for logical, diagnostic_row in missing_logical.items()
    }
    if set(base_row_to_live) & set(missing_row_to_high):
        raise RuntimeError("diagnostic retained and missing rows overlap")
    expected_active = set(base_row_to_live) | set(missing_row_to_high)
    if expected_active != set(range(diagnostic_expansion.active_rows)):
        raise RuntimeError("diagnostic active coordinates are not bijective")

    expected_cell_rows = int(expected_storage_trace_rows_per_cell)
    if expected_cell_rows <= 0:
        raise ValueError("expected cell trace row count must be positive")
    cells: list[PhysicalCellComplementActionLayout] = []
    for cell in diagnostic_expansion.owned_cell_expansions:
        if len(cell.storage_original_dofs) != expected_cell_rows:
            raise RuntimeError(
                "full-p6 cell trace dimension differs from the qualified "
                f"hexahedral value: {len(cell.storage_original_dofs)} != "
                f"{expected_cell_rows}"
            )
        low_rows, low_matrix, high_rows, high_matrix = (
            _split_active_columns(
                cell.active_rows,
                cell.coefficient_matrix,
                base_diagnostic_row_to_live_row=base_row_to_live,
                missing_diagnostic_row_to_high_row=missing_row_to_high,
            )
        )
        cells.append(
            PhysicalCellComplementActionLayout(
                local_cell=cell.local_cell,
                storage_original_dofs=cell.storage_original_dofs,
                low_rows=low_rows,
                high_rows=high_rows,
                low_coefficients=low_matrix,
                high_coefficients=high_matrix,
            )
        )

    local_low = {
        int(row) for cell in cells for row in cell.low_rows.tolist()
    }
    local_high = {
        int(row) for cell in cells for row in cell.high_rows.tolist()
    }
    global_low = {
        row for packet in communicator.allgather(local_low) for row in packet
    }
    global_high = {
        row for packet in communicator.allgather(local_high) for row in packet
    }
    if global_low != set(range(retained_trace_rows)):
        raise RuntimeError("cell expansions do not cover retained trace rows")
    if global_high != set(range(physical_layout.high_dimension)):
        raise RuntimeError("cell expansions do not cover the complement")

    storage_projections: dict[
        int, PhysicalStorageTraceDualProjection
    ] = {}
    for original, (rows, coefficients) in (
        diagnostic_expansion.storage_expansion_by_original.items()
    ):
        row_matrix = np.asarray(coefficients, dtype=np.complex128).reshape(1, -1)
        low_rows, low_matrix, high_rows, high_matrix = (
            _split_active_columns(
                np.asarray(rows, dtype=np.int64),
                row_matrix,
                base_diagnostic_row_to_live_row=base_row_to_live,
                missing_diagnostic_row_to_high_row=missing_row_to_high,
            )
        )
        storage_projections[int(original)] = (
            PhysicalStorageTraceDualProjection(
                storage_original_dof=int(original),
                low_rows=low_rows,
                low_coefficients=low_matrix[0],
                high_rows=high_rows,
                high_coefficients=high_matrix[0],
            )
        )

    checks = MappingProxyType(
        {
            "all_missing_physical_orbits_present": True,
            "canonical_high_coordinates_are_bijective": True,
            "retained_candidate_rows_are_separately_authoritative": True,
            "physical_riesz_piola_floquet_pullbacks_used": True,
            "periodic_orbit_quotient_used": True,
            "full_p6_storage_cell_trace_dimension_verified": True,
            "diagnostic_expansion_not_inserted_into_petsc": True,
            "full_p6_trace_matrix_not_materialized": True,
            "inactive_missing_p6_rows_allocated_is_zero": True,
        }
    )
    layout_audit = MappingProxyType(
        {
            "schema_version": (
                "task035b.physical-missing-p6-action-layout.v1"
            ),
            "status": "physical_missing_p6_action_layout_pass",
            "pass": True,
            "mpi_size": int(communicator.size),
            "owned_cell_count": len(cells),
            "retained_trace_rows": retained_trace_rows,
            "retained_system_rows": low_dimension,
            "high_dimension": physical_layout.high_dimension,
            "storage_trace_rows_per_cell": expected_cell_rows,
            "all_missing_expansion_role": (
                "diagnostic_coordinate_authority_only"
            ),
            "full_p6_trace_matrix_materialized": False,
            "inactive_missing_p6_rows_allocated": 0,
            "ordinary_default_changed": False,
            "checks": checks,
        }
    )
    return PhysicalMissingP6ActionLayout(
        owned_cells=tuple(cells),
        storage_dual_projections=storage_projections,
        retained_trace_rows=retained_trace_rows,
        low_dimension=low_dimension,
        high_dimension=physical_layout.high_dimension,
        storage_trace_rows_per_cell=expected_cell_rows,
        catalog_sha256=physical_layout.catalog_sha256,
        trace_geometry_sha256=physical_layout.trace_geometry_sha256,
        ordered_trace_basis_sha256=(
            physical_layout.ordered_trace_basis_sha256
        ),
        qualification_sha256=physical_layout.qualification_sha256,
        complement_layout_sha256=physical_layout.layout_sha256,
        audit=layout_audit,
    )


@dataclass(frozen=True)
class ProjectedCondensedDual:
    """One full-p6 condensed vector projected into ``L`` and ``H``."""

    retained: np.ndarray
    missing: np.ndarray
    audit: Mapping[str, Any]

    def __post_init__(self) -> None:
        retained = np.asarray(self.retained, dtype=np.complex128).copy()
        missing = np.asarray(self.missing, dtype=np.complex128).copy()
        if retained.ndim != 1 or missing.ndim != 1:
            raise ValueError("projected condensed duals must be vectors")
        retained.setflags(write=False)
        missing.setflags(write=False)
        object.__setattr__(self, "retained", retained)
        object.__setattr__(self, "missing", missing)


def project_full_p6_condensed_trace_dual(
    layout: PhysicalMissingP6ActionLayout,
    *,
    owned_storage_trace_rows: Sequence[int],
    owned_storage_trace_values: np.ndarray,
    cell_storage_trace_corrections: Mapping[int, np.ndarray],
    communicator: MPI.Intracomm,
) -> ProjectedCondensedDual:
    """Project one right/left condensed full-p6 vector without a matrix.

    The first two inputs contain every globally owned storage-trace entry
    exactly once.  ``cell_storage_trace_corrections`` contains the already
    locally condensed interior contribution in each owned cell's storage
    trace ordering.  This mirrors
    ``condense_unconstrained_vector_to_active_trace`` without first allocating
    a full-p6 active PETSc vector.
    """

    rows = np.asarray(owned_storage_trace_rows, dtype=np.int64)
    values = _readonly_vector(
        owned_storage_trace_values,
        dimension=len(rows),
        label="owned storage trace dual",
    )
    if len(np.unique(rows)) != len(rows):
        raise ValueError("owned storage trace rows are duplicated")
    expected_rows = set(layout.storage_dual_projections)
    packets = communicator.allgather(rows.tolist())
    flattened = [int(row) for packet in packets for row in packet]
    if len(flattened) != len(set(flattened)):
        raise RuntimeError("storage trace row ownership is duplicated")
    if set(flattened) != expected_rows:
        raise RuntimeError(
            "owned storage trace rows do not cover the diagnostic expansion"
        )

    low = np.zeros(layout.low_dimension, dtype=np.complex128)
    high = np.zeros(layout.high_dimension, dtype=np.complex128)
    for original, value in zip(rows, values, strict=True):
        projection = layout.storage_dual_projections[int(original)]
        low[projection.low_rows] += (
            np.conj(projection.low_coefficients) * value
        )
        high[projection.high_rows] += (
            np.conj(projection.high_coefficients) * value
        )

    by_cell = {cell.local_cell: cell for cell in layout.owned_cells}
    supplied_cells = {int(cell) for cell in cell_storage_trace_corrections}
    if supplied_cells != set(by_cell):
        raise ValueError(
            "cell correction map must cover every owned cell exactly"
        )
    for local_cell, raw_correction in cell_storage_trace_corrections.items():
        cell = by_cell[int(local_cell)]
        correction = _readonly_vector(
            raw_correction,
            dimension=len(cell.storage_original_dofs),
            label=f"cell {local_cell} condensed trace correction",
        )
        low[cell.low_rows] += cell.low_coefficients.conj().T @ correction
        high[cell.high_rows] += (
            cell.high_coefficients.conj().T @ correction
        )

    global_low = _allreduce_complex(communicator, low)
    global_high = _allreduce_complex(communicator, high)
    return ProjectedCondensedDual(
        retained=global_low,
        missing=global_high,
        audit=MappingProxyType(
            {
                "schema_version": (
                    "task035b.full-p6-condensed-dual-projection.v1"
                ),
                "status": "physical_low_high_dual_projection_pass",
                "pass": True,
                "storage_trace_rows_owned_once": True,
                "cell_interior_condensation_supplied_by_caller": True,
                "physical_riesz_piola_floquet_projection_used": True,
                "full_p6_active_vector_allocated": False,
                "full_p6_trace_matrix_materialized": False,
                "inactive_missing_p6_rows_allocated": 0,
            }
        ),
    )


class FullP6LocalSchurClassCollector:
    """Minimal live observer for deduplicated oriented local Schur tensors."""

    def __init__(self, *, storage_trace_rows_per_cell: int = 432) -> None:
        self.storage_trace_rows_per_cell = int(
            storage_trace_rows_per_cell
        )
        if self.storage_trace_rows_per_cell <= 0:
            raise ValueError("storage trace row count must be positive")
        self._schur_by_class: dict[Hashable, np.ndarray] = {}
        self._cell_class: dict[int, Hashable] = {}

    def observe(
        self,
        *,
        local_cell: int,
        class_key: Hashable,
        oriented_storage_schur: np.ndarray,
    ) -> None:
        """Record a class exactly where the local full-p6 Schur is alive."""

        cell = int(local_cell)
        if cell in self._cell_class:
            raise RuntimeError("local Schur observer saw a cell twice")
        hash(class_key)
        observed = _readonly_matrix(
            oriented_storage_schur,
            shape=(
                self.storage_trace_rows_per_cell,
                self.storage_trace_rows_per_cell,
            ),
            label="oriented full-p6 local Schur",
        )
        if class_key in self._schur_by_class:
            if not np.array_equal(
                self._schur_by_class[class_key],
                observed,
            ):
                raise RuntimeError(
                    "oriented full-p6 local Schur class tensor differs "
                    "between cells"
                )
        else:
            self._schur_by_class[class_key] = observed
        self._cell_class[cell] = class_key

    @property
    def schur_by_class(self) -> Mapping[Hashable, np.ndarray]:
        return MappingProxyType(dict(self._schur_by_class))

    @property
    def cell_class_keys(self) -> Mapping[int, Hashable]:
        return MappingProxyType(dict(self._cell_class))

    @property
    def audit(self) -> Mapping[str, Any]:
        return MappingProxyType(
            {
                "schema_version": (
                    "task035b.live-full-p6-local-schur-observer.v1"
                ),
                "status": (
                    "live_local_schur_classes_captured"
                    if self._cell_class
                    else "not_run"
                ),
                "class_count": len(self._schur_by_class),
                "cell_count": len(self._cell_class),
                "one_tensor_per_oriented_class": True,
                "per_cell_tensor_duplicates_stored": False,
                "global_trace_matrix_materialized": False,
            }
        )


class PhysicalMissingP6MaxwellActions:
    """Class-deduplicated streaming Maxwell block actions."""

    def __init__(
        self,
        *,
        layout: PhysicalMissingP6ActionLayout,
        storage_schur_by_class: Mapping[Hashable, np.ndarray],
        cell_class_keys: Mapping[int, Hashable],
        communicator: MPI.Intracomm,
        evidence_class: EvidenceClass,
        captured_by_live_local_schur_observer: bool,
    ) -> None:
        _validate_evidence_class(evidence_class)
        cells = {cell.local_cell: cell for cell in layout.owned_cells}
        classes = {int(cell): key for cell, key in cell_class_keys.items()}
        if set(classes) != set(cells):
            raise RuntimeError(
                "cell class map must cover every owned action cell"
            )
        used_classes = set(classes.values())
        if used_classes != set(storage_schur_by_class):
            raise RuntimeError(
                "local Schur class cache must contain exactly used classes"
            )
        dimension = layout.storage_trace_rows_per_cell
        schur_by_class = {
            key: _readonly_matrix(
                matrix,
                shape=(dimension, dimension),
                label=f"full-p6 local Schur class {key!r}",
            )
            for key, matrix in storage_schur_by_class.items()
        }
        self.layout = layout
        self.communicator = communicator
        self.evidence_class = evidence_class
        self._cells = cells
        self._cell_classes = classes
        self._schur_by_class = schur_by_class
        self._action_counts: dict[str, int] = {}
        local_bytes = sum(matrix.nbytes for matrix in schur_by_class.values())
        self.audit = MappingProxyType(
            {
                "schema_version": (
                    "task035b.streaming-physical-missing-p6-maxwell.v1"
                ),
                "status": "streaming_action_only_maxwell_ready",
                "pass": True,
                "evidence_class": evidence_class,
                "local_oriented_class_count": len(schur_by_class),
                "global_oriented_class_count_sum": int(
                    communicator.allreduce(
                        len(schur_by_class),
                        op=MPI.SUM,
                    )
                ),
                "local_class_tensor_bytes": int(local_bytes),
                "one_local_schur_per_oriented_class": True,
                "per_cell_schur_duplicates_stored": False,
                "captured_by_live_local_schur_observer": bool(
                    captured_by_live_local_schur_observer
                ),
                "global_full_p6_matrix_materialized": False,
                "inactive_missing_p6_rows_allocated": 0,
                "ordinary_default_changed": False,
            }
        )

    def _apply(
        self,
        vector: np.ndarray,
        *,
        input_space: Literal["low", "high"],
        output_space: Literal["low", "high"],
        schur_adjoint: bool,
        label: str,
    ) -> np.ndarray:
        input_dimension = (
            self.layout.low_dimension
            if input_space == "low"
            else self.layout.high_dimension
        )
        output_dimension = (
            self.layout.low_dimension
            if output_space == "low"
            else self.layout.high_dimension
        )
        argument = _readonly_vector(
            vector,
            dimension=input_dimension,
            label=f"{label} input",
        )
        result = np.zeros(output_dimension, dtype=np.complex128)
        for local_cell, cell in self._cells.items():
            input_rows = (
                cell.low_rows
                if input_space == "low"
                else cell.high_rows
            )
            output_rows = (
                cell.low_rows
                if output_space == "low"
                else cell.high_rows
            )
            input_coefficients = (
                cell.low_coefficients
                if input_space == "low"
                else cell.high_coefficients
            )
            output_coefficients = (
                cell.low_coefficients
                if output_space == "low"
                else cell.high_coefficients
            )
            storage_input = input_coefficients @ argument[input_rows]
            schur = self._schur_by_class[
                self._cell_classes[local_cell]
            ]
            storage_output = (
                schur.conj().T @ storage_input
                if schur_adjoint
                else schur @ storage_input
            )
            result[output_rows] += (
                output_coefficients.conj().T @ storage_output
            )
        self._action_counts[label] = self._action_counts.get(label, 0) + 1
        return _allreduce_complex(self.communicator, result)

    def a_hh(self, vector: np.ndarray) -> np.ndarray:
        return self._apply(
            vector,
            input_space="high",
            output_space="high",
            schur_adjoint=False,
            label="A_HH",
        )

    def a_hh_adjoint(self, vector: np.ndarray) -> np.ndarray:
        return self._apply(
            vector,
            input_space="high",
            output_space="high",
            schur_adjoint=True,
            label="A_HH_adjoint",
        )

    def a_hl(self, vector: np.ndarray) -> np.ndarray:
        return self._apply(
            vector,
            input_space="low",
            output_space="high",
            schur_adjoint=False,
            label="A_HL",
        )

    def a_hl_adjoint(self, vector: np.ndarray) -> np.ndarray:
        return self._apply(
            vector,
            input_space="high",
            output_space="low",
            schur_adjoint=True,
            label="A_HL_adjoint",
        )

    def a_lh(self, vector: np.ndarray) -> np.ndarray:
        return self._apply(
            vector,
            input_space="high",
            output_space="low",
            schur_adjoint=False,
            label="A_LH",
        )

    def a_lh_adjoint(self, vector: np.ndarray) -> np.ndarray:
        return self._apply(
            vector,
            input_space="low",
            output_space="high",
            schur_adjoint=True,
            label="A_LH_adjoint",
        )

    @property
    def action_counts(self) -> Mapping[str, int]:
        return MappingProxyType(dict(self._action_counts))


@dataclass(frozen=True)
class ProjectedDtnComplementMode:
    """One actual auxiliary DtN mode's missing-trace coupling."""

    auxiliary_global_index: int
    traction_high: np.ndarray
    ell_high: np.ndarray
    denominator: complex
    incident_projection_solver: complex
    mode_identity: Mapping[str, Any]
    full_p6_component_vectors_projected_live: bool
    physical_condensation_used: bool

    def __post_init__(self) -> None:
        index = int(self.auxiliary_global_index)
        if index < 0:
            raise ValueError("DtN auxiliary index must be nonnegative")
        traction = np.asarray(
            self.traction_high,
            dtype=np.complex128,
        ).copy()
        ell = np.asarray(self.ell_high, dtype=np.complex128).copy()
        if traction.ndim != 1 or ell.shape != traction.shape:
            raise ValueError("projected DtN vectors have incompatible shapes")
        if not np.all(np.isfinite(traction)) or not np.all(np.isfinite(ell)):
            raise FloatingPointError("projected DtN vectors are non-finite")
        denominator = complex(self.denominator)
        if not np.isfinite(denominator) or abs(denominator) <= _TINY:
            raise ValueError("DtN projection denominator is invalid")
        incident = complex(self.incident_projection_solver)
        if not np.isfinite(incident):
            raise ValueError("DtN incident projection is non-finite")
        traction.setflags(write=False)
        ell.setflags(write=False)
        object.__setattr__(self, "auxiliary_global_index", index)
        object.__setattr__(self, "traction_high", traction)
        object.__setattr__(self, "ell_high", ell)
        object.__setattr__(self, "denominator", denominator)
        object.__setattr__(self, "incident_projection_solver", incident)
        object.__setattr__(
            self,
            "mode_identity",
            MappingProxyType(dict(self.mode_identity)),
        )


def build_projected_dtn_complement_mode(
    *,
    auxiliary_global_index: int,
    right_high_components: Sequence[np.ndarray],
    left_high_components: Sequence[np.ndarray],
    traction_components: Sequence[complex],
    electric_components: Sequence[complex],
    denominator: complex,
    incident_projection_solver: complex,
    mode_identity: Mapping[str, Any],
    full_p6_component_vectors_projected_live: bool,
    physical_condensation_used: bool,
) -> ProjectedDtnComplementMode:
    """Combine the two tangential component projections for one mode."""

    if (
        len(right_high_components) != 2
        or len(left_high_components) != 2
        or len(traction_components) != 2
        or len(electric_components) != 2
    ):
        raise ValueError("DtN complement mode requires two components")
    right = tuple(
        np.asarray(component, dtype=np.complex128)
        for component in right_high_components
    )
    left = tuple(
        np.asarray(component, dtype=np.complex128)
        for component in left_high_components
    )
    dimensions = {component.shape for component in (*right, *left)}
    if len(dimensions) != 1:
        raise ValueError("DtN projected component dimensions differ")
    traction = sum(
        complex(weight) * component
        for weight, component in zip(
            traction_components,
            right,
            strict=True,
        )
    )
    ell = sum(
        complex(weight) * component
        for weight, component in zip(
            electric_components,
            left,
            strict=True,
        )
    )
    return ProjectedDtnComplementMode(
        auxiliary_global_index=auxiliary_global_index,
        traction_high=traction,
        ell_high=ell,
        denominator=denominator,
        incident_projection_solver=incident_projection_solver,
        mode_identity=mode_identity,
        full_p6_component_vectors_projected_live=(
            full_p6_component_vectors_projected_live
        ),
        physical_condensation_used=physical_condensation_used,
    )


class ProjectedDtnComplementActions:
    """Action-only high/auxiliary coupling for the augmented DtN system."""

    def __init__(
        self,
        *,
        low_dimension: int,
        retained_trace_rows: int,
        high_dimension: int,
        modes: Sequence[ProjectedDtnComplementMode],
        evidence_class: EvidenceClass,
    ) -> None:
        _validate_evidence_class(evidence_class)
        self.low_dimension = int(low_dimension)
        self.retained_trace_rows = int(retained_trace_rows)
        self.high_dimension = int(high_dimension)
        selected_modes = tuple(modes)
        indices = [mode.auxiliary_global_index for mode in selected_modes]
        if len(indices) != len(set(indices)):
            raise RuntimeError("DtN auxiliary indices are duplicated")
        if any(
            index < self.retained_trace_rows
            or index >= self.low_dimension
            for index in indices
        ):
            raise RuntimeError(
                "DtN complement coupling does not target auxiliary rows"
            )
        if any(
            mode.traction_high.shape != (self.high_dimension,)
            or mode.ell_high.shape != (self.high_dimension,)
            for mode in selected_modes
        ):
            raise ValueError("DtN complement vector dimension differs")
        self.modes = selected_modes
        self.evidence_class = evidence_class
        self.audit = MappingProxyType(
            {
                "schema_version": (
                    "task035b.projected-dtn-complement-actions.v1"
                ),
                "status": "action_only_projected_dtn_coupling_ready",
                "pass": True,
                "evidence_class": evidence_class,
                "mode_count": len(selected_modes),
                "coupling_semantics": (
                    "A_Haux=-traction_H; "
                    "A_auxH=-conj(ell_H)/denominator"
                ),
                "full_p6_component_vectors_projected_live": all(
                    mode.full_p6_component_vectors_projected_live
                    for mode in selected_modes
                ),
                "global_full_p6_matrix_materialized": False,
                "inactive_missing_p6_rows_allocated": 0,
                "ordinary_default_changed": False,
            }
        )

    def a_hh(self, vector: np.ndarray) -> np.ndarray:
        _readonly_vector(
            vector,
            dimension=self.high_dimension,
            label="DtN A_HH input",
        )
        return np.zeros(self.high_dimension, dtype=np.complex128)

    a_hh_adjoint = a_hh

    def a_hl(self, vector: np.ndarray) -> np.ndarray:
        low = _readonly_vector(
            vector,
            dimension=self.low_dimension,
            label="DtN A_HL input",
        )
        result = np.zeros(self.high_dimension, dtype=np.complex128)
        for mode in self.modes:
            result -= (
                mode.traction_high
                * low[mode.auxiliary_global_index]
            )
        return result

    def a_hl_adjoint(self, vector: np.ndarray) -> np.ndarray:
        high = _readonly_vector(
            vector,
            dimension=self.high_dimension,
            label="DtN A_HL adjoint input",
        )
        result = np.zeros(self.low_dimension, dtype=np.complex128)
        for mode in self.modes:
            result[mode.auxiliary_global_index] -= np.vdot(
                mode.traction_high,
                high,
            )
        return result

    def a_lh(self, vector: np.ndarray) -> np.ndarray:
        high = _readonly_vector(
            vector,
            dimension=self.high_dimension,
            label="DtN A_LH input",
        )
        result = np.zeros(self.low_dimension, dtype=np.complex128)
        for mode in self.modes:
            result[mode.auxiliary_global_index] -= (
                np.vdot(mode.ell_high, high) / mode.denominator
            )
        return result

    def a_lh_adjoint(self, vector: np.ndarray) -> np.ndarray:
        low = _readonly_vector(
            vector,
            dimension=self.low_dimension,
            label="DtN A_LH adjoint input",
        )
        result = np.zeros(self.high_dimension, dtype=np.complex128)
        for mode in self.modes:
            result -= (
                mode.ell_high
                / np.conj(mode.denominator)
                * low[mode.auxiliary_global_index]
            )
        return result

    def missing_incident_right_hand_side(self) -> np.ndarray:
        """Return only the augmented-DtN incident contribution to ``b_H``."""

        result = np.zeros(self.high_dimension, dtype=np.complex128)
        for mode in self.modes:
            result -= (
                mode.traction_high
                * mode.incident_projection_solver
            )
        result.setflags(write=False)
        return result


class PhysicalMissingP6ComplementActions:
    """Sum the streamed Maxwell and projected augmented-DtN actions."""

    def __init__(
        self,
        *,
        maxwell: PhysicalMissingP6MaxwellActions,
        dtn: ProjectedDtnComplementActions,
    ) -> None:
        if (
            maxwell.layout.low_dimension != dtn.low_dimension
            or maxwell.layout.high_dimension != dtn.high_dimension
            or maxwell.layout.retained_trace_rows
            != dtn.retained_trace_rows
        ):
            raise RuntimeError("Maxwell and DtN complement dimensions differ")
        if maxwell.evidence_class != dtn.evidence_class:
            raise RuntimeError("Maxwell and DtN evidence classes differ")
        self.maxwell = maxwell
        self.dtn = dtn
        self.low_dimension = dtn.low_dimension
        self.high_dimension = dtn.high_dimension
        self.evidence_class = dtn.evidence_class
        self.audit = MappingProxyType(
            {
                "schema_version": (
                    "task035b.physical-missing-p6-composite-actions.v1"
                ),
                "status": "physical_action_only_complement_ready",
                "pass": True,
                "evidence_class": self.evidence_class,
                "maxwell_local_schur_streamed": True,
                "augmented_dtn_mode_coupling_streamed": True,
                "global_full_p6_matrix_materialized": False,
                "inactive_missing_p6_rows_allocated": 0,
                "ordinary_default_changed": False,
            }
        )

    def a_hh(self, vector: np.ndarray) -> np.ndarray:
        return self.maxwell.a_hh(vector) + self.dtn.a_hh(vector)

    def a_hh_adjoint(self, vector: np.ndarray) -> np.ndarray:
        return self.maxwell.a_hh_adjoint(
            vector
        ) + self.dtn.a_hh_adjoint(vector)

    def a_hl(self, vector: np.ndarray) -> np.ndarray:
        return self.maxwell.a_hl(vector) + self.dtn.a_hl(vector)

    def a_hl_adjoint(self, vector: np.ndarray) -> np.ndarray:
        return self.maxwell.a_hl_adjoint(
            vector
        ) + self.dtn.a_hl_adjoint(vector)

    def a_lh(self, vector: np.ndarray) -> np.ndarray:
        return self.maxwell.a_lh(vector) + self.dtn.a_lh(vector)

    def a_lh_adjoint(self, vector: np.ndarray) -> np.ndarray:
        return self.maxwell.a_lh_adjoint(
            vector
        ) + self.dtn.a_lh_adjoint(vector)


class ReplicatedPetscLowFactorSolve:
    """Reuse one live PETSc ``A_LL`` factor from replicated NumPy vectors."""

    def __init__(
        self,
        *,
        matrix: PETSc.Mat,
        solver: PETSc.KSP,
        explicit_relative_residual_tolerance: float = 1.0e-10,
        evidence_class: EvidenceClass,
    ) -> None:
        rows, columns = map(int, matrix.getSize())
        if rows <= 0 or rows != columns:
            raise ValueError("retained PETSc matrix must be nonempty and square")
        tolerance = float(explicit_relative_residual_tolerance)
        if not np.isfinite(tolerance) or tolerance <= 0.0:
            raise ValueError("low solve residual tolerance must be positive")
        _validate_evidence_class(evidence_class)
        self.matrix = matrix
        self.solver = solver
        self.dimension = rows
        self.tolerance = tolerance
        self.evidence_class = evidence_class
        self.communicator = matrix.getComm().tompi4py()
        self._reports: list[Mapping[str, Any]] = []
        self.audit = MappingProxyType(
            {
                "schema_version": (
                    "task035b.replicated-petsc-low-factor-solve.v1"
                ),
                "status": "caller_owned_low_factor_adapter_ready",
                "pass": True,
                "evidence_class": evidence_class,
                "dimension": rows,
                "forward_factor_owned_by_caller": True,
                "new_matrix_created": False,
                "new_factor_created": False,
                "Hermitian_solve": (
                    "conj(KSPSolveTranspose(conj(rhs)))"
                ),
            }
        )

    def _distributed_vector(self, values: np.ndarray) -> PETSc.Vec:
        vector = self.matrix.createVecRight()
        start, end = map(int, vector.getOwnershipRange())
        vector.getArray()[:] = values[start:end]
        vector.assemble()
        return vector

    def _replicated_array(self, vector: PETSc.Vec) -> np.ndarray:
        start, end = map(int, vector.getOwnershipRange())
        packets = self.communicator.allgather(
            (
                start,
                end,
                np.asarray(
                    vector.getArray(readonly=True),
                    dtype=np.complex128,
                ).copy(),
            )
        )
        result = np.empty(self.dimension, dtype=np.complex128)
        coverage: set[int] = set()
        for packet_start, packet_end, values in packets:
            indices = set(range(int(packet_start), int(packet_end)))
            if coverage & indices:
                raise RuntimeError("PETSc low vector ownership overlaps")
            coverage.update(indices)
            result[int(packet_start) : int(packet_end)] = values
        if coverage != set(range(self.dimension)):
            raise RuntimeError("PETSc low vector ownership does not close")
        result.setflags(write=False)
        return result

    def _solve(self, right_hand_side: np.ndarray, *, adjoint: bool) -> np.ndarray:
        rhs_array = _readonly_vector(
            right_hand_side,
            dimension=self.dimension,
            label="A_LL right-hand side",
        )
        rhs = self._distributed_vector(
            np.conj(rhs_array) if adjoint else rhs_array
        )
        raw_solution = self.matrix.createVecRight()
        if adjoint:
            self.solver.solveTranspose(rhs, raw_solution)
            solution = raw_solution.copy()
            solution.getArray()[:] = np.conj(
                raw_solution.getArray(readonly=True)
            )
        else:
            self.solver.solve(rhs, raw_solution)
            solution = raw_solution
        reason = int(self.solver.getConvergedReason())
        actual = rhs.duplicate()
        if adjoint:
            original_rhs = self._distributed_vector(rhs_array)
            self.matrix.multHermitian(solution, actual)
            actual.axpy(PETSc.ScalarType(-1.0), original_rhs)
            denominator = float(original_rhs.norm())
            original_rhs.destroy()
        else:
            self.matrix.mult(solution, actual)
            actual.axpy(PETSc.ScalarType(-1.0), rhs)
            denominator = float(rhs.norm())
        residual = float(actual.norm()) / max(denominator, _TINY)
        if reason <= 0 or residual > self.tolerance:
            if solution is not raw_solution:
                solution.destroy()
            raw_solution.destroy()
            rhs.destroy()
            actual.destroy()
            raise RuntimeError(
                "caller-owned A_LL factor solve failed: "
                f"reason={reason}, residual={residual:.6e}, "
                f"tolerance={self.tolerance:.6e}"
            )
        replicated = self._replicated_array(solution)
        self._reports.append(
            MappingProxyType(
                {
                    "adjoint": adjoint,
                    "converged_reason": reason,
                    "explicit_relative_residual": residual,
                    "pass": True,
                }
            )
        )
        if solution is not raw_solution:
            solution.destroy()
        raw_solution.destroy()
        rhs.destroy()
        actual.destroy()
        return replicated

    def solve(self, right_hand_side: np.ndarray) -> np.ndarray:
        return self._solve(right_hand_side, adjoint=False)

    def solve_adjoint(self, right_hand_side: np.ndarray) -> np.ndarray:
        return self._solve(right_hand_side, adjoint=True)

    @property
    def reports(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(self._reports)


@dataclass(frozen=True)
class ActionOnlyGMRESReport:
    """Explicit convergence evidence for one complement inverse action."""

    adjoint: bool
    info: int
    iterations: int
    residual_history: tuple[float, ...]
    explicit_relative_residual: float
    tolerance: float
    pass_gate: bool


class PhysicalMissingP6ActionOnlyComplementSystem:
    """Action-only ``S_H`` plus independently checked GMRES inverses."""

    def __init__(
        self,
        *,
        actions: PhysicalMissingP6ComplementActions,
        low_solve: VectorAction,
        low_adjoint_solve: VectorAction,
        gmres_relative_tolerance: float = 1.0e-11,
        explicit_relative_residual_tolerance: float = 2.0e-10,
        gmres_restart: int = 40,
        gmres_maximum_cycles: int = 100,
        preconditioner: VectorAction | None = None,
        adjoint_preconditioner: VectorAction | None = None,
    ) -> None:
        for callback, label in (
            (low_solve, "low solve"),
            (low_adjoint_solve, "low adjoint solve"),
        ):
            if not callable(callback):
                raise TypeError(f"{label} must be callable")
        rtol = float(gmres_relative_tolerance)
        residual_tolerance = float(explicit_relative_residual_tolerance)
        if (
            not np.isfinite(rtol)
            or rtol <= 0.0
            or not np.isfinite(residual_tolerance)
            or residual_tolerance <= 0.0
        ):
            raise ValueError("GMRES tolerances must be positive")
        self.actions = actions
        self.low_solve = low_solve
        self.low_adjoint_solve = low_adjoint_solve
        self.rtol = rtol
        self.residual_tolerance = residual_tolerance
        self.restart = min(
            int(gmres_restart),
            actions.high_dimension,
        )
        self.maximum_cycles = int(gmres_maximum_cycles)
        if self.restart <= 0 or self.maximum_cycles <= 0:
            raise ValueError("GMRES restart/cycle limits must be positive")
        self.preconditioner = preconditioner
        self.adjoint_preconditioner = adjoint_preconditioner
        self._reports: list[ActionOnlyGMRESReport] = []
        self.audit = MappingProxyType(
            {
                "schema_version": (
                    "task035b.action-only-missing-p6-complement-system.v1"
                ),
                "status": "action_only_complement_gmres_ready",
                "pass": True,
                "evidence_class": actions.evidence_class,
                "low_factor_reused": True,
                "Schur_matrix_materialized": False,
                "LinearOperator_column_probing": False,
                "global_full_p6_matrix_materialized": False,
                "inactive_missing_p6_rows_allocated": 0,
                "ordinary_default_changed": False,
            }
        )

    def schur_action(self, vector: np.ndarray) -> np.ndarray:
        high = _readonly_vector(
            vector,
            dimension=self.actions.high_dimension,
            label="Schur input",
        )
        return (
            self.actions.a_hh(high)
            - self.actions.a_hl(
                self.low_solve(self.actions.a_lh(high))
            )
        )

    def schur_adjoint_action(self, vector: np.ndarray) -> np.ndarray:
        high = _readonly_vector(
            vector,
            dimension=self.actions.high_dimension,
            label="adjoint Schur input",
        )
        return (
            self.actions.a_hh_adjoint(high)
            - self.actions.a_lh_adjoint(
                self.low_adjoint_solve(
                    self.actions.a_hl_adjoint(high)
                )
            )
        )

    def _gmres(
        self,
        right_hand_side: np.ndarray,
        *,
        adjoint: bool,
    ) -> np.ndarray:
        dimension = self.actions.high_dimension
        rhs = _readonly_vector(
            right_hand_side,
            dimension=dimension,
            label="complement GMRES right-hand side",
        )
        action = (
            self.schur_adjoint_action if adjoint else self.schur_action
        )
        operator = LinearOperator(
            (dimension, dimension),
            matvec=action,
            rmatvec=(
                self.schur_action
                if adjoint
                else self.schur_adjoint_action
            ),
            dtype=np.complex128,
        )
        preconditioner_action = (
            self.adjoint_preconditioner
            if adjoint
            else self.preconditioner
        )
        preconditioner = (
            None
            if preconditioner_action is None
            else LinearOperator(
                (dimension, dimension),
                matvec=preconditioner_action,
                dtype=np.complex128,
            )
        )
        history: list[float] = []
        gmres_keywords: dict[str, Any] = {
            "M": preconditioner,
            "restart": self.restart,
            "maxiter": self.maximum_cycles,
            "atol": 0.0,
            "callback": lambda value: history.append(float(value)),
            "callback_type": "pr_norm",
        }
        tolerance_keyword = (
            "rtol" if "rtol" in signature(gmres).parameters else "tol"
        )
        gmres_keywords[tolerance_keyword] = self.rtol
        solution, info = gmres(operator, rhs, **gmres_keywords)
        solution = np.asarray(solution, dtype=np.complex128)
        residual = float(np.linalg.norm(action(solution) - rhs)) / max(
            float(np.linalg.norm(rhs)),
            _TINY,
        )
        passed = bool(int(info) == 0 and residual <= self.residual_tolerance)
        report = ActionOnlyGMRESReport(
            adjoint=adjoint,
            info=int(info),
            iterations=len(history),
            residual_history=tuple(history),
            explicit_relative_residual=residual,
            tolerance=self.residual_tolerance,
            pass_gate=passed,
        )
        self._reports.append(report)
        if not passed:
            raise RuntimeError(
                "action-only complement GMRES failed: "
                f"adjoint={adjoint}, info={info}, residual={residual:.6e}, "
                f"tolerance={self.residual_tolerance:.6e}"
            )
        solution.setflags(write=False)
        return solution

    def solve(self, right_hand_side: np.ndarray) -> np.ndarray:
        return self._gmres(right_hand_side, adjoint=False)

    def solve_adjoint(self, right_hand_side: np.ndarray) -> np.ndarray:
        return self._gmres(right_hand_side, adjoint=True)

    def complement_operator(self) -> ComplementSchurOperator:
        """Return the existing DWR kernel adapter over these actions."""

        return ComplementSchurOperator(
            low_dimension=self.actions.low_dimension,
            high_dimension=self.actions.high_dimension,
            a_hh=self.actions.a_hh,
            a_hl=self.actions.a_hl,
            a_lh=self.actions.a_lh,
            a_ll_solve=self.low_solve,
            a_ll_adjoint_solve=self.low_adjoint_solve,
            schur_solve=self.solve,
            schur_adjoint_solve=self.solve_adjoint,
            a_hh_adjoint_action=self.actions.a_hh_adjoint,
            a_hl_adjoint_action=self.actions.a_hl_adjoint,
            a_lh_adjoint_action=self.actions.a_lh_adjoint,
            solve_tolerance=self.residual_tolerance,
        )

    @property
    def reports(self) -> tuple[ActionOnlyGMRESReport, ...]:
        return tuple(self._reports)


@dataclass(frozen=True)
class ActualFocusChannelGoalBundle:
    """Nine independent Review-V2 channel goals in retained coordinates."""

    goals: tuple[ChannelGoal, ...]
    audit: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.audit.get("pass") is not True:
            raise ValueError("focus channel goal bundle is unqualified")


def build_actual_focus_channel_goal_bundle(
    *,
    goal_reports: Mapping[str, Mapping[str, Any]],
    retained_adjoints: Mapping[str, np.ndarray],
    tolerances: Mapping[str, float],
    baseline_signed_errors: Mapping[str, float],
    retained_trace_rows: int,
    low_dimension: int,
    high_dimension: int,
    evidence_class: EvidenceClass,
) -> ActualFocusChannelGoalBundle:
    """Bind actual auxiliary-only gradients and retained Hermitian adjoints.

    The official single-channel power, real-amplitude, and imaginary-amplitude
    functionals are stored on one existing DtN auxiliary coordinate.  Their
    direct derivative with respect to a missing trace coordinate is therefore
    exactly zero.  Their complement gradient is *not* zero:
    ``q_H = -A_LH^H z_L``.
    """

    _validate_evidence_class(evidence_class)
    expected_labels = {label for label, _component, _quantity in _FOCUS_SPECS}
    for supplied, name in (
        (set(retained_adjoints), "retained adjoints"),
        (set(tolerances), "tolerances"),
        (set(baseline_signed_errors), "baseline signed errors"),
    ):
        if supplied != expected_labels:
            raise RuntimeError(
                f"{name} must cover exactly the nine focus goals"
            )
    if not expected_labels.issubset(goal_reports):
        raise RuntimeError("actual adjoint reports lack a focus channel")

    goals: list[ChannelGoal] = []
    for label, component, quantity in _FOCUS_SPECS:
        report = goal_reports[label]
        metadata = report.get("goal")
        if not isinstance(metadata, Mapping):
            raise RuntimeError(f"{label} lacks canonical goal metadata")
        expected_prefix = "T" if label.startswith("T_") else "R"
        expected_m = -5 if "_m-5_" in label else -4
        expected_side = "bottom" if expected_prefix == "T" else "top"
        if (
            metadata.get("label") != label
            or metadata.get("side") != expected_side
            or int(metadata.get("m", 10**9)) != expected_m
            or int(metadata.get("n", 10**9)) != 0
            or metadata.get("polarization") != "s"
            or metadata.get("quantity") != quantity
        ):
            raise RuntimeError(f"{label} canonical channel identity differs")
        auxiliary_index = report.get("augmented_global_index")
        if (
            isinstance(auxiliary_index, bool)
            or not isinstance(auxiliary_index, Integral)
            or int(auxiliary_index) < int(retained_trace_rows)
            or int(auxiliary_index) >= int(low_dimension)
        ):
            raise RuntimeError(f"{label} gradient is not auxiliary-only")
        convention = str(report.get("gradient_convention", ""))
        convention_token = {
            "power": "g_aux=2*w*outgoing_amplitude",
            "amplitude_real": "g_aux=conj(boundary_phase)",
            "amplitude_imag": "g_aux=i*conj(boundary_phase)",
        }[quantity]
        adjoint_residual = report.get("adjoint_residual", {})
        if (
            report.get("pass") is not True
            or report.get("actual_discrete_system") is not True
            or int(report.get("matrix_rows", -1)) != int(low_dimension)
            or convention_token not in convention
            or not isinstance(adjoint_residual, Mapping)
            or float(adjoint_residual.get("relative_residual", np.inf))
            > 1.0e-9
        ):
            raise RuntimeError(f"{label} actual retained adjoint is unqualified")
        retained = _readonly_vector(
            retained_adjoints[label],
            dimension=low_dimension,
            label=f"{label} retained adjoint",
        )
        goals.append(
            ChannelGoal(
                label=label,
                component=component,
                tolerance=float(tolerances[label]),
                missing_gradient=np.zeros(
                    high_dimension,
                    dtype=np.complex128,
                ),
                retained_adjoint=retained,
                actual_channel_gradient=True,
                retained_adjoint_qualified=True,
                selection_target=True,
                protected=False,
                baseline_signed_error=float(
                    baseline_signed_errors[label]
                ),
            )
        )

    bundle_audit = MappingProxyType(
        {
            "schema_version": (
                "task035b.actual-focus-channel-complement-goals.v1"
            ),
            "status": "nine_focus_channel_goal_bundle_pass",
            "pass": True,
            "evidence_class": evidence_class,
            "formal_actual_pde": evidence_class == "actual_pde",
            "goal_count": len(goals),
            "independent_power_goal_count": 3,
            "independent_amplitude_real_goal_count": 3,
            "independent_amplitude_imag_goal_count": 3,
            "direct_missing_gradient": (
                "zero_by_official_auxiliary_only_support"
            ),
            "complement_gradient": "q_H=-A_LH^H*z_L",
            "complex_functional_convention": "dJ=Re(g^H dx)",
            "all_retained_adjoint_residuals_le_1e-9": True,
            "full_p6_trace_matrix_materialized": False,
            "inactive_missing_p6_rows_allocated": 0,
            "ordinary_default_changed": False,
        }
    )
    return ActualFocusChannelGoalBundle(
        goals=tuple(goals),
        audit=bundle_audit,
    )


def formal_h14_action_only_hook_requirements() -> Mapping[str, Any]:
    """Return the fail-closed capabilities still required by the formal lane."""

    return MappingProxyType(
        {
            "schema_version": (
                "task035b.formal-h14-action-only-hook-requirements.v2"
            ),
            "status": (
                "analytic_action_kernel_ready_actual_pde_capabilities_missing"
            ),
            "formal_actual_pde_ready": False,
            "actual_pde_evidence_class_enabled": False,
            "required_live_hooks": [
                {
                    "module": (
                        "src.solvers.hcurl_assembly_time_condensation"
                    ),
                    "function": "full_p6_storage_local_schur_capture",
                    "payload": (
                        "standard-p6 local_cell, oriented class_key and "
                        "432x432 storage-trace Schur; the existing fixed-"
                        "p5-trace 300x300 Schur is insufficient"
                    ),
                    "consumer": "FullP6LocalSchurClassCollector.observe",
                },
                {
                    "module": "src.adaptivity",
                    "function": (
                        "build_actual_physical_discrete_gradient_authority"
                    ),
                    "payload": (
                        "same-mesh Q5-to-Q6 interpolation, Q6-to-N1curl-p6 "
                        "discrete gradient, scalar pullbacks, SVD ranks, "
                        "commuting errors and content hashes"
                    ),
                },
                {
                    "module": "src.solvers.dtn_port_3d",
                    "function": "full_p6_dtn_mode_capture",
                    "payload": (
                        "all live full-p6 right/left surface projections, "
                        "complete auxiliary inventory, phase/mode identity, "
                        "traction/electric weights and denominators"
                    ),
                },
                {
                    "module": "src.solvers.dtn_port_3d",
                    "function": "full_enriched_rhs_projection",
                    "payload": (
                        "C_H^H applied to the complete assembly-time full "
                        "right-hand side, including direct incident traction"
                    ),
                },
                {
                    "module": (
                        "src.solvers.hcurl_assembly_time_condensation"
                    ),
                    "function": "generalized_caller_expansion_recovery",
                    "payload": (
                        "u_storage=Cq primal recovery, generalized true "
                        "residual and no duplicate MPC backsubstitution"
                    ),
                },
                {
                    "module": "src.adaptivity",
                    "function": "content_bound_actual_capture_provenance",
                    "payload": (
                        "source, mesh, geometry, operator, basis, expansion, "
                        "factor, mode inventory and live payload hashes"
                    ),
                },
                {
                    "module": "src.adaptivity",
                    "function": "protected_significant_channel_goals",
                    "payload": (
                        "three focus channels plus the full 12-channel "
                        "non-regression protection audit"
                    ),
                },
            ],
            "old_h14_offline_reconstruction_authorized": False,
            "reason_old_h14_is_insufficient": (
                "the retained 300-trace system lacks the 432-trace full-p6 "
                "couplings, full-p6 port vectors, complete b_H and actual "
                "same-mesh discrete-gradient authority"
            ),
            "formal_run_must_start_from_fixed_p5_trace_p6_interior_h14": True,
            "full_p6_trace_matrix_materialized": False,
            "inactive_missing_p6_rows_allocated": 0,
            "ordinary_default_changed": False,
        }
    )


__all__ = [
    "ActionOnlyGMRESReport",
    "ActualFocusChannelGoalBundle",
    "FullP6LocalSchurClassCollector",
    "PhysicalCellComplementActionLayout",
    "PhysicalMissingP6ActionLayout",
    "PhysicalMissingP6ActionOnlyComplementSystem",
    "PhysicalMissingP6ComplementActions",
    "PhysicalMissingP6MaxwellActions",
    "PhysicalStorageTraceDualProjection",
    "ProjectedCondensedDual",
    "ProjectedDtnComplementActions",
    "ProjectedDtnComplementMode",
    "ReplicatedPetscLowFactorSolve",
    "build_actual_focus_channel_goal_bundle",
    "build_physical_missing_p6_action_layout",
    "build_projected_dtn_complement_mode",
    "formal_h14_action_only_hook_requirements",
    "project_full_p6_condensed_trace_dual",
]
