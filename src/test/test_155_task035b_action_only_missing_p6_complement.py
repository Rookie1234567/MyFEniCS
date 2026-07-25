"""Focused contracts for the physical action-only missing-p6 complement."""

from __future__ import annotations

from dataclasses import replace
import hashlib
from types import MappingProxyType, SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from src.adaptivity.physical_channel_dwr_trace_selection import (
    PhysicalComplementDWRProvenance,
    PhysicalMissingTraceDWRLayout,
    PhysicalMissingTraceDWROrbit,
    evaluate_physical_channel_dwr,
)
from src.adaptivity.physical_missing_p6_action_only_complement import (
    FullP6LocalSchurClassCollector,
    PhysicalMissingP6ActionOnlyComplementSystem,
    PhysicalMissingP6ComplementActions,
    PhysicalMissingP6MaxwellActions,
    ProjectedDtnComplementActions,
    ReplicatedPetscLowFactorSolve,
    build_actual_focus_channel_goal_bundle,
    build_physical_missing_p6_action_layout,
    build_projected_dtn_complement_mode,
    formal_h14_action_only_hook_requirements,
    project_full_p6_condensed_trace_dual,
)
from src.constraints.selective_p6_trace_expansion import (
    ActualSelectiveP6TraceExpansion,
    PhysicalCellP6TraceExpansion,
)
from src.solvers.hcurl_assembly_time_condensation import CallerTraceExpansion


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


