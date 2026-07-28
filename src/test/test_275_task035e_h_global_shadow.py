from __future__ import annotations

import hashlib
import os
from types import MappingProxyType

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc
import pytest

from src.adaptivity.blind_controller.contracts import (
    FORMAL_GOAL_IDS,
    GoalVector,
)
from src.adaptivity.dyadic_hexa_refinement import (
    DyadicHexKey,
    build_root_dyadic_hexa_forest,
    refine_balanced_dyadic_hexa_forest,
)
from src.adaptivity.task035e_h_global_shadow import (
    build_level3_endpoint_receipt,
    close_level3_h_saturation_coverage,
    evaluate_level3_global_shadow_orbit,
    global_shadow_vector_sha256,
    level3_shadow_backend_capability_report,
)
from src.adaptivity.task035e_h_saturation import (
    build_level3_h_saturation_catalog,
    build_level3_h_saturation_patch,
    materialize_level3_h_saturation_constraints,
)
from src.adaptivity.task035e_hp_transition import (
    build_initial_hp_transition_state,
)


_SOURCE_SHA = "1234567890abcdef1234567890abcdef12345678"
_ALGORITHM_SHA = hashlib.sha256(
    b"task035e-h-global-shadow-test"
).hexdigest()


@pytest.fixture(scope="module")
def multilevel_state():
    forest = build_root_dyadic_hexa_forest(
        ((0.0, 0.0, 0.0, 1.0, 1.0, 1.0),),
        (1,),
        periodic_axes=("x", "y"),
        protect_material_interfaces=True,
    )
    forest = refine_balanced_dyadic_hexa_forest(
        forest,
        (DyadicHexKey(0, 0, 0, 0, 0),),
        maximum_level=2,
    )
    forest = refine_balanced_dyadic_hexa_forest(
        forest,
        (DyadicHexKey(0, 1, 0, 0, 0),),
        maximum_level=2,
    )
    return build_initial_hp_transition_state(
        forest,
        {cell.key: 4 for cell in forest.leaves},
        source_sha=_SOURCE_SHA,
        algorithm_sha256=_ALGORITHM_SHA,
    )


@pytest.fixture(scope="module")
def catalog(multilevel_state):
    return build_level3_h_saturation_catalog(multilevel_state)


@pytest.fixture(scope="module")
def shadow_patch(multilevel_state, catalog):
    return build_level3_h_saturation_patch(
        multilevel_state,
        catalog,
        orbit_id=catalog.periodic_orbits[0].orbit_id,
    )


@pytest.fixture(scope="module")
def constraints(shadow_patch):
    return materialize_level3_h_saturation_constraints(
        shadow_patch,
        phase_x=np.exp(0.11j),
        phase_y=np.exp(-0.19j),
        comm=MPI.COMM_SELF,
    )


def _dense_problem():
    rng = np.random.default_rng(275)
    size = 10
    raw = rng.normal(size=(size, size)) + 1j * rng.normal(
        size=(size, size)
    )
    matrix = raw.conj().T @ raw + 3.0 * np.eye(size)
    current = rng.normal(size=size) + 1j * rng.normal(size=size)
    correction = 1.0e-7 * (
        rng.normal(size=size) + 1j * rng.normal(size=size)
    )
    shadow = current + correction
    rhs = matrix @ shadow
    gradients = {
        goal_id: (
            rng.normal(size=size) + 1j * rng.normal(size=size)
        )
        for goal_id in FORMAL_GOAL_IDS
    }
    current_goals = GoalVector.from_mapping(
        {goal_id: 0.2 for goal_id in FORMAL_GOAL_IDS}
    )
    shadow_goals = GoalVector.from_mapping(
        {
            goal_id: (
                0.2
                + float(np.real(np.vdot(gradients[goal_id], correction)))
            )
            for goal_id in FORMAL_GOAL_IDS
        }
    )
    return (
        matrix,
        rhs,
        current,
        shadow,
        gradients,
        current_goals,
        shadow_goals,
    )


