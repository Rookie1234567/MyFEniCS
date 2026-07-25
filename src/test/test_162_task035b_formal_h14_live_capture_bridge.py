from __future__ import annotations

from dataclasses import replace
import inspect
from types import MappingProxyType

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from src.adaptivity.actual_physical_discrete_gradient_authority import (
    ActualPhysicalDiscreteGradientAuthority,
    ActualScalarEntityShell,
    ActualScalarGradientOrbit,
)
from src.adaptivity.complement_schur_channel_dwr import ChannelGoal
from src.adaptivity.formal_h14_live_capture_bridge import (
    assess_formal_h14_live_capture_readiness,
    build_formal_h14_live_hook_bundle,
    capture_complete_missing_rhs,
    capture_live_full_p6_dtn_modes,
    capture_live_generalized_recovery,
    capture_live_nine_focus_goals,
    snapshot_live_full_p6_local_schur_capture,
)
from src.adaptivity.dtn_goal_adjoint import (
    replicated_adjoint_partition_content_identity,
)
from src.adaptivity.physical_missing_p6_action_only_complement import (
    ActualFocusChannelGoalBundle,
    FullP6LocalSchurClassCollector,
    PhysicalCellComplementActionLayout,
    PhysicalMissingP6ActionLayout,
    PhysicalStorageTraceDualProjection,
    ProjectedCondensedDual,
    ProjectedDtnComplementMode,
)
from src.adaptivity.selective_p6_trace_exact_sequence import (
    DiscreteGradientOrbitRule,
)
from src.solvers.hcurl_assembly_time_condensation import (
    AssemblyTimeCondensedSystem,
    CellRecoveryMap,
    TraceConstraintMap,
)


_SOURCE = "1" * 40
_MESH = "f" * 64
_CATALOG = "a" * 64
_TRACE_GEOMETRY = "b" * 64
_TRACE_BASIS = "c" * 64
_SCALAR_BASIS = "d" * 64
_GRADIENT = "e" * 64
_QUALIFICATION = "9" * 64
_COMPLEMENT = "8" * 64

_FOCUS = (
    ("T_m-4_n0_s_power", "real_power", "bottom", -4, "power", 2),
    (
        "T_m-4_n0_s_amplitude_real",
        "complex_amplitude_real",
        "bottom",
        -4,
        "amplitude_real",
        2,
    ),
    (
        "T_m-4_n0_s_amplitude_imag",
        "complex_amplitude_imag",
        "bottom",
        -4,
        "amplitude_imag",
        2,
    ),
    ("R_m-4_n0_s_power", "real_power", "top", -4, "power", 3),
    (
        "R_m-4_n0_s_amplitude_real",
        "complex_amplitude_real",
        "top",
        -4,
        "amplitude_real",
        3,
    ),
    (
        "R_m-4_n0_s_amplitude_imag",
        "complex_amplitude_imag",
        "top",
        -4,
        "amplitude_imag",
        3,
    ),
    ("R_m-5_n0_s_power", "real_power", "top", -5, "power", 4),
    (
        "R_m-5_n0_s_amplitude_real",
        "complex_amplitude_real",
        "top",
        -5,
        "amplitude_real",
        4,
    ),
    (
        "R_m-5_n0_s_amplitude_imag",
        "complex_amplitude_imag",
        "top",
        -5,
        "amplitude_imag",
        4,
    ),
)


