"""Focused actual-cell coverage for the economical Maxwell-harmonic route."""

from __future__ import annotations

import numpy as np
import pytest
import ufl
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
)
from src.solvers.hybrid_adaptive_impedance_mass import (
    build_actual_hcurl_cell_tangential_mass_provider,
)
from src.solvers.hybrid_adaptive_impedance_schwarz import (
    build_adaptive_impedance_schwarz_action,
)
from src.solvers.hybrid_maxwell_harmonic_economical import (
    PAPER_CANDIDATE_COUNT,
    _cell_affine_geometry,
    _oriented_vsh_coefficients,
    _physical_vsh_values,
    _radial_pullback,
    _vsh_cartesian,
    build_economical_maxwell_harmonic_space,
)


def _cell_tags(msh: mesh.Mesh) -> object:
    owned = int(msh.topology.index_map(msh.topology.dim).size_local)
    return mesh.meshtags(
        msh,
        msh.topology.dim,
        np.arange(owned, dtype=np.int32),
        np.ones(owned, dtype=np.int32),
    )


def _facet_tags(msh: mesh.Mesh, external_tag: int) -> object:
    tdim = msh.topology.dim
    fdim = tdim - 1
    msh.topology.create_connectivity(tdim, fdim)
    msh.topology.create_connectivity(fdim, tdim)
    count = int(msh.topology.index_map(fdim).size_local)
    facets = np.arange(count, dtype=np.int32)
    points = mesh.compute_midpoints(msh, fdim, facets)
    values = np.full(count, external_tag + 1, dtype=np.int32)
    values[np.isclose(points[:, 2], 0.0)] = external_tag
    return mesh.meshtags(msh, fdim, facets, values)


def _condensed(V: fem.FunctionSpace, tags: object) -> object:
    u = ufl.TrialFunction(V)
    v = ufl.TestFunction(V)
    dx = ufl.Measure("dx", domain=V.mesh, subdomain_data=tags)
    form = fem.form(
        (
            ufl.inner(ufl.curl(u), ufl.curl(v))
            + PETSc.ScalarType(2.0 - 0.15j) * ufl.inner(u, v)
        )
        * dx(1),
        dtype=PETSc.ScalarType,
        form_compiler_options={"quadrature_degree": 4},
    )
    return build_unconstrained_assembly_time_condensation(
        form,
        V,
        tags,
        materialize_global_matrix=True,
        retain_local_schur_for_matrix_free=True,
    )