def test_dense_global_correction_closes_59_adjoints_and_endpoint(
    shadow_patch,
    constraints,
) -> None:
    (
        matrix,
        rhs,
        current,
        shadow,
        gradients,
        current_goals,
        shadow_goals,
    ) = _dense_problem()
    receipt = build_level3_endpoint_receipt(
        shadow_patch,
        current_goals=current_goals,
        shadow_goals=shadow_goals,
        shadow_solution_sha256=global_shadow_vector_sha256(shadow),
        candidate_output_payload_sha256="a" * 64,
        watchdog_record_sha256="b" * 64,
        actual_field_postprocess=False,
    )
    evidence = evaluate_level3_global_shadow_orbit(
        shadow_patch,
        constraints,
        shadow_matrix=matrix,
        shadow_rhs=rhs,
        current_in_shadow=current,
        expected_shadow_solution=shadow,
        goal_gradients=gradients,
        endpoint_receipt=receipt,
    )

    assert len(evidence.goals) == 59
    assert evidence.audit["component_algebra_pass"] is True
    assert evidence.audit["dwr_verified_goal_count"] == 59
    assert evidence.audit["all_goals_inside_saturation_budget"] is True
    assert evidence.audit["global_correction_complete"] is True
    assert evidence.audit["actual_59_goal_adjoint_complete"] is True
    assert evidence.audit["actual_endpoint_consumed"] is True
    assert evidence.audit["formal_orbit_evidence_complete"] is False
    assert evidence.audit["formal_h_saturation_status"] == "unknown"
    assert evidence.audit["measured_pass"] is False
    assert evidence.audit["production_level_three_rows_numbered"] is False
    assert "dense_synthetic_backend_has_no_formal_credit" in (
        evidence.audit["formal_blockers"]
    )


def test_backend_report_names_the_exact_incremental_and_dtn_blockers() -> None:
    report = level3_shadow_backend_capability_report()

    assert report["equivalent_complete_shadow_system_available"] is True
    assert report["child_only_incremental_shadow_system_available"] is False
    assert report["compiled_tensor_shape"] == [882, 882]
    assert report["production_plan_parser_accepts_level3"] is False
    assert report["formal_h_saturation_status"] == "unknown"
    assert {
        row["name"] for row in report["missing_public_interfaces"]
    } == {
        "append_level3_child_schur_delta",
        "standalone_variable_p_dtn_augmentation",
        "standalone_level3_live_view_factory",
    }


def test_missing_orbits_keep_the_closed_coverage_unknown(
    multilevel_state,
    catalog,
    shadow_patch,
    constraints,
) -> None:
    (
        matrix,
        rhs,
        current,
        shadow,
        gradients,
        current_goals,
        shadow_goals,
    ) = _dense_problem()
    receipt = build_level3_endpoint_receipt(
        shadow_patch,
        current_goals=current_goals,
        shadow_goals=shadow_goals,
        shadow_solution_sha256=global_shadow_vector_sha256(shadow),
        candidate_output_payload_sha256="c" * 64,
        watchdog_record_sha256="d" * 64,
        actual_field_postprocess=False,
    )
    evidence = evaluate_level3_global_shadow_orbit(
        shadow_patch,
        constraints,
        shadow_matrix=matrix,
        shadow_rhs=rhs,
        current_in_shadow=current,
        expected_shadow_solution=shadow,
        goal_gradients=gradients,
        endpoint_receipt=receipt,
    )
    coverage = close_level3_h_saturation_coverage(
        multilevel_state,
        catalog,
        (evidence,),
    )

    assert coverage.audit["formal_h_saturation_status"] == "unknown"
    assert coverage.audit["measured_pass"] is False
    assert coverage.audit["measured_fail"] is False
    assert coverage.audit["freezing_credit"] is False
    assert coverage.audit["all_level_two_orbits_covered"] is False
    assert coverage.audit["missing_orbit_ids"]
    assert coverage.audit["production_level_three_selectable"] is False