def _actual_discrete_gradient() -> ActualPhysicalDiscreteGradientAuthority:
    rule = DiscreteGradientOrbitRule(
        scalar_orbit_id="edge-orbit-0",
        anchor_trace_representative_id=0,
        required_trace_representative_ids=(0,),
        scalar_mode_count=1,
        discrete_gradient_rank=1,
        ordered_scalar_basis_sha256=_SCALAR_BASIS,
        ordered_trace_basis_sha256=_TRACE_BASIS,
        gradient_map_sha256=_GRADIENT,
        periodic_orbit_closed=True,
        discrete_gradient_verified=True,
        gradient_map_binds_ordered_basis_identity=True,
    )
    shell = ActualScalarEntityShell(
        entity_id=0,
        entity_kind="edge",
        geometry_key=((0, 0, 0), (1, 0, 0)),
        q5_dimension=4,
        q6_dimension=5,
        scalar_shell_dimension=1,
        interpolation_coefficients=np.eye(5, 4, dtype=np.complex128),
        interpolation_singular_values=np.ones(4),
        interpolation_rank=4,
        interpolation_rank_tolerance=1.0e-12,
        scalar_shell_basis=np.eye(5, 1, k=-4, dtype=np.complex128),
        scalar_shell_orthogonality_error=0.0,
        entity_shell_sha256="2" * 64,
    )
    orbit = ActualScalarGradientOrbit(
        scalar_orbit_id="edge-orbit-0",
        anchor_trace_representative_id=0,
        entity_kind="edge",
        member_entity_ids=(0,),
        scalar_mode_count=1,
        representative_to_member_scalar_pullbacks={0: np.eye(1, dtype=np.complex128)},
        required_trace_representative_ids=(0,),
        representative_missing_gradient_blocks={
            0: np.ones((1, 1), dtype=np.complex128)
        },
        gradient_singular_values=np.ones(1),
        discrete_gradient_rank=1,
        discrete_gradient_rank_tolerance=1.0e-12,
        scalar_pullback_cycle_relative_error=0.0,
        periodic_gradient_commuting_relative_error=0.0,
        gradient_map_sha256=_GRADIENT,
    )
    authority_hash = "3" * 64
    interpolation_hash = "4" * 64
    matrix_gradient_hash = "5" * 64
    return ActualPhysicalDiscreteGradientAuthority(
        rules=(rule,),
        evidence_class="actual_pde",
        catalog_sha256=_CATALOG,
        trace_geometry_sha256=_TRACE_GEOMETRY,
        ordered_trace_basis_sha256=_TRACE_BASIS,
        ordered_scalar_basis_sha256=_SCALAR_BASIS,
        actual_scalar_space_on_same_mesh=True,
        actual_discrete_gradient_coefficients=True,
        actual_periodic_floquet_pullback=True,
        dolfinx_version="0.10.0",
        basix_version="0.10.0",
        petsc_scalar_type="complex128",
        petsc_int_type="int32",
        scalar_q5_global_dofs=4,
        scalar_q6_global_dofs=5,
        hcurl_p6_global_dofs=6,
        interpolation_matrix_sha256=interpolation_hash,
        discrete_gradient_matrix_sha256=matrix_gradient_hash,
        entity_shells=(shell,),
        orbit_evidence=(orbit,),
        authority_sha256=authority_hash,
        audit=MappingProxyType(
            {
                "pass": True,
                "evidence_origin": (
                    "internally_assembled_dolfinx_interpolation_and_gradient"
                ),
                "authority_sha256": authority_hash,
                "interpolation_matrix_sha256": interpolation_hash,
                "discrete_gradient_matrix_sha256": matrix_gradient_hash,
                "full_p6_Maxwell_matrix_constructed": False,
                "inactive_p6_rows_allocated": 0,
            }
        ),
    )


def _action_layout() -> PhysicalMissingP6ActionLayout:
    storage = np.arange(432, dtype=np.int64)
    low_coefficients = np.zeros((432, 2), dtype=np.complex128)
    low_coefficients[np.arange(432), np.arange(432) % 2] = 1.0
    high_coefficients = np.full(
        (432, 1),
        0.01 + 0.003j,
        dtype=np.complex128,
    )
    cell = PhysicalCellComplementActionLayout(
        local_cell=0,
        storage_original_dofs=storage,
        low_rows=np.asarray([0, 1], dtype=np.int64),
        high_rows=np.asarray([0], dtype=np.int64),
        low_coefficients=low_coefficients,
        high_coefficients=high_coefficients,
    )
    projections = {
        int(original): PhysicalStorageTraceDualProjection(
            storage_original_dof=int(original),
            low_rows=np.asarray([int(original) % 2], dtype=np.int64),
            low_coefficients=np.asarray([1.0], dtype=np.complex128),
            high_rows=np.asarray([0], dtype=np.int64),
            high_coefficients=np.asarray(
                [0.01 + 0.003j],
                dtype=np.complex128,
            ),
        )
        for original in storage
    }
    return PhysicalMissingP6ActionLayout(
        owned_cells=(cell,),
        storage_dual_projections=projections,
        retained_trace_rows=2,
        low_dimension=5,
        high_dimension=1,
        storage_trace_rows_per_cell=432,
        catalog_sha256=_CATALOG,
        trace_geometry_sha256=_TRACE_GEOMETRY,
        ordered_trace_basis_sha256=_TRACE_BASIS,
        qualification_sha256=_QUALIFICATION,
        complement_layout_sha256=_COMPLEMENT,
        audit=MappingProxyType(
            {
                "pass": True,
                "full_p6_trace_matrix_materialized": False,
                "inactive_missing_p6_rows_allocated": 0,
                "ordinary_default_changed": False,
            }
        ),
    )