@pytest.fixture
def complement_fixture():
    comm = MPI.COMM_WORLD
    row_index = np.arange(12, dtype=np.float64)
    coefficient_matrix = (
        np.eye(12, dtype=np.complex128)
        + 0.004
        * np.outer(
            np.cos(0.31 * (row_index + 1.0))
            + 0.2j * np.sin(0.17 * (row_index + 1.0)),
            np.sin(0.23 * (row_index + 1.0)),
        )
    )
    active_rows = np.arange(12, dtype=PETSc.IntType)
    originals = np.arange(10, 22, dtype=PETSc.IntType)
    expansion_by_original = {
        int(original): (active_rows.copy(), coefficient_matrix[row].copy())
        for row, original in enumerate(originals)
    }
    caller = CallerTraceExpansion(
        owned_active_rows=(
            active_rows.copy()
            if comm.rank == 0
            else np.empty(0, dtype=PETSc.IntType)
        ),
        expansion_by_original=expansion_by_original,
        full_trace_rows=12,
        active_rows=12,
        qualification_audit=MappingProxyType(
            {
                "pass": True,
                "full_trace_matrix_constructed": False,
                "inactive_modes_have_no_petsc_rows": True,
            }
        ),
    )
    owned_cells = (
        (
            PhysicalCellP6TraceExpansion(
                local_cell=0,
                storage_original_dofs=originals,
                active_rows=active_rows,
                coefficient_matrix=coefficient_matrix,
            ),
        )
        if comm.rank == 0
        else ()
    )
    diagnostic = ActualSelectiveP6TraceExpansion(
        caller_trace_expansion=caller,
        entity_expansions=(),
        owned_cell_expansions=owned_cells,
        storage_expansion_by_original=expansion_by_original,
        base_logical_rows={
            **{(7, mode): mode for mode in range(5)},
            **{(8, mode): 5 + mode for mode in range(5)},
        },
        selected_missing_logical_rows={(7, 0): 10, (8, 0): 11},
        full_p6_storage_trace_rows=12,
        p5_periodic_quotient_rows=10,
        selected_missing_rows=2,
        active_rows=12,
        audit=MappingProxyType(
            {
                "pass": True,
                "matrix_constructed": False,
                "inactive_missing_petsc_rows": 0,
            }
        ),
    )
    orbits = tuple(
        PhysicalMissingTraceDWROrbit(
            representative_entity_id=representative,
            entity_kind="edge",
            member_entity_ids=(representative,),
            complement_indices=(index,),
            representative_to_member_pullbacks={
                representative: np.eye(1, dtype=np.complex128)
            },
            orbit_id=f"edge:{representative}",
        )
        for index, representative in enumerate((7, 8))
    )
    physical = PhysicalMissingTraceDWRLayout(
        orbits=orbits,
        canonical_logical_modes=((7, 0), (8, 0)),
        logical_mode_to_index={(7, 0): 0, (8, 0): 1},
        entity_to_representative={7: 7, 8: 8},
        high_dimension=2,
        catalog_sha256=_digest("catalog"),
        trace_geometry_sha256=_digest("geometry"),
        ordered_trace_basis_sha256=_digest("trace-basis"),
        qualification_sha256=_digest("qualification"),
        layout_sha256=_digest("layout"),
        audit=MappingProxyType({"pass": True}),
    )
    action_layout = build_physical_missing_p6_action_layout(
        diagnostic_expansion=diagnostic,
        physical_layout=physical,
        retained_active_row_by_logical_mode={
            **{(7, mode): mode for mode in range(5)},
            **{(8, mode): 5 + mode for mode in range(5)},
        },
        retained_system_rows=11,
        communicator=comm,
        expected_storage_trace_rows_per_cell=12,
    )
    storage_schur = (
        np.diag(2.5 + 0.04 * row_index + 0.02j * (row_index - 5.0))
        + 0.003
        * np.outer(
            np.sin(0.19 * (row_index + 1.0)),
            np.cos(0.27 * (row_index + 1.0))
            + 0.1j * np.sin(0.11 * (row_index + 1.0)),
        )
    )
    local_classes = {"fixture-class": storage_schur} if comm.rank == 0 else {}
    cell_classes = {0: "fixture-class"} if comm.rank == 0 else {}
    maxwell = PhysicalMissingP6MaxwellActions(
        layout=action_layout,
        storage_schur_by_class=local_classes,
        cell_class_keys=cell_classes,
        communicator=comm,
        evidence_class="analytic_fixture",
        captured_by_live_local_schur_observer=False,
    )
    right_components = (
        np.asarray([0.14 + 0.03j, -0.07j]),
        np.asarray([-0.04, 0.09 + 0.02j]),
    )
    left_components = (
        np.asarray([0.08 - 0.02j, 0.05]),
        np.asarray([0.03j, -0.11 + 0.01j]),
    )
    mode = build_projected_dtn_complement_mode(
        auxiliary_global_index=10,
        right_high_components=right_components,
        left_high_components=left_components,
        traction_components=(1.2 - 0.1j, -0.35 + 0.2j),
        electric_components=(0.7 + 0.05j, -0.2j),
        denominator=1.7,
        incident_projection_solver=0.31 - 0.07j,
        mode_identity={
            "side": "top",
            "m": -4,
            "n": 0,
            "polarization": "s",
        },
        full_p6_component_vectors_projected_live=False,
        physical_condensation_used=True,
    )
    dtn = ProjectedDtnComplementActions(
        low_dimension=11,
        retained_trace_rows=10,
        high_dimension=2,
        modes=(mode,),
        evidence_class="analytic_fixture",
    )
    actions = PhysicalMissingP6ComplementActions(
        maxwell=maxwell,
        dtn=dtn,
    )
    c_low = coefficient_matrix[:, :10]
    c_high = coefficient_matrix[:, 10:]
    a_hh = c_high.conj().T @ storage_schur @ c_high
    a_hl = np.zeros((2, 11), dtype=np.complex128)
    a_hl[:, :10] = c_high.conj().T @ storage_schur @ c_low
    a_hl[:, 10] -= mode.traction_high
    a_lh = np.zeros((11, 2), dtype=np.complex128)
    a_lh[:10, :] = c_low.conj().T @ storage_schur @ c_high
    a_lh[10, :] -= np.conj(mode.ell_high) / mode.denominator
    return SimpleNamespace(
        comm=comm,
        coefficients=coefficient_matrix,
        diagnostic=diagnostic,
        physical=physical,
        layout=action_layout,
        storage_schur=storage_schur,
        maxwell=maxwell,
        mode=mode,
        dtn=dtn,
        actions=actions,
        a_hh=a_hh,
        a_hl=a_hl,
        a_lh=a_lh,
    )