def test_endpoint_receipt_tampering_fails_closed(
    shadow_patch,
    constraints,
) -> None:
    (
        matrix,
        rhs,
        current,
        shadow,
        gradients,
        current_goals,
        shadow_goals,
    ) = _dense_problem()
    receipt = build_level3_endpoint_receipt(
        shadow_patch,
        current_goals=current_goals,
        shadow_goals=shadow_goals,
        shadow_solution_sha256=global_shadow_vector_sha256(shadow),
        candidate_output_payload_sha256="e" * 64,
        watchdog_record_sha256="f" * 64,
        actual_field_postprocess=False,
    )
    changed = dict(receipt.audit)
    changed["actual_field_postprocess"] = True
    forged = type(receipt)(
        current_goals=receipt.current_goals,
        shadow_goals=receipt.shadow_goals,
        audit=MappingProxyType(changed),
    )

    with pytest.raises(ValueError, match="identity drifted"):
        evaluate_level3_global_shadow_orbit(
            shadow_patch,
            constraints,
            shadow_matrix=matrix,
            shadow_rhs=rhs,
            current_in_shadow=current,
            expected_shadow_solution=shadow,
            goal_gradients=gradients,
            endpoint_receipt=forged,
        )


def test_caller_boolean_cannot_promote_an_endpoint(shadow_patch) -> None:
    (
        _matrix,
        _rhs,
        _current,
        shadow,
        _gradients,
        current_goals,
        shadow_goals,
    ) = _dense_problem()

    with pytest.raises(ValueError, match="qualified live view"):
        build_level3_endpoint_receipt(
            shadow_patch,
            current_goals=current_goals,
            shadow_goals=shadow_goals,
            shadow_solution_sha256=global_shadow_vector_sha256(shadow),
            candidate_output_payload_sha256="9" * 64,
            watchdog_record_sha256="8" * 64,
            actual_field_postprocess=True,
        )


def test_goal_gradient_order_is_not_caller_selectable(
    shadow_patch,
    constraints,
) -> None:
    (
        matrix,
        rhs,
        current,
        shadow,
        gradients,
        current_goals,
        shadow_goals,
    ) = _dense_problem()
    receipt = build_level3_endpoint_receipt(
        shadow_patch,
        current_goals=current_goals,
        shadow_goals=shadow_goals,
        shadow_solution_sha256=global_shadow_vector_sha256(shadow),
        candidate_output_payload_sha256="1" * 64,
        watchdog_record_sha256="2" * 64,
        actual_field_postprocess=False,
    )

    with pytest.raises(ValueError, match="formal goal order"):
        evaluate_level3_global_shadow_orbit(
            shadow_patch,
            constraints,
            shadow_matrix=matrix,
            shadow_rhs=rhs,
            current_in_shadow=current,
            expected_shadow_solution=shadow,
            goal_gradients=dict(reversed(tuple(gradients.items()))),
            endpoint_receipt=receipt,
        )


def _petsc_test_operator(comm: MPI.Intracomm, size: int) -> PETSc.Mat:
    matrix = PETSc.Mat().createAIJ(
        size=(size, size),
        nnz=3,
        comm=comm,
    )
    start, end = map(int, matrix.getOwnershipRange())
    for row in range(start, end):
        columns = [row]
        values = [4.0 + 0.0j]
        if row > 0:
            columns.append(row - 1)
            values.append(-1.0 + 0.1j)
        if row + 1 < size:
            columns.append(row + 1)
            values.append(-1.0 - 0.1j)
        matrix.setValues(
            [row],
            columns,
            np.asarray(values, dtype=PETSc.ScalarType),
        )
    matrix.assemble()
    return matrix