@pytest.mark.skipif(
    MPI.COMM_WORLD.size not in (1, 2),
    reason="economical harmonic coverage is serial and MPI2",
)
def test_task040_economical_harmonic_columns_use_actual_oriented_trace() -> None:
    comm = MPI.COMM_WORLD
    msh = mesh.create_unit_cube(
        comm,
        1,
        1,
        1,
        cell_type=mesh.CellType.hexahedron,
        ghost_mode=mesh.GhostMode.shared_facet,
    )
    msh.geometry.x[:, 0] *= 2.0
    msh.geometry.x[:, 1] *= 3.0
    msh.geometry.x[:, 2] *= 4.0
    V = fem.functionspace(
        msh,
        element("N1curl", msh.basix_cell(), 2, dtype=default_real_type),
    )
    tags = _cell_tags(msh)
    facet_tags = _facet_tags(msh, 17)
    condensed = _condensed(V, tags)
    provider = None
    action = None
    space = None
    try:
        provider = build_actual_hcurl_cell_tangential_mass_provider(
            V,
            condensed,
            quadrature_degree=4,
        )
        action = build_adaptive_impedance_schwarz_action(
            condensed,
            condensed.matrix,
            raw_tangential_face_mass_by_cell=provider,
            beta=0.7 + 0.2j,
        )
        space = build_economical_maxwell_harmonic_space(
            V,
            condensed,
            action,
            provider,
            facet_tags,
            17,
        )
        owned = int(msh.topology.index_map(msh.topology.dim).size_local)
        owned_counts = comm.allgather(owned)
        assert sum(owned_counts) == 1
        if comm.size == 2:
            assert 0 in owned_counts
        diagnostics = space.diagnostics
        assert diagnostics["candidate_count_per_patch"] == PAPER_CANDIDATE_COUNT
        assert diagnostics["global_patch_count"] == 1
        assert diagnostics["generalized_eigenproblem"] is False
        assert diagnostics["global_prolongation_created"] is False
        assert diagnostics["coarse_matrix_created"] is False
        assert diagnostics["full_vector_numeric_allgather"] is False
        assert diagnostics["exact_provider_audit"]["status"] == (
            "verified_exact_provider"
        )
        assert len(space.local_patch_records) == owned
        if owned:
            record = space.local_patch_records[0]
            audit = record.audit
            assert record.columns is not None
            assert record.columns.shape[1] == audit["retained_rank"]
            assert audit["candidate_count"] == PAPER_CANDIDATE_COUNT
            assert 0 < audit["retained_rank"] < PAPER_CANDIDATE_COUNT
            assert audit["gamma_facet_count"] == 5
            assert audit["trace_positions_identity"] is True
            assert audit["vsh_tangential_defect"] <= 1.0e-10
            assert audit["vsh_cross_identity_defect"] <= 1.0e-10
            assert audit["radial_full_jacobian_identity_defect"] <= 1.0e-10
            assert audit["radial_tie_invariance_defect"] <= 1.0e-10
            assert audit["harmonic_solve_residual_max"] < 1.0e-10
            assert audit["generalized_eigenproblem"] is False
            center = np.asarray(audit["center"], dtype=np.float64)
            half_width = np.asarray(audit["half_width"], dtype=np.float64)
            _center, _half, affine, _offset, geometry_audit = _cell_affine_geometry(
                V,
                record.cell_index,
            )
            assert geometry_audit["positive_widths"] is True
            assert np.allclose(_half, (1.0, 1.5, 2.0))
            assert not np.allclose(affine, np.eye(3))
            assert audit["physical_to_reference_pullback"] == "A.T @ v_phys"
            assert audit["physical_reference_reconstruction_defect"] <= audit[
                "physical_reference_reconstruction_gate"
            ]
            tie_directions = (
                half_width / np.linalg.norm(half_width),
                np.asarray((half_width[0], half_width[1], 0.0))
                / np.linalg.norm(half_width[:2]),
            )
            for tie_direction in tie_directions:
                tie_vsh, _tie_keys, _tie_vsh_audit = _vsh_cartesian(
                    tie_direction[None, :]
                )
                _tie_values, tie_audit = _radial_pullback(
                    tie_direction[None, :],
                    half_width,
                    tie_vsh,
                )
                assert tie_audit["radial_tie_point_count"] == 1
                assert tie_audit["radial_tie_invariance_defect"] <= 1.0e-10
            oriented, trace_positions, _orientation_audit = (
                _oriented_vsh_coefficients(V, condensed, record.cell_index)
            )
            local_dofs = np.asarray(
                V.dofmap.cell_dofs(record.cell_index),
                dtype=np.int32,
            )
            for candidate in (0, 79, 159):
                field = fem.Function(V)
                field.interpolate(
                    lambda x, candidate=candidate: _physical_vsh_values(
                        np.asarray(x).T,
                        center,
                        half_width,
                        candidate,
                    ).T,
                    np.asarray([record.cell_index], dtype=np.int32),
                )
                np.testing.assert_allclose(
                    field.x.array[local_dofs[trace_positions]],
                    oriented[trace_positions, candidate],
                    rtol=1.0e-11,
                    atol=1.0e-11,
                )
    finally:
        if space is not None:
            space.destroy()
        if action is not None:
            action.destroy()
        if provider is not None:
            provider.destroy()
        condensed.destroy()