def _goal_inputs(low_dimension: int):
    reports = {}
    adjoints = {}
    tolerances = {}
    errors = {}
    specifications = (
        ("T", -4, "power"),
        ("T", -4, "amplitude_real"),
        ("T", -4, "amplitude_imag"),
        ("R", -4, "power"),
        ("R", -4, "amplitude_real"),
        ("R", -4, "amplitude_imag"),
        ("R", -5, "power"),
        ("R", -5, "amplitude_real"),
        ("R", -5, "amplitude_imag"),
    )
    conventions = {
        "power": "g_aux=2*w*outgoing_amplitude",
        "amplitude_real": "g_aux=conj(boundary_phase)",
        "amplitude_imag": "g_aux=i*conj(boundary_phase)",
    }
    for index, (prefix, order, quantity) in enumerate(specifications):
        label = f"{prefix}_m{order}_n0_s_{quantity}"
        reports[label] = {
            "pass": True,
            "actual_discrete_system": True,
            "matrix_rows": low_dimension,
            "augmented_global_index": low_dimension - 1,
            "gradient_convention": (
                "dJ=Re(g^H dx), " + conventions[quantity]
            ),
            "adjoint_residual": {"relative_residual": 1.0e-13},
            "goal": {
                "label": label,
                "side": "bottom" if prefix == "T" else "top",
                "m": order,
                "n": 0,
                "polarization": "s",
                "quantity": quantity,
            },
        }
        adjoint = np.zeros(low_dimension, dtype=np.complex128)
        adjoint[-1] = complex(0.4 + 0.03 * index, -0.2 + 0.01 * index)
        adjoints[label] = adjoint
        tolerances[label] = 0.05
        errors[label] = 0.08 if index % 3 != 2 else -0.08
    return reports, adjoints, tolerances, errors


def test_layout_and_condensed_dual_projection_are_inactive_row_free(
    complement_fixture,
) -> None:
    fixture = complement_fixture
    layout = fixture.layout
    assert layout.audit["pass"] is True
    assert layout.audit["all_missing_expansion_role"] == (
        "diagnostic_coordinate_authority_only"
    )
    assert layout.audit["full_p6_trace_matrix_materialized"] is False
    assert layout.audit["inactive_missing_p6_rows_allocated"] == 0

    all_rows = np.arange(10, 22, dtype=np.int64)
    owned_rows = all_rows[
        np.arange(len(all_rows), dtype=np.int64) % fixture.comm.size
        == fixture.comm.rank
    ]
    trace_values = np.asarray(
        [complex(0.1 * row, -0.03 * row) for row in owned_rows],
        dtype=np.complex128,
    )
    correction_index = np.arange(12, dtype=np.float64)
    correction = (
        0.01 * np.cos(0.3 * (correction_index + 1.0))
        + 0.006j * np.sin(0.2 * (correction_index + 1.0))
    )
    projected = project_full_p6_condensed_trace_dual(
        layout,
        owned_storage_trace_rows=owned_rows,
        owned_storage_trace_values=trace_values,
        cell_storage_trace_corrections=(
            {0: correction} if fixture.comm.rank == 0 else {}
        ),
        communicator=fixture.comm,
    )
    global_trace = np.asarray(
        [complex(0.1 * row, -0.03 * row) for row in all_rows],
        dtype=np.complex128,
    )
    combined = global_trace + correction
    np.testing.assert_allclose(
        projected.retained[:10],
        fixture.coefficients[:, :10].conj().T @ combined,
        rtol=2.0e-13,
        atol=2.0e-13,
    )
    np.testing.assert_allclose(
        projected.missing,
        fixture.coefficients[:, 10:].conj().T @ combined,
        rtol=2.0e-13,
        atol=2.0e-13,
    )
    assert projected.retained[10] == 0.0
    assert projected.audit["full_p6_active_vector_allocated"] is False