def _generalized_system(
    action_layout: PhysicalMissingP6ActionLayout,
) -> AssemblyTimeCondensedSystem:
    matrix = PETSc.Mat().createAIJ(
        size=(action_layout.low_dimension, action_layout.low_dimension),
        nnz=1,
        comm=MPI.COMM_SELF,
    )
    matrix.setUp()
    for row in range(action_layout.low_dimension):
        matrix.setValue(row, row, PETSc.ScalarType(1.0))
    matrix.assemble()

    expansion = {
        original: (
            np.asarray([original % 2], dtype=PETSc.IntType),
            np.asarray(
                [1.0 + 0.01j * (original % 3)],
                dtype=np.complex128,
            ),
        )
        for original in action_layout.storage_dual_projections
    }
    qualification = {
        "pass": True,
        "catalog_sha256": _CATALOG,
        "trace_geometry_sha256": _TRACE_GEOMETRY,
        "ordered_trace_basis_sha256": _TRACE_BASIS,
    }
    constraints = TraceConstraintMap(
        owned_active_original_dofs=np.empty(0, dtype=PETSc.IntType),
        original_to_active={},
        expansion_by_original=expansion,
        full_trace_rows=len(expansion),
        active_rows=action_layout.retained_trace_rows,
        slave_rows=0,
        build_audit={
            "caller_qualification": qualification,
            "complete_storage_trace_pullback": True,
            "post_recovery_mpc_backsubstitution_forbidden": True,
            "inactive_mode_rows_allocated": False,
            "full_trace_matrix_allocated": False,
        },
        owned_active_rows=np.arange(
            action_layout.retained_trace_rows,
            dtype=PETSc.IntType,
        ),
        active_coordinates_are_original_trace_dofs=False,
    )
    class_key = ("fixture-class",)
    cell = CellRecoveryMap(
        interior_original_dofs=np.asarray([432], dtype=PETSc.IntType),
        trace_original_dofs=np.arange(432, dtype=PETSc.IntType),
        cell_local_dofs=np.arange(433, dtype=np.int32),
        raw_key=("fixture", 0),
        cell_permutation=0,
        interior_policy="fixture",
        class_key=class_key,
    )
    interior_from_trace = np.linspace(
        0.0,
        1.0,
        432,
        dtype=np.complex128,
    )[None, :]
    return AssemblyTimeCondensedSystem(
        matrix=matrix,
        owned_trace_original_dofs=np.arange(432, dtype=PETSc.IntType),
        original_to_trace={index: index for index in range(432)},
        trace_constraints=constraints,
        cell_recovery_maps=(cell,),
        interior_from_trace_by_class={
            class_key: interior_from_trace,
        },
        interior_lu_by_class={
            class_key: (
                np.ones((1, 1), dtype=np.complex128),
                np.zeros(1, dtype=np.int32),
            )
        },
        interior_rhs_projection_by_class={
            class_key: np.ones((1, 1), dtype=np.complex128)
        },
        interior_solution_embedding_by_class={
            class_key: np.ones((1, 1), dtype=np.complex128)
        },
        dual_interior_from_trace_by_class={class_key: interior_from_trace.conj()},
        appended_dual_interior_by_cell=({},),
        appended_dual_rows_registered=set(),
        interior_residual_projection_by_class={
            class_key: np.ones((1, 1), dtype=np.complex128)
        },
        full_rows=433,
        trace_rows=432,
        active_rows=action_layout.retained_trace_rows,
        appended_rows=(action_layout.low_dimension - action_layout.retained_trace_rows),
        interior_rows=1,
        active_interior_rows=0,
        build_audit={},
    )


def _dtn_modes() -> tuple[ProjectedDtnComplementMode, ...]:
    identities = (
        {"side": "bottom", "m": -4, "n": 0, "polarization": "s"},
        {"side": "top", "m": -4, "n": 0, "polarization": "s"},
        {"side": "top", "m": -5, "n": 0, "polarization": "s"},
    )
    return tuple(
        ProjectedDtnComplementMode(
            auxiliary_global_index=index + 2,
            traction_high=np.asarray(
                [0.3 * (index + 1) + 0.07j],
                dtype=np.complex128,
            ),
            ell_high=np.asarray(
                [0.11 - 0.02j * (index + 1)],
                dtype=np.complex128,
            ),
            denominator=1.0 + 0.05j * (index + 1),
            incident_projection_solver=0.2 - 0.01j * index,
            mode_identity=identity,
            full_p6_component_vectors_projected_live=True,
            physical_condensation_used=True,
        )
        for index, identity in enumerate(identities)
    )


def _dual(
    low: np.ndarray,
    high: np.ndarray,
    *,
    component: str,
    provenance_sha256: str,
    reduced_operator_sha256: str,
    complete: bool = False,
) -> ProjectedCondensedDual:
    audit: dict[str, object] = {
        "pass": True,
        "rhs_component": component,
        "live_full_p6_projection": True,
        "physical_riesz_piola_floquet_projection_used": True,
        "projection_provenance_sha256": provenance_sha256,
        "reduced_operator_sha256": reduced_operator_sha256,
        "full_p6_active_vector_allocated": False,
        "full_p6_trace_matrix_materialized": False,
        "inactive_missing_p6_rows_allocated": 0,
    }
    if complete:
        audit.update(
            {
                "complete_b_H": True,
                "complete_b_H_components": (
                    "volume_source",
                    "incident_traction",
                    "dtn_incident_auxiliary",
                ),
            }
        )
    return ProjectedCondensedDual(
        retained=np.asarray(low, dtype=np.complex128),
        missing=np.asarray(high, dtype=np.complex128),
        audit=MappingProxyType(audit),
    )


