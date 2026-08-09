from __future__ import annotations

import numpy as np
import pytest
import ufl
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from dolfinx.fem import petsc as fem_petsc
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.fullspace_matrix_free_hcurl import (
    build_task037_extra_candidate_h_fullspace_action,
)


def _build_case(degree: int, mode: str):
    mesh_3d = mesh.create_unit_cube(
        MPI.COMM_SELF,
        2,
        2,
        1,
        cell_type=mesh.CellType.hexahedron,
    )
    tdim = mesh_3d.topology.dim
    owned_cells = int(mesh_3d.topology.index_map(tdim).size_local)
    tags = np.where(np.arange(owned_cells) % 2 == 0, 1, 2).astype(np.int32)
    cell_tags = mesh.meshtags(
        mesh_3d,
        tdim,
        np.arange(owned_cells, dtype=np.int32),
        tags,
    )
    V = fem.functionspace(
        mesh_3d,
        element(
            "N1curl",
            mesh_3d.basix_cell(),
            degree,
            dtype=default_real_type,
        ),
    )
    u = ufl.TrialFunction(V)
    v = ufl.TestFunction(V)
    dx = ufl.Measure("dx", domain=mesh_3d, subdomain_data=cell_tags)
    coefficients = {
        "curl": {
            1: PETSc.ScalarType(1.0 + 0.15j),
            2: PETSc.ScalarType(1.7 - 0.25j),
        },
        "mass": {
            1: PETSc.ScalarType(2.5 - 0.2j),
            2: PETSc.ScalarType(0.65 + 0.4j),
        },
    }
    terms = []
    for tag in (1, 2):
        curl_coefficient = coefficients["curl"][tag] if mode != "mass" else 0.0
        mass_coefficient = coefficients["mass"][tag] if mode != "curl" else 0.0
        terms.append(
            (
                curl_coefficient * ufl.inner(ufl.curl(u), ufl.curl(v))
                + mass_coefficient * ufl.inner(u, v)
            )
            * dx(tag)
        )
    return mesh_3d, cell_tags, V, fem.form(sum(terms))


def _source_vector(matrix: PETSc.Mat) -> PETSc.Vec:
    source = matrix.createVecRight()
    start, stop = source.getOwnershipRange()
    ids = np.arange(start, stop, dtype=PETSc.IntType)
    values = (1.0 + 0.013 * ids) + 1j * (0.35 - 0.007 * ids)
    source.setValues(ids, np.asarray(values, dtype=PETSc.ScalarType))
    source.assemble()
    return source


@pytest.mark.parametrize("degree", [2, 3])
@pytest.mark.parametrize("mode", ["curl", "mass", "both"])
def test_fullspace_action_matches_assembled_reference(degree: int, mode: str):
    _mesh, cell_tags, function_space, form = _build_case(degree, mode)
    assembled = fem_petsc.assemble_matrix(form)
    assembled.assemble()
    action = build_task037_extra_candidate_h_fullspace_action(
        form,
        function_space,
        cell_tags,
        task037_extra_candidate_h=True,
    )
    source = _source_vector(assembled)
    expected = assembled.createVecLeft()
    observed = assembled.createVecLeft()
    repeated = assembled.createVecLeft()
    difference = observed.copy()
    try:
        assembled.mult(source, expected)
        action.matrix.mult(source, observed)
        action.matrix.mult(source, repeated)
        observed.copy(result=difference)
        difference.axpy(PETSc.ScalarType(-1.0), expected)
        relative_error = difference.norm() / max(expected.norm(), 1.0e-30)
        assert relative_error <= 1.0e-11
        assert np.all(np.isfinite(observed.getArray(readonly=True)))
        assert np.array_equal(
            observed.getArray(readonly=True),
            repeated.getArray(readonly=True),
        )
        assert action.audit["degree"] == degree
        assert action.audit["material_tags"] == (1, 2)
        assert action.audit["global_matrix_materialized"] is False
        assert action.audit["retained_cell_dense_matrix_count"] == 0
        assert action.audit["cell_tensor_scratch_count"] == 1
        assert action.audit["cell_tensor_scratch_bytes"] > 0
        assert action.audit["cell_tensor_scratch_reused"] is True
        assert action.audit["slab_matrix_nnz"] == 0
        assert action.audit["slab_factor_count"] == 0
        assert action.audit["factor_count"] == 0
    finally:
        difference.destroy()
        repeated.destroy()
        observed.destroy()
        expected.destroy()
        source.destroy()
        action.destroy()
        assembled.destroy()


def test_candidate_h_factory_requires_explicit_opt_in():
    _mesh, cell_tags, function_space, form = _build_case(2, "both")
    with pytest.raises(ValueError, match="explicit opt-in"):
        build_task037_extra_candidate_h_fullspace_action(
            form,
            function_space,
            cell_tags,
        )