def test_streamed_maxwell_and_projected_dtn_match_explicit_blocks(
    complement_fixture,
) -> None:
    fixture = complement_fixture
    high = np.asarray([0.3 - 0.1j, -0.2 + 0.05j])
    low_index = np.arange(11, dtype=np.float64)
    low = (
        0.04 * np.cos(0.21 * (low_index + 1.0))
        + 0.03j * np.sin(0.17 * (low_index + 1.0))
    )
    np.testing.assert_allclose(
        fixture.actions.a_hh(high),
        fixture.a_hh @ high,
        rtol=2.0e-13,
        atol=2.0e-13,
    )
    np.testing.assert_allclose(
        fixture.actions.a_hl(low),
        fixture.a_hl @ low,
        rtol=2.0e-13,
        atol=2.0e-13,
    )
    np.testing.assert_allclose(
        fixture.actions.a_lh(high),
        fixture.a_lh @ high,
        rtol=2.0e-13,
        atol=2.0e-13,
    )
    np.testing.assert_allclose(
        fixture.actions.a_hh_adjoint(high),
        fixture.a_hh.conj().T @ high,
        rtol=2.0e-13,
        atol=2.0e-13,
    )
    np.testing.assert_allclose(
        fixture.actions.a_hl_adjoint(high),
        fixture.a_hl.conj().T @ high,
        rtol=2.0e-13,
        atol=2.0e-13,
    )
    np.testing.assert_allclose(
        fixture.actions.a_lh_adjoint(low),
        fixture.a_lh.conj().T @ low,
        rtol=2.0e-13,
        atol=2.0e-13,
    )
    np.testing.assert_allclose(
        fixture.dtn.missing_incident_right_hand_side(),
        -fixture.mode.traction_high
        * fixture.mode.incident_projection_solver,
    )
    assert fixture.actions.audit["global_full_p6_matrix_materialized"] is False


