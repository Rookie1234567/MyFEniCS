"""Physical actual-mesh contracts for channel-DWR selective trace planning."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI

from dolfinx import fem, mesh

from src.adaptivity.complement_schur_channel_dwr import (
    ChannelGoal,
    ComplementSchurOperator,
)
from src.adaptivity.hcurl_regionwise_p import fixed_trace_hcurl_ufl_element
from src.adaptivity.p6_trace_complement_qualification import (
    qualify_p5_p6_nedelec_hexahedron_trace_complement,
)
from src.adaptivity.physical_channel_dwr_trace_selection import (
    PhysicalComplementDWRProvenance,
    PhysicalDiscreteGradientAuthority,
    build_physical_channel_dwr_trace_row_plan,
    build_physical_missing_trace_dwr_layout,
    check_physical_channel_dwr_trace_row_plan_record,
    evaluate_physical_channel_dwr,
    expand_missing_trace_complement_vector_to_entities,
    expand_missing_trace_complement_vector_to_full_p6_storage_entities,
    physical_channel_dwr_trace_row_plan_record,
    project_full_p6_storage_entity_duals_to_complement,
    project_physical_missing_trace_entity_vectors,
    select_rank_revealing_dwr_seed_orbits,
)
from src.adaptivity.selective_p6_trace_exact_sequence import (
    DiscreteGradientOrbitRule,
    ExactSequenceTraceBudgetExceeded,
)
from src.common.config_3d import SimulationConfig3D
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.constraints.selective_p6_trace_mesh_catalog import (
    build_selective_p6_trace_mesh_catalog,
)


class _EmptyFacetTags:
    def find(self, _tag: int) -> np.ndarray:
        return np.empty(0, dtype=np.int32)


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


@pytest.fixture(scope="module")
def physical_dwr_fixture():
    comm = MPI.COMM_WORLD
    msh = mesh.create_unit_cube(
        comm,
        2,
        1,
        1,
        cell_type=mesh.CellType.hexahedron,
    )
    retained_space = fem.functionspace(
        msh,
        fixed_trace_hcurl_ufl_element(5, 6),
    )
    cfg = SimulationConfig3D(
        case_name="task035b_physical_channel_dwr_selection",
        stage_case="stage4_block_grating",
        geometry_kind="rectangular_block_grating",
        lambda0=1.7,
        period_x=1.0,
        period_y=1.0,
        z_min=0.0,
        z_max=1.0,
        use_floquet_xy=True,
        incident_theta_deg=31.0,
        incident_phi_deg=19.0,
        polarization_kind="s",
        custom_polarization=None,
        nedelec_degree=6,
        nedelec_trace_degree=5,
        nedelec_interior_degree=6,
        mesh_cell_type="hexahedron",
    )
    floquet = build_double_floquet_mpc(
        retained_space,
        SimpleNamespace(
            mesh=msh,
            facet_tags=_EmptyFacetTags(),
        ),
        cfg,
    )
    assert floquet.phase_independent_topology is not None
    qualification = qualify_p5_p6_nedelec_hexahedron_trace_complement()
    catalog = build_selective_p6_trace_mesh_catalog(
        retained_trace_space=retained_space,
        phase_independent_topology=floquet.phase_independent_topology,
        qualification=qualification,
        coordinate_tolerance=1.0e-8,
        floquet_phase_x=cfg.floquet_phase_x,
        floquet_phase_y=cfg.floquet_phase_y,
        expected_qualification_sha256=(
            qualification.qualification_sha256
        ),
    )
    layout = build_physical_missing_trace_dwr_layout(
        catalog=catalog,
        qualification=qualification,
    )
    return SimpleNamespace(
        mesh=msh,
        retained_space=retained_space,
        qualification=qualification,
        catalog=catalog,
        layout=layout,
    )


def _focus_goals(
    *,
    high_dimension: int,
    low_dimension: int,
    target_indices: tuple[int, ...],
    protected_index: int | None = None,
) -> tuple[ChannelGoal, ...]:
    specifications = (
        ("T_m-4_n0_s_power", "real_power"),
        ("T_m-4_n0_s_amplitude_real", "complex_amplitude_real"),
        ("T_m-4_n0_s_amplitude_imag", "complex_amplitude_imag"),
        ("R_m-4_n0_s_power", "real_power"),
        ("R_m-4_n0_s_amplitude_real", "complex_amplitude_real"),
        ("R_m-4_n0_s_amplitude_imag", "complex_amplitude_imag"),
        ("R_m-5_n0_s_power", "real_power"),
        ("R_m-5_n0_s_amplitude_real", "complex_amplitude_real"),
        ("R_m-5_n0_s_amplitude_imag", "complex_amplitude_imag"),
    )
    goals: list[ChannelGoal] = []
    for index, (label, component) in enumerate(specifications):
        gradient = np.zeros(high_dimension, dtype=np.complex128)
        gradient[target_indices[index]] = (
            1.0j if component == "complex_amplitude_imag" else 1.0
        )
        goals.append(
            ChannelGoal(
                label=label,
                component=component,
                tolerance=1.0,
                missing_gradient=gradient,
                retained_adjoint=np.zeros(
                    low_dimension,
                    dtype=np.complex128,
                ),
                actual_channel_gradient=True,
                retained_adjoint_qualified=True,
                selection_target=True,
                protected=False,
                baseline_signed_error=0.5,
            )
        )
    protected_gradient = np.zeros(
        high_dimension,
        dtype=np.complex128,
    )
    if protected_index is not None:
        protected_gradient[int(protected_index)] = 1.0
    goals.append(
        ChannelGoal(
            label="T_m-2_n0_s_power",
            component="real_power",
            tolerance=1.0,
            missing_gradient=protected_gradient,
            retained_adjoint=np.zeros(
                low_dimension,
                dtype=np.complex128,
            ),
            actual_channel_gradient=True,
            retained_adjoint_qualified=True,
            selection_target=False,
            protected=True,
            baseline_signed_error=0.2,
        )
    )
    return tuple(goals)


def _evaluate_analytic_dwr(
    physical_dwr_fixture,
    *,
    target_indices: tuple[int, ...],
    residual: np.ndarray,
    protected_index: int | None = None,
):
    fixture = physical_dwr_fixture
    layout = fixture.layout
    identity = np.eye(layout.high_dimension, dtype=np.complex128)
    operator = ComplementSchurOperator(
        low_dimension=1,
        high_dimension=layout.high_dimension,
        a_hh=identity,
        a_hl=np.zeros(
            (layout.high_dimension, 1),
            dtype=np.complex128,
        ),
        a_lh=np.zeros(
            (1, layout.high_dimension),
            dtype=np.complex128,
        ),
        a_ll_solve=lambda rhs: rhs.copy(),
        a_ll_adjoint_solve=lambda rhs: rhs.copy(),
        schur_solve=lambda rhs: rhs.copy(),
        schur_adjoint_solve=lambda rhs: rhs.copy(),
    )
    provenance = PhysicalComplementDWRProvenance(
        evidence_class="analytic_fixture",
        source_commit="1" * 40,
        retained_candidate_record_sha256=_digest("retained-h14-record"),
        significant_channel_reference_sha256=_digest(
            "significant-channel-reference-v1"
        ),
        complement_layout_sha256=layout.layout_sha256,
        complement_storage_kind="analytic_fixture_dense",
        physical_missing_basis_tabulated=True,
        physical_entity_residual_projection_used=False,
        actual_enriched_residual_assembled=False,
        actual_complement_schur_actions=False,
        actual_complement_schur_inverse=False,
        actual_dtn_port_channel_gradients=False,
        retained_adjoints_qualified=False,
        full_p6_trace_matrix_materialized=False,
        inactive_p6_rows_allocated=0,
    )
    dwr = evaluate_physical_channel_dwr(
        layout=layout,
        provenance=provenance,
        schur=operator,
        missing_right_hand_side=residual,
        retained_state=np.zeros(1, dtype=np.complex128),
        goals=_focus_goals(
            high_dimension=layout.high_dimension,
            low_dimension=1,
            target_indices=target_indices,
            protected_index=protected_index,
        ),
    )
    return dwr


def _analytic_dwr(physical_dwr_fixture):
    fixture = physical_dwr_fixture
    layout = fixture.layout
    target_orbit = next(
        orbit
        for orbit in layout.orbits
        if orbit.entity_kind == "face"
        and len(orbit.member_entity_ids) > 1
    )
    target_indices = target_orbit.complement_indices[:9]
    residual = np.zeros(layout.high_dimension, dtype=np.complex128)
    for index, component_index in enumerate(target_indices):
        residual[component_index] = -0.2j if index % 3 == 2 else -0.2
    dwr = _evaluate_analytic_dwr(
        fixture,
        target_indices=target_indices,
        residual=residual,
    )
    return target_orbit, dwr


def _gradient_authority(physical_dwr_fixture):
    fixture = physical_dwr_fixture
    scalar_hash = _digest("ordered-global-scalar-basis")
    rules = tuple(
        DiscreteGradientOrbitRule(
            scalar_orbit_id=(
                f"fixture-scalar-{orbit.entity_kind}-"
                f"{orbit.representative_entity_id}"
            ),
            anchor_trace_representative_id=(
                orbit.representative_entity_id
            ),
            required_trace_representative_ids=(
                orbit.representative_entity_id,
            ),
            scalar_mode_count=(
                1 if orbit.entity_kind == "edge" else 9
            ),
            discrete_gradient_rank=(
                1 if orbit.entity_kind == "edge" else 9
            ),
            ordered_scalar_basis_sha256=scalar_hash,
            ordered_trace_basis_sha256=(
                fixture.catalog.ordered_trace_basis_sha256
            ),
            gradient_map_sha256=_digest(
                f"fixture-gradient-{orbit.representative_entity_id}"
            ),
            periodic_orbit_closed=True,
            discrete_gradient_verified=True,
            gradient_map_binds_ordered_basis_identity=True,
        )
        for orbit in fixture.catalog.all_inactive_orbit_numbering.orbits
    )
    return PhysicalDiscreteGradientAuthority(
        rules=rules,
        evidence_class="analytic_fixture",
        catalog_sha256=fixture.catalog.catalog_sha256,
        trace_geometry_sha256=fixture.catalog.trace_geometry_sha256,
        ordered_trace_basis_sha256=(
            fixture.catalog.ordered_trace_basis_sha256
        ),
        ordered_scalar_basis_sha256=scalar_hash,
        actual_scalar_space_on_same_mesh=False,
        actual_discrete_gradient_coefficients=False,
        actual_periodic_floquet_pullback=False,
    )


def _gradient_authority_with_dependency(
    physical_dwr_fixture,
    *,
    anchor_representative: int,
    required_representative: int,
) -> PhysicalDiscreteGradientAuthority:
    authority = _gradient_authority(physical_dwr_fixture)
    rules = tuple(
        replace(
            rule,
            required_trace_representative_ids=(
                rule.anchor_trace_representative_id,
                required_representative,
            ),
            gradient_map_sha256=_digest(
                "fixture-gradient-with-closure-"
                f"{anchor_representative}-{required_representative}"
            ),
        )
        if (
            rule.anchor_trace_representative_id
            == anchor_representative
        )
        else rule
        for rule in authority.rules
    )
    return replace(authority, rules=rules)


def test_physical_layout_binds_actual_piola_riesz_floquet_orbits(
    physical_dwr_fixture,
) -> None:
    fixture = physical_dwr_fixture
    layout = fixture.layout
    comm = MPI.COMM_WORLD

    assert layout.audit["pass"] is True
    assert layout.high_dimension == 170
    assert len(layout.orbits) == 18
    assert len(layout.entity_to_representative) == 31
    assert len(layout.canonical_logical_modes) == 170
    assert set(layout.logical_mode_to_index.values()) == set(range(170))
    assert layout.catalog_sha256 == fixture.catalog.catalog_sha256
    assert (
        layout.ordered_trace_basis_sha256
        == fixture.catalog.ordered_trace_basis_sha256
    )
    assert all(layout.audit["checks"].values())
    assert len(set(comm.allgather(layout.layout_sha256))) == 1
    assert layout.audit["full_p6_trace_matrix_constructed"] is False
    assert layout.audit["inactive_p6_rows_allocated"] == 0


def test_physical_entity_dual_projection_uses_actual_pullbacks(
    physical_dwr_fixture,
) -> None:
    fixture = physical_dwr_fixture
    layout = fixture.layout
    entity_vectors = {
        member: np.full(
            len(orbit.complement_indices),
            complex(member + 1, -(member + 2)),
            dtype=np.complex128,
        )
        for orbit in layout.orbits
        for member in orbit.member_entity_ids
    }
    projected = project_physical_missing_trace_entity_vectors(
        layout,
        entity_vectors=entity_vectors,
    )
    for orbit in layout.orbits:
        expected = sum(
            (
                orbit.representative_to_member_pullbacks[member]
                .conj()
                .T
                @ entity_vectors[member]
            )
            for member in orbit.member_entity_ids
        )
        np.testing.assert_allclose(
            projected[np.asarray(orbit.complement_indices)],
            expected,
            rtol=2.0e-13,
            atol=2.0e-13,
        )

    complement = np.linspace(
        0.1,
        1.0,
        layout.high_dimension,
        dtype=np.float64,
    ).astype(np.complex128)
    expanded = expand_missing_trace_complement_vector_to_entities(
        layout,
        complement_vector=complement,
    )
    for orbit in layout.orbits:
        representative = complement[
            np.asarray(orbit.complement_indices)
        ]
        for member in orbit.member_entity_ids:
            np.testing.assert_allclose(
                expanded[member],
                orbit.representative_to_member_pullbacks[member]
                @ representative,
            )

    with pytest.raises(ValueError, match="complete trace catalog"):
        project_physical_missing_trace_entity_vectors(
            layout,
            entity_vectors={
                key: value
                for key, value in entity_vectors.items()
                if key != 0
            },
        )

    storage_duals = {
        entity.entity_id: np.linspace(
            0.1,
            1.0,
            (
                fixture.qualification.edge.enriched_dimension
                if entity.entity_kind == "edge"
                else fixture.qualification.face.enriched_dimension
            ),
            dtype=np.float64,
        ).astype(np.complex128)
        for entity in fixture.catalog.entities
    }
    projected_storage = (
        project_full_p6_storage_entity_duals_to_complement(
            layout,
            catalog=fixture.catalog,
            qualification=fixture.qualification,
            storage_entity_duals=storage_duals,
        )
    )
    expected_missing_duals = {
        entity.entity_id: (
            getattr(
                fixture.qualification,
                entity.entity_kind,
            ).missing_basis.conj().T
            @ storage_duals[entity.entity_id]
        )
        for entity in fixture.catalog.entities
    }
    np.testing.assert_allclose(
        projected_storage,
        project_physical_missing_trace_entity_vectors(
            layout,
            entity_vectors=expected_missing_duals,
        ),
    )
    storage_expansion = (
        expand_missing_trace_complement_vector_to_full_p6_storage_entities(
            layout,
            catalog=fixture.catalog,
            qualification=fixture.qualification,
            complement_vector=complement,
        )
    )
    for entity in fixture.catalog.entities:
        shell = getattr(
            fixture.qualification,
            entity.entity_kind,
        )
        np.testing.assert_allclose(
            storage_expansion[entity.entity_id],
            shell.missing_basis @ expanded[entity.entity_id],
        )


def test_fixture_dwr_to_exact_sequence_owner_row_plan_has_no_inactive_rows(
    physical_dwr_fixture,
) -> None:
    fixture = physical_dwr_fixture
    target_orbit, dwr = _analytic_dwr(fixture)
    seeds = select_rank_revealing_dwr_seed_orbits(
        dwr,
        maximum_seed_orbits=2,
    )
    assert seeds.seed_orbit_ids == (target_orbit.orbit_id,)
    assert seeds.seed_representative_entity_ids == (
        target_orbit.representative_entity_id,
    )
    assert seeds.target_matrix_rank == 1
    assert seeds.rank_span_complete is True

    result = build_physical_channel_dwr_trace_row_plan(
        catalog=fixture.catalog,
        dwr_analysis=dwr,
        seed_selection=seeds,
        discrete_gradient=_gradient_authority(fixture),
        full3d_base_dofs=82_315,
        full3d_dof_limit=90_000,
    )
    assert result.audit["pass"] is True
    assert result.audit["formal_actual_pde_selection_input"] is False
    assert result.audit["formal_candidate_passed"] is False
    assert result.row_plan.actual_mesh is True
    assert result.row_plan.active_base_rows == 370
    assert result.row_plan.quotient_active_increment == 20
    assert result.row_plan.active_rows == 390
    assert result.row_plan.full3d_equivalent_increment == (
        20 * len(target_orbit.member_entity_ids)
    )
    assert result.audit["inactive_missing_petsc_rows"] == 0
    assert (
        result.row_plan.audit["checks"][
            "inactive_modes_have_no_row_descriptors"
        ]
        is True
    )
    selected = {
        descriptor.representative_entity_id
        for descriptor in result.row_plan.selected_row_descriptors
    }
    assert selected == {target_orbit.representative_entity_id}

    record = physical_channel_dwr_trace_row_plan_record(result)
    assert record["formal_actual_pde_selection_input"] is False
    assert record["formal_candidate_passed"] is False
    assert record["complement"]["inactive_p6_rows_allocated"] == 0
    assert record["row_plan"]["inactive_missing_petsc_rows"] == 0
    assert set(record["remaining_gates"].values()) == {"not_run"}
    json.dumps(record, sort_keys=True, allow_nan=False)
    checked = check_physical_channel_dwr_trace_row_plan_record(record)
    assert checked["pass"] is True
    assert checked["recomputes_selection_sha256"] is True
    assert (
        record["formal_h14_minimum_wiring"][
            "existing_h14_offline_reconstruction"
        ]
        == "not_authorized"
    )
    assert "stage4_retain_dual_recovery_context=False" in (
        record["formal_h14_minimum_wiring"][
            "existing_h14_offline_reconstruction_reason"
        ]
    )

    tampered = json.loads(json.dumps(record))
    tampered["row_plan"]["active_rows"] += 1
    tampered_check = check_physical_channel_dwr_trace_row_plan_record(
        tampered
    )
    assert tampered_check["pass"] is False
    assert "active_rows_recompute" in tampered_check["failures"]
    tampered_hash = json.loads(json.dumps(record))
    tampered_hash["authorities"]["selection_sha256"] = _digest(
        "tampered-selection"
    )
    tampered_hash_check = (
        check_physical_channel_dwr_trace_row_plan_record(tampered_hash)
    )
    assert tampered_hash_check["pass"] is False
    assert "selection_sha256_recomputed" in (
        tampered_hash_check["failures"]
    )
    tampered_seed_identity = json.loads(json.dumps(record))
    alternate_orbit_id = next(
        orbit["orbit_id"]
        for orbit in tampered_seed_identity["ranked_orbits"]
        if orbit["orbit_id"]
        != tampered_seed_identity["seed_selection"]["seed_orbit_ids"][0]
    )
    tampered_seed_identity["seed_selection"]["seed_orbit_ids"][0] = (
        alternate_orbit_id
    )
    tampered_seed_check = check_physical_channel_dwr_trace_row_plan_record(
        tampered_seed_identity
    )
    assert tampered_seed_check["pass"] is False
    assert "seed_orbit_ids_match_representatives" in (
        tampered_seed_check["failures"]
    )
    tampered_closed_audit = json.loads(json.dumps(record))
    first_goal = next(
        iter(
            tampered_closed_audit[
                "closed_selection_dwr_audit"
            ]["goal_aggregates"]
        )
    )
    tampered_closed_audit["closed_selection_dwr_audit"][
        "goal_aggregates"
    ][first_goal]["aggregate_normalized_signed_correction"] += 0.1
    tampered_closed_check = (
        check_physical_channel_dwr_trace_row_plan_record(
            tampered_closed_audit
        )
    )
    assert tampered_closed_check["pass"] is False
    assert "closed_selection_goal_aggregates_recomputed" in (
        tampered_closed_check["failures"]
    )


def test_exact_sequence_closure_reaudits_the_complete_whole_orbit_set(
    physical_dwr_fixture,
) -> None:
    fixture = physical_dwr_fixture
    target_orbit, dwr = _analytic_dwr(fixture)
    closure_orbit = next(
        orbit
        for orbit in fixture.layout.orbits
        if orbit.representative_entity_id
        != target_orbit.representative_entity_id
    )
    seeds = select_rank_revealing_dwr_seed_orbits(
        dwr,
        maximum_seed_orbits=2,
    )
    result = build_physical_channel_dwr_trace_row_plan(
        catalog=fixture.catalog,
        dwr_analysis=dwr,
        seed_selection=seeds,
        discrete_gradient=_gradient_authority_with_dependency(
            fixture,
            anchor_representative=(
                target_orbit.representative_entity_id
            ),
            required_representative=(
                closure_orbit.representative_entity_id
            ),
        ),
        full3d_base_dofs=82_315,
        full3d_dof_limit=90_000,
    )

    closed_audit = result.audit["closed_selection_dwr_audit"]
    assert closed_audit["pass"] is True
    assert closed_audit["closure_added_orbit_ids"] == [
        closure_orbit.orbit_id
    ]
    assert set(closed_audit["selected_orbit_ids"]) == {
        target_orbit.orbit_id,
        closure_orbit.orbit_id,
    }
    assert all(closed_audit["checks"].values())
    selected_physical_entities = {
        member
        for orbit in (target_orbit, closure_orbit)
        for member in orbit.member_entity_ids
    }
    assert set(
        result.exact_sequence_numbering.closure
        .selected_physical_entity_ids
    ) == selected_physical_entities
    selected_descriptors = {
        descriptor.representative_entity_id
        for descriptor in result.row_plan.selected_row_descriptors
    }
    assert selected_descriptors == {
        target_orbit.representative_entity_id,
        closure_orbit.representative_entity_id,
    }


def test_closure_added_protected_regression_fails_before_owner_rows(
    physical_dwr_fixture,
    monkeypatch,
) -> None:
    fixture = physical_dwr_fixture
    target_orbit = next(
        orbit
        for orbit in fixture.layout.orbits
        if orbit.entity_kind == "face"
        and len(orbit.member_entity_ids) > 1
    )
    closure_orbit = next(
        orbit
        for orbit in fixture.layout.orbits
        if orbit.representative_entity_id
        != target_orbit.representative_entity_id
    )
    target_indices = target_orbit.complement_indices[:9]
    residual = np.zeros(
        fixture.layout.high_dimension,
        dtype=np.complex128,
    )
    for index, component_index in enumerate(target_indices):
        residual[component_index] = -0.2j if index % 3 == 2 else -0.2
    protected_index = closure_orbit.complement_indices[0]
    residual[protected_index] = 0.4
    dwr = _evaluate_analytic_dwr(
        fixture,
        target_indices=target_indices,
        residual=residual,
        protected_index=protected_index,
    )
    seeds = select_rank_revealing_dwr_seed_orbits(
        dwr,
        maximum_seed_orbits=2,
    )
    assert seeds.seed_orbit_ids == (target_orbit.orbit_id,)

    def _owner_rows_must_not_be_built(*_args, **_kwargs):
        raise AssertionError(
            "owner row allocation ran before closed DWR audit"
        )

    monkeypatch.setattr(
        "src.adaptivity.physical_channel_dwr_trace_selection."
        "build_selected_p6_trace_orbit_owner_inputs",
        _owner_rows_must_not_be_built,
    )
    with pytest.raises(
        RuntimeError,
        match="aggregate_protected_non_regression",
    ):
        build_physical_channel_dwr_trace_row_plan(
            catalog=fixture.catalog,
            dwr_analysis=dwr,
            seed_selection=seeds,
            discrete_gradient=_gradient_authority_with_dependency(
                fixture,
                anchor_representative=(
                    target_orbit.representative_entity_id
                ),
                required_representative=(
                    closure_orbit.representative_entity_id
                ),
            ),
            full3d_base_dofs=82_315,
            full3d_dof_limit=90_000,
        )


def test_exact_sequence_closure_budget_overflow_fails_closed(
    physical_dwr_fixture,
) -> None:
    fixture = physical_dwr_fixture
    target_orbit, dwr = _analytic_dwr(fixture)
    closure_orbit = next(
        orbit
        for orbit in fixture.layout.orbits
        if orbit.representative_entity_id
        != target_orbit.representative_entity_id
    )
    seeds = select_rank_revealing_dwr_seed_orbits(
        dwr,
        maximum_seed_orbits=2,
    )
    base_dofs = 1_000
    seed_cost = len(target_orbit.complement_indices) * len(
        target_orbit.member_entity_ids
    )
    with pytest.raises(ExactSequenceTraceBudgetExceeded):
        build_physical_channel_dwr_trace_row_plan(
            catalog=fixture.catalog,
            dwr_analysis=dwr,
            seed_selection=seeds,
            discrete_gradient=_gradient_authority_with_dependency(
                fixture,
                anchor_representative=(
                    target_orbit.representative_entity_id
                ),
                required_representative=(
                    closure_orbit.representative_entity_id
                ),
            ),
            full3d_base_dofs=base_dofs,
            full3d_dof_limit=base_dofs + seed_cost,
        )


def test_incomplete_rrqr_target_rank_fails_closed(
    physical_dwr_fixture,
) -> None:
    fixture = physical_dwr_fixture
    target_orbits = tuple(
        orbit
        for orbit in fixture.layout.orbits
        if orbit.entity_kind == "face"
    )[:2]
    assert len(target_orbits) == 2
    target_indices = tuple(
        (
            target_orbits[0].complement_indices[index]
            if index < 5
            else target_orbits[1].complement_indices[index - 5]
        )
        for index in range(9)
    )
    residual = np.zeros(
        fixture.layout.high_dimension,
        dtype=np.complex128,
    )
    for index, component_index in enumerate(target_indices):
        residual[component_index] = -0.2j if index % 3 == 2 else -0.2
    dwr = _evaluate_analytic_dwr(
        fixture,
        target_indices=target_indices,
        residual=residual,
    )
    seeds = select_rank_revealing_dwr_seed_orbits(
        dwr,
        maximum_seed_orbits=1,
    )
    assert seeds.target_matrix_rank == 2
    assert seeds.rank_span_complete is False

    with pytest.raises(
        RuntimeError,
        match="seed_rank_span_is_complete",
    ):
        build_physical_channel_dwr_trace_row_plan(
            catalog=fixture.catalog,
            dwr_analysis=dwr,
            seed_selection=seeds,
            discrete_gradient=_gradient_authority(fixture),
            full3d_base_dofs=82_315,
            full3d_dof_limit=90_000,
        )


def test_actual_pde_provenance_and_focus_goal_contract_fail_closed(
    physical_dwr_fixture,
) -> None:
    fixture = physical_dwr_fixture
    layout = fixture.layout
    with pytest.raises(
        RuntimeError,
        match="legacy caller-supplied actual PDE complement provenance is disabled",
    ):
        PhysicalComplementDWRProvenance(
            evidence_class="actual_pde",
            source_commit="2" * 40,
            retained_candidate_record_sha256=_digest("candidate"),
            significant_channel_reference_sha256=_digest("reference"),
            complement_layout_sha256=layout.layout_sha256,
            complement_storage_kind="analytic_fixture_dense",
            physical_missing_basis_tabulated=True,
            physical_entity_residual_projection_used=True,
            actual_enriched_residual_assembled=True,
            actual_complement_schur_actions=True,
            actual_complement_schur_inverse=True,
            actual_dtn_port_channel_gradients=True,
            retained_adjoints_qualified=True,
            full_p6_trace_matrix_materialized=False,
            inactive_p6_rows_allocated=0,
        )
    with pytest.raises(
        RuntimeError,
        match="legacy caller-supplied actual PDE complement provenance is disabled",
    ):
        PhysicalComplementDWRProvenance(
            evidence_class="actual_pde",
            source_commit="2" * 40,
            retained_candidate_record_sha256=_digest("candidate"),
            significant_channel_reference_sha256=_digest("reference"),
            complement_layout_sha256=layout.layout_sha256,
            complement_storage_kind="action_only",
            physical_missing_basis_tabulated=True,
            physical_entity_residual_projection_used=True,
            actual_enriched_residual_assembled=True,
            actual_complement_schur_actions=True,
            actual_complement_schur_inverse=True,
            actual_dtn_port_channel_gradients=True,
            retained_adjoints_qualified=True,
            full_p6_trace_matrix_materialized=False,
            inactive_p6_rows_allocated=0,
        )
    with pytest.raises(RuntimeError, match="full-p6 trace matrix"):
        PhysicalComplementDWRProvenance(
            evidence_class="analytic_fixture",
            source_commit="2" * 40,
            retained_candidate_record_sha256=_digest("candidate"),
            significant_channel_reference_sha256=_digest("reference"),
            complement_layout_sha256=layout.layout_sha256,
            complement_storage_kind="analytic_fixture_dense",
            physical_missing_basis_tabulated=True,
            physical_entity_residual_projection_used=False,
            actual_enriched_residual_assembled=False,
            actual_complement_schur_actions=False,
            actual_complement_schur_inverse=False,
            actual_dtn_port_channel_gradients=False,
            retained_adjoints_qualified=False,
            full_p6_trace_matrix_materialized=True,
            inactive_p6_rows_allocated=0,
        )

    _target_orbit, dwr = _analytic_dwr(fixture)
    bad_provenance = replace(
        dwr.provenance,
        complement_layout_sha256=_digest("wrong-layout"),
    )
    operator = ComplementSchurOperator(
        low_dimension=1,
        high_dimension=layout.high_dimension,
        a_hh=np.eye(layout.high_dimension),
        a_hl=np.zeros((layout.high_dimension, 1)),
        a_lh=np.zeros((1, layout.high_dimension)),
        a_ll_solve=lambda rhs: rhs,
        a_ll_adjoint_solve=lambda rhs: rhs,
        schur_solve=lambda rhs: rhs,
        schur_adjoint_solve=lambda rhs: rhs,
    )
    with pytest.raises(RuntimeError, match="layout hashes differ"):
        evaluate_physical_channel_dwr(
            layout=layout,
            provenance=bad_provenance,
            schur=operator,
            missing_right_hand_side=np.zeros(layout.high_dimension),
            retained_state=np.zeros(1),
            goals=tuple(dwr.algebraic.goals.values()),
        )

    valid_goals = _focus_goals(
        high_dimension=layout.high_dimension,
        low_dimension=1,
        target_indices=next(
            orbit.complement_indices[:9]
            for orbit in layout.orbits
            if orbit.entity_kind == "face"
        ),
    )
    with pytest.raises(RuntimeError, match="lacks independent focus"):
        evaluate_physical_channel_dwr(
            layout=layout,
            provenance=dwr.provenance,
            schur=operator,
            missing_right_hand_side=np.zeros(layout.high_dimension),
            retained_state=np.zeros(1),
            goals=valid_goals[:-2],
        )


def test_discrete_gradient_authority_is_hash_bound(
    physical_dwr_fixture,
) -> None:
    fixture = physical_dwr_fixture
    authority = _gradient_authority(fixture)
    bad_rule = replace(
        authority.rules[0],
        ordered_trace_basis_sha256=_digest("wrong-trace-basis"),
    )
    with pytest.raises(RuntimeError, match="physical trace basis"):
        replace(
            authority,
            rules=(bad_rule, *authority.rules[1:]),
        )
    with pytest.raises(
        RuntimeError,
        match="actual physical discrete-gradient authority is incomplete",
    ):
        replace(
            authority,
            evidence_class="actual_pde",
        )


def test_h14_authority_files_are_present_and_hashable() -> None:
    root = Path(__file__).resolve().parents[2]
    records = root / (
        "benchmarks/cases/095_high_order_local_hp_resource_envelope/records"
    )
    h14 = records / "fixed_p5trace_p6interior_h14_directional_z_mpi8.json"
    reference = records / "significant_channel_reference_v1.json"
    for path in (h14, reference):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload
        assert len(hashlib.sha256(path.read_bytes()).hexdigest()) == 64
    h14_payload = json.loads(h14.read_text(encoding="utf-8"))
    assert h14_payload["candidate"]["num_nedelec_dofs"] == 82_315
    assert h14_payload["candidate"]["nedelec_trace_degree_resolved"] == 5
    assert h14_payload["candidate"]["nedelec_interior_degree_resolved"] == 6
    assert (
        h14_payload["diffraction_channel_comparison"][
            "significant_power_pass_count"
        ]
        == 7
    )
    assert (
        h14_payload["diffraction_channel_comparison"][
            "significant_complex_amplitude_pass_count"
        ]
        == 9
    )
