"""Serial/MPI2 oracle tests for the selected-p6 trace MatShell."""

from __future__ import annotations

from dataclasses import replace
import hashlib
from types import MappingProxyType, SimpleNamespace

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc
import pytest

from src.adaptivity.selective_p6_trace_exact_sequence import (
    DiscreteGradientOrbitRule,
    build_exact_sequence_closed_p6_trace_numbering,
)
from src.adaptivity.selective_p6_trace_orbits import (
    MissingP6TraceEntity,
)
from src.constraints.selective_p6_trace_3d import (
    canonical_selective_p6_trace_selection_sha256,
)
from src.constraints.selective_p6_trace_expansion import (
    ActualSelectiveP6TraceExpansion,
    PhysicalCellP6TraceExpansion,
)
from src.solvers.hcurl_assembly_time_condensation import (
    CallerTraceExpansion,
)
from src.solvers.selective_p6_trace_matrix_free import (
    create_correctness_only_selected_p6_trace_shell,
)


_CELL_ACTIVE_ROWS = (
    (0, 3, 4),
    (1, 4, 5),
    (2, 3, 4),
    (1, 5, 6),
)


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def _gradient_rule(representative: int) -> DiscreteGradientOrbitRule:
    return DiscreteGradientOrbitRule(
        scalar_orbit_id=f"scalar-edge-{representative}",
        anchor_trace_representative_id=representative,
        required_trace_representative_ids=(representative,),
        scalar_mode_count=1,
        discrete_gradient_rank=1,
        ordered_scalar_basis_sha256=_digest(f"scalar-basis-{representative}"),
        ordered_trace_basis_sha256=_digest(f"trace-basis-{representative}"),
        gradient_map_sha256=_digest(f"gradient-map-{representative}"),
        periodic_orbit_closed=True,
        discrete_gradient_verified=True,
        gradient_map_binds_ordered_basis_identity=True,
    )


def _coefficient_matrix(cell: int) -> np.ndarray:
    row = np.arange(3, dtype=np.float64) + 1.0
    column = np.arange(3, dtype=np.float64) + 1.0
    return np.eye(3, dtype=np.complex128) + (0.015 + 0.004j * (cell + 1)) * np.outer(
        np.cos(0.2 * row + 0.07 * cell),
        np.sin(0.31 * column + 0.05 * cell),
    )


def _class_matrix(class_key: str) -> np.ndarray:
    index = np.arange(3, dtype=np.float64)
    offset = 0.0 if class_key == "class-a" else 0.13
    return np.diag(
        2.1 + offset + 0.17 * index + 0.03j * (index - 1.0)
    ) + 0.025 * np.outer(
        np.sin(0.41 * (index + 1.0) + offset),
        np.cos(0.27 * (index + 1.0)) + 0.2j * np.sin(0.19 * (index + 1.0)),
    )