def test_action_only_schur_focus_goals_and_existing_dwr_kernel(
    complement_fixture,
) -> None:
    fixture = complement_fixture
    low_diagonal = (
        3.0
        + 0.07 * np.arange(11, dtype=np.float64)
        + 0.02j * (np.arange(11, dtype=np.float64) - 5.0)
    )
    a_ll = np.diag(low_diagonal)
    dense_schur = (
        fixture.a_hh
        - fixture.a_hl @ np.linalg.solve(a_ll, fixture.a_lh)
    )
    system = PhysicalMissingP6ActionOnlyComplementSystem(
        actions=fixture.actions,
        low_solve=lambda rhs: rhs / low_diagonal,
        low_adjoint_solve=lambda rhs: rhs / np.conj(low_diagonal),
        gmres_relative_tolerance=1.0e-13,
        explicit_relative_residual_tolerance=2.0e-12,
        gmres_restart=2,
        gmres_maximum_cycles=10,
    )
    rhs = np.asarray([0.13 - 0.04j, -0.09 + 0.02j])
    np.testing.assert_allclose(
        system.schur_action(rhs),
        dense_schur @ rhs,
        rtol=2.0e-13,
        atol=2.0e-13,
    )
    np.testing.assert_allclose(
        system.schur_adjoint_action(rhs),
        dense_schur.conj().T @ rhs,
        rtol=2.0e-13,
        atol=2.0e-13,
    )
    np.testing.assert_allclose(
        system.solve(rhs),
        np.linalg.solve(dense_schur, rhs),
        rtol=2.0e-12,
        atol=2.0e-12,
    )
    np.testing.assert_allclose(
        system.solve_adjoint(rhs),
        np.linalg.solve(dense_schur.conj().T, rhs),
        rtol=2.0e-12,
        atol=2.0e-12,
    )
    assert all(report.pass_gate for report in system.reports)

    reports, adjoints, tolerances, errors = _goal_inputs(11)
    bundle = build_actual_focus_channel_goal_bundle(
        goal_reports=reports,
        retained_adjoints=adjoints,
        tolerances=tolerances,
        baseline_signed_errors=errors,
        retained_trace_rows=10,
        low_dimension=11,
        high_dimension=2,
        evidence_class="analytic_fixture",
    )
    assert len(bundle.goals) == 9
    assert all(
        np.count_nonzero(goal.missing_gradient) == 0
        for goal in bundle.goals
    )
    operator = system.complement_operator()
    first_goal = bundle.goals[0]
    goal_complement = operator.goal_complement(
        missing_gradient=first_goal.missing_gradient,
        retained_adjoint=first_goal.retained_adjoint,
    )
    assert np.linalg.norm(goal_complement) > 0.0

    provenance = PhysicalComplementDWRProvenance(
        evidence_class="analytic_fixture",
        source_commit="1" * 40,
        retained_candidate_record_sha256=_digest("retained"),
        significant_channel_reference_sha256=_digest("reference"),
        complement_layout_sha256=fixture.physical.layout_sha256,
        complement_storage_kind="action_only",
        physical_missing_basis_tabulated=True,
        physical_entity_residual_projection_used=True,
        actual_enriched_residual_assembled=False,
        actual_complement_schur_actions=False,
        actual_complement_schur_inverse=False,
        actual_dtn_port_channel_gradients=True,
        retained_adjoints_qualified=True,
        full_p6_trace_matrix_materialized=False,
        inactive_p6_rows_allocated=0,
    )
    analysis = evaluate_physical_channel_dwr(
        layout=fixture.physical,
        provenance=provenance,
        schur=operator,
        missing_right_hand_side=rhs,
        retained_state=np.asarray(
            [
                0.01 * np.cos(0.2 * (index + 1.0))
                + 0.008j * np.sin(0.13 * (index + 1.0))
                for index in range(11)
            ],
            dtype=np.complex128,
        ),
        goals=bundle.goals,
        identity_tolerance=2.0e-10,
    )
    assert analysis.audit["pass"] is True
    assert analysis.audit["formal_actual_pde"] is False
    assert len(analysis.algebraic.goals) == 9


def test_live_class_collector_and_petsc_low_factor_adapter() -> None:
    collector = FullP6LocalSchurClassCollector(
        storage_trace_rows_per_cell=2
    )
    local_schur = np.asarray(
        [[2.0 + 0.1j, 0.2], [-0.05j, 1.7 - 0.03j]],
        dtype=np.complex128,
    )
    collector.observe(
        local_cell=0,
        class_key=("material", 1),
        oriented_storage_schur=local_schur,
    )
    collector.observe(
        local_cell=1,
        class_key=("material", 1),
        oriented_storage_schur=local_schur,
    )
    with pytest.raises(RuntimeError, match="class tensor differs"):
        collector.observe(
            local_cell=2,
            class_key=("material", 1),
            oriented_storage_schur=local_schur
            + np.diag(np.asarray([1.0e-3, 0.0])),
        )
    assert collector.audit["class_count"] == 1
    assert collector.audit["cell_count"] == 2

    matrix_values = np.asarray(
        [[3.0 + 0.1j, 0.2], [-0.05j, 2.4 - 0.08j]],
        dtype=np.complex128,
    )
    matrix = PETSc.Mat().createDense(
        (2, 2),
        comm=PETSc.COMM_SELF,
    )
    matrix.setValues(
        np.arange(2, dtype=PETSc.IntType),
        np.arange(2, dtype=PETSc.IntType),
        matrix_values,
    )
    matrix.assemble()
    solver = PETSc.KSP().create(PETSc.COMM_SELF)
    solver.setOperators(matrix)
    solver.setType(PETSc.KSP.Type.PREONLY)
    solver.getPC().setType(PETSc.PC.Type.LU)
    solver.setUp()
    adapter = ReplicatedPetscLowFactorSolve(
        matrix=matrix,
        solver=solver,
        explicit_relative_residual_tolerance=1.0e-12,
        evidence_class="analytic_fixture",
    )
    rhs = np.asarray([0.7 - 0.2j, -0.3 + 0.1j])
    np.testing.assert_allclose(
        adapter.solve(rhs),
        np.linalg.solve(matrix_values, rhs),
        rtol=2.0e-13,
        atol=2.0e-13,
    )
    np.testing.assert_allclose(
        adapter.solve_adjoint(rhs),
        np.linalg.solve(matrix_values.conj().T, rhs),
        rtol=2.0e-13,
        atol=2.0e-13,
    )
    assert len(adapter.reports) == 2
    assert adapter.audit["new_factor_created"] is False
    solver.destroy()
    matrix.destroy()


