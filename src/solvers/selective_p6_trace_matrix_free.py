"""Correctness-only owner-aware MatShell for selected-p6 trace actions.

The shell applies

``sum_K C_K^H S_K C_K``

directly from the qualified physical selected-p6 trace expansion.  ``S_K`` is
stored once per rank-local oriented tensor class; the full selected matrix,
an LU factor, and a replicated active vector are never constructed.

Only the active coordinates admitted by the exact-sequence-closed selection
exist.  Input values required by an owned cell are imported with a PETSc ghost
forward scatter and off-rank cell contributions are returned to their owners
with the matching reverse scatter.  Full-vector ``Allreduce``/``allgather`` is
deliberately absent from the action.

This module is an execution-disabled correctness capability.  It is not wired
to a solver profile and its audit always reports
``production_execution_enabled=False``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from types import MappingProxyType
from typing import Any, Hashable, Mapping

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc

from src.adaptivity.selective_p6_trace_exact_sequence import (
    ExactSequenceClosedP6TraceNumbering,
)
from src.constraints.selective_p6_trace_3d import (
    canonical_selective_p6_trace_selection_sha256,
)
from src.constraints.selective_p6_trace_expansion import (
    ActualSelectiveP6TraceExpansion,
)


def _validated_sha256(value: Any, *, label: str) -> str:
    normalized = str(value).lower()
    try:
        valid = len(normalized) == 64 and len(bytes.fromhex(normalized)) == 32
    except ValueError:
        valid = False
    if not valid:
        raise ValueError(f"{label} must contain 64 hexadecimal characters")
    return normalized


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


def _collective_errors(
    communicator: MPI.Intracomm,
    *,
    phase: str,
    local_error: str | None,
) -> None:
    """Raise the same error on every rank before later collectives begin."""

    errors = communicator.allgather(local_error)
    if any(error is not None for error in errors):
        details = "; ".join(
            f"rank {rank}: {error}"
            for rank, error in enumerate(errors)
            if error is not None
        )
        raise RuntimeError(f"collective {phase} validation failed: {details}")


def _exact_selected_logical_modes(
    selection: ExactSequenceClosedP6TraceNumbering,
) -> tuple[tuple[int, int], ...]:
    return tuple(
        (int(orbit.representative_entity_id), mode)
        for orbit in sorted(
            (orbit for orbit in selection.numbering.orbits if orbit.selected),
            key=lambda orbit: orbit.representative_entity_id,
        )
        for mode in range(int(orbit.missing_mode_count))
    )


@dataclass(frozen=True)
class _RankLocalCellAction:
    local_cell: int
    local_coordinate_positions: np.ndarray
    coefficient_matrix: np.ndarray
    class_key: Hashable


@dataclass(frozen=True)
class OwnerAwareSelectedP6TraceGhostPlan:
    """Rank-local ownership and ghost coordinates for the selected action."""

    active_rows: int
    ownership_start: int
    ownership_stop: int
    ghost_rows: np.ndarray
    local_global_rows: np.ndarray
    cell_actions: tuple[_RankLocalCellAction, ...]
    geometry_sha256: str
    ordered_trace_basis_sha256: str
    selection_sha256: str
    identity_sha256: str
    audit: Mapping[str, Any]

    def __post_init__(self) -> None:
        ghosts = np.asarray(self.ghost_rows, dtype=PETSc.IntType).copy()
        local_rows = np.asarray(
            self.local_global_rows,
            dtype=PETSc.IntType,
        ).copy()
        ghosts.setflags(write=False)
        local_rows.setflags(write=False)
        object.__setattr__(self, "ghost_rows", ghosts)
        object.__setattr__(self, "local_global_rows", local_rows)
        object.__setattr__(
            self,
            "audit",
            MappingProxyType(dict(self.audit)),
        )

    @property
    def owned_rows(self) -> int:
        return self.ownership_stop - self.ownership_start

    @property
    def local_coordinate_slots(self) -> int:
        return self.owned_rows + len(self.ghost_rows)


def _build_plan_and_classes(
    *,
    expansion: ActualSelectiveP6TraceExpansion,
    exact_sequence_selection: ExactSequenceClosedP6TraceNumbering,
    storage_schur_by_class: Mapping[Hashable, np.ndarray],
    cell_class_keys: Mapping[int, Hashable],
    communicator: MPI.Intracomm,
) -> tuple[
    OwnerAwareSelectedP6TraceGhostPlan,
    Mapping[Hashable, np.ndarray],
]:
    local_error: str | None = None
    normalized_owned = np.empty(0, dtype=PETSc.IntType)
    normalized_classes: dict[Hashable, np.ndarray] = {}
    geometry_hash = ""
    basis_hash = ""
    selection_hash = ""
    expected_selection_hash = ""
    active_rows = 0
    selected_modes: tuple[tuple[int, int], ...] = ()
    selected_modes_sha256 = ""
    try:
        if not isinstance(expansion, ActualSelectiveP6TraceExpansion):
            raise TypeError("expansion must be ActualSelectiveP6TraceExpansion")
        if not isinstance(
            exact_sequence_selection,
            ExactSequenceClosedP6TraceNumbering,
        ):
            raise TypeError(
                "exact_sequence_selection must be ExactSequenceClosedP6TraceNumbering"
            )
        if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
            raise TypeError("selected-p6 trace MatShell requires complex128")

        for label, audit in (
            ("expansion", expansion.audit),
            ("exact-sequence selection", exact_sequence_selection.audit),
            ("exact-sequence closure", exact_sequence_selection.closure.audit),
            (
                "exact-sequence numbering",
                exact_sequence_selection.numbering.audit,
            ),
        ):
            if audit.get("pass") is not True:
                raise RuntimeError(f"{label} is not qualified")
        caller_audit = expansion.caller_trace_expansion.qualification_audit
        if caller_audit.get("pass") is not True:
            raise RuntimeError("caller trace expansion is not qualified")
        if expansion.audit.get("matrix_constructed") is not False:
            raise RuntimeError(
                "selected-p6 expansion was already inserted into a matrix"
            )
        if caller_audit.get("full_trace_matrix_constructed") is not False:
            raise RuntimeError("full-p6 trace matrix materialization is forbidden")
        if expansion.audit.get("inactive_missing_petsc_rows") != 0:
            raise RuntimeError("inactive missing-p6 modes have PETSc rows")
        if exact_sequence_selection.audit.get("inactive_p6_rows_numbered") is not False:
            raise RuntimeError("exact-sequence selection numbered inactive p6 rows")

        geometry_hash = _validated_sha256(
            expansion.audit.get("trace_geometry_sha256"),
            label="trace geometry SHA256",
        )
        basis_hash = _validated_sha256(
            expansion.audit.get("ordered_trace_basis_sha256"),
            label="ordered trace basis SHA256",
        )
        selection_hash = _validated_sha256(
            expansion.audit.get("selection_sha256"),
            label="selection SHA256",
        )
        expected_selection_hash = canonical_selective_p6_trace_selection_sha256(
            closed_numbering=exact_sequence_selection,
            geometry_key_sha256=geometry_hash,
            ordered_trace_basis_sha256=basis_hash,
        )
        if selection_hash != expected_selection_hash:
            raise RuntimeError(
                "expansion selection SHA256 is stale or differs from the "
                "exact-sequence selection"
            )

        active_rows = int(expansion.active_rows)
        numbering = exact_sequence_selection.numbering
        closure = exact_sequence_selection.closure
        if active_rows != int(numbering.active_rows):
            raise RuntimeError(
                "expansion active rows differ from exact-sequence numbering"
            )
        if expansion.p5_periodic_quotient_rows != int(numbering.active_base_rows):
            raise RuntimeError("p5 quotient rows differ from exact-sequence numbering")
        if expansion.selected_missing_rows != int(closure.active_row_increment):
            raise RuntimeError(
                "selected missing rows differ from exact-sequence closure"
            )
        selected_modes = _exact_selected_logical_modes(exact_sequence_selection)
        selected_modes_sha256 = hashlib.sha256(
            json.dumps(
                selected_modes,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        if set(expansion.selected_missing_logical_rows) != set(selected_modes):
            raise RuntimeError(
                "physical selected rows differ from the exact-sequence "
                "whole-orbit selection"
            )
        base_rows = set(map(int, expansion.base_logical_rows.values()))
        missing_rows = set(map(int, expansion.selected_missing_logical_rows.values()))
        if base_rows & missing_rows:
            raise RuntimeError("base and selected missing coordinates overlap")
        if base_rows | missing_rows != set(range(active_rows)):
            raise RuntimeError(
                "active coordinates are not exactly base plus selected rows"
            )

        raw_owned = np.asarray(expansion.caller_trace_expansion.owned_active_rows)
        if raw_owned.ndim != 1 or not np.issubdtype(
            raw_owned.dtype,
            np.integer,
        ):
            raise TypeError("owned active rows must be an integer vector")
        normalized_owned = np.asarray(
            raw_owned,
            dtype=PETSc.IntType,
        ).copy()
        if len(np.unique(normalized_owned)) != len(normalized_owned):
            raise RuntimeError("owned active rows contain duplicates")
        if len(normalized_owned) and (
            int(normalized_owned[0]) < 0
            or int(normalized_owned[-1]) >= active_rows
            or np.any(np.diff(normalized_owned.astype(np.int64)) != 1)
        ):
            raise RuntimeError(
                "owned active rows are not one contiguous in-range block"
            )

        cells = {int(cell.local_cell): cell for cell in expansion.owned_cell_expansions}
        if len(cells) != len(expansion.owned_cell_expansions):
            raise RuntimeError("owned cell expansions contain duplicate ids")
        classes = {int(cell): key for cell, key in cell_class_keys.items()}
        if set(classes) != set(cells):
            raise RuntimeError("cell class map must cover exactly every owned cell")
        used_classes = set(classes.values())
        if used_classes != set(storage_schur_by_class):
            raise RuntimeError(
                "local Schur cache must contain exactly the used classes"
            )
        class_dimensions: dict[Hashable, int] = {}
        for local_cell, cell in cells.items():
            rows = np.asarray(cell.active_rows, dtype=np.int64)
            if len(rows) and (int(rows.min()) < 0 or int(rows.max()) >= active_rows):
                raise RuntimeError(
                    f"cell {local_cell} references an inactive coordinate"
                )
            class_key = classes[local_cell]
            dimension = len(cell.storage_original_dofs)
            previous = class_dimensions.setdefault(class_key, dimension)
            if previous != dimension:
                raise RuntimeError(
                    "one local Schur class has inconsistent storage sizes"
                )
        for class_key, dimension in class_dimensions.items():
            normalized_classes[class_key] = _readonly_matrix(
                storage_schur_by_class[class_key],
                shape=(dimension, dimension),
                label=f"local Schur class {class_key!r}",
            )
    except Exception as error:
        local_error = f"{type(error).__name__}: {error}"

    _collective_errors(
        communicator,
        phase="identity",
        local_error=local_error,
    )

    identity = (
        geometry_hash,
        basis_hash,
        selection_hash,
        expected_selection_hash,
        active_rows,
        int(expansion.p5_periodic_quotient_rows),
        int(expansion.selected_missing_rows),
        selected_modes_sha256,
    )
    identities = communicator.allgather(identity)
    if any(packet != identities[0] for packet in identities[1:]):
        raise RuntimeError(
            "collective identity validation failed: ranks supplied different "
            "selected-p6 trace authorities"
        )

    owned_counts = communicator.allgather(len(normalized_owned))
    ownership_start = int(sum(owned_counts[: communicator.rank]))
    ownership_stop = ownership_start + len(normalized_owned)
    ownership_error: str | None = None
    if not np.array_equal(
        normalized_owned.astype(np.int64, copy=False),
        np.arange(ownership_start, ownership_stop, dtype=np.int64),
    ):
        ownership_error = (
            "owned rows differ from the communicator-contiguous PETSc range"
        )
    elif sum(owned_counts) != active_rows:
        ownership_error = "owned row counts do not close global active rows"
    _collective_errors(
        communicator,
        phase="ownership",
        local_error=ownership_error,
    )

    cells = {int(cell.local_cell): cell for cell in expansion.owned_cell_expansions}
    classes = {int(cell): key for cell, key in cell_class_keys.items()}
    needed_rows = {int(row) for cell in cells.values() for row in cell.active_rows}
    ghost_rows = np.asarray(
        sorted(
            row for row in needed_rows if row < ownership_start or row >= ownership_stop
        ),
        dtype=PETSc.IntType,
    )
    local_global_rows = np.concatenate(
        (
            np.arange(
                ownership_start,
                ownership_stop,
                dtype=PETSc.IntType,
            ),
            ghost_rows,
        )
    )
    global_to_local = {
        int(row): position for position, row in enumerate(local_global_rows)
    }
    cell_actions: list[_RankLocalCellAction] = []
    maximum_cell_active_rows = 0
    maximum_storage_rows = 0
    for local_cell, cell in sorted(cells.items()):
        positions = np.asarray(
            [global_to_local[int(row)] for row in cell.active_rows],
            dtype=PETSc.IntType,
        )
        positions.setflags(write=False)
        coefficient_matrix = np.asarray(
            cell.coefficient_matrix,
            dtype=np.complex128,
        )
        cell_actions.append(
            _RankLocalCellAction(
                local_cell=local_cell,
                local_coordinate_positions=positions,
                coefficient_matrix=coefficient_matrix,
                class_key=classes[local_cell],
            )
        )
        maximum_cell_active_rows = max(
            maximum_cell_active_rows,
            len(cell.active_rows),
        )
        maximum_storage_rows = max(
            maximum_storage_rows,
            len(cell.storage_original_dofs),
        )

    identity_payload = {
        "schema": "task035b.selected-p6-trace-matrix-free-identity.v1",
        "geometry_sha256": geometry_hash,
        "ordered_trace_basis_sha256": basis_hash,
        "selection_sha256": selection_hash,
        "active_rows": active_rows,
        "base_rows": expansion.p5_periodic_quotient_rows,
        "selected_missing_rows": expansion.selected_missing_rows,
    }
    identity_sha256 = hashlib.sha256(
        json.dumps(
            identity_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    plan_audit = MappingProxyType(
        {
            "schema_version": ("task035b.owner-aware-selected-p6-trace-ghost-plan.v1"),
            "status": "correctness_only_owner_aware_ghost_plan_ready",
            "pass": True,
            "mpi_size": int(communicator.size),
            "global_active_rows": active_rows,
            "owned_coordinate_count": len(normalized_owned),
            "ghost_coordinate_count": len(ghost_rows),
            "rank_local_active_coordinate_slots": len(local_global_rows),
            "owned_cell_count": len(cell_actions),
            "maximum_cell_active_rows": maximum_cell_active_rows,
            "maximum_storage_scratch_rows": maximum_storage_rows,
            "selected_missing_rows": expansion.selected_missing_rows,
            "inactive_missing_rows_allocated": 0,
            "input_exchange": "PETSc VecGhost forward owner-to-ghost scatter",
            "output_exchange": "PETSc VecGhost reverse ghost-to-owner scatter",
            "full_vector_allreduce_used": False,
            "full_vector_allgather_used": False,
            "identity_collectives_are_fixed_size_hashes_and_counts": True,
            "replicated_active_vector_allocated": False,
            "global_matrix_constructed": False,
            "LU_factor_constructed": False,
            "production_execution_enabled": False,
            "ordinary_default_changed": False,
        }
    )
    return (
        OwnerAwareSelectedP6TraceGhostPlan(
            active_rows=active_rows,
            ownership_start=ownership_start,
            ownership_stop=ownership_stop,
            ghost_rows=ghost_rows,
            local_global_rows=local_global_rows,
            cell_actions=tuple(cell_actions),
            geometry_sha256=geometry_hash,
            ordered_trace_basis_sha256=basis_hash,
            selection_sha256=selection_hash,
            identity_sha256=identity_sha256,
            audit=plan_audit,
        ),
        MappingProxyType(normalized_classes),
    )


class SelectedP6TraceMatrixFreeContext:
    """PETSc Python Mat context with owner-local ghosted work vectors."""

    def __init__(
        self,
        *,
        plan: OwnerAwareSelectedP6TraceGhostPlan,
        storage_schur_by_class: Mapping[Hashable, np.ndarray],
        communicator: MPI.Intracomm,
    ) -> None:
        self.plan = plan
        self.communicator = communicator
        local_size = plan.owned_rows
        global_size = plan.active_rows
        self._input = PETSc.Vec().createGhost(
            plan.ghost_rows,
            size=(local_size, global_size),
            comm=communicator,
        )
        self._output = self._input.duplicate()
        self._schur_by_class = storage_schur_by_class
        maximum_storage = int(plan.audit["maximum_storage_scratch_rows"])
        maximum_active = int(plan.audit["maximum_cell_active_rows"])
        self._storage_input = np.empty(
            maximum_storage,
            dtype=np.complex128,
        )
        self._storage_output = np.empty(
            maximum_storage,
            dtype=np.complex128,
        )
        self._cell_output = np.empty(
            maximum_active,
            dtype=np.complex128,
        )
        self._apply_count = 0
        self._hermitian_apply_count = 0
        self._destroyed = False
        self._validate_global_support()

    def _validate_global_support(self) -> None:
        with self._output.localForm() as local_output:
            values = local_output.getArray()
            values.fill(0.0)
            for cell in self.plan.cell_actions:
                np.add.at(
                    values,
                    cell.local_coordinate_positions,
                    PETSc.ScalarType(1.0),
                )
        self._output.ghostUpdate(
            addv=PETSc.InsertMode.ADD_VALUES,
            mode=PETSc.ScatterMode.REVERSE,
        )
        unsupported = np.flatnonzero(
            np.abs(self._output.getArray(readonly=True)) == 0.0
        )
        local_error = (
            None
            if len(unsupported) == 0
            else (
                "owned active rows have no local-cell support: "
                + str(
                    (unsupported.astype(np.int64) + self.plan.ownership_start)[
                        :8
                    ].tolist()
                )
            )
        )
        _collective_errors(
            self.communicator,
            phase="active-row support",
            local_error=local_error,
        )
        with self._output.localForm() as local_output:
            local_output.getArray().fill(0.0)

    def _check_vectors(self, x: PETSc.Vec, y: PETSc.Vec) -> None:
        expected_range = (
            self.plan.ownership_start,
            self.plan.ownership_stop,
        )
        if x.getSize() != self.plan.active_rows:
            raise ValueError("MatShell input has the wrong global size")
        if y.getSize() != self.plan.active_rows:
            raise ValueError("MatShell output has the wrong global size")
        if tuple(map(int, x.getOwnershipRange())) != expected_range:
            raise ValueError("MatShell input ownership differs from the plan")
        if tuple(map(int, y.getOwnershipRange())) != expected_range:
            raise ValueError("MatShell output ownership differs from the plan")

    def _apply(
        self,
        x: PETSc.Vec,
        y: PETSc.Vec,
        *,
        hermitian: bool,
    ) -> None:
        if self._destroyed:
            raise RuntimeError("selected-p6 trace MatShell is destroyed")
        self._check_vectors(x, y)
        self._input.getArray()[:] = x.getArray(readonly=True)
        self._input.ghostUpdate(
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )
        with self._input.localForm() as local_input:
            input_values = local_input.getArray(readonly=True)
            with self._output.localForm() as local_output:
                output_values = local_output.getArray()
                output_values.fill(0.0)
                for cell in self.plan.cell_actions:
                    positions = cell.local_coordinate_positions
                    coefficients = cell.coefficient_matrix
                    storage_rows, active_columns = coefficients.shape
                    storage_input = self._storage_input[:storage_rows]
                    storage_output = self._storage_output[:storage_rows]
                    cell_output = self._cell_output[:active_columns]
                    np.matmul(
                        coefficients,
                        input_values[positions],
                        out=storage_input,
                    )
                    schur = self._schur_by_class[cell.class_key]
                    if hermitian:
                        np.conjugate(storage_input, out=storage_output)
                        np.matmul(
                            schur.T,
                            storage_output,
                            out=storage_input,
                        )
                        np.conjugate(storage_input, out=storage_output)
                    else:
                        np.matmul(
                            schur,
                            storage_input,
                            out=storage_output,
                        )
                    np.conjugate(storage_output, out=storage_input)
                    np.matmul(
                        coefficients.T,
                        storage_input,
                        out=cell_output,
                    )
                    np.conjugate(cell_output, out=cell_output)
                    np.add.at(output_values, positions, cell_output)
        self._output.ghostUpdate(
            addv=PETSc.InsertMode.ADD_VALUES,
            mode=PETSc.ScatterMode.REVERSE,
        )
        y.getArray()[:] = self._output.getArray(readonly=True)
        if hermitian:
            self._hermitian_apply_count += 1
        else:
            self._apply_count += 1

    def mult(
        self,
        _matrix: PETSc.Mat,
        x: PETSc.Vec,
        y: PETSc.Vec,
    ) -> None:
        self._apply(x, y, hermitian=False)

    def multHermitian(
        self,
        _matrix: PETSc.Mat,
        x: PETSc.Vec,
        y: PETSc.Vec,
    ) -> None:
        self._apply(x, y, hermitian=True)

    @property
    def audit(self) -> Mapping[str, Any]:
        return MappingProxyType(
            {
                "schema_version": ("task035b.selected-p6-trace-matrix-free-shell.v1"),
                "status": (
                    "correctness_only_matrix_free_action_ready"
                    if not self._destroyed
                    else "destroyed"
                ),
                "pass": not self._destroyed,
                "identity_sha256": self.plan.identity_sha256,
                "petsc_matrix_type": "python_context_shell",
                "mult_count": self._apply_count,
                "multHermitian_count": self._hermitian_apply_count,
                "local_oriented_schur_class_count": len(self._schur_by_class),
                "one_local_schur_per_oriented_class": True,
                "per_cell_schur_duplicates_stored": False,
                "global_explicit_matrix_constructed": False,
                "global_matrix_storage_bytes": 0,
                "global_LU_constructed": False,
                "replicated_factor_allocated": False,
                "replicated_active_vector_allocated": False,
                "full_vector_allreduce_used_by_action": False,
                "full_vector_allgather_used_by_action": False,
                "rank_local_input_output_ghost_vectors": 2,
                "persistent_rank_local_active_coordinate_slots": (
                    2 * self.plan.local_coordinate_slots
                ),
                "persistent_local_dense_scratch_complex_scalars": (
                    2 * int(self.plan.audit["maximum_storage_scratch_rows"])
                    + int(self.plan.audit["maximum_cell_active_rows"])
                ),
                "inactive_missing_rows_allocated": 0,
                "production_execution_enabled": False,
                "candidate_promotion": False,
                "ordinary_default_changed": False,
                "ghost_plan": dict(self.plan.audit),
            }
        )

    def destroy(self, _matrix: PETSc.Mat | None = None) -> None:
        if self._destroyed:
            return
        self._output.destroy()
        self._input.destroy()
        self._destroyed = True


@dataclass
class CorrectnessOnlySelectedP6TraceShell:
    """Owned PETSc MatPython shell and its explicit non-production audit."""

    matrix: PETSc.Mat
    context: SelectedP6TraceMatrixFreeContext
    _destroyed: bool = field(default=False, init=False, repr=False)

    @property
    def audit(self) -> Mapping[str, Any]:
        return self.context.audit

    def destroy(self) -> None:
        if self._destroyed:
            return
        self.context.destroy(self.matrix)
        self.matrix.destroy()
        self._destroyed = True


def create_correctness_only_selected_p6_trace_shell(
    *,
    expansion: ActualSelectiveP6TraceExpansion,
    exact_sequence_selection: ExactSequenceClosedP6TraceNumbering,
    storage_schur_by_class: Mapping[Hashable, np.ndarray],
    cell_class_keys: Mapping[int, Hashable],
    communicator: MPI.Intracomm,
) -> CorrectnessOnlySelectedP6TraceShell:
    """Create an owner-aware selected-p6 MatShell without enabling a profile."""

    plan, classes = _build_plan_and_classes(
        expansion=expansion,
        exact_sequence_selection=exact_sequence_selection,
        storage_schur_by_class=storage_schur_by_class,
        cell_class_keys=cell_class_keys,
        communicator=communicator,
    )
    context = SelectedP6TraceMatrixFreeContext(
        plan=plan,
        storage_schur_by_class=classes,
        communicator=communicator,
    )
    sizes = (
        (plan.owned_rows, plan.active_rows),
        (plan.owned_rows, plan.active_rows),
    )
    matrix = PETSc.Mat().createPython(
        sizes,
        context=context,
        comm=communicator,
    )
    matrix.setUp()
    if tuple(map(int, matrix.getOwnershipRange())) != (
        plan.ownership_start,
        plan.ownership_stop,
    ):
        matrix.destroy()
        raise RuntimeError("PETSc MatShell ownership differs from the plan")
    return CorrectnessOnlySelectedP6TraceShell(
        matrix=matrix,
        context=context,
    )


__all__ = [
    "CorrectnessOnlySelectedP6TraceShell",
    "OwnerAwareSelectedP6TraceGhostPlan",
    "SelectedP6TraceMatrixFreeContext",
    "create_correctness_only_selected_p6_trace_shell",
]
