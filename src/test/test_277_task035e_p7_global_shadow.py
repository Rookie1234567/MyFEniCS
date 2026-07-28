from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Mapping

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc
import pytest

from src.adaptivity.blind_controller.contracts import (
    FORMAL_GOAL_IDS,
    GoalVector,
)
from src.adaptivity.task035e_p7_global_shadow import (
    P7_COMPILED_ASSEMBLY_AUDIT_SCHEMA,
    P7_CONSTRAINT_AUDIT_SCHEMA,
    P7_LIVE_ENDPOINT_AUDIT_SCHEMA,
    build_p7_compiled_operator_receipt,
    build_p7_component_operator_receipt,
    build_p7_global_coverage_catalog,
    build_p7_physical_endpoint_receipt,
    close_p7_global_saturation_coverage,
    evaluate_p7_global_shadow,
    p7_global_shadow_backend_capability_report,
    p7_global_shadow_vector_sha256,
)


def _sha(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()


def _structural_bridge(*, formal: bool) -> Mapping[str, Any]:
    targets = [
        "cell:r0:x0:y0:z0",
        "cell:r0:x1:y0:z0",
    ]
    periodic = [
        {
            "root": {"dimension": 1, "geometry_key": [0, 0, 0, 0]},
            "dimension": 1,
            "members": [
                {"dimension": 1, "geometry_key": [0, 0, 0, 0]},
                {"dimension": 1, "geometry_key": [1, 0, 0, 0]},
            ],
            "member_degrees": [6, 6],
            "requested_member_count": 1,
            "closure_added_member_count": 1,
        }
    ]
    core: dict[str, Any] = {
        "schema_version": (
            "task035e.p7-saturation-structural-bridge.v1"
        ),
        "structural_coverage_pass": formal,
        "mathematical_structural_coverage_pass": True,
        "enumeration": {
            "p6_target_ids": targets,
            "cell_orbits": [
                {"target_id": target, "source_degree": 6}
                for target in targets
            ],
            "periodic_trace_orbits": periodic,
        },
        "p7_component_binding": {
            "hanging_component_audits": [
                {"patch_index": 4, "source_degree": 6}
            ],
        },
        "production_numbering": {
            "production_degrees": [4, 5, 6],
            "p7_rows_added": 0,
            "inactive_p7_numbering_pass": True,
        },
        "mpi": {
            "observed_size": 8 if formal else 1,
            "formal_partition_identity_status": (
                "pass" if formal else "not_run"
            ),
            "all_rank_digest_pass": True,
        },
    }
    return {**core, "evidence_sha256": _sha(core)}


def _dense_algebra():
    matrix = np.asarray(
        [
            [4.0 + 0.1j, 0.3 - 0.2j, 0.0, 0.0],
            [0.1 + 0.4j, 5.0 - 0.2j, -0.2j, 0.0],
            [0.0, 0.2 + 0.1j, 4.5 + 0.3j, 0.1],
            [0.1j, 0.0, -0.2 + 0.1j, 5.5 - 0.1j],
        ],
        dtype=np.complex128,
    )
    correction = np.asarray(
        [0.2 + 0.1j, -0.1j, 0.05 - 0.03j, -0.02 + 0.04j],
        dtype=np.complex128,
    )
    residual = matrix @ correction
    gradients = {
        goal_id: np.asarray(
            [
                0.01 * (index + 1),
                0.02j,
                -0.015 + 0.005j,
                0.01,
            ],
            dtype=np.complex128,
        )
        for index, goal_id in enumerate(FORMAL_GOAL_IDS)
    }
    return matrix, residual, correction, gradients


@pytest.mark.skipif(MPI.COMM_WORLD.size != 1, reason="serial contract test")
def test_dense_global_algebra_is_complete_but_formally_unknown() -> None:
    catalog = build_p7_global_coverage_catalog(
        _structural_bridge(formal=False)
    )
    matrix, residual, correction, gradients = _dense_algebra()
    operator = build_p7_component_operator_receipt(matrix, catalog)
    current = GoalVector.from_mapping(
        {goal_id: 0.0 for goal_id in FORMAL_GOAL_IDS}
    )
    shadow = GoalVector.from_mapping(
        {
            goal_id: float(np.real(np.vdot(gradient, correction)))
            for goal_id, gradient in gradients.items()
        }
    )
    endpoint = build_p7_physical_endpoint_receipt(
        operator,
        current_goals=current,
        shadow_goals=shadow,
        correction_sha256=p7_global_shadow_vector_sha256(correction),
        candidate_output_payload_sha256="a" * 64,
        watchdog_record_sha256="b" * 64,
    )
    evidence = evaluate_p7_global_shadow(
        catalog,
        operator,
        endpoint,
        matrix=matrix,
        projected_residual=residual,
        expected_correction=correction,
        goal_gradients=gradients,
    )
    coverage = close_p7_global_saturation_coverage(
        catalog,
        (evidence,),
    )

    assert evidence.audit["actual_global_correction_complete"] is True
    assert evidence.audit["actual_59_goal_adjoint_complete"] is True
    assert evidence.audit["formal_goal_count"] == 59
    assert evidence.audit["correction_relative_residual"] < 1.0e-12
    assert (
        evidence.audit["maximum_adjoint_relative_residual"]
        < 1.0e-12
    )
    assert (
        evidence.audit["signed_dwr_direct_closure_error_max"]
        < 1.0e-12
    )
    assert evidence.audit["dwr_verified_goal_count"] == 59
    assert evidence.audit["opposite_sign_goal_ids"] == []
    assert evidence.audit["formal_component_complete"] is False
    assert "dense_synthetic_backend_has_no_formal_credit" in evidence.audit[
        "formal_blockers"
    ]
    assert coverage.audit["all_p6_targets_and_orbits_covered"] is True
    assert coverage.audit["p6_saturation_status"] == "unknown"
    assert coverage.audit["measured_pass"] is False
    assert coverage.audit["measured_fail"] is False
    assert coverage.audit["production_p7_rows"] == 0
    assert coverage.audit["next_production_plan"] is None


@pytest.mark.skipif(MPI.COMM_WORLD.size != 1, reason="serial contract test")
def test_missing_target_coverage_cannot_be_measured() -> None:
    catalog = build_p7_global_coverage_catalog(
        _structural_bridge(formal=False)
    )
    matrix, residual, correction, gradients = _dense_algebra()
    operator = build_p7_component_operator_receipt(
        matrix,
        catalog,
        covered_p6_target_ids=catalog.p6_target_ids[:1],
    )
    goals = GoalVector.from_mapping(
        {goal_id: 0.0 for goal_id in FORMAL_GOAL_IDS}
    )
    endpoint = build_p7_physical_endpoint_receipt(
        operator,
        current_goals=goals,
        shadow_goals=goals,
        correction_sha256=p7_global_shadow_vector_sha256(correction),
        candidate_output_payload_sha256="c" * 64,
        watchdog_record_sha256="d" * 64,
    )
    evidence = evaluate_p7_global_shadow(
        catalog,
        operator,
        endpoint,
        matrix=matrix,
        projected_residual=residual,
        expected_correction=correction,
        goal_gradients=gradients,
    )
    coverage = close_p7_global_saturation_coverage(catalog, (evidence,))

    assert coverage.audit["p6_saturation_status"] == "unknown"
    assert coverage.audit["all_p6_targets_and_orbits_covered"] is False
    assert coverage.audit["missing_p6_target_ids"] == [
        catalog.p6_target_ids[1]
    ]


@pytest.mark.skipif(MPI.COMM_WORLD.size != 1, reason="serial contract test")
def test_actual_endpoint_effectivity_rejects_systematic_opposite_sign() -> None:
    catalog = build_p7_global_coverage_catalog(
        _structural_bridge(formal=False)
    )
    matrix, residual, correction, base_gradients = _dense_algebra()
    gradients = {
        goal_id: 1.0e4 * gradient
        for goal_id, gradient in base_gradients.items()
    }
    operator = build_p7_component_operator_receipt(matrix, catalog)
    current = GoalVector.from_mapping(
        {goal_id: 0.0 for goal_id in FORMAL_GOAL_IDS}
    )
    shadow = GoalVector.from_mapping(
        {
            goal_id: -float(np.real(np.vdot(gradient, correction)))
            for goal_id, gradient in gradients.items()
        }
    )
    endpoint = build_p7_physical_endpoint_receipt(
        operator,
        current_goals=current,
        shadow_goals=shadow,
        correction_sha256=p7_global_shadow_vector_sha256(correction),
        candidate_output_payload_sha256="8" * 64,
        watchdog_record_sha256="9" * 64,
    )
    evidence = evaluate_p7_global_shadow(
        catalog,
        operator,
        endpoint,
        matrix=matrix,
        projected_residual=residual,
        expected_correction=correction,
        goal_gradients=gradients,
    )

    assert evidence.audit["dwr_verified_goal_count"] == 0
    assert evidence.audit["opposite_sign_goal_count"] == 59
    assert "p7_actual_endpoint_effectivity_below_54_of_59" in evidence.audit[
        "formal_blockers"
    ]
    assert "p7_high_priority_goals_systematically_opposite" in evidence.audit[
        "formal_blockers"
    ]


def _petsc_vector(values: np.ndarray, matrix: PETSc.Mat) -> PETSc.Vec:
    vector = matrix.createVecRight()
    start, end = map(int, vector.getOwnershipRange())
    vector.setValues(
        np.arange(start, end, dtype=PETSc.IntType),
        np.asarray(values[start:end], dtype=PETSc.ScalarType),
    )
    vector.assemblyBegin()
    vector.assemblyEnd()
    return vector


def _petsc_system(*, failing: bool):
    comm = MPI.COMM_WORLD
    size = 16
    matrix_values = np.zeros((size, size), dtype=np.complex128)
    for row in range(size):
        matrix_values[row, row] = 5.0 + 0.02j * (row + 1)
        if row > 0:
            matrix_values[row, row - 1] = -0.2 + 0.03j
        if row + 1 < size:
            matrix_values[row, row + 1] = 0.15 - 0.02j
    matrix = PETSc.Mat().createAIJ(
        size=(size, size),
        nnz=3,
        comm=comm,
    )
    start, end = map(int, matrix.getOwnershipRange())
    for row in range(start, end):
        columns = np.flatnonzero(matrix_values[row])
        matrix.setValues(
            row,
            columns.astype(PETSc.IntType),
            matrix_values[row, columns].astype(PETSc.ScalarType),
        )
    matrix.assemblyBegin()
    matrix.assemblyEnd()
    correction_values = np.asarray(
        [
            1.0e-8
            * complex(np.cos(0.2 * index), np.sin(0.3 * index))
            for index in range(size)
        ],
        dtype=np.complex128,
    )
    residual_values = matrix_values @ correction_values
    gradient_values: dict[str, np.ndarray] = {}
    for index, goal_id in enumerate(FORMAL_GOAL_IDS):
        scale = 1.0e-7 * (index + 1)
        if failing and index == 0:
            scale = 2.0e5
        gradient_values[goal_id] = np.asarray(
            [
                scale
                * complex(
                    np.cos(0.1 * (index + 1) * (column + 1)),
                    np.sin(0.07 * (index + 2) * (column + 1)),
                )
                for column in range(size)
            ],
            dtype=np.complex128,
        )
    residual = _petsc_vector(residual_values, matrix)
    correction = _petsc_vector(correction_values, matrix)
    gradients = {
        goal_id: _petsc_vector(values, matrix)
        for goal_id, values in gradient_values.items()
    }
    direct = {
        goal_id: float(
            np.real(np.vdot(values, correction_values))
        )
        for goal_id, values in gradient_values.items()
    }
    ksp = PETSc.KSP().create(comm)
    ksp.setOperators(matrix)
    ksp.setType(PETSc.KSP.Type.GMRES)
    ksp.getPC().setType(PETSc.PC.Type.JACOBI)
    # The correction RHS is O(1e-7), so an absolute tolerance of 1e-15
    # permits a true relative residual slightly above the formal 1e-9 Gate
    # under MPI partitioning.  Keep the Gate fixed and make the fixture solve
    # genuinely tighter instead.
    ksp.setTolerances(rtol=1.0e-13, atol=1.0e-18, max_it=100)
    ksp.setGMRESRestart(30)
    ksp.setUp()
    return matrix, residual, correction, gradients, direct, ksp


def _spoofed_mapping_operator(matrix: PETSc.Mat, catalog):
    component = build_p7_component_operator_receipt(matrix, catalog)
    assembly = {
        "schema_version": P7_COMPILED_ASSEMBLY_AUDIT_SCHEMA,
        "compiled_p7_tensor_builder": True,
        "compiled_local_schur": True,
        "matrix_sha256": component.audit["matrix_sha256"],
        "selected_shadow_rows": matrix.getSize()[0],
        "compiled_p7_tensor_count": len(catalog.p6_target_ids),
        "compiled_schur_count": len(catalog.p6_target_ids),
        "compiled_p7_tensor_sha256": "1" * 64,
        "compiled_schur_sha256": "2" * 64,
        "inactive_p7_modes_globally_numbered": False,
        "production_p7_rows_numbered": False,
        "production_p7_row_count": 0,
        "production_degree_set": [4, 5, 6],
        "covered_p6_target_ids": list(catalog.p6_target_ids),
        "covered_periodic_orbit_ids": list(catalog.periodic_orbit_ids),
        "covered_hanging_orbit_ids": list(catalog.hanging_orbit_ids),
    }
    constraints = {
        "schema_version": P7_CONSTRAINT_AUDIT_SCHEMA,
        "catalog_sha256": catalog.audit["catalog_sha256"],
        "hanging_constraint_pass": True,
        "floquet_constraint_pass": True,
        "periodic_orbit_closure_pass": True,
        "production_p7_rows_numbered": False,
    }
    port = {
        "schema_version": (
            "task035d.variable-p-trace-only-port-operator.v1"
        ),
        "pass": True,
        "checks": {
            "floquet_pullback": True,
            "dtn_action": True,
        },
        "auxiliary_interior_columns_allocated": False,
    }
    return build_p7_compiled_operator_receipt(
        matrix,
        catalog,
        assembly_audit=assembly,
        constraint_audit=constraints,
        port_operator_audit=port,
    )


def _component_endpoint(operator, correction, shadow_values):
    current = GoalVector.from_mapping(
        {goal_id: 0.0 for goal_id in FORMAL_GOAL_IDS}
    )
    shadow = GoalVector.from_mapping(shadow_values)
    correction_sha = p7_global_shadow_vector_sha256(correction)
    return build_p7_physical_endpoint_receipt(
        operator,
        current_goals=current,
        shadow_goals=shadow,
        correction_sha256=correction_sha,
        candidate_output_payload_sha256="e" * 64,
        watchdog_record_sha256="f" * 64,
    )


@pytest.mark.skipif(
    os.environ.get("MYFENICS_RUN_TASK035E_P7_GLOBAL_MPI8") != "1"
    or MPI.COMM_WORLD.size != 8,
    reason="set the opt-in flag and launch this fixture with MPI8",
)
@pytest.mark.parametrize("failing", [False, True])
def test_mpi8_petsc_59_adjoint_is_fail_closed_without_live_view(
    failing: bool,
) -> None:
    catalog = build_p7_global_coverage_catalog(
        _structural_bridge(formal=True)
    )
    (
        matrix,
        residual,
        correction,
        gradients,
        direct,
        ksp,
    ) = _petsc_system(failing=failing)
    try:
        operator = _spoofed_mapping_operator(matrix, catalog)
        endpoint = _component_endpoint(operator, correction, direct)
        evidence = evaluate_p7_global_shadow(
            catalog,
            operator,
            endpoint,
            matrix=matrix,
            projected_residual=residual,
            expected_correction=correction,
            goal_gradients=gradients,
            ksp=ksp,
        )
        coverage = close_p7_global_saturation_coverage(
            catalog,
            (evidence,),
        )

        assert operator.audit["formal_backend_qualified"] is False
        assert "typed_live_compiled_operator_view_missing" in operator.audit[
            "formal_blockers"
        ]
        assert endpoint.audit["qualified_live_endpoint"] is False
        assert evidence.audit["formal_component_complete"] is False
        assert evidence.audit["actual_59_goal_adjoint_complete"] is True
        assert evidence.audit["converged_adjoint_count"] == 59
        assert evidence.audit["dwr_verified_goal_count"] == 59
        assert evidence.audit["correction_relative_residual"] < 1.0e-9
        assert (
            evidence.audit["maximum_adjoint_relative_residual"]
            < 1.0e-9
        )
        assert coverage.audit["all_p6_targets_and_orbits_covered"] is True
        assert coverage.audit["p6_saturation_status"] == "unknown"
        assert coverage.audit["measured_pass"] is False
        assert coverage.audit["measured_fail"] is False
        assert (
            coverage.audit["normalized_max"] > 0.5
        ) is failing
        assert coverage.audit["production_p7_rows"] == 0
        assert coverage.audit["next_production_plan"] is None
    finally:
        ksp.destroy()
        for vector in gradients.values():
            vector.destroy()
        correction.destroy()
        residual.destroy()
        matrix.destroy()


@pytest.mark.skipif(MPI.COMM_WORLD.size != 1, reason="serial contract test")
def test_mapping_audits_cannot_forge_formal_operator_or_endpoint() -> None:
    catalog = build_p7_global_coverage_catalog(
        _structural_bridge(formal=True)
    )
    (
        matrix,
        residual,
        correction,
        gradients,
        direct,
        ksp,
    ) = _petsc_system(failing=False)
    try:
        operator = _spoofed_mapping_operator(matrix, catalog)
        assert operator.audit["formal_backend_qualified"] is False
        assert "typed_live_compiled_operator_view_missing" in operator.audit[
            "formal_blockers"
        ]
        current = GoalVector.from_mapping(
            {goal_id: 0.0 for goal_id in FORMAL_GOAL_IDS}
        )
        shadow = GoalVector.from_mapping(direct)
        correction_sha = p7_global_shadow_vector_sha256(correction)
        forged = {
            "schema_version": P7_LIVE_ENDPOINT_AUDIT_SCHEMA,
            "actual_field_postprocess": True,
            "endpoint_values_caller_written": False,
            "operator_matrix_sha256": operator.audit["matrix_sha256"],
            "operator_receipt_sha256": operator.audit[
                "operator_receipt_sha256"
            ],
            "correction_sha256": correction_sha,
            "current_goal_vector_sha256": current.sha256,
            "shadow_goal_vector_sha256": shadow.sha256,
            "full_explicit_true_relative_residual": 0.0,
            "production_p7_rows_numbered": False,
        }
        with pytest.raises(
            ValueError,
            match="caller Mapping cannot qualify",
        ):
            build_p7_physical_endpoint_receipt(
                operator,
                current_goals=current,
                shadow_goals=shadow,
                correction_sha256=correction_sha,
                candidate_output_payload_sha256="6" * 64,
                watchdog_record_sha256="7" * 64,
                live_endpoint_audit=forged,
            )
    finally:
        ksp.destroy()
        for vector in gradients.values():
            vector.destroy()
        correction.destroy()
        residual.destroy()
        matrix.destroy()


@pytest.mark.skipif(MPI.COMM_WORLD.size != 1, reason="serial contract test")
def test_capability_report_names_live_runner_gaps() -> None:
    report = p7_global_shadow_backend_capability_report()

    assert report["p6_saturation_status"] == "unknown"
    assert report["measured_pass"] is False
    assert report["formal_goal_count"] == 59
    assert len(report["live_runner_integration_gaps"]) == 6
    assert report["formal_compiled_operator_receipt_reachable"] is False
    assert report["formal_physical_endpoint_receipt_reachable"] is False
    assert report["mapping_audits_can_grant_formal_credit"] is False
    assert report["production_p7_rows"] == 0
    assert report["selectable_as_production"] is False