def _focus_bundle_and_reports(
    *,
    low_dimension: int,
    high_dimension: int,
    communicator: MPI.Intracomm = MPI.COMM_SELF,
) -> tuple[
    ActualFocusChannelGoalBundle,
    dict[str, dict[str, object]],
]:
    goals: list[ChannelGoal] = []
    reports: dict[str, dict[str, object]] = {}
    for index, (
        label,
        component,
        side,
        order,
        quantity,
        auxiliary,
    ) in enumerate(_FOCUS):
        goals.append(
            ChannelGoal(
                label=label,
                component=component,
                tolerance=1.0e-3,
                missing_gradient=np.zeros(
                    high_dimension,
                    dtype=np.complex128,
                ),
                retained_adjoint=np.linspace(
                    0.1,
                    0.5,
                    low_dimension,
                    dtype=np.complex128,
                )
                * (index + 1),
                actual_channel_gradient=True,
                retained_adjoint_qualified=True,
                baseline_signed_error=0.0,
            )
        )
        world_ranks = tuple(communicator.allgather(int(MPI.COMM_WORLD.rank)))
        boundaries = np.linspace(
            0,
            low_dimension,
            int(communicator.size) + 1,
            dtype=np.int64,
        )
        adjoint_identity = replicated_adjoint_partition_content_identity(
            goals[-1].retained_adjoint,
            {
                "partitions": [
                    {
                        "rank": rank,
                        "world_rank": world_ranks[rank],
                        "ownership_start": int(boundaries[rank]),
                        "ownership_end": int(boundaries[rank + 1]),
                    }
                    for rank in range(int(communicator.size))
                ]
            },
        )
        reports[label] = {
            "pass": False,
            "actual_discrete_system": True,
            "goal": {
                "label": label,
                "side": side,
                "m": order,
                "n": 0,
                "polarization": "s",
                "quantity": quantity,
            },
            "gradient_norm": 1.0 + 0.1 * index,
            "gradient_convention": {
                "power": "dJ=Re(g^H dx), g_aux=2*w*outgoing_amplitude",
                "amplitude_real": ("dJ=Re(g^H dx), g_aux=conj(boundary_phase)"),
                "amplitude_imag": ("dJ=Re(g^H dx), g_aux=i*conj(boundary_phase)"),
            }[quantity],
            "transpose_converged_reason": 1,
            "minus_converged_reason": 1,
            "plus_converged_reason": 1,
            "direct_tangent_converged_reason": 1,
            "adjoint_residual": {"relative_residual": 2.0e-12},
            "minus_primal_residual": {"relative_residual": 3.0e-12},
            "plus_primal_residual": {"relative_residual": 3.0e-12},
            "direct_tangent_residual": {"relative_residual": 4.0e-12},
            "direct_adjoint_relative_error": 2.0e-10,
            "direct_adjoint_absolute_error": 2.0e-13,
            "finite_difference_relative_error": 3.0e-9,
            "finite_difference_absolute_error": 3.0e-12,
            "augmented_global_index": auxiliary,
            "matrix_rows": low_dimension,
            "adjoint_content_identity": adjoint_identity,
            "adjoint_content_sha256": adjoint_identity["global_value_sha256"],
            "adjoint_partition_content_sha256": adjoint_identity[
                "global_content_sha256"
            ],
        }
    return (
        ActualFocusChannelGoalBundle(
            goals=tuple(goals),
            audit=MappingProxyType(
                {
                    "pass": True,
                    "evidence_class": "actual_pde",
                }
            ),
        ),
        reports,
    )


