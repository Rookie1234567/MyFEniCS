"""Focused actual-cell tangential mass authority checks for Task040."""

from __future__ import annotations

import numpy as np
import pytest
import ufl
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from dolfinx.fem import petsc as fem_petsc
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


def _cell_tags(msh: mesh.Mesh) -> object:
    tdim = msh.topology.dim
    owned = int(msh.topology.index_map(tdim).size_local)
    return mesh.meshtags(
        msh,
        tdim,
        np.arange(owned, dtype=np.int32),
        np.ones(owned, dtype=np.int32),
    )


def _assemble_cell_skeleton(
    V: fem.FunctionSpace,
    condensed: object,
    provider: object,
) -> PETSc.Mat:
    comm = V.mesh.comm
    index_map = V.dofmap.index_map
    local_size = int(index_map.size_local) * int(V.dofmap.index_map_bs)
    matrix = PETSc.Mat().createAIJ(
        size=((local_size, int(condensed.full_rows)),) * 2,
        nnz=max(1, int(V.element.space_dimension)),
        comm=comm,
    )
    matrix.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR, False)
    tdim = V.mesh.topology.dim
    interior = np.asarray(
        V.element.basix_element.entity_dofs[tdim][0], dtype=np.int32
    )
    trace = np.setdiff1d(
        np.arange(int(V.element.space_dimension), dtype=np.int32),
        interior,
        assume_unique=True,
    )
    for cell in range(int(V.mesh.topology.index_map(tdim).size_local)):
        local_dofs = np.asarray(V.dofmap.cell_dofs(cell), dtype=np.int32)
        rows = np.asarray(index_map.local_to_global(local_dofs[trace]), dtype=PETSc.IntType)
        matrix.setValues(rows, rows, provider(cell), addv=PETSc.InsertMode.ADD_VALUES)
    matrix.assemble()
    return matrix


def _assemble_independent_skeleton_mass(V: fem.FunctionSpace, degree: int) -> PETSc.Mat:
    mesh_domain = V.mesh
    trial = ufl.TrialFunction(V)
    test = ufl.TestFunction(V)
    normal = ufl.FacetNormal(mesh_domain)
    ds = ufl.Measure("ds", domain=mesh_domain)
    dS = ufl.Measure("dS", domain=mesh_domain)
    form = (
        ufl.inner(ufl.cross(normal, trial), ufl.cross(normal, test)) * ds
        + ufl.inner(
            ufl.cross(normal("+"), trial("+")),
            ufl.cross(normal("+"), test("+")),
        )
        * dS
        + ufl.inner(
            ufl.cross(normal("-"), trial("-")),
            ufl.cross(normal("-"), test("-")),
        )
        * dS
    )
    matrix = fem_petsc.assemble_matrix(
        fem.form(
            form,
            dtype=PETSc.ScalarType,
            form_compiler_options={"quadrature_degree": int(degree)},
        ),
        bcs=[],
    )
    matrix.assemble()
    return matrix


