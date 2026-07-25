"""Actual same-mesh scalar-to-H(curl) discrete-gradient authority tests."""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import basix
from basix.ufl import element
import numpy as np
import pytest
from mpi4py import MPI

from dolfinx import default_real_type, fem, mesh

from src.adaptivity.actual_physical_discrete_gradient_authority import (
    ActualPhysicalDiscreteGradientAuthority,
    build_actual_physical_discrete_gradient_authority,
)
from src.adaptivity.hcurl_regionwise_p import (
    fixed_trace_hcurl_ufl_element,
)
from src.adaptivity.p6_trace_complement_qualification import (
    qualify_p5_p6_nedelec_hexahedron_trace_complement,
)
from src.adaptivity.selective_p6_trace_exact_sequence import (
    build_exact_sequence_closed_p6_trace_numbering,
)
from src.common.config_3d import SimulationConfig3D
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.constraints.selective_p6_trace_mesh_catalog import (
    build_selective_p6_trace_mesh_catalog,
)


class _EmptyFacetTags:
    def find(self, _tag: int) -> np.ndarray:
        return np.empty(0, dtype=np.int32)


@pytest.fixture(scope="module")
def actual_gradient_fixture():
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
    full_p6_space = fem.functionspace(
        msh,
        element(
            "N1curl",
            msh.basix_cell(),
            6,
            lagrange_variant=basix.LagrangeVariant.legendre,
            dtype=default_real_type,
        ),
    )
    cfg = SimulationConfig3D(
        case_name="task035b_actual_discrete_gradient_authority",
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
    authority = build_actual_physical_discrete_gradient_authority(
        full_p6_hcurl_space=full_p6_space,
        catalog=catalog,
        qualification=qualification,
        coordinate_tolerance=1.0e-8,
    )
    return SimpleNamespace(
        mesh=msh,
        retained_space=retained_space,
        full_p6_space=full_p6_space,
        qualification=qualification,
        catalog=catalog,
        authority=authority,
    )


def test_actual_authority_is_built_from_dolfinx_matrices_not_caller_flags(
    actual_gradient_fixture,
) -> None:
    fixture = actual_gradient_fixture
    authority = fixture.authority
    comm = MPI.COMM_WORLD

    assert isinstance(authority, ActualPhysicalDiscreteGradientAuthority)
    assert authority.evidence_class == "actual_pde"
    assert authority.formal_actual_pde is True
    assert authority.actual_scalar_space_on_same_mesh is True
    assert authority.actual_discrete_gradient_coefficients is True
    assert authority.actual_periodic_floquet_pullback is True
    assert authority.dolfinx_version.startswith("0.10.")
    assert authority.basix_version.startswith("0.10.")
    assert authority.petsc_scalar_type == "complex128"
    assert authority.petsc_int_type == "int32"
    assert authority.scalar_q5_global_dofs == 396
    assert authority.scalar_q6_global_dofs == 637
    assert authority.hcurl_p6_global_dofs == 1680
    assert authority.audit["pass"] is True
    assert authority.audit["caller_qualification_booleans_accepted"] is False
    assert (
        authority.audit["partition_independent_authority_hash_claimed"]
        is False
    )
    assert authority.audit["full_p6_Maxwell_matrix_constructed"] is False
    assert authority.audit["inactive_p6_rows_allocated"] == 0
    assert authority.audit["ordinary_default_changed"] is False
    assert all(authority.audit["checks"].values())
    for value in (
        authority.interpolation_matrix_sha256,
        authority.discrete_gradient_matrix_sha256,
        authority.ordered_scalar_basis_sha256,
        authority.authority_sha256,
    ):
        assert len(value) == 64
        assert len(set(comm.allgather(value))) == 1

    parameters = inspect.signature(
        build_actual_physical_discrete_gradient_authority
    ).parameters
    assert not any("qualified" in name for name in parameters)
    assert not any(
        parameter.annotation is bool
        for parameter in parameters.values()
    )


def test_actual_edge_face_shell_ranks_coefficients_and_support(
    actual_gradient_fixture,
) -> None:
    authority = actual_gradient_fixture.authority
    catalog = actual_gradient_fixture.catalog

    assert len(authority.entity_shells) == 31
    edge_shells = [
        shell
        for shell in authority.entity_shells
        if shell.entity_kind == "edge"
    ]
    face_shells = [
        shell
        for shell in authority.entity_shells
        if shell.entity_kind == "face"
    ]
    assert len(edge_shells) == 20
    assert len(face_shells) == 11
    assert all(
        shell.interpolation_coefficients.shape == (5, 4)
        and shell.interpolation_rank == 4
        and shell.scalar_shell_basis.shape == (5, 1)
        for shell in edge_shells
    )
    assert all(
        shell.interpolation_coefficients.shape == (25, 16)
        and shell.interpolation_rank == 16
        and shell.scalar_shell_basis.shape == (25, 9)
        for shell in face_shells
    )
    assert all(
        not shell.interpolation_coefficients.flags.writeable
        and not shell.scalar_shell_basis.flags.writeable
        and len(shell.entity_shell_sha256) == 64
        for shell in authority.entity_shells
    )

    assert len(authority.orbit_evidence) == 18
    assert len(authority.rules) == 18
    edges = [
        orbit
        for orbit in authority.orbit_evidence
        if orbit.entity_kind == "edge"
    ]
    faces = [
        orbit
        for orbit in authority.orbit_evidence
        if orbit.entity_kind == "face"
    ]
    assert len(edges) == 10
    assert len(faces) == 8
    assert all(
        orbit.scalar_mode_count == orbit.discrete_gradient_rank == 1
        and len(orbit.gradient_singular_values) == 1
        for orbit in edges
    )
    assert all(
        orbit.scalar_mode_count == orbit.discrete_gradient_rank == 9
        and len(orbit.gradient_singular_values) == 9
        for orbit in faces
    )
    assert any(
        len(orbit.required_trace_representative_ids) > 1
        and any(
            catalog.entities[representative].entity_kind == "face"
            for representative in orbit.required_trace_representative_ids
        )
        for orbit in edges
    )
    assert all(
        orbit.required_trace_representative_ids
        == (orbit.anchor_trace_representative_id,)
        for orbit in faces
    )
    assert all(
        np.all(np.isfinite(block))
        and not block.flags.writeable
        for orbit in authority.orbit_evidence
        for block in orbit.representative_missing_gradient_blocks.values()
    )
    assert all(
        rule.gradient_map_sha256 == orbit.gradient_map_sha256
        and rule.required_trace_representative_ids
        == orbit.required_trace_representative_ids
        and rule.discrete_gradient_rank == orbit.discrete_gradient_rank
        for rule, orbit in zip(
            authority.rules,
            authority.orbit_evidence,
            strict=True,
        )
    )


def test_actual_gradient_commuting_leakage_and_exact_sequence_closure(
    actual_gradient_fixture,
) -> None:
    fixture = actual_gradient_fixture
    authority = fixture.authority
    audit = authority.audit

    for field in (
        "maximum_scalar_shell_orthogonality_error",
        "maximum_scalar_relation_commuting_error",
        "maximum_scalar_pullback_cycle_error",
        "maximum_Piola_Riesz_decomposition_error",
        "maximum_forbidden_trace_leakage",
        "maximum_periodic_gradient_commuting_error",
        "constant_interpolation_error",
        "constant_discrete_gradient_error",
    ):
        assert audit[field] <= 1.0e-8

    edge_rule = next(
        rule
        for rule in authority.rules
        if len(rule.required_trace_representative_ids) > 1
    )
    closed = build_exact_sequence_closed_p6_trace_numbering(
        entities=fixture.catalog.missing_trace_entities,
        periodic_relations=fixture.catalog.periodic_relations,
        gradient_rules=authority.rules,
        seed_trace_representative_ids=(
            edge_rule.anchor_trace_representative_id,
        ),
        full3d_base_dofs=0,
        active_base_rows=0,
        full3d_dof_limit=10_000,
    )
    assert set(edge_rule.required_trace_representative_ids).issubset(
        closed.closure.selected_trace_representative_ids
    )
    assert edge_rule.anchor_trace_representative_id in (
        closed.closure.selected_trace_representative_ids
    )
    assert closed.audit["pass"] is True
    assert closed.audit["inactive_p6_rows_numbered"] is False


def test_fixed_p5_trace_space_cannot_impersonate_full_v6(
    actual_gradient_fixture,
) -> None:
    fixture = actual_gradient_fixture
    with pytest.raises(
        RuntimeError,
        match="v6_is_legendre_N1curl",
    ):
        build_actual_physical_discrete_gradient_authority(
            full_p6_hcurl_space=fixture.retained_space,
            catalog=fixture.catalog,
            qualification=fixture.qualification,
            coordinate_tolerance=1.0e-8,
        )
    with pytest.raises(ValueError, match="fail-closed"):
        build_actual_physical_discrete_gradient_authority(
            full_p6_hcurl_space=fixture.full_p6_space,
            catalog=fixture.catalog,
            qualification=fixture.qualification,
            coordinate_tolerance=1.0e-8,
            algebra_tolerance=2.0e-10,
            support_tolerance=1.0e-3,
        )