def _complete_capture_set(
    communicator: MPI.Intracomm = MPI.COMM_SELF,
):
    action = _action_layout()
    discrete_gradient = _actual_discrete_gradient()
    condensed = _generalized_system(action)
    recovery = capture_live_generalized_recovery(
        condensed_system=condensed,
        action_layout=action,
        source_commit=_SOURCE,
        mesh_sha256=_MESH,
    )

    collector = FullP6LocalSchurClassCollector()
    collector.observe(
        local_cell=0,
        class_key=("fixture-class",),
        oriented_storage_schur=np.eye(432, dtype=np.complex128),
    )
    local_schur = snapshot_live_full_p6_local_schur_capture(
        collector=collector,
        action_layout=action,
        communicator=communicator,
        source_commit=_SOURCE,
        mesh_sha256=_MESH,
    )
    dtn_modes = capture_live_full_p6_dtn_modes(
        modes=_dtn_modes(),
        action_layout=action,
        reduced_operator_sha256=recovery.reduced_operator_sha256,
        source_commit=_SOURCE,
        mesh_sha256=_MESH,
        communicator=communicator,
    )
    low_dimension = action.low_dimension
    volume = _dual(
        np.linspace(0.1, 0.5, low_dimension),
        np.asarray([0.4 + 0.1j]),
        component="volume_source",
        provenance_sha256=dtn_modes.provenance_sha256,
        reduced_operator_sha256=dtn_modes.reduced_operator_sha256,
    )
    incident = _dual(
        np.linspace(-0.2, 0.2, low_dimension),
        np.asarray([-0.05 + 0.02j]),
        component="incident_traction",
        provenance_sha256=dtn_modes.provenance_sha256,
        reduced_operator_sha256=dtn_modes.reduced_operator_sha256,
    )
    dtn = _dual(
        np.zeros(low_dimension),
        dtn_modes.missing_incident_rhs,
        component="dtn_incident_auxiliary",
        provenance_sha256=dtn_modes.provenance_sha256,
        reduced_operator_sha256=dtn_modes.reduced_operator_sha256,
    )
    complete = _dual(
        volume.retained + incident.retained + dtn.retained,
        volume.missing + incident.missing + dtn.missing,
        component="complete_b_H",
        provenance_sha256=dtn_modes.provenance_sha256,
        reduced_operator_sha256=dtn_modes.reduced_operator_sha256,
        complete=True,
    )
    complete_rhs = capture_complete_missing_rhs(
        complete=complete,
        components={
            "volume_source": volume,
            "incident_traction": incident,
            "dtn_incident_auxiliary": dtn,
        },
        dtn_modes=dtn_modes,
        reduced_operator_sha256=recovery.reduced_operator_sha256,
        communicator=communicator,
    )
    goal_bundle, goal_reports = _focus_bundle_and_reports(
        low_dimension=action.low_dimension,
        high_dimension=action.high_dimension,
        communicator=communicator,
    )
    focus_goals = capture_live_nine_focus_goals(
        bundle=goal_bundle,
        goal_reports=goal_reports,
        dtn_modes=dtn_modes,
        reduced_operator_sha256=recovery.reduced_operator_sha256,
        communicator=communicator,
    )
    captures = {
        "discrete_gradient": discrete_gradient,
        "action_layout": action,
        "local_schur": local_schur,
        "dtn_modes": dtn_modes,
        "complete_rhs": complete_rhs,
        "focus_goals": focus_goals,
        "recovery": recovery,
    }
    return condensed, captures


def test_missing_or_wrong_typed_live_capture_is_fail_closed() -> None:
    readiness = assess_formal_h14_live_capture_readiness()
    assert readiness.formal_actual_pde_ready is False
    assert readiness.typed_capture_contract_complete is False
    assert set(readiness.missing_capabilities) == {
        "actual_discrete_gradient",
        "physical_action_layout",
        "live_local_schur",
        "full_p6_dtn_modes",
        "complete_b_H",
        "nine_focus_goals",
        "generalized_recovery",
        "collective_validation_communicator",
    }
    with pytest.raises(RuntimeError, match="bundle remains fail-closed"):
        build_formal_h14_live_hook_bundle()

    wrong = assess_formal_h14_live_capture_readiness(
        discrete_gradient=object(),  # type: ignore[arg-type]
        communicator=MPI.COMM_SELF,
    )
    assert wrong.formal_actual_pde_ready is False
    assert "actual_discrete_gradient_wrong_type" in wrong.identity_mismatches