@pytest.mark.skipif(
    MPI.COMM_WORLD.size not in (1, 2),
    reason="actual-cell impedance mass is focused on serial and MPI2",
)
def test_task040_actual_cell_impedance_mass_has_exact_authority() -> None:
    comm = MPI.COMM_WORLD
    msh = mesh.create_unit_cube(
        comm,
        1,
        1,
        2,
        cell_type=mesh.CellType.hexahedron,
        ghost_mode=mesh.GhostMode.shared_facet,
    )
    V = fem.functionspace(
        msh,
        element("N1curl", msh.basix_cell(), 2, dtype=default_real_type),
    )
    tags = _cell_tags(msh)
    u = ufl.TrialFunction(V)
    v = ufl.TestFunction(V)
    dx = ufl.Measure("dx", domain=msh, subdomain_data=tags)
    compiled = fem.form(
        (
            ufl.inner(ufl.curl(u), ufl.curl(v))
            + PETSc.ScalarType(2.0 - 0.15j) * ufl.inner(u, v)
        )
        * dx(1),
        dtype=PETSc.ScalarType,
        form_compiler_options={"quadrature_degree": 4},
    )
    condensed = build_unconstrained_assembly_time_condensation(
        compiled,
        V,
        tags,
        materialize_global_matrix=True,
        retain_local_schur_for_matrix_free=True,
    )
    provider = None
    skeleton = None
    reference = None
    action = None
    vector = None
    provider_output = None
    reference_output = None
    difference = None
    try:
        provider = build_actual_hcurl_cell_tangential_mass_provider(
            V,
            condensed,
            quadrature_degree=4,
        )
        skeleton = _assemble_cell_skeleton(V, condensed, provider)
        audit = provider.collective_audit()
        assert audit["status"] == "verified_exact_provider"
        assert audit["actual_hcurl_facet_form_assembler"] is True
        assert audit["kernel_nonnull"] is True
        assert audit["exterior_integral_count"] == 1
        assert audit["num_coefficients"] == 0
        assert audit["num_constants"] == 0
        assert audit["facets_per_cell"] == 6
        assert audit["facet_count_global"] == 6 * audit["owned_cell_count_global"]
        assert audit["trace_original_dofs_identity_global"] is True
        assert audit["all_classes_finite_global"] is True
        assert audit["all_evaluated_classes_verified_global"] is True
        assert audit["full_vector_numeric_allgather"] is False
        assert audit["served_cell_count_global"] == audit["owned_cell_count_global"]
        assert audit["evaluated_oriented_class_count_local"] > 0
        assert audit["oriented_class_audits_local"]
        assert all(
            item["support_complete"]
            and item["nonzero"]
            and item["hermitian"]
            and item["positive_semidefinite"]
            and item["interior_leakage_relative"] <= item["interior_leakage_gate"]
            for item in audit["oriented_class_audits_local"].values()
        )

        reference = _assemble_independent_skeleton_mass(V, 4)
        vector = skeleton.createVecRight()
        first, last = map(int, vector.getOwnershipRange())
        vector.array[:] = np.asarray(
            [0.25 + 0.017 * row + 1j * (0.1 - 0.003 * row) for row in range(first, last)],
            dtype=PETSc.ScalarType,
        )
        vector.assemble()
        provider_output = skeleton.createVecLeft()
        reference_output = reference.createVecLeft()
        skeleton.mult(vector, provider_output)
        reference.mult(vector, reference_output)
        difference = provider_output.copy()
        difference.axpy(PETSc.ScalarType(-1.0), reference_output)
        relative = difference.norm() / max(reference_output.norm(), 1.0e-300)
        assert relative <= 1.0e-11

        action = build_adaptive_impedance_schwarz_action(
            condensed,
            condensed.matrix,
            raw_tangential_face_mass_by_cell=provider,
            beta=0.7 + 0.2j,
        )
        diagnostics = action.diagnostics
        assert diagnostics["actual_hcurl_facet_form_assembler"] is True
        assert diagnostics["actual_hcurl_facet_form_assembler_status"] == (
            "verified_exact_provider"
        )
        assert diagnostics["tangential_mass_source"] == (
            "actual_hcurl_ufcx_exterior_facet_provider"
        )
        assert diagnostics["exact_provider_audit"]["status"] == (
            "verified_exact_provider"
        )
        assert diagnostics["exact_provider_audit"][
            "all_evaluated_classes_verified_global"
        ] is True
        assert diagnostics["exact_provider_audit"]["numeric_cache_released"] is True
        assert diagnostics["exact_provider_audit"]["raw_cache_size_local"] == 0
        assert diagnostics["exact_provider_audit"]["oriented_numeric_cache_size_local"] == 0
        assert diagnostics["outer_bare_f_unchanged"] is True
        assert provider.audit["numeric_cache_released"] is True
        assert provider.audit["raw_cache_size_local"] == 0
        action.destroy()
        assert action.diagnostics["factor_lifecycle"]["factor_count_ready"] == 0
        assert action.diagnostics["factor_lifecycle"]["destroyed"] is True
    finally:
        if action is not None:
            action.destroy()
        if provider is not None:
            provider.destroy()
        for item in (difference, reference_output, provider_output, vector):
            if item is not None:
                item.destroy()
        for item in (reference, skeleton):
            if item is not None:
                item.destroy()
        condensed.destroy()