def test_formal_contracts_fail_closed_without_live_complete_evidence(
    complement_fixture,
) -> None:
    fixture = complement_fixture
    incomplete = replace(
        fixture.diagnostic,
        selected_missing_logical_rows={(7, 0): 10},
    )
    with pytest.raises(RuntimeError, match="every physical missing"):
        build_physical_missing_p6_action_layout(
            diagnostic_expansion=incomplete,
            physical_layout=fixture.physical,
            retained_active_row_by_logical_mode={
                **{(7, mode): mode for mode in range(5)},
                **{(8, mode): 5 + mode for mode in range(5)},
            },
            retained_system_rows=11,
            communicator=fixture.comm,
            expected_storage_trace_rows_per_cell=12,
        )

    materialized_audit = dict(fixture.diagnostic.audit)
    materialized_audit["matrix_constructed"] = True
    materialized = replace(
        fixture.diagnostic,
        audit=MappingProxyType(materialized_audit),
    )
    with pytest.raises(RuntimeError, match="must not be inserted"):
        build_physical_missing_p6_action_layout(
            diagnostic_expansion=materialized,
            physical_layout=fixture.physical,
            retained_active_row_by_logical_mode={
                **{(7, mode): mode for mode in range(5)},
                **{(8, mode): 5 + mode for mode in range(5)},
            },
            retained_system_rows=11,
            communicator=fixture.comm,
            expected_storage_trace_rows_per_cell=12,
        )

    reports, adjoints, tolerances, errors = _goal_inputs(11)
    reports.pop("R_m-5_n0_s_amplitude_imag")
    with pytest.raises(RuntimeError, match="lack a focus channel"):
        build_actual_focus_channel_goal_bundle(
            goal_reports=reports,
            retained_adjoints=adjoints,
            tolerances=tolerances,
            baseline_signed_errors=errors,
            retained_trace_rows=10,
            low_dimension=11,
            high_dimension=2,
            evidence_class="analytic_fixture",
        )

    reports, adjoints, tolerances, errors = _goal_inputs(11)
    with pytest.raises(RuntimeError, match="actual PDE evidence is disabled"):
        build_actual_focus_channel_goal_bundle(
            goal_reports=reports,
            retained_adjoints=adjoints,
            tolerances=tolerances,
            baseline_signed_errors=errors,
            retained_trace_rows=10,
            low_dimension=11,
            high_dimension=2,
            evidence_class="actual_pde",
        )

    hooks = formal_h14_action_only_hook_requirements()
    assert hooks["formal_actual_pde_ready"] is False
    assert hooks["actual_pde_evidence_class_enabled"] is False
    assert len(hooks["required_live_hooks"]) == 7
    assert hooks["old_h14_offline_reconstruction_authorized"] is False
    assert hooks["full_p6_trace_matrix_materialized"] is False