def test_capture_factories_have_no_caller_readiness_booleans() -> None:
    factories = (
        snapshot_live_full_p6_local_schur_capture,
        capture_live_full_p6_dtn_modes,
        capture_complete_missing_rhs,
        capture_live_nine_focus_goals,
        capture_live_generalized_recovery,
        assess_formal_h14_live_capture_readiness,
        build_formal_h14_live_hook_bundle,
    )
    forbidden = {
        "captured",
        "capture_complete",
        "formal",
        "formal_ready",
        "actual_pde_ready",
        "pass",
        "ready",
    }
    for factory in factories:
        parameters = inspect.signature(factory).parameters
        assert forbidden.isdisjoint(parameters)
        assert all(
            parameter.annotation not in {bool, "bool"}
            for parameter in parameters.values()
        )


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="serial typed formal-live-capture contract",
)
def test_complete_typed_capture_contract_cannot_become_formal_ready() -> None:
    condensed, captures = _complete_capture_set()
    try:
        readiness = assess_formal_h14_live_capture_readiness(
            **captures,
            communicator=MPI.COMM_SELF,
        )
        assert readiness.capability_snapshot_complete is True
        assert readiness.typed_capture_contract_complete is False
        assert readiness.formal_actual_pde_ready is False
        assert readiness.missing_capabilities == ()
        assert readiness.identity_mismatches == ()
        assert set(readiness.audit["production_hooks_missing"]) == {
            "formal_assembly_run_identity",
            "distributed_reduced_matrix_content_identity",
            "collective_live_observer_binding",
        }
        with pytest.raises(
            RuntimeError,
            match="formal h14 bundle remains fail-closed",
        ):
            build_formal_h14_live_hook_bundle(
                **captures,
                communicator=MPI.COMM_SELF,
            )

        for name in captures:
            incomplete = dict(captures)
            incomplete[name] = None
            rejected = assess_formal_h14_live_capture_readiness(
                **incomplete,
                communicator=MPI.COMM_SELF,
            )
            assert rejected.formal_actual_pde_ready is False
            assert rejected.typed_capture_contract_complete is False

        with pytest.raises(RuntimeError, match="payload hash"):
            replace(
                captures["dtn_modes"],
                provenance_sha256="0" * 64,
            )
    finally:
        condensed.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="serial raw focus-goal identity contract",
)
def test_focus_goal_raw_report_must_match_its_dtn_mode() -> None:
    condensed, captures = _complete_capture_set()
    try:
        bundle, reports = _focus_bundle_and_reports(
            low_dimension=captures["action_layout"].low_dimension,
            high_dimension=captures["action_layout"].high_dimension,
        )
        reports["T_m-4_n0_s_power"]["augmented_global_index"] = 3
        with pytest.raises(
            RuntimeError,
            match="DtN auxiliary identity differs",
        ):
            capture_live_nine_focus_goals(
                bundle=bundle,
                goal_reports=reports,
                dtn_modes=captures["dtn_modes"],
                reduced_operator_sha256=(captures["recovery"].reduced_operator_sha256),
                communicator=MPI.COMM_SELF,
            )
        reports["T_m-4_n0_s_power"]["augmented_global_index"] = 2
        reports["T_m-4_n0_s_power"]["pass"] = True
        reports["T_m-4_n0_s_power"]["adjoint_residual"] = {"relative_residual": 2.0e-6}
        with pytest.raises(
            RuntimeError,
            match="adjoint capability report is invalid",
        ):
            capture_live_nine_focus_goals(
                bundle=bundle,
                goal_reports=reports,
                dtn_modes=captures["dtn_modes"],
                reduced_operator_sha256=(captures["recovery"].reduced_operator_sha256),
                communicator=MPI.COMM_SELF,
            )
    finally:
        condensed.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="serial semantic live-capture rejection contract",
)
def test_caller_true_or_false_flags_never_upgrade_capability_evidence() -> None:
    condensed, captures = _complete_capture_set()
    try:
        for flag in (
            "full_p6_component_vectors_projected_live",
            "physical_condensation_used",
        ):
            modes = list(_dtn_modes())
            modes[0] = replace(modes[0], **{flag: False})
            snapshot = capture_live_full_p6_dtn_modes(
                modes=modes,
                action_layout=captures["action_layout"],
                reduced_operator_sha256=(captures["recovery"].reduced_operator_sha256),
                source_commit=_SOURCE,
                mesh_sha256=_MESH,
                communicator=MPI.COMM_SELF,
            )
            assert snapshot.evidence_class == "capability_only"
            assert snapshot.audit["formal_qualification"] is False
            assert (
                snapshot.audit["caller_declarations_used_for_formal_qualification"]
                is False
            )

        bundle, reports = _focus_bundle_and_reports(
            low_dimension=captures["action_layout"].low_dimension,
            high_dimension=captures["action_layout"].high_dimension,
        )
        for flag in (
            "actual_channel_gradient",
            "retained_adjoint_qualified",
        ):
            false_goal = replace(bundle.goals[0], **{flag: False})
            false_bundle = replace(
                bundle,
                goals=(false_goal, *bundle.goals[1:]),
            )
            snapshot = capture_live_nine_focus_goals(
                bundle=false_bundle,
                goal_reports=reports,
                dtn_modes=captures["dtn_modes"],
                reduced_operator_sha256=(captures["recovery"].reduced_operator_sha256),
                communicator=MPI.COMM_SELF,
            )
            assert snapshot.evidence_class == "capability_only"
            assert snapshot.audit["formal_qualification"] is False

        analytic_bundle = replace(
            bundle,
            audit=MappingProxyType(
                {
                    "pass": True,
                    "evidence_class": "analytic_fixture",
                }
            ),
        )
        snapshot = capture_live_nine_focus_goals(
            bundle=analytic_bundle,
            goal_reports=reports,
            dtn_modes=captures["dtn_modes"],
            reduced_operator_sha256=(captures["recovery"].reduced_operator_sha256),
            communicator=MPI.COMM_SELF,
        )
        readiness = assess_formal_h14_live_capture_readiness(
            **{**captures, "focus_goals": snapshot},
            communicator=MPI.COMM_SELF,
        )
        assert readiness.capability_snapshot_complete is True
        assert readiness.typed_capture_contract_complete is False
        assert readiness.formal_actual_pde_ready is False
    finally:
        condensed.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="serial adjoint content binding contract",
)
def test_adjoint_hash_drift_and_swapped_adjoint_are_rejected() -> None:
    condensed, captures = _complete_capture_set()
    try:
        bundle, reports = _focus_bundle_and_reports(
            low_dimension=captures["action_layout"].low_dimension,
            high_dimension=captures["action_layout"].high_dimension,
        )
        reports["T_m-4_n0_s_power"]["actual_discrete_system"] = False
        declared_false = capture_live_nine_focus_goals(
            bundle=bundle,
            goal_reports=reports,
            dtn_modes=captures["dtn_modes"],
            reduced_operator_sha256=(captures["recovery"].reduced_operator_sha256),
            communicator=MPI.COMM_SELF,
        )
        assert declared_false.evidence_class == "capability_only"
        assert declared_false.audit["formal_qualification"] is False

        bundle, reports = _focus_bundle_and_reports(
            low_dimension=captures["action_layout"].low_dimension,
            high_dimension=captures["action_layout"].high_dimension,
        )
        reports["T_m-4_n0_s_power"]["adjoint_content_sha256"] = "0" * 64
        with pytest.raises(
            RuntimeError,
            match="adjoint capability report is invalid",
        ):
            capture_live_nine_focus_goals(
                bundle=bundle,
                goal_reports=reports,
                dtn_modes=captures["dtn_modes"],
                reduced_operator_sha256=(captures["recovery"].reduced_operator_sha256),
                communicator=MPI.COMM_SELF,
            )

        bundle, reports = _focus_bundle_and_reports(
            low_dimension=captures["action_layout"].low_dimension,
            high_dimension=captures["action_layout"].high_dimension,
        )
        swapped = replace(
            bundle.goals[0],
            retained_adjoint=bundle.goals[1].retained_adjoint,
        )
        swapped_bundle = replace(
            bundle,
            goals=(swapped, *bundle.goals[1:]),
        )
        with pytest.raises(
            RuntimeError,
            match="adjoint capability report is invalid",
        ):
            capture_live_nine_focus_goals(
                bundle=swapped_bundle,
                goal_reports=reports,
                dtn_modes=captures["dtn_modes"],
                reduced_operator_sha256=(captures["recovery"].reduced_operator_sha256),
                communicator=MPI.COMM_SELF,
            )
    finally:
        condensed.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="serial complete b_H provenance contract",
)
def test_complete_rhs_tolerance_and_projection_audits_fail_closed() -> None:
    condensed, captures = _complete_capture_set()
    try:
        complete_capture = captures["complete_rhs"]
        with pytest.raises(ValueError, match="finite positive"):
            capture_complete_missing_rhs(
                complete=complete_capture.complete,
                components=complete_capture.components,
                dtn_modes=captures["dtn_modes"],
                reduced_operator_sha256=(captures["recovery"].reduced_operator_sha256),
                communicator=MPI.COMM_SELF,
                tolerance=np.nan,
            )
        components = dict(complete_capture.components)
        components["volume_source"] = replace(
            components["volume_source"],
            audit=MappingProxyType(
                {
                    **dict(components["volume_source"].audit),
                    "pass": False,
                }
            ),
        )
        snapshot = capture_complete_missing_rhs(
            complete=complete_capture.complete,
            components=components,
            dtn_modes=captures["dtn_modes"],
            reduced_operator_sha256=(captures["recovery"].reduced_operator_sha256),
            communicator=MPI.COMM_SELF,
        )
        assert snapshot.evidence_class == "capability_only"
        assert (
            snapshot.audit["caller_projection_audits_used_for_qualification"] is False
        )
        bad_complete = replace(
            complete_capture.complete,
            audit=MappingProxyType(
                {
                    **dict(complete_capture.complete.audit),
                    "pass": False,
                }
            ),
        )
        snapshot = capture_complete_missing_rhs(
            complete=bad_complete,
            components=complete_capture.components,
            dtn_modes=captures["dtn_modes"],
            reduced_operator_sha256=(captures["recovery"].reduced_operator_sha256),
            communicator=MPI.COMM_SELF,
        )
        assert snapshot.audit["formal_qualification"] is False
    finally:
        condensed.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="serial payload-tamper contract",
)
def test_every_capture_recomputes_its_numerical_payload_hash() -> None:
    condensed, captures = _complete_capture_set()
    try:
        changed_mode = replace(
            captures["dtn_modes"].modes[0],
            traction_high=np.asarray([99.0 + 3.0j]),
        )
        with pytest.raises(RuntimeError, match="payload hash/content is stale"):
            replace(
                captures["dtn_modes"],
                modes=(
                    changed_mode,
                    *captures["dtn_modes"].modes[1:],
                ),
            )

        changed_goal = replace(
            captures["focus_goals"].goals[0],
            retained_adjoint=(captures["focus_goals"].goals[0].retained_adjoint + 1.0),
        )
        with pytest.raises(
            RuntimeError,
            match="adjoint capability report is invalid",
        ):
            replace(
                captures["focus_goals"],
                goals=(
                    changed_goal,
                    *captures["focus_goals"].goals[1:],
                ),
            )

        key = next(iter(captures["local_schur"].schur_by_class))
        with pytest.raises(FloatingPointError, match="NaN or Inf"):
            replace(
                captures["local_schur"],
                schur_by_class=MappingProxyType(
                    {
                        key: np.full(
                            (432, 432),
                            np.nan + 0.0j,
                            dtype=np.complex128,
                        )
                    }
                ),
            )

        changed_components = dict(captures["complete_rhs"].components)
        changed_components["volume_source"] = replace(
            changed_components["volume_source"],
            retained=(changed_components["volume_source"].retained + 0.25),
        )
        with pytest.raises(RuntimeError, match="payload hash is stale"):
            replace(
                captures["complete_rhs"],
                components=changed_components,
            )

        recovery_key = next(iter(condensed.interior_from_trace_by_class))
        condensed.interior_from_trace_by_class[recovery_key][0, 0] += 0.125
        readiness = assess_formal_h14_live_capture_readiness(
            **captures,
            communicator=MPI.COMM_SELF,
        )
        assert readiness.capability_snapshot_complete is False
        assert "generalized_recovery_capability_payload_invalid" in (
            readiness.identity_mismatches
        )
    finally:
        condensed.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="serial finite recovery contract",
)
def test_generalized_recovery_rejects_nan_before_hashing() -> None:
    action = _action_layout()
    condensed = _generalized_system(action)
    try:
        class_key = next(iter(condensed.interior_from_trace_by_class))
        condensed.interior_from_trace_by_class[class_key][0, 0] = np.nan
        with pytest.raises(FloatingPointError, match="NaN or Inf"):
            capture_live_generalized_recovery(
                condensed_system=condensed,
                action_layout=action,
                source_commit=_SOURCE,
                mesh_sha256=_MESH,
            )
    finally:
        condensed.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="serial exact auxiliary-only gradient contract",
)
def test_focus_goal_missing_gradient_must_be_exactly_zero() -> None:
    condensed, captures = _complete_capture_set()
    try:
        bundle, reports = _focus_bundle_and_reports(
            low_dimension=captures["action_layout"].low_dimension,
            high_dimension=captures["action_layout"].high_dimension,
        )
        nonzero = replace(
            bundle.goals[0],
            missing_gradient=np.asarray([5.0e-15 + 0.0j]),
        )
        bundle = replace(
            bundle,
            goals=(nonzero, *bundle.goals[1:]),
        )
        with pytest.raises(
            RuntimeError,
            match="capability goal payload is invalid",
        ):
            capture_live_nine_focus_goals(
                bundle=bundle,
                goal_reports=reports,
                dtn_modes=captures["dtn_modes"],
                reduced_operator_sha256=(captures["recovery"].reduced_operator_sha256),
                communicator=MPI.COMM_SELF,
            )
    finally:
        condensed.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size < 2,
    reason="requires a multi-rank communicator",
)
def test_local_schur_collective_binds_world_membership_and_consensus() -> None:
    action = _action_layout()
    collector = FullP6LocalSchurClassCollector()
    collector.observe(
        local_cell=0,
        class_key=("fixture-class",),
        oriented_storage_schur=np.eye(432, dtype=np.complex128),
    )
    capture = snapshot_live_full_p6_local_schur_capture(
        collector=collector,
        action_layout=action,
        communicator=MPI.COMM_WORLD,
        source_commit=_SOURCE,
        mesh_sha256=_MESH,
    )
    assert capture.evidence_class == "capability_only"
    assert capture.communicator_identity["size"] == MPI.COMM_WORLD.size
    assert tuple(capture.communicator_identity["ordered_world_ranks"]) == tuple(
        MPI.COMM_WORLD.allgather(MPI.COMM_WORLD.rank)
    )
    assert len(set(MPI.COMM_WORLD.allgather(capture.collective_capture_sha256))) == 1


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 2,
    reason="MPI2 communicator-mismatch contract",
)
def test_comm_self_capture_is_rejected_by_world_assessment() -> None:
    condensed, captures = _complete_capture_set(MPI.COMM_SELF)
    try:
        readiness = assess_formal_h14_live_capture_readiness(
            **captures,
            communicator=MPI.COMM_WORLD,
        )
        assert readiness.formal_actual_pde_ready is False
        assert readiness.typed_capture_contract_complete is False
        assert readiness.capability_snapshot_complete is False
        assert any(
            "communicator_or_collective_mismatch" in mismatch
            for mismatch in readiness.identity_mismatches
        )
    finally:
        condensed.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 2,
    reason="MPI2 rank-consensus contract",
)
def test_rank_component_presence_mismatch_fails_collectively() -> None:
    condensed, captures = _complete_capture_set(MPI.COMM_SELF)
    try:
        per_rank = dict(captures)
        if MPI.COMM_WORLD.rank == 0:
            per_rank["dtn_modes"] = None
        readiness = assess_formal_h14_live_capture_readiness(
            **per_rank,
            communicator=MPI.COMM_WORLD,
        )
        assert readiness.capability_snapshot_complete is False
        assert "rank_component_presence_mismatch" in (readiness.identity_mismatches)
    finally:
        condensed.destroy()
