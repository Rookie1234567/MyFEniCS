"""Focused Stage-B1 Gamma lifting and symbolic coarse preflight checks."""

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
    build_cell_active_trace_expansion,
)
from src.solvers.hybrid_maxwell_harmonic_coarse import (
    HARD_MEMORY_BYTES,
    K0,
    STAGE_B1_RHO,
    STAGE_B1_RHO2,
    build_stage_b1_harmonic_identity,
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
        form_compiler_options={"quadrature_degree": 12},
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
    reason="Stage-B1 focused coverage is serial and MPI2",
)
def test_task040_stage_b1_harmonic_identity_and_memory_preflight() -> None:
    comm = MPI.COMM_WORLD
    msh = mesh.create_unit_cube(
        comm,
        1,
        1,
        1,
        cell_type=mesh.CellType.hexahedron,
        ghost_mode=mesh.GhostMode.shared_facet,
    )
    V = fem.functionspace(
        msh,
        element("N1curl", msh.basix_cell(), 6, dtype=default_real_type),
    )
    cell_tags = _cell_tags(msh)
    facet_tags = _facet_tags(msh, 17)
    condensed = _condensed(V, cell_tags)
    provider = None
    action = None
    try:
        provider = build_actual_hcurl_cell_tangential_mass_provider(
            V,
            condensed,
            quadrature_degree=12,
        )
        tdim = msh.topology.dim
        connectivity = msh.topology.connectivity(tdim, tdim - 1)
        owned = int(msh.topology.index_map(tdim).size_local)
        owned_counts = comm.allgather(owned)
        assert sum(owned_counts) == 1
        if comm.size == 2:
            assert 0 in owned_counts
        for cell in range(owned):
            raw_rows, active_rows, expansion = build_cell_active_trace_expansion(
                condensed, cell
            )
            assert expansion.shape == (len(raw_rows), len(active_rows))
            blocks = provider.stream_facet_trace_blocks(cell)
            assert [item[0] for item in blocks] == list(range(6))
            assert [item[1] for item in blocks] == [
                int(value) for value in connectivity.links(cell)
            ]
            summed = np.zeros_like(blocks[0][2])
            for _facet, _entity, block in blocks:
                summed += block
            assert np.allclose(summed, provider(cell), rtol=1.0e-13, atol=1.0e-13)
            external = {int(value) for value in facet_tags.find(17)}
            cell_facets = {int(value) for value in connectivity.links(cell)}
            assert len(cell_facets & external) == 1
            assert len(cell_facets - external) == 5
            no_external = {int(value) for value in facet_tags.find(19)}
            assert not cell_facets & no_external
            assert len(cell_facets - no_external) == 6

        action = build_adaptive_impedance_schwarz_action(
            condensed,
            condensed.matrix,
            raw_tangential_face_mass_by_cell=provider,
            beta=0.7 + 0.2j,
        )
        evidence = build_stage_b1_harmonic_identity(
            V,
            condensed,
            condensed.matrix,
            action,
            provider,
            cell_tags,
            facet_tags,
            17,
            current_process_tree_baseline_bytes=0,
            current_process_tree_baseline_source="fixture",
        )
        assert evidence["rho"] == STAGE_B1_RHO
        assert evidence["rho2"] == STAGE_B1_RHO2
        assert evidence["k0"] == K0
        assert evidence["patch_count"] == int(
            comm.allreduce(owned, op=MPI.SUM)
        )
        assert evidence["selected_mode_count_total"] >= 0
        assert evidence["identity_pass"] is True
        assert sum(evidence["selected_modes_per_patch_histogram"].values()) == (
            evidence["patch_count"]
        )
        assert evidence["full_vector_numeric_allgather"] is False
        assert evidence["distributed_prolongation_created"] is False
        assert evidence["coarse_matrix_created"] is False
        assert evidence["memory_preflight"]["hard_memory_bytes"] == HARD_MEMORY_BYTES
        assert evidence["memory_preflight"]["allocation_allowed"] is True
        memory = evidence["memory_preflight"]
        assert memory["baseline_known"] is True
        assert memory["current_process_tree_baseline_source"] == "fixture"
        assert memory["allocation_decision_collective"] is True
        assert memory["FP_nnz_upper"] >= 0
        assert memory["Ac_nnz_upper"] >= 0
        components = memory["components_bytes"]
        assert components["PETSc_sparse_allocation_overhead"] == (
            memory["sparse_base_bytes"]
        )
        assert memory["fixed_byte_model"][
            "petsc_sparse_allocation_overhead_multiplier"
        ] == 1.0
        assert memory["projected_peak_bytes_conservative"] is not None
        action_audit = action.diagnostics
        assert action_audit["numeric_collective_type"] == "bounded_object_alltoall"
        assert action_audit["numeric_object_alltoall_count"] == 0
        assert action_audit["harmonic_numeric_object_alltoall_count_per_solve"] == 2
        assert action_audit["harmonic_numeric_object_alltoall_count"] == 2 * evidence["patch_count"]
        assert action_audit["harmonic_max_numeric_payload_bytes"] >= 0
        assert action_audit["harmonic_max_sender_payload_bytes"] >= 0
        assert action_audit["harmonic_max_owner_payload_bytes"] >= 0
        assert action_audit["global_sequential_union"] is False
        assert action_audit["full_vector_numeric_allgather"] is False
        assert action_audit["full_numeric_replica"] is False
        assert action_audit["harmonic_multi_rhs_solve_count"] == evidence["patch_count"]
        provider_audit = evidence["exact_provider_audit"]
        assert provider_audit["status"] == "verified_exact_provider"
        assert provider_audit["actual_hcurl_facet_form_assembler"] is True
        assert provider_audit["exterior_integral_count"] == 1
        assert provider_audit["facets_per_cell"] == 6
        assert provider_audit["trace_original_dofs_identity_global"] is True
        assert provider_audit["all_classes_finite_global"] is True
        assert provider_audit["all_evaluated_classes_verified_global"] is True
        assert provider_audit["served_cell_count_global"] == 1
        assert provider_audit["numeric_cache_released"] is True
        assert provider_audit["raw_cache_size_local"] == 0
        assert provider_audit["oriented_numeric_cache_size_local"] == 0
        if owned:
            assert provider_audit["evaluated_oriented_class_count_local"] >= 1
        else:
            assert provider_audit["evaluated_oriented_class_count_local"] == 0
        assert provider_audit["oriented_class_count_global"] >= 1
        for class_audit in provider_audit["oriented_class_audits_local"].values():
            assert class_audit["finite"] is True
            assert class_audit["hermitian"] is True
            assert class_audit["positive_semidefinite"] is True
            assert class_audit["support_complete"] is True
            assert class_audit["interior_leakage_relative"] <= 1.0e-10
            assert len(class_audit["six_facet_norms"]) == 6
        for item in evidence["patch_audits"]:
            assert item["gamma_facets"] == 5
            assert item["B_positive_definite"] is True
            assert item["G_positive_semidefinite"] is True
            assert item["A_positive_semidefinite"] is True
            assert item["G_hermitian_defect"] < 1.0e-10
            assert item["A_hermitian_defect"] < 1.0e-10
            assert item["B_hermitian_defect"] < 1.0e-10
            assert item["harmonic_solve_residual_max"] < 1.0e-10
            assert item["eigen_residual"] < 1.0e-10
            assert item["B_orthogonality_defect"] < 1.0e-10
            assert item["retained_rank"] >= 1
            assert "gap" in item["rank_reveal"]
            assert item["selected_column_definition"] == "D*T*q"
    finally:
        if action is not None:
            action.destroy()
        if provider is not None:
            provider.destroy()
        condensed.destroy()