def _fixture() -> SimpleNamespace:
    comm = MPI.COMM_WORLD
    if comm.size not in {1, 2}:
        pytest.skip("selected-p6 MatShell test is qualified for MPI1/MPI2")
    exact = build_exact_sequence_closed_p6_trace_numbering(
        entities=(
            MissingP6TraceEntity(0, "edge", 1),
            MissingP6TraceEntity(1, "edge", 1),
        ),
        periodic_relations=(),
        gradient_rules=(_gradient_rule(0), _gradient_rule(1)),
        seed_trace_representative_ids=(0,),
        full3d_base_dofs=100,
        active_base_rows=6,
        full3d_dof_limit=102,
    )
    geometry_hash = _digest("matrix-free-geometry")
    basis_hash = _digest("matrix-free-ordered-trace-basis")
    selection_hash = canonical_selective_p6_trace_selection_sha256(
        closed_numbering=exact,
        geometry_key_sha256=geometry_hash,
        ordered_trace_basis_sha256=basis_hash,
    )

    active_rows = 7
    quotient, remainder = divmod(active_rows, comm.size)
    counts = tuple(quotient + int(rank < remainder) for rank in range(comm.size))
    start = sum(counts[: comm.rank])
    stop = start + counts[comm.rank]
    owned_rows = np.arange(start, stop, dtype=PETSc.IntType)

    all_cells: list[PhysicalCellP6TraceExpansion] = []
    expansion_by_original: dict[
        int,
        tuple[np.ndarray, np.ndarray],
    ] = {}
    for global_cell, raw_active in enumerate(_CELL_ACTIVE_ROWS):
        active = np.asarray(raw_active, dtype=PETSc.IntType)
        coefficients = _coefficient_matrix(global_cell)
        originals = np.arange(
            100 + 3 * global_cell,
            103 + 3 * global_cell,
            dtype=PETSc.IntType,
        )
        all_cells.append(
            PhysicalCellP6TraceExpansion(
                local_cell=global_cell,
                storage_original_dofs=originals,
                active_rows=active,
                coefficient_matrix=coefficients,
            )
        )
        for row, original in enumerate(originals):
            expansion_by_original[int(original)] = (
                active.copy(),
                coefficients[row].copy(),
            )

    local_cells = tuple(
        cell for cell in all_cells if cell.local_cell % comm.size == comm.rank
    )
    caller_audit = MappingProxyType(
        {
            "schema_version": ("task035b.test-selected-p6-matrix-free-expansion.v1"),
            "pass": True,
            "owner_aware_contiguous_petsc_rows": True,
            "inactive_modes_have_no_petsc_rows": True,
            "full_trace_matrix_constructed": False,
            "ordinary_default_changed": False,
        }
    )
    caller = CallerTraceExpansion(
        owned_active_rows=owned_rows,
        expansion_by_original=MappingProxyType(expansion_by_original),
        full_trace_rows=len(expansion_by_original),
        active_rows=active_rows,
        qualification_audit=caller_audit,
    )
    expansion_audit = MappingProxyType(
        {
            "schema_version": ("task035b.test-actual-selective-p6-expansion.v1"),
            "status": "analytic_fixture",
            "pass": True,
            "matrix_constructed": False,
            "inactive_missing_petsc_rows": 0,
            "trace_geometry_sha256": geometry_hash,
            "ordered_trace_basis_sha256": basis_hash,
            "selection_sha256": selection_hash,
            "catalog_sha256": _digest("matrix-free-catalog"),
        }
    )
    expansion = ActualSelectiveP6TraceExpansion(
        caller_trace_expansion=caller,
        entity_expansions=(),
        owned_cell_expansions=local_cells,
        storage_expansion_by_original=expansion_by_original,
        base_logical_rows={(10 + row, 0): row for row in range(6)},
        selected_missing_logical_rows={(0, 0): 6},
        full_p6_storage_trace_rows=len(expansion_by_original),
        p5_periodic_quotient_rows=6,
        selected_missing_rows=1,
        active_rows=active_rows,
        audit=expansion_audit,
    )
    local_cell_classes = {
        cell.local_cell: ("class-a" if cell.local_cell % 2 == 0 else "class-b")
        for cell in local_cells
    }
    local_classes = {
        class_key: _class_matrix(class_key)
        for class_key in set(local_cell_classes.values())
    }
    shell = create_correctness_only_selected_p6_trace_shell(
        expansion=expansion,
        exact_sequence_selection=exact,
        storage_schur_by_class=local_classes,
        cell_class_keys=local_cell_classes,
        communicator=comm,
    )
    return SimpleNamespace(
        comm=comm,
        exact=exact,
        expansion=expansion,
        shell=shell,
        all_cells=tuple(all_cells),
        local_cells=local_cells,
        local_classes=local_classes,
        local_cell_classes=local_cell_classes,
    )


def _explicit_oracle(fixture: SimpleNamespace) -> PETSc.Mat:
    shell = fixture.shell
    plan = shell.context.plan
    matrix = PETSc.Mat().createAIJ(
        (
            (plan.owned_rows, plan.active_rows),
            (plan.owned_rows, plan.active_rows),
        ),
        nnz=plan.active_rows,
        comm=fixture.comm,
    )
    for cell in fixture.local_cells:
        class_key = fixture.local_cell_classes[cell.local_cell]
        local_matrix = (
            cell.coefficient_matrix.conj().T
            @ fixture.local_classes[class_key]
            @ cell.coefficient_matrix
        )
        matrix.setValues(
            cell.active_rows,
            cell.active_rows,
            local_matrix,
            addv=PETSc.InsertMode.ADD_VALUES,
        )
    matrix.assemble()
    return matrix