def _petsc_vector(
    comm: MPI.Intracomm,
    values: np.ndarray,
) -> PETSc.Vec:
    vector = PETSc.Vec().createMPI(len(values), comm=comm)
    start, end = map(int, vector.getOwnershipRange())
    rows = np.arange(start, end, dtype=PETSc.IntType)
    vector.setValues(rows, np.asarray(values[start:end], dtype=PETSc.ScalarType))
    vector.assemble()
    return vector


@pytest.mark.skipif(
    os.environ.get("MYFENICS_RUN_TASK035E_H_GLOBAL_SHADOW_MPI8") != "1",
    reason="set the Task035e level3 global shadow MPI8 opt-in",
)
def test_distributed_global_correction_and_59_transpose_solves_are_mpi8(
    multilevel_state,
    catalog,
) -> None:
    comm = MPI.COMM_WORLD
    if comm.size != 8:
        pytest.skip("Task035e level3 global shadow component requires MPI8")
    patch = build_level3_h_saturation_patch(
        multilevel_state,
        catalog,
        orbit_id=catalog.periodic_orbits[0].orbit_id,
    )
    exact_constraints = materialize_level3_h_saturation_constraints(
        patch,
        phase_x=np.exp(0.11j),
        phase_y=np.exp(-0.19j),
        comm=comm,
    )
    size = 16
    matrix = _petsc_test_operator(comm, size)
    current = _petsc_vector(
        comm,
        np.zeros(size, dtype=np.complex128),
    )
    expected_values = 1.0e-7 * np.arange(1, size + 1) * (1.0 + 0.2j)
    expected = _petsc_vector(comm, expected_values)
    rhs = expected.duplicate()
    matrix.mult(expected, rhs)
    gradients = {
        goal_id: _petsc_vector(
            comm,
            1.0e-2
            * (
                1.0
                + (
                    (goal_index + 1)
                    * np.arange(1, size + 1)
                    % 17
                )
            )
            * (1.0 + 0.01j * (goal_index + 1)),
        )
        for goal_index, goal_id in enumerate(FORMAL_GOAL_IDS)
    }
    current_goals = GoalVector.from_mapping(
        {goal_id: 0.2 for goal_id in FORMAL_GOAL_IDS}
    )
    shadow_goals = GoalVector.from_mapping(
        {
            goal_id: 0.2 + float(gradients[goal_id].dot(expected).real)
            for goal_id in FORMAL_GOAL_IDS
        }
    )
    receipt = build_level3_endpoint_receipt(
        patch,
        current_goals=current_goals,
        shadow_goals=shadow_goals,
        shadow_solution_sha256=global_shadow_vector_sha256(expected),
        candidate_output_payload_sha256="3" * 64,
        watchdog_record_sha256="4" * 64,
        actual_field_postprocess=False,
    )
    ksp = PETSc.KSP().create(comm)
    ksp.setOperators(matrix)
    ksp.setType("preonly")
    ksp.getPC().setType("lu")
    ksp.getPC().setFactorSolverType("mumps")
    ksp.setUp()
    try:
        evidence = evaluate_level3_global_shadow_orbit(
            patch,
            exact_constraints,
            shadow_matrix=matrix,
            shadow_rhs=rhs,
            current_in_shadow=current,
            expected_shadow_solution=expected,
            goal_gradients=gradients,
            endpoint_receipt=receipt,
            ksp=ksp,
        )
        packets = comm.allgather(
            evidence.audit["orbit_evidence_sha256"]
        )

        assert len(set(packets)) == 1
        assert evidence.audit["backend"] == (
            "petsc_distributed_global_shadow"
        )
        assert evidence.audit["mpi_size"] == 8
        assert evidence.audit["component_algebra_pass"] is True
        assert evidence.audit["dwr_verified_goal_count"] == 59
        assert evidence.audit["formal_h_saturation_status"] == "unknown"
        assert "compiled_level3_shadow_cell_system_missing" in (
            evidence.audit["formal_blockers"]
        )
    finally:
        ksp.destroy()
        for vector in gradients.values():
            vector.destroy()
        rhs.destroy()
        expected.destroy()
        current.destroy()
        matrix.destroy()