def _deterministic_vector(matrix: PETSc.Mat) -> PETSc.Vec:
    vector = matrix.createVecRight()
    start, stop = map(int, vector.getOwnershipRange())
    rows = np.arange(start, stop, dtype=np.float64)
    vector.getArray()[:] = 0.3 * np.cos(0.23 * (rows + 1.0)) + 0.17j * np.sin(
        0.37 * (rows + 1.0)
    )
    return vector


def _relative_difference(left: PETSc.Vec, right: PETSc.Vec) -> float:
    difference = left.copy()
    difference.axpy(PETSc.ScalarType(-1.0), right)
    result = float(difference.norm()) / max(float(right.norm()), 1.0e-300)
    difference.destroy()
    return result


def test_shell_mult_and_hermitian_match_tiny_explicit_aij_oracle() -> None:
    fixture = _fixture()
    oracle = _explicit_oracle(fixture)
    vector = _deterministic_vector(oracle)
    shell_result = fixture.shell.matrix.createVecLeft()
    oracle_result = oracle.createVecLeft()
    shell_hermitian = fixture.shell.matrix.createVecRight()
    oracle_hermitian = oracle.createVecRight()
    try:
        fixture.shell.matrix.mult(vector, shell_result)
        oracle.mult(vector, oracle_result)
        assert _relative_difference(shell_result, oracle_result) < 3.0e-13

        fixture.shell.matrix.multHermitian(vector, shell_hermitian)
        oracle.multHermitian(vector, oracle_hermitian)
        assert _relative_difference(shell_hermitian, oracle_hermitian) < 3.0e-13
        assert fixture.shell.audit["mult_count"] == 1
        assert fixture.shell.audit["multHermitian_count"] == 1
    finally:
        oracle_hermitian.destroy()
        shell_hermitian.destroy()
        oracle_result.destroy()
        shell_result.destroy()
        vector.destroy()
        oracle.destroy()
        fixture.shell.destroy()
        assert fixture.shell.audit["status"] == "destroyed"


def test_inactive_rows_are_absent_and_scratch_is_rank_local() -> None:
    fixture = _fixture()
    try:
        audit = fixture.shell.audit
        plan = fixture.shell.context.plan
        inactive = tuple(
            orbit.representative_entity_id
            for orbit in fixture.exact.numbering.orbits
            if not orbit.selected
        )
        assert inactive == (1,)
        assert fixture.shell.matrix.getSize() == (7, 7)
        assert fixture.expansion.selected_missing_rows == 1
        assert set(fixture.expansion.selected_missing_logical_rows) == {(0, 0)}
        assert audit["inactive_missing_rows_allocated"] == 0
        assert audit["global_explicit_matrix_constructed"] is False
        assert audit["global_LU_constructed"] is False
        assert audit["replicated_factor_allocated"] is False
        assert audit["replicated_active_vector_allocated"] is False
        assert audit["full_vector_allreduce_used_by_action"] is False
        assert audit["full_vector_allgather_used_by_action"] is False
        assert audit["production_execution_enabled"] is False
        assert audit["candidate_promotion"] is False
        assert plan.local_coordinate_slots == (plan.owned_rows + len(plan.ghost_rows))
        assert plan.audit["maximum_cell_active_rows"] == 3
        assert plan.audit["maximum_storage_scratch_rows"] == 3
        if fixture.comm.size == 2:
            assert plan.local_coordinate_slots < plan.active_rows
            assert len(plan.ghost_rows) == 1
    finally:
        fixture.shell.destroy()
        assert fixture.shell.audit["status"] == "destroyed"


def test_stale_selection_identity_fails_closed_collectively() -> None:
    fixture = _fixture()
    fixture.shell.destroy()
    stale_rank = 0 if fixture.comm.size == 1 else 1
    audit = dict(fixture.expansion.audit)
    if fixture.comm.rank == stale_rank:
        audit["selection_sha256"] = "0" * 64
    stale = replace(
        fixture.expansion,
        audit=MappingProxyType(audit),
    )
    with pytest.raises(
        RuntimeError,
        match=("collective identity validation failed:.*selection SHA256 is stale"),
    ):
        create_correctness_only_selected_p6_trace_shell(
            expansion=stale,
            exact_sequence_selection=fixture.exact,
            storage_schur_by_class=fixture.local_classes,
            cell_class_keys=fixture.local_cell_classes,
            communicator=fixture.comm,
        )
